#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
신호 기반 자동매매 봇 (SignalTradingBot_Kiwoom) v3.0
- watchdog 실시간 신호 감지 (0초 지연)
- 멀티스레드 API 호출 최적화
- 미체결 주문 자동 관리
- 중복 주문 방지
"""

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
            "bot_name": "SignalTradingBot_Kiwoom",
            "daily_budget": 500000,
            "max_positions": 3,
            "use_discord_alert": True,
            
            # 매수 설정
            "buy_signals": ["STRONG_BUY"],
            "signal_validity_minutes": 10,
            
            # 매도 설정    # 🔥 매도 설정 (A안: 공격적 수익 보호)
            "target_profit_rate": 0.03,              # 3% 목표 (빠른 회전)
            "breakeven_protection_rate": 0.02,       # 2% 달성 시 본전 보호
            "tight_trailing_threshold": 0.03,        # 3% 달성 시 타이트 트레일링 시작
            "tight_trailing_rate": 0.005,            # 0.5% 타이트 트레일링
            "trailing_stop_rate": 0.01,              # 1% 일반 트레일링 (2% 미만 구간)
            "sell_signals": ["SELL", "STRONG_SELL"],
            "emergency_stop_loss": -0.03,            # -3% 긴급 손절 (타이트)
           
            # 🔥 스마트 스케줄링 설정
            "pending_order_timeout_minutes": 5,
            "check_pending_interval_seconds": 30,     # 30초마다 미체결 체크
            "check_position_interval_seconds": 60,    # 60초마다 트레일링 체크
            
            # 쿨다운 설정
            "cooldown_hours": 8,
            
            # 파일 경로
            "signal_file": "signal_history.json",
            "positions_file": "trading_positions.json",
            "pending_orders_file": "trading_pending_orders.json",
            "cooldowns_file": "trading_cooldowns.json",
            
            # 성과 추적
            "performance": {
                "total_trades": 0,
                "winning_trades": 0,
                "total_profit": 0,
                "canceled_orders": 0,
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
logger.info(f"🤖 {BOT_NAME} 초기화 v3.0 (watchdog 실시간)")
logger.info(f"💰 일일 예산: {config.get('daily_budget'):,}원")
logger.info(f"📊 최대 종목: {config.get('max_positions')}개")
logger.info(f"⚡ watchdog: 파일 변경 즉시 감지 (0초 지연)")
logger.info(f"🔄 미체결 체크: {config.get('check_pending_interval_seconds')}초마다")
logger.info(f"📈 트레일링 체크: {config.get('check_position_interval_seconds')}초마다")
logger.info("=" * 60)

################################### 신호 기반 자동매매 봇 v3.0 ##################################

class SignalTradingBot:
    """신호 기반 자동매매 봇 (watchdog + 멀티스레드)"""
    
    def __init__(self):
        self.positions = self.load_positions()
        self.pending_orders = self.load_pending_orders()
        self.cooldowns = self.load_cooldowns()
        
        self.signal_file = config.get("signal_file", "signal_history.json")
        
        # 🔥 스레드 제어
        self.running = True
        self.lock = threading.Lock()  # 데이터 동시 접근 방지
        
        logger.info(f"봇 초기화 완료")
        logger.info(f"현재 보유 종목: {len(self.positions)}개")
        logger.info(f"미체결 주문: {len(self.pending_orders)}개")
        logger.info(f"쿨다운 중인 종목: {len(self.cooldowns)}개")

    def load_positions(self):
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
    
    def save_positions(self):
        try:
            with self.lock:
                positions_file = config.get("positions_file", "trading_positions.json")
                with open(positions_file, 'w', encoding='utf-8') as f:
                    json.dump(self.positions, f, ensure_ascii=False, indent=2)
                logger.debug("✅ 포지션 저장 완료")
        except Exception as e:
            logger.error(f"포지션 저장 실패: {e}")
    
    def load_pending_orders(self):
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
    
    def load_cooldowns(self):
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
        try:
            with self.lock:
                if stock_code in self.positions:
                    logger.debug(f"🚫 {stock_code} 이미 보유 중")
                    return False, "이미 보유 중"
                
                # 🔥 매도 중인 종목도 체크
                if stock_code in self.pending_orders:
                    pending = self.pending_orders[stock_code]
                    order_type = pending.get('order_type', 'buy')
                    logger.debug(f"🚫 {stock_code} {order_type.upper()} 미체결 주문 중 (주문번호: {pending.get('order_no')})")
                    return False, f"{order_type.upper()} 미체결 주문 중"
               
                if self.is_in_cooldown(stock_code):
                    return False, "쿨다운 중"
                
                max_positions = config.get("max_positions", 3)
                total_stocks = len(self.positions) + len(self.pending_orders)
                
                if total_stocks >= max_positions:
                    logger.debug(f"🚫 최대 종목 수 도달 (보유: {len(self.positions)}, 미체결: {len(self.pending_orders)})")
                    return False, f"최대 종목 수 도달 ({total_stocks}/{max_positions})"
                
                daily_budget = config.get("daily_budget", 500000)
                used_budget = sum(
                    pos.get('entry_price', 0) * pos.get('quantity', 0)
                    for pos in self.positions.values()
                )
                
                pending_budget = sum(
                    pend.get('order_price', 0) * pend.get('order_quantity', 0)
                    for pend in self.pending_orders.values()
                )
                
                remaining_budget = daily_budget - used_budget - pending_budget
                
                if remaining_budget < 100000:
                    logger.debug(f"🚫 잔여 예산 부족 ({remaining_budget:,}원)")
                    return False, f"잔여 예산 부족 ({remaining_budget:,}원)"
                
                return True, "매수 가능"
            
        except Exception as e:
            logger.error(f"매수 가능 여부 체크 실패: {e}")
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
        try:
            stock_code = signal.get('stock_code', '')
            stock_name = signal.get('stock_name', '')
            
            logger.info("=" * 60)
            logger.info(f"🚀 {stock_name} 매수 시도")
            logger.info("=" * 60)
            
            can_buy, reason = self.can_buy(stock_code)
            if not can_buy:
                logger.warning(f"❌ 매수 불가: {reason}")
                return False
            
            stock_info = KiwoomAPI.GetStockInfo(stock_code)
            if not stock_info:
                logger.error(f"❌ 현재가 조회 실패")
                return False
            
            current_price = stock_info.get('CurrentPrice', 0)
            
            # 🔥 호가 단위 적용 (매수: 내림)
            adjusted_price = self.adjust_price_to_tick(current_price, is_buy=True)
            
            daily_budget = config.get("daily_budget", 500000)
            max_positions = config.get("max_positions", 3)
            budget_per_stock = daily_budget / max_positions
            
            # 조정된 가격으로 수량 계산
            buy_quantity = int(budget_per_stock / adjusted_price)
            
            if buy_quantity < 1:
                logger.warning(f"❌ 매수 수량 부족 (가격: {adjusted_price:,}원)")
                return False
            
            logger.info(f"💰 매수 주문: {adjusted_price:,}원 × {buy_quantity}주 = {adjusted_price * buy_quantity:,}원")
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
                        'order_price': adjusted_price,  # 조정된 가격 저장
                        'order_quantity': buy_quantity,
                        'order_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'pending',
                        'retry_count': 0,
                        'signal_score': signal.get('score', 0),
                        'signal_confidence': signal.get('confidence', 0)
                    }
                
                self.save_pending_orders()
                
                msg = f"🚀 **매수 주문 완료!**\n"
                msg += f"종목: {stock_name} ({stock_code})\n"
                msg += f"주문번호: {order_no}\n"
                msg += f"가격: {adjusted_price:,}원 × {buy_quantity}주\n"
                msg += f"투자금: {adjusted_price * buy_quantity:,}원\n"
                msg += f"신호: {signal.get('signal')} (점수: {signal.get('score'):.1f})\n"
                msg += f"⏰ 5분 내 미체결 시 자동 취소"
                
                logger.info(msg)
                
                if config.get("use_discord_alert", True):
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
                        logger.info(f"✅ {stock_name} {order_type.upper()} 체결 완료!")

                        with self.lock:
                            if order_type == 'buy':
                                # 매수 체결: positions에 추가
                                entry_price = pending['order_price']
                                self.positions[stock_code] = {
                                    'stock_name': stock_name,
                                    'entry_price': entry_price,
                                    'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'quantity': pending['order_quantity'],
                                    'highest_price': entry_price,
                                    'trailing_stop_price': entry_price * (1 - config.get("trailing_stop_rate", 0.01)),
                                    'target_profit_price': entry_price * (1 + config.get("target_profit_rate", 0.03)),
                                    'signal_score': pending.get('signal_score', 0),
                                    'signal_confidence': pending.get('signal_confidence', 0),
                                    # 🔥 새로운 플래그 추가
                                    'breakeven_protected': False,        # 본전 보호 활성화 여부
                                    'tight_trailing_active': False       # 타이트 트레일링 활성화 여부
                                }
                                
                                msg = f"✅ **매수 체결!**\n"
                                msg += f"종목: {stock_name} ({stock_code})\n"
                                msg += f"가격: {pending['order_price']:,}원 × {pending['order_quantity']}주\n"
                                msg += f"목표가: {self.positions[stock_code]['target_profit_price']:,.0f}원 (+5%)\n"
                                msg += f"트레일링: {self.positions[stock_code]['trailing_stop_price']:,.0f}원 (-1%)"
                                
                                config.update_performance('total_trades', 1)
                                
                            else:  # sell
                                # 매도 체결: positions 삭제, cooldowns 추가
                                if stock_code in self.positions:
                                    del self.positions[stock_code]
                                
                                cooldown_hours = config.get("cooldown_hours", 8)
                                cooldown_until = datetime.now() + timedelta(hours=cooldown_hours)
                                
                                profit = pending.get('expected_profit', 0)
                                profit_rate = pending.get('expected_profit_rate', 0)
                                
                                self.cooldowns[stock_code] = {
                                    'stock_name': stock_name,
                                    'sell_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'cooldown_until': cooldown_until.strftime("%Y-%m-%d %H:%M:%S"),
                                    'sell_reason': pending.get('sell_reason', ''),
                                    'profit': profit,
                                    'profit_rate': profit_rate
                                }
                                
                                config.update_performance('total_profit', profit)
                                if profit > 0:
                                    config.update_performance('winning_trades', 1)
                                
                                emoji = "🎉" if profit > 0 else "😢"
                                msg = f"{emoji} **매도 체결!**\n"
                                msg += f"종목: {stock_name} ({stock_code})\n"
                                msg += f"가격: {pending['order_price']:,}원 × {pending['order_quantity']}주\n"
                                msg += f"수익: {profit:+,}원 ({profit_rate*100:+.2f}%)\n"
                                msg += f"사유: {pending.get('sell_reason', '')}\n"
                                msg += f"쿨다운: {cooldown_hours}시간"
                            
                            del self.pending_orders[stock_code]
                        
                        self.save_positions()
                        self.save_pending_orders()
                        self.save_cooldowns()
                        
                        logger.info(msg)
                        
                        if config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        continue
                    else:
                        # ❌ 주문 취소됨 (미체결도 아니고 체결도 아님)
                        logger.warning(f"❌ {stock_name} {order_type.upper()} 주문 취소됨 (주문번호: {order_no})")
                        
                        with self.lock:
                            if stock_code in self.pending_orders:
                                del self.pending_orders[stock_code]
                        
                        self.save_pending_orders()
                        
                        msg = f"❌ **주문 취소 감지**\n"
                        msg += f"종목: {stock_name} ({stock_code})\n"
                        msg += f"타입: {order_type.upper()}\n"
                        msg += f"사유: 외부 취소 또는 오류"
                        
                        logger.warning(msg)
                        
                        if config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        continue
                
                # 🔥 3단계: 타임아웃 체크 (아직 미체결 상태)
                order_time_str = pending.get('order_time', '')
                try:
                    order_time = datetime.strptime(order_time_str, "%Y-%m-%d %H:%M:%S")
                except:
                    continue
                
                elapsed_minutes = (now - order_time).total_seconds() / 60
                
                if elapsed_minutes >= timeout_minutes:
                    retry_count = pending.get('retry_count', 0)
                    
                    logger.warning(f"⏰ {stock_name} {order_type.upper()} 미체결 타임아웃 ({elapsed_minutes:.1f}분 경과, 재시도: {retry_count}/{max_retry})")
                    
                    # 기존 주문 취소
                    cancel_result = KiwoomAPI.CancelOrder(order_no, stock_code, 0)
                    
                    if not cancel_result.get('success', False):
                        logger.error(f"❌ 주문 취소 실패: {cancel_result.get('msg', '알 수 없는 오류')}")
                        continue
                    
                    logger.info(f"✅ 주문 취소 완료")
                    
                    # 🔥 A 방식: 재시도 (최대 3회)
                    if retry_count < max_retry:
                        logger.info(f"🔄 재시도 {retry_count + 1}/{max_retry} - 현재가로 재주문")
                        
                        # 현재가 조회
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
                                    profit_rate = (adjusted_price - entry_price) / entry_price
                                    self.pending_orders[stock_code]['expected_profit'] = profit
                                    self.pending_orders[stock_code]['expected_profit_rate'] = profit_rate
                            
                            self.save_pending_orders()
                            
                            logger.info(f"✅ 재주문 완료 (가격: {adjusted_price:,}원, 주문번호: {new_order_no})")
                            
                            msg = f"🔄 **재주문 완료** ({retry_count + 1}/{max_retry})\n"
                            msg += f"종목: {stock_name} ({stock_code})\n"
                            msg += f"타입: {order_type.upper()}\n"
                            msg += f"가격: {adjusted_price:,}원 × {quantity}주"
                            
                            if config.get("use_discord_alert", True):
                                discord_alert.SendMessage(msg)
                        else:
                            logger.error(f"❌ 재주문 실패: {retry_result.get('msg', '알 수 없는 오류')}")
                    
                    else:
                        # 🔥 3회 재시도 실패 → 시장가 전환
                        logger.warning(f"🚨 {stock_name} {order_type.upper()} 재시도 {max_retry}회 실패 → 시장가 주문")
                        
                        quantity = pending['order_quantity']
                        
                        # 시장가 주문
                        if order_type == 'buy':
                            market_result = KiwoomAPI.MakeBuyMarketOrder(stock_code, quantity)
                        else:
                            market_result = KiwoomAPI.MakeSellMarketOrder(stock_code, quantity)
                        
                        if market_result.get('success', False):
                            logger.info(f"✅ 시장가 주문 완료")
                            
                            msg = f"🚨 **시장가 전환!**\n"
                            msg += f"종목: {stock_name} ({stock_code})\n"
                            msg += f"타입: {order_type.upper()}\n"
                            msg += f"수량: {quantity}주\n"
                            msg += f"사유: {max_retry}회 재시도 실패"
                            
                            if config.get("use_discord_alert", True):
                                discord_alert.SendMessage(msg)
                            
                            # pending_orders는 유지 (체결 확인 대기)
                            with self.lock:
                                self.pending_orders[stock_code]['order_no'] = market_result.get('order_no', '')
                                self.pending_orders[stock_code]['order_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                self.pending_orders[stock_code]['retry_count'] = max_retry + 1
                            
                            self.save_pending_orders()
                        else:
                            logger.error(f"❌ 시장가 주문 실패: {market_result.get('msg', '알 수 없는 오류')}")
                            
                            # 완전 실패 → pending_orders에서 삭제
                            with self.lock:
                                if stock_code in self.pending_orders:
                                    del self.pending_orders[stock_code]
                            
                            self.save_pending_orders()
                            config.update_performance('canceled_orders', 1)
            
        except Exception as e:
            logger.error(f"미체결 주문 체크 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def update_trailing_stop(self, stock_code):
        """
        트레일링 스탑 업데이트 (A안: 공격적 수익 보호)
        - 2% 달성: 본전 보호 활성화
        - 3% 달성: 타이트 트레일링 시작 (0.5%)
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
            
            # 🔥 1단계: 본전 보호 활성화 (2% 달성)
            breakeven_threshold = config.get("breakeven_protection_rate", 0.02)
            breakeven_protected = position.get('breakeven_protected', False)
            
            if not breakeven_protected and profit_rate >= breakeven_threshold:
                with self.lock:
                    self.positions[stock_code]['breakeven_protected'] = True
                    self.positions[stock_code]['trailing_stop_price'] = entry_price  # 본전으로 설정
                
                self.save_positions()
                
                logger.info(f"🛡️ {stock_code} 본전 보호 활성화! (수익률: {profit_rate*100:+.2f}%)")
                logger.info(f"   손절선: {entry_price:,}원 (본전)")
                
                if config.get("use_discord_alert", True):
                    msg = f"🛡️ **본전 보호 활성화!**\n"
                    msg += f"종목: {position.get('stock_name')} ({stock_code})\n"
                    msg += f"진입가: {entry_price:,}원\n"
                    msg += f"현재가: {current_price:,}원 ({profit_rate*100:+.2f}%)\n"
                    msg += f"손절선: {entry_price:,}원 (본전 보호)"
                    discord_alert.SendMessage(msg)
                
                return
            
            # 🔥 2단계: 타이트 트레일링 활성화 (3% 달성)
            tight_threshold = config.get("tight_trailing_threshold", 0.03)
            tight_trailing_active = position.get('tight_trailing_active', False)
            
            if not tight_trailing_active and profit_rate >= tight_threshold:
                with self.lock:
                    self.positions[stock_code]['tight_trailing_active'] = True
                    
                    tight_rate = config.get("tight_trailing_rate", 0.005)
                    self.positions[stock_code]['trailing_stop_price'] = highest_price * (1 - tight_rate)
                
                self.save_positions()
                
                logger.info(f"🎯 {stock_code} 타이트 트레일링 시작! (수익률: {profit_rate*100:+.2f}%)")
                logger.info(f"   최고가: {highest_price:,}원")
                logger.info(f"   트레일링: {self.positions[stock_code]['trailing_stop_price']:,.0f}원 (-0.5%)")
                
                if config.get("use_discord_alert", True):
                    msg = f"🎯 **타이트 트레일링 시작!**\n"
                    msg += f"종목: {position.get('stock_name')} ({stock_code})\n"
                    msg += f"진입가: {entry_price:,}원\n"
                    msg += f"최고가: {highest_price:,}원 ({profit_rate*100:+.2f}%)\n"
                    msg += f"트레일링: {self.positions[stock_code]['trailing_stop_price']:,.0f}원 (-0.5%)"
                    discord_alert.SendMessage(msg)
                
                return
            
            # 🔥 3단계: 트레일링 스탑 업데이트 (최고가 갱신 시)
            if current_price == highest_price:  # 방금 최고가 갱신됨
                if tight_trailing_active:
                    # 타이트 트레일링 모드
                    tight_rate = config.get("tight_trailing_rate", 0.005)
                    new_trailing_stop = highest_price * (1 - tight_rate)
                elif breakeven_protected:
                    # 본전 보호 모드 (2-3% 구간)
                    # 일반 트레일링 적용하되 본전 아래로는 내려가지 않음
                    trailing_rate = config.get("trailing_stop_rate", 0.01)
                    new_trailing_stop = max(entry_price, highest_price * (1 - trailing_rate))
                else:
                    # 일반 트레일링 (2% 미만 구간)
                    trailing_rate = config.get("trailing_stop_rate", 0.01)
                    new_trailing_stop = highest_price * (1 - trailing_rate)
                
                with self.lock:
                    self.positions[stock_code]['trailing_stop_price'] = new_trailing_stop
                
                self.save_positions()
                
                trailing_profit = (new_trailing_stop - entry_price) / entry_price
                logger.debug(f"🔄 {stock_code} 트레일링 업데이트: {new_trailing_stop:,.0f}원 (보장수익: {trailing_profit*100:+.2f}%)")
            
        except Exception as e:
            logger.error(f"트레일링 스탑 업데이트 실패: {e}")

    def check_sell_conditions(self, stock_code, current_signal=None):
        """
        매도 조건 체크 (A안: 공격적 수익 보호)
        
        우선순위:
        1. 목표 수익 달성 (3%)
        2. 트레일링 스탑 발동
        3. 손절 신호 (SELL, STRONG_SELL)
        4. 긴급 손절 (-3%)
        
        Args:
            stock_code: 종목코드
            current_signal: 현재 신호 정보 (선택)
        
        Returns:
            tuple: (매도 여부, 매도 사유)
        """
        try:
            with self.lock:
                if stock_code not in self.positions:
                    return False, None

                # 🔥 이미 매도 주문 중이면 스킵
                if stock_code in self.pending_orders:
                    pending = self.pending_orders[stock_code]
                    if pending.get('order_type') == 'sell':
                        logger.debug(f"⏭️ {stock_code} 이미 매도 주문 중")
                        return False, None

                position = self.positions[stock_code].copy()
            
            stock_info = KiwoomAPI.GetStockInfo(stock_code)
            if not stock_info:
                return False, None
            
            current_price = stock_info.get('CurrentPrice', 0)
            entry_price = position.get('entry_price', 0)
            trailing_stop_price = position.get('trailing_stop_price', 0)
            
            profit_rate = (current_price - entry_price) / entry_price
            
            # 🔥 매도 조건 체크 (우선순위 순서)
            
            # 1️⃣ 목표 수익 달성 (3%)
            target_profit_rate = config.get("target_profit_rate", 0.03)
            if profit_rate >= target_profit_rate:
                reason = f"목표 수익 달성 ({profit_rate*100:+.2f}%)"
                logger.info(f"🎯 {stock_code} {reason}")
                return True, reason
            
            # 2️⃣ 트레일링 스탑 발동
            if current_price <= trailing_stop_price:
                trailing_profit = (trailing_stop_price - entry_price) / entry_price
                reason = f"트레일링 스탑 발동 (보장수익: {trailing_profit*100:+.2f}%)"
                logger.info(f"📉 {stock_code} {reason}")
                return True, reason
            
            # 3️⃣ 손절 신호 (SELL, STRONG_SELL)
            sell_signals = config.get("sell_signals", ["SELL", "STRONG_SELL"])
            if current_signal and current_signal.get('signal') in sell_signals:
                confidence = current_signal.get('confidence', 0)
                min_confidence = config.get("min_signal_confidence", 0.4)
                
                if confidence >= min_confidence:
                    reason = f"손절 신호 ({current_signal.get('signal')}, 신뢰도: {confidence:.1%})"
                    logger.info(f"🚨 {stock_code} {reason}")
                    return True, reason
            
            # 4️⃣ 긴급 손절 (-3%)
            emergency_stop = config.get("emergency_stop_loss", -0.03)
            if profit_rate <= emergency_stop:
                reason = f"긴급 손절 ({profit_rate*100:+.2f}%)"
                logger.warning(f"🚨 {stock_code} {reason}")
                return True, reason
            
            return False, None
            
        except Exception as e:
            logger.error(f"매도 조건 체크 실패: {e}")
            return False, None

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
                
                if config.get("use_discord_alert", True):
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
        """보유 종목 트레일링 & 매도 체크"""
        try:
            with self.lock:
                if not self.positions:
                    return
                
                position_codes = list(self.positions.keys())
            
            logger.info(f"📊 보유 종목 체크: {len(position_codes)}개")
            
            # 최신 신호 읽기 (매도 신호 확인용)
            all_signals = self.read_latest_signals()
            valid_signals = self.filter_valid_signals(all_signals)
            
            for stock_code in position_codes:
                self.update_trailing_stop(stock_code)
                
                current_signal = None
                for sig in valid_signals:
                    if sig.get('stock_code') == stock_code:
                        current_signal = sig
                        break
                
                should_sell, reason = self.check_sell_conditions(stock_code, current_signal)
                
                if should_sell:
                    self.execute_sell(stock_code, reason)
            
        except Exception as e:
            logger.error(f"보유 종목 체크 실패: {e}")
    
    def process_new_signals(self):
        """🔥 신호 파일 변경 시 호출 (watchdog)"""
        try:
            if not self.is_trading_time():
                logger.debug("장 시간 외 - 거래 없음")
                return
            
            logger.info("")
            logger.info("🔔" * 30)
            logger.info(f"📊 신호 파일 변경 감지 - 즉시 처리!")
            logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("🔔" * 30)
            
            all_signals = self.read_latest_signals()
            valid_signals = self.filter_valid_signals(all_signals)
            
            if not valid_signals:
                logger.info("📭 유효한 신호 없음")
                return
            
            buy_signals = config.get("buy_signals", ["STRONG_BUY"])
            
            buy_candidates = [
                sig for sig in valid_signals
                if sig.get('signal') in buy_signals
            ]
            
            if buy_candidates:
                logger.info(f"🎯 매수 후보: {len(buy_candidates)}개")
                
                buy_candidates_sorted = sorted(
                    buy_candidates,
                    key=lambda x: x.get('timestamp', '')
                )
                
                for signal in buy_candidates_sorted:
                    stock_code = signal.get('stock_code', '')
                    
                    with self.lock:
                        is_already_in = stock_code in self.positions or stock_code in self.pending_orders
                    
                    if is_already_in:
                        logger.debug(f"⏭️ {stock_code} 이미 보유 또는 주문 중")
                        continue
                    
                    success = self.execute_buy(signal)
                    
                    if success:
                        with self.lock:
                            total_stocks = len(self.positions) + len(self.pending_orders)
                        
                        if total_stocks >= config.get("max_positions", 3):
                            logger.info(f"✅ 최대 종목 수 도달 - 매수 중단")
                            break
            
            # 매도 신호도 즉시 체크
            self.check_positions_and_sell()
            
            logger.info("=" * 60)
            logger.info(f"✅ 신호 처리 완료")
            with self.lock:
                logger.info(f"📊 보유 종목: {len(self.positions)}개")
                logger.info(f"📋 미체결 주문: {len(self.pending_orders)}개")
                logger.info(f"⏰ 쿨다운: {len(self.cooldowns)}개")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"신호 처리 오류: {e}")
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
        
        # 스레드 시작
        pending_thread = threading.Thread(target=pending_checker, daemon=True)
        position_thread = threading.Thread(target=position_checker, daemon=True)
        
        pending_thread.start()
        position_thread.start()
        
        logger.info("✅ 백그라운드 스레드 시작 완료")
        logger.info(f"   - 미체결 체크: {config.get('check_pending_interval_seconds')}초마다")
        logger.info(f"   - 보유 종목 체크: {config.get('check_position_interval_seconds')}초마다")
    
    def stop(self):
        """봇 중지"""
        self.running = False
        logger.info("🛑 봇 중지 신호 전송")

################################### Watchdog 핸들러 ##################################

class SignalFileHandler(FileSystemEventHandler):
    """신호 파일 변경 감지 핸들러"""
    
    def __init__(self, bot):
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
    
    if config.get("use_discord_alert", True):
        start_msg = f"🚀 **{BOT_NAME} 시작 v3.0**\n"
        start_msg += f"💰 일일 예산: {config.get('daily_budget'):,}원\n"
        start_msg += f"📊 최대 종목: {config.get('max_positions')}개\n"
        start_msg += f"🎯 매수 신호: {', '.join(config.get('buy_signals', []))}\n"
        start_msg += f"📈 목표 수익: +{config.get('target_profit_rate', 0.05)*100:.0f}%\n"
        start_msg += f"📉 트레일링: -{config.get('trailing_stop_rate', 0.01)*100:.0f}%\n"
        start_msg += f"⏰ 쿨다운: {config.get('cooldown_hours')}시간\n"
        start_msg += f"⏱️ 미체결 타임아웃: {config.get('pending_order_timeout_minutes')}분\n"
        start_msg += f"⚡ **watchdog 실시간 모드**: 0초 지연!"
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
        
        if config.get("use_discord_alert", True):
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