#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
한국주식 추세매매봇 (Trend Trading Bot)
기존 단타봇(day_trading.py)에서 전략 변경
1. 관심 섹터/종목에서 상승 전환흐름 포착 및 저점 매수
2. 일봉과 분봉 데이터 활용한 차트 분석 
3. 보조지표 활용 (RSI, MACD, 볼린저밴드)
4. 수익률 및 예산 지정
"""

import os
import sys
import time
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
import numpy as np
import pandas as pd
import random  # 여기에 random 모듈 추가
import requests  # 네이버 금융 조회를 위해 추가
from bs4 import BeautifulSoup  # 네이버 금융 조회를 위해 추가
from pykrx import stock
from typing import List, Dict, Tuple, Optional, Union

# KIS API 함수 임포트
import KIS_Common as Common
import KIS_API_Helper_KR as KisKR

# 로깅 설정
# 로그 디렉토리 생성
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# 로그 파일명 생성 함수
def log_namer(default_name):
    """로그 파일 이름 생성 함수"""
    base_filename, ext, date = default_name.split(".")
    return f"{base_filename}.{date}.{ext}"

# 로거 설정
logger = logging.getLogger('TrendTrader')
logger.setLevel(logging.INFO)

# 기존 핸들러 제거 (중복 방지)
if logger.handlers:
    logger.handlers.clear()

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'trend_trading.log')
file_handler = logging.handlers.TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=7,    # 7일치 로그 파일만 보관
    encoding='utf-8'
)
file_handler.suffix = "%Y%m%d"
file_handler.namer = log_namer

# 콘솔 핸들러 설정
console_handler = logging.StreamHandler()

# 포맷터 설정
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 핸들러 추가
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# KIS API Logger 설정
KisKR.set_logger(logger)

class TechnicalIndicators:
    """기술적 지표 계산 클래스"""

    def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR(Average True Range) 계산
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close', 'high', 'low' 컬럼이 필요
            period: ATR 계산 기간
            
        Returns:
            Series: ATR 값
        """
        high = data['high']
        low = data['low']
        close = data['close']
        
        # True Range 계산
        tr1 = abs(high - low)
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR 계산 (단순 이동평균)
        atr = tr.rolling(window=period).mean()
        
        return atr

    # 동적 ATR 기반 손절 계산 함수
    @staticmethod
    def calculate_dynamic_stop_loss(price: float, atr: float, multiplier: float = 2.0) -> float:
        """ATR 기반 동적 손절가 계산
        
        Args:
            price: 현재 가격
            atr: ATR 값
            multiplier: ATR 승수 (기본값 2)
            
        Returns:
            float: 손절가
        """
        stop_loss = price - (atr * multiplier)
        return stop_loss

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """RSI(Relative Strength Index) 계산
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close' 컬럼이 필요
            period: RSI 계산 기간
            
        Returns:
            Series: RSI 값
        """
        delta = data['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss.where(avg_loss != 0, 0.00001)  # 0으로 나누는 것 방지
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_macd(data: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
        """MACD(Moving Average Convergence Divergence) 계산
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close' 컬럼이 필요
            fast_period: 빠른 이동평균 기간
            slow_period: 느린 이동평균 기간
            signal_period: 시그널 라인 기간
            
        Returns:
            DataFrame: MACD, Signal, Histogram 값
        """
        # 지수이동평균(EMA) 계산
        ema_fast = data['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = data['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD 라인 계산
        macd_line = ema_fast - ema_slow
        
        # 시그널 라인 계산
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        
        # 히스토그램 계산
        histogram = macd_line - signal_line
        
        return pd.DataFrame({
            'MACD': macd_line,
            'Signal': signal_line,
            'Histogram': histogram
        })
    
    @staticmethod
    def calculate_bollinger_bands(data: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
        """볼린저 밴드 계산
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close' 컬럼이 필요
            period: 이동평균 기간
            num_std: 표준편차 배수
            
        Returns:
            DataFrame: 중앙선, 상단밴드, 하단밴드
        """
        # 이동평균(MA) 계산
        middle_band = data['close'].rolling(window=period).mean()
        
        # 표준편차 계산
        std = data['close'].rolling(window=period).std()
        
        # 상하단 밴드 계산
        upper_band = middle_band + (std * num_std)
        lower_band = middle_band - (std * num_std)
        
        return pd.DataFrame({
            'MiddleBand': middle_band,
            'UpperBand': upper_band,
            'LowerBand': lower_band
        })
    
    @staticmethod
    def calculate_stochastic(data: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
        """스토캐스틱 오실레이터 계산
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close', 'high', 'low' 컬럼이 필요
            k_period: %K 기간
            d_period: %D 기간
            
        Returns:
            DataFrame: %K, %D 값
        """
        # 최저가, 최고가 계산
        low_min = data['low'].rolling(window=k_period).min()
        high_max = data['high'].rolling(window=k_period).max()
        
        # %K 계산 ((종가 - 최저가) / (최고가 - 최저가)) * 100
        k = ((data['close'] - low_min) / (high_max - low_min).where(high_max != low_min, 0.00001)) * 100
        
        # %D 계산 (%K의 d_period 이동평균)
        d = k.rolling(window=d_period).mean()
        
        return pd.DataFrame({
            'K': k,
            'D': d
        })
    
    @staticmethod
    def is_golden_cross(data: pd.DataFrame, short_period: int = 5, long_period: int = 20) -> bool:
        """골든 크로스 확인 (단기 이평선이 장기 이평선을 상향 돌파)
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close' 컬럼이 필요
            short_period: 단기 이동평균 기간
            long_period: 장기 이동평균 기간
            
        Returns:
            bool: 골든 크로스 발생 여부
        """
        if len(data) < long_period + 2:
            return False
        
        # 단기, 장기 이동평균 계산
        ma_short = data['close'].rolling(window=short_period).mean()
        ma_long = data['close'].rolling(window=long_period).mean()
        
        # 현재와 이전 데이터 비교
        prev_short = ma_short.iloc[-2]
        prev_long = ma_long.iloc[-2]
        curr_short = ma_short.iloc[-1]
        curr_long = ma_long.iloc[-1]
        
        # 골든 크로스 조건: 이전에는 단기<장기, 현재는 단기>=장기
        return (prev_short < prev_long) and (curr_short >= curr_long)
    
    @staticmethod
    def is_death_cross(data: pd.DataFrame, short_period: int = 5, long_period: int = 20) -> bool:
        """데드 크로스 확인 (단기 이평선이 장기 이평선을 하향 돌파)
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close' 컬럼이 필요
            short_period: 단기 이동평균 기간
            long_period: 장기 이동평균 기간
            
        Returns:
            bool: 데드 크로스 발생 여부
        """
        if len(data) < long_period + 2:
            return False
        
        # 단기, 장기 이동평균 계산
        ma_short = data['close'].rolling(window=short_period).mean()
        ma_long = data['close'].rolling(window=long_period).mean()
        
        # 현재와 이전 데이터 비교
        prev_short = ma_short.iloc[-2]
        prev_long = ma_long.iloc[-2]
        curr_short = ma_short.iloc[-1]
        curr_long = ma_long.iloc[-1]
        
        # 데드 크로스 조건: 이전에는 단기>장기, 현재는 단기<=장기
        return (prev_short > prev_long) and (curr_short <= curr_long)
    
    @staticmethod
    def detect_support_resistance(data: pd.DataFrame, period: int = 20, threshold: float = 0.03) -> Dict[str, float]:
        """지지선/저항선 탐지
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close', 'high', 'low' 컬럼이 필요
            period: 분석 기간
            threshold: 가격 그룹화 임계값(비율)
            
        Returns:
            Dict: 지지선, 저항선 가격
        """
        if len(data) < period:
            return {"support": None, "resistance": None}
        
        # 최근 데이터 추출
        recent_data = data.iloc[-period:]
        
        # 고가/저가 분석
        highs = recent_data['high'].values
        lows = recent_data['low'].values
        
        # 지지선/저항선 탐지 (간단한 예시 - 실제로는 더 복잡한 알고리즘 사용 가능)
        support = np.percentile(lows, 10)  # 하위 10% 지점을 지지선으로 간주
        resistance = np.percentile(highs, 90)  # 상위 90% 지점을 저항선으로 간주
        
        return {
            "support": support,
            "resistance": resistance
        }
    
    @staticmethod
    def calculate_momentum(data: pd.DataFrame, period: int = 10) -> pd.Series:
        """모멘텀 지표 계산
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'close' 컬럼이 필요
            period: 모멘텀 계산 기간
            
        Returns:
            Series: 모멘텀 값
        """
        # 현재 종가와 n일 전 종가의 변화율
        momentum = (data['close'] / data['close'].shift(period)) * 100 - 100
        return momentum
    
    @staticmethod
    def is_oversold_rsi(rsi_value: float, threshold: float = 30.0) -> bool:
        """RSI 과매도 영역 확인
        
        Args:
            rsi_value: RSI 값
            threshold: 과매도 기준값
            
        Returns:
            bool: 과매도 여부
        """
        return rsi_value is not None and rsi_value <= threshold
    
    @staticmethod
    def is_overbought_rsi(rsi_value: float, threshold: float = 70.0) -> bool:
        """RSI 과매수 영역 확인
        
        Args:
            rsi_value: RSI 값
            threshold: 과매수 기준값
            
        Returns:
            bool: 과매수 여부
        """
        return rsi_value is not None and rsi_value >= threshold

class AdaptiveMarketStrategy:
    """종목별 시장 환경 적응형 전략 클래스"""
    
    def __init__(self, strategy_file="adaptive_strategy.json"):
        """초기화"""
        self.strategy_file = strategy_file
        self.stock_performance = {}  # 종목별 시장 환경 성과 데이터
        self.load_strategy()
    
    def load_strategy(self):
        """전략 데이터 로드"""
        try:
            if os.path.exists(self.strategy_file):
                with open(self.strategy_file, 'r', encoding='utf-8') as f:
                    self.stock_performance = json.load(f)
                logger.info(f"적응형 전략 데이터 로드 완료: {len(self.stock_performance)}개 종목")
            else:
                logger.info("적응형 전략 데이터 파일이 없습니다. 새로 생성합니다.")
                self.stock_performance = {}
        except Exception as e:
            logger.exception(f"적응형 전략 데이터 로드 중 오류: {str(e)}")
            self.stock_performance = {}
    
    def save_strategy(self):
        """전략 데이터 저장"""
        try:
            with open(self.strategy_file, 'w', encoding='utf-8') as f:
                json.dump(self.stock_performance, f, ensure_ascii=False, indent=4)
            logger.info(f"적응형 전략 데이터 저장 완료")
        except Exception as e:
            logger.exception(f"적응형 전략 데이터 저장 중 오류: {str(e)}")
    
    def get_stock_strategy(self, stock_code, market_env):
        """종목별 시장 환경에 따른 전략 파라미터 가져오기"""
        default_strategies = {
            "uptrend": {
                "profit_target_multiplier": 1.5,
                "stop_loss_multiplier": 0.8,
                "rsi_threshold_adjustment": 5,
                "required_signals": 2,
                "trailing_stop_multiplier": 0.9
            },
            "downtrend": {
                "profit_target_multiplier": 0.8,
                "stop_loss_multiplier": 0.6,
                "rsi_threshold_adjustment": -5,
                "required_signals": 3,
                "trailing_stop_multiplier": 0.7
            },
            "sideways": {
                "profit_target_multiplier": 1.0,
                "stop_loss_multiplier": 1.0,
                "rsi_threshold_adjustment": 0,
                "required_signals": 2,
                "trailing_stop_multiplier": 1.0
            }
        }
        
        # 종목이 데이터에 없으면 초기화
        if stock_code not in self.stock_performance:
            self.stock_performance[stock_code] = {
                "uptrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                "downtrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                "sideways": {"trades": 0, "wins": 0, "winrate": 0.0},
                "adaptive_strategy": {
                    "uptrend": {"use_common": True},
                    "downtrend": {"use_common": True},
                    "sideways": {"use_common": True}
                }
            }
        
        # 종목별 맞춤 전략 가져오기
        stock_data = self.stock_performance[stock_code]
        adaptive_strategy = stock_data["adaptive_strategy"][market_env]
        
        # 공통 전략 사용 여부
        if adaptive_strategy.get("use_common", True):
            return default_strategies[market_env]
        
        # 맞춤 전략 반환
        return {
            "profit_target_multiplier": adaptive_strategy.get("profit_target_multiplier", default_strategies[market_env]["profit_target_multiplier"]),
            "stop_loss_multiplier": adaptive_strategy.get("stop_loss_multiplier", default_strategies[market_env]["stop_loss_multiplier"]),
            "rsi_threshold_adjustment": adaptive_strategy.get("rsi_threshold_adjustment", default_strategies[market_env]["rsi_threshold_adjustment"]),
            "required_signals": adaptive_strategy.get("required_signals", default_strategies[market_env]["required_signals"]),
            "trailing_stop_multiplier": adaptive_strategy.get("trailing_stop_multiplier", default_strategies[market_env]["trailing_stop_multiplier"])
        }
    
    def update_performance(self, stock_code, market_env, win):
        """거래 성과 업데이트"""
        if stock_code not in self.stock_performance:
            self.stock_performance[stock_code] = {
                "uptrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                "downtrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                "sideways": {"trades": 0, "wins": 0, "winrate": 0.0},
                "adaptive_strategy": {
                    "uptrend": {"use_common": True},
                    "downtrend": {"use_common": True},
                    "sideways": {"use_common": True}
                }
            }
        
        # 성과 데이터 업데이트
        env_data = self.stock_performance[stock_code][market_env]
        env_data["trades"] += 1
        if win:
            env_data["wins"] += 1
        
        # 승률 계산
        if env_data["trades"] > 0:
            env_data["winrate"] = (env_data["wins"] / env_data["trades"]) * 100
        
        # 맞춤 전략 조정 (승률에 따른 자동 조정)
        self._adjust_strategy(stock_code, market_env)
        
        # 데이터 저장
        self.save_strategy()
    
    def _adjust_strategy(self, stock_code, market_env):
        """성과에 따른 전략 자동 조정"""
        env_data = self.stock_performance[stock_code][market_env]
        adaptive_strategy = self.stock_performance[stock_code]["adaptive_strategy"][market_env]
        
        # 최소 5회 이상 거래가 있어야 조정
        if env_data["trades"] < 5:
            adaptive_strategy["use_common"] = True
            return
        
        # 승률에 따른 맞춤 전략 설정
        winrate = env_data["winrate"]
        
        # 60% 이상 승률 - 기존 전략이 잘 동작
        if winrate >= 60:
            adaptive_strategy["use_common"] = True
        
        # 40%~60% 승률 - 약간 조정 필요
        elif winrate >= 40:
            if market_env == "uptrend":
                adaptive_strategy["use_common"] = False
                adaptive_strategy["profit_target_multiplier"] = 1.3  # 30% 증가 (기본값보다 약간 낮게)
                adaptive_strategy["stop_loss_multiplier"] = 0.7  # 30% 감소 (더 타이트하게)
                adaptive_strategy["rsi_threshold_adjustment"] = 3  # 약간만 완화
                adaptive_strategy["required_signals"] = 3  # 시그널 요구 증가
            else:
                adaptive_strategy["use_common"] = True
        
        # 40% 미만 승률 - 완전히 다른 전략 필요
        else:
            adaptive_strategy["use_common"] = False
            
            if market_env == "uptrend":
                # 상승장에서 성과가 좋지 않은 경우, 반대 전략 적용
                adaptive_strategy["profit_target_multiplier"] = 1.0  # 증가시키지 않음
                adaptive_strategy["stop_loss_multiplier"] = 0.5  # 50% 감소 (매우 타이트하게)
                adaptive_strategy["rsi_threshold_adjustment"] = -3  # 오히려 엄격하게
                adaptive_strategy["required_signals"] = 4  # 시그널 요구 크게 증가
                adaptive_strategy["trailing_stop_multiplier"] = 0.7  # 트레일링 스탑 30% 감소 (더 타이트하게)
            
            elif market_env == "downtrend":
                # 하락장에서 성과가 좋지 않은 경우, 보수적 전략
                adaptive_strategy["profit_target_multiplier"] = 0.6  # 목표 수익률 40% 감소
                adaptive_strategy["stop_loss_multiplier"] = 0.4  # 60% 감소 (매우 타이트하게)
                adaptive_strategy["required_signals"] = 5  # 매우 확실한 시그널만

class TrendTraderBot:
    """한국주식 추세매매봇 클래스"""

    def __init__(self, config_path: str = "trend_trader_config.json"):
        """매매봇 초기화
        
        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        # 설정 파일 경로 저장
        self.config_path = config_path
        
        self.tech_indicators = TechnicalIndicators()
        
        # 업데이트된 구성 파일에서 정보 가져오기
        self.watch_list = [item.get("code") for item in self.config.get("watch_list", [])]
        self.watch_list_info = {item.get("code"): item for item in self.config.get("watch_list", [])}

        # 섹터 정보 자동 업데이트 기능 추가
        if self.config.get("trading_strategies", {}).get("use_auto_sector_lookup", True):
            self._update_sector_info()

        # 여기서 하드코딩된 기본값을 제거하고 항상 config에서 가져옴
        self.total_budget = self.config.get("total_budget")
        self.profit_target = self.config.get("profit_target")
        self.stop_loss = self.config.get("stop_loss")
        self.max_stocks = self.config.get("max_stocks")
        self.min_trading_amount = self.config.get("min_trading_amount")
        
        # 매매 전략 설정
        trading_strategies = self.config.get("trading_strategies", {})
        self.rsi_oversold = trading_strategies.get("rsi_oversold_threshold")
        self.rsi_overbought = trading_strategies.get("rsi_overbought_threshold")
        self.macd_fast_period = trading_strategies.get("macd_fast_period")
        self.macd_slow_period = trading_strategies.get("macd_slow_period")
        self.macd_signal_period = trading_strategies.get("macd_signal_period")
        # 추가: 섹터 필터 설정
        self.use_sector_filter = trading_strategies.get("use_sector_filter", False)

        # 아래는 추가할 속성들 - run 메서드에서 필요한 설정
        self.check_interval_seconds = trading_strategies.get("check_interval_seconds", 3600)
        self.default_allocation_ratio = trading_strategies.get("default_allocation_ratio", 0.2)
        self.use_split_purchase = trading_strategies.get("use_split_purchase", True)
        self.initial_purchase_ratio = trading_strategies.get("initial_purchase_ratio", 0.5)
        self.additional_purchase_drop_pct = trading_strategies.get("additional_purchase_drop_pct", [1.5])
        self.score_weights = trading_strategies.get("score_weights", {})
        self.use_dynamic_stop = trading_strategies.get("use_dynamic_stop", False)
        self.use_trailing_stop = trading_strategies.get("use_trailing_stop", False)
        self.trailing_stop_pct = trading_strategies.get("trailing_stop_pct", 1.8)
        
        # analyze_stock에서 필요한 추가 속성
        self.use_daily_trend_filter = trading_strategies.get("use_daily_trend_filter", False)
        self.use_market_trend_filter = trading_strategies.get("use_market_trend_filter", False)
        self.market_index_code = trading_strategies.get("market_index_code", "069500")
        self.daily_trend_lookback = trading_strategies.get("daily_trend_lookback", 3)
        self.atr_multiplier = trading_strategies.get("atr_multiplier", 1.5)
        self.bollinger_period = trading_strategies.get("bollinger_period", 20)
        self.bollinger_std = trading_strategies.get("bollinger_std", 2.0)

        # 섹터 캐시 추가 (섹터 강도 분석용)
        self.sector_cache = {}
        
        # 적응형 전략 객체 추가
        self.adaptive_strategy = AdaptiveMarketStrategy()
        
        # 종목 특성 분석 및 적응형 전략 초기화
        self.update_stock_characteristics()

        self.holdings = {}  # 보유 종목 정보
        self.last_check_time = {}  # 마지막 검사 시간
        
        # 보유종목 로드
        self._load_holdings()

    def _load_config(self, config_path: str) -> Dict[str, any]:
        """설정 파일 로드
        
        Args:
            config_path: 설정 파일 경로
            
        Returns:
            Dict: 설정 정보
        """
        # 기본 설정값 정의
        default_config = {
            "api_key": "",
            "api_secret": "",
            "account_number": "",
            "account_code": "",
            "watch_list": [],
            "sector_list": [],
            "total_budget": 5000000,
            "profit_target": 5.0,
            "stop_loss": -2.0,
            "max_stocks": 4,
            "min_trading_amount": 300000,
            "trading_strategies": {
                "rsi_oversold_threshold": 30.0,
                "rsi_overbought_threshold": 68.0,
                "macd_fast_period": 10,
                "macd_slow_period": 24,
                "macd_signal_period": 8,
                "use_trailing_stop": True,
                "trailing_stop_pct": 1.8,
                "use_dynamic_stop": True,
                "atr_period": 10,
                "atr_multiplier": 1.5,
                # 추가: 섹터 필터 설정
                "use_sector_filter": True,
                "use_split_purchase": True,
                "initial_purchase_ratio": 0.50,
                "additional_purchase_ratios": [0.30, 0.20],
                "additional_purchase_drop_pct": [1.5, 3.0],
                "bollinger_period": 18,
                "bollinger_std": 2.0,
                "short_ma_period": 5,
                "mid_ma_period": 20,
                "long_ma_period": 60,
                "use_partial_profit": True,
                "partial_profit_target": 4.0,
                "partial_profit_ratio": 0.5,
                "use_time_filter": True,
                "avoid_trading_hours": ["09:00-10:00", "14:30-15:30"],
                "use_consecutive_drop_filter": True,
                "consecutive_drop_days": 2,
                "use_daily_trend_filter": True,
                "use_market_trend_filter": True,
                "market_index_code": "069500",
                "daily_trend_lookback": 3,
                "score_weights": {
                    "rsi_oversold": 3,
                    "golden_cross": 2,
                    "macd_cross_up": 3,
                    "near_lower_band": 2,
                    "momentum_turning_up": 1,
                    "near_support": 3,
                    "minute_rsi_oversold": 1,
                    "minute_macd_cross_up": 1,
                    "consecutive_drop": 2
                }
            }
        }
        
        try:
            # 설정 파일 열기
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 재귀적으로 설정값 병합 함수 정의
            def merge_config(default, loaded):
                result = default.copy()
                for key, value in loaded.items():
                    # 딕셔너리인 경우 재귀적으로 병합
                    if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                        result[key] = merge_config(result[key], value)
                    else:
                        result[key] = value
                return result
            
            # 기본 설정과 로드된 설정 병합
            merged_config = merge_config(default_config, loaded_config)
            
            logger.info(f"설정 파일 로드 완료: {config_path}")
            return merged_config
        
        except FileNotFoundError:
            logger.warning(f"설정 파일 {config_path}을 찾을 수 없습니다. 기본값을 사용합니다.")
            return default_config
        
        except json.JSONDecodeError:
            logger.error(f"설정 파일 {config_path}의 형식이 올바르지 않습니다. 기본값을 사용합니다.")
            return default_config
        
        except Exception as e:
            logger.exception(f"설정 파일 로드 중 오류: {str(e)}")
            return default_config

    def _save_config(self, config_path: str = "trend_trader_config.json") -> None:
        """설정 파일 저장
        
        Args:
            config_path: 설정 파일 경로
        """
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"설정 파일 저장 완료: {config_path}")
        except Exception as e:
            logger.exception(f"설정 파일 저장 중 오류: {str(e)}")

    # 트레일링 스탑 구현을 위한 holdings 구조 확장
    def _load_holdings(self) -> None:
        """전략 관리 종목 정보 로드"""
        try:
            if os.path.exists("trend_strategy_holdings.json"):
                with open("trend_strategy_holdings.json", 'r', encoding='utf-8') as f:
                    self.holdings = json.load(f)
                    
                logger.info(f"전략 관리 종목 로드 완료: {len(self.holdings)}개")
                
                # 현재가 업데이트
                for stock_code in list(self.holdings.keys()):
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price is not None and not isinstance(current_price, str):
                        self.holdings[stock_code]["current_price"] = current_price
                    else:
                        # 종목 정보를 가져올 수 없으면 제거 (옵션)
                        logger.warning(f"종목 {stock_code} 현재가를 조회할 수 없습니다. 홀딩에서 제거합니다.")
                        del self.holdings[stock_code]
            else:
                logger.info("전략 관리 종목 파일이 없습니다.")
                self.holdings = {}
        except Exception as e:
            logger.exception(f"전략 관리 종목 로드 중 오류: {str(e)}")
            self.holdings = {}

    def _save_holdings(self) -> None:
        """보유 종목 정보 저장"""
        try:
            # 전략 관리 종목만 필터링
            strategy_holdings = {k: v for k, v in self.holdings.items() 
                                if v.get("is_strategy_managed", False)}
                                
            with open("trend_strategy_holdings.json", 'w', encoding='utf-8') as f:
                json.dump(strategy_holdings, f, ensure_ascii=False, indent=4)
                
            logger.info(f"전략 관리 종목 정보 저장 완료: {len(strategy_holdings)}개")
        except Exception as e:
            logger.exception(f"전략 관리 종목 정보 저장 중 오류: {str(e)}")

    def check_sector_strength(self, sector_code: str) -> bool:
        """섹터 강도 확인 - 실시간 업종 동향 분석 활용
        
        Args:
            sector_code: 섹터 코드
            
        Returns:
            bool: 섹터 강세 여부
        """
        try:
            # 섹터 코드가 유효하지 않은 경우
            if not sector_code or sector_code == "Unknown":
                return True  # 기본적으로 통과
            
            # 캐싱을 위한 키 생성 (1시간 단위)
            cache_key = f"sector_strength_{sector_code}_{datetime.datetime.now().strftime('%Y%m%d_%H')}"
            
            # 캐시된 결과가 있는지 확인
            if cache_key in self.sector_cache:
                return self.sector_cache[cache_key]
            
            # 섹터 대표 종목 찾기
            representative_stock = self._find_sector_representative(sector_code)
            
            if not representative_stock:
                logger.info(f"섹터 '{sector_code}'에 대한 대표 종목을 찾을 수 없습니다. 기본 통과로 설정합니다.")
                return True
            
            # 업종 동향 분석
            is_strong, details = analyze_sector_trend(representative_stock)
            
            # 분석 결과 로깅
            if isinstance(details, dict):
                logger.info(f"섹터 '{sector_code}' 분석: 상승 비율 {details.get('rising_ratio', 0):.2f}, " +
                        f"평균 변동률 {details.get('avg_change', 0):.2f}%, 강세 여부: {is_strong}")
            else:
                logger.info(f"섹터 '{sector_code}' 분석: {details}, 강세 여부: {is_strong}")
            
            # 결과 캐싱
            self.sector_cache[cache_key] = is_strong
            
            return is_strong
        
        except Exception as e:
            logger.exception(f"섹터 강도 확인 중 오류: {str(e)}")
            return True  # 오류 발생 시 기본적으로 통과

    def _find_sector_representative(self, sector_code: str) -> str:
        """섹터의 대표 종목 찾기"""
        try:
            # 같은 섹터 내 모든 종목 수집
            same_sector_stocks = []
            
            for code, info in self.watch_list_info.items():
                if info.get("sector_code") == sector_code:
                    same_sector_stocks.append(code)
            
            if not same_sector_stocks:
                return None
            
            # 시가총액 정보로 정렬하려면 추가 작업 필요
            # 여기서는 단순히 첫 번째 종목 반환
            return same_sector_stocks[0]
            
        except Exception as e:
            logger.exception(f"섹터 대표 종목 찾기 중 오류: {str(e)}")
            return None

    def _update_sector_info(self):
        """종목별 섹터 정보 자동 업데이트"""
        try:
            updated_count = 0
            
            # 각 관심종목에 대해 섹터 정보 업데이트
            for stock_code in self.watch_list:
                # 이미 섹터 정보가 있는지 확인
                existing_info = self.watch_list_info.get(stock_code, {})
                if existing_info.get("sector_code") == "Unknown" or not existing_info.get("sector_code"):
                    # 네이버 금융을 통한 섹터 정보 조회
                    sector_info = get_sector_info(stock_code)
                    
                    # 정보 업데이트
                    if sector_info['sector'] != 'Unknown':
                        if stock_code in self.watch_list_info:
                            self.watch_list_info[stock_code]["sector_code"] = sector_info['sector']
                        else:
                            self.watch_list_info[stock_code] = {
                                "code": stock_code,
                                "sector_code": sector_info['sector'],
                                "allocation_ratio": self.default_allocation_ratio
                            }
                        updated_count += 1
                        
                        # 섹터 리스트 업데이트
                        new_sector = sector_info['sector']
                        if new_sector not in [s.get("code") for s in self.config.get("sector_list", [])]:
                            new_sector_item = {
                                "code": new_sector,
                                "allocation_ratio": 0.10  # 기본 할당 비율
                            }
                            self.config.get("sector_list", []).append(new_sector_item)
                        
                        # 연속 요청 방지를 위한 딜레이
                        time.sleep(0.5)
            
            if updated_count > 0:
                logger.info(f"{updated_count}개 종목의 섹터 정보를 업데이트했습니다.")
                
                # 마지막 업데이트 시간 기록 (설정 파일에는 저장하지 않음)
                self.config["last_sector_update"] = datetime.datetime.now().strftime("%Y%m%d")
            
        except Exception as e:
            logger.exception(f"섹터 정보 업데이트 중 오류: {str(e)}")

    def detect_market_environment(self) -> str:
        """현재 시장 환경 감지 - 개선된 로직"""
        # 코스피 또는 코스닥 지수 데이터 조회
        market_data = KisKR.GetOhlcvNew(self.market_index_code, 'D', 60, adj_ok=1)
        
        if market_data is None or market_data.empty:
            return "sideways"  # 기본값
        
        # 이동평균선 계산
        market_data['MA5'] = market_data['close'].rolling(window=5).mean()
        market_data['MA20'] = market_data['close'].rolling(window=20).mean()
        market_data['MA60'] = market_data['close'].rolling(window=60).mean()
        
        # RSI 계산 추가
        market_data['RSI'] = self.tech_indicators.calculate_rsi(market_data)
        
        # 추세 강도 계산 (ADX 대용)
        trend_strength = abs((market_data['MA20'].iloc[-1] / market_data['MA20'].iloc[-21] - 1) * 100)
        
        # 이동평균선 방향성
        ma5_slope = (market_data['MA5'].iloc[-1] / market_data['MA5'].iloc[-6] - 1) * 100
        ma20_slope = (market_data['MA20'].iloc[-1] / market_data['MA20'].iloc[-21] - 1) * 100
        
        # 볼륨 트렌드 (거래량 증가 여부)
        volume_trend = (market_data['volume'].iloc[-5:].mean() / market_data['volume'].iloc[-20:-5].mean()) > 1.0
        
        # 상승장 조건 (더 엄격하게 수정)
        if (ma5_slope > 1.0 and ma20_slope > 0.5 and  # 더 가파른 상승 요구
            market_data['MA5'].iloc[-1] > market_data['MA20'].iloc[-1] > market_data['MA60'].iloc[-1] and  # 정배열 확인
            market_data['close'].iloc[-1] > market_data['MA20'].iloc[-1] and  # 종가가 20일선 위
            market_data['RSI'].iloc[-1] > 50 and  # RSI가 50 이상 (강세)
            volume_trend):  # 거래량 증가 트렌드
            return "uptrend"
        
        # 하락장 조건 (기존 유지 + 추가 조건)
        elif (ma5_slope < -1.0 and ma20_slope < -0.5 and 
            market_data['MA5'].iloc[-1] < market_data['MA20'].iloc[-1] < market_data['MA60'].iloc[-1] and
            market_data['RSI'].iloc[-1] < 40):  # RSI가 40 미만 (약세)
            return "downtrend"
        
        # 그 외는 횡보장으로 판단
        else:
            return "sideways"

    def is_safe_to_buy_in_downtrend(self, daily_data: pd.DataFrame) -> bool:
        """하락장에서 안전한 매수 시점 확인
        
        Args:
            daily_data: 일봉 데이터
            
        Returns:
            bool: 안전한 매수 시점 여부
        """
        # 최근 과매도 강도 확인 - 보다 깊은 과매도에서만 매수
        rsi_value = daily_data['RSI'].iloc[-1]
        deep_oversold = rsi_value < 25.0  # 더 낮은 RSI 기준
        
        # 거래량 급증 확인 (반전 신호)
        avg_volume = daily_data['volume'].rolling(window=10).mean().iloc[-1]
        recent_volume = daily_data['volume'].iloc[-1]
        volume_surge = recent_volume > avg_volume * 2.0  # 평균의 2배 이상
        
        # 하락 속도 둔화 확인
        recent_drops = []
        try:
            recent_drops = [
                (daily_data['close'].iloc[i-1] - daily_data['close'].iloc[i]) / daily_data['close'].iloc[i-1] * 100
                for i in range(-5, 0)
            ]
            slowdown = all(recent_drops[i] < recent_drops[i-1] for i in range(1, len(recent_drops)))
        except:
            slowdown = False
        
        # 캔들 패턴 확인 (망치형, 역망치형 등 반전 패턴)
        bullish_reversal_pattern = self.detect_reversal_patterns(daily_data)
        
        return deep_oversold and (volume_surge or slowdown or bullish_reversal_pattern)
    
    def detect_reversal_patterns(self, daily_data: pd.DataFrame) -> bool:
        """반전 캔들 패턴 감지
        
        Args:
            daily_data: 일봉 데이터
            
        Returns:
            bool: 반전 패턴 존재 여부
        """
        try:
            # 최근 캔들 정보
            open_price = daily_data['open'].iloc[-1]
            close_price = daily_data['close'].iloc[-1]
            high_price = daily_data['high'].iloc[-1]
            low_price = daily_data['low'].iloc[-1]
            
            # 망치형 캔들 (Hammer) 확인
            if close_price > open_price:  # 양봉
                body_size = close_price - open_price
                lower_shadow = open_price - low_price
                hammer = lower_shadow > body_size * 2 and (high_price - close_price) < body_size * 0.5
            else:  # 음봉
                body_size = open_price - close_price
                lower_shadow = close_price - low_price
                hammer = lower_shadow > body_size * 2 and (high_price - open_price) < body_size * 0.5
            
            # 역망치형 캔들 (Inverted Hammer) 확인
            if close_price > open_price:  # 양봉
                body_size = close_price - open_price
                upper_shadow = high_price - close_price
                inv_hammer = upper_shadow > body_size * 2 and (open_price - low_price) < body_size * 0.5
            else:  # 음봉
                body_size = open_price - close_price
                upper_shadow = high_price - open_price
                inv_hammer = upper_shadow > body_size * 2 and (close_price - low_price) < body_size * 0.5
            
            # 도지 캔들 (Doji) 확인
            body_range = abs(close_price - open_price)
            total_range = high_price - low_price
            doji = body_range <= total_range * 0.1  # 몸통이 전체 범위의 10% 이하
            
            # 모닝스타 패턴 확인 (3일 패턴)
            if len(daily_data) >= 3:
                # 첫날: 큰 음봉
                day1_open = daily_data['open'].iloc[-3]
                day1_close = daily_data['close'].iloc[-3]
                day1_bearish = day1_close < day1_open and (day1_open - day1_close) > (daily_data['high'].iloc[-3] - daily_data['low'].iloc[-3]) * 0.6
                
                # 둘째날: 작은 몸통 (양봉/음봉 모두 가능)
                day2_open = daily_data['open'].iloc[-2]
                day2_close = daily_data['close'].iloc[-2]
                day2_small_body = abs(day2_close - day2_open) < abs(day1_close - day1_open) * 0.5
                
                # 셋째날: 큰 양봉
                day3_open = open_price
                day3_close = close_price
                day3_bullish = day3_close > day3_open and (day3_close - day3_open) > (high_price - low_price) * 0.6
                
                morning_star = day1_bearish and day2_small_body and day3_bullish
            else:
                morning_star = False
            
            return hammer or inv_hammer or doji or morning_star
            
        except Exception as e:
            logger.exception(f"반전 패턴 감지 중 오류: {str(e)}")
            return False

    def detect_uptrend(self, daily_data: pd.DataFrame) -> bool:
        """상승 추세 확인
        
        Args:
            daily_data: 일봉 데이터
            
        Returns:
            bool: 상승 추세 여부
        """
        try:
            # 이동평균선 정배열 확인 (단기>중기>장기)
            ma_uptrend = daily_data['MA5'].iloc[-1] > daily_data['MA20'].iloc[-1] > daily_data['MA60'].iloc[-1]
            
            # 상승 추세 확인 (최근 20일 중 15일 이상 상승)
            recent_data = daily_data.iloc[-20:]
            up_days = sum(1 for i in range(1, len(recent_data)) if recent_data['close'].iloc[i] > recent_data['close'].iloc[i-1])
            price_uptrend = up_days >= 15
            
            # 상승 모멘텀 확인
            momentum = daily_data['Momentum'].iloc[-1]
            momentum_uptrend = momentum > 5.0  # 최근 10일 대비 5% 이상 상승
            
            return ma_uptrend and (price_uptrend or momentum_uptrend)
        except Exception as e:
            logger.exception(f"상승 추세 확인 중 오류: {str(e)}")
            return False

    def analyze_stock(self, stock_code: str) -> Dict[str, any]:
        """종목 분석 - 상승장에서의 매수 시그널 강화"""
        try:
            # 일봉 데이터 조회 (60일)
            daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 60, adj_ok=1)
            
            if daily_data is None or daily_data.empty:
                logger.warning(f"종목 {stock_code} 일봉 데이터가 없습니다.")
                return {"is_buy_signal": False, "reason": "데이터 없음"}
            
            # 종목 기본 정보
            stock_info = KisKR.GetCurrentStatus(stock_code)
            current_price = KisKR.GetCurrentPrice(stock_code)
            
            if current_price is None or isinstance(current_price, str):
                logger.warning(f"종목 {stock_code} 현재가를 조회할 수 없습니다.")
                return {"is_buy_signal": False, "reason": "현재가 조회 실패"}
            
            # 기술적 지표 계산
            daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data)
            daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                daily_data, 
                fast_period=self.macd_fast_period, 
                slow_period=self.macd_slow_period, 
                signal_period=self.macd_signal_period
            )
            daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
                daily_data,
                period=self.bollinger_period,
                num_std=self.bollinger_std
            )
            daily_data[['K', 'D']] = self.tech_indicators.calculate_stochastic(daily_data)
            daily_data['Momentum'] = self.tech_indicators.calculate_momentum(daily_data)

            # ATR 계산 추가
            daily_data['ATR'] = self.tech_indicators.calculate_atr(daily_data)
            
            # 이동평균선 계산 (5, 20, 60일)
            daily_data['MA5'] = daily_data['close'].rolling(window=5).mean()
            daily_data['MA20'] = daily_data['close'].rolling(window=20).mean()
            daily_data['MA60'] = daily_data['close'].rolling(window=60).mean()
            
            # 분봉 데이터 조회 (30분봉)
            minute_data = KisKR.GetOhlcvMinute(stock_code, MinSt='30T')
            
            if minute_data is not None and not minute_data.empty:
                # 분봉 데이터 RSI 계산
                minute_data['RSI'] = self.tech_indicators.calculate_rsi(minute_data)
                
                # MACD 계산
                minute_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                    minute_data, 
                    fast_period=self.macd_fast_period, 
                    slow_period=self.macd_slow_period, 
                    signal_period=self.macd_signal_period
                )
                
                # 분봉 볼린저 밴드 계산
                minute_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
                    minute_data,
                    period=self.bollinger_period,
                    num_std=self.bollinger_std
                )
            
            # 분석 결과
            analysis_result = {
                "stock_code": stock_code,
                "stock_name": stock_info.get("StockName", ""),
                "current_price": current_price,
                "is_buy_signal": False,
                "signals": {
                    "daily": {},
                    "minute": {}
                },
                "technical_data": {
                    "rsi": daily_data['RSI'].iloc[-1] if not daily_data.empty else None,
                    "macd": daily_data['MACD'].iloc[-1] if not daily_data.empty else None,
                    "macd_signal": daily_data['Signal'].iloc[-1] if not daily_data.empty else None,
                    "ma5": daily_data['MA5'].iloc[-1] if not daily_data.empty else None,
                    "ma20": daily_data['MA20'].iloc[-1] if not daily_data.empty else None,
                    "ma60": daily_data['MA60'].iloc[-1] if not daily_data.empty else None,
                    # ATR 값 추가
                    "atr": daily_data['ATR'].iloc[-1] if not daily_data.empty else None
                }
            }

            # 여기에 동적 손절가 계산 코드 추가
            if not daily_data.empty:
                current_atr = daily_data['ATR'].iloc[-1]
                if not pd.isna(current_atr):
                    dynamic_stop_loss = self.tech_indicators.calculate_dynamic_stop_loss(
                        current_price, current_atr, self.atr_multiplier
                    )
                    analysis_result["technical_data"]["dynamic_stop_loss"] = dynamic_stop_loss

            # 시장 환경 감지
            market_env = self.detect_market_environment()
            analysis_result["market_environment"] = market_env
            
            # 시장 환경별 매수 전략 조정
            profit_target_adjusted = self.profit_target
            stop_loss_adjusted = self.stop_loss
            rsi_threshold_adjusted = self.rsi_oversold
            
            if market_env == "uptrend":
                # 상승장 전략 (수정된 부분)
                profit_target_adjusted = self.profit_target * 1.8  # 목표 수익률 80% 증가 (기존 50%에서 상향)
                stop_loss_adjusted = self.stop_loss * 0.8  # 손절폭 20% 감소
                rsi_threshold_adjusted = min(self.rsi_oversold + 8, 38)  # RSI 임계값 크게 완화 (기존 +5에서 +8로 상향)
                
                # 추세 확인으로 매수 신호 보강
                if not daily_data.empty:
                    # 상승장에서는 추가 매매 조건 확인
                    
                    # 1. 5일선이 20일선 위에 있는지 (골든크로스 또는 상승추세 중)
                    ma_aligned = False
                    if 'MA5' in daily_data.columns and 'MA20' in daily_data.columns:
                        ma_aligned = daily_data['MA5'].iloc[-1] > daily_data['MA20'].iloc[-1]
                        analysis_result["signals"]["daily"]["ma_aligned"] = ma_aligned
                    
                    # 2. 최근 3일간 종가 상승 추세인지
                    price_uptrend = False
                    if len(daily_data) >= 3:
                        price_uptrend = (daily_data['close'].iloc[-1] > daily_data['close'].iloc[-2] > 
                                        daily_data['close'].iloc[-3])
                        analysis_result["signals"]["daily"]["price_uptrend"] = price_uptrend
                    
                    # 3. 거래량 증가 추세인지
                    volume_trend = False
                    if 'volume' in daily_data.columns and len(daily_data) >= 10:
                        recent_vol = daily_data['volume'].iloc[-5:].mean()
                        prev_vol = daily_data['volume'].iloc[-10:-5].mean()
                        volume_trend = recent_vol > prev_vol * 1.1  # 10% 이상 증가
                        analysis_result["signals"]["daily"]["volume_trend"] = volume_trend
                    
                    # 상승장 특화 매수 점수 부여
                    uptrend_score = 0
                    if ma_aligned: uptrend_score += 2
                    if price_uptrend: uptrend_score += 1
                    if volume_trend: uptrend_score += 2
                    
                    # 상승장 특화 매수 점수 추가
                    analysis_result["uptrend_score"] = uptrend_score
                    
            elif market_env == "downtrend":
                # 하락장 전략 (매수 기준 강화, 손절폭 감소)
                profit_target_adjusted = self.profit_target * 0.8  # 목표 수익률 20% 감소
                stop_loss_adjusted = self.stop_loss * 0.6  # 손절폭 40% 감소 (더 타이트하게)
                rsi_threshold_adjusted = max(self.rsi_oversold - 5, 20)  # RSI 임계값 강화
                
                # 안전한 매수 시점인지 확인
                if not daily_data.empty:
                    is_safe_entry = self.is_safe_to_buy_in_downtrend(daily_data)
                    analysis_result["signals"]["daily"]["safe_entry"] = is_safe_entry
            
            # 조정된 파라미터 저장
            analysis_result["adjusted_parameters"] = {
                "profit_target": profit_target_adjusted,
                "stop_loss": stop_loss_adjusted,
                "rsi_threshold": rsi_threshold_adjusted
            }

            # 일봉 기반 매수 시그널 확인
            if not daily_data.empty:
                # 1. RSI 과매도 확인 (커스텀 임계값 사용)
                rsi_value = daily_data['RSI'].iloc[-1]
                is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value, rsi_threshold_adjusted)
                analysis_result["signals"]["daily"]["rsi_oversold"] = is_oversold
                
                # 2. 골든 크로스 확인 (5일선이 20일선을 상향돌파)
                is_golden_cross = self.tech_indicators.is_golden_cross(daily_data)
                analysis_result["signals"]["daily"]["golden_cross"] = is_golden_cross
                
                # 3. MACD 상향돌파 확인
                macd_cross_up = False
                try:
                    if daily_data['MACD'].iloc[-2] < daily_data['Signal'].iloc[-2] and \
                    daily_data['MACD'].iloc[-1] > daily_data['Signal'].iloc[-1]:
                        macd_cross_up = True
                except:
                    pass
                    
                analysis_result["signals"]["daily"]["macd_cross_up"] = macd_cross_up
                
                # 4. 볼린저 밴드 하단 접촉
                price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.01
                analysis_result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
                
                # 5. 모멘텀 상승 전환
                momentum_turning_up = False
                try:
                    if daily_data['Momentum'].iloc[-3] < daily_data['Momentum'].iloc[-2] < daily_data['Momentum'].iloc[-1]:
                        momentum_turning_up = True
                except:
                    pass
                    
                analysis_result["signals"]["daily"]["momentum_turning_up"] = momentum_turning_up
                
                # 6. 지지선/저항선 분석
                sr_levels = self.tech_indicators.detect_support_resistance(daily_data)
                near_support = current_price <= sr_levels["support"] * 1.03  # 지지선 근처
                analysis_result["signals"]["daily"]["near_support"] = near_support
                analysis_result["technical_data"]["support"] = sr_levels["support"]
                analysis_result["technical_data"]["resistance"] = sr_levels["resistance"]
                
                # 7. 거래량 증가 확인 추가
                volume_increase = False
                try:
                    # 최근 10일 평균 거래량 대비 현재 거래량 150% 이상
                    avg_volume = daily_data['volume'].rolling(window=10).mean().iloc[-1]
                    recent_volume = daily_data['volume'].iloc[-1]
                    volume_increase = recent_volume > avg_volume * 1.5
                    analysis_result["signals"]["daily"]["volume_increase"] = volume_increase
                except:
                    analysis_result["signals"]["daily"]["volume_increase"] = False
                
                # 8. 캔들 패턴 확인 추가
                bullish_candle = False
                try:
                    # 양봉 확인 (종가가 시가보다 높은 경우)
                    if daily_data['close'].iloc[-1] > daily_data['open'].iloc[-1]:
                        # 몸통 크기가 전체 봉의 50% 이상인 강한 양봉
                        body_size = abs(daily_data['close'].iloc[-1] - daily_data['open'].iloc[-1])
                        candle_range = daily_data['high'].iloc[-1] - daily_data['low'].iloc[-1]
                        
                        if body_size > candle_range * 0.5:
                            bullish_candle = True
                    
                    # 망치형 캔들 확인 (하단 꼬리가 몸통의 2배 이상)
                    if not bullish_candle:
                        if daily_data['close'].iloc[-1] > daily_data['open'].iloc[-1]:  # 양봉
                            body_size = daily_data['close'].iloc[-1] - daily_data['open'].iloc[-1]
                            lower_shadow = daily_data['open'].iloc[-1] - daily_data['low'].iloc[-1]
                            
                            if lower_shadow > body_size * 2 and body_size > 0:
                                bullish_candle = True
                        else:  # 음봉
                            body_size = daily_data['open'].iloc[-1] - daily_data['close'].iloc[-1]
                            lower_shadow = daily_data['close'].iloc[-1] - daily_data['low'].iloc[-1]
                            
                            if lower_shadow > body_size * 2 and body_size > 0:
                                bullish_candle = True
                    
                    analysis_result["signals"]["daily"]["bullish_candle"] = bullish_candle
                except:
                    analysis_result["signals"]["daily"]["bullish_candle"] = False
                
                # 9. 연속 하락 확인 추가
                consecutive_drop = False
                try:
                    # 최근 3일간 연속 하락 여부 확인
                    drops = [daily_data['close'].iloc[i] < daily_data['close'].iloc[i-1] for i in range(-3, 0)]
                    consecutive_drop = all(drops)
                    analysis_result["signals"]["daily"]["consecutive_drop"] = consecutive_drop
                except:
                    analysis_result["signals"]["daily"]["consecutive_drop"] = False
            
            # 분봉 기반 매수 시그널 확인
            if minute_data is not None and not minute_data.empty:
                # 1. 분봉 RSI 과매도 확인 (커스텀 임계값 사용)
                minute_rsi_value = minute_data['RSI'].iloc[-1]
                minute_is_oversold = self.tech_indicators.is_oversold_rsi(minute_rsi_value, rsi_threshold_adjusted)
                analysis_result["signals"]["minute"]["rsi_oversold"] = minute_is_oversold
                
                # 2. 분봉 MACD 상향돌파 확인
                minute_macd_cross_up = False
                try:
                    if minute_data['MACD'].iloc[-2] < minute_data['Signal'].iloc[-2] and \
                    minute_data['MACD'].iloc[-1] > minute_data['Signal'].iloc[-1]:
                        minute_macd_cross_up = True
                except:
                    pass
                    
                analysis_result["signals"]["minute"]["macd_cross_up"] = minute_macd_cross_up
                
                # 3. 분봉 볼린저 밴드 하단 접촉
                minute_near_lower_band = False
                try:
                    minute_near_lower_band = minute_data['close'].iloc[-1] <= minute_data['LowerBand'].iloc[-1] * 1.01
                    analysis_result["signals"]["minute"]["near_lower_band"] = minute_near_lower_band
                except:
                    analysis_result["signals"]["minute"]["near_lower_band"] = False
                
                # 4. 분봉 캔들 패턴 확인
                minute_bullish_candle = False
                try:
                    # 최근 3개 분봉에서 양봉이 2개 이상인지 확인
                    recent_candles = minute_data.iloc[-3:]
                    bullish_count = sum(1 for i in range(len(recent_candles)) if recent_candles['close'].iloc[i] > recent_candles['open'].iloc[i])
                    minute_bullish_candle = bullish_count >= 2
                    analysis_result["signals"]["minute"]["bullish_candle"] = minute_bullish_candle
                except:
                    analysis_result["signals"]["minute"]["bullish_candle"] = False
                
                # 5. 분봉 거래량 증가 확인
                minute_volume_increase = False
                try:
                    # 최근 10개 분봉 평균 대비 현재 거래량 증가
                    avg_volume = minute_data['volume'].rolling(window=10).mean().iloc[-1]
                    recent_volume = minute_data['volume'].iloc[-1]
                    minute_volume_increase = recent_volume > avg_volume * 1.5
                    analysis_result["signals"]["minute"]["volume_increase"] = minute_volume_increase
                except:
                    analysis_result["signals"]["minute"]["volume_increase"] = False

            # 일봉 시그널 강화: 일정 개수 이상의 조건 동시 충족 요구
            daily_signals_count = sum([
                is_oversold,              # RSI 과매도
                price_near_lower_band,    # 볼린저 밴드 하단
                near_support,             # 지지선 근처
                is_golden_cross,          # 골든 크로스
                macd_cross_up,            # MACD 상향돌파
                momentum_turning_up,      # 모멘텀 상승전환
                volume_increase,          # 거래량 증가
                bullish_candle,           # 강세 캔들 패턴
                consecutive_drop          # 연속 하락 후 반등 가능성
            ])
            
            # 상승장에서는 매수 조건 완화 - 핵심 변경 부분!
            if market_env == "uptrend":
                # 상승장에서는 RSI 과매도가 없어도 다른 조건이 충족되면 매수
                # 또한 필요 시그널 수를 2개에서 1개로 감소
                daily_buy_signal = daily_signals_count >= 1 or analysis_result.get("uptrend_score", 0) >= 3
                
                # 상승장 특화 매수 신호 추가
                if 'MA5' in daily_data.columns and 'MA20' in daily_data.columns and len(daily_data) > 1:
                    # 골든크로스 직후 매수 시그널 추가
                    if (daily_data['MA5'].iloc[-2] <= daily_data['MA20'].iloc[-2] and
                        daily_data['MA5'].iloc[-1] > daily_data['MA20'].iloc[-1]):
                        daily_buy_signal = True
                        analysis_result["signals"]["daily"]["fresh_golden_cross"] = True
            else:
                # 다른 환경에서는 기존 규칙 유지 (RSI 과매도 필수 + 최소 2개 시그널)
                daily_buy_signal = is_oversold and daily_signals_count >= 2
            
            # 분봉 시그널 강화
            minute_buy_signal = False
            if minute_data is not None and not minute_data.empty:
                minute_signals_count = sum([
                    minute_is_oversold,       # 분봉 RSI 과매도
                    minute_macd_cross_up,     # 분봉 MACD 상향돌파
                    minute_near_lower_band,   # 분봉 볼린저 밴드 하단
                    minute_bullish_candle,    # 분봉 강세 캔들
                    minute_volume_increase    # 분봉 거래량 증가
                ])
                # 분봉에서도 최소 2개 이상의 조건 충족 필요
                minute_buy_signal = minute_signals_count >= 2
                
                # 상승장에서는 분봉 매수 조건도 완화
                if market_env == "uptrend":
                    minute_buy_signal = minute_signals_count >= 1
            
            # 최종 매수 시그널 - 일봉과 분봉 모두 강화된 조건 충족해야 함
            buy_signal = daily_buy_signal
            
            # 분봉 데이터가 있는 경우에만 분봉 필터 적용
            if buy_signal and minute_data is not None and not minute_data.empty:
                buy_signal = buy_signal and minute_buy_signal
            
            # 하락장에서는 추가 안전 조건 확인
            if buy_signal and market_env == "downtrend":
                if not daily_data.empty and "safe_entry" in analysis_result["signals"]["daily"]:
                    if not analysis_result["signals"]["daily"]["safe_entry"]:
                        buy_signal = False
                        analysis_result["reason"] = "하락장 안전 매수 조건 미충족"
            
            # 기존 추세 필터 코드 유지
            if buy_signal and self.use_daily_trend_filter:
                # 일봉 추세 확인
                daily_trend_ok = TrendFilter.check_daily_trend(daily_data, self.daily_trend_lookback)
                if not daily_trend_ok:
                    buy_signal = False
                    analysis_result["reason"] = "일봉 추세 불량"
            
            if buy_signal and self.use_market_trend_filter:
                market_trend_ok = TrendFilter.check_market_trend(self.market_index_code, self.daily_trend_lookback)
                if not market_trend_ok:
                    buy_signal = False
                    analysis_result["reason"] = "시장 추세 불량"
            
            # 추가: 섹터 강도 필터 적용
            if buy_signal and hasattr(self, 'use_sector_filter') and self.use_sector_filter:
                sector_code = self.watch_list_info.get(stock_code, {}).get("sector_code")
                if sector_code:
                    sector_strength_ok = self.check_sector_strength(sector_code)
                    if not sector_strength_ok:
                        buy_signal = False
                        analysis_result["reason"] = "섹터 약세"
            
            # 최종 매수 시그널 설정
            analysis_result["is_buy_signal"] = buy_signal
            
            # 매수 이유 상세화
            if buy_signal:
                reasons = []
                if is_oversold: reasons.append("RSI 과매도")
                if price_near_lower_band: reasons.append("볼린저 밴드 하단")
                if near_support: reasons.append("지지선 근처")
                if is_golden_cross: reasons.append("골든 크로스")
                if macd_cross_up: reasons.append("MACD 상향돌파")
                if momentum_turning_up: reasons.append("모멘텀 상승전환")
                if volume_increase: reasons.append("거래량 증가")
                if bullish_candle: reasons.append("강세 캔들 패턴")
                if consecutive_drop: reasons.append("연속 하락 후 반등 기대")
                
                # 상승장에서의 추가 매수 이유
                if market_env == "uptrend":
                    if analysis_result["signals"]["daily"].get("fresh_golden_cross", False):
                        reasons.append("골든크로스 직후")
                    if analysis_result["signals"]["daily"].get("ma_aligned", False):
                        reasons.append("이동평균선 정배열")
                    if analysis_result["signals"]["daily"].get("price_uptrend", False):
                        reasons.append("가격 상승 추세")
                    if analysis_result["signals"]["daily"].get("volume_trend", False):
                        reasons.append("거래량 증가 추세")
                
                analysis_result["reason"] = "매수 시그널: " + ", ".join(reasons)
            
            # 최종 분석 결과의 일봉/분봉 시그널 점수 추가
            analysis_result["signal_scores"] = {
                "daily_score": daily_signals_count,
                "minute_score": minute_signals_count if minute_data is not None and not minute_data.empty else 0
            }
            
            # 시장 환경에 따른 조정된 매매 파라미터 추가
            if buy_signal:
                analysis_result["use_parameters"] = {
                    "profit_target": profit_target_adjusted,
                    "stop_loss": stop_loss_adjusted
                }
            
            return analysis_result

        except Exception as e:
            logger.exception(f"종목 {stock_code} 분석 중 오류: {str(e)}")
            return {"is_buy_signal": False, "reason": f"분석 오류: {str(e)}"}


    # 트레일링 스탑 로직을 포함한 check_sell_signals 메서드
    def check_sell_signals(self) -> None:
        """보유 종목 매도 시그널 확인 - 상승장에서 최적화"""
        try:
            # 현재 시장 환경 확인
            current_market_env = self.detect_market_environment()
            
            for stock_code, holding_info in list(self.holdings.items()):
                # 전략 관리 종목만 처리
                if not holding_info.get("is_strategy_managed", False):
                    continue
                    
                current_price = KisKR.GetCurrentPrice(stock_code)
                if current_price is None or isinstance(current_price, str):
                    logger.warning(f"종목 {stock_code} 현재가를 조회할 수 없습니다.")
                    continue
                
                avg_price = holding_info.get("avg_price", 0)
                if avg_price <= 0:
                    logger.warning(f"종목 {stock_code} 평균단가가 유효하지 않습니다.")
                    continue
                
                # 수익률 계산
                profit_percent = ((current_price / avg_price) - 1) * 100
                
                # 종목별 맞춤 파라미터 가져오기
                stock_strategy = self.adaptive_strategy.get_stock_strategy(stock_code, current_market_env)

                custom_profit_target = holding_info.get("profit_target", self.profit_target)
                custom_stop_loss = holding_info.get("stop_loss", self.stop_loss)
                stock_market_env = holding_info.get("market_environment", "sideways")
                
                # 상승장에서 매도 전략 최적화
                adjusted_trailing_stop_pct = self.trailing_stop_pct
                if current_market_env == "uptrend":
                    # 상승장에서는 트레일링 스탑 비율을 낮춰서 더 오래 보유하게 함
                    adjusted_trailing_stop_pct = self.trailing_stop_pct * 0.85  # 15% 감소
                
                # 트레일링 스탑 업데이트
                if self.use_trailing_stop:
                    # 현재가가 기존 최고가보다 높으면 최고가 및 트레일링 스탑 가격 업데이트
                    if current_price > holding_info.get("highest_price", 0):
                        new_stop_price = current_price * (1 - adjusted_trailing_stop_pct/100)
                        
                        # 홀딩 정보 업데이트
                        self.holdings[stock_code]["highest_price"] = current_price
                        self.holdings[stock_code]["trailing_stop_price"] = new_stop_price
                        
                        # 상승장에서는 로깅에 트레일링 스탑 조정 정보 추가
                        if current_market_env == "uptrend":
                            logger.info(f"상승장 트레일링 스탑 업데이트: {stock_code}, 최고가: {current_price:,}원, " +
                                    f"스탑 가격(조정됨): {new_stop_price:,}원 (원래 비율의 85%)")
                        else:
                            logger.info(f"트레일링 스탑 업데이트: {stock_code}, 최고가: {current_price:,}원, " +
                                    f"스탑 가격: {new_stop_price:,}원")
                
                # 기술적 지표 기반 매도 조건 확인
                daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 30, adj_ok=1)
                
                sell_signal = False
                sell_reason = ""
                
                # 부분 익절 확인 (설정 파일에서 가져온 값 사용)
                use_partial_profit = self.config.get("trading_strategies", {}).get("use_partial_profit", False)
                partial_profit_target = self.config.get("trading_strategies", {}).get("partial_profit_target", 3.0)
                partial_profit_ratio = self.config.get("trading_strategies", {}).get("partial_profit_ratio", 0.5)
                
                # 상승장에서는 부분 익절 전략 최적화
                if current_market_env == "uptrend":
                    # 상승장에서는 부분 익절 목표를 더 높게 설정
                    partial_profit_target *= 1.3  # 30% 증가
                    # 부분 익절 비율은 더 작게 설정 (더 오래 보유)
                    partial_profit_ratio *= 0.8  # 20% 감소
                
                # 부분 익절 상태 확인
                partial_profit_taken = holding_info.get("partial_profit_taken", False)
                
                # 부분 익절 실행 (아직 부분 익절 안했고, 설정 활성화되어 있고, 목표 수익률에 도달한 경우)
                if use_partial_profit and not partial_profit_taken and profit_percent >= partial_profit_target:
                    quantity = holding_info.get("quantity", 0)
                    partial_quantity = int(quantity * partial_profit_ratio)
                    
                    if partial_quantity > 0:
                        if current_market_env == "uptrend":
                            logger.info(f"상승장 부분 익절 실행: {stock_code}, 수익률: {profit_percent:.2f}%, 수량: {partial_quantity}주/{quantity}주 (조정된 비율: {partial_profit_ratio:.2f})")
                        else:
                            logger.info(f"부분 익절 실행: {stock_code}, 수익률: {profit_percent:.2f}%, 수량: {partial_quantity}주/{quantity}주")
                        
                        # 시장가 부분 매도
                        order_result = KisKR.MakeSellMarketOrder(
                            stockcode=stock_code,
                            amt=partial_quantity
                        )
                        
                        if not isinstance(order_result, str):
                            logger.info(f"부분 익절 성공: {stock_code}, {partial_quantity}주")
                            
                            # 남은 수량 업데이트
                            remaining_quantity = quantity - partial_quantity
                            self.holdings[stock_code]["quantity"] = remaining_quantity
                            self.holdings[stock_code]["partial_profit_taken"] = True
                            
                            # 트레일링 스탑 조건 강화 (부분 익절 후에는 남은 물량의 트레일링 스탑을 더 타이트하게 설정)
                            if self.use_trailing_stop:
                                # 상승장에서는 원래대로 설정 (이미 더 넓게 설정되어 있음)
                                if current_market_env == "uptrend":
                                    new_stop_price = current_price * (1 - adjusted_trailing_stop_pct/100)
                                else:
                                    # 상승장이 아닌 경우 기존 로직대로 타이트하게 설정
                                    tighter_trailing_pct = self.trailing_stop_pct * 0.8  # 20% 더 타이트하게
                                    new_stop_price = current_price * (1 - tighter_trailing_pct/100)
                                    
                                self.holdings[stock_code]["trailing_stop_price"] = new_stop_price
                                
                                if current_market_env == "uptrend":
                                    logger.info(f"상승장 부분 익절 후 트레일링 스탑 업데이트: {stock_code}, 가격: {new_stop_price:,}원 (상승장 조정 비율)")
                                else:
                                    logger.info(f"부분 익절 후 트레일링 스탑 업데이트: {stock_code}, 가격: {new_stop_price:,}원 (더 타이트하게)")
                            
                            self._save_holdings()
                        else:
                            logger.error(f"부분 익절 실패: {stock_code}, {order_result}")
                
                # 1. 목표 수익률 달성 (조정된 파라미터 사용)
                if profit_percent >= custom_profit_target:
                    sell_signal = True
                    sell_reason = f"목표 수익률 달성: {profit_percent:.2f}% (기준: {custom_profit_target:.2f}%)"
                
                # 2. 손절 조건 (조정된 파라미터 사용)
                elif profit_percent <= custom_stop_loss:
                    sell_signal = True
                    sell_reason = f"손절 조건 발동: {profit_percent:.2f}% (기준: {custom_stop_loss:.2f}%)"
                
                # 3. 트레일링 스탑 조건
                elif self.use_trailing_stop and current_price < holding_info.get("trailing_stop_price", 0):
                    # 트레일링 스탑 발동시 상승장 여부에 따라 메시지 조정
                    if current_market_env == "uptrend":
                        sell_signal = True
                        sell_reason = f"트레일링 스탑 발동: 최고가 {holding_info.get('highest_price'):,}원의 {adjusted_trailing_stop_pct}% 하락 (상승장 조정)"
                    else:
                        sell_signal = True
                        sell_reason = f"트레일링 스탑 발동: 최고가 {holding_info.get('highest_price'):,}원의 {self.trailing_stop_pct}% 하락"

                # 4. 동적 손절 적용
                use_dynamic_stop = holding_info.get("use_dynamic_stop", False)
                if use_dynamic_stop and holding_info.get("dynamic_stop_price", 0) > 0:
                    dynamic_stop_price = holding_info.get("dynamic_stop_price", 0)
                    
                    # 동적 손절 발동
                    if current_price <= dynamic_stop_price:
                        sell_signal = True
                        sell_reason = f"ATR 기반 동적 손절: {dynamic_stop_price:,}원"

                # 5. RSI 과매수 영역 (커스텀 임계값 사용)
                # 상승장에서는 RSI 과매수 조건 완화 (더 오래 보유)
                rsi_overbought_threshold = self.rsi_overbought
                if current_market_env == "uptrend":
                    rsi_overbought_threshold += 5  # 상승장에서는 RSI 과매수 기준 상향 (더 오래 보유)
                    
                if daily_data is not None and not daily_data.empty:
                    daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data)
                    rsi_value = daily_data['RSI'].iloc[-1]
                    
                    if self.tech_indicators.is_overbought_rsi(rsi_value, rsi_overbought_threshold):
                        sell_signal = True
                        if current_market_env == "uptrend":
                            sell_reason = f"RSI 과매수 영역(상승장 조정): {rsi_value:.2f} (기준: {rsi_overbought_threshold:.2f})"
                        else:
                            sell_reason = f"RSI 과매수 영역: {rsi_value:.2f}"
                    
                    # 6. 데드 크로스 (상승장에서는 데드 크로스 시그널 무시 가능)
                    if current_market_env != "uptrend":  # 상승장이 아닌 경우에만 적용
                        daily_data['MA5'] = daily_data['close'].rolling(window=5).mean()
                        daily_data['MA20'] = daily_data['close'].rolling(window=20).mean()
                        
                        if self.tech_indicators.is_death_cross(daily_data):
                            sell_signal = True
                            sell_reason = "5일선이 20일선을 하향돌파(데드 크로스)"
                    
                    # 7. MACD 하향 돌파 (상승장에서는 조건 완화)
                    if not sell_signal:
                        daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                            daily_data, 
                            fast_period=self.macd_fast_period, 
                            slow_period=self.macd_slow_period, 
                            signal_period=self.macd_signal_period
                        )
                        
                        try:
                            # MACD 하향 돌파 확인
                            macd_bearish_cross = (daily_data['MACD'].iloc[-2] > daily_data['Signal'].iloc[-2] and 
                                                daily_data['MACD'].iloc[-1] < daily_data['Signal'].iloc[-1])
                            
                            # 상승장에서는 MACD 하향 돌파만으로 매도하지 않고 추가 조건 확인
                            if current_market_env == "uptrend":
                                # 상승장에서는 MACD 하향 돌파 + 수익률이 특정 수준 이상인 경우에만 매도
                                if macd_bearish_cross and profit_percent > custom_profit_target * 0.7:  # 목표의 70% 이상 도달했을 때
                                    sell_signal = True
                                    sell_reason = f"MACD 하향돌파 + 충분한 수익 달성: {profit_percent:.2f}% (목표의 {(profit_percent/custom_profit_target*100):.0f}%)"
                            else:
                                # 상승장이 아닌 경우 기존 로직 유지
                                if macd_bearish_cross:
                                    sell_signal = True
                                    sell_reason = "MACD 하향돌파"
                        except:
                            pass
                    
                    # 8. 시장 환경 변화에 따른 추가 매도 조건
                    if stock_market_env == "uptrend" and current_market_env != "uptrend" and not sell_signal:
                        # 상승장에서 매수했는데 시장 환경이 변화한 경우, 수익 보존을 위한 추가 매도 조건
                        if profit_percent > 0:
                            if 'MA5' in daily_data.columns and 'MA20' in daily_data.columns:
                                # 이전에는 단기 > 장기, 현재는 단기 < 장기 (트렌드 반전)
                                if (daily_data['MA5'].iloc[-2] > daily_data['MA20'].iloc[-2] and 
                                    daily_data['MA5'].iloc[-1] < daily_data['MA20'].iloc[-1]):
                                    sell_signal = True
                                    sell_reason = f"시장 환경 변화 (상승장→{current_market_env}), 이익 실현: {profit_percent:.2f}%"
                    
                    elif stock_market_env == "sideways" and current_market_env == "downtrend" and not sell_signal:
                        # 횡보장에서 매수했는데 하락장으로 전환된 경우, 빠른 매도 고려
                        if profit_percent > custom_profit_target * 0.5:  # 목표의 50% 이상 도달 시
                            sell_signal = True
                            sell_reason = f"시장 환경 악화 (횡보장→하락장), 이익 보존: {profit_percent:.2f}%"
                
                # 매도 시그널이 있으면 매도 주문
                if sell_signal:
                    if current_market_env == "uptrend":
                        logger.info(f"상승장 매도 시그널 발생: {stock_code}, 이유: {sell_reason}")
                    else:
                        logger.info(f"매도 시그널 발생: {stock_code}, 이유: {sell_reason}")
                        
                    quantity = holding_info.get("quantity", 0)
                    
                    if quantity > 0:
                        # 시장가 매도
                        order_result = KisKR.MakeSellMarketOrder(
                            stockcode=stock_code,
                            amt=quantity
                        )
                        
                        if not isinstance(order_result, str):
                            logger.info(f"매도 주문 성공: {stock_code} {quantity}주")
                            # 보유 종목에서 제거
                            del self.holdings[stock_code]
                            self._save_holdings()
                        else:
                            logger.error(f"매도 주문 실패: {stock_code}, {order_result}")

                        # 거래 결과 기록 (적응형 전략 업데이트)
                        is_win = profit_percent > 0
                        self.adaptive_strategy.update_performance(stock_code, current_market_env, is_win)
               
        except Exception as e:
            logger.exception(f"매도 시그널 확인 중 오류: {str(e)}")

    def update_stock_characteristics(self, force_update=False):
        """종목 특성 주기적 업데이트"""
        try:
            # 메타데이터 확인
            metadata = self.adaptive_strategy.stock_performance.get("_metadata", {})
            last_analysis_date = metadata.get("last_analysis_date", "")
            
            # 마지막 분석일 파싱
            if last_analysis_date:
                try:
                    last_date = datetime.datetime.strptime(last_analysis_date, "%Y-%m-%d").date()
                    today = datetime.datetime.now().date()
                    days_since_last_analysis = (today - last_date).days
                except:
                    days_since_last_analysis = 999  # 파싱 오류시 업데이트 필요
            else:
                days_since_last_analysis = 999  # 데이터 없음
            
            # 30일마다 또는 강제 업데이트 시 특성 재분석
            if force_update or days_since_last_analysis >= 30:
                logger.info(f"종목 특성 업데이트 필요: 마지막 분석 후 {days_since_last_analysis}일 경과")
                self.initialize_adaptive_strategies()
                return True
            else:
                logger.info(f"종목 특성 업데이트 불필요: 마지막 분석 후 {days_since_last_analysis}일 경과 (30일 미만)")
                return False
            
        except Exception as e:
            logger.exception(f"종목 특성 업데이트 확인 중 오류: {str(e)}")
            return False

    def analyze_stock_characteristics(self):
        """종목 특성 자동 분석 및 분류"""
        try:
            logger.info("종목 특성 자동 분석 시작...")
            characteristics = {}
            
            # 모든 관심 종목에 대해 분석
            for stock_code in self.watch_list:
                # 과거 데이터 조회 (최소 120일, 충분한 데이터 확보)
                daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 120, adj_ok=1)
                
                if daily_data is None or daily_data.empty or len(daily_data) < 60:
                    logger.warning(f"종목 {stock_code} 데이터가 부족하여 특성 분석을 건너뜁니다.")
                    continue
                
                # 1. 변동성 계산 (ATR/가격 비율로 상대적 변동성 측정)
                daily_data['ATR'] = self.tech_indicators.calculate_atr(daily_data)
                avg_price = daily_data['close'].mean()
                relative_volatility = (daily_data['ATR'].mean() / avg_price) * 100
                
                # 2. 모멘텀 특성 (단기 상승 강도)
                daily_data['Returns'] = daily_data['close'].pct_change()
                momentum_score = daily_data['Returns'].rolling(window=20).mean().mean() * 100
                
                # 3. 거래량 변동성
                daily_data['VolumeChange'] = daily_data['volume'].pct_change().abs()
                volume_volatility = daily_data['VolumeChange'].mean() * 100
                
                # 4. 베타 계산 (시장과의 상관관계)
                market_data = KisKR.GetOhlcvNew(self.market_index_code, 'D', 120, adj_ok=1)
                if market_data is not None and not market_data.empty and len(market_data) >= 60:
                    # 날짜 인덱스 맞추기
                    market_data['Returns'] = market_data['close'].pct_change()
                    
                    # 공통 날짜만 선택해서 베타 계산
                    common_dates = set(daily_data.index).intersection(set(market_data.index))
                    if len(common_dates) >= 30:  # 최소 30일 데이터 필요
                        stock_returns = daily_data.loc[common_dates, 'Returns'].values
                        market_returns = market_data.loc[common_dates, 'Returns'].values
                        
                        # 베타 계산 (시장 대비 변동성)
                        beta = np.cov(stock_returns, market_returns)[0, 1] / np.var(market_returns)
                    else:
                        beta = 1.0  # 기본값
                else:
                    beta = 1.0  # 기본값
                    
                # 5. 이동평균선 기반 추세 강도
                daily_data['MA20'] = daily_data['close'].rolling(window=20).mean()
                daily_data['MA60'] = daily_data['close'].rolling(window=60).mean()
                
                # 주가가 20일선 위에 있는 비율
                above_ma20_ratio = (daily_data['close'] > daily_data['MA20']).mean() * 100
                
                # MA20이 MA60 위에 있는 비율
                above_ma60_ratio = (daily_data['MA20'] > daily_data['MA60']).mean() * 100
                
                # 6. PER/PBR 정보 (가능한 경우)
                # API 또는 웹 스크래핑으로 가져올 수 있으나 여기서는 생략
                
                # 특성 점수 계산
                growth_score = (
                    relative_volatility * 0.3 +  # 변동성이 높을수록 성장주 특성
                    momentum_score * 10 +        # 모멘텀이 높을수록 성장주 특성
                    volume_volatility * 0.2 +    # 거래량 변동이 클수록 성장주 특성
                    (beta - 1) * 20              # 베타가 높을수록 성장주 특성
                )
                
                value_score = (
                    (1 - relative_volatility/10) * 30 +  # 변동성이 낮을수록 가치주 특성
                    above_ma20_ratio * 0.3 +            # 추세를 유지할수록 가치주 특성
                    above_ma60_ratio * 0.3              # 장기 추세가 좋을수록 가치주 특성
                )
                
                # 특성 분류 (점수 기반)
                if growth_score > value_score * 1.2:  # 성장 점수가 20% 이상 높으면 성장주
                    char_type = "growth"
                elif value_score > growth_score * 1.2:  # 가치 점수가 20% 이상 높으면 가치주
                    char_type = "value"
                else:  # 그 외는 혼합형
                    char_type = "balanced"
                
                # 추가 세부 분류 (옵션)
                sub_type = None
                if relative_volatility > 5:  # 변동성이 매우 높음
                    sub_type = "high_volatility"
                elif beta > 1.5:  # 시장보다 변동성이 매우 큼
                    sub_type = "high_beta"
                elif beta < 0.7:  # 시장보다 변동성이 매우 작음
                    sub_type = "defensive"
                    
                # 결과 저장
                characteristics[stock_code] = {
                    "type": char_type,
                    "sub_type": sub_type,
                    "metrics": {
                        "relative_volatility": relative_volatility,
                        "momentum_score": momentum_score,
                        "volume_volatility": volume_volatility,
                        "beta": beta,
                        "above_ma20_ratio": above_ma20_ratio,
                        "above_ma60_ratio": above_ma60_ratio,
                        "growth_score": growth_score,
                        "value_score": value_score
                    }
                }
                
                logger.info(f"종목 {stock_code} 특성 분석: {char_type}" + 
                        (f" ({sub_type})" if sub_type else ""))
            
            return characteristics
            
        except Exception as e:
            logger.exception(f"종목 특성 분석 중 오류: {str(e)}")
            return {}            

    def initialize_adaptive_strategies(self):
        """종목 특성 기반 적응형 전략 초기화"""
        try:
            # 종목 특성 분석
            characteristics = self.analyze_stock_characteristics()
            
            # 특성별 전략 템플릿
            strategy_templates = {
                "growth": {
                    "uptrend": {
                        "profit_target_multiplier": 1.8,  # 높은 수익 목표
                        "stop_loss_multiplier": 0.7,      # 상대적으로 넓은 손절
                        "rsi_threshold_adjustment": 8,    # RSI 조건 크게 완화
                        "required_signals": 2,            # 적은 시그널 요구
                        "trailing_stop_multiplier": 0.85  # 트레일링 스탑 넓게
                    },
                    "downtrend": {
                        "profit_target_multiplier": 0.6,  # 낮은 수익 목표
                        "stop_loss_multiplier": 0.4,      # 매우 타이트한 손절
                        "rsi_threshold_adjustment": -5,   # RSI 매우 엄격하게
                        "required_signals": 4,            # 많은 시그널 요구
                        "trailing_stop_multiplier": 0.6   # 트레일링 스탑 매우 타이트하게
                    },
                    "sideways": {
                        "profit_target_multiplier": 1.2,  # 적당한 수익 목표
                        "stop_loss_multiplier": 0.8,      # 적당한 손절
                        "rsi_threshold_adjustment": 0,    # 기본 RSI 사용
                        "required_signals": 3,            # 보통 시그널 요구
                        "trailing_stop_multiplier": 0.9   # 트레일링 스탑 약간 타이트하게
                    }
                },
                "value": {
                    "uptrend": {
                        "profit_target_multiplier": 1.3,  # 적당한 수익 목표
                        "stop_loss_multiplier": 0.6,      # 타이트한 손절
                        "rsi_threshold_adjustment": 3,    # RSI 약간 완화
                        "required_signals": 3,            # 더 많은 시그널 요구
                        "trailing_stop_multiplier": 0.7   # 트레일링 스탑 타이트하게
                    },
                    "downtrend": {
                        "profit_target_multiplier": 0.8,  # 보통 수익 목표
                        "stop_loss_multiplier": 0.5,      # 타이트한 손절
                        "rsi_threshold_adjustment": -3,   # RSI 약간 엄격하게
                        "required_signals": 3,            # 보통 시그널 요구
                        "trailing_stop_multiplier": 0.7   # 트레일링 스탑 타이트하게
                    },
                    "sideways": {
                        "profit_target_multiplier": 1.0,  # 기본 수익 목표
                        "stop_loss_multiplier": 0.9,      # 기본 손절
                        "rsi_threshold_adjustment": 0,    # 기본 RSI 사용
                        "required_signals": 2,            # 기본 시그널 요구
                        "trailing_stop_multiplier": 1.0   # 기본 트레일링 스탑
                    }
                },
                "balanced": {
                    "uptrend": {
                        "profit_target_multiplier": 1.5,  # 적당히 높은 수익 목표
                        "stop_loss_multiplier": 0.7,      # 적당히 타이트한 손절
                        "rsi_threshold_adjustment": 5,    # RSI 중간 정도 완화
                        "required_signals": 2,            # 적당한 시그널 요구
                        "trailing_stop_multiplier": 0.8   # 트레일링 스탑 적당히 타이트하게
                    },
                    "downtrend": {
                        "profit_target_multiplier": 0.7,  # 적당히 낮은 수익 목표
                        "stop_loss_multiplier": 0.5,      # 적당히 타이트한 손절
                        "rsi_threshold_adjustment": -4,   # RSI 중간 정도 엄격하게
                        "required_signals": 3,            # 적당한 시그널 요구
                        "trailing_stop_multiplier": 0.7   # 트레일링 스탑 적당히 타이트하게
                    },
                    "sideways": {
                        "profit_target_multiplier": 1.1,  # 거의 기본 수익 목표
                        "stop_loss_multiplier": 0.9,      # 거의 기본 손절
                        "rsi_threshold_adjustment": 0,    # 기본 RSI 사용
                        "required_signals": 2,            # 기본 시그널 요구
                        "trailing_stop_multiplier": 0.95  # 거의 기본 트레일링 스탑
                    }
                }
            }
            
            # 서브타입 조정 템플릿
            subtype_adjustments = {
                "high_volatility": {
                    "profit_target_multiplier": 0.2,   # 더 높은 수익 목표
                    "stop_loss_multiplier": -0.1,      # 더 타이트한 손절
                    "trailing_stop_multiplier": -0.1   # 더 타이트한 트레일링 스탑
                },
                "high_beta": {
                    "profit_target_multiplier": 0.1,   # 약간 더 높은 수익 목표
                    "required_signals": 1              # 더 많은 시그널 요구
                },
                "defensive": {
                    "profit_target_multiplier": -0.1,  # 약간 더 낮은 수익 목표
                    "stop_loss_multiplier": 0.1,       # 약간 더 넓은 손절
                    "trailing_stop_multiplier": 0.1    # 약간 더 넓은 트레일링 스탑
                }
            }
            
            # 종목별 특성에 맞는 전략 초기화
            for stock_code, char_info in characteristics.items():
                char_type = char_info["type"]
                sub_type = char_info["sub_type"]
                
                # 기본 적응형 전략 구조 초기화
                if stock_code not in self.adaptive_strategy.stock_performance:
                    self.adaptive_strategy.stock_performance[stock_code] = {
                        "uptrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                        "downtrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                        "sideways": {"trades": 0, "wins": 0, "winrate": 0.0},
                        "adaptive_strategy": {
                            "uptrend": {"use_common": False},
                            "downtrend": {"use_common": False},
                            "sideways": {"use_common": False}
                        },
                        "characteristic": char_type
                    }
                else:
                    # 특성 업데이트
                    self.adaptive_strategy.stock_performance[stock_code]["characteristic"] = char_type
                
                # 특성별 템플릿 적용
                if char_type in strategy_templates:
                    for market_env in ["uptrend", "downtrend", "sideways"]:
                        # 기존 거래 횟수가 일정 수준 이상이면 전략 유지 (학습된 데이터 존중)
                        trades = self.adaptive_strategy.stock_performance[stock_code][market_env].get("trades", 0)
                        if trades >= 5:
                            continue
                        
                        # 템플릿 복사
                        strategy = strategy_templates[char_type][market_env].copy()
                        
                        # 서브타입 조정 적용
                        if sub_type in subtype_adjustments:
                            for key, adjustment in subtype_adjustments[sub_type].items():
                                if key in strategy:
                                    strategy[key] += adjustment
                        
                        # 전략 적용
                        self.adaptive_strategy.stock_performance[stock_code]["adaptive_strategy"][market_env] = strategy
                        self.adaptive_strategy.stock_performance[stock_code]["adaptive_strategy"][market_env]["use_common"] = False
            
            # 특성 메타데이터 저장
            self.adaptive_strategy.stock_performance["_metadata"] = {
                "last_analysis_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "analysis_count": self.adaptive_strategy.stock_performance.get("_metadata", {}).get("analysis_count", 0) + 1
            }
            
            # 저장
            self.adaptive_strategy.save_strategy()
            logger.info(f"종목 특성 기반 적응형 전략 초기화 완료: {len(characteristics)}개 종목")
            
            return True
            
        except Exception as e:
            logger.exception(f"적응형 전략 초기화 중 오류: {str(e)}")
            return False

    def generate_adaptive_strategy_report(self):
        """적응형 전략 상태 보고서 생성"""
        try:
            report = []
            report.append("# 한국주식 추세매매봇 적응형 전략 보고서")
            report.append(f"생성일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report.append("")
            
            # 전체 통계
            metadata = self.adaptive_strategy.stock_performance.get("_metadata", {})
            report.append(f"마지막 특성 분석일: {metadata.get('last_analysis_date', '없음')}")
            report.append(f"분석 횟수: {metadata.get('analysis_count', 0)}회")
            report.append("")
            
            # 종목별 특성 및 전략 상태
            report.append("## 종목별 특성 및 전략 상태")
            report.append("")
            report.append("| 종목코드 | 종목명 | 특성 | 상승장 승률 | 하락장 승률 | 횡보장 승률 | 전략 커스텀 상태 |")
            report.append("|---------|--------|------|------------|------------|------------|----------------|")
            
            for stock_code, data in self.adaptive_strategy.stock_performance.items():
                # 메타데이터는 건너뜀
                if stock_code == "_metadata":
                    continue
                    
                stock_name = self.watch_list_info.get(stock_code, {}).get("name", stock_code)
                char_type = data.get("characteristic", "알 수 없음")
                
                # 승률 계산
                uptrend_winrate = f"{data.get('uptrend', {}).get('winrate', 0):.1f}% ({data.get('uptrend', {}).get('trades', 0)}회)"
                downtrend_winrate = f"{data.get('downtrend', {}).get('winrate', 0):.1f}% ({data.get('downtrend', {}).get('trades', 0)}회)"
                sideways_winrate = f"{data.get('sideways', {}).get('winrate', 0):.1f}% ({data.get('sideways', {}).get('trades', 0)}회)"
                
                # 전략 커스텀 상태
                custom_status = []
                for env in ["uptrend", "downtrend", "sideways"]:
                    if not data.get("adaptive_strategy", {}).get(env, {}).get("use_common", True):
                        custom_status.append(env)
                
                if custom_status:
                    status_str = ", ".join(custom_status)
                else:
                    status_str = "기본 전략 사용"
                
                report.append(f"| {stock_code} | {stock_name} | {char_type} | {uptrend_winrate} | {downtrend_winrate} | {sideways_winrate} | {status_str} |")
            
            report.append("")
            
            # 세부 전략 정보
            report.append("## 세부 전략 파라미터 (커스텀 전략 사용 종목만)")
            report.append("")
            
            for stock_code, data in self.adaptive_strategy.stock_performance.items():
                # 메타데이터는 건너뜀
                if stock_code == "_metadata":
                    continue
                    
                # 커스텀 전략 사용 여부 확인
                uses_custom = False
                for env in ["uptrend", "downtrend", "sideways"]:
                    if not data.get("adaptive_strategy", {}).get(env, {}).get("use_common", True):
                        uses_custom = True
                        break
                
                if not uses_custom:
                    continue
                    
                stock_name = self.watch_list_info.get(stock_code, {}).get("name", stock_code)
                char_type = data.get("characteristic", "알 수 없음")
                
                report.append(f"### {stock_code} ({stock_name}) - {char_type}")
                report.append("")
                
                for env in ["uptrend", "downtrend", "sideways"]:
                    env_strat = data.get("adaptive_strategy", {}).get(env, {})
                    if not env_strat.get("use_common", True):
                        env_name = {"uptrend": "상승장", "downtrend": "하락장", "sideways": "횡보장"}[env]
                        report.append(f"#### {env_name} 전략")
                        report.append("")
                        report.append("| 파라미터 | 값 |")
                        report.append("|----------|---|")
                        
                        for param, value in env_strat.items():
                            if param == "use_common":
                                continue
                            param_name = {
                                "profit_target_multiplier": "목표 수익률 배수",
                                "stop_loss_multiplier": "손절률 배수",
                                "rsi_threshold_adjustment": "RSI 임계값 조정",
                                "required_signals": "필요 시그널 수",
                                "trailing_stop_multiplier": "트레일링 스탑 배수"
                            }.get(param, param)
                            
                            report.append(f"| {param_name} | {value} |")
                        
                        report.append("")
                
                report.append("---")
                report.append("")
            
            # 결합
            return "\n".join(report)
            
        except Exception as e:
            logger.exception(f"적응형 전략 보고서 생성 중 오류: {str(e)}")
            return f"보고서 생성 중 오류 발생: {str(e)}"

    def analyze_adaptive_backtest_results(self, backtest_results):
        """적응형 전략 백테스트 결과 분석"""
        try:
            analysis = {
                "overall_performance": {
                    "total_return": backtest_results["profit_loss_percent"],
                    "win_rate": backtest_results["win_rate"],
                    "total_trades": len([t for t in backtest_results["trades"] if t["action"] in ["SELL", "PARTIAL_SELL"]])
                },
                "market_env_performance": {},
                "stock_performance": {},
                "strategy_evolution": {}
            }
            
            # 시장 환경별 성과 분석
            for env, count in backtest_results["market_environment_stats"].items():
                env_trades = [t for t in backtest_results["trades"] 
                            if t["action"] in ["SELL", "PARTIAL_SELL"] and t["market_environment"] == env]
                
                win_trades = [t for t in env_trades if t.get("profit_loss", 0) > 0]
                
                analysis["market_env_performance"][env] = {
                    "trade_count": len(env_trades),
                    "win_rate": (len(win_trades) / len(env_trades) * 100) if env_trades else 0,
                    "avg_profit": sum(t.get("profit_loss", 0) for t in win_trades) / len(win_trades) if win_trades else 0,
                    "avg_loss": sum(t.get("profit_loss", 0) for t in env_trades if t.get("profit_loss", 0) <= 0) / 
                            len([t for t in env_trades if t.get("profit_loss", 0) <= 0]) 
                            if any(t.get("profit_loss", 0) <= 0 for t in env_trades) else 0
                }
            
            # 종목별 성과 분석
            stock_trades = {}
            for trade in backtest_results["trades"]:
                if trade["action"] in ["SELL", "PARTIAL_SELL"]:
                    stock_code = trade["stock_code"]
                    if stock_code not in stock_trades:
                        stock_trades[stock_code] = []
                    stock_trades[stock_code].append(trade)
            
            for stock_code, trades in stock_trades.items():
                win_trades = [t for t in trades if t.get("profit_loss", 0) > 0]
                
                analysis["stock_performance"][stock_code] = {
                    "trade_count": len(trades),
                    "win_rate": (len(win_trades) / len(trades) * 100) if trades else 0,
                    "avg_return": sum(t.get("profit_loss_percent", 0) for t in trades) / len(trades) if trades else 0,
                    "total_profit": sum(t.get("profit_loss", 0) for t in trades),
                    "market_env_breakdown": {
                        "uptrend": len([t for t in trades if t["market_environment"] == "uptrend"]),
                        "downtrend": len([t for t in trades if t["market_environment"] == "downtrend"]),
                        "sideways": len([t for t in trades if t["market_environment"] == "sideways"])
                    }
                }
            
            # 전략 진화 분석
            strategy_evolution = backtest_results.get("adaptive_strategy_performance", {}).get("strategy_evolution", {})
            for env, stocks in strategy_evolution.items():
                for stock_code, data in stocks.items():
                    if stock_code not in analysis["strategy_evolution"]:
                        analysis["strategy_evolution"][stock_code] = {}
                    analysis["strategy_evolution"][stock_code][env] = {
                        "initial_winrate": data["initial_winrate"],
                        "final_winrate": data["final_winrate"],
                        "improvement": data["final_winrate"] - data["initial_winrate"],
                        "trades": data["trades"]
                    }
            
            return analysis
        
        except Exception as e:
            logger.exception(f"적응형 전략 백테스트 결과 분석 중 오류: {str(e)}")
            return {}

    def visualize_adaptive_backtest(self, analysis_results, output_file=None):
        """적응형 전략 백테스트 결과 시각화"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from matplotlib.gridspec import GridSpec
            import pandas as pd
            import numpy as np
            
            # 플롯 설정
            plt.figure(figsize=(15, 12))
            gs = GridSpec(3, 2)
            
            # 1. 전체 성과 그래프
            ax1 = plt.subplot(gs[0, :])
            
            # 거래 날짜 및 누적 수익 추출
            trade_dates = []
            cumulative_returns = [0]  # 시작점
            
            for trade in self.backtest_results["trades"]:
                if trade["action"] in ["SELL", "PARTIAL_SELL"]:
                    trade_dates.append(pd.to_datetime(trade["date"]))
                    cumulative_returns.append(cumulative_returns[-1] + trade.get("profit_loss", 0))
            
            # 첫 날짜 추가 (시작일)
            trade_dates.insert(0, pd.to_datetime(self.backtest_results["trades"][0]["date"]))
            
            # 누적 수익 그래프
            ax1.plot(trade_dates, cumulative_returns, 'b-', linewidth=2)
            ax1.set_title('Cumulative Profit/Loss Over Time')
            ax1.set_ylabel('Profit/Loss (KRW)')
            ax1.grid(True)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            
            # 2. 시장 환경별 승률 비교
            ax2 = plt.subplot(gs[1, 0])
            
            env_names = list(analysis_results["market_env_performance"].keys())
            win_rates = [analysis_results["market_env_performance"][env]["win_rate"] for env in env_names]
            
            bars = ax2.bar(env_names, win_rates, color=['green', 'red', 'blue'])
            ax2.set_title('Win Rate by Market Environment')
            ax2.set_ylabel('Win Rate (%)')
            ax2.set_ylim(0, 100)
            
            # 바 위에 값 표시
            for bar, value in zip(bars, win_rates):
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, 
                        f'{value:.1f}%', ha='center', va='bottom')
            
            # 3. 종목별 승률
            ax3 = plt.subplot(gs[1, 1])
            
            stocks = list(analysis_results["stock_performance"].keys())
            stock_win_rates = [analysis_results["stock_performance"][s]["win_rate"] for s in stocks]
            
            # 승률 기준 정렬
            sorted_indices = np.argsort(stock_win_rates)
            sorted_stocks = [stocks[i] for i in sorted_indices]
            sorted_win_rates = [stock_win_rates[i] for i in sorted_indices]
            
            bars = ax3.barh(sorted_stocks, sorted_win_rates, color='orange')
            ax3.set_title('Win Rate by Stock')
            ax3.set_xlabel('Win Rate (%)')
            ax3.set_xlim(0, 100)
            
            # 바 위에 값 표시
            for bar, value in zip(bars, sorted_win_rates):
                ax3.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2, 
                        f'{value:.1f}%', va='center')
            
            # 4. 전략 진화 (승률 향상)
            ax4 = plt.subplot(gs[2, :])
            
            # 전략 진화 데이터 준비
            stocks_with_evolution = []
            improvements = []
            env_colors = []
            
            for stock_code, env_data in analysis_results["strategy_evolution"].items():
                for env, data in env_data.items():
                    if data["trades"] >= 5:  # 최소 5회 이상 거래가 있는 경우만
                        stocks_with_evolution.append(f"{stock_code} ({env})")
                        improvements.append(data["improvement"])
                        env_colors.append({'uptrend_winrate_improvement': 'green', 
                                        'downtrend_winrate_improvement': 'red', 
                                        'sideways_winrate_improvement': 'blue'}[env])
            
            # 개선도 기준 정렬
            sorted_indices = np.argsort(improvements)
            sorted_stocks_with_evolution = [stocks_with_evolution[i] for i in sorted_indices]
            sorted_improvements = [improvements[i] for i in sorted_indices]
            sorted_env_colors = [env_colors[i] for i in sorted_indices]
            
            bars = ax4.barh(sorted_stocks_with_evolution, sorted_improvements, color=sorted_env_colors)
            ax4.set_title('Strategy Evolution: Win Rate Improvement')
            ax4.set_xlabel('Win Rate Improvement (%)')
            ax4.axvline(x=0, color='k', linestyle='--')
            
            # 바 위에 값 표시
            for bar, value in zip(bars, sorted_improvements):
                ax4.text(bar.get_width() + (2 if value >= 0 else -10), 
                        bar.get_y() + bar.get_height()/2, 
                        f'{value:.1f}%', va='center', ha='left' if value >= 0 else 'right')
            
            plt.tight_layout()
            
            # 파일로 저장
            if output_file:
                plt.savefig(output_file, dpi=300, bbox_inches='tight')
                logger.info(f"백테스트 결과 시각화 저장 완료: {output_file}")
            
            plt.show()
            
        except Exception as e:
            logger.exception(f"적응형 전략 백테스트 결과 시각화 중 오류: {str(e)}")

    def apply_optimal_strategy_from_backtest(self, optimal_strategy_file="optimal_adaptive_strategy.json"):
        """백테스트에서 도출된 최적 전략을 적용"""
        try:
            # 최적 전략 파일 로드
            if not os.path.exists(optimal_strategy_file):
                logger.warning(f"최적 전략 파일 {optimal_strategy_file}이 존재하지 않습니다.")
                return False
            
            with open(optimal_strategy_file, 'r', encoding='utf-8') as f:
                optimal_strategy = json.load(f)
            
            # 적응형 전략 초기화
            if not hasattr(self, 'adaptive_strategy'):
                self.adaptive_strategy = AdaptiveMarketStrategy()
            
            # 종목별 특성 분석 (기존 함수 활용)
            characteristics = self.analyze_stock_characteristics()
            
            # 각 종목에 대해 최적 전략 적용
            for stock_code, char_info in characteristics.items():
                # 종목의 특성 정보
                char_type = char_info["type"]
                
                # 종목별 최적 전략이 있는지 확인
                if stock_code in optimal_strategy.get("stocks", {}):
                    # 종목별 맞춤 전략 적용
                    stock_strategy = optimal_strategy["stocks"][stock_code]
                    
                    # 적응형 전략 저장소에 종목 정보 초기화
                    if stock_code not in self.adaptive_strategy.stock_performance:
                        self.adaptive_strategy.stock_performance[stock_code] = {
                            "uptrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                            "downtrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                            "sideways": {"trades": 0, "wins": 0, "winrate": 0.0},
                            "adaptive_strategy": {
                                "uptrend": {"use_common": False},
                                "downtrend": {"use_common": False},
                                "sideways": {"use_common": False}
                            },
                            "characteristic": char_type
                        }
                    
                    # 각 시장 환경별 최적 전략 적용
                    for env in ["uptrend", "downtrend", "sideways"]:
                        if env in stock_strategy:
                            self.adaptive_strategy.stock_performance[stock_code]["adaptive_strategy"][env] = stock_strategy[env]
                else:
                    # 종목별 전략이 없으면 글로벌 전략 적용
                    if stock_code not in self.adaptive_strategy.stock_performance:
                        self.adaptive_strategy.stock_performance[stock_code] = {
                            "uptrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                            "downtrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                            "sideways": {"trades": 0, "wins": 0, "winrate": 0.0},
                            "adaptive_strategy": {
                                "uptrend": optimal_strategy["global"]["uptrend"],
                                "downtrend": optimal_strategy["global"]["downtrend"],
                                "sideways": optimal_strategy["global"]["sideways"]
                            },
                            "characteristic": char_type
                        }
                    else:
                        # 기존 데이터는 유지하고 전략만 업데이트
                        self.adaptive_strategy.stock_performance[stock_code]["adaptive_strategy"] = {
                            "uptrend": optimal_strategy["global"]["uptrend"],
                            "downtrend": optimal_strategy["global"]["downtrend"],
                            "sideways": optimal_strategy["global"]["sideways"]
                        }
                        self.adaptive_strategy.stock_performance[stock_code]["characteristic"] = char_type
            
            # 메타데이터 업데이트
            self.adaptive_strategy.stock_performance["_metadata"] = {
                "last_optimal_update": datetime.datetime.now().strftime("%Y-%m-%d"),
                "optimal_strategy_source": optimal_strategy_file
            }
            
            # 전략 저장
            self.adaptive_strategy.save_strategy()
            logger.info(f"백테스트 최적 전략 적용 완료")
            
            return True
            
        except Exception as e:
            logger.exception(f"최적 전략 적용 중 오류: {str(e)}")
            return False

    # 기존 run 메서드 수정
    def run(self) -> None:
        """매매봇 실행 - 상승장 대응 강화"""
        logger.info("한국주식 추세매매봇 시작")
        
        try:
            # 종목 특성 업데이트 확인
            today = datetime.datetime.now().date()
            last_run_date_str = self.config.get("last_run_date", "")
            
            if last_run_date_str:
                try:
                    last_run_date = datetime.datetime.strptime(last_run_date_str, "%Y-%m-%d").date()
                    if last_run_date < today:
                        # 날짜가 바뀌었으면 특성 업데이트 확인
                        self.update_stock_characteristics()
                except:
                    # 날짜 파싱 오류시 업데이트 실행
                    self.update_stock_characteristics()
            else:
                # 마지막 실행 날짜 없으면 업데이트
                self.update_stock_characteristics()
            
            # 마지막 실행 날짜 업데이트
            self.config["last_run_date"] = today.strftime("%Y-%m-%d")
            self._save_config()
            # 여기까지 추가 코드 끝 -------------------------------------
            # 계좌 잔고 조회
            account_balance = KisKR.GetBalance()
            
            if not account_balance or isinstance(account_balance, str):
                logger.error(f"계좌 잔고 조회 오류: {account_balance}")
                return
                    
            available_cash = account_balance.get("RemainMoney", 0)
            
            logger.info(f"계좌 잔고: {available_cash:,}원")
            logger.info(f"보유 종목: {len(self.holdings)}개")
            
            # 현재 시장 환경 감지
            market_env = self.detect_market_environment()
            logger.info(f"현재 시장 환경: {market_env}")

            # 상승장에서는 보유 종목 제한 조정
            max_stocks_adjusted = self.max_stocks
            # 기존: 상승장에서 max_stocks * 1.5
            # 수정: 모든 환경에서 일관된 보유 종목 수 유지
            if market_env == "uptrend":
                # 상승장에서도 기본 보유 종목 수 유지
                max_stocks_adjusted = self.max_stocks
                logger.info(f"상승장 감지: 기본 보유 종목 수 유지 ({max_stocks_adjusted}개)")
            elif market_env == "downtrend":
                # 하락장에서는 보유 종목 수를 줄임
                max_stocks_adjusted = max(1, int(self.max_stocks * 0.7))
                logger.info(f"하락장 감지: 보유 종목 수 감소 ({max_stocks_adjusted}개)")            
            
            # 현재 보유 종목 수 확인
            current_holdings_count = len(self.holdings)
            
            # 매수 가능한 종목 수 확인 (상승장에서는 늘어남)
            available_slots = max(0, max_stocks_adjusted - current_holdings_count)
            logger.info(f"추가 매수 가능 종목 수: {available_slots}개")
            
            # 1. 매도 시그널 확인 - 보유종목 먼저 확인
            self.check_sell_signals()
            
            # 매도 후 다시 보유 종목 수 확인
            current_holdings_count = len(self.holdings)
            available_slots = max(0, max_stocks_adjusted - current_holdings_count)
            
            # 계좌 잔고 갱신
            account_balance = KisKR.GetBalance()
            if not account_balance or isinstance(account_balance, str):
                logger.error(f"계좌 잔고 조회 오류: {account_balance}")
                available_cash = 0
            else:
                available_cash = account_balance.get("RemainMoney", 0)
            
            # 상승장에서는 관심종목 확대 - 임시 저장
            original_watch_list = self.watch_list.copy()
            if market_env == "uptrend":
                # 여기서는 예시로만 제공하며, 실제 구현 시 적절한 코드 필요
                # 예: 코스피200 또는 코스닥 상위 종목 데이터 활용
                # 이 부분은 실제 구현 시 get_top_momentum_stocks 같은 함수로 구현할 수 있음
                top_momentum_stocks = ["005930", "000660", "035420", "005380"] 
                for stock in top_momentum_stocks:
                    if stock not in self.watch_list:
                        self.watch_list.append(stock)
                
                logger.info(f"상승장 감지: 관심종목 확대 ({len(original_watch_list)} → {len(self.watch_list)})")
            
            # 2. 매수 시그널 확인 - 모든 관심종목 동시 분석 후 점수 기반 매수
            if available_slots > 0 and available_cash > self.min_trading_amount:
                # 관심종목 분석 및 매수 시그널 확인
                buy_candidates = []  # 매수 후보 종목 리스트
                
                for stock_code in self.watch_list:
                    # 이미 보유 중인 종목 스킵
                    if stock_code in self.holdings:
                        continue
                    
                    # 최근 확인 시간 체크 (설정된 주기에 한번만 확인)
                    last_check = self.last_check_time.get(stock_code, None)
                    now = datetime.datetime.now()
                    
                    # 설정에서 확인 주기 값 가져오기
                    if last_check and (now - last_check).seconds < self.check_interval_seconds:
                        continue
                    
                    # 종목 분석
                    analysis_result = self.analyze_stock(stock_code)
                    self.last_check_time[stock_code] = now
                    
                    if analysis_result.get("is_buy_signal", False):
                        # 매수 후보 목록에 추가
                        analysis_result["stock_code"] = stock_code
                        analysis_result["current_price"] = KisKR.GetCurrentPrice(stock_code)
                        buy_candidates.append(analysis_result)
                
                # 매수 후보가 있으면 점수 기반으로 정렬
                if buy_candidates:
                    # 후보 종목들에 점수 부여 및 정렬
                    score_weights = self.score_weights

                    for candidate in buy_candidates:
                        # 종목 코드와 현재 시장 환경에 맞는 전략 가져오기
                        stock_code = candidate.get("stock_code")
                        stock_strategy = self.adaptive_strategy.get_stock_strategy(stock_code, market_env)

                        score = 0
                        signals = candidate.get("signals", {})
                        
                        # 일봉 시그널 점수
                        daily_signals = signals.get("daily", {})
                        if daily_signals.get("rsi_oversold", False): 
                            score += score_weights.get("rsi_oversold", 2)
                        if daily_signals.get("golden_cross", False): 
                            score += score_weights.get("golden_cross", 2)
                        if daily_signals.get("macd_cross_up", False): 
                            score += score_weights.get("macd_cross_up", 2)
                        if daily_signals.get("near_lower_band", False): 
                            score += score_weights.get("near_lower_band", 1)
                        if daily_signals.get("momentum_turning_up", False): 
                            score += score_weights.get("momentum_turning_up", 1)
                        if daily_signals.get("near_support", False): 
                            score += score_weights.get("near_support", 2)
                        if daily_signals.get("volume_increase", False):
                            score += score_weights.get("volume_increase", 3)
                        if daily_signals.get("bullish_candle", False):
                            score += score_weights.get("bullish_candle", 2)
                        
                        # 상승장 특화 시그널 점수 추가
                        if market_env == "uptrend":
                            if daily_signals.get("fresh_golden_cross", False):
                                score += 4  # 골든크로스 직후에 높은 가중치
                            if daily_signals.get("ma_aligned", False):
                                score += 2  # 이동평균선 정배열
                            if daily_signals.get("price_uptrend", False):
                                score += 2  # 가격 상승 추세
                            if daily_signals.get("volume_trend", False):
                                score += 2  # 거래량 증가 추세
                        
                        # 분봉 시그널 점수
                        minute_signals = signals.get("minute", {})
                        if minute_signals.get("rsi_oversold", False): 
                            score += score_weights.get("minute_rsi_oversold", 1)
                        if minute_signals.get("macd_cross_up", False): 
                            score += score_weights.get("minute_macd_cross_up", 1)
                        
                        # 시장 환경 추가 점수 (상승장에서는 상승추세 종목에 가산점)
                        if market_env == "uptrend" and daily_signals.get("in_uptrend", False):
                            score += 2  # 상승장에서 상승추세 종목에 가산점
                        
                        # 섹터 강도 점수
                        stock_code = candidate.get("stock_code", "")
                        sector_code = self.watch_list_info.get(stock_code, {}).get("sector_code")
                        if sector_code and self.use_sector_filter:
                            sector_strength_ok = self.check_sector_strength(sector_code)
                            if sector_strength_ok:
                                score += score_weights.get("sector_strength", 3)

                        # 적응형 전략에 따른 점수 조정
                        required_signals = stock_strategy.get("required_signals", 2)
                        # 이미 분석 결과에서 계산된 daily_signals_count 가져오기
                        daily_signals_count = candidate.get("signal_scores", {}).get("daily_score", 0)

                        if daily_signals_count >= required_signals:
                            score += 2  # 필요 시그널 수 충족 시 보너스 점수

                        candidate["score"] = score
                        
                        # 로그에 점수 정보 추가
                        stock_name = candidate.get("stock_name", stock_code)
                        
                        # 상승장에서는 로그에 상승장 특화 정보 추가
                        if market_env == "uptrend":
                            uptrend_score = candidate.get("uptrend_score", 0)
                            logger.info(f"상승장 매수 후보: {stock_code} ({stock_name}), 점수: {score}, 상승장 점수: {uptrend_score}, "
                                    f"가격: {candidate.get('current_price', 0):,}원, "
                                    f"이유: {candidate.get('reason', '')}")
                        else:
                            logger.info(f"매수 후보: {stock_code} ({stock_name}), 점수: {score}, "
                                    f"가격: {candidate.get('current_price', 0):,}원, "
                                    f"이유: {candidate.get('reason', '')}")
                    
                    # 점수 기준 내림차순 정렬
                    buy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
                    
                    # 매수 가능한 종목 수만큼만 선택 (최대 available_slots개)
                    top_candidates = buy_candidates[:available_slots]
                    
                    # 상위 종목부터 매수 시도
                    logger.info(f"총 {len(buy_candidates)}개 매수 후보 중 상위 {len(top_candidates)}개 종목 매수 시도")
                    
                    for candidate in top_candidates:
                        stock_code = candidate.get("stock_code")
                        stock_name = candidate.get("stock_name", stock_code)
                        current_price = candidate.get("current_price", 0)
                        
                        # 상승장 여부에 따라 로그 메시지 조정
                        if market_env == "uptrend":
                            logger.info(f"상승장 매수 시도: {stock_code} ({stock_name}), 점수: {candidate.get('score', 0)}, 가격: {current_price:,}원")
                        else:
                            logger.info(f"매수 시도: {stock_code} ({stock_name}), 점수: {candidate.get('score', 0)}, 가격: {current_price:,}원")
                            
                        logger.info(f"매수 이유: {candidate.get('reason', '')}")
                        logger.info(f"시장 환경: {market_env}")
                        
                        # 조정된 파라미터 가져오기
                        adjusted_params = candidate.get("use_parameters", {})
                        custom_profit_target = adjusted_params.get("profit_target", self.profit_target)
                        custom_stop_loss = adjusted_params.get("stop_loss", self.stop_loss)
                        
                        # 상승장에서의 파라미터 로깅 개선
                        if market_env == "uptrend":
                            logger.info(f"상승장 조정 매매 파라미터 - 목표 수익률: {custom_profit_target:.2f}% (원래: {self.profit_target:.2f}%), "
                                    f"손절률: {custom_stop_loss:.2f}% (원래: {self.stop_loss:.2f}%)")
                        else:
                            logger.info(f"조정된 매매 파라미터 - 목표 수익률: {custom_profit_target:.2f}%, 손절률: {custom_stop_loss:.2f}%")
                        
                        # 종목별 예산 배분 계산
                        stock_info = self.watch_list_info.get(stock_code, {})
                        
                        # 상승장에서는 배분 비율 증가
                        if market_env == "uptrend":
                            allocation_ratio = stock_info.get("allocation_ratio", self.default_allocation_ratio)
                            allocation_ratio = min(allocation_ratio * 1.2, 0.3)  # 20% 증가, 최대 30%로 제한
                            logger.info(f"상승장 배분 비율 증가: {allocation_ratio:.2f} (원래: {stock_info.get('allocation_ratio', self.default_allocation_ratio):.2f})")
                        else:
                            allocation_ratio = stock_info.get("allocation_ratio", self.default_allocation_ratio)                    
                        
                        # 예산 내에서 매수 수량 결정
                        allocated_budget = min(self.total_budget * allocation_ratio, available_cash)
                        
                        # 분할 매수 전략 적용
                        use_split = self.use_split_purchase
                        initial_ratio = self.initial_purchase_ratio

                        # 상승장에서 분할 매수 비율 조정 (더 적극적으로)
                        if market_env == "uptrend":
                            # 상승장에서는 초기 매수 비율 증가 (더 적극적인 진입)
                            initial_ratio = min(initial_ratio * 1.3, 0.8)  # 30% 증가, 최대 80%까지
                            logger.info(f"상승장 초기 매수 비율 증가: {initial_ratio:.2f} (원래: {self.initial_purchase_ratio:.2f})")
                        
                        if use_split:
                            # 설정에서 초기 매수 비율 가져오기 (랜덤 변동 ±10%)
                            variation = 0.1  # 10% 변동
                            min_ratio = max(0.1, initial_ratio * (1 - variation))
                            max_ratio = min(0.9, initial_ratio * (1 + variation))
                            split_ratio = random.uniform(min_ratio, max_ratio)
                        else:
                            split_ratio = 1.0  # 분할 매수 사용하지 않을 경우 전체 예산 사용
                        
                        first_buy_budget = allocated_budget * split_ratio
                        
                        # 최소 거래 금액 확인
                        if first_buy_budget < self.min_trading_amount:
                            logger.info(f"종목 {stock_code} 매수 예산({first_buy_budget:,.0f}원)이 최소 거래 금액({self.min_trading_amount:,}원)보다 작습니다. 매수 건너뜀.")
                            continue
                        
                        quantity = max(1, int(first_buy_budget / current_price))
                        
                        if quantity > 0 and current_price > 0:
                            # 주문 가능한 수량으로 보정
                            try:
                                quantity = KisKR.AdjustPossibleAmt(stock_code, quantity, "MARKET")
                                logger.info(f"주문 가능 수량 보정: {quantity}주")
                            except Exception as e:
                                logger.warning(f"주문 가능 수량 보정 실패, 원래 수량으로 진행: {e}")
                            
                            # 매수 금액 재계산
                            buy_amount = current_price * quantity
                            
                            # 매수 금액이 최소 거래 금액보다 작으면 건너뜀
                            if buy_amount < self.min_trading_amount:
                                logger.info(f"종목 {stock_code} 매수 금액({buy_amount:,.0f}원)이 최소 거래 금액({self.min_trading_amount:,}원)보다 작습니다. 매수 건너뜀.")
                                continue
                            
                            # 시장가 매수
                            order_result = KisKR.MakeBuyMarketOrder(
                                stockcode=stock_code,
                                amt=quantity
                            )
                            
                            if not isinstance(order_result, str):
                                # 상승장 여부에 따라 로그 메시지 조정
                                if market_env == "uptrend":
                                    logger.info(f"상승장 매수 주문 성공: {stock_code} {quantity}주")
                                else:
                                    logger.info(f"매수 주문 성공: {stock_code} {quantity}주")
                                
                                # 매수 평균가는 시장가 주문이므로 GetMarketOrderPrice 함수로 가져옴
                                avg_price = KisKR.GetMarketOrderPrice(stock_code, order_result)
                                
                                # 보유 종목에 추가 (트레일링 스탑 설정 포함)
                                self.holdings[stock_code] = {
                                    "quantity": quantity,
                                    "avg_price": avg_price,
                                    "current_price": current_price,
                                    "buy_date": now.strftime("%Y%m%d"),
                                    "highest_price": current_price,
                                    "trailing_stop_price": 0,
                                    "split_buy": use_split,
                                    "initial_budget": allocated_budget,
                                    "used_budget": buy_amount,
                                    "remaining_budget": allocated_budget - buy_amount,
                                    # 동적 손절가 추가
                                    "use_dynamic_stop": self.use_dynamic_stop,
                                    "dynamic_stop_price": candidate.get("technical_data", {}).get("dynamic_stop_loss", 0),
                                    # 시장 환경 조정 파라미터
                                    "profit_target": custom_profit_target,
                                    "stop_loss": custom_stop_loss,
                                    "market_environment": market_env,
                                    # 전략 관리 종목 표시
                                    "is_strategy_managed": True
                                }
                                
                                # 트레일링 스탑 가격 설정
                                if self.use_trailing_stop:
                                    # 상승장에서는 트레일링 스탑 비율 조정 (더 오래 보유)
                                    if market_env == "uptrend":
                                        adjusted_trailing_stop_pct = self.trailing_stop_pct * 0.85  # 15% 감소
                                        self.holdings[stock_code]["trailing_stop_price"] = current_price * (1 - adjusted_trailing_stop_pct/100)
                                        logger.info(f"상승장 트레일링 스탑 설정: {self.holdings[stock_code]['trailing_stop_price']:,}원 (조정 비율: {adjusted_trailing_stop_pct:.2f}%)")
                                    else:
                                        self.holdings[stock_code]["trailing_stop_price"] = current_price * (1 - self.trailing_stop_pct/100)

                                self._save_holdings()
                                
                                # 사용 가능한 현금 업데이트
                                available_cash -= buy_amount
                                
                                # 추가 매수할 수 있는 슬롯이 없으면 루프 종료
                                available_slots -= 1
                                if available_slots <= 0:
                                    logger.info("최대 보유 종목 수에 도달하여 추가 매수를 중단합니다.")
                                    break
                                    
                                # 최소 거래 금액 이하로 남으면 루프 종료
                                if available_cash < self.min_trading_amount:
                                    logger.info(f"사용 가능한 현금({available_cash:,}원)이 최소 거래 금액({self.min_trading_amount:,}원) 이하로 매수를 중단합니다.")
                                    break
                            else:
                                logger.error(f"매수 주문 실패: {stock_code}, {order_result}")
                
                # 보유 종목 중 분할 매수가 가능한 종목 추가 매수 검토
                for stock_code, holding_info in list(self.holdings.items()):
                    # 전략 관리 종목만 처리
                    if not holding_info.get("is_strategy_managed", False):
                        continue
                        
                    # 분할 매수가 아니거나 남은 예산이 없으면 스킵
                    if not holding_info.get("split_buy", False) or holding_info.get("remaining_budget", 0) <= 0:
                        continue
                        
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price is None or isinstance(current_price, str):
                        continue
                        
                    avg_price = holding_info.get("avg_price", 0)
                    if avg_price <= 0:
                        continue
                        
                    # 현재 수익률 계산
                    profit_percent = ((current_price / avg_price) - 1) * 100
                    
                    # 추가 매수 조건: 수익률이 설정된 하락률 이상 하락했을 때
                    drop_thresholds = self.additional_purchase_drop_pct
                    
                    # 상승장에서는 하락률 기준 완화 (더 적극적인 추가 매수)
                    if market_env == "uptrend":
                        drop_pct = drop_thresholds[0] * 0.8 if drop_thresholds else 1.2  # 20% 더 작은 하락률에도 추가 매수
                    else:
                        drop_pct = drop_thresholds[0] if drop_thresholds else 1.5                
                    
                    if profit_percent <= -drop_pct:  # 설정된 하락률 이상 하락했을 때
                        remaining_budget = holding_info.get("remaining_budget", 0)
                        
                        # 최소 거래 금액 확인
                        if remaining_budget < self.min_trading_amount:
                            continue
                            
                        # 추가 매수 수량 계산
                        add_quantity = max(1, int(remaining_budget / current_price))
                        
                        if add_quantity > 0:
                            # 주문 가능한 수량으로 보정
                            try:
                                add_quantity = KisKR.AdjustPossibleAmt(stock_code, add_quantity, "MARKET")
                            except:
                                pass
                                
                            # 매수 금액 재계산
                            add_buy_amount = current_price * add_quantity
                            
                            # 최소 거래 금액 확인
                            if add_buy_amount < self.min_trading_amount:
                                continue
                                
                            # 시장가 추가 매수
                            if market_env == "uptrend":
                                logger.info(f"상승장 분할 매수 - 추가 매수 시도: {stock_code}, {add_quantity}주, "
                                        f"현재가: {current_price}원, 평단가: {avg_price}원, 수익률: {profit_percent:.2f}%, "
                                        f"하락 기준: {drop_pct:.2f}% (조정됨)")
                            else:
                                logger.info(f"분할 매수 - 추가 매수 시도: {stock_code}, {add_quantity}주, "
                                        f"현재가: {current_price}원, 평단가: {avg_price}원, 수익률: {profit_percent:.2f}%")
                            
                            order_result = KisKR.MakeBuyMarketOrder(
                                stockcode=stock_code,
                                amt=add_quantity
                            )
                            
                            if not isinstance(order_result, str):
                                if market_env == "uptrend":
                                    logger.info(f"상승장 추가 매수 주문 성공: {stock_code} {add_quantity}주")
                                else:
                                    logger.info(f"추가 매수 주문 성공: {stock_code} {add_quantity}주")
                                
                                # 기존 수량
                                existing_quantity = holding_info.get("quantity", 0)
                                existing_amount = existing_quantity * avg_price
                                
                                # 새로운 평균단가 계산
                                new_quantity = existing_quantity + add_quantity
                                new_avg_price = (existing_amount + add_buy_amount) / new_quantity
                                
                                # 홀딩 정보 업데이트
                                self.holdings[stock_code]["quantity"] = new_quantity
                                self.holdings[stock_code]["avg_price"] = new_avg_price
                                self.holdings[stock_code]["used_budget"] = holding_info.get("used_budget", 0) + add_buy_amount
                                self.holdings[stock_code]["remaining_budget"] = holding_info.get("remaining_budget", 0) - add_buy_amount
                                
                                # 분할 매수 모두 사용했으면 플래그 해제
                                if self.holdings[stock_code]["remaining_budget"] < self.min_trading_amount:
                                    self.holdings[stock_code]["split_buy"] = False
                                    
                                self._save_holdings()
                            else:
                                logger.error(f"추가 매수 주문 실패: {stock_code}, {order_result}")
            
            # 관심종목 원복 (임시로 추가된 종목 제거)
            if market_env == "uptrend" and len(self.watch_list) > len(original_watch_list):
                self.watch_list = original_watch_list.copy()
                logger.info(f"관심종목 원복: {len(self.watch_list)}개")
                
            logger.info("매매봇 실행 완료")
        
        except Exception as e:
            logger.exception(f"매매봇 실행 중 오류: {str(e)}")

    def run_backtest(self, start_date: str, end_date: str = None) -> Dict[str, any]:
        """백테스트 실행 - 상승장 전략 강화 반영
        
        Args:
            start_date: 시작일자 (YYYYMMDD)
            end_date: 종료일자 (YYYYMMDD), 없으면 현재 날짜
            
        Returns:
            Dict: 백테스트 결과
        """
        logger.info(f"백테스트 시작: {start_date} ~ {end_date or '현재'}")
        
        if not end_date:
            end_date = datetime.datetime.now().strftime("%Y%m%d")
        
        backtest_results = {
            "initial_capital": self.total_budget,
            "final_capital": self.total_budget,
            "profit_loss": 0,
            "profit_loss_percent": 0,
            "trades": [],
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "max_drawdown": 0,
            "market_environment_stats": {
                "uptrend": 0,  # 상승장 거래 횟수
                "downtrend": 0,  # 하락장 거래 횟수
                "sideways": 0   # 횡보장 거래 횟수
            }
        }
        
        total_capital = self.total_budget
        virtual_holdings = {}
        trades = []
        
        try:
            # 전체 백테스트 기간에 대한 시장 환경 미리 분석 
            market_env_history = {}
            try:
                # 시장 지수 데이터 가져오기
                market_data = KisKR.GetOhlcvNew(self.market_index_code, 'D', 200, adj_ok=1)
                if market_data is not None and not market_data.empty:
                    # 인덱스를 항상 datetime 형식으로 변환
                    if not isinstance(market_data.index, pd.DatetimeIndex):
                        market_data.index = pd.to_datetime(market_data.index)
                    
                    # 이동평균선 계산
                    market_data['MA5'] = market_data['close'].rolling(window=5).mean()
                    market_data['MA20'] = market_data['close'].rolling(window=20).mean()
                    market_data['MA60'] = market_data['close'].rolling(window=60).mean()
                    
                    # 각 날짜별 시장 환경 미리 계산 - 상승장 감지 로직을 수정된 버전으로 변경
                    for i in range(60, len(market_data)):  # 60일 이동평균선 계산을 위해 60일 이후부터 시작
                        date = market_data.index[i]
                        
                        # 이동평균선 방향성
                        ma5_slope = (market_data['MA5'].iloc[i] / market_data['MA5'].iloc[i-5] - 1) * 100
                        ma20_slope = (market_data['MA20'].iloc[i] / market_data['MA20'].iloc[i-20] - 1) * 100
                        
                        # 수정된 상승장 조건 (완화된 기준 적용)
                        if (ma5_slope > 0.5 and  # 0.5%만 상승해도 인정 (기존 1.0%)
                            (ma20_slope > 0.3 or market_data['MA5'].iloc[i] > market_data['MA20'].iloc[i]) and  # 중기 상승 또는 골든크로스
                            market_data['close'].iloc[i] > market_data['MA20'].iloc[i]):  # 종가가 20일선 위
                            market_env_history[date] = "uptrend"
                        
                        # 하락장 조건 (기존 유지)
                        elif (ma5_slope < -1.0 and ma20_slope < -0.5 and 
                            market_data['MA5'].iloc[i] < market_data['MA20'].iloc[i] < market_data['MA60'].iloc[i]):
                            market_env_history[date] = "downtrend"
                        
                        # 그 외는 횡보장으로 판단 (기존 유지)
                        else:
                            market_env_history[date] = "sideways"
                    
                    logger.info(f"시장 환경 분석 완료: 총 {len(market_env_history)}일")
                
            except Exception as e:
                logger.exception(f"시장 환경 분석 중 오류: {str(e)}")
                # 오류 발생 시 기본값으로 모든 날짜를 횡보장으로 설정
                market_env_history = {}
            
            # 필터링을 위한 시작일과 종료일 변환
            try:
                # YYYYMMDD 형식 변환
                if isinstance(start_date, str) and len(start_date) == 8:
                    start_date_dt = pd.to_datetime(start_date, format='%Y%m%d')
                else:
                    start_date_dt = pd.to_datetime(start_date)
                    
                if isinstance(end_date, str) and len(end_date) == 8:
                    end_date_dt = pd.to_datetime(end_date, format='%Y%m%d')
                else:
                    end_date_dt = pd.to_datetime(end_date)
            except:
                logger.warning(f"날짜 변환 실패, 문자열 형식으로 계속 진행합니다.")
                start_date_dt = start_date
                end_date_dt = end_date
            
            # 종목별 데이터 미리 로드 (캐싱)
            stock_data_cache = {}
            for stock_code in self.watch_list:
                try:
                    # 일봉 데이터 조회
                    daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 200, adj_ok=1)
                    
                    if daily_data is None or daily_data.empty:
                        logger.warning(f"백테스트: 종목 {stock_code} 일봉 데이터가 없습니다.")
                        continue

                    # 인덱스를 항상 datetime 형식으로 변환
                    if not isinstance(daily_data.index, pd.DatetimeIndex):
                        daily_data.index = pd.to_datetime(daily_data.index)
                    
                    # 필터링 수행
                    mask = (daily_data.index >= start_date_dt) & (daily_data.index <= end_date_dt)
                    filtered_data = daily_data[mask].copy()
                    
                    # 필터링 결과가 비어있는 경우 스킵
                    if filtered_data.empty:
                        logger.warning(f"백테스트: 종목 {stock_code} 지정된 기간({start_date_dt} ~ {end_date_dt}) 내 데이터가 없습니다.")
                        continue
                    
                    # 기술적 지표 계산
                    filtered_data['RSI'] = self.tech_indicators.calculate_rsi(filtered_data)
                    filtered_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                        filtered_data,
                        fast_period=self.macd_fast_period,
                        slow_period=self.macd_slow_period,
                        signal_period=self.macd_signal_period
                    )
                    filtered_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
                        filtered_data,
                        period=self.bollinger_period,
                        num_std=self.bollinger_std
                    )
                    filtered_data['MA5'] = filtered_data['close'].rolling(window=5).mean()
                    filtered_data['MA20'] = filtered_data['close'].rolling(window=20).mean()
                    filtered_data['MA60'] = filtered_data['close'].rolling(window=60).mean()
                    filtered_data['ATR'] = TechnicalIndicators.calculate_atr(filtered_data)
                    
                    # 캐시에 저장
                    stock_data_cache[stock_code] = filtered_data
                    logger.info(f"종목 {stock_code} 데이터 로드 완료: {len(filtered_data)}일")
                    
                except Exception as e:
                    logger.exception(f"종목 {stock_code} 데이터 로드 중 오류: {str(e)}")
            
            # 고유한 날짜 목록 생성 (모든 종목의 거래일 통합)
            all_dates = set()
            for stock_code, data in stock_data_cache.items():
                all_dates.update(data.index)
            
            all_dates = sorted(list(all_dates))
            logger.info(f"백테스트 총 거래일: {len(all_dates)}일")
            
            # 날짜별 시뮬레이션
            for date in all_dates:
                logger.debug(f"날짜 {date} 분석 시작")
                
                # 현재 날짜의 시장 환경 확인
                current_market_env = market_env_history.get(date, "sideways")  # 기본값은 횡보장
                
                # 상승장에서는 최대 보유 종목 수 증가
                max_holdings_count = self.max_stocks
                if current_market_env == "uptrend":
                    max_holdings_count = int(self.max_stocks * 1.5)  # 상승장에서는 1.5배로 증가
                
                # 1. 보유 중인 종목 매도 확인 (매도 시그널)
                for stock_code, holding_info in list(virtual_holdings.items()):
                    # 해당 종목의 현재 데이터가 있는지 확인
                    if stock_code not in stock_data_cache or date not in stock_data_cache[stock_code].index:
                        continue
                    
                    daily_data = stock_data_cache[stock_code]
                    current_idx = daily_data.index.get_loc(date)
                    current_price = daily_data.iloc[current_idx]['close']
                    
                    avg_price = holding_info["avg_price"]
                    profit_percent = ((current_price / avg_price) - 1) * 100
                    
                    # 종목별 맞춤 파라미터 가져오기
                    custom_profit_target = holding_info.get("profit_target", self.profit_target)
                    custom_stop_loss = holding_info.get("stop_loss", self.stop_loss)
                    market_env = holding_info.get("market_environment", "sideways")
                    
                    # 트레일링 스탑 업데이트
                    if self.use_trailing_stop:
                        # 상승장에서는 트레일링 스탑 비율 조정
                        trailing_stop_pct = self.trailing_stop_pct
                        if current_market_env == "uptrend":
                            trailing_stop_pct *= 0.85  # 15% 감소
                        
                        if current_price > holding_info.get("highest_price", 0):
                            new_stop_price = current_price * (1 - trailing_stop_pct/100)
                            virtual_holdings[stock_code]["highest_price"] = current_price
                            virtual_holdings[stock_code]["trailing_stop_price"] = new_stop_price
                    
                    # 부분 익절 확인
                    use_partial_profit = self.config.get("trading_strategies", {}).get("use_partial_profit", False)
                    partial_profit_target = self.config.get("trading_strategies", {}).get("partial_profit_target", 3.0)
                    partial_profit_ratio = self.config.get("trading_strategies", {}).get("partial_profit_ratio", 0.5)
                    
                    # 상승장에서는 부분 익절 전략 최적화
                    if current_market_env == "uptrend":
                        # 상승장에서는 부분 익절 목표를 더 높게 설정
                        partial_profit_target *= 1.3  # 30% 증가
                        # 부분 익절 비율은 더 작게 설정 (더 오래 보유)
                        partial_profit_ratio *= 0.8  # 20% 감소
                    
                    partial_profit_taken = holding_info.get("partial_profit_taken", False)
                    
                    # 부분 익절 실행
                    if use_partial_profit and not partial_profit_taken and profit_percent >= partial_profit_target:
                        quantity = holding_info.get("quantity", 0)
                        partial_quantity = int(quantity * partial_profit_ratio)
                        
                        if partial_quantity > 0:
                            # 부분 매도
                            remaining_quantity = quantity - partial_quantity
                            
                            # 부분 익절 금액
                            partial_sell_amount = current_price * partial_quantity
                            partial_profit = partial_sell_amount - (avg_price * partial_quantity)
                            
                            # 자본 업데이트
                            total_capital += partial_sell_amount
                            
                            # 거래 기록
                            trades.append({
                                "stock_code": stock_code,
                                "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                "action": "PARTIAL_SELL",
                                "reason": f"부분 익절: {profit_percent:.2f}%",
                                "date": date,
                                "price": current_price,
                                "quantity": partial_quantity,
                                "profit_loss": partial_profit,
                                "profit_loss_percent": profit_percent,
                                "market_environment": current_market_env
                            })
                            
                            # 홀딩 정보 업데이트
                            virtual_holdings[stock_code]["quantity"] = remaining_quantity
                            virtual_holdings[stock_code]["partial_profit_taken"] = True
                            
                            # 트레일링 스탑 강화
                            if self.use_trailing_stop:
                                if current_market_env == "uptrend":
                                    # 상승장에서는 기존 조정된 비율 유지
                                    new_stop_price = current_price * (1 - trailing_stop_pct/100)
                                else:
                                    # 상승장이 아닌 경우 더 타이트하게 설정
                                    tighter_trailing_pct = self.trailing_stop_pct * 0.8  # 20% 더 타이트하게
                                    new_stop_price = current_price * (1 - tighter_trailing_pct/100)
                                    
                                virtual_holdings[stock_code]["trailing_stop_price"] = new_stop_price
                            
                            # 시장 환경 통계 업데이트
                            backtest_results["market_environment_stats"][current_market_env] += 1
                            
                            # 남은 수량이 0이면 홀딩에서 제거
                            if remaining_quantity <= 0:
                                del virtual_holdings[stock_code]
                            
                            continue  # 부분 익절 후 다음 종목 확인
                    
                    # 매도 시그널 확인
                    sell_signal = False
                    sell_reason = ""
                    
                    # 1. 목표 수익률 달성
                    if profit_percent >= custom_profit_target:
                        sell_signal = True
                        sell_reason = f"목표 수익률 달성: {profit_percent:.2f}% (기준: {custom_profit_target:.2f}%)"
                    
                    # 2. 손절 조건
                    elif profit_percent <= custom_stop_loss:
                        sell_signal = True
                        sell_reason = f"손절: {profit_percent:.2f}% (기준: {custom_stop_loss:.2f}%)"
                    
                    # 3. 트레일링 스탑 조건
                    elif self.use_trailing_stop and current_price < holding_info.get("trailing_stop_price", 0):
                        sell_signal = True
                        if current_market_env == "uptrend":
                            sell_reason = f"트레일링 스탑 발동(상승장 조정): 최고가 {holding_info.get('highest_price'):,}원의 {trailing_stop_pct}% 하락"
                        else:
                            sell_reason = f"트레일링 스탑 발동: 최고가 {holding_info.get('highest_price'):,}원의 {self.trailing_stop_pct}% 하락"
                    
                    # 4. 동적 손절 조건
                    elif holding_info.get("use_dynamic_stop", False) and holding_info.get("dynamic_stop_price", 0) > 0:
                        dynamic_stop_price = holding_info.get("dynamic_stop_price", 0)
                        
                        if current_price <= dynamic_stop_price:
                            sell_signal = True
                            sell_reason = f"ATR 기반 동적 손절: {dynamic_stop_price:,}원"
                    
                    # 5. RSI 과매수 영역
                    elif current_idx > 0:
                        # 상승장에서는 RSI 과매수 기준 완화
                        rsi_overbought_threshold = self.rsi_overbought
                        if current_market_env == "uptrend":
                            rsi_overbought_threshold += 5  # 상승장에서는 RSI 과매수 기준 상향
                            
                        if self.tech_indicators.is_overbought_rsi(daily_data.iloc[current_idx]['RSI'], rsi_overbought_threshold):
                            sell_signal = True
                            if current_market_env == "uptrend":
                                sell_reason = f"RSI 과매수(상승장 조정): {daily_data.iloc[current_idx]['RSI']:.2f}"
                            else:
                                sell_reason = f"RSI 과매수: {daily_data.iloc[current_idx]['RSI']:.2f}"
                    
                    # 6. 데드 크로스 (상승장에서는 조건 무시)
                    elif current_idx > 0 and current_market_env != "uptrend" and daily_data.iloc[current_idx-1]['MA5'] > daily_data.iloc[current_idx-1]['MA20'] and \
                        daily_data.iloc[current_idx]['MA5'] <= daily_data.iloc[current_idx]['MA20']:
                        sell_signal = True
                        sell_reason = "데드 크로스 (5일선이 20일선을 하향돌파)"
                    
                    # 7. MACD 하향돌파 (상승장에서는 조건 완화)
                    elif current_idx > 0:
                        try:
                            # MACD 하향 돌파 확인
                            macd_bearish_cross = (daily_data['MACD'].iloc[current_idx-1] > daily_data['Signal'].iloc[current_idx-1] and 
                                                daily_data['MACD'].iloc[current_idx] < daily_data['Signal'].iloc[current_idx])
                            
                            # 상승장에서는 MACD 하향 돌파만으로 매도하지 않고 추가 조건 확인
                            if current_market_env == "uptrend":
                                # 상승장에서는 MACD 하향 돌파 + 수익률이 특정 수준 이상인 경우에만 매도
                                if macd_bearish_cross and profit_percent > custom_profit_target * 0.7:  # 목표의 70% 이상 도달했을 때
                                    sell_signal = True
                                    sell_reason = f"MACD 하향돌파 + 충분한 수익 달성: {profit_percent:.2f}% (목표의 {(profit_percent/custom_profit_target*100):.0f}%)"
                            else:
                                # 상승장이 아닌 경우 기존 로직 유지
                                if macd_bearish_cross:
                                    sell_signal = True
                                    sell_reason = "MACD 하향돌파"
                        except:
                            pass
                    
                    # 8. 시장 환경 변화에 따른 추가 매도 조건
                    elif market_env == "uptrend" and profit_percent > 0 and current_idx > 0 and \
                        daily_data.iloc[current_idx-1]['MA5'] > daily_data.iloc[current_idx-1]['MA20'] and \
                        daily_data.iloc[current_idx]['MA5'] < daily_data.iloc[current_idx]['MA20']:
                        sell_signal = True
                        sell_reason = f"상승 추세 반전 (수익률: {profit_percent:.2f}%)"
                    
                    elif market_env == "downtrend" and profit_percent > 0.8 * custom_profit_target:
                        sell_signal = True
                        sell_reason = f"하락장 즉시 수익 실현: {profit_percent:.2f}% (목표의 {profit_percent/custom_profit_target*100:.0f}%)"
                    
                    # 매도 시그널이 있으면 매도 실행
                    if sell_signal:
                        quantity = holding_info["quantity"]
                        sell_amount = current_price * quantity
                        profit = sell_amount - (avg_price * quantity)
                        
                        # 자본 업데이트
                        total_capital += sell_amount
                        
                        # 거래 기록
                        trades.append({
                            "stock_code": stock_code,
                            "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                            "action": "SELL",
                            "reason": sell_reason,
                            "date": date,
                            "price": current_price,
                            "quantity": quantity,
                            "profit_loss": profit,
                            "profit_loss_percent": profit_percent,
                            "market_environment": current_market_env
                        })
                        
                        # 보유 종목에서 제거
                        del virtual_holdings[stock_code]
                        
                        # 시장 환경 통계 업데이트
                        backtest_results["market_environment_stats"][current_market_env] += 1
                
                # 2. 매수 후보 종목 병렬 분석 및 점수 평가
                if len(virtual_holdings) < max_holdings_count:  # 최대 보유 종목 수 확인 (상승장에서는 증가)
                    buy_candidates = []
                    
                    for stock_code in self.watch_list:
                        # 이미 보유 중인 종목 스킵
                        if stock_code in virtual_holdings:
                            continue
                        
                        # 해당 종목의 현재 데이터가 있는지 확인
                        if stock_code not in stock_data_cache or date not in stock_data_cache[stock_code].index:
                            continue
                        
                        daily_data = stock_data_cache[stock_code]
                        current_idx = daily_data.index.get_loc(date)
                        
                        # 지표 계산을 위해 최소 필요한 데이터 확인
                        if current_idx < 20:  # 최소 20일 이상의 데이터 필요
                            continue
                        
                        current_price = daily_data.iloc[current_idx]['close']
                        
                        # 매수 시그널 분석 - 수정된 분석 함수 사용
                        # 기존 _analyze_stock_for_backtest 대신 새로운 함수 구현
                        analysis_result = self._enhanced_analyze_for_backtest(
                            stock_code=stock_code,
                            daily_data=daily_data,
                            current_idx=current_idx,
                            current_market_env=current_market_env
                        )
                        
                        if analysis_result.get("is_buy_signal", False):
                            analysis_result["stock_code"] = stock_code
                            analysis_result["current_price"] = current_price
                            analysis_result["date"] = date
                            buy_candidates.append(analysis_result)
                    
                    # 매수 후보가 있으면 점수 기반으로 정렬
                    if buy_candidates:
                        # 점수 기반 내림차순 정렬
                        buy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
                        
                        # 상위 후보만 선택 (보유 가능 종목 수만큼)
                        available_slots = max_holdings_count - len(virtual_holdings)
                        top_candidates = buy_candidates[:available_slots]
                        
                        for candidate in top_candidates:
                            stock_code = candidate.get("stock_code")
                            stock_name = candidate.get("stock_name", stock_code)
                            current_price = candidate.get("current_price", 0)
                            
                            # 종목별 할당 예산 계산
                            stock_info = self.watch_list_info.get(stock_code, {})
                            allocation_ratio = stock_info.get("allocation_ratio", self.default_allocation_ratio)
                            
                            # 상승장에서는 배분 비율 증가
                            if current_market_env == "uptrend":
                                allocation_ratio = min(allocation_ratio * 1.2, 0.3)  # 20% 증가, 최대 30%까지
                                
                            allocated_budget = self.total_budget * allocation_ratio
                            
                            # 시장 환경에 따른 매수 비율 조정
                            purchase_ratio = 1.0  # 기본값
                            if current_market_env == "downtrend":
                                purchase_ratio = 0.7  # 하락장에서는 보수적으로
                            elif current_market_env == "uptrend":
                                purchase_ratio = 1.2  # 상승장에서는 적극적으로 (20% 증가)
                            
                            adjusted_budget = min(allocated_budget * purchase_ratio, total_capital)
                            quantity = max(1, int(adjusted_budget / current_price))
                            
                            # 매수 실행
                            buy_amount = current_price * quantity
                            
                            if buy_amount <= total_capital and buy_amount >= self.min_trading_amount:
                                # 조정된 파라미터 가져오기
                                adjusted_params = candidate.get("adjusted_parameters", {})
                                custom_profit_target = adjusted_params.get("profit_target", self.profit_target)
                                custom_stop_loss = adjusted_params.get("stop_loss", self.stop_loss)
                                
                                # 자본 업데이트
                                total_capital -= buy_amount
                                
                                # 트레일링 스탑 비율 조정
                                trailing_stop_pct = self.trailing_stop_pct
                                if current_market_env == "uptrend":
                                    trailing_stop_pct *= 0.85  # 상승장에서는 15% 감소
                                
                                # 보유 종목에 추가
                                virtual_holdings[stock_code] = {
                                    "quantity": quantity,
                                    "avg_price": current_price,
                                    "buy_date": date,
                                    "highest_price": current_price,
                                    "trailing_stop_price": current_price * (1 - trailing_stop_pct/100) if self.use_trailing_stop else 0,
                                    "profit_target": custom_profit_target,
                                    "stop_loss": custom_stop_loss,
                                    "market_environment": current_market_env,
                                    "use_dynamic_stop": self.use_dynamic_stop,
                                    "dynamic_stop_price": current_price - (daily_data.iloc[current_idx]['ATR'] * self.atr_multiplier) if not pd.isna(daily_data.iloc[current_idx]['ATR']) else 0,
                                    "partial_profit_taken": False
                                }
                                
                                # 거래 기록
                                trades.append({
                                    "stock_code": stock_code,
                                    "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                    "action": "BUY",
                                    "reason": candidate.get("reason", "매수 시그널"),
                                    "date": date,
                                    "price": current_price,
                                    "quantity": quantity,
                                    "amount": buy_amount,
                                    "market_environment": current_market_env,
                                    "adjusted_parameters": {
                                        "profit_target": custom_profit_target, 
                                        "stop_loss": custom_stop_loss
                                    },
                                    "score": candidate.get("score", 0)
                                })
                                
                                # 시장 환경 통계 업데이트
                                backtest_results["market_environment_stats"][current_market_env] += 1

            # 백테스트 종료 시점에 보유중인 종목 청산
            for stock_code, holding in list(virtual_holdings.items()):
                if stock_code in stock_data_cache:
                    last_price = stock_data_cache[stock_code]['close'].iloc[-1]
                else:
                    # 데이터가 없으면 최신 가격 조회
                    daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 1, adj_ok=1)
                    if daily_data is None or daily_data.empty:
                        continue
                    last_price = daily_data.iloc[-1]['close']
                
                quantity = holding["quantity"]
                avg_price = holding["avg_price"]
                
                sell_amount = last_price * quantity
                profit = sell_amount - (avg_price * quantity)
                profit_percent = ((last_price / avg_price) - 1) * 100
                
                # 자본 업데이트
                total_capital += sell_amount
                
                # 거래 기록
                trades.append({
                    "stock_code": stock_code,
                    "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                    "action": "SELL",
                    "reason": "백테스트 종료",
                    "date": end_date_dt if isinstance(end_date_dt, datetime.datetime) else pd.to_datetime(end_date),
                    "price": last_price,
                    "quantity": quantity,
                    "profit_loss": profit,
                    "profit_loss_percent": profit_percent,
                    "market_environment": holding.get("market_environment", "sideways")
                })
            
            # 백테스트 결과 계산
            backtest_results["final_capital"] = total_capital
            backtest_results["profit_loss"] = total_capital - self.total_budget
            backtest_results["profit_loss_percent"] = (backtest_results["profit_loss"] / self.total_budget) * 100
            backtest_results["trades"] = trades
            
            # 승률 계산
            win_trades = [t for t in trades if t.get("action") in ["SELL", "PARTIAL_SELL"] and t.get("profit_loss", 0) > 0]
            loss_trades = [t for t in trades if t.get("action") in ["SELL", "PARTIAL_SELL"] and t.get("profit_loss", 0) <= 0]
            
            if len(win_trades) + len(loss_trades) > 0:
                backtest_results["win_rate"] = len(win_trades) / (len(win_trades) + len(loss_trades)) * 100
            
            # 평균 수익/손실 계산
            if win_trades:
                backtest_results["avg_profit"] = sum(t.get("profit_loss", 0) for t in win_trades) / len(win_trades)
            
            if loss_trades:
                backtest_results["avg_loss"] = sum(t.get("profit_loss", 0) for t in loss_trades) / len(loss_trades)
            
            # 최대 낙폭 계산
            capital_history = [self.total_budget]
            for trade in trades:
                if trade.get("action") == "BUY":
                    capital_history.append(capital_history[-1] - trade.get("amount", 0))
                elif trade.get("action") in ["SELL", "PARTIAL_SELL"]:
                    capital_history.append(capital_history[-1] + trade.get("price", 0) * trade.get("quantity", 0))
            
            max_capital = self.total_budget
            max_drawdown = 0
            
            for capital in capital_history:
                max_capital = max(max_capital, capital)
                drawdown = (max_capital - capital) / max_capital * 100
                max_drawdown = max(max_drawdown, drawdown)
            
            backtest_results["max_drawdown"] = max_drawdown
            
            # 종목별 성과 분석
            stock_performance = {}
            for trade in trades:
                code = trade.get("stock_code")
                if code not in stock_performance:
                    stock_performance[code] = {
                        "name": trade.get("stock_name", code),
                        "total_profit": 0,
                        "trades_count": 0,
                        "win_count": 0
                    }
                
                if trade.get("action") in ["SELL", "PARTIAL_SELL"]:
                    profit = trade.get("profit_loss", 0)
                    stock_performance[code]["total_profit"] += profit
                    stock_performance[code]["trades_count"] += 1
                    if profit > 0:
                        stock_performance[code]["win_count"] += 1
            
            # 종목별 승률 계산
            for code in stock_performance:
                trades_count = stock_performance[code]["trades_count"]
                if trades_count > 0:
                    stock_performance[code]["win_rate"] = (stock_performance[code]["win_count"] / trades_count) * 100
                else:
                    stock_performance[code]["win_rate"] = 0
            
            backtest_results["stock_performance"] = stock_performance
            
            # 시장 환경별 성과 분석
            market_env_performance = {
                "uptrend": {"trades": 0, "win_trades": 0, "profit": 0},
                "downtrend": {"trades": 0, "win_trades": 0, "profit": 0},
                "sideways": {"trades": 0, "win_trades": 0, "profit": 0}
            }
            
            for trade in trades:
                if trade.get("action") in ["SELL", "PARTIAL_SELL"]:
                    env = trade.get("market_environment", "sideways")
                    profit = trade.get("profit_loss", 0)
                    
                    market_env_performance[env]["trades"] += 1
                    market_env_performance[env]["profit"] += profit
                    
                    if profit > 0:
                        market_env_performance[env]["win_trades"] += 1
            
            # 승률 및 평균 수익 계산
            for env, data in market_env_performance.items():
                if data["trades"] > 0:
                    data["win_rate"] = (data["win_trades"] / data["trades"]) * 100
                    data["avg_profit"] = data["profit"] / data["trades"]
                else:
                    data["win_rate"] = 0
                    data["avg_profit"] = 0
            
            backtest_results["market_environment_performance"] = market_env_performance
            
            logger.info(f"백테스트 완료: 최종 자본금 {backtest_results['final_capital']:,.0f}원, " + 
                    f"수익률 {backtest_results['profit_loss_percent']:.2f}%, " +
                    f"승률 {backtest_results['win_rate']:.2f}%")
            
            # 시장 환경별 성과 로깅
            for env, stats in market_env_performance.items():
                if stats["trades"] > 0:
                    logger.info(f"시장 환경 '{env}' 성과: 거래 수: {stats['trades']}건, " +
                            f"승률: {stats['win_rate']:.2f}%, 평균 수익: {stats['avg_profit']:,.0f}원")
            
            return backtest_results
        
        except Exception as e:
            logger.exception(f"백테스트 실행 중 오류: {str(e)}")
            return backtest_results

    def run_adaptive_backtest(self, start_date: str, end_date: str = None, reset_strategy: bool = False) -> Dict[str, any]:
        """적응형 전략을 적용한 백테스트 실행
        
        Args:
            start_date: 시작일자 (YYYYMMDD)
            end_date: 종료일자 (YYYYMMDD), 없으면 현재 날짜
            reset_strategy: 기존 전략 데이터를 초기화하고 시작할지 여부
            
        Returns:
            Dict: 백테스트 결과
        """
        logger.info(f"적응형 전략 백테스트 시작: {start_date} ~ {end_date or '현재'}")
        
        if not end_date:
            end_date = datetime.datetime.now().strftime("%Y%m%d")
        
        # 백테스트 결과 기본 구조
        backtest_results = {
            "initial_capital": self.total_budget,
            "final_capital": self.total_budget,
            "profit_loss": 0,
            "profit_loss_percent": 0,
            "trades": [],
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "max_drawdown": 0,
            "market_environment_stats": {
                "uptrend": 0,
                "downtrend": 0,
                "sideways": 0
            },
            "adaptive_strategy_performance": {}
        }
        
        # 초기 자본금
        total_capital = self.total_budget
        virtual_holdings = {}
        trades = []
        
        # 적응형 전략 관리를 위한 임시 객체
        if reset_strategy:
            logger.info("적응형 전략 데이터 초기화")
            backtest_adaptive_strategy = AdaptiveMarketStrategy("backtest_adaptive_strategy.json")
            # 데이터 초기화
            backtest_adaptive_strategy.stock_performance = {}
            backtest_adaptive_strategy.save_strategy()
        else:
            backtest_adaptive_strategy = AdaptiveMarketStrategy("backtest_adaptive_strategy.json")
        
        try:
            # 종목 특성 초기 분석
            characteristics = self.analyze_stock_characteristics()
            
            # 특성 기반 초기 전략 설정
            for stock_code, char_info in characteristics.items():
                char_type = char_info["type"]
                sub_type = char_info["sub_type"]
                
                # 템플릿과 조정 로직 (기존 initialize_adaptive_strategies와 동일)
                # 이 부분은 동일하게 구현하여 초기 전략 설정
                
                # 특성 데이터 저장
                backtest_adaptive_strategy.stock_performance[stock_code] = {
                    "characteristic": char_type,
                    "sub_type": sub_type,
                    "metrics": char_info["metrics"],
                    "uptrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                    "downtrend": {"trades": 0, "wins": 0, "winrate": 0.0},
                    "sideways": {"trades": 0, "wins": 0, "winrate": 0.0},
                    "adaptive_strategy": {
                        "uptrend": {}, 
                        "downtrend": {}, 
                        "sideways": {}
                    }
                }
                
                # 특성에 맞는 초기 전략 설정 (initialize_adaptive_strategies와 동일)
                
            # 백테스트 날짜 데이터 준비 (기존 백테스트 로직과 동일)
            
            # 시장 환경 기록
            market_env_history = {}
            # 시장 환경 분석 코드...
            
            # 종목 데이터 캐싱
            stock_data_cache = {}
            # 종목 데이터 로드 코드...
            
            # 고유한 날짜 목록 생성
            all_dates = sorted(list(set(date for stock_code, data in stock_data_cache.items() for date in data.index)))
            
            # 백테스트 학습 모드 설정
            adaptive_learning = True  # 백테스트 중 전략 학습 여부
            adaptive_apply_interval = 20  # 몇 거래일마다 학습된 전략을 적용할지
            days_counter = 0
            
            # 날짜별 시뮬레이션
            for date in all_dates:
                days_counter += 1
                logger.debug(f"날짜 {date} 분석 시작")
                
                # 현재 날짜의 시장 환경 확인
                current_market_env = market_env_history.get(date, "sideways")
                
                # 1. 보유 중인 종목 매도 확인 (매도 시그널)
                for stock_code, holding_info in list(virtual_holdings.items()):
                    # 각 종목에 대한 매도 로직
                    
                    # 종목별 맞춤 파라미터 가져오기 (적응형)
                    stock_strategy = backtest_adaptive_strategy.get_stock_strategy(stock_code, current_market_env)
                    
                    custom_profit_target = holding_info.get("profit_target", self.profit_target)
                    custom_stop_loss = holding_info.get("stop_loss", self.stop_loss)
                    trailing_stop_pct = self.trailing_stop_pct * stock_strategy.get("trailing_stop_multiplier", 1.0)
                    
                    # 매도 로직...
                    
                    # 매도 시그널이 있으면 매도 주문
                    if sell_signal:
                        # 매도 실행 로직...
                        
                        # 적응형 전략 업데이트 (거래 성과 기록)
                        is_win = profit_percent > 0
                        if adaptive_learning:
                            backtest_adaptive_strategy.update_performance(stock_code, current_market_env, is_win)
                
                # 매도 후 주기적으로 학습된 전략 적용
                if adaptive_learning and days_counter % adaptive_apply_interval == 0:
                    logger.info(f"백테스트 날짜 {date}: 적응형 전략 학습 적용 ({days_counter}일)")
                    backtest_adaptive_strategy.save_strategy()
                
                # 2. 매수 후보 종목 분석
                if len(virtual_holdings) < self.max_stocks:  # 최대 보유 종목 수 확인
                    buy_candidates = []
                    
                    for stock_code in self.watch_list:
                        # 매수 후보 분석 로직...
                        
                        # 종목별 맞춤 전략 적용하여 분석
                        stock_strategy = backtest_adaptive_strategy.get_stock_strategy(stock_code, current_market_env)
                        
                        # 분석 결과에 전략 파라미터 적용
                        profit_target_adjusted = self.profit_target * stock_strategy.get("profit_target_multiplier", 1.0)
                        stop_loss_adjusted = self.stop_loss * stock_strategy.get("stop_loss_multiplier", 1.0)
                        rsi_threshold_adjusted = self.rsi_oversold + stock_strategy.get("rsi_threshold_adjustment", 0)
                        required_signals = stock_strategy.get("required_signals", 2)
                        
                        # 매수 시그널 판단 (필요 시그널 개수 맞춤화)
                        daily_buy_signal = (is_oversold or current_market_env != "uptrend") and daily_signals_count >= required_signals
                        
                        # 매수 시그널이 있으면 후보에 추가
                        if daily_buy_signal:
                            buy_candidates.append({
                                "stock_code": stock_code,
                                "current_price": current_price,
                                "score": calculate_score(signals, self.score_weights),
                                "profit_target": profit_target_adjusted,
                                "stop_loss": stop_loss_adjusted,
                                "trailing_stop_pct": self.trailing_stop_pct * stock_strategy.get("trailing_stop_multiplier", 1.0)
                            })
                    
                    # 매수 후보 선택 및 매수 실행 로직...
                
            # 백테스트 종료 시 보유 종목 청산
            
            # 백테스트 결과 계산
            
            # 적응형 전략 성과 추가
            backtest_results["adaptive_strategy_performance"] = {
                "final_strategies": backtest_adaptive_strategy.stock_performance,
                "strategy_evolution": {
                    "uptrend_winrate_improvement": {},
                    "downtrend_winrate_improvement": {},
                    "sideways_winrate_improvement": {}
                }
            }
            
            # 전략 진화 분석 (초기 vs 최종)
            for stock_code, perf in backtest_adaptive_strategy.stock_performance.items():
                if stock_code == "_metadata":
                    continue
                    
                for env in ["uptrend", "downtrend", "sideways"]:
                    if perf[env]["trades"] >= 5:  # 최소 5회 이상 거래가 있는 경우만
                        backtest_results["adaptive_strategy_performance"]["strategy_evolution"][f"{env}_winrate_improvement"][stock_code] = {
                            "initial_winrate": 0,  # 초기 승률은 기록하지 않았으므로 0으로 설정
                            "final_winrate": perf[env]["winrate"],
                            "trades": perf[env]["trades"]
                        }
            
            # 백테스트 결과 파일 저장
            adaptive_backtest_file = f"adaptive_backtest_result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(adaptive_backtest_file, 'w', encoding='utf-8') as f:
                json.dump(backtest_results, f, ensure_ascii=False, indent=4, default=str)
            
            # 학습된 전략도 별도 저장
            backtest_adaptive_strategy.save_strategy()
            logger.info(f"적응형 전략 백테스트 결과 저장 완료: {adaptive_backtest_file}")
            
            return backtest_results
            
        except Exception as e:
            logger.exception(f"적응형 전략 백테스트 실행 중 오류: {str(e)}")
            return backtest_results

    def run_incremental_backtest(self, days=30, apply_results=True):
        """최근 일정 기간에 대한 증분 백테스트를 실행하고 전략 업데이트"""
        try:
            # 날짜 계산
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
            
            logger.info(f"증분 백테스트 시작: {start_date} ~ {end_date} ({days}일)")
            
            # 증분 백테스트 실행 (기존 전략 데이터 유지)
            results = self.run_adaptive_backtest(start_date, end_date, reset_strategy=False)
            
            # 결과 저장
            incremental_results_file = f"incremental_backtest_{start_date}_{end_date}.json"
            with open(incremental_results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4, default=str)
            
            # 최적 전략 분석
            analysis_file = f"incremental_optimal_analysis_{start_date}_{end_date}.json"
            analysis = self.find_optimal_strategy_parameters(incremental_results_file, analysis_file)
            
            # 결과 적용
            if apply_results:
                self.apply_optimal_strategy_from_backtest("optimal_adaptive_strategy.json")
                logger.info(f"증분 백테스트 결과 적용 완료")
            
            return {
                "results_file": incremental_results_file,
                "analysis_file": analysis_file,
                "results": results,
                "analysis": analysis
            }
            
        except Exception as e:
            logger.exception(f"증분 백테스트 실행 중 오류: {str(e)}")
            return None        

    def find_optimal_strategy_parameters(self, backtest_results_file, output_file=None):
        """백테스트 결과 분석을 통한 최적 전략 파라미터 도출"""
        try:
            # 백테스트 결과 로드
            with open(backtest_results_file, 'r', encoding='utf-8') as f:
                backtest_results = json.load(f)
            
            # 분석 결과 초기화
            analysis = {
                "stock_optimal_strategies": {},
                "market_env_optimal_strategies": {},
                "global_optimal_strategy": {}
            }
            
            # 종목별 시장환경별 성과 집계
            stock_env_performance = {}
            
            for trade in backtest_results["trades"]:
                if trade["action"] in ["SELL", "PARTIAL_SELL"]:
                    stock_code = trade["stock_code"]
                    market_env = trade["market_environment"]
                    profit = trade.get("profit_loss", 0)
                    profit_percent = trade.get("profit_loss_percent", 0)
                    
                    # 성과 데이터 구조 초기화
                    if stock_code not in stock_env_performance:
                        stock_env_performance[stock_code] = {
                            "uptrend": {"trades": [], "parameters": []},
                            "downtrend": {"trades": [], "parameters": []},
                            "sideways": {"trades": [], "parameters": []}
                        }
                    
                    # 거래 기록
                    stock_env_performance[stock_code][market_env]["trades"].append({
                        "profit": profit,
                        "profit_percent": profit_percent,
                        "date": trade["date"]
                    })
                    
                    # 매매 파라미터 기록 (있는 경우)
                    if "adjusted_parameters" in trade:
                        stock_env_performance[stock_code][market_env]["parameters"].append(trade["adjusted_parameters"])
            
            # 종목별 최적 전략 분석
            for stock_code, env_data in stock_env_performance.items():
                analysis["stock_optimal_strategies"][stock_code] = {}
                
                for env, data in env_data.items():
                    if len(data["trades"]) >= 3:  # 최소 3회 이상 거래가 있는 경우만
                        # 수익률 기준 거래 정렬
                        sorted_trades = sorted(data["trades"], key=lambda x: x["profit_percent"], reverse=True)
                        
                        # 상위 30% 거래의 평균 파라미터 계산
                        top_n = max(1, int(len(sorted_trades) * 0.3))
                        top_trades = sorted_trades[:top_n]
                        
                        # 해당 거래들의 파라미터가 있으면 분석
                        if data["parameters"]:
                            avg_params = {}
                            for param_key in data["parameters"][0].keys():
                                avg_params[param_key] = sum(p.get(param_key, 0) for p in data["parameters"][:top_n]) / top_n
                            
                            # 결과 저장
                            analysis["stock_optimal_strategies"][stock_code][env] = {
                                "trade_count": len(data["trades"]),
                                "avg_return": sum(t["profit_percent"] for t in data["trades"]) / len(data["trades"]),
                                "top_trades_avg_return": sum(t["profit_percent"] for t in top_trades) / len(top_trades),
                                "optimal_parameters": avg_params
                            }
            
            # 시장 환경별 전체 최적 전략 분석
            all_env_trades = {
                "uptrend": {"trades": [], "parameters": []},
                "downtrend": {"trades": [], "parameters": []},
                "sideways": {"trades": [], "parameters": []}
            }
            
            # 모든 종목의 데이터 통합
            for stock_data in stock_env_performance.values():
                for env, data in stock_data.items():
                    all_env_trades[env]["trades"].extend(data["trades"])
                    all_env_trades[env]["parameters"].extend(data["parameters"])
            
            # 시장 환경별 최적 전략 계산
            for env, data in all_env_trades.items():
                if len(data["trades"]) >= 5:  # 최소 5회 이상 거래가 있는 경우만
                    # 수익률 기준 거래 정렬
                    sorted_trades = sorted(data["trades"], key=lambda x: x["profit_percent"], reverse=True)
                    
                    # 상위 30% 거래의 평균 파라미터 계산
                    top_n = max(1, int(len(sorted_trades) * 0.3))
                    top_trades = sorted_trades[:top_n]
                    
                    # 해당 거래들의 파라미터가 있으면 분석
                    if data["parameters"]:
                        avg_params = {}
                        for param_key in data["parameters"][0].keys():
                            values = [p.get(param_key, 0) for p in data["parameters"][:top_n]]
                            avg_params[param_key] = sum(values) / len(values)
                        
                        # 결과 저장
                        analysis["market_env_optimal_strategies"][env] = {
                            "trade_count": len(data["trades"]),
                            "avg_return": sum(t["profit_percent"] for t in data["trades"]) / len(data["trades"]),
                            "top_trades_avg_return": sum(t["profit_percent"] for t in top_trades) / len(top_trades),
                            "optimal_parameters": avg_params
                        }
            
            # 전체 최적 전략 계산 (모든 거래)
            all_trades = []
            all_parameters = []
            
            for env_data in all_env_trades.values():
                all_trades.extend(env_data["trades"])
                all_parameters.extend(env_data["parameters"])
            
            if all_trades and all_parameters:
                # 수익률 기준 거래 정렬
                sorted_all_trades = sorted(all_trades, key=lambda x: x["profit_percent"], reverse=True)
                
                # 상위 30% 거래의 평균 파라미터 계산
                top_n = max(1, int(len(sorted_all_trades) * 0.3))
                top_all_trades = sorted_all_trades[:top_n]
                
                # 해당 거래들의 파라미터가 있으면 분석
                if all_parameters:
                    global_avg_params = {}
                    for param_key in all_parameters[0].keys():
                        global_avg_params[param_key] = sum(p.get(param_key, 0) for p in all_parameters[:top_n]) / top_n
                    
                    # 결과 저장
                    analysis["global_optimal_strategy"] = {
                        "trade_count": len(all_trades),
                        "avg_return": sum(t["profit_percent"] for t in all_trades) / len(all_trades),
                        "top_trades_avg_return": sum(t["profit_percent"] for t in top_all_trades) / len(top_all_trades),
                        "optimal_parameters": global_avg_params
                    }
            
            # 최적 전략 적용을 위한 변환
            adaptive_strategy_config = {
                "global": {
                    "uptrend": self._convert_optimal_params_to_strategy(analysis["market_env_optimal_strategies"].get("uptrend", {}).get("optimal_parameters", {})),
                    "downtrend": self._convert_optimal_params_to_strategy(analysis["market_env_optimal_strategies"].get("downtrend", {}).get("optimal_parameters", {})),
                    "sideways": self._convert_optimal_params_to_strategy(analysis["market_env_optimal_strategies"].get("sideways", {}).get("optimal_parameters", {}))
                },
                "stocks": {}
            }
            
            # 종목별 최적 전략 변환
            for stock_code, env_strategies in analysis["stock_optimal_strategies"].items():
                adaptive_strategy_config["stocks"][stock_code] = {
                    "uptrend": self._convert_optimal_params_to_strategy(env_strategies.get("uptrend", {}).get("optimal_parameters", {})),
                    "downtrend": self._convert_optimal_params_to_strategy(env_strategies.get("downtrend", {}).get("optimal_parameters", {})),
                    "sideways": self._convert_optimal_params_to_strategy(env_strategies.get("sideways", {}).get("optimal_parameters", {}))
                }
            
            # 결과 저장
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(analysis, f, ensure_ascii=False, indent=4)
                logger.info(f"최적 전략 분석 결과 저장 완료: {output_file}")
            
            # 최적 전략 설정 파일 저장
            optimal_strategy_file = "optimal_adaptive_strategy.json"
            with open(optimal_strategy_file, 'w', encoding='utf-8') as f:
                json.dump(adaptive_strategy_config, f, ensure_ascii=False, indent=4)
            logger.info(f"최적 적응형 전략 설정 저장 완료: {optimal_strategy_file}")
            
            return analysis
            
        except Exception as e:
            logger.exception(f"최적 전략 파라미터 도출 중 오류: {str(e)}")
            return {}
        
    def _convert_optimal_params_to_strategy(self, optimal_params):
        """최적 파라미터를 전략 형식으로 변환"""
        # 기본 전략 템플릿
        strategy = {
            "use_common": False,
            "profit_target_multiplier": 1.0,
            "stop_loss_multiplier": 1.0,
            "rsi_threshold_adjustment": 0,
            "required_signals": 2,
            "trailing_stop_multiplier": 1.0
        }
        
        # 파라미터 매핑 (백테스트 파라미터 -> 전략 파라미터)
        if optimal_params:
            # 목표 수익률 파라미터 변환
            if "profit_target" in optimal_params:
                base_profit_target = self.profit_target
                if base_profit_target != 0:
                    strategy["profit_target_multiplier"] = optimal_params["profit_target"] / base_profit_target
            
            # 손절률 파라미터 변환
            if "stop_loss" in optimal_params:
                base_stop_loss = self.stop_loss
                if base_stop_loss != 0:
                    strategy["stop_loss_multiplier"] = optimal_params["stop_loss"] / base_stop_loss
            
            # RSI 임계값 파라미터 변환
            if "rsi_threshold" in optimal_params:
                base_rsi = self.rsi_oversold
                strategy["rsi_threshold_adjustment"] = optimal_params["rsi_threshold"] - base_rsi
            
            # 필요 시그널 수 파라미터 변환
            if "required_signals" in optimal_params:
                strategy["required_signals"] = int(optimal_params["required_signals"])
        
        return strategy

    # 백테스트용 강화된 종목 분석 함수 추가
    def _enhanced_analyze_for_backtest(self, stock_code: str, daily_data: pd.DataFrame, current_idx: int, current_market_env: str) -> Dict[str, any]:
        """상승장 전략이 강화된 백테스트용 종목 분석 함수
        
        Args:
            stock_code: 종목코드
            daily_data: 일봉 데이터
            current_idx: 현재 데이터 인덱스
            current_market_env: 현재 시장 환경
            
        Returns:
            Dict: 분석 결과
        """
        try:
            # 종목 기본 정보
            stock_name = self.watch_list_info.get(stock_code, {}).get("name", stock_code)
            current_price = daily_data.iloc[current_idx]['close']
            
            # 분석 결과 초기화
            analysis_result = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "current_price": current_price,
                "is_buy_signal": False,
                "signals": {
                    "daily": {},
                },
                "technical_data": {
                    "rsi": daily_data['RSI'].iloc[current_idx] if 'RSI' in daily_data.columns else None,
                    "macd": daily_data['MACD'].iloc[current_idx] if 'MACD' in daily_data.columns else None,
                    "macd_signal": daily_data['Signal'].iloc[current_idx] if 'Signal' in daily_data.columns else None,
                    "ma5": daily_data['MA5'].iloc[current_idx] if 'MA5' in daily_data.columns else None,
                    "ma20": daily_data['MA20'].iloc[current_idx] if 'MA20' in daily_data.columns else None,
                    "ma60": daily_data['MA60'].iloc[current_idx] if 'MA60' in daily_data.columns else None,
                    "atr": daily_data['ATR'].iloc[current_idx] if 'ATR' in daily_data.columns else None
                }
            }
            
            # 동적 손절가 계산
            if 'ATR' in daily_data.columns and not pd.isna(daily_data['ATR'].iloc[current_idx]):
                current_atr = daily_data['ATR'].iloc[current_idx]
                dynamic_stop_loss = current_price - (current_atr * self.atr_multiplier)
                analysis_result["technical_data"]["dynamic_stop_loss"] = dynamic_stop_loss
            
            # 시장 환경에 따른 파라미터 조정
            profit_target_adjusted = self.profit_target
            stop_loss_adjusted = self.stop_loss
            rsi_threshold_adjusted = self.rsi_oversold
            
            if current_market_env == "uptrend":
                # 상승장 전략 (수정된 부분)
                profit_target_adjusted = self.profit_target * 1.8  # 목표 수익률 80% 증가 (기존 50%에서 상향)
                stop_loss_adjusted = self.stop_loss * 0.8  # 손절폭 20% 감소
                rsi_threshold_adjusted = min(self.rsi_oversold + 8, 38)  # RSI 임계값 크게 완화 (기존 +5에서 +8로 상향)
                
                # 추세 확인으로 매수 신호 보강
                if not daily_data.empty:
                    # 상승장에서는 추가 매매 조건 확인
                    
                    # 1. 5일선이 20일선 위에 있는지 (골든크로스 또는 상승추세 중)
                    ma_aligned = False
                    if 'MA5' in daily_data.columns and 'MA20' in daily_data.columns:
                        ma_aligned = daily_data['MA5'].iloc[current_idx] > daily_data['MA20'].iloc[current_idx]
                        analysis_result["signals"]["daily"]["ma_aligned"] = ma_aligned
                    
                    # 2. 최근 3일간 종가 상승 추세인지
                    price_uptrend = False
                    if current_idx >= 3:
                        price_uptrend = (daily_data['close'].iloc[current_idx] > daily_data['close'].iloc[current_idx-1] > 
                                    daily_data['close'].iloc[current_idx-2])
                        analysis_result["signals"]["daily"]["price_uptrend"] = price_uptrend
                    
                    # 3. 거래량 증가 추세인지
                    volume_trend = False
                    if 'volume' in daily_data.columns and current_idx >= 10:
                        recent_vol = daily_data['volume'].iloc[current_idx-4:current_idx+1].mean()
                        prev_vol = daily_data['volume'].iloc[current_idx-9:current_idx-4].mean()
                        volume_trend = recent_vol > prev_vol * 1.1  # 10% 이상 증가
                        analysis_result["signals"]["daily"]["volume_trend"] = volume_trend
                    
                    # 상승장 특화 매수 점수 부여
                    uptrend_score = 0
                    if ma_aligned: uptrend_score += 2
                    if price_uptrend: uptrend_score += 1
                    if volume_trend: uptrend_score += 2
                    
                    # 상승장 특화 매수 점수 추가
                    analysis_result["uptrend_score"] = uptrend_score
                    
            elif current_market_env == "downtrend":
                # 하락장 전략 (매수 기준 강화, 손절폭 감소)
                profit_target_adjusted = self.profit_target * 0.8  # 목표 수익률 20% 감소
                stop_loss_adjusted = self.stop_loss * 0.6  # 손절폭 40% 감소 (더 타이트하게)
                rsi_threshold_adjusted = max(self.rsi_oversold - 5, 20)  # RSI 임계값 강화
                
                # 안전한 매수 시점인지 확인
                is_safe_entry = self.is_safe_to_buy_in_downtrend(daily_data)
                analysis_result["signals"]["daily"]["safe_entry"] = is_safe_entry
            
            # 조정된 파라미터 저장
            analysis_result["adjusted_parameters"] = {
                "profit_target": profit_target_adjusted,
                "stop_loss": stop_loss_adjusted,
                "rsi_threshold": rsi_threshold_adjusted
            }
            
            # 1. RSI 과매도 확인 (시장 환경에 맞는 임계값 사용)
            rsi_value = daily_data['RSI'].iloc[current_idx] if 'RSI' in daily_data.columns else None
            is_oversold = rsi_value is not None and rsi_value <= rsi_threshold_adjusted
            analysis_result["signals"]["daily"]["rsi_oversold"] = is_oversold
            
            # 2. 골든 크로스 확인
            is_golden_cross = False
            if current_idx > 0 and 'MA5' in daily_data.columns and 'MA20' in daily_data.columns:
                if daily_data['MA5'].iloc[current_idx-1] < daily_data['MA20'].iloc[current_idx-1] and \
                daily_data['MA5'].iloc[current_idx] >= daily_data['MA20'].iloc[current_idx]:
                    is_golden_cross = True
            analysis_result["signals"]["daily"]["golden_cross"] = is_golden_cross
            
            # 3. MACD 상향돌파 확인
            macd_cross_up = False
            if current_idx > 0 and 'MACD' in daily_data.columns and 'Signal' in daily_data.columns:
                if daily_data['MACD'].iloc[current_idx-1] < daily_data['Signal'].iloc[current_idx-1] and \
                daily_data['MACD'].iloc[current_idx] >= daily_data['Signal'].iloc[current_idx]:
                    macd_cross_up = True
            analysis_result["signals"]["daily"]["macd_cross_up"] = macd_cross_up
            
            # 4. 볼린저 밴드 하단 접촉
            price_near_lower_band = False
            if 'LowerBand' in daily_data.columns:
                price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[current_idx] * 1.01
            analysis_result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
            
            # 5. 모멘텀 상승 전환
            momentum_turning_up = False
            if current_idx >= 3:
                try:
                    # 모멘텀은 계산이 필요하면 직접 계산
                    if 'Momentum' not in daily_data.columns:
                        recent_momentum = [(daily_data['close'].iloc[i] / daily_data['close'].iloc[i-10] - 1) * 100 
                                        for i in range(current_idx-2, current_idx+1) if i >= 10]
                        if len(recent_momentum) == 3:
                            momentum_turning_up = recent_momentum[0] < recent_momentum[1] < recent_momentum[2]
                    else:
                        momentum_turning_up = (daily_data['Momentum'].iloc[current_idx-2] < 
                                            daily_data['Momentum'].iloc[current_idx-1] < 
                                            daily_data['Momentum'].iloc[current_idx])
                except:
                    momentum_turning_up = False
            analysis_result["signals"]["daily"]["momentum_turning_up"] = momentum_turning_up
            
            # 6. 지지선 근처인지 확인
            near_support = False
            support_price = None
            try:
                # 지지선 계산 (간단한 방법 - 최근 20일 저가의 하위 10%)
                if current_idx >= 20:
                    recent_lows = daily_data['low'].iloc[current_idx-20:current_idx].values
                    support_price = np.percentile(recent_lows, 10)
                    near_support = current_price <= support_price * 1.03  # 지지선 근처 (3% 이내)
            except:
                near_support = False
            analysis_result["signals"]["daily"]["near_support"] = near_support
            analysis_result["technical_data"]["support"] = support_price
            
            # 7. 거래량 증가 확인
            volume_increase = False
            if 'volume' in daily_data.columns and current_idx >= 10:
                try:
                    avg_volume = daily_data['volume'].iloc[current_idx-10:current_idx].mean()
                    current_volume = daily_data['volume'].iloc[current_idx]
                    volume_increase = current_volume > avg_volume * 1.5  # 50% 이상 증가
                except:
                    volume_increase = False
            analysis_result["signals"]["daily"]["volume_increase"] = volume_increase
            
            # 8. 캔들 패턴 확인 (강세 캔들)
            bullish_candle = False
            try:
                if current_idx >= 0 and all(col in daily_data.columns for col in ['open', 'close', 'high', 'low']):
                    open_price = daily_data['open'].iloc[current_idx]
                    close_price = daily_data['close'].iloc[current_idx]
                    high_price = daily_data['high'].iloc[current_idx]
                    low_price = daily_data['low'].iloc[current_idx]
                    
                    # 양봉 확인
                    if close_price > open_price:
                        body_size = close_price - open_price
                        candle_range = high_price - low_price
                        
                        if body_size > candle_range * 0.5:
                            bullish_candle = True
                    
                    # 망치형 캔들 확인 (하단 꼬리가 몸통의 2배 이상)
                    if not bullish_candle:
                        if close_price > open_price:  # 양봉
                            body_size = close_price - open_price
                            lower_shadow = open_price - low_price
                            
                            if lower_shadow > body_size * 2 and body_size > 0:
                                bullish_candle = True
                        else:  # 음봉
                            body_size = open_price - close_price
                            lower_shadow = close_price - low_price
                            
                            if lower_shadow > body_size * 2 and body_size > 0:
                                bullish_candle = True
            except:
                bullish_candle = False
            analysis_result["signals"]["daily"]["bullish_candle"] = bullish_candle
            
            # 9. 연속 하락 확인
            consecutive_drop = False
            if current_idx >= 3:
                try:
                    drops = []
                    for i in range(current_idx-2, current_idx+1):
                        if i > 0:
                            drops.append(daily_data['close'].iloc[i] < daily_data['close'].iloc[i-1])
                    consecutive_drop = all(drops)
                except:
                    consecutive_drop = False
            analysis_result["signals"]["daily"]["consecutive_drop"] = consecutive_drop
            
            # 10. 골든크로스 직후 여부 확인 (상승장 특화 신호)
            fresh_golden_cross = False
            if current_idx > 0 and 'MA5' in daily_data.columns and 'MA20' in daily_data.columns:
                if (daily_data['MA5'].iloc[current_idx-1] <= daily_data['MA20'].iloc[current_idx-1] and
                    daily_data['MA5'].iloc[current_idx] > daily_data['MA20'].iloc[current_idx]):
                    fresh_golden_cross = True
            analysis_result["signals"]["daily"]["fresh_golden_cross"] = fresh_golden_cross
            
            # 최종 매수 시그널 결정
            # 일봉 시그널 점수 계산
            daily_signals_count = sum([
                is_oversold,              # RSI 과매도
                price_near_lower_band,    # 볼린저 밴드 하단
                near_support,             # 지지선 근처
                is_golden_cross,          # 골든 크로스
                macd_cross_up,            # MACD 상향돌파
                momentum_turning_up,      # 모멘텀 상승전환
                volume_increase,          # 거래량 증가
                bullish_candle,           # 강세 캔들 패턴
                consecutive_drop,         # 연속 하락 후 반등 가능성
                fresh_golden_cross        # 골든크로스 직후 (상승장 특화)
            ])
            
            # 상승장에서는 매수 조건 완화 - 핵심 변경 부분!
            if current_market_env == "uptrend":
                # 상승장에서는 RSI 과매도가 없어도 다른 조건이 충족되면 매수
                # 또한 필요 시그널 수를 2개에서 1개로 감소
                daily_buy_signal = daily_signals_count >= 1 or analysis_result.get("uptrend_score", 0) >= 3
                
                # 상승장 특화 매수 신호 추가 - 골든크로스 직후 매수
                if fresh_golden_cross:
                    daily_buy_signal = True
            else:
                # 다른 환경에서는 기존 규칙 유지 (RSI 과매도 필수 + 최소 2개 시그널)
                daily_buy_signal = is_oversold and daily_signals_count >= 2
            
            # 하락장에서는 추가 안전 조건 확인
            if daily_buy_signal and current_market_env == "downtrend":
                if not analysis_result["signals"]["daily"].get("safe_entry", False):
                    daily_buy_signal = False
                    analysis_result["reason"] = "하락장 안전 매수 조건 미충족"
            
            # 최종 매수 시그널 설정
            analysis_result["is_buy_signal"] = daily_buy_signal
            
            # 매수 이유 상세화
            if daily_buy_signal:
                reasons = []
                if is_oversold: reasons.append("RSI 과매도")
                if price_near_lower_band: reasons.append("볼린저 밴드 하단")
                if near_support: reasons.append("지지선 근처")
                if is_golden_cross: reasons.append("골든 크로스")
                if macd_cross_up: reasons.append("MACD 상향돌파")
                if momentum_turning_up: reasons.append("모멘텀 상승전환")
                if volume_increase: reasons.append("거래량 증가")
                if bullish_candle: reasons.append("강세 캔들 패턴")
                if consecutive_drop: reasons.append("연속 하락 후 반등 기대")
                
                # 상승장에서의 추가 매수 이유
                if current_market_env == "uptrend":
                    if fresh_golden_cross: reasons.append("골든크로스 직후")
                    if analysis_result["signals"]["daily"].get("ma_aligned", False): reasons.append("이동평균선 정배열")
                    if analysis_result["signals"]["daily"].get("price_uptrend", False): reasons.append("가격 상승 추세")
                    if analysis_result["signals"]["daily"].get("volume_trend", False): reasons.append("거래량 증가 추세")
                
                analysis_result["reason"] = "매수 시그널: " + ", ".join(reasons)
            
            # 점수 기반 정렬을 위한 Score 계산
            score = daily_signals_count * 2  # 기본 점수
            
            # 상승장 특화 점수 추가
            if current_market_env == "uptrend":
                if fresh_golden_cross: score += 4  # 골든크로스 직후에 높은 가중치
                if analysis_result["signals"]["daily"].get("ma_aligned", False): score += 2  # 이동평균선 정배열
                if analysis_result["signals"]["daily"].get("price_uptrend", False): score += 2  # 가격 상승 추세
                if analysis_result["signals"]["daily"].get("volume_trend", False): score += 2  # 거래량 증가 추세
                score += analysis_result.get("uptrend_score", 0)  # 상승장 특화 점수 추가
            
            analysis_result["score"] = score
            
            return analysis_result

        except Exception as e:
            logger.warning(f"종목 {stock_code} 백테스트 분석 중 오류: {str(e)}")
            return {"is_buy_signal": False, "reason": f"분석 오류: {str(e)}"}


    def _analyze_stock_for_backtest(self, stock_code: str, daily_data: pd.DataFrame, current_idx: int, current_market_env: str) -> Dict[str, any]:
        """백테스트용 종목 분석 함수
        
        Args:
            stock_code: 종목코드
            daily_data: 일봉 데이터
            current_idx: 현재 데이터 인덱스
            current_market_env: 현재 시장 환경
            
        Returns:
            Dict: 분석 결과
        """
        try:
            # 종목 기본 정보
            stock_name = self.watch_list_info.get(stock_code, {}).get("name", stock_code)
            current_price = daily_data.iloc[current_idx]['close']
            
            # 분석 결과 초기화
            analysis_result = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "current_price": current_price,
                "is_buy_signal": False,
                "signals": {
                    "daily": {},
                },
                "technical_data": {
                    "rsi": daily_data['RSI'].iloc[current_idx] if 'RSI' in daily_data.columns else None,
                    "macd": daily_data['MACD'].iloc[current_idx] if 'MACD' in daily_data.columns else None,
                    "macd_signal": daily_data['Signal'].iloc[current_idx] if 'Signal' in daily_data.columns else None,
                    "ma5": daily_data['MA5'].iloc[current_idx] if 'MA5' in daily_data.columns else None,
                    "ma20": daily_data['MA20'].iloc[current_idx] if 'MA20' in daily_data.columns else None,
                    "ma60": daily_data['MA60'].iloc[current_idx] if 'MA60' in daily_data.columns else None,
                    "atr": daily_data['ATR'].iloc[current_idx] if 'ATR' in daily_data.columns else None
                }
            }
            
            # 동적 손절가 계산
            if 'ATR' in daily_data.columns and not pd.isna(daily_data['ATR'].iloc[current_idx]):
                current_atr = daily_data['ATR'].iloc[current_idx]
                dynamic_stop_loss = current_price - (current_atr * self.atr_multiplier)
                analysis_result["technical_data"]["dynamic_stop_loss"] = dynamic_stop_loss
            
            # 시장 환경에 따른 파라미터 조정
            rsi_threshold_adjusted = self.rsi_oversold
            custom_profit_target = self.profit_target
            custom_stop_loss = self.stop_loss
            
            if current_market_env == "uptrend":
                # 상승장: RSI 임계값 완화, 목표 수익률 증가
                rsi_threshold_adjusted = min(self.rsi_oversold + 5, 35)
                custom_profit_target = self.profit_target * 1.5
                custom_stop_loss = self.stop_loss * 0.8
            elif current_market_env == "downtrend":
                # 하락장: RSI 임계값 강화, 목표 수익률 감소, 손절 강화
                rsi_threshold_adjusted = max(self.rsi_oversold - 5, 20)
                custom_profit_target = self.profit_target * 0.8
                custom_stop_loss = self.stop_loss * 0.6
            
            # 조정된 파라미터 저장
            analysis_result["adjusted_parameters"] = {
                "profit_target": custom_profit_target,
                "stop_loss": custom_stop_loss,
                "rsi_threshold": rsi_threshold_adjusted
            }
            
            # 1. RSI 과매도 확인
            rsi_value = daily_data['RSI'].iloc[current_idx] if 'RSI' in daily_data.columns else None
            is_oversold = rsi_value is not None and rsi_value <= rsi_threshold_adjusted
            analysis_result["signals"]["daily"]["rsi_oversold"] = is_oversold
            
            # 2. 골든 크로스 확인
            is_golden_cross = False
            if current_idx > 0 and 'MA5' in daily_data.columns and 'MA20' in daily_data.columns:
                if daily_data['MA5'].iloc[current_idx-1] < daily_data['MA20'].iloc[current_idx-1] and \
                daily_data['MA5'].iloc[current_idx] >= daily_data['MA20'].iloc[current_idx]:
                    is_golden_cross = True
            analysis_result["signals"]["daily"]["golden_cross"] = is_golden_cross
            
            # 3. MACD 상향돌파 확인
            macd_cross_up = False
            if current_idx > 0 and 'MACD' in daily_data.columns and 'Signal' in daily_data.columns:
                if daily_data['MACD'].iloc[current_idx-1] < daily_data['Signal'].iloc[current_idx-1] and \
                daily_data['MACD'].iloc[current_idx] >= daily_data['Signal'].iloc[current_idx]:
                    macd_cross_up = True
            analysis_result["signals"]["daily"]["macd_cross_up"] = macd_cross_up
            
            # 4. 볼린저 밴드 하단 접촉
            price_near_lower_band = False
            if 'LowerBand' in daily_data.columns:
                price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[current_idx] * 1.01
            analysis_result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
            
            # 5. 모멘텀 상승 전환
            momentum_turning_up = False
            if current_idx >= 3:
                # 최근 3일간 상승 추세 확인
                try:
                    close_prices = daily_data['close'].iloc[current_idx-2:current_idx+1]
                    momentum_turning_up = close_prices.is_monotonic_increasing
                except:
                    momentum_turning_up = False
            analysis_result["signals"]["daily"]["momentum_turning_up"] = momentum_turning_up
            
            # 6. 거래량 증가 확인
            volume_increase = False
            if 'volume' in daily_data.columns and current_idx >= 10:
                try:
                    avg_volume = daily_data['volume'].iloc[current_idx-10:current_idx].mean()
                    current_volume = daily_data['volume'].iloc[current_idx]
                    volume_increase = current_volume > avg_volume * 1.5
                except:
                    volume_increase = False
            analysis_result["signals"]["daily"]["volume_increase"] = volume_increase
            
            # 7. 캔들 패턴 확인 (강세 캔들)
            bullish_candle = False
            try:
                open_price = daily_data['open'].iloc[current_idx]
                close_price = current_price
                high_price = daily_data['high'].iloc[current_idx]
                low_price = daily_data['low'].iloc[current_idx]
                
                # 양봉 확인
                if close_price > open_price:
                    body_size = close_price - open_price
                    candle_range = high_price - low_price
                    
                    if body_size > candle_range * 0.5:
                        bullish_candle = True
                
                # 망치형 확인
                if not bullish_candle:
                    if close_price > open_price:  # 양봉
                        body_size = close_price - open_price
                        lower_shadow = open_price - low_price
                        
                        if lower_shadow > body_size * 2 and body_size > 0:
                            bullish_candle = True
                    else:  # 음봉
                        body_size = open_price - close_price
                        lower_shadow = close_price - low_price
                        
                        if lower_shadow > body_size * 2 and body_size > 0:
                            bullish_candle = True
            except:
                bullish_candle = False
            analysis_result["signals"]["daily"]["bullish_candle"] = bullish_candle
            
            # 8. 연속 하락 확인
            consecutive_drop = False
            if current_idx >= 3:
                try:
                    prices = daily_data['close'].iloc[current_idx-3:current_idx]
                    drops = [prices.iloc[i] < prices.iloc[i-1] for i in range(1, len(prices))]
                    consecutive_drop = all(drops)
                except:
                    consecutive_drop = False
            analysis_result["signals"]["daily"]["consecutive_drop"] = consecutive_drop
            
            # 시장 환경별 추가 조건
            additional_condition = True
            
            if current_market_env == "downtrend":
                # 하락장에서는 안전한 매수 시점 추가 확인
                deep_oversold = rsi_value is not None and rsi_value < 25.0
                volume_surge = volume_increase and daily_data['volume'].iloc[current_idx] > daily_data['volume'].iloc[current_idx-10:current_idx].mean() * 2.0
                
                is_safe_entry = deep_oversold and (volume_surge or bullish_candle)
                additional_condition = is_safe_entry
                analysis_result["signals"]["daily"]["safe_entry"] = is_safe_entry
            
            elif current_market_env == "uptrend":
                # 상승장에서는 상승 추세 종목 우선 체크
                in_uptrend = False
                
                if 'MA5' in daily_data.columns and 'MA20' in daily_data.columns and 'MA60' in daily_data.columns:
                    ma5 = daily_data['MA5'].iloc[current_idx]
                    ma20 = daily_data['MA20'].iloc[current_idx]
                    ma60 = daily_data['MA60'].iloc[current_idx]
                    
                    if not pd.isna(ma5) and not pd.isna(ma20) and not pd.isna(ma60):
                        in_uptrend = ma5 > ma20 > ma60
                
                # 상승장에서는 추가 조건 완화
                additional_condition = in_uptrend or (is_oversold and (is_golden_cross or macd_cross_up))
                analysis_result["signals"]["daily"]["in_uptrend"] = in_uptrend
            
            # 매수 시그널 평가: 점수 기반 시스템
            score = 0
            score_weights = self.score_weights
            
            # 일봉 시그널 점수
            if is_oversold: 
                score += score_weights.get("rsi_oversold", 3)
            if is_golden_cross: 
                score += score_weights.get("golden_cross", 2)
            if macd_cross_up: 
                score += score_weights.get("macd_cross_up", 3)
            if price_near_lower_band: 
                score += score_weights.get("near_lower_band", 2)
            if momentum_turning_up: 
                score += score_weights.get("momentum_turning_up", 1)
            if volume_increase:
                score += score_weights.get("volume_increase", 3)
            if bullish_candle:
                score += score_weights.get("bullish_candle", 2)
            if consecutive_drop:
                score += score_weights.get("consecutive_drop", 2)
            
            # 시장 환경 추가 점수
            if current_market_env == "uptrend" and analysis_result["signals"]["daily"].get("in_uptrend", False):
                score += 2  # 상승장에서 상승추세 종목에 가산점
            
            # 섹터 강도 점수
            sector_code = self.watch_list_info.get(stock_code, {}).get("sector_code")
            if sector_code and self.use_sector_filter:
                sector_strength_ok = self.check_sector_strength(sector_code)
                if sector_strength_ok:
                    score += score_weights.get("sector_strength", 3)
                    analysis_result["signals"]["daily"]["sector_strength"] = True
            
            analysis_result["score"] = score
            
            # 최종 매수 시그널 결정 (시장 환경 고려)
            # 일봉 시그널 강화: 2개 이상의 조건 동시 충족 요구
            daily_signals_count = sum([
                is_oversold,              # RSI 과매도
                price_near_lower_band,    # 볼린저 밴드 하단
                is_golden_cross,          # 골든 크로스
                macd_cross_up,            # MACD 상향돌파
                momentum_turning_up,      # 모멘텀 상승전환
                volume_increase,          # 거래량 증가
                bullish_candle,           # 강세 캔들 패턴
                consecutive_drop          # 연속 하락 후 반등 가능성
            ])
            
            # 일봉에서 최소 2개 이상의 매수 시그널이 동시에 발생해야 함
            # RSI 과매도는 거의 필수 조건으로 유지
            daily_buy_signal = is_oversold and daily_signals_count >= 2
            
            # 시장 환경별 추가 조건 적용
            buy_signal = daily_buy_signal and additional_condition
            
            # 최종 매수 시그널 설정
            analysis_result["is_buy_signal"] = buy_signal
            
            # 매수 이유 상세화
            if buy_signal:
                reasons = []
                if is_oversold: reasons.append("RSI 과매도")
                if price_near_lower_band: reasons.append("볼린저 밴드 하단")
                if is_golden_cross: reasons.append("골든 크로스")
                if macd_cross_up: reasons.append("MACD 상향돌파")
                if momentum_turning_up: reasons.append("모멘텀 상승전환")
                if volume_increase: reasons.append("거래량 증가")
                if bullish_candle: reasons.append("강세 캔들 패턴")
                if consecutive_drop: reasons.append("연속 하락 후 반등 기대")
                
                analysis_result["reason"] = ", ".join(reasons)
            
            # 시장 환경에 따른 조정된 매매 파라미터 추가
            if buy_signal:
                analysis_result["use_parameters"] = {
                    "profit_target": custom_profit_target,
                    "stop_loss": custom_stop_loss
                }
            
            return analysis_result

        except Exception as e:
            logger.warning(f"종목 {stock_code} 백테스트 분석 중 오류: {str(e)}")
            return {"is_buy_signal": False, "reason": f"분석 오류: {str(e)}"}

# 추세 필터 클래스 추가
class TrendFilter:
    """시장 및 일봉 추세 필터 클래스"""
    @staticmethod
    def check_market_trend(market_index_code: str, lookback_days: int = 10) -> bool:
        """시장 추세 확인 (지수 또는 대표 ETF 기반)
        
        Args:
            market_index_code: 시장 지수 또는 ETF 코드 (예: KODEX 200 - 069500)
            lookback_days: 확인할 기간(일)
            
        Returns:
            bool: 상승 추세 여부
        """
        try:
            # 지수 또는 ETF 데이터 가져오기
            market_data = KisKR.GetOhlcvNew(market_index_code, 'D', lookback_days+5, adj_ok=1)
            
            if market_data is None or market_data.empty:
                logger.warning(f"시장 지수 데이터({market_index_code})를 가져올 수 없습니다.")
                return True  # 데이터 없으면 기본적으로 매수 허용
            
            # 이동평균선 계산 (5일)
            market_data['MA5'] = market_data['close'].rolling(window=5).mean()
            
            # 추세 확인 - 최근 종가가 5일 이평선 위에 있고, 5일 이평선이 상승 추세인지
            if len(market_data) < 5:
                return True
                
            recent_ma5 = market_data['MA5'].iloc[-1]
            prev_ma5 = market_data['MA5'].iloc[-2]
            recent_close = market_data['close'].iloc[-1]
            
            # 종가가 5일선 위에 있고, 5일선이 상승 중이면 상승 추세로 판단
            is_uptrend = (recent_close > recent_ma5) and (recent_ma5 > prev_ma5)
            
            return is_uptrend
        
        except Exception as e:
            logger.exception(f"시장 추세 확인 중 오류: {str(e)}")
            return True  # 오류 발생 시 기본적으로 매수 허용

    @staticmethod
    def check_daily_trend(data: pd.DataFrame, lookback_days: int = 5) -> bool:
        """종목의 일봉 추세 확인
        
        Args:
            data: 일봉 데이터
            lookback_days: 확인할 기간(일)
            
        Returns:
            bool: 상승 추세 여부
        """
        try:
            if data is None or data.empty or len(data) < lookback_days:
                return True  # 데이터 부족시 기본적으로 매수 허용
            
            # 최근 n일 데이터 추출
            recent_data = data.iloc[-lookback_days:]
            
            # 종가 기준 방향성 확인
            first_close = recent_data['close'].iloc[0]
            last_close = recent_data['close'].iloc[-1]
            
            # 히스토그램 방향성 확인 (MACD 히스토그램이 최근 상승 중인지)
            has_macd = 'Histogram' in recent_data.columns
            
            # MACD 히스토그램이 있고 상승중인지 확인
            if has_macd:
                histogram_direction = recent_data['Histogram'].diff().iloc[-1] > 0
            else:
                histogram_direction = True  # 데이터 없으면 기본적으로 통과
            
            # 가격 상승 + 히스토그램 상승이면 상승 추세로 판단
            return (last_close > first_close) and histogram_direction
            
        except Exception as e:
            logger.exception(f"일봉 추세 확인 중 오류: {str(e)}")
            return True  # 오류 발생 시 기본적으로 매수 허용

def get_sector_info(stock_code):
    """네이버 금융을 통한 섹터 정보 조회"""
    try:
        logger.info(f"\n네이버 금융 조회 시작 (종목코드: {stock_code})...")
        
        # 네이버 금융 종목 페이지
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # 한글 깨짐 방지
            response.encoding = 'euc-kr'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 업종 정보 찾기
            industry_element = soup.select_one('#content > div.section.trade_compare > h4 > em > a')
            if industry_element:
                sector = industry_element.get_text(strip=True)
                logger.info(f"네이버 금융에서 업종 정보를 찾았습니다: {sector}")
                
                # 시장 구분 찾기
                market = "Unknown"
                for mkt in ["KOSPI", "KOSDAQ"]:
                    try:
                        if stock_code in stock.get_market_ticker_list(market=mkt):
                            market = mkt
                            break
                    except Exception:
                        continue
                
                return {
                    'sector': sector,
                    'industry': sector,
                    'market': market
                }
            else:
                logger.info("업종 정보를 찾을 수 없습니다.")
        else:
            logger.info(f"네이버 금융 접속 실패. 상태 코드: {response.status_code}")
            
        return {
            'sector': 'Unknown',
            'industry': 'Unknown',
            'market': 'Unknown'
        }
        
    except Exception as e:
        logger.info(f"섹터 정보 조회 중 에러: {str(e)}")
        return {
            'sector': 'Unknown',
            'industry': 'Unknown',
            'market': 'Unknown'
        }

# 업종 동향 분석 함수 - 모듈 레벨에 위치
def analyze_sector_trend(stock_code, min_sector_stocks=2):
    """
    업종 동향 상세 분석 - 캐시 적용
    """
    try:
        # 기존 섹터 정보 활용
        sector_info = get_sector_info(stock_code)
        if not sector_info or sector_info['sector'] == 'Unknown':
            return False, "섹터 정보 없음"
            
        # 동일 업종 종목들의 현재가 조회
        sector_stocks = stock.get_market_ticker_list(market="ALL")
        sector_prices = {}
        
        for ticker in sector_stocks[:50]:  # 시가총액 상위 50개만
            try:
                current_price = KisKR.GetCurrentPrice(ticker)
                prev_close = KisKR.GetStockPrevClose(ticker)
                if current_price and prev_close:
                    sector_prices[ticker] = {
                        'change_rate': (current_price - prev_close) / prev_close * 100
                    }
            except:
                continue
                
        if len(sector_prices) < min_sector_stocks:
            return False, "업종 데이터 부족"
            
        # 업종 강도 분석
        rising_count = sum(1 for data in sector_prices.values() 
                         if data['change_rate'] > 0)
        avg_change = sum(data['change_rate'] for data in sector_prices.values()) / len(sector_prices)
        
        # 업종 동향 판단
        is_sector_strong = (
            rising_count / len(sector_prices) > 0.3 or  # 30% 이상 상승
            avg_change > 0 or                           # 평균 상승
            rising_count >= min_sector_stocks            # 최소 종목 수 만족
        )
        
        return is_sector_strong, {
            'rising_ratio': rising_count / len(sector_prices),
            'avg_change': avg_change
        }
        
    except Exception as e:
        logger.error(f"업종 분석 중 에러: {str(e)}")
        return False, str(e)

# 설정파일 생성 함수
def create_config_file(config_path: str = "trend_trader_config.json") -> None:
    """기본 설정 파일 생성 - 하드코딩 없이 구현
    
    Args:
        config_path: 설정 파일 경로
    """
    try:
        logger.info("기본 설정 파일 생성 시작...")
        
        # 대표 지수/종목 코드
        sample_codes = [
            "000660",  # SK하이닉스
            "207940",  # 삼성바이오로직스
            "006400",  # 삼성SDI
            "051910",  # LG화학
            "035900",  # JYP Ent.
            "293490"   # 카카오게임즈
        ]
        
        # 이미 정의된 섹터 정보 함수 활용
        watch_list = []
        unique_sectors = set()
        
        logger.info("종목 및 섹터 정보 수집 중...")
        
        for stock_code in sample_codes:
            try:
                # 기존 get_sector_info 함수 활용
                sector_info = get_sector_info(stock_code)
                
                # 종목명 가져오기 (KIS API 활용)
                stock_name = "Unknown"
                try:
                    stock_status = KisKR.GetCurrentStatus(stock_code)
                    if stock_status and isinstance(stock_status, dict):
                        stock_name = stock_status.get("StockName", "Unknown")
                except:
                    pass
                
                if stock_name == "Unknown":
                    # KIS API로 이름을 가져오지 못한 경우 기본값 사용
                    stock_name = f"{stock_code} 종목"
                
                # 종목 정보 추가
                allocation_ratio = round(1.0 / len(sample_codes), 2)  # 균등 배분
                watch_list.append({
                    "code": stock_code,
                    "name": stock_name,
                    "sector_code": sector_info.get('sector', 'Unknown'),
                    "allocation_ratio": allocation_ratio,
                    "stop_loss": -2.0,
                    "trailing_stop_pct": 1.8
                })
                
                # 섹터 추적
                if sector_info.get('sector') != 'Unknown':
                    unique_sectors.add(sector_info.get('sector'))
                
                logger.info(f"종목 정보 추가: {stock_code} ({stock_name}) - 업종: {sector_info.get('sector', 'Unknown')}")
                
                # 연속 요청 방지
                time.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"종목 {stock_code} 정보 수집 중 오류: {str(e)}")
        
        # 섹터 리스트 구성 (ETF 매핑 없이)
        sector_list = []
        for sector in unique_sectors:
            sector_list.append({
                "code": sector,
                "allocation_ratio": round(1.0 / len(unique_sectors), 2)  # 균등 배분
            })
        
        # 기본 설정 구성
        config = {
            "watch_list": watch_list,
            "sector_list": sector_list,
            "total_budget": 5000000,
            "profit_target": 5.0,
            "stop_loss": -1.5,
            "max_stocks": 4,
            "min_trading_amount": 300000,
            "trading_strategies": {
                # RSI 관련 설정
                "rsi_oversold_threshold": 28.0,
                "rsi_overbought_threshold": 68.0,
                
                # MACD 관련 설정
                "macd_fast_period": 10,
                "macd_slow_period": 24,
                "macd_signal_period": 8,
                
                # 트레일링 스탑 관련 설정
                "use_trailing_stop": True,
                "trailing_stop_pct": 1.5,
                
                # 추세 필터 관련 설정
                "use_daily_trend_filter": True,
                "use_market_trend_filter": True,
                "market_index_code": "069500",  # KODEX 200 ETF
                "daily_trend_lookback": 3,
                
                # 섹터 필터 설정
                "use_sector_filter": True,
                
                # 섹터 자동 조회 설정
                "use_auto_sector_lookup": True,
                "auto_sector_lookup_interval": 7,
                
                # ATR 관련 설정
                "use_dynamic_stop": True,
                "atr_period": 10,
                "atr_multiplier": 1.5,
                
                # 분할 매수 관련 설정
                "use_split_purchase": True,
                "initial_purchase_ratio": 0.30,
                "additional_purchase_ratios": [0.30, 0.30, 0.10],
                "additional_purchase_drop_pct": [1.5, 3.0, 5.0],
                
                # 볼린저 밴드 관련 설정
                "bollinger_period": 18,
                "bollinger_std": 2.0,
                
                # 이동평균선 관련 설정
                "short_ma_period": 5,
                "mid_ma_period": 20,
                "long_ma_period": 60,
                
                # 부분 익절 전략
                "use_partial_profit": True,
                "partial_profit_target": 3.0,
                "partial_profit_ratio": 0.5,
                
                # 시간 필터
                "use_time_filter": True,
                "avoid_trading_hours": ["09:00-10:00", "14:30-15:30"],
                
                # 연속 하락일 필터
                "use_consecutive_drop_filter": True,
                "consecutive_drop_days": 2,
                
                # 확인 주기 설정
                "check_interval_seconds": 1800,
                
                # 매수 점수 가중치
                "score_weights": {
                    "rsi_oversold": 4,
                    "golden_cross": 2,
                    "macd_cross_up": 4,
                    "near_lower_band": 3,
                    "momentum_turning_up": 2,
                    "near_support": 3,
                    "minute_rsi_oversold": 2,
                    "minute_macd_cross_up": 2,
                    "consecutive_drop": 2,
                    "volume_increase": 3,
                    "bullish_candle": 2,
                    "sector_strength": 3
                },
                
                # 매수 필터 강화 설정
                "required_daily_signals": 2,
                "required_minute_signals": 2,
                
                # 뉴스 필터 설정
                "use_news_filter": False
            }
        }
        
        # API 정보 항목 추가 (빈 값)
        config["api_key"] = ""
        config["api_secret"] = ""
        config["account_number"] = ""
        config["account_code"] = ""
        
        # 현재 날짜 추가 (섹터 정보 업데이트 트래킹용)
        config["last_sector_update"] = datetime.datetime.now().strftime("%Y%m%d")
        
        # 설정 파일 저장
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"기본 설정 파일 생성 완료: {config_path}")
        logger.info(f"수집된 종목 수: {len(watch_list)}, 섹터 수: {len(sector_list)}")
        logger.info(f"API 정보 확인이 필요한 경우 {config_path} 파일에 추가 정보를 입력하세요.")
        
    except Exception as e:
        logger.exception(f"설정 파일 생성 중 오류: {str(e)}")
        raise  # 예외를 다시 발생시켜 호출자에게 알림

# 메인 함수
def main():
    """메인 함수"""
    # API 모드 설정 (실제 계좌 사용)
    try:
        Common.SetChangeMode("REAL")  # REAL 모드로 설정
        logger.info("실제 계좌(REAL) 모드로 설정되었습니다.")
    except Exception as e:
        logger.warning(f"API 모드 설정 중 오류: {e}")
        logger.info("기본 모드를 사용합니다.")
    
    # 설정 파일 존재 확인 및 생성
    config_path = "trend_trader_config.json"
    if not os.path.exists(config_path):
        create_config_file(config_path)
        logger.info(f"API 정보 확인이 필요한 경우 {config_path} 파일에 추가 정보를 입력하세요.")
    
    # 매매봇 인스턴스 생성
    trend_bot = TrendTraderBot(config_path)
    
    # 실행 모드 선택
    if len(sys.argv) > 1:
        # 백테스트 모드
        if sys.argv[1] == "backtest":
            # 백테스트 기간 설정
            start_date = sys.argv[2] if len(sys.argv) > 2 else (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y%m%d")
            end_date = sys.argv[3] if len(sys.argv) > 3 else None
            
            # 적응형 백테스트 여부
            adaptive = "--adaptive" in sys.argv
            reset = "--reset" in sys.argv
            
            if adaptive:
                logger.info(f"적응형 백테스트 모드 실행: {start_date} ~ {end_date or '현재'}")
                results = trend_bot.run_adaptive_backtest(start_date, end_date, reset_strategy=reset)
                
                # 결과 분석 및 시각화
                analysis = trend_bot.analyze_adaptive_backtest_results(results)
                trend_bot.visualize_adaptive_backtest(
                    analysis, 
                    output_file=f"adaptive_backtest_viz_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                )
            else:
                logger.info(f"일반 백테스트 모드 실행: {start_date} ~ {end_date or '현재'}")
                results = trend_bot.run_backtest(start_date, end_date)
            
            # 백테스트 결과 저장
            results_file = f"backtest_result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                # default=str 옵션 추가 - 모든 직렬화 불가능한 객체를 문자열로 변환
                json.dump(results, f, ensure_ascii=False, indent=4, default=str)            
                
            logger.info(f"백테스트 결과 저장 완료: {results_file}")

        # 백테스트 분석 모드
        elif sys.argv[1] == "analyze-backtest":
            if len(sys.argv) < 3:
                logger.error("분석할 백테스트 결과 파일을 지정해주세요.")
                return
                
            backtest_file = sys.argv[2]
            output_file = f"backtest_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            logger.info(f"백테스트 결과 분석 시작: {backtest_file}")
            trend_bot.find_optimal_strategy_parameters(backtest_file, output_file)
            
        # 최적 전략 적용 모드
        elif sys.argv[1] == "apply-optimal":
            if len(sys.argv) < 3:
                optimal_file = "optimal_adaptive_strategy.json"
            else:
                optimal_file = sys.argv[2]
                
            logger.info(f"최적 전략 적용 시작: {optimal_file}")
            trend_bot.apply_optimal_strategy_from_backtest(optimal_file)
            
        # 증분 백테스트 모드
        elif sys.argv[1] == "incremental-backtest":
            days = 30
            if len(sys.argv) >= 3:
                try:
                    days = int(sys.argv[2])
                except:
                    pass
                
            apply_results = "--no-apply" not in sys.argv
            
            logger.info(f"증분 백테스트 시작: 최근 {days}일, 결과 적용: {apply_results}")
            trend_bot.run_incremental_backtest(days, apply_results)

        elif sys.argv[1] == "virtual":
            # 가상 계좌 모드로 변경
            try:
                Common.SetChangeMode("VIRTUAL")
                logger.info("모의 계좌(VIRTUAL) 모드로 설정되었습니다.")
            except Exception as e:
                logger.error(f"모의 계좌 모드 설정 실패: {e}")
                return
                
            # 실시간 매매 모드
            logger.info("모의 계좌 매매 모드 실행")
            
            # 장 중인지 확인
            if KisKR.IsMarketOpen():
                logger.info("장 중입니다. 매매봇을 실행합니다.")
                trend_bot.run()
            else:
                logger.info("현재 장 중이 아닙니다. 매매봇을 종료합니다.")
        else:
            logger.error(f"알 수 없는 실행 모드: {sys.argv[1]}")
    else:
        # 실시간 매매 모드
        logger.info("실시간 매매 모드 실행")
        
        # 장 중인지 확인
        if KisKR.IsMarketOpen():
            logger.info("장 중입니다. 매매봇을 실행합니다.")
            trend_bot.run()
        else:
            logger.info("현재 장 중이 아닙니다. 매매봇을 종료합니다.")


if __name__ == "__main__":
    main()