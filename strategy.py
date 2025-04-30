#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
한국주식 추세매매봇 (Trend Trading Bot)
- 전략 유형 분리 및 종목별 전략 적용 기능 추가
- 다양한 전략 유형을 정의하고 종목별로 선택 적용 가능
- 백테스트를 통한 전략별 성과 비교 기능
"""

import os
import sys
import time
import json
import logging
import datetime
import numpy as np
import pandas as pd
import random
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

# 전략 유형 정의를 위한 클래스
class TradingStrategy:
    """매매 전략 기본 클래스"""
    
    def __init__(self, name: str, params: Dict[str, any]):
        """매매 전략 초기화
        
        Args:
            name: 전략 이름
            params: 전략 매개변수
        """
        self.name = name
        self.params = params
        self.tech_indicators = TechnicalIndicators()
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """매수 신호 분석 (추상 메서드)
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        raise NotImplementedError("Subclass must implement this method")
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """매도 신호 분석 (추상 메서드)
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        raise NotImplementedError("Subclass must implement this method")
    
    def get_stop_loss_price(self, daily_data: pd.DataFrame, current_price: float, 
                            avg_price: float) -> float:
        """손절가 계산 (기본 구현)
        
        Args:
            daily_data: 일봉 데이터
            current_price: 현재가
            avg_price: 평균단가
            
        Returns:
            float: 손절가
        """
        # 기본 손절가 계산 (매입가의 x% 하락)
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        return avg_price * (1 - stop_loss_pct/100)


# RSI 기반 전략 
class RSIStrategy(TradingStrategy):
    """RSI 과매도/과매수 기반 매매 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """RSI 기반 매수 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "minute": {}
            },
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        # RSI 계산
        rsi_period = self.params.get("rsi_period", 14)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
        
        # 볼린저 밴드 계산
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )

        # 매수 조건 확인
        rsi_value = daily_data['RSI'].iloc[-1]
        rsi_oversold_threshold = self.params.get("rsi_oversold_threshold", 30.0)
        
        # 1. RSI 과매도 확인
        is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value, rsi_oversold_threshold)
        result["signals"]["daily"]["rsi_oversold"] = is_oversold
        
        # 2. 볼린저 밴드 하단 접촉
        price_near_lower_band = False
        if current_price is not None:
            price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[-1] * 1.01
        else:
            price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.01
            
        result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
        
        # 매수 신호 결합 (RSI 과매도 + 볼린저 밴드 하단)
        buy_signal = is_oversold and price_near_lower_band
        
        # 추가 확인 (선택): 분봉 데이터 분석
        use_minute_confirm = self.params.get("use_minute_confirm", False)
        minute_signal = True  # 기본값
        
        if use_minute_confirm and minute_data is not None and not minute_data.empty:
            minute_data['RSI'] = self.tech_indicators.calculate_rsi(minute_data, period=rsi_period)
            minute_rsi_value = minute_data['RSI'].iloc[-1]
            minute_is_oversold = self.tech_indicators.is_oversold_rsi(minute_rsi_value, rsi_oversold_threshold)
            result["signals"]["minute"]["rsi_oversold"] = minute_is_oversold
            
            minute_signal = minute_is_oversold
        
        # 최종 매수 신호 및 이유 설정
        result["is_buy_signal"] = buy_signal and minute_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if is_oversold:
                reasons.append(f"RSI 과매도 ({rsi_value:.2f} < {rsi_oversold_threshold})")
            if price_near_lower_band:
                reasons.append("볼린저 밴드 하단 접촉")
                
            result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """RSI 기반 매도 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_sell_signal": False,
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        avg_price = holding_info.get("avg_price", 0)
        if avg_price <= 0:
            return result
        
        # 수익률 계산
        profit_percent = ((current_price / avg_price) - 1) * 100
        
        # RSI 계산
        rsi_period = self.params.get("rsi_period", 14)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
        rsi_value = daily_data['RSI'].iloc[-1]
        
        # 1. 목표 수익률 달성
        profit_target = self.params.get("profit_target", 5.0)
        if profit_percent >= profit_target:
            result["is_sell_signal"] = True
            result["reason"] = f"목표 수익률 달성: {profit_percent:.2f}%"
            return result
        
        # 2. 손절 조건
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        if profit_percent <= -stop_loss_pct:
            result["is_sell_signal"] = True
            result["reason"] = f"손절 조건 발동: {profit_percent:.2f}%"
            return result
        
        # 3. RSI 과매수 영역
        rsi_overbought_threshold = self.params.get("rsi_overbought_threshold", 70.0)
        if self.tech_indicators.is_overbought_rsi(rsi_value, rsi_overbought_threshold):
            result["is_sell_signal"] = True
            result["reason"] = f"RSI 과매수 영역: {rsi_value:.2f}"
            return result
        
        return result
    
    def get_stop_loss_price(self, daily_data: pd.DataFrame, current_price: float, 
                            avg_price: float) -> float:
        """RSI 전략 손절가 계산
        
        Args:
            daily_data: 일봉 데이터
            current_price: 현재가
            avg_price: 평균단가
            
        Returns:
            float: 손절가
        """
        use_dynamic_stop = self.params.get("use_dynamic_stop", False)
        
        if use_dynamic_stop and not daily_data.empty:
            # ATR 기반 동적 손절가 계산
            atr_period = self.params.get("atr_period", 14)
            atr_multiplier = self.params.get("atr_multiplier", 2.0)
            
            daily_data['ATR'] = self.tech_indicators.calculate_atr(daily_data, period=atr_period)
            atr_value = daily_data['ATR'].iloc[-1]
            
            if not pd.isna(atr_value):
                return self.tech_indicators.calculate_dynamic_stop_loss(
                    current_price, atr_value, atr_multiplier
                )
        
        # 기본 손절가 (매입가의 x% 하락)
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        return avg_price * (1 - stop_loss_pct/100)


# MACD 기반 전략
class MACDStrategy(TradingStrategy):
    """MACD 기반 매매 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """MACD 기반 매수 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "minute": {}
            },
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        # MACD 계산
        fast_period = self.params.get("macd_fast_period", 12)
        slow_period = self.params.get("macd_slow_period", 26)
        signal_period = self.params.get("macd_signal_period", 9)
        
        daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
            daily_data, 
            fast_period=fast_period, 
            slow_period=slow_period, 
            signal_period=signal_period
        )
        
        # 이동평균선 계산
        short_ma_period = self.params.get("short_ma_period", 5)
        long_ma_period = self.params.get("long_ma_period", 20)
        daily_data['MA_short'] = daily_data['close'].rolling(window=short_ma_period).mean()
        daily_data['MA_long'] = daily_data['close'].rolling(window=long_ma_period).mean()

        # 매수 조건 확인
        # 1. MACD 상향돌파 확인
        macd_cross_up = False
        try:
            if len(daily_data) >= 2:
                if daily_data['MACD'].iloc[-2] < daily_data['Signal'].iloc[-2] and \
                daily_data['MACD'].iloc[-1] >= daily_data['Signal'].iloc[-1]:
                    macd_cross_up = True
        except:
            pass
            
        result["signals"]["daily"]["macd_cross_up"] = macd_cross_up
        
        # 2. 히스토그램 상승 확인
        histogram_rising = False
        try:
            if len(daily_data) >= 2:
                if daily_data['Histogram'].iloc[-1] > daily_data['Histogram'].iloc[-2]:
                    histogram_rising = True
        except:
            pass
            
        result["signals"]["daily"]["histogram_rising"] = histogram_rising
        
        # 3. 골든 크로스 확인
        golden_cross = self.tech_indicators.is_golden_cross(
            daily_data, 
            short_period=short_ma_period, 
            long_period=long_ma_period
        )
        result["signals"]["daily"]["golden_cross"] = golden_cross
        
        # 매수 신호 결합 (MACD 상향돌파 또는 (히스토그램 상승 + 골든 크로스))
        buy_signal = macd_cross_up or (histogram_rising and golden_cross)
        
        # 분봉 확인 (선택)
        use_minute_confirm = self.params.get("use_minute_confirm", False)
        minute_signal = True  # 기본값
        
        if use_minute_confirm and minute_data is not None and not minute_data.empty:
            # 분봉 MACD 계산
            minute_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
                minute_data, 
                fast_period=fast_period, 
                slow_period=slow_period, 
                signal_period=signal_period
            )
            
            minute_macd_cross_up = False
            try:
                if len(minute_data) >= 2:
                    if minute_data['MACD'].iloc[-2] < minute_data['Signal'].iloc[-2] and \
                    minute_data['MACD'].iloc[-1] >= minute_data['Signal'].iloc[-1]:
                        minute_macd_cross_up = True
            except:
                pass
                
            result["signals"]["minute"]["macd_cross_up"] = minute_macd_cross_up
            minute_signal = minute_macd_cross_up
        
        # 최종 매수 신호 및 이유 설정
        result["is_buy_signal"] = buy_signal and minute_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if macd_cross_up:
                reasons.append("MACD 상향돌파")
            if histogram_rising:
                reasons.append("MACD 히스토그램 상승")
            if golden_cross:
                reasons.append("골든 크로스")
                
            result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """MACD 기반 매도 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_sell_signal": False,
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        avg_price = holding_info.get("avg_price", 0)
        if avg_price <= 0:
            return result
        
        # 수익률 계산
        profit_percent = ((current_price / avg_price) - 1) * 100
        
        # MACD 계산
        fast_period = self.params.get("macd_fast_period", 12)
        slow_period = self.params.get("macd_slow_period", 26)
        signal_period = self.params.get("macd_signal_period", 9)
        
        daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
            daily_data, 
            fast_period=fast_period, 
            slow_period=slow_period, 
            signal_period=signal_period
        )
        
        # 이동평균선 계산
        short_ma_period = self.params.get("short_ma_period", 5)
        long_ma_period = self.params.get("long_ma_period", 20)
        daily_data['MA_short'] = daily_data['close'].rolling(window=short_ma_period).mean()
        daily_data['MA_long'] = daily_data['close'].rolling(window=long_ma_period).mean()
        
        # 1. 목표 수익률 달성
        profit_target = self.params.get("profit_target", 5.0)
        if profit_percent >= profit_target:
            result["is_sell_signal"] = True
            result["reason"] = f"목표 수익률 달성: {profit_percent:.2f}%"
            return result
        
        # 2. 손절 조건
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        if profit_percent <= -stop_loss_pct:
            result["is_sell_signal"] = True
            result["reason"] = f"손절 조건 발동: {profit_percent:.2f}%"
            return result
        
        # 3. MACD 하향돌파 확인
        macd_cross_down = False
        try:
            if len(daily_data) >= 2:
                if daily_data['MACD'].iloc[-2] > daily_data['Signal'].iloc[-2] and \
                daily_data['MACD'].iloc[-1] < daily_data['Signal'].iloc[-1]:
                    macd_cross_down = True
        except:
            pass
            
        if macd_cross_down:
            result["is_sell_signal"] = True
            result["reason"] = "MACD 하향돌파"
            return result
        
        # 4. 데드 크로스 확인
        death_cross = self.tech_indicators.is_death_cross(
            daily_data, 
            short_period=short_ma_period, 
            long_period=long_ma_period
        )
        
        if death_cross:
            result["is_sell_signal"] = True
            result["reason"] = "데드 크로스 발생"
            return result
        
        return result

# 볼린저 밴드 기반 전략
class BollingerBandStrategy(TradingStrategy):
    """볼린저 밴드 기반 매매 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """볼린저 밴드 기반 매수 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "minute": {}
            },
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        # 볼린저 밴드 계산
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )
        
        # 스토캐스틱 계산 (선택)
        use_stochastic = self.params.get("use_stochastic", True)
        if use_stochastic:
            k_period = self.params.get("stoch_k_period", 14)
            d_period = self.params.get("stoch_d_period", 3)
            
            daily_data[['K', 'D']] = self.tech_indicators.calculate_stochastic(
                daily_data, k_period=k_period, d_period=d_period
            )

        # 매수 조건 확인
        # 1. 하단 밴드 접촉/돌파
        price_near_lower_band = False
        price_below_lower_band = False
        
        if current_price is not None:
            price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[-1] * 1.01
            price_below_lower_band = current_price < daily_data['LowerBand'].iloc[-1]
        else:
            price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.01
            price_below_lower_band = daily_data['close'].iloc[-1] < daily_data['LowerBand'].iloc[-1]
            
        result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
        result["signals"]["daily"]["below_lower_band"] = price_below_lower_band
        
        # 2. 밴드 폭 확장/수축 확인
        band_width = (daily_data['UpperBand'] - daily_data['LowerBand']) / daily_data['MiddleBand']
        band_width_expanding = False
        
        if len(band_width) >= 3:
            if band_width.iloc[-1] > band_width.iloc[-2] > band_width.iloc[-3]:
                band_width_expanding = True
                
        result["signals"]["daily"]["band_width_expanding"] = band_width_expanding
        
        # 3. 스토캐스틱 과매도 확인 (선택)
        stoch_oversold = False
        if use_stochastic and 'K' in daily_data.columns and 'D' in daily_data.columns:
            stoch_oversold_threshold = self.params.get("stoch_oversold_threshold", 20.0)
            if daily_data['K'].iloc[-1] < stoch_oversold_threshold and daily_data['D'].iloc[-1] < stoch_oversold_threshold:
                stoch_oversold = True
                
        result["signals"]["daily"]["stoch_oversold"] = stoch_oversold
        
        # 매수 신호 결합 (하단 밴드 접촉 + 스토캐스틱 과매도)
        buy_signal = price_near_lower_band and (not self.params.get("require_stoch_oversold", False) or stoch_oversold)
        
        # 최종 매수 신호 및 이유 설정
        result["is_buy_signal"] = buy_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if price_near_lower_band:
                reasons.append("볼린저 밴드 하단 접촉")
            if price_below_lower_band:
                reasons.append("볼린저 밴드 하단 돌파")
            if stoch_oversold:
                reasons.append("스토캐스틱 과매도")
                
            result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """볼린저 밴드 기반 매도 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_sell_signal": False,
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        avg_price = holding_info.get("avg_price", 0)
        if avg_price <= 0:
            return result
        
        # 수익률 계산
        profit_percent = ((current_price / avg_price) - 1) * 100
        
        # 볼린저 밴드 계산
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )
        
        # 스토캐스틱 계산 (선택)
        use_stochastic = self.params.get("use_stochastic", True)
        if use_stochastic:
            k_period = self.params.get("stoch_k_period", 14)
            d_period = self.params.get("stoch_d_period", 3)
            
            daily_data[['K', 'D']] = self.tech_indicators.calculate_stochastic(
                daily_data, k_period=k_period, d_period=d_period
            )
        
        # 1. 목표 수익률 달성
        profit_target = self.params.get("profit_target", 5.0)
        if profit_percent >= profit_target:
            result["is_sell_signal"] = True
            result["reason"] = f"목표 수익률 달성: {profit_percent:.2f}%"
            return result
        
        # 2. 손절 조건
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        if profit_percent <= -stop_loss_pct:
            result["is_sell_signal"] = True
            result["reason"] = f"손절 조건 발동: {profit_percent:.2f}%"
            return result
        
        # 3. 상단 밴드 접촉/돌파
        price_near_upper_band = current_price >= daily_data['UpperBand'].iloc[-1] * 0.99
        
        if price_near_upper_band:
            result["is_sell_signal"] = True
            result["reason"] = "볼린저 밴드 상단 접촉"
            return result
        
        # 4. 스토캐스틱 과매수 확인 (선택)
        if use_stochastic and 'K' in daily_data.columns and 'D' in daily_data.columns:
            stoch_overbought_threshold = self.params.get("stoch_overbought_threshold", 80.0)
            if daily_data['K'].iloc[-1] > stoch_overbought_threshold and daily_data['D'].iloc[-1] > stoch_overbought_threshold:
                result["is_sell_signal"] = True
                result["reason"] = "스토캐스틱 과매수"
                return result
        
        return result
        
        
# 이동평균선 기반 전략
class MovingAverageStrategy(TradingStrategy):
    """이동평균선 기반 매매 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """이동평균선 기반 매수 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "minute": {}
            },
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        # 이동평균선 기간 설정
        short_period = self.params.get("ma_short_period", 5)
        mid_period = self.params.get("ma_mid_period", 20)
        long_period = self.params.get("ma_long_period", 60)
        
        # 이동평균선 계산
        daily_data[f'MA{short_period}'] = daily_data['close'].rolling(window=short_period).mean()
        daily_data[f'MA{mid_period}'] = daily_data['close'].rolling(window=mid_period).mean()
        daily_data[f'MA{long_period}'] = daily_data['close'].rolling(window=long_period).mean()

        # 매수 조건 확인
        # 1. 골든 크로스 (단기 > 중기)
        golden_cross_mid = self.tech_indicators.is_golden_cross(
            daily_data, 
            short_period=short_period, 
            long_period=mid_period
        )
        result["signals"]["daily"]["golden_cross_mid"] = golden_cross_mid
        
        # 2. 골든 크로스 (중기 > 장기)
        golden_cross_long = False
        if long_period > 0:
            golden_cross_long = self.tech_indicators.is_golden_cross(
                daily_data, 
                short_period=mid_period, 
                long_period=long_period
            )
        result["signals"]["daily"]["golden_cross_long"] = golden_cross_long
        
        # 3. 현재가 > 단기 이평선
        price_above_short_ma = False
        if current_price is not None:
            price_above_short_ma = current_price > daily_data[f'MA{short_period}'].iloc[-1]
        else:
            price_above_short_ma = daily_data['close'].iloc[-1] > daily_data[f'MA{short_period}'].iloc[-1]
            
        result["signals"]["daily"]["price_above_short_ma"] = price_above_short_ma
        
        # 4. 모든 이평선이 정렬된 상태 (상승추세)
        uptrend_alignment = False
        if long_period > 0:
            if len(daily_data) > long_period:
                ma_short = daily_data[f'MA{short_period}'].iloc[-1]
                ma_mid = daily_data[f'MA{mid_period}'].iloc[-1]
                ma_long = daily_data[f'MA{long_period}'].iloc[-1]
                
                uptrend_alignment = ma_short > ma_mid > ma_long
        else:
            if len(daily_data) > mid_period:
                ma_short = daily_data[f'MA{short_period}'].iloc[-1]
                ma_mid = daily_data[f'MA{mid_period}'].iloc[-1]
                
                uptrend_alignment = ma_short > ma_mid
                
        result["signals"]["daily"]["uptrend_alignment"] = uptrend_alignment
        
        # 매수 신호 결합
        ma_strategy_type = self.params.get("ma_strategy_type", "golden_cross")
        
        if ma_strategy_type == "golden_cross":
            # 골든 크로스 기반 전략
            buy_signal = golden_cross_mid or (golden_cross_long and long_period > 0)
        elif ma_strategy_type == "uptrend":
            # 상승추세 기반 전략
            buy_signal = uptrend_alignment and price_above_short_ma
        elif ma_strategy_type == "bounce":
            # 지지선 반등 기반 전략
            buy_signal = price_above_short_ma and daily_data['close'].iloc[-2] < daily_data[f'MA{short_period}'].iloc[-2]
        else:
            # 기본 전략 (골든 크로스)
            buy_signal = golden_cross_mid
        
        # 최종 매수 신호 및 이유 설정
        result["is_buy_signal"] = buy_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if golden_cross_mid:
                reasons.append(f"{short_period}일선이 {mid_period}일선을 상향돌파")
            if golden_cross_long:
                reasons.append(f"{mid_period}일선이 {long_period}일선을 상향돌파")
            if uptrend_alignment:
                reasons.append("이동평균선 정렬 상승추세")
            if price_above_short_ma:
                reasons.append(f"현재가가 {short_period}일선 위에 위치")
                
            result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """이동평균선 기반 매도 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_sell_signal": False,
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        avg_price = holding_info.get("avg_price", 0)
        if avg_price <= 0:
            return result
        
        # 수익률 계산
        profit_percent = ((current_price / avg_price) - 1) * 100
        
        # 이동평균선 기간 설정
        short_period = self.params.get("ma_short_period", 5)
        mid_period = self.params.get("ma_mid_period", 20)
        long_period = self.params.get("ma_long_period", 60)
        
        # 이동평균선 계산
        daily_data[f'MA{short_period}'] = daily_data['close'].rolling(window=short_period).mean()
        daily_data[f'MA{mid_period}'] = daily_data['close'].rolling(window=mid_period).mean()
        
        if long_period > 0:
            daily_data[f'MA{long_period}'] = daily_data['close'].rolling(window=long_period).mean()
        
        # 1. 목표 수익률 달성
        profit_target = self.params.get("profit_target", 5.0)
        if profit_percent >= profit_target:
            result["is_sell_signal"] = True
            result["reason"] = f"목표 수익률 달성: {profit_percent:.2f}%"
            return result
        
        # 2. 손절 조건
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        if profit_percent <= -stop_loss_pct:
            result["is_sell_signal"] = True
            result["reason"] = f"손절 조건 발동: {profit_percent:.2f}%"
            return result
        
        # 3. 데드 크로스 (단기 < 중기)
        death_cross_mid = self.tech_indicators.is_death_cross(
            daily_data, 
            short_period=short_period, 
            long_period=mid_period
        )
        
        if death_cross_mid:
            result["is_sell_signal"] = True
            result["reason"] = f"{short_period}일선이 {mid_period}일선을 하향돌파(데드 크로스)"
            return result
        
        # 4. 현재가 < 단기 이평선 (하락 전환)
        if current_price < daily_data[f'MA{short_period}'].iloc[-1] and \
           daily_data['close'].iloc[-2] >= daily_data[f'MA{short_period}'].iloc[-2]:
            result["is_sell_signal"] = True
            result["reason"] = f"현재가가 {short_period}일선 아래로 하락"
            return result
        
        return result

# 트레일링 스탑 전략 클래스 (기본 전략에 트레일링 스탑 기능을 추가한 래퍼)
class TrailingStopStrategy(TradingStrategy):
    """기본 전략에 트레일링 스탑 기능을 추가한 전략 래퍼"""
    
    def __init__(self, base_strategy: TradingStrategy, params: Dict[str, any]):
        """트레일링 스탑 전략 초기화
        
        Args:
            base_strategy: 기본 전략 객체
            params: 전략 매개변수
        """
        super().__init__(f"TrailingStop_{base_strategy.name}", params)
        self.base_strategy = base_strategy
        
        # 베이스 전략 파라미터 업데이트
        for key, value in params.items():
            if key != "trailing_stop_pct":
                self.base_strategy.params[key] = value
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """기본 전략의 매수 신호 분석 호출
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        return self.base_strategy.analyze_buy_signal(daily_data, minute_data, current_price)
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """트레일링 스탑 로직이 추가된 매도 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        # 먼저 기본 전략의 매도 신호 확인
        base_result = self.base_strategy.analyze_sell_signal(daily_data, holding_info, current_price)
        
        # 기본 전략에서 매도 신호가 발생했으면 그대로 반환
        if base_result["is_sell_signal"]:
            return base_result
        
        # 트레일링 스탑 조건 확인
        highest_price = holding_info.get("highest_price", 0)
        trailing_stop_price = holding_info.get("trailing_stop_price", 0)
        
        # 트레일링 스탑 발동
        if trailing_stop_price > 0 and current_price < trailing_stop_price:
            return {
                "is_sell_signal": True,
                "reason": f"트레일링 스탑 발동: 최고가 {highest_price:,}원의 " + 
                        f"{self.params.get('trailing_stop_pct', 2.0)}% 하락"
            }
        
        return base_result
    
    def get_stop_loss_price(self, daily_data: pd.DataFrame, current_price: float, 
                            avg_price: float) -> float:
        """기본 전략의 손절가 계산 호출
        
        Args:
            daily_data: 일봉 데이터
            current_price: 현재가
            avg_price: 평균단가
            
        Returns:
            float: 손절가
        """
        return self.base_strategy.get_stop_loss_price(daily_data, current_price, avg_price)
    
    def update_trailing_stop(self, holding_info: Dict[str, any], 
                       current_price: float) -> Dict[str, any]:
        """트레일링 스탑 정보 업데이트
        
        Args:
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 업데이트된 보유 종목 정보
        """
        highest_price = holding_info.get("highest_price", current_price)
        
        # 현재가가 최고가보다 높으면 최고가 및 트레일링 스탑 가격 업데이트
        if current_price > highest_price:
            trailing_stop_pct = self.params.get("trailing_stop_pct", 2.0)
            new_stop_price = current_price * (1 - trailing_stop_pct/100)
            
            # 홀딩 정보 업데이트
            holding_info["highest_price"] = current_price
            holding_info["trailing_stop_price"] = new_stop_price
        
        return holding_info


# 복합 전략 클래스 (여러 전략을 조합)
class CompositeStrategy(TradingStrategy):
    """여러 전략을 조합한 복합 전략 클래스"""
    
    def __init__(self, name: str, strategies: List[TradingStrategy], params: Dict[str, any]):
        """복합 전략 초기화
        
        Args:
            name: 전략 이름
            strategies: 전략 목록
            params: 전략 매개변수
        """
        super().__init__(name, params)
        self.strategies = strategies
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """복합 전략 매수 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            minute_data: 분봉 데이터 (선택)
            current_price: 현재가 (선택)
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "minute": {}
            },
            "reason": "",
            "strategy_results": []
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        # 모든 전략의 매수 신호 분석
        for strategy in self.strategies:
            strategy_result = strategy.analyze_buy_signal(daily_data, minute_data, current_price)
            result["strategy_results"].append({
                "strategy_name": strategy.name,
                "is_buy_signal": strategy_result.get("is_buy_signal", False),
                "reason": strategy_result.get("reason", "")
            })
        
        # 매수 신호 조합 방식
        combine_method = self.params.get("combine_method", "any")
        
        if combine_method == "all":
            # 모든 전략에서 매수 신호가 발생해야 함
            buy_signal = all(result["is_buy_signal"] for result in result["strategy_results"])
        elif combine_method == "majority":
            # 과반수 이상의 전략에서 매수 신호가 발생해야 함
            buy_signals_count = sum(1 for result in result["strategy_results"] if result["is_buy_signal"])
            buy_signal = buy_signals_count > len(self.strategies) / 2
        else:
            # 하나 이상의 전략에서 매수 신호가 발생하면 됨
            buy_signal = any(result["is_buy_signal"] for result in result["strategy_results"])
        
        # 최종 매수 신호 및 이유 설정
        result["is_buy_signal"] = buy_signal
        
        if result["is_buy_signal"]:
            buy_strategies = [result["strategy_name"] for result in result["strategy_results"] if result["is_buy_signal"]]
            result["reason"] = f"매수 신호 발생 전략: {', '.join(buy_strategies)}"
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """복합 전략 매도 신호 분석
        
        Args:
            daily_data: 일봉 데이터
            holding_info: 보유 종목 정보
            current_price: 현재가
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            "is_sell_signal": False,
            "reason": "",
            "strategy_results": []
        }
        
        if daily_data is None or daily_data.empty:
            return result
        
        # 모든 전략의 매도 신호 분석
        for strategy in self.strategies:
            strategy_result = strategy.analyze_sell_signal(daily_data, holding_info, current_price)
            result["strategy_results"].append({
                "strategy_name": strategy.name,
                "is_sell_signal": strategy_result.get("is_sell_signal", False),
                "reason": strategy_result.get("reason", "")
            })
        
        # 매도 신호는 하나의 전략에서만 발생해도 매도
        for strategy_result in result["strategy_results"]:
            if strategy_result["is_sell_signal"]:
                result["is_sell_signal"] = True
                result["reason"] = f"{strategy_result['strategy_name']}: {strategy_result['reason']}"
                break
        
        return result
    
    def get_stop_loss_price(self, daily_data: pd.DataFrame, current_price: float, 
                            avg_price: float) -> float:
        """복합 전략 손절가 계산 (가장 보수적인 손절가 사용)
        
        Args:
            daily_data: 일봉 데이터
            current_price: 현재가
            avg_price: 평균단가
            
        Returns:
            float: 손절가
        """
        stop_loss_prices = []
        
        for strategy in self.strategies:
            stop_loss_price = strategy.get_stop_loss_price(daily_data, current_price, avg_price)
            stop_loss_prices.append(stop_loss_price)
        
        # 가장 높은 손절가 반환 (가장 보수적인 손절)
        if stop_loss_prices:
            return max(stop_loss_prices)
        
        # 기본 손절가
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        return avg_price * (1 - stop_loss_pct/100)


# 트렌드 필터 클래스
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

# 전략 관리자 클래스
class StrategyManager:
    """전략 관리자 클래스 - 전략 생성 및 관리"""
    
    def __init__(self, strategies_config: Dict[str, any]):
        """전략 관리자 초기화
        
        Args:
            strategies_config: 전략 설정
        """
        self.strategies_config = strategies_config
        self.strategy_cache = {}  # 생성된 전략 인스턴스 캐시
    
    def get_strategy(self, strategy_name: str, stock_code: str = None) -> TradingStrategy:
        """전략 인스턴스 가져오기
        
        Args:
            strategy_name: 전략 이름
            stock_code: 종목코드 (선택)
            
        Returns:
            TradingStrategy: 전략 인스턴스
        """
        # 캐시 키 생성
        cache_key = f"{strategy_name}_{stock_code}" if stock_code else strategy_name
        
        # 캐시에 있으면 반환
        if cache_key in self.strategy_cache:
            return self.strategy_cache[cache_key]
        
        # 전략 설정 가져오기
        strategy_config = self.strategies_config.get(strategy_name, {})
        strategy_type = strategy_config.get("type", strategy_name)
        
        # 종목별 설정이 있으면 병합
        if stock_code and "stock_config" in strategy_config:
            stock_specific_config = strategy_config["stock_config"].get(stock_code, {})
            # 딕셔너리 병합 (종목별 설정이 우선)
            params = {**strategy_config.get("params", {}), **stock_specific_config}
        else:
            params = strategy_config.get("params", {})
        
        # 전략 인스턴스 생성
        strategy = self._create_strategy(strategy_type, strategy_name, params)
        
        if strategy:
            # 캐시에 저장
            self.strategy_cache[cache_key] = strategy
            return strategy
        
        return None
    
    def _create_strategy(self, strategy_type: str, strategy_name: str, params: Dict[str, any]) -> TradingStrategy:
        """전략 인스턴스 생성
        
        Args:
            strategy_type: 전략 유형
            strategy_name: 전략 이름
            params: 전략 매개변수
            
        Returns:
            TradingStrategy: 전략 인스턴스
        """
        if strategy_type == "RSI":
            strategy = RSIStrategy(strategy_name, params)
        elif strategy_type == "MACD":
            strategy = MACDStrategy(strategy_name, params)
        elif strategy_type == "BollingerBand":
            strategy = BollingerBandStrategy(strategy_name, params)
        elif strategy_type == "MovingAverage":
            strategy = MovingAverageStrategy(strategy_name, params)
        elif strategy_type == "Composite":
            # 복합 전략 생성
            sub_strategies = []
            for sub_strategy_name in params.get("strategies", []):
                sub_strategy = self.get_strategy(sub_strategy_name)
                if sub_strategy:
                    sub_strategies.append(sub_strategy)
            
            if sub_strategies:
                strategy = CompositeStrategy(strategy_name, sub_strategies, params)
            else:
                logger.warning(f"복합 전략 {strategy_name}에 유효한 하위 전략이 없습니다.")
                strategy = None
        else:
            logger.warning(f"알 수 없는 전략 유형: {strategy_type}")
            strategy = None
        
        # 트레일링 스탑 래핑 확인
        if strategy and params.get("use_trailing_stop", False):
            strategy = TrailingStopStrategy(strategy, params)
        
        return strategy


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
        
        self.total_budget = self.config.get("total_budget", 5000000)  # 기본 총 예산 500만원
        self.max_stocks = self.config.get("max_stocks", 5)  # 최대 동시 보유 종목 수
        
        # 전략 관리자 초기화
        self.strategy_manager = StrategyManager(self.config.get("strategies", {}))
        
        self.holdings = {}  # 보유 종목 정보
        self.last_check_time = {}  # 마지막 검사 시간
        
        # 로그 파일명 설정
        today = datetime.datetime.now().strftime("%Y%m%d")
        self.log_file = f"trend_trading_{today}.log"
        
        # 보유종목 정보 로드
        self._load_holdings()

    
    def _load_config(self, config_path: str) -> Dict[str, any]:
        """설정 파일 로드
        
        Args:
            config_path: 설정 파일 경로
            
        Returns:
            Dict: 설정 정보
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"설정 파일 {config_path}을 찾을 수 없습니다. 기본값을 사용합니다.")
            # 기본 설정 반환
            return {
                "api_key": "",
                "api_secret": "",
                "account_number": "",
                "account_code": "",
                "watch_list": [],
                "sector_list": [],
                "total_budget": 5000000,
                "max_stocks": 5,
                "strategies": {}
            }
        except Exception as e:
            logger.exception(f"설정 파일 로드 중 오류: {str(e)}")
            return {}
    
    def _save_config(self) -> None:
        """설정 파일 저장"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"설정 파일 저장 완료: {self.config_path}")
        except Exception as e:
            logger.exception(f"설정 파일 저장 중 오류: {str(e)}")


    def _load_holdings(self) -> None:
        """보유 종목 정보 로드"""
        try:
            # API로 계좌 잔고 가져오기
            account_balance = KisKR.GetBalance()
            
            if not account_balance or isinstance(account_balance, str):
                logger.warning("계좌 잔고 정보를 가져올 수 없습니다.")
                return
            
            # 보유종목 정보 가져오기
            stock_list = KisKR.GetMyStockList()
            
            # 보유중인 종목 추가
            for stock in stock_list:
                stock_code = stock.get("StockCode")
                if stock_code:
                    current_price = float(stock.get("StockNowPrice", 0))
                    
                    # 종목별 적용된 전략 정보 확인
                    strategy_name = self.watch_list_info.get(stock_code, {}).get("strategy", "RSI")
                    
                    self.holdings[stock_code] = {
                        "quantity": int(stock.get("StockAmt", 0)),
                        "avg_price": float(stock.get("StockAvgPrice", 0)),
                        "current_price": current_price,
                        "buy_date": datetime.datetime.now().strftime("%Y%m%d"),
                        "highest_price": current_price,  # 트레일링 스탑을 위한 최고가 기록
                        "trailing_stop_price": 0,  # 트레일링 스탑 가격
                        "strategy": strategy_name,  # 적용된 전략명
                        "split_buy": True,  # 분할 매수 옵션
                        "initial_budget": 0,  # 총 예산
                        "used_budget": 0,  # 사용된 예산
                        "remaining_budget": 0  # 남은 예산
                    }
                    
                    # 트레일링 스탑 가격 설정
                    strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
                    
                    if isinstance(strategy, TrailingStopStrategy):
                        trailing_pct = strategy.params.get("trailing_stop_pct", 2.0)
                        self.holdings[stock_code]["trailing_stop_price"] = current_price * (1 - trailing_pct/100)
            
            logger.info(f"보유 종목 로드 완료: {len(self.holdings)}개")
        except Exception as e:
            logger.exception(f"보유 종목 로드 중 오류: {str(e)}")


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
            
            # 분봉 데이터 조회 (30분봉)
            minute_data = KisKR.GetOhlcvMinute(stock_code, MinSt='30T')
            
            # 종목별 전략 가져오기
            strategy_name = self.watch_list_info.get(stock_code, {}).get("strategy", "RSI")
            strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
            
            if strategy is None:
                logger.warning(f"종목 {stock_code}에 대한 전략 {strategy_name}을 찾을 수 없습니다.")
                return {"is_buy_signal": False, "reason": "전략 설정 없음"}
            
            # 매수 신호 분석
            analysis_result = strategy.analyze_buy_signal(daily_data, minute_data, current_price)
            
            # 분석 결과에 종목 정보 추가
            analysis_result["stock_code"] = stock_code
            analysis_result["stock_name"] = stock_info.get("StockName", "")
            analysis_result["current_price"] = current_price
            analysis_result["strategy"] = strategy_name
            
            # 시장 추세 필터 적용 (설정에서 활성화된 경우)
            if analysis_result.get("is_buy_signal", False) and self.config.get("use_market_trend_filter", False):
                market_index_code = self.config.get("market_index_code", "069500")
                market_trend_ok = TrendFilter.check_market_trend(market_index_code)
                if not market_trend_ok:
                    analysis_result["is_buy_signal"] = False
                    analysis_result["reason"] = "시장 추세 불량"
            
            return analysis_result
        except Exception as e:
            logger.exception(f"종목 {stock_code} 분석 중 오류: {str(e)}")
            return {"is_buy_signal": False, "reason": f"분석 오류: {str(e)}"}


    def check_sell_signals(self) -> None:
        """보유 종목 매도 시그널 확인"""
        try:
            for stock_code, holding_info in list(self.holdings.items()):
                current_price = KisKR.GetCurrentPrice(stock_code)
                if current_price is None or isinstance(current_price, str):
                    logger.warning(f"종목 {stock_code} 현재가를 조회할 수 없습니다.")
                    continue
                
                # 업데이트된 현재가 저장
                holding_info["current_price"] = current_price
                
                # 종목별 전략 가져오기
                strategy_name = holding_info.get("strategy", "RSI")
                strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
                
                if strategy is None:
                    logger.warning(f"종목 {stock_code}에 대한 전략 {strategy_name}을 찾을 수 없습니다.")
                    continue
                
                # 트레일링 스탑 업데이트 (TrailingStopStrategy 경우)
                if isinstance(strategy, TrailingStopStrategy):
                    holding_info = strategy.update_trailing_stop(holding_info, current_price)
                
                # 일봉 데이터 조회
                daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 30, adj_ok=1)
                
                if daily_data is None or daily_data.empty:
                    logger.warning(f"종목 {stock_code} 일봉 데이터가 없습니다.")
                    continue
                
                # 매도 신호 분석
                sell_result = strategy.analyze_sell_signal(daily_data, holding_info, current_price)
                
                # 매도 시그널이 있으면 매도 주문
                if sell_result.get("is_sell_signal", False):
                    logger.info(f"매도 시그널 발생: {stock_code}, 이유: {sell_result.get('reason', '')}")
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
                
                if last_check and (now - last_check).seconds < 3600:
                    continue
                
                # 종목 분석
                analysis_result = self.analyze_stock(stock_code)
                self.last_check_time[stock_code] = now
                
                if analysis_result.get("is_buy_signal", False):
                    # 매수 후보 목록에 추가
                    buy_candidates.append(analysis_result)
            
            # 매수 후보가 있으면 점수 기반으로 정렬
            if buy_candidates:
                # 후보 종목들에 점수 부여
                for candidate in buy_candidates:
                    # 기본 점수
                    score = 1
                    
                    # 전략별 가중치 적용
                    strategy_name = candidate.get("strategy", "RSI")
                    strategy_weight = self.config.get("strategy_weights", {}).get(strategy_name, 1.0)
                    score *= strategy_weight
                    
                    candidate["score"] = score
                
                # 점수 기준 내림차순 정렬
                buy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
                
                # 최소 거래 금액 설정 확인
                min_trading_amount = self.config.get("min_trading_amount", 500000)  # 기본값 50만원
                
                # 상위 종목부터 매수 시도
                for candidate in buy_candidates:
                    if available_slots <= 0:
                        break
                        
                    stock_code = candidate.get("stock_code")
                    stock_name = candidate.get("stock_name", stock_code)
                    current_price = candidate.get("current_price", 0)
                    strategy_name = candidate.get("strategy", "RSI")
                    
                    logger.info(f"매수 후보: {stock_code} ({stock_name}), 전략: {strategy_name}, 점수: {candidate.get('score', 0)}, 가격: {current_price:,}원")
                    logger.info(f"매수 이유: {candidate.get('reason', '')}")
                    
                    # 종목별 예산 배분 계산
                    stock_info = self.watch_list_info.get(stock_code, {})
                    allocation_ratio = stock_info.get("allocation_ratio", 0.2)  # 기본값 20%
                    
                    # 예산 내에서 매수 수량 결정
                    allocated_budget = min(self.total_budget * allocation_ratio, available_cash)
                    
                    # 분할 매수 전략 적용 - 첫 매수는 할당 예산의 40~60% 사용
                    split_ratio = random.uniform(0.4, 0.6)  # 40~60% 랜덤 비율
                    first_buy_budget = allocated_budget * split_ratio
                    
                    # 최소 거래 금액 확인
                    if first_buy_budget < min_trading_amount:
                        logger.info(f"종목 {stock_code} 매수 예산({first_buy_budget:,.0f}원)이 최소 거래 금액({min_trading_amount:,}원)보다 작습니다. 매수 건너뜀.")
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
                        if buy_amount < min_trading_amount:
                            logger.info(f"종목 {stock_code} 매수 금액({buy_amount:,.0f}원)이 최소 거래 금액({min_trading_amount:,}원)보다 작습니다. 매수 건너뜀.")
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
                            
                            # 보유 종목에 추가
                            self.holdings[stock_code] = {
                                "quantity": quantity,
                                "avg_price": avg_price,
                                "current_price": current_price,
                                "buy_date": now.strftime("%Y%m%d"),
                                "highest_price": current_price,
                                "trailing_stop_price": 0,
                                "strategy": strategy_name,
                                "split_buy": True,
                                "initial_budget": allocated_budget,
                                "used_budget": buy_amount,
                                "remaining_budget": allocated_budget - buy_amount
                            }
                            
                            # 트레일링 스탑 가격 설정 (TrailingStopStrategy 경우)
                            strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
                            if isinstance(strategy, TrailingStopStrategy):
                                trailing_pct = strategy.params.get("trailing_stop_pct", 2.0)
                                self.holdings[stock_code]["trailing_stop_price"] = current_price * (1 - trailing_pct/100)
                                
                            self._save_holdings()
                            
                            # 사용 가능한 슬롯 감소
                            available_slots -= 1
                        else:
                            logger.error(f"매수 주문 실패: {stock_code}, {order_result}")
                
            # 보유 종목 중 분할 매수가 가능한 종목 추가 매수 검토
            for stock_code, holding_info in list(self.holdings.items()):
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
                
                # 추가 매수 조건: 현재 가격이 평균단가보다 낮을 때
                if current_price < avg_price * 0.98:  # 2% 이상 하락했을 때
                    remaining_budget = holding_info.get("remaining_budget", 0)
                    min_trading_amount = self.config.get("min_trading_amount", 500000)
                    
                    # 최소 거래 금액 확인
                    if remaining_budget < min_trading_amount:
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
                        if add_buy_amount < min_trading_amount:
                            continue
                            
                        # 시장가 추가 매수
                        logger.info(f"분할 매수 - 추가 매수 시도: {stock_code}, {add_quantity}주, 현재가: {current_price}원, 평단가: {avg_price}원")
                        
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
                            if self.holdings[stock_code]["remaining_budget"] < min_trading_amount:
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
                "max_drawdown": 0,
                "strategy_performance": {}
            }
            
            total_capital = self.total_budget
            virtual_holdings = {}
            trades = []
            max_holdings_count = self.max_stocks  # 최대 동시 보유 종목 수 제한
            
            try:
                # 관심종목 반복
                for stock_code in self.watch_list:
                    # 종목 정보 가져오기
                    stock_info = self.watch_list_info.get(stock_code, {})
                    allocation_ratio = stock_info.get("allocation_ratio", 0.2)  # 기본값 20%
                    strategy_name = stock_info.get("strategy", "RSI")  # 기본 전략 RSI
                    
                    # 전략 인스턴스 가져오기
                    strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
                    
                    if strategy is None:
                        logger.warning(f"백테스트: 종목 {stock_code}에 대한 전략 {strategy_name}을 찾을 수 없습니다.")
                        continue
                    
                    # 일봉 데이터 조회
                    daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 200, adj_ok=1)
                    
                    if daily_data is None or daily_data.empty:
                        logger.warning(f"백테스트: 종목 {stock_code} 일봉 데이터가 없습니다.")
                        continue

                    # 백테스트 기간에 해당하는 데이터만 필터링
                    try:
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
                        
                        # 필터링 결과가 비어있는 경우 확인
                        if filtered_data.empty:
                            logger.warning(f"백테스트: 종목 {stock_code} 지정된 기간({start_date_dt} ~ {end_date_dt}) 내 데이터가 없습니다.")
                            continue
                        
                    except Exception as e:
                        logger.error(f"데이터 필터링 중 오류: {e}")
                        # 필터링 실패 시 원본 데이터 사용
                        filtered_data = daily_data.copy()
                        logger.warning(f"필터링 실패로 전체 데이터 사용: {len(filtered_data)}개")

                    logger.info(f"종목 {stock_code} 백테스트 데이터 기간: {filtered_data.index[0]} ~ {filtered_data.index[-1]}")

                    # 전략 성능 기록용 변수 초기화
                    if strategy_name not in backtest_results["strategy_performance"]:
                        backtest_results["strategy_performance"][strategy_name] = {
                            "trades_count": 0,
                            "win_count": 0,
                            "total_profit": 0,
                            "total_loss": 0,
                            "win_rate": 0
                        }

                    # 날짜별 시뮬레이션
                    for i in range(20, len(filtered_data)):  # 지표 계산을 위해 20일 이후부터 시작
                        date = filtered_data.index[i]
                        current_price = filtered_data.iloc[i]['close']
                        
                        # 데이터 슬라이스 (현재까지의 데이터)
                        current_data = filtered_data.iloc[:i+1].copy()
                        
                        # 보유중인 종목인지 확인
                        if stock_code in virtual_holdings:
                            # 매도 조건 확인
                            holding_info = virtual_holdings[stock_code]
                            holding_info["current_price"] = current_price
                            
                            # 매도 신호 분석
                            sell_result = strategy.analyze_sell_signal(current_data, holding_info, current_price)
                            
                            if sell_result.get("is_sell_signal", False):
                                # 매도 실행
                                quantity = holding_info["quantity"]
                                avg_price = holding_info["avg_price"]
                                sell_amount = current_price * quantity
                                profit = sell_amount - (avg_price * quantity)
                                profit_percent = ((current_price / avg_price) - 1) * 100
                                
                                # 자본 업데이트
                                total_capital += sell_amount
                                
                                # 거래 기록
                                trade_record = {
                                    "stock_code": stock_code,
                                    "stock_name": stock_info.get("name", stock_code),
                                    "action": "SELL",
                                    "strategy": strategy_name,
                                    "reason": sell_result.get("reason", ""),
                                    "date": date,
                                    "price": current_price,
                                    "quantity": quantity,
                                    "profit_loss": profit,
                                    "profit_loss_percent": profit_percent
                                }
                                
                                trades.append(trade_record)
                                
                                # 전략 성능 업데이트
                                backtest_results["strategy_performance"][strategy_name]["trades_count"] += 1
                                if profit > 0:
                                    backtest_results["strategy_performance"][strategy_name]["win_count"] += 1
                                    backtest_results["strategy_performance"][strategy_name]["total_profit"] += profit
                                else:
                                    backtest_results["strategy_performance"][strategy_name]["total_loss"] += profit
                                
                                # 보유 종목에서 제거
                                del virtual_holdings[stock_code]
                            
                        else:
                            # 최대 보유 종목 수 확인
                            if len(virtual_holdings) >= max_holdings_count:
                                continue
                                
                            # 매수 신호 분석
                            buy_result = strategy.analyze_buy_signal(current_data, None, current_price)
                            
                            if buy_result.get("is_buy_signal", False) and total_capital > current_price:
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
                                        "buy_date": date,
                                        "highest_price": current_price,
                                        "trailing_stop_price": 0,
                                        "current_price": current_price,
                                        "strategy": strategy_name
                                    }
                                    
                                    # 트레일링 스탑 설정 (TrailingStopStrategy 경우)
                                    if isinstance(strategy, TrailingStopStrategy):
                                        trailing_pct = strategy.params.get("trailing_stop_pct", 2.0)
                                        virtual_holdings[stock_code]["trailing_stop_price"] = current_price * (1 - trailing_pct/100)
                                    
                                    # 거래 기록
                                    trade_record = {
                                        "stock_code": stock_code,
                                        "stock_name": stock_info.get("name", stock_code),
                                        "action": "BUY",
                                        "strategy": strategy_name,
                                        "reason": buy_result.get("reason", ""),
                                        "date": date,
                                        "price": current_price,
                                        "quantity": quantity,
                                        "amount": buy_amount
                                    }
                                    
                                    trades.append(trade_record)
                    
                # 백테스트 종료 시점에 보유중인 종목 청산
                for stock_code, holding in virtual_holdings.items():
                    # 마지막 가격으로 청산
                    strategy_name = holding.get("strategy", "RSI")
                    stock_info = self.watch_list_info.get(stock_code, {})
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
                        trade_record = {
                            "stock_code": stock_code,
                            "stock_name": stock_info.get("name", stock_code),
                            "action": "SELL",
                            "strategy": strategy_name,
                            "reason": "백테스트 종료",
                            "date": end_date_dt if isinstance(end_date_dt, datetime.datetime) else pd.to_datetime(end_date),
                            "price": last_price,
                            "quantity": quantity,
                            "profit_loss": profit,
                            "profit_loss_percent": profit_percent
                        }
                        
                        trades.append(trade_record)
                        
                        # 전략 성능 업데이트
                        if strategy_name in backtest_results["strategy_performance"]:
                            backtest_results["strategy_performance"][strategy_name]["trades_count"] += 1
                            if profit > 0:
                                backtest_results["strategy_performance"][strategy_name]["win_count"] += 1
                                backtest_results["strategy_performance"][strategy_name]["total_profit"] += profit
                            else:
                                backtest_results["strategy_performance"][strategy_name]["total_loss"] += profit
                
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
                
                # 전략별 승률 계산
                for strategy_name, perf in backtest_results["strategy_performance"].items():
                    trades_count = perf["trades_count"]
                    if trades_count > 0:
                        perf["win_rate"] = (perf["win_count"] / trades_count) * 100
                        
                        # 평균 수익/손실 추가
                        if perf["win_count"] > 0:
                            perf["avg_profit"] = perf["total_profit"] / perf["win_count"]
                        if trades_count - perf["win_count"] > 0:
                            perf["avg_loss"] = perf["total_loss"] / (trades_count - perf["win_count"])
                
                # 추가: 종목별 성과 분석
                stock_performance = {}
                for trade in trades:
                    if trade.get("action") != "SELL":
                        continue
                        
                    code = trade.get("stock_code")
                    if code not in stock_performance:
                        stock_performance[code] = {
                            "name": trade.get("stock_name", code),
                            "total_profit": 0,
                            "trades_count": 0,
                            "win_count": 0,
                            "by_strategy": {}
                        }
                    
                    profit = trade.get("profit_loss", 0)
                    strategy = trade.get("strategy", "unknown")
                    
                    # 종목별 성과 업데이트
                    stock_performance[code]["total_profit"] += profit
                    stock_performance[code]["trades_count"] += 1
                    if profit > 0:
                        stock_performance[code]["win_count"] += 1
                    
                    # 종목별 전략별 성과 업데이트
                    if strategy not in stock_performance[code]["by_strategy"]:
                        stock_performance[code]["by_strategy"][strategy] = {
                            "trades_count": 0,
                            "win_count": 0,
                            "total_profit": 0
                        }
                    
                    stock_performance[code]["by_strategy"][strategy]["trades_count"] += 1
                    if profit > 0:
                        stock_performance[code]["by_strategy"][strategy]["win_count"] += 1
                    stock_performance[code]["by_strategy"][strategy]["total_profit"] += profit
                
                # 종목별 승률 계산
                for code in stock_performance:
                    trades_count = stock_performance[code]["trades_count"]
                    if trades_count > 0:
                        stock_performance[code]["win_rate"] = (stock_performance[code]["win_count"] / trades_count) * 100
                    else:
                        stock_performance[code]["win_rate"] = 0
                    
                    # 전략별 승률 계산
                    for strategy, perf in stock_performance[code]["by_strategy"].items():
                        if perf["trades_count"] > 0:
                            perf["win_rate"] = (perf["win_count"] / perf["trades_count"]) * 100
                        else:
                            perf["win_rate"] = 0
                
                backtest_results["stock_performance"] = stock_performance
                
                logger.info(f"백테스트 완료: 최종 자본금 {backtest_results['final_capital']:,.0f}원, " + 
                        f"수익률 {backtest_results['profit_loss_percent']:.2f}%, " +
                        f"승률 {backtest_results['win_rate']:.2f}%")
                
                return backtest_results
            
            except Exception as e:
                logger.exception(f"백테스트 실행 중 오류: {str(e)}")
                return backtest_results

# 설정파일 생성 함수
def create_config_file(config_path: str = "trend_trader_config.json") -> None:
    """기본 설정 파일 생성
    
    Args:
        config_path: 설정 파일 경로
    """
    config = {
        "watch_list": [
            {"code": "005490", "name": "POSCO홀딩스", "allocation_ratio": 0.2, "strategy": "RSI_Default"},
            {"code": "373220", "name": "LG에너지솔루션", "allocation_ratio": 0.2, "strategy": "MACD_Default"},
            {"code": "000660", "name": "SK하이닉스", "allocation_ratio": 0.2, "strategy": "BB_Default"},
            {"code": "035720", "name": "카카오", "allocation_ratio": 0.2, "strategy": "MA_Default"},
            {"code": "005930", "name": "삼성전자", "allocation_ratio": 0.2, "strategy": "Composite_Default"}
        ],
        "total_budget": 5000000,  # 총 투자 예산
        "max_stocks": 5,  # 최대 동시 보유 종목 수
        "min_trading_amount": 500000,  # 최소 거래 금액
        "use_market_trend_filter": True,  # 시장 추세 필터 사용 여부
        "market_index_code": "069500",  # KODEX 200
        
        # 전략 가중치 (백테스트 결과에 따라 조정 가능)
        "strategy_weights": {
            "RSI_Default": 1.0,
            "MACD_Default": 1.0,
            "BB_Default": 1.0,
            "MA_Default": 1.0,
            "Composite_Default": 1.2  # 복합 전략에 가중치 부여
        },
        
        # 전략 정의
        "strategies": {
            # RSI 기반 전략
            "RSI_Default": {
                "type": "RSI",
                "params": {
                    "rsi_period": 14,
                    "rsi_oversold_threshold": 30.0,
                    "rsi_overbought_threshold": 70.0,
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0,
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "use_minute_confirm": True,
                    "use_dynamic_stop": False,
                    "atr_period": 14,
                    "atr_multiplier": 2.0
                }
            },
            "RSI_Aggressive": {
                "type": "RSI",
                "params": {
                    "rsi_period": 14,
                    "rsi_oversold_threshold": 35.0,  # 더 높은 진입점
                    "rsi_overbought_threshold": 65.0,  # 더 낮은 매도점
                    "profit_target": 4.0,  # 낮은 목표 수익률
                    "stop_loss_pct": 2.0,  # 엄격한 손절
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "use_minute_confirm": True,
                    "use_trailing_stop": True,  # 트레일링 스탑 사용
                    "trailing_stop_pct": 2.0
                }
            },
            "RSI_Conservative": {
                "type": "RSI",
                "params": {
                    "rsi_period": 14,
                    "rsi_oversold_threshold": 25.0,  # 더 낮은 진입점
                    "rsi_overbought_threshold": 75.0,  # 더 높은 매도점
                    "profit_target": 7.0,  # 높은 목표 수익률
                    "stop_loss_pct": 4.0,  # 여유로운 손절
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "use_minute_confirm": False,
                    "use_dynamic_stop": True,  # 동적 손절 사용
                    "atr_period": 14,
                    "atr_multiplier": 2.5
                }
            },
            
            # MACD 기반 전략
            "MACD_Default": {
                "type": "MACD",
                "params": {
                    "macd_fast_period": 12,
                    "macd_slow_period": 26,
                    "macd_signal_period": 9,
                    "short_ma_period": 5,
                    "long_ma_period": 20,
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0,
                    "use_minute_confirm": False
                }
            },
            "MACD_TrailingStop": {
                "type": "MACD",
                "params": {
                    "macd_fast_period": 12,
                    "macd_slow_period": 26,
                    "macd_signal_period": 9,
                    "short_ma_period": 5,
                    "long_ma_period": 20,
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0,
                    "use_minute_confirm": False,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 2.0
                }
            },
            
            # 볼린저 밴드 기반 전략
            "BB_Default": {
                "type": "BollingerBand",
                "params": {
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0,
                    "use_stochastic": True,
                    "stoch_k_period": 14,
                    "stoch_d_period": 3,
                    "stoch_oversold_threshold": 20,
                    "stoch_overbought_threshold": 80,
                    "require_stoch_oversold": False
                }
            },
            "BB_StochFilter": {
                "type": "BollingerBand",
                "params": {
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0,
                    "use_stochastic": True,
                    "stoch_k_period": 14,
                    "stoch_d_period": 3,
                    "stoch_oversold_threshold": 20,
                    "stoch_overbought_threshold": 80,
                    "require_stoch_oversold": True,  # 스토캐스틱 필터 적용
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 2.0
                }
            },
            
            # 이동평균선 기반 전략
            "MA_Default": {
                "type": "MovingAverage",
                "params": {
                    "ma_short_period": 5,
                    "ma_mid_period": 20,
                    "ma_long_period": 60,
                    "ma_strategy_type": "golden_cross",  # golden_cross, uptrend, bounce
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0
                }
            },
            "MA_Uptrend": {
                "type": "MovingAverage",
                "params": {
                    "ma_short_period": 5,
                    "ma_mid_period": 20,
                    "ma_long_period": 60,
                    "ma_strategy_type": "uptrend",  # 상승추세 전략
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 2.0
                }
            },
            "MA_Bounce": {
                "type": "MovingAverage",
                "params": {
                    "ma_short_period": 5,
                    "ma_mid_period": 20,
                    "ma_long_period": 0,  # 장기 이평선 사용 안함
                    "ma_strategy_type": "bounce",  # 반등 전략
                    "profit_target": 4.0,
                    "stop_loss_pct": 2.0,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5
                }
            },
            
            # 복합 전략
            "Composite_Default": {
                "type": "Composite",
                "params": {
                    "strategies": ["RSI_Default", "MACD_Default"],
                    "combine_method": "any",  # any, all, majority
                    "profit_target": 5.0,
                    "stop_loss_pct": 3.0
                }
            },
            "Composite_Conservative": {
                "type": "Composite",
                "params": {
                    "strategies": ["RSI_Conservative", "MACD_Default", "BB_Default"],
                    "combine_method": "majority",  # 과반수 이상 동의 필요
                    "profit_target": 6.0,
                    "stop_loss_pct": 3.5,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 2.0
                }
            },
            "Composite_Aggressive": {
                "type": "Composite",
                "params": {
                    "strategies": ["RSI_Aggressive", "MACD_TrailingStop"],
                    "combine_method": "any",  # 한 전략이라도 매수 신호면 매수
                    "profit_target": 4.0,
                    "stop_loss_pct": 2.0,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5
                }
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
                
                # 전략별 성과 출력
                print("\n=== 전략별 성과 ===")
                for strategy_name, perf in results.get("strategy_performance", {}).items():
                    print(f"전략: {strategy_name}")
                    print(f"  - 거래횟수: {perf.get('trades_count', 0)}회")
                    print(f"  - 승률: {perf.get('win_rate', 0):.2f}%")
                    print(f"  - 총 수익: {perf.get('total_profit', 0):,.0f}원")
                    print(f"  - 총 손실: {perf.get('total_loss', 0):,.0f}원")
                    if perf.get('win_count', 0) > 0:
                        print(f"  - 평균 수익: {perf.get('avg_profit', 0):,.0f}원")
                    if perf.get('trades_count', 0) - perf.get('win_count', 0) > 0:
                        print(f"  - 평균 손실: {perf.get('avg_loss', 0):,.0f}원")
                    print()
                
                # 최종 성과 출력
                print("\n=== 백테스트 최종 성과 ===")
                print(f"초기 자본: {results.get('initial_capital', 0):,.0f}원")
                print(f"최종 자본: {results.get('final_capital', 0):,.0f}원")
                print(f"수익률: {results.get('profit_loss_percent', 0):.2f}%")
                print(f"승률: {results.get('win_rate', 0):.2f}%")
                print(f"최대 낙폭: {results.get('max_drawdown', 0):.2f}%")
                print(f"거래횟수: {len([t for t in results.get('trades', []) if t.get('action') == 'SELL'])}회")
                
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