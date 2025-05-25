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
    """사용 가능한 예산 계산 (전략별 분기 처리) - 수정된 버전"""
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
                # 🔥 수정된 비례형 모드: 점진적 성과 기반 조정
                initial_asset = trading_config.initial_total_asset
                
                if initial_asset <= 0:
                    # 최초 실행시 현재 총자산을 초기자산으로 설정
                    initial_asset = total_money
                    trading_config.config["initial_total_asset"] = initial_asset
                    trading_config.save_config()
                    logger.info(f"🎯 초기 총자산 설정: {initial_asset:,.0f}원")
                
                # 성과율 계산
                performance = (total_money - initial_asset) / initial_asset
                
                # 🎯 점진적 배율 계산 (안전한 방식)
                if performance > 0.2:  # 20% 이상 수익
                    # 큰 수익에서는 보수적으로 증가
                    multiplier = min(1.4, 1.0 + performance * 0.3)
                elif performance > 0.1:  # 10~20% 수익
                    # 중간 수익에서는 적당히 증가
                    multiplier = 1.0 + performance * 0.5
                elif performance > 0.05:  # 5~10% 수익
                    # 작은 수익에서는 비례 증가
                    multiplier = 1.0 + performance * 0.8
                elif performance > -0.05:  # ±5% 내
                    # 변동 없음
                    multiplier = 1.0
                elif performance > -0.1:  # -5~-10% 손실
                    # 작은 손실에서는 소폭 감소만
                    multiplier = max(0.95, 1.0 + performance * 0.2)
                elif performance > -0.2:  # -10~-20% 손실  
                    # 중간 손실에서는 적당히 감소
                    multiplier = max(0.85, 1.0 + performance * 0.15)
                else:  # -20% 이상 손실
                    # 큰 손실에서는 최소한만 감소
                    multiplier = max(0.7, 1.0 + performance * 0.1)
                
                # 조정된 예산 계산
                adjusted_budget = absolute_budget * multiplier
                
                # 최종 사용가능 예산
                available_budget = min(adjusted_budget, remain_money)
                
                # 상세 로깅
                performance_pct = performance * 100
                budget_change = ((multiplier - 1.0) * 100)
                
                logger.info(f"  - 기준 예산: {absolute_budget:,.0f}원")
                logger.info(f"  - 초기 자산: {initial_asset:,.0f}원")
                logger.info(f"  - 현재 자산: {total_money:,.0f}원")
                logger.info(f"  - 자산 성과: {performance_pct:+.1f}%")
                logger.info(f"  - 예산 배율: {multiplier:.3f}배 ({budget_change:+.1f}%)")
                logger.info(f"  - 조정 예산: {adjusted_budget:,.0f}원")
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
    """예산 정보 메시지 생성 (수정된 버전)"""
    try:
        balance = KisKR.GetBalance()
        if not balance:
            return "계좌 정보 조회 실패"
        
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        available_budget = get_available_budget()
        
        if trading_config.use_absolute_budget:
            strategy = trading_config.absolute_budget_strategy
            absolute_budget = trading_config.absolute_budget
            
            if strategy == "proportional":
                # 🔥 수정된 Proportional 모드 메시지
                initial_asset = trading_config.initial_total_asset
                
                if initial_asset > 0:
                    performance = (total_money - initial_asset) / initial_asset
                    performance_pct = performance * 100
                    
                    # 배율 계산 (get_available_budget와 동일한 로직)
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
                    
                    budget_change = ((multiplier - 1.0) * 100)
                    
                    msg = f"⚖️ 점진적 비례형 예산 운용\n"
                    msg += f"기준 예산: {absolute_budget:,.0f}원\n"
                    msg += f"초기 자산: {initial_asset:,.0f}원\n"
                    msg += f"현재 자산: {total_money:,.0f}원\n"
                    msg += f"자산 성과: {performance_pct:+.1f}%\n"
                    msg += f"예산 배율: {multiplier:.3f}배 ({budget_change:+.1f}%)\n"
                    msg += f"현금 잔고: {remain_money:,.0f}원\n"
                    msg += f"봇 운용 예산: {available_budget:,.0f}원"
                else:
                    msg = f"⚖️ 점진적 비례형 예산 운용 (초기화 중)\n"
                    msg += f"기준 예산: {absolute_budget:,.0f}원\n"
                    msg += f"현재 자산: {total_money:,.0f}원\n"
                    msg += f"봇 운용 예산: {available_budget:,.0f}원"
            
            elif strategy == "adaptive":
                # Adaptive 모드 메시지 (기존과 동일)
                loss_tolerance = trading_config.budget_loss_tolerance
                min_budget = absolute_budget * (1 - loss_tolerance)
                
                msg = f"🔄 적응형 절대금액 예산 운용\n"
                msg += f"기준 예산: {absolute_budget:,.0f}원\n"
                msg += f"손실 허용: {loss_tolerance*100:.0f}%\n"
                msg += f"최소 예산: {min_budget:,.0f}원\n"
                msg += f"현재 자산: {total_money:,.0f}원\n"
                msg += f"현금 잔고: {remain_money:,.0f}원\n"
                msg += f"봇 운용 예산: {available_budget:,.0f}원"
            
            else:  # strict 모드
                # Strict 모드 메시지 (기존과 동일)
                msg = f"🔒 엄격형 절대금액 예산 운용\n"
                msg += f"설정 예산: {absolute_budget:,.0f}원 (고정)\n"
                msg += f"현재 자산: {total_money:,.0f}원\n"
                msg += f"현금 잔고: {remain_money:,.0f}원\n"
                msg += f"봇 운용 예산: {available_budget:,.0f}원"
        
        else:
            # 비율 기반 예산 운용 (기존과 동일)
            msg = f"📊 비율 기반 예산 운용\n"
            msg += f"설정 비율: {trading_config.trade_budget_ratio*100:.1f}%\n"
            msg += f"총 자산: {total_money:,.0f}원\n"
            msg += f"현금 잔고: {remain_money:,.0f}원\n"
            msg += f"봇 운용 예산: {available_budget:,.0f}원"
        
        return msg
        
    except Exception as e:
        logger.error(f"예산 정보 메시지 생성 중 에러: {str(e)}")
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
    """매수 신호 분석 - 고수익률 버전 (기회 확대)"""
    try:
        signals = []
        score = 0
        warning_reasons = []
        
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        rsi = stock_data['rsi']
        df = stock_data['ohlcv_data']
        
        # 🟡 완화된 경고 시스템 (점수 감점)
        if len(df) >= 5:
            recent_drop_5d = (df['close'].iloc[-1] / df['close'].iloc[-6] - 1) * 100
            recent_drop_3d = (df['close'].iloc[-1] / df['close'].iloc[-4] - 1) * 100
            
            if recent_drop_5d < -25:  # 20% → 25% 완화
                score -= 12  # 15 → 12 완화
                warning_reasons.append(f"5일간 급락 {recent_drop_5d:.1f}% (-12점)")
            elif recent_drop_3d < -15:  # 12% → 15% 완화
                score -= 8  # 10 → 8 완화
                warning_reasons.append(f"3일간 급락 {recent_drop_3d:.1f}% (-8점)")
        
        if rsi > 85:  # 80 → 85 완화
            score -= 15  # 20 → 15 완화
            warning_reasons.append(f"극도 과매수 RSI {rsi:.1f} (-15점)")
        elif rsi > 80:  # 75 → 80 완화
            score -= 8  # 10 → 8 완화
            warning_reasons.append(f"과매수 RSI {rsi:.1f} (-8점)")
        
        # 🚀 3단계: 추가 매수 신호들
        
        # 1) 연속 하락 후 반등 신호
        if len(df) >= 5:
            consecutive_down = 0
            for i in range(1, 4):
                if df['close'].iloc[-i] < df['close'].iloc[-i-1]:
                    consecutive_down += 1
                else:
                    break
            
            if consecutive_down >= 2 and df['close'].iloc[-1] > df['close'].iloc[-2]:
                score += 25
                signals.append(f"연속 하락 후 반등 ({consecutive_down}일 하락) (+25)")
        
        # 2) 거래량 급증 + 가격 상승
        if len(df) >= 10:
            recent_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(10).mean().iloc[-1]
            volume_surge = recent_volume / avg_volume if avg_volume > 0 else 1
            price_change = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100
            
            if volume_surge >= 1.3 and price_change > 0.5:  # 기준 완화
                score += 20
                signals.append(f"거래량 급증 + 상승 ({volume_surge:.1f}배, +{price_change:.1f}%) (+20)")
        
        # 3) 기술적 바닥 패턴
        if len(df) >= 10:
            recent_low = df['low'].iloc[-10:].min()
            if current_price <= recent_low * 1.08:  # 5% → 8% 완화
                score += 15
                signals.append("기술적 바닥 근처 (+15)")
        
        # 4) 기존 신호들 (기준 완화)
        
        # RSI 기반 신호
        rsi_oversold = target_config.get('rsi_oversold', 55)  # 50 → 55 완화
        if rsi <= rsi_oversold - 20:  # 15 → 20 완화
            score += 30
            signals.append(f"RSI 극과매도 {rsi:.1f} (+30)")
        elif rsi <= rsi_oversold - 10:  # 추가
            score += 25
            signals.append(f"RSI 강과매도 {rsi:.1f} (+25)")
        elif rsi <= rsi_oversold:
            score += 20
            signals.append(f"RSI 과매도 {rsi:.1f} (+20)")
        elif rsi <= rsi_oversold + 10:  # 완화
            score += 12
            signals.append(f"RSI 조정 구간 {rsi:.1f} (+12)")
        
        # 볼린저밴드 신호
        bb_position = "middle"
        if current_price <= stock_data['bb_lower'] * 1.08:  # 5% → 8% 완화
            score += 25
            signals.append("볼린저밴드 하단 근처 (+25)")
            bb_position = "lower"
        elif current_price <= stock_data['bb_middle'] * 1.03:  # 완화
            score += 18
            signals.append("볼린저밴드 중간선 근처 (+18)")
            bb_position = "middle"
        elif current_price <= stock_data['bb_middle']:
            score += 12
            signals.append("볼린저밴드 중간선 하단 (+12)")
            bb_position = "below_middle"
        
        # MACD 신호
        macd = stock_data['macd']
        macd_signal = stock_data['macd_signal']
        macd_histogram = stock_data['macd_histogram']
        
        if len(df) >= 3:
            if macd > macd_signal and macd_histogram > 0:
                score += 20
                signals.append("MACD 골든크로스 + 히스토그램 상승 (+20)")
            elif macd > macd_signal:
                score += 15
                signals.append("MACD 골든크로스 (+15)")
            elif macd_histogram > 0:
                score += 10
                signals.append("MACD 히스토그램 상승 (+10)")
        
        # 이동평균선 신호
        ma5 = stock_data['ma5']
        ma20 = stock_data['ma20']
        ma60 = stock_data['ma60']
        
        if ma5 > ma20 > ma60:
            strength = ((ma5 - ma60) / ma60) * 100
            if strength > 2:  # 3% → 2% 완화
                score += 18
                signals.append("강한 정배열 (+18)")
            else:
                score += 12
                signals.append("정배열 (+12)")
        elif ma5 > ma20:
            score += 10
            signals.append("단기 상승 (+10)")
        elif ma5 > ma20 * 0.99:  # 거의 근접 (완화)
            score += 8
            signals.append("골든크로스 임박 (+8)")
        
        # 거래량 신호
        if len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume_20d = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = recent_volume / avg_volume_20d if avg_volume_20d > 0 else 1
            
            if volume_ratio >= 1.5:  # 1.8 → 1.5 완화
                score += 15
                signals.append(f"거래량 폭증 {volume_ratio:.1f}배 (+15)")
            elif volume_ratio >= 1.2:  # 1.3 → 1.2 완화
                score += 10
                signals.append(f"거래량 급증 {volume_ratio:.1f}배 (+10)")
            elif volume_ratio >= 1.0:  # 1.1 → 1.0 완화
                score += 6
                signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+6)")
        
        # 🎯 3단계: 매수 기준 대폭 완화
        min_score = target_config.get('min_score', 35)  # 40 → 35 완화
        
        # 강력한 매수 신호 조건
        strong_buy_conditions = [
            score >= min_score + 20,  # 15 → 20 상향
            any("연속 하락 후 반등" in s for s in signals),
            any("거래량 급증 + 상승" in s for s in signals),
            any("극과매도" in s for s in signals),
            rsi <= 30,  # 25 → 30 완화
            score >= 60  # 50 → 60 상향
        ]
        
        signal_strength = 'STRONG' if any(strong_buy_conditions) else 'NORMAL'
        is_buy_signal = score >= min_score
        
        # 신호 강도를 target_config에 저장 (포지션 크기 계산시 사용)
        target_config['last_signal_strength'] = signal_strength
        
        all_signals = signals + warning_reasons
        
        return {
            'is_buy_signal': is_buy_signal,
            'signal_strength': signal_strength,
            'score': score,
            'min_score': min_score,
            'signals': all_signals if all_signals else ["매수 신호 부족"],
            'bb_position': bb_position,
            'analysis': {
                'rsi': rsi,
                'price_vs_bb_lower': (current_price / stock_data['bb_lower'] - 1) * 100 if stock_data['bb_lower'] > 0 else 0,
                'enhanced_strategy': True
            }
        }
        
    except Exception as e:
        logger.error(f"고수익률 매수 신호 분석 중 에러: {str(e)}")
        return {'is_buy_signal': False, 'score': 0, 'signals': [f"분석 오류: {str(e)}"]}
    
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
    """매도 신호 분석 - 고수익률 버전 (다단계 익절)"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position.get('entry_price', 0)
        
        if entry_price <= 0:
            return {'is_sell_signal': False, 'sell_type': None, 'reason': 'entry_price 정보 없음'}
        
        profit_rate = (current_price - entry_price) / entry_price
        entry_signal_strength = position.get('signal_strength', 'NORMAL')
        
        # 🚨 긴급 매도 (기존 유지)
        df = stock_data.get('ohlcv_data')
        if df is not None and len(df) >= 3:
            daily_drop = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100
            if daily_drop < -12:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'emergency_exit',
                    'reason': f"극도 급락 {daily_drop:.1f}% (긴급 매도)",
                    'urgent': True
                }
        
        # 🚀 2단계: 적극적 다단계 익절 전략
        
        # 기본 익절 목표 설정
        base_target = target_config.get('profit_target', 0.10)  # 6% → 10%
        
        # 신호 강도별 목표 조정
        if entry_signal_strength == 'STRONG':
            profit_targets = {
                'quick': base_target * 0.5,     # 5% 빠른 익절
                'normal': base_target,          # 10% 일반 익절
                'extended': base_target * 1.5   # 15% 확장 익절
            }
        else:
            profit_targets = {
                'quick': base_target * 0.4,     # 4% 빠른 익절
                'normal': base_target * 0.8,    # 8% 일반 익절
                'extended': base_target * 1.2   # 12% 확장 익절
            }
        
        # 기술적 지표 확인
        rsi = stock_data.get('rsi', 50)
        ma5 = stock_data.get('ma5', 0)
        ma20 = stock_data.get('ma20', 0)
        bb_upper = stock_data.get('bb_upper', 0)
        
        # 다단계 익절 실행
        
        # 1) 빠른 익절 - 과매수 구간
        if profit_rate >= profit_targets['quick']:
            if rsi >= 75 or (bb_upper > 0 and current_price >= bb_upper):
                return {
                    'is_sell_signal': True,
                    'sell_type': 'quick_profit',
                    'reason': f"과매수 구간 빠른 익절 {profit_rate*100:.1f}% (목표: {profit_targets['quick']*100:.1f}%)",
                    'urgent': False
                }
        
        # 2) 부분 익절 - 일반 목표 달성시
        if profit_rate >= profit_targets['normal']:
            # 아직 부분매도 안했고, 추세가 약화되지 않았으면 부분매도
            if not position.get('partial_sold', False) and ma5 > ma20 and rsi < 80:
                # 실제 부분매도는 구현 복잡성으로 인해 로그만 남기고 보유 지속
                logger.info(f"🎯 부분 익절 기회: {profit_rate*100:.1f}% (50% 매도 고려)")
                position['partial_sold'] = True  # 플래그 설정
                # 트레일링 스탑으로 전환
                pass
            else:
                # 추세 약화시 전체 매도
                if ma5 <= ma20 or rsi >= 80:
                    return {
                        'is_sell_signal': True,
                        'sell_type': 'normal_profit',
                        'reason': f"추세 약화 익절 {profit_rate*100:.1f}% (목표: {profit_targets['normal']*100:.1f}%)",
                        'urgent': False
                    }
        
        # 3) 확장 익절 - 고수익 달성시
        if profit_rate >= profit_targets['extended']:
            return {
                'is_sell_signal': True,
                'sell_type': 'extended_profit',
                'reason': f"확장 목표 달성 {profit_rate*100:.1f}% (목표: {profit_targets['extended']*100:.1f}%)",
                'urgent': False
            }
        
        # 📉 손절 (기존 유지 - 100% 승률 보존)
        base_stop_loss = target_config.get('stop_loss', -0.12)  # -10% → -12%
        
        if entry_signal_strength == 'STRONG':
            adjusted_stop_loss = base_stop_loss * 1.4
        else:
            adjusted_stop_loss = base_stop_loss
        
        # 시간 기반 완화
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
        
        min_holding_hours = target_config.get('min_holding_hours', 48)
        if holding_hours < min_holding_hours:
            time_multiplier = 1 + (min_holding_hours - holding_hours) / min_holding_hours * 1.5
            adjusted_stop_loss *= time_multiplier
        
        if profit_rate <= adjusted_stop_loss:
            if rsi <= 30:
                return {
                    'is_sell_signal': False,
                    'sell_type': None,
                    'reason': f"과매도로 손절 지연 (RSI: {rsi:.1f})",
                    'urgent': False
                }
            
            return {
                'is_sell_signal': True,
                'sell_type': 'stop_loss',
                'reason': f"손절 실행 {profit_rate*100:.1f}% (기준: {adjusted_stop_loss*100:.1f}%)",
                'urgent': True
            }
        
        # 🔄 적극적 트레일링 스탑
        trailing_stop = target_config.get('trailing_stop', 0.025)  # 3% → 2.5% 타이트
        high_price = position.get('high_price', entry_price)
        
        if high_price > entry_price and profit_rate > 0.03:
            trailing_loss = (high_price - current_price) / high_price
            
            # 수익률별 차등 트레일링
            if profit_rate > 0.12:  # 12% 이상 수익시
                adjusted_trailing = trailing_stop * 0.7  # 더 타이트
            elif profit_rate > 0.08:  # 8% 이상 수익시
                adjusted_trailing = trailing_stop * 0.85
            else:
                adjusted_trailing = trailing_stop
            
            if trailing_loss >= adjusted_trailing:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop',
                    'reason': f"트레일링 스탑 {trailing_loss*100:.1f}% (수익: {profit_rate*100:.1f}%)",
                    'urgent': True
                }
        
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"보유 지속 (수익률: {profit_rate*100:.1f}%, 보유: {holding_hours:.1f}시간)",
            'urgent': False,
            'profit_rate': profit_rate
        }
        
    except Exception as e:
        logger.error(f"고수익률 매도 신호 분석 중 에러: {str(e)}")
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
    """포지션 크기 계산 - 고수익률 버전 (25-30% 배분)"""
    try:
        if stock_price <= 0 or available_budget <= 0:
            return 0
            
        current_available_budget = get_available_budget()
        usable_budget = min(available_budget, current_available_budget)
        
        if usable_budget <= 0:
            return 0
        
        # 🚀 1단계: 포지션 크기 확대
        base_allocation = get_safe_config_value(target_config, 'allocation_ratio', 0.25)  # 기본 25%
        
        # 신호 강도에 따른 추가 확대
        signal_strength = target_config.get('last_signal_strength', 'NORMAL')
        if signal_strength == 'STRONG':
            enhanced_allocation = base_allocation * 1.3  # 강한 신호시 30% 추가
        else:
            enhanced_allocation = base_allocation * 1.1  # 일반 신호시 10% 추가
        
        # 최대 한도 설정 (리스크 관리)
        max_allocation = 0.35  # 최대 35%
        enhanced_allocation = min(enhanced_allocation, max_allocation)
        
        allocated_budget = usable_budget * enhanced_allocation
        
        # 최소 주문 금액 체크
        min_order_amount = get_safe_config_value(target_config, 'min_order_amount', 10000)
        if allocated_budget < min_order_amount:
            return 0
        
        # 최대 주문 금액 제한
        max_order_amount = get_safe_config_value(target_config, 'max_order_amount', usable_budget * 0.4)
        allocated_budget = min(allocated_budget, max_order_amount)
        
        # 기본 수량 계산
        base_quantity = int(allocated_budget / stock_price)
        
        if base_quantity <= 0:
            return 0
        
        # 수수료 고려한 조정
        estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
        total_needed = (stock_price * base_quantity) + estimated_fee
        
        while total_needed > allocated_budget and base_quantity > 0:
            base_quantity -= 1
            if base_quantity > 0:
                estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
                total_needed = (stock_price * base_quantity) + estimated_fee
            else:
                break
        
        if base_quantity <= 0:
            return 0
        
        # 종목별 최소/최대 수량 제한
        min_quantity = get_safe_config_value(target_config, 'min_quantity', 1)
        max_quantity = get_safe_config_value(target_config, 'max_quantity', float('inf'))
        final_quantity = max(min_quantity, min(base_quantity, max_quantity))
        
        # 최종 검증
        final_amount = stock_price * final_quantity
        final_fee = calculate_trading_fee(stock_price, final_quantity, True)
        final_total = final_amount + final_fee
        
        if final_total > allocated_budget:
            return 0
        
        logger.info(f"🚀 고수익률 포지션: {enhanced_allocation*100:.1f}% 배분, {final_quantity}주, {final_total:,.0f}원")
        
        return final_quantity
        
    except Exception as e:
        logger.error(f"고수익률 포지션 계산 중 에러: {str(e)}")
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
                                stock_env = sell_analysis.get('stock_environment', 'sideways')
                                
                                # 적응형 전략 업데이트
                                adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
                                adaptive_strategy.update_performance(
                                    stock_code, 
                                    stock_env, 
                                    win=(net_profit > 0)
                                )
                                
                                win_lose = "승리" if net_profit > 0 else "패배"
                                logger.info(f"🧠 적응형 전략 학습 완료: {stock_code} ({stock_env}) - {win_lose}")
                                
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
    """기본 설정 파일 생성 (백테스트 문제점 반영한 개선 버전)"""
    try:
        logger.info("백테스트 문제점 반영한 개선 설정 파일 생성 시작...")
        
        # 기본 타겟 종목들 정의 (거래량 확보를 위해 확대)
        sample_codes = ["034020", "272210", "267250"]
        
        # 특성별 파라미터 매핑 (백테스트 결과 반영)
        characteristic_params = {
            "growth": {
                "allocation_ratio": 0.30,        # 🚀 20% → 30% (1단계)
                "profit_target": 0.12,           # 🚀 8.5% → 12% (2단계)
                "stop_loss": -0.12,              # 🚀 -10% → -12% (완화)
                "rsi_oversold": 55,              # 🚀 50 → 55 (3단계)
                "rsi_overbought": 75,
                "min_score": 30,                 # 🚀 40 → 30 (3단계)
                "trailing_stop": 0.025,          # 🚀 3% → 2.5% (타이트)
                "min_holding_hours": 48,
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.5,
                "stop_loss_delay_hours": 2
            },
            "balanced": {
                "allocation_ratio": 0.25,        # 🚀 18% → 25% (1단계)
                "profit_target": 0.10,           # 🚀 7.5% → 10% (2단계)
                "stop_loss": -0.12,              # 🚀 완화
                "rsi_oversold": 55,              # 🚀 완화 (3단계)
                "rsi_overbought": 75,
                "min_score": 30,                 # 🚀 완화 (3단계)
                "trailing_stop": 0.03,
                "min_holding_hours": 48,
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.4,
                "stop_loss_delay_hours": 2
            },
            "value": {
                "allocation_ratio": 0.22,        # 🚀 16% → 22% (1단계)
                "profit_target": 0.08,           # 🚀 7% → 8% (2단계)
                "stop_loss": -0.10,              # 적정 유지
                "rsi_oversold": 60,              # 🚀 50 → 60 (3단계)
                "rsi_overbought": 70,
                "min_score": 35,                 # 🚀 65 → 35 (3단계)
                "trailing_stop": 0.035,
                "min_holding_hours": 48,
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.3,
                "stop_loss_delay_hours": 1
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
        
        # 전체 설정 구성 (백테스트 문제점 반영)
        config = {
            "target_stocks": target_stocks,
            
            # 예산 설정 - 기존 구조 유지하되 일부 값만 최적화
            "use_absolute_budget": True,
            "absolute_budget_strategy": "proportional",
            "absolute_budget": 10000000,
            "initial_total_asset": 0,
            "budget_loss_tolerance": 0.2,
            "trade_budget_ratio": 0.85,             # 0.90 → 0.85 (약간 보수적)
            
            # 포지션 관리 - 일부만 최적화
            "max_positions": 6,                     # 8 → 6 (적정 분산)
            "min_stock_price": 3000,                # 기존 유지
            "max_stock_price": 200000,              # 기존 유지
            
            # 🎯 손익 관리 설정 - 백테스트 결과 반영
            "stop_loss_ratio": -0.04,               # -0.025 → -0.04 (완화)
            "take_profit_ratio": 0.08,              # 0.055 → 0.08 (상향)
            "trailing_stop_ratio": 0.025,           # 0.018 → 0.025 (보호 강화)
            "max_daily_loss": -0.06,                # -0.04 → -0.06 (완화)
            "max_daily_profit": 0.08,               # 0.06 → 0.08 (기회 확대)
            
            # 🎯 기술적 분석 설정 - 매수 기회 확대
            "rsi_period": 14,                       # 기존 유지
            "rsi_oversold": 35,                     # 30 → 35 (기회 증가)
            "rsi_overbought": 75,                   # 70 → 75 (매도 늦춤)
            "macd_fast": 12,                        # 기존 유지
            "macd_slow": 26,                        # 기존 유지
            "macd_signal": 9,                       # 기존 유지
            "bb_period": 20,                        # 기존 유지
            "bb_std": 2.0,                          # 기존 유지
            
            # 적응형 전략 사용 설정 - 기존 유지
            "use_adaptive_strategy": True,
            "use_trend_filter": True,
            
            # 기타 설정 - 기존 유지
            "last_sector_update": datetime.datetime.now().strftime('%Y%m%d'),
            "bot_name": "TargetStockBot",           # 기존 이름 유지
            "use_discord_alert": True,
            "check_interval_minutes": 30
        }

        # 파일 저장
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"🎯 개선된 설정 파일 생성 완료: {config_path}")
        logger.info(f"주요 개선: 매수조건 완화, 적응형 전략 끄기, 손익비율 조정")
        
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