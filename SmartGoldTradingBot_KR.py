#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
개선된 스마트 매직 스플릿 봇 (SmartMagicSplitBot_KR_Enhanced) - 절대 예산 기반 동적 조정 버전
1. 절대 예산 기반 투자 (다른 매매봇과 독립적 운영)
2. 성과 기반 동적 예산 조정 (70%~140% 범위)
3. 안전장치 강화 (현금 잔고 기반 검증)
4. 🔥 적응형 쿨다운 시스템 (매도 후 즉시 재매수 방지)
5. 🔥 순차 진입 검증 강화 (이전 차수 보유 + 동적 하락률)
6. 🔥 개선된 매수 체결 추적 (실제 체결량 정확 계산)
7. 🔥 브로커 데이터 동기화 (실시간 일치 확인)
8. 기존 스플릿 로직 유지 (5차수 분할 매매)
"""

import KIS_Common as Common
import KIS_API_Helper_KR as KisKR
import discord_alert
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import os
import schedule

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
logger = logging.getLogger('SmartMagicSplitGoldLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'smart_magic_gold_split.log')
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

# KIS_API_Helper_KR과 KIS_Common 모듈에 로거 전달
try:
    KisKR.set_logger(logger)
    Common.set_logger(logger)
except:
    logger.warning("API 헬퍼 모듈에 로거를 전달할 수 없습니다.")

# ############################### 외국인-기관 매매흐름 라이브러리 ##############################
# try:
#     from foreign_institution_analyzer import trading_trend_analyzer
#     FI_ANALYZER_AVAILABLE = True
#     logger.info("✅ 외국인/기관 매매동향 분석기 로드 완료")
# except ImportError as e:
#     FI_ANALYZER_AVAILABLE = False
#     logger.warning(f"⚠️ 외국인/기관 분석기 로드 실패: {str(e)}")


# 🔥 API 초기화 (가장 먼저!)
Common.SetChangeMode()
logger.info("✅ API 초기화 완료 - 모든 KIS API 사용 가능")

################################### 통합된 설정 관리 시스템 ##################################
class SmartSplitConfig:
    """스마트 스플릿 설정 관리 클래스 - 개선된 버전"""
    
    def __init__(self, config_path: str = "smart_split_config_enhanced.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()

# SmartGoldTradingBot_KR.py의 기존 get_default_config() 함수 수정
# 백테스팅 결과: SmartMagicSplit 26.48% < Buy&Hold ~35% 문제 해결

    def get_default_config(self):
        """🥇 금투자 최적화 설정 - 일반 주식용 로직에서 금 ETF 특성 반영"""
        try:
            # 🔥 금투자 최적화 - 주식용 설정을 금 특성에 맞게 수정
            stock_type_templates = {
                "gold_etf_hedged": {  # 🆕 환헤지 금 ETF 전용 (KODEX 골드선물(H))
                    "hold_profit_target": 12,           # 🚀 35% → 12% (금은 안전자산, 현실적 목표)
                    "quick_profit_target": 6,           # 🚀 15% → 6% (빠른 수익 실현)  
                    "loss_cut": [-0.08, -0.12, -0.15, -0.18, -0.20],  # 🚀 손절선 완화 (금은 회복력 좋음)
                    "safety_protection_ratio": 0.88,    # 0.85 → 0.88 (금은 안정성 우선)
                    "time_based_sell_days": 180,        # 🚀 90일 → 180일 (금은 장기투자 유리)
                    "partial_sell_ratio": 0.50,         # 🚀 0.30 → 0.50 (절반만 매도로 장기보유)
                    "min_holding": 0,
                    "reentry_cooldown_base_hours": 2,   # 🚀 0.5시간 → 2시간 (금은 급등락 적음)
                    "min_pullback_for_reentry": 1.5,    # 🚀 0.8% → 1.5% (더 확실한 조정 대기)
                    "volatility_cooldown_multiplier": 0.8, # 금 특화 변동성 고려
                    "market_cooldown_adjustment": True,
                    "enable_sequential_validation": True,
                    "dynamic_drop_adjustment": True,
                    "uptrend_sell_ratio_multiplier": 0.6,  # 🚀 0.5 → 0.6 (상승장에서 적당히 매도)
                    "high_profit_sell_reduction": True,
                    "rsi_upper_bound": 90,              # 🚀 85 → 90 (금은 과매수 지속 가능)
                    "volatility_threshold": 0.8,        # 🆕 금 특화: 낮은 변동성 기준
                    "safe_haven_factor": True           # 🆕 안전자산 부스터
                },
                "gold_etf_unhedged": {  # 🆕 환노출 금 ETF 전용 (TIGER 골드선물)
                    "hold_profit_target": 15,           # 🚀 35% → 15% (환리스크 보상으로 약간 높게)
                    "quick_profit_target": 8,           # 🚀 15% → 8%
                    "loss_cut": [-0.10, -0.15, -0.18, -0.20, -0.22],  # 환리스크로 손절 좀더 빨리
                    "safety_protection_ratio": 0.85,    # 환리스크 있어서 좀더 공격적
                    "time_based_sell_days": 150,        # 180일 → 150일 (환율 변동성)
                    "partial_sell_ratio": 0.60,         # 0.50 → 0.60 (환위험으로 더 많이 매도)
                    "min_holding": 0,
                    "reentry_cooldown_base_hours": 1,   # 2시간 → 1시간 (환율 변동 활용)
                    "min_pullback_for_reentry": 2.0,    # 1.5% → 2.0% (환율 리스크 고려)
                    "volatility_cooldown_multiplier": 0.7,
                    "market_cooldown_adjustment": True,
                    "enable_sequential_validation": True,
                    "dynamic_drop_adjustment": True,
                    "uptrend_sell_ratio_multiplier": 0.7,  # 환리스크로 조금 더 매도
                    "high_profit_sell_reduction": True,
                    "rsi_upper_bound": 88,              # 90 → 88 (환율 변동성 고려)
                    "volatility_threshold": 1.2,        # 환율 변동으로 더 높은 변동성
                    "currency_hedge": False             # 🆕 환노출 표시
                },
                "gold_physical": {  # 🆕 금현물 ETF 전용 (ACE KRX 금현물)
                    "hold_profit_target": 10,           # 🚀 30% → 10% (현물은 가장 보수적)
                    "quick_profit_target": 5,           # 🚀 12% → 5%
                    "loss_cut": [-0.06, -0.10, -0.13, -0.15, -0.17],  # 현물은 가장 보수적
                    "safety_protection_ratio": 0.92,    # 현물 안정성 최우선
                    "time_based_sell_days": 365,        # 🚀 120일 → 365일 (현물은 초장기)
                    "partial_sell_ratio": 0.30,         # 0.25 → 0.30 (적게 매도)
                    "min_holding": 0,
                    "reentry_cooldown_base_hours": 4,   # 0.5시간 → 4시간 (현물은 더 신중)
                    "min_pullback_for_reentry": 1.2,    # 0.8% → 1.2%
                    "volatility_cooldown_multiplier": 0.9, # 0.6 → 0.9
                    "market_cooldown_adjustment": True,
                    "enable_sequential_validation": True,
                    "dynamic_drop_adjustment": True,
                    "uptrend_sell_ratio_multiplier": 0.4,  # 🚀 0.6 → 0.4 (현물은 장기보유 우선)
                    "high_profit_sell_reduction": True,
                    "rsi_upper_bound": 92,              # 🚀 85 → 92 (현물은 최고 관대)
                    "volatility_threshold": 0.6,        # 현물은 가장 낮은 변동성
                    "physical_premium": True            # 🆕 현물 프리미엄 고려
                }
            }
            
            # 🥇 금투자 최적화 포트폴리오 구성
            target_stocks_config = {
                "132030": {  # KODEX 골드선물(H) - 환헤지
                    "weight": 0.35,              # 비중 유지 (백테스팅 검증)
                    "stock_type": "gold_etf_hedged",
                    "name": "KODEX 골드선물(H)"
                },
                "319640": {  # TIGER 골드선물 - 환노출  
                    "weight": 0.35,              # 비중 유지 (백테스팅 검증)
                    "stock_type": "gold_etf_unhedged", 
                    "name": "TIGER 골드선물"
                },
                "411060": {  # ACE KRX 금현물 - 현물기반
                    "weight": 0.30,              # 비중 유지 (백테스팅 검증)
                    "stock_type": "gold_physical",
                    "name": "ACE KRX 금현물"
                }
            }

            # 종목별 설정 적용 (금투자 최적화)
            target_stocks = {}
            
            for stock_code, basic_config in target_stocks_config.items():
                try:
                    logger.info(f"🥇 금투자 최적화 설정 적용 중: {stock_code}")
                    
                    stock_type = basic_config.get("stock_type", "gold_etf_hedged")
                    type_template = stock_type_templates.get(stock_type, stock_type_templates["gold_etf_hedged"])
                    
                    # 금투자 최적화 설정 적용
                    optimized_config = {
                        "name": basic_config["name"],
                        "weight": basic_config["weight"],
                        "stock_type": stock_type,
                        **type_template  # 금투자 최적화된 모든 설정 적용
                    }
                    
                    target_stocks[stock_code] = optimized_config
                    
                    logger.info(f"✅ {basic_config['name']} 금투자 최적화 완료:")
                    logger.info(f"  └─ 목표수익률: {type_template['hold_profit_target']}% (금 특성 반영)")
                    logger.info(f"  └─ 쿨다운: {type_template['reentry_cooldown_base_hours']}시간 (금 변동성 고려)")
                    logger.info(f"  └─ 보유기간: {type_template['time_based_sell_days']}일 (장기투자)")
                    logger.info(f"  └─ RSI상한: {type_template['rsi_upper_bound']} (금 특성)")
                    
                except Exception as e:
                    logger.error(f"금투자 최적화 설정 적용 중 오류 {stock_code}: {str(e)}")

            # 🔥 금투자 특화 매매 파라미터
            return {
                "absolute_budget": 600000,  # 절대 예산 (60만원 기본)
                "target_stocks": target_stocks,
                
                # 🔥 금 특화 하락률 기준 (변동성 낮음 반영)
                "base_drops": [0, 0.015, 0.020, 0.025, 0.030],  # 🚀 1.5%~3% (기존 2.5%~4%에서 하향)
                
                # 금투자 특화 제어 시스템
                "enhanced_buy_control": {
                    "enable_adaptive_cooldown": True,
                    "enable_sequential_validation": True,  
                    "enable_enhanced_order_tracking": True,
                    "enable_broker_sync": True,
                    "gold_market_analysis": True,           # 🆕 금시장 분석 활성화
                    "safe_haven_detection": True,          # 🆕 안전자산 수요 감지
                    "currency_correlation": True,          # 🆕 환율 상관관계 분석
                    "volatility_adjustment": True          # 🆕 변동성 기반 조정
                },
                
                # 🔥 금투자 특화 시장 보호 (기존 주식용 수정)
                "market_protection": {
                    "enable_market_sentiment": True,
                    "bear_market_threshold": -15,           # -20 → -15 (금은 더 민감)
                    "volatility_protection": True,
                    "max_daily_trades": 2,                  # 3 → 2 (금은 적게 매매)
                    "emergency_stop_loss": -30,             # 🚀 -25 → -30 (금은 더 관대)
                    "safe_haven_boost": True               # 🆕 안전자산 부스터
                },
                
                # 성과 추적 (기존 유지)
                "performance_tracking": {
                    "daily_summary": True,
                    "weekly_report": True,
                    "monthly_analysis": True,
                    "benchmark_comparison": True,          # Buy & Hold와 비교
                    "gold_benchmark": "GLD"                # 🆕 금 ETF 벤치마크
                },
                
                # 리스크 관리 (금투자 특화)
                "risk_management": {
                    "max_position_size": 0.4,              # 종목당 최대 40% (기존 유지)
                    "cash_reserve_ratio": 0.1,             # 10% 현금 보유
                    "correlation_limit": 0.8,              # 🚀 0.7 → 0.8 (금 ETF는 상관성 높음)
                    "volatility_limit": 2.5,               # 🚀 2.0 → 2.5 (금은 변동성 낮음)
                    "drawdown_limit": -15,                 # 🚀 -12 → -15 (금은 더 관대)
                    "trend_confirmation_required": True
                },
                
                # 기타 설정들 (기존 유지)
                "div_num": 5,
                "buy_limit": True,
                "sell_limit": True,
                "fee_rate": 0.00015,
                "tax_rate": 0.0023,
                "use_discord_alert": True,
                "bot_name": "GoldETF_Optimized_Bot",        # 🚀 봇명 변경
                "version": "3.0_Gold_Optimized",           # 🚀 버전 업데이트
                "last_config_update": datetime.now().isoformat(),
                
                # 🚀 금투자 최적화 메타데이터
                "gold_optimization_metadata": {
                    "optimization_date": datetime.now().isoformat(),
                    "optimization_type": "Gold ETF Specialized",
                    "key_changes": {
                        "profit_targets_realistic": "35% → 10-15% (현실적)",
                        "rsi_bounds_relaxed": "85 → 90-92 (금 특성)",
                        "drop_requirements_lowered": "2.5-4% → 1.5-3% (변동성)",
                        "holding_period_extended": "90 → 150-365일 (장기)",
                        "foreign_analysis_removed": "금 ETF에 부적합한 분석 제거"
                    },
                    "expected_improvements": {
                        "reduced_false_signals": "RSI 과매수 신호 감소",
                        "better_entry_timing": "낮은 하락률 기준으로 진입 증가", 
                        "long_term_focus": "금의 장기 투자 특성 반영",
                        "realistic_targets": "달성 가능한 수익률 목표"
                    },
                    "risk_considerations": {
                        "currency_risk": "환노출 ETF 환율 리스크 고려",
                        "correlation_risk": "금 ETF간 높은 상관성",
                        "liquidity_risk": "금현물 ETF 유동성 고려",
                        "premium_discount": "NAV 괴리율 모니터링"
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"금투자 최적화 설정 생성 중 오류: {str(e)}")
            # 오류 시 기본 금투자 설정 반환
            return self._get_gold_fallback_config()

    def _get_gold_fallback_config(self):
        """금투자 기본 fallback 설정"""
        return {
            "absolute_budget": 600000,
            "target_stocks": {
                "132030": {
                    "name": "KODEX 골드선물(H)",
                    "weight": 0.4,
                    "stock_type": "gold_etf_hedged",
                    "hold_profit_target": 12,
                    "rsi_upper_bound": 90
                },
                "319640": {
                    "name": "TIGER 골드선물", 
                    "weight": 0.35,
                    "stock_type": "gold_etf_unhedged",
                    "hold_profit_target": 15,
                    "rsi_upper_bound": 88
                },
                "411060": {
                    "name": "ACE KRX 금현물",
                    "weight": 0.25, 
                    "stock_type": "gold_physical",
                    "hold_profit_target": 10,
                    "rsi_upper_bound": 92
                }
            },
            "base_drops": [0, 0.015, 0.020, 0.025, 0.030],  # 금 특화
            "div_num": 5,
            "use_discord_alert": True,
            "version": "3.0_Gold_Fallback"
        }

    def load_config(self):
            """설정 파일 로드 - 기본 설정 생성 통합"""
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # 기본 설정과 병합
                default_config = self.get_default_config()
                self.config = self._merge_config(default_config, loaded_config)
                logger.info(f"✅ 개선된 설정 파일 로드 완료: {self.config_path}")
                
            except FileNotFoundError:
                logger.info(f"📋 개선된 설정 파일이 없습니다. 기본 설정 파일을 생성합니다: {self.config_path}")
                self.config = self.get_default_config()
                self.save_config()
                self._send_creation_message()
                
            except Exception as e:
                logger.error(f"설정 파일 로드 중 오류: {str(e)}")
                self.config = self.get_default_config()
    
    def _send_creation_message(self):
        """개선된 설정 파일 생성 시 안내 메시지 전송"""
        try:
            setup_msg = f"🔧 개선된 스마트 스플릿 설정 파일 생성 완료!\n"
            setup_msg += f"📁 파일: {self.config_path}\n"
            setup_msg += f"💰 초기 예산: {self.config['absolute_budget']:,}원\n"
            setup_msg += f"🚀 버전: Enhanced 2.0 - 한국주식 특화\n\n"
            
            setup_msg += f"🔥 주요 개선사항:\n"
            setup_msg += f"• 적응형 쿨다운: 매도 후 즉시 재매수 방지\n"
            setup_msg += f"• 순차 진입 검증: 이전 차수 보유 + 하락률 필수 확인\n"
            setup_msg += f"• 개선된 주문 추적: 실제 체결량 정확 계산\n"
            setup_msg += f"• 브로커 동기화: 30분마다 데이터 일치 확인\n\n"
            
            target_stocks = self.config.get('target_stocks', {})
            setup_msg += f"📊 종목 설정:\n"
            for stock_code, stock_config in target_stocks.items():
                allocated = self.config['absolute_budget'] * stock_config.get('weight', 0)
                cooldown_hours = stock_config.get('reentry_cooldown_base_hours', 6)
                min_pullback = stock_config.get('min_pullback_for_reentry', 2.0)
                setup_msg += f"• {stock_config.get('name', stock_code)}: {stock_config.get('weight', 0)*100:.1f}% ({allocated:,.0f}원)\n"
                setup_msg += f"  └─ 쿨다운 {cooldown_hours}시간, 조정요구 {min_pullback}%\n"
            
            setup_msg += f"\n⚙️ 설정 변경은 {self.config_path} 파일을 수정하세요."
            setup_msg += f"\n🚨 주의: 기존 봇과 동시 실행 금지!"
            
            logger.info(setup_msg)
            
            if self.config.get("use_discord_alert", True):
                discord_alert.SendMessage(setup_msg)
        except Exception as alert_e:
            logger.warning(f"설정 파일 생성 메시지 전송 중 오류: {str(alert_e)}")
    
    def _merge_config(self, default, loaded):
        """설정 병합 (기본값 + 로드된 값)"""
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            self.config["last_config_update"] = datetime.now().isoformat()
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"✅ 개선된 설정 파일 저장 완료: {self.config_path}")
        except Exception as e:
            logger.error(f"설정 파일 저장 중 오류: {str(e)}")
    
    # 속성 접근자들 (기존 유지 + 개선된 항목 추가)
    @property
    def use_absolute_budget(self):
        return self.config.get("use_absolute_budget", True)
    
    @property
    def absolute_budget(self):
        return self.config.get("absolute_budget", 1000000)
    
    @property
    def absolute_budget_strategy(self):
        return self.config.get("absolute_budget_strategy", "proportional")
    
    @property
    def target_stocks(self):
        return self.config.get("target_stocks", {})
    
    @property
    def enhanced_buy_control(self):
        return self.config.get("enhanced_buy_control", {})
    
    def update_enhanced_metrics(self, metric_name, increment=1):
        """개선된 성과 지표 업데이트"""
        tracking = self.config.get("performance_tracking", {})
        enhanced_metrics = tracking.get("enhanced_metrics", {})
        enhanced_metrics[metric_name] = enhanced_metrics.get(metric_name, 0) + increment
        tracking["enhanced_metrics"] = enhanced_metrics
        self.config["performance_tracking"] = tracking
        self.save_config()

# 전역 설정 인스턴스
config = SmartSplitConfig()

# 봇 이름 설정
BOT_NAME = Common.GetNowDist() + "_" + config.config.get("bot_name", "SmartMagicSplitBot_Enhanced")

################################### 개선된 메인 클래스 ##################################

class SmartMagicSplit:

    def __init__(self):
        self.split_data_list = self.load_split_data()
        self.total_money = 0
        self.update_budget()
        self._upgrade_json_structure_if_needed()
        # 🔥 새로 추가: 매도 이력 추적을 위한 딕셔너리
        self.last_sell_time = {}  # {stock_code: datetime}
        # 🔥 새로 추가: 미체결 주문 추적
        self.pending_orders = {}  # {stock_code: order_info}
        self.pending_sell_orders = {}  # 🔥 매도용 (신규 추가) 

        # 🔥 손절 시스템 초기화
        self.stop_loss_history = {}  # 종목별 손절 이력
        self.daily_stop_count = 0    # 일일 손절 횟수
        self.last_stop_date = None   # 마지막 손절 날짜

        # 🔥 하락 보호 시스템 초기화
        self.position_size_multiplier = 1.0
        self.stop_loss_adjustment = 0.0
        self.max_positions_allowed = 5
        self.disable_high_risk_stocks = False
        # self.suspend_all_buys = True  # ← False를 True로 변경 (신규매수 완전 중단)
        self.suspend_all_buys = False  # ← 핵심 변경: True를 False로!
        self.bear_market_mode = False
        self.defer_new_entries_hours = 0
        self.last_trend_check_time = None
        self.current_protection_level = "normal"               

########################################### 추세적 하락 대응 시스템 ############################################

    def detect_market_trend_with_individual_stocks(self):
        """🚨 개별 종목 상황을 고려한 스마트 하락 보호 시스템"""
        try:
            # 🔥 1. 코스피 전체 상황 분석
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 90)
            if kospi_df is None or len(kospi_df) < 60:
                return "neutral", 0, {}
            
            current_price = kospi_df['close'].iloc[-1]
            
            # 이동평균선 계산
            ma5 = kospi_df['close'].rolling(5).mean().iloc[-1]
            ma20 = kospi_df['close'].rolling(20).mean().iloc[-1]
            ma60 = kospi_df['close'].rolling(60).mean().iloc[-1]
            
            # 고점 대비 하락률 계산
            recent_high = kospi_df['high'].rolling(60).max().iloc[-1]
            kospi_decline = (current_price - recent_high) / recent_high
            
            # 연속 하락일 계산
            consecutive_red_days = 0
            for i in range(len(kospi_df) - 1, 0, -1):
                if kospi_df['close'].iloc[i] < kospi_df['close'].iloc[i-1]:
                    consecutive_red_days += 1
                else:
                    break
            
            # 변동성 측정
            returns = kospi_df['close'].pct_change()
            volatility = returns.rolling(20).std().iloc[-1] * 100
            
            # 🔥 2. 보유 종목별 개별 상황 분석
            target_stocks = config.target_stocks
            individual_analysis = {}
            
            for stock_code, stock_info in target_stocks.items():
                try:
                    stock_df = Common.GetOhlcv("KR", stock_code, 60)
                    if stock_df is None or len(stock_df) < 30:
                        continue
                    
                    stock_current = stock_df['close'].iloc[-1]
                    stock_high = stock_df['high'].rolling(30).max().iloc[-1]
                    stock_decline = (stock_current - stock_high) / stock_high
                    
                    # 개별 종목 RSI
                    stock_rsi = self.get_technical_indicators(stock_code).get('rsi', 50)
                    
                    # 보유 포지션 확인
                    holdings = self.get_current_holdings(stock_code)
                    has_positions = holdings['amount'] > 0
                    
                    individual_analysis[stock_code] = {
                        'decline_rate': stock_decline,
                        'rsi': stock_rsi,
                        'has_positions': has_positions,
                        'stock_name': stock_info.get('name', stock_code),
                        'protection_needed': self._calculate_individual_protection_need(
                            stock_decline, stock_rsi, has_positions
                        )
                    }
                    
                except Exception as e:
                    logger.warning(f"{stock_code} 개별 분석 실패: {str(e)}")
                    continue
            
            # 🔥 3. 스마트 보호 결정 로직
            market_trend, risk_level, protection_msg = self._make_smart_protection_decision(
                kospi_decline, individual_analysis, consecutive_red_days, volatility
            )
            
            # 로깅
            logger.info(f"🔍 스마트 시장 분석: {market_trend}")
            logger.info(f"   📉 코스피 고점대비: {kospi_decline*100:.1f}%")
            logger.info(f"   🔴 연속하락: {consecutive_red_days}일")
            logger.info(f"   📊 변동성: {volatility:.1f}%")
            if individual_analysis:
                avg_individual_decline = sum(info['decline_rate'] for info in individual_analysis.values()) / len(individual_analysis)
                avg_rsi = sum(info['rsi'] for info in individual_analysis.values()) / len(individual_analysis)
                logger.info(f"   📈 개별종목 평균하락: {avg_individual_decline*100:.1f}%")
                logger.info(f"   📊 개별종목 평균RSI: {avg_rsi:.1f}")
            logger.info(f"   ⚠️ 위험수준: {risk_level}/10")
            logger.info(f"   🛡️ 보호사유: {protection_msg}")
            
            return market_trend, risk_level, {
                'kospi_decline': kospi_decline,
                'consecutive_red_days': consecutive_red_days,
                'volatility': volatility,
                'individual_analysis': individual_analysis,
                'protection_reason': protection_msg
            }
            
        except Exception as e:
            logger.error(f"스마트 하락 보호 분석 오류: {str(e)}")
            return "neutral", 5, {}

    def _calculate_individual_protection_need(self, stock_decline, rsi, has_positions):
        """개별 종목의 보호 필요성 계산"""
        protection_score = 0
        
        # 하락률 기준 점수 (완화된 기준)
        if stock_decline <= -0.25:      # -25% 이상
            protection_score += 4
        elif stock_decline <= -0.18:    # -18% 이상  
            protection_score += 3
        elif stock_decline <= -0.12:    # -12% 이상 (기존 -10%에서 완화)
            protection_score += 2
        elif stock_decline <= -0.08:    # -8% 이상 (기존 -5%에서 완화)
            protection_score += 1
        
        # RSI 과매도 구간에서는 보호 완화
        if rsi <= 25:
            protection_score -= 2  # 극한 과매도시 보호 완화
        elif rsi <= 35:
            protection_score -= 1  # 과매도시 보호 완화
        elif rsi >= 75:
            protection_score += 1  # 과매수시 보호 강화
        
        # 포지션 보유 상황 고려
        if has_positions:
            protection_score += 1  # 포지션 있으면 보호 약간 강화
        
        return max(0, protection_score)

    def _make_smart_protection_decision(self, kospi_decline, individual_analysis, consecutive_red_days, volatility):
        """스마트 보호 결정 - 개별 종목 상황 종합"""
        
        # 🔥 1. 코스피 기본 위험도 계산 (완화된 기준)
        if kospi_decline <= -0.25:      # -25% 이상 (기존 -20%)
            kospi_risk = 4
        elif kospi_decline <= -0.18:    # -18% 이상 (기존 -15%)
            kospi_risk = 3  
        elif kospi_decline <= -0.12:    # -12% 이상 (기존 -10%)
            kospi_risk = 2
        elif kospi_decline <= -0.08:    # -8% 이상 (기존 -5%)
            kospi_risk = 1
        else:
            kospi_risk = 0
        
        # 🔥 2. 개별 종목 상황 종합
        total_stocks = len(individual_analysis)
        if total_stocks == 0:
            return "neutral", 5, "종목 데이터 없음"
        
        # 종목별 보호 필요성 평균
        protection_scores = [info['protection_needed'] for info in individual_analysis.values()]
        avg_individual_risk = sum(protection_scores) / len(protection_scores)
        
        # 과매도 종목 비율 계산
        oversold_stocks = sum(1 for info in individual_analysis.values() if info['rsi'] <= 30)
        oversold_ratio = oversold_stocks / total_stocks
        
        # 포지션 보유 종목 수
        position_stocks = sum(1 for info in individual_analysis.values() if info['has_positions'])
        
        # 🔥 3. 추가 안전장치
        additional_risk = 0
        
        # 연속 하락일 체크 (완화)
        if consecutive_red_days >= 7:    # 기존 5→7일
            additional_risk += 2
        elif consecutive_red_days >= 5:  # 기존 3→5일
            additional_risk += 1
        
        # 변동성 체크 (완화)
        if volatility > 5.0:    # 기존 4.0→5.0
            additional_risk += 2
        elif volatility > 3.5:  # 기존 2.5→3.5
            additional_risk += 1
        
        # 🔥 4. 최종 보호 결정
        final_risk = kospi_risk + additional_risk
        
        # 개별 종목 상황이 양호하면 보호 완화
        protection_msg = f"코스피 {kospi_decline*100:.1f}% 하락"
        
        if avg_individual_risk <= 1.5 and oversold_ratio >= 0.5:
            final_risk -= 2
            protection_msg += f", 개별종목 과매도({oversold_ratio*100:.0f}%)로 보호 완화"
        
        # 포지션 보유가 적으면 보호 완화
        if position_stocks <= 1:
            final_risk -= 1
            protection_msg += f", 포지션 적음({position_stocks}개)으로 완화"
        
        # 개별 종목들이 모두 심각하면 보호 강화
        if avg_individual_risk >= 3.0:
            final_risk += 1
            protection_msg += f", 개별종목도 심각하여 보호 강화"
        
        # 최종 리스크 레벨 결정
        final_risk = max(0, min(4, final_risk))
        
        if final_risk == 0:
            return "normal", 3, protection_msg + " → 정상 운영"
        elif final_risk == 1:
            return "mild_protection", 4, protection_msg + " → 경미한 보호"
        elif final_risk == 2:
            return "moderate_protection", 6, protection_msg + " → 중간 보호" 
        elif final_risk == 3:
            return "strong_protection", 8, protection_msg + " → 강한 보호"
        else:
            return "emergency_protection", 10, protection_msg + " → 응급 보호"

    def detect_market_trend_enhanced(self):
        """🚨 강화된 시장 추세 감지 - 추세적 하락 대비"""
        try:
            # 🔥 1. 코스피 추세 분석
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 90)
            if kospi_df is None or len(kospi_df) < 60:
                return "neutral", 0, {}
            
            current_price = kospi_df['close'].iloc[-1]
            
            # 이동평균선 계산
            ma5 = kospi_df['close'].rolling(5).mean().iloc[-1]
            ma20 = kospi_df['close'].rolling(20).mean().iloc[-1]
            ma60 = kospi_df['close'].rolling(60).mean().iloc[-1]
            
            # 🔥 2. 고점 대비 하락률 계산
            recent_high = kospi_df['high'].rolling(60).max().iloc[-1]
            decline_from_high = (current_price - recent_high) / recent_high
            
            # 🔥 3. 연속 하락일 계산
            consecutive_red_days = 0
            for i in range(len(kospi_df) - 1, 0, -1):
                if kospi_df['close'].iloc[i] < kospi_df['close'].iloc[i-1]:
                    consecutive_red_days += 1
                else:
                    break
            
            # 🔥 4. 변동성 측정 (VIX 대용)
            returns = kospi_df['close'].pct_change()
            volatility = returns.rolling(20).std().iloc[-1] * 100
            
            # 🔥 5. 시장 폭 측정 (상승 종목 비율)
            # 실제로는 코스피200 개별 종목 데이터 필요하지만, 여기서는 근사치 사용
            market_breadth = self.calculate_market_breadth()
            
            # 🔥 6. 추세 등급 결정
            trend_score = 0
            
            # 이동평균선 배열
            if current_price > ma5 > ma20 > ma60:
                trend_score += 3  # 강한 상승
            elif current_price > ma5 > ma20:
                trend_score += 2  # 상승
            elif current_price > ma20:
                trend_score += 1  # 약한 상승
            elif current_price < ma5 < ma20:
                trend_score -= 2  # 하락
            elif current_price < ma5 < ma20 < ma60:
                trend_score -= 3  # 강한 하락
            
            # 고점 대비 하락률 반영
            if decline_from_high <= -0.20:
                trend_score -= 4  # 크래시 수준
            elif decline_from_high <= -0.15:
                trend_score -= 3  # 심각한 하락
            elif decline_from_high <= -0.10:
                trend_score -= 2  # 중간 하락
            elif decline_from_high <= -0.05:
                trend_score -= 1  # 경미한 하락
            
            # 연속 하락일 반영
            if consecutive_red_days >= 7:
                trend_score -= 3
            elif consecutive_red_days >= 5:
                trend_score -= 2
            elif consecutive_red_days >= 3:
                trend_score -= 1
            
            # 변동성 반영
            if volatility > 4.0:  # 한국주식 기준 고변동성
                trend_score -= 2
            elif volatility > 2.5:
                trend_score -= 1
            
            # 시장 폭 반영
            if market_breadth < 0.3:  # 30% 미만 상승
                trend_score -= 2
            elif market_breadth < 0.4:
                trend_score -= 1
            
            # 🔥 7. 최종 추세 판정
            if trend_score >= 4:
                market_trend = "strong_uptrend"
            elif trend_score >= 2:
                market_trend = "uptrend"
            elif trend_score >= -1:
                market_trend = "neutral"
            elif trend_score >= -3:
                market_trend = "downtrend"
            elif trend_score >= -6:
                market_trend = "strong_downtrend"
            else:
                market_trend = "crash"  # 🚨 크래시 수준
            
            # 🔥 8. 위험 수준 계산
            risk_level = max(0, min(10, -trend_score + 5))
            
            trend_details = {
                'decline_from_high': decline_from_high,
                'consecutive_red_days': consecutive_red_days,
                'volatility': volatility,
                'market_breadth': market_breadth,
                'trend_score': trend_score,
                'risk_level': risk_level,
                'ma5': ma5,
                'ma20': ma20,
                'ma60': ma60
            }
            
            logger.info(f"🔍 강화된 시장 분석: {market_trend}")
            logger.info(f"   📉 고점대비: {decline_from_high*100:.1f}%")
            logger.info(f"   🔴 연속하락: {consecutive_red_days}일")
            logger.info(f"   📊 변동성: {volatility:.1f}%")
            logger.info(f"   📈 시장폭: {market_breadth*100:.1f}%")
            logger.info(f"   ⚠️ 위험수준: {risk_level}/10")
            
            return market_trend, risk_level, trend_details
            
        except Exception as e:
            logger.error(f"강화된 시장 추세 감지 오류: {str(e)}")
            return "neutral", 5, {}

    def apply_smart_downtrend_protection(self, protection_level, risk_level, protection_reason):
        """스마트 하락 보호 적용 - 단계별 차등 적용"""
        try:
            if protection_level == "normal":
                # 정상 상태 - 보호 해제
                self.reset_protection_measures()
                return False, "정상 운영"
            
            elif protection_level == "mild_protection":
                # 경미한 보호 - 매수량만 소폭 축소
                self.position_size_multiplier = 0.9  # 10% 축소
                self.stop_loss_adjustment = 0.01     # 1%p 강화
                self.max_positions_allowed = 5       # 모든 차수 허용
                self.suspend_all_buys = False        # 매수 허용
                
                logger.warning(f"🟡 경미한 보호 활성화: {protection_reason}")
                protection_msg = "경미한 보호: 매수량 10% 축소"
                
            elif protection_level == "moderate_protection":
                # 중간 보호 - 기존 1단계와 유사하지만 완화
                self.position_size_multiplier = 0.8  # 20% 축소
                self.stop_loss_adjustment = 0.02     # 2%p 강화
                self.max_positions_allowed = 4       # 4차수까지 허용
                self.suspend_all_buys = False        # 매수 허용
                
                logger.warning(f"🟠 중간 보호 활성화: {protection_reason}")
                protection_msg = "중간 보호: 매수량 20% 축소, 4차수까지"
                
            elif protection_level == "strong_protection":
                # 강한 보호 - 기존 2단계와 유사하지만 매수 중단하지 않음
                self.position_size_multiplier = 0.6  # 40% 축소
                self.stop_loss_adjustment = 0.03     # 3%p 강화
                self.max_positions_allowed = 3       # 3차수까지만
                self.suspend_all_buys = False        # 매수는 허용 (중요!)
                
                logger.error(f"🔴 강한 보호 활성화: {protection_reason}")
                protection_msg = "강한 보호: 매수량 40% 축소, 3차수까지"
                
            else:  # emergency_protection
                # 응급 보호 - 매수 중단
                self.suspend_all_buys = True
                self.execute_emergency_partial_sell(0.2)  # 20% 매도 (기존 30%)
                self.bear_market_mode = True
                
                logger.error(f"🚨 응급 보호 활성화: {protection_reason}")
                protection_msg = "응급 보호: 매수 중단, 20% 응급매도"
            
            # Discord 알림
            if config.config.get("use_discord_alert", True):
                protection_alert = f"🛡️ **스마트 하락 보호 작동**\n"
                protection_alert += f"📊 {protection_reason}\n"
                protection_alert += f"🔧 조치: {protection_msg}"
                discord_alert.SendMessage(protection_alert)
            
            # 현재 보호 레벨 업데이트
            self.current_protection_level = protection_level
            
            return True, protection_msg
            
        except Exception as e:
            logger.error(f"스마트 하락 보호 적용 오류: {str(e)}")
            return False, f"보호 적용 실패: {str(e)}"

    def reset_protection_measures(self):
        """보호 조치 해제"""
        self.position_size_multiplier = 1.0
        self.stop_loss_adjustment = 0.0
        self.max_positions_allowed = 5
        self.disable_high_risk_stocks = False
        self.suspend_all_buys = False
        self.bear_market_mode = False
        self.current_protection_level = "normal"
        
        logger.info("✅ 모든 하락 보호 조치 해제 - 정상 운영 재개")

    def apply_downtrend_protection(self, market_trend, risk_level, trend_details):
        """🛡️ 추세적 하락 대비 보호 조치 적용"""
        try:
            protection_config = config.config.get('enhanced_downtrend_protection', {})
            if not protection_config.get('enable', True):
                return False, "하락 보호 시스템 비활성화"
            
            decline_from_high = trend_details.get('decline_from_high', 0)
            consecutive_red_days = trend_details.get('consecutive_red_days', 0)
            volatility = trend_details.get('volatility', 0)
            
            # 🚨 1단계: 경미한 하락 (-5% ~ -10%)
            if -0.10 <= decline_from_high < -0.05 or market_trend == "downtrend":
                logger.warning("🟡 1단계 하락 보호 활성화")
                
                # 매수량 20% 축소
                self.position_size_multiplier = 0.8
                
                # 손절선 2%p 강화
                self.stop_loss_adjustment = 0.02
                
                # 현금 비율 85%로 증가
                self.safety_cash_ratio = 0.85
                
                protection_msg = "1단계 하락 보호: 매수량 20% 축소, 손절선 강화"
                
            # 🚨 2단계: 중간 하락 (-10% ~ -15%)
            elif -0.15 <= decline_from_high < -0.10 or market_trend == "strong_downtrend":
                logger.error("🟠 2단계 하락 보호 활성화")
                
                # 매수량 40% 축소
                self.position_size_multiplier = 0.6
                
                # 손절선 4%p 강화
                self.stop_loss_adjustment = 0.04
                
                # 현금 비율 90%로 증가
                self.safety_cash_ratio = 0.90
                
                # 4-5차수 매수 중단
                self.max_positions_allowed = 3
                
                # 고위험 종목 매수 중단
                self.disable_high_risk_stocks = True
                
                protection_msg = "2단계 하락 보호: 매수량 40% 축소, 4-5차수 중단"
                
            # 🚨 3단계: 심각한 하락 (-15% ~ -20%)
            elif -0.20 <= decline_from_high < -0.15:
                logger.error("🔴 3단계 하락 보호 활성화")
                
                # 매수량 60% 축소
                self.position_size_multiplier = 0.4
                
                # 손절선 6%p 강화
                self.stop_loss_adjustment = 0.06
                
                # 현금 비율 95%로 증가
                self.safety_cash_ratio = 0.95
                
                # 최대 2차수만 허용
                self.max_positions_allowed = 2
                
                # 응급 부분 매도 30%
                self.execute_emergency_partial_sell(0.3)
                
                protection_msg = "3단계 하락 보호: 매수량 60% 축소, 응급 부분매도 30%"
                
            # 🚨 4단계: 크래시 수준 (-20% 이상)
            elif decline_from_high <= -0.20 or market_trend == "crash":
                logger.error("🚨 4단계 크래시 보호 활성화")
                
                # 모든 매수 중단
                self.suspend_all_buys = True
                
                # 응급 매도 70%
                self.execute_emergency_sell(0.7)
                
                # 현금 98% 보존
                self.safety_cash_ratio = 0.98
                
                # 베어마켓 모드 활성화
                self.bear_market_mode = True
                
                protection_msg = "4단계 크래시 보호: 모든 매수 중단, 응급매도 70%"
                
            # 🚨 변동성 스파이크 대응
            elif volatility > 4.0 or consecutive_red_days >= 5:
                logger.warning("⚡ 변동성 스파이크 보호 활성화")
                
                # 신규 진입 24시간 연기
                self.defer_new_entries_hours = 24
                
                # 손절선 3%p 강화
                self.stop_loss_adjustment = 0.03
                
                protection_msg = "변동성 보호: 24시간 진입 연기, 손절선 강화"
                
            else:
                # 정상 상태
                self.reset_protection_measures()
                return False, "정상 상태 - 보호 조치 없음"
            
            # 🔥 보호 조치 적용 알림
            if config.config.get("use_discord_alert", True):
                alert_msg = f"🛡️ **추세적 하락 보호 발동**\n"
                alert_msg += f"📊 시장 상황: {market_trend}\n"
                alert_msg += f"📉 고점 대비: {decline_from_high*100:.1f}%\n"
                alert_msg += f"🔴 연속 하락: {consecutive_red_days}일\n"
                alert_msg += f"⚠️ 위험 수준: {risk_level}/10\n"
                alert_msg += f"🛡️ 보호 조치: {protection_msg}\n"
                alert_msg += f"⏰ 적용 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                # discord_alert.SendMessage(alert_msg)
            
            logger.error(f"🛡️ {protection_msg}")
            return True, protection_msg
            
        except Exception as e:
            logger.error(f"하락 보호 조치 적용 오류: {str(e)}")
            return False, f"보호 조치 오류: {str(e)}"
            
    def execute_emergency_sell(self, sell_ratio):
        """🚨 응급 전량 매도 실행 (크래시 수준)"""
        try:
            logger.error(f"🚨 응급 전량 매도 실행: {sell_ratio*100:.0f}%")
            
            target_stocks = config.target_stocks
            total_emergency_sales = 0
            total_emergency_amount = 0
            
            for stock_code, stock_config in target_stocks.items():
                try:
                    stock_name = stock_config.get('name', stock_code)
                    holdings = self.get_current_holdings(stock_code)
                    
                    if holdings['amount'] > 0:
                        sell_amount = max(1, int(holdings['amount'] * sell_ratio))
                        current_price = KisKR.GetCurrentPrice(stock_code)
                        
                        logger.error(f"🚨 {stock_name} 응급 매도: {sell_amount:,}주")
                        
                        # 응급 매도 실행 (시장가 주문)
                        result, error = self.handle_emergency_sell(stock_code, sell_amount, current_price)
                        
                        if result:
                            total_emergency_sales += sell_amount
                            total_emergency_amount += sell_amount * current_price
                            logger.error(f"✅ {stock_name} 응급 매도 완료: {sell_amount:,}주")
                            
                            # 🔥 내부 데이터도 즉시 정리 (동기화)
                            self.emergency_clear_positions(stock_code, sell_amount)
                            
                        else:
                            logger.error(f"❌ {stock_name} 응급 매도 실패: {error}")
                            
                except Exception as stock_e:
                    logger.error(f"종목 {stock_code} 응급 매도 중 오류: {str(stock_e)}")
            
            # 응급 매도 완료 알림
            if total_emergency_sales > 0:
                emergency_msg = f"🚨 **응급 전량 매도 완료**\n"
                emergency_msg += f"매도 비율: {sell_ratio*100:.0f}%\n"
                emergency_msg += f"총 매도량: {total_emergency_sales:,}주\n"
                emergency_msg += f"매도 금액: {total_emergency_amount:,.0f}원\n"
                emergency_msg += f"사유: 크래시 수준 하락 보호\n"
                emergency_msg += f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(emergency_msg)
                
                # 응급 매도 성과 지표 업데이트
                config.update_enhanced_metrics("emergency_sells_executed", 1)
                    
            return total_emergency_sales > 0
            
        except Exception as e:
            logger.error(f"응급 전량 매도 실행 오류: {str(e)}")
            return False        

    def emergency_clear_positions(self, stock_code, sold_amount):
        """🚨 응급 매도 후 내부 데이터 즉시 정리"""
        try:
            # 해당 종목 데이터 찾기
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return
            
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🚨 모든 포지션 강제 정리
            total_cleared = 0
            for magic_data in stock_data_info['MagicDataList']:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    position_num = magic_data['Number']
                    current_amount = magic_data['CurrentAmt']
                    entry_price = magic_data['EntryPrice']
                    
                    # 현재가로 손익 계산
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price:
                        position_loss = (current_price - entry_price) * current_amount
                        self.update_realized_pnl(stock_code, position_loss)
                    
                    # 응급 매도 기록 생성
                    sell_record = {
                        'date': datetime.now().strftime("%Y-%m-%d"),
                        'time': datetime.now().strftime("%H:%M:%S"),
                        'price': current_price or entry_price,
                        'amount': current_amount,
                        'reason': f"{position_num}차 응급매도(크래시보호)",
                        'return_pct': ((current_price - entry_price) / entry_price * 100) if current_price and entry_price > 0 else 0,
                        'entry_price': entry_price,
                        'stop_type': 'emergency_sell',
                        'protection_level': 'crash',
                        'emergency_sell': True
                    }
                    
                    # SellHistory 추가
                    if 'SellHistory' not in magic_data:
                        magic_data['SellHistory'] = []
                    magic_data['SellHistory'].append(sell_record)
                    
                    # 포지션 완전 정리
                    magic_data['CurrentAmt'] = 0
                    magic_data['IsBuy'] = False
                    
                    # 최고점 리셋
                    for key in list(magic_data.keys()):
                        if key.startswith('max_profit_'):
                            magic_data[key] = 0
                    
                    total_cleared += current_amount
                    logger.error(f"🚨 {stock_name} {position_num}차 강제 정리: {current_amount:,}주")
            
            # 데이터 저장
            self.save_split_data()
            
            logger.error(f"🚨 {stock_name} 응급 정리 완료: {total_cleared:,}주")
            
        except Exception as e:
            logger.error(f"응급 포지션 정리 중 오류: {str(e)}")        
            
    def handle_emergency_sell(self, stock_code, amount, price):
        """🚨 응급 매도 처리 (시장가 우선)"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            logger.error(f"🚨 {stock_name} 응급 매도 시작: {amount:,}주")
            
            # 응급 상황이므로 시장가로 즉시 매도 시도
            emergency_price = int(price * 0.95)  # 5% 아래 가격으로 빠른 체결 유도
            
            result = KisKR.MakeSellLimitOrder(stock_code, amount, emergency_price)
            
            if result:
                logger.error(f"✅ {stock_name} 응급 매도 주문 완료")
                return result, None
            else:
                logger.error(f"❌ {stock_name} 응급 매도 주문 실패")
                return None, "응급 매도 주문 실패"
                
        except Exception as e:
            logger.error(f"❌ 응급 매도 처리 중 오류: {str(e)}")
            return None, str(e)

    def execute_emergency_partial_sell(self, sell_ratio):
        """🚨 응급 부분 매도 실행"""
        try:
            logger.error(f"🚨 응급 부분 매도 실행: {sell_ratio*100:.0f}%")
            
            target_stocks = config.target_stocks
            total_emergency_sales = 0
            
            for stock_code, stock_config in target_stocks.items():
                try:
                    stock_name = stock_config.get('name', stock_code)
                    holdings = self.get_current_holdings(stock_code)
                    
                    if holdings['amount'] > 0:
                        sell_amount = max(1, int(holdings['amount'] * sell_ratio))
                        current_price = KisKR.GetCurrentPrice(stock_code)
                        
                        logger.error(f"🚨 {stock_name} 응급 매도: {sell_amount:,}주")
                        
                        # 응급 매도 실행 (시장가 주문)
                        result, error = self.handle_emergency_sell(stock_code, sell_amount, current_price)
                        
                        if result:
                            total_emergency_sales += sell_amount
                            logger.error(f"✅ {stock_name} 응급 매도 완료: {sell_amount:,}주")
                        else:
                            logger.error(f"❌ {stock_name} 응급 매도 실패: {error}")
                            
                except Exception as stock_e:
                    logger.error(f"종목 {stock_code} 응급 매도 중 오류: {str(stock_e)}")
            
            # 응급 매도 완료 알림
            if total_emergency_sales > 0:
                emergency_msg = f"🚨 **응급 부분 매도 완료**\n"
                emergency_msg += f"매도 비율: {sell_ratio*100:.0f}%\n"
                emergency_msg += f"총 매도량: {total_emergency_sales:,}주\n"
                emergency_msg += f"사유: 추세적 하락 보호\n"
                emergency_msg += f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(emergency_msg)
                    
            return total_emergency_sales > 0
            
        except Exception as e:
            logger.error(f"응급 부분 매도 실행 오류: {str(e)}")
            return False

    def calculate_market_breadth(self):
        """시장 폭 계산 (상승 종목 비율)"""
        try:
            # 실제로는 코스피200 개별 종목 데이터가 필요
            # 여기서는 대표 종목들로 근사치 계산
            sample_stocks = ["005930", "000660", "035420", "051910", "068270"]  # 삼성전자, SK하이닉스 등
            
            up_count = 0
            total_count = 0
            
            for stock_code in sample_stocks:
                try:
                    df = Common.GetOhlcv("KR", stock_code, 5)
                    if df is not None and len(df) >= 2:
                        if df['close'].iloc[-1] > df['close'].iloc[-2]:
                            up_count += 1
                        total_count += 1
                except:
                    continue
            
            if total_count > 0:
                breadth = up_count / total_count
            else:
                breadth = 0.5  # 기본값
                
            return breadth
            
        except Exception as e:
            logger.error(f"시장 폭 계산 오류: {str(e)}")
            return 0.5

    def reset_protection_measures(self):
        """보호 조치 초기화"""
        self.position_size_multiplier = 1.0
        self.stop_loss_adjustment = 0.0
        self.safety_cash_ratio = 0.8
        self.max_positions_allowed = 5
        self.disable_high_risk_stocks = False
        self.suspend_all_buys = False
        self.bear_market_mode = False
        self.defer_new_entries_hours = 0

########################################### 손절시스템 ############################################

    def calculate_adaptive_stop_loss_threshold(self, stock_code, position_count, holding_days=0):
        """🔥 한국주식 특화 적응형 손절선 계산"""
        try:
            stop_config = config.config.get('enhanced_stop_loss', {})
            
            if not stop_config.get('enable', True):
                return None, "손절 시스템 비활성화"
            
            # 🎯 1단계: 차수별 기본 손절선
            thresholds = stop_config.get('adaptive_thresholds', {})
            
            if position_count == 1:
                base_threshold = thresholds.get('position_1', -0.15)
                category = "초기투자"
            elif position_count == 2:
                base_threshold = thresholds.get('position_2', -0.20)
                category = "추가투자"
            else:  # 3차수 이상
                base_threshold = thresholds.get('position_3_plus', -0.25)
                category = "전략완성"
            
            # 🔥 2단계: 종목별 개별 설정 확인
            stock_overrides = stop_config.get('stock_specific_overrides', {})
            if stock_code in stock_overrides:
                override_key = f'position_{position_count}' if position_count <= 2 else 'position_3_plus'
                if override_key in stock_overrides[stock_code]:
                    base_threshold = stock_overrides[stock_code][override_key]
                    category += f"(종목특화)"
                    logger.info(f"📊 {stock_code} 종목별 손절선 적용: {base_threshold*100:.1f}%")
            
            final_threshold = base_threshold
            adjustments = []
            
            # 🔥 3단계: 한국주식 변동성 기반 조정
            try:
                df = Common.GetOhlcv("KR", stock_code, 60)
                if df is not None and len(df) >= 30:
                    volatility = df['close'].pct_change().std() * 100
                    vol_config = stop_config.get('volatility_adjustment', {})
                    
                    high_threshold = vol_config.get('threshold_high', 6.0)
                    medium_threshold = vol_config.get('threshold_medium', 3.5)
                    
                    if volatility > high_threshold:
                        vol_adjustment = vol_config.get('high_volatility', -0.04)
                        vol_desc = f"고변동성({volatility:.1f}%)"
                    elif volatility > medium_threshold:
                        vol_adjustment = vol_config.get('medium_volatility', -0.02)
                        vol_desc = f"중변동성({volatility:.1f}%)"
                    else:
                        vol_adjustment = vol_config.get('low_volatility', 0.0)
                        vol_desc = f"저변동성({volatility:.1f}%)"
                    
                    final_threshold += vol_adjustment
                    if vol_adjustment != 0:
                        adjustments.append(f"{vol_desc} {vol_adjustment*100:+.1f}%p")
                else:
                    vol_desc = "변동성 계산 불가"
            except Exception as vol_e:
                logger.warning(f"변동성 계산 실패: {str(vol_e)}")
                vol_desc = "변동성 계산 실패"
            
            # 🔥 4단계: 시장 상황 기반 조정 (코스피 기준)
            market_config = stop_config.get('market_adjustment', {})
            if market_config.get('enable', True) and market_config.get('kospi_based', True):
                market_timing = self.detect_market_timing()
                market_adjustments = market_config.get('adjustments', {})
                
                market_adj = market_adjustments.get(market_timing, 0.0)
                final_threshold += market_adj
                
                if market_adj != 0:
                    adjustments.append(f"코스피{market_timing} {market_adj*100:+.1f}%p")
            
            # 🔥 5단계: 시간 기반 강화
            time_config = stop_config.get('time_based_rules', {})
            if time_config.get('enable', True) and holding_days > 0:
                time_rules = time_config.get('rules', {})
                time_adjustment = 0
                time_desc = ""
                
                if holding_days >= 365:
                    time_threshold = time_rules.get('365_day_threshold', -0.05)
                    if time_threshold > final_threshold:  # 더 엄격한 기준 적용
                        time_adjustment = time_threshold - final_threshold
                        time_desc = f"1년보유 강화"
                elif holding_days >= 180:
                    time_threshold = time_rules.get('180_day_threshold', -0.08)
                    if time_threshold > final_threshold:
                        time_adjustment = time_threshold - final_threshold
                        time_desc = f"6개월보유 강화"
                elif holding_days >= 90:
                    time_threshold = time_rules.get('90_day_threshold', -0.12)
                    if time_threshold > final_threshold:
                        time_adjustment = time_threshold - final_threshold
                        time_desc = f"3개월보유 강화"
                
                if time_adjustment != 0:
                    final_threshold += time_adjustment
                    adjustments.append(f"{time_desc} {time_adjustment*100:+.1f}%p")
            
            # 🔥 6단계: 안전 범위 제한
            min_threshold = base_threshold * 0.5   # 기본값의 50%까지 완화 가능
            max_threshold = base_threshold * 1.5   # 기본값의 150%까지 강화 가능
            final_threshold = max(min_threshold, min(final_threshold, max_threshold))
            
            # 최종 결과
            adjustment_desc = f"{category} (기본{base_threshold*100:.1f}%"
            if adjustments:
                adjustment_desc += f" + {', '.join(adjustments)}"
            adjustment_desc += f" = 최종{final_threshold*100:.1f}%)"
            
            return final_threshold, adjustment_desc
            
        except Exception as e:
            logger.error(f"적응형 손절선 계산 오류: {str(e)}")
            return -0.20, f"계산 오류: 기본 -20% 적용"

    def check_emergency_stop_conditions(self):
        """🔥 비상 손절 조건 체크"""
        try:
            stop_config = config.config.get('enhanced_stop_loss', {})
            emergency_config = stop_config.get('emergency_stop', {})
            
            if not emergency_config.get('enable', True):
                return False, ""
            
            # 🚨 1. 전체 포트폴리오 손실 체크
            balance = KisKR.GetBalance()
            current_total = float(balance.get('TotalMoney', 0))
            initial_asset = config.config.get("initial_total_asset", current_total)
            
            if initial_asset > 0:
                total_loss_rate = (initial_asset - current_total) / initial_asset
                emergency_threshold = emergency_config.get('total_portfolio_loss', -0.30)
                
                if total_loss_rate > abs(emergency_threshold):
                    return True, f"전체 포트폴리오 손실 한계 초과: {total_loss_rate*100:.1f}% > {abs(emergency_threshold)*100:.0f}%"
            
            # 🚨 2. 일일 손절 한도 체크
            today = datetime.now().strftime("%Y-%m-%d")
            daily_limit = emergency_config.get('daily_stop_limit', 2)
            
            if self.last_stop_date == today and self.daily_stop_count >= daily_limit:
                return True, f"일일 손절 한도 초과: {self.daily_stop_count}/{daily_limit}"
            
            # 🚨 3. 연속 손절 체크
            consecutive_limit = emergency_config.get('consecutive_stops', 4)
            recent_stops = self.count_recent_consecutive_stops()
            
            if recent_stops >= consecutive_limit:
                return True, f"연속 손절 한도 초과: {recent_stops}/{consecutive_limit}"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"비상 손절 조건 체크 오류: {str(e)}")
            return False, ""

    def count_recent_consecutive_stops(self):
        """최근 연속 손절 횟수 계산"""
        try:
            consecutive_count = 0
            today = datetime.now()
            
            for stock_data in self.split_data_list:
                stock_code = stock_data['StockCode']
                
                for magic_data in stock_data.get('MagicDataList', []):
                    for sell_record in magic_data.get('SellHistory', []):
                        reason = sell_record.get('reason', '')
                        
                        if '적응형손절' in reason or '손절' in reason:
                            try:
                                sell_date = datetime.strptime(sell_record.get('date', ''), "%Y-%m-%d")
                                days_ago = (today - sell_date).days
                                
                                if days_ago <= 7:  # 최근 7일 내
                                    consecutive_count += 1
                            except:
                                continue
            
            return consecutive_count
            
        except Exception as e:
            logger.error(f"연속 손절 계산 오류: {str(e)}")
            return 0

    def execute_adaptive_stop_loss(self, stock_code, indicators, magic_data_list):
        """🔥 하락 보호가 통합된 한국주식 적응형 손절 실행 - process_trading에 통합될 핵심 함수"""
        try:
            # 🚨 비상 손절 조건 먼저 체크
            emergency_stop, emergency_reason = self.check_emergency_stop_conditions()
            if emergency_stop:
                logger.error(f"🚨 비상 손절 발동: {emergency_reason}")
                if config.config.get("use_discord_alert", True):
                    emergency_msg = f"🚨 **비상 손절 발동** 🚨\n"
                    emergency_msg += f"사유: {emergency_reason}\n"
                    emergency_msg += f"모든 자동 매매 중단"
                    discord_alert.SendMessage(emergency_msg)
                return True  # 비상 상황으로 매매 중단
            
            current_price = indicators['current_price']
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥 전체 포지션 정보 계산
            total_investment = 0
            total_shares = 0
            active_positions = []
            first_buy_date = None
            
            for magic_data in magic_data_list:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    total_investment += magic_data['EntryPrice'] * magic_data['CurrentAmt']
                    total_shares += magic_data['CurrentAmt']
                    active_positions.append(magic_data)
                    
                    # 첫 매수 날짜 추적
                    entry_date = magic_data.get('EntryDate', '')
                    if entry_date and entry_date != "":
                        try:
                            buy_date = datetime.strptime(entry_date, "%Y-%m-%d")
                            if first_buy_date is None or buy_date < first_buy_date:
                                first_buy_date = buy_date
                        except:
                            pass
            
            if total_shares <= 0:
                return False  # 보유 없음
            
            # 🔥 전체 평균 수익률 계산
            avg_entry_price = total_investment / total_shares
            total_return_pct = (current_price - avg_entry_price) / avg_entry_price * 100
            position_count = len(active_positions)
            holding_days = (datetime.now() - first_buy_date).days if first_buy_date else 0
            
            # 🔥 기존 적응형 손절선 계산
            stop_threshold, threshold_desc = self.calculate_adaptive_stop_loss_threshold(
                stock_code, position_count, holding_days
            )
            
            if stop_threshold is None:
                return False  # 손절 시스템 비활성화
            
            # 🚨🚨🚨 하락 보호 추가 조정 적용 🚨🚨🚨
            protection_adjustment = getattr(self, 'stop_loss_adjustment', 0.0)
            protection_level = getattr(self, 'current_protection_level', 'normal')
            
            if protection_adjustment != 0:
                original_threshold = stop_threshold
                stop_threshold += protection_adjustment  # 하락 보호 조정 적용
                
                # 🛡️ 하락장에서는 추가 완화 (기회 제공)
                if protection_level in ['downtrend', 'strong_downtrend']:
                    additional_relief = -0.02  # 2%p 추가 완화
                    stop_threshold += additional_relief
                    protection_desc = f" + 하락보호 {protection_adjustment*100:+.1f}%p + 하락장완화 {additional_relief*100:+.1f}%p"
                elif protection_level in ['moderate_decline', 'severe_decline']:
                    protection_desc = f" + 하락보호 {protection_adjustment*100:+.1f}%p"
                else:
                    protection_desc = f" + 하락보호 {protection_adjustment*100:+.1f}%p"
                
                # 🔧 안전 범위 제한 (기존 threshold의 50% ~ 150% 사이)
                min_threshold = original_threshold * 0.5
                max_threshold = original_threshold * 1.5
                stop_threshold = max(min_threshold, min(stop_threshold, max_threshold))
                
                threshold_desc += protection_desc + f" = 최종 {stop_threshold*100:.1f}%"
                
                logger.info(f"🛡️ {stock_name} 하락보호 손절선 조정:")
                logger.info(f"   기존: {original_threshold*100:.1f}%")
                logger.info(f"   최종: {stop_threshold*100:.1f}%")
                logger.info(f"   보호수준: {protection_level}")
                logger.info(f"   조정폭: {(stop_threshold - original_threshold)*100:+.1f}%p")
            
            stop_threshold_pct = stop_threshold * 100
            
            # 🔥 손절 조건 판단
            if total_return_pct <= stop_threshold_pct:
                
                logger.warning(f"🚨 {stock_name} 적응형 손절 발동!")
                logger.warning(f"   💰 평균가: {avg_entry_price:,.0f}원 → 현재가: {current_price:,.0f}원")
                logger.warning(f"   📊 손실률: {total_return_pct:.1f}% ≤ 손절선: {stop_threshold_pct:.1f}%")
                logger.warning(f"   🔢 활성차수: {position_count}개")
                logger.warning(f"   📅 보유기간: {holding_days}일")
                logger.warning(f"   🎯 {threshold_desc}")
                
                # 🚨 하락 보호 상태 추가 로깅
                if protection_adjustment != 0:
                    logger.warning(f"   🛡️ 하락보호: {protection_level} 수준 적용")
                    logger.warning(f"   📉 조정효과: 손절선 {protection_adjustment*100:+.1f}%p 변경")
                
                # 🔥 손절 실행 (모든 포지션 정리)
                total_stop_amount = 0
                position_details = []
                total_realized_loss = 0
                
                # 🔥 데이터 백업 (롤백용)
                stop_config = config.config.get('enhanced_stop_loss', {})
                execution_options = stop_config.get('execution_options', {})
                
                if execution_options.get('data_backup_before_stop', True):
                    backup_data = {
                        'magic_data_list': [magic_data.copy() for magic_data in magic_data_list],
                        'timestamp': datetime.now().isoformat(),
                        'protection_level': protection_level,
                        'protection_adjustment': protection_adjustment
                    }
                
                try:
                    for magic_data in magic_data_list:
                        if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                            position_num = magic_data['Number']
                            current_amount = magic_data['CurrentAmt']
                            entry_price = magic_data['EntryPrice']
                            
                            # 개별 차수 손익 계산
                            individual_return_pct = (current_price - entry_price) / entry_price * 100
                            position_loss = (current_price - entry_price) * current_amount
                            
                            # 🔥 한국주식 매도 주문
                            result, error = self.handle_sell(stock_code, current_amount, current_price)
                            
                            if result:
                                # 🚨 하락 보호 정보가 포함된 손절 기록 생성
                                sell_record = {
                                    'date': datetime.now().strftime("%Y-%m-%d"),
                                    'time': datetime.now().strftime("%H:%M:%S"),
                                    'price': current_price,
                                    'amount': current_amount,
                                    'reason': f"{position_num}차 적응형손절",
                                    'return_pct': individual_return_pct,
                                    'entry_price': entry_price,
                                    'stop_threshold': stop_threshold_pct,
                                    'threshold_desc': threshold_desc,
                                    'holding_days': holding_days,
                                    'position_count': position_count,
                                    'total_return_at_stop': total_return_pct,
                                    'avg_price_at_stop': avg_entry_price,
                                    'stop_type': 'adaptive_stop_loss',
                                    'protection_level': protection_level,  # 🆕 하락 보호 수준
                                    'protection_adjustment': protection_adjustment,  # 🆕 보호 조정값
                                    'protection_applied': protection_adjustment != 0  # 🆕 보호 적용 여부
                                }
                                
                                # SellHistory 추가
                                if 'SellHistory' not in magic_data:
                                    magic_data['SellHistory'] = []
                                magic_data['SellHistory'].append(sell_record)
                                
                                # 포지션 정리
                                magic_data['CurrentAmt'] = 0
                                magic_data['IsBuy'] = False
                                
                                # 최고점 리셋
                                for key in list(magic_data.keys()):
                                    if key.startswith('max_profit_'):
                                        magic_data[key] = 0
                                
                                total_stop_amount += current_amount
                                total_realized_loss += position_loss
                                position_details.append(
                                    f"{position_num}차 {current_amount}주({individual_return_pct:+.1f}%)"
                                )
                                
                                logger.info(f"✅ {stock_name} {position_num}차 손절 완료: "
                                        f"{current_amount}주 @ {current_price:,.0f}원 ({individual_return_pct:+.1f}%)")
                            else:
                                logger.error(f"❌ {stock_name} {position_num}차 손절 주문 실패: {error}")
                                # 실패한 경우 백업으로 롤백할 수 있도록 준비
                                raise Exception(f"손절 주문 실패: {error}")
                    
                    # 🔥 손절 완료 후 처리
                    if total_stop_amount > 0:
                        
                        # 🚨 하락 보호 손절 실행 횟수 증가
                        if not hasattr(self, 'last_stop_date'):
                            self.last_stop_date = None
                        if not hasattr(self, 'daily_stop_count'):
                            self.daily_stop_count = 0
                        
                        today = datetime.now().strftime("%Y-%m-%d")
                        if self.last_stop_date != today:
                            self.daily_stop_count = 1
                            self.last_stop_date = today
                        else:
                            self.daily_stop_count += 1
                        
                        # 실현손익 업데이트
                        self.update_realized_pnl(stock_code, total_realized_loss)
                        
                        # 🚨 하락 보호 성과 지표 업데이트
                        if hasattr(config, 'update_enhanced_metrics'):
                            config.update_enhanced_metrics("stop_loss_executions", 1)
                            if protection_adjustment != 0:
                                config.update_enhanced_metrics("downtrend_protections_activated", 1)
                        
                        # 데이터 저장
                        self.save_split_data()
                        
                        # 🔥 손절 완료 알림 (하락 보호 정보 포함)
                        msg = f"🚨 {stock_name} 적응형 손절 완료!\n"
                        msg += f"  📊 {threshold_desc}\n"
                        msg += f"  💰 평균가: {avg_entry_price:,.0f}원 → 현재가: {current_price:,.0f}원\n"
                        msg += f"  📉 손실률: {total_return_pct:.1f}% (손절선: {stop_threshold_pct:.1f}%)\n"
                        msg += f"  🔢 총매도: {total_stop_amount}주 ({position_count}개 차수)\n"
                        msg += f"  📋 세부내역: {', '.join(position_details)}\n"
                        msg += f"  📅 보유기간: {holding_days}일\n"
                        msg += f"  💸 실현손실: {total_realized_loss:+,.0f}원\n"
                        msg += f"  🕐 일일손절: {self.daily_stop_count}회\n"
                        
                        # 🚨 하락 보호 정보 추가
                        if protection_adjustment != 0:
                            msg += f"  🛡️ 하락보호: {protection_level} 수준\n"
                            msg += f"  📉 보호효과: 손절선 {protection_adjustment*100:+.1f}%p 조정\n"
                            
                            if protection_level in ['downtrend', 'strong_downtrend']:
                                msg += f"  🔄 하락장 추가완화: -2.0%p 적용\n"
                        
                        # 🔥 쿨다운 안내
                        cooldown_hours = execution_options.get('cooldown_after_stop', 24)
                        msg += f"  ⏰ 재매수 쿨다운: {cooldown_hours}시간\n"
                        msg += f"  🔄 다음 사이클에서 새로운 1차 시작 가능\n"
                        
                        # 🚨 하락 보호 안내
                        if protection_adjustment != 0:
                            msg += f"  🛡️ 하락 보호 시스템이 적용된 손절입니다"
                        
                        logger.error(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        # 🔥 손절 후 특별 쿨다운 설정
                        if not hasattr(self, 'last_sell_time'):
                            self.last_sell_time = {}
                        if not hasattr(self, 'last_sell_info'):
                            self.last_sell_info = {}
                        
                        self.last_sell_time[stock_code] = datetime.now()
                        self.last_sell_info[stock_code] = {
                            'amount': total_stop_amount,
                            'price': current_price,
                            'timestamp': datetime.now(),
                            'type': 'stop_loss',
                            'protection_level': protection_level,
                            'protection_applied': protection_adjustment != 0
                        }
                        
                        return True  # 손절 실행됨
                
                except Exception as stop_e:
                    # 🔥 손절 실행 중 오류 발생시 롤백
                    logger.error(f"❌ {stock_name} 손절 실행 중 오류: {str(stop_e)}")
                    
                    if execution_options.get('data_backup_before_stop', True) and 'backup_data' in locals():
                        try:
                            # 백업 데이터로 롤백
                            for i, backup_magic in enumerate(backup_data['magic_data_list']):
                                if i < len(magic_data_list):
                                    magic_data_list[i].update(backup_magic)
                            
                            self.save_split_data()
                            logger.warning(f"🔄 {stock_name} 손절 실패 롤백 완료")
                            
                            # 롤백 알림 (하락 보호 정보 포함)
                            if config.config.get("use_discord_alert", True):
                                rollback_msg = f"⚠️ {stock_name} 손절 실패 롤백\n"
                                rollback_msg += f"손절 시도했으나 오류 발생\n"
                                rollback_msg += f"데이터 자동 복구 완료\n"
                                if protection_adjustment != 0:
                                    rollback_msg += f"보호수준: {protection_level}\n"
                                rollback_msg += f"오류: {str(stop_e)}"
                                discord_alert.SendMessage(rollback_msg)
                        
                        except Exception as rollback_e:
                            logger.error(f"💥 {stock_name} 롤백도 실패: {str(rollback_e)}")
                    
                    return False
            
            else:
                # 손절선 미도달 - 현재 상태 로깅 (하락 보호 정보 포함)
                buffer = total_return_pct - stop_threshold_pct
                debug_msg = f"💎 {stock_name} 손절선 여유: {total_return_pct:.1f}% (손절선: {stop_threshold_pct:.1f}%, 여유: {buffer:+.1f}%p)"
                
                if protection_adjustment != 0:
                    debug_msg += f" [보호: {protection_level}]"
                
                logger.debug(debug_msg)
                return False
                
        except Exception as e:
            logger.error(f"하락보호 통합 적응형 손절 실행 중 오류: {str(e)}")
            return False
            
    def check_enhanced_cooldown(self, stock_code):
        """🔥 강화된 쿨다운 시스템 - 매도 후 즉시 재매수 100% 차단"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥🔥🔥 최우선: 즉시 쿨다운 체크 (절대 우선순위) 🔥🔥🔥
            if hasattr(self, 'last_sell_time') and stock_code in self.last_sell_time:
                last_sell = self.last_sell_time[stock_code]
                seconds_passed = (datetime.now() - last_sell).total_seconds()
                
                # 매도 정보 확인
                sell_info = getattr(self, 'last_sell_info', {}).get(stock_code, {})
                sell_type = sell_info.get('type', 'unknown')
                sell_amount = sell_info.get('amount', 0)
                
                # 매도 타입별 강제 쿨다운
                if sell_type == 'stop_loss':
                    required_cooldown = 86400  # 손절: 24시간
                    cooldown_desc = "손절 후 24시간"
                else:  # profit_taking
                    required_cooldown = 21600   # 수익확정: 6시간
                    cooldown_desc = "수익확정 후 6시간"
                
                if seconds_passed < required_cooldown:
                    hours_remaining = (required_cooldown - seconds_passed) / 3600
                    logger.info(f"🚫 {stock_name} 강제 쿨다운 중")
                    logger.info(f"   📊 매도정보: {sell_amount}주 {sell_type}")
                    logger.info(f"   ⏰ 경과시간: {seconds_passed/3600:.1f}시간 / {required_cooldown/3600:.0f}시간")
                    logger.info(f"   ⏳ 남은시간: {hours_remaining:.1f}시간")
                    logger.info(f"   🎯 {cooldown_desc} 강제 적용")
                    return False
                else:
                    # 쿨다운 완료시 정리
                    del self.last_sell_time[stock_code]
                    if hasattr(self, 'last_sell_info') and stock_code in self.last_sell_info:
                        del self.last_sell_info[stock_code]
                    logger.info(f"✅ {stock_name} 강제 쿨다운 완료: {seconds_passed/3600:.1f}시간 경과")
            
            # 🔥 기존 적응형 쿨다운 로직 (보조적 역할)
            return self.check_adaptive_cooldown(stock_code)
            
        except Exception as e:
            logger.error(f"강화된 쿨다운 체크 오류: {str(e)}")
            return False  # 오류 시 매수 차단        

################################### 수익확정 로직 개선 ##################################

    def check_quick_profit_opportunity(self, stock_code, magic_data, current_price, stock_config):
        """빠른 수익 확정 기회 체크 - 🚀 즉시 개선"""
        try:
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
            
            if current_amount <= 0:
                return False, ""
            
            # 수익률 계산
            current_return = (current_price - entry_price) / entry_price * 100
            
            # 빠른 확정 목표 가져오기
            quick_target = stock_config.get('quick_profit_target', 4)  # 기본 4%
            
            # 빠른 확정 조건 체크
            if current_return >= quick_target:
                logger.info(f"💰 {stock_code} 빠른 수익 확정 기회 발견!")
                logger.info(f"   현재 수익률: {current_return:.2f}% ≥ 빠른확정목표: {quick_target}%")
                return True, f"빠른수익확정({current_return:.1f}%≥{quick_target}%)"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"빠른 수익 확정 체크 오류: {str(e)}")
            return False, ""

    def check_safety_protection(self, stock_code, magic_data, current_price, stock_config, max_profit_achieved):
        """안전장치 보호선 체크 - 🛡️ 즉시 개선"""
        try:
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
            
            if current_amount <= 0 or max_profit_achieved <= 0:
                return False, ""
            
            # 현재 수익률
            current_return = (current_price - entry_price) / entry_price * 100
            
            # 목표 수익률과 보호 비율
            target_profit = stock_config.get('hold_profit_target', 6)
            protection_ratio = stock_config.get('safety_protection_ratio', 0.95)
            
            # 안전 보호선 계산
            safety_line = target_profit * protection_ratio
            
            # 최고점 달성 후 보호선 이하로 떨어졌는지 체크
            if max_profit_achieved >= target_profit and current_return <= safety_line:
                logger.warning(f"🛡️ {stock_code} 안전장치 발동!")
                logger.warning(f"   최고점: {max_profit_achieved:.2f}% → 현재: {current_return:.2f}%")
                logger.warning(f"   보호선: {safety_line:.2f}% (목표 {target_profit}%의 {protection_ratio:.0%})")
                return True, f"안전장치매도(최고{max_profit_achieved:.1f}%→보호선{safety_line:.1f}%)"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"안전장치 체크 오류: {str(e)}")
            return False, ""

    def check_time_based_sell(self, stock_code, magic_data, current_price, stock_config):
        """시간 기반 매도 체크 - ⏰ 즉시 개선"""
        try:
            entry_date_str = magic_data.get('EntryDate', '')
            if not entry_date_str:
                return False, ""
            
            # 진입 날짜 계산
            try:
                entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
                days_held = (datetime.now() - entry_date).days
            except:
                return False, ""
            
            entry_price = magic_data['EntryPrice']
            current_return = (current_price - entry_price) / entry_price * 100
            
            # 설정값 가져오기
            time_threshold_days = stock_config.get('time_based_sell_days', 45)
            time_threshold_return = stock_config.get('time_based_sell_threshold', 3)
            
            # 시간 기반 매도 조건
            if days_held >= time_threshold_days and current_return >= time_threshold_return:
                logger.info(f"⏰ {stock_code} 시간 기반 매도 조건 충족!")
                logger.info(f"   보유기간: {days_held}일 ≥ {time_threshold_days}일")
                logger.info(f"   수익률: {current_return:.2f}% ≥ {time_threshold_return}%")
                return True, f"시간기반매도({days_held}일보유,{current_return:.1f}%수익)"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"시간 기반 매도 체크 오류: {str(e)}")
            return False, ""

################################### 🔥 적응형 쿨다운 시스템 ##################################

    def check_adaptive_cooldown(self, stock_code):
        """🔥 개선된 적응형 쿨다운 시스템 - 즉시 쿨다운 + 기존 로직 통합"""
        try:
            # 🔥 0단계: 즉시 쿨다운 체크 (최최우선) - 타이밍 갭 해결
            if hasattr(self, 'last_sell_time') and stock_code in self.last_sell_time:
                last_sell = self.last_sell_time[stock_code]
                hours_passed = (datetime.now() - last_sell).total_seconds() / 3600
                
                # 매도 정보 확인
                sell_info = getattr(self, 'last_sell_info', {}).get(stock_code, {})
                sell_type = sell_info.get('type', 'profit_taking')
                sell_amount = sell_info.get('amount', 0)
                
                # 매도 타입별 기본 쿨다운
                if sell_type == 'stop_loss':
                    base_cooldown_hours = 24  # 손절: 24시간
                else:  # profit_taking
                    base_cooldown_hours = 6   # 수익확정: 6시간
                
                if hours_passed < base_cooldown_hours:
                    logger.info(f"🚫 {stock_code} 즉시 쿨다운: {hours_passed:.1f}h/{base_cooldown_hours}h")
                    logger.info(f"   매도정보: {sell_amount}주 {sell_type} (타이밍갭 해결)")
                    return False
                else:
                    # 쿨다운 완료시 정리
                    del self.last_sell_time[stock_code]
                    if hasattr(self, 'last_sell_info') and stock_code in self.last_sell_info:
                        del self.last_sell_info[stock_code]
                    logger.info(f"✅ {stock_code} 즉시 쿨다운 완료: {hours_passed:.1f}h 경과")
            
            # 🚨 1단계: 손절 후 특별 쿨다운 체크 (기존 로직 유지)
            if hasattr(self, 'last_sell_time') and stock_code in self.last_sell_time:
                last_sell = self.last_sell_time[stock_code]
                
                # 손절 관련 설정 로드
                stop_config = config.config.get('enhanced_stop_loss', {})
                execution_options = stop_config.get('execution_options', {})
                cooldown_hours = execution_options.get('cooldown_after_stop', 24)
                
                hours_passed = (datetime.now() - last_sell).total_seconds() / 3600
                
                if hours_passed < cooldown_hours:
                    logger.info(f"🚫 {stock_code} 손절 후 특별 쿨다운: {hours_passed:.1f}h/{cooldown_hours}h")
                    return False
                else:
                    logger.info(f"✅ {stock_code} 손절 후 쿨다운 완료: {hours_passed:.1f}h 경과")
            
            # 🔥 2단계: 기존 적응형 쿨다운 시스템 (SellHistory 기반)
            
            # 해당 종목의 최근 매도 이력 확인
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return True  # 데이터 없으면 매수 허용
            
            # 종목 설정 로드
            target_stocks = config.target_stocks
            stock_config = target_stocks.get(stock_code, {})
            
            # 최근 매도 이력 확인
            latest_sell_time = None
            latest_sell_type = None
            latest_sell_return = 0
            latest_sell_reason = ""
            
            for magic_data in stock_data_info['MagicDataList']:
                for sell_record in magic_data.get('SellHistory', []):
                    try:
                        sell_date = datetime.strptime(sell_record.get('date', ''), "%Y-%m-%d")
                        
                        # 최근 3일 내 매도만 체크
                        if (datetime.now() - sell_date).days <= 3:
                            if latest_sell_time is None or sell_date > latest_sell_time:
                                latest_sell_time = sell_date
                                return_pct = sell_record.get('return_pct', 0)
                                latest_sell_return = return_pct
                                latest_sell_type = 'loss' if return_pct < 0 else 'profit'
                                latest_sell_reason = sell_record.get('reason', '')
                    except:
                        continue
            
            # 최근 매도 이력이 없으면 매수 허용
            if latest_sell_time is None:
                return True
            
            # 🔥🔥🔥 핵심 개선: 적응형 쿨다운 계산 🔥🔥🔥
            hours_passed = (datetime.now() - latest_sell_time).total_seconds() / 3600
            
            # 1단계: 기본 쿨다운 계산 (수익률별 차등)
            base_cooldown_hours = stock_config.get('reentry_cooldown_base_hours', 6)
            
            if latest_sell_type == 'profit':
                if latest_sell_return >= 20:
                    base_cooldown = base_cooldown_hours * 2.0    # 20% 이상 대박: 2배
                elif latest_sell_return >= 15:
                    base_cooldown = base_cooldown_hours * 1.8    # 15% 이상 큰 수익: 1.8배
                elif latest_sell_return >= 10:
                    base_cooldown = base_cooldown_hours * 1.5    # 10% 이상 목표 달성: 1.5배
                elif latest_sell_return >= 5:
                    base_cooldown = base_cooldown_hours * 1.2    # 5% 이상 소액: 1.2배
                else:
                    base_cooldown = base_cooldown_hours * 1.0    # 5% 미만 손익분기: 기본
            else:
                # 손절의 경우 - 특별 처리
                if '적응형손절' in latest_sell_reason or '손절' in latest_sell_reason:
                    # 이미 위에서 손절 후 특별 쿨다운으로 처리됨
                    base_cooldown = base_cooldown_hours * 0.6    # 일반 손실보다 짧게
                else:
                    base_cooldown = base_cooldown_hours * 0.8    # 일반 손실: 80%
            
            # 2단계: 변동성 기반 조정
            volatility_multiplier = stock_config.get('volatility_cooldown_multiplier', 0.7)
            try:
                # 종목별 변동성 확인
                df = Common.GetOhlcv("KR", stock_code, 30)
                if df is not None and len(df) >= 20:
                    volatility = df['close'].pct_change().std() * 100
                    
                    if volatility > 6.0:        # 고변동성 (한화오션 등)
                        vol_multiplier = volatility_multiplier   # 설정값 적용
                        volatility_desc = "고변동성"
                    elif volatility > 3.5:      # 중변동성
                        vol_multiplier = 0.8     # 20% 단축
                        volatility_desc = "중변동성"
                    else:                       # 저변동성 (삼성전자 등)
                        vol_multiplier = 0.9     # 10% 단축
                        volatility_desc = "저변동성"
                else:
                    vol_multiplier = 0.8
                    volatility_desc = "데이터부족"
            except:
                vol_multiplier = 0.8
                volatility_desc = "계산실패"
            
            # 3단계: 시장 상황 기반 조정 (설정에서 활성화된 경우만)
            market_multiplier = 1.0
            market_desc = "시장조정없음"
            
            if stock_config.get('market_cooldown_adjustment', True):
                market_timing = self.detect_market_timing()
                if market_timing in ["strong_downtrend", "downtrend"]:
                    market_multiplier = 0.6     # 하락장에서는 40% 단축 (기회!)
                    market_desc = "하락장 기회"
                elif market_timing in ["strong_uptrend", "uptrend"]:
                    market_multiplier = 1.1     # 상승장에서는 10% 연장
                    market_desc = "상승장 신중"
                else:
                    market_multiplier = 0.9     # 중립에서는 10% 단축
                    market_desc = "중립"
            
            # 4단계: 종목 타입별 조정
            stock_type = stock_config.get('stock_type', 'growth')
            if stock_type == 'growth':
                type_multiplier = 0.8     # 성장주는 20% 단축
                type_desc = "성장주"
            elif stock_type == 'value':
                type_multiplier = 1.2     # 가치주는 20% 연장
                type_desc = "가치주"
            else:
                type_multiplier = 1.0
                type_desc = "일반주"
            
            # 최종 쿨다운 계산
            final_cooldown = base_cooldown * vol_multiplier * market_multiplier * type_multiplier
            final_cooldown = max(1, min(final_cooldown, 48))  # 최소 1시간, 최대 48시간
            
            # 🔥 결과 판단 및 로깅
            if hours_passed < final_cooldown:
                logger.info(f"🕐 {stock_code} 기존 쿨다운: {hours_passed:.1f}h/{final_cooldown:.1f}h")
                logger.info(f"   📊 매도정보: {latest_sell_type} {latest_sell_return:+.1f}%")
                logger.info(f"   🔧 조정요소: {volatility_desc} × {market_desc} × {type_desc}")
                
                # 상세 계산 과정 로깅 (디버깅용)
                logger.debug(f"   📋 쿨다운 계산: 기본{base_cooldown:.1f}h × 변동성{vol_multiplier:.1f} × 시장{market_multiplier:.1f} × 타입{type_multiplier:.1f}")
                
                return False
            else:
                logger.info(f"✅ {stock_code} 기존 쿨다운 완료: {hours_passed:.1f}h 경과")
                logger.info(f"   🎯 최종 쿨다운: {final_cooldown:.1f}h")
                logger.info(f"   📈 단축효과: {(1-final_cooldown/base_cooldown)*100:.0f}% (기본 대비)")
                
                # 🔥 쿨다운 완료 시 추가 안전 체크
                
                # 당일 매수 횟수 체크
                today = datetime.now().strftime("%Y-%m-%d")
                daily_buy_count = 0
                
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data.get('EntryDate') == today:
                        daily_buy_count += 1
                
                # 종목별 일일 한도 체크
                enhanced_buy_control = config.config.get('enhanced_buy_control', {})
                max_daily_buys = enhanced_buy_control.get('max_daily_buys_per_stock', 2)
                
                if daily_buy_count >= max_daily_buys:
                    logger.info(f"🚫 {stock_code} 일일 매수 한도 도달: {daily_buy_count}/{max_daily_buys}")
                    return False
                
                return True
                    
        except Exception as e:
            logger.error(f"적응형 쿨다운 체크 오류: {str(e)}")
            return True  # 오류 시 매수 허용
            
        # 🔥 최종 안전장치: 모든 조건 통과
        return True

################################### 🔥 순차 진입 검증 시스템 ##################################

    def check_sequential_entry_validation(self, stock_code, position_num, indicators):
        """🔥 순차 진입 검증 시스템 - 이전 차수 보유 + 동적 하락률 필수 확인"""
        try:
            enhanced_control = config.enhanced_buy_control
            if not enhanced_control.get("enable_sequential_validation", True):
                return True, "순차 검증 비활성화"
            
            # 1차수는 검증 제외 (초기 진입)
            if position_num == 1:
                return True, "1차수는 검증 제외"
            
            # 해당 종목 데이터 찾기
            stock_data_info = None
            for data_info in self.split_data_list:
                if data_info['StockCode'] == stock_code:
                    stock_data_info = data_info
                    break
            
            if not stock_data_info:
                return False, "종목 데이터 없음"
            
            magic_data_list = stock_data_info['MagicDataList']
            
            # 🔥 핵심 1: 직전 차수 보유 확인 (순차적 진입 강제)
            prev_position_index = position_num - 2  # 0-based index
            
            if prev_position_index < 0 or prev_position_index >= len(magic_data_list):
                return False, f"{position_num-1}차 데이터 없음"
            
            prev_magic_data = magic_data_list[prev_position_index]
            
            # 직전 차수가 보유 상태인지 확인
            if not (prev_magic_data.get('IsBuy', False) and prev_magic_data.get('CurrentAmt', 0) > 0):
                logger.info(f"🚫 {stock_code} {position_num}차 순차 검증 실패: {position_num-1}차 미보유")
                logger.info(f"   {position_num-1}차 상태: IsBuy={prev_magic_data.get('IsBuy', False)}, 수량={prev_magic_data.get('CurrentAmt', 0)}")
                
                # 순차 검증 차단 횟수 증가
                config.update_enhanced_metrics("sequential_blocked_buys", 1)
                
                return False, f"{position_num-1}차 미보유로 순차 진입 차단"
            
            # 🔥 핵심 2: 동적 하락률 검증
            prev_entry_price = prev_magic_data.get('EntryPrice', 0)
            current_price = indicators.get('current_price', 0)
            
            if prev_entry_price <= 0 or current_price <= 0:
                return False, f"{position_num-1}차 매수가 또는 현재가 정보 없음"
            
            # 실제 하락률 계산
            actual_drop_rate = (prev_entry_price - current_price) / prev_entry_price
            
            # 🔥 동적 하락률 요구사항 계산
            required_drop_rate, adjustment_details = self.calculate_dynamic_drop_requirement(
                position_num, indicators, stock_code
            )
            
            # 하락률 조건 검증
            if actual_drop_rate < required_drop_rate:
                logger.info(f"🚫 {stock_code} {position_num}차 하락률 검증 실패:")
                logger.info(f"   📊 {position_num-1}차 매수가: {prev_entry_price:,.0f}원")
                logger.info(f"   📊 현재가: {current_price:,.0f}원")
                logger.info(f"   📉 실제하락률: {actual_drop_rate*100:.2f}%")
                logger.info(f"   📉 필요하락률: {required_drop_rate*100:.2f}%")
                if adjustment_details:
                    logger.info(f"   🎯 조정내역: {', '.join(adjustment_details)}")
                
                config.update_enhanced_metrics("sequential_blocked_buys", 1)
                
                return False, f"하락률 부족 ({actual_drop_rate*100:.2f}% < {required_drop_rate*100:.2f}%)"
            
            # 🔥 모든 검증 통과
            logger.info(f"✅ {stock_code} {position_num}차 순차 진입 검증 통과:")
            logger.info(f"   🔗 {position_num-1}차 보유: {prev_magic_data.get('CurrentAmt', 0)}주 @ {prev_entry_price:,.0f}원")
            logger.info(f"   📉 하락률: {actual_drop_rate*100:.2f}% ≥ {required_drop_rate*100:.2f}% (필요)")
            if adjustment_details:
                logger.info(f"   🎯 동적조정: {', '.join(adjustment_details)}")
            
            return True, f"순차 검증 통과 (하락률 {actual_drop_rate*100:.2f}%)"
            
        except Exception as e:
            logger.error(f"순차 진입 검증 중 오류: {str(e)}")
            return False, f"검증 오류: {str(e)}"

    def calculate_dynamic_drop_requirement(self, position_num, indicators, stock_code):
        """🔥 동적 하락률 요구사항 계산 - 시장 상황과 기술적 조건 반영"""
        try:
            # 기본 하락률 가져오기
            drop_config = config.config.get("dynamic_drop_requirements", {})
            base_drops = drop_config.get("base_drops", {})
            adjustment_factors = drop_config.get("adjustment_factors", {})
            
            # 기본 하락률 (차수별)
            base_drop = base_drops.get(str(position_num), 0.06)
            adjustment_details = []
            final_drop = base_drop
            
            if not drop_config.get("enable", True):
                return base_drop, ["동적 조정 비활성화"]
            
            # 🔥 RSI 기반 조정
            rsi = indicators.get('rsi', 50)
            if rsi <= 25:  # 극한 과매도
                rsi_adjustment = adjustment_factors.get("rsi_oversold_bonus", -0.01)
                final_drop += rsi_adjustment
                adjustment_details.append(f"극한과매도RSI({rsi:.1f}) {rsi_adjustment*100:+.1f}%p")
            elif rsi >= 75:  # 과매수
                rsi_adjustment = adjustment_factors.get("rsi_overbought_penalty", 0.01)
                final_drop += rsi_adjustment
                adjustment_details.append(f"과매수RSI({rsi:.1f}) {rsi_adjustment*100:+.1f}%p")
            
            # 🔥 시장 상황 기반 조정
            # market_timing = self.detect_market_timing()
            market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())

            if market_timing in ["strong_downtrend", "downtrend"]:
                market_adjustment = adjustment_factors.get("market_downtrend_bonus", -0.015)
                final_drop += market_adjustment
                adjustment_details.append(f"하락장({market_timing}) {market_adjustment*100:+.1f}%p")
            elif market_timing in ["strong_uptrend", "uptrend"]:
                market_adjustment = adjustment_factors.get("market_uptrend_penalty", 0.01)
                final_drop += market_adjustment
                adjustment_details.append(f"상승장({market_timing}) {market_adjustment*100:+.1f}%p")
            
            # 🔥 변동성 기반 조정 (한국주식 특화)
            try:
                df = Common.GetOhlcv("KR", stock_code, 20)
                if df is not None and len(df) >= 15:
                    volatility = df['close'].pct_change().std() * 100
                    if volatility > 5.0:  # 한국주식 고변동성
                        vol_adjustment = adjustment_factors.get("volatility_bonus", -0.005)
                        final_drop += vol_adjustment
                        adjustment_details.append(f"고변동성({volatility:.1f}%) {vol_adjustment*100:+.1f}%p")
            except:
                pass
            
            # 🔥 안전 범위 제한 (기본값의 50% ~ 150% 사이)
            min_drop = base_drop * 0.5
            max_drop = base_drop * 1.5
            final_drop = max(min_drop, min(final_drop, max_drop))
            
            # 기본값과 다른 경우만 조정 로깅
            if abs(final_drop - base_drop) > 0.001:
                adjustment_details.insert(0, f"기본{base_drop*100:.1f}%→최종{final_drop*100:.1f}%")
            
            return final_drop, adjustment_details
            
        except Exception as e:
            logger.error(f"동적 하락률 계산 오류: {str(e)}")
            return 0.06, [f"계산 오류: 기본 6% 사용"]

################################### 🔥 개선된 매수 주문 처리 시스템 ##################################

    def handle_buy_with_execution_tracking(self, stock_code, amount, price):
        """🔥 하락 보호가 통합된 매수 주문 처리 - 한국주식용 체결량 정확 계산"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🚨🚨🚨 최우선: 하락 보호 시스템 최종 체크 🚨🚨🚨
            
            # 🚨 1. 전체 매수 중단 재확인 (주문 직전 체크)
            if getattr(self, 'suspend_all_buys', False):
                logger.error(f"🚫 {stock_name} 매수 중단: 크래시 수준 하락 보호 활성화")
                return None, None, "크래시 수준 하락 보호로 매수 중단"
            
            # 🚨 2. 베어마켓 모드 재확인
            if getattr(self, 'bear_market_mode', False):
                logger.error(f"🐻 {stock_name} 매수 중단: 베어마켓 모드 활성화")
                return None, None, "베어마켓 모드로 매수 중단"
            
            # 🚨 3. 매수량 조정 적용 (하락 보호)
            position_multiplier = getattr(self, 'position_size_multiplier', 1.0)
            protection_level = getattr(self, 'current_protection_level', 'normal')
            
            if position_multiplier < 1.0:
                original_amount = amount
                adjusted_amount = max(1, int(amount * position_multiplier))
                
                logger.warning(f"🛡️ {stock_name} 하락 보호 매수량 조정:")
                logger.warning(f"   보호 수준: {protection_level}")
                logger.warning(f"   원래 수량: {original_amount:,}주")
                logger.warning(f"   조정 수량: {adjusted_amount:,}주 ({position_multiplier*100:.0f}%)")
                logger.warning(f"   축소 효과: {original_amount - adjusted_amount:,}주 절약")
                
                amount = adjusted_amount
                
                # 하락 보호 매수량 조정 Discord 알림
                if config.config.get("use_discord_alert", True):
                    protection_msg = f"🛡️ **하락 보호 매수량 조정**\n"
                    protection_msg += f"종목: {stock_name}\n"
                    protection_msg += f"보호 수준: {protection_level}\n"
                    protection_msg += f"원래 수량: {original_amount:,}주\n"
                    protection_msg += f"조정 수량: {adjusted_amount:,}주 ({position_multiplier*100:.0f}%)\n"
                    protection_msg += f"리스크 감소: {original_amount - adjusted_amount:,}주"
                    discord_alert.SendMessage(protection_msg)
            
            # 🔥🔥🔥 기존 매수 로직 (기존 코드 + 개선사항) 🔥🔥🔥
            
            # 🔥 1. 매수 전 보유량 기록 (핵심 추가)
            before_holdings = self.get_current_holdings(stock_code)
            before_amount = before_holdings.get('amount', 0)
            before_avg_price = before_holdings.get('avg_price', 0)
            
            logger.info(f"📊 {stock_name} 매수 전 현황:")
            logger.info(f"   보유량: {before_amount:,}주")
            if before_avg_price > 0:
                logger.info(f"   평균가: {before_avg_price:,.0f}원")
            
            # 🚨 하락 보호 상태 표시
            if protection_level != 'normal':
                logger.info(f"   🛡️ 하락 보호: {protection_level} 수준")
            if position_multiplier < 1.0:
                logger.info(f"   📉 매수량 조정: {position_multiplier*100:.0f}% 적용")
            
            # 🔥 2. 현재가 재조회 및 검증
            old_price = price
            try:
                current_price = KisKR.GetCurrentPrice(stock_code)
                if current_price and current_price > 0:
                    actual_price = current_price
                    price_diff = actual_price - old_price
                    price_change_rate = abs(price_diff) / old_price
                    
                    logger.info(f"💰 {stock_name} 매수 전 현재가 재조회:")
                    logger.info(f"   분석시 가격: {old_price:,.0f}원")
                    logger.info(f"   현재 가격: {actual_price:,.0f}원")
                    logger.info(f"   가격 변화: {price_diff:+,.0f}원 ({price_change_rate*100:+.2f}%)")
                    
                    # 🔥 가격 급등 보호 (한국주식 특화: 3% 이상 급등시 매수 포기)
                    # 🚨 하락 보호 상태에서는 5%까지 허용 (기회 확대)
                    price_limit = 0.05 if protection_level in ['downtrend', 'strong_downtrend'] else 0.03
                    
                    if price_diff > 0 and price_change_rate > price_limit:
                        logger.warning(f"💔 {stock_name} 과도한 가격 급등으로 매수 포기")
                        logger.warning(f"   허용 한도: {price_limit*100:.0f}% (보호수준: {protection_level})")
                        return None, None, f"가격 급등으로 매수 포기 ({price_change_rate*100:.1f}% > {price_limit*100:.0f}%)"
                    elif protection_level in ['downtrend', 'strong_downtrend'] and price_change_rate > 0.03:
                        logger.info(f"🛡️ {stock_name} 하락장 가격 급등 허용: {price_change_rate*100:.1f}%")
                else:
                    actual_price = old_price
                    logger.warning(f"⚠️ {stock_name} 현재가 조회 실패, 분석시 가격 사용")
                    
            except Exception as price_error:
                actual_price = old_price
                logger.error(f"❌ {stock_name} 현재가 조회 중 오류: {str(price_error)}")
            
            # 🔥 3. 미체결 주문 추적 초기화
            if not hasattr(self, 'pending_orders'):
                self.pending_orders = {}
            
            # 중복 주문 방지 (같은 종목 10분 내 주문 방지)
            # 🚨 하락 보호 상태에서는 5분으로 단축 (기회 확대)
            cooldown_minutes = 5 if protection_level in ['downtrend', 'strong_downtrend'] else 10
            
            if stock_code in self.pending_orders:
                pending_info = self.pending_orders[stock_code]
                order_time_str = pending_info.get('order_time', '')
                try:
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                    
                    if elapsed_minutes < cooldown_minutes:
                        logger.warning(f"❌ {stock_name} 중복 주문 방지: {elapsed_minutes:.1f}분 전 주문 있음 (한도: {cooldown_minutes}분)")
                        return None, None, f"중복 주문 방지 ({elapsed_minutes:.1f}분/{cooldown_minutes}분)"
                except:
                    pass
            
            # 🔥 4. 주문 정보 기록 (하락 보호 정보 포함)
            order_info = {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'order_amount': amount,
                'original_amount': amount / position_multiplier if position_multiplier < 1.0 else amount,
                'before_amount': before_amount,
                'analysis_price': old_price,
                'order_price': actual_price,
                'price_change': actual_price - old_price,
                'protection_level': protection_level,
                'position_multiplier': position_multiplier,
                'status': 'submitted'
            }
            
            self.pending_orders[stock_code] = order_info
            
            # 🔥 5. 주문 전송 (한국주식: 1% 위로 지정가)
            estimated_fee = self.calculate_trading_fee(actual_price, amount, True)
            order_price = int(actual_price * 1.01)  # 한국주식은 정수 단위
            
            logger.info(f"🔵 {stock_name} 매수 주문 전송:")
            logger.info(f"   수량: {amount:,}주")
            if position_multiplier < 1.0:
                logger.info(f"   (원래: {int(amount/position_multiplier):,}주 → 하락보호 조정)")
            logger.info(f"   주문가격: {order_price:,}원 (현재가 +1%)")
            logger.info(f"   예상 수수료: {estimated_fee:,.0f}원")
            if protection_level != 'normal':
                logger.info(f"   🛡️ 보호 수준: {protection_level}")
            
            # 🔥 한국주식 매수 주문 실행
            order_result = KisKR.MakeBuyLimitOrder(stock_code, amount, order_price)
            
            if not order_result or isinstance(order_result, str):
                # 주문 실패시 pending 제거
                if stock_code in self.pending_orders:
                    del self.pending_orders[stock_code]
                
                error_msg = f"❌ {stock_name} 매수 주문 실패: {order_result}"
                logger.error(error_msg)
                return None, None, error_msg
            
            # 🔥 6. 주문 성공시 처리
            logger.info(f"✅ {stock_name} 매수 주문 성공 - 체결 확인 시작")
            
            # 🔥 7. 개선된 체결 확인 (한국주식 특화: 최대 90초)
            logger.info(f"⏳ {stock_name} 체결 확인 (최대 90초)")
            start_time = time.time()
            check_count = 0
            
            while time.time() - start_time < 90:  # 한국주식은 90초로 연장
                check_count += 1
                time.sleep(3)  # 3초마다 체크 (한국주식 체결 속도 고려)
                
                # 한국주식 보유 종목 조회
                try:
                    my_stocks = KisKR.GetMyStockList()
                    current_total = 0
                    current_avg_price = actual_price
                    
                    for stock in my_stocks:
                        if stock['StockCode'] == stock_code:
                            current_total = int(stock.get('StockAmt', 0))
                            if stock.get('StockAvgPrice'):
                                current_avg_price = float(stock.get('StockAvgPrice', actual_price))
                            break
                    
                    # 🔥🔥🔥 핵심 수정: 증가분을 실제 체결량으로 계산 🔥🔥🔥
                    actual_executed = current_total - before_amount
                    
                    if actual_executed >= amount:  # 목표 수량 이상 체결
                        
                        # 🔥 체결 상세 정보 로깅 (하락 보호 정보 포함)
                        logger.info(f"✅ {stock_name} 매수 체결 완료!")
                        logger.info(f"   🎯 목표수량: {amount:,}주")
                        if position_multiplier < 1.0:
                            original_target = int(amount / position_multiplier)
                            logger.info(f"   🛡️ 원래목표: {original_target:,}주 (하락보호로 {original_target-amount:,}주 절약)")
                        logger.info(f"   📊 매수 전 보유: {before_amount:,}주")
                        logger.info(f"   📊 매수 후 총보유: {current_total:,}주")
                        logger.info(f"   ✅ 실제 체결량: {actual_executed:,}주")
                        logger.info(f"   💰 주문가격: {order_price:,}원")
                        logger.info(f"   💰 체결가격: {current_avg_price:,.0f}원")
                        if protection_level != 'normal':
                            logger.info(f"   🛡️ 보호수준: {protection_level}")
                        
                        # 가격 개선 계산
                        execution_diff = current_avg_price - order_price
                        total_investment = current_avg_price * actual_executed
                        actual_fee = self.calculate_trading_fee(current_avg_price, actual_executed, True)
                        
                        logger.info(f"   📊 가격개선: {execution_diff:+,.0f}원")
                        logger.info(f"   💵 투자금액: {total_investment:,.0f}원")
                        logger.info(f"   💸 실제수수료: {actual_fee:,.0f}원")
                        logger.info(f"   🕐 체결시간: {check_count * 3}초")
                        
                        # 🔥 하락 보호로 인한 리스크 감소 효과 계산
                        if position_multiplier < 1.0:
                            saved_amount = int(amount / position_multiplier) - amount
                            saved_investment = current_avg_price * saved_amount
                            logger.info(f"   🛡️ 하락보호 효과:")
                            logger.info(f"      절약 수량: {saved_amount:,}주")
                            logger.info(f"      절약 금액: {saved_investment:,.0f}원")
                            logger.info(f"      리스크 감소: {(1-position_multiplier)*100:.0f}%")
                        
                        # 체결 완료시 pending 제거
                        if stock_code in self.pending_orders:
                            del self.pending_orders[stock_code]
                        
                        # 🔥 체결 완료 Discord 알림 (하락 보호 정보 포함)
                        if config.config.get("use_discord_alert", True):
                            msg = f"✅ {stock_name} 매수 체결!\n"
                            msg += f"💰 {current_avg_price:,.0f}원 × {actual_executed:,}주\n"
                            msg += f"📊 투자금액: {total_investment:,.0f}원\n"
                            
                            if position_multiplier < 1.0:
                                saved_amount = int(amount / position_multiplier) - amount
                                saved_investment = current_avg_price * saved_amount
                                msg += f"🛡️ 하락보호: {saved_amount:,}주 절약 ({saved_investment:,.0f}원)\n"
                                msg += f"📉 보호수준: {protection_level}\n"
                            
                            if abs(execution_diff) > 100:
                                msg += f"🎯 가격개선: {execution_diff:+,.0f}원\n"
                            msg += f"⚡ 체결시간: {check_count * 3}초"
                            discord_alert.SendMessage(msg)
                        
                        # 🔥🔥🔥 핵심: 실제 체결량 반환 🔥🔥🔥
                        return current_avg_price, actual_executed, "체결 완료"
                
                except Exception as check_e:
                    logger.warning(f"   ⚠️ 체결 확인 중 오류: {str(check_e)}")
                
                # 진행 상황 로깅 (15초마다)
                if check_count % 5 == 0:
                    logger.info(f"   ⏳ 체결 대기 중... ({check_count * 3}초 경과)")
            
            # 🔥 8. 미체결시 처리
            logger.warning(f"⏰ {stock_name} 체결 시간 초과 (90초)")
            
            # 미체결 상태로 기록 유지
            if stock_code in self.pending_orders:
                self.pending_orders[stock_code]['status'] = 'pending'
                self.pending_orders[stock_code]['timeout_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 미체결 알림 (하락 보호 정보 포함)
            if config.config.get("use_discord_alert", True):
                msg = f"⏰ {stock_name} 매수 미체결\n"
                msg += f"💰 주문: {order_price:,}원 × {amount:,}주\n"
                if position_multiplier < 1.0:
                    msg += f"🛡️ 하락보호 적용: {protection_level}\n"
                msg += f"⚠️ 90초 내 체결되지 않음\n"
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
            
            logger.error(f"❌ {stock_name} 하락보호 통합 매수 주문 처리 중 오류: {str(e)}")
            return None, None, str(e)

    def check_and_manage_pending_orders(self):
        """🔥 미체결 주문 자동 관리 - 한국주식 특화"""
        try:
            if not hasattr(self, 'pending_orders') or not self.pending_orders:
                return
            
            logger.info("🔍 미체결 주문 자동 관리 시작")
            
            completed_orders = []
            expired_orders = []
            
            for stock_code, order_info in self.pending_orders.items():
                try:
                    stock_name = order_info.get('stock_name', stock_code)
                    order_time_str = order_info.get('order_time', '')
                    
                    if not order_time_str:
                        continue
                        
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                    
                    logger.info(f"📋 미체결 주문 체크: {stock_name} ({elapsed_minutes:.1f}분 경과)")
                    
                    # 🔥 1. 체결 여부 재확인
                    my_stocks = KisKR.GetMyStockList()
                    executed_amount = 0
                    avg_price = 0
                    before_amount = order_info.get('before_amount', 0)
                    target_amount = order_info.get('order_amount', 0)
                    
                    for stock in my_stocks:
                        if stock['StockCode'] == stock_code:
                            current_amount = int(stock.get('StockAmt', 0))
                            executed_amount = current_amount - before_amount  # 증가분이 체결량
                            if stock.get('StockAvgPrice'):
                                avg_price = float(stock.get('StockAvgPrice', 0))
                            break
                    
                    if executed_amount >= target_amount:
                        # 🎉 지연 체결 발견!
                        logger.info(f"✅ 지연 체결 발견: {stock_name} {executed_amount:,}주 @ {avg_price:,.0f}원")
                        
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
                            msg += f"💰 {avg_price:,.0f}원 × {executed_amount:,}주\n"
                            msg += f"⏰ 지연시간: {elapsed_minutes:.1f}분"
                            discord_alert.SendMessage(msg)
                        
                    elif elapsed_minutes > 20:  # 한국주식: 20분 이상 미체결시 만료
                        # 🗑️ 만료 처리
                        logger.warning(f"⏰ 미체결 주문 만료: {stock_name} ({elapsed_minutes:.1f}분)")
                        
                        expired_orders.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'elapsed_minutes': elapsed_minutes
                        })
                        
                    else:
                        # 🔄 계속 대기
                        logger.info(f"⏳ 계속 대기: {stock_name} ({elapsed_minutes:.1f}/20분)")
                    
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
            
            # 요약 로깅
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
        """매수 주문 처리 - 개선된 버전으로 리다이렉트"""
        success, executed_amount, message = self.handle_buy_with_execution_tracking(stock_code, amount, price)
        
        if success and executed_amount:
            return success, executed_amount
        else:
            return None, None

################################### 🔥 브로커 데이터 동기화 시스템 ##################################

    def sync_all_positions_with_broker(self):
        """🔥 전체 포지션 브로커 동기화 - 한국주식 특화"""
        try:
            logger.info("🔄 전체 포지션 브로커 동기화 시작")
            
            target_stocks = config.target_stocks
            sync_count = 0
            
            for stock_code in target_stocks.keys():
                try:
                    holdings = self.get_current_holdings(stock_code)
                    broker_amount = holdings.get('amount', 0)
                    broker_avg_price = holdings.get('avg_price', 0)
                    stock_name = target_stocks[stock_code].get('name', stock_code)
                    
                    # 해당 종목 데이터 찾기
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    if not stock_data_info:
                        continue
                    
                    # 🔥 내부 관리 수량 계산 (개선된 방식)
                    internal_total = 0
                    active_positions = []
                    
                    for magic_data in stock_data_info['MagicDataList']:
                        current_amt = magic_data.get('CurrentAmt', 0)
                        if current_amt > 0:  # IsBuy 조건 제거하고 수량만 체크
                            internal_total += current_amt
                            active_positions.append(magic_data)
                    
                    # 🔥 동기화 필요 여부 판단
                    needs_sync = False
                    sync_reason = ""
                    
                    # Case 1: 브로커에 보유가 있는데 내부에 없는 경우 (핵심 문제!)
                    if broker_amount > 0 and internal_total == 0:
                        needs_sync = True
                        sync_reason = f"브로커 보유({broker_amount:,}주) vs 내부 없음"
                        
                        # 🔥 첫 번째 포지션에 브로커 데이터 복원
                        first_pos = stock_data_info['MagicDataList'][0]
                        first_pos['CurrentAmt'] = broker_amount
                        first_pos['EntryPrice'] = broker_avg_price
                        first_pos['EntryAmt'] = broker_amount
                        first_pos['IsBuy'] = True  # 🔥 중요: IsBuy도 수정!
                        # 기존 보유는 30일 전 날짜로 설정 (쿨다운 회피)
                        first_pos['EntryDate'] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                        
                        logger.info(f"✅ {stock_name} 브로커 기준 복원:")
                        logger.info(f"   수량: 0 → {broker_amount:,}주")
                        logger.info(f"   평균단가: {broker_avg_price:,.0f}원")
                        logger.info(f"   IsBuy: false → true")
                        
                    # Case 2: 브로커에 없는데 내부에 있는 경우
                    elif broker_amount == 0 and internal_total > 0:
                        needs_sync = True
                        sync_reason = f"브로커 없음 vs 내부 보유({internal_total:,}주)"
                        
                        # 🔥 모든 포지션 정리
                        for magic_data in stock_data_info['MagicDataList']:
                            if magic_data['CurrentAmt'] > 0:
                                magic_data['CurrentAmt'] = 0
                                magic_data['IsBuy'] = False
                                # 최고점도 리셋
                                for key in list(magic_data.keys()):
                                    if key.startswith('max_profit_'):
                                        magic_data[key] = 0
                        
                        logger.info(f"✅ {stock_name} 내부 데이터 정리 (브로커 기준)")
                        
                    # Case 3: 수량은 맞는데 IsBuy 상태가 틀린 경우
                    elif broker_amount > 0 and internal_total == broker_amount:
                        # IsBuy 상태 검증
                        correct_positions = [
                            magic_data for magic_data in stock_data_info['MagicDataList']
                            if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0
                        ]
                        
                        if len(correct_positions) == 0:  # 수량은 맞는데 IsBuy=false인 경우
                            needs_sync = True
                            sync_reason = f"수량 일치({broker_amount:,}주) but IsBuy=false"
                            
                            # 보유량이 있는 포지션의 IsBuy를 true로 수정
                            for magic_data in stock_data_info['MagicDataList']:
                                if magic_data['CurrentAmt'] > 0:
                                    magic_data['IsBuy'] = True
                                    logger.info(f"✅ {stock_name} {magic_data['Number']}차 IsBuy: false → true")
                        
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
                                    
                                    logger.info(f"✅ {stock_name} {pos['Number']}차 평균단가 동기화:")
                                    logger.info(f"   {old_price:,.0f}원 → {broker_avg_price:,.0f}원")
                        
                    # Case 4: 수량 불일치
                    elif broker_amount != internal_total:
                        needs_sync = True
                        sync_reason = f"수량 불일치: 브로커 {broker_amount:,} vs 내부 {internal_total:,}"
                        
                        if len(active_positions) == 1:
                            # 단일 포지션: 직접 동기화
                            pos = active_positions[0]
                            old_amount = pos['CurrentAmt']
                            
                            pos['CurrentAmt'] = broker_amount
                            pos['EntryPrice'] = broker_avg_price
                            pos['IsBuy'] = broker_amount > 0
                            
                            logger.info(f"✅ {stock_name} {pos['Number']}차 수량 동기화:")
                            logger.info(f"   수량: {old_amount:,} → {broker_amount:,}주")
                            logger.info(f"   평균단가: {broker_avg_price:,.0f}원")
                            
                        else:
                            # 다중 포지션: 첫 번째에 통합
                            if active_positions:
                                first_pos = active_positions[0]
                                
                                # 나머지 포지션 정리
                                for pos in active_positions[1:]:
                                    pos['CurrentAmt'] = 0
                                    pos['IsBuy'] = False
                                
                                # 첫 번째 포지션에 통합
                                first_pos['CurrentAmt'] = broker_amount
                                first_pos['EntryPrice'] = broker_avg_price
                                first_pos['IsBuy'] = broker_amount > 0
                                
                                logger.info(f"✅ {stock_name} {first_pos['Number']}차에 통합:")
                                logger.info(f"   {broker_amount:,}주 @ {broker_avg_price:,.0f}원")
                    
                    if needs_sync:
                        sync_count += 1
                        logger.warning(f"⚠️ {stock_name} 동기화 실행: {sync_reason}")
                        
                        # 브로커 동기화 수정 횟수 증가
                        config.update_enhanced_metrics("broker_sync_corrections", 1)
                        
                except Exception as stock_e:
                    logger.error(f"종목 {stock_code} 동기화 중 오류: {str(stock_e)}")
            
            if sync_count > 0:
                self.save_split_data()
                logger.info(f"✅ 전체 포지션 동기화 완료: {sync_count}개 종목 수정")
                
                # 🔥 동기화 결과 Discord 알림
                if config.config.get("use_discord_alert", True):
                    sync_msg = f"🔄 **포지션 동기화 완료**\n"
                    sync_msg += f"수정된 종목: {sync_count}개\n"
                    sync_msg += f"브로커 기준으로 데이터 정정됨\n"
                    sync_msg += f"⚠️ 데이터 불일치 해결"
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

    def verify_after_trade(self, stock_code, trade_type, expected_change=None):
        """🔥 매매 후 데이터 검증 - 브로커와 내부 데이터 일치 확인"""
        try:
            # API 반영 대기
            time.sleep(2)
            
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
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
            
            internal_avg_price = total_investment / internal_amount if internal_amount > 0 else 0
            
            # 🔥 3. 수량 일치 확인
            quantity_match = (broker_amount == internal_amount)
            
            # 🔥 4. 평균가 일치 확인 (3% 오차 허용 - 한국주식 특화)
            price_match = True
            if broker_amount > 0 and internal_amount > 0:
                if broker_avg_price > 0 and internal_avg_price > 0:
                    price_diff_pct = abs(broker_avg_price - internal_avg_price) / broker_avg_price * 100
                    price_match = price_diff_pct <= 3.0  # 한국주식: 3% 오차 허용
            
            # 🔥 5. 결과 로깅
            if quantity_match and price_match:
                logger.info(f"✅ {stock_name} {trade_type} 후 데이터 일치 확인")
                logger.info(f"   수량: {broker_amount:,}주 (브로커 = 내부)")
                if broker_amount > 0:
                    logger.info(f"   평균가: 브로커 {broker_avg_price:,.0f}원 vs 내부 {internal_avg_price:,.0f}원")
                    if len(active_positions) > 1:
                        logger.info(f"   활성 포지션: {len(active_positions)}개")
                return True
                
            else:
                # 불일치 상세 로깅
                logger.warning(f"⚠️ {stock_name} {trade_type} 후 데이터 불일치 감지!")
                logger.warning(f"   수량 일치: {'✅' if quantity_match else '❌'} (브로커: {broker_amount:,}, 내부: {internal_amount:,})")
                
                if broker_amount > 0 and internal_amount > 0:
                    price_diff_pct = abs(broker_avg_price - internal_avg_price) / broker_avg_price * 100 if broker_avg_price > 0 else 0
                    logger.warning(f"   평균가 일치: {'✅' if price_match else '❌'} (차이: {price_diff_pct:.1f}%)")
                    logger.warning(f"     브로커 평균가: {broker_avg_price:,.0f}원")
                    logger.warning(f"     내부 평균가: {internal_avg_price:,.0f}원")
                
                # 활성 포지션 상세 정보
                if active_positions:
                    logger.warning(f"   내부 활성 포지션:")
                    for pos in active_positions:
                        logger.warning(f"     {pos['position']}차: {pos['amount']:,}주 @ {pos['price']:,.0f}원")
                
                # 🔥 불일치 시 Discord 알림
                if config.config.get("use_discord_alert", True):
                    mismatch_msg = f"⚠️ **데이터 불일치 감지**\n"
                    mismatch_msg += f"종목: {stock_name}\n"
                    mismatch_msg += f"거래: {trade_type}\n"
                    mismatch_msg += f"브로커: {broker_amount:,}주 @ {broker_avg_price:,.0f}원\n"
                    mismatch_msg += f"내부: {internal_amount:,}주 @ {internal_avg_price:,.0f}원\n"
                    mismatch_msg += f"🔄 다음 동기화에서 자동 수정"
                    discord_alert.SendMessage(mismatch_msg)
                
                return False
        
        except Exception as e:
            logger.error(f"❌ {stock_code} {trade_type} 후 검증 중 오류: {str(e)}")
            return False

    def periodic_sync_check(self):
        """주기적 브로커 데이터 동기화 체크 (30분마다 실행)"""
        try:
            current_time = datetime.now()
            
            # 마지막 동기화 시간 체크
            if not hasattr(self, 'last_full_sync_time'):
                self.last_full_sync_time = current_time
                logger.info("🔄 초기 브로커 데이터 동기화 실행")
                self.sync_all_positions_with_broker()
            else:
                time_diff_minutes = (current_time - self.last_full_sync_time).total_seconds() / 60
                sync_interval = config.enhanced_buy_control.get("sync_check_interval_minutes", 30)
                
                if time_diff_minutes >= sync_interval:
                    logger.info(f"🔄 정기 브로커 동기화 실행 ({time_diff_minutes:.0f}분 경과)")
                    self.sync_all_positions_with_broker()
                    self.last_full_sync_time = current_time
        
        except Exception as e:
            logger.error(f"주기적 동기화 체크 중 오류: {str(e)}")

################################### 🔥 데이터 안전성 강화 시스템 ##################################

    def save_split_data(self):
        """매매 데이터 저장 - 안전성 강화 버전"""
        try:
            bot_file_path = f"KrStock_{BOT_NAME}.json"
            
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
            
            logger.debug("✅ 안전한 데이터 저장 완료")
            
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

    def load_split_data(self):
        """저장된 매매 데이터 로드"""
        try:
            bot_file_path = f"KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'r', encoding='utf-8') as json_file:
                return json.load(json_file)
        except Exception:
            return []

    def _upgrade_json_structure_if_needed(self):
        """JSON 구조 업그레이드: 부분 매도를 지원하기 위한 필드 추가 - 개선된 버전"""
        is_modified = False
        
        for stock_data in self.split_data_list:
            for magic_data in stock_data['MagicDataList']:
                # CurrentAmt 필드 추가
                if 'CurrentAmt' not in magic_data and magic_data['IsBuy']:
                    magic_data['CurrentAmt'] = magic_data['EntryAmt']
                    is_modified = True
                
                # SellHistory 필드 추가 (개선된 구조)
                if 'SellHistory' not in magic_data:
                    magic_data['SellHistory'] = []
                    is_modified = True
                    
                # 🔥 EntryDate 필드 개선
                if 'EntryDate' not in magic_data:
                    if magic_data['IsBuy']:
                        # 🔥 기존 매수 데이터는 30일 전으로 설정 (쿨다운 회피)
                        magic_data['EntryDate'] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                        logger.info(f"기존 매수 데이터 발견: EntryDate를 30일 전으로 설정 (쿨다운 회피)")
                    else:
                        magic_data['EntryDate'] = ""
                    is_modified = True
                
                # 🔥 새로운 추적 필드들 추가
                if magic_data.get('SellHistory'):
                    for sell_record in magic_data['SellHistory']:
                        if 'return_pct' not in sell_record:
                            entry_price = magic_data.get('EntryPrice', 0)
                            sell_price = sell_record.get('price', entry_price)
                            if entry_price > 0:
                                sell_record['return_pct'] = (sell_price - entry_price) / entry_price * 100
                            else:
                                sell_record['return_pct'] = 0
                            is_modified = True
        
        if is_modified:
            logger.info("JSON 구조를 개선된 부분 매도 지원을 위해 업그레이드했습니다.")
            logger.info("🔥 기존 매수 데이터의 EntryDate는 30일 전으로 설정되어 쿨다운이 회피됩니다.")
            self.save_split_data()

################################### 🔥 기존 함수들 개선 ##################################

    def get_current_holdings(self, stock_code):
        """현재 보유 수량 및 상태 조회 - 한국주식용"""
        try:
            my_stocks = KisKR.GetMyStockList()
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
            logger.error(f"한국주식 보유 수량 조회 중 오류: {str(e)}")
            return {'amount': 0, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0}
        
    def handle_sell(self, stock_code, amount, price):
        """매도 주문 처리 - 🔥 강화된 쿨다운 설정 + 체결 확인 + 미체결 추적 포함"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥 1. 거래시간 재확인 (매도 시점에서 다시 체크)
            is_trading_time, _ = check_trading_time()
            if not is_trading_time:
                logger.warning(f"❌ {stock_name} 장외시간 매도 시도 차단")
                return None, "장외시간 매도 거부"
            
            # 🔥 2. 매도 전 보유량 기록 및 확인
            before_holdings = self.get_current_holdings(stock_code)
            before_amount = before_holdings.get('amount', 0)
            
            if before_amount < amount:
                logger.warning(f"❌ {stock_name} 보유량 부족: 보유 {before_amount}주 vs 매도 {amount}주")
                return None, "보유량 부족"
            
            # 🔥 3. 미체결 매도 추적 초기화
            if not hasattr(self, 'pending_sell_orders'):
                self.pending_sell_orders = {}
            
            # 🔥 4. 중복 매도 주문 방지 (10분 내 매도 주문 방지)
            if stock_code in self.pending_sell_orders:
                pending_info = self.pending_sell_orders[stock_code]
                order_time_str = pending_info.get('order_time', '')
                try:
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                    
                    if elapsed_minutes < 10:
                        logger.warning(f"❌ {stock_name} 중복 매도 방지: {elapsed_minutes:.1f}분 전 매도 주문 있음")
                        return None, "중복 매도 방지"
                except:
                    pass
            
            # 🔥 5. 수수료 예상 계산 및 주문 준비
            estimated_fee = self.calculate_trading_fee(price, amount, False)
            order_price = int(price * 0.99)  # 한국주식은 정수 단위, 1% 아래로 지정가
            
            logger.info(f"📉 {stock_name} 매도 주문 시도:")
            logger.info(f"   수량: {amount:,}주 × {order_price:,}원")
            logger.info(f"   예상 수수료: {estimated_fee:,.0f}원")
            
            # 🔥 6. 한국주식 지정가 매도 주문 실행
            result = KisKR.MakeSellLimitOrder(stock_code, amount, order_price)
            
            if not result:
                logger.error(f"❌ {stock_name} 매도 주문 응답 없음")
                return None, "매도 주문 응답 없음"
            
            # 🔥 7. 주문 응답 체크 (기존 로직 개선)
            if isinstance(result, dict):
                rt_cd = result.get('rt_cd', '')
                msg1 = result.get('msg1', '')
                
                # 🔥 명확한 실패 코드가 있는 경우만 실패 처리
                if rt_cd and rt_cd != '0':
                    error_msg = f"매도 실패: {msg1} (rt_cd: {rt_cd})"
                    logger.error(f"❌ {stock_name} {error_msg}")
                    return None, error_msg
            
            # 🔥 8. 매도 주문 정보 기록 (미체결 추적용)
            sell_order_info = {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'order_amount': amount,
                'before_amount': before_amount,
                'order_price': order_price,
                'original_price': price,
                'status': 'submitted'
            }
            
            self.pending_sell_orders[stock_code] = sell_order_info
            
            logger.info(f"✅ {stock_name} 매도 주문 성공 - 체결 확인 시작")
            
            # 🔥 9. 60초간 체결 확인
            start_time = time.time()
            check_count = 0
            
            while time.time() - start_time < 60:
                check_count += 1
                time.sleep(2)  # 2초마다 체크
                
                try:
                    current_holdings = self.get_current_holdings(stock_code)
                    current_amount = current_holdings.get('amount', 0)
                    
                    # 🔥🔥🔥 핵심: 보유량 감소로 체결 확인
                    actual_sold = before_amount - current_amount
                    
                    if actual_sold >= amount:
                        # 🎉 체결 완료!
                        logger.info(f"✅ {stock_name} 매도 체결 완료!")
                        logger.info(f"   🎯 목표수량: {amount:,}주")
                        logger.info(f"   📊 매도 전: {before_amount:,}주 → 매도 후: {current_amount:,}주")
                        logger.info(f"   ✅ 실제 매도량: {actual_sold:,}주")
                        logger.info(f"   🕐 체결시간: {check_count * 2}초")
                        
                        # 가격 차이 로깅
                        price_diff = order_price - price
                        if abs(price_diff) > 10:
                            logger.info(f"   📊 주문가격 차이: {price_diff:+,.0f}원")
                        
                        # 🔥 체결 완료시 pending 제거
                        if stock_code in self.pending_sell_orders:
                            del self.pending_sell_orders[stock_code]
                        
                        # 🔥🔥🔥 핵심 개선: 매도 완료 즉시 강제 쿨다운 설정 🔥🔥🔥
                        if not hasattr(self, 'last_sell_time'):
                            self.last_sell_time = {}
                        if not hasattr(self, 'last_sell_info'):
                            self.last_sell_info = {}

                        # 🔥 매도 타입 판단 (손절 vs 수익확정)
                        sell_type = 'profit_taking'  # 기본값
                        
                        # 매도 사유로 손절 여부 판단 (호출하는 곳에서 구분 가능하도록)
                        import inspect
                        frame = inspect.currentframe()
                        try:
                            caller_locals = frame.f_back.f_locals
                            if 'sell_reason' in caller_locals:
                                reason = caller_locals.get('sell_reason', '')
                                if '손절' in reason or 'stop_loss' in reason.lower():
                                    sell_type = 'stop_loss'
                        except:
                            pass
                        finally:
                            del frame

                        self.last_sell_time[stock_code] = datetime.now()
                        self.last_sell_info[stock_code] = {
                            'amount': actual_sold,
                            'price': order_price,
                            'original_price': price,
                            'timestamp': datetime.now(),
                            'type': sell_type,
                            'before_amount': before_amount,
                            'after_amount': current_amount
                        }

                        # 🔥 강화된 쿨다운 설정 로깅
                        cooldown_hours = 24 if sell_type == 'stop_loss' else 6
                        logger.info(f"🕐 {stock_name} 매도 완료 - 즉시 강제 쿨다운 설정")
                        logger.info(f"   📊 매도 정보: {actual_sold:,}주 {sell_type} 매도")
                        logger.info(f"   ⏰ 쿨다운 시작: {datetime.now()}")
                        logger.info(f"   🔒 재매수 금지: 향후 {cooldown_hours}시간")
                        logger.info(f"   🛡️ 매도 후 즉시 재매수 100% 차단")
                        
                        # 🔥 체결 완료 Discord 알림
                        if config.config.get("use_discord_alert", True):
                            sell_type_desc = "손절" if sell_type == 'stop_loss' else "수익확정"
                            msg = f"✅ {stock_name} {sell_type_desc} 매도 체결!\n"
                            msg += f"💰 {order_price:,}원 × {actual_sold:,}주\n"
                            msg += f"⚡ 체결시간: {check_count * 2}초\n"
                            msg += f"🔒 쿨다운: {cooldown_hours}시간 재매수 금지\n"
                            msg += f"🛡️ 즉시 재매수 방지 시스템 작동"
                            discord_alert.SendMessage(msg)
                        
                        # 🔥 성공 반환 (기존 인터페이스 유지)
                        return result, None
                        
                except Exception as check_e:
                    logger.warning(f"   ⚠️ 매도 체결 확인 중 오류: {str(check_e)}")
                
                # 진행 상황 로깅 (10초마다)
                if check_count % 5 == 0:
                    logger.info(f"   ⏳ 매도 체결 대기 중... ({check_count * 2}초 경과)")
            
            # 🔥 10. 60초 후 미체결 처리
            logger.warning(f"⏰ {stock_name} 매도 체결 시간 초과 (60초)")
            
            # 🔥 미체결 상태로 기록 유지 (20분간 추적)
            if stock_code in self.pending_sell_orders:
                self.pending_sell_orders[stock_code]['status'] = 'pending'
                self.pending_sell_orders[stock_code]['timeout_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 🔥 미체결 알림
            if config.config.get("use_discord_alert", True):
                msg = f"⏰ {stock_name} 매도 미체결\n"
                msg += f"💰 주문: {order_price:,}원 × {amount:,}주\n"
                msg += f"⚠️ 60초 내 체결되지 않음\n"
                msg += f"🔄 20분간 지연 체결 추적 중..."
                discord_alert.SendMessage(msg)
            
            logger.warning(f"⚠️ 미체결: {stock_name} - 주문은 활성 상태, 20분간 추적")
            return None, "체결 시간 초과 - 추적 중"
            
        except Exception as e:
            # 🔥 예외 발생시 pending 정리
            try:
                if hasattr(self, 'pending_sell_orders') and stock_code in self.pending_sell_orders:
                    del self.pending_sell_orders[stock_code]
            except:
                pass
            
            logger.error(f"❌ {stock_name} 매도 주문 처리 중 예외: {str(e)}")
            return None, str(e)

    def check_pending_sell_orders(self):
        """🔥 매도 미체결 주문 자동 관리 - 20분간 지연 체결 추적"""
        try:
            if not hasattr(self, 'pending_sell_orders') or not self.pending_sell_orders:
                return
            
            logger.info("🔍 매도 미체결 주문 자동 관리 시작")
            
            completed_orders = []
            expired_orders = []
            
            for stock_code, order_info in self.pending_sell_orders.items():
                try:
                    stock_name = order_info.get('stock_name', stock_code)
                    order_time_str = order_info.get('order_time', '')
                    
                    if not order_time_str:
                        continue
                        
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                    
                    logger.info(f"📋 매도 미체결 주문 체크: {stock_name} ({elapsed_minutes:.1f}분 경과)")
                    
                    # 🔥 1. 체결 여부 재확인
                    current_holdings = self.get_current_holdings(stock_code)
                    current_amount = current_holdings.get('amount', 0)
                    before_amount = order_info.get('before_amount', 0)
                    target_amount = order_info.get('order_amount', 0)
                    
                    actual_sold = before_amount - current_amount
                    
                    if actual_sold >= target_amount:
                        # 🎉 지연 체결 발견!
                        logger.info(f"✅ 지연 매도 체결 발견: {stock_name} {actual_sold:,}주")
                        
                        completed_orders.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'sold_amount': actual_sold,
                            'order_price': order_info.get('order_price', 0),
                            'original_price': order_info.get('original_price', 0),
                            'delay_minutes': elapsed_minutes,
                            'order_info': order_info
                        })
                        
                    elif elapsed_minutes > 20:  # 20분 이상 미체결시 만료
                        logger.warning(f"⏰ 매도 미체결 주문 만료: {stock_name} ({elapsed_minutes:.1f}분)")
                        
                        expired_orders.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'elapsed_minutes': elapsed_minutes
                        })
                        
                    else:
                        # 🔄 계속 대기
                        logger.info(f"⏳ 계속 대기: {stock_name} ({elapsed_minutes:.1f}/20분)")
                    
                except Exception as e:
                    logger.error(f"매도 미체결 주문 체크 중 오류 ({stock_code}): {str(e)}")
            
            # 🔥 2. 완료된 주문 처리 및 SellHistory 기록
            for completed in completed_orders:
                stock_code = completed['stock_code']
                stock_name = completed['stock_name']
                
                try:
                    # 해당 종목의 MagicDataList 찾기
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    if stock_data_info:
                        # 보유 중인 포지션 찾아서 SellHistory 기록
                        for magic_data in stock_data_info['MagicDataList']:
                            if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                                
                                # 🔥 지연 체결 SellHistory 기록
                                entry_price = magic_data['EntryPrice']
                                sell_price = completed['original_price']
                                return_pct = (sell_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
                                
                                sell_record = {
                                    'date': datetime.now().strftime("%Y-%m-%d"),
                                    'time': datetime.now().strftime("%H:%M:%S"),
                                    'amount': completed['sold_amount'],
                                    'price': sell_price,
                                    'return_pct': return_pct,
                                    'sell_ratio': 1.0,  # 전량 매도로 가정
                                    'reason': f'지연_체결({completed["delay_minutes"]:.1f}분)',
                                    'max_profit': magic_data.get(f'max_profit_{magic_data["Number"]}', 0),
                                    'order_price': completed['order_price']
                                }
                                
                                # SellHistory에 추가
                                if 'SellHistory' not in magic_data:
                                    magic_data['SellHistory'] = []
                                magic_data['SellHistory'].append(sell_record)
                                
                                # CurrentAmt 업데이트
                                magic_data['CurrentAmt'] = max(0, magic_data['CurrentAmt'] - completed['sold_amount'])
                                
                                # 전량 매도시 IsBuy 상태 변경
                                if magic_data['CurrentAmt'] <= 0:
                                    magic_data['IsBuy'] = False
                                    # 최고점 리셋
                                    for key in list(magic_data.keys()):
                                        if key.startswith('max_profit_'):
                                            magic_data[key] = 0
                                
                                # 실현손익 업데이트
                                realized_pnl = (sell_price - entry_price) * completed['sold_amount']
                                self.update_realized_pnl(stock_code, realized_pnl)
                                
                                logger.info(f"✅ {stock_name} 지연 체결 처리 완료:")
                                logger.info(f"   차수: {magic_data['Number']}차")
                                logger.info(f"   매도량: {completed['sold_amount']:,}주")
                                logger.info(f"   수익률: {return_pct:+.1f}%")
                                logger.info(f"   지연시간: {completed['delay_minutes']:.1f}분")
                                logger.info(f"   실현손익: {realized_pnl:+,.0f}원")
                                
                                break  # 첫 번째 보유 포지션에만 적용
                    
                    # 🔥 3. Discord 알림
                    if config.config.get("use_discord_alert", True):
                        msg = f"🎉 지연 매도 체결: {stock_name}\n"
                        msg += f"💰 {completed['sold_amount']:,}주 매도\n"
                        msg += f"📊 수익률: {return_pct:+.1f}%\n"
                        msg += f"⏰ 지연시간: {completed['delay_minutes']:.1f}분\n"
                        msg += f"✅ SellHistory 자동 기록됨\n"
                        msg += f"🔥 적응형 쿨다운 정상 작동 예정"
                        discord_alert.SendMessage(msg)
                    
                except Exception as process_e:
                    logger.error(f"지연 체결 처리 중 오류 ({stock_code}): {str(process_e)}")
                
                # 완료된 주문 제거 예약
                if stock_code in self.pending_sell_orders:
                    del self.pending_sell_orders[stock_code]
                    logger.info(f"✅ 완료된 매도 주문 제거: {stock_name}")
            
            # 🔥 4. 만료된 주문 제거
            for expired in expired_orders:
                stock_code = expired['stock_code']
                if stock_code in self.pending_sell_orders:
                    del self.pending_sell_orders[stock_code]
                    logger.info(f"⏰ 만료된 매도 주문 제거: {expired['stock_name']}")
            
            # 🔥 5. 처리 완료 후 데이터 저장
            if completed_orders:
                self.save_split_data()
                logger.info("💾 지연 체결 처리 후 데이터 저장 완료")
            
            # 🔥 6. 요약 로깅
            if completed_orders or expired_orders:
                summary_msg = f"📋 매도 미체결 주문 관리 완료\n"
                if completed_orders:
                    summary_msg += f"✅ 지연 체결: {len(completed_orders)}개\n"
                if expired_orders:
                    summary_msg += f"⏰ 만료 정리: {len(expired_orders)}개"
                
                logger.info(summary_msg)
            
            remaining_count = len(getattr(self, 'pending_sell_orders', {}))
            if remaining_count > 0:
                logger.info(f"🔄 계속 관리 중인 매도 미체결 주문: {remaining_count}개")
            
        except Exception as e:
            logger.error(f"매도 미체결 주문 자동 관리 중 오류: {str(e)}")

    def check_and_manage_pending_orders(self):
        """🔥 미체결 주문 자동 관리 - 매수 + 매도 통합"""
        try:
            # 🔥 1. 기존 매수 미체결 주문 관리
            if hasattr(self, 'pending_orders') and self.pending_orders:
                logger.info("🔍 미체결 주문 자동 관리 시작")
                
                completed_orders = []
                expired_orders = []
                
                for stock_code, order_info in self.pending_orders.items():
                    try:
                        stock_name = order_info.get('stock_name', stock_code)
                        order_time_str = order_info.get('order_time', '')
                        try:
                            order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                            elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                            
                            logger.info(f"📋 미체결 주문 체크: {stock_name} ({elapsed_minutes:.1f}분 경과)")
                            
                            # 체결 여부 재확인 (기존 매수 로직)
                            my_stocks = KisKR.GetMyStockList()
                            executed_amount = 0
                            before_amount = order_info.get('before_amount', 0)
                            target_amount = order_info.get('order_amount', 0)
                            
                            for stock in my_stocks:
                                if stock['StockCode'] == stock_code:
                                    current_amount = int(stock.get('StockAmt', 0))
                                    executed_amount = current_amount - before_amount
                                    break
                            
                            if executed_amount >= target_amount:
                                completed_orders.append({
                                    'stock_code': stock_code,
                                    'stock_name': stock_name,
                                    'executed_amount': executed_amount,
                                    'delay_minutes': elapsed_minutes
                                })
                            elif elapsed_minutes > 20:
                                expired_orders.append({
                                    'stock_code': stock_code,
                                    'stock_name': stock_name,
                                    'elapsed_minutes': elapsed_minutes
                                })
                            
                        except Exception as time_e:
                            logger.error(f"매수 주문 시간 처리 오류: {str(time_e)}")
                            
                    except Exception as e:
                        logger.error(f"미체결 주문 체크 중 오류 ({stock_code}): {str(e)}")
                
                # 완료/만료된 주문 제거
                for completed in completed_orders:
                    if completed['stock_code'] in self.pending_orders:
                        del self.pending_orders[completed['stock_code']]
                        logger.info(f"✅ 지연 매수 체결: {completed['stock_name']}")
                
                for expired in expired_orders:
                    if expired['stock_code'] in self.pending_orders:
                        del self.pending_orders[expired['stock_code']]
                        logger.info(f"⏰ 만료된 매수 주문 제거: {expired['stock_name']}")
            
            # 🔥 2. 새로 추가: 매도 미체결 주문 관리
            self.check_pending_sell_orders()
            
        except Exception as e:
            logger.error(f"미체결 주문 자동 관리 중 오류: {str(e)}")

    def calculate_trading_fee(self, price, quantity, is_buy=True):
        """거래 수수료 및 세금 계산 - 한국주식 실제 수수료 반영"""
        trade_amount = price * quantity
        
        # 🔥 한국주식 실제 수수료 적용
        commission_rate = config.config.get("commission_rate", 0.00015)
        commission = trade_amount * commission_rate
        
        if not is_buy:  # 매도 시에만 세금 부과
            tax_rate = config.config.get("tax_rate", 0.0023)
            special_tax_rate = config.config.get("special_tax_rate", 0.0015)
            tax = trade_amount * tax_rate
            special_tax = trade_amount * special_tax_rate
        else:
            tax = 0
            special_tax = 0
        
        return commission + tax + special_tax

    def detect_market_timing(self):
        """한국 시장 추세와 타이밍을 감지하는 함수"""
        try:
            # 🔥 코스피 지수 데이터로 한국 시장 상황 판단
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 90)
            if kospi_df is None or len(kospi_df) < 20:
                logger.warning("코스피 데이터 조회 실패, 중립 상태로 설정")
                return "neutral"
                
            # 이동평균선 계산
            kospi_ma5 = kospi_df['close'].rolling(window=5).mean().iloc[-1]
            kospi_ma20 = kospi_df['close'].rolling(window=20).mean().iloc[-1]
            kospi_ma60 = kospi_df['close'].rolling(window=60).mean().iloc[-1]
            
            current_index = kospi_df['close'].iloc[-1]
            
            # 시장 상태 판단
            if current_index > kospi_ma5 > kospi_ma20 > kospi_ma60:
                return "strong_uptrend"  # 강한 상승 추세
            elif current_index > kospi_ma5 and kospi_ma5 > kospi_ma20:
                return "uptrend"         # 상승 추세
            elif current_index < kospi_ma5 and kospi_ma5 < kospi_ma20:
                return "downtrend"       # 하락 추세
            elif current_index < kospi_ma5 < kospi_ma20 < kospi_ma60:
                return "strong_downtrend"  # 강한 하락 추세
            else:
                return "neutral"         # 중립
        except Exception as e:
            logger.error(f"한국 마켓 타이밍 감지 중 오류: {str(e)}")
            return "neutral"

    def update_realized_pnl(self, stock_code, realized_pnl):
        """실현 손익 업데이트 - 설정 파일에도 반영"""
        for data_info in self.split_data_list:
            if data_info['StockCode'] == stock_code:

                data_info['RealizedPNL'] = data_info.get('RealizedPNL', 0) + realized_pnl
                # 🔥 월별 손익 추적
                current_month = datetime.now().strftime("%Y-%m")
                monthly_pnl = data_info.get('MonthlyPNL', {})
                monthly_pnl[current_month] = monthly_pnl.get(current_month, 0) + realized_pnl
                data_info['MonthlyPNL'] = monthly_pnl
                
                # 🔥 설정 파일의 성과 추적에도 반영
                tracking = config.config.get("performance_tracking", {})
                tracking["total_realized_pnl"] = tracking.get("total_realized_pnl", 0) + realized_pnl
                
                if realized_pnl > 0:
                    tracking["winning_trades"] = tracking.get("winning_trades", 0) + 1
                
                tracking["total_trades"] = tracking.get("total_trades", 0) + 1
                
                config.config["performance_tracking"] = tracking
                config.save_config()
                
                logger.info(f"✅ {stock_code} 실현손익 업데이트: {realized_pnl:+,.0f}원")
                break

    ################################### 🔥 예산 관리 시스템 ##################################

    def calculate_dynamic_budget(self):
        """🔥 한국주식 성과 기반 동적 예산 계산"""
        try:
            # 🔥 한국주식 계좌 정보 조회
            balance = KisKR.GetBalance()
            if not balance:
                logger.error("한국주식 계좌 정보 조회 실패")
                return config.absolute_budget
                
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 초기 자산 설정 (첫 실행시)
            if config.config.get("initial_total_asset", 0) == 0:
                config.config["initial_total_asset"] = current_total
                config.save_config()
                logger.info(f"🎯 초기 총 자산 설정: {current_total:,.0f}원")
            
            # 성과율 계산
            initial_asset = config.config.get("initial_total_asset", current_total)
            performance_rate = (current_total - initial_asset) / initial_asset if initial_asset > 0 else 0
            
            # 성과 추적 업데이트
            tracking = config.config.get("performance_tracking", {})
            tracking["best_performance"] = max(tracking.get("best_performance", 0), performance_rate)
            tracking["worst_performance"] = min(tracking.get("worst_performance", 0), performance_rate)
            config.config["performance_tracking"] = tracking
            
            # 🔥 전략별 예산 계산
            strategy = config.absolute_budget_strategy
            base_budget = config.absolute_budget
            
            if strategy == "proportional":
                # 성과 기반 동적 조정
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
                # 손실 허용도 기반 조정
                loss_tolerance = config.config.get("budget_loss_tolerance", 0.2)
                min_budget = base_budget * (1 - loss_tolerance)
                
                if current_total >= min_budget:
                    dynamic_budget = base_budget
                else:
                    dynamic_budget = max(current_total * 0.8, min_budget)
                    
            else:  # "strict"
                # 고정 예산
                dynamic_budget = base_budget
            
            # 🔥 안전장치: 현금 잔고 기반 제한
            safety_ratio = config.config.get("safety_cash_ratio", 0.8)
            max_safe_budget = remain_money * safety_ratio
            
            if dynamic_budget > max_safe_budget:
                logger.warning(f"💰 현금 잔고 기반 예산 제한: {dynamic_budget:,.0f}원 → {max_safe_budget:,.0f}원")
                dynamic_budget = max_safe_budget
            
            # 로깅
            logger.info(f"📊 한국주식 동적 예산 계산 결과:")
            logger.info(f"  전략: {strategy}")
            logger.info(f"  초기 자산: {initial_asset:,.0f}원")
            logger.info(f"  현재 자산: {current_total:,.0f}원")
            logger.info(f"  현금 잔고: {remain_money:,.0f}원")
            logger.info(f"  성과율: {performance_rate*100:+.2f}%")
            if strategy == "proportional":
                logger.info(f"  예산 배수: {multiplier:.2f}x")
            logger.info(f"  최종 예산: {dynamic_budget:,.0f}원")
            
            return dynamic_budget
            
        except Exception as e:
            logger.error(f"한국주식 동적 예산 계산 중 오류: {str(e)}")
            return config.absolute_budget

    def update_budget(self):
        """예산 업데이트 - 한국주식 절대 예산 기반"""
        if config.use_absolute_budget:
            self.total_money = self.calculate_dynamic_budget()
            logger.info(f"💰 한국주식 절대 예산 기반 운영: {self.total_money:,.0f}원")
        else:
            # 기존 방식 (호환성 유지)
            balance = KisKR.GetBalance()
            self.total_money = float(balance.get('TotalMoney', 0)) * 0.08  # 8%
            logger.info(f"💰 비율 기반 운영 (8%): {self.total_money:,.0f}원")

    ################################### 🔥 빠른 동기화 체크 시스템 ##################################

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
                    logger.warning(f"🚨 {stock_name}: 브로커 {broker_amount:,}주 vs 내부 {internal_amount:,}주")
            
            if mismatch_count == 0:
                logger.info("✅ 모든 종목 데이터 일치")
                return True
            else:
                logger.warning(f"⚠️ {mismatch_count}개 종목 데이터 불일치")
                return False
                
        except Exception as e:
            logger.error(f"빠른 동기화 체크 중 오류: {str(e)}")
            return False

    ################################### 🔥 개선된 기술지표 계산 ##################################

    def get_technical_indicators_weighted(self, stock_code, period=60, recent_period=30, recent_weight=0.7):
        """한국주식용 가중치를 적용한 기술적 지표 계산 함수"""
        try:
            # 🔥 한국주식 전체 기간 데이터 가져오기
            df = Common.GetOhlcv("KR", stock_code, period)
            if df is None or len(df) < period // 2:
                logger.warning(f"{stock_code} 한국주식 데이터 조회 실패")
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
            step_gap = gap / config.config.get("div_num", 5.0)
            percent_gap = round((gap / min_price) * 100, 2)
            
            # 목표 수익률과 트리거 손실률 계산
            target_rate = round(percent_gap / config.config.get("div_num", 5.0), 2)
            trigger_rate = -round((percent_gap / config.config.get("div_num", 5.0)), 2)
            
            # 조정폭 계산
            current_price = KisKR.GetCurrentPrice(stock_code)
            pullback_from_high = (max_high_30 - current_price) / max_high_30 * 100
            
            # 현재 구간 계산
            div_num = config.config.get("div_num", 5.0)
            now_step = div_num
            for step in range(1, int(div_num) + 1):
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
                'pullback_from_high': pullback_from_high
            }
        except Exception as e:
            logger.error(f"한국주식 가중치 적용 기술적 지표 계산 중 오류: {str(e)}")
            return None

    def get_technical_indicators(self, stock_code):
        """기존 기술적 지표 계산 함수 (호환성 유지)"""
        target_stocks = config.target_stocks
        stock_config = target_stocks.get(stock_code, {})
        
        period = stock_config.get('period', 60)
        recent_period = stock_config.get('recent_period', 30)
        recent_weight = stock_config.get('recent_weight', 0.7)
        
        return self.get_technical_indicators_weighted(
            stock_code, 
            period=period, 
            recent_period=recent_period, 
            recent_weight=recent_weight
        )

    ################################### 🔥 개선된 성과 추적 시스템 ##################################

    def get_performance_summary(self):
        """현재 성과 요약 정보 반환"""
        try:
            # 브로커 실제 정보
            balance = KisKR.GetBalance()
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 설정에서 추적 정보
            tracking = config.config.get("performance_tracking", {})
            initial_asset = config.config.get("initial_total_asset", current_total)
            
            # 성과 계산
            total_change = current_total - initial_asset
            total_change_pct = (total_change / initial_asset * 100) if initial_asset > 0 else 0
            
            # 실현손익 합계
            total_realized_pnl = 0
            for stock_data in self.split_data_list:
                total_realized_pnl += stock_data.get('RealizedPNL', 0)
            
            # 미실현손익 계산
            unrealized_pnl = 0
            target_stocks = config.target_stocks
            
            for stock_code in target_stocks.keys():
                holdings = self.get_current_holdings(stock_code)
                if holdings['amount'] > 0 and holdings['avg_price'] > 0:
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price:
                        stock_unrealized = (current_price - holdings['avg_price']) * holdings['amount']
                        unrealized_pnl += stock_unrealized
            
            return {
                'current_total': current_total,
                'initial_asset': initial_asset,
                'total_change': total_change,
                'total_change_pct': total_change_pct,
                'remain_money': remain_money,
                'realized_pnl': total_realized_pnl,
                'unrealized_pnl': unrealized_pnl,
                'total_pnl': total_realized_pnl + unrealized_pnl,
                'best_performance': tracking.get('best_performance', 0),
                'worst_performance': tracking.get('worst_performance', 0),
                'total_trades': tracking.get('total_trades', 0),
                'winning_trades': tracking.get('winning_trades', 0),
                'enhanced_metrics': tracking.get('enhanced_metrics', {})
            }
            
        except Exception as e:
            logger.error(f"성과 요약 계산 중 오류: {str(e)}")
            return {}

################################### 🔥 개선된 수익 확정 로직 ##################################

    def check_profit_cap(self, stock_code, magic_data, current_price, stock_config):
        """🎯 수익률 상한제 체크 - 시장상황별 동적 조정"""
        try:
            position_num = magic_data['Number']
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
            
            if current_amount <= 0:
                return False, ""
            
            # 현재 수익률 계산
            current_return = (current_price - entry_price) / entry_price * 100
            
            # 수익률 상한제 설정 확인
            profit_cap_settings = stock_config.get('profit_cap_settings', {})
            if not profit_cap_settings.get('enable', False):
                return False, ""
            
            # 현재 시장상황 감지
            market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())
            
            # 시장상황별 상한 가져오기
            market_caps = profit_cap_settings.get('market_based_caps', {})
            current_market_config = market_caps.get(market_timing, market_caps.get('neutral', {}))
            
            # 차수별 상한 (1차~5차)
            position_caps = current_market_config.get('position_caps', [20, 18, 15, 12, 10])
            if position_num <= len(position_caps):
                profit_cap = position_caps[position_num - 1]
            else:
                profit_cap = position_caps[-1]  # 마지막 값 사용
            
            # 상한 도달 체크
            if current_return >= profit_cap:
                logger.warning(f"🎯 {stock_code} {position_num}차 수익률 상한 도달!")
                logger.warning(f"   현재 수익률: {current_return:.1f}% ≥ 상한: {profit_cap}%")
                logger.warning(f"   시장상황: {market_timing}")
                return True, f"수익상한도달({current_return:.1f}%≥{profit_cap}%_시장:{market_timing})"
            
            # 경고 레벨 체크
            warning_level = current_market_config.get('warning_level', profit_cap * 0.8)
            if current_return >= warning_level:
                logger.info(f"⚠️ {stock_code} {position_num}차 상한 경고!")
                logger.info(f"   현재: {current_return:.1f}% ≥ 경고: {warning_level}% (상한: {profit_cap}%)")
            
            return False, ""
            
        except Exception as e:
            logger.error(f"수익률 상한 체크 오류: {str(e)}")
            return False, ""

    def check_enhanced_trailing_stop(self, stock_code, magic_data, current_price, stock_config):
        """🔄 안전한 트레일링 스탑 체크 - 수익 구간에서만 작동"""
        try:
            position_num = magic_data['Number']
            entry_price = magic_data['EntryPrice']
            current_amount = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
            
            if current_amount <= 0:
                return False, ""
            
            # 현재 수익률 계산
            current_return = (current_price - entry_price) / entry_price * 100
            
            # 트레일링 스탑 설정 확인
            trailing_config = stock_config.get('enhanced_trailing_stop', {})
            if not trailing_config.get('enable', False):
                return False, ""
            
            # 최고점 추적
            max_profit_key = f'max_profit_{position_num}'
            max_profit = magic_data.get(max_profit_key, 0)
            
            # 🛡️ 안전장치 1: 손실 상태에서는 트레일링 비활성화
            if current_return <= 0:
                return False, "손실상태_트레일링_비활성화"
            
            # 🛡️ 안전장치 2: 최소 활성화 수익률 체크
            min_activation = trailing_config.get('min_profit_activation', 5)
            if max_profit < min_activation:
                return False, f"최소활성화수익_미달({max_profit:.1f}%<{min_activation}%)"
            
            # 🛡️ 안전장치 3: 최소 유지 수익률 체크
            min_keep_profit = trailing_config.get('min_keep_profit', 2)
            if current_return <= min_keep_profit:
                return False, f"최소유지수익_보호({current_return:.1f}%≤{min_keep_profit}%)"
            
            # 🔄 트레일링 거리 계산 (구간별 차등)
            profit_zones = trailing_config.get('profit_zones', [
                {"min": 5, "max": 10, "trailing": 3},
                {"min": 10, "max": 20, "trailing": 4},
                {"min": 20, "max": 999, "trailing": 5}
            ])
            
            trailing_distance = 3  # 기본값
            for zone in profit_zones:
                if zone['min'] <= max_profit < zone['max']:
                    trailing_distance = zone['trailing']
                    break
            
            # 🔧 동적 조정 (변동성, 시장 스트레스)
            dynamic_adjustment = trailing_config.get('dynamic_adjustment', {})
            
            # 변동성 조정
            try:
                df = Common.GetOhlcv("KR", stock_code, 20)
                if df is not None and len(df) >= 15:
                    volatility = df['close'].pct_change().std() * 100
                    if volatility > 5.0:  # 고변동성
                        volatility_bonus = dynamic_adjustment.get('high_volatility_bonus', 1)
                        trailing_distance += volatility_bonus
                        logger.debug(f"📊 {stock_code} 고변동성 조정: +{volatility_bonus}%p")
            except:
                pass
            
            # 시장 상황 조정
            market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())
            if market_timing in ['downtrend', 'strong_downtrend']:
                stress_bonus = dynamic_adjustment.get('market_stress_bonus', 2)
                trailing_distance += stress_bonus
                logger.debug(f"📉 {stock_code} 시장스트레스 조정: +{stress_bonus}%p")
            
            # 🎯 트레일링 라인 계산
            trailing_line = max_profit - trailing_distance
            safe_trailing_line = max(trailing_line, min_keep_profit)  # 최소 수익 보장
            
            # 🔥 트레일링 스탑 발동 체크
            if current_return <= safe_trailing_line:
                logger.warning(f"🔄 {stock_code} {position_num}차 트레일링 스탑 발동!")
                logger.warning(f"   최고점: {max_profit:.1f}% → 현재: {current_return:.1f}%")
                logger.warning(f"   트레일링 거리: {trailing_distance}%p")
                logger.warning(f"   트레일링 라인: {safe_trailing_line:.1f}%")
                return True, f"안전트레일링({max_profit:.1f}%→{current_return:.1f}%,거리:{trailing_distance}%p)"
            
            # 디버그 로깅
            logger.debug(f"🔄 {stock_code} {position_num}차 트레일링 상태:")
            logger.debug(f"   현재: {current_return:.1f}% | 최고: {max_profit:.1f}% | 라인: {safe_trailing_line:.1f}%")
            
            return False, ""
            
        except Exception as e:
            logger.error(f"트레일링 스탑 체크 오류: {str(e)}")
            return False, ""

################################### 🔥 개선된 메인 매매 로직 ##################################

    def process_enhanced_selling_logic(self, stock_code, stock_info, magic_data_list, indicators, holdings):
        """🚀 개선된 매도 로직 - 상한제 + 트레일링 스탑 통합"""
        
        current_price = indicators['current_price']

        # 🔥 버그 방지 안전장치 (추가)
        for magic_data in magic_data_list:
            if magic_data['IsBuy'] and magic_data.get('CurrentAmt', 0) > 0:
                entry_price = magic_data['EntryPrice']
                current_return = (current_price - entry_price) / entry_price * 100
                
                if current_return <= 0:
                    logger.debug(f"🔍 {stock_code} 손실상태({current_return:.1f}%) - 수익매도 차단")
                    return False

        stock_config = config.target_stocks[stock_code]
        sells_executed = False
        
        for magic_data in magic_data_list:
            if magic_data['IsBuy'] and magic_data.get('CurrentAmt', 0) > 0:
                position_num = magic_data['Number']
                entry_price = magic_data['EntryPrice']
                current_amount = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                
                # 현재 수익률 계산
                current_return = (current_price - entry_price) / entry_price * 100
                
                # 🔥 최고점 추적 (개별 차수별)
                max_profit_key = f'max_profit_{position_num}'
                if max_profit_key not in magic_data:
                    magic_data[max_profit_key] = 0
                
                if current_return > magic_data[max_profit_key]:
                    magic_data[max_profit_key] = current_return
                    logger.info(f"📈 {stock_code} {position_num}차 최고점 갱신: {current_return:.1f}%")
                
                max_profit_achieved = magic_data[max_profit_key]
                
                # 매도 조건 체크 (우선순위 순서)
                should_sell = False
                sell_reason = ""
                sell_ratio = 1.0  # 기본 전량 매도
                
                # 🎯 1순위: 수익률 상한제 체크 (NEW!)
                cap_sell, cap_reason = self.check_profit_cap(
                    stock_code, magic_data, current_price, stock_config
                )
                
                if cap_sell:
                    should_sell = True
                    sell_reason = cap_reason
                    sell_ratio = 1.0  # 상한 도달시 무조건 전량매도
                    logger.warning(f"🎯 {stock_code} {position_num}차 수익 상한 매도")
                
                # 🔄 2순위: 안전한 트레일링 스탑 체크 (NEW!)
                elif max_profit_achieved > 0:
                    trailing_sell, trailing_reason = self.check_enhanced_trailing_stop(
                        stock_code, magic_data, current_price, stock_config
                    )
                    
                    if trailing_sell:
                        should_sell = True
                        sell_reason = trailing_reason
                        sell_ratio = 1.0  # 트레일링 스탑은 전량매도
                        logger.warning(f"🔄 {stock_code} {position_num}차 트레일링 스탑 매도")
                
                # 🚀 3순위: 기존 빠른 수익 확정 체크
                if not should_sell:
                    quick_sell, quick_reason = self.check_quick_profit_opportunity(
                        stock_code, magic_data, current_price, stock_config
                    )
                    
                    if quick_sell:
                        should_sell = True
                        sell_reason = quick_reason
                        sell_ratio = 0.5  # 50% 부분 매도 (1주라서 실제로는 0주)
                        logger.info(f"💰 {stock_code} {position_num}차 빠른 수익 확정: 50% 부분 매도")
                
                # 🛡️ 4순위: 기존 안전장치 보호선 체크  
                if not should_sell and max_profit_achieved > 0:
                    safety_sell, safety_reason = self.check_safety_protection(
                        stock_code, magic_data, current_price, stock_config, max_profit_achieved
                    )
                    
                    if safety_sell:
                        should_sell = True
                        sell_reason = safety_reason
                        sell_ratio = 1.0  # 안전장치는 전량 매도
                        logger.warning(f"🛡️ {stock_code} {position_num}차 안전장치 매도")
                
                # 🎯 5순위: 기존 기본 목표가 달성
                if not should_sell:
                    if current_return >= stock_config.get('hold_profit_target', 6):
                        should_sell = True
                        sell_reason = f"목표달성({current_return:.1f}%≥{stock_config.get('hold_profit_target', 6)}%)"
                        
                        # 상승장에서는 부분 매도, 다른 상황에서는 전량 매도
                        market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())                  
                        if market_timing in ["strong_uptrend", "uptrend"]:
                            sell_ratio = stock_config.get('partial_sell_ratio', 0.4)  # 40% 부분 매도 (1주라서 0주)
                            logger.info(f"📈 {stock_code} {position_num}차 상승장 목표 달성: {sell_ratio*100:.0f}% 부분 매도")
                        else:
                            sell_ratio = 1.0  # 전량 매도
                            logger.info(f"🎯 {stock_code} {position_num}차 목표 달성: 전량 매도")
                
                # ⏰ 6순위: 기존 시간 기반 매도
                if not should_sell:
                    time_sell, time_reason = self.check_time_based_sell(
                        stock_code, magic_data, current_price, stock_config
                    )
                    
                    if time_sell:
                        should_sell = True
                        sell_reason = time_reason
                        sell_ratio = 0.6  # 60% 매도 (1주라서 0주)
                        logger.info(f"⏰ {stock_code} {position_num}차 시간 기반 매도: 60% 매도")

                # 🔥🔥🔥 실제 매도 실행 (누락된 핵심 부분) 🔥🔥🔥
                if should_sell:
                    try:
                        # 매도량 계산
                        if sell_ratio < 1.0:  # 부분 매도
                            if current_amount == 1:
                                # 1주인 경우 부분매도는 불가능하므로 스킵하거나 1주 전량매도
                                if sell_ratio >= 0.5:  # 50% 이상이면 1주 매도
                                    sell_amount = 1
                                    logger.info(f"🔧 {stock_code} {position_num}차 1주 전량매도 (부분매도 불가)")
                                else:
                                    logger.debug(f"⏭️ {stock_code} {position_num}차 부분매도 스킵: 1주×{sell_ratio:.1%}=0주")
                                    continue
                            else:
                                sell_amount = max(1, int(current_amount * sell_ratio))
                        else:  # 전량 매도
                            sell_amount = current_amount
                        
                        # 실제 매도 주문 실행
                        logger.info(f"🚀 {stock_code} {position_num}차 매도 실행: {sell_amount}주 ({sell_reason})")
                        
                        result, error = self.handle_sell(stock_code, sell_amount, current_price)
                        
                        if result:
                            # 매도 성공 처리
                            magic_data['CurrentAmt'] = current_amount - sell_amount
                            
                            if magic_data['CurrentAmt'] <= 0:
                                magic_data['IsBuy'] = False
                                # 전량 매도 시 최고점 리셋
                                if max_profit_key in magic_data:
                                    magic_data[max_profit_key] = 0
                            
                            # 매도 이력 기록
                            if 'SellHistory' not in magic_data:
                                magic_data['SellHistory'] = []
                            
                            # 실현 손익 계산
                            realized_pnl = (current_price - entry_price) * sell_amount
                            magic_data['SellHistory'].append({
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "amount": sell_amount,
                                "price": current_price,
                                "return_pct": current_return,
                                "reason": sell_reason,
                                "realized_pnl": realized_pnl
                            })
                            
                            # 실현손익 업데이트
                            self.update_realized_pnl(stock_code, realized_pnl)
                            
                            # 데이터 저장
                            self.save_split_data()
                            
                            # 성공 로깅
                            logger.info(f"✅ {stock_code} {position_num}차 매도 완료!")
                            logger.info(f"   매도량: {sell_amount}주 @ {current_price:,.0f}원")
                            logger.info(f"   수익률: {current_return:.2f}%")
                            logger.info(f"   실현손익: {realized_pnl:+,.0f}원")
                            logger.info(f"   사유: {sell_reason}")
                            
                            sells_executed = True
                            
                            # Discord 알림
                            if config.config.get("use_discord_alert", True):
                                # 🔥 설정파일에서 종목명 가져오기
                                stock_config = config.target_stocks.get(stock_code, {})
                                stock_name = stock_config.get('name', f"종목{stock_code}")
                                
                                profit_emoji = "💰" if realized_pnl > 0 else "📉"
                                sell_type = "수익확정" if realized_pnl > 0 else "손절"
                                discord_msg = f"{profit_emoji} **{stock_name} {sell_type}**\n"  # ✅ 동적!
                                discord_msg += f"• {position_num}차: {sell_amount}주 매도\n"
                                discord_msg += f"• 매도가: {current_price:,}원\n"
                                discord_msg += f"• 수익률: {current_return:+.2f}%\n"
                                discord_msg += f"• 실현손익: {realized_pnl:+,}원\n"
                                discord_msg += f"• 사유: {sell_reason}"
                                discord_alert.SendMessage(discord_msg)
                                
                            # if config.config.get("use_discord_alert", True):
                            #     profit_emoji = "💰" if realized_pnl > 0 else "📉"
                            #     discord_msg = f"{profit_emoji} **한화오션 수익확정**\n"
                            #     discord_msg += f"• {position_num}차: {sell_amount}주 매도\n"
                            #     discord_msg += f"• 매도가: {current_price:,}원\n"
                            #     discord_msg += f"• 수익률: {current_return:+.2f}%\n"
                            #     discord_msg += f"• 실현손익: {realized_pnl:+,}원\n"
                            #     discord_msg += f"• 사유: {sell_reason}"
                            #     discord_alert.SendMessage(discord_msg)
                                
                        else:
                            logger.error(f"❌ {stock_code} {position_num}차 매도 실패: {error}")
                            logger.error(f"   매도 시도: {sell_amount}주 @ {current_price:,.0f}원")
                            logger.error(f"   실패 사유: {sell_reason}")
                            
                    except Exception as sell_error:
                        logger.error(f"❌ {stock_code} {position_num}차 매도 처리 중 오류: {str(sell_error)}")


                # 🔥 매도 실행 (기존 로직 유지)
                # if should_sell:
                #     # 🔥 핵심: 1주 보유시 0주 계산 문제 해결
                #     if current_amount == 1 and sell_ratio < 1.0:
                #         # 부분매도가 0주로 계산되는 경우 처리
                #         calculated_amount = int(current_amount * sell_ratio)
                #         if calculated_amount == 0:
                #             # 🎯 상한제나 트레일링 스탑은 강제 전량매도
                #             if cap_sell or trailing_sell:
                #                 sell_amount = 1
                #                 logger.info(f"🔧 {stock_code} {position_num}차 1주 강제매도: {sell_reason}")
                #             else:
                #                 # 일반 부분매도는 스킵 (기존 로직 유지)
                #                 logger.debug(f"⏭️ {stock_code} {position_num}차 부분매도 스킵: 1주×{sell_ratio:.1%}=0주")
                #                 continue
                #         else:
                #             sell_amount = calculated_amount
                #     else:
                #         sell_amount = max(1, int(current_amount * sell_ratio))
                    
                #     # 매도량이 보유량보다 크면 조정
                #     if sell_amount > holdings['amount']:
                #         sell_amount = holdings['amount']
                    
                #     # 매도 주문 실행 (기존 함수 사용)
                #     result, error = self.handle_sell(stock_code, sell_amount, current_price)
                    
                #     if result:
                #         # 🎉 매도 성공 처리 (기존 로직)
                #         magic_data['CurrentAmt'] = current_amount - sell_amount
                        
                #         if magic_data['CurrentAmt'] <= 0:
                #             magic_data['IsBuy'] = False
                #             # 전량 매도 시 최고점 리셋
                #             magic_data[max_profit_key] = 0
                        
                #         # 매도 이력 기록
                #         if 'SellHistory' not in magic_data:
                #             magic_data['SellHistory'] = []
                        
                #         # 실현 손익 계산
                #         realized_pnl = (current_price - entry_price) * sell_amount
                #         magic_data['SellHistory'].append({
                #             "date": datetime.now().strftime("%Y-%m-%d"),
                #             "time": datetime.now().strftime("%H:%M:%S"),
                #             "amount": sell_amount,
                #             "price": current_price,
                #             "profit": realized_pnl,
                #             "return_pct": current_return,
                #             "sell_ratio": sell_ratio,
                #             "reason": sell_reason,
                #             "max_profit": max_profit_achieved
                #         })
                        
                #         # 누적 실현 손익 업데이트
                #         self.update_realized_pnl(stock_code, realized_pnl)
                        
                #         # 🎯 개선된 성공 메시지
                #         sell_type = "전량" if sell_ratio >= 1.0 else "부분"
                #         msg = f"✅ {stock_code} {position_num}차 {sell_type} 매도 완료!\n"
                #         msg += f"💰 {sell_amount}주 @ {current_price:,.0f}원\n"
                #         msg += f"📊 수익률: {current_return:+.2f}%\n"
                #         msg += f"💵 실현손익: {realized_pnl:+,.0f}원\n"
                #         msg += f"🎯 사유: {sell_reason}\n"
                        
                #         if max_profit_achieved > current_return:
                #             msg += f"📈 최고점: {max_profit_achieved:.1f}%\n"
                        
                #         # 🔥 개선사항 표시
                #         if cap_sell:
                #             msg += f"🎯 수익상한제 적용\n"
                #         elif trailing_sell:
                #             msg += f"🔄 안전 트레일링 스탑 적용\n"
                            
                #         logger.info(msg)
                        
                #         if config.config.get("use_discord_alert", True):
                #             discord_alert.SendMessage(msg)
                        
                #         sells_executed = True
                        
                #     else:
                #         logger.error(f"❌ {stock_code} {position_num}차 매도 실패: {error}")
        
        return sells_executed

    def _execute_sell_only_mode(self):
        """🚨 매도 전용 모드 (하락 보호 상황)"""
        try:
            logger.error("🚫 매도 전용 모드 실행 - 보유 포지션 정리 우선")
            
            target_stocks = config.target_stocks
            
            for stock_code, stock_info in target_stocks.items():
                try:
                    # 기술적 지표 계산
                    indicators = self.get_technical_indicators(stock_code)
                    if not indicators:
                        continue
                    
                    # 현재 보유 정보 조회
                    holdings = self.get_current_holdings(stock_code)
                    if holdings['amount'] <= 0:
                        continue
                    
                    # 종목 데이터 찾기
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    if not stock_data_info:
                        continue
                    
                    magic_data_list = stock_data_info['MagicDataList']
                    
                    # 🚨 손절 및 수익 매도만 실행
                    self.execute_adaptive_stop_loss(stock_code, indicators, magic_data_list)
                    self.process_enhanced_selling_logic(
                        stock_code, stock_info, magic_data_list, indicators, holdings
                    )
                    
                except Exception as e:
                    logger.error(f"매도 전용 모드 처리 중 오류 ({stock_code}): {str(e)}")
            
        except Exception as e:
            logger.error(f"매도 전용 모드 실행 오류: {str(e)}")

    def _execute_bear_market_mode(self):
        """🐻 베어마켓 모드 (극도로 제한적 운영)"""
        try:
            logger.error("🐻 베어마켓 모드 실행 - 극도로 제한적 운영")
            
            # 1. 매도 우선 실행
            self._execute_sell_only_mode()
            
            # 2. 현금 비율 강제 조정
            balance = KisKR.GetBalance()
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            cash_ratio = remain_money / current_total if current_total > 0 else 0
            
            bear_config = config.config.get('enhanced_downtrend_protection', {}).get('bear_market_mode', {})
            target_cash_ratio = bear_config.get('settings', {}).get('max_investment_ratio', 0.30)
            
            if cash_ratio < (1 - target_cash_ratio):  # 현금이 70% 미만이면
                # 추가 매도 필요
                additional_sell_ratio = 0.2  # 20% 추가 매도
                logger.error(f"🐻 베어마켓 모드: 현금 부족으로 {additional_sell_ratio*100:.0f}% 추가 매도")
                self.execute_emergency_partial_sell(additional_sell_ratio)
            
        except Exception as e:
            logger.error(f"베어마켓 모드 실행 오류: {str(e)}")

    def process_trading(self):
        """🔥 매도 후 즉시 재매수 방지가 강화된 매매 로직 처리"""
        """🔥 하락 보호 시스템이 통합된 매매 로직 처리"""
        # 🚨 1. 시장 추세 분석 및 하락 보호 체크 (5분마다)
        current_time = datetime.now()
        if (self.last_trend_check_time is None or 
            (current_time - self.last_trend_check_time).total_seconds() > 300):  # 5분
            
            # market_trend, risk_level, trend_details = self.detect_market_trend_enhanced()
            # protection_applied, protection_msg = self.apply_downtrend_protection(
            #     market_trend, risk_level, trend_details
            # )

            market_trend, risk_level, trend_details = self.detect_market_trend_with_individual_stocks()
            protection_applied, protection_msg = self.apply_smart_downtrend_protection(
                market_trend, risk_level, trend_details
            )
            
            if protection_applied:
                logger.error(f"🛡️ 하락 보호 시스템 작동: {protection_msg}")
                self.current_protection_level = market_trend
            
            self.last_trend_check_time = current_time
        
        # 🚨 2. 전체 매수 중단 체크
        if getattr(self, 'suspend_all_buys', False):
            logger.error("🚫 하락 보호로 인한 전체 매수 중단 - 매도만 실행")
            # 매도 로직만 실행하고 매수는 스킵
            self._execute_sell_only_mode()
            return
        
        # 🚨 3. 베어마켓 모드 체크
        if getattr(self, 'bear_market_mode', False):
            logger.error("🐻 베어마켓 모드 - 제한적 운영")
            self._execute_bear_market_mode()
            return

        # 🔥 4. 매매 시작 전 전체 동기화 체크
        if not hasattr(self, 'last_full_sync_time'):
            self.last_full_sync_time = datetime.now()
            self.sync_all_positions_with_broker()
        else:
            time_diff = (datetime.now() - self.last_full_sync_time).total_seconds()
            if time_diff > 1800:  # 30분마다
                logger.info("🔄 정기 전체 포지션 동기화 실행")
                self.sync_all_positions_with_broker()
                self.last_full_sync_time = datetime.now()
        
        # 🔥 5. 미체결 주문 자동 관리
        self.check_and_manage_pending_orders()
        
        # 🔥 6. 동적 예산 업데이트
        self.update_budget()

        # 🔥 7. 전역 비상 정지 체크
        emergency_stop, emergency_reason = self.check_emergency_stop_conditions()
        if emergency_stop:
            logger.error(f"🚨 전역 비상 정지: {emergency_reason}")
            
            if config.config.get("use_discord_alert", True):
                emergency_msg = f"🚨 **전역 비상 정지 발동** 🚨\n"
                emergency_msg += f"📊 정지 사유: {emergency_reason}\n"
                emergency_msg += f"🛑 모든 자동 매매 활동 중단\n"
                emergency_msg += f"🔧 수동 확인 및 설정 조정 필요"
                #discord_alert.SendMessage(emergency_msg)
            
            return  # 모든 매매 중단

        # 🔥🔥🔥 핵심 개선: 매도/매수 분리 처리 🔥🔥🔥
        
        # 현재 시장 상황 캐싱 (성능 최적화)
        self._current_market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())
        logger.info(f"📊 현재 시장 상황: {self._current_market_timing}")
        
        target_stocks = config.target_stocks
        
        # 🔥 STEP 1: 매도 전용 루프 (매도된 종목 추적)
        sells_executed_this_cycle = {}
        logger.info("🔥 STEP 1: 매도 로직 전용 실행")
        
        for stock_code, stock_info in target_stocks.items():
            try:
                stock_name = stock_info.get('name', stock_code)
                
                # 기술적 지표 계산
                indicators = self.get_technical_indicators(stock_code)
                if not indicators:
                    logger.warning(f"❌ {stock_name} 기술적 지표 계산 실패")
                    continue
                
                # 현재 보유 정보 조회
                holdings = self.get_current_holdings(stock_code)
                
                # 종목 데이터 찾기
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if not stock_data_info:
                    continue  # 매도할 데이터가 없으면 스킵
                
                magic_data_list = stock_data_info['MagicDataList']
                
                # 🚨 보유 중일 때만 매도 로직 실행
                if holdings['amount'] > 0:
                    
                    # 🚨 적응형 손절 체크 (최우선)
                    stop_executed = self.execute_adaptive_stop_loss(stock_code, indicators, magic_data_list)
                    
                    if stop_executed:
                        logger.warning(f"🚨 {stock_name} 적응형 손절 실행 - 매도 완료")
                        sells_executed_this_cycle[stock_code] = {
                            'type': 'stop_loss',
                            'time': datetime.now(),
                            'reason': '적응형 손절'
                        }
                        continue  # 손절 실행되면 다른 매도 로직 스킵
                    
                    # 🔥 손절되지 않은 경우에만 수익 매도 로직 실행
                    sells_executed = self.process_enhanced_selling_logic(
                        stock_code, stock_info, stock_data_info['MagicDataList'], indicators, holdings
                    )
                    
                    if sells_executed:
                        logger.info(f"💰 {stock_name} 수익 매도 완료")
                        sells_executed_this_cycle[stock_code] = {
                            'type': 'profit_taking',
                            'time': datetime.now(),
                            'reason': '수익 확정'
                        }
                        self.save_split_data()
                        
                        # 🔥🔥🔥 매도 즉시 강제 쿨다운 설정 🔥🔥🔥
                        if not hasattr(self, 'last_sell_time'):
                            self.last_sell_time = {}
                        if not hasattr(self, 'last_sell_info'):
                            self.last_sell_info = {}
                        
                        self.last_sell_time[stock_code] = datetime.now()
                        self.last_sell_info[stock_code] = {
                            'amount': holdings['amount'],
                            'price': indicators['current_price'],
                            'timestamp': datetime.now(),
                            'type': 'profit_taking'
                        }
                        
                        logger.info(f"🕐 {stock_name} 매도 완료 - 강제 쿨다운 설정 ({datetime.now()})")
                    
            except Exception as e:
                logger.error(f"❌ {stock_code} 매도 처리 중 오류: {str(e)}")
        
        # 🔥 STEP 2: 매수 전용 루프 (매도된 종목 완전 제외)
        logger.info("🔥 STEP 2: 매수 로직 전용 실행")
        
        if sells_executed_this_cycle:
            excluded_stocks = list(sells_executed_this_cycle.keys())
            logger.info(f"🚫 이번 사이클 매도된 종목 매수 제외: {excluded_stocks}")
        
        for stock_code, stock_info in target_stocks.items():
            try:
                stock_name = stock_info.get('name', stock_code)
                
                # 🔥🔥🔥 핵심: 이번 사이클에서 매도된 종목은 완전 제외 🔥🔥🔥
                if stock_code in sells_executed_this_cycle:
                    sell_info = sells_executed_this_cycle[stock_code]
                    logger.info(f"🚫 {stock_name} 매수 제외: 이번 사이클 {sell_info['reason']} 실행됨")
                    continue
                
                # 🔥 쿨다운 체크 (강화된 버전)
                if not self.check_enhanced_cooldown(stock_code):
                    logger.info(f"⏳ {stock_name} 쿨다운 중 - 매수 스킵")
                    continue
                
                # 기술적 지표 계산
                indicators = self.get_technical_indicators(stock_code)
                if not indicators:
                    logger.warning(f"❌ {stock_name} 기술적 지표 계산 실패")
                    continue
                
                # 현재 보유 정보 조회
                holdings = self.get_current_holdings(stock_code)
                
                # 종목 데이터 찾기/생성
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                # 종목 데이터가 없으면 새로 생성 (기존 로직)
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
                        'StockName': stock_name,
                        'IsReady': True,
                        'MagicDataList': magic_data_list,
                        'RealizedPNL': 0,
                        'MonthlyPNL': {},
                        'max_profit': 0
                    }
                    
                    self.split_data_list.append(stock_data_info)
                    self.save_split_data()
                    
                    msg = f"🎯 {stock_name} 적응형 손절 시스템 통합 스마트스플릿 준비 완료!!"
                    logger.info(msg)
                    if config.config.get("use_discord_alert", True):
                        discord_alert.SendMessage(msg)
                
                magic_data_list = stock_data_info['MagicDataList']
                
                # 🎯 매수 로직 실행
                total_budget = self.total_money * stock_info['weight']
                buy_executed_this_cycle = False
                
                for i, magic_data in enumerate(magic_data_list):
                    if not magic_data['IsBuy']:  # 해당 차수가 매수되지 않은 경우
                        
                        position_num = i + 1
                        
                        # 🔥 순차 진입 검증 (2차수부터 적용)
                        if position_num > 1:
                            sequential_ok, sequential_reason = self.check_sequential_entry_validation(
                                stock_code, position_num, indicators
                            )
                            
                            if not sequential_ok:
                                logger.info(f"🚫 {stock_name} {position_num}차 순차 검증 실패: {sequential_reason}")
                                continue
                        
                        # 🔥 매수 조건 판단
                        should_buy, buy_reason = self.should_buy_enhanced(
                            stock_code, position_num, indicators, magic_data_list, stock_info
                        )
                        
                        if should_buy:
                            # 투자 비중 설정 (역피라미드)
                            if position_num == 1:
                                investment_ratio = 0.15
                            elif position_num == 2:
                                investment_ratio = 0.18
                            elif position_num == 3:
                                investment_ratio = 0.22
                            elif position_num == 4:
                                investment_ratio = 0.25
                            else:  # 5차수
                                investment_ratio = 0.20
                            
                            # 매수 실행
                            invest_amount = total_budget * investment_ratio
                            buy_amt = max(1, int(invest_amount / indicators['current_price']))
                            
                            estimated_fee = self.calculate_trading_fee(indicators['current_price'], buy_amt, True)
                            total_cost = (indicators['current_price'] * buy_amt) + estimated_fee
                            
                            balance = KisKR.GetBalance()
                            remain_money = float(balance.get('RemainMoney', 0))
                            
                            logger.info(f"💰 {stock_name} {position_num}차 매수 시도:")
                            logger.info(f"   필요 자금: {total_cost:,.0f}원, 보유 현금: {remain_money:,.0f}원")
                            logger.info(f"   매수 이유: {buy_reason}")
                            
                            if total_cost <= remain_money:
                                # 개선된 매수 처리
                                actual_price, executed_amount, message = self.handle_buy_with_execution_tracking(
                                    stock_code, buy_amt, indicators['current_price']
                                )
                                
                                if actual_price and executed_amount:
                                    # 데이터 업데이트
                                    backup_data = {
                                        'IsBuy': magic_data['IsBuy'],
                                        'EntryPrice': magic_data['EntryPrice'],
                                        'EntryAmt': magic_data['EntryAmt'],
                                        'CurrentAmt': magic_data['CurrentAmt'],
                                        'EntryDate': magic_data['EntryDate']
                                    }
                                    
                                    try:
                                        magic_data['IsBuy'] = True
                                        magic_data['EntryPrice'] = actual_price
                                        magic_data['EntryAmt'] = executed_amount
                                        magic_data['CurrentAmt'] = executed_amount
                                        magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                        
                                        self.save_split_data()
                                        
                                        # 🔥 성공 메시지
                                        msg = f"🚀 {stock_name} {position_num}차 매수 완료!\n"
                                        msg += f"  💰 {actual_price:,.0f}원 × {executed_amount:,}주\n"
                                        msg += f"  📊 투자비중: {investment_ratio*100:.1f}%\n"
                                        msg += f"  🎯 {buy_reason}\n"
                                        
                                        # 적응형 손절선 안내
                                        current_positions = sum([1 for md in magic_data_list if md['IsBuy']])
                                        stop_threshold, threshold_desc = self.calculate_adaptive_stop_loss_threshold(
                                            stock_code, current_positions, 0
                                        )
                                        
                                        if stop_threshold:
                                            msg += f"  🛡️ 적응형 손절선: {stop_threshold*100:.1f}%\n"
                                            msg += f"     ({threshold_desc.split('(')[0].strip()})\n"
                                        
                                        msg += f"  🔥 매도 후 재매수 방지 시스템 적용"
                                        
                                        logger.info(msg)
                                        if config.config.get("use_discord_alert", True):
                                            discord_alert.SendMessage(msg)
                                        
                                        buy_executed_this_cycle = True
                                        break
                                        
                                    except Exception as update_e:
                                        # 롤백
                                        logger.error(f"❌ {stock_name} {position_num}차 데이터 업데이트 중 오류: {str(update_e)}")
                                        
                                        magic_data['IsBuy'] = backup_data['IsBuy']
                                        magic_data['EntryPrice'] = backup_data['EntryPrice']
                                        magic_data['EntryAmt'] = backup_data['EntryAmt']
                                        magic_data['CurrentAmt'] = backup_data['CurrentAmt']
                                        magic_data['EntryDate'] = backup_data['EntryDate']
                                        
                                        logger.warning(f"🔄 {stock_name} {position_num}차 업데이트 오류 롤백 완료")
                                        continue
                                
                                else:
                                    logger.warning(f"❌ {stock_name} {position_num}차 매수 실패: {message}")
                            
                            else:
                                logger.warning(f"❌ {stock_name} {position_num}차 매수 자금 부족")
                    
            except Exception as e:
                logger.error(f"❌ {stock_code} 매수 처리 중 오류: {str(e)}")
        
        # 🔥 STEP 3: 사이클 완료 처리
        if sells_executed_this_cycle:
            logger.info(f"📊 이번 사이클 매도 완료: {len(sells_executed_this_cycle)}개 종목")
            for stock_code, sell_info in sells_executed_this_cycle.items():
                stock_name = target_stocks[stock_code].get('name', stock_code)
                logger.info(f"   • {stock_name}: {sell_info['reason']} ({sell_info['time']})")
        
        # 처리 완료 후 캐시 정리
        if hasattr(self, '_current_market_timing'):
            delattr(self, '_current_market_timing')
        
        # 일일 손절 횟수 리셋 (자정에)
        current_date = datetime.now().strftime("%Y-%m-%d")
        if hasattr(self, 'last_stop_date') and self.last_stop_date != current_date:
            if hasattr(self, 'daily_stop_count'):
                self.daily_stop_count = 0
            logger.info("🔄 일일 손절 카운터 리셋")

    def should_buy_enhanced(self, stock_code, position_num, indicators, magic_data_list, stock_info):
        """🔥 하락 보호가 통합된 최적화된 매수 조건 - 기존 로직 + 개선사항 + 하락 보호 + 외국인/기관 분석"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🚨🚨🚨 최우선: 하락 보호 시스템 체크 🚨🚨🚨
            
            # 🚨 1. 전체 매수 중단 체크 (크래시 수준)
            if getattr(self, 'suspend_all_buys', False):
                return False, "🚫 하락 보호: 크래시 수준으로 전체 매수 중단"
            
            # 🚨 2. 베어마켓 모드 체크
            if getattr(self, 'bear_market_mode', False):
                return False, "🐻 베어마켓 모드: 신규 포지션 금지"
            
            # 🚨 3. 신규 진입 연기 체크 (변동성 스파이크)
            defer_hours = getattr(self, 'defer_new_entries_hours', 0)
            if defer_hours > 0:
                if not hasattr(self, 'last_defer_time'):
                    self.last_defer_time = datetime.now()
                
                hours_passed = (datetime.now() - self.last_defer_time).total_seconds() / 3600
                if hours_passed < defer_hours:
                    return False, f"⚡ 변동성 보호: {defer_hours-hours_passed:.1f}시간 진입 연기"
                else:
                    # 연기 해제
                    self.defer_new_entries_hours = 0
                    logger.info(f"✅ {stock_name} 변동성 보호 연기 해제")
            
            # 🚨 4. 차수 제한 체크 (하락 보호 단계별)
            max_positions = getattr(self, 'max_positions_allowed', 5)
            if position_num > max_positions:
                protection_level = getattr(self, 'current_protection_level', 'normal')
                return False, f"🛡️ 하락 보호({protection_level}): {max_positions}차수 초과 매수 제한"
            
            # 🚨 5. 고위험 종목 고차수 매수 제한
            if getattr(self, 'disable_high_risk_stocks', False):
                if stock_info.get('stock_type') == 'high_volatility' and position_num >= 4:
                    return False, f"⚠️ 하락 보호: 고위험 종목({stock_info.get('stock_type')}) 고차수 제한"
            
            # 🚨 6. 매수량 조정 상태 확인 및 로깅
            position_multiplier = getattr(self, 'position_size_multiplier', 1.0)
            if position_multiplier < 1.0:
                logger.info(f"💰 {stock_name} 하락 보호 매수량 조정: {position_multiplier*100:.0f}% 적용 예정")
            
            # # 🔥🔥🔥 외국인/기관 매매동향 체크 (모든 차수에 적용!) 🔥🔥🔥
            # if FI_ANALYZER_AVAILABLE:
            #     try:
            #         fi_analysis = trading_trend_analyzer.calculate_combined_trading_signal(stock_code)
                    
            #         # 외국인/기관 강한 매도 시 매수 차단
            #         if (fi_analysis['direction'] == 'bearish' and 
            #             fi_analysis['signal_strength'] in ['STRONG', 'MODERATE']):
                        
            #             # 차수별 차등 적용
            #             if position_num <= 2:  # 1-2차는 엄격
            #                 return False, f"🚫 외국인/기관 {fi_analysis['signal_strength'].lower()} 매도로 {position_num}차 진입 보류"
            #             elif position_num <= 3 and fi_analysis['signal_strength'] == 'STRONG':
            #                 return False, f"🚫 외국인/기관 강한 매도로 3차 진입 보류"
            #             # 4-5차는 가격 메리트로 진입 허용
                    
            #         # 외국인/기관 강한 매수 시 추가 로깅
            #         elif (fi_analysis['direction'] == 'bullish' and 
            #             fi_analysis['signal_strength'] in ['STRONG', 'MODERATE']):
            #             logger.info(f"💰 {stock_name} {position_num}차: 외국인/기관 {fi_analysis['signal_strength'].lower()} 매수흐름 감지")
                    
            #         # 중립일 때도 로깅 (디버깅용)
            #         else:
            #             logger.debug(f"🔄 {stock_name} {position_num}차: 외국인/기관 중립({fi_analysis['direction']}, {fi_analysis['signal_strength']})")
                        
            #     except Exception as fi_error:
            #         logger.warning(f"⚠️ 외국인/기관 분석 오류 ({stock_code}): {str(fi_error)}")
            
            # 🔥🔥🔥 기존 매수 조건 로직 (기존 코드 유지) 🔥🔥🔥
            
            # 🔥 1. 기본 안전 조건 체크 (기존 로직 유지)
            if indicators['current_price'] <= 0:
                return False, "현재가 정보 없음"
            
            # 🔥 2. RSI 범위 체크 (기존 핵심 로직)
            if not (15 <= indicators['rsi'] <= 90):
                return False, f"RSI 범위 벗어남({indicators['rsi']:.1f})"
            
            # 🔥 3. 종목별 차별화된 조건 (기존 개선사항)
            # rsi_limits = {
            #     "042660": 75,  # 한화오션: 유지
            #     "034020": 75,  # ⭐ 두산에너빌리티: 조정 구간 활용 (65→75)
            #     "005930": 72   # 삼성전자: 유지
            # }

            rsi_limits = {
                "005930": 72,   # 삼성전자: 블루칩 안정성
                "007660": 75,   # 이수페타시스: 고변동성
                "403870": 75    # HPSP: 고변동성
            }

            # pullback_requirements = {
            #     "042660": 3.0,  # 한화오션: 유지
            #     "034020": 1.2,  # ⭐ 두산에너빌리티: 진입 장벽 낮춤 (2.0→1.2)
            #     "005930": 1.8   # 삼성전자: 유지
            # }

            pullback_requirements = {
                "005930": 1.8,  # 삼성전자: 낮은 조정 요구 (안정성)
                "007660": 3.0,  # 이수페타시스: 높은 조정 요구 (고변동성)
                "403870": 3.0   # HPSP: 높은 조정 요구 (고변동성)
            }            

            max_rsi = rsi_limits.get(stock_code, 70)
            min_pullback = pullback_requirements.get(stock_code, 2.5)
            
            # 🚨 하락 보호 상태에서 조건 완화 적용
            protection_level = getattr(self, 'current_protection_level', 'normal')
            if protection_level in ['downtrend', 'strong_downtrend']:
                # 하락장에서는 진입 조건 완화
                max_rsi += 5  # RSI 5pt 완화
                min_pullback *= 0.8  # 조정 요구 20% 완화
                logger.info(f"🛡️ {stock_name} 하락장 조건 완화: RSI {max_rsi}, 조정요구 {min_pullback:.1f}%")
            
            # 🔥 4. 차수별 조건 체크
            if position_num == 1:
                # 1차수: 조정률 기반 진입 (기존 로직 + 개선)
                if indicators['pullback_from_high'] < min_pullback:
                    return False, f"조정률 부족({indicators['pullback_from_high']:.1f}% < {min_pullback:.1f}%)"
                
                if indicators['rsi'] > max_rsi:
                    return False, f"RSI 과매수({indicators['rsi']:.1f} > {max_rsi})"
                
                # 🚨 하락 보호 상태 안내
                protection_msg = ""
                if position_multiplier < 1.0:
                    protection_msg = f" [하락보호: 매수량 {position_multiplier*100:.0f}%]"
                
                return True, f"1차 최적화 진입(조정률 {indicators['pullback_from_high']:.1f}%, RSI {indicators['rsi']:.1f}){protection_msg}"
                
            else:
                # 2-5차수: 순차 진입 검증은 이미 통과했으므로 추가 조건만 체크
                
                # 🔥 차수가 높을수록 RSI 조건 완화 (기존 개선)
                adjusted_max_rsi = max_rsi + (position_num - 2) * 2  # 차수당 2pt씩 완화
                
                if indicators['rsi'] > adjusted_max_rsi:
                    return False, f"RSI 과매수({indicators['rsi']:.1f} > {adjusted_max_rsi})"
                
                # 🔥 5. 시장 상황별 추가 제한 (기존 핵심 로직 + 하락 보호 통합)
                market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())

                # 🚨 하락 보호 상태에서는 시장 제한 완화
                if protection_level not in ['downtrend', 'strong_downtrend']:
                    # 정상 상태에서만 기존 제한 적용
                    if market_timing == "strong_uptrend" and position_num >= 4:
                        return False, f"강한 상승장에서 {position_num}차수 제한"
                    
                    if market_timing == "uptrend" and position_num >= 5:
                        return False, f"상승장에서 5차수 제한"
                else:
                    # 하락장에서는 고차수 진입 허용 (기회!)
                    logger.info(f"🛡️ {stock_name} 하락장 고차수 진입 허용: {position_num}차")
                
                # 🚨 하락 보호 상태 안내
                protection_msg = ""
                if position_multiplier < 1.0:
                    protection_msg = f" [하락보호: 매수량 {position_multiplier*100:.0f}%]"
                if protection_level != 'normal':
                    protection_msg += f" [보호수준: {protection_level}]"

                return True, f"{position_num}차 최적화 진입(순차 검증 통과, RSI {indicators['rsi']:.1f}, 시장: {market_timing}){protection_msg}"
            
        except Exception as e:
            logger.error(f"하락 보호 통합 매수 조건 판단 중 오류: {str(e)}")
            return False, f"판단 오류: {str(e)}"

################################### 🔥 거래 시간 체크 및 메인 실행 ##################################

def check_trading_time():
    """장중 거래 가능한 시간대인지 체크하고 장 시작 시점도 확인 - 기존 버전 방식 적용"""
    try:
        # 🔥 1. 휴장일 체크 (가장 먼저!)
        if KisKR.IsTodayOpenCheck() == 'N':
            logger.info("휴장일 입니다.")
            return False, False

        # 🔥 2. 장 상태 확인 (실제 KIS API 활용)
        market_status = KisKR.MarketStatus()
        if market_status is None or not isinstance(market_status, dict):
            logger.info("장 상태 확인 실패")
            return False, False
            
        status_code = market_status.get('Status', '')
        
        # 🔥 3. 장 시작 시점 체크
        current_time = datetime.now().time()
        is_market_start = (status_code == '0' and current_time.hour == 8)
        
        # 🔥 4. 거래 가능 시간 체크
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
        
        if status_code:  # 상태가 있을 때만 로깅
            logger.info(f"장 상태: {status_desc.get(status_code, '알 수 없음')} (코드: {status_code})")
        
        return is_trading_time, is_market_start
        
    except Exception as e:
        logger.error(f"거래 시간 체크 중 에러 발생: {str(e)}")
        return False, False

################################### 🔥 메인 실행 함수 ##################################
def run_bot():
    """개선된 봇 실행 함수 - 장외시간 체크 추가"""
    try:
        # 🔥 실행 전 장중시간 재확인 (이중 안전장치)
        is_trading_time, _ = check_trading_time()
        if not is_trading_time:
            logger.debug("⏰ run_bot 호출되었으나 장외시간 - 실행 스킵")
            return
        
        # 🔥 전역 봇 인스턴스 사용 (싱글톤 패턴)
        global bot_instance
        if bot_instance is None:
            bot_instance = SmartMagicSplit()
            logger.info("🤖 개선된 봇 인스턴스 생성")
        
        # 🔥 시작 시 예산 및 종목 정보 출력 (처음에만)
        if not hasattr(run_bot, 'first_run_logged'):
            logger.info(f"🚀 개선된 스마트 매직 스플릿 봇 실행!")
            logger.info(f"💰 현재 예산: {bot_instance.total_money:,.0f}원")
            
            target_stocks = config.target_stocks
            logger.info(f"🎯 한국주식 타겟 종목 현황 (개선된 버전):")
            
            for stock_code, stock_config in target_stocks.items():
                weight = stock_config.get('weight', 0)
                allocated_budget = bot_instance.total_money * weight
                stock_type = stock_config.get('stock_type', 'normal')
                cooldown_hours = stock_config.get('reentry_cooldown_base_hours', 6)
                min_pullback = stock_config.get('min_pullback_for_reentry', 2.5)
                
                logger.info(f"  - {stock_config['name']}({stock_code}):")
                logger.info(f"    💰 비중 {weight*100:.1f}% ({allocated_budget:,.0f}원)")
                logger.info(f"    🎯 타입: {stock_type}")
                logger.info(f"    🕐 쿨다운: {cooldown_hours}시간")
                logger.info(f"    📉 조정요구: {min_pullback}%")
            
            # 🔥 개선된 기능 활성화 상태 출력
            enhanced_control = config.enhanced_buy_control
            logger.info(f"🔥 개선된 기능 활성화 상태:")
            logger.info(f"  - 적응형 쿨다운: {'✅' if enhanced_control.get('enable_adaptive_cooldown', True) else '❌'}")
            logger.info(f"  - 순차 진입 검증: {'✅' if enhanced_control.get('enable_sequential_validation', True) else '❌'}")
            logger.info(f"  - 개선된 주문 추적: {'✅' if enhanced_control.get('enable_enhanced_order_tracking', True) else '❌'}")
            logger.info(f"  - 브로커 동기화: {'✅' if enhanced_control.get('enable_broker_sync', True) else '❌'}")
            
            run_bot.first_run_logged = True
        
        # 매매 로직 실행
        bot_instance.process_trading()
        
    except Exception as e:
        logger.error(f"봇 실행 중 오류 발생: {str(e)}")
        # run_bot 내부 오류는 상위에서 처리하도록 다시 raise
        raise e

def send_startup_message():
   """개선된 시작 메시지 전송"""
   try:
       target_stocks = config.target_stocks
       
       msg = "🚀 개선된 스마트 매직 스플릿 봇 시작!\n"
       msg += "=" * 40 + "\n"
       msg += f"💰 설정 예산: {config.absolute_budget:,.0f}원\n"
       msg += f"🔥 버전: Enhanced 2.0 - 한국주식 특화\n\n"
       
       msg += f"🎯 타겟 종목 ({len(target_stocks)}개):\n"
       for stock_code, stock_config in target_stocks.items():
           weight = stock_config.get('weight', 0)
           stock_type = stock_config.get('stock_type', 'normal')
           cooldown_hours = stock_config.get('reentry_cooldown_base_hours', 6)
           msg += f"• {stock_config['name']}({stock_code}): {weight*100:.1f}% 비중\n"
           msg += f"  └─ {stock_type} 타입, 쿨다운 {cooldown_hours}시간\n"
       
       msg += f"\n🔥 주요 개선사항:\n"
       msg += f"• 적응형 쿨다운: 매도 후 즉시 재매수 방지\n"
       msg += f"• 순차 진입 검증: 이전 차수 보유 + 하락률 필수\n"
       msg += f"• 개선된 주문 추적: 실제 체결량 정확 계산\n"
       msg += f"• 브로커 동기화: 30분마다 데이터 일치 확인\n"
       msg += f"• 한국주식 특화: 삼성전자, 한화오션 최적화\n\n"
       
       msg += f"⚙️ 주요 설정:\n"
       msg += f"• 분할 수: {config.config.get('div_num', 5)}차수\n"
       msg += f"• 수수료: 0.015% + 세금 0.23%\n"
       msg += f"• 거래시간: 09:00-15:30 KST\n\n"
       
       msg += f"🚨 핵심 해결 문제:\n"
       msg += f"• 한화오션 매도 직후 재매수 → 쿨다운으로 완전 차단\n"
       msg += f"• 아무때나 차수 진입 → 순차 검증으로 강제 순서\n"
       msg += f"• 브로커-봇 데이터 불일치 → 실시간 동기화\n"
       msg += f"• 매수 후 체결 불확실 → 90초간 실제 체결 추적\n\n"
       
       msg += f"⚠️ 주의: 기존 봇과 동시 실행 절대 금지!"
       
       logger.info(msg)
       if config.config.get("use_discord_alert", True):
           discord_alert.SendMessage(msg)
           
   except Exception as e:
       logger.error(f"시작 메시지 전송 중 오류: {str(e)}")

def send_enhanced_performance_report():
   """개선된 일일 성과 보고서"""
   try:
       if not hasattr(globals(), 'bot_instance') or bot_instance is None:
           return
           
       logger.info("📊 개선된 성과 보고서 생성 시작")
       
       # 성과 요약 정보 가져오기
       performance = bot_instance.get_performance_summary()
       
       if not performance:
           logger.error("성과 정보 조회 실패")
           return
       
       # 오늘 날짜
       today_korean = datetime.now().strftime("%Y년 %m월 %d일")
       
       # 🔥 개선된 보고서 생성
       report = f"📊 **개선된 일일 성과 보고서** ({today_korean})\n"
       report += "=" * 50 + "\n\n"
       
       # 💰 전체 자산 현황
       current_total = performance.get('current_total', 0)
       initial_asset = performance.get('initial_asset', 0)
       total_change = performance.get('total_change', 0)
       total_change_pct = performance.get('total_change_pct', 0)
       remain_money = performance.get('remain_money', 0)
       
       report += f"💰 **전체 자산 현황**\n"
       report += f"```\n"
       report += f"현재 총자산: {current_total:,.0f}원\n"
       report += f"초기 자산:   {initial_asset:,.0f}원\n"
       report += f"손익:       {total_change:+,.0f}원 ({total_change_pct:+.2f}%)\n"
       report += f"현금 잔고:   {remain_money:,.0f}원\n"
       report += f"투자 비율:   {((current_total-remain_money)/current_total*100):.1f}%\n"
       report += f"```\n\n"
       
       # 📊 개선된 성과 지표
       enhanced_metrics = performance.get('enhanced_metrics', {})
       cooldown_prevented = enhanced_metrics.get('cooldown_prevented_buys', 0)
       sequential_blocked = enhanced_metrics.get('sequential_blocked_buys', 0)
       sync_corrections = enhanced_metrics.get('broker_sync_corrections', 0)
       
       if cooldown_prevented > 0 or sequential_blocked > 0 or sync_corrections > 0:
           report += f"🔥 **개선된 기능 성과**\n"
           if cooldown_prevented > 0:
               report += f"🕐 적응형 쿨다운 방지: {cooldown_prevented}회\n"
           if sequential_blocked > 0:
               report += f"🔗 순차 검증 차단: {sequential_blocked}회\n"
           if sync_corrections > 0:
               report += f"🔄 브로커 동기화 수정: {sync_corrections}회\n"
           report += "\n"
       
       # 📈 종목별 현황
       target_stocks = config.target_stocks
       report += f"📈 **종목별 현황**\n"
       
       for stock_code, stock_config in target_stocks.items():
           holdings = bot_instance.get_current_holdings(stock_code)
           stock_name = stock_config.get('name', stock_code)
           
           if holdings['amount'] > 0:
               current_price = KisKR.GetCurrentPrice(stock_code)
               revenue_rate = holdings.get('revenue_rate', 0)
               revenue_money = holdings.get('revenue_money', 0)
               
               report += f"📊 **{stock_name}** ({stock_code})\n"
               report += f"   💼 보유: {holdings['amount']:,}주 @ {holdings['avg_price']:,.0f}원\n"
               report += f"   💲 현재가: {current_price:,.0f}원\n"
               report += f"   📈 수익률: {revenue_rate:+.2f}%\n"
               report += f"   💰 평가손익: {revenue_money:+,.0f}원\n"
           else:
               report += f"⭕ **{stock_name}** ({stock_code}): 미보유\n"
           
           report += "\n"
       
       # 📋 손익 요약
       realized_pnl = performance.get('realized_pnl', 0)
       unrealized_pnl = performance.get('unrealized_pnl', 0)
       total_pnl = performance.get('total_pnl', 0)
       
       report += f"📋 **손익 요약**\n"
       report += f"```\n"
       report += f"실현 손익:   {realized_pnl:+,.0f}원\n"
       report += f"미실현손익:  {unrealized_pnl:+,.0f}원\n"
       report += f"총 손익:     {total_pnl:+,.0f}원\n"
       if initial_asset > 0:
           total_return_pct = (total_pnl / initial_asset) * 100
           report += f"총 수익률:   {total_return_pct:+.2f}%\n"
       report += f"```\n\n"
       
       # 💡 내일 전망
       market_timing = bot_instance.detect_market_timing()
       market_desc = {
           "strong_uptrend": "🚀 강한 상승 추세",
           "uptrend": "📈 상승 추세", 
           "neutral": "➖ 중립",
           "downtrend": "📉 하락 추세",
           "strong_downtrend": "🔻 강한 하락 추세"
       }
       
       report += f"💡 **시장 전망**\n"
       report += f"코스피 상황: {market_desc.get(market_timing, '분석 중')}\n"
       
       if market_timing in ["downtrend", "strong_downtrend"]:
           report += f"📉 하락장 → 적응형 쿨다운 30% 단축, 기회 포착\n"
       elif market_timing in ["uptrend", "strong_uptrend"]:
           report += f"📈 상승장 → 신중한 매수, 4차수 이상 제한\n"
       
       report += f"\n🕒 보고서 생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
       report += f"\n🔥 Enhanced 2.0 with 적응형 쿨다운 + 순차 검증"
       
       # Discord 전송
       if config.config.get("use_discord_alert", True):
           discord_alert.SendMessage(report)
           logger.info("✅ 개선된 성과 보고서 전송 완료")
       else:
           logger.info("📊 개선된 성과 보고서 생성 완료 (Discord 알림 비활성화)")
           logger.info(f"\n{report}")
           
   except Exception as e:
       logger.error(f"개선된 성과 보고서 생성 중 오류: {str(e)}")
       error_msg = f"⚠️ 개선된 보고서 생성 오류\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n오류: {str(e)}"
       if config.config.get("use_discord_alert", True):
           discord_alert.SendMessage(error_msg)

################################### 🔥 스케줄링 시스템 ##################################

def setup_enhanced_schedule():
    """개선된 스케줄링 설정 - 장마감 시간 안전하게 조정"""
    try:
        # 🌅 장 시작 성과 보고서: 매일 09:00
        schedule.every().day.at("09:00").do(send_enhanced_performance_report).tag('morning_report')
        
        # 📊 장마감 성과 보고서: 15:35로 변경 (안전 마진 5분)
        schedule.every().day.at("15:35").do(send_enhanced_performance_report).tag('closing_report')
        
        # 🛡️ 확실한 장마감 보고서: 15:45 추가 (이중 안전장치)
        schedule.every().day.at("15:45").do(send_enhanced_performance_report).tag('after_closing_report')
        
        # 📈 주간 보고서: 금요일 16:00
        schedule.every().friday.at("16:00").do(send_enhanced_performance_report).tag('weekly_report')
        
        logger.info("✅ 완전히 개선된 스케줄링 설정 완료")
        logger.info("   🌅 장시작 보고서: 매일 09:00")
        logger.info("   📊 장마감 보고서: 매일 15:35 (주보고서)")
        logger.info("   🛡️ 확실한 보고서: 매일 15:45 (백업)")
        logger.info("   📈 주간 보고서: 금요일 16:00")
        
    except Exception as e:
        logger.error(f"스케줄링 설정 중 오류: {str(e)}")

################################### 🔥 메인 함수 ##################################

# 전역 봇 인스턴스 (싱글톤)
bot_instance = None

def main():
    """메인 함수 - 완전히 개선된 한국주식 봇 실행"""
    
    # 🔥 스케줄링 설정 (장마감 시간 안전하게 조정)
    setup_enhanced_schedule()
    
    # 시작 메시지 전송
    send_startup_message()
    
    # 🚨 중요: 30초마다 run_bot 실행하는 스케줄 제거
    # (장외시간에도 계속 실행되는 문제 해결)
    
    # 🔥 개선된 메인 루프
    logger.info("🔄 완전히 개선된 메인 루프 시작")
    
    # 장외시간 카운터 (로그 스팸 방지)
    after_hours_log_count = 0
    last_trading_status = None
    
    while True:
        try:
            # 📊 스케줄 체크 (장중/장외 관계없이 항상 실행)
            schedule.run_pending()
            
            # 🔥 한국 장 시간 체크
            is_trading_time, is_market_start = check_trading_time()
            
            # 🕐 장외시간 처리 (효율적 대기 + 로그 스팸 방지)
            if not is_trading_time:
                # 상태 변화시에만 로깅
                if last_trading_status != "after_hours":
                    logger.info("⏰ 장외시간 - 매매 중단, 5분 간격으로 체크")
                    after_hours_log_count = 0
                    last_trading_status = "after_hours"
                
                # 장외시간 진행 상황 (30분마다 한 번씩만 로깅)
                after_hours_log_count += 1
                if after_hours_log_count % 6 == 0:  # 5분 × 6 = 30분
                    current_time = datetime.now().strftime("%H:%M")
                    logger.info(f"💤 장외시간 대기 중 ({current_time}) - 스케줄만 체크")
                
                # 🔥 장외시간에는 5분 대기 (API 호출 최소화)
                time.sleep(300)
                continue
            
            # 🚀 장중시간 처리
            if last_trading_status != "trading":
                logger.info("🚀 장중시간 - 매매 로직 활성화")
                last_trading_status = "trading"
                after_hours_log_count = 0
            
            # 🔥 장 시작 시점 특별 처리
            if is_market_start:
                logger.info("🌅 한국 장 시작! 특별 점검 수행")
                
                # 장 시작 시 전체 동기화 강제 실행
                if bot_instance:
                    logger.info("🔄 장 시작 - 전체 포지션 동기화 실행")
                    bot_instance.sync_all_positions_with_broker()
                    
                # 장 시작 알림
                if config.config.get("use_discord_alert", True):
                    start_msg = f"🌅 **한국 장 시작!**\n"
                    start_msg += f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    start_msg += f"🤖 개선된 봇 시스템 활성화\n"
                    start_msg += f"🔄 전체 동기화 완료"
                    discord_alert.SendMessage(start_msg)
            
            # 🎯 매매 로직 실행 (장중에만)
            try:
                run_bot()
                
                # 장중에는 30초 간격으로 실행
                time.sleep(30)
                
            except Exception as trading_e:
                logger.error(f"❌ 매매 로직 실행 중 오류: {str(trading_e)}")
                
                # 매매 오류는 Discord 알림 (중요)
                if config.config.get("use_discord_alert", True):
                    trading_error_msg = f"⚠️ **매매 로직 오류**\n"
                    trading_error_msg += f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    trading_error_msg += f"오류: {str(trading_e)}\n"
                    trading_error_msg += f"🔄 30초 후 재시도"
                    discord_alert.SendMessage(trading_error_msg)
                
                # 매매 오류시에는 30초 대기 후 재시도
                time.sleep(30)
           
        except KeyboardInterrupt:
            logger.info("🛑 사용자에 의한 프로그램 종료")
            
            # 종료 알림
            if config.config.get("use_discord_alert", True):
                shutdown_msg = f"🛑 **봇 수동 종료**\n"
                shutdown_msg += f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                shutdown_msg += f"사용자에 의한 정상 종료"
                discord_alert.SendMessage(shutdown_msg)
                
            break
            
        except Exception as main_e:
            logger.error(f"💥 메인 루프 중 심각한 예외 발생: {str(main_e)}")
            
            # 심각한 오류 시 상세 정보와 함께 Discord 알림
            if config.config.get("use_discord_alert", True):
                import traceback
                error_detail = traceback.format_exc()
                
                error_msg = f"🚨 **메인 루프 심각한 오류**\n"
                error_msg += f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                error_msg += f"오류: {str(main_e)}\n"
                error_msg += f"🔄 10초 후 재시작 시도\n"
                error_msg += f"```\n{error_detail[-500:]}```"  # 마지막 500자만
                discord_alert.SendMessage(error_msg)
            
            # 심각한 오류시에는 10초 대기 (빈번한 재시작 방지)
            time.sleep(10)

if __name__ == "__main__":
   main()




