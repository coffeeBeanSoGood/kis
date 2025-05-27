#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
기술적 분석 라이브러리
TechnicalIndicators, AdaptiveMarketStrategy, TrendFilter 클래스 포함
"""

import os
import json
import logging
import datetime
import numpy as np
import pandas as pd
from typing import Dict, Any
import KIS_API_Helper_KR as KisKR

# 여기에 trend_trading.py에서 다음 클래스들을 그대로 복사:
# - TechnicalIndicators 클래스 (전체)
# - AdaptiveMarketStrategy 클래스 (전체) 
# - TrendFilter 클래스 (전체)

# 전역 logger 변수 선언
logger = None

def set_logger(external_logger):
    """외부 로거를 설정하는 함수"""
    global logger
    logger = external_logger

class TechnicalIndicators:
    """기술적 지표 계산 클래스"""
    @staticmethod
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

        # 🔥 동적 파라미터 데이터 추가
        self.dynamic_parameters = {}  # 종목별 동적 파라미터
        
        self.load_strategy()

    def load_strategy(self):
        """전략 데이터 로드"""
        try:
            if os.path.exists(self.strategy_file):
                with open(self.strategy_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.stock_performance = data.get('stock_performance', {})
                    # 🔥 동적 파라미터 로드 추가
                    self.dynamic_parameters = data.get('dynamic_parameters', {})
                logger.info(f"적응형 전략 데이터 로드 완료: {len(self.stock_performance)}개 종목")
            else:
                logger.info("적응형 전략 데이터 파일이 없습니다. 새로 생성합니다.")
                self.stock_performance = {}
                self.dynamic_parameters = {}  # 🔥 추가
        except Exception as e:
            logger.exception(f"적응형 전략 데이터 로드 중 오류: {str(e)}")
            self.stock_performance = {}
            self.dynamic_parameters = {}  # 🔥 추가

    def save_strategy(self):
        """전략 데이터 저장"""
        try:
            # 🔥 동적 파라미터도 함께 저장
            data = {
                'stock_performance': self.stock_performance,
                'dynamic_parameters': self.dynamic_parameters,
                'last_updated': datetime.datetime.now().isoformat()
            }
            
            with open(self.strategy_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
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

        # 환경별 전략 데이터 구조 확인
        if "adaptive_strategy" not in self.stock_performance[stock_code]:
            self.stock_performance[stock_code]["adaptive_strategy"] = {
                "uptrend": {"use_common": True},
                "downtrend": {"use_common": True},
                "sideways": {"use_common": True}
            }
        
        # 현재 시장 환경에 대한 전략 데이터 확인
        if market_env not in self.stock_performance[stock_code]["adaptive_strategy"]:
            self.stock_performance[stock_code]["adaptive_strategy"][market_env] = {"use_common": True}
        
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
            if env_data["trades"] > 0:
                env_data["winrate"] = (env_data["wins"] / env_data["trades"]) * 100
            else:
                env_data["winrate"] = 0.0
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

    def get_dynamic_parameters(self, stock_code: str, market_env: str = "sideways") -> Dict:
        """동적 파라미터 조회"""
        
        # 종목별 동적 파라미터 초기화
        if stock_code not in self.dynamic_parameters:
            self.dynamic_parameters[stock_code] = {
                'rsi_threshold': 55,
                'min_score': 40,
                'performance_data': {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'recent_results': []
                },
                'last_updated': datetime.datetime.now().isoformat()
            }
        
        base_params = self.dynamic_parameters[stock_code]
        
        # 시장 환경별 조정
        market_adjustments = {
            'uptrend': {'rsi_adjust': +10, 'score_adjust': -5},
            'downtrend': {'rsi_adjust': -15, 'score_adjust': +10},
            'sideways': {'rsi_adjust': -5, 'score_adjust': -2}
        }
        
        adjust = market_adjustments.get(market_env, {'rsi_adjust': 0, 'score_adjust': 0})
        
        # 성과 기반 조정
        perf_data = base_params['performance_data']
        if len(perf_data['recent_results']) >= 5:
            recent_win_rate = sum(perf_data['recent_results'][-5:]) / 5
            if recent_win_rate >= 0.8:
                adjust['rsi_adjust'] += 5
                adjust['score_adjust'] -= 5
            elif recent_win_rate <= 0.2:
                adjust['rsi_adjust'] -= 10
                adjust['score_adjust'] += 10
        
        # 최종 파라미터
        final_params = {
            'rsi_threshold': max(25, min(70, base_params['rsi_threshold'] + adjust['rsi_adjust'])),
            'min_score': max(25, min(70, base_params['min_score'] + adjust['score_adjust']))
        }
        
        logger.info(f"🧠 {stock_code} 동적 파라미터 ({market_env}): "
                f"RSI {final_params['rsi_threshold']}, 점수 {final_params['min_score']}")
        
        return final_params

    def update_dynamic_performance(self, stock_code: str, trade_result: Dict):
        """거래 결과로 동적 파라미터 성과 업데이트"""
        
        if stock_code not in self.dynamic_parameters:
            self.get_dynamic_parameters(stock_code)  # 초기화
        
        perf_data = self.dynamic_parameters[stock_code]['performance_data']
        
        # 통계 업데이트
        perf_data['total_trades'] += 1
        if trade_result.get('profit', 0) > 0:
            perf_data['winning_trades'] += 1
            perf_data['recent_results'].append(1)
        else:
            perf_data['recent_results'].append(0)
        
        # 최근 결과 10개만 유지
        if len(perf_data['recent_results']) > 10:
            perf_data['recent_results'].pop(0)
        
        # 연속 결과에 따른 기본 파라미터 조정
        if len(perf_data['recent_results']) >= 5:
            last_5 = perf_data['recent_results'][-5:]
            base_params = self.dynamic_parameters[stock_code]
            
            if sum(last_5) == 0:  # 5연패
                base_params['rsi_threshold'] = max(25, base_params['rsi_threshold'] - 5)
                base_params['min_score'] = min(65, base_params['min_score'] + 5)
                logger.warning(f"🔴 {stock_code} 5연패로 기본 파라미터 보수적 조정")
            elif sum(last_5) == 5:  # 5연승
                base_params['rsi_threshold'] = min(65, base_params['rsi_threshold'] + 3)
                base_params['min_score'] = max(25, base_params['min_score'] - 3)
                logger.info(f"🟢 {stock_code} 5연승으로 기본 파라미터 공격적 조정")
        
        # 기존 시장 환경 학습도 함께 호출
        market_env = trade_result.get('market_env', 'sideways')
        win = trade_result.get('profit', 0) > 0
        self.update_performance(stock_code, market_env, win)  # 기존 메서드 호출
        
        # 업데이트 시간 기록
        self.dynamic_parameters[stock_code]['last_updated'] = datetime.datetime.now().isoformat()
        
        self.save_strategy()
        logger.info(f"📊 {stock_code} 동적 파라미터 성과 업데이트 완료")

    def get_parameter_report(self, stock_code: str) -> str:
        """동적 파라미터 보고서"""
        
        if stock_code not in self.dynamic_parameters:
            return f"{stock_code}: 동적 파라미터 데이터 없음"
        
        data = self.dynamic_parameters[stock_code]
        perf_data = data['performance_data']
        
        report = f"🧠 {stock_code} 동적 파라미터:\n"
        report += f"기본 RSI: {data['rsi_threshold']}, 점수: {data['min_score']}\n"
        
        if perf_data['total_trades'] > 0:
            win_rate = perf_data['winning_trades'] / perf_data['total_trades'] * 100
            report += f"거래: {perf_data['total_trades']}회 (승률: {win_rate:.1f}%)\n"
            
            if len(perf_data['recent_results']) > 0:
                recent_pattern = ''.join(['🟢' if x else '🔴' for x in perf_data['recent_results'][-5:]])
                report += f"최근: {recent_pattern}\n"
        
        return report

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