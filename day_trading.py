import json
import pandas as pd
import numpy as np
import discord_alert
import concurrent.futures
import threading

import openai
import urllib.request
import urllib.parse
from dotenv import load_dotenv
import re
import time
from datetime import datetime, timedelta
from pytz import timezone  # 이미 있던 from datetime import datetime 라인 근처에 추가
import os

import requests
from bs4 import BeautifulSoup
from pykrx import stock

import KIS_Common as Common
import KIS_API_Helper_KR as KisKR


################################### 상수 정의 ##################################

# 전략 적용 차별화 시간대 정의
MORNING_SESSION_START_HOUR = 9 #시
MORNING_SESSION_END_HOUR = 10 #시
AFTERNOON_SESSION_START_HOUR = 12 #시
POWER_HOUR = 14  # 파워아워
MORNING_SESSION_END_MINUTE = 30 #분
EARLY_MORNING_END_MINUTE = 40 #분
VERY_EARLY_MORNING_END_MINUTE = 30 #분

# 설정 값
TRADE_BUDGET_RATIO = 0.07  # 전체 계좌의 8%를 이 봇이 사용
INITIAL_STOP_LOSS = -1.2  # 초기 손절라인 2.0%
TRAILING_STOP_GAP = 0.6   # 고점 대비 0.8% 하락시 청산
TRAILING_START = 0.8      # 1.2% 이상 수익시 트레일링 시작
REEVALUATION_MIN_PROFIT = 1.5  # 재평가 최소 수익률 기준 1% 추가

# 리스크 관리 설정
MIN_ATR_TAKE_PROFIT = 3.0  # ATR 기반 익절의 최소 기준(3.0%)
ATR_TAKE_PROFIT_MULTIPLIER = 3  # ATR 기반 익절 계수
IMMEDIATE_TAKE_PROFIT = 1.8  # 즉시 매도 목표 수익률
MAX_DAILY_PROFIT = 1.8  # 일일 최대 수익 한도 1.8%
MORNING_TAKE_PROFIT = 1.1  # 오전장 매수 종목은 1.1% 익절
MAX_DAILY_LOSS = -2.5     # 일일 최대 손실 한도 1.0%
MAX_POSITION_SIZE = 0.3   # 단일 종목 최대 비중 30%
MAX_BUY_AMOUNT = 2   # 당일 최대 매수 보유 종목
MAX_BB_PROXIMITY = 0.03  # 당일 최대 BB 이동 비율
MIN_HOLD_HOURS = 0.5  # 최소 보유 시간 (시간단위)
MAX_EARLY_MORNING_BUY_RSI = 74   # 당일 오전 상한 RSI
MIN_EARLY_MORNING_BUY_RSI = 25   # 당일 오전 하한 RSI
MAX_BUY_RSI = 72   # 당일 상한 RSI
MIN_BUY_RSI = 30   # 당일 하한 RSI

# 종목 선정기준 설정
MIN_MARKET_CAP = 800     # 최소 시가총액 (단위 : 억원)
MAX_STOCK_PRICE = 150000    # 최대 주가 제한
MIN_DAILY_VOLUME = 10000  # 최소 일일 거래량
MIN_PRICE_THRESHOLD = 2500 # 저가 종목 가격 제한

# 전일 고모멘텀 종목 최대 저장 기간
HIGH_MOMENTUM_STORE_DAYS = 5  # 고모멘텀 종목 저장 기간 (일)
HIGH_MOMENTUM_SCORE_THRESHOLD = 70  # 고모멘텀 점수 기준

# 유동성 관련 설정 추가
MAX_VOLUME_RATIO = 0.1    # 거래량의 최대 10%까지만 매매
VOLUME_WINDOW = 5         # 5일 평균 거래량 사용

# 홍인기 전략 관련 상수 추가
MIN_RISE_RATE = 3.0       # 최소 상승률 (default 5% 에서 하향 조정)
MIN_INDUSTRY_COUNT = 3    # 주도 산업 판단을 위한 최소 종목 수

# 신고가 돌파 전략 설정
MIN_GAP_PERCENT = 0.5     # 갭 상승 최소 비율 (0.5%)
MIN_BREAKOUT_VOLUME = 0.8 # 신고가 돌파 시 거래량 기준 (전일 대비 80%)
TWIN_PEAKS_MAX_GAP = 10   # 쌍봉 패턴 최대 봉 간격
TWIN_PEAKS_SIMILARITY = 0.05  # 쌍봉 고점 간 가격 차이 허용 범위 (5%)

# 분봉 분석 설정
MINUTE_INTERVAL = 1       # 분봉 기준 (1분봉)
BUYING_PRESSURE_THRESHOLD = 0.3  # 매수세 강도 기준 (30%)
VOLUME_SURGE_THRESHOLD = 2.0     # 거래량 급증 기준 (평균 대비 2배)
MOMENTUM_LOSS_THRESHOLD = -0.01  # 모멘텀 상실 판단 기준 (-1%)

# 상수 추가
NEWS_NEGATIVE_THRESHOLD = 50  # 부정적 뉴스 판단 기준 (50%)
NEWS_POSITIVE_THRESHOLD = 30  # 긍정적 뉴스 판단 기준 (30%)
CACHE_EXPIRY = 180        # 캐시 만료 시간 (초)

# 봇 네임 설정
BOT_NAME = Common.GetNowDist() + "_DayTradeMomentumBot"

################################################################################
# 분할매수 관련 상수 정의
################################################################################
# 분할매수 설정
ENABLE_FRACTIONAL_BUY = True     # 분할매수 기능 활성화 여부
MAX_BUY_STAGES = 3               # 최대 매수 단계 (3회)
FIRST_BUY_RATIO = 0.33           # 첫 번째 매수 비율 (33%)
SECOND_BUY_RATIO = 0.33          # 두 번째 매수 비율 (33%)
THIRD_BUY_RATIO = 0.34           # 세 번째 매수 비율 (34%)

# 분할매수 사이 최소 대기 시간
FRACTIONAL_BUY_COOLDOWN = 15*60  # 15분 (초 단위)

################################################################################
# 분할매도 관련 상수 정의
################################################################################

# 분할매도 설정
ENABLE_FRACTIONAL_SELL = True     # 분할매도 기능 활성화 여부
FIRST_PROFIT_THRESHOLD = 0.6      # 첫 번째 매도 수익률 기준 (0.6%)
SECOND_PROFIT_THRESHOLD = 2.0     # 두 번째 매도 수익률 기준 (2.0%)
THIRD_PROFIT_THRESHOLD = 2.5      # 세 번째 매도 수익률 기준 (2.5%)
FIRST_SELL_RATIO = 0.3            # 첫 번째 매도 비율 (30%)
SECOND_SELL_RATIO = 0.3           # 두 번째 매도 비율 (40%)
THIRD_SELL_RATIO = 1.0            # 세 번째 매도 비율 (나머지 전체)

# 고변동성 종목 조기 수익 실현 설정
HIGH_VOLATILITY_THRESHOLD = 3.0   # 고변동성 판단 ATR 기준 (3% 이상)
HIGH_VOL_PROFIT_THRESHOLD = 1.5   # 고변동성 매도 수익률 기준 (1.5%)
HIGH_VOL_SELL_RATIO = 0.5         # 고변동성 매도 비율 (50%)

# 분할매도 쿨다운 시간 (동일 종목 연속 분할매도 방지)
FRACTIONAL_SELL_COOLDOWN = 20*60  # 20분 (초 단위)


# 파일 상단(글로벌 변수 정의 부분)에 락 객체 추가 // 병렬처리 시 안정성 개선
api_lock = threading.Lock()

################################### 로깅 처리 ##################################

import logging
from logging.handlers import TimedRotatingFileHandler

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
logger = logging.getLogger('DayTradeLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'day_trading.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=3,    # 3일치 로그 파일만 보관
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

# KIS_API_Helper_KR과 KIS_Common 모듈에 로거 전달
KisKR.set_logger(logger)
Common.set_logger(logger)


################################### 캐시 처리 ##################################

# TimedCache 클래스 정의
class TimedCache:
    def __init__(self, expiry_seconds=CACHE_EXPIRY):
        self.cache = {}
        self.expiry = expiry_seconds
        self._last_cleanup = time.time()
        
    def get(self, key):
        self.cleanup()
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.expiry:
                return data
            del self.cache[key]
        return None
        
    def set(self, key, value):
        self.cache[key] = (value, time.time())
        
    def cleanup(self):
        current_time = time.time()
        if current_time - self._last_cleanup >= 60:
            expired_keys = [k for k, v in self.cache.items() 
                          if current_time - v[1] >= self.expiry]
            for k in expired_keys:
                del self.cache[k]
            self._last_cleanup = current_time

# 캐시 관리자 클래스 정의 (싱글톤으로 구현)
class CacheManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CacheManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.caches = {
            'volume_rank': TimedCache(expiry_seconds=60),    # 1분
            'stock_data': TimedCache(expiry_seconds=60),     # 1분
            'minute_data': TimedCache(expiry_seconds=60),    # 1분
            'sector_info': TimedCache(expiry_seconds=3600),  # 1시간
            'volume_data': TimedCache(expiry_seconds=300),   # 5분
            'stock_list': TimedCache(expiry_seconds=300),    # 5분
            'news_articles': TimedCache(expiry_seconds=3600),  # 1시간
            'news_analysis': TimedCache(expiry_seconds=3600), # 1시간
            'order_book_history': TimedCache(expiry_seconds=60),  # 1분 동안 캐시            
            'momentum_data': TimedCache(expiry_seconds=180),  # 3분 (180초) 만료
            'discord_news_messages': TimedCache(expiry_seconds=3600),  # 1시간 (캐시 기간 조정 가능)
            'discord_price_alerts': TimedCache(expiry_seconds=3600),    # 1시간 고점 알림용 새로운 캐시
            'discord_loss_messages': TimedCache(expiry_seconds=3600),  # 1시간 (캐시 기간 조정 가능)
            'discord_scan_messages': TimedCache(expiry_seconds=3600)  # 1시간 동안 중복 알림 방지
        }
        self._initialized = True

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, cache_type, key):
        if cache_type in self.caches:
            return self.caches[cache_type].get(key)
        return None

    def set(self, cache_type, key, value):
        if cache_type in self.caches:
            self.caches[cache_type].set(key, value)

    def create_key(self, *args):
        return '_'.join(str(arg) for arg in args)

def cached(cache_type, expiry=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 캐시 매니저 인스턴스 얻기
            cache_manager = CacheManager.get_instance()
            
            # 캐시 키 생성
            cache_key = cache_manager.create_key(
                func.__name__,
                *args,
                *[f"{k}={v}" for k, v in sorted(kwargs.items())]
            )
            
            # 캐시된 결과 확인
            cached_result = cache_manager.get(cache_type, cache_key)
            if cached_result is not None:
                logger.info(f"캐시 히트: {func.__name__}")
                return cached_result
            
            # 함수 실행 및 결과 캐싱
            result = func(*args, **kwargs)
            cache_manager.set(cache_type, cache_key, result)
            return result
        return wrapper
    return decorator        

# 전역 캐시 매니저 인스턴스 생성
cache_manager = CacheManager.get_instance()    

################################### 캐시 처리 끝 ##################################


# Common.SetChangeMode("VIRTUAL")  # 실제 계좌 거래시 주석 처리
Common.SetChangeMode()



################################### 전략 적용 시간대 구분   ##################################

def is_in_morning_session(): #오전 9시 ~ 10시30분
    now = datetime.now()
    return (MORNING_SESSION_START_HOUR <= now.hour < MORNING_SESSION_END_HOUR) or \
           (now.hour == MORNING_SESSION_END_HOUR and now.minute <= MORNING_SESSION_END_MINUTE)

def is_in_early_morning_session(): # 오전 9시 ~ 9시 40분
    now = datetime.now()
    return (now.hour == MORNING_SESSION_START_HOUR and now.minute <= EARLY_MORNING_END_MINUTE)

def is_in_very_early_morning_session(): # 오전 9시 ~ 9시 30분
    now = datetime.now()
    return (now.hour == MORNING_SESSION_START_HOUR and now.minute <= VERY_EARLY_MORNING_END_MINUTE)

# 새로운 함수 추가: 9시 5분 이전인지 확인하는 함수
def is_too_early_for_trading():
    now = datetime.now()
    return (now.hour == MORNING_SESSION_START_HOUR and now.minute < 5)    

def is_in_afternoon_session(): # 오후 12시 이후, 수익보호를 위한 update_trailing_stop 처리
    now = datetime.now()
    return (now.hour >= AFTERNOON_SESSION_START_HOUR)

def is_in_powerhour_session(): # 14시 이후
    now = datetime.now()
    return (now.hour >= POWER_HOUR)


################################### 동적 스탑로스 계산 ##################################

def calculate_adaptive_stop_loss(entry_price, atr, current_price, initial_stop_rate=INITIAL_STOP_LOSS):
    """
    변동성 적응형 스탑로스 계산 - 수정된 버전
    
    Args:
        entry_price (float): 진입 가격
        atr (float): 평균 진폭 범위 
        current_price (float): 현재 가격
        initial_stop_rate (float): 초기 손실 허용 비율 (기본 -2.5%)
    
    Returns:
        float: 계산된 스탑로스 가격 (항상 entry_price보다 낮음)
    """
    try:
        # initial_stop_rate가 음수임을 확인 (예: -2.5)
        if initial_stop_rate > 0:
            initial_stop_rate = -initial_stop_rate
            
        # 변동성 기반 멀티팩터 계산
        volatility_factor = atr / current_price 
        
        # 동적 ATR 멀티플라이어 
        #adaptive_multiplier = max(1.0, min(2.0, 1.2 * (1 / volatility_factor)))
            
        # 동적 ATR 멀티플라이어 증가 (1.0~2.0 → 1.5~2.5)
        adaptive_multiplier = max(1.5, min(2.5, 1.5 * (1 / volatility_factor)))


        # 손절매 가격 계산 - 진입가에서 손실률을 빼는 방식으로 계산
        # stop_loss = entry_price * (1 + (initial_stop_rate / 100) * 0.8)  # 초기 손실률의 80%만 적용

        # 손절매 가격 계산 - adaptive_multiplier를 실제로 사용
        stop_loss = entry_price * (1 + (initial_stop_rate / 100) * adaptive_multiplier * 0.7)

        
        # 추가 안전장치 - 손절가는 항상 진입가보다 낮아야 함
        if stop_loss >= entry_price:
            stop_loss = entry_price * (1 + initial_stop_rate/100)  # 기본 손절률 적용
            
        # 최소 손실률 보장 (너무 타이트하지 않게)
        # min_stop_loss = entry_price * (1 - 0.01)  # 최소 1% 손실 허용
        min_stop_loss = entry_price * (1 - 0.015)  # 최소 1.5% 손실 허용(기존 1%에서 완화)

        # 최대 손실률 제한
        max_stop_loss = entry_price * (1 + initial_stop_rate/100)  # 초기 손실률 적용
        
        # 최종 스탑로스 결정 (범위 내에 있도록)
        stop_loss = min(max(stop_loss, max_stop_loss), min_stop_loss)
        
        return stop_loss
    
    except Exception as e:
        logger.error(f"Adaptive Stop Loss 계산 중 에러: {str(e)}")
        # 에러시 기본 스탑로스 적용 (진입가의 initial_stop_rate%)
        return entry_price * (1 + initial_stop_rate/100)

    
################################### 동적 스탑로스 계산 끝 ##################################

def check_rsi_divergence(stock_data):
    """
    RSI Divergence 발생 여부 확인
    가격 고점 갱신, RSI는 하락 중이면 True 반환
    """
    try:
        df = stock_data['minute_ohlcv']
        if len(df) < 10:
            return False

        # 종가, RSI 계산
        closes = df['close']
        delta = closes.diff().fillna(0)
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=9, min_periods=1).mean()
        avg_loss = loss.rolling(window=9, min_periods=1).mean()
        rs = avg_gain / avg_loss.replace(0, 0.00001)
        rsi = 100 - (100 / (1 + rs))

        # 최근 고점, RSI 값
        recent_high = closes.iloc[-5:].max()
        prev_high = closes.iloc[-10:-5].max()
        recent_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-5]

        # 가격 고점 갱신 & RSI 하락 Divergence
        if recent_high > prev_high and recent_rsi < prev_rsi:
            return True
        else:
            return False

    except Exception as e:
        logger.error(f"RSI Divergence 체크 중 에러: {str(e)}")
        return False


# 트렌드 전환 감지 함수 (수정)
def check_trend_reversal(stock_data):
    """
    주식의 트렌드 반전 가능성을 분석하는 함수
    - 시간대별 유연한 분석 로직
    - 다양한 기술적 지표 종합 활용
    """
    try:    
        # 현재 시간 확인
        now = datetime.now()
        is_morning_session = is_in_morning_session()
        is_early_morning = is_in_early_morning_session()
        
        # 데이터 요구사항 동적 조정
        min_data_points = 3 if is_early_morning else 8
        
        # DataFrame 검증
        df = stock_data['ohlcv']
        if df is None or len(df) < min_data_points:
            # 데이터 부족 시 조건부 통과 - 장 초반에는 더 관대하게
            if is_early_morning:
                logger.info(f"장 초반 데이터 부족, 조건부 통과 처리")
                return True
            else:
                logger.info(f"데이터 부족으로 트렌드 반전 분석 불가")
                return False

        current_price = stock_data['current_price']
        
        # 1. MACD 분석 (30점)
        macd_score = 0
        try:
            # 장초반에는 더 짧은 기간의 MACD 사용
            short_span = 8 if is_early_morning else 12
            long_span = 17 if is_early_morning else 26
            
            exp1 = df['close'].ewm(span=short_span, adjust=False).mean()
            exp2 = df['close'].ewm(span=long_span, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            # NaN 값 체크 및 안전 처리
            macd_current = macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0
            macd_prev = macd.iloc[-2] if len(macd) > 1 and not pd.isna(macd.iloc[-2]) else 0
            signal_current = signal.iloc[-1] if not pd.isna(signal.iloc[-1]) else 0
            
            macd_diff = macd_current - signal_current
            macd_change = macd_current - macd_prev
            
            logger.info(f"MACD 분석:")
            logger.info(f"- MACD/Signal 차이: {macd_diff:.3f}")
            logger.info(f"- MACD 변화량: {macd_change:.3f}")

            if macd_diff > 0:
                macd_score += 15
                logger.info("MACD > Signal (+15)")
            elif is_morning_session and macd_diff > -0.3:  # 오전장 조건 완화
                macd_score += 10
                logger.info("MACD 근접 (+10)")
            
            if macd_change > 0:
                macd_score += 10
                logger.info("MACD 상승중 (+10)")
        except Exception as e:
            logger.error(f"MACD 분석 중 에러: {str(e)}")

        # 2. 이동평균선 분석 (20점)
        ma_score = 0
        try:
            # 최소 기간 설정으로 NaN 방지
            ma5 = df['close'].rolling(window=5, min_periods=1).mean()
            ma20 = df['close'].rolling(window=20, min_periods=1).mean()
            
            # NaN 값 확인 및 처리
            ma5_current = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else current_price
            ma20_current = ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else current_price
            
            # 안전한 비율 계산
            price_ma5_ratio = current_price / ma5_current if ma5_current > 0 else 1
            price_ma20_ratio = current_price / ma20_current if ma20_current > 0 else 1
            
            # 연속 양봉 패턴
            bullish_candles = df[df['close'] > df['open']]
            bullish_ratio = len(bullish_candles) / len(df) if len(df) > 0 else 0
            
            # 장기 추세 변화 감지
            long_term_trend_change = (
                current_price > ma20_current and  # 20일선 상향 돌파
                bullish_ratio > 0.6  # 60% 이상 양봉
            )
            
            logger.info(f"이동평균선 분석:")
            logger.info(f"- 현재가/MA5 비율: {price_ma5_ratio:.3f}")
            logger.info(f"- 현재가/MA20 비율: {price_ma20_ratio:.3f}")
            
            if price_ma5_ratio > 1.001:
                ma_score += 10
                logger.info("MA5 상향돌파 (+10)")
            elif is_morning_session and 0.995 < price_ma5_ratio <= 1.001:
                ma_score += 5
                logger.info("MA5 근접 (+5)")
            
            if current_price > ma20_current:
                ma_score += 10
                logger.info("MA20 상향 (+10)")
            elif is_morning_session and 0.99 < price_ma20_ratio <= 1:
                ma_score += 5
                logger.info("MA20 근접 (+5)")
            
            # 추세 반전 시 추가 점수
            if long_term_trend_change:
                ma_score += 5
                logger.info("장기 추세 반전 (+5)")
        except Exception as e:
            logger.error(f"이동평균 분석 중 에러: {str(e)}")

        # 3. 거래량 분석 (25점)
        volume_score = 0
        try:
            # 동적 윈도우 크기 선택
            window_sizes = [3, 5, 10] if not is_early_morning else [3]
            
            volume_scores = []
            
            for window in window_sizes:
                # 최근 거래량들
                recent_volumes = df['volume'].tail(window)
                
                # 현재 거래량
                current_volume = recent_volumes.iloc[-1]
                
                # 평균 및 표준편차 계산
                avg_volume = recent_volumes.mean()
                std_volume = recent_volumes.std()
                
                # 변동성을 고려한 점수 계산
                # 평균보다 높고, z-score로 변동성 반영
                z_score = (current_volume - avg_volume) / (std_volume + 1)  # +1로 0으로 나누기 방지
                
                # 시간대별 기준 차등 적용
                if is_early_morning:
                    volume_threshold = 1.2
                    max_score = 15
                else:
                    volume_threshold = 1.5
                    max_score = 25
                
                # 복합 점수 계산
                if current_volume > avg_volume * volume_threshold:
                    # z-score에 따라 점수 차등 부여
                    volume_score_window = min(max_score, int(max_score * (1 + z_score)))
                    volume_scores.append(volume_score_window)
            
            # 여러 윈도우 중 최대 점수 선택
            volume_score = max(volume_scores) if volume_scores else 0
            
            logger.info(f"거래량 분석:")
            logger.info(f"- 분석 윈도우: {window_sizes}")
            logger.info(f"- 최종 거래량 점수: {volume_score}")
            
            # 거래량 점수에 상한선 설정
            volume_score = min(volume_score, 25)
        except Exception as e:
            logger.error(f"거래량 분석 중 에러: {str(e)}")

        # 4. RSI 분석 (15점)
        rsi_score = 0
        try:
            # 시간대별 RSI 범위 조정
            if is_early_morning:
                rsi_lower = MIN_EARLY_MORNING_BUY_RSI
                rsi_upper = MAX_EARLY_MORNING_BUY_RSI
            else:
                rsi_lower = MIN_BUY_RSI
                rsi_upper = MAX_BUY_RSI

            # RSI 계산 - 안전한 방식
            rsi_period = 14
            delta = df['close'].diff().fillna(0)  # NaN 값 자동 처리
            
            if len(df) >= rsi_period + 1:
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                
                # min_periods=1 추가로 데이터 부족시 NaN 방지
                avg_gain = gain.rolling(window=rsi_period, min_periods=1).mean()
                avg_loss = loss.rolling(window=rsi_period, min_periods=1).mean()
                
                # 0으로 나누기 방지
                rs = avg_gain / avg_loss.replace(0, 0.00001)
                rsi = 100 - (100 / (1 + rs))
                
                # 마지막 값이 NaN인 경우 처리
                current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
                rsi_direction = True  # 기본값 설정
                
                if len(rsi) >= 2 and not pd.isna(rsi.iloc[-2]):
                    rsi_direction = current_rsi > rsi.iloc[-2]
                
                logger.info(f"RSI 분석: {current_rsi:.1f}")
                
                if rsi_lower < current_rsi < rsi_upper:
                    rsi_score += 10
                    logger.info("RSI 적정구간 (+10)")
                
                # RSI 방향성 점수 추가
                if rsi_direction and not pd.isna(current_rsi):
                    rsi_score += 5
                    logger.info("RSI 상승중 (+5)")
            else:
                logger.info("RSI 계산을 위한 데이터 부족")
        except Exception as e:
            logger.error(f"RSI 분석 중 에러: {str(e)}")

        # 점수 합산
        reversal_score = macd_score + ma_score + volume_score + rsi_score

        # 시간대별 점수 기준 차등 적용
        if is_early_morning:
            # 장 초반: 더 낮은 점수로 통과 가능
            reversal_threshold = 4  # 기존 5점에서 4점으로 완화
        else:
            reversal_threshold = 5  # 기존 기준 유지

        # 트렌드 반전 여부 최종 판단
        is_reversal_likely = reversal_score >= reversal_threshold
        
        logger.info(f"트렌드 반전 점수: {reversal_score}/16 (기준: {reversal_threshold}점)")
        
        # 고모멘텀 종목에 대한 예외 처리 강화
        if 'momentum_score' in stock_data:
            # 모멘텀 점수에 따라 더 세밀한 예외 처리
            if stock_data['momentum_score'] >= 80 and reversal_score >= 3:
                logger.info(f"고모멘텀 종목({stock_data['momentum_score']}) - 낮은 점수도 통과")
                is_reversal_likely = True
            elif stock_data['momentum_score'] >= 65 and reversal_score >= 4:
                logger.info(f"높은 모멘텀 종목({stock_data['momentum_score']}) - 기준 완화")
                is_reversal_likely = True
        
        return is_reversal_likely
        
    except Exception as e:
        logger.error(f"트렌드 전환 감지 중 에러: {str(e)}")
        
        # 장 초반에는 에러 발생해도 True 반환
        if is_early_morning:
            logger.warning(f"장초반 트렌드 분석 에러 - 완화된 기준 적용: {str(e)}")
            return True
        
        return False



# check_trend_reversal 함수에 돌파 패턴 감지 로직 추가
def check_breakout_pattern(stock_data):
    """이동평균선 돌파 패턴 감지 함수"""
    try:
        df = stock_data['ohlcv']
        current_price = stock_data['current_price']
        
        # 20일 이동평균선 돌파 확인
        ma20 = stock_data.get('ma20', 0)
        prev_close = stock_data.get('prev_close', 0)
        
        # 전일 종가는 MA20 아래, 현재가는 MA20 위 = 돌파
        breakout_ma20 = (prev_close < ma20 and current_price > ma20)
        
        # 거래량 동반 확인
        volume_increase = stock_data['volume'] > stock_data['volume_ma5'] * 1.5
        
        if breakout_ma20 and volume_increase:
            logger.info(f"MA20 상향 돌파 패턴 감지! (거래량 증가 동반)")
            return True
            
        return False
    except Exception as e:
        logger.error(f"돌파 패턴 감지 중 에러: {str(e)}")
        return False


#@cached('minute_data')
def check_short_term_momentum(stock_data):
    """
    단기 모멘텀 확인 - 매수세 강도 반영, 트렌드 전환 및 양봉비율 완화 적용
    """
    try: 
        # 현재 시간 확인
        now = datetime.now()
        is_morning_session = is_in_morning_session()
        is_early_morning = is_in_early_morning_session()
        
        # 종목 코드 가져오기
        stock_code = stock_data.get('code', 'unknown')
        stock_name = KisKR.GetStockName(stock_code)
        
        # 캐시 매니저 인스턴스 가져오기
        cache_manager = CacheManager.get_instance()
        rejection_key = cache_manager.create_key(stock_code, 'momentum_rejection')
        # 기존 캐시 조회
        rejection_data = cache_manager.get('momentum_data', rejection_key)        

        # 이전에 거부된 종목인지 확인 (약 15분의 쿨다운 적용)
        if rejection_data:
            logger.info(f"{stock_name}({stock_code}): 최근 거부된 종목")
            return False

        # 기존 데이터 유효성 검사 로직 유지
        if not isinstance(stock_data, dict):
            logger.error(f"유효하지 않은 stock_data 타입: {type(stock_data)}")
            # 거부 이력 기록
            cache_manager.set('momentum_data', rejection_key, {
                'time': now.timestamp(),
                'reason': '데이터 형식 오류'
            })
            return False

        # 필수 키 확인 로직 유지
        required_keys = ['code', 'current_price', 'ohlcv']
        for key in required_keys:
            if key not in stock_data:
                logger.error(f"필수 키 누락: {key}")
                # 거부 이력 기록
                cache_manager.set('momentum_data', rejection_key, {
                    'time': now.timestamp(),
                    'reason': f'필수 데이터 누락: {key}'
                })
                return False

        # 장초반 데이터 부족 처리 로직 완화
        if is_early_morning:
            logger.info(f"장초반 모멘텀 체크 - 데이터 요구사항 완화")
            return True

        # 분봉 데이터 로드 로직 강화
        if 'minute_ohlcv' not in stock_data or stock_data['minute_ohlcv'] is None:
            logger.info(f"{stock_code}: 분봉 데이터 없음")
            
            # 장 초반이 아닌 경우 분봉 데이터 없으면 거부
            if not is_morning_session:
                # 거부 이력 기록
                cache_manager.set('momentum_data', rejection_key, {
                    'time': now.timestamp(),
                    'reason': '분봉 데이터 없음'
                })
                return False
            else:
                # 오전장에는 허용하지만 로그 추가
                logger.info(f"{stock_code}: 오전장 분봉 데이터 없음 - 허용")
                return True
                
        df_minute = stock_data['minute_ohlcv']

        # 최소 필요 분봉 데이터 수 확인 (더 엄격하게 변경)
        required_candles = 5 if is_early_morning else 12
        if len(df_minute) < required_candles:
            logger.info(f"{stock_code}: 분봉 데이터 부족 (현재: {len(df_minute)}개, 필요: {required_candles}개)")
            
            # 거부 이력 기록
            cache_manager.set('momentum_data', rejection_key, {
                'time': now.timestamp(),
                'reason': f'분봉 데이터 부족: {len(df_minute)}개'
            })
            return False

        # === 추가: 최신 캔들 상태 확인 ===
        # 가장 최근 캔들이 음봉인 경우 모멘텀 상실로 간주
        latest_candle = df_minute.iloc[-1]
        if latest_candle['close'] < latest_candle['open']:
            # 가장 최근 캔들이 음봉이고 거래량이 평균 이하인 경우
            recent_avg_volume = df_minute['volume'].tail(5).mean()
            if latest_candle['volume'] < recent_avg_volume:
                logger.info(f"{stock_name}({stock_code}): 최근 캔들 음봉 + 거래량 저조 - 모멘텀 상실")
                cache_manager.set('momentum_data', rejection_key, {
                    'time': now.timestamp(),
                    'reason': '최근 캔들 모멘텀 상실'
                })
                return False

        #---------------------------------------------------------------------------------
        # 1. 매수/매도 세력 판단 로직 개선 - 트렌드 지속성 확인 추가
        #---------------------------------------------------------------------------------
        # 최근 캔들과 추세 분석을 위한 범위 확장
        recent_candles = df_minute.tail(min(6, len(df_minute)))  # 최근 6개 봉 분석
        trend_candles = df_minute.tail(min(12, len(df_minute)))  # 추세 분석용 12개 봉
        
        # 1.1 개선된 매수 압력 계산 로직
        buying_pressure = []
        volume_trend_factor = 1.0  # 거래량 추세 가중치
        
        for _, candle in recent_candles.iterrows():
            range_total = candle['high'] - candle['low']
            if range_total == 0:  # 영봉 방지
                continue
                
            if candle['close'] >= candle['open']:  # 양봉
                # 윗꼬리 비율
                upper_shadow = (candle['high'] - candle['close']) / range_total
                # 몸통 비율
                body_ratio = (candle['close'] - candle['open']) / range_total
                # 매수세 강도: 몸통이 크고 윗꼬리가 짧을수록 강함
                strength = body_ratio * (1 - upper_shadow)
                
                # 거래량 추세 반영
                volume_trend_factor = 1 + (candle['volume'] / df_minute['volume'].mean() - 1) * 0.5
                strength *= volume_trend_factor
            else:  # 음봉
                # 아랫꼬리 비율
                lower_shadow = (candle['close'] - candle['low']) / range_total
                # 몸통 비율
                body_ratio = (candle['open'] - candle['close']) / range_total
                # 매수세 강도: 음봉이지만 아랫꼬리가 길수록 매수세 있음
                strength = lower_shadow - body_ratio

            buying_pressure.append(strength)

        avg_buying_pressure = sum(buying_pressure) / len(buying_pressure) if buying_pressure else 0
        
        # 1.2 트렌드 지속성 체크 - 연속적인 상승 흐름 확인
        # 가격 추세 분석
        closes = trend_candles['close'].values
        price_changes = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        positive_changes = sum(1 for change in price_changes if change > 0)
        positive_ratio = positive_changes / len(price_changes) if price_changes else 0
        
        # 최근 종가 상승 여부 체크 (추가된 부분)
        recent_uptrend = all(closes[i] <= closes[i+1] for i in range(len(closes)-3, len(closes)-1)) if len(closes) >= 3 else False
        
        # 정황상 단기 하락추세인지 확인 - 완화된 조건 적용(0.4->0.3)
        #is_declining = positive_ratio < 0.3 or (len(closes) >= 3 and closes[-1] < closes[-3])
        is_declining = positive_ratio < 0.25 or (len(closes) >= 3 and closes[-1] < closes[-3] * 0.98)  # 완화된 조건

        if is_declining:
            logger.info(f"{stock_name}({stock_code}): 단기 하락추세 감지 (양봉비율: {positive_ratio:.2f}, 최근상승: {recent_uptrend})")
            
            # 2. 트렌드 전환 포착 조건 추가 - 하락 추세에서 반등 신호 확인
            if check_trend_reversal(stock_data):
                logger.info(f"{stock_name}({stock_code}): 하락추세이나 반등 신호 감지! 예외 적용")
                is_declining = False  # 트렌드 반전 감지되면 하락추세 무시
                
            if is_declining:  # 여전히 하락추세로 판단되면
                # 거부 이력 기록
                cache_manager.set('momentum_data', rejection_key, {
                    'time': now.timestamp(),
                    'reason': '단기 하락추세'
                })
                return False

        # === 추가: 최근 3개 캔들 중 음봉 비율 분석 ===
        recent_3_candles = df_minute.tail(3)
        bearish_count = sum(1 for _, candle in recent_3_candles.iterrows() 
                          if candle['close'] < candle['open'])
        bearish_ratio = bearish_count / len(recent_3_candles)
        
        # 최근 3개 캔들 중 음봉이 2개 이상인 경우 모멘텀 상실로 간주
        if bearish_ratio >= 0.67:  # 3개 중 2개 이상이 음봉
            logger.info(f"{stock_name}({stock_code}): 최근 캔들 음봉 비율 높음 ({bearish_ratio:.2f}) - 모멘텀 상실")
            cache_manager.set('momentum_data', rejection_key, {
                'time': now.timestamp(),
                'reason': '최근 음봉 비율 높음'
            })
            return False
        
        #---------------------------------------------------------------------------------
        # 호가 및 RSI 로직은 기존 코드와 동일
        #---------------------------------------------------------------------------------
        orderbook = KisKR.GetOrderBook(stock_code)
        bid_strength = 0
        if orderbook:
            total_bid = orderbook['total_bid_rem']
            total_ask = orderbook['total_ask_rem']
            bid_strength = total_bid / (total_bid + total_ask) if (total_bid + total_ask) > 0 else 0

        volume_increasing = df_minute['volume'].iloc[-1] > df_minute['volume'].rolling(window=5).mean().iloc[-1] * 1.8
        price_rising = df_minute['close'].iloc[-1] > df_minute['close'].iloc[-2]

        # 추가: 두 번째 최근 봉도 확인
        if len(df_minute) >= 3:
            prev_price_rising = df_minute['close'].iloc[-2] > df_minute['close'].iloc[-3]
        else:
            prev_price_rising = True  # 데이터 부족 시 기본값

        # 거래량 증가와 함께 가격이 상승하면 매수세로 판단
        # volume_with_buying = volume_increasing and price_rising
        # 거래량 증가와 함께 가격이 상승하면 매수세로 판단 - 연속 상승 조건 추가
        volume_with_buying = volume_increasing and price_rising and prev_price_rising        

        # RSI 분석 코드 유지...
        try:
            rsi_period = 5 if is_early_morning else 9
            delta = df_minute['close'].diff()
            
            delta = delta.fillna(0)
            
            if len(df_minute) >= rsi_period + 1:
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                
                avg_gain = gain.rolling(window=rsi_period, min_periods=1).mean()
                avg_loss = loss.rolling(window=rsi_period, min_periods=1).mean()
                
                rs = avg_gain / avg_loss.replace(0, 0.00001)
                rsi = 100 - (100 / (1 + rs))
                
                current_rsi = rsi.iloc[-1]
                rsi_direction = rsi.iloc[-1] > rsi.iloc[-2] if len(rsi) >= 2 else True

                # 시간대별 RSI 범위 조정 (개선된 부분)
                if is_early_morning:
                    # 장초반에는 더 넓은 RSI 범위 허용
                    rsi_lower = MIN_EARLY_MORNING_BUY_RSI
                    rsi_upper = MAX_EARLY_MORNING_BUY_RSI
                else:
                    # 일반 시간대에는 약간 완화된 범위
                    rsi_lower = MIN_BUY_RSI
                    rsi_upper = MAX_BUY_RSI


                # 저점 상승 패턴이 감지되면 RSI 상한선 완화
                is_suitable_entry, pattern_info = detect_higher_lows_pattern(stock_code)
                
                if is_suitable_entry:
                    # 저점 상승 패턴이 감지되고 매수 적합성이 높으면 RSI 상한 완화
                    pattern_strength = pattern_info.get('pattern_strength', 0)
                    
                    # 패턴 강도에 따른 동적 RSI 상한 증가
                    if pattern_strength >= 8:  # 매우 강한 패턴
                        rsi_upper += 15        # RSI 상한 15 증가
                        logger.info(f"매우 강한 저점 상승 패턴 감지: RSI 상한 +15 (최대 {rsi_upper})")
                    elif pattern_strength >= 6: # 강한 패턴
                        rsi_upper += 10        # RSI 상한 10 증가
                        logger.info(f"강한 저점 상승 패턴 감지: RSI 상한 +10 (최대 {rsi_upper})")
                    elif pattern_strength >= 4: # 적당한 패턴
                        rsi_upper += 5         # RSI 상한 5 증가
                        logger.info(f"저점 상승 패턴 감지: RSI 상한 +5 (최대 {rsi_upper})")

                # 트렌드 반전 신호가 있는 경우에도 RSI 상한 일부 완화
                if check_trend_reversal(stock_data):
                    rsi_upper += 5  # RSI 상한 5 증가
                    logger.info(f"트렌드 반전 신호 감지: RSI 상한 +5 (최대 {rsi_upper})")

                # 이 부분은 기존 코드를 유지하되, 완화된 rsi_upper 값을 사용합니다
                rsi_signal = rsi_lower < current_rsi < rsi_upper

            else:
                rsi_signal = True  # 데이터 부족 시 True
                rsi_direction = True
                current_rsi = 50  # 기본값
        except Exception as e:
            logger.warning(f"RSI 계산 중 오류: {str(e)}")
            rsi_signal = True  # 오류 시 True
            rsi_direction = True
            current_rsi = 50  # 기본값
        
        # 양봉 비율 계산 및 로깅 - 완화된 조건 적용(0.5->0.4)
        logger.info(f"양봉 비율: {positive_ratio:.2f} (완화된 기준: >= 0.4)")
        
        # 최근 3개 캔들에서 양봉이 2개 이상인지 확인
        recent_3_candles = recent_candles.tail(min(3, len(recent_candles)))
        bullish_in_recent_3 = sum(1 for _, candle in recent_3_candles.iterrows() 
                                if candle['close'] > candle['open'])
        recent_3_bullish_ratio = bullish_in_recent_3 / len(recent_3_candles) if len(recent_3_candles) > 0 else 0
        
        logger.info(f"최근 3개 캔들 양봉 비율: {recent_3_bullish_ratio:.2f} (2/3 이상 = {recent_3_bullish_ratio >= 2/3})")
        
        # 매수 시그널 판단 - 시간대별 차별화 및 양봉비율 기준 완화
        if is_morning_session:
            # 오전 시간대 - RSI 비중 낮추고 다른 지표 중심으로 판단
            strong_buying = (
                (avg_buying_pressure > 0.25 or bid_strength > 0.33) and  # 요구 조건 약간 강화
                volume_with_buying and  # 거래량 증가 필수
                (positive_ratio >= 0.4 or recent_3_bullish_ratio >= 2/3)  # 완화된 양봉 비율 조건
            )
            
            # 오전 시간대 매우 강한 매수세 조건
            very_strong_buying = (
                avg_buying_pressure > 0.35 and
                bid_strength > 0.38 and
                volume_with_buying and
                (positive_ratio >= 0.5 or recent_3_bullish_ratio >= 2/3)  # 완화된 양봉 비율 조건
            )
        else:
            # 일반 시간대 - 모든 지표 포함하여 엄격하게 판단
            strong_buying = (
                (avg_buying_pressure > 0.25 or bid_strength > 0.33) and  # 요구 조건 약간 강화
                volume_with_buying and
                rsi_signal and  # RSI 조건 포함
                rsi_direction and  # RSI가 상승중이어야 함 (추가된 조건)
                (positive_ratio >= 0.4 or recent_3_bullish_ratio >= 2/3) and  # 완화된 양봉 비율 조건
                recent_uptrend      # 최근 상승 추세 확인 (추가된 조건)
            )
            
            # 일반 시간대 매우 강한 매수세 조건
            very_strong_buying = (
                avg_buying_pressure > 0.35 and
                bid_strength > 0.38 and
                volume_with_buying and
                rsi_signal and  # RSI 조건 추가
                rsi_direction and  # RSI가 상승중이어야 함 (추가된 조건)
                (positive_ratio >= 0.5 or recent_3_bullish_ratio >= 2/3) and  # 완화된 양봉 비율 조건
                recent_uptrend      # 최근 상승 추세 확인 (추가된 조건)
            )

        # 분석 결과 자세한 로깅 추가
        logger.info(f"\n{stock_name}({stock_code}) 모멘텀 상세:")
        logger.info(f"- 매수압력: {avg_buying_pressure:.2f} (기준: > 0.25)")
        logger.info(f"- 호가강도: {bid_strength:.2f} (기준: > 0.33)")
        logger.info(f"- 거래량증가: {volume_increasing} & 가격상승: {price_rising}")
        logger.info(f"- RSI: {current_rsi:.1f} (상승중: {rsi_direction})")
        logger.info(f"- 양봉비율: {positive_ratio:.2f} (완화된 기준: >= 0.4)")
        logger.info(f"- 최근3캔들 양봉비율: {recent_3_bullish_ratio:.2f} (기준: >= 2/3)")
        logger.info(f"- 최근상승추세: {recent_uptrend}")
        
        # 트렌드 반전 신호 확인 결과 로깅
        trend_reversal_detected = check_trend_reversal(stock_data)
        logger.info(f"- 트렌드 반전 신호: {trend_reversal_detected}")
        
        breakout_detected = check_breakout_pattern(stock_data)
        logger.info(f"- 돌파 패턴: {breakout_detected}")
        
        # 수정된 부분: 트렌드 반전이 감지된 경우에만 호가 조건 확인
        if trend_reversal_detected:
            # 호가 확인
            is_favorable, order_info = analyze_order_book(stock_code)
            if not is_favorable:
                logger.info(f"{stock_name}({stock_code}): 트렌드 반전 감지되었으나 호가 불리하여 제외")
                trend_reversal_detected = False  # 호가 불리하면 트렌드 반전 신호 무효화
                
            # RSI 확인 (과매수 상태 체크)
            if current_rsi > MAX_BUY_RSI:
                logger.info(f"{stock_name}({stock_code}): 트렌드 반전 감지되었으나 RSI 과매수({current_rsi:.1f}) 상태로 제외")
                trend_reversal_detected = False  # RSI 과매수면 트렌드 반전 신호 무효화

        # === RSI Divergence 체크 ===
        divergence_detected = check_rsi_divergence(stock_data)
        if divergence_detected:
            logger.info(f"{stock_name}({stock_code}): RSI Divergence 발생 — 매수 금지")
            return False

        # 모든 매수 시그널 조합
        buying_decision = strong_buying or very_strong_buying or trend_reversal_detected or breakout_detected

        if not buying_decision:
            # 거부 이력 기록 - 기존 캐시 매니저 사용
            cache_manager.set('momentum_data', rejection_key, {
                'time': now.timestamp(),
                'reason': '매수세 부족',
                'stock_name': stock_name,
                'session_type': 'morning' if is_morning_session else 'general'
            })            
        
        # 최종 판단 결과 로깅
        decision_text = "매수세 감지" if buying_decision else "매수세 부족"
        logger.info(f"{stock_name}({stock_code}): {decision_text} (강한매수: {strong_buying}, 매우강한매수: {very_strong_buying}, 트렌드반전: {trend_reversal_detected})")
        
        return buying_decision

    except Exception as e:
        # 장초반에는 에러 발생해도 True 반환
        if is_early_morning:
            logger.warning(f"장초반 모멘텀 체크 에러 - 완화된 기준 적용: {str(e)}")
            return True
        
        stock_code = stock_data.get('code', 'unknown')
        stock_name = KisKR.GetStockName(stock_code) if stock_code != 'unknown' else "알 수 없음"
        logger.error(f"{stock_name}({stock_code}) 단기 모멘텀 체크 중 에러: {str(e)}")
        
        # 에러 발생시 거부 이력 기록
        cache_manager = CacheManager.get_instance()
        rejection_key = cache_manager.create_key(stock_code, 'momentum_rejection')  # 일관성 있게 수정
        cache_manager.set('momentum_data', rejection_key, {
            'time': now.timestamp(),
            'reason': f'분석 오류: {str(e)}'
        })        
        
        return False



def check_fixed_take_profit(stock_data, position):
    try:
        entry_price = position['entry_price']
        current_price = stock_data['current_price']
        
        # 수수료 계산
        buy_fee = calculate_trading_fee(entry_price, position['amount'], is_buy=True)
        sell_fee = calculate_trading_fee(current_price, position['amount'], is_buy=False)
        total_fee = buy_fee + sell_fee
        
        # 수익률 계산 (수수료 반영)
        total_profit = (current_price - entry_price) * position['amount'] - total_fee
        profit_rate = (total_profit / (entry_price * position['amount'])) * 100
        
        # 최소 수익 기준 동적 조정
        min_profit_threshold = max(
            MIN_ATR_TAKE_PROFIT,  # 최소 고정 수익 보장
            (total_fee / (entry_price * position['amount'])) * 100 * 2  # 수수료의 2배 이상 수익
        )
        
        # ATR 기반 익절 기준 완화
        atr = stock_data.get('atr', 0)
        atr_profit_threshold = max(
            min_profit_threshold, 
            atr / entry_price * 100 * 2  # ATR 계수 완화
        )
        
        # 다양한 익절 조건
        take_profit_conditions = [
            profit_rate >= atr_profit_threshold,
            profit_rate >= 10.0  # 고정 10% 익절 기준
        ]
        
        if any(take_profit_conditions):
            msg = (
                f"📈 익절 조건 달성!\n"
                f"- 수수료 반영 수익률: {profit_rate:.2f}%\n"
                f"- 최소 수익 기준: {min_profit_threshold:.2f}%\n"
                f"- ATR 기반 임계값: {atr_profit_threshold:.2f}%\n"
                f"- 총 수수료: {total_fee:,.0f}원"
            )
            logger.info(msg)
            discord_alert.SendMessage(msg)
            
            return True, "Dynamic Take Profit"
        
        return False, None
    
    except Exception as e:
        logger.error(f"익절 조건 체크 중 에러: {str(e)}")
        return False, None


@cached('order_book_data')  # 기존 캐시 데코레이터 사용
def analyze_order_book(stock_code, depth=5, pattern_detected=False, pattern_strength=0):
    """
    개선된 호가 분석 - 호가 강도와 매수/매도 잔량의 동적 분석
    저점 상승 패턴 감지 시 조건 완화 로직 추가
    - 매수 잔량이 매우 많은 경우(높은 매수 압력)도 유리한 것으로 판단
    - 저점 상승 패턴 감지 시 훨씬 더 적극적인 완화 적용
    
    Args:
        stock_code (str): 종목코드
        depth (int): 호가 깊이
        pattern_detected (bool): 저점 상승 패턴 감지 여부
        pattern_strength (float): 패턴 강도 점수 (0-10)
        
    Returns:
        tuple: (is_favorable, order_info)
    """

    try:
        if not stock_code:
            return False, "종목코드 없음"
            
        order_book = KisKR.GetOrderBook(stock_code, depth)
        if not order_book:
            return False, "호가 데이터 없음"
        
        # 1. 호가 강도 계산 (기존 방식)
        total_bid_rem = order_book['total_bid_rem']
        total_ask_rem = order_book['total_ask_rem']
        order_strength = total_bid_rem / total_ask_rem if total_ask_rem > 0 else 0
        
        # 2. 호가 잔량 추세 분석
        cache_manager = CacheManager.get_instance()
        
        # 캐시 키 생성 (종목코드 기반)
        cache_key = f"{stock_code}_order_book_trend"
        
        # 이전 호가 데이터 로드
        prev_order_book_data = cache_manager.get('order_book_data', cache_key)
        
        # 호가 추세 정보 초기화
        order_book_trend = {
            'bid_trend': None,   # 매수 잔량 추세
            'ask_trend': None,   # 매도 잔량 추세
            'bid_volume_change': 0,
            'ask_volume_change': 0
        }
        
        # 이전 데이터가 있는 경우 변화율 계산
        if prev_order_book_data:
            bid_volume_change = (total_bid_rem - prev_order_book_data['total_bid_rem']) / prev_order_book_data['total_bid_rem'] * 100 if prev_order_book_data['total_bid_rem'] > 0 else 0
            ask_volume_change = (total_ask_rem - prev_order_book_data['total_ask_rem']) / prev_order_book_data['total_ask_rem'] * 100 if prev_order_book_data['total_ask_rem'] > 0 else 0
            
            order_book_trend['bid_volume_change'] = bid_volume_change
            order_book_trend['ask_volume_change'] = ask_volume_change
            
            # 추세 판단
            order_book_trend['bid_trend'] = 'increasing' if bid_volume_change > 0 else 'decreasing'
            order_book_trend['ask_trend'] = 'increasing' if ask_volume_change > 0 else 'decreasing'
        
        # 현재 호가 데이터 캐시에 저장
        cache_manager.set('order_book_data', cache_key, {
            'total_bid_rem': total_bid_rem,
            'total_ask_rem': total_ask_rem,
            'timestamp': time.time()
        })
        
        # 3. 상세 호가 분석
        top_bid_levels = [level['bid_volume'] for level in order_book['levels']]
        top_ask_levels = [level['ask_volume'] for level in order_book['levels']]
        
        # 4. 고급 호가 강도 계산
        bid_concentration = max(top_bid_levels) / sum(top_bid_levels) if sum(top_bid_levels) > 0 else 0
        ask_concentration = max(top_ask_levels) / sum(top_ask_levels) if sum(top_ask_levels) > 0 else 0
        
        # 5. 매도/매수 압력 지표
        selling_pressure = ask_concentration / (bid_concentration + 0.001)
        buying_pressure = bid_concentration / (ask_concentration + 0.001)
        
        # 현재 시간 확인
        is_morning_session = is_in_morning_session()
        is_early_morning = is_in_early_morning_session()
        is_very_early_morning = is_in_very_early_morning_session()  # 추가: 매우 이른 장초반 (9시-9시20분)
        is_power_hour = is_in_powerhour_session()
        
        # 시간대별 호가 강도 기준 조정 (더 완화된 기준 적용)
        if is_very_early_morning:  # 매우 이른 장초반 (9시-9시20분) - 가장 완화된 기준
            order_strength_lower = 0.25  # 0.3에서 더 완화 (75% 완화)
            order_strength_upper = 15.0  # 상한 더 증가 (특히 매우 이른 장초반 유동성이 낮을 수 있음)
            ask_concentration_threshold = 0.7  # 이른 시간대 더 관대한 기준 적용
        elif is_early_morning:
            # 장초반 조건 크게 완화 (하한 0.3 -> 0.25)
            order_strength_lower = 0.28  # 기존 0.3에서 완화
            order_strength_upper = 12.0  # 상한 증가 (10.0 -> 12.0)
            ask_concentration_threshold = 0.6  # 기준 완화 (0.5 -> 0.6)
        elif is_power_hour:
            # 파워아워 조건 완화 (하한 0.5 -> 0.45)
            order_strength_lower = 0.45  # 기존 0.5에서 완화
            order_strength_upper = 12.0  
            ask_concentration_threshold = 0.5 # 기준 유지
        else:
            # 일반 시간대 조건 완화 (하한 0.6 -> 0.55)
            order_strength_lower = 0.55  # 기존 0.6에서 완화
            order_strength_upper = 10.0  # 상한 유지
            ask_concentration_threshold = 0.45 # 기준 유지

        # === 저점 상승 패턴 감지 시 기준 완화 (기존보다 더 적극적으로) ===
        if pattern_detected:
            # 패턴 강도에 따른 차등 완화 (기존보다 더 적극적)
            if pattern_strength >= 7.0:  # 매우 강한 패턴
                order_strength_lower *= 0.4  # 60% 낮춤 (기존 50%보다 더 완화)
                order_strength_upper *= 1.5  # 50% 증가 (기존 40%보다 더 완화)
                logger.info(f"매우 강한 저점 패턴 감지: 호가 기준 60% 완화 ({order_strength_lower:.2f}) 및 상한 50% 증가")
            elif pattern_strength >= 5.0:  # 강한 패턴
                order_strength_lower *= 0.5  # 50% 낮춤 (기존 40%보다 더 완화)
                order_strength_upper *= 1.4  # 40% 증가 (기존 30%보다 더 완화)
                logger.info(f"강한 저점 패턴 감지: 호가 기준 50% 완화 ({order_strength_lower:.2f}) 및 상한 40% 증가")
            else:  # 일반 패턴
                order_strength_lower *= 0.6  # 40% 낮춤 (기존 30%보다 더 완화)
                order_strength_upper *= 1.3  # 30% 증가 (기존 20%보다 더 완화)
                logger.info(f"저점 패턴 감지: 호가 기준 40% 완화 ({order_strength_lower:.2f}) 및 상한 30% 증가")
                
            # 매수/매도 압력 기준도 완화
            buying_pressure_threshold = 0.2  # 기준 더 완화 (0.25 -> 0.2)
        else:
            buying_pressure_threshold = 0.35  # 패턴 없을 때 기준 완화 (0.4 -> 0.35)

        # 강한 모멘텀 점수 확인 - 점수가 높을수록 호가 조건 완화
        momentum_score = 0
        try:
            # 캐시에서 모멘텀 점수 조회 시도
            momentum_key = f"{stock_code}_momentum_score"
            momentum_data = cache_manager.get('momentum_data', momentum_key)
            if momentum_data:
                momentum_score = momentum_data.get('score', 0)
                
                # 모멘텀 점수가 높으면 더 적극적으로 완화 (기존보다 강화)
                if momentum_score >= 80:  # 매우 높은 모멘텀 (기존 75에서 상향)
                    order_strength_lower *= 0.5  # 50% 추가 완화 (기존 40%보다 완화)
                    logger.info(f"매우 높은 모멘텀 점수({momentum_score}) 감지: 호가 기준 추가 완화 ({order_strength_lower:.2f})")
                elif momentum_score >= 70:  # 높은 모멘텀 (기존 65에서 상향)
                    order_strength_lower *= 0.6  # 40% 추가 완화 (기존 30%보다 완화)
                    logger.info(f"높은 모멘텀 점수({momentum_score}) 감지: 호가 기준 추가 완화 ({order_strength_lower:.2f})")
                elif momentum_score >= 60:  # 중등도 모멘텀 (새로 추가)
                    order_strength_lower *= 0.7  # 30% 추가 완화
                    logger.info(f"중등도 모멘텀 점수({momentum_score}) 감지: 호가 기준 추가 완화 ({order_strength_lower:.2f})")
        except Exception as e:
            logger.info(f"모멘텀 점수 조회 중 오류: {str(e)}")

        # 최종 분석 결과
        result = {
            'order_strength': order_strength,
            'total_bid_rem': total_bid_rem,
            'total_ask_rem': total_ask_rem,
            'order_book_trend': order_book_trend,
            'bid_concentration': bid_concentration,
            'ask_concentration': ask_concentration,
            'selling_pressure': selling_pressure,
            'buying_pressure': buying_pressure,
            'top_bid_levels': top_bid_levels,
            'top_ask_levels': top_ask_levels,
            'momentum_score': momentum_score
        }

        # === 새로운 로직: 매수 압력이 매우 높은 경우 추가 검사 ===
        is_very_high_buying = order_strength > order_strength_upper
        high_buying_favorable = False
        
        if is_very_high_buying:
            # 매수 압력이 매우 높은 경우, 다른 지표 확인 (기준 완화)
            high_buying_favorable = (
                buying_pressure > 0.65 and  # 매수 집중도가 높고 (0.7 -> 0.65)
                not ask_concentration > 0.75  # 매도 집중도가 지나치게 높지 않음 (0.7 -> 0.75)
            )
            
            # 매수 압력이 매우 높아도 다른 조건이 양호하면 유리하다고 판단
            if high_buying_favorable:
                logger.info(f"매수 잔량 비율 매우 높음({order_strength:.2f}) - 특별 조건 적용: 매수 집중도({buying_pressure:.2f}) 우수")
                # 후술할 is_favorable 조건에 영향을 주기 위해 변수 조정
                is_very_high_buying = False  # 불리 판정 무효화
                result['very_high_buying_passed'] = True  # 추가 정보 표시
        
        # === 모멘텀 점수가 매우 높은 경우(80이상) 호가 완화 평가 (더 적극적으로) ===
        has_high_momentum = momentum_score >= 75  # 기존 80에서 75로 완화
        momentum_override = False
        
        if has_high_momentum:
            # 모멘텀이 매우 높은 경우, 최소한의 조건만 확인 (더 완화된 기준)
            momentum_override = (
                # 매수/매도 비율이 0.2 이상이면 통과 (기존 0.25에서 완화)
                order_strength >= 0.2 and
                # 매수 잔량이 기존 5000에서 4000으로 완화
                total_bid_rem > 4000
            )
            
            if momentum_override:
                logger.info(f"모멘텀 점수 매우 높음({momentum_score}) - 호가 조건 특별 완화 적용")
                result['momentum_override'] = True
        
        # 호가 유리성 판단 로직 - 패턴 감지 여부에 따라 조정 (더 적극적인 완화)
        if pattern_detected or has_high_momentum:
            # 저점 상승 패턴 감지 또는 고모멘텀 시 완화된 조건
            is_favorable = (
                momentum_override or  # 매우 높은 모멘텀 예외 (보다 적극적으로)
                (
                    (order_strength >= order_strength_lower and order_strength <= order_strength_upper) and
                    (
                        buying_pressure > buying_pressure_threshold or  # 완화된 기준 적용
                        buying_pressure > selling_pressure * 0.8  # 매수압력이 매도압력의 80% 이상이면 추가 (이전에는 없던 조건)
                    ) and
                    (
                        order_book_trend.get('bid_trend') == 'increasing' or 
                        (is_morning_session and order_book_trend.get('bid_trend') is not None) or
                        (is_early_morning)  # 장초반에는 추세 조건 생략 가능 (추가된 조건)
                    )
                )
            ) or (is_very_high_buying and high_buying_favorable)  # 추가: 매우 높은 매수세 + 양호한 다른 지표
        else:
            # 일반 조건 (기존 조건보다 추가적으로 완화)
            is_favorable = (
                (order_strength_lower <= order_strength <= order_strength_upper) and
                buying_pressure > buying_pressure_threshold and  # 완화된 기준 적용
                (
                    ask_concentration < ask_concentration_threshold or
                    buying_pressure > selling_pressure * 0.7  # 매수압력이 매도압력의 70% 이상이면 허용 (기존 80%에서 완화)
                ) and
                (
                    order_book_trend.get('bid_trend') == 'increasing' or 
                    (is_morning_session and order_book_trend.get('bid_trend') is not None) or
                    (is_early_morning and buying_pressure > 0.3)  # 장초반에는 추세 조건 대신 매수압력만 확인 (추가된 조건)
                )
            ) or (is_very_high_buying and high_buying_favorable)  # 추가: 매우 높은 매수세 + 양호한 다른 지표
        
        # === 추가: 매우 이른 장초반 (9시-9시20분) 특별 조건 ===
        if is_very_early_morning:
            # 이 시간대는 유동성이 매우 낮고 호가가 불안정할 수 있으므로 특별 조건 추가
            very_early_override = (
                # 매우 이른 시간대 추가 완화 조건
                (momentum_score >= 65 and order_strength >= 0.15) or  # 모멘텀 높을 때 더 완화된 기준
                (pattern_strength >= 6.0 and order_strength >= 0.18) or  # 강한 패턴이 있을 때 완화된 기준
                (total_bid_rem > 5000 and order_strength >= 0.2)  # 절대적 매수잔량이 많으면 완화된 기준
            )
            
            if very_early_override:
                logger.info(f"매우 이른 장초반 특별 조건 적용: 호가 조건 크게 완화")
                is_favorable = True
                result['very_early_override'] = True
        
        # 상세 로깅
        logger.info("\n=== 호가 분석 상세 ===")
        logger.info(f"매수/매도 강도: {order_strength:.2f} (기준: {order_strength_lower}~{order_strength_upper})")
        logger.info(f"매수 잔량 변화: {order_book_trend.get('bid_volume_change', 0):.2f}%")
        logger.info(f"매도 잔량 변화: {order_book_trend.get('ask_volume_change', 0):.2f}%")
        logger.info(f"매수 압력: {buying_pressure:.2f}")
        logger.info(f"매도 압력: {selling_pressure:.2f}")
        if is_very_high_buying:
            logger.info(f"매수 잔량 비율 매우 높음 - 추가 검사 결과: {'통과' if high_buying_favorable else '실패'}")
        if has_high_momentum:
            logger.info(f"모멘텀 점수 매우 높음({momentum_score}) - 특별 조건 적용: {'통과' if momentum_override else '실패'}")
        if is_very_early_morning and 'very_early_override' in result:
            logger.info(f"매우 이른 장초반 특별 조건 적용: {'통과'}")
        logger.info(f"최종 호가 유리성: {'긍정적' if is_favorable else '부정적'}")
        
        return is_favorable, result
        
    except Exception as e:
        logger.error(f"호가 분석 중 에러: {str(e)}")
        return False, str(e)


@cached('sector_info')
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
            rising_count / len(sector_prices) > 0.3 or  # 과반 상승--> 완화
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


@cached('stock_list')
def get_stock_list():
    """종목 리스트를 가져오는 함수"""
    try:
        logger.info("\n시가총액 상위 종목 필터링 중...")

        stock_list = KisKR.GetMarketCodeList(
            price_limit=MAX_STOCK_PRICE,
            min_market_cap=MIN_MARKET_CAP * 100000000,
            min_volume=MIN_DAILY_VOLUME,
            max_stocks=50,
            is_morning_session = is_in_morning_session(),
            is_early_morning = is_in_early_morning_session()
        )

        # stock_list가 None인 경우 체크
        if stock_list is None:
            logger.info("ERROR: 종목 리스트 조회 실패")
            return []
            

        return stock_list

    except Exception as e:
        logger.error(f"종목 리스트 조회 중 에러: {str(e)}")
        return []



def check_price_surge(stock_data, window_minutes=30):
    """
    급등 종목 체크 함수 - 개선된 버전 2.0
    - MACD 강도와 거래량 균형 개선: 둘 중 하나만 매우 강해도 통과 가능
    - 고점 초과 판단 로직 개선: 더 긴 기간으로 비교하는 로직 추가
    
    Args:
        stock_data (dict): 종목 데이터
        window_minutes (int): 확인할 시간 범위 (분 단위, 기본값: 30분)
        
    Returns:
        bool: True면 매수 가능, False면 매수 제한
    """
    try:
        stock_code = stock_data.get('code', '알 수 없음')
        logger.info(f"check_price_surge - 호출됨 ({stock_code})")
        logger.info(f"stock_data 키 목록: {list(stock_data.keys())}")

        # 분봉 데이터가 없으면 일봉으로 대체
        if 'minute_ohlcv' not in stock_data or stock_data['minute_ohlcv'] is None:
            logger.info(f"분봉 데이터 없음 - 급등 체크 건너뜀")
            return True
            
        minute_df = stock_data['minute_ohlcv']
        
        # 데이터 포인트 부족 시 체크 건너뜀
        if len(minute_df) < 5:
            logger.info(f"분봉 데이터 부족 ({len(minute_df)}개) - 급등 체크 건너뜀")
            return True
            
        # 현재 시간 기준 window_minutes 내의 데이터만 필터링
        now = datetime.now()
        cutoff_time = now - timedelta(minutes=window_minutes)
        
        # 인덱스가 datetime 타입인지 확인
        if isinstance(minute_df.index, pd.DatetimeIndex):
            recent_data = minute_df[minute_df.index >= cutoff_time]
            # 개선: 더 긴 기간의 데이터도 함께 로드
            longer_cutoff_time = now - timedelta(minutes=window_minutes*3)  # 3배 더 긴 기간
            longer_data = minute_df[minute_df.index >= longer_cutoff_time]
        else:
            # 인덱스가 datetime이 아니면 최근 N개 캔들만 사용
            candle_interval = 5  # 기본 5분봉 가정
            candle_count = max(3, int(window_minutes / candle_interval))
            recent_data = minute_df.tail(candle_count)
            # 개선: 더 긴 기간의 캔들도 가져오기
            longer_candle_count = candle_count * 3  # 3배 더 긴 기간
            longer_data = minute_df.tail(min(longer_candle_count, len(minute_df)))
            
        # 최저가와 최고가 찾기 (단기)
        if len(recent_data) > 0:
            low_price = recent_data['low'].min()
            high_price = recent_data['high'].max()
            current_price = stock_data['current_price']
            
            # 개선: 더 긴 기간의 최저가와 최고가도 계산
            if len(longer_data) > len(recent_data):
                longer_low_price = longer_data['low'].min()
                longer_high_price = longer_data['high'].max()
                # 더 낮은 저점과 더 높은 고점으로 업데이트
                if longer_low_price < low_price:
                    low_price = longer_low_price
                if longer_high_price > high_price:
                    high_price = longer_high_price
            
            # 상승률 계산
            surge_percent = ((high_price - low_price) / low_price) * 100
            
            # 현재가가 고점과 얼마나 가까운지 계산
            proximity_to_high = ((current_price - low_price) / (high_price - low_price)) * 100 if (high_price - low_price) > 0 else 0
            
            # 동적 급등 기준 설정 (기존과 동일)
            if current_price < 10000:  # 1만원 미만 종목
                base_surge_percent = 4.0
            elif current_price < 50000:  # 5만원 미만 종목
                base_surge_percent = 3.5
            else:  # 고가 종목
                base_surge_percent = 3.0
            
            # 시간대별 조정 (기존과 동일)
            is_early_morning_session = is_in_early_morning_session()
            is_power_hour = is_in_powerhour_session()

            if is_early_morning_session:
                time_factor = 1.2
            elif is_power_hour:
                time_factor = 0.9
            else:
                time_factor = 1.0
            
            # 변동성 조정 (기존과 동일)
            atr = stock_data.get('atr', 0)
            if atr > 0:
                atr_ratio = atr / current_price * 100
                volatility_factor = min(max(atr_ratio / 2, 0.8), 1.5)
            else:
                volatility_factor = 1.0
            
            # 최종 급등 기준 계산
            max_surge_percent = base_surge_percent * time_factor * volatility_factor
            
            # 로깅 추가
            logger.info(f"\n급등 확인:")
            logger.info(f"- 최근 {window_minutes}분 상승률: {surge_percent:.2f}%")
            logger.info(f"- 최저가 대비 현재 위치: {proximity_to_high:.1f}% (0%: 최저점, 100%: 최고점)")
            logger.info(f"- 급등 기준: {max_surge_percent:.2f}% (기본: {base_surge_percent:.1f}%, 시간: x{time_factor:.1f}, 변동성: x{volatility_factor:.1f})")
            
            # === 개선된 부분: 매수 제한 조건 ===
            # 1. 기존 급등 판단 (더 긴 기간 데이터 사용)
            is_surge = surge_percent > max_surge_percent and proximity_to_high > 75
            
            # 2. 개선: 더 긴 기간 기준 속성 계산
            if len(longer_data) > len(recent_data):
                # 더 긴 기간 내 위치 계산 (고점과의 거리)
                relative_position = ((current_price - longer_low_price) / (longer_high_price - longer_low_price)) * 100 if (longer_high_price - longer_low_price) > 0 else 0
                
                # 주의: 이 값은 100%를 초과할 수 있음 (단기 범위와 장기 범위가 다르기 때문)
                logger.info(f"- 긴 기간({window_minutes*3}분) 기준 현재 위치: {relative_position:.1f}%")
                
                # 고점 초과 판단 로직 개선: 더 긴 기간으로 비교 시 상대 위치가 70% 미만이면 급등 초기/중기로 간주
                is_early_stage_in_longer_term = relative_position < 70
            else:
                is_early_stage_in_longer_term = False
            
            # 3. 추가: 모멘텀 점수 확인 (기준 완화: 65 -> 60)
            momentum_score = 0
            if 'momentum_score' in stock_data:
                momentum_score = stock_data['momentum_score']
            
            high_momentum_override = momentum_score >= 60
            
            # 4. MACD 시그널 확인
            macd_signal_strength = 0
            if 'macd' in stock_data and 'macd_signal' in stock_data and 'prev_macd' in stock_data:
                macd = stock_data['macd']
                macd_signal = stock_data['macd_signal']
                prev_macd = stock_data['prev_macd']
                
                if macd > macd_signal and macd > prev_macd:
                    macd_diff = (macd - macd_signal) / abs(macd_signal) if macd_signal != 0 else 0
                    macd_change = (macd - prev_macd) / abs(prev_macd) if prev_macd != 0 else 0
                    
                    # MACD 시그널 강도 계산 (0-10 사이)
                    macd_signal_strength = min(10, (macd_diff * 100 + macd_change * 100) / 20)
                    logger.info(f"- MACD 시그널 강도: {macd_signal_strength:.1f}/10")
            
            # 5. 거래량 확인
            volume_quality = 0
            if 'volume' in stock_data and 'volume_ma5' in stock_data:
                volume_ratio = stock_data['volume'] / stock_data['volume_ma5']
                # 거래량 품질 점수 (0-10 사이)
                volume_quality = min(10, volume_ratio * 5)
                logger.info(f"- 거래량 품질: {volume_quality:.1f}/10 (평균 대비 {volume_ratio:.1f}배)")
            
            # 6. 캔들 패턴 분석 (연속 상승/하락 추세)
            recent_candles = recent_data.tail(min(5, len(recent_data)))
            bullish_candles = sum(1 for i in range(len(recent_candles)) 
                               if recent_candles.iloc[i]['close'] > recent_candles.iloc[i]['open'])
            bullish_ratio = bullish_candles / len(recent_candles)
            logger.info(f"- 최근 양봉 비율: {bullish_ratio:.2f} ({bullish_candles}/{len(recent_candles)})")
            
            # === 개선된 종합적인 매수 판단 로직 ===
            # 1. 모멘텀 점수가 높은 경우 (60 이상), 급등이라도 매수 허용
            
            # 2. 개선: MACD와 거래량 균형 - 둘 중 하나만 매우 강해도 충분
            # - MACD가 매우 강하면(8+) 거래량이 적어도(3+) OK
            # - 거래량이 매우 많으면(8+) MACD가 약해도(3+) OK
            strong_macd_acceptable_volume = macd_signal_strength >= 8 and volume_quality >= 3
            strong_volume_acceptable_macd = volume_quality >= 8 and macd_signal_strength >= 3
            
            # MACD 또는 거래량 중 하나라도 충분히 강하면 허용
            strong_signal_or_volume = strong_macd_acceptable_volume or strong_volume_acceptable_macd
            
            # 3. 급등이 시작된 초기 단계인 경우 (추가 완화된 조건)
            early_surge_stage = (
                surge_percent > max_surge_percent and  # 급등 상황이지만
                proximity_to_high < 60 and             # 아직 고점까지 거리가 있고
                bullish_ratio >= 0.7 and              # 최근 캔들 대부분이 양봉이며
                volume_quality >= 4                   # 거래량이 적정 수준 이상
            )
            
            # 4. 개선: 더 긴 기간 기준으로 아직 초기/중기 단계인 경우
            longer_term_early_stage = is_early_stage_in_longer_term and bullish_ratio >= 0.6
            
            # 최종 판단: 급등이지만 위의 조건 중 하나라도 만족하면 매수 허용
            if is_surge:
                # 기존 로직: 급등으로 매수 제한
                logger.info(f"⚠️ 급등 감지! 최근 {window_minutes}분 간 {surge_percent:.2f}% 상승, 현재 고점 대비 위치: {proximity_to_high:.1f}%")
                
                # 강한 모멘텀이 있는 경우 예외 처리
                if high_momentum_override:
                    logger.info(f"✅ 모멘텀 점수 높음 ({momentum_score}) - 급등에도 불구하고 매수 허용")
                    return True
                elif strong_signal_or_volume:
                    if strong_macd_acceptable_volume:
                        logger.info(f"✅ 매우 강한 MACD 신호({macd_signal_strength:.1f}/10)와 적절한 거래량({volume_quality:.1f}/10) - 급등에도 불구하고 매수 허용")
                    else:
                        logger.info(f"✅ 매우 높은 거래량({volume_quality:.1f}/10)과 적절한 MACD({macd_signal_strength:.1f}/10) - 급등에도 불구하고 매수 허용")
                    return True
                elif early_surge_stage:
                    logger.info(f"✅ 급등 초기 단계로 판단 - 매수 허용")
                    return True
                elif longer_term_early_stage:
                    logger.info(f"✅ 더 긴 기간({window_minutes*3}분) 기준으로 아직 초기/중기 단계 - 매수 허용")
                    return True
                else:
                    logger.info(f"❌ 급등으로 인한 매수 제한 - 예외 조건 없음")
                    return False
            
            return True  # 급등이 아닌 경우 매수 허용
                
        return True  # 데이터 부족 등의 경우 안전하게 매수 허용
            
    except Exception as e:
        logger.error(f"급등 체크 중 에러: {str(e)}")
        return True  # 에러 발생 시 기본적으로 매수 허용




# 전일 고모멘텀 종목 리스트 저장

def save_high_momentum_missed_stocks(stock_data, momentum_score, reason):
    try:
        # 기준 점수 이상인 종목만 저장
        if momentum_score < HIGH_MOMENTUM_SCORE_THRESHOLD:
            return
            
        stock_code = stock_data['code']
        stock_name = KisKR.GetStockName(stock_code)
        
        potential_stocks_file = f"HighMomentumStocks_{BOT_NAME}.json"
        
        # 기존 파일 읽기
        try:
            with open(potential_stocks_file, 'r') as f:
                potential_stocks = json.load(f)
        except:
            potential_stocks = {"stocks": []}
        
        # 날짜 정보 추가 (날짜별 저장)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # HIGH_MOMENTUM_STORE_DAYS일 이내 데이터만 유지하면서 새로운 종목 추가 가능
        potential_stocks['stocks'] = [
            stock for stock in potential_stocks['stocks'] 
            if stock.get('saved_time', today) >= (datetime.now() - timedelta(days=HIGH_MOMENTUM_STORE_DAYS)).strftime('%Y-%m-%d')
        ]
        
        # 이미 존재하는 종목인지 확인
        existing_codes = [stock["code"] for stock in potential_stocks["stocks"]]
        
        # 이미 존재하는 종목인지 확인
        if stock_code not in existing_codes:
            # 종목 정보 구성
            stock_info = {
                'code': stock_code,
                'name': stock_name,
                'price': stock_data['current_price'],
                'momentum_score': momentum_score,
                'rsi': stock_data['rsi'],
                'volume_ratio': stock_data['volume'] / stock_data['volume_ma5'] if stock_data['volume_ma5'] > 0 else 0,
                'macd': float(stock_data['macd']),
                'saved_time': today,
                'reason': reason  # 매수 제외 사유
            }
            
            # 리스트에 추가
            potential_stocks["stocks"].append(stock_info)
            
            # 파일 저장
            with open(potential_stocks_file, 'w') as f:
                json.dump(potential_stocks, f)
                
            logger.info(f"🌟 고모멘텀 잠재 종목 추가: {stock_name}({stock_code}) - 점수: {momentum_score}, 사유: {reason}")
        
    except Exception as e:
        logger.error(f"고모멘텀 종목 저장 중 에러: {str(e)}")



def load_high_momentum_stocks():
    """저장된 고모멘텀 종목 로드"""
    try:
        potential_stocks_file = f"HighMomentumStocks_{BOT_NAME}.json"
        
        # 파일 읽기 시도
        try:
            with open(potential_stocks_file, 'r') as f:
                high_momentum_stocks = json.load(f)
        except:
            return []
        
        logger.info(f"저장된 고모멘텀 종목 {len(high_momentum_stocks['stocks'])}개 로드")
        return high_momentum_stocks['stocks']
            
    except Exception as e:
        logger.error(f"고모멘텀 종목 로드 중 에러: {str(e)}")
        return []
    

# 이동평균선 관계 체크 추가
# 2. NaN 처리를 위한 이동평균선 계산 함수 개선
def check_ma_relationship(df):
    """
    이동평균선 관계 체크 - NaN 값 안전하게 처리
    """
    try:
        current_price = df['close'].iloc[-1]
        
        # 안전하게 이동평균선 계산
        ma5 = df['close'].rolling(window=5, min_periods=1).mean().iloc[-1]
        ma10 = df['close'].rolling(window=10, min_periods=1).mean().iloc[-1]
        ma20 = df['close'].rolling(window=20, min_periods=1).mean().iloc[-1]
        
        # NaN 값 처리
        ma5 = ma5 if not pd.isna(ma5) else current_price
        ma10 = ma10 if not pd.isna(ma10) else current_price
        ma20 = ma20 if not pd.isna(ma20) else current_price
        
        # 조건들
        price_above_ma5 = current_price > ma5
        price_above_ma10 = current_price > ma10
        ma5_above_ma10 = ma5 > ma10
        
        # 안전한 비율 계산
        ma5_ma10_diff_ratio = ((ma5 - ma10) / ma10 * 100) if ma10 > 0 else 0
        
        is_positive_trend = (
            price_above_ma5 and 
            price_above_ma10 and 
            ma5_above_ma10 and 
            ma5_ma10_diff_ratio > 0
        )
        
        logger.info(f"\n이동평균선 관계 분석:")
        logger.info(f"현재가: {current_price:,.0f}")
        logger.info(f"5일 이평선: {ma5:,.0f}")
        logger.info(f"10일 이평선: {ma10:,.0f}")
        logger.info(f"MA5/MA10 차이 비율: {ma5_ma10_diff_ratio:.2f}%")
        logger.info(f"추세 판단: {'긍정적' if is_positive_trend else '부정적'}")
        
        return is_positive_trend
    
    except Exception as e:
        logger.error(f"이동평균선 관계 분석 중 오류: {str(e)}")
        return False



# 3. 고점 근접도 함수 개선 (로그 명확화)
def check_improved_high_proximity(stock_data, momentum_score):
    """
    개선된 고점 근접도 판단 함수
    - 모멘텀 점수에 따른 동적 임계값 조정
    - 상승 추세 강도 기반 차등 적용
    - ATR 기반 변동성 반영
    - 시간대별 차등 조건 적용
    """
    try:
        current_price = stock_data['current_price']
        df = stock_data['ohlcv']
        
        # 현재 시간 확인
        now = datetime.now()
        current_hour = now.hour
        is_afternoon = current_hour >= 13
        is_late_market = current_hour >= 14
        
        # 추세 판단 - 이동평균선 관계와 상승 강도 확인
        ma5 = df['close'].rolling(window=5, min_periods=1).mean().iloc[-1]
        ma10 = df['close'].rolling(window=10, min_periods=1).mean().iloc[-1]
        ma20 = df['close'].rolling(window=20, min_periods=1).mean().iloc[-1]
        
        # NaN 처리
        ma5 = ma5 if not pd.isna(ma5) else current_price
        ma10 = ma10 if not pd.isna(ma10) else current_price
        ma20 = ma20 if not pd.isna(ma20) else current_price
        
        # 상승 추세 강도 점수 계산 (0-3점)
        trend_strength = 0
        
        # 1. 단기 이동평균선 배열 (현재가 > MA5 > MA10 > MA20)
        if current_price > ma5 and ma5 > ma10 and ma10 > ma20:
            trend_strength += 1
        
        # 2. 이동평균선 간격 분석 (MA5와 MA10 사이 간격이 넓을수록 강한 추세)
        ma5_ma10_gap_ratio = ((ma5 - ma10) / ma10 * 100) if ma10 > 0 else 0
        if ma5_ma10_gap_ratio > 1.0:
            trend_strength += 1
        
        # 3. 최근 가격 모멘텀 (최근 3일간 상승 비율)
        if len(df) >= 3:
            recent_price_changes = [
                (df['close'].iloc[-i] - df['close'].iloc[-i-1]) / df['close'].iloc[-i-1]
                for i in range(1, min(4, len(df)))
            ]
            positive_changes = sum(1 for change in recent_price_changes if change > 0)
            if positive_changes >= 2:  # 최근 3일 중 2일 이상 상승
                trend_strength += 1
        
        # 상승 추세 여부 최종 판단 (2점 이상이면 강한 추세로 판단)
        is_strong_uptrend = trend_strength >= 2
        is_uptrend = trend_strength >= 1  # 약한 추세라도 상승 추세로 인정
        
        # 변동성 기반 동적 조정
        atr = stock_data.get('atr', 0)
        price_volatility = atr / current_price * 100 if current_price > 0 else 0
        
        # 분봉/일봉 사용 결정
        use_minute_data = True
        if 'minute_ohlcv' not in stock_data or stock_data['minute_ohlcv'] is None:
            use_minute_data = False
        
        analysis_df = stock_data['minute_ohlcv'] if use_minute_data else df
            
        # 최근 N일/분 데이터로 고점 계산 (제한된 기간 사용)
        if use_minute_data:
            # 분봉의 경우 최근 60개 봉만 사용 (5분봉 기준 약 5시간)
            recent_data = analysis_df.tail(min(60, len(analysis_df)))
        else:
            # 일봉의 경우 최근 5일만 사용
            recent_data = analysis_df.tail(min(5, len(analysis_df)))
            
        daily_high = recent_data['high'].max()
        
        # 기본 고점 근접도 계산
        high_price_ratio = (daily_high - current_price) / current_price * 100
        
        # 로깅용 원래 임계값 저장
        original_threshold = 2.0  # 기본 고점 임계값
        
        # ====== 개선: 모멘텀 점수 기반 임계값 조정 강화 ======
        if momentum_score >= 85:  # 최상위 모멘텀 (85+)
            score_factor = 2.0    # 임계값 2배 완화
        elif momentum_score >= 80:  # 매우 높은 모멘텀 (80-84)
            score_factor = 1.8    # 임계값 1.8배 완화
        elif momentum_score >= 75:  # 높은 모멘텀 (75-79)
            score_factor = 1.5    # 임계값 1.5배 완화
        elif momentum_score >= 70:  # 중상위 모멘텀 (70-74)
            score_factor = 1.3    # 임계값 1.3배 완화
        else:                      # 일반 모멘텀 (70 미만)
            score_factor = 1.0    # 기존 임계값 유지
            
        # ====== 개선: 상승 추세 강도에 따른 임계값 조정 강화 ======
        if is_strong_uptrend:    # 강한 상승 추세
            trend_factor = 1.5   # 임계값 1.5배 완화
        elif is_uptrend:         # 일반 상승 추세
            trend_factor = 1.2   # 임계값 1.2배 완화
        else:                    # 상승 추세 아님
            trend_factor = 1.0   # 기존 임계값 유지
            
        # 시간대별 임계값 조정
        is_afternoon_session = is_in_afternoon_session()
        is_power_hour = is_in_powerhour_session()  # 파워아워

        if is_power_hour:  # 14시 이후
            time_factor = 1.8  # 14시 이후 80% 추가 완화
        elif is_afternoon_session:  # 오후 시간대
            time_factor = 1.5  # 오후 시간대 50% 완화
        else:
            time_factor = 1.0
            
        # 변동성 기반 임계값 조정
        volatility_factor = min(max(1.0, price_volatility / 2), 1.5)  # 1.0~1.5 범위로 제한
        
        # 최종 임계값 계산
        high_threshold = original_threshold * score_factor * time_factor * trend_factor * volatility_factor
        
        # 상세 로깅 추가
        logger.info(f"\n개선된 고점 근접도 분석:")
        logger.info(f"- 현재가: {current_price:,.0f}원")
        logger.info(f"- 최근 고점: {daily_high:,.0f}원")
        logger.info(f"- 고점 근접도: {high_price_ratio:.2f}%")
        logger.info(f"- 기본 임계값: {original_threshold:.1f}%")
        logger.info(f"- 모멘텀 계수(x{score_factor:.1f}), 시간대 계수(x{time_factor:.1f})")
        logger.info(f"- 추세 계수(x{trend_factor:.1f}), 변동성 계수(x{volatility_factor:.1f})")
        logger.info(f"- 상승 추세 강도: {trend_strength}/3점 ({'강한 추세' if is_strong_uptrend else '약한 추세' if is_uptrend else '추세 없음'})")
        logger.info(f"- 최종 임계값: {high_threshold:.1f}%")
        
        # ====== 개선: 예외 조건 강화 - 모멘텀 + 추세 + 시간대 조합에 따른 오버라이드 ======
        # 특정 조건에서는 고점 근접도를 무시하고 강제 통과시키는 로직
        override_condition = (
            (momentum_score >= 80 and is_strong_uptrend and is_afternoon_session) or  # 최상위 모멘텀 + 강한 추세 + 오후장
            (momentum_score >= 85 and is_uptrend) or                                  # 최고 모멘텀 + 일반 추세
            (momentum_score >= 80 and is_power_hour and is_uptrend)                   # 상위 모멘텀 + 파워아워 + 일반 추세
        )
        
        # 오버라이드 조건 충족 시 무조건 통과, 단 극단적 근접도(10% 이상)는 예외
        if override_condition and high_price_ratio < 10:
            logger.info(f"✅ 고점 근접도 조건 오버라이드: 모멘텀({momentum_score}) + {'강한' if is_strong_uptrend else '일반'} 추세 + {'파워아워' if is_power_hour else '오후장' if is_afternoon_session else '일반'} 시간대")
            return True
            
        # 고점 근접도 조건 체크
        if high_price_ratio <= high_threshold:
            logger.info(f"✅ 고점 근접도 조건 충족: {high_price_ratio:.2f}% <= {high_threshold:.2f}%")
            return True
        else:
            logger.info(f"⚠️ 고점 근접도 조건 불충족: 고점과의 차이 {high_price_ratio:.2f}% > 기준 {high_threshold:.2f}% (차이: +{high_price_ratio - high_threshold:.2f}%)")
            return False
            
    except Exception as e:
        logger.error(f"개선된 고점 근접도 확인 중 에러: {str(e)}")
        # 에러 발생 시 기본 값으로 진행
        return False
    

# 5. 단기 상승률 모멘텀 우회 조건 개선 함수
def check_momentum_based_rise_override(stock_data, momentum_score):
    """
    모멘텀 점수가 높지만 단기 상승률이 낮은 상황에서도 매수할 수 있는 
    추가 판단 로직을 제공하는 함수 - 오류 수정 및 명확한 반환값
    """
    try:
        # 기본 기준: 모멘텀 점수가 70 이상인 경우에만 적용
        if momentum_score < 70:
            return False, "모멘텀 점수 부족 (70 미만)"
            
        # 현재 시간 확인 (오후 시간대에 더 유리한 조건 적용)
        is_afternoon_session = is_in_afternoon_session()
        is_power_hour = is_in_powerhour_session()
        
        # 차트 패턴 분석 (캔들, 거래량)
        df = stock_data['ohlcv']
        
        # 1. 지지선 반등 패턴 확인 - 최근 5일 저점에서 반등
        recent_low = df['low'].tail(5).min()
        current_price = stock_data['current_price']
        low_bounce_ratio = (current_price - recent_low) / recent_low * 100
        
        # 2. 이동평균선 분석 - 최근 이동평균선 상향 돌파 확인
        ma5 = df['close'].rolling(window=5, min_periods=1).mean().iloc[-1]
        ma10 = df['close'].rolling(window=10, min_periods=1).mean().iloc[-1]
        ma20 = df['close'].rolling(window=20, min_periods=1).mean().iloc[-1]
        
        # NaN 방지
        ma5 = ma5 if not pd.isna(ma5) else current_price
        ma10 = ma10 if not pd.isna(ma10) else current_price
        ma20 = ma20 if not pd.isna(ma20) else current_price
        
        # 이전 ma5 값 안전하게 얻기
        prev_ma5 = current_price  # 기본값
        if len(df) >= 6:
            prev_close_values = df['close'].iloc[-6:-1]
            if len(prev_close_values) > 0:
                prev_ma5 = prev_close_values.mean()
        
        ma_rising = ma5 > prev_ma5
        
        ma_uptrend = (
            (current_price > ma5 and ma5 > ma10) or  # 상승 추세
            (current_price > ma5 and ma_rising)  # 5일선 상향 중
        )
        
        # 3. MACD 분석 - 매수 신호 확인
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # 안전한 비교
        macd_current = macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0
        macd_prev = macd.iloc[-2] if len(macd) > 1 and not pd.isna(macd.iloc[-2]) else 0
        signal_current = signal.iloc[-1] if not pd.isna(signal.iloc[-1]) else 0
        signal_prev = signal.iloc[-2] if len(signal) > 1 and not pd.isna(signal.iloc[-2]) else 0
        
        macd_cross_up = (
            macd_current > signal_current and  # 현재 MACD > 시그널
            macd_prev <= signal_prev  # 직전에는 MACD <= 시그널
        )
        
        # 4. 거래량 패턴 분석
        volume_ratio = stock_data['volume'] / stock_data['volume_ma5'] if stock_data['volume_ma5'] > 0 else 0
        increasing_volume = (
            volume_ratio > 1.2 and  # 평균보다 20% 이상 거래량
            stock_data['volume'] > stock_data['prev_volume']  # 전일보다 거래량 증가
        )
        
        # 5. 매수/매도 잔량 분석
        order_book = KisKR.GetOrderBook(stock_data['code'])
        bid_ask_ratio = 0
        if order_book:
            total_bid = order_book['total_bid_rem']
            total_ask = order_book['total_ask_rem']
            if total_ask > 0:
                bid_ask_ratio = total_bid / total_ask
        
        buying_pressure = bid_ask_ratio > 1.0  # 매수 잔량이 매도 잔량보다 많음
        
        # 조건 종합 - 여러 지표 중에서 일정 개수 이상 충족하면 단기 상승률 조건 우회
        override_conditions = [
            low_bounce_ratio > 1.0,  # 최근 저점 대비 1% 이상 반등
            ma_uptrend,              # 이동평균선 상향 돌파
            macd_cross_up,           # MACD 골든크로스
            increasing_volume,       # 거래량 증가
            buying_pressure,         # 호가창 매수세 강함
            momentum_score >= 75     # 모멘텀 점수가 매우 높음
        ]
        
        # 시간대별 필요 조건 수 차등 적용
        if is_power_hour:  # 파워아워(14시 이후)
            required_conditions = 2  # 2개 이상 조건 충족 시 허용
        elif is_afternoon_session:  # 오후 시간대
            required_conditions = 3  # 3개 이상 조건 충족 시 허용
        else:
            required_conditions = 4  # 기본 4개 이상 조건 충족 시 허용
        
        # True 값 개수 계산
        conditions_met = sum(1 for condition in override_conditions if condition)
        
        # 상세 로깅
        logger.info(f"\n모멘텀 기반 단기 상승률 우회 조건 분석:")
        logger.info(f"- 모멘텀 점수: {momentum_score}")
        logger.info(f"- 저점 반등률: {low_bounce_ratio:.2f}% (기준: >1.0%)")
        logger.info(f"- 이동평균선 상향: {ma_uptrend}")
        logger.info(f"- MACD 골든크로스: {macd_cross_up}")
        logger.info(f"- 거래량 증가: {increasing_volume} ({volume_ratio:.2f}배)")
        logger.info(f"- 호가 매수세: {buying_pressure} (비율: {bid_ask_ratio:.2f})")
        logger.info(f"- 충족 조건: {conditions_met}/{len(override_conditions)} (필요: {required_conditions})")
        
        # 충족한 조건 수가 필요 조건 수 이상이면 우회 허용
        if conditions_met >= required_conditions:
            return True, f"모멘텀 점수({momentum_score}) + {conditions_met}개 매수 신호"
        
        return False, f"조건 부족 ({conditions_met}/{required_conditions})"
    
    except Exception as e:
        logger.error(f"모멘텀 기반 단기 상승률 우회 분석 중 에러: {str(e)}")
        return False, f"분석 오류: {str(e)}"



def find_consolidation_pattern(stock_data):
    """
    박스권 횡보 후 돌파 가능성이 있는 종목 확인 함수 - 오류 수정 버전
    
    Args:
        stock_data (dict): 종목 데이터
        
    Returns:
        tuple: (is_consolidation, info)
    """
    try:
        df = stock_data['ohlcv']
        
        # 최근 10일 데이터 추출
        recent_df = df.tail(10)
        
        # 데이터 충분한지 확인
        if len(recent_df) < 5:
            return False, {"error": "데이터 부족"}
        
        # 1. 가격 변동성 체크 (박스권 확인)
        price_range = (recent_df['high'].max() - recent_df['low'].min()) / recent_df['low'].min() * 100
        
        # 수정된 부분: pct_change 계산을 안전하게 수행
        daily_changes = []
        for i in range(1, len(recent_df)):
            prev_close = recent_df['close'].iloc[i-1]
            curr_close = recent_df['close'].iloc[i]
            if prev_close > 0:
                change = abs((curr_close - prev_close) / prev_close * 100)
                daily_changes.append(change)
                
        avg_daily_change = sum(daily_changes) / len(daily_changes) if daily_changes else 0
        
        # 2. 거래량 감소 후 증가 패턴 확인
        recent_volume = recent_df['volume'].values
        volume_trend = []
        for i in range(1, len(recent_volume)):
            if recent_volume[i-1] > 0:
                volume_trend.append(1 if recent_volume[i] > recent_volume[i-1] else -1)
        
        recent_volume_increase = sum(volume_trend[-3:]) > 0 if len(volume_trend) >= 3 else False
        
        # 3. 최근 돌파 가능성 확인
        if len(recent_df) >= 6:
            last_3_days = recent_df.tail(3)
            earlier_days = recent_df.iloc[:-3]
            
            earlier_mean_price = earlier_days['close'].mean() if len(earlier_days) > 0 else 0
            earlier_mean_volume = earlier_days['volume'].mean() if len(earlier_days) > 0 else 0
            
            recent_breakout = (
                earlier_mean_price > 0 and
                earlier_mean_volume > 0 and
                last_3_days['close'].iloc[-1] > earlier_mean_price and
                last_3_days['volume'].iloc[-1] > earlier_mean_volume
            )
        else:
            recent_breakout = False
        
        # 박스권 판단 기준: 변동성 낮음 + 최근 거래량 변화 + 돌파 가능성
        is_consolidation = (
            price_range < 8.0 and  # 8% 이내 변동
            avg_daily_change < 2.0 and  # 평균 변동 2% 미만
            recent_volume_increase and  # 최근 거래량 증가
            recent_breakout  # 최근 가격/거래량 돌파
        )
        
        info = {
            'price_range': price_range,
            'avg_daily_change': avg_daily_change,
            'recent_volume_increase': recent_volume_increase,
            'recent_breakout': recent_breakout
        }
        
        if is_consolidation:
            logger.info(f"\n박스권 돌파 패턴 감지:")
            logger.info(f"- 가격 변동폭: {price_range:.2f}% (10일)")
            logger.info(f"- 평균 일변동: {avg_daily_change:.2f}%")
            logger.info(f"- 최근 거래량 증가: {recent_volume_increase}")
            logger.info(f"- 박스권 돌파 징후: {recent_breakout}")
        
        return is_consolidation, info
    
    except Exception as e:
        logger.error(f"박스권 패턴 분석 중 에러: {str(e)}")
        return False, {"error": str(e)}

def enhanced_entry_timing(stock_data):
    """상승 초기 단계를 더 정확하게 감지하는 개선된 함수"""
    df = stock_data['minute_ohlcv']
    if df is None or len(df) < 20:  # 충분한 데이터 확보
        return False
    
    # == 1. 저점 돌파 패턴 확인 ==
    # 최근 10~20분 내 저점 형성 후 돌파 확인
    recent_df = df.tail(20)
    lowest_idx = recent_df['low'].idxmin()
    lowest_point = recent_df.loc[lowest_idx]
    
    current_idx = recent_df.index[-1]
    current_candle = recent_df.iloc[-1]
    
    # 저점 형성 후 경과된 봉 수 계산
    candles_since_low = len(recent_df.loc[lowest_idx:current_idx])
    
    # 저점 대비 상승률 계산
    rise_from_low = (current_candle['close'] - lowest_point['low']) / lowest_point['low'] * 100
    
    # 적절한 저점 돌파 조건 (3~8개 봉 내에 저점 형성 & 1~3% 상승)
    valid_low_breakout = (
        3 <= candles_since_low <= 8 and
        1.0 <= rise_from_low <= 3.0
    )
    
    # == 2. 거래량 분석 - 상승 초기에 거래량 증가 패턴 ==
    # 저점 전/후 거래량 비교
    pre_low_volume = recent_df.loc[:lowest_idx]['volume'].mean()
    post_low_volume = recent_df.loc[lowest_idx:]['volume'].mean()
    volume_increase_ratio = post_low_volume / pre_low_volume if pre_low_volume > 0 else 0
    
    significant_volume_increase = volume_increase_ratio > 1.3  # 30% 이상 거래량 증가
    
    # == 3. 이동평균선 골든크로스 초기 단계 확인 ==
    ma5 = df['close'].rolling(window=5).mean()
    ma10 = df['close'].rolling(window=10).mean()
    
    # 최근 MA5가 상승 중이고, MA10과의 거리가 가까워지는 중
    ma5_increasing = ma5.iloc[-1] > ma5.iloc[-3]
    ma_converging = (ma5.iloc[-1] - ma10.iloc[-1]) > (ma5.iloc[-3] - ma10.iloc[-3])
    
    # 추가: 직전 봉들의 상승 패턴 확인
    recent_price_action = recent_df.tail(4)
    higher_lows = all(recent_price_action['low'].iloc[i] >= recent_price_action['low'].iloc[i-1] 
                     for i in range(1, len(recent_price_action)))
    
    higher_highs = all(recent_price_action['high'].iloc[i] >= recent_price_action['high'].iloc[i-1] 
                      for i in range(1, len(recent_price_action)))
    
    # 결합 조건 - 여러 지표 중 충분한 수의 조건이 만족되면 매수 시그널
    uptrend_beginning_signals = [
        valid_low_breakout,
        significant_volume_increase,
        ma5_increasing,
        ma_converging,
        higher_lows,
        higher_highs
    ]
    
    # 6개 신호 중 4개 이상 만족하면 상승 초기 단계로 판단
    signals_count = sum(1 for signal in uptrend_beginning_signals if signal)
    
    return signals_count >= 4


# 개선된 코드를 적용할 부분 (check_buy_conditions 함수 수정)
def check_buy_conditions(stock_data):
    """단타 전략을 위한 매수 조건 확인 - 개선된 로직 흐름"""
    try:
        # stock_code를 stock_data에서 가져옴
        stock_code = stock_data['code']
        current_price = stock_data['current_price']
        rsi = stock_data['rsi']
        stock_name = KisKR.GetStockName(stock_code)

        # === 여기에 새로운 코드 추가 (기존 코드 실행 전) ===
        # 저점 상승 패턴 체크
        is_suitable_entry, pattern_info = detect_higher_lows_pattern(stock_code)
        
        # 패턴이 감지되고 매수 시점이 적합하면 다른 조건들을 우회
        if is_suitable_entry:
            pattern_strength = pattern_info.get('pattern_strength', 0)
            timing_score = pattern_info.get('timing_score', 0)
            buy_timing = pattern_info.get('buy_timing', 'none')
            logger.info(f"\n✨ {stock_name}({stock_code}) - 저점 상승 패턴 매수 시점 감지!")
            logger.info(f"- 패턴 강도: {pattern_strength:.1f}/10")
            logger.info(f"- 매수 시점: {buy_timing} (점수: {timing_score:.1f}/10)")

        # 패턴이 감지됐으나 적합성이 부족한 경우도 패턴 강도가 충분하면 추가 검증
        if not is_suitable_entry and pattern_info.get('pattern_strength', 0) >= 4.0:
            # pattern_strength를 안전하게 가져오도록 수정
            pattern_strength = pattern_info.get('pattern_strength', 0)            
            logger.info(f"{stock_name}({stock_code}) - 저점 상승 패턴 감지됨(적합성 부족), 패턴 강도({pattern_info.get('pattern_strength', 0):.1f}) 기반으로 추가 검증")
            # 패턴 강도가 좋으면 적합성 높게 재평가
            if pattern_info.get('pattern_strength', 0) >= 5.0:
                is_suitable_entry = True
                logger.info(f"{stock_name}({stock_code}) - 패턴 강도 우수로 매수 적합성 인정")

            
            # 최소한의 안전 조건만 확인
            
            # 1. 호가 확인 - 패턴 감지 정보 전달
            is_favorable, order_info = analyze_order_book(
                stock_code, 
                depth=5, 
                pattern_detected=True, 
                pattern_strength=pattern_strength
            )

            if not is_favorable:
                logger.info(f"{stock_name}({stock_code}) - 저점 상승 패턴 감지됐으나 호가 불리로 제외")
                return False
                
            # 2. 거래량 최소 확인
            if stock_data['volume'] <= stock_data['volume_ma5'] * 0.5:
                logger.info(f"{stock_name}({stock_code}) - 저점 상승 패턴 감지됐으나 거래량 부족으로 제외")
                return False
                
            # 3. 현재 캔들이 양봉인지 확인
            if 'minute_ohlcv' in stock_data and stock_data['minute_ohlcv'] is not None:
                minute_df = stock_data['minute_ohlcv']
                if len(minute_df) >= 1:
                    current_candle_bullish = minute_df['close'].iloc[-1] > minute_df['open'].iloc[-1]
                    if not current_candle_bullish:
                        logger.info(f"{stock_name}({stock_code}) - 저점 상승 패턴 감지됐으나 현재 음봉이므로 제외")
                        return False
            
            # 4. RSI 극단치는 여전히 회피 (과매수/과매도 방지)
            is_early_morning = is_in_early_morning_session()
            if (is_early_morning and (rsi > 85 or rsi < 25)) or (not is_early_morning and (rsi > 80 or rsi < 30)):
                logger.info(f"{stock_name}({stock_code}) - 저점 상승 패턴 감지됐으나 RSI 극단치({rsi:.1f})로 제외")
                return False
            
            # 주요 조건 통과: 저점 상승 패턴 + 최소 안전 조건
            logger.info(f"✨ {stock_name}({stock_code}) - 저점 상승 패턴 전략으로 매수 조건 통과!")
            logger.info(f"- 패턴 강도: {pattern_info.get('pattern_strength', 0):.1f}/10")
            logger.info(f"- 지역 저점 수: {pattern_info.get('local_lows_count', 0)}개")
            logger.info(f"- 마지막 저점 이후 상승률: {pattern_info.get('rise_after_last_low', 0):.2f}%")
            
            return True

        # 급등 체크 - 최근 30분 내 3% 이상 상승한 종목이면 매수 보류
        if not check_price_surge(stock_data, window_minutes=30):
            logger.info(f"{stock_name}({stock_code}) - 단기 급등으로 매수 보류")
            
            # 모멘텀 점수 확인 및 고점 근접도 조건 동적 조정
            passed_momentum, momentum_score = check_momentum_conditions(stock_data, return_score=True)
            
            # 모멘텀 점수가 높은 경우 저장
            if momentum_score >= HIGH_MOMENTUM_SCORE_THRESHOLD:
                save_high_momentum_missed_stocks(stock_data, momentum_score, "단기 급등")
            return False
        
        # 현재 시간 확인
        is_morning_session = is_in_morning_session()
        is_early_morning = is_in_early_morning_session()
        
        # 모멘텀 점수 확인
        passed_momentum, momentum_score = check_momentum_conditions(stock_data, return_score=True)
        # if not passed_momentum:
        #     logger.info(f"{stock_name}({stock_code}) - 모멘텀 점수 부족으로 제외 (점수: {momentum_score})")
        #     return False
        if not passed_momentum:
            # 오전장에는 모멘텀 부족 시에도 추가 체크 진행
            if is_morning_session and momentum_score >= 50:  # 모멘텀 최소 기준 완화
                logger.info(f"{stock_name}({stock_code}) - 오전장 모멘텀 완화 적용 (점수: {momentum_score})")
                
                # 오전장 추가 확인 - 최근 상승 확인
                if check_continuous_uptrend(stock_code, min_candles=2):  # 2개로 완화
                    logger.info(f"{stock_name}({stock_code}) - 오전장 연속 상승 패턴 감지로 모멘텀 부족해도 통과")
                    # 통과 처리 후 계속 진행
                else:
                    logger.info(f"{stock_name}({stock_code}) - 오전장이지만 추가 패턴도 부족하여 제외")
                    return False
            else:
                logger.info(f"{stock_name}({stock_code}) - 모멘텀 점수 부족으로 제외 (점수: {momentum_score})")
                return False
       
        logger.info(f"{stock_name}({stock_code}) - 모멘텀 점수 통과: {momentum_score}/100")

        # 고점 근접도 체크 - 오전장에는 기준 대폭 완화
        if is_early_morning:
            # 오전장 최소 체크 - 극단적 고점 근접(10% 이상)만 제외
            if 'minute_ohlcv' in stock_data and stock_data['minute_ohlcv'] is not None:
                minute_df = stock_data['minute_ohlcv']
                if len(minute_df) >= 5:
                    recent_high = minute_df['high'].max()
                    high_ratio = (recent_high - current_price) / current_price * 100
                    if high_ratio > 10:  # 10% 이상 차이나는 경우만 제외
                        logger.info(f"{stock_name}({stock_code}) - 오전장이지만 극단적 고점 근접으로 제외")
                        return False
            
            logger.info(f"{stock_name}({stock_code}) - 오전장 고점 근접도 조건 통과 (완화 기준 적용)")

        else:
            # 고점 근접도 체크 - 조건 충족 여부 먼저 확인하고 로그 출력
            high_proximity_passed = check_improved_high_proximity(stock_data, momentum_score)

            if not high_proximity_passed:
                logger.info(f"{stock_name}({stock_code}) - 고점 근접도 조건 불충족으로 제외")
                
                # 모멘텀 점수가 높은 경우 저장
                if momentum_score >= HIGH_MOMENTUM_SCORE_THRESHOLD:
                    save_high_momentum_missed_stocks(stock_data, momentum_score, "고점 근접도 불충족")
                
                return False

            logger.info(f"{stock_name}({stock_code}) - 고점 근접도 조건 통과")
        
        # 분봉 데이터 확인 및 안전 처리
        if 'minute_ohlcv' not in stock_data or stock_data['minute_ohlcv'] is None:
            logger.info(f"{stock_code}: 분봉 데이터 없음")
            if is_early_morning or is_morning_session:
                # 오전장에서만 일봉 데이터로 대체 가능
                logger.info(f"{stock_code}: 일봉 데이터로 대체")
                analysis_df = stock_data['ohlcv']
            else:
                logger.info(f"{stock_code}: 매수 조건 확인 불가")
                return False
        else:
            analysis_df = stock_data['minute_ohlcv']

        # 데이터 길이 체크
        if len(analysis_df) < 5:
            logger.info(f"{stock_code}: 데이터 부족 (개수: {len(analysis_df)}개)")
            if is_early_morning or is_morning_session:
                # 오전장에서만 일봉으로 대체
                logger.info(f"{stock_code}: 일봉 데이터로 대체")
                analysis_df = stock_data['ohlcv']
            else:
                logger.info(f"{stock_name}({stock_code}) - 데이터 부족으로 제외")
                return False
        
        # 단기 급등 여부 (분봉 또는 일봉)
        short_term_low = analysis_df['low'].tail(10).min()
        short_term_rise = ((current_price - short_term_low) / short_term_low) * 100
        
        # 시간대별 다른 기준 적용
        if is_early_morning:
            rise_min = 2.0  # 최소 2% 상승
            rise_max = None  # 상한 제한 없음
        else:
            rise_min = 2.2  # 최소 2.2% 상승
            rise_max = 15.0  # 최대 15% 상승

        # 모멘텀 점수 기반 동적 상승률 조정
        if momentum_score >= 75:
            # 매우 높은 모멘텀 점수(75+)를 가진 종목은 상승률 기준 50% 완화
            rise_min_adjusted = rise_min * 0.5
            logger.info(f"모멘텀 점수가 매우 높음({momentum_score}): 상승률 기준 50% 완화 ({rise_min} -> {rise_min_adjusted})")
        elif momentum_score >= 65:
            # 높은 모멘텀 점수(65+)를 가진 종목은 상승률 기준 30% 완화
            rise_min_adjusted = rise_min * 0.7
            logger.info(f"모멘텀 점수가 높음({momentum_score}): 상승률 기준 30% 완화 ({rise_min} -> {rise_min_adjusted})")
        else:
            # 일반 종목은 기존 기준 적용
            rise_min_adjusted = rise_min
            logger.info(f"일반 모멘텀 점수({momentum_score}): 기존 상승률 기준 유지 ({rise_min})")

        ################ 동적 상승률 조정 ###########
        # 모멘텀 점수 기반 동적 상승률 조정
        if momentum_score >= 85:
            # 초고 모멘텀 점수(85+)에 대한 추가 완화
            rise_min_adjusted = rise_min * 0.3  # 70% 추가 완화
            logger.info(f"초고 모멘텀 점수({momentum_score}): 상승률 기준 70% 완화 ({rise_min} -> {rise_min_adjusted})")
        elif momentum_score >= 75:
            # 기존 완화 유지
            rise_min_adjusted = rise_min * 0.5  # 50% 완화
            logger.info(f"모멘텀 점수가 매우 높음({momentum_score}): 상승률 기준 50% 완화 ({rise_min} -> {rise_min_adjusted})")
        elif momentum_score >= 65:
            # 기존 완화 유지
            rise_min_adjusted = rise_min * 0.7  # 30% 완화
            logger.info(f"모멘텀 점수가 높음({momentum_score}): 상승률 기준 30% 완화 ({rise_min} -> {rise_min_adjusted})")
        else:
            # 일반 종목은 기존 기준 적용
            rise_min_adjusted = rise_min
            logger.info(f"일반 모멘텀 점수({momentum_score}): 기존 상승률 기준 유지 ({rise_min})")
        ################ 동적 상승률 조정 끝 ##########

        # 단기 상승률 조건 - 동적으로 조정된 기준값 사용
        if short_term_rise < rise_min_adjusted:
            logger.info(f"⚠️ 단기 상승률 조건 불충족: 현재 {short_term_rise:.2f}% < 기준 {rise_min_adjusted}%")

            # 모멘텀 기반 단기 상승률 조건 우회 여부 확인
            can_override, override_reason = check_momentum_based_rise_override(stock_data, momentum_score)
            
            if can_override:
                logger.info(f"✅ 단기 상승률 조건 우회 적용: {override_reason}")
            else:
                logger.info(f"{stock_name}({stock_code}) - 단기 상승률 조건 불충족으로 제외: {override_reason}")
                
                # 모멘텀 점수가 높은 경우 저장
                if momentum_score >= HIGH_MOMENTUM_SCORE_THRESHOLD:
                    save_high_momentum_missed_stocks(stock_data, momentum_score, "단기 상승률 조건 불충족")
                    
                # 박스권 돌파 패턴 확인 (추가 분석)
                is_consolidation, info = find_consolidation_pattern(stock_data)
                if is_consolidation:
                    logger.info(f"⚠️ 박스권 돌파 패턴 감지됨 - 모니터링 대상")
                    
                return False

        logger.info(f"✅ 단기 상승률 조건 충족: {short_term_rise:.2f}% >= {rise_min_adjusted}%")
        
        # 상승률 상한 체크 - 장초반 제외
        if not is_early_morning and rise_max and short_term_rise > rise_max:
            logger.info(f"⚠️ 상승률 초과: {short_term_rise:.1f}% > {rise_max}%")
            logger.info(f"{stock_name}({stock_code}) - 상승률 초과로 제외")
            return False

        # 거래량 조건 강화
        current_volume = stock_data['volume']
        avg_volume = stock_data['volume_ma5']

        # 시간대별로 다른 기준 적용
        # if is_early_morning:
        #     volume_multiplier = 1.3  # 거래량 1.3배 이상
        #     min_bullish_candles = 2  # 최근 캔들 중 2개 이상 양봉
        # else:
        #     volume_multiplier = 1.7  # 거래량 1.7배 이상
        #     min_bullish_candles = 3  # 최근 캔들 중 3개 이상 양봉

        if is_early_morning:
            volume_multiplier = 1.3  # 거래량 1.0배 이상 (1.3배에서 완화)
            min_bullish_candles = 2  # 최근 캔들 중 1개 이상 양봉 (2개에서 완화)
        elif is_morning_session:
            volume_multiplier = 1.5  # 거래량 1.2배 이상 (1.7배에서 완화)
            min_bullish_candles = 2  # 최근 캔들 중 2개 이상 양봉 (3개에서 완화)
        else:
            volume_multiplier = 2.0  # 거래량 1.7배 이상 (기존과 동일)
            min_bullish_candles = 3  # 최근 캔들 중 3개 이상 양봉 (기존과 동일)

        # 분봉/일봉 상승 모멘텀 분석
        recent_candles = analysis_df.tail(10)
        bullish_candles = recent_candles[recent_candles['close'] > recent_candles['open']]
            
        # 거래량 조건 체크
        if current_volume <= avg_volume * volume_multiplier:
            logger.info(f"⚠️ 거래량 조건 미달: {current_volume:,.0f} <= {avg_volume * volume_multiplier:,.0f}")
            logger.info(f"{stock_name}({stock_code}) - 거래량 부족으로 제외")
            return False
            
        if len(bullish_candles) < min_bullish_candles:
            logger.info(f"⚠️ 양봉 수 부족: {len(bullish_candles)}개 < {min_bullish_candles}개")
            logger.info(f"{stock_name}({stock_code}) - 양봉 수 부족으로 제외")
            return False
            
        logger.info(f"✅ 거래량 조건 충족: {current_volume:,.0f} > {avg_volume * volume_multiplier:,.0f}")
        logger.info(f"✅ 양봉 수 충족: {len(bullish_candles)}개 >= {min_bullish_candles}개")


        # RSI 조건 조정
        if is_early_morning:
            rsi_lower = MIN_EARLY_MORNING_BUY_RSI
            rsi_upper = MAX_EARLY_MORNING_BUY_RSI
        else:
            rsi_lower = MIN_BUY_RSI
            rsi_upper = MAX_BUY_RSI


        # 저점 상승 패턴 확인 - 새로 추가
        is_suitable_entry, pattern_info = detect_higher_lows_pattern(stock_code)
        if is_suitable_entry or (pattern_info.get('pattern_strength', 0) >= 4):
            # 저점 상승 패턴이 감지되고 매수 적합성이 높으면 RSI 상한 완화
            pattern_strength = pattern_info.get('pattern_strength', 0)
            logger.info(f"\n✨ {stock_name}({stock_code}) - 오전장 저점 상승 패턴 감지! 패턴 강도: {pattern_strength:.1f}/10")

            # 패턴 강도에 따른 동적 RSI 상한 증가
            if pattern_strength >= 8:  # 매우 강한 패턴
                pattern_extension = 15  # RSI 상한 15 증가
                logger.info(f"매우 강한 저점 상승 패턴 감지: RSI 상한 +15")
            elif pattern_strength >= 6:  # 강한 패턴
                pattern_extension = 10  # RSI 상한 10 증가
                logger.info(f"강한 저점 상승 패턴 감지: RSI 상한 +10")
            else:  # 적당한 패턴
                pattern_extension = 5  # RSI 상한 5 증가
                logger.info(f"저점 상승 패턴 감지: RSI 상한 +5")
            
            rsi_upper += pattern_extension
            logger.info(f"저점 상승 패턴으로 RSI 상한 완화: {rsi_upper}")
        else:
            # 저점 상승 패턴이 없을 때도 트렌드 반전 체크
            if check_trend_reversal(stock_data):
                rsi_upper += 5  # RSI 상한 5 증가
                logger.info(f"트렌드 반전 신호로 RSI 상한 일부 완화: {rsi_upper}")

        # 강한 거래량 조건 확인 - 기존 코드 유지
        volume_ratio = current_volume / avg_volume
        is_strong_volume = volume_ratio >= 3.0  # 3배 이상의 거래량을 강한 거래량으로 정의

        # 거래량이 매우 강할 경우 RSI 상한선 추가 완화 (조건부 완화)
        if is_strong_volume:
            # 거래량 강도에 따른 동적 RSI 상한 조정
            volume_strength = min(volume_ratio / 3.0, 2.0)  # 1.0~2.0 범위로 제한
            rsi_extension = 5 * volume_strength  # 최대 10포인트까지 확장 가능
            adjusted_rsi_upper = rsi_upper + rsi_extension  # 이미 저점 상승 패턴으로 조정된 rsi_upper에 추가
            
            logger.info(f"강한 거래량 감지 (평균 대비 {volume_ratio:.1f}배)")
            logger.info(f"RSI 상한 추가 완화: {rsi_upper} → {adjusted_rsi_upper:.1f}")
        else:
            adjusted_rsi_upper = rsi_upper


        # 거래량이 매우 강할 경우 RSI 상한선 추가 완화 (조건부 완화)
        if is_strong_volume:
            # 거래량 강도에 따른 동적 RSI 상한 조정
            volume_strength = min(volume_ratio / 3.0, 2.0)  # 1.0~2.0 범위로 제한
            rsi_extension = 5 * volume_strength  # 최대 10포인트까지 확장 가능
            adjusted_rsi_upper = rsi_upper + rsi_extension  # 이미 저점 상승 패턴으로 조정된 rsi_upper에 추가
            
            logger.info(f"강한 거래량 감지 (평균 대비 {volume_ratio:.1f}배)")
            logger.info(f"RSI 상한 추가 완화: {rsi_upper} → {adjusted_rsi_upper:.1f}")
        else:
            adjusted_rsi_upper = rsi_upper


        # RSI 조건 체크 - 강한 거래량 시 완화된 기준 적용
        if not (rsi_lower < rsi < adjusted_rsi_upper):
            if rsi <= rsi_lower:
                logger.info(f"⚠️ RSI 과매도 상태: {rsi:.1f} <= {rsi_lower}")
                logger.info(f"{stock_name}({stock_code}) - RSI 과매도 상태로 제외")
                return False
            else:
                # 거래량에 따른 추가 세부 로깅
                if is_strong_volume and rsi < rsi_upper + 10:  # 최대 10포인트까지만 예외 고려
                    logger.info(f"⚠️ RSI 과매수 상태이나 강한 거래량 동반: {rsi:.1f}")
                    
                    # 추가 보호 조건: 거래량이 매우 높더라도 RSI가 극단적으로 높으면 제외
                    if rsi >= 85:
                        logger.info(f"⚠️ RSI가 지나치게 높아(85+) 거래량에 관계없이 매수 제외")
                        logger.info(f"{stock_name}({stock_code}) - 극단적 RSI 상태로 제외")
                        return False
                    
                    # MACD 추세 확인 (추가 확인)
                    macd_trend_strong = (
                        stock_data['macd'] > stock_data['macd_signal'] and
                        stock_data['macd'] > stock_data['prev_macd'] * 1.05  # 5% 이상 증가
                    )
                    
                    if not macd_trend_strong:
                        logger.info(f"⚠️ 강한 거래량에도 MACD 추세 불충분으로 제외")
                        logger.info(f"{stock_name}({stock_code}) - MACD 추세 약세로 제외")
                        return False
                    
                    # 여기까지 왔다면 강한 거래량 + 적절한 MACD 조건 충족으로 예외 적용
                    logger.info(f"✅ 강한 거래량 + 상승 추세로 RSI 과매수 기준 완화 적용")
                else:
                    logger.info(f"⚠️ RSI 과매수 상태: {rsi:.1f} >= {adjusted_rsi_upper:.1f}")
                    logger.info(f"{stock_name}({stock_code}) - RSI 상태로 제외")
                    return False
                
        logger.info(f"✅ RSI 조건 충족: {rsi_lower} < {rsi:.1f} < {adjusted_rsi_upper:.1f}")

        # 오후 시간대 이동평균선 관계 체크
        is_afternoon_session = is_in_afternoon_session()
        if is_afternoon_session and not check_ma_relationship(stock_data['ohlcv']):
            logger.info(f"{stock_name}({stock_code}) - 오후 시간대 이동평균선 관계 부정적으로 제외")
            return False

        # 호가 분석
        is_favorable, order_info = analyze_order_book(stock_code)
        if not is_favorable:
            logger.info(f"{stock_name}({stock_code}) - 호가 조건 미달로 제외")
            return False
            
        logger.info(f"✅ 호가 조건 충족")

        # 추세 유지 확인 - 장초반 제외 & 분봉 데이터가 있는 경우만
        if not is_early_morning and 'minute_ohlcv' in stock_data and stock_data['minute_ohlcv'] is not None:
            minute_df = stock_data['minute_ohlcv']
            if len(minute_df) >= 6 and current_price <= minute_df['close'].iloc[-6]:
                logger.info(f"{stock_name}({stock_code}) - 최근 추세 하락으로 제외")
                return False
                
        logger.info(f"✅ 추세 유지 조건 충족")

        # 최종 매수 결정 전에 상승 초기 단계 확인 추가
        if not enhanced_entry_timing(stock_data):
            logger.info(f"{stock_name}({stock_code}) - 상승 초기 단계가 아니므로 매수 보류")
            return False

        logger.info(f"✅ {stock_code} 모든 매수 조건 충족")
        return True

    except Exception as e:
        stock_name = KisKR.GetStockName(stock_data['code']) if 'code' in stock_data else "알 수 없음"
        stock_code = stock_data.get('code', "알 수 없음")
        logger.error(f"매수 조건 분석 중 오류: {str(e)}")
        logger.info(f"{stock_name}({stock_code}) - 분석 중 오류 발생으로 제외")
        return False


def calculate_dynamic_rise_threshold(stock_data):
    """
    주식의 특성에 따라 동적으로 상승률 임계값을 계산하는 함수
    
    Args:
        stock_data (dict): 종목 데이터
    
    Returns:
        float: 동적으로 계산된 상승률 임계값
    """
    try:
        df = stock_data['ohlcv']
        
        # 최근 20일 일간 상승률 계산
        daily_returns = ((df['close'] - df['open']) / df['open']) * 100
        
        # 통계적 특성 계산
        mean_return = daily_returns.mean()
        std_return = daily_returns.std()
        
        # 변동성 기반 동적 임계값 계산
        # 평균 + 1.5 * 표준편차 방식으로 임계값 설정
        dynamic_threshold = mean_return + (1.5 * std_return)
        
        # 최소/최대 임계값 제한
        dynamic_threshold = max(3.0, min(dynamic_threshold, 10.0))  # 기존 2.0-8.0에서 3.0-10.0으로 조정
        
        logger.info(f"동적 상승률 임계값 계산:")
        logger.info(f"- 평균 일간 수익률: {mean_return:.2f}%")
        logger.info(f"- 일간 수익률 표준편차: {std_return:.2f}%")
        logger.info(f"- 계산된 임계값: {dynamic_threshold:.2f}%")
        
        return dynamic_threshold
    
    except Exception as e:
        logger.error(f"동적 임계값 계산 중 에러: {str(e)}")
        return 5.0  # 기본값


def is_near_recent_high(stock_code):
    """
    분봉 기준 최근 고점 근접 여부 확인
    - 단타 전략에 최적화
    - 분봉 데이터 기반 빠른 모멘텀 판단
    """
    try:
        # 분봉 데이터 로드 (기본 1분봉)
        df = KisKR.GetOhlcvMinute(stock_code)
        
        if df is None or len(df) < 30:  # 최소 30개 분봉 필요
            return False
        
        # 최근 30개 분봉 내 최고가
        recent_high = df['high'].tail(30).max()
        current_price = df['close'].iloc[-1]
        
        # 현재 시간 확인
        #now = datetime.now()
        is_morning_session = is_in_morning_session()
        
        # 시간대별 동적 임계값
        if is_morning_session:  # 장 초반
            proximity_threshold = 0.02  # 2% 근접
            rise_threshold = 1.0        # 1% 상승
        else:
            proximity_threshold = 0.01  # 1% 근접
            rise_threshold = 1.5        # 1.5% 상승
        
        # 고가 근접도 계산
        proximity_rate = (recent_high - current_price) / recent_high
        
        # 최근 분봉 상승률 계산
        recent_rises = ((df['close'].tail(5) - df['open'].tail(5)) / df['open'].tail(5) * 100)
        max_short_rise = recent_rises.max()
        avg_short_rise = recent_rises.mean()
        
        # 상세 로깅
        logger.info(f"\n단기 고점 근접 분석 ({stock_code}):")
        logger.info(f"- 현재가: {current_price:,.0f}원")
        logger.info(f"- 최근 30분봉 고가: {recent_high:,.0f}원")
        logger.info(f"- 고가 근접도: {proximity_rate*100:.2f}%")
        logger.info(f"- 최근 5분봉 최대 상승률: {max_short_rise:.2f}%")
        logger.info(f"- 최근 5분봉 평균 상승률: {avg_short_rise:.2f}%")
        
        # 복합 조건 평가
        is_close = (
            proximity_rate < proximity_threshold and  # 고가 근접도
            (max_short_rise > rise_threshold or     # 최대 상승률 또는
             avg_short_rise > rise_threshold * 0.7)  # 평균 상승률
        )
        
        return is_close
    
    except Exception as e:
        logger.error(f"단기 고점 체크 중 에러: {str(e)}")
        return False


def analyze_candle_patterns(stock_data):
    """연속 양봉/음봉 패턴 분석 및 위치 판단"""
    try:
        df = stock_data['ohlcv']
        
        # 최근 20개 봉 분석
        recent_candles = df.tail(20)
        
        # 1. 상승 구간 파악
        candle_directions = []  # 양봉/음봉 기록
        price_levels = []       # 가격 수준 기록
        bullish_count = 0      # 연속 양봉 카운트
        total_bullish = 0      # 전체 양봉 수
        
        for i in range(len(recent_candles)):
            # 양봉/음봉 기록
            is_bullish = recent_candles['close'].iloc[i] > recent_candles['open'].iloc[i]
            candle_directions.append(1 if is_bullish else -1)
            
            if is_bullish:
                total_bullish += 1
                if i > 0 and candle_directions[i-1] == 1:
                    bullish_count += 1
            else:
                bullish_count = 0
            
            # 가격과 거래량 기록
            price_levels.append({
                'high': recent_candles['high'].iloc[i],
                'low': recent_candles['low'].iloc[i],
                'volume': recent_candles['volume'].iloc[i]
            })
        
        # 2. 상승 구간 분석
        uptrend_segments = []
        current_segment = []
        
        for i, direction in enumerate(candle_directions):
            if direction == 1:  # 양봉
                current_segment.append(i)
            else:  # 음봉
                if len(current_segment) >= 2:  # 2개 이상 연속 양봉 구간 저장
                    uptrend_segments.append(current_segment)
                current_segment = []
        
        if current_segment:  # 마지막 구간 처리
            uptrend_segments.append(current_segment)
        
        # 3. 초기 상승추세 판단
        is_initial_uptrend = False
        if uptrend_segments:
            latest_segment = uptrend_segments[-1]
            # 초기 상승 조건
            is_initial_uptrend = (
                len(uptrend_segments) <= 2 and               # 상승 구간이 2개 이하
                bullish_count >= 2 and                       # 현재 2개 이상 연속 양봉
                total_bullish <= 5                           # 전체 양봉이 5개 이하
            )
        
        # 4. 후반부 상승 판단
        is_late_uptrend = False
        reasons = []
        
        if uptrend_segments and len(uptrend_segments) >= 2:  # 최소 2개 이상의 상승 구간
            latest_segment = uptrend_segments[-1]
            
            # a) 거래량 분석
            recent_volume_avg = sum(price_levels[i]['volume'] for i in latest_segment) / len(latest_segment)
            prev_volume_avg = df['volume'].iloc[-20:-len(latest_segment)].mean()
            volume_increase_rate = recent_volume_avg / prev_volume_avg if prev_volume_avg > 0 else 0
            
            # b) 고점 돌파 확인
            current_high = max(price_levels[i]['high'] for i in latest_segment)
            previous_high = max(df['high'].iloc[-20:-len(latest_segment)])
            breaks_previous_high = current_high > previous_high
            
            # c) 상승 강도 계산
            recent_candle_sizes = [
                (price_levels[i]['high'] - price_levels[i]['low']) 
                for i in latest_segment
            ]
            avg_recent_size = sum(recent_candle_sizes) / len(recent_candle_sizes)
            
            previous_sizes = [
                (price_levels[i]['high'] - price_levels[i]['low']) 
                for i in range(len(price_levels)-len(latest_segment))
            ]
            avg_previous_size = sum(previous_sizes) / len(previous_sizes) if previous_sizes else 0
            
            # 상승 강도 계산
            price_strength = sum(
                (price_levels[i]['high'] - price_levels[i]['low']) / price_levels[i]['low'] * 100
                for i in latest_segment
            ) / len(latest_segment)
            
            # 후반부 상승 판단
            if volume_increase_rate > 1.5:
                reasons.append(f"거래량 급증 (이전 대비 {volume_increase_rate:.1f}배)")
                is_late_uptrend = True
                
            if breaks_previous_high:
                reasons.append("이전 고점 돌파")
                is_late_uptrend = True
                
            if avg_recent_size > avg_previous_size * 1.2:
                reasons.append("봉의 크기 증가")
                is_late_uptrend = True
        
        pattern = {
            'is_initial_uptrend': is_initial_uptrend,
            'is_late_uptrend': is_late_uptrend,
            'reasons': reasons,
            'bullish_count': bullish_count,
            'total_bullish': total_bullish,
            'uptrend_segments': len(uptrend_segments),
            'current_segment_size': len(current_segment) if current_segment else 0,
            'volume_trend': volume_increase_rate > 1.5 if 'volume_increase_rate' in locals() else False,
            'strength': price_strength if 'price_strength' in locals() else 0
        }
        
        if is_initial_uptrend:
            logger.info("\n초기 상승 패턴 감지:")
            logger.info(f"- 연속 양봉: {bullish_count}개")
            logger.info(f"- 전체 양봉: {total_bullish}개")
        elif is_late_uptrend:
            logger.info("\n후반부 상승 패턴 감지:")
            for reason in reasons:
                logger.info(f"- {reason}")
        
        return pattern
        
    except Exception as e:
        logger.error(f"캔들 패턴 분석 중 에러: {str(e)}")
        return None

def is_high_rise_today(stock_data):
    """당일 급등 여부 확인 - 패턴 기반 개선버전"""
    try:
        df = stock_data['ohlcv']
        current_price = stock_data['current_price']
        open_price = df['open'].iloc[-1]
        
        # 캔들 패턴 분석
        pattern = analyze_candle_patterns(stock_data)
        if pattern is None:
            return False
            
        # 기본 상승률 계산
        today_rise_rate = ((current_price - open_price) / open_price) * 100
        recent_low = df['low'].tail(6).min()
        recent_rise_rate = ((current_price - recent_low) / recent_low) * 100
        
        logger.info(f"\n상승 패턴 분석:")
        logger.info(f"- 연속 양봉: {pattern['bullish_count']}개")
        logger.info(f"- 전체 양봉: {pattern['total_bullish']}개")
        logger.info(f"- 거래량 증가: {pattern['volume_trend']}")
        logger.info(f"- 상승 강도: {pattern['strength']:.2f}%")
        
        # 초기 상승추세인 경우 - 매수 허용 기준 완화
        if pattern['is_initial_uptrend']:
            is_high_rise = (
                today_rise_rate > 5.0 or       # 5% 이상 급등
                recent_rise_rate > 3.5         # 30분내 3.5% 이상 급등
            )
            logger.info("초기 상승추세 판단중...")
            
        # 후반부 상승인 경우 - 매수 제한 기준 강화
        elif pattern['is_late_uptrend']:
            is_high_rise = (
                today_rise_rate > 2.5 or       # 2.5% 이상만 되어도 제한
                recent_rise_rate > 1.5 or      # 30분내 1.5% 이상 급등
                pattern['strength'] > 4.0      # 누적 상승강도 4% 초과
            )
            logger.info("후반부 상승 판단중...")
            
        else:
            # 일반적인 상황 - 기존 로직 유지
            is_high_rise = (
                today_rise_rate > 3.5 or       # 3.5% 이상 급등
                recent_rise_rate > 2.0         # 30분내 2% 이상 급등
            )
            logger.info("일반 패턴 판단중...")
        
        if is_high_rise:
            logger.info(f"당일 급등 감지:")
            logger.info(f"- 시초가 대비 상승률: {today_rise_rate:.2f}%")
            logger.info(f"- 최근 30분 상승률: {recent_rise_rate:.2f}%")
            
        return is_high_rise
            
    except Exception as e:
        logger.error(f"급등 체크 중 에러: {str(e)}")
        return False

# 연속 음봉 수 계산 로직 추가
def count_continuous_bearish_candles(df, min_candles=3):
    if df is None or len(df) < min_candles:
        return 0
    
    bearish_count = 0
    for i in range(1, len(df)):
        # 엄격한 음봉 조건 (종가 < 시가, 종가와 시가의 차이 고려)
        if ((df['close'].iloc[-i] < df['open'].iloc[-i]) and 
            (df['close'].iloc[-i-1] < df['open'].iloc[-i-1]) and
            abs(df['close'].iloc[-i] - df['open'].iloc[-i]) > 0.005):  # 0.5% 이상 차이
            bearish_count += 1
        else:
            break

    return bearish_count


def check_pending_orders(stock_code, trading_state=None):
    """
    특정 종목의 미체결 주문이 있는지 확인 - 내부 상태와 API 양쪽 확인
    
    Args:
        stock_code (str): 종목코드
        trading_state (dict): 트레이딩 상태 (None이면 자동 로드)
        
    Returns:
        bool: 미체결 주문이 있으면 True, 없으면 False
    """
    try:
        # 1. 내부 상태 확인 (메모리/파일)
        if trading_state is None:
            trading_state = load_trading_state()
            
        pending_orders = trading_state.get('pending_orders', {})
        if stock_code in pending_orders:
            order_info = pending_orders[stock_code]
            if order_info.get('status', '') in ['pending', 'submitted']:
                logger.info(f"{stock_code}: 내부 상태에 미체결 주문 있음")
                return True
        
        # 2. API 확인 (기존 로직)
        open_orders = KisKR.GetOrderList(
            stockcode=stock_code,
            side="BUY",
            status="OPEN"  # 미체결 주문만 조회
        )
        
        # API 반환값 체크 - 문자열인 경우는 에러코드
        if isinstance(open_orders, str):
            logger.error(f"주문 목록 조회 오류: {open_orders}")
            # API 오류 시에도 내부 상태가 미체결이면 True 반환
            return stock_code in pending_orders
        
        # 해당 종목의 미체결 주문 필터링
        api_pending_orders = [
            order for order in open_orders 
            if order.get('OrderStock') == stock_code and 
               order.get('OrderSatus') == "Open"  # API 필드명 주의: OrderSatus (오타)
        ]
        
        if api_pending_orders:
            logger.info(f"{stock_code}: API에서 미체결 주문 있음 - 매수 건너뜀")
            return True
        
        return False
            
    except Exception as e:
        logger.error(f"미체결 주문 확인 중 에러: {str(e)}")
        # 에러 발생 시에도 내부 상태 확인
        if trading_state and 'pending_orders' in trading_state:
            return stock_code in trading_state['pending_orders']
        return False  # 모든 확인이 실패하면 안전하게 False 반환


def cancel_order(order_id):
    """
    주문 취소 함수
    
    Args:
        order_id (str): 주문번호
        
    Returns:
        bool: 취소 성공 여부
    """
    try:
        # GetOrderList로 주문 정보 상세 조회
        order_details = KisKR.GetOrderList(
            status="OPEN"  # 미체결 주문만 필요
        )
        
        # API 반환값 체크 - 문자열인 경우는 에러코드
        if isinstance(order_details, str):
            logger.error(f"주문 목록 조회 오류: {order_details}")
            return False
            
        # 주문번호로 주문 찾기
        target_order = None
        for order in order_details:
            if order.get('OrderNum') == order_id:
                target_order = order
                break
                
        if not target_order:
            logger.error(f"취소할 주문을 찾을 수 없음: {order_id}")
            return False
            
        # CancelModifyOrder 함수 호출
        stock_code = target_order.get('OrderStock')
        order_num1 = target_order.get('OrderNum')
        order_num2 = target_order.get('OrderNum2', '')
        order_amt = target_order.get('OrderAmt', 0)
        order_price = float(target_order.get('OrderAvgPrice', '0'))
        
        result = KisKR.CancelModifyOrder(
            stockcode=stock_code,
            order_num1=order_num1,
            order_num2=order_num2,
            order_amt=order_amt,
            order_price=order_price,
            mode="CANCEL"
        )
        
        # 취소 결과 확인
        if isinstance(result, dict) and 'OrderNum' in result:
            logger.info(f"주문 취소 성공: {order_id}")
            return True
        else:
            logger.error(f"주문 취소 실패: {result}")
            return False
            
    except Exception as e:
        logger.error(f"주문 취소 중 에러: {str(e)}")
        return False


def auto_cancel_pending_orders(max_pending_minutes=15):
    """
    일정 시간 이상 경과된 미체결 주문 자동 취소 - 개선버전
    
    Args:
        max_pending_minutes (int): 미체결 상태 최대 허용 시간(분)
    """
    try:
        # 트레이딩 상태 로드
        trading_state = load_trading_state()
        pending_orders = trading_state.get('pending_orders', {})
        
        if not pending_orders:
            return  # 미체결 주문이 없으면 건너뜀
            
        current_time = datetime.now()
        canceled_orders = []  # 취소된 주문 목록
        processed_orders = []  # 처리된 주문 목록 (삭제 대상)
        
        # 내 주식 목록 가져오기 (실제 보유 확인용)
        my_stocks = KisKR.GetMyStockList()
        holding_codes = {}
        
        # 코드별 보유 수량 맵 생성
        for stock in my_stocks:
            holding_codes[stock['StockCode']] = int(stock.get('StockAmt', 0))
        
        # 미체결 주문 순회
        for stock_code, order_info in list(pending_orders.items()):
            try:
                # 주문 상태 확인
                order_status = order_info.get('status', 'unknown')
                
                # 이미 체결/취소된 주문은 처리 목록에 추가하고 넘어감
                if order_status in ['filled', 'canceled', 'expired']:
                    processed_orders.append(stock_code)
                    continue
                
                # 실제 보유 중인지 확인 (API로)
                actual_amount = holding_codes.get(stock_code, 0)
                expected_amount = order_info.get('order_amount', 0)
                
                # 미체결 상태인데 실제로는 보유 중인 경우 (체결되었지만 상태가 업데이트되지 않은 경우)
                if order_status in ['pending', 'submitted'] and actual_amount > 0:
                    # 이미 상태 불일치 알림이 발송되었는지 확인
                    already_fixed = order_info.get('already_fixed', False)
                    
                    if not already_fixed:
                        stock_name = KisKR.GetStockName(stock_code)
                        logger.info(f"{stock_name}({stock_code}) - 미체결 주문으로 표시되어 있으나 실제로 보유 중 - 상태 업데이트")
                        
                        # 보유 정보로 포지션 업데이트
                        if stock_code not in trading_state.get('positions', {}):
                            if 'positions' not in trading_state:
                                trading_state['positions'] = {}

                            # 주문 정보에서 지정가 가져오기 (대체값으로만 사용)
                            order_price = order_info.get('order_price', 0)

                            # 실제 체결가를 API에서 가져와 사용
                            avg_price = float(stock.get('AvrPrice', 0))  # API의 평균매입가 우선 사용
                            if avg_price <= 0:  # API 평균가가 없는 경우에만
                                avg_price = order_price  # 주문가를 대체값으로 사용
                                logger.warning(f"{stock_code}: API 평균가 정보 없음 - 주문가 {order_price}원을 대체값으로 사용")

                            trading_state['positions'][stock_code] = {
                                'entry_price': avg_price,  # 지정가 우선 사용
                                'amount': actual_amount,
                                'entry_time': order_info.get('order_time', current_time.strftime('%Y-%m-%d %H:%M:%S')),
                                'trading_fee': 0,  # 정확한 수수료 정보 없음
                                'code': stock_code,
                                'strategy': 'auto_recovery',  # 자동 복구 표시
                                'recovery_note': '미체결 주문으로 표시되었으나 실제 보유 중 발견',
                                # 분할매수 정보도 유지
                                'buy_stage': order_info.get('buy_stage', 1),
                                'last_buy_time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                                'total_planned_amount': order_info.get('total_planned_amount', actual_amount)
                            }
                            
                            msg = f"⚠️ 상태 불일치 수정: {stock_name}({stock_code})\n"
                            msg += f"- 미체결 주문으로 등록되어 있었으나 실제로 보유 중\n"
                            msg += f"- 보유량: {actual_amount}주, 평균가: {avg_price:,}원\n"
                            msg += f"- 상태 자동 복구 완료"
                            logger.info(msg)
                            discord_alert.SendMessage(msg)
                        
                        # 중복 복구 방지를 위해 상태 표시
                        order_info['already_fixed'] = True
                        order_info['status'] = 'filled'  # 체결된 것으로 상태 변경
                        order_info['fix_time'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
                        
                        # 자동으로 trading_state 저장
                        save_trading_state(trading_state)
                    else:
                        # 이미 복구 처리된 주문
                        processed_orders.append(stock_code)
                    
                    continue
                
                # 주문 시간 파싱
                order_time_str = order_info.get('order_time', '')
                if not order_time_str:
                    logger.warning(f"{stock_code}: 주문 시간 정보 없음 - 미체결 주문에서 제거")
                    processed_orders.append(stock_code)
                    continue
                
                try:
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    logger.warning(f"{stock_code}: 주문 시간 형식 오류 ({order_time_str}) - 미체결 주문에서 제거")
                    processed_orders.append(stock_code)
                    continue
                
                # 경과 시간 계산
                elapsed_minutes = (current_time - order_time).total_seconds() / 60
                
                # 설정 시간 초과 확인
                if elapsed_minutes > max_pending_minutes:
                    stock_name = KisKR.GetStockName(stock_code)
                    logger.info(f"자동 취소 대상: {stock_name}({stock_code}) - {elapsed_minutes:.1f}분 경과")
                    
                    # 체결되지 않은 주문 정보 확인
                    open_orders = KisKR.GetOrderList(
                        stockcode=stock_code,
                        side="BUY",
                        status="OPEN"
                    )
                    
                    has_open_order = False
                    order_id = order_info.get('order_id', '')
                    
                    # 취소할 주문 찾기
                    for order in open_orders:
                        if order.get('OrderStock') == stock_code:
                            has_open_order = True
                            order_id = order.get('OrderNum', '')
                            break
                    
                    if has_open_order:
                        # 주문 취소 시도
                        cancel_success = cancel_order(order_id)
                        
                        if cancel_success:
                            msg = f"🕒 미체결 주문 자동 취소 ({elapsed_minutes:.1f}분 경과)\n"
                            msg += f"- 종목: {stock_name}({stock_code})\n"
                            msg += f"- 수량: {order_info.get('order_amount', 0)}주 @ {order_info.get('order_price', 0):,}원"
                            logger.info(msg)
                            discord_alert.SendMessage(msg)
                            
                            # 주문 상태 업데이트
                            order_info['status'] = 'canceled'
                            order_info['cancel_time'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
                            canceled_orders.append(stock_code)
                        else:
                            logger.error(f"주문 취소 실패: {stock_code} - 주문번호: {order_id}")
                    else:
                        # API 상으로는 미체결 주문이 없지만 상태 파일에는 있는 경우
                        logger.info(f"{stock_name}({stock_code}) - 미체결 주문 정보가 있으나 실제 주문 없음 - 상태 제거")
                        order_info['status'] = 'expired'
                        order_info['expire_time'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
                        processed_orders.append(stock_code)
                
            except Exception as inner_e:
                logger.error(f"미체결 주문 처리 중 오류 (종목: {stock_code}): {str(inner_e)}")
                continue
        
        # 처리된 주문 정리 - 24시간 이상 경과한 항목은 제거
        for stock_code in processed_orders:
            order_info = pending_orders.get(stock_code, {})
            process_time_str = order_info.get('fix_time', order_info.get('cancel_time', order_info.get('expire_time')))
            
            if process_time_str:
                try:
                    process_time = datetime.strptime(process_time_str, '%Y-%m-%d %H:%M:%S')
                    time_since_process = (current_time - process_time).total_seconds() / 3600  # 시간으로 변환
                    
                    if time_since_process >= 24:  # 24시간 이상 경과
                        if stock_code in pending_orders:
                            logger.info(f"{stock_code} - 처리 완료된 미체결 주문 기록 삭제 (처리 후 {time_since_process:.1f}시간 경과)")
                            del pending_orders[stock_code]
                except ValueError:
                    # 날짜 형식 오류가 있으면 바로 삭제
                    if stock_code in pending_orders:
                        del pending_orders[stock_code]
        
        # 상태 저장
        if canceled_orders or processed_orders:
            trading_state['pending_orders'] = pending_orders
            save_trading_state(trading_state)
            logger.info(f"미체결 주문 처리 완료: {len(canceled_orders)}개 취소, {len(processed_orders)}개 처리됨")
            
    except Exception as e:
        logger.error(f"미체결 주문 자동 취소 중 오류: {str(e)}")


def count_total_positions_for_fractional(trading_state):
    """
    분할 매수 전략용 포지션 카운트 함수 - 단계별 카운트 적용
    """
    try:
        # 기존 포지션 수 (각 종목은 하나의 포지션으로 카운트)
        held_positions = set(trading_state['positions'].keys())
        held_count = len(held_positions)
        
        # 미체결 주문 추적 정보
        pending_orders = trading_state.get('pending_orders', {})
        
        # API를 통한 미체결 주문 조회
        open_orders = KisKR.GetOrderList(
            side="BUY",
            status="OPEN",  # 미체결 주문만 조회
            limit=10  # 최대 10개까지 조회
        )
        
        # 미체결 주문 중인 종목 코드 목록
        pending_stocks = set()
        if open_orders and isinstance(open_orders, list):
            for order in open_orders:
                stock_code = order.get('OrderStock')
                if stock_code:
                    pending_stocks.add(stock_code)
                    # 미체결 주문 정보를 trading_state에 저장
                    if stock_code not in pending_orders:
                        pending_orders[stock_code] = {
                            'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'order_price': float(order.get('OrderAvgPrice', '0')),
                            'order_amount': int(order.get('OrderAmt', 0)),
                            'order_id': order.get('OrderNum', '')
                        }
        
        # 펜딩 주문 정보 업데이트
        trading_state['pending_orders'] = pending_orders
        
        # 보유 종목 중에 없는 미체결 주문 종목만 카운트 (중복 방지)
        unique_pending_stocks = pending_stocks - held_positions
        pending_count = len(unique_pending_stocks)
        
        # 총 포지션 수 계산 (기본)
        raw_count = held_count + pending_count
        
        # === 분할 매수를 위한 추가 계산 ===
        # 실제 총 포지션 수 (종목 별 단계가 최대인 경우를 제외)
        available_slots = 0
        for stock_code, position in trading_state.get('positions', {}).items():
            current_stage = position.get('buy_stage', MAX_BUY_STAGES)
            
            # 최대 단계에 도달하지 않은 경우, 해당 종목은 추가 매수 가능
            if current_stage < MAX_BUY_STAGES:
                # 쿨다운 체크
                last_buy_time = position.get('last_buy_time')
                if last_buy_time:
                    last_buy_datetime = datetime.strptime(last_buy_time, '%Y-%m-%d %H:%M:%S')
                    time_since_last_buy = (datetime.now() - last_buy_datetime).total_seconds()
                    
                    # 쿨다운 시간이 지났으면 추가 매수 가능
                    if time_since_last_buy >= FRACTIONAL_BUY_COOLDOWN:
                        available_slots += 1
        
        # 단계를 고려한 총 포지션 수 = 총 종목 수 - 추가 매수 가능한 슬롯 수
        adjusted_count = raw_count - available_slots
        
        logger.info(f"포지션 카운트: 보유 {held_count}개 + 미체결 {pending_count}개 = 총 {raw_count}개")
        logger.info(f"분할매수 고려: 추가 매수 가능 슬롯 {available_slots}개, 조정된 포지션 수 {adjusted_count}개")
        
        # 분할 매수 로직을 위한 상세 정보 반환
        return held_count, pending_count, adjusted_count, available_slots
        
    except Exception as e:
        logger.error(f"포지션 카운트 중 에러: {str(e)}")
        # 에러 발생 시 안전한 값 반환
        return len(trading_state.get('positions', {})), 0, len(trading_state.get('positions', {})), 0


def wait_for_order_execution(stock_code, order_amount, max_wait_time=45, order_type="BUY", order_price=None):
    """주문 체결을 안전하게 기다리는 함수 - 체결가 오차 허용 버전"""
    start_time = time.time()
    order_side = "BUY" if order_type == "BUY" else "SELL"
    stock_name = KisKR.GetStockName(stock_code)
    
    logger.info(f"{stock_name}({stock_code}) {order_type} 주문 체결 대기... 주문량: {order_amount}주")
    executed_amount = 0
    executed_price = 0
    
    # 시작 시점의 보유 수량 확인
    initial_position = None
    try:
        my_stocks = KisKR.GetMyStockList()
        for stock in my_stocks:
            if stock['StockCode'] == stock_code:
                initial_position = stock
                break
    except Exception as e:
        logger.error(f"초기 보유 수량 확인 중 오류: {str(e)}")
    
    initial_amount = int(initial_position.get('StockAmt', 0)) if initial_position else 0
    logger.info(f"{stock_name}({stock_code}) 초기 보유 수량: {initial_amount}주")
    
    # 상태 확인 최대 시도 횟수
    max_check_attempts = 8  # 시도 횟수 증가
    current_check = 0
    
    while time.time() - start_time < max_wait_time and current_check < max_check_attempts:
        try:
            current_check += 1
            
            # 1. API를 통한 체결 확인 시도
            order_details = KisKR.GetOrderList(
                stockcode=stock_code,
                side=order_side,
                status="CLOSE",  # 체결된 주문만 조회
                limit=10  # 더 많은 주문 기록 확인
            )
            
            if order_details:
                # 최근 60초 이내 체결된 주문 필터링 및 확인
                current_time = time.time()
                recent_orders = []
                
                for order in order_details:
                    order_date_str = order.get('OrderDate', '')
                    order_time_str = order.get('OrderTime', '')
                    
                    if order_date_str and order_time_str:
                        try:
                            order_datetime_str = f"{order_date_str} {order_time_str}"
                            order_timestamp = time.mktime(
                                datetime.strptime(
                                    order_datetime_str, 
                                    "%Y%m%d %H%M%S"
                                ).timetuple()
                            )
                            
                            if current_time - order_timestamp <= 120:  # 2분으로 확장
                                recent_orders.append(order)
                        except Exception as e:
                            logger.warning(f"주문 시간 변환 중 오류: {e}")
                
                # 체결 주문 확인 - 수량이 일치하거나 유사한 주문 찾기
                for order in recent_orders:
                    if (order.get('OrderStock') == stock_code and 
                        order.get('OrderStatus') == 'Close' and
                        order.get('OrderSide') == ('Buy' if order_type == "BUY" else 'Sell')):
                        
                        # 체결 정보 확인 - 수량 유사성 확인
                        order_amt = int(order.get('OrderAmt', 0))
                        # 주문 수량의 50% 이상 또는 절대 수량이 거의 일치하면 인정
                        if order_amt >= order_amount * 0.5 or abs(order_amt - order_amount) <= 2:
                            executed_price = float(order.get('OrderAvgPrice', 0))
                            executed_amount = order_amt
                            
                            if executed_price > 0 and executed_amount > 0:
                                logger.info(f"{stock_name}({stock_code}) {order_type} 주문 체결 확인: {executed_amount}주 @ {executed_price:,.0f}원")
                                return executed_price, executed_amount
            
            # 2. 계좌 데이터로 확인 - 이 부분을 더 강화
            current_stocks = KisKR.GetMyStockList()
            for stock in current_stocks:
                if stock['StockCode'] == stock_code:
                    current_amount = int(stock.get('StockAmt', 0))
                    
                    # 보유 수량 변화 감지 - 여기가 핵심 수정 부분
                    if order_type == "BUY":
                        if current_amount > initial_amount:
                            changed_amount = current_amount - initial_amount
                            
                            # 변경: 주문량과 실제 변화량 비교 로직 추가
                            if changed_amount != order_amount:
                                logger.warning(f"주문 수량({order_amount}주)과 실제 변화량({changed_amount}주)이 다릅니다!")
                                
                                # 실제 주문된 수량(order_amount)과 변화량 비교
                                # 만약 변화량이 주문량보다 적으면 부분 체결로 간주
                                if changed_amount < order_amount:
                                    logger.info(f"부분 체결로 판단됨: {changed_amount}주 (주문: {order_amount}주)")
                                # 만약 변화량이 주문량보다 많으면, 예상치 못한 상황이므로 로그 기록
                                elif changed_amount > order_amount:
                                    logger.warning(f"예상보다 많은 수량 체결됨: {changed_amount}주 (주문: {order_amount}주)")
                            
                            # 체결가 결정 - 다양한 소스에서 가장 신뢰할 수 있는 것 선택
                            # 1. 평균단가 (가능한 경우)
                            avg_price = float(stock.get('AvrPrice', 0))
                            
                            # 2. 현재가 (API에서)
                            current_market_price = KisKR.GetCurrentPrice(stock_code)
                            
                            # 3. 호가 정보 (더 정확한 체결가를 위해)
                            order_book = KisKR.GetOrderBook(stock_code)
                            best_price = 0
                            if order_book and 'levels' in order_book and len(order_book['levels']) > 0:
                                best_price = order_book['levels'][0]['ask_price']  # 최우선매도호가
                            
                            # 체결가 결정 로직
                            if avg_price > 0:
                                price_to_use = avg_price
                                logger.info(f"체결가 결정: 계좌 평균단가 기준 ({avg_price:,.0f}원)")
                            elif best_price > 0:
                                price_to_use = best_price
                                logger.info(f"체결가 결정: 호가 기준 ({best_price:,.0f}원)")
                            elif order_price is not None and order_price > 0:
                                price_to_use = order_price
                                logger.info(f"체결가 결정: 지정가 기준 ({order_price:,.0f}원)")
                            else:
                                price_to_use = current_market_price
                                logger.info(f"체결가 결정: 현재가 기준 ({current_market_price:,.0f}원)")
                            
                            # 중요: 실제 변화된 수량 반환 (주문량 아님)
                            logger.info(f"{stock_name}({stock_code}) {order_type} 주문 체결 확인 (계좌 데이터 기반): {changed_amount}주 @ {price_to_use:,.0f}원")
                            
                            # 체결 정보를 로그에 더 자세히 기록
                            if changed_amount == order_amount:
                                logger.info(f"{stock_name}({stock_code}) - 완전 체결: 주문량({order_amount}주) = 체결량({changed_amount}주)")
                            else:
                                logger.info(f"{stock_name}({stock_code}) - 부분 체결: 주문량({order_amount}주) vs 체결량({changed_amount}주)")
                            
                            return price_to_use, changed_amount
                    else:  # SELL
                        if current_amount < initial_amount:
                            changed_amount = initial_amount - current_amount
                            
                            # 변경: 주문량과 실제 변화량 비교 로직 추가
                            if changed_amount != order_amount:
                                logger.warning(f"주문 수량({order_amount}주)과 실제 변화량({changed_amount}주)이 다릅니다!")
                                
                                # 실제 주문된 수량(order_amount)과 변화량 비교
                                if changed_amount < order_amount:
                                    logger.info(f"부분 체결로 판단됨: {changed_amount}주 (주문: {order_amount}주)")
                                elif changed_amount > order_amount:
                                    logger.warning(f"예상보다 많은 수량 체결됨: {changed_amount}주 (주문: {order_amount}주)")
                            
                            # 체결가 결정 로직 (매도 버전)
                            # 현재가 및 호가 정보 가져오기
                            current_market_price = KisKR.GetCurrentPrice(stock_code)
                            order_book = KisKR.GetOrderBook(stock_code)
                            best_price = 0
                            if order_book and 'levels' in order_book and len(order_book['levels']) > 0:
                                best_price = order_book['levels'][0]['bid_price']  # 최우선매수호가
                            
                            # 체결가 결정
                            if best_price > 0:
                                price_to_use = best_price
                                logger.info(f"체결가 결정: 호가 기준 ({best_price:,.0f}원)")
                            elif current_market_price > 0:
                                price_to_use = current_market_price
                                logger.info(f"체결가 결정: 현재가 기준 ({current_market_price:,.0f}원)")
                            elif order_price is not None and order_price > 0:
                                price_to_use = order_price
                                logger.info(f"체결가 결정: 지정가 기준 ({order_price:,.0f}원)")
                            else:
                                # 기본값 (최후의 수단)
                                price_to_use = order_price if order_price else current_price
                                logger.info(f"체결가 결정: 기본값 사용 ({price_to_use:,.0f}원)")

                            # 상세 로깅 추가
                            logger.info(f"""
                        매도 가격 상세 정보:
                        - 최우선매수호가: {best_price:,.0f}원
                        - 현재가: {current_market_price:,.0f}원
                        - 최종 체결가: {price_to_use:,.0f}원
                        """)

                            logger.info(f"{stock_name}({stock_code}) {order_type} 주문 체결 확인 (계좌 데이터 기반): {changed_amount}주 @ {price_to_use:,.0f}원")
                            return price_to_use, changed_amount
                    
                    # 변화가 없는 경우 로그 기록
                    logger.info(f"{stock_name}({stock_code}) 보유수량 변화 없음: {current_amount}주 (초기: {initial_amount}주)")
            
            # 주기적인 대기 메시지 출력
            elapsed = time.time() - start_time
            if int(elapsed) % 5 == 0 and elapsed > 0:
                logger.info(f"{stock_name}({stock_code}) {order_type} 주문 체결 대기 중... ({int(elapsed)}초/{max_wait_time}초)")
            
            # API 호출 빈도 조절
            sleep_time = 2 if elapsed < 10 else 3
            time.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"{order_type} 주문 상태 확인 중 에러: {str(e)}")
            time.sleep(2)
    
    # 최종 확인 - 대기 시간 종료 후 마지막 시도
    logger.warning(f"{stock_name}({stock_code}) {order_type} 주문 체결 확인 제한 도달 ({max_wait_time}초/{max_check_attempts}회)")
    
    try:
        # 최종 계좌 상태 확인
        final_stocks = KisKR.GetMyStockList()
        for stock in final_stocks:
            if stock['StockCode'] == stock_code:
                final_amount = int(stock.get('StockAmt', 0))
                
                if (order_type == "BUY" and final_amount > initial_amount) or \
                   (order_type == "SELL" and final_amount < initial_amount):
                    
                    # 매수/매도에 따른 수량 변화 계산
                    if order_type == "BUY":
                        changed_amount = final_amount - initial_amount
                    else:  # SELL
                        changed_amount = initial_amount - final_amount
                    
                    # 주문량과 실제 변화량 차이 로깅
                    if changed_amount != order_amount:
                        logger.warning(f"최종 확인: 주문량({order_amount}주)과 실제 변화량({changed_amount}주) 불일치!")
                    
                    # 가격 정보 확보 (다양한 소스에서)
                    # 1. 호가 정보 가져오기
                    order_book = None
                    try:
                        order_book = KisKR.GetOrderBook(stock_code)
                    except:
                        pass
                        
                    best_price = 0
                    if order_book and 'levels' in order_book and len(order_book['levels']) > 0:
                        if order_type == "BUY":
                            best_price = order_book['levels'][0]['ask_price']  # 최우선매도호가
                        else:  # SELL
                            best_price = order_book['levels'][0]['bid_price']  # 최우선매수호가
                    
                    # 2. 평균가 가져오기
                    avg_price = float(stock.get('AvrPrice', 0))
                    
                    # 3. 현재가 가져오기
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    
                    # 최종 가격 결정 로직
                    if best_price > 0:
                        price_to_use = best_price
                        logger.info(f"최종 확인: 호가 기반 체결가 사용 - {changed_amount}주 @ {price_to_use:,.0f}원")
                    elif order_price is not None and order_price > 0:
                        price_to_use = order_price
                        logger.info(f"최종 확인: 지정가 기반 체결가 사용 - {changed_amount}주 @ {price_to_use:,.0f}원")
                    elif avg_price > 0:
                        price_to_use = avg_price
                        logger.info(f"최종 확인: 평균가 기반 체결가 사용 - {changed_amount}주 @ {price_to_use:,.0f}원")
                    else:
                        price_to_use = current_price
                        logger.info(f"최종 확인: 현재가 기반 체결가 사용 - {changed_amount}주 @ {price_to_use:,.0f}원")
                    
                    return price_to_use, changed_amount
                else:
                    logger.info(f"{stock_name}({stock_code}) 최종 보유수량 확인: {final_amount}주 (초기: {initial_amount}주) - 변화 없음")
    
    except Exception as e:
        logger.error(f"체결 상태 최종 확인 중 오류: {str(e)}")
    
    # 여기에 도달하면 체결 확인에 실패한 것
    return 0, 0

############### 고위험 매수 방지를 위한 함수 추가 ###################

def check_upper_circuit_condition(stock_code, stock_data):
    """
    상한가 근처 종목 체크 - 매수 주문 시 위험 방지
    
    Args:
        stock_code (str): 종목코드
        stock_data (dict): 종목 데이터
        
    Returns:
        bool: True면 상한가 근처가 아님(매수 가능), False면 상한가 근처(매수 제한)
    """
    try:
        # 현재가 및 전일종가 확인
        current_price = stock_data['current_price']
        prev_close = stock_data['prev_close']
        
        # 상한가 계산 (한국 시장 상한가는 일반적으로 전일 종가의 30%)
        theoretical_upper_limit = prev_close * 1.3
        
        # 상한가 근처 판단 (상한가의 95% 이상)
        upper_circuit_threshold = theoretical_upper_limit * 0.95
        
        # 상한가 근접 여부 체크
        is_near_upper_circuit = current_price >= upper_circuit_threshold
        
        # 최근 급격한 상승 여부 체크 (10% 이상 상승)
        price_increase_rate = ((current_price - prev_close) / prev_close) * 100
        is_rapid_increase = price_increase_rate >= 10
        
        # 호가 정보 가져오기 (매수/매도 잔량 확인)
        order_book = KisKR.GetOrderBook(stock_code)
        bid_ask_imbalance = False
        
        if order_book:
            total_bid = order_book['total_bid_rem']
            total_ask = order_book['total_ask_rem']
            
            # 매도 잔량이 매우 적은 경우 (매수 잔량의 10% 미만)
            if total_ask > 0 and total_bid / total_ask > 10:
                bid_ask_imbalance = True
        
        # 로깅
        logger.info(f"\n상한가 근접 체크 ({stock_code}):")
        logger.info(f"- 현재가: {current_price:,.0f}원, 전일종가: {prev_close:,.0f}원")
        logger.info(f"- 상한가 이론치: {theoretical_upper_limit:,.0f}원")
        logger.info(f"- 상한가 근접도: {(current_price/theoretical_upper_limit)*100:.1f}%")
        logger.info(f"- 금일 상승률: {price_increase_rate:.1f}%")
        if order_book:
            logger.info(f"- 호가 불균형: 매수잔량 {total_bid:,}주, 매도잔량 {total_ask:,}주")
        
        # 상한가 근처이거나 급등중이거나 호가 불균형이 있으면 매수 제한
        if is_near_upper_circuit or (is_rapid_increase and bid_ask_imbalance):
            logger.info(f"⚠️ 상한가 근접 또는 급등으로 매수 제한 ({price_increase_rate:.1f}% 상승)")
            
            # 캐시 이용하여 알림 중복 방지
            cache_key = f"{stock_code}_upper_circuit_alert"
            cache_manager = CacheManager.get_instance()
            
            if not cache_manager.get('discord_price_alerts', cache_key):
                stock_name = KisKR.GetStockName(stock_code)
                msg = f"⚠️ 상한가 근접 매수 제한: {stock_name}({stock_code})\n"
                msg += f"- 현재가: {current_price:,}원 (상한가의 {(current_price/theoretical_upper_limit)*100:.1f}%)\n"
                msg += f"- 금일 상승률: {price_increase_rate:.1f}%\n"
                msg += f"- 사유: 급등 종목 지연 체결 위험"
                
                discord_alert.SendMessage(msg)
                cache_manager.set('discord_price_alerts', cache_key, True)
                
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"상한가 체크 중 에러: {str(e)}")
        # 에러 발생 시 안전하게 매수 불가 반환
        return False


def check_buy_order_suitability(stock_code, buy_amount, stock_data):
    """
    매수 주문 적합성 최종 확인 함수 - 개선버전
    - 오전장에 한해 모멘텀 점수가 높은 종목은 상승률 제한 완화
    """
    try:
        stock_name = KisKR.GetStockName(stock_code)
        
        # 1. 현재가 재확인
        current_price = KisKR.GetCurrentPrice(stock_code)
        prev_close = stock_data.get('prev_close', 0)
        
        # 현재 시간대 확인
        is_early_morning = is_in_early_morning_session()
        is_morning_session = is_in_morning_session()
        
        # 2. 당일 상승률 체크
        if prev_close > 0:
            price_increase_rate = ((current_price - prev_close) / prev_close) * 100
            
            # 시간대별 허용 가능 상승률 차등 적용
            if is_early_morning:
                base_max_allowed_rise = 7.0  # 오전 9시대: 7% 초과 상승 시 매수 제한
            elif is_morning_session:
                base_max_allowed_rise = 8.5  # 오전장: 8.5% 초과 상승 시 매수 제한
            else:
                base_max_allowed_rise = 10.0  # 일반 시간대: 10% 초과 상승 시 매수 제한
            
            # 초기값 설정
            max_allowed_rise = base_max_allowed_rise
                
            # === 새로운 코드: 오전장 한정 모멘텀 기반 예외 처리 ===
            should_apply_exception = False
            exception_reason = ""
            
            # 오전장에만 예외 적용
            if is_morning_session:
                # 모멘텀 점수 확인
                momentum_score = 0
                if 'momentum_score' in stock_data:
                    momentum_score = stock_data['momentum_score']
                    
                # MACD 신호 강도 계산
                macd_signal_strength = 0
                if ('macd' in stock_data and 'macd_signal' in stock_data and 
                    'prev_macd' in stock_data):
                    macd = stock_data['macd']
                    macd_signal = stock_data['macd_signal']
                    prev_macd = stock_data['prev_macd']
                    
                    if macd > macd_signal and macd > prev_macd:
                        macd_diff = abs((macd - macd_signal) / macd_signal) if macd_signal != 0 else 0
                        macd_change = abs((macd - prev_macd) / prev_macd) if prev_macd != 0 else 0
                        macd_signal_strength = min(10, (macd_diff * 100 + macd_change * 100) / 20)
                
                # 거래량 품질 점수 계산
                volume_quality = 0
                if 'volume' in stock_data and 'volume_ma5' in stock_data:
                    volume_ratio = stock_data['volume'] / stock_data['volume_ma5']
                    volume_quality = min(10, volume_ratio * 5)
                
                # 예외 조건 1: 매우 높은 모멘텀 점수 (오전장에는 더 큰 완화 적용)
                if momentum_score >= 75:
                    max_allowed_rise *= 2.5  # 오전장에는 2.5배로 더 크게 완화
                    should_apply_exception = True
                    exception_reason = f"매우 높은 모멘텀 점수({momentum_score}) 기반 예외"
                elif momentum_score >= 65:
                    max_allowed_rise *= 2.0  # 오전장에는 2배로 완화
                    should_apply_exception = True
                    exception_reason = f"높은 모멘텀 점수({momentum_score}) 기반 예외"
                elif momentum_score >= 60:
                    max_allowed_rise *= 1.5  # 오전장에는 1.5배로 완화
                    should_apply_exception = True
                    exception_reason = f"모멘텀 점수({momentum_score}) 기반 예외"
                
                # 예외 조건 2: 매우 강한 MACD 신호 (오전장에만 적용)
                if macd_signal_strength >= 8:
                    max_allowed_rise = max(max_allowed_rise, base_max_allowed_rise * 2.5)
                    should_apply_exception = True
                    exception_reason = f"매우 강한 MACD 신호({macd_signal_strength:.1f}/10) 기반 예외"
                elif macd_signal_strength >= 6:
                    max_allowed_rise = max(max_allowed_rise, base_max_allowed_rise * 2.0)
                    should_apply_exception = True
                    exception_reason = f"강한 MACD 신호({macd_signal_strength:.1f}/10) 기반 예외"
                
                # 예외 조건 3: 장 초반(9시대)에는 추가 완화
                if is_early_morning and momentum_score >= 55:
                    max_allowed_rise *= 1.2  # 추가 20% 완화
                    exception_reason += " + 장 초반 추가 완화"
            else:
                # 오전장이 아닌 경우 기본값 사용
                logger.info(f"오전장이 아닌 시간대 - 기본 상승률 제한 적용: {max_allowed_rise:.1f}%")
            
            # 예외 적용 시 로그 출력
            if should_apply_exception:
                logger.info(f"✨ 오전장 상승률 제한 완화 적용: {exception_reason}")
                logger.info(f"   기존 제한: {base_max_allowed_rise:.1f}% → 변경: {max_allowed_rise:.1f}%")
            
            # 최종 상승률 검증
            if price_increase_rate > max_allowed_rise:
                reason = f"당일 상승률 과다 ({price_increase_rate:.1f}% > {max_allowed_rise:.1f}%)"
                logger.info(f"⚠️ {stock_name}({stock_code}) 매수 부적합: {reason}")
                return False, reason
            else:
                logger.info(f"✅ 당일 상승률 적합: {price_increase_rate:.1f}% <= {max_allowed_rise:.1f}%")
            
            # === 새로운 코드 끝 ===
            
            # 추가: 상승률 대비 거래량 확인 (이 부분은 전체 시간대에 적용)
            volume_ratio = stock_data.get('volume', 0) / stock_data.get('volume_ma5', 1)
            if price_increase_rate > 5.0 and volume_ratio < 1.0:
                reason = f"상승률 대비 거래량 부족 (상승률: {price_increase_rate:.1f}%, 거래량: {volume_ratio:.2f}배)"
                logger.info(f"⚠️ {stock_name}({stock_code}) 매수 부적합: {reason}")
                return False, reason
        
        # 기존 코드는 그대로 유지...
        
        # 모든 조건 통과
        logger.info(f"✅ {stock_name}({stock_code}) 매수 적합 판정")
        return True, "매수 적합"
        
    except Exception as e:
        logger.error(f"매수 적합성 확인 중 에러: {str(e)}")
        return False, f"오류 발생: {str(e)}"


def check_delayed_execution_risk(stock_code, stock_data):
    """
    체결 지연 위험 평가 함수
    - 매수 주문과 실제 체결 간 지연 위험이 높은 종목 식별
    
    Args:
        stock_code (str): 종목 코드
        stock_data (dict): 종목 데이터
        
    Returns:
        tuple: (risk_level, message) - risk_level: 0(낮음), 1(중간), 2(높음)
    """
    try:
        # 현재 시간 체크
        now = datetime.now()
        is_morning_session = is_in_morning_session()
        
        # 위험 평가 점수 (0: 안전, 10: 매우 위험)
        risk_score = 0
        risk_factors = []
        
        # 1. 거래량 급증 체크
        volume_ratio = stock_data['volume'] / stock_data['volume_ma5']
        if volume_ratio > 3.0:
            risk_score += 2
            risk_factors.append(f"거래량 급증 (5일평균 대비 {volume_ratio:.1f}배)")
        
        # 2. 가격 급등 체크
        price_change = ((stock_data['current_price'] - stock_data['prev_close']) / stock_data['prev_close']) * 100
        if price_change > 15.0:
            risk_score += 3
            risk_factors.append(f"가격 급등 ({price_change:.1f}%)")
        elif price_change > 8.0:
            risk_score += 2
            risk_factors.append(f"가격 상승 ({price_change:.1f}%)")
        
        # 3. 시간대 리스크 (장 초반 15분은 변동성 크고 체결 지연 위험 높음)
        market_open_time = datetime(now.year, now.month, now.day, 9, 0, 0)
        minutes_since_open = (now - market_open_time).total_seconds() / 60
        
        if 0 <= minutes_since_open <= 15:
            risk_score += 3
            risk_factors.append(f"장 초반 변동성 구간 (시작 후 {minutes_since_open:.0f}분)")
        
        # 4. 호가 불균형 체크
        order_book = KisKR.GetOrderBook(stock_code)
        if order_book:
            total_bid = order_book['total_bid_rem']
            total_ask = order_book['total_ask_rem']
            
            if total_ask > 0 and total_bid / total_ask > 5:
                risk_score += 2
                risk_factors.append(f"호가 불균형 (매수/매도 잔량비 {total_bid/total_ask:.1f}배)")
        
        # 위험도 레벨 결정
        if risk_score >= 6:
            risk_level = 2  # 높음
            risk_message = "체결 지연 위험 높음"
        elif risk_score >= 3:
            risk_level = 1  # 중간
            risk_message = "체결 지연 위험 중간"
        else:
            risk_level = 0  # 낮음
            risk_message = "체결 지연 위험 낮음"
        
        # 상세 메시지 구성
        detailed_message = f"{risk_message} (점수: {risk_score}/10)\n- " + "\n- ".join(risk_factors)
        
        # 로깅
        logger.info(f"\n체결 지연 위험 평가 ({stock_code}):")
        logger.info(f"- 위험도: {risk_level} ({risk_message})")
        logger.info(f"- 위험 점수: {risk_score}/10")
        for factor in risk_factors:
            logger.info(f"- {factor}")
        
        return risk_level, detailed_message
        
    except Exception as e:
        logger.error(f"체결 지연 위험 평가 중 에러: {str(e)}")
        return 2, f"오류 발생으로 안전하게 높은 위험도 반환: {str(e)}"

def cancel_existing_orders(stock_code):
    """주어진 종목의 미체결 주문을 취소"""
    try:
        # 미체결 주문 조회
        open_orders = KisKR.GetOrderList(
            stockcode=stock_code,
            side="BUY",
            status="OPEN"
        )
        
        cancel_count = 0
        # 미체결 주문 취소
        for order in open_orders:
            if order.get('OrderStock') == stock_code:
                order_id = order.get('OrderNum')
                cancel_result = cancel_order(order_id)
                if cancel_result:
                    cancel_count += 1
                    logger.info(f"{stock_code} 미체결 주문 취소 성공: 주문번호 {order_id}")
                else:
                    logger.error(f"{stock_code} 미체결 주문 취소 실패: 주문번호 {order_id}")
                    
        if cancel_count > 0:
            logger.info(f"{stock_code}의 미체결 주문 {cancel_count}개 취소 완료")
            
        return cancel_count > 0
        
    except Exception as e:
        logger.error(f"미체결 주문 취소 중 에러: {str(e)}")
        return False


def handle_buy_order_with_safety(stock_code, stock_name, buy_amount, stock_price, stock_data, trading_state=None):
    """
    분할매수 기능이 추가된 안전 지정가 매수 처리 함수 - 개선버전
    """
    try:
        # 트레이딩 상태 로드
        if trading_state is None:
            trading_state = load_trading_state()

        # 매수량 초기화
        original_amount = buy_amount  # 원래 계획 수량
        current_order_amount = buy_amount  # 현재 주문할 수량 (분할매수에 따라 변경됨)

        # 분할매수 로직 적용
        if ENABLE_FRACTIONAL_BUY:
            # 이미 보유 중인 종목인지 확인
            if stock_code in trading_state.get('positions', {}):
                position = trading_state['positions'][stock_code]
                
                # 현재 매수 단계 확인 (기본값 1로 설정)
                current_stage = position.get('buy_stage', 1)
                
                # 마지막 매수 시간 확인
                last_buy_time = position.get('last_buy_time')
                current_time = datetime.now()
                
                # 최대 매수 단계 도달 여부 확인
                if current_stage >= MAX_BUY_STAGES:
                    logger.info(f"{stock_name}({stock_code}) - 이미 최대 매수 단계({current_stage}/{MAX_BUY_STAGES})에 도달했습니다.")
                    return None, "최대 매수 단계 도달", 0
                
                # 쿨다운 체크
                if last_buy_time:
                    last_buy_datetime = datetime.strptime(last_buy_time, '%Y-%m-%d %H:%M:%S')
                    time_since_last_buy = (current_time - last_buy_datetime).total_seconds()
                    
                    # 쿨다운 시간 이내면 추가 매수 불가
                    if time_since_last_buy < FRACTIONAL_BUY_COOLDOWN:
                        cooldown_remaining = (FRACTIONAL_BUY_COOLDOWN - time_since_last_buy) / 60
                        logger.info(f"{stock_name}({stock_code}) - 분할매수 쿨다운 중 (남은 시간: {cooldown_remaining:.1f}분)")
                        return None, "분할매수 쿨다운", 0

                # 매우 적은 수량(2-3주)의 경우 특별 처리
                total_planned_amount = position.get('total_planned_amount', original_amount)

                logger.info(f"""
                분할매수 상세 정보:
                - 원본 수량: {original_amount}주
                - 현재 매수 단계: {current_stage}
                - 총 계획 수량: {total_planned_amount}주
                """)

                if total_planned_amount <= 3:
                    buy_amount = 1  # 각 단계에서 1주씩 매수
                    current_order_amount = buy_amount  # 현재 주문량도 동기화
                    logger.info(f"적은 수량({total_planned_amount}주) 특별 처리: 1주 매수")
                else:
                    # 각 단계별로 total_planned_amount의 일정 비율로 매수량 계산
                    # current_stage는 현재까지 완료한 단계, 즉 다음에 진행할 단계의 직전 단계
                    if current_stage == 1:
                        # 2단계 매수 - 총 계획 수량의 SECOND_BUY_RATIO(33%) 매수
                        buy_amount = int(total_planned_amount * SECOND_BUY_RATIO)
                        next_stage = 2
                        logger.info(f"2단계 매수: {buy_amount}주 (총 계획 수량 {total_planned_amount}주의 {SECOND_BUY_RATIO*100:.0f}%)")
                    elif current_stage == 2:
                        # 3단계 매수 - 총 계획 수량의 THIRD_BUY_RATIO(34%) 매수
                        buy_amount = int(total_planned_amount * THIRD_BUY_RATIO)
                        next_stage = 3
                        logger.info(f"3단계 매수: {buy_amount}주 (총 계획 수량 {total_planned_amount}주의 {THIRD_BUY_RATIO*100:.0f}%)")
                    else:
                        # 이미 최대 단계에 도달
                        logger.info(f"이미 최대 매수 단계({current_stage}/{MAX_BUY_STAGES})에 도달했습니다.")
                        return None, "최대 매수 단계 도달", 0
                    current_order_amount = buy_amount  # current_order_amount를 계산된 buy_amount로 업데이트                        
                    # 최소 1주 보장
                    buy_amount = max(1, buy_amount)
                    logger.info(f"최종 매수 수량: {buy_amount}주")
            else:
                # 신규 매수인 경우, 1단계 매수 수량 계산
                current_order_amount = int(original_amount * FIRST_BUY_RATIO)
                next_stage = 1
                logger.info(f"{stock_name}({stock_code}) - 분할매수 1단계 진행: {current_order_amount}주 (원래 계획: {original_amount}주)")
        else:
            # 분할매수 비활성화 상태면 원래 수량 그대로 사용
            next_stage = 1

        # 최소 1주 보장
        current_order_amount = max(1, current_order_amount)
        
        # 1. 매수 적합성 최종 확인
        is_suitable, suitability_message = check_buy_order_suitability(stock_code, current_order_amount, stock_data)
        if not is_suitable:
            error_msg = f"{stock_name}({stock_code}) - 매수 부적합 판정: {suitability_message}"
            logger.info(error_msg)
            
            # 해당 종목의 미체결 주문이 있다면 취소
            cancel_existing_orders(stock_code)
            
            return None, error_msg, 0
        
        # 매수 직전 한 번 더 RSI 체크
        current_data = get_stock_data(stock_code)
        if current_data and current_data['rsi'] > MAX_BUY_RSI:
            error_msg = f"매수 직전 RSI 재확인: 과매수 상태({current_data['rsi']:.1f})로 매수 취소"
            logger.info(f"{stock_name}({stock_code}) - {error_msg}")
            return None, error_msg, 0
            
        # 매수 직전 호가 상태 재확인
        is_favorable, _ = analyze_order_book(stock_code)
        if not is_favorable:
            error_msg = f"매수 직전 호가 재확인: 불리한 호가로 매수 취소"
            logger.info(f"{stock_name}({stock_code}) - {error_msg}")
            return None, error_msg, 0
        
        # 2. 체결 지연 위험 평가
        risk_level, risk_message = check_delayed_execution_risk(stock_code, stock_data)
        
        # 3. 위험 수준에 따른 주문 방식 조정
        original_risk_amount = current_order_amount  # 조정 전 수량 저장
        if risk_level == 2:  # 높은 위험
            logger.info(f"{stock_name}({stock_code}) - ⚠️ 체결 지연 고위험 감지: {risk_message}")
            
            # 주문 수량 조정 (절반으로 감소)
            adjusted_amount = max(1, current_order_amount // 2)
            if adjusted_amount < current_order_amount:
                logger.info(f"{stock_name}({stock_code}) - 체결 지연 위험으로 주문 수량 조정: {current_order_amount}주 → {adjusted_amount}주")
                current_order_amount = adjusted_amount  # 수량 재조정
            
            # 고위험 매수 알림
            msg = f"⚠️ 고위험 매수 진행 - {stock_name}({stock_code})\n"
            msg += f"- 수량: {current_order_amount}주 (위험으로 인한 감소)\n"
            msg += f"- 위험 요인: {risk_message}"
            discord_alert.SendMessage(msg)
        
        # 4. 적절한 지정가 설정
        limit_price = stock_price  # 기본값으로 현재가 사용
        order_book = KisKR.GetOrderBook(stock_code)
        if order_book and 'levels' in order_book and len(order_book['levels']) > 0:
            # 최우선 매도호가 확인
            best_ask_price = order_book['levels'][0]['ask_price']
            
            # 고점 근처 또는 상한가 근처 여부 확인
            is_near_high = False
            if 'ohlcv' in stock_data and stock_data['ohlcv'] is not None:
                daily_high = stock_data['ohlcv']['high'].max()
                high_ratio = (daily_high - stock_price) / stock_price * 100
                is_near_high = high_ratio < 0.5  # 고점과의 차이가 0.5% 미만이면 고점 근처로 판단
            
            # 상한가 계산 (단순 추정)
            prev_close = stock_data.get('prev_close', stock_price * 0.9)
            theoretical_upper_limit = prev_close * 1.3
            upper_proximity = (theoretical_upper_limit - stock_price) / stock_price * 100
            is_near_upper_limit = upper_proximity < 1.0  # 상한가와 1% 이내면 상한가 근처로 판단
            
            # 매수 가격 결정 로직 개선
            if is_near_high or is_near_upper_limit:
                # 고점이나 상한가 근처면 더 보수적으로 현재가에 매수
                limit_price = stock_price
                logger.info(f"고점 또는 상한가 근처 감지 - 현재가 기준 주문: {limit_price:,.0f}원")
            else:
                # 일반적인 경우 - 현재가와 최우선매도호가 사이의 가격 적용 (스프레드의 30%만 추가)
                if best_ask_price > stock_price:
                    spread = best_ask_price - stock_price
                    limit_price = stock_price + (spread * 0.3)  # 스프레드의 30%만 상승
                else:
                    limit_price = stock_price
            
            # 항상 현재가의 0.5% 이상 높지 않도록 제한
            limit_price = min(limit_price, stock_price * 1.005)            
            logger.info(f"주문 가격 결정: {limit_price:,.0f}원 (현재가: {stock_price:,.0f}원, 최우선매도호가: {best_ask_price:,.0f}원)")
        
        # 정수형 가격으로 변환
        int_limit_price = int(limit_price)
        
        # 주문 시작 전 주문 ID 생성 - 추적을 위해
        order_id = f"{stock_code}_{int(time.time())}"
        
        # 5. 지정가 매수 주문 실행
        logger.info(f"{stock_name}({stock_code}) - 지정가 매수 주문 실행: {current_order_amount}주 @ {int_limit_price:,}원")
        order_result = KisKR.MakeBuyLimitOrder(stock_code, current_order_amount, int_limit_price)
        
        # 주문 결과 유효성 검사 강화
        if isinstance(order_result, str) and ("Error" in order_result or "rt_cd" in order_result or "msg" in order_result):
            logger.error(f"{stock_name}({stock_code}) - 매수 주문 API 오류: {order_result}")
            return None, f"주문 API 오류: {order_result}", 0
            
        if not order_result:
            logger.error(f"{stock_name}({stock_code}) - 매수 주문 실패 (API 응답 없음)")
            return None, "주문 실패", 0

        # 미체결 주문 정보 미리 저장
        if 'pending_orders' not in trading_state:
            trading_state['pending_orders'] = {}
            
        trading_state['pending_orders'][stock_code] = {
            'order_id': order_id,
            'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'order_price': int_limit_price,
            'order_amount': current_order_amount,
            'total_planned_amount': original_amount,  # 분할매수를 위한 원래 계획 수량 저장
            'buy_stage': next_stage,  # 분할매수 단계 정보 추가
            'status': 'submitted',  # 주문 제출 상태
            'risk_level': risk_level
        }
        
        # 안전하게 상태 저장 (체결 확인 전)
        try:
            save_trading_state(trading_state)
            logger.info(f"{stock_name}({stock_code}) - 주문 정보 저장 완료 (주문ID: {order_id})")
        except Exception as e:
            logger.error(f"{stock_name}({stock_code}) - 주문 정보 저장 중 오류: {str(e)}")

        # 가격 재검증 코드 추가 ----------------
        # 주문 직후, 체결 대기 전 현재가 변동 체크
        initial_price = stock_price
        time.sleep(3)  # 잠시 대기 후 가격 재확인
        current_price_check = KisKR.GetCurrentPrice(stock_code)

        # 급격한 가격 하락 감지 (예: 1% 이상 하락)
        if current_price_check < initial_price * 0.99:
            logger.warning(f"{stock_name}({stock_code}) - ⚠️ 주문 직후 가격 급락 감지: {initial_price:,.0f}원 → {current_price_check:,.0f}원 ({((current_price_check/initial_price)-1)*100:.2f}%)")
            
            # 기존 주문 취소 시도
            cancel_result = cancel_existing_orders(stock_code)
            
            if cancel_result:
                # 취소 후 주문 상태 업데이트
                if stock_code in trading_state['pending_orders']:
                    trading_state['pending_orders'][stock_code]['status'] = 'canceled'
                    trading_state['pending_orders'][stock_code]['cancel_reason'] = '가격 급락'
                    trading_state['pending_orders'][stock_code]['cancel_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    save_trading_state(trading_state)
                    
                # 취소 후 재주문 여부 결정
                if current_price_check < int_limit_price:
                    logger.warning(f"{stock_name}({stock_code}) - 지정가({int_limit_price:,.0f}원)보다 현재가({current_price_check:,.0f}원)가 낮아 주문 취소")
                    
                    # 주문 취소 알림
                    msg = f"❌ 주문 취소: {stock_name}({stock_code})\n"
                    msg += f"- 사유: 주문 직후 가격 급락 감지\n"
                    msg += f"- 주문가: {int_limit_price:,}원\n"
                    msg += f"- 현재가: {current_price_check:,}원 ({((current_price_check/initial_price)-1)*100:.2f}%)"
                    discord_alert.SendMessage(msg)
                    
                    return None, "가격 급락으로 주문 취소", 0
        # 가격 재검증 코드 끝 -------------------------

        # 체결 대기 (시간 증가)
        logger.info(f"{stock_name}({stock_code}) - 체결 확인을 위해 10초 대기...")
        time.sleep(10)

        # 체결 대기 함수 호출 - 지정가 정보 전달
        executed_price, executed_amount = wait_for_order_execution(
            stock_code, 
            current_order_amount,
            max_wait_time=45,
            order_type="BUY",
            order_price=int_limit_price  # 지정가 정보 전달
        )
        
        # 체결 정보 검증
        if executed_amount <= 0 or executed_price <= 0:
            # 미체결 상태로 진행
            logger.info(f"{stock_name}({stock_code}) - 미체결 상태로 진행: {current_order_amount}주 @ {int_limit_price:,}원")
            
            # 미체결 주문 상태 업데이트
            if stock_code in trading_state['pending_orders']:
                trading_state['pending_orders'][stock_code].update({
                    'status': 'pending',  # 미체결 상태
                    'last_check_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                save_trading_state(trading_state)
            
            # 미체결 알림
            msg = f"⏳ 매수 주문 미체결 상태: {stock_name}({stock_code})\n"
            msg += f"- 수량: {current_order_amount:,}주 @ {int_limit_price:,}원\n"
            msg += f"- 주문은 시스템에 등록되었으며, 자동 취소 시간까지 체결을 기다립니다."
            logger.info(msg)
            discord_alert.SendMessage(msg)
            
            return None, "미체결", 0  # 명확하게 체결 실패 상태 반환

        # 체결된 경우 - 정확한 체결량 기준으로 처리
        logger.info(f"{stock_name}({stock_code}) - 체결 완료: 지정가 {int_limit_price:,}원 → 실제 체결가 {executed_price:.0f}원 (체결량: {executed_amount}주)")
        
        # 매수 수수료 계산 - 실제 체결량 기준
        buy_fee = calculate_trading_fee(executed_price, executed_amount, is_buy=True)

        # 포지션 상태 업데이트 시도
        try:
            # 트레이딩 상태 업데이트
            if 'positions' not in trading_state:
                trading_state['positions'] = {}
                
            # 체결 여부에 따라 미체결 주문 상태 업데이트
            if stock_code in trading_state['pending_orders']:
                # 일반 매수 체결
                trading_state['pending_orders'][stock_code].update({
                    'executed_amount': executed_amount,
                    'executed_price': executed_price,
                    'status': 'filled',
                    'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # 분할매수 로직 적용 - 이미 매수한 종목인 경우
            if ENABLE_FRACTIONAL_BUY and stock_code in trading_state.get('positions', {}):
                # 기존 포지션 정보 백업
                position = trading_state['positions'][stock_code]
                prev_amount = position['amount']
                prev_entry_price = position['entry_price']
                prev_fee = position.get('trading_fee', 0)
                
                # 새로운 평균 매수가 계산
                total_value = (prev_amount * prev_entry_price) + (executed_amount * executed_price)
                new_amount = prev_amount + executed_amount

                # 체결량이 0이 아닌 경우에만 새 평균가 계산 (0으로 나누기 방지)
                if new_amount > 0:
                    new_entry_price = total_value / new_amount
                else:
                    new_entry_price = executed_price
                
                # 수수료 합산
                total_fee = prev_fee + buy_fee
                
                # 포지션 정보 업데이트
                position.update({
                    'entry_price': new_entry_price,
                    'amount': new_amount,
                    'trading_fee': total_fee,
                    'buy_stage': next_stage,  # 매수 단계 업데이트
                    'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_planned_amount': original_amount  # 원래 계획 수량 저장/업데이트
                })
                
                logger.info(f"{stock_name}({stock_code}) - 포지션 업데이트 (분할매수 {next_stage}단계):")
                logger.info(f"- 이전: {prev_amount}주 @ {prev_entry_price:,.0f}원")
                logger.info(f"- 추가: {executed_amount}주 @ {executed_price:,.0f}원")
                logger.info(f"- 변경: {new_amount}주 @ {new_entry_price:,.0f}원")
            else:
                # 새로운 포지션 (첫 매수)
                trading_state['positions'][stock_code] = {
                    'entry_price': executed_price,
                    'amount': executed_amount,
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'trading_fee': buy_fee,
                    'code': stock_code,
                    'strategy': 'momentum_buy',
                    # 분할매수 정보 추가
                    'buy_stage': next_stage,
                    'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_planned_amount': original_amount
                }
                
                logger.info(f"{stock_name}({stock_code}) - 신규 포지션 생성:")
                logger.info(f"- 매수가: {executed_price:,.0f}원")
                logger.info(f"- 수량: {executed_amount}주")
                logger.info(f"- 수수료: {buy_fee:,.0f}원")
                logger.info(f"- 분할매수 단계: {next_stage}/{MAX_BUY_STAGES}")
            
            # 상태 저장 (중요: 트랜잭션 성공 확인)
            save_trading_state(trading_state)
            logger.info(f"{stock_name}({stock_code}) - 포지션 저장 완료")

        except Exception as e:
            # 포지션 저장 실패 시 상세 로깅 및 복구 시도
            logger.error(f"{stock_name}({stock_code}) - 포지션 저장 중 오류 발생: {str(e)}")
            logger.error(f"포지션 저장 실패 시 백업 로직 실행")
            
            # 백업 로직: 간단한 정보로 다시 시도
            try:
                # 단순화된 포지션 정보 저장
                trading_state['positions'][stock_code] = {
                    'entry_price': executed_price,
                    'amount': executed_amount,
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'trading_fee': buy_fee,
                    'code': stock_code,
                    'strategy': 'emergency_save',  # 비상 저장 표시
                    'buy_stage': next_stage  # 분할매수 단계 정보 포함
                }
                save_trading_state(trading_state)
                logger.info(f"{stock_name}({stock_code}) - 백업 포지션 저장 성공")
                
                # 알림 발송
                emergency_msg = f"⚠️ 포지션 저장 오류 발생 - 백업 저장 완료: {stock_name}({stock_code})"
                discord_alert.SendMessage(emergency_msg)
                
            except Exception as backup_e:
                logger.critical(f"{stock_name}({stock_code}) - 백업 저장도 실패! {str(backup_e)}")
                error_msg = f"⚠️ 심각한 포지션 저장 오류 - 수동 확인 필요: {stock_name}({stock_code})"
                discord_alert.SendMessage(error_msg)
        
        # 성공 메시지 출력
        msg = f"✅ 매수 주문 체결 완료!"
        msg += f"\n"
        msg += f"- 종목: {stock_name}({stock_code})\n"
        msg += f"- 수량: {executed_amount:,}주"
        if ENABLE_FRACTIONAL_BUY:
            msg += f" (분할매수 {next_stage}/{MAX_BUY_STAGES}단계)"
        msg += f"\n"
        msg += f"- 매수가: {int(executed_price):,}원\n"
        msg += f"- 거래비용: {int(buy_fee):,}원"
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 상태 파일의 유무 확인 (추가 안전 조치)
        try:
            # 파일 존재 여부 확인
            file_exists = os.path.exists(f"KrStock_{BOT_NAME}.json")
            if not file_exists:
                logger.critical(f"심각한 오류: 상태 파일이 존재하지 않습니다!")
                emergency_msg = f"⚠️ 상태 파일 없음 - 수동 개입 필요!"
                discord_alert.SendMessage(emergency_msg)
            else:
                # 파일 내용 확인
                try:
                    with open(f"KrStock_{BOT_NAME}.json", 'r') as f:
                        saved_state = json.load(f)
                    
                    if stock_code not in saved_state.get('positions', {}):
                        logger.critical(f"심각한 오류: 상태 파일에 방금 매수한 종목이 없습니다!")
                        emergency_msg = f"⚠️ 상태 파일에 매수 종목 누락 - 수동 개입 필요!"
                        discord_alert.SendMessage(emergency_msg)
                except:
                    logger.critical(f"심각한 오류: 상태 파일을 읽을 수 없습니다!")
                    emergency_msg = f"⚠️ 상태 파일 읽기 실패 - 수동 개입 필요!"
                    discord_alert.SendMessage(emergency_msg)
        except:
            # 파일 체크에서 오류가 발생해도 계속 진행
            pass
        
        return executed_price, None, executed_amount
        
    except Exception as e:
        # 주요 오류 발생 시 추가 정보 로깅 및 경고
        error_msg = f"매수 주문 처리 중 심각한 오류: {str(e)}"
        logger.error(error_msg)
        
        # 상태 파일 안전 확인
        try:
            # 트레이딩 상태 다시 로드해서 체크
            trading_state = load_trading_state()
            
            # API로 실제 보유 상태 확인
            my_stocks = KisKR.GetMyStockList()
            stock_in_account = any(s['StockCode'] == stock_code for s in my_stocks)
            
            # 보유 중인데 상태 파일에 없으면 비상 복구
            if stock_in_account and stock_code not in trading_state.get('positions', {}):
                logger.critical(f"비상 상황: 실제로 보유 중이지만 상태 파일에 없는 종목 감지 - {stock_code}")
                
                # 계좌 정보로 포지션 복구 시도
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        if 'positions' not in trading_state:
                            trading_state['positions'] = {}
                            
                        # 실제 평균가 확보 (API에서 직접)
                        actual_avg_price = float(stock.get('AvrPrice', 0))
                        
                        # 평균가가 없거나 0인 경우에만 대체값 사용
                        entry_price = actual_avg_price if actual_avg_price > 0 else stock_price
                            
                        # 긴급 포지션 정보 생성
                        trading_state['positions'][stock_code] = {
                            'entry_price': entry_price,
                            'amount': int(stock.get('StockAmt', 0)),
                            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'trading_fee': 0,  # 정확한 수수료는 알 수 없음
                            'code': stock_code,
                            'strategy': 'emergency_recovery',  # 비상 복구 표시
                            'buy_stage': 1  # 분할매수 단계 1로 설정
                        }
                        save_trading_state(trading_state)
                        
                        emergency_msg = f"⚠️ 비상 상황 - 상태 파일에 누락된 매수 종목 복구 완료: {stock_name}({stock_code})"
                        emergency_msg += f"\n- 실제 평균가: {entry_price:,.0f}원으로 복구"
                        discord_alert.SendMessage(emergency_msg)
                        break
        except Exception as recovery_e:
            logger.critical(f"비상 복구 중 추가 오류: {str(recovery_e)}")
        
        return None, str(e), 0

    
################## 고위험 매수 방지를 위한 함수 추가 끝 ########################    


def handle_buy_order(stock_code, stock_name, buy_amount, stock_price, stock_data=None, trading_state=None):

    """
    분할매수 기능이 추가된 지정가 매수 처리 함수 - 개선버전
    """
    try:
        # 트레이딩 상태 로드
        if trading_state is None:
            trading_state = load_trading_state()

        # 매수량 초기화
        original_amount = buy_amount  # 원래 계획 수량
        current_order_amount = buy_amount  # 현재 주문할 수량 (분할매수에 따라 변경됨)        

        # 0. 매수 수량이 10개를 초과하는 경우 반으로 줄임(기존동일)
        # if buy_amount > 10:
        #     adjusted_amount = max(1, buy_amount // 2)
        #     logger.info(f"매수 수량 조정: {buy_amount}주 → {adjusted_amount}주 (10개 초과로 인한 감소)")
        #     buy_amount = adjusted_amount
        # remaining_amount = 0  # 남은 수량 없음

        # 분할매수 로직 적용
        if ENABLE_FRACTIONAL_BUY:
            # 이미 보유 중인 종목인지 확인
            if stock_code in trading_state.get('positions', {}):
                position = trading_state['positions'][stock_code]
                
                # 현재 매수 단계 확인 (기본값 1로 설정)
                current_stage = position.get('buy_stage', 1)
                
                # 마지막 매수 시간 확인
                last_buy_time = position.get('last_buy_time')
                current_time = datetime.now()
                
                # 최대 매수 단계 도달 여부 확인
                if current_stage >= MAX_BUY_STAGES:
                    logger.info(f"{stock_name}({stock_code}) - 이미 최대 매수 단계({current_stage}/{MAX_BUY_STAGES})에 도달했습니다.")
                    return None, "최대 매수 단계 도달", 0
                
                # 쿨다운 체크
                if last_buy_time:
                    last_buy_datetime = datetime.strptime(last_buy_time, '%Y-%m-%d %H:%M:%S')
                    time_since_last_buy = (current_time - last_buy_datetime).total_seconds()
                    
                    # 쿨다운 시간 이내면 추가 매수 불가
                    if time_since_last_buy < FRACTIONAL_BUY_COOLDOWN:
                        cooldown_remaining = (FRACTIONAL_BUY_COOLDOWN - time_since_last_buy) / 60
                        logger.info(f"{stock_name}({stock_code}) - 분할매수 쿨다운 중 (남은 시간: {cooldown_remaining:.1f}분)")
                        return None, "분할매수 쿨다운", 0

                # 매우 적은 수량(2-3주)의 경우 특별 처리
                total_planned_amount = position.get('total_planned_amount', original_amount)

                logger.info(f"""
                분할매수 상세 정보:
                - 원본 수량: {original_amount}주
                - 현재 매수 단계: {current_stage}
                - 총 계획 수량: {total_planned_amount}주
                """)

                if total_planned_amount <= 3:
                    buy_amount = 1  # 각 단계에서 1주씩 매수
                    current_order_amount = buy_amount  # 현재 주문량도 동기화
                    logger.info(f"적은 수량({total_planned_amount}주) 특별 처리: 1주 매수")
                else:
                    # 각 단계별로 total_planned_amount의 일정 비율로 매수량 계산
                    # current_stage는 현재까지 완료한 단계, 즉 다음에 진행할 단계의 직전 단계
                    if current_stage == 1:
                        # 2단계 매수 - 총 계획 수량의 SECOND_BUY_RATIO(33%) 매수
                        buy_amount = int(total_planned_amount * SECOND_BUY_RATIO)
                        next_stage = 2
                        logger.info(f"2단계 매수: {buy_amount}주 (총 계획 수량 {total_planned_amount}주의 {SECOND_BUY_RATIO*100:.0f}%)")
                    elif current_stage == 2:
                        # 3단계 매수 - 총 계획 수량의 THIRD_BUY_RATIO(34%) 매수
                        buy_amount = int(total_planned_amount * THIRD_BUY_RATIO)
                        next_stage = 3
                        logger.info(f"3단계 매수: {buy_amount}주 (총 계획 수량 {total_planned_amount}주의 {THIRD_BUY_RATIO*100:.0f}%)")
                    else:
                        # 이미 최대 단계에 도달
                        logger.info(f"이미 최대 매수 단계({current_stage}/{MAX_BUY_STAGES})에 도달했습니다.")
                        return None, "최대 매수 단계 도달", 0
                    current_order_amount = buy_amount  # current_order_amount를 계산된 buy_amount로 업데이트                        
                    # 최소 1주 보장
                    buy_amount = max(1, buy_amount)
                    logger.info(f"최종 매수 수량: {buy_amount}주")
            else:
                # 신규 매수인 경우, 1단계 매수 수량 계산
                current_order_amount = int(original_amount * FIRST_BUY_RATIO)
                next_stage = 1
                logger.info(f"{stock_name}({stock_code}) - 분할매수 1단계 진행: {current_order_amount}주 (원래 계획: {original_amount}주)")
        else:
            # 분할매수 비활성화 상태면 원래 수량 그대로 사용
            next_stage = 1

        # 최소 1주 보장
        current_order_amount = max(1, current_order_amount)

        # 호가 정보 확인하여 매수 호가 설정
        limit_price = stock_price  # 기본값으로 현재가 사용
        order_book = KisKR.GetOrderBook(stock_code)
        if order_book and 'levels' in order_book and len(order_book['levels']) > 0:
            # 최우선 매도호가 확인
            best_ask_price = order_book['levels'][0]['ask_price']
            
            # 고점 근처 또는 상한가 근처 여부 확인
            is_near_high = False
            if 'ohlcv' in stock_data and stock_data['ohlcv'] is not None:
                daily_high = stock_data['ohlcv']['high'].max()
                high_ratio = (daily_high - stock_price) / stock_price * 100
                is_near_high = high_ratio < 0.5  # 고점과의 차이가 0.5% 미만이면 고점 근처로 판단
            
            # 상한가 계산 (단순 추정)
            prev_close = stock_data.get('prev_close', stock_price * 0.9)
            theoretical_upper_limit = prev_close * 1.3
            upper_proximity = (theoretical_upper_limit - stock_price) / stock_price * 100
            is_near_upper_limit = upper_proximity < 1.0  # 상한가와 1% 이내면 상한가 근처로 판단
            
            # 매수 가격 결정 로직 개선
            if is_near_high or is_near_upper_limit:
                # 고점이나 상한가 근처면 더 보수적으로 현재가에 매수
                limit_price = stock_price
                logger.info(f"고점 또는 상한가 근처 감지 - 현재가 기준 주문: {limit_price:,.0f}원")
            else:
                # 일반적인 경우 - 현재가와 최우선매도호가 사이의 가격 적용 (스프레드의 30%만 추가)
                if best_ask_price > stock_price:
                    spread = best_ask_price - stock_price
                    limit_price = stock_price + (spread * 0.3)  # 스프레드의 30%만 상승
                else:
                    limit_price = stock_price
            
            # 항상 현재가의 0.5% 이상 높지 않도록 제한
            limit_price = min(limit_price, stock_price * 1.005)            
            logger.info(f"주문 가격 결정: {limit_price:,.0f}원 (현재가: {stock_price:,.0f}원, 최우선매도호가: {best_ask_price:,.0f}원)")

        # 정수형 가격으로 변환
        int_limit_price = int(limit_price)
        
        # 주문 시작 전 주문 ID 생성 - 추적을 위해
        order_id = f"{stock_code}_{int(time.time())}"
        
        logger.info(f"{stock_name}({stock_code}) - 지정가 매수 주문 실행: {current_order_amount}주 @ {int_limit_price:,}원")
        order_result = KisKR.MakeBuyLimitOrder(stock_code, current_order_amount, int_limit_price)        

        # 주문 결과 유효성 검사 강화
        if isinstance(order_result, str) and ("Error" in order_result or "rt_cd" in order_result or "msg" in order_result):
            logger.error(f"매수 주문 API 오류: {order_result}")
            return None, f"주문 API 오류: {order_result}", 0
            
        if not order_result:
            logger.error(f"매수 주문 실패 (API 응답 없음)")
            return None, "주문 실패", 0

        # 주문 정보 저장 (체결 여부와 관계없이)
        if 'pending_orders' not in trading_state:
            trading_state['pending_orders'] = {}
            
        # 미체결 주문 정보 미리 저장
        trading_state['pending_orders'][stock_code] = {
            'order_id': order_id,
            'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'order_price': int_limit_price,
            'order_amount': current_order_amount,
            'total_planned_amount': original_amount,  # 분할매수를 위한 원래 계획 수량 저장
            'buy_stage': next_stage,  # 분할매수 단계 정보 추가
            'status': 'submitted'
        }
        
        # 안전하게 상태 저장 (체결 확인 전)
        try:
            save_trading_state(trading_state)
            logger.info(f"주문 정보 저장 완료: {stock_code} (주문ID: {order_id})")
        except Exception as e:
            logger.error(f"주문 정보 저장 중 오류: {str(e)}")
            # 저장 실패해도 계속 진행 (체결 확인 시도)

        # 주문 직후, 체결 대기 전 현재가 변동 체크
        initial_price = stock_price
        time.sleep(3)  # 잠시 대기 후 가격 재확인
        current_price_check = KisKR.GetCurrentPrice(stock_code)

        # 급격한 가격 하락 감지 (예: 1% 이상 하락)
        if current_price_check < initial_price * 0.99:
            logger.warning(f"⚠️ 주문 직후 가격 급락 감지: {initial_price} → {current_price_check} ({((current_price_check/initial_price)-1)*100:.2f}%)")
            
            # 기존 주문 취소 시도
            cancel_result = cancel_existing_orders(stock_code)
            
            if cancel_result:
                # 취소 후 주문 상태 업데이트
                if stock_code in trading_state['pending_orders']:
                    trading_state['pending_orders'][stock_code]['status'] = 'canceled'
                    trading_state['pending_orders'][stock_code]['cancel_reason'] = '가격 급락'
                    trading_state['pending_orders'][stock_code]['cancel_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    save_trading_state(trading_state)
                    
                # 취소 후 재주문 여부 결정
                if current_price_check < int_limit_price:
                    logger.warning(f"지정가({int_limit_price})보다 현재가({current_price_check})가 낮아 주문 취소")
                    return None, "가격 급락으로 주문 취소", 0
        # 가격 재검증 코드 끝 -------------------------

        # 체결 대기 (시간 증가)
        logger.info(f"체결 확인을 위해 10초 대기...")
        time.sleep(10)

        # 체결 대기 함수 호출 - 지정가 정보 전달
        executed_price, executed_amount = wait_for_order_execution(
            stock_code, 
            current_order_amount,
            max_wait_time=45,
            order_type="BUY",
            order_price=int_limit_price  # 지정가 정보 전달
        )        
        
        # 주문 체결 여부 검증 강화 (체결 상태 명시적 로깅)
        if executed_amount <= 0 or executed_price <= 0:
            # 미체결 알림
            logger.info(f"미체결 상태로 진행: {stock_name}({stock_code}) {buy_amount}주 @ {int_limit_price:,}원")
            
            # 미체결 주문 상태 업데이트
            if stock_code in trading_state['pending_orders']:
                trading_state['pending_orders'][stock_code].update({
                    'status': 'pending',  # 미체결 상태
                    'last_check_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                save_trading_state(trading_state)
            
            # 미체결 알림 메시지
            msg = f"⏳ 매수 주문 미체결 상태: {stock_name}({stock_code})\n"
            msg += f"- 수량: {current_order_amount:,}주 @ {int_limit_price:,}원\n"
            msg += f"- 주문은 시스템에 등록되었으며, 자동 취소 시간까지 체결을 기다립니다."
            logger.info(msg)
            discord_alert.SendMessage(msg)
            
            return None, "미체결", 0  # 명확하게 체결 실패 상태 반환
        
        # 체결된 경우 - 실제 체결 정보 사용
        # 체결가와 예상가 차이 확인
        price_diff = ((executed_price - stock_price) / stock_price) * 100
        logger.info(f"체결 완료: 예상가 {stock_price:,.0f}원 → 실제 체결가 {executed_price:,.0f}원 ({price_diff:.2f}% 차이)")
        
        # 체결가가 예상가보다 3% 이상 높으면 경고
        if price_diff > 3.0:
            logger.warning(f"⚠️ 체결가 급등 발생: {price_diff:.2f}% 상승")
        
        # 매수 수수료 계산 - 실제 체결량 기준
        buy_fee = calculate_trading_fee(executed_price, executed_amount, is_buy=True)

        # 포지션 상태 업데이트 시도
        try:
            # 트레이딩 상태 업데이트
            if 'positions' not in trading_state:
                trading_state['positions'] = {}
                
            # 체결 여부에 따라 미체결 주문 상태 업데이트
            if stock_code in trading_state['pending_orders']:
                # 일반 매수 체결
                trading_state['pending_orders'][stock_code].update({
                    'executed_amount': executed_amount,
                    'executed_price': executed_price,
                    'status': 'filled',
                    'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # 분할매수 로직 적용 - 이미 매수한 종목인 경우
            if ENABLE_FRACTIONAL_BUY and stock_code in trading_state.get('positions', {}):
                # 기존 포지션 정보 백업
                position = trading_state['positions'][stock_code]
                prev_amount = position['amount']
                prev_entry_price = position['entry_price']
                prev_fee = position.get('trading_fee', 0)
                
                # 새로운 평균 매수가 계산
                total_value = (prev_amount * prev_entry_price) + (executed_amount * executed_price)
                new_amount = prev_amount + executed_amount
                new_entry_price = total_value / new_amount if new_amount > 0 else executed_price
                
                # 수수료 합산
                total_fee = prev_fee + buy_fee
                
                # 포지션 정보 업데이트
                position.update({
                    'entry_price': new_entry_price,
                    'amount': new_amount,
                    'trading_fee': total_fee,
                    'buy_stage': next_stage,  # 매수 단계 업데이트
                    'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_planned_amount': original_amount  # 원래 계획 수량 저장/업데이트
                })
                
                logger.info(f"포지션 업데이트 (분할매수 {next_stage}단계):")
                logger.info(f"- 이전: {prev_amount}주 @ {prev_entry_price:,.0f}원")
                logger.info(f"- 추가: {executed_amount}주 @ {executed_price:,.0f}원")
                logger.info(f"- 변경: {new_amount}주 @ {new_entry_price:,.0f}원")
            else:
                # 새로운 포지션 (첫 매수)
                trading_state['positions'][stock_code] = {
                    'entry_price': executed_price,
                    'amount': executed_amount,
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'trading_fee': buy_fee,
                    'code': stock_code,
                    'strategy': 'momentum_buy',
                    # 분할매수 정보 추가
                    'buy_stage': next_stage,
                    'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_planned_amount': original_amount
                }
                
                logger.info(f"신규 포지션 생성: {stock_name}({stock_code})")
                logger.info(f"- 매수가: {executed_price:,.0f}원")
                logger.info(f"- 수량: {executed_amount}주")
                logger.info(f"- 수수료: {buy_fee:,.0f}원")
            
            # 상태 저장 (중요: 트랜잭션 성공 확인)
            save_trading_state(trading_state)
            logger.info(f"포지션 저장 완료: {stock_code}")

        except Exception as e:
            # 포지션 저장 실패 시 상세 로깅 및 복구 시도
            logger.error(f"포지션 저장 중 오류 발생: {str(e)}")
            logger.error(f"포지션 저장 실패 시 백업 로직 실행")
            
            # 백업 로직: 간단한 정보로 다시 시도
            try:
                # 단순화된 포지션 정보 저장
                trading_state['positions'][stock_code] = {
                    'entry_price': executed_price,
                    'amount': executed_amount,
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'trading_fee': buy_fee,
                    'code': stock_code,
                    'strategy': 'emergency_save',  # 비상 저장 표시
                    'buy_stage': next_stage  # 분할매수 단계 정보 포함
                }
                save_trading_state(trading_state)
                logger.info(f"백업 포지션 저장 성공: {stock_code}")
                
                # 알림 발송
                emergency_msg = f"⚠️ 포지션 저장 오류 발생 - 백업 저장 완료: {stock_name}({stock_code})"
                discord_alert.SendMessage(emergency_msg)
                
            except Exception as backup_e:
                logger.critical(f"백업 저장도 실패! {str(backup_e)}")
                error_msg = f"⚠️ 심각한 포지션 저장 오류 - 수동 확인 필요: {stock_name}({stock_code})"
                discord_alert.SendMessage(error_msg)
        
        # 성공 메시지 출력
        msg = f"✅ 매수 주문 체결 완료!"
        msg += f"\n"
        msg += f"- 종목: {stock_name}({stock_code})\n"
        msg += f"- 수량: {executed_amount:,}주"
        if ENABLE_FRACTIONAL_BUY:
            msg += f" (분할매수 {next_stage}/{MAX_BUY_STAGES}단계)"
        msg += f"\n"
        msg += f"- 매수가: {int(executed_price):,}원\n"
        msg += f"- 거래비용: {int(buy_fee):,}원"
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 상태 파일의 유무 확인 (추가 안전 조치)
        try:
            # 파일 존재 여부 확인
            file_exists = os.path.exists(f"KrStock_{BOT_NAME}.json")
            if not file_exists:
                logger.critical(f"심각한 오류: 상태 파일이 존재하지 않습니다!")
                emergency_msg = f"⚠️ 상태 파일 없음 - 수동 개입 필요!"
                discord_alert.SendMessage(emergency_msg)
            else:
                # 파일 내용 확인
                try:
                    with open(f"KrStock_{BOT_NAME}.json", 'r') as f:
                        saved_state = json.load(f)
                    
                    if stock_code not in saved_state.get('positions', {}):
                        logger.critical(f"심각한 오류: 상태 파일에 방금 매수한 종목이 없습니다!")
                        emergency_msg = f"⚠️ 상태 파일에 매수 종목 누락 - 수동 개입 필요!"
                        discord_alert.SendMessage(emergency_msg)
                except:
                    logger.critical(f"심각한 오류: 상태 파일을 읽을 수 없습니다!")
                    emergency_msg = f"⚠️ 상태 파일 읽기 실패 - 수동 개입 필요!"
                    discord_alert.SendMessage(emergency_msg)
        except:
            # 파일 체크에서 오류가 발생해도 계속 진행
            pass
        
        return executed_price, None, executed_amount
        
    except Exception as e:
        # 주요 오류 발생 시 추가 정보 로깅 및 경고
        error_msg = f"매수 주문 처리 중 심각한 오류: {str(e)}"
        logger.error(error_msg)
        
        # 상태 파일 안전 확인
        try:
            # 트레이딩 상태 다시 로드해서 체크
            trading_state = load_trading_state()
            
            # API로 실제 보유 상태 확인
            my_stocks = KisKR.GetMyStockList()
            stock_in_account = any(s['StockCode'] == stock_code for s in my_stocks)

            # 보유 중인데 상태 파일에 없으면 비상 복구
            if stock_in_account and stock_code not in trading_state.get('positions', {}):
                logger.critical(f"비상 상황: 실제로 보유 중이지만 상태 파일에 없는 종목 감지 - {stock_code}")
                
                # 계좌 정보로 포지션 복구 시도
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        if 'positions' not in trading_state:
                            trading_state['positions'] = {}
                            
                        # 실제 평균가 확보 (API에서 직접)
                        actual_avg_price = float(stock.get('AvrPrice', 0))
                        
                        # 평균가가 없거나 0인 경우에만 대체값 사용
                        entry_price = actual_avg_price if actual_avg_price > 0 else stock_price
                            
                        # 긴급 포지션 정보 생성
                        trading_state['positions'][stock_code] = {
                            'entry_price': entry_price,
                            'amount': int(stock.get('StockAmt', 0)),
                            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'trading_fee': 0,  # 정확한 수수료는 알 수 없음
                            'code': stock_code,
                            'strategy': 'emergency_recovery',  # 비상 복구 표시
                            'buy_stage': 1  # 분할매수 단계 1로 설정
                        }
                        save_trading_state(trading_state)
                        
                        emergency_msg = f"⚠️ 비상 상황 - 상태 파일에 누락된 매수 종목 복구 완료: {stock_name}({stock_code})"
                        emergency_msg += f"\n- 실제 평균가: {entry_price:,.0f}원으로 복구"
                        discord_alert.SendMessage(emergency_msg)
                        break
        except Exception as recovery_e:
            logger.critical(f"비상 복구 중 추가 오류: {str(recovery_e)}")

        # 포지션 상태 업데이트 시도
        try:
            # 트레이딩 상태 업데이트 (어떤 상황에서든 체결 정보 저장)
            if 'positions' not in trading_state:
                trading_state['positions'] = {}
                
            # 체결 여부에 따라 미체결 주문 상태 업데이트
            if stock_code in trading_state['pending_orders']:
                # 일반 매수 체결
                trading_state['pending_orders'][stock_code].update({
                    'executed_amount': executed_amount,
                    'executed_price': executed_price,
                    'status': 'filled',
                    'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

            # 분할매수 로직 적용 - 새로 추가
            if ENABLE_FRACTIONAL_BUY and stock_code in trading_state.get('positions', {}):
                # 기존 포지션 업데이트 (추가 매수)
                position = trading_state['positions'][stock_code]
                
                # 기존 포지션 정보 백업
                prev_amount = position['amount']
                prev_entry_price = position['entry_price']
                prev_fee = position.get('trading_fee', 0)
                
                # 새로운 평균 매수가 계산
                total_value = (prev_amount * prev_entry_price) + (executed_amount * executed_price)
                new_amount = prev_amount + executed_amount

                # 체결량이 0이 아닌 경우에만 새 평균가 계산 (0으로 나누기 방지)
                if new_amount > 0:
                    new_entry_price = total_value / new_amount
                else:
                    new_entry_price = executed_price

                # 수수료 합산
                total_fee = prev_fee + buy_fee
                
                # 포지션 정보 업데이트
                position.update({
                    'entry_price': new_entry_price,
                    'amount': new_amount,
                    'trading_fee': total_fee,
                    'buy_stage': next_stage,  # 매수 단계 업데이트
                    'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_planned_amount': original_amount  # 원래 계획 수량 저장/업데이트
                })

                logger.info(f"포지션 업데이트 (분할매수 {next_stage}단계):")
                logger.info(f"- 이전: {prev_amount}주 @ {prev_entry_price:,.0f}원")
                logger.info(f"- 추가: {executed_amount}주 @ {executed_price:,.0f}원")
                logger.info(f"- 변경: {new_amount}주 @ {new_entry_price:,.0f}원")
            else:
                # 새로운 포지션
                trading_state['positions'][stock_code] = {
                    'entry_price': executed_price,
                    'amount': executed_amount,
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'trading_fee': buy_fee,
                    'code': stock_code,
                    'strategy': 'momentum_buy',
                    # 분할매수 정보 추가
                    'buy_stage': next_stage,
                    'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_planned_amount': original_amount
                }
            
            logger.info(f"신규 포지션 생성: {stock_name}({stock_code})")
            logger.info(f"- 매수가: {executed_price:,.0f}원")
            logger.info(f"- 수량: {executed_amount}주")
            logger.info(f"- 수수료: {buy_fee:,.0f}원")
            
            # 포지션 저장 먼저
            save_trading_state(trading_state)
            logger.info(f"포지션 저장 완료: {stock_code}")

        except Exception as e:
            # 포지션 저장 실패 시 상세 로깅 및 복구 시도
            logger.error(f"포지션 저장 중 오류 발생: {str(e)}")
            logger.error(f"포지션 저장 실패 시 백업 로직 실행")
            
            # 백업 로직: 간단한 정보로 다시 시도
            try:
                # 단순화된 포지션 정보 저장
                trading_state['positions'][stock_code] = {
                    'entry_price': executed_price,
                    'amount': executed_amount,
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'trading_fee': buy_fee,
                    'code': stock_code,
                    'strategy': 'emergency_save',  # 비상 저장 표시
                    'buy_stage': next_stage  # 분할매수 단계는 유지
                }
                save_trading_state(trading_state)
                logger.info(f"백업 포지션 저장 성공: {stock_code}")
                
                # 알림 발송
                emergency_msg = f"⚠️ 포지션 저장 오류 발생 - 백업 저장 완료: {stock_name}({stock_code})"
                discord_alert.SendMessage(emergency_msg)
                
            except Exception as backup_e:
                logger.critical(f"백업 저장도 실패! {str(backup_e)}")
                error_msg = f"⚠️ 심각한 포지션 저장 오류 - 수동 확인 필요: {stock_name}({stock_code})"
                discord_alert.SendMessage(error_msg)
        
        # 성공 메시지 출력 - 분할매수 정보 추가
        msg = f"✅ 매수 주문 체결 완료!"
        msg += f"\n"
        msg += f"- 종목: {stock_name}({stock_code})\n"
        msg += f"- 수량: {executed_amount:,}주"
        if ENABLE_FRACTIONAL_BUY:
            msg += f" (분할매수 {next_stage}/{MAX_BUY_STAGES}단계)"
        msg += f"\n"
        msg += f"- 매수가: {int(executed_price):,}원\n"
        msg += f"- 거래비용: {int(buy_fee):,}원"
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 상태 파일의 유무 확인 (추가 안전 조치)
        try:
            # 파일 존재 여부 확인
            file_exists = os.path.exists(f"KrStock_{BOT_NAME}.json")
            if not file_exists:
                logger.critical(f"심각한 오류: 상태 파일이 존재하지 않습니다!")
                emergency_msg = f"⚠️ 상태 파일 없음 - 수동 개입 필요!"
                discord_alert.SendMessage(emergency_msg)
            else:
                # 파일 내용 확인
                try:
                    with open(f"KrStock_{BOT_NAME}.json", 'r') as f:
                        saved_state = json.load(f)
                    
                    if stock_code not in saved_state.get('positions', {}):
                        logger.critical(f"심각한 오류: 상태 파일에 방금 매수한 종목이 없습니다!")
                        emergency_msg = f"⚠️ 상태 파일에 매수 종목 누락 - 수동 개입 필요!"
                        discord_alert.SendMessage(emergency_msg)
                except:
                    logger.critical(f"심각한 오류: 상태 파일을 읽을 수 없습니다!")
                    emergency_msg = f"⚠️ 상태 파일 읽기 실패 - 수동 개입 필요!"
                    discord_alert.SendMessage(emergency_msg)
        except:
            # 파일 체크에서 오류가 발생해도 계속 진행
            pass
        
        return executed_price, None, executed_amount
        
    except Exception as e:
        # 주요 오류 발생 시 추가 정보 로깅 및 경고
        error_msg = f"매수 주문 처리 중 심각한 오류: {str(e)}"
        logger.error(error_msg)
        
        # 상태 파일 안전 확인
        try:
            # 트레이딩 상태 다시 로드해서 체크
            trading_state = load_trading_state()
            
            # API로 실제 보유 상태 확인
            my_stocks = KisKR.GetMyStockList()
            stock_in_account = any(s['StockCode'] == stock_code for s in my_stocks)
            
            # 보유 중인데 상태 파일에 없으면 비상 복구
            if stock_in_account and stock_code not in trading_state.get('positions', {}):
                logger.critical(f"비상 상황: 실제로 보유 중이지만 상태 파일에 없는 종목 감지 - {stock_code}")
                
                # 계좌 정보로 포지션 복구 시도
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        if 'positions' not in trading_state:
                            trading_state['positions'] = {}
                            
                        # 긴급 포지션 정보 생성
                        trading_state['positions'][stock_code] = {
                            'entry_price': float(stock.get('AvrPrice', stock_price)),
                            'amount': int(stock.get('StockAmt', 0)),
                            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'trading_fee': 0,  # 정확한 수수료는 알 수 없음
                            'code': stock_code,
                            'strategy': 'emergency_recovery',  # 비상 복구 표시
                            'buy_stage': 1  # 기본값으로 1단계 설정
                        }
                        save_trading_state(trading_state)
                        
                        emergency_msg = f"⚠️ 비상 상황 - 상태 파일에 누락된 매수 종목 복구 완료: {stock_name}({stock_code})"
                        discord_alert.SendMessage(emergency_msg)
                        break
        except Exception as recovery_e:
            logger.critical(f"비상 복구 중 추가 오류: {str(recovery_e)}")
        
        return None, str(e), 0



def wait_for_sell_order_execution(stock_code, order_amount, max_wait_time=30):
    """매도 주문 체결을 안전하게 기다리는 함수"""
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            order_details = KisKR.GetOrderList(
                stockcode=stock_code,
                side="SELL",
                status="CLOSE",
                limit=5  # 더 많은 주문 기록 확인
            )
            
            if order_details:
                # 주문 정보 더 자세히 로깅
                logger.info(f"주문 상세 정보: {order_details}")
                
                # 최근 체결된 주문 찾기
                for order in order_details:
                    # 정확한 주문 매칭 확인 (시간 기반 필터링 추가)
                    order_time_str = order.get('OrderTime', '')
                    if order_time_str:
                        try:
                            order_time = datetime.strptime(order_time_str, "%H%M%S")
                            current_time = datetime.now()
                            time_diff = (current_time - order_time).total_seconds()
                            
                            # 최근 5분 이내 주문만 고려
                            if time_diff > 300:  # 5분 = 300초
                                continue
                        except:
                            # 시간 형식 변환 오류 시 계속 진행
                            pass
                    
                    if (order.get('OrderStock') == stock_code and 
                        order.get('OrderAmt') == order_amount and
                        order.get('OrderStatus') == 'Close' and
                        order.get('OrderSide') == 'Sell'):
                        
                        executed_price = float(order.get('OrderAvgPrice', 0))
                                        
                        if executed_price > 0:
                            logger.info(f"실제 체결가: {executed_price:,.0f}원")
                            return executed_price
                                    
            # 주문 상태 주기적으로 확인
            if (time.time() - start_time) % 5 < 1:  # 약 5초마다 로그 출력
                logger.info(f"{stock_code} 매도 주문 체결 대기 중... ({int(time.time() - start_time)}초 경과)")
                
            time.sleep(1)  # 1초 간격으로 체크
            
        except Exception as e:
            logger.error(f"매도 주문 상태 확인 중 에러: {str(e)}")
    
    logger.warning(f"{stock_code} 매도 주문 체결 확인 타임아웃 ({max_wait_time}초)")
    return 0  # 최대 대기 시간 초과


def process_sell_order(stock_code, amount):
    """매도 주문 처리 및 체결 정보 반환 - 개선버전"""
    try:
        stock_name = KisKR.GetStockName(stock_code)
        logger.info(f"{stock_name}({stock_code}) 매도 주문 시작: {amount}주")
        
        # 시작 시점의 보유 수량 확인
        initial_position = None
        my_stocks = KisKR.GetMyStockList()
        
        for stock in my_stocks:
            if stock['StockCode'] == stock_code:
                initial_position = stock
                break
        
        if not initial_position:
            return None, 0, f"보유 종목 정보를 찾을 수 없음"
        
        actual_amount = int(initial_position.get('StockAmt', 0))
        
        if actual_amount < amount:
            logger.warning(f"{stock_name}({stock_code}) 매도 수량 조정: {amount}주 → {actual_amount}주 (실제 보유량 기준)")
            if actual_amount <= 0:
                return None, 0, "보유 수량 부족으로 매도 불가"
            amount = actual_amount
            
        # 매도 주문 실행
        logger.info(f"{stock_name}({stock_code}) 시장가 매도 주문 실행: {amount}주")
        order_result = KisKR.MakeSellMarketOrder(stock_code, amount)
        
        # 주문 결과 유효성 검사 강화
        if isinstance(order_result, str) and ("Error" in order_result or "rt_cd" in order_result or "msg" in order_result):
            logger.error(f"{stock_name}({stock_code}) 매도 주문 API 오류: {order_result}")
            return None, 0, f"주문 API 오류: {order_result}"
            
        if not order_result:
            logger.error(f"{stock_name}({stock_code}) 매도 주문 실패")
            return None, 0, "주문 실패 (API 응답 없음)"
            
        # 체결 정보 확인 (개선된 함수 사용)
        executed_price, executed_amount = wait_for_order_execution(
            stock_code, 
            amount, 
            max_wait_time=15, 
            order_type="SELL"
        )
        
        if executed_price == 0 or executed_amount == 0:
            # 체결 실패 또는 타임아웃 - 실제 계좌 변동 확인
            logger.warning(f"{stock_name}({stock_code}) 매도 체결 확인 실패, 계좌 변동 확인 시도")
            
            # 주문 후 실제 잔고 변동 확인
            time.sleep(2)  # 잔고 반영 시간 대기
            updated_stocks = KisKR.GetMyStockList()
            
            # 종목이 계좌에서 사라졌거나 수량이 감소했는지 확인
            updated_position = None
            for stock in updated_stocks:
                if stock['StockCode'] == stock_code:
                    updated_position = stock
                    break
            
            if updated_position is None:
                # 종목이 계좌에서 완전히 사라짐 - 전체 매도로 판단
                logger.info(f"{stock_name}({stock_code}) 보유 목록에서 제거됨 - 전체 매도 완료")
                executed_amount = actual_amount
                executed_price = KisKR.GetCurrentPrice(stock_code)  # 현재가로 대체
            elif int(updated_position.get('StockAmt', 0)) < actual_amount:
                # 보유 수량이 감소 - 일부 매도 완료로 판단
                executed_amount = actual_amount - int(updated_position.get('StockAmt', 0))
                executed_price = KisKR.GetCurrentPrice(stock_code)  # 현재가로 대체
                logger.info(f"{stock_name}({stock_code}) 보유량 감소 확인: {actual_amount}주 → {updated_position.get('StockAmt', 0)}주 (매도량: {executed_amount}주)")
            else:
                # 보유 수량 변화 없음 - 매도 체결 실패
                logger.error(f"{stock_name}({stock_code}) 매도 체결 확인 최종 실패")
                return None, 0, "체결 확인 실패"
        
        logger.info(f"{stock_name}({stock_code}) 매도 체결 확인 완료: {executed_amount}주 @ {executed_price:,.0f}원")
        return executed_price, executed_amount, None
        
    except Exception as e:
        logger.error(f"매도 주문 처리 중 에러: {str(e)}")
        return None, 0, str(e)


def handle_sell_order(stock_code, position, sell_type, daily_profit):    
    """매도 처리 통합 함수 - 개선버전"""
    try:
        stock_name = KisKR.GetStockName(stock_code)
        amount = position['amount']
        entry_price = position['entry_price']
        
        # 매도 메시지 생성 - 매도 유형별 설명 추가
        sell_reason_map = {
            'trailing_stop': '트레일링 스탑',
            'dynamic_stoploss': '손절라인',
            'ADAPTIVE_STOPLOSS': '변동성 기반 손절',
            'DIRECT_STOPLOSS': '직접 손절',
            'selling_pressure': '매수세 급격한 약화',
            'vwap_breakdown': 'VWAP 하향 돌파',
            'volume_surge': '거래량 급증',
            'momentum_lost': '모멘텀 상실',
            'ORDER_FLOW_PROTECT': '호가 급변 수익 보존',
            'ATR_TAKE_PROFIT': 'ATR 기반 익절',
            'TAKE_PROFIT': '목표 수익 달성',
            'MORNING_TAKE_PROFIT': '오전장 익절',
            'TIME_BASED_TAKE_PROFIT': '시간 경과 익절',
            'MARKET_CLOSE_PROFIT': '장 마감 전 수익 보존',
            'MARKET_CLOSE_STOPLOSS': '장 마감 전 손절',
            'REEVALUATION': '다음날 재평가',
            'FRACTIONAL_SELL': '분할매도',
            'PROFIT_PROTECTION_EARLY_LOSS': '수익 보호 (조기 손실 차단)',
            'PROFIT_PROTECTION_RETREAT': '수익 보호 (수익 반납 방지)',
            'PROFIT_PROTECTION_TAKE_SMALL_PROFIT': '수익 보호 (소액 수익 확정)',
            'PROFIT_PROTECTION_TRAILING': '수익 보호 (강화된 트레일링)'
        }

        sell_reason = sell_reason_map.get(sell_type, '기타')

        logger.info(f"매도 타입: {sell_type}, 변환된 사유: {sell_reason}")
        msg = f"{sell_reason} 조건 도달로 매도 시도!\n"
        msg += f"종목: {stock_name}({stock_code}), 수량: {amount:,}주"
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 매도 전 실제 보유량 확인 (API로 재확인)
        actual_position = None
        try:
            my_stocks = KisKR.GetMyStockList()
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    actual_position = stock
                    break
                    
            if actual_position:
                actual_amount = int(actual_position.get('StockAmt', 0))
                if actual_amount != amount:
                    logger.warning(f"{stock_name}({stock_code}) 매도량 불일치: 상태파일({amount}주) vs 실제보유({actual_amount}주)")
                    # 실제 보유량으로 조정
                    amount = actual_amount
        except Exception as e:
            logger.error(f"실제 보유량 확인 중 오류: {str(e)}")
            # 오류 발생 시 기존 수량 유지
        
        # 매도 주문 실행 및 실제 체결가 확인 - 개선된 함수 사용
        executed_price, executed_amount, error = process_sell_order(stock_code, amount)
        
        if error:
            # 매도 실패 알림
            error_msg = f"⚠️ {stock_name}({stock_code}) 매도 실패: {error}"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            return False, None, amount  # 실패 시 원래 수량 그대로 반환
            
        if executed_amount <= 0 or executed_price <= 0:
            error_msg = f"⚠️ {stock_name}({stock_code}) 매도 실패: 체결 확인 불가"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            return False, None, amount  # 실패 시 원래 수량 그대로 반환
            
        # 수수료 계산 (실제 체결가 기준)
        buy_fee = position.get('trading_fee', calculate_trading_fee(entry_price, executed_amount, is_buy=True))
        sell_fee = calculate_trading_fee(executed_price, executed_amount, is_buy=False)
        total_fee = buy_fee + sell_fee
        
        # 실제 손익 계산 - 실제 체결량 기준
        gross_profit = (executed_price - entry_price) * executed_amount
        net_profit = gross_profit - total_fee
        net_profit_rate = (net_profit / (entry_price * executed_amount)) * 100

        logger.info(f"\n=== 매도 수익률 상세 내역 ({stock_name}) ===")
        logger.info(f"- 매수가: {entry_price:,.0f}원, 매도가: {executed_price:,.0f}원")
        logger.info(f"- 매도량: {executed_amount}주")
        logger.info(f"- 총 수수료/세금: {total_fee:,.0f}원 (매수: {buy_fee:,.0f}원, 매도: {sell_fee:,.0f}원)")
        logger.info(f"- 순이익: {net_profit:,.0f}원")
        logger.info(f"- 순수익률: {net_profit_rate:.2f}%")
        logger.info(f"- 매도 사유: {sell_reason}")

        # trade_info 생성 (실제 체결가와 수량 기준)
        trade_info = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'entry_price': entry_price,
            'exit_price': executed_price,
            'amount': executed_amount,  # 실제 체결량 사용
            'profit_amount': net_profit,
            'profit_rate': net_profit_rate,
            'trading_fee': total_fee,
            'sell_type': sell_type,
            'sell_reason': sell_reason,
            'sell_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # daily_profit 업데이트
        daily_profit['today_profit'] += net_profit
        daily_profit['accumulated_profit'] += net_profit
        daily_profit['total_trades'] += 1
        if net_profit > 0:
            daily_profit['winning_trades'] += 1
        daily_profit['max_profit_trade'] = max(daily_profit['max_profit_trade'], net_profit)
        daily_profit['max_loss_trade'] = min(daily_profit['max_loss_trade'], net_profit)
        
        if daily_profit['start_money'] > 0:
            daily_profit['today_profit_rate'] = (daily_profit['today_profit'] / 
                                               daily_profit['start_money']) * 100
        
        # 일부 체결 여부 체크
        remaining_amount = amount - executed_amount
        is_partial_execution = remaining_amount > 0
        
        # 매도 완료 메시지
        msg = f"💰 매도 {'일부 ' if is_partial_execution else ''}완료 - {stock_name}({stock_code})\n"
        msg += f"매도가: {executed_price:,.0f}원 (수수료/세금: {total_fee:,.0f}원)\n"
        msg += f"순수익: {net_profit:,.0f}원 ({net_profit_rate:.2f}%)\n"
        
        if is_partial_execution:
            msg += f"체결 수량: {executed_amount}주 (요청: {amount}주, 남은 수량: {remaining_amount}주)\n"
        else:
            msg += f"체결 수량: {executed_amount}주\n"
            
        msg += f"매도사유: {sell_reason}\n"
        msg += f"당일 누적 손익: {daily_profit['today_profit']:,.0f}원"
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 매도 후 실제 계좌 상태 재확인
        try:
            after_stocks = KisKR.GetMyStockList()
            still_holding = False
            actual_remaining = 0
            
            for stock in after_stocks:
                if stock['StockCode'] == stock_code:
                    still_holding = True
                    actual_remaining = int(stock.get('StockAmt', 0))
                    break
            
            # 계좌 데이터와 계산된 잔여량 비교 (상태 정합성 체크)
            if still_holding and actual_remaining > 0:
                if actual_remaining != remaining_amount:
                    logger.warning(f"{stock_name}({stock_code}) 매도 후 잔여량 불일치: 계산({remaining_amount}주) vs 실제({actual_remaining}주)")
                    # 실제 잔여량으로 보정
                    remaining_amount = actual_remaining
            elif remaining_amount > 0 and not still_holding:
                # 계산상으로는 남아있어야 하는데 계좌에 없음 (전량 매도된 것으로 간주)
                logger.warning(f"{stock_name}({stock_code}) 매도 후 잔여량 이상: 계산상 {remaining_amount}주 남아야 하지만 실제로는 모두 매도됨")
                remaining_amount = 0
        except Exception as e:
            logger.error(f"매도 후 계좌 상태 확인 중 오류: {str(e)}")
        
        # 성공적인 매도 후 상태 저장
        save_daily_profit_state(daily_profit)
        
        return True, trade_info, remaining_amount
        
    except Exception as e:
        error_msg = f"매도 처리 중 에러: {str(e)}"
        logger.error(error_msg)
        discord_alert.SendMessage(f"⚠️ 매도 실패: {error_msg}")
        return False, None, amount  # 원래 수량 그대로 반환



def check_twin_peaks_pattern(df, window=20):
    """쌍봉 패턴과 신고가 돌파 확인"""
    try:
        if df is None or len(df) < window:
            return None
            
        # 이동 최고가 계산
        rolling_high = df['high'].rolling(window=window).max()
        
        # 갭 상승 확인 (MIN_GAP_PERCENT 사용)
        gap_up = (df['open'].iloc[-1] - df['high'].iloc[-2]) / df['high'].iloc[-2] * 100 >= MIN_GAP_PERCENT
        
        # 신고가 돌파 확인
        new_high = df['high'].iloc[-1] > rolling_high.iloc[-2]
        
        # 거래량 비교 (MIN_BREAKOUT_VOLUME 사용)
        avg_volume = df['volume'].rolling(window=5).mean().iloc[-1]
        volume_lighter = df['volume'].iloc[-1] <= avg_volume * MIN_BREAKOUT_VOLUME
        
        # 당일 음봉 여부 확인
        is_bearish = df['close'].iloc[-1] < df['open'].iloc[-1]
        
        # 쌍봉 패턴 확인
        peaks = []
        for i in range(2, len(df)-2):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                df['high'].iloc[i] > df['high'].iloc[i-2] and
                df['high'].iloc[i] > df['high'].iloc[i+1] and 
                df['high'].iloc[i] > df['high'].iloc[i+2]):
                peaks.append((i, df['high'].iloc[i]))
        
        twin_peaks = False
        if len(peaks) >= 2:
            last_two_peaks = peaks[-2:]
            peak_gap = last_two_peaks[1][0] - last_two_peaks[0][0]
            price_diff = abs(last_two_peaks[1][1] - last_two_peaks[0][1])/last_two_peaks[0][1]
            twin_peaks = (peak_gap <= TWIN_PEAKS_MAX_GAP and 
                         price_diff < TWIN_PEAKS_SIMILARITY)
        
        return {
            'has_pattern': new_high and gap_up and volume_lighter and not is_bearish,
            'gap_up': gap_up,
            'new_high': new_high,
            'volume_lighter': volume_lighter,
            'is_bearish': is_bearish,
            'twin_peaks': twin_peaks,
            'last_peak_price': peaks[-1][1] if peaks else None
        }
        
    except Exception as e:
        logger.error(f"쌍봉 패턴 확인 중 에러: {str(e)}")
        return None


@cached('minute_data')
def analyze_minute_data(stock_code, interval=MINUTE_INTERVAL):
    """분봉 데이터 분석"""
    try:
        df = KisKR.GetOhlcvMinute(stock_code)
        if df is None or len(df) < 20:
            return None
        
        # 당일 예상 거래량 계산
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].mean()
        volume_projection = (current_volume / len(df)) * (390/interval)
        
        # 매수세 강도 분석
        recent_candles = df.iloc[-10:]
        buying_pressure = (recent_candles['close'] > recent_candles['open']).mean()
        
        # VWAP 계산
        vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()
        
        # 거래량 급증 여부 - 전역 상수 사용
        volume_threshold = VOLUME_SURGE_THRESHOLD # 전역 상수 사용
        volume_surge = df['volume'].iloc[-1] > avg_volume * volume_threshold
        
        # 추가 분석 지표
        recent_volume_trend = df['volume'].iloc[-3:].mean() > df['volume'].iloc[-6:-3].mean()
        price_momentum = (df['close'].iloc[-1] / df['close'].iloc[-3]) - 1
        
        # 연속 음봉 카운트
        continuous_bearish_count = count_continuous_bearish_candles(df)

        result = {
            'volume_projection': volume_projection,
            'avg_volume': avg_volume,
            'buying_pressure': buying_pressure,
            'current_price': df['close'].iloc[-1],
            'vwap': vwap,
            'above_vwap': df['close'].iloc[-1] > vwap,
            'volume_trend': recent_volume_trend,
            'price_momentum': price_momentum,
            'volume_surge': volume_surge,
            'continuous_bearish_count': continuous_bearish_count,
            'continuous_bearish_detailed_info': {
                'count': continuous_bearish_count,
                'recent_candles': recent_candles.to_dict('records')
            }
        }
        
        # 거래량 분석 로깅
        logger.info(f"\n거래량 분석:")
        logger.info(f"- 5일평균 대비: {current_volume/avg_volume:.2f}배")
        if len(df) > 1:
            prev_volume = df['volume'].iloc[-2]
            logger.info(f"- 전일 대비: {current_volume/prev_volume:.2f}배")
        
        return result
        
    except Exception as e:
        logger.error(f"거래량 분석 중 에러: {str(e)}")
        return None

       
def calculate_trading_fee(price, quantity, is_buy=True):
    """거래 수수료 및 세금 계산"""
    commission_rate = 0.0000156  # 수수료 0.00156%
    # tax_rate = 0.0023  # 매도 시 거래세 0.23%
    tax_rate = 0  # 매도 시 거래세 0%
    special_tax_rate = 0.0015  # 농어촌특별세 (매도금액의 0.15%)
    
    commission = price * quantity * commission_rate
    if not is_buy:  # 매도 시에만 세금 부과
        tax = price * quantity * tax_rate
        special_tax = price * quantity * special_tax_rate
    else:
        tax = 0
        special_tax = 0
    
    return commission + tax + special_tax


def load_today_trade_history():
    """당일 매매 수익 정보 로드"""
    try:
        with open(f"TodayTradeHistory_{BOT_NAME}.json", 'r') as f:
            return json.load(f)
    except:
        return {
            'date': '',
            'trades': []  # 당일 매도 거래 정보 리스트
        }

def save_today_trade_history(history):
    """당일 매매 수익 정보 저장"""
    with open(f"TodayTradeHistory_{BOT_NAME}.json", 'w') as f:
        json.dump(history, f)

def send_daily_trading_report():
    """장마감 시 당일 매매 수익 보고서 생성 및 전송"""
    try:
        trade_history = load_today_trade_history()
        
        if not trade_history['trades']:
            msg = "📊 금일 매매 수익 보고서\n"
            msg += f"========== {datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
            msg += "금일 매도한 종목이 없습니다."
            logger.info(msg)
            discord_alert.SendMessage(msg)
            return

        # 각 거래별 실제 수익 계산 (수수료/세금 포함)
        for trade in trade_history['trades']:
            buy_fee = calculate_trading_fee(trade['entry_price'], trade['amount'], is_buy=True)
            sell_fee = calculate_trading_fee(trade['exit_price'], trade['amount'], is_buy=False)
            total_fee = buy_fee + sell_fee
            
            # 실제 수익 계산
            gross_profit = (trade['exit_price'] - trade['entry_price']) * trade['amount']
            net_profit = gross_profit - total_fee
            net_profit_rate = (net_profit / (trade['entry_price'] * trade['amount'])) * 100
            
            trade['profit_amount'] = net_profit
            trade['profit_rate'] = net_profit_rate
            trade['trading_fee'] = total_fee        
            
        total_profit = sum(trade['profit_amount'] for trade in trade_history['trades'])
        average_profit_rate = sum(trade['profit_rate'] for trade in trade_history['trades']) / len(trade_history['trades'])
        
        msg = "📊 금일 매매 수익 보고서\n"
        msg += f"========== {datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
        msg += f"총 실현수익: {total_profit:,.0f}원\n"
        msg += f"평균 수익률: {average_profit_rate:.2f}%\n\n"
        msg += "종목별 실현 수익:\n"
        
        for trade in trade_history['trades']:
            msg += f"- {trade['stock_name']}({trade['stock_code']}): "
            msg += f"{trade['profit_amount']:,.0f}원 ({trade['profit_rate']:.2f}%)\n"
            msg += f"  매수가: {trade['entry_price']:,.0f}원, "
            msg += f"매도가: {trade['exit_price']:,.0f}원, "
            msg += f"수량: {trade['amount']:,}주\n"
            msg += f"  거래비용: {trade['trading_fee']:,.0f}원\n"
            if 'sell_reason' in trade:  # 매도 사유 표시 추가
                msg += f"  매도사유: {trade['sell_reason']}\n"            
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
    except Exception as e:
        logger.error(f"일일 매매 수익 보고서 생성 중 에러: {str(e)}")

def load_daily_trading_history():
    """당일 매매 이력 로드"""
    try:
        with open(f"DailyTrading_{BOT_NAME}.json", 'r') as f:
            return json.load(f)
    except:
        return {'last_date': '', 'sold_stocks': []}

def save_daily_trading_history(history):
    """당일 매매 이력 저장"""
    with open(f"DailyTrading_{BOT_NAME}.json", 'w') as f:
        json.dump(history, f)

@cached('volume_data')
def get_average_volume(stock_code, days=5):
    """일평균 거래량 계산"""
    try:        
        time.sleep(0.1)
        # days의 2배로 요청하여 충분한 데이터 확보 시도
        df = Common.GetOhlcv("KR", stock_code, days * 2)
        
        if df is None:
            logger.info("거래량 데이터 없음")
            return 0
            
        data_count = len(df)
        logger.info(f"거래량 데이터 수: {data_count}")
        
        if data_count == 0:
            return 0
            
        # 최근 데이터부터 사용 가능한 만큼 사용
        avg_volume = df['volume'].tail(min(days, data_count)).mean()
        logger.info(f"평균 거래량: {avg_volume:,.0f}주 (최근 {min(days, data_count)}일 평균)")
        
        return avg_volume

    except Exception as e:
        logger.error(f"거래량 계산 중 에러: {str(e)}")
        return 0

def check_liquidity(stock_code, amount):
    """유동성 체크 함수"""
    try:
        avg_volume = get_average_volume(stock_code, VOLUME_WINDOW)
        if avg_volume == 0:
            return {
                'is_liquid': False,
                'suggested_amount': 0,
                'avg_volume': 0,
                'volume_ratio': 0,
                'message': "거래량 데이터 부족"
            }

        # 디버그 정보 추가
        volume_ratio = amount / avg_volume if avg_volume > 0 else 0
        logger.info(f"DEBUG: check_liquidity")
        logger.info(f"stock_code: {stock_code}")
        logger.info(f"amount: {amount}")
        logger.info(f"avg_volume: {avg_volume}")
        logger.info(f"MAX_VOLUME_RATIO: {MAX_VOLUME_RATIO}")
        logger.info(f"volume_ratio: {volume_ratio}")

        is_liquid = volume_ratio <= MAX_VOLUME_RATIO
        suggested_amount = min(amount, int(avg_volume * MAX_VOLUME_RATIO))

        message = (f"{VOLUME_WINDOW}일 평균거래량: {avg_volume:,.0f}주\n"
                  f"희망수량 비율: {volume_ratio*100:.1f}%\n"
                  f"최대매수가능: {suggested_amount:,}주")
        
        return {
            'is_liquid': is_liquid,
            'suggested_amount': suggested_amount,
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'message': message
        }
    except Exception as e:
        logger.error(f"유동성 체크 중 에러: {str(e)}")
        return {
            'is_liquid': False,
            'suggested_amount': 0,
            'avg_volume': 0,
            'volume_ratio': 0,
            'message': f"에러 발생: {str(e)}"
        }


def calculate_position_size(available_budget, stock_code, stock_price, atr, current_positions):
    try:
        # atr이 None인 경우 get_stock_data()로부터 다시 가져오기
        if atr is None:
            stock_data = get_stock_data(stock_code)
            if stock_data is None:
                logger.info(f"{stock_code}: 주가 데이터를 가져올 수 없어 포지션 사이징 불가")
                return 0
            
            atr = stock_data.get('atr', 0)  # atr 값 안전하게 가져오기

        # 실시간 잔고 조회를 통해 사용 가능한 현금 확인
        actual_balance = KisKR.GetBalance()
        if actual_balance is None or not isinstance(actual_balance, dict):
            error_msg = f"실시간 계좌 잔고 조회 실패"
            logger.error(error_msg)
            discord_alert.SendMessage(f"⚠️ {error_msg}")
            return 0
            
        actual_remain_money = float(actual_balance.get('RemainMoney', 0))
        stock_name = KisKR.GetStockName(stock_code)
        
        # 실제 가용 자금과 전략 가용 자금 중 작은 값을 사용
        real_available_budget = min(available_budget, actual_remain_money)
        
        if real_available_budget <= 0:
            error_msg = f"⚠️ {stock_name}({stock_code}) 매수 실패 - 실제 가용 자금 부족: {actual_remain_money:,.0f}원"
            logger.info(error_msg)
            discord_alert.SendMessage(error_msg)
            return 0
            
        if real_available_budget < available_budget:
            warning_msg = f"⚠️ {stock_name}({stock_code}) 매수 예산 조정: {available_budget:,.0f}원 → {real_available_budget:,.0f}원 (실제 잔고 기준)"
            logger.info(warning_msg)
            # discord_alert.SendMessage(warning_msg)
            available_budget = real_available_budget

        # 한 종목당 전체 예산의 최대 30%까지만 사용
        max_budget_per_stock = available_budget * MAX_POSITION_SIZE
        
        logger.info(f"예산 계산:")
        logger.info(f"- 총 가용 예산: {available_budget:,.0f}원")
        logger.info(f"- 종목당 최대 예산(30%): {max_budget_per_stock:,.0f}원")
        
        # 주가가 최대 예산을 초과하는 경우에도 1주는 매수 가능하도록 조정
        if max_budget_per_stock < stock_price:
            max_budget_per_stock = stock_price  # 최소 1주는 살 수 있도록 조정
            
        # 실제 사용할 예산
        effective_budget = min(available_budget * 0.9, max_budget_per_stock)
        logger.info(f"- 실제 사용 예산: {effective_budget:,.0f}원")
        
        # 기본 수량 계산
        calculated_amount = int(effective_budget / stock_price)
        logger.info(f"- 계산된 주수: {calculated_amount}주")
        
        # 유동성 체크
        liquidity_check = check_liquidity(stock_code, calculated_amount)
        final_amount = min(calculated_amount, liquidity_check['suggested_amount'])
        
        # 매수 수량이 조정된 경우 알림
        if final_amount < calculated_amount:
            adjustment_msg = f"⚠️ {stock_name}({stock_code}) 유동성 부족으로 매수 수량 조정: {calculated_amount}주 → {final_amount}주"
            logger.info(adjustment_msg)
            discord_alert.SendMessage(adjustment_msg)
        
        # 디버그 정보 추가
        logger.info(f"DEBUG: calculate_position_size")
        logger.info(f"available_budget: {available_budget}")
        logger.info(f"stock_price: {stock_price}")
        logger.info(f"calculated_amount: {calculated_amount}")
        logger.info(f"liquidity_check: {liquidity_check}")
        logger.info(f"final_amount: {final_amount}")
        
        # 1주 이상이면 매수 진행
        if final_amount >= 1:
            # 최종 금액 확인 - 충분한 잔고가 있는지 재확인
            final_cost = final_amount * stock_price
            if final_cost > actual_remain_money:
                warning_msg = f"⚠️ {stock_name}({stock_code}) 최종 매수금액({final_cost:,.0f}원)이 실제 가용자금({actual_remain_money:,.0f}원)을 초과합니다. 매수 수량을 조정합니다."
                logger.warning(warning_msg)
                discord_alert.SendMessage(warning_msg)
                
                # 가능한 최대 수량으로 조정
                adjusted_amount = int(actual_remain_money / stock_price)
                final_amount = adjusted_amount
                
                logger.info(f"조정된 최종 주수: {final_amount}주")
                
            if final_amount < 1:
                error_msg = f"⚠️ {stock_name}({stock_code}) 조정 후 매수 가능 수량이 1주 미만입니다. 매수를 취소합니다."
                logger.info(error_msg)
                discord_alert.SendMessage(error_msg)
                return 0
                
            return final_amount
        
        # 매수 불가능한 경우
        if final_amount < 1:
            error_msg = f"⚠️ {stock_name}({stock_code}) 계산된 매수 수량이 1주 미만입니다. 매수를 취소합니다."
            logger.info(error_msg)
            discord_alert.SendMessage(error_msg)
        
        return final_amount
        
    except Exception as e:
        error_msg = f"⚠️ 포지션 사이징 계산 중 에러: {str(e)}"
        logger.error(error_msg)
        discord_alert.SendMessage(error_msg)
        return 0


def check_trading_time():
    """장중 거래 가능한 시간대인지 체크하고 장 시작 시점도 확인"""
    try:
        # 휴장일 체크
        if KisKR.IsTodayOpenCheck() == 'N':
            logger.info("휴장일 입니다.")
            return False, False

        # 장 상태 확인
        market_status = KisKR.MarketStatus()
        if market_status is None or not isinstance(market_status, dict):
            logger.info("장 상태 확인 실패")
            return False, False
            
        status_code = market_status.get('Status', '')
        
        # 장 시작 시점 체크 (동시호가 '0' 여부로 확인)
        # 장 시작 시점 체크 (동시호가 '0' 여부와 9시 체크)
        current_time = datetime.now().time()
        is_market_open = (status_code == '0' and # 동시호가
                         current_time.hour == 8)
        
        # 거래 가능 시간 체크 ('2'는 장중)
        is_trading_time = (status_code == '2')
        
        # 장 상태 로깅
        status_desc = {
            '': '장 개시전',
            '1': '장 개시전',
            '2': '장중',
            '3': '장 종료후',
            '4': '시간외단일가',
            '0': '동시호가'
        }
        logger.info(f"장 상태: {status_desc.get(status_code, '알 수 없음')}")
        
        return is_trading_time, is_market_open
        
    except Exception as e:
        logger.error(f"거래 시간 체크 중 에러 발생: {str(e)}")
        return False, False

def calculate_macd(df):
    """MACD 계산"""
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calculate_volume_trend(df):
    """거래량 증가 추세 확인"""
    vol_ma = df['volume'].rolling(window=5).mean()
    return df['volume'] > vol_ma


@cached('stock_data')
def get_stock_data(stock_code):
    """종목의 현재가, 보조지표 등 데이터 조회"""
    try:    
        logger.info(f"get_stock_data 함수 호출: {stock_code}")     
        # 현재 시간 확인
        now = datetime.now()
        is_early_morning = is_in_early_morning_session()
        
        # 일봉 데이터
        logger.info(f"{stock_code}: 일봉 데이터 로드 시작")
        df = Common.GetOhlcv("KR", stock_code, 20)  # 20일로 충분
        logger.info(f"{stock_code}: 일봉 데이터 로드 완료. 데이터 크기: {len(df) if df is not None else 'None'}")
        
        # DataFrame 유효성 검사 추가 - 일봉 데이터가 없으면 먼저 체크해서 리턴
        if df is None or len(df) < 5:  # 최소 5개의 일봉 데이터 필요
            logger.error(f"{stock_code}: 일봉 데이터를 가져올 수 없거나 데이터 부족")
            return None
        
        # 장초반에는 분봉 데이터 처리 개선
        minute_df = None
        try:
            logger.info(f"{stock_code}: is_early_morning 상태 = {is_early_morning}")
            if not is_early_morning:
                # 장초반이 아닐 때만 실제 분봉 데이터 로드 시도
                logger.info(f"{stock_code}: 분봉 데이터 로드 직전. KisKR.GetOhlcvMinute 호출 시작")

                # 락 사용: 분봉 데이터 API 호출 시 락 획득
                with api_lock:
                    # 실제 KisKR.GetOhlcvMinute 함수 반환값 확인
                    minute_df = KisKR.GetOhlcvMinute(stock_code, MinSt='5T')
                logger.info(f"{stock_code}: KisKR.GetOhlcvMinute 호출 결과. 타입: {type(minute_df)}, 값: {minute_df is None and 'None' or 'Not None'}")
                
                if minute_df is not None:
                    logger.info(f"{stock_code}: 분봉 데이터 길이: {len(minute_df)}")
                    
                    # 데이터가 충분하면 그대로 사용
                    if len(minute_df) >= 5:  # 최소 5개 이상 분봉 필요
                        logger.info(f"{stock_code}: 분봉 데이터 로드 성공 (길이: {len(minute_df)}개)")
                    else:
                        # 분봉 데이터가 부족한 경우 일봉으로 대체
                        logger.info(f"{stock_code}: 분봉 데이터가 부족함 (길이: {len(minute_df)}개)")
                        rows_to_use = min(5, len(df))  # 최대 5개 사용
                        minute_df = df.head(rows_to_use).copy()
                        minute_df.index = pd.date_range(start=now, periods=rows_to_use, freq='5T')
                        logger.info(f"{stock_code}: 분봉 데이터를 일봉으로 대체함. 대체 길이: {len(minute_df)}개")
                else:
                    # 분봉 데이터가 없는 경우
                    logger.info(f"{stock_code}: 분봉 데이터가 None으로 반환됨")
                    rows_to_use = min(5, len(df))  # 최대 5개 사용
                    minute_df = df.head(rows_to_use).copy()
                    minute_df.index = pd.date_range(start=now, periods=rows_to_use, freq='5T')
                    logger.info(f"{stock_code}: 분봉 데이터 없음, 일봉으로 대체함. 대체 길이: {len(minute_df)}개")
            else:
                # 장초반일 때는 일봉 데이터를 분봉 데이터로 활용 (개선된 부분)
                logger.info(f"{stock_code}: 장초반 시간대 - 일봉 데이터를 분봉 데이터로 변환")
                rows_to_use = min(5, len(df))  # 최대 5개 사용
                minute_df = df.head(rows_to_use).copy()
                minute_df.index = pd.date_range(start=now, periods=rows_to_use, freq='5T')
                logger.info(f"{stock_code}: 장초반용 변환된 분봉 데이터 길이: {len(minute_df)}개")
        except Exception as e:
            logger.error(f"{stock_code} 분봉 데이터 로드 중 에러: {str(e)}")
            logger.error(f"분봉 데이터 에러 스택 트레이스: ", exc_info=True)
            
            # 에러 발생 시 일봉 데이터로 대체
            rows_to_use = min(5, len(df))  # 최대 5개 사용
            minute_df = df.head(rows_to_use).copy()
            minute_df.index = pd.date_range(start=now, periods=rows_to_use, freq='5T')
            logger.info(f"{stock_code}: 에러 발생으로 일봉 데이터로 대체한 분봉 데이터 생성 (길이: {len(minute_df)}개)")

        # 현재가 조회
        current_price = KisKR.GetCurrentPrice(stock_code)
        logger.info(f"{stock_code}: 현재가 = {current_price}")
        
        # 현재가 유효성 검사
        if not current_price or current_price <= 0:
            logger.error(f"{stock_code}: 현재가를 가져올 수 없음")
            return None

        try:
            # RSI 계산
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 0.00001)
            rsi = 100 - (100 / (1 + rs))

            # NaN 체크 추가
            rsi_value = rsi.iloc[-1]
            if pd.isna(rsi_value):
                rsi_value = 50  # NaN일 경우 중립값(50) 사용
            
            # 볼린저밴드 계산
            ma20 = df['close'].rolling(window=20).mean()
            std = df['close'].rolling(window=20).std()
            upper = ma20 + 2 * std
            lower = ma20 - 2 * std
            
            # MACD 계산
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            # ATR 계산
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            atr = true_range.rolling(window=14).mean()
            
            result = {
                'current_price': current_price,
                'ohlcv': df,
                'minute_ohlcv': minute_df,  # 분봉 데이터 추가
                'code': stock_code,
                'rsi': rsi_value,  # NaN 값이 처리된 rsi 값 사용
                'upper_band': upper.iloc[-1],
                'lower_band': lower.iloc[-1],
                'ma5': df['close'].rolling(window=5).mean().iloc[-1],
                'ma10': df['close'].rolling(window=10).mean().iloc[-1],
                'ma20': ma20.iloc[-1],
                'volume': df['volume'].iloc[-1],
                'prev_volume': df['volume'].iloc[-2],
                'volume_ma5': df['volume'].rolling(window=5).mean().iloc[-1],
                'macd': macd.iloc[-1],
                'macd_signal': signal.iloc[-1],
                'prev_macd': macd.iloc[-2],
                'prev_macd_signal': signal.iloc[-2],
                'atr': atr.iloc[-1],
                'close': df['close'].iloc[-1],
                'prev_close': df['close'].iloc[-2],
                'low': df['low'].iloc[-1]
            }
            
            # 결과 minute_ohlcv 값 최종 확인
            if result['minute_ohlcv'] is None:
                logger.warning(f"{stock_code}: 최종 분봉 데이터가 None - 이는 정상적이지 않은 상황입니다")
            else:
                logger.info(f"{stock_code}: 최종 분봉 데이터 길이: {len(result['minute_ohlcv'])}개")

            return result
        
        except Exception as e:
            logger.error(f"주가 데이터 계산 중 에러: {stock_code}, {str(e)}")
            return None
        
    except Exception as e:
        logger.error(f"주가 데이터 조회 중 에러: {str(e)}")
        return None
    


# 4. 모멘텀 점수 계산의 NaN 처리 및 일관성 개선
def check_momentum_conditions(stock_data, return_score=False):
    """모멘텀 조건 체크 - NaN 처리 개선"""
    if stock_data is None:
        return (False, 0) if return_score else False
        
    try:    
        # 타입 체크 추가
        if not isinstance(stock_data, dict):
            logger.error(f"Invalid stock_data type: {type(stock_data)}")
            return (False, 0) if return_score else False
            
        # 필수 필드 검증
        required_fields = ['code', 'current_price', 'ohlcv']
        for field in required_fields:
            if field not in stock_data:
                logger.error(f"Missing required field: {field}")
                return (False, 0) if return_score else False

        stock_code = stock_data['code']
        df = stock_data['ohlcv']  # 이미 DataFrame으로 로드된 데이터 사용
        
        # 현재 시간 확인
        is_morning_session = is_in_morning_session()
        is_early_morning = is_in_early_morning_session()
        
        # 데이터 요구사항 동적 조정
        min_data_points = 3 if is_early_morning else 8
        
        # DataFrame 검증
        if df is None or len(df) < min_data_points:
            logger.info(f"분봉 데이터 부족 ({len(df) if df is not None else 0}개 < {min_data_points}개)")
            return (False, 0) if return_score else False

        momentum_score = 0
        score_details = []

        logger.info(f"\n=== {stock_code} 상세 모멘텀 분석 ===")
        logger.info(f"시간대: {'장초반' if is_early_morning else '오전장' if is_morning_session else '일반'}")

        # MACD 분석 (30점)
        macd_score = 0
        try:
            if 'minute_ohlcv' in stock_data and stock_data['minute_ohlcv'] is not None and len(stock_data['minute_ohlcv']) >= 10:
                minute_df = stock_data['minute_ohlcv']
                
                # 단타용 더 짧은 주기의 MACD
                short_span = 4
                long_span = 9
                
                exp1 = minute_df['close'].ewm(span=short_span, adjust=False).mean()
                exp2 = minute_df['close'].ewm(span=long_span, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=3, adjust=False).mean()
            else:
                # 분봉 데이터 없으면 기존 일봉 MACD 사용
                short_span = 8 if is_early_morning else 12
                long_span = 17 if is_early_morning else 26
                
                exp1 = df['close'].ewm(span=short_span, adjust=False).mean()
                exp2 = df['close'].ewm(span=long_span, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()

            # NaN 값 체크 및 안전 처리
            macd_current = macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0
            macd_prev = macd.iloc[-2] if len(macd) > 1 and not pd.isna(macd.iloc[-2]) else 0
            signal_current = signal.iloc[-1] if not pd.isna(signal.iloc[-1]) else 0
            
            macd_diff = macd_current - signal_current
            macd_change = macd_current - macd_prev
            
            logger.info(f"MACD 분석:")
            logger.info(f"- MACD/Signal 차이: {macd_diff:.3f}")
            logger.info(f"- MACD 변화량: {macd_change:.3f}")

            if macd_diff > 0:
                macd_score += 15
                score_details.append("MACD > Signal (+15)")
            elif is_morning_session and macd_diff > -0.3:  # 오전장 조건 완화
                macd_score += 10
                score_details.append("MACD 근접 (+10)")
            
            if macd_change > 0:
                macd_score += 10
                score_details.append("MACD 상승중 (+10)")
                
            momentum_score += macd_score
            
        except Exception as e:
            logger.error(f"MACD 분석 중 에러: {str(e)}")

        # 이동평균선 분석 (20점)
        ma_score = 0
        try:
            current_price = df['close'].iloc[-1]
            
            # 최소 기간 설정으로 NaN 방지
            ma5 = df['close'].rolling(window=5, min_periods=1).mean()
            ma20 = df['close'].rolling(window=20, min_periods=1).mean()
            
            # NaN 값 확인 및 처리
            ma5_current = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else current_price
            ma20_current = ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else current_price
            
            # 안전한 비율 계산
            price_ma5_ratio = current_price / ma5_current if ma5_current > 0 else 1
            price_ma20_ratio = current_price / ma20_current if ma20_current > 0 else 1
            
            # 연속 양봉 패턴
            bullish_candles = df[df['close'] > df['open']]
            bullish_ratio = len(bullish_candles) / len(df) if len(df) > 0 else 0
            
            # 장기 추세 변화 감지 (신규 로직)
            long_term_trend_change = (
                current_price > ma20_current and  # 20일선 상향 돌파
                bullish_ratio > 0.6  # 60% 이상 양봉
            )
            
            logger.info(f"이동평균선 분석:")
            logger.info(f"- 현재가/MA5 비율: {price_ma5_ratio:.3f}")
            logger.info(f"- 현재가/MA20 비율: {price_ma20_ratio:.3f}")
            
            if price_ma5_ratio > 1.001:
                ma_score += 10
                score_details.append("MA5 상향돌파 (+10)")
            elif is_morning_session and 0.995 < price_ma5_ratio <= 1.001:
                ma_score += 5
                score_details.append("MA5 근접 (+5)")
            
            if current_price > ma20_current:
                ma_score += 10
                score_details.append("MA20 상향 (+10)")
            elif is_morning_session and 0.99 < price_ma20_ratio <= 1:
                ma_score += 5
                score_details.append("MA20 근접 (+5)")
            
            # 추세 반전 시 추가 점수
            if long_term_trend_change:
                ma_score += 5
                score_details.append("장기 추세 반전 (+5)")
            
            momentum_score += ma_score
            
        except Exception as e:
            logger.error(f"이동평균 분석 중 에러: {str(e)}")

        # 거래대금 분석 섹션 추가
        turnover_score = 0
        try:
            # 거래대금 조회
            turnover = calculate_turnover(stock_data['code'])
            
            # 최근 5일 평균 거래대금 계산
            df = stock_data['ohlcv']
            avg_turnover = df['volume'].mean() * df['close'].mean()  # 거래대금 = 거래량 * 종가
            
            # 거래대금 비율 계산
            turnover_ratio = turnover / avg_turnover if avg_turnover > 0 else 0
            
            # 로깅
            logger.info(f"\n거래대금 분석:")
            logger.info(f"- 현재 거래대금: {turnover:,.0f}원")
            logger.info(f"- 평균 거래대금: {avg_turnover:,.0f}원")
            logger.info(f"- 거래대금 비율: {turnover_ratio:.2f}배")
            
            # 거래대금 점수 계산
            if turnover_ratio >= 2.0:  # 평균 대비 2배 이상
                turnover_score += 15
                logger.info(f"거래대금 점수: {turnover_score}/15 (2배 이상)")
            elif turnover_ratio >= 1.5:  # 평균 대비 1.5배 이상
                turnover_score += 10
                logger.info(f"거래대금 점수: {turnover_score}/15 (1.5배 이상)")
            elif turnover_ratio >= 1.2:  # 평균 대비 1.2배 이상
                turnover_score += 5
                logger.info(f"거래대금 점수: {turnover_score}/15 (1.2배 이상)")
            
            # 모멘텀 점수에 거래대금 점수 추가
            momentum_score += turnover_score
            
        except Exception as e:
            logger.error(f"거래대금 분석 중 에러: {str(e)}")

        # 거래량 분석 (25점)
        volume_score = 0
        try:
            current_volume = df['volume'].iloc[-1] if not pd.isna(df['volume'].iloc[-1]) else 0
            volume_ma5 = df['volume'].rolling(window=5, min_periods=1).mean()
            volume_ma5_value = volume_ma5.iloc[-1] if not pd.isna(volume_ma5.iloc[-1]) else 1
            
            # 0으로 나누기 방지
            if volume_ma5_value <= 0:
                volume_ma5_value = 1
                
            volume_ratio = current_volume / volume_ma5_value
            
            # 가중치를 적용한 거래량 점수 계산
            volume_trend_factor = 1 + (volume_ratio - 1) * 1.5  # 추세 반영 인자
            
            logger.info(f"거래량 분석:")
            logger.info(f"- 5일평균 대비: {volume_ratio:.2f}배")
            
            # 시간대별 거래량 기준 조정
            if is_early_morning:
                if volume_ratio >= 1.5:
                    volume_score += int(15 * volume_trend_factor)
                    score_details.append(f"거래량 5일평균 {volume_ratio:.1f}배 (+{int(15 * volume_trend_factor)})")
            else:
                if volume_ratio >= 1.8:
                    volume_score += int(15 * volume_trend_factor)
                    score_details.append(f"거래량 5일평균 {volume_ratio:.1f}배 (+{int(15 * volume_trend_factor)})")
            
            # 거래량 점수에 상한선 설정
            volume_score = min(volume_score, 25)
            momentum_score += volume_score
                
        except Exception as e:
            logger.error(f"거래량 분석 중 에러: {str(e)}")

        # RSI 분석 (15점)
        rsi_score = 0
        try:
            # 시간대별 RSI 범위 조정 (개선된 부분)
            if is_early_morning:
                # 장초반에는 더 넓은 RSI 범위 허용
                rsi_lower = MIN_EARLY_MORNING_BUY_RSI
                rsi_upper = MAX_EARLY_MORNING_BUY_RSI
            else:
                # 일반 시간대에는 약간 완화된 범위
                rsi_lower = MIN_BUY_RSI
                rsi_upper = MAX_BUY_RSI

            # RSI 계산 - 안전한 방식
            rsi_period = 14
            delta = df['close'].diff().fillna(0)  # NaN 값 자동 처리
            
            if len(df) >= rsi_period + 1:
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                
                # min_periods=1 추가로 데이터 부족시 NaN 방지
                avg_gain = gain.rolling(window=rsi_period, min_periods=1).mean()
                avg_loss = loss.rolling(window=rsi_period, min_periods=1).mean()
                
                # 0으로 나누기 방지
                rs = avg_gain / avg_loss.replace(0, 0.00001)
                rsi = 100 - (100 / (1 + rs))
                
                # 마지막 값이 NaN인 경우 처리
                current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
                rsi_direction = True  # 기본값 설정
                
                if len(rsi) >= 2 and not pd.isna(rsi.iloc[-2]):
                    rsi_direction = current_rsi > rsi.iloc[-2]
                
                logger.info(f"RSI 분석: {current_rsi:.1f}")

                # 여기에 새로운 로직 추가
                if rsi_lower < current_rsi < rsi_upper:
                    rsi_score += 10
                    # 추가: RSI가 70 이상이면 점수 페널티
                    if current_rsi > 70:
                        rsi_score -= 5  # RSI 70 이상일 경우 점수 차감
                        logger.info(f"RSI 70 이상으로 점수 차감: {rsi_score}")
                
                if rsi_lower < current_rsi < rsi_upper:
                    rsi_score += 10
                    score_details.append("RSI 적정구간 (+10)")
                
                # RSI 방향성 점수 추가
                if rsi_direction and not pd.isna(current_rsi):
                    rsi_score += 5
                    score_details.append("RSI 상승중 (+5)")
                
                momentum_score += rsi_score
            else:
                logger.info("RSI 계산을 위한 데이터 부족")
                
        except Exception as e:
            logger.error(f"RSI 분석 중 에러: {str(e)}")

        # 시간대별 점수 기준 조정
        # required_score = 35 if is_early_morning else 45 if is_morning_session else 55
        required_score = 30 if is_early_morning else 38 if is_morning_session else 55  # 기존 35/45/55에서 완화

        # 거래량 조건 추가 - 이 부분을 추가
        if volume_score < 10:  # 거래량 점수가 10점 미만인 경우
            # 오전장은 거래량이 적을 수 있으므로 예외 처리
            if not is_early_morning and momentum_score < 60:  # 다른 지표가 매우 강하지 않다면
                logger.info(f"거래량 점수 부족 ({volume_score}/25점) 및 총점도 충분히 높지 않음 ({momentum_score}/100점)")
                return (False, momentum_score) if return_score else False

        # RSI 상한 조정 추가 - 이 부분도 추가
        if 'current_rsi' in locals() and current_rsi > 65:  # RSI가 65 이상인 경우
            # 오전장이 아닌 경우에만 요구 점수 상향
            if not is_morning_session:
                additional_required = 10
                logger.info(f"RSI 과매수 근접 ({current_rsi:.1f}): 요구 점수 +{additional_required}점 상향")
                required_score += additional_required

        # 최종 점수 출력
        logger.info(f"\n=== {stock_code} 최종 모멘텀 점수 ===")
        logger.info(f"총점: {momentum_score}/100점 (기준: {required_score}점)")
        logger.info(f"- MACD 점수: {macd_score}/30")
        logger.info(f"- 이동평균 점수: {ma_score}/20")
        logger.info(f"- 거래량 점수: {volume_score}/25")
        logger.info(f"- RSI 점수: {rsi_score}/15")
        
        logger.info(f"\n[{stock_code} 세부 판단근거]")
        for detail in score_details:
            logger.info(f"- {detail}")

        passed = momentum_score >= required_score
        logger.info(f"\n최종 판정: {'통과' if passed else '미달'}")

        # 모멘텀 점수 캐싱 - 호가분석에서 활용하기 위해
        if passed:
            cache_key = f"{stock_code}_momentum_score"
            cache_manager = CacheManager.get_instance()
            cache_manager.set('momentum_data', cache_key, {
                'score': momentum_score,
                'time': time.time()
            })

        # 수정된 부분: return_score 파라미터에 따라 반환값 형태 변경
        return (passed, momentum_score) if return_score else passed

    except Exception as e:
        # 안전한 예외 처리
        logger.error(f"모멘텀 체크 중 에러 발생: {str(e)}")
        return (False, 0) if return_score else False


def load_detected_stocks():
    """이전 포착 종목 로드"""
    try:
        with open(f"DetectedStocks_{BOT_NAME}.json", 'r') as f:
            return json.load(f)
    except:
        return {'last_date': '', 'stocks': []}

def save_detected_stocks(state):
    """포착 종목 저장"""
    with open(f"DetectedStocks_{BOT_NAME}.json", 'w') as f:
        json.dump(state, f)

def calculate_turnover(stock_code):
    """거래대금 계산"""
    try:
        # 거래대금 순위 조회 (코스피 시장, 상위 종목)
        trading_volume_stocks = KisKR.GetVolumeRank(
            market_code="J",  # 코스피
            vol_type="20172",  # 거래대금 기준
            top_n=100,  # 충분히 많은 종목 확인
            max_price=150000  # 주가 제한
        )
        
        # 해당 종목의 거래대금 찾기
        for stock in trading_volume_stocks:
            if stock['code'] == stock_code:
                logger.info(f"{stock_code} 거래대금: {stock['volume']:,.0f}원")
                return stock['volume']
        
        logger.info(f"{stock_code} 거래대금 데이터 없음")
        return 0
    
    except Exception as e:
        logger.error(f"거래대금 계산 중 에러: {str(e)}")
        return 0        

def calculate_rise_rate(stock_data):
    """상승률 계산"""
    try:
        current_price = stock_data['current_price']
        df = stock_data['ohlcv']
        
        if current_price <= 0 or df is None or len(df) == 0:
            return 0
            
        start_price = float(df['open'].iloc[0])
        if start_price <= 0:
            return 0
            
        rise_rate = ((current_price - start_price) / start_price) * 100
        logger.info(f"시가: {start_price:,.0f}원, 현재가: {current_price:,.0f}원, 상승률: {rise_rate:.2f}%")
            
        return rise_rate
        
    except Exception as e:
        logger.error(f"상승률 계산 중 에러: {str(e)}")
        return 0
    
@cached('sector_info')
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


def scan_hong_strategy_stocks(stock_list=None, is_morning_session=False, is_early_morning=False, min_rise_rate=MIN_RISE_RATE):
   """
   홍인기 전략 기반 종목 스캔
   
   Args:
       stock_list (list): 이미 필터링된 종목 리스트
       is_morning_session (bool): 오전장 여부
       is_early_morning (bool): 장초반 여부
       min_rise_rate (float): 최소 상승률 기준 (완화된 기준이 전달될 수 있음)
   """
   try:
       hong_stocks = []
       current_scan_detected = set()  # 현재 스캔에서 이미 처리된 종목

       if not stock_list:
           return []

       # 당일 매도 종목 체크
       daily_trading = load_daily_trading_history()
       sold_stocks = daily_trading.get('sold_stocks', [])

       if sold_stocks:
           logger.info(f"\n당일 매도 제외 종목: {len(sold_stocks)}개")        

       # 이전 포착 종목 로드
       detected_stocks = load_detected_stocks()
       previously_detected = set()  # 이전 포착 종목 저장용 set
       if detected_stocks and 'stocks' in detected_stocks:
           previously_detected = {stock.get('code') for stock in detected_stocks['stocks']}

       candidates = []
       for stock in stock_list:
           try:
               stock_code = stock['code']
               
               # 당일 매도 종목 스킵
               if stock_code in sold_stocks:
                   logger.info(f"{stock['name']}({stock_code}) - 당일 매도 종목으로 스킵")
                   continue

               current_price = KisKR.GetCurrentPrice(stock_code)
               df = KisKR.GetStockOpenPrice(stock_code)
               
               # DataFrame 유효성 검사 추가
               if df is None or df.empty:
                   logger.info(f"{stock_code}: 시가 데이터를 가져올 수 없습니다.")
                   continue

               stock_data = {
                   'current_price': current_price,
                   'ohlcv': df
               }
               
               # 상승률 계산 (calculate_rise_rate 함수를 사용)
               rise_rate = calculate_rise_rate(stock_data)
               
               # min_rise_rate 이상 상승한 종목만 필터링
               if rise_rate >= min_rise_rate:
                   sector_info = get_sector_info(stock_code)
                   if sector_info and sector_info.get('industry'):
                       candidates.append({
                           'code': stock_code,
                           'name': stock['name'],
                           'rise_rate': rise_rate,
                           'price': current_price,
                           'sector': sector_info['sector'],
                           'industry': sector_info['industry']
                       })

                       # 이전에 포착되지 않은 종목만 알림
                       if stock_code not in previously_detected:
                           logger.info(f">>> [신규 포착] {stock['name']}")
                           logger.info(f"    섹터: {sector_info['sector']}")
                           logger.info(f"    산업: {sector_info['industry']}")
                           logger.info(f"    상승률: {rise_rate:.1f}%")
                       else:
                           logger.info(f">>> [기존 포착] {stock['name']}")

           except Exception as e:
               logger.error(f"종목 {stock_code} 분석 중 에러: {str(e)}")
               continue

       # 산업별 상승 종목 그룹화
       industry_data = {}
       for stock in candidates:
           industry = stock['industry']
           if industry not in industry_data:
               industry_data[industry] = []
           industry_data[industry].append(stock)
           
       # 주도 산업 내 상위 종목 선정 (3종목 이상 상승한 산업)
       for industry, stocks in industry_data.items():
           if len(stocks) >= MIN_INDUSTRY_COUNT:  # 3종목 이상
               sorted_stocks = sorted(stocks, key=lambda x: x['rise_rate'], reverse=True)
               
               for stock in sorted_stocks[:2]:  # 상위 2종목만
                   # 현재 스캔에서 이미 처리된 종목은 스킵
                   if stock['code'] in current_scan_detected:
                       continue

                   stock_data = get_stock_data(stock['code'])

                   logger.info(f"stock_data 타입: {type(stock_data)}")
                   logger.info(f"stock_data 내용: {stock_data}")

                   if stock_data is not None:
                       stock_info = {
                           'code': stock['code'],
                           'name': stock['name'],
                           'price': stock['price'],
                           'rise_rate': stock['rise_rate'],
                           'sector': stock['sector'],
                           'industry': stock['industry'],
                           'volume_ratio': stock_data['volume'] / stock_data['prev_volume'],
                           'rsi': stock_data['rsi'],
                           'atr': stock_data['atr'],
                           'strategy': 'hong'
                       }
                       hong_stocks.append(stock_info)
                       current_scan_detected.add(stock['code'])  # 현재 스캔에서 처리 완료 표시

                       # 이전에 포착되지 않은 종목만 알림
                       if stock['code'] not in previously_detected:
                           msg = "🎯 홍인기전략 신규 포착 종목:\n"
                           msg += f"- {stock['name']}({stock['code']})\n"
                           msg += f"  현재가: {stock['price']:,}원\n"
                           msg += f"  상승률: {stock['rise_rate']:.1f}%\n"
                           msg += f"- 산업: {industry} (산업 내 상승종목: {len(stocks)}개)"
                           logger.info(msg)
                        #    discord_alert.SendMessage(msg)
       
       return hong_stocks  # 함수의 마지막에 hong_stocks 반환
           
   except Exception as e:
       logger.error(f"홍인기 전략 스캔 중 에러 발생: {str(e)}")
       return []  # 에러 발생시 빈 리스트 반환


def process_stock_chunk(stocks_chunk, momentum_stocks, sold_stocks, previous_codes):
    """단일 청크 처리 함수 - 디버깅 강화"""
    # 현재 시간 체크
    now = datetime.now()
    chunk_results = []

    for stock in stocks_chunk:
        try:
            stock_code = stock['code']
            logger.info(f"\n>>> 종목 분석 시작: {stock['name']}({stock_code})")

            # 기본 체크
            if any(s['code'] == stock_code for s in momentum_stocks):
                logger.info(f"- 이미 선정된 종목으로 스킵")
                continue
            if stock_code in sold_stocks:
                logger.info(f"- 당일 매도 종목으로 스킵")
                continue

            # 주가 데이터 로드 시점 확인
            logger.info("- 주가 데이터 로드 시도...")
            stock_data = get_stock_data(stock_code)
            

            if stock_data is None:
                logger.info("  -> 주가 데이터 로드 실패")
                continue
            logger.info("  -> 주가 데이터 로드 성공")

            # stock_data에 필수 필드 추가 및 확인
            stock_data['code'] = stock_code
            mandatory_fields = ['code', 'current_price', 'volume', 'volume_ma5', 'rsi', 'macd', 'macd_signal']
            missing_fields = [field for field in mandatory_fields if field not in stock_data]
            if missing_fields:
                logger.info(f"  -> 필수 필드 누락: {missing_fields}")
                continue
            logger.info("  -> 필수 필드 확인 완료")

            # 모멘텀 조건 체크
            logger.info("- 모멘텀 조건 체크 시작...")
            
            # momentum_score 초기화
            momentum_score = 0
            
            result = check_momentum_conditions(stock_data)
            if isinstance(result, tuple):
                passed_momentum, momentum_score = result
            else:
                passed_momentum = result
            
            logger.info(f"  -> 모멘텀 체크 결과: {'통과' if passed_momentum else '실패'}")

            if passed_momentum:
                # 고점 근접 체크
                logger.info("- 고점 근접 체크...")

                if not check_buy_conditions(stock_data):
                    #logger.info(f"{stock['name']}({stock_code}) - 고점 근접으로 제외")
                    
                    # 모멘텀 점수가 높은 경우 저장
                    if momentum_score >= HIGH_MOMENTUM_SCORE_THRESHOLD:
                        save_high_momentum_missed_stocks(stock_data, momentum_score, "고점 근접도 불충족")
                    
                    continue
                logger.info("  -> 고점 체크(check_buy_conditions 함수 실행결과) 통과")

                # 최종 선정
                logger.info(f">>> {stock['name']} - 모든 조건 통과!")
                avg_volume = get_average_volume(stock_code, VOLUME_WINDOW)
                
                stock_info = {
                    'code': stock_code,
                    'name': stock['name'],
                    'price': stock_data['current_price'],
                    'volume_ratio': stock_data['volume'] / stock_data['prev_volume'],
                    'avg_volume': avg_volume,
                    'rsi': stock_data['rsi'],
                    'atr': stock_data['atr'],
                    'strategy': 'momentum',
                    'momentum_score': momentum_score  # 모멘텀 점수 추가
                }
                chunk_results.append(stock_info)

                # 신규 포착 알림
                if stock_code not in previous_codes:
                    msg = f"🎯 새로운 모멘텀 포착! - {stock['name']}({stock_code})\n"
                    msg += f"- 현재가: {stock_data['current_price']:,}원\n"
                    msg += f"- 거래량: {stock_data['volume']:,}주 "
                    msg += f"(평균 대비 {stock_data['volume']/avg_volume*100:.1f}%)\n"
                    msg += f"- RSI: {stock_data['rsi']:.1f}\n"
                    msg += f"- 모멘텀 점수: {momentum_score}"
                    logger.info(msg)

        except Exception as e:
            logger.error(f"종목 {stock_code if 'stock_code' in locals() else 'Unknown'} 처리 중 에러: {str(e)}")
            continue
            
    return chunk_results


############# 장 초반 종목 스캔 (9:00~9:20)#############

@cached('volume_rank')
def get_early_morning_stocks():
    """
    장 초반(9시-9시20분) 거래량 기반 종목 선별 함수
    - 코스피, 코스닥 거래량 상위 종목 필터링
    - 상승종목 + 거래량 급증 종목 중심으로 선별
    
    Returns:
        list: 선별된 종목 목록
    """
    try:
        logger.info("\n=== 장 초반 거래량 순위 기준 적용 ===")
        
        # KOSPI, KOSDAQ 거래량 순위 상위 종목 가져오기
        kospi_volume_stocks = KisKR.GetVolumeRank(market_code="J", vol_type="20171", top_n=15, max_price=MAX_STOCK_PRICE)
        #kosdaq_volume_stocks = KisKR.GetVolumeRank(market_code="U", vol_type="20171", top_n=15, max_price=MAX_STOCK_PRICE)
        
        # 두 리스트 합치기
        #volume_rank_stocks = kospi_volume_stocks + kosdaq_volume_stocks
        volume_rank_stocks = kospi_volume_stocks
        
        # 상승률이 양수인 종목만 필터링 (하락 종목 제외)
        volume_rank_stocks = [stock for stock in volume_rank_stocks if stock['change_rate'] > 0]
        
        # 거래량 비율(전일대비)이 높은 순으로 정렬
        volume_rank_stocks.sort(key=lambda x: x['volume_ratio'], reverse=True)
        
        # 이 종목들을 stock_list 형식에 맞게 변환
        stock_list = []
        for stock in volume_rank_stocks:
            stock_list.append({
                'code': stock['code'],
                'name': stock['name'],
                'current_price': stock['price'],
                'volume': stock['volume'],
                'volume_ratio': stock['volume_ratio'],
                'price_change': stock['change_rate']
            })
        
        logger.info(f"거래량 순위 기준 {len(stock_list)}개 종목 로드 완료")
        for i, stock in enumerate(stock_list[:5]):  # 상위 5개만 로깅
            logger.info(f"{i+1}. {stock['name']}({stock['code']}) - 거래량 {stock['volume']:,}주, 상승률 {stock['price_change']}%, 거래량비율 {stock['volume_ratio']}배")
        
        return stock_list
        
    except Exception as e:
        logger.error(f"거래량 순위 종목 로드 중 에러: {str(e)}")
        return []
    

def filter_early_momentum_stocks(stock_list):
    """
    장 초반 모멘텀 종목 필터링 함수 - 개선버전
    """
    filtered_stocks = []
    
    for stock in stock_list:
        try:
            # 기본 필터링 조건 (약간 강화)
            if (
                # stock['volume_ratio'] >= 1.5 and  # 전일 대비 거래량 1.5배 이상 (기존 1.2배)
                # stock['price_change'] >= 2.0      # 상승률 2.0% 이상 (기존 1.5%)
                stock['volume_ratio'] >= 1.2 and  # 전일 대비 거래량 1.2배 이상 (기존 1.5배)
                stock['price_change'] >= 1.5      # 상승률 1.5% 이상 (기존 2.0%)
            ):
                # 추가 정보 조회
                stock_data = get_stock_data(stock['code'])
                
                if stock_data is not None:
                    # RSI 확인 (하한선 추가)
                    if stock_data['rsi'] <= MAX_BUY_RSI and stock_data['rsi'] >= 30:  # RSI 하한 추가
                        # 호가 정보 확인 (추가)
                        is_favorable, order_info = analyze_order_book(stock['code'])
                        
                        # 호가가 불리한 경우 제외 (추가)
                        # if not is_favorable:
                        #     logger.info(f"{stock['name']}({stock['code']}) - 호가 불리로 제외")
                        #     continue
                        if not is_favorable and order_info.get('order_strength', 0) < 0.3:  # 극단적으로 불리한 경우만 거부
                            logger.info(f"{stock['name']}({stock['code']}) - 호가 매우 불리로 제외")
                            continue

                        # 모든 조건 통과 시 추가
                        stock_info = {
                            'code': stock['code'],
                            'name': stock['name'],
                            'price': stock['current_price'],
                            'volume_ratio': stock['volume_ratio'],
                            'rise_rate': stock['price_change'],
                            'rsi': stock_data['rsi'],
                            'atr': stock_data.get('atr', 0),
                            'strategy': 'early_momentum'
                        }
                        filtered_stocks.append(stock_info)
                        
                        # 실시간 로깅
                        logger.info(f"✅ 장 초반 모멘텀 포착: {stock['name']}({stock['code']})")
                        logger.info(f"   거래량: {stock['volume_ratio']}배, 상승률: {stock['price_change']}%")
        
        except Exception as e:
            logger.error(f"모멘텀 필터링 중 에러 ({stock['code']}): {str(e)}")
    
    # 모멘텀 스코어로 정렬 (추가)
    filtered_stocks.sort(key=lambda x: x['volume_ratio'] * x['rise_rate'], reverse=True)
    
    # 결과 요약 로깅
    if filtered_stocks:
        logger.info(f"\n✅ 장 초반 모멘텀 {len(filtered_stocks)}개 종목 감지")
        
    return filtered_stocks  


def check_continuous_uptrend(stock_code, min_candles=3):
    """
    최근 연속 상승 패턴 확인 - 장 초반 매수 강화용 (개선버전)
    """
    try:
        # 현재 시간이 장 초반인지 확인
        now = datetime.now()
        is_early_morning = is_in_early_morning_session()
        is_very_early = now.hour == 9 and now.minute < 20  # 9시 20분 이전
        
        # 매우 이른 시간대(9:20 이전)에는 시가 대비 현재가로 빠른 판단
        if is_very_early:
            current_price = KisKR.GetCurrentPrice(stock_code)
            open_price_df = KisKR.GetStockOpenPrice(stock_code)
            
            # DataFrame 유효성 체크 추가
            if open_price_df is not None and not open_price_df.empty:
                # 시가 데이터에서 값을 안전하게 추출
                open_price = open_price_df['open'].iloc[-1] if 'open' in open_price_df.columns else 0
                
                if open_price > 0 and current_price > open_price:
                    # 시가 대비 상승률 계산
                    open_price_ratio = (current_price - open_price) / open_price * 100
                    
                    # 시가 대비 1% 이상 상승하면 패턴 인정
                    if open_price_ratio >= 1.0:
                        logger.info(f"{stock_code}: 장초반 시가대비 {open_price_ratio:.1f}% 상승 패턴 인정")
                        return True
            
            # 호가 정보 추가 활용 (9시 20분 이전)
            is_favorable, order_info = analyze_order_book(stock_code)
            if isinstance(order_info, dict) and is_favorable:
                # 매수세가 강하면 패턴 인정
                if order_info.get('order_strength', 0) > 1.5:
                    logger.info(f"{stock_code}: 장초반 매수세 강함 (호가비율: {order_info.get('order_strength', 0):.1f})")
                    return True
        
        # 분봉 데이터 가져오기 (1분봉)
        minute_data = KisKR.GetOhlcvMinute(stock_code, MinSt='1T')
        
        # 시간대별 분봉 요구사항 차별화
        required_candles = min_candles
        if is_early_morning:
            # 장 초반 9시대에는 분봉 요구사항 완화
            if now.minute < 30:  # 9:30 이전
                required_candles = 2  # 2개 분봉만 있어도 패턴 인정
        
        # 분봉 데이터 부족 시 일봉 데이터 활용
        if minute_data is None or len(minute_data) < required_candles:
            # 장 초반 또는 분봉 데이터가 부족한 경우 일봉 데이터로 대체
            daily_data = KisKR.GetOhlcv("KR", stock_code, 5)
            if daily_data is not None and len(daily_data) >= 3:
                # 최근 3일 상승 패턴 확인 (완화된 조건)
                # 1) 마지막 종가 > 전일 종가 (어제보다 상승)
                is_rising_today = daily_data['close'].iloc[-1] > daily_data['close'].iloc[-2]
                
                # 2) 추가 조건: 2일 연속 상승 또는 3일 중 2일 상승
                two_day_uptrend = daily_data['close'].iloc[-2] > daily_data['close'].iloc[-3]
                three_day_two_up = (daily_data['close'].iloc[-1] > daily_data['close'].iloc[-3])
                
                # 장초반에는 완화된 조건: 오늘 상승 중 + (2일 연속 상승 또는 3일 중 상승)
                daily_pattern_detected = is_rising_today and (two_day_uptrend or three_day_two_up)
                
                if daily_pattern_detected:
                    logger.info(f"{stock_code}: 일봉 기반 상승 패턴 감지")
                
                return daily_pattern_detected
                
            # 데이터 부족하고 장초반 9시 30분 이전이면 호가 기반 판단
            if is_early_morning and now.minute < 30:
                # 최소한의 정보로 판단: 호가 정보 재확인
                is_favorable, order_info = analyze_order_book(stock_code)
                if isinstance(order_info, dict) and order_info.get('order_strength', 0) > 1.2:
                    logger.info(f"{stock_code}: 분봉 부족, 호가 정보로 판단 (강도: {order_info.get('order_strength', 0):.1f})")
                    return True
                    
            return False  # 데이터 부족
        
        # 최근 캔들 데이터
        recent_candles = minute_data.tail(required_candles)
        
        # 상승 패턴 확인 (장 초반에는 완화된 조건)
        if is_early_morning:
            # 마지막 캔들이 양봉인지 확인
            last_candle_bullish = recent_candles['close'].iloc[-1] > recent_candles['open'].iloc[-1]
            
            # 마지막 캔들이 직전 캔들보다 높은지
            price_rising = recent_candles['close'].iloc[-1] > recent_candles['close'].iloc[-2]
            
            # 거래량 증가 여부
            volume_increasing = False
            if len(recent_candles) >= 2:
                volume_increasing = recent_candles['volume'].iloc[-1] > recent_candles['volume'].iloc[-2]
            
            # 장 초반 완화된 패턴 기준
            early_morning_pattern = (
                (last_candle_bullish and price_rising) or  # 마지막 캔들이 양봉이고 상승 중
                (last_candle_bullish and volume_increasing)  # 마지막 캔들이 양봉이고 거래량 증가
            )
            
            if early_morning_pattern:
                logger.info(f"{stock_code}: 장 초반 완화된 상승 패턴 감지")
                
            return early_morning_pattern
            
        else:
            # 일반 시간대는 기존 로직대로 더 엄격한 패턴 확인
            price_rising = True
            for i in range(1, len(recent_candles)):
                if recent_candles['close'].iloc[i] <= recent_candles['close'].iloc[i-1]:
                    price_rising = False
                    break
                    
            # 마지막 캔들이 양봉인지 확인
            last_candle_bullish = recent_candles['close'].iloc[-1] > recent_candles['open'].iloc[-1]
            
            # 거래량 증가 여부
            volume_increasing = False
            if len(recent_candles) >= 3:
                avg_volume = recent_candles['volume'].iloc[:-1].mean()
                volume_increasing = recent_candles['volume'].iloc[-1] > avg_volume
            
            # 일반 시간대 패턴 확인 - 더 엄격함
            normal_pattern = (
                price_rising or 
                (last_candle_bullish and volume_increasing and recent_candles['close'].iloc[-1] > recent_candles['close'].iloc[-2])
            )
            
            if normal_pattern:
                logger.info(f"{stock_code}: 일반 시간대 상승 패턴 감지")
                
            return normal_pattern
        
    except Exception as e:
        logger.error(f"{stock_code}: 연속 상승 패턴 확인 중 에러: {str(e)}")
        
        # 장 초반 9시 20분 이전에는 에러 발생해도 True 반환하여 과도한 필터링 방지
        if is_very_early:
            logger.info(f"{stock_code}: 장 초반 데이터 부족, 패턴 검사 생략")
            return True
            
        return False  # 기타 시간대에는 오류 발생 시 안전하게 False 반환

######### 장 초반 종목 스캔 끝 #############

def detect_higher_lows_pattern(stock_code, min_candles=8):
    """
    저점을 높여가는 계단식 상승 패턴 감지 함수 - 조기 모멘텀 감지 개선
    """
    try:
        stock_data = get_stock_data(stock_code)
        if stock_data is None:
            return False, {"error": "데이터 없음"}
            
        # 분봉과 일봉 데이터 모두 활용
        minute_df = stock_data.get('minute_ohlcv')
        daily_df = stock_data.get('ohlcv')
        
        # 적어도 하나는 있어야 함
        if minute_df is None and daily_df is None:
            return False, {"error": "분봉/일봉 데이터 모두 없음"}
            
        # 분봉 데이터가 있으면 분봉 기준으로 처리
        if minute_df is not None and len(minute_df) >= min_candles:
            df = minute_df
            timeframe = "minute"
        # 없으면 일봉 데이터로 처리
        elif daily_df is not None and len(daily_df) >= 5:  # 일봉은 5개만 있어도 충분
            df = daily_df
            timeframe = "daily"
        else:
            return False, {"error": "충분한 데이터 없음"}
            
        # 현재가와 차트 데이터
        current_price = stock_data['current_price']
        lows = df['low'].values
        highs = df['high'].values
        closes = df['close'].values
        volumes = df['volume'].values
        
        # === 1. 지역 저점 찾기 (양쪽 이웃보다 낮은 봉) ===
        local_lows = []
        for i in range(1, len(lows)-1):
            if lows[i] <= lows[i-1] and lows[i] <= lows[i+1]:
                # 저점이 동일한 경우도 포함
                local_lows.append((i, lows[i]))
        
        # 충분한 저점이 없으면 종료
        if len(local_lows) < 2:  # 2개 이상의 저점 필요
            return False, {"reason": "지역 저점 부족", "count": len(local_lows)}
            
        # === 2. 저점 상승 확인 ===
        # 연속적인 저점만 확인 (중간에 없어진 저점은 무시)
        valid_lows = []
        prev_idx = -10  # 초기값
        
        for idx, price in local_lows:
            if idx > prev_idx + 1:  # 연속되지 않은 인덱스
                valid_lows.append((idx, price))
                prev_idx = idx
        
        # 유효 저점이 2개 이상인지 확인
        if len(valid_lows) < 2:
            return False, {"reason": "유효 저점 부족", "count": len(valid_lows)}
            
        # 저점 상승 확인
        rising_lows = True
        for i in range(1, len(valid_lows)):
            # 0.3% 이상 상승해야 의미있는 저점 상승으로 간주
            low_rise_pct = (valid_lows[i][1] - valid_lows[i-1][1]) / valid_lows[i-1][1] * 100
            if low_rise_pct < 0.3:
                rising_lows = False
                break
                
        # === 3. 고점 확인 (고점도 상승하는지) ===
        local_highs = []
        for i in range(1, len(highs)-1):
            if highs[i] >= highs[i-1] and highs[i] >= highs[i+1]:
                local_highs.append((i, highs[i]))
        
        rising_highs = False
        if len(local_highs) >= 2:
            # 고점도 상승하는지 확인
            rising_highs = local_highs[-1][1] > local_highs[0][1]
        
        # === 개선: 거래량 급증 확인 ===
        volume_surge = False
        if len(volumes) >= 3:
            # 최근 3개 봉의 거래량 평균
            recent_avg_vol = np.mean(volumes[-3:])
            # 이전 5개 봉의 거래량 평균
            prev_avg_vol = np.mean(volumes[-8:-3]) if len(volumes) >= 8 else np.mean(volumes[:-3])
            # 거래량 급증 감지
            volume_surge = recent_avg_vol > prev_avg_vol * 1.5
        
        # === 4. 추가 조건: 최근 추세 확인 ===
        # 마지막 저점 이후 상승 확인
        last_low_idx = valid_lows[-1][0]
        last_low_price = valid_lows[-1][1]
        
        # 마지막 저점 이후 상승률
        if last_low_idx < len(closes) - 1:  # 마지막 저점 이후 데이터가 있는지 확인
            price_after_low = closes[-1]
            rise_after_low = (price_after_low - last_low_price) / last_low_price * 100
        else:
            rise_after_low = 0
            
        # 거래량 증가 확인
        volume_increase = False
        if last_low_idx < len(volumes) - 3:  # 최소 3개 이상의 데이터가 필요
            avg_volume_before = np.mean(volumes[max(0, last_low_idx-3):last_low_idx+1])
            avg_volume_after = np.mean(volumes[last_low_idx+1:])
            volume_increase = avg_volume_after > avg_volume_before * 1.2  # 20% 이상 증가
            
        # 최근 캔들 방향성 확인 (상승 중인지)
        recent_rising = False
        if len(closes) >= 3:
            recent_rising = closes[-1] > closes[-3]  # 최근 3개 캔들 상승 추세
            
        # === 5. 패턴 강도 계산 ===
        # 기본 점수: 저점 상승(5) + 고점 상승(2) + 거래량 증가(1) + 최근 상승(2)
        pattern_strength = 0
        
        if rising_lows:
            pattern_strength += 5
        if rising_highs:
            pattern_strength += 2
        if volume_increase:
            pattern_strength += 1
        if recent_rising:
            pattern_strength += 2
            
        # 상승률에 따른 추가 점수
        if rise_after_low > 2.0:  # 2% 이상 상승
            pattern_strength += min(2, rise_after_low / 2)  # 최대 2점 추가
            
        # === 개선: 거래량 급증시 추가 점수 ===
        if volume_surge:
            pattern_strength += 2
            
        # 시간대별 조정
        is_early_morning = is_in_early_morning_session()
        if is_early_morning:
            pattern_strength *= 1.2  # 장초반은 20% 가중치
            
        # 최대 10점으로 제한
        pattern_strength = min(10, pattern_strength)
            
        # === 6. 패턴 판정 ===
        # 핵심 조건: 저점 상승 + 일정 강도 이상
        pattern_detected = rising_lows and pattern_strength >= 4.0
        
        # === 7. 매수 시점 적합성 평가 ===
        buy_timing = "none"  # 기본값: 매수 시점 아님
        
        if pattern_detected:
            # 마지막 저점으로부터의 위치 확인
            last_low_idx = valid_lows[-1][0]
            current_idx = len(closes) - 1
            
            # 거리 계산 (캔들 수 기준)
            distance_from_low = current_idx - last_low_idx
            
            # 마지막 저점 이후 가격 움직임 분석
            if last_low_idx < len(closes) - 1:
                price_at_low = lows[last_low_idx]
                current_close = closes[-1]
                
                # 저점 대비 현재 가격 상승률
                rise_from_low = (current_close - price_at_low) / price_at_low * 100
                
                # === 개선: 매수 시점 판단 기준 확장 ===
                if distance_from_low <= 1:
                    # 저점 직후 (0-1 캔들 이내) - 가장 적합한 매수 시점
                    buy_timing = "perfect"
                    timing_score = 10.0
                elif distance_from_low <= 3 and rise_from_low < 2.0:
                    # 저점에서 약간 지났지만 아직 많이 상승하지 않음 (2-3 캔들)
                    buy_timing = "good"
                    timing_score = 8.0
                elif distance_from_low <= 5 and rise_from_low < 3.0:
                    # 저점에서 좀 지났고 어느 정도 상승 (4-5 캔들)
                    buy_timing = "acceptable"
                    timing_score = 6.0
                else:
                    # 저점에서 많이 지났거나 이미 많이 상승
                    buy_timing = "late"
                    timing_score = 4.0
                
                # 직전 캔들 분석 (추세 전환 확인)
                if len(closes) >= 2:
                    prev_close = closes[-2]
                    prev_open = df['open'].iloc[-2]
                    current_open = df['open'].iloc[-1]
                    
                    # 전환점 감지: 직전 캔들이 양봉이고 현재 캔들이 이어서 상승
                    if prev_close > prev_open and current_close > current_open and current_close > prev_close:
                        buy_timing = "breakout"  # 추세 전환 감지
                        timing_score += 1.0  # 추가 점수
                    
                # 양봉 연속성 체크
                consecutive_bullish = 0
                for i in range(min(3, len(closes))):
                    idx = len(closes) - 1 - i
                    if idx >= 0 and closes[idx] > df['open'].iloc[idx]:
                        consecutive_bullish += 1
                    else:
                        break
                        
                if consecutive_bullish >= 2:
                    timing_score += 1.0  # 연속 양봉 추가 점수
                    
                # 최종 매수 시점 점수 (최대 10점)
                timing_score = min(10.0, timing_score)
            else:
                timing_score = 0.0
        else:
            timing_score = 0.0
            
        # 상세 정보
        info = {
            "timeframe": timeframe,
            "rising_lows": rising_lows,
            "rising_highs": rising_highs,
            "local_lows_count": len(valid_lows),
            "rise_after_last_low": rise_after_low,
            "volume_increase": volume_increase,
            "volume_surge": volume_surge,  # 추가: 거래량 급증 여부
            "recent_rising": recent_rising,
            "pattern_strength": pattern_strength,
            "buy_timing": buy_timing,
            "timing_score": timing_score
        }
        
        # 패턴 감지와 매수 시점 모두 적합한지 평가
        is_suitable_entry = pattern_detected and timing_score >= 6.0  # 최소 6점 이상
        
        # 개선: 거래량 급증과 함께 저점 반등이 감지될 경우 매수 적합성 향상
        if pattern_detected and volume_surge and timing_score >= 5.0:
            is_suitable_entry = True
            info["reason"] = "거래량 급증 동반 저점 반등"
        
        # 최종 정보 업데이트
        info["is_suitable_entry"] = is_suitable_entry
        
        # 로그 추가
        if pattern_detected:
            logger.info(f"\n✨ 저점 상승 패턴 감지 ({stock_code}):")
            logger.info(f"- 패턴 강도: {pattern_strength:.1f}/10")
            logger.info(f"- 저점 상승: {rising_lows}, 고점 상승: {rising_highs}")
            logger.info(f"- 유효 저점 수: {len(valid_lows)}개")
            logger.info(f"- 마지막 저점 이후 상승률: {rise_after_low:.2f}%")
            logger.info(f"- 거래량 증가: {volume_increase}, 거래량 급증: {volume_surge}")
            logger.info(f"- 최근 상승 추세: {recent_rising}")
            logger.info(f"- 매수 시점: {buy_timing} (점수: {timing_score:.1f}/10)")
            logger.info(f"- 저점으로부터 거리: {distance_from_low if 'distance_from_low' in locals() else 'N/A'}캔들")
            logger.info(f"- 매수 적합성: {'적합' if is_suitable_entry else '부적합'}")
        
        return is_suitable_entry, info  # 패턴 감지가 아닌 매수 적합성 반환
        
    except Exception as e:
        logger.error(f"저점 상승 패턴 감지 중 에러: {str(e)}")
        return False, {"error": str(e)}


def scan_momentum_stocks():
    """급등 가능성이 높은 종목 스캔 - 완전한 버전"""
    momentum_stocks = []
    
    try:
        logger.info("==== scan_momentum_stocks 함수 시작 ====")
        # 현재 시간 체크
        # now = datetime.now()
        # is_morning_session = (9 <= now.hour < 10)
        # is_early_morning = (now.hour == 9 and now.minute <= 35)
        # is_very_early_morning = (now.hour == 9 and now.minute <= 20)  # 장 시작 직후 9시-9시20분

        is_morning_session = is_in_morning_session()
        is_early_morning = is_in_early_morning_session()
        is_very_early_morning = is_in_very_early_morning_session()

        # 상수 기준으로 시간대별 필터링 조건 조정
        if is_morning_session:
            logger.info("\n=== 오전장 조건 적용 ===")
            if is_early_morning:
                # 장초반 50% 완화
                market_cap = MIN_MARKET_CAP * 0.5     # 800억 -> 400억
                volume = MIN_DAILY_VOLUME * 0.5       # 10000 -> 5000
                rise_rate = MIN_RISE_RATE * 0.5     # 3.5% -> 2.0%
                logger.info("장초반 완화 조건 적용 (50%)")
            else:
                # 오전장 25% 완화
                market_cap = MIN_MARKET_CAP * 0.75    # 800억 -> 600억
                volume = MIN_DAILY_VOLUME * 0.8       # 10000 -> 8000
                rise_rate = MIN_RISE_RATE * 0.85     # 3.5% -> 3.0%
                logger.info("오전장 일반 조건 적용 (25%)")
                
            logger.info(f"- 최소 시총: {market_cap}억 (기준: {MIN_MARKET_CAP}억)")
            logger.info(f"- 최소 거래량: {volume} (기준: {MIN_DAILY_VOLUME})")
            logger.info(f"- 상승률 기준: {rise_rate}% (기준: {MIN_RISE_RATE}%)")
        else:
            market_cap = MIN_MARKET_CAP
            volume = MIN_DAILY_VOLUME
            rise_rate = MIN_RISE_RATE

        # stock_list = KisKR.GetMarketCodeList(
        #     price_limit=MAX_STOCK_PRICE,     # 주가 제한은 고정
        #     min_market_cap=market_cap * 100000000,
        #     min_volume=volume,
        #     max_stocks=50
        # )

        if is_very_early_morning:

            # 9시 10분 이전인지 확인
            if is_too_early_for_trading():
                logger.info("오전 9시 5분 이전에는 종목 스캔만 하고 매수는 하지 않습니다.")
                # 스캔은 계속 진행하지만 매수할 때 main 함수에서 시간 체크

            # 장 초반 거래량 기반 종목 선별 (별도 함수 사용)
            stock_list = get_early_morning_stocks()
            
            # 장 초반 모멘텀 필터링 적용 및 추가
            early_momentum_stocks = filter_early_momentum_stocks(stock_list)

            # 장 초반 모멘텀 종목들에 대해 추가 검증 (중요 추가)
            verified_momentum_stocks = []
            for stock in early_momentum_stocks:
                # 연속 상승 패턴 확인 (추가된 검증)
                if check_continuous_uptrend(stock['code'], min_candles=3):
                    verified_momentum_stocks.append(stock)
                else:
                    logger.info(f"{stock['name']}({stock['code']}) - 연속 상승 패턴 없음")
            
            # 검증된 종목만 매수 후보로 추가
            if verified_momentum_stocks:
                # 상위 2개 종목만 선택 (선택적 추가)
                top_momentum_stocks = verified_momentum_stocks[:2]
                momentum_stocks.extend(top_momentum_stocks)
                logger.info(f"장 초반 검증 완료: {len(verified_momentum_stocks)}개 중 {len(top_momentum_stocks)}개 선택")

            # if early_momentum_stocks:
            #     momentum_stocks.extend(early_momentum_stocks)


            # 전일 고모멘텀 종목 로드 및 추가
            high_momentum_stocks = load_high_momentum_stocks()

            if high_momentum_stocks:
                logger.info(f"\n=== 장 초반 전일 고모멘텀 종목 {len(high_momentum_stocks)}개 추가 ===")
                
                # 기존 모멘텀 스캔 종목과 중복 체크
                existing_codes = [stock['code'] for stock in momentum_stocks]
                
                # 고모멘텀 종목들에 대해 강화된 필터링 적용
                high_momentum_filtered = []
                for stock in high_momentum_stocks:
                    if stock['code'] not in existing_codes:
                        # 현재 가격 업데이트
                        current_price = KisKR.GetCurrentPrice(stock['code'])
                        if current_price <= 0:
                            logger.info(f"{stock['name']}({stock['code']}) - 현재가 조회 실패, 제외")
                            continue
                            
                        # 기본 데이터 로드
                        stock_data = get_stock_data(stock['code'])
                        if stock_data is None:
                            logger.info(f"{stock['name']}({stock['code']}) - 데이터 로드 실패, 제외")
                            continue
                        
                        # 1. 연속 상승 패턴 확인 (추가된 검증)
                        if not check_continuous_uptrend(stock['code'], min_candles=3):
                            logger.info(f"{stock['name']}({stock['code']}) - 전일 고모멘텀 종목이나 연속 상승 패턴 없음, 제외")
                            continue
                            
                        # 2. 호가 정보 확인 (추가된 검증)
                        is_favorable, order_info = analyze_order_book(stock['code'])
                        if not is_favorable:
                            logger.info(f"{stock['name']}({stock['code']}) - 전일 고모멘텀 종목이나 호가 불리, 제외")
                            continue
                            
                        # 3. RSI 확인 (추가된 검증)
                        rsi = stock_data.get('rsi', 50)  # 기본값 50
                        if rsi > MAX_BUY_RSI or rsi < 40:  # 40-70 범위로 제한
                            logger.info(f"{stock['name']}({stock['code']}) - 전일 고모멘텀 종목이나 RSI 부적합 ({rsi:.1f}), 제외")
                            continue
                            
                        # 4. 당일 상승률 확인 (추가된 검증)
                        prev_close = stock_data.get('prev_close', 0)
                        if prev_close > 0:
                            today_change = ((current_price - prev_close) / prev_close) * 100
                            # 이미 많이 상승한 종목은 제외 (3% 이상)
                            if today_change > 3.0:
                                logger.info(f"{stock['name']}({stock['code']}) - 전일 고모멘텀 종목이나 당일 상승률 높음 ({today_change:.1f}%), 제외")
                                continue
                            # 하락 중인 종목도 제외
                            elif today_change < -0.5:
                                logger.info(f"{stock['name']}({stock['code']}) - 전일 고모멘텀 종목이나 당일 하락 중 ({today_change:.1f}%), 제외")
                                continue
                        
                        # 모든 조건 통과 시 추가
                        stock_info = {
                            'code': stock['code'],
                            'name': stock['name'],
                            'price': current_price,
                            'rsi': rsi,
                            'volume_ratio': stock.get('volume_ratio', 1.0),
                            'atr': stock_data.get('atr', 0),
                            'strategy': 'previous_high_momentum'
                        }
                        high_momentum_filtered.append(stock_info)
                        logger.info(f"✅ 장 초반 매수 대상(전일 고모멘텀 + 추가검증 통과): {stock['name']}({stock['code']})")
                
                # 모멘텀 스코어가 높은 순으로 정렬 (추가)
                if high_momentum_filtered:
                    # 간단한 모멘텀 스코어 계산 (RSI + 당일 변동)
                    for stock in high_momentum_filtered:
                        stock_data = get_stock_data(stock['code'])
                        prev_close = stock_data.get('prev_close', stock['price'])
                        today_change = ((stock['price'] - prev_close) / prev_close) * 100 if prev_close > 0 else 0
                        
                        # 모멘텀 스코어: RSI 가중치 + 당일 변동 가중치 + 거래량 비율
                        momentum_score = (
                            (stock['rsi'] * 0.5) +                     # RSI 비중 50%
                            (max(0, today_change) * 10) +              # 당일 상승률 비중 (10배 가중치)
                            (stock.get('volume_ratio', 1.0) * 5)       # 거래량 비율 비중 (5배 가중치)
                        )
                        stock['momentum_score'] = momentum_score
                    
                    # 모멘텀 스코어로 정렬
                    high_momentum_filtered.sort(key=lambda x: x.get('momentum_score', 0), reverse=True)
                    
                    # 상위 2개만 선택 (선택적)
                    # high_momentum_filtered = high_momentum_filtered[:2]
                    
                    # 로깅
                    logger.info(f"\n=== 전일 고모멘텀 종목 중 {len(high_momentum_filtered)}개 최종 선택 ===")
                    for i, stock in enumerate(high_momentum_filtered):
                        logger.info(f"{i+1}. {stock['name']}({stock['code']}) - 모멘텀 점수: {stock.get('momentum_score', 0):.1f}")
                
                # 최종 선택된 고모멘텀 종목 추가
                momentum_stocks.extend(high_momentum_filtered)


            ############## 신규 추가/ 외국인, 기관 매매 정보 반영 ##############

            # 당일 매도 종목 확인
            daily_trading = load_daily_trading_history()
            sold_stocks = daily_trading.get('sold_stocks', [])

            # 외국인/기관 매수 상위 종목 추출
            institution_trading_info = KisKR.get_institution_foreign_trading_info()
            # 상위 10개 외국인/기관 매수 종목 선별
            top_institution_stocks = sorted(
                institution_trading_info, 
                key=lambda x: int(x['frgn_ntby_qty']), 
                reverse=True
            )[:10]       

            if top_institution_stocks:
                logger.info(f"\n=== 장 초반 외국인/기관 매수 종목 {len(top_institution_stocks)}개 추가 ===")
                
                # 기존 모멘텀 스캔 종목과 중복 체크
                existing_codes = [stock['code'] for stock in momentum_stocks]
                
                for stock in top_institution_stocks:
                    stock_code = stock['mksc_shrn_iscd']
                    
                    # 중복 및 당일 매도 종목 제외
                    if stock_code not in existing_codes and stock_code not in sold_stocks:
                        # 현재 가격 업데이트
                        current_price = KisKR.GetCurrentPrice(stock_code)
                        if current_price <= 0:
                            logger.info(f"{stock['hts_kor_isnm']}({stock_code}) - 현재가 조회 실패, 제외")
                            continue
                        
                        # 기본 데이터 로드
                        stock_data = get_stock_data(stock_code)
                        if stock_data is None:
                            logger.info(f"{stock['hts_kor_isnm']}({stock_code}) - 데이터 로드 실패, 제외")
                            continue
                        
                        # 최소한의 안전 조건 확인
                        if check_continuous_uptrend(stock_code, min_candles=2):
                            stock_info = {
                                'code': stock_code,
                                'name': stock['hts_kor_isnm'],
                                'price': current_price,
                                'volume_ratio': float(stock.get('acml_vol', 0)) / stock_data.get('volume_ma5', 1),
                                'rsi': stock_data['rsi'],
                                'atr': stock_data.get('atr', 0),
                                'strategy': 'institution_buy'
                            }
                            momentum_stocks.append(stock_info)
                            
                            logger.info(f"✅ 장 초반 매수 대상(외국인/기관 매수): {stock['hts_kor_isnm']}({stock_code})")

                # 최종 선택된 외국인/기관 매수 종목 수 트래킹
                final_selected_count = len([stock for stock in momentum_stocks if stock.get('strategy') == 'institution_buy'])
                logger.info(f"\n=== 외국인/기관 매수 종목 중 {final_selected_count}개 최종 선택 ===")

            ############## 신규 추가/ 외국인, 기관 매매 정보 반영 END##############

        else:
            # 1차 종목 필터링 - 시총, 거래량 기준 (한 번만 호출)
            logger.info("get_stock_list() 함수 호출...")
            stock_list = get_stock_list()
            logger.info(f"get_stock_list() 결과: {len(stock_list if stock_list else [])}개 종목")

        if not stock_list:
            logger.info("종목 리스트가 비어있습니다. 스캔을 건너뜁니다.")
            return momentum_stocks
        
        # 2차 홍인기 전략 스캔 - rise_rate 기준 추가 적용
        hong_strategy_stocks = scan_hong_strategy_stocks(
            stock_list=stock_list, 
            is_morning_session=is_morning_session, 
            is_early_morning=is_early_morning,
            min_rise_rate=rise_rate
        )

        if hong_strategy_stocks:
            momentum_stocks.extend(hong_strategy_stocks)
            logger.info(f"\n홍인기 전략으로 {len(hong_strategy_stocks)}종목 선정")

        # 기존 검출 종목 로드
        detected_stocks = load_detected_stocks()
        today = datetime.now().strftime('%Y-%m-%d')
        
        if detected_stocks['last_date'] != today:
            detected_stocks = {'last_date': today, 'stocks': []}
        
        previous_codes = [stock['code'] for stock in detected_stocks['stocks']]
        
        # 당일 매도 종목 체크
        daily_trading = load_daily_trading_history()
        sold_stocks = daily_trading.get('sold_stocks', [])
        if sold_stocks:
            logger.info(f"\n당일 매도 제외 종목: {len(sold_stocks)}개")

 
        logger.info(f"\n총 {len(stock_list)}개 종목 분석 시작...")

        # 청크 기반 병렬 처리
        CHUNK_SIZE = 20
        chunks = [stock_list[i:i + CHUNK_SIZE] 
                 for i in range(0, len(stock_list), CHUNK_SIZE)]
        
        processed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(
                process_stock_chunk, 
                chunk, 
                momentum_stocks, 
                sold_stocks,
                previous_codes
            ) for chunk in chunks]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    results = future.result()
                    if results:
                        momentum_stocks.extend(results)
                    processed_count += CHUNK_SIZE
                    logger.info(f"진행률: {min(processed_count, len(stock_list))}/{len(stock_list)}")
                except Exception as e:
                    logger.error(f"청크 처리 중 에러: {str(e)}")
                    continue

        # 결과 정렬 및 저장
        momentum_stocks.sort(
            key=lambda x: (x['volume_ratio'], x['rsi']), 
            reverse=True
        )

        # 저점 상승 패턴 종목 추가 스캔
        higher_lows_candidates = []
        # (저점 상승 패턴 코드...)

        # 이미 처리된 종목 중복 방지
        processed_codes = [stock['code'] for stock in momentum_stocks]
        
        for stock in stock_list:
            if stock['code'] in sold_stocks or stock['code'] in processed_codes:
                continue  # 당일 매도 종목 또는 이미 포함된 종목은 제외
            
            # 저점 상승 패턴 확인
            is_suitable_entry, pattern_info = detect_higher_lows_pattern(stock['code'])
            
            if is_suitable_entry:
                # 패턴 감지 및 매수 적합성 충족
                pattern_strength = pattern_info.get('pattern_strength', 0)
                timing_score = pattern_info.get('timing_score', 0)
                buy_timing = pattern_info.get('buy_timing', 'none')
                
                # 추가 검증: get_stock_data로 데이터 다시 가져오기
                stock_data = get_stock_data(stock['code'])
                if stock_data:
                    # 일부 기본 조건 확인 (호가, 거래량 등)
                    is_favorable, _ = analyze_order_book(stock['code'])
                    volume_ok = stock_data['volume'] > stock_data['volume_ma5'] * 0.8
                    
                    if is_favorable and volume_ok:
                        stock_info = {
                            'code': stock['code'],
                            'name': stock['name'],
                            'price': stock_data['current_price'],
                            'volume_ratio': stock_data['volume'] / stock_data['volume_ma5'],
                            'rsi': stock_data['rsi'],
                            'atr': stock_data['atr'],
                            'strategy': 'higher_lows',  # 새로운 전략 표시
                            'pattern_strength': pattern_strength,
                            'timing_score': timing_score,
                            'buy_timing': buy_timing
                        }
                        higher_lows_candidates.append(stock_info)
                        
                        logger.info(f"✨ 저점 상승 패턴 매수 후보 추가: {stock['name']}({stock['code']})")
                        logger.info(f"- 패턴 강도: {pattern_strength:.1f}/10, 매수 시점: {buy_timing} (점수: {timing_score:.1f}/10)")

        # 패턴 강도와 타이밍 점수 기반으로 정렬
        if higher_lows_candidates:
            # 패턴 강도 * 0.6 + 타이밍 점수 * 0.4로 종합 점수 계산
            for candidate in higher_lows_candidates:
                combined_score = (candidate.get('pattern_strength', 0) * 0.6 + 
                                 candidate.get('timing_score', 0) * 0.4)
                candidate['combined_score'] = combined_score
            
            # 종합 점수로 정렬
            higher_lows_candidates.sort(key=lambda x: x.get('combined_score', 0), reverse=True)
            
            # 상위 2개만 선택 (변경 가능)
            top_candidates = higher_lows_candidates[:2]
            momentum_stocks.extend(top_candidates)
            
            logger.info(f"\n=== 저점 상승 패턴 종목 {len(top_candidates)}개 추가됨 ===")
            for stock in top_candidates:
                logger.info(f"- {stock['name']}({stock['code']}) - 종합점수: {stock.get('combined_score', 0):.1f}/10")
                logger.info(f"  (패턴 강도: {stock.get('pattern_strength', 0):.1f}, 타이밍: {stock.get('timing_score', 0):.1f}, 매수 시점: {stock.get('buy_timing', 'unknown')})")

        # 저점 상승 패턴 종목 추가 스캔 끝

        detected_stocks['stocks'] = momentum_stocks
        save_detected_stocks(detected_stocks)
        
        # 스캔 결과 요약
        logger.info(f"\n=== 스캔 완료 ({len(momentum_stocks)}종목) ===")

        if momentum_stocks:
            msg = f"===== 스캔 완료 ({len(momentum_stocks)}종목) =====\n"
            for stock in momentum_stocks[:3]:
                if stock.get('strategy') == 'early_momentum':
                    strategy_name = "장초반"
                    msg += f"- [{strategy_name}] {stock['name']}({stock['code']}): "
                    msg += f"거래량 {stock['volume_ratio']:.1f}배, "
                    msg += f"상승률 {stock.get('rise_rate', 0):.1f}%\n"
                else:
                    strategy_name = "홍인기" if stock.get('strategy') == 'hong' else "모멘텀"
                    msg += f"- [{strategy_name}] {stock['name']}({stock['code']}): "
                    if stock.get('strategy') == 'hong':
                        msg += f"상승률 {stock.get('rise_rate', 0):.1f}%, "
                        msg += f"섹터: {stock.get('sector', 'N/A')}\n"
                    else:
                        msg += f"거래량 {stock['volume_ratio']:.1f}배, "
                        msg += f"RSI {stock['rsi']:.1f}\n"
            logger.info(msg)

            # 캐시 키 생성 (오늘 날짜 + 스캔 종목 수)
            cache_key = f"momentum_scan_{today}_{len(momentum_stocks)}"
            
            # 캐시 매니저에서 알림 여부 확인
            cache_manager = CacheManager.get_instance()
            if not cache_manager.get('discord_scan_messages', cache_key):
                # discord_alert.SendMessage(msg)
                cache_manager.set('discord_scan_messages', cache_key, True)
            else:
                logger.info(f"스캔 결과 알림 이미 전송됨 (캐시 유효)")
                
    except Exception as e:
        logger.error(f"스캔 중 에러 발생: {str(e)}")
            
    return momentum_stocks


def load_trading_state():
    """트레이딩 상태 로드"""
    try:
        with open(f"KrStock_{BOT_NAME}.json", 'r') as f:
            return json.load(f)
    except:
        return {'positions': {}}

def save_trading_state(state):
    """트레이딩 상태 저장"""
    with open(f"KrStock_{BOT_NAME}.json", 'w') as f:
        json.dump(state, f)

def load_daily_profit_state():
    """일일 손익 상태 로드"""
    try:
        with open(f"DailyProfit_{BOT_NAME}.json", 'r') as f:
            return json.load(f)
    except:
        return {
            'last_date': '',
            'start_money': 0,          # 당일 시작시 봇 운용 금액
            'today_profit': 0,         # 당일 실현 손익
            'today_profit_rate': 0,    # 당일 실현 손익률
            'accumulated_profit': 0,    # 봇 시작 이후 누적 실현 손익
            'total_trades': 0,         # 총 거래 횟수
            'winning_trades': 0,       # 승리 거래 횟수
            'max_profit_trade': 0,     # 최대 수익 거래
            'max_loss_trade': 0        # 최대 손실 거래
        }
    
def save_daily_profit_state(state):
    """일일 손익 상태 저장"""
    with open(f"DailyProfit_{BOT_NAME}.json", 'w') as f:
    #with open(f"./DailyProfit_{BOT_NAME}.json", 'w') as f:
        json.dump(state, f)

def send_daily_report():
    """일일 거래 성과 보고서 생성 및 전송"""
    # 1. 계좌 전체 현황
    balance = KisKR.GetBalance()
    my_stocks = KisKR.GetMyStockList()
    daily_profit = load_daily_profit_state()
    
    def safe_float(value, default=0):
        if value is None or value == '':
            return float(default)
        return float(str(value).replace(',', ''))
    
    total_money = safe_float(balance.get('TotalMoney'))
    stock_revenue = safe_float(balance.get('StockRevenue'))
    revenue_rate = (stock_revenue / (total_money - stock_revenue)) * 100 if (total_money - stock_revenue) != 0 else 0
    
    msg = "📊 일일 거래 성과 보고서 📊\n"
    msg += f"========== {datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
    msg += f"[전체 계좌 현황]\n"
    msg += f"총 평가금액: {total_money:,.0f}원\n"
    msg += f"누적 손익: {stock_revenue:,.0f}원 ({revenue_rate:.2f}%)\n"
    
    if my_stocks:
        msg += "\n보유 종목 현황:\n"
        for stock in my_stocks:
            msg += f"- {stock['StockName']}({stock['StockCode']}): "
            msg += f"{stock['StockAmt']}주, {safe_float(stock['StockRevenueMoney']):,.0f}원 ({stock['StockRevenueRate']}%)\n"
    else:
        msg += "\n현재 보유 종목 없음\n"
        
    # 2. 봇 전용 성과 추가
    if daily_profit['total_trades'] > 0:
        msg += f"\n[봇 거래 성과]\n"
        msg += f"봇 운용금액: {daily_profit['start_money']:,.0f}원\n"
        msg += f"당일 실현손익: {daily_profit['today_profit']:,.0f}원 ({daily_profit['today_profit_rate']:.2f}%)\n"
        msg += f"누적 실현손익: {daily_profit['accumulated_profit']:,.0f}원\n"
        
        winning_rate = (daily_profit['winning_trades'] / daily_profit['total_trades']) * 100
        msg += f"총 거래: {daily_profit['total_trades']}회 (승률: {winning_rate:.1f}%)\n"
        msg += f"최대 수익: {daily_profit['max_profit_trade']:,.0f}원\n"
        msg += f"최대 손실: {daily_profit['max_loss_trade']:,.0f}원"
    
    logger.info(msg)
    discord_alert.SendMessage(msg)


def is_strong_uptrend(current_data, current_profit_rate):
    """
    단기 강한 상승추세 판단 함수
    
    Args:
        current_data (dict): 주식 데이터
        current_profit_rate (float): 현재 수익률
    
    Returns:
        bool: 강한 상승추세 여부
    """
    try:
        # 가격과 단기 MA 관계
        price_ma5_diff_ratio = (current_data['current_price'] - current_data['ma5']) / current_data['ma5'] * 100
        price_ma10_diff_ratio = (current_data['current_price'] - current_data['ma10']) / current_data['ma10'] * 100
        
        # MA 기울기 (상대적 위치)
        ma5_ma10_diff_ratio = (current_data['ma5'] - current_data['ma10']) / current_data['ma10'] * 100
        
        # 거래량 추세
        volume_trend = current_data['volume'] / current_data['volume_ma5']
        
        # 단기 MA 관계
        ma_relationship = (
            current_data['current_price'] > current_data['ma5'] and
            current_data['current_price'] > current_data['ma10'] and
            current_data['ma5'] > current_data['ma10']
        )
        
        # 최근 분봉 데이터 분석 (단기 가격 변동성)
        if 'minute_ohlcv' in current_data and current_data['minute_ohlcv'] is not None:
            recent_candles = current_data['minute_ohlcv'].tail(5)  # 최근 5개 캔들 분석
            
            # 가격 변동성 계산
            price_volatility = (recent_candles['high'].max() - recent_candles['low'].min()) / recent_candles['close'].iloc[0] * 100
            
            # 급격한 가격 변동 감지
            sudden_price_change = any(
                abs((recent_candles['close'].iloc[i] - recent_candles['close'].iloc[i-1]) / recent_candles['close'].iloc[i-1] * 100) > 1.5
                for i in range(1, len(recent_candles))
            )
        else:
            price_volatility = 0
            sudden_price_change = False
        
        # 상승추세 판단 종합 조건
        strong_uptrend_conditions = [
            price_ma5_diff_ratio > 1,           # MA5 위 1% 이상
            price_ma10_diff_ratio > 1,          # MA10 위 1% 이상
            ma5_ma10_diff_ratio > 0,            # MA5가 MA10 위에 있음
            volume_trend > 1.2,                 # 거래량 20% 이상 증가
            ma_relationship                     # MA 긍정적 관계
        ]
        
        # 손실 심각도에 따른 추세 판단 로직
        conditions_met = sum(strong_uptrend_conditions)
        
        # 손실 심각도에 따라 다른 기준 적용
        if current_profit_rate <= -2.0:
            # 큰 손실 상황: 더 엄격한 추세 조건 요구
            uptrend_threshold = 5  # 모든 조건 충족
            no_sudden_change_condition = not sudden_price_change and price_volatility < 2.0
        elif current_profit_rate < 0:
            # 소폭 손실 상황: 4개 이상 조건 충족
            uptrend_threshold = 4
            no_sudden_change_condition = not sudden_price_change and price_volatility < 3.0
        else:
            # 수익 상황: 기존 로직 유지
            uptrend_threshold = 4
            no_sudden_change_condition = not sudden_price_change and price_volatility < 3.0
        
        logger.info("\n=== 단기 상승추세 분석 ===")
        logger.info(f"현재 수익률: {current_profit_rate:.2f}%")
        logger.info(f"현재가/MA5 비율: {price_ma5_diff_ratio:.2f}%")
        logger.info(f"현재가/MA10 비율: {price_ma10_diff_ratio:.2f}%")
        logger.info(f"MA5/MA10 비율: {ma5_ma10_diff_ratio:.2f}%")
        logger.info(f"거래량 비율: {volume_trend:.2f}배")
        logger.info(f"MA 관계: {ma_relationship}")
        logger.info(f"충족 조건 수: {conditions_met}/5")
        logger.info(f"가격 변동성: {price_volatility:.2f}%")
        logger.info(f"급격한 가격 변동: {'있음' if sudden_price_change else '없음'}")
        logger.info(f"추세 판단 임계값: {uptrend_threshold}")
        
        # 최종 추세 판단
        return conditions_met >= uptrend_threshold and no_sudden_change_condition
    
    except Exception as e:
        logger.error(f"단기 상승추세 분석 중 에러: {str(e)}")
        return False


def analyze_market_conditions(stock_code, current_data):
    """
    종합적인 시장 상황 분석
    """
    try:
        # 호가 분석
        is_favorable, order_info = analyze_order_book(stock_code)
        
        # 분봉 데이터 분석
        minute_data = analyze_minute_data(stock_code)
        
        conditions = {
            'order_book_favorable': is_favorable,
            'order_strength': order_info.get('order_strength', 0) if is_favorable else 0,
            'volume_trend': minute_data.get('volume_trend', False) if minute_data else False,
            'buying_pressure': minute_data.get('buying_pressure', 0) if minute_data else 0,
            'rsi': current_data.get('rsi', 50),
            'macd_trend': (current_data.get('macd', 0) > current_data.get('macd_signal', 0))
        }
        
        return conditions
    
    except Exception as e:
        logger.error(f"시장 상황 분석 중 에러: {str(e)}")
        return {}


def check_early_exit_conditions(market_conditions, current_profit_rate):
    """
    시장 상황 나쁨을 판단하고 조기 분할 매도 결정
    
    Args:
        market_conditions (dict): 시장 상황 분석 결과
        current_profit_rate (float): 현재 수익률
    
    Returns:
        dict: 분할 매도 결정 정보
    """
    # 시장 상황 나쁨을 판단하는 세부 지표들
    negative_conditions = [
        market_conditions.get('order_strength', 0) < 0.8,   # 호가 강도 약화
        market_conditions.get('buying_pressure', 0) < 0.3,  # 매수 압력 감소
        market_conditions.get('rsi', 50) > 70,              # RSI 과매수
        not market_conditions.get('volume_trend', False)    # 거래량 추세 약세
    ]
    
    # 부정적 조건 개수 카운트
    negative_count = sum(negative_conditions)
    
    # 조기 매도 판단 로직
    if (
        current_profit_rate > 0.5 and   # 최소 0.5% 수익
        current_profit_rate < 3.0 and   # 3% 미만 수익
        negative_count >= 2              # 2개 이상의 부정적 조건
    ):
        # 매도 비율 동적 결정 (부정적 조건 수에 따라)
        sell_percentage = min(0.3 + (negative_count * 0.1), 0.5)
        
        return {
            'should_exit': True,
            'sell_percentage': sell_percentage,
            'reason': f"부정적 시장 조건 ({negative_count}/4): 작은 수익 보존 매도",
            'negative_conditions': [
                '호가 강도 약화' if negative_conditions[0] else None,
                '매수 압력 감소' if negative_conditions[1] else None,
                'RSI 과매수' if negative_conditions[2] else None,
                '거래량 추세 약세' if negative_conditions[3] else None
            ]
        }
    
    return {
        'should_exit': False,
        'sell_percentage': 0,
        'reason': "매도 조건 미충족",
        'negative_conditions': []
    }


################################################################################
# 분할매도 핵심 로직 (새로운 함수)
################################################################################

def determine_fractional_sell(position, current_price, current_data):
    """
    분할매도 조건 확인 및 매도 비율 결정 함수
    
    Args:
        position (dict): 현재 포지션 정보
        current_price (float): 현재가
        current_data (dict): 종목 데이터
        
    Returns:
        tuple: (should_sell, sell_ratio, sell_reason) - 매도 여부, 매도 비율, 매도 사유
    """
    try:
        # 분할매도 기능 비활성화 상태면 바로 리턴
        if not ENABLE_FRACTIONAL_SELL:
            return False, 0, None
            
        stock_code = position['code']
        stock_name = KisKR.GetStockName(stock_code)
        entry_price = position['entry_price']
        current_amount = position['amount']
        
        # 기본 정보 및 쿨다운 체크
        current_time = datetime.now()
        last_fractional_sell_time = position.get('last_fractional_sell_time', None)
        
        # 최근 분할매도 이력이 있는지 확인 (쿨다운 적용)
        if last_fractional_sell_time:
            last_sell_time = datetime.strptime(last_fractional_sell_time, '%Y-%m-%d %H:%M:%S')
            time_since_last_sell = (current_time - last_sell_time).total_seconds()
            
            # 쿨다운 시간 이내라면 분할매도 하지 않음
            if time_since_last_sell < FRACTIONAL_SELL_COOLDOWN:
                cooldown_remaining = (FRACTIONAL_SELL_COOLDOWN - time_since_last_sell) / 60
                logger.info(f"{stock_name}({stock_code}) - 분할매도 쿨다운 중 (남은 시간: {cooldown_remaining:.1f}분)")
                return False, 0, None
        
        # 수익률 계산 개선 - 수수료와 세금 반영
        buy_fee = position.get('trading_fee', calculate_trading_fee(entry_price, current_amount, is_buy=True))
        sell_fee_estimate = calculate_trading_fee(current_price, current_amount, is_buy=False)
        total_fee = buy_fee + sell_fee_estimate
        
        gross_profit = (current_price - entry_price) * current_amount
        net_profit = gross_profit - total_fee
        profit_rate = (net_profit / (entry_price * current_amount)) * 100
        
        logger.info(f"\n=== 분할매도 조건 체크 ({stock_name}) ===")
        logger.info(f"- 현재 순수익률(수수료/세금 반영): {profit_rate:.2f}%")
        logger.info(f"- 현재 분할매도 단계: {position.get('fractional_sell_stage', 0)}")

        # 기본 상태 초기화
        sell_ratio = 0
        sell_reason = None
        
        # 이미 실행된 분할매도 단계 확인
        fractional_sell_stage = position.get('fractional_sell_stage', 0)
        
        # 고변동성 종목 체크
        atr = current_data.get('atr', 0)
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
        is_high_volatility = atr_pct >= HIGH_VOLATILITY_THRESHOLD
        
        logger.info(f"\n=== 분할매도 조건 체크 ({stock_name}) ===")
        logger.info(f"- 현재 수익률: {profit_rate:.2f}%")
        logger.info(f"- 현재 분할매도 단계: {fractional_sell_stage}")
        logger.info(f"- ATR: {atr:.2f}, ATR%: {atr_pct:.2f}% (고변동성: {is_high_volatility})")
        
        # 고변동성 종목 조기 수익실현 (단계 0에서만)
        if is_high_volatility and fractional_sell_stage == 0 and profit_rate >= HIGH_VOL_PROFIT_THRESHOLD:
            sell_ratio = HIGH_VOL_SELL_RATIO
            sell_reason = "HIGH_VOLATILITY_PROFIT"
            logger.info(f"✅ 고변동성 조기 수익실현 조건 충족: {profit_rate:.2f}% >= {HIGH_VOL_PROFIT_THRESHOLD}%")
            logger.info(f"✅ 매도 비율: {sell_ratio*100}%")
            return True, sell_ratio, sell_reason
        
        # 일반 분할매도 조건 체크 (단계별)
        if fractional_sell_stage == 0 and profit_rate >= FIRST_PROFIT_THRESHOLD:
            # 첫 번째 분할매도
            sell_ratio = FIRST_SELL_RATIO
            sell_reason = "FIRST_STAGE_PROFIT"
            logger.info(f"✅ 첫 번째 분할매도 조건 충족: {profit_rate:.2f}% >= {FIRST_PROFIT_THRESHOLD}%")
            
        elif fractional_sell_stage == 1 and profit_rate >= SECOND_PROFIT_THRESHOLD:
            # 두 번째 분할매도
            sell_ratio = SECOND_SELL_RATIO
            sell_reason = "SECOND_STAGE_PROFIT"
            logger.info(f"✅ 두 번째 분할매도 조건 충족: {profit_rate:.2f}% >= {SECOND_PROFIT_THRESHOLD}%")
            
        elif fractional_sell_stage == 2 and profit_rate >= THIRD_PROFIT_THRESHOLD:
            # 세 번째 분할매도 (남은 전체)
            sell_ratio = THIRD_SELL_RATIO
            sell_reason = "THIRD_STAGE_PROFIT"
            logger.info(f"✅ 세 번째 분할매도 조건 충족: {profit_rate:.2f}% >= {THIRD_PROFIT_THRESHOLD}%")
        
        # 매도 조건 불충족
        if sell_ratio == 0:
            logger.info(f"❌ 분할매도 조건 미충족")
            return False, 0, None
            
        # 매도 비율에 따른 로깅
        logger.info(f"✅ 매도 비율: {sell_ratio*100}%")
        return True, sell_ratio, sell_reason
        
    except Exception as e:
        logger.error(f"분할매도 조건 체크 중 오류: {str(e)}")
        return False, 0, None

################################################################################
# 분할매도 실행 함수 (새로운 함수)
################################################################################

def execute_fractional_sell(stock_code, position, sell_ratio, sell_reason, daily_profit):
    """
    분할매도 실행 함수
    
    Args:
        stock_code (str): 종목코드
        position (dict): 현재 포지션 정보
        sell_ratio (float): 매도 비율 (0.0-1.0)
        sell_reason (str): 매도 사유
        daily_profit (dict): 일일 손익 정보
        
    Returns:
        tuple: (success, trade_info, remaining_amount) - 성공 여부, 거래 정보, 남은 수량
    """
    try:
        stock_name = KisKR.GetStockName(stock_code)
        entry_price = position['entry_price']
        current_amount = position['amount']
        
        # 매도할 수량 계산 (최소 1주 이상)
        sell_amount = max(1, int(current_amount * sell_ratio))
        
        # 전체 매도인 경우 남은 수량 전체 매도
        if sell_ratio == 1.0 or sell_amount >= current_amount:
            sell_amount = current_amount
        
        logger.info(f"\n=== 분할매도 실행 ({stock_name}) ===")
        logger.info(f"- 총 보유량: {current_amount}주")
        logger.info(f"- 매도 비율: {sell_ratio*100:.1f}%")
        logger.info(f"- 매도 수량: {sell_amount}주")
        
        # 매도 사유 정보 표시
        sell_reason_display = {
            "HIGH_VOLATILITY_PROFIT": "고변동성 조기 수익실현",
            "FIRST_STAGE_PROFIT": "1단계 수익실현",
            "SECOND_STAGE_PROFIT": "2단계 수익실현",
            "THIRD_STAGE_PROFIT": "3단계 수익실현(전량)"
        }.get(sell_reason, sell_reason)
        
        # 매도 메시지 생성
        msg = f"{sell_reason_display} 조건 도달로 분할매도 시도!\n"
        msg += f"종목: {stock_name}({stock_code}), 수량: {sell_amount:,}주 (총 {current_amount:,}주 중)"
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 매도 주문 실행 및 실제 체결가 확인
        executed_price, executed_amount, error = process_sell_order(stock_code, sell_amount)
        
        if error:
            error_msg = f"⚠️ {stock_name}({stock_code}) 분할매도 실패: {error}"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            return False, None, current_amount
            
        if executed_amount <= 0 or executed_price <= 0:
            error_msg = f"⚠️ {stock_name}({stock_code}) 분할매도 실패: 체결 확인 불가"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            return False, None, current_amount
            
        # 수수료 계산 (실제 체결가 기준)
        buy_fee_per_share = calculate_trading_fee(entry_price, 1, is_buy=True) # 1주당 매수 수수료
        sell_fee_per_share = calculate_trading_fee(executed_price, 1, is_buy=False) # 1주당 매도 수수료
        
        buy_fee = buy_fee_per_share * executed_amount
        sell_fee = sell_fee_per_share * executed_amount
        total_fee = buy_fee + sell_fee
        
        # 실제 손익 계산 - 실제 체결량 기준
        gross_profit = (executed_price - entry_price) * executed_amount
        net_profit = gross_profit - total_fee
        net_profit_rate = (net_profit / (entry_price * executed_amount)) * 100
        
        # trade_info 생성 (실제 체결가와 수량 기준)
        trade_info = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'entry_price': entry_price,
            'exit_price': executed_price,
            'amount': executed_amount,  # 실제 체결량 사용
            'profit_amount': net_profit,
            'profit_rate': net_profit_rate,
            'trading_fee': total_fee,
            'sell_type': f"FRACTIONAL_{sell_reason}",
            'sell_reason': sell_reason_display,
            'sell_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'is_fractional': True,  # 분할매도 표시
            'fractional_ratio': sell_ratio
        }
        
        # daily_profit 업데이트
        daily_profit['today_profit'] += net_profit
        daily_profit['accumulated_profit'] += net_profit
        daily_profit['total_trades'] += 1
        if net_profit > 0:
            daily_profit['winning_trades'] += 1
        daily_profit['max_profit_trade'] = max(daily_profit['max_profit_trade'], net_profit)
        daily_profit['max_loss_trade'] = min(daily_profit['max_loss_trade'], net_profit)
        
        if daily_profit['start_money'] > 0:
            daily_profit['today_profit_rate'] = (daily_profit['today_profit'] / 
                                               daily_profit['start_money']) * 100
        
        # 남은 수량 계산
        remaining_amount = current_amount - executed_amount
        
        # 분할매도 완료 메시지
        msg = f"💰 분할매도 완료 - {stock_name}({stock_code})\n"
        msg += f"매도가: {executed_price:,.0f}원 (수수료/세금: {total_fee:,.0f}원)\n"
        msg += f"순수익: {net_profit:,.0f}원 ({net_profit_rate:.2f}%)\n"
        msg += f"매도수량: {executed_amount}주 (남은 수량: {remaining_amount}주)\n"
        msg += f"매도사유: {sell_reason_display}\n"
        msg += f"당일 누적 손익: {daily_profit['today_profit']:,.0f}원"
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
        # 성공적인 매도 후 상태 저장
        save_daily_profit_state(daily_profit)
        
        return True, trade_info, remaining_amount
        
    except Exception as e:
        error_msg = f"분할매도 처리 중 에러: {str(e)}"
        logger.error(error_msg)
        discord_alert.SendMessage(f"⚠️ 분할매도 실패: {error_msg}")
        return False, None, position['amount']


def update_trailing_stop(position, current_price, current_data):
    """
    트레일링 스탑 업데이트 함수 - 개선된 버전
    - 트레일링 스탑 기능이 먼저 활성화되도록 우선 순위 변경
    - 상승 모멘텀 있을 때 즉시 매도 조건 우회
    """
    try:
        logger.info(f"\n===== update_trailing_stop - 매도 조건 체크 시작 =====")

        # 기존 변수 초기화
        stock_code = position['code']
        stock_name = KisKR.GetStockName(stock_code)
        entry_price = position['entry_price']
        current_amount = position['amount']
        
        # 수익률 계산 개선 - 수수료와 세금 반영
        buy_fee = position.get('trading_fee', calculate_trading_fee(entry_price, current_amount, is_buy=True))
        sell_fee_estimate = calculate_trading_fee(current_price, current_amount, is_buy=False)
        total_fee = buy_fee + sell_fee_estimate
        
        gross_profit = (current_price - entry_price) * current_amount
        net_profit = gross_profit - total_fee
        current_profit_rate = (net_profit / (entry_price * current_amount)) * 100

        logger.info(f"매수가: {entry_price:,.0f}원, 현재가: {current_price:,.0f}원")
        logger.info(f"순수익률(수수료/세금 반영): {current_profit_rate:.2f}% (총 거래비용: {total_fee:,.0f}원)")

        # 매수 시간과 현재 시간의 차이 계산
        entry_time = datetime.strptime(position['entry_time'], '%Y-%m-%d %H:%M:%S')
        current_time = datetime.now()
        time_diff = current_time - entry_time
        hours_passed = time_diff.total_seconds() / 3600  # 경과 시간(시간 단위)

        # 오전장 매수 여부 확인 - 매수 시간이 9시인 경우
        is_morning_entry = entry_time.hour == 9
        # 오후장 여부 확인 (12시 이후)
        is_afternoon_session = is_in_afternoon_session()
        # 현재 포지션 정보 로깅 추가
        logger.info(f"\n===== {stock_name}({stock_code}) 매도 조건 체크 =====")
        logger.info(f"매수가: {entry_price:,.0f}원, 현재가: {current_price:,.0f}원")
        logger.info(f"현재 수익률: {current_profit_rate:.2f}% (경과시간: {hours_passed:.1f}시간)")
        logger.info(f"매수 시간: {entry_time.strftime('%Y-%m-%d %H:%M:%S')}, 오전장 매수: {'예' if is_morning_entry else '아니오'}")

        # [분할매도 로직 추가 - 최우선 체크]
        # 수익 구간에서 분할매도 조건 확인
        if current_profit_rate > 0:
            should_sell_partial, sell_ratio, sell_reason = determine_fractional_sell(
                position, current_price, current_data
            )
            
            # 분할매도 조건 충족 시
            if should_sell_partial and sell_ratio > 0:
                return True, position, f"FRACTIONAL_{sell_reason}"

        # ===== 1. 직접 손절 체크 (최우선) - 다른 조건에 관계없이 가장 먼저 체크 =====
        # 직접 손절 가능성 체크 (우선 순위 상향)
        if current_profit_rate <= INITIAL_STOP_LOSS:
            logger.info(f"✅ 수익률 기반 손절 조건 충족 (현재 수익률 {current_profit_rate:.2f}% <= 기준 {INITIAL_STOP_LOSS}%)")
            logger.info(f"✅ 손절 실행 - 추세 보호 무시")
            return True, position, "DIRECT_STOPLOSS"
        else:
            logger.info(f"❌ 수익률 기반 손절 조건 미달 (현재 수익률 {current_profit_rate:.2f}% > 기준 {INITIAL_STOP_LOSS}%)")
            
        # ===== 중요 개선: 트레일링 스탑 로직을 즉시 매도 로직보다 먼저 처리 =====
        # 트레일링 스탑 적용 기준 완화 - 1.5%에서 1.0%로 낮춤
        trailing_start_threshold = 1.0  # TRAILING_START 대신 직접 사용
        
        if current_profit_rate >= trailing_start_threshold:
            logger.info(f"✅ 트레일링 스탑 적용 시작 조건 충족 (수익률: {current_profit_rate:.2f}% >= {trailing_start_threshold}%)")
            
            if 'high_price' not in position or current_price > position['high_price']:
                old_high = position.get('high_price', entry_price)
                position['high_price'] = current_price
                
                # ATR 기반 동적 갭 조정
                atr = current_data.get('atr', 0)
                atr_ratio = atr / current_price * 100 if current_price > 0 else TRAILING_STOP_GAP
                
                # 트레일링 갭 동적 계산 - 상승 속도가 빠르면 더 넓게, 느리면 더 좁게
                if 'minute_ohlcv' in current_data and current_data['minute_ohlcv'] is not None:
                    minute_df = current_data['minute_ohlcv']
                    if len(minute_df) >= 5:
                        # 최근 5개 분봉 가격 기울기 계산
                        recent_prices = minute_df['close'].tail(5).values
                        price_slope = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] * 100
                        
                        # 기울기가 가파르면 트레일링 갭을 넓게 설정 (최대 2%)
                        if price_slope > 1.0:  # 5개 분봉 동안 1% 이상 상승
                            dynamic_stop_gap = min(2.0, TRAILING_STOP_GAP * 1.5)
                            logger.info(f"급격한 상승 감지 (5분봉 기울기: {price_slope:.2f}%) - 트레일링 갭 확대: {dynamic_stop_gap:.2f}%")
                        else:
                            # 일반적인 상승 - ATR 기반 갭 사용
                            dynamic_stop_gap = max(TRAILING_STOP_GAP, atr_ratio * 0.8)
                    else:
                        dynamic_stop_gap = max(TRAILING_STOP_GAP, atr_ratio * 0.8)
                else:
                    dynamic_stop_gap = max(TRAILING_STOP_GAP, atr_ratio * 0.8)
                
                # 수익률에 따른 추가 조정 - 수익이 클수록 갭을 좁게 (더 보수적으로)
                if current_profit_rate > 5.0:
                    final_gap = dynamic_stop_gap * 0.8  # 5% 이상 수익 시 갭 축소
                elif current_profit_rate > 3.0:
                    final_gap = dynamic_stop_gap * 0.9  # 3% 이상 수익 시 갭 약간 축소
                else:
                    final_gap = dynamic_stop_gap
                
                old_trailing_stop = position.get('trailing_stop_price', 0)
                position['trailing_stop_price'] = current_price * (1 - final_gap/100)
                
                logger.info(f"트레일링 스탑 갱신:")
                logger.info(f"- 신규 고점: {current_price:,.0f}원 (이전: {old_high:,.0f}원)")
                logger.info(f"- ATR 비율: {atr_ratio:.2f}%, 최종 스탑갭: {final_gap:.2f}%")
                logger.info(f"- 트레일링 스탑: {position['trailing_stop_price']:,.0f}원 (이전: {old_trailing_stop:,.0f}원)")
            else:
                logger.info(f"고점 유지: {position['high_price']:,.0f}원 (현재: {current_price:,.0f}원)")
                logger.info(f"현재 트레일링 스탑: {position.get('trailing_stop_price', 0):,.0f}원")

            # 트레일링 스탑 발동
            if 'trailing_stop_price' in position and current_price <= position['trailing_stop_price']:
                high_price = position.get('high_price', current_price)
                drop_from_high = (high_price - current_price) / high_price * 100
                logger.info(f"✅ 트레일링 스탑 발동 (고점대비 하락률: {drop_from_high:.2f}%)")
                # 강한 모멘텀 체크 (다른 매도 조건과 일관성 유지)
                if is_strong_momentum and drop_from_high < 1.0: # 하락폭이 1% 미만인 경우에만 적용
                    logger.info(f"⚠️ 트레일링 스탑 조건이나 강한 모멘텀으로 매도 보류")
                    return False, position, "MOMENTUM_HOLD"
                else:
                    logger.info(f"✅ 트레일링 스탑 발동 (고점대비 하락률: {drop_from_high:.2f}%)")
                    return True, position, "trailing_stop"

            elif 'trailing_stop_price' in position:
                stop_gap = (current_price - position['trailing_stop_price']) / current_price * 100
                logger.info(f"❌ 트레일링 스탑 미발동 (현재가와 스탑 차이: {stop_gap:.2f}%)")
        else:
            logger.info(f"❌ 트레일링 스탑 적용 조건 미달 (수익률: {current_profit_rate:.2f}% < {trailing_start_threshold}%)")
        
        # ===== 2. 강한 상승 모멘텀 체크 (즉시 매도 우회 여부 결정) =====
        is_strong_momentum = False
        
        # 분봉 데이터로 모멘텀 확인
        if 'minute_ohlcv' in current_data and current_data['minute_ohlcv'] is not None:
            minute_df = current_data['minute_ohlcv']
            if len(minute_df) >= 5:
                # 1. 최근 분봉 연속 상승 체크
                recent_candles = minute_df.tail(5)
                price_rising = True
                for i in range(1, len(recent_candles)):
                    if recent_candles['close'].iloc[i] <= recent_candles['close'].iloc[i-1]:
                        price_rising = False
                        break
                
                # 2. 거래량 급증 체크
                volume_increasing = recent_candles['volume'].iloc[-1] > recent_candles['volume'].mean() * 1.5
                
                # 3. 최근 양봉 비율 확인
                bullish_candles = sum(1 for i in range(len(recent_candles)) if recent_candles['close'].iloc[i] > recent_candles['open'].iloc[i])
                strong_buying = bullish_candles >= 4  # 5개 중 4개 이상 양봉
                
                # 강한 모멘텀 판단
                is_strong_momentum = (price_rising and volume_increasing) or (strong_buying and volume_increasing)
                
                if is_strong_momentum:
                    logger.info(f"강한 상승 모멘텀 감지:")
                    logger.info(f"- 연속 상승: {price_rising}")
                    logger.info(f"- 양봉 비율: {bullish_candles}/5")
                    logger.info(f"- 거래량 급증: {volume_increasing} ({recent_candles['volume'].iloc[-1]/recent_candles['volume'].mean():.1f}배)")

        # ===== 누적 수익 보호 로직 (당일 누적 수익률 1.5% 이상인 경우) =====

        # 일일 수익 상태 확인
        daily_profit = load_daily_profit_state()
        today_profit_rate = daily_profit['today_profit_rate']
        # 당일 누적 실현 수익률이 1% 이상일 때 추가 매수 종목 
        # 보호 로직 적용
        is_profit_protection_active = today_profit_rate >= 1.5

        if is_profit_protection_active:
            # 1. 새로 매수한 종목이 손실 구간에 진입하면 빠르게 청산
            if hours_passed < 0.3 and current_profit_rate < -0.4:
                # 손실 상황에서도 강한 모멘텀이 있는지 확인
                if is_strong_momentum and current_profit_rate > -0.5:  # 손실이 심각하지 않은 경우만
                    logger.info(f"⚠️ 당일 수익 보호: 신규 매수 후 손실이나 강한 모멘텀으로 매도 보류")
                else:
                    logger.info(f"✅ 당일 수익 보호: 신규 매수 후 수익률 {current_profit_rate:.2f}% 하락 - 빠른 손절")
                    return True, position, "PROFIT_PROTECTION_EARLY_LOSS"
            
            # 2. 수익이 났다가 수익의 절반 이상 반납 시 청산
            if 'high_profit_rate' not in position:
                position['high_profit_rate'] = max(0, current_profit_rate)
            elif current_profit_rate > position['high_profit_rate']:
                position['high_profit_rate'] = current_profit_rate
            
            high_profit = position.get('high_profit_rate', 0)
            if high_profit > 1.0 and current_profit_rate < high_profit * 0.5:
                # 강한 모멘텀 확인
                if is_strong_momentum and current_profit_rate > 0:  # 여전히 수익 중인 경우만
                    logger.info(f"⚠️ 당일 수익 보호: 수익 반납 조건이나 강한 모멘텀으로 매도 보류")
                else:
                    logger.info(f"✅ 당일 수익 보호: 최고 수익 {high_profit:.2f}%의 절반 이상 반납 (현재: {current_profit_rate:.2f}%)")
                    return True, position, "PROFIT_PROTECTION_RETREAT"
            
            # 3. 미실현 수익이 0.6% 이상이면 즉시 확정
            if current_profit_rate >= 0.6:
                # 강한 모멘텀이 있는 경우 이 조건을 우회
                if is_strong_momentum:
                    logger.info(f"⚠️ 당일 수익 보호: 미실현 수익 {current_profit_rate:.2f}% 즉시 확정 조건이나 강한 모멘텀으로 보류")
                else:
                    logger.info(f"✅ 당일 수익 보호: 미실현 수익 {current_profit_rate:.2f}% 즉시 확정")
                    return True, position, "PROFIT_PROTECTION_TAKE_SMALL_PROFIT"
            
            # 4. 트레일링 스탑 더 민감하게 설정
            if current_profit_rate > 0:
                # 수익 구간에서 보다 적극적인 트레일링 스탑 적용
                if 'protection_high_price' not in position or current_price > position['protection_high_price']:
                    position['protection_high_price'] = current_price
                    # 수익 상황에서는 0.3% 하락시 매도
                    protection_stop_price = current_price * (1 - 0.003)
                    position['protection_stop_price'] = protection_stop_price
                    logger.info(f"당일 수익 보호: 트레일링 스탑 강화 - 고점 대비 0.3% 하락 시 매도 ({protection_stop_price:,.0f}원)")
                
                # 트레일링 스탑 확인
                if 'protection_stop_price' in position and current_price <= position['protection_stop_price']:
                    # 강한 모멘텀 확인 - 하락폭이 매우 작은 경우만 예외 적용
                    protection_high_price = position.get('protection_high_price', current_price)
                    drop_percent = (protection_high_price - current_price) / protection_high_price * 100
                    if is_strong_momentum and drop_percent < 0.5:  # 0.5% 미만 하락
                        logger.info(f"⚠️ 당일 수익 보호: 강화된 트레일링 스탑 조건이나 강한 모멘텀으로 매도 보류")
                    else:
                        logger.info(f"✅ 당일 수익 보호: 강화된 트레일링 스탑 발동")
                        return True, position, "PROFIT_PROTECTION_TRAILING"


        # ===== 3. 높은 수익률 달성 시 즉시 매도 (모멘텀 고려) =====
        if is_morning_entry:
            # 오전장 매수 종목은 MORNING_TAKE_PROFIT 기준 적용
            if current_profit_rate >= MORNING_TAKE_PROFIT:
                # 상승 모멘텀이 강하면 즉시 매도 연기
                if is_strong_momentum:
                    logger.info(f"⚠️ 오전장 매수 종목 익절 기준({MORNING_TAKE_PROFIT:.2f}%) 도달했으나 강한 모멘텀으로 매도 보류")
                    return False, position, "MOMENTUM_HOLD"
                else:
                    logger.info(f"✅ 오전장 매수 종목 익절 {MORNING_TAKE_PROFIT:.2f}% 조건 충족 (수익률: {current_profit_rate:.2f}%)")
                    return True, position, "MORNING_TAKE_PROFIT"
        else:    
            if current_profit_rate >= IMMEDIATE_TAKE_PROFIT:
                # 상승 모멘텀이 강하면 즉시 매도 연기
                if is_strong_momentum:
                    logger.info(f"⚠️ 목표 수익률({IMMEDIATE_TAKE_PROFIT:.2f}%) 도달했으나 강한 모멘텀으로 매도 보류")
                    return False, position, "MOMENTUM_HOLD"
                else:
                    logger.info(f"✅ 목표 수익률 달성으로 즉시 매도 진행 (수익률: {current_profit_rate:.2f}%)")
                    return True, position, "TAKE_PROFIT"
            else:
                logger.info(f"❌ 목표 수익률({IMMEDIATE_TAKE_PROFIT}%) 미달: {current_profit_rate:.2f}%")

        # ===== 오후장 추가 조건: 호가창 급변 시 수익 보존 =====
        if is_afternoon_session and current_profit_rate > 0:
            try:
                # 현재 호가 정보 가져오기 - 안전하게 처리
                is_favorable, order_info = analyze_order_book(stock_code)
                
                # 호가 정보 유효성 검사
                if isinstance(order_info, dict) and 'order_strength' in order_info:
                    current_order_strength = order_info['order_strength']
                    
                    # 이전 호가 정보 가져오기 - 저장된 값 또는 기본값
                    last_check_time = position.get('last_order_check_time', 0)
                    prev_order_strength = position.get('prev_order_strength', current_order_strength)
                    
                    # 현재 시간 (타임스탬프)
                    current_timestamp = int(time.time())
                    
                    # 마지막 체크 이후 최소 30초가 지난 경우에만 비교 (너무 빈번한 비교 방지)
                    if current_timestamp - last_check_time >= 30:
                        # 호가 강도 변화율 계산
                        order_strength_change = (current_order_strength - prev_order_strength) / prev_order_strength * 100 if prev_order_strength > 0 else 0
                        
                        logger.info(f"호가 강도 변화율: {order_strength_change:.2f}% (현재: {current_order_strength:.2f}, 이전: {prev_order_strength:.2f})")
                        
                        # 호가 강도가 30% 이상 감소한 경우 수익 보존 매도
                        if order_strength_change <= -30 and current_profit_rate > 0:
                            # 강한 모멘텀이 있으면 이 조건도 우회
                            if is_strong_momentum:
                                logger.info(f"⚠️ 호가창 급변 감지됐으나 강한 모멘텀으로 매도 보류 (호가 강도 {order_strength_change:.2f}% 감소)")
                            else:
                                logger.info(f"✅ 호가창 급변으로 인한 수익 보존 매도 (호가 강도 {order_strength_change:.2f}% 감소)")
                                return True, position, "ORDER_FLOW_PROTECT"
                        
                        # 이전 값 업데이트 (큰 변경이 있을 때만)
                        if abs(order_strength_change) > 5:  # 5% 이상 변화가 있을 때만 업데이트
                            position['prev_order_strength'] = current_order_strength
                            position['last_order_check_time'] = current_timestamp
                    else:
                        logger.info(f"호가 체크 간격이 너무 짧음 (마지막 체크 후 {current_timestamp - last_check_time}초 경과)")
                else:
                    logger.info(f"유효한 호가 정보를 가져오지 못했습니다: {order_info}")
            except Exception as e:
                logger.error(f"호가 정보 분석 중 에러: {str(e)}")
        
        # ===== 오후장 추가 조건: ATR 기반 동적 익절 =====
        if is_afternoon_session and current_profit_rate > 0:
            try:
                atr = current_data.get('atr', 0)
                if atr > 0:  # ATR 값이 유효할 때만 계산
                    atr_profit_threshold = (atr / current_price * 100 * 0.8)  # ATR의 80%를 익절 임계값으로 설정
                    
                    logger.info(f"ATR 기반 익절 임계값: {atr_profit_threshold:.2f}% (ATR: {atr:.2f})")
                    
                    # 최소 임계값 설정 (너무 작은 값 방지)
                    atr_profit_threshold = max(atr_profit_threshold, 0.5)
                    
                    if current_profit_rate >= atr_profit_threshold:
                        # 강한 모멘텀이 있으면 이 조건도 우회
                        if is_strong_momentum:
                            logger.info(f"⚠️ ATR 기반 익절 조건 충족했으나 강한 모멘텀으로 매도 보류")
                        else:
                            logger.info(f"✅ ATR 기반 동적 익절 조건 충족 (수익률: {current_profit_rate:.2f}% >= 임계값 {atr_profit_threshold:.2f}%)")
                            return True, position, "ATR_TAKE_PROFIT"
            except Exception as e:
                logger.error(f"ATR 기반 익절 계산 중 에러: {str(e)}")

        # ===== 4. 시간 경과에 따른 동적 매도 수익률 =====
        # 장 시간대별 최소 보유 시간 동적 조정
        is_early_morning = is_in_early_morning_session()  # 오전 9시대
        is_morning_session = is_in_morning_session() # 오전 10:30까지

        # 시간대별 최소 보유 시간 조정
        adjusted_min_hold_hours = MIN_HOLD_HOURS
        if is_early_morning:
            adjusted_min_hold_hours = MIN_HOLD_HOURS * 0.5  # 오전 9시대는 최소 보유 시간 50%로 단축
            logger.info(f"오전 9시대 - 최소 보유 시간 50% 단축: {adjusted_min_hold_hours:.1f}시간")
        elif is_morning_session:
            adjusted_min_hold_hours = MIN_HOLD_HOURS * 0.7  # 오전 10:30까지는 최소 보유 시간 70%로 단축
            logger.info(f"오전장 - 최소 보유 시간 70% 단축: {adjusted_min_hold_hours:.1f}시간")
        else:
            logger.info(f"일반 시간대 - 기본 최소 보유 시간: {adjusted_min_hold_hours:.1f}시간")

        # 시간이 길어질수록 목표 수익률을 선형적으로 감소시킴
        if hours_passed >= 1.0:  # 1시간 이상 경과
            # 1시간 경과 후 부터는 목표 수익률을 점진적으로 낮춤
            # 4시간 이후에는 최소 0.8%의 수익만으로도 즉시 매도
            half_hours_passed = hours_passed * 2  # 30분 단위로 변환
            dynamic_take_profit = max(0.8, IMMEDIATE_TAKE_PROFIT - (half_hours_passed - 1.0) * 0.25)

            logger.info(f"경과 시간({hours_passed:.1f}시간)에 따른 완화된 목표 수익률: {dynamic_take_profit:.2f}%")
            
            if current_profit_rate >= dynamic_take_profit:
                # 강한 모멘텀이 있으면 이 조건도 우회
                if is_strong_momentum:
                    logger.info(f"⚠️ 시간 경과로 완화된 수익률 목표 달성했으나 강한 모멘텀으로 매도 보류")
                else:
                    logger.info(f"✅ 시간 경과로 완화된 수익률 목표 달성으로 즉시 매도")
                    return True, position, "TIME_BASED_TAKE_PROFIT"
            else:
                logger.info(f"❌ 완화된 목표 수익률({dynamic_take_profit:.2f}%) 미달: {current_profit_rate:.2f}%")
        else:
            # 1시간 미만은 원래 목표 수익률 유지
            logger.info(f"1시간 미만 경과 - 기본 목표 수익률 유지: {IMMEDIATE_TAKE_PROFIT}%")

        # ===== 5. 변동성 기반 손절 계산 =====
        # ATR 기반 동적 스탑로스 계산
        atr = current_data.get('atr', 0)
        atr_stop_gap = atr / current_price * 100
        dynamic_stop_gap = max(TRAILING_STOP_GAP, atr_stop_gap * 1.2)
        
        # ATR 관련 정보 로깅
        logger.info(f"ATR: {atr:.2f}, ATR 기반 스탑갭: {atr_stop_gap:.2f}%, 최종 스탑갭: {dynamic_stop_gap:.2f}%")
        
        # 변동성 적응형 스탑로스 계산
        adaptive_stop_loss_price = calculate_adaptive_stop_loss(
            entry_price, 
            atr, 
            current_price
        )

        # 스탑로스 상세 정보 로깅
        adaptive_stop_loss_rate = ((adaptive_stop_loss_price - entry_price) / entry_price) * 100
        logger.info(f"변동성 기반 스탑로스: {adaptive_stop_loss_price:,.0f}원 (손절률: {adaptive_stop_loss_rate:.2f}%)")

        # 변동성 기반 손절 조건 확인 - 단일 체크로 통합
        if adaptive_stop_loss_price > 0 and current_price <= adaptive_stop_loss_price and adaptive_stop_loss_price < entry_price:
            # 강한 모멘텀 체크 (손실이 심각하지 않을 경우에만)
            adaptive_stop_loss_rate = ((adaptive_stop_loss_price - entry_price) / entry_price) * 100
            if is_strong_momentum and adaptive_stop_loss_rate > -2.0:  # 손실이 2% 미만인 경우만
                logger.info(f"⚠️ 변동성 손절 조건 충족했으나 강한 모멘텀으로 매도 보류")
                return False, position, "MOMENTUM_HOLD"
            else:
                logger.info(f"✅ 변동성 손절 조건 충족 (현재가 {current_price:,.0f} <= 손절가 {adaptive_stop_loss_price:,.0f})")
                return True, position, "ADAPTIVE_STOPLOSS"
        else:
            logger.info(f"❌ 변동성 손절 조건 미달 (현재가 {current_price:,.0f} > 손절가 {adaptive_stop_loss_price:,.0f} 또는 손절가가 진입가 이상)")

        # 손절 임계값은 음수값이므로 min 함수가 올바른 접근법
        dynamic_loss_threshold = min(
            INITIAL_STOP_LOSS,  
            (adaptive_stop_loss_price - entry_price) / entry_price * 100
        )
        
        logger.info(f"수정된 동적 손실 임계값: {dynamic_loss_threshold:.2f}%")
        
        # 현재가가 변동성 기반 스탑로스 가격 이하인지 직접 체크
        if current_price <= adaptive_stop_loss_price:
            logger.info(f"✅ 변동성 손절 조건 충족 (현재가 <= 변동성 손절가)")
            return True, position, "ADAPTIVE_STOPLOSS"
        
        # 동적 손실 임계값 기반 손절 체크
        if current_profit_rate <= dynamic_loss_threshold:
            logger.info(f"✅ 동적 손절 조건 충족 (수익률: {current_profit_rate:.2f}% <= {dynamic_loss_threshold:.2f}%)")
            return True, position, "DYNAMIC_STOPLOSS"
        else:
            logger.info(f"❌ 동적 손절 조건 미달 (수익률: {current_profit_rate:.2f}% > {dynamic_loss_threshold:.2f}%)")

# ===== 6. 추세 보호 로직 (손실률이 큰 경우는 제외) =====
        # 수정: 손실이 -2% 이상인 경우 추세 보호 로직을 적용하지 않음
        if current_profit_rate < -2.0:
            logger.info(f"❌ 추세 보호 로직 무시 - 손실률(-2% 이하)이 큰 경우 추세 보호 사용 안함")
        else:
            # 추세 보호 로직에 is_strong_uptrend 함수 적용
            if is_strong_uptrend(current_data, current_profit_rate) or is_strong_momentum:
                logger.info("❌ 매도 보류 사유: 강한 단기 상승추세 감지 (손실률이 -2% 이내인 경우만 적용)")
                return False, position, "TREND_PROTECTION"
            else:
                logger.info("✅ 상승추세 아님 - 추세 보호 로직 해제")
        
        # ===== 7. 장 마감 시간 근처 체크 =====
        # 장 마감 시간 근처 체크 (15시 이후)
        is_near_market_close = current_time.hour >= 15
        
        # 최소 보유 시간 체크 - 장 마감 전에는 체크 무시
        if not is_near_market_close:
            min_hold_seconds = adjusted_min_hold_hours * 3600
            if time_diff.total_seconds() < min_hold_seconds:  # 시간을 초로 변환
                min_passed = time_diff.total_seconds() / 60
                # 손실이 -2% 이상이면 최소 보유 시간 체크 무시
                if current_profit_rate < -2.0:
                    logger.info(f"✅ 손실률(-2% 이하)이 큰 경우 최소 보유 시간 무시")
                else:
                    logger.info(f"❌ 매도 보류 사유: 최소 보유 시간 미달 - {min_passed:.1f}분 경과 (최소 {adjusted_min_hold_hours * 60:.1f}분 필요)")
                    return False, position, "HOLD"
            else:
                min_passed = time_diff.total_seconds() / 60
                logger.info(f"✅ 최소 보유 시간 충족: {min_passed:.1f}분 경과 (최소 {adjusted_min_hold_hours * 60:.1f}분)")
        else:
            # 장 마감 전에는 수익중인 경우 매도 가능하도록
            if current_profit_rate > 0.5:  # 0.5% 이상 수익시
                logger.info(f"장 마감 전 수익 보존 매도 검토 (수익률: {current_profit_rate:.2f}%)")
                return True, position, "MARKET_CLOSE_PROFIT"  # 장 마감 전 수익 보존 매도 추가
            else:
                # 손실중이면 추가 하락 방어를 위한 타이트한 스탑로스 적용
                adaptive_stop = calculate_adaptive_stop_loss(
                    entry_price,
                    current_data['atr'],
                    current_price,
                    INITIAL_STOP_LOSS * 0.7  # 손절 기준 30% 타이트하게
                )
                adaptive_stop_rate = (adaptive_stop - entry_price) / entry_price * 100
                logger.info(f"장 마감 전 타이트한 손절: 기준가 {adaptive_stop:,.0f}원 (손절률: {adaptive_stop_rate:.2f}%)")
                
                if current_price <= adaptive_stop:
                    logger.info(f"✅ 장 마감 전 손절 조건 충족으로 매도")
                    return True, position, "MARKET_CLOSE_STOPLOSS"
                else:
                    logger.info(f"❌ 장 마감 전 손절 조건 미달 (현재가 > 손절가)")
        
        # ===== 8. 호가 및 추가 매도 조건 =====
        # 호가 분석으로 매도 압력 확인
        try:
            is_favorable, order_info = analyze_order_book(position['code'])
            
            # 호가 상세 정보 로깅
            if isinstance(order_info, dict) and 'order_strength' in order_info:
                logger.info(f"호가 분석: 매수/매도 강도 = {order_info['order_strength']:.2f}")
                logger.info(f"매수잔량: {order_info['total_bid_rem']:,}, 매도잔량: {order_info['total_ask_rem']:,}")
                
                if (
                    order_info['order_strength'] < 0.6 and  # 매수/매도 강도 더 엄격하게
                    order_info['total_bid_rem'] / order_info['total_ask_rem'] < 0.5  # 매수/매도 잔량 비율 추가
                ):
                    # 강한 모멘텀이 있으면 이 조건도 우회
                    if is_strong_momentum:
                        logger.info(f"⚠️ 매수세 약화 감지됐으나 강한 모멘텀으로 매도 보류")
                    else:
                        logger.info(f"✅ 매도 사유: 매수세 현저히 약화 (매수/매도 강도: {order_info['order_strength']:.2f})")
                        return True, position, "SELLING_PRESSURE"
                else:
                    logger.info(f"❌ 매도 압력 조건 미달 (매수/매도 강도: {order_info['order_strength']:.2f})")
            else:
                logger.info(f"호가 정보 형식 오류: {order_info}")
        except Exception as e:
            logger.error(f"호가 분석 중 에러: {str(e)}")
        
        # 분봉 데이터 분석
        try:
            minute_data = analyze_minute_data(position.get('code', ''))
            
            # 매도 조건 세분화
            sell_conditions = {
                'selling_pressure': False,
                'vwap_breakdown': False,
                'volume_surge': False,
                'momentum_lost': False,
                'trailing_stop': False
            }
            
            # 매수세 약화 조건
            if minute_data and isinstance(minute_data, dict):
                if (
                    # 매수 압력이 더 낮아야 함
                    minute_data.get('buying_pressure', 1) < (BUYING_PRESSURE_THRESHOLD * 0.7) and 
                    
                    # 연속 음봉 조건 강화 
                    minute_data.get('continuous_bearish_count', 0) >= 4 and 
                    
                    # 수익률 조건 상향
                    current_profit_rate > 1.0 and
                    
                    # 호가 분석 추가 (order_info가 딕셔너리인 경우만)
                    isinstance(order_info, dict) and
                    order_info.get('order_strength', 1) < 0.6 and  # 매수/매도 강도 추가 확인
                    not order_info.get('very_high_buying_passed', False)  # 매우 높은 매수세 예외 처리 적용

                ):
                    # 강한 모멘텀이 있으면 이 조건도 우회
                    if is_strong_momentum:
                        logger.info(f"⚠️ 매수세 약화 감지됐으나 강한 모멘텀으로 매도 보류")
                    else:
                        sell_conditions['selling_pressure'] = True
                        logger.info(f"✅ 매수세 약화 조건 충족 (매수압력: {minute_data.get('buying_pressure', 0):.2f}, 연속음봉: {minute_data.get('continuous_bearish_count', 0)}개)")
                else:
                    if isinstance(minute_data, dict):
                        logger.info(f"❌ 매수세 약화 조건 미달:")
                        logger.info(f"   - 매수압력: {minute_data.get('buying_pressure', 0):.2f} (기준: {BUYING_PRESSURE_THRESHOLD * 0.7:.2f} 미만)")
                        logger.info(f"   - 연속음봉: {minute_data.get('continuous_bearish_count', 0)}개 (기준: 4개 이상)")
                        logger.info(f"   - 수익률: {current_profit_rate:.2f}% (기준: 1.0% 초과)")
                        if isinstance(order_info, dict):
                            logger.info(f"   - 매수/매도 강도: {order_info.get('order_strength', 0):.2f} (기준: 0.6 미만)")
                    else:
                        logger.info("❌ 분봉 데이터 형식 오류")
            else:
                logger.info("❌ 분봉 데이터 없음 - 매수세 약화 조건 확인 불가")

            # VWAP 하향 돌파
            if minute_data and isinstance(minute_data, dict):
                if (
                    not minute_data.get('above_vwap', True) and 
                    current_profit_rate > 1
                ):
                    # 강한 모멘텀이 있으면 이 조건도 우회
                    if is_strong_momentum:
                        logger.info(f"⚠️ VWAP 하향 돌파 감지됐으나 강한 모멘텀으로 매도 보류")
                    else:
                        sell_conditions['vwap_breakdown'] = True
                        logger.info(f"✅ VWAP 하향 돌파 조건 충족 (수익률: {current_profit_rate:.2f}% > 1%)")
                elif isinstance(minute_data, dict):
                    logger.info(f"❌ VWAP 하향 돌파 조건 미달 (VWAP 상단 여부: {minute_data.get('above_vwap', False)}, 수익률: {current_profit_rate:.2f}%)")
            
            # 거래량 급증
            if minute_data and isinstance(minute_data, dict):
                if (
                    minute_data.get('volume_surge', False) and 
                    current_profit_rate > 2 and 
                    not minute_data.get('buying_pressure', 0) > 0.5
                ):
                    # 강한 모멘텀이 있으면 이 조건도 우회
                    if is_strong_momentum:
                        logger.info(f"⚠️ 거래량 급증 감지됐으나 강한 모멘텀으로 매도 보류")
                    else:
                        sell_conditions['volume_surge'] = True
                        logger.info(f"✅ 거래량 급증 조건 충족 (수익률: {current_profit_rate:.2f}% > 2%)")
                elif isinstance(minute_data, dict):
                    logger.info(f"❌ 거래량 급증 조건 미달 (거래량급증: {minute_data.get('volume_surge', False)}, 수익률: {current_profit_rate:.2f}%)")
            
            # 모멘텀 상실
            if minute_data and isinstance(minute_data, dict):
                if (
                    minute_data.get('price_momentum', 0) < MOMENTUM_LOSS_THRESHOLD and 
                    not minute_data.get('volume_trend', False) and 
                    current_profit_rate > 1.5
                ):
                    # 강한 모멘텀이 있으면 이 조건도 우회
                    if is_strong_momentum:
                        logger.info(f"⚠️ 모멘텀 상실 감지됐으나 강한 상승 모멘텀으로 매도 보류")
                    else:
                        sell_conditions['momentum_lost'] = True
                        logger.info(f"✅ 모멘텀 상실 조건 충족 (가격모멘텀: {minute_data.get('price_momentum', 0):.3f} < {MOMENTUM_LOSS_THRESHOLD})")
                elif isinstance(minute_data, dict):
                    logger.info(f"❌ 모멘텀 상실 조건 미달 (가격모멘텀: {minute_data.get('price_momentum', 0):.3f})")
        except Exception as e:
            logger.error(f"분봉 데이터 분석 중 에러: {str(e)}")
        
        # 최종 매도 결정
        sell_decision = any(sell_conditions.values())
        
        # 가장 먼저 만족된 매도 사유 선택
        sell_type = next(
            (key for key, value in sell_conditions.items() if value), 
            "NONE"
        )
        
        if sell_decision:
            logger.info(f"✅ 최종 매도 결정: {sell_type}")
        else:
            logger.info(f"❌ 매도 조건 미달 - 모든 매도 조건 불충족")
        
        return sell_decision, position, sell_type
        
    except Exception as e:
        logger.error(f"트레일링 스탑 업데이트 중 에러: {str(e)}")
        return False, position, "ERROR"
    


def check_market_condition():
    """전반적인 시장 상황 체크 - 완화된 버전"""
    try:
        # KODEX 200으로 전체적인 시장 상황 확인
        kospi_data = get_stock_data('069500')  # KODEX 200
        if kospi_data is None:
            return True  # 데이터 획득 실패시 기본적으로 트레이딩 허용
            
        # 이전 조건: 20일선 위 + RSI 30-70
        # 수정된 조건:
        
        # 1. 추세 조건 완화: 5일선과의 관계로 단기 추세 확인
        market_trend_ok = (
            kospi_data['current_price'] > kospi_data['ma5'] or  # 5일선 위 또는
            abs(kospi_data['current_price'] / kospi_data['ma20'] - 1) < 0.02  # 20일선 2% 이내
        )
        
        # 2. RSI 조건 완화: 과매도/과매수 극단 상황에서만 제한
        market_rsi_ok = 20 < kospi_data['rsi'] < 80  # RSI 범위 확대
        
        # 3. MACD 반영: 강한 하락 추세인 경우만 제한
        macd_condition = (
            kospi_data['macd'] > kospi_data['macd_signal'] or  # 골든크로스이거나
            kospi_data['macd'] > kospi_data['prev_macd']  # MACD 상승 추세
        )
        
        # 세 조건 중 두 개 이상 충족시 매매 허용
        conditions_met = sum([market_trend_ok, market_rsi_ok, macd_condition])
        
        return conditions_met >= 2  # 세 조건 중 두 개 이상 충족시 True 반환
        
    except Exception as e:
        logger.error(f"Error checking market condition: {str(e)}")
        return True  # 에러 발생시 기본적으로 트레이딩 허용

@cached('news_articles')    
def get_news_articles(stock_code, company_name):
   """네이버 뉴스 API를 통한 관련 뉴스 수집"""
   try:
       # 회사명/종목코드 검증 로직 추가
       if not company_name or not stock_code:
           logger.info(f"경고: 잘못된 회사명 또는 종목코드 - 회사명: {company_name}, 종목코드: {stock_code}")
           return []

       logger.info(f"뉴스 검색 시도: {company_name} ({stock_code})")

       load_dotenv()
       
       current_time = datetime.now()
       twelve_hours_ago = current_time - timedelta(hours=12)
      
       keywords = [
           f"{company_name}",
           f"{stock_code}"
       ]
       
       all_articles = []
       processed_titles = set()
       
       for keyword in keywords:
           encText = urllib.parse.quote(keyword)
           url = f"https://openapi.naver.com/v1/search/news?query={encText}&display=50&sort=date"
           
           request = urllib.request.Request(url)
           request.add_header("X-Naver-Client-Id", os.getenv("NAVER_CLIENT_ID"))
           request.add_header("X-Naver-Client-Secret", os.getenv("NAVER_CLIENT_SECRET"))
           
           response = urllib.request.urlopen(request)
           
           if response.getcode() == 200:
               response_body = response.read()
               news_data = json.loads(response_body.decode('utf-8'))
               
               for item in news_data['items']:
                   # HTML 태그 및 특수문자 제거
                   title = re.sub('<[^>]+>', '', item['title'])
                   title = re.sub('&[a-zA-Z]+;', '', title)  # HTML 엔터티 제거
                #    title = re.sub('[^가-힣0-9a-zA-Z\s\[\]\(\)\.,-]', '', title)  # 허용된 문자만 남김
                   title = re.sub(r'[^가-힣0-9a-zA-Z\s\[\]\(\)\.,-]', '', title)                   
                   
                   description = re.sub('<[^>]+>', '', item['description'])
                   description = re.sub('&[a-zA-Z]+;', '', description)  # HTML 엔터티 제거
                #    description = re.sub('[^가-힣0-9a-zA-Z\s\[\]\(\)\.,-]', '', description)  # 허용된 문자만 남김
                   description = re.sub(r'[^가-힣0-9a-zA-Z\s\[\]\(\)\.,-]', '', description)                   
                   
                   # 제목 또는 내용에 회사명이 포함된 경우만 처리
                   if company_name not in title and company_name not in description:
                       continue
                       
                   if title in processed_titles:
                       continue
                   
                   pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                   
                   if pub_date >= twelve_hours_ago:
                       impact_keywords = [
                           '실적', '매출', '영업이익', '계약', '투자', '강세', '체결', '수주', 
                           '특허', 'MOU', '기술', '제품', '신제품', '개발', '협약', '증가',
                           '상승', '하락', '급등', '급락', '신고가', '신저가', '호실적', '흑자',
                           '적자', '매수', '매도', '목표가', '예상', '전망', '리포트'
                       ]
                       
                       if any(keyword in title or keyword in description for keyword in impact_keywords):
                           all_articles.append({
                               'title': title.strip(),  # 앞뒤 공백 제거
                               'description': description[:30].strip()  # 앞뒤 공백 제거
                           })
                           processed_titles.add(title)
           
           time.sleep(0.1)
       
       all_articles.sort(key=lambda x: x['title'])
       selected_articles = all_articles[:3]
       
       logger.info(f"\n=== {company_name} 주요 뉴스 ===")
       for i, article in enumerate(selected_articles, 1):
           logger.info(f"\n[{i}] {article['title']}")
           logger.info(f"내용: {article['description']}...")
       
       logger.info(f"\n총 {len(selected_articles)}개의 관련 뉴스를 찾았습니다.")
       
       return selected_articles
           
   except Exception as e:
       logger.error(f"뉴스 수집 중 에러 발생 - 회사명: {company_name}, 종목코드: {stock_code}")
       logger.error(f"뉴스 수집 중 에러 발생: {str(e)}")
       return []   


@cached('news_analysis')
def analyze_all_stocks_news(my_stocks):
    """모든 보유 종목의 뉴스를 한번에 분석"""
    try:
        if not my_stocks:
            return {}
            
        news_data = {
            "stocks": {}
        }
        
        for stock in my_stocks:
            stock_code = stock['StockCode']
            stock_name = stock['StockName']
            
            news_articles = get_news_articles(stock_code, stock_name)
            if not news_articles:
                logger.info(f"경고: {stock_name} ({stock_code})에 대한 뉴스를 찾을 수 없습니다.")
                continue
                
            news_data["stocks"][stock_name] = {
                "stock_code": stock_code,
                "articles": [
                    {
                        "title": article['title'],
                        "description": article['description']
                    }
                    for article in news_articles[:3]  # 최근 3개 뉴스
                ]
            }

        if news_data["stocks"]:
            client = openai.OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[{
                    "role": "system",
                    "content": """Analyze the impact of news articles on stock prices for multiple companies.
                    For each company, provide:
                    1. Company name (stock_name)
                    2. Decision (POSITIVE, NEGATIVE, or NEUTRAL)
                    3. Percentage impact (1-100 for positive/negative, 0 for neutral)
                    4. Reason for the decision

                    Return the analysis for each company in the provided JSON structure."""
                },
                {
                    "role": "user",
                    "content": json.dumps(news_data, ensure_ascii=False)
                }],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "stock_analysis_result",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "analyses": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "stock_name": {"type": "string"},
                                            "decision": {"type": "string", "enum": ["POSITIVE", "NEGATIVE", "NEUTRAL"]},
                                            "percentage": {"type": "integer"},
                                            "reason": {"type": "string"}
                                        },
                                        "required": ["stock_name", "decision", "percentage", "reason"]
                                    }
                                }
                            },
                            "required": ["analyses"]
                        }
                    }
                },
                max_tokens=1000
            )

            analysis_results = json.loads(response.choices[0].message.content)

            # 분석 결과를 news_data 구조에 통합
            if "analyses" in analysis_results:
                for analysis in analysis_results["analyses"]:
                    stock_name = analysis["stock_name"]
                    if stock_name in news_data["stocks"]:
                        news_data["stocks"][stock_name]["analysis"] = {
                            "decision": analysis["decision"],
                            "percentage": analysis["percentage"],
                            "reason": analysis["reason"]
                        }

            # 결과 로깅 및 알림
            msg = "📊 보유/매수대상 종목 뉴스 분석 결과\n"
            for analysis in analysis_results.get("analyses", []):
                msg += f"\n=== {analysis['stock_name']} ===\n"
                msg += f"판단: {analysis['decision']}\n"
                msg += f"영향도: {analysis['percentage']}%\n"
                msg += f"이유: {analysis['reason']}\n"

            logger.info(msg)
            # discord_alert.SendMessage(msg)

            return news_data
        
        return news_data  # 뉴스가 없는 경우 빈 구조 반환
        
    except Exception as e:
        logger.error(f"전체 뉴스 분석 중 에러: {str(e)}")
        return {}


def check_next_day_exit_conditions(stock_code, position, news_data=None):
    """다음날 보유 종목 재평가 - 새로운 뉴스 분석 결과 형식 사용"""
    try:
        current_data = get_stock_data(stock_code)

        if current_data is None:
            return False
        
        stock_name = KisKR.GetStockName(stock_code)
        
        entry_price = position['entry_price']
        current_price = current_data['current_price']
        profit_rate = (current_price - entry_price) / entry_price * 100
        
        if profit_rate < REEVALUATION_MIN_PROFIT:
            return False
        
        volume_increased = current_data['volume'] > current_data['prev_volume']
        price_declined = current_data['close'] < current_data['ma5']
        
        macd_declining = (current_data['macd'] < current_data['prev_macd'] and 
                         current_data['macd'] < current_data['macd_signal'])
                         
        rsi_overbought = current_data['rsi'] > MAX_BUY_RSI

        # 수정된 뉴스 분석 결과 형식 처리
        news_negative_impact = False
        news_analysis_info = None
        
        if news_data and "stocks" in news_data:
            # 종목명으로 해당 종목 찾기 시도
            for stock_name_key, stock_info in news_data["stocks"].items():
                if stock_info.get("stock_code") == stock_code and "analysis" in stock_info:
                    analysis = stock_info["analysis"]
                    news_negative_impact = (
                        analysis["decision"] == "NEGATIVE" and 
                        analysis["percentage"] > 50  # 부정적 영향이 50% 이상인 경우
                    )
                    news_analysis_info = analysis
                    break

        should_exit = (
            (volume_increased and price_declined) or
            macd_declining or
            rsi_overbought or
            news_negative_impact
        )
        
        if should_exit:
            msg = f"[다음날 재평가] {stock_name}({stock_code}) 매도 시그널 발생!\n"
            msg += f"수익률: {profit_rate:.2f}% (기준: {REEVALUATION_MIN_PROFIT:.1f}%)\n"
            msg += f"거래량 증가: {volume_increased}, 가격 하락: {price_declined}\n"
            msg += f"MACD 하락: {macd_declining}, RSI: {current_data['rsi']:.1f}\n"
            
            if news_negative_impact:
                for stock_info in news_data["stocks"].values():
                    if stock_info.get("stock_code") == stock_code:
                        analysis = stock_info["analysis"]
                        msg += f"뉴스 분석: {analysis['decision']} ({analysis['percentage']}%)\n"
                        msg += f"이유: {analysis['reason']}"
            
            logger.info(msg)
            discord_alert.SendMessage(msg)
        
        return should_exit
        
    except Exception as e:
        logger.error(f"다음날 재평가 중 에러: {str(e)}")
        return False
    
def get_actual_position_count(trading_state):
    # 실제 보유 종목 수
    held_positions = set(trading_state['positions'].keys())
    held_count = len(held_positions)
    
    # 미체결 주문 중인 종목 (이미 보유 중인 종목 제외)
    pending_orders = trading_state.get('pending_orders', {})
    pending_stocks = set()
    
    for stock_code, order_info in pending_orders.items():
        # 완전히 매도된 종목은 제외 (positions에 없고 status가 filled인 경우)
        # 부분 매도된 종목이라면 positions에 여전히 존재할 것임
        if not (stock_code not in held_positions and order_info.get('status') == 'filled'):
            # 이미 보유 중인 종목도 제외 (중복 카운트 방지)
            if stock_code not in held_positions:
                pending_stocks.add(stock_code)
    
    pending_count = len(pending_stocks)
    
    # 총 종목 수 (보유 종목 + 미체결 주문 종목)
    total_count = held_count + pending_count
    logger.info(f"get_actual_position_count: 보유 {held_count}개 + 미체결 {pending_count}개 = 총 {total_count}개")
    
    return total_count

def main():
   msg = "모멘텀 데이트레이딩 봇 시작!"
   logger.info(msg)
   discord_alert.SendMessage(msg)
 
   today = datetime.now().strftime('%Y-%m-%d')

################초기화 코드 선언#########################

    # 전역 변수로 뉴스 분석 관련 상태 유지
   news_analysis_done = False

   all_news_analysis = {}

    # 일별 매매 보고서 전송 완료 여부 표시
   send_daily_report_finished = False

    # 장 시작 알림 상태 초기화
   market_open_notified = False
  
   # 계좌현황 상태 초기화
   is_initialized = False

   # 당일 손익 한도 초과여부 초기화
   discord_today_profit = False
   discord_today_loss = False

   # 체결 지연 관련 안전 매수 기능 활성화
   safe_buy_enabled = True


   # 당일 매도 종목 리스트 초기화 - 이 부분을 추가해야 합니다
   sold_stocks = []

################초기화 코드 선언#########################

   while True:
       try:
           today = datetime.now().strftime('%Y-%m-%d')
           # 휴장일 체크
           if KisKR.IsTodayOpenCheck() == 'N':
              logger.info("휴장일 입니다.")
              time.sleep(300)  # 5분 대기
              continue
                      
           # 거래 상태 로드
           trading_state = load_trading_state()

           now = datetime.now()
           current_date = now.strftime('%Y-%m-%d')

           # 장 시작 운영 시간 및 시작시간 체크
           is_trading_time, is_market_open = check_trading_time()


           # 미체결 주문 자동 취소 함수 호출 (루프마다 체크)
           auto_cancel_pending_orders(max_pending_minutes=15)  # 15분 이후 취소

################################################## 초기화 코드 ####################################################

           # 일일 매매 이력 로드
           daily_trading = load_daily_trading_history()

           # 당일 매도 종목 리스트 업데이트
           sold_stocks = daily_trading.get('sold_stocks', [])

           # 날짜가 바뀌면 상태 초기화
           if daily_trading['last_date'] != today:

           # 장 시작 알림 상태 초기화
               market_open_notified = False

           # 일별 매매 보고서 전송 완료 여부 표시
               send_daily_report_finished = False

           # 계좌현황 상태 초기화
               is_initialized = False

           # 뉴스분석 날짜 변경에 따른 초기화
               all_news_analysis = {}
               news_analysis_done = False

           # 당일 손익 한도 초과여부 초기화
               discord_today_profit = False
               discord_today_loss = False

           # 당일 매도 종목 리스트 초기화 - 날짜 변경 시 명시적으로 초기화
               sold_stocks = []               

            # 오전 장중(8:00-10:00) 여부
           is_morning_session = is_in_morning_session()

            # 오전 이른 장중(9:00-09:20) 여부
           is_early_morning_session = is_in_early_morning_session()

            # 오후 장중(12:00-) 여부
           is_afternoon_session = is_in_afternoon_session()


           # 계좌현황 : 개장 후 아직 초기화되지 않은 경우 초기화 실행
           if is_market_open and not is_initialized:
               balance = KisKR.GetBalance()
               total_money = float(balance.get('TotalMoney', 0))
                
               # 봇의 운용 금액 계산
               trading_budget = total_money * TRADE_BUDGET_RATIO
                
               # 기존 daily_profit 로드
               daily_profit = load_daily_profit_state()
                            
               daily_profit = {
                   'last_date': current_date,
                   'start_money': trading_budget,
                   'today_profit': 0,
                   'today_profit_rate': 0,
                   'accumulated_profit': daily_profit.get('accumulated_profit', 0),  # 누적 데이터 유지
                   'total_trades': daily_profit.get('total_trades', 0),
                   'winning_trades': daily_profit.get('winning_trades', 0),
                   'max_profit_trade': daily_profit.get('max_profit_trade', 0),
                   'max_loss_trade': daily_profit.get('max_loss_trade', 0)
               }

               save_daily_profit_state(daily_profit)

               daily_trading = {
                   'last_date': current_date,
                   'sold_stocks': []
               }

               save_daily_trading_history(daily_trading)

                # 당일 거래 히스토리 초기화
               trade_history = {
                   'date': current_date,
                   'trades': []
               }
               save_today_trade_history(trade_history)

               
               is_initialized = True
               time.sleep(60)               
                
################################################## 초기화 코드 ####################################################

            # 실시간 계좌 정보 업데이트
           try:
               current_balance = KisKR.GetBalance()
               current_total_money = float(current_balance.get('TotalMoney', 0))
               current_stock_revenue = float(current_balance.get('StockRevenue', 0))
           except Exception as e:
               logger.info(f"계좌 정보 조회 중 에러: {str(e)}")
               time.sleep(30)
               continue

            # 장 시작 시점에 계좌현황 알림
           if is_market_open and not market_open_notified:
               msg = f"===== 장 시작 계좌 현황 =====\n"
               msg += f"총 평가금액: {current_total_money:,.0f}원\n"
               msg += f"투자원금: {daily_profit['start_money']:,.0f}원\n"  # 투자원금 표시 추가
               msg += f"이 봇의 운용 금액: {trading_budget:,.0f}원\n"
               msg += f"누적 손익: {current_stock_revenue:,.0f}원\n"
               msg += f"당일 손익: {daily_profit['today_profit']:,.0f}원 ({daily_profit['today_profit_rate']:.2f}%)"
               logger.info(msg)
               discord_alert.SendMessage(msg)
               market_open_notified = True

           # 장 개장일이면서 장 마감 시간이면 일일 보고서 전송
           if KisKR.IsTodayOpenCheck() and now.hour == 15 and now.minute >= 30 and now.minute < 50 and not send_daily_report_finished:  # 15:30~15:35 사이
               send_daily_report()  # 기존 계좌 보고서
               send_daily_trading_report()  # 당일 매매 수익 보고서
               send_daily_report_finished = True

           if not is_trading_time:
               msg = "장 시간 외 입니다. 다음 장 시작까지 대기"
               logger.info(msg)
               time.sleep(300)  # 5분 대기
               continue

           trading_budget = current_total_money * TRADE_BUDGET_RATIO

           # 손실 한도 체크를 위해 daily_profit 로드
           daily_profit = load_daily_profit_state()

           # 당일 실현손익 기준으로 손실 한도 체크
           if daily_profit['today_profit_rate'] <= MAX_DAILY_LOSS:
               msg = f"⚠️ 금일 봇 거래 손실 한도 도달! (당일 실현손익률: {daily_profit['today_profit_rate']:.2f}% ≤ {MAX_DAILY_LOSS}%)\n"
               msg += f"실현손익: {daily_profit['today_profit']:,.0f}원"
               msg += f"신규 매수는 중단되지만 기존 포지션 관리는 계속됩니다."
               logger.info(msg)
               if not discord_today_loss:
                    discord_alert.SendMessage(msg)
                    discord_today_loss = True
           
           # 당일 실현손익 기준으로 수익 한도 체크 - 새로운 매수만 제한하고 손절은 계속 작동하도록 수정
           if daily_profit['today_profit_rate'] >= MAX_DAILY_PROFIT:
               msg = f"🎯 금일 봇 거래 목표 수익 달성! (당일 실현수익률: {daily_profit['today_profit_rate']:.2f}% ≥ {MAX_DAILY_PROFIT}%)\n"
               msg += f"실현수익: {daily_profit['today_profit']:,.0f}원\n"
               msg += f"신규 매수는 중단되지만 기존 포지션 관리는 계속됩니다."
               logger.info(msg)
               if not discord_today_profit:
                    discord_alert.SendMessage(msg)
                    discord_today_profit = True

           # 봇이 보유한 종목들의 종목코드 리스트
           bot_positions = list(trading_state['positions'].keys())

           logger.info(f"bot_positions 내용: {bot_positions}")           

           # 초기화 추가
           bot_stocks = []

           # 봇 포지션이 있는 경우에만 처리
           if bot_positions:
              # 초기화 추가
               # 보유 포지션 체크 및 트레일링 스탑/손절
               my_stocks = KisKR.GetMyStockList()
               # 봇이 매매한 종목만 필터링
               bot_stocks = [stock for stock in my_stocks if stock['StockCode'] in bot_positions]

            # 오전 장중(9:00-10:00)에만 일일 뉴스 분석
           if is_morning_session and not news_analysis_done and bot_stocks:
               logger.info("오늘의 뉴스 분석 시작...")
               all_news_analysis = analyze_all_stocks_news(bot_stocks)
               news_analysis_done = True
               msg = "오늘의 보유 종목 뉴스 분석 완료"
               logger.info(msg)
            #    discord_alert.SendMessage(msg)

           # 봇이 매매한 종목만 체크
           for stock in bot_stocks:
               stock_code = stock['StockCode']
               if stock_code in trading_state['positions']:
                   position = trading_state['positions'][stock_code]
                   current_price = KisKR.GetCurrentPrice(stock_code)
                   current_data = get_stock_data(stock_code)
                                
                   # 기존 트레일링 스탑 체크
                   should_sell, updated_position, sell_type = update_trailing_stop(position, current_price, current_data)
                                
                   # 오전 장중이면 다음날 재평가 로직도 체크
                   if is_morning_session and not should_sell:  # 트레일링 스탑에 걸리지 않은 경우만

                   # entry_time을 datetime 객체로 변환
                       entry_time = datetime.strptime(position['entry_time'], '%Y-%m-%d %H:%M:%S')
                       current_time = datetime.now()

                   # 매수일자와 현재 일자가 다른 경우에만 재평가
                       if entry_time.date() < current_time.date():
                            if check_next_day_exit_conditions(stock_code, position, all_news_analysis):
                                should_sell = True
                                sell_type = "REEVALUATION"
                                
                   trading_state['positions'][stock_code] = updated_position
                   save_trading_state(trading_state)

                   if should_sell:
                       # 분할매도 조건 확인
                       if sell_type.startswith("FRACTIONAL_"):
                           # 분할매도 로직 호출
                           sell_reason = sell_type.replace("FRACTIONAL_", "")
                           
                           # determine_fractional_sell 함수에서 얻은 매도 비율 다시 계산
                           # (함수 호출 결과에서 바로 추출할 수 없어 매도 유형에 따라 설정)
                           sell_ratio = 0.0
                           
                           if sell_reason == "HIGH_VOLATILITY_PROFIT":
                               sell_ratio = HIGH_VOL_SELL_RATIO
                           elif sell_reason == "FIRST_STAGE_PROFIT":
                               sell_ratio = FIRST_SELL_RATIO
                           elif sell_reason == "SECOND_STAGE_PROFIT":
                               sell_ratio = SECOND_SELL_RATIO
                           elif sell_reason == "THIRD_STAGE_PROFIT":
                               sell_ratio = THIRD_SELL_RATIO
                               
                           # 분할매도 실행
                           success, trade_info, remaining_amount = execute_fractional_sell(
                               stock_code, 
                               position, 
                               sell_ratio, 
                               sell_reason, 
                               daily_profit
                           )
                           
                           if success:
                               # 거래 이력 저장
                               trade_history = load_today_trade_history()
                               if trade_history['date'] != current_date:
                                   trade_history = {'date': current_date, 'trades': []}

                               # trade_info가 None이 아닌 경우에만 거래 이력에 추가
                               if trade_info is not None:  # None 체크로 명확히 함
                                   trade_history['trades'].append(trade_info)
                                   save_today_trade_history(trade_history)
                                   logger.info(f"거래 이력 저장 완료: {stock_code}")
                               else:
                                   logger.warning(f"{stock_code} 거래 정보가 없어 이력에 저장하지 않음")
                                
                               # 분할매도 정보 업데이트
                               if remaining_amount > 0:
                                   # 분할매도 단계 업데이트
                                   if 'fractional_sell_stage' not in position:
                                       position['fractional_sell_stage'] = 0
                                   
                                   position['fractional_sell_stage'] += 1
                                   position['last_fractional_sell_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                   position['amount'] = remaining_amount
                                   
                                   # 트레이딩 상태 저장
                                   trading_state['positions'][stock_code] = position
                                   save_trading_state(trading_state)
                                   
                                   logger.info(f"{stock_name}({stock_code}) 분할매도 완료 - 포지션 업데이트: 남은 수량 {remaining_amount}주, 단계 {position['fractional_sell_stage']}")
                               else:
                                   # 전체 매도 완료된 경우
                                   del trading_state['positions'][stock_code]
                                   save_trading_state(trading_state)
                                   
                                   # 당일 매도 종목 리스트에 추가 및 저장
                                   daily_trading = load_daily_trading_history()
                                   if stock_code not in daily_trading['sold_stocks']:
                                       daily_trading['sold_stocks'].append(stock_code)
                                       save_daily_trading_history(daily_trading)
                                       
                                   logger.info(f"{stock_name}({stock_code}) 전체 매도 완료 - 포지션 삭제")
                           else:
                               # 매도 실패 시 로그 및 알림 추가
                               msg = f"⚠️ {stock_name}({stock_code}) 분할매도 실패 - 다음 주기에 재시도합니다."
                               logger.warning(msg)
                               discord_alert.SendMessage(msg)
                       else:
                           # 기존 매도 로직 사용 (변경 없음)
                           success, trade_info, remaining_amount = handle_sell_order(
                               stock_code, 
                               position, 
                               sell_type, 
                               daily_profit
                            )
                           
                           if success:
                               # 거래 이력 저장
                               trade_history = load_today_trade_history()
                               if trade_history['date'] != current_date:
                                   trade_history = {'date': current_date, 'trades': []}

                               # trade_info가 None이 아닌 경우에만 거래 이력에 추가
                               if trade_info is not None:  # None 체크로 명확히 함
                                   trade_history['trades'].append(trade_info)
                                   save_today_trade_history(trade_history)
                                   logger.info(f"거래 이력 저장 완료: {stock_code}")
                               else:
                                   logger.warning(f"{stock_code} 거래 정보가 없어 이력에 저장하지 않음")
                                
                               # 일부 매도인 경우 (remaining_amount > 0)
                               if remaining_amount > 0:
                                   # 포지션 수량 업데이트
                                   trading_state['positions'][stock_code]['amount'] = remaining_amount
                                   save_trading_state(trading_state)
                                   logger.info(f"{stock_name}({stock_code}) 일부 매도 완료 - 남은 수량: {remaining_amount}주")
                               else:
                                   # 전체 매도인 경우 - 포지션 삭제
                                   del trading_state['positions'][stock_code]
                                   save_trading_state(trading_state)
                                   # 당일 매도 종목 리스트에 추가 및 저장
                                   daily_trading = load_daily_trading_history()
                                   if stock_code not in daily_trading['sold_stocks']:
                                       daily_trading['sold_stocks'].append(stock_code)
                                       save_daily_trading_history(daily_trading)

                               # 여기에 미체결 주문 상태 제거 로직 추가
                               if 'pending_orders' in trading_state and stock_code in trading_state['pending_orders']:
                                   del trading_state['pending_orders'][stock_code]
                                   logger.info(f"{stock_code} 미체결 주문 상태 제거")
                                   save_trading_state(trading_state)

                           else:
                               # 매도 실패 시 로그 및 알림 추가
                               msg = f"⚠️ {stock_name}({stock_code}) 매도 실패 - 다음 주기에 재시도합니다."
                               logger.warning(msg)
                               discord_alert.SendMessage(msg)

           # 시장 상황 체크
        #    if not check_market_condition():
        #        msg = "시장 상황이 좋지 않아 거래를 보류합니다."
        #        logger.info(msg)
        #        discord_alert.SendMessage(msg)
        #        time.sleep(300)  # 5분 대기
        #        continue                           
                           
           # 새로운 매매기회 스캔 (수정버전 / 15시 이전 까지만 작동)

           logger.info("==== 매수 조건 확인 ====")
           logger.info(f"현재 시간: {now.hour}:{now.minute}")
           # 기존 로그 추가 (단순 포지션 수 체크)
           logger.info(f"포지션 수 체크: {len(trading_state['positions'])} < {MAX_BUY_AMOUNT} = {len(trading_state['positions']) < MAX_BUY_AMOUNT}")

          # 실제 보유 종목 수와 미체결 주문 수를 함께 확인
        #    held_count, pending_count, total_count = count_total_positions(trading_state)
          # 실제 보유 종목 수와 미체결 주문 수를 함께 확인 - 분할매수 고려
           held_count, pending_count, adjusted_count, available_slots = count_total_positions_for_fractional(trading_state)

           # 총 보유 종목 수(실제 보유 + 미체결)가 최대 허용치보다 작은 경우에만 추가 매수 진행
           logger.info(f"get_actual_position_count 값 : {get_actual_position_count(trading_state)}")
                      
           if now.hour < 15 and get_actual_position_count(trading_state) < MAX_BUY_AMOUNT:  # 15시 이전, 최대 보유 종목 수 미만
               logger.info(f"추가 매수 가능: 현재 {adjusted_count}개 보유: {held_count}/주문중: {pending_count} (최대 {MAX_BUY_AMOUNT}개)")

               # 9시 5분 이전인지 확인하는 로직 추가
               if is_too_early_for_trading():
                   logger.info("오전 9시 5분 이전에는 매수하지 않습니다. 9시 5분 이후에 매수를 시작합니다.")
                   time.sleep(60)  # 1분 대기
                   continue

               momentum_stocks = scan_momentum_stocks()
               
               if momentum_stocks:
                   current_position_count = get_actual_position_count(trading_state)
                   if current_position_count >= MAX_BUY_AMOUNT:
                       logger.info(f"최대 보유 종목 수({MAX_BUY_AMOUNT}개) 도달, 추가 매수 중단")
                       continue

                   # 스캔 결과가 있을 때 한 번 더 포지션 확인 (추가된 부분)
                   #held_count, pending_count, total_count = count_total_positions(trading_state)
                   held_count, pending_count, adjusted_count, available_slots = count_total_positions_for_fractional(trading_state)

                   if adjusted_count >= MAX_BUY_AMOUNT:
                       logger.info(f"스캔 완료 후 확인 - 최대 보유 종목 수({MAX_BUY_AMOUNT}개) 도달, 추가 매수 중단")
                       time.sleep(30)  # 30초 대기
                       continue  # 다음 루프로 건너뜀                

                   daily_trading = load_daily_trading_history()  # 현재 매매 이력 로드
                   
                   for stock in momentum_stocks:
                       
                       current_position_count = get_actual_position_count(trading_state)
                       if current_position_count >= MAX_BUY_AMOUNT:
                           logger.info(f"최대 보유 종목 수({MAX_BUY_AMOUNT}개) 도달, 보유: {held_count}/주문중: {pending_count}: 추가 매수 중단")
                           break                       
                       # 다시 한번 보유 한도 체크 (분할매수 고려)
                       held_count, pending_count, adjusted_count, available_slots = count_total_positions_for_fractional(trading_state)

                       # 당일 매도 종목은 스킵
                       if stock['code'] in daily_trading['sold_stocks']:
                           logger.info(f"{stock['name']}({stock['code']}) - 당일 매도 종목으로 매수 제외")
                           continue

                    #    # 현재 보유 종목은 스킵 (이미 count_total_positions에서 체크하지만 안전하게 한번 더)
                    #    if stock['code'] in trading_state['positions']:
                    #        logger.info(f"{stock['name']}({stock['code']}) - 이미 보유중인 종목으로 매수 제외")
                    #        continue

                       # 분할 매수 로직 적용 - 이미 보유중이더라도 최대 단계에 도달하지 않았으면 매수 진행
                       if stock['code'] in trading_state['positions']:
                           position = trading_state['positions'][stock['code']]
                           current_stage = position.get('buy_stage', 1)
                            
                           # 최대 매수 단계 도달 여부 확인
                           if current_stage >= MAX_BUY_STAGES:
                               logger.info(f"{stock['name']}({stock['code']}) - 최대 매수 단계 도달({current_stage}/{MAX_BUY_STAGES})로 매수 제외")
                               continue
                            
                           # 쿨다운 체크
                           last_buy_time = position.get('last_buy_time')
                           if last_buy_time:
                               last_buy_datetime = datetime.strptime(last_buy_time, '%Y-%m-%d %H:%M:%S')
                               time_since_last_buy = (datetime.now() - last_buy_datetime).total_seconds()
                                
                               if time_since_last_buy < FRACTIONAL_BUY_COOLDOWN:
                                   remaining_min = (FRACTIONAL_BUY_COOLDOWN - time_since_last_buy) / 60
                                   logger.info(f"{stock['name']}({stock['code']}) - 분할매수 쿨다운 중 (남은 시간: {remaining_min:.1f}분)")
                                   continue
                                
                           logger.info(f"{stock['name']}({stock['code']}) - 분할매수 {current_stage}단계 → {current_stage+1}단계 진행 가능")

                       # 해당 종목의 미체결 주문이 있는지 확인
                       if check_pending_orders(stock['code']):
                           # 미체결 주문이 있으면 이 종목 건너뜀
                           logger.info(f"{stock['name']}({stock['code']}) - 미체결 주문 있음, 매수 건너뜀")
                           continue

                        # 최대 종목 수 초과여부 확인
                       if len(trading_state['positions']) >= MAX_BUY_AMOUNT:
                           logger.info("최대 보유 종목 수 초과로 새로운 매수 불가")
                           continue  # 현재 종목 건너뛰기

                       # 3000원 미만 종목 필터링 (뉴스 분석 전에 추가)
                       if stock['price'] < MIN_PRICE_THRESHOLD:
                           logger.info(f"⚠️ 저가 종목 매수 제한: {stock['name']}({stock['code']}) - 현재가 {stock['price']:,}원 < 기준가 {MIN_PRICE_THRESHOLD:,}원")
                           continue


                       logger.info(f"\n{stock['name']}({stock['code']}) 매수 분석 시작")

                       ######################### 뉴스 AI분석 추가 #########################
                       try:
                           news_data = analyze_all_stocks_news([{
                               'StockCode': stock['code'],
                               'StockName': stock['name']
                           }])
                                            
                           # 뉴스 분석 결과 확인 - 수정된 구조에 맞게 접근
                           is_news_negative = False
                           analysis = None  # analysis 변수 초기화

                           # 뉴스가 없는 경우 처리 추가 (일단 주석처리)
                           if not news_data or "stocks" not in news_data or len(news_data["stocks"]) == 0:
                               if is_early_morning_session:
                                   # 오전장에는 뉴스 없음을 NEUTRAL로 간주하여 매수 제한
                                   is_news_negative = True
                                   logger.info(f"{stock['name']}({stock['code']}) - 뉴스 정보 없음, 오전장 기준 NEUTRAL로 간주하여 매수 제외")
                                    
                                   # 캐시 키 생성 (중복 알림 방지용)
                                   cache_key = f"{stock['code']}_no_news"
                                   cache_manager = CacheManager.get_instance()
                                   if not cache_manager.get('discord_news_messages', cache_key):
                                       msg = f"⚠️ {stock['name']}({stock['code']}) 매수 제외\n"
                                       msg += f"- 사유: 오전장 시간대 뉴스 정보 없음 (NEUTRAL 간주)"
                                       #discord_alert.SendMessage(msg)
                                       cache_manager.set('discord_news_messages', cache_key, True)
                                    
                                   continue  # 매수 제외하고 다음 종목으로
                               else:
                                   # 일반 시간대에는 뉴스 없음을 허용
                                   logger.info(f"{stock['name']}({stock['code']}) - 뉴스 정보 없음, 일반 시간대 매수 허용")


                           if news_data and "stocks" in news_data:
                               # 종목명으로 해당 종목의 분석 결과 찾기
                               for stock_name, stock_info in news_data["stocks"].items():
                                   if stock_info.get("stock_code") == stock['code'] and "analysis" in stock_info:
                                       analysis = stock_info["analysis"]
                                            
                                       # 필요한 키들이 모두 있는지 확인
                                       if all(key in analysis for key in ["decision", "percentage", "reason"]):

                                           if is_early_morning_session:  # 오전장인 경우 오전장 기준으로 분석
                                                # NEUTRAL도 매수 제한에 포함
                                               if analysis["decision"] == "NEUTRAL":
                                                   is_news_negative = True
                                                   logger.info(f"뉴스 분석 결과 중립적(오전장 기준 매수 제한): {analysis['reason']}")
                                                   break
                                               if analysis["decision"] == "POSITIVE" and isinstance(analysis["percentage"], (int, float)):
                                                   if analysis["percentage"] <= 10:  # 긍정적 영향이 10% 이하인 경우
                                                       is_news_negative = True
                                                       logger.info(f"뉴스 분석 결과 긍정적 이지만 영향도 부족(오전장 기준): {analysis['reason']}")
                                                       break
                                               if analysis["decision"] == "NEGATIVE":
                                                   is_news_negative = True
                                                   logger.info(f"뉴스 분석 결과 부정적: {analysis['reason']}")
                                                   break
                                           else:  # 오전장이 아닌 경우
                                               if analysis["decision"] == "NEGATIVE" and isinstance(analysis["percentage"], (int, float)):
                                                   if analysis["percentage"] > 50:  # 부정적 영향이 50% 이상인 경우
                                                       is_news_negative = True
                                                       logger.info(f"뉴스 분석 결과 부정적: {analysis['reason']}")
                                                       break

                               if is_news_negative and analysis:  # analysis가 있는 경우에만 메시지 전송
                                   # 캐시 키 생성 (종목코드와 메시지 타입으로 구성)
                                   cache_key = f"{stock['code']}_negative_news"
                                   # 캐시 매니저에서 메시지 전송 여부 확인
                                   cache_manager = CacheManager.get_instance()
                                   if not cache_manager.get('discord_news_messages', cache_key):
                                       logger.info(f"{stock['name']}({stock['code']}) - 부정적인 뉴스로 인해 매수 제외")
                                       msg = f"⚠️ {stock['name']}({stock['code']}) 매수 제외\n"
                                       msg += f"- 사유: {analysis.get('reason', '부정적인 뉴스')}\n"
                                       msg += f"- 영향도: {analysis.get('percentage', 0)}%"
                                       discord_alert.SendMessage(msg)

                                       # 메시지 전송 기록을 캐시에 저장
                                       cache_manager.set('discord_news_messages', cache_key, True)
                                   else:
                                       logger.info(f"{stock['name']}({stock['code']}) - 부정적인 뉴스 알림 이미 전송됨 (캐시 유효)")
                                   continue  # 부정적 뉴스가 있는 경우 이 종목의 매수를 건너뜀

                       except Exception as e:
                           logger.error(f"뉴스 분석 중 에러 발생: {str(e)}")
                           discord_alert.SendMessage(f"⚠️ 뉴스 분석 중 에러: {str(e)}")
                           continue
    
                    ######################### 뉴스 AI분석 끝 #########################
                       # 주문가능 예산 계산
                       available_budget = trading_budget / (MAX_BUY_AMOUNT - len(trading_state['positions']))
                       logger.info(f"할당 예산: {available_budget:,.0f}원")

                       position = None  # 변수 초기화
                       if stock['code'] in trading_state['positions']:
                           position = trading_state['positions'][stock['code']]

                       if position and position.get('buy_stage', 0) > 0:
                           # 이미 분할매수 중인 경우 원래 계획 수량 사용
                           buy_amount = position.get('total_planned_amount', 0)
                           logger.info(f"{stock['name']}({stock['code']}) - 분할매수 중: 기존 계획 수량 {buy_amount}주 사용")
                       else:
                           # 신규 매수인 경우 새로 계산
                           buy_amount = calculate_position_size(
                               available_budget,
                               stock['code'],
                               stock['price'],
                               stock['atr'],
                               trading_state['positions']
                           )

                       logger.info(f"계산된 매수 수량: {buy_amount}주 (주가: {stock['price']:,.0f}원)")

                       if buy_amount < 1:
                           logger.info("매수 수량이 1주 미만이거나 유동성 부족으로 매수 보류")
                           continue

                       try:
                           stock_data = get_stock_data(stock['code'])
                           if stock_data is None:
                               logger.info(f"{stock['name']}({stock['code']}) - 종목 데이터 로드 실패")
                               continue

                           if not check_short_term_momentum(stock_data):
                               logger.info(f"{stock['name']}({stock['code']}) - 단기 하락추세로 매수 보류")
                               continue       

                           if is_afternoon_session:
                               if stock_data['rsi'] > MAX_BUY_RSI:
                                   logger.info(f"{stock['name']}({stock['code']}) - 과매수 상태({stock['rsi']})로 매수 보류")
                                   continue

                           logger.info("매수 주문 시작...")
                           msg = f"{stock['name']}({stock['code']}) 모멘텀 매수 시그널 포착! {buy_amount}주 매수 진행\n"
                           msg += f"RSI: {stock['rsi']:.2f}, 거래량: {stock['volume_ratio']:.2f}배"
                           logger.info(msg)
                           #discord_alert.SendMessage(msg)

                           # 안전 매수 기능 활성화된 경우 새로운 함수 사용
                           if is_morning_session:
                               safe_buy_enabled = True
                               logger.info(f"오전장 시간대({now.hour}:{now.minute:02d}) - 안전매수 기능 활성화")
                            #    if is_early_morning_session:
                            #        logger.info("장초반 시간대 - 안전매수 강화 모드")
                           else:
                               safe_buy_enabled = False
                               logger.info(f"일반 시간대({now.hour}:{now.minute:02d}) - 기본 매수 기능 사용")

                           if safe_buy_enabled:
                               # 추가 안전장치가 적용된 매수 함수 사용
                               executed_price, error, executed_amount = handle_buy_order_with_safety(
                                   stock['code'],
                                   stock['name'],
                                   buy_amount,
                                   stock['price'],
                                   stock_data,
                                   trading_state  # trading_state 추가
                               )
                           else:
                               # 기존 매수 함수 사용
                               executed_price, error, executed_amount = handle_buy_order(
                                   stock['code'],
                                   stock['name'],
                                   buy_amount,
                                   stock['price'],
                                   stock_data,
                                   trading_state  # trading_state 추가
                               )                               

                           if error:
                               error_msg = f"매수 주문 중 에러 발생: {error}"
                               logger.error(error_msg)
                               #discord_alert.SendMessage(f"⚠️ {stock['name']}({stock['code']}) {error_msg}")
                               continue

                            # 수정된 부분: 체결된 경우에만 포지션 정보 업데이트하고, 조정된 수량 사용
                            # 포지션 상태 업데이트 시도
                           try:
                               # 이미 해당 종목이 포지션에 있는 경우
                               if stock['code'] in trading_state['positions']:
                                   position = trading_state['positions'][stock['code']]
                                    
                                   # 현재 매수 단계 확인 및 다음 단계로 진행
                                   current_stage = position.get('buy_stage', 1)
                                   next_stage = current_stage + 1
                                    
                                   # 분할매수 정보 업데이트
                                   trading_state['positions'][stock['code']] = {
                                       'entry_price': executed_price,
                                       'amount': executed_amount,
                                       'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                       'trading_fee': buy_fee,
                                       'code': stock['code'],
                                       'strategy': 'momentum_buy',
                                       'buy_stage': next_stage,  # 다음 단계로 진행
                                       'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                       'total_planned_amount': buy_amount  # 원래 계획된 총 매수량
                                   }
                                    
                                   logger.info(f"분할매수 단계 진행:")
                                   logger.info(f"- 종목: {stock['name']}({stock['code']})")
                                   logger.info(f"- 이전 단계: {current_stage}")
                                   logger.info(f"- 현재 단계: {next_stage}")
                                   logger.info(f"- 매수가: {executed_price:,.0f}원")
                                   logger.info(f"- 수량: {executed_amount}주")
                                
                               # 신규 매수인 경우
                               else:
                                   trading_state['positions'][stock['code']] = {
                                       'entry_price': executed_price,
                                       'amount': executed_amount,
                                       'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                       'trading_fee': buy_fee,
                                       'code': stock['code'],
                                       'strategy': 'momentum_buy',
                                       'buy_stage': 1,  # 첫 번째 단계
                                       'last_buy_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                       'total_planned_amount': buy_amount  # 원래 계획된 총 매수량
                                   }
                                    
                                   logger.info(f"신규 매수 - 첫 번째 단계: {stock['name']}({stock['code']})")
                                
                               # 상태 저장
                               save_trading_state(trading_state)
                           except Exception as e:
                               error_msg = f"⚠️ 포지션 저장 오류 - {stock['name']}({stock['code']}): {str(e)}"
                               logger.error(error_msg)
                               discord_alert.SendMessage(error_msg)

                       except Exception as e:
                           error_msg = f"매수 주문 중 에러 발생: {str(e)}"
                           logger.error(error_msg)
                           discord_alert.SendMessage(f"⚠️ {stock['name']}({stock['code']}) {error_msg}")

           time.sleep(30)  # 30초 간격으로 체크
           
       except Exception as e:
           msg = f"⚠️ 에러 발생!\n{str(e)}"
           logger.error(msg)
           discord_alert.SendMessage(msg)
           time.sleep(30)

if __name__ == "__main__":
   main()