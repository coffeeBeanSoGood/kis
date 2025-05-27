#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
타겟 종목 매매봇 (Target Stock Trading Bot) - Config 클래스 적용 완전 개선 버전
bb_trading.py의 방식을 참고하여 trend_trading.py의 기술적 분석을 적용
1. 미리 설정된 타겟 종목들에 대해서만 매매 진행
2. 종목별 개별 매매 파라미터 적용
3. technical_analysis.py의 고도화된 기술적 분석 활용
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
from technical_analysis import TechnicalIndicators, AdaptiveMarketStrategy, TrendFilter

import requests
from bs4 import BeautifulSoup

from pending_order_manager import PendingOrderManager, enhance_trading_state

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
            
            # 🔥 손익 관리 설정 - 개선된 버전
            "stop_loss_ratio": -0.045,          # -2.5% → -4.5%로 완화
            "take_profit_ratio": 0.08,          # 5.5% → 8%로 상향
            "trailing_stop_ratio": 0.025,       # 1.8% → 2.5%로 완화
            "max_daily_loss": -0.06,            # -4% → -6%로 완화
            "max_daily_profit": 0.08,           # 6% → 8%로 상향
            
            # 🔥 손절 지연 설정 (새로 추가)
            "stop_loss_delay_hours": 2,         # 매수 후 2시간은 손절 지연
            "volatility_stop_multiplier": 1.5,  # 변동성 기반 손절 배수
            "use_adaptive_stop": True,          # 적응형 손절 사용
            "min_holding_hours": 4,             # 최소 보유시간 4시간
            
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
        """최대 보유 종목 수 - 활성 타겟 종목 수 기반"""
        active_count = 0
        for stock_code, config in self.target_stocks.items():
            if config.get('enabled', True):
                active_count += 1
        return active_count if active_count > 0 else 1
    
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

    @property
    def absolute_budget_strategy(self):
        """절대 예산 관리 전략 (strict, adaptive, proportional)"""
        return self.config.get("absolute_budget_strategy", "strict")
    
    @property
    def budget_loss_tolerance(self):
        """예산 손실 허용 비율 (adaptive 모드용)"""
        return self.config.get("budget_loss_tolerance", 0.2)
    
    @property
    def initial_total_asset(self):
        """초기 총 자산 (proportional 모드용)"""
        return self.config.get("initial_total_asset", 0)

    
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

    # 기존 속성들 다음에 추가
    @property
    def use_absolute_budget(self):
        """절대 예산 사용 여부"""
        return self.config.get("use_absolute_budget", False)

    @property
    def absolute_budget(self):
        """절대 예산 금액 (원)"""
        return self.config.get("absolute_budget", 5000000)

    @property
    def use_adaptive_strategy(self):
        """적응형 전략 사용 여부"""
        return self.config.get("use_adaptive_strategy", True)

    @property
    def use_trend_filter(self):
        """트렌드 필터 사용 여부"""
        return self.config.get("use_trend_filter", True)
    
    # =========================== 분봉 타이밍 설정 ===========================
    @property
    def use_intraday_timing(self):
        """분봉 진입 타이밍 사용 여부"""
        return self.config.get("use_intraday_timing", False)  # 기본값 False (백테스트 고려)
    
    @property
    def intraday_check_interval(self):
        """분봉 체크 주기 (초)"""
        return self.config.get("intraday_check_interval", 30)
    
    @property
    def max_candidate_wait_hours(self):
        """최대 대기 시간"""
        return self.config.get("max_candidate_wait_hours", 2)


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

log_file = os.path.join(log_directory, 'bb_trading.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=3,
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

import technical_analysis
technical_analysis.set_logger(logger)

# import news_analysis
# news_analysis.set_logger(logger)

# =========================== 전역 설정 인스턴스 ===========================
trading_config = None
pending_manager = None

def initialize_pending_manager():
    """미체결 주문 관리자 초기화"""
    global pending_manager
    
    pending_manager = PendingOrderManager(
        kis_api=KisKR,
        trading_config=trading_config, 
        discord_alert=discord_alert,
        logger=logger,
        fee_calculator=calculate_trading_fee  # 🎯 초기화시 바로 전달
    )
    
    logger.info("🔧 미체결 주문 관리자 초기화 완료")

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

def get_active_target_stock_count():
    """활성화된 타겟 종목 수 자동 계산"""
    try:
        active_count = 0
        for stock_code, config in trading_config.target_stocks.items():
            if config.get('enabled', True):  # enabled가 True인 것만 카운트
                active_count += 1
        
        logger.debug(f"활성 타겟 종목 수: {active_count}개")
        return active_count
        
    except Exception as e:
        logger.error(f"활성 종목 수 계산 중 오류: {str(e)}")
        return 1  # 최소 1개로 설정하여 0으로 나누기 방지

def get_per_stock_budget_limit():
    """종목별 예산 한도 계산 - 활성 종목 수 기반"""
    try:
        if trading_config.use_absolute_budget:
            total_budget = trading_config.absolute_budget
        else:
            balance = KisKR.GetBalance()
            if not balance:
                return 0
            total_money = float(balance.get('TotalMoney', 0))
            total_budget = total_money * trading_config.trade_budget_ratio
        
        active_stock_count = get_active_target_stock_count()
        
        if active_stock_count == 0:
            logger.warning("활성화된 타겟 종목이 없습니다")
            return 0
        
        per_stock_limit = total_budget / active_stock_count
        
        logger.debug(f"종목별 예산 한도: {per_stock_limit:,.0f}원 (총예산: {total_budget:,.0f}원 ÷ {active_stock_count}종목)")
        return per_stock_limit
        
    except Exception as e:
        logger.error(f"종목별 예산 한도 계산 중 오류: {str(e)}")
        return 0
    
def get_total_invested_amount(trading_state):
    """현재 총 투자된 금액 계산"""
    try:
        total_invested = 0
        for stock_code, position in trading_state['positions'].items():
            if stock_code in trading_config.target_stocks:
                invested_amount = position['entry_price'] * position['amount']
                total_invested += invested_amount
                logger.debug(f"투자된 금액 - {stock_code}: {invested_amount:,.0f}원")
        
        logger.info(f"📊 총 투자된 금액: {total_invested:,.0f}원")
        return total_invested
        
    except Exception as e:
        logger.error(f"총 투자 금액 계산 중 오류: {str(e)}")
        return 0

def get_invested_amount_for_stock(stock_code, trading_state):
    """특정 종목에 투자된 금액 계산"""
    try:
        if stock_code not in trading_state['positions']:
            return 0
        
        position = trading_state['positions'][stock_code]
        invested_amount = position['entry_price'] * position['amount']
        
        logger.debug(f"종목별 투자금액 - {stock_code}: {invested_amount:,.0f}원")
        return invested_amount
        
    except Exception as e:
        logger.error(f"종목별 투자 금액 계산 중 오류 ({stock_code}): {str(e)}")
        return 0    

def get_available_budget(trading_state=None):
    """사용 가능한 예산 계산 - 이미 투자된 금액 차감 (개선됨)"""
    try:
        if trading_state is None:
            trading_state = load_trading_state()
        
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return 0
            
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        
        if total_money <= 0:
            logger.warning("계좌 총 자산이 0 이하입니다.")
            return 0
        
        # 총 투자 가능 예산 계산
        if trading_config.use_absolute_budget:
            total_target_budget = trading_config.absolute_budget
            strategy = trading_config.absolute_budget_strategy
            
            logger.info(f"💰 절대금액 예산 모드: {strategy}")
            
            if strategy == "proportional":
                initial_asset = trading_config.initial_total_asset
                
                if initial_asset <= 0:
                    initial_asset = total_money
                    trading_config.config["initial_total_asset"] = initial_asset
                    trading_config.save_config()
                    logger.info(f"🎯 초기 총자산 설정: {initial_asset:,.0f}원")
                
                performance = (total_money - initial_asset) / initial_asset
                
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
                
                total_target_budget = total_target_budget * multiplier
                
                logger.info(f"  - 성과 기반 조정: {performance*100:+.1f}% → 배율 {multiplier:.3f}")
                
            elif strategy == "adaptive":
                loss_tolerance = trading_config.budget_loss_tolerance
                min_budget = total_target_budget * (1 - loss_tolerance)
                
                if total_money >= min_budget:
                    total_target_budget = total_target_budget
                else:
                    total_target_budget = max(total_money, min_budget)
            
            # strategy == "strict"는 그대로 유지
        else:
            # 비율 기반 예산
            total_target_budget = total_money * trading_config.trade_budget_ratio
        
        # 🎯 핵심: 이미 투자된 금액 차감
        total_invested = get_total_invested_amount(trading_state)
        remaining_target_budget = total_target_budget - total_invested
        
        # 현금 잔고와 비교하여 최종 사용 가능 예산 결정
        available_budget = min(remaining_target_budget, remain_money)
        
        logger.info(f"📊 개선된 예산 계산:")
        logger.info(f"  - 목표 총예산: {total_target_budget:,.0f}원")
        logger.info(f"  - 이미 투자됨: {total_invested:,.0f}원")
        logger.info(f"  - 남은 목표예산: {remaining_target_budget:,.0f}원")
        logger.info(f"  - 현금 잔고: {remain_money:,.0f}원")
        logger.info(f"  - 사용가능 예산: {available_budget:,.0f}원")
        
        return max(0, available_budget)
        
    except Exception as e:
        logger.error(f"개선된 예산 계산 중 에러: {str(e)}")
        return 0

def get_remaining_budget_for_stock(stock_code, trading_state):
    """특정 종목의 남은 투자 가능 예산 계산 - 미체결 주문 금액 포함"""
    try:
        per_stock_limit = get_per_stock_budget_limit()
        
        # 🆕 라이브러리 사용해서 미체결 주문 금액 포함 계산
        committed_amount = pending_manager.get_committed_budget_for_stock(
            stock_code, trading_state, get_invested_amount_for_stock
        )
        
        remaining = per_stock_limit - committed_amount
        
        stock_name = trading_config.target_stocks.get(stock_code, {}).get('name', stock_code)
        logger.debug(f"💰 {stock_name}({stock_code}) 남은 예산: {remaining:,}원 (한도: {per_stock_limit:,}원, 사용중: {committed_amount:,}원)")
        
        return max(0, remaining)
        
    except Exception as e:
        logger.error(f"종목별 남은 예산 계산 중 오류 ({stock_code}): {str(e)}")
        return 0

def get_budget_info_message():
    """예산 정보 메시지 생성 - 종목별 분배 현황 포함 (개선됨)"""
    try:
        trading_state = load_trading_state()
        balance = KisKR.GetBalance()
        
        if not balance:
            return "계좌 정보 조회 실패"
        
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        
        # 예산 계산
        total_available_budget = get_available_budget(trading_state)
        total_invested = get_total_invested_amount(trading_state)
        per_stock_limit = get_per_stock_budget_limit()
        
        # 기본 정보
        if trading_config.use_absolute_budget:
            strategy = trading_config.absolute_budget_strategy
            absolute_budget = trading_config.absolute_budget
            
            msg = f"💰 절대금액 예산 운용 ({strategy})\n"
            msg += f"설정 예산: {absolute_budget:,.0f}원\n"
        else:
            msg = f"📊 비율 기반 예산 운용\n"
            msg += f"설정 비율: {trading_config.trade_budget_ratio*100:.1f}%\n"
        
        msg += f"현재 자산: {total_money:,.0f}원\n"
        msg += f"현금 잔고: {remain_money:,.0f}원\n"
        msg += f"\n📈 투자 현황:\n"
        msg += f"• 총 투자됨: {total_invested:,.0f}원\n"
        msg += f"• 사용가능: {total_available_budget:,.0f}원\n"
        msg += f"• 종목별 한도: {per_stock_limit:,.0f}원\n"
        
        # 종목별 투자 현황
        msg += f"\n🎯 종목별 투자 현황:\n"
        for stock_code, stock_config in trading_config.target_stocks.items():
            if not stock_config.get('enabled', True):
                continue
                
            stock_name = stock_config.get('name', stock_code)
            invested = get_invested_amount_for_stock(stock_code, trading_state)
            remaining = get_remaining_budget_for_stock(stock_code, trading_state)
            usage_rate = (invested / per_stock_limit * 100) if per_stock_limit > 0 else 0
            
            if invested > 0:
                msg += f"• {stock_name}: {invested:,.0f}원 ({usage_rate:.1f}%)\n"
            else:
                msg += f"• {stock_name}: 투자 대기 (가능: {remaining:,.0f}원)\n"
        
        return msg
        
    except Exception as e:
        logger.error(f"개선된 예산 정보 메시지 생성 중 에러: {str(e)}")
        return "예산 정보 조회 실패"

def get_safe_config_value(target_config, key, default_value):
    """종목별 설정에서 안전하게 값 가져오기"""
    try:
        # 종목별 설정에서 먼저 찾기
        if key in target_config and target_config[key] is not None:
            return target_config[key]
        
        # 전역 설정에서 찾기
        if hasattr(trading_config, key):
            return getattr(trading_config, key)
        
        # 기본값 반환
        return default_value
        
    except Exception as e:
        logger.warning(f"설정값 조회 중 오류 ({key}): {str(e)}")
        return default_value        

def calculate_trading_fee(price, quantity, is_buy=True):
    """거래 수수료 및 세금 계산"""
    commission_rate = 0.0000156  # 수수료 0.00156%
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

def detect_stock_environment(stock_code):
    """개별 종목의 환경 감지 - 시장 환경 감지 로직 적용"""
    try:
        # 개별 종목 데이터 조회
        stock_data = KisKR.GetOhlcvNew(stock_code, 'D', 60, adj_ok=1)
        
        if stock_data is None or stock_data.empty:
            return "sideways"  # 기본값
        
        # 이동평균선 계산
        stock_data['MA5'] = stock_data['close'].rolling(window=5).mean()
        stock_data['MA20'] = stock_data['close'].rolling(window=20).mean()
        stock_data['MA60'] = stock_data['close'].rolling(window=60).mean()
        
        # RSI 계산 추가
        stock_data['RSI'] = TechnicalIndicators.calculate_rsi(stock_data)
        
        # MACD 계산 추가
        stock_data[['MACD', 'Signal', 'Histogram']] = TechnicalIndicators.calculate_macd(
            stock_data, 
            fast_period=12, 
            slow_period=26, 
            signal_period=9
        )
        
        # 볼린저 밴드 계산 추가
        stock_data[['MiddleBand', 'UpperBand', 'LowerBand']] = TechnicalIndicators.calculate_bollinger_bands(
            stock_data,
            period=20,
            num_std=2.0
        )
        
        # 추세 강도 계산 (ADX 대용)
        trend_strength = abs((stock_data['MA20'].iloc[-1] / stock_data['MA20'].iloc[-21] - 1) * 100)
        
        # 이동평균선 방향성
        ma5_slope = (stock_data['MA5'].iloc[-1] / stock_data['MA5'].iloc[-6] - 1) * 100
        ma20_slope = (stock_data['MA20'].iloc[-1] / stock_data['MA20'].iloc[-21] - 1) * 100
        
        # 변동성 측정 (볼린저 밴드 폭)
        recent_bandwidth = (stock_data['UpperBand'].iloc[-1] - stock_data['LowerBand'].iloc[-1]) / stock_data['MiddleBand'].iloc[-1] * 100
        avg_bandwidth = ((stock_data['UpperBand'] - stock_data['LowerBand']) / stock_data['MiddleBand']).rolling(window=20).mean().iloc[-1] * 100
        
        # 볼륨 트렌드 (거래량 증가 여부)
        volume_trend = (stock_data['volume'].iloc[-5:].mean() / stock_data['volume'].iloc[-20:-5].mean()) > 1.0
        
        # MACD 히스토그램 방향
        histogram_direction = stock_data['Histogram'].diff().iloc[-1] > 0
        
        # 최근 연속 상승/하락 일수 계산
        price_changes = stock_data['close'].pct_change().iloc[-10:]
        consecutive_up = 0
        consecutive_down = 0
        current_consecutive_up = 0
        current_consecutive_down = 0
        
        for change in price_changes:
            if change > 0:
                current_consecutive_up += 1
                current_consecutive_down = 0
            elif change < 0:
                current_consecutive_down += 1
                current_consecutive_up = 0
            else:
                current_consecutive_up = 0
                current_consecutive_down = 0
                
            consecutive_up = max(consecutive_up, current_consecutive_up)
            consecutive_down = max(consecutive_down, current_consecutive_down)
        
        # 상승장 지표 점수
        uptrend_score = 0
        if ma5_slope > 0.8: uptrend_score += 2
        if ma20_slope > 0.3: uptrend_score += 2
        if stock_data['MA5'].iloc[-1] > stock_data['MA20'].iloc[-1]: uptrend_score += 1
        if stock_data['close'].iloc[-1] > stock_data['MA20'].iloc[-1]: uptrend_score += 1
        if stock_data['RSI'].iloc[-1] > 55: uptrend_score += 1
        if histogram_direction: uptrend_score += 1
        if volume_trend: uptrend_score += 1
        if consecutive_up >= 3: uptrend_score += 1
        
        # 하락장 지표 점수
        downtrend_score = 0
        if ma5_slope < -0.8: downtrend_score += 2
        if ma20_slope < -0.3: downtrend_score += 2
        if stock_data['MA5'].iloc[-1] < stock_data['MA20'].iloc[-1]: downtrend_score += 1
        if stock_data['close'].iloc[-1] < stock_data['MA20'].iloc[-1]: downtrend_score += 1
        if stock_data['RSI'].iloc[-1] < 45: downtrend_score += 1
        if not histogram_direction: downtrend_score += 1
        if not volume_trend: downtrend_score += 1
        if consecutive_down >= 3: downtrend_score += 1
        
        # 횡보장 지표 - 변동성 관련
        sideways_score = 0
        if abs(ma5_slope) < 0.5: sideways_score += 2  # 단기 이동평균 기울기가 완만함
        if abs(ma20_slope) < 0.3: sideways_score += 2  # 중기 이동평균 기울기가 완만함
        if recent_bandwidth < avg_bandwidth: sideways_score += 2  # 최근 변동성이 평균보다 낮음
        if stock_data['RSI'].iloc[-1] > 40 and stock_data['RSI'].iloc[-1] < 60: sideways_score += 2  # RSI가 중간 영역
        if abs(stock_data['close'].iloc[-1] - stock_data['MA20'].iloc[-1]) / stock_data['MA20'].iloc[-1] < 0.02: sideways_score += 2  # 종가가 20일선 근처
        
        # 점수 기반 종목 환경 판단
        logger.debug(f"종목 {stock_code} 환경 점수 - 상승: {uptrend_score}, 하락: {downtrend_score}, 횡보: {sideways_score}")
        
        # 명확한 상승장/하락장 조건
        if uptrend_score >= 7 and uptrend_score > downtrend_score + 3 and uptrend_score > sideways_score + 2:
            result = "uptrend"
        elif downtrend_score >= 7 and downtrend_score > uptrend_score + 3 and downtrend_score > sideways_score + 2:
            result = "downtrend"
        # 횡보장 조건 강화
        elif sideways_score >= 6 and abs(uptrend_score - downtrend_score) <= 2:
            result = "sideways"
        # 약한 상승/하락 추세
        elif uptrend_score > downtrend_score + 2:
            result = "uptrend"
        elif downtrend_score > uptrend_score + 2:
            result = "downtrend"
        # 그 외는 횡보장으로 판단
        else:
            result = "sideways"
        
        logger.debug(f"종목 {stock_code} 환경 판정: {result}")
        return result
        
    except Exception as e:
        logger.warning(f"종목 {stock_code} 환경 감지 중 오류: {str(e)}")
        return "sideways"  # 기본값

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
    """매수 신호 분석 - 조건부 차단 방식 (균형잡힌 버전) - 디버깅 추가"""
    try:
        signals = []
        score = 0
        
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        rsi = stock_data['rsi']
        df = stock_data['ohlcv_data']
        
        # ========== 디버깅 로그 시작 ==========
        stock_name = target_config.get('name', stock_code)
        logger.info(f"🎯 [{stock_code}] {stock_name} 매수 신호 분석 시작")
        logger.info(f"📊 [{stock_code}] 기본 데이터: 현재가 {current_price:,}원, RSI {rsi:.1f}")
        
        # 🔍 극한 조건들 미리 계산
        
        # 1) 가격 위치 계산
        price_position = 0.5  # 기본값
        if len(df) >= 20:
            recent_low_20d = df['low'].iloc[-20:].min()
            recent_high_20d = df['high'].iloc[-20:].max()
            if recent_high_20d > recent_low_20d:
                price_position = (current_price - recent_low_20d) / (recent_high_20d - recent_low_20d)
        
        logger.info(f"📍 [{stock_code}] 가격 위치: {price_position*100:.1f}% (20일 구간)")
        
        # 2) 볼린저밴드 위치 계산
        bb_upper = stock_data.get('bb_upper', 0)
        bb_position_ratio = 0.5  # 기본값
        if bb_upper > 0:
            bb_position_ratio = current_price / bb_upper
        
        logger.info(f"📈 [{stock_code}] 볼린저밴드: 상단 {bb_upper:,.0f}원, 비율 {bb_position_ratio:.3f}")
        
        # 3) 거래량 비율 계산
        volume_ratio = 1.0
        if len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume_20d = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = recent_volume / avg_volume_20d if avg_volume_20d > 0 else 1
        
        logger.info(f"📊 [{stock_code}] 거래량: 최근 {recent_volume:,}주, 평균 대비 {volume_ratio:.2f}배")
        
        # 4) 연속 상승 일수 계산
        consecutive_up_days = 0
        if len(df) >= 5:
            recent_changes = df['close'].pct_change().iloc[-5:]
            for change in recent_changes:
                if change > 0.025:  # 2.5% 이상 상승
                    consecutive_up_days += 1
                else:
                    break
        
        logger.info(f"📈 [{stock_code}] 연속 상승: {consecutive_up_days}일")
        
        # 🚨 극한 조건 정의 (4개 중 2개 이상시 차단)
        extreme_conditions = [
            rsi >= 90,                      # RSI 90% 이상 (일진파워 94% 해당)
            price_position >= 0.90,         # 20일 구간 90% 이상 고점  
            bb_position_ratio >= 1.01,      # 볼밴 상단 1% 돌파
            volume_ratio >= 4.0,            # 거래량 4배 이상 급증
        ]
        
        extreme_count = sum(extreme_conditions)
        
        logger.info(f"⚠️ [{stock_code}] 극한 조건: {extreme_count}/4개 (RSI≥90: {extreme_conditions[0]}, 고점≥90%: {extreme_conditions[1]}, 볼밴돌파: {extreme_conditions[2]}, 거래량≥4배: {extreme_conditions[3]})")
        
        # 🚨 2개 이상 극한 조건 만족시 차단
        if extreme_count >= 2:
            extreme_reasons = []
            if extreme_conditions[0]: extreme_reasons.append(f"RSI 극과매수({rsi:.1f}%)")
            if extreme_conditions[1]: extreme_reasons.append(f"고점권({price_position*100:.1f}%)")
            if extreme_conditions[2]: extreme_reasons.append(f"볼밴상단돌파({bb_position_ratio:.3f})")
            if extreme_conditions[3]: extreme_reasons.append(f"거래량급증({volume_ratio:.1f}배)")
            
            logger.info(f"❌ [{stock_code}] 극한 조건 차단: {', '.join(extreme_reasons)}")
            
            return {
                'is_buy_signal': False,
                'signal_strength': 'REJECTED',
                'score': 0,
                'min_score': 0,
                'signals': [f"❌ 극한 조건 {extreme_count}개로 매수 차단: {', '.join(extreme_reasons)}"],
                'analysis': {
                    'rejection_reason': 'multiple_extreme_conditions',
                    'extreme_count': extreme_count,
                    'extreme_details': {
                        'rsi': rsi,
                        'price_position': price_position,
                        'bb_ratio': bb_position_ratio,
                        'volume_ratio': volume_ratio
                    }
                },
                'bb_position': 'rejected'
            }

        # 🔥 동적 파라미터 적용
        logger.info(f"🧠 [{stock_code}] 동적 파라미터 적용 시작...")
        
        if trading_config.use_adaptive_strategy:
            try:
                from technical_analysis import AdaptiveMarketStrategy
                adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
                market_env = detect_stock_environment(stock_code)
                
                logger.info(f"🌍 [{stock_code}] 시장 환경: {market_env}")
                
                if hasattr(adaptive_strategy, 'get_dynamic_parameters'):
                    dynamic_params = adaptive_strategy.get_dynamic_parameters(stock_code, market_env)
                    rsi_threshold = dynamic_params['rsi_threshold']
                    min_score = dynamic_params['min_score']
                    logger.info(f"🧠 [{stock_code}] 동적 파라미터: RSI기준 {rsi_threshold}, 점수기준 {min_score} (환경: {market_env})")
                else:
                    rsi_threshold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
                    min_score = target_config.get('min_score', 42)
                    logger.info(f"🔧 [{stock_code}] 기본 파라미터 (동적 메서드 없음): RSI기준 {rsi_threshold}, 점수기준 {min_score}")
                    
            except Exception as e:
                logger.warning(f"⚠️ [{stock_code}] 동적 파라미터 적용 실패: {e}")
                rsi_threshold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
                min_score = target_config.get('min_score', 42)
                logger.info(f"🔧 [{stock_code}] 기본 파라미터 (예외 발생): RSI기준 {rsi_threshold}, 점수기준 {min_score}")
        else:
            rsi_threshold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
            min_score = target_config.get('min_score', 42)
            logger.info(f"🔧 [{stock_code}] 기본 파라미터 (적응형 비활성): RSI기준 {rsi_threshold}, 점수기준 {min_score}")
    
        # 🎯 매수 신호 점수 계산 시작
        logger.info(f"🎯 [{stock_code}] 점수 계산 시작...")
        
        # 1) RSI 신호 (과매수 페널티 포함)
        rsi_score = 0
        if rsi <= 20:  # 극과매도
            rsi_score = 40
            signals.append(f"RSI 극과매도 {rsi:.1f} (+40)")
        elif rsi <= 25:  # 강과매도  
            rsi_score = 35
            signals.append(f"RSI 강과매도 {rsi:.1f} (+35)")
        elif rsi <= 30:  # 과매도
            rsi_score = 30
            signals.append(f"RSI 과매도 {rsi:.1f} (+30)")
        elif rsi <= rsi_threshold:  # 동적 기준
            rsi_score = 20
            signals.append(f"RSI 조정구간 {rsi:.1f} (+20)")
        elif rsi >= 85:  # 🔥 극과매수 페널티 (차단 아닌 페널티)
            rsi_score = -30
            signals.append(f"RSI 극과매수 페널티 {rsi:.1f} (-30)")
        elif rsi >= 75:  # 과매수 페널티
            rsi_score = -20
            signals.append(f"RSI 과매수 페널티 {rsi:.1f} (-20)")
        elif rsi >= 70:  # 과매수 주의
            rsi_score = -10
            signals.append(f"RSI 과매수 주의 {rsi:.1f} (-10)")
        
        score += rsi_score
        logger.info(f"📊 [{stock_code}] RSI 점수: {rsi_score}점 (누적: {score}점)")

        # 2) 볼린저밴드 신호 (상단 근처 페널티 포함)
        bb_lower = stock_data.get('bb_lower', 0)
        bb_middle = stock_data.get('bb_middle', 0)
        bb_position = "middle"
        bb_score = 0
        
        if bb_lower > 0:
            bb_lower_distance = (current_price - bb_lower) / bb_lower * 100
            
            if bb_lower_distance <= -2:  # 하단 돌파
                bb_score = 35
                signals.append("볼린저밴드 하단 돌파 (+35)")
                bb_position = "breakthrough"
            elif bb_lower_distance <= 3:  # 하단 근처
                bb_score = 25
                signals.append("볼린저밴드 하단 근처 (+25)")
                bb_position = "lower"
            elif current_price <= bb_middle:
                bb_score = 15
                signals.append("볼린저밴드 중간선 하단 (+15)")
                bb_position = "below_middle"
            elif bb_position_ratio >= 1.0:  # 🔥 상단 돌파 페널티 (차단 아닌 페널티)
                bb_score = -25
                signals.append(f"볼린저밴드 상단 돌파 페널티 (-25)")
                bb_position = "upper_break"
            elif bb_position_ratio >= 0.97:  # 상단 근접 페널티
                bb_score = -15
                signals.append(f"볼린저밴드 상단 근접 페널티 (-15)")
                bb_position = "upper_near"
        
        score += bb_score
        logger.info(f"📈 [{stock_code}] 볼린저밴드 점수: {bb_score}점 (누적: {score}점)")
        
        # 3) 이동평균선 추세 (기존 로직 유지)
        ma5 = stock_data['ma5']
        ma20 = stock_data['ma20']
        ma60 = stock_data['ma60']
        
        ma_score = 0
        if ma5 > ma20:
            if ma20 > ma60:
                ma_score = 20
                signals.append("완전 정배열 (+20)")
            else:
                ma_score = 15
                signals.append("단기 상승 추세 (+15)")
        elif ma5 > ma20 * 0.995:
            ma_score = 12
            signals.append("골든크로스 임박 (+12)")
        
        score += ma_score
        logger.info(f"📊 [{stock_code}] 이동평균 점수: {ma_score}점 (누적: {score}점)")

        # 4) 가격 위치 기반 점수 (페널티 포함)
        price_score = 0
        if price_position >= 0.85:  # 85% 이상 고점권 페널티
            price_score = -20
            signals.append(f"20일 고점권 페널티 {price_position*100:.1f}% (-20)")
        elif price_position >= 0.75:  # 75% 이상 페널티
            price_score = -10
            signals.append(f"20일 상위권 페널티 {price_position*100:.1f}% (-10)")
        elif price_position <= 0.2:  # 20일 저점 근처
            price_score = 25
            signals.append("20일 저점 근처 (+25)")
        elif price_position <= 0.3:
            price_score = 20
            signals.append("20일 하위 30% 구간 (+20)")
        elif price_position <= 0.4:
            price_score = 15
            signals.append("20일 하위 40% 구간 (+15)")
        
        score += price_score
        logger.info(f"📍 [{stock_code}] 가격위치 점수: {price_score}점 (누적: {score}점)")
        
        # 5) MACD 신호 (기존 로직 유지)
        macd = stock_data['macd']
        macd_signal = stock_data['macd_signal']
        macd_histogram = stock_data['macd_histogram']
        
        macd_score = 0
        if macd > macd_signal and macd_histogram > 0:
            macd_score = 15
            signals.append("MACD 골든크로스 + 상승 (+15)")
        elif macd > macd_signal:
            macd_score = 10
            signals.append("MACD 골든크로스 (+10)")
        elif macd_histogram > 0:
            macd_score = 8
            signals.append("MACD 모멘텀 상승 (+8)")
        
        score += macd_score
        logger.info(f"📊 [{stock_code}] MACD 점수: {macd_score}점 (누적: {score}점)")
        
        # 6) 거래량 신호 (과열 페널티 포함)
        volume_score = 0
        if volume_ratio >= 3.0:  # 🔥 3배 이상 급등시 페널티 (과열 우려)
            volume_score = -15
            signals.append(f"거래량 과열 페널티 {volume_ratio:.1f}배 (-15)")
        elif volume_ratio >= 1.5:  # 거래량 증가
            volume_score = 12
            signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+12)")
        elif volume_ratio >= 1.2:
            volume_score = 8
            signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+8)")
        
        score += volume_score
        logger.info(f"📊 [{stock_code}] 거래량 점수: {volume_score}점 (누적: {score}점)")
        
        # 7) 연속 상승 페널티
        consecutive_score = 0
        if consecutive_up_days >= 4:  # 4일 연속 급등 페널티
            consecutive_score = -20
            signals.append(f"연속 급등 페널티 {consecutive_up_days}일 (-20)")
        elif consecutive_up_days >= 3:  # 3일 연속 상승 주의
            consecutive_score = -10
            signals.append(f"연속 상승 주의 {consecutive_up_days}일 (-10)")
        
        score += consecutive_score
        logger.info(f"📈 [{stock_code}] 연속상승 점수: {consecutive_score}점 (누적: {score}점)")
        
        # 8) 연속 하락 후 반등 신호 (기존 로직 유지)
        reversal_score = 0
        if len(df) >= 5:
            consecutive_down = 0
            for i in range(1, 4):
                if df['close'].iloc[-i] < df['close'].iloc[-i-1]:
                    consecutive_down += 1
                else:
                    break
            
            if consecutive_down >= 2 and df['close'].iloc[-1] > df['close'].iloc[-2]:
                reversal_score = 20
                signals.append(f"연속하락 후 반등 ({consecutive_down}일) (+20)")
        
        score += reversal_score
        logger.info(f"🔄 [{stock_code}] 반등신호 점수: {reversal_score}점 (누적: {score}점)")
        
        # 🎯 최종 매수 판단
        signal_strength = 'NORMAL'
        
        # 강력한 매수 신호 조건 (적당히 강화)
        strong_conditions = [
            rsi <= 25,  # RSI 극과매도
            bb_position in ["breakthrough", "lower"],  # 볼린저밴드 하단권
            score >= 75,  # 🎯 70 → 75 (적당히 상향)
            any("연속하락 후 반등" in s for s in signals),  # 반등 신호
            price_position <= 0.4,  # 🎯 하위 40% 구간
        ]

        # 강력한 신호는 2개 이상 조건 만족시
        if sum(strong_conditions) >= 2:
            signal_strength = 'STRONG'

        is_buy_signal = score >= min_score
        
        logger.info(f"🎯 [{stock_code}] 최종 판정: 점수 {score}/{min_score}점, 신호강도 {signal_strength}")

        # 🎯 특별조건 할인 (조건 완화)
        if rsi <= 18 and bb_position == "breakthrough" and price_position <= 0.3:  # 정말 극한 상황에만
            discounted_score = max(25, min_score * 0.75)  # 할인 폭 적당히
            if score >= discounted_score and not is_buy_signal:
                signals.append(f"극한조건 점수할인: {discounted_score:.0f}점")
                is_buy_signal = True
                logger.info(f"🎁 [{stock_code}] 극한조건 할인 적용: {discounted_score:.0f}점")

        # target_config에 신호 강도 저장
        target_config['last_signal_strength'] = signal_strength
        target_config['last_signal_score'] = score

        logger.info(f"{'🎯' if is_buy_signal else '⏳'} [{stock_code}] 최종 결과: {'매수 신호' if is_buy_signal else '대기'} (점수: {score}/{min_score}점, 강도: {signal_strength})")

        return {
            'is_buy_signal': is_buy_signal,
            'signal_strength': signal_strength,
            'score': score,
            'min_score': min_score,
            'signals': signals if signals else ["매수 신호 부족"],
            'bb_position': bb_position,
            'analysis': {
                'rsi': rsi,
                'price_position': price_position,
                'volume_surge': volume_ratio,
                'trend_strength': 'strong' if ma5 > ma20 > ma60 else 'weak',
                'extreme_count': extreme_count,
                'safety_checks': {
                    'rsi_extreme': rsi >= 90,
                    'position_extreme': price_position >= 0.90,
                    'bb_extreme': bb_position_ratio >= 1.01,
                    'volume_extreme': volume_ratio >= 4.0,
                    'consecutive_surge': consecutive_up_days >= 4
                }
            },
            'used_parameters': {
                'rsi_threshold': rsi_threshold,
                'min_score': min_score,
                'market_env': detect_stock_environment(stock_code) if trading_config.use_adaptive_strategy else 'unknown'
            }
        }
        # ========== 디버깅 로그 끝 ==========
        
    except Exception as e:
        logger.error(f"❌ [{stock_data.get('stock_code', 'UNKNOWN')}] 매수 신호 분석 중 에러: {str(e)}")
        logger.exception(f"❌ [{stock_data.get('stock_code', 'UNKNOWN')}] 상세 에러 정보:")
        return {'is_buy_signal': False, 'score': 0, 'min_score': 0, 'signals': [f"분석 오류: {str(e)}"]}
    
# 🎯 분봉 타이밍도 조건부 차단으로 수정
def analyze_intraday_entry_timing(stock_code, target_config):
    """분봉 기준 최적 진입 타이밍 분석 - 조건부 차단 방식"""
    try:
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price:
            return {'enter_now': True, 'reason': '현재가 조회 실패로 즉시 진입'}
        
        # 분봉 데이터 조회 (기존 로직)
        try:
            df_5m = KisKR.GetOhlcvNew(stock_code, 'M', 24, adj_ok=1)
            
            if df_5m is None or len(df_5m) < 10:
                df_5m = Common.GetOhlcv("KR", stock_code, 24)
                
        except Exception as api_e:
            logger.debug(f"분봉 API 호출 실패: {str(api_e)}, 일봉으로 대체")
            df_5m = Common.GetOhlcv("KR", stock_code, 24)
        
        if df_5m is None or len(df_5m) < 10:
            return {'enter_now': True, 'reason': '데이터 부족으로 즉시 진입'}
        
        data_length = len(df_5m)
        
        # 기술적 지표 계산
        rsi_period = min(14, data_length // 2)
        ma_short = min(5, data_length // 4)
        ma_long = min(20, data_length // 2)
        bb_period = min(20, data_length // 2)
        
        if rsi_period < 3:
            return {'enter_now': True, 'reason': '데이터 부족으로 즉시 진입'}
        
        df_5m['RSI'] = TechnicalIndicators.calculate_rsi(df_5m, rsi_period)
        df_5m['MA_Short'] = df_5m['close'].rolling(window=ma_short).mean()
        df_5m['MA_Long'] = df_5m['close'].rolling(window=ma_long).mean()
        
        if data_length >= bb_period:
            bb_data = TechnicalIndicators.calculate_bollinger_bands(df_5m, bb_period, 2.0)
            df_5m[['BB_Mid', 'BB_Upper', 'BB_Lower']] = bb_data
        else:
            df_5m['BB_Mid'] = df_5m['close']
            df_5m['BB_Upper'] = df_5m['close'] * 1.02
            df_5m['BB_Lower'] = df_5m['close'] * 0.98
        
        # 🚨 분봉 극한 조건 계산
        intraday_rsi = df_5m['RSI'].iloc[-1] if not pd.isna(df_5m['RSI'].iloc[-1]) else 50
        bb_upper_5m = df_5m['BB_Upper'].iloc[-1]
        intraday_bb_ratio = current_price / bb_upper_5m if bb_upper_5m > 0 else 0.5
        
        # 분봉 극한 조건 (2개 이상시 진입 거부)
        intraday_extreme = [
            intraday_rsi >= 85,           # 분봉 RSI 85% 이상
            intraday_bb_ratio >= 1.02,    # 분봉 볼밴 상단 2% 돌파
        ]
        
        intraday_extreme_count = sum(intraday_extreme)
        
        # 🚨 분봉 극한 조건 2개 만족시 진입 거부
        if intraday_extreme_count >= 2:
            return {
                'enter_now': False,
                'entry_score': 0,
                'entry_signals': [f'분봉 극한 조건 {intraday_extreme_count}개로 진입 거부'],
                'reason': f'분봉 과열(RSI:{intraday_rsi:.1f}%, BB:{intraday_bb_ratio:.3f})로 진입 거부'
            }
        
        # 🎯 분봉 진입 점수 계산 (페널티 포함)
        entry_signals = []
        entry_score = 0
        
        # RSI 신호 (페널티 포함)
        if intraday_rsi <= 30:
            entry_score += 30
            entry_signals.append(f"분봉 RSI 과매도 {intraday_rsi:.1f} (+30)")
        elif intraday_rsi <= 45:
            entry_score += 20
            entry_signals.append(f"분봉 RSI 조정 {intraday_rsi:.1f} (+20)")
        elif intraday_rsi >= 80:  # 🔥 페널티 (차단 아님)
            entry_score -= 20
            entry_signals.append(f"분봉 RSI 과매수 페널티 {intraday_rsi:.1f} (-20)")
        elif intraday_rsi >= 70:
            entry_score -= 10
            entry_signals.append(f"분봉 RSI 과매수 주의 {intraday_rsi:.1f} (-10)")
        
        # 볼린저밴드 신호 (페널티 포함)
        bb_lower_5m = df_5m['BB_Lower'].iloc[-1]
        if not pd.isna(bb_lower_5m) and current_price <= bb_lower_5m * 1.02:
            entry_score += 25
            entry_signals.append("분봉 볼린저 하단 근접 (+25)")
        elif intraday_bb_ratio >= 1.0:  # 🔥 페널티 (차단 아님)
            entry_score -= 15
            entry_signals.append(f"분봉 볼밴 상단 페널티 (-15)")
        elif intraday_bb_ratio >= 0.98:
            entry_score -= 8
            entry_signals.append(f"분봉 볼밴 상단 주의 (-8)")
        
        # 나머지 신호들 (기존 로직)
        try:
            ma_short_current = df_5m['MA_Short'].iloc[-1]
            if not pd.isna(ma_short_current):
                distance_ratio = abs(current_price - ma_short_current) / ma_short_current
                if distance_ratio <= 0.01:
                    entry_score += 20
                    entry_signals.append(f"{ma_short}MA 지지 (+20)")
        except:
            pass
        
        try:
            if data_length >= 10:
                recent_volume = df_5m['volume'].iloc[-3:].mean()
                past_volume = df_5m['volume'].iloc[-10:-3].mean()
                
                if past_volume > 0:
                    volume_ratio = recent_volume / past_volume
                    if volume_ratio >= 1.3:
                        entry_score += 15
                        entry_signals.append(f"분봉 거래량 증가 {volume_ratio:.1f}배 (+15)")
        except:
            pass
        
        try:
            if data_length >= 5:
                recent_changes = df_5m['close'].pct_change().iloc[-4:]
                down_count = sum(1 for x in recent_changes if x < -0.01)
                last_change = df_5m['close'].pct_change().iloc[-1]
                
                if down_count >= 2 and last_change > 0.005:
                    entry_score += 20
                    entry_signals.append("분봉 반등 신호 (+20)")
                
                recent_high = df_5m['high'].iloc[-min(10, data_length):].max()
                if current_price >= recent_high * 0.98:  # 🔥 페널티 (차단 아님)
                    entry_score -= 10
                    entry_signals.append("분봉 단기 고점 페널티 (-10)")
        except:
            pass
        
        # 🎯 분봉 진입 기준 (적당히 강화)
        min_entry_score = target_config.get('min_entry_score', 22)  # 20 → 22 (적당히 상향)
        
        if data_length < 20:
            min_entry_score = max(12, min_entry_score - 8)  # 할인 폭 적당히
            entry_signals.append(f"데이터 부족으로 기준 완화 ({data_length}개)")
        
        enter_now = entry_score >= min_entry_score
        
        result = {
            'enter_now': enter_now,
            'entry_score': entry_score,
            'entry_signals': entry_signals,
            'reason': f"{'분봉 진입 타이밍 양호' if enter_now else '분봉 진입 대기'} (점수: {entry_score}/{min_entry_score})",
            'data_info': {
                'data_length': data_length,
                'rsi_period': rsi_period,
                'ma_periods': [ma_short, ma_long],
                'intraday_extreme_count': intraday_extreme_count
            }
        }
        
        logger.debug(f"{stock_code} 균형잡힌 분봉 분석 결과: {result['reason']}")
        return result
            
    except Exception as e:
        logger.error(f"균형잡힌 분봉 진입 타이밍 분석 중 오류: {str(e)}")
        # 🎯 오류 발생시 중립적 처리
        return {
            'enter_now': True,  # 분석 오류시에는 기회를 놓치지 않도록
            'entry_score': 0,
            'entry_signals': [f"분석 오류로 즉시 진입: {str(e)}"],
            'reason': '분석 오류로 즉시 진입 (기회 보존)'
        }

def should_use_intraday_timing(opportunity, target_config):
    """신호 강도별 분봉 타이밍 사용 여부 결정"""
    try:
        # 전역 설정에서 분봉 타이밍이 비활성화된 경우
        if not getattr(trading_config, 'use_intraday_timing', False):
            return False, 0, "분봉 타이밍 비활성화"
        
        daily_score = opportunity['score']
        signal_strength = opportunity.get('signal_strength', 'NORMAL')
        
        # 🎯 신호 강도별 차등 적용
        if signal_strength == 'STRONG' and daily_score >= 70:
            # 매우 강한 신호: 즉시 매수
            return False, 0, f"강력한 신호로 즉시 매수 (점수: {daily_score})"
            
        elif daily_score >= 60:
            # 강한 신호: 30분만 대기
            return True, 0.5, f"강한 신호로 30분 대기 (점수: {daily_score})"
            
        elif daily_score >= 50:
            # 중간 신호: 1시간 대기
            return True, 1.0, f"중간 신호로 1시간 대기 (점수: {daily_score})"
            
        elif daily_score >= 40:
            # 보통 신호: 2시간 대기 (기존)
            return True, 2.0, f"보통 신호로 2시간 대기 (점수: {daily_score})"
            
        else:
            # 약한 신호: 분봉 타이밍 더 엄격하게
            return True, 1.5, f"약한 신호로 1.5시간 대기 (점수: {daily_score})"
            
    except Exception as e:
        logger.error(f"분봉 타이밍 결정 중 오류: {str(e)}")
        return True, 2.0, "오류로 기본 대기"

def calculate_adaptive_stop_loss(stock_data, position, target_config):
    """적응형 손절 계산 - 변동성과 시장 환경 고려"""
    try:
        entry_price = position['entry_price']
        current_price = stock_data['current_price']
        
        # 기본 손절 비율
        base_stop_ratio = target_config.get('stop_loss', trading_config.stop_loss_ratio)
        
        # 1. 변동성 기반 조정
        atr = stock_data.get('atr', 0)
        if atr > 0:
            # ATR 기반 변동성 손절 (ATR의 1.5배)
            volatility_multiplier = target_config.get('volatility_stop_multiplier', 1.5)
            volatility_stop = (atr * volatility_multiplier) / entry_price
            
            # 변동성이 높으면 손절폭 확대
            adjusted_stop_ratio = min(base_stop_ratio, -volatility_stop)
        else:
            adjusted_stop_ratio = base_stop_ratio
        
        # 2. 시장 환경별 조정
        if trading_config.use_adaptive_strategy:
            stock_env = detect_stock_environment(stock_data['stock_code'])
            
            if stock_env == "uptrend":
                # 상승장: 손절폭 20% 확대
                adjusted_stop_ratio *= 1.2
            elif stock_env == "downtrend":
                # 하락장: 손절폭 10% 축소 (빠른 손절)
                adjusted_stop_ratio *= 0.9
            # 횡보장: 기본값 유지
        
        # 3. 보유시간 기반 조정
        entry_time = datetime.datetime.strptime(position['entry_time'], '%Y-%m-%d %H:%M:%S')
        holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
        min_holding = target_config.get('min_holding_hours', 4)
        
        # 최소 보유시간 미달시 손절 지연
        if holding_hours < min_holding:
            delay_hours = target_config.get('stop_loss_delay_hours', 2)
            if holding_hours < delay_hours:
                # 초기 2시간은 손절폭 50% 확대
                adjusted_stop_ratio *= 1.5
                logger.info(f"손절 지연 적용: {holding_hours:.1f}시간 < {delay_hours}시간")
        
        # 4. 기술적 지지선 고려
        support = stock_data.get('support', 0)
        if support > 0:
            support_based_stop = (support - entry_price) / entry_price
            # 지지선이 기본 손절선보다 낮으면 지지선 기준 사용
            if support_based_stop < adjusted_stop_ratio:
                adjusted_stop_ratio = min(adjusted_stop_ratio, support_based_stop * 0.98)  # 지지선 2% 아래
                logger.info(f"지지선 기반 손절 적용: {support:,.0f}원")
        
        # 5. 최대/최소 손절 한계 설정
        max_stop_ratio = -0.08  # 최대 8% 손절
        min_stop_ratio = -0.02  # 최소 2% 손절
        adjusted_stop_ratio = max(max_stop_ratio, min(min_stop_ratio, adjusted_stop_ratio))
        
        logger.debug(f"적응형 손절 계산: {base_stop_ratio:.1%} → {adjusted_stop_ratio:.1%}")
        
        return adjusted_stop_ratio
        
    except Exception as e:
        logger.error(f"적응형 손절 계산 중 오류: {str(e)}")
        return target_config.get('stop_loss', trading_config.stop_loss_ratio)

def analyze_sell_signal(stock_data, position, target_config):
    """개선된 매도 신호 분석 - 자본 보호 우선 손절"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position.get('entry_price', 0)
        
        if entry_price <= 0:
            return {'is_sell_signal': False, 'sell_type': None, 'reason': 'entry_price 정보 없음'}
        
        profit_rate = (current_price - entry_price) / entry_price
        entry_signal_strength = position.get('signal_strength', 'NORMAL')
        
        # 🚨 1단계: 긴급 매도 (기준 강화)
        df = stock_data.get('ohlcv_data')
        if df is not None and len(df) >= 3:
            daily_drop = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100
            if daily_drop < -10:  # -15% → -10% (더 엄격하게)
                return {
                    'is_sell_signal': True,
                    'sell_type': 'emergency_exit',
                    'reason': f"급락 긴급매도 {daily_drop:.1f}%",
                    'urgent': True
                }
        
        # 🎯 2단계: 익절 로직 (기존 유지 - 좋음)
        if entry_signal_strength == 'STRONG':
            profit_targets = {
                'quick': 0.08,      # 8% 빠른 익절
                'normal': 0.15,     # 15% 일반 익절  
                'extended': 0.25    # 25% 확장 익절
            }
        else:
            profit_targets = {
                'quick': 0.06,      # 6% 빠른 익절
                'normal': 0.12,     # 12% 일반 익절
                'extended': 0.20    # 20% 확장 익절
            }
        
        # RSI와 볼린저밴드 과열 확인
        rsi = stock_data.get('rsi', 50)
        bb_upper = stock_data.get('bb_upper', 0)
        
        is_overheated = (rsi >= 80) or (bb_upper > 0 and current_price >= bb_upper)
        is_very_overheated = (rsi >= 85) or (bb_upper > 0 and current_price >= bb_upper * 1.02)
        
        # 익절 실행
        if profit_rate >= profit_targets['quick']:
            if is_very_overheated:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'quick_profit_overheated',
                    'reason': f"과열상태 빠른익절 {profit_rate*100:.1f}%",
                    'urgent': False
                }
            elif profit_rate >= profit_targets['normal'] and is_overheated:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'normal_profit_overheated',
                    'reason': f"과열상태 일반익절 {profit_rate*100:.1f}%",
                    'urgent': False
                }
        
        if profit_rate >= profit_targets['extended']:
            return {
                'is_sell_signal': True,
                'sell_type': 'extended_profit',
                'reason': f"확장목표 달성 {profit_rate*100:.1f}%",
                'urgent': False
            }
        
        # 보유시간 계산
        holding_hours = 0
        try:
            entry_time_str = position.get('entry_time', '')
            if entry_time_str:
                if len(entry_time_str) > 10:
                    try:
                        entry_time = datetime.datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        entry_time = datetime.datetime.strptime(entry_time_str, '%Y-%m-%d')
                else:
                    entry_time = datetime.datetime.strptime(entry_time_str, '%Y-%m-%d')
                holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
        except:
            holding_days = position.get('holding_days', 0)
            holding_hours = holding_days * 24
        
        # 🔥 3단계: 개선된 손절 로직 - 자본 보호 우선
        
        # 신호별 손절 기준 (대폭 강화)
        if entry_signal_strength == 'STRONG':
            base_stop_loss = -0.08  # -18% → -8% (대폭 강화)
        else:
            base_stop_loss = -0.06  # -15% → -6% (대폭 강화)
        
        # 🎯 시간별 손절 로직 (대폭 단축)
        if holding_hours < 2:  # 6시간 → 2시간 (대폭 단축)
            # 극한 상황 손절 기준 강화
            if profit_rate <= -0.12:  # -25% → -12% (대폭 강화)
                return {
                    'is_sell_signal': True,
                    'sell_type': 'emergency_stop_loss',
                    'reason': f"극한상황 손절 {profit_rate*100:.1f}% (보유 {holding_hours:.1f}시간)",
                    'urgent': True
                }
            else:
                return {
                    'is_sell_signal': False,
                    'sell_type': None,
                    'reason': f"초기보유 손절지연 {profit_rate*100:.1f}% (보유 {holding_hours:.1f}시간)",
                    'urgent': False
                }
        
        elif holding_hours < 12:  # 24시간 → 12시간 (단축)
            # 손절 기준 20% 완화 (50% → 20%)
            adjusted_stop_loss = base_stop_loss * 1.2
        elif holding_hours < 24:  # 72시간 → 24시간 (대폭 단축)
            # 손절 기준 10% 완화 (25% → 10%)
            adjusted_stop_loss = base_stop_loss * 1.1
        else:
            # 기본 손절 기준 적용
            adjusted_stop_loss = base_stop_loss
        
        # 🔥 4단계: RSI 기반 손절 지연 (조건 대폭 강화)
        if profit_rate <= adjusted_stop_loss:
            # 🎯 극도 과매도에서만 지연 (조건 대폭 강화)
            if rsi <= 20:  # 25 → 20 (더 극한 상황에만)
                # 추가 조건: 볼린저밴드 하단 -3% 돌파시에만
                if current_price <= stock_data.get('bb_lower', 0) * 0.97:  # 3% 아래만
                    return {
                        'is_sell_signal': False,
                        'sell_type': None,
                        'reason': f"극도과매도+볼밴하단 손절지연 {profit_rate*100:.1f}% (RSI: {rsi:.1f})",
                        'urgent': False
                    }
            
            # 🔥 기본: 즉시 손절 실행 (지연 조건 대폭 축소)
            return {
                'is_sell_signal': True,
                'sell_type': 'improved_stop_loss',
                'reason': f"자본보호 손절 {profit_rate*100:.1f}% (기준: {adjusted_stop_loss*100:.1f}%)",
                'urgent': True
            }
        
        # 🔄 5단계: 트레일링 스탑 (조건 강화)
        trailing_stop = target_config.get('trailing_stop', 0.03)  # 4% → 3% (강화)
        high_price = position.get('high_price', entry_price)
        
        if high_price > entry_price and profit_rate > 0.04:  # 5% → 4% (기준 낮춤)
            trailing_loss = (high_price - current_price) / high_price
            
            # 수익률별 차등 트레일링 (더 타이트하게)
            if profit_rate > 0.20:  # 20% 이상 수익시
                adjusted_trailing = trailing_stop * 0.5  # 0.6 → 0.5 (더 타이트)
            elif profit_rate > 0.15:  # 15% 이상 수익시
                adjusted_trailing = trailing_stop * 0.7  # 0.8 → 0.7 (더 타이트)
            elif profit_rate > 0.10:  # 10% 이상 수익시
                adjusted_trailing = trailing_stop * 0.9  # 1.0 → 0.9 (더 타이트)
            else:
                adjusted_trailing = trailing_stop * 1.1  # 1.3 → 1.1 (덜 관대)
            
            if trailing_loss >= adjusted_trailing:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop',
                    'reason': f"트레일링스탑 {trailing_loss*100:.1f}% (수익: {profit_rate*100:.1f}%)",
                    'urgent': True
                }
        
        # 🎯 6단계: 추세 반전 감지 매도 (기준 강화)
        ma5 = stock_data.get('ma5', 0)
        ma20 = stock_data.get('ma20', 0)
        
        # 수익 상태에서 추세 반전시 매도 (기준 낮춤)
        if profit_rate > 0.02:  # 3% → 2% (기준 낮춤)
            if ma5 < ma20 * 0.985:  # 0.98 → 0.985 (더 민감하게)
                if rsi < 45:  # 40 → 45 (더 민감하게)
                    return {
                        'is_sell_signal': True,
                        'sell_type': 'trend_reversal',
                        'reason': f"추세반전 매도 {profit_rate*100:.1f}% (MA5<MA20, RSI약세)",
                        'urgent': False
                    }
        
        # 🔥 7단계: 추가 안전장치 - 연속 하락 손절
        if len(df) >= 3:
            # 최근 3일 연속 하락 + 손실 상태면 매도
            recent_changes = df['close'].pct_change().iloc[-3:]
            consecutive_down = sum(1 for x in recent_changes if x < -0.02)  # 2% 이상 하락
            
            if consecutive_down >= 2 and profit_rate < -0.03:  # 연속 하락 + 3% 손실
                return {
                    'is_sell_signal': True,
                    'sell_type': 'consecutive_decline',
                    'reason': f"연속하락 안전매도 {profit_rate*100:.1f}% (연속하락 {consecutive_down}일)",
                    'urgent': True
                }
        
        # 기본: 보유 지속
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"보유지속 (수익률: {profit_rate*100:.1f}%, 보유: {holding_hours:.1f}시간)",
            'urgent': False,
            'profit_rate': profit_rate,
            'holding_hours': holding_hours
        }
        
    except Exception as e:
        logger.error(f"개선된 매도 신호 분석 중 에러: {str(e)}")
        return {'is_sell_signal': False, 'sell_type': None, 'reason': f'분석 오류: {str(e)}'}

def analyze_intraday_entry_timing(stock_code, target_config):
    """분봉 기준 최적 진입 타이밍 분석 - API 호출 방식 수정"""
    try:
        # 🔥 KIS API 정확한 사용법으로 수정
        try:
            # 방법 1: KisKR.GetOhlcvNew 사용 (분봉)
            # 'M' = 분봉, 개수, adj_ok=1 (수정주가 적용)
            df_5m = KisKR.GetOhlcvNew(stock_code, 'M', 24, adj_ok=1)
            
            if df_5m is None or len(df_5m) < 10:
                logger.debug(f"KisKR.GetOhlcvNew 분봉 조회 실패: {stock_code}")
                
                # 방법 2: Common.GetOhlcv 기본 호출 (일봉을 짧게)
                df_5m = Common.GetOhlcv("KR", stock_code, 24)  # period 파라미터 제거
                
        except Exception as api_e:
            logger.debug(f"분봉 API 호출 실패: {str(api_e)}, 일봉으로 대체")
            # 방법 3: 일봉 데이터로 대체 (기존 방식)
            df_5m = Common.GetOhlcv("KR", stock_code, 24)
        
        if df_5m is None or len(df_5m) < 10:
            logger.debug(f"모든 데이터 조회 실패: {stock_code}")
            return {'enter_now': True, 'reason': '데이터 부족으로 즉시 진입'}
        
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price:
            return {'enter_now': True, 'reason': '현재가 조회 실패로 즉시 진입'}
        
        # 🔥 데이터 길이에 따른 적응적 분석
        data_length = len(df_5m)
        logger.debug(f"{stock_code} 데이터 길이: {data_length}")
        
        # 기술적 지표 계산 (데이터 길이에 맞게 조정)
        rsi_period = min(14, data_length // 2)
        ma_short = min(5, data_length // 4)
        ma_long = min(20, data_length // 2)
        bb_period = min(20, data_length // 2)
        
        if rsi_period < 3:
            return {'enter_now': True, 'reason': '데이터 부족으로 즉시 진입'}
        
        # 기술적 지표 계산
        df_5m['RSI'] = TechnicalIndicators.calculate_rsi(df_5m, rsi_period)
        df_5m['MA_Short'] = df_5m['close'].rolling(window=ma_short).mean()
        df_5m['MA_Long'] = df_5m['close'].rolling(window=ma_long).mean()
        
        # 볼린저밴드 (데이터가 충분할 때만)
        if data_length >= bb_period:
            bb_data = TechnicalIndicators.calculate_bollinger_bands(df_5m, bb_period, 2.0)
            df_5m[['BB_Mid', 'BB_Upper', 'BB_Lower']] = bb_data
        else:
            # 볼린저밴드 계산 불가시 더미 값
            df_5m['BB_Mid'] = df_5m['close']
            df_5m['BB_Upper'] = df_5m['close'] * 1.02
            df_5m['BB_Lower'] = df_5m['close'] * 0.98
        
        entry_signals = []
        entry_score = 0
        
        # 🎯 1) RSI 기반 신호
        try:
            rsi_current = df_5m['RSI'].iloc[-1]
            if not pd.isna(rsi_current):
                if rsi_current <= 30:
                    entry_score += 30
                    entry_signals.append(f"RSI 과매도 {rsi_current:.1f} (+30)")
                elif rsi_current <= 40:
                    entry_score += 20
                    entry_signals.append(f"RSI 조정 {rsi_current:.1f} (+20)")
                elif rsi_current >= 70:
                    entry_score -= 20
                    entry_signals.append(f"RSI 과매수 {rsi_current:.1f} (-20)")
        except:
            pass
        
        # 🎯 2) 볼린저밴드 기반 신호
        try:
            bb_lower = df_5m['BB_Lower'].iloc[-1]
            bb_upper = df_5m['BB_Upper'].iloc[-1]
            
            if not pd.isna(bb_lower) and current_price <= bb_lower * 1.02:
                entry_score += 25
                entry_signals.append("볼린저 하단 근접 (+25)")
            elif not pd.isna(bb_upper) and current_price >= bb_upper * 0.98:
                entry_score -= 15
                entry_signals.append("볼린저 상단 근접 (-15)")
        except:
            pass
        
        # 🎯 3) 이동평균선 지지
        try:
            ma_short_current = df_5m['MA_Short'].iloc[-1]
            if not pd.isna(ma_short_current):
                distance_ratio = abs(current_price - ma_short_current) / ma_short_current
                if distance_ratio <= 0.01:  # 1% 이내
                    entry_score += 20
                    entry_signals.append(f"{ma_short}MA 지지 (+20)")
        except:
            pass
        
        # 🎯 4) 거래량 신호
        try:
            if data_length >= 10:
                recent_volume = df_5m['volume'].iloc[-3:].mean()
                past_volume = df_5m['volume'].iloc[-10:-3].mean()
                
                if past_volume > 0:
                    volume_ratio = recent_volume / past_volume
                    if volume_ratio >= 1.2:
                        entry_score += 15
                        entry_signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+15)")
        except:
            pass
        
        # 🎯 5) 가격 추세 신호
        try:
            if data_length >= 5:
                # 최근 변화율 계산
                recent_changes = df_5m['close'].pct_change().iloc[-4:]
                down_count = sum(1 for x in recent_changes if x < -0.01)  # 1% 이상 하락
                last_change = df_5m['close'].pct_change().iloc[-1]
                
                if down_count >= 2 and last_change > 0.005:  # 연속 하락 후 반등
                    entry_score += 20
                    entry_signals.append("반등 신호 (+20)")
                
                # 고점 근처 체크
                recent_high = df_5m['high'].iloc[-min(10, data_length):].max()
                if current_price >= recent_high * 0.98:
                    entry_score -= 10
                    entry_signals.append("단기 고점 근처 (-10)")
        except:
            pass
        
        # 🎯 진입 결정
        min_entry_score = target_config.get('min_entry_score', 20)  # 기준 완화
        
        # 데이터 부족시 기준 완화
        if data_length < 20:
            min_entry_score = max(10, min_entry_score - 10)
            entry_signals.append(f"데이터 부족으로 기준 완화 ({data_length}개)")
        
        enter_now = entry_score >= min_entry_score
        
        result = {
            'enter_now': enter_now,
            'entry_score': entry_score,
            'entry_signals': entry_signals,
            'reason': f"{'진입 타이밍 양호' if enter_now else '진입 대기'} (점수: {entry_score}/{min_entry_score})",
            'data_info': {
                'data_length': data_length,
                'rsi_period': rsi_period,
                'ma_periods': [ma_short, ma_long]
            }
        }
        
        logger.debug(f"{stock_code} 분봉 분석 결과: {result['reason']}")
        return result
            
    except Exception as e:
        logger.error(f"분봉 진입 타이밍 분석 중 오류: {str(e)}")
        # 오류 발생시에도 매수 기회를 놓치지 않도록 즉시 진입
        return {
            'enter_now': True, 
            'entry_score': 0,
            'entry_signals': [f"분석 오류: {str(e)}"],
            'reason': '분석 오류로 즉시 진입'
        }
    
################################### 상태 관리 ##################################

def load_trading_state():
    """트레이딩 상태 로드 - pending_orders 필드 추가"""
    try:
        bot_name = get_bot_name()
        with open(f"TargetStockBot_{bot_name}.json", 'r') as f:
            state = json.load(f)
        
        # 🆕 pending_orders 필드 추가 (라이브러리 사용)
        state = enhance_trading_state(state)
        return state
        
    except:
        return enhance_trading_state({
            'positions': {},
            'daily_stats': {
                'date': '',
                'total_profit': 0,
                'total_trades': 0,
                'winning_trades': 0,
                'start_balance': 0
            }
        })

def save_trading_state(state):
    """트레이딩 상태 저장"""
    bot_name = get_bot_name()
    with open(f"TargetStockBot_{bot_name}.json", 'w') as f:
        json.dump(state, f, indent=2)

################################### 매매 실행 ##################################

def calculate_position_size(target_config, stock_code, stock_price, trading_state):
    """포지션 크기 계산 - 종목별 예산 한도 적용 (개선됨)"""
    try:
        if stock_price <= 0:
            return 0
        
        # 1. 종목별 남은 예산 확인
        remaining_budget_for_stock = get_remaining_budget_for_stock(stock_code, trading_state)
        
        if remaining_budget_for_stock <= 0:
            stock_name = target_config.get('name', stock_code)
            logger.info(f"❌ {stock_name}({stock_code}): 종목별 예산 한도 초과 (남은예산: {remaining_budget_for_stock:,.0f}원)")
            return 0
        
        # 2. 전체 사용 가능 예산 확인
        total_available_budget = get_available_budget(trading_state)
        
        if total_available_budget <= 0:
            logger.info("❌ 전체 사용 가능 예산 부족")
            return 0
        
        # 3. 실제 사용할 예산 결정 (둘 중 작은 값)
        usable_budget = min(remaining_budget_for_stock, total_available_budget)
        
        # 4. 기본 배분율 적용
        base_allocation = get_safe_config_value(target_config, 'allocation_ratio', 0.35)
        
        # 5. 신호 강도별 배분 조정
        signal_strength = target_config.get('last_signal_strength', 'NORMAL')
        if signal_strength == 'STRONG':
            strength_multiplier = 1.2  # 20% 증가 (기존 40%에서 축소)
        else:
            strength_multiplier = 1.0   # 기본값
        
        # 6. 최종 배분 예산 계산
        enhanced_allocation = base_allocation * strength_multiplier
        allocated_budget = usable_budget * enhanced_allocation
        
        # 7. 최소 주문 금액 체크
        min_order_amount = get_safe_config_value(target_config, 'min_order_amount', 10000)
        if allocated_budget < min_order_amount:
            return 0
        
        # 8. 기본 수량 계산
        base_quantity = int(allocated_budget / stock_price)

        # 🆕 임시 디버깅 로그 추가
        stock_name = target_config.get('name', stock_code)
        logger.info(f"🔍 임시 디버깅 - {stock_name}({stock_code}): 사용예산 {usable_budget:,}원, 배분율 {enhanced_allocation*100:.1f}%, 배분예산 {allocated_budget:,}원, 현재가 {stock_price:,}원, 계산수량 {base_quantity}주, 최소주문금액 {min_order_amount:,}원")
            
        if base_quantity <= 0:
            return 0
        
        # 9. 수수료 고려한 조정
        estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
        total_needed = (stock_price * base_quantity) + estimated_fee
        
        # 예산 내에서 수량 조정
        while total_needed > allocated_budget and base_quantity > 0:
            base_quantity -= 1
            if base_quantity > 0:
                estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
                total_needed = (stock_price * base_quantity) + estimated_fee
            else:
                break
        
        if base_quantity <= 0:
            return 0
        
        # 10. 최종 검증
        final_amount = stock_price * base_quantity
        final_fee = calculate_trading_fee(stock_price, base_quantity, True)
        final_total = final_amount + final_fee
        
        # 🎯 추가 검증: 종목별 한도 재확인
        current_invested = get_invested_amount_for_stock(stock_code, trading_state)
        per_stock_limit = get_per_stock_budget_limit()
        
        if (current_invested + final_total) > per_stock_limit * 1.01:  # 1% 여유 허용
            logger.warning(f"⚠️ 종목별 한도 초과 위험: {current_invested + final_total:,.0f}원 > {per_stock_limit:,.0f}원")
            return 0
        
        stock_name = target_config.get('name', stock_code)
        logger.info(f"🎯 개선된 포지션 계산: {stock_name}({stock_code})")
        logger.info(f"   종목별 남은예산: {remaining_budget_for_stock:,.0f}원")
        logger.info(f"   배분율: {enhanced_allocation*100:.1f}% (기본: {base_allocation*100:.1f}% × {strength_multiplier:.2f})")
        logger.info(f"   최종 수량: {base_quantity}주 ({final_total:,.0f}원)")
        logger.info(f"   투자 후 종목별 총투자: {current_invested + final_total:,.0f}원 / {per_stock_limit:,.0f}원")
        
        return base_quantity
        
    except Exception as e:
        logger.error(f"개선된 포지션 계산 중 에러: {str(e)}")
        return 0

def execute_buy_order(stock_code, target_config, quantity, price):
    """매수 주문 실행 - 미체결 주문 추적 추가"""
    try:
        stock_name = target_config.get('name', stock_code)
        trading_state = load_trading_state()
        
        # 🆕 1. 중복 주문 방지 (라이브러리 사용)
        if pending_manager.check_pending_orders(stock_code, trading_state):
            logger.warning(f"❌ 중복 주문 방지: {stock_name}({stock_code}) - 이미 미체결 주문 있음")
            return None, None
        
        # 🆕 2. 주문 추적 시작 (라이브러리 사용)
        order_info = {
            'quantity': quantity,
            'price': price,
            'target_config': target_config,
            'signal_strength': target_config.get('last_signal_strength', 'NORMAL'),
            'daily_score': target_config.get('last_signal_score', 0)
        }
        
        pending_manager.track_pending_order(trading_state, stock_code, order_info)
        save_trading_state(trading_state)
        
        # 🆕 3. 주문 접수 알림 (라이브러리 사용)
        order_amount = quantity * price
        estimated_fee = calculate_trading_fee(price, quantity, True)
        
        order_info['order_amount'] = order_amount
        order_info['estimated_fee'] = estimated_fee
        pending_manager.send_order_alert('submit', stock_code, order_info)
        
        # 4. 실제 주문 실행 (기존 로직)
        logger.info(f"{stock_name}({stock_code}) 매수 주문: {quantity}주 @ {price:,.0f}원")
        
        order_result = KisKR.MakeBuyLimitOrder(stock_code, quantity, int(price))
        
        if not order_result or isinstance(order_result, str):
            # 🆕 주문 실패시 pending 제거 (라이브러리 사용)
            trading_state = load_trading_state()
            pending_manager.remove_pending_order(trading_state, stock_code, "주문 실패")
            save_trading_state(trading_state)
            
            error_msg = f"❌ 매수 주문 실패: {stock_name}({stock_code}) - {order_result}"
            logger.error(error_msg)
            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                discord_alert.SendMessage(error_msg)
            return None, None
        
        # 5. 주문 성공시 order_id 업데이트
        if isinstance(order_result, dict):
            order_id = order_result.get('OrderNum', order_result.get('OrderNo', ''))
            if order_id:
                trading_state = load_trading_state()
                if stock_code in trading_state.get('pending_orders', {}):
                    trading_state['pending_orders'][stock_code]['order_id'] = order_id
                    trading_state['pending_orders'][stock_code]['status'] = 'submitted'
                    save_trading_state(trading_state)
                    logger.info(f"📋 주문번호 등록: {stock_name}({stock_code}) - {order_id}")
        
        # 6. 체결 확인 (기존 로직)
        start_time = time.time()
        while time.time() - start_time < 60:
            my_stocks = KisKR.GetMyStockList()
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    executed_amount = int(stock.get('StockAmt', 0))
                    if executed_amount > 0:
                        avg_price = float(stock.get('AvrPrice', price))
                        
                        # 🆕 체결 완료시 pending 제거 (라이브러리 사용)
                        trading_state = load_trading_state()
                        pending_manager.remove_pending_order(trading_state, stock_code, "체결 완료")
                        save_trading_state(trading_state)
                        
                        # 🆕 체결 완료 알림 (라이브러리 사용)
                        pending_manager.send_order_alert('fill', stock_code, {
                            'executed_price': avg_price,
                            'executed_amount': executed_amount
                        })
                        
                        logger.info(f"매수 체결 확인: {executed_amount}주 @ {avg_price:,.0f}원")
                        return avg_price, executed_amount
            time.sleep(3)
        
        # 🆕 미체결시 알림 (라이브러리 사용)
        logger.warning(f"체결 확인 실패: {stock_code}")
        pending_manager.send_order_alert('pending', stock_code, order_info)
        
        return None, None
        
    except Exception as e:
        # 🆕 예외 발생시 pending 정리 (라이브러리 사용)
        try:
            trading_state = load_trading_state()
            pending_manager.remove_pending_order(trading_state, stock_code, f"오류 발생: {str(e)}")
            save_trading_state(trading_state)
        except:
            pass
        
        logger.error(f"매수 주문 실행 중 에러: {str(e)}")
        return None, None

def process_buy_candidates(trading_state):
    """매수 대기 후보들의 진입 타이밍 재확인 - 신호별 대기시간 + 강제매수 로직"""
    try:
        if 'buy_candidates' not in trading_state:
            return trading_state
        
        if not trading_state['buy_candidates']:
            return trading_state
        
        logger.info("🔄 매수 대기 후보 관리 시작")
        logger.info(f"📋 현재 대기 종목: {len(trading_state['buy_candidates'])}개")
        
        candidates_to_remove = []
        candidates_executed = []
        candidates_expired = []
        
        for stock_code, candidate_info in trading_state['buy_candidates'].items():
            try:
                # 기본 정보 추출
                opportunity = candidate_info['opportunity']
                stock_name = opportunity['stock_name']
                daily_score = candidate_info.get('daily_score', 0)
                signal_strength = candidate_info.get('signal_strength', 'NORMAL')
                timing_reason = candidate_info.get('timing_reason', '알 수 없음')
                
                # 대기 시간 계산
                wait_start = datetime.datetime.fromisoformat(candidate_info['wait_start_time'])
                wait_hours = (datetime.datetime.now() - wait_start).total_seconds() / 3600
                wait_minutes = wait_hours * 60
                max_wait_hours = candidate_info.get('max_wait_hours', 2.0)
                
                logger.info(f"\n🔍 대기 종목 검토: {stock_name}({stock_code})")
                logger.info(f"   대기시간: {wait_minutes:.0f}분 / {max_wait_hours*60:.0f}분")
                logger.info(f"   일봉점수: {daily_score}점 ({signal_strength})")
                logger.info(f"   대기전략: {timing_reason}")
                
                # 🕐 대기 시간 초과 체크
                if wait_hours > max_wait_hours:
                    logger.info(f"   ⏰ 대기 시간 초과!")
                    
                    # 🎯 강제 매수 여부 결정 (신호 강도별)
                    should_force_buy = False
                    force_reason = ""
                    
                    if signal_strength == 'STRONG':
                        # 강한 신호는 항상 강제 매수
                        should_force_buy = True
                        force_reason = "강한 신호로 강제 매수"
                        
                    elif daily_score >= 60:
                        # 60점 이상은 강제 매수
                        should_force_buy = True
                        force_reason = f"고점수({daily_score}점)로 강제 매수"
                        
                    elif daily_score >= 50:
                        # 50점 이상은 조건부 강제 매수 (현재 RSI 체크)
                        try:
                            current_price = KisKR.GetCurrentPrice(stock_code)
                            stock_data = get_stock_data(stock_code)
                            if stock_data and stock_data.get('rsi', 50) <= 40:
                                should_force_buy = True
                                force_reason = f"중간점수({daily_score}점) + RSI과매도({stock_data['rsi']:.1f})로 강제 매수"
                            else:
                                force_reason = f"중간점수({daily_score}점)지만 RSI({stock_data.get('rsi', 50):.1f})로 매수 포기"
                        except:
                            force_reason = f"중간점수({daily_score}점)지만 데이터 오류로 매수 포기"
                            
                    elif daily_score >= 40:
                        # 40점대는 매수 포기
                        force_reason = f"보통점수({daily_score}점)로 매수 포기"
                        
                    else:
                        # 40점 미만은 매수 포기 (실제로는 발생하지 않음)
                        force_reason = f"낮은점수({daily_score}점)로 매수 포기"
                    
                    logger.info(f"   🎯 강제매수 결정: {force_reason}")
                    
                    if should_force_buy:
                        # 💰 예산 재확인
                        remaining_budget = get_remaining_budget_for_stock(stock_code, trading_state)
                        total_available_budget = get_available_budget(trading_state)
                        
                        if remaining_budget <= 10000 or total_available_budget <= 10000:
                            logger.info(f"   ❌ 예산 부족으로 강제매수 불가")
                            logger.info(f"      종목별 예산: {remaining_budget:,.0f}원")
                            logger.info(f"      전체 예산: {total_available_budget:,.0f}원")
                            candidates_expired.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name, 
                                'reason': '예산 부족',
                                'daily_score': daily_score,
                                'wait_time': wait_hours
                            })
                        else:
                            # 🚀 강제 매수 실행
                            logger.info(f"   🚀 강제 매수 실행 시작")
                            
                            target_config = opportunity['target_config']
                            stock_price = opportunity['price']
                            
                            # 현재가 재확인
                            try:
                                current_price = KisKR.GetCurrentPrice(stock_code)
                                if current_price and current_price > 0:
                                    stock_price = current_price
                                    logger.info(f"      현재가 업데이트: {stock_price:,.0f}원")
                            except:
                                logger.warning(f"      현재가 조회 실패, 기존 가격 사용: {stock_price:,.0f}원")
                            
                            # 포지션 크기 계산
                            quantity = calculate_position_size(target_config, stock_code, stock_price, trading_state)
                            
                            if quantity < 1:
                                logger.info(f"   ❌ 매수 수량 부족 (계산수량: {quantity})")
                                candidates_expired.append({
                                    'stock_code': stock_code,
                                    'stock_name': stock_name,
                                    'reason': '수량 부족',
                                    'daily_score': daily_score,
                                    'wait_time': wait_hours
                                })
                            else:
                                # 📝 매수 실행
                                logger.info(f"      수량: {quantity}주, 가격: {stock_price:,.0f}원")
                                
                                executed_price, executed_amount = execute_buy_order(
                                    stock_code, target_config, quantity, stock_price
                                )
                                
                                if executed_price and executed_amount:
                                    # ✅ 매수 성공
                                    buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                                    actual_investment = executed_price * executed_amount
                                    
                                    logger.info(f"   ✅ 강제 매수 성공!")
                                    logger.info(f"      체결가: {executed_price:,.0f}원")
                                    logger.info(f"      체결량: {executed_amount}주")
                                    logger.info(f"      투자금액: {actual_investment:,.0f}원")
                                    
                                    # 포지션 정보 저장
                                    position_info = {
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'entry_price': executed_price,
                                        'amount': executed_amount,
                                        'buy_fee': buy_fee,
                                        'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        'high_price': executed_price,
                                        'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', trading_config.trailing_stop_ratio)),
                                        'target_config': target_config,
                                        'buy_analysis': opportunity['analysis'],
                                        'signal_strength': signal_strength,
                                        'daily_score': daily_score,
                                        'entry_method': 'forced_buy_after_wait',  # 🔥 강제매수 표시
                                        'wait_time_hours': wait_hours,
                                        'force_reason': force_reason
                                    }
                                    
                                    trading_state['positions'][stock_code] = position_info
                                    
                                    # 성공 기록
                                    candidates_executed.append({
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'executed_price': executed_price,
                                        'executed_amount': executed_amount,
                                        'investment_amount': actual_investment,
                                        'daily_score': daily_score,
                                        'signal_strength': signal_strength,
                                        'wait_time': wait_hours,
                                        'force_reason': force_reason
                                    })
                                    
                                    # 🎉 Discord 알림
                                    msg = f"⏰ 대기 후 강제 매수: {stock_name}({stock_code})\n"
                                    msg += f"매수가: {executed_price:,.0f}원 × {executed_amount}주\n"
                                    msg += f"투자금액: {actual_investment:,.0f}원\n"
                                    msg += f"대기시간: {wait_hours:.1f}시간\n"
                                    msg += f"일봉점수: {daily_score}점 ({signal_strength})\n"
                                    msg += f"매수사유: {force_reason}"

                                    # 🆕 뉴스 분석 정보 추가
                                    if opportunity.get('news_impact'):
                                        news_impact = opportunity['news_impact']
                                        decision = news_impact.get('decision', 'NEUTRAL')
                                        percentage = news_impact.get('percentage', 0)
                                        reason = news_impact.get('reason', '')
                                        
                                        msg += f"\n📰 뉴스 분석:\n"
                                        if decision == 'POSITIVE':
                                            msg += f"• ✅ 긍정 뉴스 ({percentage}% 신뢰도)\n"
                                            if reason:
                                                msg += f"• 내용: {reason[:80]}...\n"
                                        elif decision == 'NEGATIVE': 
                                            msg += f"• ❌ 부정 뉴스 ({percentage}% 신뢰도)\n"
                                            if reason:
                                                msg += f"• 내용: {reason[:80]}...\n"
                                        else:
                                            msg += f"• ⚪ 중립 뉴스 (영향 없음)\n"
                                    
                                    logger.info(msg)
                                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                                        discord_alert.SendMessage(msg)
                                        
                                else:
                                    # ❌ 매수 실패
                                    logger.error(f"   ❌ 강제 매수 실패")
                                    candidates_expired.append({
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'reason': '주문 실패',
                                        'daily_score': daily_score,
                                        'wait_time': wait_hours
                                    })
                    else:
                        # 📉 매수 포기
                        candidates_expired.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'reason': force_reason,
                            'daily_score': daily_score,
                            'wait_time': wait_hours
                        })
                    
                    # 대기 목록에서 제거
                    candidates_to_remove.append(stock_code)
                    continue
                
                # 🔍 아직 대기 시간 내: 분봉 진입 타이밍 재확인
                logger.info(f"   🕐 대기 시간 내: 분봉 타이밍 재확인")
                
                target_config = opportunity['target_config']
                timing_analysis = analyze_intraday_entry_timing(stock_code, target_config)
                
                current_intraday_score = timing_analysis.get('entry_score', 0)
                min_intraday_score = candidate_info.get('min_intraday_score', 20)
                previous_intraday_score = candidate_info.get('last_intraday_score', 0)
                
                logger.info(f"   분봉 점수: {current_intraday_score}/{min_intraday_score}점 (이전: {previous_intraday_score}점)")
                
                # 점수 변화 분석
                score_change = current_intraday_score - previous_intraday_score
                if score_change != 0:
                    change_direction = "상승" if score_change > 0 else "하락"
                    logger.info(f"   점수 변화: {score_change:+d}점 ({change_direction})")
                
                if timing_analysis['enter_now']:
                    # 🎯 분봉 타이밍 도래!
                    logger.info(f"   🎯 분봉 진입 타이밍 도래!")
                    logger.info(f"      사유: {timing_analysis['reason']}")
                    logger.info(f"      대기시간: {wait_hours:.1f}시간")
                    
                    # 분봉 신호 출력
                    if timing_analysis.get('entry_signals'):
                        logger.info(f"      분봉 신호:")
                        for signal in timing_analysis['entry_signals'][:3]:
                            logger.info(f"        - {signal}")
                    
                    # 💰 예산 재확인
                    remaining_budget = get_remaining_budget_for_stock(stock_code, trading_state)
                    total_available_budget = get_available_budget(trading_state)
                    
                    if remaining_budget <= 10000 or total_available_budget <= 10000:
                        logger.info(f"   ❌ 예산 부족으로 매수 불가")
                        candidates_expired.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'reason': '예산 부족 (분봉 타이밍)',
                            'daily_score': daily_score,
                            'wait_time': wait_hours
                        })
                        candidates_to_remove.append(stock_code)
                        continue
                    
                    # 📝 매수 실행
                    target_config = opportunity['target_config']
                    stock_price = opportunity['price']
                    
                    # 현재가 재확인
                    try:
                        current_price = KisKR.GetCurrentPrice(stock_code)
                        if current_price and current_price > 0:
                            stock_price = current_price
                    except:
                        pass
                    
                    quantity = calculate_position_size(target_config, stock_code, stock_price, trading_state)
                    
                    if quantity < 1:
                        logger.info(f"   ❌ 매수 수량 부족")
                        candidates_expired.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'reason': '수량 부족 (분봉 타이밍)',
                            'daily_score': daily_score,
                            'wait_time': wait_hours
                        })
                    else:
                        logger.info(f"   🔵 분봉 타이밍 매수 실행")
                        
                        executed_price, executed_amount = execute_buy_order(
                            stock_code, target_config, quantity, stock_price
                        )
                        
                        if executed_price and executed_amount:
                            # ✅ 매수 성공
                            buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                            actual_investment = executed_price * executed_amount
                            
                            logger.info(f"   ✅ 분봉 타이밍 매수 성공!")
                            
                            # 포지션 정보 저장
                            position_info = {
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'entry_price': executed_price,
                                'amount': executed_amount,
                                'buy_fee': buy_fee,
                                'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'high_price': executed_price,
                                'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', trading_config.trailing_stop_ratio)),
                                'target_config': target_config,
                                'buy_analysis': opportunity['analysis'],
                                'signal_strength': signal_strength,
                                'daily_score': daily_score,
                                'entry_method': 'intraday_timing_after_wait',
                                'wait_time_hours': wait_hours,
                                'intraday_analysis': timing_analysis,
                                'intraday_score': current_intraday_score
                            }
                            
                            trading_state['positions'][stock_code] = position_info
                            
                            # 성공 기록
                            candidates_executed.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'executed_price': executed_price,
                                'executed_amount': executed_amount,
                                'investment_amount': actual_investment,
                                'daily_score': daily_score,
                                'signal_strength': signal_strength,
                                'wait_time': wait_hours,
                                'intraday_score': current_intraday_score,
                                'entry_method': '분봉 타이밍'
                            })
                            
                            # 🎉 Discord 알림
                            msg = f"🎯 분봉 타이밍 매수: {stock_name}({stock_code})\n"
                            msg += f"매수가: {executed_price:,.0f}원 × {executed_amount}주\n"
                            msg += f"투자금액: {actual_investment:,.0f}원\n"
                            msg += f"대기시간: {wait_hours:.1f}시간\n"
                            msg += f"일봉점수: {daily_score}점 ({signal_strength})\n"
                            msg += f"분봉점수: {current_intraday_score}점\n"
                            msg += f"진입사유: {timing_analysis['reason']}"

                            if opportunity.get('news_impact'):
                                news_impact = opportunity['news_impact']
                                decision = news_impact.get('decision', 'NEUTRAL')
                                percentage = news_impact.get('percentage', 0)
                                reason = news_impact.get('reason', '')
                                
                                msg += f"\n📰 뉴스 분석:\n"
                                if decision == 'POSITIVE':
                                    msg += f"• ✅ 긍정 뉴스 ({percentage}% 신뢰도)\n"
                                    if reason:
                                        msg += f"• 내용: {reason[:80]}...\n"
                                elif decision == 'NEGATIVE': 
                                    msg += f"• ❌ 부정 뉴스 ({percentage}% 신뢰도)\n"
                                    if reason:
                                        msg += f"• 내용: {reason[:80]}...\n"
                                else:
                                    msg += f"• ⚪ 중립 뉴스 (영향 없음)\n"

                            logger.info(msg)
                            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                                discord_alert.SendMessage(msg)
                        else:
                            logger.error(f"   ❌ 분봉 타이밍 매수 실패")
                            candidates_expired.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'reason': '주문 실패 (분봉 타이밍)',
                                'daily_score': daily_score,
                                'wait_time': wait_hours
                            })
                    
                    candidates_to_remove.append(stock_code)
                
                else:
                    # 🔄 계속 대기: 정보 업데이트
                    logger.info(f"   🔄 분봉 타이밍 대기 계속")
                    logger.info(f"      사유: {timing_analysis['reason']}")
                    
                    # 대기 정보 업데이트
                    candidate_info['last_intraday_score'] = current_intraday_score
                    candidate_info['last_check_time'] = datetime.datetime.now().isoformat()
                    candidate_info['check_count'] = candidate_info.get('check_count', 0) + 1
                    
                    # 분봉 신호 변화 추적
                    if timing_analysis.get('entry_signals'):
                        candidate_info['latest_intraday_signals'] = timing_analysis['entry_signals'][:3]
                    
            except Exception as e:
                logger.error(f"매수 후보 처리 중 오류 ({stock_code}): {str(e)}")
                candidates_to_remove.append(stock_code)
                candidates_expired.append({
                    'stock_code': stock_code,
                    'stock_name': stock_code,
                    'reason': f'처리 오류: {str(e)}',
                    'daily_score': 0,
                    'wait_time': 0
                })
        
        # 🗑️ 처리 완료된 후보들 제거
        for stock_code in candidates_to_remove:
            if stock_code in trading_state['buy_candidates']:
                del trading_state['buy_candidates'][stock_code]
        
        # 📊 처리 결과 요약
        total_processed = len(candidates_executed) + len(candidates_expired)
        remaining_candidates = len(trading_state.get('buy_candidates', {}))
        
        logger.info(f"\n📊 매수 대기 후보 처리 완료:")
        logger.info(f"   - 처리된 종목: {total_processed}개")
        logger.info(f"   - 매수 실행: {len(candidates_executed)}개")
        logger.info(f"   - 매수 포기: {len(candidates_expired)}개")
        logger.info(f"   - 계속 대기: {remaining_candidates}개")
        
        # 🎯 실행된 종목 상세 정보
        if candidates_executed:
            logger.info(f"\n✅ 매수 실행된 종목들:")
            for exec_info in candidates_executed:
                logger.info(f"   - {exec_info['stock_name']}({exec_info['stock_code']}): "
                          f"{exec_info['executed_price']:,.0f}원×{exec_info['executed_amount']}주, "
                          f"대기 {exec_info['wait_time']:.1f}시간")
        
        # 📉 포기된 종목 상세 정보
        if candidates_expired:
            logger.info(f"\n❌ 매수 포기된 종목들:")
            for exp_info in candidates_expired:
                logger.info(f"   - {exp_info['stock_name']}({exp_info['stock_code']}): "
                          f"{exp_info['reason']}, 대기 {exp_info['wait_time']:.1f}시간")
        
        # 🔄 계속 대기 중인 종목들
        if remaining_candidates > 0:
            logger.info(f"\n⏳ 계속 대기 중인 종목들:")
            for stock_code, info in trading_state['buy_candidates'].items():
                wait_start = datetime.datetime.fromisoformat(info['wait_start_time'])
                wait_hours = (datetime.datetime.now() - wait_start).total_seconds() / 3600
                max_wait = info.get('max_wait_hours', 2.0)
                stock_name = info['opportunity']['stock_name']
                daily_score = info.get('daily_score', 0)
                
                remaining_time = max_wait - wait_hours
                logger.info(f"   - {stock_name}({stock_code}): "
                          f"{wait_hours:.1f}시간 대기 중 (남은시간: {remaining_time:.1f}시간, {daily_score}점)")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"매수 후보 관리 중 전체 오류: {str(e)}")
        logger.exception("상세 에러 정보:")
        return trading_state

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
    """타겟 종목 매수 기회 스캔 - 뉴스 분석 통합 (캐시 적용)"""
    try:
        # 기존 로직들...
        if 'recent_sells' in trading_state:
            expired_stocks = []
            now = datetime.datetime.now()
            
            for stock_code, sell_info in trading_state['recent_sells'].items():
                try:
                    sell_time = datetime.datetime.fromisoformat(sell_info['sell_time'])
                    cooldown_hours = sell_info.get('cooldown_hours', 2)
                    
                    if (now - sell_time).total_seconds() / 3600 > cooldown_hours:
                        expired_stocks.append(stock_code)
                except:
                    expired_stocks.append(stock_code)
            
            for stock_code in expired_stocks:
                del trading_state['recent_sells'][stock_code]
            
            if expired_stocks:
                logger.info(f"재매수 방지 만료: {len(expired_stocks)}개 종목")
        
        # 🔥 뉴스 캐시 초기화
        if 'news_cache' not in trading_state:
            trading_state['news_cache'] = {}
        
        # 만료된 뉴스 캐시 정리
        news_cache_hours = trading_config.config.get('news_cache_hours', 6)
        expired_news = []
        for stock_code, cache_data in trading_state['news_cache'].items():
            try:
                last_check = datetime.datetime.fromisoformat(cache_data['last_check'])
                if (datetime.datetime.now() - last_check).total_seconds() / 3600 > news_cache_hours:
                    expired_news.append(stock_code)
            except:
                expired_news.append(stock_code)
        
        for stock_code in expired_news:
            del trading_state['news_cache'][stock_code]
        
        if expired_news:
            logger.info(f"뉴스 캐시 만료: {len(expired_news)}개 종목")
            save_trading_state(trading_state)  # 캐시 정리 저장
        
        buy_opportunities = []
        current_positions = len(trading_state['positions'])
        
        if current_positions >= get_active_target_stock_count():
            logger.info(f"최대 보유 종목 수 도달({get_active_target_stock_count()}개)")
            return []
        
        logger.info(f"타겟 종목 매수 기회 스캔 시작: {len(trading_config.target_stocks)}개 종목 분석")
        
        # 🔥 뉴스 분석을 위한 종목 리스트 준비
        stocks_for_news = []
        technical_results = {}  # 기술적 분석 결과 저장
        cached_news_count = 0  # 캐시 히트 카운트
        
        # 1단계: 기술적 분석 먼저 수행
        for stock_code, target_config in trading_config.target_stocks.items():
            # ========== 디버깅 코드 시작 ==========
            logger.info(f"🔍 [{stock_code}] 스캔 시작")
            
            try:
                if not target_config.get('enabled', True):
                    logger.info(f"❌ [{stock_code}] 비활성화됨")
                    continue
                    
                if stock_code in trading_state['positions']:
                    logger.info(f"❌ [{stock_code}] 이미 보유 중")
                    continue
                
                # 🆕 미체결 주문 체크 (라이브러리 사용)
                if pending_manager.check_pending_orders(stock_code, trading_state):
                    logger.info(f"❌ [{stock_code}] 미체결 주문 있음")
                    continue
                
                # 재매수 방지 체크
                if 'recent_sells' in trading_state and stock_code in trading_state['recent_sells']:
                    sell_info = trading_state['recent_sells'][stock_code]
                    try:
                        sell_time = datetime.datetime.fromisoformat(sell_info['sell_time'])
                        cooldown_hours = sell_info.get('cooldown_hours', 2)
                        elapsed_hours = (datetime.datetime.now() - sell_time).total_seconds() / 3600
                        
                        if elapsed_hours < cooldown_hours:
                            remaining_hours = cooldown_hours - elapsed_hours
                            stock_name = target_config.get('name', stock_code)
                            logger.info(f"❌ [{stock_code}] 재매수 방지: 남은시간 {remaining_hours:.1f}시간")
                            continue
                    except:
                        pass
                
                # 가격 필터링 - 디버깅 추가
                logger.info(f"📊 [{stock_code}] 현재가 조회 중...")
                current_price = KisKR.GetCurrentPrice(stock_code)
                logger.info(f"📊 [{stock_code}] 현재가: {current_price}")
                
                if not current_price:
                    logger.info(f"❌ [{stock_code}] 현재가 조회 실패 (None)")
                    continue
                    
                if current_price < trading_config.min_stock_price:
                    logger.info(f"❌ [{stock_code}] 최소가격 미달: {current_price} < {trading_config.min_stock_price}")
                    continue
                    
                if current_price > trading_config.max_stock_price:
                    logger.info(f"❌ [{stock_code}] 최대가격 초과: {current_price} > {trading_config.max_stock_price}")
                    continue
                
                # 종목 데이터 분석 - 디버깅 추가
                logger.info(f"📈 [{stock_code}] 종목 데이터 조회 시작...")
                stock_data = get_stock_data(stock_code)
                
                if not stock_data:
                    logger.info(f"❌ [{stock_code}] 종목 데이터 조회 실패")
                    continue
                
                logger.info(f"✅ [{stock_code}] 매수 신호 분석 시작")
                
                # 매수 신호 분석
                buy_analysis = analyze_buy_signal(stock_data, target_config)
                
                # 기술적 분석 결과 저장
                technical_results[stock_code] = {
                    'stock_data': stock_data,
                    'target_config': target_config,
                    'buy_analysis': buy_analysis,
                    'current_price': current_price
                }
                
                # 뉴스 체크가 필요한 종목 선별
                if trading_config.config.get('use_news_analysis', False):
                    news_threshold = trading_config.config.get('news_check_threshold', 35)
                    if buy_analysis['score'] >= news_threshold:
                        # 🔥 캐시 확인
                        if stock_code in trading_state['news_cache']:
                            cache_data = trading_state['news_cache'][stock_code]
                            try:
                                last_check = datetime.datetime.fromisoformat(cache_data['last_check'])
                                cache_age_hours = (datetime.datetime.now() - last_check).total_seconds() / 3600
                                
                                if cache_age_hours < news_cache_hours:
                                    # 캐시 유효 - 바로 사용
                                    cached_news_count += 1
                                    logger.info(f"📰 [{stock_code}] 뉴스 캐시 사용 (캐시 나이: {cache_age_hours:.1f}시간)")
                                else:
                                    # 캐시 만료 - 새로 분석 필요
                                    stocks_for_news.append({
                                        'StockCode': stock_code,
                                        'StockName': target_config.get('name', stock_code)
                                    })
                                    logger.info(f"📰 [{stock_code}] 뉴스 캐시 만료 - 재분석 필요")
                            except:
                                # 캐시 데이터 오류 - 새로 분석
                                stocks_for_news.append({
                                    'StockCode': stock_code,
                                    'StockName': target_config.get('name', stock_code)
                                })
                        else:
                            # 캐시 없음 - 새로 분석
                            stocks_for_news.append({
                                'StockCode': stock_code,
                                'StockName': target_config.get('name', stock_code)
                            })
                            logger.info(f"📰 [{stock_code}] 뉴스 분석 대상 추가 (점수: {buy_analysis['score']})")
                
                if buy_analysis['is_buy_signal']:
                    logger.info(f"🎯 [{stock_code}] 매수 기회 발견! (점수: {buy_analysis.get('score', 0)})")
                else:
                    logger.info(f"⏳ [{stock_code}] 매수 신호 없음 (점수: {buy_analysis.get('score', 0)}/{buy_analysis.get('min_score', 40)})")
                
            except Exception as e:
                logger.error(f"❌ [{stock_code}] 예외 발생: {str(e)}")
                continue
            # ========== 디버깅 코드 끝 ==========
        
        # 2단계: 뉴스 분석 (캐시되지 않은 종목만)
        news_results = {}
        
        # 🔥 캐시된 뉴스 먼저 로드
        if cached_news_count > 0:
            logger.info(f"📰 캐시에서 {cached_news_count}개 종목 뉴스 로드")
            for stock_code in technical_results:
                if stock_code in trading_state['news_cache']:
                    cache_data = trading_state['news_cache'][stock_code]
                    if 'news_score' in cache_data:
                        news_results[stock_code] = cache_data['news_score']
        
        # 🔥 새로운 뉴스 분석 수행
        if stocks_for_news and trading_config.config.get('use_news_analysis', False):
            logger.info(f"📰 {len(stocks_for_news)}개 종목 뉴스 신규 분석 시작")
            try:
                import news_analysis
                news_analysis.set_logger(logger)  # logger 설정
                news_data = news_analysis.analyze_all_stocks_news(stocks_for_news)
                
                # 뉴스 결과를 종목별로 매핑 및 캐시 저장
                if news_data and 'stocks' in news_data:
                    for stock_name, stock_news in news_data['stocks'].items():
                        stock_code = stock_news.get('stock_code')
                        if stock_code and 'analysis' in stock_news:
                            news_score = stock_news['analysis']
                            news_results[stock_code] = news_score
                            
                            # 🔥 캐시에 저장
                            trading_state['news_cache'][stock_code] = {
                                'last_check': datetime.datetime.now().isoformat(),
                                'news_score': news_score,
                                'articles': stock_news.get('articles', [])[:2]  # 최근 2개 기사 제목만 저장
                            }
                            
                            logger.info(f"📰 {stock_name}({stock_code}): {news_score['decision']} "
                                      f"({news_score['percentage']}%) - 캐시 저장")
                    
                    # 캐시 업데이트 저장
                    save_trading_state(trading_state)
                            
            except Exception as e:
                logger.error(f"뉴스 일괄 분석 실패: {str(e)}")
        
        # 3단계: 기술적 분석과 뉴스 분석 결합
        for stock_code, tech_result in technical_results.items():
            buy_analysis = tech_result['buy_analysis']
            target_config = tech_result['target_config']
            stock_name = target_config.get('name', stock_code)
            
            # 뉴스 점수 반영
            if stock_code in news_results:
                news_impact = news_results[stock_code]
                decision = news_impact.get('decision', 'NEUTRAL')
                percentage = news_impact.get('percentage', 0)
                reason = news_impact.get('reason', '')
                
                # 뉴스 점수 계산
                news_weight = trading_config.config.get('news_weight', {})
                positive_mult = news_weight.get('positive_multiplier', 0.3)
                negative_mult = news_weight.get('negative_multiplier', 0.5)
                
                original_score = buy_analysis['score']
                
                if decision == 'POSITIVE':
                    news_score = int(percentage * positive_mult)
                    buy_analysis['score'] += news_score
                    buy_analysis['signals'].append(f"긍정 뉴스 +{news_score}점: {reason[:50]}")
                    logger.info(f"📰 {stock_name}: 긍정 뉴스 +{news_score}점 (기존 {original_score} → {buy_analysis['score']})")
                    
                    # 매우 긍정적 뉴스는 신호 강도 상향
                    if percentage >= 70 and buy_analysis.get('signal_strength') == 'NORMAL':
                        buy_analysis['signal_strength'] = 'STRONG'
                        target_config['last_signal_strength'] = 'STRONG'
                    
                elif decision == 'NEGATIVE':
                    news_score = -int(percentage * negative_mult)
                    
                    # 매우 부정적 뉴스는 스킵
                    if percentage >= 70:
                        logger.info(f"❌ {stock_name}: 강한 부정 뉴스로 제외")
                        continue
                    
                    buy_analysis['score'] += news_score
                    buy_analysis['signals'].append(f"부정 뉴스 {news_score}점: {reason[:50]}")
                    logger.info(f"📰 {stock_name}: 부정 뉴스 {news_score}점 (기존 {original_score} → {buy_analysis['score']})")
                
                buy_analysis['news_impact'] = news_impact
                
                # 뉴스 반영 후 재판단
                buy_analysis['is_buy_signal'] = buy_analysis['score'] >= buy_analysis['min_score']
            
            # 최종 매수 신호 판단
            if buy_analysis['is_buy_signal']:
                buy_opportunities.append({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'price': tech_result['current_price'],
                    'score': buy_analysis['score'],
                    'min_score': buy_analysis['min_score'],
                    'signals': buy_analysis['signals'],
                    'analysis': buy_analysis['analysis'],
                    'target_config': target_config,
                    'signal_strength': buy_analysis.get('signal_strength', 'NORMAL'),
                    'news_impact': buy_analysis.get('news_impact')
                })
                
                logger.info(f"✅ 매수 기회 발견: {stock_name}({stock_code})")
                logger.info(f"   점수: {buy_analysis['score']}/{buy_analysis['min_score']}점")
                for signal in buy_analysis['signals'][:3]:
                    logger.info(f"   - {signal}")
        
        # 점수 순으로 정렬
        buy_opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        # 🔥 캐시 상태 로깅
        total_cache_entries = len(trading_state.get('news_cache', {}))
        logger.info(f"📰 뉴스 캐시 현황: 총 {total_cache_entries}개 종목, 이번 스캔에서 {cached_news_count}개 재사용")
        
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
    """보유 포지션 관리 - API 보유 vs 봇 미기록 케이스 처리 추가"""
    try:
        my_stocks = KisKR.GetMyStockList()
        positions_to_remove = []
        
        # 🔥 1단계: 봇 기록 종목들 처리 (기존 로직)
        for stock_code, position in trading_state['positions'].items():
            try:
                # 타겟 종목이 아닌 경우 스킵
                if stock_code not in trading_config.target_stocks:
                    continue
                
                # API에서 실제 보유 확인
                actual_holding = None
                if my_stocks:
                    for stock in my_stocks:
                        if stock['StockCode'] == stock_code:
                            actual_holding = stock
                            break
                
                target_config = trading_config.target_stocks[stock_code]
                stock_name = target_config.get('name', stock_code)
                
                # 🔥 봇 기록의 수량 사용 (API와 무관)
                current_amount = position.get('amount', 0)
                
                if current_amount <= 0:
                    logger.info(f"봇 기록상 보유 수량 0 - 포지션 제거: {stock_name}({stock_code})")
                    positions_to_remove.append(stock_code)
                    continue
                
                # 🔥 ========== 여기에 수량 검증 로직 추가 ==========
                # API 조회 성공시 실제 보유량 검증
                actual_amount = 0
                if my_stocks and actual_holding:
                    actual_amount = int(actual_holding.get('StockAmt', 0))
                
                # 실제 보유량이 봇 기록보다 적으면 매도 불가
                sell_amount = current_amount  # 기본값: 봇 기록 수량
                
                if my_stocks:  # API 조회 성공시에만 검증
                    if actual_amount == 0:
                        # 실제 보유 없음 - 매도 불가, 포지션만 정리
                        warning_msg = f"⚠️ 실제 보유량 0으로 매도 불가: {stock_name}({stock_code})\n"
                        warning_msg += f"봇 기록: {current_amount}주 → 포지션 정리"
                        logger.warning(warning_msg)
                        discord_alert.SendMessage(warning_msg)
                        positions_to_remove.append(stock_code)
                        continue
                        
                    elif actual_amount < current_amount:
                        # 실제 보유량이 적음 - 실제 보유량만큼만 매도
                        sell_amount = actual_amount
                        warning_msg = f"⚠️ 보유량 불일치로 매도량 조정: {stock_name}({stock_code})\n"
                        warning_msg += f"봇 기록: {current_amount}주 → 실제: {actual_amount}주\n"
                        warning_msg += f"매도 예정: {sell_amount}주"
                        logger.warning(warning_msg)
                        discord_alert.SendMessage(warning_msg)
                        
                        # 봇 기록도 실제 수량으로 조정
                        position['amount'] = actual_amount
                        trading_state['positions'][stock_code] = position
                
                # 🔥 ========== 검증 로직 끝 ==========
                
                # API 검증 결과 알림 (기존 로직 유지하되 더 간단하게)
                if my_stocks and actual_holding:
                    if actual_amount != current_amount and actual_amount > 0:
                        logger.debug(f"수량 차이 감지 (이미 조정됨): {stock_name}({stock_code}) "
                                   f"봇:{current_amount}주 → 실제:{actual_amount}주")
                elif not my_stocks:
                    logger.debug(f"API 조회 실패 - 봇 기록으로만 관리: {stock_name}({stock_code})")
                
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
                    logger.info(f"🔴 매도 신호 감지: {stock_name}({stock_code})")
                    logger.info(f"   유형: {sell_analysis['sell_type']}")
                    logger.info(f"   이유: {sell_analysis['reason']}")
                    
                    # 🔥 검증된 수량으로 매도 주문 실행
                    logger.info(f"   매도 수량: {sell_amount}주 (검증완료)")
                    executed_price, executed_amount = execute_sell_order(
                        stock_code, target_config, sell_amount  # 검증된 수량 사용
                    )
                    
                    if executed_price and executed_amount:
                        # 손익 계산 (기존 로직 유지)
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
                        
                        # 🔥 재매수 방지 기록
                        if 'recent_sells' not in trading_state:
                            trading_state['recent_sells'] = {}
                        
                        trading_state['recent_sells'][stock_code] = {
                            'sell_time': datetime.datetime.now().isoformat(),
                            'sell_reason': sell_analysis['sell_type'],
                            'cooldown_hours': 2
                        }
                        
                        # 매도 완료 알림
                        msg = f"💰 매도 완료: {stock_name}({stock_code})\n"
                        msg += f"매도가: {executed_price:,.0f}원\n"
                        msg += f"수량: {executed_amount}주\n"
                        msg += f"순손익: {net_profit:,.0f}원 ({profit_rate:.2f}%)\n"
                        msg += f"매도사유: {sell_analysis['reason']}\n"
                        msg += f"재매수 방지: 2시간"
                        
                        # 🔥 수량 조정이 있었다면 추가 안내
                        if sell_amount != current_amount:
                            msg += f"\n⚠️ 수량 조정: 봇기록 {current_amount}주 → 실제매도 {executed_amount}주"
                        
                        logger.info(msg)
                        discord_alert.SendMessage(msg)
                        
                        # 적응형 전략 학습 (기존 로직 유지)
                        if trading_config.use_adaptive_strategy:
                            try:
                                stock_env = sell_analysis.get('stock_environment', 'sideways')
                                adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
                                adaptive_strategy.update_performance(
                                    stock_code, 
                                    stock_env, 
                                    win=(net_profit > 0)
                                )
                                win_lose = "승리" if net_profit > 0 else "패배"
                                logger.info(f"🧠 적응형 전략 학습: {stock_code} ({stock_env}) - {win_lose}")
                            except Exception as e:
                                logger.error(f"적응형 전략 학습 오류: {str(e)}")
                        
                        # 포지션 제거
                        positions_to_remove.append(stock_code)
                    else:
                        logger.error(f"매도 주문 실패: {stock_name}({stock_code})")
                
            except Exception as e:
                logger.error(f"포지션 처리 오류 ({stock_code}): {str(e)}")
                continue
        
        # 🔥 2단계: API에는 있지만 봇 기록에 없는 종목 체크 (기존 로직 유지)
        if my_stocks:  # API 조회 성공시에만
            bot_tracked_stocks = set(trading_state['positions'].keys())
            
            for stock in my_stocks:
                stock_code = stock['StockCode']
                actual_amount = int(stock.get('StockAmt', 0))
                
                # 타겟 종목이고, 실제 보유량이 있고, 봇 기록에 없는 경우
                if (stock_code in trading_config.target_stocks and 
                    actual_amount > 0 and 
                    stock_code not in bot_tracked_stocks):
                    
                    stock_name = trading_config.target_stocks[stock_code].get('name', stock_code)
                    current_price = float(stock.get('NowPrice', 0))
                    
                    warning_msg = f"📊 외부 보유 감지: {stock_name}({stock_code})\n"
                    warning_msg += f"실제 계좌: {actual_amount}주 (현재가: {current_price:,.0f}원)\n"
                    warning_msg += f"봇 기록: 없음\n"
                    warning_msg += f"→ 다른 앱에서 매수한 것으로 추정\n"
                    warning_msg += f"→ 봇 관리 대상 아님 (독립 운영)"
                    
                    logger.info(warning_msg)
                    discord_alert.SendMessage(warning_msg)
        
        # 제거할 포지션 정리
        for stock_code in positions_to_remove:
            if stock_code in trading_state['positions']:
                del trading_state['positions'][stock_code]
                logger.info(f"포지션 제거 완료: {stock_code}")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"포지션 관리 오류: {str(e)}")
        return trading_state

def execute_buy_opportunities(buy_opportunities, trading_state):
    """매수 기회 실행 - 신호 강도별 분봉 타이밍 + 40점 기준 적용"""
    try:
        if not buy_opportunities:
            return trading_state
        
        # 전체 사용 가능 예산 확인
        total_available_budget = get_available_budget(trading_state)
        
        if total_available_budget <= 0:
            logger.info("💰 전체 사용 가능 예산이 없습니다.")
            return trading_state
        
        # 현재 포지션 수 확인 - 활성 종목 수 기반
        current_positions = len(trading_state['positions'])
        max_allowed_positions = get_active_target_stock_count()
        max_new_positions = max_allowed_positions - current_positions
        
        if max_new_positions <= 0:
            logger.info(f"📊 최대 보유 종목 수 도달: {current_positions}/{max_allowed_positions}")
            return trading_state
        
        # 일일 손익 한도 확인
        daily_stats = trading_state['daily_stats']
        if daily_stats['start_balance'] > 0:
            daily_profit_rate = daily_stats['total_profit'] / daily_stats['start_balance']
            
            if daily_profit_rate <= trading_config.max_daily_loss:
                logger.info(f"📉 일일 손실 한도 도달: {daily_profit_rate*100:.1f}%")
                return trading_state
            
            if daily_profit_rate >= trading_config.max_daily_profit:
                logger.info(f"📈 일일 수익 한도 도달: {daily_profit_rate*100:.1f}%")
                return trading_state
        
        # 예산 현황 출력
        total_invested = get_total_invested_amount(trading_state)
        per_stock_limit = get_per_stock_budget_limit()
        active_stock_count = get_active_target_stock_count()
        
        logger.info(f"💰 매수 실행 준비 (신호 강도별 분봉 타이밍):")
        logger.info(f"  - 전체 사용가능 예산: {total_available_budget:,.0f}원")
        logger.info(f"  - 이미 투자된 금액: {total_invested:,.0f}원")
        logger.info(f"  - 활성 타겟 종목 수: {active_stock_count}개")
        logger.info(f"  - 종목별 예산 한도: {per_stock_limit:,.0f}원")
        logger.info(f"  - 현재/최대 보유종목: {current_positions}/{max_allowed_positions}개")
        logger.info(f"  - 매수 기준: 40점 (강화)")
        
        # 매수 실행
        executed_count = 0
        for i, opportunity in enumerate(buy_opportunities[:max_new_positions]):
            try:
                stock_code = opportunity['stock_code']
                stock_name = opportunity['stock_name']
                stock_price = opportunity['price']
                target_config = opportunity['target_config']
                daily_score = opportunity['score']
                signal_strength = opportunity.get('signal_strength', 'NORMAL')
                
                logger.info(f"\n🔍 매수 검토: {stock_name}({stock_code})")
                logger.info(f"   일봉 점수: {daily_score}점 ({signal_strength})")
                
                # 종목별 남은 예산 확인
                remaining_budget = get_remaining_budget_for_stock(stock_code, trading_state)
                if remaining_budget <= 10000:  # 최소 1만원 이상
                    logger.info(f"   ❌ 종목별 예산 부족: {remaining_budget:,.0f}원")
                    continue
                
                # 🎯 신호 강도별 분봉 타이밍 결정
                use_intraday, max_wait_hours, timing_reason = should_use_intraday_timing(opportunity, target_config)
                
                logger.info(f"   📊 분봉 타이밍 전략: {timing_reason}")
                
                # 분봉 타이밍 적용 여부
                if use_intraday:
                    logger.info(f"   🔍 분봉 진입 타이밍 분석 중...")
                    timing_analysis = analyze_intraday_entry_timing(stock_code, target_config)
                    
                    intraday_score = timing_analysis.get('entry_score', 0)
                    min_intraday_score = target_config.get('min_entry_score', 20)
                    
                    logger.info(f"   🕐 분봉 점수: {intraday_score}/{min_intraday_score}점")
                    
                    if not timing_analysis['enter_now']:
                        logger.info(f"   ⏳ 분봉 진입 타이밍 대기 결정")
                        logger.info(f"      사유: {timing_analysis['reason']}")
                        logger.info(f"      최대 대기시간: {max_wait_hours}시간")
                        
                        # 매수 대기 리스트에 추가 (신호별 대기시간 적용)
                        if 'buy_candidates' not in trading_state:
                            trading_state['buy_candidates'] = {}
                        
                        trading_state['buy_candidates'][stock_code] = {
                            'opportunity': opportunity,
                            'wait_start_time': datetime.datetime.now().isoformat(),
                            'max_wait_hours': max_wait_hours,  # 🔥 신호별 대기시간
                            'daily_score': daily_score,
                            'signal_strength': signal_strength,
                            'last_intraday_score': intraday_score,
                            'min_intraday_score': min_intraday_score,
                            'last_check_time': datetime.datetime.now().isoformat(),
                            'timing_reason': timing_reason,  # 🔥 타이밍 이유 저장
                            'timing_analysis': timing_analysis
                        }
                        
                        logger.info(f"      → 매수 대기 리스트 등록 완료")
                        
                        # 대기 종목 요약 정보
                        total_candidates = len(trading_state.get('buy_candidates', {}))
                        logger.info(f"📋 현재 매수 대기 종목: {total_candidates}개")
                        
                        continue
                    else:
                        logger.info(f"   ✅ 분봉 진입 타이밍 양호")
                        logger.info(f"      사유: {timing_analysis['reason']}")
                        logger.info(f"      분봉 신호: {timing_analysis.get('entry_signals', [])[:3]}")
                else:
                    logger.info(f"   🚀 일봉 신호 강도로 즉시 매수 진행")
                
                # 포지션 크기 계산
                quantity = calculate_position_size(target_config, stock_code, stock_price, trading_state)
                
                if quantity < 1:
                    logger.info(f"   ❌ 매수 수량 부족 (계산된 수량: {quantity})")
                    continue
                
                # 최종 투자금액 계산
                estimated_investment = stock_price * quantity
                estimated_fee = calculate_trading_fee(stock_price, quantity, True)
                total_cost = estimated_investment + estimated_fee
                
                logger.info(f"   💰 매수 계획:")
                logger.info(f"      수량: {quantity}주")
                logger.info(f"      가격: {stock_price:,.0f}원")
                logger.info(f"      투자금액: {estimated_investment:,.0f}원")
                logger.info(f"      예상 수수료: {estimated_fee:,.0f}원")
                logger.info(f"      총 소요: {total_cost:,.0f}원")
                
                # 🔵 매수 주문 실행
                logger.info(f"   🔵 매수 주문 실행: {stock_name}({stock_code})")
                executed_price, executed_amount = execute_buy_order(
                    stock_code, target_config, quantity, stock_price
                )
                
                if executed_price and executed_amount:
                    # 매수 수수료 계산
                    buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                    actual_investment = executed_price * executed_amount
                    
                    logger.info(f"   ✅ 매수 체결 성공!")
                    logger.info(f"      체결가: {executed_price:,.0f}원")
                    logger.info(f"      체결량: {executed_amount}주")
                    logger.info(f"      실제 투자금액: {actual_investment:,.0f}원")
                    logger.info(f"      실제 수수료: {buy_fee:,.0f}원")
                    
                    # 포지션 정보 저장
                    position_info = {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'entry_price': executed_price,
                        'amount': executed_amount,
                        'buy_fee': buy_fee,
                        'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'high_price': executed_price,
                        'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', trading_config.trailing_stop_ratio)),
                        'target_config': target_config,
                        'buy_analysis': opportunity['analysis'],
                        'signal_strength': signal_strength,
                        'daily_score': daily_score,  # 🔥 일봉 점수 저장
                        'entry_method': 'intraday_timing' if use_intraday else 'daily_signal_only'
                    }
                    
                    # 분봉 타이밍 사용시 분봉 정보도 저장
                    if use_intraday and 'timing_analysis' in locals():
                        position_info['intraday_analysis'] = timing_analysis
                        position_info['intraday_score'] = timing_analysis.get('entry_score', 0)
                    
                    trading_state['positions'][stock_code] = position_info
                    executed_count += 1
                    
                    # 📊 예산 현황 업데이트
                    updated_total_invested = get_total_invested_amount(trading_state) + actual_investment
                    total_target_budget = get_per_stock_budget_limit() * active_stock_count
                    remaining_total_budget = total_target_budget - updated_total_invested
                    
                    # 종목별 투자 현황
                    current_stock_invested = get_invested_amount_for_stock(stock_code, trading_state) + actual_investment
                    stock_usage_rate = (current_stock_invested / per_stock_limit * 100) if per_stock_limit > 0 else 0
                    
                    # 🎉 매수 완료 알림 (상세 정보 포함)
                    msg = f"🎉 매수 완료: {stock_name}({stock_code})\n"
                    msg += f"매수가: {executed_price:,.0f}원 × {executed_amount}주\n"
                    msg += f"투자금액: {actual_investment:,.0f}원\n"
                    msg += f"수수료: {buy_fee:,.0f}원\n"
                    
                    # 신호 정보
                    msg += f"\n🎯 신호 정보:\n"
                    msg += f"• 일봉 점수: {daily_score}점 ({signal_strength})\n"
                    if use_intraday:
                        intraday_score = timing_analysis.get('entry_score', 0) if 'timing_analysis' in locals() else 0
                        msg += f"• 분봉 점수: {intraday_score}점\n"
                        msg += f"• 진입 방식: 분봉 타이밍 적용\n"
                    else:
                        msg += f"• 진입 방식: 강한 신호로 즉시 매수\n"
                    
                    # 예산 현황
                    msg += f"\n📊 예산 현황:\n"
                    msg += f"• 전체 투자: {updated_total_invested:,.0f}원\n"
                    msg += f"• 남은 예산: {remaining_total_budget:,.0f}원\n"
                    msg += f"• 활성 종목 수: {active_stock_count}개\n"
                    
                    # 종목별 투자 현황
                    msg += f"\n💰 {stock_name} 투자 현황:\n"
                    msg += f"• 투자금액: {current_stock_invested:,.0f}원\n"
                    msg += f"• 종목별 한도: {per_stock_limit:,.0f}원\n"
                    msg += f"• 사용률: {stock_usage_rate:.1f}%\n"

                    if opportunity.get('news_impact'):
                        news_impact = opportunity['news_impact']
                        decision = news_impact.get('decision', 'NEUTRAL')
                        percentage = news_impact.get('percentage', 0)
                        reason = news_impact.get('reason', '')
                        
                        msg += f"\n📰 뉴스 분석:\n"
                        if decision == 'POSITIVE':
                            msg += f"• ✅ 긍정 뉴스 ({percentage}% 신뢰도)\n"
                            if reason:
                                msg += f"• 내용: {reason[:80]}...\n"  # 80자까지만
                        elif decision == 'NEGATIVE': 
                            msg += f"• ❌ 부정 뉴스 ({percentage}% 신뢰도)\n"
                            if reason:
                                msg += f"• 내용: {reason[:80]}...\n"
                        else:
                            msg += f"• ⚪ 중립 뉴스 (영향 없음)\n"

                    # 주요 매수 사유 (상위 3개)
                    if opportunity.get('signals'):
                        msg += f"\n📈 주요 매수 사유:\n"
                        for signal in opportunity['signals'][:3]:
                            msg += f"• {signal}\n"
                    
                    logger.info(msg)
                    
                    # Discord 알림 전송
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(msg)
                    
                    # 전체 예산 재확인 (다음 매수를 위해)
                    total_available_budget = get_available_budget(trading_state)
                    if total_available_budget < 10000:  # 1만원 미만이면 매수 중단
                        logger.info("💰 전체 예산 부족으로 매수 중단")
                        break
                    
                    logger.info(f"   💰 남은 전체 예산: {total_available_budget:,.0f}원")
                
                else:
                    logger.error(f"   ❌ 매수 주문 실패: {stock_name}({stock_code})")
                    logger.error(f"      주문 결과: {executed_price}, {executed_amount}")
                
            except Exception as e:
                logger.error(f"매수 실행 중 에러 ({stock_code}): {str(e)}")
                continue
        
        # 🎯 실행 결과 요약
        if executed_count > 0:
            logger.info(f"\n🎯 매수 실행 완료: {executed_count}개 종목")
            
            # 현재 포지션 현황
            updated_positions = len(trading_state['positions'])
            logger.info(f"📊 현재 보유 종목: {updated_positions}/{max_allowed_positions}개")
            
            # 전체 투자 현황
            final_total_invested = get_total_invested_amount(trading_state)
            final_available_budget = get_available_budget(trading_state)
            
            logger.info(f"💰 전체 투자 현황:")
            logger.info(f"   - 총 투자됨: {final_total_invested:,.0f}원")
            logger.info(f"   - 사용 가능: {final_available_budget:,.0f}원")
        else:
            logger.info(f"\n⏸️ 매수 실행 종목 없음")
            logger.info(f"   사유: 예산 부족, 타이밍 대기, 또는 기준 미달")
        
        # 매수 대기 종목 현황
        if 'buy_candidates' in trading_state and trading_state['buy_candidates']:
            candidate_count = len(trading_state['buy_candidates'])
            logger.info(f"\n📋 매수 대기 종목: {candidate_count}개")
            
            for code, info in trading_state['buy_candidates'].items():
                wait_start = datetime.datetime.fromisoformat(info['wait_start_time'])
                wait_minutes = (datetime.datetime.now() - wait_start).total_seconds() / 60
                max_wait_hours = info.get('max_wait_hours', 2.0)
                daily_score = info.get('daily_score', 0)
                signal_strength = info.get('signal_strength', 'NORMAL')
                
                stock_name = info['opportunity']['stock_name']
                logger.info(f"   - {stock_name}({code}): {wait_minutes:.0f}분 대기 "
                          f"(최대 {max_wait_hours}시간, {daily_score}점 {signal_strength})")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"매수 실행 중 전체 에러: {str(e)}")
        logger.exception("상세 에러 정보:")
        return trading_state

def create_config_file(config_path: str = "target_stock_config.json") -> None:
    """기본 설정 파일 생성 (분봉 타이밍 옵션 + 뉴스 분석 포함한 개선 버전)"""
    try:
        logger.info("분봉 타이밍 + 뉴스 분석 옵션 포함한 개선 설정 파일 생성 시작...")
        
        # 기본 타겟 종목들 정의 (거래량 확보를 위해 확대)
        sample_codes = ["272210", "034020", "010140"]  # 한화시스템, 두산에너빌리티, 삼성중공업

        # 🎯 특성별 파라미터 수정 (모든 타입의 min_score 상향)
        characteristic_params = {
            "growth": {
                "allocation_ratio": 1,
                "profit_target": 0.12,
                "stop_loss": -0.08,           # -0.12 → -0.08
                "rsi_oversold": 55,
                "rsi_overbought": 75,
                "min_score": 40,                 # 🔥 30 → 40 (강화)
                "trailing_stop": 0.03,        # 0.025 → 0.03  
                "min_holding_hours": 24,      # 48 → 24
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.5,
                "stop_loss_delay_hours": 2,
                
                # 🎯 분봉 진입 타이밍 설정 (완화)
                "min_entry_score": 20,              # 🔥 30 → 20 (완화)
                "intraday_rsi_oversold": 35,
                "intraday_rsi_overbought": 70,
                "intraday_volume_threshold": 1.2,
                "use_bb_entry_timing": True,
                "bb_lower_margin": 0.02,
                "ma_support_margin": 0.01
            },
            "balanced": {
                "allocation_ratio": 0.5,
                "profit_target": 0.10,
                "stop_loss": -0.07,           # -0.12 → -0.07
                "rsi_oversold": 55,
                "rsi_overbought": 75,
                "min_score": 40,                 # 🔥 30 → 40 (강화)
                "trailing_stop": 0.035,       # 0.03 → 0.035
                "min_holding_hours": 24,      # 48 → 24
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.4,
                "stop_loss_delay_hours": 2,
                "min_entry_score": 25,              # 🔥 35 → 25 (완화)
                "intraday_rsi_oversold": 40,
                "intraday_rsi_overbought": 65,
                "intraday_volume_threshold": 1.15,
                "use_bb_entry_timing": True,
                "bb_lower_margin": 0.025,
                "ma_support_margin": 0.015
            },
            "value": {
                "allocation_ratio": 0.5,
                "profit_target": 0.08,
                "stop_loss": -0.06,           # -0.10 → -0.06
                "rsi_oversold": 60,
                "rsi_overbought": 70,
                "min_score": 45,                 # 🔥 35 → 45 (가장 보수적)
                "trailing_stop": 0.04,        # 0.035 → 0.04
                "min_holding_hours": 24,      # 48 → 24
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.3,
                "stop_loss_delay_hours": 1,
                
                "min_entry_score": 30,              # 🔥 40 → 30 (완화)
                "intraday_rsi_oversold": 45,
                "intraday_rsi_overbought": 60,
                "intraday_volume_threshold": 1.1,
                "use_bb_entry_timing": True,
                "bb_lower_margin": 0.03,
                "ma_support_margin": 0.02
            }
        }

        # 임시 종목 특성 분석 (간단화 버전)
        target_stocks = {}
        for i, stock_code in enumerate(sample_codes):
            try:
                # 종목명 조회
                stock_status = KisKR.GetCurrentStatus(stock_code)
                if stock_status and isinstance(stock_status, dict):
                    stock_name = stock_status.get("StockName", f"종목{stock_code}")
                else:
                    stock_name = f"종목{stock_code}"
                
                # 섹터 정보 조회
                sector_info = get_sector_info(stock_code)
                
                # 🔥 모든 종목을 성장주로 설정 (사용자 요청)
                char_type = "growth"
                
                # 특성별 파라미터 적용
                params = characteristic_params[char_type].copy()
                params.update({
                    "name": stock_name,
                    "sector": sector_info.get('sector', 'Unknown'),
                    "enabled": True,
                    "characteristic_type": char_type
                })
                
                target_stocks[stock_code] = params
                logger.info(f"종목 설정: {stock_code}({stock_name}) - {char_type}")
                
                time.sleep(0.5)  # API 호출 간격
                
            except Exception as e:
                logger.warning(f"종목 {stock_code} 정보 수집 중 오류: {str(e)}")
                # 기본값으로 설정
                target_stocks[stock_code] = characteristic_params["growth"].copy()
                target_stocks[stock_code].update({
                    "name": f"종목{stock_code}",
                    "sector": "Unknown",
                    "enabled": True,
                    "characteristic_type": "growth"
                })
        
        # 전체 설정 구성 (분봉 타이밍 + 뉴스 분석 옵션 포함)
        config = {
            "target_stocks": target_stocks,
            
            # 🎯 분봉 타이밍 전역 설정 (새로 추가)
            "use_intraday_timing": True,            # 분봉 진입 타이밍 사용 여부 (백테스트시 False)
            "intraday_check_interval": 10,          # 분봉 체크 주기 (초) - 분봉 타이밍 사용시
            "default_check_interval": 30,           # 기본 체크 주기 (초) - 일봉만 사용시
            "max_candidate_wait_hours": 2,          # 최대 대기 시간 (시간)
            "intraday_data_period": "5m",           # 분봉 데이터 주기 (5분봉)
            "intraday_data_count": 24,              # 분봉 데이터 개수 (2시간치)
            "force_buy_after_wait": True,           # 최대 대기시간 후 강제 매수 여부
            
            # 🔥 뉴스 분석 설정 (새로 추가)
            "use_news_analysis": True,             # 뉴스 분석 기능 사용 여부 (기본값 False)
            "news_check_threshold": 35,             # 이 점수 이상일 때만 뉴스 체크
            "always_check_news": False,             # 점수와 관계없이 항상 뉴스 체크
            "news_cache_hours": 6,                  # 뉴스 캐시 유효 시간
            "news_weight": {
                "positive_multiplier": 0.15,         # 긍정 뉴스 가중치 (최대 15점)
                "negative_multiplier": 0.25          # 부정 뉴스 가중치 (최대 25점)
            },
            
            # 예산 설정 - 기존 구조 유지하되 일부 값만 최적화
            "use_absolute_budget": True,
            "absolute_budget_strategy": "proportional",
            "absolute_budget": 600000,              # 🎯 60만원으로 설정
            "initial_total_asset": 0,
            "budget_loss_tolerance": 0.2,
            "trade_budget_ratio": 0.9,             
            
            # 포지션 관리 - 일부만 최적화
            # "max_positions": 3,                     # 🎯 3종목으로 설정
            "min_stock_price": 3000,                # 기존 유지
            "max_stock_price": 200000,              # 기존 유지
            
            # 🎯 손익 관리 설정 - 백테스트 결과 반영
            "stop_loss_ratio": -0.04,               # -0.025 → -0.04 (완화)
            "take_profit_ratio": 0.08,              # 0.055 → 0.08 (상향)
            "trailing_stop_ratio": 0.025,           # 0.018 → 0.025 (보호 강화)
            "max_daily_loss": -0.06,                # -0.04 → -0.06 (완화)
            "max_daily_profit": 0.08,               # 0.06 → 0.08 (기회 확대)
            
            # 🎯 기술적 분석 설정 - 매수 기회 확대 → 제한
            "rsi_period": 14,
            "rsi_oversold": 35,
            "rsi_overbought": 75,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,

            # 🔥 전역 기본 매수 기준 상향
            "default_min_score": 40,  # 새로 추가

            # 적응형 전략 사용 설정 - 기존 유지
            "use_adaptive_strategy": True,
            "use_trend_filter": True,
            
            # 🎯 분봉 타이밍 관련 알림 설정
            "alert_intraday_wait": True,            # 분봉 대기 알림 사용 여부
            "alert_intraday_entry": True,           # 분봉 진입 알림 사용 여부
            "alert_candidate_summary": True,        # 대기 종목 요약 알림 사용 여부
            
            # 기타 설정 - 기존 유지
            "last_sector_update": datetime.datetime.now().strftime('%Y%m%d'),
            "bot_name": "TargetStockBot",           # 기존 이름 유지
            "use_discord_alert": True,
            "check_interval_minutes": 30            # 기본 체크 주기 (분) - 호환성 유지
        }

        # 파일 저장
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"🎯 분봉 타이밍 + 뉴스 분석 옵션 포함 설정 파일 생성 완료: {config_path}")
        logger.info(f"주요 설정:")
        logger.info(f"  - 분봉 타이밍: {'ON' if config['use_intraday_timing'] else 'OFF'}")
        logger.info(f"  - 뉴스 분석: {'ON' if config['use_news_analysis'] else 'OFF'}")
        logger.info(f"  - 예산: {config['absolute_budget']:,}원")
        # logger.info(f"  - 최대 종목수: {config['max_positions']}개")
        logger.info(f"  - 체크 주기: {config['intraday_check_interval']}초 (분봉 사용시)")
        logger.info(f"  - 뉴스 캐시: {config['news_cache_hours']}시간")
        logger.info(f"  - 모든 종목: 성장주 전략 적용")
        
        # 적응형 전략 파일 초기화
        try:
            adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
            adaptive_strategy.save_strategy()
            logger.info("적응형 전략 파일 초기화 완료")
        except Exception as e:
            logger.warning(f"적응형 전략 파일 초기화 중 오류 (무시): {str(e)}")
        
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

    # 🆕 미체결 주문 관리자 초기화
    initialize_pending_manager()
    
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
    # enabled_count = sum(1 for stock_config in config.target_stocks.values() if stock_config.get('enabled', True))
    # logger.info(f"활성화된 타겟 종목: {enabled_count}개")
    enabled_count = get_active_target_stock_count()
    logger.info(f"활성화된 타겟 종목: {enabled_count}개 (자동 계산)")

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
    last_pending_check = datetime.datetime.now()  # 🆕 미체결 주문 체크 시간
    
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
                msg = f"🔔 장 시작!\n"
                msg += get_budget_info_message()
                msg += f"\n타겟 종목: {enabled_count}개"

                # 🆕 미체결 주문 현황 추가 (라이브러리 사용)
                pending_status = pending_manager.get_pending_orders_status(trading_state)
                if pending_status['count'] > 0:
                    msg += f"\n미체결 주문: {pending_status['count']}개 (자동 관리 중)"
 
                logger.info(msg)
                discord_alert.SendMessage(msg)
                market_open_notified = True

            # 거래 시간이 아니면 대기
            if not is_trading_time:
                logger.info("장 시간 외입니다.")
                time.sleep(300)  # 5분 대기
                continue

            # 🆕 미체결 주문 자동 관리 (5분마다) - 라이브러리 사용
            if (now - last_pending_check).total_seconds() >= 300:
                logger.info("🔍 미체결 주문 자동 관리 실행")
                trading_state = pending_manager.auto_cancel_pending_orders(trading_state, max_pending_minutes=15)
                save_trading_state(trading_state)
                last_pending_check = now
            
            # 포지션 관리 (매도 신호 체크)
            logger.info("=== 타겟 종목 포지션 관리 ===")
            trading_state = process_positions(trading_state)
            save_trading_state(trading_state)

            # 🎯 분봉 타이밍 사용시에만 매수 대기 후보 관리
            if hasattr(trading_config, 'use_intraday_timing') and trading_config.use_intraday_timing:
                trading_state = process_buy_candidates(trading_state)
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
            if (now - last_status_report).seconds >= 3600:
                send_target_stock_status()
                
                # 🆕 미체결 주문 현황 보고 (라이브러리 사용)
                pending_status = pending_manager.get_pending_orders_status(trading_state)
                if pending_status['count'] > 0:
                    pending_msg = f"\n📋 미체결 주문 현황: {pending_status['count']}개\n"
                    for order in pending_status['orders']:
                        pending_msg += f"• {order['stock_name']}: {order['quantity']}주 ({order['elapsed_minutes']:.0f}분 경과)\n"
                    
                    logger.info(pending_msg)
                    discord_alert.SendMessage(pending_msg)
                
                last_status_report = now
            
            # 장 마감 후 일일 보고서
            if now.hour >= 15 and now.minute >= 30 and not daily_report_sent:
                send_daily_report(trading_state)
                
                # 🆕 미체결 주문 정리 보고서 (라이브러리 사용)
                pending_status = pending_manager.get_pending_orders_status(trading_state)
                if pending_status['count'] > 0:
                    final_pending_msg = f"📋 장 마감 미체결 주문 현황: {pending_status['count']}개\n"
                    for order in pending_status['orders']:
                        final_pending_msg += f"• {order['stock_name']}: {order['quantity']}주 @ {order['price']:,}원\n"
                    final_pending_msg += "→ 내일 장 시작 전 자동 정리됩니다."
                    
                    logger.info(final_pending_msg)
                    discord_alert.SendMessage(final_pending_msg)
                
                daily_report_sent = True

            # 30초 대기
            # time.sleep(30)

            # 🎯 분봉 타이밍 사용시 체크 주기 조정
            if hasattr(trading_config, 'use_intraday_timing') and trading_config.use_intraday_timing:
                check_interval = getattr(trading_config, 'intraday_check_interval', 10)
            else:
                check_interval = 30  # 기존 주기
                
            time.sleep(check_interval)

        except Exception as e:
            error_msg = f"⚠️ 메인 루프 에러: {str(e)}"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            time.sleep(60)  # 에러 발생 시 1분 대기

if __name__ == "__main__":
    # 실제 거래 모드로 설정
    Common.SetChangeMode()
    
    main()