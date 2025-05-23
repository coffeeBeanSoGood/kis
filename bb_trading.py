#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
타겟 종목 매매봇 (Target Stock Trading Bot)
bb_trading.py의 방식을 참고하여 trend_trading.py의 기술적 분석을 적용
1. 미리 설정된 타겟 종목들에 대해서만 매매 진행
2. 종목별 개별 매매 파라미터 적용
3. trend_trading.py의 고도화된 기술적 분석 활용
4. bb_trading.py의 체계적인 리스크 관리 적용
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

################################### 상수 정의 ##################################

# 봇 네임 설정
BOT_NAME = Common.GetNowDist() + "_TargetStockBot"

# 전략 설정 (bb_trading.py 방식 참고)
TRADE_BUDGET_RATIO = 0.90           # 전체 계좌의 90%를 이 봇이 사용
MAX_POSITIONS = 8                   # 최대 보유 종목 수 (타겟 종목 수와 동일하게)
MIN_STOCK_PRICE = 3000              # 최소 주가 3,000원
MAX_STOCK_PRICE = 200000            # 최대 주가 200,000원

# 손익 관리 설정
STOP_LOSS_RATIO = -0.025            # 손절 비율 (-2.5%)
TAKE_PROFIT_RATIO = 0.055           # 익절 비율 (5.5%)
TRAILING_STOP_RATIO = 0.018         # 트레일링 스탑 비율 (1.8%)
MAX_DAILY_LOSS = -0.04              # 일일 최대 손실 한도 (-4%)
MAX_DAILY_PROFIT = 0.06             # 일일 최대 수익 한도 (6%)

# 기술적 분석 설정 (trend_trading.py 방식 적용)
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2.0

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

################################### 타겟 종목 설정 ##################################
TARGET_STOCKS = {}
################################### 설정 파일 관리 ##################################

def _load_config(config_path: str = "target_stock_config.json") -> Dict[str, any]:
    """설정 파일 로드"""
    default_config = {
        "target_stocks": TARGET_STOCKS,
        "total_budget": 50000000,
        "max_positions": 8,
        "min_stock_price": 3000,
        "max_stock_price": 200000,
        "stop_loss_ratio": -0.025,
        "take_profit_ratio": 0.055,
        "trailing_stop_ratio": 0.018,
        "max_daily_loss": -0.04,
        "max_daily_profit": 0.06,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "last_sector_update": ""
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

def _save_config(config: dict, config_path: str = "target_stock_config.json") -> None:
    """설정 파일 저장"""
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"설정 파일 저장 완료: {config_path}")
    except Exception as e:
        logger.exception(f"설정 파일 저장 중 오류: {str(e)}")


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

################################### 유틸리티 함수 ##################################

def _update_stock_info(target_stocks):
    """종목별 이름과 섹터 정보 자동 업데이트 (신규 함수)"""
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
    """거래 수수료 및 세금 계산 (bb_trading.py 방식)"""
    commission_rate = 0.0000156
    tax_rate = 0
    special_tax_rate = 0.0015
    
    commission = price * quantity * commission_rate
    if not is_buy:
        tax = price * quantity * tax_rate
        special_tax = price * quantity * special_tax_rate
    else:
        tax = 0
        special_tax = 0
    
    return commission + tax + special_tax

def check_trading_time():
    """장중 거래 가능한 시간대인지 체크 (bb_trading.py 방식)"""
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
        is_market_open = (status_code == '0' and current_time.hour == 8)
        is_trading_time = (status_code == '2')
        
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
    """종목 데이터 조회 및 기술적 분석 (trend_trading.py 방식 적용)"""
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
        
        # trend_trading.py의 기술적 지표 계산 활용
        df['RSI'] = TechnicalIndicators.calculate_rsi(df, RSI_PERIOD)
        
        macd_data = TechnicalIndicators.calculate_macd(
            df, MACD_FAST, MACD_SLOW, MACD_SIGNAL
        )
        df[['MACD', 'Signal', 'Histogram']] = macd_data
        
        bb_data = TechnicalIndicators.calculate_bollinger_bands(
            df, BB_PERIOD, BB_STD
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
    """매수 신호 분석 (trend_trading.py 방식 + bb_trading.py 점수 시스템)"""
    try:
        signals = []
        score = 0
        
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        rsi = stock_data['rsi']
        
        # 종목별 개별 설정 적용
        rsi_oversold = target_config.get('rsi_oversold', RSI_OVERSOLD)
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
        
        # 6. 거래량 분석 (trend_trading.py 방식 적용)
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
    """매도 신호 분석 (bb_trading.py 방식 + trend_trading.py 기술적 분석)"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position['entry_price']
        
        # 수익률 계산
        profit_rate = (current_price - entry_price) / entry_price
        
        # 종목별 개별 설정 적용
        profit_target = target_config.get('profit_target', TAKE_PROFIT_RATIO)
        stop_loss = target_config.get('stop_loss', STOP_LOSS_RATIO)
        trailing_stop = target_config.get('trailing_stop', TRAILING_STOP_RATIO)
        rsi_overbought = target_config.get('rsi_overbought', RSI_OVERBOUGHT)
        
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
        
        # 기술적 매도 신호 판정 (70점 이상 + 수익 상태일 때)
        is_sell_signal = score >= 70 and profit_rate > 0.01  # 최소 1% 수익일 때만
        
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
    """트레이딩 상태 로드 (bb_trading.py 방식)"""
    try:
        with open(f"TargetStockBot_{BOT_NAME}.json", 'r') as f:
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
    """트레이딩 상태 저장 (bb_trading.py 방식)"""
    with open(f"TargetStockBot_{BOT_NAME}.json", 'w') as f:
        json.dump(state, f, indent=2)

################################### 매매 실행 ##################################

def calculate_position_size(target_config, available_budget, stock_price):
    """포지션 크기 계산 (bb_trading.py + 종목별 설정)"""
    try:
        # 계좌 잔고 확인
        balance = KisKR.GetBalance()
        if not balance:
            return 0
            
        actual_balance = float(balance.get('RemainMoney', 0))
        usable_budget = min(available_budget, actual_balance)
        
        # 종목별 할당 비율 적용
        allocation_ratio = target_config.get('allocation_ratio', 0.125)  # 기본 12.5% (8개 종목 기준)
        allocated_budget = usable_budget * allocation_ratio
        
        # 매수 가능 수량 계산
        max_quantity = int(allocated_budget / stock_price)
        
        return max(1, max_quantity) if max_quantity > 0 else 0
        
    except Exception as e:
        logger.error(f"포지션 크기 계산 중 에러: {str(e)}")
        return 0

def execute_buy_order(stock_code, target_config, quantity, price):
    """매수 주문 실행 (bb_trading.py 방식)"""
    try:
        stock_name = target_config.get('name', stock_code)
        logger.info(f"{stock_name}({stock_code}) 매수 주문: {quantity}주 @ {price:,.0f}원")
        
        # 지정가 매수 주문
        order_result = KisKR.MakeBuyLimitOrder(stock_code, quantity, int(price))
        
        if not order_result or isinstance(order_result, str):
            logger.error(f"매수 주문 실패: {order_result}")
            return None, None
        
        # 체결 확인 (최대 30초 대기)
        start_time = time.time()
        while time.time() - start_time < 30:
            my_stocks = KisKR.GetMyStockList()
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    executed_amount = int(stock.get('StockAmt', 0))
                    if executed_amount > 0:
                        avg_price = float(stock.get('AvrPrice', price))
                        logger.info(f"매수 체결 확인: {executed_amount}주 @ {avg_price:,.0f}원")
                        return avg_price, executed_amount
            time.sleep(2)
        
        logger.warning(f"매수 체결 확인 실패: {stock_code}")
        return None, None
        
    except Exception as e:
        logger.error(f"매수 주문 실행 중 에러: {str(e)}")
        return None, None

def execute_sell_order(stock_code, target_config, quantity):
    """매도 주문 실행 (bb_trading.py 방식)"""
    try:
        stock_name = target_config.get('name', stock_code)
        logger.info(f"{stock_name}({stock_code}) 매도 주문: {quantity}주")
        
        # 시장가 매도 주문
        order_result = KisKR.MakeSellMarketOrder(stock_code, quantity)
        
        if not order_result or isinstance(order_result, str):
            logger.error(f"매도 주문 실패: {order_result}")
            return None, None
        
        # 체결 확인 (최대 30초 대기)
        start_time = time.time()
        initial_amount = quantity
        
        while time.time() - start_time < 30:
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
            
            time.sleep(2)
        
        logger.warning(f"매도 체결 확인 실패: {stock_code}")
        return None, None
        
    except Exception as e:
        logger.error(f"매도 주문 실행 중 에러: {str(e)}")
        return None, None

################################### 보고서 생성 ##################################

def send_daily_report(trading_state):
    """일일 거래 성과 보고서 (bb_trading.py 방식)"""
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
                if stock_code in trading_state['positions'] and stock_code in TARGET_STOCKS:
                    target_config = TARGET_STOCKS[stock_code]
                    msg += f"- {target_config['name']}({stock_code}): "
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
        
        for stock_code, config in TARGET_STOCKS.items():
            if not config.get('enabled', True):
                continue
                
            current_price = KisKR.GetCurrentPrice(stock_code)
            if current_price:
                stock_data = get_stock_data(stock_code)
                if stock_data:
                    buy_analysis = analyze_buy_signal(stock_data, config)
                    
                    msg += f"\n[{config['name']}({stock_code})]\n"
                    msg += f"현재가: {current_price:,}원\n"
                    msg += f"RSI: {stock_data['rsi']:.1f} (기준: {config['rsi_oversold']})\n"
                    msg += f"매수점수: {buy_analysis['score']}/{config['min_score']}\n"
                    
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
    """타겟 종목 매수 기회 스캔 (bb_trading.py 방식 + trend_trading.py 분석)"""
    try:
        buy_opportunities = []
        current_positions = len(trading_state['positions'])
        
        # 최대 보유 종목 수 확인
        if current_positions >= MAX_POSITIONS:
            logger.info(f"최대 보유 종목 수({MAX_POSITIONS}개) 도달")
            return []
        
        logger.info(f"타겟 종목 매수 기회 스캔 시작: {len(TARGET_STOCKS)}개 종목 분석")
        
        for stock_code, target_config in TARGET_STOCKS.items():
            try:
                # 비활성화된 종목 제외
                if not target_config.get('enabled', True):
                    continue
                    
                # 이미 보유 중인 종목은 제외
                if stock_code in trading_state['positions']:
                    continue
                
                # 가격 필터링
                current_price = KisKR.GetCurrentPrice(stock_code)
                if not current_price or current_price < MIN_STOCK_PRICE or current_price > MAX_STOCK_PRICE:
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
                        'stock_name': target_config['name'],
                        'price': current_price,
                        'score': buy_analysis['score'],
                        'min_score': buy_analysis['min_score'],
                        'signals': buy_analysis['signals'],
                        'analysis': buy_analysis['analysis'],
                        'target_config': target_config
                    })
                    
                    logger.info(f"✅ 매수 기회 발견: {target_config['name']}({stock_code})")
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
    """트레일링 스탑 업데이트 (bb_trading.py 방식 + 종목별 설정)"""
    try:
        trailing_stop_ratio = target_config.get('trailing_stop', TRAILING_STOP_RATIO)
        
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
    """보유 포지션 관리 (bb_trading.py 방식 + trend_trading.py 분석)"""
    try:
        my_stocks = KisKR.GetMyStockList()
        positions_to_remove = []
        
        for stock_code, position in trading_state['positions'].items():
            try:
                # 타겟 종목이 아닌 경우 스킵
                if stock_code not in TARGET_STOCKS:
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
                
                target_config = TARGET_STOCKS[stock_code]
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
                    logger.info(f"🔴 매도 신호 감지: {target_config['name']}({stock_code})")
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
                        msg = f"💰 매도 완료: {target_config['name']}({stock_code})\n"
                        msg += f"매도가: {executed_price:,.0f}원\n"
                        msg += f"수량: {executed_amount}주\n"
                        msg += f"순손익: {net_profit:,.0f}원 ({profit_rate:.2f}%)\n"
                        msg += f"매도사유: {sell_analysis['reason']}"
                        
                        logger.info(msg)
                        discord_alert.SendMessage(msg)
                        
                        # 포지션 제거
                        positions_to_remove.append(stock_code)
                    else:
                        logger.error(f"매도 주문 실패: {target_config['name']}({stock_code})")
                
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
    """매수 기회 실행 (bb_trading.py 방식 + 종목별 설정)"""
    try:
        if not buy_opportunities:
            return trading_state
        
        # 계좌 정보 조회
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return trading_state
        
        total_money = float(balance.get('TotalMoney', 0))
        available_budget = total_money * TRADE_BUDGET_RATIO
        
        # 일일 손실/수익 한도 확인
        daily_stats = trading_state['daily_stats']
        if daily_stats['start_balance'] > 0:
            daily_profit_rate = daily_stats['total_profit'] / daily_stats['start_balance']
            
            if daily_profit_rate <= MAX_DAILY_LOSS:
                logger.info(f"일일 손실 한도 도달: {daily_profit_rate*100:.1f}%")
                return trading_state
            
            if daily_profit_rate >= MAX_DAILY_PROFIT:
                logger.info(f"일일 수익 한도 도달: {daily_profit_rate*100:.1f}%")
                return trading_state
        
        current_positions = len(trading_state['positions'])
        max_new_positions = MAX_POSITIONS - current_positions
        
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
                        'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', TRAILING_STOP_RATIO)),
                        'target_config': target_config,
                        'buy_analysis': opportunity['analysis']
                    }
                    
                    # 매수 완료 알림
                    msg = f"✅ 매수 완료: {stock_name}({stock_code})\n"
                    msg += f"매수가: {executed_price:,.0f}원\n"
                    msg += f"수량: {executed_amount}주\n"
                    msg += f"투자금액: {executed_price * executed_amount:,.0f}원\n"
                    msg += f"수수료: {buy_fee:,.0f}원\n"
                    msg += f"목표수익률: {target_config.get('profit_target', TAKE_PROFIT_RATIO)*100:.1f}%\n"
                    msg += f"손절률: {target_config.get('stop_loss', STOP_LOSS_RATIO)*100:.1f}%"
                    
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

def main():
    """메인 함수"""
    global TARGET_STOCKS
    # 설정 파일 로드
    config_path = "target_stock_config.json"

    # 설정 파일이 없으면 생성
    if not os.path.exists(config_path):
        create_config_file(config_path)
        logger.info(f"기본 설정 파일 생성 완료: {config_path}")

    # 설정 로드
    config = _load_config(config_path)
    TARGET_STOCKS = config.get("target_stocks", TARGET_STOCKS)
    # 섹터 정보 업데이트 (날짜가 바뀌었거나 처음 실행시)
    today = datetime.datetime.now().strftime('%Y%m%d')
    last_update = config.get("last_sector_update", "")
    
    if last_update != today:
        logger.info("섹터 정보 자동 업데이트 시작...")
        TARGET_STOCKS = _update_stock_info(TARGET_STOCKS)
        
        # 업데이트된 설정 저장
        config["target_stocks"] = TARGET_STOCKS
        config["last_sector_update"] = today
        _save_config(config, config_path)

    msg = "🎯 타겟 종목 매매봇 시작!"
    logger.info(msg)
    discord_alert.SendMessage(msg)
    
    # 타겟 종목 현황 출력
    enabled_count = sum(1 for config in TARGET_STOCKS.values() if config.get('enabled', True))
    logger.info(f"활성화된 타겟 종목: {enabled_count}개")
    for stock_code, config in TARGET_STOCKS.items():
        if config.get('enabled', True):
            logger.info(f"  - {config['name']}({stock_code}): "
                       f"목표수익률 {config.get('profit_target', 0)*100:.1f}%, "
                       f"손절률 {config.get('stop_loss', 0)*100:.1f}%, "
                       f"배분비율 {config.get('allocation_ratio', 0)*100:.1f}%")
    
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
            
            # 장 시작 알림
            if is_market_open and not market_open_notified:
                balance = KisKR.GetBalance()
                if balance:
                    total_money = float(balance.get('TotalMoney', 0))
                    msg = f"🔔 장 시작!\n총 자산: {total_money:,.0f}원\n"
                    msg += f"봇 운용자금: {total_money * TRADE_BUDGET_RATIO:,.0f}원\n"
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

def create_config_file(config_path: str = "target_stock_config.json") -> None:
   """기본 설정 파일 생성"""
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
           
           # 전략 설정 (bb_trading.py 방식 참고)
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
           
           # 기술적 분석 설정 (trend_trading.py 방식 적용)
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
   
if __name__ == "__main__":
    # 실제 거래 모드로 설정
    Common.SetChangeMode()
    
    main()