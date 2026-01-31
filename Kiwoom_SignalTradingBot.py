#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
신호 기반 자동매매 봇 (SignalTradingBot_Kiwoom) v3.0
- watchdog 실시간 신호 감지 (0초 지연)
- 멀티스레드 API 호출 최적화
- 미체결 주문 자동 관리
- 중복 주문 방지
"""

from __future__ import annotations
import Kiwoom_API_Helper_KR as KiwoomKR
import discord_alert
import json
import time
from datetime import datetime, timedelta
import os
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

################################### 로깅 처리 ##################################
import logging
from logging.handlers import TimedRotatingFileHandler

log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

def log_namer(default_name):
    base_filename, ext, date = default_name.split(".")
    return f"{base_filename}.{date}.{ext}"

logger = logging.getLogger('SignalTradingBotLogger')
logger.setLevel(logging.INFO)

log_file = os.path.join(log_directory, 'signal_trading_bot.log')
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

################################### 로깅 처리 끝 ##################################

# 키움 API 초기화
try:
    KiwoomAPI = KiwoomKR.Kiwoom_Common(log_level=logging.INFO)
    
    if not KiwoomAPI.LoadConfigData():
        logger.error("❌ 키움 API 설정 로드 실패")
        exit(1)
    
    if not KiwoomAPI.GetAccessToken():
        logger.error("❌ 키움 API 토큰 발급 실패")
        exit(1)
    
    logger.info("✅ 키움 API 초기화 성공")
except Exception as e:
    logger.error(f"❌ 키움 API 초기화 중 오류: {str(e)}")
    exit(1)

################################### 설정 관리 ##################################

class ConfigManager:
    """통합 설정 관리자"""

    def __init__(self, config_file='signal_trading_config.json'):
        self.config_file = config_file
        self.config = self.load_config()

        self.default_config = {
            # ============================================
            # 계좌 및 자산 설정
            # ============================================
            "min_asset_threshold": 400000,      # 최소 자산 40만원 (이하 시 매매 중지)
            "max_positions": 2,                 # 최대 보유 종목 수
            
            # ============================================
            # 매수 설정
            # ============================================
            "buy_signals": ["STRONG_BUY", "CONFIRMED_BUY"],
            "signal_validity_minutes": 10,      # 신호 유효 시간 (분)
            "buy_cutoff_time": "14:50",         # 매수 마감 시간

            # ============================================
            # 매도 설정 (개선: 적극적 수익 보호 + 타이트 트레일링)
            # ============================================
            "target_profit_rate": 0.02,              # 2% 목표 수익
            # "breakeven_protection_rate": 0.008,      # 0.8% 달성 시 본전 보호 (기존 0.02)
            "breakeven_protection_rate": 0.012,      # 🔥 1.2% 달성 시 본전 보호 (비대칭!)
            "commission_rate": 0.004,                # 🔥 [신규] 0.4% 거래비용
            "tight_trailing_threshold": 0.03,        # 3% 달성 시 초타이트 (기존 0.02)
            "tight_trailing_rate": 0.003,            # 🔥 0.3% 초타이트 (기존 0.005)
            "trailing_stop_rate": 0.005,             # 🔥 0.5% 기본 트레일링 (기존 0.01)
            "min_profit_for_trailing": 0.008,        # 0.8% 이상일 때 트레일링 활성화
            "sell_signals": ["SELL", "STRONG_SELL"], # 매도 신호 종류
            "emergency_stop_loss": -0.03,            # -3% 긴급 손절
            
            # ============================================
            # 동적 손절 설정 (ATR 기반)
            # ============================================
            "stop_loss_grace_period_minutes": 10,    # 매수 후 10분 유예
            "extreme_stop_loss": -0.05,              # -5% 극단 손절
            "atr_stop_multiplier": 2.0,              # ATR 배수
            "atr_min_stop_loss": 0.02,               # ATR 최소 손절 2%
            "atr_max_stop_loss": 0.08,               # ATR 최대 손절 8%
            "signal_override_buffer": 0.02,          # 신호 우선 버퍼 2%
            "min_signal_confidence": 0.4,            # 최소 신호 신뢰도 40%
            
            # ============================================
            # 스마트 스케줄링 설정
            # ============================================
            "pending_order_timeout_minutes": 10,     # 미체결 주문 타임아웃
            "check_pending_interval_seconds": 30,    # 미체결 체크 주기
            "check_position_interval_seconds": 60,   # 보유 종목 체크 주기
            "cooldown_hours": 8,                     # 매도 후 재매수 금지 시간
            
            # ============================================
            # 파일 경로 설정
            # ============================================
            "signal_file": "signal_history.json",
            "positions_file": "trading_positions.json",
            "pending_orders_file": "trading_pending_orders.json",
            "cooldowns_file": "trading_cooldowns.json",
            
            # ============================================
            # 알림 설정
            # ============================================
            "use_discord": True,
            "bot_name": "SignalTradingBot_Kiwoom",
            
            # ============================================
            # 성과 추적 설정
            # ============================================
            "performance": {
                # 📌 수동 관리 (입금/출금 시 사용자가 직접 수정!)
                "baseline_asset": 500000,
                "baseline_date": datetime.now().strftime("%Y-%m-%d"),
                "baseline_note": "추가 입금 시 baseline_asset을 수동으로 업데이트하세요",
                
                # ✅ 자동 계산 (봇이 관리)
                "total_realized_profit": 0,
                "total_realized_loss": 0,
                "net_realized_profit": 0,
                
                # 📊 거래 통계
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "canceled_orders": 0,
                "win_rate": 0.0,
                
                # 🏆 최고/최저 기록
                "best_performance_rate": 0.0,
                "best_performance_date": "",
                "worst_performance_rate": 0.0,
                "worst_performance_date": "",
                
                # 📅 일일 기록
                "last_report_date": "",
                "start_date": datetime.now().strftime("%Y-%m-%d")
            }
        }

        self._upgrade_config_if_needed()

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"설정 로드 실패: {e}")
            return {}
    
    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.debug("✅ 설정 저장 완료")
        except Exception as e:
            logger.error(f"설정 저장 실패: {e}")
    
    def _upgrade_config_if_needed(self):
        is_modified = False
        
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
                is_modified = True
        
        if is_modified:
            self.save_config()
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
        self.save_config()
    
    def update_performance(self, metric, value):
        if 'performance' not in self.config:
            self.config['performance'] = self.default_config['performance'].copy()
        
        if isinstance(value, (int, float)):
            self.config['performance'][metric] = self.config['performance'].get(metric, 0) + value
        else:
            self.config['performance'][metric] = value
        
        self.save_config()

config = ConfigManager()
BOT_NAME = config.get("bot_name", "SignalTradingBot_Kiwoom")

logger.info("=" * 60)
logger.info(f"🤖 {config.get('bot_name')} 초기화 v3.0 (watchdog 실시간)")
# logger.info(f"💰 초기 자산: {config.get('initial_budget', 500000):,}원")  # ✅ 수정!
logger.info(f"⚠️ 최소 자산: {config.get('min_asset_threshold', 400000):,}원 (이하 시 매매 중지)")  # ✅ 추가!
logger.info(f"📊 최대 종목: {config.get('max_positions')}개")
logger.info("⚡ watchdog: 파일 변경 즉시 감지 (0초 지연)")
logger.info(f"🔄 미체결 체크: {config.get('check_pending_interval_seconds')}초마다")
logger.info(f"📈 트레일링 체크: {config.get('check_position_interval_seconds')}초마다")
logger.info("=" * 60)

################################### 신호 기반 자동매매 봇 v3.0 ##################################

# ============================================
# 🔥 1. API 타임아웃 래퍼 함수 추가 (파일 상단에 추가)
# ============================================

class TimeoutError(Exception):
    """타임아웃 예외"""
    pass

def call_with_timeout(func, timeout=10, *args, **kwargs):
    """
    함수를 타임아웃과 함께 실행
    
    Args:
        func: 실행할 함수
        timeout: 타임아웃 시간(초)
        *args, **kwargs: 함수 인자
    
    Returns:
        함수 실행 결과 또는 None (타임아웃 시)
    
    Raises:
        TimeoutError: 타임아웃 발생 시
    """
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        raise TimeoutError(f"{func.__name__} 타임아웃 ({timeout}초 초과)")
    
    if exception[0]:
        raise exception[0]
    
    return result[0]


class SignalTradingBot:
    """신호 기반 자동매매 봇 (watchdog + 멀티스레드)"""
    
    def __init__(self):
        # 🔥 파일 경로 먼저 설정 (load 함수들이 이걸 사용함)
        self.signal_file = config.get("signal_file", "signal_history.json")
        self.positions_file = config.get("positions_file", "trading_positions.json")
        self.pending_orders_file = config.get("pending_orders_file", "trading_pending_orders.json")
        self.cooldowns_file = config.get("cooldowns_file", "trading_cooldowns.json")

        self.positions: dict = self.load_positions()
        self.pending_orders: dict = self.load_pending_orders()
        self.cooldowns: dict = self.load_cooldowns()
        
        # 🔥 스레드 제어
        self.running: bool = True
        self.lock: threading.Lock = threading.Lock()  # 데이터 동시 접근 방지
        
        logger.info(f"봇 초기화 완료")
        logger.info(f"현재 보유 종목: {len(self.positions)}개")
        logger.info(f"미체결 주문: {len(self.pending_orders)}개")
        logger.info(f"쿨다운 중인 종목: {len(self.cooldowns)}개")

    def load_positions(self) -> dict:
            """보유 종목 로드"""
            try:
                if os.path.exists(self.positions_file):
                    with open(self.positions_file, 'r', encoding='utf-8') as f:
                        positions = json.load(f)
                        
                        # 🔥 기존 포지션에 새 필드 추가 (하위 호환성)
                        for stock_code, position in positions.items():
                            if 'breakeven_protected' not in position:
                                position['breakeven_protected'] = False
                            if 'tight_trailing_active' not in position:
                                position['tight_trailing_active'] = False
                        
                        return positions
                return {}
            except Exception as e:
                logger.error(f"포지션 로드 실패: {e}")
                return {}

    def process_new_signals(self):
        """
        신호 파일 변경 시 실행되는 핵심 함수
        watchdog에서 호출됨
        
        처리 흐름:
        1. 장중 시간 체크
        2. 최신 신호 읽기
        3. 유효 신호 필터링
        4. STRONG_BUY/CONFIRMED_BUY 신호 매수 실행
        """
        try:
            logger.info("=" * 80)
            logger.info("🔔 신호 처리 시작!")
            logger.info("=" * 80)
            
            # 1️⃣ 장중 시간 체크
            if not self.is_trading_time():
                logger.info("⏰ 장 시간 외 - 신호 처리 스킵")
                return
            
            # 2️⃣ 최신 신호 읽기
            logger.info("📖 신호 파일 읽는 중...")
            all_signals = self.read_latest_signals()
            
            if not all_signals:
                logger.info("📭 신호 없음")
                return
            
            # 3️⃣ 유효한 신호만 필터링
            logger.info("🔍 유효 신호 필터링 중...")
            valid_signals = self.filter_valid_signals(all_signals)
            
            if not valid_signals:
                logger.info("❌ 유효한 신호 없음")
                return
            
            # 4️⃣ 매수 대상 신호만 선택 (STRONG_BUY, CONFIRMED_BUY)
            buy_signal_types = config.get("buy_signals", ["STRONG_BUY", "CONFIRMED_BUY"])
            buy_signals = [
                sig for sig in valid_signals 
                if sig.get('signal') in buy_signal_types
            ]
            
            logger.info(f"🎯 매수 대상 신호: {len(buy_signals)}건 ({', '.join(buy_signal_types)})")
            
            if not buy_signals:
                logger.info("💤 매수 대상 신호 없음 (STRONG_BUY/CONFIRMED_BUY만 처리)")
                return
            
            # 5️⃣ 각 매수 신호 처리
            processed_count = 0
            
            for signal in buy_signals:
                stock_code = signal.get('stock_code', '')
                stock_name = signal.get('stock_name', '')
                signal_type = signal.get('signal', '')
                score = signal.get('score', 0)
                confidence = signal.get('confidence', 0)
                timestamp = signal.get('timestamp', '')
                
                logger.info("")
                logger.info("─" * 80)
                logger.info(f"🔍 [{stock_name}] {signal_type} 신호 처리 시작")
                logger.info(f"   📊 점수: {score:.1f}/100, 신뢰도: {confidence*100:.0f}%")
                logger.info(f"   ⏰ 발생시각: {timestamp}")
                logger.info("─" * 80)
                
                # 매수 가능 여부 체크
                # can_buy, reason = self.can_buy_stock(signal)
                can_buy, reason = self.can_buy(stock_code)
                
                if not can_buy:
                    logger.info(f"❌ 매수 불가: {reason}")
                    logger.info("─" * 80)
                    continue
                
                # ✅ 매수 실행!
                logger.info(f"✅ 매수 가능! 매수 실행 중...")
                
                success = self.execute_buy(signal)
                
                if success:
                    processed_count += 1
                    logger.info(f"🎉 매수 완료!")
                else:
                    logger.warning(f"⚠️ 매수 실패")
                
                logger.info("─" * 80)
                
                # 너무 빠른 연속 주문 방지
                time.sleep(1)
            
            # 6️⃣ 처리 결과 요약
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"✅ 신호 처리 완료!")
            logger.info(f"📊 총 신호: {len(all_signals)}건")
            logger.info(f"✔️ 유효 신호: {len(valid_signals)}건")
            logger.info(f"🎯 매수 대상: {len(buy_signals)}건")
            logger.info(f"💰 실제 매수: {processed_count}건")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"❌ 신호 처리 중 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def save_positions(self):
        try:
            with self.lock:
                positions_file = config.get("positions_file", "trading_positions.json")
                with open(positions_file, 'w', encoding='utf-8') as f:
                    json.dump(self.positions, f, ensure_ascii=False, indent=2)
                logger.debug("✅ 포지션 저장 완료")
        except Exception as e:
            logger.error(f"포지션 저장 실패: {e}")
    
    def load_pending_orders(self) -> dict:
        try:
            pending_file = config.get("pending_orders_file", "trading_pending_orders.json")
            if os.path.exists(pending_file):
                with open(pending_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"미체결 주문 로드 실패: {e}")
            return {}
    
    def save_pending_orders(self):
        try:
            with self.lock:
                pending_file = config.get("pending_orders_file", "trading_pending_orders.json")
                with open(pending_file, 'w', encoding='utf-8') as f:
                    json.dump(self.pending_orders, f, ensure_ascii=False, indent=2)
                logger.debug("✅ 미체결 주문 저장 완료")
        except Exception as e:
            logger.error(f"미체결 주문 저장 실패: {e}")
    
    def load_cooldowns(self) -> dict:
        try:
            cooldowns_file = config.get("cooldowns_file", "trading_cooldowns.json")
            if os.path.exists(cooldowns_file):
                with open(cooldowns_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"쿨다운 로드 실패: {e}")
            return {}
    
    def save_cooldowns(self):
        try:
            with self.lock:
                cooldowns_file = config.get("cooldowns_file", "trading_cooldowns.json")
                with open(cooldowns_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cooldowns, f, ensure_ascii=False, indent=2)
                logger.debug("✅ 쿨다운 저장 완료")
        except Exception as e:
            logger.error(f"쿨다운 저장 실패: {e}")
    
    def is_trading_time(self):
        """장중 시간 체크"""
        now = datetime.now()
        
        if now.weekday() >= 5:
            return False
        
        current_time = now.time()
        market_open = datetime.strptime("09:00", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        return market_open <= current_time <= market_close
    
    def read_latest_signals(self):
        try:
            if not os.path.exists(self.signal_file):
                logger.warning(f"신호 파일 없음: {self.signal_file}")
                return []
            
            with open(self.signal_file, 'r', encoding='utf-8') as f:
                signals = json.load(f)
            
            signals_sorted = sorted(
                signals,
                key=lambda x: x.get('timestamp', ''),
                reverse=True
            )
            
            logger.info(f"📊 신호 파일 읽기 성공: {len(signals_sorted)}건")
            return signals_sorted
            
        except Exception as e:
            logger.error(f"신호 읽기 실패: {e}")
            return []
    
    def filter_valid_signals(self, signals):
        try:
            validity_minutes = config.get("signal_validity_minutes", 10)
            now = datetime.now()
            
            valid_signals = []
            
            for signal in signals:
                signal_time_str = signal.get('timestamp', '')
                try:
                    signal_time = datetime.strptime(signal_time_str, "%Y-%m-%d %H:%M:%S")
                except:
                    continue
                
                elapsed_minutes = (now - signal_time).total_seconds() / 60
                
                if elapsed_minutes > validity_minutes:
                    continue
                
                confidence = signal.get('confidence', 0)
                if confidence < 0.4:
                    continue
                
                valid_signals.append(signal)
            
            logger.info(f"✅ 유효한 신호: {len(valid_signals)}건 (최근 {validity_minutes}분 이내)")
            return valid_signals
            
        except Exception as e:
            logger.error(f"신호 필터링 실패: {e}")
            return []
    
    def is_in_cooldown(self, stock_code):
        try:
            with self.lock:
                if stock_code not in self.cooldowns:
                    return False
                
                cooldown_data = self.cooldowns[stock_code]
                cooldown_until_str = cooldown_data.get('cooldown_until', '')
                
                try:
                    cooldown_until = datetime.strptime(cooldown_until_str, "%Y-%m-%d %H:%M:%S")
                except:
                    return False
                
                now = datetime.now()
                
                if now < cooldown_until:
                    remaining = (cooldown_until - now).total_seconds() / 3600
                    logger.debug(f"⏰ {stock_code} 쿨다운 중 (남은 시간: {remaining:.1f}시간)")
                    return True
                else:
                    del self.cooldowns[stock_code]
                    self.save_cooldowns()
                    logger.info(f"✅ {stock_code} 쿨다운 해제")
                    return False
            
        except Exception as e:
            logger.error(f"쿨다운 체크 실패: {e}")
            return False

    def can_buy(self, stock_code):
        """
        매수 가능 여부 체크 (상세 로깅 추가)
        
        Returns:
            tuple: (bool, str) - (매수가능여부, 사유)
        """
        try:
            logger.info(f"🔍 매수 가능 여부 체크 시작: {stock_code}")
            # 🔥 0단계: 매수 시간 제한 (새로 추가)
            now = datetime.now()
            cutoff_str = config.get("buy_cutoff_time", "14:50")
            cutoff_time = datetime.strptime(cutoff_str, "%H:%M").time()
            
            if now.time() >= cutoff_time:
                return False, f"매수 시간 마감 ({now.strftime('%H:%M')} >= {cutoff_str})"

            # 1️⃣ 보유 중 체크
            logger.debug("   → 1단계: 보유 여부 확인...")
            with self.lock:
                if stock_code in self.positions:
                    logger.debug(f"   ❌ 이미 보유 중")
                    return False, "이미 보유 중"
            logger.debug("   ✅ 미보유 확인")
            
            # 2️⃣ 미체결 주문 체크
            logger.debug("   → 2단계: 미체결 주문 확인...")
            with self.lock:
                if stock_code in self.pending_orders:
                    logger.debug(f"   ❌ 미체결 주문 존재")
                    return False, "미체결 주문 있음"
            logger.debug("   ✅ 미체결 주문 없음")
            
            # 3️⃣ 쿨다운 체크
            logger.debug("   → 3단계: 쿨다운 확인...")
            with self.lock:
                if stock_code in self.cooldowns:
                    cooldown_until = self.cooldowns[stock_code].get('cooldown_until', '')
                    
                    if cooldown_until:
                        try:
                            cooldown_dt = datetime.strptime(cooldown_until, "%Y-%m-%d %H:%M:%S")
                            now = datetime.now()
                            
                            if now < cooldown_dt:
                                remaining = (cooldown_dt - now).total_seconds() / 3600
                                logger.debug(f"   ❌ 쿨다운 중 (남은 시간: {remaining:.1f}시간)")
                                return False, f"쿨다운 중 ({remaining:.1f}시간 남음)"
                            else:
                                # 쿨다운 만료 - 삭제
                                logger.debug(f"   ✅ 쿨다운 만료 - 삭제")
                                del self.cooldowns[stock_code]
                                self.save_cooldowns()
                        except Exception as e:
                            logger.error(f"   ⚠️ 쿨다운 파싱 오류: {e}")
            logger.debug("   ✅ 쿨다운 없음")
            
            # 4️⃣ 총 자산 계산 (타임아웃 적용)
            logger.debug("   → 4단계: 자산 계산...")
            
            try:
                asset_info = call_with_timeout(
                    self.calculate_total_asset,
                    timeout=30  # 전체 자산 계산은 30초 타임아웃
                )
            except TimeoutError as e:
                logger.error(f"   ❌ 자산 계산 타임아웃: {e}")
                return False, "자산 조회 타임아웃"
            
            if not asset_info:
                logger.error(f"   ❌ 자산 조회 실패")
                return False, "자산 조회 실패"
            
            total_asset = asset_info['total_asset']
            logger.debug(f"   ✅ 자산 조회 완료: {total_asset:,}원")
            
            # 5️⃣ 최소 자산 체크
            logger.debug("   → 5단계: 최소 자산 확인...")
            min_asset = config.get('min_asset_threshold', 400000)
            
            if total_asset < min_asset:
                logger.error(f"   ❌ 최소 자산 미달")
                logger.error(f"      현재 자산: {total_asset:,}원")
                logger.error(f"      최소 기준: {min_asset:,}원")
                
                if config.get("use_discord", True):
                    msg = f"🚨 **긴급! 최소 자산 미달**\n"
                    msg += f"현재 자산: {total_asset:,}원\n"
                    msg += f"최소 기준: {min_asset:,}원\n"
                    msg += f"차액: {total_asset - min_asset:,}원\n"
                    msg += f"⛔ 모든 매수 중지!"
                    discord_alert.SendMessage(msg)
                
                return False, f"최소 자산 미달 ({total_asset:,}원 < {min_asset:,}원)"
            logger.debug(f"   ✅ 최소 자산 충족")
            
            # 6️⃣ 최대 종목 수 체크
            logger.debug("   → 6단계: 최대 종목 수 확인...")
            max_positions = config.get("max_positions", 3)
            
            with self.lock:
                total_stocks = len(self.positions) + len(self.pending_orders)
            
            if total_stocks >= max_positions:
                logger.debug(f"   ❌ 최대 종목 수 도달 ({total_stocks}/{max_positions})")
                return False, f"최대 종목 수 도달 ({total_stocks}/{max_positions})"
            logger.debug(f"   ✅ 종목 수 여유 있음 ({total_stocks}/{max_positions})")
            
            logger.info("✅ 매수 가능 여부 체크 완료: 매수 가능!")
            return True, "매수 가능"
            
        except Exception as e:
            logger.error(f"❌ 매수 가능 여부 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)

    def adjust_price_to_tick(self, price, is_buy=True):
            """
            호가 단위에 맞게 가격 조정
            
            Args:
                price: 원본 가격
                is_buy: True면 매수(내림), False면 매도(올림)
            
            Returns:
                int: 조정된 가격
            """
            try:
                # 한국 주식 호가 단위
                if price < 1000:
                    tick = 1
                elif price < 5000:
                    tick = 5
                elif price < 10000:
                    tick = 10
                elif price < 50000:
                    tick = 50
                elif price < 100000:
                    tick = 100
                elif price < 500000:
                    tick = 500
                else:
                    tick = 1000
                
                # 호가 단위로 나눈 몫
                quotient = price // tick
                remainder = price % tick
                
                if remainder == 0:
                    # 이미 호가 단위에 맞음
                    adjusted_price = price
                elif is_buy:
                    # 매수: 내림 (유리하게)
                    adjusted_price = quotient * tick
                else:
                    # 매도: 올림 (유리하게)
                    adjusted_price = (quotient + 1) * tick
                
                logger.debug(f"호가 조정: {price:,}원 → {adjusted_price:,}원 (단위: {tick}원, {'매수' if is_buy else '매도'})")
                
                return adjusted_price
                
            except Exception as e:
                logger.error(f"호가 단위 조정 실패: {e}")
                return price

    def execute_buy(self, signal):
        """매수 실행 (개선된 버전)"""
        try:
            stock_code = signal.get('stock_code', '')
            stock_name = signal.get('stock_name', '')
            
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"🚀 {stock_name}({stock_code}) 매수 시도 시작")
            logger.info(f"   신호: {signal.get('signal')} (점수: {signal.get('score'):.1f})")
            logger.info(f"   시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)

            # 🔥 매수 가능 여부 체크 (타임아웃 적용)
            logger.info("📋 1단계: 매수 가능 여부 체크")
            
            try:
                can_buy, reason = call_with_timeout(
                    self.can_buy,
                    timeout=40,  # can_buy 전체는 40초 타임아웃
                    stock_code=stock_code
                )
            except TimeoutError as e:
                logger.error(f"❌ 매수 가능 여부 체크 타임아웃: {e}")
                logger.error(f"   API 응답 지연 - 이번 매수 건너뜀")
                return False

            if not can_buy:
                logger.warning(f"❌ 매수 불가: {reason}")
                logger.warning(f"   매수 프로세스 중단")
                return False
            
            logger.info(f"✅ 매수 가능 확인: {reason}")
            
            # 🔥🔥🔥 1️⃣ 총 자산 계산
            asset_info = self.calculate_total_asset()
            if not asset_info:
                logger.error(f"❌ 자산 조회 실패")
                return False
            
            total_asset = asset_info['total_asset']
            orderable_amt = asset_info['orderable_amt']
            holding_value = asset_info['holding_value']
            pending_value = asset_info['pending_value']
            
            logger.info(f"💰 자산 현황:")
            logger.info(f"   총 자산: {total_asset:,}원")
            logger.info(f"   현금: {orderable_amt:,}원")
            logger.info(f"   보유주식: {holding_value:,}원")
            logger.info(f"   미체결: {pending_value:,}원")
            
            # 🔥🔥🔥 2️⃣ 남은 슬롯 계산
            max_positions = config.get("max_positions", 3)
            current_stocks = len(self.positions) + len(self.pending_orders)
            remaining_slots = max_positions - current_stocks
            
            logger.info(f"📊 포지션:")
            logger.info(f"   현재: {current_stocks}종목")
            logger.info(f"   남은 슬롯: {remaining_slots}개")
            
            # 🔥🔥🔥 3️⃣ 남은 자산 계산
            used_asset = holding_value + pending_value
            remaining_asset = total_asset - used_asset
            
            logger.info(f"💵 사용 가능 자산:")
            logger.info(f"   전체: {total_asset:,}원")
            logger.info(f"   사용 중: {used_asset:,}원")
            logger.info(f"   남은 금액: {remaining_asset:,}원")
            
            # 🔥🔥🔥 4️⃣ 종목당 예산 계산 (남은 자산 균등배분)
            if remaining_slots > 0:
                budget_per_stock = remaining_asset / remaining_slots
            else:
                logger.warning(f"❌ 남은 슬롯 없음")
                return False
            
            logger.info(f"🎯 이번 매수 예산: {budget_per_stock:,.0f}원")
            logger.info(f"   ({remaining_asset:,}원 ÷ {remaining_slots}개)")
            
            # 최소 매수 금액 체크
            if budget_per_stock < 10000:
                logger.warning(f"❌ 매수 금액 부족 (최소 1만원 필요, 현재: {budget_per_stock:,.0f}원)")
                return False
            
            # 실제 주문가능금액 체크
            if budget_per_stock > orderable_amt:
                logger.warning(f"⚠️ 예산 조정: {budget_per_stock:,.0f}원 → {orderable_amt:,}원 (현금 부족)")
                budget_per_stock = orderable_amt
            
            # 현재가 조회
            stock_info = KiwoomAPI.GetStockInfo(stock_code)
            if not stock_info:
                logger.error(f"❌ 현재가 조회 실패")
                return False
            
            current_price = stock_info.get('CurrentPrice', 0)
            
            # 🔥 호가 단위 적용 (매수: 내림)
            adjusted_price = self.adjust_price_to_tick(current_price, is_buy=True)
            
            # 🔥 5️⃣ 매수 수량 계산
            buy_quantity = int(budget_per_stock / adjusted_price)
            
            if buy_quantity < 1:
                logger.warning(f"❌ 매수 수량 부족 (가격: {adjusted_price:,}원, 예산: {budget_per_stock:,.0f}원)")
                return False
            
            # 실제 투자 금액
            actual_investment = adjusted_price * buy_quantity
            
            logger.info(f"💰 매수 주문:")
            logger.info(f"   가격: {adjusted_price:,}원 × {buy_quantity}주")
            logger.info(f"   투자금: {actual_investment:,}원")
            if adjusted_price != current_price:
                logger.info(f"   (원래가: {current_price:,}원 → 호가 조정: {adjusted_price:,}원)")
            
            # 조정된 가격으로 주문
            order_result = KiwoomAPI.MakeBuyLimitOrder(stock_code, buy_quantity, adjusted_price)
            
            if order_result.get('success', False):
                order_no = order_result.get('order_no', '')
                
                with self.lock:
                    self.pending_orders[stock_code] = {
                        'stock_name': stock_name,
                        'order_no': order_no,
                        'order_type': 'buy',
                        'order_price': adjusted_price,
                        'order_quantity': buy_quantity,
                        'order_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'pending',
                        'retry_count': 0,
                        'signal_score': signal.get('score', 0),
                        'signal_confidence': signal.get('confidence', 0)
                    }
                
                self.save_pending_orders()
                
                # 매수 후 남은 슬롯
                new_remaining_slots = remaining_slots - 1
                
                msg = f"🚀 **매수 주문 완료!**\n"
                msg += f"종목: {stock_name} ({stock_code})\n"
                msg += f"주문번호: {order_no}\n"
                msg += f"가격: {adjusted_price:,}원 × {buy_quantity}주\n"
                msg += f"투자금: {actual_investment:,}원\n"
                msg += f"\n💰 **자산 현황**:\n"
                msg += f"총 자산: {total_asset:,}원\n"
                msg += f"사용 가능: {remaining_asset:,}원\n"
                msg += f"남은 슬롯: {new_remaining_slots}개\n"
                msg += f"\n📊 신호: {signal.get('signal')} (점수: {signal.get('score'):.1f})\n"
                msg += f"⏰ 5분 내 미체결 시 자동 취소"
                
                logger.info(msg)
                
                if config.get("use_discord", True):
                    discord_alert.SendMessage(msg)
                
                return True
            else:
                error_msg = order_result.get('msg', '알 수 없는 오류')
                logger.error(f"❌ 매수 주문 실패: {error_msg}")
                return False
            
        except Exception as e:
            logger.error(f"매수 실행 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def check_pending_orders(self):
        """
        미체결 주문 체크 (매수 + 매도)
        - 체결 확인: 실제 체결가(FilledPrice) 사용
        - 재시도: 최대 3회
        - 시장가 전환: 3회 실패 후
        """
        try:
            with self.lock:
                if not self.pending_orders:
                    return
                
                logger.info("=" * 60)
                logger.info(f"📋 미체결 주문 체크: {len(self.pending_orders)}건")
                logger.info("=" * 60)
            
            now = datetime.now()
            timeout_minutes = config.get("pending_order_timeout_minutes", 5)
            max_retry = 3
            
            for stock_code in list(self.pending_orders.keys()):
                with self.lock:
                    if stock_code not in self.pending_orders:
                        continue
                    pending = self.pending_orders[stock_code].copy()
                
                order_no = pending.get('order_no', '')
                stock_name = pending.get('stock_name', '')
                order_type = pending.get('order_type', 'buy')
                
                # 🔥 1단계: 미체결 목록 확인
                unfilled_orders = KiwoomAPI.GetUnfilledOrders(stock_code)
                
                is_still_pending = False
                for order in unfilled_orders:
                    if order.get('OrderNo') == order_no:
                        is_still_pending = True
                        break
                
                if not is_still_pending:
                    # 🔥 2단계: 체결 목록 확인
                    filled_orders = KiwoomAPI.GetFilledOrders(stock_code)
                    
                    is_filled = False
                    for order in filled_orders:
                        if order.get('OrderNo') == order_no:
                            is_filled = True
                            break
                    
                    if is_filled:
                        # ✅ 체결 완료!
                        logger.info(f"✅ {stock_name} {order_type.upper()} 주문 체결 확인")
                        
                        # 🔥 실제 체결가 가져오기
                        filled_price = None
                        filled_qty = None
                        commission = 0
                        tax = 0
                        
                        for order in filled_orders:
                            if order.get('OrderNo') == order_no:
                                filled_price = order.get('FilledPrice', 0)
                                filled_qty = order.get('FilledQty', 0)
                                commission = order.get('Commission', 0)
                                tax = order.get('Tax', 0)
                                break
                        
                        # 체결가 검증
                        if not filled_price or filled_price <= 0:
                            logger.warning(f"⚠️ {stock_name} 체결가 조회 실패, 주문가 사용")
                            filled_price = pending['order_price']
                            filled_qty = pending['order_quantity']
                        
                        logger.info(f"✅ {stock_name} {order_type.upper()} 체결 완료!")
                        logger.info(f"   주문가: {pending['order_price']:,}원 → 체결가: {filled_price:,}원")
                        if commission > 0 or tax > 0:
                            logger.info(f"   수수료: {commission:,}원, 세금: {tax:,}원")
                        
                        with self.lock:
                            if order_type == 'buy':
                                # 매수 체결: positions에 추가
                                self.positions[stock_code] = {
                                    'stock_name': stock_name,
                                    'entry_price': filled_price,  # ✅ 실제 체결가 사용
                                    'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'quantity': filled_qty,       # ✅ 실제 체결수량
                                    'highest_price': filled_price,
                                    'trailing_stop_price': filled_price * (1 - config.get("trailing_stop_rate", 0.01)),
                                    'target_profit_price': filled_price * (1 + config.get("target_profit_rate", 0.03)),
                                    'signal_score': pending.get('signal_score', 0),
                                    'signal_confidence': pending.get('signal_confidence', 0),
                                    'breakeven_protected': False,
                                    'tight_trailing_active': False,
                                    # 🔥 추가 정보 기록
                                    'order_price': pending['order_price'],  # 참고용
                                    'entry_commission': commission
                                }
                                
                                price_diff = filled_price - pending['order_price']
                                msg = f"✅ **매수 체결!**\n"
                                msg += f"종목: {stock_name} ({stock_code})\n"
                                msg += f"체결가: {filled_price:,}원 × {filled_qty}주\n"
                                if price_diff != 0:
                                    emoji = "💰" if price_diff < 0 else "📊"
                                    msg += f"{emoji} 주문가: {pending['order_price']:,}원 ({price_diff:+,}원)\n"
                                msg += f"투자금: {filled_price * filled_qty:,}원\n"
                                if commission > 0:
                                    msg += f"수수료: {commission:,}원\n"
                                msg += f"목표가: {self.positions[stock_code]['target_profit_price']:,.0f}원 (+3%)\n"
                                msg += f"트레일링: {self.positions[stock_code]['trailing_stop_price']:,.0f}원 (-1%)"
                                
                            else:  # sell
                                # 🔥 매도 체결: 실제 체결가로 수익 재계산
                                if stock_code in self.positions:
                                    entry_price = self.positions[stock_code]['entry_price']
                                    entry_commission = self.positions[stock_code].get('entry_commission', 0)
                                    
                                    # 실제 수익 계산 (매수 수수료 + 매도 수수료 + 세금)
                                    profit = (filled_price - entry_price) * filled_qty - entry_commission - commission - tax
                                    profit_rate = (filled_price - entry_price) / entry_price
                                    
                                    del self.positions[stock_code]
                                else:
                                    # positions에 없으면 pending_orders에서 가져옴
                                    entry_price = pending.get('entry_price', 0)
                                    profit = (filled_price - entry_price) * filled_qty - commission - tax
                                    profit_rate = (filled_price - entry_price) / entry_price if entry_price > 0 else 0
                                    entry_commission = 0
                                
                                cooldown_hours = config.get("cooldown_hours", 8)
                                cooldown_until = datetime.now() + timedelta(hours=cooldown_hours)
                                
                                self.cooldowns[stock_code] = {
                                    'stock_name': stock_name,
                                    'sell_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'cooldown_until': cooldown_until.strftime("%Y-%m-%d %H:%M:%S"),
                                    'sell_reason': pending.get('sell_reason', ''),
                                    'entry_price': entry_price,
                                    'sell_price': filled_price,
                                    'quantity': filled_qty,
                                    'profit': profit,
                                    'profit_rate': profit_rate,
                                    'commission': commission,
                                    'entry_commission': entry_commission,
                                    'tax': tax
                                }
                                
                                # 🔥🔥🔥 성과 기록 업데이트 (여기가 핵심!)
                                config.update_performance('total_trades', 1)
                                
                                if profit > 0:
                                    config.update_performance('total_realized_profit', profit)
                                    config.update_performance('winning_trades', 1)
                                else:
                                    config.update_performance('total_realized_loss', abs(profit))
                                    config.update_performance('losing_trades', 1)
                                
                                # 순 실현 수익 계산
                                perf = config.get('performance', {})
                                total_profit = perf.get('total_realized_profit', 0)
                                total_loss = perf.get('total_realized_loss', 0)
                                net_profit = total_profit - total_loss
                                config.set('performance.net_realized_profit', net_profit)
                                
                                # 승률 계산
                                total_trades = perf.get('total_trades', 0)
                                winning_trades = perf.get('winning_trades', 0)
                                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                                config.set('performance.win_rate', win_rate)
                                
                                price_diff = filled_price - pending['order_price']
                                emoji = "🎉" if profit > 0 else "😢"
                                msg = f"{emoji} **매도 체결!**\n"
                                msg += f"종목: {stock_name} ({stock_code})\n"
                                msg += f"주문번호: {order_no}\n"
                                msg += f"체결가: {filled_price:,}원 × {filled_qty}주\n"
                                if price_diff != 0:
                                    emoji2 = "💰" if price_diff > 0 else "📊"
                                    msg += f"{emoji2} 주문가: {pending['order_price']:,}원 ({price_diff:+,}원)\n"
                                msg += f"실현 수익: {profit:+,}원 ({profit_rate*100:+.2f}%)\n"
                                msg += f"사유: {pending.get('sell_reason', '')}\n"
                                msg += f"💰 누적 순수익: {net_profit:+,}원\n"
                                msg += f"📊 승률: {win_rate:.1f}% ({winning_trades}/{total_trades})"
                            
                            del self.pending_orders[stock_code]
                        
                        self.save_positions()
                        self.save_cooldowns()
                        self.save_pending_orders()
                        
                        logger.info(msg)
                        
                        if config.get("use_discord", True):
                            discord_alert.SendMessage(msg)
                        
                        continue
                    else:
                        # ❓ 미체결도 체결도 아님 (API 지연 가능성)
                        logger.debug(f"🤔 {stock_name} 주문 상태 불명확 - 다음 체크 대기")
                        continue
                
                # 🔥 3단계: 타임아웃 체크 (미체결 상태)
                order_time_str = pending.get('order_time', '')
                try:
                    order_time = datetime.strptime(order_time_str, "%Y-%m-%d %H:%M:%S")
                except:
                    continue
                
                elapsed_minutes = (now - order_time).total_seconds() / 60
                
                if elapsed_minutes > timeout_minutes:
                    retry_count = pending.get('retry_count', 0)
                    
                    logger.warning(f"⚠️ {stock_name} 미체결 타임아웃 ({elapsed_minutes:.1f}분)")
                    
                    if retry_count >= max_retry:
                        logger.error(f"❌ {stock_name} 최대 재시도 초과 - 주문 취소")
                        
                        cancel_result = KiwoomAPI.CancelOrder(order_no, stock_code)
                        
                        with self.lock:
                            if stock_code in self.pending_orders:
                                del self.pending_orders[stock_code]
                        
                        self.save_pending_orders()
                        
                        config.update_performance('canceled_orders', 1)
                        
                        msg = f"❌ **주문 취소**\n"
                        msg += f"종목: {stock_name} ({stock_code})\n"
                        msg += f"사유: 미체결 타임아웃 (재시도 {retry_count}회)\n"
                        msg += f"주문가: {pending['order_price']:,}원"
                        
                        logger.warning(msg)
                        
                        if config.get("use_discord", True):
                            discord_alert.SendMessage(msg)
                        
                        continue
                    
                    # 재주문 시도
                    logger.info(f"🔄 {stock_name} 재주문 시도 ({retry_count + 1}/{max_retry})")
                    
                    cancel_result = KiwoomAPI.CancelOrder(order_no, stock_code)
                    time.sleep(1)
                    
                    stock_info = KiwoomAPI.GetStockInfo(stock_code)
                    if not stock_info:
                        logger.error(f"❌ 현재가 조회 실패 - 재시도 중단")
                        with self.lock:
                            if stock_code in self.pending_orders:
                                del self.pending_orders[stock_code]
                        self.save_pending_orders()
                        continue
                    
                    current_price = stock_info.get('CurrentPrice', 0)
                    adjusted_price = self.adjust_price_to_tick(current_price, is_buy=(order_type=='buy'))
                    
                    quantity = pending['order_quantity']
                    
                    # 재주문
                    if order_type == 'buy':
                        retry_result = KiwoomAPI.MakeBuyLimitOrder(stock_code, quantity, adjusted_price)
                    else:
                        retry_result = KiwoomAPI.MakeSellLimitOrder(stock_code, quantity, adjusted_price)
                    
                    if retry_result.get('success', False):
                        new_order_no = retry_result.get('order_no', '')
                        
                        with self.lock:
                            self.pending_orders[stock_code]['order_no'] = new_order_no
                            self.pending_orders[stock_code]['order_price'] = adjusted_price
                            self.pending_orders[stock_code]['order_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            self.pending_orders[stock_code]['retry_count'] = retry_count + 1
                            
                            # 매도인 경우 예상 수익 재계산
                            if order_type == 'sell':
                                entry_price = pending['entry_price']
                                profit = (adjusted_price - entry_price) * quantity
                                profit_rate = (adjusted_price - entry_price) / entry_price if entry_price > 0 else 0
                                self.pending_orders[stock_code]['expected_profit'] = profit
                                self.pending_orders[stock_code]['expected_profit_rate'] = profit_rate
                        
                        self.save_pending_orders()
                        
                        logger.info(f"✅ {stock_name} 재주문 완료 (새 주문번호: {new_order_no})")
                    else:
                        logger.error(f"❌ {stock_name} 재주문 실패")
            
        except Exception as e:
            logger.error(f"미체결 주문 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def update_trailing_stop(self, stock_code):
        """
        트레일링 스탑 업데이트 (완전 개선: 적극적 수익 보호)
        
        🔥🔥🔥 핵심 개선 사항:
        1. 본전 보호 시 수수료 반영 (진짜 본전)
        2. return 제거 → 소수익도 보호
        3. 0.5% 기본 트레일링 (2배 촘촘)
        4. 3% 달성 시 0.3% 초타이트
        
        3단계 시스템:
        - 1% 달성: 본전 보호 (수수료 포함)
        - 1~3% 구간: 0.5% 트레일링
        - 3% 이상: 0.3% 초타이트 트레일링
        """
        try:
            with self.lock:
                if stock_code not in self.positions:
                    return
                position = self.positions[stock_code].copy()
            
            stock_info = KiwoomAPI.GetStockInfo(stock_code)
            if not stock_info:
                return
            
            current_price = stock_info.get('CurrentPrice', 0)
            entry_price = position.get('entry_price', 0)
            highest_price = position.get('highest_price', 0)
            
            # 현재 수익률 계산
            profit_rate = (current_price - entry_price) / entry_price
            
            # 최고가 갱신 체크
            if current_price > highest_price:
                with self.lock:
                    self.positions[stock_code]['highest_price'] = current_price
                    highest_price = current_price
                
                logger.debug(f"📈 {stock_code} 최고가 갱신: {current_price:,}원 (수익률: {profit_rate*100:+.2f}%)")
            
            # 🔥🔥🔥 조건부 트레일링 활성화 체크
            min_profit_for_trailing = config.get("min_profit_for_trailing", 0.01)
            
            if profit_rate < min_profit_for_trailing:
                logger.debug(f"  ⏸️ {stock_code} 트레일링 대기: 수익률 {profit_rate*100:+.2f}% < {min_profit_for_trailing*100:.0f}%")
                logger.debug(f"  💡 ATR 손절만 사용 (소폭 상승에 민감하지 않게)")
                return
            
            # 🔥🔥🔥 핵심 개선: 수수료 반영한 진짜 본전 가격 계산
            commission_rate = config.get("commission_rate", 0.004)
            breakeven_price = int(entry_price * (1 + commission_rate))
            
            # 🔥 1단계: 본전 보호 활성화 (1% 달성)
            breakeven_threshold = config.get("breakeven_protection_rate", 0.01)
            breakeven_protected = position.get('breakeven_protected', False)
            
            if not breakeven_protected and profit_rate >= breakeven_threshold:
                with self.lock:
                    self.positions[stock_code]['breakeven_protected'] = True
                    self.positions[stock_code]['trailing_stop_price'] = breakeven_price  # ✅ 수수료 반영!
                
                self.save_positions()
                
                commission_amount = breakeven_price - entry_price
                logger.info(f"🛡️ {stock_code} 본전 보호 활성화! (수익률: {profit_rate*100:+.2f}%)")
                logger.info(f"   진입가: {entry_price:,}원")
                logger.info(f"   거래비용: {commission_amount:,}원 ({commission_rate*100:.2f}%)")
                logger.info(f"   실제 본전: {breakeven_price:,}원")
                logger.info(f"   손절선: {breakeven_price:,}원 (본전+수수료)")
                
                if config.get("use_discord", True):
                    stock_name = position.get('stock_name', stock_code)
                    msg = f"🛡️ **본전 보호 활성화!**\n"
                    msg += f"종목: {stock_name} ({stock_code})\n"
                    msg += f"진입가: {entry_price:,}원\n"
                    msg += f"현재가: {current_price:,}원 ({profit_rate*100:+.2f}%)\n"
                    msg += f"거래비용: {commission_amount:,}원\n"
                    msg += f"손절선: {breakeven_price:,}원 (본전+수수료)"
                    discord_alert.SendMessage(msg)
                
                # 🔥🔥🔥 return 제거! 아래 트레일링 로직도 실행됨
            
            # 🔥 2단계: 초타이트 트레일링 활성화 (3% 달성)
            tight_threshold = config.get("tight_trailing_threshold", 0.03)
            tight_trailing_active = position.get('tight_trailing_active', False)
            
            if not tight_trailing_active and profit_rate >= tight_threshold:
                with self.lock:
                    self.positions[stock_code]['tight_trailing_active'] = True
                    tight_rate = config.get("tight_trailing_rate", 0.003)  # 0.3%
                    new_trailing_stop = highest_price * (1 - tight_rate)
                    # 본전 이하로 내려가지 않도록 보장
                    new_trailing_stop = max(breakeven_price, int(new_trailing_stop))
                    self.positions[stock_code]['trailing_stop_price'] = new_trailing_stop
                
                self.save_positions()
                
                logger.info(f"🎯 {stock_code} 초타이트 트레일링 시작! (수익률: {profit_rate*100:+.2f}%)")
                logger.info(f"   최고가: {highest_price:,}원")
                logger.info(f"   트레일링: {new_trailing_stop:,}원 (-0.3%)")
                
                if config.get("use_discord", True):
                    stock_name = position.get('stock_name', stock_code)
                    msg = f"🎯 **초타이트 트레일링!**\n"
                    msg += f"종목: {stock_name} ({stock_code})\n"
                    msg += f"진입가: {entry_price:,}원\n"
                    msg += f"최고가: {highest_price:,}원 ({profit_rate*100:+.2f}%)\n"
                    msg += f"트레일링: {new_trailing_stop:,}원 (-0.3%)"
                    discord_alert.SendMessage(msg)
                
                # 🔥🔥🔥 return 제거! 아래 로직도 실행
            
            # 🔥 3단계: 트레일링 스탑 업데이트 (최고가 갱신 시)
            if current_price == highest_price:  # 방금 최고가 갱신됨
                if tight_trailing_active:
                    # 초타이트 트레일링 모드 (3% 이상)
                    tight_rate = config.get("tight_trailing_rate", 0.003)  # 0.3%
                    new_trailing_stop = highest_price * (1 - tight_rate)
                elif breakeven_protected:
                    # 본전 보호 모드 (1~3% 구간)
                    # 🔥 0.5% 트레일링 적용 (기존 1%보다 2배 촘촘)
                    trailing_rate = config.get("trailing_stop_rate", 0.005)  # 0.5%
                    new_trailing_stop = highest_price * (1 - trailing_rate)
                else:
                    # 일반 트레일링 (1~3% 구간, 본전 보호 미활성화)
                    trailing_rate = config.get("trailing_stop_rate", 0.005)  # 0.5%
                    new_trailing_stop = highest_price * (1 - trailing_rate)
                
                # 🔥🔥🔥 핵심: 진짜 본전(수수료 포함) 이하로 절대 내려가지 않음
                new_trailing_stop = max(breakeven_price, int(new_trailing_stop))
                
                with self.lock:
                    self.positions[stock_code]['trailing_stop_price'] = new_trailing_stop
                
                self.save_positions()
                
                trailing_profit = (new_trailing_stop - entry_price) / entry_price
                logger.debug(f"🔄 {stock_code} 트레일링 업데이트: {new_trailing_stop:,}원 (보장수익: {trailing_profit*100:+.2f}%)")
            
        except Exception as e:
            logger.error(f"트레일링 스탑 업데이트 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def check_sell_conditions(self, stock_code, current_signal=None):
        """
        매도 조건 체크 (🔥 로깅 대폭 강화)
        
        우선순위:
        1. 목표 수익 달성 (3%)
        2. 트레일링 스탑 발동
        3. 손절 신호 (SELL/STRONG_SELL)
        4. 긴급 손절 (-3%)
        5. ATR 기반 동적 손절
        
        Returns:
            tuple: (should_sell: bool, reason: str)
        """
        try:
            with self.lock:
                if stock_code not in self.positions:
                    return False, "포지션 없음"
                
                position = self.positions[stock_code].copy()
            
            # 기본 정보
            stock_info = KiwoomAPI.GetStockInfo(stock_code)
            if not stock_info:
                return False, "현재가 조회 실패"
            
            current_price = stock_info.get('CurrentPrice', 0)
            entry_price = position.get('entry_price', 0)
            entry_time_str = position.get('entry_time', '')
            highest_price = position.get('highest_price', entry_price)
            trailing_stop_price = position.get('trailing_stop_price', 0)
            target_profit_price = position.get('target_profit_price', 0)
            
            # 수익률 계산
            profit_rate = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            
            # 보유 시간
            try:
                entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
                holding_time = datetime.now() - entry_time
                holding_minutes = holding_time.total_seconds() / 60
            except:
                holding_minutes = 0
            
            logger.info(f"    ┌─ 매도 조건 상세 체크 ─┐")
            
            # 🔥 1️⃣ 목표 수익 체크
            logger.info(f"    │ [1/5] 목표 수익 체크")
            target_profit_rate = config.get("target_profit_rate", 0.03)
            
            if current_price >= target_profit_price:
                reason = f"목표 수익 달성 ({profit_rate*100:+.2f}% >= {target_profit_rate*100:.0f}%)"
                logger.info(f"    │   ✅ 만족: {current_price:,}원 >= {target_profit_price:,}원")
                logger.info(f"    └─────────────────────┘")
                return True, reason
            else:
                logger.info(f"    │   ❌ 미만족: {current_price:,}원 < {target_profit_price:,}원 (차이: {(target_profit_price-current_price):,}원)")
            
            # 🔥 2️⃣ 트레일링 스탑 체크
            logger.info(f"    │ [2/5] 트레일링 스탑 체크")
            
            if current_price <= trailing_stop_price:
                trailing_loss = (trailing_stop_price - current_price) / current_price
                reason = f"트레일링 스탑 ({profit_rate*100:+.2f}%, 최고가 대비 -{trailing_loss*100:.2f}%)"
                logger.info(f"    │   ✅ 발동: {current_price:,}원 <= {trailing_stop_price:,}원")
                logger.info(f"    │   최고가: {highest_price:,}원 → 현재가: {current_price:,}원")
                logger.info(f"    └─────────────────────┘")
                return True, reason
            else:
                logger.info(f"    │   ❌ 미발동: {current_price:,}원 > {trailing_stop_price:,}원 (여유: {(current_price-trailing_stop_price):,}원)")
            
            # 🔥 3️⃣ 긴급 손절 체크
            logger.info(f"    │ [3/5] 긴급 손절 체크")
            emergency_stop = config.get("emergency_stop_loss", -0.03)
            
            if profit_rate <= emergency_stop:
                reason = f"긴급 손절 ({profit_rate*100:+.2f}% <= {emergency_stop*100:.0f}%)"
                logger.info(f"    │   ✅ 발동: {profit_rate*100:.2f}% <= {emergency_stop*100:.0f}%")
                logger.info(f"    └─────────────────────┘")
                return True, reason
            else:
                logger.info(f"    │   ❌ 미발동: {profit_rate*100:.2f}% > {emergency_stop*100:.0f}% (여유: {(profit_rate-emergency_stop)*100:.2f}%p)")
            
            # 🔥 4️⃣ 유예 기간 체크
            logger.info(f"    │ [4/5] 유예 기간 / ATR 손절 체크")
            grace_period_minutes = config.get("stop_loss_grace_period_minutes", 10)
            
            if holding_minutes < grace_period_minutes:
                logger.info(f"    │   ⏰ 유예 중: {holding_minutes:.0f}분 < {grace_period_minutes}분")
                
                # 유예 기간 중 극단 손절만 체크
                extreme_stop = config.get("extreme_stop_loss", -0.05)
                if profit_rate <= extreme_stop:
                    reason = f"극단 손절 ({profit_rate*100:+.2f}%, 보유 {holding_minutes:.0f}분)"
                    logger.info(f"    │   🚨 극단 손절 발동: {profit_rate*100:.2f}% <= {extreme_stop*100:.0f}%")
                    logger.info(f"    └─────────────────────┘")
                    return True, reason
                else:
                    logger.info(f"    │   ✅ 극단 손절 미발동: {profit_rate*100:.2f}% > {extreme_stop*100:.0f}%")
                    logger.info(f"    └─────────────────────┘")
                    return False, f"유예 중 ({holding_minutes:.0f}분/{grace_period_minutes}분)"
            
            logger.info(f"    │   ✅ 유예 완료: {holding_minutes:.0f}분 >= {grace_period_minutes}분")
            
            # 🔥 5️⃣ ATR 기반 동적 손절
            logger.info(f"    │   🔍 ATR 동적 손절선 계산 중...")
            dynamic_stop = self._calculate_dynamic_stop_loss(stock_code, current_price)
            
            # 신호와 변동성 통합 판단
            signal_type = current_signal.get('signal', 'HOLD') if current_signal else 'HOLD'
            signal_confidence = current_signal.get('confidence', 0) if current_signal else 0
            
            logger.info(f"    │   📊 ATR 손절선: {dynamic_stop*100:.2f}%")
            logger.info(f"    │   📡 신호: {signal_type} (신뢰도: {signal_confidence:.1%})")
            logger.info(f"    │   💰 현재 손익: {profit_rate*100:+.2f}%")
            
            logger.info(f"    │ [5/5] 통합 손절 판단 시작...")
            should_stop, stop_reason = self._integrated_stop_decision(
                stock_code,
                profit_rate,
                dynamic_stop,
                signal_type,
                signal_confidence
            )
            
            logger.info(f"    └─────────────────────┘")
            
            if should_stop:
                return True, stop_reason
            
            return False, "모든 매도 조건 미충족"
            
        except Exception as e:
            logger.error(f"    ❌ 매도 조건 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, f"체크 실패: {str(e)}"

    def calculate_unrealized_profit(self):
        """미실현 손익 계산"""
        try:
            total_unrealized = 0
            
            with self.lock:
                for stock_code, position in self.positions.items():
                    stock_info = KiwoomAPI.GetStockInfo(stock_code)
                    if not stock_info:
                        continue
                    
                    current_price = stock_info.get('CurrentPrice', 0)
                    entry_price = position.get('entry_price', 0)
                    quantity = position.get('quantity', 0)
                    
                    if current_price > 0 and entry_price > 0:
                        unrealized = (current_price - entry_price) * quantity
                        total_unrealized += unrealized
            
            return total_unrealized
            
        except Exception as e:
            logger.error(f"미실현 손익 계산 실패: {e}")
            return 0
    
    def send_daily_report(self):
        """일일 리포트 전송 (장 마감 후)"""
        try:
            logger.info("=" * 60)
            logger.info("📊 일일 리포트 생성 중...")
            logger.info("=" * 60)

            # 🔥🔥🔥 올바른 방법! 🔥🔥🔥
            # config 파일 다시 로드 (최신 데이터 반영)
            config.config = config.load_config()
            logger.info("✅ config 파일 재로드 완료")
            # 🔥🔥🔥 여기까지 추가 🔥🔥🔥

            # 1️⃣ 성과 데이터 가져오기
            perf = config.get('performance', {})
            total_trades = perf.get('total_trades', 0)
            winning_trades = perf.get('winning_trades', 0)
            total_profit = perf.get('total_profit', 0)
            total_loss = perf.get('total_loss', 0)
            canceled_orders = perf.get('canceled_orders', 0)
            
            # 2️⃣ 현재 자산 계산
            asset_info = self.calculate_total_asset()
            if not asset_info:
                logger.warning("⚠️ 자산 정보 조회 실패")
                return
            
            total_asset = asset_info['total_asset']
            orderable_amt = asset_info['orderable_amt']
            holding_value = asset_info['holding_value']
            pending_value = asset_info['pending_value']
            
            # 3️⃣ 미실현 손익 계산
            unrealized_profit = self.calculate_unrealized_profit()
            
            # 4️⃣ 승률 계산
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            net_profit = total_profit + total_loss  # total_loss는 음수
            
            # 5️⃣ 보유 종목 상세
            holdings_detail = ""
            with self.lock:
                if self.positions:
                    holdings_detail = "\n**📈 보유 종목:**\n"
                    for stock_code, position in self.positions.items():
                        stock_name = position.get('stock_name', '')
                        quantity = position.get('quantity', 0)
                        entry_price = position.get('entry_price', 0)
                        
                        stock_info = KiwoomAPI.GetStockInfo(stock_code)
                        current_price = stock_info.get('CurrentPrice', 0) if stock_info else 0
                        
                        if current_price > 0:
                            profit_rate = ((current_price - entry_price) / entry_price) * 100
                            profit_amt = (current_price - entry_price) * quantity
                            holdings_detail += f"• {stock_name} ({stock_code})\n"
                            holdings_detail += f"  └─ {quantity}주, {profit_rate:+.2f}% ({profit_amt:+,}원)\n"
                else:
                    holdings_detail = "\n**📈 보유 종목:** 없음\n"
            
            # 6️⃣ 디스코드 메시지 생성
            msg = f"📊 **{BOT_NAME} 일일 리포트**\n"
            msg += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            msg += "=" * 30 + "\n\n"
            
            msg += "**💰 자산 현황**\n"
            msg += f"• 총 자산: {total_asset:,}원\n"
            msg += f"• 현금: {orderable_amt:,}원\n"
            msg += f"• 보유 평가: {holding_value:,}원\n"
            msg += f"• 미체결: {pending_value:,}원\n"
            msg += f"• 미실현 손익: {unrealized_profit:+,}원\n\n"
            
            msg += "**📈 거래 성과**\n"
            msg += f"• 총 거래: {total_trades}회\n"
            msg += f"• 승률: {win_rate:.1f}% ({winning_trades}승/{total_trades-winning_trades}패)\n"
            msg += f"• 실현 수익: {total_profit:+,}원\n"
            msg += f"• 실현 손실: {total_loss:+,}원\n"
            msg += f"• 순 손익: {net_profit:+,}원\n"
            msg += f"• 취소 주문: {canceled_orders}회\n"
            
            msg += holdings_detail
            
            msg += f"\n**🔄 쿨다운 종목**\n"
            with self.lock:
                if self.cooldowns:
                    for stock_code, cooldown in self.cooldowns.items():
                        stock_name = cooldown.get('stock_name', '')
                        cooldown_until = cooldown.get('cooldown_until', '')
                        msg += f"• {stock_name} ({stock_code}): {cooldown_until}까지\n"
                else:
                    msg += "• 없음\n"
            
            # 7️⃣ 전송
            logger.info("✅ 일일 리포트 생성 완료")
            logger.info(msg)

            # 🔥 수정: use_discord로 변경 + 상세 로그 추가
            if config.get("use_discord", True):
                try:
                    discord_alert.SendMessage(msg)
                    logger.info("✅ Discord 일일 리포트 전송 완료")
                except Exception as discord_e:
                    logger.error(f"❌ Discord 전송 실패: {discord_e}")
            else:
                logger.warning("⚠️ Discord 알림이 비활성화되어 있습니다")
            
        except Exception as e:
            logger.error(f"일일 리포트 생성 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _calculate_dynamic_stop_loss(self, stock_code, current_price):
        """ATR 기반 동적 손절선 계산 (Kiwoom API 연속조회 활용)"""
        try:
            # 🔥 이제 20개 분봉 리스트를 받아옴!
            minute_data = KiwoomAPI.GetMinuteData(stock_code, count=20)
            
            if not minute_data or len(minute_data) < 14:
                logger.debug(f"{stock_code} 분봉 데이터 부족 ({len(minute_data) if minute_data else 0}개), 기본 손절선 적용")
                return self._get_default_stop_loss(stock_code)
            
            # ATR 계산
            atr = self._calculate_atr(minute_data, period=14)
            
            if atr == 0:
                logger.debug(f"{stock_code} ATR 계산 실패, 기본 손절선 적용")
                return self._get_default_stop_loss(stock_code)
            
            atr_ratio = atr / current_price
            base_multiplier = config.get("atr_stop_multiplier", 2.0)
            dynamic_stop = -max(0.02, min(0.08, atr_ratio * base_multiplier))
            
            logger.info(f"📊 {stock_code} 동적 손절선:")
            logger.info(f"   현재가: {current_price:,}원")
            logger.info(f"   분봉 데이터: {len(minute_data)}개")
            logger.info(f"   ATR: {atr:.0f}원 ({atr_ratio*100:.2f}%)")
            logger.info(f"   손절선: {dynamic_stop*100:.2f}%")
            
            return dynamic_stop
            
        except Exception as e:
            logger.error(f"동적 손절선 계산 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._get_default_stop_loss(stock_code)

    def _calculate_atr(self, minute_data, period=14):
        """
        ATR(Average True Range) 계산
        
        Args:
            minute_data: 분봉 리스트 (최신순)
            period: ATR 계산 기간 (기본 14)
        
        Returns:
            float: ATR 값 (원 단위)
        """
        try:
            if len(minute_data) < period + 1:
                return 0
            
            true_ranges = []
            
            # 최신 데이터부터 과거로 순회
            for i in range(len(minute_data) - 1):
                current = minute_data[i]
                previous = minute_data[i + 1]
                
                high = float(current.get('HighPrice', 0))
                low = float(current.get('LowPrice', 0))
                prev_close = float(previous.get('ClosePrice', 0))
                
                # True Range 계산
                tr1 = high - low                    # 당일 고가-저가
                tr2 = abs(high - prev_close)       # 당일 고가 - 전일 종가
                tr3 = abs(low - prev_close)        # 당일 저가 - 전일 종가
                
                true_range = max(tr1, tr2, tr3)
                true_ranges.append(true_range)
            
            # ATR = 최근 period개 True Range의 평균
            atr = sum(true_ranges[:period]) / period
            
            logger.debug(f"ATR 계산: {period}개 TR 평균 = {atr:.0f}원")
            
            return atr
            
        except Exception as e:
            logger.error(f"ATR 계산 오류: {e}")
            return 0

    def _integrated_stop_decision(self, stock_code, profit_rate, dynamic_stop, signal_type, signal_confidence):
        """신호와 변동성 통합 손절 판단 (🔥 로깅 대폭 강화)"""
        try:
            min_confidence = config.get("min_signal_confidence", 0.4)
            
            logger.info(f"        ┌─ 통합 손절 판단 ─┐")
            logger.info(f"        │ 입력 정보:")
            logger.info(f"        │   • 현재 손익: {profit_rate*100:+.2f}%")
            logger.info(f"        │   • ATR 손절: {dynamic_stop*100:.2f}%")
            logger.info(f"        │   • 신호: {signal_type}")
            logger.info(f"        │   • 신뢰도: {signal_confidence:.1%}")
            logger.info(f"        │")
            
            # 상황 1: STRONG_SELL (최우선)
            logger.info(f"        │ [상황1] STRONG_SELL 체크")
            if signal_type == "STRONG_SELL" and signal_confidence >= min_confidence:
                reason = f"강력 손절 신호 (STRONG_SELL, 신뢰도: {signal_confidence:.1%})"
                logger.info(f"        │   🚨 ✅ STRONG_SELL 발동!")
                logger.info(f"        │   → ATR 무시하고 즉시 손절")
                logger.info(f"        └─────────────────┘")
                return True, reason
            else:
                if signal_type == "STRONG_SELL":
                    logger.info(f"        │   ❌ STRONG_SELL이지만 신뢰도 부족 ({signal_confidence:.1%} < {min_confidence:.1%})")
                else:
                    logger.info(f"        │   ❌ STRONG_SELL 아님 (신호: {signal_type})")
            
            # 상황 2: ATR 손절선 도달
            logger.info(f"        │ [상황2] ATR 손절선 도달 체크")
            logger.info(f"        │   비교: {profit_rate*100:.2f}% vs {dynamic_stop*100:.2f}%")
            
            if profit_rate <= dynamic_stop:
                logger.info(f"        │   ⚠️ ATR 손절선 도달!")
                
                # 강한 매수 신호 유지 시 추가 유예
                if signal_type in ["STRONG_BUY", "BUY"] and signal_confidence >= 0.6:
                    grace_buffer = config.get("signal_override_buffer", 0.02)
                    final_stop = dynamic_stop - grace_buffer
                    
                    logger.info(f"        │   🔄 {signal_type} 신호 감지 → 추가 유예 검토")
                    logger.info(f"        │   신뢰도: {signal_confidence:.1%} >= 60%")
                    logger.info(f"        │   유예 버퍼: {grace_buffer*100:.0f}%")
                    logger.info(f"        │   최종 손절: {final_stop*100:.2f}%")
                    
                    if profit_rate <= final_stop:
                        reason = f"최종 손절 ({profit_rate*100:+.2f}%, {signal_type} 신호에도 불구)"
                        logger.info(f"        │   ⚠️ ✅ 최종 손절선도 돌파 → 손절")
                        logger.info(f"        └─────────────────┘")
                        return True, reason
                    else:
                        logger.info(f"        │   ✅ 유예 적용: {profit_rate*100:.2f}% > {final_stop*100:.2f}%")
                        logger.info(f"        │   → {signal_type} 강세로 관찰 지속")
                        logger.info(f"        └─────────────────┘")
                        return False, None
                
                # 신호 없거나 약함 → 손절
                reason = f"ATR 손절 ({profit_rate*100:+.2f}%, 기준: {dynamic_stop*100:.1f}%)"
                logger.info(f"        │   ✅ 매수 신호 없음 or 약함 → 손절")
                logger.info(f"        └─────────────────┘")
                return True, reason
            else:
                atr_buffer = profit_rate - dynamic_stop
                logger.info(f"        │   ❌ ATR 손절선 미도달")
                logger.info(f"        │   여유: {atr_buffer*100:.2f}%p")
            
            # 상황 3: SELL 신호 + ATR 여유
            logger.info(f"        │ [상황3] SELL 신호 복합 판단")
            
            if signal_type == "SELL" and signal_confidence >= min_confidence:
                atr_buffer = dynamic_stop - profit_rate
                atr_usage = (profit_rate / dynamic_stop) * 100 if dynamic_stop != 0 else 0
                
                logger.info(f"        │   ⚠️ SELL 신호 발생!")
                logger.info(f"        │   신뢰도: {signal_confidence:.1%}")
                logger.info(f"        │   손실: {profit_rate*100:+.2f}%")
                logger.info(f"        │   ATR: {dynamic_stop*100:.2f}%")
                logger.info(f"        │   ATR 사용률: {atr_usage:.1f}%")
                
                # 고신뢰도 SELL → 즉시 손절
                if signal_confidence >= 0.75:
                    reason = f"고신뢰 SELL ({signal_confidence:.1%}, ATR 무시)"
                    logger.info(f"        │   🚨 ✅ 신뢰도 매우 높음 ({signal_confidence:.1%} >= 75%) → 즉시 손절")
                    logger.info(f"        └─────────────────┘")
                    return True, reason
                
                # ATR 50% 이상 소진 + SELL → 손절
                if atr_usage >= 50:
                    reason = f"SELL+ATR 복합 손절 ({signal_confidence:.1%}, ATR {atr_usage:.0f}% 소진)"
                    logger.info(f"        │   ⚠️ ✅ ATR 반 이상 소진 ({atr_usage:.0f}% >= 50%) → 손절")
                    logger.info(f"        └─────────────────┘")
                    return True, reason
                
                # ATR 여유 충분 → 관찰
                logger.info(f"        │   🔄 ATR 여유 충분 ({atr_usage:.0f}% < 50%) → 관찰")
                logger.info(f"        └─────────────────┘")
                return False, None
            else:
                if signal_type == "SELL":
                    logger.info(f"        │   ❌ SELL이지만 신뢰도 부족 ({signal_confidence:.1%} < {min_confidence:.1%})")
                else:
                    logger.info(f"        │   ❌ SELL 아님 (신호: {signal_type})")
            
            logger.info(f"        │")
            logger.info(f"        │ ✅ 모든 손절 조건 미충족 → 보유 유지")
            logger.info(f"        └─────────────────┘")
            return False, None
            
        except Exception as e:
            logger.error(f"        ❌ 통합 손절 판단 실패: {e}")
            if profit_rate <= dynamic_stop:
                return True, f"ATR 손절 (판단 실패)"
            return False, None

    def _get_default_stop_loss(self, stock_code):
        """기본 손절선 (ATR 실패 시)"""
        sector_volatility = {
            "battery": -0.05,        # 2차전지: 고변동성
            "robot": -0.05,          # 로봇: 고변동성
            "defense": -0.04,        # 방산: 중간 변동성
            "nuclear": -0.04,        # 원전: 중간 변동성
            "power": -0.04,          # 🆕 전력: 중간 변동성
            "semiconductor": -0.03,  # 반도체: 저변동성 (대형주)
            "lng": -0.04,            # LNG: 중간 변동성
            "shipbuilding": -0.04,   # 조선: 중간 변동성
            "bio": -0.06,            # 🆕 바이오: 초고변동성
            "entertainment": -0.05   # 🆕 엔터: 고변동성
        }
        
        sector = self._get_stock_sector(stock_code)
        return sector_volatility.get(sector, -0.04)

    def _get_stock_sector(self, stock_code):
        """종목 섹터 조회"""
        sector_map = {
            # 2차전지 (18종목)
            "086520": "battery", "247540": "battery", "005490": "battery",
            "003670": "battery", "006400": "battery", "373220": "battery",
            "051910": "battery", "066970": "battery", "348370": "battery",
            "278280": "battery", "357780": "battery", "078600": "battery",
            "020150": "battery", "361610": "battery", "305720": "battery",
            "365340": "battery", "005070": "battery", "095500": "battery",
            
            # LNG (2종목)
            "033500": "lng", "017960": "lng",
            
            # 조선 (3종목)
            "042660": "shipbuilding", "010140": "shipbuilding", 
            "097230": "shipbuilding",
            
            # 원전 (7종목)
            "105840": "nuclear", "457550": "nuclear", "094820": "nuclear",
            "034020": "nuclear", "000720": "nuclear", "028260": "nuclear",
            "051600": "nuclear",
            
            # 전력/중전기 (10종목)
            "267260": "power", "298040": "power", "010120": "power",
            "001440": "power", "152360": "power", "291640": "power",
            "126720": "power", "033100": "power", "388050": "power",
            "189860": "power",
            
            # 방산 (7종목)
            "272210": "defense", "064350": "defense", "079550": "defense",
            "012450": "defense", "047810": "defense", "103140": "defense",
            "281990": "defense",
            
            # 로봇 (9종목)
            "030530": "robot", "058610": "robot", "182690": "robot",
            "108490": "robot", "454910": "robot", "399720": "robot",
            "140860": "robot", "056080": "robot", "348340": "robot",
            
            # 반도체 (19종목)
            "005930": "semiconductor", "000660": "semiconductor",
            "000990": "semiconductor", "108320": "semiconductor",
            "131970": "semiconductor", "036540": "semiconductor",
            "067310": "semiconductor", "058470": "semiconductor",
            "039030": "semiconductor", "403870": "semiconductor",
            "042700": "semiconductor", "240810": "semiconductor",
            "036930": "semiconductor", "064760": "semiconductor",
            "005290": "semiconductor", "007660": "semiconductor",
            "218410": "semiconductor", "101490": "semiconductor",
            "319660": "semiconductor",
            
            # 바이오 (7종목)
            "207940": "bio", "068270": "bio", "302440": "bio",
            "326030": "bio", "128940": "bio", "067080": "bio",
            "028300": "bio",
            
            # 엔터테인먼트 (4종목)
            "352820": "entertainment", "035900": "entertainment",
            "041510": "entertainment", "122870": "entertainment"
        }
        
        return sector_map.get(stock_code, "unknown")

    def execute_sell(self, stock_code, reason):
        """
        매도 주문 실행 (미체결 관리 포함)
        """
        try:
            with self.lock:
                if stock_code not in self.positions:
                    return False
                
                position = self.positions[stock_code].copy()
            
            stock_name = position.get('stock_name', '')
            
            logger.info("=" * 60)
            logger.info(f"💸 {stock_name} 매도 시도: {reason}")
            logger.info("=" * 60)
            
            stock_info = KiwoomAPI.GetStockInfo(stock_code)
            if not stock_info:
                logger.error(f"❌ 현재가 조회 실패")
                return False
            
            current_price = stock_info.get('CurrentPrice', 0)
            
            # 🔥 호가 단위 적용 (매도: 올림)
            adjusted_price = self.adjust_price_to_tick(current_price, is_buy=False)
            
            quantity = position.get('quantity', 0)
            entry_price = position.get('entry_price', 0)
            
            profit = (adjusted_price - entry_price) * quantity
            profit_rate = (adjusted_price - entry_price) / entry_price
            
            logger.info(f"💸 매도 주문: {adjusted_price:,}원 × {quantity}주 = {adjusted_price * quantity:,}원")
            if adjusted_price != current_price:
                logger.info(f"   (원래가: {current_price:,}원 → 호가 조정: {adjusted_price:,}원)")
            logger.info(f"📊 예상 수익: {profit:+,}원 ({profit_rate*100:+.2f}%)")
            
            order_result = KiwoomAPI.MakeSellLimitOrder(stock_code, quantity, adjusted_price)
            
            if order_result.get('success', False):
                order_no = order_result.get('order_no', '')
                
                # 🔥 매도 미체결 관리: pending_orders에 추가
                with self.lock:
                    self.pending_orders[stock_code] = {
                        'stock_name': stock_name,
                        'order_no': order_no,
                        'order_type': 'sell',  # 매도 타입
                        'order_price': adjusted_price,
                        'order_quantity': quantity,
                        'order_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'pending',
                        'retry_count': 0,
                        'sell_reason': reason,
                        'entry_price': entry_price,
                        'expected_profit': profit,
                        'expected_profit_rate': profit_rate
                    }
                
                # positions는 유지! (체결 확인 후 삭제)
                
                self.save_pending_orders()
                
                msg = f"💸 **매도 주문 완료!**\n"
                msg += f"종목: {stock_name} ({stock_code})\n"
                msg += f"주문번호: {order_no}\n"
                msg += f"가격: {adjusted_price:,}원 × {quantity}주\n"
                msg += f"예상 수익: {profit:+,}원 ({profit_rate*100:+.2f}%)\n"
                msg += f"사유: {reason}\n"
                msg += f"⏰ 체결 확인 중..."
                
                logger.info(msg)
                
                if config.get("use_discord", True):
                    discord_alert.SendMessage(msg)
                
                return True
            else:
                error_msg = order_result.get('msg', '알 수 없는 오류')
                logger.error(f"❌ 매도 주문 실패: {error_msg}")
                return False
            
        except Exception as e:
            logger.error(f"매도 실행 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def check_positions_and_sell(self):
        """보유 종목 트레일링 & 매도 체크 (🔥 로깅 강화)"""
        try:
            with self.lock:
                if not self.positions:
                    logger.debug("📊 보유 종목 없음 - 매도 체크 스킵")
                    return
                
                position_codes = list(self.positions.keys())
            
            logger.info("=" * 80)
            logger.info(f"📊 보유 종목 체크 시작: {len(position_codes)}개")
            logger.info("=" * 80)
            
            # 최신 신호 읽기 (매도 신호 확인용)
            all_signals = self.read_latest_signals()
            valid_signals = self.filter_valid_signals(all_signals)
            
            logger.info(f"📡 유효 신호: {len(valid_signals)}개")
            
            for stock_code in position_codes:
                try:
                    with self.lock:
                        if stock_code not in self.positions:
                            continue
                        position = self.positions[stock_code].copy()
                    
                    stock_name = position.get('stock_name', stock_code)
                    
                    logger.info("")
                    logger.info("─" * 80)
                    logger.info(f"🔍 [{stock_name}] 매도 조건 체크 시작")
                    logger.info("─" * 80)
                    
                    # 🔥 1. 현재 상태 정보 로그
                    stock_info = KiwoomAPI.GetStockInfo(stock_code)
                    if not stock_info:
                        logger.warning(f"  ⚠️ 현재가 조회 실패 - 스킵")
                        continue
                    
                    current_price = stock_info.get('CurrentPrice', 0)
                    entry_price = position.get('entry_price', 0)
                    entry_time_str = position.get('entry_time', '')
                    highest_price = position.get('highest_price', entry_price)
                    trailing_stop = position.get('trailing_stop_price', 0)
                    
                    # 수익률 계산
                    profit_rate = (current_price - entry_price) / entry_price if entry_price > 0 else 0
                    
                    # 보유 시간 계산
                    try:
                        entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
                        holding_time = datetime.now() - entry_time
                        holding_minutes = holding_time.total_seconds() / 60
                    except:
                        holding_minutes = 0
                    
                    logger.info(f"  📌 현재가: {current_price:,}원")
                    logger.info(f"  📌 진입가: {entry_price:,}원")
                    logger.info(f"  📌 현재 수익률: {profit_rate*100:+.2f}%")
                    logger.info(f"  📌 최고가: {highest_price:,}원")
                    logger.info(f"  📌 보유 시간: {holding_minutes:.0f}분")
                    logger.info(f"  📌 트레일링 스탑: {trailing_stop:,}원")
                    
                    # 🔥 2. 현재 신호 확인
                    current_signal = None
                    for sig in valid_signals:
                        if sig.get('stock_code') == stock_code:
                            current_signal = sig
                            break
                    
                    if current_signal:
                        signal_type = current_signal.get('signal', 'HOLD')
                        signal_confidence = current_signal.get('confidence', 0)
                        signal_score = current_signal.get('score', 0)
                        logger.info(f"  📡 현재 신호: {signal_type} (점수: {signal_score:.1f}, 신뢰도: {signal_confidence:.1%})")
                    else:
                        logger.info(f"  📡 현재 신호: 없음 (유효 신호 없음)")
                    
                    # 🔥 3. 트레일링 스탑 업데이트
                    logger.info(f"  🔄 트레일링 스탑 업데이트 시작...")
                    self.update_trailing_stop(stock_code)
                    
                    # 🔥 4. 매도 조건 체크 (상세 로그 포함)
                    logger.info(f"  🔍 매도 조건 체크 시작...")
                    should_sell, reason = self.check_sell_conditions(stock_code, current_signal)
                    
                    # 🔥 5. 매도 판단 결과
                    if should_sell:
                        logger.warning(f"  ✅ 매도 결정: {reason}")
                        logger.info(f"  💸 매도 실행 시작...")
                        self.execute_sell(stock_code, reason)
                    else:
                        if reason:
                            logger.info(f"  ⏸️ 매도 안 함: {reason}")
                        else:
                            logger.info(f"  ⏸️ 매도 안 함: 모든 조건 미충족")
                    
                    logger.info("─" * 80)
                    
                except Exception as e:
                    logger.error(f"  ❌ {stock_code} 체크 중 오류: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info("=" * 80)
            logger.info(f"✅ 보유 종목 체크 완료")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"보유 종목 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def check_positions_and_sell(self):
        """보유 종목 트레일링 & 매도 체크 (🔥 로깅 강화)"""
        try:
            with self.lock:
                if not self.positions:
                    logger.debug("📊 보유 종목 없음 - 매도 체크 스킵")
                    return
                
                position_codes = list(self.positions.keys())
            
            logger.info("=" * 80)
            logger.info(f"📊 보유 종목 체크 시작: {len(position_codes)}개")
            logger.info("=" * 80)
            
            # 최신 신호 읽기 (매도 신호 확인용)
            all_signals = self.read_latest_signals()
            valid_signals = self.filter_valid_signals(all_signals)
            
            logger.info(f"📡 유효 신호: {len(valid_signals)}개")
            
            for stock_code in position_codes:
                try:
                    with self.lock:
                        if stock_code not in self.positions:
                            continue
                        position = self.positions[stock_code].copy()
                    
                    stock_name = position.get('stock_name', stock_code)
                    
                    logger.info("")
                    logger.info("─" * 80)
                    logger.info(f"🔍 [{stock_name}] 매도 조건 체크 시작")
                    logger.info("─" * 80)
                    
                    # 🔥 1. 현재 상태 정보 로그
                    stock_info = KiwoomAPI.GetStockInfo(stock_code)
                    if not stock_info:
                        logger.warning(f"  ⚠️ 현재가 조회 실패 - 스킵")
                        continue
                    
                    current_price = stock_info.get('CurrentPrice', 0)
                    entry_price = position.get('entry_price', 0)
                    entry_time_str = position.get('entry_time', '')
                    highest_price = position.get('highest_price', entry_price)
                    trailing_stop = position.get('trailing_stop_price', 0)
                    
                    # 수익률 계산
                    profit_rate = (current_price - entry_price) / entry_price if entry_price > 0 else 0
                    
                    # 보유 시간 계산
                    try:
                        entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
                        holding_time = datetime.now() - entry_time
                        holding_minutes = holding_time.total_seconds() / 60
                    except:
                        holding_minutes = 0
                    
                    logger.info(f"  📌 현재가: {current_price:,}원")
                    logger.info(f"  📌 진입가: {entry_price:,}원")
                    logger.info(f"  📌 현재 수익률: {profit_rate*100:+.2f}%")
                    logger.info(f"  📌 최고가: {highest_price:,}원")
                    logger.info(f"  📌 보유 시간: {holding_minutes:.0f}분")
                    logger.info(f"  📌 트레일링 스탑: {trailing_stop:,}원")
                    
                    # 🔥 2. 현재 신호 확인
                    current_signal = None
                    for sig in valid_signals:
                        if sig.get('stock_code') == stock_code:
                            current_signal = sig
                            break
                    
                    if current_signal:
                        signal_type = current_signal.get('signal', 'HOLD')
                        signal_confidence = current_signal.get('confidence', 0)
                        signal_score = current_signal.get('score', 0)
                        logger.info(f"  📡 현재 신호: {signal_type} (점수: {signal_score:.1f}, 신뢰도: {signal_confidence:.1%})")
                    else:
                        logger.info(f"  📡 현재 신호: 없음 (유효 신호 없음)")
                    
                    # 🔥 3. 트레일링 스탑 업데이트
                    logger.info(f"  🔄 트레일링 스탑 업데이트 시작...")
                    self.update_trailing_stop(stock_code)
                    
                    # 🔥 4. 매도 조건 체크 (상세 로그 포함)
                    logger.info(f"  🔍 매도 조건 체크 시작...")
                    should_sell, reason = self.check_sell_conditions(stock_code, current_signal)
                    
                    # 🔥 5. 매도 판단 결과
                    if should_sell:
                        logger.warning(f"  ✅ 매도 결정: {reason}")
                        logger.info(f"  💸 매도 실행 시작...")
                        self.execute_sell(stock_code, reason)
                    else:
                        if reason:
                            logger.info(f"  ⏸️ 매도 안 함: {reason}")
                        else:
                            logger.info(f"  ⏸️ 매도 안 함: 모든 조건 미충족")
                    
                    logger.info("─" * 80)
                    
                except Exception as e:
                    logger.error(f"  ❌ {stock_code} 체크 중 오류: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info("=" * 80)
            logger.info(f"✅ 보유 종목 체크 완료")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"보유 종목 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def start_background_threads(self):
        """백그라운드 스레드 시작"""
        
        def pending_checker():
            """미체결 주문 체크 스레드"""
            interval = config.get("check_pending_interval_seconds", 30)
            
            while self.running:
                try:
                    if self.is_trading_time():
                        self.check_pending_orders()
                except Exception as e:
                    logger.error(f"미체결 체크 스레드 오류: {e}")
                
                time.sleep(interval)
        
        def position_checker():
            """보유 종목 트레일링 & 매도 체크 스레드"""
            interval = config.get("check_position_interval_seconds", 60)
            
            while self.running:
                try:
                    if self.is_trading_time():
                        self.check_positions_and_sell()
                except Exception as e:
                    logger.error(f"보유 종목 체크 스레드 오류: {e}")
                
                time.sleep(interval)
        
        # 🔥🔥🔥 여기부터 새로 추가 🔥🔥🔥

        def daily_report_checker():
            """일일 리포트 전송 체크 (15:20~15:30)"""
            report_sent_date = None
            logger.info("✅ 일일 리포트 체크 스레드 시작")
            
            while self.running:
                try:
                    now = datetime.now()
                    
                    # 🔥🔥🔥 여기 수정! 평일 체크 추가 🔥🔥🔥
                    # 15:20~15:30 사이이고 평일(월~금)인지 확인
                    is_weekday = now.weekday() < 5  # 월(0) ~ 금(4)
                    
                    if (now.hour == 15 and 
                        20 <= now.minute <= 30 and 
                        is_weekday):  # 👈 평일 체크 추가!
                        
                        # 오늘 아직 전송 안했으면 전송
                        if report_sent_date != now.date():
                            logger.info("📊 일일 리포트 시간 도달 (장 개장일)")
                            self.send_daily_report()
                            report_sent_date = now.date()
                            logger.info(f"✅ 일일 리포트 전송 완료 - 다음: {(now + timedelta(days=1)).date()}")
                    
                    # 🆕 주말/공휴일 로그 추가 (디버깅용)
                    elif now.hour == 15 and 20 <= now.minute <= 30:
                        if not is_weekday:
                            if report_sent_date != now.date():  # 하루에 한 번만 로그
                                logger.info("⏸️ 오늘은 주말이므로 일일 리포트를 전송하지 않습니다")
                                report_sent_date = now.date()  # 로그 중복 방지
                    
                except Exception as e:
                    logger.error(f"일일 리포트 체크 스레드 오류: {e}")
                
                # 1분마다 체크
                time.sleep(60)

        # 🔥🔥🔥 여기까지 추가 🔥🔥🔥
        
        # 스레드 시작
        pending_thread = threading.Thread(target=pending_checker, daemon=True)
        position_thread = threading.Thread(target=position_checker, daemon=True)
        report_thread = threading.Thread(target=daily_report_checker, daemon=True)  # 🔥 추가!
        
        pending_thread.start()
        position_thread.start()
        report_thread.start()  # 🔥 추가!
        
        logger.info("✅ 백그라운드 스레드 시작 완료")
        logger.info(f"   - 미체결 체크: {config.get('check_pending_interval_seconds')}초마다")
        logger.info(f"   - 보유 종목 체크: {config.get('check_position_interval_seconds')}초마다")
        logger.info(f"   - 일일 리포트: 15:20~15:30 (장 마감 후)")  # 🔥 추가!

    def stop(self):
        """봇 중지"""
        self.running = False
        logger.info("🛑 봇 중지 신호 전송")

    def calculate_total_asset(self, retry_count=0, max_retry=3) -> dict:
        """
        총 자산 계산 (타임아웃 및 재시도 추가)
        = 주문가능금액 + 보유주식평가금액 + 미체결매수금액
        
        Args:
            retry_count: 현재 재시도 횟수
            max_retry: 최대 재시도 횟수
        
        Returns:
            dict: {
                'total_asset': 총 자산,
                'orderable_amt': 주문가능금액,
                'holding_value': 보유주식평가금액,
                'pending_value': 미체결매수금액
            }
        """
        try:
            logger.info(f"💰 자산 계산 시작 (시도: {retry_count + 1}/{max_retry + 1})")

            # 1️⃣ 주문가능금액 조회 (타임아웃 10초)
            logger.debug("   → 1단계: 잔고 조회 시작...")

            try:
                balance = call_with_timeout(KiwoomAPI.GetBalance, timeout=10)
            except TimeoutError as e:
                logger.error(f"❌ 잔고 조회 타임아웃: {e}")
                
                if retry_count < max_retry:
                    logger.warning(f"🔄 {retry_count + 1}초 후 재시도...")
                    time.sleep(retry_count + 1)
                    return self.calculate_total_asset(retry_count + 1, max_retry)
                else:
                    logger.error(f"❌ 최대 재시도 초과 - 자산 계산 실패")
                    return None

            if not balance:
                logger.error("❌ 잔고 조회 실패 (응답 없음)")
                
                if retry_count < max_retry:
                    logger.warning(f"🔄 {retry_count + 1}초 후 재시도...")
                    time.sleep(retry_count + 1)
                    return self.calculate_total_asset(retry_count + 1, max_retry)
                else:
                    logger.error(f"❌ 최대 재시도 초과 - 자산 계산 실패")
                    return None

            # 🔥🔥🔥 개선: D+2 예수금 우선 사용 (정산 반영된 실제 금액)
            orderable_amt = balance.get('OrderableAmt', 0)
            d2_deposit = balance.get('D2_Deposit', 0)

            # D+2 예수금이 주문가능금액보다 크면 D+2 사용 (매도 체결 반영)
            if d2_deposit > orderable_amt:
                logger.info(f"   💡 D+2 예수금 사용: {d2_deposit:,}원 (주문가능: {orderable_amt:,}원)")
                logger.info(f"   → 정산 반영된 실제 금액으로 계산")
                orderable_amt = d2_deposit
            else:
                logger.debug(f"   ✅ 주문가능금액 사용: {orderable_amt:,}원")

            logger.debug(f"   ✅ 1단계 완료: 현금 {orderable_amt:,}원")

            # 2️⃣ 보유 주식 평가금액 계산
            logger.debug("   → 2단계: 보유주식 평가 시작...")
            holding_value = 0
            
            with self.lock:
                position_count = len(self.positions)
                logger.debug(f"      보유 종목 수: {position_count}개")
                
                for idx, (stock_code, position) in enumerate(self.positions.items(), 1):
                    try:
                        logger.debug(f"      {idx}/{position_count} - {stock_code} 평가 중...")
                        
                        stock_info = call_with_timeout(
                            KiwoomAPI.GetStockInfo, 
                            timeout=10,
                            stock_code=stock_code
                        )
                        
                        if stock_info:
                            current_price = stock_info.get('CurrentPrice', 0)
                            quantity = position.get('quantity', 0)
                            value = current_price * quantity
                            holding_value += value
                            logger.debug(f"         {current_price:,}원 × {quantity}주 = {value:,}원")
                        else:
                            logger.warning(f"      ⚠️ {stock_code} 현재가 조회 실패 - 스킵")
                            
                    except TimeoutError:
                        logger.warning(f"      ⚠️ {stock_code} 현재가 조회 타임아웃 - 스킵")
                    except Exception as e:
                        logger.error(f"      ❌ {stock_code} 평가 오류: {e}")
            
            logger.debug(f"   ✅ 2단계 완료: 보유주식 {holding_value:,}원")
            
            # 3️⃣ 미체결 매수 주문 금액 계산
            logger.debug("   → 3단계: 미체결 주문 계산 시작...")
            pending_value = 0
            
            with self.lock:
                pending_count = len(self.pending_orders)
                logger.debug(f"      미체결 주문 수: {pending_count}개")
                
                for stock_code, pending in self.pending_orders.items():
                    if pending.get('order_type') == 'buy':
                        order_price = pending.get('order_price', 0)
                        order_quantity = pending.get('order_quantity', 0)
                        value = order_price * order_quantity
                        pending_value += value
                        logger.debug(f"      {stock_code}: {order_price:,}원 × {order_quantity}주 = {value:,}원")
            
            logger.debug(f"   ✅ 3단계 완료: 미체결 {pending_value:,}원")
            
            # 4️⃣ 총 자산
            total_asset = orderable_amt + holding_value + pending_value
            
            result = {
                'total_asset': total_asset,
                'orderable_amt': orderable_amt,
                'holding_value': holding_value,
                'pending_value': pending_value
            }
            
            logger.info(f"✅ 자산 계산 완료!")
            logger.info(f"   💰 총 자산: {total_asset:,}원")
            logger.info(f"      현금: {orderable_amt:,}원")
            logger.info(f"      보유: {holding_value:,}원")
            logger.info(f"      미체결: {pending_value:,}원")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 총 자산 계산 예외: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            if retry_count < max_retry:
                logger.warning(f"🔄 {retry_count + 1}초 후 재시도...")
                time.sleep(retry_count + 1)
                return self.calculate_total_asset(retry_count + 1, max_retry)
            
            return None

    def calculate_unrealized_profit(self) -> dict:
        """
        미실현 손익 계산
        
        Returns:
            dict: {
                'unrealized_profit': 미실현 손익,
                'unrealized_rate': 미실현 수익률,
                'total_invested': 총 투자금액,
                'current_value': 현재 평가금액
            }
        """
        try:
            total_invested = 0
            current_value = 0
            
            with self.lock:
                for stock_code, position in self.positions.items():
                    entry_price = position.get('entry_price', 0)
                    quantity = position.get('quantity', 0)
                    entry_commission = position.get('entry_commission', 0)
                    
                    # 매수 금액
                    invested = (entry_price * quantity) + entry_commission
                    total_invested += invested
                    
                    # 현재 평가 금액
                    stock_info = KiwoomAPI.GetStockInfo(stock_code)
                    if stock_info:
                        current_price = stock_info.get('CurrentPrice', 0)
                        value = current_price * quantity
                        current_value += value
            
            unrealized_profit = current_value - total_invested
            unrealized_rate = (unrealized_profit / total_invested * 100) if total_invested > 0 else 0
            
            return {
                'unrealized_profit': unrealized_profit,
                'unrealized_rate': unrealized_rate,
                'total_invested': total_invested,
                'current_value': current_value
            }
            
        except Exception as e:
            logger.error(f"미실현 손익 계산 실패: {e}")
            return {
                'unrealized_profit': 0,
                'unrealized_rate': 0,
                'total_invested': 0,
                'current_value': 0
            }

    def send_daily_report(self):
        """일일 성과 리포트 발송 (장 마감 후)"""
        try:
            logger.info("=" * 60)
            logger.info("📊 일일 성과 리포트 생성 중...")
            logger.info("=" * 60)
            
            # 1. 현재 자산 조회
            asset_info = self.calculate_total_asset()
            if not asset_info:
                logger.error("❌ 자산 조회 실패 - 리포트 생성 중단")
                return
            
            current_asset = asset_info['total_asset']
            
            # 2. 성과 데이터 로드
            perf = config.get('performance', {})
            baseline_asset = perf.get('baseline_asset', 500000)
            baseline_date = perf.get('baseline_date', '')
            
            net_realized_profit = perf.get('net_realized_profit', 0)
            total_trades = perf.get('total_trades', 0)
            winning_trades = perf.get('winning_trades', 0)
            losing_trades = perf.get('losing_trades', 0)
            win_rate = perf.get('win_rate', 0)
            
            # 3. 미실현 손익 계산
            unrealized_info = self.calculate_unrealized_profit()
            unrealized_profit = unrealized_info['unrealized_profit']
            
            # 4. 총 수익 계산
            total_profit = net_realized_profit + unrealized_profit
            total_profit_rate = (total_profit / baseline_asset * 100) if baseline_asset > 0 else 0
            
            # 5. 계좌 증감
            account_change = current_asset - baseline_asset
            account_change_rate = (account_change / baseline_asset * 100) if baseline_asset > 0 else 0
            
            # 6. 최고/최저 기록 업데이트
            best_rate = perf.get('best_performance_rate', 0)
            worst_rate = perf.get('worst_performance_rate', 0)
            
            if total_profit_rate > best_rate:
                config.set('performance.best_performance_rate', total_profit_rate)
                config.set('performance.best_performance_date', datetime.now().strftime("%Y-%m-%d"))
                best_rate = total_profit_rate
            
            if worst_rate == 0 or total_profit_rate < worst_rate:
                config.set('performance.worst_performance_rate', total_profit_rate)
                config.set('performance.worst_performance_date', datetime.now().strftime("%Y-%m-%d"))
                worst_rate = total_profit_rate
            
            # 7. 오늘 실적 계산 (어제 대비)
            last_report_date = perf.get('last_report_date', '')
            today_date = datetime.now().strftime("%Y-%m-%d")
            
            # 오늘 날짜로 업데이트
            config.set('performance.last_report_date', today_date)
            
            # 8. 리포트 메시지 생성
            today_str = datetime.now().strftime("%Y-%m-%d (%a)")
            
            msg = f"📊 **일일 매매 성과 리포트**\n"
            msg += f"{'━'*30}\n"
            msg += f"📅 {today_str}\n\n"
            
            msg += f"💰 **자산 현황**\n"
            msg += f"• 기준 자산: {baseline_asset:,}원 ({baseline_date} 기준)\n"
            msg += f"• 현재 자산: {current_asset:,}원\n"
            msg += f"• 계좌 증감: {account_change:+,}원 ({account_change_rate:+.2f}%)\n\n"
            
            msg += f"🎯 **실제 봇 성과** (거래 기반)\n"
            msg += f"• 실현 수익: {net_realized_profit:+,}원\n"
            msg += f"• 미실현 수익: {unrealized_profit:+,}원\n"
            msg += f"• 순 수익: {total_profit:+,}원\n"
            msg += f"• 수익률: {total_profit_rate:+.2f}%\n\n"
            
            msg += f"📈 **거래 통계** (누적)\n"
            msg += f"• 총 거래: {total_trades}회\n"
            msg += f"• 수익 거래: {winning_trades}회\n"
            msg += f"• 손실 거래: {losing_trades}회\n"
            msg += f"• 승률: {win_rate:.1f}%\n\n"
            
            msg += f"🏆 **역대 기록**\n"
            best_date = perf.get('best_performance_date', '')
            worst_date = perf.get('worst_performance_date', '')
            
            if best_rate > 0:
                msg += f"• 최고 수익률: {best_rate:+.2f}% ({best_date})\n"
            if worst_rate < 0:
                msg += f"• 최저 수익률: {worst_rate:+.2f}% ({worst_date})\n"
            
            msg += f"\n{'━'*30}\n"
            msg += f"💡 추가 입금 시 config 파일에서\n"
            msg += f"   baseline_asset을 수동 업데이트하세요."

            logger.info("✅ 일일 리포트 생성 완료")
            logger.info(msg)

            # 🔥 수정: use_discord로 변경 + 상세 로그 추가
            if config.get("use_discord", True):
                try:
                    discord_alert.SendMessage(msg)
                    logger.info("✅ Discord 일일 리포트 전송 완료")
                except Exception as discord_e:
                    logger.error(f"❌ Discord 전송 실패: {discord_e}")
            else:
                logger.warning("⚠️ Discord 알림이 비활성화되어 있습니다")

        except Exception as e:
            logger.error(f"일일 리포트 생성 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

################################### Watchdog 핸들러 ##################################

class SignalFileHandler(FileSystemEventHandler):
    """신호 파일 변경 감지 핸들러"""
    
    def __init__(self, bot: SignalTradingBot):
        self.bot = bot
        self.signal_file = os.path.abspath(bot.signal_file)
        logger.info(f"🔍 감시 대상: {self.signal_file}")
    
    def on_modified(self, event):
        """파일 수정 이벤트"""
        if event.is_directory:
            return
        
        if os.path.abspath(event.src_path) == self.signal_file:
            logger.info(f"🔔 신호 파일 변경 감지: {event.src_path}")
            
            # 약간의 지연 (파일 쓰기 완료 대기)
            time.sleep(0.5)
            
            # 신호 처리 실행
            self.bot.process_new_signals()

################################### 메인 실행 ##################################

def main():
    bot_instance = SignalTradingBot()
    
    logger.info("=" * 60)
    logger.info(f"🤖 {BOT_NAME} 시작 v3.0 (watchdog)")
    logger.info("=" * 60)

    # 🔥 실시간 자산 조회
    asset_info = bot_instance.calculate_total_asset()
    
    if not asset_info:
        logger.error("❌ 계좌 정보 조회 실패 - 봇 시작 불가")
        return

    # 🔥 수정: use_discord로 변경
    if config.get("use_discord", True):
        start_msg = f"🚀 **{BOT_NAME} 시작 v3.0**\n"
        start_msg += f"{'─'*30}\n"
        start_msg += f"💰 **현재 자산 현황**\n"
        start_msg += f"• 총 자산: {asset_info['total_asset']:,}원\n"
        start_msg += f"  ├─ 현금: {asset_info['orderable_amt']:,}원\n"
        start_msg += f"  ├─ 보유주: {asset_info['holding_value']:,}원\n"
        start_msg += f"  └─ 미체결: {asset_info['pending_value']:,}원\n"
        start_msg += f"\n⚙️ **운영 설정**\n"
        start_msg += f"• 최소 자산: {config.get('min_asset_threshold', 400000):,}원 (이하 시 매매 중지)\n"
        start_msg += f"• 최대 종목: {config.get('max_positions')}개\n"
        start_msg += f"• watchdog: 실시간 감지 (0초 지연)\n"
        start_msg += f"\n🔥 **동적 자산 관리**\n"
        start_msg += f"• 남은 자산 ÷ 남은 슬롯 = 종목당 예산\n"
        start_msg += f"• 총 자산 기준 실시간 배분\n"
        start_msg += f"• ATR 기반 동적 손절\n"
        start_msg += f"\n📈 **매도 전략**\n"
        start_msg += f"• 목표 수익: +{config.get('target_profit_rate', 0.03)*100:.0f}%\n"
        # start_msg += f"• 일반 트레일링: -{config.get('trailing_stop_rate', 0.01)*100:.0f}%\n"
        start_msg += f"• 일반 트레일링: -{config.get('trailing_stop_rate', 0.01)*100:.1f}%\n"  # ← .0f를 .1f로!
        start_msg += f"• 타이트 트레일링: -{config.get('tight_trailing_rate', 0.005)*100:.1f}% (+3% 달성 시)\n"
        start_msg += f"• 본전 보호: +{config.get('breakeven_protection_rate', 0.02)*100:.0f}% 달성 시\n"
        start_msg += f"• 긴급 손절: {config.get('emergency_stop_loss', -0.03)*100:.0f}%\n"
        start_msg += f"• 쿨다운: {config.get('cooldown_hours')}시간\n"
        start_msg += f"{'─'*30}\n"
        start_msg += "✅ 시스템 준비 완료!"
        
        discord_alert.SendMessage(start_msg)
    
    # 백그라운드 스레드 시작
    bot_instance.start_background_threads()
    
    # watchdog 설정
    event_handler = SignalFileHandler(bot_instance)
    observer = Observer()
    
    # 신호 파일이 있는 디렉토리 감시
    watch_dir = os.path.dirname(os.path.abspath(bot_instance.signal_file)) or "."
    observer.schedule(event_handler, watch_dir, recursive=False)
    observer.start()
    
    logger.info(f"👁️ watchdog 시작 - 디렉토리 감시: {watch_dir}")
    logger.info("⚡ 신호 파일 변경 시 즉시 실행!")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("👋 봇 종료 중...")
        
        observer.stop()
        bot_instance.stop()
        
        observer.join()
        
        if config.get("use_discord", True):
            perf = config.get('performance', {})
            total_trades = perf.get('total_trades', 0)
            winning_trades = perf.get('winning_trades', 0)
            total_profit = perf.get('total_profit', 0)
            canceled_orders = perf.get('canceled_orders', 0)
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            msg = f"👋 **{BOT_NAME} 종료**\n"
            msg += f"📊 총 거래: {total_trades}회\n"
            msg += f"✅ 수익 거래: {winning_trades}회 ({win_rate:.1f}%)\n"
            msg += f"💰 총 수익: {total_profit:+,}원\n"
            msg += f"🚫 취소 주문: {canceled_orders}회"
            
            discord_alert.SendMessage(msg)
        
        logger.info("👋 봇 종료 완료")

if __name__ == "__main__":
    main()