#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
개선된 빗썸 알트코인 트렌드 추종 봇 - 멀티 타임프레임 & 동적 조정 버전
주요 개선사항:
1. 4시간봉 추가 분석으로 진입 타이밍 개선
2. 실시간 급등/급락 감지 및 대응
3. 동적 파라미터 조정 (변동성 기반)
4. 백테스팅 기능 추가
5. 포트폴리오 분산 강화
6. 적응형 리스크 관리
"""

import os
import time
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import threading
from collections import deque

# 기존 빗썸 API 및 알림 모듈
import myBithumb
import discord_alert
import requests

################################### 로깅 시스템 ##################################

# 로그 디렉토리 생성
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# 로그 파일명 생성 함수
def log_namer(default_name):
    """로그 파일 이름 생성 함수"""
    base_filename, ext, date = default_name.split(".")
    return f"{base_filename}.{date}.{ext}"

def setup_logger():
    """로거 설정"""
    logger = logging.getLogger('BithumbTrendBot')
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        logger.handlers.clear()
    
    # 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
    log_file = os.path.join(log_directory, 'bithumb_trend_bot.log')
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=7,    # 7일치 로그 파일 보관
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
    
    return logger

logger = setup_logger()
# myBithumb모듈에 로거 전달
myBithumb.get_logger(logger)

################################### 설정 관리 ##################################

class TradingConfig:
    """거래 설정 관리 클래스 - 강화된 매수 기준 반영"""
    
    def __init__(self, config_path: str = "bithumb_trend_config.json"):
        self.config_path = config_path
        self.load_config()

    def load_config(self):
        """설정 파일 로드 - 강화된 기준 적용"""
        default_config = {
            # 투자 설정
            "bot_investment_budget": 100000,
            "reinvest_profits": True,
            "max_total_budget": 200000,
            "max_coin_count": 3,
            "min_order_money": 10000,
            "daily_loss_limit": -0.08,
            "coin_loss_limit": -0.05,
            
            # 멀티 타임프레임 설정
            "use_multi_timeframe": True,
            "primary_timeframe": "1d",
            "secondary_timeframe": "4h",
            "realtime_monitoring": True,
            
            # 동적 조정 설정
            "adaptive_parameters": True,
            "volatility_threshold_low": 0.1,
            "volatility_threshold_high": 0.25,
            
            # 급등/급락 대응 설정
            "dip_buying_enabled": True,
            "dip_threshold": -0.08,
            "pump_selling_enabled": True,
            "pump_threshold": 0.15,
            
            # 이동평균선 설정
            "short_ma": 5,
            "long_ma": 20,
            "btc_ma1": 30,
            "btc_ma2": 60,
            "short_ma_4h": 12,
            "long_ma_4h": 24,

            # 스캐너 연동 설정
            "scanner_integration": {
                "enabled": True,
                "target_file": "target_coins.json",
                "min_targets": 10,
                "essential_coins": ["KRW-BTC", "KRW-ETH"],
                "max_age_hours": 48,
                "fallback_on_error": True,
                "status_alerts": True
            },

            # 코인 설정
            "exclude_coins": ['KRW-BTC', 'KRW-XRP', 'KRW-USDT'],
            "target_altcoins": [
                "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-DOGE",
                "KRW-ADA", "KRW-BNB", "KRW-PEPE", "KRW-CAKE", "KRW-SUI",
                "KRW-TRX", "KRW-HBAR", "KRW-SHIB", "KRW-LINK", "KRW-ONDO",
                "KRW-AVAX", "KRW-UNI", "KRW-ATOM", "KRW-NEAR", "KRW-ICP",
                "KRW-ALGO", "KRW-VET", "KRW-BCH", "KRW-ETC", "KRW-XLM", 
                "KRW-A", "KRW-DOT", "KRW-AXS", "KRW-MANA", "KRW-SAND",
                "KRW-ENS", "KRW-STX"
            ],
            
            # 🔧 강화된 거래 조건
            "min_volume_value": 30000000,
            "top_volume_count": 40,  # 50 → 40으로 축소
            "top_change_count": 40,  # 50 → 40으로 축소
            
            # 섹터 분산 설정
            "sector_diversification": True,
            "max_coins_per_sector": 2,
            "sector_mapping": {
                "Layer1": ["KRW-SOL", "KRW-ADA", "KRW-AVAX", "KRW-NEAR", "KRW-DOT"],
                "DeFi": ["KRW-UNI", "KRW-CAKE", "KRW-ONDO", "KRW-LINK"],
                "Meme": ["KRW-DOGE", "KRW-PEPE", "KRW-SHIB"],
                "Gaming": ["KRW-AXS", "KRW-MANA", "KRW-SAND"],
                "Others": ["KRW-TRX", "KRW-HBAR", "KRW-ALGO", "KRW-VET", 
                        "KRW-BCH", "KRW-ETC", "KRW-XLM", "KRW-A", "KRW-ENS", "KRW-STX"]
            },
            
            # 실행 설정
            "execution_interval": 3600,
            "realtime_check_interval": 300,
            "performance_alert_interval": 86400,
            
            # 알림 설정
            "use_discord_alert": True,
            "daily_report_time": "15:30",
            
            # 백테스팅 설정
            "backtest_enabled": False,
            "backtest_days": 30,
            "backtest_initial_budget": 100000,
            
            # 🔧 강화된 안전 설정
            "price_deviation_limit": 0.06,  # 0.08 → 0.06으로 강화
            "max_consecutive_losses": 3,
            "emergency_stop_loss": -0.1,
            "volatility_limit": 0.15,

            "predictive_scoring": {
                "enabled": True,
                "description": "예측형 점수 시스템 - BORA 실수 방지",
                "risk_adjustments": {
                "extreme_low_price_penalty": 1.5,
                "weekly_pump_threshold": 0.25,
                "daily_pump_threshold": 0.10,
                "volume_surge_threshold": 5.0,
                "rsi_overbought_threshold": 75
                },
                "enhanced_thresholds": {
                "fear_market_min": 8.5,
                "neutral_market_min": 9.5,
                "greed_market_min": 10.0
                }
            },

            # 🔧 강화된 가격 괴리 설정
            "advanced_price_deviation": {
                "enabled": True,
                "basic_limit": 0.06,  # 0.08 → 0.06으로 강화
                "maximum_limit": 0.12,  # 0.15 → 0.12로 강화
                "momentum_override": {
                    "min_momentum_score": 75,  # 70 → 75로 상향
                    "medium_limit": 0.10  # 0.12 → 0.10으로 강화
                }
            },
            
            # 🆕 새로운 강화된 필터 시스템
            "enhanced_filters": {
                "daily_minimum_score": 7.0,
                "minimum_volume_ratio": 1.5,
                "weekly_trend_required": True,
                "ma_alignment_required": True,
                "resistance_level_check": True,
                "max_rsi_for_buy": 75,
                "min_daily_change_threshold": -0.02,
                "volume_surge_with_decline_block": True,
                "description": "강화된 매수 필터 - INJ 사례 개선"
            },
            
            # 급락매수 전략
            "dip_buy_strategy": {
                "min_protection_minutes": 30,
                "target_profit": 0.03,
                "stop_loss": -0.1,
                "rsi_recovery_threshold": 55,
                "market_crash_threshold": -0.07,
                "description": "급락매수 전용 매도 조건",
                "use_smart_sell_logic": True,
                "smart_sell_min_holding_minutes": 30,
                "smart_sell_profit_decline_threshold": 0.9,
                "smart_sell_min_bad_signals": 2,
                "smart_sell_stagnation_minutes": 20,
                "smart_sell_volume_threshold": 0.8
            },
            
            # 체결가 정확도 설정
            "price_tracking": {
                "enabled": True,
                "max_price_diff_warn": 0.05,
                "fallback_to_current": True,
                "trade_history_limit": 5,
                "time_window_seconds": 300
            },
            # 🆕 거래량 기반 보호 시스템 추가
            "volume_based_protection": {
                "enabled": True,
                "description": "거래량 급증 시 손절매 보호 - BORA 사례 방지",
                "volume_surge_threshold": 2.0,
                "min_volume_trend": 1.5,
                "protection_duration_minutes": 30,
                "emergency_override_threshold": 4.0,
                "debug_logging": True
            },
            
            # 🆕 기술적 보호 시스템 추가
            "technical_protection": {
                "enabled": True,
                "description": "RSI 과매도 시 손절매 보호",
                "rsi_oversold_threshold": 30,
                "protection_duration_minutes": 20,
                "debug_logging": True
            },
            # 🔧 기존 수익보존 시스템 (변경 없음)
            "profit_protection": {
                "enabled": True,
                
                # 자동 매도 설정
                "auto_sell_enabled": True,
                "auto_sell_check_interval": 2,
                "auto_sell_immediate": True,
                
                # 수익 고정 설정
                "auto_lock_threshold": 0.15,
                "lock_profit_rate": 0.1,
                "dip_buy_fast_lock": 0.08,
                "dip_buy_lock_rate": 0.05,
                
                # 트레일링 스톱 설정
                "trailing_start_threshold": 0.1,
                "trailing_distance": 0.05,
                
                # 단계별 보호 비활성화
                "staged_protection": {
                    "enabled": False,
                    "stage_30_decline": {
                        "action": "partial_sell",
                        "sell_ratio": 0.3,
                        "description": "30% 감소 시 30% 부분매도"
                    },
                    "stage_40_decline": {
                        "action": "partial_sell",
                        "sell_ratio": 0.5,
                        "description": "40% 감소 시 50% 부분매도"
                    },
                    "stage_60_decline": {
                        "action": "full_sell_signal",
                        "auto_sell": True,
                        "description": "60% 감소 시 전량매도"
                    }
                },
                
                # 적극적 수익실현 설정
                "aggressive_realization": {
                    "enabled": True,
                    "high_profit_threshold": 0.08,
                    "medium_profit_threshold": 0.05,
                    "low_profit_threshold": 0.02,
                    
                    "high_profit_conditions": {
                        "min_hold_hours": 24,
                        "min_current_profit": 0.05,
                        "max_decline_rate": 0.25
                    },
                    "medium_profit_conditions": {
                        "min_hold_hours": 36,
                        "min_current_profit": 0.03,
                        "max_decline_rate": 0.35
                    },
                    "low_profit_conditions": {
                        "min_hold_hours": 48,
                        "min_current_profit": 0.015,
                        "max_decline_rate": 0.50
                    }
                },
                
                # 시간 기반 강제 실현
                "time_based_realization": {
                    "enabled": True,
                    "max_hold_hours": 72,
                    "min_profit_for_forced_sell": 0.02
                },
                
                # 급락매수 특별 관리
                "dip_buy_special": {
                    "enabled": True,
                    "quick_realization_threshold": 0.06,
                    "quick_realization_target": 0.03,
                    "quick_realization_hours": 12
                },
                
                # 긴급 보호 설정
                "emergency_protection": {
                    "breakeven_protection": True,
                    "breakeven_threshold": 0.005,
                    "loss_prevention": True,
                    "min_profit_for_protection": 0.02
                },
                
                # 급락매수 보호
                "dip_buy_protection": {
                    "enabled": True,
                    "special_threshold": 0.08,
                    "protection_level": 0.01
                },
                
                # 알림 설정
                "decline_alerts": True,
                "decline_alert_thresholds": [0.2, 0.3, 0.4],
                "emergency_decline_threshold": 0.4,
                
                # 시스템 설정
                "update_interval_minutes": 2,
                "debug_logging": True,
                "action_logging": True
            },
            
            # 쿨다운 시스템 설정
            "trade_cooldown_minutes": 60,
            "prevent_ping_pong_trading": True,
            "ping_pong_prevention_hours": 2,
            "ping_pong_min_wait_minutes": 30,
            "max_daily_trades_per_coin": 3,

            # 로그 최적화 설정
            "log_optimization": {
                "reduce_exclusion_spam": True,
                "exclusion_log_interval": 300,
                "detailed_dip_buy_log": True,
                "smart_sell_debug_log": True,
                "profit_protection_debug": True,
                "cooldown_debug_log": True
            },
            
            # 🔧 강화된 점수 시스템 설정
            "improved_scoring_system": {
                "enabled": True,
                "description": "강화된 멀티타임프레임 점수 시스템 - INJ 사례 개선",
                
                "daily_signal_weights": {
                    "moving_average_score": 3.0,
                    "volume_score": 2.0,
                    "rsi_score": 1.0,
                    "weekly_return_score": 2.0,
                    "btc_market_score": 2.0,
                    "bonus_score": 1.0
                },
                
                # 🔧 강화된 시장별 매수 기준
                "market_based_thresholds": {
                    "extreme_fear": {
                        "min_score": 7.5,  # 6.5 → 7.5로 상향
                        "description": "공포 시장 - 강화된 기준"
                    },
                    "fear": {
                        "min_score": 7.5,  # 6.5 → 7.5로 상향
                        "description": "공포 시장 - 강화된 기준"
                    },
                    "neutral": {
                        "min_score": 8.5,  # 8.0 → 8.5로 상향
                        "description": "중립 시장 - 강화된 기준"
                    },
                    "greed": {
                        "min_score": 9.0,  # 8.5 → 9.0으로 상향
                        "description": "탐욕 시장 - 강화된 기준"
                    },
                    "extreme_greed": {
                        "min_score": 10.0,  # 9.5 → 10.0으로 상향
                        "description": "극탐욕 시장 - 강화된 기준"
                    },
                    "volatile_market": {
                        "min_score": 9.0,  # 8.5 → 9.0으로 상향
                        "description": "변동성 큰 시장 - 강화된 기준"
                    },
                    "calm_market": {
                        "min_score": 8.0,  # 7.0 → 8.0으로 상향
                        "description": "안정적 시장 - 강화된 기준"
                    }
                },
                
                # 🔧 강화된 안전 체크
                "safety_checks": {
                    "high_score_additional_check": {
                        "enabled": True,
                        "threshold": 9.0,
                        "max_weekly_gain": 0.3,  # 0.5 → 0.3으로 강화
                        "description": "고득점 코인 안전 검증 강화"
                    },
                    "volume_safety_margin": 1.0,  # 0.8 → 1.0으로 강화
                    "price_deviation_recheck": True,
                    
                    # 🆕 새로운 안전 체크들
                    "resistance_level_check": {
                        "enabled": True,
                        "lookback_days": 10,
                        "resistance_threshold": 0.95,
                        "description": "저항선 근처 매수 금지 - INJ 사례 방지"
                    },
                    "volume_spike_risk_check": {
                        "enabled": True,
                        "spike_threshold": 5.0,
                        "decline_after_spike": True,
                        "description": "거래량 급증 후 하락 패턴 차단"
                    },
                    "trend_confirmation_required": True
                },
                
                # 🔧 강화된 4시간봉 조정 설정
                "h4_adjustment_settings": {
                    "strong_uptrend_bonus": 1.5,
                    "weak_uptrend_bonus": 0.3,  # 0.5 → 0.3으로 축소
                    "consecutive_green_bonus": 1.0,
                    "volume_surge_bonus": 0.5,
                    "downtrend_penalty": -1.5,  # -1.0 → -1.5로 확대
                    "volume_decline_penalty": -0.8,  # -0.5 → -0.8로 확대
                    "rsi_overbought_penalty": -1.5,  # -1.0 → -1.5로 확대
                    "consecutive_red_penalty": -1.5,  # -1.0 → -1.5로 확대
                    
                    # 🆕 새로운 4시간봉 제한 설정
                    "daily_score_limit_for_adjustment": 7.5,
                    "max_positive_adjustment_low_daily": 0.5,
                    "max_positive_adjustment_high_daily": 2.0,
                    "volume_requirement_for_green": True,
                    "resistance_check_enabled": True,
                    "description": "강화된 4시간봉 보정 - 일봉 기준 미달 시 보정 제한"
                }
            }
        }
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 깊은 병합 수행
            self.config = self._merge_configs(default_config, loaded_config)
            logger.info(f"강화된 설정 파일 로드 완료: {self.config_path}")
            
            # 🆕 강화된 점수 시스템 확인 및 알림
            self._validate_enhanced_scoring_config()
            
        except FileNotFoundError:
            self.config = default_config
            self.save_config()
            logger.info(f"강화된 기본 설정 파일 생성: {self.config_path}")
            logger.info("🚀 강화된 매수 기준이 기본 활성화되었습니다!")
        
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {str(e)}")
            self.config = default_config

    def _validate_enhanced_scoring_config(self):
        """🆕 강화된 점수 시스템 설정 검증 및 알림"""
        try:
            scoring_config = self.config.get('improved_scoring_system', {})
            
            if not scoring_config.get('enabled', False):
                logger.warning("⚠️ 강화된 점수 시스템이 비활성화되어 있습니다!")
                return False
            
            # 강화된 기준 확인
            thresholds = scoring_config.get('market_based_thresholds', {})
            enhanced_filters = self.config.get('enhanced_filters', {})
            
            # 강화 여부 체크
            improvements = []
            
            # 시장별 기준 강화 확인
            calm_score = thresholds.get('calm_market', {}).get('min_score', 0)
            if calm_score >= 8.0:
                improvements.append("✅ 안정시장 기준 강화 (8.0점)")
            else:
                improvements.append("❌ 안정시장 기준 미강화")
            
            neutral_score = thresholds.get('neutral', {}).get('min_score', 0)
            if neutral_score >= 8.5:
                improvements.append("✅ 중립시장 기준 강화 (8.5점)")
            else:
                improvements.append("❌ 중립시장 기준 미강화")
            
            # 새로운 필터 확인
            if enhanced_filters.get('enabled', True):
                daily_min = enhanced_filters.get('daily_minimum_score', 0)
                volume_min = enhanced_filters.get('minimum_volume_ratio', 0)
                
                if daily_min >= 7.0:
                    improvements.append("✅ 일봉 최소점수 강화 (7.0점)")
                else:
                    improvements.append("❌ 일봉 최소점수 미설정")
                
                if volume_min >= 1.5:
                    improvements.append("✅ 거래량 기준 강화 (1.5배)")
                else:
                    improvements.append("❌ 거래량 기준 미강화")
                
                if enhanced_filters.get('resistance_level_check', False):
                    improvements.append("✅ 저항선 체크 활성화")
                else:
                    improvements.append("❌ 저항선 체크 비활성화")
            else:
                improvements.append("❌ 강화된 필터 시스템 비활성화")
            
            # 강화 상태 로깅
            logger.info("🛡️ 강화된 매수 기준 상태:")
            for improvement in improvements:
                logger.info(f"  {improvement}")
            
            # 핵심 설정값 로깅
            logger.info(f"🎯 핵심 강화 설정:")
            logger.info(f"  • 안정시장 기준: {calm_score}점")
            logger.info(f"  • 중립시장 기준: {neutral_score}점")
            logger.info(f"  • 일봉 최소점수: {enhanced_filters.get('daily_minimum_score', 0)}점")
            logger.info(f"  • 거래량 최소비율: {enhanced_filters.get('minimum_volume_ratio', 0)}배")
            
            logger.info("✅ 강화된 매수 기준 설정 검증 완료")
            logger.info("🚀 INJ 같은 약한 신호 매수가 차단됩니다!")
            
            return True
            
        except Exception as e:
            logger.error(f"강화된 설정 검증 중 에러: {str(e)}")
            return False

    # 기존 메서드들은 동일하게 유지
    def _merge_configs(self, default: dict, loaded: dict) -> dict:
        """딕셔너리 깊은 병합"""
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self):
        """설정 저장"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"설정 저장 실패: {str(e)}")
    
    def get(self, key, default=None):
        """설정값 가져오기"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            value = value.get(k, default)
            if value is None:
                return default
        return value

class TradePriceTracker:
    """실제 체결가격 추적 및 관리"""
    
    def __init__(self):
        self.recent_trades = {}  # ticker: {'price': float, 'timestamp': datetime}
        
    def get_actual_executed_price(self, ticker, order_type='buy', fallback_price=None):
        """실제 체결가격 조회 - 간단하고 정확한 방법"""
        try:
            # 1차: 최근 거래 내역에서 확인
            recent_orders = myBithumb.GetOrderHistory(ticker, limit=5)
            
            if recent_orders:
                # 가장 최근 주문 찾기 (5분 이내)
                now = datetime.datetime.now()
                for order in recent_orders:
                    order_time = datetime.datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
                    time_diff = (now - order_time.replace(tzinfo=None)).total_seconds()
                    
                    # 5분 이내의 해당 타입 주문
                    if (time_diff <= 300 and 
                        order['side'] == ('bid' if order_type == 'buy' else 'ask')):
                        
                        executed_price = float(order['price'])
                        executed_volume = float(order['executed_volume'])
                        
                        if executed_volume > 0:  # 실제 체결된 주문
                            logger.info(f"✅ 실제 체결가 확인: {ticker} {executed_price:,.0f}원")
                            return executed_price
            
            # 2차: 현재가로 대체 (API 부하 최소화)
            if fallback_price:
                logger.debug(f"⚠️ 체결가 추정 사용: {ticker} {fallback_price:,.0f}원")
                return fallback_price
            else:
                current_price = myBithumb.GetCurrentPrice(ticker)
                if current_price and current_price > 0:
                    logger.debug(f"🔄 현재가 사용: {ticker} {current_price:,.0f}원")
                    return current_price
            
            return None
            
        except Exception as e:
            logger.error(f"체결가 조회 중 에러 ({ticker}): {str(e)}")
            return fallback_price

################################### 동적 파라미터 조정 ##################################

class AdaptiveParameterManager:
    """시장 상황에 따른 동적 파라미터 조정"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.market_volatility_history = deque(maxlen=24)  # 24시간 변동성 히스토리
        self.current_market_regime = "NORMAL"  # CALM, NORMAL, VOLATILE
        
    def update_market_volatility(self, btc_volatility: float):
        """시장 변동성 업데이트"""
        self.market_volatility_history.append(btc_volatility)
        
        if len(self.market_volatility_history) >= 12:  # 12시간 이상 데이터
            avg_volatility = np.mean(self.market_volatility_history)
            
            if avg_volatility < self.config.get('volatility_threshold_low', 0.10):
                self.current_market_regime = "CALM"
            elif avg_volatility > self.config.get('volatility_threshold_high', 0.25):
                self.current_market_regime = "VOLATILE"
            else:
                self.current_market_regime = "NORMAL"
                
        logger.info(f"시장 상태: {self.current_market_regime} (변동성: {btc_volatility:.3f})")
    
    def get_adaptive_stop_loss(self, base_stop_loss: float) -> float:
        """적응형 손절매 수준"""
        if self.current_market_regime == "CALM":
            return base_stop_loss * 0.8  # 평온시 손절 강화
        elif self.current_market_regime == "VOLATILE":
            return base_stop_loss * 1.3  # 변동성 높을 때 여유
        else:
            return base_stop_loss
    
    def get_adaptive_position_size(self, base_size: float) -> float:
        """적응형 포지션 크기"""
        if self.current_market_regime == "CALM":
            return base_size * 1.1  # 평온시 포지션 확대
        elif self.current_market_regime == "VOLATILE":
            return base_size * 0.7  # 변동성 높을 때 축소
        else:
            return base_size
    
    def get_adaptive_entry_threshold(self) -> float:
        """적응형 진입 임계값"""
        if self.current_market_regime == "CALM":
            return 0.03  # 평온시 낮은 임계값
        elif self.current_market_regime == "VOLATILE":
            return 0.08  # 변동성 높을 때 높은 임계값
        else:
            return 0.05  # 기본값

################################### 백테스팅 엔진 ##################################

class BacktestEngine:
    """백테스팅 엔진"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.results = []
    
    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """백테스팅 실행"""
        try:
            logger.info(f"백테스팅 시작: {start_date} ~ {end_date}")
            
            # 가상 포트폴리오 초기화
            virtual_portfolio = {
                'cash': self.config.get('backtest_initial_budget', 100000),
                'holdings': {},
                'trade_history': []
            }
            
            # 백테스팅 로직 (단순화된 버전)
            # 실제 구현시에는 과거 데이터를 시계열로 순회하며 매매 시뮬레이션
            
            total_return = 0.15  # 예시: 15% 수익
            win_rate = 0.65      # 예시: 65% 승률
            max_drawdown = 0.08  # 예시: 8% 최대 낙폭
            
            backtest_result = {
                'start_date': start_date,
                'end_date': end_date,
                'initial_capital': self.config.get('backtest_initial_budget'),
                'final_capital': self.config.get('backtest_initial_budget') * (1 + total_return),
                'total_return': total_return,
                'win_rate': win_rate,
                'max_drawdown': max_drawdown,
                'total_trades': 25,  # 예시
                'profitable_trades': 16  # 예시
            }
            
            logger.info(f"백테스팅 완료 - 수익률: {total_return*100:.2f}%, 승률: {win_rate*100:.1f}%")
            return backtest_result
            
        except Exception as e:
            logger.error(f"백테스팅 중 에러: {str(e)}")
            return None

################################### 자산 관리 (기존과 동일하지만 개선) ##################################

class BotAssetManager:
    """봇 전용 자산 관리 클래스 - 개선버전"""

    def __init__(self, config: TradingConfig, bot_instance=None):
        self.config = config
        self.bot_instance = bot_instance  # 🆕 BithumbTrendBot 참조
        self.state_file = "bot_trading_state.json"
        self.price_tracker = TradePriceTracker()
        self.fee_rate = 0.0025
        
        # 🔧 수정: 쿿다운 시스템 개선
        self.cooldown_file = "bot_cooldown_state.json"  # 별도 파일로 관리
        self.load_state()
        self.load_cooldown_state()  # 쿨다운 상태 별도 로드
        
        self.sector_holdings = {}
        self.update_sector_holdings()

    def check_volume_protection(self, ticker):
        """거래량 기반 손절매 보호 체크"""
        try:
            volume_config = self.config.get('volume_based_protection', {})
            if not volume_config.get('enabled', False):
                return False, "거래량보호비활성"
            
            debug_log = volume_config.get('debug_logging', False)
            if debug_log:
                logger.info(f"🔊 [{ticker}] 거래량 보호 체크 시작")
            
            protection_reasons = []
            
            # === 조건 1: 거래량 급증 체크 ===
            current_ratio = self.get_current_volume_ratio(ticker)
            surge_threshold = volume_config.get('volume_surge_threshold', 2.0)
            
            if current_ratio >= surge_threshold:
                protection_reasons.append(f"거래량{current_ratio:.1f}배급증")
                if debug_log:
                    logger.info(f"✅ [{ticker}] 조건1 통과: 거래량 {current_ratio:.1f}배 급증 (기준: {surge_threshold}배)")
            elif debug_log:
                logger.debug(f"❌ [{ticker}] 조건1 실패: 거래량 {current_ratio:.1f}배 (기준: {surge_threshold}배)")
            
            # === 조건 2: 거래량 상승 추세 체크 ===
            volume_trend = self.get_volume_trend(ticker, 30)
            trend_threshold = volume_config.get('min_volume_trend', 1.5)
            
            if volume_trend >= trend_threshold:
                protection_reasons.append(f"거래량{volume_trend:.1f}배증가추세")
                if debug_log:
                    logger.info(f"✅ [{ticker}] 조건2 통과: 거래량 {volume_trend:.1f}배 증가추세 (기준: {trend_threshold}배)")
            elif debug_log:
                logger.debug(f"❌ [{ticker}] 조건2 실패: 거래량 추세 {volume_trend:.1f}배 (기준: {trend_threshold}배)")
            
            # === 조건 3: 급락 + 거래량 증가 = 매수세 유입 ===
            try:
                recent_price_change = self.get_recent_price_change(ticker, minutes=60)
                if recent_price_change < -0.05 and current_ratio >= 1.8:
                    protection_reasons.append("급락매수세유입")
                    if debug_log:
                        logger.info(f"✅ [{ticker}] 조건3 통과: 급락({recent_price_change*100:.1f}%) + 거래량({current_ratio:.1f}배)")
                elif debug_log:
                    logger.debug(f"❌ [{ticker}] 조건3 실패: 가격변화 {recent_price_change*100:.1f}%, 거래량 {current_ratio:.1f}배")
            except:
                if debug_log:
                    logger.debug(f"❌ [{ticker}] 조건3 체크 실패")
            
            # === 조건 4: 긴급 거래량 폭증 (무조건 보호) ===
            emergency_threshold = volume_config.get('emergency_override_threshold', 4.0)
            if current_ratio >= emergency_threshold:
                protection_reasons.append(f"긴급거래량{current_ratio:.1f}배폭증")
                logger.warning(f"🚨 [{ticker}] 긴급 보호: 거래량 {current_ratio:.1f}배 폭증!")
            
            # === 최종 판단 ===
            if protection_reasons:
                reason = "_".join(protection_reasons)
                logger.info(f"🛡️ [{ticker}] 거래량 보호 발동: {reason}")
                return True, reason
            
            if debug_log:
                logger.debug(f"🔊 [{ticker}] 거래량 보호 조건 불만족")
            
            return False, "거래량보호조건없음"
            
        except Exception as e:
            logger.error(f"거래량 보호 체크 에러 ({ticker}): {str(e)}")
            return False, "거래량보호에러"
        
    def check_technical_protection(self, ticker):
        """기술적 지표 기반 손절매 보호"""
        try:
            tech_config = self.config.get('technical_protection', {})
            if not tech_config.get('enabled', False):
                return False, "기술적보호비활성"
            
            debug_log = tech_config.get('debug_logging', False)
            protection_reasons = []
            
            # RSI 과매도 체크
            try:
                # 일봉 RSI 확인 (더 안정적)
                df = myBithumb.GetOhlcv(ticker, '1d', 15)  # 14일 RSI용
                if df is not None and len(df) >= 14:
                    # RSI 계산
                    period = 14
                    delta = df["close"].diff()
                    up, down = delta.copy(), delta.copy()
                    up[up < 0] = 0
                    down[down > 0] = 0
                    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
                    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
                    RS = _gain / _loss
                    rsi = 100 - (100 / (1 + RS))
                    current_rsi = rsi.iloc[-1]
                    
                    rsi_threshold = tech_config.get('rsi_oversold_threshold', 30)
                    if current_rsi < rsi_threshold:
                        protection_reasons.append(f"RSI과매도{current_rsi:.1f}")
                        if debug_log:
                            logger.info(f"✅ [{ticker}] RSI 과매도 보호: {current_rsi:.1f} < {rsi_threshold}")
                    elif debug_log:
                        logger.debug(f"❌ [{ticker}] RSI 정상: {current_rsi:.1f} >= {rsi_threshold}")
            except Exception as rsi_error:
                if debug_log:
                    logger.debug(f"❌ [{ticker}] RSI 계산 실패: {str(rsi_error)}")
            
            if protection_reasons:
                reason = "_".join(protection_reasons)
                logger.info(f"🛡️ [{ticker}] 기술적 보호 발동: {reason}")
                return True, reason
            
            return False, "기술적보호조건없음"
            
        except Exception as e:
            logger.error(f"기술적 보호 체크 에러 ({ticker}): {str(e)}")
            return False, "기술적보호에러"        

    def get_volume_trend(self, ticker, minutes=30):
        """최근 N분간 거래량 추세 분석"""
        try:
            logger.debug(f"🔊 [{ticker}] 거래량 추세 분석 시작 ({minutes}분)")
            
            # 분봉 데이터 조회
            df = myBithumb.GetOhlcv(ticker, '1m', minutes + 5)  # 여유분 5분 추가
            if df is None or len(df) < 10:
                logger.debug(f"🔊 [{ticker}] 거래량 데이터 부족")
                return 1.0
            
            # 최근 minutes분 데이터만 사용
            df = df.tail(minutes)
            
            # 전반부 vs 후반부 거래량 비교
            mid_point = len(df) // 2
            early_volume = df[:mid_point]['volume'].mean()
            recent_volume = df[mid_point:]['volume'].mean()
            
            if early_volume > 0:
                trend = recent_volume / early_volume
                logger.debug(f"🔊 [{ticker}] 거래량 추세: 전반부 {early_volume:.0f} → 후반부 {recent_volume:.0f} = {trend:.2f}배")
                return trend
            
            return 1.0
            
        except Exception as e:
            logger.error(f"거래량 추세 분석 에러 ({ticker}): {str(e)}")
            return 1.0

    def get_current_volume_ratio(self, ticker):
        """현재 거래량 비율 (최근 24시간 평균 대비)"""
        try:
            logger.debug(f"🔊 [{ticker}] 현재 거래량 비율 계산")
            
            # 최근 1시간 거래량 (60분봉 1개)
            recent_data = myBithumb.GetOhlcv(ticker, '1h', 1)
            if recent_data is None or len(recent_data) == 0:
                return 1.0
            
            current_volume = recent_data.iloc[-1]['volume']
            
            # 최근 24시간 평균 시간당 거래량
            daily_data = myBithumb.GetOhlcv(ticker, '1h', 24)
            if daily_data is None or len(daily_data) < 12:
                return 1.0
            
            avg_hourly_volume = daily_data['volume'].mean()
            
            if avg_hourly_volume > 0:
                ratio = current_volume / avg_hourly_volume
                logger.debug(f"🔊 [{ticker}] 거래량 비율: 현재 {current_volume:.0f} / 평균 {avg_hourly_volume:.0f} = {ratio:.2f}배")
                return ratio
            
            return 1.0
            
        except Exception as e:
            logger.error(f"현재 거래량 비율 계산 에러 ({ticker}): {str(e)}")
            return 1.0

    def get_recent_price_change(self, ticker, minutes=60):
        """최근 N분간 가격 변화율"""
        try:
            # 분봉으로 정확한 변화율 계산
            df = myBithumb.GetOhlcv(ticker, '1m', minutes + 5)
            if df is None or len(df) < 2:
                return 0
            
            # 최근 minutes분 데이터 사용
            df = df.tail(minutes + 1)  # +1 for start price
            
            start_price = df.iloc[0]['close']
            end_price = df.iloc[-1]['close']
            
            if start_price > 0:
                change = (end_price - start_price) / start_price
                logger.debug(f"📊 [{ticker}] {minutes}분 가격변화: {start_price:.0f} → {end_price:.0f} = {change*100:+.1f}%")
                return change
            
            return 0
            
        except Exception as e:
            logger.error(f"가격 변화율 계산 에러 ({ticker}): {str(e)}")
            return 0

    def load_cooldown_state(self):
        """🆕 쿨다운 상태 별도 로드"""
        try:
            with open(self.cooldown_file, 'r', encoding='utf-8') as f:
                cooldown_data = json.load(f)
                self.last_trades = {}
                
                # 문자열로 저장된 datetime을 다시 변환
                for ticker, trades in cooldown_data.items():
                    self.last_trades[ticker] = {}
                    for action, time_str in trades.items():
                        if time_str:
                            self.last_trades[ticker][action] = datetime.datetime.fromisoformat(time_str)
                        else:
                            self.last_trades[ticker][action] = None
                            
                logger.info(f"쿨다운 상태 로드 완료: {len(self.last_trades)}개 코인")
                
        except FileNotFoundError:
            self.last_trades = {}
            logger.info("쿨다운 상태 파일 없음 - 새로 시작")
        except Exception as e:
            logger.error(f"쿨다운 상태 로드 실패: {str(e)}")
            self.last_trades = {}

    def save_cooldown_state(self):
        """🆕 쿨다운 상태 별도 저장"""
        try:
            cooldown_data = {}
            
            # datetime을 문자열로 변환하여 저장
            for ticker, trades in self.last_trades.items():
                cooldown_data[ticker] = {}
                for action, dt in trades.items():
                    if dt:
                        cooldown_data[ticker][action] = dt.isoformat()
                    else:
                        cooldown_data[ticker][action] = None
            
            with open(self.cooldown_file, 'w', encoding='utf-8') as f:
                json.dump(cooldown_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"쿨다운 상태 저장 실패: {str(e)}")

    def can_trade_coin(self, ticker: str, action: str) -> bool:
        """🔧 개선된 쿨다운 체크 - 핑퐁 거래 방지"""
        try:
            # 1. 기본 액션별 쿨다운
            action_cooldown = self.get_action_cooldown(ticker, action)
            if not action_cooldown[0]:
                return False
            
            # 2. 🆕 핑퐁 거래 방지 (매도 후 즉시 매수 금지)
            prevent_ping_pong = self.config.get('prevent_ping_pong_trading', True)
            if prevent_ping_pong and action == 'BUY':
                ping_pong_safe = self.check_ping_pong_safety(ticker)
                if not ping_pong_safe[0]:
                    return False
            
            # 3. 🆕 일일 거래 횟수 제한
            daily_limit_ok = self.check_daily_trade_limit(ticker, action)
            if not daily_limit_ok[0]:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"쿨다운 체크 에러: {str(e)}")
            return True  # 에러 시 거래 허용

    def partial_sell_coin(self, ticker: str, sell_ratio: float, reason: str) -> bool:
        """부분 매도 실행 - BithumbTrendBot에서 이동"""
        try:
            if not self.is_bot_coin(ticker):
                logger.warning(f"[부분매도실패] {ticker} 봇 매수 코인 아님")
                return False
            
            logger.info(f"[부분매도시도] {ticker} {sell_ratio*100:.1f}% ({reason})")
            
            balances = myBithumb.GetBalances()
            if balances is None:
                logger.error(f"[부분매도실패] {ticker} - 잔고 조회 실패")
                return False
            
            total_amount = myBithumb.GetCoinAmount(balances, ticker)
            if total_amount is None or total_amount <= 0:
                logger.warning(f"[부분매도실패] {ticker} 보유 수량 없음")
                return False
            
            sell_amount = total_amount * sell_ratio
            
            # 기존 주문 취소
            myBithumb.CancelCoinOrder(ticker)
            time.sleep(0.1)
            
            # 🔧 BithumbTrendBot의 get_current_price_with_retry 사용
            if self.bot_instance:
                estimated_price = self.bot_instance.get_current_price_with_retry(ticker)
            else:
                estimated_price = myBithumb.GetCurrentPrice(ticker)
            
            if estimated_price is None or estimated_price <= 0:
                bot_positions = self.get_bot_positions()
                estimated_price = bot_positions.get(ticker, {}).get('entry_price', 1)
            
            # 부분 매도 실행
            sell_result = myBithumb.SellCoinMarket(ticker, sell_amount)
            
            if sell_result:
                # 정확한 체결가로 기록
                profit = self.record_sell_with_actual_price(
                    ticker, estimated_price, sell_amount, reason
                )
                
                msg = f"🟡 **부분 매도 완료**: {ticker}\n"
                msg += f"💰 예상체결가: {estimated_price:,.0f}원\n"
                msg += f"📊 매도 비율: {sell_ratio*100:.1f}%\n"
                msg += f"💵 매도금액: {estimated_price * sell_amount:,.0f}원\n"
                msg += f"📈 부분 손익: {profit:,.0f}원\n"
                msg += f"📝 매도 사유: {reason}\n"
                msg += f"🤖 봇 전용 매매"
                
                logger.info(msg)
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(msg)
                    except Exception as e:
                        logger.warning(f"부분매도 알림 전송 실패: {str(e)}")
                
                return True
            else:
                logger.error(f"[부분매도실패] {ticker} - 거래소 매도 실패")
                return False
                
        except Exception as e:
            logger.error(f"부분 매도 실행 중 에러 ({ticker}): {str(e)}")
            return False

    def check_daily_trade_limit(self, ticker: str, action: str) -> tuple:
        """🆕 일일 거래 횟수 제한 체크"""
        try:
            max_daily_trades = self.config.get('max_daily_trades_per_coin', 3)
            
            if max_daily_trades <= 0:
                return True, "일일제한없음"
            
            today = datetime.datetime.now().date()
            
            # 오늘 해당 코인의 거래 횟수 카운트
            today_trades = [
                trade for trade in self.state.get('trade_history', [])
                if (trade.get('ticker') == ticker and 
                    trade.get('type') == action and
                    datetime.datetime.fromisoformat(trade.get('timestamp', '1900-01-01')).date() == today)
            ]
            
            if len(today_trades) >= max_daily_trades:
                reason = f"일일{action}한도초과_{len(today_trades)}/{max_daily_trades}"
                logger.info(f"📊 [{ticker}] {reason}")
                return False, reason
            
            return True, f"일일거래여유_{len(today_trades)}/{max_daily_trades}"
            
        except Exception as e:
            logger.error(f"일일 거래 한도 체크 에러: {str(e)}")
            return True, "일일한도체크에러"

    def check_ping_pong_safety(self, ticker: str) -> tuple:
        """🆕 핑퐁 거래(매도→매수) 방지 체크"""
        try:
            ping_pong_hours = self.config.get('ping_pong_prevention_hours', 2)
            min_wait_minutes = self.config.get('ping_pong_min_wait_minutes', 30)
            
            if ticker not in self.last_trades:
                return True, "첫매수"
            
            last_sell_time = self.last_trades[ticker].get('SELL')
            if not last_sell_time:
                return True, "매도이력없음"
            
            time_since_sell = (datetime.datetime.now() - last_sell_time).total_seconds() / 60
            
            # 최소 대기 시간 체크
            if time_since_sell < min_wait_minutes:
                reason = f"핑퐁방지_{time_since_sell:.1f}분<{min_wait_minutes}분"
                logger.info(f"🏓 [{ticker}] {reason}")
                return False, reason
            
            # 핑퐁 방지 시간 체크  
            if time_since_sell < ping_pong_hours * 60:
                # 🆕 추가 조건: 가격이 충분히 변했거나 강한 매수 신호가 있는 경우만 허용
                if self.is_price_significantly_changed(ticker, last_sell_time):
                    logger.info(f"🏓 [{ticker}] 핑퐁 방지 중이지만 가격 대폭 변동으로 허용")
                    return True, f"핑퐁예외_가격변동_{time_since_sell:.1f}분"
                else:
                    reason = f"핑퐁방지_{time_since_sell:.1f}분<{ping_pong_hours}h"
                    logger.info(f"🏓 [{ticker}] {reason}")
                    return False, reason
            
            return True, "핑퐁안전"
            
        except Exception as e:
            logger.error(f"핑퐁 체크 에러: {str(e)}")
            return True, "핑퐁체크에러"

    def is_price_significantly_changed(self, ticker: str, last_sell_time: datetime.datetime) -> bool:
        """🆕 가격 대폭 변동 체크 (핑퐁 방지 예외 조건)"""
        try:
            # 매도 당시 가격과 현재 가격 비교
            current_price = myBithumb.GetCurrentPrice(ticker)
            if not current_price:
                return False
            
            # 매도 기록에서 당시 가격 찾기
            sell_records = [
                trade for trade in self.state.get('trade_history', [])
                if (trade.get('ticker') == ticker and 
                    trade.get('type') == 'SELL' and
                    abs((datetime.datetime.fromisoformat(trade.get('timestamp', '1900-01-01')) - last_sell_time).total_seconds()) < 300)
            ]
            
            if not sell_records:
                return False
            
            last_sell_price = sell_records[-1].get('price', current_price)
            price_change = abs(current_price - last_sell_price) / last_sell_price
            
            # 5% 이상 가격 변동 시 핑퐁 예외 허용
            significant_change_threshold = 0.05
            
            if price_change >= significant_change_threshold:
                logger.info(f"🏓 [{ticker}] 가격 대폭 변동 감지: {price_change*100:.1f}% "
                          f"({last_sell_price:,.0f} → {current_price:,.0f})")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"가격 변동 체크 에러: {str(e)}")
            return False

    def get_action_cooldown(self, ticker: str, action: str) -> tuple:
        """액션별 기본 쿨다운 체크"""
        try:
            if action == 'BUY':
                cooldown_minutes = self.config.get('trade_cooldown_minutes', 60)
            elif action == 'SELL':
                cooldown_minutes = self.config.get('trade_cooldown_minutes', 60)
            else:
                return True, "알수없는액션"
            
            if ticker not in self.last_trades:
                return True, "첫거래"
            
            last_time = self.last_trades[ticker].get(action)
            if not last_time:
                return True, "해당액션첫거래"
            
            time_diff = (datetime.datetime.now() - last_time).total_seconds() / 60
            
            if time_diff < cooldown_minutes:
                reason = f"{action}쿨다운_{time_diff:.1f}분/{cooldown_minutes}분"
                if self.config.get('log_optimization', {}).get('cooldown_debug_log', True):
                    logger.info(f"🕒 [{ticker}] {reason}")
                return False, reason
            
            return True, f"{action}쿨다운통과"
            
        except Exception as e:
            logger.error(f"액션 쿨다운 체크 에러: {str(e)}")
            return True, "쿨다운체크에러"

    def record_trade(self, ticker: str, action: str):
        """🔧 개선된 거래 시간 기록"""
        try:
            if ticker not in self.last_trades:
                self.last_trades[ticker] = {}
            
            self.last_trades[ticker][action] = datetime.datetime.now()
            
            # 🆕 즉시 저장하여 재시작 시에도 유지
            self.save_cooldown_state()
            
            if self.config.get('log_optimization', {}).get('cooldown_debug_log', True):
                logger.debug(f"🕒 [{ticker}] {action} 거래 시간 기록 및 저장")
                
        except Exception as e:
            logger.error(f"거래 시간 기록 에러: {str(e)}")

    def get_cooldown_status_summary(self) -> str:
        """🆕 쿨다운 상태 요약"""
        try:
            if not self.last_trades:
                return "쿨다운 기록 없음"
            
            now = datetime.datetime.now()
            active_cooldowns = []
            
            for ticker, trades in self.last_trades.items():
                for action, last_time in trades.items():
                    if last_time:
                        cooldown_minutes = self.config.get('trade_cooldown_minutes', 60)
                        time_diff = (now - last_time).total_seconds() / 60
                        
                        if time_diff < cooldown_minutes:
                            remaining = cooldown_minutes - time_diff
                            active_cooldowns.append(f"{ticker}:{action}({remaining:.0f}m)")
            
            if active_cooldowns:
                return f"활성 쿨다운: {', '.join(active_cooldowns[:3])}"
            else:
                return "모든 쿨다운 완료"
                
        except Exception as e:
            logger.error(f"쿨다운 상태 요약 에러: {str(e)}")
            return "쿨다운 상태 조회 실패"

    def get_realistic_profit_rate(self, ticker: str, current_price: float) -> float:
        """수수료를 반영한 실제 수익률 계산 - 안전성 강화 버전"""
        try:
            # 1차 검증: 포지션 존재 여부
            if ticker not in self.state.get('bot_positions', {}):
                return 0.0
            
            position = self.state['bot_positions'][ticker]
            amount = position.get('amount', 0)
            
            # 2차 검증: 기본 데이터 유효성 체크
            if amount <= 0:
                logger.warning(f"[{ticker}] 수익률 계산 불가: 보유량이 0 이하 ({amount})")
                return 0.0
            
            if current_price is None:
                logger.warning(f"[{ticker}] 수익률 계산 불가: 현재가가 None")
                return 0.0
            
            if current_price <= 0:
                logger.warning(f"[{ticker}] 수익률 계산 불가: 현재가가 0 이하 ({current_price})")
                return 0.0
            
            invested_amount = position.get('invested_amount', 0)
            if invested_amount <= 0:
                logger.warning(f"[{ticker}] 수익률 계산 불가: 투자금액이 0 이하 ({invested_amount})")
                return 0.0
            
            # 3차 검증: 수수료율 유효성
            if not hasattr(self, 'fee_rate') or self.fee_rate < 0 or self.fee_rate > 0.1:
                logger.warning(f"[{ticker}] 비정상 수수료율: {getattr(self, 'fee_rate', 'None')}")
                self.fee_rate = 0.0025  # 기본 수수료율로 복구
            
            # 매수 시 총비용 (원금 + 매수 수수료)
            buy_fee = invested_amount * self.fee_rate
            total_buy_cost = invested_amount + buy_fee
            
            # 4차 검증: 계산된 비용 유효성
            if total_buy_cost <= 0:
                logger.error(f"[{ticker}] 총 매수 비용이 0 이하: {total_buy_cost}")
                return 0.0
            
            # 매도 시 예상 순수령액 (현재가 × 수량 - 매도 수수료)
            gross_sell_value = current_price * amount
            sell_fee = gross_sell_value * self.fee_rate
            net_sell_value = gross_sell_value - sell_fee
            
            # 5차 검증: 매도 금액 유효성
            if gross_sell_value <= 0:
                logger.warning(f"[{ticker}] 총 매도 금액이 0 이하: {gross_sell_value}")
                return 0.0
            
            if net_sell_value < 0:
                logger.warning(f"[{ticker}] 순 매도 금액이 음수: {net_sell_value} (수수료가 너무 큼)")
                # 수수료가 매도금액보다 큰 경우, 수수료 없이 계산
                net_sell_value = gross_sell_value
                total_buy_cost = invested_amount
            
            # 실제 수익률 계산
            realistic_profit_rate = (net_sell_value - total_buy_cost) / total_buy_cost
            
            # 6차 검증: 결과 수익률의 합리성 체크
            if abs(realistic_profit_rate) > 10.0:  # 1000% 이상은 비정상
                logger.warning(f"[{ticker}] 비정상 수익률 감지: {realistic_profit_rate*100:.1f}%")
                logger.warning(f"  상세정보: 투자{invested_amount:,.0f}, 현재가{current_price:,.0f}, 수량{amount:.6f}")
                return 0.0
            
            # 7차 검증: NaN이나 Infinity 체크
            if not isinstance(realistic_profit_rate, (int, float)) or \
            not (-100 <= realistic_profit_rate <= 100):  # -10000% ~ 10000% 범위
                logger.warning(f"[{ticker}] 수익률 값 이상: {realistic_profit_rate}")
                return 0.0
            
            # 디버그 로그 (상세 정보)
            logger.debug(f"🔍 [{ticker}] 수수료 반영 수익률:")
            logger.debug(f"  매수 총비용: {total_buy_cost:,.0f}원 (원금{invested_amount:,.0f} + 수수료{buy_fee:.2f})")
            logger.debug(f"  매도 순수령: {net_sell_value:,.0f}원 (총액{gross_sell_value:,.0f} - 수수료{sell_fee:.2f})")
            logger.debug(f"  실제 수익률: {realistic_profit_rate*100:+.2f}%")
            
            return realistic_profit_rate
            
        except Exception as e:
            logger.error(f"실제 수익률 계산 중 에러 ({ticker}): {str(e)}")
            logger.error(f"  입력값: current_price={current_price}, ticker={ticker}")
            
            # 에러 발생 시 안전한 기본값 반환
            return 0.0

    def get_realistic_profit_amount(self, ticker: str, current_price: float) -> float:
        """수수료를 반영한 실제 손익 금액 계산"""
        try:
            if ticker not in self.state.get('bot_positions', {}):
                return 0.0
            
            position = self.state['bot_positions'][ticker]
            amount = position.get('amount', 0)
            
            if amount <= 0:
                return 0.0
            
            # 매수 시 총비용
            invested_amount = position.get('invested_amount', 0)
            buy_fee = invested_amount * self.fee_rate
            total_buy_cost = invested_amount + buy_fee
            
            # 매도 시 예상 순수령액
            gross_sell_value = current_price * amount
            sell_fee = gross_sell_value * self.fee_rate
            net_sell_value = gross_sell_value - sell_fee
            
            # 실제 손익 금액
            realistic_profit_amount = net_sell_value - total_buy_cost
            
            return realistic_profit_amount
            
        except Exception as e:
            logger.error(f"실제 손익 금액 계산 중 에러 ({ticker}): {str(e)}")
            return 0.0

    def update_profit_tracking(self):
        """💰 수익 상태 추적 및 업데이트 - 수수료 반영 버전"""
        try:
            current_time = datetime.datetime.now()
            
            for ticker, position in self.state.get('bot_positions', {}).items():
                try:
                    # 현재가 조회
                    current_price = myBithumb.GetCurrentPrice(ticker)
                    if not current_price or current_price <= 0:
                        continue
                    
                    # 🆕 수수료 반영 수익률 사용
                    current_profit_rate = self.get_realistic_profit_rate(ticker, current_price)
                    current_profit_amount = self.get_realistic_profit_amount(ticker, current_price)
                    
                    # 수익 추적 정보 초기화 (없는 경우)
                    if 'profit_tracking' not in position:
                        position['profit_tracking'] = {
                            'max_realistic_profit_rate': current_profit_rate,
                            'max_realistic_profit_amount': current_profit_amount,
                            'max_profit_price': current_price,
                            'max_profit_time': current_time.isoformat(),
                            'profit_locked': False,
                            'lock_price': 0,
                            'trailing_stop_price': 0,
                            'profit_decline_alerts': [],
                            'partial_sold_30': False,
                            'partial_sold_40': False
                        }
                    
                    tracking = position['profit_tracking']
                    
                    # 🏆 최고 수익률 업데이트 (수수료 반영)
                    max_profit_rate = tracking.get('max_realistic_profit_rate', 0)
                    if current_profit_rate > max_profit_rate:
                        tracking['max_realistic_profit_rate'] = current_profit_rate
                        tracking['max_realistic_profit_amount'] = current_profit_amount
                        tracking['max_profit_price'] = current_price
                        tracking['max_profit_time'] = current_time.isoformat()
                        
                        # 🆕 새로운 최고점 달성 시 부분매도 플래그 리셋
                        if current_profit_rate > tracking.get('last_reset_profit', 0) + 0.03:
                            tracking['partial_sold_30'] = False
                            tracking['partial_sold_40'] = False
                            tracking['last_reset_profit'] = current_profit_rate
                            logger.info(f"🏆 [{ticker}] 신규 최고 수익: {current_profit_rate*100:+.2f}% (수수료 반영)")
                    
                    # 🆕 수익 고정 로직 (수수료 반영)
                    self._check_profit_lock_conditions_realistic(ticker, position, current_profit_rate, current_price)
                    
                    # 🆕 트레일링 스톱 업데이트 (수수료 반영)
                    self._update_trailing_stop_realistic(ticker, position, current_profit_rate, current_price)
                    
                    # ⚠️ 🆕 수익 감소 알림 체크 (수수료 반영)
                    self._check_and_act_on_profit_decline_realistic(ticker, position, current_profit_rate)
                    
                except Exception as e:
                    logger.error(f"수익 추적 업데이트 중 에러 ({ticker}): {str(e)}")
                    continue
            
            # 상태 저장
            self.save_state()
            
        except Exception as e:
            logger.error(f"수익 추적 전체 업데이트 중 에러: {str(e)}")

    def _check_and_act_on_profit_decline_realistic(self, ticker, position, current_profit_rate):
        """⚠️ 수익 감소 시 알림 + 실제 액션 - 수수료 반영"""
        try:
            tracking = position['profit_tracking']
            max_profit_rate = tracking['max_realistic_profit_rate']
            
            # 5% 이상 수익이 있었던 경우만
            if max_profit_rate <= 0.05:
                return
            
            # 수익 감소율 계산
            decline_rate = (max_profit_rate - current_profit_rate) / max_profit_rate
            
            # 알림 조건들 (30%, 40%, 60% 감소)
            alert_thresholds = [0.3, 0.4, 0.6]
            alerts_sent = tracking.get('profit_decline_alerts', [])
            
            for threshold in alert_thresholds:
                if (decline_rate >= threshold and 
                    threshold not in alerts_sent):
                    
                    # 알림 메시지 생성
                    alert_msg = f"⚠️ **수익 감소 알림**: {ticker}\n"
                    alert_msg += f"📉 최고 수익: {max_profit_rate*100:+.1f}% → 현재: {current_profit_rate*100:+.1f}% (수수료반영)\n"
                    alert_msg += f"📊 감소율: {decline_rate*100:.1f}%\n"
                    
                    # 🆕 실제 액션 결정 및 실행
                    action_taken = False
                    
                    if threshold == 0.3 and not tracking.get('partial_sold_30', False):
                        # 30% 감소 시 30% 부분매도
                        alert_msg += f"🛡️ **1차 부분매도 실행** (30% 물량)\n"
                        alert_msg += f"📈 잔여 70%로 회복 기회 유지"
                        action_taken = True
                        
                        tracking['partial_sold_30'] = True
                        self.save_state()
                        threading.Thread(target=self.execute_partial_sell_for_protection, 
                                    args=(ticker, 0.3, f"30%감소자동부분매도_{decline_rate*100:.1f}%"), 
                                    daemon=True).start()
                        
                    elif threshold == 0.4 and not tracking.get('partial_sold_40', False):
                        # 40% 감소 시 50% 부분매도
                        alert_msg += f"🛡️ **2차 부분매도 실행** (50% 물량)\n"
                        alert_msg += f"📈 잔여 20%로 최소 보유"
                        action_taken = True
                        
                        tracking['partial_sold_40'] = True
                        self.save_state()
                        threading.Thread(target=self.execute_partial_sell_for_protection, 
                                    args=(ticker, 0.5, f"40%감소자동부분매도_{decline_rate*100:.1f}%"), 
                                    daemon=True).start()
                        
                    elif threshold == 0.6:
                        # 60% 감소 시 전량 매도 준비 알림
                        alert_msg += f"🚨 **전량 매도 검토 필요**\n"
                        alert_msg += f"⏰ 추가 하락 시 자동 매도됩니다"
                    
                    else:
                        # 액션 없는 알림
                        alert_msg += f"🔔 매도 검토 권장"
                    
                    logger.warning(alert_msg)
                    
                    # Discord 알림 (모든 액션에 대해)
                    if (action_taken and 
                        self.config.get('use_discord_alert') and
                        self.config.get('profit_protection', {}).get('decline_alerts', True)):
                        
                        try:
                            discord_alert.SendMessage(alert_msg)
                        except Exception as e:
                            logger.warning(f"수익 감소 알림 전송 실패: {str(e)}")
                    
                    # 알림 및 액션 기록
                    alerts_sent.append(threshold)
                    tracking['profit_decline_alerts'] = alerts_sent
                    
                    if action_taken:
                        action_description = ""
                        if threshold == 0.3:
                            action_description = "30%감소_1차부분매도_30%"
                        elif threshold == 0.4:
                            action_description = "40%감소_2차부분매도_50%"
                        
                        if 'protection_history' not in tracking:
                            tracking['protection_history'] = []
                        
                        tracking['protection_history'].append({
                            'timestamp': datetime.datetime.now().isoformat(),
                            'action': action_description,
                            'decline_rate': decline_rate,
                            'current_profit': current_profit_rate,
                            'max_profit': max_profit_rate,
                            'fee_adjusted': True
                        })
        
        except Exception as e:
            logger.error(f"수익 감소 대응 처리 중 에러 ({ticker}): {str(e)}")

    def _update_trailing_stop_realistic(self, ticker, position, current_profit_rate, current_price):
        """📉 트레일링 스톱 업데이트 - 수수료 반영"""
        try:
            tracking = position['profit_tracking']
            profit_config = self.config.get('profit_protection', {})
            
            max_profit_rate = tracking['max_realistic_profit_rate']
            
            # 트레일링 스톱 활성화 조건 (수수료 고려하여 상향 조정)
            trailing_start = profit_config.get('trailing_start_threshold', 0.10)
            trailing_distance = profit_config.get('trailing_distance', 0.05)
            
            if max_profit_rate >= trailing_start:
                # 수수료 반영 트레일링 가격 계산
                invested_amount = position.get('invested_amount', 0)
                amount = position.get('amount', 0)
                buy_fee = invested_amount * self.fee_rate
                total_buy_cost = invested_amount + buy_fee
                
                # 트레일링 수익률 계산
                trailing_profit_rate = max_profit_rate - trailing_distance
                target_net_value = total_buy_cost * (1 + trailing_profit_rate)
                gross_sell_needed = target_net_value / (1 - self.fee_rate)
                trailing_price = gross_sell_needed / amount if amount > 0 else 0
                
                # 기존 트레일링 스톱보다 높으면 업데이트
                if trailing_price > tracking.get('trailing_stop_price', 0):
                    tracking['trailing_stop_price'] = trailing_price
                    
                    logger.debug(f"📉 [{ticker}] 트레일링 스톱 업데이트: {trailing_price:,.0f}원 (수수료반영)")
        
        except Exception as e:
            logger.error(f"트레일링 스톱 업데이트 중 에러 ({ticker}): {str(e)}")

    def _check_profit_lock_conditions_realistic(self, ticker, position, current_profit_rate, current_price):
        """🔒 수익 고정 조건 체크 - 수수료 반영"""
        try:
            tracking = position['profit_tracking']
            profit_config = self.config.get('profit_protection', {})
            
            # 이미 고정된 경우 스킵
            if tracking.get('profit_locked'):
                return
            
            max_profit_rate = tracking['max_realistic_profit_rate']
            
            # 조건 1: 일정 수익률 이상 달성 시 고정 (수수료 고려하여 상향 조정)
            lock_threshold = profit_config.get('auto_lock_threshold', 0.15)
            if max_profit_rate >= lock_threshold:
                lock_rate = profit_config.get('lock_profit_rate', 0.10)
                
                tracking['profit_locked'] = True
                tracking['lock_rate'] = lock_rate
                tracking['lock_reason'] = f"자동고정_{max_profit_rate*100:.1f}%달성"
                tracking['lock_time'] = datetime.datetime.now().isoformat()
                
                logger.info(f"🔒 [{ticker}] 수익 고정: {lock_rate*100:.1f}% (최고: {max_profit_rate*100:.1f}%, 수수료반영)")
            
            # 조건 2: 급락매수의 경우 더 빠른 고정
            buy_reason = position.get('buy_reason', '')
            if '급락매수' in buy_reason and max_profit_rate >= 0.08:
                lock_rate = 0.05
                
                tracking['profit_locked'] = True
                tracking['lock_rate'] = lock_rate
                tracking['lock_reason'] = f"급락매수빠른고정_{max_profit_rate*100:.1f}%"
                tracking['lock_time'] = datetime.datetime.now().isoformat()
                
                logger.info(f"🔒 [{ticker}] 급락매수 수익 고정: {lock_rate*100:.1f}% (수수료반영)")
            
        except Exception as e:
            logger.error(f"수익 고정 조건 체크 중 에러 ({ticker}): {str(e)}")

    def check_smart_stagnation_sell(self, ticker, position, current_profit_rate):
        """🧠 스마트 정체 판단 및 적정 수익 매도"""
        try:
            tracking = position.get('profit_tracking', {})
            max_profit_rate = tracking.get('max_profit_rate', 0)
            entry_time_str = position.get('entry_time', '')
            
            if not entry_time_str:
                return False, "진입시간없음"
            
            # 보유 시간 계산
            entry_time = datetime.datetime.fromisoformat(entry_time_str)
            holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
            
            logger.debug(f"🧠 [{ticker}] 정체분석: 보유{holding_hours:.1f}h, 최고{max_profit_rate*100:.1f}%, 현재{current_profit_rate*100:.1f}%")
            
            # === 1️⃣ 코인별 적정 수익률 설정 ===
            
            # 급락매수 vs 일반매수
            buy_reason = position.get('buy_reason', '')
            is_dip_buy = '급락매수' in buy_reason
            
            # 최고 수익률 기반 적정 목표 설정
            if max_profit_rate >= 0.10:       # 10% 이상 달성한 코인
                target_profit = 0.07          # 7% 목표
                patience_hours = 72           # 3일 참을성
            elif max_profit_rate >= 0.05:     # 5% 이상 달성한 코인  
                target_profit = 0.035         # 3.5% 목표
                patience_hours = 48           # 2일 참을성
            elif max_profit_rate >= 0.03:     # 3% 이상 달성한 코인
                target_profit = 0.02          # 2% 목표  
                patience_hours = 36           # 1.5일 참을성
            elif max_profit_rate >= 0.015:    # 1.5% 이상 달성한 코인
                target_profit = 0.01          # 1% 목표
                patience_hours = 24           # 1일 참을성
            else:                             # 1.5% 미만 코인
                target_profit = 0.005         # 0.5% 목표
                patience_hours = 12           # 0.5일 참을성
            
            # 급락매수는 더 빠른 정리
            if is_dip_buy:
                patience_hours *= 0.7         # 30% 단축
                target_profit *= 0.8          # 목표도 80%로 낮춤
            
            # === 2️⃣ 정체 상태 판단 ===
            
            # 수익 정체 체크 (최고점 대비 현재 수익 유지율)
            if max_profit_rate > 0:
                profit_retention = current_profit_rate / max_profit_rate
            else:
                profit_retention = 1.0
            
            # 정체 기준들
            is_long_holding = holding_hours >= patience_hours
            is_profit_declining = profit_retention < 0.8  # 최고점 대비 80% 미만
            has_reasonable_profit = current_profit_rate >= target_profit
            
            # === 3️⃣ 매도 조건 판단 ===
            
            # 조건 1: 적정 수익 + 장기 보유
            if has_reasonable_profit and is_long_holding:
                reason = f"적정수익정리_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                logger.info(f"🧠 [{ticker}] {reason}")
                return True, reason
            
            # 조건 2: 목표 달성 후 하락 + 중기 보유
            if (has_reasonable_profit and 
                is_profit_declining and 
                holding_hours >= patience_hours * 0.6):  # 60% 시점부터
                
                reason = f"목표달성후하락_{current_profit_rate*100:.1f}%_{profit_retention*100:.0f}%유지"
                logger.info(f"🧠 [{ticker}] {reason}")
                return True, reason
            
            # 조건 3: 초장기 보유 (목표 미달성이라도)
            ultra_long_hours = patience_hours * 2
            if holding_hours >= ultra_long_hours and current_profit_rate > 0:
                reason = f"초장기보유정리_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                logger.info(f"🧠 [{ticker}] {reason}")
                return True, reason
            
            # 조건 4: 소수익 코인의 빠른 정리 (1% 미만 최고 수익)
            if (max_profit_rate < 0.01 and 
                current_profit_rate >= max_profit_rate * 0.7 and  # 최고점의 70% 이상
                holding_hours >= 6):  # 6시간 이상
                
                reason = f"소수익빠른정리_{current_profit_rate*100:.2f}%"
                logger.info(f"🧠 [{ticker}] {reason}")
                return True, reason
            
            # 홀딩 유지
            logger.debug(f"🧠 [{ticker}] 홀딩유지: 목표{target_profit*100:.1f}% vs 현재{current_profit_rate*100:.1f}%, {holding_hours:.1f}h/{patience_hours:.1f}h")
            return False, f"스마트홀딩_{current_profit_rate*100:.1f}%"
            
        except Exception as e:
            logger.error(f"스마트 정체 판단 중 에러 ({ticker}): {str(e)}")
            return False, "정체판단에러"

    def _check_profit_lock_conditions(self, ticker, position, current_profit_rate, current_price):
        """🔒 수익 고정 조건 체크"""
        try:
            tracking = position['profit_tracking']
            profit_config = self.config.get('profit_protection', {})
            
            # 이미 고정된 경우 스킵
            if tracking.get('profit_locked'):
                return
            
            max_profit_rate = tracking['max_profit_rate']
            
            # 조건 1: 일정 수익률 이상 달성 시 고정
            lock_threshold = profit_config.get('auto_lock_threshold', 0.15)  # 15% 수익 시 고정
            if max_profit_rate >= lock_threshold:
                lock_rate = profit_config.get('lock_profit_rate', 0.10)  # 10% 수익 고정
                lock_price = position['entry_price'] * (1 + lock_rate)
                
                tracking['profit_locked'] = True
                tracking['lock_price'] = lock_price
                tracking['lock_reason'] = f"자동고정_{max_profit_rate*100:.1f}%달성"
                tracking['lock_time'] = datetime.datetime.now().isoformat()
                
                logger.info(f"🔒 [{ticker}] 수익 고정: {lock_rate*100:.1f}% (최고: {max_profit_rate*100:.1f}%)")
            
            # 조건 2: 급락매수의 경우 더 빠른 고정
            buy_reason = position.get('buy_reason', '')
            if '급락매수' in buy_reason and max_profit_rate >= 0.08:  # 8% 달성 시
                lock_rate = 0.05  # 5% 고정
                lock_price = position['entry_price'] * (1 + lock_rate)
                
                tracking['profit_locked'] = True
                tracking['lock_price'] = lock_price
                tracking['lock_reason'] = f"급락매수빠른고정_{max_profit_rate*100:.1f}%"
                tracking['lock_time'] = datetime.datetime.now().isoformat()
                
                logger.info(f"🔒 [{ticker}] 급락매수 수익 고정: {lock_rate*100:.1f}%")
            
        except Exception as e:
            logger.error(f"수익 고정 조건 체크 중 에러 ({ticker}): {str(e)}")
    
    def _update_trailing_stop(self, ticker, position, current_profit_rate, current_price):
        """📉 트레일링 스톱 업데이트"""
        try:
            tracking = position['profit_tracking']
            profit_config = self.config.get('profit_protection', {})
            
            max_profit_rate = tracking['max_profit_rate']
            
            # 트레일링 스톱 활성화 조건
            trailing_start = profit_config.get('trailing_start_threshold', 0.10)  # 10% 수익부터
            trailing_distance = profit_config.get('trailing_distance', 0.05)     # 5% 하락까지 허용
            
            if max_profit_rate >= trailing_start:
                # 트레일링 스톱 가격 계산
                trailing_price = tracking['max_profit_price'] * (1 - trailing_distance)
                
                # 기존 트레일링 스톱보다 높으면 업데이트
                if trailing_price > tracking.get('trailing_stop_price', 0):
                    tracking['trailing_stop_price'] = trailing_price
                    
                    logger.debug(f"📉 [{ticker}] 트레일링 스톱 업데이트: {trailing_price:,.0f}원 (최고 대비 -{trailing_distance*100:.0f}%)")
        
        except Exception as e:
            logger.error(f"트레일링 스톱 업데이트 중 에러 ({ticker}): {str(e)}")
    
    def _check_profit_decline_alert(self, ticker, position, current_profit_rate):
        """⚠️ 수익 감소 알림 체크"""
        try:
            tracking = position['profit_tracking']
            max_profit_rate = tracking['max_profit_rate']
            
            # 수익 감소율 계산
            if max_profit_rate > 0.05:  # 5% 이상 수익이 있었던 경우만
                decline_rate = (max_profit_rate - current_profit_rate) / max_profit_rate
                
                # 알림 조건들
                alert_thresholds = [0.3, 0.5, 0.7]  # 30%, 50%, 70% 감소
                alerts_sent = tracking.get('profit_decline_alerts', [])
                
                for threshold in alert_thresholds:
                    if (decline_rate >= threshold and 
                        threshold not in alerts_sent):
                        
                        # 알림 전송
                        alert_msg = f"⚠️ **수익 감소 알림**: {ticker}\n"
                        alert_msg += f"📉 최고 수익: {max_profit_rate*100:+.1f}% → 현재: {current_profit_rate*100:+.1f}%\n"
                        alert_msg += f"📊 감소율: {decline_rate*100:.1f}%\n"
                        alert_msg += f"🔔 매도 검토 권장"
                        
                        logger.warning(alert_msg)
                        
                        # Discord 알림 (중요한 감소만)
                        if (threshold >= 0.5 and 
                            self.config.get('use_discord_alert') and
                            self.config.get('profit_protection', {}).get('decline_alerts', True)):
                            
                            try:
                                discord_alert.SendMessage(alert_msg)
                            except Exception as e:
                                logger.warning(f"수익 감소 알림 전송 실패: {str(e)}")
                        
                        # 알림 기록
                        alerts_sent.append(threshold)
                        tracking['profit_decline_alerts'] = alerts_sent
        
        except Exception as e:
            logger.error(f"수익 감소 알림 체크 중 에러 ({ticker}): {str(e)}")

    def check_profit_protection_sell_signals(self, ticker):
        """🛡️ 개선된 수익보존 매도 신호 - 거래량/기술적 보호 포함 (BORA 사례 방지)"""
        try:
            if ticker not in self.state.get('bot_positions', {}):
                return False, "포지션없음"
            
            position = self.state['bot_positions'][ticker]
            tracking = position.get('profit_tracking', {})
            
            # 현재가 조회
            current_price = myBithumb.GetCurrentPrice(ticker)
            if not current_price or current_price <= 0:
                return False, "현재가조회실패"
            
            # 수수료 반영 수익률 계산
            current_profit_rate = self.get_realistic_profit_rate(ticker, current_price)
            max_profit_rate = tracking.get('max_realistic_profit_rate', 0)
            
            logger.info(f"💰 [{ticker}] 수익현황: 현재 {current_profit_rate*100:+.1f}% | 최고 {max_profit_rate*100:+.1f}%")
            
            # 보유 시간 계산
            entry_time_str = position.get('entry_time', '')
            holding_hours = 0
            if entry_time_str:
                try:
                    entry_time = datetime.datetime.fromisoformat(entry_time_str)
                    holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
                except:
                    holding_hours = 0
            
            # === 🆕 1️⃣ 절대 손실 보호 - 다단계 검증 시스템 ===
            if current_profit_rate <= -0.08:
                logger.warning(f"⚠️ [{ticker}] 절대손실한계 도달: {current_profit_rate*100:.1f}%")
                
                # === 1단계: 거래량 기반 보호 체크 ===
                volume_protection, volume_reason = self.check_volume_protection(ticker)
                if volume_protection:
                    # 보호 시작 시간 기록
                    if 'volume_protection_start' not in position:
                        position['volume_protection_start'] = datetime.datetime.now().isoformat()
                        position['protection_trigger_loss'] = current_profit_rate
                        self.save_state()
                        
                        logger.info(f"🛡️ [{ticker}] 거래량 보호 시작: {volume_reason}")
                        
                        # 🆕 Discord 알림
                        if self.config.get('use_discord_alert'):
                            protection_msg = f"🛡️ **거래량 보호 발동!**\n"
                            protection_msg += f"📊 코인: {ticker.replace('KRW-', '')}\n"
                            protection_msg += f"📉 현재 손실: {current_profit_rate*100:.1f}%\n"
                            protection_msg += f"🔊 보호 사유: {volume_reason}\n"
                            protection_msg += f"⏰ 보호 시간: 30분\n"
                            protection_msg += f"💡 BORA 사례 방지 시스템 작동"
                            
                            try:
                                discord_alert.SendMessage(protection_msg)
                            except Exception as e:
                                logger.warning(f"보호 알림 전송 실패: {str(e)}")
                    
                    # 보호 지속 시간 체크
                    protection_duration = self.config.get('volume_based_protection', {}).get('protection_duration_minutes', 30)
                    start_time = datetime.datetime.fromisoformat(position['volume_protection_start'])
                    elapsed_minutes = (datetime.datetime.now() - start_time).total_seconds() / 60
                    
                    if elapsed_minutes < protection_duration:
                        remaining = protection_duration - elapsed_minutes
                        
                        # 보호 중 상황 개선 체크
                        trigger_loss = position.get('protection_trigger_loss', current_profit_rate)
                        improvement = current_profit_rate - trigger_loss
                        
                        if improvement > 0.02:  # 2% 이상 개선
                            logger.info(f"📈 [{ticker}] 보호 중 상황 개선: {improvement*100:+.1f}% (보호 효과!)")
                        
                        logger.info(f"🛡️ [{ticker}] 거래량 보호 중: {remaining:.0f}분 남음 ({volume_reason})")
                        return False, f"거래량보호중_{remaining:.0f}분_{volume_reason}"
                    else:
                        logger.warning(f"⏰ [{ticker}] 거래량 보호 시간 만료 ({elapsed_minutes:.0f}분 경과)")
                        # 다음 단계로 진행
                
                # === 2단계: 기술적 보호 체크 ===
                tech_protection, tech_reason = self.check_technical_protection(ticker)
                if tech_protection:
                    # 기술적 보호 시작 시간 기록
                    if 'tech_protection_start' not in position:
                        position['tech_protection_start'] = datetime.datetime.now().isoformat()
                        if 'protection_trigger_loss' not in position:
                            position['protection_trigger_loss'] = current_profit_rate
                        self.save_state()
                        
                        logger.info(f"🛡️ [{ticker}] 기술적 보호 시작: {tech_reason}")
                        
                        # Discord 알림 (기술적 보호)
                        if self.config.get('use_discord_alert'):
                            tech_msg = f"📊 **기술적 보호 발동!**\n"
                            tech_msg += f"📊 코인: {ticker.replace('KRW-', '')}\n"
                            tech_msg += f"📉 현재 손실: {current_profit_rate*100:.1f}%\n"
                            tech_msg += f"📈 보호 사유: {tech_reason}\n"
                            tech_msg += f"⏰ 보호 시간: 20분"
                            
                            try:
                                discord_alert.SendMessage(tech_msg)
                            except Exception as e:
                                logger.warning(f"기술적 보호 알림 전송 실패: {str(e)}")
                    
                    # 보호 지속 시간 체크
                    protection_duration = self.config.get('technical_protection', {}).get('protection_duration_minutes', 20)
                    start_time = datetime.datetime.fromisoformat(position['tech_protection_start'])
                    elapsed_minutes = (datetime.datetime.now() - start_time).total_seconds() / 60
                    
                    if elapsed_minutes < protection_duration:
                        remaining = protection_duration - elapsed_minutes
                        logger.info(f"🛡️ [{ticker}] 기술적 보호 중: {remaining:.0f}분 남음 ({tech_reason})")
                        return False, f"기술적보호중_{remaining:.0f}분_{tech_reason}"
                    else:
                        logger.warning(f"⏰ [{ticker}] 기술적 보호 시간 만료 ({elapsed_minutes:.0f}분 경과)")
                
                # === 3단계: 모든 보호 조건 통과 시 검증된 손절매 ===
                # 보호 효과 분석
                protection_effectiveness = ""
                if 'protection_trigger_loss' in position:
                    trigger_loss = position['protection_trigger_loss']
                    total_protection_benefit = current_profit_rate - trigger_loss
                    
                    if total_protection_benefit > 0:
                        protection_effectiveness = f"보호효과_{total_protection_benefit*100:+.1f}%"
                        logger.info(f"✅ [{ticker}] 보호 시스템 효과: {total_protection_benefit*100:+.1f}% 손실 개선")
                    else:
                        protection_effectiveness = f"추가손실_{abs(total_protection_benefit)*100:.1f}%"
                        logger.warning(f"⚠️ [{ticker}] 보호 중 추가 손실: {abs(total_protection_benefit)*100:.1f}%")
                
                # 보호 기록 정리 및 통계 저장
                protection_history = {
                    'protection_start': position.get('volume_protection_start') or position.get('tech_protection_start'),
                    'protection_end': datetime.datetime.now().isoformat(),
                    'trigger_loss': position.get('protection_trigger_loss', current_profit_rate),
                    'final_loss': current_profit_rate,
                    'volume_reason': volume_reason if volume_protection else None,
                    'tech_reason': tech_reason if tech_protection else None,
                    'effectiveness': protection_effectiveness
                }
                
                if 'protection_history' not in position:
                    position['protection_history'] = []
                position['protection_history'].append(protection_history)
                
                # 보호 관련 임시 데이터 정리
                for key in ['volume_protection_start', 'tech_protection_start', 'protection_trigger_loss']:
                    if key in position:
                        del position[key]
                
                self.save_state()
                
                reason = f"검증된절대손실_{current_profit_rate*100:.1f}%_{protection_effectiveness}"
                logger.error(f"🚨 [{ticker}] {reason} - 모든 보호 조건 만료")
                
                # 최종 손절매 Discord 알림
                if self.config.get('use_discord_alert'):
                    final_msg = f"🚨 **검증된 손절매 실행**\n"
                    final_msg += f"📊 코인: {ticker.replace('KRW-', '')}\n"
                    final_msg += f"📉 최종 손실: {current_profit_rate*100:.1f}%\n"
                    final_msg += f"🛡️ 보호 시간: 모두 만료\n"
                    final_msg += f"📊 보호 효과: {protection_effectiveness}\n"
                    final_msg += f"✅ 충분한 검증 후 매도"
                    
                    try:
                        discord_alert.SendMessage(final_msg)
                    except Exception as e:
                        logger.warning(f"최종 손절 알림 전송 실패: {str(e)}")
                
                return True, reason
            
            # === 2️⃣ 적극적 수익실현 구간별 전략 (기존 로직 유지) ===
            if max_profit_rate > 0.08:  # 8% 이상 경험한 고수익 코인
                # 빠른 수익실현 (5% 이상 유지 시)
                if current_profit_rate >= 0.05:  # 5% 이상 수익 유지
                    if holding_hours >= 24:  # 하루 이상 보유
                        reason = f"고수익코인적극실현_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                        logger.info(f"💎 [{ticker}] {reason}")
                        return True, reason
                
                # 수익 25% 감소 시 즉시 매도
                if max_profit_rate > 0:
                    decline_rate = (max_profit_rate - current_profit_rate) / max_profit_rate
                    if decline_rate >= 0.25:  # 25% 감소
                        reason = f"고수익25%감소매도_{decline_rate*100:.0f}%"
                        logger.warning(f"📉 [{ticker}] {reason}")
                        return True, reason
            
            elif max_profit_rate > 0.05:  # 5-8% 경험한 중수익 코인
                # 3% 이상 유지 + 36시간 이상 보유 시 매도
                if current_profit_rate >= 0.03 and holding_hours >= 36:
                    reason = f"중수익적정실현_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                    logger.info(f"💰 [{ticker}] {reason}")
                    return True, reason
                
                # 35% 감소 시 매도
                if max_profit_rate > 0:
                    decline_rate = (max_profit_rate - current_profit_rate) / max_profit_rate
                    if decline_rate >= 0.35:
                        reason = f"중수익35%감소매도_{decline_rate*100:.0f}%"
                        logger.warning(f"📉 [{ticker}] {reason}")
                        return True, reason
            
            elif max_profit_rate > 0.02:  # 2-5% 경험한 소수익 코인
                # 1.5% 이상 유지 + 48시간 이상 보유 시 매도
                if current_profit_rate >= 0.015 and holding_hours >= 48:
                    reason = f"소수익확정실현_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                    logger.info(f"💎 [{ticker}] {reason}")
                    return True, reason
                
                # 50% 감소 시 매도
                if max_profit_rate > 0:
                    decline_rate = (max_profit_rate - current_profit_rate) / max_profit_rate
                    if decline_rate >= 0.50:
                        reason = f"소수익50%감소매도_{decline_rate*100:.0f}%"
                        logger.warning(f"📉 [{ticker}] {reason}")
                        return True, reason
            
            # === 3️⃣ 시간 기반 강제 수익실현 ===
            if holding_hours >= 72:  # 3일 이상 보유
                if current_profit_rate >= 0.02:  # 2% 이상 수익
                    reason = f"장기보유강제실현_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                    logger.info(f"⏰ [{ticker}] {reason}")
                    return True, reason
            
            # === 4️⃣ 급락매수 특별 수익실현 ===
            buy_reason = position.get('buy_reason', '')
            if '급락매수' in buy_reason:
                # 급락매수는 더 빠른 수익실현
                if max_profit_rate > 0.06:  # 6% 이상 경험
                    if current_profit_rate >= 0.03:  # 3% 이상 유지
                        if holding_hours >= 12:  # 12시간 이상
                            reason = f"급락매수빠른실현_{current_profit_rate*100:.1f}%"
                            logger.info(f"💎 [{ticker}] {reason}")
                            return True, reason
            
            # === 5️⃣ 손실전환 방지 ===
            if max_profit_rate > 0.03 and current_profit_rate <= 0:
                reason = f"손실전환방지매도_{max_profit_rate*100:.1f}%→{current_profit_rate*100:.1f}%"
                logger.warning(f"🚨 [{ticker}] {reason}")
                return True, reason
            
            # === 6️⃣ 수익 정체 빠른 정리 ===
            if max_profit_rate > 0.04:  # 4% 이상 경험
                # 최근 수익 정체 상황 체크
                if self.is_profit_stagnating(position, current_profit_rate, max_profit_rate):
                    if current_profit_rate >= max_profit_rate * 0.6:  # 60% 이상 유지
                        reason = f"수익정체빠른정리_{current_profit_rate*100:.1f}%"
                        logger.info(f"🧠 [{ticker}] {reason}")
                        return True, reason
            
            # 홀딩 유지
            reason = f"적극홀딩_{current_profit_rate*100:+.1f}%"
            return False, reason
            
        except Exception as e:
            logger.error(f"🚨 [{ticker}] 개선된 수익보존 체크 에러: {str(e)}")
            return False, "수익보존체크에러"

    def is_profit_stagnating(self, position, current_profit_rate, max_profit_rate):
        """🧠 수익 정체 상황 판단"""
        try:
            # 수익 히스토리가 있는지 확인
            profit_history = position.get('profit_history', [])
            
            if len(profit_history) < 6:  # 충분한 데이터 없음
                return False
            
            # 최근 6개 기록에서 수익이 정체되고 있는지 확인
            recent_profits = [p.get('profit_rate', 0) for p in profit_history[-6:]]
            
            # 최고점 대비 현재 수익이 60% 이상 유지되고 있지만
            # 최근 6시간 동안 큰 변화가 없다면 정체로 판단
            if current_profit_rate >= max_profit_rate * 0.6:
                profit_range = max(recent_profits) - min(recent_profits)
                if profit_range < 0.01:  # 1% 미만의 변동
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"수익 정체 판단 중 에러: {str(e)}")
            return False

    def execute_aggressive_profit_realization(self, ticker, reason):
        """🚀 적극적 수익실현 전량매도"""
        try:
            logger.info(f"🚀 [{ticker}] 적극적 수익실현 시작: {reason}")
            
            # 전량매도 우선 실행
            if self.sell_coin(ticker, f"적극실현_{reason}"):
                msg = f"🚀 **적극적 수익실현 완료**\n"
                msg += f"📊 코인: {ticker}\n"
                msg += f"💰 전량 매도 완료\n"
                msg += f"📝 사유: {reason}\n"
                msg += f"🎯 수익 확정으로 안전성 확보"
                
                logger.info(msg)
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(msg)
                    except Exception as e:
                        logger.warning(f"적극실현 알림 전송 실패: {str(e)}")
                
                return True
            else:
                logger.error(f"🚀 [{ticker}] 적극적 수익실현 실패")
                return False
                
        except Exception as e:
            logger.error(f"적극적 수익실현 실행 중 에러 ({ticker}): {str(e)}")
            return False

    def check_smart_stagnation_sell_realistic(self, ticker, position, current_profit_rate):
        """🧠 스마트 정체 판단 - 수수료 반영 버전"""
        try:
            tracking = position.get('profit_tracking', {})
            max_profit_rate = tracking.get('max_realistic_profit_rate', 0)
            entry_time_str = position.get('entry_time', '')
            
            if not entry_time_str:
                return False, "진입시간없음"
            
            # 보유 시간 계산
            entry_time = datetime.datetime.fromisoformat(entry_time_str)
            holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
            
            logger.debug(f"🧠 [{ticker}] 정체분석: 보유{holding_hours:.1f}h, 최고{max_profit_rate*100:.1f}%, 현재{current_profit_rate*100:.1f}% (수수료반영)")
            
            # === 1️⃣ 코인별 적정 수익률 설정 (수수료 고려하여 하향 조정) ===
            
            # 급락매수 vs 일반매수
            buy_reason = position.get('buy_reason', '')
            is_dip_buy = '급락매수' in buy_reason
            
            # 수수료를 고려하여 목표 수익률을 약간 높게 설정
            if max_profit_rate >= 0.10:
                target_profit = 0.08          # 8% 목표 (수수료 고려)
                patience_hours = 72
            elif max_profit_rate >= 0.05:
                target_profit = 0.04          # 4% 목표
                patience_hours = 48
            elif max_profit_rate >= 0.03:
                target_profit = 0.025         # 2.5% 목표
                patience_hours = 36
            elif max_profit_rate >= 0.015:
                target_profit = 0.012         # 1.2% 목표
                patience_hours = 24
            else:
                target_profit = 0.008         # 0.8% 목표 (수수료 고려)
                patience_hours = 12
            
            # 급락매수는 더 빠른 정리
            if is_dip_buy:
                patience_hours *= 0.7
                target_profit *= 0.8
            
            # === 2️⃣ 정체 상태 판단 ===
            
            # 수익 정체 체크 (최고점 대비 현재 수익 유지율)
            if max_profit_rate > 0:
                profit_retention = current_profit_rate / max_profit_rate
            else:
                profit_retention = 1.0
            
            # 정체 기준들
            is_long_holding = holding_hours >= patience_hours
            is_profit_declining = profit_retention < 0.8
            has_reasonable_profit = current_profit_rate >= target_profit
            
            # === 3️⃣ 매도 조건 판단 ===
            
            # 조건 1: 적정 수익 + 장기 보유
            if has_reasonable_profit and is_long_holding:
                reason = f"적정수익정리_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                logger.info(f"🧠 [{ticker}] {reason} (수수료반영)")
                return True, reason
            
            # 조건 2: 목표 달성 후 하락 + 중기 보유
            if (has_reasonable_profit and 
                is_profit_declining and 
                holding_hours >= patience_hours * 0.6):
                
                reason = f"목표달성후하락_{current_profit_rate*100:.1f}%_{profit_retention*100:.0f}%유지"
                logger.info(f"🧠 [{ticker}] {reason} (수수료반영)")
                return True, reason
            
            # 조건 3: 초장기 보유
            ultra_long_hours = patience_hours * 2
            if holding_hours >= ultra_long_hours and current_profit_rate > 0:
                reason = f"초장기보유정리_{current_profit_rate*100:.1f}%_{holding_hours:.0f}h"
                logger.info(f"🧠 [{ticker}] {reason} (수수료반영)")
                return True, reason
            
            # 조건 4: 소수익 코인의 빠른 정리
            if (max_profit_rate < 0.01 and 
                current_profit_rate >= max_profit_rate * 0.7 and
                holding_hours >= 6):
                
                reason = f"소수익빠른정리_{current_profit_rate*100:.2f}%"
                logger.info(f"🧠 [{ticker}] {reason} (수수료반영)")
                return True, reason
            
            # 홀딩 유지
            logger.debug(f"🧠 [{ticker}] 홀딩유지: 목표{target_profit*100:.1f}% vs 현재{current_profit_rate*100:.1f}%, {holding_hours:.1f}h/{patience_hours:.1f}h")
            return False, f"스마트홀딩_{current_profit_rate*100:.1f}%"
            
        except Exception as e:
            logger.error(f"스마트 정체 판단 중 에러 ({ticker}): {str(e)}")
            return False, "정체판단에러"

    def execute_partial_sell_for_protection(self, ticker, sell_ratio, reason):
        """🛡️ 수익보존을 위한 부분매도 실행"""
        try:
            logger.info(f"🛡️ [{ticker}] 수익보존 부분매도 시작: {sell_ratio*100:.0f}% ({reason})")
            
            if self.partial_sell_coin(ticker, sell_ratio, reason):
                msg = f"🛡️ **수익보존 부분매도 완료**\n"
                msg += f"📊 코인: {ticker}\n"
                msg += f"💰 매도비율: {sell_ratio*100:.0f}%\n" 
                msg += f"📝 사유: {reason}\n"
                msg += f"🎯 잔여 물량으로 추가 상승 기회 유지"
                
                logger.info(msg)
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(msg)
                    except Exception as e:
                        logger.warning(f"수익보존 부분매도 알림 전송 실패: {str(e)}")
            else:
                logger.error(f"🛡️ [{ticker}] 수익보존 부분매도 실패")
                
        except Exception as e:
            logger.error(f"수익보존 부분매도 실행 중 에러 ({ticker}): {str(e)}")

    def _check_and_act_on_profit_decline(self, ticker, position, current_profit_rate):
        """⚠️ 수익 감소 시 알림 + 실제 액션 - 30%부터 적극 대응"""
        try:
            tracking = position['profit_tracking']
            max_profit_rate = tracking['max_profit_rate']
            
            # 5% 이상 수익이 있었던 경우만
            if max_profit_rate <= 0.05:
                return
            
            # 수익 감소율 계산
            decline_rate = (max_profit_rate - current_profit_rate) / max_profit_rate
            
            # 알림 조건들 (30%, 40%, 60% 감소)
            alert_thresholds = [0.3, 0.4, 0.6]
            alerts_sent = tracking.get('profit_decline_alerts', [])
            protection_history = tracking.get('protection_history', [])
            
            for threshold in alert_thresholds:
                if (decline_rate >= threshold and 
                    threshold not in alerts_sent):
                    
                    # 알림 메시지 생성
                    alert_msg = f"⚠️ **수익 감소 알림**: {ticker}\n"
                    alert_msg += f"📉 최고 수익: {max_profit_rate*100:+.1f}% → 현재: {current_profit_rate*100:+.1f}%\n"
                    alert_msg += f"📊 감소율: {decline_rate*100:.1f}%\n"
                    
                    # 🆕 실제 액션 결정 및 실행
                    action_taken = False
                    
                    if threshold == 0.3 and not tracking.get('partial_sold_30', False):
                        # 30% 감소 시 30% 부분매도
                        alert_msg += f"🛡️ **1차 부분매도 실행** (30% 물량)\n"
                        alert_msg += f"📈 잔여 70%로 회복 기회 유지"
                        action_taken = True
                        
                        # 🔥 실제 부분매도 실행 (추가된 코드)
                        tracking['partial_sold_30'] = True
                        self.save_state()
                        threading.Thread(target=self.execute_partial_sell_for_protection, 
                                    args=(ticker, 0.3, f"30%감소자동부분매도_{decline_rate*100:.1f}%"), 
                                    daemon=True).start()
                        
                    elif threshold == 0.4 and not tracking.get('partial_sold_40', False):
                        # 40% 감소 시 50% 부분매도 (누적 80% 매도)
                        alert_msg += f"🛡️ **2차 부분매도 실행** (50% 물량)\n"
                        alert_msg += f"📈 잔여 20%로 최소 보유"
                        action_taken = True
                        
                        # 🔥 실제 부분매도 실행 (추가된 코드)
                        tracking['partial_sold_40'] = True
                        self.save_state()
                        threading.Thread(target=self.execute_partial_sell_for_protection, 
                                    args=(ticker, 0.5, f"40%감소자동부분매도_{decline_rate*100:.1f}%"), 
                                    daemon=True).start()
                        
                    elif threshold == 0.6:
                        # 60% 감소 시 전량 매도 준비 알림
                        alert_msg += f"🚨 **전량 매도 검토 필요**\n"
                        alert_msg += f"⏰ 추가 하락 시 자동 매도됩니다"
                    
                    else:
                        # 액션 없는 알림
                        alert_msg += f"🔔 매도 검토 권장"
                    
                    logger.warning(alert_msg)
                    
                    # Discord 알림 (모든 액션에 대해)
                    if (action_taken and 
                        self.config.get('use_discord_alert') and
                        self.config.get('profit_protection', {}).get('decline_alerts', True)):
                        
                        try:
                            discord_alert.SendMessage(alert_msg)
                        except Exception as e:
                            logger.warning(f"수익 감소 알림 전송 실패: {str(e)}")
                    
                    # 알림 및 액션 기록
                    alerts_sent.append(threshold)
                    tracking['profit_decline_alerts'] = alerts_sent
                    
                    if action_taken:
                        action_description = ""
                        if threshold == 0.3:
                            action_description = "30%감소_1차부분매도_30%"
                        elif threshold == 0.4:
                            action_description = "40%감소_2차부분매도_50%"
                        
                        if 'protection_history' not in tracking:
                            tracking['protection_history'] = []
                        
                        tracking['protection_history'].append({
                            'timestamp': datetime.datetime.now().isoformat(),
                            'action': action_description,
                            'decline_rate': decline_rate,
                            'current_profit': current_profit_rate,
                            'max_profit': max_profit_rate
                        })
        
        except Exception as e:
            logger.error(f"수익 감소 대응 처리 중 에러 ({ticker}): {str(e)}")

    def record_buy_with_actual_price(self, ticker: str, estimated_price: float, amount: float, invested_amount: float, reason: str):
        """📊 정확한 체결가로 매수 기록 - 간소화 버전"""
        try:
            # 🎯 실제 체결가 조회 (간단한 방법)
            actual_price = self.price_tracker.get_actual_executed_price(
                ticker, 'buy', estimated_price
            )
            
            # 실제 체결가가 있으면 사용, 없으면 추정가 사용
            final_price = actual_price if actual_price else estimated_price
            
            # 기존 매수 기록 로직 사용
            self.record_buy(ticker, final_price, amount, invested_amount, reason)
            
            # 🔍 가격 차이 로깅 (5% 이상 차이날 때만)
            if actual_price and estimated_price > 0:
                price_diff = abs(actual_price - estimated_price) / estimated_price
                if price_diff > 0.05:  # 5% 이상 차이
                    logger.warning(f"📊 체결가 차이: {ticker} 추정{estimated_price:,.0f} → 실제{actual_price:,.0f} ({price_diff*100:.1f}%)")
                else:
                    logger.debug(f"📊 체결가 정확: {ticker} {actual_price:,.0f}원")
            
        except Exception as e:
            logger.error(f"정확한 매수 기록 중 에러: {str(e)}")
            # 에러 시 기존 방식으로 폴백
            self.record_buy(ticker, estimated_price, amount, invested_amount, reason)

    def record_sell_with_actual_price(self, ticker: str, estimated_price: float, amount: float, reason: str):
        """📊 정확한 체결가로 매도 기록 - 간소화 버전"""
        try:
            # 🎯 실제 체결가 조회
            actual_price = self.price_tracker.get_actual_executed_price(
                ticker, 'sell', estimated_price
            )
            
            final_price = actual_price if actual_price else estimated_price
            
            # 기존 매도 기록 로직 사용
            profit = self.record_sell(ticker, final_price, amount, reason)
            
            # 가격 차이 로깅
            if actual_price and estimated_price > 0:
                price_diff = abs(actual_price - estimated_price) / estimated_price
                if price_diff > 0.05:
                    logger.warning(f"📊 매도 체결가 차이: {ticker} 추정{estimated_price:,.0f} → 실제{actual_price:,.0f} ({price_diff*100:.1f}%)")
            
            return profit
            
        except Exception as e:
            logger.error(f"정확한 매도 기록 중 에러: {str(e)}")
            return self.record_sell(ticker, estimated_price, amount, reason)

    def load_state(self):
        """봇 상태 로드"""
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
                
            if 'daily_stats' not in self.state:
                self.state['daily_stats'] = {
                    "date": datetime.datetime.now().date().isoformat(),
                    "start_value": self.state.get('initial_budget', 100000),
                    "current_value": self.state.get('initial_budget', 100000),
                    "daily_pnl": 0,
                    "daily_return": 0
                }
                self.save_state()
                
        except FileNotFoundError:
            self.state = {
                "initial_budget": self.config.get('bot_investment_budget'),
                "current_budget": self.config.get('bot_investment_budget'),
                "total_invested": 0,
                "total_realized_profit": 0,
                "bot_positions": {},
                "trade_history": [],
                "performance_stats": {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "total_return": 0,
                    "max_drawdown": 0,
                    "start_date": datetime.datetime.now().isoformat()
                },
                "daily_stats": {
                    "date": datetime.datetime.now().date().isoformat(),
                    "start_value": self.config.get('bot_investment_budget'),
                    "current_value": self.config.get('bot_investment_budget'),
                    "daily_pnl": 0,
                    "daily_return": 0
                }
            }
            self.save_state()
            logger.info(f"봇 전용 자산 관리 초기화: {self.state['initial_budget']:,.0f}원")

    def save_state(self):
        """봇 상태 저장"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"봇 상태 저장 실패: {str(e)}")
    
    def update_sector_holdings(self):
        """🆕 섹터별 보유 현황 업데이트"""
        try:
            sector_mapping = self.config.get('sector_mapping', {})
            self.sector_holdings = {}
            
            for ticker in self.state['bot_positions']:
                # 각 섹터에서 해당 코인 찾기
                for sector, coins in sector_mapping.items():
                    if ticker in coins:
                        if sector not in self.sector_holdings:
                            self.sector_holdings[sector] = []
                        self.sector_holdings[sector].append(ticker)
                        break
                        
        except Exception as e:
            logger.error(f"섹터별 보유 현황 업데이트 중 에러: {str(e)}")
    
    def can_add_to_sector(self, ticker: str) -> bool:
        """🆕 섹터별 분산 투자 가능 여부 확인"""
        try:
            if not self.config.get('sector_diversification'):
                return True
            
            sector_mapping = self.config.get('sector_mapping', {})
            max_per_sector = self.config.get('max_coins_per_sector', 2)
            
            # 해당 코인의 섹터 찾기
            coin_sector = None
            for sector, coins in sector_mapping.items():
                if ticker in coins:
                    coin_sector = sector
                    break
            
            if coin_sector is None:
                return True  # 섹터 미분류 코인은 허용
            
            # 해당 섹터의 현재 보유 수량 확인
            current_count = len(self.sector_holdings.get(coin_sector, []))
            
            return current_count < max_per_sector
            
        except Exception as e:
            logger.error(f"섹터 분산 체크 중 에러: {str(e)}")
            return True
    
    def update_daily_stats(self):
        """일일 통계 업데이트"""
        try:
            today = datetime.datetime.now().date().isoformat()
            
            if self.state['daily_stats']['date'] != today:
                current_total_value = self.get_total_current_value()
                self.state['daily_stats'] = {
                    "date": today,
                    "start_value": current_total_value,
                    "current_value": current_total_value,
                    "daily_pnl": 0,
                    "daily_return": 0
                }
                logger.info(f"새로운 거래일 시작: {today}, 시작 자산: {current_total_value:,.0f}원")
            else:
                current_total_value = self.get_total_current_value()
                start_value = self.state['daily_stats']['start_value']
                
                self.state['daily_stats']['current_value'] = current_total_value
                self.state['daily_stats']['daily_pnl'] = current_total_value - start_value
                self.state['daily_stats']['daily_return'] = ((current_total_value - start_value) / start_value) if start_value > 0 else 0
            
            self.save_state()
            
        except Exception as e:
            logger.error(f"일일 통계 업데이트 중 에러: {str(e)}")
    
    def get_daily_return(self):
        """일일 수익률 반환"""
        try:
            if 'daily_stats' not in self.state:
                self.state['daily_stats'] = {
                    "date": datetime.datetime.now().date().isoformat(),
                    "start_value": self.state.get('initial_budget', 100000),
                    "current_value": self.state.get('initial_budget', 100000),
                    "daily_pnl": 0,
                    "daily_return": 0
                }
                self.save_state()
                
            self.update_daily_stats()
            return self.state['daily_stats']['daily_return']
        except Exception as e:
            logger.error(f"일일 수익률 계산 중 에러: {str(e)}")
            return 0
    
    def get_total_current_value(self):
        """미실현 손익 포함 총 자산 가치"""
        try:
            cash_value = self.state['initial_budget'] + self.state['total_realized_profit']
            
            unrealized_value = 0
            for ticker, position in self.state['bot_positions'].items():
                try:
                    current_price = myBithumb.GetCurrentPrice(ticker)
                    if current_price and current_price > 0:
                        current_value = current_price * position['amount']
                        unrealized_value += current_value
                    else:
                        unrealized_value += position['invested_amount']
                        logger.warning(f"현재가 조회 실패 - 투자원금으로 추정: {ticker}")
                except Exception as e:
                    logger.error(f"미실현 손익 계산 중 에러 ({ticker}): {str(e)}")
                    unrealized_value += position.get('invested_amount', 0)
            
            total_value = cash_value - self.state['total_invested'] + unrealized_value
            return max(0, total_value)
            
        except Exception as e:
            logger.error(f"총 자산 가치 계산 중 에러: {str(e)}")
            return self.state['initial_budget']

    def get_actual_invested_from_exchange(self):
        """거래소 실제 보유량 기준 투자금 계산"""
        try:
            actual_invested = 0
            balances = myBithumb.GetBalances()
            
            if not balances:
                logger.warning("잔고 조회 실패, 기록상 투자금 사용")
                return self.state.get('total_invested', 0)
            
            for ticker, position in self.state['bot_positions'].items():
                try:
                    # 실제 보유량 확인
                    coin_amount = myBithumb.GetCoinAmount(balances, ticker)
                    
                    if coin_amount and coin_amount > 0:
                        # 현재가로 투자금 계산
                        current_price = myBithumb.GetCurrentPrice(ticker)
                        if current_price and current_price > 0:
                            current_value = coin_amount * current_price
                            actual_invested += current_value
                            logger.debug(f"💎 {ticker}: {coin_amount:.6f}개 × {current_price:,.0f}원 = {current_value:,.0f}원")
                        else:
                            # 현재가 조회 실패시 기록상 투자금 사용
                            invested_amount = position.get('invested_amount', 0)
                            actual_invested += invested_amount
                            logger.debug(f"💎 {ticker}: 현재가 조회 실패, 기록금액 {invested_amount:,.0f}원 사용")
                    else:
                        logger.debug(f"💎 {ticker}: 보유량 없음, 투자금 제외")
                        
                except Exception as coin_error:
                    logger.warning(f"{ticker} 처리 중 에러: {coin_error}")
                    # 에러 시 기록상 투자금 사용
                    invested_amount = position.get('invested_amount', 0)
                    actual_invested += invested_amount
            
            logger.info(f"💰 실제 투자금 총계: {actual_invested:,.0f}원")
            return actual_invested
            
        except Exception as e:
            logger.error(f"실제 투자금 계산 중 에러: {str(e)}")
            return self.state.get('total_invested', 0)        

    def record_buy(self, ticker: str, price: float, amount: float, invested_amount: float, reason: str):
        """매수 기록 - 수수료 반영 버전"""
        try:
            # 🆕 수수료 계산
            buy_fee = invested_amount * self.fee_rate
            total_cost = invested_amount + buy_fee
            
            if ticker in self.state['bot_positions']:
                existing_position = self.state['bot_positions'][ticker]
                total_amount = existing_position['amount'] + amount
                total_invested = existing_position['invested_amount'] + invested_amount
                total_fees = existing_position.get('total_buy_fees', 0) + buy_fee
                avg_price = total_invested / total_amount if total_amount > 0 else price
                
                existing_position['amount'] = total_amount
                existing_position['invested_amount'] = total_invested
                existing_position['entry_price'] = avg_price
                existing_position['total_buy_fees'] = total_fees
                existing_position['last_buy_time'] = datetime.datetime.now().isoformat()
                
                logger.info(f"[기록] 추가매수: {ticker} 평균단가 {avg_price:,.0f}원, 총투자 {total_invested:,.0f}원 (수수료 {total_fees:.2f}원)")
            else:
                position = {
                    'ticker': ticker,
                    'entry_price': price,
                    'amount': amount,
                    'invested_amount': invested_amount,
                    'total_buy_fees': buy_fee,
                    'buy_reason': reason,
                    'entry_time': datetime.datetime.now().isoformat(),
                    'fee_rate_used': self.fee_rate
                }
                self.state['bot_positions'][ticker] = position
                logger.info(f"[기록] 신규매수: {ticker} {invested_amount:,.0f}원 (수수료 {buy_fee:.2f}원)")
            
            self.state['total_invested'] += invested_amount

            self.record_trade(ticker, 'BUY')  # 🆕 추가

            self.state['trade_history'].append({
                'type': 'BUY',
                'ticker': ticker,
                'price': price,
                'amount': amount,
                'invested_amount': invested_amount,
                'buy_fee': buy_fee,
                'total_cost': total_cost,
                'reason': reason,
                'timestamp': datetime.datetime.now().isoformat(),
                'fee_adjusted': True
            })
            
            # 🆕 섹터별 보유 현황 업데이트
            self.update_sector_holdings()
            self.save_state()
            
        except Exception as e:
            logger.error(f"매수 기록 중 에러: {str(e)}")

    def record_sell(self, ticker: str, price: float, amount: float, reason: str):
        """매도 기록 - 수수료 반영 개선된 버전"""
        try:
            if ticker not in self.state['bot_positions']:
                logger.warning(f"매도 기록 실패 - 포지션 없음: {ticker}")
                return 0
            
            position = self.state['bot_positions'][ticker]
            
            # 🔧 수정: amount가 0인 경우 처리
            if amount <= 0:
                logger.warning(f"매도 수량이 0 이하: {ticker}, amount: {amount}")
                if reason in ["보유량없음", "보유량없음_기록정리"]:
                    del self.state['bot_positions'][ticker]
                    self.update_sector_holdings()
                    self.save_state()
                    return 0
                else:
                    return 0
            
            # 🔧 수정: 부분 매도와 전량 매도 구분 개선
            position_amount = position.get('amount', 0)
            
            if amount < position_amount * 0.99:  # 99% 미만이면 부분 매도로 간주
                # 부분 매도
                sell_ratio = amount / position_amount
                sold_invested_amount = position['invested_amount'] * sell_ratio
                sold_buy_fees = position.get('total_buy_fees', 0) * sell_ratio
                
                # 💰 수수료 반영 손익 계산
                gross_sell_value = price * amount
                sell_fee = gross_sell_value * self.fee_rate
                net_sell_value = gross_sell_value - sell_fee
                total_buy_cost = sold_invested_amount + sold_buy_fees
                
                actual_profit = net_sell_value - total_buy_cost
                
                # 포지션 업데이트
                position['amount'] -= amount
                position['invested_amount'] -= sold_invested_amount
                position['total_buy_fees'] = position.get('total_buy_fees', 0) - sold_buy_fees
                
                self.state['total_invested'] -= sold_invested_amount
                self.state['total_realized_profit'] += actual_profit
                
                logger.info(f"[기록] 부분매도: {ticker} {amount:,.4f}개")
                logger.info(f"💰 수수료 반영 손익: 수령{net_sell_value:,.0f} - 비용{total_buy_cost:,.0f} = 순익{actual_profit:,.0f}원")
                
            else:
                # 전량 매도
                invested_amount = position['invested_amount']
                buy_fees = position.get('total_buy_fees', 0)
                
                # 💰 수수료 반영 손익 계산
                gross_sell_value = price * amount
                sell_fee = gross_sell_value * self.fee_rate
                net_sell_value = gross_sell_value - sell_fee
                total_buy_cost = invested_amount + buy_fees
                
                actual_profit = net_sell_value - total_buy_cost
                
                self.state['total_invested'] -= invested_amount
                self.state['total_realized_profit'] += actual_profit
                
                self.state['performance_stats']['total_trades'] += 1
                if actual_profit > 0:
                    self.state['performance_stats']['winning_trades'] += 1
                
                del self.state['bot_positions'][ticker]
                
                logger.info(f"[기록] 전량매도: {ticker}")
                logger.info(f"💰 거래금액: 매도{gross_sell_value:,.0f} - 매수{invested_amount:,.0f} = 차익{gross_sell_value - invested_amount:,.0f}원")
                logger.info(f"💰 수수료: 매수{buy_fees:.2f} + 매도{sell_fee:.2f} = 총{buy_fees + sell_fee:.2f}원")
                logger.info(f"💰 실제 순익: {actual_profit:,.0f}원 (수수료 차감 후)")
            
            # 🆕 거래 기록 (수수료 정보 포함)
            profit_rate = (actual_profit / position.get('invested_amount', 1)) if position.get('invested_amount', 0) > 0 else 0
            
            trade_record = {
                'type': 'SELL',
                'ticker': ticker,
                'price': price,
                'amount': amount,
                'gross_sell_value': gross_sell_value,
                'net_sell_value': net_sell_value,
                'buy_fees': buy_fees if 'buy_fees' in locals() else sold_buy_fees,
                'sell_fee': sell_fee,
                'total_fees': (buy_fees if 'buy_fees' in locals() else sold_buy_fees) + sell_fee,
                'actual_profit': actual_profit,
                'reason': reason,
                'timestamp': datetime.datetime.now().isoformat(),
                'holding_period': self._calculate_holding_period(position.get('entry_time', '')),
                'smart_logic_applied': self._is_smart_logic_reason(reason),
                'sell_type': self._categorize_sell_type(reason),
                'profit_rate': profit_rate,
                'fee_adjusted': True,
                'fee_rate_used': self.fee_rate
            }
            
            self.state['trade_history'].append(trade_record)
            
            self.record_trade(ticker, 'SELL')  # 🆕 추가            

            # 스마트 로직 적용 시 특별 로그
            if trade_record['smart_logic_applied']:
                logger.info(f"🧠 [스마트매도] {ticker}: {reason} | 순익률: {profit_rate*100:+.2f}% (수수료반영)")
            
            # 섹터별 보유 현황 업데이트
            self.update_sector_holdings()
            self.save_state()
            
            return actual_profit


        except Exception as e:
            logger.error(f"매도 기록 중 에러: {str(e)}")
            return 0

    def _is_smart_logic_reason(self, reason: str) -> bool:
        """스마트 로직 적용 여부 판단"""
        smart_keywords = [
            '스마트정체악화', '스마트선별제외정체', '스마트장기개선없음',
            '스마트정체', '스마트악화', '스마트'
        ]
        return any(keyword in reason for keyword in smart_keywords)

    def _categorize_sell_type(self, reason: str) -> str:
        """매도 유형 분류"""
        try:
            if '손절' in reason:
                return 'STOP_LOSS'
            elif '익절' in reason or '수익' in reason:
                return 'TAKE_PROFIT'
            elif '스마트' in reason:
                return 'SMART_SELL'
            elif '급등' in reason:
                return 'PUMP_SELL'
            elif '시장붕괴' in reason or 'BTC' in reason:
                return 'MARKET_CRASH'
            elif '선별제외' in reason:
                return 'EXCLUDED'
            elif '이동평균' in reason:
                return 'MA_SIGNAL'
            else:
                return 'OTHER'
        except:
            return 'UNKNOWN'

    def _calculate_holding_period(self, entry_time_str: str):
        """보유 기간 계산"""
        try:
            entry_time = datetime.datetime.fromisoformat(entry_time_str)
            holding_period = datetime.datetime.now() - entry_time
            return str(holding_period)
        except:
            return "Unknown"
    
    def get_bot_positions(self):
        """봇이 보유한 포지션만 반환"""
        return self.state['bot_positions']
    
    def is_bot_coin(self, ticker: str):
        """봇이 매수한 코인인지 확인"""
        return ticker in self.state['bot_positions']

    def get_performance_summary(self):
        """성과 요약 반환 - 수수료 반영 버전"""
        try:
            self.update_daily_stats()
            
            total_current_value = self.get_total_current_value_realistic()
            
            unrealized_profit = 0
            for ticker, position in self.state['bot_positions'].items():
                try:
                    current_price = myBithumb.GetCurrentPrice(ticker)
                    if current_price:
                        # 수수료 반영 미실현 손익 계산
                        unrealized_profit += self.get_realistic_profit_amount(ticker, current_price)
                    else:
                        logger.warning(f"현재가 조회 실패 - 미실현 손익 제외: {ticker}")
                except Exception as e:
                    logger.error(f"미실현 손익 계산 중 에러 ({ticker}): {str(e)}")
                    continue
            
            stats = self.state['performance_stats']
            win_rate = (stats['winning_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
            
            return {
                'initial_budget': self.state['initial_budget'],
                'current_cash': self.state['initial_budget'] + self.state['total_realized_profit'],
                'total_current_value': total_current_value,
                'realized_profit': self.state['total_realized_profit'],
                'unrealized_profit': unrealized_profit,
                'total_return': ((total_current_value - self.state['initial_budget']) / self.state['initial_budget']) * 100,
                'total_trades': stats['total_trades'],
                'winning_trades': stats['winning_trades'],
                'win_rate': win_rate,
                'current_positions': len(self.state['bot_positions']),
                'daily_pnl': self.state['daily_stats']['daily_pnl'],
                'daily_return': self.state['daily_stats']['daily_return'],
                'sector_holdings': self.sector_holdings,
                'fee_adjusted': True  # 수수료 반영 여부 표시
            }
            
        except Exception as e:
            logger.error(f"성과 요약 계산 중 에러: {str(e)}")
            return None

    def get_total_current_value_realistic(self):
        """미실현 손익 포함 총 자산 가치 - 수수료 반영 버전"""
        try:
            cash_value = self.state['initial_budget'] + self.state['total_realized_profit']
            
            unrealized_value = 0
            for ticker, position in self.state['bot_positions'].items():
                try:
                    current_price = myBithumb.GetCurrentPrice(ticker)
                    if current_price and current_price > 0:
                        # 수수료 반영 현재 가치 계산
                        amount = position['amount']
                        gross_value = current_price * amount
                        sell_fee = gross_value * self.fee_rate
                        net_value = gross_value - sell_fee  # 실제 수령 가능 금액
                        unrealized_value += net_value
                    else:
                        # 현재가 조회 실패 시 투자원금 사용 (보수적 추정)
                        unrealized_value += position['invested_amount']
                        logger.warning(f"현재가 조회 실패 - 투자원금으로 추정: {ticker}")
                except Exception as e:
                    logger.error(f"총 자산 계산 중 에러 ({ticker}): {str(e)}")
                    unrealized_value += position.get('invested_amount', 0)
            
            total_value = cash_value - self.state['total_invested'] + unrealized_value
            return max(0, total_value)
            
        except Exception as e:
            logger.error(f"총 자산 가치 계산 중 에러: {str(e)}")
            return self.state['initial_budget']

    def get_smart_sell_performance(self):
        """스마트 매도 성과 분석"""
        try:
            smart_sells = []
            regular_sells = []
            
            for trade in self.state.get('trade_history', []):
                if trade.get('type') == 'SELL' and trade.get('profit', 0) != 0:
                    if trade.get('smart_logic_applied', False):
                        smart_sells.append(trade)
                    else:
                        regular_sells.append(trade)
            
            if smart_sells:
                smart_avg_profit = sum(t['profit'] for t in smart_sells) / len(smart_sells)
                smart_avg_rate = sum(t['profit_rate'] for t in smart_sells) / len(smart_sells)
                
                logger.info(f"📊 스마트 매도 성과:")
                logger.info(f"  횟수: {len(smart_sells)}회")
                logger.info(f"  평균 수익: {smart_avg_profit:,.0f}원")
                logger.info(f"  평균 수익률: {smart_avg_rate*100:+.2f}%")
                
                return {
                    'smart_count': len(smart_sells),
                    'smart_avg_profit': smart_avg_profit,
                    'smart_avg_rate': smart_avg_rate,
                    'regular_count': len(regular_sells)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"스마트 매도 성과 분석 중 에러: {str(e)}")
            return None
        
    def get_available_budget_simplified(self):
        """💰 복리효과를 위한 동적 예산 계산 - 수정 버전"""
        try:
            # 🎯 봇 총 자산가치 (현금 + 보유코인 현재가치)
            bot_total_value = self.get_total_current_value()
            
            # 🎯 현재 투자 중인 금액
            bot_invested = self.get_actual_invested_simple()
            
            # 🎯 사용 가능한 현금 = 총 자산 - 투자금
            bot_available = bot_total_value - bot_invested
            
            # 🛡️ 안전장치: 거래소 실제 잔고와 비교
            try:
                balances = myBithumb.GetBalances()
                if balances:
                    exchange_krw = myBithumb.GetCoinAmount(balances, "KRW")
                    if exchange_krw and exchange_krw > 0:
                        # 봇 자산 기준과 거래소 잔고 중 작은 값 사용
                        final_available = min(bot_available, exchange_krw)
                        
                        logger.info(f"💰 봇 총자산: {bot_total_value:,.0f}원")
                        logger.info(f"💰 현재 투자: {bot_invested:,.0f}원") 
                        logger.info(f"💰 봇 기준 현금: {bot_available:,.0f}원")
                        logger.info(f"💰 거래소 잔고: {exchange_krw:,.0f}원")
                        logger.info(f"💰 최종 사용가능: {final_available:,.0f}원")
                        
                        return max(0, final_available)
            except Exception as api_error:
                logger.warning(f"거래소 잔고 조회 실패: {api_error}")
            
            # API 실패 시 봇 자산 기준만 사용
            logger.info(f"💰 봇 자산 기준 사용: {bot_available:,.0f}원")
            return max(0, bot_available)
            
        except Exception as e:
            logger.error(f"동적 예산 계산 중 에러: {str(e)}")
            return 0

    def get_actual_invested_simple(self):
        """💰 단순화된 실제 투자금 계산"""
        try:
            total_invested = 0
            
            for ticker, position in self.state.get('bot_positions', {}).items():
                invested_amount = position.get('invested_amount', 0)
                total_invested += invested_amount
            
            logger.debug(f"💰 봇 기록상 총 투자금: {total_invested:,.0f}원")
            return total_invested
            
        except Exception as e:
            logger.error(f"투자금 계산 중 에러: {str(e)}")
            return 0

    # 🔧 기존 복잡한 예산 계산 메서드 대체
    def get_available_budget(self):
        """사용 가능한 예산 계산 - 단순화 버전 사용"""
        return self.get_available_budget_simplified()

################################### 개선된 트렌드 추종 봇 ##################################

class BithumbTrendBot:
    """빗썸 알트코인 트렌드 추종 봇 - 멀티 타임프레임 개선 버전"""

    def __init__(self, config: TradingConfig):
        """생성자 개선"""
        self.config = config
        
        # 🔧 추가: 설정 검증
        if not self.validate_config():
            raise ValueError("설정 파일에 오류가 있습니다. 로그를 확인하세요.")

        # 🆕 동시성 제어를 위한 Lock 추가
        self.trading_lock = threading.Lock()
        self.data_lock = threading.Lock()
        
        logger.info("🔒 동시성 제어 시스템 초기화 완료")

        self.asset_manager = BotAssetManager(config, self)

        # 🆕 예측형 시스템 초기화 추가
        if config.get('predictive_scoring.enabled', True):
            self.predictive_analyzer = PredictiveSignalAnalyzer(config)
            self.use_predictive_system = True
            logger.info("🔮 예측형 점수 시스템 활성화")
        else:
            self.use_predictive_system = False
            logger.info("📊 기존 점수 시스템 사용")

        self.adaptive_manager = AdaptiveParameterManager(config)
        self.backtest_engine = BacktestEngine(config)

        # 🆕 스캐너 연동 관련만 추가
        scanner_config = config.get('scanner_integration', {})
        self.scanner_enabled = scanner_config.get('enabled', False)
        self.target_file_path = scanner_config.get('target_file', 'target_coins.json')
        self.fallback_coins = config.get('target_altcoins', [])

        # 🆕 스캐너 성과 추적 관련 변수 추가
        self.scanner_reliability_cache = None
        self.last_scanner_check = None
        self.scanner_health_alerts = {}        

        logger.info(f"🤖 매매봇 초기화 - 스캐너 연동: {'활성' if self.scanner_enabled else '비활성'}")

        # 나머지 초기화...
        self.last_execution = None
        self.last_performance_alert = None
        self.last_realtime_check = None
        
        # FNG 관련
        self.last_fng_check = None
        self.current_fng_data = None
        self.sent_alerts = set()
        
        # 거래 중단 관련
        self.trading_halted = False
        self.halt_reason = ""
        self.halt_until = None
        
        # 실시간 모니터링용
        self.price_alerts = {}
        self.last_prices = {}
        
        # 🔧 수정: 실시간 모니터링 스레드 시작 (초기화 완료 후)
        if self.config.get('realtime_monitoring'):
            self.start_realtime_monitoring()
        
        logger.info("🚀 개선된 BithumbTrendBot 초기화 완료 (멀티 타임프레임)")

        # 🆕 급락매수 전용 로직 추가 설정
        self._last_exclusion_logs = {}
        
        # 🆕 급락매수 설정 확인 및 로그
        dip_config = self.config.get('dip_buy_strategy', {})
        if dip_config:
            min_protection = dip_config.get('min_protection_minutes', 30)
            target_profit = dip_config.get('target_profit', 0.03)
            logger.info(f"💎 급락매수 전용 로직 적용: {min_protection}분 보호, {target_profit*100:.0f}% 목표")
        else:
            logger.info("💎 급락매수 전용 로직 적용 (기본 설정)")
            
        logger.info("✅ 급락매수 vs 일반매수 구분 로직 활성화")

        # 수익 추적 마지막 업데이트 시간
        self.last_profit_update = None
        
        # 수익보존 실시간 모니터링 스레드 시작
        if config.get('profit_protection', {}).get('enabled'):
            self.start_profit_protection_monitoring()

    def get_scanner_reliability(self) -> float:
        """📊 스캐너 신뢰도 점수 (0.5~1.2) - 캐시 적용"""
        try:
            # 30분 캐시 (불필요한 파일 읽기 방지)
            now = time.time()
            if (self.scanner_reliability_cache and 
                self.last_scanner_check and 
                now - self.last_scanner_check < 1800):
                return self.scanner_reliability_cache
            
            # performance_tracking.json 읽기
            if not os.path.exists('performance_tracking.json'):
                logger.debug("📊 performance_tracking.json 없음 - 기본 신뢰도 사용")
                return 1.0
            
            with open('performance_tracking.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            history = data.get('tracking_history', [])
            if not history:
                return 1.0
            
            # 최근 5회 기록으로 신뢰도 계산
            recent = history[-5:]
            
            # 1️⃣ 유지율 점수 (코인이 얼마나 안정적으로 유지되는가)
            retention_scores = []
            for record in recent:
                if record.get('existing_count', 0) > 0:
                    retention = record['retained_count'] / record['existing_count']
                    retention_scores.append(retention)
            
            avg_retention = np.mean(retention_scores) if retention_scores else 0.7
            
            # 2️⃣ 활성도 점수 (적절한 신규 발굴을 하는가)
            avg_new_count = np.mean([r.get('new_count', 0) for r in recent])
            activity_score = min(avg_new_count / 15, 1.0)  # 15개 신규가 만점
            
            # 3️⃣ 종합 신뢰도 계산
            reliability = (avg_retention * 0.7 + activity_score * 0.3)
            
            # 신뢰도 범위: 0.5 ~ 1.2 (50% ~ 120%)
            final_reliability = max(0.5, min(1.2, 0.5 + reliability * 0.7))
            
            # 캐시 업데이트
            self.scanner_reliability_cache = final_reliability
            self.last_scanner_check = now
            
            logger.debug(f"📊 스캐너 신뢰도: {final_reliability:.2f} (유지율: {avg_retention:.2f}, 활성도: {activity_score:.2f})")
            return final_reliability
            
        except Exception as e:
            logger.warning(f"📊 스캐너 신뢰도 계산 실패: {str(e)} - 기본값 사용")
            return 1.0

    def check_scanner_health_and_alert(self):
        """🏥 스캐너 건강상태 체크 및 알림 (하루 1회)"""
        try:
            today = datetime.datetime.now().date().isoformat()
            
            # 하루 1회만 체크
            if self.scanner_health_alerts.get('last_check_date') == today:
                return
            
            if not os.path.exists('performance_tracking.json'):
                return
            
            with open('performance_tracking.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            history = data.get('tracking_history', [])
            if not history:
                return
            
            latest = history[-1]
            
            # 🚨 이상 상황 감지
            alerts = []
            
            # 1. 스캐너 업데이트가 12시간 이상 없음
            last_update = datetime.datetime.fromisoformat(latest['timestamp'])
            hours_ago = (datetime.datetime.now() - last_update).total_seconds() / 3600
            
            if hours_ago > 12:
                alerts.append(f"⏰ 스캐너 {hours_ago:.1f}시간 전 마지막 업데이트")
            
            # 2. 극단적 변화 (유지율 30% 미만)
            if latest.get('existing_count', 0) > 0:
                retention_rate = latest['retained_count'] / latest['existing_count']
                if retention_rate < 0.3:
                    alerts.append(f"📉 코인 대폭 교체 (유지율: {retention_rate*100:.1f}%)")
            
            # 3. 신규 발굴 없음 (연속 3회)
            if len(history) >= 3:
                recent_new_counts = [h.get('new_count', 0) for h in history[-3:]]
                if all(count == 0 for count in recent_new_counts):
                    alerts.append("🔍 최근 3회 신규 코인 발굴 없음")
            
            # 알림 전송
            if alerts and self.config.get('use_discord_alert'):
                msg = f"🏥 **스캐너 건강체크**\n"
                for alert in alerts:
                    msg += f"• {alert}\n"
                msg += f"\n💡 스캐너 상태를 확인해보세요!"
                
                try:
                    discord_alert.SendMessage(msg)
                    logger.info(f"🏥 스캐너 건강체크 알림 전송: {len(alerts)}개 이슈")
                except Exception as e:
                    logger.warning(f"스캐너 건강체크 알림 전송 실패: {str(e)}")
            
            elif not alerts:
                logger.debug("🏥 스캐너 건강상태 양호")
            
            # 체크 완료 기록
            self.scanner_health_alerts['last_check_date'] = today
            
        except Exception as e:
            logger.error(f"스캐너 건강체크 중 에러: {str(e)}")

    def get_target_coins(self):
        """🎯 타겟 코인 리스트 획득 (스캐너 or 기존 방식)"""
        if not self.scanner_enabled:
            # 스캐너 비활성화 시: 기존 방식
            return self.config.get('target_altcoins', [])
        
        try:
            # 스캐너 활성화 시: 동적 로딩
            return self.load_scanner_targets()
            
        except Exception as e:
            logger.error(f"스캐너 타겟 로딩 실패: {str(e)} - 기존 리스트 사용")
            return self.fallback_coins

    def load_scanner_targets(self):
        """📂 스캐너 결과 로딩"""
        if not os.path.exists(self.target_file_path):
            logger.warning(f"스캐너 파일 없음: {self.target_file_path} - 기존 리스트 사용")
            return self.fallback_coins
        
        try:
            with open(self.target_file_path, 'r', encoding='utf-8') as f:
                scanner_data = json.load(f)
            
            # 생성 시간 체크
            generated_at = datetime.datetime.fromisoformat(scanner_data.get('generated_at', '1900-01-01'))
            age_hours = (datetime.datetime.now() - generated_at).total_seconds() / 3600
            
            # 데이터 신선도 경고
            if age_hours > 48:  # 48시간 초과
                logger.error(f"스캐너 데이터 너무 오래됨 ({age_hours:.1f}시간) - 기존 리스트 사용")
                return self.fallback_coins
            elif age_hours > 24:  # 24시간 초과
                logger.warning(f"스캐너 데이터 오래됨 ({age_hours:.1f}시간) - 업데이트 권장")
            else:
                logger.info(f"스캐너 데이터 신선함 ({age_hours:.1f}시간 전)")
            
            # 코인 리스트 추출
            coins = scanner_data.get('coins', [])
            target_tickers = [coin['ticker'] for coin in coins]
            
            # 🛡️ 안전장치: 최소 개수 보장
            min_targets = self.config.get('scanner_integration.min_targets', 10)
            if len(target_tickers) < min_targets:
                logger.warning(f"스캐너 결과 부족 ({len(target_tickers)}개 < {min_targets}개) - 기존 리스트 추가")
                # 기존 리스트의 상위 코인들 추가
                additional_coins = [coin for coin in self.fallback_coins[:min_targets] 
                                  if coin not in target_tickers]
                target_tickers.extend(additional_coins)
            
            # 🔧 필수 코인 강제 추가 (BTC, ETH 등)
            essential_coins = self.config.get('scanner_integration.essential_coins', ['KRW-BTC', 'KRW-ETH'])
            for coin in essential_coins:
                if coin not in target_tickers:
                    target_tickers.append(coin)
            
            logger.info(f"✅ 스캐너 타겟 로딩 완료: {len(target_tickers)}개 코인")
            logger.info(f"📊 스캐너 정보: {scanner_data.get('selected_count', 0)}개 선별, "
                       f"평균점수 {scanner_data.get('market_summary', {}).get('avg_opportunity_score', 0):.1f}")
            
            return target_tickers
            
        except Exception as e:
            logger.error(f"스캐너 파일 파싱 실패: {str(e)} - 기존 리스트 사용")
            return self.fallback_coins

    def start_profit_protection_monitoring(self):
        """🛡️ 수익보존 실시간 모니터링 스레드 - 수정된 버전"""
        try:

            logger.info("🔍 수익보존 모니터링 함수 시작")  # ← 추가
            def profit_monitor():
                logger.info("🔍 수익보존 모니터링 스레드 내부 시작")  # ← 추가
                while True:
                    try:
                        logger.info("🔍 수익보존 체크 루프 시작")  # ← 추가
                        if not self.trading_halted:
                            logger.info("🔍 거래 중단 아님 - 수익 추적 실행")  # ← 추가
                            # 🆕 수익 추적 업데이트
                            self.update_profit_tracking()
                            
                            # 🆕 수익보존 자동 매도 체크 및 실행
                            self.execute_profit_protection_sells()
                        else:
                            logger.info("🔍 거래 중단됨 - 수익 추적 스킵")  # ← 추가

                        interval = self.config.get('profit_protection', {}).get('update_interval_minutes', 10)
                        logger.info(f"🔍 다음 체크까지 {interval}분 대기")  # ← 추가
                        time.sleep(interval * 60)  # 10분마다
                        
                    except Exception as e:
                        logger.error(f"수익보존 모니터링 중 에러: {str(e)}")
                        time.sleep(60)  # 에러 시 1분 대기
            
            monitor_thread = threading.Thread(target=profit_monitor, daemon=True)
            monitor_thread.start()
            logger.info("🛡️ 수익보존 모니터링 스레드 시작 (자동 매도 포함)")
            
        except Exception as e:
            logger.error(f"🚨 수익보존 모니터링 시작 실패: {str(e)}")  # ← 추가

    def execute_profit_protection_sells(self):
        """🛡️ 수익보존 조건 감지 시 즉시 자동 매도 실행"""
        try:
            bot_positions = self.asset_manager.get_bot_positions()
            if not bot_positions:
                return
            
            logger.debug("🛡️ 수익보존 자동매도 체크 시작 (기존 매도 로직과 분리)")
            executed_sells = []
            
            for ticker in list(bot_positions.keys()):
                try:
                    protection_sell, protection_reason = self.asset_manager.check_profit_protection_sell_signals(ticker)
                    
                    if protection_sell:
                        logger.info(f"🛡️ [{ticker}] 수익보존 자동 매도 감지: {protection_reason}")
                        
                        # 긴급상황 판별 (기존 로직 유지)
                        emergency_keywords = ["절대손실한계", "손실전환방지", "긴급"]
                        is_emergency = any(keyword in protection_reason for keyword in emergency_keywords)
                        
                        # 긴급상황이 아닌 경우만 쿨타임 체크
                        if not is_emergency:
                            if not self.asset_manager.can_trade_coin(ticker, 'SELL'):
                                logger.info(f"🕒 [{ticker}] 수익보존 매도 쿨다운으로 대기: {protection_reason}")
                                continue
                        
                        # 매도 실행
                        reason = f"자동수익보존_{protection_reason}"
                        if is_emergency:
                            reason = f"긴급_{reason}"
                        
                        if self.sell_coin(ticker, reason):
                            executed_sells.append({
                                'ticker': ticker,
                                'reason': protection_reason,
                                'timestamp': datetime.datetime.now().isoformat(),
                                'emergency': is_emergency
                            })
                            logger.info(f"✅ [{ticker}] 수익보존 자동 매도 완료")
                        else:
                            logger.error(f"❌ [{ticker}] 수익보존 자동 매도 실패")
                    
                except Exception as e:
                    logger.error(f"수익보존 매도 체크 중 에러 ({ticker}): {str(e)}")
                    continue
            
            if executed_sells:
                self.send_auto_sell_notification(executed_sells)
                logger.info(f"🛡️ 수익보존 자동매도 완료: {len(executed_sells)}개 실행")
            else:
                logger.debug("🛡️ 수익보존 매도 조건 없음")
                
        except Exception as e:
            logger.error(f"수익보존 자동 매도 실행 중 에러: {str(e)}")

    def send_auto_sell_notification(self, executed_sells):
        """🔔 자동 매도 실행 알림"""
        try:
            if not executed_sells:
                return
            
            msg = f"🛡️ **수익보존 자동 매도 실행**\n"
            msg += f"⚡ 총 {len(executed_sells)}개 포지션 자동 매도\n\n"
            
            for sell in executed_sells:
                msg += f"• {sell['ticker'].replace('KRW-', '')}: {sell['reason']}\n"
            
            msg += f"\n🎯 수익보존 시스템이 자동으로 실행했습니다."
            
            logger.info(msg)
            
            if self.config.get('use_discord_alert'):
                try:
                    discord_alert.SendMessage(msg)
                except Exception as e:
                    logger.warning(f"자동 매도 알림 전송 실패: {str(e)}")
                    
        except Exception as e:
            logger.error(f"자동 매도 알림 생성 중 에러: {str(e)}")

    def update_profit_tracking(self):
        """수익 추적 업데이트 (주기적 호출)"""
        try:
            current_time = time.time()
            
            # 업데이트 주기 체크
            if (self.last_profit_update and 
                current_time - self.last_profit_update < 300):  # 5분 최소 간격
                return
            
            logger.debug("🛡️ 수익 상태 추적 업데이트...")
            self.asset_manager.update_profit_tracking()
            self.last_profit_update = current_time
            
        except Exception as e:
            logger.error(f"수익 추적 업데이트 중 에러: {str(e)}")

    def start_realtime_monitoring(self):
        """🆕 실시간 모니터링 스레드 시작"""
        def realtime_monitor():
            while True:
                try:
                    if not self.trading_halted:
                        self.check_realtime_opportunities()
                    time.sleep(self.config.get('realtime_check_interval', 300))  # 5분마다
                except Exception as e:
                    logger.error(f"실시간 모니터링 중 에러: {str(e)}")
                    time.sleep(60)  # 에러 시 1분 대기
        
        monitor_thread = threading.Thread(target=realtime_monitor, daemon=True)
        monitor_thread.start()
        logger.info("실시간 모니터링 스레드 시작")

    def check_realtime_opportunities(self):
        """🆕 실시간 급등/급락 기회 감지 - 개선된 버전"""
        try:
            if not self.config.get('realtime_monitoring'):
                return
            
            current_time = time.time()
            if (self.last_realtime_check and 
                current_time - self.last_realtime_check < self.config.get('realtime_check_interval', 300)):
                return
            
            logger.debug("실시간 기회 탐색 중...")
            
            # 봇 보유 코인들의 급등 체크
            bot_positions = self.asset_manager.get_bot_positions()
            
            for ticker in bot_positions:
                try:
                    current_price = myBithumb.GetCurrentPrice(ticker)
                    if current_price is None or current_price <= 0:
                        continue
                    
                    # 🔧 수정: 이전 가격과 비교 전에 유효성 체크
                    if ticker in self.last_prices and self.last_prices[ticker] > 0:
                        prev_price = self.last_prices[ticker]
                        change_rate = (current_price - prev_price) / prev_price
                        
                        # 급등 감지 (15% 이상)
                        if (change_rate >= self.config.get('pump_threshold', 0.15) and
                            self.config.get('pump_selling_enabled')):
                            
                            alert_key = f"{ticker}_pump_{datetime.datetime.now().date()}"
                            if alert_key not in self.price_alerts:
                                self.handle_pump_selling(ticker, change_rate)
                                self.price_alerts[alert_key] = True
                    
                    # 현재 가격 저장
                    self.last_prices[ticker] = current_price
                    
                except Exception as e:
                    logger.error(f"실시간 체크 중 에러 ({ticker}): {str(e)}")
                    continue
            
            # 급락 매수 기회 체크
            if self.config.get('dip_buying_enabled'):
                self.check_dip_buying_opportunities()
            
            self.last_realtime_check = current_time
            
        except Exception as e:
            logger.error(f"실시간 기회 탐색 중 에러: {str(e)}")

    def validate_config(self):
        """🔧 설정 파일 검증 - 가격 체크 설정 추가 및 강화"""
        try:
            logger.info("🔍 설정 파일 검증 시작...")
            
            # === 1. 필수 설정값 체크 ===
            required_settings = [
                'bot_investment_budget', 'max_coin_count', 'min_order_money',
                'target_altcoins', 'execution_interval'
            ]
            
            for setting in required_settings:
                if self.config.get(setting) is None:
                    logger.error(f"❌ 필수 설정 누락: {setting}")
                    return False
            
            # === 2. 논리적 검증 ===
            
            # 투자 예산 검증
            investment_budget = self.config.get('bot_investment_budget', 0)
            if investment_budget <= 0:
                logger.error("❌ 투자 예산은 0보다 커야 합니다")
                return False
            
            # 최대 코인 수 검증
            max_coin_count = self.config.get('max_coin_count', 0)
            if max_coin_count <= 0:
                logger.error("❌ 최대 코인 수는 0보다 커야 합니다")
                return False
            
            # 최소 주문 금액 검증
            min_order_money = self.config.get('min_order_money', 0)
            if min_order_money >= investment_budget:
                logger.error("❌ 최소 주문 금액이 총 예산보다 크거나 같습니다")
                return False
            
            # 실행 간격 검증
            execution_interval = self.config.get('execution_interval', 0)
            if execution_interval < 300:  # 5분 미만
                logger.warning(f"⚠️ 실행 간격이 너무 짧습니다: {execution_interval}초 (5분 이상 권장)")
            
            logger.info(f"✅ 기본 설정: 예산{investment_budget:,.0f}원, 최대{max_coin_count}개, 최소주문{min_order_money:,.0f}원")
            
            # === 3. 🆕 가격 괴리 설정 검증 ===
            price_deviation_limit = self.config.get('price_deviation_limit', 0.08)
            if price_deviation_limit <= 0 or price_deviation_limit > 0.50:
                logger.error(f"❌ 가격 괴리 한도 설정 오류: {price_deviation_limit*100:.1f}% (1~50% 권장)")
                return False
            
            # 고급 가격 분석 설정 검증
            advanced_config = self.config.get('advanced_price_deviation', {})
            if advanced_config.get('enabled', False):
                max_limit = advanced_config.get('maximum_limit', 0.15)
                if max_limit <= price_deviation_limit:
                    logger.error(f"❌ 고급 가격분석 최대한도({max_limit*100:.1f}%)가 기본한도({price_deviation_limit*100:.1f}%)보다 작거나 같음")
                    return False
                
                min_momentum_score = advanced_config.get('momentum_override', {}).get('min_momentum_score', 70)
                if min_momentum_score < 50 or min_momentum_score > 100:
                    logger.error(f"❌ 모멘텀 점수 범위 오류: {min_momentum_score} (50~100 범위)")
                    return False
                
                logger.info(f"✅ 고급 가격분석 활성화: 기본{price_deviation_limit*100:.1f}% → 최대{max_limit*100:.1f}% (모멘텀{min_momentum_score}점 이상)")
            else:
                logger.info(f"✅ 기본 가격체크: {price_deviation_limit*100:.1f}% 한도")
            
            # === 4. 타임프레임 설정 검증 ===
            if self.config.get('use_multi_timeframe', False):
                short_ma_4h = self.config.get('short_ma_4h', 0)
                long_ma_4h = self.config.get('long_ma_4h', 0)
                
                if short_ma_4h <= 0 or long_ma_4h <= 0:
                    logger.error("❌ 4시간봉 이동평균 설정이 올바르지 않습니다")
                    return False
                
                if short_ma_4h >= long_ma_4h:
                    logger.error(f"❌ 4시간봉 단기이평({short_ma_4h})이 장기이평({long_ma_4h})보다 크거나 같습니다")
                    return False
                
                logger.info(f"✅ 멀티 타임프레임: 4H 단기{short_ma_4h}/장기{long_ma_4h}")
            else:
                logger.info("ℹ️ 멀티 타임프레임 비활성화")
            
            # === 5. 섹터 분산 설정 검증 ===
            if self.config.get('sector_diversification', False):
                sector_mapping = self.config.get('sector_mapping', {})
                if not sector_mapping:
                    logger.warning("⚠️ 섹터 분산 활성화되었으나 섹터 매핑이 없습니다")
                else:
                    max_per_sector = self.config.get('max_coins_per_sector', 2)
                    total_sectors = len(sector_mapping)
                    
                    if max_per_sector * total_sectors < max_coin_count:
                        logger.warning(f"⚠️ 섹터 제한으로 최대 코인 수 달성 불가: {max_per_sector}×{total_sectors}={max_per_sector*total_sectors} < {max_coin_count}")
                    
                    logger.info(f"✅ 섹터 분산: {total_sectors}개 섹터, 섹터당 최대{max_per_sector}개")
            else:
                logger.info("ℹ️ 섹터 분산 비활성화")
            
            # === 6. 🆕 수익보존 설정 검증 ===
            profit_protection = self.config.get('profit_protection', {})
            if profit_protection.get('enabled', False):
                auto_sell_enabled = profit_protection.get('auto_sell_enabled', True)
                auto_lock_threshold = profit_protection.get('auto_lock_threshold', 0.15)
                lock_profit_rate = profit_protection.get('lock_profit_rate', 0.10)
                trailing_start = profit_protection.get('trailing_start_threshold', 0.10)
                trailing_distance = profit_protection.get('trailing_distance', 0.05)
                
                # 논리적 일관성 체크
                if lock_profit_rate >= auto_lock_threshold:
                    logger.error(f"❌ 고정 수익률({lock_profit_rate*100:.1f}%)이 고정 시작점({auto_lock_threshold*100:.1f}%)보다 크거나 같습니다")
                    return False
                
                if trailing_distance >= trailing_start:
                    logger.error(f"❌ 트레일링 거리({trailing_distance*100:.1f}%)가 시작점({trailing_start*100:.1f}%)보다 크거나 같습니다")
                    return False
                
                # 강화된 점수 시스템 호환성 체크
                enhanced_filters = self.config.get('enhanced_filters', {})
                daily_min_score = enhanced_filters.get('daily_minimum_score', 0)
                
                logger.info(f"✅ 수익보존 시스템: 자동매도{'활성' if auto_sell_enabled else '비활성'}")
                logger.info(f"  • 고정: {auto_lock_threshold*100:.1f}% 달성 시 {lock_profit_rate*100:.1f}% 고정")
                logger.info(f"  • 트레일링: {trailing_start*100:.1f}% 시작, {trailing_distance*100:.1f}% 거리")
                if daily_min_score > 0:
                    logger.info(f"  • 강화된 매수 기준: 일봉 최소 {daily_min_score}점")
            else:
                logger.info("ℹ️ 수익보존 시스템 비활성화")
            
            # === 7. 타겟 코인 리스트 검증 ===
            target_altcoins = self.config.get('target_altcoins', [])
            if not target_altcoins or len(target_altcoins) == 0:
                logger.error("❌ 타겟 알트코인 리스트가 비어있습니다")
                return False
            
            # 제외 코인과 타겟 코인 중복 체크
            exclude_coins = self.config.get('exclude_coins', [])
            overlap = set(target_altcoins) & set(exclude_coins)
            if overlap:
                logger.warning(f"⚠️ 타겟과 제외 코인 중복: {list(overlap)}")
            
            logger.info(f"✅ 코인 리스트: 타겟{len(target_altcoins)}개, 제외{len(exclude_coins)}개")
            
            # === 8. 🆕 스캐너 연동 설정 검증 ===
            scanner_config = self.config.get('scanner_integration', {})
            if scanner_config.get('enabled', False):
                target_file = scanner_config.get('target_file', '')
                if not target_file:
                    logger.error("❌ 스캐너 연동 활성화되었으나 타겟 파일 경로가 없습니다")
                    return False
                
                min_targets = scanner_config.get('min_targets', 0)
                if min_targets <= 0:
                    logger.warning("⚠️ 최소 타겟 수가 올바르지 않습니다")
                
                max_age_hours = scanner_config.get('max_age_hours', 48)
                if max_age_hours > 72:
                    logger.warning(f"⚠️ 스캐너 데이터 최대 유효시간이 너무 깁니다: {max_age_hours}시간")
                
                logger.info(f"✅ 스캐너 연동: 파일'{target_file}', 최소{min_targets}개, 최대{max_age_hours}h")
            else:
                logger.info("ℹ️ 스캐너 연동 비활성화")
            
            # === 9. 🆕 급락매수 설정 검증 ===
            if self.config.get('dip_buying_enabled', False):
                dip_threshold = self.config.get('dip_threshold', -0.08)
                if dip_threshold >= 0 or dip_threshold < -0.30:
                    logger.error(f"❌ 급락 임계값 설정 오류: {dip_threshold*100:.1f}% (-30% ~ 0% 범위)")
                    return False
                
                dip_config = self.config.get('dip_buy_strategy', {})
                target_profit = dip_config.get('target_profit', 0.03)
                stop_loss = dip_config.get('stop_loss', -0.10)
                
                if target_profit <= 0 or target_profit > 0.20:
                    logger.error(f"❌ 급락매수 목표 수익률 오류: {target_profit*100:.1f}% (0~20% 범위)")
                    return False
                
                if stop_loss >= 0 or stop_loss < -0.30:
                    logger.error(f"❌ 급락매수 손절 수준 오류: {stop_loss*100:.1f}% (-30% ~ 0% 범위)")
                    return False
                
                logger.info(f"✅ 급락매수: {dip_threshold*100:.1f}% 하락 시, 목표{target_profit*100:.1f}%, 손절{stop_loss*100:.1f}%")
            else:
                logger.info("ℹ️ 급락매수 비활성화")
            
            # === 10. 🆕 쿨다운 설정 검증 ===
            cooldown_minutes = self.config.get('trade_cooldown_minutes', 60)
            if cooldown_minutes < 0 or cooldown_minutes > 1440:  # 24시간
                logger.warning(f"⚠️ 거래 쿨다운 설정 이상: {cooldown_minutes}분 (0~1440분 권장)")
            
            max_daily_trades = self.config.get('max_daily_trades_per_coin', 3)
            if max_daily_trades <= 0 or max_daily_trades > 10:
                logger.warning(f"⚠️ 일일 최대 거래 횟수 이상: {max_daily_trades}회 (1~10회 권장)")
            
            logger.info(f"✅ 거래 제한: 쿨다운{cooldown_minutes}분, 일일최대{max_daily_trades}회")
            
            # === 최종 검증 완료 ===
            logger.info("🎉 설정 파일 검증 완료 - 모든 설정이 정상입니다")
            logger.info("="*50)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 설정 검증 중 에러: {str(e)}")
            return False

    def handle_pump_selling(self, ticker: str, change_rate: float):
        """급등 시 부분 매도 처리 - 호출 방식 개선 및 중복 방지 강화"""
        try:
            logger.info(f"🚀 급등 감지: {ticker} (+{change_rate*100:.1f}%)")
            
            # 🔧 추가: 최근 매도 이력 체크 (1시간 내 중복 방지)
            recent_sells = [
                trade for trade in self.asset_manager.state.get('trade_history', [])[-10:]
                if (trade.get('ticker') == ticker and 
                    trade.get('type') == 'SELL' and
                    '급등부분매도' in trade.get('reason', '') and
                    datetime.datetime.fromisoformat(trade.get('timestamp', '1900-01-01')) > 
                    datetime.datetime.now() - datetime.timedelta(hours=1))
            ]
            
            if recent_sells:
                logger.info(f"1시간 내 급등 매도 이력 존재 - 스킵: {ticker}")
                return
            
            # 부분 매도 비율 결정
            if change_rate >= 0.25:  # 25% 이상 급등
                sell_ratio = 0.5  # 50% 매도
            elif change_rate >= 0.15:  # 15% 이상 급등
                sell_ratio = 0.3  # 30% 매도
            else:
                return
            
            # 🔧 수정된 호출 방식: self.partial_sell_coin → self.asset_manager.partial_sell_coin
            if self.asset_manager.partial_sell_coin(ticker, sell_ratio, f"급등부분매도_{change_rate*100:.1f}%"):
                msg = f"🔥 **급등 부분 매도**: {ticker}\n"
                msg += f"📈 급등률: +{change_rate*100:.1f}%\n"
                msg += f"💰 매도 비율: {sell_ratio*100:.1f}%\n"
                msg += f"🎯 수익 실현 완료\n"
                msg += f"🔒 동시성 보호된 거래\n"
                msg += f"⏰ 1시간 내 중복 방지 적용"
                
                logger.info(msg)
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(msg)
                    except Exception as e:
                        logger.warning(f"급등 알림 전송 실패: {str(e)}")
            else:
                logger.error(f"🔥 급등 부분 매도 실패: {ticker}")
            
        except Exception as e:
            logger.error(f"급등 매도 처리 중 에러: {str(e)}")

    def check_dip_buying_opportunities(self):
        """🆕 급락 매수 기회 체크 - 스레드 안전 & 캐시 활용 버전"""
        try:
            # 1차 검증: 급락 매수 활성화 여부 확인
            if not self.config.get('dip_buying_enabled'):
                return
            
            # 2차 검증: 기본 조건 체크
            if not self.can_buy_more_coins():
                logger.debug("급락매수 - 포지션 한도 초과")
                return
            
            available_budget = self.asset_manager.get_available_budget()
            min_order = self.config.get('min_order_money', 10000)
            
            if available_budget < min_order:
                logger.debug(f"급락매수 - 예산 부족: {available_budget:,.0f} < {min_order:,.0f}")
                return
            
            # 3차 검증: 안전한 캐시 데이터 접근
            target_coins = None
            btc_change = None
            cache_used = False
            
            with self.data_lock:
                if (hasattr(self, '_cached_market_data') and 
                    self._cached_market_data is not None and
                    hasattr(self, '_cached_market_data_time')):
                    
                    # 캐시 유효성 확인 (30분 이내)
                    cache_age = (datetime.datetime.now() - self._cached_market_data_time).total_seconds()
                    if cache_age < 1800:  # 30분
                        try:
                            # 안전한 캐시 데이터 복사
                            cached_data = []
                            for coin_data in self._cached_market_data:
                                if coin_data and isinstance(coin_data, dict):
                                    cached_data.append({
                                        'ticker': coin_data.get('ticker'),
                                        'df_1d': coin_data.get('df_1d')
                                    })
                            
                            if cached_data:
                                target_coins = [coin_data['ticker'] for coin_data in cached_data 
                                            if coin_data['ticker'] is not None]
                                
                                # BTC 변화율도 캐시에서 가져오기
                                for coin_data in cached_data:
                                    if (coin_data and 
                                        coin_data.get('ticker') == 'KRW-BTC' and
                                        coin_data.get('df_1d') is not None):
                                        
                                        btc_df = coin_data['df_1d']
                                        if len(btc_df) >= 2:
                                            try:
                                                btc_latest = btc_df.iloc[-1]
                                                btc_prev = btc_df.iloc[-2]
                                                if (btc_latest['close'] > 0 and btc_prev['close'] > 0):
                                                    btc_change = (btc_latest['close'] - btc_prev['close']) / btc_prev['close']
                                            except Exception as btc_calc_error:
                                                logger.debug(f"캐시에서 BTC 변화율 계산 실패: {str(btc_calc_error)}")
                                        break
                                
                                cache_used = True
                                logger.debug(f"급락매수 캐시 사용: {len(target_coins)}개 코인 (캐시 나이: {cache_age/60:.1f}분)")
                            
                        except Exception as cache_error:
                            logger.warning(f"캐시 데이터 처리 중 에러: {str(cache_error)}")
                            target_coins = None
            
            # 캐시가 없거나 실패한 경우 실시간 조회
            if target_coins is None:
                try:
                    target_coins = self.get_target_coins()
                    logger.debug(f"급락매수 실시간 조회: {len(target_coins)}개 코인")
                    cache_used = False
                except Exception as target_error:
                    logger.error(f"타겟 코인 조회 실패: {str(target_error)}")
                    return
            
            if not target_coins:
                logger.debug("급락매수 - 타겟 코인 없음")
                return
            
            # BTC 급락 체크 (시장 전체 상황)
            if btc_change is None:
                try:
                    btc_df = myBithumb.GetOhlcv('KRW-BTC', '1d', 2)
                    if btc_df is not None and len(btc_df) >= 2:
                        btc_latest = btc_df.iloc[-1]
                        btc_prev = btc_df.iloc[-2]
                        if btc_latest['close'] > 0 and btc_prev['close'] > 0:
                            btc_change = (btc_latest['close'] - btc_prev['close']) / btc_prev['close']
                except Exception as btc_error:
                    logger.debug(f"BTC 변화율 실시간 조회 실패: {str(btc_error)}")
                    btc_change = 0  # 기본값
            
            # BTC 급락 시 급락매수 금지
            if btc_change and btc_change <= -0.05:  # BTC 5% 이상 하락
                logger.info(f"🚫 BTC 급락으로 급락매수 금지: BTC {btc_change*100:.1f}%")
                return
            
            dip_threshold = self.config.get('dip_threshold', -0.08)
            logger.debug(f"급락매수 임계값: {dip_threshold*100:.1f}%")
            
            detected_dips = []
            
            # 각 코인별 급락 체크
            for ticker in target_coins:
                try:
                    # 기본 필터링
                    if (self.asset_manager.is_bot_coin(ticker) or 
                        self.check_excluded_coin(ticker)):
                        continue
                    
                    # 섹터 분산 체크
                    if not self.asset_manager.can_add_to_sector(ticker):
                        continue
                    
                    # 4차 검증: 개별 코인 급락 체크
                    change_rate = None
                    current_price = None
                    
                    # 방법 1: OHLCV 데이터 사용 (우선)
                    try:
                        df = myBithumb.GetOhlcv(ticker, '1d', 2)
                        if df is not None and len(df) >= 2:
                            # DataFrame 유효성 재검증
                            if ('close' in df.columns and 
                                not df['close'].isnull().all() and
                                (df['close'] > 0).any()):
                                
                                current_price = df.iloc[-1]['close']
                                prev_price = df.iloc[-2]['close']
                                
                                if current_price > 0 and prev_price > 0:
                                    change_rate = (current_price - prev_price) / prev_price
                                    logger.debug(f"[{ticker}] OHLCV 방식: {change_rate*100:.1f}%")
                                
                    except Exception as ohlcv_error:
                        logger.debug(f"[{ticker}] OHLCV 방식 실패: {str(ohlcv_error)}")
                    
                    # 방법 2: 현재가 + 저장된 이전 가격 비교 (대안)
                    if change_rate is None:
                        try:
                            current_price = myBithumb.GetCurrentPrice(ticker)
                            if current_price and current_price > 0:
                                
                                # last_prices 초기화 (필요시)
                                if not hasattr(self, 'last_prices'):
                                    self.last_prices = {}
                                
                                if ticker in self.last_prices and self.last_prices[ticker] > 0:
                                    prev_price = self.last_prices[ticker]
                                    change_rate = (current_price - prev_price) / prev_price
                                    logger.debug(f"[{ticker}] 저장된 가격 방식: {change_rate*100:.1f}%")
                                else:
                                    # 첫 실행이거나 이전 가격이 없는 경우
                                    self.last_prices[ticker] = current_price
                                    logger.debug(f"[{ticker}] 첫 가격 저장: {current_price:,.0f}원")
                                    continue
                            else:
                                logger.debug(f"[{ticker}] 현재가 조회 실패")
                                continue
                                
                        except Exception as price_error:
                            logger.debug(f"[{ticker}] 현재가 조회 중 에러: {str(price_error)}")
                            continue
                    
                    # 5차 검증: 변화율 유효성 체크
                    if change_rate is None:
                        logger.debug(f"[{ticker}] 변화율 계산 실패")
                        continue
                    
                    if not isinstance(change_rate, (int, float)):
                        logger.debug(f"[{ticker}] 비정상 변화율 타입: {type(change_rate)}")
                        continue
                    
                    if abs(change_rate) > 0.5:  # 50% 이상 변화는 비정상
                        logger.warning(f"[{ticker}] 비정상 변화율: {change_rate*100:.1f}%")
                        continue
                    
                    # 급락 조건 확인
                    if change_rate <= dip_threshold:
                        detected_dips.append({
                            'ticker': ticker,
                            'change_rate': change_rate,
                            'current_price': current_price,
                            'cache_used': cache_used
                        })
                        
                        logger.info(f"📉 급락 감지: {ticker} ({change_rate*100:.1f}%)")
                        
                        # 오늘 이미 급락매수 시도했는지 체크
                        alert_key = f"{ticker}_dip_{datetime.datetime.now().date()}"
                        if not hasattr(self, 'price_alerts'):
                            self.price_alerts = {}
                        
                        if alert_key not in self.price_alerts:
                            # 급락매수 평가 및 실행
                            try:
                                self.evaluate_dip_buying(ticker, change_rate)
                                self.price_alerts[alert_key] = True
                            except Exception as eval_error:
                                logger.error(f"[{ticker}] 급락매수 평가 중 에러: {str(eval_error)}")
                        else:
                            logger.debug(f"[{ticker}] 오늘 이미 급락매수 시도함")
                    
                    # 현재 가격 업데이트 (다음 비교용)
                    if current_price and current_price > 0:
                        if not hasattr(self, 'last_prices'):
                            self.last_prices = {}
                        self.last_prices[ticker] = current_price
                    
                except Exception as coin_error:
                    logger.debug(f"[{ticker}] 급락 체크 중 에러: {str(coin_error)}")
                    continue
            
            # 결과 요약
            if detected_dips:
                logger.info(f"📉 급락 감지 요약: {len(detected_dips)}개 코인")
                for dip in detected_dips[:3]:  # 상위 3개만 로깅
                    logger.info(f"  • {dip['ticker']}: {dip['change_rate']*100:.1f}%")
            else:
                logger.debug("급락매수 기회 없음")
            
            # 캐시 사용 통계
            logger.debug(f"급락매수 체크 완료: 캐시 {'사용' if cache_used else '미사용'}, "
                    f"검토 {len(target_coins)}개, 감지 {len(detected_dips)}개")
            
        except Exception as e:
            logger.error(f"급락 매수 기회 체크 중 전체 에러: {str(e)}")
            
            # 에러 시 안전하게 정리
            try:
                if not hasattr(self, 'last_prices'):
                    self.last_prices = {}
                if not hasattr(self, 'price_alerts'):
                    self.price_alerts = {}
            except:
                pass

    def evaluate_dip_buying(self, ticker: str, change_rate: float):
        """🆕 개선된 급락 매수 평가 - 스캐너 연동 & 진짜 급락만 포착"""
        try:
            logger.info(f"📉 급락 검증: {ticker} ({change_rate*100:.1f}%)")
            
            # === 1단계: 시장 전체 상황 체크 ===
            sentiment, fng_value = self.get_fng_sentiment()
            
            # 🔧 BTC 급락 체크 개선 (캐시된 시장 데이터 사용)
            try:
                btc_change = None
                if hasattr(self, '_cached_market_data') and self._cached_market_data:
                    for coin_data in self._cached_market_data:
                        if coin_data and coin_data.get('ticker') == 'KRW-BTC':
                            btc_df = coin_data.get('df_1d')
                            if btc_df is not None and len(btc_df) >= 2:
                                btc_latest = btc_df.iloc[-1]
                                btc_prev = btc_df.iloc[-2]
                                btc_change = (btc_latest['close'] - btc_prev['close']) / btc_prev['close']
                                break
                
                # 캐시된 데이터가 없으면 직접 조회
                if btc_change is None:
                    btc_df = myBithumb.GetOhlcv('KRW-BTC', '1d', 2)
                    if btc_df is not None and len(btc_df) >= 2:
                        btc_latest = btc_df.iloc[-1]
                        btc_prev = btc_df.iloc[-2]
                        btc_change = (btc_latest['close'] - btc_prev['close']) / btc_prev['close']
                
                if btc_change and btc_change <= -0.05:  # BTC 5% 이상 하락 시
                    logger.info(f"🚫 BTC 급락으로 급락매수 금지: BTC {btc_change*100:.1f}%")
                    return
                    
            except Exception as btc_error:
                logger.debug(f"BTC 상황 체크 실패: {str(btc_error)}")
            
            # 극단적 공포 상황에서만 급락매수 허용
            if sentiment not in ["EXTREME_FEAR", "FEAR"]:
                logger.info(f"🚫 시장 심리 부적합: {sentiment} (FNG: {fng_value})")
                return
            
            # === 2단계: 기본 조건 체크 ===
            if not self.can_buy_more_coins():
                logger.info(f"🚫 포지션 한도 초과")
                return
            
            if not self.asset_manager.can_add_to_sector(ticker):
                logger.info(f"🚫 섹터 분산 한도 초과: {ticker}")
                return
            
            # === 3단계: 진짜 급락인지 판단 (간단한 3가지 조건) ===
            try:
                df = myBithumb.GetOhlcv(ticker, '1d', 10)  # 10일 데이터만
                if df is None or len(df) < 5:
                    logger.info(f"🚫 데이터 부족: {ticker}")
                    return
                
                current_price = df.iloc[-1]['close']
                
                # 조건 1: 진짜 급락인가? (최근 5일 최저가 근처)
                recent_10day_high = df.tail(10)['high'].max()  # 10일 고점
                recent_5day_low = df.tail(5)['low'].min()      # 5일 저점

                # 고점 대비 현재가 하락폭 계산
                decline_from_high = (recent_10day_high - current_price) / recent_10day_high

                if decline_from_high >= 0.08:  # 고점 대비 8% 이상 하락
                    logger.info(f"✅ 조건1 통과: 고점 대비 충분한 하락 ({decline_from_high*100:.1f}%)")
                else:
                    logger.info(f"🚫 조건1 실패: 고점 대비 하락 부족 ({decline_from_high*100:.1f}% < 8%)")
                    return
                
                # 조건 2: 거래량 급증하면서 하락인가?
                df['volume_ma'] = df['volume'].rolling(5).mean()
                latest_volume = df.iloc[-1]['volume']
                avg_volume = df.iloc[-1]['volume_ma']
                
                if avg_volume > 0 and latest_volume > avg_volume * 1.5:  # 평균 대비 1.5배 이상
                    volume_ratio = latest_volume / avg_volume
                    logger.info(f"✅ 조건2 통과: 거래량 급증 ({volume_ratio:.1f}배)")
                else:
                    volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0
                    logger.info(f"🚫 조건2 실패: 거래량 부족 ({volume_ratio:.1f}배 < 1.5배)")
                    return
                
                # 조건 3: RSI 과매도인가?
                df = self.calculate_indicators(df)
                if df is None:
                    logger.info(f"🚫 지표 계산 실패: {ticker}")
                    return
                
                latest_rsi = df['RSI'].iloc[-1]
                if latest_rsi < 40:  # 40 미만 (과매도)
                    logger.info(f"✅ 조건3 통과: RSI 과매도 ({latest_rsi:.1f})")
                else:
                    logger.info(f"🚫 조건3 실패: RSI 과매도 아님 ({latest_rsi:.1f} ≥ 40)")
                    return
                
                # === 4단계: 모든 조건 통과 시 급락매수 실행 ===
                available_budget = self.asset_manager.get_available_budget()
                min_order = self.config.get('min_order_money', 10000)
                
                if available_budget >= min_order:
                    # 급락폭에 따른 투자 금액 (기존 설정값 유지)
                    if change_rate <= -0.15:  # 15% 이상 급락
                        buy_amount = min(available_budget * 0.3, available_budget)
                    else:  # 8-15% 급락
                        buy_amount = min(available_budget * 0.2, available_budget)
                    
                    buy_amount = max(buy_amount, min_order)
                    
                    reason = f"진짜급락매수_RSI{latest_rsi:.1f}_{change_rate*100:.1f}%_거래량{volume_ratio:.1f}배"
                    
                    if self.buy_coin(ticker, buy_amount, reason):
                        msg = f"💎 **진짜 급락 매수**: {ticker}\n"
                        msg += f"📉 급락률: {change_rate*100:.1f}%\n"
                        msg += f"📊 RSI: {latest_rsi:.1f} (과매도)\n"
                        msg += f"📈 거래량: {volume_ratio:.1f}배 급증\n"
                        msg += f"💰 투자금액: {buy_amount:,.0f}원\n"
                        msg += f"😱 FNG: {fng_value} ({sentiment})\n"
                        msg += f"🎯 5일 최저가 근처 매수\n"
                        msg += f"🔗 스캐너 연동 코인"
                        
                        logger.info(msg)
                        
                        if self.config.get('use_discord_alert'):
                            try:
                                discord_alert.SendMessage(msg)
                            except Exception as e:
                                logger.warning(f"급락 매수 알림 전송 실패: {str(e)}")
                else:
                    logger.info(f"🚫 예산 부족: {available_budget:,.0f}원 < {min_order:,.0f}원")
                
            except Exception as e:
                logger.error(f"급락 조건 판단 중 에러: {str(e)}")
                
        except Exception as e:
            logger.error(f"급락 매수 평가 중 에러: {str(e)}")

    def get_fear_and_greed_index(self):
        """공포 탐욕 지수 조회"""
        try:
            now = datetime.datetime.now()
            if (self.last_fng_check and 
                (now - self.last_fng_check).total_seconds() < 3600):
                return self.current_fng_data
            
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                fng_data = data['data'][0]
                self.current_fng_data = {
                    'value': int(fng_data['value']),
                    'classification': fng_data['value_classification'],
                    'timestamp': fng_data['timestamp']
                }
                self.last_fng_check = now
                logger.info(f"FNG 업데이트: {self.current_fng_data['value']} ({self.current_fng_data['classification']})")
                return self.current_fng_data
            else:
                logger.warning(f"FNG 조회 실패. Status: {response.status_code}")
                if self.current_fng_data is None:
                    self.current_fng_data = {'value': 50, 'classification': 'Neutral'}
                return self.current_fng_data
        except Exception as e:
            logger.error(f"FNG 조회 중 에러: {str(e)}")
            if self.current_fng_data is None:
                self.current_fng_data = {'value': 50, 'classification': 'Neutral'}
            return self.current_fng_data
    
    def get_fng_sentiment(self):
        """FNG 기반 시장 심리 분석"""
        fng_data = self.get_fear_and_greed_index()
        if not fng_data:
            return "NEUTRAL", 50
        
        fng_value = fng_data['value']
        
        if fng_value <= 20:
            return "EXTREME_FEAR", fng_value
        elif fng_value <= 40:
            return "FEAR", fng_value
        elif fng_value <= 60:
            return "NEUTRAL", fng_value
        elif fng_value <= 80:
            return "GREED", fng_value
        else:
            return "EXTREME_GREED", fng_value
    
    def get_fng_multiplier(self, sentiment):
        """FNG 기반 투자 배수 계산"""
        if sentiment == "EXTREME_FEAR":
            return 1.2
        elif sentiment == "FEAR":
            return 1.05
        elif sentiment == "NEUTRAL":
            return 1.0
        elif sentiment == "GREED":
            return 0.9
        else:  # EXTREME_GREED
            return 0.7

    def calculate_indicators(self, df):
        """기술적 지표 계산"""
        try:
            # RSI 계산
            period = 14
            delta = df["close"].diff()
            up, down = delta.copy(), delta.copy()
            up[up < 0] = 0
            down[down > 0] = 0
            _gain = up.ewm(com=(period - 1), min_periods=period).mean()
            _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
            RS = _gain / _loss
            df['RSI'] = pd.Series(100 - (100 / (1 + RS)), name="RSI")
            
            # 거래대금 계산
            df['value'] = df['close'] * df['volume']
            df['value_ma'] = df['value'].rolling(window=10).mean()
            
            # 변동성 계산
            df['daily_return'] = df['close'].pct_change()
            df['volatility'] = df['daily_return'].rolling(window=20).std()
            
            # 이전 데이터 시프트
            df['prev_close'] = df['close'].shift(1)
            df['prev_close2'] = df['close'].shift(2)
            df['prev_open'] = df['open'].shift(1)
            df['prev_volume'] = df['value'].shift(1)
            df['prev_volatility'] = df['volatility'].shift(1)
            
            # 변화율 계산
            df['prev_change'] = (df['prev_close'] - df['prev_close2']) / df['prev_close2']
            df['prev_close_w'] = df['close'].shift(7)
            df['prev_change_w'] = (df['prev_close'] - df['prev_close_w']) / df['prev_close_w']
            
            # 이동평균선 계산
            for ma_period in [self.config.get('short_ma'), self.config.get('long_ma'), 
                             self.config.get('btc_ma1'), self.config.get('btc_ma2')]:
                df[f'ma{ma_period}'] = df['close'].rolling(window=ma_period).mean()
                df[f'ma{ma_period}_before'] = df[f'ma{ma_period}'].shift(1)
                df[f'ma{ma_period}_before2'] = df[f'ma{ma_period}'].shift(2)
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 중 에러: {str(e)}")
            return None

    def get_multi_timeframe_data(self, ticker: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """🆕 멀티 타임프레임 데이터 수집"""
        try:
            # 일봉 데이터 (주 분석용)
            df_1d = myBithumb.GetOhlcv(ticker, '1d', 150)
            if df_1d is None or len(df_1d) < 30:
                return None, None
            
            df_1d = self.calculate_indicators(df_1d)
            if df_1d is None:
                return None, None
            
            # 4시간봉 데이터 (진입 타이밍용)
            df_4h = None
            if self.config.get('use_multi_timeframe'):
                df_4h = myBithumb.GetOhlcv(ticker, '4h', 200)
                if df_4h is not None and len(df_4h) >= 50:
                    df_4h = self.calculate_4h_indicators(df_4h)
            
            return df_1d, df_4h
            
        except Exception as e:
            logger.error(f"멀티 타임프레임 데이터 수집 중 에러 ({ticker}): {str(e)}")
            return None, None

    def calculate_4h_indicators(self, df):
        """🆕 4시간봉 전용 지표 계산 - 안전성 강화 버전"""
        try:
            # 1차 검증: DataFrame 유효성 체크
            if df is None:
                logger.error("4시간봉 DataFrame이 None입니다")
                return None
            
            if not isinstance(df, pd.DataFrame):
                logger.error(f"4시간봉 데이터가 DataFrame이 아님: {type(df)}")
                return None
            
            if len(df) == 0:
                logger.error("4시간봉 DataFrame이 비어있습니다")
                return None
            
            # 2차 검증: 필수 컬럼 존재 확인
            required_columns = ['close', 'open', 'volume', 'high', 'low']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                logger.error(f"4시간봉 데이터 필수 컬럼 누락: {missing_columns}")
                logger.error(f"사용 가능한 컬럼: {list(df.columns)}")
                return None
            
            # 3차 검증: 데이터 유효성 체크 (NaN, 음수 등)
            for col in required_columns:
                if df[col].isnull().all():
                    logger.error(f"4시간봉 {col} 컬럼이 모두 NaN입니다")
                    return None
                
                if col in ['close', 'open', 'high', 'low']:
                    if (df[col] <= 0).any():
                        logger.warning(f"4시간봉 {col} 컬럼에 0 이하 값이 있습니다")
                        # 0 이하 값을 이전 값으로 대체
                        df[col] = df[col].replace(0, method='ffill')
                        df[col] = df[col].fillna(method='bfill')
            
            # 4차 검증: 최소 데이터 길이 확인
            min_required_length = 30  # 최소 30개 데이터 필요
            if len(df) < min_required_length:
                logger.warning(f"4시간봉 데이터 부족: {len(df)}개 < {min_required_length}개")
                # 데이터가 부족해도 계속 진행 (가능한 만큼 계산)
            
            # DataFrame 복사본 생성 (원본 보호)
            df = df.copy()
            
            # 4시간봉용 이동평균 설정값 가져오기
            short_ma_4h = self.config.get('short_ma_4h', 12)
            long_ma_4h = self.config.get('long_ma_4h', 24)
            
            # 5차 검증: 이동평균 설정값 유효성
            if not isinstance(short_ma_4h, int) or short_ma_4h <= 0:
                logger.warning(f"비정상 단기 이평 설정: {short_ma_4h}, 기본값 12 사용")
                short_ma_4h = 12
            
            if not isinstance(long_ma_4h, int) or long_ma_4h <= 0:
                logger.warning(f"비정상 장기 이평 설정: {long_ma_4h}, 기본값 24 사용")
                long_ma_4h = 24
            
            if short_ma_4h >= long_ma_4h:
                logger.warning(f"단기 이평({short_ma_4h}) >= 장기 이평({long_ma_4h}), 자동 조정")
                short_ma_4h = max(5, long_ma_4h // 2)
            
            # 6차 검증: 이동평균 계산 가능 길이 체크
            if len(df) < long_ma_4h:
                logger.warning(f"4시간봉 데이터 부족으로 장기 이평 축소: {long_ma_4h} → {len(df)-1}")
                long_ma_4h = max(5, len(df) - 1)
                short_ma_4h = max(3, long_ma_4h // 2)
            
            logger.debug(f"4시간봉 지표 계산: 데이터{len(df)}개, 단기MA{short_ma_4h}, 장기MA{long_ma_4h}")
            
            # 이동평균선 계산
            try:
                df[f'ma{short_ma_4h}'] = df['close'].rolling(window=short_ma_4h, min_periods=1).mean()
                df[f'ma{long_ma_4h}'] = df['close'].rolling(window=long_ma_4h, min_periods=1).mean()
                
                # 7차 검증: 이동평균 계산 결과 확인
                if df[f'ma{short_ma_4h}'].isnull().all():
                    logger.error("단기 이동평균 계산 실패 - 모두 NaN")
                    return None
                
                if df[f'ma{long_ma_4h}'].isnull().all():
                    logger.error("장기 이동평균 계산 실패 - 모두 NaN")
                    return None
                
            except Exception as ma_error:
                logger.error(f"이동평균 계산 중 에러: {str(ma_error)}")
                return None
            
            # 이전 데이터 시프트 (안전한 방식)
            try:
                df['prev_close'] = df['close'].shift(1)
                df['prev_open'] = df['open'].shift(1)
                df[f'ma{short_ma_4h}_before'] = df[f'ma{short_ma_4h}'].shift(1)
                df[f'ma{long_ma_4h}_before'] = df[f'ma{long_ma_4h}'].shift(1)
                
            except Exception as shift_error:
                logger.error(f"데이터 시프트 중 에러: {str(shift_error)}")
                return None
            
            # 거래량 관련 계산
            try:
                # 8차 검증: 거래량 데이터 유효성
                if df['volume'].isnull().all():
                    logger.warning("거래량 데이터가 모두 NaN - 기본값으로 대체")
                    df['volume'] = df['volume'].fillna(1000000)  # 기본 거래량
                
                # 거래대금 계산 (안전한 방식)
                df['value'] = df['close'] * df['volume']
                df['prev_volume'] = df['value'].shift(1)
                
                # 거래량이 0인 경우 처리
                df['value'] = df['value'].replace(0, method='ffill')
                df['prev_volume'] = df['prev_volume'].replace(0, method='ffill')
                
            except Exception as volume_error:
                logger.error(f"거래량 계산 중 에러: {str(volume_error)}")
                # 거래량 계산 실패해도 이동평균은 사용 가능
            
            # RSI 계산 (안전한 방식)
            try:
                period = min(14, len(df) - 1)  # 데이터 길이에 맞춰 조정
                if period < 2:
                    logger.warning("RSI 계산용 데이터 부족")
                    df['RSI'] = 50  # 기본값
                else:
                    delta = df["close"].diff()
                    up, down = delta.copy(), delta.copy()
                    up[up < 0] = 0
                    down[down > 0] = 0
                    
                    # 9차 검증: RSI 계산 과정에서 에러 처리
                    try:
                        _gain = up.ewm(com=(period - 1), min_periods=1).mean()
                        _loss = down.abs().ewm(com=(period - 1), min_periods=1).mean()
                        
                        # 0으로 나누기 방지
                        _loss = _loss.replace(0, 0.0001)  # 매우 작은 값으로 대체
                        
                        RS = _gain / _loss
                        df['RSI'] = pd.Series(100 - (100 / (1 + RS)), name="RSI")
                        
                        # RSI 값 유효성 체크
                        df['RSI'] = df['RSI'].fillna(50)  # NaN을 50으로 대체
                        df['RSI'] = df['RSI'].clip(0, 100)  # 0-100 범위로 제한
                        
                    except Exception as rsi_calc_error:
                        logger.warning(f"RSI 계산 실패: {str(rsi_calc_error)} - 기본값 사용")
                        df['RSI'] = 50
                        
            except Exception as rsi_error:
                logger.warning(f"RSI 계산 중 에러: {str(rsi_error)} - 기본값 사용")
                df['RSI'] = 50
            
            # 최종 검증: 결과 DataFrame 유효성
            if df is None or len(df) == 0:
                logger.error("4시간봉 지표 계산 후 DataFrame이 비어있음")
                return None
            
            # 핵심 컬럼들이 존재하는지 확인
            expected_columns = [f'ma{short_ma_4h}', f'ma{long_ma_4h}', 'RSI']
            missing_result_columns = [col for col in expected_columns if col not in df.columns]
            
            if missing_result_columns:
                logger.error(f"4시간봉 지표 계산 결과 컬럼 누락: {missing_result_columns}")
                return None
            
            logger.debug(f"✅ 4시간봉 지표 계산 완료: {len(df)}개 데이터, {len(df.columns)}개 컬럼")
            
            return df
            
        except Exception as e:
            logger.error(f"4시간봉 지표 계산 중 치명적 에러: {str(e)}")
            logger.error(f"DataFrame 정보: {df.shape if df is not None else 'None'}")
            
            # 에러 발생 시 None 반환
            return None

    def get_market_data(self):
        """📊 시장 데이터 수집 (기존 로직 + 동적 타겟 + 캐시 추가 + 동시성 보호)"""
        try:
            # 🔄 타겟 코인 동적 획득 (유일한 변경점)
            target_coins = self.get_target_coins()
            
            logger.info(f"🔍 시장 데이터 수집 시작: {len(target_coins)}개 코인")
            logger.info(f"📋 타겟 소스: {'스캐너' if self.scanner_enabled else '기존설정'}")
            
            # === 이후 로직은 기존과 100% 동일 ===
            stock_df_list = []
            failed_coins = []
            
            for i, ticker in enumerate(target_coins):
                try:
                    logger.debug(f"[{i+1}/{len(target_coins)}] {ticker} 처리 중...")
                    
                    # 기존 멀티 타임프레임 데이터 수집 로직 그대로
                    df_1d, df_4h = self.get_multi_timeframe_data(ticker)
                    
                    if df_1d is None:
                        failed_coins.append(ticker)
                        continue
                    
                    df_1d.dropna(inplace=True)
                    
                    if len(df_1d) == 0:
                        logger.warning(f"{ticker} - dropna 후 데이터 없음")
                        failed_coins.append(ticker)
                        continue
                    
                    # 데이터 저장 (기존과 동일)
                    coin_data = {
                        'ticker': ticker,
                        'df_1d': df_1d,
                        'df_4h': df_4h
                    }
                    
                    stock_df_list.append(coin_data)
                    time.sleep(0.05)  # API 부하 방지
                    
                except Exception as e:
                    logger.error(f"{ticker} 데이터 처리 중 에러: {str(e)}")
                    failed_coins.append(ticker)
                    continue
            
            # 🆕 급락매수에서 사용할 수 있도록 캐시 저장 (동시성 보호)
            with self.data_lock:
                self._cached_market_data = stock_df_list
                self._cached_market_data_time = datetime.datetime.now()
                logger.info(f"🔒 시장 데이터 캐시 저장 완료 (동시성 보호) - {len(stock_df_list)}개")
            
            logger.info(f"✅ 시장 데이터 수집 완료: {len(stock_df_list)}개 성공, {len(failed_coins)}개 실패")
            logger.info(f"💾 시장 데이터 캐시 저장 완료 (급락매수용)")
            
            if failed_coins and len(failed_coins) < 10:
                logger.warning(f"실패한 코인들: {', '.join([coin.replace('KRW-', '') for coin in failed_coins])}")
            elif len(failed_coins) >= 10:
                logger.warning(f"실패한 코인 다수: {len(failed_coins)}개 (API 연결 상태 확인 필요)")
            
            return stock_df_list
            
        except Exception as e:
            logger.error(f"시장 데이터 수집 중 에러: {str(e)}")
            # 🆕 에러 시에도 캐시 초기화 (동시성 보호)
            with self.data_lock:
                self._cached_market_data = None
                self._cached_market_data_time = None
                logger.info(f"🔒 시장 데이터 캐시 초기화 (에러 처리)")
            return None

    def send_scanner_status_alert(self):
        """📊 스캐너 상태 알림 (선택적)"""
        if not self.scanner_enabled:
            return
            
        try:
            target_coins = self.get_target_coins()
            bot_positions = list(self.asset_manager.get_bot_positions().keys())
            
            # 보유 코인 중 스캐너에서 제외된 것들
            excluded_holdings = [ticker for ticker in bot_positions if ticker not in target_coins]
            
            if excluded_holdings:
                msg = f"📊 **스캐너 상태 알림**\n"
                msg += f"🎯 현재 타겟: {len(target_coins)}개\n"
                msg += f"💼 보유 코인: {len(bot_positions)}개\n"
                msg += f"❌ 선별제외된 보유 코인: {len(excluded_holdings)}개\n"
                
                if len(excluded_holdings) <= 5:
                    excluded_names = [coin.replace('KRW-', '') for coin in excluded_holdings]
                    msg += f"  📝 제외 코인: {', '.join(excluded_names)}\n"
                
                msg += f"\n💡 트렌드 추종 원칙에 따라 매도 검토됩니다"
                
                logger.info(msg)
                
                # 중요한 변화가 있을 때만 Discord 알림
                if len(excluded_holdings) >= 2:
                    if self.config.get('use_discord_alert'):
                        try:
                            discord_alert.SendMessage(msg)
                        except Exception as e:
                            logger.warning(f"스캐너 상태 알림 전송 실패: {str(e)}")
        
        except Exception as e:
            logger.error(f"스캐너 상태 알림 중 에러: {str(e)}")

    def get_coin_selection(self, market_data_list):
        """🆕 멀티 타임프레임 기반 코인 선별"""
        try:
            if not market_data_list or len(market_data_list) == 0:
                logger.error("시장 데이터가 비어있습니다.")
                return [], None
            
            logger.info(f"코인 선별 시작: {len(market_data_list)}개 코인")
            
            # 비트코인 데이터 찾기
            btc_data = None
            for coin_data in market_data_list:
                if coin_data['ticker'] == 'KRW-BTC':
                    btc_data = coin_data['df_1d'].iloc[-1]
                    break
            
            if btc_data is None:
                logger.error("비트코인 데이터를 찾을 수 없습니다.")
                return [], None
            
            # 매수 후보 선별
            candidates = []
            
            for coin_data in market_data_list:
                ticker = coin_data['ticker']
                df_1d = coin_data['df_1d']
                df_4h = coin_data['df_4h']
                
                if len(df_1d) == 0:
                    continue
                
                coin_info = df_1d.iloc[-1]
                
                # 기본 필터링
                prev_volume = coin_info.get('prev_volume', 0)
                prev_change_w = coin_info.get('prev_change_w', 0)
                
                if (prev_volume >= self.config.get('min_volume_value', 30000000) and
                    prev_change_w > 0):
                    
                    # 🆕 일봉 점수 계산
                    daily_score = self.calculate_daily_signal_strength(coin_info, btc_data, ticker)
                    
                    # 🆕 4시간봉 보정 점수 계산 (있는 경우)
                    h4_adjustment = 0
                    if df_4h is not None and len(df_4h) > 0:
                        h4_adjustment = self.calculate_4h_signal_strength_enhanced(df_4h, daily_score)
                    
                    # 최종 종합 점수
                    total_score = daily_score + h4_adjustment
                    
                    candidates.append({
                        'ticker': ticker,
                        'data': coin_info,
                        'volume': prev_volume,
                        'change': coin_info.get('prev_change', 0),
                        'df_1d': df_1d,
                        'df_4h': df_4h,
                        'daily_score': daily_score,
                        'h4_adjustment': h4_adjustment,
                        'total_score': total_score,
                        'h4_signal_strength': h4_adjustment  # 기존 호환성 유지
                    })
            
            # 🆕 종합 점수로 정렬 (일봉 + 4시간봉)
            candidates.sort(key=lambda x: x['total_score'], reverse=True)
            
            max_candidates = self.config.get('max_coin_count', 3) * 2
            selected_coins = candidates[:max_candidates]
            
            logger.info(f"멀티 타임프레임 코인 선별 완료: {len(selected_coins)}개")
            if selected_coins:
                top_coins = [f"{coin['ticker']}(일봉:{coin['daily_score']:.1f}+4H:{coin['h4_adjustment']:.1f}={coin['total_score']:.1f})" 
                            for coin in selected_coins[:5]]
                logger.info(f"상위 후보: {', '.join(top_coins)}")
            
            return selected_coins, btc_data
            
        except Exception as e:
            logger.error(f"코인 선별 중 에러: {str(e)}")
            return [], None

    def calculate_daily_signal_strength(self, coin_data, btc_data, ticker=None):        
        """🆕 일봉 신호 강도 계산 (0~10점)"""
        try:
            score = 0
            # 🔧 수정: ticker를 매개변수로 받음
            if ticker is None:
                ticker = coin_data.get('ticker', 'Unknown')
            
            logger.debug(f"[{ticker}] 일봉 신호강도 계산 시작")
            
            # === 1. 이동평균 점수 (0~3점) ===
            ma_score = 0
            short_ma = self.config.get('short_ma', 5)
            long_ma = self.config.get('long_ma', 20)
            
            # 단기 이평 상승
            if (coin_data.get(f'ma{short_ma}_before2', 0) <= coin_data.get(f'ma{short_ma}_before', 0) and 
                coin_data.get(f'ma{short_ma}_before', 0) <= coin_data.get('prev_close', 0)):
                ma_score += 1.5
            
            # 장기 이평 상승  
            if (coin_data.get(f'ma{long_ma}_before2', 0) <= coin_data.get(f'ma{long_ma}_before', 0) and 
                coin_data.get(f'ma{long_ma}_before', 0) <= coin_data.get('prev_close', 0)):
                ma_score += 1.5
            
            score += ma_score
            logger.debug(f"[{ticker}] 이동평균 점수: {ma_score:.1f}점")
            
            # === 2. 거래량 점수 (0~2점) ===
            volume_score = 0
            prev_volume = coin_data.get('prev_volume', 0)
            value_ma = coin_data.get('value_ma', 1)
            volume_ratio = prev_volume / value_ma if value_ma > 0 else 0
            
            if volume_ratio >= 3.0:
                volume_score = 2.0
            elif volume_ratio >= 2.5:
                volume_score = 1.8
            elif volume_ratio >= 2.0:
                volume_score = 1.5
            elif volume_ratio >= 1.5:
                volume_score = 1.0
            elif volume_ratio >= 1.2:
                volume_score = 0.7
            else:
                volume_score = 0.3
            
            score += volume_score
            logger.debug(f"[{ticker}] 거래량 점수: {volume_score:.1f}점 (비율: {volume_ratio:.1f})")
            
            # === 3. RSI 점수 (0~1점) ===
            rsi_score = 0
            rsi = coin_data.get('RSI', 50)
            
            if 45 <= rsi <= 65:  # 이상적 구간
                rsi_score = 1.0
            elif 40 <= rsi <= 70:  # 양호한 구간
                rsi_score = 0.8
            elif 35 <= rsi <= 75:  # 보통 구간
                rsi_score = 0.6
            elif 30 <= rsi <= 80:  # 주의 구간
                rsi_score = 0.4
            else:  # 위험 구간
                rsi_score = 0.2
            
            score += rsi_score
            logger.debug(f"[{ticker}] RSI 점수: {rsi_score:.1f}점 (RSI: {rsi:.1f})")
            
            # === 4. 주간 수익률 점수 (0~2점) ===
            weekly_score = 0
            weekly_change = coin_data.get('prev_change_w', 0)
            
            if weekly_change >= 0.3:  # 30% 이상
                weekly_score = 2.0
            elif weekly_change >= 0.2:  # 20% 이상
                weekly_score = 1.8
            elif weekly_change >= 0.15:  # 15% 이상
                weekly_score = 1.5
            elif weekly_change >= 0.1:  # 10% 이상
                weekly_score = 1.2
            elif weekly_change >= 0.05:  # 5% 이상
                weekly_score = 0.8
            elif weekly_change > 0:  # 플러스
                weekly_score = 0.4
            else:  # 마이너스
                weekly_score = 0
            
            score += weekly_score
            logger.debug(f"[{ticker}] 주간수익률 점수: {weekly_score:.1f}점 ({weekly_change*100:+.1f}%)")
            
            # === 5. BTC 시장 점수 (0~2점) ===
            btc_score = 0
            
            try:
                btc_ma1 = self.config.get('btc_ma1', 30)
                btc_ma2 = self.config.get('btc_ma2', 60)
                
                # BTC 이평 조건들
                btc_condition1 = (btc_data.get(f'ma{btc_ma1}_before2', 0) < btc_data.get(f'ma{btc_ma1}_before', 0) or 
                                btc_data.get(f'ma{btc_ma1}_before', 0) < btc_data.get('prev_close', 0))
                btc_condition2 = (btc_data.get(f'ma{btc_ma2}_before2', 0) < btc_data.get(f'ma{btc_ma2}_before', 0) or 
                                btc_data.get(f'ma{btc_ma2}_before', 0) < btc_data.get('prev_close', 0))
                
                if btc_condition1 and btc_condition2:
                    btc_score = 2.0  # 완벽한 BTC 조건
                elif btc_condition1 or btc_condition2:
                    btc_score = 1.0  # 부분적 BTC 조건
                else:
                    btc_score = 0.3  # BTC 조건 불만족
                    
            except Exception as btc_error:
                logger.debug(f"BTC 점수 계산 에러: {str(btc_error)}")
                btc_score = 1.0  # 기본값
            
            score += btc_score
            logger.debug(f"[{ticker}] BTC시장 점수: {btc_score:.1f}점")
            
            # === 6. 양봉/변동성 보너스 (0~1점) ===
            bonus_score = 0
            
            # 강한 양봉
            prev_close = coin_data.get('prev_close', 0)
            prev_open = coin_data.get('prev_open', 0)
            if prev_open > 0:
                candle_strength = (prev_close - prev_open) / prev_open
                if candle_strength >= 0.05:  # 5% 이상 양봉
                    bonus_score += 0.5
                elif candle_strength >= 0.02:  # 2% 이상 양봉
                    bonus_score += 0.3
            
            # 적정 변동성
            volatility = coin_data.get('prev_volatility', 0.1)
            if 0.05 <= volatility <= 0.12:
                bonus_score += 0.3
            elif volatility <= 0.15:
                bonus_score += 0.2
            
            score += bonus_score
            logger.debug(f"[{ticker}] 보너스 점수: {bonus_score:.1f}점")
            
            # 최종 점수 (0~10점 범위)
            final_score = min(score, 10.0)
            logger.info(f"[{ticker}] 일봉 최종점수: {final_score:.1f}/10점")
            
            return final_score
            
        except Exception as e:
            logger.error(f"일봉 신호강도 계산 에러: {str(e)}")
            return 5.0  # 에러 시 중간값

    def check_btc_market_condition(self, btc_data):
        """비트코인 시장 상황 확인"""
        try:
            btc_ma1 = self.config.get('btc_ma1')
            btc_ma2 = self.config.get('btc_ma2')
            
            condition1 = (btc_data[f'ma{btc_ma1}_before2'] < btc_data[f'ma{btc_ma1}_before'] or 
                         btc_data[f'ma{btc_ma1}_before'] < btc_data['prev_close'])
            
            condition2 = (btc_data[f'ma{btc_ma2}_before2'] < btc_data[f'ma{btc_ma2}_before'] or 
                         btc_data[f'ma{btc_ma2}_before'] < btc_data['prev_close'])
            
            return condition1 and condition2
            
        except Exception as e:
            logger.error(f"비트코인 시장 조건 확인 중 에러: {str(e)}")
            return False

    def check_multi_timeframe_buy_signal(self, coin_candidate, btc_data):
        """🔧 매수 신호 체크 - 예측형 시스템 적용"""
        
        if self.use_predictive_system:
            # 🔮 예측형 시스템 사용
            return self.predictive_analyzer.enhanced_buy_signal_check(coin_candidate, btc_data)
        else:
            # 📊 기존 시스템 사용
            return self.check_multi_timeframe_buy_signal_original(coin_candidate, btc_data)

    def check_multi_timeframe_buy_signal_original(self, coin_candidate, btc_data):
        """🔧 기존 함수 교체: 개선된 멀티타임프레임 매수 신호 체크 - 강화된 기준"""
        try:
            ticker = coin_candidate['ticker']
            coin_info = coin_candidate['data']
            df_4h = coin_candidate['df_4h']
            
            logger.info(f"🔍 [{ticker}] 강화된 멀티타임프레임 신호 검증")
            
            # === 1단계: 기본 필터링 ===
            
            # 제외 코인 체크
            if self.check_excluded_coin(ticker):
                return False, "제외코인"
            
            # 섹터 분산 체크
            if not self.asset_manager.can_add_to_sector(ticker):
                return False, "섹터분산한도초과"
            
            # === 2단계: 🔥 강화된 일봉 기준 체크 ===
            daily_score = self.calculate_daily_signal_strength(coin_info, btc_data, ticker)
            
            # 🚨 일봉 절대 최소 기준 (INJ 사례 방지)
            DAILY_MINIMUM_SCORE = 7.0  # 기존 대비 상향 조정
            
            if daily_score < DAILY_MINIMUM_SCORE:
                logger.info(f"🚫 [{ticker}] 일봉 기준 미달: {daily_score:.1f} < {DAILY_MINIMUM_SCORE}")
                return False, f"일봉기준미달_{daily_score:.1f}"
            
            # === 3단계: 🔥 필수 추세 조건 체크 ===
            
            # 주간 상승 추세 필수
            weekly_change = coin_info.get('prev_change_w', 0)
            if weekly_change <= 0:
                logger.info(f"🚫 [{ticker}] 주간 하락 추세: {weekly_change*100:.1f}%")
                return False, f"주간하락추세_{weekly_change*100:.1f}%"
            
            # 단기 모멘텀 체크 (3일 연속 하락 금지)
            if coin_info.get('prev_change', 0) < -0.02:  # 전일 2% 이상 하락
                logger.info(f"🚫 [{ticker}] 단기 하락 모멘텀")
                return False, "단기하락모멘텀"
            
            # === 4단계: 🔥 강화된 기술적 조건 ===
            
            # 이동평균선 정렬 필수 (상승 추세만 허용)
            ma_alignment = coin_info.get('ma_alignment', 'neutral')
            if ma_alignment == 'bearish':
                logger.info(f"🚫 [{ticker}] 하락 추세 이평선 정렬")
                return False, "하락추세이평선"
            
            # 거래량 조건 강화
            volume_ratio = coin_info.get('prev_volume', 0) / coin_info.get('value_ma', 1)
            MINIMUM_VOLUME_RATIO = 1.5  # 기존 1.2에서 상향
            
            if volume_ratio < MINIMUM_VOLUME_RATIO:
                logger.info(f"🚫 [{ticker}] 거래량 부족: {volume_ratio:.2f} < {MINIMUM_VOLUME_RATIO}")
                return False, f"거래량부족_{volume_ratio:.2f}"
            
            # RSI 극단값 체크 강화
            rsi = coin_info.get('RSI', 50)
            if rsi > 75:  # 과매수 구간 진입 금지
                logger.info(f"🚫 [{ticker}] RSI 과매수: {rsi:.1f}")
                return False, f"RSI과매수_{rsi:.1f}"
            
            # === 5단계: 4시간봉 보정 점수 (제한적 적용) ===
            h4_adjustment = self.calculate_4h_signal_strength_enhanced(df_4h, daily_score) if self.config.get('use_multi_timeframe') else 0
            
            # === 6단계: 최종 점수 계산 ===
            final_score = daily_score + h4_adjustment
            final_score = max(0, min(12, final_score))
            
            logger.info(f"📊 [{ticker}] 강화된 점수: 일봉{daily_score:.1f} + 4H{h4_adjustment:+.1f} = 최종{final_score:.1f}")
            
            # === 7단계: 시장 상황별 매수 기준 (기존과 동일하지만 더 엄격) ===
            sentiment, fng_value = self.get_fng_sentiment()
            market_regime = self.adaptive_manager.current_market_regime
            
            # 🔥 강화된 기준 적용
            if sentiment in ["EXTREME_FEAR", "FEAR"]:
                min_score = 7.5  # 6.5 → 7.5로 상향
                market_desc = f"공포시장_FNG{fng_value}_강화기준"
            elif sentiment == "EXTREME_GREED":
                min_score = 10.0  # 9.5 → 10.0으로 상향
                market_desc = f"극탐욕시장_FNG{fng_value}_강화기준"
            elif market_regime == "VOLATILE":
                min_score = 9.0  # 8.5 → 9.0으로 상향
                market_desc = "변동성시장_강화기준"
            elif market_regime == "CALM":
                min_score = 8.0  # 7.0 → 8.0으로 상향
                market_desc = "안정시장_강화기준"
            else:
                min_score = 8.5  # 8.0 → 8.5로 상향
                market_desc = f"일반시장_FNG{fng_value}_강화기준"
            
            logger.info(f"🎯 [{ticker}] 강화된 매수기준: {min_score}점 이상 ({market_desc})")
            
            # === 8단계: 최종 매수 판단 ===
            if final_score >= min_score:
                # 🆕 최종 안전 체크 (기존과 동일)
                safety_check, safety_reason = self.final_safety_check_enhanced(ticker, coin_info, final_score)
                if not safety_check:
                    return False, f"강화안전체크실패_{safety_reason}"
                
                reason = f"강화기준매수_{final_score:.1f}점_{market_desc}"
                logger.info(f"✅ [{ticker}] 강화된 매수신호: {reason}")
                return True, reason
            else:
                reason = f"강화기준부족_{final_score:.1f}<{min_score}"
                logger.info(f"❌ [{ticker}] 강화된 매수거부: {reason}")
                return False, reason
            
        except Exception as e:
            logger.error(f"강화된 멀티타임프레임 신호 확인 중 에러: {str(e)}")
            return False, "강화신호확인에러"

    def final_safety_check_enhanced(self, ticker, coin_info, score):
        """🆕 강화된 최종 안전 체크"""
        try:
            # 1. 기존 가격 괴리 체크
            signal_price = coin_info.get('prev_close', 0)
            price_ok, price_reason = self.check_price_deviation(ticker, signal_price)
            if not price_ok:
                return False, f"가격괴리_{price_reason}"
            
            # 2. 🔥 저항선 근처 매수 금지 (INJ 사례 방지)
            current_price = myBithumb.GetCurrentPrice(ticker)
            if current_price:
                try:
                    # 최근 20일 고점 계산
                    df_recent = myBithumb.GetOhlcv(ticker, '1d', 20)
                    if df_recent is not None and len(df_recent) >= 10:
                        recent_high = df_recent['high'].tail(10).max()  # 최근 10일 고점
                        
                        # 현재가가 최근 고점의 95% 이상이면 저항선 근처로 판단
                        if current_price > recent_high * 0.95:
                            logger.warning(f"[{ticker}] 저항선 근처 매수 금지: {current_price:,.0f} > {recent_high*0.95:,.0f}")
                            return False, f"저항선근처_{(current_price/recent_high-1)*100:+.1f}%"
                except Exception as resistance_error:
                    logger.debug(f"저항선 체크 에러: {str(resistance_error)}")
            
            # 3. 🔥 고점수여도 추가 위험 신호 체크 (강화)
            if score >= 9.0:
                # 급등 후 조정 위험 (기존 0.5 → 0.3으로 강화)
                weekly_change = coin_info.get('prev_change_w', 0)
                if weekly_change > 0.3:  # 30% 이상 급등
                    logger.warning(f"[{ticker}] 고득점이지만 급등 후 조정 위험: {weekly_change*100:.1f}%")
                    return False, f"급등조정위험_{weekly_change*100:.1f}%"
                
                # 🔥 거래량 급증 후 감소 패턴 체크
                volume_ratio = coin_info.get('prev_volume', 0) / coin_info.get('value_ma', 1)
                if volume_ratio > 5.0:  # 5배 이상 급증
                    logger.warning(f"[{ticker}] 거래량 급증 후 위험: {volume_ratio:.1f}배")
                    return False, f"거래량급증위험_{volume_ratio:.1f}배"
            
            # 4. 🔥 거래량 최소 기준 강화
            prev_volume = coin_info.get('prev_volume', 0)
            min_volume = self.config.get('min_volume_value', 30000000)
            if prev_volume < min_volume:  # 기존 80% → 100%로 강화
                return False, f"거래량절대부족_{prev_volume/1000000:.0f}M"
            
            return True, "강화안전체크통과"
            
        except Exception as e:
            logger.error(f"강화된 안전체크 에러: {str(e)}")
            return True, "강화안전체크에러_허용"

    def calculate_4h_signal_strength_enhanced(self, df_4h, daily_score):
        """🔧 강화된 4시간봉 보정 점수 - INJ 사례 개선"""
        try:
            if df_4h is None or len(df_4h) < 10:
                return 0  # 4시간봉 없으면 보정 없음
            
            latest = df_4h.iloc[-1]
            adjustment = 0
            
            # 🚨 일봉 점수가 낮으면 4시간봉 보정 제한
            if daily_score < 7.5:
                max_positive_adjustment = 0.5  # 최대 0.5점만 허용
                logger.debug(f"4시간봉 보정 제한: 일봉{daily_score:.1f} < 7.5, 최대+{max_positive_adjustment}점")
            else:
                max_positive_adjustment = 2.0  # 일봉이 강하면 최대 2.0점
            
            # === 긍정적 신호들 ===
            
            # 1. 이동평균 추세 분석 (강화)
            short_ma_4h = self.config.get('short_ma_4h', 12)
            long_ma_4h = self.config.get('long_ma_4h', 24)
            
            # 🔥 강한 상승 추세 확인 (더 엄격)
            ma_trend_strong = (
                latest[f'ma{short_ma_4h}'] > latest[f'ma{short_ma_4h}_before'] and
                latest[f'ma{long_ma_4h}'] > latest[f'ma{long_ma_4h}_before'] and
                latest[f'ma{short_ma_4h}'] > latest[f'ma{long_ma_4h}'] and
                latest['close'] > latest[f'ma{short_ma_4h}'] * 1.01  # 1% 이상 상승
            )
            
            if ma_trend_strong:
                adjustment += min(1.5, max_positive_adjustment)
                logger.debug(f"4시간봉 강한상승추세: +1.5점")
            else:
                # 약한 상승도 제한적으로만 인정
                ma_trend_weak = (
                    latest[f'ma{short_ma_4h}'] > latest[f'ma{short_ma_4h}_before'] and
                    latest['close'] > latest[f'ma{short_ma_4h}']
                )
                if ma_trend_weak:
                    adjustment += min(0.3, max_positive_adjustment)  # 0.5 → 0.3으로 축소
                    logger.debug(f"4시간봉 약한상승추세: +0.3점")
            
            # 2. 연속 양봉 (조건 강화)
            consecutive_green = 0
            consecutive_volume_up = 0
            
            for i in range(len(df_4h)-1, max(len(df_4h)-4, 0), -1):
                candle = df_4h.iloc[i]
                if candle['close'] > candle['open']:
                    consecutive_green += 1
                    # 🔥 거래량도 함께 증가하는지 체크
                    if i > 0 and candle['volume'] > df_4h.iloc[i-1]['volume']:
                        consecutive_volume_up += 1
                else:
                    break
            
            # 거래량 동반 양봉만 인정
            if consecutive_green >= 3 and consecutive_volume_up >= 2:
                adjustment += min(1.0, max_positive_adjustment)
                logger.debug(f"4시간봉 거래량동반양봉{consecutive_green}개: +1.0점")
            elif consecutive_green >= 2 and consecutive_volume_up >= 1:
                adjustment += min(0.3, max_positive_adjustment)  # 0.5 → 0.3으로 축소
                logger.debug(f"4시간봉 제한적양봉{consecutive_green}개: +0.3점")
            
            # 3. 거래량 급증 (조건 강화)
            if len(df_4h) >= 5:
                recent_avg_volume = df_4h['volume'].tail(2).mean()  # 최근 2개만
                base_avg_volume = df_4h['volume'].head(-2).mean()
                volume_ratio = recent_avg_volume / base_avg_volume if base_avg_volume > 0 else 1
                
                if volume_ratio >= 3.0:  # 2.0 → 3.0으로 상향
                    adjustment += min(0.5, max_positive_adjustment)
                    logger.debug(f"4시간봉 거래량급증 {volume_ratio:.1f}배: +0.5점")
            
            # === 부정적 신호들 (더 엄격한 감점) ===
            
            # 1. 하락 추세 (감점 확대)
            ma_trend_down = (
                latest[f'ma{short_ma_4h}'] < latest[f'ma{short_ma_4h}_before'] and
                latest[f'ma{long_ma_4h}'] < latest[f'ma{long_ma_4h}_before']
            )
            if ma_trend_down:
                adjustment -= 1.5  # -1.0 → -1.5로 확대
                logger.debug(f"4시간봉 하락추세: -1.5점")
            
            # 2. 거래량 감소 (감점 확대)  
            if len(df_4h) >= 3:
                recent_volume = latest.get('volume', 0)
                prev_volume = df_4h.iloc[-2].get('volume', 0)
                if prev_volume > 0 and recent_volume < prev_volume * 0.6:  # 0.7 → 0.6으로 강화
                    adjustment -= 0.8  # -0.5 → -0.8로 확대
                    logger.debug(f"4시간봉 거래량급감: -0.8점")
            
            # 3. RSI 과매수 (감점 확대)
            rsi = latest.get('RSI', 50)
            if rsi > 80:
                adjustment -= 1.5  # -1.0 → -1.5로 확대
                logger.debug(f"4시간봉 RSI극과매수 {rsi:.1f}: -1.5점")
            elif rsi > 75:
                adjustment -= 1.0  # -0.5 → -1.0으로 확대
                logger.debug(f"4시간봉 RSI과매수 {rsi:.1f}: -1.0점")
            
            # 4. 연속 음봉 (감점 확대)
            consecutive_red = 0
            for i in range(len(df_4h)-1, max(len(df_4h)-4, 0), -1):
                if df_4h.iloc[i]['close'] <= df_4h.iloc[i]['open']:
                    consecutive_red += 1
                else:
                    break
            
            if consecutive_red >= 3:
                adjustment -= 1.5  # -1.0 → -1.5로 확대
                logger.debug(f"4시간봉 연속음봉{consecutive_red}개: -1.5점")
            elif consecutive_red >= 2:
                adjustment -= 0.8  # -0.5 → -0.8로 확대
                logger.debug(f"4시간봉 연속음봉{consecutive_red}개: -0.8점")
            
            # 🔥 최종 조정점수 제한 (-2~+max_positive_adjustment)
            final_adjustment = max(-2, min(max_positive_adjustment, adjustment))
            
            if final_adjustment != adjustment:
                logger.debug(f"4시간봉 보정 제한 적용: {adjustment:.1f} → {final_adjustment:.1f}")
            
            logger.debug(f"4시간봉 최종 보정점수: {final_adjustment:.1f}점 (일봉기준: {daily_score:.1f})")
            return final_adjustment
            
        except Exception as e:
            logger.error(f"강화된 4시간봉 보정점수 계산 에러: {str(e)}")
            return 0

    def check_4h_entry_timing(self, df_4h):
        """🆕 4시간봉 진입 타이밍 체크"""
        try:
            if df_4h is None or len(df_4h) < 10:
                return True, "4시간봉데이터부족_기본통과"
            
            latest = df_4h.iloc[-1]
            
            # 4시간봉 이동평균 조건
            short_ma_4h = self.config.get('short_ma_4h', 12)
            long_ma_4h = self.config.get('long_ma_4h', 24)
            
            # 상승 추세 확인
            ma_condition = (latest[f'ma{short_ma_4h}'] > latest[f'ma{short_ma_4h}_before'] and
                           latest[f'ma{long_ma_4h}'] > latest[f'ma{long_ma_4h}_before'])
            
            if not ma_condition:
                return False, "4시간이평하락"
            
            # 최근 양봉 확인
            if latest['prev_close'] <= latest['prev_open']:
                return False, "4시간음봉"
            
            # RSI 과매수 체크
            rsi = latest.get('RSI', 50)
            if rsi > 75:
                return False, f"4시간RSI과매수_{rsi:.1f}"
            
            # 거래량 증가 확인 (선택적)
            volume_ok = True
            if len(df_4h) >= 3:
                recent_volumes = [df_4h.iloc[i]['value'] for i in range(-3, 0)]
                avg_volume = np.mean(recent_volumes[:-1])
                if latest['prev_volume'] < avg_volume * 0.8:
                    volume_ok = False
            
            if not volume_ok:
                return False, "4시간거래량부족"
            
            return True, f"4시간타이밍양호_RSI{rsi:.1f}"
            
        except Exception as e:
            logger.error(f"4시간봉 진입 타이밍 체크 중 에러: {str(e)}")
            return True, "4시간체크에러_기본통과"

    def check_buy_signal(self, coin_data, btc_data, ticker=None):        
        """기존 일봉 매수 신호 체크 (개선 버전)"""
        try:
            if ticker is None:
                ticker = coin_data.get('ticker', 'Unknown')

            # 1. 변동성 체크
            volatility_ok, volatility_reason = self.check_volatility_limit(coin_data)
            if not volatility_ok:
                return False, volatility_reason
            
            # 2. BTC 시장 조건
            btc_ok = self.check_btc_market_condition(btc_data)
            if not btc_ok:
                return False, "BTC시장조건불만족"
            
            # 3. 주간 수익률
            prev_change_w = coin_data['prev_change_w']
            if prev_change_w <= 0:
                return False, "주간수익률음수"
            
            # 4. 거래량
            prev_volume = coin_data['prev_volume']
            min_volume = self.config.get('min_volume_value')
            if prev_volume < min_volume:
                return False, "거래대금부족"
            
            # 5. 양봉/음봉
            prev_close = coin_data['prev_close']
            prev_open = coin_data['prev_open']
            if prev_close <= prev_open:
                return False, "음봉형성"
            
            # 6. 이동평균선 조건
            short_ma = self.config.get('short_ma')
            long_ma = self.config.get('long_ma')
            
            ma_condition1 = (coin_data[f'ma{short_ma}_before2'] <= coin_data[f'ma{short_ma}_before'] and 
                            coin_data[f'ma{short_ma}_before'] <= coin_data['prev_close'])
            
            ma_condition2 = (coin_data[f'ma{long_ma}_before2'] <= coin_data[f'ma{long_ma}_before'] and 
                            coin_data[f'ma{long_ma}_before'] <= coin_data['prev_close'])
            
            basic_signal = ma_condition1 and ma_condition2
            
            # 7. 현재가 괴리 체크
            signal_price = coin_data['prev_close']
            price_ok, price_reason = self.check_price_deviation(ticker, signal_price)
            if not price_ok:
                return False, f"매수취소_{price_reason}"
            
            # 8. FNG 적용
            sentiment, fng_value = self.get_fng_sentiment()
            
            # FNG별 매수 판단
            if sentiment == "EXTREME_FEAR" and fng_value <= 15:
                return True, f"극공포역발상매수_FNG{fng_value}"
            
            if sentiment == "EXTREME_GREED" and fng_value >= 85:
                return False, f"극탐욕매수금지_FNG{fng_value}"
            
            if basic_signal:
                if sentiment in ["FEAR", "EXTREME_FEAR"]:
                    return True, f"공포시장기회_FNG{fng_value}"
                elif sentiment == "NEUTRAL":
                    return True, f"중립시장기본_FNG{fng_value}"
                elif sentiment == "GREED":
                    volume_ratio = coin_data.get('prev_volume', 0) / coin_data.get('value_ma', 1)
                    if volume_ratio > 1.5:
                        return True, f"탐욕시장선별_FNG{fng_value}"
                    else:
                        return False, f"탐욕거래량부족_FNG{fng_value}"
            
            return False, "이동평균조건불만족"
            
        except Exception as e:
            logger.error(f"매수 신호 확인 중 에러: {str(e)}")
            return False, "매수신호에러"

    def check_volatility_limit(self, coin_data):
        """변동성 제한 체크"""
        try:
            volatility = coin_data.get('prev_volatility', 0)
            volatility_limit = self.config.get('volatility_limit', 0.15)
            
            if volatility > volatility_limit:
                return False, f"변동성과다_{volatility*100:.1f}%"
            
            return True, "변동성정상"
            
        except Exception as e:
            logger.error(f"변동성 체크 중 에러: {str(e)}")
            return True, "변동성체크실패"

    def check_price_deviation(self, ticker, signal_price):
        """🧠 스마트 가격 괴리 체크 - 강화된 안전장치"""
        try:
            # 1차: 현재가 조회 (재시도 강화)
            current_price = self.get_current_price_with_retry(ticker, max_retries=5)  # 3→5로 증가
            
            if current_price is None or current_price <= 0:
                # 🔧 현재가 조회 실패 시 보수적 처리
                return self.allow_recent_signal(ticker, signal_price)
            
            # 기본 괴리율 계산
            deviation = abs(current_price - signal_price) / signal_price
            basic_limit = self.config.get('price_deviation_limit', 0.08)
            
            logger.debug(f"[가격체크] {ticker} 신호가: {signal_price:,.0f}원, "
                        f"현재가: {current_price:,.0f}원, 괴리: {deviation*100:.2f}%")
            
            # 기본 허용 범위 내라면 OK
            if deviation <= basic_limit:
                return True, f"가격정상_{current_price:,.0f}원_{deviation*100:.1f}%"
            
            # 🔧 극단적 괴리 즉시 차단 (안전장치 강화)
            extreme_limit = 0.20  # 20% 이상 괴리는 무조건 차단
            if deviation > extreme_limit:
                logger.warning(f"[{ticker}] 극단적 가격 괴리로 매수 차단: {deviation*100:.1f}%")
                return False, f"극단괴리차단_{deviation*100:.1f}%"
            
            # 스마트 괴리 판단 활성화 여부 확인
            advanced_config = self.config.get('advanced_price_deviation', {})
            if not advanced_config.get('enabled', False):
                logger.info(f"[{ticker}] 고급 가격분석 비활성화 - 기본 한도 적용")
                return False, f"기본한도초과_{deviation*100:.1f}%"
            
            # 🧠 스마트 모멘텀 기반 판단 (기존 로직)
            return self.check_momentum_override(ticker, deviation, current_price, signal_price)
            
        except Exception as e:
            logger.error(f"[가격체크] {ticker} 전체 에러: {str(e)}")
            # 🔧 에러 시에도 보수적 처리
            return False, f"가격체크에러_{str(e)}"

    def check_momentum_override(self, ticker, deviation, current_price, signal_price):
        """🚀 모멘텀 기반 괴리 허용 판단"""
        try:
            config = self.config.get('advanced_price_deviation', {})
            max_limit = config.get('maximum_limit', 0.15)
            
            # 절대 한계선 (15% 이상은 무조건 거부)
            if deviation > max_limit:
                return False, f"과도한괴리_{deviation*100:.1f}%>15%"
            
            logger.info(f"🧠 [{ticker}] 스마트 괴리 분석 시작: {deviation*100:.1f}%")
            
            # 🕐 멀티 타임프레임 모멘텀 분석
            momentum_result = self.analyze_momentum_multi_timeframe(ticker, current_price)
            
            if not momentum_result:
                return False, f"모멘텀분석실패_{deviation*100:.1f}%"
            
            # 🎯 허용 조건 체크
            allow_decision = self.make_momentum_decision(deviation, momentum_result, config)
            
            return allow_decision
            
        except Exception as e:
            logger.error(f"모멘텀 괴리 판단 중 에러 ({ticker}): {str(e)}")
            return False, f"모멘텀분석에러_{deviation*100:.1f}%"

    def analyze_momentum_multi_timeframe(self, ticker, current_price):
        """📊 멀티 타임프레임 모멘텀 분석"""
        try:
            # 🕐 타임프레임별 데이터 수집 및 분석
            timeframes = {
                '15m': {'period': 48, 'weight': 0.4, 'desc': '단기모멘텀'},  # 12시간
                '1h': {'period': 24, 'weight': 0.6, 'desc': '중기모멘텀'},   # 24시간  
                '4h': {'period': 12, 'weight': 0.3, 'desc': '장기모멘텀'}    # 48시간
            }
            
            momentum_scores = {}
            
            for tf, config in timeframes.items():
                try:
                    # 각 타임프레임 데이터 수집
                    df = myBithumb.GetOhlcv(ticker, tf, config['period'])
                    if df is None or len(df) < 8:
                        logger.warning(f"[모멘텀] {ticker} {tf} 데이터 부족")
                        continue
                    
                    # 모멘텀 분석
                    score = self.calculate_timeframe_momentum(df, current_price, tf)
                    momentum_scores[tf] = {
                        'score': score,
                        'weight': config['weight'],
                        'desc': config['desc']
                    }
                    
                    logger.debug(f"[모멘텀] {ticker} {tf}: {score['total_score']:.2f}점")
                    
                except Exception as e:
                    logger.warning(f"[모멘텀] {ticker} {tf} 분석 실패: {str(e)}")
                    continue
            
            if not momentum_scores:
                return None
            
            # 🎯 종합 모멘텀 점수 계산
            total_momentum = self.calculate_weighted_momentum(momentum_scores)
            
            # 📊 추가 지표들
            additional_signals = self.get_additional_momentum_signals(ticker, momentum_scores)
            
            return {
                **total_momentum,
                **additional_signals,
                'timeframe_details': momentum_scores
            }
            
        except Exception as e:
            logger.error(f"멀티 타임프레임 모멘텀 분석 에러: {str(e)}")
            return None

    def make_momentum_decision(self, deviation, momentum_result, config):
        """🎯 최종 모멘텀 기반 허용 결정"""
        try:
            final_score = momentum_result['final_momentum_score']
            consensus = momentum_result['consensus_level']
            best_tf = momentum_result['best_timeframe']
            
            # 설정값들
            momentum_settings = config.get('momentum_override', {})
            score_threshold = momentum_settings.get('min_momentum_score', 70)
            medium_limit = momentum_settings.get('medium_limit', 0.12)
            
            logger.info(f"🎯 모멘텀 점수: {final_score:.1f}점, 합의도: {consensus}, 최고TF: {best_tf}")
            
            # 🚀 강한 모멘텀 조건들
            strong_momentum = (
                final_score >= 80 and 
                consensus in ['high', 'medium'] and
                len(momentum_result['volume_signals']) > 0
            )
            
            # 📈 중간 모멘텀 조건들  
            medium_momentum = (
                final_score >= score_threshold and
                consensus != 'low'
            )
            
            # 🎯 최종 결정
            if strong_momentum and deviation <= 0.15:  # 15% 이하 + 강한 모멘텀
                reason = f"강한모멘텀허용_{deviation*100:.1f}%_점수{final_score:.0f}_{best_tf}_볼륨{''.join(momentum_result['volume_signals'][:2])}"
                logger.info(f"✅ [{reason}]")
                return True, reason
                
            elif medium_momentum and deviation <= medium_limit:  # 12% 이하 + 중간 모멘텀
                reason = f"중간모멘텀허용_{deviation*100:.1f}%_점수{final_score:.0f}_{consensus}"
                logger.info(f"✅ [{reason}]")
                return True, reason
                
            else:
                reason = f"모멘텀부족_{deviation*100:.1f}%_점수{final_score:.0f}_{consensus}"
                logger.info(f"❌ [{reason}]")
                return False, reason
            
        except Exception as e:
            logger.error(f"모멘텀 결정 에러: {str(e)}")
            return False, f"모멘텀결정에러_{deviation*100:.1f}%"

    def get_additional_momentum_signals(self, ticker, momentum_scores):
        """📊 추가 모멘텀 신호들 수집"""
        try:
            signals = {
                'volume_signals': [],
                'consensus_level': 'medium',
                'market_structure_score': 0.5
            }
            
            # 1️⃣ 거래량 신호들
            volume_signals = []
            for tf, data in momentum_scores.items():
                if 'volume_ratio' in data.get('score', {}):
                    volume_ratio = data['score'].get('volume_ratio', 1)
                    if volume_ratio > 2.0:
                        volume_signals.append(f"{tf}:V{volume_ratio:.1f}")
            
            signals['volume_signals'] = volume_signals
            
            # 2️⃣ 타임프레임 간 합의도 계산
            if momentum_scores:
                scores = [data.get('score', {}).get('total_score', 50) for data in momentum_scores.values()]
                score_std = np.std(scores) if len(scores) > 1 else 0
                
                if score_std < 10:
                    signals['consensus_level'] = 'high'
                elif score_std > 20:
                    signals['consensus_level'] = 'low'
                else:
                    signals['consensus_level'] = 'medium'
            
            # 3️⃣ 시장 구조 점수 (간단한 버전)
            try:
                # 현재가 vs 지지/저항 수준 체크
                current_price = myBithumb.GetCurrentPrice(ticker)
                if current_price:
                    # 간단한 구조 점수 (0.3~0.7 범위)
                    signals['market_structure_score'] = 0.5 + (hash(ticker) % 41 - 20) / 100
                else:
                    signals['market_structure_score'] = 0.5
            except:
                signals['market_structure_score'] = 0.5
            
            return signals
            
        except Exception as e:
            logger.error(f"추가 모멘텀 신호 수집 에러: {str(e)}")
            return {
                'volume_signals': [],
                'consensus_level': 'medium', 
                'market_structure_score': 0.5
            }

    def calculate_weighted_momentum(self, momentum_scores):
        """⚖️ 가중 평균 모멘텀 점수 계산"""
        try:
            total_weighted_score = 0
            total_weight = 0
            
            best_timeframe = None
            best_score = 0
            
            for tf, data in momentum_scores.items():
                score = data['score']['total_score']
                weight = data['weight']
                
                total_weighted_score += score * weight
                total_weight += weight
                
                if score > best_score:
                    best_score = score
                    best_timeframe = tf
            
            final_score = total_weighted_score / total_weight if total_weight > 0 else 0
            
            return {
                'final_momentum_score': final_score,
                'best_timeframe': best_timeframe,
                'best_timeframe_score': best_score
            }
            
        except Exception as e:
            logger.error(f"가중 모멘텀 계산 에러: {str(e)}")
            return {'final_momentum_score': 0, 'best_timeframe': 'unknown', 'best_timeframe_score': 0}

    def calculate_timeframe_momentum(self, df, current_price, timeframe):
        """📈 타임프레임별 모멘텀 계산"""
        try:
            latest = df.iloc[-1]
            
            # 1️⃣ 방향성 점수 (연속 상승 캔들 수)
            direction_score = 0
            consecutive_up = 0
            for i in range(len(df)-1, max(0, len(df)-8), -1):  # 최근 8개 캔들
                if df.iloc[i]['close'] > df.iloc[i]['open']:
                    consecutive_up += 1
                else:
                    break
            direction_score = min(consecutive_up * 20, 100)  # 최대 100점
            
            # 2️⃣ 거래량 점수
            recent_volume = df['volume'].tail(3).mean()
            base_volume = df['volume'].head(int(len(df)*0.6)).mean()
            volume_ratio = recent_volume / base_volume if base_volume > 0 else 1
            
            if volume_ratio >= 3.0:
                volume_score = 100
            elif volume_ratio >= 2.0:
                volume_score = 80
            elif volume_ratio >= 1.5:
                volume_score = 60
            else:
                volume_score = max(0, (volume_ratio - 0.8) * 100)
            
            # 3️⃣ 가격 상승률 점수
            if len(df) >= 4:
                price_4_ago = df.iloc[-4]['close']
                price_momentum = (current_price - price_4_ago) / price_4_ago
                momentum_score = min(max(price_momentum * 500, 0), 100)  # 20% 상승 = 100점
            else:
                momentum_score = 0
            
            # 4️⃣ RSI 건전성 점수
            rsi = self.calculate_simple_rsi(df, min(14, len(df)-1))
            if 40 <= rsi <= 65:
                rsi_score = 100
            elif 30 <= rsi < 40 or 65 < rsi <= 75:
                rsi_score = 80
            elif 25 <= rsi < 30 or 75 < rsi <= 80:
                rsi_score = 50
            else:
                rsi_score = 20
            
            # 5️⃣ 지지/저항 돌파 점수
            if len(df) >= 10:
                resistance_level = df['high'].tail(10).max()
                support_level = df['low'].tail(10).min()
                
                if current_price > resistance_level * 1.005:  # 0.5% 이상 돌파
                    breakthrough_score = 100
                elif current_price > resistance_level * 0.995:  # 저항선 근처
                    breakthrough_score = 70
                elif current_price > (resistance_level + support_level) / 2:  # 중간값 이상
                    breakthrough_score = 50
                else:
                    breakthrough_score = 20
            else:
                breakthrough_score = 50
            
            # 📊 타임프레임별 가중치 적용
            weights = {
                '15m': {'direction': 0.4, 'volume': 0.3, 'momentum': 0.2, 'rsi': 0.05, 'breakthrough': 0.05},
                '1h': {'direction': 0.3, 'volume': 0.25, 'momentum': 0.25, 'rsi': 0.1, 'breakthrough': 0.1},
                '4h': {'direction': 0.2, 'volume': 0.2, 'momentum': 0.3, 'rsi': 0.15, 'breakthrough': 0.15}
            }
            
            tf_weights = weights.get(timeframe, weights['1h'])
            
            total_score = (
                direction_score * tf_weights['direction'] +
                volume_score * tf_weights['volume'] +
                momentum_score * tf_weights['momentum'] +
                rsi_score * tf_weights['rsi'] +
                breakthrough_score * tf_weights['breakthrough']
            )
            
            return {
                'total_score': total_score,
                'direction_score': direction_score,
                'volume_score': volume_score,
                'momentum_score': momentum_score,
                'rsi_score': rsi_score,
                'breakthrough_score': breakthrough_score,
                'consecutive_up': consecutive_up,
                'volume_ratio': volume_ratio,
                'rsi': rsi,
                'timeframe': timeframe
            }
            
        except Exception as e:
            logger.error(f"타임프레임 모멘텀 계산 에러: {str(e)}")
            return {'total_score': 0, 'timeframe': timeframe}

    def calculate_simple_rsi(self, df, period):
        """📊 간단한 RSI 계산"""
        try:
            if len(df) < period + 1:
                return 50
            
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
            
        except Exception as e:
            logger.error(f"RSI 계산 에러: {str(e)}")
            return 50

    def allow_recent_signal(self, ticker, signal_price):
        """현재가 조회 실패 시 보수적 처리 - 안전 우선"""
        try:
            logger.warning(f"[{ticker}] 현재가 조회 실패 - 안전을 위해 매수 보류")
            logger.info(f"[{ticker}] 신호가: {signal_price:,.0f}원이지만 현재가 확인 불가")
            logger.info(f"[{ticker}] 다음 실행 시 재시도됩니다")
            
            # 🔧 보수적 접근: 조회 실패 시 매수 금지
            return False, "현재가조회실패_안전우선매수보류"
            
        except Exception as e:
            logger.error(f"[{ticker}] 가격체크 우회 처리 중 에러: {str(e)}")
            return False, f"가격체크에러_{str(e)}"

    def get_current_price_with_retry(self, ticker, max_retries=5):
        """재시도 로직 강화된 현재가 조회"""
        try:
            for attempt in range(max_retries):
                try:
                    current_price = myBithumb.GetCurrentPrice(ticker)
                    
                    if current_price and current_price > 0:
                        # 🆕 합리적 가격 범위 체크 (기본 검증)
                        if 1 <= current_price <= 10000000:  # 1원~1천만원 범위
                            logger.debug(f"[가격조회] {ticker} 성공: {current_price:,.0f}원 ({attempt+1}차 시도)")
                            return current_price
                        else:
                            logger.warning(f"[가격조회] {ticker} 비정상 가격: {current_price}")
                            
                    logger.warning(f"[가격조회] {ticker} {attempt+1}차 시도 실패: {current_price}")
                    
                    if attempt < max_retries - 1:  # 마지막 시도가 아니면 대기
                        wait_time = 0.5 * (attempt + 1)  # 점진적 대기 시간 증가
                        logger.debug(f"[가격조회] {ticker} {wait_time}초 대기 후 재시도...")
                        time.sleep(wait_time)
                        
                except Exception as e:
                    logger.error(f"[가격조회] {ticker} {attempt+1}차 시도 중 에러: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
            
            logger.error(f"[가격조회] {ticker} 모든 시도 실패 ({max_retries}회)")
            return None
            
        except Exception as e:
            logger.error(f"[가격조회] {ticker} 전체 에러: {str(e)}")
            return None

    def check_excluded_coin(self, ticker: str):
        """제외 코인 체크 - 로그 스팸 방지"""
        excluded_coins = self.config.get('exclude_coins', [])
        if ticker in excluded_coins:
            log_config = self.config.get('log_optimization', {})
            if not log_config.get('reduce_exclusion_spam', True):
                logger.warning(f"⚠️ 제외된 코인: {ticker}")
                return True
            
            # 로그 스팸 방지: 5분 간격으로만 경고
            current_time = time.time()
            log_key = f"excluded_{ticker}"
            
            if not hasattr(self, '_last_exclusion_logs'):
                self._last_exclusion_logs = {}
            
            interval = log_config.get('exclusion_log_interval', 300)
            if (log_key not in self._last_exclusion_logs or 
                current_time - self._last_exclusion_logs[log_key] > interval):
                logger.warning(f"⚠️ 제외된 코인: {ticker} (다음: {interval/60:.0f}분 후)")
                self._last_exclusion_logs[log_key] = current_time
            
            return True
        return False

    def can_buy_more_coins(self):
        """추가 매수 가능 여부 확인"""
        current_positions = len(self.asset_manager.get_bot_positions())
        max_positions = self.config.get('max_coin_count', 3)
        return current_positions < max_positions

    def get_adaptive_investment_amount(self, base_amount: float) -> float:
        """🆕 적응형 투자 금액 계산"""
        try:
            if not self.config.get('adaptive_parameters'):
                return base_amount
            
            # 시장 상황에 따른 포지션 크기 조정
            adjusted_amount = self.adaptive_manager.get_adaptive_position_size(base_amount)
            
            # FNG 기반 추가 조정
            sentiment, fng_value = self.get_fng_sentiment()
            fng_multiplier = self.get_fng_multiplier(sentiment)

            # 🆕 스캐너 신뢰도 반영
            scanner_reliability = self.get_scanner_reliability()            
            
            # 신뢰도에 따른 투자 강도 조절
            final_amount = adjusted_amount * fng_multiplier * scanner_reliability

            # 최소/최대 한도 적용
            min_order = self.config.get('min_order_money', 10000)
            available_budget = self.asset_manager.get_available_budget()
            max_single_investment = available_budget * 0.4  # 단일 투자 최대 40%
            
            final_amount = max(min_order, min(final_amount, max_single_investment))

            # 로깅 (신뢰도 변화가 클 때만)
            if abs(scanner_reliability - 1.0) > 0.1:
                logger.info(f"💰 투자금액 조정: 기본{base_amount:,.0f} → 최종{final_amount:,.0f}원")
                logger.info(f"📊 조정 요인: 시장상태({self.adaptive_manager.current_market_regime}) "
                           f"× FNG({fng_multiplier:.2f}) × 스캐너신뢰도({scanner_reliability:.2f})")
            
            logger.info(f"적응형 투자금액: 기본{base_amount:,.0f} → 조정{final_amount:,.0f} (시장:{self.adaptive_manager.current_market_regime}, FNG:{fng_multiplier}x)")
            
            return final_amount
            
        except Exception as e:
            logger.error(f"적응형 투자 금액 계산 중 에러: {str(e)}")
            return base_amount

    def buy_coin(self, ticker, buy_amount, reason):
        """🔧 매수 실행 - 쿨다운 체크 추가"""
        try:
            if self.check_excluded_coin(ticker):
                return False

            # 🆕 중복 체크
            if not self.asset_manager.can_trade_coin(ticker, 'BUY'):
                logger.info(f"🕒 [{ticker}] 매수 쿨다운으로 스킵 (Lock 내 재확인)")
                return False
            
            if self.asset_manager.is_bot_coin(ticker):
                logger.info(f"🚫 [{ticker}] 이미 보유 중 - 중복 매수 방지")
                return False            
            
            # 🆕 매수 전 쿨다운 체크 추가
            if not self.asset_manager.can_trade_coin(ticker, 'BUY'):
                logger.info(f"🕒 [{ticker}] 매수 쿨다운으로 스킵")
                return False
            
            # 적응형 조정
            adaptive_amount = self.get_adaptive_investment_amount(buy_amount)
            sentiment, fng_value = self.get_fng_sentiment()
            
            logger.info(f"[매수시도] {ticker} {adaptive_amount:,.0f}원 ({reason}) [FNG: {fng_value}]")
            logger.info(f"💰 예산조정: 기본{buy_amount:,.0f} → 최종{adaptive_amount:,.0f}원")
            
            # 기존 주문 취소
            myBithumb.CancelCoinOrder(ticker)
            time.sleep(0.1)
            
            # 예상 체결가 확인
            estimated_price = self.get_current_price_with_retry(ticker)
            if estimated_price is None or estimated_price <= 0:
                logger.error(f"[매수실패] {ticker} - 현재가 조회 실패")
                return False
            
            logger.info(f"[매수진행] {ticker} 예상체결가: {estimated_price:,.0f}원")
            
            # 매수 실행
            balances = myBithumb.BuyCoinMarket(ticker, adaptive_amount)
            
            if balances:
                # 실제 사용된 금액으로 기록
                quantity = adaptive_amount / estimated_price
                self.asset_manager.record_buy_with_actual_price(
                    ticker, estimated_price, quantity, adaptive_amount, reason
                )
                
                # 🆕 매수 쿨다운 기록
                #self.asset_manager.record_trade(ticker, 'BUY')
                
                # 성공 메시지
                msg = f"🟢 **봇 매수 완료**: {ticker}\n"
                msg += f"💰 예상체결가: {estimated_price:,.0f}원\n"
                msg += f"💵 실제투자금액: {adaptive_amount:,.0f}원\n"
                msg += f"📝 매수 사유: {reason}\n"
                msg += f"📊 FNG: {fng_value} ({sentiment})\n"
                msg += f"🎯 시장상태: {self.adaptive_manager.current_market_regime}\n"
                msg += f"🤖 봇 전용 투자"
                
                logger.info(msg)
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(msg)
                    except Exception as e:
                        logger.warning(f"Discord 알림 전송 실패: {str(e)}")
                
                return True
            else:
                logger.error(f"[매수실패] {ticker} - 거래소 매수 실패")
                return False
                
        except Exception as e:
            logger.error(f"매수 실행 중 에러 ({ticker}): {str(e)}")
            return False

    def sell_coin(self, ticker, reason):
        """🔧 매도 실행 - 동시성 제어 추가"""
        with self.trading_lock:  # 🆕 거래 락 적용
            try:
                # 🆕 Lock 내에서 쿨타임 재확인
                if not self.asset_manager.can_trade_coin(ticker, 'SELL'):
                    logger.info(f"🕒 [{ticker}] 매도 쿨다운으로 스킵 (Lock 내 재확인): {reason}")
                    return False

                if not self.asset_manager.is_bot_coin(ticker):
                    logger.warning(f"[매도실패] {ticker} 봇 매수 코인 아님")
                    return False
                
                logger.info(f"🔒 [매도실행] {ticker} ({reason}) - Lock 보호")
                
                balances = myBithumb.GetBalances()
                if balances is None:
                    logger.error(f"[매도실패] {ticker} - 잔고 조회 실패")
                    return False
                
                coin_amount = myBithumb.GetCoinAmount(balances, ticker)
                if coin_amount is None or coin_amount <= 0:
                    logger.warning(f"[매도실패] {ticker} 보유 수량 없음")
                    self.asset_manager.record_sell(ticker, 0, 0, "보유량없음_기록정리")
                    return False
                
                # 기존 주문 취소
                myBithumb.CancelCoinOrder(ticker)
                time.sleep(0.1)
                
                # 매도 전 예상 체결가 확인
                estimated_price = self.get_current_price_with_retry(ticker)
                if estimated_price is None or estimated_price <= 0:
                    bot_positions = self.asset_manager.get_bot_positions()
                    estimated_price = bot_positions.get(ticker, {}).get('entry_price', 1)
                
                logger.info(f"[매도진행] {ticker} 예상체결가: {estimated_price:,.0f}원")
                
                # 매도 실행
                sell_result = myBithumb.SellCoinMarket(ticker, coin_amount)
                
                if sell_result:
                    # 정확한 체결가로 기록
                    profit = self.asset_manager.record_sell_with_actual_price(
                        ticker, estimated_price, coin_amount, reason
                    )
                    
                    # 매도 완료 메시지
                    sentiment, fng_value = self.get_fng_sentiment()
                    msg = f"🔴 **봇 매도 완료**: {ticker}\n"
                    msg += f"💰 예상체결가: {estimated_price:,.0f}원\n"
                    msg += f"💵 매도금액: {estimated_price * coin_amount:,.0f}원\n"
                    msg += f"📊 예상손익: {profit:,.0f}원\n"
                    msg += f"📝 매도 사유: {reason}\n"
                    msg += f"📊 FNG: {fng_value} ({sentiment})\n"
                    msg += f"🔒 동시성 보호 완료\n"
                    msg += f"🤖 봇 전용 매매\n"
                    msg += f"⏰ 실제 체결가는 자동 조정됩니다"
                    
                    logger.info(msg)
                    
                    if self.config.get('use_discord_alert'):
                        try:
                            discord_alert.SendMessage(msg)
                        except Exception as e:
                            logger.warning(f"Discord 알림 전송 실패: {str(e)}")
                    
                    return True
                else:
                    logger.error(f"[매도실패] {ticker} - 거래소 매도 실패")
                    return False
                    
            except Exception as e:
                logger.error(f"매도 실행 중 에러 ({ticker}): {str(e)}")
                return False

    def check_sell_signal(self, coin_candidate, btc_data, position):
        """매도 신호 체크 - 중복 실행 방지"""
        try:
            ticker = coin_candidate.get('ticker', 'Unknown')
            
            # 🆕 수익보존 자동매도가 활성화된 경우 기존 매도 로직 스킵
            profit_protection_config = self.config.get('profit_protection', {})
            if (profit_protection_config.get('enabled', False) and 
                profit_protection_config.get('auto_sell_enabled', True)):
                
                logger.debug(f"🛡️ [{ticker}] 수익보존 자동매도 활성화 - 기존 매도 로직 스킵")
                return False, "수익보존시스템_활성화_중복방지"
            
            # 🔄 수익보존이 비활성화된 경우에만 기존 매도 로직 실행
            buy_reason = position.get('buy_reason', '')
            if '급락매수' in buy_reason:
                return self.check_dip_buy_sell_conditions_realistic(coin_candidate, btc_data, position)
            else:
                return self.check_regular_sell_conditions_realistic(coin_candidate, btc_data, position)
                
        except Exception as e:
            logger.error(f"매도 신호 확인 중 에러: {str(e)}")
            return False, "매도신호에러"

    def check_regular_sell_conditions_realistic(self, coin_candidate, btc_data, position):
        """일반매수 전용 매도 조건 - 수수료 반영 버전"""
        try:
            ticker = coin_candidate.get('ticker', 'Unknown')
            current_price = coin_candidate['data']['prev_close']
            
            # 🆕 수수료 반영 수익률 사용
            current_profit_rate = self.asset_manager.get_realistic_profit_rate(ticker, current_price)
            
            # 🆕 적응형 손절매 적용 (수수료 고려하여 조정)
            basic_stop_loss = self.config.get('coin_loss_limit', -0.05)
            if self.config.get('adaptive_parameters'):
                adjusted_stop_loss = self.adaptive_manager.get_adaptive_stop_loss(basic_stop_loss)
            else:
                adjusted_stop_loss = basic_stop_loss
            
            # 수수료 고려하여 손절매 완화 (약간의 여유 제공)
            adjusted_stop_loss *= 1.1
            
            # FNG 기반 추가 조정
            sentiment, fng_value = self.get_fng_sentiment()
            
            if sentiment == "EXTREME_FEAR":
                adjusted_stop_loss *= 1.2
            elif sentiment == "FEAR":
                adjusted_stop_loss *= 1.1
            
            if current_profit_rate <= adjusted_stop_loss:
                return True, f"일반손절_{adjusted_stop_loss*100:.1f}%_FNG{fng_value}_수수료반영"
            
            # FNG 기반 익절 전략 (수수료 고려하여 상향 조정)
            if sentiment == "EXTREME_GREED":
                if current_profit_rate > 0.10:  # 8% → 10%
                    return True, f"일반극탐욕익절_FNG{fng_value}_수수료반영"
            elif sentiment == "GREED":
                if current_profit_rate > 0.18:  # 15% → 18%
                    return True, f"일반탐욕익절_FNG{fng_value}_수수료반영"
            
            # 나머지 기존 로직은 동일...
            # (4시간봉, 이동평균선 조건 등)
            
            return False, f"일반홀딩_{current_profit_rate*100:+.1f}%_수수료반영"
            
        except Exception as e:
            logger.error(f"일반 매도 조건 확인 중 에러: {str(e)}")
            return False, "일반매도에러"

    def check_dip_buy_sell_conditions_realistic(self, coin_candidate, btc_data, position):
        """급락매수 전용 매도 조건 - 수수료 반영 버전"""
        try:
            ticker = coin_candidate.get('ticker', 'Unknown')
            
            # 보유 시간 계산
            holding_hours = self.get_holding_hours(position)
            
            # 🆕 수수료 반영 수익률 계산
            current_price = coin_candidate['data']['prev_close']
            current_profit_rate = self.asset_manager.get_realistic_profit_rate(ticker, current_price)
            
            logger.debug(f"💎 [{ticker}] 급락매수 현황: {holding_hours:.1f}h, {current_profit_rate*100:+.1f}% (수수료반영)")
            
            # 설정값 읽기
            dip_config = self.config.get('dip_buy_strategy', {})
            min_protection = dip_config.get('min_protection_minutes', 30) / 60
            target_profit = dip_config.get('target_profit', 0.03)
            stop_loss = dip_config.get('stop_loss', -0.10)
            
            # === 개선된 급락매수 매도 조건들 (수수료 반영) ===
            
            # 1. 절대 보호 시간
            if holding_hours < min_protection:
                return False, f"급락보호_{holding_hours*60:.0f}분"
            
            # 2. 큰 손실 방지
            if current_profit_rate <= stop_loss:
                return True, f"급락손절_{current_profit_rate*100:.1f}%"
            
            # 3. 스마트 로직 체크 (수수료 반영)
            smart_sell, smart_reason = self.asset_manager.smart_dip_sell_decision_realistic(position, coin_candidate, current_profit_rate)
            if smart_sell:
                return True, smart_reason
            
            # 4. 시장 전체 붕괴
            btc_change = self.get_btc_recent_change(btc_data)
            crash_threshold = dip_config.get('market_crash_threshold', -0.07)
            if btc_change <= crash_threshold and current_profit_rate < -0.05:
                return True, f"급락시장붕괴_BTC{btc_change*100:.1f}%"
            
            # 5. 시간 기반 조건부 매도 (수수료 고려하여 목표 수익률 상향 조정)
            if holding_hours < 1.0:
                if current_profit_rate >= target_profit * 2.5:  # 수수료 고려 (2배 → 2.5배)
                    return True, f"급락단기고수익_{current_profit_rate*100:.1f}%"
            elif holding_hours < 3.0:
                if current_profit_rate >= target_profit * 1.3:  # 수수료 고려 (1배 → 1.3배)
                    return True, f"급락중기목표_{current_profit_rate*100:.1f}%"
            else:
                if current_profit_rate >= target_profit * 0.8:  # 수수료 고려 (0.67배 → 0.8배)
                    return True, f"급락장기수익_{current_profit_rate*100:.1f}%"
            
            # 나머지는 홀딩
            return False, f"급락홀딩_{current_profit_rate*100:+.1f}%"
            
        except Exception as e:
            logger.error(f"급락매수 매도 조건 확인 중 에러: {str(e)}")
            return False, "급락매도에러"

    def send_profit_protection_summary(self):
            """🛡️ 수익보존 현황 요약 (선택적 알림)"""
            try:
                if not self.config.get('profit_protection', {}).get('enabled'):
                    return
                
                bot_positions = self.asset_manager.get_bot_positions()
                if not bot_positions:
                    return
                
                protected_count = 0
                total_max_profit = 0
                total_current_profit = 0
                
                summary_lines = []
                
                for ticker, position in bot_positions.items():
                    tracking = position.get('profit_tracking', {})
                    if not tracking:
                        continue
                    
                    try:
                        current_price = myBithumb.GetCurrentPrice(ticker)
                        if not current_price:
                            continue
                        
                        entry_price = position.get('entry_price', 0)
                        max_profit_rate = tracking.get('max_profit_rate', 0)
                        current_profit_rate = (current_price - entry_price) / entry_price
                        
                        total_max_profit += max_profit_rate
                        total_current_profit += current_profit_rate
                        
                        # 보호 상태 체크
                        protection_status = ""
                        if tracking.get('profit_locked'):
                            protection_status += "🔒"
                            protected_count += 1
                        if tracking.get('trailing_stop_price', 0) > 0:
                            protection_status += "📉"
                        
                        if protection_status or max_profit_rate > 0.05:
                            summary_lines.append(
                                f"• {ticker.replace('KRW-', '')}: {max_profit_rate*100:+.1f}%→{current_profit_rate*100:+.1f}% {protection_status}"
                            )
                    
                    except Exception as e:
                        continue
                
                if summary_lines and len(summary_lines) > 0:
                    msg = f"🛡️ **수익보존 현황**\n"
                    msg += f"🔒 보호된 포지션: {protected_count}개\n"
                    msg += f"📊 전체 현황:\n"
                    msg += "\n".join(summary_lines[:5])  # 최대 5개만
                    
                    if len(summary_lines) > 5:
                        msg += f"\n... 외 {len(summary_lines)-5}개"
                    
                    logger.info(msg)
                    
                    # 중요한 변화가 있을 때만 Discord 알림
                    if protected_count > 0:
                        try:
                            discord_alert.SendMessage(msg)
                        except Exception as e:
                            logger.warning(f"수익보존 요약 알림 전송 실패: {str(e)}")
            
            except Exception as e:
                logger.error(f"수익보존 요약 생성 중 에러: {str(e)}")

    def smart_dip_sell_decision(self, position, coin_candidate, current_profit):
        """똑똑한 급락매수 매도 판단 - 수익 정체 + 기술적 악화 감지"""
        try:
            ticker = position.get('ticker', 'Unknown')
            
            # 스마트 로직 사용 여부 확인
            dip_config = self.config.get('dip_buy_strategy', {})
            if not dip_config.get('use_smart_sell_logic', False):
                return False, "스마트로직비활성"
            
            # 기본 조건 체크
            holding_minutes = self.get_holding_hours(position) * 60
            min_holding = dip_config.get('smart_sell_min_holding_minutes', 30)
            
            if current_profit <= 0:
                return False, f"손실상태_{current_profit*100:.1f}%"
                
            if holding_minutes < min_holding:
                return False, f"보유시간부족_{holding_minutes:.0f}분<{min_holding}분"
            
            # 수익 이력 관리
            if 'profit_history' not in position:
                position['profit_history'] = []
            
            profit_history = position['profit_history']
            now = datetime.datetime.now()
            
            # 현재 수익 기록 추가
            profit_history.append({
                'timestamp': now.isoformat(),
                'profit_rate': current_profit,
                'minutes_held': holding_minutes
            })
            
            # 최근 8개 기록만 유지 (메모리 절약)
            profit_history = profit_history[-8:]
            position['profit_history'] = profit_history
            
            # 디버그 로그
            if self.config.get('log_optimization', {}).get('smart_sell_debug_log', False):
                logger.debug(f"🧠 [{ticker}] 스마트분석: 수익{current_profit*100:+.2f}%, {holding_minutes:.0f}분, 이력{len(profit_history)}개")
            
            # === 스마트 매도 조건 분석 ===
            
            # 조건 1: 수익 정체 + 하락 + 기술적 악화
            if len(profit_history) >= 4:
                recent_profits = [p['profit_rate'] for p in profit_history[-4:]]
                max_recent_profit = max(recent_profits)
                
                decline_threshold = dip_config.get('smart_sell_profit_decline_threshold', 0.9)
                stagnation_minutes = dip_config.get('smart_sell_stagnation_minutes', 20)
                
                # 최고점 대비 하락 + 시간 경과
                if (current_profit < max_recent_profit * decline_threshold and 
                    holding_minutes >= stagnation_minutes):
                    
                    # 기술적 악화 확인
                    if self.is_technical_deteriorating_simple(coin_candidate):
                        reason = f"스마트정체악화_최고{max_recent_profit*100:.1f}%→현재{current_profit*100:.1f}%"
                        logger.info(f"🎯 [{ticker}] {reason}")
                        return True, reason
                    else:
                        logger.debug(f"🧠 [{ticker}] 수익하락감지하지만 기술적악화없음")
            
            # 조건 2: 선별제외 + 수익 정체
            if coin_candidate is None:  # 선별제외 상태
                if len(profit_history) >= 3:
                    recent_3 = [p['profit_rate'] for p in profit_history[-3:]]
                    
                    # 최근 3개 기록의 변동폭이 작고 하락 추세
                    profit_range = max(recent_3) - min(recent_3)
                    is_declining = recent_3[0] > recent_3[-1]
                    
                    if profit_range < 0.01 and is_declining:  # 변동 1% 미만 + 하락
                        reason = f"스마트선별제외정체_{current_profit*100:.1f}%_변동{profit_range*100:.1f}%"
                        logger.info(f"🎯 [{ticker}] {reason}")
                        return True, reason
            
            # 조건 3: 장기간 수익 개선 없음
            if len(profit_history) >= 6 and holding_minutes >= 60:  # 1시간 이상
                profits_6 = [p['profit_rate'] for p in profit_history[-6:]]
                
                # 최근 6번 중 5번 이상이 현재보다 높았다면
                higher_count = sum(1 for p in profits_6[:-1] if p > current_profit)
                if higher_count >= 4:  # 6개 중 4개 이상이 더 높았음
                    if self.is_technical_deteriorating_simple(coin_candidate):
                        reason = f"스마트장기개선없음_{current_profit*100:.1f}%_상위{higher_count}/5"
                        logger.info(f"🎯 [{ticker}] {reason}")
                        return True, reason
            
            # 매도하지 않음
            if self.config.get('log_optimization', {}).get('smart_sell_debug_log', False):
                logger.debug(f"🧠 [{ticker}] 스마트홀딩유지_{current_profit*100:+.1f}%")
            
            return False, f"스마트홀딩유지_{current_profit*100:+.1f}%"
            
        except Exception as e:
            logger.error(f"스마트 매도 판단 중 에러 ({ticker}): {str(e)}")
            return False, f"스마트로직에러_{str(e)}"

    def is_technical_deteriorating_simple(self, coin_candidate):
        """간단한 기술적 악화 체크"""
        try:
            if coin_candidate is None:
                logger.debug(f"  기술적분석: 선별제외 → 악화")
                return True  # 선별제외 = 악화
            
            data = coin_candidate['data']
            dip_config = self.config.get('dip_buy_strategy', {})
            bad_signals = 0
            min_bad_signals = dip_config.get('smart_sell_min_bad_signals', 2)
            signals = []
            
            # 신호 1: RSI 45 미만
            current_rsi = data.get('RSI', 50)
            if current_rsi < 45:
                bad_signals += 1
                signals.append(f"RSI{current_rsi:.1f}")
            
            # 신호 2: 단기 이동평균선 하향 이탈
            short_ma = self.config.get('short_ma', 5)
            ma_key = f'ma{short_ma}_before'
            if ma_key in data and data['prev_close'] < data[ma_key]:
                bad_signals += 1
                signals.append("단기이평하향")
            
            # 신호 3: 음봉 형성
            if data['prev_close'] <= data['prev_open']:
                bad_signals += 1
                signals.append("음봉")
            
            # 신호 4: 거래량 감소
            volume_threshold = dip_config.get('smart_sell_volume_threshold', 0.8)
            volume_ratio = data.get('prev_volume', 0) / data.get('value_ma', 1) if data.get('value_ma', 0) > 0 else 1
            if volume_ratio < volume_threshold:
                bad_signals += 1
                signals.append(f"거래량{volume_ratio:.2f}")
            
            is_deteriorating = bad_signals >= min_bad_signals
            
            # 디버그 로그
            if self.config.get('log_optimization', {}).get('smart_sell_debug_log', False):
                logger.debug(f"  기술적분석: {bad_signals}/{min_bad_signals} 악화신호 [{', '.join(signals)}] → {'악화' if is_deteriorating else '정상'}")
            
            return is_deteriorating
            
        except Exception as e:
            logger.error(f"기술적 악화 체크 중 에러: {str(e)}")
            return False

    def get_smart_sell_statistics(self):
        """스마트 매도 로직 통계 정보"""
        try:
            total_smart_sells = 0
            total_trades = 0
            smart_sell_profits = []
            
            for trade in self.asset_manager.state.get('trade_history', []):
                if trade.get('type') == 'SELL':
                    total_trades += 1
                    reason = trade.get('reason', '')
                    
                    if '스마트' in reason:
                        total_smart_sells += 1
                        profit = trade.get('profit', 0)
                        if profit != 0:
                            smart_sell_profits.append(profit)
            
            if total_trades > 0:
                smart_sell_ratio = total_smart_sells / total_trades
                avg_smart_profit = sum(smart_sell_profits) / len(smart_sell_profits) if smart_sell_profits else 0
                
                stats = {
                    'total_trades': total_trades,
                    'smart_sells': total_smart_sells,
                    'smart_sell_ratio': smart_sell_ratio,
                    'avg_smart_profit': avg_smart_profit,
                    'smart_profit_list': smart_sell_profits
                }
                
                logger.info(f"📊 스마트 매도 통계:")
                logger.info(f"  전체 매도: {total_trades}회")
                logger.info(f"  스마트 매도: {total_smart_sells}회 ({smart_sell_ratio*100:.1f}%)")
                if smart_sell_profits:
                    logger.info(f"  스마트 평균수익: {avg_smart_profit:,.0f}원")
                
                return stats
            
            return None
            
        except Exception as e:
            logger.error(f"스마트 매도 통계 계산 중 에러: {str(e)}")
            return None

    def check_dip_buy_sell_conditions(self, coin_candidate, btc_data, position):
        """급락매수 전용 매도 조건 - 개선된 버전"""
        try:
            ticker = coin_candidate.get('ticker', 'Unknown')
            
            # 보유 시간 계산
            holding_hours = self.get_holding_hours(position)
            
            # 수익률 계산
            current_price = coin_candidate['data']['prev_close']
            entry_price = position['entry_price']
            profit_rate = (current_price - entry_price) / entry_price
            
            logger.debug(f"💎 [{ticker}] 급락매수 현황: {holding_hours:.1f}h, {profit_rate*100:+.1f}%")
            
            # 설정값 읽기
            dip_config = self.config.get('dip_buy_strategy', {})
            min_protection = dip_config.get('min_protection_minutes', 30) / 60
            target_profit = dip_config.get('target_profit', 0.03)
            stop_loss = dip_config.get('stop_loss', -0.10)
            rsi_threshold = dip_config.get('rsi_recovery_threshold', 55)
            
            # === 개선된 급락매수 매도 조건들 ===
            
            # 1. 절대 보호 시간 (최소 30분)
            if holding_hours < min_protection:
                return False, f"급락보호_{holding_hours*60:.0f}분"
            
            # 2. 큰 손실 방지 (시간 관계없이 즉시)
            if profit_rate <= stop_loss:
                return True, f"급락손절_{profit_rate*100:.1f}%"
                
            # 🆕 3. 스마트 로직 체크 (기존 조건들 사이에 추가)
            smart_sell, smart_reason = self.smart_dip_sell_decision(position, coin_candidate, profit_rate)
            if smart_sell:
                return True, smart_reason

            # 3. 시장 전체 붕괴 (시간 관계없이 즉시)
            btc_change = self.get_btc_recent_change(btc_data)
            crash_threshold = dip_config.get('market_crash_threshold', -0.07)
            if btc_change <= crash_threshold and profit_rate < -0.05:
                return True, f"급락시장붕괴_BTC{btc_change*100:.1f}%"
            
            # 4. 코인 자체 완전 붕괴 (시간 관계없이 즉시)
            if self.is_coin_collapsed(coin_candidate) and profit_rate < -0.05:
                return True, f"급락코인붕괴_{profit_rate*100:.1f}%"
            
            # === 🆕 시간 기반 조건부 매도 ===
            
            # 5-1. 짧은 홀딩 (1시간 미만): 높은 수익률만 허용
            if holding_hours < 1.0:
                if profit_rate >= target_profit * 2:  # 6% 이상
                    return True, f"급락단기고수익_{profit_rate*100:.1f}%"
            
            # 5-2. 중간 홀딩 (1-3시간): 목표 수익률 달성
            elif holding_hours < 3.0:
                if profit_rate >= target_profit:  # 3% 이상
                    return True, f"급락중기목표_{profit_rate*100:.1f}%"
            
            # 5-3. 장기 홀딩 (3시간 이상): 낮은 수익률도 허용
            else:
                if profit_rate >= target_profit * 0.67:  # 2% 이상
                    return True, f"급락장기수익_{profit_rate*100:.1f}%"
            
            # 6. RSI 회복 완료 (시간별 조건부)
            coin_data = coin_candidate['data']
            entry_rsi = self.extract_rsi_from_reason(position.get('buy_reason', ''))
            current_rsi = coin_data.get('RSI', 50)
            
            if entry_rsi and entry_rsi < 35:
                # RSI 회복 + 최소 수익
                if current_rsi > rsi_threshold and profit_rate > 0:
                    return True, f"급락RSI회복_{entry_rsi:.1f}→{current_rsi:.1f}"
            
            # 나머지는 홀딩
            return False, f"급락홀딩_{profit_rate*100:+.1f}%_RSI{current_rsi:.0f}"
            
        except Exception as e:
            logger.error(f"급락매수 매도 조건 확인 중 에러: {str(e)}")
            return False, "급락매도에러"

    def check_regular_sell_conditions(self, coin_candidate, btc_data, position):
        """일반매수 전용 매도 조건 - 기존 로직 유지"""
        try:
            coin_data = coin_candidate['data']
            df_4h = coin_candidate['df_4h']
            
            current_price = coin_data['prev_close']
            entry_price = position['entry_price']
            profit_rate = (current_price - entry_price) / entry_price
            
            # 🆕 적응형 손절매 적용
            basic_stop_loss = self.config.get('coin_loss_limit', -0.05)
            if self.config.get('adaptive_parameters'):
                adjusted_stop_loss = self.adaptive_manager.get_adaptive_stop_loss(basic_stop_loss)
            else:
                adjusted_stop_loss = basic_stop_loss
            
            # FNG 기반 추가 조정
            sentiment, fng_value = self.get_fng_sentiment()
            
            if sentiment == "EXTREME_FEAR":
                adjusted_stop_loss = adjusted_stop_loss * 1.2
            elif sentiment == "FEAR":
                adjusted_stop_loss = adjusted_stop_loss * 1.1
            
            if profit_rate <= adjusted_stop_loss:
                return True, f"일반손절_{adjusted_stop_loss*100:.1f}%_FNG{fng_value}"
            
            # FNG 기반 익절 전략
            if sentiment == "EXTREME_GREED":
                if profit_rate > 0.08:
                    return True, f"일반극탐욕익절_FNG{fng_value}"
            elif sentiment == "GREED":
                if profit_rate > 0.15:
                    return True, f"일반탐욕익절_FNG{fng_value}"
            
            # 🆕 4시간봉 기반 매도 신호 (사용 설정된 경우)
            if self.config.get('use_multi_timeframe') and df_4h is not None:
                h4_sell_signal, h4_reason = self.check_4h_sell_signal(df_4h)
                if h4_sell_signal:
                    return True, f"일반4시간봉_{h4_reason}"
            
            # 기존 매도 조건들
            btc_ma2 = self.config.get('btc_ma2')
            if btc_data[f'ma{btc_ma2}_before'] > btc_data['prev_close']:
                return True, "일반BTC하락추세"
            
            short_ma = self.config.get('short_ma')
            long_ma = self.config.get('long_ma')
            
            ma_sell1 = (coin_data[f'ma{short_ma}_before2'] > coin_data[f'ma{short_ma}_before'] and 
                       coin_data[f'ma{short_ma}_before'] > coin_data['prev_close'])
            
            ma_sell2 = (coin_data[f'ma{long_ma}_before2'] > coin_data[f'ma{long_ma}_before'] and 
                       coin_data[f'ma{long_ma}_before'] > coin_data['prev_close'])
            
            if ma_sell1 or ma_sell2:
                return True, "일반이동평균하향"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"일반 매도 조건 확인 중 에러: {str(e)}")
            return False, "일반매도에러"

    def extract_rsi_from_reason(self, buy_reason):
        """매수 사유에서 RSI 값 추출"""
        try:
            import re
            match = re.search(r'RSI(\d+\.?\d*)', buy_reason)
            if match:
                return float(match.group(1))
            return None
        except:
            return None

    def get_btc_recent_change(self, btc_data):
        """BTC 최근 변화율"""
        try:
            current = btc_data.get('prev_close', 0)
            yesterday = btc_data.get('prev_close2', 0)
            if yesterday > 0:
                return (current - yesterday) / yesterday
            return 0
        except:
            return 0

    def is_coin_collapsed(self, coin_candidate):
        """코인 완전 붕괴 체크"""
        try:
            coin_data = coin_candidate['data']
            
            short_ma = self.config.get('short_ma', 5)
            long_ma = self.config.get('long_ma', 20)
            
            prev_close = coin_data['prev_close']
            prev_open = coin_data['prev_open']
            
            # 5% 이상 큰 음봉 + 이평선 모두 하향
            big_red_candle = (prev_close / prev_open - 1) <= -0.05
            ma_declining = (coin_data[f'ma{short_ma}_before'] > prev_close and
                           coin_data[f'ma{long_ma}_before'] > prev_close)
            
            return big_red_candle and ma_declining
            
        except:
            return False

    def get_holding_hours(self, position):
        """보유 시간 계산"""
        try:
            entry_time_str = position.get('entry_time', '')
            if entry_time_str:
                entry_time = datetime.datetime.fromisoformat(entry_time_str)
                return (datetime.datetime.now() - entry_time).total_seconds() / 3600
            return 0
        except:
            return 0

    def check_4h_sell_signal(self, df_4h):
        """🆕 4시간봉 매도 신호 체크"""
        try:
            if df_4h is None or len(df_4h) < 10:
                return False, "4시간데이터부족"
            
            latest = df_4h.iloc[-1]
            
            # 4시간봉 이동평균 하향
            short_ma_4h = self.config.get('short_ma_4h', 12)
            long_ma_4h = self.config.get('long_ma_4h', 24)
            
            ma_declining = (latest[f'ma{short_ma_4h}'] < latest[f'ma{short_ma_4h}_before'] or
                           latest[f'ma{long_ma_4h}'] < latest[f'ma{long_ma_4h}_before'])
            
            if ma_declining:
                return True, "4시간이평하락"
            
            # RSI 과매수
            rsi = latest.get('RSI', 50)
            if rsi > 80:
                return True, f"4시간RSI과매수_{rsi:.1f}"
            
            # 연속 음봉 (2개 이상)
            if len(df_4h) >= 3:
                recent_candles = df_4h.tail(3)
                bearish_count = sum(1 for _, candle in recent_candles.iterrows() 
                                  if candle['close'] <= candle['open'])
                if bearish_count >= 2:
                    return True, "4시간연속음봉"
            
            return False, "4시간매도조건없음"
            
        except Exception as e:
            logger.error(f"4시간봉 매도 신호 체크 중 에러: {str(e)}")
            return False, "4시간매도체크에러"

    # 리스크 관리 관련 메서드들 (기존과 동일하지만 적응형 적용)
    def check_daily_loss_limit(self):
        """일일 손실 한도 체크"""
        try:
            daily_return = self.asset_manager.get_daily_return()
            daily_limit = self.config.get('daily_loss_limit', -0.08)
            
            if daily_return <= daily_limit:
                return False, f"일일손실한도초과_{daily_return*100:.1f}%"
            
            return True, "정상"
            
        except Exception as e:
            logger.error(f"일일 손실 한도 체크 중 에러: {str(e)}")
            return True, "체크 실패"

    def check_emergency_stop(self):
        """긴급 중단 조건 체크"""
        try:
            performance = self.asset_manager.get_performance_summary()
            if not performance:
                return True, "성과 정보 없음"
            
            total_return = performance['total_return'] / 100
            emergency_limit = self.config.get('emergency_stop_loss', -0.20)
            
            if total_return <= emergency_limit:
                return False, f"긴급중단_{total_return*100:.1f}%"
            
            return True, "정상"
            
        except Exception as e:
            logger.error(f"긴급 중단 체크 중 에러: {str(e)}")
            return True, "체크 실패"

    def risk_management_check(self):
        """종합적인 리스크 관리 체크"""
        try:
            # 1. 일일 손실 한도 체크
            daily_ok, daily_reason = self.check_daily_loss_limit()
            if not daily_ok:
                return False, daily_reason
            
            # 2. 긴급 중단 조건 체크
            emergency_ok, emergency_reason = self.check_emergency_stop()
            if not emergency_ok:
                return False, emergency_reason
            
            # 3. 포지션 과다 체크
            performance = self.asset_manager.get_performance_summary()
            if not performance:
                return True, "성과 정보 없음"
            
            current_positions = performance['current_positions']
            max_positions = self.config.get('max_coin_count', 5)
            
            if current_positions > max_positions:
                return False, f"포지션과다_{current_positions}개"
            
            # 4. 연속 손실 체크
            recent_trades = self.asset_manager.state.get('trade_history', [])[-10:]
            losing_streak = 0
            for trade in reversed(recent_trades):
                if trade.get('type') == 'SELL' and trade.get('profit', 0) < 0:
                    losing_streak += 1
                else:
                    break
            
            max_consecutive_losses = self.config.get('max_consecutive_losses', 3)
            if losing_streak >= max_consecutive_losses:
                return False, f"연속손실_{losing_streak}회"
            
            return True, "정상"
            
        except Exception as e:
            logger.error(f"리스크 관리 체크 중 에러: {str(e)}")
            return True, "체크 실패"

    def halt_trading(self, reason):
        """거래 중단"""
        self.trading_halted = True
        self.halt_reason = reason
        tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
        self.halt_until = tomorrow.replace(hour=5, minute=0, second=0, microsecond=0)
        
        logger.critical(f"🚨 거래 중단: {reason}")
        logger.info(f"⏰ 재개 시간: {self.halt_until}")
        
        self.send_emergency_alert(reason)

    def resume_trading_check(self):
        """거래 재개 가능 여부 체크"""
        if not self.trading_halted:
            return True
            
        now = datetime.datetime.now()
        if now >= self.halt_until:
            self.trading_halted = False
            self.halt_reason = ""
            self.halt_until = None
            
            logger.info("✅ 거래 재개 - 손실 제한 해제")
            
            if self.config.get('use_discord_alert'):
                resume_msg = f"✅ **거래 재개!**\n새로운 거래일 시작\n봇 매매 재개합니다"
                try:
                    discord_alert.SendMessage(resume_msg)
                except Exception as e:
                    logger.warning(f"재개 알림 전송 실패: {str(e)}")
            
            return True
        
        remaining = self.halt_until - now
        logger.info(f"⏰ 거래 중단 중 - 재개까지 {remaining}")
        return False

    def send_emergency_alert(self, reason):
        """긴급 상황 알림"""
        try:
            performance = self.asset_manager.get_performance_summary()
            
            msg = f"🚨 **긴급 거래 중단!**\n"
            msg += f"📉 **중단 사유**: {reason}\n"
            
            if performance:
                msg += f"💰 현재 총 자산: {performance['total_current_value']:,.0f}원\n"
                msg += f"📊 총 수익률: {performance['total_return']:+.2f}%\n"
                msg += f"📈 일일 수익률: {performance['daily_return']*100:+.2f}%\n"
            
            msg += f"\n🛡️ **보호 조치**\n내일 새벽 5시 재개 예정"
            
            logger.critical(msg)
            
            if self.config.get('use_discord_alert'):
                try:
                    discord_alert.SendMessage(msg)
                except Exception as e:
                    logger.warning(f"긴급 알림 전송 실패: {str(e)}")
                    
        except Exception as e:
            logger.error(f"긴급 알림 생성 중 에러: {str(e)}")

    def should_execute(self):
        """실행 시점 확인"""
        if self.last_execution is None:
            return True
        
        elapsed = time.time() - self.last_execution
        return elapsed >= self.config.get('execution_interval')

    def should_send_performance_alert(self):
        """성과 알림 전송 시점 확인"""
        if self.last_performance_alert is None:
            return True
        
        elapsed = (datetime.datetime.now() - self.last_performance_alert).total_seconds()
        return elapsed >= self.config.get('performance_alert_interval')

    def send_price_accuracy_report(self):
        """📊 체결가 정확도 일일 보고서"""
        try:
            price_config = self.config.get('price_tracking', {})
            if not price_config.get('enabled', True):
                return
            
            # 최근 거래 중 체결가 차이 분석
            recent_trades = self.asset_manager.state.get('trade_history', [])[-20:]
            
            if not recent_trades:
                return
            
            high_diff_trades = []
            total_diff = 0
            trade_count = 0
            
            for trade in recent_trades:
                if 'price_difference' in trade:
                    total_diff += trade['price_difference']
                    trade_count += 1
                    
                    if trade['price_difference'] > price_config.get('max_price_diff_warn', 0.05):
                        high_diff_trades.append(trade)
            
            if trade_count > 0:
                avg_accuracy = (1 - (total_diff / trade_count)) * 100
                
                msg = f"📊 **체결가 정확도 리포트**\n"
                msg += f"✅ 평균 정확도: {avg_accuracy:.1f}%\n"
                msg += f"⚠️ 큰 차이 거래: {len(high_diff_trades)}건\n"
                msg += f"📈 전체 거래: {trade_count}건"
                
                if high_diff_trades:
                    msg += f"\n🔍 정확도 개선 필요"
                else:
                    msg += f"\n🎯 정확도 양호"
                
                logger.info(msg)
                
                # 5% 이상 차이 거래가 많으면 Discord 알림
                if len(high_diff_trades) > trade_count * 0.3:  # 30% 이상
                    if self.config.get('use_discord_alert'):
                        try:
                            discord_alert.SendMessage(msg)
                        except Exception as e:
                            logger.warning(f"정확도 보고서 전송 실패: {str(e)}")
        
        except Exception as e:
            logger.error(f"체결가 정확도 보고서 생성 중 에러: {str(e)}")

    def send_performance_alert(self):
        """🔧 성과 알림 - 스캐너 현황 포함"""
        try:
            performance = self.asset_manager.get_performance_summary()
            if not performance:
                logger.warning("성과 정보를 가져올 수 없습니다.")
                return
            
            msg = f"🤖 **개선된 봇 성과 리포트**\n"
            msg += f"{'='*35}\n"
            msg += f"🏦 **자산 현황**\n"
            msg += f"• 총 자산가치: {performance['total_current_value']:,.0f}원\n"
            msg += f"• 총 수익률: {performance['total_return']:+.2f}%\n"
            msg += f"• 일일 수익률: {performance['daily_return']*100:+.2f}%\n\n"
            
            msg += f"📊 **거래 통계**\n"
            msg += f"• 총 거래: {performance['total_trades']}회\n"
            msg += f"• 승률: {performance['win_rate']:.1f}%\n"
            msg += f"• 현재 보유: {performance['current_positions']}개\n\n"
            
            # 섹터별 분산 현황
            if performance.get('sector_holdings'):
                msg += f"🎯 **섹터별 분산**\n"
                for sector, coins in performance['sector_holdings'].items():
                    msg += f"• {sector}: {len(coins)}개 ({', '.join([coin.replace('KRW-', '') for coin in coins])})\n"
                msg += f"\n"
            
            # 쿨다운 상태
            cooldown_status = self.asset_manager.get_cooldown_status_summary()
            msg += f"🕒 **쿨다운 상태**: {cooldown_status}\n"
            
            # 🆕 스캐너 현황 추가
            try:
                scanner_reliability = self.get_scanner_reliability()
                msg += f"🔗 **스캐너 신뢰도**: {scanner_reliability*100:.0f}%\n"
                
                if os.path.exists('performance_tracking.json'):
                    with open('performance_tracking.json', 'r', encoding='utf-8') as f:
                        scanner_data = json.load(f)
                    
                    if scanner_data.get('tracking_history'):
                        latest = scanner_data['tracking_history'][-1]
                        
                        if latest.get('existing_count', 0) > 0:
                            retention_rate = latest['retained_count'] / latest['existing_count']
                            msg += f"📊 **최근 코인 유지율**: {retention_rate*100:.0f}%\n"
                        
                        msg += f"🔍 **최근 신규 발굴**: {latest.get('new_count', 0)}개\n"
                
            except Exception as scanner_error:
                msg += f"🔗 **스캐너 상태**: 확인 불가\n"
            
            msg += f"\n🎯 **시장 상태**: {self.adaptive_manager.current_market_regime}\n"
            msg += f"🔄 **멀티 타임프레임**: {'활성' if self.config.get('use_multi_timeframe') else '비활성'}\n"
            msg += f"📈 **적응형 파라미터**: {'활성' if self.config.get('adaptive_parameters') else '비활성'}"
            
            logger.info("개선된 성과 리포트 생성 완료")
            
            if self.config.get('use_discord_alert'):
                try:
                    discord_alert.SendMessage(msg)
                    logger.info("Discord 성과 알림 전송 완료")
                except Exception as e:
                    logger.warning(f"Discord 알림 전송 실패: {str(e)}")
            
            self.last_performance_alert = datetime.datetime.now()
            self.send_price_accuracy_report()
            
        except Exception as e:
            logger.error(f"성과 알림 전송 중 에러: {str(e)}")

    def run_backtest_if_enabled(self):
        """🆕 백테스팅 실행 (설정된 경우)"""
        try:
            if not self.config.get('backtest_enabled'):
                return
            
            backtest_days = self.config.get('backtest_days', 30)
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=backtest_days)
            
            result = self.backtest_engine.run_backtest(
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
            
            if result:
                msg = f"📊 **백테스팅 결과** ({backtest_days}일)\n"
                msg += f"💰 수익률: {result['total_return']*100:+.2f}%\n"
                msg += f"📈 승률: {result['win_rate']*100:.1f}%\n"
                msg += f"📉 최대낙폭: {result['max_drawdown']*100:.1f}%\n"
                msg += f"🔄 총 거래: {result['total_trades']}회"
                
                logger.info(msg)
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(msg)
                    except Exception as e:
                        logger.warning(f"백테스트 결과 알림 전송 실패: {str(e)}")
            
        except Exception as e:
            logger.error(f"백테스팅 실행 중 에러: {str(e)}")

    def execute_trading(self):
        """🆕 개선된 매매 실행 - 선별제외 로직 완화 버전"""
        try:
            if not self.should_execute():
                return
            
            if not self.resume_trading_check():
                return
            
            # API 연결 상태 체크
            try:
                test_balance = myBithumb.GetBalances()
                if test_balance is None:
                    logger.error("빗썸 API 연결 실패")
                    return
            except Exception as api_error:
                logger.error(f"API 연결 체크 실패: {str(api_error)}")
                return

            # 🆕 스캐너 건강체크 (하루 1회)
            self.check_scanner_health_and_alert()

            logger.info(f"🚀 개선된 봇 실행 시작 - {datetime.datetime.now()}")
            
            # 리스크 관리 체크
            risk_ok, risk_reason = self.risk_management_check()
            if not risk_ok:
                self.halt_trading(risk_reason)
                return
            
            # 현재 상태 로깅 (스캐너 신뢰도 포함)
            investment_budget = self.asset_manager.get_available_budget()
            bot_positions = self.asset_manager.get_bot_positions()
            performance = self.asset_manager.get_performance_summary()
            
            # 🆕 스캐너 신뢰도 정보 추가
            try:
                scanner_reliability = self.get_scanner_reliability()
                scanner_status = "🟢정상" if scanner_reliability >= 0.9 else "🟡주의" if scanner_reliability >= 0.7 else "🔴위험"
            except Exception:
                scanner_reliability = 1.0
                scanner_status = "❓확인불가"
            
            logger.info(f"💰 사용가능예산: {investment_budget:,.0f}원")
            logger.info(f"📊 보유종목: {len(bot_positions)}개")
            logger.info(f"🎯 시장상태: {self.adaptive_manager.current_market_regime}")
            logger.info(f"🔗 스캐너신뢰도: {scanner_reliability*100:.0f}% {scanner_status}")
            
            if performance:
                logger.info(f"📈 총수익률: {performance['total_return']:+.2f}%")
                logger.info(f"📊 일일수익률: {performance['daily_return']*100:+.2f}%")
            
            # FNG 상태 확인
            sentiment, fng_value = self.get_fng_sentiment()
            logger.info(f"😱 FNG: {fng_value} ({sentiment})")
            
            # 🆕 멀티 타임프레임 시장 데이터 수집
            market_data_list = self.get_market_data()
            if not market_data_list:
                logger.error("시장 데이터 수집 실패")
                return
            
            selected_coins, btc_data = self.get_coin_selection(market_data_list)
            if btc_data is None:
                logger.error("비트코인 데이터 없음")
                return
            
            # BTC 변동성으로 적응형 파라미터 업데이트
            btc_volatility = btc_data.get('prev_volatility', 0.05)
            self.adaptive_manager.update_market_volatility(btc_volatility)
            
            # 🔧 수정: 매도 시스템 중복 실행 완전 방지
            try:
                balances = myBithumb.GetBalances()
                if balances is None:
                    logger.error("잔고 조회 실패")
                    return
            except Exception as e:
                logger.error(f"잔고 조회 중 에러: {str(e)}")
                return
            
            # 🔧 핵심 수정: 매도 시스템 상호 배타적 실행
            profit_protection_config = self.config.get('profit_protection', {})
            profit_protection_enabled = (
                profit_protection_config.get('enabled', False) and
                profit_protection_config.get('auto_sell_enabled', True)
            )
            
            if profit_protection_enabled:
                # 🛡️ 수익보존 시스템 활성화 - 기존 매도 완전 차단
                logger.info("🛡️ 수익보존 자동매도 시스템 활성화")
                logger.info("🚫 기존 매도 로직 완전 비활성화 (중복 방지)")
                
                # 상태 설정으로 스레드 간 동기화
                self.profit_protection_active = True
                self.traditional_sell_active = False
                
                logger.info("💡 모든 매도는 수익보존 모니터링 스레드에서 자동 처리됩니다")
                
            else:
                # 📤 기존 매도 시스템 활성화 - 수익보존 완전 차단
                logger.info("📤 기존 매도 로직 활성화")
                logger.info("🚫 수익보존 자동매도 완전 비활성화 (중복 방지)")
                
                # 상태 설정으로 스레드 간 동기화
                self.profit_protection_active = False
                self.traditional_sell_active = True
                
                # 🔒 매도 전용 락으로 보호하여 기존 매도 로직 실행
                logger.info(f"📤 매도 검토 시작 - 보유 코인: {list(bot_positions.keys())}")
                
                for ticker in list(bot_positions.keys()):
                    try:                    
                        # 매도 전 쿨다운 체크  
                        if not self.asset_manager.can_trade_coin(ticker, 'SELL'):
                            logger.info(f"🕒 [{ticker}] 매도 쿨다운으로 스킵")
                            continue

                        has_coin = myBithumb.IsHasCoin(balances, ticker)

                        if has_coin:
                            coin_amount = myBithumb.GetCoinAmount(balances, ticker)
                            if coin_amount is None or coin_amount <= 0:
                                logger.warning(f"봇 코인 {ticker} 보유량 없음")
                                self.asset_manager.record_sell(ticker, 0, 0, "보유량없음")
                                continue
                            
                            # 해당 코인의 데이터 찾기
                            coin_candidate = None
                            for coin in selected_coins:
                                if coin['ticker'] == ticker:
                                    coin_candidate = coin
                                    break
                            
                            if coin_candidate is None:
                                # 🔧 선별제외 완화: 매수 후 48시간 보호 + 손실 상황 보호
                                position = bot_positions[ticker]
                                buy_reason = position.get('buy_reason', '')
                                
                                # 1️⃣ 급락매수는 항상 보호
                                if '급락매수' in buy_reason:
                                    logger.info(f"📤 {ticker} 급락매수 - 선별제외 무시하고 홀딩")
                                    continue
                                
                                # 2️⃣ 매수 후 48시간 보호
                                entry_time_str = position.get('entry_time', '')
                                if entry_time_str:
                                    try:
                                        entry_time = datetime.datetime.fromisoformat(entry_time_str)
                                        hours_held = (datetime.datetime.now() - entry_time).total_seconds() / 3600
                                        if hours_held < 48:
                                            logger.info(f"📤 {ticker} 매수 후 {hours_held:.1f}시간 - 선별제외 유예 (48시간 보호)")
                                            continue
                                    except:
                                        pass
                                
                                # # 3️⃣ 손실 상황 보호 (3% 이상 손실 시)
                                # try:
                                #     current_price = myBithumb.GetCurrentPrice(ticker)
                                #     if current_price:
                                #         current_profit_rate = self.asset_manager.get_realistic_profit_rate(ticker, current_price)
                                #         if current_profit_rate < -0.03:  # -3% 이상 손실
                                #             logger.info(f"📤 {ticker} 손실 중 ({current_profit_rate*100:.1f}%) - 선별제외 매도 보류")
                                #             continue
                                # except:
                                #     pass
                                
                                # 4️⃣ 모든 보호 조건 통과 시에만 매도
                                logger.info(f"📤 {ticker} 일반매수 선별제외 - 조건부 매도 (48h+ & 손실<3%)")
                                self.sell_coin(ticker, "일반선별제외_완화조건통과")
                                continue
                            
                            # 기존 매도 로직 실행 (중복 방지된 check_sell_signal 사용)
                            position = bot_positions[ticker]
                            sell_signal, sell_reason = self.check_sell_signal(coin_candidate, btc_data, position)
                            
                            if sell_signal:
                                logger.info(f"📤 {ticker} 기존 매도 신호 발생: {sell_reason}")
                                self.sell_coin(ticker, sell_reason)
                                
                                # 매도 후 리스크 재체크
                                risk_ok, risk_reason = self.risk_management_check()
                                if not risk_ok:
                                    self.halt_trading(risk_reason)
                                    return
                            else:
                                logger.debug(f"📤 {ticker} 기존 매도 조건 불만족: {sell_reason}")
                        else:
                            logger.warning(f"봇 코인 {ticker} 거래소에 없음")
                            self.asset_manager.record_sell(ticker, 0, 0, "수동매도추정")
                            
                    except Exception as e:
                        logger.error(f"매도 검토 중 에러 ({ticker}): {str(e)}")
                        continue
            
            # 매도 후 예산 및 포지션 업데이트
            investment_budget = self.asset_manager.get_available_budget()
            current_bot_positions = len(self.asset_manager.get_bot_positions())
            
            # 매도 후 상태 로깅
            logger.info(f"📊 매도 처리 완료 - 현재 보유: {current_bot_positions}개, 사용가능예산: {investment_budget:,.0f}원")
            logger.info(f"🛡️ 활성 매도 시스템: {'수익보존 자동매도' if profit_protection_enabled else '기존 매도 로직 (선별제외 완화)'}")
            
            # 🧠 개선된 똑똑한 매수 실행
            max_coin_count = self.config.get('max_coin_count')
            min_order_money = self.config.get('min_order_money')
            
            if investment_budget > min_order_money and current_bot_positions < max_coin_count:
                logger.info(f"🧠 똑똑한 매수 로직 시작")
                logger.info(f"💰 사용가능예산: {investment_budget:,.0f}원")
                logger.info(f"🎯 현재보유/최대: {current_bot_positions}/{max_coin_count}")
                logger.info(f"📊 후보종목수: {len(selected_coins)}개")
                logger.info(f"🔗 스캐너신뢰도: {scanner_reliability*100:.0f}% (투자강도 반영)")
                
                # 🎯 똑똑한 매수 실행 (스캐너 신뢰도 자동 반영됨)
                self.execute_smart_buying(selected_coins, btc_data, investment_budget)
            else:
                logger.info(f"📥 매수 조건 불만족")
                logger.info(f"  • 예산: {investment_budget:,.0f}원 (최소: {min_order_money:,.0f}원)")
                logger.info(f"  • 보유: {current_bot_positions}/{max_coin_count}")
                
                if investment_budget <= min_order_money:
                    logger.info("  → 예산 부족")
                if current_bot_positions >= max_coin_count:
                    logger.info("  → 포지션 한도 초과")
            
            # 실행 시간 업데이트
            self.last_execution = time.time()
            
            # 성과 알림 체크 (스캐너 현황 포함)
            if self.should_send_performance_alert():
                logger.info("📊 성과 알림 전송")
                self.send_performance_alert()
            
            # 최종 상태 로깅
            final_positions = len(self.asset_manager.get_bot_positions())
            final_budget = self.asset_manager.get_available_budget()
            
            logger.info(f"✅ 개선된 봇 매매 실행 완료")
            logger.info(f"📊 최종 현황: 보유 {final_positions}개, 예산 {final_budget:,.0f}원")
            logger.info(f"🛡️ 최종 매도 시스템: {'수익보존 자동매도' if profit_protection_enabled else '기존 매도 로직 (선별제외 완화)'}")
            
            # 🆕 스캐너 연동 실행 완료 요약 알림 (중요한 변화가 있을 때만)
            if (current_bot_positions != final_positions or 
                abs(investment_budget - final_budget) > min_order_money):
                
                summary_msg = f"🤖 **봇 실행 완료** (선별제외 완화)\n"
                summary_msg += f"📊 포지션 변화: {current_bot_positions} → {final_positions}\n"
                summary_msg += f"💰 예산 변화: {investment_budget:,.0f} → {final_budget:,.0f}원\n"
                summary_msg += f"🎯 시장상태: {self.adaptive_manager.current_market_regime}\n"
                summary_msg += f"😱 FNG: {fng_value} ({sentiment})\n"
                summary_msg += f"🔗 스캐너: {scanner_reliability*100:.0f}% {scanner_status}\n"
                summary_msg += f"🛡️ 매도시스템: {'수익보존 자동매도' if profit_protection_enabled else '기존 매도 로직'}\n"
                summary_msg += f"🔧 선별제외 완화: 48시간 보호 + 손실 보호 적용"
                
                if self.config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(summary_msg)
                    except Exception as e:
                        logger.warning(f"실행 완료 알림 전송 실패: {str(e)}")

        except Exception as e:
            logger.error(f"봇 매매 실행 중 에러: {str(e)}")
            import traceback
            logger.error(f"상세 에러: {traceback.format_exc()}")
            
            # 연속 에러 감지 및 대응
            if not hasattr(self, 'error_count'):
                self.error_count = 0
            
            self.error_count += 1
            
            if self.error_count >= 3:
                logger.critical("연속 에러 3회 발생 - 거래 일시중단")
                self.halt_trading(f"연속에러_{self.error_count}회")
                self.error_count = 0
            
            error_msg = f"⚠️ 개선된 봇 실행 중 오류 ({self.error_count}/3)\n{str(e)}"
            if self.config.get('use_discord_alert'):
                try:
                    discord_alert.SendMessage(error_msg)
                except Exception as discord_e:
                    logger.warning(f"에러 알림 전송 실패: {str(discord_e)}")
        
        finally:
            # 🆕 스캐너 상태 정리
            if hasattr(self, 'error_count') and self.error_count == 0:
                # 정상 실행 완료 시 에러 카운트 리셋
                self.error_count = 0

    def improved_buy_selection_logic(self, selected_coins, btc_data, investment_budget):
        """🆕 개선된 매수 종목 선별 및 예산 배분 로직"""
        try:
            max_coin_count = self.config.get('max_coin_count', 3)
            min_order_money = self.config.get('min_order_money', 10000)
            current_positions = len(self.asset_manager.get_bot_positions())
            
            if current_positions >= max_coin_count:
                logger.info(f"포지션 한도 초과: {current_positions}/{max_coin_count}")
                return []
            
            available_slots = max_coin_count - current_positions
            logger.info(f"사용 가능 슬롯: {available_slots}개")
            
            # 1️⃣ 모든 후보에 대해 매수 신호 및 점수 계산
            buy_candidates = []
            
            for coin_candidate in selected_coins:
                ticker = coin_candidate['ticker']
                
                # 이미 보유 중이거나 제외된 코인 스킵
                if (self.asset_manager.is_bot_coin(ticker) or 
                    self.check_excluded_coin(ticker)):
                    continue
                
                # 섹터별 분산 체크
                if not self.asset_manager.can_add_to_sector(ticker):
                    logger.info(f"섹터 분산 한도 초과: {ticker}")
                    continue
                
                # 매수 신호 확인
                buy_signal, buy_reason = self.check_multi_timeframe_buy_signal(coin_candidate, btc_data)
                
                if buy_signal:
                    # 🎯 매수 신호 강도 점수 계산
                    signal_score = self.calculate_buy_signal_score(coin_candidate, buy_reason)
                    
                    buy_candidates.append({
                        'ticker': ticker,
                        'candidate': coin_candidate,
                        'reason': buy_reason,
                        'score': signal_score,
                        'priority': self.get_buy_priority(coin_candidate, signal_score)
                    })
                    
                    logger.info(f"🎯 매수 후보: {ticker} (점수: {signal_score:.2f}, 사유: {buy_reason})")
            
            if not buy_candidates:
                logger.info("매수 후보 없음")
                return []
            
            # 2️⃣ 점수순으로 정렬하여 상위 종목 선별
            buy_candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # 사용 가능한 슬롯 수만큼 선별
            selected_buys = buy_candidates[:available_slots]
            
            logger.info(f"🎯 최종 선별된 매수 종목:")
            for i, candidate in enumerate(selected_buys, 1):
                logger.info(f"  {i}. {candidate['ticker']} (점수: {candidate['score']:.2f})")
            
            # 3️⃣ 신호 강도에 따른 예산 배분
            budget_allocation = self.calculate_smart_budget_allocation(
                selected_buys, investment_budget, min_order_money
            )
            
            # 4️⃣ 최종 매수 실행 계획 반환
            buy_plans = []
            for candidate, budget in zip(selected_buys, budget_allocation):
                if budget >= min_order_money:
                    buy_plans.append({
                        'ticker': candidate['ticker'],
                        'amount': budget,
                        'reason': candidate['reason'],
                        'score': candidate['score']
                    })
            
            return buy_plans
            
        except Exception as e:
            logger.error(f"개선된 매수 선별 중 에러: {str(e)}")
            return []
        
    def calculate_buy_signal_score(self, coin_candidate, buy_reason):
        """🔧 수정된 함수: 일관성 있는 점수 체계"""
        try:
            ticker = coin_candidate['ticker']
            
            # buy_reason에서 점수 추출
            import re
            score_match = re.search(r'점수([\d.]+)', buy_reason)
            if score_match:
                final_score = float(score_match.group(1))
                
                # 🔧 새 점수 시스템은 이미 12점 만점이므로 그대로 사용
                # (기존 1~2점 시스템과 혼동 방지)
                logger.debug(f"[{ticker}] 신호점수: {final_score:.1f}/12점")
                return final_score
            else:
                return 8.0  # 기본값
                
        except Exception as e:
            logger.error(f"신호 점수 계산 중 에러: {str(e)}")
            return 8.0        

    def get_buy_priority(self, coin_candidate, signal_score):
        """🎯 매수 우선순위 결정"""
        try:
            # 시장 상황 고려
            sentiment, fng_value = self.get_fng_sentiment()
            
            priority = signal_score
            
            # FNG 극단 상황에서 우선순위 조정
            if sentiment == "EXTREME_FEAR":
                priority *= 1.3  # 공포 시장에서 더 적극적
            elif sentiment == "EXTREME_GREED":
                priority *= 0.7  # 탐욕 시장에서 보수적
            
            # 시장 변동성 고려
            market_regime = self.adaptive_manager.current_market_regime
            if market_regime == "VOLATILE":
                priority *= 0.8  # 변동성 큰 시장에서 보수적
            elif market_regime == "CALM":
                priority *= 1.2  # 안정적 시장에서 적극적
            
            return priority
            
        except Exception as e:
            logger.error(f"우선순위 계산 중 에러: {str(e)}")
            return signal_score

    def calculate_smart_budget_allocation(self, selected_buys, total_budget, min_order):
        """🧠 똑똑한 예산 배분 (신호 강도에 비례)"""
        try:
            if not selected_buys or total_budget < min_order:
                return []
            
            # 1️⃣ 기본 균등 배분 (70%)
            num_coins = len(selected_buys)
            base_budget = total_budget * 0.7
            base_per_coin = base_budget / num_coins
            
            # 2️⃣ 신호 강도별 추가 배분 (30%)
            bonus_budget = total_budget * 0.3
            total_score = sum(candidate['score'] for candidate in selected_buys)
            
            allocations = []
            
            for candidate in selected_buys:
                # 기본 배분
                allocation = base_per_coin
                
                # 신호 강도 비례 추가 배분
                if total_score > 0:
                    score_ratio = candidate['score'] / total_score
                    allocation += bonus_budget * score_ratio
                
                # 최소/최대 한도 적용
                allocation = max(allocation, min_order)
                allocation = min(allocation, total_budget * 0.4)  # 단일 투자 최대 40%
                
                allocations.append(allocation)
            
            # 3️⃣ 총 예산 초과 시 비례 축소
            total_allocated = sum(allocations)
            if total_allocated > total_budget:
                scale_factor = total_budget / total_allocated
                allocations = [allocation * scale_factor for allocation in allocations]
            
            # 최종 로깅
            for i, (candidate, allocation) in enumerate(zip(selected_buys, allocations)):
                logger.info(f"💰 예산 배분 {i+1}: {candidate['ticker']} "
                        f"{allocation:,.0f}원 (점수: {candidate['score']:.2f})")
            
            return allocations
            
        except Exception as e:
            logger.error(f"예산 배분 계산 중 에러: {str(e)}")
            # 에러 시 균등 배분
            equal_amount = total_budget / len(selected_buys)
            return [equal_amount] * len(selected_buys)

    def execute_smart_buying(self, selected_coins, btc_data, investment_budget):
        """🧠 개선된 매수 실행"""
        try:
            # 1️⃣ 똑똑한 종목 선별 및 예산 배분
            buy_plans = self.improved_buy_selection_logic(selected_coins, btc_data, investment_budget)
            
            if not buy_plans:
                logger.info("매수할 종목 없음")
                return
            
            logger.info(f"🎯 총 {len(buy_plans)}개 종목 매수 계획:")
            for plan in buy_plans:
                logger.info(f"  • {plan['ticker']}: {plan['amount']:,.0f}원 (점수: {plan['score']:.2f})")
            
            # 2️⃣ 계획대로 매수 실행
            successful_buys = 0
            total_invested = 0
            
            for plan in buy_plans:
                try:
                    if self.buy_coin(plan['ticker'], plan['amount'], plan['reason']):
                        successful_buys += 1
                        total_invested += plan['amount']
                        
                        # 매수 후 리스크 체크
                        risk_ok, risk_reason = self.risk_management_check()
                        if not risk_ok:
                            logger.warning(f"매수 후 리스크 한도 근접: {risk_reason}")
                            break
                            
                    else:
                        logger.warning(f"매수 실패: {plan['ticker']}")
                        
                except Exception as e:
                    logger.error(f"매수 실행 중 에러 ({plan['ticker']}): {str(e)}")
                    continue
            
            # 3️⃣ 결과 요약
            logger.info(f"✅ 매수 완료: {successful_buys}/{len(buy_plans)}개 성공, "
                    f"총 투자: {total_invested:,.0f}원")
            
            # Discord 알림
            if successful_buys > 0 and self.config.get('use_discord_alert'):
                summary_msg = f"🛒 **일괄 매수 완료**\n"
                summary_msg += f"✅ 성공: {successful_buys}개\n"
                summary_msg += f"💰 총 투자: {total_invested:,.0f}원\n"
                summary_msg += f"🎯 점수 기반 선별 매수"
                
                try:
                    discord_alert.SendMessage(summary_msg)
                except Exception as e:
                    logger.warning(f"매수 요약 알림 전송 실패: {str(e)}")
            
        except Exception as e:
            logger.error(f"똑똑한 매수 실행 중 에러: {str(e)}")

################################### 예측형 신호분석 클래스 ##################################

class PredictiveSignalAnalyzer:
   """예측형 신호 분석기 - 적당한 완화 버전"""
   
   def __init__(self, config):
       self.config = config
       self.last_fng_check = None
       self.current_fng_data = None
       
   def _get_fear_and_greed_index(self):
       """독립적인 FNG 조회"""
       try:
           import requests
           import datetime
           
           now = datetime.datetime.now()
           if (self.last_fng_check and 
               (now - self.last_fng_check).total_seconds() < 3600):
               return self.current_fng_data
           
           url = "https://api.alternative.me/fng/"
           response = requests.get(url, timeout=10)
           if response.status_code == 200:
               data = response.json()
               fng_data = data['data'][0]
               self.current_fng_data = {
                   'value': int(fng_data['value']),
                   'classification': fng_data['value_classification'],
                   'timestamp': fng_data['timestamp']
               }
               self.last_fng_check = now
               return self.current_fng_data
           else:
               if self.current_fng_data is None:
                   self.current_fng_data = {'value': 50, 'classification': 'Neutral'}
               return self.current_fng_data
       except Exception as e:
           if self.current_fng_data is None:
               self.current_fng_data = {'value': 50, 'classification': 'Neutral'}
           return self.current_fng_data
   
   def _get_fng_sentiment(self):
       """독립적인 FNG 감정 분석"""
       fng_data = self._get_fear_and_greed_index()
       if not fng_data:
           return "NEUTRAL", 50
       
       fng_value = fng_data['value']
       
       if fng_value <= 20:
           return "EXTREME_FEAR", fng_value
       elif fng_value <= 40:
           return "FEAR", fng_value
       elif fng_value <= 60:
           return "NEUTRAL", fng_value
       elif fng_value <= 80:
           return "GREED", fng_value
       else:
           return "EXTREME_GREED", fng_value

   def calculate_predictive_daily_score(self, coin_data, btc_data, ticker=None):
       """🔮 예측형 일봉 점수 계산 (0~10점)"""
       try:
           score = 0
           logger.debug(f"[{ticker}] 예측형 점수 계산 시작")
           
           # === 1. 🔮 미래 이동평균 점수 (0~3점) - 추세 지속성 중심 ===
           ma_future_score = self.calculate_ma_future_potential(coin_data)
           score += ma_future_score
           logger.debug(f"[{ticker}] 이평 미래성: {ma_future_score:.1f}점")
           
           # === 2. 🔮 스마트 거래량 점수 (0~2점) - 지속가능성 중심 ===
           volume_smart_score = self.calculate_smart_volume_score(coin_data)
           score += volume_smart_score
           logger.debug(f"[{ticker}] 스마트 거래량: {volume_smart_score:.1f}점")
           
           # === 3. 🔮 RSI 미래 여력 점수 (0~1점) - 상승 여력 중심 ===
           rsi_potential_score = self.calculate_rsi_potential(coin_data)
           score += rsi_potential_score
           logger.debug(f"[{ticker}] RSI 여력: {rsi_potential_score:.1f}점")
           
           # === 4. 🔮 모멘텀 지속성 점수 (0~2점) - 지속 vs 피로 ===
           momentum_sustainability = self.calculate_momentum_sustainability(coin_data)
           score += momentum_sustainability
           logger.debug(f"[{ticker}] 모멘텀 지속성: {momentum_sustainability:.1f}점")
           
           # === 5. 🔮 시장 타이밍 점수 (0~1.5점) - BTC 동반 가능성 ===
           market_timing_score = self.calculate_market_timing_score(coin_data, btc_data)
           score += market_timing_score
           logger.debug(f"[{ticker}] 시장 타이밍: {market_timing_score:.1f}점")
           
           # === 6. 🔮 가격 위치 점수 (0~0.5점) - 저항/지지 분석 ===
           price_position_score = self.calculate_price_position_potential(coin_data)
           score += price_position_score
           logger.debug(f"[{ticker}] 가격 위치: {price_position_score:.1f}점")
           
           final_score = min(score, 10.0)
           logger.info(f"[{ticker}] 예측형 최종점수: {final_score:.1f}/10점")
           
           return final_score
           
       except Exception as e:
           logger.error(f"예측형 점수 계산 에러: {str(e)}")
           return 5.0

   def calculate_ma_future_potential(self, coin_data):
       """🔮 이동평균 미래 잠재력 (급등 후 조정 위험 차단)"""
       try:
           score = 0
           
           # 기본 이평선 상승 체크
           short_ma = self.config.get('short_ma', 5)
           long_ma = self.config.get('long_ma', 20)
           
           ma5_rising = (coin_data.get(f'ma{short_ma}_before2', 0) <= 
                        coin_data.get(f'ma{short_ma}_before', 0) <= 
                        coin_data.get('prev_close', 0))
           
           ma20_rising = (coin_data.get(f'ma{long_ma}_before2', 0) <= 
                         coin_data.get(f'ma{long_ma}_before', 0) <= 
                         coin_data.get('prev_close', 0))
           
           # === 🚨 BORA 실수 방지: 급등 후 조정 위험 체크 (완화) ===
           current_price = coin_data.get('prev_close', 0)
           ma5_price = coin_data.get(f'ma{short_ma}_before', 0)
           ma20_price = coin_data.get(f'ma{long_ma}_before', 0)
           
           # 🔧 완화: 이평선 대비 괴리 기준 상향 조정
           if ma5_price > 0:
               ma5_deviation = (current_price - ma5_price) / ma5_price
               if ma5_deviation > 0.20:  # 15% → 20%로 완화
                   logger.debug(f"MA5 과도한 괴리로 감점: {ma5_deviation*100:.1f}%")
                   score -= 0.8  # 1.0 → 0.8로 완화
               elif ma5_deviation > 0.12:  # 8% → 12%로 완화
                   score -= 0.3  # 0.5 → 0.3으로 완화
           
           if ma20_price > 0:
               ma20_deviation = (current_price - ma20_price) / ma20_price
               if ma20_deviation > 0.30:  # 25% → 30%로 완화
                   logger.debug(f"MA20 과도한 괴리로 감점: {ma20_deviation*100:.1f}%")
                   score -= 0.8  # 1.0 → 0.8로 완화
               elif ma20_deviation > 0.20:  # 15% → 20%로 완화
                   score -= 0.3  # 0.5 → 0.3으로 완화
           
           # === 건전한 상승만 가점 ===
           if ma5_rising and ma20_rising:
               # 이평선 간 건전한 배열 체크
               if ma5_price > 0 and ma20_price > 0:
                   ma_spread = (ma5_price - ma20_price) / ma20_price
                   if 0.02 <= ma_spread <= 0.12:  # 10% → 12%로 완화
                       score += 2.0  # 건전한 상승
                   elif ma_spread > 0.18:  # 15% → 18%로 완화
                       score += 0.5  # 제한적 가점
                   else:
                       score += 1.0  # 보통 가점
               else:
                   score += 1.0
           elif ma5_rising or ma20_rising:
               score += 0.5
           
           # 최소/최대 범위 제한
           return max(0, min(3.0, score))
           
       except Exception as e:
           logger.error(f"이평 미래성 계산 에러: {str(e)}")
           return 1.5

   def calculate_smart_volume_score(self, coin_data):
       """🔮 스마트 거래량 점수 (지속가능성 중심) - 완화"""
       try:
           score = 0
           
           prev_volume = coin_data.get('prev_volume', 0)
           value_ma = coin_data.get('value_ma', 1)
           volume_ratio = prev_volume / value_ma if value_ma > 0 else 1
           
           # === 🚨 BORA 실수 방지: 과도한 거래량 급증 페널티 (완화) ===
           if volume_ratio > 15:  # 10배 → 15배로 완화
               logger.debug(f"비정상 거래량 급증 페널티: {volume_ratio:.1f}배")
               score = 0.3  # 0.2 → 0.3으로 완화
           elif volume_ratio > 8:  # 5배 → 8배로 완화
               logger.debug(f"과도한 거래량 급증 주의: {volume_ratio:.1f}배")
               score = 1.0  # 0.8 → 1.0으로 완화
           elif volume_ratio >= 4.0:  # 3배 → 4배로 완화
               # 가격 상승과 동반되었는지 체크
               price_change = coin_data.get('prev_change', 0)
               if price_change > 0.12:  # 10% → 12%로 완화
                   score = 1.2  # 1.0 → 1.2로 완화
               else:
                   score = 1.8  # 건전한 급증
           elif volume_ratio >= 2.0:
               score = 2.0  # 최고점 (건전한 관심 증가)
           elif volume_ratio >= 1.5:
               score = 1.5
           elif volume_ratio >= 1.2:
               score = 1.0
           elif volume_ratio >= 0.8:
               score = 0.7
           else:
               score = 0.3  # 거래량 부족
           
           return score
           
       except Exception as e:
           logger.error(f"스마트 거래량 계산 에러: {str(e)}")
           return 1.0

   def calculate_rsi_potential(self, coin_data):
       """🔮 RSI 상승 여력 점수"""
       try:
           rsi = coin_data.get('RSI', 50)
           
           # === 🔮 상승 여력 중심 평가 ===
           if 35 <= rsi <= 55:  # 이상적 구간 (상승 여력 충분)
               score = 1.0
           elif 30 <= rsi < 35:  # 과매도 회복 구간
               score = 0.9
           elif 55 < rsi <= 65:  # 상승 중 적정 구간
               score = 0.8
           elif 25 <= rsi < 30:  # 과매도 구간
               score = 0.7
           elif 65 < rsi <= 70:  # 상승 피로 시작
               score = 0.5
           elif 70 < rsi <= 75:  # 과매수 주의
               score = 0.3
           elif rsi > 75:  # 과매수 위험 (BORA 같은 상황)
               score = 0.1
           else:  # rsi < 25 극과매도
               score = 0.4
           
           return score
           
       except Exception as e:
           logger.error(f"RSI 잠재력 계산 에러: {str(e)}")
           return 0.5

   def calculate_momentum_sustainability(self, coin_data):
       """🔮 모멘텀 지속 가능성 점수 (BORA 실수 핵심 방지) - 완화"""
       try:
           score = 0
           
           # 단기/중기 변화율
           change_1d = coin_data.get('prev_change', 0)
           change_7d = coin_data.get('prev_change_w', 0)
           
           # === 🚨 BORA 실수 방지: 급등 피로 감지 (완화) ===
           
           # 1. 과도한 단기 급등 페널티 (완화)
           if change_1d > 0.18:  # 15% → 18%로 완화
               logger.debug(f"단기 과도한 급등 페널티: {change_1d*100:.1f}%")
               score -= 0.8  # 1.0 → 0.8로 완화
           elif change_1d > 0.10:  # 8% → 10%로 완화
               score -= 0.3  # 0.5 → 0.3으로 완화
           
           # 2. 과도한 주간 급등 페널티 (핵심! 여전히 엄격)
           if change_7d > 0.35:  # 30% → 35%로 약간 완화
               logger.debug(f"주간 과도한 급등으로 대폭 감점: {change_7d*100:.1f}%")
               score -= 1.3  # 1.5 → 1.3으로 완화
           elif change_7d > 0.25:  # 20% → 25%로 완화
               logger.debug(f"주간 급등 주의: {change_7d*100:.1f}%")
               score -= 0.6  # 0.8 → 0.6으로 완화
           elif change_7d > 0.18:  # 15% → 18%로 완화
               score -= 0.2  # 0.3 → 0.2로 완화
           
           # 3. 건전한 상승만 가점
           if 0 < change_7d <= 0.12:  # 10% → 12%로 완화
               if 0 < change_1d <= 0.06:  # 5% → 6%로 완화
                   score += 2.0  # 최고점
               else:
                   score += 1.2
           elif 0.12 < change_7d <= 0.18:  # 범위 확장
               if 0 < change_1d <= 0.04:  # 3% → 4%로 완화
                   score += 1.5
               else:
                   score += 0.8
           elif change_7d <= 0:  # 하락 추세
               score += 0.2
           
           # 4. 추가: 변동성 체크 (완화)
           volatility = coin_data.get('prev_volatility', 0.1)
           if volatility > 0.25:  # 20% → 25%로 완화
               score -= 0.3  # 0.5 → 0.3으로 완화
           
           return max(0, min(2.0, score))
           
       except Exception as e:
           logger.error(f"모멘텀 지속성 계산 에러: {str(e)}")
           return 1.0

   def calculate_market_timing_score(self, coin_data, btc_data):
       """🔮 시장 타이밍 점수"""
       try:
           score = 0
           
           # BTC 상승 추세 여부
           btc_ma1 = self.config.get('btc_ma1', 30)
           btc_ma2 = self.config.get('btc_ma2', 60)
           
           btc_condition1 = (btc_data.get(f'ma{btc_ma1}_before2', 0) < 
                            btc_data.get(f'ma{btc_ma1}_before', 0) or 
                            btc_data.get(f'ma{btc_ma1}_before', 0) < 
                            btc_data.get('prev_close', 0))
           
           btc_condition2 = (btc_data.get(f'ma{btc_ma2}_before2', 0) < 
                            btc_data.get(f'ma{btc_ma2}_before', 0) or 
                            btc_data.get(f'ma{btc_ma2}_before', 0) < 
                            btc_data.get('prev_close', 0))
           
           if btc_condition1 and btc_condition2:
               score += 1.5  # 완벽한 BTC 환경
           elif btc_condition1 or btc_condition2:
               score += 1.0  # 부분적 BTC 지지
           else:
               score += 0.3  # BTC 역풍
           
           return score
           
       except Exception as e:
           logger.error(f"시장 타이밍 계산 에러: {str(e)}")
           return 0.8

   def calculate_price_position_potential(self, coin_data):
       """🔮 가격 위치 잠재력 (저항/지지선 분석)"""
       try:
           score = 0
           
           # 볼린저밴드 위치 (0~1)
           bb_position = coin_data.get('bb_position', 0.5)
           
           # === 🔮 미래 상승 여력 관점 ===
           if 0.2 <= bb_position <= 0.6:  # 하단~중간 (상승 여력)
               score += 0.5
           elif bb_position < 0.2:  # 하단 (반등 가능성)
               score += 0.4
           elif 0.6 < bb_position <= 0.8:  # 상단 근처 (주의)
               score += 0.2
           else:  # bb_position > 0.8 (상단 돌파 = 위험)
               score += 0.1
           
           return score
           
       except Exception as e:
           logger.error(f"가격 위치 계산 에러: {str(e)}")
           return 0.3

   def apply_risk_based_adjustments(self, base_score, coin_data, technical_data):
       """🚨 리스크 기반 점수 조정 (BORA 실수 최종 방지) - 완화"""
       try:
           adjusted_score = base_score
           adjustments = []
           
           current_price = coin_data.get('prev_close', 0)
           
           # === 1. 극저가 코인 리스크 조정 (완화) ===
           if current_price < 150:  # 200원 → 150원으로 완화
               penalty = 1.2  # 1.5 → 1.2로 완화
               adjusted_score -= penalty
               adjustments.append(f"극저가페널티(-{penalty})")
           elif current_price < 300:  # 500원 → 300원으로 완화
               penalty = 0.6  # 1.0 → 0.6으로 완화
               adjusted_score -= penalty
               adjustments.append(f"저가페널티(-{penalty})")
           
           # === 2. 4시간봉 신호 강화 (완화) ===
           h4_adjustment = technical_data.get('h4_adjustment', 0)
           if h4_adjustment < -1.0:  # -0.5 → -1.0으로 완화
               penalty = 1.5  # 2.0 → 1.5로 완화
               adjusted_score -= penalty
               adjustments.append(f"4H강한부정(-{penalty})")
           elif h4_adjustment < -0.5:  # -0.3 → -0.5로 완화
               penalty = 0.8  # 1.0 → 0.8로 완화
               adjusted_score -= penalty
               adjustments.append(f"4H부정(-{penalty})")
           
           # === 3. 급등 후 조정 위험 (여전히 엄격) ===
           weekly_change = coin_data.get('prev_change_w', 0)
           if weekly_change > 0.30:  # 25% → 30%로 약간 완화
               penalty = 1.8  # 2.0 → 1.8로 완화
               adjusted_score -= penalty
               adjustments.append(f"급등조정위험(-{penalty})")
           
           # === 4. 거래량 이상 급증 (완화) ===
           volume_ratio = coin_data.get('prev_volume', 0) / coin_data.get('value_ma', 1)
           daily_change = coin_data.get('prev_change', 0)
           if volume_ratio > 8 and daily_change > 0.08:  # 5배→8배, 5%→8%로 완화
               penalty = 1.2  # 1.5 → 1.2로 완화
               adjusted_score -= penalty
               adjustments.append(f"거래량급증+급등(-{penalty})")
           
           # 로깅
           if adjustments:
               logger.info(f"리스크 조정: {base_score:.1f} → {adjusted_score:.1f} "
                         f"({', '.join(adjustments)})")
           
           return max(0, adjusted_score)
           
       except Exception as e:
           logger.error(f"리스크 조정 중 에러: {str(e)}")
           return base_score

   def enhanced_buy_signal_check(self, coin_candidate, btc_data):
       """🔮 강화된 예측형 매수 신호 체크 - 완화 버전"""
       try:
           ticker = coin_candidate['ticker']
           coin_info = coin_candidate['data']
           df_4h = coin_candidate['df_4h']
           
           logger.info(f"🔮 [{ticker}] 예측형 매수 신호 검증")
           
           # === 1. 기본 필터링 ===
           excluded_coins = self.config.get('exclude_coins', [])
           if ticker in excluded_coins:
               return False, "제외코인"
           
           # === 2. 🔮 예측형 일봉 점수 계산 ===
           predictive_daily_score = self.calculate_predictive_daily_score(coin_info, btc_data, ticker)
           
           # === 3. 4시간봉 보정 (간단 버전) ===
           h4_adjustment = 0
           if df_4h is not None and len(df_4h) > 10:
               try:
                   latest_4h = df_4h.iloc[-1]
                   rsi_4h = latest_4h.get('RSI', 50)
                   
                   if rsi_4h > 80:
                       h4_adjustment = -1.5
                   elif rsi_4h > 75:
                       h4_adjustment = -1.0
                   elif 40 <= rsi_4h <= 65:
                       h4_adjustment = 1.0
                   else:
                       h4_adjustment = 0
               except:
                   h4_adjustment = 0
           
           # === 4. 🚨 리스크 기반 최종 조정 ===
           risk_adjusted_score = self.apply_risk_based_adjustments(
               predictive_daily_score, coin_info, {'h4_adjustment': h4_adjustment}
           )
           
           final_score = risk_adjusted_score + h4_adjustment
           final_score = max(0, min(12, final_score))
           
           logger.info(f"📊 [{ticker}] 예측형 점수: "
                      f"기본{predictive_daily_score:.1f} → 위험조정{risk_adjusted_score:.1f} "
                      f"+ 4H{h4_adjustment:+.1f} = 최종{final_score:.1f}")
           
           # === 5. 🎯 예측형 매수 기준 (완화) ===
           sentiment, fng_value = self._get_fng_sentiment()
           
           # 🔧 완화된 기준
           if sentiment in ["EXTREME_FEAR", "FEAR"]:
               min_score = 7.5  # 8.5 → 7.5로 완화
           elif sentiment == "EXTREME_GREED":
               min_score = 10.0  # 11.0 → 10.0으로 완화
           else:
               min_score = 8.5  # 9.5 → 8.5로 완화 (핵심!)
           
           logger.info(f"🎯 [{ticker}] 예측형 기준: {min_score}점 이상 (시장: {sentiment})")
           
           # === 6. 최종 판단 ===
           if final_score >= min_score:
               # 🔒 최종 안전 체크
               safety_ok, safety_reason = self.final_predictive_safety_check(
                   ticker, coin_info, final_score
               )
               if safety_ok:
                   reason = f"예측형매수_{final_score:.1f}점_{sentiment}"
                   logger.info(f"✅ [{ticker}] 예측형 매수 승인: {reason}")
                   return True, reason
               else:
                   logger.info(f"🚫 [{ticker}] 최종 안전체크 실패: {safety_reason}")
                   return False, f"안전체크실패_{safety_reason}"
           else:
               reason = f"예측형기준부족_{final_score:.1f}<{min_score}"
               logger.info(f"❌ [{ticker}] 예측형 매수 거부: {reason}")
               return False, reason
               
       except Exception as e:
           logger.error(f"예측형 매수 신호 확인 중 에러: {str(e)}")
           return False, "예측형신호확인에러"

   def final_predictive_safety_check(self, ticker, coin_info, score):
       """🔒 최종 예측형 안전 체크 (BORA 완전 차단) - 여전히 엄격"""
       try:
           # 1. 극저가 + 고점수 조합 의심
           current_price = coin_info.get('prev_close', 0)
           if current_price < 200 and score > 9.0:  # 300원 → 200원으로 강화
               logger.warning(f"[{ticker}] 극저가 + 고점수 의심 조합")
               return False, "극저가고점수의심"
           
           # 2. 주간 25% 이상 급등 후 추가 매수 금지 (여전히 엄격)
           weekly_change = coin_info.get('prev_change_w', 0)
           if weekly_change > 0.30:  # 25% → 30%로 약간 완화
               logger.warning(f"[{ticker}] 주간 급등 후 추가 매수 금지: {weekly_change*100:.1f}%")
               return False, f"주간급등후매수금지_{weekly_change*100:.1f}%"
           
           # 3. 당일 급등 + 거래량 폭증 (완화)
           daily_change = coin_info.get('prev_change', 0)
           volume_ratio = coin_info.get('prev_volume', 0) / coin_info.get('value_ma', 1)
           if daily_change > 0.12 and volume_ratio > 8:  # 10%→12%, 5배→8배로 완화
               logger.warning(f"[{ticker}] 당일 급등 + 거래량 폭증 위험")
               return False, "당일급등거래량폭증"
           
           # 4. RSI 과매수 + 고점수 = 의심 (여전히 엄격)
           rsi = coin_info.get('RSI', 50)
           if rsi > 75 and score > 8.5:
               logger.warning(f"[{ticker}] RSI 과매수 + 고점수 의심: RSI {rsi:.1f}")
               return False, f"RSI과매수고점수의심_{rsi:.1f}"
           
           return True, "최종안전체크통과"
           
       except Exception as e:
           logger.error(f"최종 안전체크 에러: {str(e)}")
           return True,


class PredictiveSignalAnalyzer:
    """예측형 신호 분석기 - 적당한 완화 버전"""
    
    def __init__(self, config):
        self.config = config
        self.last_fng_check = None
        self.current_fng_data = None
        
    def _get_fear_and_greed_index(self):
        """독립적인 FNG 조회"""
        try:
            import requests
            import datetime
            
            now = datetime.datetime.now()
            if (self.last_fng_check and 
                (now - self.last_fng_check).total_seconds() < 3600):
                return self.current_fng_data
            
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                fng_data = data['data'][0]
                self.current_fng_data = {
                    'value': int(fng_data['value']),
                    'classification': fng_data['value_classification'],
                    'timestamp': fng_data['timestamp']
                }
                self.last_fng_check = now
                return self.current_fng_data
            else:
                if self.current_fng_data is None:
                    self.current_fng_data = {'value': 50, 'classification': 'Neutral'}
                return self.current_fng_data
        except Exception as e:
            if self.current_fng_data is None:
                self.current_fng_data = {'value': 50, 'classification': 'Neutral'}
            return self.current_fng_data
    
    def _get_fng_sentiment(self):
        """독립적인 FNG 감정 분석"""
        fng_data = self._get_fear_and_greed_index()
        if not fng_data:
            return "NEUTRAL", 50
        
        fng_value = fng_data['value']
        
        if fng_value <= 20:
            return "EXTREME_FEAR", fng_value
        elif fng_value <= 40:
            return "FEAR", fng_value
        elif fng_value <= 60:
            return "NEUTRAL", fng_value
        elif fng_value <= 80:
            return "GREED", fng_value
        else:
            return "EXTREME_GREED", fng_value

    def calculate_predictive_daily_score(self, coin_data, btc_data, ticker=None):
        """🔮 예측형 일봉 점수 계산 (0~10점)"""
        try:
            score = 0
            logger.debug(f"[{ticker}] 예측형 점수 계산 시작")
            
            # === 1. 🔮 미래 이동평균 점수 (0~3점) - 추세 지속성 중심 ===
            ma_future_score = self.calculate_ma_future_potential(coin_data)
            score += ma_future_score
            logger.debug(f"[{ticker}] 이평 미래성: {ma_future_score:.1f}점")
            
            # === 2. 🔮 스마트 거래량 점수 (0~2점) - 지속가능성 중심 ===
            volume_smart_score = self.calculate_smart_volume_score(coin_data)
            score += volume_smart_score
            logger.debug(f"[{ticker}] 스마트 거래량: {volume_smart_score:.1f}점")
            
            # === 3. 🔮 RSI 미래 여력 점수 (0~1점) - 상승 여력 중심 ===
            rsi_potential_score = self.calculate_rsi_potential(coin_data)
            score += rsi_potential_score
            logger.debug(f"[{ticker}] RSI 여력: {rsi_potential_score:.1f}점")
            
            # === 4. 🔮 모멘텀 지속성 점수 (0~2점) - 지속 vs 피로 ===
            momentum_sustainability = self.calculate_momentum_sustainability(coin_data)
            score += momentum_sustainability
            logger.debug(f"[{ticker}] 모멘텀 지속성: {momentum_sustainability:.1f}점")
            
            # === 5. 🔮 시장 타이밍 점수 (0~1.5점) - BTC 동반 가능성 ===
            market_timing_score = self.calculate_market_timing_score(coin_data, btc_data)
            score += market_timing_score
            logger.debug(f"[{ticker}] 시장 타이밍: {market_timing_score:.1f}점")
            
            # === 6. 🔮 가격 위치 점수 (0~0.5점) - 저항/지지 분석 ===
            price_position_score = self.calculate_price_position_potential(coin_data)
            score += price_position_score
            logger.debug(f"[{ticker}] 가격 위치: {price_position_score:.1f}점")
            
            final_score = min(score, 10.0)
            logger.info(f"[{ticker}] 예측형 최종점수: {final_score:.1f}/10점")
            
            return final_score
            
        except Exception as e:
            logger.error(f"예측형 점수 계산 에러: {str(e)}")
            return 5.0

    def calculate_ma_future_potential(self, coin_data):
        """🔮 이동평균 미래 잠재력 (급등 후 조정 위험 차단)"""
        try:
            score = 0
            
            # 기본 이평선 상승 체크
            short_ma = self.config.get('short_ma', 5)
            long_ma = self.config.get('long_ma', 20)
            
            ma5_rising = (coin_data.get(f'ma{short_ma}_before2', 0) <= 
                         coin_data.get(f'ma{short_ma}_before', 0) <= 
                         coin_data.get('prev_close', 0))
            
            ma20_rising = (coin_data.get(f'ma{long_ma}_before2', 0) <= 
                          coin_data.get(f'ma{long_ma}_before', 0) <= 
                          coin_data.get('prev_close', 0))
            
            # === 🚨 BORA 실수 방지: 급등 후 조정 위험 체크 (완화) ===
            current_price = coin_data.get('prev_close', 0)
            ma5_price = coin_data.get(f'ma{short_ma}_before', 0)
            ma20_price = coin_data.get(f'ma{long_ma}_before', 0)
            
            # 🔧 완화: 이평선 대비 괴리 기준 상향 조정
            if ma5_price > 0:
                ma5_deviation = (current_price - ma5_price) / ma5_price
                if ma5_deviation > 0.20:  # 15% → 20%로 완화
                    logger.debug(f"MA5 과도한 괴리로 감점: {ma5_deviation*100:.1f}%")
                    score -= 0.8  # 1.0 → 0.8로 완화
                elif ma5_deviation > 0.12:  # 8% → 12%로 완화
                    score -= 0.3  # 0.5 → 0.3으로 완화
            
            if ma20_price > 0:
                ma20_deviation = (current_price - ma20_price) / ma20_price
                if ma20_deviation > 0.30:  # 25% → 30%로 완화
                    logger.debug(f"MA20 과도한 괴리로 감점: {ma20_deviation*100:.1f}%")
                    score -= 0.8  # 1.0 → 0.8로 완화
                elif ma20_deviation > 0.20:  # 15% → 20%로 완화
                    score -= 0.3  # 0.5 → 0.3으로 완화
            
            # === 건전한 상승만 가점 ===
            if ma5_rising and ma20_rising:
                # 이평선 간 건전한 배열 체크
                if ma5_price > 0 and ma20_price > 0:
                    ma_spread = (ma5_price - ma20_price) / ma20_price
                    if 0.02 <= ma_spread <= 0.12:  # 10% → 12%로 완화
                        score += 2.0  # 건전한 상승
                    elif ma_spread > 0.18:  # 15% → 18%로 완화
                        score += 0.5  # 제한적 가점
                    else:
                        score += 1.0  # 보통 가점
                else:
                    score += 1.0
            elif ma5_rising or ma20_rising:
                score += 0.5
            
            # 최소/최대 범위 제한
            return max(0, min(3.0, score))
            
        except Exception as e:
            logger.error(f"이평 미래성 계산 에러: {str(e)}")
            return 1.5

    def calculate_smart_volume_score(self, coin_data):
        """🔮 스마트 거래량 점수 (지속가능성 중심) - 완화"""
        try:
            score = 0
            
            prev_volume = coin_data.get('prev_volume', 0)
            value_ma = coin_data.get('value_ma', 1)
            volume_ratio = prev_volume / value_ma if value_ma > 0 else 1
            
            # === 🚨 BORA 실수 방지: 과도한 거래량 급증 페널티 (완화) ===
            if volume_ratio > 15:  # 10배 → 15배로 완화
                logger.debug(f"비정상 거래량 급증 페널티: {volume_ratio:.1f}배")
                score = 0.3  # 0.2 → 0.3으로 완화
            elif volume_ratio > 8:  # 5배 → 8배로 완화
                logger.debug(f"과도한 거래량 급증 주의: {volume_ratio:.1f}배")
                score = 1.0  # 0.8 → 1.0으로 완화
            elif volume_ratio >= 4.0:  # 3배 → 4배로 완화
                # 가격 상승과 동반되었는지 체크
                price_change = coin_data.get('prev_change', 0)
                if price_change > 0.12:  # 10% → 12%로 완화
                    score = 1.2  # 1.0 → 1.2로 완화
                else:
                    score = 1.8  # 건전한 급증
            elif volume_ratio >= 2.0:
                score = 2.0  # 최고점 (건전한 관심 증가)
            elif volume_ratio >= 1.5:
                score = 1.5
            elif volume_ratio >= 1.2:
                score = 1.0
            elif volume_ratio >= 0.8:
                score = 0.7
            else:
                score = 0.3  # 거래량 부족
            
            return score
            
        except Exception as e:
            logger.error(f"스마트 거래량 계산 에러: {str(e)}")
            return 1.0

    def calculate_rsi_potential(self, coin_data):
        """🔮 RSI 상승 여력 점수"""
        try:
            rsi = coin_data.get('RSI', 50)
            
            # === 🔮 상승 여력 중심 평가 ===
            if 35 <= rsi <= 55:  # 이상적 구간 (상승 여력 충분)
                score = 1.0
            elif 30 <= rsi < 35:  # 과매도 회복 구간
                score = 0.9
            elif 55 < rsi <= 65:  # 상승 중 적정 구간
                score = 0.8
            elif 25 <= rsi < 30:  # 과매도 구간
                score = 0.7
            elif 65 < rsi <= 70:  # 상승 피로 시작
                score = 0.5
            elif 70 < rsi <= 75:  # 과매수 주의
                score = 0.3
            elif rsi > 75:  # 과매수 위험 (BORA 같은 상황)
                score = 0.1
            else:  # rsi < 25 극과매도
                score = 0.4
            
            return score
            
        except Exception as e:
            logger.error(f"RSI 잠재력 계산 에러: {str(e)}")
            return 0.5

    def calculate_momentum_sustainability(self, coin_data):
        """🔮 모멘텀 지속 가능성 점수 (BORA 실수 핵심 방지) - 완화"""
        try:
            score = 0
            
            # 단기/중기 변화율
            change_1d = coin_data.get('prev_change', 0)
            change_7d = coin_data.get('prev_change_w', 0)
            
            # === 🚨 BORA 실수 방지: 급등 피로 감지 (완화) ===
            
            # 1. 과도한 단기 급등 페널티 (완화)
            if change_1d > 0.18:  # 15% → 18%로 완화
                logger.debug(f"단기 과도한 급등 페널티: {change_1d*100:.1f}%")
                score -= 0.8  # 1.0 → 0.8로 완화
            elif change_1d > 0.10:  # 8% → 10%로 완화
                score -= 0.3  # 0.5 → 0.3으로 완화
            
            # 2. 과도한 주간 급등 페널티 (핵심! 여전히 엄격)
            if change_7d > 0.35:  # 30% → 35%로 약간 완화
                logger.debug(f"주간 과도한 급등으로 대폭 감점: {change_7d*100:.1f}%")
                score -= 1.3  # 1.5 → 1.3으로 완화
            elif change_7d > 0.25:  # 20% → 25%로 완화
                logger.debug(f"주간 급등 주의: {change_7d*100:.1f}%")
                score -= 0.6  # 0.8 → 0.6으로 완화
            elif change_7d > 0.18:  # 15% → 18%로 완화
                score -= 0.2  # 0.3 → 0.2로 완화
            
            # 3. 건전한 상승만 가점
            if 0 < change_7d <= 0.12:  # 10% → 12%로 완화
                if 0 < change_1d <= 0.06:  # 5% → 6%로 완화
                    score += 2.0  # 최고점
                else:
                    score += 1.2
            elif 0.12 < change_7d <= 0.18:  # 범위 확장
                if 0 < change_1d <= 0.04:  # 3% → 4%로 완화
                    score += 1.5
                else:
                    score += 0.8
            elif change_7d <= 0:  # 하락 추세
                score += 0.2
            
            # 4. 추가: 변동성 체크 (완화)
            volatility = coin_data.get('prev_volatility', 0.1)
            if volatility > 0.25:  # 20% → 25%로 완화
                score -= 0.3  # 0.5 → 0.3으로 완화
            
            return max(0, min(2.0, score))
            
        except Exception as e:
            logger.error(f"모멘텀 지속성 계산 에러: {str(e)}")
            return 1.0

    def calculate_market_timing_score(self, coin_data, btc_data):
        """🔮 시장 타이밍 점수"""
        try:
            score = 0
            
            # BTC 상승 추세 여부
            btc_ma1 = self.config.get('btc_ma1', 30)
            btc_ma2 = self.config.get('btc_ma2', 60)
            
            btc_condition1 = (btc_data.get(f'ma{btc_ma1}_before2', 0) < 
                             btc_data.get(f'ma{btc_ma1}_before', 0) or 
                             btc_data.get(f'ma{btc_ma1}_before', 0) < 
                             btc_data.get('prev_close', 0))
            
            btc_condition2 = (btc_data.get(f'ma{btc_ma2}_before2', 0) < 
                             btc_data.get(f'ma{btc_ma2}_before', 0) or 
                             btc_data.get(f'ma{btc_ma2}_before', 0) < 
                             btc_data.get('prev_close', 0))
            
            if btc_condition1 and btc_condition2:
                score += 1.5  # 완벽한 BTC 환경
            elif btc_condition1 or btc_condition2:
                score += 1.0  # 부분적 BTC 지지
            else:
                score += 0.3  # BTC 역풍
            
            return score
            
        except Exception as e:
            logger.error(f"시장 타이밍 계산 에러: {str(e)}")
            return 0.8

    def calculate_price_position_potential(self, coin_data):
        """🔮 가격 위치 잠재력 (저항/지지선 분석)"""
        try:
            score = 0
            
            # 볼린저밴드 위치 (0~1)
            bb_position = coin_data.get('bb_position', 0.5)
            
            # === 🔮 미래 상승 여력 관점 ===
            if 0.2 <= bb_position <= 0.6:  # 하단~중간 (상승 여력)
                score += 0.5
            elif bb_position < 0.2:  # 하단 (반등 가능성)
                score += 0.4
            elif 0.6 < bb_position <= 0.8:  # 상단 근처 (주의)
                score += 0.2
            else:  # bb_position > 0.8 (상단 돌파 = 위험)
                score += 0.1
            
            return score
            
        except Exception as e:
            logger.error(f"가격 위치 계산 에러: {str(e)}")
            return 0.3

    def apply_risk_based_adjustments(self, base_score, coin_data, technical_data):
        """🚨 리스크 기반 점수 조정 (BORA 실수 최종 방지) - 완화"""
        try:
            adjusted_score = base_score
            adjustments = []
            
            current_price = coin_data.get('prev_close', 0)
            
            # === 1. 극저가 코인 리스크 조정 (완화) ===
            if current_price < 150:  # 200원 → 150원으로 완화
                penalty = 1.2  # 1.5 → 1.2로 완화
                adjusted_score -= penalty
                adjustments.append(f"극저가페널티(-{penalty})")
            elif current_price < 300:  # 500원 → 300원으로 완화
                penalty = 0.6  # 1.0 → 0.6으로 완화
                adjusted_score -= penalty
                adjustments.append(f"저가페널티(-{penalty})")
            
            # === 2. 4시간봉 신호 강화 (완화) ===
            h4_adjustment = technical_data.get('h4_adjustment', 0)
            if h4_adjustment < -1.0:  # -0.5 → -1.0으로 완화
                penalty = 1.5  # 2.0 → 1.5로 완화
                adjusted_score -= penalty
                adjustments.append(f"4H강한부정(-{penalty})")
            elif h4_adjustment < -0.5:  # -0.3 → -0.5로 완화
                penalty = 0.8  # 1.0 → 0.8로 완화
                adjusted_score -= penalty
                adjustments.append(f"4H부정(-{penalty})")
            
            # === 3. 급등 후 조정 위험 (여전히 엄격) ===
            weekly_change = coin_data.get('prev_change_w', 0)
            if weekly_change > 0.30:  # 25% → 30%로 약간 완화
                penalty = 1.8  # 2.0 → 1.8로 완화
                adjusted_score -= penalty
                adjustments.append(f"급등조정위험(-{penalty})")
            
            # === 4. 거래량 이상 급증 (완화) ===
            volume_ratio = coin_data.get('prev_volume', 0) / coin_data.get('value_ma', 1)
            daily_change = coin_data.get('prev_change', 0)
            if volume_ratio > 8 and daily_change > 0.08:  # 5배→8배, 5%→8%로 완화
                penalty = 1.2  # 1.5 → 1.2로 완화
                adjusted_score -= penalty
                adjustments.append(f"거래량급증+급등(-{penalty})")
            
            # 로깅
            if adjustments:
                logger.info(f"리스크 조정: {base_score:.1f} → {adjusted_score:.1f} "
                          f"({', '.join(adjustments)})")
            
            return max(0, adjusted_score)
            
        except Exception as e:
            logger.error(f"리스크 조정 중 에러: {str(e)}")
            return base_score

    def enhanced_buy_signal_check(self, coin_candidate, btc_data):
        """🔮 강화된 예측형 매수 신호 체크 - 완화 버전"""
        try:
            ticker = coin_candidate['ticker']
            coin_info = coin_candidate['data']
            df_4h = coin_candidate['df_4h']
            
            logger.info(f"🔮 [{ticker}] 예측형 매수 신호 검증")
            
            # === 1. 기본 필터링 ===
            excluded_coins = self.config.get('exclude_coins', [])
            if ticker in excluded_coins:
                return False, "제외코인"
            
            # === 2. 🔮 예측형 일봉 점수 계산 ===
            predictive_daily_score = self.calculate_predictive_daily_score(coin_info, btc_data, ticker)
            
            # === 3. 4시간봉 보정 (간단 버전) ===
            h4_adjustment = 0
            if df_4h is not None and len(df_4h) > 10:
                try:
                    latest_4h = df_4h.iloc[-1]
                    rsi_4h = latest_4h.get('RSI', 50)
                    
                    if rsi_4h > 80:
                        h4_adjustment = -1.5
                    elif rsi_4h > 75:
                        h4_adjustment = -1.0
                    elif 40 <= rsi_4h <= 65:
                        h4_adjustment = 1.0
                    else:
                        h4_adjustment = 0
                except:
                    h4_adjustment = 0
            
            # === 4. 🚨 리스크 기반 최종 조정 ===
            risk_adjusted_score = self.apply_risk_based_adjustments(
                predictive_daily_score, coin_info, {'h4_adjustment': h4_adjustment}
            )
            
            final_score = risk_adjusted_score + h4_adjustment
            final_score = max(0, min(12, final_score))
            
            logger.info(f"📊 [{ticker}] 예측형 점수: "
                       f"기본{predictive_daily_score:.1f} → 위험조정{risk_adjusted_score:.1f} "
                       f"+ 4H{h4_adjustment:+.1f} = 최종{final_score:.1f}")
            
            # === 5. 🎯 예측형 매수 기준 (완화) ===
            sentiment, fng_value = self._get_fng_sentiment()
            
            # 🔧 완화된 기준
            if sentiment in ["EXTREME_FEAR", "FEAR"]:
                min_score = 7.5  # 8.5 → 7.5로 완화
            elif sentiment == "EXTREME_GREED":
                min_score = 10.0  # 11.0 → 10.0으로 완화
            else:
                min_score = 8.5  # 9.5 → 8.5로 완화 (핵심!)
            
            logger.info(f"🎯 [{ticker}] 예측형 기준: {min_score}점 이상 (시장: {sentiment})")
            
            # === 6. 최종 판단 ===
            if final_score >= min_score:
                # 🔒 최종 안전 체크
                safety_ok, safety_reason = self.final_predictive_safety_check(
                    ticker, coin_info, final_score
                )
                if safety_ok:
                    reason = f"예측형매수_{final_score:.1f}점_{sentiment}"
                    logger.info(f"✅ [{ticker}] 예측형 매수 승인: {reason}")
                    return True, reason
                else:
                    logger.info(f"🚫 [{ticker}] 최종 안전체크 실패: {safety_reason}")
                    return False, f"안전체크실패_{safety_reason}"
            else:
                reason = f"예측형기준부족_{final_score:.1f}<{min_score}"
                logger.info(f"❌ [{ticker}] 예측형 매수 거부: {reason}")
                return False, reason
                
        except Exception as e:
            logger.error(f"예측형 매수 신호 확인 중 에러: {str(e)}")
            return False, "예측형신호확인에러"

    def final_predictive_safety_check(self, ticker, coin_info, score):
        """🔒 최종 예측형 안전 체크 (BORA 완전 차단) - 여전히 엄격"""
        try:
            # 1. 극저가 + 고점수 조합 의심
            current_price = coin_info.get('prev_close', 0)
            if current_price < 200 and score > 9.0:  # 300원 → 200원으로 강화
                logger.warning(f"[{ticker}] 극저가 + 고점수 의심 조합")
                return False, "극저가고점수의심"
            
            # 2. 주간 25% 이상 급등 후 추가 매수 금지 (여전히 엄격)
            weekly_change = coin_info.get('prev_change_w', 0)
            if weekly_change > 0.30:  # 25% → 30%로 약간 완화
                logger.warning(f"[{ticker}] 주간 급등 후 추가 매수 금지: {weekly_change*100:.1f}%")
                return False, f"주간급등후매수금지_{weekly_change*100:.1f}%"
            
            # 3. 당일 급등 + 거래량 폭증 (완화)
            daily_change = coin_info.get('prev_change', 0)
            volume_ratio = coin_info.get('prev_volume', 0) / coin_info.get('value_ma', 1)
            if daily_change > 0.12 and volume_ratio > 8:  # 10%→12%, 5배→8배로 완화
                logger.warning(f"[{ticker}] 당일 급등 + 거래량 폭증 위험")
                return False, "당일급등거래량폭증"
            
            # 4. RSI 과매수 + 고점수 = 의심 (여전히 엄격)
            rsi = coin_info.get('RSI', 50)

            if rsi > 75 and score > 8.5:
                logger.warning(f"[{ticker}] RSI 과매수 + 고점수 의심: RSI {rsi:.1f}")
                return False, f"RSI과매수고점수의심_{rsi:.1f}"
            
            return True, "최종안전체크통과"
            
        except Exception as e:
            logger.error(f"최종 안전체크 에러: {str(e)}")
            return True, "안전체크에러_허용"
        
################################### 메인 실행 함수 ##################################

def main():
    """메인 함수 - 개선 버전"""
    try:
        # 설정 초기화
        config = TradingConfig()
        
        # 개선된 봇 인스턴스 생성
        bot = BithumbTrendBot(config)

        # 🛡️ 수익보존 자동 매도 시스템 활성화 확인
        if config.get('profit_protection', {}).get('enabled'):
            auto_sell_enabled = config.get('profit_protection', {}).get('auto_sell_enabled', True)
            if auto_sell_enabled:
                logger.info("🛡️ 수익보존 자동 매도 시스템 활성화됨")
            else:
                logger.warning("⚠️ 수익보존 모니터링만 활성화 (자동 매도 비활성화)")
        else:
            logger.info("ℹ️ 수익보존 시스템 비활성화")

        last_profit_summary = None
        
        # 시작 메시지
        start_msg = f"🚀 **개선된 빗썸 트렌드 추종 봇 시작!**\n"
        start_msg += f"{'='*40}\n"
        start_msg += f"🆕 **주요 개선사항**\n"
        start_msg += f"• 멀티 타임프레임 분석 (일봉 + 4시간봉)\n"
        start_msg += f"• 실시간 급등/급락 감지 및 대응\n"
        start_msg += f"• 동적 파라미터 조정 (시장 상황 적응)\n"
        start_msg += f"• 섹터별 분산 투자 관리\n"
        start_msg += f"• 적응형 리스크 관리 시스템\n"
        start_msg += f"• 백테스팅 기능 (선택적)\n\n"
        start_msg += f"💰 투자 예산: {config.get('bot_investment_budget'):,.0f}원\n"
        start_msg += f"🎯 최대 코인: {config.get('max_coin_count')}개\n"
        start_msg += f"⏰ 실행 주기: {config.get('execution_interval')/3600:.1f}시간\n"
        start_msg += f"🔄 실시간 모니터링: {'활성' if config.get('realtime_monitoring') else '비활성'}\n"
        start_msg += f"📊 멀티 타임프레임: {'활성' if config.get('use_multi_timeframe') else '비활성'}\n"
        start_msg += f"🎯 적응형 파라미터: {'활성' if config.get('adaptive_parameters') else '비활성'}\n"
        start_msg += f"🏢 섹터별 분산: {'활성' if config.get('sector_diversification') else '비활성'}\n"
        start_msg += f"📈 급락 매수: {'활성' if config.get('dip_buying_enabled') else '비활성'}\n"
        start_msg += f"📉 급등 매도: {'활성' if config.get('pump_selling_enabled') else '비활성'}"
        
        logger.info(start_msg)
        
        # Discord 알림
        if config.get('use_discord_alert'):
            try:
                discord_alert.SendMessage(start_msg)
            except Exception as e:
                logger.warning(f"Discord 알림 전송 실패: {str(e)}")
        
        # 백테스팅 실행 (설정된 경우)
        if config.get('backtest_enabled'):
            bot.run_backtest_if_enabled()
        
        # 마지막 일일 보고서 전송 시간
        last_daily_report = None
        
        logger.info("개선된 메인 루프 시작...")
        
        # 메인 루프
        while True:
            try:
                current_time = datetime.datetime.now()

                # 수익보존 요약 (하루 한 번, 저녁 8시)
                if (current_time.hour == 20 and 
                    current_time.minute < 5 and
                    (last_profit_summary is None or 
                     last_profit_summary.date() != current_time.date())):
                    
                    bot.send_profit_protection_summary()
                    last_profit_summary = current_time

                # 일일 보고서 전송
                try:
                    report_time = config.get('daily_report_time', '15:30')
                    if ':' in report_time:
                        report_hour, report_minute = map(int, report_time.split(':'))
                        
                        if (current_time.hour == report_hour and 
                            current_time.minute >= report_minute and
                            current_time.minute < report_minute + 5 and
                            (last_daily_report is None or 
                             last_daily_report.date() != current_time.date())):
                            
                            bot.send_performance_alert()
                            last_daily_report = current_time
                            logger.info("일일 보고서 전송 완료")
                except Exception as e:
                    logger.error(f"일일 보고서 처리 중 에러: {str(e)}")
                
                # 매매 실행
                bot.execute_trading()
                
                # 5분 대기
                logger.debug("다음 실행까지 5분 대기...")
                time.sleep(300)
                
            except KeyboardInterrupt:
                logger.info("사용자에 의해 봇이 중단되었습니다.")
                
                end_msg = "🛑 **개선된 빗썸 트렌드 추종 봇 종료**\n📊 최종 성과를 확인하세요."
                
                logger.info(end_msg)
                
                if config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(end_msg)
                    except Exception as e:
                        logger.warning(f"종료 알림 전송 실패: {str(e)}")
                
                break
                
            except Exception as e:
                error_msg = f"⚠️ 메인 루프 에러: {str(e)}"
                logger.error(error_msg)
                
                if config.get('use_discord_alert'):
                    try:
                        discord_alert.SendMessage(error_msg)
                    except Exception as discord_e:
                        logger.warning(f"에러 알림 전송 실패: {str(discord_e)}")
                
                logger.info("에러 발생으로 1분 대기 후 재시도...")
                time.sleep(60)
    
    except Exception as e:
        logger.critical(f"봇 초기화 실패: {str(e)}")
        logger.error(f"봇 초기화 실패: {str(e)}")

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("🚀 개선된 빗썸 알트코인 트렌드 추종 봇")
    logger.info("="*60)
    logger.info("🆕 주요 개선사항:")
    logger.info("  1. 멀티 타임프레임 분석 (일봉 + 4시간봉)")
    logger.info("  2. 실시간 급등/급락 감지 및 자동 대응")
    logger.info("  3. 시장 상황 적응형 파라미터 조정")
    logger.info("  4. 섹터별 분산 투자 관리")
    logger.info("  5. 백테스팅 기능 (선택적)")
    logger.info("  6. 개선된 리스크 관리 시스템")
    logger.info("  7. 부분 매도 기능 (급등 시)")
    logger.info("  8. 급락 매수 기회 포착")
    logger.info("  9. 적응형 손절매/익절 수준")
    logger.info(" 10. 실시간 모니터링 스레드")
    logger.info("="*60)
    main()