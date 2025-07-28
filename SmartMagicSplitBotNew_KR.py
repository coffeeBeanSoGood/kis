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
logger = logging.getLogger('SmartMagicSplitEnhancedLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'smart_magic_split.log')
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

################################### 통합된 설정 관리 시스템 ##################################

# 🔥 API 초기화 (가장 먼저!)
Common.SetChangeMode()
logger.info("✅ API 초기화 완료 - 모든 KIS API 사용 가능")

class SmartSplitConfig:
    """스마트 스플릿 설정 관리 클래스 - 개선된 버전"""
    
    def __init__(self, config_path: str = "smart_split_config_enhanced.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()


    def get_default_config(self):
        """기본 설정값 반환 - 🔥 3종목 분산투자 + 하락률 완화 + 적응형 손절 시스템이 통합된 개선된 한국주식 버전"""
        # 🎯 종목타입별 개선된 템플릿 정의
        stock_type_templates = {
            "growth": {          # 성장주 템플릿 (개선됨)
                "period": 60,
                "recent_period": 30,
                "recent_weight": 0.7,
                "hold_profit_target": 8,
                "quick_profit_target": 5,
                "base_profit_target": 12,
                "safety_protection_ratio": 0.95,
                "time_based_sell_days": 45,
                "partial_sell_ratio": 0.25,
                "min_holding": 0,
                # 🔥 새로운 적응형 쿨다운 설정
                "reentry_cooldown_base_hours": 6,       # 기본 쿨다운 6시간
                "min_pullback_for_reentry": 2.0,        # 재진입 최소 조정률 2%
                "volatility_cooldown_multiplier": 0.5,  # 고변동성 시 50% 단축
                "market_cooldown_adjustment": True,     # 시장상황별 조정 활성화
                # 🔥 순차 진입 검증 설정
                "enable_sequential_validation": True,   # 순차 진입 검증 활성화
                "dynamic_drop_adjustment": True,        # 동적 하락률 조정
                # 🔥 매도 최적화 설정
                "uptrend_sell_ratio_multiplier": 0.6,   # 상승장 매도 비율 승수
                "high_profit_sell_reduction": True      # 고수익 시 매도량 감소
            },
            "value": {           # 가치주 템플릿 (개선됨)
                "period": 90,
                "recent_period": 45,
                "recent_weight": 0.5,
                "hold_profit_target": 7,
                "quick_profit_target": 5,
                "base_profit_target": 8,
                "safety_protection_ratio": 0.95,
                "time_based_sell_days": 60,
                "partial_sell_ratio": 0.4,
                "min_holding": 0,
                # 🔥 가치주는 더 긴 쿨다운
                "reentry_cooldown_base_hours": 8,       # 기본 8시간
                "min_pullback_for_reentry": 3.0,        # 3% 조정 요구
                "volatility_cooldown_multiplier": 0.7,  # 변동성 조정 30%
                "market_cooldown_adjustment": True,
                "enable_sequential_validation": True,
                "dynamic_drop_adjustment": True,
                "uptrend_sell_ratio_multiplier": 0.8,
                "high_profit_sell_reduction": False
            }
        }
        
        # 🔥 3종목 분산투자 설정 (한국주식)
        target_stocks_config = {
            "449450": {"weight": 0.4, "stock_type": "growth"},     # PLUS K방산 - 40%
            "042660": {"weight": 0.3, "stock_type": "growth"},     # 한화오션 - 30%
            "034020": {"weight": 0.3, "stock_type": "growth"}      # 두산에너빌리티 - 30%
        }
        
        # 종목별 정보 수집 및 설정 생성
        target_stocks = {}
        
        for stock_code, basic_config in target_stocks_config.items():
            try:
                logger.info(f"종목 정보 수집 중: {stock_code}")
                
                # 종목명 조회 시도
                stock_name = f"종목{stock_code}"  # 기본값
                stock_names = {
                    "449450": "PLUS K방산",
                    "042660": "한화오션", 
                    "034020": "두산에너빌리티"
                }
                
                try:
                    if stock_code in stock_names:
                        stock_name = stock_names[stock_code]
                        logger.info(f"종목명 설정 완료: {stock_code} → {stock_name}")
                    else:
                        stock_status = KisKR.GetCurrentStatus(stock_code)
                        if stock_status and isinstance(stock_status, dict):
                            api_name = stock_status.get("StockName", "")
                            if api_name and api_name.strip():
                                stock_name = api_name
                                logger.info(f"종목명 조회 성공: {stock_code} → {stock_name}")
                except Exception as name_e:
                    logger.warning(f"종목명 조회 API 오류: {str(name_e)} - 기본명 사용")
                
                # 현재가 조회 시도 (유효성 검증용)
                try:
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price and current_price > 0:
                        logger.info(f"현재가 확인 완료: {stock_code} = {current_price:,.0f}원")
                except Exception as price_e:
                    logger.warning(f"현재가 조회 API 오류: {str(price_e)} - 설정은 유지")
                
                # 🎯 종목타입에 따른 템플릿 자동 선택
                stock_type = basic_config["stock_type"]
                if stock_type in stock_type_templates:
                    type_template = stock_type_templates[stock_type]
                    logger.info(f"{stock_code} → {stock_type} 개선된 템플릿 적용")
                else:
                    # 정의되지 않은 타입은 growth 템플릿 사용
                    type_template = stock_type_templates["growth"]
                    logger.warning(f"{stock_code} → 정의되지 않은 타입({stock_type}), growth 템플릿 사용")
                
                # 🔥 종목별 특화 설정 (변동성 조정)
                volatility_adjustments = {
                    "449450": 0.5,  # PLUS K방산: 저변동성 → 50% 단축
                    "042660": 0.5,  # 한화오션: 고변동성 → 50% 단축  
                    "034020": 0.7   # 두산에너빌리티: 중변동성 → 70% 단축
                }
                
                if stock_code in volatility_adjustments:
                    type_template = type_template.copy()
                    type_template["volatility_cooldown_multiplier"] = volatility_adjustments[stock_code]
                    logger.info(f"{stock_code} 변동성 조정: {volatility_adjustments[stock_code]}")
                
                # 🔥 최종 종목 설정 생성 (기본 정보 + 개선된 타입별 템플릿)
                stock_config = {
                    "name": stock_name,
                    "weight": basic_config["weight"],
                    "stock_type": stock_type,
                    **type_template  # 개선된 타입별 템플릿 자동 적용
                }
                
                target_stocks[stock_code] = stock_config
                
                weight = basic_config["weight"]
                logger.info(f"✅ 종목 설정 완료: {stock_code}({stock_name})")
                logger.info(f"   📊 타입: {stock_type}, 비중: {weight*100:.1f}%")
                logger.info(f"   🕐 쿨다운: {type_template['reentry_cooldown_base_hours']}시간")
                logger.info(f"   📉 조정요구: {type_template['min_pullback_for_reentry']}%")
                logger.info(f"   🎯 변동성조정: {type_template['volatility_cooldown_multiplier']}")
                
                time.sleep(0.5)  # API 호출 간격
                
            except Exception as e:
                logger.error(f"종목 {stock_code} 처리 중 심각한 오류: {str(e)}")
                # 오류 시에도 기본 설정으로 종목 추가
                stock_type = basic_config.get("stock_type", "growth")
                type_template = stock_type_templates.get(stock_type, stock_type_templates["growth"])
                
                error_config = {
                    "name": stock_names.get(stock_code, f"종목{stock_code}"),
                    "weight": basic_config["weight"],
                    "stock_type": stock_type,
                    **type_template
                }
                target_stocks[stock_code] = error_config
                logger.info(f"🔧 오류 복구: {stock_code} 기본 설정으로 추가됨")
        
        # 🔧 비중 검증 및 로깅
        total_weight = sum(config.get('weight', 0) for config in target_stocks.values())
        logger.info(f"총 비중 합계: {total_weight:.3f}")
        
        if abs(total_weight - 1.0) > 0.001:
            logger.warning(f"⚠️ 총 비중이 1.0이 아닙니다: {total_weight:.3f}")
        else:
            logger.info("✅ 총 비중 합계 정상: 1.000")
        
        # 각 종목별 할당 예산 로깅
        budget = 1000000
        logger.info("📋 3종목 분산투자 할당 예산 및 개선된 전략:")
        for stock_code, stock_config in target_stocks.items():
            allocated = budget * stock_config['weight']
            logger.info(f"  • {stock_config['name']}({stock_code}): {stock_config['weight']*100:.1f}% → {allocated:,.0f}원")
            logger.info(f"    └─ {stock_config['stock_type']} 타입, 쿨다운 {stock_config['reentry_cooldown_base_hours']}시간")
            logger.info(f"    └─ 변동성조정: {stock_config['volatility_cooldown_multiplier']}, 조정요구: {stock_config['min_pullback_for_reentry']}%")
        
        # 🔥🔥🔥 통합된 기본 설정 반환 (3종목 분산투자 + 하락률 25% 완화 + 적응형 손절 시스템 포함) 🔥🔥🔥
        return {
            # 🔥 절대 예산 설정
            "use_absolute_budget": True,
            "absolute_budget": budget,
            "absolute_budget_strategy": "proportional",
            "initial_total_asset": 0,
            
            # 🔥 동적 조정 설정
            "performance_multiplier_range": [0.7, 1.4],
            "budget_loss_tolerance": 0.2,
            "safety_cash_ratio": 0.8,
            
            # 봇 기본 설정
            "bot_name": "SmartMagicSplitBot_Enhanced",
            "div_num": 5.0,
            
            # 🔥 개선된 매수 제어 설정
            "enhanced_buy_control": {
                "enable_adaptive_cooldown": True,           # 적응형 쿨다운 활성화
                "enable_sequential_validation": True,       # 순차 진입 검증 활성화
                "enable_enhanced_order_tracking": True,     # 개선된 주문 추적 활성화
                "enable_broker_sync": True,                 # 브로커 동기화 활성화
                "max_daily_buys_per_stock": 2,             # 종목당 일일 최대 매수
                "order_timeout_seconds": 60,                # 주문 타임아웃
                "sync_check_interval_minutes": 30           # 동기화 체크 간격
            },
            
            # 🔥 동적 하락률 요구사항 설정 (25% 완화 적용)
            "dynamic_drop_requirements": {
                "enable": True,
                "base_drops": {
                    "2": 0.045,  # 2차: 4.5% 하락 (기존 6%에서 25% 완화)
                    "3": 0.055,  # 3차: 5.5% 하락 (기존 7%에서 21% 완화)
                    "4": 0.070,  # 4차: 7.0% 하락 (기존 9%에서 22% 완화)
                    "5": 0.085   # 5차: 8.5% 하락 (기존 11%에서 23% 완화)
                },
                "adjustment_factors": {
                    "rsi_oversold_bonus": -0.01,      # RSI 과매도 시 1%p 완화
                    "market_downtrend_bonus": -0.015,  # 하락장 시 1.5%p 완화
                    "volatility_bonus": -0.005,       # 고변동성 시 0.5%p 완화
                    "rsi_overbought_penalty": 0.01,   # RSI 과매수 시 1%p 강화
                    "market_uptrend_penalty": 0.01    # 상승장 시 1%p 강화
                }
            },
            
            # 🔥🔥🔥 3종목 특화 적응형 손절 시스템 🔥🔥🔥
            "enhanced_stop_loss": {
                "enable": True,
                "description": "3종목 분산투자 한국주식 특화 적응형 손절 시스템",
                
                # 🎯 차수별 기본 손절선 (한국주식 특성 반영)
                "adaptive_thresholds": {
                    "position_1": -0.15,      # 1차수: -15% (미국 -18%보다 관대)
                    "position_2": -0.20,      # 2차수: -20% (미국 -22%보다 관대)
                    "position_3_plus": -0.25  # 3차수 이상: -25% (미국 -28%보다 관대)
                },
                
                # 🔥 한국주식 변동성 조정 (더 큰 조정폭)
                "volatility_adjustment": {
                    "high_volatility": -0.04,     # 고변동성: 4%p 완화 (한화오션 등)
                    "medium_volatility": -0.02,   # 중변동성: 2%p 완화 (두산에너빌리티)
                    "low_volatility": 0.0,        # 저변동성: 조정 없음 (PLUS K방산 등)
                    "threshold_high": 6.0,        # 한국주식 고변동성 기준: 6%
                    "threshold_medium": 3.5       # 한국주식 중변동성 기준: 3.5%
                },
                
                # ⏰ 시간 기반 손절 (한국주식 특성 고려)
                "time_based_rules": {
                    "enable": True,
                    "rules": {
                        "90_day_threshold": -0.12,   # 90일 보유시 -12% (미국보다 관대)
                        "180_day_threshold": -0.08,  # 180일 보유시 -8% (미국보다 관대)
                        "365_day_threshold": -0.05   # 1년 보유시 -5% (한국 특화)
                    }
                },
                
                # 🛡️ 비상 손절 (전체 포트폴리오 보호)
                "emergency_stop": {
                    "enable": True,
                    "total_portfolio_loss": -0.30,    # 전체 -30% 도달시 모든 거래 중단
                    "consecutive_stops": 4,           # 연속 4회 손절시 하루 휴식
                    "daily_stop_limit": 2             # 하루 최대 2회 손절
                },
                
                # 🎯 시장 상황별 조정 (한국 시장 특화)
                "market_adjustment": {
                    "enable": True,
                    "kospi_based": True,              # 코스피 기준 조정
                    "adjustments": {
                        "strong_downtrend": -0.03,   # 강한 하락장: 3%p 완화
                        "downtrend": -0.015,         # 하락장: 1.5%p 완화  
                        "neutral": 0.0,              # 중립: 조정 없음
                        "uptrend": 0.01,             # 상승장: 1%p 강화
                        "strong_uptrend": 0.02       # 강한 상승장: 2%p 강화
                    }
                },
                
                # 📊 3종목별 개별 설정 (분산투자 특화)
                "stock_specific_overrides": {
                    "449450": {  # PLUS K방산 - 대형주 특성상 엄격
                        "position_1": -0.18,     # 1차: -18%
                        "position_2": -0.23,     # 2차: -23%
                        "position_3_plus": -0.28 # 3차+: -28%
                    },
                    "042660": {  # 한화오션 - 변동성 큰 종목은 관대
                        "position_1": -0.12,     # 1차: -12%
                        "position_2": -0.17,     # 2차: -17%
                        "position_3_plus": -0.22 # 3차+: -22%
                    },
                    "034020": {  # 두산에너빌리티 - 표준 설정
                        "position_1": -0.15,     # 1차: -15%
                        "position_2": -0.20,     # 2차: -20%
                        "position_3_plus": -0.25 # 3차+: -25%
                    }
                },
                
                # 🔧 실행 옵션
                "execution_options": {
                    "partial_stop_loss": False,      # 부분 손절 비활성화 (전량만)
                    "stop_loss_reason_logging": True, # 상세 손절 사유 로깅
                    "discord_alert": True,           # Discord 손절 알림
                    "cooldown_after_stop": 24,       # 손절 후 24시간 재매수 금지
                    "data_backup_before_stop": True  # 손절 전 데이터 백업
                }
            },
            
            # 수수료 및 세금 설정
            "commission_rate": 0.00015,
            "tax_rate": 0.0023,
            "special_tax_rate": 0.0015,
            
            # 기술적 지표 설정
            "rsi_period": 14,
            "atr_period": 14,
            "pullback_rate": 5,
            "rsi_lower_bound": 30,
            "rsi_upper_bound": 78,
            "ma_short": 5,
            "ma_mid": 20,
            "ma_long": 60,
            
            # 🎯 3종목 분산투자 설정 (개선된 타입별 템플릿 자동 적용됨)
            "target_stocks": target_stocks,
            
            # 성과 추적 초기화
            "performance_tracking": {
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "best_performance": 0.0,
                "worst_performance": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "total_realized_pnl": 0.0,
                # 🔥 개선된 성과 지표
                "enhanced_metrics": {
                    "cooldown_prevented_buys": 0,     # 쿨다운으로 방지된 매수
                    "sequential_blocked_buys": 0,      # 순차검증으로 차단된 매수
                    "broker_sync_corrections": 0,      # 브로커 동기화 수정 횟수
                    "average_hold_days": 0,           # 평균 보유 일수
                    "partial_sell_count": 0,          # 부분 매도 횟수
                    "stop_loss_executions": 0,        # 🔥 새로 추가: 손절 실행 횟수
                    "emergency_stops": 0,             # 🔥 새로 추가: 비상 손절 횟수
                    "stop_loss_savings": 0.0          # 🔥 새로 추가: 손절로 방지한 추가 손실
                }
            },
            
            # 기타 설정
            "use_discord_alert": True,
            "last_config_update": datetime.now().isoformat(),
            
            # 🔥 3종목 분산투자 개선된 사용자 안내 메시지
            "_readme_enhanced": {
                "버전": "Enhanced 3.1 - 3종목 분산투자 + 하락률 균형 조정",
                "주요_개선사항": {
                    "3종목_분산투자": "PLUS K방산(40%) + 한화오션(30%) + 두산에너빌리티(30%)",
                    "적응형_쿨다운": "매도 후 즉시 재매수 방지 - 수익률/변동성/시장상황별 차등",
                    "순차_진입_검증": "이전 차수 보유 + 동적 하락률 달성 필수 확인",
                    "개선된_주문_추적": "실제 체결량 정확 계산 및 미체결 주문 자동 관리",
                    "브로커_데이터_동기화": "30분마다 브로커-내부 데이터 강제 일치",
                    "적응형_손절_시스템": "🔥 차수별 손절선 + 변동성 조정 + 시간 기반 강화",
                    "3종목_특화": "각 종목별 변동성 및 손절 특성 개별 반영",
                    "하락률_요구사항_최적화": "🆕 25% 완화로 진입 기회 증가 + 안전성 유지"
                },
                "핵심_해결_문제": {
                    "집중투자_위험": "2종목 → 3종목 분산으로 리스크 분산",
                    "재매수_문제": "매도 직후 재매수 → 쿨다운으로 방지",
                    "순차_진입": "아무때나 차수 진입 → 이전 차수 필수 + 하락률 검증",
                    "데이터_불일치": "브로커-봇 수량 차이 → 실시간 동기화로 해결",
                    "체결_추적": "매수 주문 후 불확실 → 90초간 실제 체결 확인",
                    "무한_물타기": "🔥 5차수까지 무제한 → 적응형 손절선으로 제한",
                    "장기_塩漬け": "🔥 무기한 보유 → 시간 기반 손절로 정리",
                    "최대_손실": "🔥 제한 없음 → 전체 -30% 도달시 비상 정지",
                    "진입_기회_부족": "🆕 과도한 하락률 요구 → 균형잡힌 25% 완화"
                },
                "3종목_분산투자_상세": {
                    "비중_배분": "PLUS K방산 40만원 + 한화오션 30만원 + 두산에너빌리티 30만원",
                    "섹터_다양화": "방산(K방산) + 조선(한화오션) + 에너지(두산에너빌리티)",
                    "리스크_분산": "한 종목 급락시 다른 종목으로 손실 분산",
                    "기회_확대": "3종목으로 진입 기회 3배 증가",
                    "변동성_관리": "종목별 개별 쿨다운 및 손절선 설정"
                },
                "종목별_특화_설정": {
                    "PLUS_K방산": {
                        "비중": "40% (40만원)",
                        "특성": "대형주, 저변동성",
                        "손절선": "엄격 (-18%/-23%/-28%)",
                        "쿨다운": "6시간, 50% 단축"
                    },
                    "한화오션": {
                        "비중": "30% (30만원)",
                        "특성": "중형주, 고변동성",
                        "손절선": "관대 (-12%/-17%/-22%)",
                        "쿨다운": "6시간, 50% 단축"
                    },
                    "두산에너빌리티": {
                        "비중": "30% (30만원)",
                        "특성": "대형주, 중변동성",
                        "손절선": "표준 (-15%/-20%/-25%)",
                        "쿨다운": "6시간, 70% 단축"
                    }
                },
                "예상_효과": {
                    "안정성_향상": "분산투자로 변동성 30% 감소 예상",
                    "수익_기회": "3종목 → 진입 기회 3배 증가",
                    "리스크_관리": "최대 손실을 개별 종목당 10만원으로 제한",
                    "자금_효율성": "100만원을 3종목에 최적 배분",
                    "승률_개선": "분산 효과로 전체 승률 향상 기대"
                }
            }
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
        """🔥 한국주식 적응형 손절 실행 - process_trading에 통합될 핵심 함수"""
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
            
            # 🔥 적응형 손절선 계산
            stop_threshold, threshold_desc = self.calculate_adaptive_stop_loss_threshold(
                stock_code, position_count, holding_days
            )
            
            if stop_threshold is None:
                return False  # 손절 시스템 비활성화
            
            stop_threshold_pct = stop_threshold * 100
            
            # 🔥 손절 조건 판단
            if total_return_pct <= stop_threshold_pct:
                
                logger.warning(f"🚨 {stock_name} 적응형 손절 발동!")
                logger.warning(f"   💰 평균가: {avg_entry_price:,.0f}원 → 현재가: {current_price:,.0f}원")
                logger.warning(f"   📊 손실률: {total_return_pct:.1f}% ≤ 손절선: {stop_threshold_pct:.1f}%")
                logger.warning(f"   🔢 활성차수: {position_count}개")
                logger.warning(f"   📅 보유기간: {holding_days}일")
                logger.warning(f"   🎯 {threshold_desc}")
                
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
                        'timestamp': datetime.now().isoformat()
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
                                # 손절 기록 생성
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
                                    'stop_type': 'adaptive_stop_loss'
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
                        
                        # 손절 이력 업데이트
                        today = datetime.now().strftime("%Y-%m-%d")
                        if self.last_stop_date != today:
                            self.daily_stop_count = 1
                            self.last_stop_date = today
                        else:
                            self.daily_stop_count += 1
                        
                        # 실현손익 업데이트
                        self.update_realized_pnl(stock_code, total_realized_loss)
                        
                        # 데이터 저장
                        self.save_split_data()
                        
                        # 🔥 손절 완료 알림
                        msg = f"🚨 {stock_name} 적응형 손절 완료!\n"
                        msg += f"  📊 {threshold_desc}\n"
                        msg += f"  💰 평균가: {avg_entry_price:,.0f}원 → 현재가: {current_price:,.0f}원\n"
                        msg += f"  📉 손실률: {total_return_pct:.1f}% (손절선: {stop_threshold_pct:.1f}%)\n"
                        msg += f"  🔢 총매도: {total_stop_amount}주 ({position_count}개 차수)\n"
                        msg += f"  📋 세부내역: {', '.join(position_details)}\n"
                        msg += f"  📅 보유기간: {holding_days}일\n"
                        msg += f"  💸 실현손실: {total_realized_loss:+,.0f}원\n"
                        msg += f"  🕐 일일손절: {self.daily_stop_count}회\n"
                        
                        # 🔥 쿨다운 안내
                        cooldown_hours = execution_options.get('cooldown_after_stop', 24)
                        msg += f"  ⏰ 재매수 쿨다운: {cooldown_hours}시간\n"
                        msg += f"  🔄 다음 사이클에서 새로운 1차 시작 가능"
                        
                        logger.error(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        # 🔥 손절 후 특별 쿨다운 설정
                        self.last_sell_time[stock_code] = datetime.now()
                        
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
                            
                            # 롤백 알림
                            if config.config.get("use_discord_alert", True):
                                rollback_msg = f"⚠️ {stock_name} 손절 실패 롤백\n"
                                rollback_msg += f"손절 시도했으나 오류 발생\n"
                                rollback_msg += f"데이터 자동 복구 완료\n"
                                rollback_msg += f"오류: {str(stop_e)}"
                                discord_alert.SendMessage(rollback_msg)
                        
                        except Exception as rollback_e:
                            logger.error(f"💥 {stock_name} 롤백도 실패: {str(rollback_e)}")
                    
                    return False
            
            else:
                # 손절선 미도달 - 현재 상태 로깅
                buffer = total_return_pct - stop_threshold_pct
                logger.debug(f"💎 {stock_name} 손절선 여유: {total_return_pct:.1f}% (손절선: {stop_threshold_pct:.1f}%, 여유: {buffer:+.1f}%p)")
                return False
                
        except Exception as e:
            logger.error(f"적응형 손절 실행 중 오류: {str(e)}")
            return False

    def check_stop_loss_cooldown(self, stock_code):
        """🔥 손절 후 쿨다운 체크 (기존 쿨다운과 통합)"""
        try:
            # 손절 후 특별 쿨다운 체크
            if stock_code in self.last_sell_time:
                last_sell = self.last_sell_time[stock_code]
                
                stop_config = config.config.get('enhanced_stop_loss', {})
                execution_options = stop_config.get('execution_options', {})
                cooldown_hours = execution_options.get('cooldown_after_stop', 24)
                
                hours_passed = (datetime.now() - last_sell).total_seconds() / 3600
                
                if hours_passed < cooldown_hours:
                    logger.info(f"🚫 {stock_code} 손절 후 쿨다운: {hours_passed:.1f}h/{cooldown_hours}h")
                    return False
            
            # 기존 적응형 쿨다운도 체크
            return self.check_adaptive_cooldown(stock_code)
            
        except Exception as e:
            logger.error(f"손절 쿨다운 체크 오류: {str(e)}")
            return True

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
                    else:                       # 저변동성 (PLUS K방산 등)
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
        """🔥 개선된 매수 주문 처리 - 한국주식용 체결량 정확 계산"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥 1. 매수 전 보유량 기록 (핵심 추가)
            before_holdings = self.get_current_holdings(stock_code)
            before_amount = before_holdings.get('amount', 0)
            before_avg_price = before_holdings.get('avg_price', 0)
            
            logger.info(f"📊 {stock_name} 매수 전 현황:")
            logger.info(f"   보유량: {before_amount:,}주")
            if before_avg_price > 0:
                logger.info(f"   평균가: {before_avg_price:,.0f}원")
            
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
                    if price_diff > 0 and price_change_rate > 0.03:
                        logger.warning(f"💔 {stock_name} 과도한 가격 급등으로 매수 포기")
                        return None, None, "가격 급등으로 매수 포기"
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
            if stock_code in self.pending_orders:
                pending_info = self.pending_orders[stock_code]
                order_time_str = pending_info.get('order_time', '')
                try:
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
                    
                    if elapsed_minutes < 10:
                        logger.warning(f"❌ {stock_name} 중복 주문 방지: {elapsed_minutes:.1f}분 전 주문 있음")
                        return None, None, "중복 주문 방지"
                except:
                    pass
            
            # 🔥 4. 주문 정보 기록
            order_info = {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'order_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'order_amount': amount,
                'before_amount': before_amount,
                'analysis_price': old_price,
                'order_price': actual_price,
                'price_change': actual_price - old_price,
                'status': 'submitted'
            }
            
            self.pending_orders[stock_code] = order_info
            
            # 🔥 5. 주문 전송 (한국주식: 1% 위로 지정가)
            estimated_fee = self.calculate_trading_fee(actual_price, amount, True)
            order_price = int(actual_price * 1.01)  # 한국주식은 정수 단위
            
            logger.info(f"🔵 {stock_name} 매수 주문 전송:")
            logger.info(f"   수량: {amount:,}주")
            logger.info(f"   주문가격: {order_price:,}원 (현재가 +1%)")
            logger.info(f"   예상 수수료: {estimated_fee:,.0f}원")
            
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
                        
                        # 🔥 체결 상세 정보 로깅
                        logger.info(f"✅ {stock_name} 매수 체결 완료!")
                        logger.info(f"   🎯 목표수량: {amount:,}주")
                        logger.info(f"   📊 매수 전 보유: {before_amount:,}주")
                        logger.info(f"   📊 매수 후 총보유: {current_total:,}주")
                        logger.info(f"   ✅ 실제 체결량: {actual_executed:,}주")
                        logger.info(f"   💰 주문가격: {order_price:,}원")
                        logger.info(f"   💰 체결가격: {current_avg_price:,.0f}원")
                        
                        # 가격 개선 계산
                        execution_diff = current_avg_price - order_price
                        total_investment = current_avg_price * actual_executed
                        actual_fee = self.calculate_trading_fee(current_avg_price, actual_executed, True)
                        
                        logger.info(f"   📊 가격개선: {execution_diff:+,.0f}원")
                        logger.info(f"   💵 투자금액: {total_investment:,.0f}원")
                        logger.info(f"   💸 실제수수료: {actual_fee:,.0f}원")
                        logger.info(f"   🕐 체결시간: {check_count * 3}초")
                        
                        # 체결 완료시 pending 제거
                        if stock_code in self.pending_orders:
                            del self.pending_orders[stock_code]
                        
                        # 🔥 체결 완료 Discord 알림
                        if config.config.get("use_discord_alert", True):
                            msg = f"✅ {stock_name} 매수 체결!\n"
                            msg += f"💰 {current_avg_price:,.0f}원 × {actual_executed:,}주\n"
                            msg += f"📊 투자금액: {total_investment:,.0f}원\n"
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
            
            # 미체결 알림
            if config.config.get("use_discord_alert", True):
                msg = f"⏰ {stock_name} 매수 미체결\n"
                msg += f"💰 주문: {order_price:,}원 × {amount:,}주\n"
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
            
            logger.error(f"❌ {stock_name} 매수 주문 처리 중 오류: {str(e)}")
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
        """매도 주문 처리 - 체결 확인 + 미체결 추적 포함"""
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
                        
                        # 🔥 체결 완료 Discord 알림
                        if config.config.get("use_discord_alert", True):
                            msg = f"✅ {stock_name} 매도 체결!\n"
                            msg += f"💰 {order_price:,}원 × {actual_sold:,}주\n"
                            msg += f"⚡ 체결시간: {check_count * 2}초"
                            discord_alert.SendMessage(msg)

                        # 🔥🔥🔥 바로 여기에 추가! 🔥🔥🔥
                        # 매도 완료 즉시 쿨다운 설정 (타이밍 갭 해결)
                        if not hasattr(self, 'last_sell_time'):
                            self.last_sell_time = {}
                        if not hasattr(self, 'last_sell_info'):
                            self.last_sell_info = {}

                        self.last_sell_time[stock_code] = datetime.now()
                        self.last_sell_info[stock_code] = {
                            'amount': actual_sold,
                            'price': order_price,
                            'timestamp': datetime.now(),
                            'type': 'profit_taking'
                        }

                        logger.info(f"🕐 {stock_name} 매도 완료 - 즉시 쿨다운 설정")
                        # 🔥🔥🔥 추가 끝 🔥🔥🔥
                        
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


################################### 🔥 개선된 메인 매매 로직 ##################################

    def process_improved_selling_logic(self, stock_code, stock_info, magic_data_list, indicators, holdings):
        """개선된 매도 로직 - 🚀 즉시 적용 개선사항 통합"""
        
        current_price = indicators['current_price']
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
                
                # 🚀 1순위: 빠른 수익 확정 체크
                quick_sell, quick_reason = self.check_quick_profit_opportunity(
                    stock_code, magic_data, current_price, stock_config
                )
                
                if quick_sell:
                    should_sell = True
                    sell_reason = quick_reason
                    sell_ratio = 0.5  # 50% 부분 매도 (나머지는 더 기다림)
                    logger.info(f"💰 {stock_code} {position_num}차 빠른 수익 확정: 50% 부분 매도")
                
                # 🛡️ 2순위: 안전장치 보호선 체크  
                elif max_profit_achieved > 0:
                    safety_sell, safety_reason = self.check_safety_protection(
                        stock_code, magic_data, current_price, stock_config, max_profit_achieved
                    )
                    
                    if safety_sell:
                        should_sell = True
                        sell_reason = safety_reason
                        sell_ratio = 1.0  # 안전장치는 전량 매도
                        logger.warning(f"🛡️ {stock_code} {position_num}차 안전장치 매도")
                
                # 🎯 3순위: 기본 목표가 달성 (개선된 목표)
                elif current_return >= stock_config.get('hold_profit_target', 6):
                    should_sell = True
                    sell_reason = f"목표달성({current_return:.1f}%≥{stock_config.get('hold_profit_target', 6)}%)"
                    
                    # 상승장에서는 부분 매도, 다른 상황에서는 전량 매도
                    # market_timing = self.detect_market_timing()
                    market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())                  
                    if market_timing in ["strong_uptrend", "uptrend"]:
                        sell_ratio = stock_config.get('partial_sell_ratio', 0.4)  # 40% 부분 매도
                        logger.info(f"📈 {stock_code} {position_num}차 상승장 목표 달성: {sell_ratio*100:.0f}% 부분 매도")
                    else:
                        sell_ratio = 1.0  # 전량 매도
                        logger.info(f"🎯 {stock_code} {position_num}차 목표 달성: 전량 매도")
                
                # ⏰ 4순위: 시간 기반 매도
                else:
                    time_sell, time_reason = self.check_time_based_sell(
                        stock_code, magic_data, current_price, stock_config
                    )
                    
                    if time_sell:
                        should_sell = True
                        sell_reason = time_reason
                        sell_ratio = 0.6  # 60% 매도 (장기 보유 시 적극 확정)
                        logger.info(f"⏰ {stock_code} {position_num}차 시간 기반 매도: 60% 매도")
                
                # 🔥 매도 실행
                if should_sell:
                    sell_amount = max(1, int(current_amount * sell_ratio))
                    
                    # 매도량이 보유량보다 크면 조정
                    if sell_amount > holdings['amount']:
                        sell_amount = holdings['amount']
                    
                    # 매도 주문 실행
                    result, error = self.handle_sell(stock_code, sell_amount, current_price)
                    
                    if result:
                        # 🎉 매도 성공 처리
                        magic_data['CurrentAmt'] = current_amount - sell_amount
                        
                        if magic_data['CurrentAmt'] <= 0:
                            magic_data['IsBuy'] = False
                            # 전량 매도 시 최고점 리셋
                            magic_data[max_profit_key] = 0
                        
                        # 매도 이력 기록
                        if 'SellHistory' not in magic_data:
                            magic_data['SellHistory'] = []
                        
                        # 실현 손익 계산
                        realized_pnl = (current_price - entry_price) * sell_amount
                        magic_data['SellHistory'].append({
                            "date": datetime.now().strftime("%Y-%m-%d"),     # ✅ 소문자로 변경
                            "time": datetime.now().strftime("%H:%M:%S"),     # 일관성을 위해 소문자
                            "amount": sell_amount,
                            "price": current_price,
                            "profit": realized_pnl,
                            "return_pct": current_return,                    # 소문자 + 언더스코어
                            "sell_ratio": sell_ratio,
                            "reason": sell_reason,
                            "max_profit": max_profit_achieved
                        })
                        
                        # 누적 실현 손익 업데이트
                        self.update_realized_pnl(stock_code, realized_pnl)
                        
                        # 성공 메시지
                        sell_type = "부분" if sell_ratio < 1.0 else "전량"
                        msg = f"✅ {stock_code} {position_num}차 {sell_type} 매도 완료!\n"
                        msg += f"💰 {sell_amount}주 @ {current_price:,.0f}원\n"
                        msg += f"📊 수익률: {current_return:+.2f}%\n"
                        msg += f"💵 실현손익: {realized_pnl:+,.0f}원\n"
                        msg += f"🎯 사유: {sell_reason}\n"
                        
                        if max_profit_achieved > current_return:
                            msg += f"📈 최고점: {max_profit_achieved:.1f}%에서 확정\n"
                        
                        if sell_ratio < 1.0:
                            remaining = current_amount - sell_amount
                            msg += f"💎 잔여: {remaining}주 계속 보유"
                        
                        logger.info(msg)
                        discord_alert.SendMessage(msg)
                        
                        sells_executed = True
                        
                    else:
                        logger.error(f"❌ {stock_code} {position_num}차 매도 실패: {error}")
        
        return sells_executed
        
    def log_improvement_status(self):
        """개선사항 적용 현황 로깅"""
        try:
            logger.info("🚀 개선사항 적용 현황 체크:")
            
            for stock_code, stock_config in config.target_stocks.items():
                stock_name = stock_config.get('name', stock_code)
                old_target = 12  # 기존 목표
                new_target = stock_config.get('hold_profit_target', 6)
                quick_target = stock_config.get('quick_profit_target', 4)
                
                logger.info(f"  📊 {stock_name}:")
                logger.info(f"    • 목표수익률: {old_target}% → {new_target}% ({((new_target-old_target)/old_target*100):+.0f}%)")
                logger.info(f"    • 빠른확정: {quick_target}% 옵션 추가")
                logger.info(f"    • 안전장치: 목표의 95% 보호선 추가")
                logger.info(f"    • 시간매도: {stock_config.get('time_based_sell_days', 45)}일 후 자동검토")
        
        except Exception as e:
            logger.error(f"개선 현황 로깅 오류: {str(e)}")    

    def process_trading(self):
        """🔥 적응형 손절이 통합된 매매 로직 처리"""
        
        # 🔥 1. 매매 시작 전 전체 동기화 체크
        if not hasattr(self, 'last_full_sync_time'):
            self.last_full_sync_time = datetime.now()
            self.sync_all_positions_with_broker()
        else:
            time_diff = (datetime.now() - self.last_full_sync_time).total_seconds()
            if time_diff > 1800:  # 30분마다
                logger.info("🔄 정기 전체 포지션 동기화 실행")
                self.sync_all_positions_with_broker()
                self.last_full_sync_time = datetime.now()
        
        # 🔥 2. 미체결 주문 자동 관리
        self.check_and_manage_pending_orders()
        
        # 🔥 3. 동적 예산 업데이트
        self.update_budget()

        # 🔥 4. 전역 비상 정지 체크 (새로 추가)
        emergency_stop, emergency_reason = self.check_emergency_stop_conditions()
        if emergency_stop:
            logger.error(f"🚨 전역 비상 정지: {emergency_reason}")
            
            # 비상 정지 Discord 알림
            if config.config.get("use_discord_alert", True):
                emergency_msg = f"🚨 **전역 비상 정지 발동** 🚨\n"
                emergency_msg += f"📊 정지 사유: {emergency_reason}\n"
                emergency_msg += f"🛑 모든 자동 매매 활동 중단\n"
                emergency_msg += f"🔧 수동 확인 및 설정 조정 필요"
                discord_alert.SendMessage(emergency_msg)
            
            return  # 모든 매매 중단

        # 현재 시장 상황 캐싱 (성능 최적화)
        self._current_market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())
        logger.info(f"📊 현재 시장 상황: {self._current_market_timing}")        
        
        # 각 종목별 처리
        target_stocks = config.target_stocks
        
        for stock_code, stock_info in target_stocks.items():
            try:
                stock_name = stock_info.get('name', stock_code)
                
                # 🔥 손절 후 쿨다운 체크 (최우선)
                if not self.check_adaptive_cooldown(stock_code):
                    logger.info(f"⏳ {stock_name} 쿨다운 중 - 매수 스킵")
                    continue
                
                # 기술적 지표 계산
                indicators = self.get_technical_indicators(stock_code)
                if not indicators:
                    logger.warning(f"❌ {stock_name} 기술적 지표 계산 실패")
                    continue
                
                # 현재 보유 정보 조회
                holdings = self.get_current_holdings(stock_code)
                
                # 종목 데이터 찾기/생성 (기존 로직 유지)
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
                
                # 🔥🔥🔥 핵심: 보유 중일 때 적응형 손절 먼저 체크 🔥🔥🔥
                if holdings['amount'] > 0:
                    
                    # 🚨 적응형 손절 체크 (최우선)
                    stop_executed = self.execute_adaptive_stop_loss(stock_code, indicators, magic_data_list)
                    
                    if stop_executed:
                        logger.warning(f"🚨 {stock_name} 적응형 손절 실행됨 - 이번 사이클 종료")
                        
                        # 손절 실행 후 쿨다운 설정
                        if not hasattr(self, 'last_sell_time'):
                            self.last_sell_time = {}
                        self.last_sell_time[stock_code] = datetime.now()
                        
                        continue  # 손절 실행되면 다른 로직 스킵
                    
                    # 🔥 손절되지 않은 경우에만 기존 매도 로직 실행
                    sells_executed = self.process_improved_selling_logic(
                        stock_code, stock_info, stock_data_info['MagicDataList'], indicators, holdings
                    )
                    
                    if sells_executed:
                        logger.info(f"🎯 {stock_name} 수익 매도 전략 실행 완료")
                        self.save_split_data()
                
                # 🔥 매수 로직 (기존과 유사하지만 손절 쿨다운 고려됨)
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
                        
                        # 🔥 매수 조건 판단 (기존 로직)
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
                            
                            # 매수 실행 (기존 로직)
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
                                    # 데이터 업데이트 (기존 로직)
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
                                        
                                        # 🔥 성공 메시지 (적응형 손절 안내 추가)
                                        msg = f"🚀 {stock_name} {position_num}차 매수 완료!\n"
                                        msg += f"  💰 {actual_price:,.0f}원 × {executed_amount:,}주\n"
                                        msg += f"  📊 투자비중: {investment_ratio*100:.1f}%\n"
                                        msg += f"  🎯 {buy_reason}\n"
                                        
                                        # 🔥 적응형 손절선 안내
                                        current_positions = sum([1 for md in magic_data_list if md['IsBuy']])
                                        stop_threshold, threshold_desc = self.calculate_adaptive_stop_loss_threshold(
                                            stock_code, current_positions, 0
                                        )
                                        
                                        if stop_threshold:
                                            msg += f"  🛡️ 적응형 손절선: {stop_threshold*100:.1f}%\n"
                                            msg += f"     ({threshold_desc.split('(')[0].strip()})\n"
                                        
                                        msg += f"  🔥 적응형 손절 + 순차 검증 + 쿨다운 시스템 적용"
                                        
                                        logger.info(msg)
                                        if config.config.get("use_discord_alert", True):
                                            discord_alert.SendMessage(msg)
                                        
                                        buy_executed_this_cycle = True
                                        break
                                        
                                    except Exception as update_e:
                                        # 롤백 (기존 로직)
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
                logger.error(f"{stock_code} 처리 중 오류 발생: {str(e)}")
                import traceback
                traceback.print_exc()

        # 처리 완료 후 캐시 정리
        if hasattr(self, '_current_market_timing'):
            delattr(self, '_current_market_timing')
        
        # 🔥 일일 손절 횟수 리셋 (자정에)
        current_date = datetime.now().strftime("%Y-%m-%d")
        if hasattr(self, 'last_stop_date') and self.last_stop_date != current_date:
            if hasattr(self, 'daily_stop_count'):
                self.daily_stop_count = 0
            logger.info("🔄 일일 손절 카운터 리셋")

    def should_buy_enhanced(self, stock_code, position_num, indicators, magic_data_list, stock_info):
        """🔥 개선된 매수 조건 판단 - 기존 로직 + 개선사항 통합"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            # 🔥 1. 기본 안전 조건 체크
            if indicators['current_price'] <= 0:
                return False, "현재가 정보 없음"
            
            if not (15 <= indicators['rsi'] <= 90):
                return False, f"RSI 범위 벗어남({indicators['rsi']:.1f})"
            
            # 🔥 2. 종목별 기본 매수 조건
            min_pullback = stock_info.get('min_pullback_for_reentry', 2.5)
            max_rsi = 70  # 기본값
            
            # 차수별 RSI 조건 완화
            if position_num >= 3:
                max_rsi = 75  # 3차수 이상은 RSI 완화
            
            # 🔥 3. 차수별 조건 체크
            if position_num == 1:
                # 1차수: 조정률 기반 진입
                if indicators['pullback_from_high'] < min_pullback:
                    return False, f"조정률 부족({indicators['pullback_from_high']:.1f}% < {min_pullback:.1f}%)"
                
                if indicators['rsi'] > max_rsi:
                    return False, f"RSI 과매수({indicators['rsi']:.1f} > {max_rsi})"
                
                return True, f"1차 진입 조건 충족(조정률 {indicators['pullback_from_high']:.1f}%, RSI {indicators['rsi']:.1f})"
                
            else:
                # 2-5차수: 순차 진입 검증은 이미 통과했으므로 추가 조건만 체크
                
                # RSI 과매수 체크 (차수가 높을수록 완화)
                if indicators['rsi'] > max_rsi:
                    return False, f"RSI 과매수({indicators['rsi']:.1f} > {max_rsi})"
                
                # 🔥 시장 상황별 추가 제한
                # market_timing = self.detect_market_timing()
                market_timing = getattr(self, '_current_market_timing', self.detect_market_timing())

                if market_timing == "strong_uptrend" and position_num >= 4:
                    # 강한 상승장에서는 4차수 이상 제한
                    return False, f"강한 상승장에서 {position_num}차수 제한"
                
                return True, f"{position_num}차 진입 조건 충족(순차 검증 통과, RSI {indicators['rsi']:.1f})"
            
        except Exception as e:
            logger.error(f"개선된 매수 조건 판단 중 오류: {str(e)}")
            return False, f"판단 오류: {str(e)}"

    def sync_single_stock_position(self, stock_code):
        """단일 종목 포지션 동기화"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
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
                return False
            
            # 내부 데이터 수량 계산
            internal_total = sum([
                magic_data['CurrentAmt'] for magic_data in stock_data_info['MagicDataList']
                if magic_data['IsBuy']
            ])
            
            if broker_amount != internal_total:
                logger.warning(f"🔄 {stock_name} 즉시 동기화 실행:")
                logger.warning(f"   브로커: {broker_amount:,}주 vs 내부: {internal_total:,}주")
                
                # 간단한 동기화 (첫 번째 포지션에 통합)
                magic_data_list = stock_data_info['MagicDataList']
                
                # 모든 포지션 초기화
                for magic_data in magic_data_list:
                    magic_data['CurrentAmt'] = 0
                    magic_data['IsBuy'] = False
                
                # 브로커 보유량이 있으면 첫 번째 포지션에 설정
                if broker_amount > 0:
                    first_pos = magic_data_list[0]
                    first_pos['CurrentAmt'] = broker_amount
                    first_pos['EntryPrice'] = broker_avg_price
                    first_pos['EntryAmt'] = broker_amount
                    first_pos['IsBuy'] = True
                    first_pos['EntryDate'] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                
                self.save_split_data()
                logger.info(f"✅ {stock_name} 즉시 동기화 완료")
                
                # 동기화 수정 횟수 증가
                config.update_enhanced_metrics("broker_sync_corrections", 1)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"단일 종목 동기화 중 오류: {str(e)}")
            return False

################################### 🔥 개선된 매도 시스템 ##################################

    def process_enhanced_selling(self, stock_code, indicators, magic_data_list):
        """🔥 개선된 차수별 매도 처리 - 기존 로직 + 트레일링 스톱 개선"""
        try:
            target_stocks = config.target_stocks
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            stock_info = target_stocks.get(stock_code, {})  # 🔥 이 줄 추가
            current_price = indicators['current_price']
            
            # 종목별 기본 목표 수익률
            base_target_pct = stock_info.get('hold_profit_target', 10)
            
            total_sells = 0
            sell_details = []
            
            # 🔥 각 차수별로 개별 매도 판단
            for magic_data in magic_data_list:
                if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                    
                    position_num = magic_data['Number']
                    entry_price = magic_data['EntryPrice']
                    current_amount = magic_data['CurrentAmt']
                    
                    if entry_price <= 0:
                        continue
                    
                    # 현재 수익률 계산
                    position_return_pct = (current_price - entry_price) / entry_price * 100
                    
                    # 🔥 개별 차수별 최고점 추적
                    position_max_key = f'max_profit_{position_num}'
                    if position_max_key not in magic_data:
                        magic_data[position_max_key] = 0
                    
                    # 최고점 업데이트
                    if position_return_pct > magic_data[position_max_key]:
                        magic_data[position_max_key] = position_return_pct
                        logger.info(f"📈 {stock_name} {position_num}차 최고점 갱신: {position_return_pct:.1f}%")
                    
                    current_max = magic_data[position_max_key]
                    
                    # 🔥 매도 조건 체크
                    should_sell = False
                    sell_reason = ""
                    
                    # 목표 수익률 미달성 시 홀딩
                    if position_return_pct < base_target_pct:
                        continue
                    
                    # 🔥 개선된 트레일링 스톱 (세분화)
                    if current_max >= base_target_pct:
                        
                        # 6구간 세분화 트레일링
                        if current_max >= base_target_pct * 3.0:
                            trailing_pct = 0.025  # 2.5%
                            level = "극한수익"
                        elif current_max >= base_target_pct * 2.5:
                            trailing_pct = 0.03   # 3.0%
                            level = "초고수익"
                        elif current_max >= base_target_pct * 2.0:
                            trailing_pct = 0.035  # 3.5%
                            level = "고수익"
                        elif current_max >= base_target_pct * 1.5:
                            trailing_pct = 0.04   # 4.0%
                            level = "중수익"
                        elif current_max >= base_target_pct * 1.2:
                            trailing_pct = 0.045  # 4.5%
                            level = "양호수익"
                        else:
                            trailing_pct = 0.05   # 5.0%
                            level = "목표달성"
                        
                        # 트레일링 기준가 계산
                        trailing_threshold = current_max - (trailing_pct * 100)
                        
                        # 안전장치: 목표가의 95% 보호
                        safety_threshold = base_target_pct * 0.95
                        final_threshold = max(trailing_threshold, safety_threshold)
                        
                        if position_return_pct <= final_threshold:
                            should_sell = True
                            
                            if final_threshold == safety_threshold:
                                sell_reason = f"{position_num}차 안전장치 매도 ({base_target_pct:.1f}%의 95% 보호)"
                            else:
                                sell_reason = f"{position_num}차 트레일링스톱 ({level}, 최고{current_max:.1f}%→{trailing_pct*100:.0f}%하락)"
                    
                    # 극한 상승 체크
                    if position_return_pct >= base_target_pct * 3.0:
                        should_sell = True
                        sell_reason = f"{position_num}차 극한상승 매도 ({base_target_pct*3.0:.1f}% 달성)"
                    
                    # 🔥 매도 실행
                    if should_sell:
                        logger.info(f"🚨 {stock_name} {position_num}차 매도 실행:")
                        logger.info(f"   진입가: {entry_price:,.0f}원")
                        logger.info(f"   현재가: {current_price:,.0f}원")
                        logger.info(f"   수익률: {position_return_pct:+.1f}%")
                        logger.info(f"   최고점: {current_max:.1f}%")
                        logger.info(f"   사유: {sell_reason}")
                        
                        # 매도 주문 실행
                        result, error = self.handle_sell(stock_code, current_amount, current_price)
                        
                        if result:
                            # 매도 기록 생성
                            sell_record = {
                                'date': datetime.now().strftime("%Y-%m-%d"),
                                'price': current_price,
                                'amount': current_amount,
                                'reason': sell_reason,
                                'return_pct': position_return_pct,
                                'max_profit_at_sell': current_max,
                                'target_profit_pct': base_target_pct,
                                'entry_price': entry_price
                            }
                            
                            # 데이터 업데이트
                            magic_data['SellHistory'].append(sell_record)
                            magic_data['CurrentAmt'] = 0
                            magic_data['IsBuy'] = False
                            magic_data[position_max_key] = 0  # 최고점 리셋
                            
                            # 실현손익 계산 및 업데이트
                            realized_pnl = (current_price - entry_price) * current_amount
                            sell_fee = self.calculate_trading_fee(current_price, current_amount, False)
                            net_pnl = realized_pnl - sell_fee
                            
                            self.update_realized_pnl(stock_code, net_pnl)
                            
                            total_sells += current_amount
                            sell_details.append({
                                'position': position_num,
                                'amount': current_amount,
                                'return_pct': position_return_pct,
                                'max_profit': current_max,
                                'pnl': net_pnl,
                                'reason': sell_reason
                            })
                            
                            logger.info(f"✅ {stock_name} {position_num}차 매도 완료:")
                            logger.info(f"   {current_amount:,}주 @ {current_price:,.0f}원 ({position_return_pct:+.1f}%)")
                            logger.info(f"   실현손익: {net_pnl:+,.0f}원")
            
            # 매도 완료 처리
            if total_sells > 0:
                self.save_split_data()
                
                # 🔥 매도 완료 알림
                msg = f"💰 {stock_name} 개선된 매도 완료!\n"
                msg += f"  📊 총 매도량: {total_sells:,}주 @ {current_price:,.0f}원\n"
                msg += f"  🎯 목표수익률: {base_target_pct:.1f}%\n"
                msg += f"  📋 매도된 차수:\n"
                
                total_realized = sum([detail['pnl'] for detail in sell_details])
                for detail in sell_details:
                    msg += f"    • {detail['position']}차: {detail['amount']:,}주 "
                    msg += f"({detail['return_pct']:+.1f}%, 최고:{detail['max_profit']:.1f}%)\n"
                
                msg += f"  💵 총 실현손익: {total_realized:+,.0f}원\n"
                msg += f"  🔥 개선된 트레일링 스톱 적용"
                
                logger.info(msg)
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(msg)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"개선된 차수별 매도 처리 중 오류: {str(e)}")
            return False

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
       msg += f"• 한국주식 특화: PLUS K방산, 한화오션 최적화\n\n"
       
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




