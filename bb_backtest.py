#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
bb_trading.py 정확한 백테스트 시스템
- bb_trading.py의 실제 함수들을 그대로 임포트하여 사용
- 실매매와 동일한 로직으로 백테스트 수행
- target_stock_config.json 설정 파일 그대로 사용
"""

import os
import sys
import json
import logging
import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# KIS API 모듈들 임포트 (실제 데이터 조회용)
try:
    import KIS_Common as Common
    import KIS_API_Helper_KR as KisKR
    KIS_API_AVAILABLE = True
    print("✅ KIS API 모듈 임포트 성공")
except ImportError:
    KIS_API_AVAILABLE = False
    print("❌ KIS API 모듈 임포트 실패")
    print("KIS_Common.py와 KIS_API_Helper_KR.py가 필요합니다.")

# 데이터 소스 우선순위 설정
if KIS_API_AVAILABLE:
    DATA_SOURCE = "kis_api"
    print("📊 데이터 소스: KIS API (실제 한국 주식 데이터)")
else:
    try:
        import yfinance as yf
        DATA_SOURCE = "yfinance"
        print("📊 데이터 소스: yfinance (대체 데이터)")
    except ImportError:
        DATA_SOURCE = "sample"
        print("📊 데이터 소스: 샘플 데이터")

# bb_trading.py에서 필요한 함수들 임포트
try:
    from bb_trading import (
        # 설정 클래스
        TradingConfig,
        initialize_config,
        
        # 매매 신호 분석 함수
        analyze_buy_signal,
        analyze_sell_signal,
        
        # 포지션 관리 함수
        calculate_position_size,
        update_trailing_stop,
        calculate_trading_fee,
        
        # 종목 데이터 함수
        get_stock_data,
        
        # 예산 관리 함수
        get_available_budget,
        
        # 환경 감지 함수
        detect_stock_environment,
        
        # 유틸리티 함수
        get_safe_config_value
    )
    print("✅ bb_trading.py 핵심 함수들 임포트 성공")
    BB_FUNCTIONS_AVAILABLE = True
    
except ImportError as e:
    print(f"⚠️ bb_trading.py 함수 임포트 실패: {e}")
    print("일부 함수만 사용 가능합니다.")
    BB_FUNCTIONS_AVAILABLE = False
    
    # 최소한의 설정 클래스만 구현
    class TradingConfig:
        def __init__(self, config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        
        @property
        def target_stocks(self):
            return self.config.get("target_stocks", {})
        
        @property
        def use_absolute_budget(self):
            return self.config.get("use_absolute_budget", False)
        
        @property
        def absolute_budget(self):
            return self.config.get("absolute_budget", 5000000)
        
        @property
        def absolute_budget_strategy(self):
            return self.config.get("absolute_budget_strategy", "proportional")
        
        @property
        def trade_budget_ratio(self):
            return self.config.get("trade_budget_ratio", 0.7)
        
        @property
        def max_positions(self):
            return self.config.get("max_positions", 5)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('accurate_backtest.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('AccurateBacktest')

################################### 백테스트용 데이터 소스 ##################################

def generate_sample_ohlcv_data(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """bb_trading.py 호환 샘플 데이터 생성"""
    try:
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        business_days = [d for d in date_range if d.weekday() < 5]
        
        if len(business_days) == 0:
            return pd.DataFrame()
        
        # 종목별 고정 시드
        np.random.seed(hash(stock_code) % 2**32)
        
        # 기준가 설정 (종목별 다르게)
        base_price = 10000 + (hash(stock_code) % 50000)
        
        # 더 현실적인 데이터 생성
        prices = [base_price]
        volumes = []
        
        for i in range(len(business_days)):
            # 일일 변동률 (-3% ~ +3%)
            daily_return = np.random.normal(0.002, 0.018)
            daily_return = max(-0.03, min(0.03, daily_return))  # 제한
            
            new_price = prices[-1] * (1 + daily_return)
            prices.append(new_price)
            
            # 거래량 (변동성과 연동)
            base_volume = 100000 + abs(hash(stock_code) % 200000)
            volume_multiplier = 1 + abs(daily_return) * 5  # 변동성 클수록 거래량 증가
            volume = int(base_volume * volume_multiplier * np.random.uniform(0.5, 1.5))
            volumes.append(volume)
        
        # OHLCV 데이터 생성
        data = []
        for i, close_price in enumerate(prices[1:]):  # 첫 번째 가격 제외
            prev_close = prices[i]
            
            # 시가는 전일 종가 기준 ±1% 내
            open_price = prev_close * (1 + np.random.normal(0, 0.005))
            
            # 고가, 저가 생성
            high_low_range = abs(close_price - open_price) + close_price * 0.01
            high = max(open_price, close_price) + np.random.uniform(0, high_low_range * 0.5)
            low = min(open_price, close_price) - np.random.uniform(0, high_low_range * 0.5)
            
            # 저가가 고가보다 높으면 조정
            if low > high:
                low, high = high, low
            
            data.append({
                'open': round(open_price, 0),
                'high': round(high, 0),
                'low': round(low, 0), 
                'close': round(close_price, 0),
                'volume': volumes[i]
            })
        
        df = pd.DataFrame(data, index=business_days[:len(data)])
        
        # bb_trading.py와 호환되도록 60일 이상 데이터 보장
        if len(df) < 60:
            # 부족한 데이터를 앞쪽에 추가
            additional_days = 60 - len(df)
            start_extended = business_days[0] - pd.Timedelta(days=additional_days * 2)
            additional_range = pd.date_range(start=start_extended, end=business_days[0], freq='D')
            additional_business_days = [d for d in additional_range if d.weekday() < 5][-additional_days:]
            
            # 추가 데이터 생성
            additional_data = []
            current_price = base_price
            for date in additional_business_days:
                daily_return = np.random.normal(0.001, 0.015)
                current_price *= (1 + daily_return)
                
                open_price = current_price * (1 + np.random.normal(0, 0.005))
                high = max(open_price, current_price) * (1 + abs(np.random.normal(0, 0.01)))
                low = min(open_price, current_price) * (1 - abs(np.random.normal(0, 0.01)))
                volume = int(100000 * np.random.uniform(0.5, 1.5))
                
                additional_data.append({
                    'open': round(open_price, 0),
                    'high': round(high, 0), 
                    'low': round(low, 0),
                    'close': round(current_price, 0),
                    'volume': volume
                })
            
            # 기존 데이터와 합치기
            additional_df = pd.DataFrame(additional_data, index=additional_business_days)
            df = pd.concat([additional_df, df])
        
        logger.info(f"📊 {stock_code} 샘플 OHLCV 데이터 생성: {len(df)}일")
        return df
        
    except Exception as e:
        logger.error(f"샘플 OHLCV 데이터 생성 실패: {e}")
        return pd.DataFrame()

def get_kis_api_data(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """KIS API로부터 한국 주식 데이터 조회 (bb_trading.py와 동일)"""
    try:
        logger.info(f"🔍 {stock_code} KIS API 데이터 조회 시작")
        
        # bb_trading.py와 동일한 방식으로 데이터 조회
        # 기술적 지표 계산을 위해 충분한 기간 조회 (최대 500일)
        df = Common.GetOhlcv("KR", stock_code, 500)
        
        if df is None or len(df) == 0:
            logger.warning(f"❌ {stock_code} KIS API 데이터 없음")
            return pd.DataFrame()
        
        # 날짜 인덱스 확인 및 정리
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        # 백테스트 기간으로 필터링하되, 기술적 지표 계산을 위해 충분한 과거 데이터 유지
        end_dt = pd.to_datetime(end_date)
        start_dt = pd.to_datetime(start_date)
        
        # 시작일보다 60일 앞서부터 데이터 포함 (기술적 지표 계산용)
        extended_start = start_dt - pd.Timedelta(days=90)
        
        # 날짜 필터링
        mask = (df.index >= extended_start) & (df.index <= end_dt)
        filtered_df = df[mask].copy()
        
        if len(filtered_df) == 0:
            logger.warning(f"❌ {stock_code} 기간 내 KIS API 데이터 없음")
            return pd.DataFrame()
        
        # 백테스트 기간 데이터 확인
        backtest_mask = (filtered_df.index >= start_dt) & (filtered_df.index <= end_dt)
        backtest_data = filtered_df[backtest_mask]
        
        if len(backtest_data) == 0:
            logger.warning(f"❌ {stock_code} 백테스트 기간 KIS API 데이터 없음")
            return pd.DataFrame()
        
        # 데이터 품질 검증
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in filtered_df.columns]
        
        if missing_columns:
            logger.error(f"❌ {stock_code} KIS API 데이터 컬럼 부족: {missing_columns}")
            return pd.DataFrame()
        
        # 가격 데이터 유효성 검증
        if (filtered_df['close'] <= 0).any() or filtered_df['close'].isna().any():
            logger.warning(f"⚠️ {stock_code} KIS API 데이터에 이상값 존재")
            # 이상값 제거
            filtered_df = filtered_df[filtered_df['close'] > 0].copy()
            filtered_df = filtered_df.dropna()
        
        logger.info(f"✅ {stock_code} KIS API 데이터 성공")
        logger.info(f"   전체 기간: {filtered_df.index[0].date()} ~ {filtered_df.index[-1].date()}")
        logger.info(f"   백테스트 기간: {backtest_data.index[0].date()} ~ {backtest_data.index[-1].date()}")
        logger.info(f"   전체 일수: {len(filtered_df)}일, 백테스트 일수: {len(backtest_data)}일")
        logger.info(f"   가격 범위: {filtered_df['close'].min():,.0f} ~ {filtered_df['close'].max():,.0f}원")
        
        return filtered_df
        
    except Exception as e:
        logger.error(f"❌ {stock_code} KIS API 조회 중 오류: {str(e)}")
        return pd.DataFrame()

def get_yfinance_data(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """yfinance로부터 한국 주식 데이터 조회 (KIS API 실패시 대체용)"""
    try:
        logger.info(f"🔍 {stock_code} yfinance 데이터 조회 (대체 수단)")
        
        # 한국 주식 티커 변환 (여러 형식 시도)
        possible_tickers = []
        
        # 방법 1: 기본 KS/KQ 방식
        if stock_code.startswith("0"):  # 코스닥
            possible_tickers.append(f"{stock_code}.KQ")
        else:  # 코스피
            possible_tickers.append(f"{stock_code}.KS")
        
        # 방법 2: 반대로도 시도
        if stock_code.startswith("0"):
            possible_tickers.append(f"{stock_code}.KS")
        else:
            possible_tickers.append(f"{stock_code}.KQ")
        
        # 기술적 지표 계산을 위해 시작일보다 90일 일찍 조회
        extended_start = pd.to_datetime(start_date) - pd.Timedelta(days=120)
        
        # 각 티커 형식을 순서대로 시도
        for ticker in possible_tickers:
            try:
                logger.debug(f"yfinance 시도: {ticker}")
                
                stock = yf.Ticker(ticker)
                df = stock.history(
                    start=extended_start.strftime('%Y-%m-%d'), 
                    end=end_date,
                    auto_adjust=True,
                    back_adjust=True
                )
                
                if df.empty or len(df) < 30:
                    continue
                
                # 컬럼명 소문자로 변환
                df.columns = [col.lower() for col in df.columns]
                
                # 필요한 컬럼 확인
                required_columns = ['open', 'high', 'low', 'close', 'volume']
                if not all(col in df.columns for col in required_columns):
                    continue
                
                df = df[required_columns].copy()
                
                # 백테스트 기간 데이터 확인
                backtest_mask = (df.index >= start_date) & (df.index <= end_date)
                backtest_data = df[backtest_mask]
                
                if len(backtest_data) == 0:
                    continue
                
                logger.info(f"✅ {stock_code} yfinance 성공: {ticker}")
                logger.info(f"   전체: {len(df)}일, 백테스트: {len(backtest_data)}일")
                return df
                
            except Exception as e:
                logger.debug(f"yfinance {ticker} 실패: {str(e)[:50]}")
                continue
        
        logger.warning(f"❌ {stock_code} yfinance 모든 시도 실패")
        return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"yfinance 조회 중 오류 ({stock_code}): {e}")
        return pd.DataFrame()

# bb_trading.py 호환 데이터 조회 함수 오버라이드
def get_stock_data_backtest(stock_code: str, all_data: pd.DataFrame, current_date: datetime.date) -> Optional[Dict]:
    """백테스트용 종목 데이터 조회 (bb_trading.py 호환)"""
    try:
        if all_data.empty:
            return None
        
        # 현재 날짜까지의 데이터만 사용 (미래 데이터 방지)
        mask = all_data.index.date <= current_date
        available_data = all_data[mask]
        
        if len(available_data) < 30:
            return None
        
        # 현재가
        current_price = available_data['close'].iloc[-1]
        
        if BB_FUNCTIONS_AVAILABLE:
            # bb_trading.py의 실제 get_stock_data 함수 사용
            # 하지만 데이터는 우리가 제공한 것 사용
            try:
                # bb_trading.py의 get_stock_data 로직을 시뮬레이션
                # (실제로는 KIS API 대신 우리 데이터 사용)
                
                # TechnicalIndicators를 임포트해서 사용
                from bb_trading import TechnicalIndicators
                
                # 기술적 지표 계산
                rsi = TechnicalIndicators.calculate_rsi(available_data, trading_config.rsi_period)
                
                macd_data = TechnicalIndicators.calculate_macd(
                    available_data, trading_config.macd_fast, trading_config.macd_slow, trading_config.macd_signal
                )
                
                bb_data = TechnicalIndicators.calculate_bollinger_bands(
                    available_data, trading_config.bb_period, trading_config.bb_std
                )
                
                # 이동평균선
                ma5 = available_data['close'].rolling(window=5).mean()
                ma20 = available_data['close'].rolling(window=20).mean()
                ma60 = available_data['close'].rolling(window=60).mean()
                
                # ATR
                atr = TechnicalIndicators.calculate_atr(available_data)
                
                # 지지/저항선
                sr_data = TechnicalIndicators.detect_support_resistance(available_data)
                
                return {
                    'stock_code': stock_code,
                    'current_price': current_price,
                    'ohlcv_data': available_data,
                    'rsi': rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50,
                    'macd': macd_data['MACD'].iloc[-1] if not pd.isna(macd_data['MACD'].iloc[-1]) else 0,
                    'macd_signal': macd_data['Signal'].iloc[-1] if not pd.isna(macd_data['Signal'].iloc[-1]) else 0,
                    'macd_histogram': macd_data['Histogram'].iloc[-1] if not pd.isna(macd_data['Histogram'].iloc[-1]) else 0,
                    'bb_upper': bb_data['UpperBand'].iloc[-1] if not pd.isna(bb_data['UpperBand'].iloc[-1]) else 0,
                    'bb_middle': bb_data['MiddleBand'].iloc[-1] if not pd.isna(bb_data['MiddleBand'].iloc[-1]) else 0,
                    'bb_lower': bb_data['LowerBand'].iloc[-1] if not pd.isna(bb_data['LowerBand'].iloc[-1]) else 0,
                    'ma5': ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else 0,
                    'ma20': ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else 0,
                    'ma60': ma60.iloc[-1] if not pd.isna(ma60.iloc[-1]) else 0,
                    'support': sr_data.get("support", 0),
                    'resistance': sr_data.get("resistance", 0),
                    'atr': atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
                }
                
            except Exception as e:
                logger.error(f"bb_trading.py 함수 사용 중 오류: {e}")
                return None
        
        else:
            # bb_trading.py 함수 없으면 간단한 데이터만 제공
            return {
                'stock_code': stock_code,
                'current_price': current_price,
                'ohlcv_data': available_data
            }
        
    except Exception as e:
        logger.error(f"종목 데이터 조회 중 오류 ({stock_code}): {e}")
        return None

################################### 정확한 백테스트 엔진 ##################################

class AccurateBacktest:
    """bb_trading.py 실제 함수 사용한 정확한 백테스트"""
    
    def __init__(self, config_path: str = "target_stock_config.json"):
        self.config_path = config_path
        self.trading_config = None
        self.results = {}
        self.trade_history = []
        self.daily_portfolio = []
        
        self.load_trading_config()
    
    def load_trading_config(self):
        """bb_trading.py와 동일한 방식으로 설정 로드"""
        global trading_config
        
        try:
            if BB_FUNCTIONS_AVAILABLE:
                # bb_trading.py의 initialize_config 함수 사용
                self.trading_config = initialize_config(self.config_path)
                trading_config = self.trading_config  # 전역 변수 설정
            else:
                # 직접 설정 로드
                self.trading_config = TradingConfig(self.config_path)
                trading_config = self.trading_config
            
            logger.info(f"✅ 설정 파일 로드 완료: {self.config_path}")
            logger.info(f"타겟 종목 수: {len(self.trading_config.target_stocks)}개")
            
        except Exception as e:
            logger.error(f"❌ 설정 파일 로드 실패: {e}")
            raise
    
    def get_stock_data_for_backtest(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """백테스트용 종목 데이터 조회 (KIS API 우선 사용)"""
        
        logger.info(f"📊 {stock_code} 데이터 조회 시작...")
        
        # 1. KIS API 시도 (최우선 - bb_trading.py와 동일)
        if KIS_API_AVAILABLE:
            df = get_kis_api_data(stock_code, start_date, end_date)
            if not df.empty and len(df) > 60:
                logger.info(f"✅ {stock_code} KIS API 실제 데이터 사용")
                return df
            else:
                logger.warning(f"⚠️ {stock_code} KIS API 데이터 부족 또는 실패")
        else:
            logger.info(f"⚠️ KIS API 모듈 없음")
        
        # 2. yfinance 시도 (대체 수단)
        if DATA_SOURCE in ["yfinance", "sample"]:
            df = get_yfinance_data(stock_code, start_date, end_date)
            if not df.empty and len(df) > 60:
                logger.info(f"✅ {stock_code} yfinance 데이터 사용")
                return df
            else:
                logger.info(f"⚠️ {stock_code} yfinance 데이터 부족 또는 실패")
        
        # 3. 샘플 데이터 생성 (최후 수단)
        logger.info(f"📊 {stock_code} 샘플 데이터 생성 (최후 수단)")
        
        target_config = self.trading_config.target_stocks.get(stock_code, {})
        stock_name = target_config.get('name', f'종목{stock_code}')
        
        sample_df = self.generate_realistic_sample_data(stock_code, stock_name, start_date, end_date)
        
        if not sample_df.empty:
            logger.info(f"✅ {stock_code}({stock_name}) 샘플 데이터 사용")
            return sample_df
        else:
            logger.error(f"❌ {stock_code} 모든 데이터 소스 실패")
            return pd.DataFrame()
    
    def generate_realistic_sample_data(self, stock_code: str, stock_name: str, start_date: str, end_date: str) -> pd.DataFrame:
        """더 현실적인 샘플 데이터 생성"""
        try:
            # 날짜 범위 설정 (120일 앞서부터 - 기술적 지표 계산용)
            end_dt = pd.to_datetime(end_date)
            start_dt = pd.to_datetime(start_date) - pd.Timedelta(days=120)
            
            date_range = pd.date_range(start=start_dt, end=end_dt, freq='D')
            business_days = [d for d in date_range if d.weekday() < 5]
            
            if len(business_days) == 0:
                return pd.DataFrame()
            
            # 종목별 고정 시드
            np.random.seed(hash(stock_code) % 2**32)
            
            # 종목 특성별 기준가 및 변동성 설정
            if '에너빌리티' in stock_name or '에너지' in stock_name:
                base_price = 15000 + (hash(stock_code) % 30000)  # 15,000~45,000
                volatility = 0.025  # 높은 변동성
            elif '시스템' in stock_name or 'IT' in stock_name:
                base_price = 20000 + (hash(stock_code) % 40000)  # 20,000~60,000
                volatility = 0.022
            elif '현대' in stock_name or '중공업' in stock_name:
                base_price = 50000 + (hash(stock_code) % 100000)  # 50,000~150,000
                volatility = 0.018
            else:
                base_price = 10000 + (hash(stock_code) % 50000)  # 10,000~60,000
                volatility = 0.02
            
            # 트렌드 설정 (3개월간 전체적인 방향)
            trend_direction = (hash(stock_code + stock_name) % 3) - 1  # -1, 0, 1
            daily_trend = trend_direction * 0.0005  # 일일 트렌드
            
            # 가격 시뮬레이션 (더 현실적인 랜덤워크)
            prices = [base_price]
            volumes = []
            
            # 주기적 패턴 추가 (월요일 효과, 금요일 효과 등)
            for i, date in enumerate(business_days):
                # 기본 변동률
                daily_return = np.random.normal(daily_trend, volatility)
                
                # 요일별 효과
                weekday = date.weekday()
                if weekday == 0:  # 월요일 - 약간 하락 편향
                    daily_return -= 0.002
                elif weekday == 4:  # 금요일 - 약간 상승 편향
                    daily_return += 0.001
                
                # 월별 효과 (실제 한국 주식시장 패턴 반영)
                month = date.month
                if month in [1, 11, 12]:  # 연말/연초 효과
                    daily_return += 0.001
                elif month in [4, 5]:  # 봄 시즌
                    daily_return += 0.0005
                
                # 극단적 변동 제한
                daily_return = max(-0.10, min(0.10, daily_return))  # ±10% 제한
                
                new_price = prices[-1] * (1 + daily_return)
                prices.append(new_price)
                
                # 거래량 생성 (변동성과 가격 변화율에 비례)
                base_volume = 100000 + abs(hash(stock_code + str(i)) % 500000)
                volume_multiplier = 1 + abs(daily_return) * 10  # 변동성 클수록 거래량 증가
                
                # 주가 수준별 거래량 조정
                if new_price > base_price * 1.1:  # 고점 근처
                    volume_multiplier *= 1.5
                elif new_price < base_price * 0.9:  # 저점 근처
                    volume_multiplier *= 1.3
                
                volume = int(base_volume * volume_multiplier * np.random.uniform(0.5, 2.0))
                volumes.append(volume)
            
            # OHLCV 데이터 생성
            data = []
            for i in range(1, len(prices)):  # 첫 번째 가격 제외
                close_price = prices[i]
                prev_close = prices[i-1]
                
                # 시가 (전일 종가 기준 ±2% 갭)
                gap_ratio = np.random.normal(0, 0.01)
                gap_ratio = max(-0.05, min(0.05, gap_ratio))  # ±5% 제한
                open_price = prev_close * (1 + gap_ratio)
                
                # 일중 변동폭 계산
                intraday_volatility = abs(close_price - open_price) + close_price * 0.008
                
                # 고가 (시가/종가 중 높은 값 + 일중 상승폭)
                high_base = max(open_price, close_price)
                high_extension = np.random.uniform(0, intraday_volatility * 0.8)
                high = high_base + high_extension
                
                # 저가 (시가/종가 중 낮은 값 - 일중 하락폭)
                low_base = min(open_price, close_price)
                low_extension = np.random.uniform(0, intraday_volatility * 0.8)
                low = max(low_base - low_extension, close_price * 0.5)  # 50% 이하로 떨어지지 않도록
                
                # 데이터 정합성 확인
                high = max(high, open_price, close_price)
                low = min(low, open_price, close_price)
                
                data.append({
                    'open': round(open_price, 0),
                    'high': round(high, 0),
                    'low': round(low, 0),
                    'close': round(close_price, 0),
                    'volume': volumes[i-1]
                })
            
            df = pd.DataFrame(data, index=business_days[1:len(data)+1])
            
            # 데이터 품질 검증
            if len(df) < 60:
                logger.warning(f"{stock_code} 생성된 데이터 부족: {len(df)}일")
                return pd.DataFrame()
            
            # 이상값 검증
            price_changes = df['close'].pct_change().abs()
            if (price_changes > 0.3).any():  # 30% 이상 변동이 있으면 조정
                logger.info(f"{stock_code} 극단적 변동 조정")
                df['close'] = df['close'].rolling(2).mean().fillna(df['close'])
                df['high'] = df[['high', 'close']].max(axis=1)
                df['low'] = df[['low', 'close']].min(axis=1)
            
            logger.info(f"📊 {stock_code}({stock_name}) 현실적 샘플 데이터 생성 완료")
            logger.info(f"   기간: {df.index[0].date()} ~ {df.index[-1].date()}")
            logger.info(f"   가격범위: {df['close'].min():,.0f} ~ {df['close'].max():,.0f}원")
            logger.info(f"   평균변동성: {df['close'].pct_change().std()*100:.2f}%")
            
            return df
            
        except Exception as e:
            logger.error(f"현실적 샘플 데이터 생성 실패 ({stock_code}): {e}")
            return pd.DataFrame()
    
    def simulate_available_budget_accurate(self, total_value: float, initial_total: float, cash: float) -> float:
        """bb_trading.py와 동일한 예산 계산"""
        try:
            if BB_FUNCTIONS_AVAILABLE:
                # 실제 bb_trading.py의 get_available_budget 함수 로직 사용
                # (단, 실제 잔고 대신 시뮬레이션 값 사용)
                
                if self.trading_config.use_absolute_budget:
                    absolute_budget = self.trading_config.absolute_budget
                    strategy = self.trading_config.absolute_budget_strategy
                    
                    if strategy == "strict":
                        return min(absolute_budget, cash)
                    
                    elif strategy == "proportional":
                        if initial_total <= 0:
                            initial_total = total_value
                        
                        performance = (total_value - initial_total) / initial_total
                        
                        # bb_trading.py와 동일한 배율 계산
                        if performance > 0.2:
                            multiplier = min(1.4, 1.0 + performance * 0.3)
                        elif performance > 0.1:
                            multiplier = 1.0 + performance * 0.5
                        elif performance > 0.05:
                            multiplier = 1.0 + performance * 0.8
                        elif performance > -0.05:
                            multiplier = 1.0
                        elif performance > -0.1:
                            multiplier = max(0.95, 1.0 + performance * 0.2)
                        elif performance > -0.2:
                            multiplier = max(0.85, 1.0 + performance * 0.15)
                        else:
                            multiplier = max(0.7, 1.0 + performance * 0.1)
                        
                        adjusted_budget = absolute_budget * multiplier
                        return min(adjusted_budget, cash)
                    
                    elif strategy == "adaptive":
                        loss_tolerance = self.trading_config.budget_loss_tolerance
                        min_budget = absolute_budget * (1 - loss_tolerance)
                        
                        if total_value >= min_budget:
                            budget_target = absolute_budget
                        else:
                            budget_target = max(total_value, min_budget)
                        
                        return min(budget_target, cash)
                
                else:
                    # 비율 기반
                    budget_ratio = self.trading_config.trade_budget_ratio
                    return min(total_value * budget_ratio, cash)
            
            else:
                # bb_trading.py 함수 없으면 간단한 계산
                return cash * 0.7
                
        except Exception as e:
            logger.error(f"예산 계산 중 오류: {e}")
            return cash * 0.7
    
    def run_backtest(self, start_date: str, end_date: str, initial_cash: float = 10000000):
        """정확한 백테스트 실행"""
        logger.info(f"🚀 정확한 백테스트 시작: {start_date} ~ {end_date}")
        logger.info(f"💰 초기 자금: {initial_cash:,.0f}원")
        logger.info(f"🔧 bb_trading.py 함수 사용: {'✅' if BB_FUNCTIONS_AVAILABLE else '❌'}")
        
        # 초기 상태
        cash = initial_cash
        positions = {}
        initial_total_asset = initial_cash
        total_trades = 0
        winning_trades = 0
        total_profit = 0
        
        # 타겟 종목 데이터 조회
        stock_data_dict = {}
        for stock_code in self.trading_config.target_stocks.keys():
            if self.trading_config.target_stocks[stock_code].get('enabled', True):
                df = self.get_stock_data_for_backtest(stock_code, start_date, end_date)
                if not df.empty and len(df) > 60:  # bb_trading.py는 60일 데이터 필요
                    stock_data_dict[stock_code] = df
        
        if not stock_data_dict:
            logger.error("❌ 사용 가능한 종목 데이터가 없습니다.")
            return
        
        # 공통 날짜 범위 설정 (백테스트 기간만)
        all_dates = set()
        for df in stock_data_dict.values():
            backtest_mask = (df.index >= start_date) & (df.index <= end_date)
            backtest_dates = df[backtest_mask].index.date
            all_dates.update(backtest_dates)
        
        trading_dates = sorted(list(all_dates))
        logger.info(f"📅 백테스트 기간: {len(trading_dates)}일")
        
        # 일별 백테스트 실행
        for i, current_date in enumerate(trading_dates):
            try:
                # 현재 날짜의 종목 데이터 준비
                daily_stock_data = {}
                
                for stock_code, all_data in stock_data_dict.items():
                    stock_data = get_stock_data_backtest(stock_code, all_data, current_date)
                    if stock_data:
                        daily_stock_data[stock_code] = stock_data
                
                if not daily_stock_data:
                    continue
                
                # 포지션 현재가 업데이트
                for stock_code, position in positions.items():
                    if stock_code in daily_stock_data:
                        current_price = daily_stock_data[stock_code]['current_price']
                        position['current_price'] = current_price
                        
                        # bb_trading.py의 update_trailing_stop 함수 사용
                        if BB_FUNCTIONS_AVAILABLE:
                            target_config = self.trading_config.target_stocks[stock_code]
                            position = update_trailing_stop(position, current_price, target_config)
                            positions[stock_code] = position
                        else:
                            # 간단한 트레일링 스탑
                            if 'high_price' not in position or current_price > position['high_price']:
                                position['high_price'] = current_price
                
                # 포트폴리오 가치 계산
                stock_value = sum(pos['amount'] * pos.get('current_price', pos['entry_price']) 
                                for pos in positions.values())
                total_value = cash + stock_value
                available_budget = self.simulate_available_budget_accurate(total_value, initial_total_asset, cash)
                
                # 기존 포지션 매도 체크
                positions_to_close = []
                
                for stock_code, position in positions.items():
                    if stock_code not in daily_stock_data:
                        continue
                    
                    try:
                        target_config = self.trading_config.target_stocks[stock_code]
                        
                        if BB_FUNCTIONS_AVAILABLE:
                            # bb_trading.py의 실제 analyze_sell_signal 함수 사용
                            sell_analysis = analyze_sell_signal(daily_stock_data[stock_code], position, target_config)
                        else:
                            # 간단한 매도 신호 (폴백)
                            current_price = daily_stock_data[stock_code]['current_price']
                            entry_price = position['entry_price']
                            profit_rate = (current_price - entry_price) / entry_price
                            
                            stop_loss = target_config.get('stop_loss', -0.03)
                            take_profit = target_config.get('profit_target', 0.06)
                            
                            if profit_rate <= stop_loss:
                                sell_analysis = {
                                    'is_sell_signal': True,
                                    'sell_type': 'stop_loss',
                                    'reason': f"손절 {profit_rate*100:.1f}%",
                                    'profit_rate': profit_rate
                                }
                            elif profit_rate >= take_profit:
                                sell_analysis = {
                                    'is_sell_signal': True,
                                    'sell_type': 'take_profit',
                                    'reason': f"익절 {profit_rate*100:.1f}%", 
                                    'profit_rate': profit_rate
                                }
                            else:
                                sell_analysis = {'is_sell_signal': False}
                        
                        if sell_analysis['is_sell_signal']:
                            # 매도 실행
                            sell_price = daily_stock_data[stock_code]['current_price']
                            sell_amount = position['amount']
                            
                            # bb_trading.py의 calculate_trading_fee 함수 사용
                            if BB_FUNCTIONS_AVAILABLE:
                                sell_fee = calculate_trading_fee(sell_price, sell_amount, False)
                            else:
                                sell_fee = sell_price * sell_amount * 0.003
                            
                            # 손익 계산
                            entry_price = position['entry_price']
                            buy_fee = position.get('buy_fee', 0)
                            gross_profit = (sell_price - entry_price) * sell_amount
                            net_profit = gross_profit - buy_fee - sell_fee
                            
                            # 현금 회수
                            cash += sell_price * sell_amount - sell_fee
                            
                            # 거래 기록
                            self.trade_history.append({
                                'date': current_date,
                                'action': 'SELL',
                                'stock_code': stock_code,
                                'stock_name': target_config.get('name', stock_code),
                                'price': sell_price,
                                'amount': sell_amount,
                                'net_profit': net_profit,
                                'profit_rate': sell_analysis.get('profit_rate', (sell_price - entry_price) / entry_price),
                                'reason': sell_analysis.get('reason', 'Unknown'),
                                'holding_days': (current_date - position['entry_date']).days,
                                'sell_type': sell_analysis.get('sell_type', 'unknown')
                            })
                            
                            # 통계 업데이트
                            total_trades += 1
                            total_profit += net_profit
                            if net_profit > 0:
                                winning_trades += 1
                            
                            positions_to_close.append(stock_code)
                            
                            logger.info(f"💰 매도: {target_config.get('name', stock_code)} "
                                      f"{net_profit:+,.0f}원 ({sell_analysis.get('profit_rate', 0)*100:+.1f}%) "
                                      f"[{sell_analysis.get('sell_type', 'unknown')}]")
                    
                    except Exception as e:
                        logger.error(f"매도 분석 오류 ({stock_code}): {e}")
                        continue
                
                # 매도된 포지션 제거
                for stock_code in positions_to_close:
                    del positions[stock_code]
                
                # 새로운 매수 기회 탐색
                if len(positions) < self.trading_config.max_positions and available_budget > 100000:
                    buy_opportunities = []
                    
                    for stock_code, target_config in self.trading_config.target_stocks.items():
                        if not target_config.get('enabled', True):
                            continue
                        if stock_code in positions:
                            continue
                        if stock_code not in daily_stock_data:
                            continue
                        
                        try:
                            if BB_FUNCTIONS_AVAILABLE:
                                # bb_trading.py의 실제 analyze_buy_signal 함수 사용
                                buy_analysis = analyze_buy_signal(daily_stock_data[stock_code], target_config)
                            else:
                                # 간단한 매수 신호 (폴백)
                                current_price = daily_stock_data[stock_code]['current_price']
                                rsi = daily_stock_data[stock_code].get('rsi', 50)
                                
                                score = 0
                                if rsi <= 30:
                                    score += 30
                                if len(daily_stock_data[stock_code]['ohlcv_data']) >= 20:
                                    ma20 = daily_stock_data[stock_code]['ohlcv_data']['close'].rolling(20).mean().iloc[-1]
                                    if current_price <= ma20 * 1.02:
                                        score += 25
                                
                                min_score = target_config.get('min_score', 70)
                                buy_analysis = {
                                    'is_buy_signal': score >= min_score,
                                    'score': score,
                                    'min_score': min_score,
                                    'signals': [f"간단 분석 점수: {score}"]
                                }
                            
                            if buy_analysis['is_buy_signal']:
                                buy_opportunities.append({
                                    'stock_code': stock_code,
                                    'stock_name': target_config.get('name', stock_code),
                                    'price': daily_stock_data[stock_code]['current_price'],
                                    'score': buy_analysis['score'],
                                    'target_config': target_config,
                                    'analysis': buy_analysis
                                })
                        
                        except Exception as e:
                            logger.error(f"매수 분석 오류 ({stock_code}): {e}")
                            continue
                    
                    # 점수순 정렬 후 매수 실행
                    buy_opportunities.sort(key=lambda x: x['score'], reverse=True)
                    max_new_positions = self.trading_config.max_positions - len(positions)
                    
                    for opportunity in buy_opportunities[:max_new_positions]:
                        if available_budget <= 100000:
                            break
                        
                        stock_code = opportunity['stock_code']
                        stock_price = opportunity['price']
                        target_config = opportunity['target_config']
                        
                        try:
                            if BB_FUNCTIONS_AVAILABLE:
                                # bb_trading.py의 실제 calculate_position_size 함수 사용
                                quantity = calculate_position_size(target_config, available_budget, stock_price)
                            else:
                                # 간단한 포지션 크기 계산
                                allocation_ratio = target_config.get('allocation_ratio', 0.2)
                                allocated_budget = available_budget * allocation_ratio
                                quantity = int(allocated_budget / (stock_price * 1.003))  # 수수료 고려
                            
                            if quantity <= 0:
                                continue
                            
                            # 수수료 계산
                            if BB_FUNCTIONS_AVAILABLE:
                                buy_fee = calculate_trading_fee(stock_price, quantity, True)
                            else:
                                buy_fee = stock_price * quantity * 0.003
                            
                            total_cost = stock_price * quantity
                            total_needed = total_cost + buy_fee
                            
                            if total_needed > cash:
                                continue
                            
                            # 매수 실행
                            cash -= total_needed
                            available_budget -= total_needed
                            
                            # 포지션 생성
                            positions[stock_code] = {
                                'stock_code': stock_code,
                                'entry_price': stock_price,
                                'amount': quantity,
                                'buy_fee': buy_fee,
                                'entry_date': current_date,
                                'current_price': stock_price,
                                'high_price': stock_price,
                                'trailing_stop': stock_price * (1 - target_config.get('trailing_stop', self.trading_config.trailing_stop_ratio))
                            }
                            
                            # 거래 기록
                            self.trade_history.append({
                                'date': current_date,
                                'action': 'BUY',
                                'stock_code': stock_code,
                                'stock_name': target_config.get('name', stock_code),
                                'price': stock_price,
                                'amount': quantity,
                                'total_cost': total_needed,
                                'score': opportunity['score'],
                                'signals': ', '.join(opportunity['analysis'].get('signals', []))
                            })
                            
                            logger.info(f"✅ 매수: {target_config.get('name', stock_code)} "
                                      f"{stock_price:,.0f}원 × {quantity}주 = {total_needed:,.0f}원 "
                                      f"(점수: {opportunity['score']})")
                        
                        except Exception as e:
                            logger.error(f"매수 실행 오류 ({stock_code}): {e}")
                            continue
                
                # 일별 포트폴리오 기록
                stock_value = sum(pos['amount'] * pos.get('current_price', pos['entry_price']) 
                                for pos in positions.values())
                total_value = cash + stock_value
                
                self.daily_portfolio.append({
                    'date': current_date,
                    'cash': cash,
                    'stock_value': stock_value,
                    'total_value': total_value,
                    'available_budget': available_budget,
                    'positions_count': len(positions),
                    'daily_return': (total_value / initial_cash - 1) * 100
                })
                
                # 진행 상황 출력
                if i % 10 == 0 or i == len(trading_dates) - 1:
                    progress = (i + 1) / len(trading_dates) * 100
                    logger.info(f"📊 진행률: {progress:.1f}% ({current_date}) "
                              f"총자산: {total_value:,.0f}원 "
                              f"수익률: {(total_value/initial_cash-1)*100:+.1f}% "
                              f"보유: {len(positions)}개")
            
            except Exception as e:
                logger.error(f"❌ {current_date} 백테스트 중 오류: {e}")
                continue
        
        # 최종 정산 (남은 포지션 매도)
        final_date = trading_dates[-1] if trading_dates else datetime.date.today()
        for stock_code, position in positions.items():
            if stock_code in daily_stock_data:
                final_price = daily_stock_data[stock_code]['current_price']
                sell_amount = position['amount']
                
                if BB_FUNCTIONS_AVAILABLE:
                    sell_fee = calculate_trading_fee(final_price, sell_amount, False)
                else:
                    sell_fee = final_price * sell_amount * 0.003
                
                entry_price = position['entry_price']
                buy_fee = position.get('buy_fee', 0)
                gross_profit = (final_price - entry_price) * sell_amount
                net_profit = gross_profit - buy_fee - sell_fee
                
                cash += final_price * sell_amount - sell_fee
                total_profit += net_profit
                total_trades += 1
                if net_profit > 0:
                    winning_trades += 1
                
                # 최종 정산 거래 기록
                self.trade_history.append({
                    'date': final_date,
                    'action': 'FINAL_SELL',
                    'stock_code': stock_code,
                    'stock_name': self.trading_config.target_stocks[stock_code].get('name', stock_code),
                    'price': final_price,
                    'amount': sell_amount,
                    'net_profit': net_profit,
                    'profit_rate': (final_price - entry_price) / entry_price,
                    'reason': '백테스트 종료',
                    'holding_days': (final_date - position['entry_date']).days,
                    'sell_type': 'final_settlement'
                })
        
        # 최종 결과 계산
        final_value = cash
        total_return = (final_value / initial_cash - 1) * 100
        
        self.results = {
            'initial_cash': initial_cash,
            'final_value': final_value,
            'total_return': total_return,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'winning_rate': winning_trades / max(total_trades, 1) * 100,
            'total_profit': total_profit,
            'trading_days': len(trading_dates),
            'annual_return': total_return * (365 / len(trading_dates)) if len(trading_dates) > 0 else 0,
            'bb_functions_used': BB_FUNCTIONS_AVAILABLE
        }
        
        logger.info("🎯 정확한 백테스트 완료!")
        self.print_results()
        self.print_detailed_analysis()
    
    def print_results(self):
        """결과 출력"""
        if not self.results:
            return
        
        print("\n" + "="*70)
        print("📊 BB TRADING 정확한 백테스트 결과")
        print("="*70)
        print(f"🔧 bb_trading.py 함수 사용: {'✅ YES' if self.results['bb_functions_used'] else '❌ NO'}")
        print(f"💰 초기 자금:       {self.results['initial_cash']:>15,.0f}원")
        print(f"💰 최종 자금:       {self.results['final_value']:>15,.0f}원")
        print(f"📈 총 수익률:       {self.results['total_return']:>15.2f}%")
        print(f"📅 연환산 수익률:   {self.results['annual_return']:>15.2f}%")
        print(f"🔢 총 거래 횟수:     {self.results['total_trades']:>15}회")
        print(f"✅ 승리 거래:       {self.results['winning_trades']:>15}회")
        print(f"🎯 승률:            {self.results['winning_rate']:>15.1f}%")
        print(f"💸 순손익:          {self.results['total_profit']:>15,.0f}원")
        print(f"📅 거래일수:        {self.results['trading_days']:>15}일")
        print("="*70)
    
    def print_detailed_analysis(self):
        """상세 분석 출력"""
        if not self.trade_history:
            return
        
        buy_trades = [t for t in self.trade_history if t['action'] == 'BUY']
        sell_trades = [t for t in self.trade_history if t['action'] in ['SELL', 'FINAL_SELL']]
        
        print("\n📋 거래 분석:")
        print("-" * 70)
        print(f"매수 거래: {len(buy_trades)}회")
        print(f"매도 거래: {len(sell_trades)}회")
        
        if sell_trades:
            profits = [t['net_profit'] for t in sell_trades]
            profit_rates = [t['profit_rate'] * 100 for t in sell_trades]
            holding_days = [t.get('holding_days', 0) for t in sell_trades]
            
            print(f"\n💰 손익 통계:")
            print(f"평균 수익:   {np.mean(profits):>12,.0f}원 ({np.mean(profit_rates):>6.2f}%)")
            print(f"최대 수익:   {max(profits):>12,.0f}원 ({max(profit_rates):>6.2f}%)")
            print(f"최대 손실:   {min(profits):>12,.0f}원 ({min(profit_rates):>6.2f}%)")
            print(f"평균 보유:   {np.mean(holding_days):>12.1f}일")
            print(f"수익 표준편차: {np.std(profits):>8,.0f}원")
            
            # 매도 유형별 분석
            sell_types = {}
            for trade in sell_trades:
                sell_type = trade.get('sell_type', 'unknown')
                if sell_type not in sell_types:
                    sell_types[sell_type] = {'count': 0, 'profit': 0}
                sell_types[sell_type]['count'] += 1
                sell_types[sell_type]['profit'] += trade['net_profit']
            
            print(f"\n📊 매도 유형별 분석:")
            for sell_type, data in sell_types.items():
                avg_profit = data['profit'] / data['count']
                print(f"{sell_type:>15}: {data['count']:>3}회, "
                      f"총 {data['profit']:>10,.0f}원 (평균: {avg_profit:>8,.0f}원)")
        
        # 종목별 성과
        if sell_trades:
            print(f"\n🎯 종목별 성과:")
            print("-" * 70)
            stock_performance = {}
            for trade in sell_trades:
                stock_name = trade.get('stock_name', trade['stock_code'])
                if stock_name not in stock_performance:
                    stock_performance[stock_name] = {
                        'profit': 0, 'trades': 0, 'holding_days': []
                    }
                stock_performance[stock_name]['profit'] += trade['net_profit']
                stock_performance[stock_name]['trades'] += 1
                stock_performance[stock_name]['holding_days'].append(trade.get('holding_days', 0))
            
            # 수익순으로 정렬
            sorted_stocks = sorted(stock_performance.items(), 
                                 key=lambda x: x[1]['profit'], reverse=True)
            
            for stock_name, perf in sorted_stocks:
                avg_profit = perf['profit'] / perf['trades']
                avg_holding = np.mean(perf['holding_days'])
                print(f"{stock_name:>15}: {perf['profit']:>10,.0f}원 "
                      f"({perf['trades']:>2}회, 평균: {avg_profit:>8,.0f}원, "
                      f"보유: {avg_holding:>4.1f}일)")
        
        # 월별 성과
        if self.daily_portfolio:
            print(f"\n📅 월별 성과:")
            print("-" * 70)
            df_portfolio = pd.DataFrame(self.daily_portfolio)
            df_portfolio['date'] = pd.to_datetime(df_portfolio['date'])
            df_portfolio['month'] = df_portfolio['date'].dt.to_period('M')
            
            monthly_returns = df_portfolio.groupby('month').agg({
                'total_value': ['first', 'last'],
                'daily_return': ['min', 'max']
            }).round(2)
            
            for month in monthly_returns.index:
                start_value = monthly_returns.loc[month, ('total_value', 'first')]
                end_value = monthly_returns.loc[month, ('total_value', 'last')]
                monthly_return = (end_value / start_value - 1) * 100
                min_return = monthly_returns.loc[month, ('daily_return', 'min')]
                max_return = monthly_returns.loc[month, ('daily_return', 'max')]
                
                print(f"{month}: {monthly_return:>6.2f}% "
                      f"(최저: {min_return:>6.2f}%, 최고: {max_return:>6.2f}%)")
    
    def save_detailed_results(self, prefix: str = "accurate_backtest"):
        """상세 결과 저장"""
        try:
            # 거래 내역 CSV
            if self.trade_history:
                df_trades = pd.DataFrame(self.trade_history)
                df_trades.to_csv(f"{prefix}_trades.csv", index=False, encoding='utf-8-sig')
                logger.info(f"📊 거래 내역 저장: {prefix}_trades.csv")
            
            # 일별 포트폴리오 CSV
            if self.daily_portfolio:
                df_portfolio = pd.DataFrame(self.daily_portfolio)
                df_portfolio.to_csv(f"{prefix}_portfolio.csv", index=False, encoding='utf-8-sig')
                logger.info(f"📊 포트폴리오 내역 저장: {prefix}_portfolio.csv")
            
            # 결과 요약 JSON
            with open(f"{prefix}_summary.json", 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info(f"📊 결과 요약 저장: {prefix}_summary.json")
            
            print(f"\n✅ 상세 결과 저장 완료:")
            print(f"  - {prefix}_trades.csv (거래 내역)")
            print(f"  - {prefix}_portfolio.csv (일별 포트폴리오)")
            print(f"  - {prefix}_summary.json (결과 요약)")
            
        except Exception as e:
            logger.error(f"결과 저장 중 오류: {e}")

################################### 실행 함수 ##################################

def run_accurate_backtest_3months():
    """정확한 백테스트 (3개월)"""
    try:
        backtest = AccurateBacktest("target_stock_config.json")
        
        end_date = datetime.datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
        
        print(f"🚀 정확한 백테스트 시작 (3개월)")
        print(f"📅 기간: {start_date} ~ {end_date}")
        print(f"🔧 bb_trading.py 함수 사용: {'✅' if BB_FUNCTIONS_AVAILABLE else '❌'}")
        
        backtest.run_backtest(
            start_date=start_date,
            end_date=end_date,
            initial_cash=10000000
        )
        
        # 결과 저장
        backtest.save_detailed_results("accurate_3months")
        
        print("\n✅ 정확한 백테스트 완료!")
        
    except Exception as e:
        logger.error(f"❌ 정확한 백테스트 실행 중 오류: {e}")
        print(f"❌ 오류 발생: {e}")

def run_accurate_backtest_6months():
    """정확한 백테스트 (6개월)"""
    try:
        backtest = AccurateBacktest("target_stock_config.json")
        
        end_date = datetime.datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime('%Y-%m-%d')
        
        print(f"🚀 정확한 백테스트 시작 (6개월)")
        print(f"📅 기간: {start_date} ~ {end_date}")
        print(f"🔧 bb_trading.py 함수 사용: {'✅' if BB_FUNCTIONS_AVAILABLE else '❌'}")
        
        backtest.run_backtest(
            start_date=start_date,
            end_date=end_date,
            initial_cash=10000000
        )
        
        # 결과 저장
        backtest.save_detailed_results("accurate_6months")
        
        print("\n✅ 정확한 백테스트 완료!")
        
    except Exception as e:
        logger.error(f"❌ 정확한 백테스트 실행 중 오류: {e}")
        print(f"❌ 오류 발생: {e}")

def run_accurate_custom_backtest():
    """정확한 사용자 정의 백테스트"""
    print("🎯 정확한 백테스트 설정")
    print("=" * 50)
    print(f"🔧 bb_trading.py 함수 사용: {'✅' if BB_FUNCTIONS_AVAILABLE else '❌'}")
    
    # 기간 설정
    while True:
        try:
            months = int(input("백테스트 기간 (개월, 예: 6): "))
            if months > 0:
                break
            else:
                print("양수를 입력해주세요.")
        except ValueError:
            print("숫자를 입력해주세요.")
    
    # 초기 자금 설정
    while True:
        try:
            initial_cash = int(input("초기 자금 (원, 예: 10000000): "))
            if initial_cash > 0:
                break
            else:
                print("양수를 입력해주세요.")
        except ValueError:
            print("숫자를 입력해주세요.")
    
    # 날짜 계산
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=months*30)).strftime('%Y-%m-%d')
    
    print(f"\n📅 백테스트 기간: {start_date} ~ {end_date}")
    print(f"💰 초기 자금: {initial_cash:,}원")
    
    confirm = input("\n정확한 백테스트를 실행하시겠습니까? (y/n): ")
    if confirm.lower() != 'y':
        print("백테스트를 취소했습니다.")
        return
    
    try:
        backtest = AccurateBacktest("target_stock_config.json")
        backtest.run_backtest(start_date, end_date, initial_cash)
        
        # 결과 저장
        filename = f"accurate_custom_{months}months_{initial_cash//10000}만원"
        backtest.save_detailed_results(filename)
        
        print("\n✅ 정확한 백테스트 완료!")
        
    except Exception as e:
        logger.error(f"❌ 정확한 백테스트 실행 중 오류: {e}")
        print(f"❌ 오류 발생: {e}")

################################### 메인 실행부 ##################################

if __name__ == "__main__":
    Common.SetChangeMode()
    print("🎯 BB Trading 정확한 백테스트 시스템")
    print("(bb_trading.py 실제 함수 사용)")
    print("=" * 60)
    print(f"🔧 bb_trading.py 함수 가용성: {'✅ 사용 가능' if BB_FUNCTIONS_AVAILABLE else '❌ 제한적 사용'}")
    print(f"📊 데이터 소스: {DATA_SOURCE.upper()}")
    if DATA_SOURCE == "kis_api":
        print("   → 실제 한국 주식 데이터 (KIS API)")
        print("   → bb_trading.py와 동일한 데이터 소스")
    elif DATA_SOURCE == "yfinance":
        print("   → 대체 데이터 (yfinance)")
        print("   → KIS API 없을 때 사용")
    else:
        print("   → 샘플 데이터")
        print("   → 실제 API 없을 때 사용")
    print("=" * 60)
    print("1. 정확한 백테스트 (3개월)")
    print("2. 정확한 백테스트 (6개월)")
    print("3. 사용자 정의 정확한 백테스트")
    print("0. 종료")
    
    while True:
        try:
            choice = input("\n선택하세요 (0-3): ")
            
            if choice == "1":
                run_accurate_backtest_3months()
                break
            elif choice == "2":
                run_accurate_backtest_6months()
                break
            elif choice == "3":
                run_accurate_custom_backtest()
                break
            elif choice == "0":
                print("프로그램을 종료합니다.")
                break
            else:
                print("올바른 번호를 입력해주세요.")
                
        except KeyboardInterrupt:
            print("\n\n프로그램을 종료합니다.")
            break
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            break