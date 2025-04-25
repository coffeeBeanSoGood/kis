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
        self.watch_list = self.config.get("watch_list", [])
        self.sector_list = self.config.get("sector_list", [])
        self.budget = self.config.get("budget", 1000000)  # 기본 예산 100만원
        self.profit_target = self.config.get("profit_target", 5.0)  # 목표 수익률 (%)
        self.stop_loss = self.config.get("stop_loss", -3.0)  # 손절 비율 (%)
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
                "budget": 1000000,
                "profit_target": 5.0,
                "stop_loss": -3.0
            }
        except Exception as e:
            logger.exception(f"설정 파일 로드 중 오류: {str(e)}")
            return {}
    
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
                    self.holdings[stock_code] = {
                        "quantity": int(stock.get("StockAmt", 0)),
                        "avg_price": float(stock.get("StockAvgPrice", 0)),
                        "current_price": float(stock.get("StockNowPrice", 0)),
                        "buy_date": datetime.datetime.now().strftime("%Y%m%d")  # 매수일 정보가 없으면 현재 날짜로
                    }
            
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
            
            # 기술적 지표 계산
            daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data)
            daily_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(daily_data)
            daily_data[['MiddleBand', 'UpperBand', 'LowerBand']] = self.tech_indicators.calculate_bollinger_bands(daily_data)
            daily_data[['K', 'D']] = self.tech_indicators.calculate_stochastic(daily_data)
            daily_data['Momentum'] = self.tech_indicators.calculate_momentum(daily_data)
            
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
                minute_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(minute_data)
            
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
                }
            }
            
            # 일봉 기반 매수 시그널 확인
            if not daily_data.empty:
                # 1. RSI 과매도 확인
                rsi_value = daily_data['RSI'].iloc[-1]
                is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value)
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
                # 1. 분봉 RSI 과매도 확인
                minute_rsi_value = minute_data['RSI'].iloc[-1]
                minute_is_oversold = self.tech_indicators.is_oversold_rsi(minute_rsi_value)
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
            # 일봉 기준: RSI 과매도 상태이고 (지지선 근처 또는 모멘텀 상승 전환 또는 골든 크로스)
            daily_buy_signal = is_oversold and (near_support or momentum_turning_up or is_golden_cross)
            minute_buy_signal = False
            
            if minute_data is not None and not minute_data.empty:
                minute_buy_signal = minute_is_oversold or minute_macd_cross_up
            
            # 일봉과 분봉 모두 매수 시그널이면 매수
            analysis_result["is_buy_signal"] = daily_buy_signal and minute_buy_signal
            
            if analysis_result["is_buy_signal"]:
                analysis_result["reason"] = "저점 매수 시그널 발생"
            else:
                analysis_result["reason"] = "매수 조건 불충족"
            
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
                
                avg_price = holding_info.get("avg_price", 0)
                if avg_price <= 0:
                    logger.warning(f"종목 {stock_code} 평균단가가 유효하지 않습니다.")
                    continue
                
                # 수익률 계산
                profit_percent = ((current_price / avg_price) - 1) * 100
                
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
                
                # 3. RSI 과매수 영역
                elif daily_data is not None and not daily_data.empty:
                    daily_data['RSI'] = self.tech_indicators.calculate_rsi(daily_data)
                    rsi_value = daily_data['RSI'].iloc[-1]
                    
                    if self.tech_indicators.is_overbought_rsi(rsi_value):
                        sell_signal = True
                        sell_reason = f"RSI 과매수 영역: {rsi_value:.2f}"
                    
                    # 4. 데드 크로스
                    daily_data['MA5'] = daily_data['close'].rolling(window=5).mean()
                    daily_data['MA20'] = daily_data['close'].rolling(window=20).mean()
                    
                    if self.tech_indicators.is_death_cross(daily_data):
                        sell_signal = True
                        sell_reason = "5일선이 20일선을 하향돌파(데드 크로스)"
                
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
            
            # 관심종목 분석 및 매수 시그널 확인
            for stock_code in self.watch_list:
                # 이미 보유 중인 종목 스킵
                if stock_code in self.holdings:
                    continue
                
                # 최근 확인 시간 체크 (1시간에 한 번만 확인)
                last_check = self.last_check_time.get(stock_code, None)
                now = datetime.datetime.now()
                
                if last_check and (now - last_check).seconds < 3600:
                    continue
                
                # 종목 분석
                analysis_result = self.analyze_stock(stock_code)
                self.last_check_time[stock_code] = now
                
                if analysis_result.get("is_buy_signal", False):
                    stock_name = analysis_result.get("stock_name", stock_code)
                    current_price = analysis_result.get("current_price", 0)
                    
                    logger.info(f"매수 시그널 발생: {stock_code} ({stock_name}), 가격: {current_price:,}원")
                    logger.info(f"매수 이유: {analysis_result.get('reason', '')}")
                    
                    # 예산 내에서 매수 수량 결정
                    max_budget = min(self.budget, available_cash)
                    quantity = max(1, int(max_budget / current_price))
                    
                    if quantity > 0 and current_price > 0:
                        # 주문 가능한 수량으로 보정
                        try:
                            quantity = KisKR.AdjustPossibleAmt(stock_code, quantity, "MARKET")
                            logger.info(f"주문 가능 수량 보정: {quantity}주")
                        except Exception as e:
                            logger.warning(f"주문 가능 수량 보정 실패, 원래 수량으로 진행: {e}")
                        
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
                                "buy_date": now.strftime("%Y%m%d")
                            }
                            self._save_holdings()
                        else:
                            logger.error(f"매수 주문 실패: {stock_code}, {order_result}")
                
                # 처리 간격 두기
                time.sleep(1)
            
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
            "initial_capital": self.budget,
            "final_capital": self.budget,
            "profit_loss": 0,
            "profit_loss_percent": 0,
            "trades": [],
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "max_drawdown": 0
        }
        
        total_capital = self.budget
        virtual_holdings = {}
        trades = []
        
        try:
            # 관심종목 반복
            for stock_code in self.watch_list:
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

                logger.info(f"종목 {stock_code} 백테스트 데이터 기간: {start_date_dt} ~ {end_date_dt}")

                # 기술적 지표 계산
                filtered_data['RSI'] = self.tech_indicators.calculate_rsi(filtered_data)
                filtered_data[['MACD', 'Signal', 'Histogram']] = self.tech_indicators.calculate_macd(filtered_data)
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
                            
                        # 3. RSI 과매수
                        elif self.tech_indicators.is_overbought_rsi(filtered_data.iloc[i]['RSI']):
                            # 매도 실행
                            quantity = virtual_holdings[stock_code]["quantity"]
                            sell_amount = current_price * quantity
                            profit = sell_amount - (avg_price * quantity)
                            
                            # 자본 업데이트
                            total_capital += sell_amount
                            
                            # 거래 기록
                            trades.append({
                                "stock_code": stock_code,
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
                    
                    else:
                        # 매수 조건 확인
                        
                        # 1. RSI 과매도 확인
                        rsi_value = filtered_data.iloc[i]['RSI']
                        is_oversold = self.tech_indicators.is_oversold_rsi(rsi_value)
                        
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
                            # 예산 내에서 매수 수량 결정
                            max_budget = min(self.budget, total_capital)
                            quantity = max(1, int(max_budget / current_price))
                            
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
                        "action": "SELL",
                        "reason": "백테스트 종료",
                        "date": end_date,
                        "price": last_price,
                        "quantity": quantity,
                        "profit_loss": profit,
                        "profit_loss_percent": profit_percent
                    })
            
            # 백테스트 결과 계산
            backtest_results["final_capital"] = total_capital
            backtest_results["profit_loss"] = total_capital - self.budget
            backtest_results["profit_loss_percent"] = (backtest_results["profit_loss"] / self.budget) * 100
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
            capital_history = [self.budget]
            for trade in trades:
                if trade.get("action") == "BUY":
                    capital_history.append(capital_history[-1] - trade.get("amount", 0))
                elif trade.get("action") == "SELL":
                    capital_history.append(capital_history[-1] + trade.get("price", 0) * trade.get("quantity", 0))
            
            max_capital = self.budget
            max_drawdown = 0
            
            for capital in capital_history:
                max_capital = max(max_capital, capital)
                drawdown = (max_capital - capital) / max_capital * 100
                max_drawdown = max(max_drawdown, drawdown)
            
            backtest_results["max_drawdown"] = max_drawdown
            
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
            "005490"  # POSCO홀딩스
        ],
        "sector_list": [
            "2차전지"
        ],
        "budget": 1000000,  # 종목당 최대 투자금액
        "profit_target": 5.0,  # 목표 수익률 (%)
        "stop_loss": -3.0  # 손절 비율 (%)
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