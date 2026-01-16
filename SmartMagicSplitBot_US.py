#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
미국주식용 스마트 매직 스플릿 봇 (SmartMagicSplitBot_US) - 절대 예산 기반 동적 조정 버전
1. 절대 예산 기반 투자 (달러 기준, 다른 매매봇과 독립적 운영)
2. 성과 기반 동적 예산 조정 (70%~140% 범위)
3. 안전장치 강화 (현금 잔고 기반 검증)
4. 설정 파일 분리 (JSON 기반 관리)
5. 기존 스플릿 로직 유지 (5차수 분할 매매)
6. 미국주식 특화 (IONQ, SMR 타겟)
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
logger = logging.getLogger('SmartMagicSplitUsLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'smart_magic_split_us.log')
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

# 🔥🔥🔥 글로벌 Rate Limiter 초기화 🔥🔥🔥
try:
    import global_rate_limiter
    global_rate_limiter.set_logger(logger)
    global_rate_limiter.get_rate_limiter(is_virtual=False)  # 싱글톤 인스턴스만 생성
    logger.info("🚦 글로벌 Rate Limiter 활성화 (실전 모드)")
except ImportError as e:
    logger.warning(f"⚠️ 글로벌 Rate Limiter를 찾을 수 없습니다: {e}")
except Exception as e:
    logger.warning(f"⚠️ 글로벌 Rate Limiter 초기화 실패: {e}")

# discord_alert에 로거 전달
try:
    discord_alert.set_logger(logger)
    logger.info("✅ discord_alert 모듈에 로거 전달 완료")
except:
    logger.warning("⚠️ discord_alert 모듈에 로거 전달 실패")

# 🔥🔥🔥 급락 감지 및 수익 보호 모듈 추가 🔥🔥🔥
try:
    import market_crash_detector
    market_crash_detector.set_logger(logger)  # 로거 전달 (중요!)
    CRASH_DETECTOR_AVAILABLE = True
    logger.info("🚨 급락 감지 및 수익 보호 모듈 로드 완료")
except ImportError as e:
    CRASH_DETECTOR_AVAILABLE = False
    logger.warning(f"⚠️ 급락 감지 모듈을 찾을 수 없습니다: {str(e)}")
    logger.warning("급락 감지 기능이 비활성화됩니다.")

# 🔥🔥🔥 저점 판별 시스템 추가 🔥🔥🔥
try:
    import bottom_detector
    bottom_detector.set_logger(logger)
    BOTTOM_DETECTOR_AVAILABLE = True
    logger.info("🎯 저점 판별 시스템 모듈 로드 완료")
except ImportError as e:
    BOTTOM_DETECTOR_AVAILABLE = False
    logger.warning(f"⚠️ 저점 판별 모듈을 찾을 수 없습니다: {str(e)}")
    logger.warning("저점 판별 기능이 비활성화됩니다.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🆕 AI Cash Target Seller import 추가
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from ai_cash_target_seller import AICashTargetSeller, set_logger as set_cash_seller_logger
    CASH_TARGET_ENABLED = True
    logger.info("✅ AI Cash Target Seller 로드 완료")
except ImportError as e:
    CASH_TARGET_ENABLED = False
    logger.info(f"⚠️ AI Cash Target Seller 로드 실패: {e}")

################################### 뉴스 라이브러리 ##################################
try:
    import news_analysis_us_finhub
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
        """현재 보유 수량 조회"""
        try:
            my_stocks = SafeKisUS.safe_get_my_stock_list("USD")
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    return {
                        'amount': int(stock['StockAmt']),
                        'avg_price': float(stock['StockAvgPrice'])
                    }
            return {'amount': 0, 'avg_price': 0}
        except Exception as e:
            logger.error(f"보유 수량 조회 중 오류 ({stock_code}): {str(e)}")
            return {'amount': 0, 'avg_price': 0}

    def load_bot_data(self):
        """봇 데이터 파일 로드 - 🔥 동적 파일명 지원"""
        try:
            # 🔥 BOT_NAME 전역변수 사용 (동적으로 파일명 생성)
            data_file = f"/var/autobot/kisUS/UsStock_{BOT_NAME}.json"
            
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"✅ 봇 데이터 로드 성공: {data_file} ({len(data)}개 종목)")
                    return data
            else:
                logger.warning(f"⚠️ 봇 데이터 파일 없음: {data_file}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 봇 데이터 로드 중 오류: {str(e)}")
            logger.error(f"   파일 경로: {data_file if 'data_file' in locals() else '경로 미생성'}")
            return []

    def calculate_bot_specific_performance(self):
        """봇별 실제 투자 성과 계산 (파일 저장 포함) - 🔥 안전장치 강화"""
        try:
            my_total_investment = 0
            my_total_current_value = 0
            my_realized_pnl = 0
            
            # 🔥 파일을 딱 한 번만 로드
            bot_data = self.load_bot_data()
            
            # 디버깅: 로드된 데이터 확인
            logger.info(f"📊 {self.bot_name} 성과 계산 시작 - 로드된 종목 수: {len(bot_data)}")
            
            # 현재 자신의 종목들만 조회
            for stock_code in self.target_stocks:
                # 1️⃣ 브로커에서 실제 보유 조회 (미실현손익용)
                holdings = self.get_current_holdings(stock_code)
                
                # 🔥🔥🔥 안전장치: API 오류나 None 체크 추가 🔥🔥🔥
                if holdings is None:
                    logger.warning(f"⚠️ {stock_code} 보유 정보 조회 실패 (None 반환)")
                    continue
                    
                if 'api_error' in holdings and holdings['api_error']:
                    logger.warning(f"⚠️ {stock_code} API 오류로 성과 계산 스킵")
                    continue
                
                amount = holdings.get('amount', 0)
                
                # 🔥 안전한 비교: None이 아니고, 0보다 큰 경우만 처리
                if amount is not None and amount > 0:
                    current_price = SafeKisUS.safe_get_current_price(stock_code)
                    if current_price is not None and current_price > 0:
                        current_value = amount * current_price
                        avg_price = holdings.get('avg_price', 0)
                        
                        if avg_price is not None and avg_price > 0:
                            investment_cost = amount * avg_price
                            
                            my_total_investment += investment_cost
                            my_total_current_value += current_value
                            
                            logger.info(f"   📈 {stock_code}: {amount}주 @ ${avg_price:.2f} = ${investment_cost:,.2f}")
                        else:
                            logger.warning(f"⚠️ {stock_code} 평균가격 정보 없음")
                    else:
                        logger.warning(f"⚠️ {stock_code} 현재가 조회 실패")
                
                # 2️⃣ 실현손익 조회 (이미 로드된 bot_data에서)
                stock_realized = 0
                for stock_data in bot_data:
                    if stock_data.get('StockCode') == stock_code:
                        realized_value = stock_data.get('RealizedPNL', 0)
                        if realized_value is not None:
                            stock_realized = realized_value
                            my_realized_pnl += stock_realized
                            
                            # 디버깅: 종목별 실현손익 출력
                            if stock_realized != 0:
                                logger.info(f"   💰 {stock_code} 실현손익: ${stock_realized:,.2f}")
                        break
            
            # 🔥 안전장치: initial_asset이 None이거나 0인 경우 처리
            if self.initial_asset is None or self.initial_asset <= 0:
                logger.error(f"❌ {self.bot_name} 초기자산이 유효하지 않음: {self.initial_asset}")
                return None
            
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
            
            # 🔥 디버깅: 계산 결과 출력
            logger.info(f"📊 {self.bot_name} 성과 계산 완료:")
            logger.info(f"   초기 자산: ${self.initial_asset:,.2f}")
            logger.info(f"   투자 금액: ${my_total_investment:,.2f}")
            logger.info(f"   현재 가치: ${my_total_current_value:,.2f}")
            logger.info(f"   실현 손익: ${my_realized_pnl:,.2f}")
            logger.info(f"   현금 부분: ${current_cash_portion:,.2f}")
            logger.info(f"   총 자산: ${my_total_asset:,.2f}")
            logger.info(f"   수익률: {actual_performance*100:+.2f}%")
            
            # 🔥 성과 데이터 파일에 저장
            self.save_performance_data(perf_data)
            
            return perf_data
            
        except Exception as e:
            logger.error(f"❌ {self.bot_name} 성과 계산 중 오류: {str(e)}")
            import traceback
            logger.error(f"   상세 오류: {traceback.format_exc()}")
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
    
    def __init__(self, config_path: str = "smart_split_config_us.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()

    def get_default_config(self):
            """기본 설정 반환 - 🔥 순수 원전 3종목 + 변동성 기반 적응형 시스템"""
            return {
                "bot_name": "SmartMagicSplitBot_US",
                "currency": "USD",
                "use_absolute_budget": True,
                "absolute_budget": 3000,
                "absolute_budget_strategy": "proportional",
                "initial_total_asset": 5010,
                "div_num": 5,
                
                # 🔥 변동성 기반 적응형 임계값 시스템
                "volatility_analysis": {
                    "enable": True,
                    "volatility_thresholds": {
                        "low": 2.0,
                        "medium": 3.5,
                        "high": 5.0,
                        "_comment": "일별 변동성 기준값 (표준편차 * 100)"
                    },
                    "max_move_thresholds": {
                        "stable": 5.0,
                        "volatile": 8.0,
                        "_comment": "최근 30일 최대 일간 변동폭 기준값"
                    },
                    "volatility_multipliers": {
                        "low": 0.6,
                        "medium": 0.8,
                        "high": 1.0,
                        "ultra_high": 1.2,
                        "_comment": "변동성별 임계값 조정 계수"
                    },
                    "max_move_multipliers": {
                        "stable": 0.95,
                        "normal": 1.05,
                        "volatile": 1.1,
                        "_comment": "최대 변동폭별 임계값 조정 계수"
                    },
                    "stock_ranges": {
                        "CCJ": {
                            "min": 10,
                            "max": 18,
                            "_comment": "우라늄 채굴 대장주 - 고변동성 고려"
                        },
                        "LEU": {
                            "min": 8,
                            "max": 15,
                            "_comment": "농축 독점기업 - 중변동성 고려"
                        },
                        "BWXT": {
                            "min": 6,
                            "max": 12,
                            "_comment": "기술주 - 저변동성 고려"
                        }
                    },
                    "analysis_period": 90,
                    "recent_period": 30,
                    "_comment": "변동성 분석 기간 (일)"
                },
                
                "buy_limit_system": {
                    "global_limits": {
                        "enable": True,
                        "daily_max": 8,
                        "weekly_max": 28,
                        "monthly_max": 70,
                        "high_frequency_penalty": {
                            "threshold": 5,
                            "penalty_hours": 3,
                            "severity_multiplier": 1.3
                        },
                        "market_condition_modifier": {
                            "bull": 1.2,
                            "bear": 0.8,
                            "neutral": 1.0,
                            "high": 1.3,
                            "low": 0.8
                        },
                        "partial_sell_cooldown": {
                            "enable": True,
                            "first_partial": 2,
                            "second_partial": 3,
                            "full_sell": 5,
                            "_comment": "순수 원전 부분매도 최적화"
                        }
                    },
                    "dynamic_limits": {
                        "enable": True,
                        "base_daily": 5,
                        "per_stock_max": 2,
                        "market_bonus": {
                            "downtrend": 5,
                            "uptrend": 3,
                            "neutral": 4
                        },
                        "volatility_bonus": 4,
                        "opportunity_bonus": {
                            "high_density": 4,
                            "medium_density": 3,
                            "low_density": 1
                        },
                        "absolute_max": 12
                    },
                    "_comment": "🔥 순수 원전 3종목 특화 - 안정적 매수 제한"
                },
                
                "market_position_limits": {
                    "strong_uptrend": 6,
                    "uptrend": 6,
                    "neutral": 5,
                    "downtrend": 5,
                    "strong_downtrend": 4,
                    "_comment": "원전 테마 안정성 + 성장성"
                },
                
                "progressive_buy_drops": {
                    "2": 0.05,
                    "3": 0.07,
                    "4": 0.09,
                    "5": 0.12
                },

                "target_stocks": {
                    "CCJ": {
                        "name": "Cameco Corp",
                        "weight": 0.4,
                        "enabled": True,
                        "max_positions": 5,
                        "min_pullback": 0.02,
                        "max_rsi_buy": 75,
                        "profit_target": 12,
                        "stop_loss": -15,
                        "partial_sell_config": {
                            "enable": True,
                            "first_sell_threshold": 14,
                            "first_sell_ratio": 0.2,
                            "adaptive_threshold": True,
                            "_comment": "🔥 adaptive_threshold: true로 변동성 기반 적응형 임계값 활성화",
                            "hybrid_protection": {
                                "enable": True,
                                "min_quantity_for_partial": 3,
                                "min_profit_for_trailing": 7,
                                "post_partial_trailing": 0.05,
                                "emergency_trailing_enable": True,
                                "emergency_max_profit_threshold": 7,
                                "emergency_trailing_drop": 0.07,
                                "_comment": "원전 대장주: 안정적 수익확보 + 7% 이상에서만 트레일링"
                            }
                        },
                        # 🔥🔥🔥 신버전: 종목별 갭 조정 추가 🔥🔥🔥
                        "gap_adjustment": {
                            "enable": True,
                            "threshold": -2.5,
                            "safety_margin": 4.0,
                            "_comment": "🔥 신버전: 우라늄 대장주 - 상대적 안정성"
                        },
                        "news_weight": 0.25,
                        "nuclear_theme_weight": 0.3,
                        "_comment": "우라늄 채굴 대장주"
                    },
                    "LEU": {
                        "name": "Centrus Energy Corp",
                        "weight": 0.35,
                        "enabled": True,
                        "max_positions": 5,
                        "min_pullback": 0.025,
                        "max_rsi_buy": 73,
                        "profit_target": 15,
                        "stop_loss": -18,
                        "partial_sell_config": {
                            "enable": True,
                            "first_sell_threshold": 15,
                            "first_sell_ratio": 0.25,
                            "adaptive_threshold": True,
                            "_comment": "🔥 adaptive_threshold: true로 변동성 기반 적응형 임계값 활성화",
                            "hybrid_protection": {
                                "enable": True,
                                "min_quantity_for_partial": 2,
                                "min_profit_for_trailing": 10,
                                "post_partial_trailing": 0.06,
                                "emergency_trailing_enable": True,
                                "emergency_max_profit_threshold": 8,
                                "emergency_trailing_drop": 0.03,
                                "_comment": "HALEU 농축 독점: 높은 수익 기대 + 정부 계약 안정성"
                            }
                        },
                        # 🔥🔥🔥 신버전: 종목별 갭 조정 추가 🔥🔥🔥
                        "gap_adjustment": {
                            "enable": True,
                            "threshold": -3.5,
                            "safety_margin": 6.0,
                            "_comment": "🔥 신버전: HALEU 독점 - 고변동성 대응"
                        },
                        "news_weight": 0.3,
                        "nuclear_theme_weight": 0.35,
                        "_comment": "미국 유일 HALEU 농축 독점 + DOE 27억달러 계약"
                    },
                    "BWXT": {
                        "name": "BWX Technologies",
                        "weight": 0.25,
                        "enabled": True,
                        "max_positions": 5,
                        "min_pullback": 0.025,
                        "max_rsi_buy": 73,
                        "profit_target": 10,
                        "stop_loss": -12,
                        "partial_sell_config": {
                            "enable": True,
                            "first_sell_threshold": 12,
                            "first_sell_ratio": 0.33,
                            "adaptive_threshold": True,
                            "_comment": "🔥 adaptive_threshold: true로 변동성 기반 적응형 임계값 활성화",
                            "hybrid_protection": {
                                "enable": True,
                                "min_quantity_for_partial": 2,
                                "min_profit_for_trailing": 8,
                                "post_partial_trailing": 0.06,
                                "emergency_trailing_enable": True,
                                "emergency_max_profit_threshold": 8,
                                "emergency_trailing_drop": 0.08,
                                "_comment": "원전 기술주: 즉시 수익확보 + 8% 이상에서만 트레일링"
                            }
                        },
                        # 🔥🔥🔥 신버전: 종목별 갭 조정 추가 🔥🔥🔥
                        "gap_adjustment": {
                            "enable": True,
                            "threshold": -2.0,
                            "safety_margin": 3.5,
                            "_comment": "🔥 신버전: SMR 기술 - 매우 안정적"
                        },
                        "news_weight": 0.2,
                        "nuclear_theme_weight": 0.25,
                        "_comment": "SMR 기술 전문 + 해군용 원자로"
                    }
                },
                
                "comprehensive_scoring": {
                    "enable": True,
                    "position_thresholds": {
                        "1": 65,
                        "2": 62,
                        "3": 58,
                        "4": 54,
                        "5": 50
                    },
                    "_comment": "원전 테마 특화 - 5차수 단계적 완화, 안정성 중시"
                },
                
                "individual_stock_limits": {
                    "enable": True,
                    "default_daily_max": 2,
                    "stock_specific": {
                        "CCJ": {
                            "daily_max": 3,
                            "weekly_max": 8
                        },
                        "LEU": {
                            "daily_max": 3,
                            "weekly_max": 8
                        },
                        "BWXT": {
                            "daily_max": 2,
                            "weekly_max": 6
                        }
                    },
                    "_comment": "순수 원전 테마 안정적 제어"
                },
                
                "risk_management": {
                    "max_position_ratio": 0.4,
                    "emergency_stop_loss": -0.18,
                    "daily_loss_limit": -0.1,
                    "position_size_limit": 0.4,
                    "_comment": "순수 원전 테마 중장기 관점 + LEU 독점성 반영"
                },
                
                "technical_analysis": {
                    "enable": True,
                    "rsi_period": 14,
                    "ma_periods": [5, 20, 60],
                    "volume_analysis": True,
                    "trend_confirmation": True,
                    "nuclear_momentum_weight": 0.3,
                    "_comment": "순수 원전 테마 모멘텀 고려"
                },
                
                "news_analysis": {
                    "enable": True,
                    "sentiment_weight": 0.25,
                    "cache_duration_minutes": 240,
                    "nuclear_theme_bonus": 0.25,
                    "earnings_weight": 0.25,
                    "_comment": "순수 원전 테마 뉴스 가중치 강화"
                },
                
                "volatility_adjustment": -0.03,
                
                "time_based_rules": {
                    "45_day_threshold": -0.12,
                    "90_day_threshold": -0.08
                },
                
                "trading_limits": {
                    "daily_trading_limits": {
                        "enable": True,
                        "max_daily_trades": 6,
                        "max_stock_trades": 2,
                        "reset_hour": 9,
                        "market_condition_multiplier": {
                            "strong_uptrend": 1.3,
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
                            "_comment": "순수 원전 부분매도 최적화"
                        }
                    },
                    "dynamic_limits": {
                        "enable": True,
                        "base_daily": 5,
                        "per_stock_max": 2,
                        "market_bonus": {
                            "downtrend": 5,
                            "uptrend": 3,
                            "neutral": 4
                        },
                        "volatility_bonus": 4,
                        "opportunity_bonus": {
                            "high_density": 4,
                            "medium_density": 3,
                            "low_density": 1
                        },
                        "absolute_max": 12
                    },
                    "_comment": "🔥 순수 원전 3종목 특화 - 안정적 매수 제한"
                },
                
                "use_discord_alert": True,
                "discord_webhook_url": "",
                "trading_enabled": True,
                "auto_trading": True,
                "market_hours_only": True,
                "pre_market_trading": False,
                "after_hours_trading": False,
                
                "market_timing": {
                    "enable": True,
                    "spy_trend_weight": 0.4,
                    "individual_strength_weight": 0.6,
                    "market_condition_adjustment": True,
                    "_comment": "원전 테마 개별 강도 중시"
                },
                
                "_readme": {
                    "설명": "🔥 순수 원전 수직통합 시스템 (4개봇 아키텍처) + 변동성 기반 적응형 시스템",
                    "업데이트_날짜": "2025-09-08",
                    "투자전략": "CCJ+LEU+BWXT 완전 원전 공급망 집중 + 종목별 변동성 최적화",
                    "총예산": "$2,800 (4개봇 재배분)",
                    "통화": "USD (달러)",
                    "테마": "순수 원전 (채굴→농축→기술)"
                },
                
                "_comment_hybrid_system": "🔥 순수 원전 특화 하이브리드 보호 시스템 - LEU 독점성 극대화 + 변동성 기반 적응형 임계값",
                "last_config_update": datetime.now().isoformat(),
                
                "performance_tracking": {
                    "best_performance": 0.0,
                    "worst_performance": 0.0
                },
                
                "commission_rate": 0.0015,
                "tax_rate": 0.0,
                "special_tax_rate": 0.0,
                "budget_check_before_buy": True,
                "minimum_cash_reserve": 200,
                "performance_multiplier_range": [0.7, 1.4],
                "budget_loss_tolerance": 0.25,
                "safety_cash_ratio": 0.95,
                "rsi_period": 14,
                "atr_period": 14,
                "pullback_rate": 1.5,
                "rsi_lower_bound": 20,
                "rsi_upper_bound": 80,
                "ma_short": 5,
                "ma_mid": 20,
                "ma_long": 60,
                
                "buy_control": {
                    "max_daily_buys": 10,
                    "enable_cooldown": True,
                    "cooldown_days": [0, 0, 0, 0, 0],
                    "post_sell_cooldown_hours": 3,
                    "loss_sell_cooldown_hours": 4,
                    "max_daily_trades": 12,
                    "market_based_limits": True,
                    "consecutive_loss_limit": 4,
                    "min_cooldown_hours": 1,
                    "max_cooldown_hours": 8,
                    "adaptive_cooldown": {
                        "enable": True,
                        "profit_based": {
                            "25_percent": 6,
                            "20_percent": 4,
                            "15_percent": 3,
                            "10_percent": 2,
                            "break_even": 1
                        },
                        "loss_sell": 4,
                        "volatility_multiplier": {
                            "high": 1.5,
                            "medium": 1.0,
                            "low": 0.8
                        }
                    }
                }
            }

    def load_config(self):
        """설정 파일 로드 - 🔥 설정파일 완전 우선 (확실한 방법)"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 🔥 새로운 방법: 설정파일을 그대로 사용하고, 누락된 것만 기본값에서 보완
            default_config = self.get_default_config()
            
            # 기본값에서 누락된 최상위 키만 추가
            for key, value in default_config.items():
                if key not in loaded_config:
                    loaded_config[key] = value
            
            self.config = loaded_config  # 🔥 핵심: 설정파일을 직접 사용!
            logger.info(f"✅ 설정 파일 로드 완료 (설정파일 완전 우선): {self.config_path}")
            
            # 🔥 디버그: 실제 로드된 ai_theme_weight 값 확인
            pltr_config = self.config.get('target_stocks', {}).get('PLTR', {})
            ai_theme_weight = pltr_config.get('ai_theme_weight', 0)
            logger.info(f"🤖 PLTR ai_theme_weight 최종값: {ai_theme_weight} ({ai_theme_weight*100:.0f}%)")
            
        except FileNotFoundError:
            logger.info(f"📋 설정 파일이 없습니다. 기본 설정 파일을 생성합니다: {self.config_path}")
            self.config = self.get_default_config()
            self.save_config()
            self._send_creation_message()
            
        except Exception as e:
            logger.error(f"설정 파일 로드 중 오류: {str(e)}")
            self.config = self.get_default_config()

    def load_allocated_budget(self):
        """중앙 예산 조정기에서 할당된 예산 읽기"""
        try:
            allocation_file = "budget_allocation.json"
            
            # 파일이 없으면 None 반환 (기본 예산 사용)
            if not os.path.exists(allocation_file):
                logger.info("💡 budget_allocation.json 파일이 없습니다. 기본 예산을 사용합니다.")
                return None
            
            # 파일 읽기
            with open(allocation_file, 'r', encoding='utf-8') as f:
                allocation_data = json.load(f)
            
            # 원전봇 예산 찾기
            bot_name = self.config.get("bot_name", "SmartMagicSplitBot_US")
            allocations = allocation_data.get('allocations', {})
            
            # 봇 이름으로 할당 정보 찾기
            for key, value in allocations.items():
                if value.get('bot_key') == '원전봇' or key == bot_name:
                    allocated_budget = value.get('allocated_budget')
                    budget_change_pct = value.get('budget_change_pct', 0)
                    performance = value.get('performance', 0)
                    
                    logger.info("=" * 80)
                    logger.info(f"💰 {bot_name} 할당 예산: ${allocated_budget:,.0f}")
                    logger.info(f"   📊 예산 변화: {budget_change_pct:+.1f}% (초기 대비)")
                    logger.info(f"   📈 성과: {performance*100:+.2f}%")
                    logger.info(f"   ⏰ 업데이트: {allocation_data.get('timestamp', 'N/A')}")
                    logger.info("=" * 80)
                    
                    return allocated_budget
            
            logger.warning(f"⚠️ {bot_name}의 예산 할당 정보를 찾을 수 없습니다. 기본 예산을 사용합니다.")
            return None
            
        except Exception as e:
            logger.error(f"❌ 예산 할당 파일 읽기 오류: {str(e)}")
            logger.info("💡 기본 예산을 사용합니다.")
            return None

    def _send_creation_message(self):
        """설정 파일 생성 시 안내 메시지 전송 - 🔥 순수 원전 3종목 특화 버전 (4개봇 아키텍처)"""
        try:
            setup_msg = f"🔥 순수 원전 3종목 수직통합 시스템 설정 완료!\n"
            setup_msg += f"📁 파일: {self.config_path}\n"
            setup_msg += f"💰 초기 예산: ${self.config['absolute_budget']:,} (4개봇 재배분)\n"
            setup_msg += f"📊 예산 전략: {self.config['absolute_budget_strategy']}\n"
            setup_msg += f"🎯 분할 차수: {self.config['div_num']:.0f}차수 (안정적 장기투자)\n"
            setup_msg += f"💱 통화: {self.config['currency']}\n\n"
            
            # 🔥 순수 원전 수직통합 하이브리드 보호 시스템 강조
            setup_msg += f"🔥 **순수 원전 수직통합 하이브리드 보호 시스템 완전 적용**\n"
            setup_msg += f"✅ 원전 공급망 + 하이브리드 보호 완벽 결합\n"
            setup_msg += f"✅ 세계 유일 완전 수직통합 (채굴→농축→기술)\n"
            setup_msg += f"✅ 정부 정책 100% 수혜 + 에너지 안보\n"
            setup_msg += f"✅ 부분매도 + 트레일링 이중 안전망\n"
            setup_msg += f"✅ 5차수 안정 투자 + 장기 성장\n"
            setup_msg += f"✅ 러시아 의존 탈피 + 원전 르네상스\n\n"
            
            setup_msg += f"🎯 **순수 원전 3종목 하이브리드 설정**:\n"
            
            target_stocks = self.config.get('target_stocks', {})
            # 🔥 VRT, RKLB 완전 제거, LEU 추가
            nuclear_hybrid_info = {
                "CCJ": ("14% 부분매도(20%)", "7% 응급트레일링", "우라늄 채굴 안정주 (5주→1주씩)"),
                "LEU": ("15% 부분매도(33%)", "8% 응급트레일링", "HALEU 농축 독점 (3주→1주씩)"),  # 🔥 신규 추가
                "BWXT": ("12% 즉시매도(33%)", "6% 응급트레일링", "SMR 기술 선도 (8주→2주씩)")
            }
            
            for stock_code, stock_config in target_stocks.items():
                allocated = self.config['absolute_budget'] * stock_config.get('weight', 0)
                partial_info, trailing_info, description = nuclear_hybrid_info.get(stock_code, ("설정됨", "설정됨", "하이브리드 적용"))
                
                # 하이브리드 설정 정보 추출
                partial_config = stock_config.get('partial_sell_config', {})
                hybrid_config = partial_config.get('hybrid_protection', {})
                min_quantity = hybrid_config.get('min_quantity_for_partial', 2)
                
                setup_msg += f"• **{stock_config.get('name', stock_code)}** ({stock_code})\n"
                setup_msg += f"  💰 비중: {stock_config.get('weight', 0)*100:.1f}% (${allocated:,.0f})\n"
                setup_msg += f"  🎯 {description}\n"
                setup_msg += f"  💎 부분매도: {partial_info}\n"
                setup_msg += f"  🛡️ 응급보호: {trailing_info}\n"
                setup_msg += f"  📊 최소수량: {min_quantity}주 이상시 적용\n\n"
            
            # 🔥 순수 원전 수직통합 시스템 핵심 장점
            setup_msg += f"🚀 **순수 원전 수직통합 시스템 핵심 장점**:\n"
            setup_msg += f"✅ 완전 공급망: 채굴(CCJ)→농축(LEU)→기술(BWXT)\n"
            setup_msg += f"✅ 독점적 지위: 각 분야 독점/선도 기업만 선별\n"
            setup_msg += f"✅ 정부 수혜: 에너지 안보 + 러시아 의존 탈피\n"
            setup_msg += f"✅ 확실한 수익: 부분매도로 조기 확보\n"
            setup_msg += f"✅ 무제한 참여: 잔여 물량으로 상승 기회\n"
            setup_msg += f"✅ 빠른 보호: 트레일링으로 급락 대응\n"
            setup_msg += f"✅ 이중 안전망: 부분매도 + 트레일링\n"
            setup_msg += f"✅ 심리적 안정: 확실한 수익으로 편안함\n"
            setup_msg += f"✅ 현실적 실행: 1주 단위 실제 거래 가능\n\n"
            
            # 🔥 4개봇 아키텍처 내 역할
            setup_msg += f"🏗️ **4개봇 아키텍처 내 역할**:\n"
            setup_msg += f"🏭 원전봇(나): 안정성 담당 (41% 비중) - 5차수\n"
            setup_msg += f"🤖 AI봇: 성장성 담당 (NVDA+VRT+PLTR) - 3차수\n"
            setup_msg += f"🚀 미래기술봇: 혁신성 담당 (RKLB+IONQ) - 3차수\n"
            setup_msg += f"💼 빅테크봇: 방어성 담당 (GOOGL+AMZN) - 3차수\n\n"
            
            setup_msg += f"📊 **즉시 적용 효과 (순수 원전)**:\n"
            setup_msg += f"💰 수익 확보: 기존 0% → 즉시 부분매도 실행\n"
            setup_msg += f"🛡️ 리스크 감소: 최대 손실 대폭 감소\n"
            setup_msg += f"⚡ 회전율 향상: 빠른 수익 확보로 효율성 증대\n"
            setup_msg += f"🎯 테마 순수성: 100% 원전 집중 완성\n\n"
            
            setup_msg += f"🔧 **수량 기반 현실성**:\n"
            setup_msg += f"• 2주 이상 보유시에만 부분매도 실행\n"
            setup_msg += f"• 부분매도 후 최소 1주 보장\n"
            setup_msg += f"• 1주 단위 실제 거래 가능한 현실적 매도\n"
            setup_msg += f"• 수량 변화에 따라 자동으로 비율 조정\n\n"
            
            setup_msg += f"💡 **설정 변경 후 봇을 재시작하면 자동 적용됩니다.**"
            
            # Discord 전송
            if self.config.get("use_discord_alert", True):
                discord_alert.SendMessage(setup_msg)
                
            logger.info("✅ 순수 원전 3종목 수직통합 시스템 설정 생성 메시지 전송 완료")
            
        except Exception as e:
            logger.error(f"원전봇 설정 생성 메시지 전송 오류: {str(e)}")

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
            logger.info(f"✅ 설정 파일 저장 완료: {self.config_path}")
        except Exception as e:
            logger.error(f"설정 파일 저장 중 오류: {str(e)}")
    
    # 속성 접근자들 (기존 유지)
    @property
    def use_absolute_budget(self):
        return self.config.get("use_absolute_budget", True)
    
    # @property
    # def absolute_budget(self):
    #     return self.config.get("absolute_budget", 10000)  # $10,000로 변경

    @property
    def absolute_budget(self):
        # 1. 먼저 중앙에서 할당된 예산 확인
        allocated_budget = self.load_allocated_budget()
        
        # 2. 할당된 예산이 있으면 사용
        if allocated_budget is not None:
            return allocated_budget
        
        # 3. 없으면 설정 파일의 기본값 사용
        default_budget = self.config.get("absolute_budget", 3000)  # 원전봇 기본 $3,000
        logger.info(f"💡 기본 예산 사용: ${default_budget:,.0f}")
        return default_budget

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
        return self.config.get("bot_name", "SmartMagicSplitBot_US")
    
    @property
    def div_num(self):
        return self.config.get("div_num", 5.0)
    
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
    config_path = "smart_split_config_us.json"
    
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
        self.config = config  # 🔥 ai_cash_target_seller.py에서 discord 알림 발송 처리 설정

        # 🔥 독립 성과 추적기 추가
        self.performance_tracker = IndependentPerformanceTracker(
            bot_name="MainBot",
            initial_asset=config.absolute_budget,
            target_stocks=list(config.target_stocks.keys())
        )
        logger.info(f"✅ 독립 성과 추적 시스템 초기화 완료")
        self.update_budget()
        self._upgrade_json_structure_if_needed()
        # 🔥 뉴스 캐시 초기화 추가
        self.news_cache = {}
        self.last_news_check = {}  # 종목별 마지막 뉴스 체크 시간        

        # 🔥 알림 캐시 초기화 (3시간 동안 중복 알림 방지)
        self.alert_cache = {}
        self.ALERT_CACHE_DURATION = 3 * 60 * 60  # 3시간 (초 단위)
        logger.info(f"✅ 알림 캐시 시스템 초기화 완료 (중복 방지: 3시간)")

        # 🔥 변동성 기반 적응형 시스템 초기화
        self.log_volatility_analysis_summary()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🆕 AI Cash Target Seller 초기화 + 로거 전달
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.logger = logger
        if CASH_TARGET_ENABLED:
            try:
                # 1단계: 로거 설정 (Cash Target Seller 모듈에 전달)
                set_cash_seller_logger(self.logger)
                
                # 2단계: 인스턴스 생성
                self.cash_target_seller = AICashTargetSeller(self)
                
                # 3단계: 초기화 완료 로그
                self.logger.info("✅ AI Cash Target Seller 초기화 완료")
                
            except Exception as e:
                self.logger.error(f"❌ AI Cash Target Seller 초기화 실패: {e}")
                import traceback
                traceback.print_exc()
                self.cash_target_seller = None
        else:
            self.cash_target_seller = None
            self.logger.warning("⚠️ AI Cash Target Seller 비활성화 (모듈 미설치)")
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def should_run_cash_target_seller(self):
        """
        AI 현금확보 로직 실행 시점 판단
        
        [실행 전략]
        - 미국 정규장 오픈 후 30분 경과 (한국시간 00:00 이후)
        - 장 마감 30분 전까지 (한국시간 05:30 이전)
        - 초기 변동성 진정 후 안정된 시점에 현금 확보
        
        Returns:
            bool: 실행 가능 여부
        """
        try:
            import pytz
            
            # 한국 시간 가져오기
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst)
            current_hour = now_kst.hour
            current_minute = now_kst.minute
            current_time = current_hour * 60 + current_minute  # 분 단위로 변환
            
            # 실행 가능 시간대: 00:00 ~ 05:30 (한국시간)
            # = 미국 장 오픈 후 30분 ~ 마감 30분 전
            start_time = 0 * 60 + 0      # 00:00 (0분)
            end_time = 5 * 60 + 30        # 05:30 (330분)
            
            # 시간대 체크
            if start_time <= current_time < end_time:
                logger.debug(f"✅ AI 현금확보 실행 가능 시간대: {current_hour:02d}:{current_minute:02d} KST")
                return True
            else:
                logger.debug(f"⏭️ AI 현금확보 실행 불가 시간대: {current_hour:02d}:{current_minute:02d} KST "
                            f"(가능시간: 00:00~05:30)")
                return False
                
        except Exception as e:
            logger.error(f"AI 현금확보 실행 시점 체크 오류: {e}")
            # 오류 시 안전하게 실행 허용 (기존 동작 유지)
            return True

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
            # if current_holdings > 0:
            #     logger.info(f"✅ {stock_code} 현재 보유 중({current_holdings}주) - 쿨다운 면제")
            #     return True

            # 개선: 보유 여부와 무관하게 쿨다운 체크 진행
            logger.info(f"📊 {stock_code} 보유현황: {current_holdings}주 (쿨다운 체크 진행)")
            
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
        """JSON 구조 업그레이드: 부분매도 지원을 위한 필드 추가 - 🔥 완전한 부분매도 버전"""
        is_modified = False
        
        for stock_data in self.split_data_list:
            for magic_data in stock_data['MagicDataList']:
                # 🔥 기존 필드들 (CurrentAmt, SellHistory, EntryDate) - 기존 로직 유지
                if 'CurrentAmt' not in magic_data and magic_data['IsBuy']:
                    magic_data['CurrentAmt'] = magic_data['EntryAmt']
                    is_modified = True
                
                if 'SellHistory' not in magic_data:
                    magic_data['SellHistory'] = []
                    is_modified = True
                    
                # 🔥 수정된 EntryDate 필드 추가 로직
                if 'EntryDate' not in magic_data:
                    if magic_data['IsBuy']:
                        # 🔥 기존 매수 데이터는 빈 문자열로 설정 (날짜 불명)
                        magic_data['EntryDate'] = ""
                        logger.warning(f"기존 매수 데이터 발견: EntryDate를 빈 문자열로 설정 (쿨다운 무시됨)")
                    else:
                        # 매수하지 않은 차수는 빈 문자열
                        magic_data['EntryDate'] = ""
                    is_modified = True

                # 🔥🔥🔥 새로 추가: 부분매도 시스템 필드들 🔥🔥🔥
                if 'PartialSellHistory' not in magic_data:
                    """부분매도 이력 저장용 배열
                    각 부분매도마다 다음 정보 저장:
                    - date, time, price, amount, remaining_amount
                    - sell_ratio, return_pct, reason, stage, is_full_sell
                    """
                    magic_data['PartialSellHistory'] = []
                    is_modified = True
                    
                if 'OriginalAmt' not in magic_data:
                    """원래 매수 수량 (부분매도 추적용)
                    부분매도를 통해 CurrentAmt가 변해도 
                    원래 얼마나 샀는지 기억하기 위함
                    """
                    if magic_data.get('IsBuy', False):
                        # 이미 매수한 포지션이면 현재 EntryAmt를 원본으로 설정
                        magic_data['OriginalAmt'] = magic_data.get('EntryAmt', 0)
                    else:
                        # 아직 매수하지 않은 포지션은 0
                        magic_data['OriginalAmt'] = 0
                    is_modified = True
                    
                if 'PartialSellStage' not in magic_data:
                    """부분매도 단계 추적
                    0: 부분매도 미실행 (완전 보유)
                    1: 1차 부분매도 완료
                    2: 2차 부분매도 완료  
                    3: 최종 전량매도 완료
                    """
                    magic_data['PartialSellStage'] = 0
                    is_modified = True
                    
                if 'RemainingRatio' not in magic_data:
                    """남은 보유 비율 (0.0 ~ 1.0)
                    1.0 = 100% 보유 (부분매도 안함)
                    0.7 = 70% 보유 (30% 부분매도함)
                    0.0 = 0% 보유 (전량매도함)
                    """
                    if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                        magic_data['RemainingRatio'] = 1.0  # 완전 보유
                    else:
                        magic_data['RemainingRatio'] = 0.0  # 보유 없음
                    is_modified = True
                    
                if 'MaxProfitBeforePartialSell' not in magic_data:
                    """부분매도 이전 최고 수익률
                    부분매도 후 트레일링 스톱의 기준점으로 사용
                    첫 부분매도 실행 전까지의 최고 수익률을 기록
                    """
                    magic_data['MaxProfitBeforePartialSell'] = 0.0
                    is_modified = True

                # 🔥 기존 포지션 데이터 검증 및 보정
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    # OriginalAmt가 CurrentAmt보다 작으면 보정 (데이터 무결성)
                    if magic_data.get('OriginalAmt', 0) < magic_data.get('CurrentAmt', 0):
                        magic_data['OriginalAmt'] = magic_data['CurrentAmt']
                        logger.info(f"OriginalAmt 보정: CurrentAmt({magic_data['CurrentAmt']})로 설정")
                        is_modified = True
                    
                    # RemainingRatio 재계산 (데이터 무결성)
                    original = magic_data.get('OriginalAmt', 1)
                    current = magic_data.get('CurrentAmt', 0)
                    if original > 0:
                        calculated_ratio = current / original
                        stored_ratio = magic_data.get('RemainingRatio', 1.0)
                        
                        # 비율이 5% 이상 차이나면 보정
                        if abs(calculated_ratio - stored_ratio) > 0.05:
                            magic_data['RemainingRatio'] = calculated_ratio
                            logger.info(f"RemainingRatio 보정: {stored_ratio:.2f} → {calculated_ratio:.2f}")
                            is_modified = True
        
        if is_modified:
            logger.info("🔥 JSON 구조 업그레이드 완료: 부분매도 시스템 지원 필드 추가")
            logger.info("   ✅ PartialSellHistory: 부분매도 이력 추적")
            logger.info("   ✅ OriginalAmt: 원본 매수량 기록")
            logger.info("   ✅ PartialSellStage: 부분매도 단계 추적")
            logger.info("   ✅ RemainingRatio: 잔여 보유 비율")
            logger.info("   ✅ MaxProfitBeforePartialSell: 부분매도 전 최고점")
            logger.info("   🔄 기존 데이터 무결성 검증 및 보정 완료")
            self.save_split_data()

    def calculate_dynamic_budget(self):
        """🔥 동적 예산 계산 - 중앙 예산 조정기 우선 적용"""
        try:
            # 🔥🔥🔥 1단계: 중앙 예산 조정기에서 할당된 예산이 있는지 확인
            allocated_budget = config.load_allocated_budget()
            
            if allocated_budget is not None:
                # 중앙에서 할당된 예산은 이미 성과가 반영되어 있으므로 그대로 사용
                logger.info("=" * 80)
                logger.info("🎯 중앙 예산 조정기 할당 예산 적용")
                logger.info(f"   💰 할당 예산: ${allocated_budget:,.0f}")
                logger.info(f"   📊 이 예산은 이미 성과가 반영된 최종 예산입니다")
                logger.info(f"   ✅ 추가 배수 적용 없이 그대로 사용합니다")
                logger.info("=" * 80)
                return allocated_budget
            
            # 🔥🔥🔥 2단계: 중앙 할당 예산이 없으면 독립 동적 계산 수행
            logger.info("💡 중앙 예산 조정기 미사용 → 독립 동적 예산 계산 시작")
            
            # 미국주식 계좌 정보 조회 (USD 기준)
            balance = SafeKisUS.safe_get_balance("USD")
            if not balance:
                logger.error("미국주식 계좌 정보 조회 실패")
                return config.absolute_budget
                
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 초기 자산 설정 (첫 실행시)
            if config.initial_total_asset == 0:
                config.update_initial_asset(current_total)
                logger.info(f"🎯 초기 총 자산 설정: ${current_total:,.0f}")
            
            # 전략별 예산 계산
            strategy = config.absolute_budget_strategy
            base_budget = config.absolute_budget
            
            if strategy == "proportional":
                # performance_tracker 존재 여부 확인 (안전장치)
                if hasattr(self, 'performance_tracker') and self.performance_tracker:
                    # 독립적 성과 기반 동적 조정
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
                
                # 성과 추적 업데이트
                config.update_performance(performance_rate)
                
                # 성과 기반 multiplier 계산
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
                # adaptive 전략
                loss_tolerance = config.config.get("budget_loss_tolerance", 0.25)
                min_budget = base_budget * (1 - loss_tolerance)
                
                if current_total >= min_budget:
                    dynamic_budget = base_budget
                else:
                    dynamic_budget = max(current_total * 0.8, min_budget)
                    
            else:  # "strict"
                # 고정 예산
                dynamic_budget = base_budget
            
            # 안전장치: 현금 잔고 기반 제한
            safety_ratio = config.config.get("safety_cash_ratio", 0.9)
            max_safe_budget = remain_money * safety_ratio
            
            if dynamic_budget > max_safe_budget:
                logger.warning(f"💰 현금 잔고 기반 예산 제한: ${dynamic_budget:,.0f} → ${max_safe_budget:,.0f}")
                dynamic_budget = max_safe_budget
            
            # 추가 안전장치: 독립 성과 기반 제한 (performance_tracker 존재시만)
            if strategy == "proportional" and hasattr(self, 'performance_tracker') and self.performance_tracker:
                perf_data = self.performance_tracker.calculate_bot_specific_performance()
                if perf_data:
                    max_safe_independent = perf_data['total_current_asset'] * 0.95
                    if dynamic_budget > max_safe_independent:
                        logger.warning(f"🎯 독립 자산 기반 예산 제한: ${dynamic_budget:,.0f} → ${max_safe_independent:,.0f}")
                        dynamic_budget = max_safe_independent
            
            # 로깅
            logger.info(f"📊 미국주식 독립 동적 예산 계산 결과:")
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
        """미국 시장 추세와 타이밍을 감지하는 함수"""
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
            
            # 🔥 당일 변화율 계산 (추가)
            prev_close = spy_df['close'].iloc[-2]
            daily_change = (current_index - prev_close) / prev_close * 100
            
            # 시장 상태 판단
            if current_index > spy_ma5 > spy_ma20 > spy_ma60:
                result = "strong_uptrend"  # 강한 상승 추세
            elif current_index > spy_ma5 and spy_ma5 > spy_ma20:
                result = "uptrend"         # 상승 추세
            elif current_index < spy_ma5 and spy_ma5 < spy_ma20:
                result = "downtrend"       # 하락 추세
            elif current_index < spy_ma5 < spy_ma20 < spy_ma60:
                result = "strong_downtrend"  # 강한 하락 추세
            else:
                result = "neutral"         # 중립
            
            # 🔥🔥🔥 로깅 추가! (핵심 개선) 🔥🔥🔥
            logger.info(f"📊 시장 타이밍 감지 결과: {result}")
            logger.info(f"   💰 SPY 현재가: ${current_index:.2f} ({daily_change:+.2f}%)")
            logger.info(f"   📈 이평선: MA5=${spy_ma5:.2f}, MA20=${spy_ma20:.2f}, MA60=${spy_ma60:.2f}")
            
            # 🚨 급락 경고 (선택사항 - 더 눈에 띄게)
            if daily_change <= -2.0:
                logger.error(f"🚨🚨🚨 시장 급락 감지! SPY {daily_change:.2f}% 하락!")
            elif daily_change <= -1.0:
                logger.warning(f"⚠️ 시장 하락 주의! SPY {daily_change:.2f}% 하락")
            
            return result
            
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
        
    # def get_partial_sell_config(self, stock_code):
    #     """종목별 부분매도 설정 가져오기"""
    #     try:
    #         target_stocks = config.target_stocks
    #         stock_config = target_stocks.get(stock_code, {})
    #         partial_config = stock_config.get('partial_sell_config', {})
            
    #         # 기본값 설정 (부분매도 비활성화)
    #         if not partial_config.get('enable', False):
    #             return None
                
    #         return {
    #             'first_sell_threshold': partial_config.get('first_sell_threshold', 15),
    #             'first_sell_ratio': partial_config.get('first_sell_ratio', 0.3),
    #             'second_sell_threshold': partial_config.get('second_sell_threshold', 25),
    #             'second_sell_ratio': partial_config.get('second_sell_ratio', 0.4),
    #             'final_sell_threshold': partial_config.get('final_sell_threshold', 35),
    #             'trailing_after_partial': partial_config.get('trailing_after_partial', 0.05)
    #         }
            
    #     except Exception as e:
    #         logger.error(f"부분매도 설정 가져오기 오류: {str(e)}")
    #         return None

    def get_partial_sell_config(self, stock_code):
        """종목별 부분매도 설정 가져오기 - 적응형 시스템 적용"""
        return self.get_adaptive_partial_sell_config(stock_code)

    def log_volatility_analysis_summary(self):
        """변동성 분석 요약 로깅 - 시작시 전체 종목 분석"""
        try:
            logger.info("=" * 60)
            logger.info("🔥 원전봇 변동성 기반 적응형 시스템 초기화")
            logger.info("=" * 60)
            
            target_stocks = config.target_stocks
            
            for stock_code in target_stocks.keys():
                try:
                    # 각 종목별 변동성 분석 및 적응형 임계값 계산
                    adaptive_threshold = self.calculate_volatility_adjusted_threshold(stock_code)
                    
                    # 기존 설정과 비교
                    stock_config = target_stocks.get(stock_code, {})
                    original_threshold = stock_config.get('partial_sell_config', {}).get('first_sell_threshold', 12)
                    
                    # 개선 효과 계산
                    improvement_pct = ((original_threshold - adaptive_threshold) / original_threshold) * 100
                    
                    if improvement_pct > 0:
                        effect = f"🟢 {improvement_pct:.1f}% 완화 (빠른 수익확보)"
                    elif improvement_pct < -5:
                        effect = f"🔴 {abs(improvement_pct):.1f}% 강화 (신중한 매도)"
                    else:
                        effect = f"🟡 {abs(improvement_pct):.1f}% 미조정 (적정수준)"
                    
                    logger.info(f"📊 {stock_code}: {original_threshold}% → {adaptive_threshold:.1f}% ({effect})")
                    
                except Exception as e:
                    logger.error(f"❌ {stock_code} 변동성 분석 실패: {str(e)}")
            
            logger.info("=" * 60)
            logger.info("🎯 변동성 기반 적응형 시스템 준비 완료!")
            logger.info("📈 예상 효과: 수익확보 속도 40-60% 향상, 기회비용 50% 감소")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ 변동성 분석 요약 로깅 오류: {str(e)}")

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

                # logger.info(f"📋 {stock_code} {position_num}차 매도 기록을 GlobalSellHistory에 즉시 백업 완료")
                
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

                    logger.info(f"📋 {stock_code} {position_num}차 매도 기록을 GlobalSellHistory에 즉시 백업 완료")
                
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
            
            # 🔥🔥🔥 현재가 조회 with API 호출 제한 대응 🔥🔥🔥
            current_price = None
            max_retries = 3
            retry_delay = 2  # 초
            
            for attempt in range(max_retries):
                try:
                    # API 호출 간 딜레이 추가 (초당 거래 제한 회피)
                    if attempt > 0:
                        time.sleep(retry_delay)
                        logger.info(f"🔄 {stock_code} 현재가 조회 재시도 {attempt + 1}/{max_retries}")
                    
                    current_price = SafeKisUS.safe_get_current_price(stock_code)
                    
                    if current_price and current_price > 0:
                        logger.info(f"✅ {stock_code} 현재가 조회 성공: ${current_price:.2f}")
                        break
                    else:
                        logger.warning(f"⚠️ {stock_code} 현재가 조회 결과가 None 또는 0")
                        
                except Exception as price_error:
                    logger.error(f"❌ {stock_code} 현재가 조회 시도 {attempt + 1} 실패: {str(price_error)}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
            
            # 🔥 현재가 조회 실패 시 대체 로직
            if current_price is None or current_price <= 0:
                logger.error(f"🚨 {stock_code} 현재가 조회 최종 실패 - 전일 종가로 대체")
                current_price = prev_close
                
                # 전일 종가도 문제가 있으면 None 반환
                if current_price is None or current_price <= 0:
                    logger.error(f"🚨 {stock_code} 전일 종가도 사용 불가 - 지표 계산 중단")
                    return None
            
            # 조정폭 계산 (current_price가 None이 아님을 보장)
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

    def check_account_cash_safety(self, min_safety_cash=800, alert_threshold=1000, upcoming_buy_cost=0):
        """
        계좌 레벨 현금 안전망 체크 - 오버커밋 시스템 최종 방어선
        🔥 개선: 매수 후 예상 잔액까지 검증
        
        Args:
            min_safety_cash: 최소 안전 현금 (이하면 매수 차단)
            alert_threshold: 경고 임계값 (이하면 경고만, 매수는 허용)
            upcoming_buy_cost: 예정된 매수 비용 (매수가 * 수량 + 수수료) - 🔥 NEW
        
        Returns:
            tuple: (허용여부, 상태메시지, 현금잔고)
        """
        try:
            # 실제 계좌 현금 잔고 조회
            balance = SafeKisUS.safe_get_balance("USD")
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 🔥 핵심 개선: 매수 후 예상 잔액 계산
            estimated_cash_after_buy = remain_money - upcoming_buy_cost
            
            # 🔥 매수 후 잔액 기준으로 판단 (원본은 현재 잔액만 체크)
            if estimated_cash_after_buy < min_safety_cash:
                # 🚨 위험: 매수하면 안전선 아래로 떨어짐
                msg = f"🚨 매수 후 현금 부족 예상! 현재: ${remain_money:.0f} - 매수: ${upcoming_buy_cost:.0f} = ${estimated_cash_after_buy:.0f} < 안전선: ${min_safety_cash}"
                logger.error(msg)
                
                # 🔥 캐시 체크: 3시간 내 동일 알림 방지 (원본 로직 유지)
                alert_key = f"cash_critical_{min_safety_cash}"
                current_time = time.time()
                
                if alert_key not in self.alert_cache or (current_time - self.alert_cache[alert_key]) > self.ALERT_CACHE_DURATION:
                    # Discord 긴급 알림 (3시간마다만 전송)
                    if config.config.get("use_discord_alert", True):
                        alert_msg = (
                            f"🚨 **매수 차단: 현금 안전선 보호**\n\n"
                            f"💰 현재 현금: ${remain_money:,.0f}\n"
                            f"💸 매수 비용: ${upcoming_buy_cost:,.0f}\n"
                            f"📉 매수 후 잔액: ${estimated_cash_after_buy:,.0f}\n"
                            f"🛡️ 안전선: ${min_safety_cash:,.0f}\n"
                            f"⚠️ 부족액: ${min_safety_cash - estimated_cash_after_buy:,.0f}\n\n"
                            f"⚠️ 매수 실행시 안전선 아래로 떨어지므로 차단됨\n"
                            f"🔄 해결: 포지션 정리 후 현금 확보 필요"
                        )
                        discord_alert.SendMessage(alert_msg)
                        
                        # 캐시 업데이트
                        self.alert_cache[alert_key] = current_time
                        logger.info(f"✅ 현금 긴급 알림 전송 완료 (다음 알림: 3시간 후)")
                else:
                    time_remaining = self.ALERT_CACHE_DURATION - (current_time - self.alert_cache[alert_key])
                    hours_remaining = time_remaining / 3600
                    logger.info(f"⏳ 현금 긴급 알림 대기 중 (남은 시간: {hours_remaining:.1f}시간)")
                
                return False, msg, remain_money
                
            elif estimated_cash_after_buy < alert_threshold:
                # ⚠️ 경고: 매수는 허용하지만 주의
                msg = f"⚠️ 매수 후 현금 여유 부족! 예상: ${estimated_cash_after_buy:.0f} < 경고선: ${alert_threshold}"
                logger.warning(msg)
                
                # 🔥 캐시 체크: 경고 레벨도 3시간 내 중복 방지 (원본 로직 유지)
                alert_key = f"cash_warning_{alert_threshold}"
                current_time = time.time()
                
                if alert_key not in self.alert_cache or (current_time - self.alert_cache[alert_key]) > self.ALERT_CACHE_DURATION:
                    if config.config.get("use_discord_alert", True):
                        alert_msg = (
                            f"⚠️ **현금 경고 (매수 허용)**\n\n"
                            f"💰 현재 현금: ${remain_money:,.0f}\n"
                            f"💸 매수 비용: ${upcoming_buy_cost:,.0f}\n"
                            f"📉 매수 후 잔액: ${estimated_cash_after_buy:,.0f}\n"
                            f"🛡️ 경고선: ${alert_threshold:,.0f}\n\n"
                            f"✅ 매수는 진행되지만 추가 매수 주의 필요\n"
                            f"📊 권장: 추가 매수 신중 검토"
                        )
                        discord_alert.SendMessage(alert_msg)
                        
                        self.alert_cache[alert_key] = current_time
                        logger.info(f"✅ 현금 주의 알림 전송 완료 (다음 알림: 3시간 후)")
                else:
                    time_remaining = self.ALERT_CACHE_DURATION - (current_time - self.alert_cache[alert_key])
                    hours_remaining = time_remaining / 3600
                    logger.info(f"⏳ 현금 주의 알림 대기 중 (남은 시간: {hours_remaining:.1f}시간)")
                
                return True, msg, remain_money
                
            else:
                # ✅ 안전: 매수 후에도 충분한 현금 확보
                msg = f"✅ 현금 안전 (매수 후: ${estimated_cash_after_buy:.0f} ≥ 안전선: ${min_safety_cash})"
                logger.debug(msg)
                return True, msg, remain_money
                
        except Exception as e:
            # API 오류 시 안전하게 매수 차단
            error_msg = f"계좌 현금 체크 오류: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, 0

    def load_ai_protection_mode(self):
            """AI 수익 보호 판단 로드"""
            try:
                protection_file = "profit_protection.json"
                
                if not os.path.exists(protection_file):
                    logger.debug("ℹ️ profit_protection.json 없음 - 기존 방식 유지")
                    return None
                
                with open(protection_file, 'r', encoding='utf-8') as f:
                    protection = json.load(f)
                
                # 유효성 검증
                if not protection.get('validated', False):
                    logger.warning("⚠️ AI 판단 검증 실패 - 기존 방식 유지")
                    return None
                
                # 타임스탬프 체크 (6시간 이내만 유효)
                timestamp_str = protection.get('timestamp')
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    age = datetime.now() - timestamp
                    
                    if age > timedelta(hours=10):
                        logger.warning(f"⚠️ AI 판단 만료 ({age.total_seconds()/3600:.1f}시간 전)")
                        return None
                    
                    logger.info(f"✅ AI 판단 로드 성공 ({age.total_seconds()/3600:.1f}시간 전)")
                
                return protection
                
            except Exception as e:
                logger.error(f"❌ AI 판단 로드 실패: {e}")
                return None

    def calculate_dynamic_cash_reserve(self, total_asset):
        """
        🔥 AI 통합 버전 - 동적 현금 안전선 계산
        
        우선순위:
        1. AI 판단 (있으면 최우선)
        2. 동적 계산 (시장 기반)
        3. Config 고정값 (폴백)
        
        Args:
            total_asset (float): 현재 총 자산
            
        Returns:
            dict: {
                'min_safety_cash': float,      # 최소 안전 현금
                'alert_threshold': float,       # 경고 임계값
                'source': str,                  # 출처 ('AI', 'dynamic', 'config_fallback')
                'ai_target_cash_ratio': float,  # AI 목표 비율 (AI일 때만)
                'urgency': str                  # 긴급도 (AI일 때만)
            }
        """
        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 [STEP 1] AI 판단 우선 확인
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            protection_mode = self.load_ai_protection_mode()
            
            if protection_mode and protection_mode.get('protection_required'):
                cash_strategy = protection_mode.get('cash_strategy', {})
                target_cash_ratio = cash_strategy.get('target_cash_ratio', 0.15)
                urgency = cash_strategy.get('urgency', 'medium')
                
                # AI 목표 현금 비율 기준으로 안전선 계산
                min_safety_cash = total_asset * target_cash_ratio
                
                # 긴급도에 따라 경고선 조정
                urgency_multipliers = {
                    'high': 0.9,      # HIGH: 목표의 90%까지도 경고
                    'medium': 0.8,    # MEDIUM: 목표의 80%까지 경고
                    'low': 0.7        # LOW: 목표의 70%까지 경고
                }
                multiplier = urgency_multipliers.get(urgency, 0.8)
                alert_threshold = min_safety_cash / multiplier
                
                logger.warning("=" * 80)
                logger.warning("🤖 AI 기반 현금 안전선 적용!")
                logger.warning(f"   📊 시장 국면: {protection_mode.get('market_phase', 'N/A').upper()}")
                logger.warning(f"   ⚠️ 위험 수준: {protection_mode.get('risk_level', 'N/A')}")
                logger.warning(f"   🎯 목표 현금: {target_cash_ratio*100:.0f}% (${min_safety_cash:,.0f})")
                logger.warning(f"   🛡️ 안전선: ${min_safety_cash:,.0f}")
                logger.warning(f"   ⚡ 긴급도: {urgency.upper()}")
                
                # 핵심 인사이트도 로깅
                key_insights = protection_mode.get('key_insights', [])
                if key_insights:
                    logger.warning(f"   💡 AI 판단 근거:")
                    for idx, insight in enumerate(key_insights[:3], 1):
                        logger.warning(f"      {idx}. {insight}")
                
                logger.warning("=" * 80)
                
                return {
                    'min_safety_cash': round(min_safety_cash, 2),
                    'alert_threshold': round(alert_threshold, 2),
                    'source': 'AI',
                    'ai_target_cash_ratio': target_cash_ratio,
                    'urgency': urgency
                }
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 [STEP 2] AI 없으면 기존 동적 계산
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # Level 1: 기본 비율 (Config)
            dynamic_reserve_config = config.config.get('dynamic_cash_reserve', {})
            base_safety_ratio = dynamic_reserve_config.get('base_safety_ratio', 0.12)
            base_alert_ratio = dynamic_reserve_config.get('base_alert_ratio', 0.15)
            
            # Level 2: 시장 국면 감지
            market_timing = self.detect_market_timing()
            
            market_multipliers = {
                "strong_uptrend": 0.5,
                "uptrend": 0.7,
                "neutral": 1.0,
                "downtrend": 1.5,
                "strong_downtrend": 2.0
            }
            market_multiplier = market_multipliers.get(market_timing, 1.0)
            
            # 최종 계산
            min_safety_cash = total_asset * base_safety_ratio * market_multiplier
            alert_threshold = total_asset * base_alert_ratio * market_multiplier
            
            # 안전 장치
            absolute_min = dynamic_reserve_config.get('absolute_min', 300)
            max_ratio_limit = dynamic_reserve_config.get('max_ratio_limit', 0.35)
            
            min_safety_cash = max(min_safety_cash, absolute_min)
            min_safety_cash = min(min_safety_cash, total_asset * max_ratio_limit)
            
            alert_threshold = max(alert_threshold, absolute_min * 1.2)
            alert_threshold = min(alert_threshold, total_asset * max_ratio_limit * 1.2)
            
            logger.debug(f"💰 동적 현금 안전선: ${min_safety_cash:,.0f} (시장: {market_timing})")
            
            return {
                'min_safety_cash': round(min_safety_cash, 2),
                'alert_threshold': round(alert_threshold, 2),
                'source': 'dynamic',
                'calculation_details': {
                    'total_asset': total_asset,
                    'base_safety_ratio': base_safety_ratio,
                    'market_timing': market_timing,
                    'market_multiplier': market_multiplier,
                    'final_safety_ratio': (min_safety_cash / total_asset * 100) if total_asset > 0 else 0
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 동적 현금 안전선 계산 오류: {e}")
            # 폴백: Config 고정값
            return {
                'min_safety_cash': 800,
                'alert_threshold': 1000,
                'source': 'config_fallback'
            }

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

    def get_technical_indicators(self, stock_code):
        """기존 기술적 지표 계산 함수 (호환성 유지)"""
        period, recent_period, recent_weight = self.determine_optimal_period(stock_code)
        return self.get_technical_indicators_weighted(
            stock_code, 
            period=period, 
            recent_period=recent_period, 
            recent_weight=recent_weight
        )

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

    def get_next_buying_position(self, stock_code):
        """다음 매수할 차수 정확히 계산"""
        try:
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return 1  # 데이터 없으면 1차부터
            
            # 🔥 현재 활성 포지션들 확인
            active_positions = []
            for i, magic_data in enumerate(stock_data_info['MagicDataList']):
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    active_positions.append(i + 1)  # 1-based
            
            if not active_positions:
                return 1  # 활성 포지션 없으면 1차
            
            # 🔥 다음 빈 차수 찾기
            max_position = len(stock_data_info['MagicDataList'])
            for position_num in range(1, max_position + 1):
                if position_num not in active_positions:
                    return position_num
            
            logger.warning(f"⚠️ {stock_code} 모든 차수가 활성화됨")
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

    def get_actual_sell_execution_price(self, stock_code, order_price, sell_amount, max_wait=30):
        """매도 실제 체결가 조회 - 반복 확인 방식 (최대 30초)"""
        try:
            logger.info(f"⏳ {stock_code} 매도 체결 확인 시작 (최대 {max_wait}초)")
            
            start_time = time.time()
            check_count = 0
            today = datetime.now().strftime("%Y%m%d")
            
            while time.time() - start_time < max_wait:
                check_count += 1
                time.sleep(5)  # 5초마다 체크
                
                # 최근 매도 주문 조회
                recent_orders = SafeKisUS.safe_get_order_list(stock_code, "SELL", "CLOSE", 1)
                if not recent_orders:
                    logger.debug(f"   {stock_code} 매도 주문 내역 없음 ({check_count}차 시도)")
                    continue  # 다음 체크로 넘어감
                
                # 오늘 날짜의 가장 최근 체결 주문 찾기
                for order in recent_orders:
                    if (order.get('OrderDate') == today and 
                        order.get('OrderResultAmt', 0) > 0 and  # 체결량 있음
                        order.get('OrderSatus') == 'Close'):     # 체결 완료
                        
                        actual_price = float(order.get('OrderAvgPrice', 0))
                        actual_amount = int(order.get('OrderResultAmt', 0))
                        
                        # 수량 검증
                        if actual_amount != sell_amount:
                            logger.debug(f"   {stock_code} 수량 불일치: 예상 {sell_amount}주 vs 실제 {actual_amount}주")
                            continue
                        
                        # 합리성 검증: 주문가와 5% 이상 차이나면 제외
                        if actual_price > 0:
                            price_diff_pct = abs(actual_price - order_price) / order_price * 100
                            if price_diff_pct <= 5.0:  # 5% 이내만 허용
                                elapsed = int(time.time() - start_time)
                                logger.info(f"✅ {stock_code} 매도 체결 완료! ${actual_price:.2f} ({actual_amount}주, {check_count}차 시도, {elapsed}초 소요)")
                                return actual_price
                            else:
                                logger.warning(f"⚠️ {stock_code} 체결가 차이 과도: {price_diff_pct:.1f}%")
                
                # 진행 상황 로깅 (10초마다)
                if check_count % 2 == 0:
                    elapsed = int(time.time() - start_time)
                    logger.info(f"   ⏳ {stock_code} 매도 체결 대기 중... ({elapsed}/{max_wait}초, {check_count}차 시도)")
            
            # 30초 내 체결 확인 실패
            logger.warning(f"⏰ {stock_code} {max_wait}초 내 매도 체결 확인 실패 ({check_count}차 시도)")
            return None
            
        except Exception as e:
            logger.error(f"❌ {stock_code} 매도 실제 체결가 조회 오류: {str(e)}")
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

            # 🔥🔥🔥 이 부분 추가 🔥🔥🔥
            logger.info(f"⏳ {stock_name} API 반영 대기 중... (10초)")
            time.sleep(10)

            # 🔥 7. 개선된 체결 확인 (핵심 수정)
            logger.info(f"⏳ {stock_name} 체결 확인 시작 (최대 50)")
            start_time = time.time()
            check_count = 0
            
            while time.time() - start_time < 50:
                check_count += 1
                
                # 미국주식 보유 종목 조회
                my_stocks = SafeKisUS.safe_get_my_stock_list("USD")
                if my_stocks is None:
                    continue  # 다음 체크로 넘어감

                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        current_total = int(stock.get('StockAmt', 0))  # 현재 총 보유량
                        
                        # # 🔥🔥🔥 핵심 수정: 실제 체결가 조회 🔥🔥🔥
                        # actual_execution_price = self.get_actual_execution_price(stock_code, order_price)
                        
                        # # 실제 체결가 조회 실패 시 주문가 사용 (안전장치)
                        # if actual_execution_price is None:
                        #     actual_execution_price = order_price
                        #     logger.warning(f"⚠️ {stock_name} 실제 체결가 조회 실패 - 주문가 사용: ${order_price:.2f}")

                        # 🔥🔥🔥 핵심 수정: 증가분을 실제 체결량으로 계산 🔥🔥🔥
                        actual_executed = current_total - before_amount
                        
                        if actual_executed >= amount:  # 목표 수량 이상 체결
                            
                            # 체결 완료시 pending 제거
                            if stock_code in self.pending_orders:
                                del self.pending_orders[stock_code]
                            
                            # # 🔥 체결 완료 알림 (수정됨)
                            # if config.config.get("use_discord_alert", True):
                            #     msg = f"✅ {stock_name} 매수 체결!\n"
                            #     msg += f"💰 ${actual_execution_price:.2f} × {actual_executed}주\n"  # 🔥 실제 체결가/체결량
                            #     msg += f"📊 투자금액: ${total_investment:.2f}\n"
                            #     if abs(execution_diff) > 0.1:
                            #         msg += f"🎯 가격개선: ${execution_diff:+.2f}\n"
                            #     msg += f"⚡ 체결시간: {check_count * 5}초"
                            #     discord_alert.SendMessage(msg)
                            
                            # 🔧 개선된 동기화 호출 (핵심 수정)
                            try:

                                # 🔥 변수 초기화 먼저! (중요!)
                                actual_execution_price = order_price  # 기본값 설정
                                actual_executed = current_total - before_amount  # 실제 체결 수량

                                # 🔥 먼저 실제 체결가 조회 (3초 대기)
                                logger.info(f"⏳ {stock_name} 실제 체결가 조회 시작 (3초 대기)")
                                time.sleep(3)  # 주문내역 API 반영 대기

                                try:
                                    actual_execution_price_from_order = self.get_actual_execution_price(stock_code, order_price)
                                    
                                    if actual_execution_price_from_order:
                                        actual_execution_price = actual_execution_price_from_order
                                        logger.info(f"✅ {stock_name} 실제 체결가 조회 성공: ${actual_execution_price:.2f}")
                                    else:
                                        logger.warning(f"⚠️ {stock_name} 실제 체결가 조회 실패 - 주문가 사용: ${actual_execution_price:.2f}")
                                        
                                except Exception as price_error:
                                    logger.warning(f"⚠️ {stock_name} 체결가 조회 중 오류: {str(price_error)}")
                                    logger.warning(f"   주문가 사용: ${actual_execution_price:.2f}")
                                    # actual_execution_price는 이미 order_price로 초기화됨

                                # 🔥 가격 개선 계산 (Discord 알림 전에 먼저 계산!)
                                execution_diff = actual_execution_price - order_price
                                total_investment = actual_execution_price * actual_executed  # 🔥 수정: 실제 체결가 기준
                                actual_fee = self.calculate_trading_fee(actual_execution_price, actual_executed, True)

                                # 🔥 체결 완료 알림 (이제 모든 변수가 정의됨)
                                if config.config.get("use_discord_alert", True):
                                    msg = f"✅ {stock_name} 매수 체결!\n"
                                    msg += f"💰 ${actual_execution_price:.2f} × {actual_executed}주\n"
                                    msg += f"📊 투자금액: ${total_investment:.2f}\n"
                                    if abs(execution_diff) > 0.1:
                                        msg += f"🎯 가격개선: ${execution_diff:+.2f}\n"
                                    msg += f"⚡ 체결시간: {check_count * 5}초"
                                    discord_alert.SendMessage(msg)

                                # 🔥 체결 상세 정보 로깅
                                logger.info(f"✅ {stock_name} 매수 체결 완료!")
                                logger.info(f"   🎯 목표수량: {amount}주")
                                logger.info(f"   📊 매수 전 보유: {before_amount}주")
                                logger.info(f"   📊 매수 후 총보유: {current_total}주")
                                logger.info(f"   ✅ 실제 체결량: {actual_executed}주")
                                logger.info(f"   💰 주문가격: ${order_price:.2f}")
                                logger.info(f"   💰 체결가격: ${actual_execution_price:.2f}")
                                logger.info(f"   📊 가격개선: ${execution_diff:+.2f}")
                                logger.info(f"   💵 투자금액: ${total_investment:.2f}")
                                logger.info(f"   💸 실제수수료: ${actual_fee:.2f}")
                                logger.info(f"   🕐 체결시간: {check_count * 5}초")

                                # 현재 몇 차수 매수인지 파악
                                current_position_num = self.get_next_buying_position(stock_code)
                                if not current_position_num:
                                    logger.error(f"❌ {stock_code} 다음 매수 차수를 찾을 수 없음")
                                    return actual_execution_price, actual_executed, "체결 완료"  # 그래도 체결은 성공
                                
                                logger.info(f"📊 {stock_name} 매수 차수: {current_position_num}차")
                                
                                # 종목 데이터 찾기
                                stock_data_info = None
                                for data_info in self.split_data_list:
                                    if data_info['StockCode'] == stock_code:
                                        stock_data_info = data_info
                                        break
                                
                                if stock_data_info:
                                    magic_data_list = stock_data_info['MagicDataList']
                                    
                                    # 🔥🔥🔥 1단계: update_position_after_buy() 먼저 실행 🔥🔥🔥
                                    logger.info(f"🔄 {stock_name} {current_position_num}차 포지션 데이터 업데이트 시작")
                                    update_success, update_msg = self.update_position_after_buy(
                                        stock_code=stock_code,
                                        position_num=current_position_num,
                                        executed_amount=actual_executed,
                                        actual_price=actual_execution_price,
                                        magic_data_list=magic_data_list
                                    )
                                    
                                    if update_success:
                                        logger.info(f"✅ {stock_name} {current_position_num}차 포지션 데이터 업데이트 완료")
                                    else:
                                        logger.warning(f"⚠️ {stock_name} {current_position_num}차 업데이트 실패: {update_msg}")

                                    # 🔥🔥🔥 2단계: sync로 실제 체결가 정정 (개선) 🔥🔥🔥
                                    # 1차 실패 시 무조건 2차 시도, 가격 차이 있을 때도 2차 확인
                                    if not actual_execution_price_from_order:
                                        # 1차 조회 실패 → 2차 sync로 정확한 체결가 확인 필수
                                        logger.info(f"🔄 {stock_name} {current_position_num}차 1차 체결가 조회 실패 - 2차 sync 시도")
                                        sync_success = self.sync_position_after_buy_with_order_list(
                                            stock_code=stock_code,
                                            position_num=current_position_num, 
                                            order_price=order_price,
                                            expected_amount=actual_executed
                                        )
                                        
                                        if sync_success:
                                            logger.info(f"✅ {stock_name} {current_position_num}차 정확한 체결가 동기화 완료 (2차 성공)")
                                        else:
                                            logger.warning(f"⚠️ {stock_name} {current_position_num}차 2차 동기화도 실패 - 주문가 사용")
                                            
                                    elif abs(actual_execution_price - order_price) > 0.01:
                                        # 가격 차이 있음 → 추가 검증을 위한 2차 확인
                                        logger.info(f"🔄 {stock_name} {current_position_num}차 실제 체결가 동기화 시작")
                                        sync_success = self.sync_position_after_buy_with_order_list(
                                            stock_code=stock_code,
                                            position_num=current_position_num, 
                                            order_price=order_price,
                                            expected_amount=actual_executed
                                        )
                                        
                                        if sync_success:
                                            logger.info(f"✅ {stock_name} {current_position_num}차 정확한 체결가 동기화 완료")
                                        else:
                                            logger.warning(f"⚠️ {stock_name} {current_position_num}차 동기화 실패 (데이터는 이미 업데이트됨)")
                                    else:
                                        # 1차 성공 + 주문가와 동일 → 추가 확인 불필요
                                        logger.info(f"ℹ️ {stock_name} 체결가 확인 완료 - 동기화 불필요")

                                    # 저장
                                    self.save_split_data()
                                else:
                                    logger.error(f"❌ {stock_code} 종목 데이터를 찾을 수 없음")
                                                                
                            except Exception as sync_error:
                                logger.error(f"⚠️ {stock_name} 동기화 실패하지만 매수는 성공: {str(sync_error)}")
                                # 🔥 중요: 동기화 실패해도 매수는 성공으로 처리

                            # 🔥🔥🔥 핵심: 실제 체결가 반환 🔥🔥🔥
                            return actual_execution_price, actual_executed, "체결 완료"
                
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

    def sync_position_after_buy_with_order_list(self, stock_code, position_num, order_price, expected_amount):
        """주문내역 조회 기반 정확한 체결가 동기화 - 차수 혼동 버그 수정 (원전봇 5차수용)"""
        try:
            # 🔥 1. 파라미터 검증 강화 (원전봇: 1~5차)
            if not isinstance(position_num, int) or position_num < 1 or position_num > 5:
                logger.error(f"❌ {stock_code} 잘못된 차수: {position_num} (1~5만 허용)")
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
            
            # 🔥 6. 주문내역에서 실제 체결가 조회
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
        """현재 매수 중인 차수 파악 - 5차수용"""
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
            for i in range(4, -1, -1):  # 🔥 5차부터 역순으로 (4, 3, 2, 1, 0)
                magic_data = stock_data_info['MagicDataList'][i]
                if magic_data.get('IsBuy', False) and magic_data.get('CurrentAmt', 0) > 0:
                    return i + 1
            
            return None
            
        except Exception as e:
            logger.error(f"매수 차수 파악 중 오류: {str(e)}")
            return None            

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
        """매도 주문 처리 - 실제 체결가 조회 추가"""
        try:
            # 수수료 예상 계산
            estimated_fee = self.calculate_trading_fee(price, amount, False)
            
            # 🔥 미국주식 지정가 매도 주문 (1% 아래로 주문)
            order_price = round(price * 0.99, 2)
            result = SafeKisUS.safe_make_sell_limit_order(stock_code, amount, order_price)
                        
            if result:
                logger.info(f"📉 {stock_code} 매도 주문 전송: {amount}주 × ${order_price:.2f}, 예상 수수료: ${estimated_fee:.2f}")
                
                # 🔥🔥🔥 실제 체결가 조회 추가 🔥🔥🔥
                actual_price = self.get_actual_sell_execution_price(stock_code, order_price, amount)
                if actual_price:
                    logger.info(f"✅ {stock_code} 매도 실제 체결가: ${actual_price:.2f}")
                    return result, actual_price  # 실제 체결가 반환
            
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

    def calculate_stock_volatility(self, stock_code, days=20):
        """종목별 변동성 계산 (일평균 변동률)
        
        Args:
            stock_code: 종목 코드
            days: 계산 기간 (기본 20일)
        
        Returns:
            float: 일평균 변동률 (%)
        """
        try:
            # 최근 데이터 조회
            df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", days + 5)  # ✅ 올바른 순서!
            
            if df is None or len(df) < 10:
                logger.warning(f"⚠️ {stock_code} 변동성 계산 실패 - 기본값 3.0% 사용")
                return 3.0
            
            # 일별 수익률 계산
            daily_returns = df['close'].pct_change().dropna()
            
            if len(daily_returns) < 5:
                return 3.0
            
            # 평균 절대 변동률
            avg_volatility = abs(daily_returns).mean() * 100
            recent_volatility = abs(daily_returns.tail(10)).mean() * 100
            
            # 최종 변동성 (최근 70% + 전체 30%)
            stock_volatility = (recent_volatility * 0.7 + avg_volatility * 0.3)
            
            logger.debug(f"📊 {stock_code} 변동성: {stock_volatility:.2f}%/일")
            
            return stock_volatility
            
        except Exception as e:
            logger.error(f"❌ {stock_code} 변동성 계산 오류: {str(e)}")
            return 3.0        

    def calculate_dynamic_drop_requirement(self, stock_code, position_num, indicators, market_timing, news_sentiment):
        """🎯 최적 균형: 변동성 기반 차수별 차등 강화
        
        핵심 개선:
        1. 종목별 변동성 실시간 계산
        2. 차수별 차등 적용 (1차 자유, 물타기 엄격)
        3. 변동성 높을수록 조건 강화 (기존 로직 반전)
        4. RSI 안전장치 추가 (고변동성 구간만)
        
        Args:
            stock_code: 종목 코드
            position_num: 매수 차수 (2, 3, 4, 5)
            indicators: 기술적 지표
            market_timing: 시장 상황
            news_sentiment: 뉴스 감성
        
        Returns:
            tuple: (required_drop, adjustments, rsi_limit)
        """
        try:
            # 🔥 기본 하락률 설정
            base_required_drops = {
                2: 0.06,  # 기본 6%
                3: 0.07,  # 기본 7%  
                4: 0.09,  # 기본 9%
                5: 0.11   # 기본 11%
            }
            
            base_drop = base_required_drops.get(position_num, 0.06)
            adjustments = []
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥🔥🔥 핵심 개선: 변동성 기반 차수별 차등 강화 🔥🔥🔥
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # 1️⃣ 종목별 변동성 계산
            volatility = self.calculate_stock_volatility(stock_code, days=20)
            
            # 2️⃣ 차수별 + 변동성별 조정 계수 결정
            if volatility > 5.0:  # 극한 변동성 (IONQ급)
                if position_num == 2:
                    multiplier = 1.15  # 15% 강화
                    rsi_limit = 35
                    vol_desc = "극한변동"
                elif position_num >= 3:
                    multiplier = 1.25  # 25% 강화
                    rsi_limit = 30 if position_num == 3 else 25
                    vol_desc = "극한변동"
                else:  # 1차 (이 함수는 2차 이상만 호출됨)
                    multiplier = 1.05
                    rsi_limit = 40
                    vol_desc = "극한변동"
                    
                adjustments.append(f"{vol_desc}({volatility:.1f}%)")
                adjustments.append(f"{position_num}차 +{(multiplier-1)*100:.0f}% 강화")
                    
            elif volatility > 4.0:  # 고변동성 (RKLB급)
                if position_num == 2:
                    multiplier = 1.10  # 10% 강화
                    rsi_limit = 35
                elif position_num >= 3:
                    multiplier = 1.15  # 15% 강화
                    rsi_limit = 30
                else:
                    multiplier = 1.0
                    rsi_limit = 40
                    
                adjustments.append(f"고변동({volatility:.1f}%)")
                adjustments.append(f"{position_num}차 +{(multiplier-1)*100:.0f}% 강화")
                
            elif volatility > 3.0:  # 중변동성 (원전 일반)
                if position_num == 2:
                    multiplier = 1.05  # 5% 강화
                    rsi_limit = 40
                elif position_num >= 3:
                    multiplier = 1.10  # 10% 강화
                    rsi_limit = 35
                else:
                    multiplier = 1.0
                    rsi_limit = 45
                    
                adjustments.append(f"중변동({volatility:.1f}%)")
                if multiplier > 1.0:
                    adjustments.append(f"{position_num}차 +{(multiplier-1)*100:.0f}% 강화")
                
            else:  # 저변동성 (2% 이하)
                if position_num >= 3:
                    multiplier = 1.05  # 3차 이상만 5% 강화
                    rsi_limit = 40
                else:
                    multiplier = 1.0  # 2차는 기본
                    rsi_limit = 45
                    
                adjustments.append(f"저변동({volatility:.1f}%)")
                if multiplier > 1.0:
                    adjustments.append(f"{position_num}차 +{(multiplier-1)*100:.0f}% 강화")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 3️⃣ 기존 조건 조정 (시장/뉴스/RSI)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            rsi = indicators.get('rsi', 50)
            news_decision = news_sentiment.get('decision', 'NEUTRAL')
            news_percentage = news_sentiment.get('percentage', 0)
            pullback = indicators.get('pullback_from_high', 0)
            
            # 🟢 완화 조건들
            if rsi <= 25:
                multiplier *= 0.85
                adjustments.append("극한과매도(-15%)")
            elif rsi <= 35:
                multiplier *= 0.92
                adjustments.append("과매도(-8%)")
            
            if market_timing == "strong_downtrend":
                multiplier *= 0.8
                adjustments.append("강한하락장(-20%)")
            elif market_timing == "downtrend":
                multiplier *= 0.9
                adjustments.append("하락장(-10%)")
            
            if news_decision == 'POSITIVE' and news_percentage >= 70:
                multiplier *= 0.92
                adjustments.append("긍정뉴스(-8%)")
            
            if pullback >= 15:
                multiplier *= 0.9
                adjustments.append(f"큰조정{pullback:.1f}%(-10%)")
            elif pullback >= 10:
                multiplier *= 0.95
                adjustments.append(f"조정{pullback:.1f}%(-5%)")
            
            # 🔴 강화 조건들
            if market_timing == "strong_uptrend":
                multiplier *= 1.2
                adjustments.append("강한상승장(+20%)")
            elif market_timing == "uptrend":
                multiplier *= 1.1
                adjustments.append("상승장(+10%)")
            
            if news_decision == 'NEGATIVE' and news_percentage >= 70:
                multiplier *= 1.15
                adjustments.append("부정뉴스(+15%)")
            
            if rsi >= 70:
                multiplier *= 1.15
                adjustments.append("과매수(+15%)")
            elif rsi >= 60:
                multiplier *= 1.08
                adjustments.append("과매수주의(+8%)")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 4️⃣ 최종 하락률 계산
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            final_drop = base_drop * multiplier
            
            # 안전 범위 제한 (기존보다 넓게)
            final_drop = max(base_drop * 0.8, min(final_drop, base_drop * 1.5))
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5️⃣ RSI 안전장치 추가 검증 (고변동성 구간만)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            rsi_check_failed = False
            if volatility > 4.0:  # 고변동성 이상만
                if rsi > rsi_limit:
                    rsi_check_failed = True
                    adjustments.append(f"⚠️ RSI {rsi:.1f} > {rsi_limit} 초과")
            
            # 로깅
            if adjustments:
                logger.info(f"📊 {stock_code} {position_num}차 하락률 조정:")
                logger.info(f"   기본: {base_drop*100:.1f}% → 최종: {final_drop*100:.1f}%")
                for adj in adjustments:
                    logger.info(f"   {adj}")
                if volatility > 4.0:
                    logger.info(f"   RSI 안전장치: {rsi:.1f} (한도: {rsi_limit})")
            
            return final_drop, adjustments, rsi_limit if rsi_check_failed else None
            
        except Exception as e:
            logger.error(f"동적 하락률 계산 중 오류: {str(e)}")
            return base_required_drops.get(position_num, 0.06), ["오류로기본값사용"], None

    def calculate_dynamic_pullback_score(self, stock_code, indicators):
            """
            🔥 동적 조정폭 점수 계산 시스템
            - 변동성 기반 동적 기준선
            - 추세 강도 반영
            - RSI 연계 조정
            - 고점 근접도 페널티
            
            Args:
                stock_code: 종목 코드
                indicators: 기술적 지표 딕셔너리
                
            Returns:
                tuple: (최종점수 0-30, 상세정보)
            """
            try:
                # === 1. 기본 데이터 추출 ===
                current_price = indicators.get('current_price', 0)
                pullback = indicators.get('pullback_from_high', 0)
                rsi = indicators.get('rsi', 50)
                ma20 = indicators.get('ma_mid', 0)
                
                if current_price <= 0:
                    logger.warning(f"⚠️ {stock_code} 현재가 정보 없음 - 조정폭 점수 0")
                    return 0, {'error': '현재가 정보 없음'}
                
                # === 2. 변동성 계산 (60일 기준) ===
                df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", 60)
                if df is None or len(df) < 30:
                    volatility = 3.0  # 미국 주식 평균 기본값
                    logger.info(f"   📊 {stock_code} 변동성: 기본값 {volatility:.1f}% 사용")
                else:
                    volatility = df['close'].pct_change().std() * 100
                    logger.info(f"   📊 {stock_code} 60일 변동성: {volatility:.1f}%")
                
                # === 3. 동적 조정폭 기준 계산 ===
                base_meaningful = volatility * 1.5    # 의미있는 조정
                base_good = volatility * 2.5          # 좋은 조정
                base_excellent = volatility * 3.5     # 훌륭한 조정
                
                # === 4. 추세 강도 반영 ===
                adjustment_factor = 1.0
                trend_desc = "중립"
                
                if current_price > 0 and ma20 > 0:
                    trend_strength = (current_price - ma20) / ma20 * 100
                    
                    if trend_strength > 10:       # 강한 상승
                        adjustment_factor = 1.3
                        trend_desc = f"강한상승({trend_strength:.1f}%, 기준+30%)"
                    elif trend_strength > 5:      # 중간 상승
                        adjustment_factor = 1.15
                        trend_desc = f"상승({trend_strength:.1f}%, 기준+15%)"
                    elif trend_strength < -10:    # 강한 하락
                        adjustment_factor = 0.7
                        trend_desc = f"강한하락({trend_strength:.1f}%, 기준-30%)"
                    elif trend_strength < -5:     # 중간 하락
                        adjustment_factor = 0.85
                        trend_desc = f"하락({trend_strength:.1f}%, 기준-15%)"
                    else:
                        trend_desc = f"중립({trend_strength:.1f}%)"
                
                # 조정된 기준 적용
                meaningful = base_meaningful * adjustment_factor
                good = base_good * adjustment_factor
                excellent = base_excellent * adjustment_factor
                
                # === 5. RSI 기반 조정 ===
                rsi_factor = 1.0
                rsi_desc = "중립"
                
                if rsi >= 70:
                    rsi_factor = 1.5
                    rsi_desc = f"과매수(RSI:{rsi:.1f}, 기준+50%)"
                elif rsi >= 60:
                    rsi_factor = 1.2
                    rsi_desc = f"매수권(RSI:{rsi:.1f}, 기준+20%)"
                elif rsi <= 30:
                    rsi_factor = 0.7
                    rsi_desc = f"과매도(RSI:{rsi:.1f}, 기준-30%)"
                elif rsi <= 40:
                    rsi_factor = 0.85
                    rsi_desc = f"매도권(RSI:{rsi:.1f}, 기준-15%)"
                else:
                    rsi_desc = f"중립(RSI:{rsi:.1f})"
                
                meaningful *= rsi_factor
                good *= rsi_factor
                excellent *= rsi_factor
                
                # === 6. 기본 점수 계산 ===
                if pullback >= excellent:
                    base_score = 30
                    score_reason = f"훌륭한조정({pullback:.1f}%≥{excellent:.1f}%)"
                elif pullback >= good:
                    base_score = 25
                    score_reason = f"좋은조정({pullback:.1f}%≥{good:.1f}%)"
                elif pullback >= meaningful:
                    base_score = 20
                    score_reason = f"의미있는조정({pullback:.1f}%≥{meaningful:.1f}%)"
                elif pullback >= meaningful * 0.7:
                    base_score = 12
                    score_reason = f"약한조정({pullback:.1f}%≥{meaningful*0.7:.1f}%)"
                elif pullback >= meaningful * 0.5:
                    base_score = 6
                    score_reason = f"매우약한조정({pullback:.1f}%≥{meaningful*0.5:.1f}%)"
                else:
                    base_score = 0
                    score_reason = f"고점근처({pullback:.1f}%<{meaningful*0.5:.1f}%)"
                
                # === 7. 고점 근접도 페널티 ===
                peak_penalty = 0
                peak_desc = ""
                
                if df is not None and len(df) >= 20:
                    recent_high = df['high'].rolling(20).max().iloc[-1]
                    if recent_high > 0:
                        distance_from_peak = (recent_high - current_price) / recent_high * 100
                        
                        if distance_from_peak < 3:
                            peak_penalty = -10
                            peak_desc = f"고점3%이내({distance_from_peak:.1f}%, -10점)"
                        elif distance_from_peak < 5:
                            peak_penalty = -5
                            peak_desc = f"고점5%이내({distance_from_peak:.1f}%, -5점)"
                        elif distance_from_peak < 8:
                            peak_penalty = -2
                            peak_desc = f"고점8%이내({distance_from_peak:.1f}%, -2점)"
                
                # === 8. 최종 점수 (0-30점 범위) ===
                final_score = max(0, min(30, base_score + peak_penalty))
                
                # === 9. 로깅 ===
                logger.info(f"📊 {stock_code} 동적 조정폭 점수:")
                logger.info(f"   변동성: {volatility:.1f}% → 기준(의미:{meaningful:.1f}%, 좋음:{good:.1f}%, 훌륭:{excellent:.1f}%)")
                logger.info(f"   실제조정: {pullback:.1f}%")
                logger.info(f"   추세조정: {trend_desc}")
                logger.info(f"   RSI조정: {rsi_desc}")
                if peak_desc:
                    logger.info(f"   ⚠️ {peak_desc}")
                logger.info(f"   최종: {base_score}점{peak_penalty:+d} = {final_score}점 ({score_reason})")
                
                return final_score, {
                    'volatility': volatility,
                    'meaningful_threshold': meaningful,
                    'good_threshold': good,
                    'excellent_threshold': excellent,
                    'actual_pullback': pullback,
                    'base_score': base_score,
                    'peak_penalty': peak_penalty,
                    'final_score': final_score,
                    'reason': score_reason
                }
                
            except Exception as e:
                logger.error(f"❌ {stock_code} 동적 조정폭 점수 계산 오류: {str(e)}")
                import traceback
                traceback.print_exc()
                return 0, {'error': str(e)}

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
                    # 🔥 수정된 부분: stock_code 추가 전달
                    market_timing = self.detect_market_timing()
                    required_drop, adjustments, rsi_limit = self.calculate_dynamic_drop_requirement(
                        stock_code,  # 🔥 추가!
                        position_num, 
                        indicators, 
                        market_timing, 
                        news_sentiment
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

                    # 🔥🔥 RSI 안전장치 추가 검증 (고변동성 구간만) 🔥🔥
                    if rsi_limit is not None:
                        current_rsi = indicators.get('rsi', 50)
                        if current_rsi > rsi_limit:
                            fail_reason = f"RSI 안전장치 발동: {current_rsi:.1f} > {rsi_limit} (고변동성 구간)"
                            logger.warning(f"⚠️ {stock_code} {position_num}차 RSI 안전장치:")
                            logger.warning(f"   현재 RSI: {current_rsi:.1f}")
                            logger.warning(f"   RSI 한도: {rsi_limit}")
                            logger.warning(f"   → 고변동성 구간에서 과매수 진입 차단")
                            return 0, [fail_reason]

                    # 하락률 통과 시 성공 로깅
                    logger.info(f"✅ {stock_code} {position_num}차 하락률 검증 통과:")
                    logger.info(f"   {actual_drop*100:.1f}% ≥ {required_drop*100:.1f}% ({', '.join(adjustments) if adjustments else '기본조건'})")
               
                else:
                    return 0, ["직전 차수 데이터 없음"]
            
            # 🔥🔥🔥 2단계: 하락률 통과 후 종합 점수 계산 🔥🔥🔥
            total_score = 0
            score_details = []

            # 🔥 1️⃣ 가격 조건 점수 (30점) - 동적 조정폭 시스템 (1차 매수용)
            if position_num == 1:
                # 1차수: 동적 조정폭 기반 점수
                price_score, pullback_details = self.calculate_dynamic_pullback_score(
                    stock_code, indicators
                )
                price_desc = pullback_details.get('reason', '조정폭')
                
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

            # 🔥 2️⃣ RSI 점수 (20점) - 1차 매수 강화 버전
            rsi = indicators.get('rsi', 50)
            if position_num == 1:
                # 1차 매수: 과매수 페널티 강화
                if 20 <= rsi <= 30:
                    rsi_score = 20
                elif 30 < rsi <= 45:
                    rsi_score = 16
                elif 45 < rsi <= 55:
                    rsi_score = 12
                elif 55 < rsi <= 65:
                    rsi_score = 8
                elif 65 < rsi <= 70:
                    rsi_score = 4  # 기존 8점 → 4점 강화
                else:
                    rsi_score = 0  # RSI 70 이상은 0점
            else:
                # 2-3차 매수: 기존 로직 유지
                if 20 <= rsi <= 30:
                    rsi_score = 20
                elif 30 < rsi <= 45:
                    rsi_score = 16
                elif 45 < rsi <= 55:
                    rsi_score = 12
                elif 55 < rsi <= 70:
                    rsi_score = 8
                elif 70 < rsi <= 80:
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
        """종합 점수 기반 매수 결정 - 🔥 완전한 버전 (급락감지 + 저점판별 + 기존로직)"""
        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 0-1: 급락 감지 (최우선!)
            # Level 3 폭락은 무조건 차단, Level 1-2는 조건 강화
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            crash_penalty = 0
            crash_max_position = 5  # 원전봇 기본값
            crash_rsi_limit = 72    # 원전봇 기본값
            
            if CRASH_DETECTOR_AVAILABLE:
                crash_detector = market_crash_detector.get_crash_detector()
                restrictions = crash_detector.get_intraday_protection_level(stock_code)

                # Level 3: 매수 완전 차단
                if not restrictions['allowed']:
                    logger.warning(f"🚨 {stock_code} {position_num}차 급락 완전 차단")
                    logger.warning(f"   레벨: Level {restrictions['level']}")
                    logger.warning(f"   📊 시장: {restrictions['market_desc']}")
                    logger.warning(f"   📊 종목: {restrictions['stock_desc']}")
                    logger.warning(f"   ⏰ {restrictions['cooldown_hours']}시간 쿨다운")
                    return False, f"Level 3 폭락 차단: {restrictions['reason']}"
                
                # Level 1, 2: 조건 강화
                if restrictions['score_penalty'] > 0:
                    crash_penalty = restrictions['score_penalty']
                    crash_max_position = restrictions['max_position']
                    crash_rsi_limit = restrictions['rsi_limit']
                    
                    # 🏭 원전봇 특화: 차수 제한 완화 (3→4차)
                    if crash_max_position == 3:
                        crash_max_position = 4
                        logger.info(f"🏭 원전봇 특화: 급락 시 최대 차수 3→4차")
                    
                    # 🏭 원전봇 특화: RSI 상한 완화 (70→72)
                    if crash_rsi_limit == 70:
                        crash_rsi_limit = 72
                        logger.info(f"🏭 원전봇 특화: RSI 상한 70→72")
                    
                    logger.warning(f"🚨 {stock_code} {position_num}차 급락 대응 모드:")
                    logger.warning(f"   레벨: Level {restrictions.get('level', 0)}")
                    logger.warning(f"   점수 페널티: +{crash_penalty}점")
                    logger.warning(f"   RSI 상한: {crash_rsi_limit}")
                    logger.warning(f"   최대 차수: {crash_max_position}차")
                    
                    # 차수 제한 즉시 체크
                    if position_num > crash_max_position:
                        logger.warning(f"🚫 {stock_code} {position_num}차 차수 제한 초과")
                        return False, f"급락 차수 제한: 최대 {crash_max_position}차"
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 0-2: 저점 판별 (하락장에서만)
            # 강한 하락장에서 진짜 저점인지 확인
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            market_timing = self.detect_market_timing()
            
            # 강한 하락장: 저점 판별 필수
            if market_timing == "strong_downtrend":
                logger.warning(f"🚨 {stock_code} 강한 하락장 감지 - 저점 판별 모드")
                
                if BOTTOM_DETECTOR_AVAILABLE:
                    detector = bottom_detector.get_bottom_detector(SafeKisUS)
                    bottom_result = detector.detect_true_bottom(stock_code)
                    
                    if not bottom_result['is_bottom']:
                        logger.error(f"🚫 {stock_code} 저점 아님 (점수: {bottom_result['score']}/100)")
                        logger.error(f"   신호: {bottom_result['signals']}")
                        return False, f"강한 하락장 - 저점 미확인 ({bottom_result['score']}점)"
                    
                    elif bottom_result['confidence'] == 'HIGH':
                        logger.info(f"✅ {stock_code} 고신뢰 저점! (점수: {bottom_result['score']}/100)")
                        logger.info(f"   신호: {bottom_result['signals']}")
                        # 저점 확인 → 매수 진행
                        
                    elif bottom_result['confidence'] == 'MEDIUM':
                        logger.warning(f"⚠️ {stock_code} 중신뢰 저점 (점수: {bottom_result['score']}/100)")
                        logger.warning(f"   신호: {bottom_result['signals']}")
                        # 1-2차만 허용
                        if position_num > 2:
                            return False, f"중신뢰 저점 - 1-2차만 허용"
            
            # 일반 하락장: 조건부 저점 판별
            elif market_timing == "downtrend":
                logger.warning(f"⚠️ {stock_code} 하락장 - 저점 체크")
                
                if BOTTOM_DETECTOR_AVAILABLE:
                    # 신규 진입 (1차): 저점 필수
                    has_position = any(m['IsBuy'] and m['CurrentAmt'] > 0 
                                    for m in magic_data_list)
                    
                    if not has_position and position_num == 1:
                        detector = bottom_detector.get_bottom_detector(SafeKisUS)
                        bottom_result = detector.detect_true_bottom(stock_code)
                        
                        if bottom_result['score'] < 50:
                            logger.error(f"🚫 {stock_code} 신규 진입 차단 (저점 미확인: {bottom_result['score']}점)")
                            return False, f"하락장 - 저점 미확인"
                        else:
                            logger.info(f"✅ {stock_code} 저점 신호 확인 - 신규 진입 허용")
                            logger.info(f"   신호: {bottom_result['signals']}")
                    
                    # 기존 분할 (2-5차): 약한 저점 신호도 허용
                    else:
                        detector = bottom_detector.get_bottom_detector(SafeKisUS)
                        bottom_result = detector.detect_true_bottom(stock_code)
                        
                        if bottom_result['score'] < 30:
                            logger.warning(f"🚫 {stock_code} {position_num}차 분할 차단 (신호 약함: {bottom_result['score']}점)")
                            return False, f"하락장 - 분할 신호 약함"
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 1: 동적 하락률 필수 검증 + 종합 점수 계산
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            total_score, score_details = self.calculate_comprehensive_entry_score(
                stock_code, position_num, indicators, news_sentiment, magic_data_list
            )
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 2: 설정파일에서 threshold 읽어오기
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            comprehensive_config = config.config.get('comprehensive_scoring', {})
            position_thresholds = comprehensive_config.get('position_thresholds', {})
            
            # 🏭 원전봇 설정값 (설정파일 우선, 없으면 기본값)
            thresholds = {
                1: int(position_thresholds.get('1', 70)),
                2: int(position_thresholds.get('2', 64)),  # 원전봇 특화
                3: int(position_thresholds.get('3', 58)),  # 원전봇 특화
                4: int(position_thresholds.get('4', 54)),  # 원전봇 특화
                5: int(position_thresholds.get('5', 50))
            }
            
            required_score = thresholds.get(position_num, 70)
            original_threshold = required_score  # 원본 저장
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 3: 급락 페널티 적용
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if crash_penalty > 0:
                required_score += crash_penalty
                logger.warning(f"🚨 {stock_code} {position_num}차 급락 보정: 기준 {original_threshold}점 → {required_score}점")
            
            decision = total_score >= required_score
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 4: 기본 안전장치 (RSI 상한 동적 적용)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            safety_check = (
                indicators['current_price'] > 0 and
                15 <= indicators['rsi'] <= min(90, crash_rsi_limit)  # 동적 RSI 상한
            )
            
            # RSI 제한 로그
            if indicators['rsi'] > crash_rsi_limit:
                logger.warning(f"⚠️ {stock_code} RSI 제한: {indicators['rsi']:.1f} > {crash_rsi_limit}")
            
            final_decision = decision and safety_check
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 5: 상세 로깅 (기존 로직 완전 복원)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # 설정 정보
            if comprehensive_config.get('enable', True):
                setting_info = f"설정파일 기준"
            else:
                setting_info = f"기본값 사용"
            
            # 급락 적용 정보 추가
            if crash_penalty > 0:
                setting_info += f" + 급락대응(+{crash_penalty}점)"
            
            status = "✅ 매수" if final_decision else "❌ 대기"
            logger.info(f"🎯 {stock_code} {position_num}차 종합점수 판단: {total_score}점/{required_score}점 ({setting_info}) → {status}")
            
            # 점수 상세 출력
            for detail in score_details:
                logger.info(f"   📊 {detail}")
            
            # 안전장치 체크
            if not safety_check:
                logger.info(f"   ⚠️ 안전장치: 가격={indicators['current_price']}, RSI={indicators['rsi']}")
            
            # 설정 적용 확인 로깅
            if comprehensive_config.get('enable', True):
                logger.info(f"   ⚙️ 설정적용: threshold={original_threshold}점 (파일에서 로드)")
                if crash_penalty > 0:
                    logger.info(f"   🚨 급락보정: threshold={original_threshold}→{required_score}점 (+{crash_penalty}점)")
            else:
                logger.info(f"   ⚙️ 기본설정: threshold={required_score}점 (하드코딩)")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥 STEP 6: 하락률 검증 정보 표시
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if position_num > 1 and total_score > 0:
                logger.info(f"   🔗 순차 조건: {position_num-1}차 보유 + 동적 하락률 → ✅")
            elif position_num > 1:
                logger.info(f"   🔗 순차 조건: 동적 하락률 검증 실패 → ❌")
            
            # 최종 결과 반환
            return final_decision, f"종합점수 {total_score}/{required_score} ({setting_info})"
            
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
        """매매 로직 처리 - 종합 점수 기반 개선 버전"""

        # 🔥🔥🔥 미체결 주문 자동 관리 (가장 먼저 실행) 🔥🔥🔥
        try:
            self.check_and_manage_pending_orders()
        except Exception as e:
            logger.error(f"미체결 주문 관리 중 오류: {str(e)}")

        # 🔍 30분마다 불일치 감지 (수정하지 않음!)
        current_time = datetime.now()

        # 🔥 헬퍼 함수: 장 시작 직후 여부 확인
        def is_market_opening_period():
            """장 시작 후 10분 이내인지 확인 (09:30~09:40 ET)"""
            try:
                now_ny = datetime.now(timezone('America/New_York'))
                # 09:30~09:40 ET 사이 = 장 시작 직후 10분
                return (now_ny.hour == 9 and 30 <= now_ny.minute < 50)
            except Exception as e:
                logger.error(f"장 시작 시점 체크 오류: {str(e)}")
                return False

        if not hasattr(self, 'last_discrepancy_check'):
            self.last_discrepancy_check = current_time
            # 🔥 개선: 봇 시작 시 장 시작 직후라면 체크 건너뛰기
            if is_market_opening_period():
                logger.info("🔔 장 시작 직후라 초기 불일치 체크 건너뜀 (KIS API 안정화 대기)")
            else:
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
        #         logger.info("🔄 정기 전체 포지션 동기화 실행")
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

        # 🔥🔥🔥 비상정지 체크 - 매수만 차단, 매도는 정상 실행 🔥🔥🔥
        is_emergency_mode = self.check_emergency_conditions()
        
        if is_emergency_mode:
            logger.info("⚠️ 원전봇 비상정지 중 - 매수 차단, 매도/최고점갱신은 정상 실행")
        
        # 🔥 동적 예산 업데이트 (항상 실행)
        self.update_budget()

        # 🔥 뉴스 분석 (캐시 기반으로 최적화 - API 비용 절약)
        try:
            if NEWS_ANALYSIS_AVAILABLE:
                # 먼저 캐시된 뉴스 확인 (240분 유효)
                news_summary = self.get_cached_news_summary()
                
                if news_summary is None:
                    # 캐시가 없거나 만료된 경우만 새로운 API 호출
                    logger.info("📰 뉴스 API 호출 - 새로운 분석 수행")
                    news_summary = self.analyze_all_stocks_news()
                    self.cache_news_summary(news_summary)
                    
                    # API 호출 알림 (비용 모니터링용)
                    api_call_msg = f"💰 뉴스 API 호출됨 - {datetime.now().strftime('%H:%M:%S')}"
                    logger.warning(api_call_msg)
                    
                else:
                    # 캐시된 결과 사용 (API 비용 절약)
                    logger.info("📰 캐시된 뉴스 분석 결과 사용 (API 비용 절약)")
            else:
                news_summary = {}
                logger.info("📰 뉴스 분석 모듈 비활성화, 기존 방식으로 진행")
        except Exception as e:
            logger.warning(f"뉴스 분석 실패, 기존 방식으로 진행: {str(e)}")
            news_summary = {}
        
        # 각 종목별 처리
        target_stocks = config.target_stocks

        for stock_code, stock_info in target_stocks.items():
            try:
                
                # 🔥 매도 후 쿨다운 체크 (매매 로직 시작 전)
                if not self.check_post_sell_cooldown(stock_code):
                    logger.info(f"⏳ {stock_code} 매도 후 쿨다운 중 - 매수 스킵")
                    continue

                # 🔥🔥🔥 비상정지 시 매수 건너뛰고 매도만 실행 🔥🔥🔥
                if is_emergency_mode:
                    logger.debug(f"⚠️ {stock_code} 비상정지 중 - 매수 건너뛰고 매도 체크만 실행")
                    
                    # 뉴스 정보
                    news_sentiment = news_summary.get(stock_code, {})
                    news_decision = news_sentiment.get('decision', 'NEUTRAL')
                    news_percentage = news_sentiment.get('percentage', 0)
                    
                    # 기술적 지표 조회 (매도에 필요)
                    period, recent_period, recent_weight = self.determine_optimal_period(stock_code)
                    indicators = self.get_technical_indicators_weighted(
                        stock_code, 
                        period=period, 
                        recent_period=recent_period, 
                        recent_weight=recent_weight
                    )
                    
                    if not indicators:
                        logger.warning(f"❌ {stock_code} 기술적 지표 조회 실패")
                        time.sleep(0.5)
                        continue
                    
                    # 종목 데이터 찾기
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    if stock_data_info:
                        magic_data_list = stock_data_info['MagicDataList']
                        
                        # 매도 체크 실행 (비상정지 중에도!)
                        sells_executed = self.process_position_wise_selling(
                            stock_code, indicators, magic_data_list, news_decision, news_percentage
                        )
                        
                        if sells_executed:
                            logger.info(f"✅ {stock_code} 비상정지 중 매도 실행 완료")
                    
                    time.sleep(0.5)
                    continue  # 다음 종목으로 (매수 로직 건너뜀)
                
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
                
                # 종목 데이터가 없으면 새로 생성
                if stock_data_info is None:
                    magic_data_list = []
                    
                    for i in range(5):  # 5차수
                        magic_data_list.append({
                            'Number': i + 1,
                            'EntryPrice': 0,
                            'EntryAmt': 0,
                            'CurrentAmt': 0,
                            'SellHistory': [],
                            'EntryDate': '',
                            'IsBuy': False
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
                    
                    msg = f"{stock_code} 미국주식 스마트스플릿 투자 준비 완료!!"
                    logger.info(msg)
                    if config.config.get("use_discord_alert", True):
                        discord_alert.SendMessage(msg)
                
                # 🔥 개선된 5차수 분할 매수 로직
                magic_data_list = stock_data_info['MagicDataList']
                total_budget = self.total_money * stock_info['weight']
                
                # 🔥 종목별 매수 조건 설정값 가져오기
                stock_config = target_stocks.get(stock_code, {})
                min_pullback = stock_config.get('min_pullback', 2.5)
                max_rsi_buy = stock_config.get('max_rsi_buy', 65)
                min_green_candle = stock_config.get('min_green_candle', 1.005)
                trend_requirement = stock_config.get('trend_requirement', False)
                
                base_conditions = {
                    'min_pullback': min_pullback,
                    'max_rsi_buy': max_rsi_buy,
                    'green_candle_req': min_green_candle,
                    'position_limit': 5
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
                
                # 🔥 점진적 매수 간격 설정
                progressive_drops = config.config.get('progressive_buy_drops', {
                    "2": 0.06, "3": 0.07, "4": 0.09, "5": 0.11
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
                
                # 🔥 시장 상황별 포지션 제한 (뉴스 제한 제거)
                market_limits = config.config.get('market_position_limits', {
                    'strong_downtrend': 1, 'downtrend': 2, 'neutral': 3,
                    'uptrend': 4, 'strong_uptrend': 5
                })
                max_allowed_position = market_limits.get(market_timing, 3)
                
                # 🔥 매수 쿨다운 설정
                buy_control = config.config.get('buy_control', {})
                enable_cooldown = buy_control.get('enable_cooldown', False)
                cooldown_days = buy_control.get('cooldown_days', [0, 1, 2, 3, 5])
                max_daily_buys = buy_control.get('max_daily_buys', 2)
                
                # 🔥 일일 매수 횟수 체크
                today = datetime.now().strftime("%Y-%m-%d")
                daily_buy_count = 0
                for magic_data in magic_data_list:
                    if magic_data['IsBuy'] and magic_data.get('EntryDate') == today:
                        daily_buy_count += 1
                
                if daily_buy_count >= max_daily_buys:
                    logger.info(f"{stock_code} 일일 매수 한도 도달: {daily_buy_count}/{max_daily_buys}")
                    continue

                # 장 시작 직후 20분간 매수 활동 보류
                if is_market_opening_period():
                    logger.info(f"⏰ {stock_code} 장 시작 후 20분 대기 중 - 09:50 ET 이후 매수 예정")
                    continue  # 다음 종목으로 건너뛰기

                # 🔥🔥🔥 개선된 각 차수별 매수 조건 체크 🔥🔥🔥
                buy_executed_this_cycle = False
                
                for i, magic_data in enumerate(magic_data_list):
                    if not magic_data['IsBuy']:
                        
                        position_num = i + 1
                        
                        # 🔥 시장 상황 기반 포지션 제한 체크 (뉴스 제한 제거)
                        if position_num > max_allowed_position:
                            logger.info(f"{stock_code} {position_num}차 매수 제한: 시장상황 (최대 {max_allowed_position}차수)")
                            continue

                        # 🔥 매수 쿨다운 체크 (기존 유지)
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
                        
                        # 🔥 1차수 재진입 조건 체크 (기존 유지)
                        if position_num == 1:
                            reentry_allowed, reentry_reason = self.check_reentry_conditions(stock_code, indicators)
                            if not reentry_allowed:
                                logger.info(f"🚫 {stock_code} 1차 매수 차단: {reentry_reason}")
                                continue
                        
                        # 🚀🚀🚀 새로운 종합 점수 기반 매수 결정 🚀🚀🚀
                        should_buy, buy_reason = self.should_buy_with_comprehensive_score(
                            stock_code, position_num, indicators, news_sentiment, magic_data_list, adjusted_conditions
                        )
                        
                        # 투자 비중 설정 (기존 방식 유지)
                        if position_num == 1:
                            investment_ratio = 0.15 * position_multiplier
                        elif position_num == 2:
                            investment_ratio = 0.18 * position_multiplier
                        elif position_num == 3:
                            investment_ratio = 0.22 * position_multiplier
                        elif position_num == 4:
                            investment_ratio = 0.25 * position_multiplier
                        else:  # 5차수
                            investment_ratio = 0.20 * position_multiplier
                        
                        # 🔥🔥🔥 매수 실행 로직 (핵심 수정 부분) 🔥🔥🔥
                        if should_buy:
                            logger.info(f"💰 {stock_code} {position_num}차 매수 진행 - 종합 점수 시스템")
                            
                            safety_check = (
                                indicators['current_price'] > 0 and
                                15 <= indicators['rsi'] <= 90
                            )

                            if safety_check:
                                invest_amount = total_budget * investment_ratio
                                buy_amt = max(1, int(invest_amount / indicators['current_price']))

                                # 🔥 먼저 매수 비용 계산
                                estimated_fee = self.calculate_trading_fee(indicators['current_price'], buy_amt, True)
                                upcoming_buy_cost = (indicators['current_price'] * buy_amt) + estimated_fee

                                # 🔥🔥 STEP 1: 계좌 레벨 안전망 체크 (AI 통합)
                                balance = SafeKisUS.safe_get_balance("USD")
                                total_asset = float(balance.get('TotalMoney', 0))
                                cash_reserve = self.calculate_dynamic_cash_reserve(total_asset)
                                
                                account_safe, account_msg, cash_balance = self.check_account_cash_safety(
                                    min_safety_cash=cash_reserve['min_safety_cash'],
                                    alert_threshold=cash_reserve['alert_threshold'],
                                    upcoming_buy_cost=upcoming_buy_cost
                                )

                                if not account_safe:
                                    logger.error(f"🚨 {stock_code} 계좌 안전망 차단: {account_msg}")
                                    logger.error(f"   📍 안전선 출처: {cash_reserve['source']}")
                                    continue  # 매수 스킵


                                if not account_safe:
                                    logger.error(f"🚨 {stock_code} 계좌 안전망 차단: {account_msg}")
                                    continue  # 매수 스킵

                                # # 🔥🔥 STEP 1: 계좌 레벨 안전망 체크 (최우선)
                                # account_safe, account_msg, cash_balance = self.check_account_cash_safety(
                                #     min_safety_cash=800,    # $800 이하면 매수 차단
                                #     alert_threshold=1000     # $1000 이하면 경고
                                # )
                                
                                # if not account_safe:
                                #     logger.error(f"🚨 {stock_code} 계좌 안전망 차단: {account_msg}")
                                #     continue  # 매수 스킵
                                
                                # 🔥 STEP 2: 봇별 예산 체크 (기존 로직)
                                can_buy, budget_reason = self.check_budget_before_buy(
                                    stock_code, buy_amt, indicators['current_price']
                                )
                                
                                if not can_buy:
                                    logger.warning(f"🚫 {stock_code} {position_num}차 매수 차단: {budget_reason}")
                                    continue
                                
                                logger.info(f"✅ {stock_code} {position_num}차 예산 체크 통과: {budget_reason}")
                                logger.info(f"✅ 계좌 안전 확인: {account_msg}")
                                # 🔥🔥🔥 예산 체크 끝 🔥🔥🔥

                                estimated_fee = self.calculate_trading_fee(indicators['current_price'], buy_amt, True)
                                total_cost = (indicators['current_price'] * buy_amt) + estimated_fee
                                
                                balance = SafeKisUS.safe_get_balance("USD")
                                remain_money = float(balance.get('RemainMoney', 0))
                                
                                logger.info(f"  💰 필요 자금: ${total_cost:.2f}, 보유 현금: ${remain_money:.2f}")
                                
                                if total_cost <= remain_money:
                                    # 🔥 개선된 매수 처리 (체결 확인 포함)
                                    actual_price, executed_amount, message = self.handle_buy_with_execution_tracking(
                                        stock_code, buy_amt, indicators['current_price']
                                    )

                                    if actual_price and executed_amount:
                                        # ✅ handle_buy_with_execution_tracking()에서 이미 업데이트 완료
                                        # ✅ 여기서는 성공 메시지만 전송
                                        
                                        # 성공 메시지 작성
                                        msg = f"🤖 {stock_code} 원전봇 {buy_reason}!\n"
                                        msg += f"  수량: {executed_amount}주 @ ${actual_price:.2f}\n"
                                        msg += f"  투자비중: {investment_ratio*100:.1f}% ({position_num}차)\n"
                                        msg += f"  차수시스템: 5차수 집중 투자\n"
                                        
                                        # 가격 개선 정보 추가
                                        price_diff = actual_price - indicators['current_price']
                                        if abs(price_diff) > 0.01:
                                            msg += f"  가격개선: ${price_diff:+.2f}\n"
                                        
                                        # msg += f"  🎯 AI 테마 고점권 대응 전략!"
                                        
                                        logger.info(msg)
                                        if config.config.get("use_discord_alert", True):
                                            discord_alert.SendMessage(msg)
                                        
                                        buy_executed_this_cycle = True
                                        break  # 매수 성공으로 루프 종료
                                    
                                    else:
                                        # 매수 실패 (체결 실패)
                                        logger.warning(f"❌ {stock_code} {position_num}차 매수 실패: {message}")
                                        if "가격 급등" in message:
                                            logger.info(f"  💡 {stock_code} 가격 급등으로 인한 매수 포기는 정상적인 보호 기능입니다")
                                    
                                else:
                                    logger.warning(f"❌ {stock_code} 매수 자금 부족: 필요 ${total_cost:.2f} vs 보유 ${remain_money:.2f}")
                            else:
                                logger.warning(f"❌ {stock_code} 안전장치 실패: 가격={indicators['current_price']}, RSI={indicators['rsi']}")

                if holdings.get('api_error', False):
                    logger.warning(f"⚠️ {stock_code} API 오류로 매도 처리 스킵")
                    return False

                if holdings['amount'] == -1:  # API 오류
                    logger.info(f"🔄 {stock_code} API 오류 - 기존 데이터 유지, 매도 처리 안함")
                    return False

                # 🔥 차수별 수익보존 매도 로직 (기존과 동일 유지)
                if holdings['amount'] > 0:
                    
                    # 수량 동기화 체크
                    internal_total = sum([magic_data['CurrentAmt'] for magic_data in magic_data_list if magic_data['IsBuy']])
                    
                    if abs(internal_total - holdings['amount']) > 0:
                        logger.warning(f"{stock_code} 수량 불일치 감지: 내부관리={internal_total}, API조회={holdings['amount']}")
                        # if internal_total > 0:
                        #     sync_ratio = holdings['amount'] / internal_total
                        #     for magic_data in magic_data_list:
                        #         if magic_data['IsBuy']:
                        #             magic_data['CurrentAmt'] = int(magic_data['CurrentAmt'] * sync_ratio)
                        #     logger.info(f"{stock_code} 수량 동기화 완료: 비율={sync_ratio:.3f}")
                        #     self.save_split_data()
                                            
                        # ✅ 새로운 안전한 코드 (바로 교체)
                        if internal_total != holdings['amount']:
                            logger.warning(f"⚠️ {stock_code} 수량 불일치 감지: 내부관리={internal_total}, API조회={holdings['amount']}")
                            logger.warning(f"🔍 {stock_code} 수동 확인이 필요할 수 있습니다.")
                            # ❌ sync_ratio 계산 및 CurrentAmt 자동 수정 완전 제거
                        else:
                            logger.debug(f"✅ {stock_code} 수량 일치 확인: {internal_total}주")

                    # 🔥 차수별 개별 매도 처리 (모든 매도 로직이 여기서 완료됨)
                    sells_executed = self.process_position_wise_selling(
                        stock_code, indicators, magic_data_list, news_decision, news_percentage
                    )
                    
                    # 매도 실행 여부만 로깅 (상세 내용은 process_position_wise_selling에서 처리)
                    if sells_executed:
                        logger.info(f"🎯 {stock_code} 차수별 매도 전략 실행 완료")
                    else:
                        # 매도가 없었을 때의 현재 상태 간단 로깅
                        total_positions = sum([magic_data['CurrentAmt'] for magic_data in magic_data_list if magic_data['IsBuy']])
                        if total_positions > 0:
                            logger.debug(f"💎 {stock_code} 전체 {total_positions}주 홀딩 유지")

                # 🔥 간단한 API 호출 간격 추가
                time.sleep(0.5)  # 0.5초 대기
                
            except Exception as e:
                logger.error(f"{stock_code} 처리 중 오류 발생: {str(e)}")
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
            """🔥 원전봇 스마트 비상 조건 체크 - 실제 투자금 기준 + 자동복구 v2.2"""
            emergency_settings = self.get_emergency_config()
            
            emergency_loss_limit = emergency_settings['total_loss_limit']
            consecutive_limit = emergency_settings['consecutive_stop_limit']
            monitoring_days = emergency_settings['monitoring_days']
            
            # 🔥 원전봇 독립 성과 조회
            if not hasattr(self, 'performance_tracker') or not self.performance_tracker:
                logger.error("❌ 원전봇 독립 성과 추적기가 초기화되지 않음 - 비상정지 체크 불가")
                return False
            
            perf_data = self.performance_tracker.calculate_bot_specific_performance()
            
            if not perf_data:
                logger.error("❌ 원전봇 성과 계산 실패 - 비상정지 체크 불가")
                return False
            
            # 🔥 실제 투자금 기준 손실 계산
            total_investment = perf_data['total_investment']
            current_value = perf_data['current_investment_value']
            realized_pnl = perf_data['realized_pnl']
            
            emergency_history = self.get_emergency_stop_history()
            
            # 🔥 보유 없을 때 처리 (익절/손절 구분)
            if total_investment == 0 and emergency_history:
                # 🔥 비상정지 발동 시점의 기준값 사용
                base_investment = emergency_history.get('base_total_investment', 0)
                
                if base_investment > 0:
                    # 🔥 발동 시점 기준으로 손실률 계산
                    total_loss = realized_pnl  # 보유 없으면 실현손익만
                    loss_ratio = abs(total_loss) / base_investment if total_loss < 0 else 0.0
                    
                    logger.info(f"=" * 60)
                    logger.info(f"📊 원전봇 비상정지 체크 (발동 시점 기준)")
                    logger.info(f"=" * 60)
                    logger.info(f"⚡ 비상정지 발동 시점 투자금: ${base_investment:,.2f}")
                    logger.info(f"💰 현재 실현손익: ${realized_pnl:+,.2f}")
                    logger.info(f"📉 현재 손실률: {loss_ratio*100:.1f}%")
                    logger.info(f"=" * 60)
                else:
                    # 기준값 없으면 초기 예산 사용
                    initial_asset = perf_data['initial_asset']
                    loss_ratio = abs(realized_pnl) / initial_asset if realized_pnl < 0 and initial_asset > 0 else 0.0
                    logger.warning(f"⚠️ 비상정지 발동 시점 투자금 없음 - 초기 예산 기준 사용")
                
                # 🔥 이전 실현손익과 비교
                prev_realized_pnl = emergency_history.get('prev_realized_pnl', realized_pnl)
                
                # 🔥 실현손익이 개선되었는지 확인
                pnl_improved = (realized_pnl > prev_realized_pnl)
                
                # 🔥 마지막 매도가 익절인지 확인
                last_sell_was_profit = False
                if hasattr(self, 'split_data_list') and len(self.split_data_list) > 0:
                    for stock_data in self.split_data_list:
                        if 'GlobalSellHistory' in stock_data and len(stock_data['GlobalSellHistory']) > 0:
                            last_sell = stock_data['GlobalSellHistory'][-1]
                            # 최근 1분 이내 매도만 체크
                            try:
                                sell_time_str = last_sell.get('timestamp', '')
                                if sell_time_str:
                                    sell_time = datetime.fromisoformat(sell_time_str)
                                    time_diff = (datetime.now() - sell_time).total_seconds()
                                    if time_diff < 60:  # 1분 이내
                                        return_pct = last_sell.get('return_pct', 0)
                                        if return_pct > 0:
                                            last_sell_was_profit = True
                                            logger.info(f"✅ 최근 매도 익절 확인: {return_pct:+.1f}%")
                                            break
                            except:
                                pass
                
                # 🔥 익절 후 처리
                if pnl_improved or last_sell_was_profit:
                    logger.info(f"📈 익절 감지: 실현손익 ${prev_realized_pnl:+,.2f} → ${realized_pnl:+,.2f}")
                    
                    # 손실 10% 미만이면 즉시 5차수 완전 복귀
                    if loss_ratio < 0.10:
                        msg = f"🔄 원전봇 비상 정지 자동 해제\n"
                        msg += f"📊 해제 사유: 익절 + 손실 < 10%\n"
                        msg += f"💰 실현손익: ${realized_pnl:+,.2f}\n"
                        msg += f"📉 손실률: {loss_ratio*100:.1f}%\n"
                        msg += f"🎯 허용 차수: 5차수"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        self.clear_emergency_stop_history()
                        return False
                    
                    # 10~20% 손실이면 3차수
                    elif loss_ratio < 0.20:
                        msg = f"🔄 원전봇 비상 정지 부분 해제 (익절 후)\n"
                        msg += f"📊 해제 사유: 익절\n"
                        msg += f"💰 실현손익: ${realized_pnl:+,.2f}\n"
                        msg += f"📉 손실률: {loss_ratio*100:.1f}%\n"
                        msg += f"🎯 허용 차수: 3차수"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        emergency_history['prev_realized_pnl'] = realized_pnl
                        self.split_data_list[0]['EmergencyStopHistory'] = emergency_history
                        self.save_split_data()
                        
                        self.set_position_limit(3)
                        return False
                    
                    else:  # 20% 이상
                        msg = f"🔄 원전봇 비상 정지 부분 해제 (익절 후)\n"
                        msg += f"📊 해제 사유: 익절\n"
                        msg += f"💰 실현손익: ${realized_pnl:+,.2f}\n"
                        msg += f"📉 손실률: {loss_ratio*100:.1f}%\n"
                        msg += f"🎯 허용 차수: 1차수"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        emergency_history['prev_realized_pnl'] = realized_pnl
                        self.split_data_list[0]['EmergencyStopHistory'] = emergency_history
                        self.save_split_data()
                        
                        self.set_position_limit(1)
                        return False
                
                else:
                    # ❌ 손절 후 - 시간 기반 재개
                    logger.info(f"📉 손절 감지: 실현손익 ${prev_realized_pnl:+,.2f} → ${realized_pnl:+,.2f}")
                    
                    triggered_at_str = emergency_history.get('triggered_at', '')
                    if triggered_at_str:
                        try:
                            triggered_at = datetime.fromisoformat(triggered_at_str)
                            elapsed_hours = (datetime.now() - triggered_at).total_seconds() / 3600
                        except:
                            elapsed_hours = 0
                    else:
                        elapsed_hours = 0
                    
                    # 손실 10% 미만이면 즉시 재개
                    if loss_ratio < 0.10:
                        msg = f"🔄 원전봇 비상 정지 자동 해제\n"
                        msg += f"📊 해제 사유: 손실 < 10%\n"
                        msg += f"💰 실현손익: ${realized_pnl:+,.2f}\n"
                        msg += f"📉 손실률: {loss_ratio*100:.1f}%\n"
                        msg += f"🎯 허용 차수: 5차수"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        self.clear_emergency_stop_history()
                        return False
                    
                    # 24시간 경과 → 1차수 재개
                    elif elapsed_hours >= 24:
                        msg = f"🔄 원전봇 비상 정지 부분 해제 (시간 기반)\n"
                        msg += f"📊 해제 사유: 손절 후 24시간 경과\n"
                        msg += f"💰 실현손익: ${realized_pnl:+,.2f}\n"
                        msg += f"📉 손실률: {loss_ratio*100:.1f}%\n"
                        msg += f"⏰ 경과: {elapsed_hours:.1f}시간\n"
                        msg += f"🎯 허용 차수: 1차수"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        emergency_history['prev_realized_pnl'] = realized_pnl
                        self.split_data_list[0]['EmergencyStopHistory'] = emergency_history
                        self.save_split_data()
                        
                        self.set_position_limit(1)
                        return False
                    
                    # 아직 시간 부족
                    else:
                        time_until_resume = 24 - elapsed_hours
                        msg = f"🚨 원전봇 비상 정지 유지 (손절 후 대기)\n"
                        msg += f"💰 실현손익: ${realized_pnl:+,.2f}\n"
                        msg += f"📉 손실률: {loss_ratio*100:.1f}%\n"
                        msg += f"⏰ 경과: {elapsed_hours:.1f}시간\n"
                        msg += f"⏳ 재개까지: {time_until_resume:.1f}시간"
                        
                        if self.should_log_emergency_status():
                            logger.error(msg)
                            if config.config.get("use_discord_alert", True):
                                discord_alert.SendMessage(msg)
                        
                        return True  # 계속 중단
            
            # 🔥 아직 투자 안한 경우 (비상정지 이력 없음)
            if total_investment == 0:
                logger.info("📊 원전봇 아직 투자 내역 없음 - 비상정지 체크 스킵")
                return False
            
            # 🔥 실제 투자금 기준 손실 계산 (보유 중인 경우)
            unrealized_loss = current_value - total_investment
            total_loss = unrealized_loss + realized_pnl
            
            if total_loss < 0:
                loss_ratio = abs(total_loss) / total_investment
            else:
                loss_ratio = 0.0
            
            logger.info(f"=" * 60)
            logger.info(f"📊 원전봇 비상정지 체크 (실투자금 기준)")
            logger.info(f"=" * 60)
            logger.info(f"💸 실제 투자금:   ${total_investment:,.2f}")
            logger.info(f"📈 현재 평가액:   ${current_value:,.2f}")
            logger.info(f"📊 미실현 손익:   ${unrealized_loss:+,.2f}")
            logger.info(f"💰 실현 손익:     ${realized_pnl:+,.2f}")
            logger.info(f"💵 총 손익:       ${total_loss:+,.2f}")
            logger.info(f"📉 손실률:        {loss_ratio*100:.1f}%")
            logger.info(f"⚠️ 비상정지 한도: {emergency_loss_limit*100:.0f}%")
            logger.info(f"=" * 60)
            
            # 연속 손절 체크
            recent_stop_count = self.count_recent_stop_losses(days=monitoring_days)
            
            emergency_triggered = False
            emergency_reason = ""
            
            # 총 손실 한도 (실투자금 기준)
            if loss_ratio > emergency_loss_limit:
                emergency_triggered = True
                emergency_reason = f"원전봇 실투자금 대비 손실 한도 초과: {loss_ratio*100:.1f}% > {emergency_loss_limit*100:.0f}%"
            
            # 연속 손절 한도
            elif recent_stop_count >= consecutive_limit:
                emergency_triggered = True
                emergency_reason = f"연속 손절 한도 초과: 최근 {monitoring_days}일간 {recent_stop_count}개 포지션 손절"
            
            # 🔥🔥🔥 비상정지 발동 시 🔥🔥🔥
            if emergency_triggered:
                # 🎯 회복 조건 체크 (원전봇 독립 성과 전달)
                recovery_result = self.check_recovery_conditions(
                    loss_ratio, 
                    emergency_loss_limit,
                    perf_data  # 🔥 원전봇 성과 데이터 전달
                )
                
                if recovery_result['allow_resume']:
                    # 🔥 비상정지 이력 조회
                    emergency_history = self.get_emergency_stop_history()
                    
                    # 🔥 재개 알림 플래그 확인
                    resume_notified = emergency_history.get('resume_notified', False) if emergency_history else False
                    current_max_positions = recovery_result['max_positions']
                    last_notified_positions = emergency_history.get('last_notified_positions', 0) if emergency_history else 0
                    
                    # 🔥 조건: 첫 재개이거나 차수가 증가한 경우에만 알림
                    should_notify = not resume_notified or (current_max_positions > last_notified_positions)
                    
                    if should_notify:
                        # ✅ 회복 조건 충족 - 단계적 재개 (1회만 알림)
                        msg = f"🔄🔄🔄 원전봇 비상 정지 자동 해제! 🔄🔄🔄\n"
                        msg += f"📊 회복 상태: {recovery_result['recovery_type']}\n"
                        msg += f"💰 손실률 회복: {recovery_result['recovery_rate']*100:.1f}%\n"
                        msg += f"📈 현재 손실률: {loss_ratio*100:.1f}% (최대 손실: {recovery_result['peak_loss']*100:.1f}%)\n"
                        msg += f"💸 실제 투자금: ${total_investment:,.2f} 기준\n"
                        msg += f"🎯 허용 차수: {recovery_result['max_positions']}차수\n"
                        msg += f"⚙️ 재개 사유: {recovery_result['reason']}\n"
                        msg += f"✅ 단계적 매매 재개"
                        
                        logger.info(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        # 🔥 재개 알림 플래그 설정 (반복 방지)
                        if emergency_history:
                            emergency_history['resume_notified'] = True
                            emergency_history['last_notified_positions'] = current_max_positions
                            emergency_history['resume_notified_at'] = datetime.now().isoformat()
                            self.split_data_list[0]['EmergencyStopHistory'] = emergency_history
                            self.save_split_data()
                            logger.info(f"💾 원전봇 재개 알림 플래그 설정: {current_max_positions}차수")
                            
                            # 🔥🔥🔥 [v2.2 신규] Level 5 완전 복구 시 이력 삭제
                            if recovery_result.get('should_clear_history', False):
                                logger.info("🎉 원전봇 Level 5 완전 복구 달성 - 비상정지 이력 삭제")
                                self.clear_emergency_stop_history()
                                # RecoveryPositionLimit도 삭제하여 완전히 정상화
                                if self.split_data_list and len(self.split_data_list) > 0:
                                    if 'RecoveryPositionLimit' in self.split_data_list[0]:
                                        del self.split_data_list[0]['RecoveryPositionLimit']
                                        self.save_split_data()
                                        logger.info("🎯 원전봇 복구 차수 제한 해제 - 정상 운영 복귀")
                    else:
                        # 🔕 이미 알림한 상태 - 로그만 남김
                        logger.info(f"📊 원전봇 비상정지 해제 상태 유지: {current_max_positions}차수 (알림 생략)")
                    
                    # 🔥 차수 제한 설정 (Level 5 아닐 때만)
                    if not recovery_result.get('should_clear_history', False):
                        self.set_position_limit(recovery_result['max_positions'])

                    return False  # 매매 재개
                
                else:
                    msg = f"🚨🚨🚨 원전봇 비상 정지 유지 🚨🚨🚨\n"
                    msg += f"📊 정지 사유: {emergency_reason}\n"
                    msg += f"💸 실제 투자금: ${total_investment:,.2f}\n"
                    msg += f"💰 현재 손실률: {loss_ratio*100:.1f}%\n"
                    msg += f"📈 회복률: {recovery_result['recovery_rate']*100:.1f}% (필요: {recovery_result['required_recovery']*100:.0f}%)\n"
                    msg += f"🛑 매매 활동 중단\n"
                    msg += f"ℹ️ {recovery_result['recovery_hint']}"
                    
                    if self.should_log_emergency_status():
                        logger.error(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                    
                    return True
            
            return False

    def check_recovery_conditions(self, current_loss_ratio, emergency_loss_limit, perf_data=None):
        """🔄 비상정지 자동 복구 조건 체크 - v2.2 (5차수 시스템)
        
        Args:
            current_loss_ratio: 현재 손실률 (0.197 = -19.7%)
            emergency_loss_limit: 비상정지 기준 손실률 (0.20 = -20%)
            perf_data: 원전봇 성과 데이터 (optional)
        
        Returns:
            {
                'allow_resume': bool,
                'recovery_type': str,
                'max_positions': int,
                'recovery_rate': float,
                'reason': str,
                'should_clear_history': bool  # v2.2 신규
            }
        """
        try:
            # 🔥 1. 비상정지 이력 조회
            emergency_data = self.get_emergency_stop_history()
            
            if not emergency_data:
                # 🔥 비상정지 첫 발동 - 기준값 저장
                self.save_emergency_stop_history(current_loss_ratio)
                
                # 🔥 원전봇 초기 자산 정보 저장
                if perf_data:
                    emergency_data = self.get_emergency_stop_history()
                    emergency_data['bot_initial_asset'] = perf_data['initial_asset']
                    emergency_data['bot_current_asset'] = perf_data['total_current_asset']
                    
                    # 🔥 발동 시점의 기준값 저장
                    emergency_data['base_total_investment'] = perf_data['total_investment']
                    emergency_data['base_realized_pnl'] = perf_data['realized_pnl']
                    emergency_data['prev_realized_pnl'] = perf_data['realized_pnl']
                    
                    self.split_data_list[0]['EmergencyStopHistory'] = emergency_data
                    self.save_split_data()
                    
                    logger.info(f"💾 원전봇 비상정지 기준값 저장:")
                    logger.info(f"   발동 시점 투자금: ${perf_data['total_investment']:,.2f}")
                    logger.info(f"   발동 시점 실현손익: ${perf_data['realized_pnl']:+,.2f}")
                
                return {
                    'allow_resume': False,
                    'recovery_type': '비상정지 첫 발동',
                    'max_positions': 0,
                    'recovery_rate': 0.0,
                    'peak_loss': current_loss_ratio,
                    'required_recovery': 0.30,
                    'reason': '비상정지 발동 - 회복 대기',
                    'recovery_hint': '원전봇 손실률 30% 이상 회복 시 1차수 재개 가능'
                }
            
            # 🔥 발동 시점 기준값 조회
            base_investment = emergency_data.get('base_total_investment', 0)
            
            # 🔥 2. 최대 손실률 대비 회복률 계산
            peak_loss = emergency_data.get('peak_loss_ratio', current_loss_ratio)
            
            # 🔥 현재 손실률을 발동 시점 기준으로 재계산
            if perf_data and base_investment > 0:
                current_total_investment = perf_data['total_investment']
                current_value = perf_data['current_investment_value']
                current_realized = perf_data['realized_pnl']
                
                # 미실현 손익
                if current_total_investment > 0:
                    unrealized = current_value - current_total_investment
                else:
                    unrealized = 0
                
                # 총 손익 (실현 + 미실현)
                total_loss = current_realized + unrealized
                
                # 🔥 발동 시점 투자금 기준 손실률
                adjusted_loss_ratio = abs(total_loss) / base_investment if total_loss < 0 else 0.0
                
                logger.info(f"📊 원전봇 회복률 계산 (발동 시점 기준):")
                logger.info(f"   기준 투자금: ${base_investment:,.2f}")
                logger.info(f"   현재 실현손익: ${current_realized:+,.2f}")
                logger.info(f"   현재 미실현: ${unrealized:+,.2f}")
                logger.info(f"   총 손익: ${total_loss:+,.2f}")
                logger.info(f"   조정 손실률: {adjusted_loss_ratio*100:.1f}%")
                
                # 조정된 손실률 사용
                current_loss_ratio = adjusted_loss_ratio
            
            # 최대 손실 갱신 (더 나빠진 경우)
            if current_loss_ratio > peak_loss:
                peak_loss = current_loss_ratio
                self.update_emergency_peak_loss(peak_loss)
                
                # 🔥 원전봇 자산 정보도 갱신
                if perf_data:
                    emergency_data = self.get_emergency_stop_history()
                    emergency_data['bot_current_asset'] = perf_data['total_current_asset']
                    self.split_data_list[0]['EmergencyStopHistory'] = emergency_data
                    self.save_split_data()
                
                logger.warning(f"📉 원전봇 최대 손실률 갱신: {peak_loss*100:.1f}%")
            
            # 회복률 계산: (최대손실 - 현재손실) / 최대손실
            if peak_loss > 0:
                recovery_rate = (peak_loss - current_loss_ratio) / peak_loss
            else:
                recovery_rate = 0.0
            
            # 🔥 원전봇 자산 정보 로깅
            if perf_data:
                logger.info(f"📊 원전봇 회복률 계산:")
                logger.info(f"   초기 자산: ${perf_data['initial_asset']:,.2f}")
                logger.info(f"   현재 자산: ${perf_data['total_current_asset']:,.2f}")
                logger.info(f"   최대 손실: {peak_loss*100:.1f}% → 현재 {current_loss_ratio*100:.1f}%")
                logger.info(f"   회복률: {recovery_rate*100:.1f}%")
            else:
                logger.info(f"📊 회복률 계산: 최대손실 {peak_loss*100:.1f}% → 현재 {current_loss_ratio*100:.1f}% = {recovery_rate*100:.1f}% 회복")
            
            # 🔥 3. 시장 상승 추세 체크 (SPY 기준)
            market_trend = self.check_market_uptrend()
            
            # 🔥 4. 개별 종목 회복 신호 카운트
            recovery_signals = self.count_stock_recovery_signals()
            
            # 🔥 5. 5단계 복구 판정 (원전봇은 5차수!)
            
            # 🎯 Level 5: 완전 복구 (40% 이상 회복 + 시장 호조 + 종목 회복)
            if recovery_rate >= 0.40 and market_trend and recovery_signals >= 2:
                return {
                    'allow_resume': True,
                    'recovery_type': 'Level 5: 완전 복구',
                    'max_positions': 5,
                    'recovery_rate': recovery_rate,
                    'peak_loss': peak_loss,
                    'required_recovery': 0.40,
                    'reason': f'손실 {recovery_rate*100:.1f}% 회복 + 시장 상승 + {recovery_signals}개 종목 회복',
                    'recovery_hint': '',
                    'should_clear_history': True  # 🔥 이력 삭제 플래그
                }
            
            # 🎯 Level 4: 대부분 복구 (35% 이상 회복)
            elif recovery_rate >= 0.35:
                return {
                    'allow_resume': True,
                    'recovery_type': 'Level 4: 대부분 복구',
                    'max_positions': 4,
                    'recovery_rate': recovery_rate,
                    'peak_loss': peak_loss,
                    'required_recovery': 0.40,
                    'reason': f'손실 {recovery_rate*100:.1f}% 회복 (목표: 40%)',
                    'recovery_hint': f'40% 이상 회복 시 5차수 복구 (현재 {recovery_rate*100:.1f}%)'
                }
           
            # 🎯 Level 3: 절반 이상 복구 (25% 이상 회복)
            elif recovery_rate >= 0.25:
                return {
                    'allow_resume': True,
                    'recovery_type': 'Level 3: 절반 이상 복구',
                    'max_positions': 3,
                    'recovery_rate': recovery_rate,
                    'peak_loss': peak_loss,
                    'required_recovery': 0.40,
                    'reason': f'손실 {recovery_rate*100:.1f}% 회복 (목표: 40%)',
                    'recovery_hint': f'35% 이상 회복 시 4차수 복구 (현재 {recovery_rate*100:.1f}%)'
                }
            
            # 🎯 Level 2: 부분 복구 (15% 이상 회복)
            elif recovery_rate >= 0.15:
                return {
                    'allow_resume': True,
                    'recovery_type': 'Level 2: 부분 복구',
                    'max_positions': 2,
                    'recovery_rate': recovery_rate,
                    'peak_loss': peak_loss,
                    'required_recovery': 0.40,
                    'reason': f'손실 {recovery_rate*100:.1f}% 회복 (목표: 40%)',
                    'recovery_hint': f'25% 이상 회복 시 3차수 복구 (현재 {recovery_rate*100:.1f}%)'
                }
            
            # 🎯 Level 1: 최소 복구 (10% 이상 회복 또는 시장 호조)
            elif recovery_rate >= 0.10 or (market_trend and recovery_signals >= 1):
                return {
                    'allow_resume': True,
                    'recovery_type': 'Level 1: 최소 복구',
                    'max_positions': 1,
                    'recovery_rate': recovery_rate,
                    'peak_loss': peak_loss,
                    'required_recovery': 0.40,
                    'reason': f'손실 {recovery_rate*100:.1f}% 회복 또는 시장 회복 신호',
                    'recovery_hint': f'15% 이상 회복 시 2차수 복구 (현재 {recovery_rate*100:.1f}%)'
                }
            
            # ❌ 아직 회복 조건 미달
            else:
                return {
                    'allow_resume': False,
                    'recovery_type': '회복 대기 중',
                    'max_positions': 0,
                    'recovery_rate': recovery_rate,
                    'peak_loss': peak_loss,
                    'required_recovery': 0.40,
                    'reason': f'회복률 {recovery_rate*100:.1f}% (목표: 10% 이상)',
                    'recovery_hint': '10% 이상 회복 또는 시장 회복 신호 시 1차수 재개'
                }
                
        except Exception as e:
            logger.error(f"회복 조건 체크 오류: {str(e)}")
            return {
                'allow_resume': False,
                'recovery_type': '오류',
                'max_positions': 0,
                'recovery_rate': 0.0,
                'peak_loss': current_loss_ratio,
                'required_recovery': 0.40,
                'reason': f'체크 오류: {str(e)}',
                'recovery_hint': ''
            }

    def check_market_uptrend(self):
        """시장 추세 확인 (SPY 기준)"""
        try:
            df = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 10)
            if df is None or len(df) < 10:
                logger.warning("SPY 데이터 없음 - 시장 추세 알 수 없음")
                return "unknown"
            
            current_price = df['close'].iloc[-1]
            ma5 = df['close'].rolling(window=5).mean().iloc[-1]
            ma10 = df['close'].rolling(window=10).mean().iloc[-1]
            
            # 최근 3일 변화율
            three_day_ago = df['close'].iloc[-4]
            three_day_change = ((current_price - three_day_ago) / three_day_ago) * 100
            
            # 판정
            if current_price > ma5 and ma5 > ma10 and three_day_change > 2.0:
                return "strong_up"
            elif current_price > ma5 and three_day_change > 0.5:
                return "moderate_up"
            elif three_day_change < -2.0:
                return "down"
            else:
                return "neutral"
        
        except Exception as e:
            logger.error(f"시장 추세 체크 오류: {str(e)}")
            return "unknown"

    def count_stock_recovery_signals(self):
        """개별 종목 회복 신호 카운트 (원전 3종목)"""
        try:
            recovery_count = 0
            
            # 원전봇 종목 조회 (CCJ, OKLO, LEU)
            for stock_data in self.split_data_list:
                stock_code = stock_data.get('StockCode')
                if not stock_code:
                    continue
                
                # 각 종목의 최근 3일 추세 체크
                df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", 5)
                if df is None or len(df) < 3:
                    continue
                
                current_price = df['close'].iloc[-1]
                three_day_ago = df['close'].iloc[-4]
                
                # 3일간 상승률
                change_3d = ((current_price - three_day_ago) / three_day_ago) * 100
                
                # 회복 신호: 3일간 +3% 이상 상승
                if change_3d > 3.0:
                    recovery_count += 1
                    logger.info(f"  ✅ {stock_code} 회복 신호: 3일 +{change_3d:.1f}%")
            
            logger.info(f"📊 원전봇 종목 회복 신호: {recovery_count}개 / 3개")
            return recovery_count
        
        except Exception as e:
            logger.error(f"종목 회복 신호 카운트 오류: {str(e)}")
            return 0

    def get_emergency_stop_history(self):
        """비상정지 이력 조회"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                return self.split_data_list[0].get('EmergencyStopHistory', None)
            return None
        except Exception as e:
            logger.error(f"비상정지 이력 조회 오류: {str(e)}")
            return None

    def save_emergency_stop_history(self, peak_loss_ratio):
        """비상정지 이력 저장"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                self.split_data_list[0]['EmergencyStopHistory'] = {
                    'triggered_at': datetime.now().isoformat(),
                    'peak_loss_ratio': peak_loss_ratio,
                    'prev_realized_pnl': self.performance_tracker.calculate_bot_specific_performance()['realized_pnl'] if hasattr(self, 'performance_tracker') else 0,
                    'last_check': datetime.now().isoformat()
                }
                self.save_split_data()
                logger.info(f"💾 원전봇 비상정지 이력 저장: 최대 손실률 {peak_loss_ratio*100:.1f}%")
        except Exception as e:
            logger.error(f"비상정지 이력 저장 오류: {str(e)}")

    def update_emergency_peak_loss(self, new_peak_loss):
        """최대 손실률 업데이트"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                if 'EmergencyStopHistory' in self.split_data_list[0]:
                    self.split_data_list[0]['EmergencyStopHistory']['peak_loss_ratio'] = new_peak_loss
                    self.split_data_list[0]['EmergencyStopHistory']['last_check'] = datetime.now().isoformat()
                    self.save_split_data()
        except Exception as e:
            logger.error(f"최대 손실률 업데이트 오류: {str(e)}")

    def clear_emergency_stop_history(self):
        """비상정지 이력 삭제"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                if 'EmergencyStopHistory' in self.split_data_list[0]:
                    del self.split_data_list[0]['EmergencyStopHistory']
                    self.save_split_data()
                    logger.info("💾 원전봇 비상정지 이력 삭제 완료")
        except Exception as e:
            logger.error(f"비상정지 이력 삭제 오류: {str(e)}")

    def set_position_limit(self, max_positions):
        """단계적 복구 시 차수 제한 설정"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                self.split_data_list[0]['RecoveryPositionLimit'] = {
                    'max_positions': max_positions,
                    'set_at': datetime.now().isoformat()
                }
                self.save_split_data()
                logger.info(f"🎯 원전봇 복구 차수 제한 설정: 최대 {max_positions}차수")
        except Exception as e:
            logger.error(f"차수 제한 설정 오류: {str(e)}")

    def get_position_limit(self):
        """현재 차수 제한 조회 (원전봇은 5차수)"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                limit_info = self.split_data_list[0].get('RecoveryPositionLimit', None)
                if limit_info:
                    return limit_info.get('max_positions', 5)
            return 5  # 기본값: 제한 없음 (5차수)
        except Exception as e:
            logger.error(f"차수 제한 조회 오류: {str(e)}")
            return 5

    def should_log_emergency_status(self):
        """6시간마다 한 번씩 상태 로깅"""
        try:
            if self.split_data_list and len(self.split_data_list) > 0:
                emergency_data = self.split_data_list[0].get('EmergencyStopHistory', {})
                last_log = emergency_data.get('last_status_log', '')
                
                if last_log:
                    last_log_time = datetime.fromisoformat(last_log)
                    hours_elapsed = (datetime.now() - last_log_time).total_seconds() / 3600
                    
                    if hours_elapsed >= 6:
                        emergency_data['last_status_log'] = datetime.now().isoformat()
                        self.split_data_list[0]['EmergencyStopHistory'] = emergency_data
                        self.save_split_data()
                        return True
                    return False
                else:
                    emergency_data['last_status_log'] = datetime.now().isoformat()
                    self.split_data_list[0]['EmergencyStopHistory'] = emergency_data
                    self.save_split_data()
                    return True
        except Exception as e:
            logger.error(f"로깅 체크 오류: {str(e)}")
            return True

    def get_dynamic_trailing_drop(self, max_profit_pct, stock_code=""):
        """🔥 수익률에 따른 동적 트레일링 간격 계산 - 혁신적 개선"""
        try:
            # 🎯 수익률 구간별 차등화 트레일링
            if max_profit_pct >= 50:        # 50% 이상 초대박
                trailing_drop = 0.02        # 2% 트레일링 (매우 타이트)
                grade = "초대박"
            elif max_profit_pct >= 30:      # 30~50% 대박
                trailing_drop = 0.025       # 2.5% 트레일링 
                grade = "대박"
            elif max_profit_pct >= 20:      # 20~30% 높은 수익
                trailing_drop = 0.03        # 3% 트레일링
                grade = "높은수익"
            elif max_profit_pct >= 15:      # 15~20% 좋은 수익  
                trailing_drop = 0.035       # 3.5% 트레일링
                grade = "좋은수익"
            elif max_profit_pct >= 10:      # 10~15% 일반 수익
                trailing_drop = 0.045       # 4.5% 트레일링 
                grade = "일반수익"
            elif max_profit_pct >= 5:       # 5~10% 소폭 수익
                trailing_drop = 0.05        # 5% 트레일링 (기본값)
                grade = "소폭수익"
            else:                           # 5% 미만
                trailing_drop = 0.06        # 6% 트레일링 (여유있게)
                grade = "저수익"
            
            logger.info(f"🎯 {stock_code} 동적 트레일링: {max_profit_pct:.1f}% → {trailing_drop*100:.1f}% 간격 ({grade})")
            
            return trailing_drop
            
        except Exception as e:
            logger.error(f"동적 트레일링 계산 오류: {str(e)}")
            return 0.05  # 기본값 5% 반환        

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

                logger.debug(f"   → 1단계 부분매도 체크 진입")
                logger.debug(f"      first_threshold: {first_threshold}%")

                if position_return_pct >= first_threshold:
                    logger.info(f"✅ {stock_code} {current_position_num}차 부분매도 조건 충족!")
                    return {
                        'action': 'partial_sell',
                        'sell_ratio': first_ratio,
                        'reason': f'1차 개선된 부분매도 ({first_threshold}% 달성)',
                        'type': 'smart_partial'
                    }
                else:
                    logger.debug(f"      부분매도 조건 미충족 ({position_return_pct:.2f}% < {first_threshold}%)")

            # 2단계: 부분매도 후 동적 트레일링 (기존 유지)
            if current_stage >= 1:
                dynamic_trailing_drop = self.get_dynamic_trailing_drop(position_max, stock_code)

                logger.debug(f"   → 2단계 부분매도 후 트레일링 체크")
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
            if current_stage == 0:
                emergency_enable = hybrid_config.get('emergency_trailing_enable', True)
                min_profit_threshold = hybrid_config.get('emergency_max_profit_threshold', 6)
                
                # base_emergency_drop = hybrid_config.get('emergency_trailing_drop', 0.04)
                # dynamic_emergency_drop = max(base_emergency_drop, self.get_dynamic_trailing_drop(position_max, stock_code) + 0.01)

                # 🔥 개선: 동적 트레일링만 사용
                dynamic_trailing = self.get_dynamic_trailing_drop(position_max, stock_code)
                dynamic_emergency_drop = dynamic_trailing + 0.01

                # 최소 보장값: 동적값이 너무 낮으면 2% 최소 보장
                if dynamic_emergency_drop < 0.02:
                    dynamic_emergency_drop = 0.02
                    logger.info(f"⚠️ {stock_code} 응급트레일링 최소값 보장: 2%")

                # 🔥 핵심 개선: 최소 안전 마진 설정 (이 부분은 RSI 체크 없이도 중요!)
                MIN_SAFETY_MARGIN = 2.0  # 최소 2% 수익 보장
                
                # 시장 상황 체크
                try:
                    market_timing = self.detect_market_timing()
                    if market_timing['decision'] == 'strong_downtrend':
                        MIN_SAFETY_MARGIN = 1.0  # 강한 하락장에서는 1%로 완화
                        logger.info(f"📉 {stock_code} 강한 하락장 감지 - 안전마진 1%로 조정")
                except:
                    pass
                
                condition_1 = emergency_enable
                condition_2 = position_return_pct > MIN_SAFETY_MARGIN  # 🔥 핵심 개선!
                condition_3 = position_max >= min_profit_threshold
                condition_4 = position_return_pct <= position_max - (dynamic_emergency_drop * 100)
                
                # 개선된 로그
                if emergency_enable and position_max >= min_profit_threshold:
                    logger.info(f"📊 {stock_code} 응급트레일링 조건 체크:")
                    logger.info(f"   최고점: {position_max:.1f}% (>= {min_profit_threshold}% {'✅' if condition_3 else '❌'})")
                    logger.info(f"   현재수익률: {position_return_pct:.1f}% (> {MIN_SAFETY_MARGIN}% {'✅' if condition_2 else '❌'})")
                    logger.info(f"   보호선: {position_max - (dynamic_emergency_drop * 100):.1f}% (<= {'✅' if condition_4 else '❌'})")
                    logger.info(f"   트레일링 간격: {dynamic_emergency_drop*100:.1f}%")

                    # 급락 경고
                    if position_max >= 10 and position_return_pct < position_max * 0.5:
                        logger.warning(f"⚠️ {stock_code} 급락 감지: 최고 {position_max:.1f}% → 현재 {position_return_pct:.1f}%")

                if all([condition_1, condition_2, condition_3, condition_4]):
                    return {
                        'action': 'emergency_trailing',
                        'sell_ratio': 1.0,
                        'reason': f'🔥개선 응급트레일링 (최고{position_max:.1f}%→{dynamic_emergency_drop*100:.1f}%하락)',
                        'type': 'emergency_trailing'
                    }
         
            logger.debug(f"   → 모든 조건 미충족, 홀딩")
            return {'action': 'hold', 'reason': '하이브리드 조건 미충족'}
            
        except Exception as e:
            logger.error(f"하이브리드 보호 체크 오류: {str(e)}")
            return {'action': 'hold', 'reason': f'오류: {str(e)}'}

    def adjust_position_max_for_gap(self, stock_code, magic_data, current_price, position_return_pct):
        """갭 하락 감지 및 최고점 조정 - 원전봇 특화 (트레일링 시작점 리셋)"""
        try:
            # 🔥🔥🔥 [신버전] 종목별 갭 조정 설정 가져오기 🔥🔥🔥
            # stock_config = self.config.get('target_stocks', {}).get(stock_code, {})
            stock_config = config.config.get('target_stocks', {}).get(stock_code, {})  # ✅ 수정
            gap_config = stock_config.get('gap_adjustment', {})
            gap_enable = gap_config.get('enable', True)
            
            # 갭 조정 비활성화 시 바로 종료
            if not gap_enable:
                return
            
            # 🔥 손실 상태에서는 갭 조정 불필요 (트레일링 어차피 안됨)
            if position_return_pct < 0:
                return
            
            position_num = magic_data.get('Number', 1)
            
            # 전일 종가 정보
            prev_close_key = f'prev_close_{position_num}'
            prev_close = magic_data.get(prev_close_key, 0)
            
            # 최고점 키 (원전봇 키 형식)
            max_profit_key = f'max_profit_{position_num}'
            current_max = magic_data.get(max_profit_key, 0)
            
            # 현재 Stage 확인
            current_stage = magic_data.get('PartialSellStage', 0)
            
            # 갭 조정 플래그
            gap_adjusted_key = f'gap_adjusted_{position_num}'
            already_adjusted_today = magic_data.get(gap_adjusted_key, False)
            
            # 오늘 날짜
            today = datetime.now().strftime("%Y-%m-%d")
            last_check_date_key = f'last_gap_check_{position_num}'
            last_check_date = magic_data.get(last_check_date_key, "")
            
            # 새로운 날짜면 초기화
            if last_check_date != today:
                magic_data[gap_adjusted_key] = False
                magic_data[last_check_date_key] = today
                already_adjusted_today = False
            
            # 전일 종가가 있고, 아직 오늘 조정하지 않았으면
            if prev_close > 0 and not already_adjusted_today:
                # 갭 계산 (전일 종가 대비)
                gap_pct = ((current_price - prev_close) / prev_close) * 100
                
                # 🔥🔥🔥 [신버전] 종목별 갭 임계값과 안전 마진 직접 가져오기 🔥🔥🔥
                gap_threshold = gap_config.get('threshold', -3.0)
                base_safety_margin_config = gap_config.get('safety_margin', 4.5)
                
                # 🔥 partial_sell_config 가져오기
                partial_config = stock_config.get('partial_sell_config', {})
                hybrid_config = partial_config.get('hybrid_protection', {})
                
                # 🔥 두 가지 트레일링 설정 모두 가져오기
                emergency_threshold = hybrid_config.get('emergency_max_profit_threshold', 7)
                emergency_drop = hybrid_config.get('emergency_trailing_drop', 0.07) * 100
                post_partial_drop = hybrid_config.get('post_partial_trailing', 0.05) * 100
                
                # 🎯 현재 Stage에 따라 적절한 트레일링 기준 선택
                if current_stage == 0:
                    # 부분매도 전 → 응급 트레일링 기준
                    base_drop = emergency_drop
                    strategy_type = "응급트레일링"
                else:
                    # 부분매도 후 → 부분매도 후 트레일링 기준
                    base_drop = post_partial_drop
                    strategy_type = "부분매도후트레일링"
                
                # 변동성 승수 (기존 설정 활용)
                volatility_multiplier = stock_config.get('volatility_adjustment', 1.0)
                
                # 변동성 전략 설명
                if volatility_multiplier > 1.1:
                    strategy_desc = "고변동성"
                    safety_multiplier = 1.3
                elif volatility_multiplier < 0.9:
                    strategy_desc = "저변동성"
                    safety_multiplier = 0.8
                else:
                    strategy_desc = "중간변동성"
                    safety_multiplier = 1.0
                
                # 안전 마진 계산
                base_safety_margin = base_safety_margin_config * (base_drop / 100) * safety_multiplier
                
                # 🔥 갭 하락 감지
                if gap_pct <= gap_threshold and not already_adjusted_today:
                    logger.warning(f"⚠️ {stock_code} {position_num}차 갭 하락 감지 (원전봇 신버전):")
                    logger.warning(f"   전일 종가: ${prev_close:.2f}")
                    logger.warning(f"   현재가: ${current_price:.2f}")
                    logger.warning(f"   갭: {gap_pct:.2f}%")
                    logger.warning(f"   갭 임계값: {gap_threshold:.1f}% ({stock_code} 종목별 설정)")
                    logger.warning(f"   이전 최고점: {current_max:.1f}%")
                    logger.warning(f"   현재 Stage: {current_stage} ({strategy_type})")
                    logger.warning(f"   변동성 전략: {strategy_desc}")
                    
                    # 🎯 갭 크기별 안전 마진 조정
                    gap_severity = abs(gap_pct)
                    if gap_severity >= 5.0:  # 큰 갭 하락 (5% 이상)
                        safety_margin = base_safety_margin * 1.5
                        severity_desc = "큰 갭"
                    elif gap_severity >= 3.0:  # 중간 갭 (3~5%)
                        safety_margin = base_safety_margin * 1.2
                        severity_desc = "중간 갭"
                    else:  # 작은 갭
                        safety_margin = base_safety_margin * 1.0
                        severity_desc = "작은 갭"
                    
                    # 🔥 최고점 재조정 (현재 수익률 + 안전 마진)
                    new_max = position_return_pct + safety_margin
                    
                    # 🛡️ 안전장치: 새 최고점이 너무 낮으면 최소값 보장
                    if current_stage == 0:
                        min_threshold = emergency_threshold * 0.5
                    else:
                        min_profit_for_trailing = hybrid_config.get('min_profit_for_trailing', 7)
                        min_threshold = min_profit_for_trailing * 0.5
                    
                    new_max = max(new_max, min_threshold)
                    
                    # 최고점 업데이트
                    old_max = magic_data[max_profit_key]
                    magic_data[max_profit_key] = new_max
                    magic_data[gap_adjusted_key] = True
                    
                    logger.warning(f"   📊 최고점 재조정: {old_max:.1f}% → {new_max:.1f}%")
                    logger.warning(f"   🛡️ 안전 마진: {safety_margin:.2f}% ({severity_desc}, {base_drop:.1f}% 트레일링 기준)")
                    logger.warning(f"   📐 기본 안전마진: {base_safety_margin:.1f}% (설정값: {base_safety_margin_config})")
                    logger.warning(f"   🎯 트레일링 전략: {strategy_type} (Stage {current_stage})")
                    logger.warning(f"   ✅ 갭 하락 보정 완료 - 트레일링 시작점 리셋")
                    logger.warning(f"   ⚛️ 원전봇 5차수 시스템 - 급락 보호 활성화 (신버전)")
            
            # 🔥 종가 저장 (장 종료 30분 전부터)
            now = datetime.now()
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # 장 종료 30분 전부터 종가 업데이트 (3:30 PM ~ 4:00 PM ET)
            if now >= market_close.replace(hour=15, minute=30):
                magic_data[prev_close_key] = current_price
                
        except Exception as e:
            logger.error(f"원전봇 갭 조정 오류: {str(e)}")

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
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🚨 STEP 0: 긴급 청산 체크 (최우선! - 전체 평단가 기준) - 🏭 원전봇 특화
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if CRASH_DETECTOR_AVAILABLE:
                crash_detector = market_crash_detector.get_crash_detector()
                
                # 1. 전체 평단가 계산
                total_invested = 0
                total_shares = 0
                active_positions = [m for m in magic_data_list if m.get('IsBuy') and m.get('CurrentAmt', 0) > 0]
                
                for magic_data in active_positions:
                    entry_price = magic_data.get('EntryPrice', 0)
                    current_amt = magic_data.get('CurrentAmt', 0)
                    
                    if entry_price > 0 and current_amt > 0:
                        total_invested += entry_price * current_amt
                        total_shares += current_amt
                
                if total_shares > 0:
                    avg_price = total_invested / total_shares
                    total_return_pct = ((current_price - avg_price) / avg_price) * 100
                    
                    # 2. 긴급 청산 필요성 판단
                    emergency_decision = crash_detector.get_emergency_liquidation_decision(
                        stock_code, total_return_pct, total_shares, avg_price, current_price
                    )

                    if emergency_decision['execute']:
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # 🚨🚨🚨 긴급 청산 실행! - 🏭 원전봇 5차수 전량 청산
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        
                        logger.critical("=" * 80)
                        logger.critical(f"🚨🚨🚨 {stock_code} 긴급 청산 발동! (원전봇)")
                        logger.critical(f"사유: {emergency_decision['reason']}")
                        logger.critical(f"평단가: ${avg_price:.2f} | 현재가: ${current_price:.2f}")
                        logger.critical(f"수익률: {total_return_pct:+.1f}% | 보유: {total_shares}주")
                        logger.critical(f"시장: {emergency_decision['market_desc']}")
                        logger.critical(f"종목: {emergency_decision['stock_desc']}")
                        logger.critical("=" * 80)
                        
                        # 🏭 원전봇 특화: 5차수 시스템 전량 청산
                        emergency_sells = 0
                        emergency_details = []
                        
                        for magic_data in sorted(active_positions, key=lambda x: x.get('PositionIndex', 0), reverse=True):
                            position_num = magic_data.get('PositionIndex', 0) + 1
                            entry_price = magic_data.get('EntryPrice', 0)
                            sell_amount = magic_data.get('CurrentAmt', 0)
                            
                            if sell_amount <= 0:
                                continue
                            
                            position_return = ((current_price - entry_price) / entry_price) * 100
                            
                            # API 매도 실행
                            sell_result = SafeKisUS.safe_sell_stock(
                                stock_code, sell_amount, current_price, order_type="LOC"
                            )
                            
                            if sell_result and sell_result.get('success'):
                                logger.critical(f"🚨 {stock_code} {position_num}차 긴급청산: {sell_amount}주 @ ${current_price:.2f} ({position_return:+.1f}%)")
                                
                                # 수량 업데이트
                                magic_data['CurrentAmt'] = 0
                                magic_data['IsBuy'] = False
                                
                                emergency_sells += sell_amount
                                emergency_details.append({
                                    'position': position_num,
                                    'amount': sell_amount,
                                    'entry_price': entry_price,
                                    'sell_price': current_price,
                                    'return_pct': position_return
                                })
                                
                                # 이력 보존
                                self._preserve_sell_history_for_cooldown(stock_code, magic_data)
                                
                                time.sleep(1)  # API 부하 방지
                            else:
                                logger.error(f"❌ {stock_code} {position_num}차 긴급청산 실패")
                        
                        if emergency_sells > 0:
                            # 종목 상태 업데이트
                            for stock_data in self.split_data_list:
                                if stock_data['StockCode'] == stock_code:
                                    stock_data['IsReady'] = True
                                    break
                            
                            self.save_split_data()
                            
                            # Discord 긴급 알림
                            msg = f"🚨🚨🚨 긴급 청산 발동! (원전봇)\n"
                            msg += f"종목: {stock_code}\n"
                            msg += f"사유: {emergency_decision['reason']}\n"
                            msg += f"총 청산: {emergency_sells}주 @ ${current_price:.2f}\n"
                            msg += f"평단가: ${avg_price:.2f} | 수익률: {total_return_pct:+.1f}%\n"
                            msg += f"시장: {emergency_decision['market_desc']}\n"
                            msg += f"종목: {emergency_decision['stock_desc']}\n\n"
                            msg += f"📋 차수별 청산:\n"
                            
                            for detail in emergency_details:
                                msg += f"  • {detail['position']}차: {detail['amount']}주 "
                                msg += f"(${detail['entry_price']:.2f}→${detail['sell_price']:.2f}, {detail['return_pct']:+.1f}%)\n"
                            
                            msg += f"\n⏰ 쿨다운: {emergency_decision['cooldown_hours']}시간"
                            
                            discord_alert.SendMessage(msg)
                            
                            logger.critical(f"✅ {stock_code} 긴급 청산 완료: {emergency_sells}주")
                            logger.critical(f"⏰ 재매수 가능: {emergency_decision['cooldown_hours']}시간 후")
                            
                            return True  # 긴급 청산 완료, 더 이상 처리 안함
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔥🔥🔥 기존 매도 로직은 여기서부터 시작 (기존 코드 유지) 🔥🔥🔥
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
                            
                            # 🔥 매도 주문 실행 (실제 체결가 반환 받기)
                            result, actual_sell_price = self.handle_sell(stock_code, current_amount, current_price)

                            if result:
                                # 🔥 실제 체결가 사용 (조회 실패 시 현재가 사용)
                                final_sell_price = actual_sell_price if actual_sell_price else current_price
                                
                                # 🔥 실제 체결가 로깅 (가격 차이가 있을 때만)
                                if actual_sell_price and abs(actual_sell_price - current_price) > 0.01:
                                    price_diff = actual_sell_price - round(current_price * 0.99, 2)
                                    logger.info(f"💰 {stock_code} {position_num}차 적응형손절 체결가: ${final_sell_price:.2f} (가격차이: ${price_diff:+.2f})")
                                
                                # 개별 차수별 손익 계산 (실제 체결가 기준)
                                individual_return = (final_sell_price - entry_price) / entry_price * 100
                                
                                # 매도 기록 (실제 체결가 기록)
                                sell_record = {
                                    'date': datetime.now().strftime("%Y-%m-%d"),
                                    'price': final_sell_price,  # 🔥 실제 체결가 기록
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
                        # 🔥🔥🔥 [긴급 추가] 적응형 손절 후 즉시 JSON 저장! 🔥🔥🔥
                        try:
                            logger.warning(f"💾 {stock_code} 적응형 손절 데이터 저장 시작...")
                            self.save_split_data()
                            logger.warning(f"✅ {stock_code} 적응형 손절 데이터 저장 완료!")
                            # 🔥🔥🔥 GlobalSellHistory 즉시 업데이트 🔥🔥🔥
                            try:
                                # stock_data_info 찾기
                                stock_data_info = None
                                for data_info in self.split_data_list:
                                    if data_info['StockCode'] == stock_code:
                                        stock_data_info = data_info
                                        break
                                
                                if stock_data_info:
                                    # GlobalSellHistory 초기화
                                    if 'GlobalSellHistory' not in stock_data_info:
                                        stock_data_info['GlobalSellHistory'] = []
                                    
                                    # 매도된 각 차수를 GlobalSellHistory에 기록
                                    for magic_data in magic_data_list:
                                        if not magic_data['IsBuy'] and magic_data.get('CurrentAmt', 0) == 0:
                                            position_num = magic_data['Number']
                                            
                                            # SellHistory에서 가장 최근 적응형 손절 기록 찾기
                                            sell_history = magic_data.get('SellHistory', [])
                                            if sell_history:
                                                latest_sell = sell_history[-1]  # 가장 최근 매도
                                                
                                                # 적응형 손절인지 확인
                                                if '적응형손절' in latest_sell.get('reason', ''):
                                                    # GlobalSellHistory에 추가할 레코드 생성
                                                    global_sell_record = {
                                                        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                        'position_num': position_num,
                                                        'sell_price': latest_sell.get('price', 0),
                                                        'sell_amount': latest_sell.get('amount', 0),
                                                        'entry_price': latest_sell.get('avg_price_at_stop', 0),
                                                        'return_pct': latest_sell.get('return_pct', 0),
                                                        'record_type': 'adaptive_stop_loss',
                                                        'stop_loss_type': latest_sell.get('stop_loss_type', ''),
                                                        'preserved_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                                    }
                                                    
                                                    # 중복 체크
                                                    is_duplicate = False
                                                    for existing in stock_data_info['GlobalSellHistory']:
                                                        same_date = existing.get('date', '')[:16] == global_sell_record['date'][:16]
                                                        same_position = existing.get('position_num', 0) == position_num
                                                        same_price = abs(existing.get('sell_price', 0) - global_sell_record['sell_price']) < 0.01
                                                        
                                                        if same_date and same_position and same_price:
                                                            is_duplicate = True
                                                            break
                                                    
                                                    if not is_duplicate:
                                                        stock_data_info['GlobalSellHistory'].insert(0, global_sell_record)
                                                        logger.info(f"📋 {stock_code} {position_num}차 적응형 손절을 GlobalSellHistory에 즉시 기록")
                                    
                                    # 저장
                                    self.save_split_data()
                                    logger.info(f"✅ {stock_code} GlobalSellHistory 업데이트 및 저장 완료!")

                            except Exception as e:
                                logger.error(f"❌ {stock_code} GlobalSellHistory 업데이트 오류: {str(e)}")
                            # 🔥🔥🔥 추가 끝 🔥🔥🔥
                        except Exception as save_error:
                            logger.error(f"❌ {stock_code} 적응형 손절 데이터 저장 실패: {save_error}")
                            logger.error(f"   스택 트레이스: {traceback.format_exc()}")
                            # 저장 실패 시 긴급 알림
                            emergency_msg = f"⚠️⚠️⚠️ {stock_code} 적응형 손절 데이터 저장 실패!\n"
                            emergency_msg += f"매도 완료: {total_stop_amount}주\n"
                            emergency_msg += f"수동 확인 및 JSON 파일 복구 필요!\n"
                            emergency_msg += f"오류: {str(save_error)}"
                            if config.config.get("use_discord_alert", True):
                                discord_alert.SendMessage(emergency_msg)
                        # 🔥🔥🔥 [추가 끝] 🔥🔥🔥

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
            
            # 🔥 브로커 실제 보유 정보 조회 (🔧 API 오류 체크 강화)
            holdings = self.get_current_holdings(stock_code)
            
            # 🔧🔧🔧 핵심 개선: API 오류 체크 추가 🔧🔧🔧
            if holdings.get('api_error', False):
                logger.warning(f"⚠️ {stock_code} API 오류로 매도 처리 스킵")
                return False

            if holdings['amount'] == -1:  # API 오류
                logger.info(f"🔄 {stock_code} API 오류 - 기존 데이터 유지, 매도 처리 안함")
                return False
            
            broker_amount = holdings['amount']
            broker_avg_price = holdings['avg_price']

            # ✅ 수정된 코드 (안전!)
            if broker_amount <= 0:
                if holdings.get('api_error', False):
                    logger.warning(f"🔄 {stock_code} API 오류로 데이터 정리 차단 - 기존 상태 유지")
                    return False
                else:
                    # 🔥🔥🔥 핵심 개선: 즉시 정리하지 않고 확인 대기 🔥🔥🔥
                    
                    # 내부 보유 수량 계산
                    internal_total = sum([m['CurrentAmt'] for m in magic_data_list if m.get('IsBuy', False)])
                    
                    if internal_total > 0:
                        # 🚨 경고: 브로커 0인데 내부는 보유 중
                        logger.warning(f"⚠️⚠️⚠️ {stock_code} 브로커-내부 불일치 감지!")
                        logger.warning(f"   브로커: 0주")
                        logger.warning(f"   내부: {internal_total}주")
                        logger.warning(f"   📋 3회 연속 확인 후 정리 예정")
                        
                        # 🔥 불일치 카운터 증가
                        if not hasattr(self, 'mismatch_counters'):
                            self.mismatch_counters = {}
                        
                        counter_key = f"{stock_code}_zero_mismatch"
                        self.mismatch_counters[counter_key] = self.mismatch_counters.get(counter_key, 0) + 1
                        
                        current_count = self.mismatch_counters[counter_key]
                        logger.warning(f"   🔢 불일치 카운트: {current_count}/3")
                        
                        # 🔥 3회 연속 확인 후에만 정리
                        if current_count >= 3:
                            logger.error(f"🚨🚨🚨 {stock_code} 3회 연속 불일치 - 데이터 정리 실행")
                            
                            # 정리 전 백업
                            backup_data = {
                                'stock_code': stock_code,
                                'timestamp': datetime.now().isoformat(),
                                'broker_amount': 0,
                                'internal_data': [
                                    {
                                        'position': m['Number'],
                                        'amount': m['CurrentAmt'],
                                        'price': m.get('EntryPrice', 0),
                                        'date': m.get('EntryDate', '')
                                    }
                                    for m in magic_data_list if m.get('IsBuy', False)
                                ]
                            }
                            
                            # 백업 파일 저장
                            backup_file = f"/var/autobot/kisUS/emergency_backup_{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                            try:
                                import json
                                with open(backup_file, 'w') as f:
                                    json.dump(backup_data, f, indent=2)
                                logger.info(f"💾 긴급 백업 저장: {backup_file}")
                            except:
                                pass
                            
                            # 데이터 정리
                            for magic_data in magic_data_list:
                                if magic_data['IsBuy']:
                                    magic_data['CurrentAmt'] = 0
                                    magic_data['IsBuy'] = False
                                    magic_data['RemainingRatio'] = 0.0
                                    magic_data['PartialSellStage'] = 0
                                    for key in list(magic_data.keys()):
                                        if key.startswith('max_profit_'):
                                            magic_data[key] = 0
                            
                            self.save_split_data()
                            
                            # 카운터 리셋
                            self.mismatch_counters[counter_key] = 0
                            
                            # Discord 긴급 알림
                            emergency_msg = f"🚨🚨🚨 {stock_code} 데이터 정리 완료\n"
                            emergency_msg += f"브로커 0주 vs 내부 {internal_total}주 (3회 연속 확인)\n"
                            emergency_msg += f"백업: {backup_file}\n"
                            emergency_msg += f"수동 확인 필요!"
                            
                            if config.config.get("use_discord_alert", True):
                                discord_alert.SendMessage(emergency_msg)
                            
                            return False
                        else:
                            # 아직 3회 미만 - 다음 사이클까지 대기
                            logger.info(f"⏳ {stock_code} 다음 확인까지 대기 ({current_count}/3)")
                            return False
                    else:
                        # 내부도 비어있으면 정상
                        logger.debug(f"✅ {stock_code} 브로커-내부 모두 0주 (정상)")
                        return False

            # # 🔧🔧🔧 핵심 개선: API 오류 시 데이터 정리 차단 🔧🔧🔧
            # if broker_amount <= 0:
            #     if holdings.get('api_error', False):
            #         logger.warning(f"🔄 {stock_code} API 오류로 데이터 정리 차단 - 기존 상태 유지")
            #         return False
            #     else:
            #         logger.info(f"💎 {stock_code} 브로커 실제 보유 없음 - 내부 데이터 정리")
            #         for magic_data in magic_data_list:
            #             if magic_data['IsBuy']:
            #                 magic_data['CurrentAmt'] = 0
            #                 magic_data['IsBuy'] = False
            #                 magic_data['RemainingRatio'] = 0.0
            #                 magic_data['PartialSellStage'] = 0
            #                 # 최고점 리셋
            #                 for key in list(magic_data.keys()):
            #                     if key.startswith('max_profit_'):
            #                         magic_data[key] = 0
                    
            #         self.save_split_data()
            #         return False

            # 🔥 부분매도 설정 가져오기
            base_partial_config = self.get_partial_sell_config(stock_code)
            adjusted_partial_config = self.calculate_market_adjusted_sell_thresholds(stock_code, base_partial_config)

            # 🔥🔥🔥 3단계: 각 차수별로 혁신적인 부분매도 처리 🔥🔥🔥
            for magic_data in magic_data_list:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    
                    position_num = magic_data['Number']
                    entry_price = magic_data['EntryPrice']
                    current_amount = magic_data['CurrentAmt']
                    
                    # 🔧🔧🔧 핵심 개선: 브로커 평균단가 동기화 로직 제거 (진입가 보호) 🔧🔧🔧
                    effective_entry_price = entry_price
                    calculation_method = "내부기준"
                    
                    # 🔥 정확한 수익률 계산
                    position_return_pct = (current_price - effective_entry_price) / effective_entry_price * 100

                    # 🔥🔥🔥 [추가] 갭 하락 감지 및 최고점 조정 🔥🔥🔥
                    self.adjust_position_max_for_gap(
                        stock_code, magic_data, current_price, position_return_pct
                    )
                    # 🔥🔥🔥 갭 조정 완료 🔥🔥🔥

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
                                    'position': magic_data['Number'],
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
                                
                                # result, error = self.handle_sell(stock_code, current_amount, current_price)
                                result, actual_sell_price = self.handle_sell(stock_code, current_amount, current_price)
                                
                                if result:
                                    # ✅ 실제 체결가 사용 (조회 실패 시 현재가 사용)
                                    final_sell_price = actual_sell_price if actual_sell_price else current_price
                                    
                                    # ✅ 실제 체결가 로깅
                                    if actual_sell_price and abs(actual_sell_price - current_price) > 0.01:
                                        price_diff = actual_sell_price - round(current_price * 0.99, 2)
                                        logger.info(f"💰 {stock_code} {position_num}차 기존방식 체결가: ${final_sell_price:.2f} (가격차이: ${price_diff:+.2f})")
                                    
                                    # ✅ 실제 체결가로 수익률 재계산
                                    position_return_pct_actual = (final_sell_price - effective_entry_price) / effective_entry_price * 100
                                    
                                    # 기존 매도 처리 로직과 동일
                                    sell_record = {
                                        'date': datetime.now().strftime("%Y-%m-%d"),
                                        'price': final_sell_price,  # 🔥 실제 체결가 기록
                                        'amount': current_amount,
                                        'reason': f"{position_num}차 기존방식 트레일링스톱",
                                        'return_pct': position_return_pct_actual  # 🔥 실제 체결가 기준 수익률
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
                                        'position': magic_data['Number'],
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
                            # result, error = self.handle_sell(stock_code, realistic_sell_amount, current_price)
                            result, actual_sell_price = self.handle_sell(stock_code, realistic_sell_amount, current_price)
                            
                            if result:
                                # ✅ 실제 체결가 사용
                                final_sell_price = actual_sell_price if actual_sell_price else current_price
                                
                                # ✅ 실제 체결가 로깅
                                if actual_sell_price and abs(actual_sell_price - current_price) > 0.01:
                                    price_diff = actual_sell_price - round(current_price * 0.99, 2)
                                    logger.info(f"💰 {stock_code} {position_num}차 하이브리드매도 체결가: ${final_sell_price:.2f} (가격차이: ${price_diff:+.2f})")
                                
                                # ✅ 실제 체결가로 손익 재계산
                                position_return_pct = (final_sell_price - entry_price) / entry_price * 100
                                position_pnl = (final_sell_price - entry_price) * realistic_sell_amount
                                sell_fee = self.calculate_trading_fee(final_sell_price, realistic_sell_amount, False)
                                net_position_pnl = position_pnl - sell_fee
                                
                                remaining_amount = current_amount - realistic_sell_amount
                                original_amount = magic_data.get('OriginalAmt', current_amount)
                                is_full_sell = (remaining_amount == 0)
                                sell_ratio = realistic_sell_amount / original_amount if original_amount > 0 else 1.0
                                
                                sell_details.append({
                                    'position': magic_data['Number'],
                                    'amount': realistic_sell_amount,
                                    'remaining': remaining_amount,
                                    'entry_price': entry_price,
                                    'sell_price': final_sell_price,  # 🔥 실제 체결가
                                    'return_pct': position_return_pct,
                                    'max_profit': position_max,
                                    'pnl': net_position_pnl,
                                    'reason': hybrid_action['reason'],
                                    'sell_ratio': sell_ratio,
                                    'is_full_sell': is_full_sell,
                                    'stage': hybrid_action.get('type', '하이브리드'),
                                    'system_type': '하이브리드매도'
                                })
                                
                                # process_hybrid_sell_record 호출 시 실제 체결가 전달
                                self.process_hybrid_sell_record(
                                    stock_code, magic_data, realistic_sell_amount, 
                                    final_sell_price,  # 🔥 실제 체결가
                                    position_return_pct, hybrid_action
                                )
                                
                                total_sells += realistic_sell_amount
                                
                                # 매도 완료 시 처리 (기존 로직과 동일)
                                if magic_data['CurrentAmt'] <= 0:
                                    logger.info(f"📊 {stock_code} {position_num}차 완전 청산 완료")
                                    continue
                                    
                            else:
                                logger.error(f"❌ {stock_code} {position_num}차 하이브리드 매도 실패")
            
            # ⭐⭐⭐ 하이브리드 코드 추가 끝 ⭐⭐⭐

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

                    # 🔥 수정: pnl 값이 있는지 확인하고, 없으면 직접 계산
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

    # 🔥 1. 매수 후 동기화 함수 (추가)
    def sync_position_after_buy(self, stock_code, position_num, order_price, expected_amount):
        """매수 후 실제 체결가 동기화 - 개선 버전
        
        Args:
            stock_code: 종목 코드
            position_num: 매수한 차수 (1~5)
            order_price: 주문 가격
            expected_amount: 예상 매수량
        """
        try:
            time.sleep(3)  # 브로커 반영 대기 시간 증가
            
            # 🔍 1단계: 브로커 데이터 조회
            holdings = self.get_current_holdings(stock_code)
            if holdings.get('api_error', False) or holdings['amount'] <= 0:
                logger.warning(f"⚠️ {stock_code} 브로커 조회 실패 또는 보유량 없음 - 동기화 스킵")
                return
            
            broker_total_amount = holdings['amount']
            broker_avg_price = holdings['avg_price']
            
            # 🔍 2단계: 해당 차수 데이터 찾기 (latest_position 방식 대신 정확한 차수 지정)
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return
            
            target_position = stock_data_info['MagicDataList'][position_num - 1]
            
            # 🔍 3단계: 안전성 검증
            # 3-1. 해당 차수가 실제로 매수된 상태인지 확인
            if not target_position.get('IsBuy', False) or target_position.get('CurrentAmt', 0) <= 0:
                logger.warning(f"⚠️ {stock_code} {position_num}차 매수 상태가 아님 - 동기화 스킵")
                return
            
            # 3-2. 예상 수량과 실제 수량 대략적 일치 확인
            actual_position_amount = target_position['CurrentAmt']
            if abs(actual_position_amount - expected_amount) > max(1, expected_amount * 0.1):
                logger.warning(f"⚠️ {stock_code} {position_num}차 수량 불일치: 예상{expected_amount} vs 실제{actual_position_amount} - 동기화 스킵")
                return
            
            # 🔍 4단계: 실제 체결가 추정 및 검증
            current_entry_price = target_position['EntryPrice']
            
            # 4-1. 단일 포지션인 경우: 브로커 평균가 = 실제 체결가
            total_internal_amount = sum([
                magic_data['CurrentAmt'] for magic_data in stock_data_info['MagicDataList']
                if magic_data.get('IsBuy', False)
            ])
            
            if total_internal_amount == broker_total_amount and total_internal_amount == actual_position_amount:
                # 단일 포지션: 브로커 평균가가 실제 체결가
                estimated_execution_price = broker_avg_price
                sync_method = "단일포지션"
            else:
                # 다중 포지션: 주문가 기준으로 합리적 추정
                price_improvement = broker_avg_price - order_price
                estimated_execution_price = order_price + (price_improvement * 0.5)  # 보수적 추정
                sync_method = "다중포지션추정"
            
            # 4-2. 합리적 범위 검증
            order_diff_pct = abs(estimated_execution_price - order_price) / order_price * 100
            entry_diff_pct = abs(estimated_execution_price - current_entry_price) / current_entry_price * 100
            
            # 🔥 핵심 개선: 엄격한 범위 제한
            if order_diff_pct > 5.0:  # 주문가 대비 5% 초과 차이는 비정상
                logger.warning(f"⚠️ {stock_code} {position_num}차 가격 차이 과도: {order_diff_pct:.1f}% - 동기화 스킵")
                return
            
            if entry_diff_pct > 3.0:  # 기존 진입가 대비 3% 초과 차이는 신중하게
                logger.warning(f"⚠️ {stock_code} {position_num}차 진입가 차이 큼: {entry_diff_pct:.1f}% - 동기화 스킵")
                return
            
            # 🔍 5단계: 동기화 실행 (원래 의도에 맞게)
            if entry_diff_pct > 0.5:  # 0.5% 이상 차이날 때만 업데이트
                old_price = target_position['EntryPrice']
                target_position['EntryPrice'] = estimated_execution_price
                
                logger.info(f"✅ {stock_code} {position_num}차 실제체결가 동기화 완료:")
                logger.info(f"   방식: {sync_method}")
                logger.info(f"   주문가: ${order_price:.2f}")
                logger.info(f"   기존 진입가: ${old_price:.2f}")
                logger.info(f"   새 진입가: ${estimated_execution_price:.2f}")
                logger.info(f"   개선폭: ${estimated_execution_price - order_price:+.2f}")
                
                # 🔥 브로커 참조 정보 별도 저장 (데이터 보존)
                stock_data_info['BrokerSyncInfo'] = {
                    'avg_price': broker_avg_price,
                    'total_amount': broker_total_amount,
                    'last_sync_time': datetime.now().isoformat(),
                    'sync_position': position_num,
                    'sync_method': sync_method
                }
                
                # 저장
                self.save_split_data()
            else:
                logger.debug(f"✅ {stock_code} {position_num}차 가격 차이 미미 - 동기화 불필요")
        
        except Exception as e:
            logger.error(f"❌ {stock_code} {position_num}차 체결가 동기화 중 오류: {str(e)}")

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

    def calculate_volatility_adjusted_threshold(self, stock_code):
            """변동성 기반 적응형 임계값 계산 - 원전봇 전용"""
            try:
                # 🔥 설정파일에서 기본 임계값 읽기
                stock_config = config.target_stocks.get(stock_code, {})
                partial_config = stock_config.get('partial_sell_config', {})
                base_threshold = partial_config.get('first_sell_threshold', 12)
                
                # 적응형 시스템 비활성화시 기본값 반환
                if not partial_config.get('adaptive_threshold', False):
                    logger.info(f"{stock_code} 적응형 임계값 비활성화, 기본값 사용: {base_threshold}%")
                    return base_threshold
                
                # 🔥 설정파일에서 변동성 분석 설정 읽기 (안전한 방식)
                try:
                    # config 객체에서 volatility_analysis 찾기
                    if hasattr(config, 'volatility_analysis'):
                        volatility_config = config.volatility_analysis
                    elif hasattr(config, 'config') and 'volatility_analysis' in config.config:
                        volatility_config = config.config['volatility_analysis']
                    else:
                        raise AttributeError("volatility_analysis not found")
                except:
                    # 설정을 찾을 수 없으면 기본값 사용
                    volatility_config = {
                        'enable': True,
                        'volatility_thresholds': {'low': 2.0, 'medium': 3.5, 'high': 5.0},
                        'volatility_multipliers': {'low': 0.6, 'medium': 0.8, 'high': 1.0, 'ultra_high': 1.2},
                        'max_move_thresholds': {'stable': 5.0, 'volatile': 8.0},
                        'max_move_multipliers': {'stable': 0.95, 'normal': 1.05, 'volatile': 1.1},
                        'stock_ranges': {
                            'CCJ': {'min': 10, 'max': 18},
                            'LEU': {'min': 8, 'max': 15},
                            'BWXT': {'min': 6, 'max': 12}
                        },
                        'analysis_period': 90,
                        'recent_period': 30
                    }
                    logger.warning(f"{stock_code} 변동성 설정을 찾을 수 없어 기본값 사용")
                
                if not volatility_config.get('enable', True):
                    logger.info(f"{stock_code} 변동성 분석 비활성화, 기본값 사용: {base_threshold}%")
                    return base_threshold
                    
                # 변동성 기준값들
                vol_thresholds = volatility_config.get('volatility_thresholds', {})
                vol_low = vol_thresholds.get('low', 2.0)
                vol_medium = vol_thresholds.get('medium', 3.5)
                vol_high = vol_thresholds.get('high', 5.0)
                
                # 최대 변동폭 기준값들
                move_thresholds = volatility_config.get('max_move_thresholds', {})
                move_stable = move_thresholds.get('stable', 5.0)
                move_volatile = move_thresholds.get('volatile', 8.0)
                
                # 변동성별 조정 계수
                vol_multipliers = volatility_config.get('volatility_multipliers', {})
                
                # 분석 기간
                analysis_period = volatility_config.get('analysis_period', 90)
                recent_period = volatility_config.get('recent_period', 30)
                
                # 🔥 1단계: 변동성 분석
                try:
                    # SafeKisUS 임포트 확인 필요
                    df = SafeKisUS.safe_get_ohlcv_new(stock_code, "D", analysis_period)
                except NameError:
                    # SafeKisUS가 임포트되지 않은 경우
                    logger.error(f"{stock_code} SafeKisUS 모듈을 찾을 수 없음, 기본값 사용")
                    return base_threshold
                    
                if df is None or len(df) < 30:
                    logger.warning(f"{stock_code} 데이터 부족, 기본값 사용: {base_threshold}%")
                    return base_threshold
                    
                # 일별 변동성 계산 (표준편차 * 100)
                daily_volatility = df['close'].pct_change().std() * 100
                
                # 🔥 2단계: 최근 변동폭 계산
                recent_data = df.tail(recent_period)
                max_daily_move = recent_data['close'].pct_change().abs().max() * 100
                
                # 🔥 3단계: 설정값 기반 변동성 조정 계수 계산
                if daily_volatility < vol_low:           # 저변동성
                    volatility_multiplier = vol_multipliers.get('low', 0.6)
                    volatility_grade = "저변동성"
                elif daily_volatility < vol_medium:      # 중변동성
                    volatility_multiplier = vol_multipliers.get('medium', 0.8)
                    volatility_grade = "중변동성"
                elif daily_volatility < vol_high:        # 고변동성
                    volatility_multiplier = vol_multipliers.get('high', 1.0)
                    volatility_grade = "고변동성"
                else:                                    # 초고변동성
                    volatility_multiplier = vol_multipliers.get('ultra_high', 1.2)
                    volatility_grade = "초고변동성"
                
                # 🔥 4단계: 최대 변동폭 기반 추가 조정
                move_multipliers = volatility_config.get('max_move_multipliers', {})
                if max_daily_move > move_volatile:       # 극한변동
                    max_move_multiplier = move_multipliers.get('volatile', 1.1)
                    move_grade = "극한변동"
                elif max_daily_move > move_stable:       # 큰변동
                    max_move_multiplier = move_multipliers.get('normal', 1.05)
                    move_grade = "큰변동"
                else:                                    # 안정변동
                    max_move_multiplier = move_multipliers.get('stable', 0.95)
                    move_grade = "안정변동"
                
                # 🔥 5단계: 최종 적응형 임계값 계산
                adjusted_threshold = base_threshold * volatility_multiplier * max_move_multiplier
                
                # 🔥 6단계: 설정값 기반 범위 제한
                stock_ranges = volatility_config.get('stock_ranges', {})
                stock_range = stock_ranges.get(stock_code, {"min": 6, "max": 18})
                min_threshold = stock_range.get('min', 6)
                max_threshold = stock_range.get('max', 18)
                
                adjusted_threshold = max(min_threshold, min(max_threshold, adjusted_threshold))
                
                # 🔥 7단계: 상세 로깅
                logger.info(f"🎯 {stock_code} 변동성 기반 적응형 임계값 계산:")
                logger.info(f"   📊 일별변동성: {daily_volatility:.2f}% ({volatility_grade})")
                logger.info(f"   📊 최대변동폭: {max_daily_move:.2f}% ({move_grade})")
                logger.info(f"   📊 기본임계값: {base_threshold}% → 적응형임계값: {adjusted_threshold:.1f}%")
                logger.info(f"   📊 변동성계수: {volatility_multiplier:.2f}, 변동폭계수: {max_move_multiplier:.2f}")
                
                return round(adjusted_threshold, 1)
                
            except Exception as e:
                logger.error(f"❌ {stock_code} 변동성 기반 임계값 계산 오류: {str(e)}")
                # 에러시 기본값 반환
                stock_config = config.target_stocks.get(stock_code, {})
                partial_config = stock_config.get('partial_sell_config', {})
                fallback_threshold = partial_config.get('first_sell_threshold', 12)
                return fallback_threshold

    def get_adaptive_partial_sell_config(self, stock_code):
        """적응형 부분매도 설정 - 변동성 기반 임계값 적용"""
        try:
            # 기존 설정 가져오기
            target_stocks = config.target_stocks
            stock_config = target_stocks.get(stock_code, {})
            partial_config = stock_config.get('partial_sell_config', {})
            
            # 기본값 설정 (부분매도 비활성화)
            if not partial_config.get('enable', False):
                return None
            
            # 🔥 핵심: 변동성 기반 적응형 임계값 적용
            adaptive_threshold = self.calculate_volatility_adjusted_threshold(stock_code)
            
            # 기존 설정에 적응형 임계값 적용
            adaptive_config = {
                'first_sell_threshold': adaptive_threshold,                    # 🔥 적응형 임계값
                'first_sell_ratio': partial_config.get('first_sell_ratio', 0.33),
                'second_sell_threshold': partial_config.get('second_sell_threshold', adaptive_threshold + 10),
                'second_sell_ratio': partial_config.get('second_sell_ratio', 0.4),
                'final_sell_threshold': partial_config.get('final_sell_threshold', adaptive_threshold + 20),
                'trailing_after_partial': partial_config.get('trailing_after_partial', 0.05),
                'hybrid_protection': partial_config.get('hybrid_protection', {}),
                '_adaptive_applied': True,                                     # 🔥 적응형 적용 표시
                '_original_threshold': partial_config.get('first_sell_threshold', 12),  # 원본값 보존
                '_adaptive_threshold': adaptive_threshold                      # 계산된 값 보존
            }
            
            logger.info(f"✅ {stock_code} 적응형 부분매도 설정 적용:")
            logger.info(f"   🔄 고정임계값: {partial_config.get('first_sell_threshold', 12)}% → 적응형임계값: {adaptive_threshold}%")
            
            return adaptive_config
            
        except Exception as e:
            logger.error(f"❌ {stock_code} 적응형 부분매도 설정 오류: {str(e)}")
            return None

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
        news_setup_msg += "🔍 **분석 대상**: CCJ, BWXT, LEU \n"
        news_setup_msg += "📊 **매매 영향**: 긍정 뉴스 시 매수 조건 완화, 부정 뉴스 시 매수 차단\n"
        news_setup_msg += "🔧 **필요 설정**: .env 파일에 FINHUB_API_KEY, OPENAI_API_KEY 추가"
        
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
    """봇 실행 함수"""
    try:
        # 봇 초기화 및 실행
        bot = get_bot_instance()
        
        # 🔥 시작 시 예산 정보 출력
        logger.info(f"🚀 미국주식 스마트 매직 스플릿 봇 시작!")
        logger.info(f"💰 현재 예산: ${bot.total_money:,.0f}")
        logger.info(f"💱 통화: USD")
        
        target_stocks = config.target_stocks
        
        # 타겟 종목 현황 출력
        logger.info(f"🎯 미국주식 타겟 종목 현황:")
        for stock_code, stock_config in target_stocks.items():
            weight = stock_config.get('weight', 0)
            allocated_budget = bot.total_money * weight
            logger.info(f"  - {stock_config['name']}({stock_code}): 비중 {weight*100:.1f}% (${allocated_budget:,.0f})")

        # 🔥🔥🔥 AI Cash Target Seller 실행 (시간대 제어 추가) 🔥🔥🔥
        if hasattr(bot, 'cash_target_seller') and bot.cash_target_seller:
            try:
                # 실행 시점 체크 (00:00~05:30 KST만 실행)
                should_run = bot.should_run_cash_target_seller()
                
                if should_run:
                    cash_executed = bot.cash_target_seller.execute_if_needed()
                    if cash_executed:
                        logger.warning("💰 목표 현금 확보 완료")
                        time.sleep(2)
                else:
                    logger.debug("⏭️ AI 현금확보: 실행 시간대 아님 (초기 변동성 회피)")
                    
            except Exception as e:
                logger.error(f"❌ Cash Target Seller 오류: {e}")

        # 매매 로직 실행
        bot.process_trading()
        
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {str(e)}")

def send_startup_message():
    """원전봇 시작 메시지 전송 - 🔥 순수 원전 3종목 특화 버전 (4개봇 아키텍처)"""
    try:
        target_stocks = config.target_stocks
        
        msg = "🔥 순수 원전 3종목 완전 수직통합 봇 시작! (4개봇 아키텍처)\n"
        msg += "=" * 40 + "\n"
        msg += f"💱 통화: USD (달러)\n"
        msg += f"💵 설정 예산: ${config.absolute_budget:,.0f} (4개봇 재배분)\n"
        msg += f"📊 예산 전략: 순수 원전 집중 + 수직통합 완성\n"
        msg += f"🎯 차수 시스템: {config.div_num:.0f}차수 안정적 장기투자\n"
        
        # 🔥 순수 원전 수직통합 강조 - LEU 추가, VRT/RKLB 제거
        msg += f"\n🏭 **순수 원전 수직통합 포트폴리오** (4개봇 특화)\n"
        msg += f"⚛️ CCJ (40%) → 우라늄 채굴 (서방 1위)\n"
        msg += f"🔬 LEU (35%) → HALEU 농축 (미국 독점)\n"  # 🔥 VRT 대체
        msg += f"🏭 BWXT (25%) → SMR 기술 (선도기업)\n"
        # 🔥 RKLB 라인 완전 삭제
        
        # 🔥 LEU 특별 강조 - 새로 추가
        msg += f"\n🔥 **LEU (Centrus Energy) 독점성**\n"
        msg += f"✅ 미국 유일 HALEU 농축 기업\n"
        msg += f"✅ NRC 라이선스 + DOE 27억달러 10년 계약\n"
        msg += f"✅ 차세대 SMR 연료 독점 공급\n"
        msg += f"✅ 러시아 의존 탈피 핵심 기업\n"
        
        msg += f"\n🏆 **세계 유일 완전 원전 공급망**\n"
        msg += f"🔄 채굴(CCJ) → 농축(LEU) → 기술(BWXT)\n"
        msg += f"🔄 우라늄 원료 → HALEU 연료 → SMR 기술\n"
        msg += f"🔄 정부 정책 100% 수혜 구조\n"
        msg += f"🔄 러시아 대체 + 에너지 안보\n"
        
        msg += f"\n🎯 **원전 타겟 종목** (3개) - 순수 테마:\n"
        
        # 🔥 원전 특화 설명 - LEU 추가, VRT/RKLB 제거
        nuclear_descriptions = {
            "CCJ": ("우라늄 채굴 대장주", "서방 1위", "14% 수익매도", "안정적 공급"),
            "LEU": ("HALEU 농축 독점", "미국 유일", "15% 수익매도", "정부 계약"),  # 🔥 새로 추가
            "BWXT": ("SMR 기술 선도", "해군 원자로", "12% 수익매도", "기술 우위")
            # 🔥 VRT, RKLB 설명 완전 제거
        }
        
        for stock_code, stock_config in target_stocks.items():
            weight = stock_config.get('weight', 0)
            allocated = config.absolute_budget * weight
            
            # 타겟 수익률 정보
            profit_target = stock_config.get('profit_target', 10)
            first_sell = stock_config.get('partial_sell_config', {}).get('first_sell_threshold', 10)
            
            desc = nuclear_descriptions.get(stock_code, ("원전 기업", "안정성", "수익매도", "특화"))
            
            msg += f"  {stock_code} ({stock_config['name']})\n"
            msg += f"    💰 비중: {weight*100:.0f}% (${allocated:,.0f})\n"
            msg += f"    🎯 특징: {desc[0]} - {desc[1]}\n"
            msg += f"    📊 전략: {first_sell}% {desc[2]} + 하이브리드 보호\n"
            msg += f"    ⚡ 장점: {desc[3]}\n\n"
        
        msg += f"🔥 **4개 봇 아키텍처 내 역할**\n"
        msg += f"✅ 포트폴리오 안정성 담당 (44% 최대 비중)\n"  # 🔥 수정: 41% → 44%
        msg += f"✅ 5차수 장기 투자 (다른 봇은 3차수)\n"
        msg += f"✅ 정부 정책 수혜 + 에너지 안보\n"
        msg += f"✅ 뉴스 분석 마스터 (경제 캘린더 생성)\n"
        
        # 🔥 VRT, RKLB 이동 안내 추가
        msg += f"\n📋 **4개봇 분리 완료**\n"
        msg += f"🤖 VRT → AI봇으로 이동 (NVDA와 시너지)\n"
        msg += f"🚀 RKLB → 미래기술봇으로 이동 (IONQ와 혁신)\n"
        msg += f"⚛️ 원전봇 → 순수 원전 테마 100% 완성\n"
        
        msg += f"\n🎯 **기대 성과** (순수 원전)\n"
        msg += f"📊 연간 목표 수익률: 20-35% (중위험-중수익)\n"
        msg += f"📊 안정성: 정부 정책 + 독점적 지위\n"
        msg += f"📊 성장성: 원전 르네상스 + SMR 혁신\n"
        msg += f"📊 독점성: 세계 유일 완전 공급망\n"
        
        msg += f"\n📅 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        msg += f"\n🤖 버전: 순수 원전 수직통합 v3.0 (4개봇 아키텍처 + LEU 독점)"
        
        # Discord 전송
        # line_url = Common.GetSendURL(Common.GetNowDist())
        # Common.SendMessage(line_url, msg)
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(msg)

    except Exception as e:
        logger.error(f"원전봇 시작 메시지 전송 오류: {str(e)}")

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
        # 30분마다 차수별 트레일링 상태 상세 로그
        schedule.every(30).minutes.do(
            lambda: get_bot_instance().log_position_wise_trailing_status()
        ).tag('position_monitoring')
        
        logger.info("✅ 차수별 트레일링 모니터링 설정 완료 (30분마다)")
        
    except Exception as e:
        logger.error(f"향상된 모니터링 설정 중 오류: {str(e)}")

# 🔥 기존 스케줄링 함수들도 개선된 버전으로 교체하기 위한 함수
def setup_enhanced_monitoring_with_partial_sell():
    """부분매도 시스템을 포함한 향상된 모니터링 설정"""
    try:
        # 30분마다 부분매도 상태 로그
        schedule.every(30).minutes.do(
            lambda: get_bot_instance().log_partial_sell_status()
        ).tag('partial_sell_monitoring')
        
        logger.info("✅ 부분매도 시스템 모니터링 설정 완료 (30분마다)")
        
    except Exception as e:
        logger.error(f"부분매도 모니터링 설정 중 오류: {str(e)}")

def main():
    """메인 함수 - 미국주식용 설정 파일 자동 생성 포함"""
    
    # 🔥 1. 설정 파일 확인 및 생성 (가장 먼저 실행)
    config_created = check_and_create_config()
    
    if config_created:

        # 설정 파일이 새로 생성된 경우 사용자 안내
        user_msg = "🚀 미국주식 스마트 스플릿 봇 상승 추세 최적화 설정 완료!\n\n"
        user_msg += "📊 **차트 분석 기반 최적화 적용**\n"
        user_msg += f"💰 투자 예산: ${config.absolute_budget:,}\n"
        user_msg += f"💱 통화: USD (달러)\n"
        user_msg += f"🎯 진입 점수: 63/58/53/48/43점 (4-5점 완화)\n"
        user_msg += f"📈 진입 간격: 4.5/5.5/7/9% (기회 확대)\n"
        user_msg += f"💎 부분매도: 전종목 활성화\n\n"
        
        user_msg += "📊 **종목별 최적화 설정**:\n"

        chart_analysis = {
            "CCJ": ("우라늄 채굴 대장주", "1.5%", "14/22/32%", "서방 1위 독점"),
            "LEU": ("HALEU 농축 독점", "2.0%", "15/25/35%", "미국 유일 농축"),  # 🔥 VRT 대체
            "BWXT": ("SMR 기술 선도", "2.5%", "12/20/30%", "해군 원자로 기술")   # 🔥 기존 유지
            # 🔥 VRT, RKLB 완전 제거
        }

        for stock_code, stock_config in config.target_stocks.items():
            allocated = config.absolute_budget * stock_config.get('weight', 0)
            stock_type = stock_config.get('stock_type', 'normal')
            analysis, pullback, partial = chart_analysis.get(stock_code, ("일반", "2.5%", "비활성화"))
            
            user_msg += f"🎯 **{stock_config.get('name', stock_code)}** ({stock_code})\n"
            user_msg += f"   💰 {stock_config.get('weight', 0)*100:.1f}% (${allocated:,.0f}) - {stock_type}\n"
            user_msg += f"   📊 차트: {analysis}\n"
            user_msg += f"   📉 진입: {pullback} 조정\n"
            user_msg += f"   💎 부분매도: {partial}\n"
        
        user_msg += f"\n🎯 **핵심 개선 효과**:\n"
        user_msg += f"📈 매수 기회: +40-50% 증가\n"
        user_msg += f"🛡️ 수익 보호: +50% 개선 (부분매도)\n"
        user_msg += f"⚡ 회전율: +70% 향상\n"
        user_msg += f"🎯 적응성: +60% 개선\n\n"
        
        user_msg += f"🕐 미국 장 시간: 09:30-16:00 ET (한국시간 23:30-06:00)\n"
        user_msg += f"🚀 상승 추세에 최적화된 공격적 매매 전략\n"
        user_msg += f"\n⏰ 10초 후 봇이 시작됩니다..."
        
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
    
    # 2분마다 실행하도록 스케줄 설정
    # schedule.every(30).seconds.do(run_bot)
    schedule.every(2).minutes.do(run_bot)
 
    # 🔥🔥🔥 상승 추세 최적화 스케줄러 실행 🔥🔥🔥
    logger.info("🚀 상승 추세 최적화 스케줄러 시작")
    # logger.info("📊 매매 간격: 30초")
    # logger.info("🔄 동기화: 20분마다")
    logger.info("📈 진입 점수: 63/58/53/48/43점")
    logger.info("💎 부분매도: 전종목 활성화")    

    logger.info("🚀 최적화된 스케줄러 시작 (2분 간격)")
    logger.info("📊 API 호출 75% 감소로 안정성 향상")
    consecutive_errors = 0

    # 🔥🔥🔥 수정된 스케줄러 실행 🔥🔥🔥
    while True:
        try:
            
            # 🔥 미국 장 시간 체크
            is_trading_time, is_market_start = check_trading_time()    

            if not is_trading_time:
                logger.info("미국 장 시간 외입니다. 다음 장 시작까지 대기")
                time.sleep(300)  # 5분 대기
                continue    

            # 🔥 장 시작 시점 특별 처리
            if is_market_start:
                logger.info("🚀 미국 장 시작! 2분 간격 안정화 모드")
                logger.info("🚀 미국 장 시작! 상승 추세 최적화 전략 활성화")
                logger.info("📊 공격적 진입 조건으로 기회 포착 준비")

            # 📊 스케줄 체크 (항상 먼저 실행)
            schedule.run_pending()
            consecutive_errors = 0  # 성공시 리셋

            time.sleep(5)  # CPU 사용량을 줄이기 위해 짧은 대기 시간 추가

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