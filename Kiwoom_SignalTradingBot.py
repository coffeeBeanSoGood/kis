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

# 키움 API 초기화 (재시도 로직 추가)
max_init_retry = 3
init_success = False

for init_attempt in range(1, max_init_retry + 1):
    try:
        logger.info("=" * 60)
        logger.info(f"🔧 키움 API 초기화 시도 {init_attempt}/{max_init_retry}")
        logger.info("=" * 60)
        
        # 1. API 객체 생성
        KiwoomAPI = KiwoomKR.Kiwoom_Common(log_level=logging.INFO)
        
        # 2. 설정 파일 로드
        if not KiwoomAPI.LoadConfigData():
            logger.error("❌ 키움 API 설정 로드 실패")
            logger.error("💡 myStockInfo.yaml 파일을 확인하세요")
            if init_attempt < max_init_retry:
                wait_time = 3
                logger.warning(f"⏳ {wait_time}초 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("=" * 60)
                logger.error("❌ 최종 실패: 설정 파일 로드 불가")
                logger.error("=" * 60)
                exit(1)
        
        # 3. 토큰 발급 (GetAccessToken 내부에서 재시도 처리됨)
        if not KiwoomAPI.GetAccessToken():
            logger.error(f"❌ 키움 API 토큰 발급 실패 (시도 {init_attempt}/{max_init_retry})")
            if init_attempt < max_init_retry:
                wait_time = 5
                logger.warning(f"⏳ {wait_time}초 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("=" * 60)
                logger.error("❌ 최종 실패: 토큰 발급 불가")
                logger.error("=" * 60)
                exit(1)
        
        # 4. 초기화 성공
        logger.info("=" * 60)
        logger.info(f"✅ 키움 API 초기화 성공 (시도 {init_attempt}회)")
        logger.info("=" * 60)
        init_success = True
        break  # 성공하면 루프 탈출
        
    except Exception as e:
        logger.error(f"❌ 키움 API 초기화 중 예외 발생 (시도 {init_attempt}/{max_init_retry})")
        logger.error(f"예외 내용: {str(e)}")
        
        if init_attempt < max_init_retry:
            wait_time = 5
            logger.warning(f"⏳ {wait_time}초 후 재시도...")
            time.sleep(wait_time)
        else:
            logger.error("=" * 60)
            logger.error("❌ 최종 실패: 예외 발생으로 초기화 불가")
            logger.error("=" * 60)
            import traceback
            logger.error(traceback.format_exc())
            exit(1)

# 초기화 실패 시 종료
if not init_success:
    logger.error("=" * 60)
    logger.error("❌ 키움 API 초기화 최종 실패 - 봇 종료")
    logger.error("=" * 60)
    exit(1)

################################### 설정 관리 (3개 파일 분리) ##################################

class ConfigManager:
    """
    통합 설정 관리자 (3개 파일 분리)
    - signal_trading_config.json: 매매 전략 설정
    - signal_trading_budget.json: 투자 예산 설정
    - signal_trading_performance.json: 성과 추적 데이터
    """

    def __init__(self, 
                 config_file='signal_trading_config.json',
                 budget_file='signal_trading_budget.json',
                 performance_file='signal_trading_performance.json'):
        
        self.config_file = config_file
        self.budget_file = budget_file
        self.performance_file = performance_file
        
        # 각 파일 로드
        self.config = self.load_config()
        self.budget_config = self.load_budget()
        self.performance_config = self.load_performance()
        
        # 기본값으로 업그레이드
        self._upgrade_config_if_needed()

    # ============================================
    # 기본 설정값 (3개 파일 분리)
    # ============================================

    @property
    def default_config(self):
        """매매 전략 기본값"""
        return {
            "bot_name": "SignalTradingBot_Kiwoom",
            "use_discord": True,
            
            # 매수 설정
            "buy_signals": ["STRONG_BUY", "CONFIRMED_BUY"],
            "signal_validity_minutes": 10,
            "buy_cutoff_time": "14:50",
            "min_signal_confidence": 0.4,
            
            # 매도 설정
            "sell_signals": ["SELL", "STRONG_SELL"],
            "target_profit_rate": 0.025,
            "breakeven_protection_rate": 0.015,
            "tight_trailing_threshold": 0.020,
            "tight_trailing_rate": 0.002,
            
            # ⚠️ 여기 수정 필요!
            "trailing_stop_rate": 0.003,              # 🔥 0.005로 변경!
            "min_profit_for_trailing": 0.006,         # 🔥 0.008로 변경!
            "ultra_tight_trailing_rate": 0.0005,      # 🆕 추가 필요!
            
            # 🆕 기술적 지표 설정 (전체 추가 필요!)
            "use_technical_trailing": True,
            "technical_indicators": {
                "use_rsi": True,
                "use_bollinger": True,
                "use_ma": True,
                "use_volume": True,
                
                "rsi_weight": 30,
                "bollinger_weight": 30,
                "ma_weight": 20,
                "volume_weight": 20,
                
                "rsi_period": 14,
                "bollinger_period": 20,
                "bollinger_std": 2,
                "ma_short_period": 5,
                "ma_long_period": 20
            },
            
            "technical_multiplier": {
                "strong_bull": 2.0,
                "bull": 1.3,
                "neutral": 1.0,
                "bear": 0.7,
                "strong_bear": 0.4
            },
            
            # 🆕 신호 기반 트레일링 유예 (전체 추가 필요!)
            "trailing_signal_override": True,
            "trailing_override_confidence": 0.6,
            "trailing_override_signals": ["STRONG_BUY", "CONFIRMED_BUY", "BUY"],
            "trailing_override_max_loss": 0.005,
            
            # 손절 설정
            "emergency_stop_loss": -0.03,
            "stop_loss_grace_period_minutes": 10,
            "extreme_stop_loss": -0.05,
            "atr_stop_multiplier": 2.0,
            "atr_min_stop_loss": 0.02,
            "atr_max_stop_loss": 0.08,
            "signal_override_buffer": 0.02,
            
            # 기타 설정
            "commission_rate": 0.004,
            "pending_order_timeout_minutes": 10,
            "check_pending_interval_seconds": 30,
            "check_position_interval_seconds": 60,
            "cooldown_hours": 8,
            
            # 파일 경로
            "signal_file": "signal_history.json",
            "positions_file": "trading_positions.json",
            "pending_orders_file": "trading_pending_orders.json",
            "cooldowns_file": "trading_cooldowns.json"
        }
    
    @property
    def default_budget(self):
        """예산 설정 기본값"""
        return {
            "min_asset_threshold": 400000,
            "max_positions": 2,
            "baseline_asset": 500000,
            "baseline_date": datetime.now().strftime("%Y-%m-%d"),
            "baseline_note": "추가 입금/출금 시 자동으로 업데이트됩니다",
            
            # 🆕 입출금 자동 감지 설정
            "auto_deposit_check": True,              # 자동 감지 활성화
            "deposit_check_interval_hours": 24,      # 점검 주기 (시간)
            "deposit_check_time": "09:05",           # 점검 시각 (HH:MM)
            "last_deposit_check_date": "",           # 마지막 점검일 (YYYYMMDD)
            
            # 입출금 이력
            "deposit_withdraw_history": []
        }

    @property
    def default_performance(self):
        """성과 추적 기본값"""
        return {
            # 자동 계산
            "total_realized_profit": 0,
            "total_realized_loss": 0,
            "net_realized_profit": 0,
            
            # 거래 통계
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "canceled_orders": 0,
            "win_rate": 0.0,
            
            # 최고/최저 기록
            "best_performance_rate": 0.0,
            "best_performance_date": "",
            "worst_performance_rate": 0.0,
            "worst_performance_date": "",
            
            # 일일 기록
            "last_report_date": "",
            "start_date": datetime.now().strftime("%Y-%m-%d")
        }

    # ============================================
    # 파일 로드/저장
    # ============================================
    
    def load_config(self):
        """매매 전략 설정 로드"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"설정 로드 실패: {e}")
            return {}
    
    def load_budget(self):
        """투자 예산 설정 로드"""
        try:
            if os.path.exists(self.budget_file):
                with open(self.budget_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"예산 설정 로드 실패: {e}")
            return {}
    
    def load_performance(self):
        """성과 추적 데이터 로드"""
        try:
            if os.path.exists(self.performance_file):
                with open(self.performance_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"성과 데이터 로드 실패: {e}")
            return {}
    
    def save_config(self):
        """매매 전략 설정 저장"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.debug("✅ 매매 전략 설정 저장 완료")
        except Exception as e:
            logger.error(f"설정 저장 실패: {e}")
    
    def save_budget(self):
        """투자 예산 설정 저장"""
        try:
            with open(self.budget_file, 'w', encoding='utf-8') as f:
                json.dump(self.budget_config, f, ensure_ascii=False, indent=2)
            logger.debug("✅ 예산 설정 저장 완료")
        except Exception as e:
            logger.error(f"예산 설정 저장 실패: {e}")
    
    def save_performance(self):
        """성과 추적 데이터 저장"""
        try:
            with open(self.performance_file, 'w', encoding='utf-8') as f:
                json.dump(self.performance_config, f, ensure_ascii=False, indent=2)
            logger.debug("✅ 성과 데이터 저장 완료")
        except Exception as e:
            logger.error(f"성과 데이터 저장 실패: {e}")

    def reload_all(self):
        """
        모든 설정 파일 재로드
        config, budget, performance 파일을 모두 다시 읽어옴
        """
        try:
            self.config = self.load_config()
            self.budget_config = self.load_budget()
            self.performance_config = self.load_performance()
            logger.info("✅ 모든 설정 파일 재로드 완료 (config + budget + performance)")
        except Exception as e:
            logger.error(f"설정 파일 재로드 실패: {e}")

    # ============================================
    # 초기화 및 업그레이드
    # ============================================
    
    def _upgrade_config_if_needed(self):
        """설정 파일 자동 업그레이드"""
        is_modified = False
        
        # 1. 매매 전략 설정 업그레이드
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
                is_modified = True
        
        if is_modified:
            self.save_config()
            logger.info("📝 매매 전략 설정 업그레이드 완료")
        
        # 2. 예산 설정 업그레이드
        is_modified = False
        for key, value in self.default_budget.items():
            if key not in self.budget_config:
                self.budget_config[key] = value
                is_modified = True
        
        if is_modified:
            self.save_budget()
            logger.info("📝 예산 설정 업그레이드 완료")
        
        # 3. 성과 데이터 업그레이드
        is_modified = False
        for key, value in self.default_performance.items():
            if key not in self.performance_config:
                self.performance_config[key] = value
                is_modified = True
        
        if is_modified:
            self.save_performance()
            logger.info("📝 성과 데이터 업그레이드 완료")

    # ============================================
    # 통합 접근 메서드
    # ============================================
    
    def get(self, key, default=None):
        """
        설정값 가져오기 (3개 파일 모두 검색)
        우선순위: config > budget > performance
        """
        # 1. 매매 전략에서 찾기
        if key in self.config:
            return self.config[key]
        
        # 2. 예산 설정에서 찾기
        if key in self.budget_config:
            return self.budget_config[key]
        
        # 3. 성과 데이터에서 찾기 (performance.xxx 형식 지원)
        if key.startswith('performance.'):
            perf_key = key.replace('performance.', '')
            
            # baseline 관련은 budget에서 찾기
            if perf_key in ['baseline_asset', 'baseline_date', 'baseline_note']:
                return self.budget_config.get(perf_key, default)
            
            # 나머지는 performance에서 찾기
            if perf_key in self.performance_config:
                return self.performance_config[perf_key]
        
        # performance 전체 요청 시 budget의 baseline 포함
        if key == 'performance':
            result = self.performance_config.copy()
            # baseline 정보를 budget에서 가져와 추가
            result['baseline_asset'] = self.budget_config.get('baseline_asset', 500000)
            result['baseline_date'] = self.budget_config.get('baseline_date', '')
            result['baseline_note'] = self.budget_config.get('baseline_note', '')
            return result
        
        # 4. 기본값 반환
        return default
    
    def set(self, key, value):
        """
        설정값 저장 (적절한 파일에 자동 저장)
        """
        # performance.xxx 형식이면 적절한 파일에 저장
        if key.startswith('performance.'):
            perf_key = key.replace('performance.', '')
            
            # baseline 관련은 budget 파일에 저장
            if perf_key in ['baseline_asset', 'baseline_date', 'baseline_note']:
                self.budget_config[perf_key] = value
                self.save_budget()
                return
            
            # 나머지는 performance 파일에 저장
            self.performance_config[perf_key] = value
            self.save_performance()
            return
        
        # performance면 전체 성과 데이터 교체
        if key == 'performance':
            # baseline은 budget으로 분리
            if 'baseline_asset' in value:
                self.budget_config['baseline_asset'] = value['baseline_asset']
            if 'baseline_date' in value:
                self.budget_config['baseline_date'] = value['baseline_date']
            if 'baseline_note' in value:
                self.budget_config['baseline_note'] = value['baseline_note']
            
            # baseline 제거 후 performance에 저장
            perf_value = {k: v for k, v in value.items() 
                         if k not in ['baseline_asset', 'baseline_date', 'baseline_note']}
            self.performance_config = perf_value
            
            self.save_budget()
            self.save_performance()
            return
        
        # 예산 관련 키면 예산 파일에 저장
        if key in ['min_asset_threshold', 'max_positions', 'baseline_asset', 'baseline_date', 'baseline_note']:
            self.budget_config[key] = value
            self.save_budget()
            return
        
        # 그 외는 매매 전략 설정에 저장
        self.config[key] = value
        self.save_config()
    
    # ============================================
    # 성과 추적 전용 메서드
    # ============================================
    
    def update_performance(self, metric, value):
        """
        성과 메트릭 업데이트
        
        Args:
            metric: 메트릭 이름 (예: 'net_realized_profit', 'total_trades')
            value: 설정할 값 또는 증가시킬 값
        """
        if isinstance(value, (int, float)):
            # 숫자면 기존 값에 더하기
            current = self.performance_config.get(metric, 0)
            self.performance_config[metric] = current + value
        else:
            # 그 외는 값 교체
            self.performance_config[metric] = value
        
        self.save_performance()

    def add_deposit_withdraw_history(self, date, time, tx_type, amount, depositor=""):
        """
        입출금 이력 추가
        
        Args:
            date: 거래일자 (YYYYMMDD)
            time: 처리시간 (HH:MM:SS)
            tx_type: deposit or withdraw
            amount: 금액
            depositor: 입금자 (선택)
        """
        history = self.budget_config.get('deposit_withdraw_history', [])
        
        history.append({
            'date': date,
            'time': time,
            'type': tx_type,
            'amount': amount,
            'depositor': depositor,
            'timestamp': datetime.now().isoformat()
        })
        
        # 최근 100개만 유지 (너무 많아지면 파일 비대화 방지)
        if len(history) > 100:
            history = history[-100:]
        
        self.budget_config['deposit_withdraw_history'] = history
        self.save_budget()
        
        logger.info(f"✅ 입출금 이력 추가: {tx_type} {amount:,}원 ({date} {time})")

    def get_deposit_withdraw_summary(self, days=30):
        """
        최근 N일 입출금 요약
        
        Args:
            days: 조회 기간 (일)
        
        Returns:
            dict: {
                'total_deposits': 총 입금액,
                'total_withdraws': 총 출금액,
                'net_change': 순 변동,
                'count': 거래 건수
            }
        """
        history = self.budget_config.get('deposit_withdraw_history', [])
        
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        total_deposits = 0
        total_withdraws = 0
        count = 0
        
        for h in history:
            if h.get('date', '') >= cutoff_date:
                count += 1
                if h['type'] == 'deposit':
                    total_deposits += h['amount']
                else:
                    total_withdraws += h['amount']
        
        return {
            'total_deposits': total_deposits,
            'total_withdraws': total_withdraws,
            'net_change': total_deposits - total_withdraws,
            'count': count
        }

    def get_performance(self, metric, default=None):
        """성과 메트릭 가져오기"""
        return self.performance_config.get(metric, default)
    
    def set_performance(self, metric, value):
        """성과 메트릭 직접 설정"""
        self.performance_config[metric] = value
        self.save_performance()

# 전역 설정 인스턴스
config = ConfigManager()
BOT_NAME = config.get("bot_name", "SignalTradingBot_Kiwoom")

logger.info("=" * 60)
logger.info(f"🤖 {config.get('bot_name')} 초기화 v3.0 (3개 파일 분리)")
logger.info(f"⚠️ 최소 자산: {config.get('min_asset_threshold', 400000):,}원")
logger.info(f"📊 최대 종목: {config.get('max_positions')}개")
logger.info("=" * 60)
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

            # 🔥🔥🔥 [여기부터 추가] 우선순위 정렬 로직 🔥🔥🔥
            logger.info("")
            logger.info("=" * 80)
            logger.info("🎯 신호 우선순위 정렬 중...")
            logger.info("=" * 80)

            # 정렬 함수
            def get_signal_priority(signal):
                """
                신호 우선순위 계산
                
                우선순위:
                1. 신호 타입 (CONFIRMED_BUY > STRONG_BUY)
                2. 점수 (높을수록 우선)
                3. 신뢰도 (높을수록 우선)
                4. 시간 (최신 우선)
                
                Returns:
                    tuple: (신호타입순위, 점수, 신뢰도, 시간)
                """
                signal_type = signal.get('signal', '')
                score = signal.get('score', 0)
                confidence = signal.get('confidence', 0)
                timestamp = signal.get('timestamp', '')
                
                # 신호 타입 우선순위 (숫자가 클수록 우선)
                type_priority = {
                    'CONFIRMED_BUY': 100,  # 3회 연속 검증된 신호 - 최우선
                    'STRONG_BUY': 90       # 강력 매수 신호
                }
                
                type_score = type_priority.get(signal_type, 0)
                
                return (
                    type_score,      # 1순위: 신호 타입 (CONFIRMED_BUY 우선)
                    score,           # 2순위: 점수 (높을수록 우선)
                    confidence,      # 3순위: 신뢰도 (높을수록 우선)
                    timestamp        # 4순위: 시간 (최신 우선)
                )

            # 우선순위 정렬 (높은 우선순위 → 낮은 우선순위)
            buy_signals_sorted = sorted(
                buy_signals,
                key=get_signal_priority,
                reverse=True
            )

            # 정렬 결과 로그 출력
            logger.info("📊 우선순위 정렬 결과:")
            for idx, signal in enumerate(buy_signals_sorted, 1):
                stock_name = signal.get('stock_name', '')
                signal_type = signal.get('signal', '')
                score = signal.get('score', 0)
                confidence = signal.get('confidence', 0)
                
                priority_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "📌"
                
                logger.info(f"  {priority_emoji} {idx}순위: [{stock_name}]")
                logger.info(f"     신호: {signal_type}, 점수: {score:.1f}, 신뢰도: {confidence*100:.0f}%")

            logger.info("=" * 80)
            logger.info("")

            # 🔥🔥🔥 [여기까지 추가] 🔥🔥🔥

            # 5️⃣ 각 매수 신호 처리(정렬된 순서대로)
            processed_count = 0
            
            for signal in buy_signals_sorted:
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
                    timeout=40,
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
            
            with self.lock:
                current_positions = len(self.positions)
                current_pending = len(self.pending_orders)
            
            occupied_slots = current_positions + current_pending
            remaining_slots = max_positions - occupied_slots
            
            logger.info(f"📊 슬롯 현황:")
            logger.info(f"   최대 슬롯: {max_positions}개")
            logger.info(f"   사용 중: {occupied_slots}개 (보유: {current_positions}, 미체결: {current_pending})")
            logger.info(f"   남은 슬롯: {remaining_slots}개")
            
            if remaining_slots <= 0:
                logger.warning(f"❌ 슬롯 부족")
                return False

            # 🔥🔥🔥 3️⃣ 동적 예산 계산 (현금만 사용)
            budget_per_stock = orderable_amt / remaining_slots

            logger.info(f"💵 예산 배분:")
            logger.info(f"   종목당 예산: {budget_per_stock:,.0f}원 (사용가능 현금 {orderable_amt:,}원 ÷ 남은 슬롯 {remaining_slots}개)")
            logger.info(f"   💡 보유주식({holding_value:,}원)과 미체결({pending_value:,}원)은 예산 계산에서 제외")

            # 🔥 4️⃣ 현재가 조회 및 호가 조정
            try:
                stock_info = call_with_timeout(
                    KiwoomAPI.GetStockInfo,
                    timeout=10,
                    stock_code=stock_code
                )
            except TimeoutError:
                logger.error(f"❌ 현재가 조회 타임아웃")
                return False
            
            if not stock_info:
                logger.error(f"❌ 현재가 조회 실패")
                return False
            
            current_price = stock_info.get('CurrentPrice', 0)
            
            # 호가 단위 적용 (매수: 내림)
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
                        'original_price': adjusted_price,  # 🔥 추가: 최초 지정가 저장
                        'order_quantity': buy_quantity,
                        'order_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'pending',
                        'retry_count': 0,
                        'signal': signal.get('signal', ''),  # 🔥 추가: 신호 타입 저장
                        'signal_score': signal.get('score', 0),
                        'signal_confidence': signal.get('confidence', 0)
                    }
                
                self.save_pending_orders()
                
                # 매수 후 남은 슬롯
                new_remaining_slots = remaining_slots - 1
                
                # 남은 자산
                remaining_asset = total_asset - actual_investment
                
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
        - 🔥 지정가 고수 전략: 재주문 시 원래 지정가 유지
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
                        logger.info(f"   체결가: {filled_price:,}원 × {filled_qty}주")
                        logger.info(f"   수수료: {commission:,}원, 세금: {tax:,}원")
                        
                        # 주문가와 체결가 차이 로그
                        price_diff = filled_price - pending['order_price']
                        if price_diff != 0:
                            emoji = "💰" if price_diff > 0 else "📊"
                            logger.info(f"   {emoji} 체결가-주문가: {price_diff:+,}원")

                        # 매수 체결 처리
                        if order_type == 'buy':
                            # 🔥 목표 수익 가격 계산
                            target_profit_rate = config.get("target_profit_rate", 0.03)
                            target_profit_price = int(filled_price * (1 + target_profit_rate))
                            
                            # 🔥 본전 보호 가격 계산 (수수료 포함)
                            commission_rate = config.get("commission_rate", 0.00015)
                            tax_rate = config.get("tax_rate", 0.0)
                            total_cost_rate = commission_rate * 2 + tax_rate
                            breakeven_price = int(filled_price * (1 + total_cost_rate))
                            
                            with self.lock:
                                self.positions[stock_code] = {
                                    'stock_name': stock_name,
                                    'quantity': filled_qty,
                                    'entry_price': filled_price,
                                    'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'highest_price': filled_price,
                                    'trailing_stop_price': breakeven_price,  # 🔥 초기값: 본전 가격
                                    'target_profit_price': target_profit_price,  # 🔥 추가!
                                    'breakeven_price': breakeven_price,  # 🔥 추가!
                                    'breakeven_protected': False,
                                    'tight_trailing_active': False,
                                    'signal': pending.get('signal', ''),
                                    'score': pending.get('signal_score', 0)
                                }
                                
                                del self.pending_orders[stock_code]

                            self.save_positions()
                            self.save_pending_orders()
                            
                            msg = f"✅ **매수 체결!**\n"
                            msg += f"종목: {stock_name} ({stock_code})\n"
                            msg += f"주문번호: {order_no}\n"
                            msg += f"체결가: {filled_price:,}원 × {filled_qty}주\n"
                            if price_diff != 0:
                                emoji2 = "💰" if price_diff > 0 else "📊"
                                msg += f"{emoji2} 주문가: {pending['order_price']:,}원 ({price_diff:+,}원)\n"
                            msg += f"투자금: {filled_price * filled_qty:,}원"
                            
                            logger.info(msg)
                            
                            if config.get("use_discord", True):
                                discord_alert.SendMessage(msg)
                            
                            continue
                        
                        # 매도 체결 처리
                        else:  # sell
                            entry_price = pending.get('entry_price', 0)
                            profit = (filled_price - entry_price) * filled_qty - commission - tax
                            profit_rate = (filled_price - entry_price) / entry_price if entry_price > 0 else 0
                            
                            # 성과 업데이트
                            config.update_performance('total_realized_profit', profit)
                            config.update_performance('net_realized_profit', profit)
                            
                            total_trades = config.get('performance.total_trades', 0) + 1
                            config.set('performance.total_trades', total_trades)
                            
                            if profit > 0:
                                winning_trades = config.get('performance.winning_trades', 0) + 1
                                config.set('performance.winning_trades', winning_trades)
                            else:
                                losing_trades = config.get('performance.losing_trades', 0) + 1
                                config.set('performance.losing_trades', losing_trades)
                            
                            # 승률 계산
                            winning_trades = config.get('performance.winning_trades', 0)
                            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                            config.set('performance.win_rate', win_rate)
                            
                            # 쿨다운 등록
                            cooldown_hours = config.get("cooldown_hours", 8)
                            cooldown_until = (datetime.now() + timedelta(hours=cooldown_hours)).strftime("%Y-%m-%d %H:%M:%S")
                            
                            net_profit = config.get('performance.net_realized_profit', 0)
                            
                            with self.lock:
                                self.cooldowns[stock_code] = {
                                    'stock_name': stock_name,
                                    'cooldown_until': cooldown_until,
                                    'reason': pending.get('sell_reason', ''),
                                    'profit': profit,
                                    'profit_rate': profit_rate
                                }
                                
                                if stock_code in self.positions:
                                    del self.positions[stock_code]
                                
                                del self.pending_orders[stock_code]
                            
                            self.save_positions()
                            self.save_cooldowns()
                            self.save_pending_orders()
                            
                            msg = f"💸 **매도 체결!**\n"
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
                    
                    else:
                        # 🔥🔥🔥 재주문 시도 (지정가 고수 전략) 🔥🔥🔥
                        logger.info(f"🔄 {stock_name} 재주문 시도 ({retry_count + 1}/{max_retry})")
                        logger.info(f"   💡 전략: 지정가 고수 (원래 지정가 유지)")
                        
                        # 🔥 원래 지정가 사용 (현재가 조회 없음!)
                        original_price = pending.get('original_price')
                        
                        if not original_price:
                            # 하위 호환성: original_price 없으면 order_price 사용
                            original_price = pending.get('order_price', 0)
                            logger.warning(f"   ⚠️ original_price 없음 - order_price 사용: {original_price:,}원")
                        
                        if original_price <= 0:
                            logger.error(f"❌ {stock_name} 유효하지 않은 주문가 - 재주문 스킵")
                            continue
                        
                        # 🔥 원래 지정가로 재주문 (상향 조정 없음!)
                        adjusted_price = original_price
                        quantity = pending.get('order_quantity', 0)
                        
                        logger.info(f"   📊 재주문 가격: {adjusted_price:,}원 (최초 지정가 유지)")
                        
                        # 기존 주문 취소
                        logger.info(f"   1️⃣ 기존 주문 취소 중...")

                        try:
                            cancel_result = call_with_timeout(
                                KiwoomAPI.CancelOrder,
                                timeout=10,
                                original_order_no=order_no,   # ✅ 올바른 파라미터명
                                stock_code=stock_code
                            )
                        except TimeoutError:
                            logger.error(f"   ❌ 주문 취소 타임아웃 - 재주문 스킵")
                            continue
                        
                        if not cancel_result:
                            logger.warning(f"   ⚠️ 기존 주문 취소 실패 - 재주문 스킵")
                            continue
                        
                        logger.info(f"   ✅ 기존 주문 취소 완료")
                        
                        # 재주문
                        logger.info(f"   2️⃣ 재주문 실행 중...")
                        logger.info(f"      가격: {adjusted_price:,}원 (최초 지정가)")
                        logger.info(f"      수량: {quantity}주")
                        
                        try:
                            if order_type == 'buy':
                                new_order_result = call_with_timeout(
                                    KiwoomAPI.MakeBuyLimitOrder,
                                    timeout=10,
                                    stock_code=stock_code,
                                    quantity=quantity,
                                    price=adjusted_price  # 🔥 원래 지정가!
                                )
                            else:  # sell
                                new_order_result = call_with_timeout(
                                    KiwoomAPI.MakeSellLimitOrder,
                                    timeout=10,
                                    stock_code=stock_code,
                                    quantity=quantity,
                                    price=adjusted_price  # 🔥 원래 지정가!
                                )
                        except TimeoutError:
                            logger.error(f"   ❌ 재주문 타임아웃")
                            continue

                        if new_order_result and new_order_result.get('success'):
                            new_order_no = new_order_result.get('order_no', '')
                            
                            with self.lock:
                                self.pending_orders[stock_code]['order_no'] = new_order_no
                                self.pending_orders[stock_code]['order_price'] = adjusted_price
                                # 🔥 original_price는 유지! (변경 안 함)
                                # 🔥🔥🔥 order_time도 유지! (최초 주문 시간 기준으로 타임아웃 체크)
                                # self.pending_orders[stock_code]['order_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # ← 삭제!
                                self.pending_orders[stock_code]['retry_count'] = retry_count + 1
                                
                                # 매도인 경우 예상 수익 재계산
                                if order_type == 'sell':
                                    entry_price = pending['entry_price']
                                    profit = (adjusted_price - entry_price) * quantity
                                    profit_rate = (adjusted_price - entry_price) / entry_price if entry_price > 0 else 0
                                    self.pending_orders[stock_code]['expected_profit'] = profit
                                    self.pending_orders[stock_code]['expected_profit_rate'] = profit_rate
                            
                            self.save_pending_orders()
                            
                            logger.info(f"   ✅ {stock_name} 재주문 완료")
                            logger.info(f"      새 주문번호: {new_order_no}")
                            logger.info(f"      유지된 가격: {adjusted_price:,}원")
                            logger.info(f"      재시도 횟수: {retry_count + 1}/{max_retry}")
                            logger.info(f"      💡 최초 주문 시간 유지 → 타임아웃 누적 계산")  # 🆕 추가

                        else:
                            logger.error(f"   ❌ {stock_name} 재주문 실패")
            
        except Exception as e:
            logger.error(f"미체결 주문 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def update_trailing_stop(self, stock_code):
        """
        트레일링 스탑 업데이트 (기술적 지표 결합)
        
        🔥 완전한 수익보호 시스템:
        1. 수익률 기반 기본 트레일링 간격 결정
        2. 기술적 지표로 간격 동적 조정
        3. 본전 보호 적용
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
            
            # 트레일링 활성화 체크 (0.8%)
            min_profit_for_trailing = config.get("min_profit_for_trailing", 0.008)
            if profit_rate < min_profit_for_trailing:
                logger.debug(f"  ⏸️ {stock_code} 트레일링 대기: 수익률 {profit_rate*100:+.2f}% < {min_profit_for_trailing*100:.1f}%")
                return
            
            # 🔥🔥🔥 수수료 반영한 진짜 본전 가격
            commission_rate = config.get("commission_rate", 0.004)
            breakeven_price = int(entry_price * (1 + commission_rate))
            
            # 플래그 가져오기
            breakeven_protected = position.get('breakeven_protected', False)
            tight_trailing_active = position.get('tight_trailing_active', False)
            ultra_tight_active = position.get('ultra_tight_active', False)
            
            # 🆕 4단계: 울트라 타이트 활성화 (2.5% 달성)
            target_profit = config.get("target_profit_rate", 0.025)
            
            if not ultra_tight_active and profit_rate >= target_profit:
                with self.lock:
                    self.positions[stock_code]['ultra_tight_active'] = True
                    ultra_rate = config.get("ultra_tight_trailing_rate", 0.0005)
                    new_trailing_stop = highest_price * (1 - ultra_rate)
                    new_trailing_stop = max(breakeven_price, int(new_trailing_stop))
                    self.positions[stock_code]['trailing_stop_price'] = new_trailing_stop
                
                self.save_positions()
                
                logger.info(f"🚀 {stock_code} 울트라 타이트 트레일링! (수익률: {profit_rate*100:+.2f}%)")
                logger.info(f"   최고가: {highest_price:,}원")
                logger.info(f"   트레일링: {new_trailing_stop:,}원 (-0.05%)")
                logger.info(f"   💡 목표 달성! 이제 0.05%만 떨어져도 매도")
                
                if config.get("use_discord", True):
                    stock_name = position.get('stock_name', stock_code)
                    msg = f"🚀 **울트라 타이트 모드!**\n"
                    msg += f"종목: {stock_name} ({stock_code})\n"
                    msg += f"목표 수익: {profit_rate*100:+.2f}% 달성!\n"
                    msg += f"최고가: {highest_price:,}원\n"
                    msg += f"트레일링: {new_trailing_stop:,}원 (-0.05%)\n"
                    msg += f"💎 고점 추적 중..."
                    discord_alert.SendMessage(msg)
            
            # 3단계: 타이트 트레일링 (2.0% 달성)
            tight_threshold = config.get("tight_trailing_threshold", 0.020)
            
            if not tight_trailing_active and profit_rate >= tight_threshold:
                with self.lock:
                    self.positions[stock_code]['tight_trailing_active'] = True
                    tight_rate = config.get("tight_trailing_rate", 0.002)
                    new_trailing_stop = highest_price * (1 - tight_rate)
                    new_trailing_stop = max(breakeven_price, int(new_trailing_stop))
                    self.positions[stock_code]['trailing_stop_price'] = new_trailing_stop
                
                self.save_positions()
                
                logger.info(f"🎯 {stock_code} 타이트 트레일링! (수익률: {profit_rate*100:+.2f}%)")
                logger.info(f"   최고가: {highest_price:,}원")
                logger.info(f"   트레일링: {new_trailing_stop:,}원 (-0.2%)")
            
            # 2단계: 본전 보호 (1.5% 달성)
            breakeven_threshold = config.get("breakeven_protection_rate", 0.015)
            
            if not breakeven_protected and profit_rate >= breakeven_threshold:
                with self.lock:
                    self.positions[stock_code]['breakeven_protected'] = True
                    self.positions[stock_code]['trailing_stop_price'] = breakeven_price
                
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
            
            # 🔥 최고가 갱신 시 트레일링 업데이트
            if current_price == highest_price:
                logger.info(f"    ┌─ 트레일링 업데이트 ─┐")
                logger.info(f"    │ 최고가 갱신: {highest_price:,}원")
                
                # 1️⃣ 수익률 기반 기본 간격 결정
                if ultra_tight_active:
                    base_rate = config.get("ultra_tight_trailing_rate", 0.0005)
                    stage = "울트라 타이트 (2.5% 이상)"
                elif tight_trailing_active:
                    base_rate = config.get("tight_trailing_rate", 0.002)
                    stage = "타이트 (2.0~2.5%)"
                elif breakeven_protected:
                    base_rate = config.get("trailing_stop_rate", 0.005)
                    stage = "본전보호 (1.5~2.0%)"
                else:
                    base_rate = config.get("trailing_stop_rate", 0.005)
                    stage = "일반 (0.8~1.5%)"
                
                logger.info(f"    │ 수익 단계: {stage}")
                logger.info(f"    │ 기본 간격: {base_rate*100:.2f}%")
                
                # 2️⃣ 기술적 지표로 간격 조정
                use_technical = config.get("use_technical_trailing", True)
                
                if use_technical:
                    logger.info(f"    │")
                    logger.info(f"    │ 🔬 기술적 지표 분석 시작...")
                    
                    minute_data = KiwoomAPI.GetMinuteData(stock_code, count=25)
                    
                    if minute_data and len(minute_data) >= 20:
                        technical_score = self._calculate_technical_score(stock_code, minute_data)
                        multiplier = self._get_technical_multiplier(technical_score)
                        
                        adjusted_rate = base_rate * multiplier
                        
                        logger.info(f"    │")
                        logger.info(f"    │ 최종 간격: {base_rate*100:.2f}% × {multiplier:.1f} = {adjusted_rate*100:.3f}%")
                    else:
                        logger.warning(f"    │ ⚠️ 분봉 데이터 부족 → 기본 간격 사용")
                        adjusted_rate = base_rate
                else:
                    logger.info(f"    │ 기술적 지표 미사용 → 기본 간격")
                    adjusted_rate = base_rate
                
                # 3️⃣ 트레일링 스탑 계산
                new_trailing_stop = highest_price * (1 - adjusted_rate)
                
                # 본전 이하로 절대 안 내려감
                new_trailing_stop = max(breakeven_price, int(new_trailing_stop))
                
                with self.lock:
                    self.positions[stock_code]['trailing_stop_price'] = new_trailing_stop
                
                self.save_positions()
                
                trailing_profit = (new_trailing_stop - entry_price) / entry_price
                
                logger.info(f"    │")
                logger.info(f"    │ ✅ 트레일링 업데이트 완료")
                logger.info(f"    │ 새 손절선: {new_trailing_stop:,}원")
                logger.info(f"    │ 보장 수익: {trailing_profit*100:+.2f}%")
                logger.info(f"    └─────────────────────┘")
            
        except Exception as e:
            logger.error(f"트레일링 스탑 업데이트 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def check_sell_conditions(self, stock_code, current_signal=None):
        """
        매도 조건 체크 (완전한 수익보호 시스템)
        
        우선순위:
        1. 트레일링 스탑 발동 (기술적 지표 + 신호 유예)
        2. 손절 신호 (SELL/STRONG_SELL)
        3. 긴급 손절 (-3%)
        4. ATR 기반 동적 손절
        
        ⚠️ 목표 수익 즉시 매도 제거! (울트라 타이트 트레일링으로 대체)
        
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

            # 🔥 0️⃣ 유예 기간 체크 (맨 앞으로 이동!)
            logger.info(f"    │ [0/6] 유예 기간 체크")
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
                    logger.info(f"    │   → 유예 기간까지 대기 ({grace_period_minutes - holding_minutes:.0f}분 남음)")
                    logger.info(f"    └─────────────────────┘")
                    return False, f"유예 중 ({holding_minutes:.0f}분/{grace_period_minutes}분)"

            logger.info(f"    │   ✅ 유예 완료: {holding_minutes:.0f}분 >= {grace_period_minutes}분")

            # ❌ 목표 수익 체크 제거!
            # 울트라 타이트 트레일링으로 대체됨
            # logger.info(f"    │ [1/6] 목표 수익 체크")
            # if current_price >= target_profit_price:
            #     return True, "목표 수익 달성"

            # 🔥 1️⃣ 트레일링 스탑 체크 (우선순위 상향!)
            logger.info(f"    │ [1/6] 트레일링 스탑 체크")

            if current_price <= trailing_stop_price:
                trailing_loss = (trailing_stop_price - current_price) / current_price
                
                logger.info(f"    │   ⚠️ 트레일링 도달!")
                logger.info(f"    │   현재가: {current_price:,}원 <= 손절선: {trailing_stop_price:,}원")
                logger.info(f"    │   최고가: {highest_price:,}원 → 현재가: {current_price:,}원")
                
                # 🆕 신호 기반 트레일링 유예 체크
                use_signal_override = config.get("trailing_signal_override", True)
                
                if use_signal_override and current_signal:
                    signal_type = current_signal.get('signal', 'HOLD')
                    signal_confidence = current_signal.get('confidence', 0)
                    override_confidence = config.get("trailing_override_confidence", 0.6)
                    override_signals = config.get("trailing_override_signals", ["STRONG_BUY", "CONFIRMED_BUY", "BUY"])
                    
                    logger.info(f"    │")
                    logger.info(f"    │   🔍 신호 기반 유예 검토...")
                    logger.info(f"    │   현재 신호: {signal_type} (신뢰도: {signal_confidence:.1%})")
                    
                    if signal_type in override_signals and signal_confidence >= override_confidence:
                        # 강한 매수 신호 → 유예 검토
                        
                        # 단, 너무 큰 손실은 유예 불가
                        max_override_loss = config.get("trailing_override_max_loss", 0.005)
                        current_loss = (entry_price - current_price) / entry_price
                        
                        if current_loss <= max_override_loss:
                            logger.info(f"    │   ✅ {signal_type} 신호 감지!")
                            logger.info(f"    │   신뢰도: {signal_confidence:.1%} >= {override_confidence:.1%}")
                            logger.info(f"    │   현재 손익: {profit_rate*100:+.2f}% (유예 가능 범위)")
                            logger.info(f"    │   → 트레일링 유예! 보유 유지")
                            logger.info(f"    └─────────────────────┘")
                            return False, f"트레일링 유예 ({signal_type} 신호)"
                        else:
                            logger.info(f"    │   ⚠️ {signal_type} 신호 있으나 손실 과다")
                            logger.info(f"    │   손실: {current_loss*100:.2f}% > 한도: {max_override_loss*100:.1f}%")
                            logger.info(f"    │   → 유예 불가, 매도 진행")
                    else:
                        logger.info(f"    │   ❌ 유예 조건 미충족")
                        if signal_type not in override_signals:
                            logger.info(f"    │   이유: 신호 유형 ({signal_type})")
                        else:
                            logger.info(f"    │   이유: 신뢰도 부족 ({signal_confidence:.1%} < {override_confidence:.1%})")
                
                reason = f"트레일링 스탑 ({profit_rate*100:+.2f}%, 최고가 대비 -{trailing_loss*100:.2f}%)"
                logger.info(f"    │   💥 트레일링 발동 → 매도")
                logger.info(f"    └─────────────────────┘")
                return True, reason
            else:
                logger.info(f"    │   ✅ 미발동: {current_price:,}원 > {trailing_stop_price:,}원")
                logger.info(f"    │   여유: {(current_price-trailing_stop_price):,}원 ({((current_price-trailing_stop_price)/current_price)*100:.2f}%)")

            # 🔥 2️⃣ 긴급 손절 체크
            logger.info(f"    │ [2/6] 긴급 손절 체크")
            emergency_stop = config.get("emergency_stop_loss", -0.03)

            if profit_rate <= emergency_stop:
                reason = f"긴급 손절 ({profit_rate*100:+.2f}% <= {emergency_stop*100:.0f}%)"
                logger.info(f"    │   ✅ 발동: {profit_rate*100:.2f}% <= {emergency_stop*100:.0f}%")
                logger.info(f"    └─────────────────────┘")
                return True, reason
            else:
                logger.info(f"    │   ❌ 미발동: {profit_rate*100:.2f}% > {emergency_stop*100:.0f}% (여유: {(profit_rate-emergency_stop)*100:.2f}%p)")

            # 🔥 3️⃣ ATR 기반 동적 손절
            logger.info(f"    │ [3/6] ATR 동적 손절선 계산")
            logger.info(f"    │   🔍 ATR 동적 손절선 계산 중...")
            dynamic_stop = self._calculate_dynamic_stop_loss(stock_code, current_price)

            # 신호와 변동성 통합 판단
            signal_type = current_signal.get('signal', 'HOLD') if current_signal else 'HOLD'
            signal_confidence = current_signal.get('confidence', 0) if current_signal else 0

            logger.info(f"    │   📊 ATR 손절선: {dynamic_stop*100:.2f}%")
            logger.info(f"    │   📡 신호: {signal_type} (신뢰도: {signal_confidence:.1%})")
            logger.info(f"    │   💰 현재 손익: {profit_rate*100:+.2f}%")

            logger.info(f"    │ [4/6] 통합 손절 판단 시작...")
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

    def send_market_open_alert(self):
        """
        장 시작 알림 전송 (09:00)
        - 계좌 현황 (기준자산 대비 증감 포함)
        - 보유 종목 상세
        - 누적 성과
        """
        try:
            logger.info("=" * 60)
            logger.info("🔔 장 시작 알림 생성 중...")
            logger.info("=" * 60)
            
            # 🔥 설정 파일 다시 로드 (최신 데이터 반영)
            config.reload_all()
            logger.info("✅ 모든 config 파일 재로드 완료")
            
            # 1️⃣ 자산 정보 조회
            asset_info = self.calculate_total_asset()
            if not asset_info:
                logger.error("❌ 자산 정보 조회 실패 - 장 시작 알림 생략")
                return
            
            total_asset = asset_info['total_asset']
            orderable_amt = asset_info['orderable_amt']
            holding_value = asset_info['holding_value']
            pending_value = asset_info['pending_value']
            
            # 2️⃣ 기준 자산 대비 증감 계산
            perf = config.get('performance', {})
            # baseline_asset은 budget_config에서 가져와야 함 (perf에 포함되어 있지만 명시적으로 확인)
            baseline_asset = perf.get('baseline_asset', config.get('baseline_asset', total_asset))
            baseline_date = perf.get('baseline_date', config.get('baseline_date', '-'))
            
            asset_diff = total_asset - baseline_asset
            asset_diff_rate = (asset_diff / baseline_asset * 100) if baseline_asset > 0 else 0
            
            # 3️⃣ 성과 데이터
            total_trades = perf.get('total_trades', 0)
            winning_trades = perf.get('winning_trades', 0)
            losing_trades = perf.get('losing_trades', 0)
            net_realized_profit = perf.get('net_realized_profit', 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # 4️⃣ 메시지 생성
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            msg = f"🔔 **장 시작 알림** ({now_str})\n"
            msg += f"{'━' * 30}\n"
            
            # 💰 계좌 현황
            msg += f"💰 **계좌 현황**\n"
            msg += f"• 총 자산: {total_asset:,}원 ({asset_diff:+,}원, {asset_diff_rate:+.1f}% vs 기준)\n"
            msg += f"  ├─ 현금: {orderable_amt:,}원\n"
            msg += f"  ├─ 보유주: {holding_value:,}원\n"
            msg += f"  └─ 미체결: {pending_value:,}원\n"
            msg += f"• 기준 자산: {baseline_asset:,}원 ({baseline_date})\n"
            
            # 📈 보유 종목 상세
            msg += f"\n📈 **보유 종목 상세**\n"
            
            with self.lock:
                if self.positions:
                    for stock_code, position in self.positions.items():
                        stock_name = position.get('stock_name', stock_code)
                        qty = position.get('quantity', 0)
                        avg_price = position.get('avg_price', 0)
                        
                        # 현재가 조회
                        try:
                            stock_info = KiwoomAPI.GetStockInfo(stock_code)
                            current_price = stock_info.get('CurrentPrice', avg_price) if stock_info else avg_price
                        except:
                            current_price = avg_price
                        
                        # 수익률 계산
                        profit_rate = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
                        
                        msg += f"• {stock_name}({stock_code})\n"
                        msg += f"  수량: {qty}주 | 평균가: {avg_price:,}원\n"
                        msg += f"  현재가: {current_price:,}원 | 수익률: {profit_rate:+.2f}%\n"
                else:
                    msg += f"• 보유 종목 없음\n"
            
            # 📊 누적 성과
            msg += f"\n📊 **누적 성과**\n"
            msg += f"• 총 거래: {total_trades}회\n"
            msg += f"• 승률: {win_rate:.1f}% ({winning_trades}승 {losing_trades}패)\n"
            msg += f"• 실현손익: {net_realized_profit:+,}원\n"
            
            msg += f"{'━' * 30}\n"
            msg += f"✅ 매매 시스템 정상 가동 중!"
            
            # 5️⃣ Discord 전송
            if config.get("use_discord", True):
                discord_alert.SendMessage(msg)
                logger.info("✅ 장 시작 알림 전송 완료")
            
            logger.info(msg)
            
        except Exception as e:
            logger.error(f"❌ 장 시작 알림 생성 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def check_deposit_withdraw(self):
        """
        kt00015 API를 사용한 입출금 내역 확인 및 baseline 자동 업데이트
        
        - 마지막 점검일 이후 입출금 내역 조회
        - baseline_asset 자동 업데이트
        - 이력 기록 및 Discord 알림
        """
        try:
            logger.info("=" * 60)
            logger.info("💰 입출금 자동 감지 시작")
            logger.info("=" * 60)
            
            # 1️⃣ 설정 확인
            if not config.get('auto_deposit_check', True):
                logger.info("⚠️ 자동 입출금 감지가 비활성화되어 있습니다")
                return
            
            # 2️⃣ 조회 기간 설정
            last_checked = config.get('last_deposit_check_date', '')
            today = datetime.now().strftime("%Y%m%d")
            
            # 첫 실행이거나 마지막 점검일이 없으면 어제부터 조회
            if not last_checked:
                last_checked = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
                logger.info(f"📅 첫 실행: 어제({last_checked})부터 조회")
            
            # 이미 오늘 점검했으면 스킵
            if last_checked == today:
                logger.info(f"✅ 오늘 이미 점검 완료: {today}")
                return
            
            logger.info(f"📅 조회 기간: {last_checked} ~ {today}")
            
            # 3️⃣ kt00015 API 호출 (입출금만)
            transactions = KiwoomAPI.GetTransactionHistory(
                start_date=last_checked,
                end_date=today,
                transaction_type="1"  # 입출금만
            )
            
            if not transactions:
                logger.info("✅ 신규 입출금 내역 없음")
                config.set('last_deposit_check_date', today)
                return
            
            # 4️⃣ 입출금 내역 분석
            total_change = 0
            deposit_count = 0
            withdraw_count = 0
            deposit_details = []
            withdraw_details = []
            
            for tx in transactions:
                tx_type = tx['Type']  # deposit or withdraw
                amount = tx['Amount']
                date = tx['Date']
                time = tx['Time']
                depositor = tx['Depositor']
                remark = tx['Remark']
                
                if tx_type == 'deposit':
                    total_change += amount
                    deposit_count += 1
                    deposit_details.append(f"  💰 {date} {time}: +{amount:,}원 ({depositor or remark})")
                    logger.info(f"💰 입금 감지: +{amount:,}원 ({date} {time}, {depositor or remark})")
                elif tx_type == 'withdraw':
                    total_change -= amount
                    withdraw_count += 1
                    withdraw_details.append(f"  💸 {date} {time}: -{amount:,}원 ({remark})")
                    logger.info(f"💸 출금 감지: -{amount:,}원 ({date} {time}, {remark})")
                
                # 이력 기록
                config.add_deposit_withdraw_history(
                    date=date,
                    time=time,
                    tx_type=tx_type,
                    amount=amount,
                    depositor=depositor
                )
            
            # 5️⃣ baseline_asset 업데이트
            if total_change != 0:
                current_baseline = config.get('baseline_asset', 0)
                new_baseline = current_baseline + total_change
                
                logger.info(f"📊 Baseline 업데이트: {current_baseline:,}원 → {new_baseline:,}원 ({total_change:+,}원)")
                
                config.set('baseline_asset', new_baseline)
                config.set('baseline_date', datetime.now().strftime("%Y-%m-%d"))
                config.set('baseline_note', f"자동 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                # 6️⃣ Discord 알림
                msg = f"💰 **입출금 자동 감지 및 Baseline 업데이트**\n"
                msg += f"{'━'*40}\n"
                msg += f"📅 점검 기간: {last_checked} ~ {today}\n\n"
                
                if deposit_count > 0:
                    msg += f"📥 **입금: {deposit_count}건**\n"
                    msg += "\n".join(deposit_details[:5])  # 최대 5건만 표시
                    if len(deposit_details) > 5:
                        msg += f"\n  ... 외 {len(deposit_details) - 5}건\n"
                    msg += "\n\n"
                
                if withdraw_count > 0:
                    msg += f"📤 **출금: {withdraw_count}건**\n"
                    msg += "\n".join(withdraw_details[:5])
                    if len(withdraw_details) > 5:
                        msg += f"\n  ... 외 {len(withdraw_details) - 5}건\n"
                    msg += "\n\n"
                
                msg += f"💵 **순 변동: {total_change:+,}원**\n"
                msg += f"📊 **Baseline 업데이트**\n"
                msg += f"  • 이전: {current_baseline:,}원\n"
                msg += f"  • 현재: {new_baseline:,}원\n"
                msg += f"{'━'*40}\n"
                msg += f"✅ 성과 계산 기준이 자동으로 조정되었습니다!"
                
                if config.get("use_discord", True):
                    discord_alert.SendMessage(msg)
                
                logger.info("✅ Baseline 자동 업데이트 완료")
            else:
                logger.info("✅ 입출금 합계: 0원 (baseline 변경 없음)")
            
            # 7️⃣ 마지막 점검일 갱신
            config.set('last_deposit_check_date', today)
            logger.info(f"✅ 입출금 감지 완료: {today}")
            
        except Exception as e:
            logger.error(f"❌ 입출금 감지 중 오류: {e}")
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

    def _calculate_rsi(self, minute_data, period=14):
        """
        RSI(Relative Strength Index) 계산
        
        Args:
            minute_data: 분봉 리스트 (최신순)
            period: RSI 계산 기간 (기본 14)
        
        Returns:
            float: RSI 값 (0~100)
        """
        try:
            if len(minute_data) < period + 1:
                return 50  # 데이터 부족 시 중립값
            
            closes = [float(d.get('ClosePrice', 0)) for d in minute_data[:period+1]]
            
            gains = []
            losses = []
            
            for i in range(len(closes)-1):
                change = closes[i] - closes[i+1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            
            if avg_loss == 0:
                return 100
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"RSI 계산 오류: {e}")
            return 50

    def _calculate_bollinger_bands(self, minute_data, period=20, std_dev=2):
        """
        볼린저 밴드 계산
        
        Args:
            minute_data: 분봉 리스트
            period: 이동평균 기간
            std_dev: 표준편차 배수
        
        Returns:
            dict: {upper, middle, lower, current, position}
        """
        try:
            if len(minute_data) < period:
                return None
            
            closes = [float(d.get('ClosePrice', 0)) for d in minute_data[:period]]
            current = closes[0]
            
            ma = sum(closes) / period
            variance = sum((x - ma) ** 2 for x in closes) / period
            std = variance ** 0.5
            
            upper_band = ma + (std_dev * std)
            lower_band = ma - (std_dev * std)
            
            # 밴드 내 위치 (0~1)
            band_width = upper_band - lower_band
            position_in_band = (current - lower_band) / band_width if band_width > 0 else 0.5
            
            return {
                'upper': upper_band,
                'middle': ma,
                'lower': lower_band,
                'current': current,
                'position': position_in_band
            }
            
        except Exception as e:
            logger.error(f"볼린저 밴드 계산 오류: {e}")
            return None

    def _calculate_moving_averages(self, minute_data):
        """
        이동평균선 계산 및 배열 분석
        
        Returns:
            dict: {ma5, ma20, current, alignment}
        """
        try:
            if len(minute_data) < 20:
                return None
            
            closes = [float(d.get('ClosePrice', 0)) for d in minute_data]
            current = closes[0]
            
            ma5 = sum(closes[:5]) / 5
            ma20 = sum(closes[:20]) / 20
            
            # 정배열/역배열 판단
            if current > ma5 > ma20:
                alignment = "정배열"
            elif current < ma5 < ma20:
                alignment = "역배열"
            else:
                alignment = "혼재"
            
            # 5분선과의 거리 (%)
            distance = (current - ma5) / ma5 * 100 if ma5 > 0 else 0
            
            return {
                'ma5': ma5,
                'ma20': ma20,
                'current': current,
                'alignment': alignment,
                'distance_from_ma5': distance
            }
            
        except Exception as e:
            logger.error(f"이동평균 계산 오류: {e}")
            return None

    def _calculate_volume_strength(self, minute_data):
        """
        거래량 강도 분석
        
        Returns:
            float: 거래량 비율 (최근/평균)
        """
        try:
            if len(minute_data) < 5:
                return 1.0
            
            recent_volume = float(minute_data[0].get('Volume', 0))
            avg_volume = sum(float(d.get('Volume', 0)) for d in minute_data[:5]) / 5
            
            if avg_volume == 0:
                return 1.0
            
            volume_ratio = recent_volume / avg_volume
            
            return volume_ratio
            
        except Exception as e:
            logger.error(f"거래량 분석 오류: {e}")
            return 1.0

    def _calculate_technical_score(self, stock_code, minute_data):
        """
        기술적 지표 종합 점수 계산 (0~100점)
        
        점수가 높을수록 강세 → 트레일링 완화
        점수가 낮을수록 약세 → 트레일링 강화
        
        Returns:
            float: 종합 점수 (0~100)
        """
        try:
            tech_config = config.get("technical_indicators", {})
            
            if not tech_config.get("use_rsi") and not tech_config.get("use_bollinger") and \
            not tech_config.get("use_ma") and not tech_config.get("use_volume"):
                return 50  # 지표 미사용 시 중립
            
            score = 0
            max_score = 0
            
            logger.info(f"    ┌─ 기술적 지표 분석 ─┐")
            
            # 1️⃣ RSI 평가
            if tech_config.get("use_rsi", True):
                rsi_period = tech_config.get("rsi_period", 14)
                rsi = self._calculate_rsi(minute_data, period=rsi_period)
                rsi_weight = tech_config.get("rsi_weight", 30)
                
                if rsi <= 30:
                    rsi_score = rsi_weight  # 과매도 → 만점
                elif rsi >= 70:
                    rsi_score = 0   # 과매수 → 0점
                else:
                    # 40~60이 최적 (중립 근처)
                    rsi_score = rsi_weight * (1 - abs(50 - rsi) / 50)
                
                score += rsi_score
                max_score += rsi_weight
                logger.info(f"    │ 📊 RSI: {rsi:.1f} → {rsi_score:.0f}/{rsi_weight}점")
            
            # 2️⃣ 볼린저 밴드 평가
            if tech_config.get("use_bollinger", True):
                bb_period = tech_config.get("bollinger_period", 20)
                bb_std = tech_config.get("bollinger_std", 2)
                bb = self._calculate_bollinger_bands(minute_data, period=bb_period, std_dev=bb_std)
                bb_weight = tech_config.get("bollinger_weight", 30)
                
                if bb:
                    position = bb['position']
                    
                    if position <= 0.2:
                        bb_score = bb_weight  # 하단 → 만점
                    elif position >= 0.8:
                        bb_score = 0   # 상단 → 0점
                    else:
                        # 중심(0.5)에 가까울수록 높은 점수
                        bb_score = bb_weight * (1 - abs(0.5 - position) * 2)
                    
                    score += bb_score
                    max_score += bb_weight
                    logger.info(f"    │ 📊 볼린저: {position*100:.0f}% → {bb_score:.0f}/{bb_weight}점")
                else:
                    logger.info(f"    │ ⚠️ 볼린저: 계산 실패")
            
            # 3️⃣ 이동평균 배열 평가
            if tech_config.get("use_ma", True):
                ma = self._calculate_moving_averages(minute_data)
                ma_weight = tech_config.get("ma_weight", 20)
                
                if ma:
                    if ma['alignment'] == "정배열":
                        ma_score = ma_weight  # 정배열 → 만점
                    elif ma['alignment'] == "역배열":
                        ma_score = 0   # 역배열 → 0점
                    else:
                        ma_score = ma_weight * 0.5  # 혼재 → 중간
                    
                    score += ma_score
                    max_score += ma_weight
                    logger.info(f"    │ 📊 이평: {ma['alignment']} → {ma_score:.0f}/{ma_weight}점")
                else:
                    logger.info(f"    │ ⚠️ 이평: 계산 실패")
            
            # 4️⃣ 거래량 강도 평가
            if tech_config.get("use_volume", True):
                volume_ratio = self._calculate_volume_strength(minute_data)
                volume_weight = tech_config.get("volume_weight", 20)
                
                if volume_ratio > 1.5:
                    volume_score = volume_weight  # 거래량 급증 → 만점
                elif volume_ratio > 1.2:
                    volume_score = volume_weight * 0.75
                elif volume_ratio < 0.8:
                    volume_score = volume_weight * 0.25  # 거래량 감소 → 낮은 점수
                else:
                    volume_score = volume_weight * 0.5
                
                score += volume_score
                max_score += volume_weight
                logger.info(f"    │ 📊 거래량: {volume_ratio:.1f}배 → {volume_score:.0f}/{volume_weight}점")
            
            # 최종 점수 정규화 (0~100)
            final_score = (score / max_score * 100) if max_score > 0 else 50
            
            logger.info(f"    │")
            logger.info(f"    │ 🎯 종합 점수: {final_score:.1f}/100점")
            logger.info(f"    └─────────────────────┘")
            
            return final_score
            
        except Exception as e:
            logger.error(f"기술적 점수 계산 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 50  # 오류 시 중립

    def _get_technical_multiplier(self, technical_score):
        """
        기술적 점수에 따른 트레일링 배율 반환
        
        Args:
            technical_score: 0~100 점수
        
        Returns:
            float: 트레일링 간격 배율
        """
        multipliers = config.get("technical_multiplier", {
            "strong_bull": 2.0,
            "bull": 1.3,
            "neutral": 1.0,
            "bear": 0.7,
            "strong_bear": 0.4
        })
        
        if technical_score >= 70:
            multiplier = multipliers.get("strong_bull", 2.0)
            status = "🟢 강세"
        elif technical_score >= 50:
            multiplier = multipliers.get("bull", 1.3)
            status = "🟡 중강세"
        elif technical_score >= 40:
            multiplier = multipliers.get("neutral", 1.0)
            status = "⚪ 중립"
        elif technical_score >= 30:
            multiplier = multipliers.get("bear", 0.7)
            status = "🟠 약세"
        else:
            multiplier = multipliers.get("strong_bear", 0.4)
            status = "🔴 강약세"
        
        logger.info(f"    📊 기술적 배율: {status} → ×{multiplier:.1f}")
        
        return multiplier

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
                        'order_type': 'sell',
                        'order_price': adjusted_price,
                        'original_price': adjusted_price,  # 🔥 최초 지정가 저장 (일관성)
                        'order_quantity': quantity,
                        'order_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'retry_count': 0,
                        'entry_price': entry_price,
                        'expected_profit': profit,
                        'expected_profit_rate': profit_rate,
                        'sell_reason': reason
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
        
        def daily_report_checker():
            """일일 리포트 전송 체크 (15:20~15:30)"""
            report_sent_date = None
            logger.info("✅ 일일 리포트 체크 스레드 시작")
            
            while self.running:
                try:
                    now = datetime.now()
                    today_date = now.date()
                    
                    # 영업일이고, 15:20~15:30 사이이며, 오늘 아직 전송 안 했으면
                    if (now.weekday() < 5 and  # 월~금요일
                        now.hour == 15 and 
                        20 <= now.minute < 40 and
                        report_sent_date != today_date):
                        
                        logger.info("📊 일일 리포트 전송 시각!")
                        self.send_daily_report()
                        
                        # 오늘 전송 완료 표시
                        report_sent_date = today_date
                        logger.info(f"📊 오늘({today_date}) 일일 리포트 전송 완료")
                        
                except Exception as e:
                    logger.error(f"❌ 일일 리포트 체크 오류: {e}")
                
                time.sleep(60)  # 1분마다 체크
        
        def market_open_alert_checker():
            """장 시작 알림 체크 (09:00)"""
            alert_sent_today = None
            logger.info("✅ 장 시작 알림 체크 스레드 시작")
            
            while self.running:
                try:
                    now = datetime.now()
                    today_date = now.date()
                    
                    # 영업일이고, 09:00이며, 오늘 아직 전송 안 했으면
                    if (now.weekday() < 5 and  # 월~금요일
                        now.hour == 9 and 
                        now.minute == 0 and
                        alert_sent_today != today_date):
                      
                        logger.info("🔔 장이 열렸습니다! 알림 전송 중...")
                        self.send_market_open_alert()
                        
                        # 오늘 알림 전송 완료 표시
                        alert_sent_today = today_date
                        logger.info(f"🔔 오늘({today_date}) 장 시작 알림 전송 완료")
                        
                except Exception as e:
                    logger.error(f"❌ 장 시작 알림 체크 오류: {e}")
                
                time.sleep(30)  # 30초마다 체크
        
        # 🆕 입출금 감지 스레드 추가
        def deposit_check_worker():
            """입출금 점검 워커 (백그라운드 스레드)"""
            logger.info("✅ 입출금 점검 워커 시작")
            
            last_check_day = None
            
            while self.running:
                try:
                    now = datetime.now()
                    today = now.date()
                    
                    # 설정된 점검 시각 가져오기
                    check_time_str = config.get('deposit_check_time', '09:05')
                    check_hour, check_minute = map(int, check_time_str.split(':'))
                    
                    # 점검 시각 도달 확인
                    if (now.hour == check_hour and 
                        now.minute == check_minute and 
                        last_check_day != today):
                        
                        # 영업일에만 점검 (평일 체크)
                        if now.weekday() < 5:  # 월~금요일
                            logger.info(f"⏰ 점검 시각 도달: {check_time_str}")

                            self.check_deposit_withdraw()
                            last_check_day = today
                            
                            # 1분 대기 (중복 실행 방지)
                            time.sleep(60)
                        else:
                            logger.info(f"⏰ 점검 시각이지만 휴장일: {check_time_str}")
                            last_check_day = today
                            time.sleep(60)
                    
                    # 30초마다 시간 체크
                    time.sleep(30)
                    
                except Exception as e:
                    logger.error(f"❌ 입출금 점검 워커 오류: {e}")
                    time.sleep(60)
        
        # 스레드 시작
        pending_thread = threading.Thread(target=pending_checker, daemon=True)
        position_thread = threading.Thread(target=position_checker, daemon=True)
        report_thread = threading.Thread(target=daily_report_checker, daemon=True)
        market_open_thread = threading.Thread(target=market_open_alert_checker, daemon=True)
        deposit_check_thread = threading.Thread(target=deposit_check_worker, daemon=True)  # 🆕 추가
        
        pending_thread.start()
        position_thread.start()
        report_thread.start()
        market_open_thread.start()
        deposit_check_thread.start()  # 🆕 추가

        logger.info("✅ 백그라운드 스레드 시작 완료")
        logger.info(f"   - 미체결 체크: {config.get('check_pending_interval_seconds')}초마다")
        logger.info(f"   - 보유 종목 체크: {config.get('check_position_interval_seconds')}초마다")
        logger.info(f"   - 일일 리포트: 15:20~15:30 (장 마감 후)")
        logger.info(f"   - 🔔 장 시작 알림: 매일 09:00 (영업일만)")
        logger.info(f"   - 💰 입출금 감지: 매일 {config.get('deposit_check_time', '09:05')} (영업일만)")  # 🆕 추가

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
            
            # 🔥 설정 파일 다시 로드 (최신 데이터 반영)
            config.reload_all()
            logger.info("✅ 모든 config 파일 재로드 완료")
            
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
            
            # msg += f"\n{'━'*30}\n"
            # msg += f"💡 추가 입금 시 config 파일에서\n"
            # msg += f"   baseline_asset을 수동 업데이트하세요."

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

    # 🔥🔥🔥 여기에 추가! 🔥🔥🔥
    # 모든 설정 파일 다시 로드 (최신 데이터 반영)
    config.reload_all()
    # 🔥🔥🔥 여기까지 추가 🔥🔥🔥

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
        start_msg += f"• 목표 수익: +{config.get('target_profit_rate', 0.025)*100:.1f}%\n"  # 🔥 default 0.03 → 0.025
        start_msg += f"• 일반 트레일링: -{config.get('trailing_stop_rate', 0.003)*100:.1f}%\n"  # 🔥 default 0.01 → 0.003
        start_msg += f"• 타이트 트레일링: -{config.get('tight_trailing_rate', 0.002)*100:.1f}% (+2% 달성 시)\n"  # 🔥 default 0.005 → 0.002, 주석 +3% → +2%
        start_msg += f"• 본전 보호: +{config.get('breakeven_protection_rate', 0.015)*100:.1f}% 달성 시\n"  # 🔥 default 0.02 → 0.015
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
            net_realized_profit = perf.get('net_realized_profit', 0)
            canceled_orders = perf.get('canceled_orders', 0)
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            msg = f"👋 **{BOT_NAME} 종료**\n"
            msg += f"📊 총 거래: {total_trades}회\n"
            msg += f"✅ 수익 거래: {winning_trades}회 ({win_rate:.1f}%)\n"
            msg += f"💰 총 수익: {net_realized_profit:+,}원\n"
            msg += f"🚫 취소 주문: {canceled_orders}회"
            
            discord_alert.SendMessage(msg)
        
        logger.info("👋 봇 종료 완료")

if __name__ == "__main__":
    main()