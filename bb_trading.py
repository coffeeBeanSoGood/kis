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

import technical_analysis
technical_analysis.set_logger(logger)

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

def get_available_budget():
    """사용 가능한 예산 계산 (전략별 분기 처리)"""
    try:
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return 0
            
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        
        if total_money <= 0:
            logger.warning("계좌 총 자산이 0 이하입니다.")
            return 0
        
        if trading_config.use_absolute_budget:
            # 절대 금액 기반 예산
            absolute_budget = trading_config.absolute_budget
            strategy = trading_config.absolute_budget_strategy
            
            logger.info(f"💰 절대금액 예산 모드: {strategy}")
            
            if strategy == "strict":
                # 엄격 모드: 설정값 고정
                available_budget = min(absolute_budget, remain_money)
                
                logger.info(f"  - 설정 예산: {absolute_budget:,.0f}원 (고정)")
                logger.info(f"  - 현금 잔고: {remain_money:,.0f}원")
                logger.info(f"  - 사용가능: {available_budget:,.0f}원")
                
            elif strategy == "adaptive":
                # 적응형 모드: 손실 허용범위 내에서 조정
                loss_tolerance = trading_config.budget_loss_tolerance
                min_budget = absolute_budget * (1 - loss_tolerance)
                
                if total_money >= min_budget:
                    budget_target = absolute_budget
                else:
                    budget_target = max(total_money, min_budget)
                
                available_budget = min(budget_target, remain_money)
                
                logger.info(f"  - 기준 예산: {absolute_budget:,.0f}원")
                logger.info(f"  - 손실 허용: {loss_tolerance*100:.0f}%")
                logger.info(f"  - 최소 예산: {min_budget:,.0f}원")
                logger.info(f"  - 현재 자산: {total_money:,.0f}원")
                logger.info(f"  - 목표 예산: {budget_target:,.0f}원")
                logger.info(f"  - 사용가능: {available_budget:,.0f}원")
                
            elif strategy == "proportional":
                # 🎯 비례형 모드: 총자산 비례 조정
                initial_asset = trading_config.initial_total_asset
                
                if initial_asset <= 0:
                    # 최초 실행시 현재 총자산을 초기자산으로 설정
                    initial_asset = total_money
                    trading_config.config["initial_total_asset"] = initial_asset
                    trading_config.save_config()
                    logger.info(f"🎯 초기 총자산 설정: {initial_asset:,.0f}원")
                
                # 총자산 변화율 계산
                asset_ratio = total_money / initial_asset
                
                # 비례적으로 예산 조정
                adjusted_budget = absolute_budget * asset_ratio
                
                # 안전장치: 최소/최대 예산 설정
                min_budget = absolute_budget * 0.3   # 30%
                max_budget = absolute_budget * 3.0   # 300%
                adjusted_budget = max(min_budget, min(adjusted_budget, max_budget))
                
                # 현금 잔고 고려한 최종 예산
                available_budget = min(adjusted_budget, remain_money)
                
                # 상세 로깅
                performance = ((total_money - initial_asset) / initial_asset) * 100
                budget_change = ((adjusted_budget / absolute_budget) - 1) * 100
                
                logger.info(f"  - 기준 예산: {absolute_budget:,.0f}원")
                logger.info(f"  - 초기 자산: {initial_asset:,.0f}원")
                logger.info(f"  - 현재 자산: {total_money:,.0f}원")
                logger.info(f"  - 자산 성과: {performance:+.1f}%")
                logger.info(f"  - 예산 배율: {asset_ratio:.2f}배")
                logger.info(f"  - 조정 예산: {adjusted_budget:,.0f}원 ({budget_change:+.1f}%)")
                logger.info(f"  - 현금 잔고: {remain_money:,.0f}원")
                logger.info(f"  - 사용가능: {available_budget:,.0f}원")
                
            else:
                # 알 수 없는 전략: strict 모드로 대체
                logger.warning(f"알 수 없는 예산 전략: {strategy}, strict 모드로 대체")
                available_budget = min(absolute_budget, remain_money)
            
        else:
            # 비율 기반 예산 (기존 방식)
            budget_ratio = trading_config.trade_budget_ratio
            budget_by_ratio = total_money * budget_ratio
            available_budget = min(budget_by_ratio, remain_money)
            
            logger.info(f"📊 비율 기반 예산: {budget_ratio*100:.1f}%")
            logger.info(f"  - 총 자산: {total_money:,.0f}원")
            logger.info(f"  - 계산 예산: {budget_by_ratio:,.0f}원")
            logger.info(f"  - 사용가능: {available_budget:,.0f}원")
        
        return max(0, available_budget)
        
    except Exception as e:
        logger.error(f"예산 계산 중 에러: {str(e)}")
        return 0

def get_budget_info_message():
    """예산 정보 메시지 생성 (Proportional 모드 지원)"""
    try:
        balance = KisKR.GetBalance()
        if not balance:
            return "계좌 정보 조회 실패"
        
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        available_budget = get_available_budget()
        
        if trading_config.use_absolute_budget:
            # Proportional 모드 정보
            absolute_budget = trading_config.absolute_budget
            initial_asset = trading_config.config.get("initial_total_asset", 0)
            
            if initial_asset > 0:
                asset_ratio = total_money / initial_asset
                performance = ((total_money - initial_asset) / initial_asset) * 100
                
                msg = f"⚖️ 비례형 절대금액 예산 운용\n"
                msg += f"기준 예산: {absolute_budget:,.0f}원\n"
                msg += f"초기 자산: {initial_asset:,.0f}원\n"
                msg += f"현재 자산: {total_money:,.0f}원\n"
                msg += f"자산 성과: {performance:+.1f}%\n"
                msg += f"예산 배율: {asset_ratio:.2f}배\n"
                msg += f"현금 잔고: {remain_money:,.0f}원\n"
                msg += f"봇 운용 예산: {available_budget:,.0f}원"
            else:
                msg = f"⚖️ 비례형 절대금액 예산 운용 (초기화 중)\n"
                msg += f"기준 예산: {absolute_budget:,.0f}원\n"
                msg += f"현재 자산: {total_money:,.0f}원\n"
                msg += f"봇 운용 예산: {available_budget:,.0f}원"
        else:
            msg = f"📊 비율 기반 예산 운용\n"
            msg += f"설정 비율: {trading_config.trade_budget_ratio*100:.1f}%\n"
            msg += f"총 자산: {total_money:,.0f}원\n"
            msg += f"현금 잔고: {remain_money:,.0f}원\n"
            msg += f"봇 운용 예산: {available_budget:,.0f}원"
        
        return msg
        
    except Exception as e:
        logger.error(f"예산 정보 메시지 생성 중 에러: {str(e)}")
        return "예산 정보 조회 실패"
    
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


def detect_market_environment():
    """현재 시장 환경 감지 - 개선된 로직"""
    try:
        # 코스피 지수 데이터 조회 (KODEX 200 ETF)
        market_index_code = "069500"
        market_data = KisKR.GetOhlcvNew(market_index_code, 'D', 60, adj_ok=1)
        
        if market_data is None or market_data.empty:
            return "sideways"  # 기본값
        
        # 이동평균선 계산
        market_data['MA5'] = market_data['close'].rolling(window=5).mean()
        market_data['MA20'] = market_data['close'].rolling(window=20).mean()
        market_data['MA60'] = market_data['close'].rolling(window=60).mean()
        
        # RSI 계산 추가
        market_data['RSI'] = TechnicalIndicators.calculate_rsi(market_data)
        
        # MACD 계산 추가
        market_data[['MACD', 'Signal', 'Histogram']] = TechnicalIndicators.calculate_macd(
            market_data, 
            fast_period=12, 
            slow_period=26, 
            signal_period=9
        )
        
        # 볼린저 밴드 계산 추가
        market_data[['MiddleBand', 'UpperBand', 'LowerBand']] = TechnicalIndicators.calculate_bollinger_bands(
            market_data,
            period=20,
            num_std=2.0
        )
        
        # 추세 강도 계산 (ADX 대용)
        trend_strength = abs((market_data['MA20'].iloc[-1] / market_data['MA20'].iloc[-21] - 1) * 100)
        
        # 이동평균선 방향성
        ma5_slope = (market_data['MA5'].iloc[-1] / market_data['MA5'].iloc[-6] - 1) * 100
        ma20_slope = (market_data['MA20'].iloc[-1] / market_data['MA20'].iloc[-21] - 1) * 100
        
        # 변동성 측정 (볼린저 밴드 폭)
        recent_bandwidth = (market_data['UpperBand'].iloc[-1] - market_data['LowerBand'].iloc[-1]) / market_data['MiddleBand'].iloc[-1] * 100
        avg_bandwidth = ((market_data['UpperBand'] - market_data['LowerBand']) / market_data['MiddleBand']).rolling(window=20).mean().iloc[-1] * 100
        
        # 볼륨 트렌드 (거래량 증가 여부)
        volume_trend = (market_data['volume'].iloc[-5:].mean() / market_data['volume'].iloc[-20:-5].mean()) > 1.0
        
        # MACD 히스토그램 방향
        histogram_direction = market_data['Histogram'].diff().iloc[-1] > 0
        
        # 최근 연속 상승/하락 일수 계산
        price_changes = market_data['close'].pct_change().iloc[-10:]
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
        if market_data['MA5'].iloc[-1] > market_data['MA20'].iloc[-1]: uptrend_score += 1
        if market_data['close'].iloc[-1] > market_data['MA20'].iloc[-1]: uptrend_score += 1
        if market_data['RSI'].iloc[-1] > 55: uptrend_score += 1
        if histogram_direction: uptrend_score += 1
        if volume_trend: uptrend_score += 1
        if consecutive_up >= 3: uptrend_score += 1
        
        # 하락장 지표 점수
        downtrend_score = 0
        if ma5_slope < -0.8: downtrend_score += 2
        if ma20_slope < -0.3: downtrend_score += 2
        if market_data['MA5'].iloc[-1] < market_data['MA20'].iloc[-1]: downtrend_score += 1
        if market_data['close'].iloc[-1] < market_data['MA20'].iloc[-1]: downtrend_score += 1
        if market_data['RSI'].iloc[-1] < 45: downtrend_score += 1
        if not histogram_direction: downtrend_score += 1
        if not volume_trend: downtrend_score += 1
        if consecutive_down >= 3: downtrend_score += 1
        
        # 횡보장 지표 - 변동성 관련
        sideways_score = 0
        if abs(ma5_slope) < 0.5: sideways_score += 2  # 단기 이동평균 기울기가 완만함
        if abs(ma20_slope) < 0.3: sideways_score += 2  # 중기 이동평균 기울기가 완만함
        if recent_bandwidth < avg_bandwidth: sideways_score += 2  # 최근 변동성이 평균보다 낮음
        if market_data['RSI'].iloc[-1] > 40 and market_data['RSI'].iloc[-1] < 60: sideways_score += 2  # RSI가 중간 영역
        if abs(market_data['close'].iloc[-1] - market_data['MA20'].iloc[-1]) / market_data['MA20'].iloc[-1] < 0.02: sideways_score += 2  # 종가가 20일선 근처
        
        # 점수 기반 시장 환경 판단 (개선된 알고리즘)
        logger.info(f"시장 환경 점수 - 상승: {uptrend_score}, 하락: {downtrend_score}, 횡보: {sideways_score}")
        
        # 명확한 상승장/하락장 조건
        if uptrend_score >= 7 and uptrend_score > downtrend_score + 3 and uptrend_score > sideways_score + 2:
            result = "uptrend"
        elif downtrend_score >= 7 and downtrend_score > uptrend_score + 3 and downtrend_score > sideways_score + 2:
            result = "downtrend"
        # 횡보장 조건 강화
        elif sideways_score >= 6 and abs(uptrend_score - downtrend_score) <= 2:  # 상승/하락 점수 차이가 작고 횡보 점수가 높은 경우
            result = "sideways"
        # 약한 상승/하락 추세
        elif uptrend_score > downtrend_score + 2:
            result = "uptrend"
        elif downtrend_score > uptrend_score + 2:
            result = "downtrend"
        # 그 외는 횡보장으로 판단
        else:
            result = "sideways"
        
        logger.info(f"시장 환경 판정: {result}")
        return result
        
    except Exception as e:
        logger.warning(f"시장 환경 감지 중 오류: {str(e)}")
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
   """매수 신호 분석 (적응형 전략 적용)"""
   try:
       # 적응형 전략 적용
       if trading_config.use_adaptive_strategy:
           # 종목 환경만 사용 (더 정확)
           stock_env = detect_stock_environment(stock_data['stock_code'])
           
           # 적응형 전략 인스턴스 생성
           adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
           
           # 종목별 맞춤 전략 가져오기
           stock_strategy = adaptive_strategy.get_stock_strategy(stock_data['stock_code'], stock_env)
           
           # 전략에 따른 파라미터 조정
           rsi_oversold = target_config.get('rsi_oversold', trading_config.rsi_oversold) + stock_strategy.get("rsi_threshold_adjustment", 0)
           min_score = target_config.get('min_score', 70) - stock_strategy.get("required_signals", 2) * 5
       else:
           # 기존 방식 사용
           rsi_oversold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
           min_score = target_config.get('min_score', 70)
       
       signals = []
       score = 0
       
       stock_code = stock_data['stock_code']
       current_price = stock_data['current_price']
       rsi = stock_data['rsi']
       
       # 1. RSI 과매도 신호 (조정된 임계값 사용)
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
       
       # 7. 적응형 전략 추가 신호 (시장 환경별)
       if trading_config.use_adaptive_strategy:
           # 상승장에서의 추가 매수 신호
           if stock_env == "uptrend":
               # 골든크로스 직후 매수 신호
               if ma5 > ma20 and abs((ma5 / ma20) - 1) < 0.01:  # 5일선이 20일선을 막 돌파
                   score += 15
                   signals.append("골든크로스 직후 (+15)")
               
               # 상승 추세에서 일시적 조정 후 반등
               if current_price > ma20 and current_price < ma5:
                   score += 10
                   signals.append("상승 추세 중 조정 후 반등 기대 (+10)")
           
           # 하락장에서의 안전 매수 신호
           elif stock_env == "downtrend":
               # 극도의 과매도에서만 매수
               if rsi <= 20:
                   score += 15
                   signals.append("극도 과매도 (+15)")
               else:
                   score -= 10  # 하락장에서는 점수 감점
                   signals.append("하락장 위험 (-10)")
           
           # 횡보장에서의 매수 신호
           else:  # sideways
               # 볼린저밴드 활용 강화
               if bb_position == "lower":
                   score += 10
                   signals.append("횡보장 밴드 하단 매수 (+10)")
       
       # 매수 신호 판정 (적응형 전략 고려)
       is_buy_signal = score >= min_score
       
       # 추가 필터링 (적응형 전략)
       if trading_config.use_adaptive_strategy and is_buy_signal:
           required_signals = stock_strategy.get("required_signals", 2)
           signal_count = len(signals)
           
           if signal_count < required_signals:
               is_buy_signal = False
               signals.append(f"신호 부족 ({signal_count}/{required_signals})")
       
       return {
           'is_buy_signal': is_buy_signal,
           'score': score,
           'min_score': min_score,
           'signals': signals,
           'bb_position': bb_position,
           'market_environment': stock_env if trading_config.use_adaptive_strategy else "unknown",
           'analysis': {
               'rsi': rsi,
               'rsi_threshold': rsi_oversold,
               'macd_cross': macd > macd_signal,
               'price_vs_bb_lower': (current_price / stock_data['bb_lower'] - 1) * 100 if stock_data['bb_lower'] > 0 else 0,
               'adaptive_strategy_applied': trading_config.use_adaptive_strategy,
               'trend_filter_applied': trading_config.use_trend_filter
           }
       }
       
   except Exception as e:
       logger.error(f"매수 신호 분석 중 에러: {str(e)}")
       return {'is_buy_signal': False, 'score': 0, 'signals': [f"분석 오류: {str(e)}"]}
   
def analyze_sell_signal(stock_data, position, target_config):
    """매도 신호 분석 (적응형 전략 적용)"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position['entry_price']
        
        # 수익률 계산
        profit_rate = (current_price - entry_price) / entry_price
        
        # 적응형 전략 적용
        if trading_config.use_adaptive_strategy:
            # 시장 환경 감지
            market_env = detect_market_environment()
            
            # 적응형 전략 인스턴스 생성
            adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
            
            # 종목별 맞춤 전략 가져오기
            stock_strategy = adaptive_strategy.get_stock_strategy(stock_code, market_env)
            
            # 전략에 따른 파라미터 조정
            profit_target = target_config.get('profit_target', trading_config.take_profit_ratio) * stock_strategy.get("profit_target_multiplier", 1.0)
            stop_loss = target_config.get('stop_loss', trading_config.stop_loss_ratio) * stock_strategy.get("stop_loss_multiplier", 1.0)
            trailing_stop = target_config.get('trailing_stop', trading_config.trailing_stop_ratio) * stock_strategy.get("trailing_stop_multiplier", 1.0)
            rsi_overbought = target_config.get('rsi_overbought', trading_config.rsi_overbought) + stock_strategy.get("rsi_threshold_adjustment", 0)
        else:
            # 기존 방식 사용
            profit_target = target_config.get('profit_target', trading_config.take_profit_ratio)
            stop_loss = target_config.get('stop_loss', trading_config.stop_loss_ratio)
            trailing_stop = target_config.get('trailing_stop', trading_config.trailing_stop_ratio)
            rsi_overbought = target_config.get('rsi_overbought', trading_config.rsi_overbought)
        
        # 1. 손익 관리 신호 (최우선 - 조정된 파라미터 사용)
        if profit_rate <= stop_loss:
            return {
                'is_sell_signal': True,
                'sell_type': 'stop_loss',
                'reason': f"손절 실행 {profit_rate*100:.1f}% (기준: {stop_loss*100:.1f}%)",
                'urgent': True,
                'market_environment': market_env if trading_config.use_adaptive_strategy else "unknown"
            }
        
        if profit_rate >= profit_target:
            return {
                'is_sell_signal': True,
                'sell_type': 'take_profit',
                'reason': f"익절 실행 {profit_rate*100:.1f}% (기준: {profit_target*100:.1f}%)",
                'urgent': True,
                'market_environment': market_env if trading_config.use_adaptive_strategy else "unknown"
            }
        
        # 2. 트레일링 스탑 확인 (조정된 파라미터 사용)
        if 'high_price' in position:
            trailing_loss = (position['high_price'] - current_price) / position['high_price']
            if trailing_loss >= trailing_stop:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop',
                    'reason': f"트레일링 스탑 {trailing_loss*100:.1f}% (기준: {trailing_stop*100:.1f}%)",
                    'urgent': True,
                    'market_environment': market_env if trading_config.use_adaptive_strategy else "unknown"
                }
        
        # 3. 기술적 분석 기반 매도 신호
        signals = []
        score = 0
        
        # RSI 과매수 (조정된 임계값 사용)
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
        
        # 4. 적응형 전략 추가 매도 신호 (시장 환경별)
        if trading_config.use_adaptive_strategy:
            # 상승장에서의 매도 신호 (더 관대하게)
            if market_env == "uptrend":
                # 상승장에서는 매도를 늦춰서 더 많은 수익 추구
                if profit_rate > profit_target * 0.7:  # 목표의 70% 달성시에만 기술적 매도 고려
                    score *= 0.8  # 매도 점수 20% 감소
                    signals.append("상승장 매도 신호 완화")
                else:
                    score *= 0.5  # 수익이 충분하지 않으면 매도 점수 50% 감소
                    signals.append("상승장 수익 부족으로 매도 신호 억제")
            
            # 하락장에서의 매도 신호 (더 빠르게)
            elif market_env == "downtrend":
                # 하락장에서는 빠른 매도로 손실 최소화
                if profit_rate > 0:  # 수익이 있으면 빠른 매도
                    score += 20
                    signals.append("하락장 수익 보존 매도")
                elif profit_rate > stop_loss * 0.5:  # 손실이 작으면 조기 매도
                    score += 15
                    signals.append("하락장 손실 확대 방지 매도")
            
            # 횡보장에서의 매도 신호 (밴드 활용)
            else:  # sideways
                # 볼린저밴드 상단에서 적극적 매도
                if current_price >= stock_data['bb_upper'] * 0.98:
                    score += 10
                    signals.append("횡보장 밴드 상단 매도")
        
        # 기술적 매도 신호 판정 (적응형 전략 고려)
        if trading_config.use_adaptive_strategy:
            # 시장 환경에 따른 매도 기준 조정
            if market_env == "uptrend":
                # 상승장: 수익 상태에서만 낮은 점수로 매도, 손실에서는 높은 점수 요구
                if profit_rate > 0.01:
                    is_sell_signal = score >= 60  # 기존 70에서 낮춤
                else:
                    is_sell_signal = score >= 90  # 기존 85에서 높임
            elif market_env == "downtrend":
                # 하락장: 더 빠른 매도
                if profit_rate > 0:
                    is_sell_signal = score >= 50  # 수익시 더 빨리 매도
                else:
                    is_sell_signal = score >= 70  # 손실시에도 빨리 매도
            else:  # sideways
                # 횡보장: 기본 기준 사용
                if profit_rate > 0.01:
                    is_sell_signal = score >= 70
                else:
                    is_sell_signal = score >= 85
        else:
            # 기존 방식 사용
            if profit_rate > 0.01:
                is_sell_signal = score >= 70
            else:
                is_sell_signal = score >= 85
        
        if is_sell_signal:
            return {
                'is_sell_signal': True,
                'sell_type': 'technical',
                'reason': f"기술적 매도신호 (점수: {score}): {', '.join(signals)}",
                'urgent': False,
                'profit_rate': profit_rate,
                'market_environment': market_env if trading_config.use_adaptive_strategy else "unknown",
                'adaptive_strategy_applied': trading_config.use_adaptive_strategy
            }
        
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"보유 지속 (수익률: {profit_rate*100:.1f}%, 기술점수: {score})",
            'urgent': False,
            'profit_rate': profit_rate,
            'market_environment': market_env if trading_config.use_adaptive_strategy else "unknown",
            'adaptive_strategy_applied': trading_config.use_adaptive_strategy
        }
        
    except Exception as e:
        logger.error(f"매도 신호 분석 중 에러: {str(e)}")
        return {'is_sell_signal': False, 'sell_type': None, 'reason': f'분석 오류: {str(e)}'}

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
    """포지션 크기 계산 (수정된 버전 - 예산 로직 개선)"""
    try:
        # 1. 기본 검증
        if stock_price <= 0:
            logger.warning("주가가 0 이하입니다.")
            return 0
            
        if available_budget <= 0:
            logger.warning("사용 가능한 예산이 없습니다.")
            return 0
        
        # 2. 실제 사용 가능한 예산 재확인 (최신 정보로)
        current_available_budget = get_available_budget()
        
        # 전달받은 예산과 현재 예산 중 작은 값 사용 (안전장치)
        usable_budget = min(available_budget, current_available_budget)
        
        if usable_budget <= 0:
            logger.warning("실제 사용 가능한 예산이 없습니다.")
            return 0
        
        logger.info(f"포지션 계산용 예산: {usable_budget:,.0f}원")
        
        # 3. 종목별 할당 비율 적용
        allocation_ratio = target_config.get('allocation_ratio', 0.125)  # 기본 12.5%
        
        # 할당 비율 검증 (0.01% ~ 50% 범위)
        allocation_ratio = max(0.0001, min(0.5, allocation_ratio))
        
        allocated_budget = usable_budget * allocation_ratio
        logger.info(f"할당 예산: {allocated_budget:,.0f}원 (비율: {allocation_ratio*100:.1f}%)")
        
        # 4. 최소 주문 금액 체크
        min_order_amount = target_config.get('min_order_amount', 10000)  # 기본 1만원
        if allocated_budget < min_order_amount:
            logger.info(f"할당 예산이 최소 주문 금액({min_order_amount:,}원)보다 작습니다.")
            return 0
        
        # 5. 최대 주문 금액 제한 (리스크 관리)
        max_order_amount = target_config.get('max_order_amount', usable_budget * 0.2)  # 기본 20% 제한
        allocated_budget = min(allocated_budget, max_order_amount)
        
        # 6. 기본 수량 계산
        base_quantity = int(allocated_budget / stock_price)
        logger.info(f"기본 계산 수량: {base_quantity}주")
        
        if base_quantity <= 0:
            logger.info("계산된 수량이 0 이하입니다.")
            return 0
        
        # 7. 수수료 고려한 실제 필요 금액 계산
        estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
        total_needed = (stock_price * base_quantity) + estimated_fee
        
        # 8. 수수료 포함해서 예산 초과하면 수량 조정
        while total_needed > allocated_budget and base_quantity > 0:
            base_quantity -= 1
            if base_quantity > 0:
                estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
                total_needed = (stock_price * base_quantity) + estimated_fee
            else:
                break
        
        # 9. 최종 검증
        if base_quantity <= 0:
            logger.info("수수료 고려 후 매수 가능한 수량이 없습니다.")
            return 0
        
        # 10. 종목별 최소/최대 수량 제한 적용
        min_quantity = target_config.get('min_quantity', 1)
        max_quantity = target_config.get('max_quantity', float('inf'))
        
        final_quantity = max(min_quantity, min(base_quantity, max_quantity))
        
        # 11. 최종 금액 검증
        final_amount = stock_price * final_quantity
        final_fee = calculate_trading_fee(stock_price, final_quantity, True)
        final_total = final_amount + final_fee
        
        if final_total > allocated_budget:
            logger.warning(f"최종 필요금액({final_total:,.0f}원)이 할당예산({allocated_budget:,.0f}원)을 초과합니다.")
            return 0
        
        # 12. 로깅
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
                        
                        # 🔥 새로 추가: 적응형 전략 학습
                        if trading_config.use_adaptive_strategy:
                            try:
                                # 매도 시점의 시장 환경 확인
                                market_env = sell_analysis.get('market_environment', 'sideways')
                                
                                # 적응형 전략 업데이트
                                adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
                                adaptive_strategy.update_performance(
                                    stock_code, 
                                    market_env, 
                                    win=(net_profit > 0)
                                )
                                
                                win_lose = "승리" if net_profit > 0 else "패배"
                                logger.info(f"🧠 적응형 전략 학습 완료: {stock_code} ({market_env}) - {win_lose}")
                                
                            except Exception as e:
                                logger.error(f"적응형 전략 학습 중 오류: {str(e)}")
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
    """매수 기회 실행 (수정된 버전 - 새로운 예산 로직 적용)"""
    try:
        if not buy_opportunities:
            return trading_state
        
        # 새로운 예산 계산 함수 사용
        available_budget = get_available_budget()
        
        if available_budget <= 0:
            logger.info("사용 가능한 예산이 없습니다.")
            return trading_state
        
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
        
        logger.info(f"매수 실행 준비:")
        logger.info(f"  - 사용 가능 예산: {available_budget:,.0f}원")
        logger.info(f"  - 현재 보유 종목: {current_positions}개/{trading_config.max_positions}개")
        logger.info(f"  - 추가 매수 가능: {max_new_positions}개")
        
        # 상위 종목들에 대해 매수 실행
        for i, opportunity in enumerate(buy_opportunities[:max_new_positions]):
            try:
                stock_code = opportunity['stock_code']
                stock_name = opportunity['stock_name']
                stock_price = opportunity['price']
                target_config = opportunity['target_config']
                
                # 매수 전 예산 재확인 (실시간)
                current_budget = get_available_budget()
                if current_budget <= 0:
                    logger.info("예산 소진으로 매수 중단")
                    break
                
                # 포지션 크기 계산 (현재 예산으로)
                quantity = calculate_position_size(target_config, current_budget, stock_price)
                
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
                    msg += f"손절률: {target_config.get('stop_loss', trading_config.stop_loss_ratio)*100:.1f}%\n"
                    msg += f"남은 예산: {get_available_budget():,.0f}원"
                    
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

# create_config_file 함수도 Proportional 모드로 수정
def create_config_file(config_path: str = "target_stock_config.json") -> None:
    """기본 설정 파일 생성 (Proportional 모드 적용)"""
    try:
        logger.info("종목 특성 기반 설정 파일 생성 시작...")
        
        # 기본 타겟 종목들 정의
        sample_codes = ["034020", "272210", "267250"]
        
        # 특성별 파라미터 매핑
        characteristic_params = {
            "growth": {
                "allocation_ratio": 0.15,
                "profit_target": 0.07,
                "stop_loss": -0.035,
                "rsi_oversold": 25,
                "rsi_overbought": 75,
                "min_score": 65,
                "trailing_stop": 0.025
            },
            "value": {
                "allocation_ratio": 0.12,
                "profit_target": 0.045,
                "stop_loss": -0.02,
                "rsi_oversold": 35,
                "rsi_overbought": 65,
                "min_score": 70,
                "trailing_stop": 0.015
            },
            "balanced": {
                "allocation_ratio": 0.10,
                "profit_target": 0.055,
                "stop_loss": -0.025,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "min_score": 70,
                "trailing_stop": 0.018
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
                
                # 간단한 특성 할당
                if i == 0:
                    char_type = "growth"
                elif i == len(sample_codes) - 1:
                    char_type = "value"
                else:
                    char_type = "balanced"
                
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
                target_stocks[stock_code] = characteristic_params["balanced"].copy()
                target_stocks[stock_code].update({
                    "name": f"종목{stock_code}",
                    "sector": "Unknown",
                    "enabled": True,
                    "characteristic_type": "balanced"
                })
        
        # 전체 설정 구성 (Proportional 모드 적용)
        config = {
            "target_stocks": target_stocks,
            
            # 예산 설정 - Proportional 모드
            "use_absolute_budget": True,                    # 절대금액 모드 사용
            "absolute_budget_strategy": "proportional",     # 🎯 비례형 전략
            "absolute_budget": 10000000,                    # 기준 예산 1천만원
            "initial_total_asset": 0,                       # 최초 실행시 자동 설정
            "budget_loss_tolerance": 0.2,                   # adaptive 모드용 (사용안함)
            "trade_budget_ratio": 0.90,                     # 비율모드 백업용
            
            # 나머지 설정들은 기존과 동일...
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
            
            # 적응형 전략 사용 설정
            "use_adaptive_strategy": True,
            "use_trend_filter": True,
            
            # 기타 설정
            "last_sector_update": datetime.datetime.now().strftime('%Y%m%d'),
            "bot_name": "TargetStockBot",
            "use_discord_alert": True,
            "check_interval_minutes": 30
        }

        # 파일 저장
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"🎯 Proportional 모드 설정 파일 생성 완료: {config_path}")
        logger.info(f"등록된 종목 수: {len(target_stocks)}개")
        logger.info(f"예산 관리: 비례형 절대금액 모드 (기준: {config['absolute_budget']:,}원)")
        
        # 적응형 전략 파일 초기화
        adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
        adaptive_strategy.save_strategy()
        
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
                msg = f"🔔 장 시작!\n"
                msg += get_budget_info_message()
                msg += f"\n타겟 종목: {enabled_count}개"
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