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
    def check_volume_increase(data: pd.DataFrame, period: int = 5) -> bool:
        """거래량 증가 확인
        
        Args:
            data: 가격 데이터가 포함된 DataFrame, 'volume' 컬럼이 필요
            period: 확인 기간
            
        Returns:
            bool: 거래량 증가 여부
        """
        if 'volume' not in data.columns or len(data) < period + 1:
            return False
            
        # 최근 평균 거래량과 이전 평균 거래량 비교
        recent_avg_volume = data['volume'].iloc[-period:].mean()
        prev_avg_volume = data['volume'].iloc[-(period*2):-period].mean()
        
        # 거래량이 20% 이상 증가했는지 확인
        return recent_avg_volume > prev_avg_volume * 1.2


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
    
    # TradingStrategy 클래스의 get_stop_loss_price 메서드 수정 (약 라인 156)
    def get_stop_loss_price(self, daily_data: pd.DataFrame, current_price: float, 
                            avg_price: float) -> float:
        """손절가 계산 (기본 구현)"""
        # ATR 기반 동적 손절가 계산 (변동성에 따른 손절가 조정)
        if not daily_data.empty and len(daily_data) > 20:
            atr = TechnicalIndicators.calculate_atr(daily_data, period=14).iloc[-1]
            if not pd.isna(atr):
                max_loss_percent = self.params.get("stop_loss_pct", 3.0)
                # 손절가를 ATR의 1.5배와 고정 비율 중 작은 값으로 설정
                dynamic_stop = avg_price * (1 - min(atr * 1.5 / avg_price, max_loss_percent/100))
                return dynamic_stop
        
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
        """볼린저 밴드 기반 매수 신호 분석 (더 많은 매수 신호 생성)"""
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
        bb_std = self.params.get("bb_std", 1.8)  # 2.0에서 1.8로 낮춤 (더 빈번한 신호)
        
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )
        
        # 스토캐스틱 계산
        use_stochastic = self.params.get("use_stochastic", True)
        if use_stochastic:
            k_period = self.params.get("stoch_k_period", 14)
            d_period = self.params.get("stoch_d_period", 3)
            
            daily_data[['K', 'D']] = self.tech_indicators.calculate_stochastic(
                daily_data, k_period=k_period, d_period=d_period
            )

        # RSI 계산 (추가)
        rsi_period = self.params.get("rsi_period", 14)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)

        # 매수 조건 확인
        # 1. 하단 밴드 접촉/근접
        price_near_lower_band = False
        price_below_lower_band = False
        
        if current_price is not None:
            price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[-1] * 1.03  # 1.01에서 1.03으로 완화
            price_below_lower_band = current_price < daily_data['LowerBand'].iloc[-1]
        else:
            price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.03
            price_below_lower_band = daily_data['close'].iloc[-1] < daily_data['LowerBand'].iloc[-1]

        # 밴드 폭 확인 - 너무 좁은 밴드에서는 매수 신호 억제 (조건 완화)
        band_width = (daily_data['UpperBand'] - daily_data['LowerBand']) / daily_data['MiddleBand']
        band_width_too_narrow = band_width.iloc[-1] < 0.025  # 0.04에서 0.025로 하향 (더 많은 거래 허용)
        
        if band_width_too_narrow:
            result["is_buy_signal"] = False
            result["reason"] = "볼린저 밴드 폭이 너무 좁음"
            return result

        # 거래량 확인 (조건 완화)
        volume_increase = self.tech_indicators.check_volume_increase(daily_data, period=5)
        recent_volume = daily_data['volume'].iloc[-1]
        avg_volume = daily_data['volume'].iloc[-10:].mean()
        sufficient_volume = recent_volume >= avg_volume * 0.8  # 거래량이 평균의 80% 이상이면 충분
        
        # OR 조건으로 변경 (둘 중 하나만 만족해도 통과)
        volume_condition = volume_increase or sufficient_volume
        
        if not volume_condition and self.params.get("require_volume_increase", True):
            result["is_buy_signal"] = False
            result["reason"] = "거래량 조건 미충족"
            return result

        # 최근 가격 추세 확인 (조건 완화)
        recent_low_point = False
        price_consolidation = False  # 가격 횡보 패턴 (추가)
        
        if len(daily_data) >= 5:
            # 최근 상승 패턴 확인
            recent_low_point = (daily_data['close'].iloc[-2] > daily_data['close'].iloc[-3] and
                            daily_data['close'].iloc[-1] > daily_data['close'].iloc[-2])
            
            # 가격 횡보 패턴 확인 (추가)
            recent_range = (daily_data['high'].iloc[-5:].max() - daily_data['low'].iloc[-5:].min()) / daily_data['close'].iloc[-1]
            price_consolidation = recent_range < 0.05  # 최근 5일간 변동폭이 5% 미만
            
        # 가격 조건 - OR 조건으로 변경
        price_pattern = recent_low_point or price_consolidation
            
        result["signals"]["daily"]["recent_low_point"] = recent_low_point        
        result["signals"]["daily"]["price_consolidation"] = price_consolidation
        result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
        result["signals"]["daily"]["below_lower_band"] = price_below_lower_band
        
        # 2. 밴드 폭 확장/수축 확인
        band_width_expanding = False
        
        if len(band_width) >= 3:
            if band_width.iloc[-1] > band_width.iloc[-2]:  # 2개 연속에서 1개만 커도 통과하도록 변경
                band_width_expanding = True
                
        result["signals"]["daily"]["band_width_expanding"] = band_width_expanding
        
        # 3. 스토캐스틱 과매도 또는 RSI 과매도 확인 (조건 완화 - OR 조건)
        stoch_oversold = False
        rsi_oversold = False
        
        if use_stochastic and 'K' in daily_data.columns and 'D' in daily_data.columns:
            stoch_oversold_threshold = self.params.get("stoch_oversold_threshold", 25.0)  # 20에서 25로 완화
            if daily_data['K'].iloc[-1] < stoch_oversold_threshold or daily_data['D'].iloc[-1] < stoch_oversold_threshold:  # AND에서 OR로 변경
                stoch_oversold = True
        
        # RSI 과매도 추가
        rsi_oversold_threshold = self.params.get("rsi_oversold_threshold", 35.0)  # 35로 설정
        if daily_data['RSI'].iloc[-1] < rsi_oversold_threshold:
            rsi_oversold = True
                
        result["signals"]["daily"]["stoch_oversold"] = stoch_oversold
        result["signals"]["daily"]["rsi_oversold"] = rsi_oversold
        
        # 기술적 지표 조건 완화 (스토캐스틱 또는 RSI 중 하나만 만족해도 통과)
        indicator_condition = stoch_oversold or rsi_oversold
        
        # 매수 신호 결합 (조건 완화 - 모든 조건 필요 없이 핵심 조건만 충족하면 됨)
        buy_signal = (price_near_lower_band and indicator_condition and 
                    volume_condition)  # 패턴 확인은 선택적
        
        # 최종 매수 신호 및 이유 설정
        result["is_buy_signal"] = buy_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if price_near_lower_band:
                reasons.append("볼린저 밴드 하단 접근")
            if price_below_lower_band:
                reasons.append("볼린저 밴드 하단 돌파")
            if stoch_oversold:
                reasons.append("스토캐스틱 과매도")
            if rsi_oversold:
                reasons.append("RSI 과매도")
            if recent_low_point:
                reasons.append("최근 반등 패턴")
            if price_consolidation:
                reasons.append("가격 횡보 패턴")
            if volume_increase:
                reasons.append("거래량 증가")
            if sufficient_volume:
                reasons.append("충분한 거래량")
                
            result["reason"] = ", ".join(reasons)
        
        return result

    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                            current_price: float) -> Dict[str, any]:
        """볼린저 밴드 기반 매도 신호 분석 (수익률 극대화)"""
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
        bb_std = self.params.get("bb_std", 1.8)  # 2.0에서 1.8로 낮춤 (동일하게 유지)
        
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )
        
        # 스토캐스틱 계산
        use_stochastic = self.params.get("use_stochastic", True)
        if use_stochastic:
            k_period = self.params.get("stoch_k_period", 14)
            d_period = self.params.get("stoch_d_period", 3)
            
            daily_data[['K', 'D']] = self.tech_indicators.calculate_stochastic(
                daily_data, k_period=k_period, d_period=d_period
            )
        
        # RSI 계산 (추가)
        rsi_period = self.params.get("rsi_period", 14)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
        
        # 1. 목표 수익률 달성 - 점진적 목표 수익률 (수정)
        initial_profit_target = self.params.get("profit_target", 3.0)  # 4.0에서 3.0으로 하향
        
        # 보유 기간에 따른 점진적 목표 수익률 조정
        buy_date = holding_info.get("buy_date", datetime.datetime.now().strftime("%Y%m%d"))
        if isinstance(buy_date, str):
            buy_date = datetime.datetime.strptime(buy_date, "%Y%m%d")
        current_date = datetime.datetime.now()
        holding_days = (current_date - buy_date).days
        
        # 보유 기간이 길어질수록 목표 수익률 점진적 하향
        if holding_days > 10:
            adjusted_profit_target = initial_profit_target * 0.8  # 10일 이상 보유 시 20% 하향
        elif holding_days > 5:
            adjusted_profit_target = initial_profit_target * 0.9  # 5일 이상 보유 시 10% 하향
        else:
            adjusted_profit_target = initial_profit_target
            
        if profit_percent >= adjusted_profit_target:
            result["is_sell_signal"] = True
            result["reason"] = f"목표 수익률 달성: {profit_percent:.2f}% (목표: {adjusted_profit_target:.2f}%)"
            return result
        
        # 2. 손절 조건 - 작은 수익 구간 보호 (수정)
        stop_loss_pct = self.params.get("stop_loss_pct", 2.0)
        
        # 수익 중에는 손절선 상향 조정 (이익 보호)
        if profit_percent > 1.5:  # 1.5% 이상 수익 중이면
            dynamic_stop_loss = 0.8 * profit_percent  # 최고 수익의 80% 수준으로 손절선 상향
            if profit_percent - dynamic_stop_loss > 1.0:  # 최소 1% 이상 수익 보호
                stop_loss_pct = dynamic_stop_loss
        
        if profit_percent <= -stop_loss_pct:
            result["is_sell_signal"] = True
            result["reason"] = f"손절 조건 발동: {profit_percent:.2f}%"
            return result
        
        # 3. 상단 밴드 접촉/돌파
        price_near_upper_band = current_price >= daily_data['UpperBand'].iloc[-1] * 0.97  # 0.99에서 0.97로 완화
        
        if price_near_upper_band and profit_percent > 0:  # 이익 중일 때만 실행
            result["is_sell_signal"] = True
            result["reason"] = f"볼린저 밴드 상단 접근, 수익률: {profit_percent:.2f}%"
            return result
        
        # 4. 스토캐스틱 과매수 확인 또는 RSI 과매수 (조건 강화)
        if use_stochastic and 'K' in daily_data.columns and 'D' in daily_data.columns:
            stoch_overbought_threshold = self.params.get("stoch_overbought_threshold", 75.0)  # 80에서 75로 완화
            if (daily_data['K'].iloc[-1] > stoch_overbought_threshold and daily_data['D'].iloc[-1] > stoch_overbought_threshold) and profit_percent > 0:
                result["is_sell_signal"] = True
                result["reason"] = f"스토캐스틱 과매수, 수익률: {profit_percent:.2f}%"
                return result
        
        # RSI 과매수 확인 (추가)
        rsi_overbought_threshold = self.params.get("rsi_overbought_threshold", 65.0)  # 70에서 65로 완화
        if daily_data['RSI'].iloc[-1] > rsi_overbought_threshold and profit_percent > 0:
            result["is_sell_signal"] = True
            result["reason"] = f"RSI 과매수, 수익률: {profit_percent:.2f}%"
            return result
        
        # 5. 수익 추세 반전 확인 (추가)
        if profit_percent > 1.0:  # 1% 이상 수익 중일 때
            if len(daily_data) >= 3:
                # 3일 연속 종가 하락 확인
                price_down_trend = (daily_data['close'].iloc[-1] < daily_data['close'].iloc[-2] < daily_data['close'].iloc[-3])
                
                if price_down_trend:
                    result["is_sell_signal"] = True
                    result["reason"] = f"수익 중 가격 하락세 확인, 수익률: {profit_percent:.2f}%"
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

# 멀티타임프레임 RSI 전략
class MultiTimeframeRSIStrategy(TradingStrategy):
    """두 개의 타임프레임(일봉, 주봉)에서 RSI 확인"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """멀티타임프레임 RSI 매수 신호 분석"""
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "weekly": {}
            },
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty or len(daily_data) < 30:
            return result
        
        # 일봉 데이터에서 RSI 계산
        rsi_period = self.params.get("rsi_period", 14)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
        
        # 주봉 데이터 생성
        if not isinstance(daily_data.index, pd.DatetimeIndex):
            daily_data.index = pd.to_datetime(daily_data.index)
            
        weekly_data = daily_data.resample('W').agg({
            'open': 'first', 
            'high': 'max', 
            'low': 'min', 
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        # 주봉 RSI 계산
        weekly_data['RSI'] = self.tech_indicators.calculate_rsi(weekly_data, period=rsi_period)
        
        # 과매도 확인
        daily_rsi = daily_data['RSI'].iloc[-1]
        daily_rsi_oversold = self.tech_indicators.is_oversold_rsi(
            daily_rsi, 
            self.params.get("daily_rsi_oversold_threshold", 35.0)
        )
        
        weekly_rsi = weekly_data['RSI'].iloc[-1] if not weekly_data.empty else None
        weekly_rsi_oversold = self.tech_indicators.is_oversold_rsi(
            weekly_rsi, 
            self.params.get("weekly_rsi_oversold_threshold", 40.0)
        ) if weekly_rsi is not None else False
        
        # 볼린저 밴드 확인 (일봉)
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )
        
        # 하단 밴드 접근 확인
        price_near_lower_band = False
        if current_price is not None:
            price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[-1] * 1.02
        else:
            price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.02
            
        result["signals"]["daily"]["rsi_oversold"] = daily_rsi_oversold
        result["signals"]["daily"]["rsi_value"] = daily_rsi
        result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
        
        if weekly_rsi is not None:
            result["signals"]["weekly"]["rsi_oversold"] = weekly_rsi_oversold
            result["signals"]["weekly"]["rsi_value"] = weekly_rsi
        
        # 매수 신호 조합
        # 1. 일봉 RSI 과매도 + 주봉 RSI 과매도/하락 중이면 강한 신호
        weekly_rsi_declining = False
        if len(weekly_data) >= 2:
            weekly_rsi_declining = weekly_data['RSI'].iloc[-1] < weekly_data['RSI'].iloc[-2]
            
        strong_signal = daily_rsi_oversold and (weekly_rsi_oversold or weekly_rsi_declining)
        
        # 2. 일봉 RSI 과매도 + 볼린저 밴드 하단 접근도 매수 신호
        band_signal = daily_rsi_oversold and price_near_lower_band
        
        # 최종 매수 신호
        result["is_buy_signal"] = strong_signal or band_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if daily_rsi_oversold:
                reasons.append(f"일봉 RSI 과매도 ({daily_rsi:.2f})")
            if weekly_rsi_oversold:
                reasons.append(f"주봉 RSI 과매도 ({weekly_rsi:.2f})")
            elif weekly_rsi_declining:
                reasons.append(f"주봉 RSI 하락 중 ({weekly_rsi:.2f})")
            if price_near_lower_band:
                reasons.append("볼린저 밴드 하단 접근")
                
            result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """멀티타임프레임 RSI 매도 신호 분석"""
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
        
        # 일봉 RSI 계산
        rsi_period = self.params.get("rsi_period", 14)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
        daily_rsi = daily_data['RSI'].iloc[-1]
        
        # 주봉 데이터 생성 및 RSI 계산
        if not isinstance(daily_data.index, pd.DatetimeIndex):
            daily_data.index = pd.to_datetime(daily_data.index)
            
        weekly_data = daily_data.resample('W').agg({
            'open': 'first', 
            'high': 'max', 
            'low': 'min', 
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        weekly_data['RSI'] = self.tech_indicators.calculate_rsi(weekly_data, period=rsi_period)
        weekly_rsi = weekly_data['RSI'].iloc[-1] if not weekly_data.empty else None
        
        # 볼린저 밴드 계산
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
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
        
        # 3. 일봉 RSI 과매수 영역
        daily_rsi_overbought_threshold = self.params.get("daily_rsi_overbought_threshold", 65.0)
        if self.tech_indicators.is_overbought_rsi(daily_rsi, daily_rsi_overbought_threshold):
            result["is_sell_signal"] = True
            result["reason"] = f"일봉 RSI 과매수 영역: {daily_rsi:.2f}"
            return result
        
        # 4. 주봉 RSI 과매수 영역 (더 강한 시그널)
        if weekly_rsi is not None:
            weekly_rsi_overbought_threshold = self.params.get("weekly_rsi_overbought_threshold", 70.0)
            if self.tech_indicators.is_overbought_rsi(weekly_rsi, weekly_rsi_overbought_threshold):
                result["is_sell_signal"] = True
                result["reason"] = f"주봉 RSI 과매수 영역: {weekly_rsi:.2f}"
                return result
        
        # 5. 상단 밴드 접촉 + 일정 수익률 달성
        min_profit_for_band_sell = self.params.get("min_profit_for_band_sell", 2.0)
        if profit_percent >= min_profit_for_band_sell:
            price_near_upper_band = current_price >= daily_data['UpperBand'].iloc[-1] * 0.98
            if price_near_upper_band:
                result["is_sell_signal"] = True
                result["reason"] = f"볼린저 밴드 상단 접촉 + 수익률 {profit_percent:.2f}%"
                return result
        
        return result    
    
class HybridTrendStrategy(TradingStrategy):
    """추세추종과 역추세 접근법을 결합한 하이브리드 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """하이브리드 전략 매수 신호 분석"""
        result = {
            "is_buy_signal": False,
            "signals": {
                "daily": {},
                "trend_status": {}
            },
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty or len(daily_data) < 30:
            return result
        
        # 추세 강도 판단
        # 1. ADX 계산 (Average Directional Index - 추세 강도 지표)
        # ADX 계산을 위한 함수 (기존 TechnicalIndicators에 추가 필요)
        def calculate_adx(data, period=14):
            high = data['high']
            low = data['low']
            close = data['close']
            
            # +DM, -DM 계산
            plus_dm = high.diff()
            minus_dm = low.diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm > 0] = 0
            minus_dm = abs(minus_dm)
            
            # +DM > -DM 및 -DM > +DM 조건 적용
            plus_dm[(plus_dm < minus_dm) | (plus_dm == minus_dm)] = 0
            minus_dm[(minus_dm < plus_dm) | (minus_dm == plus_dm)] = 0
            
            # TR 계산
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # 평활화 적용
            smoothed_tr = tr.rolling(window=period).sum()
            smoothed_plus_dm = plus_dm.rolling(window=period).sum()
            smoothed_minus_dm = minus_dm.rolling(window=period).sum()
            
            # +DI, -DI 계산
            plus_di = 100 * (smoothed_plus_dm / smoothed_tr)
            minus_di = 100 * (smoothed_minus_dm / smoothed_tr)
            
            # DX 계산
            dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
            
            # ADX 계산 (DX의 평활화)
            adx = dx.rolling(window=period).mean()
            
            return pd.DataFrame({
                'ADX': adx,
                'Plus_DI': plus_di,
                'Minus_DI': minus_di
            })
        
        # ADX 계산
        adx_period = self.params.get("adx_period", 14)
        adx_data = calculate_adx(daily_data, period=adx_period)
        
        adx_value = adx_data['ADX'].iloc[-1]
        plus_di = adx_data['Plus_DI'].iloc[-1]
        minus_di = adx_data['Minus_DI'].iloc[-1]
        
        # 추세 강도 및 방향 판단
        is_strong_trend = adx_value > self.params.get("strong_trend_threshold", 25)
        is_uptrend = plus_di > minus_di
        is_downtrend = minus_di > plus_di
        is_sideways = adx_value < self.params.get("sideways_threshold", 20)
        
        result["signals"]["trend_status"]["adx"] = adx_value
        result["signals"]["trend_status"]["is_strong_trend"] = is_strong_trend
        result["signals"]["trend_status"]["is_uptrend"] = is_uptrend
        result["signals"]["trend_status"]["is_downtrend"] = is_downtrend
        result["signals"]["trend_status"]["is_sideways"] = is_sideways
        
        # 시장 상황에 따른 전략 적용
        # 1. 추세장일 때는 추세추종 전략 (이동평균선, MACD)
        if is_strong_trend and is_uptrend:
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
            
            # 1. MACD 상향돌파 확인
            macd_cross_up = False
            if len(daily_data) >= 2:
                if daily_data['MACD'].iloc[-2] < daily_data['Signal'].iloc[-2] and \
                   daily_data['MACD'].iloc[-1] >= daily_data['Signal'].iloc[-1]:
                    macd_cross_up = True
            
            # 2. 히스토그램 상승 확인
            histogram_rising = False
            if len(daily_data) >= 2:
                if daily_data['Histogram'].iloc[-1] > daily_data['Histogram'].iloc[-2]:
                    histogram_rising = True
            
            result["signals"]["daily"]["macd_cross_up"] = macd_cross_up
            result["signals"]["daily"]["histogram_rising"] = histogram_rising
            
            # 추세 추종 매수 신호
            trend_buy_signal = macd_cross_up or histogram_rising
            
            if trend_buy_signal:
                result["is_buy_signal"] = True
                reasons = []
                reasons.append(f"강한 상승 추세 (ADX: {adx_value:.2f})")
                if macd_cross_up:
                    reasons.append("MACD 상향돌파")
                if histogram_rising:
                    reasons.append("MACD 히스토그램 상승")
                result["reason"] = ", ".join(reasons)
        
        # 2. 횡보장이나 약한 하락장일 때는 역추세 전략 (RSI, 볼린저 밴드)
        elif is_sideways or (is_downtrend and not is_strong_trend):
            # RSI 계산
            rsi_period = self.params.get("rsi_period", 14)
            daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
            
            # 볼린저 밴드 계산
            bb_period = self.params.get("bb_period", 20)
            bb_std = self.params.get("bb_std", 2.0)
            daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
                daily_data, period=bb_period, num_std=bb_std
            )
            
            # 역추세 매수 조건 확인
            rsi_value = daily_data['RSI'].iloc[-1]
            rsi_oversold = self.tech_indicators.is_oversold_rsi(
                rsi_value, 
                self.params.get("rsi_oversold_threshold", 35.0)
            )
            
            # 볼린저 밴드 하단 접근 확인
            price_near_lower_band = False
            if current_price is not None:
                price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[-1] * 1.02
            else:
                price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.02
                
            result["signals"]["daily"]["rsi_oversold"] = rsi_oversold
            result["signals"]["daily"]["rsi_value"] = rsi_value
            result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
            
            # 역추세 매수 신호
            counter_trend_buy_signal = rsi_oversold and price_near_lower_band
            
            if counter_trend_buy_signal:
                result["is_buy_signal"] = True
                market_type = "횡보장" if is_sideways else "약한 하락장"
                reasons = [
                    f"{market_type} (ADX: {adx_value:.2f})",
                    f"RSI 과매도 ({rsi_value:.2f})",
                    "볼린저 밴드 하단 접근"
                ]
                result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """하이브리드 전략 매도 신호 분석"""
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
        
        # 먼저 기본 매도 조건 확인
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
        
        # ADX 계산을 위한 함수 (이전과 동일)
        def calculate_adx(data, period=14):
            high = data['high']
            low = data['low']
            close = data['close']
            
            plus_dm = high.diff()
            minus_dm = low.diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm > 0] = 0
            minus_dm = abs(minus_dm)
            
            plus_dm[(plus_dm < minus_dm) | (plus_dm == minus_dm)] = 0
            minus_dm[(minus_dm < plus_dm) | (minus_dm == plus_dm)] = 0
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            smoothed_tr = tr.rolling(window=period).sum()
            smoothed_plus_dm = plus_dm.rolling(window=period).sum()
            smoothed_minus_dm = minus_dm.rolling(window=period).sum()
            
            plus_di = 100 * (smoothed_plus_dm / smoothed_tr)
            minus_di = 100 * (smoothed_minus_dm / smoothed_tr)
            
            dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
            adx = dx.rolling(window=period).mean()
            
            return pd.DataFrame({
                'ADX': adx,
                'Plus_DI': plus_di,
                'Minus_DI': minus_di
            })
        
        # ADX 계산
        adx_period = self.params.get("adx_period", 14)
        adx_data = calculate_adx(daily_data, period=adx_period)
        
        adx_value = adx_data['ADX'].iloc[-1]
        plus_di = adx_data['Plus_DI'].iloc[-1]
        minus_di = adx_data['Minus_DI'].iloc[-1]
        
        # 추세 강도 및 방향 판단
        is_strong_trend = adx_value > self.params.get("strong_trend_threshold", 25)
        is_uptrend = plus_di > minus_di
        is_downtrend = minus_di > plus_di
        is_sideways = adx_value < self.params.get("sideways_threshold", 20)
        
        # 시장 상황별 매도 로직
        # 1. 강한 상승 추세에서 반전 신호 확인
        if is_strong_trend and is_uptrend:
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
            
            # MACD 하향돌파 확인
            macd_cross_down = False
            if len(daily_data) >= 2:
                if daily_data['MACD'].iloc[-2] > daily_data['Signal'].iloc[-2] and \
                   daily_data['MACD'].iloc[-1] < daily_data['Signal'].iloc[-1]:
                    macd_cross_down = True
            
            if macd_cross_down and profit_percent > 0:
                result["is_sell_signal"] = True
                result["reason"] = f"MACD 하향돌파 (상승 추세 속 매도 신호), 수익률: {profit_percent:.2f}%"
                return result
            
            # 히스토그램 하락 + 일정 수익 달성
            min_profit_for_hist_sell = self.params.get("min_profit_for_hist_sell", 3.0)
            if profit_percent >= min_profit_for_hist_sell:
                histogram_falling = False
                if len(daily_data) >= 2:
                    if daily_data['Histogram'].iloc[-1] < daily_data['Histogram'].iloc[-2]:
                        histogram_falling = True
                
                if histogram_falling:
                    result["is_sell_signal"] = True
                    result["reason"] = f"MACD 히스토그램 하락 + 충분한 수익 ({profit_percent:.2f}%)"
                    return result
        
        # 2. 횡보장이나 약한 하락장에서 매도 신호
        elif is_sideways or (is_downtrend and not is_strong_trend):
            # RSI 계산
            rsi_period = self.params.get("rsi_period", 14)
            daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
            
            # 볼린저 밴드 계산
            bb_period = self.params.get("bb_period", 20)
            bb_std = self.params.get("bb_std", 2.0)
            daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
                daily_data, period=bb_period, num_std=bb_std
            )
            
            # RSI 과매수 확인
            rsi_value = daily_data['RSI'].iloc[-1]
            rsi_overbought = self.tech_indicators.is_overbought_rsi(
                rsi_value, 
                self.params.get("rsi_overbought_threshold", 65.0)
            )
            
            # 볼린저 밴드 상단 접근 확인
            price_near_upper_band = current_price >= daily_data['UpperBand'].iloc[-1] * 0.98
                
            # 역추세 매도 조건
            if (rsi_overbought or price_near_upper_band) and profit_percent > 0:
                reasons = []
                market_type = "횡보장" if is_sideways else "약한 하락장"
                reasons.append(f"{market_type} (ADX: {adx_value:.2f})")
                
                if rsi_overbought:
                    reasons.append(f"RSI 과매수 ({rsi_value:.2f})")
                if price_near_upper_band:
                    reasons.append("볼린저 밴드 상단 접근")
                
                reasons.append(f"수익률: {profit_percent:.2f}%")
                
                result["is_sell_signal"] = True
                result["reason"] = ", ".join(reasons)
                return result
        
        # 3. 강한 하락 추세 감지 시 손절 대비 빠른 매도
        if is_strong_trend and is_downtrend:
            # 약세장에서는 수익이 있다면 빠르게 매도
            if profit_percent > 0:
                result["is_sell_signal"] = True
                result["reason"] = f"강한 하락 추세 감지 (ADX: {adx_value:.2f}), 수익 확정: {profit_percent:.2f}%"
                return result
            # 수익이 없더라도 손절 기준보다 약한 기준으로 매도
            elif profit_percent < 0 and profit_percent > -stop_loss_pct * 0.7:
                result["is_sell_signal"] = True
                result["reason"] = f"강한 하락 추세에서 손실 최소화 매도: {profit_percent:.2f}%"
                return result
        
        return result

class EnhancedMACDStrategy(TradingStrategy):
    """상승장 특화 MACD 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """향상된 MACD 매수 신호 분석"""
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
        
        # MACD 설정 (더 짧은 기간으로 설정하여 더 빠른 시그널 포착)
        fast_period = self.params.get("macd_fast_period", 8)  # 12에서 8로 변경
        slow_period = self.params.get("macd_slow_period", 21) # 26에서 21로 변경
        signal_period = self.params.get("macd_signal_period", 7)  # 9에서 7로 변경
        
        daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
            daily_data, 
            fast_period=fast_period, 
            slow_period=slow_period, 
            signal_period=signal_period
        )
        
        # 이동평균선 계산
        short_ma_period = self.params.get("short_ma_period", 3)  # 5에서 3으로 변경
        mid_ma_period = self.params.get("mid_ma_period", 10)     # 10 추가
        long_ma_period = self.params.get("long_ma_period", 20)   # 20 유지
        
        daily_data['MA_short'] = daily_data['close'].rolling(window=short_ma_period).mean()
        daily_data['MA_mid'] = daily_data['close'].rolling(window=mid_ma_period).mean()
        daily_data['MA_long'] = daily_data['close'].rolling(window=long_ma_period).mean()

        # 매수 조건 확인
        # 1. MACD 상향돌파 또는 히스토그램 증가
        macd_cross_up = False
        try:
            if len(daily_data) >= 2:
                if daily_data['MACD'].iloc[-2] < daily_data['Signal'].iloc[-2] and \
                daily_data['MACD'].iloc[-1] >= daily_data['Signal'].iloc[-1]:
                    macd_cross_up = True
        except:
            pass
            
        histogram_rising = False
        try:
            if len(daily_data) >= 3:  # 2개가 아닌 3개의 기간으로 확인하여 더 강한 상승 확인
                if daily_data['Histogram'].iloc[-1] > daily_data['Histogram'].iloc[-2] > daily_data['Histogram'].iloc[-3]:
                    histogram_rising = True
            elif len(daily_data) >= 2:
                if daily_data['Histogram'].iloc[-1] > daily_data['Histogram'].iloc[-2]:
                    histogram_rising = True
        except:
            pass
        
        # 2. 이동평균선 배열 상태 확인 (상승 추세 확인)
        ma_aligned_uptrend = False
        if len(daily_data) > long_ma_period:
            ma_short = daily_data['MA_short'].iloc[-1]
            ma_mid = daily_data['MA_mid'].iloc[-1]
            ma_long = daily_data['MA_long'].iloc[-1]
            
            # 이동평균선이 정렬되어 있는지 확인 (상승 추세)
            ma_aligned_uptrend = ma_short > ma_mid > ma_long
        
        # 3. 모멘텀 확인
        momentum_period = self.params.get("momentum_period", 10)
        daily_data['Momentum'] = self.tech_indicators.calculate_momentum(daily_data, period=momentum_period)
        momentum_positive = daily_data['Momentum'].iloc[-1] > 0 if len(daily_data) > momentum_period else False
        
        # 4. 볼륨 증가 확인
        volume_increase = self.tech_indicators.check_volume_increase(daily_data, period=5)
        
        # 결과 저장
        result["signals"]["daily"]["macd_cross_up"] = macd_cross_up
        result["signals"]["daily"]["histogram_rising"] = histogram_rising
        result["signals"]["daily"]["ma_aligned_uptrend"] = ma_aligned_uptrend
        result["signals"]["daily"]["momentum_positive"] = momentum_positive
        result["signals"]["daily"]["volume_increase"] = volume_increase
        
        # 매수 신호 결합 (상승장 특화 - 빠른 진입을 위해 조건 완화)
        primary_condition = macd_cross_up or (histogram_rising and ma_aligned_uptrend)
        secondary_condition = momentum_positive or volume_increase
        
        # 매수 신호
        result["is_buy_signal"] = primary_condition and secondary_condition
        
        if result["is_buy_signal"]:
            reasons = []
            if macd_cross_up:
                reasons.append("MACD 상향돌파")
            if histogram_rising:
                reasons.append("MACD 히스토그램 상승")
            if ma_aligned_uptrend:
                reasons.append(f"이동평균선 정렬 상승추세 ({short_ma_period}/{mid_ma_period}/{long_ma_period}일)")
            if momentum_positive:
                reasons.append(f"{momentum_period}일 모멘텀 양수")
            if volume_increase:
                reasons.append("거래량 증가")
                
            result["reason"] = ", ".join(reasons)
        
        return result
    
    def analyze_sell_signal(self, daily_data: pd.DataFrame, holding_info: Dict[str, any], 
                           current_price: float) -> Dict[str, any]:
        """향상된 MACD 매도 신호 분석"""
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
        
        # 1. 목표 수익률 달성 (상승장 특화 - 더 높게 설정)
        profit_target = self.params.get("profit_target", 5.0)  # 기본 5%로 유지하되, 트레일링 스탑으로 더 많은 수익 추구
        if profit_percent >= profit_target:
            result["is_sell_signal"] = True
            result["reason"] = f"목표 수익률 달성: {profit_percent:.2f}%"
            return result
        
        # 2. 손절 조건 (상승장 특화 - 약간 넓게 설정)
        stop_loss_pct = self.params.get("stop_loss_pct", 3.0)
        if profit_percent <= -stop_loss_pct:
            result["is_sell_signal"] = True
            result["reason"] = f"손절 조건 발동: {profit_percent:.2f}%"
            return result
        
        # MACD 설정
        fast_period = self.params.get("macd_fast_period", 8)
        slow_period = self.params.get("macd_slow_period", 21)
        signal_period = self.params.get("macd_signal_period", 7)
        
        daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(
            daily_data, 
            fast_period=fast_period, 
            slow_period=slow_period, 
            signal_period=signal_period
        )
        
        # 3. MACD 하향돌파 확인
        macd_cross_down = False
        try:
            if len(daily_data) >= 2:
                if daily_data['MACD'].iloc[-2] > daily_data['Signal'].iloc[-2] and \
                daily_data['MACD'].iloc[-1] < daily_data['Signal'].iloc[-1]:
                    macd_cross_down = True
        except:
            pass
            
        # 4. 히스토그램 하락 확인 (2일 연속)
        histogram_falling = False
        try:
            if len(daily_data) >= 3:
                if daily_data['Histogram'].iloc[-1] < daily_data['Histogram'].iloc[-2] < daily_data['Histogram'].iloc[-3]:
                    histogram_falling = True
            elif len(daily_data) >= 2:
                if daily_data['Histogram'].iloc[-1] < daily_data['Histogram'].iloc[-2]:
                    histogram_falling = True
        except:
            pass
        
        # 5. 모멘텀 하락 확인
        momentum_period = self.params.get("momentum_period", 10)
        daily_data['Momentum'] = self.tech_indicators.calculate_momentum(daily_data, period=momentum_period)
        momentum_negative = daily_data['Momentum'].iloc[-1] < 0 if len(daily_data) > momentum_period else False
        
        # 추가 매도 조건 (상승장 특화 - 이익이 있을 때만 매도)
        macd_based_exit = (macd_cross_down or histogram_falling) and profit_percent > 0
        momentum_based_exit = momentum_negative and profit_percent > 1.0  # 최소 1% 이상 수익일 때
        
        if macd_based_exit:
            result["is_sell_signal"] = True
            reason_parts = []
            if macd_cross_down:
                reason_parts.append("MACD 하향돌파")
            else:
                reason_parts.append("MACD 히스토그램 하락")
            reason_parts.append(f"수익률: {profit_percent:.2f}%")
            result["reason"] = ", ".join(reason_parts)
            return result
        
        if momentum_based_exit:
            result["is_sell_signal"] = True
            result["reason"] = f"모멘텀 하락, 수익률: {profit_percent:.2f}%"
            return result
        
        return result

# RSI 기반 전략 (개선 버전)
class EnhancedRSIStrategy(TradingStrategy):
    """개선된 RSI 전략"""
    
    def analyze_buy_signal(self, daily_data: pd.DataFrame, minute_data: pd.DataFrame = None, 
                          current_price: float = None) -> Dict[str, any]:
        """개선된 RSI 매수 신호 분석"""
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
        
        # RSI 계산 - 여러 기간 사용
        rsi_period_short = self.params.get("rsi_period_short", 9)
        rsi_period = self.params.get("rsi_period", 14)
        rsi_period_long = self.params.get("rsi_period_long", 21)
        
        daily_data['RSI_short'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period_short)
        daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period)
        daily_data['RSI_long'] = self.tech_indicators.calculate_rsi(daily_data, period=rsi_period_long)
        
        # 볼린저 밴드 계산
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(
            daily_data, period=bb_period, num_std=bb_std
        )

        # 매수 조건 확인
        rsi_value = daily_data['RSI'].iloc[-1]
        rsi_short_value = daily_data['RSI_short'].iloc[-1]
        rsi_long_value = daily_data['RSI_long'].iloc[-1]
        
        rsi_oversold_threshold = self.params.get("rsi_oversold_threshold", 35.0)
        
        # 1. RSI 과매도 확인 (다중 기간)
        is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value, rsi_oversold_threshold)
        is_short_oversold = self.tech_indicators.is_oversold_rsi(rsi_short_value, rsi_oversold_threshold)
        is_long_oversold = self.tech_indicators.is_oversold_rsi(rsi_long_value, rsi_oversold_threshold)
        
        result["signals"]["daily"]["rsi_oversold"] = is_oversold
        result["signals"]["daily"]["rsi_short_oversold"] = is_short_oversold
        result["signals"]["daily"]["rsi_long_oversold"] = is_long_oversold
        
        # 2. 볼린저 밴드 하단 접촉
        price_near_lower_band = False
        if current_price is not None:
            price_near_lower_band = current_price <= daily_data['LowerBand'].iloc[-1] * 1.02
        else:
            price_near_lower_band = daily_data['close'].iloc[-1] <= daily_data['LowerBand'].iloc[-1] * 1.02
            
        result["signals"]["daily"]["near_lower_band"] = price_near_lower_band
        
        # 3. RSI 반등 확인 (더 민감한 반응)
        rsi_rebounding = False
        if len(daily_data) >= 3:
            if daily_data['RSI'].iloc[-1] > daily_data['RSI'].iloc[-2] > daily_data['RSI'].iloc[-3]:
                rsi_rebounding = True
        elif len(daily_data) >= 2:
            if daily_data['RSI'].iloc[-1] > daily_data['RSI'].iloc[-2]:
                rsi_rebounding = True
                
        result["signals"]["daily"]["rsi_rebounding"] = rsi_rebounding
        
        # 4. RSI 다이버전스 확인 (가격과 RSI 방향 불일치)
        rsi_divergence = False
        if len(daily_data) >= 5:
            price_lower_low = daily_data['low'].iloc[-1] < min(daily_data['low'].iloc[-5:-1])
            rsi_higher_low = daily_data['RSI'].iloc[-1] > min(daily_data['RSI'].iloc[-5:-1])
            rsi_divergence = price_lower_low and rsi_higher_low
        
        result["signals"]["daily"]["rsi_divergence"] = rsi_divergence
        
        # 매수 신호 결합
        # 1. 기본 RSI 과매도 + 밴드 하단
        basic_signal = is_oversold and price_near_lower_band
        
        # 2. 다중 기간 RSI 일치
        multi_period_signal = (is_short_oversold or is_oversold) and is_long_oversold
        
        # 3. RSI 반등 또는 다이버전스
        enhanced_signal = (is_short_oversold or is_oversold) and (rsi_rebounding or rsi_divergence)
        
        # 분봉 확인 (선택)
        use_minute_confirm = self.params.get("use_minute_confirm", False)
        minute_signal = True  # 기본값
        
        if use_minute_confirm and minute_data is not None and not minute_data.empty:
            minute_data['RSI'] = self.tech_indicators.calculate_rsi(minute_data, period=rsi_period)
            minute_rsi_value = minute_data['RSI'].iloc[-1]
            minute_is_oversold = self.tech_indicators.is_oversold_rsi(minute_rsi_value, rsi_oversold_threshold)
            result["signals"]["minute"]["rsi_oversold"] = minute_is_oversold
            
            # 분봉 반등 확인
            minute_rsi_rebounding = False
            if len(minute_data) >= 3:
                if minute_data['RSI'].iloc[-1] > minute_data['RSI'].iloc[-2] > minute_data['RSI'].iloc[-3]:
                    minute_rsi_rebounding = True
            elif len(minute_data) >= 2:
                if minute_data['RSI'].iloc[-1] > minute_data['RSI'].iloc[-2]:
                    minute_rsi_rebounding = True
                    
            result["signals"]["minute"]["rsi_rebounding"] = minute_rsi_rebounding
            
            minute_signal = minute_is_oversold or minute_rsi_rebounding
        
        # 최종 매수 신호
        result["is_buy_signal"] = (basic_signal or multi_period_signal or enhanced_signal) and minute_signal
        
        if result["is_buy_signal"]:
            reasons = []
            if is_oversold:
                reasons.append(f"RSI 과매도 ({rsi_value:.2f})")
            if is_short_oversold:
                reasons.append(f"단기 RSI 과매도 ({rsi_short_value:.2f})")
            if is_long_oversold:
                reasons.append(f"장기 RSI 과매도 ({rsi_long_value:.2f})")
            if price_near_lower_band:
                reasons.append("볼린저 밴드 하단 접근")
            if rsi_rebounding:
                reasons.append("RSI 반등")
            if rsi_divergence:
                reasons.append("RSI 다이버전스")
                
            result["reason"] = ", ".join(reasons)
        
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
    # TrendFilter 클래스의   메서드 개선 (약 라인 795)
    @staticmethod
    def check_market_trend(market_index_code: str, lookback_days: int = 10) -> bool:
        """시장 추세 확인 (지수 또는 대표 ETF 기반)"""
        try:
            # 지수 또는 ETF 데이터 가져오기
            market_data = KisKR.GetOhlcvNew(market_index_code, 'D', lookback_days+10, adj_ok=1)
            
            if market_data is None or market_data.empty:
                logger.warning(f"시장 지수 데이터({market_index_code})를 가져올 수 없습니다.")
                return False  # 기본값 True에서 False로 변경 - 데이터 없으면 매수 안함
            
            # 이동평균선 계산 (5일, 10일)
            market_data['MA5'] = market_data['close'].rolling(window=5).mean()
            market_data['MA10'] = market_data['close'].rolling(window=10).mean()
            
            # MACD 계산
            market_data[['MACD', 'Signal', 'Histogram']] = TechnicalIndicators.calculate_macd(
                market_data, fast_period=12, slow_period=26, signal_period=9
            )
            
            if len(market_data) < 10:
                return False  # 기본값 True에서 False로 변경 - 데이터 부족하면 매수 안함
                    
            recent_ma5 = market_data['MA5'].iloc[-1]
            recent_ma10 = market_data['MA10'].iloc[-1]
            recent_close = market_data['close'].iloc[-1]
            
            # MACD 히스토그램 방향
            histogram_direction = market_data['Histogram'].diff().iloc[-1] > 0
            
            # 더 엄격한 상승 추세 조건 (AND 조건으로 변경):
            # 1. 종가가 5일선 위에 있고
            # 2. 5일선이 10일선 위에 있고
            # 3. MACD 히스토그램이 상승 중
            is_uptrend = (recent_close > recent_ma5) and (recent_ma5 > recent_ma10) and histogram_direction
            
            return is_uptrend
            
        except Exception as e:
            logger.exception(f"시장 추세 확인 중 오류: {str(e)}")
            return False  # 기본값 True에서 False로 변경 - 오류 발생시 매수 안함

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


    # StrategyManager 클래스의 _create_strategy 메서드 개선4
    def _create_strategy(self, strategy_type: str, strategy_name: str, params: Dict[str, any]) -> TradingStrategy:
        """전략 인스턴스 생성
        
        Args:
            strategy_type: 전략 유형
            strategy_name: 전략 이름
            params: 전략 매개변수
            
        Returns:
            TradingStrategy: 전략 인스턴스
        """
        # 기본 매개변수를 보완하기 위한 공통 설정
        default_params = {
            "profit_target": 5.0,
            "stop_loss_pct": 3.0
        }
        
        # 전략별 기본 매개변수
        strategy_default_params = {
            "RSI": {
                "rsi_period": 14,
                "rsi_oversold_threshold": 30.0,
                "rsi_overbought_threshold": 70.0,
                "bb_period": 20,
                "bb_std": 2.0
            },
            "MACD": {
                "macd_fast_period": 8,  # 12에서 8로 변경
                "macd_slow_period": 21, # 26에서 21로 변경
                "macd_signal_period": 9,
                "short_ma_period": 5,
                "long_ma_period": 20
            },
            "BollingerBand": {
                "bb_period": 20,
                "bb_std": 2.0,
                "stoch_k_period": 14,
                "stoch_d_period": 3,
                "stoch_oversold_threshold": 20,
                "stoch_overbought_threshold": 80
            },
            "MovingAverage": {
                "ma_short_period": 5,
                "ma_mid_period": 20,
                "ma_long_period": 60,
                "ma_strategy_type": "golden_cross"
            },
            # 추가된 전략들의 기본 매개변수
            "EnhancedRSIStrategy": {
                "rsi_period_short": 9,
                "rsi_period": 14,
                "rsi_period_long": 21,
                "rsi_oversold_threshold": 35.0,
                "rsi_overbought_threshold": 65.0,
                "bb_period": 20,
                "bb_std": 2.0
            },
            "EnhancedMACDStrategy": {
                "macd_fast_period": 8,
                "macd_slow_period": 21,
                "macd_signal_period": 7,
                "short_ma_period": 3,
                "mid_ma_period": 10,
                "long_ma_period": 20,
                "momentum_period": 10
            },
            "MultiTimeframeRSIStrategy": {
                "rsi_period": 14,
                "daily_rsi_oversold_threshold": 35.0,
                "daily_rsi_overbought_threshold": 65.0,
                "weekly_rsi_oversold_threshold": 40.0,
                "weekly_rsi_overbought_threshold": 70.0
            },
            "HybridTrendStrategy": {
                "adx_period": 14,
                "strong_trend_threshold": 25,
                "sideways_threshold": 20,
                "macd_fast_period": 12,
                "macd_slow_period": 26,
                "macd_signal_period": 9
            },
            "VolatilityBreakoutStrategy": {
                "volatility_period": 20,
                "k_value": 0.5,
                "ma_short_period": 5,
                "ma_long_period": 20
            },
            # Composite 전략 기본 매개변수
            "Composite": {
                "combine_method": "any",
                "strategies": ["RSI_Default", "BB_StochFilter"]
            },
            # Composite_Premium 전략 기본 매개변수 (실제로는 Composite 타입)
            "Composite_Premium": {
                "combine_method": "any",
                "strategies": ["EnhancedRSIStrategy", "BB_StochFilter"],
                "profit_target": 2.0,
                "stop_loss_pct": 1.8,
                "use_trailing_stop": True,
                "trailing_stop_pct": 1.5,
                "dynamic_trailing": True,
                "min_holding_days": 0
            }
        }
        
        # 기본 매개변수와 전략별 기본 매개변수 적용
        if strategy_type in strategy_default_params:
            merged_params = {**default_params, **strategy_default_params[strategy_type], **params}
        else:
            merged_params = {**default_params, **params}
        
        # 트레일링 스탑 및 동적 손절 매개변수 추가
        if "use_trailing_stop" not in merged_params:
            if strategy_type in ["MACD", "BollingerBand", "EnhancedMACDStrategy", "HybridTrendStrategy"]:
                merged_params["use_trailing_stop"] = True
                merged_params["trailing_stop_pct"] = merged_params.get("trailing_stop_pct", 2.0)
        
        if "use_dynamic_stop" not in merged_params:
            if strategy_type in ["RSI", "EnhancedRSIStrategy", "MultiTimeframeRSIStrategy"]:
                merged_params["use_dynamic_stop"] = True
                merged_params["atr_period"] = merged_params.get("atr_period", 14)
                merged_params["atr_multiplier"] = merged_params.get("atr_multiplier", 2.0)
        
        # 전략 인스턴스 생성
        if strategy_type == "RSI":
            strategy = RSIStrategy(strategy_name, merged_params)
        elif strategy_type == "MACD":
            strategy = MACDStrategy(strategy_name, merged_params)
        elif strategy_type == "BollingerBand":
            strategy = BollingerBandStrategy(strategy_name, merged_params)
        elif strategy_type == "MovingAverage":
            strategy = MovingAverageStrategy(strategy_name, merged_params)
        elif strategy_type == "EnhancedRSIStrategy":
            strategy = EnhancedRSIStrategy(strategy_name, merged_params)
        elif strategy_type == "EnhancedMACDStrategy":
            strategy = EnhancedMACDStrategy(strategy_name, merged_params)
        elif strategy_type == "MultiTimeframeRSIStrategy":
            strategy = MultiTimeframeRSIStrategy(strategy_name, merged_params)
        elif strategy_type == "HybridTrendStrategy":
            strategy = HybridTrendStrategy(strategy_name, merged_params)
        elif strategy_type == "VolatilityBreakoutStrategy":
            # VolatilityBreakoutStrategy는 코드에 구현되어 있지 않은 것 같습니다.
            # 실제 구현이 없다면 이 부분을 제거하거나 에러 처리해야 합니다.
            logger.warning(f"VolatilityBreakoutStrategy 전략이 구현되어 있지 않습니다.")
            strategy = None
        elif strategy_type == "Composite" or strategy_name == "Composite_Premium":
            # 복합 전략 생성
            sub_strategies = []
            for sub_strategy_name in merged_params.get("strategies", []):
                sub_strategy = self.get_strategy(sub_strategy_name)
                if sub_strategy:
                    sub_strategies.append(sub_strategy)
            
            if sub_strategies:
                strategy = CompositeStrategy(strategy_name, sub_strategies, merged_params)
            else:
                logger.warning(f"복합 전략 {strategy_name}에 유효한 하위 전략이 없습니다.")
                strategy = None
        else:
            logger.warning(f"알 수 없는 전략 유형: {strategy_type}")
            strategy = None
        
        # 트레일링 스탑 래핑 확인
        if strategy and merged_params.get("use_trailing_stop", False):
            strategy = TrailingStopStrategy(strategy, merged_params)
        
        return strategy

class TrendTraderBot:
    """한국주식 추세매매봇 클래스"""
    def analyze_backtest_results(self, results: Dict[str, any]) -> None:
        """백테스트 결과 상세 분석"""
        # 전략별 성과 분석
        print("\n=== 전략별 성과 분석 ===")
        for strategy_name, perf in results.get("strategy_performance", {}).items():
            print(f"전략: {strategy_name}")
            print(f"  - 거래횟수: {perf.get('trades_count', 0)}회")
            print(f"  - 승률: {perf.get('win_rate', 0):.2f}%")
            print(f"  - 총 수익: {perf.get('total_profit', 0):,.0f}원")
            print(f"  - 총 손실: {perf.get('total_loss', 0):,.0f}원")
            print(f"  - 순 손익: {perf.get('total_profit', 0) + perf.get('total_loss', 0):,.0f}원")
            
            if perf.get('win_count', 0) > 0:
                print(f"  - 평균 수익: {perf.get('avg_profit', 0):,.0f}원")
            if perf.get('trades_count', 0) - perf.get('win_count', 0) > 0:
                print(f"  - 평균 손실: {perf.get('avg_loss', 0):,.0f}원")
            
            # 손익비율 계산
            if perf.get('avg_loss', 0) != 0:
                profit_loss_ratio = abs(perf.get('avg_profit', 0) / perf.get('avg_loss', 0))
                print(f"  - 손익비: {profit_loss_ratio:.2f}")
            print()
            
        # 트레일링 스탑 분석
        trailing_stop_trades = [t for t in results.get('trades', []) 
                            if t.get('action') == 'SELL' and '트레일링 스탑' in t.get('reason', '')]
        
        if trailing_stop_trades:
            trailing_win = [t for t in trailing_stop_trades if t.get('profit_loss', 0) > 0]
            
            print("\n=== 트레일링 스탑 분석 ===")
            print(f"트레일링 스탑 발동 횟수: {len(trailing_stop_trades)}회")
            print(f"트레일링 스탑 승률: {len(trailing_win) / len(trailing_stop_trades) * 100:.2f}%")
            
            avg_trailing_loss = sum([t.get('profit_loss', 0) for t in trailing_stop_trades 
                                if t.get('profit_loss', 0) <= 0]) / len([t for t in trailing_stop_trades 
                                if t.get('profit_loss', 0) <= 0]) if [t for t in trailing_stop_trades 
                                if t.get('profit_loss', 0) <= 0] else 0
            
            print(f"트레일링 스탑 평균 손실: {avg_trailing_loss:,.0f}원")
            print()
            
        # 연속 손실 분석
        sell_trades = [t for t in results.get('trades', []) if t.get('action') == 'SELL']
        
        consecutive_losses = 0
        max_consecutive_losses = 0
        
        for trade in sell_trades:
            if trade.get('profit_loss', 0) <= 0:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0
        
        print(f"최대 연속 손실 횟수: {max_consecutive_losses}회")
        
        # 홀딩 기간 분석
        holding_periods = []
        for i in range(0, len(results.get('trades', [])), 2):
            if i+1 < len(results.get('trades', [])):
                buy_trade = results.get('trades', [])[i]
                sell_trade = results.get('trades', [])[i+1]
                
                if buy_trade.get('action') == 'BUY' and sell_trade.get('action') == 'SELL':
                    buy_date = pd.to_datetime(buy_trade.get('date'))
                    sell_date = pd.to_datetime(sell_trade.get('date'))
                    holding_days = (sell_date - buy_date).days
                    holding_periods.append(holding_days)
        
        if holding_periods:
            avg_holding_period = sum(holding_periods) / len(holding_periods)
            print(f"평균 보유 기간: {avg_holding_period:.1f}일")
            
            win_holding_periods = []
            loss_holding_periods = []
            
            for i in range(0, len(results.get('trades', [])), 2):
                if i+1 < len(results.get('trades', [])):
                    buy_trade = results.get('trades', [])[i]
                    sell_trade = results.get('trades', [])[i+1]
                    
                    if buy_trade.get('action') == 'BUY' and sell_trade.get('action') == 'SELL':
                        buy_date = pd.to_datetime(buy_trade.get('date'))
                        sell_date = pd.to_datetime(sell_trade.get('date'))
                        holding_days = (sell_date - buy_date).days
                        
                        if sell_trade.get('profit_loss', 0) > 0:
                            win_holding_periods.append(holding_days)
                        else:
                            loss_holding_periods.append(holding_days)
            
            if win_holding_periods:
                avg_win_holding = sum(win_holding_periods) / len(win_holding_periods)
                print(f"수익 거래 평균 보유 기간: {avg_win_holding:.1f}일")
            
            if loss_holding_periods:
                avg_loss_holding = sum(loss_holding_periods) / len(loss_holding_periods)
                print(f"손실 거래 평균 보유 기간: {avg_loss_holding:.1f}일")

    # TrendTraderBot 클래스에 시장 상황 분석 메서드 추가
    def analyze_market_condition(self) -> str:
        """시장 상황 분석 (상승/하락/횡보)"""
        market_index_code = self.config.get("market_index_code", "069500")
        lookback_days = 60  # 분석 기간
        
        # 지수 데이터 가져오기
        market_data = KisKR.GetOhlcvNew(market_index_code, 'D', lookback_days+10, adj_ok=1)
        
        if market_data is None or market_data.empty:
            logger.warning(f"시장 지수 데이터({market_index_code})를 가져올 수 없습니다.")
            return "neutral"  # 기본값
        
        # ADX 계산 (추세 강도)
        # ADX 계산 함수 필요 (앞서 제안한 HybridTrendStrategy 내 함수 활용)
        adx_threshold = self.config.get("market_analysis", {}).get("adx_threshold_strong_trend", 25)
        
        # 이동평균선 계산
        market_data['MA20'] = market_data['close'].rolling(window=20).mean()
        market_data['MA60'] = market_data['close'].rolling(window=60).mean()
        
        if len(market_data) < 60:
            return "neutral"
        
        # 최근 종가, 이동평균
        recent_close = market_data['close'].iloc[-1]
        ma20 = market_data['MA20'].iloc[-1]
        ma60 = market_data['MA60'].iloc[-1]
        
        # 20일 변화율
        change_20d = ((recent_close / market_data['close'].iloc[-21]) - 1) * 100
        
        # 시장 상황 판단
        if recent_close > ma20 > ma60 and change_20d > 3:
            return "bull"  # 상승장
        elif recent_close < ma20 < ma60 and change_20d < -3:
            return "bear"  # 하락장
        else:
            return "neutral"  # 횡보장

    def monitor_portfolio_risk(self) -> None:
        """포트폴리오 위험 지표 모니터링"""
        if not self.holdings:
            return
        
        # 현재 포트폴리오 가치 계산
        portfolio_value = 0
        initial_investment = 0
        
        for stock_code, holding_info in self.holdings.items():
            quantity = holding_info.get("quantity", 0)
            avg_price = holding_info.get("avg_price", 0)
            current_price = KisKR.GetCurrentPrice(stock_code)
            
            if current_price is not None and not isinstance(current_price, str):
                # 현재 가치
                stock_value = quantity * current_price
                # 초기 투자금
                initial_value = quantity * avg_price
                
                portfolio_value += stock_value
                initial_investment += initial_value
        
        # 계좌 잔고 가져오기
        account_balance = KisKR.GetBalance()
        if not account_balance or isinstance(account_balance, str):
            return
        
        cash = account_balance.get("RemainMoney", 0)
        
        # 총 자산 계산 (포트폴리오 + 현금)
        total_assets = portfolio_value + cash
        
        # 최대 낙폭 계산을 위한 최고 자산가
        if not hasattr(self, 'peak_assets'):
            self.peak_assets = total_assets
        elif total_assets > self.peak_assets:
            self.peak_assets = total_assets
        
        # 현재 낙폭 계산
        if self.peak_assets > 0:
            current_drawdown = (self.peak_assets - total_assets) / self.peak_assets * 100
            logger.info(f"현재 포트폴리오 낙폭: {current_drawdown:.2f}%")
            
            # 낙폭이 15% 이상이면 보수적 모드로 전환
            if current_drawdown > 15.0:
                logger.warning(f"높은 낙폭 감지: {current_drawdown:.2f}%, 보수적 모드로 전환")
                self.conservative_mode = True
                
                # 보수적 모드에서는 신규 매수 제한 및 손절 기준 강화
                for stock_code, holding_info in self.holdings.items():
                    strategy_name = holding_info.get("strategy", "RSI")
                    strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
                    
                    if strategy is not None:
                        # 트레일링 스탑 비율 감소
                        if isinstance(strategy, TrailingStopStrategy):
                            old_pct = strategy.params.get("trailing_stop_pct", 2.0)
                            strategy.params["trailing_stop_pct"] = old_pct * 0.8
                            logger.info(f"종목 {stock_code} 트레일링 스탑 비율 감소: {old_pct:.2f}% → {strategy.params['trailing_stop_pct']:.2f}%")
            else:
                # 낙폭이 10% 미만이면 정상 모드로 복귀
                if hasattr(self, 'conservative_mode') and self.conservative_mode and current_drawdown < 10.0:
                    logger.info(f"낙폭 완화: {current_drawdown:.2f}%, 정상 모드로 복귀")
                    self.conservative_mode = False
        
        # 포트폴리오 정보 로깅
        logger.info(f"포트폴리오 가치: {portfolio_value:,.0f}원, 초기 투자금: {initial_investment:,.0f}원, 현금: {cash:,.0f}원")
        logger.info(f"총 자산: {total_assets:,.0f}원, 최고 자산: {self.peak_assets:,.0f}원")

    def analyze_market_liquidity(self, stock_code: str, daily_data: pd.DataFrame) -> Dict[str, any]:
        """시장 유동성 분석 - 거래 증가 시기 포착"""
        result = {
            "is_high_liquidity": False,
            "reason": ""
        }
        
        if daily_data is None or daily_data.empty or len(daily_data) < 20:
            return result
        
        # 1. 거래량 추세 분석
        recent_volume = daily_data['volume'].iloc[-5:].mean()  # 최근 5일 평균 거래량
        prev_volume = daily_data['volume'].iloc[-20:-5].mean()  # 이전 15일 평균 거래량
        
        volume_ratio = recent_volume / prev_volume if prev_volume > 0 else 1.0
        
        if volume_ratio > 1.2:  # 거래량 20% 이상 증가
            result["is_high_liquidity"] = True
            result["reason"] += "거래량 증가 "
        
        # 2. 변동성 분석
        recent_range = (daily_data['high'].iloc[-5:].max() - daily_data['low'].iloc[-5:].min()) / daily_data['close'].iloc[-5:].mean()
        prev_range = (daily_data['high'].iloc[-20:-5].max() - daily_data['low'].iloc[-20:-5].min()) / daily_data['close'].iloc[-20:-5].mean()
        
        range_ratio = recent_range / prev_range if prev_range > 0 else 1.0
        
        if range_ratio > 1.1:  # 변동성 10% 이상 증가
            result["is_high_liquidity"] = True
            result["reason"] += "변동성 증가 "
        
        # 3. 가격 모멘텀 확인
        price_momentum = daily_data['close'].pct_change(5).iloc[-1] * 100  # 5일 가격 변화율
        
        if abs(price_momentum) > 3.0:  # 3% 이상 가격 변화
            result["is_high_liquidity"] = True
            result["reason"] += "가격 모멘텀 강화 "
        
        return result

    def update_dynamic_trailing_stop(self, stock_code: str, current_price: float, holding_info: Dict[str, any]) -> Dict[str, any]:
        """수익률에 따른 동적 트레일링 스탑 비율 설정 (이익 구간 보호)"""
        avg_price = holding_info.get("avg_price", current_price)
        highest_price = holding_info.get("highest_price", current_price)
        
        # 현재 수익률 계산
        profit_percent = ((current_price / avg_price) - 1) * 100
        
        # 기본 트레일링 스탑 비율
        strategy_name = holding_info.get("strategy", "RSI")
        strategy = self.strategy_manager.get_strategy(strategy_name, stock_code)
        
        trailing_pct = 2.0  # 기본값 3.0에서 2.0으로 축소
        if isinstance(strategy, TrailingStopStrategy):
            trailing_pct = strategy.params.get("trailing_stop_pct", 2.0)

        # 최소 보유 기간 확인
        buy_date = holding_info.get("buy_date", datetime.datetime.now().strftime("%Y%m%d"))
        if isinstance(buy_date, str):
            buy_date = datetime.datetime.strptime(buy_date, "%Y%m%d")
        current_date = datetime.datetime.now()
        holding_days = (current_date - buy_date).days

        # 수익에 따른 트레일링 스탑 적용 (수정)
        if profit_percent >= 1.0:  # 수익이 1% 이상인 경우부터 트레일링 스탑 적용 (2%에서 1%로 하향)
            # 수익에 비례하여 트레일링 스탑 적용
            if profit_percent > 6.0:  # 높은 수익
                trailing_pct = trailing_pct * 0.3  # 더 타이트하게
            elif profit_percent > 4.0:
                trailing_pct = trailing_pct * 0.4
            elif profit_percent > 2.5:
                trailing_pct = trailing_pct * 0.6
            elif profit_percent > 1.5:
                trailing_pct = trailing_pct * 0.8
        else:
            # 수익이 1% 미만인 경우 고정 손절선 사용
            stop_loss_pct = strategy.params.get("stop_loss_pct", 2.0)
            stop_loss_price = avg_price * (1 - stop_loss_pct/100)
            holding_info["trailing_stop_price"] = stop_loss_price
            return holding_info

        # 최소 보유 기간 적용 (매수 후 1일 이상) - 2일에서 1일로 감소
        if holding_days < 1:
            # 초기에는 고정 손절선만 사용
            stop_loss_pct = strategy.params.get("stop_loss_pct", 2.0)
            stop_loss_price = avg_price * (1 - stop_loss_pct/100)
            holding_info["trailing_stop_price"] = stop_loss_price
            return holding_info

        # 새로운 트레일링 스탑 가격 계산
        if current_price > highest_price:
            holding_info["highest_price"] = current_price
            holding_info["trailing_stop_price"] = current_price * (1 - trailing_pct/100)
        
        return holding_info

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
            
            # 추가된 부분: 최근 거래 기록 확인 - 빈번한 매매 방지
            # 거래 이력 속성 확인 및 초기화
            if not hasattr(self, 'trade_history'):
                self.trade_history = []  # 아직 속성이 없다면 초기화
                
                # 선택적으로 거래 이력 파일에서 로드
                try:
                    if os.path.exists('trade_history.json'):
                        with open('trade_history.json', 'r', encoding='utf-8') as f:
                            self.trade_history = json.load(f)
                except Exception as e:
                    logger.warning(f"거래 이력 로드 실패: {e}")
            
            # 최근 거래 이력 확인 (매수 신호가 있을 때만)
            if analysis_result.get("is_buy_signal", False):
                # 최소 거래 간격 설정 (일)
                min_trade_interval = self.config.get("min_trade_interval", 7)
                
                # 최근 30일 내 거래 기록 확인
                today = datetime.datetime.now()
                recent_trades = [trade for trade in self.trade_history 
                            if trade.get("stock_code") == stock_code 
                            and trade.get("action") == "SELL"
                            and "date" in trade]
                
                if recent_trades:
                    # 가장 최근 매도 거래 찾기
                    last_trade = max(recent_trades, key=lambda x: datetime.datetime.strptime(x.get("date", "19700101"), "%Y%m%d"))
                    
                    # 날짜 변환 (문자열 형식에 맞게 조정)
                    try:
                        last_trade_date = datetime.datetime.strptime(last_trade.get("date", ""), "%Y%m%d")
                        days_since_last_trade = (today - last_trade_date).days
                        
                        # 마지막 거래로부터 최소 간격 경과해야 재매수 허용
                        if days_since_last_trade < min_trade_interval:
                            analysis_result["is_buy_signal"] = False
                            analysis_result["reason"] = f"최근 거래({days_since_last_trade}일 전) 후 대기 기간"
                            logger.info(f"종목 {stock_code} 최근 거래 후 대기 기간으로 매수 신호 무시")
                    except Exception as e:
                        logger.warning(f"날짜 처리 오류: {e}")
            
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
                
                # 최고가 업데이트
                highest_price = holding_info.get("highest_price", current_price)
                if current_price > highest_price:
                    # 수익률 기반 동적 트레일링 스탑 적용
                    holding_info = self.update_dynamic_trailing_stop(stock_code, current_price, holding_info)                    
                    
                    # 트레일링 스탑 가격 업데이트 (TrailingStopStrategy 경우)
                    if isinstance(strategy, TrailingStopStrategy) or strategy_name in ["MACD_Default", "Composite_Default", "BB_Default", "BB_StochFilter"]:
                        trailing_pct = strategy.params.get("trailing_stop_pct", 2.0) if isinstance(strategy, TrailingStopStrategy) else 2.0
                        holding_info["trailing_stop_price"] = current_price * (1 - trailing_pct/100)
                        logger.info(f"종목 {stock_code} 최고가 갱신: {current_price:,}원, 트레일링 스탑: {holding_info['trailing_stop_price']:,}원")
                
                # 트레일링 스탑 확인
                trailing_stop_price = holding_info.get("trailing_stop_price", 0)
                if trailing_stop_price > 0 and current_price < trailing_stop_price:
                    logger.info(f"종목 {stock_code} 트레일링 스탑 발동: 현재가 {current_price:,}원 < 트레일링 스탑 {trailing_stop_price:,}원")
                    quantity = holding_info.get("quantity", 0)
                    avg_price = holding_info.get("avg_price", 0)
                    
                    profit_percent = ((current_price / avg_price) - 1) * 100
                    
                    if quantity > 0:
                        # 시장가 매도
                        order_result = KisKR.MakeSellMarketOrder(
                            stockcode=stock_code,
                            amt=quantity
                        )
                        
                        if not isinstance(order_result, str):
                            logger.info(f"트레일링 스탑 매도 성공: {stock_code} {quantity}주, 수익률: {profit_percent:.2f}%")
                            # 보유 종목에서 제거
                            del self.holdings[stock_code]
                            self._save_holdings()
                        else:
                            logger.error(f"트레일링 스탑 매도 실패: {stock_code}, {order_result}")
                    
                    continue  # 트레일링 스탑으로 매도했으면 다른 매도 신호 확인 안 함

                # 여기에 보수적 모드 확인 코드 추가
                if hasattr(self, 'conservative_mode') and self.conservative_mode:
                    # 보수적 모드에서는 목표 수익률 하향 조정
                    if isinstance(strategy, TrailingStopStrategy):
                        original_profit_target = strategy.params.get("profit_target", 5.0)
                        conservative_profit_target = original_profit_target * 0.7  # 70% 수준으로 하향
                        
                        profit_percent = ((current_price / avg_price) - 1) * 100
                        
                        # 하향 조정된 목표 수익률 달성 시 매도
                        if profit_percent >= conservative_profit_target:
                            logger.info(f"보수적 모드 매도: {stock_code}, 수익률: {profit_percent:.2f}% (목표: {conservative_profit_target:.2f}%)")
                            quantity = holding_info.get("quantity", 0)
                            
                            if quantity > 0:
                                # 시장가 매도
                                order_result = KisKR.MakeSellMarketOrder(
                                    stockcode=stock_code,
                                    amt=quantity
                                )
                                
                                if not isinstance(order_result, str):
                                    logger.info(f"보수적 모드 매도 성공: {stock_code} {quantity}주")
                                    # 보유 종목에서 제거
                                    del self.holdings[stock_code]
                                    self._save_holdings()
                                else:
                                    logger.error(f"보수적 모드 매도 실패: {stock_code}, {order_result}")
                            
                            continue  # 다음 종목으로

                # 타임 스탑 (보유 기간이 너무 길면 매도)
                now = datetime.datetime.now()
                buy_date_str = holding_info.get("buy_date", now.strftime("%Y%m%d"))
                buy_date = datetime.datetime.strptime(buy_date_str, "%Y%m%d")
                holding_days = (now - buy_date).days

                # 최대 보유 기간 확인 (설정에서 가져오기)
                max_holding_days = self.config.get("max_holding_days", 15)
                if holding_days > max_holding_days:
                    # 최대 보유 기간 초과 시 무조건 매도
                    logger.info(f"최대 보유 기간 초과: {stock_code}, 보유일수: {holding_days}일, 최대: {max_holding_days}일")
                    quantity = holding_info.get("quantity", 0)
                    avg_price = holding_info.get("avg_price", 0)
                    profit_percent = ((current_price / avg_price) - 1) * 100
                    
                    if quantity > 0:
                        # 시장가 매도
                        order_result = KisKR.MakeSellMarketOrder(
                            stockcode=stock_code,
                            amt=quantity
                        )
                        
                        if not isinstance(order_result, str):
                            logger.info(f"최대 보유 기간 매도 성공: {stock_code} {quantity}주, 수익률: {profit_percent:.2f}%")
                            # 보유 종목에서 제거
                            del self.holdings[stock_code]
                            self._save_holdings()
                        else:
                            logger.error(f"최대 보유 기간 매도 실패: {stock_code}, {order_result}")
                    
                    continue  # 다음 종목으로

                if holding_days > self.config.get("time_stop_days", 15):  # 15일 이상 보유한 경우 (20일에서 15일로 변경)
                    # 수익률 확인
                    avg_price = holding_info.get("avg_price", 0)
                    profit_percent = ((current_price / avg_price) - 1) * 100
                    
                    # 타임 스탑 조건 확인 (더 엄격하게 수정)
                    if profit_percent < self.config.get("time_stop_profit_pct", 1.5) or profit_percent < 0:  # 수익률 1.5% 미만이거나 손실인 경우
                        logger.info(f"타임 스탑 발동: {stock_code}, 보유일수: {holding_days}일, 수익률: {profit_percent:.2f}%")
                        quantity = holding_info.get("quantity", 0)
                        
                        if quantity > 0:
                            # 시장가 매도
                            order_result = KisKR.MakeSellMarketOrder(
                                stockcode=stock_code,
                                amt=quantity
                            )
                            
                            if not isinstance(order_result, str):
                                logger.info(f"타임 스탑 매도 성공: {stock_code} {quantity}주")
                                # 보유 종목에서 제거
                                del self.holdings[stock_code]
                                self._save_holdings()
                            else:
                                logger.error(f"타임 스탑 매도 실패: {stock_code}, {order_result}")
                        
                        continue  # 다음 종목으로
                
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

            # 포트폴리오 위험 모니터링 추가 (매매 시작 전)
            if self.config.get("risk_management", {}).get("monitor_portfolio_risk", False):
                self.monitor_portfolio_risk()

            # 현재 보유 종목 수 확인
            current_holdings_count = len(self.holdings)
            
            # 매수 가능한 종목 수 확인
            available_slots = max(0, self.max_stocks - current_holdings_count)
            logger.info(f"추가 매수 가능 종목 수: {available_slots}개")

            # 보수적 모드에서는 매수 제한
            if hasattr(self, 'conservative_mode') and self.conservative_mode:
                logger.warning("보수적 모드 활성화 중: 신규 매수가 제한됩니다.")
                available_slots = 0

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
                    
                    # 변동성 기반 포지션 사이징 (추가)
                    try:
                        # 일봉 데이터 조회
                        daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 30, adj_ok=1)
                        
                        if daily_data is not None and not daily_data.empty and len(daily_data) > 20:
                            # ATR 계산
                            atr = self.tech_indicators.calculate_atr(daily_data, period=14).iloc[-1]
                            
                            # 모멘텀 계산
                            momentum = self.tech_indicators.calculate_momentum(daily_data, period=10).iloc[-1]
                            
                            if not pd.isna(atr) and not pd.isna(momentum):
                                # 변동성 비율 계산
                                volatility_ratio = atr / current_price
                                
                                # 기본 수량 조정
                                if volatility_ratio > 0.025:  # 2.5% 이상 변동성 (높음)
                                    quantity = max(1, int(quantity * 0.7))  # 30% 수량 감소
                                    logger.info(f"높은 변동성 감지: {volatility_ratio:.2%}, 수량 30% 감소")
                                elif volatility_ratio < 0.01:  # 1% 미만 변동성 (낮음)
                                    quantity = max(1, int(quantity * 1.2))  # 20% 수량 증가
                                    logger.info(f"낮은 변동성 감지: {volatility_ratio:.2%}, 수량 20% 증가")
                                    
                                # 모멘텀 기반 추가 조정
                                if momentum > 5.0:  # 강한 상승 모멘텀
                                    quantity = max(1, int(quantity * 1.1))  # 10% 추가 증가
                                    logger.info(f"강한 상승 모멘텀 감지: {momentum:.2f}, 수량 10% 추가 증가")
                                elif momentum < -3.0:  # 하락 모멘텀
                                    quantity = max(1, int(quantity * 0.9))  # 10% 추가 감소
                                    logger.info(f"하락 모멘텀 감지: {momentum:.2f}, 수량 10% 추가 감소")
                    except Exception as e:
                        logger.warning(f"변동성 기반 포지션 사이징 적용 중 오류: {e}")
                    
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
                            
                            # 거래 이력에 추가 (새로 추가된 부분)
                            trade_record = {
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                "action": "BUY",
                                "strategy": strategy_name,
                                "reason": candidate.get("reason", ""),
                                "date": now.strftime("%Y%m%d"),
                                "price": avg_price,
                                "quantity": quantity,
                                "amount": buy_amount
                            }
                            
                            # 거래 이력에 추가
                            if not hasattr(self, 'trade_history'):
                                self.trade_history = []
                            self.trade_history.append(trade_record)
                            
                            # 거래 이력 저장
                            try:
                                with open('trade_history.json', 'w', encoding='utf-8') as f:
                                    json.dump(self.trade_history, f, ensure_ascii=False, indent=4, default=str)
                            except Exception as e:
                                logger.warning(f"거래 이력 저장 실패: {e}")
                                
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
                        
                        # 변동성 기반 포지션 사이징 (추가)
                        try:
                            # 일봉 데이터 조회
                            daily_data = KisKR.GetOhlcvNew(stock_code, 'D', 30, adj_ok=1)
                            
                            if daily_data is not None and not daily_data.empty and len(daily_data) > 20:
                                # ATR 계산
                                atr = self.tech_indicators.calculate_atr(daily_data, period=14).iloc[-1]
                                
                                # 모멘텀 계산
                                momentum = self.tech_indicators.calculate_momentum(daily_data, period=10).iloc[-1]
                                
                                if not pd.isna(atr) and not pd.isna(momentum):
                                    # 변동성 비율 계산
                                    volatility_ratio = atr / current_price
                                    
                                    # 기본 수량 조정
                                    if volatility_ratio > 0.025:  # 2.5% 이상 변동성 (높음)
                                        add_quantity = max(1, int(add_quantity * 0.7))  # 30% 수량 감소
                                        logger.info(f"추가 매수: 높은 변동성 감지: {volatility_ratio:.2%}, 수량 30% 감소")
                                    elif volatility_ratio < 0.01:  # 1% 미만 변동성 (낮음)
                                        add_quantity = max(1, int(add_quantity * 1.2))  # 20% 수량 증가
                                        logger.info(f"추가 매수: 낮은 변동성 감지: {volatility_ratio:.2%}, 수량 20% 증가")
                                        
                                    # 모멘텀 기반 추가 조정
                                    if momentum > 5.0:  # 강한 상승 모멘텀
                                        add_quantity = max(1, int(add_quantity * 1.1))  # 10% 추가 증가
                                        logger.info(f"추가 매수: 강한 상승 모멘텀 감지: {momentum:.2f}, 수량 10% 추가 증가")
                                    elif momentum < -3.0:  # 하락 모멘텀
                                        add_quantity = max(1, int(add_quantity * 0.9))  # 10% 추가 감소
                                        logger.info(f"추가 매수: 하락 모멘텀 감지: {momentum:.2f}, 수량 10% 추가 감소")
                        except Exception as e:
                            logger.warning(f"추가 매수: 변동성 기반 포지션 사이징 적용 중 오류: {e}")
                        
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
                                
                                # 거래 이력에 추가 (새로 추가된 부분)
                                strategy_name = holding_info.get("strategy", "RSI")
                                stock_name = self.watch_list_info.get(stock_code, {}).get("name", stock_code)
                                
                                trade_record = {
                                    "stock_code": stock_code,
                                    "stock_name": stock_name,
                                    "action": "BUY_ADDITIONAL",
                                    "strategy": strategy_name,
                                    "reason": "분할 매수 추가 매수",
                                    "date": now.strftime("%Y%m%d"),
                                    "price": current_price,
                                    "quantity": add_quantity,
                                    "amount": add_buy_amount
                                }
                                
                                # 거래 이력에 추가
                                if not hasattr(self, 'trade_history'):
                                    self.trade_history = []
                                self.trade_history.append(trade_record)
                                
                                # 거래 이력 저장
                                try:
                                    with open('trade_history.json', 'w', encoding='utf-8') as f:
                                        json.dump(self.trade_history, f, ensure_ascii=False, indent=4, default=str)
                                except Exception as e:
                                    logger.warning(f"거래 이력 저장 실패: {e}")
                                
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
            "strategy_performance": {},
            "stock_performance": {}
        }
        
        total_capital = self.total_budget
        virtual_holdings = {}
        trades = []
        max_holdings_count = self.max_stocks  # 최대 동시 보유 종목 수 제한
        
        # 백테스트용 위험 관리 변수 추가
        peak_assets = self.total_budget  # 최고 자산
        conservative_mode = False  # 보수적 모드 플래그
        conservative_mode_threshold = self.config.get("risk_management", {}).get("conservative_mode_threshold", 10.0)
        normal_mode_threshold = self.config.get("risk_management", {}).get("normal_mode_threshold", 7.0)
        use_time_stop = self.config.get("risk_management", {}).get("use_time_stop", True)
        time_stop_days = self.config.get("time_stop_days", 15)  # 20에서 15로 수정
        time_stop_profit_pct = self.config.get("time_stop_profit_pct", 1.5)  # 1.0에서 1.5로 수정
        
        # 백테스트용 거래 이력 추적
        virtual_trade_history = {}  # {stock_code: last_sell_date}
        
        # 최소 거래 간격 설정
        min_trade_interval = self.config.get("backtest_settings", {}).get("min_trade_interval", 10)  # 7에서 10으로 수정
        use_trade_interval = self.config.get("backtest_settings", {}).get("use_trade_interval", True)  # 기본값 활성화
        
        try:
            # 관심종목 반복
            for stock_code in self.watch_list:
                # 거래 이력 초기화
                virtual_trade_history[stock_code] = None
                
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
                        "win_rate": 0,
                        "avg_profit": 0,
                        "avg_loss": 0
                    }

                # 날짜별 시뮬레이션
                for i in range(20, len(filtered_data)):  # 지표 계산을 위해 20일 이후부터 시작
                    date = filtered_data.index[i]
                    current_price = filtered_data.iloc[i]['close']
                    
                    # 현재 자산 및 낙폭 계산 (포트폴리오 위험 모니터링)
                    current_assets = total_capital
                    for s_code, holding in virtual_holdings.items():
                        stock_quantity = holding.get("quantity", 0)
                        if s_code == stock_code:
                            # 현재 분석 중인 종목은 현재가 사용
                            stock_price = current_price
                        else:
                            # 다른 종목은 마지막 가격 사용
                            stock_price = holding.get("current_price", 0)
                        
                        current_assets += stock_quantity * stock_price
                    
                    # 최고 자산 갱신
                    if current_assets > peak_assets:
                        peak_assets = current_assets
                    
                    # 현재 낙폭 계산
                    current_drawdown = 0
                    if peak_assets > 0:
                        current_drawdown = (peak_assets - current_assets) / peak_assets * 100
                    
                    # 보수적 모드 전환 확인
                    if current_drawdown > conservative_mode_threshold and not conservative_mode:
                        conservative_mode = True
                        logger.info(f"[{date}] 백테스트: 높은 낙폭 감지: {current_drawdown:.2f}%, 보수적 모드로 전환")
                        
                        # 보수적 모드 전환 시 트레일링 스탑 비율 조정
                        for held_code, held_info in virtual_holdings.items():
                            held_strategy_name = held_info.get("strategy", "RSI")
                            held_strategy = self.strategy_manager.get_strategy(held_strategy_name, held_code)
                            
                            if isinstance(held_strategy, TrailingStopStrategy):
                                old_pct = held_strategy.params.get("trailing_stop_pct", 2.0)
                                held_strategy.params["trailing_stop_pct"] = old_pct * 0.8
                                logger.info(f"종목 {held_code} 트레일링 스탑 비율 감소: {old_pct:.2f}% → {held_strategy.params['trailing_stop_pct']:.2f}%")
                                
                                # 트레일링 스탑 가격 재계산
                                held_highest_price = held_info.get("highest_price", 0)
                                if held_highest_price > 0:
                                    new_trailing_stop_pct = held_strategy.params["trailing_stop_pct"]
                                    held_info["trailing_stop_price"] = held_highest_price * (1 - new_trailing_stop_pct/100)
                                
                    elif current_drawdown < normal_mode_threshold and conservative_mode:
                        conservative_mode = False
                        logger.info(f"[{date}] 백테스트: 낙폭 완화: {current_drawdown:.2f}%, 정상 모드로 복귀")
                        
                        # 정상 모드 복귀 시 트레일링 스탑 비율 원복
                        for held_code, held_info in virtual_holdings.items():
                            held_strategy_name = held_info.get("strategy", "RSI")
                            held_strategy = self.strategy_manager.get_strategy(held_strategy_name, held_code)
                            
                            if isinstance(held_strategy, TrailingStopStrategy):
                                held_strategy.params["trailing_stop_pct"] = strategy.params.get("original_trailing_stop_pct", 
                                                                                            held_strategy.params.get("trailing_stop_pct", 2.0))
                                
                    # 데이터 슬라이스 (현재까지의 데이터)
                    current_data = filtered_data.iloc[:i+1].copy()
                    
                    # 먼저 보유중인 종목의 트레일링 스탑 및 현재가 업데이트
                    for stock_code_held in list(virtual_holdings.keys()):
                        holding_info = virtual_holdings[stock_code_held]
                        
                        # 현재가 업데이트 (다른 종목인 경우 해당 종목의 현재가를 찾아야 함)
                        if stock_code_held == stock_code:
                            holding_price = current_price
                        else:
                            # 간소화를 위해 현재 보유가 사용, 실제로는 해당 종목의 현재가를 찾아야 함
                            holding_price = holding_info.get("current_price", 0)
                        
                        holding_info["current_price"] = holding_price
                        
                        # 최고가 업데이트 및 트레일링 스탑 확인
                        strategy_name_held = holding_info.get("strategy", "RSI")
                        strategy_held = self.strategy_manager.get_strategy(strategy_name_held, stock_code_held)
                        
                        # 최고가 업데이트
                        highest_price = holding_info.get("highest_price", holding_price)
                        if holding_price > highest_price:
                            holding_info["highest_price"] = holding_price
                            
                            # 트레일링 스탑 가격 업데이트
                            if hasattr(strategy_held, 'params') and (
                                isinstance(strategy_held, TrailingStopStrategy) or 
                                strategy_held.params.get("use_trailing_stop", False)
                            ):
                                trailing_pct = strategy_held.params.get("trailing_stop_pct", 2.0)  # 5.0에서 2.0으로 수정
                                holding_info["trailing_stop_price"] = holding_price * (1 - trailing_pct/100)
                                
                                # 보수적 모드에서는 더 타이트한 트레일링 스탑 적용
                                if conservative_mode:
                                    conservative_trailing_pct = trailing_pct * 0.8
                                    holding_info["trailing_stop_price"] = holding_price * (1 - conservative_trailing_pct/100)
                        
                        # 트레일링 스탑 매도 확인
                        trailing_stop_price = holding_info.get("trailing_stop_price", 0)
                        if trailing_stop_price > 0 and holding_price < trailing_stop_price:
                            # 트레일링 스탑 매도 실행
                            quantity = holding_info["quantity"]
                            avg_price = holding_info["avg_price"]
                            sell_amount = holding_price * quantity
                            profit = sell_amount - (avg_price * quantity)
                            profit_percent = ((holding_price / avg_price) - 1) * 100
                            
                            # 자본 업데이트
                            total_capital += sell_amount
                            # 거래 기록
                            trade_record = {
                                "stock_code": stock_code_held,
                                "stock_name": self.watch_list_info.get(stock_code_held, {}).get("name", stock_code_held),
                                "action": "SELL",
                                "strategy": strategy_name_held,
                                "reason": f"트레일링 스탑 발동: {profit_percent:.2f}%",
                                "date": date,
                                "price": holding_price,
                                "quantity": quantity,
                                "profit_loss": profit,
                                "profit_loss_percent": profit_percent
                            }
                            
                            trades.append(trade_record)
                            
                            # 최근 매도 거래 일자 기록 (거래 간격 추적)
                            virtual_trade_history[stock_code_held] = date
                            
                            # 전략 성능 업데이트
                            if strategy_name_held in backtest_results["strategy_performance"]:
                                backtest_results["strategy_performance"][strategy_name_held]["trades_count"] += 1
                                if profit > 0:
                                    backtest_results["strategy_performance"][strategy_name_held]["win_count"] += 1
                                    backtest_results["strategy_performance"][strategy_name_held]["total_profit"] += profit
                                else:
                                    backtest_results["strategy_performance"][strategy_name_held]["total_loss"] += profit
                            
                            # 보유 종목에서 제거
                            del virtual_holdings[stock_code_held]
                            continue  # 매도 후 다음 종목으로
                        
                        # 보수적 모드 확인
                        if conservative_mode:
                            # 보수적 모드에서는 목표 수익률 하향 조정
                            if hasattr(strategy_held, 'params'):
                                original_profit_target = strategy_held.params.get("profit_target", 5.0)
                                conservative_profit_target = original_profit_target * 0.7  # 70% 수준으로 하향
                                
                                avg_price = holding_info["avg_price"]
                                profit_percent = ((holding_price / avg_price) - 1) * 100
                                
                                # 하향 조정된 목표 수익률 달성 시 매도
                                if profit_percent >= conservative_profit_target:
                                    # 매도 실행
                                    quantity = holding_info["quantity"]
                                    sell_amount = holding_price * quantity
                                    profit = sell_amount - (avg_price * quantity)
                                    
                                    # 자본 업데이트
                                    total_capital += sell_amount
                                    
                                    # 거래 기록
                                    trade_record = {
                                        "stock_code": stock_code_held,
                                        "stock_name": self.watch_list_info.get(stock_code_held, {}).get("name", stock_code_held),
                                        "action": "SELL",
                                        "strategy": strategy_name_held,
                                        "reason": f"보수적 모드 매도: {profit_percent:.2f}% (목표: {conservative_profit_target:.2f}%)",
                                        "date": date,
                                        "price": holding_price,
                                        "quantity": quantity,
                                        "profit_loss": profit,
                                        "profit_loss_percent": profit_percent
                                    }
                                    
                                    trades.append(trade_record)
                                    
                                    # 최근 매도 거래 일자 기록 (거래 간격 추적)
                                    virtual_trade_history[stock_code_held] = date
                                    
                                    # 전략 성능 업데이트
                                    if strategy_name_held in backtest_results["strategy_performance"]:
                                        backtest_results["strategy_performance"][strategy_name_held]["trades_count"] += 1
                                        if profit > 0:
                                            backtest_results["strategy_performance"][strategy_name_held]["win_count"] += 1
                                            backtest_results["strategy_performance"][strategy_name_held]["total_profit"] += profit
                                        else:
                                            backtest_results["strategy_performance"][strategy_name_held]["total_loss"] += profit
                                    
                                    # 보유 종목에서 제거
                                    del virtual_holdings[stock_code_held]
                                    continue  # 매도 후 다음 종목으로
                        
                        # 타임 스탑 확인
                        if use_time_stop:
                            buy_date = holding_info.get("buy_date", date)
                            if isinstance(buy_date, str):
                                try:
                                    buy_date = pd.to_datetime(buy_date)
                                except:
                                    buy_date = pd.to_datetime(date) - pd.Timedelta(days=1)
                            
                            current_date = pd.to_datetime(date)
                            holding_days = (current_date - buy_date).days
                            
                            # 최대 보유 기간 확인 (신규 추가)
                            max_holding_days = self.config.get("max_holding_days", 15)
                            if holding_days > max_holding_days:
                                # 최대 보유 기간 초과 시 무조건 매도
                                quantity = holding_info["quantity"]
                                avg_price = holding_info["avg_price"]
                                sell_amount = holding_price * quantity
                                profit = sell_amount - (avg_price * quantity)
                                profit_percent = ((holding_price / avg_price) - 1) * 100
                                
                                # 자본 업데이트
                                total_capital += sell_amount
                                
                                # 거래 기록
                                trade_record = {
                                    "stock_code": stock_code_held,
                                    "stock_name": self.watch_list_info.get(stock_code_held, {}).get("name", stock_code_held),
                                    "action": "SELL",
                                    "strategy": strategy_name_held,
                                    "reason": f"최대 보유 일수 초과: {holding_days}일, 수익률 {profit_percent:.2f}%",
                                    "date": date,
                                    "price": holding_price,
                                    "quantity": quantity,
                                    "profit_loss": profit,
                                    "profit_loss_percent": profit_percent
                                }
                                
                                trades.append(trade_record)
                                
                                # 최근 매도 거래 일자 기록 (거래 간격 추적)
                                virtual_trade_history[stock_code_held] = date
                                
                                # 전략 성능 업데이트
                                if strategy_name_held in backtest_results["strategy_performance"]:
                                    backtest_results["strategy_performance"][strategy_name_held]["trades_count"] += 1
                                    if profit > 0:
                                        backtest_results["strategy_performance"][strategy_name_held]["win_count"] += 1
                                        backtest_results["strategy_performance"][strategy_name_held]["total_profit"] += profit
                                    else:
                                        backtest_results["strategy_performance"][strategy_name_held]["total_loss"] += profit
                                
                                # 보유 종목에서 제거
                                del virtual_holdings[stock_code_held]
                                continue  # 매도 후 다음 종목으로
                            
                            # 타임 스탑 조건 확인 (기존 로직 수정)
                            if holding_days > time_stop_days:
                                # 수익률 확인
                                avg_price = holding_info["avg_price"]
                                profit_percent = ((holding_price / avg_price) - 1) * 100
                                
                                # 타임 스탑 조건 확인 (더 엄격하게 수정)
                                if profit_percent < time_stop_profit_pct or profit_percent < 0:  # 조건 추가 - 손실이면 무조건 매도
                                    # 매도 실행
                                    quantity = holding_info["quantity"]
                                    sell_amount = holding_price * quantity
                                    profit = sell_amount - (avg_price * quantity)
                                    
                                    # 자본 업데이트
                                    total_capital += sell_amount
                                    
                                    # 거래 기록
                                    trade_record = {
                                        "stock_code": stock_code_held,
                                        "stock_name": self.watch_list_info.get(stock_code_held, {}).get("name", stock_code_held),
                                        "action": "SELL",
                                        "strategy": strategy_name_held,
                                        "reason": f"타임 스탑 발동: 보유일수 {holding_days}일, 수익률 {profit_percent:.2f}%",
                                        "date": date,
                                        "price": holding_price,
                                        "quantity": quantity,
                                        "profit_loss": profit,
                                        "profit_loss_percent": profit_percent
                                    }
                                    
                                    trades.append(trade_record)
                                    
                                    # 최근 매도 거래 일자 기록 (거래 간격 추적)
                                    virtual_trade_history[stock_code_held] = date
                                    
                                    # 전략 성능 업데이트
                                    if strategy_name_held in backtest_results["strategy_performance"]:
                                        backtest_results["strategy_performance"][strategy_name_held]["trades_count"] += 1
                                        if profit > 0:
                                            backtest_results["strategy_performance"][strategy_name_held]["win_count"] += 1
                                            backtest_results["strategy_performance"][strategy_name_held]["total_profit"] += profit
                                        else:
                                            backtest_results["strategy_performance"][strategy_name_held]["total_loss"] += profit
                                    
                                    # 보유 종목에서 제거
                                    del virtual_holdings[stock_code_held]
                                    continue  # 매도 후 다음 종목으로
                        
                        # 매도 조건 확인 - 해당 종목 데이터 가져오기
                        stock_data = None
                        if stock_code_held != stock_code:
                            # 다른 종목이면 데이터 가져오기
                            stock_data_full = KisKR.GetOhlcvNew(stock_code_held, 'D', 200, adj_ok=1)
                            if stock_data_full is not None and not stock_data_full.empty:
                                # 해당 날짜까지의 데이터만 필터링
                                if isinstance(stock_data_full.index, pd.DatetimeIndex):
                                    stock_data = stock_data_full[stock_data_full.index <= date].copy()
                                else:
                                    stock_data_full.index = pd.to_datetime(stock_data_full.index)
                                    stock_data = stock_data_full[stock_data_full.index <= date].copy()
                        else:
                            # 현재 분석 중인 종목이면 현재 데이터 사용
                            stock_data = current_data
                        
                        # 매도 신호 분석
                        if stock_data is not None and not stock_data.empty and len(stock_data) > 20:
                            sell_result = strategy_held.analyze_sell_signal(stock_data, holding_info, holding_price)
                            
                            if sell_result.get("is_sell_signal", False):
                                # 매도 실행
                                quantity = holding_info["quantity"]
                                avg_price = holding_info["avg_price"]
                                sell_amount = holding_price * quantity
                                profit = sell_amount - (avg_price * quantity)
                                profit_percent = ((holding_price / avg_price) - 1) * 100
                                
                                # 자본 업데이트
                                total_capital += sell_amount
                                
                                # 거래 기록
                                trade_record = {
                                    "stock_code": stock_code_held,
                                    "stock_name": self.watch_list_info.get(stock_code_held, {}).get("name", stock_code_held),
                                    "action": "SELL",
                                    "strategy": strategy_name_held,
                                    "reason": sell_result.get("reason", ""),
                                    "date": date,
                                    "price": holding_price,
                                    "quantity": quantity,
                                    "profit_loss": profit,
                                    "profit_loss_percent": profit_percent
                                }
                                
                                trades.append(trade_record)
                                
                                # 최근 매도 거래 일자 기록 (거래 간격 추적)
                                virtual_trade_history[stock_code_held] = date
                                
                                # 전략 성능 업데이트
                                if strategy_name_held in backtest_results["strategy_performance"]:
                                    backtest_results["strategy_performance"][strategy_name_held]["trades_count"] += 1
                                    if profit > 0:
                                        backtest_results["strategy_performance"][strategy_name_held]["win_count"] += 1
                                        backtest_results["strategy_performance"][strategy_name_held]["total_profit"] += profit
                                    else:
                                        backtest_results["strategy_performance"][strategy_name_held]["total_loss"] += profit
                                
                                # 보유 종목에서 제거
                                del virtual_holdings[stock_code_held]
                    
                    # 매수 가능 종목 확인 (보유 수 제한)
                    if len(virtual_holdings) >= max_holdings_count:
                        continue
                    
                    # 보수적 모드에서는 신규 매수 제한
                    if conservative_mode:
                        continue
                    
                    # 최소 거래 간격 확인 (거래 간격 제한 활성화된 경우)
                    if use_trade_interval and stock_code in virtual_trade_history and virtual_trade_history[stock_code] is not None:
                        last_sell_date = virtual_trade_history[stock_code]
                        days_since_last_trade = (date - last_sell_date).days
                        
                        if days_since_last_trade < min_trade_interval:
                            # 최소 거래 간격이 지나지 않았으면 매수 건너뛰기
                            continue
                            
                    # 매수 신호 분석
                    if stock_code not in virtual_holdings:  # 이미 보유한 종목은 스킵
                        buy_result = strategy.analyze_buy_signal(current_data, None, current_price)
                        
                        if buy_result.get("is_buy_signal", False) and total_capital > current_price:
                            # 시장 추세 필터 확인 (활성화된 경우)
                            if self.config.get("use_market_trend_filter", False):
                                market_index_code = self.config.get("market_index_code", "069500")
                                # 해당 날짜까지의 시장 데이터로 추세 확인
                                market_data = KisKR.GetOhlcvNew(market_index_code, 'D', 30, adj_ok=1)
                                if market_data is not None and not market_data.empty:
                                    if isinstance(market_data.index, pd.DatetimeIndex):
                                        market_data_filtered = market_data[market_data.index <= date]
                                    else:
                                        market_data.index = pd.to_datetime(market_data.index)
                                        market_data_filtered = market_data[market_data.index <= date]
                                    
                                    if not market_data_filtered.empty:
                                        market_trend_ok = TrendFilter.check_market_trend(market_index_code, lookback_days=10)
                                        if not market_trend_ok:
                                            continue  # 시장 추세가 좋지 않으면 매수 스킵
                            
                            # 종목별 할당 예산 계산
                            allocation_ratio = self.watch_list_info.get(stock_code, {}).get("allocation_ratio", 0.2)
                            
                            # 예산 내에서 매수 수량 결정
                            max_available = min(self.total_budget * allocation_ratio, total_capital)
                            quantity = max(1, int(max_available / current_price))
                            
                            # 변동성 기반 포지션 사이징 (ATR 기반 조정)
                            if len(current_data) > 20:
                                try:
                                    atr = self.tech_indicators.calculate_atr(current_data, period=14).iloc[-1]
                                    
                                    # 모멘텀 계산
                                    momentum = self.tech_indicators.calculate_momentum(current_data, period=10).iloc[-1]
                                    
                                    if not pd.isna(atr) and not pd.isna(momentum):
                                        # 변동성 비율 계산
                                        volatility_ratio = atr / current_price
                                        
                                        # 기본 수량 조정
                                        if volatility_ratio > 0.025:  # 2.5% 이상 변동성 (높음)
                                            quantity = max(1, int(quantity * 0.7))  # 30% 수량 감소
                                        elif volatility_ratio < 0.01:  # 1% 미만 변동성 (낮음)
                                            quantity = max(1, int(quantity * 1.2))  # 20% 수량 증가
                                            
                                        # 모멘텀 기반 추가 조정
                                        if momentum > 5.0:  # 강한 상승 모멘텀
                                            quantity = max(1, int(quantity * 1.1))  # 10% 추가 증가
                                        elif momentum < -3.0:  # 하락 모멘텀
                                            quantity = max(1, int(quantity * 0.9))  # 10% 추가 감소
                                except Exception as e:
                                    pass  # 오류 시 원래 수량 사용
                            
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
                                
                                # 트레일링 스탑 설정
                                if hasattr(strategy, 'params') and (
                                    isinstance(strategy, TrailingStopStrategy) or 
                                    strategy.params.get("use_trailing_stop", False)
                                ):
                                    trailing_pct = strategy.params.get("trailing_stop_pct", 2.0)
                                    
                                    # 원래 트레일링 스탑 비율 백업 (정상 모드 복귀시 사용)
                                    if isinstance(strategy, TrailingStopStrategy):
                                        strategy.params["original_trailing_stop_pct"] = trailing_pct
                                    
                                    # 보수적 모드에서는 더 타이트한 트레일링 스탑 적용
                                    if conservative_mode:
                                        trailing_pct = trailing_pct * 0.8
                                    
                                    virtual_holdings[stock_code]["trailing_stop_price"] = current_price * (1 - trailing_pct/100)
                                
                                # 거래 기록
                                trade_record = {
                                    "stock_code": stock_code,
                                    "stock_name": self.watch_list_info.get(stock_code, {}).get("name", stock_code),
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
                
                # Sharpe Ratio 계산 (추가 성능 지표)
                daily_returns = []
                current_capital = self.total_budget
                dates = sorted(list(set([pd.to_datetime(t.get("date")) for t in trades])))
                
                if dates:
                    start_date = dates[0]
                    end_date = dates[-1]
                    
                    # 일별 자본 변화 추적
                    date_capital = {start_date: self.total_budget}
                    
                    for trade in sorted(trades, key=lambda x: pd.to_datetime(x.get("date"))):
                        trade_date = pd.to_datetime(trade.get("date"))
                        
                        if trade.get("action") == "BUY":
                            current_capital -= trade.get("amount", 0)
                        elif trade.get("action") == "SELL":
                            current_capital += trade.get("price", 0) * trade.get("quantity", 0)
                        
                        date_capital[trade_date] = current_capital
                    
                    # 날짜 정렬
                    sorted_dates = sorted(date_capital.keys())
                    
                    # 일별 수익률 계산
                    for i in range(1, len(sorted_dates)):
                        prev_capital = date_capital[sorted_dates[i-1]]
                        curr_capital = date_capital[sorted_dates[i]]
                        daily_return = (curr_capital - prev_capital) / prev_capital if prev_capital > 0 else 0
                        daily_returns.append(daily_return)
                    
                    if daily_returns:
                        # Sharpe Ratio 계산 (무위험이자율 가정: 연 1.5%)
                        risk_free_rate = 0.015 / 252  # 일별 무위험이자율
                        avg_daily_return = np.mean(daily_returns)
                        std_daily_return = np.std(daily_returns)
                        
                        if std_daily_return > 0:
                            sharpe_ratio = (avg_daily_return - risk_free_rate) / std_daily_return * np.sqrt(252)  # 연율화
                            backtest_results["sharpe_ratio"] = sharpe_ratio
                            
                            # Sortino Ratio 계산 (하락 위험만 고려)
                            negative_returns = [r for r in daily_returns if r < 0]
                            if negative_returns:
                                downside_dev = np.std(negative_returns)
                                if downside_dev > 0:
                                    sortino_ratio = (avg_daily_return - risk_free_rate) / downside_dev * np.sqrt(252)
                                    backtest_results["sortino_ratio"] = sortino_ratio
                
                # 백테스트 결과에 위험 관리 관련 정보 추가
                backtest_results["risk_management"] = {
                    "conservative_mode_activations": sum(1 for trade in trades if "보수적 모드 매도" in trade.get("reason", "")),
                    "trailing_stop_activations": sum(1 for trade in trades if "트레일링 스탑 발동" in trade.get("reason", "")),
                    "time_stop_activations": sum(1 for trade in trades if "타임 스탑 발동" in trade.get("reason", ""))
                }
                
                logger.info(f"백테스트 완료: 최종 자본금 {backtest_results['final_capital']:,.0f}원, " + 
                        f"수익률 {backtest_results['profit_loss_percent']:.2f}%, " +
                        f"승률 {backtest_results['win_rate']:.2f}%")
                
                # 위험 관리 통계 출력
                logger.info(f"위험 관리 통계: 트레일링 스탑 {backtest_results['risk_management']['trailing_stop_activations']}회, " +
                        f"타임 스탑 {backtest_results['risk_management']['time_stop_activations']}회, " +
                        f"보수적 모드 매도 {backtest_results['risk_management']['conservative_mode_activations']}회")
                
                # 백테스트 결과 분석 실행 (새로 추가)
                self.analyze_backtest_results(backtest_results)
                
                return backtest_results
            
        except Exception as e:
            logger.exception(f"백테스트 실행 중 오류: {str(e)}")
            return backtest_results

# 설정파일 생성 함수 개선
def create_config_file(config_path: str = "trend_trader_config.json") -> None:
    """기본 설정 파일 생성 (거래 적극성 대폭 강화)
    
    Args:
        config_path: 설정 파일 경로
    """
    config = {
        "watch_list": [
            {"code": "005490", "name": "POSCO홀딩스", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"},
            {"code": "373220", "name": "LG에너지솔루션", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"},
            {"code": "000660", "name": "SK하이닉스", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"},
            {"code": "035420", "name": "NAVER", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"},
            {"code": "005380", "name": "현대차", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"},
            {"code": "000100", "name": "유한양행", "allocation_ratio": 0.12, "strategy": "BB_StochFilter"},
            {"code": "042660", "name": "한화오션", "allocation_ratio": 0.12, "strategy": "BB_StochFilter"},
            {"code": "051910", "name": "LG화학", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"},
            {"code": "000270", "name": "기아", "allocation_ratio": 0.15, "strategy": "BB_StochFilter"}
        ],
        "total_budget": 5000000,  # 총 투자 예산
        "max_stocks": 7,  # 최대 동시 보유 종목 수 (6에서 7로 증가)
        "min_trading_amount": 300000,  # 최소 거래 금액 (400000에서 300000으로 감소)
        "use_market_trend_filter": False,  # 시장 추세 필터 비활성화 (True에서 False로 변경)
        "market_index_code": "069500",  # KODEX 200
        "time_stop_days": 10,  # 타임 스탑 기준 일수 (12에서 10으로 감소)
        "time_stop_profit_pct": 0.8,  # 타임 스탑 수익률 기준 (1.0에서 0.8로 하향)
        "max_holding_days": 10,  # 최대 보유 기간 (12에서 10으로 감소)

        # 거래 설정
        "trade_settings": {
            "min_trade_interval": 3,       # 최소 거래 간격 (7에서 3으로 대폭 감소)
            "use_trade_interval": True,    # 거래 간격 제한 사용 여부
            "track_trade_history": True    # 거래 이력 추적 사용 여부
        },
        
        # 백테스트 설정
        "backtest_settings": {
            "min_trade_interval": 3,      # 최소 거래 간격 (7에서 3으로 대폭 감소)
            "use_trade_interval": True,   # 거래 간격 제한 사용 여부
            "analyze_results": True,      # 백테스트 결과 자동 분석
            "auto_optimize": True,        # 자동 최적화
            "save_trade_history": True    # 백테스트 거래 이력 저장
        },
        
        # 전략 가중치
        "strategy_weights": {
            "RSI_Default": 1.2,
            "EnhancedRSIStrategy": 1.4,
            "MACD_Default": 0.7,
            "EnhancedMACDStrategy": 1.2,
            "BB_Default": 0.8,
            "BB_StochFilter": 1.5,         # 1.3에서 1.5로 상향 (백테스트 결과에 따라 가중치 증가)
            "MA_Default": 0.8,
            "MultiTimeframeRSIStrategy": 1.4,
            "HybridTrendStrategy": 1.3,
            "VolatilityBreakoutStrategy": 1.2,
            "Composite_Default": 1.4,
            "Composite_Premium": 1.4
        },
        
        # 전략 정의
        "strategies": {
            # 볼린저 밴드 전략 (대폭 완화)
            "BB_Default": {
                "type": "BollingerBand",
                "params": {
                    "bb_period": 20,
                    "bb_std": 1.5,           # 1.8에서 1.5로 더 낮춤 (더 자주 신호 발생)
                    "profit_target": 2.0,     # 3.0에서 2.0으로 하향 (더 빠른 수익실현)
                    "stop_loss_pct": 1.8,     # 2.0에서 1.8로 하향 (더 빠른 손절)
                    "use_stochastic": True,
                    "stoch_k_period": 14,
                    "stoch_d_period": 3,
                    "stoch_oversold_threshold": 30,  # 25에서 30으로 더 완화
                    "stoch_overbought_threshold": 70, # 75에서 70으로 완화
                    "require_stoch_oversold": False,  # 스토캐스틱 필수 조건 해제
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,  # 2.0에서 1.5로 하향 (더 타이트하게)
                    "dynamic_trailing": True,
                    
                    # 추가: 밴드 폭 확인
                    "check_band_width": False,  # True에서 False로 변경 (더 많은 진입)
                    "min_band_width_ratio": 0.02,  # 0.025에서 0.02로 더 완화
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False,  # True에서 False로 변경 (더 많은 진입)
                    "min_volume_ratio": 0.6,  # 0.8에서 0.6으로 더 완화
                    
                    # 최소 보유 기간
                    "min_holding_days": 0  # 1에서 0으로 감소 (당일 매매 허용)
                }
            },
            
            # 스토캐스틱 필터가 적용된 볼린저 밴드 전략 (대폭 완화)
            "BB_StochFilter": {
                "type": "BollingerBand",
                "params": {
                    "bb_period": 20,
                    "bb_std": 1.5,
                    "profit_target": 2.0,
                    "stop_loss_pct": 2.0,  # 1.8에서 2.0으로 상향 (더 여유 있게)
                    "use_stochastic": True,
                    "stoch_k_period": 14,
                    "stoch_d_period": 3,
                    "stoch_oversold_threshold": 30,
                    "stoch_overbought_threshold": 70,
                    "require_stochastic": False,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 3.0,  # 1.5에서 3.0으로 대폭 상향 (더 여유 있게)
                    "dynamic_trailing": True,
                    
                    # RSI 필터
                    "use_rsi_filter": False,
                    "rsi_period": 14,
                    "rsi_oversold_threshold": 40,
                    
                    # 추가: 반등 확인 (매수 시점 최적화)
                    "require_rebound": True,  # 새로 추가: 반등 확인
                    "rebound_days": 1,        # 최소 1일 반등
                    "rebound_percent": 0.5,   # 0.5% 이상 반등
                    
                    # 추가: 밴드 폭 확인
                    "check_band_width": False,
                    "min_band_width_ratio": 0.02,
                    
                    # 최소/최대 보유 기간
                    "min_holding_days": 1,  # 0에서 1로 상향 (너무 짧은 거래 방지)
                    "max_holding_days": 8,  # 최대 보유 기간 설정
                    
                    # 거래량 조건
                    "require_volume_increase": False,
                    "min_volume_ratio": 0.6
                }
            },
            
            # RSI 기반 전략 (완화)
            "RSI_Default": {
                "type": "RSI",
                "params": {
                    "rsi_period": 14,
                    "rsi_oversold_threshold": 40.0,  # 35에서 40으로 더 완화
                    "rsi_overbought_threshold": 60.0, # 65에서 60으로 완화
                    "profit_target": 2.0,        # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,        # 2.0에서 1.8로 하향
                    "bb_period": 20,
                    "bb_std": 1.5,               # 1.8에서 1.5로 낮춤
                    "use_minute_confirm": False,
                    "use_dynamic_stop": True,
                    "atr_period": 14,
                    "atr_multiplier": 1.8,       # 2.0에서 1.8로 하향
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,    # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,     # 1에서 0으로 감소
                    
                    # 추가: 매수 시 추가 필터
                    "require_price_near_lower_band": False,  # 계속 False 유지
                    "require_volume_increase": False        # True에서 False로 변경
                }
            },
                        
            # 이동평균선 기반 전략 (완화)
            "MA_Default": {
                "type": "MovingAverage",
                "params": {
                    "ma_short_period": 3,
                    "ma_mid_period": 10,
                    "ma_long_period": 30,
                    "ma_strategy_type": "bounce",
                    "profit_target": 2.0,      # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,      # 2.0에서 1.8로 하향
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,  # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,     # 1에서 0으로 감소
                    
                    # 추가: 볼륨 필터
                    "require_volume_increase": False,  # True에서 False로 변경
                    
                    # 추가: MA 정렬 필터
                    "require_ma_alignment": False  # 계속 False 유지
                }
            },
            
            # 기본 복합 전략 (완화)
            "Composite_Default": {
                "type": "Composite",
                "params": {
                    "strategies": ["RSI_Default", "BB_StochFilter"],
                    "combine_method": "any",   # 계속 any 유지
                    "profit_target": 2.0,      # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,      # 2.0에서 1.8로 하향
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,  # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,     # 1에서 0으로 감소
                    
                    # 추가: 시장 상황 필터
                    "use_market_filter": False,  # True에서 False로 변경
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False  # True에서 False로 변경
                }
            },
            
            # 새로운 전략: 향상된 RSI 전략 (완화)
            "EnhancedRSIStrategy": {
                "type": "EnhancedRSIStrategy",
                "params": {
                    "rsi_period_short": 9,
                    "rsi_period": 14,
                    "rsi_period_long": 21,
                    "rsi_oversold_threshold": 40.0,  # 35에서 40으로 더 완화
                    "rsi_overbought_threshold": 60.0, # 65에서 60으로 완화
                    "profit_target": 2.0,        # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,        # 2.0에서 1.8로 하향
                    "bb_period": 20,
                    "bb_std": 1.5,               # 1.8에서 1.5로 낮춤
                    "use_minute_confirm": False,
                    "use_dynamic_stop": True,
                    "atr_period": 14,
                    "atr_multiplier": 1.8,       # 2.0에서 1.8로 하향
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,    # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    
                    # 추가: 다이버전스 감지
                    "detect_divergence": False,  # True에서 False로 변경 (더 많은 진입)
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,      # 1에서 0으로 감소
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False  # True에서 False로 변경
                }
            },
            
            # 새로운 전략: 향상된 MACD 전략 (완화)
            "EnhancedMACDStrategy": {
                "type": "EnhancedMACDStrategy",
                "params": {
                    "macd_fast_period": 8,
                    "macd_slow_period": 21,
                    "macd_signal_period": 7,
                    "short_ma_period": 3,
                    "mid_ma_period": 10,
                    "long_ma_period": 20,
                    "momentum_period": 10,
                    "profit_target": 2.0,       # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,       # 2.0에서 1.8로 하향
                    "use_minute_confirm": False,
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,   # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    "min_profit_for_hist_sell": 2.0,  # 3.0에서 2.0으로 하향
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,     # 1에서 0으로 감소
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False,  # True에서 False로 변경
                    
                    # 추가: MA 정렬 필터
                    "require_ma_alignment": False  # 계속 False 유지
                }
            },
            
            # 새로운 전략: 멀티타임프레임 RSI 전략 (완화)
            "MultiTimeframeRSIStrategy": {
                "type": "MultiTimeframeRSIStrategy",
                "params": {
                    "rsi_period": 14,
                    "daily_rsi_oversold_threshold": 40.0,  # 35에서 40으로 더 완화
                    "daily_rsi_overbought_threshold": 60.0, # 65에서 60으로 완화
                    "weekly_rsi_oversold_threshold": 45.0,  # 계속 45 유지
                    "weekly_rsi_overbought_threshold": 60.0, # 65에서 60으로 완화
                    "profit_target": 2.0,      # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,      # 2.0에서 1.8로 하향
                    "bb_period": 20,
                    "bb_std": 1.5,             # 1.8에서 1.5로 낮춤
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,  # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    "min_profit_for_band_sell": 1.5,  # 2.0에서 1.5로 하향
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,     # 1에서 0으로 감소
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False,  # True에서 False로 변경
                    
                    # 추가: 밴드 폭 확인
                    "check_band_width": False,  # True에서 False로 변경
                    "min_band_width_ratio": 0.02  # 0.025에서 0.02로 완화
                }
            },
            
            # 새로운 전략: 하이브리드 추세 전략 (완화)
            "HybridTrendStrategy": {
                "type": "HybridTrendStrategy",
                "params": {
                    "adx_period": 14,
                    "strong_trend_threshold": 15,  # 20에서 15로 더 하향
                    "sideways_threshold": 10,     # 15에서 10으로 더 하향
                    "macd_fast_period": 8,
                    "macd_slow_period": 21,
                    "macd_signal_period": 7,
                    "rsi_period": 14,
                    "rsi_oversold_threshold": 40.0,  # 35에서 40으로 더 완화
                    "rsi_overbought_threshold": 60.0, # 65에서 60으로 완화
                    "bb_period": 20,
                    "bb_std": 1.5,              # 1.8에서 1.5로 낮춤
                    "profit_target": 2.0,       # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,       # 2.0에서 1.8로 하향
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,   # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    "min_profit_for_hist_sell": 2.0,  # 3.0에서 2.0으로 하향
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,     # 1에서 0으로 감소
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False,  # True에서 False로 변경
                    
                    # 추가: ADX 최소값 설정
                    "min_adx_value": 10  # 15에서 10으로 더 하향
                }
            },
            
            # 변동성 돌파 전략 (완화)
            "VolatilityBreakoutStrategy": {
                "type": "VolatilityBreakoutStrategy",
                "params": {
                    "volatility_period": 20,
                    "k_value": 0.4,            # 0.5에서 0.4로 하향 (더 빠른 진입)
                    "ma_short_period": 5,
                    "ma_long_period": 20,
                    "profit_target": 2.0,      # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.5,      # 1.8에서 1.5로 하향
                    "use_volatility_filter": False,  # True에서 False로 변경
                    "use_volume_filter": False,     # True에서 False로 변경
                    "use_trend_filter": False,      # 계속 False 유지
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5,    # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    "use_intraday_exit": False,
                    "intraday_profit_target": 1.5,  # 2.0에서 1.5로 하향
                    "end_of_day_stop_loss": -0.8,   # -1.0에서 -0.8로 상향
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0      # 1에서 0으로 감소
                }
            },
            
            # 최적화된 프리미엄 복합 전략 (완화)
            "Composite_Premium": {
                "type": "Composite",
                "params": {
                    "strategies": ["EnhancedRSIStrategy", "BB_StochFilter"],
                    "combine_method": "any",  # 계속 any 유지
                    "profit_target": 2.0,     # 3.0에서 2.0으로 하향
                    "stop_loss_pct": 1.8,     # 2.0에서 1.8로 하향
                    "use_trailing_stop": True,
                    "trailing_stop_pct": 1.5, # 2.0에서 1.5로 하향
                    "dynamic_trailing": True,
                    
                    # 추가: 최소 보유 기간
                    "min_holding_days": 0,    # 1에서 0으로 감소
                    
                    # 추가: 최대 보유 기간
                    "max_holding_days": 10,   # 12에서 10으로 감소
                    
                    # 추가: 시장 상황 필터
                    "use_market_filter": False,  # True에서 False로 변경
                    
                    # 추가: 거래량 필터
                    "require_volume_increase": False,  # True에서 False로 변경
                    
                    # 추가: 밴드 폭 확인
                    "check_band_width": False,  # True에서 False로 변경
                    "min_band_width_ratio": 0.02  # 0.025에서 0.02로 완화
                }
            }
        },
        
        # 위험 관리 설정 (완화)
        "risk_management": {
            "use_dynamic_trailing_stop": True,
            "use_time_stop": True,
            "monitor_portfolio_risk": True,
            "conservative_mode_threshold": 20.0,     # 15.0에서 20.0으로 상향 (덜 보수적)
            "normal_mode_threshold": 15.0,           # 10.0에서 15.0으로 상향
            "conservative_profit_target_ratio": 0.9, # 0.85에서 0.9로 상향 (덜 보수적)
            "market_condition_check_interval": 20,
            "position_size_limit_ratio": 0.3,        # 0.25에서 0.3으로 상향 (종목당 비중 증가)
            "sector_exposure_limit": 0.4             # 0.35에서 0.4로 상향 (섹터 다양화 완화)
        },
        
        # 동적 트레일링 스탑 설정 (최적화)
        "dynamic_trailing_stop": {
            "very_high_profit_pct": 6.0,
            "very_high_profit_ratio": 0.5,    # 0.3에서 0.5로 상향 (덜 타이트하게)
            "high_profit_pct": 4.0,
            "high_profit_ratio": 0.6,         # 0.4에서 0.6으로 상향 (덜 타이트하게)
            "medium_profit_pct": 2.5,
            "medium_profit_ratio": 0.7,       # 0.5에서 0.7로 상향 (덜 타이트하게)
            "low_profit_pct": 1.5,
            "low_profit_ratio": 0.8,          # 0.7에서 0.8로 상향 (덜 타이트하게)
            "minimal_profit_pct": 0.8,
            "minimal_profit_ratio": 1.0,
            "min_profit_to_apply": 0.8
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
            # 이 부분에 백테스트 결과 분석 함수 추가
            trend_bot.analyze_backtest_results(results)
            
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