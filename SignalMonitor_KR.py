#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
매매 신호 모니터링 시스템 (SignalMonitor_KR.py)
실제 자동매매 전 신호 정확도 검증용
- 섹터별 종목 실시간 모니터링
- 매수/매도 신호 발생 시 알림 (콘솔 + 디스코드)
- 신호 히스토리 저장 및 정확도 분석
- 중복 알림 방지 (조용한 모드)

버그 수정 버전:
- 조용한 모드 논리 일치
- 중복 체크 최적화
- 신호 발견 조건 명확화
- 성능 개선
"""

import Kiwoom_API_Helper_KR as KiwoomKR
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
logger = logging.getLogger('SignalMonitorLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'signal_monitor.log')
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

################################### 로깅 처리 끝 ##################################

################################### 설정 ##################################

# 섹터별 추천 종목 (20종목)
TARGET_STOCKS = {
    # 🤖 로봇 (4종목)
    "056080": {"name": "유진로봇", "sector": "robot"},
    "056190": {"name": "에스에프에이", "sector": "robot"},
    "108490": {"name": "로보티즈", "sector": "robot"},
    "117730": {"name": "티로보틱스", "sector": "robot"},
    
    # ⚡ 원전 (4종목)
    "034020": {"name": "두산에너빌리티", "sector": "nuclear"},
    "010140": {"name": "삼성중공업", "sector": "nuclear"},
    "267250": {"name": "HD현대", "sector": "nuclear"},
    "123700": {"name": "SJM홀딩스", "sector": "nuclear"},
    
    # 🚀 방산 (4종목)
    "042660": {"name": "한화오션", "sector": "defense"},
    "012450": {"name": "한화에어로스페이스", "sector": "defense"},
    "272210": {"name": "한화시스템", "sector": "defense"},
    "064960": {"name": "SNT모티브", "sector": "defense"},
    
    # 🔋 2차전지 (4종목)
    "373220": {"name": "LG에너지솔루션", "sector": "battery"},
    "006400": {"name": "삼성SDI", "sector": "battery"},
    "051910": {"name": "LG화학", "sector": "battery"},
    "096770": {"name": "SK이노베이션", "sector": "battery"},
    
    # 💾 반도체 (4종목)
    "005930": {"name": "삼성전자", "sector": "semiconductor"},
    "000660": {"name": "SK하이닉스", "sector": "semiconductor"},
    "000990": {"name": "DB하이텍", "sector": "semiconductor"},
    "084370": {"name": "유진테크", "sector": "semiconductor"},
}

# 모니터링 설정 (조용한 모드)
MONITOR_CONFIG = {
    "check_interval_minutes": 5,  # 체크 주기 (분)
    "signal_threshold": 60,        # 신호 발생 최소 점수 (BUY 이상)
    "trading_hours_only": True,    # 장중에만 체크
    "save_history": True,          # 신호 히스토리 저장
    "history_file": "signal_history.json",
    "results_file": "signal_results.json",
    "use_discord": True,           # 디스코드 알림 사용 여부
    
    # 🔇 조용한 모드 설정
    "discord_only_strong_signals": True,  # STRONG_BUY/STRONG_SELL만 알림
    "resend_alert_hours": 0,              # 재알림 없음
    "skip_downgrade_alerts": True,        # 다운그레이드 시 알림 스킵
}

################################### 메인 클래스 ##################################

class SignalMonitor:
    """매매 신호 모니터링 클래스"""
    
    def __init__(self):
        """초기화"""
        self.kiwoom = None
        self.signal_history = []
        self.signal_cache = {}
        self.last_alerts = {}  # 🔥 마지막 알림 기록
        
        # 🔥 장시간 체크 최적화 (버그 4 수정)
        self.market_open_time = datetime.strptime("09:00", "%H:%M").time()
        self.market_close_time = datetime.strptime("15:30", "%H:%M").time()
        
        self.load_history()
        
        # API 초기화
        self.initialize_api()
    
    def initialize_api(self):
        """키움 API 초기화"""
        try:
            logger.info("=" * 60)
            logger.info("🔧 키움증권 API 초기화 중...")
            logger.info("=" * 60)
            
            self.kiwoom = KiwoomKR.Kiwoom_Common()
            
            # 설정 로드
            if not self.kiwoom.LoadConfigData():
                logger.error("❌ 설정 파일 로드 실패")
                return False
            
            # 토큰 발급
            if not self.kiwoom.GetAccessToken():
                logger.error("❌ 토큰 발급 실패")
                return False
            
            logger.info("✅ 키움증권 API 초기화 완료")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"❌ API 초기화 실패: {e}")
            return False
    
    def load_history(self):
        """신호 히스토리 로드"""
        try:
            history_file = MONITOR_CONFIG["history_file"]
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    self.signal_history = json.load(f)
                logger.info(f"✅ 신호 히스토리 로드: {len(self.signal_history)}건")
            else:
                self.signal_history = []
                logger.info("📋 새로운 신호 히스토리 시작")
        except Exception as e:
            logger.error(f"히스토리 로드 실패: {e}")
            self.signal_history = []
    
    def save_history(self):
        """신호 히스토리 저장"""
        try:
            history_file = MONITOR_CONFIG["history_file"]
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.signal_history, f, ensure_ascii=False, indent=2)
            logger.debug(f"💾 신호 히스토리 저장: {len(self.signal_history)}건")
        except Exception as e:
            logger.error(f"히스토리 저장 실패: {e}")
    
    def analyze_timing(self, stock_code, stock_info):
        """
        매수/매도 타이밍 종합 분석
        """
        try:
            stock_name = stock_info["name"]
            sector = stock_info["sector"]
            
            logger.info(f"=" * 60)
            logger.info(f"📊 [{sector}] {stock_name} 타이밍 분석 시작")
            logger.info(f"=" * 60)
            
            analysis_result = {
                "signal": "HOLD",
                "score": 50,
                "reasons": [],
                "details": {},
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "stock_code": stock_code,
                "stock_name": stock_name,
                "sector": sector
            }
            
            score = 50  # 중립 50점에서 시작
            reasons = []
            
            # ═══════════════════════════════════════════════════════════
            # 1️⃣ 호가 분석
            # ═══════════════════════════════════════════════════════════
            logger.info("🔍 [1/5] 호가 분석 중...")
            hoga_data = self.kiwoom.GetHoga(stock_code)
            
            if hoga_data:
                total_sell_qty = hoga_data.get("TotalSellQty", 0)
                total_buy_qty = hoga_data.get("TotalBuyQty", 0)
                
                if total_sell_qty > 0 and total_buy_qty > 0:
                    buy_ratio = total_buy_qty / (total_buy_qty + total_sell_qty) * 100
                    
                    analysis_result["details"]["hoga"] = {
                        "total_buy_qty": total_buy_qty,
                        "total_sell_qty": total_sell_qty,
                        "buy_ratio": round(buy_ratio, 2)
                    }
                    
                    if buy_ratio >= 70:
                        score += 15
                        reasons.append(f"✅ 매수호가 우세 ({buy_ratio:.1f}%)")
                        logger.info(f"   ✅ 매수호가 우세: {buy_ratio:.1f}%")
                    elif buy_ratio >= 60:
                        score += 8
                        reasons.append(f"✓ 매수호가 다소 우세 ({buy_ratio:.1f}%)")
                        logger.info(f"   ✓ 매수호가 다소 우세: {buy_ratio:.1f}%")
                    elif buy_ratio <= 30:
                        score -= 15
                        reasons.append(f"❌ 매도호가 우세 ({100-buy_ratio:.1f}%)")
                        logger.info(f"   ❌ 매도호가 우세: {100-buy_ratio:.1f}%")
                    elif buy_ratio <= 40:
                        score -= 8
                        reasons.append(f"⚠ 매도호가 다소 우세 ({100-buy_ratio:.1f}%)")
                        logger.info(f"   ⚠ 매도호가 다소 우세: {100-buy_ratio:.1f}%")
                    else:
                        logger.info(f"   ➖ 호가 균형: 매수 {buy_ratio:.1f}%")
            
            # ═══════════════════════════════════════════════════════════
            # 2️⃣ 체결 정보 분석
            # ═══════════════════════════════════════════════════════════
            logger.info("🔍 [2/5] 체결 정보 분석 중...")
            execution_data = self.kiwoom.GetExecutionInfo(stock_code)
            
            if execution_data and execution_data.get("LatestExecution"):
                latest = execution_data["LatestExecution"]
                exec_strength = latest.get("ExecutionStrength", 0)
                exec_qty = latest.get("ExecutionQty", 0)
                
                analysis_result["details"]["execution"] = {
                    "strength": exec_strength,
                    "latest_qty": exec_qty,
                    "latest_price": latest.get("CurrentPrice", 0)
                }
                
                if exec_strength >= 150:
                    score += 12
                    reasons.append(f"✅ 체결강도 매우 강함 ({exec_strength:.1f}%)")
                    logger.info(f"   ✅ 체결강도 매우 강함: {exec_strength:.1f}%")
                elif exec_strength >= 120:
                    score += 6
                    reasons.append(f"✓ 체결강도 강함 ({exec_strength:.1f}%)")
                    logger.info(f"   ✓ 체결강도 강함: {exec_strength:.1f}%")
                elif exec_strength <= 80 and exec_strength > 0:
                    score -= 12
                    reasons.append(f"❌ 체결강도 약함 ({exec_strength:.1f}%)")
                    logger.info(f"   ❌ 체결강도 약함: {exec_strength:.1f}%")
                elif exec_strength <= 90 and exec_strength > 0:
                    score -= 6
                    reasons.append(f"⚠ 체결강도 다소 약함 ({exec_strength:.1f}%)")
                    logger.info(f"   ⚠ 체결강도 다소 약함: {exec_strength:.1f}%")
                else:
                    logger.info(f"   ➖ 체결강도 보통: {exec_strength:.1f}%")
            
            # ═══════════════════════════════════════════════════════════
            # 3️⃣ 외국인/기관 매매 동향
            # ═══════════════════════════════════════════════════════════
            logger.info("🔍 [3/5] 외국인/기관 매매 동향 분석 중...")
            
            foreign_data = self.kiwoom.GetRealtimeInvestorTrading(
                market_type="000", 
                investor="6",
                exchange_type="3"
            )
            
            institution_data = self.kiwoom.GetRealtimeInvestorTrading(
                market_type="000",
                investor="7",
                exchange_type="3"
            )
            
            foreign_net_buy = 0
            institution_net_buy = 0
            
            if foreign_data:
                for item in foreign_data:
                    if item["StockCode"] == stock_code:
                        foreign_net_buy = item.get("NetBuyQty", 0)
                        analysis_result["details"]["foreign_net_buy"] = foreign_net_buy
                        break
            
            if institution_data:
                for item in institution_data:
                    if item["StockCode"] == stock_code:
                        institution_net_buy = item.get("NetBuyQty", 0)
                        analysis_result["details"]["institution_net_buy"] = institution_net_buy
                        break
            
            if foreign_net_buy > 0 and institution_net_buy > 0:
                score += 15
                reasons.append(f"✅ 외국인+기관 동반 순매수")
                logger.info(f"   ✅ 외국인+기관 동반 순매수")
            elif foreign_net_buy > 0 or institution_net_buy > 0:
                score += 8
                buyer = "외국인" if foreign_net_buy > 0 else "기관"
                reasons.append(f"✓ {buyer} 순매수")
                logger.info(f"   ✓ {buyer} 순매수")
            elif foreign_net_buy < 0 and institution_net_buy < 0:
                score -= 15
                reasons.append(f"❌ 외국인+기관 동반 순매도")
                logger.info(f"   ❌ 외국인+기관 동반 순매도")
            elif foreign_net_buy < 0 or institution_net_buy < 0:
                score -= 8
                seller = "외국인" if foreign_net_buy < 0 else "기관"
                reasons.append(f"⚠ {seller} 순매도")
                logger.info(f"   ⚠ {seller} 순매도")
            else:
                logger.info(f"   ➖ 외국인/기관 매매 중립")
            
            # ═══════════════════════════════════════════════════════════
            # 4️⃣ 현재가 분석
            # ═══════════════════════════════════════════════════════════
            logger.info("🔍 [4/5] 현재가 및 거래량 분석 중...")
            stock_data = self.kiwoom.GetStockInfo(stock_code)
            
            if stock_data:
                change_rate = stock_data.get("ChangeRate", 0)
                current_price = stock_data.get("CurrentPrice", 0)
                volume = stock_data.get("Volume", 0)
                
                analysis_result["details"]["stock_info"] = {
                    "current_price": current_price,
                    "change_rate": change_rate,
                    "volume": volume
                }
                
                if change_rate >= 3.0:
                    score += 10
                    reasons.append(f"✅ 강한 상승세 (+{change_rate:.2f}%)")
                    logger.info(f"   ✅ 강한 상승세: +{change_rate:.2f}%")
                elif change_rate >= 1.0:
                    score += 5
                    reasons.append(f"✓ 상승세 (+{change_rate:.2f}%)")
                    logger.info(f"   ✓ 상승세: +{change_rate:.2f}%")
                elif change_rate <= -3.0:
                    score -= 10
                    reasons.append(f"❌ 강한 하락세 ({change_rate:.2f}%)")
                    logger.info(f"   ❌ 강한 하락세: {change_rate:.2f}%")
                elif change_rate <= -1.0:
                    score -= 5
                    reasons.append(f"⚠ 하락세 ({change_rate:.2f}%)")
                    logger.info(f"   ⚠ 하락세: {change_rate:.2f}%")
                else:
                    logger.info(f"   ➖ 등락률 보통: {change_rate:+.2f}%")
                
                if volume >= 1000000:
                    score += 5
                    reasons.append(f"✓ 거래량 활발 ({volume:,}주)")
                    logger.info(f"   ✓ 거래량 활발: {volume:,}주")
            
            # ═══════════════════════════════════════════════════════════
            # 5️⃣ 분봉 데이터 분석
            # ═══════════════════════════════════════════════════════════
            logger.info("🔍 [5/5] 분봉 추세 분석 중...")
            minute_data = self.kiwoom.GetMinuteData(stock_code)
            
            if minute_data:
                close_price = minute_data.get("ClosePrice", 0)
                open_price = minute_data.get("OpenPrice", 0)
                
                analysis_result["details"]["minute_data"] = {
                    "open": open_price,
                    "close": close_price
                }
                
                if close_price > open_price and open_price > 0:
                    candle_ratio = ((close_price - open_price) / open_price) * 100
                    if candle_ratio >= 2.0:
                        score += 8
                        reasons.append(f"✅ 강한 양봉 ({candle_ratio:.1f}%)")
                        logger.info(f"   ✅ 강한 양봉: {candle_ratio:.1f}%")
                    else:
                        score += 4
                        reasons.append(f"✓ 양봉 ({candle_ratio:.1f}%)")
                        logger.info(f"   ✓ 양봉: {candle_ratio:.1f}%")
                elif close_price < open_price and open_price > 0:
                    candle_ratio = ((open_price - close_price) / open_price) * 100
                    if candle_ratio >= 2.0:
                        score -= 8
                        reasons.append(f"❌ 강한 음봉 (-{candle_ratio:.1f}%)")
                        logger.info(f"   ❌ 강한 음봉: -{candle_ratio:.1f}%")
                    else:
                        score -= 4
                        reasons.append(f"⚠ 음봉 (-{candle_ratio:.1f}%)")
                        logger.info(f"   ⚠ 음봉: -{candle_ratio:.1f}%")
            
            # ═══════════════════════════════════════════════════════════
            # 📊 최종 신호 판단
            # ═══════════════════════════════════════════════════════════
            score = max(0, min(100, score))
            
            if score >= 75:
                signal = "STRONG_BUY"
                signal_emoji = "🔥💰"
            elif score >= 60:
                signal = "BUY"
                signal_emoji = "📈✅"
            elif score >= 40:
                signal = "HOLD"
                signal_emoji = "⏸️"
            elif score >= 25:
                signal = "SELL"
                signal_emoji = "⚠️📉"
            else:
                signal = "STRONG_SELL"
                signal_emoji = "🚨❌"
            
            analysis_result["signal"] = signal
            analysis_result["score"] = round(score, 1)
            analysis_result["reasons"] = reasons
            
            logger.info(f"")
            logger.info(f"=" * 60)
            logger.info(f"{signal_emoji} 최종 신호: {signal} (점수: {score:.1f}/100)")
            logger.info(f"=" * 60)
            
            if reasons:
                logger.info(f"📋 신호 발생 이유:")
                for reason in reasons:
                    logger.info(f"   {reason}")
            
            logger.info(f"=" * 60)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"타이밍 분석 예외: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def should_send_alert(self, stock_code, result):
        """
        알림 발송 여부 판단 (중복 방지만 체크)
        
        Note: 조용한 모드 필터링은 check_all_stocks()에서 이미 처리됨
        
        Returns:
            bool: 알림을 보내야 하면 True
        """
        try:
            current_signal = result["signal"]
            current_time = datetime.now()
            
            # 🔥 이전 알림 기록 확인 (버그 2 수정: 중복 체크만)
            if stock_code in self.last_alerts:
                last_alert = self.last_alerts[stock_code]
                last_signal = last_alert.get("signal")
                last_time = last_alert.get("time")
                
                # 1. 같은 신호 중복 체크
                if current_signal == last_signal:
                    logger.debug(f"중복 신호 스킵: {stock_code} - {current_signal}")
                    return False
                
                # 2. 신호 다운그레이드 체크
                if MONITOR_CONFIG.get("skip_downgrade_alerts", True):
                    signal_priority = {
                        "STRONG_BUY": 5,
                        "BUY": 4,
                        "HOLD": 3,
                        "SELL": 2,
                        "STRONG_SELL": 1
                    }
                    
                    current_priority = signal_priority.get(current_signal, 0)
                    last_priority = signal_priority.get(last_signal, 0)
                    
                    # 매수 신호가 약해지거나, 매도 신호가 약해지면 스킵
                    if current_signal in ["STRONG_BUY", "BUY", "HOLD"]:
                        if current_priority < last_priority:
                            logger.debug(f"신호 다운그레이드 스킵: {last_signal} → {current_signal}")
                            return False
                    elif current_signal in ["SELL", "STRONG_SELL"]:
                        if current_priority > last_priority:
                            logger.debug(f"매도 신호 다운그레이드 스킵: {last_signal} → {current_signal}")
                            return False
            
            # 🔥 새로운 신호 또는 신호 변경 → 알림 발송
            logger.info(f"신호 변경 감지: {self.last_alerts.get(stock_code, {}).get('signal', 'NONE')} → {current_signal}")
            self.last_alerts[stock_code] = {
                "signal": current_signal,
                "time": current_time,
                "score": result["score"]
            }
            
            return True
            
        except Exception as e:
            logger.error(f"알림 발송 여부 판단 실패: {e}")
            return True  # 에러 시에는 알림 발송
    
    def check_all_stocks(self):
        """전체 종목 체크"""
        try:
            logger.info("")
            logger.info("🔄" * 30)
            logger.info(f"📊 전체 종목 스캔 시작 ({len(TARGET_STOCKS)}종목)")
            logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("🔄" * 30)
            
            signals_found = []
            alerts_sent = []
            
            # 🔥 조용한 모드 설정 (버그 1, 3 수정)
            only_strong_signals = MONITOR_CONFIG.get("discord_only_strong_signals", True)
            
            for stock_code, stock_info in TARGET_STOCKS.items():
                try:
                    # 분석 실행
                    result = self.analyze_timing(stock_code, stock_info)
                    
                    if result:
                        # 캐시 업데이트
                        self.signal_cache[stock_code] = result
                        
                        # 신호 발생 조건 체크
                        signal = result["signal"]
                        score = result["score"]
                        threshold = MONITOR_CONFIG["signal_threshold"]
                        
                        # 🔥 신호 발견 조건 (버그 1 수정)
                        should_track = False
                        
                        if only_strong_signals:
                            # 조용한 모드 ON: STRONG_BUY/STRONG_SELL만
                            if signal in ["STRONG_BUY", "STRONG_SELL"]:
                                should_track = True
                        else:
                            # 조용한 모드 OFF: BUY 이상 + 모든 매도 신호
                            if score >= threshold or signal in ["SELL", "STRONG_SELL"]:
                                should_track = True
                        
                        if should_track:
                            signals_found.append(result)
                            
                            # 히스토리 저장
                            if MONITOR_CONFIG["save_history"]:
                                self.signal_history.append(result)
                            
                            # 🔥 알림 발송 (중복 체크만)
                            if self.should_send_alert(stock_code, result):
                                self.send_signal_alert(result)
                                alerts_sent.append(result)
                            else:
                                logger.debug(f"중복 알림 스킵: {stock_info['name']} - {signal}")
                    
                    # API 호출 간격
                    time.sleep(0.5)
                    
                except Exception as stock_e:
                    logger.error(f"{stock_info['name']} 분석 실패: {stock_e}")
                    continue
            
            # 요약
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"✅ 스캔 완료: {len(signals_found)}개 신호 발견, {len(alerts_sent)}개 알림 발송")
            logger.info("=" * 60)
            
            if signals_found:
                for sig in signals_found:
                    sent_mark = "📢" if sig in alerts_sent else "🔇"
                    logger.info(f"  {sent_mark} [{sig['sector']}] {sig['stock_name']}: {sig['signal']} ({sig['score']:.1f}점)")
            
            # 히스토리 저장
            if MONITOR_CONFIG["save_history"]:
                self.save_history()
                
        except Exception as e:
            logger.error(f"전체 종목 체크 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def send_signal_alert(self, result):
        """
        신호 알림 발송 (콘솔 + 디스코드)
        
        Note: 조용한 모드 필터링은 check_all_stocks()에서 이미 처리됨
        """
        try:
            stock_code = result["stock_code"]
            stock_name = result["stock_name"]
            sector = result["sector"]
            signal = result["signal"]
            score = result["score"]
            
            # 이모지 매핑
            signal_emoji_map = {
                "STRONG_BUY": "🔥💰",
                "BUY": "📈✅",
                "HOLD": "⏸️",
                "SELL": "⚠️📉",
                "STRONG_SELL": "🚨❌"
            }
            
            sector_emoji_map = {
                "robot": "🤖",
                "nuclear": "⚡",
                "defense": "🚀",
                "battery": "🔋",
                "semiconductor": "💾"
            }
            
            emoji = signal_emoji_map.get(signal, "📊")
            sector_emoji = sector_emoji_map.get(sector, "📊")
            
            # ═══════════════════════════════════════════════════════════
            # 콘솔 메시지 출력
            # ═══════════════════════════════════════════════════════════
            console_msg = f"\n{'='*50}\n"
            console_msg += f"{emoji} 매매 신호 발생!\n"
            console_msg += f"{'='*50}\n"
            console_msg += f"종목: [{sector}] {stock_name} ({stock_code})\n"
            console_msg += f"신호: {signal} (점수: {score:.1f}/100)\n"
            console_msg += f"시각: {result['timestamp']}\n"
            console_msg += f"\n📋 신호 이유:\n"
            
            for reason in result["reasons"][:5]:  # 상위 5개만
                console_msg += f"  • {reason}\n"
            
            if result["details"].get("stock_info"):
                stock_info = result["details"]["stock_info"]
                console_msg += f"\n💹 현재가 정보:\n"
                console_msg += f"  가격: {stock_info['current_price']:,}원\n"
                console_msg += f"  등락: {stock_info['change_rate']:+.2f}%\n"
                console_msg += f"  거래량: {stock_info['volume']:,}주\n"
            
            console_msg += f"{'='*50}\n"
            
            logger.info(console_msg)
            
            # ═══════════════════════════════════════════════════════════
            # 디스코드 메시지 생성 및 발송
            # ═══════════════════════════════════════════════════════════
            if MONITOR_CONFIG.get("use_discord", True):
                # 🔥 조용한 모드 체크 제거 (버그 2 수정: check_all_stocks에서 이미 처리됨)
                
                # 디스코드 메시지 작성
                discord_msg = f"{emoji} **매매 신호 발생!**\n"
                discord_msg += f"{'─'*30}\n"
                discord_msg += f"**종목**: {sector_emoji} [{sector}] {stock_name}\n"
                discord_msg += f"**코드**: `{stock_code}`\n"
                discord_msg += f"**신호**: `{signal}` (점수: **{score:.1f}**/100)\n"
                discord_msg += f"**시각**: {result['timestamp']}\n"
                
                # 신호 이유 (상위 5개)
                if result["reasons"]:
                    discord_msg += f"\n📋 **신호 이유**:\n"
                    for i, reason in enumerate(result["reasons"][:5], 1):
                        discord_msg += f"`{i}.` {reason}\n"
                
                # 현재가 정보
                if result["details"].get("stock_info"):
                    stock_info = result["details"]["stock_info"]
                    discord_msg += f"\n💹 **현재가 정보**:\n"
                    discord_msg += f"• 가격: `{stock_info['current_price']:,}원`\n"
                    discord_msg += f"• 등락: `{stock_info['change_rate']:+.2f}%`\n"
                    discord_msg += f"• 거래량: `{stock_info['volume']:,}주`\n"
                
                # 상세 지표 추가
                details = result.get("details", {})
                
                # 호가 정보
                if details.get("hoga"):
                    hoga = details["hoga"]
                    discord_msg += f"\n📊 **호가 분석**:\n"
                    discord_msg += f"• 매수잔량: `{hoga['total_buy_qty']:,}주`\n"
                    discord_msg += f"• 매도잔량: `{hoga['total_sell_qty']:,}주`\n"
                    discord_msg += f"• 매수비율: `{hoga['buy_ratio']:.1f}%`\n"
                
                # 체결강도
                if details.get("execution"):
                    execution = details["execution"]
                    discord_msg += f"\n⚡ **체결강도**: `{execution['strength']:.1f}%`\n"
                
                # 외국인/기관
                foreign = details.get("foreign_net_buy", 0)
                institution = details.get("institution_net_buy", 0)
                
                if foreign != 0 or institution != 0:
                    discord_msg += f"\n🌐 **세력 동향**:\n"
                    if foreign != 0:
                        foreign_status = "순매수" if foreign > 0 else "순매도"
                        discord_msg += f"• 외국인: `{foreign_status} {abs(foreign):,}주`\n"
                    if institution != 0:
                        inst_status = "순매수" if institution > 0 else "순매도"
                        discord_msg += f"• 기관: `{inst_status} {abs(institution):,}주`\n"
                
                discord_msg += f"\n{'─'*30}\n"
                discord_msg += f"🔔 SignalMonitor_KR (조용한 모드 🔇)"
                
                # 디스코드 전송
                try:
                    discord_alert.SendMessage(discord_msg)
                    logger.info(f"✅ 디스코드 알림 전송 완료: {stock_name}")
                except Exception as discord_e:
                    logger.error(f"❌ 디스코드 알림 전송 실패: {discord_e}")
            
        except Exception as e:
            logger.error(f"알림 발송 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def is_trading_time(self):
        """장중 시간 체크 (최적화)"""
        try:
            if not MONITOR_CONFIG["trading_hours_only"]:
                return True
            
            now = datetime.now()
            
            # 주말 체크
            if now.weekday() >= 5:
                return False
            
            # 🔥 장 시간 체크 (사전 파싱된 시간 사용)
            current_time = now.time()
            return self.market_open_time <= current_time <= self.market_close_time
            
        except Exception as e:
            logger.error(f"장시간 체크 실패: {e}")
            return False

################################### 메인 실행 ##################################

def run_monitor():
    """모니터링 실행"""
    try:
        monitor = SignalMonitor()
        
        if not monitor.kiwoom:
            logger.error("❌ API 초기화 실패 - 모니터링 중단")
            return
        
        # 장중 시간 체크
        if not monitor.is_trading_time():
            logger.info("⏰ 장 시간 외입니다. 대기 중...")
            return
        
        # 전체 종목 체크
        monitor.check_all_stocks()
        
    except Exception as e:
        logger.error(f"모니터링 실행 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """메인 함수"""
    try:
        logger.info("=" * 60)
        logger.info("🚀 매매 신호 모니터링 시스템 시작 (조용한 모드 🔇)")
        logger.info("=" * 60)
        logger.info(f"📊 모니터링 종목: {len(TARGET_STOCKS)}개")
        logger.info(f"⏱️ 체크 주기: {MONITOR_CONFIG['check_interval_minutes']}분")
        logger.info(f"📈 신호 임계값: {MONITOR_CONFIG['signal_threshold']}점 이상")
        logger.info(f"💬 디스코드 알림: {'ON (STRONG 신호만)' if MONITOR_CONFIG.get('use_discord') else 'OFF'}")
        logger.info(f"🔇 중복 알림: 차단됨 (신호 변경 시에만 알림)")
        logger.info("=" * 60)
        
        # 🔥 디스코드 시작 알림
        if MONITOR_CONFIG.get("use_discord", True):
            try:
                startup_msg = "🚀 **매매 신호 모니터링 시작!** 🔇\n"
                startup_msg += f"{'─'*30}\n"
                startup_msg += f"📊 **모니터링 종목**: {len(TARGET_STOCKS)}개\n"
                startup_msg += f"⏱️ **체크 주기**: {MONITOR_CONFIG['check_interval_minutes']}분\n"
                startup_msg += f"📈 **신호 임계값**: {MONITOR_CONFIG['signal_threshold']}점 이상\n"
                startup_msg += f"🔇 **조용한 모드**: STRONG_BUY/STRONG_SELL만 알림\n"
                startup_msg += f"\n🔍 **섹터별 종목**:\n"
                
                sector_count = {}
                for stock_info in TARGET_STOCKS.values():
                    sector = stock_info["sector"]
                    sector_count[sector] = sector_count.get(sector, 0) + 1
                
                sector_emoji = {
                    "robot": "🤖",
                    "nuclear": "⚡",
                    "defense": "🚀",
                    "battery": "🔋",
                    "semiconductor": "💾"
                }
                
                sector_name_kr = {
                    "robot": "로봇",
                    "nuclear": "원전",
                    "defense": "방산",
                    "battery": "2차전지",
                    "semiconductor": "반도체"
                }
                
                for sector, count in sector_count.items():
                    emoji = sector_emoji.get(sector, "📊")
                    name_kr = sector_name_kr.get(sector, sector)
                    startup_msg += f"• {emoji} {name_kr}: `{count}개`\n"
                
                startup_msg += f"\n{'─'*30}\n"
                startup_msg += f"✅ 시스템 준비 완료!"
                
                discord_alert.SendMessage(startup_msg)
                logger.info("✅ 디스코드 시작 알림 전송 완료")
            except Exception as discord_e:
                logger.warning(f"⚠️ 디스코드 시작 알림 전송 실패: {discord_e}")
        
        # 섹터별 종목 수 출력 (콘솔)
        logger.info("📊 섹터별 종목 수:")
        sector_count = {}
        for stock_info in TARGET_STOCKS.values():
            sector = stock_info["sector"]
            sector_count[sector] = sector_count.get(sector, 0) + 1
        
        sector_emoji = {
            "robot": "🤖",
            "nuclear": "⚡",
            "defense": "🚀",
            "battery": "🔋",
            "semiconductor": "💾"
        }
        
        for sector, count in sector_count.items():
            emoji = sector_emoji.get(sector, "📊")
            logger.info(f"  {emoji} {sector}: {count}개")
        
        logger.info("=" * 60)
        
        # 처음에 한 번 실행
        run_monitor()
        
        # 스케줄 설정
        interval = MONITOR_CONFIG["check_interval_minutes"]
        schedule.every(interval).minutes.do(run_monitor)
        
        # 스케줄러 실행
        logger.info(f"⏰ {interval}분마다 자동 실행됩니다...")
        
        while True:
            schedule.run_pending()
            time.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 사용자에 의해 중단되었습니다.")
        
        # 🔥 디스코드 종료 알림
        if MONITOR_CONFIG.get("use_discord", True):
            try:
                stop_msg = "🛑 **매매 신호 모니터링 중단**\n"
                stop_msg += f"종료 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                discord_alert.SendMessage(stop_msg)
            except:
                pass
                
    except Exception as e:
        logger.error(f"메인 실행 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 🔥 디스코드 오류 알림
        if MONITOR_CONFIG.get("use_discord", True):
            try:
                error_msg = f"❌ **시스템 오류 발생**\n"
                error_msg += f"```{str(e)[:200]}```"
                discord_alert.SendMessage(error_msg)
            except:
                pass

if __name__ == "__main__":
    main()