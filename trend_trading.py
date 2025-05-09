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
import datetime
import numpy as np
import pandas as pd
import random  # 여기에 random 모듈 추가
from typing import List, Dict, Tuple, Optional, Union

# KIS API 함수 임포트
import KIS_Common as Common
import KIS_API_Helper_KR as KisKR

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"trend_trading_{datetime.datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TrendTrader")

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
        
        self.holdings = {}  # 보유 종목 정보
        self.last_check_time = {}  # 마지막 검사 시간

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

    def _save_holdings(self) -> None:
        """보유 종목 정보 저장"""
        try:
            with open("holdings.json", 'w', encoding='utf-8') as f:
                json.dump(self.holdings, f, ensure_ascii=False, indent=4)
            logger.info("보유 종목 정보 저장 완료")
        except Exception as e:
            logger.exception(f"보유 종목 정보 저장 중 오류: {str(e)}")


    def analyze_stock(self, stock_code: str) -> Dict[str, any]:
        """종목 분석
        
        Args:
            stock_code: 종목코드
            
        Returns:
            Dict: 분석 결과
        """
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
            daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(daily_data)
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
                    atr_multiplier = self.config.get("trading_strategies", {}).get("atr_multiplier")
                    dynamic_stop_loss = self.tech_indicators.calculate_dynamic_stop_loss(
                        current_price, current_atr, atr_multiplier
                    )
                    analysis_result["technical_data"]["dynamic_stop_loss"] = dynamic_stop_loss

            # 일봉 기반 매수 시그널 확인
            if not daily_data.empty:
                # 1. RSI 과매도 확인 (커스텀 임계값 사용)
                rsi_value = daily_data['RSI'].iloc[-1]
                is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value, self.rsi_oversold)
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
            
            # 분봉 기반 매수 시그널 확인
            if minute_data is not None and not minute_data.empty:
                # 1. 분봉 RSI 과매도 확인 (커스텀 임계값 사용)
                minute_rsi_value = minute_data['RSI'].iloc[-1]
                minute_is_oversold = self.tech_indicators.is_oversold_rsi(minute_rsi_value, self.rsi_oversold)
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

            # 종합 매수 시그널 결정
            daily_buy_signal = is_oversold and (near_support or momentum_turning_up or is_golden_cross)
            minute_buy_signal = False
            
            if minute_data is not None and not minute_data.empty:
                minute_buy_signal = minute_is_oversold or minute_macd_cross_up
            
            # 기본 매수 시그널
            buy_signal = daily_buy_signal and minute_buy_signal
            
            # 추세 필터 적용 (설정에서 활성화된 경우)
            if buy_signal and self.config.get("trading_strategies", {}).get("use_daily_trend_filter", False):
                # 일봉 추세 확인
                daily_trend_ok = TrendFilter.check_daily_trend(daily_data)
                if not daily_trend_ok:
                    buy_signal = False
                    analysis_result["reason"] = "일봉 추세 불량"
            
            # 시장 추세 필터 적용 (설정에서 활성화된 경우)
            if buy_signal and self.config.get("trading_strategies", {}).get("use_market_trend_filter", False):
                market_index_code = self.config.get("trading_strategies", {}).get("market_index_code", "069500")
                market_trend_ok = TrendFilter.check_market_trend(market_index_code)
                if not market_trend_ok:
                    buy_signal = False
                    analysis_result["reason"] = "시장 추세 불량"
            
            # 최종 매수 시그널 설정
            analysis_result["is_buy_signal"] = buy_signal
            
            # 매수 이유 추가
            if buy_signal:
                analysis_result["reason"] = "저점 매수 시그널 발생"
            
            return analysis_result
        except Exception as e:
            logger.exception(f"종목 {stock_code} 분석 중 오류: {str(e)}")
            return {"is_buy_signal": False, "reason": f"분석 오류: {str(e)}"}

    # 트레일링 스탑 로직을 포함한 check_sell_signals 메서드
    def check_sell_signals(self) -> None:
        """보유 종목 매도 시그널 확인 (트레일링 스탑 포함)"""
        try:
            for stock_code, holding_info in list(self.holdings.items()):
                current_price = KisKR.GetCurrentPrice(stock_code)
                # 전략 관리 종목만 처리
                if not holding_info.get("is_strategy_managed", False):
                    continue

                if current_price is None or isinstance(current_price, str):
                    logger.warning(f"종목 {stock_code} 현재가를 조회할 수 없습니다.")
                    continue
                
                avg_price = holding_info.get("avg_price", 0)
                if avg_price <= 0:
                    logger.warning(f"종목 {stock_code} 평균단가가 유효하지 않습니다.")
                    continue
                
                # 수익률 계산
                profit_percent = ((current_price / avg_price) - 1) * 100
                
                # 트레일링 스탑 업데이트
                use_trailing_stop = self.config.get("trading_strategies", {}).get("use_trailing_stop", False)
                if use_trailing_stop:
                    # 현재가가 기존 최고가보다 높으면 최고가 및 트레일링 스탑 가격 업데이트
                    if current_price > holding_info.get("highest_price", 0):
                        trailing_pct = self.config.get("trading_strategies", {}).get("trailing_stop_pct", 2.0)
                        new_stop_price = current_price * (1 - trailing_pct/100)
                        
                        # 홀딩 정보 업데이트
                        self.holdings[stock_code]["highest_price"] = current_price
                        self.holdings[stock_code]["trailing_stop_price"] = new_stop_price
                        logger.info(f"트레일링 스탑 업데이트: {stock_code}, 최고가: {current_price:,}원, " +
                                f"스탑 가격: {new_stop_price:,}원")
                
                # 기술적 지표 기반 매도 조건 확인
                daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 30, adj_ok=1)
                
                sell_signal = False
                sell_reason = ""
                
                # 1. 목표 수익률 달성
                if profit_percent >= self.profit_target:
                    sell_signal = True
                    sell_reason = f"목표 수익률 달성: {profit_percent:.2f}%"
                
                # 2. 손절 조건
                elif profit_percent <= self.stop_loss:
                    sell_signal = True
                    sell_reason = f"손절 조건 발동: {profit_percent:.2f}%"
                
                # 3. 트레일링 스탑 조건
                elif use_trailing_stop and current_price < holding_info.get("trailing_stop_price", 0):
                    sell_signal = True
                    sell_reason = f"트레일링 스탑 발동: 최고가 {holding_info.get('highest_price'):,}원의 " + \
                                f"{self.config.get('trading_strategies', {}).get('trailing_stop_pct', 2.0)}% 하락"

                # ===== 여기에 동적 손절 코드 추가 =====
                # 동적 손절 적용
                use_dynamic_stop = holding_info.get("use_dynamic_stop", False)
                if use_dynamic_stop and holding_info.get("dynamic_stop_price", 0) > 0:
                    dynamic_stop_price = holding_info.get("dynamic_stop_price", 0)
                    
                    # 동적 손절 발동
                    if current_price <= dynamic_stop_price:
                        sell_signal = True
                        sell_reason = f"ATR 기반 동적 손절: {dynamic_stop_price:,}원"

                # 4. RSI 과매수 영역 (커스텀 임계값 사용)
                elif daily_data is not None and not daily_data.empty:
                    daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data)
                    rsi_value = daily_data['RSI'].iloc[-1]
                    
                    if self.tech_indicators.is_overbought_rsi(rsi_value, self.rsi_overbought):
                        sell_signal = True
                        sell_reason = f"RSI 과매수 영역: {rsi_value:.2f}"
                    
                    # 5. 데드 크로스
                    daily_data['MA5'] = daily_data['close'].rolling(window=5).mean()
                    daily_data['MA20'] = daily_data['close'].rolling(window=20).mean()
                    
                    if self.tech_indicators.is_death_cross(daily_data):
                        sell_signal = True
                        sell_reason = "5일선이 20일선을 하향돌파(데드 크로스)"
                    
                    # 6. MACD 하향 돌파
                    if not sell_signal:
                        daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                            daily_data, 
                            fast_period=self.macd_fast_period, 
                            slow_period=self.macd_slow_period, 
                            signal_period=self.macd_signal_period
                        )
                        
                        try:
                            if daily_data['MACD'].iloc[-2] > daily_data['Signal'].iloc[-2] and \
                            daily_data['MACD'].iloc[-1] < daily_data['Signal'].iloc[-1]:
                                sell_signal = True
                                sell_reason = "MACD 하향돌파"
                        except:
                            pass
                
                # 매도 시그널이 있으면 매도 주문
                if sell_signal:
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
        
        except Exception as e:
            logger.exception(f"매도 시그널 확인 중 오류: {str(e)}")


    # run 메서드 수정 - 최소 거래 금액 제한 및 분할 매수 적용
    def run(self) -> None:
        """매매봇 실행"""
        logger.info("한국주식 추세매매봇 시작")
        
        try:
            # 계좌 잔고 조회
            account_balance = KisKR.GetBalance()
            
            if not account_balance or isinstance(account_balance, str):
                logger.error(f"계좌 잔고 조회 오류: {account_balance}")
                return
                    
            available_cash = account_balance.get("RemainMoney", 0)
            
            logger.info(f"계좌 잔고: {available_cash:,}원")
            logger.info(f"보유 종목: {len(self.holdings)}개")
            logger.info(f"최대 보유 종목 수: {self.max_stocks}개")
            
            # 현재 보유 종목 수 확인
            current_holdings_count = len(self.holdings)
            
            # 매수 가능한 종목 수 확인
            available_slots = max(0, self.max_stocks - current_holdings_count)
            logger.info(f"추가 매수 가능 종목 수: {available_slots}개")
            
            # 관심종목 분석 및 매수 시그널 확인
            buy_candidates = []  # 매수 후보 종목 리스트
            
            for stock_code in self.watch_list:
                # 이미 보유 중인 종목 스킵
                if stock_code in self.holdings:
                    continue
                
                # 매수 가능 종목 수가 0이면 분석 중단
                if available_slots <= 0:
                    logger.info("최대 보유 종목 수에 도달하여 추가 매수 분석을 중단합니다.")
                    break
                
                # 최근 확인 시간 체크 (1시간에 한 번만 확인)
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
                    
                    # 분봉 시그널 점수
                    minute_signals = signals.get("minute", {})
                    if minute_signals.get("rsi_oversold", False): 
                        score += score_weights.get("minute_rsi_oversold", 1)
                    if minute_signals.get("macd_cross_up", False): 
                        score += score_weights.get("minute_macd_cross_up", 1)
                    
                    candidate["score"] = score
                
                # 점수 기준 내림차순 정렬
                buy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
                
                # 상위 종목부터 매수 시도
                for candidate in buy_candidates:
                    if available_slots <= 0:
                        break
                        
                    stock_code = candidate.get("stock_code")
                    stock_name = candidate.get("stock_name", stock_code)
                    current_price = candidate.get("current_price", 0)
                    
                    logger.info(f"매수 후보: {stock_code} ({stock_name}), 점수: {candidate.get('score', 0)}, 가격: {current_price:,}원")
                    logger.info(f"매수 이유: {candidate.get('reason', '')}")
                    
                    # 종목별 예산 배분 계산
                    stock_info = self.watch_list_info.get(stock_code, {})
                    # 수정 후:
                    allocation_ratio = stock_info.get("allocation_ratio", self.default_allocation_ratio)                    
                    # 예산 내에서 매수 수량 결정
                    allocated_budget = min(self.total_budget * allocation_ratio, available_cash)
                    
                    # 분할 매수 전략 적용
                    use_split = self.use_split_purchase
                    initial_ratio = self.initial_purchase_ratio

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
                                # 전략 관리 종목 표시
                                "is_strategy_managed": True
                            }
                            
                            # 트레일링 스탑 가격 설정
                            if self.use_trailing_stop:
                                self.holdings[stock_code]["trailing_stop_price"] = current_price * (1 - self.trailing_stop_pct/100)

                            self._save_holdings()
                            
                            # 사용 가능한 슬롯 감소
                            available_slots -= 1
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
                        logger.info(f"분할 매수 - 추가 매수 시도: {stock_code}, {add_quantity}주, 현재가: {current_price}원, 평단가: {avg_price}원, 수익률: {profit_percent:.2f}%")
                        
                        order_result = KisKR.MakeBuyMarketOrder(
                            stockcode=stock_code,
                            amt=add_quantity
                        )
                        
                        if not isinstance(order_result, str):
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
            
            # 매도 시그널 확인
            self.check_sell_signals()
            
            logger.info("매매봇 실행 완료")
        
        except Exception as e:
            logger.exception(f"매매봇 실행 중 오류: {str(e)}")

    def run_backtest(self, start_date: str, end_date: str = None) -> Dict[str, any]:
        """백테스트 실행
        
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
            "max_drawdown": 0
        }
        
        total_capital = self.total_budget
        virtual_holdings = {}
        trades = []
        
        # 나머지 백테스트 코드는 원래 코드를 유지하되, 일부 부분만 수정


    def run_backtest(self, start_date: str, end_date: str = None) -> Dict[str, any]:
        """백테스트 실행
        
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
            "max_drawdown": 0
        }
        
        total_capital = self.total_budget
        virtual_holdings = {}
        trades = []
        max_holdings_count = self.max_stocks  # 최대 동시 보유 종목 수 제한
        
        try:
            # 관심종목 반복
            for stock_code in self.watch_list:
                # 종목별 할당 비율 가져오기
                stock_info = self.watch_list_info.get(stock_code, {})
                allocation_ratio = stock_info.get("allocation_ratio", 0.2)  # 기본값 20%
                
                # 일봉 데이터 조회
                daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 200, adj_ok=1)
                
                if daily_data is None or daily_data.empty:
                    logger.warning(f"백테스트: 종목 {stock_code} 일봉 데이터가 없습니다.")
                    continue

                # 백테스트 기간에 해당하는 데이터만 필터링
                try:
                    # 로그 추가 - 필터링 전 데이터 정보
                    logger.info(f"종목 {stock_code} 전체 데이터 기간: {daily_data.index[0]} ~ {daily_data.index[-1]}")
                    logger.info(f"전체 데이터 개수: {len(daily_data)}")
                    
                    # 인덱스를 항상 datetime 형식으로 변환
                    if not isinstance(daily_data.index, pd.DatetimeIndex):
                        daily_data.index = pd.to_datetime(daily_data.index)
                    
                    # 필터링 날짜 형식 변환
                    if isinstance(start_date, str):
                        try:
                            # YYYYMMDD 형식 변환
                            if len(start_date) == 8:
                                start_date_dt = pd.to_datetime(start_date, format='%Y%m%d')
                            else:
                                start_date_dt = pd.to_datetime(start_date)
                        except:
                            # 변환 실패시 첫 날짜 사용
                            start_date_dt = daily_data.index[0]
                            logger.warning(f"시작일 형식 변환 실패, 첫 날짜({start_date_dt})로 대체")
                    else:
                        start_date_dt = start_date
                    
                    if isinstance(end_date, str):
                        try:
                            # YYYYMMDD 형식 변환
                            if len(end_date) == 8:
                                end_date_dt = pd.to_datetime(end_date, format='%Y%m%d')
                            else:
                                end_date_dt = pd.to_datetime(end_date)
                        except:
                            # 변환 실패시 마지막 날짜 사용
                            end_date_dt = daily_data.index[-1]
                            logger.warning(f"종료일 형식 변환 실패, 마지막 날짜({end_date_dt})로 대체")
                    else:
                        end_date_dt = end_date
                    
                    # 필터링 수행
                    mask = (daily_data.index >= start_date_dt) & (daily_data.index <= end_date_dt)
                    filtered_data = daily_data[mask].copy()
                    
                    # 필터링 결과 로그
                    logger.info(f"필터링된 데이터 개수: {len(filtered_data)}")
                    
                    # 필터링 결과가 비어있는 경우 확인
                    if filtered_data.empty:
                        logger.warning(f"백테스트: 종목 {stock_code} 지정된 기간({start_date_dt} ~ {end_date_dt}) 내 데이터가 없습니다.")
                        
                        # 해당 기간에 가까운 데이터가 있는지 확인 (옵션)
                        # 지정된 기간과 가장 가까운 30일치 데이터 사용
                        closest_date_idx = (daily_data.index - start_date_dt).abs().argmin()
                        start_idx = max(0, closest_date_idx - 15)
                        end_idx = min(len(daily_data) - 1, closest_date_idx + 15)
                        
                        if start_idx < end_idx:
                            filtered_data = daily_data.iloc[start_idx:end_idx+1].copy()
                            logger.info(f"가장 가까운 날짜의 데이터 사용: {filtered_data.index[0]} ~ {filtered_data.index[-1]}")
                        
                        if filtered_data.empty:
                            continue  # 그래도 비어있으면 다음 종목으로
                    
                except Exception as e:
                    logger.error(f"데이터 필터링 중 오류: {e}")
                    # 필터링 실패 시 원본 데이터 사용
                    filtered_data = daily_data.copy()
                    logger.warning(f"필터링 실패로 전체 데이터 사용: {len(filtered_data)}개")

                logger.info(f"종목 {stock_code} 백테스트 데이터 기간: {filtered_data.index[0]} ~ {filtered_data.index[-1]}")

                # 기술적 지표 계산 - 커스텀 파라미터 사용
                filtered_data['RSI'] = self.tech_indicators.calculate_rsi(filtered_data)
                filtered_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                    filtered_data,
                    fast_period=self.macd_fast_period,
                    slow_period=self.macd_slow_period,
                    signal_period=self.macd_signal_period
                )
                filtered_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(filtered_data)
                filtered_data['MA5'] = filtered_data['close'].rolling(window=5).mean()
                filtered_data['MA20'] = filtered_data['close'].rolling(window=20).mean()
                
                # 날짜별 시뮬레이션
                for i in range(20, len(filtered_data)):  # 지표 계산을 위해 20일 이후부터 시작
                    date = filtered_data.index[i]
                    current_price = filtered_data.iloc[i]['close']
                    
                    # 보유중인 종목인지 확인
                    if stock_code in virtual_holdings:
                        # 매도 조건 확인
                        avg_price = virtual_holdings[stock_code]["avg_price"]
                        profit_percent = ((current_price / avg_price) - 1) * 100
                        
                        # 1. 목표 수익률 달성
                        if profit_percent >= self.profit_target:
                            # 매도 실행
                            quantity = virtual_holdings[stock_code]["quantity"]
                            sell_amount = current_price * quantity
                            profit = sell_amount - (avg_price * quantity)
                            
                            # 자본 업데이트
                            total_capital += sell_amount
                            
                            # 거래 기록
                            trades.append({
                                "stock_code": stock_code,
                                "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                "action": "SELL",
                                "reason": f"목표 수익률 달성: {profit_percent:.2f}%",
                                "date": date,
                                "price": current_price,
                                "quantity": quantity,
                                "profit_loss": profit,
                                "profit_loss_percent": profit_percent
                            })
                            
                            # 보유 종목에서 제거
                            del virtual_holdings[stock_code]
                            
                        # 2. 손절 조건
                        elif profit_percent <= self.stop_loss:
                            # 매도 실행
                            quantity = virtual_holdings[stock_code]["quantity"]
                            sell_amount = current_price * quantity
                            profit = sell_amount - (avg_price * quantity)
                            
                            # 자본 업데이트
                            total_capital += sell_amount
                            
                            # 거래 기록
                            trades.append({
                                "stock_code": stock_code,
                                "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                "action": "SELL",
                                "reason": f"손절: {profit_percent:.2f}%",
                                "date": date,
                                "price": current_price,
                                "quantity": quantity,
                                "profit_loss": profit,
                                "profit_loss_percent": profit_percent
                            })
                            
                            # 보유 종목에서 제거
                            del virtual_holdings[stock_code]
                            
                        # 3. RSI 과매수 - 커스텀 임계값 사용
                        elif self.tech_indicators.is_overbought_rsi(filtered_data.iloc[i]['RSI'], self.rsi_overbought):
                            # 매도 실행
                            quantity = virtual_holdings[stock_code]["quantity"]
                            sell_amount = current_price * quantity
                            profit = sell_amount - (avg_price * quantity)
                            
                            # 자본 업데이트
                            total_capital += sell_amount
                            
                            # 거래 기록
                            trades.append({
                                "stock_code": stock_code,
                                "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                "action": "SELL",
                                "reason": f"RSI 과매수: {filtered_data.iloc[i]['RSI']:.2f}",
                                "date": date,
                                "price": current_price,
                                "quantity": quantity,
                                "profit_loss": profit,
                                "profit_loss_percent": profit_percent
                            })
                            
                            # 보유 종목에서 제거
                            del virtual_holdings[stock_code]
                            
                        # 4. MACD 하향돌파 확인
                        elif i > 0 and filtered_data.iloc[i-1]['MACD'] > filtered_data.iloc[i-1]['Signal'] and \
                            filtered_data.iloc[i]['MACD'] < filtered_data.iloc[i]['Signal']:
                            # 매도 실행
                            quantity = virtual_holdings[stock_code]["quantity"]
                            sell_amount = current_price * quantity
                            profit = sell_amount - (avg_price * quantity)
                            
                            # 자본 업데이트
                            total_capital += sell_amount
                            
                            # 거래 기록
                            trades.append({
                                "stock_code": stock_code,
                                "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                "action": "SELL",
                                "reason": "MACD 하향돌파",
                                "date": date,
                                "price": current_price,
                                "quantity": quantity,
                                "profit_loss": profit,
                                "profit_loss_percent": profit_percent
                            })
                            
                            # 보유 종목에서 제거
                            del virtual_holdings[stock_code]
                        
                    else:
                        # 최대 보유 종목 수 확인
                        if len(virtual_holdings) >= max_holdings_count:
                            continue
                            
                        # 매수 조건 확인
                        # 1. RSI 과매도 확인 - 커스텀 임계값 사용
                        rsi_value = filtered_data.iloc[i]['RSI']
                        is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value, self.rsi_oversold)
                        
                        # 2. 골든 크로스 확인
                        golden_cross = False
                        if i > 0 and filtered_data.iloc[i-1]['MA5'] < filtered_data.iloc[i-1]['MA20'] and \
                        filtered_data.iloc[i]['MA5'] >= filtered_data.iloc[i]['MA20']:
                            golden_cross = True
                        
                        # 3. 볼린저 밴드 하단 접촉
                        near_lower_band = current_price <= filtered_data.iloc[i]['LowerBand'] * 1.01
                        
                        # 4. MACD 상향돌파
                        macd_cross_up = False
                        if i > 0 and filtered_data.iloc[i-1]['MACD'] < filtered_data.iloc[i-1]['Signal'] and \
                        filtered_data.iloc[i]['MACD'] >= filtered_data.iloc[i]['Signal']:
                            macd_cross_up = True
                        
                        # 종합 매수 시그널
                        buy_signal = is_oversold and (near_lower_band or golden_cross or macd_cross_up)
                        
                        if buy_signal and total_capital > current_price:
                            # 종목별 할당 예산 계산
                            allocated_budget = self.total_budget * allocation_ratio
                            
                            # 예산 내에서 매수 수량 결정
                            max_available = min(allocated_budget, total_capital)
                            quantity = max(1, int(max_available / current_price))
                            
                            # 매수 실행
                            buy_amount = current_price * quantity
                            
                            if buy_amount <= total_capital:
                                # 자본 업데이트
                                total_capital -= buy_amount
                                
                                # 보유 종목에 추가
                                virtual_holdings[stock_code] = {
                                    "quantity": quantity,
                                    "avg_price": current_price,
                                    "buy_date": date
                                }
                                
                                # 거래 기록
                                buy_reason = ""
                                if is_oversold:
                                    buy_reason += "RSI 과매도, "
                                if near_lower_band:
                                    buy_reason += "볼린저 밴드 하단, "
                                if golden_cross:
                                    buy_reason += "골든 크로스, "
                                if macd_cross_up:
                                    buy_reason += "MACD 상향돌파, "
                                
                                trades.append({
                                    "stock_code": stock_code,
                                    "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
                                    "action": "BUY",
                                    "reason": buy_reason.rstrip(", "),
                                    "date": date,
                                    "price": current_price,
                                    "quantity": quantity,
                                    "amount": buy_amount
                                })
                
            # 백테스트 종료 시점에 보유중인 종목 청산
            for stock_code, holding in virtual_holdings.items():
                # 마지막 가격으로 청산
                daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 1, adj_ok=1)

                if daily_data is not None and not daily_data.empty:
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
                        "profit_loss_percent": profit_percent
                    })
            
            # 백테스트 결과 계산
            backtest_results["final_capital"] = total_capital
            backtest_results["profit_loss"] = total_capital - self.total_budget
            backtest_results["profit_loss_percent"] = (backtest_results["profit_loss"] / self.total_budget) * 100
            backtest_results["trades"] = trades
            
            # 승률 계산
            win_trades = [t for t in trades if t.get("action") == "SELL" and t.get("profit_loss", 0) > 0]
            loss_trades = [t for t in trades if t.get("action") == "SELL" and t.get("profit_loss", 0) <= 0]
            
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
                elif trade.get("action") == "SELL":
                    capital_history.append(capital_history[-1] + trade.get("price", 0) * trade.get("quantity", 0))
            
            max_capital = self.total_budget
            max_drawdown = 0
            
            for capital in capital_history:
                max_capital = max(max_capital, capital)
                drawdown = (max_capital - capital) / max_capital * 100
                max_drawdown = max(max_drawdown, drawdown)
            
            backtest_results["max_drawdown"] = max_drawdown
            
            # 추가: 종목별 성과 분석
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
                
                if trade.get("action") == "SELL":
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
            
            logger.info(f"백테스트 완료: 최종 자본금 {backtest_results['final_capital']:,.0f}원, " + 
                    f"수익률 {backtest_results['profit_loss_percent']:.2f}%, " +
                    f"승률 {backtest_results['win_rate']:.2f}%")
            
            return backtest_results
        
        except Exception as e:
            logger.exception(f"백테스트 실행 중 오류: {str(e)}")
            return backtest_results


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

# 설정파일 생성 함수
def create_config_file(config_path: str = "trend_trader_config.json") -> None:
    """기본 설정 파일 생성
    
    Args:
        config_path: 설정 파일 경로
    """
    config = {
        "watch_list": [
            # {"code": "005490", "name": "POSCO홀딩스", "allocation_ratio": 0.15, "stop_loss": -2.0, "trailing_stop_pct": 1.8},
            # {"code": "000660", "name": "SK하이닉스", "allocation_ratio": 0.20, "stop_loss": -2.0, "trailing_stop_pct": 1.5},
            # {"code": "000155", "name": "두산우", "allocation_ratio": 0.10, "stop_loss": -2.0, "trailing_stop_pct": 2.0},
            # {"code": "042660", "name": "한화오션", "allocation_ratio": 0.25, "stop_loss": -1.5, "trailing_stop_pct": 1.5},
            # {"code": "000100", "name": "유한양행", "allocation_ratio": 0.20, "stop_loss": -2.0, "trailing_stop_pct": 1.8},
            {"code": "028300", "name": "HLB", "allocation_ratio": 0.05, "stop_loss": -1.5, "trailing_stop_pct": 2.0}
            # {"code": "373220", "name": "LG에너지솔루션", "allocation_ratio": 0.05, "stop_loss": -1.8, "trailing_stop_pct": 1.8}
        ],
        "total_budget": 5000000,  # 총 투자 예산
        "profit_target": 5.0,     # 목표 수익률 (%)
        "stop_loss": -2.0,        # 기본 손절 비율 (%)
        "max_stocks": 4,          # 최대 동시 보유 종목 수 (5에서 4로 감소)
        "min_trading_amount": 300000,  # 최소 거래 금액
        "trading_strategies": {
            # RSI 관련 설정
            "rsi_oversold_threshold": 30.0,   # RSI 과매도 기준
            "rsi_overbought_threshold": 68.0, # RSI 과매수 기준
            
            # MACD 관련 설정
            "macd_fast_period": 10,   # MACD 빠른 이동평균
            "macd_slow_period": 24,   # MACD 느린 이동평균
            "macd_signal_period": 8,  # MACD 시그널 라인
            
            # 트레일링 스탑 관련 설정
            "use_trailing_stop": True,
            "trailing_stop_pct": 1.8,  # 기본 트레일링 스탑 비율(%)
            
            # 추세 필터 관련 설정
            "use_daily_trend_filter": True,
            "use_market_trend_filter": True,
            "market_index_code": "069500",  # KODEX 200 ETF
            "daily_trend_lookback": 3,      # 일일 추세 확인 기간
            
            # ATR 관련 설정
            "use_dynamic_stop": True,
            "atr_period": 10,         # ATR 계산 기간
            "atr_multiplier": 1.5,    # ATR 승수
            
            # 분할 매수 관련 설정
            "use_split_purchase": True,
            "initial_purchase_ratio": 0.50,  # 초기 매수 비율 (60%에서 50%로 감소)
            "additional_purchase_ratios": [0.30, 0.20],  # 2단계 추가 매수 비율
            "additional_purchase_drop_pct": [1.5, 3.0],  # 추가 매수 하락 기준(%)
            
            # 볼린저 밴드 관련 설정
            "bollinger_period": 18,   # 볼린저 밴드 기간
            "bollinger_std": 2.0,     # 볼린저 밴드 표준편차 배수
            
            # 이동평균선 관련 설정
            "short_ma_period": 5,     # 단기 이동평균선 기간
            "mid_ma_period": 20,      # 중기 이동평균선 기간
            "long_ma_period": 60,     # 장기 이동평균선 기간
            
            # 부분 익절 전략
            "use_partial_profit": True,    # 부분 익절 사용
            "partial_profit_target": 4.0,  # 4% 도달 시 부분 익절
            "partial_profit_ratio": 0.5,   # 50% 물량 부분 익절
            
            # 시간 필터
            "use_time_filter": True,
            "avoid_trading_hours": ["09:00-10:00", "14:30-15:30"],  # 장 초반과 후반 거래 회피
            
            # 연속 하락일 필터
            "use_consecutive_drop_filter": True,
            "consecutive_drop_days": 2,    # 2일 연속 하락 후 매수 고려
            
            # 매수 점수 가중치 (점수 기반 종목 선정에 사용)
            "score_weights": {
                "rsi_oversold": 3,         # RSI 과매도 가중치
                "golden_cross": 2,         # 골든 크로스 가중치
                "macd_cross_up": 3,        # MACD 상향돌파 가중치
                "near_lower_band": 2,      # 볼링저 밴드 하단 접촉
                "momentum_turning_up": 1,  # 모멘텀 상승 전환
                "near_support": 3,         # 지지선 근처 (2에서 3으로 증가)
                "minute_rsi_oversold": 1,  # 분봉 RSI 과매도
                "minute_macd_cross_up": 1, # 분봉 MACD 상향돌파
                "consecutive_drop": 2      # 연속 하락일 가중치
            }
        }
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"기본 설정 파일 생성 완료: {config_path}")
    except Exception as e:
        logger.exception(f"설정 파일 생성 중 오류: {str(e)}")


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
            
            logger.info(f"백테스트 모드 실행: {start_date} ~ {end_date or '현재'}")
            results = trend_bot.run_backtest(start_date, end_date)
            
            # 백테스트 결과 저장
            results_file = f"backtest_result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                # default=str 옵션 추가 - 모든 직렬화 불가능한 객체를 문자열로 변환
                json.dump(results, f, ensure_ascii=False, indent=4, default=str)            
                
            logger.info(f"백테스트 결과 저장 완료: {results_file}")
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