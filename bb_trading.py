#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
타겟 종목 매매봇 (Target Stock Trading Bot) - Config 클래스 적용 완전 개선 버전
bb_trading.py의 방식을 참고하여 trend_trading.py의 기술적 분석을 적용
1. 미리 설정된 타겟 종목들에 대해서만 매매 진행
2. 종목별 개별 매매 파라미터 적용
3. trend_trading.py의 고도화된 기술적 분석 활용
4. bb_trading.py의 체계적인 리스크 관리 적용
5. Config 클래스로 모든 설정 통합 관리
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
import concurrent.futures
import threading
from typing import List, Dict, Tuple, Optional, Union

# KIS API 함수 임포트
import KIS_Common as Common
import KIS_API_Helper_KR as KisKR
import discord_alert

# trend_trading.py에서 기술적 분석 클래스들 임포트
from trend_trading import TechnicalIndicators, AdaptiveMarketStrategy, TrendFilter

import requests
from bs4 import BeautifulSoup

################################### 설정 클래스 ##################################

class TradingConfig:
    """거래 설정 관리 클래스"""
    
    def __init__(self, config_path: str = "target_stock_config.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """설정 파일 로드"""
        self.config = self._load_config_file(self.config_path)
        if hasattr(self, '_logger_initialized'):
            logger.info("거래 설정 로드 완료")
            logger.info(f"예산 비율: {self.trade_budget_ratio*100}%, 최대 보유: {self.max_positions}개")
    
    def save_config(self):
        """설정 파일 저장"""
        self._save_config_file(self.config, self.config_path)
    
    def _load_config_file(self, config_path: str) -> Dict[str, any]:
        """설정 파일 로드 (내부 함수)"""
        default_config = {
            "target_stocks": {},
            
            # 전략 설정
            "trade_budget_ratio": 0.90,
            "max_positions": 8,
            "min_stock_price": 3000,
            "max_stock_price": 200000,
            
            # 손익 관리 설정
            "stop_loss_ratio": -0.025,
            "take_profit_ratio": 0.055,
            "trailing_stop_ratio": 0.018,
            "max_daily_loss": -0.04,
            "max_daily_profit": 0.06,
            
            # 기술적 분석 설정
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,
            
            # 기타 설정
            "last_sector_update": "",
            "bot_name": "TargetStockBot",
            "use_discord_alert": True,
            "check_interval_minutes": 30
        }
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 기본 설정과 로드된 설정 병합
            def merge_config(default, loaded):
                result = default.copy()
                for key, value in loaded.items():
                    if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                        result[key] = merge_config(result[key], value)
                    else:
                        result[key] = value
                return result
            
            merged_config = merge_config(default_config, loaded_config)
            if hasattr(self, '_logger_initialized'):
                logger.info(f"설정 파일 로드 완료: {config_path}")
            return merged_config
        
        except FileNotFoundError:
            if hasattr(self, '_logger_initialized'):
                logger.warning(f"설정 파일 {config_path}을 찾을 수 없습니다. 기본값을 사용합니다.")
            return default_config
        
        except json.JSONDecodeError:
            if hasattr(self, '_logger_initialized'):
                logger.error(f"설정 파일 {config_path}의 형식이 올바르지 않습니다. 기본값을 사용합니다.")
            return default_config
        
        except Exception as e:
            if hasattr(self, '_logger_initialized'):
                logger.exception(f"설정 파일 로드 중 오류: {str(e)}")
            return default_config
    
    def _save_config_file(self, config: dict, config_path: str) -> None:
        """설정 파일 저장 (내부 함수)"""
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            if hasattr(self, '_logger_initialized'):
                logger.info(f"설정 파일 저장 완료: {config_path}")
        except Exception as e:
            if hasattr(self, '_logger_initialized'):
                logger.exception(f"설정 파일 저장 중 오류: {str(e)}")
    
    # =========================== 전략 설정 ===========================
    @property
    def trade_budget_ratio(self):
        """거래 예산 비율"""
        return self.config.get("trade_budget_ratio", 0.90)
    
    @property
    def max_positions(self):
        """최대 보유 종목 수"""
        return self.config.get("max_positions", 8)
    
    @property
    def min_stock_price(self):
        """최소 주가"""
        return self.config.get("min_stock_price", 3000)
    
    @property
    def max_stock_price(self):
        """최대 주가"""
        return self.config.get("max_stock_price", 200000)
    
    # =========================== 손익 관리 ===========================
    @property
    def stop_loss_ratio(self):
        """손절 비율"""
        return self.config.get("stop_loss_ratio", -0.025)
    
    @property
    def take_profit_ratio(self):
        """익절 비율"""
        return self.config.get("take_profit_ratio", 0.055)
    
    @property
    def trailing_stop_ratio(self):
        """트레일링 스탑 비율"""
        return self.config.get("trailing_stop_ratio", 0.018)
    
    @property
    def max_daily_loss(self):
        """일일 최대 손실 한도"""
        return self.config.get("max_daily_loss", -0.04)
    
    @property
    def max_daily_profit(self):
        """일일 최대 수익 한도"""
        return self.config.get("max_daily_profit", 0.06)
    
    # =========================== 기술적 분석 ===========================
    @property
    def rsi_period(self):
        """RSI 기간"""
        return self.config.get("rsi_period", 14)
    
    @property
    def rsi_oversold(self):
        """RSI 과매도 기준"""
        return self.config.get("rsi_oversold", 30)
    
    @property
    def rsi_overbought(self):
        """RSI 과매수 기준"""
        return self.config.get("rsi_overbought", 70)
    
    @property
    def macd_fast(self):
        """MACD 빠른 기간"""
        return self.config.get("macd_fast", 12)
    
    @property
    def macd_slow(self):
        """MACD 느린 기간"""
        return self.config.get("macd_slow", 26)
    
    @property
    def macd_signal(self):
        """MACD 시그널 기간"""
        return self.config.get("macd_signal", 9)
    
    @property
    def bb_period(self):
        """볼린저밴드 기간"""
        return self.config.get("bb_period", 20)
    
    @property
    def bb_std(self):
        """볼린저밴드 표준편차"""
        return self.config.get("bb_std", 2.0)
    
    # =========================== 타겟 종목 관리 ===========================
    @property
    def target_stocks(self):
        """타겟 종목 딕셔너리"""
        return self.config.get("target_stocks", {})
    
    def get_stock_config(self, stock_code: str):
        """특정 종목의 설정 반환"""
        return self.target_stocks.get(stock_code, {})
    
    def update_target_stocks(self, target_stocks: dict):
        """타겟 종목 업데이트"""
        self.config["target_stocks"] = target_stocks
        self.save_config()
    
    # =========================== 기타 설정 ===========================
    @property
    def bot_name(self):
        """봇 이름"""
        return self.config.get("bot_name", "TargetStockBot")
    
    @property
    def last_sector_update(self):
        """마지막 섹터 업데이트 날짜"""
        return self.config.get("last_sector_update", "")
    
    def update_last_sector_update(self, date_str: str):
        """마지막 섹터 업데이트 날짜 갱신"""
        self.config["last_sector_update"] = date_str
        self.save_config()
    
    def update_setting(self, key: str, value):
        """설정 값 업데이트"""
        self.config[key] = value
        self.save_config()
        if hasattr(self, '_logger_initialized'):
            logger.info(f"설정 업데이트: {key} = {value}")
    
    def reload_config(self):
        """설정 파일 다시 로드"""
        self.load_config()

################################### 로깅 처리 ##################################

log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

def log_namer(default_name):
    """로그 파일 이름 생성 함수"""
    base_filename, ext, date = default_name.split(".")
    return f"{base_filename}.{date}.{ext}"

# 로거 설정
logger = logging.getLogger('TargetStockTrader')
logger.setLevel(logging.INFO)

if logger.handlers:
    logger.handlers.clear()

log_file = os.path.join(log_directory, 'target_stock_trading.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
file_handler.suffix = "%Y%m%d"
file_handler.namer = log_namer

console_handler = logging.StreamHandler()

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

KisKR.set_logger(logger)
Common.set_logger(logger)

# =========================== 전역 설정 인스턴스 ===========================
trading_config = None

def initialize_config(config_path: str = "target_stock_config.json"):
    """설정 초기화"""
    global trading_config
    trading_config = TradingConfig(config_path)
    trading_config._logger_initialized = True  # 로거 초기화 완료 표시
    trading_config.load_config()  # 로거 초기화 후 다시 로드하여 로그 출력
    return trading_config

def get_bot_name():
    """봇 이름 반환"""
    if trading_config:
        return Common.GetNowDist() + "_" + trading_config.bot_name
    else:
        return Common.GetNowDist() + "_TargetStockBot"

################################### 유틸리티 함수 ##################################

def get_sector_info(stock_code):
    """네이버 금융을 통한 섹터 정보 조회"""
    try:
        logger.info(f"네이버 금융 조회 시작 (종목코드: {stock_code})...")
        
        # 네이버 금융 종목 페이지
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            response.encoding = 'euc-kr'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 업종 정보 찾기
            industry_element = soup.select_one('#content > div.section.trade_compare > h4 > em > a')
            if industry_element:
                sector = industry_element.get_text(strip=True)
                logger.info(f"네이버 금융에서 업종 정보를 찾았습니다: {sector}")
                
                return {
                    'sector': sector,
                    'industry': sector
                }
            else:
                logger.info("업종 정보를 찾을 수 없습니다.")
        else:
            logger.info(f"네이버 금융 접속 실패. 상태 코드: {response.status_code}")
            
        return {
            'sector': 'Unknown',
            'industry': 'Unknown'
        }
        
    except Exception as e:
        logger.info(f"섹터 정보 조회 중 에러: {str(e)}")
        return {
            'sector': 'Unknown',
            'industry': 'Unknown'
        }

def _update_stock_info(target_stocks):
    """종목별 이름과 섹터 정보 자동 업데이트"""
    try:
        updated_count = 0
        
        for stock_code, stock_info in target_stocks.items():
            try:
                # 1. 종목명 조회 (KIS API)
                if "name" not in stock_info or not stock_info.get("name"):
                    stock_status = KisKR.GetCurrentStatus(stock_code)
                    if stock_status and isinstance(stock_status, dict):
                        stock_name = stock_status.get("StockName", f"종목{stock_code}")
                        target_stocks[stock_code]["name"] = stock_name
                        logger.info(f"종목명 업데이트: {stock_code} -> {stock_name}")
                
                # 2. 섹터 정보 조회 (네이버 금융)
                if stock_info.get("sector") == "Unknown" or not stock_info.get("sector"):
                    sector_info = get_sector_info(stock_code)
                    
                    if sector_info['sector'] != 'Unknown':
                        target_stocks[stock_code]["sector"] = sector_info['sector']
                        updated_count += 1
                        logger.info(f"섹터 정보 업데이트: {stock_code}({target_stocks[stock_code]['name']}) -> {sector_info['sector']}")
                    
                    # 연속 요청 방지
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.warning(f"종목 {stock_code} 정보 업데이트 중 오류: {str(e)}")
                # 기본값 설정
                if "name" not in target_stocks[stock_code]:
                    target_stocks[stock_code]["name"] = f"종목{stock_code}"
                if "sector" not in target_stocks[stock_code]:
                    target_stocks[stock_code]["sector"] = "Unknown"
        
        if updated_count > 0:
            logger.info(f"{updated_count}개 종목의 정보를 업데이트했습니다.")
        
        return target_stocks
        
    except Exception as e:
        logger.exception(f"종목 정보 업데이트 중 오류: {str(e)}")
        return target_stocks

def calculate_trading_fee(price, quantity, is_buy=True):
    """거래 수수료 및 세금 계산 (개선된 버전)"""
    try:
        if price <= 0 or quantity <= 0:
            return 0
            
        trade_amount = price * quantity
        
        # 증권사 수수료 (통상 0.015%, 최소 1000원)
        commission_rate = 0.00015  # 0.015%
        commission = max(trade_amount * commission_rate, 1000)  # 최소 1000원
        
        total_fee = commission
        
        if not is_buy:  # 매도시에만 추가 세금
            # 증권거래세 (0.23%)
            securities_tax = trade_amount * 0.0023
            
            # 농어촌특별세 (증권거래세의 20%, 즉 거래금액의 0.046%)
            special_tax = securities_tax * 0.2
            
            total_fee += securities_tax + special_tax
        
        return round(total_fee, 0)  # 원 단위로 반올림
        
    except Exception as e:
        logger.error(f"거래 수수료 계산 중 에러: {str(e)}")
        return 0

def check_trading_time():
    """장중 거래 가능한 시간대인지 체크 (개선된 버전)"""
    try:
        if KisKR.IsTodayOpenCheck() == 'N':
            logger.info("휴장일 입니다.")
            return False, False

        market_status = KisKR.MarketStatus()
        if market_status is None or not isinstance(market_status, dict):
            logger.info("장 상태 확인 실패")
            return False, False
            
        status_code = market_status.get('Status', '')
        current_time = datetime.datetime.now().time()
        
        # 동시호가: 8:30-9:00
        is_market_open = (status_code == '0' and 
                         current_time >= datetime.time(8, 30) and 
                         current_time < datetime.time(9, 0))
        
        # 정규장: 9:00-15:30
        is_trading_time = (status_code == '2' and
                          current_time >= datetime.time(9, 0) and
                          current_time < datetime.time(15, 30))
        
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

################################### 기술적 분석 함수 ##################################

def get_stock_data(stock_code):
    """종목 데이터 조회 및 기술적 분석 (Config 적용)"""
    try:
        # 일봉 데이터 조회
        df = Common.GetOhlcv("KR", stock_code, 60)
        
        if df is None or len(df) < 30:
            logger.error(f"{stock_code}: 데이터 부족")
            return None
        
        # 현재가 조회
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price or current_price <= 0:
            logger.error(f"{stock_code}: 현재가 조회 실패")
            return None
        
        # Config에서 기술적 지표 설정값 사용
        df['RSI'] = TechnicalIndicators.calculate_rsi(df, trading_config.rsi_period)
        
        macd_data = TechnicalIndicators.calculate_macd(
            df, trading_config.macd_fast, trading_config.macd_slow, trading_config.macd_signal
        )
        df[['MACD', 'Signal', 'Histogram']] = macd_data
        
        bb_data = TechnicalIndicators.calculate_bollinger_bands(
            df, trading_config.bb_period, trading_config.bb_std
        )
        df[['MiddleBand', 'UpperBand', 'LowerBand']] = bb_data
        
        # 이동평균선 계산
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        
        # ATR 계산
        df['ATR'] = TechnicalIndicators.calculate_atr(df)
        
        # 지지/저항선 분석
        sr_data = TechnicalIndicators.detect_support_resistance(df)
        
        return {
            'stock_code': stock_code,
            'current_price': current_price,
            'ohlcv_data': df,
            'rsi': df['RSI'].iloc[-1] if not pd.isna(df['RSI'].iloc[-1]) else 50,
            'macd': df['MACD'].iloc[-1] if not pd.isna(df['MACD'].iloc[-1]) else 0,
            'macd_signal': df['Signal'].iloc[-1] if not pd.isna(df['Signal'].iloc[-1]) else 0,
            'macd_histogram': df['Histogram'].iloc[-1] if not pd.isna(df['Histogram'].iloc[-1]) else 0,
            'bb_upper': df['UpperBand'].iloc[-1] if not pd.isna(df['UpperBand'].iloc[-1]) else 0,
            'bb_middle': df['MiddleBand'].iloc[-1] if not pd.isna(df['MiddleBand'].iloc[-1]) else 0,
            'bb_lower': df['LowerBand'].iloc[-1] if not pd.isna(df['LowerBand'].iloc[-1]) else 0,
            'ma5': df['MA5'].iloc[-1] if not pd.isna(df['MA5'].iloc[-1]) else 0,
            'ma20': df['MA20'].iloc[-1] if not pd.isna(df['MA20'].iloc[-1]) else 0,
            'ma60': df['MA60'].iloc[-1] if not pd.isna(df['MA60'].iloc[-1]) else 0,
            'support': sr_data.get("support", 0),
            'resistance': sr_data.get("resistance", 0),
            'atr': df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0
        }
        
    except Exception as e:
        logger.error(f"종목 데이터 조회 중 에러: {str(e)}")
        return None

################################### 매매 신호 분석 ##################################

def analyze_buy_signal(stock_data, target_config):
    """매수 신호 분석 (Config 적용)"""
    try:
        signals = []
        score = 0
        
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        rsi = stock_data['rsi']
        
        # 종목별 개별 설정 적용 (없으면 전역 설정 사용)
        rsi_oversold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
        min_score = target_config.get('min_score', 70)
        
        # 1. RSI 과매도 신호 (25점)
        if rsi <= rsi_oversold:
            score += 25
            signals.append(f"RSI 과매도 {rsi:.1f} (+25)")
        elif rsi <= rsi_oversold + 5:
            score += 15
            signals.append(f"RSI 매수권 진입 {rsi:.1f} (+15)")
        
        # 2. 볼린저밴드 신호 (20점)
        bb_position = "middle"
        if current_price <= stock_data['bb_lower']:
            score += 20
            signals.append("볼린저밴드 하단 터치 (+20)")
            bb_position = "lower"
        elif current_price <= stock_data['bb_middle']:
            score += 10
            signals.append("볼린저밴드 중간선 하단 (+10)")
            bb_position = "below_middle"
        
        # 3. MACD 신호 (20점)
        macd = stock_data['macd']
        macd_signal = stock_data['macd_signal']
        macd_histogram = stock_data['macd_histogram']
        
        if macd > macd_signal and macd_histogram > 0:
            score += 20
            signals.append("MACD 골든크로스 + 상승 (+20)")
        elif macd > macd_signal:
            score += 15
            signals.append("MACD 골든크로스 (+15)")
        elif macd_histogram > 0:
            score += 10
            signals.append("MACD 히스토그램 상승 (+10)")
        
        # 4. 이동평균선 신호 (15점)
        ma5 = stock_data['ma5']
        ma20 = stock_data['ma20']
        ma60 = stock_data['ma60']
        
        if ma5 > ma20 > ma60:  # 정배열
            score += 15
            signals.append("이동평균선 정배열 (+15)")
        elif ma5 > ma20:  # 단기 상승
            score += 10
            signals.append("단기 이평선 돌파 (+10)")
        
        # 5. 지지선 근처 신호 (10점)
        support = stock_data['support']
        if support > 0 and current_price <= support * 1.02:  # 지지선 2% 이내
            score += 10
            signals.append("지지선 근처 (+10)")
        
        # 6. 거래량 분석
        df = stock_data['ohlcv_data']
        if len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
            
            if volume_ratio >= 1.5:
                score += 10
                signals.append(f"거래량 급증 {volume_ratio:.1f}배 (+10)")
            elif volume_ratio >= 1.2:
                score += 5
                signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+5)")
        
        # 매수 신호 판정
        is_buy_signal = score >= min_score
        
        return {
            'is_buy_signal': is_buy_signal,
            'score': score,
            'min_score': min_score,
            'signals': signals,
            'bb_position': bb_position,
            'analysis': {
                'rsi': rsi,
                'rsi_threshold': rsi_oversold,
                'macd_cross': macd > macd_signal,
                'price_vs_bb_lower': (current_price / stock_data['bb_lower'] - 1) * 100 if stock_data['bb_lower'] > 0 else 0
            }
        }
        
    except Exception as e:
        logger.error(f"매수 신호 분석 중 에러: {str(e)}")
        return {'is_buy_signal': False, 'score': 0, 'signals': []}

def analyze_sell_signal(stock_data, position, target_config):
    """매도 신호 분석 (Config 적용)"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position['entry_price']
        
        # 수익률 계산
        profit_rate = (current_price - entry_price) / entry_price
        
        # 종목별 개별 설정 적용 (없으면 전역 설정 사용)
        profit_target = target_config.get('profit_target', trading_config.take_profit_ratio)
        stop_loss = target_config.get('stop_loss', trading_config.stop_loss_ratio)
        trailing_stop = target_config.get('trailing_stop', trading_config.trailing_stop_ratio)
        rsi_overbought = target_config.get('rsi_overbought', trading_config.rsi_overbought)
        
        # 1. 손익 관리 신호 (최우선)
        if profit_rate <= stop_loss:
            return {
                'is_sell_signal': True,
                'sell_type': 'stop_loss',
                'reason': f"손절 실행 {profit_rate*100:.1f}%",
                'urgent': True
            }
        
        if profit_rate >= profit_target:
            return {
                'is_sell_signal': True,
                'sell_type': 'take_profit',
                'reason': f"익절 실행 {profit_rate*100:.1f}%",
                'urgent': True
            }
        
        # 2. 트레일링 스탑 확인
        if 'high_price' in position:
            trailing_loss = (position['high_price'] - current_price) / position['high_price']
            if trailing_loss >= trailing_stop:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop',
                    'reason': f"트레일링 스탑 {trailing_loss*100:.1f}%",
                    'urgent': True
                }
        
        # 3. 기술적 분석 기반 매도 신호
        signals = []
        score = 0
        
        # RSI 과매수
        rsi = stock_data['rsi']
        if rsi >= rsi_overbought:
            score += 30
            signals.append(f"RSI 과매수 {rsi:.1f}")
        
        # 볼린저밴드 상단
        if current_price >= stock_data['bb_upper']:
            score += 25
            signals.append("볼린저밴드 상단 터치")
        
        # MACD 하향 전환
        macd = stock_data['macd']
        macd_signal = stock_data['macd_signal']
        if macd < macd_signal:
            score += 20
            signals.append("MACD 하향 전환")
        
        # 저항선 근처
        resistance = stock_data['resistance']
        if resistance > 0 and current_price >= resistance * 0.98:
            score += 15
            signals.append("저항선 근처")
        
        # 이동평균선 데드크로스
        if TechnicalIndicators.is_death_cross(stock_data['ohlcv_data']):
            score += 20
            signals.append("데드크로스 발생")
        
        # 기술적 매도 신호 판정
        if profit_rate > 0.01:  # 수익 상태에서는 낮은 점수로도 매도
            is_sell_signal = score >= 70
        else:  # 손실 상태에서는 더 높은 점수 요구
            is_sell_signal = score >= 85
        
        if is_sell_signal:
            return {
                'is_sell_signal': True,
                'sell_type': 'technical',
                'reason': f"기술적 매도신호 (점수: {score}): {', '.join(signals)}",
                'urgent': False,
                'profit_rate': profit_rate
            }
        
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"보유 지속 (수익률: {profit_rate*100:.1f}%, 기술점수: {score})",
            'urgent': False,
            'profit_rate': profit_rate
        }
        
    except Exception as e:
        logger.error(f"매도 신호 분석 중 에러: {str(e)}")
        return {'is_sell_signal': False, 'sell_type': None, 'reason': '분석 오류'}

################################### 상태 관리 ##################################

def load_trading_state():
    """트레이딩 상태 로드"""
    try:
        bot_name = get_bot_name()
        with open(f"TargetStockBot_{bot_name}.json", 'r') as f:
            return json.load(f)
    except:
        return {
            'positions': {},
            'daily_stats': {
                'date': '',
                'total_profit': 0,
                'total_trades': 0,
                'winning_trades': 0,
                'start_balance': 0
            }
        }

def save_trading_state(state):
    """트레이딩 상태 저장"""
    bot_name = get_bot_name()
    with open(f"TargetStockBot_{bot_name}.json", 'w') as f:
        json.dump(state, f, indent=2)

################################### 매매 실행 ##################################

def calculate_position_size(target_config, available_budget, stock_price):
    """포지션 크기 계산 (개선된 버전 - Config 적용)"""
    try:
        # 1. 기본 검증
        if stock_price <= 0:
            logger.warning("주가가 0 이하입니다.")
            return 0
            
        if available_budget <= 0:
            logger.warning("사용 가능한 예산이 없습니다.")
            return 0
        
        # 2. 계좌 잔고 재확인 (실시간)
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return 0
            
        actual_balance = float(balance.get('RemainMoney', 0))
        logger.info(f"실제 잔고: {actual_balance:,.0f}원, 사용가능 예산: {available_budget:,.0f}원")
        
        # 3. 실제 사용 가능한 예산 조정
        usable_budget = min(available_budget, actual_balance)
        
        if usable_budget <= 0:
            logger.warning("실제 사용 가능한 예산이 없습니다.")
            return 0
        
        # 4. 종목별 할당 비율 적용
        allocation_ratio = target_config.get('allocation_ratio', 0.125)  # 기본 12.5%
        
        # 할당 비율 검증 (0.01% ~ 50% 범위)
        allocation_ratio = max(0.0001, min(0.5, allocation_ratio))
        
        allocated_budget = usable_budget * allocation_ratio
        logger.info(f"할당 예산: {allocated_budget:,.0f}원 (비율: {allocation_ratio*100:.1f}%)")
        
        # 5. 최소 주문 금액 체크
        min_order_amount = target_config.get('min_order_amount', 10000)  # 기본 1만원
        if allocated_budget < min_order_amount:
            logger.info(f"할당 예산이 최소 주문 금액({min_order_amount:,}원)보다 작습니다.")
            return 0
        
        # 6. 최대 주문 금액 제한 (리스크 관리)
        max_order_amount = target_config.get('max_order_amount', usable_budget * 0.2)  # 기본 20% 제한
        allocated_budget = min(allocated_budget, max_order_amount)
        
        # 7. 기본 수량 계산
        base_quantity = int(allocated_budget / stock_price)
        logger.info(f"기본 계산 수량: {base_quantity}주")
        
        if base_quantity <= 0:
            logger.info("계산된 수량이 0 이하입니다.")
            return 0
        
        # 8. 수수료 고려한 실제 필요 금액 계산
        estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
        total_needed = (stock_price * base_quantity) + estimated_fee
        
        # 9. 수수료 포함해서 예산 초과하면 수량 조정
        while total_needed > allocated_budget and base_quantity > 0:
            base_quantity -= 1
            if base_quantity > 0:
                estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
                total_needed = (stock_price * base_quantity) + estimated_fee
            else:
                break
        
        # 10. 최종 검증
        if base_quantity <= 0:
            logger.info("수수료 고려 후 매수 가능한 수량이 없습니다.")
            return 0
        
        # 11. 종목별 최소/최대 수량 제한 적용
        min_quantity = target_config.get('min_quantity', 1)
        max_quantity = target_config.get('max_quantity', float('inf'))
        
        final_quantity = max(min_quantity, min(base_quantity, max_quantity))
        
        # 12. 최종 금액 검증
        final_amount = stock_price * final_quantity
        final_fee = calculate_trading_fee(stock_price, final_quantity, True)
        final_total = final_amount + final_fee
        
        if final_total > allocated_budget:
            logger.warning(f"최종 필요금액({final_total:,.0f}원)이 할당예산({allocated_budget:,.0f}원)을 초과합니다.")
            return 0
        
        # 13. 로깅
        logger.info(f"최종 매수 수량: {final_quantity}주")
        logger.info(f"필요 금액: {final_amount:,.0f}원")
        logger.info(f"예상 수수료: {final_fee:,.0f}원")
        logger.info(f"총 필요 금액: {final_total:,.0f}원")
        logger.info(f"남은 할당 예산: {allocated_budget - final_total:,.0f}원")
        
        return final_quantity
        
    except Exception as e:
        logger.error(f"포지션 크기 계산 중 에러: {str(e)}")
        return 0

def execute_buy_order(stock_code, target_config, quantity, price):
    """매수 주문 실행"""
    try:
        stock_name = target_config.get('name', stock_code)
        logger.info(f"{stock_name}({stock_code}) 매수 주문: {quantity}주 @ {price:,.0f}원")
        
        # 지정가 매수 주문
        order_result = KisKR.MakeBuyLimitOrder(stock_code, quantity, int(price))
        
        if not order_result or isinstance(order_result, str):
            logger.error(f"매수 주문 실패: {order_result}")
            return None, None
        
        # 체결 확인 (최대 60초 대기)
        start_time = time.time()
        while time.time() - start_time < 60:
            my_stocks = KisKR.GetMyStockList()
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    executed_amount = int(stock.get('StockAmt', 0))
                    if executed_amount > 0:
                        avg_price = float(stock.get('AvrPrice', price))
                        logger.info(f"매수 체결 확인: {executed_amount}주 @ {avg_price:,.0f}원")
                        return avg_price, executed_amount
            time.sleep(3)
        
        logger.warning(f"매수 체결 확인 실패: {stock_code}")
        return None, None
        
    except Exception as e:
        logger.error(f"매수 주문 실행 중 에러: {str(e)}")
        return None, None

def execute_sell_order(stock_code, target_config, quantity):
    """매도 주문 실행"""
    try:
        stock_name = target_config.get('name', stock_code)
        logger.info(f"{stock_name}({stock_code}) 매도 주문: {quantity}주")
        
        # 시장가 매도 주문
        order_result = KisKR.MakeSellMarketOrder(stock_code, quantity)
        
        if not order_result or isinstance(order_result, str):
            logger.error(f"매도 주문 실패: {order_result}")
            return None, None
        
        # 체결 확인 (최대 60초 대기)
        start_time = time.time()
        initial_amount = quantity
        
        while time.time() - start_time < 60:
            my_stocks = KisKR.GetMyStockList()
            current_amount = 0
            
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    current_amount = int(stock.get('StockAmt', 0))
                    break
            
            if current_amount < initial_amount:
                executed_amount = initial_amount - current_amount
                current_price = KisKR.GetCurrentPrice(stock_code)
                logger.info(f"매도 체결 확인: {executed_amount}주 @ {current_price:,.0f}원")
                return current_price, executed_amount
            
            time.sleep(3)
        
        logger.warning(f"매도 체결 확인 실패: {stock_code}")
        return None, None
        
    except Exception as e:
        logger.error(f"매도 주문 실행 중 에러: {str(e)}")
        return None, None

################################### 보고서 생성 ##################################

def send_daily_report(trading_state):
    """일일 거래 성과 보고서"""
    try:
        balance = KisKR.GetBalance()
        my_stocks = KisKR.GetMyStockList()
        daily_stats = trading_state['daily_stats']
        
        total_money = float(balance.get('TotalMoney', 0))
        stock_revenue = float(balance.get('StockRevenue', 0))
        
        msg = "📊 타겟 종목 매매봇 일일 성과 보고서 📊\n"
        msg += f"========== {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
        msg += f"[전체 계좌 현황]\n"
        msg += f"총 평가금액: {total_money:,.0f}원\n"
        msg += f"누적 손익: {stock_revenue:,.0f}원\n"
        
        if my_stocks:
            msg += "\n[보유 종목 현황]\n"
            for stock in my_stocks:
                stock_code = stock['StockCode']
                if stock_code in trading_state['positions'] and stock_code in trading_config.target_stocks:
                    target_config = trading_config.target_stocks[stock_code]
                    msg += f"- {target_config.get('name', stock_code)}({stock_code}): "
                    msg += f"{stock['StockAmt']}주, {float(stock['StockRevenueMoney']):,.0f}원 "
                    msg += f"({stock['StockRevenueRate']}%)\n"
        else:
            msg += "\n현재 보유 종목 없음\n"
        
        if daily_stats['total_trades'] > 0:
            winning_rate = (daily_stats['winning_trades'] / daily_stats['total_trades']) * 100
            msg += f"\n[봇 거래 성과]\n"
            msg += f"일일 실현손익: {daily_stats['total_profit']:,.0f}원\n"
            msg += f"총 거래: {daily_stats['total_trades']}회 (승률: {winning_rate:.1f}%)"
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
    except Exception as e:
        logger.error(f"일일 보고서 생성 중 에러: {str(e)}")

def send_target_stock_status():
    """타겟 종목 현황 보고서"""
    try:
        msg = "📋 타겟 종목 현황 📋\n"
        msg += f"========== {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
        
        for stock_code, config in trading_config.target_stocks.items():
            if not config.get('enabled', True):
                continue
                
            current_price = KisKR.GetCurrentPrice(stock_code)
            if current_price:
                stock_data = get_stock_data(stock_code)
                if stock_data:
                    buy_analysis = analyze_buy_signal(stock_data, config)
                    
                    msg += f"\n[{config.get('name', stock_code)}({stock_code})]\n"
                    msg += f"현재가: {current_price:,}원\n"
                    msg += f"RSI: {stock_data['rsi']:.1f} (기준: {config.get('rsi_oversold', trading_config.rsi_oversold)})\n"
                    msg += f"매수점수: {buy_analysis['score']}/{config.get('min_score', 70)}\n"
                    
                    if buy_analysis['is_buy_signal']:
                        msg += "✅ 매수 신호 발생!\n"
                    else:
                        msg += "⏳ 매수 대기 중\n"
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
    except Exception as e:
        logger.error(f"타겟 종목 현황 보고서 생성 중 에러: {str(e)}")

################################### 메인 로직 ##################################

def scan_target_stocks(trading_state):
    """타겟 종목 매수 기회 스캔 (Config 적용)"""
    try:
        buy_opportunities = []
        current_positions = len(trading_state['positions'])
        
        # Config에서 최대 보유 종목 수 확인
        if current_positions >= trading_config.max_positions:
            logger.info(f"최대 보유 종목 수({trading_config.max_positions}개) 도달")
            return []
        
        logger.info(f"타겟 종목 매수 기회 스캔 시작: {len(trading_config.target_stocks)}개 종목 분석")
        
        for stock_code, target_config in trading_config.target_stocks.items():
            try:
                # 비활성화된 종목 제외
                if not target_config.get('enabled', True):
                    continue
                    
                # 이미 보유 중인 종목은 제외
                if stock_code in trading_state['positions']:
                    continue
                
                # Config에서 가격 필터링
                current_price = KisKR.GetCurrentPrice(stock_code)
                if not current_price or current_price < trading_config.min_stock_price or current_price > trading_config.max_stock_price:
                    continue
                
                # 종목 데이터 분석
                stock_data = get_stock_data(stock_code)
                if not stock_data:
                    continue
                
                # 매수 신호 분석 (종목별 설정 적용)
                buy_analysis = analyze_buy_signal(stock_data, target_config)
                
                if buy_analysis['is_buy_signal']:
                    buy_opportunities.append({
                        'stock_code': stock_code,
                        'stock_name': target_config.get('name', stock_code),
                        'price': current_price,
                        'score': buy_analysis['score'],
                        'min_score': buy_analysis['min_score'],
                        'signals': buy_analysis['signals'],
                        'analysis': buy_analysis['analysis'],
                        'target_config': target_config
                    })
                    
                    logger.info(f"✅ 매수 기회 발견: {target_config.get('name', stock_code)}({stock_code})")
                    logger.info(f"   점수: {buy_analysis['score']}/{buy_analysis['min_score']}점")
                    for signal in buy_analysis['signals']:
                        logger.info(f"   - {signal}")
            
            except Exception as e:
                logger.error(f"종목 분석 중 에러 ({stock_code}): {str(e)}")
                continue
        
        # 점수 순으로 정렬
        buy_opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"매수 기회 스캔 완료: {len(buy_opportunities)}개 발견")
        return buy_opportunities
        
    except Exception as e:
        logger.error(f"매수 기회 스캔 중 에러: {str(e)}")
        return []

def update_trailing_stop(position, current_price, target_config):
    """트레일링 스탑 업데이트 (Config 적용)"""
    try:
        trailing_stop_ratio = target_config.get('trailing_stop', trading_config.trailing_stop_ratio)
        
        # 고점 업데이트
        if 'high_price' not in position or current_price > position['high_price']:
            position['high_price'] = current_price
            position['trailing_stop'] = current_price * (1 - trailing_stop_ratio)
            logger.info(f"트레일링 스탑 업데이트: 고점 {current_price:,.0f}원, 스탑 {position['trailing_stop']:,.0f}원")
        
        return position
        
    except Exception as e:
        logger.error(f"트레일링 스탑 업데이트 중 에러: {str(e)}")
        return position

def process_positions(trading_state):
    """보유 포지션 관리 (Config 적용)"""
    try:
        my_stocks = KisKR.GetMyStockList()
        positions_to_remove = []
        
        for stock_code, position in trading_state['positions'].items():
            try:
                # 타겟 종목이 아닌 경우 스킵
                if stock_code not in trading_config.target_stocks:
                    continue
                
                # 실제 보유 여부 확인
                actual_holding = None
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        actual_holding = stock
                        break
                
                if not actual_holding:
                    logger.warning(f"{stock_code}: 포지션 정보는 있으나 실제 보유하지 않음")
                    positions_to_remove.append(stock_code)
                    continue
                
                target_config = trading_config.target_stocks[stock_code]
                current_amount = int(actual_holding.get('StockAmt', 0))
                
                if current_amount <= 0:
                    positions_to_remove.append(stock_code)
                    continue
                
                # 종목 데이터 조회
                stock_data = get_stock_data(stock_code)
                if not stock_data:
                    continue
                
                current_price = stock_data['current_price']
                
                # 트레일링 스탑 업데이트
                position = update_trailing_stop(position, current_price, target_config)
                trading_state['positions'][stock_code] = position
                
                # 매도 신호 분석
                sell_analysis = analyze_sell_signal(stock_data, position, target_config)
                
                if sell_analysis['is_sell_signal']:
                    logger.info(f"🔴 매도 신호 감지: {target_config.get('name', stock_code)}({stock_code})")
                    logger.info(f"   유형: {sell_analysis['sell_type']}")
                    logger.info(f"   이유: {sell_analysis['reason']}")
                    
                    # 매도 주문 실행
                    executed_price, executed_amount = execute_sell_order(
                        stock_code, target_config, current_amount
                    )
                    
                    if executed_price and executed_amount:
                        # 손익 계산
                        entry_price = position['entry_price']
                        buy_fee = position.get('buy_fee', 0)
                        sell_fee = calculate_trading_fee(executed_price, executed_amount, False)
                        
                        gross_profit = (executed_price - entry_price) * executed_amount
                        net_profit = gross_profit - buy_fee - sell_fee
                        profit_rate = (net_profit / (entry_price * executed_amount)) * 100
                        
                        # 일일 통계 업데이트
                        trading_state['daily_stats']['total_profit'] += net_profit
                        trading_state['daily_stats']['total_trades'] += 1
                        if net_profit > 0:
                            trading_state['daily_stats']['winning_trades'] += 1
                        
                        # 매도 완료 알림
                        msg = f"💰 매도 완료: {target_config.get('name', stock_code)}({stock_code})\n"
                        msg += f"매도가: {executed_price:,.0f}원\n"
                        msg += f"수량: {executed_amount}주\n"
                        msg += f"순손익: {net_profit:,.0f}원 ({profit_rate:.2f}%)\n"
                        msg += f"매도사유: {sell_analysis['reason']}"
                        
                        logger.info(msg)
                        discord_alert.SendMessage(msg)
                        
                        # 포지션 제거
                        positions_to_remove.append(stock_code)
                    else:
                        logger.error(f"매도 주문 실패: {target_config.get('name', stock_code)}({stock_code})")
                
            except Exception as e:
                logger.error(f"포지션 처리 중 에러 ({stock_code}): {str(e)}")
                continue
        
        # 제거할 포지션 정리
        for stock_code in positions_to_remove:
            if stock_code in trading_state['positions']:
                del trading_state['positions'][stock_code]
                logger.info(f"포지션 제거: {stock_code}")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"포지션 관리 중 에러: {str(e)}")
        return trading_state

def execute_buy_opportunities(buy_opportunities, trading_state):
    """매수 기회 실행 (Config 적용)"""
    try:
        if not buy_opportunities:
            return trading_state
        
        # 계좌 정보 조회
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return trading_state
        
        total_money = float(balance.get('TotalMoney', 0))
        # Config에서 예산 비율 사용
        available_budget = total_money * trading_config.trade_budget_ratio
        
        # Config에서 일일 손실/수익 한도 확인
        daily_stats = trading_state['daily_stats']
        if daily_stats['start_balance'] > 0:
            daily_profit_rate = daily_stats['total_profit'] / daily_stats['start_balance']
            
            if daily_profit_rate <= trading_config.max_daily_loss:
                logger.info(f"일일 손실 한도 도달: {daily_profit_rate*100:.1f}%")
                return trading_state
            
            if daily_profit_rate >= trading_config.max_daily_profit:
                logger.info(f"일일 수익 한도 도달: {daily_profit_rate*100:.1f}%")
                return trading_state
        
        current_positions = len(trading_state['positions'])
        max_new_positions = trading_config.max_positions - current_positions
        
        # 상위 종목들에 대해 매수 실행
        for i, opportunity in enumerate(buy_opportunities[:max_new_positions]):
            try:
                stock_code = opportunity['stock_code']
                stock_name = opportunity['stock_name']
                stock_price = opportunity['price']
                target_config = opportunity['target_config']
                
                # 포지션 크기 계산 (종목별 설정 적용)
                quantity = calculate_position_size(target_config, available_budget, stock_price)
                
                if quantity < 1:
                    logger.info(f"매수 수량 부족: {stock_name}({stock_code})")
                    continue
                
                logger.info(f"🔵 매수 시도: {stock_name}({stock_code})")
                logger.info(f"   수량: {quantity}주, 가격: {stock_price:,.0f}원")
                logger.info(f"   점수: {opportunity['score']}/{opportunity['min_score']}점")
                
                # 매수 주문 실행
                executed_price, executed_amount = execute_buy_order(
                    stock_code, target_config, quantity, stock_price
                )
                
                if executed_price and executed_amount:
                    # 매수 수수료 계산
                    buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                    
                    # 포지션 정보 저장 (종목별 설정 포함)
                    trading_state['positions'][stock_code] = {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'entry_price': executed_price,
                        'amount': executed_amount,
                        'buy_fee': buy_fee,
                        'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'high_price': executed_price,
                        'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', trading_config.trailing_stop_ratio)),
                        'target_config': target_config,
                        'buy_analysis': opportunity['analysis']
                    }
                    
                    # 매수 완료 알림
                    msg = f"✅ 매수 완료: {stock_name}({stock_code})\n"
                    msg += f"매수가: {executed_price:,.0f}원\n"
                    msg += f"수량: {executed_amount}주\n"
                    msg += f"투자금액: {executed_price * executed_amount:,.0f}원\n"
                    msg += f"수수료: {buy_fee:,.0f}원\n"
                    msg += f"목표수익률: {target_config.get('profit_target', trading_config.take_profit_ratio)*100:.1f}%\n"
                    msg += f"손절률: {target_config.get('stop_loss', trading_config.stop_loss_ratio)*100:.1f}%"
                    
                    logger.info(msg)
                    discord_alert.SendMessage(msg)
                else:
                    logger.error(f"매수 주문 실패: {stock_name}({stock_code})")
                
            except Exception as e:
                logger.error(f"매수 실행 중 에러: {str(e)}")
                continue
        
        return trading_state
        
    except Exception as e:
        logger.error(f"매수 기회 실행 중 에러: {str(e)}")
        return trading_state

def create_config_file(config_path: str = "target_stock_config.json") -> None:
    """기본 설정 파일 생성 (Config 클래스 사용)"""
    try:
        logger.info("기본 설정 파일 생성 시작...")
        
        # 기본 타겟 종목들 정의 (종목코드와 설정만)
        default_target_stocks = {
            "006400": {  # 삼성SDI
                "allocation_ratio": 0.12,
                "profit_target": 0.055,
                "stop_loss": -0.025,
                "trailing_stop": 0.02,
                "rsi_oversold": 28,
                "rsi_overbought": 72,
                "min_score": 70,
                "enabled": True
            },
            "028300": {  # HLB
                "allocation_ratio": 0.08,
                "profit_target": 0.04,
                "stop_loss": -0.02,
                "trailing_stop": 0.015,
                "rsi_oversold": 32,
                "rsi_overbought": 68,
                "min_score": 65,
                "enabled": True
            }
        }
        
        # 종목별 이름과 섹터 정보 자동 업데이트
        logger.info("기본 종목들의 이름 및 섹터 정보 조회 중...")
        updated_stocks = _update_stock_info(default_target_stocks)
        
        config = {
            "target_stocks": updated_stocks,
            
            # 전략 설정
            "trade_budget_ratio": 0.90,
            "max_positions": 8,
            "min_stock_price": 3000,
            "max_stock_price": 200000,
            
            # 손익 관리 설정
            "stop_loss_ratio": -0.025,
            "take_profit_ratio": 0.055,
            "trailing_stop_ratio": 0.018,
            "max_daily_loss": -0.04,
            "max_daily_profit": 0.06,
            
            # 기술적 분석 설정
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,
            
            # 기타 설정
            "last_sector_update": datetime.datetime.now().strftime('%Y%m%d'),
            "bot_name": "TargetStockBot",
            "use_discord_alert": True,
            "check_interval_minutes": 30
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"기본 설정 파일 생성 완료: {config_path}")
        logger.info(f"등록된 종목 수: {len(updated_stocks)}개")
        
        # 생성된 종목 정보 로깅
        for stock_code, stock_info in updated_stocks.items():
            stock_name = stock_info.get('name', stock_code)
            sector = stock_info.get('sector', 'Unknown')
            allocation = stock_info.get('allocation_ratio', 0) * 100
            logger.info(f"  - {stock_name}({stock_code}): "
                       f"섹터 {sector}, "
                       f"배분비율 {allocation:.1f}%")
        
    except Exception as e:
        logger.exception(f"설정 파일 생성 중 오류: {str(e)}")
        raise

def main():
    """메인 함수 (Config 적용)"""
    
    # 1. 설정 초기화 (가장 먼저!)
    config_path = "target_stock_config.json"
    
    # 설정 파일이 없으면 생성
    if not os.path.exists(config_path):
        create_config_file(config_path)
        logger.info(f"기본 설정 파일 생성 완료: {config_path}")
    
    # Config 클래스 초기화
    config = initialize_config(config_path)
    
    # 섹터 정보 업데이트 (날짜가 바뀌었거나 처음 실행시)
    today = datetime.datetime.now().strftime('%Y%m%d')
    
    if config.last_sector_update != today:
        logger.info("섹터 정보 자동 업데이트 시작...")
        updated_stocks = _update_stock_info(config.target_stocks)
        config.update_target_stocks(updated_stocks)
        config.update_last_sector_update(today)

    msg = "🎯 타겟 종목 매매봇 시작!"
    logger.info(msg)
    discord_alert.SendMessage(msg)
    
    # 타겟 종목 현황 출력 (Config 사용)
    enabled_count = sum(1 for stock_config in config.target_stocks.values() if stock_config.get('enabled', True))
    logger.info(f"활성화된 타겟 종목: {enabled_count}개")
    for stock_code, stock_config in config.target_stocks.items():
        if stock_config.get('enabled', True):
            logger.info(f"  - {stock_config.get('name', stock_code)}({stock_code}): "
                       f"목표수익률 {stock_config.get('profit_target', config.take_profit_ratio)*100:.1f}%, "
                       f"손절률 {stock_config.get('stop_loss', config.stop_loss_ratio)*100:.1f}%, "
                       f"배분비율 {stock_config.get('allocation_ratio', 0)*100:.1f}%")
    
    # 초기 상태
    daily_report_sent = False
    market_open_notified = False
    last_status_report = datetime.datetime.now()
    
    while True:
        try:
            now = datetime.datetime.now()
            today = now.strftime('%Y-%m-%d')
            
            # 거래 시간 체크
            is_trading_time, is_market_open = check_trading_time()
            
            # 트레이딩 상태 로드
            trading_state = load_trading_state()
            
            # 날짜가 바뀌면 일일 통계 초기화
            if trading_state['daily_stats']['date'] != today:
                balance = KisKR.GetBalance()
                start_balance = float(balance.get('TotalMoney', 0)) if balance else 0
                
                trading_state['daily_stats'] = {
                    'date': today,
                    'total_profit': 0,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'start_balance': start_balance
                }
                daily_report_sent = False
                market_open_notified = False
                save_trading_state(trading_state)
            
            # 장 시작 알림 (Config 사용)
            if is_market_open and not market_open_notified:
                balance = KisKR.GetBalance()
                if balance:
                    total_money = float(balance.get('TotalMoney', 0))
                    msg = f"🔔 장 시작!\n총 자산: {total_money:,.0f}원\n"
                    msg += f"봇 운용자금: {total_money * config.trade_budget_ratio:,.0f}원\n"
                    msg += f"타겟 종목: {enabled_count}개"
                    logger.info(msg)
                    discord_alert.SendMessage(msg)
                market_open_notified = True
            
            # 거래 시간이 아니면 대기
            if not is_trading_time:
                logger.info("장 시간 외입니다.")
                time.sleep(300)  # 5분 대기
                continue
            
            # 포지션 관리 (매도 신호 체크)
            logger.info("=== 타겟 종목 포지션 관리 ===")
            trading_state = process_positions(trading_state)
            save_trading_state(trading_state)
            
            # 새로운 매수 기회 스캔 (15시 이전까지만)
            if now.hour < 15:
                logger.info("=== 타겟 종목 매수 기회 스캔 ===")
                buy_opportunities = scan_target_stocks(trading_state)
                
                if buy_opportunities:
                    # 매수 실행
                    trading_state = execute_buy_opportunities(buy_opportunities, trading_state)
                    save_trading_state(trading_state)
            
            # 1시간마다 타겟 종목 현황 보고
            if (now - last_status_report).seconds >= 3600:  # 1시간마다
                send_target_stock_status()
                last_status_report = now
            
            # 장 마감 후 일일 보고서 (15:30 이후)
            if now.hour >= 15 and now.minute >= 30 and not daily_report_sent:
                send_daily_report(trading_state)
                daily_report_sent = True
            
            # 30초 대기
            time.sleep(30)
            
        except Exception as e:
            error_msg = f"⚠️ 메인 루프 에러: {str(e)}"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            time.sleep(60)  # 에러 발생 시 1분 대기

if __name__ == "__main__":
    # 실제 거래 모드로 설정
    Common.SetChangeMode()
    
    main()