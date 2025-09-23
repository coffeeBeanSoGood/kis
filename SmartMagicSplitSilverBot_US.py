#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
미국주식용 스마트 매직 스플릿 봇 (SmartMagicSplitSilverBot_US) - 절대 예산 기반 동적 조정 버전
1. 절대 예산 기반 투자 (달러 기준, 다른 매매봇과 독립적 운영)
2. 성과 기반 동적 예산 조정 (70%~140% 범위)
3. 안전장치 강화 (현금 잔고 기반 검증)
4. 설정 파일 분리 (JSON 기반 관리)
5. 기존 스플릿 로직 유지 (3차수 분할 매매)
6. 미국주식 특화 (PAAS + AG + HL)
"""

import KIS_Common as Common
import KIS_API_Helper_US as KisUS
import discord_alert
import json
import time
from datetime import datetime
from pytz import timezone
import pandas as pd
import os
import schedule
from datetime import datetime, timedelta  # timedelta 추가 (주간 계산용)
from api_resilience import retry_manager, SafeKisUS, set_logger as set_resilience_logger

import yfinance as yf  # SLV 데이터 수집용
import numpy as np     # 데이터 계산용

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
logger = logging.getLogger('SmartMagicSplitSilverLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'smart_magic_split_silver_us.log')
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

################################### 로깅 처리 끝 ##################################

# KIS_API_Helper_US와 KIS_Common 모듈에 로거 전달
try:
    KisUS.set_logger(logger)
    Common.set_logger(logger)
    # 🔥 API 복원력 모듈에도 로거 전달
    set_resilience_logger(logger)

    logger.info("✅ 모든 모듈에 로거 전달 완료 (KIS API, Common, API Resilience)")
except:
    logger.warning("모듈에 로거 전달 중 오류")

################################### 뉴스 라이브러리 ##################################
try:
    import news_analysis_us_silver_theme as news_analysis_us_finhub
    news_analysis_us_finhub.set_logger(logger)
    NEWS_ANALYSIS_AVAILABLE = True
    logger.info("📰 미국주식 뉴스 분석 모듈 로드 완료")
except ImportError as e:
    NEWS_ANALYSIS_AVAILABLE = False
    logger.warning(f"⚠️ 뉴스 분석 모듈을 찾을 수 없습니다: {str(e)}")
    logger.warning("뉴스 분석 기능이 비활성화됩니다. 기존 로직으로만 동작합니다.")
################################### 뉴스 라이브러리 끝##################################

################################### 통합된 설정 관리 시스템 ##################################
# 🔥 API 초기화 (가장 먼저!)
Common.SetChangeMode()
logger.info("✅ 미국주식 API 초기화 완료 - 모든 KIS API 사용 가능")

class IndependentPerformanceTracker:
    """독립적 성과 추적 시스템"""
    
    def __init__(self, bot_name, initial_asset, target_stocks):
        self.bot_name = bot_name
        self.initial_asset = initial_asset
        self.target_stocks = target_stocks
        self.performance_file = f"performance_{bot_name.lower()}.json"
        # 🔥 성과 파일 초기화
        self.initialize_performance_file()

    def initialize_performance_file(self):
        """성과 파일 초기화"""
        try:
            if not os.path.exists(self.performance_file):
                # 초기 성과 파일 생성
                initial_data = {
                    "bot_name": self.bot_name,
                    "initial_asset": self.initial_asset,
                    "target_stocks": self.target_stocks,
                    "created_date": datetime.now().isoformat(),
                    "performance_history": [],
                    "last_update": datetime.now().isoformat(),
                    "current_performance": 0.0,
                    "best_performance": 0.0,
                    "worst_performance": 0.0,
                    "total_calculations": 0
                }
                
                with open(self.performance_file, 'w', encoding='utf-8') as f:
                    json.dump(initial_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"✅ {self.bot_name} 성과 파일 생성: {self.performance_file}")
            else:
                logger.info(f"📊 {self.bot_name} 기존 성과 파일 로드: {self.performance_file}")
                
        except Exception as e:
            logger.error(f"{self.bot_name} 성과 파일 초기화 중 오류: {str(e)}")
    
    def save_performance_data(self, perf_data):
        """성과 데이터 저장"""
        try:
            # 기존 데이터 로드
            performance_data = {}
            if os.path.exists(self.performance_file):
                with open(self.performance_file, 'r', encoding='utf-8') as f:
                    performance_data = json.load(f)
            
            # 성과 히스토리 업데이트
            if 'performance_history' not in performance_data:
                performance_data['performance_history'] = []
            
            # 새로운 성과 기록 추가
            new_record = {
                "timestamp": datetime.now().isoformat(),
                "performance_rate": perf_data['actual_performance'],
                "total_current_asset": perf_data['total_current_asset'],
                "total_investment": perf_data['total_investment'],
                "current_investment_value": perf_data['current_investment_value'],
                "realized_pnl": perf_data['realized_pnl']
            }
            
            performance_data['performance_history'].append(new_record)
            
            # 최대 100개 기록만 유지 (너무 커지지 않도록)
            if len(performance_data['performance_history']) > 100:
                performance_data['performance_history'] = performance_data['performance_history'][-100:]
            
            # 현재 성과 업데이트
            performance_data['last_update'] = datetime.now().isoformat()
            performance_data['current_performance'] = perf_data['actual_performance']
            performance_data['total_calculations'] = performance_data.get('total_calculations', 0) + 1
            
            # 최고/최저 성과 업데이트
            current_perf = perf_data['actual_performance']
            performance_data['best_performance'] = max(
                performance_data.get('best_performance', current_perf), 
                current_perf
            )
            performance_data['worst_performance'] = min(
                performance_data.get('worst_performance', current_perf), 
                current_perf
            )
            
            # 파일 저장
            with open(self.performance_file, 'w', encoding='utf-8') as f:
                json.dump(performance_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"{self.bot_name} 성과 데이터 저장 중 오류: {str(e)}")

    def get_current_holdings(self, stock_code):
        """현재 보유 수량 및 상태 조회 - 안전한 API 호출"""
        try:
            my_stocks = SafeKisUS.safe_get_my_stock_list("USD")
            if my_stocks is None:
                logger.warning(f"⚠️ {stock_code} 보유 수량 조회 API 실패")
                return {'amount': -1, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0, 'api_error': True}
                
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    return {
                        'amount': int(stock['StockAmt']),
                        'avg_price': float(stock['StockAvgPrice']),
                        'revenue_rate': float(stock['StockRevenueRate']),
                        'revenue_money': float(stock['StockRevenueMoney'])
                    }
            return {'amount': 0, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0}
            
        except Exception as e:
            logger.error(f"❌ {stock_code} 보유 수량 조회 중 예외: {str(e)}")
            return {'amount': -1, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0, 'api_error': True}

    def load_bot_data(self):
        """봇 데이터 파일 로드"""
        try:
            data_file = "/var/autobot/kisUS/UsStock_REAL_SmartMagicSplitBot_US.json"
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"봇 데이터 로드 중 오류: {str(e)}")
            return []

    def calculate_bot_specific_performance(self):
        """봇별 실제 투자 성과 계산 (파일 저장 포함)"""
        try:
            my_total_investment = 0
            my_total_current_value = 0
            my_realized_pnl = 0
            
            # 현재 자신의 종목들만 조회
            for stock_code in self.target_stocks:
                # 브로커에서 실제 보유 조회
                holdings = self.get_current_holdings(stock_code)
                if holdings['amount'] > 0:
                    current_price = SafeKisUS.safe_get_current_price(stock_code)
                    if current_price > 0:
                        current_value = holdings['amount'] * current_price
                        investment_cost = holdings['amount'] * holdings['avg_price']
                        
                        my_total_investment += investment_cost
                        my_total_current_value += current_value
                
                # 실현손익 조회
                bot_data = self.load_bot_data()
                for stock_data in bot_data:
                    if stock_data.get('StockCode') == stock_code:
                        my_realized_pnl += stock_data.get('RealizedPNL', 0)
            
            # 총 현재 자산 계산
            current_cash_portion = self.initial_asset - my_total_investment + my_realized_pnl
            my_total_asset = my_total_current_value + current_cash_portion
            
            # 실제 성과율 계산
            actual_performance = (my_total_asset - self.initial_asset) / self.initial_asset
            
            perf_data = {
                'initial_asset': self.initial_asset,
                'total_investment': my_total_investment,
                'current_investment_value': my_total_current_value,
                'realized_pnl': my_realized_pnl,
                'current_cash_portion': current_cash_portion,
                'total_current_asset': my_total_asset,
                'actual_performance': actual_performance
            }
            
            # 🔥 성과 데이터 파일에 저장
            self.save_performance_data(perf_data)
            
            return perf_data
            
        except Exception as e:
            logger.error(f"{self.bot_name} 성과 계산 중 오류: {str(e)}")
            return None
   
    def get_dynamic_budget_multiplier(self, performance_rate):
        """성과 기반 예산 배수 계산"""
        if performance_rate > 0.3:
            return 1.4
        elif performance_rate > 0.2:
            return 1.3
        elif performance_rate > 0.15:
            return 1.25
        elif performance_rate > 0.1:
            return 1.2
        elif performance_rate > 0.05:
            return 1.1
        elif performance_rate > -0.05:
            return 1.0
        elif performance_rate > -0.1:
            return 0.95
        elif performance_rate > -0.15:
            return 0.9
        elif performance_rate > -0.2:
            return 0.85
        else:
            return 0.7
    
    def calculate_independent_dynamic_budget(self):
        """독립적 동적 예산 계산"""
        try:
            perf_data = self.calculate_bot_specific_performance()
            if not perf_data:
                return self.initial_asset
            
            # 성과 기반 배수 계산
            multiplier = self.get_dynamic_budget_multiplier(perf_data['actual_performance'])
            
            # 동적 예산 = 초기자산 × 배수
            dynamic_budget = self.initial_asset * multiplier
            
            # 안전장치: 현재 가용 자산을 초과할 수 없음
            max_safe_budget = perf_data['total_current_asset'] * 0.95
            if dynamic_budget > max_safe_budget:
                dynamic_budget = max_safe_budget
                logger.warning(f"{self.bot_name} 동적예산이 가용자산 초과로 제한됨: ${dynamic_budget:,.0f}")
            
            logger.info(f"📊 {self.bot_name} 독립 성과:")
            logger.info(f"   초기자산: ${self.initial_asset:,.0f}")
            logger.info(f"   현재자산: ${perf_data['total_current_asset']:,.0f}")
            logger.info(f"   실제성과: {perf_data['actual_performance']*100:+.2f}%")
            logger.info(f"   예산배수: {multiplier:.2f}x")
            logger.info(f"   동적예산: ${dynamic_budget:,.0f}")
            
            return dynamic_budget
            
        except Exception as e:
            logger.error(f"{self.bot_name} 독립 동적예산 계산 중 오류: {str(e)}")
            return self.initial_asset

class SmartSplitConfig:
    """미국주식용 스마트 스플릿 설정 관리 클래스 - 통합 버전"""
    
    def __init__(self, config_path: str = "smart_split_silver_config_us.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()

    def get_default_config(self):
        """🥈 실버 광산주 완전 하이브리드 보호 시스템 기본 설정 - 5번째 봇 (PAAS+HL+AG)"""
        return {
            "bot_name": "SmartMagicSplitSilverBot_US",
            "currency": "USD",
            "use_absolute_budget": True,
            "absolute_budget": 1600,  # 🥈 5번째 봇 예산
            "absolute_budget_strategy": "proportional",
            "initial_total_asset": 5010,
            "div_num": 3,  # 3차수 시스템 (변동성 활용)
            
            # 🥈 매수 제한 시스템 (실버 광산주 특화)
            "buy_limit_system": {
                "global_limits": {
                    "enable": True,
                    "daily_max": 6,  # 실버 변동성 고려
                    "weekly_max": 20,
                    "monthly_max": 50,
                    "high_frequency_penalty": {
                        "threshold": 4,
                        "penalty_hours": 3,
                        "severity_multiplier": 1.3
                    },
                    "market_condition_modifier": {
                        "bull": 1.3,  # 실버 강세장에서 적극적
                        "bear": 0.7,
                        "neutral": 1.0,
                        "high": 1.4,
                        "low": 0.8
                    },
                    "partial_sell_cooldown": {
                        "enable": True,
                        "first_partial": 2,
                        "second_partial": 3,
                        "full_sell": 5,
                        "_comment": "실버 부분매도별 차등 쿨다운"
                    }
                },
                "dynamic_limits": {
                    "enable": True,
                    "base_daily": 4,
                    "per_stock_max": 2,
                    "market_bonus": {
                        "downtrend": 4,
                        "uptrend": 2,
                        "neutral": 3
                    },
                    "volatility_bonus": 3,
                    "opportunity_bonus": {
                        "high_density": 3,
                        "medium_density": 2,
                        "low_density": 1
                    },
                    "absolute_max": 8
                },
                "_comment": "🥈 실버 광산주 특화 - 구조적 공급부족 + 산업수요 폭발"
            },
            
            # 🥈 시장 포지션 제한 (실버 특화)
            "market_position_limits": {
                "strong_uptrend": 4,
                "uptrend": 4,
                "neutral": 3,
                "downtrend": 3,
                "strong_downtrend": 2,
                "_comment": "실버 모멘텀 특화"
            },
            
            # 🥈 점진적 매수 하락률
            "progressive_buy_drops": {
                "2": 0.04,  # 실버 변동성 고려
                "3": 0.06
            },
            
            # 🥈 실버 광산주 3종목 포트폴리오
            "target_stocks": {
                "PAAS": {
                    "name": "Pan American Silver Corp",
                    "weight": 0.40,  # 40% - 대형 안정주
                    "enabled": True,
                    "max_positions": 3,
                    "min_pullback": 0.02,
                    "max_rsi_buy": 75,
                    "profit_target": 12,
                    "stop_loss": -15,
                    "partial_sell_config": {
                        "enable": True,
                        "first_sell_threshold": 12,
                        "first_sell_ratio": 0.30,
                        "hybrid_protection": {
                            "enable": True,
                            "min_quantity_for_partial": 1,
                            "min_profit_for_trailing": 8,
                            "post_partial_trailing": 0.06,
                            "emergency_trailing_enable": True,
                            "emergency_max_profit_threshold": 8,
                            "emergency_trailing_drop": 0.05,
                            "_comment": "아메리카 최대 은 생산기업: 안정적 수익확보"
                        }
                    },
                    "news_weight": 0.3,
                    "silver_theme_weight": 0.35,
                    "_comment": "아메리카 대륙 최대 은 생산기업, 12개 운영 광산"
                },
                "HL": {
                    "name": "Hecla Mining Company",
                    "weight": 0.35,  # 35% - 미국 독점
                    "enabled": True,
                    "max_positions": 3,
                    "min_pullback": 0.025,
                    "max_rsi_buy": 73,
                    "profit_target": 15,
                    "stop_loss": -18,
                    "partial_sell_config": {
                        "enable": True,
                        "first_sell_threshold": 15,
                        "first_sell_ratio": 0.25,
                        "hybrid_protection": {
                            "enable": True,
                            "min_quantity_for_partial": 1,
                            "min_profit_for_trailing": 10,
                            "post_partial_trailing": 0.07,
                            "emergency_trailing_enable": True,
                            "emergency_max_profit_threshold": 10,
                            "emergency_trailing_drop": 0.04,
                            "_comment": "미국 독점 지위: 높은 수익 기대 + 정부 정책 수혜"
                        }
                    },
                    "news_weight": 0.35,
                    "silver_theme_weight": 0.4,
                    "_comment": "미국 최대 은 생산기업 (미국 은 생산 50% 점유)"
                },
                "AG": {
                    "name": "First Majestic Silver Corp",
                    "weight": 0.25,  # 25% - 성장주
                    "enabled": True,
                    "max_positions": 3,
                    "min_pullback": 0.03,
                    "max_rsi_buy": 70,
                    "profit_target": 18,
                    "stop_loss": -20,
                    "partial_sell_config": {
                        "enable": True,
                        "first_sell_threshold": 18,
                        "first_sell_ratio": 0.35,
                        "hybrid_protection": {
                            "enable": True,
                            "min_quantity_for_partial": 1,
                            "min_profit_for_trailing": 12,
                            "post_partial_trailing": 0.08,
                            "emergency_trailing_enable": True,
                            "emergency_max_profit_threshold": 12,
                            "emergency_trailing_drop": 0.06,
                            "_comment": "성장형 은 생산기업: 적극적 확장 + M&A"
                        }
                    },
                    "news_weight": 0.25,
                    "silver_theme_weight": 0.3,
                    "_comment": "중간 규모 1차 은 생산기업, Gatos Silver 인수로 성장"
                }
            },
            
            # 🥈 종합 스코어링 (실버 광산주 특화)
            "comprehensive_scoring": {
                "enable": True,
                "position_thresholds": {
                    "1": 65,  # 3차수: 적극적
                    "2": 60,
                    "3": 55
                },
                "_comment": "실버 광산주 특화 - 3차수 적극적 매수, 변동성 활용"
            },
            
            # 🥈 개별 종목 제한 (실버 변동성 고려)
            "individual_stock_limits": {
                "enable": True,
                "default_daily_max": 2,
                "stock_specific": {
                    "PAAS": {"daily_max": 2, "weekly_max": 8},   # 대형주 안정적
                    "HL": {"daily_max": 2, "weekly_max": 8},     # 독점 지위
                    "AG": {"daily_max": 1, "weekly_max": 6}      # 변동성 큰 성장주
                },
                "_comment": "실버 광산주 변동성 고려한 제한"
            },
            
            # 🥈 리스크 관리 (3종목 분산)
            "risk_management": {
                "max_position_ratio": 0.4,  # 최대 포지션 비중
                "emergency_stop_loss": -0.25,  # 실버 변동성 고려
                "daily_loss_limit": -0.1,
                "position_size_limit": 0.4,  # 3종목 분산
                "_comment": "실버 광산주 3종목 분산 설정"
            },
            
            # 🥈 기술적 분석
            "technical_analysis": {
                "enable": True,
                "rsi_period": 14,
                "ma_periods": [5, 20, 60],
                "volume_analysis": True,
                "trend_confirmation": True,
                "momentum_weight": 0.5,  # 실버 모멘텀 중시
                "_comment": "실버 광산주 모멘텀 중시"
            },
            
            # 🥈 뉴스 분석
            "news_analysis": {
                "enable": True,
                "sentiment_weight": 0.3,
                "cache_duration_minutes": 120,
                "silver_theme_bonus": 0.2,  # 실버 테마 보너스
                "earnings_weight": 0.35,
                "_comment": "실버 광산주 뉴스 가중치 강화"
            },
            
            # 🥈 기타 설정
            "volatility_adjustment": -0.03,  # 실버 변동성 고려
            "time_based_rules": {
                "45_day_threshold": -0.12,
                "90_day_threshold": -0.08
            },
            
            # 🥈 거래 제한 (실버 광산주 특화)
            "trading_limits": {
                "daily_trading_limits": {
                    "enable": True,
                    "max_daily_trades": 5,
                    "max_stock_trades": 2,
                    "reset_hour": 9,
                    "market_condition_multiplier": {
                        "strong_uptrend": 1.4,
                        "uptrend": 1.2,
                        "neutral": 1.0,
                        "downtrend": 0.8,
                        "strong_downtrend": 0.6
                    },
                    "partial_sell_cooldown": {
                        "enable": True,
                        "first_partial": 2,
                        "second_partial": 3,
                        "full_sell": 5,
                        "_comment": "실버 부분매도별 차등 쿨다운"
                    }
                },
                "dynamic_limits": {
                    "enable": True,
                    "base_daily": 4,
                    "per_stock_max": 2,
                    "market_bonus": {
                        "downtrend": 4,
                        "uptrend": 2,
                        "neutral": 3
                    },
                    "volatility_bonus": 3,
                    "opportunity_bonus": {
                        "high_density": 3,
                        "medium_density": 2,
                        "low_density": 1
                    },
                    "absolute_max": 8
                },
                "_comment": "🥈 실버 광산주 특화 - 구조적 공급부족 + 산업수요 폭발"
            },
            
            # 🥈 기본 설정
            "use_discord_alert": True,
            "discord_webhook_url": "",
            "trading_enabled": True,
            "auto_trading": True,
            "market_hours_only": True,
            "pre_market_trading": False,
            "after_hours_trading": False,
            
            "market_timing": {
                "enable": True,
                "spy_trend_weight": 0.3,  # 실버는 독립적 움직임
                "individual_strength_weight": 0.7,  # 개별 강도 중시
                "market_condition_adjustment": True,
                "_comment": "실버 테마 개별 강도 우선"
            },
            
            # 🥈 메타데이터 (5번째 봇)
            "_readme": {
                "설명": "🥈 실버 광산주 특화 시스템 (5번째 봇) + 하이브리드 보호",
                "업데이트_날짜": "2025-09-19",
                "투자전략": "PAAS+HL+AG 실버 대표주 집중 + 구조적 공급부족 수혜",
                "총예산": "$1,200 (5번째 봇)",
                "통화": "USD (달러)",
                "테마": "실버 광산주 (지역/규모 분산)",
                "시장전망": "5년 연속 공급부족 + 산업수요 폭발 ($40-100 목표)"
            },
            
            "_comment_silver_system": "🥈 실버 특화 하이브리드 보호 시스템 - 구조적 공급부족 + 산업수요 폭발 수혜",
            "last_config_update": datetime.now().isoformat(),
            
            "performance_tracking": {
                "best_performance": 0.0,
                "worst_performance": 0.0,
                "total_trades": 0,
                "win_rate": 0.0
            }
        }

    def load_config(self):
        """설정 파일 로드"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # 기본 설정과 병합
                default_config = self.get_default_config()
                self.config = self._merge_config(loaded_config, default_config)
                
                logger.info(f"✅ 실버봇 설정 파일 로드 완료: {self.config_path}")
            else:
                logger.info(f"⚠️ 설정 파일 없음. 기본 설정으로 생성: {self.config_path}")
                self.config = self.get_default_config()
                self.save_config()
                
        except Exception as e:
            logger.error(f"❌ 설정 파일 로드 오류: {str(e)}")
            self.config = self.get_default_config()

    def _send_creation_message(self):
        """설정 파일 생성 시 안내 메시지 전송 - 🥈 실버 특화 하이브리드 보호 시스템 버전"""
        try:
            target_stocks = config.target_stocks
            
            setup_msg = f"🥈 **실버봇 설정 완료** - 5번째 봇 추가!\n"
            setup_msg += f"📁 파일: {config.config_path}\n"
            setup_msg += f"💰 초기 예산: ${config.absolute_budget:,} (5번째 봇)\n"
            setup_msg += f"📊 예산 전략: {config.config['absolute_budget_strategy']}\n"
            setup_msg += f"🎯 분할 차수: {config.div_num:.0f}차수 (변동성 활용)\n"
            setup_msg += f"💱 통화: {config.config['currency']}\n\n"
            
            # 🥈 실버 시장 현황 강조
            setup_msg += f"📈 **실버 시장 현황** (2025년)\n"
            setup_msg += f"🔥 5년 연속 공급 부족 (수요 12억온스 vs 공급 부족)\n"
            setup_msg += f"⚡ 산업 수요 폭발: 태양광+전기차+전자제품 = 7억온스 돌파\n"
            setup_msg += f"💰 가격 상승: $40+ 돌파, 전문가 목표가 $50-100\n"
            setup_msg += f"🚀 광산주 레버리지: 은 가격 상승 시 2-3배 효과\n\n"
            
            # 🥈 실버 하이브리드 보호 시스템 강조
            setup_msg += f"🥈 **실버 특화 하이브리드 보호 시스템 완전 적용**\n"
            setup_msg += f"✅ 실버 모멘텀 + 하이브리드 보호 완벽 결합\n"
            setup_msg += f"✅ 구조적 공급부족 + 산업수요 폭발 수혜\n"
            setup_msg += f"✅ 지역/규모 완전 분산 (아메리카+미국+캐나다)\n"
            setup_msg += f"✅ 3차수 적극적 변동성 활용\n"
            setup_msg += f"✅ 응급 백업 시스템 + 이중 안전망\n"
            setup_msg += f"✅ 실버 변동성 대응 + 레버리지 효과 극대화\n\n"
            
            setup_msg += f"🎯 **실버 타겟 종목 하이브리드 설정**:\n"
            
            silver_hybrid_info = {
                "PAAS": ("12% 안정매도(30%)", "8% 응급트레일링", "아메리카 최대 (12개 광산)"),
                "HL": ("15% 독점매도(25%)", "10% 응급트레일링", "미국 독점 지위 (50% 점유)"),
                "AG": ("18% 성장매도(35%)", "12% 응급트레일링", "적극적 확장 (M&A 활발)")
            }
            
            for stock_code, stock_config in target_stocks.items():
                allocated = config.absolute_budget * stock_config.get('weight', 0)
                partial_info, trailing_info, description = silver_hybrid_info.get(stock_code, ("설정됨", "설정됨", "실버 하이브리드 적용"))
                
                # 하이브리드 설정 정보 추출
                partial_config = stock_config.get('partial_sell_config', {})
                hybrid_config = partial_config.get('hybrid_protection', {})
                min_quantity = hybrid_config.get('min_quantity_for_partial', 1)
                
                setup_msg += f"• **{stock_config.get('name', stock_code)}** ({stock_code})\n"
                setup_msg += f"  💰 비중: {stock_config.get('weight', 0)*100:.1f}% (${allocated:,.0f})\n"
                setup_msg += f"  🎯 {description}\n"
                setup_msg += f"  💎 부분매도: {partial_info}\n"
                setup_msg += f"  🛡️ 응급보호: {trailing_info}\n"
                setup_msg += f"  📊 최소수량: {min_quantity}주부터 적용\n"
            
            # 🥈 실버 하이브리드 시스템 핵심 장점
            setup_msg += f"\n🚀 **실버 하이브리드 시스템 핵심 장점**:\n"
            setup_msg += f"✅ 구조적 수혜: 5년 연속 공급부족 + 산업수요 폭발\n"
            setup_msg += f"✅ 레버리지 효과: 은 가격 상승 시 광산주 2-3배 수익\n"
            setup_msg += f"✅ 완전 분산: 지역(3개국) + 규모(대/중/소) 분산\n"
            setup_msg += f"✅ 변동성 활용: 3차수로 실버 변동성을 기회로 전환\n"
            setup_msg += f"✅ 빠른 보호: 트레일링으로 급락 즉시 대응\n"
            setup_msg += f"✅ 이중 안전망: 부분매도 + 응급 트레일링\n"
            setup_msg += f"✅ 포트폴리오 완성: 5축 분산 (원전+AI+빅테크+미래기술+실버)\n\n"
            
            # 🔥 즉시 적용 효과
            setup_msg += f"⚡ **5번째 봇 즉시 효과**:\n"
            setup_msg += f"🎯 PAAS: 대형주 안정성 + 12개 광산 분산\n"
            setup_msg += f"🥈 HL: 미국 독점 지위 + 정부 정책 수혜\n"
            setup_msg += f"💎 AG: 성장주 모멘텀 + M&A 확장 효과\n"
            setup_msg += f"📊 포트폴리오 완성: 5축 분산 효과\n"
            setup_msg += f"🚀 리스크 분산: 20% 증가 (5개 테마)\n"
            setup_msg += f"😌 인플레이션 헤지: 원자재 포지션 확보\n\n"
            
            setup_msg += f"💡 **실버 하이브리드 매도 시나리오**:\n"
            setup_msg += f"🥈 PAAS: 12% 달성 → 30% 매도 → 70% 트레일링\n"
            setup_msg += f"⛏️ HL: 15% 달성 → 25% 매도 → 75% 트레일링\n"
            setup_msg += f"💎 AG: 18% 달성 → 35% 매도 → 65% 트레일링\n"
            setup_msg += f"🛡️ 응급 보호: 부분매도 실패시 8-12% 트레일링\n\n"
            
            setup_msg += f"🔧 **실버 특화 시스템 ($1,200)**:\n"
            setup_msg += f"• 실버 3축: PAAS(40%) + HL(35%) + AG(25%)\n"
            setup_msg += f"• 지역 분산: 아메리카+미국+캐나다 리스크 분산\n"
            setup_msg += f"• 규모 분산: 대형+독점+성장 완전 커버\n"
            setup_msg += f"• 구조적 수혜: 공급부족 + 산업수요 폭발\n"
            setup_msg += f"• 변동성 활용: 3차수로 기민한 대응\n\n"
            
            setup_msg += f"⚙️ **설정 변경**은 {config.config_path} 파일을 수정하세요.\n"
            setup_msg += f"🕐 **미국 장 시간**: 09:30-16:00 ET (한국시간 23:30-06:00)\n"
            setup_msg += f"🥈 **실버 하이브리드**: 구조적 공급부족 + 산업수요 폭발의 완벽한 수혜"
            
            logger.info(setup_msg)
            
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(setup_msg)
                
            # 🎯 상세 사용자 안내 메시지
            logger.info("=" * 40)
            logger.info("🥈 실버 특화 하이브리드 보호 시스템 설정 파일이 생성되었습니다!")
            logger.info("📊 실버 모멘텀 + 하이브리드 보호 + 5축 분산 완벽 결합")
            logger.info("📝 주요 설정 항목:")
            logger.info("  1. absolute_budget: 투자할 총 달러 금액 (기본: $1,200)")
            logger.info("  2. target_stocks의 hybrid_protection: 실버 특화 하이브리드 보호")
            logger.info("  3. first_sell_threshold: 부분매도 시작 수익률 (PAAS 12%, HL 15%, AG 18%)")
            logger.info("  4. emergency_trailing_drop: 응급 트레일링 하락폭 (8-12%)")
            logger.info("  5. min_quantity_for_partial: 부분매도 최소 수량 (1주)")
            logger.info("  6. min_pullback: 진입 조정폭 (PAAS 2%, HL 2.5%, AG 3%)")
            logger.info("🎯 실버 하이브리드 시스템 핵심 장점:")
            logger.info("  ✅ 구조적 수혜: 5년 연속 공급부족 + 산업수요 폭발")
            logger.info("  ✅ 레버리지 효과: 은 가격 상승 시 광산주 2-3배 수익")
            logger.info("  ✅ 완전 분산: 지역(3개국) + 규모(대/중/소) 분산")
            logger.info("  ✅ 변동성 활용: 3차수로 실버 변동성을 기회로 전환")
            logger.info("  ✅ 빠른 급락 대응: 트레일링으로 변동성 즉시 보호")
            logger.info("  ✅ 이중 안전망: 부분매도 + 응급 트레일링")
            logger.info("  ✅ 포트폴리오 완성: 5축 분산 (원전+AI+빅테크+미래기술+실버)")
            logger.info("🚀 실버 시장 즉시 적용 효과:")
            logger.info("  📊 PAAS: 아메리카 최대 안정성 + 12개 광산 분산")
            logger.info("  🥈 HL: 미국 독점 지위 + 정부 정책 수혜")
            logger.info("  💎 AG: 성장주 모멘텀 + M&A 확장 효과")
            logger.info("  🛡️ 리스크 분산: 5축 포트폴리오로 20% 증가")
            logger.info("  ⚡ 인플레이션 헤지: 원자재 포지션 확보")
            logger.info("💡 실버 하이브리드 매도 시나리오:")
            logger.info("  🥈 PAAS: 12% 달성 → 30% 매도 → 70% 트레일링")
            logger.info("  ⛏️ HL: 15% 달성 → 25% 매도 → 75% 트레일링")
            logger.info("  💎 AG: 18% 달성 → 35% 매도 → 65% 트레일링")
            logger.info("  🛡️ 응급 보호: 부분매도 실패시 8-12% 트레일링")
            logger.info("🔧 실버 특화 시스템 ($1,200):")
            logger.info("  • 실버 3축: PAAS(40%) + HL(35%) + AG(25%)")
            logger.info("  • 지역 분산: 아메리카+미국+캐나다 리스크 분산")
            logger.info("  • 규모 분산: 대형+독점+성장 완전 커버")
            logger.info("  • 구조적 수혜: 공급부족 + 산업수요 폭발")
            logger.info("  • 변동성 활용: 3차수로 기민한 대응")
            logger.info("💡 설정 변경 후 봇을 재시작하면 자동 적용됩니다.")
            logger.info("🕐 미국 장 시간: 09:30-16:00 ET (한국시간 23:30-06:00)")
            logger.info("🥈 실버 하이브리드: 구조적 공급부족과 산업수요 폭발의 혁신적 수혜")
            logger.info("=" * 40)
            
        except Exception as e:
            logger.error(f"실버봇 설정 생성 메시지 전송 오류: {str(e)}")
  
    def _merge_config(self, loaded, default):
        """설정 병합 - 🔥 로드된 설정 우선 (완전 수정)"""
        result = loaded.copy()  # 🔥 변경: 로드된 설정을 기준으로 시작
        
        # 기본값에서 누락된 키만 추가
        for key, value in default.items():
            if key not in result:
                result[key] = value
            elif isinstance(result[key], dict) and isinstance(value, dict):
                # 🔥 변경: 재귀 호출시에도 로드된 값 우선
                result[key] = self._merge_config(result[key], value)
        
        return result
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            self.config["last_config_update"] = datetime.now().isoformat()
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"✅ 실버봇 설정 파일 저장 완료: {self.config_path}")
        except Exception as e:
            logger.error(f"❌ 설정 파일 저장 중 오류: {str(e)}")            
    
    # 속성 접근자들 (기존 유지)
    @property
    def use_absolute_budget(self):
        return self.config.get("use_absolute_budget", True)
    
    @property
    def absolute_budget(self):
        return self.config.get("absolute_budget", 1200)  # $1,200로 변경
    
    @property
    def absolute_budget_strategy(self):
        return self.config.get("absolute_budget_strategy", "proportional")
    
    @property
    def initial_total_asset(self):
        return self.config.get("initial_total_asset", 0)
    
    @property
    def target_stocks(self):
        return self.config.get("target_stocks", {})
    
    @property
    def bot_name(self):
        return self.config.get("bot_name", "SmartMagicSplitBot_Silver_US")
    
    @property
    def div_num(self):
        return self.config.get("div_num", 3.0)
    
    def update_initial_asset(self, asset_value):
        """초기 자산 업데이트"""
        self.config["initial_total_asset"] = asset_value
        self.save_config()
    
    def update_performance(self, performance_rate):
        """성과 추적 업데이트"""
        tracking = self.config.get("performance_tracking", {})
        tracking["best_performance"] = max(tracking.get("best_performance", 0), performance_rate)
        tracking["worst_performance"] = min(tracking.get("worst_performance", 0), performance_rate)
        self.config["performance_tracking"] = tracking
        self.save_config()


# 🔥 전역 봇 인스턴스 관리 (새로 추가)
bot_instance = None

def get_bot_instance():
    """전역 봇 인스턴스 반환 (싱글톤 패턴)"""
    global bot_instance
    if bot_instance is None:
        logger.info("🤖 새로운 봇 인스턴스 생성")
        bot_instance = SmartMagicSplit()
    return bot_instance

def reset_bot_instance():
    """봇 인스턴스 리셋 (필요시 사용)"""
    global bot_instance
    bot_instance = None
    logger.info("🔄 봇 인스턴스 리셋")

################################### 간단한 체크 함수 (호환성 유지) ##################################

def check_and_create_config():
    """설정 파일 존재 여부 확인 - 간소화된 버전"""
    config_path = "smart_split_silver_config_us.json"
    
    if not os.path.exists(config_path):
        logger.info(f"📋 설정 파일이 없어서 SmartSplitConfig 클래스에서 자동 생성합니다.")
        return True  # 새로 생성됨을 알림
    else:
        logger.info(f"✅ 설정 파일 존재: {config_path}")
        return False  # 기존 파일 사용

# 전역 설정 인스턴스
config = SmartSplitConfig()

# 봇 이름 설정
BOT_NAME = Common.GetNowDist() + "_" + config.bot_name

# 이 파일은 Part 1 뒤에 이어집니다

################################### 메인 클래스 ##################################

class SmartMagicSplit:
    def __init__(self):
        self.split_data_list = self.load_split_data()
        self.total_money = 0
        self.update_budget()
        self._upgrade_json_structure_if_needed()
        # 🔥 뉴스 캐시 초기화 추가
        self.news_cache = {}
        self.last_news_check = {}  # 종목별 마지막 뉴스 체크 시간        

        # 🥈 실버 연동성 강화를 위한 SLV 데이터 캐시 (아래 3줄 추가)
        self.slv_data_cache = {}
        self.slv_cache_time = None
        self.slv_cache_duration = 300  # 5분 캐시

        # 🔥 독립 성과 추적기 추가 (AI봇용)
        self.performance_tracker = IndependentPerformanceTracker(
            bot_name="SilverBot",
            initial_asset=config.absolute_budget,  # 1800
            target_stocks=list(config.target_stocks.keys())  # ["NVDA", "PLTR"]
        )
        logger.info(f"✅ SILVER봇 독립 성과 추적 시스템 초기화 완료")

################################### SLV 데이터 수집 함수 추가 ##################################

    def get_slv_reference_data(self):
        """SLV(실버 ETF) 참조 데이터 수집"""
        try:
            current_time = time.time()
            
            # 캐시 유효성 검사 (5분간 재사용)
            if (self.slv_cache_time and 
                current_time - self.slv_cache_time < self.slv_cache_duration and 
                self.slv_data_cache):
                return self.slv_data_cache
            
            # SLV 최근 5일 데이터 수집
            slv_history = yf.download("SLV", period="10d", interval="1d")
            if slv_history.empty:
                logger.warning("SLV 히스토리 데이터 없음 - 기존 로직 사용")
                return None
                
            # 현재가 계산
            current_price = float(slv_history['Close'].iloc[-1])
            recent_prices = slv_history['Close'].tail(5).tolist()
            
            # SLV 분석 지표 계산
            slv_analysis = {
                'current_price': current_price,
                'change_1d': (recent_prices[-1] - recent_prices[-2]) / recent_prices[-2] * 100 if len(recent_prices) >= 2 else 0,
                'change_3d': (recent_prices[-1] - recent_prices[-4]) / recent_prices[-4] * 100 if len(recent_prices) >= 4 else 0,
                'change_5d': (recent_prices[-1] - recent_prices[0]) / recent_prices[0] * 100 if len(recent_prices) >= 5 else 0,
                'trend_3d': self.calculate_trend_direction(recent_prices[-3:]) if len(recent_prices) >= 3 else 'neutral'
            }
            
            # 캐시 업데이트
            self.slv_data_cache = slv_analysis
            self.slv_cache_time = current_time
            
            logger.info(f"🥈 SLV 분석: ${current_price:.2f}, 1일 {slv_analysis['change_1d']:+.1f}%, 3일트렌드 {slv_analysis['trend_3d']}")
            
            return slv_analysis
            
        except Exception as e:
            logger.error(f"SLV 데이터 수집 오류: {str(e)} - 기존 로직 사용")
            return None

    def calculate_trend_direction(self, prices):
        """가격 추세 방향 계산"""
        if len(prices) < 2:
            return 'neutral'
        
        up_count = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])
        total_moves = len(prices) - 1
        
        if up_count >= total_moves * 0.7:
            return 'bullish'    # 70% 이상 상승
        elif up_count <= total_moves * 0.3:
            return 'bearish'    # 70% 이상 하락
        else:
            return 'neutral'    # 중립

    def calculate_silver_bonus_score(self, stock_code, indicators):
        """🥈 실버 연동성 보너스 점수 계산 (기존 점수에 추가)"""
        try:
            slv_data = self.get_slv_reference_data()
            if not slv_data:
                return 0  # SLV 데이터 없으면 보너스 없음
            
            silver_score = 0
            
            # 실버 광산주별 레버리지 계수 (경험치)
            leverage = {'PAAS': 2.1, 'HL': 2.5, 'AG': 2.8}.get(stock_code, 2.3)
            
            # 🎯 실버 연동 보너스 점수 로직
            
            # 보너스 1: SLV 강세 + 광산주 상대적 약세 (역전 기회)
            if slv_data['change_3d'] > 2:  # SLV 3일간 2% 이상 상승
                expected_change = slv_data['change_3d'] * leverage
                actual_change = indicators.get('change_3d', 0)
                
                if actual_change < expected_change * 0.5:  # 예상의 50% 미만
                    silver_score += 20
                    logger.info(f"🥈 {stock_code} SLV 강세({slv_data['change_3d']:+.1f}%) vs 광산주 약세 → +20점")
            
            # 보너스 2: SLV 연속 상승 트렌드
            if slv_data['trend_3d'] == 'bullish' and slv_data['change_1d'] > 0.5:
                silver_score += 10
                logger.info(f"🥈 {stock_code} SLV 상승 트렌드 → +10점")
            
            # 보너스 3: SLV 급등 후 추격 매수
            if slv_data['change_1d'] > 1.5:  # SLV 하루 1.5% 이상 상승
                expected_daily = slv_data['change_1d'] * leverage
                actual_daily = indicators.get('change_1d', 0)
                
                if actual_daily < expected_daily * 0.3:  # 추격 기회
                    silver_score += 15
                    logger.info(f"🥈 {stock_code} SLV 급등({slv_data['change_1d']:+.1f}%) 추격 기회 → +15점")
            
            # 패널티: SLV 약세 시 보수적 접근
            if slv_data['trend_3d'] == 'bearish' and slv_data['change_1d'] < -1:
                silver_score -= 10
                logger.info(f"🥈 {stock_code} SLV 약세 트렌드 → -10점")
            
            if silver_score != 0:
                logger.info(f"🥈 {stock_code} 실버 연동 보너스: {silver_score}점")
            
            return silver_score
            
        except Exception as e:
            logger.error(f"실버 연동 점수 계산 오류: {str(e)}")
            return 0

################################### 쿨다운 시스템 ##################################

    def check_post_sell_cooldown(self, stock_code):
        """🔥 종목 레벨 이력 활용한 개선된 적응형 쿨다운 시스템"""
        try:
            # 해당 종목의 최근 매도 이력 확인
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return True  # 데이터 없으면 매수 허용
            
            # 🔥 현재 보유 상태 확인
            current_holdings = sum([
                magic_data['CurrentAmt'] for magic_data in stock_data_info['MagicDataList']
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0
            ])
            
            # 🔥 보유 중인 종목은 쿨다운 면제 (부분매도 시스템의 핵심!)
            if current_holdings > 0:
                logger.info(f"✅ {stock_code} 현재 보유 중({current_holdings}주) - 쿨다운 면제")
                return True
            
            # 🔥 종목 레벨 + 차수별 매도이력 통합 확인
            latest_full_sell_time = None
            latest_sell_type = None
            latest_sell_return = 0
            
            # 1. 종목 레벨 GlobalSellHistory 체크 (우선순위)
            global_sell_history = stock_data_info.get('GlobalSellHistory', [])
            for sell_record in global_sell_history:
                try:
                    # 🔥 시간 파싱 버그 수정
                    sell_date_str = sell_record.get('date', '')
                    if ' ' in sell_date_str:
                        # "2025-09-06 00:00:19" 형식
                        sell_date = datetime.strptime(sell_date_str[:19], "%Y-%m-%d %H:%M:%S")
                    else:
                        # "2025-09-06" 형식
                        sell_date = datetime.strptime(sell_date_str[:10], "%Y-%m-%d")
                    
                    # 최근 3일 내 전량매도만 체크
                    if (datetime.now() - sell_date).total_seconds() / 86400 <= 3:
                        if latest_full_sell_time is None or sell_date > latest_full_sell_time:
                            latest_full_sell_time = sell_date
                            return_pct = sell_record.get('return_pct', 0)
                            latest_sell_return = return_pct
                            latest_sell_type = 'loss' if return_pct < 0 else 'profit'
                except:
                    continue
            
            # 2. 차수별 SellHistory 체크 (전량매도)
            for magic_data in stock_data_info['MagicDataList']:
                for sell_record in magic_data.get('SellHistory', []):
                    try:
                        # 🔥 시간 파싱 버그 수정
                        sell_date_str = sell_record.get('date', '')
                        if ' ' in sell_date_str:
                            # "2025-09-06 00:00:19" 형식
                            sell_date = datetime.strptime(sell_date_str[:19], "%Y-%m-%d %H:%M:%S")
                        else:
                            # "2025-09-06" 형식
                            sell_date = datetime.strptime(sell_date_str[:10], "%Y-%m-%d")
                        
                        # 최근 3일 내 전량매도만 체크
                        if (datetime.now() - sell_date).total_seconds() / 86400 <= 3:
                            if latest_full_sell_time is None or sell_date > latest_full_sell_time:
                                latest_full_sell_time = sell_date
                                return_pct = sell_record.get('return_pct', 0)
                                latest_sell_return = return_pct
                                latest_sell_type = 'loss' if return_pct < 0 else 'profit'
                    except:
                        continue
                
                # 3. PartialSellHistory에서 전량매도 완료 체크
                partial_history = magic_data.get('PartialSellHistory', [])
                for partial_record in partial_history:
                    if partial_record.get('is_full_sell', False):
                        try:
                            # 🔥 시간 파싱 버그 수정
                            sell_date_str = partial_record.get('date', '')
                            if ' ' in sell_date_str:
                                # "2025-09-06 00:00:19" 형식
                                sell_date = datetime.strptime(sell_date_str[:19], "%Y-%m-%d %H:%M:%S")
                            else:
                                # "2025-09-06" 형식
                                sell_date = datetime.strptime(sell_date_str[:10], "%Y-%m-%d")
                            
                            if (datetime.now() - sell_date).total_seconds() / 86400 <= 3:
                                if latest_full_sell_time is None or sell_date > latest_full_sell_time:
                                    latest_full_sell_time = sell_date
                                    return_pct = partial_record.get('return_pct', 0)
                                    latest_sell_return = return_pct
                                    latest_sell_type = 'loss' if return_pct < 0 else 'profit'
                        except:
                            continue
            
            # 최근 전량매도 이력이 없으면 매수 허용
            if latest_full_sell_time is None:
                logger.info(f"✅ {stock_code} 최근 전량매도 이력 없음 - 매수 허용")
                return True
            
            # 🔥 핵심 개선: 전량매도에만 적용되는 완화된 쿨다운
            hours_passed = (datetime.now() - latest_full_sell_time).total_seconds() / 3600
            
            # 1단계: 부분매도 시스템 고려한 기본 쿨다운 (기존 대비 50% 단축)
            if latest_sell_type == 'profit':
                if latest_sell_return >= 25:
                    base_cooldown = 6       # 25% 이상 대박: 6시간
                elif latest_sell_return >= 20:
                    base_cooldown = 5       # 20% 이상: 5시간
                elif latest_sell_return >= 15:
                    base_cooldown = 4       # 15% 이상: 4시간
                elif latest_sell_return >= 10:
                    base_cooldown = 3       # 10% 이상: 3시간
                else:
                    base_cooldown = 2       # 10% 미만: 2시간
            else:
                # 손절의 경우
                base_cooldown = 3           # 손절은 3시간
            
            # 2단계: 변동성 기반 조정
            try:
                df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", 30)
                if df is not None and len(df) >= 20:
                    volatility = df['close'].pct_change().std() * 100
                    
                    if volatility > 4.0:
                        volatility_multiplier = 0.4   # 60% 단축
                        volatility_desc = "고변동성"
                    elif volatility > 2.5:
                        volatility_multiplier = 0.6   # 40% 단축
                        volatility_desc = "중변동성"
                    else:
                        volatility_multiplier = 0.7   # 30% 단축
                        volatility_desc = "저변동성"
                else:
                    volatility_multiplier = 0.7
                    volatility_desc = "데이터부족"
            except:
                volatility_multiplier = 0.7
                volatility_desc = "계산실패"
            
            # 3단계: 시장 상황 기반 추가 조정
            market_timing = self.detect_market_timing()
            if market_timing in ["strong_downtrend", "downtrend"]:
                market_multiplier = 0.5     # 하락장에서는 50% 추가 단축
                market_desc = "하락장 기회"
            elif market_timing in ["strong_uptrend", "uptrend"]:
                market_multiplier = 1.0     # 상승장에서는 그대로
                market_desc = "상승장"
            else:
                market_multiplier = 0.8     # 중립에서는 20% 단축
                market_desc = "중립"
            
            # 최종 쿨다운 계산
            final_cooldown = base_cooldown * volatility_multiplier * market_multiplier
            final_cooldown = max(1, min(final_cooldown, 12))  # 최소 1시간, 최대 12시간
            
            if hours_passed < final_cooldown:
                logger.info(f"🕐 {stock_code} 전량매도 후 쿨다운: {hours_passed:.1f}h/{final_cooldown:.1f}h")
                logger.info(f"   📊 전량매도 수익률: {latest_sell_return:+.1f}% ({latest_sell_type})")
                logger.info(f"   📈 조정: {volatility_desc} × {market_desc}")
                logger.info(f"   💡 부분매도 시스템으로 쿨다운 50% 단축 적용")
                return False
            else:
                logger.info(f"✅ {stock_code} 전량매도 후 쿨다운 완료: {hours_passed:.1f}h 경과")
                logger.info(f"   🎯 적용된 쿨다운: {final_cooldown:.1f}h (부분매도 시스템 혜택)")
                return True
                
        except Exception as e:
            logger.error(f"개선된 쿨다운 체크 오류: {str(e)}")
            return True  # 오류 시 매수 허용

    def check_dynamic_daily_buy_limit(self, stock_code):
        """🔥 개선된 동적 일일 매수 한도 - 기회 기반 확대"""
        try:
            # 🔥 시장 상황 분석
            market_timing = self.detect_market_timing()
            
            # 🔥 변동성 분석
            try:
                spy_df = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 10)
                if spy_df is not None and len(spy_df) >= 5:
                    recent_volatility = spy_df['close'].pct_change().tail(5).std() * 100
                    is_high_volatility_day = recent_volatility > 2.0
                else:
                    is_high_volatility_day = False
            except:
                is_high_volatility_day = False
            
            # 🔥 기회 밀도 계산 (여러 종목이 동시에 매수 조건 만족하는지)
            target_stocks = config.target_stocks
            stocks_in_opportunity = 0
            
            for code, stock_config in target_stocks.items():
                try:
                    indicators = self.get_technical_indicators(code)
                    if indicators:
                        min_pullback = stock_config.get('min_pullback', 2.5)
                        max_rsi_buy = stock_config.get('max_rsi_buy', 65)
                        
                        if (indicators['pullback_from_high'] >= min_pullback and 
                            indicators['rsi'] <= max_rsi_buy):
                            stocks_in_opportunity += 1
                except:
                    continue
            
            opportunity_density = stocks_in_opportunity / len(target_stocks)
            
            # 🔥🔥🔥 동적 한도 계산 🔥🔥🔥
            base_daily_limit = 3  # 기본 3회
            
            # 시장 상황별 조정
            if market_timing in ["strong_downtrend", "downtrend"]:
                market_bonus = 3        # 하락장은 기회! +3회
                market_desc = "하락장 기회"
            elif market_timing in ["strong_uptrend", "uptrend"]:
                market_bonus = 1        # 상승장은 +1회
                market_desc = "상승장"
            else:
                market_bonus = 2        # 중립은 +2회
                market_desc = "중립"
            
            # 변동성 보너스
            volatility_bonus = 2 if is_high_volatility_day else 0
            volatility_desc = "고변동일" if is_high_volatility_day else "평상시"
            
            # 기회 밀도 보너스
            if opportunity_density >= 0.75:      # 75% 이상 종목이 기회
                opportunity_bonus = 2
                opportunity_desc = "기회 풍부"
            elif opportunity_density >= 0.5:     # 50% 이상 종목이 기회
                opportunity_bonus = 1
                opportunity_desc = "기회 보통"
            else:
                opportunity_bonus = 0
                opportunity_desc = "기회 부족"
            
            # 최종 한도 계산
            final_daily_limit = base_daily_limit + market_bonus + volatility_bonus + opportunity_bonus
            final_daily_limit = min(final_daily_limit, 8)  # 최대 8회 제한
            
            # 🔥 오늘 매수 횟수 체크
            today = datetime.now().strftime("%Y-%m-%d")
            today_buy_count = 0
            
            for stock_data in self.split_data_list:
                for magic_data in stock_data['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data.get('EntryDate') == today:
                        today_buy_count += 1
            
            # 🔥 종목별 개별 한도도 체크 (종목당 최대 2회)
            stock_today_count = 0
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    for magic_data in data_info['MagicDataList']:
                        if magic_data['IsBuy'] and magic_data.get('EntryDate') == today:
                            stock_today_count += 1
                    break
            
            # 결과 판단
            total_limit_ok = today_buy_count < final_daily_limit
            stock_limit_ok = stock_today_count < 2  # 종목당 최대 2회
            
            if total_limit_ok and stock_limit_ok:
                logger.info(f"✅ {stock_code} 일일 한도 여유: {today_buy_count}/{final_daily_limit}회 (종목: {stock_today_count}/2)")
                logger.info(f"   📊 조건: {market_desc} + {volatility_desc} + {opportunity_desc}")
                return True
            else:
                if not total_limit_ok:
                    logger.info(f"🚫 {stock_code} 일일 전체 한도 도달: {today_buy_count}/{final_daily_limit}회")
                if not stock_limit_ok:
                    logger.info(f"🚫 {stock_code} 종목별 한도 도달: {stock_today_count}/2회")
                return False
                
        except Exception as e:
            logger.error(f"동적 일일 한도 체크 오류: {str(e)}")
            return True  # 오류 시 허용

    def get_news_adjusted_buy_conditions(self, stock_code, base_conditions, news_sentiment):
        """🔥 개선된 뉴스 기반 조건 조정 - 차단에서 조건 강화로 변경"""
        try:
            news_decision = news_sentiment.get('decision', 'NEUTRAL')
            news_percentage = news_sentiment.get('percentage', 0)
            
            # 기본 조건 복사
            adjusted_conditions = base_conditions.copy()
            adjustment_desc = []
            
            if news_decision == 'NEGATIVE':
                if news_percentage >= 80:
                    # 🔥 매우 부정적 뉴스: 강한 조건 강화 (차단하지 않음!)
                    adjusted_conditions['min_pullback'] *= 1.8      # 조정폭 80% 증가
                    adjusted_conditions['max_rsi_buy'] -= 15        # RSI 15 낮춤
                    adjusted_conditions['position_limit'] = 2       # 최대 2차수까지
                    adjusted_conditions['green_candle_req'] *= 1.1  # 상승 요구 강화
                    
                    adjustment_desc = [
                        f"매우 부정 뉴스({news_percentage}%)",
                        f"조정폭 요구: {base_conditions['min_pullback']:.1f}% → {adjusted_conditions['min_pullback']:.1f}%",
                        f"RSI 요구: ≤{base_conditions['max_rsi_buy']} → ≤{adjusted_conditions['max_rsi_buy']}",
                        f"최대 차수: 5차 → 2차"
                    ]
                    
                elif news_percentage >= 60:
                    # 🔥 부정적 뉴스: 중간 조건 강화
                    adjusted_conditions['min_pullback'] *= 1.4      # 조정폭 40% 증가
                    adjusted_conditions['max_rsi_buy'] -= 8         # RSI 8 낮춤
                    adjusted_conditions['position_limit'] = 3       # 최대 3차수까지
                    adjusted_conditions['green_candle_req'] *= 1.05 # 상승 요구 소폭 강화
                    
                    adjustment_desc = [
                        f"부정 뉴스({news_percentage}%)",
                        f"조정폭 요구: {base_conditions['min_pullback']:.1f}% → {adjusted_conditions['min_pullback']:.1f}%",
                        f"RSI 요구: ≤{base_conditions['max_rsi_buy']} → ≤{adjusted_conditions['max_rsi_buy']}",
                        f"최대 차수: 5차 → 3차"
                    ]
                    
                else:
                    # 약간 부정적: 소폭 조건 강화
                    adjusted_conditions['min_pullback'] *= 1.2      # 조정폭 20% 증가
                    adjusted_conditions['max_rsi_buy'] -= 5         # RSI 5 낮춤
                    adjusted_conditions['position_limit'] = 4       # 최대 4차수까지
                    
                    adjustment_desc = [
                        f"약간 부정 뉴스({news_percentage}%)",
                        f"조정폭 요구: {base_conditions['min_pullback']:.1f}% → {adjusted_conditions['min_pullback']:.1f}%",
                        f"RSI 요구: ≤{base_conditions['max_rsi_buy']} → ≤{adjusted_conditions['max_rsi_buy']}"
                    ]
                    
            elif news_decision == 'POSITIVE':
                # 🔥 긍정적 뉴스: 조건 완화 (기존 로직 유지)
                if news_percentage >= 70:
                    adjusted_conditions['min_pullback'] *= 0.8     # 조정폭 20% 완화
                    adjusted_conditions['max_rsi_buy'] += 5        # RSI 5 상향
                    adjusted_conditions['green_candle_req'] *= 0.95 # 상승 요구 완화
                    
                    adjustment_desc = [
                        f"긍정 뉴스({news_percentage}%)",
                        f"조정폭 요구: {base_conditions['min_pullback']:.1f}% → {adjusted_conditions['min_pullback']:.1f}%",
                        f"RSI 요구: ≤{base_conditions['max_rsi_buy']} → ≤{adjusted_conditions['max_rsi_buy']}"
                    ]
            else:
                # NEUTRAL: 조정 없음
                adjustment_desc = ["뉴스 중립 - 기본 조건 적용"]
            
            # 🔥 뉴스 신뢰도 및 시간 경과 고려
            if hasattr(self, 'news_cache_time'):
                cache_age_minutes = (datetime.now() - self.news_cache_time).total_seconds() / 60
                if cache_age_minutes > 180:  # 3시간 이상 오래된 뉴스
                    # 뉴스 영향력 50% 감소
                    if news_decision == 'NEGATIVE':
                        # 강화된 조건을 원래로 50% 복원
                        pullback_diff = adjusted_conditions['min_pullback'] - base_conditions['min_pullback']
                        rsi_diff = base_conditions['max_rsi_buy'] - adjusted_conditions['max_rsi_buy']
                        
                        adjusted_conditions['min_pullback'] = base_conditions['min_pullback'] + (pullback_diff * 0.5)
                        adjusted_conditions['max_rsi_buy'] = base_conditions['max_rsi_buy'] - (rsi_diff * 0.5)
                        
                        adjustment_desc.append(f"뉴스 시효({cache_age_minutes:.0f}분) - 영향 50% 감소")
            
            # 로깅
            if adjustment_desc:
                logger.info(f"📰 {stock_code} 뉴스 기반 조건 조정:")
                for desc in adjustment_desc:
                    logger.info(f"   {desc}")
            
            return adjusted_conditions, adjustment_desc
            
        except Exception as e:
            logger.error(f"뉴스 기반 조건 조정 오류: {str(e)}")
            return base_conditions, ["뉴스 조정 실패 - 기본 조건 적용"]

    def check_reentry_conditions(self, stock_code, indicators):
        """재진입 조건 체크 - 🔥 개선된 쿨다운과 연계"""
        try:
            # 🔥 1. 쿨다운 체크가 최우선 (개선된 시스템)
            cooldown_ok = self.check_post_sell_cooldown(stock_code)
            if not cooldown_ok:
                return False, "매도 후 쿨다운 대기 중"
            
            # 해당 종목의 최근 매도 이력 확인
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return True, "신규 종목"
            
            # 🔥 2. 최근 수익 매도 이력 찾기
            latest_profit_sell = None
            latest_sell_time = None
            last_avg_buy_price = None
            
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            # 🔥 3. 매도 이력 상세 분석
            for magic_data in stock_data_info['MagicDataList']:
                # 기존 SellHistory에서 최근 수익 매도 찾기
                for sell_record in magic_data.get('SellHistory', []):
                    sell_date = sell_record.get('date', '')
                    return_pct = sell_record.get('return_pct', 0)
                    
                    # 최근 24시간 내 수익 매도만 체크
                    if sell_date in [today, yesterday] and return_pct > 0:
                        if latest_profit_sell is None:
                            latest_profit_sell = sell_record
                            last_avg_buy_price = magic_data.get('EntryPrice', 0)
                            latest_sell_time = sell_date
                
                # PartialSellHistory에서 전량매도 완료 체크
                partial_history = magic_data.get('PartialSellHistory', [])
                for partial_record in partial_history:
                    if partial_record.get('is_full_sell', False):
                        sell_date = partial_record.get('date', '')
                        return_pct = partial_record.get('return_pct', 0)
                        
                        if sell_date in [today, yesterday] and return_pct > 0:
                            if latest_profit_sell is None:
                                latest_profit_sell = partial_record
                                last_avg_buy_price = magic_data.get('EntryPrice', 0)
                                latest_sell_time = sell_date
            
            # 🔥 4. 최근 수익 매도가 없으면 일반적 재진입 허용
            if latest_profit_sell is None:
                logger.info(f"✅ {stock_code} 최근 수익 매도 없음 - 재진입 허용")
                return True, "최근 수익 매도 이력 없음"
            
            # 🔥 5. 수익 매도 후 재진입 조건 체크
            try:
                current_price = indicators.get('current_price', 0)
                last_sell_price = latest_profit_sell.get('price', 0)
                last_sell_return = latest_profit_sell.get('return_pct', 0)
                
                if current_price <= 0 or last_sell_price <= 0 or last_avg_buy_price <= 0:
                    logger.warning(f"⚠️ {stock_code} 가격 정보 부족 - 재진입 허용")
                    return True, "가격 정보 부족으로 허용"
                
                # 🔥 6. 재진입 가격 조건 계산
                # 수익률에 따른 차등 조건
                if last_sell_return >= 20:
                    # 20% 이상 고수익: 매도가 대비 8% 이상 하락 필요
                    target_threshold = last_sell_price * 0.92
                    method_desc = "고수익 재진입(매도가 -8%)"
                elif last_sell_return >= 10:
                    # 10-20% 수익: 매도가 대비 5% 이상 하락 필요
                    target_threshold = last_sell_price * 0.95
                    method_desc = "중수익 재진입(매도가 -5%)"
                elif last_sell_return >= 5:
                    # 5-10% 수익: 매도가 대비 3% 이상 하락 필요
                    target_threshold = last_sell_price * 0.97
                    method_desc = "소수익 재진입(매도가 -3%)"
                else:
                    # 5% 미만 수익: 평균 매수가 이하에서만
                    target_threshold = last_avg_buy_price * 0.98
                    method_desc = "저수익 재진입(평균가 -2%)"
                
                # 🔥 7. 가격 조건 체크
                if current_price > target_threshold:
                    drop_from_sell = (last_sell_price - current_price) / last_sell_price * 100
                    drop_from_avg = (last_avg_buy_price - current_price) / last_avg_buy_price * 100
                    
                    return False, (f"재매수 가격 조건 미달 (현재: ${current_price:.2f})\n"
                                f"  📊 필요가격: ${target_threshold:.2f} 이하 ({method_desc})\n"
                                f"  📉 매도가 대비: {drop_from_sell:+.1f}%\n"
                                f"  📉 평균가 대비: {drop_from_avg:+.1f}%")
                
                # 🔥 8. 추가 안전 조건들
                
                # RSI 과매수 방지
                if indicators['rsi'] > 65:
                    return False, f"RSI 과매수 (현재: {indicators['rsi']:.1f} > 65)"
                
                # 시장 상황별 추가 제한
                market_timing = self.detect_market_timing()
                if market_timing == "strong_uptrend":
                    if current_price > last_sell_price * 0.92:  # 8% 이상 하락 필요
                        return False, "강한 상승장에서 재매수 제한 (매도가 대비 8% 이상 하락 필요)"
                
                # 🔥 9. 일일 재매수 제한 (강화)
                reentry_count_today = 0
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data.get('EntryDate') == today and magic_data['IsBuy']:
                        reentry_count_today += 1
                
                if reentry_count_today >= 1:
                    return False, "일일 재매수 제한 (하루 1회만 허용)"
                
                # 🔥 10. 가격 상승 중 재진입 차단 (추가 안전장치)
                if current_price > last_sell_price * 1.02:  # 2% 이상 상승시
                    return False, f"가격 상승 중 재진입 차단 (매도가 ${last_sell_price:.2f} → 현재가 ${current_price:.2f}, +{((current_price/last_sell_price-1)*100):.1f}%)"
                
                # 🔥 11. 모든 조건 통과
                drop_from_sell = (last_sell_price - current_price) / last_sell_price * 100
                drop_from_avg = (last_avg_buy_price - current_price) / last_avg_buy_price * 100
                
                success_msg = (f"재매수 조건 충족!\n"
                            f"  💰 이전 매도: ${last_sell_price:.2f} ({last_sell_return:+.1f}% 수익)\n"
                            f"  📊 평균 매수가: ${last_avg_buy_price:.2f}\n"
                            f"  🎯 현재가: ${current_price:.2f} ({method_desc})\n"
                            f"  📉 매도가 대비: {drop_from_sell:+.1f}%\n"
                            f"  📉 평균가 대비: {drop_from_avg:+.1f}%")

                logger.info(f"✅ {stock_code} 재진입 조건 모두 충족")
                logger.info(f"   💰 이전 매도: ${last_sell_price:.2f} ({last_sell_return:+.1f}%)")
                logger.info(f"   🎯 현재가: ${current_price:.2f} (목표: ${target_threshold:.2f} 이하)")
                logger.info(f"   📉 하락폭: {drop_from_sell:+.1f}% (매도가 대비)")
                
                return True, success_msg
                    
            except Exception as e:
                logger.error(f"재매수 조건 계산 오류: {str(e)}")
                return True, "계산 오류로 허용"
        
        except Exception as e:
            logger.error(f"재진입 조건 체크 전체 오류: {str(e)}")
            return True, "전체 오류로 허용"
   
    def is_same_day_resell_allowed(self, stock_code):
        """당일 재매수 허용 여부 체크"""
        try:
            buy_control = config.config.get('buy_control', {})
            max_daily_trades = buy_control.get('max_daily_trades', 2)  # 하루 최대 2회 거래
            
            # 오늘 매매 횟수 계산
            today = datetime.now().strftime("%Y-%m-%d")
            daily_trade_count = 0
            
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return True
            
            # 오늘 매수 횟수
            for magic_data in stock_data_info['MagicDataList']:
                if magic_data.get('EntryDate') == today:
                    daily_trade_count += 1
            
            # 오늘 매도 횟수
            for magic_data in stock_data_info['MagicDataList']:
                for sell_record in magic_data.get('SellHistory', []):
                    if sell_record.get('date') == today:
                        daily_trade_count += 1
            
            if daily_trade_count >= max_daily_trades:
                logger.info(f"🚫 {stock_code} 일일 거래 한도 도달: {daily_trade_count}/{max_daily_trades}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"일일 거래 한도 체크 오류: {str(e)}")
            return True

################################### 뉴스 분석 시스템 ##################################

    def analyze_all_stocks_news(self):
        """모든 타겟 종목의 뉴스를 한번에 분석"""
        try:
            target_stocks = config.target_stocks
            stocks_list = []
            for stock_code, stock_config in target_stocks.items():
                stocks_list.append({
                    "ticker": stock_code,
                    "company_name": stock_config.get("name", stock_code)
                })
            
            logger.info(f"📰 전체 종목 뉴스 분석 시작: {len(stocks_list)}개 종목")
            news_results = news_analysis_us_finhub.analyze_us_stocks_news(stocks_list)
            
            # 결과를 종목별로 정리
            news_summary = {}
            if news_results and "stocks" in news_results:
                for company_name, data in news_results["stocks"].items():
                    ticker = data.get("ticker", "")
                    analysis = data.get("analysis", {})
                    
                    if ticker and analysis:
                        news_summary[ticker] = {
                            "decision": analysis.get("decision", "NEUTRAL"),
                            "percentage": analysis.get("percentage", 0),
                            "reason": analysis.get("reason", ""),
                            "company_name": company_name
                        }
            
            # 결과 로깅
            logger.info("📊 전체 종목 뉴스 분석 완료:")
            for ticker, sentiment in news_summary.items():
                decision_emoji = {"POSITIVE": "📈", "NEGATIVE": "📉", "NEUTRAL": "➖"}.get(sentiment["decision"], "❓")
                logger.info(f"  {decision_emoji} {ticker}: {sentiment['decision']} ({sentiment['percentage']}%)")
            
            return news_summary
            
        except Exception as e:
            logger.error(f"전체 종목 뉴스 분석 중 오류: {str(e)}")
            return {}

    def get_cached_news_summary(self):
            """캐시된 뉴스 분석 결과 조회 (240분 유효)"""
            try:
                current_time = datetime.now()
                
                # 캐시가 없거나 30분 이상 지났으면 None 반환
                if not hasattr(self, 'news_cache_time') or not self.news_cache:
                    return None
                    
                time_diff = (current_time - self.news_cache_time).total_seconds()
                cache_expire_minutes = 240  # 240분 캐시
                
                if time_diff > (cache_expire_minutes * 60):
                    logger.info(f"📰 뉴스 캐시 만료 ({time_diff/60:.1f}분 경과)")
                    return None
                    
                logger.info(f"📰 캐시된 뉴스 사용 (캐시 나이: {time_diff/60:.1f}분)")
                return self.news_cache
                
            except Exception as e:
                logger.error(f"뉴스 캐시 조회 중 오류: {str(e)}")
                return None     

    def cache_news_summary(self, news_summary):
        """뉴스 분석 결과 캐시 저장"""
        try:
            self.news_cache = news_summary
            self.news_cache_time = datetime.now()
            logger.info("📰 뉴스 분석 결과 캐시에 저장 완료")
        except Exception as e:
            logger.error(f"뉴스 캐시 저장 중 오류: {str(e)}")

################################### 성과 보고 시스템 ##################################

    def send_daily_performance_report(self):
        """일일 성과 보고서 전송 - 미국 장마감 후"""
        try:
            logger.info("📊 일일 성과 보고서 생성 시작")
            
            # 🔥 현재 계좌 정보 조회
            balance = SafeKisUS.safe_get_balance("USD")
            if not balance:
                logger.error("계좌 정보 조회 실패 - 일일 보고서 생성 불가")
                return
                
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            invested_amount = current_total - remain_money
            
            # 🔥 초기 투자 예산 대비 성과 계산
            initial_budget = config.absolute_budget
            total_change = current_total - initial_budget
            total_change_pct = (total_change / initial_budget) * 100 if initial_budget > 0 else 0
            
            # 📅 오늘 날짜
            today = datetime.now().strftime("%Y-%m-%d")
            today_korean = datetime.now().strftime("%Y년 %m월 %d일")
            
            # 🔍 오늘의 매매 현황 집계
            today_buys = 0
            today_sells = 0
            today_buy_amount = 0
            today_sell_amount = 0
            today_realized_pnl = 0
            
            # 종목별 현황 분석
            stock_status = []
            total_realized_pnl = 0
            
            for stock_data in self.split_data_list:
                stock_code = stock_data['StockCode']
                stock_name = stock_data['StockName']
                
                # 보유 현황 조회
                holdings = self.get_current_holdings(stock_code)
                current_price = SafeKisUS.safe_get_current_price(stock_code)
                
                # 평균 매수가 및 수익률 계산
                total_investment = 0
                total_shares = 0
                active_positions = 0
                
                for magic_data in stock_data['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        total_investment += magic_data['EntryPrice'] * magic_data['CurrentAmt']
                        total_shares += magic_data['CurrentAmt']
                        active_positions += 1
                    
                    # 오늘 매수 체크
                    if magic_data['IsBuy'] and magic_data.get('EntryDate') == today:
                        today_buys += 1
                        today_buy_amount += magic_data['EntryPrice'] * magic_data['EntryAmt']
                    
                    # 오늘 매도 체크
                    for sell_record in magic_data.get('SellHistory', []):
                        if sell_record.get('date') == today:
                            today_sells += 1
                            today_sell_amount += sell_record['price'] * sell_record['amount']
                            today_realized_pnl += (sell_record['price'] - magic_data['EntryPrice']) * sell_record['amount']
                
                # 현재 수익률 계산
                if total_shares > 0 and current_price:
                    avg_entry_price = total_investment / total_shares
                    current_return = (current_price - avg_entry_price) / avg_entry_price * 100
                    unrealized_pnl = (current_price - avg_entry_price) * holdings['amount']
                else:
                    avg_entry_price = 0
                    current_return = 0
                    unrealized_pnl = 0
                
                # 실현손익 누적
                stock_realized_pnl = stock_data.get('RealizedPNL', 0)
                total_realized_pnl += stock_realized_pnl
                
                # 종목 상태 결정
                if holdings['amount'] > 0:
                    status = f"{active_positions}차수 보유"
                    status_emoji = "📈" if current_return > 0 else "📉" if current_return < 0 else "➖"
                else:
                    status = "미보유"
                    status_emoji = "⭕"
                
                stock_status.append({
                    'code': stock_code,
                    'name': stock_name,
                    'status': status,
                    'emoji': status_emoji,
                    'shares': holdings['amount'],
                    'avg_price': avg_entry_price,
                    'current_price': current_price,
                    'return_pct': current_return,
                    'unrealized_pnl': unrealized_pnl,
                    'realized_pnl': stock_realized_pnl
                })
            
            # 🔥 일일 보고서 메시지 생성
            report = f"📊 **일일 성과 보고서** ({today_korean})\n"
            report += "=" * 38 + "\n\n"
            
            # 💰 전체 자산 현황
            report += f"💰 **전체 자산 현황**\n"
            report += f"```\n"
            report += f"현재 총자산: ${current_total:,.0f}\n"
            report += f"초기 예산:   ${initial_budget:,.0f}\n"
            report += f"손익:       ${total_change:+,.0f} ({total_change_pct:+.2f}%)\n"
            report += f"현금 잔고:   ${remain_money:,.0f}\n"
            report += f"투자 금액:   ${invested_amount:,.0f}\n"
            report += f"```\n\n"
            
            # 📈 종목별 현황
            report += f"📈 **종목별 현황**\n"
            for stock in stock_status:
                report += f"{stock['emoji']} **{stock['name']}** ({stock['code']})\n"
                if stock['shares'] > 0:
                    report += f"   💼 {stock['status']} | {stock['shares']}주 @ ${stock['avg_price']:.2f}\n"
                    report += f"   💲 현재가: ${stock['current_price']:.2f} | 수익률: {stock['return_pct']:+.2f}%\n"
                    report += f"   📊 미실현: ${stock['unrealized_pnl']:+,.0f} | 실현누적: ${stock['realized_pnl']:+,.0f}\n"
                else:
                    report += f"   💼 {stock['status']} | 실현누적: ${stock['realized_pnl']:+,.0f}\n"
                report += "\n"
            
            # 📊 오늘의 매매 활동
            if today_buys > 0 or today_sells > 0:
                report += f"🔄 **오늘의 매매 활동**\n"
                if today_buys > 0:
                    report += f"   🛒 매수: {today_buys}회 | ${today_buy_amount:,.0f}\n"
                if today_sells > 0:
                    report += f"   💰 매도: {today_sells}회 | ${today_sell_amount:,.0f}\n"
                    report += f"   📈 오늘 실현손익: ${today_realized_pnl:+,.0f}\n"
                report += "\n"
            else:
                report += f"🔄 **오늘의 매매 활동**: 매매 없음\n\n"
            
            # 📋 투자 성과 요약
            total_unrealized = sum([s['unrealized_pnl'] for s in stock_status])
            report += f"📋 **투자 성과 요약**\n"
            report += f"```\n"
            report += f"실현 손익:   ${total_realized_pnl:+,.0f}\n"
            report += f"미실현손익:  ${total_unrealized:+,.0f}\n"
            report += f"총 손익:     ${total_realized_pnl + total_unrealized:+,.0f}\n"
            report += f"수익률:      {((total_realized_pnl + total_unrealized) / initial_budget * 100):+.2f}%\n"
            report += f"```\n\n"
            
            # 💡 내일 전망
            report += f"💡 **내일 전망**\n"
            market_timing = self.detect_market_timing()
            market_desc = {
                "strong_uptrend": "강한 상승 추세 🚀",
                "uptrend": "상승 추세 📈", 
                "neutral": "중립 ➖",
                "downtrend": "하락 추세 📉",
                "strong_downtrend": "강한 하락 추세 🔻"
            }
            report += f"시장 상황: {market_desc.get(market_timing, '분석 중')}\n"
            
            # 매수 가능 차수 안내
            market_limits = config.config.get('market_position_limits', {})
            max_positions = market_limits.get(market_timing, 3)
            report += f"최대 매수 차수: {max_positions}차수\n"
            
            report += f"\n🕒 보고서 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Discord 전송
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(report)
                logger.info("✅ 일일 성과 보고서 전송 완료")
            else:
                logger.info("📊 일일 성과 보고서 생성 완료 (Discord 알림 비활성화)")
                logger.info(f"\n{report}")
                
        except Exception as e:
            logger.error(f"일일 성과 보고서 생성 중 오류: {str(e)}")
            error_msg = f"⚠️ 일일 보고서 생성 오류\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n오류: {str(e)}"
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(error_msg)

    def send_weekly_performance_report(self):
        """주간 성과 보고서 전송 - 금요일 장마감 후"""
        try:
            logger.info("📈 주간 성과 보고서 생성 시작")
            
            # 현재 계좌 정보 조회
            balance = SafeKisUS.safe_get_balance("USD")
            if not balance:
                logger.error("계좌 정보 조회 실패 - 주간 보고서 생성 불가")
                return
                
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 초기 투자 예산 대비 성과
            initial_budget = config.absolute_budget
            total_change = current_total - initial_budget
            total_change_pct = (total_change / initial_budget) * 100 if initial_budget > 0 else 0
            
            # 주간 기간 계산 (지난 7일)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            week_desc = f"{start_date.strftime('%m/%d')} - {end_date.strftime('%m/%d')}"
            
            # 주간 매매 통계 집계
            week_buys = 0
            week_sells = 0
            week_buy_amount = 0
            week_sell_amount = 0
            week_realized_pnl = 0
            
            # 종목별 주간 성과 분석
            stock_weekly_performance = []
            total_realized_pnl = 0
            
            for stock_data in self.split_data_list:
                stock_code = stock_data['StockCode']
                stock_name = stock_data['StockName']
                
                # 보유 현황
                holdings = self.get_current_holdings(stock_code)
                current_price = SafeKisUS.safe_get_current_price(stock_code)
                
                # 주간 매매 집계
                stock_week_buys = 0
                stock_week_sells = 0
                stock_week_realized = 0
                
                # 평균 매수가 계산
                total_investment = 0
                total_shares = 0
                max_position = 0
                
                for magic_data in stock_data['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        total_investment += magic_data['EntryPrice'] * magic_data['CurrentAmt']
                        total_shares += magic_data['CurrentAmt']
                        max_position = max(max_position, magic_data['Number'])
                    
                    # 주간 매수 체크
                    if magic_data['IsBuy'] and magic_data.get('EntryDate'):
                        try:
                            entry_date = datetime.strptime(magic_data['EntryDate'], "%Y-%m-%d")
                            if start_date <= entry_date <= end_date:
                                stock_week_buys += 1
                                week_buys += 1
                                week_buy_amount += magic_data['EntryPrice'] * magic_data['EntryAmt']
                        except:
                            pass
                    
                    # 주간 매도 체크
                    for sell_record in magic_data.get('SellHistory', []):
                        try:
                            sell_date = datetime.strptime(sell_record.get('date', ''), "%Y-%m-%d")
                            if start_date <= sell_date <= end_date:
                                stock_week_sells += 1
                                week_sells += 1
                                week_sell_amount += sell_record['price'] * sell_record['amount']
                                pnl = (sell_record['price'] - magic_data['EntryPrice']) * sell_record['amount']
                                stock_week_realized += pnl
                                week_realized_pnl += pnl
                        except:
                            pass
                
                # 현재 수익률 계산
                if total_shares > 0 and current_price:
                    avg_entry_price = total_investment / total_shares
                    current_return = (current_price - avg_entry_price) / avg_entry_price * 100
                    unrealized_pnl = (current_price - avg_entry_price) * holdings['amount']
                else:
                    avg_entry_price = 0
                    current_return = 0
                    unrealized_pnl = 0
                
                # 누적 실현손익
                stock_realized_pnl = stock_data.get('RealizedPNL', 0)
                total_realized_pnl += stock_realized_pnl
                
                stock_weekly_performance.append({
                    'code': stock_code,
                    'name': stock_name,
                    'shares': holdings['amount'],
                    'max_position': max_position,
                    'current_price': current_price,
                    'avg_price': avg_entry_price,
                    'return_pct': current_return,
                    'unrealized_pnl': unrealized_pnl,
                    'total_realized_pnl': stock_realized_pnl,
                    'week_buys': stock_week_buys,
                    'week_sells': stock_week_sells,
                    'week_realized': stock_week_realized
                })
            
            # 🔥 주간 보고서 메시지 생성
            report = f"📈 **주간 성과 보고서** ({week_desc})\n"
            report += "=" * 60 + "\n\n"
            
            # 💰 핵심 성과 지표
            report += f"💰 **핵심 성과 지표**\n"
            report += f"```\n"
            report += f"현재 총자산:    ${current_total:,.0f}\n"
            report += f"초기 예산:      ${initial_budget:,.0f}\n"
            report += f"절대 손익:      ${total_change:+,.0f}\n"
            report += f"수익률:         {total_change_pct:+.2f}%\n"
            report += f"현금 비중:      {(remain_money/current_total*100):.1f}%\n"
            report += f"```\n\n"
            
            # 📊 주간 매매 활동
            report += f"📊 **주간 매매 활동**\n"
            if week_buys > 0 or week_sells > 0:
                report += f"```\n"
                report += f"총 매수:        {week_buys}회 | ${week_buy_amount:,.0f}\n"
                report += f"총 매도:        {week_sells}회 | ${week_sell_amount:,.0f}\n"
                report += f"주간 실현손익:  ${week_realized_pnl:+,.0f}\n"
                if week_buy_amount > 0:
                    turnover = (week_sell_amount / week_buy_amount) * 100
                    report += f"회전율:         {turnover:.1f}%\n"
                report += f"```\n\n"
            else:
                report += f"이번 주 매매 활동이 없었습니다.\n\n"
            
            # 🎯 종목별 상세 성과
            report += f"🎯 **종목별 상세 성과**\n"
            for stock in stock_weekly_performance:
                # 종목별 배치 정보
                weight = 0
                target_stocks = config.target_stocks
                if stock['code'] in target_stocks:
                    weight = target_stocks[stock['code']]['weight']
                
                report += f"**{stock['name']} ({stock['code']})** - 비중 {weight*100:.0f}%\n"
                
                if stock['shares'] > 0:
                    report += f"   📊 보유: {stock['shares']}주 ({stock['max_position']}차수) @ ${stock['avg_price']:.2f}\n"
                    report += f"   💲 현재가: ${stock['current_price']:.2f} | 수익률: {stock['return_pct']:+.2f}%\n"
                    report += f"   💰 미실현: ${stock['unrealized_pnl']:+,.0f}\n"
                else:
                    report += f"   📊 현재 미보유\n"
                
                report += f"   🔄 주간 매매: 매수 {stock['week_buys']}회 | 매도 {stock['week_sells']}회\n"
                report += f"   📈 누적 실현: ${stock['total_realized_pnl']:+,.0f}\n"
                if stock['week_realized'] != 0:
                    report += f"   ⚡ 주간 실현: ${stock['week_realized']:+,.0f}\n"
                report += "\n"
            
            # 📋 포트폴리오 분석
            total_unrealized = sum([s['unrealized_pnl'] for s in stock_weekly_performance])
            total_portfolio_pnl = total_realized_pnl + total_unrealized
            
            report += f"📋 **포트폴리오 분석**\n"
            report += f"```\n"
            report += f"총 실현손익:    ${total_realized_pnl:+,.0f}\n"
            report += f"총 미실현손익:  ${total_unrealized:+,.0f}\n"
            report += f"포트폴리오 손익: ${total_portfolio_pnl:+,.0f}\n"
            report += f"포트폴리오 수익률: {(total_portfolio_pnl/initial_budget*100):+.2f}%\n"
            report += f"```\n\n"
            
            # 🔮 다음 주 전략
            report += f"🔮 **다음 주 전략**\n"
            market_timing = self.detect_market_timing()
            
            if market_timing in ["strong_uptrend", "uptrend"]:
                report += f"📈 상승 추세 지속 → 적극적 매수 전략\n"
            elif market_timing in ["downtrend", "strong_downtrend"]:
                report += f"📉 하락 추세 → 방어적 포지션 관리\n"
            else:
                report += f"➖ 중립 상황 → 선별적 기회 포착\n"
            
            # 현금 비중 조언
            cash_ratio = remain_money / current_total
            if cash_ratio > 0.7:
                report += f"💰 현금 비중 높음 ({cash_ratio*100:.0f}%) → 매수 기회 대기\n"
            elif cash_ratio < 0.2:
                report += f"⚠️ 현금 비중 낮음 ({cash_ratio*100:.0f}%) → 신중한 매수 필요\n"
            
            report += f"\n📅 보고서 생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            report += f"\n🔄 다음 주간 보고서: 다음 금요일 장마감 후"
            
            # Discord 전송
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(report)
                logger.info("✅ 주간 성과 보고서 전송 완료")
            else:
                logger.info("📈 주간 성과 보고서 생성 완료 (Discord 알림 비활성화)")
                logger.info(f"\n{report}")
                
        except Exception as e:
            logger.error(f"주간 성과 보고서 생성 중 오류: {str(e)}")
            error_msg = f"⚠️ 주간 보고서 생성 오류\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n오류: {str(e)}"
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(error_msg)

    def _upgrade_json_structure_if_needed(self):
        """JSON 구조 업그레이드: 3차수 시스템 지원"""
        is_modified = False
        
        for stock_data in self.split_data_list:
            magic_data_list = stock_data['MagicDataList']
            
            # 🔥 3차수로 조정 (5개 → 3개)
            if len(magic_data_list) > 3:
                stock_data['MagicDataList'] = magic_data_list[:3]
                is_modified = True
                logger.info(f"🔄 {stock_data['StockCode']} 3차수로 조정")
            elif len(magic_data_list) < 3:
                # 3개보다 적으면 추가 생성
                while len(magic_data_list) < 3:
                    new_position = len(magic_data_list) + 1
                    magic_data_list.append({
                        'Number': new_position,
                        'EntryPrice': 0,
                        'EntryAmt': 0,
                        'CurrentAmt': 0,
                        'SellHistory': [],
                        'EntryDate': "",
                        'IsBuy': False,
                        'OriginalAmt': 0,
                        'PartialSellHistory': [],
                        'PartialSellStage': 0,
                        'RemainingRatio': 0.0,
                        'MaxProfitBeforePartialSell': 0.0
                    })
                is_modified = True
            
            # 각 차수별 필드 검증 및 추가
            for magic_data in magic_data_list:
                # 기존 필드들 (기존 로직 유지)
                if 'CurrentAmt' not in magic_data and magic_data.get('IsBuy', False):
                    magic_data['CurrentAmt'] = magic_data.get('EntryAmt', 0)
                    is_modified = True
                
                if 'SellHistory' not in magic_data:
                    magic_data['SellHistory'] = []
                    is_modified = True
                    
                if 'EntryDate' not in magic_data:
                    magic_data['EntryDate'] = ""
                    is_modified = True

                # 부분매도 시스템 필드들 (기존 로직 유지)
                if 'PartialSellHistory' not in magic_data:
                    magic_data['PartialSellHistory'] = []
                    is_modified = True
                    
                if 'OriginalAmt' not in magic_data:
                    if magic_data.get('IsBuy', False):
                        magic_data['OriginalAmt'] = magic_data.get('EntryAmt', 0)
                    else:
                        magic_data['OriginalAmt'] = 0
                    is_modified = True
                    
                if 'PartialSellStage' not in magic_data:
                    magic_data['PartialSellStage'] = 0
                    is_modified = True
                    
                if 'RemainingRatio' not in magic_data:
                    if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                        magic_data['RemainingRatio'] = 1.0
                    else:
                        magic_data['RemainingRatio'] = 0.0
                    is_modified = True
                    
                if 'MaxProfitBeforePartialSell' not in magic_data:
                    magic_data['MaxProfitBeforePartialSell'] = 0.0
                    is_modified = True
        
        if is_modified:
            logger.info("🔥 SILVER 봇 3차수 JSON 구조 업그레이드 완료")
            self.save_split_data()

    def calculate_dynamic_budget(self):
        """🔥 독립적 성과 기반 동적 예산 계산 (안전장치 추가)"""
        try:
            # 🔥 미국주식 계좌 정보 조회 (USD 기준)
            balance = SafeKisUS.safe_get_balance("USD")

            if not balance:
                logger.error("미국주식 계좌 정보 조회 실패")
                return config.absolute_budget
                
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 🔥 초기 자산 설정 (첫 실행시) - 기존 로직 유지
            if config.initial_total_asset == 0:
                config.update_initial_asset(current_total)
                logger.info(f"🎯 초기 총 자산 설정: ${current_total:,.0f}")
            
            # 🔥 전략별 예산 계산
            strategy = config.absolute_budget_strategy
            base_budget = config.absolute_budget
            
            if strategy == "proportional":
                # 🔥 performance_tracker 존재 여부 확인 (안전장치)
                if hasattr(self, 'performance_tracker') and self.performance_tracker:
                    # 독립적 성과 기반 동적 조정 (새로운 로직)
                    perf_data = self.performance_tracker.calculate_bot_specific_performance()
                    
                    if perf_data:
                        # 자신만의 실제 성과로 계산
                        performance_rate = perf_data['actual_performance']
                        logger.info(f"📊 독립 성과 기반 계산: {performance_rate*100:+.2f}%")
                    else:
                        # 독립 성과 계산 실패시 기존 방식으로 폴백
                        logger.warning("독립 성과 계산 실패, 전체 계좌 기준으로 폴백")
                        initial_asset = config.initial_total_asset
                        performance_rate = (current_total - initial_asset) / initial_asset if initial_asset > 0 else 0
                else:
                    # performance_tracker가 없으면 기존 방식으로 폴백
                    logger.warning("⚠️ 독립 성과 추적기 미초기화, 전체 계좌 기준으로 계산")
                    initial_asset = config.initial_total_asset
                    performance_rate = (current_total - initial_asset) / initial_asset if initial_asset > 0 else 0
                
                # 🔥 성과 추적 업데이트 (기존 로직 유지)
                config.update_performance(performance_rate)
                
                # 🔥 성과 기반 multiplier 계산 (기존 로직 유지)
                if performance_rate > 0.3:          # +30% 이상: 140% 예산
                    multiplier = 1.4
                elif performance_rate > 0.2:        # +20%: 130% 예산
                    multiplier = 1.3
                elif performance_rate > 0.15:       # +15%: 125% 예산
                    multiplier = 1.25
                elif performance_rate > 0.1:        # +10%: 120% 예산
                    multiplier = 1.2
                elif performance_rate > 0.05:       # +5%: 110% 예산
                    multiplier = 1.1
                elif performance_rate > -0.05:      # ±5%: 100% 예산
                    multiplier = 1.0
                elif performance_rate > -0.1:       # -10%: 95% 예산
                    multiplier = 0.95
                elif performance_rate > -0.15:      # -15%: 90% 예산
                    multiplier = 0.9
                elif performance_rate > -0.2:       # -20%: 85% 예산
                    multiplier = 0.85
                else:                               # -20% 초과: 70% 예산
                    multiplier = 0.7
                    
                dynamic_budget = base_budget * multiplier
                
            elif strategy == "adaptive":
                # 🔥 adaptive 전략 (기존 로직 유지)
                loss_tolerance = config.config.get("budget_loss_tolerance", 0.25)
                min_budget = base_budget * (1 - loss_tolerance)
                
                if current_total >= min_budget:
                    dynamic_budget = base_budget
                else:
                    dynamic_budget = max(current_total * 0.8, min_budget)
                    
            else:  # "strict"
                # 🔥 고정 예산 (기존 로직 유지)
                dynamic_budget = base_budget
            
            # 🔥 안전장치: 현금 잔고 기반 제한 (기존 로직 유지)
            safety_ratio = config.config.get("safety_cash_ratio", 0.9)
            max_safe_budget = remain_money * safety_ratio
            
            if dynamic_budget > max_safe_budget:
                logger.warning(f"💰 현금 잔고 기반 예산 제한: ${dynamic_budget:,.0f} → ${max_safe_budget:,.0f}")
                dynamic_budget = max_safe_budget
            
            # 🔥 추가 안전장치: 독립 성과 기반 제한 (performance_tracker 존재시만)
            if strategy == "proportional" and hasattr(self, 'performance_tracker') and self.performance_tracker:
                perf_data = self.performance_tracker.calculate_bot_specific_performance()
                if perf_data:
                    max_safe_independent = perf_data['total_current_asset'] * 0.95
                    if dynamic_budget > max_safe_independent:
                        logger.warning(f"🎯 독립 자산 기반 예산 제한: ${dynamic_budget:,.0f} → ${max_safe_independent:,.0f}")
                        dynamic_budget = max_safe_independent
            
            # 🔥 로깅 (기존 로직 확장)
            logger.info(f"📊 미국주식 동적 예산 계산 결과:")
            logger.info(f"  전략: {strategy}")
            logger.info(f"  기준 자산: ${config.initial_total_asset:,.0f}")
            logger.info(f"  현재 자산: ${current_total:,.0f}")
            logger.info(f"  현금 잔고: ${remain_money:,.0f}")
            
            if strategy == "proportional":
                if hasattr(self, 'performance_tracker') and self.performance_tracker:
                    perf_data = self.performance_tracker.calculate_bot_specific_performance()
                    if perf_data:
                        logger.info(f"  독립 성과: {perf_data['actual_performance']*100:+.2f}%")
                        logger.info(f"  독립 자산: ${perf_data['total_current_asset']:,.0f}")
                logger.info(f"  예산 배수: {multiplier:.2f}x")
            
            logger.info(f"  최종 예산: ${dynamic_budget:,.0f}")
            
            return dynamic_budget
            
        except Exception as e:
            logger.error(f"미국주식 동적 예산 계산 중 오류: {str(e)}")
            return config.absolute_budget

    def update_budget(self):
        """예산 업데이트 - 미국주식 절대 예산 기반"""
        if config.use_absolute_budget:
            self.total_money = self.calculate_dynamic_budget()
            logger.info(f"💰 미국주식 절대 예산 기반 운영: ${self.total_money:,.0f}")
        else:
            # 기존 방식 (호환성 유지)
            balance = SafeKisUS.safe_get_balance("USD")
            self.total_money = float(balance.get('TotalMoney', 0)) * 0.08  # 8%
            logger.info(f"💰 비율 기반 운영 (8%): ${self.total_money:,.0f}")

    def load_split_data(self):
        """저장된 매매 데이터 로드"""
        try:
            bot_file_path = f"/var/autobot/kisUS/UsStock_{BOT_NAME}.json"
            with open(bot_file_path, 'r') as json_file:
                return json.load(json_file)
        except Exception:
            return []
        
    def save_split_data(self):
        """매매 데이터 저장 - 안전성 강화 버전"""
        try:
            bot_file_path = f"/var/autobot/kisUS/UsStock_{BOT_NAME}.json"
            
            # 🔥 1. 백업 파일 생성 (기존 파일이 있으면)
            backup_path = f"{bot_file_path}.backup"
            if os.path.exists(bot_file_path):
                try:
                    import shutil
                    shutil.copy2(bot_file_path, backup_path)
                    logger.debug(f"📁 백업 파일 생성: {backup_path}")
                except Exception as backup_e:
                    logger.warning(f"백업 파일 생성 실패: {str(backup_e)}")
                    # 백업 실패해도 계속 진행
            
            # 🔥 2. 임시 파일에 먼저 저장
            temp_path = f"{bot_file_path}.temp"
            with open(temp_path, 'w', encoding='utf-8') as temp_file:
                json.dump(self.split_data_list, temp_file, ensure_ascii=False, indent=2)
            
            # 🔥 3. JSON 유효성 검증
            with open(temp_path, 'r', encoding='utf-8') as verify_file:
                test_data = json.load(verify_file)
                if not isinstance(test_data, list):
                    raise ValueError("저장된 데이터가 올바른 형식이 아닙니다")
            
            # 🔥 4. 원자적 교체 (rename은 원자적 연산)
            if os.name == 'nt':  # Windows
                if os.path.exists(bot_file_path):
                    os.remove(bot_file_path)
            os.rename(temp_path, bot_file_path)
            
            # 🔥 5. 최종 검증
            with open(bot_file_path, 'r', encoding='utf-8') as final_verify:
                json.load(final_verify)
            
            logger.debug("✅ 데이터 저장 완료 (안전모드)")
            
            # 🔥 6. 성공 시 오래된 백업 정리
            try:
                if os.path.exists(backup_path):
                    file_age = time.time() - os.path.getmtime(backup_path)
                    if file_age > 3600:  # 1시간 이상된 백업 삭제
                        os.remove(backup_path)
            except:
                pass  # 정리 실패해도 무시
            
        except Exception as e:
            logger.error(f"❌ 데이터 저장 중 오류: {str(e)}")
            
            # 🔥 7. 복구 시도
            try:
                # 임시 파일 정리
                temp_path = f"{bot_file_path}.temp"
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                # 백업으로 복구 시도
                backup_path = f"{bot_file_path}.backup"
                if os.path.exists(backup_path):
                    import shutil
                    shutil.copy2(backup_path, bot_file_path)
                    logger.info("📁 백업 파일로 복구 완료")
                
            except Exception as recovery_e:
                logger.error(f"복구 시도 중 오류: {str(recovery_e)}")
            
            # 🔥 8. 오류 재발생으로 상위에서 롤백 처리하도록
            raise e
        
    def verify_after_trade(self, stock_code, trade_type, expected_change=None):
        """매매 후 데이터 검증 - 브로커와 내부 데이터 일치 확인"""
        try:
            # API 반영 대기
            time.sleep(2)
            
            stock_name = config.target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥 1. 브로커 실제 보유량 조회
            holdings = self.get_current_holdings(stock_code)
            broker_amount = holdings.get('amount', 0)
            broker_avg_price = holdings.get('avg_price', 0)
            
            # 🔥 2. 내부 데이터 보유량 계산
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                logger.error(f"❌ {stock_code} 내부 데이터를 찾을 수 없습니다")
                return False
            
            # 내부 관리 수량 및 활성 포지션 계산
            internal_amount = 0
            active_positions = []
            total_investment = 0
            
            for magic_data in stock_data_info['MagicDataList']:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    internal_amount += magic_data['CurrentAmt']
                    active_positions.append({
                        'position': magic_data['Number'],
                        'amount': magic_data['CurrentAmt'],
                        'price': magic_data['EntryPrice']
                    })
                    total_investment += magic_data['EntryPrice'] * magic_data['CurrentAmt']
            
            # 내부 평균가 계산
            internal_avg_price = total_investment / internal_amount if internal_amount > 0 else 0
            
            # 🔥 3. 수량 일치 확인
            quantity_match = (broker_amount == internal_amount)
            
            # 🔥 4. 평균가 일치 확인 (5% 오차 허용)
            price_match = True
            if broker_amount > 0 and internal_amount > 0:
                if broker_avg_price > 0 and internal_avg_price > 0:
                    price_diff_pct = abs(broker_avg_price - internal_avg_price) / broker_avg_price * 100
                    price_match = price_diff_pct <= 5.0  # 5% 오차 허용
            
            # 🔥 5. 결과 로깅
            if quantity_match and price_match:
                logger.info(f"✅ {stock_name} {trade_type} 후 데이터 일치 확인")
                logger.info(f"   수량: {broker_amount}주 (브로커 = 내부)")
                if broker_amount > 0:
                    logger.info(f"   평균가: 브로커 ${broker_avg_price:.2f} vs 내부 ${internal_avg_price:.2f}")
                    if len(active_positions) > 1:
                        logger.info(f"   활성 포지션: {len(active_positions)}개")
                return True
                
            else:
                # 불일치 상세 로깅
                logger.warning(f"⚠️ {stock_name} {trade_type} 후 데이터 불일치 감지!")
                logger.warning(f"   수량 일치: {'✅' if quantity_match else '❌'} (브로커: {broker_amount}, 내부: {internal_amount})")
                
                if broker_amount > 0 and internal_amount > 0:
                    price_diff_pct = abs(broker_avg_price - internal_avg_price) / broker_avg_price * 100 if broker_avg_price > 0 else 0
                    logger.warning(f"   평균가 일치: {'✅' if price_match else '❌'} (차이: {price_diff_pct:.1f}%)")
                    logger.warning(f"     브로커 평균가: ${broker_avg_price:.2f}")
                    logger.warning(f"     내부 평균가: ${internal_avg_price:.2f}")
                
                # 활성 포지션 상세 정보
                if active_positions:
                    logger.warning(f"   내부 활성 포지션:")
                    for pos in active_positions:
                        logger.warning(f"     {pos['position']}차: {pos['amount']}주 @ ${pos['price']:.2f}")
                
                # 🔥 6. 불일치 시 추가 정보 수집
                if expected_change:
                    logger.info(f"   예상 변화량: {expected_change}")
                
                return False
        
        except Exception as e:
            logger.error(f"❌ {stock_code} {trade_type} 후 검증 중 오류: {str(e)}")
            return False

    def quick_data_sync_check(self):
        """빠른 전체 데이터 동기화 체크"""
        try:
            logger.info("🔍 빠른 동기화 체크 시작")
            
            mismatch_count = 0
            target_stocks = config.target_stocks
            
            for stock_code in target_stocks.keys():
                holdings = self.get_current_holdings(stock_code)
                broker_amount = holdings.get('amount', 0)
                
                # 내부 데이터 조회
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if not stock_data_info:
                    continue
                
                internal_amount = sum([
                    magic_data['CurrentAmt'] for magic_data in stock_data_info['MagicDataList']
                    if magic_data['IsBuy']
                ])
                
                # 불일치 감지
                if broker_amount != internal_amount:
                    mismatch_count += 1
                    stock_name = target_stocks[stock_code].get('name', stock_code)
                    logger.warning(f"🚨 {stock_name}: 브로커 {broker_amount}주 vs 내부 {internal_amount}주")
            
            if mismatch_count == 0:
                logger.info("✅ 모든 종목 데이터 일치")
                return True
            else:
                logger.warning(f"⚠️ {mismatch_count}개 종목 데이터 불일치")
                return False
                
        except Exception as e:
            logger.error(f"빠른 동기화 체크 중 오류: {str(e)}")
            return False

    def calculate_trading_fee(self, price, quantity, is_buy=True):
        """거래 수수료 및 세금 계산 - 미국주식 실제 수수료 반영"""
        trade_amount = price * quantity
        
        # 🔥 실제 수수료 적용 (0.25%)
        commission_rate = config.config.get("commission_rate", 0.0025)
        commission = trade_amount * commission_rate
        
        tax = 0.0        # 미국주식 양도소득세 없음
        special_tax = 0.0  # 특별세 없음
        
        return commission + tax + special_tax    

    def detect_market_timing(self):
        """미국 시장 추세와 타이밍을 감지하는 함수 - 안전한 API 호출"""
        try:
            # 🔥 S&P 500 ETF (SPY) 데이터로 미국 시장 상황 판단 (안전한 호출)
            spy_df = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 90)
            if spy_df is None or len(spy_df) < 20:
                logger.warning("SPY 데이터 조회 실패, 중립 상태로 설정")
                return "neutral"
                
            # 이동평균선 계산
            spy_ma5 = spy_df['close'].rolling(window=5).mean().iloc[-1]
            spy_ma20 = spy_df['close'].rolling(window=20).mean().iloc[-1]
            spy_ma60 = spy_df['close'].rolling(window=60).mean().iloc[-1]
            
            current_index = spy_df['close'].iloc[-1]
            
            # 시장 상태 판단
            if current_index > spy_ma5 > spy_ma20 > spy_ma60:
                return "strong_uptrend"  # 강한 상승 추세
            elif current_index > spy_ma5 and spy_ma5 > spy_ma20:
                return "uptrend"         # 상승 추세
            elif current_index < spy_ma5 and spy_ma5 < spy_ma20:
                return "downtrend"       # 하락 추세
            elif current_index < spy_ma5 < spy_ma20 < spy_ma60:
                return "strong_downtrend"  # 강한 하락 추세
            else:
                return "neutral"         # 중립
        except Exception as e:
            logger.error(f"미국 마켓 타이밍 감지 중 오류: {str(e)}")
            return "neutral"

    def determine_optimal_period(self, stock_code):
        """종목의 특성과 시장 환경에 따라 최적의 분석 기간을 결정하는 함수"""
        try:
            target_stocks = config.target_stocks
            
            # 기본값 설정
            default_period = 60
            default_recent = 30
            default_weight = 0.6
            
            # 종목별 특성 확인
            if stock_code in target_stocks and "period" in target_stocks[stock_code]:
                # 미리 설정된 값이 있으면 사용
                stock_config = target_stocks[stock_code]
                return (
                    stock_config.get("period", default_period),
                    stock_config.get("recent_period", default_recent),
                    stock_config.get("recent_weight", default_weight)
                )
            
            # 🔥 미국주식 데이터로 종목 특성 분석
            df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", 90)
            if df is None or len(df) < 45:
                return default_period, default_recent, default_weight
                    
            # 미국 시장 환경 판단
            spy_df = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 60)
            if spy_df is not None and len(spy_df) >= 20:
                current_index = spy_df['close'].iloc[-1]
                ma20 = spy_df['close'].rolling(window=20).mean().iloc[-1]
                spy_20d_return = ((current_index - spy_df['close'].iloc[-20]) / spy_df['close'].iloc[-20]) * 100
                
                is_bullish_market = current_index > ma20 and spy_20d_return > 3
                is_bearish_market = current_index < ma20 and spy_20d_return < -3
                
                if is_bullish_market:
                    rapid_rise_threshold = 25  # 미국주식 특성 반영
                    rapid_rise_period = 20
                elif is_bearish_market:
                    rapid_rise_threshold = 40
                    rapid_rise_period = 40
                else:
                    rapid_rise_threshold = 30
                    rapid_rise_period = 30
            else:
                rapid_rise_threshold = 30
                rapid_rise_period = 30
                
            # 최근 상승률 계산
            if len(df) > rapid_rise_period:
                recent_return = ((df['close'].iloc[-1] - df['close'].iloc[-rapid_rise_period]) / df['close'].iloc[-rapid_rise_period]) * 100
            else:
                recent_return = 0
                
            # 급등주 판단
            is_rapid_rise = recent_return > rapid_rise_threshold
            
            # 변동성 분석
            volatility_90d = df['close'].pct_change().std() * 100
            
            # 급등주는 45-60일, 가중치 높게
            if is_rapid_rise:
                logger.info(f"{stock_code} 급등주 특성 발견: 최근 {rapid_rise_period}일 수익률 {recent_return:.2f}% (기준 {rapid_rise_threshold}%)")
                period = min(60, max(45, int(volatility_90d * 2)))
                recent_period = min(30, max(20, int(period / 2)))
                weight = 0.7
            else:
                # 일반 변동성 주식
                if volatility_90d > 4.0:  # 미국주식 높은 변동성 기준 조정
                    period = 50
                    weight = 0.65
                elif volatility_90d < 2.0:  # 낮은 변동성
                    period = 75
                    weight = 0.55
                else:  # 중간 변동성
                    period = 60
                    weight = 0.6
                    
                recent_period = int(period / 2)
            
            logger.info(f"{stock_code} 최적 기간 분석 결과: 전체기간={period}일, 최근기간={recent_period}일, 가중치={weight}")
            return period, recent_period, weight
            
        except Exception as e:
            logger.error(f"최적 기간 결정 중 오류: {str(e)}")
            return default_period, default_recent, default_weight

    def calculate_dynamic_profit_target(self, stock_code, indicators):
        """동적으로 목표 수익률을 계산하는 함수 - 뉴스-주가 괴리 고려 추가"""
        try:
            target_stocks = config.target_stocks
            base_target = target_stocks[stock_code].get('base_profit_target', 8)
            
            # 기존 시장 상황 조정
            market_timing = self.detect_market_timing()
            market_factor = 1.0
            
            if market_timing in ["strong_uptrend", "uptrend"]:
                market_factor = 0.8  # 20% 낮춤 (빠른 회전)
            elif market_timing in ["downtrend", "strong_downtrend"]:
                market_factor = 1.3  # 30% 높임 (신중한 매도)
            
            # 변동성 기반 추가 조정 (기존 로직)
            try:
                spy_df = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 20)
                if spy_df is not None and len(spy_df) >= 10:
                    spy_volatility = spy_df['close'].pct_change().std() * 100
                    
                    if spy_volatility > 3.0:
                        volatility_factor = 1.2
                    elif spy_volatility < 1.5:
                        volatility_factor = 0.9
                    else:
                        volatility_factor = 1.0
                else:
                    volatility_factor = 1.0
            except:
                volatility_factor = 1.0
            
            # 최종 목표 수익률 계산
            dynamic_target = base_target * market_factor * volatility_factor
            
            # 범위 제한 (5-25% 사이)
            dynamic_target = max(5, min(25, dynamic_target))
            
            logger.info(f"{stock_code} 동적 목표수익률: {dynamic_target:.1f}% (기본:{base_target}%, 시장:{market_factor:.2f}, 변동성:{volatility_factor:.2f})")
            
            return dynamic_target
            
        except Exception as e:
            logger.error(f"동적 목표 수익률 계산 중 오류: {str(e)}")
            return 8
        
    def get_partial_sell_config(self, stock_code):
        """종목별 부분매도 설정 가져오기"""
        try:
            target_stocks = config.target_stocks
            stock_config = target_stocks.get(stock_code, {})
            partial_config = stock_config.get('partial_sell_config', {})
            
            # 기본값 설정 (부분매도 비활성화)
            if not partial_config.get('enable', False):
                return None
                
            return {
                'first_sell_threshold': partial_config.get('first_sell_threshold', 15),
                'first_sell_ratio': partial_config.get('first_sell_ratio', 0.3),
                'second_sell_threshold': partial_config.get('second_sell_threshold', 25),
                'second_sell_ratio': partial_config.get('second_sell_ratio', 0.4),
                'final_sell_threshold': partial_config.get('final_sell_threshold', 35),
                'trailing_after_partial': partial_config.get('trailing_after_partial', 0.05)
            }
            
        except Exception as e:
            logger.error(f"부분매도 설정 가져오기 오류: {str(e)}")
            return None

    def calculate_market_adjusted_sell_thresholds(self, stock_code, base_config):
        """시장 상황에 따른 매도 기준 동적 조정"""
        try:
            if not base_config:
                return None
                
            market_timing = self.detect_market_timing()
            adjusted_config = base_config.copy()
            
            # 🔥 시장 상황별 조정
            if market_timing == "strong_uptrend":
                # 강한 상승장: 매도 기준 상향 (20% 인상)
                multiplier = 1.2
                trailing_multiplier = 1.5  # 트레일링도 여유있게
                market_desc = "강한상승장"
                
            elif market_timing == "uptrend":
                # 상승장: 매도 기준 소폭 상향 (10% 인상)
                multiplier = 1.1
                trailing_multiplier = 1.2
                market_desc = "상승장"
                
            elif market_timing in ["downtrend", "strong_downtrend"]:
                # 하락장: 매도 기준 하향 (빠른 수익 확정)
                multiplier = 0.8
                trailing_multiplier = 0.7  # 빠른 확정
                market_desc = "하락장"
                
            else:
                # 중립: 기본값 유지
                multiplier = 1.0
                trailing_multiplier = 1.0
                market_desc = "중립"
            
            # 조정 적용
            adjusted_config['first_sell_threshold'] *= multiplier
            adjusted_config['second_sell_threshold'] *= multiplier
            adjusted_config['final_sell_threshold'] *= multiplier
            adjusted_config['trailing_after_partial'] *= trailing_multiplier
            
            logger.info(f"📊 {stock_code} 시장조정 매도기준: {market_desc} (×{multiplier:.1f})")
            
            return adjusted_config
            
        except Exception as e:
            logger.error(f"시장 조정 매도 기준 계산 오류: {str(e)}")
            return base_config

    def _add_to_global_sell_history_immediately(self, stock_code, sell_record, position_num, record_type='full_sell'):
            """매도 완료 즉시 GlobalSellHistory에 백업"""
            try:
                # 종목 데이터 찾기
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if not stock_data_info:
                    logger.error(f"❌ {stock_code} 종목 데이터를 찾을 수 없음")
                    return
                
                # GlobalSellHistory 구조 초기화
                if 'GlobalSellHistory' not in stock_data_info:
                    stock_data_info['GlobalSellHistory'] = []
                
                # 글로벌 매도 기록 생성
                global_sell_record = sell_record.copy()
                global_sell_record['position_num'] = position_num
                global_sell_record['preserved_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if record_type == 'partial_sell':
                    global_sell_record['record_type'] = 'partial_sell'
                
                # GlobalSellHistory에 추가 (최신 순으로 정렬하기 위해 맨 앞에 삽입)
                # stock_data_info['GlobalSellHistory'].insert(0, global_sell_record)
                # 🔥 중복 체크 후 GlobalSellHistory에 추가

                # 🔥 중복 체크 후 GlobalSellHistory에 추가
                existing_record = None
                for existing in stock_data_info['GlobalSellHistory']:
                    same_date = existing.get('date', '') == global_sell_record.get('date', '')
                    same_position = existing.get('position_num', 0) == global_sell_record.get('position_num', 0)
                    same_price = abs(existing.get('sell_price', 0) - global_sell_record.get('sell_price', 0)) < 0.01
                    same_amount = existing.get('sell_amount', 0) == global_sell_record.get('sell_amount', 0)
                    
                    if same_date and same_position and same_price and same_amount:
                        existing_record = existing
                        break

                if existing_record:
                    # 중복 발견: 아무것도 하지 않음 (이미 기록됨)
                    logger.info(f"🔄 {stock_code} GlobalSellHistory 중복 기록 스킵 - 이미 존재함")
                else:
                    # 신규 기록: 추가
                    stock_data_info['GlobalSellHistory'].insert(0, global_sell_record)
                    logger.info(f"📋 {stock_code} {position_num}차 매도 기록을 GlobalSellHistory에 신규 추가 완료")

                logger.info(f"📋 {stock_code} {position_num}차 매도 기록을 GlobalSellHistory에 즉시 백업 완료")
                
            except Exception as e:
                logger.error(f"GlobalSellHistory 즉시 백업 중 오류: {str(e)}")

    def execute_partial_sell(self, stock_code, magic_data, sell_amount, current_price, sell_reason):
        """부분매도 실행 - GlobalSellHistory 즉시 백업 개선 (SafeKisUS 통일)"""
        try:
            position_num = magic_data['Number']
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data['CurrentAmt']
            
            if sell_amount <= 0 or sell_amount > current_amount:
                return False, "잘못된 매도 수량"
            
            # 🔥 1단계: 매도 주문 실행 (SafeKisUS 방식으로 통일)
            try:
                # 시장가 대신 현재가 기준 지정가 매도 (1% 아래)
                sell_price = round(current_price * 0.99, 2)
                order_result = SafeKisUS.safe_make_sell_limit_order(stock_code, sell_amount, sell_price)
                
                if not order_result:
                    logger.error(f"❌ {stock_code} {position_num}차 부분매도 주문 실패: API 호출 실패")
                    return False, "주문 실패: API 호출 실패"
                
                # KIS API 응답 구조에 맞춰 성공 여부 확인
                if isinstance(order_result, dict):
                    # 주문 성공 시 OrderNum 또는 OrderNum2가 있음
                    order_num = order_result.get('OrderNum') or order_result.get('OrderNum2')
                    if order_num:
                        logger.info(f"✅ {stock_code} {position_num}차 부분매도 주문 성공: {sell_amount}주 × ${sell_price:.2f} (주문번호: {order_num})")
                    else:
                        logger.error(f"❌ {stock_code} {position_num}차 부분매도 주문 실패: 주문번호 없음")
                        return False, "주문 실패: 주문번호 없음"
                else:
                    logger.error(f"❌ {stock_code} {position_num}차 부분매도 주문 실패: 예상치 못한 응답 형식")
                    return False, "주문 실패: 예상치 못한 응답 형식"
                    
            except Exception as order_e:
                logger.error(f"❌ {stock_code} {position_num}차 부분매도 주문 처리 실패: {str(order_e)}")
                return False, f"주문 실패: {str(order_e)}"
            
            # 🔥 2단계: 수익률 계산
            position_return_pct = (current_price - entry_price) / entry_price * 100
            sell_ratio = sell_amount / magic_data.get('OriginalAmt', current_amount)
            is_full_sell = (current_amount - sell_amount <= 0)
            
            # 🔥 3단계: 데이터 백업
            backup_data = {
                'CurrentAmt': magic_data['CurrentAmt'],
                'PartialSellStage': magic_data.get('PartialSellStage', 0),
                'RemainingRatio': magic_data.get('RemainingRatio', 1.0),
                'PartialSellHistory': magic_data.get('PartialSellHistory', []).copy()
            }
            
            try:
                # 🔥 4단계: 부분매도 기록 생성
                partial_sell_record = {
                    'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'position_num': position_num,
                    'sell_amount': sell_amount,
                    'sell_price': sell_price,  # 실제 주문 가격 기록
                    'current_price': current_price,
                    'entry_price': entry_price,
                    'position_return_pct': round(position_return_pct, 2),
                    'sell_ratio': round(sell_ratio, 3),
                    'remaining_amount': current_amount - sell_amount,
                    'reason': sell_reason,
                    'order_num': order_num if 'order_num' in locals() else None
                }
                
                # 🔥 5단계: MagicData 업데이트
                magic_data['CurrentAmt'] -= sell_amount
                magic_data['PartialSellStage'] = magic_data.get('PartialSellStage', 0) + 1
                
                if not is_full_sell:
                    # 부분매도인 경우
                    magic_data['RemainingRatio'] = magic_data['CurrentAmt'] / magic_data.get('OriginalAmt', current_amount + sell_amount)
                    
                    # 부분매도 기록 추가
                    if 'PartialSellHistory' not in magic_data:
                        magic_data['PartialSellHistory'] = []
                    magic_data['PartialSellHistory'].append(partial_sell_record)
                    
                else:
                    # 전량매도인 경우
                    magic_data['IsBuy'] = False
                    magic_data['RemainingRatio'] = 0.0
                    
                    # 매도 이력에 추가
                    if 'SellHistory' not in magic_data:
                        magic_data['SellHistory'] = []
                    
                    sell_record = partial_sell_record.copy()
                    sell_record['sell_type'] = 'partial_to_full'
                    magic_data['SellHistory'].append(sell_record)
                
                # 🔥 6단계: GlobalSellHistory 즉시 백업
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if stock_data_info:
                    if 'GlobalSellHistory' not in stock_data_info:
                        stock_data_info['GlobalSellHistory'] = []
                    
                    # 글로벌 매도 기록 생성
                    global_sell_record = partial_sell_record.copy()
                    global_sell_record['record_type'] = 'partial_sell' if not is_full_sell else 'partial_to_full'
                    global_sell_record['preserved_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # GlobalSellHistory에 추가 (최신 순으로 정렬하기 위해 맨 앞에 삽입)
                    # stock_data_info['GlobalSellHistory'].insert(0, global_sell_record)
                    # 🔥 중복 체크 후 GlobalSellHistory에 추가
                    existing_record = None
                    for existing in stock_data_info['GlobalSellHistory']:
                        same_date = existing.get('date', '') == global_sell_record.get('date', '')
                        same_position = existing.get('position_num', 0) == global_sell_record.get('position_num', 0)
                        same_price = abs(existing.get('sell_price', 0) - global_sell_record.get('sell_price', 0)) < 0.01
                        same_amount = existing.get('sell_amount', 0) == global_sell_record.get('sell_amount', 0)
                        
                        if same_date and same_position and same_price and same_amount:
                            existing_record = existing
                            break

                    if existing_record:
                        # 중복 발견: 아무것도 하지 않음 (이미 기록됨)
                        logger.info(f"🔄 {stock_code} GlobalSellHistory 중복 기록 스킵 - 이미 존재함")
                    else:
                        # 신규 기록: 추가
                        stock_data_info['GlobalSellHistory'].insert(0, global_sell_record)
                        logger.info(f"📋 {stock_code} {position_num}차 매도 기록을 GlobalSellHistory에 신규 추가 완료")

                # 🔥 7단계: 데이터 저장
                self.save_split_data()
                
                # 🔥 8단계: Discord 알림
                if config.config.get("use_discord_alert", True):
                    sell_type_text = "부분매도" if not is_full_sell else "전량매도"
                    profit_text = f"+{position_return_pct:.1f}%" if position_return_pct > 0 else f"{position_return_pct:.1f}%"
                    
                    discord_msg = f"📉 **{sell_type_text} 완료**\n"
                    discord_msg += f"종목: {stock_code}\n"
                    discord_msg += f"차수: {position_num}차\n"
                    discord_msg += f"수량: {sell_amount}주\n"
                    discord_msg += f"가격: ${sell_price:.2f}\n"
                    discord_msg += f"수익률: {profit_text}\n"
                    discord_msg += f"사유: {sell_reason}"
                    
                    if not is_full_sell:
                        discord_msg += f"\n잔여: {magic_data['CurrentAmt']}주"
                    
                    discord_alert.SendMessage(discord_msg)
                
                success_msg = f"✅ {stock_code} {position_num}차 {sell_type_text if 'sell_type_text' in locals() else '매도'} 성공"
                logger.info(success_msg)
                return True, success_msg
                
            except Exception as update_e:
                # 데이터 복구
                magic_data.update(backup_data)
                logger.error(f"데이터 업데이트 중 오류 발생, 백업 데이터로 복구: {str(update_e)}")
                return False, f"데이터 업데이트 실패: {str(update_e)}"
                
        except Exception as e:
            logger.error(f"부분매도 실행 중 전체 오류: {str(e)}")
            return False, f"부분매도 실행 실패: {str(e)}"

    def should_execute_partial_sell(self, stock_code, magic_data, current_price, adjusted_config):
        """부분매도 실행 여부 판단"""
        try:
            if not adjusted_config:
                return False, None, "부분매도 비활성화"
                
            position_num = magic_data['Number']
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data['CurrentAmt']
            
            if current_amount <= 0:
                return False, None, "보유량 없음"
            
            # 현재 수익률 계산
            position_return_pct = (current_price - entry_price) / entry_price * 100
            current_stage = magic_data.get('PartialSellStage', 0)

            # 🔥🔥🔥 신규 추가: 예산 기반 기회비용 방지 체크 🔥🔥🔥
            budget_opportunity_reason = self.check_budget_driven_opportunity_cost(
                stock_code, magic_data, position_return_pct, current_price
            )
            
            if budget_opportunity_reason:
                # 예산 압박 상황에서 적극적 수익보존
                if position_return_pct >= 2.0:  # 최소 2% 수익
                    logger.warning(f"🚨 {stock_code} {position_num}차 예산압박 수익보존:")
                    logger.warning(f"   {budget_opportunity_reason}")
                    logger.warning(f"   💰 즉시 전량매도로 현금확보 ({position_return_pct:.1f}% 수익)")
                    
                    sell_amount = current_amount  # 해당 차수 전량
                    return True, sell_amount, f"예산압박 수익보존: {budget_opportunity_reason}"
            # 🔥🔥🔥 예산 기반 기회비용 방지 체크 끝 🔥🔥🔥

            # 🔥 단계별 부분매도 판단
            sell_amount = 0
            sell_reason = ""
            
            if current_stage == 0:  # 첫 번째 부분매도
                if position_return_pct >= adjusted_config['first_sell_threshold']:
                    original_amt = magic_data.get('OriginalAmt', current_amount)
                    sell_amount = int(original_amt * adjusted_config['first_sell_ratio'])
                    sell_reason = f"{position_num}차 1단계 부분매도 ({adjusted_config['first_sell_threshold']:.1f}% 달성)"
                    
            elif current_stage == 1:  # 두 번째 부분매도
                if position_return_pct >= adjusted_config['second_sell_threshold']:
                    original_amt = magic_data.get('OriginalAmt', current_amount)
                    sell_amount = int(original_amt * adjusted_config['second_sell_ratio'])
                    sell_reason = f"{position_num}차 2단계 부분매도 ({adjusted_config['second_sell_threshold']:.1f}% 달성)"
                    
            elif current_stage == 2:  # 최종 전량매도
                if position_return_pct >= adjusted_config['final_sell_threshold']:
                    sell_amount = current_amount  # 전량
                    sell_reason = f"{position_num}차 최종 전량매도 ({adjusted_config['final_sell_threshold']:.1f}% 달성)"
            
            # 🔥 부분매도 후 트레일링 스톱 체크
            if current_stage > 0 and sell_amount == 0:
                max_profit_key = f'max_profit_{position_num}'
                current_max = magic_data.get(max_profit_key, 0)
                
                # 최고점 업데이트
                if position_return_pct > current_max:
                    magic_data[max_profit_key] = position_return_pct
                    current_max = position_return_pct

                # 🔥🔥🔥 새로 추가: 부분매도 후에도 손실 상태에서는 트레일링 금지 🔥🔥🔥
                if position_return_pct < 0:
                    logger.info(f"🚫 {stock_code} {position_num}차 부분매도후 손실상태 트레일링 금지: "
                            f"현재 손실 ({position_return_pct:+.1f}%)")
                    # 트레일링 실행하지 않고 계속 진행 (홀딩)
                else:
                    
                    # 트레일링 스톱 체크
                    trailing_threshold = current_max - (adjusted_config['trailing_after_partial'] * 100)
                    
                    if position_return_pct <= trailing_threshold and current_max > adjusted_config['first_sell_threshold']:
                        sell_amount = current_amount  # 잔여 전량
                        sell_reason = f"{position_num}차 부분매도후 트레일링스톱 (최고{current_max:.1f}%→{adjusted_config['trailing_after_partial']*100:.0f}%하락)"
                
            # 매도량 검증 및 조정
            if sell_amount > 0:
                sell_amount = min(sell_amount, current_amount)
                if sell_amount <= 0:
                    return False, None, "매도량 계산 오류"
                    
                return True, sell_amount, sell_reason
            
            return False, None, f"매도 조건 미충족 (현재: {position_return_pct:.1f}%, 단계: {current_stage})"
            
        except Exception as e:
            logger.error(f"부분매도 판단 중 오류: {str(e)}")
            return False, None, str(e)

    def get_technical_indicators_weighted(self, stock_code, period=60, recent_period=30, recent_weight=0.7):
        """미국주식용 가중치를 적용한 기술적 지표 계산 함수"""
        try:
            # 🔥 미국주식 전체 기간 데이터 가져오기
            df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", period)
            if df is None or len(df) < period // 2:
                logger.warning(f"{stock_code} 미국주식 데이터 조회 실패")
                return None
            
            # 설정값 가져오기
            ma_short = config.config.get("ma_short", 5)
            ma_mid = config.config.get("ma_mid", 20)
            ma_long = config.config.get("ma_long", 60)
            rsi_period = config.config.get("rsi_period", 14)
            atr_period = config.config.get("atr_period", 14)
            
            # 기본 이동평균선 계산
            ma_short_val = Common.GetMA(df, ma_short, -2)
            ma_short_before = Common.GetMA(df, ma_short, -3)
            ma_mid_val = Common.GetMA(df, ma_mid, -2)
            ma_mid_before = Common.GetMA(df, ma_mid, -3)
            ma_long_val = Common.GetMA(df, ma_long, -2)
            ma_long_before = Common.GetMA(df, ma_long, -3)
            
            # 최근 30일 고가
            max_high_30 = df['high'].iloc[-recent_period:].max()
            
            # 가격 정보
            prev_open = df['open'].iloc[-2]
            prev_close = df['close'].iloc[-2]
            prev_high = df['high'].iloc[-2]
            
            # 전체 기간과 최근 기간의 최대/최소 가격 계산
            full_min_price = df['close'].min()
            full_max_price = df['close'].max()
            
            recent_min_price = df['close'].iloc[-recent_period:].min()
            recent_max_price = df['close'].iloc[-recent_period:].max()
            
            # 가중치 적용한 최대/최소 가격 계산
            min_price = (recent_weight * recent_min_price) + ((1 - recent_weight) * full_min_price)
            max_price = (recent_weight * recent_max_price) + ((1 - recent_weight) * full_max_price)
            
            # RSI 계산
            delta = df['close'].diff()
            gain = delta.copy()
            loss = delta.copy()
            gain[gain < 0] = 0
            loss[loss > 0] = 0
            avg_gain = gain.rolling(window=rsi_period).mean()
            avg_loss = abs(loss.rolling(window=rsi_period).mean())
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-2]
            
            # ATR 계산
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=atr_period).mean().iloc[-2]
            
            # 갭 계산
            gap = max_price - min_price
            step_gap = gap / config.div_num
            percent_gap = round((gap / min_price) * 100, 2)
            
            # 목표 수익률과 트리거 손실률 계산
            target_rate = round(percent_gap / config.div_num, 2)
            trigger_rate = -round((percent_gap / config.div_num), 2)
            
            # 조정폭 계산
            current_price = SafeKisUS.safe_get_current_price(stock_code)
            pullback_from_high = (max_high_30 - current_price) / max_high_30 * 100
            
            # 현재 구간 계산
            now_step = config.div_num
            for step in range(1, int(config.div_num) + 1):
                if prev_close < min_price + (step_gap * step):
                    now_step = step
                    break
            
            # 추세 판단
            is_uptrend = ma_short_val > ma_mid_val and ma_mid_val > ma_long_val and ma_short_val > ma_short_before
            is_downtrend = ma_short_val < ma_mid_val and ma_mid_val < ma_long_val and ma_short_val < ma_short_before
            
            market_trend = 'strong_up' if is_uptrend else 'strong_down' if is_downtrend else 'sideways'
            if ma_short_val > ma_mid_val and ma_short_val > ma_short_before:
                market_trend = 'up'
            elif ma_short_val < ma_mid_val and ma_short_val < ma_short_before:
                market_trend = 'down'
            
            # 급등주 특성 반영
            recent_rise_percent = ((recent_max_price - recent_min_price) / recent_min_price) * 100
            is_rapid_rise = recent_rise_percent > 25  # 미국주식 기준 조정
            
            return {
                'current_price': current_price,
                'prev_open': prev_open,
                'prev_close': prev_close,
                'prev_high': prev_high,
                'ma_short': ma_short_val,
                'ma_short_before': ma_short_before,
                'ma_mid': ma_mid_val,
                'ma_mid_before': ma_mid_before,
                'ma_long': ma_long_val,
                'ma_long_before': ma_long_before,
                'min_price': min_price,
                'max_price': max_price,
                'max_high_30': max_high_30,
                'gap': gap,
                'step_gap': step_gap,
                'percent_gap': percent_gap,
                'target_rate': target_rate,
                'trigger_rate': trigger_rate,
                'now_step': now_step,
                'market_trend': market_trend,
                'rsi': current_rsi,
                'atr': atr,
                'pullback_from_high': pullback_from_high,
                'is_rapid_rise': is_rapid_rise,
                'recent_rise_percent': recent_rise_percent
            }
        except Exception as e:
            logger.error(f"미국주식 가중치 적용 기술적 지표 계산 중 오류: {str(e)}")
            return None

    def get_technical_indicators(self, stock_code):
        """기존 기술적 지표 계산 함수 (호환성 유지)"""
        period, recent_period, recent_weight = self.determine_optimal_period(stock_code)
        return self.get_technical_indicators_weighted(
            stock_code, 
            period=period, 
            recent_period=recent_period, 
            recent_weight=recent_weight
        )

###################### 기회비용 상실방지(매도 시) 및 종목별 예산사용 관리(매수 시) ###############################
    def calculate_budget_usage_ratio(self, stock_code):
        """종목별 예산 사용률 계산 및 액션 필요성 판단"""
        try:
            # 현재 투자 금액 계산
            magic_data_list = self.get_stock_magic_data_list(stock_code)
            total_used = sum([
                m['EntryPrice'] * m['CurrentAmt'] 
                for m in magic_data_list 
                if m['IsBuy'] and m['CurrentAmt'] > 0
            ])
            
            # 할당된 예산 계산 (config에서 가져오기)
            target_stocks = config.target_stocks
            stock_config = target_stocks.get(stock_code, {})
            weight = stock_config.get('weight', 0)
            allocated_budget = config.absolute_budget * weight
            
            if allocated_budget <= 0:
                logger.warning(f"⚠️ {stock_code} 예산 할당 정보 없음")
                return {'requires_action': False, 'usage_ratio': 0}
            
            # 사용률 계산
            usage_ratio = (total_used / allocated_budget) * 100
            
            # 액션 필요성 판단
            if usage_ratio >= 120:  # 20% 초과
                action_level = "critical"
                requires_action = True
            elif usage_ratio >= 110:  # 10% 초과
                action_level = "warning"
                requires_action = True
            elif usage_ratio >= 100:  # 100% 사용
                action_level = "caution"
                requires_action = True
            else:
                action_level = "normal"
                requires_action = False
            
            logger.info(f"📊 {stock_code} 예산 사용률: {usage_ratio:.1f}% "
                    f"(${total_used:,.0f} / ${allocated_budget:,.0f}) - {action_level}")
            
            return {
                'requires_action': requires_action,
                'usage_ratio': usage_ratio,
                'total_used': total_used,
                'allocated_budget': allocated_budget,
                'action_level': action_level
            }
            
        except Exception as e:
            logger.error(f"예산 사용률 계산 오류: {str(e)}")
            return {'requires_action': False, 'usage_ratio': 0}

    def check_position_opportunity_cost(self, stock_code, magic_data, current_return, budget_info):
        """예산 초과 상황에서만 실행되는 안전한 빠른 익절 체크 - 🔥 손익비 고려 개선"""
        try:
            position_num = magic_data['Number']
            max_profit_key = f'max_profit_{position_num}'
            max_profit = magic_data.get(max_profit_key, 0)
            usage_ratio = budget_info['usage_ratio']
            
            # 🔥 예산 사용률에 따른 안전한 차등 조건 (최소 익절 임계값 적용)
            if usage_ratio >= 180:  # 80% 초과 (Ultra Critical)
                # 매우 적극적 안전익절: 6% 이상 수익 + 8% 이상 최고점 + 1.5%p 하락
                min_profit = 6.0
                min_max_profit = 8.0
                required_drop = 1.5
                level = "Ultra Critical"
                
            elif usage_ratio >= 150:  # 50% 초과 (Super Critical)
                # 적극적 안전익절: 6% 이상 수익 + 8% 이상 최고점 + 2.0%p 하락
                min_profit = 6.0
                min_max_profit = 8.0
                required_drop = 2.0
                level = "Super Critical"
                
            elif usage_ratio >= 120:  # 20% 초과 (Critical)
                # 안전익절: 5% 이상 수익 + 7% 이상 최고점 + 2.5%p 하락
                min_profit = 5.0
                min_max_profit = 7.0
                required_drop = 2.5
                level = "Critical"
                
            elif usage_ratio >= 110:  # 10% 초과 (Warning)
                # 보수적 안전익절: 5% 이상 수익 + 8% 이상 최고점 + 3.0%p 하락
                min_profit = 5.0
                min_max_profit = 8.0
                required_drop = 3.0
                level = "Warning"
                
            elif usage_ratio >= 100:  # 100% 사용 (Caution)
                # 매우 보수적: 4% 이상 수익 + 9% 이상 최고점 + 4.0%p 하락
                min_profit = 4.0
                min_max_profit = 9.0
                required_drop = 4.0
                level = "Caution"
            else:
                return None  # 예산 정상 → 예외로직 실행 안함
            
            # 🔥 안전한 익절 조건 체크
            profit_drop = max_profit - current_return
            
            # 조건 검증
            conditions_met = (
                current_return >= min_profit and           # 최소 익절 수익률
                max_profit >= min_max_profit and           # 충분한 최고점 경험
                profit_drop >= required_drop               # 필요한 하락폭
            )
            
            if conditions_met:
                # 🔥 추가 안전장치: 손실 전환 방지
                if current_return <= 1.0:  # 1% 이하는 위험 구간
                    logger.warning(f"⚠️ {stock_code} {position_num}차 예산압박이지만 수익률 {current_return:.1f}% 너무 낮음 - 익절 보류")
                    return None
                
                return (f"{level} 예산초과 {position_num}차 안전익절 "
                    f"(수익{current_return:.1f}% ≥ {min_profit}%, "
                    f"최고{max_profit:.1f}% ≥ {min_max_profit}%, "
                    f"하락{profit_drop:.1f}%p ≥ {required_drop}%p)")
            
            else:
                # 🔥 상세 로그: 왜 조건 미충족인지 명시
                missing_conditions = []
                if current_return < min_profit:
                    missing_conditions.append(f"수익률 {current_return:.1f}% < {min_profit}%")
                if max_profit < min_max_profit:
                    missing_conditions.append(f"최고점 {max_profit:.1f}% < {min_max_profit}%")
                if profit_drop < required_drop:
                    missing_conditions.append(f"하락폭 {profit_drop:.1f}%p < {required_drop}%p")
                
                logger.debug(f"📊 {stock_code} {position_num}차 {level} 예산초과 but 안전익절 조건 미충족: {', '.join(missing_conditions)}")
                return None
            
        except Exception as e:
            logger.error(f"안전한 기회비용 조건 체크 오류: {str(e)}")
            return None

    def check_budget_driven_opportunity_cost(self, stock_code, magic_data, current_return, current_price):
        """예산 사용률 기반 안전한 빠른 익절 체크 - 🔥 2단계 검증 + 손익비 고려"""
        try:
            # 🔥 1단계: 예산 사용률 체크 (필수 조건)
            budget_usage_info = self.calculate_budget_usage_ratio(stock_code)
            
            if not budget_usage_info['requires_action']:
                return None  # 예산 사용률 정상 → 예외로직 실행 안함
            
            # 🔥 2단계: 안전한 빠른 익절 조건 체크 (예산 초과시만 실행)
            safe_profit_taking_reason = self.check_position_opportunity_cost(
                stock_code, magic_data, current_return, budget_usage_info
            )
            
            if safe_profit_taking_reason:
                # 🔥 3단계: 최종 안전장치 - 시장 상황 고려
                position_num = magic_data['Number']
                logger.info(f"🎯 {stock_code} {position_num}차 예산압박 안전익절 준비:")
                logger.info(f"   💰 현재 수익률: {current_return:.2f}%")
                logger.info(f"   📊 예산 사용률: {budget_usage_info['usage_ratio']:.1f}%")
                logger.info(f"   🎯 익절 사유: {safe_profit_taking_reason}")
                logger.info(f"   🔄 효과: 현금확보로 신규 매수 기회 창출")
                
                return f"예산사용률 {budget_usage_info['usage_ratio']:.0f}% → {safe_profit_taking_reason}"
            
            return None
            
        except Exception as e:
            logger.error(f"예산 기반 안전 익절 체크 오류: {str(e)}")
            return None

    def check_budget_before_buy(self, stock_code, proposed_buy_amount, current_price):
        """예산 기반 매수 제한 체크 - 🔥 예산 초과 매수 방지"""
        try:
            # 현재 예산 사용률 확인
            budget_usage_info = self.calculate_budget_usage_ratio(stock_code)
            
            if not budget_usage_info:
                return True, "예산 정보 없음"
            
            usage_ratio = budget_usage_info['usage_ratio']
            allocated_budget = budget_usage_info['allocated_budget']
            total_used = budget_usage_info['total_used']
            
            # 추가 매수 후 예상 사용률 계산
            estimated_additional_cost = proposed_buy_amount * current_price
            estimated_total_used = total_used + estimated_additional_cost
            estimated_usage_ratio = (estimated_total_used / allocated_budget) * 100
            
            logger.info(f"📊 {stock_code} 매수 전 예산 체크:")
            logger.info(f"   현재 사용률: {usage_ratio:.1f}%")
            logger.info(f"   매수 후 예상: {estimated_usage_ratio:.1f}%")
            logger.info(f"   추가 비용: ${estimated_additional_cost:,.0f}")
            
            # 매수 제한 기준
            if usage_ratio >= 150:  # 50% 초과시 완전 차단
                return False, f"예산 초과로 매수 금지 (현재 {usage_ratio:.1f}% ≥ 150%)"
            
            elif usage_ratio >= 130:  # 30% 초과시 엄격 제한
                return False, f"예산 심각 초과로 매수 제한 (현재 {usage_ratio:.1f}% ≥ 130%)"
            
            elif usage_ratio >= 110:  # 10% 초과시 조건부 허용
                # 현재 수익 상황 확인
                profitable_positions = self.get_profitable_positions(stock_code, current_price)
                if not profitable_positions:
                    return False, f"예산 초과 + 수익 포지션 없음으로 매수 제한 (현재 {usage_ratio:.1f}%)"
                else:
                    total_profit_amount = sum([p['profit_amount'] for p in profitable_positions])
                    logger.warning(f"⚠️ {stock_code} 예산 초과하지만 수익 포지션 있어 조건부 허용")
                    logger.warning(f"   수익 포지션: {len(profitable_positions)}개, 총 수익: ${total_profit_amount:,.0f}")
                    return True, f"조건부 허용 (수익 포지션 {len(profitable_positions)}개 존재)"
            
            else:  # 110% 미만은 정상 허용
                return True, f"정상 예산 범위 ({usage_ratio:.1f}%)"
            
        except Exception as e:
            logger.error(f"예산 기반 매수 제한 체크 오류: {str(e)}")
            return True, "체크 실패로 허용"

    def get_profitable_positions(self, stock_code, current_price):
        """해당 종목의 수익 포지션 목록 반환"""
        try:
            magic_data_list = self.get_stock_magic_data_list(stock_code)
            
            profitable_positions = []
            for magic_data in magic_data_list:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    position_num = magic_data['Number']
                    entry_price = magic_data['EntryPrice']
                    amount = magic_data['CurrentAmt']
                    current_return = (current_price - entry_price) / entry_price * 100
                    
                    if current_return > 0:
                        profit_amount = (current_price - entry_price) * amount
                        profitable_positions.append({
                            'position_num': position_num,
                            'entry_price': entry_price,
                            'current_price': current_price,
                            'return_pct': current_return,
                            'amount': amount,
                            'profit_amount': profit_amount
                        })
            
            if profitable_positions:
                logger.info(f"📈 {stock_code} 수익 포지션 현황:")
                for pos in profitable_positions:
                    logger.info(f"   {pos['position_num']}차: {pos['return_pct']:+.1f}% "
                            f"(${pos['profit_amount']:+,.0f})")
            
            return profitable_positions
            
        except Exception as e:
            logger.error(f"수익 포지션 확인 오류: {str(e)}")
            return []

###################### 기회비용 상실방지(매도 시) 및 종목별 예산사용 관리(매수 시) 끝 #############################

    def check_small_pullback_buy_opportunity(self, stock_code, indicators):
        """우상향 성장주의 작은 조정 시 추가 매수 기회 확인"""
        try:
            target_stocks = config.target_stocks
            
            # 성장주/테크주 확인
            stock_type = target_stocks.get(stock_code, {}).get('stock_type')
            if stock_type not in ['growth', 'tech']:
                return False
                
            # 우상향 확인
            ma_alignment = (indicators['ma_short'] > indicators['ma_mid'] and 
                        indicators['ma_mid'] > indicators['ma_long'])
                        
            # 작은 조정 확인 (미국주식: 1-4% 하락)
            small_pullback = (1.0 <= indicators['pullback_from_high'] <= 4.0)
            
            # 과매수 확인
            not_overbought = indicators['rsi'] < 75
            
            return ma_alignment and small_pullback and not_overbought
        except Exception as e:
            logger.error(f"작은 조정 매수 기회 확인 중 오류: {str(e)}")
            return False
        
    # 🔧 기존 코드 수정
    def get_current_holdings(self, stock_code):
        """현재 보유 수량 및 상태 조회 - 미국주식용"""
        try:
            # 🔥 미국주식 보유 종목 리스트 조회 (USD 기준)
            my_stocks = SafeKisUS.safe_get_my_stock_list("USD")
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    return {
                        'amount': int(stock['StockAmt']),
                        'avg_price': float(stock['StockAvgPrice']),
                        'revenue_rate': float(stock['StockRevenueRate']),
                        'revenue_money': float(stock['StockRevenueMoney'])
                    }
            return {'amount': 0, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0}
        except Exception as e:
            logger.error(f"❌ {stock_code} 미국주식 보유 수량 조회 중 API 오류: {str(e)}")
            # 🔧 새로 추가: API 오류 표시
            return {'amount': -1, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0, 'api_error': True}        

    def sync_position_after_buy_with_order_list(self, stock_code, position_num, order_price, expected_amount):
        """주문내역 조회 기반 정확한 체결가 동기화 - 차수 혼동 버그 수정 (3차수봇용)"""
        try:
            # 🔥 1. 파라미터 검증 강화 (3차수봇: 1~3차)
            if not isinstance(position_num, int) or position_num < 1 or position_num > 3:
                logger.error(f"❌ {stock_code} 잘못된 차수: {position_num} (1~3만 허용)")
                return False
                
            logger.info(f"🔄 {stock_code} {position_num}차 주문내역 기반 동기화 시작")
            logger.info(f"   대상 차수: {position_num}차 (1-based)")
            logger.info(f"   주문가: ${order_price:.2f}")
            logger.info(f"   예상 수량: {expected_amount}주")
            
            # 🔥 2. 종목 데이터 찾기
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                logger.error(f"❌ {stock_code} 종목 데이터 없음")
                return False
            
            # 🔥 3. 정확한 차수 데이터 식별 및 보호
            target_position_index = position_num - 1  # 0-based 인덱스
            if target_position_index >= len(stock_data_info['MagicDataList']):
                logger.error(f"❌ {stock_code} {position_num}차 데이터 인덱스 초과")
                return False
                
            target_position = stock_data_info['MagicDataList'][target_position_index]
            
            # 🔥 4. 업데이트 전 현재 상태 로깅 (디버깅용)
            logger.info(f"📊 {stock_code} 업데이트 전 상태:")
            for i, magic_data in enumerate(stock_data_info['MagicDataList']):
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    logger.info(f"   {i+1}차: ${magic_data['EntryPrice']:.2f} ({magic_data['CurrentAmt']}주)")
            
            # 🔥 5. 해당 차수가 실제로 매수된 상태인지 검증
            if not target_position.get('IsBuy', False):
                logger.warning(f"⚠️ {stock_code} {position_num}차가 매수 상태가 아님 - 동기화 스킵")
                return False
                
            if target_position.get('CurrentAmt', 0) <= 0:
                logger.warning(f"⚠️ {stock_code} {position_num}차 보유량이 0 - 동기화 스킵")
                return False
            
            # 🔥 6. 주문내역에서 실제 체결가 조회 (SafeKisUS 사용)
            time.sleep(2)  # 브로커 시스템 반영 대기
            
            recent_orders = SafeKisUS.safe_get_order_list(stock_code, "BUY", "CLOSE", 1)
            if not recent_orders:
                logger.warning(f"⚠️ {stock_code} 최근 매수 주문 조회 실패")
                return False
            
            # 🔥 7. 가장 최근 체결 주문 찾기 (오늘 날짜)
            today = datetime.now().strftime("%Y%m%d")
            latest_buy_order = None
            
            for order in recent_orders:
                if (order.get('OrderDate') == today and 
                    order.get('OrderResultAmt', 0) > 0 and  # 체결량 있음
                    order.get('OrderSatus') == 'Close'):     # 체결 완료
                    latest_buy_order = order
                    break
            
            if not latest_buy_order:
                logger.warning(f"⚠️ {stock_code} 오늘 체결된 매수 주문 없음")
                return False
            
            # 🔥 8. 실제 체결가 추출 및 검증
            try:
                actual_execution_price = float(latest_buy_order['OrderAvgPrice'])
                executed_amount = int(latest_buy_order['OrderResultAmt'])
                order_time = latest_buy_order.get('OrderTime', '')
            except (ValueError, KeyError) as e:
                logger.error(f"❌ {stock_code} 주문 데이터 파싱 오류: {str(e)}")
                return False
            
            # 🔥 9. 체결가 합리성 검증
            price_diff_pct = abs(actual_execution_price - order_price) / order_price * 100
            if price_diff_pct > 5.0:  # 5% 이상 차이는 비정상
                logger.warning(f"⚠️ {stock_code} {position_num}차 체결가 차이 과도: {price_diff_pct:.1f}% - 동기화 스킵")
                return False
            
            # 🔥 10. **핵심 수정**: 정확한 차수에만 업데이트
            old_price = target_position['EntryPrice']
            old_amount = target_position['CurrentAmt']
            
            # 🚨 중요: 지정된 차수에만 업데이트, 다른 차수는 절대 건드리지 않음
            target_position['EntryPrice'] = actual_execution_price
            target_position['CurrentAmt'] = executed_amount
            target_position['EntryAmt'] = executed_amount
            
            # 🔥 11. 완료 로깅
            price_improvement = actual_execution_price - order_price
            logger.info(f"✅ {stock_code} {position_num}차 실제 체결가 동기화 완료:")
            logger.info(f"   🎯 업데이트 대상: {position_num}차 (인덱스 {target_position_index})")
            logger.info(f"   주문가: ${order_price:.2f}")
            logger.info(f"   기존 기록: ${old_price:.2f} ({old_amount}주)")  
            logger.info(f"   실제 체결가: ${actual_execution_price:.2f} ({executed_amount}주)")
            logger.info(f"   가격 개선: ${price_improvement:+.2f}")
            logger.info(f"   주문시간: {order_time}")
            logger.info(f"   방법: 주문내역 직접 조회 (100% 정확)")
            
            # 🔥 12. 업데이트 후 전체 상태 확인 로깅
            logger.info(f"📊 {stock_code} 업데이트 후 상태:")
            for i, magic_data in enumerate(stock_data_info['MagicDataList']):
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    emoji = "🎯" if i == target_position_index else "📍"
                    logger.info(f"   {emoji} {i+1}차: ${magic_data['EntryPrice']:.2f} ({magic_data['CurrentAmt']}주)")
            
            # 🔥 13. 브로커 참조 정보 저장
            stock_data_info['OrderSyncInfo'] = {
                'last_order_num': latest_buy_order.get('OrderNum', ''),
                'last_order_num2': latest_buy_order.get('OrderNum2', ''),
                'actual_execution_price': actual_execution_price,
                'executed_amount': executed_amount,
                'order_date': latest_buy_order['OrderDate'],
                'order_time': order_time,
                'sync_position': position_num,  # 🔥 정확한 차수 기록
                'sync_method': '주문내역조회',
                'last_sync_time': datetime.now().isoformat()
            }
            
            # 🔥 14. 데이터 저장
            self.save_split_data()
            return True
            
        except Exception as e:
            logger.error(f"❌ {stock_code} {position_num}차 주문조회 기반 동기화 중 오류: {str(e)}")
            return False

    def get_current_buying_position(self, stock_code):
        """현재 매수 중인 차수 파악 - 3차수용"""
        try:
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return None
            
            # 🔍 방법 1: 가장 최근 EntryDate를 가진 차수 찾기
            today = datetime.now().strftime("%Y-%m-%d")
            recent_positions = []
            
            for i, magic_data in enumerate(stock_data_info['MagicDataList']):
                if (magic_data.get('IsBuy', False) and 
                    magic_data.get('EntryDate') == today and
                    magic_data.get('CurrentAmt', 0) > 0):
                    recent_positions.append(i + 1)  # 1-based
            
            if recent_positions:
                return max(recent_positions)  # 가장 높은 차수 반환
            
            # 🔍 방법 2: 보유 중인 가장 높은 차수
            for i in range(2, -1, -1):  # 🔥 3차부터 역순으로 (2, 1, 0)
                magic_data = stock_data_info['MagicDataList'][i]
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    return i + 1
            
            return None
            
        except Exception as e:
            logger.error(f"매수 차수 파악 중 오류: {str(e)}")
            return None

    def get_next_buying_position(self, stock_code):
        """다음 매수할 차수 정확히 계산"""
        try:
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return 1
            
            # 현재 활성 포지션들 확인
            active_positions = []
            for i, magic_data in enumerate(stock_data_info['MagicDataList']):
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    active_positions.append(i + 1)
            
            if not active_positions:
                return 1
            
            # 다음 빈 차수 찾기
            max_position = len(stock_data_info['MagicDataList'])
            for position_num in range(1, max_position + 1):
                if position_num not in active_positions:
                    return position_num
            
            return None
            
        except Exception as e:
            logger.error(f"다음 매수 차수 계산 중 오류: {str(e)}")
            return None

    def get_actual_execution_price(self, stock_code, order_price):
        """실제 체결가 조회 - 주문내역에서 정확한 체결가 추출"""
        try:
            time.sleep(1)  # 브로커 시스템 반영 대기
            
            # 최근 매수 주문 조회
            recent_orders = SafeKisUS.safe_get_order_list(stock_code, "BUY", "CLOSE", 1)
            if not recent_orders:
                return None
            
            # 오늘 날짜의 가장 최근 체결 주문 찾기
            today = datetime.now().strftime("%Y%m%d")
            
            for order in recent_orders:
                if (order.get('OrderDate') == today and 
                    order.get('OrderResultAmt', 0) > 0 and  # 체결량 있음
                    order.get('OrderSatus') == 'Close'):     # 체결 완료
                    
                    actual_price = float(order.get('OrderAvgPrice', 0))
                    
                    # 합리성 검증: 주문가와 5% 이상 차이나면 제외
                    if actual_price > 0:
                        price_diff_pct = abs(actual_price - order_price) / order_price * 100
                        if price_diff_pct <= 5.0:  # 5% 이내만 허용
                            logger.info(f"✅ {stock_code} 실제 체결가 조회 성공: ${actual_price:.2f}")
                            return actual_price
            
            return None
            
        except Exception as e:
            logger.error(f"❌ {stock_code} 실제 체결가 조회 오류: {str(e)}")
            return None

    def handle_buy_with_execution_tracking(self, stock_code, amount, price):
        """개선된 매수 주문 처리 - 체결량 계산 오류 수정"""
        try:
            stock_name = config.target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥 1. 매수 전 보유량 기록 (핵심 추가)
            before_holdings = self.get_current_holdings(stock_code)
            before_amount = before_holdings.get('amount', 0)
            before_avg_price = before_holdings.get('avg_price', 0)
            
            logger.info(f"📊 {stock_name} 매수 전 현황:")
            logger.info(f"   보유량: {before_amount}주")
            if before_avg_price > 0:
                logger.info(f"   평균가: ${before_avg_price:.2f}")
            
            # 🔥 2. 현재가 재조회 (기존 로직 유지)
            old_price = price
            try:
                current_price = SafeKisUS.safe_get_current_price(stock_code)

                if current_price and current_price > 0:
                    actual_price = current_price
                    price_diff = actual_price - old_price
                    logger.info(f"💰 매수 전 현재가 재조회: {stock_name}")
                    logger.info(f"   분석시 가격: ${old_price:.2f}")
                    logger.info(f"   현재 가격: ${actual_price:.2f}")
                    logger.info(f"   가격 변화: ${price_diff:+.2f}")
                    
                    # 가격 변화 검증
                    price_change_rate = abs(price_diff) / old_price
                    if price_change_rate > 0.03:
                        logger.warning(f"⚠️ 가격 변화 {price_change_rate*100:.1f}% 감지")
                        if price_diff > 0 and price_change_rate > 0.05:
                            logger.warning(f"💔 과도한 가격 상승으로 매수 포기")
                            return None, None, "가격 급등으로 매수 포기"
                else:
                    actual_price = old_price
                    logger.warning(f"⚠️ 현재가 조회 실패, 분석시 가격 사용: ${actual_price:.2f}")
                    
            except Exception as price_error:
                actual_price = old_price
                logger.error(f"❌ 현재가 조회 중 오류: {str(price_error)}")
            
            # 🔥 3. 미체결 주문 추적 초기화
            if not hasattr(self, 'pending_orders'):
                self.pending_orders = {}
            
            # 중복 주문 방지
            if stock_code in self.pending_orders:
                pending_info = self.pending_orders[stock_code]
                order_time = datetime.strptime(pending_info['order_time'], '%Y-%m-%d %H:%M:%S')
                elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                
                if elapsed_minutes < 10:
                    logger.warning(f"❌ 중복 주문 방지: {stock_name} - {elapsed_minutes:.1f}분 전 주문 있음")
                    return None, None, "중복 주문 방지"
            
            # 🔥 4. 주문 정보 기록
            order_info = {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'order_amount': amount,
                'before_amount': before_amount,  # 🔥 매수 전 보유량 추가
                'analysis_price': old_price,
                'order_price': actual_price,
                'price_change': actual_price - old_price,
                'status': 'submitted'
            }
            
            self.pending_orders[stock_code] = order_info
            
            # 🔥 5. 주문 전송
            estimated_fee = self.calculate_trading_fee(actual_price, amount, True)
            order_price = round(actual_price * 1.01, 2)  # 1% 위로 지정가
            
            logger.info(f"🔵 {stock_name} 매수 주문 전송")
            logger.info(f"   수량: {amount}주")
            logger.info(f"   주문가격: ${order_price:.2f} (현재가 +1%)")
            logger.info(f"   예상 수수료: ${estimated_fee:.2f}")
            
            # order_result = KisUS.MakeBuyLimitOrder(stock_code, amount, order_price)
            order_result = SafeKisUS.safe_make_buy_limit_order(stock_code, amount, order_price)

            if not order_result or isinstance(order_result, str):
                # 주문 실패시 pending 제거
                if stock_code in self.pending_orders:
                    del self.pending_orders[stock_code]
                
                error_msg = f"❌ 매수 주문 실패: {stock_name} - {order_result}"
                logger.error(error_msg)
                return None, None, error_msg
            
            # 🔥 6. 주문 성공시 order_id 기록
            if isinstance(order_result, dict):
                order_id = order_result.get('OrderNum', order_result.get('OrderNo', ''))
                if order_id:
                    self.pending_orders[stock_code]['order_id'] = order_id
                    logger.info(f"📋 주문번호 등록: {stock_name} - {order_id}")
            
            # 🔥 7. 개선된 체결 확인 (핵심 수정)
            logger.info(f"⏳ {stock_name} 체결 확인 시작 (최대 60초)")
            start_time = time.time()
            check_count = 0
            
            while time.time() - start_time < 60:
                check_count += 1
                
                # 미국주식 보유 종목 조회
                my_stocks = SafeKisUS.safe_get_my_stock_list("USD")
                if my_stocks is None:
                    continue  # 다음 체크로 넘어감

                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        current_total = int(stock.get('StockAmt', 0))  # 현재 총 보유량
                        
                        # 🔥🔥🔥 핵심 수정: 실제 체결가 조회 🔥🔥🔥
                        actual_execution_price = self.get_actual_execution_price(stock_code, order_price)
                        
                        # 실제 체결가 조회 실패 시 주문가 사용 (안전장치)
                        if actual_execution_price is None:
                            actual_execution_price = order_price
                            logger.warning(f"⚠️ {stock_name} 실제 체결가 조회 실패 - 주문가 사용: ${order_price:.2f}")

                        # 🔥🔥🔥 핵심 수정: 증가분을 실제 체결량으로 계산 🔥🔥🔥
                        actual_executed = current_total - before_amount
                        
                        if actual_executed >= amount:  # 목표 수량 이상 체결
                            
                            # 🔥 체결 상세 정보 로깅 (수정됨)
                            logger.info(f"✅ {stock_name} 매수 체결 완료!")
                            logger.info(f"   🎯 목표수량: {amount}주")
                            logger.info(f"   📊 매수 전 보유: {before_amount}주")
                            logger.info(f"   📊 매수 후 총보유: {current_total}주")
                            logger.info(f"   ✅ 실제 체결량: {actual_executed}주")  # 🔥 수정: 실제 증가분
                            logger.info(f"   💰 주문가격: ${order_price:.2f}")
                            logger.info(f"   💰 체결가격: ${actual_execution_price:.2f}")  # 🔥 수정: 실제 체결가
                            
                            # 가격 개선 계산
                            execution_diff = actual_execution_price - order_price
                            total_investment = actual_execution_price * actual_executed  # 🔥 수정: 실제 체결가 기준
                            actual_fee = self.calculate_trading_fee(actual_execution_price, actual_executed, True)
                            
                            logger.info(f"   📊 가격개선: ${execution_diff:+.2f}")
                            logger.info(f"   💵 투자금액: ${total_investment:.2f}")
                            logger.info(f"   💸 실제수수료: ${actual_fee:.2f}")
                            logger.info(f"   🕐 체결시간: {check_count * 5}초")
                            
                            # 체결 완료시 pending 제거
                            if stock_code in self.pending_orders:
                                del self.pending_orders[stock_code]
                            
                            # 🔥 체결 완료 알림 (수정됨)
                            if config.config.get("use_discord_alert", True):
                                msg = f"✅ {stock_name} 매수 체결!\n"
                                msg += f"💰 ${actual_execution_price:.2f} × {actual_executed}주\n"  # 🔥 실제 체결가/체결량
                                msg += f"📊 투자금액: ${total_investment:.2f}\n"
                                if abs(execution_diff) > 0.1:
                                    msg += f"🎯 가격개선: ${execution_diff:+.2f}\n"
                                msg += f"⚡ 체결시간: {check_count * 5}초"
                                discord_alert.SendMessage(msg)
                            
                            # 🔧 개선된 동기화 호출 (핵심 수정)
                            try:
                                # 현재 몇 차수 매수인지 파악
                                current_position_num = self.get_next_buying_position(stock_code)
                                if not current_position_num:
                                    logger.error(f"❌ {stock_code} 다음 매수 차수를 찾을 수 없음")
                                    return None, None, "차수 계산 실패"
                                logger.info(f"📊 {stock_name} 매수 예정 차수: {current_position_num}차")

                                if current_position_num:
                                    logger.info(f"🔄 {stock_name} {current_position_num}차 실제 체결가 동기화 시작")
                                    # 🔥🔥🔥 새로운 동기화 로직 사용 🔥🔥🔥
                                    sync_success = self.sync_position_after_buy_with_order_list(
                                        stock_code=stock_code,
                                        position_num=current_position_num, 
                                        order_price=order_price,
                                        expected_amount=actual_executed
                                    )
                                    if sync_success:
                                        logger.info(f"✅ {stock_name} {current_position_num}차 정확한 체결가 동기화 완료")
                                    else:
                                        logger.warning(f"⚠️ {stock_name} {current_position_num}차 동기화 실패 (매수는 성공)")
                                else:
                                    logger.warning(f"⚠️ {stock_name} 매수 차수 파악 실패 - 동기화 스킵")
                                    
                            except Exception as sync_error:
                                logger.error(f"⚠️ {stock_name} 동기화 실패하지만 매수는 성공: {str(sync_error)}")
                                # 🔥 중요: 동기화 실패해도 매수는 성공으로 처리
                            
                            # 🔥🔥🔥 핵심: 실제 체결가 반환 🔥🔥🔥
                            return actual_execution_price, actual_executed, "체결 완료"  # 🔥 수정: 실제 체결가 반환
                
                # 5초마다 체크
                if check_count % 3 == 0:  # 15초마다 로그
                    logger.info(f"   ⏳ 체결 대기 중... ({check_count * 5}초 경과)")
                
                time.sleep(5)
            
            # 🔥 8. 미체결시 처리
            logger.warning(f"⏰ {stock_name} 체결 시간 초과 (60초)")
            
            # 미체결 상태로 기록 유지
            if stock_code in self.pending_orders:
                self.pending_orders[stock_code]['status'] = 'pending'
                self.pending_orders[stock_code]['timeout_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 미체결 알림
            if config.config.get("use_discord_alert", True):
                msg = f"⏰ {stock_name} 매수 미체결\n"
                msg += f"💰 주문: ${order_price:.2f} × {amount}주\n"
                msg += f"⚠️ 60초 내 체결되지 않음\n"
                msg += f"🔄 계속 모니터링 중..."
                discord_alert.SendMessage(msg)
            
            logger.warning(f"⚠️ 미체결: {stock_name} - 주문은 활성 상태")
            return None, None, "체결 시간 초과"
            
        except Exception as e:
            # 예외 발생시 pending 정리
            try:
                if hasattr(self, 'pending_orders') and stock_code in self.pending_orders:
                    del self.pending_orders[stock_code]
            except:
                pass
            
            logger.error(f"❌ 매수 주문 처리 중 오류: {str(e)}")
            return None, None, str(e)

    def check_and_manage_pending_orders(self):
        """미체결 주문 자동 관리 (bb_trading.py 컨셉 적용) - 수정 버전"""
        try:
            # 🔥 수정: pending_orders가 인스턴스 변수로 변경됨
            if not hasattr(self, 'pending_orders') or not self.pending_orders:
                return
            
            logger.info("🔍 미체결 주문 자동 관리 시작")
            
            completed_orders = []
            expired_orders = []
            
            for stock_code, order_info in self.pending_orders.items():
                try:
                    stock_name = order_info.get('stock_name', stock_code)
                    order_time = datetime.strptime(order_info['order_time'], '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                    
                    logger.info(f"📋 미체결 주문 체크: {stock_name} ({elapsed_minutes:.1f}분 경과)")
                    
                    # 🔥 1. 체결 여부 재확인
                    my_stocks = SafeKisUS.safe_get_my_stock_list("USD")
                    executed_amount = 0
                    avg_price = 0
                    
                    for stock in my_stocks:
                        if stock['StockCode'] == stock_code:
                            executed_amount = int(stock.get('StockAmt', 0))
                            avg_price = float(stock.get('StockAvgPrice', 0))
                            break
                    
                    if executed_amount >= order_info['order_amount']:
                        # 🎉 체결 완료 발견!
                        logger.info(f"✅ 지연 체결 발견: {stock_name} {executed_amount}주 @ ${avg_price:.2f}")
                        
                        completed_orders.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'executed_price': avg_price,
                            'executed_amount': executed_amount,
                            'delay_minutes': elapsed_minutes
                        })
                        
                        # Discord 알림
                        if config.config.get("use_discord_alert", True):
                            msg = f"🎉 지연 체결 발견: {stock_name}\n"
                            msg += f"💰 ${avg_price:.2f} × {executed_amount}주\n"
                            msg += f"⏰ 지연시간: {elapsed_minutes:.1f}분"
                            discord_alert.SendMessage(msg)
                        
                    elif elapsed_minutes > 15:  # 15분 이상 미체결
                        # 🗑️ 만료 처리
                        logger.warning(f"⏰ 미체결 주문 만료: {stock_name} ({elapsed_minutes:.1f}분)")
                        
                        expired_orders.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'elapsed_minutes': elapsed_minutes
                        })
                        
                        # 필요시 주문 취소 로직 추가 가능
                        
                    else:
                        # 🔄 계속 대기
                        logger.info(f"⏳ 계속 대기: {stock_name} ({elapsed_minutes:.1f}/15분)")
                    
                except Exception as e:
                    logger.error(f"미체결 주문 체크 중 오류 ({stock_code}): {str(e)}")
            
            # 🔥 완료된 주문 제거
            for completed in completed_orders:
                stock_code = completed['stock_code']
                if stock_code in self.pending_orders:
                    del self.pending_orders[stock_code]
                    logger.info(f"✅ 완료된 주문 제거: {completed['stock_name']}")
            
            # 🔥 만료된 주문 제거
            for expired in expired_orders:
                stock_code = expired['stock_code']
                if stock_code in self.pending_orders:
                    del self.pending_orders[stock_code]
                    logger.info(f"⏰ 만료된 주문 제거: {expired['stock_name']}")
            
            # 요약 알림
            if completed_orders or expired_orders:
                summary_msg = f"📋 미체결 주문 관리 완료\n"
                if completed_orders:
                    summary_msg += f"✅ 지연 체결: {len(completed_orders)}개\n"
                if expired_orders:
                    summary_msg += f"⏰ 만료 정리: {len(expired_orders)}개"
                
                logger.info(summary_msg)
            
            remaining_count = len(getattr(self, 'pending_orders', {}))
            if remaining_count > 0:
                logger.info(f"🔄 계속 관리 중인 미체결 주문: {remaining_count}개")
            
        except Exception as e:
            logger.error(f"미체결 주문 자동 관리 중 오류: {str(e)}")        

    def handle_buy(self, stock_code, amount, price):
        """개선된 매수 주문 처리 (bb_trading.py 로직 적용)"""
        success, executed_amount, message = self.handle_buy_with_execution_tracking(stock_code, amount, price)
        
        if success and executed_amount:
            return success, executed_amount
        else:
            return None, None

    def handle_sell(self, stock_code, amount, price):
        """매도 주문 처리 - 미국주식용 (로깅 개선)"""
        try:
            # 수수료 예상 계산
            estimated_fee = self.calculate_trading_fee(price, amount, False)
            
            # 🔥 미국주식 지정가 매도 주문 (1% 아래로 주문)
            order_price = round(price * 0.99, 2)
            result = SafeKisUS.safe_make_sell_limit_order(stock_code, amount, order_price)
                        
            if result:
                logger.info(f"📉 {stock_code} 매도 주문 전송: {amount}주 × ${order_price:.2f}, 예상 수수료: ${estimated_fee:.2f}")
            
            return result, None
        except Exception as e:
            return None, str(e)
            
    def count_recent_stop_losses(self, days=7):
        """최근 N일간 손절 횟수 계산"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            stop_count = 0
            
            for stock_data in self.split_data_list:
                for magic_data in stock_data.get('MagicDataList', []):
                    for sell_record in magic_data.get('SellHistory', []):
                        if '손절' in sell_record.get('reason', ''):
                            try:
                                sell_date = datetime.strptime(sell_record.get('date', ''), "%Y-%m-%d")
                                if sell_date >= cutoff_date:
                                    stop_count += 1
                                    break  # 같은 종목의 중복 카운트 방지
                            except:
                                continue
            
            return stop_count
            
        except Exception as e:
            logger.error(f"최근 손절 횟수 계산 중 오류: {str(e)}")
            return 0        
        
    ################################### 1. 스마트 매수 결정 함수 (새로 추가) ###################################

    def smart_buy_decision(self, stock_code, indicators, news_adjusted_conditions, market_timing):
        """🔥 개선된 스마트 매수 결정 - 핵심 조건 + 가점 시스템"""
        try:
            # 🔴 핵심 조건 (Must Have) - 3개만!
            min_pullback = news_adjusted_conditions['min_pullback']
            max_rsi_buy = news_adjusted_conditions['max_rsi_buy']
            min_green_candle = news_adjusted_conditions['green_candle_req']
            
            # 필수 조건들
            core_conditions = {
                'pullback_ok': indicators['pullback_from_high'] >= min_pullback,
                'rsi_ok': 15 <= indicators['rsi'] <= max_rsi_buy,
                'price_positive': indicators['current_price'] > 0
            }
            
            # 🔴 핵심 조건 체크
            core_passed = all(core_conditions.values())
            
            if not core_passed:
                failed_cores = [k for k, v in core_conditions.items() if not v]
                logger.debug(f"💥 {stock_code} 핵심 조건 실패: {failed_cores}")
                return False, "핵심 조건 미달성", {}
            
            # 🟡 보조 조건 (Nice to Have) - 가점 시스템
            bonus_score = 0
            bonus_details = []
            
            # 이동평균 추세 (2점)
            if indicators['market_trend'] in ['up', 'strong_up']:
                bonus_score += 2
                bonus_details.append("상승추세(+2)")
            elif indicators['market_trend'] in ['sideways']:
                bonus_score += 1
                bonus_details.append("횡보(+1)")
            
            # 거래량 (1점)
            try:
                # 간단한 거래량 체크 (구현 가능한 범위에서)
                if indicators.get('volume_spike', False):  # 향후 구현 시
                    bonus_score += 1
                    bonus_details.append("거래량(+1)")
            except:
                pass
            
            # 캔들 패턴 (1점)
            candle_strength = indicators['prev_close'] / indicators['prev_open']
            if candle_strength >= min_green_candle:
                bonus_score += 1
                bonus_details.append(f"양봉({candle_strength:.3f}, +1)")
            
            # RSI 과매도 보너스 (2점)
            if indicators['rsi'] <= 35:
                bonus_score += 2
                bonus_details.append(f"과매도(RSI:{indicators['rsi']:.1f}, +2)")
            elif indicators['rsi'] <= 45:
                bonus_score += 1
                bonus_details.append(f"저RSI(RSI:{indicators['rsi']:.1f}, +1)")
            
            # 큰 조정 보너스 (1-2점)
            if indicators['pullback_from_high'] >= min_pullback * 2.5:
                bonus_score += 2
                bonus_details.append(f"큰조정({indicators['pullback_from_high']:.1f}%, +2)")
            elif indicators['pullback_from_high'] >= min_pullback * 1.8:
                bonus_score += 1
                bonus_details.append(f"적당조정({indicators['pullback_from_high']:.1f}%, +1)")
            
            # 시장 상황 보너스 (1점)
            if market_timing in ["downtrend", "strong_downtrend"]:
                bonus_score += 1
                bonus_details.append(f"하락장기회({market_timing}, +1)")
            
            # 🎯 최종 점수 기준
            required_bonus_score = 3  # 보조 조건 3점 이상
            
            # 🔥 시장 상황별 기준 조정
            if market_timing == "strong_downtrend":
                required_bonus_score = 2  # 강한 하락장에서는 2점으로 완화
            elif market_timing == "strong_uptrend":
                required_bonus_score = 4  # 강한 상승장에서는 4점으로 강화
            
            decision_passed = bonus_score >= required_bonus_score
            
            # 로깅
            logger.info(f"🎯 {stock_code} 스마트 매수 결정:")
            logger.info(f"   🔴 핵심: 조정{indicators['pullback_from_high']:.1f}%≥{min_pullback:.1f}%, RSI{indicators['rsi']:.1f}≤{max_rsi_buy}")
            logger.info(f"   🟡 보조: {bonus_score}점/{required_bonus_score}점 필요 - {', '.join(bonus_details) if bonus_details else '없음'}")
            logger.info(f"   ✅❌ 최종: {'매수 허용' if decision_passed else '매수 거부'}")
            
            decision_summary = {
                'core_score': '3/3' if core_passed else f"{sum(core_conditions.values())}/3",
                'bonus_score': f'{bonus_score}/{required_bonus_score}',
                'bonus_details': bonus_details,
                'market_timing': market_timing
            }
            
            return decision_passed, "스마트 결정 완료", decision_summary
            
        except Exception as e:
            logger.error(f"스마트 매수 결정 중 오류: {str(e)}")
            return False, f"결정 오류: {str(e)}", {}

    ################################### 2. 차수별 간소화된 매수 조건 ###################################

    def get_simplified_buy_conditions_by_position(self, position_num, magic_data_list, indicators, progressive_drops):
        """🔥 차수별 간소화된 매수 조건 - 복잡한 로직 제거"""
        try:
            if position_num == 1:  # 1차 매수
                return {
                    'condition_type': 'initial_entry',
                    'special_checks': [],
                    'description': '1차 매수 (스마트 결정만 적용)'
                }
                
            elif position_num == 2:  # 2차 매수  
                if magic_data_list[0]['IsBuy'] and magic_data_list[0]['CurrentAmt'] > 0:
                    entry_price_1st = magic_data_list[0]['EntryPrice']
                    drop_threshold = float(progressive_drops.get("2", 0.06))
                    
                    # 🔥 간소화: 가격 조건만 체크
                    price_drop = (entry_price_1st - indicators['current_price']) / entry_price_1st
                    price_condition = price_drop >= drop_threshold
                    
                    return {
                        'condition_type': 'price_drop',
                        'price_condition': price_condition,
                        'required_drop': drop_threshold,
                        'actual_drop': price_drop,
                        'entry_price': entry_price_1st,
                        'description': f'2차 매수 ({drop_threshold*100:.0f}% 하락 시)'
                    }
                else:
                    return {'condition_type': 'blocked', 'description': '1차 보유 없음'}
                    
            elif position_num == 3:  # 3차 매수
                if magic_data_list[1]['IsBuy'] and magic_data_list[1]['CurrentAmt'] > 0:
                    entry_price_2nd = magic_data_list[1]['EntryPrice']
                    drop_threshold = float(progressive_drops.get("3", 0.07))
                    
                    price_drop = (entry_price_2nd - indicators['current_price']) / entry_price_2nd
                    price_condition = price_drop >= drop_threshold
                    
                    return {
                        'condition_type': 'price_drop',
                        'price_condition': price_condition,
                        'required_drop': drop_threshold,
                        'actual_drop': price_drop,
                        'entry_price': entry_price_2nd,
                        'description': f'3차 매수 ({drop_threshold*100:.0f}% 하락 시)'
                    }
                else:
                    return {'condition_type': 'blocked', 'description': '2차 보유 없음'}
                    
            elif position_num == 4:  # 4차 매수
                if magic_data_list[2]['IsBuy'] and magic_data_list[2]['CurrentAmt'] > 0:
                    entry_price_3rd = magic_data_list[2]['EntryPrice']
                    drop_threshold = float(progressive_drops.get("4", 0.09))
                    
                    price_drop = (entry_price_3rd - indicators['current_price']) / entry_price_3rd
                    price_condition = price_drop >= drop_threshold
                    
                    # 4차는 추가 안전 조건
                    safety_condition = indicators['rsi'] <= 40  # 간소화: RSI만 체크
                    
                    return {
                        'condition_type': 'price_drop_with_safety',
                        'price_condition': price_condition,
                        'safety_condition': safety_condition,
                        'required_drop': drop_threshold,
                        'actual_drop': price_drop,
                        'entry_price': entry_price_3rd,
                        'description': f'4차 매수 ({drop_threshold*100:.0f}% 하락 + RSI≤40)'
                    }
                else:
                    return {'condition_type': 'blocked', 'description': '3차 보유 없음'}
                    
            elif position_num == 5:  # 5차 매수
                if magic_data_list[3]['IsBuy'] and magic_data_list[3]['CurrentAmt'] > 0:
                    entry_price_4th = magic_data_list[3]['EntryPrice']
                    drop_threshold = float(progressive_drops.get("5", 0.11))
                    
                    price_drop = (entry_price_4th - indicators['current_price']) / entry_price_4th
                    price_condition = price_drop >= drop_threshold
                    
                    # 5차는 더 엄격한 안전 조건 (하지만 간소화)
                    safety_condition = (indicators['rsi'] <= 35 and 
                                    indicators['prev_close'] > indicators['prev_open'] * 0.97)
                    
                    return {
                        'condition_type': 'final_safety',
                        'price_condition': price_condition,
                        'safety_condition': safety_condition,
                        'required_drop': drop_threshold,
                        'actual_drop': price_drop,
                        'entry_price': entry_price_4th,
                        'description': f'5차 매수 (최종 방어, {drop_threshold*100:.0f}% 하락 + 안전조건)'
                    }
                else:
                    return {'condition_type': 'blocked', 'description': '4차 보유 없음'}
            
            return {'condition_type': 'invalid', 'description': '잘못된 차수'}
            
        except Exception as e:
            logger.error(f"차수별 조건 계산 중 오류: {str(e)}")
            return {'condition_type': 'error', 'description': f'조건 계산 오류: {str(e)}'}

    def calculate_dynamic_drop_requirement(self, position_num, indicators, market_timing, news_sentiment):
        """동적 하락률 요구사항 계산 - 조건에 따라 완화/강화"""
        try:
            # 🔥 기본 하락률 설정
            base_required_drops = {
                2: 0.06,  # 기본 6%
                3: 0.07,  # 기본 7%  
                4: 0.09,  # 기본 9%
                5: 0.11   # 기본 11%
            }
            
            base_drop = base_required_drops.get(position_num, 0.06)
            adjustment_factor = 1.0
            adjustments = []
            
            # 🟢 완화 조건들 (하락률 요구 줄이기)
            
            # RSI 과매도 조건
            rsi = indicators.get('rsi', 50)
            if rsi <= 25:
                adjustment_factor *= 0.8    # 20% 완화
                adjustments.append("극한과매도(-20%)")
            elif rsi <= 35:
                adjustment_factor *= 0.9    # 10% 완화
                adjustments.append("과매도(-10%)")
            
            # 시장 상황별 완화
            if market_timing == "strong_downtrend":
                adjustment_factor *= 0.7    # 30% 완화
                adjustments.append("강한하락장(-30%)")
            elif market_timing == "downtrend":
                adjustment_factor *= 0.85   # 15% 완화
                adjustments.append("하락장(-15%)")
            
            # 긍정적 뉴스 완화
            news_decision = news_sentiment.get('decision', 'NEUTRAL')
            news_percentage = news_sentiment.get('percentage', 0)
            if news_decision == 'POSITIVE' and news_percentage >= 70:
                adjustment_factor *= 0.9    # 10% 완화
                adjustments.append("긍정뉴스(-10%)")
            
            # 큰 조정 시 완화 (이미 많이 떨어진 상태)
            pullback = indicators.get('pullback_from_high', 0)
            if pullback >= 15:  # 15% 이상 조정
                adjustment_factor *= 0.85   # 15% 완화
                adjustments.append(f"큰조정{pullback:.1f}%(-15%)")
            elif pullback >= 10:  # 10% 이상 조정
                adjustment_factor *= 0.9    # 10% 완화
                adjustments.append(f"중간조정{pullback:.1f}%(-10%)")
            
            # 🔴 강화 조건들 (하락률 요구 늘리기)
            
            # 강한 상승장에서 신중하게
            if market_timing == "strong_uptrend":
                adjustment_factor *= 1.3    # 30% 강화
                adjustments.append("강한상승장(+30%)")
            elif market_timing == "uptrend":
                adjustment_factor *= 1.15   # 15% 강화  
                adjustments.append("상승장(+15%)")
            
            # 부정적 뉴스 강화
            if news_decision == 'NEGATIVE' and news_percentage >= 70:
                adjustment_factor *= 1.2    # 20% 강화
                adjustments.append("부정뉴스(+20%)")
            
            # RSI 과매수 강화
            if rsi >= 70:
                adjustment_factor *= 1.2    # 20% 강화
                adjustments.append("과매수(+20%)")
            elif rsi >= 60:
                adjustment_factor *= 1.1    # 10% 강화
                adjustments.append("과매수주의(+10%)")
            
            # 최종 하락률 계산 (안전 범위 제한)
            final_drop = base_drop * adjustment_factor
            final_drop = max(base_drop * 0.5, min(final_drop, base_drop * 1.5))  # 50%~150% 범위
            
            return final_drop, adjustments
            
        except Exception as e:
            logger.error(f"동적 하락률 계산 중 오류: {str(e)}")
            # 오류 시 기본값 반환
            return base_required_drops.get(position_num, 0.06), ["오류로기본값사용"]

    def calculate_comprehensive_entry_score(self, stock_code, position_num, indicators, news_sentiment, magic_data_list):
        """종합적 진입 점수 계산 함수 - 🔥 동적 하락률 필수 검증 + 점수 시스템"""
        try:
            # 🔥🔥🔥 1단계: 동적 하락률 필수 검증 (Pass/Fail) 🔥🔥🔥
            if position_num == 1:
                # 1차수는 하락률 조건 없음 (초기 진입)
                pass
            else:
                # 🔥 순차적 직전 차수 확인
                prev_index = position_num - 2
                if prev_index >= 0 and prev_index < len(magic_data_list):
                    prev_data = magic_data_list[prev_index]
                    
                    # 직전 차수 보유 확인
                    if not (prev_data.get('IsBuy', False) and prev_data.get('CurrentAmt', 0) > 0):
                        logger.warning(f"{stock_code} {position_num}차: {position_num-1}차 미보유로 순차 진입 차단")
                        return 0, [f"{position_num-1}차 미보유로 순차 진입 차단"]
                    
                    prev_price = prev_data.get('EntryPrice', 0)
                    if prev_price <= 0:
                        return 0, [f"{position_num-1}차 매수가 없음"]
                    
                    current_price = indicators.get('current_price', 0)
                    if current_price <= 0:
                        return 0, ["현재가 정보 없음"]
                    
                    # 🔥 동적 하락률 계산
                    market_timing = self.detect_market_timing()
                    required_drop, adjustments = self.calculate_dynamic_drop_requirement(
                        position_num, indicators, market_timing, news_sentiment
                    )
                    
                    actual_drop = (prev_price - current_price) / prev_price
                    
                    # 🔥 필수 하락률 검증 (이 조건을 통과해야만 점수 계산 진행)
                    if actual_drop < required_drop:
                        fail_reason = f"필수 하락률 미달: {actual_drop*100:.1f}% < {required_drop*100:.1f}%"
                        if adjustments:
                            fail_reason += f" (조건조정: {', '.join(adjustments)})"
                        
                        logger.info(f"🚫 {stock_code} {position_num}차 하락률 검증 실패:")
                        logger.info(f"   기준가: {position_num-1}차 ${prev_price:.2f}")
                        logger.info(f"   현재가: ${current_price:.2f}")
                        logger.info(f"   실제하락: {actual_drop*100:.1f}%")
                        logger.info(f"   필요하락: {required_drop*100:.1f}%")
                        if adjustments:
                            logger.info(f"   조건조정: {', '.join(adjustments)}")
                        
                        return 0, [fail_reason]
                    
                    # 하락률 통과 시 성공 로깅
                    logger.info(f"✅ {stock_code} {position_num}차 하락률 검증 통과:")
                    logger.info(f"   {actual_drop*100:.1f}% ≥ {required_drop*100:.1f}% ({', '.join(adjustments) if adjustments else '기본조건'})")
                
                else:
                    return 0, ["직전 차수 데이터 없음"]
            
            # 🔥🔥🔥 2단계: 하락률 통과 후 종합 점수 계산 🔥🔥🔥
            total_score = 0
            score_details = []
            
            # 🔥 1️⃣ 가격 조건 점수 (30점) - 하락률 달성도 기반
            if position_num == 1:
                # 1차수: 조정폭 기반 점수
                pullback = indicators.get('pullback_from_high', 0)
                if pullback >= 8.0:
                    price_score = 30
                    price_desc = f"조정폭({pullback:.1f}%)"
                elif pullback >= 5.0:
                    price_score = 25
                    price_desc = f"조정폭({pullback:.1f}%)"
                elif pullback >= 3.0:
                    price_score = 20
                    price_desc = f"조정폭({pullback:.1f}%)"
                elif pullback >= 1.5:
                    price_score = 15
                    price_desc = f"조정폭({pullback:.1f}%)"
                else:
                    price_score = 5
                    price_desc = f"조정폭({pullback:.1f}%)"
                
            else:
                # 2-5차수: 하락률 달성도 기반 점수 (이미 필수 조건은 통과함)
                if actual_drop >= required_drop * 1.5:
                    price_score = 30  # 큰 하락 (필요량의 150% 이상)
                    achievement = f"{actual_drop/required_drop*100:.0f}%달성"
                elif actual_drop >= required_drop * 1.2:
                    price_score = 25  # 충분한 하락 (필요량의 120% 이상)
                    achievement = f"{actual_drop/required_drop*100:.0f}%달성"
                else:
                    price_score = 20  # 기본 달성 (필요량 달성)
                    achievement = f"{actual_drop/required_drop*100:.0f}%달성"
                
                price_desc = f"순차하락률({actual_drop*100:.1f}%/{required_drop*100:.0f}%, {achievement})"
                
                # 조정사항이 있으면 추가 표시
                if adjustments:
                    price_desc += f", 조건조정됨"
            
            total_score += price_score
            score_details.append(f"{price_desc}: {price_score}점")
            
            # 🔥 2️⃣ RSI 점수 (20점) - 기존 로직 유지
            rsi = indicators.get('rsi', 50)
            if 20 <= rsi <= 30:
                rsi_score = 20
            elif 30 <= rsi <= 45:
                rsi_score = 16
            elif 45 <= rsi <= 55:
                rsi_score = 12
            elif 55 <= rsi <= 70:
                rsi_score = 8
            elif 70 <= rsi <= 80:
                rsi_score = 4
            else:
                rsi_score = 0
                
            total_score += rsi_score
            score_details.append(f"RSI({rsi:.1f}): {rsi_score}점")
            
            # 🔥 3️⃣ 추세 점수 (15점) - 기존 로직 유지
            market_trend = indicators.get('market_trend', 'sideways')
            trend_scores = {
                'strong_up': 15, 'up': 12, 'sideways': 9, 'down': 6, 'strong_down': 3
            }
            trend_score = trend_scores.get(market_trend, 9)
            total_score += trend_score
            score_details.append(f"추세({market_trend}): {trend_score}점")
            
            # 🔥 4️⃣ 지지선 점수 (10점) - 기존 로직 유지
            current_price = indicators.get('current_price', 0)
            ma_short = indicators.get('ma_short', 0)
            ma_mid = indicators.get('ma_mid', 0)
            
            if current_price > 0 and ma_short > 0 and ma_mid > 0:
                if current_price > ma_short > ma_mid:
                    support_score = 10
                elif current_price > ma_short:
                    support_score = 8
                elif current_price > ma_mid:
                    support_score = 6
                else:
                    support_score = 3
            else:
                support_score = 3
                
            total_score += support_score
            score_details.append(f"지지선: {support_score}점")
            
            # 🔥 5️⃣ 시장 상황 점수 (15점) - 기존 로직 유지
            market_timing = self.detect_market_timing()
            market_scores = {
                "strong_uptrend": 15, "uptrend": 12, "neutral": 9, 
                "downtrend": 6, "strong_downtrend": 3
            }
            market_score = market_scores.get(market_timing, 9)
            total_score += market_score
            score_details.append(f"시장({market_timing}): {market_score}점")
            
            # 🔥 6️⃣ 뉴스 점수 (±10점) - 기존 로직 유지
            news_decision = news_sentiment.get('decision', 'NEUTRAL')
            news_percentage = news_sentiment.get('percentage', 0)
            
            if news_decision == 'POSITIVE':
                news_score = 8 if news_percentage >= 70 else 5 if news_percentage >= 50 else 2
            elif news_decision == 'NEGATIVE':
                news_score = -8 if news_percentage >= 80 else -5 if news_percentage >= 60 else -2
            else:
                news_score = 0
                
            total_score += news_score
            if news_score != 0:
                score_details.append(f"뉴스({news_decision} {news_percentage}%): {news_score:+}점")
            
            return total_score, score_details
            
        except Exception as e:
            logger.error(f"개선된 종합 점수 계산 예외: {str(e)}")
            return 0, [f"예외발생: {str(e)[:50]}"]

    def should_buy_with_comprehensive_score(self, stock_code, position_num, indicators, 
                                        news_sentiment, magic_data_list, adjusted_conditions):
        """종합 점수 기반 매수 결정 - 🔥 설정 파일 우선 적용 버전 (하드코딩 제거)"""
        try:
            # 🔥 1단계: 동적 하락률 필수 검증 + 종합 점수 계산
            total_score, score_details = self.calculate_comprehensive_entry_score(
                stock_code, position_num, indicators, news_sentiment, magic_data_list
            )

            # 🔥 2단계: 실버 연동성 보너스 점수 추가 (NEW!)
            silver_bonus = self.calculate_silver_bonus_score(stock_code, indicators)
            total_score += silver_bonus

            if silver_bonus != 0:
                score_details.append(f"실버연동: {silver_bonus:+}점")

            # 🔥🔥🔥 핵심 개선: 설정 파일 우선, 하드코딩 완전 제거 🔥🔥🔥
            comprehensive_config = config.config.get('comprehensive_scoring', {})
            position_thresholds = comprehensive_config.get('position_thresholds', {})
            
            # 🔥 설정 파일에서 기준점수 직접 읽어오기 (하드코딩 ai_optimized_thresholds 제거)
            required_score = int(position_thresholds.get(str(position_num), 65))  # 기본값만 유지
            original_threshold = required_score  # 원본 저장
            
            # 🔥 AI 테마 보너스 적용 (기존 로직 유지하되 로그 메시지 개선)
            # stock_config = config.target_stocks.get(stock_code, {})
            # ai_theme_weight = stock_config.get('ai_theme_weight', 0)
            
            # ai_bonus = 0
            # if ai_theme_weight >= 0.25:  # AI 비중 25% 이상
            #     ai_bonus = 2  # 2점 추가 완화 (기준점을 낮춰주는 혜택)
            #     required_score -= ai_bonus  # 기준점수에서 차감하여 완화
            #     logger.info(f"🤖 {stock_code} AI 테마 보너스: 기준점 -{ai_bonus}점 완화 (AI비중 {ai_theme_weight*100:.0f}%)")

            # 🔥 3단계: 실버 강력 신호시 추가 임계값 완화 (NEW!)
            if silver_bonus >= 20:  # 실버 강력 신호
                required_score -= 5
                logger.info(f"🥈 {stock_code} 실버 강력 신호로 기준점 추가 -5점 완화")

            # 🔥 급락 방지 안전장치 (12% 이상 급락 시 기준 강화) - 기존 로직 유지
            current_price = indicators.get('current_price', 0)
            safety_penalty = 0
            if position_num > 1:
                prev_magic_data = magic_data_list[position_num - 2]  # 직전 차수
                if prev_magic_data['IsBuy'] and prev_magic_data['EntryPrice'] > 0:
                    prev_price = prev_magic_data['EntryPrice']
                    drop_rate = (prev_price - current_price) / prev_price
                    
                    if drop_rate > 0.12:  # 12% 이상 급락
                        safety_penalty = 5
                        required_score += safety_penalty
                        logger.info(f"⚠️ {stock_code} 급락 방지: {drop_rate*100:.1f}% 하락으로 기준 +{safety_penalty}점 강화")
            
            # 🔥 4단계: 최종 매수 결정
            decision = total_score >= required_score
            
            # 🔥 5단계: 기본 안전장치 (기존 유지)
            safety_check = (
                indicators['current_price'] > 0 and
                15 <= indicators['rsi'] <= 90
            )
            
            final_decision = decision and safety_check
            
            # 🔥 6단계: 상세 로깅 (설정 파일 우선 적용 정보 명확화)
            status = "✅ 매수" if final_decision else "❌ 대기"
            
            # 설정 적용 상태 표시
            config_source = "설정파일 우선"
            if silver_bonus >= 20:
                config_source += "+실버강화(-5점)"                
            if safety_penalty > 0:
                config_source += f" + 급락방지(+{safety_penalty}점)"
                
            logger.info(f"🎯 {stock_code} {position_num}차 종합점수 판단: {total_score}점/{required_score}점 ({config_source}) → {status}")
            
            for detail in score_details:
                logger.info(f"   📊 {detail}")
                
            if not safety_check:
                logger.info(f"   ⚠️ 안전장치: 가격={indicators['current_price']}, RSI={indicators['rsi']}")
            
            # 🔥 설정 파일 우선 적용 확인 로깅
            logger.info(f"   ⚙️ 설정파일 기준: {original_threshold}점 (smart_split_ai_config_us.json)")
            # if ai_bonus > 0:
            #     logger.info(f"   🤖 AI테마 완화: -{ai_bonus}점 → 최종 기준 {required_score}점")
            if safety_penalty > 0:
                logger.info(f"   ⚠️ 급락 방지: +{safety_penalty}점 → 최종 기준 {required_score}점")
            
            # 🔥 하락률 검증 정보 표시 (기존 로직 유지)
            if position_num > 1 and total_score > 0:
                logger.info(f"   🔗 순차 조건: {position_num-1}차 보유 + 동적 하락률 → ✅")
            elif position_num > 1:
                logger.info(f"   🔗 순차 조건: 동적 하락률 검증 실패 → ❌")
            
            return final_decision, f"종합점수 {total_score}/{required_score} ({config_source})"
            
        except Exception as e:
            logger.error(f"종합 매수 결정 중 오류: {str(e)}")
            return False, f"판단 오류: {str(e)}"

    def _preserve_sell_history_for_cooldown(self, stock_code, magic_data):
        """재매수 쿨다운용 매도 이력 보존 - 종목 레벨로 이동"""
        try:
            # 종목 데이터 찾기
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return
            
            # 🔥 종목 레벨 매도이력 구조 초기화
            if 'GlobalSellHistory' not in stock_data_info:
                stock_data_info['GlobalSellHistory'] = []
            
            # 🔥 기존 차수별 매도이력을 종목 레벨로 이동
            if magic_data.get('SellHistory'):
                for sell_record in magic_data['SellHistory']:
                    # 차수 정보 추가
                    global_sell_record = sell_record.copy()
                    global_sell_record['position_num'] = magic_data['Number']
                    global_sell_record['preserved_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    stock_data_info['GlobalSellHistory'].append(global_sell_record)
                    
                logger.info(f"📋 {stock_code} {magic_data['Number']}차 매도이력 {len(magic_data['SellHistory'])}건을 종목 레벨로 보존")
            
            # 🔥 부분매도 이력도 보존
            if magic_data.get('PartialSellHistory'):
                for partial_record in magic_data['PartialSellHistory']:
                    global_partial_record = partial_record.copy()
                    global_partial_record['position_num'] = magic_data['Number']
                    global_partial_record['preserved_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    global_partial_record['record_type'] = 'partial_sell'
                    
                    stock_data_info['GlobalSellHistory'].append(global_partial_record)
                    
                logger.info(f"📋 {stock_code} {magic_data['Number']}차 부분매도이력 {len(magic_data['PartialSellHistory'])}건을 종목 레벨로 보존")
            
        except Exception as e:
            logger.error(f"매도이력 보존 중 오류: {str(e)}")

    def get_next_available_position(self, magic_data_list):
        """다음 사용 가능한 차수 찾기"""
        try:
            for i, magic_data in enumerate(magic_data_list):
                # 빈 포지션 조건: IsBuy=False이고 CurrentAmt=0
                is_empty = (not magic_data.get('IsBuy', False) and 
                           magic_data.get('CurrentAmt', 0) == 0)
                
                if is_empty:
                    return i + 1  # 1-based 차수 반환
            
            return None  # 모든 차수 사용 중
            
        except Exception as e:
            logger.error(f"다음 사용 가능한 차수 찾기 중 오류: {str(e)}")
            return None

    def update_position_after_buy(self, stock_code, position_num, executed_amount, actual_price, magic_data_list):
        """매수 후 포지션 데이터 업데이트 - Version 2 기반 개선된 버전
        
        Args:
            stock_code: 종목 코드
            position_num: 원래 시도했던 차수 (무시됨 - 자동으로 올바른 차수 찾음)
            executed_amount: 실제 체결량
            actual_price: 실제 체결가
            magic_data_list: 종목의 MagicDataList
            
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        try:
            entry_date = datetime.now().strftime("%Y-%m-%d")
            
            # 🔥 1단계: 올바른 차수 결정 (핵심 개선)
            # position_num은 무시하고 자동으로 올바른 차수 찾기
            target_position_num = self.get_next_available_position(magic_data_list)
            
            if target_position_num is None:
                error_msg = f"❌ {stock_code} 모든 차수(1-5차) 사용 중 - 매수 불가"
                logger.error(error_msg)
                return False, error_msg
            
            target_magic_data = magic_data_list[target_position_num - 1]
            
            # 🔥 2단계: 재진입 vs 연속매수 정확한 판단 (기존 Version 2 로직 개선)
            is_reentry = False
            
            if target_position_num == 1:  # 1차수만 재진입 가능
                # 🔥 핵심 개선: 현재 활성 포지션 여부 먼저 확인
                is_currently_active = (target_magic_data.get('CurrentAmt', 0) > 0 and 
                                     target_magic_data.get('IsBuy', False))
                
                if not is_currently_active:  # 현재 비어있을 때만 재진입 검사
                    has_sell_history = len(target_magic_data.get('SellHistory', [])) > 0
                    has_partial_history = len(target_magic_data.get('PartialSellHistory', [])) > 0
                    original_amt = target_magic_data.get('OriginalAmt', 0)
                    
                    # 재진입 판단: 매도 이력 있고 + 기존 OriginalAmt > 새 매수량
                    if (has_sell_history or has_partial_history) and original_amt > executed_amount:
                        is_reentry = True
                        logger.info(f"🔄 {stock_code} {target_position_num}차 재진입 감지: {original_amt}주 → {executed_amount}주")
                else:
                    # 1차가 활성상태면 연속매수이므로 다음 빈 차수 사용
                    logger.info(f"📈 {stock_code} 1차 활성 포지션 존재 - {target_position_num}차에 연속매수")
            
            # 🔥 3단계: 빈 포지션 사용시 완전 초기화 (첫 번째 함수 로직 통합)
            was_empty_position = not target_magic_data.get('IsBuy', False)
            
            if was_empty_position:
                # 🔥 재매수 쿨다운용 이력 보존 (종목 레벨로 이동)
                if hasattr(self, '_preserve_sell_history_for_cooldown'):
                    self._preserve_sell_history_for_cooldown(stock_code, target_magic_data)
                
                # 🔥 완전 초기화 (첫 번째 함수의 핵심 로직)
                logger.info(f"🔄 {stock_code} {target_position_num}차 빈 포지션 재사용 - 완전 초기화 시작")
                
                # 이전 흔적들 완전 정리 (부분매도 이력 포함)
                target_magic_data['SellHistory'] = []
                target_magic_data['PartialSellHistory'] = []
                target_magic_data['PartialSellStage'] = 0
                target_magic_data['RemainingRatio'] = 1.0
                target_magic_data['MaxProfitBeforePartialSell'] = 0.0
                
                # 최고점 리셋
                max_profit_key = f'max_profit_{target_position_num}'
                if max_profit_key in target_magic_data:
                    target_magic_data[max_profit_key] = 0
                
                logger.info(f"✅ {stock_code} {target_position_num}차 이전 흔적 완전 정리 완료")
            
            # 🔥 재진입인 경우 추가 초기화 (두 번째 함수 로직 보완)
            if is_reentry:
                target_magic_data['OriginalAmt'] = executed_amount    # 새 기준
                target_magic_data['PartialSellStage'] = 0            # 초기화
                target_magic_data['RemainingRatio'] = 1.0            # 100%

                # 🔥 재진입시에도 최고점 초기화 추가 (IONQ 버그 수정)
                max_profit_key = f'max_profit_{target_position_num}'
                target_magic_data[max_profit_key] = 0

                logger.info(f"✅ {stock_code} {target_position_num}차 재진입 데이터 초기화 완료 (max_profit 포함)")

            # 🔥 4단계: 일반적인 매수 처리 (양쪽 함수 로직 통합)
            target_magic_data['IsBuy'] = True
            target_magic_data['EntryPrice'] = actual_price
            target_magic_data['CurrentAmt'] = executed_amount
            target_magic_data['EntryDate'] = entry_date
            target_magic_data['EntryAmt'] = executed_amount
            
            if not is_reentry and was_empty_position:
                target_magic_data['OriginalAmt'] = executed_amount  # 신규 진입
                target_magic_data['RemainingRatio'] = 1.0          # 100% 보유
                target_magic_data['PartialSellStage'] = 0          # 초기 상태
                
                # 🔥 신규 진입시 최고점도 초기화
                max_profit_key = f'max_profit_{target_position_num}'
                target_magic_data[max_profit_key] = 0
            
            # 🔥 5단계: 완료 로깅 (통합 버전)
            if is_reentry:
                action_type = "재진입"
                status_detail = "완전 초기화됨"
            elif was_empty_position:
                action_type = "빈포지션재사용"
                status_detail = "완전 초기화됨"
            else:
                action_type = "연속매수"
                status_detail = "기존 포지션 보존됨"
                
            logger.info(f"✅ {stock_code} {target_position_num}차 {action_type} 데이터 업데이트 완료")
            logger.info(f"   매수량: {executed_amount}주 @ ${actual_price:.2f}")
            logger.info(f"   진입일: {entry_date}")
            logger.info(f"   상태: {action_type} ({status_detail})")
            
            return True, None  # 🔥 기존 Version 2와 동일한 tuple 반환
            
        except Exception as e:
            error_msg = f"❌ {stock_code} 포지션 업데이트 중 오류: {str(e)}"
            logger.error(error_msg)
            return False, error_msg  # 🔥 기존 Version 2와 동일한 tuple 반환

    def validate_position_consistency(self):
        """포지션 데이터 일관성 검증"""
        try:
            issues = []
            
            for stock_data in self.split_data_list:
                stock_code = stock_data['StockCode']
                
                for magic_data in stock_data['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        current_amt = magic_data['CurrentAmt']
                        original_amt = magic_data.get('OriginalAmt', 0)
                        remaining_ratio = magic_data.get('RemainingRatio', 1.0)
                        position_num = magic_data['Number']
                        
                        # 🔍 불일치 감지
                        if original_amt > 0:
                            expected_ratio = current_amt / original_amt
                            if abs(remaining_ratio - expected_ratio) > 0.01:
                                issues.append({
                                    'stock': stock_code,
                                    'position': position_num,
                                    'issue': 'RemainingRatio 불일치',
                                    'current': remaining_ratio,
                                    'expected': expected_ratio
                                })
                        
                        if current_amt > 0 and original_amt == 0:
                            issues.append({
                                'stock': stock_code,
                                'position': position_num,
                                'issue': 'OriginalAmt가 0인데 CurrentAmt > 0',
                                'current_amt': current_amt
                            })
            
            if issues:
                logger.warning(f"⚠️ 포지션 데이터 불일치 {len(issues)}건 발견:")
                for issue in issues:
                    logger.warning(f"   {issue['stock']} {issue['position']}차: {issue['issue']}")
            else:
                logger.info("✅ 모든 포지션 데이터 일관성 확인")
                
            return len(issues) == 0
            
        except Exception as e:
            logger.error(f"데이터 일관성 검증 중 오류: {str(e)}")
            return False        

    def sync_broker_average_price_only(self, stock_code, magic_data_list):
        """브로커 평균단가만 동기화 (개별 진입가는 보존)"""
        try:
            time.sleep(1)  # API 반영 대기
            holdings = self.get_current_holdings(stock_code)
            broker_avg_price = holdings.get('avg_price', 0)
            broker_amount = holdings.get('amount', 0)
            
            if broker_avg_price > 0 and broker_amount > 0:
                # 🔥 전체 포지션에 대한 브로커 평균단가 정보를 별도 필드에 저장
                # (개별 차수의 EntryPrice는 건드리지 않음)
                
                # 종목 데이터에 브로커 정보 추가
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if stock_data_info:
                    stock_data_info['BrokerAvgPrice'] = broker_avg_price
                    stock_data_info['BrokerTotalAmount'] = broker_amount
                    stock_data_info['LastSyncTime'] = datetime.now().isoformat()
                    
                    logger.info(f"  💰 브로커 정보 동기화: {broker_amount}주 @ ${broker_avg_price:.2f}")
                    logger.info(f"  🔒 개별 차수 진입가 보존됨")
        
        except Exception as e:
            logger.error(f"브로커 평균단가 동기화 중 오류: {str(e)}")

    def calculate_position_return_with_broker_sync(self, magic_data, current_price, broker_avg_price, broker_amount, stock_code):
        """포지션별 수익률 계산 - 브로커 데이터 고려"""
        try:
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data['CurrentAmt']
            position_num = magic_data['Number']
            
            # 🔥 단일 포지션이고 브로커 평균가와 차이가 큰 경우 브로커 기준 사용
            total_internal = sum([m['CurrentAmt'] for m in self.get_stock_magic_data_list(stock_code) if m['IsBuy']])
            
            if (total_internal == broker_amount and 
                current_amount == broker_amount and 
                entry_price > 0 and
                abs(broker_avg_price - entry_price) / entry_price > 0.02):  # 2% 이상 차이
                
                effective_entry_price = broker_avg_price
                calculation_method = "브로커기준"
                
                logger.warning(f"⚠️ {stock_code} {position_num}차 평균단가 차이 감지:")
                logger.warning(f"   내부: ${entry_price:.2f} vs 브로커: ${broker_avg_price:.2f}")
                logger.warning(f"   → 브로커 평균단가로 수익률 계산")
            else:
                effective_entry_price = entry_price
                calculation_method = "내부기준"
            
            if effective_entry_price > 0:
                position_return_pct = (current_price - effective_entry_price) / effective_entry_price * 100
            else:
                position_return_pct = 0
                logger.warning(f"⚠️ {stock_code} {position_num}차 진입가가 0입니다")
            
            return position_return_pct, effective_entry_price, calculation_method
            
        except Exception as e:
            logger.error(f"포지션별 수익률 계산 중 오류: {str(e)}")
            return 0, entry_price, "오류"

    def get_stock_magic_data_list(self, stock_code):
        """종목의 MagicDataList 조회 헬퍼 함수"""
        try:
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    return data_info['MagicDataList']
            return []
        except Exception as e:
            logger.error(f"종목 데이터 조회 중 오류: {str(e)}")
            return []

    def check_position_discrepancies(self):
        """포지션 불일치 감지 및 알림 전용 함수"""
        try:
            target_stocks = config.target_stocks
            discrepancies = []
            
            for stock_code in target_stocks.keys():
                stock_name = target_stocks[stock_code].get('name', stock_code)
                
                # 🔍 브로커 실제 보유량 조회
                holdings = self.get_current_holdings(stock_code)
                broker_amount = holdings.get('amount', 0)
                broker_avg_price = holdings.get('avg_price', 0)
                broker_revenue_rate = holdings.get('revenue_rate', 0)
                
                # 🔍 봇 내부 관리 수량 계산
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if not stock_data_info:
                    if broker_amount > 0:
                        # 브로커에는 있는데 봇 데이터에 없음
                        discrepancies.append({
                            'type': 'missing_bot_data',
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'broker_amount': broker_amount,
                            'broker_avg_price': broker_avg_price,
                            'internal_amount': 0,
                            'difference': broker_amount,
                            'severity': 'HIGH'
                        })
                    continue
                
                # 🔍 내부 보유 수량 및 상세 분석
                internal_positions = []
                internal_total = 0
                total_investment = 0
                
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        position_info = {
                            'position': magic_data['Number'],
                            'amount': magic_data['CurrentAmt'],
                            'entry_price': magic_data['EntryPrice'],
                            'entry_date': magic_data.get('EntryDate', '날짜없음'),
                            'original_amount': magic_data.get('OriginalAmt', magic_data['CurrentAmt']),
                            'partial_stage': magic_data.get('PartialSellStage', 0),
                            'remaining_ratio': magic_data.get('RemainingRatio', 1.0)
                        }
                        internal_positions.append(position_info)
                        internal_total += magic_data['CurrentAmt']
                        total_investment += magic_data['EntryPrice'] * magic_data['CurrentAmt']
                
                # 내부 평균가 계산
                internal_avg_price = total_investment / internal_total if internal_total > 0 else 0
                
                # 🚨 불일치 감지
                if broker_amount != internal_total:
                    difference = broker_amount - internal_total
                    difference_pct = abs(difference) / max(broker_amount, internal_total, 1) * 100
                    
                    # 심각도 판정
                    if abs(difference) >= 10 or difference_pct >= 20:
                        severity = 'HIGH'
                    elif abs(difference) >= 5 or difference_pct >= 10:
                        severity = 'MEDIUM'
                    else:
                        severity = 'LOW'
                    
                    discrepancy_info = {
                        'type': 'quantity_mismatch',
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'broker_amount': broker_amount,
                        'broker_avg_price': broker_avg_price,
                        'broker_revenue_rate': broker_revenue_rate,
                        'internal_amount': internal_total,
                        'internal_avg_price': internal_avg_price,
                        'internal_positions': internal_positions,
                        'difference': difference,
                        'difference_pct': difference_pct,
                        'severity': severity,
                        'realized_pnl': stock_data_info.get('RealizedPNL', 0)
                    }
                    discrepancies.append(discrepancy_info)
                
                # 🔍 평균가 차이도 체크 (수량은 같지만 가격이 다른 경우)
                # elif broker_amount > 0 and internal_total > 0:
                #     if abs(broker_avg_price - internal_avg_price) / internal_avg_price > 0.05:  # 5% 이상 차이
                #         discrepancy_info = {
                #             'type': 'price_mismatch',
                #             'stock_code': stock_code,
                #             'stock_name': stock_name,
                #             'broker_amount': broker_amount,
                #             'broker_avg_price': broker_avg_price,
                #             'internal_amount': internal_total,
                #             'internal_avg_price': internal_avg_price,
                #             'internal_positions': internal_positions,
                #             'price_difference_pct': abs(broker_avg_price - internal_avg_price) / internal_avg_price * 100,
                #             'severity': 'MEDIUM'
                #         }
                #         discrepancies.append(discrepancy_info)
            
            # 🚨 불일치 발견 시 상세 알림
            if discrepancies:
                self.send_detailed_discrepancy_alert(discrepancies)
                return discrepancies
            else:
                logger.info("✅ 모든 종목의 보유 수량이 브로커와 일치합니다")
                return []
                
        except Exception as e:
            logger.error(f"포지션 불일치 감지 중 오류: {str(e)}")
            return []
        
    def send_detailed_discrepancy_alert(self, discrepancies):
        """상세한 불일치 알림 전송"""
        try:
            high_severity = [d for d in discrepancies if d['severity'] == 'HIGH']
            medium_severity = [d for d in discrepancies if d['severity'] == 'MEDIUM']
            low_severity = [d for d in discrepancies if d['severity'] == 'LOW']
            
            # 🚨 심각도별 알림 메시지 생성
            alert_msg = f"🚨 **포지션 불일치 감지** ({len(discrepancies)}개 종목)\n"
            alert_msg += f"⏰ 감지 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # 🔥 HIGH 심각도 (즉시 확인 필요)
            if high_severity:
                alert_msg += f"🚨 **HIGH 심각도** ({len(high_severity)}개) - 즉시 확인 필요!\n"
                for disc in high_severity:
                    alert_msg += self._format_discrepancy_detail(disc)
                    alert_msg += "\n"
            
            # ⚠️ MEDIUM 심각도 (조만간 확인 필요)
            if medium_severity:
                alert_msg += f"⚠️ **MEDIUM 심각도** ({len(medium_severity)}개) - 확인 권장\n"
                for disc in medium_severity:
                    alert_msg += self._format_discrepancy_detail(disc)
                    alert_msg += "\n"
            
            # 💡 LOW 심각도 (참고용)
            if low_severity:
                alert_msg += f"💡 **LOW 심각도** ({len(low_severity)}개) - 참고\n"
                for disc in low_severity:
                    alert_msg += self._format_discrepancy_detail(disc, brief=True)
            
            # 📋 권장 조치사항
            alert_msg += f"\n📋 **권장 조치사항**:\n"
            alert_msg += f"1. 브로커 앱에서 실제 보유량 확인\n"
            alert_msg += f"2. 최근 매매 내역과 봇 로그 대조\n"
            alert_msg += f"3. 심각한 불일치시 봇 일시 정지 고려\n"
            alert_msg += f"4. 수동 매매 여부 확인\n\n"
            alert_msg += f"🔒 **중요**: 봇은 자동 수정하지 않습니다"
            
            # Discord 알림 전송
            logger.warning(f"🚨 포지션 불일치 감지: {len(discrepancies)}개 종목")
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(alert_msg)
                
            # 상세 로그 기록
            for disc in discrepancies:
                logger.warning(f"  {disc['stock_name']}: {disc['type']} - {disc['severity']}")
                
        except Exception as e:
            logger.error(f"불일치 알림 전송 중 오류: {str(e)}")

    def _format_discrepancy_detail(self, disc, brief=False):
        """불일치 상세 정보 포맷팅"""
        try:
            msg = f"• **{disc['stock_name']} ({disc['stock_code']})**\n"
            
            if disc['type'] == 'quantity_mismatch':
                msg += f"  📊 브로커: {disc['broker_amount']}주 @ ${disc['broker_avg_price']:.2f}\n"
                msg += f"  🤖 봇관리: {disc['internal_amount']}주 @ ${disc.get('internal_avg_price', 0):.2f}\n"
                msg += f"  📉 차이: {disc['difference']:+}주 ({disc['difference_pct']:.1f}%)\n"
                
                if not brief and 'internal_positions' in disc:
                    msg += f"  📋 봇 내부 포지션:\n"
                    for pos in disc['internal_positions']:
                        stage_desc = f" (단계{pos['partial_stage']})" if pos['partial_stage'] > 0 else ""
                        msg += f"    {pos['position']}차: {pos['amount']}주 @ ${pos['entry_price']:.2f}{stage_desc}\n"
            
            elif disc['type'] == 'price_mismatch':
                msg += f"  💰 브로커 평균가: ${disc['broker_avg_price']:.2f}\n"
                msg += f"  🤖 봇 계산가: ${disc.get('internal_avg_price', 0):.2f}\n"
                msg += f"  📊 가격 차이: {disc['price_difference_pct']:.1f}%\n"
            
            elif disc['type'] == 'missing_bot_data':
                msg += f"  🚨 브로커: {disc['broker_amount']}주 보유\n"
                msg += f"  🤖 봇: 데이터 없음\n"
                msg += f"  ⚠️ 수동 매매 또는 데이터 유실 의심\n"
            
            return msg
            
        except Exception as e:
            return f"• {disc.get('stock_name', 'Unknown')}: 포맷팅 오류\n"  

    def process_trading(self):
        """SILVER 봇 3차수 매매 로직 처리 - AG + PAAS + HL 최적화 버전"""

        # 🔍 30분마다 불일치 감지 (수정하지 않음!)
        current_time = datetime.now()
        if not hasattr(self, 'last_discrepancy_check'):
            self.last_discrepancy_check = current_time
            # 시작 시 1회 체크
            discrepancies = self.check_position_discrepancies()
            if discrepancies:
                logger.warning(f"🚨 초기 불일치 감지: {len(discrepancies)}개 종목")
        else:
            time_diff = (current_time - self.last_discrepancy_check).total_seconds()
            if time_diff > 1800:  # 30분마다
                logger.info("🔍 정기 포지션 불일치 감지 실행")
                discrepancies = self.check_position_discrepancies()
                self.last_discrepancy_check = current_time

        if not hasattr(self, 'last_consistency_check'):
            self.last_consistency_check = current_time
            self.validate_position_consistency()  # 추가!
        else:
            time_diff = (current_time - self.last_consistency_check).total_seconds()
            if time_diff > 1800:  # 30분마다
                self.validate_position_consistency()  # 추가!
                self.last_consistency_check = current_time     

        # 매매 시작 전 전체 동기화 (30분마다)
        # current_time = datetime.now()
        # if not hasattr(self, 'last_full_sync_time'):
        #     self.last_full_sync_time = current_time
        #     self.sync_all_positions_with_broker()
        # else:
        #     time_diff = (current_time - self.last_full_sync_time).total_seconds()
        #     if time_diff > 1800:  # 30분마다
        #         logger.info("🔄 SILVER 봇 정기 전체 포지션 동기화 실행")
        #         self.sync_all_positions_with_broker()
        #         self.last_full_sync_time = current_time
        
        # 🔥 미국 마켓 오픈 상태 확인
        is_market_open = SafeKisUS.safe_is_market_open()
        
        if not is_market_open:
            logger.info("미국 시장이 열리지 않았습니다.")
            for stock_info in self.split_data_list:
                stock_info['IsReady'] = True
            self.save_split_data()
            return

        # 🔥 1. 매매 시작 전 미체결 주문 체크
        self.check_and_manage_pending_orders()

        # 🔥 개선된 비상 손절 체크
        if self.check_emergency_conditions():
            return  # 매매 중단
        
        # 🔥 동적 예산 업데이트
        self.update_budget()
        
        # 🔥 뉴스 분석 (캐시 기반으로 최적화 - API 비용 절약)
        try:
            if NEWS_ANALYSIS_AVAILABLE:
                # 먼저 캐시된 뉴스 확인 (240분 유효)
                news_summary = self.get_cached_news_summary()
                
                if news_summary is None:
                    # 캐시가 없거나 만료된 경우만 새로운 API 호출
                    logger.info("📰 SILVER 봇 뉴스 API 호출 - 새로운 분석 수행")
                    news_summary = self.analyze_all_stocks_news()
                    self.cache_news_summary(news_summary)
                    
                    # API 호출 알림 (비용 모니터링용)
                    api_call_msg = f"💰 SILVER 봇 뉴스 API 호출됨 - {datetime.now().strftime('%H:%M:%S')}"
                    logger.warning(api_call_msg)
                    
                else:
                    # 캐시된 결과 사용 (API 비용 절약)
                    logger.info("📰 SILVER 봇 캐시된 뉴스 분석 결과 사용 (API 비용 절약)")
            else:
                news_summary = {}
                logger.info("📰 뉴스 분석 모듈 비활성화, 기존 방식으로 진행")
        except Exception as e:
            logger.warning(f"뉴스 분석 실패, 기존 방식으로 진행: {str(e)}")
            news_summary = {}
        
        # 각 종목별 처리 - config 사용 (SILVER 봇에서는 기존 config 객체 사용)
        target_stocks = config.target_stocks

        for stock_code, stock_info in target_stocks.items():
            try:
                
                # 🔥 매도 후 쿨다운 체크 (매매 로직 시작 전)
                if not self.check_post_sell_cooldown(stock_code):
                    logger.info(f"⏳ {stock_code} 매도 후 쿨다운 중 - 매수 스킵")
                    continue
                
                # 🔥 일일 거래 한도 체크
                if not self.check_dynamic_daily_buy_limit(stock_code):    
                    logger.info(f"📊 {stock_code} 일일 거래 한도 도달 - 매수 스킵")
                    continue

                # 🔥 뉴스 감정 분석 결과 가져오기
                news_sentiment = news_summary.get(stock_code, {})
                news_decision = news_sentiment.get('decision', 'NEUTRAL')
                news_percentage = news_sentiment.get('percentage', 0)
                
                # 종목 특성에 따른 최적의 기간 결정
                period, recent_period, recent_weight = self.determine_optimal_period(stock_code)
                
                # 가중치를 적용한 기술적 지표 계산
                indicators = self.get_technical_indicators_weighted(
                    stock_code, 
                    period=period, 
                    recent_period=recent_period, 
                    recent_weight=recent_weight
                )
                
                if not indicators:
                    continue
                
                # 현재 보유 정보 조회
                holdings = self.get_current_holdings(stock_code)
                
                # 첫 실행 시 종목 데이터 생성
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                # 🔥 종목 데이터가 없으면 새로 생성 (3차수용)
                if stock_data_info is None:
                    magic_data_list = []
                    
                    # 🔥 3차수로 변경 (기존 5차수에서)
                    for i in range(3):  # 5 → 3으로 변경
                        magic_data_list.append({
                            'Number': i + 1,
                            'EntryPrice': 0,
                            'EntryAmt': 0,
                            'CurrentAmt': 0,
                            'SellHistory': [],
                            'EntryDate': '',
                            'IsBuy': False,
                            'OriginalAmt': 0,
                            'PartialSellHistory': [],
                            'PartialSellStage': 0,
                            'RemainingRatio': 0.0,
                            'MaxProfitBeforePartialSell': 0.0
                        })
                    
                    stock_data_info = {
                        'StockCode': stock_code,
                        'StockName': stock_info['name'],
                        'IsReady': True,
                        'GlobalSellHistory': [],  # 🔧 새로 추가된 필드
                        'MagicDataList': magic_data_list,
                        'RealizedPNL': 0,
                        'MonthlyPNL': {},
                        'max_profit': 0
                    }
                    
                    self.split_data_list.append(stock_data_info)
                    self.save_split_data()
                    
                    msg = f"🤖 {stock_code} SILVER 봇 3차수 투자 준비 완료!!"
                    logger.info(msg)
                    if config.config.get("use_discord_alert", True):
                        discord_alert.SendMessage(msg)
                
                # 🔥 개선된 3차수 분할 매수 로직
                magic_data_list = stock_data_info['MagicDataList']
                total_budget = self.total_money * stock_info['weight']
                
                # 🔥 종목별 매수 조건 설정값 가져오기
                stock_config = target_stocks.get(stock_code, {})
                min_pullback = stock_config.get('min_pullback', 3.5)
                max_rsi_buy = stock_config.get('max_rsi_buy', 62)
                min_green_candle = stock_config.get('min_green_candle', 1.003)
                trend_requirement = stock_config.get('trend_requirement', False)
                
                base_conditions = {
                    'min_pullback': min_pullback,
                    'max_rsi_buy': max_rsi_buy,
                    'green_candle_req': min_green_candle,
                    'position_limit': 3  # 🔥 3차수로 제한
                }

                adjusted_conditions, adjustment_desc = self.get_news_adjusted_buy_conditions(
                    stock_code, base_conditions, news_sentiment
                )

                # 조정된 조건들 적용
                news_adjusted_pullback = adjusted_conditions['min_pullback']
                news_adjusted_rsi = adjusted_conditions['max_rsi_buy']
                news_adjusted_candle = adjusted_conditions['green_candle_req']
            
                # 🔥 전역 설정값
                rsi_lower = config.config.get('rsi_lower_bound', 25)
                rsi_upper = config.config.get('rsi_upper_bound', 75)
                
                # 🔥 3차수용 점진적 매수 간격 설정
                progressive_drops = config.config.get('progressive_buy_drops', {
                    "2": 0.10, "3": 0.18
                })
                
                # 시장 상황에 따른 포지션 크기 조정
                market_timing = self.detect_market_timing()
                position_multiplier = 1.0
                
                if market_timing == "strong_downtrend":
                    position_multiplier = 0.5
                    logger.info(f"{stock_code} 강한 하락장 감지: 포지션 크기 50% 축소")
                elif market_timing == "downtrend":
                    position_multiplier = 0.7
                    logger.info(f"{stock_code} 하락장 감지: 포지션 크기 30% 축소")
                elif market_timing == "strong_uptrend":
                    position_multiplier = 1.2
                    logger.info(f"{stock_code} 강한 상승장 감지: 포지션 크기 20% 확대")
                
                # 🔥 시장 상황별 포지션 제한 (3차수 기준)
                market_limits = config.config.get('market_position_limits', {
                    'strong_downtrend': 1, 'downtrend': 2, 'neutral': 2,
                    'uptrend': 3, 'strong_uptrend': 3
                })
                max_allowed_position = market_limits.get(market_timing, 2)
                
                # 🔥 매수 쿨다운 설정
                buy_control = config.config.get('buy_control', {})
                enable_cooldown = buy_control.get('enable_cooldown', False)
                cooldown_days = buy_control.get('cooldown_days', [0, 1, 2])  # 3차수용
                max_daily_buys = buy_control.get('max_daily_buys', 3)
                
                # 🔥 일일 매수 횟수 체크
                today = datetime.now().strftime("%Y-%m-%d")
                daily_buy_count = 0
                for magic_data in magic_data_list:
                    if magic_data['IsBuy'] and magic_data.get('EntryDate') == today:
                        daily_buy_count += 1
                
                if daily_buy_count >= max_daily_buys:
                    logger.info(f"{stock_code} 일일 매수 한도 도달: {daily_buy_count}/{max_daily_buys}")
                    continue

                # 🔥🔥🔥 개선된 각 차수별 매수 조건 체크 (3차수용) 🔥🔥🔥
                buy_executed_this_cycle = False
                
                # 🔥 3차수만 체크하도록 변경
                for i, magic_data in enumerate(magic_data_list):
                    if not magic_data['IsBuy'] and i < 3:  # 0, 1, 2 (1차, 2차, 3차)
                        
                        position_num = i + 1
                        
                        # 🔥 시장 상황 기반 포지션 제한 체크
                        if position_num > max_allowed_position:
                            logger.info(f"{stock_code} {position_num}차 매수 제한: 시장상황 (최대 {max_allowed_position}차수)")
                            continue

                        # 🔥 매수 쿨다운 체크
                        if enable_cooldown and i < len(cooldown_days):
                            if magic_data.get('EntryDate'):
                                try:
                                    last_buy = datetime.strptime(magic_data['EntryDate'], "%Y-%m-%d")
                                    days_passed = (datetime.now() - last_buy).days
                                    required_days = cooldown_days[i]
                                    
                                    if days_passed < required_days:
                                        logger.info(f"{stock_code} {position_num}차 매수 쿨다운: {days_passed}/{required_days}일")
                                        continue
                                except Exception as e:
                                    logger.warning(f"{stock_code} {position_num}차 쿨다운 날짜 파싱 오류: {str(e)}")
                        
                        # 🔥 1차수 재진입 조건 체크
                        if position_num == 1:
                            reentry_allowed, reentry_reason = self.check_reentry_conditions(stock_code, indicators)
                            if not reentry_allowed:
                                logger.info(f"🚫 {stock_code} 1차 매수 차단: {reentry_reason}")
                                continue
                        
                        # 🚀🚀🚀 새로운 종합 점수 기반 매수 결정 🚀🚀🚀
                        should_buy, buy_reason = self.should_buy_with_comprehensive_score(
                            stock_code, position_num, indicators, news_sentiment, magic_data_list, adjusted_conditions
                        )
                        
                        # 🔥 3차수용 투자 비중 설정 (역피라미드)
                        if position_num == 1:
                            investment_ratio = 0.40 * position_multiplier  # 40%
                        elif position_num == 2:
                            investment_ratio = 0.35 * position_multiplier  # 35%
                        else:  # 3차수
                            investment_ratio = 0.25 * position_multiplier  # 25%
                        
                        # 🔥🔥🔥 매수 실행 로직 🔥🔥🔥
                        if should_buy:
                            logger.info(f"💰 {stock_code} {position_num}차 매수 진행 - SILVER 봇 3차수 시스템")
                            
                            safety_check = (
                                indicators['current_price'] > 0 and
                                15 <= indicators['rsi'] <= 90
                            )
                            
                            if safety_check:
                                invest_amount = total_budget * investment_ratio
                                buy_amt = max(1, int(invest_amount / indicators['current_price']))

                                # 🔥🔥🔥 신규 추가: 매수 전 예산 체크 🔥🔥🔥
                                can_buy, budget_reason = self.check_budget_before_buy(
                                    stock_code, buy_amt, indicators['current_price']
                                )
                                
                                if not can_buy:
                                    logger.warning(f"🚫 {stock_code} {position_num}차 매수 차단: {budget_reason}")
                                    continue  # 다음 차수나 다음 종목으로 이동
                                
                                logger.info(f"✅ {stock_code} {position_num}차 예산 체크 통과: {budget_reason}")
                                # 🔥🔥🔥 예산 체크 끝 🔥🔥🔥

                                estimated_fee = self.calculate_trading_fee(indicators['current_price'], buy_amt, True)
                                total_cost = (indicators['current_price'] * buy_amt) + estimated_fee
                                
                                balance = SafeKisUS.safe_get_balance("USD")
                                remain_money = float(balance.get('RemainMoney', 0))
                                
                                # 🔥 SILVER 봇 전용 현금 여유 체크
                                minimum_reserve = config.config.get('minimum_cash_reserve', 300)
                                available_cash = remain_money - minimum_reserve
                                
                                logger.info(f"  💰 필요 자금: ${total_cost:.2f}, 가용 현금: ${available_cash:.2f}")
                                
                                if total_cost <= available_cash:
                                    # 🔥 개선된 매수 처리 (체결 확인 포함)
                                    actual_price, executed_amount, message = self.handle_buy_with_execution_tracking(
                                        stock_code, buy_amt, indicators['current_price']
                                    )
                                    
                                    if actual_price and executed_amount:
                                        # 🔥🔥🔥 SILVER 봇 3차수 데이터 업데이트 🔥🔥🔥
                                        logger.info(f"🔄 {stock_code} {position_num}차 SILVER 봇 매수 데이터 업데이트 시작")
                                        
                                        try:
                                            # 🔥 3차수 전용 업데이트 함수 사용
                                            update_success, backup_data = self.update_position_after_buy(
                                                stock_code, position_num, executed_amount, actual_price, magic_data_list
                                            )
                                            
                                            if update_success:
                                                logger.info(f"  📊 SILVER 봇 업데이트: {executed_amount}주 @ ${actual_price:.2f}")
                                                
                                                # 저장 시도
                                                self.save_split_data()
                                                logger.info(f"  💾 {stock_code} {position_num}차 SILVER 봇 데이터 저장 완료")
                                                
                                                # 검증
                                                verification_ok = self.verify_after_trade(stock_code, f"{position_num}차 매수")
                                                if not verification_ok:
                                                    logger.warning(f"  ⚠️ {stock_code} {position_num}차 매수 후 검증 실패 (하지만 진행)")
                                                
                                                # 성공 메시지
                                                msg = f"🤖 {stock_code} SILVER 봇 {buy_reason}!\n"
                                                msg += f"  수량: {executed_amount}주 @ ${actual_price:.2f}\n"
                                                msg += f"  투자비중: {investment_ratio*100:.1f}% ({position_num}차)\n"
                                                msg += f"  차수시스템: 3차수 집중 투자\n"
                                                
                                                # 가격 개선 정보 추가
                                                price_diff = actual_price - indicators['current_price']
                                                if abs(price_diff) > 0.01:
                                                    msg += f"  가격개선: ${price_diff:+.2f}\n"
                                                
                                                msg += f"  🎯 AI 테마 고점권 대응 전략!"
                                                
                                                logger.info(msg)
                                                if config.config.get("use_discord_alert", True):
                                                    discord_alert.SendMessage(msg)
                                                
                                                buy_executed_this_cycle = True
                                                break  # 매수 성공으로 루프 종료
                                            
                                            else:
                                                logger.error(f"  ❌ {stock_code} {position_num}차 SILVER 봇 데이터 업데이트 실패")
                                                continue
                                            
                                        except Exception as update_e:
                                            logger.error(f"  ❌ {stock_code} {position_num}차 SILVER 봇 데이터 업데이트 중 오류: {str(update_e)}")
                                            
                                            # 백업이 있으면 롤백 실행
                                            if 'backup_data' in locals():
                                                try:
                                                    # 🔥 원래 차수에 롤백
                                                    target_magic_data = magic_data_list[position_num - 1]
                                                    target_magic_data['IsBuy'] = backup_data['IsBuy']
                                                    target_magic_data['EntryPrice'] = backup_data['EntryPrice']
                                                    target_magic_data['EntryAmt'] = backup_data['EntryAmt']
                                                    target_magic_data['CurrentAmt'] = backup_data['CurrentAmt']
                                                    target_magic_data['EntryDate'] = backup_data['EntryDate']
                                                    logger.warning(f"  🔄 {stock_code} {position_num}차 SILVER 봇 롤백 완료")
                                                except:
                                                    logger.error(f"  💥 {stock_code} {position_num}차 SILVER 봇 롤백도 실패")
                                            continue
                                    
                                    else:
                                        # 매수 실패 (체결 실패)
                                        logger.warning(f"❌ {stock_code} {position_num}차 SILVER 봇 매수 실패: {message}")
                                        if "가격 급등" in message:
                                            logger.info(f"  💡 {stock_code} 가격 급등으로 인한 매수 포기는 정상적인 보호 기능입니다")
                                    
                                else:
                                    logger.warning(f"❌ {stock_code} SILVER 봇 매수 자금 부족: 필요 ${total_cost:.2f} vs 가용 ${available_cash:.2f}")
                            else:
                                logger.warning(f"❌ {stock_code} 안전장치 실패: 가격={indicators['current_price']}, RSI={indicators['rsi']}")
                
                # 🔥 차수별 수익보존 매도 로직 (3차수 최적화)
                if holdings['amount'] > 0:
                    
                    # 수량 동기화 체크
                    internal_total = sum([magic_data['CurrentAmt'] for magic_data in magic_data_list if magic_data['IsBuy']])
                    
                    if abs(internal_total - holdings['amount']) > 0:
                        logger.warning(f"{stock_code} SILVER 봇 수량 불일치 감지: 내부관리={internal_total}, API조회={holdings['amount']}")
                        # if internal_total > 0:
                        #     sync_ratio = holdings['amount'] / internal_total
                        #     for magic_data in magic_data_list:
                        #         if magic_data['IsBuy']:
                        #             magic_data['CurrentAmt'] = int(magic_data['CurrentAmt'] * sync_ratio)
                        #     logger.info(f"{stock_code} SILVER 봇 수량 동기화 완료: 비율={sync_ratio:.3f}")
                        #     self.save_split_data()

                        # ✅ 새로운 안전한 코드 (바로 교체)
                        if internal_total != holdings['amount']:
                            logger.warning(f"⚠️ {stock_code} AI봇 수량 불일치 감지: 내부관리={internal_total}, API조회={holdings['amount']}")
                            logger.warning(f"🤖 {stock_code} AI봇 수동 확인이 필요할 수 있습니다.")
                            # ❌ sync_ratio 계산 및 CurrentAmt 자동 수정 완전 제거
                        else:
                            logger.debug(f"✅ {stock_code} AI봇 수량 일치 확인: {internal_total}주")                        
                    
                    # 🔥 차수별 개별 매도 처리 (기존 함수 사용)
                    sells_executed = self.process_position_wise_selling(
                        stock_code, indicators, magic_data_list, news_decision, news_percentage
                    )
                    
                    # 매도 실행 여부만 로깅
                    if sells_executed:
                        logger.info(f"🎯 {stock_code} SILVER 봇 3차수 매도 전략 실행 완료")
                    else:
                        # 매도가 없었을 때의 현재 상태 간단 로깅
                        total_positions = sum([magic_data['CurrentAmt'] for magic_data in magic_data_list if magic_data['IsBuy']])
                        if total_positions > 0:
                            logger.debug(f"💎 {stock_code} SILVER 봇 전체 {total_positions}주 홀딩 유지")

                # 🔥 간단한 API 호출 간격 추가
                time.sleep(0.5)  # 0.5초 대기
                
            except Exception as e:
                logger.error(f"{stock_code} SILVER 봇 처리 중 오류 발생: {str(e)}")
                import traceback
                traceback.print_exc()

    def get_emergency_config(self):
        """비상 손절 설정 가져오기"""
        emergency_config = config.config.get('emergency_config', {})
        
        return {
            'total_loss_limit': emergency_config.get('total_loss_limit', 0.20),
            'consecutive_stop_limit': emergency_config.get('consecutive_stop_limit', 3),
            'monitoring_days': emergency_config.get('monitoring_days', 7)
        }

    def check_emergency_conditions(self):
        """설정 기반 비상 조건 체크"""
        emergency_settings = self.get_emergency_config()
        
        emergency_loss_limit = emergency_settings['total_loss_limit']
        consecutive_limit = emergency_settings['consecutive_stop_limit']
        monitoring_days = emergency_settings['monitoring_days']
        
        if config.initial_total_asset > 0:
            balance = SafeKisUS.safe_get_balance("USD")
            current_total = float(balance.get('TotalMoney', 0))
            loss_ratio = (config.initial_total_asset - current_total) / config.initial_total_asset
            
            # 연속 손절 체크
            recent_stop_count = self.count_recent_stop_losses(days=monitoring_days)
            
            emergency_triggered = False
            emergency_reason = ""
            
            # 총 손실 한도
            if loss_ratio > emergency_loss_limit:
                emergency_triggered = True
                emergency_reason = f"총 손실 한도 초과: {loss_ratio*100:.1f}% > {emergency_loss_limit*100:.1f}%"
            
            # 연속 손절 한도
            elif recent_stop_count >= consecutive_limit:
                emergency_triggered = True
                emergency_reason = f"연속 손절 한도 초과: 최근 {monitoring_days}일간 {recent_stop_count}개 종목 손절"
            
            if emergency_triggered:
                msg = f"🚨🚨🚨 설정 기반 비상 정지 발동 🚨🚨🚨\n"
                msg += f"📊 정지 사유: {emergency_reason}\n"
                msg += f"💰 현재 총 손실률: {loss_ratio*100:.1f}%\n"
                msg += f"⚙️ 설정값: 손실한도 {emergency_loss_limit*100:.0f}%, 연속손절 {consecutive_limit}회\n"
                msg += f"🛑 모든 자동 매매 활동 중단"
                
                logger.error(msg)
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(msg)
                return True
        
        return False

    def get_dynamic_trailing_drop(self, max_profit_pct, stock_code=""):
        """🔥 AI 테마 특화 동적 트레일링 간격 계산 - 더 빠른 반응"""
        try:
            # 🎯 AI 테마 특화: 변동성이 크므로 더 세밀한 구간 설정
            if max_profit_pct >= 40:        # 40% 이상 AI 초대박
                trailing_drop = 0.02        # 2% 트레일링 (매우 타이트)
                grade = "AI초대박"
            elif max_profit_pct >= 25:      # 25~40% AI 대박
                trailing_drop = 0.025       # 2.5% 트레일링
                grade = "AI대박"
            elif max_profit_pct >= 18:      # 18~25% AI 높은 수익
                trailing_drop = 0.03        # 3% 트레일링  
                grade = "AI높은수익"
            elif max_profit_pct >= 12:      # 12~18% AI 좋은 수익
                trailing_drop = 0.035       # 3.5% 트레일링
                grade = "AI좋은수익"
            elif max_profit_pct >= 8:       # 8~12% AI 일반 수익
                trailing_drop = 0.04        # 4% 트레일링
                grade = "AI일반수익"
            elif max_profit_pct >= 4:       # 4~8% AI 소폭 수익
                trailing_drop = 0.045       # 4.5% 트레일링
                grade = "AI소폭수익"
            else:                           # 4% 미만
                trailing_drop = 0.05        # 5% 트레일링
                grade = "AI저수익"
            
            logger.info(f"🤖 {stock_code} AI 동적트레일링: {max_profit_pct:.1f}% → {trailing_drop*100:.1f}% 간격 ({grade})")
            
            return trailing_drop
            
        except Exception as e:
            logger.error(f"AI 동적 트레일링 계산 오류: {str(e)}")
            return 0.04  # AI 기본값 4% 반환    

    def check_hybrid_protection(self, stock_code, magic_data, current_price, position_return_pct, position_max):
        """하이브리드 보호 시스템 체크 - 🔥 LIFO 우선순위 추가"""
        try:
            stock_config = config.target_stocks.get(stock_code, {})
            partial_config = stock_config.get('partial_sell_config', {})
            hybrid_config = partial_config.get('hybrid_protection', {})
            
            if not hybrid_config.get('enable', False):
                return {'action': 'hold', 'reason': '하이브리드 보호 비활성화'}
            
            current_amount = magic_data['CurrentAmt']
            current_stage = magic_data.get('PartialSellStage', 0)
            min_quantity = hybrid_config.get('min_quantity_for_partial', 2)
            current_position_num = magic_data['Number']
            
            # 🔥🔥🔥 새로 추가: LIFO 우선순위 체크 🔥🔥🔥
            # 더 최근 차수가 있는지 확인
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if stock_data_info:
                # 더 높은 차수(최근 진입)가 활성인지 확인
                for other_magic_data in stock_data_info['MagicDataList']:
                    if (other_magic_data['IsBuy'] and 
                        other_magic_data['CurrentAmt'] > 0 and 
                        other_magic_data['Number'] > current_position_num):
                        
                        # 더 최근 차수의 상황 확인
                        other_entry_price = other_magic_data['EntryPrice']
                        other_return_pct = (current_price - other_entry_price) / other_entry_price * 100
                        
                        # 더 최근 차수가 거의 손실 없으면 트레일링 금지
                        if other_return_pct > -2.0:  # -2% 이상이면 우선순위 준수
                            logger.info(f"🚫 {stock_code} {current_position_num}차 트레일링 금지: "
                                    f"{other_magic_data['Number']}차 LIFO 우선순위 "
                                    f"({other_return_pct:+.1f}% > -2.0%)")
                            return {'action': 'hold', 'reason': 'LIFO 우선순위 준수'}
            
            # 🔥🔥🔥 새로 추가: 손실 상태 트레일링 금지 🔥🔥🔥
            if position_return_pct < 0:
                logger.info(f"🚫 {stock_code} {current_position_num}차 트레일링 금지: "
                        f"현재 손실 상태 ({position_return_pct:+.1f}%)")
                return {'action': 'hold', 'reason': '손실 상태 트레일링 금지'}
            
            # 기존 로직 그대로 유지 (변경 없음)
            min_profit_for_trailing = hybrid_config.get('min_profit_for_trailing', 3)
            
            # 1단계: 부분매도 조건 (기존 유지)
            if current_stage == 0 and current_amount >= min_quantity:
                first_threshold = partial_config.get('first_sell_threshold', 12)
                first_ratio = partial_config.get('first_sell_ratio', 0.3)
                
                if position_return_pct >= first_threshold:
                    return {
                        'action': 'partial_sell',
                        'sell_ratio': first_ratio,
                        'reason': f'1차 개선된 부분매도 ({first_threshold}% 달성)',
                        'type': 'smart_partial'
                    }
            
            # 2단계: 부분매도 후 동적 트레일링 (기존 유지)
            elif current_stage >= 1:
                dynamic_trailing_drop = self.get_dynamic_trailing_drop(position_max, stock_code)
                
                if (position_return_pct > min_profit_for_trailing and
                    position_max > min_profit_for_trailing + 2 and
                    position_return_pct <= position_max - (dynamic_trailing_drop * 100)):
                    
                    return {
                        'action': 'post_partial_trailing',
                        'sell_ratio': 1.0,
                        'reason': f'동적트레일링 (최고{position_max:.1f}%→{dynamic_trailing_drop*100:.1f}%하락)',
                        'type': 'post_partial_trailing'
                    }
            
            # 3단계: 응급 트레일링 (기존 유지)
            elif current_stage == 0:
                emergency_enable = hybrid_config.get('emergency_trailing_enable', True)
                min_profit_threshold = hybrid_config.get('emergency_max_profit_threshold', 12)
                
                base_emergency_drop = hybrid_config.get('emergency_trailing_drop', 0.08)
                dynamic_emergency_drop = max(base_emergency_drop, self.get_dynamic_trailing_drop(position_max, stock_code) + 0.01)
                
                condition_1 = emergency_enable
                condition_2 = position_return_pct > min_profit_for_trailing
                condition_3 = position_max >= min_profit_threshold
                condition_4 = position_return_pct <= position_max - (dynamic_emergency_drop * 100)
                
                if all([condition_1, condition_2, condition_3, condition_4]):
                    return {
                        'action': 'emergency_trailing',
                        'sell_ratio': 1.0,
                        'reason': f'응급트레일링 (최고{position_max:.1f}%→{dynamic_emergency_drop*100:.1f}%하락)',
                        'type': 'emergency_trailing'
                    }
            
            return {'action': 'hold', 'reason': '하이브리드 조건 미충족'}
            
        except Exception as e:
            logger.error(f"하이브리드 보호 체크 오류: {str(e)}")
            return {'action': 'hold', 'reason': f'오류: {str(e)}'}

    def calculate_realistic_sell_amount(self, current_amount, sell_ratio, action_type):
        """현실적 매도 수량 계산 - 최소 단위 및 잔여 보장"""
        
        try:
            if action_type in ['post_partial_trailing', 'emergency_trailing']:
                # 트레일링은 전량매도
                return current_amount
            
            # 부분매도의 경우
            calculated_amount = int(current_amount * sell_ratio)
            
            # 최소 1주 매도, 최소 1주 보유 보장
            min_sell = 1
            min_remaining = 1
            
            # 현실적 조정
            if calculated_amount < min_sell:
                calculated_amount = min_sell
            
            if current_amount - calculated_amount < min_remaining:
                # 남을 수량이 1주 미만이면 전량매도
                calculated_amount = current_amount
            
            # 최종 검증
            if calculated_amount > current_amount:
                calculated_amount = current_amount
            
            if calculated_amount <= 0:
                return 0
                
            logger.info(f"  📊 현실적 수량 조정: {current_amount}주 × {sell_ratio:.1f} = {int(current_amount * sell_ratio)}주 → {calculated_amount}주")
            
            return calculated_amount
            
        except Exception as e:
            logger.error(f"현실적 매도 수량 계산 중 오류: {str(e)}")
            return 0

    def process_hybrid_sell_record(self, stock_code, magic_data, sell_amount, current_price, position_return_pct, hybrid_action):
        """하이브리드 매도 기록 처리 - 🔥 RealizedPNL 업데이트 로직 추가"""
        
        try:
            position_num = magic_data['Number']
            entry_price = magic_data['EntryPrice']
            remaining_amount = magic_data['CurrentAmt'] - sell_amount
            is_full_sell = (remaining_amount <= 0)
            
            # 🔥🔥🔥 추가: 실현손익 계산 및 업데이트 🔥🔥🔥
            position_pnl = (current_price - entry_price) * sell_amount
            sell_fee = self.calculate_trading_fee(current_price, sell_amount, False)
            net_pnl = position_pnl - sell_fee
            
            # 🔥 종목별 실현손익에 추가 (누락되었던 핵심 로직!)
            for stock_data in self.split_data_list:
                if stock_data['StockCode'] == stock_code:
                    stock_data['RealizedPNL'] += net_pnl
                    logger.info(f"💰 {stock_code} RealizedPNL 업데이트: ${stock_data['RealizedPNL']:.2f} (${net_pnl:+.2f} 추가)")
                    break
            
            # 🔥 매도 기록 생성
            sell_record = {
                'date': datetime.now().strftime("%Y-%m-%d"),
                'time': datetime.now().strftime("%H:%M:%S"),
                'price': current_price,
                'amount': sell_amount,
                'reason': f"{position_num}차 {hybrid_action['reason']}",
                'return_pct': position_return_pct,
                'hybrid_type': hybrid_action['type']
            }
            
            if is_full_sell:
                # 전량매도 처리
                magic_data['SellHistory'].append(sell_record)
                magic_data['CurrentAmt'] = 0
                magic_data['IsBuy'] = False
                magic_data['RemainingRatio'] = 0.0
                magic_data['PartialSellStage'] = 3
                
                # 최고점 리셋
                max_profit_key = f'max_profit_{position_num}'
                magic_data[max_profit_key] = 0
                
            else:
                # 부분매도 처리
                magic_data['CurrentAmt'] = remaining_amount
                
                # 기존 부분매도 시스템과 호환되도록 PartialSellHistory에도 기록
                partial_record = sell_record.copy()
                partial_record['remaining_amount'] = remaining_amount
                partial_record['is_full_sell'] = False
                partial_record['sell_ratio'] = sell_amount / (sell_amount + remaining_amount)
                partial_record['stage'] = hybrid_action.get('stage', magic_data.get('PartialSellStage', 0) + 1)
                
                magic_data['PartialSellHistory'].append(partial_record)
                
                # PartialSellStage 업데이트
                if hybrid_action['type'] == 'smart_partial':
                    magic_data['PartialSellStage'] = hybrid_action.get('stage', 1)
                
                # RemainingRatio 업데이트
                original_amt = magic_data.get('OriginalAmt', sell_amount + remaining_amount)
                magic_data['RemainingRatio'] = remaining_amount / original_amt if original_amt > 0 else 0
            
            # 🔥 GlobalSellHistory에도 기록 (기존 로직 유지)
            global_record = sell_record.copy()
            global_record['remaining_amount'] = remaining_amount
            global_record['is_full_sell'] = is_full_sell
            global_record['sell_ratio'] = sell_amount / (sell_amount + remaining_amount) if (sell_amount + remaining_amount) > 0 else 1.0
            global_record['stage'] = hybrid_action.get('stage', 1)
            global_record['position_num'] = position_num
            global_record['preserved_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            global_record['record_type'] = 'partial_sell' if not is_full_sell else 'full_sell'
            
            # 종목 데이터에서 GlobalSellHistory 추가
            for stock_data in self.split_data_list:
                if stock_data['StockCode'] == stock_code:
                    if 'GlobalSellHistory' not in stock_data:
                        stock_data['GlobalSellHistory'] = []
                    stock_data['GlobalSellHistory'].append(global_record)
                    break
            
            logger.info(f"✅ {stock_code} {position_num}차 하이브리드 매도 완료:")
            logger.info(f"   매도: {sell_amount}주 @ ${current_price:.2f}")
            logger.info(f"   수익률: {position_return_pct:+.1f}%")
            logger.info(f"   실현손익: ${net_pnl:+.2f}")  # 🔥 추가된 로그
            logger.info(f"   잔여: {remaining_amount}주")
            logger.info(f"   유형: {hybrid_action['type']}")
            
        except Exception as e:
            logger.error(f"하이브리드 매도 기록 처리 중 오류: {str(e)}")
       
    def process_position_wise_selling(self, stock_code, indicators, magic_data_list, news_decision, news_percentage):
        """각 차수별로 개별적으로 매도 조건을 판단하고 실행 - 🔥 API 오류 방지 개선 버전"""
        try:
            current_price = indicators['current_price']
            
            # 🔥🔥🔥 1단계: 개선된 전체 포지션 적응형 손절 체크 (기존 로직 유지) 🔥🔥🔥
            total_investment = 0
            total_shares = 0
            active_positions = []
            first_buy_date = None
            
            # 전체 평균가 및 포지션 정보 계산
            for magic_data in magic_data_list:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    total_investment += magic_data['EntryPrice'] * magic_data['CurrentAmt']
                    total_shares += magic_data['CurrentAmt']
                    active_positions.append(magic_data)
                    
                    # 🔥 첫 매수 날짜 추적 (시간 기반 손절용)
                    entry_date = magic_data.get('EntryDate', '')
                    if entry_date and entry_date != "":
                        try:
                            buy_date = datetime.strptime(entry_date, "%Y-%m-%d")
                            if first_buy_date is None or buy_date < first_buy_date:
                                first_buy_date = buy_date
                        except:
                            pass
            
            if total_shares > 0:
                avg_entry_price = total_investment / total_shares
                total_return = (current_price - avg_entry_price) / avg_entry_price * 100
                position_count = len(active_positions)
                
                # 🔥🔥🔥 핵심 개선: 적응형 손절 시스템 (기존 로직 그대로 유지) 🔥🔥🔥
                should_stop_loss = False
                stop_loss_reason = ""
                
                # 🔥 설정 파일에서 적응형 손절선 가져오기
                stop_loss_config = config.config.get('enhanced_stop_loss', {})
                adaptive_thresholds = stop_loss_config.get('adaptive_thresholds', {
                    'position_1': -0.18,
                    'position_2': -0.22,
                    'position_3_plus': -0.28
                })

                # 1️⃣ 차수별 적응형 손절선 계산 (설정 기반)
                if position_count == 1:
                    adaptive_stop_loss = adaptive_thresholds.get('position_1', -0.18) * 100
                    stop_category = "초기단계"
                elif position_count == 2:
                    adaptive_stop_loss = adaptive_thresholds.get('position_2', -0.22) * 100
                    stop_category = "진행중"
                elif position_count >= 3:
                    adaptive_stop_loss = adaptive_thresholds.get('position_3_plus', -0.28) * 100
                    stop_category = "전략완성"
                    
                # 🔥🔥🔥 변동성 조정도 설정에서 가져오기 🔥🔥🔥
                volatility_adjustment_config = stop_loss_config.get('volatility_adjustment', -0.03)

                # 2️⃣ 변동성 기반 손절선 조정
                try:
                    df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", 90)
                    if df is not None and len(df) >= 30:
                        volatility = df['close'].pct_change().std() * 100
                        
                        if volatility > 4.0:  # 고변동성 (RKLB, VRT 등)
                            volatility_adjustment = -3.0  # 3%p 완화
                            volatility_desc = "고변동성"
                        elif volatility > 2.5:  # 중변동성
                            volatility_adjustment = -1.5  # 1.5%p 완화  
                            volatility_desc = "중변동성"
                        else:  # 저변동성 (CCJ 등)
                            volatility_adjustment = 0.0
                            volatility_desc = "저변동성"
                        
                        adaptive_stop_loss += volatility_adjustment
                        
                        logger.info(f"📊 {stock_code} 적응형 손절선: {adaptive_stop_loss:.1f}% "
                                f"({stop_category}, {volatility_desc}, 변동성:{volatility:.1f}%)")
                    else:
                        volatility_desc = "데이터부족"
                        
                except Exception as vol_e:
                    logger.warning(f"변동성 계산 실패: {str(vol_e)}")
                    volatility_desc = "계산실패"
                
                # 🔥🔥🔥 시간 기반 손절도 설정에서 가져오기 🔥🔥🔥
                time_based_rules = stop_loss_config.get('time_based_rules', {
                    '60_day_threshold': -0.15,
                    '120_day_threshold': -0.10
                })
                # 3️⃣ 시간 기반 손절 (장기 부진 종목 정리)
                time_based_stop = False
                if first_buy_date:
                    days_holding = (datetime.now() - first_buy_date).days
                    
                    # 60일 룰
                    day_60_threshold = time_based_rules.get('60_day_threshold', -0.15) * 100
                    if days_holding >= 60 and total_return <= day_60_threshold:
                        time_based_stop = True
                        stop_loss_reason = f"장기부진 손절 (보유 {days_holding}일, {total_return:.1f}% ≤ {day_60_threshold:.1f}%)"
                        logger.warning(f"⏰ {stock_code} 장기부진 감지: {days_holding}일 보유, {total_return:.1f}% 손실")
                        
                    # 120일 룰
                    day_120_threshold = time_based_rules.get('120_day_threshold', -0.10) * 100
                    if days_holding >= 120 and total_return <= day_120_threshold:
                        time_based_stop = True  
                        stop_loss_reason = f"초장기부진 손절 (보유 {days_holding}일, {total_return:.1f}% ≤ {day_120_threshold:.1f}%)"
                        logger.warning(f"🚨 {stock_code} 초장기부진: {days_holding}일 보유, {total_return:.1f}% 손실")

                # 4️⃣ 최종 손절 판단
                if total_return <= adaptive_stop_loss:
                    should_stop_loss = True
                    stop_loss_reason = f"적응형 손절 ({position_count}차수, {stop_category}, {total_return:.1f}% ≤ {adaptive_stop_loss:.1f}%)"
                    
                elif time_based_stop:
                    should_stop_loss = True
                    # stop_loss_reason은 이미 3️⃣에서 설정됨
                
                # 5️⃣ 적응형 손절 실행 (기존 로직 그대로)
                if should_stop_loss:
                    logger.warning(f"🚨 {stock_code} 적응형 손절 실행:")
                    logger.warning(f"   💰 평균가: ${avg_entry_price:.2f} → 현재가: ${current_price:.2f}")
                    logger.warning(f"   📊 손실률: {total_return:.1f}% (손절선: {adaptive_stop_loss:.1f}%)")
                    logger.warning(f"   🔢 활성차수: {position_count}개")
                    logger.warning(f"   📅 보유기간: {(datetime.now() - first_buy_date).days if first_buy_date else 0}일")
                    logger.warning(f"   🎯 사유: {stop_loss_reason}")
                    
                    # 모든 포지션 일괄 손절 실행
                    total_stop_amount = 0
                    position_details = []
                    
                    for magic_data in magic_data_list:
                        if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                            position_num = magic_data['Number']
                            current_amount = magic_data['CurrentAmt']
                            entry_price = magic_data['EntryPrice']
                            
                            # 매도 주문 실행
                            result, error = self.handle_sell(stock_code, current_amount, current_price)
                            
                            if result:
                                # 개별 차수별 손익 계산
                                individual_return = (current_price - entry_price) / entry_price * 100
                                
                                # 매도 기록
                                sell_record = {
                                    'date': datetime.now().strftime("%Y-%m-%d"),
                                    'price': current_price,
                                    'amount': current_amount,
                                    'reason': f"{position_num}차 적응형손절",
                                    'return_pct': individual_return,
                                    'avg_price_at_stop': avg_entry_price,
                                    'total_return_pct': total_return,
                                    'stop_loss_type': stop_category,
                                    'adaptive_stop_line': adaptive_stop_loss,
                                    'holding_days': (datetime.now() - first_buy_date).days if first_buy_date else 0,
                                    'volatility_desc': volatility_desc
                                }
                                magic_data['SellHistory'].append(sell_record)
                                magic_data['CurrentAmt'] = 0
                                magic_data['IsBuy'] = False
                                magic_data['RemainingRatio'] = 0.0  # 🔥 부분매도 필드도 정리
                                magic_data['PartialSellStage'] = 3  # 최종 완료로 설정
                                
                                # 🔥 최고점도 리셋
                                for key in list(magic_data.keys()):
                                    if key.startswith('max_profit_'):
                                        magic_data[key] = 0
                                
                                total_stop_amount += current_amount
                                position_details.append(f"{position_num}차 {current_amount}주({individual_return:+.1f}%)")
                    
                    if total_stop_amount > 0:
                        # 🔥 적응형 손절 완료 알림
                        msg = f"🚨 {stock_code} 적응형 손절 완료!\n"
                        msg += f"  📊 {stop_category} 단계 손절 (활성차수: {position_count}개)\n"
                        msg += f"  💰 평균가: ${avg_entry_price:.2f} → 현재가: ${current_price:.2f}\n"
                        msg += f"  📉 손실률: {total_return:.1f}% (손절선: {adaptive_stop_loss:.1f}%)\n"
                        msg += f"  🔢 총매도: {total_stop_amount}주\n"
                        msg += f"  📋 세부내역: {', '.join(position_details)}\n"
                        if first_buy_date:
                            msg += f"  📅 보유기간: {(datetime.now() - first_buy_date).days}일\n"
                        msg += f"  🎯 {stop_loss_reason}\n"
                        msg += f"  🔄 다음 사이클에서 새로운 1차 시작"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        # 적응형 손절 완료 후 즉시 종료
                        return True

            # 🔥🔥🔥 2단계: 혁신적인 부분매도 시스템 🔥🔥🔥
            
            total_sells = 0
            sell_details = []
            max_profit_updated = False
            
            # 🔥 stock_data_info 미리 찾기
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                logger.error(f"❌ {stock_code} 종목 데이터를 찾을 수 없습니다")
                return False
            
            # 🔥 브로커 실제 보유 정보 조회 (수정됨)
            holdings = self.get_current_holdings(stock_code)
            
            # 🔧 API 오류 체크 추가
            if holdings.get('api_error', False):
                logger.warning(f"⚠️ {stock_code} API 오류로 매도 처리 스킵")
                return False

            if holdings['amount'] == -1:  # API 오류
                logger.info(f"🔄 {stock_code} API 오류 - 기존 데이터 유지, 매도 처리 안함")
                return False
            
            broker_amount = holdings['amount']
            broker_avg_price = holdings['avg_price']
            
            # 🔧 API 오류 시 데이터 정리 차단
            if broker_amount <= 0:
                if holdings.get('api_error', False):
                    logger.warning(f"🔄 {stock_code} API 오류로 데이터 정리 차단 - 기존 상태 유지")
                    return False
                else:
                    logger.info(f"💎 {stock_code} 브로커 실제 보유 없음 - 내부 데이터 정리")
                    for magic_data in magic_data_list:
                        if magic_data['IsBuy']:
                            magic_data['CurrentAmt'] = 0
                            magic_data['IsBuy'] = False
                            magic_data['RemainingRatio'] = 0.0
                            magic_data['PartialSellStage'] = 0
                            # 최고점 리셋
                            for key in list(magic_data.keys()):
                                if key.startswith('max_profit_'):
                                    magic_data[key] = 0
                    
                    self.save_split_data()
                    return False

            # 🔥 부분매도 설정 가져오기
            base_partial_config = self.get_partial_sell_config(stock_code)
            adjusted_partial_config = self.calculate_market_adjusted_sell_thresholds(stock_code, base_partial_config)

            # 🔥🔥🔥 3단계: 각 차수별로 혁신적인 부분매도 처리 🔥🔥🔥
            for magic_data in magic_data_list:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    
                    position_num = magic_data['Number']
                    entry_price = magic_data['EntryPrice']
                    current_amount = magic_data['CurrentAmt']
                    
                    # 🔧 브로커 평균단가 동기화 로직 제거 (진입가 보호)
                    effective_entry_price = entry_price
                    calculation_method = "내부기준"
                    
                    # 🔥 정확한 수익률 계산
                    position_return_pct = (current_price - effective_entry_price) / effective_entry_price * 100
                    
                    # 🔥 개별 차수별 최고점 추적
                    position_max_key = f'max_profit_{position_num}'
                    if position_max_key not in magic_data:
                        magic_data[position_max_key] = 0
                    
                    previous_position_max = magic_data[position_max_key]
                    
                    if position_return_pct > previous_position_max:
                        magic_data[position_max_key] = position_return_pct
                        max_profit_updated = True
                        logger.info(f"📈 {stock_code} {position_num}차 최고점 갱신: {previous_position_max:.1f}% → {position_return_pct:.1f}%")

                    # 🔥🔥🔥 NEW: 전체 종목 최고점 업데이트 (평단가 기준) 🔥🔥🔥
                    # 활성 포지션들의 가중평균 진입가 계산
                    total_invested = sum(pos['EntryPrice'] * pos['CurrentAmt'] for pos in magic_data_list if pos['IsBuy'] and pos['CurrentAmt'] > 0)
                    total_shares = sum(pos['CurrentAmt'] for pos in magic_data_list if pos['IsBuy'] and pos['CurrentAmt'] > 0)

                    if total_shares > 0:
                        avg_price = total_invested / total_shares
                        total_return_pct = (current_price - avg_price) / avg_price * 100
                        
                        # 전체 종목 최고점 업데이트
                        if total_return_pct > stock_data_info['max_profit']:
                            previous_total_max = stock_data_info['max_profit']
                            stock_data_info['max_profit'] = total_return_pct
                            logger.info(f"📈 {stock_code} 전체 최고점 갱신: {previous_total_max:.1f}% → {total_return_pct:.1f}%")
                    # 🔥🔥🔥 전체 종목 최고점 업데이트 끝 🔥🔥🔥

                    # 🔥🔥🔥 혁신의 핵심: 부분매도 시스템 실행 🔥🔥🔥
                    if adjusted_partial_config:
                        # 부분매도 판단
                        should_sell, sell_amount, sell_reason = self.should_execute_partial_sell(
                            stock_code, magic_data, current_price, adjusted_partial_config
                        )
                        
                        if should_sell and sell_amount > 0:
                            logger.info(f"🎯 {stock_code} {position_num}차 스마트 부분매도 실행:")
                            logger.info(f"   현재 수익률: {position_return_pct:+.1f}%")
                            logger.info(f"   매도 사유: {sell_reason}")
                            logger.info(f"   매도 수량: {sell_amount}주 / {current_amount}주")
                            
                            # 부분매도 실행
                            success, message = self.execute_partial_sell(
                                stock_code, magic_data, sell_amount, current_price, sell_reason
                            )
                            
                            if success:
                                # 실현손익 계산
                                position_pnl = (current_price - effective_entry_price) * sell_amount
                                sell_fee = self.calculate_trading_fee(current_price, sell_amount, False)
                                net_position_pnl = position_pnl - sell_fee
                                
                                # 누적 실현손익 업데이트
                                stock_data_info['RealizedPNL'] += net_position_pnl
                                
                                # 매도 완료 처리
                                total_sells += sell_amount
                                
                                # 전량매도인지 부분매도인지 구분
                                is_full_sell = (magic_data['CurrentAmt'] == 0)
                                remaining_amount = magic_data['CurrentAmt']
                                original_amount = magic_data.get('OriginalAmt', sell_amount + remaining_amount)
                                sell_ratio = sell_amount / original_amount if original_amount > 0 else 1.0
                                
                                sell_details.append({
                                    'position': position_num,
                                    'amount': sell_amount,
                                    'remaining': remaining_amount,
                                    'entry_price': effective_entry_price,
                                    'sell_price': current_price,
                                    'return_pct': position_return_pct,
                                    'max_profit': magic_data[position_max_key],
                                    'pnl': net_position_pnl,
                                    'reason': sell_reason,
                                    'calculation_method': calculation_method,
                                    'sell_ratio': sell_ratio,
                                    'is_full_sell': is_full_sell,
                                    'stage': magic_data.get('PartialSellStage', 0),
                                    'system_type': '부분매도'
                                })
                                
                                logger.info(f"✅ {stock_code} {position_num}차 스마트 부분매도 완료:")
                                logger.info(f"   매도: {sell_amount}주 @ ${current_price:.2f}")
                                logger.info(f"   수익률: {position_return_pct:+.1f}%")
                                logger.info(f"   실현손익: ${net_position_pnl:+.2f}")
                                logger.info(f"   잔여: {remaining_amount}주 ({(remaining_amount/original_amount*100) if original_amount > 0 else 0:.0f}%)")
                                
                            else:
                                logger.error(f"❌ {stock_code} {position_num}차 부분매도 실패: {message}")
                        
                        else:
                            # 부분매도 조건 미충족시 로깅 (디버그용)
                            current_stage = magic_data.get('PartialSellStage', 0)
                            logger.debug(f"💎 {stock_code} {position_num}차 홀딩: {position_return_pct:+.1f}% (단계{current_stage}, {sell_reason})")

                        # ⭐⭐⭐ 여기서부터 하이브리드 코드 추가 ⭐⭐⭐
                        
                        # 🔥🔥🔥 하이브리드 보호 시스템 추가 🔥🔥🔥
                        logger.info(f"🔥 {stock_code} 하이브리드 보호 시스템 체크 시작")
                        
                        # 각 차수별 하이브리드 보호 체크
                        for magic_data in magic_data_list:
                            if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                                
                                position_num = magic_data['Number']
                                entry_price = magic_data['EntryPrice']
                                current_amount = magic_data['CurrentAmt']
                                position_return_pct = (current_price - entry_price) / entry_price * 100
                                position_max_key = f'max_profit_{position_num}'
                                position_max = magic_data.get(position_max_key, 0)
                                current_stage = magic_data.get('PartialSellStage', 0)
                                
                                # 하이브리드 보호 시스템 체크
                                hybrid_action = self.check_hybrid_protection(
                                    stock_code, magic_data, current_price, position_return_pct, position_max
                                )
                                
                                if hybrid_action['action'] != 'hold':
                                    logger.info(f"🔥 {stock_code} {position_num}차 하이브리드 보호 실행: {hybrid_action['reason']}")
                                    
                                    # 현실적 매도 수량 계산
                                    realistic_sell_amount = self.calculate_realistic_sell_amount(
                                        current_amount, hybrid_action['sell_ratio'], hybrid_action['action']
                                    )
                                    
                                    if realistic_sell_amount > 0:
                                        result, error = self.handle_sell(stock_code, realistic_sell_amount, current_price)
                                        
                                        if result:

                                            # 🔥🔥🔥 새로 추가: sell_details에 하이브리드 매도 결과 저장 🔥🔥🔥
                                            position_pnl = (current_price - entry_price) * realistic_sell_amount
                                            sell_fee = self.calculate_trading_fee(current_price, realistic_sell_amount, False)
                                            net_position_pnl = position_pnl - sell_fee
                                            
                                            remaining_amount = current_amount - realistic_sell_amount
                                            original_amount = magic_data.get('OriginalAmt', current_amount)
                                            is_full_sell = (remaining_amount == 0)
                                            sell_ratio = realistic_sell_amount / original_amount if original_amount > 0 else 1.0
                                            
                                            sell_details.append({
                                                'position': position_num,
                                                'amount': realistic_sell_amount,
                                                'remaining': remaining_amount,
                                                'entry_price': entry_price,
                                                'sell_price': current_price,
                                                'return_pct': position_return_pct,
                                                'max_profit': position_max,
                                                'pnl': net_position_pnl,  # 🔥 정확한 실현손익
                                                'reason': hybrid_action['reason'],
                                                'sell_ratio': sell_ratio,
                                                'is_full_sell': is_full_sell,
                                                'stage': hybrid_action.get('type', '하이브리드'),
                                                'system_type': '하이브리드매도'
                                            })

                                            # 하이브리드 매도 기록 처리
                                            self.process_hybrid_sell_record(
                                                stock_code, magic_data, realistic_sell_amount, current_price, 
                                                position_return_pct, hybrid_action
                                            )
                                            
                                            total_sells += realistic_sell_amount
                                            
                                            # 매도 완료 시 처리 (기존 로직과 동일)
                                            if magic_data['CurrentAmt'] <= 0:
                                                logger.info(f"📊 {stock_code} {position_num}차 완전 청산 완료")
                                                continue
                                                
                                        else:
                                            logger.error(f"❌ {stock_code} {position_num}차 하이브리드 매도 실패: {error}")
                        
                        # ⭐⭐⭐ 하이브리드 코드 추가 끝 ⭐⭐⭐

                    else:
                        # 🔥 부분매도 비활성화된 경우 기존 로직 사용 (안전장치)
                        logger.debug(f"📊 {stock_code} {position_num}차 부분매도 비활성화 - 기존 로직 적용")
                        
                        # 기본 목표 수익률 계산 (기존 로직)
                        base_target = self.calculate_dynamic_profit_target(stock_code, indicators)
                        target_profit_pct = base_target
                        
                        # 목표가 미달성시 홀딩
                        if position_return_pct < target_profit_pct:
                            logger.debug(f"💎 {stock_code} {position_num}차 목표가 미달성: {position_return_pct:.1f}% < {target_profit_pct:.1f}%")
                            continue
                        
                        # 기존 트레일링 스톱 로직
                        current_position_max = magic_data[position_max_key]
                        grace_threshold = target_profit_pct * 1.05
                        
                        if current_position_max >= grace_threshold:
                            # 기존 6구간 트레일링 로직
                            if current_position_max >= target_profit_pct * 3.0:
                                trailing_pct = 0.025
                                level = "극한수익"
                            elif current_position_max >= target_profit_pct * 2.5:
                                trailing_pct = 0.03
                                level = "초고수익"
                            elif current_position_max >= target_profit_pct * 2.0:
                                trailing_pct = 0.035
                                level = "고수익"
                            elif current_position_max >= target_profit_pct * 1.5:
                                trailing_pct = 0.04
                                level = "중수익"
                            elif current_position_max >= target_profit_pct * 1.2:
                                trailing_pct = 0.045
                                level = "양호수익"
                            else:
                                trailing_pct = 0.05
                                level = "목표달성"
                            
                            basic_trailing = current_position_max - (trailing_pct * 100)
                            safety_line = target_profit_pct * 0.95
                            final_threshold = max(basic_trailing, safety_line)
                            
                            if position_return_pct <= final_threshold:
                                # 기존 전량매도 실행
                                logger.warning(f"🚨 {stock_code} {position_num}차 기존방식 전량매도:")
                                logger.warning(f"   진입가: ${effective_entry_price:.2f}")
                                logger.warning(f"   현재가: ${current_price:.2f}")
                                logger.warning(f"   수익률: {position_return_pct:+.1f}%")
                                logger.warning(f"   최고점: {current_position_max:.1f}%")
                                
                                result, error = self.handle_sell(stock_code, current_amount, current_price)
                                
                                if result:
                                    # 기존 매도 처리 로직과 동일
                                    sell_record = {
                                        'date': datetime.now().strftime("%Y-%m-%d"),
                                        'price': current_price,
                                        'amount': current_amount,
                                        'reason': f"{position_num}차 기존방식 트레일링스톱",
                                        'return_pct': position_return_pct
                                    }
                                    magic_data['SellHistory'].append(sell_record)
                                    magic_data['CurrentAmt'] = 0
                                    magic_data['IsBuy'] = False
                                    magic_data['RemainingRatio'] = 0.0
                                    magic_data['PartialSellStage'] = 3  # 완료로 설정
                                    magic_data[position_max_key] = 0
                                    
                                    # 실현손익 계산
                                    position_pnl = (current_price - effective_entry_price) * current_amount
                                    sell_fee = self.calculate_trading_fee(current_price, current_amount, False)
                                    net_position_pnl = position_pnl - sell_fee
                                    stock_data_info['RealizedPNL'] += net_position_pnl
                                    
                                    total_sells += current_amount
                                    original_amount = magic_data.get('OriginalAmt', current_amount)
                                    sell_details.append({
                                        'position': position_num,
                                        'amount': current_amount,
                                        'remaining': 0,
                                        'entry_price': effective_entry_price,
                                        'sell_price': current_price,
                                        'return_pct': position_return_pct,
                                        'max_profit': current_position_max,
                                        'pnl': net_position_pnl,
                                        'reason': f"기존방식 {level} 트레일링스톱",
                                        'calculation_method': calculation_method,
                                        'sell_ratio': 1.0,
                                        'is_full_sell': True,
                                        'stage': 'legacy',
                                        'system_type': '기존방식'
                                    })
                                    
                                    logger.info(f"✅ {stock_code} {position_num}차 기존방식 매도 완료")

            # 🔥 최고점 업데이트되었거나 매도가 있으면 저장
            if max_profit_updated or total_sells > 0:
                self.save_split_data()
                if max_profit_updated and total_sells == 0:
                    logger.info(f"📊 {stock_code} 최고점 업데이트로 데이터 저장")

            if total_sells > 0:
                
                # 🔥 전체 포지션 상태 확인
                remaining_positions = sum([magic_data['CurrentAmt'] for magic_data in magic_data_list if magic_data['IsBuy']])
                
                if remaining_positions == 0:
                    stock_data_info['IsReady'] = True
                    logger.info(f"🎉 {stock_code} 전량 매도 완료 - Ready 상태로 전환")
                else:
                    logger.info(f"📊 {stock_code} 부분 매도 완료 - 잔여 {remaining_positions}주 보유 중")
                
                # 🔥🔥🔥 혁신적인 매도 완료 메시지 (부분매도 정보 포함) 🔥🔥🔥
                msg = f"💰 {stock_code} 스마트 부분매도 시스템 실행!\n"
                msg += f"  📊 총 매도량: {total_sells}주 @ ${current_price:.2f}\n"
                
                if news_decision != 'NEUTRAL':
                    msg += f"  📰 뉴스반영: {news_decision}({news_percentage}%)\n"
                
                msg += f"  📋 매도 상세내역:\n"
                
                total_realized = 0
                partial_sells = 0
                full_sells = 0
                
                for detail in sell_details:
                    system_type = detail.get('system_type', '기존방식')
                    stage_desc = f"단계{detail['stage']}" if isinstance(detail['stage'], int) else detail['stage']
                    sell_type = "전량" if detail['is_full_sell'] else "부분"
                    
                    msg += f"    • {detail['position']}차: {detail['amount']}주 {sell_type}매도 "
                    msg += f"(${detail['entry_price']:.2f}→${detail['sell_price']:.2f}, "
                    msg += f"{detail['return_pct']:+.1f}%, 최고:{detail['max_profit']:.1f}%, {stage_desc}, {system_type})\n"
                    
                    if detail['remaining'] > 0:
                        remaining_ratio = detail['remaining'] / (detail['remaining'] + detail['amount']) * 100
                        msg += f"      → 잔여: {detail['remaining']}주 계속 홀딩 ({remaining_ratio:.0f}%)\n"

                    if 'pnl' in detail and detail['pnl'] is not None:
                        detail_pnl = detail['pnl']
                    else:
                        # pnl이 없거나 None인 경우 직접 계산
                        position_pnl = (detail['sell_price'] - detail['entry_price']) * detail['amount']
                        sell_fee = self.calculate_trading_fee(detail['sell_price'], detail['amount'], False)
                        detail_pnl = position_pnl - sell_fee
                        logger.warning(f"⚠️ {stock_code} {detail['position']}차 pnl 값 누락, 직접 계산: ${detail_pnl:.2f}")

                    total_realized += detail_pnl

                    if detail['is_full_sell']:
                        full_sells += 1
                    else:
                        partial_sells += 1
                
                msg += f"  💵 총 실현손익: ${total_realized:+.2f}\n"
                msg += f"  💎 누적 실현손익: ${stock_data_info['RealizedPNL']:+.2f}\n"
                msg += f"  📊 매도 유형: 부분매도 {partial_sells}개, 전량매도 {full_sells}개\n"
                msg += f"  📊 잔여포지션: {remaining_positions}주\n"
                
                # 🔥 부분매도 시스템 혜택 강조
                if partial_sells > 0:
                    msg += f"  🎯 시스템: 단계별 수익확보 + 추가상승 기대\n"
                    msg += f"  ✅ 혜택: 기회비용 최소화 + 리스크 관리\n"
                    if remaining_positions > 0:
                        msg += f"  🚀 잔여 물량으로 무제한 상승 참여 가능\n"
                else:
                    msg += f"  🎯 시스템: 기존 트레일링 방식 적용\n"
                
                msg += f"  🔍 데이터 검증: 완료"
                
                logger.info(msg)
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(msg)
                return True

            return False
            
        except Exception as e:
            logger.error(f"개선된 부분매도 차수별 매도 처리 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def log_position_wise_trailing_status(self):
        """차수별 트레일링 스톱 상태 상세 로그"""
        try:
            target_stocks = config.target_stocks
            
            for stock_code in target_stocks.keys():
                holdings = self.get_current_holdings(stock_code)
                if holdings['amount'] > 0:
                    
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    if stock_data_info:
                        current_price = SafeKisUS.safe_get_current_price(stock_code)
                        base_target = self.calculate_dynamic_profit_target(stock_code, {'current_price': current_price})
                        
                        logger.info(f"📊 {stock_code} 차수별 상태 (목표: {base_target:.1f}%):")
                        
                        active_positions = []
                        
                        for magic_data in stock_data_info['MagicDataList']:
                            if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                                position_num = magic_data['Number']
                                entry_price = magic_data['EntryPrice']
                                amount = magic_data['CurrentAmt']
                                
                                position_return = (current_price - entry_price) / entry_price * 100
                                position_max = magic_data.get(f'max_profit_{position_num}', 0)
                                
                                # 상태 판단
                                if position_return < base_target:
                                    status = "목표가 미달성"
                                    emoji = "💎"
                                elif position_max < base_target * 1.05:
                                    status = "상승여유 제공중"
                                    emoji = "⏳"
                                else:
                                    status = "트레일링 활성"
                                    emoji = "🎯"
                                
                                active_positions.append({
                                    'pos': position_num,
                                    'amount': amount,
                                    'entry': entry_price,
                                    'return': position_return,
                                    'max': position_max,
                                    'status': status,
                                    'emoji': emoji
                                })
                        
                        for pos in sorted(active_positions, key=lambda x: x['pos']):
                            logger.info(f"  {pos['emoji']} {pos['pos']}차: {pos['amount']}주@${pos['entry']:.2f} "
                                      f"({pos['return']:+.1f}%, 최고:{pos['max']:.1f}%) - {pos['status']}")
        
        except Exception as e:
            logger.error(f"차수별 트레일링 상태 로그 중 오류: {str(e)}")

    def log_partial_sell_status(self):
        """부분매도 시스템 상태 상세 로깅"""
        try:
            target_stocks = config.target_stocks
            
            logger.info("📊 부분매도 시스템 현황:")
            
            for stock_code in target_stocks.keys():
                holdings = self.get_current_holdings(stock_code)
                if holdings['amount'] > 0:
                    
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    if stock_data_info:
                        current_price = SafeKisUS.safe_get_current_price(stock_code)
                        partial_config = self.get_partial_sell_config(stock_code)
                        
                        logger.info(f"🎯 {stock_code} 부분매도 현황:")
                        
                        active_positions = []
                        
                        for magic_data in stock_data_info['MagicDataList']:
                            if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                                position_num = magic_data['Number']
                                entry_price = magic_data['EntryPrice']
                                current_amount = magic_data['CurrentAmt']
                                original_amount = magic_data.get('OriginalAmt', current_amount)
                                
                                position_return = (current_price - entry_price) / entry_price * 100
                                remaining_ratio = magic_data.get('RemainingRatio', 1.0)
                                stage = magic_data.get('PartialSellStage', 0)
                                
                                # 다음 매도 기준 계산
                                if partial_config and stage < 3:
                                    adjusted_config = self.calculate_market_adjusted_sell_thresholds(stock_code, partial_config)
                                    if stage == 0:
                                        next_threshold = adjusted_config['first_sell_threshold']
                                        next_action = f"1단계 부분매도({adjusted_config['first_sell_ratio']*100:.0f}%)"
                                    elif stage == 1:
                                        next_threshold = adjusted_config['second_sell_threshold']
                                        next_action = f"2단계 부분매도({adjusted_config['second_sell_ratio']*100:.0f}%)"
                                    elif stage == 2:
                                        next_threshold = adjusted_config['final_sell_threshold']
                                        next_action = "최종 전량매도"
                                    else:
                                        next_threshold = 0
                                        next_action = "매도 완료"
                                else:
                                    next_threshold = 0
                                    next_action = "부분매도 비활성화"
                                
                                # 상태 판단
                                if not partial_config:
                                    status = "기존 시스템"
                                    emoji = "📈"
                                elif position_return < next_threshold:
                                    status = f"대기중 (목표: {next_threshold:.1f}%)"
                                    emoji = "⏳"
                                else:
                                    status = f"매도 준비 ({next_action})"
                                    emoji = "🎯"
                                
                                active_positions.append({
                                    'pos': position_num,
                                    'amount': current_amount,
                                    'original': original_amount,
                                    'entry': entry_price,
                                    'return': position_return,
                                    'ratio': remaining_ratio,
                                    'stage': stage,
                                    'status': status,
                                    'emoji': emoji,
                                    'next_action': next_action
                                })
                        
                        for pos in sorted(active_positions, key=lambda x: x['pos']):
                            logger.info(f"  {pos['emoji']} {pos['pos']}차: {pos['amount']}/{pos['original']}주@${pos['entry']:.2f} "
                                    f"({pos['return']:+.1f}%, 잔여:{pos['ratio']*100:.0f}%, 단계{pos['stage']}) - {pos['status']}")
        
        except Exception as e:
            logger.error(f"부분매도 상태 로깅 중 오류: {str(e)}")

    def get_partial_sell_performance_summary(self):
        """부분매도 시스템 성과 요약"""
        try:
            target_stocks = config.target_stocks
            total_partial_sells = 0
            total_partial_pnl = 0
            
            performance_summary = {}
            
            for stock_code in target_stocks.keys():
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if stock_data_info:
                    stock_partial_sells = 0
                    stock_partial_pnl = 0
                    
                    for magic_data in stock_data_info['MagicDataList']:
                        partial_history = magic_data.get('PartialSellHistory', [])
                        
                        for record in partial_history:
                            if not record.get('is_full_sell', True):  # 부분매도만 카운트
                                stock_partial_sells += 1
                                
                                # 수익 계산
                                amount = record.get('amount', 0)
                                price = record.get('price', 0)
                                return_pct = record.get('return_pct', 0)
                                
                                if amount > 0 and price > 0:
                                    entry_price = price / (1 + return_pct/100)
                                    pnl = (price - entry_price) * amount
                                    stock_partial_pnl += pnl
                    
                    total_partial_sells += stock_partial_sells
                    total_partial_pnl += stock_partial_pnl
                    
                    if stock_partial_sells > 0:
                        performance_summary[stock_code] = {
                            'partial_sells': stock_partial_sells,
                            'partial_pnl': stock_partial_pnl,
                            'avg_pnl': stock_partial_pnl / stock_partial_sells
                        }
            
            return {
                'total_partial_sells': total_partial_sells,
                'total_partial_pnl': total_partial_pnl,
                'by_stock': performance_summary
            }
            
        except Exception as e:
            logger.error(f"부분매도 성과 요약 중 오류: {str(e)}")
            return None

    def send_enhanced_daily_performance_report(self):
        """부분매도 정보가 포함된 개선된 일일 성과 보고서"""
        try:
            logger.info("📊 개선된 일일 성과 보고서 생성 시작")
            
            # 기존 보고서 로직 실행
            self.send_daily_performance_report()
            
            # 🔥 부분매도 시스템 추가 보고서
            partial_performance = self.get_partial_sell_performance_summary()
            
            if partial_performance and partial_performance['total_partial_sells'] > 0:
                
                today = datetime.now().strftime("%Y년 %m월 %d일")
                
                # 부분매도 시스템 보고서 생성
                partial_report = f"🎯 **부분매도 시스템 성과** ({today})\n"
                partial_report += "=" * 35 + "\n\n"
                
                total_sells = partial_performance['total_partial_sells']
                total_pnl = partial_performance['total_partial_pnl']
                avg_pnl = total_pnl / total_sells if total_sells > 0 else 0
                
                partial_report += f"📊 **전체 성과**\n"
                partial_report += f"```\n"
                partial_report += f"총 부분매도 횟수:  {total_sells}회\n"
                partial_report += f"총 부분매도 수익:  ${total_pnl:+,.0f}\n"
                partial_report += f"평균 수익:        ${avg_pnl:+,.0f}/회\n"
                partial_report += f"```\n\n"
                
                # 종목별 부분매도 성과
                partial_report += f"🎯 **종목별 부분매도 성과**\n"
                for stock_code, perf in partial_performance['by_stock'].items():
                    stock_name = config.target_stocks.get(stock_code, {}).get('name', stock_code)
                    
                    partial_report += f"**{stock_name} ({stock_code})**\n"
                    partial_report += f"   🔄 부분매도: {perf['partial_sells']}회\n"
                    partial_report += f"   💰 부분수익: ${perf['partial_pnl']:+,.0f}\n"
                    partial_report += f"   📊 평균수익: ${perf['avg_pnl']:+,.0f}/회\n\n"
                
                # 현재 부분매도 진행 상황
                partial_report += f"📈 **현재 부분매도 진행 상황**\n"
                
                target_stocks = config.target_stocks
                active_partial_positions = 0
                
                for stock_code in target_stocks.keys():
                    holdings = self.get_current_holdings(stock_code)
                    if holdings['amount'] > 0:
                        
                        stock_data_info = None
                        for data_info in self.split_data_list:
                            if data_info['StockCode'] == stock_code:
                                stock_data_info = data_info
                                break
                        
                        if stock_data_info:
                            stock_name = target_stocks[stock_code].get('name', stock_code)
                            current_price = SafeKisUS.safe_get_current_price(stock_code)
                            partial_config = self.get_partial_sell_config(stock_code)
                            
                            if partial_config:
                                adjusted_config = self.calculate_market_adjusted_sell_thresholds(stock_code, partial_config)
                                
                                for magic_data in stock_data_info['MagicDataList']:
                                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                                        position_num = magic_data['Number']
                                        entry_price = magic_data['EntryPrice']
                                        current_amount = magic_data['CurrentAmt']
                                        original_amount = magic_data.get('OriginalAmt', current_amount)
                                        stage = magic_data.get('PartialSellStage', 0)
                                        
                                        position_return = (current_price - entry_price) / entry_price * 100
                                        remaining_ratio = current_amount / original_amount * 100
                                        
                                        # 다음 매도 목표
                                        if stage == 0:
                                            next_target = adjusted_config['first_sell_threshold']
                                            next_desc = "1단계"
                                        elif stage == 1:
                                            next_target = adjusted_config['second_sell_threshold']
                                            next_desc = "2단계"
                                        elif stage == 2:
                                            next_target = adjusted_config['final_sell_threshold']
                                            next_desc = "최종"
                                        else:
                                            next_target = 0
                                            next_desc = "완료"
                                        
                                        if stage < 3:
                                            active_partial_positions += 1
                                            progress = min(100, (position_return / next_target * 100)) if next_target > 0 else 100
                                            
                                            partial_report += f"• **{stock_name} {position_num}차**: "
                                            partial_report += f"{position_return:+.1f}% → {next_desc}목표 {next_target:.1f}% "
                                            partial_report += f"(진행률: {progress:.0f}%, 잔여: {remaining_ratio:.0f}%)\n"
                
                if active_partial_positions == 0:
                    partial_report += "현재 부분매도 대기 중인 포지션이 없습니다.\n"
                
                partial_report += f"\n💡 **부분매도 시스템 효과**\n"
                partial_report += f"✅ 수익 조기 확보로 리스크 감소\n"
                partial_report += f"✅ 잔여 포지션으로 추가 상승 기대\n"
                partial_report += f"✅ 전량매도 대비 기회비용 최소화\n"
                partial_report += f"✅ 재진입 쿨다운 대폭 완화 (50% 단축)\n"
                
                partial_report += f"\n🕒 보고서 생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                # Discord 전송
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(partial_report)
                    logger.info("✅ 부분매도 시스템 성과 보고서 전송 완료")
                else:
                    logger.info("📊 부분매도 시스템 성과 보고서 생성 완료")
                    logger.info(f"\n{partial_report}")
                    
        except Exception as e:
            logger.error(f"개선된 일일 성과 보고서 생성 중 오류: {str(e)}")

    # 🔥 2. 전체 포지션 동기화 함수 (추가)
    def sync_all_positions_with_broker(self):
        """매매 시작 전 모든 포지션을 브로커 기준으로 동기화 - 🔥 수정된 버전"""
        try:
            logger.info("🔄 전체 포지션 브로커 동기화 시작")
            
            target_stocks = config.target_stocks
            sync_count = 0
            
            for stock_code in target_stocks.keys():
                holdings = self.get_current_holdings(stock_code)
                broker_amount = holdings.get('amount', 0)
                broker_avg_price = holdings.get('avg_price', 0)
                
                # 해당 종목 데이터 찾기
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if not stock_data_info:
                    continue
                
                # 🔥 핵심 수정: 내부 관리 수량 계산 (IsBuy 조건 제거)
                internal_total = 0
                active_positions = []
                
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['CurrentAmt'] > 0:  # 🔥 IsBuy 조건 제거!
                        internal_total += magic_data['CurrentAmt']
                        active_positions.append(magic_data)
                
                # 🔥 새로운 로직: 브로커 우선 동기화
                needs_sync = False
                sync_reason = ""
                
                # Case 1: 브로커에 보유가 있는데 내부에 없는 경우 (핵심 문제!)
                if broker_amount > 0 and internal_total == 0:
                    needs_sync = True
                    sync_reason = f"브로커 보유({broker_amount}주) vs 내부 없음"
                    
                    # 🔥 첫 번째 포지션에 브로커 데이터 복원
                    first_pos = stock_data_info['MagicDataList'][0]
                    first_pos['CurrentAmt'] = broker_amount
                    first_pos['EntryPrice'] = broker_avg_price
                    first_pos['EntryAmt'] = broker_amount
                    first_pos['IsBuy'] = True  # 🔥 중요: IsBuy도 수정!
                    # first_pos['EntryDate'] = ""  # 기존 보유라서 날짜 없음
                    if first_pos.get('EntryDate', '') == "":
                        first_pos['EntryDate'] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                    logger.info(f"✅ {stock_code} 브로커 기준 복원:")
                    logger.info(f"   수량: 0 → {broker_amount}")
                    logger.info(f"   평균단가: ${broker_avg_price:.2f}")
                    logger.info(f"   IsBuy: false → true")
                    
                # Case 2: 브로커에 없는데 내부에 있는 경우
                elif broker_amount == 0 and internal_total > 0:
                    needs_sync = True
                    sync_reason = f"브로커 없음 vs 내부 보유({internal_total}주)"
                    
                    # 🔥 모든 포지션 정리
                    for magic_data in stock_data_info['MagicDataList']:
                        if magic_data['CurrentAmt'] > 0:
                            magic_data['CurrentAmt'] = 0
                            magic_data['IsBuy'] = False
                            # 최고점도 리셋
                            for key in list(magic_data.keys()):
                                if key.startswith('max_profit_'):
                                    magic_data[key] = 0
                    
                    logger.info(f"✅ {stock_code} 내부 데이터 정리 (브로커 기준)")
                    
                # Case 3: 수량은 맞는데 IsBuy 상태가 틀린 경우
                elif broker_amount > 0 and internal_total == broker_amount:
                    # IsBuy 상태 검증
                    correct_positions = [
                        magic_data for magic_data in stock_data_info['MagicDataList']
                        if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0
                    ]
                    
                    if len(correct_positions) == 0:  # 수량은 맞는데 IsBuy=false인 경우
                        needs_sync = True
                        sync_reason = f"수량 일치({broker_amount}주) but IsBuy=false"
                        
                        # 보유량이 있는 포지션의 IsBuy를 true로 수정
                        for magic_data in stock_data_info['MagicDataList']:
                            if magic_data['CurrentAmt'] > 0:
                                magic_data['IsBuy'] = True
                                logger.info(f"✅ {stock_code} {magic_data['Number']}차 IsBuy: false → true")
                    
                    # 평균단가 차이 확인 (단일 포지션인 경우)
                    elif len(correct_positions) == 1 and broker_amount > 0:
                        pos = correct_positions[0]
                        internal_price = pos['EntryPrice']
                        
                        if internal_price > 0:  # 0이 아닌 경우만 비교
                            price_diff_pct = abs(broker_avg_price - internal_price) / internal_price * 100
                            
                            if price_diff_pct > 2.0:  # 2% 이상 차이
                                needs_sync = True
                                sync_reason = f"평균단가 차이: {price_diff_pct:.1f}%"
                                
                                old_price = pos['EntryPrice']
                                pos['EntryPrice'] = broker_avg_price
                                
                                logger.info(f"✅ {stock_code} {pos['Number']}차 평균단가 동기화:")
                                logger.info(f"   ${old_price:.2f} → ${broker_avg_price:.2f}")
                    
                # Case 4: 수량 불일치
                elif broker_amount != internal_total:
                    needs_sync = True
                    sync_reason = f"수량 불일치: 브로커 {broker_amount} vs 내부 {internal_total}"
                    
                    if len(active_positions) == 1:
                        # 단일 포지션: 직접 동기화
                        pos = active_positions[0]
                        old_amount = pos['CurrentAmt']
                        
                        pos['CurrentAmt'] = broker_amount
                        pos['EntryPrice'] = broker_avg_price
                        if broker_amount > 0:
                            pos['IsBuy'] = True
                        else:
                            pos['IsBuy'] = False
                        
                        logger.info(f"✅ {stock_code} {pos['Number']}차 수량 동기화:")
                        logger.info(f"   수량: {old_amount} → {broker_amount}")
                        logger.info(f"   평균단가: ${broker_avg_price:.2f}")
                        
                    elif len(active_positions) > 1:
                        # 다중 포지션: 첫 번째에 통합
                        first_pos = active_positions[0]
                        
                        # 나머지 포지션 정리
                        for pos in active_positions[1:]:
                            pos['CurrentAmt'] = 0
                            pos['IsBuy'] = False
                        
                        # 첫 번째 포지션에 통합
                        first_pos['CurrentAmt'] = broker_amount
                        first_pos['EntryPrice'] = broker_avg_price
                        if broker_amount > 0:
                            first_pos['IsBuy'] = True
                        else:
                            first_pos['IsBuy'] = False
                        
                        logger.info(f"✅ {stock_code} {first_pos['Number']}차에 통합: {broker_amount}주 @ ${broker_avg_price:.2f}")
                
                if needs_sync:
                    sync_count += 1
                    logger.warning(f"⚠️ {stock_code} 동기화 실행: {sync_reason}")
            
            if sync_count > 0:
                self.save_split_data()
                logger.info(f"✅ 전체 포지션 동기화 완료: {sync_count}개 종목")
                
                # 🔥 동기화 결과 Discord 알림
                if config.config.get("use_discord_alert", True):
                    sync_msg = f"🔄 **포지션 동기화 완료**\n"
                    sync_msg += f"수정된 종목: {sync_count}개\n"
                    sync_msg += f"브로커 기준으로 데이터 정정됨"
                    discord_alert.SendMessage(sync_msg)
            else:
                logger.info("✅ 모든 포지션이 이미 동기화됨")
            
        except Exception as e:
            logger.error(f"전체 포지션 동기화 중 오류: {str(e)}")
            
            # 🔥 동기화 실패 알림
            if config.config.get("use_discord_alert", True):
                error_msg = f"🚨 **포지션 동기화 실패**\n"
                error_msg += f"오류: {str(e)}\n"
                error_msg += f"수동 확인 필요"
                discord_alert.SendMessage(error_msg)

################################### 거래 시간 체크 ##################################

def setup_news_analysis_schedule():
    """뉴스 분석 스케줄 설정"""
    try:
        # 뉴스 분석: 매일 장 시작 30분 전 (09:00 ET)
        schedule.every().day.at("09:00").do(
            lambda: SmartMagicSplit().analyze_all_stocks_news()
        ).tag('news_analysis')
        
        # 점심시간 뉴스 업데이트: 매일 12:00 ET
        schedule.every().day.at("12:00").do(
            lambda: SmartMagicSplit().analyze_all_stocks_news()
        ).tag('midday_news')
        
        logger.info("✅ 뉴스 분석 스케줄 설정 완료")
        logger.info("   📰 장전 뉴스 분석: 매일 09:00 ET (한국시간 23:00)")
        logger.info("   📰 점심 뉴스 업데이트: 매일 12:00 ET (한국시간 02:00)")
        
        # 안내 메시지
        news_setup_msg = "📰 **뉴스 분석 시스템 활성화**\n\n"
        news_setup_msg += "🔍 **분석 대상**: NVDIA, Palantir, VRT \n"
        news_setup_msg += "📊 **매매 영향**: 긍정 뉴스 시 매수 조건 완화, 부정 뉴스 시 매수 차단\n"
        news_setup_msg += "🔧 **필요 설정**: .env 파일에 SERPAPI_API_KEY, OPENAI_API_KEY 추가"
        
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(news_setup_msg)
        
    except Exception as e:
        logger.error(f"뉴스 분석 스케줄 설정 중 오류: {str(e)}")

def check_trading_time():
    """미국 장중 거래 가능한 시간대인지 체크하고 장 시작 시점도 확인"""
    try:
        # 🔥 미국 마켓 오픈 상태 확인 (KIS API 사용)
        is_market_open = SafeKisUS.safe_is_market_open()
        if is_market_open is None:
            logger.warning("장 상태 조회 실패, 시간 기반으로만 판단")
            is_market_open = False

        # 미국 현지 시간 출력 (디버깅용)
        now_time = datetime.now(timezone('America/New_York'))
        
        # 상태 로깅
        status_desc = "장중" if is_market_open else "장 시간 외"
        logger.info(f"KIS API 장 상태: {status_desc} (현재 뉴욕 시간: {now_time.strftime('%Y-%m-%d %H:%M:%S %Z')})")
        
        # 직접 시간 확인으로 이중 검증 (시장 시간: 9:30 AM - 4:00 PM ET)
        is_market_hours = False
        is_market_start = False  # 장 시작 시점 체크용
        
        if now_time.weekday() < 5:  # 월-금요일
            # 정규 장 시간 체크 (9:30 AM - 4:00 PM ET)
            if now_time.hour > 9 or (now_time.hour == 9 and now_time.minute >= 30):  # 9:30 AM 이후
                if now_time.hour < 16:  # 4:00 PM 이전
                    is_market_hours = True
            
            # 🔥 장 시작 시점 체크 (9:30 AM 정각 또는 직후 몇 분)
            if now_time.hour == 9 and 30 <= now_time.minute <= 35:
                is_market_start = True
                logger.info("🔔 미국 장 시작 시점 감지!")
        
        logger.info(f"시간 기반 장 상태 확인: {'장중' if is_market_hours else '장 시간 외'}")
        
        # 🔥 최종 거래 가능 여부 판단
        # API와 시간 체크 중 하나라도 True면 거래 가능으로 판단 (안전장치)
        final_trading_time = is_market_open or is_market_hours
        
        logger.info(f"최종 거래 가능 여부: {'⭕ 거래 가능' if final_trading_time else '❌ 거래 불가'}")
        
        return final_trading_time, is_market_start
        
    except Exception as e:
        logger.error(f"미국 거래 시간 체크 중 에러 발생: {str(e)}")
        # 에러 발생 시 안전하게 거래 불가로 판단
        return False, False

################################### 메인 실행 함수 ##################################

def run_bot():
    """🥈 실버봇 실행 함수 - 5번째 봇 특화 버전"""
    try:
        # 봇 초기화 및 실행
        bot = get_bot_instance()
        
        # 🥈 시작 시 예산 정보 출력
        logger.info("🥈 실버 광산주 특화 하이브리드 보호 시스템 봇 시작 (5번째 봇)")
        logger.info(f"💰 현재 예산: ${bot.total_money:,.0f}")
        logger.info(f"💱 통화: USD")

        target_stocks = config.target_stocks
        
        # 🥈 표준화: 타겟 종목 현황 출력
        logger.info(f"🎯 실버 광산주 타겟 종목 현황 (5번째 봇):")
        for stock_code, stock_config in target_stocks.items():
            # 🥈 표준화: weight 필드 안전 접근 (원전봇과 동일)
            weight = stock_config.get('weight', 0)
            allocated_budget = bot.total_money * weight
            stock_name = stock_config.get('name', stock_code)
            logger.info(f"  - {stock_name}({stock_code}): 비중 {weight*100:.1f}% (${allocated_budget:,.0f})")
        
        # 매매 로직 실행
        bot.process_trading()
        
    except Exception as e:
        logger.error(f"🥈 실버봇 실행 중 오류 발생: {str(e)}")

def send_startup_message():
    """🥈 실버봇 시작 메시지"""
    try:
        target_stocks = config.target_stocks
        
        setup_msg = f"🥈 **실버봇 시작** - 5번째 봇 추가 완료!\n"
        setup_msg += f"=" * 40 + "\n"
        setup_msg += f"💱 통화: USD (달러)\n" 
        setup_msg += f"💵 설정 예산: ${config.absolute_budget:,.0f} (5번째 봇)\n"
        setup_msg += f"📊 예산 전략: 실버 광산주 집중 + 구조적 공급부족 수혜\n"
        setup_msg += f"🎯 차수 시스템: {config.div_num:.0f}차수 적극적 변동성 활용\n\n"
        
        # 🥈 실버 시장 현황 강조
        setup_msg += f"📈 **실버 시장 현황** (2025년)\n"
        setup_msg += f"🔥 5년 연속 공급 부족 (수요 12억온스 vs 공급 부족)\n"
        setup_msg += f"⚡ 산업 수요 폭발: 태양광+전기차+전자제품 = 7억온스 돌파\n"
        setup_msg += f"💰 가격 상승: $40+ 돌파, 전문가 목표가 $50-100\n"
        setup_msg += f"🚀 광산주 레버리지: 은 가격 상승 시 2-3배 효과\n\n"
        
        # 🥈 실버 포트폴리오 구성
        setup_msg += f"🏭 **실버 광산주 포트폴리오** (3종목 분산)\n"
        
        silver_descriptions = {
            "PAAS": ("아메리카 최대 은 생산", "12개 운영광산", "12% 수익매도", "안정적 대형주", "40%"),
            "HL": ("미국 독점 지위", "미국 50% 점유", "15% 수익매도", "정부 정책 수혜", "35%"),
            "AG": ("성장형 중간규모", "M&A 확장 중", "18% 수익매도", "적극적 성장", "25%")
        }
        
        for stock_code, stock_config in target_stocks.items():
            desc = silver_descriptions.get(stock_code, ("실버 기업", "안정성", "수익매도", "특화", "비중"))
            budget_allocation = config.absolute_budget * stock_config.get('weight', 0)
            
            setup_msg += f"🥈 **{stock_code}** ({desc[4]}) - ${budget_allocation:.0f}\n"
            setup_msg += f"   🎯 특징: {desc[0]} ({desc[1]})\n"
            setup_msg += f"   📊 첫 매도: {desc[2]} + 하이브리드 보호\n"
            setup_msg += f"   ⚡ 장점: {desc[3]}\n\n"
        
        # 🔥 즉시 적용 효과
        setup_msg += f"⚡ **5번째 봇 즉시 효과**:\n"
        setup_msg += f"🎯 PAAS: 대형주 안정성 + 12개 광산 분산\n"
        setup_msg += f"🥈 HL: 미국 독점 지위 + 정부 정책 수혜\n"
        setup_msg += f"💎 AG: 성장주 모멘텀 + M&A 확장 효과\n"
        setup_msg += f"📊 포트폴리오 완성: 5축 분산 (원전+AI+빅테크+미래기술+실버)\n"
        setup_msg += f"🚀 리스크 분산: 20% 증가 (5개 테마)\n"
        setup_msg += f"😌 심리 안정: 원자재 헤지 + 인플레이션 대비\n\n"
        
        setup_msg += f"💡 **실버 하이브리드 매도 시나리오**:\n"
        setup_msg += f"🥈 PAAS: 12% 달성 → 30% 매도 → 70% 트레일링\n"
        setup_msg += f"⛏️ HL: 15% 달성 → 25% 매도 → 75% 트레일링\n"
        setup_msg += f"💎 AG: 18% 달성 → 35% 매도 → 65% 트레일링\n"
        setup_msg += f"🛡️ 응급 보호: 부분매도 실패시 15-20% 트레일링\n\n"
        
        setup_msg += f"🔧 **실버 특화 시스템 ($1,200)**:\n"
        setup_msg += f"• 실버 3축: PAAS(40%) + HL(35%) + AG(25%)\n"
        setup_msg += f"• 지역 분산: 아메리카+미국+캐나다 리스크 분산\n"
        setup_msg += f"• 규모 분산: 대형+독점+성장 완전 커버\n"
        setup_msg += f"• 구조적 수혜: 공급부족 + 산업수요 폭발\n\n"
        
        setup_msg += f"⚙️ **설정 변경**은 {config.config_path} 파일을 수정하세요.\n"
        setup_msg += f"🕐 **미국 장 시간**: 09:30-16:00 ET (한국시간 23:30-06:00)\n"
        setup_msg += f"🥈 **실버 하이브리드**: 구조적 공급부족 + 산업수요 폭발의 완벽한 수혜"
        
        logger.info(setup_msg)
        
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(setup_msg)
            
        logger.info("=" * 40)
        logger.info("🥈 실버 특화 하이브리드 보호 시스템 설정 파일이 생성되었습니다!")
        logger.info("🎯 5번째 봇으로 포트폴리오 분산 완성!")
        logger.info("📈 구조적 공급부족 + 산업수요 폭발 수혜 시스템 가동!")
        logger.info("=" * 40)
        
    except Exception as e:
        logger.error(f"실버봇 설정 생성 메시지 전송 오류: {str(e)}")

################################### 보고서 스케줄링 ##################################

def setup_performance_reporting_schedule():
    """성과 보고서 스케줄 설정"""
    try:
        # 🌅 장 시작 시 성과 보고서: 매일 22:30 KST (미국 장 시작 시간)
        schedule.every().day.at("22:30").do(
            lambda: get_bot_instance().send_daily_performance_report()
        ).tag('market_open_report')

        # 📊 장마감 후 성과 보고서: 매일 16:10 ET (한국시간 06:10)
        schedule.every().day.at("06:10").do(
            lambda: get_bot_instance().send_daily_performance_report()
        ).tag('market_close_report')
        
        # 📈 주간 보고서: 금요일 장마감 30분 후 (16:30 ET) 
        schedule.every().friday.at("06:30").do(
            lambda: get_bot_instance().send_weekly_performance_report()
        ).tag('weekly_report')
        
        logger.info("✅ 성과 보고서 스케줄 설정 완료")
        logger.info("   🌅 장시작 성과보고서: 매일 09:30 ET (한국시간 22:30)")
        logger.info("   📊 장마감 성과보고서: 매일 16:10 ET (한국시간 06:10)")
        logger.info("   📈 주간 성과보고서: 금요일 16:30 ET (한국시간 06:30)")
        
        # 🔥 스케줄 확인 메시지
        setup_msg = "📅 **성과 보고서 스케줄 설정 완료**\n\n"
        setup_msg += "🌅 **장시작 성과보고서**\n"
        setup_msg += "   ⏰ 시간: 매일 09:30 ET (한국시간 22:30)\n"
        setup_msg += "   📋 내용: 전날 성과, 보유현황, 오늘 전망\n\n"
        setup_msg += "📊 **장마감 성과보고서**\n"
        setup_msg += "   ⏰ 시간: 매일 16:10 ET (한국시간 06:10)\n"
        setup_msg += "   📋 내용: 당일 매매현황, 종목별 수익률, 전체 성과\n\n"
        setup_msg += "📈 **주간 성과보고서**\n" 
        setup_msg += "   ⏰ 시간: 금요일 16:30 ET (한국시간 06:30)\n"
        setup_msg += "   📋 내용: 주간 매매통계, 포트폴리오 분석, 다음주 전략\n\n"
        setup_msg += "💰 **핵심 지표**: 초기 예산 대비 절대 손익 및 수익률 포함"
        
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(setup_msg)
        
    except Exception as e:
        logger.error(f"성과 보고서 스케줄 설정 중 오류: {str(e)}")

def setup_enhanced_monitoring():
    """향상된 모니터링 스케줄 설정"""
    try:
        # 33분마다 차수별 트레일링 상태 상세 로그
        schedule.every(33).minutes.do(
            lambda: get_bot_instance().log_position_wise_trailing_status()
        ).tag('position_monitoring')
        
        logger.info("✅ 차수별 트레일링 모니터링 설정 완료 (33분마다)")
        
    except Exception as e:
        logger.error(f"향상된 모니터링 설정 중 오류: {str(e)}")

# 🔥 기존 스케줄링 함수들도 개선된 버전으로 교체하기 위한 함수
def setup_enhanced_monitoring_with_partial_sell():
    """부분매도 시스템을 포함한 향상된 모니터링 설정"""
    try:
        # 33분마다 부분매도 상태 로그
        schedule.every(33).minutes.do(
            lambda: get_bot_instance().log_partial_sell_status()
        ).tag('partial_sell_monitoring')
        
        logger.info("✅ 부분매도 시스템 모니터링 설정 완료 (33분마다)")
        
    except Exception as e:
        logger.error(f"부분매도 모니터링 설정 중 오류: {str(e)}")

def main():
    """메인 함수 - 미국주식용 설정 파일 자동 생성 포함"""
    
    # 🔥 1. 설정 파일 확인 및 생성 (가장 먼저 실행)
    config_created = check_and_create_config()
    
    if config_created:
        # 설정 파일이 새로 생성된 경우 사용자 안내
        user_msg = "🎯 미국주식 스마트 스플릿 봇 초기 설정 완료!\n\n"
        user_msg += "📝 설정 확인 사항:\n"
        user_msg += f"1. 투자 예산: ${config.absolute_budget:,}\n"
        user_msg += f"2. 통화: USD (달러)\n"
        user_msg += "3. 종목별 비중:\n"
        
        for stock_code, stock_config in config.target_stocks.items():
            allocated = config.absolute_budget * stock_config.get('weight', 0)
            stock_type = stock_config.get('stock_type', 'normal')
            user_msg += f"   • {stock_config.get('name', stock_code)}({stock_code}): {stock_config.get('weight', 0)*100:.1f}% (${allocated:,.0f}) - {stock_type}\n"
        
        user_msg += f"\n🕐 미국 장 시간: 09:30-16:00 ET (한국시간 23:30-06:00)"
        user_msg += "\n\n🚀 10초 후 봇이 시작됩니다..."
        
        logger.info(user_msg)
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(user_msg)
        
        # 사용자가 설정을 확인할 시간 제공
        time.sleep(10)

    # 🔥 2. 성과 보고서 스케줄 설정
    # setup_performance_reporting_schedule()

    # 🔥 3. 향상된 모니터링 설정 (새로 추가)
    setup_enhanced_monitoring()    

    # 🔥 3-2. 부분매도 모니터링 설정 (새로 추가)
    # 설명: 30분마다 부분매도 진행 상황을 로그로 출력
    # 함수 위치: 6단계에서 def main(): 바로 위에 추가해야 함
    # 출력 예시: "VRT 1차: 60/100주 (잔여:60%, 단계1) - 2단계 부분매도 준비"
    setup_enhanced_monitoring_with_partial_sell()

    # 🔥 4. 뉴스 분석 스케줄 설정 (새로 추가)
    if NEWS_ANALYSIS_AVAILABLE:
       setup_news_analysis_schedule()
    else:
       logger.info("뉴스 분석 모듈이 비활성화되어 스케줄을 설정하지 않습니다.")

    # 🔥 5. API 재시도 통계 로깅 스케줄 추가
    schedule.every(2).hours.do(
        lambda: retry_manager.log_statistics()
    ).tag('api_stats')
    logger.info("✅ API 재시도 통계 로깅 설정 완료 (2시간마다)")

    # 시작 메시지 전송
    send_startup_message()
    
    # 처음에 한 번 실행
    run_bot()
    
    # 77초마다 실행하도록 스케줄 설정

    # 🔥🔥🔥 간단한 개선: 30초 → 2분, 장외 시간 최적화 🔥🔥🔥
    schedule.every(3).minutes.do(run_bot)  # 77초 → 3분으로 변경
    logger.info("🚀 최적화된 스케줄러 시작 (3분 간격)")
    logger.info("📊 API 호출 75% 감소로 안정성 향상")
    
    consecutive_errors = 0

    # 🔥🔥🔥 수정된 스케줄러 실행 🔥🔥🔥
    while True:

        try:
            # # 📊 스케줄 체크 (항상 먼저 실행)
            # schedule.run_pending()
            # 🔥 미국 장 시간 체크
            is_trading_time, is_market_start = check_trading_time()    

            if not is_trading_time:
                logger.info("미국 장 시간 외입니다. 다음 장 시작까지 5분 대기")
                time.sleep(300)  # 5분 대기
                continue    

            # 🔥 장 시작 시점 특별 처리
            if is_market_start:
                logger.info("🚀 미국 장 시작! 특별 점검 수행")

            # 기존 스케줄 실행
            schedule.run_pending()
            consecutive_errors = 0  # 성공시 리셋

            time.sleep(3)  # CPU 사용량을 줄이기 위해 짧은 대기 시간 추가

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"메인 루프 오류 (연속 {consecutive_errors}회): {str(e)}")
            
            # 🔥 간단한 에러 대응
            if consecutive_errors >= 3:
                sleep_time = min(300, consecutive_errors * 30)  # 최대 5분
                logger.warning(f"⚠️ 연속 오류로 {sleep_time}초 대기")
                time.sleep(sleep_time)
            else:
                time.sleep(60)  # 1분 대기

if __name__ == "__main__":
    main()