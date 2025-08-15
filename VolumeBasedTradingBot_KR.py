#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
거래량 기반 자동매매 봇 (VolumeBasedTradingBot_KR) - 실시간 거래량 변화 추적 시스템
1. 바닥권 매집 신호 감지 (거래량 급증 + 양봉)
2. 눌림목 매수 타이밍 포착
3. 상투권 대량거래 매도 신호
4. 다중 시간프레임 거래량 분석 (일봉 → 30분봉 → 5분봉)
5. 실시간 거래량 모니터링 및 자동 매매 실행
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
import numpy as np

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
logger = logging.getLogger('VolumeBasedTradingLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'volume_trading_bot.log')
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

# API 초기화
Common.SetChangeMode()
logger.info("✅ API 초기화 완료 - 모든 KIS API 사용 가능")

################################### 설정 관리 시스템 ##################################

class VolumeTradeConfig:
    """거래량 기반 매매 설정 관리 클래스"""
    
    def __init__(self, config_path: str = "volume_trading_config.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()

    def get_default_config(self):
        """기본 설정값 반환"""
        return {
            "bot_name": "VolumeBasedTradingBot",
            "trading_budget": 5000000,  # 500만원 기본 예산
            "max_positions": 5,         # 최대 5개 종목 동시 보유
            
            # 거래량 기반 매수 조건
            "buy_conditions": {
                "volume_surge_ratio": 2.0,        # 평균 대비 2배 이상 거래량 급증
                "consecutive_pattern_days": 3,    # 2-3일 연속 패턴 감지
                "pullback_volume_decrease": 0.7,  # 눌림목에서 거래량 30% 감소
                "candle_body_ratio": 0.6,         # 장대양봉 몸통 비율 60% 이상
                "min_price_increase": 3.0,        # 최소 3% 이상 상승
                "rsi_upper_limit": 75,            # RSI 75 이하에서만 매수
                "volume_ma_period": 20            # 거래량 이동평균 기간
            },
            
            # 거래량 기반 매도 조건  
            "sell_conditions": {
                "high_volume_surge": 3.0,         # 고점에서 3배 이상 거래량 급증
                "negative_candle_threshold": 0.5, # 장대음봉 기준 (몸통 50% 이상)
                "profit_target": 50.0,            # 목표 수익률 50%
                "stop_loss": -15.0,               # 손절선 -15%
                "volume_decrease_days": 3,        # 거래량 감소 지속 일수
                "rsi_sell_threshold": 80          # RSI 80 이상에서 매도 고려
            },
            
            # 다중 시간프레임 설정
            "timeframes": {
                "daily": {"period": 60, "weight": 0.6},      # 일봉 60일, 가중치 60%
                "30min": {"period": 48, "weight": 0.3},      # 30분봉 48개(24시간), 가중치 30%
                "5min": {"period": 72, "weight": 0.1}        # 5분봉 72개(6시간), 가중치 10%
            },
            
            # 시장 상황별 조정
            "market_conditions": {
                "bull_market_multiplier": 1.2,    # 상승장에서 매수량 20% 증가
                "bear_market_multiplier": 0.6,    # 하락장에서 매수량 40% 감소
                "sideways_multiplier": 0.8        # 횡보장에서 매수량 20% 감소
            },
            
            # 종목 스캔 설정
            "stock_scan": {
                "max_price": 100000,              # 최대 주가 10만원
                "min_market_cap": 1000,           # 최소 시가총액 1000억
                "min_volume": 100000,             # 최소 거래량 10만주
                "scan_markets": ["KOSPI", "KOSDAQ"], # 스캔 대상 시장
                "update_interval_minutes": 30      # 종목 리스트 업데이트 주기
            },
            
            # 리스크 관리
            "risk_management": {
                "max_position_per_stock": 0.3,    # 종목당 최대 30% 투자
                "daily_loss_limit": -5.0,         # 일일 손실 한계 -5%
                "consecutive_loss_limit": 3,      # 연속 손실 거래 한계
                "emergency_stop_loss": -20.0      # 긴급 정지 손실률
            },
            
            # 알림 설정
            "notifications": {
                "use_discord_alert": True,
                "signal_alerts": True,
                "trade_execution_alerts": True,
                "daily_summary_alerts": True
            },
            
            # 성과 추적
            "performance_tracking": {
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "total_trades": 0,
                "winning_trades": 0,
                "total_profit": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0
            }
        }

    def load_config(self):
        """설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            default_config = self.get_default_config()
            self.config = self._merge_config(default_config, loaded_config)
            logger.info(f"✅ 설정 파일 로드 완료: {self.config_path}")
            
        except FileNotFoundError:
            logger.info(f"📋 설정 파일이 없습니다. 기본 설정으로 생성: {self.config_path}")
            self.config = self.get_default_config()
            self.save_config()
            
            # Discord 알림
            if self.config.get("notifications", {}).get("use_discord_alert", True):
                setup_msg = f"🔧 **거래량 기반 매매봇 설정 생성**\n"
                setup_msg += f"📊 매매 예산: {self.config['trading_budget']:,}원\n"
                setup_msg += f"📈 최대 보유종목: {self.config['max_positions']}개\n"
                setup_msg += f"⚡ 거래량 급증 기준: {self.config['buy_conditions']['volume_surge_ratio']}배\n"
                setup_msg += f"🎯 목표수익률: {self.config['sell_conditions']['profit_target']}%\n"
                setup_msg += f"🛡️ 손절선: {self.config['sell_conditions']['stop_loss']}%"
                discord_alert.SendMessage(setup_msg)
                
        except Exception as e:
            logger.error(f"설정 파일 로드 중 오류: {str(e)}")
            self.config = self.get_default_config()

    def _merge_config(self, default, loaded):
        """설정 병합"""
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
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"✅ 설정 파일 저장 완료: {self.config_path}")
        except Exception as e:
            logger.error(f"설정 파일 저장 중 오류: {str(e)}")

# 전역 설정 인스턴스
config = VolumeTradeConfig()

################################### 거래량 분석 엔진 ##################################

class VolumeAnalysisEngine:
    """거래량 패턴 분석 엔진"""
    
    def __init__(self):
        self.volume_cache = {}  # 거래량 데이터 캐시
        self.pattern_history = {}  # 패턴 이력 추적
        
    def get_volume_data(self, stock_code, timeframe="daily", period=60):
        """종목별 거래량 데이터 조회"""
        try:
            cache_key = f"{stock_code}_{timeframe}_{period}"
            current_time = time.time()
            
            # 캐시 확인 (5분 유효)
            if cache_key in self.volume_cache:
                cache_data = self.volume_cache[cache_key]
                if current_time - cache_data['timestamp'] < 300:  # 5분
                    return cache_data['data']
            
            # 데이터 조회
            if timeframe == "daily":
                df = Common.GetOhlcv("KR", stock_code, period)
            else:
                # 분봉 데이터는 별도 구현 필요 (KIS API 제약)
                df = Common.GetOhlcv("KR", stock_code, period)
            
            if df is None or len(df) < 10:
                return None
                
            # 거래량 관련 지표 계산
            df['volume_ma5'] = df['volume'].rolling(5).mean()
            df['volume_ma20'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma20']
            df['price_change'] = (df['close'] - df['open']) / df['open'] * 100
            df['candle_body_ratio'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])
            
            # 캐시 저장
            self.volume_cache[cache_key] = {
                'data': df,
                'timestamp': current_time
            }
            
            return df
            
        except Exception as e:
            logger.error(f"거래량 데이터 조회 오류 ({stock_code}): {str(e)}")
            return None

    def detect_volume_surge_pattern(self, stock_code):
        """거래량 급증 패턴 감지"""
        try:
            df = self.get_volume_data(stock_code, "daily", 60)
            if df is None or len(df) < 20:
                return False, "데이터 부족"
            
            buy_conditions = config.config["buy_conditions"]
            
            # 최근 3일 데이터
            recent_data = df.tail(3)
            
            # 1. 바닥권 매집 신호 체크
            # - 일정 기간 거래량 낮다가 급증
            volume_ma = df['volume_ma20'].iloc[-4:-1].mean()  # 이전 3일 평균
            current_volume = df['volume'].iloc[-1]
            volume_surge_ratio = current_volume / volume_ma if volume_ma > 0 else 0
            
            # 2. 양봉 + 거래량 급증 체크
            price_change = df['price_change'].iloc[-1]
            candle_body_ratio = df['candle_body_ratio'].iloc[-1]
            
            # 3. 연속 패턴 체크 (3일 패턴)
            pattern_detected = False
            
            if len(recent_data) >= 3:
                day1_volume_surge = recent_data['volume_ratio'].iloc[0] >= buy_conditions["volume_surge_ratio"]
                day1_positive = recent_data['price_change'].iloc[0] > 0
                
                day2_volume_decrease = recent_data['volume_ratio'].iloc[1] < recent_data['volume_ratio'].iloc[0]
                
                day3_volume_increase = recent_data['volume_ratio'].iloc[2] > recent_data['volume_ratio'].iloc[1]
                day3_positive = recent_data['price_change'].iloc[2] > 0
                
                # 3일 연속 패턴 확인
                if day1_volume_surge and day1_positive and day2_volume_decrease and day3_volume_increase and day3_positive:
                    pattern_detected = True
                    pattern_type = "3일_연속_매집_패턴"
            
            # 4. 장대양봉 + 대량거래 체크
            if (volume_surge_ratio >= buy_conditions["volume_surge_ratio"] and 
                price_change >= buy_conditions["min_price_increase"] and
                candle_body_ratio >= buy_conditions["candle_body_ratio"]):
                pattern_detected = True
                pattern_type = "장대양봉_대량거래"
            
            if pattern_detected:
                signal_info = {
                    'pattern_type': pattern_type,
                    'volume_surge_ratio': volume_surge_ratio,
                    'price_change': price_change,
                    'candle_body_ratio': candle_body_ratio,
                    'signal_strength': min(volume_surge_ratio / 2.0, 1.0) * 100
                }
                return True, signal_info
            
            return False, "패턴 미감지"
            
        except Exception as e:
            logger.error(f"거래량 급증 패턴 감지 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}"

    def detect_pullback_opportunity(self, stock_code):
        """눌림목 매수 기회 감지"""
        try:
            df = self.get_volume_data(stock_code, "daily", 30)
            if df is None or len(df) < 10:
                return False, "데이터 부족"
            
            buy_conditions = config.config["buy_conditions"]
            
            # 최근 거래량 급증 이후 조정 구간 체크
            recent_volume_surge = False
            surge_index = -1
            
            # 최근 5일 내 거래량 급증 확인
            for i in range(5):
                if len(df) > i and df['volume_ratio'].iloc[-(i+1)] >= buy_conditions["volume_surge_ratio"]:
                    recent_volume_surge = True
                    surge_index = -(i+1)
                    break
            
            if not recent_volume_surge:
                return False, "최근 거래량 급증 없음"
            
            # 급증 이후 거래량 감소 + 가격 조정 확인
            current_volume_ratio = df['volume_ratio'].iloc[-1]
            surge_volume_ratio = df['volume_ratio'].iloc[surge_index]
            
            volume_decreased = current_volume_ratio <= surge_volume_ratio * buy_conditions["pullback_volume_decrease"]
            
            # 가격이 하락 조정 중인지 확인
            surge_price = df['close'].iloc[surge_index]
            current_price = df['close'].iloc[-1]
            price_pullback = (current_price - surge_price) / surge_price * 100
            
            if volume_decreased and -10 <= price_pullback <= -2:  # 2-10% 조정
                signal_info = {
                    'pattern_type': '눌림목_매수_기회',
                    'surge_volume_ratio': surge_volume_ratio,
                    'current_volume_ratio': current_volume_ratio,
                    'price_pullback': price_pullback,
                    'days_since_surge': abs(surge_index) - 1
                }
                return True, signal_info
            
            return False, "눌림목 조건 미충족"
            
        except Exception as e:
            logger.error(f"눌림목 기회 감지 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}"

    def detect_distribution_pattern(self, stock_code):
        """상투권 분배 패턴 감지 (매도 신호)"""
        try:
            df = self.get_volume_data(stock_code, "daily", 60)
            if df is None or len(df) < 20:
                return False, "데이터 부족"
            
            sell_conditions = config.config["sell_conditions"]
            
            # 고점 구간 확인 (최근 20일 최고가 대비)
            recent_high = df['high'].tail(20).max()
            current_price = df['close'].iloc[-1]
            high_ratio = current_price / recent_high
            
            if high_ratio < 0.9:  # 고점 대비 10% 이상 하락시 분배 패턴 아님
                return False, "고점 구간 아님"
            
            # 대량거래 + 장대음봉 체크
            current_volume_ratio = df['volume_ratio'].iloc[-1]
            price_change = df['price_change'].iloc[-1]
            candle_body_ratio = df['candle_body_ratio'].iloc[-1]
            
            # 위꼬리 긴 캔들 체크
            upper_shadow = (df['high'].iloc[-1] - max(df['open'].iloc[-1], df['close'].iloc[-1])) / (df['high'].iloc[-1] - df['low'].iloc[-1])
            
            # 분배 패턴 조건
            volume_surge = current_volume_ratio >= sell_conditions["high_volume_surge"]
            negative_candle = price_change < 0 and candle_body_ratio >= sell_conditions["negative_candle_threshold"]
            long_upper_shadow = upper_shadow > 0.3
            
            if volume_surge and (negative_candle or long_upper_shadow):
                signal_info = {
                    'pattern_type': '상투권_분배_패턴',
                    'volume_surge_ratio': current_volume_ratio,
                    'price_change': price_change,
                    'upper_shadow_ratio': upper_shadow,
                    'high_ratio': high_ratio
                }
                return True, signal_info
            
            return False, "분배 패턴 미감지"
            
        except Exception as e:
            logger.error(f"분배 패턴 감지 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}"

################################### 메인 거래 봇 클래스 ##################################

class VolumeBasedTradingBot:
    """거래량 기반 자동매매 봇"""
    
    def __init__(self):
        self.analysis_engine = VolumeAnalysisEngine()
        self.positions = {}  # 현재 포지션 정보
        self.trading_data = []  # 거래 이력
        self.last_scan_time = None
        self.target_stocks = []  # 관심 종목 리스트
        
        # 데이터 로드
        self.load_trading_data()
        
        logger.info("🤖 거래량 기반 자동매매 봇 초기화 완료")

    def load_trading_data(self):
        """거래 데이터 로드"""
        try:
            data_file = "volume_trading_data.json"
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    self.trading_data = json.load(f)
                logger.info(f"✅ 거래 데이터 로드 완료: {len(self.trading_data)}건")
            else:
                self.trading_data = []
                logger.info("📋 새로운 거래 데이터 파일 생성")
        except Exception as e:
            logger.error(f"거래 데이터 로드 오류: {str(e)}")
            self.trading_data = []

    def save_trading_data(self):
        """거래 데이터 저장"""
        try:
            data_file = "volume_trading_data.json"
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(self.trading_data, f, ensure_ascii=False, indent=2)
            logger.debug("✅ 거래 데이터 저장 완료")
        except Exception as e:
            logger.error(f"거래 데이터 저장 오류: {str(e)}")

    def scan_market_for_volume_signals(self):
        """시장 전체 거래량 신호 스캔"""
        try:
            current_time = datetime.now()
            scan_config = config.config["stock_scan"]
            
            # 스캔 주기 체크
            if (self.last_scan_time and 
                (current_time - self.last_scan_time).total_seconds() < scan_config["update_interval_minutes"] * 60):
                return self.target_stocks
            
            logger.info("📊 시장 거래량 신호 스캔 시작...")
            
            # 거래량 순위 상위 종목 조회
            volume_stocks = []
            
            for market in scan_config["scan_markets"]:
                market_code = "J" if market == "KOSPI" else "Q"
                volume_rank = KisKR.get_volume_rank(
                    market_code=market_code,
                    vol_type="20171",  # 거래량 순위
                    top_n=50,
                    max_price=scan_config["max_price"]
                )
                
                if volume_rank:
                    volume_stocks.extend(volume_rank)
            
            # 거래량 급증 종목 필터링
            signal_stocks = []
            
            for stock in volume_stocks[:100]:  # 상위 100개만 분석
                try:
                    stock_code = stock['code']
                    stock_name = stock['name']
                    
                    # 시가총액 필터
                    if stock['price'] * 1000000 < scan_config["min_market_cap"] * 100000000:
                        continue
                    
                    # 거래량 급증 패턴 체크
                    surge_detected, surge_info = self.analysis_engine.detect_volume_surge_pattern(stock_code)
                    
                    if surge_detected:
                        signal_stocks.append({
                            'code': stock_code,
                            'name': stock_name,
                            'price': stock['price'],
                            'volume_ratio': stock.get('volume_ratio', 0),
                            'signal_info': surge_info
                        })
                        
                        logger.info(f"🔍 거래량 신호 감지: {stock_name} ({stock_code})")
                        logger.info(f"   패턴: {surge_info.get('pattern_type', 'Unknown')}")
                        logger.info(f"   거래량 비율: {surge_info.get('volume_surge_ratio', 0):.1f}배")
                        
                except Exception as e:
                    logger.error(f"종목 분석 오류 ({stock.get('code', 'Unknown')}): {str(e)}")
                    continue
            
            # 신호 강도별 정렬
            signal_stocks.sort(key=lambda x: x['signal_info'].get('signal_strength', 0), reverse=True)
            
            # 상위 종목만 선택
            max_positions = config.config["max_positions"]
            self.target_stocks = signal_stocks[:max_positions * 2]  # 여유분 확보
            
            self.last_scan_time = current_time
            
            logger.info(f"✅ 거래량 신호 스캔 완료: {len(self.target_stocks)}개 종목 선별")
            
            # Discord 알림
            if (config.config["notifications"]["signal_alerts"] and 
                config.config["notifications"]["use_discord_alert"]):
                
                if signal_stocks:
                    alert_msg = f"📊 **거래량 신호 감지** ({len(signal_stocks)}개)\n\n"
                    for i, stock in enumerate(signal_stocks[:5], 1):
                        signal_info = stock['signal_info']
                        alert_msg += f"{i}. {stock['name']}\n"
                        alert_msg += f"   패턴: {signal_info.get('pattern_type', 'Unknown')}\n"
                        alert_msg += f"   거래량: {signal_info.get('volume_surge_ratio', 0):.1f}배\n\n"
                    
                    discord_alert.SendMessage(alert_msg)
            
            return self.target_stocks
            
        except Exception as e:
            logger.error(f"시장 스캔 오류: {str(e)}")
            return self.target_stocks or []

    def check_buy_conditions(self, stock_code, stock_name):
        """매수 조건 종합 체크"""
        try:
            # 1. 현재 포지션 체크
            current_positions = len([p for p in self.positions.values() if p.get('amount', 0) > 0])
            if current_positions >= config.config["max_positions"]:
                return False, "최대 포지션 수 초과"
            
            # 2. 이미 보유 중인지 체크
            if stock_code in self.positions and self.positions[stock_code].get('amount', 0) > 0:
                return False, "이미 보유 중"
            
            # 3. 거래량 패턴 분석
            surge_detected, surge_info = self.analysis_engine.detect_volume_surge_pattern(stock_code)
            pullback_detected, pullback_info = self.analysis_engine.detect_pullback_opportunity(stock_code)
            
            if not (surge_detected or pullback_detected):
                return False, "거래량 패턴 미감지"
            
            # 4. 기술적 지표 체크
            current_price = KisKR.GetCurrentPrice(stock_code)
            if not current_price:
                return False, "현재가 정보 없음"
            
            # RSI 체크 (간단한 계산)
            df = Common.GetOhlcv("KR", stock_code, 20)
            if df is not None and len(df) >= 14:
                # RSI 계산
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta).where(delta < 0, 0).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1]
                
                rsi_limit = config.config["buy_conditions"]["rsi_upper_limit"]
                if current_rsi > rsi_limit:
                    return False, f"RSI 과매수 구간 ({current_rsi:.1f} > {rsi_limit})"
            
            # 5. 예산 체크
            balance = KisKR.GetBalance()
            available_cash = float(balance.get('RemainMoney', 0))
            
            position_size = config.config["trading_budget"] / config.config["max_positions"]
            
            # 시장 상황별 조정
            market_multiplier = self.get_market_condition_multiplier()
            adjusted_position_size = position_size * market_multiplier
            
            if available_cash < adjusted_position_size:
                return False, f"잔고 부족 (필요: {adjusted_position_size:,.0f}원, 보유: {available_cash:,.0f}원)"
            
            # 6. 재료/호재 체크 (뉴스 데이터 있을 경우)
            # TODO: 뉴스 API 연동시 구현
            
            signal_type = "거래량_급증" if surge_detected else "눌림목_매수"
            signal_data = surge_info if surge_detected else pullback_info
            
            return True, {
                'signal_type': signal_type,
                'signal_data': signal_data,
                'position_size': adjusted_position_size,
                'current_price': current_price,
                'rsi': current_rsi if 'current_rsi' in locals() else None
            }
            
        except Exception as e:
            logger.error(f"매수 조건 체크 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}"

    def check_sell_conditions(self, stock_code, position_info):
        """매도 조건 종합 체크"""
        try:
            sell_conditions = config.config["sell_conditions"]
            
            # 1. 현재가 조회
            current_price = KisKR.GetCurrentPrice(stock_code)
            if not current_price:
                return False, "현재가 정보 없음", {}
            
            entry_price = position_info['entry_price']
            profit_rate = (current_price - entry_price) / entry_price * 100
            
            # 2. 손절선 체크
            if profit_rate <= sell_conditions["stop_loss"]:
                return True, "손절선_도달", {
                    'sell_type': '손절매',
                    'profit_rate': profit_rate,
                    'reason': f'손절선 도달 ({profit_rate:.1f}%)'
                }
            
            # 3. 목표 수익률 달성
            if profit_rate >= sell_conditions["profit_target"]:
                return True, "목표수익_달성", {
                    'sell_type': '익절매',
                    'profit_rate': profit_rate,
                    'reason': f'목표 수익률 달성 ({profit_rate:.1f}%)'
                }
            
            # 4. 상투권 분배 패턴 체크
            distribution_detected, dist_info = self.analysis_engine.detect_distribution_pattern(stock_code)
            if distribution_detected:
                return True, "분배패턴_감지", {
                    'sell_type': '기술적매도',
                    'profit_rate': profit_rate,
                    'reason': f"분배 패턴 감지: {dist_info.get('pattern_type', 'Unknown')}",
                    'pattern_info': dist_info
                }
            
            # 5. 대량거래 음봉 출현
            df = self.analysis_engine.get_volume_data(stock_code, "daily", 5)
            if df is not None and len(df) >= 2:
                current_volume_ratio = df['volume_ratio'].iloc[-1]
                price_change = df['price_change'].iloc[-1]
                
                if (current_volume_ratio >= sell_conditions["high_volume_surge"] and 
                    price_change < -2):  # 2% 이상 하락
                    return True, "대량거래_음봉", {
                        'sell_type': '기술적매도',
                        'profit_rate': profit_rate,
                        'reason': f'대량거래 음봉 출현 (거래량: {current_volume_ratio:.1f}배, 하락: {price_change:.1f}%)'
                    }
            
            # 6. 거래량 감소 + 가격 하락 지속 체크
            if df is not None and len(df) >= sell_conditions["volume_decrease_days"]:
                recent_volume_trend = df['volume_ratio'].tail(sell_conditions["volume_decrease_days"])
                recent_price_trend = df['price_change'].tail(sell_conditions["volume_decrease_days"])
                
                volume_decreasing = recent_volume_trend.mean() < 1.0
                price_declining = recent_price_trend.mean() < 0
                
                if volume_decreasing and price_declining and profit_rate < 10:  # 수익률 10% 미만일 때만
                    return True, "거래량감소_하락지속", {
                        'sell_type': '기술적매도',
                        'profit_rate': profit_rate,
                        'reason': f'{sell_conditions["volume_decrease_days"]}일간 거래량 감소 + 가격 하락'
                    }
            
            # 7. RSI 과매수 구간 + 수익 실현
            if profit_rate > 20:  # 20% 이상 수익시에만 RSI 체크
                df_rsi = Common.GetOhlcv("KR", stock_code, 20)
                if df_rsi is not None and len(df_rsi) >= 14:
                    delta = df_rsi['close'].diff()
                    gain = delta.where(delta > 0, 0).rolling(14).mean()
                    loss = (-delta).where(delta < 0, 0).rolling(14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]
                    
                    if current_rsi >= sell_conditions["rsi_sell_threshold"]:
                        return True, "RSI_과매수", {
                            'sell_type': '기술적매도',
                            'profit_rate': profit_rate,
                            'reason': f'RSI 과매수 구간 ({current_rsi:.1f}) + 수익 실현'
                        }
            
            return False, "매도 조건 미충족", {}
            
        except Exception as e:
            logger.error(f"매도 조건 체크 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}", {}

    def get_market_condition_multiplier(self):
        """시장 상황별 매수량 조정 배수 계산"""
        try:
            # 코스피 지수로 시장 상황 판단
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 20)
            if kospi_df is None or len(kospi_df) < 10:
                return 1.0
            
            # 단순한 추세 판단 (5일 이평선 vs 20일 이평선)
            ma5 = kospi_df['close'].rolling(5).mean().iloc[-1]
            ma20 = kospi_df['close'].rolling(20).mean().iloc[-1]
            current_price = kospi_df['close'].iloc[-1]
            
            market_conditions = config.config["market_conditions"]
            
            if current_price > ma5 > ma20:
                # 상승장
                return market_conditions["bull_market_multiplier"]
            elif current_price < ma5 < ma20:
                # 하락장
                return market_conditions["bear_market_multiplier"]
            else:
                # 횡보장
                return market_conditions["sideways_multiplier"]
                
        except Exception as e:
            logger.error(f"시장 상황 분석 오류: {str(e)}")
            return 1.0

    def execute_buy_order(self, stock_code, stock_name, buy_info):
        """매수 주문 실행"""
        try:
            current_price = buy_info['current_price']
            position_size = buy_info['position_size']
            
            # 매수 수량 계산 (현재가 기준)
            buy_amount = int(position_size / current_price)
            
            if buy_amount <= 0:
                logger.warning(f"❌ {stock_name} 매수 수량 계산 오류 (수량: {buy_amount})")
                return False
            
            # 지정가 매수 (현재가 + 0.5% 상향)
            buy_price = int(current_price * 1.005)
            
            logger.info(f"📈 {stock_name} 매수 주문 실행")
            logger.info(f"   종목코드: {stock_code}")
            logger.info(f"   매수가격: {buy_price:,}원")
            logger.info(f"   매수수량: {buy_amount:,}주")
            logger.info(f"   투자금액: {buy_price * buy_amount:,}원")
            logger.info(f"   신호타입: {buy_info['signal_type']}")
            
            # 실제 매수 주문
            order_result = KisKR.MakeBuyLimitOrder(stock_code, buy_amount, buy_price)
            
            if isinstance(order_result, dict) and 'OrderNum' in order_result:
                # 매수 성공
                position_data = {
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'entry_price': buy_price,
                    'amount': buy_amount,
                    'entry_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'signal_type': buy_info['signal_type'],
                    'signal_data': buy_info['signal_data'],
                    'order_num': order_result['OrderNum']
                }
                
                # 포지션 기록
                self.positions[stock_code] = position_data
                
                # 거래 이력 저장
                trade_record = position_data.copy()
                trade_record['trade_type'] = 'BUY'
                trade_record['total_amount'] = buy_price * buy_amount
                self.trading_data.append(trade_record)
                
                self.save_trading_data()
                
                # 성과 추적 업데이트
                config.config["performance_tracking"]["total_trades"] += 1
                config.save_config()
                
                logger.info(f"✅ {stock_name} 매수 주문 완료")
                
                # Discord 알림
                if (config.config["notifications"]["trade_execution_alerts"] and 
                    config.config["notifications"]["use_discord_alert"]):
                    
                    buy_msg = f"💰 **매수 주문 체결**\n\n"
                    buy_msg += f"🏢 종목: {stock_name} ({stock_code})\n"
                    buy_msg += f"💵 가격: {buy_price:,}원\n"
                    buy_msg += f"📊 수량: {buy_amount:,}주\n"
                    buy_msg += f"💎 투자금액: {buy_price * buy_amount:,}원\n"
                    buy_msg += f"🎯 신호: {buy_info['signal_type']}\n"
                    buy_msg += f"📈 RSI: {buy_info.get('rsi', 'N/A'):.1f}" if buy_info.get('rsi') else ""
                    
                    discord_alert.SendMessage(buy_msg)
                
                return True
                
            else:
                # 매수 실패
                logger.error(f"❌ {stock_name} 매수 주문 실패: {order_result}")
                return False
                
        except Exception as e:
            logger.error(f"매수 주문 실행 오류 ({stock_code}): {str(e)}")
            return False

    def execute_sell_order(self, stock_code, position_info, sell_info):
        """매도 주문 실행"""
        try:
            stock_name = position_info['stock_name']
            sell_amount = position_info['amount']
            
            # 현재가 조회
            current_price = KisKR.GetCurrentPrice(stock_code)
            if not current_price:
                logger.error(f"❌ {stock_name} 현재가 조회 실패")
                return False
            
            # 지정가 매도 (현재가 - 0.5% 하향)
            sell_price = int(current_price * 0.995)
            
            logger.info(f"📉 {stock_name} 매도 주문 실행")
            logger.info(f"   종목코드: {stock_code}")
            logger.info(f"   매도가격: {sell_price:,}원")
            logger.info(f"   매도수량: {sell_amount:,}주")
            logger.info(f"   수익률: {sell_info['profit_rate']:.2f}%")
            logger.info(f"   매도사유: {sell_info['reason']}")
            
            # 실제 매도 주문
            order_result = KisKR.MakeSellLimitOrder(stock_code, sell_amount, sell_price)
            
            if isinstance(order_result, dict) and 'OrderNum' in order_result:
                # 매도 성공
                entry_price = position_info['entry_price']
                profit = (sell_price - entry_price) * sell_amount
                profit_rate = sell_info['profit_rate']
                
                # 거래 이력 저장
                trade_record = {
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'trade_type': 'SELL',
                    'entry_price': entry_price,
                    'sell_price': sell_price,
                    'amount': sell_amount,
                    'profit': profit,
                    'profit_rate': profit_rate,
                    'sell_reason': sell_info['reason'],
                    'sell_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'hold_days': self.calculate_hold_days(position_info['entry_date']),
                    'order_num': order_result['OrderNum']
                }
                
                self.trading_data.append(trade_record)
                
                # 포지션 제거
                del self.positions[stock_code]
                
                self.save_trading_data()
                
                # 성과 추적 업데이트
                tracking = config.config["performance_tracking"]
                tracking["total_profit"] += profit
                
                if profit > 0:
                    tracking["winning_trades"] += 1
                    if profit > tracking.get("best_trade", 0):
                        tracking["best_trade"] = profit
                else:
                    if profit < tracking.get("worst_trade", 0):
                        tracking["worst_trade"] = profit
                
                config.save_config()
                
                logger.info(f"✅ {stock_name} 매도 주문 완료 (수익: {profit:+,.0f}원, {profit_rate:+.2f}%)")
                
                # Discord 알림
                if (config.config["notifications"]["trade_execution_alerts"] and 
                    config.config["notifications"]["use_discord_alert"]):
                    
                    profit_emoji = "📈" if profit > 0 else "📉"
                    sell_msg = f"{profit_emoji} **매도 주문 체결**\n\n"
                    sell_msg += f"🏢 종목: {stock_name} ({stock_code})\n"
                    sell_msg += f"💵 매도가격: {sell_price:,}원\n"
                    sell_msg += f"📊 수량: {sell_amount:,}주\n"
                    sell_msg += f"💰 수익: {profit:+,.0f}원 ({profit_rate:+.2f}%)\n"
                    sell_msg += f"📅 보유기간: {trade_record['hold_days']}일\n"
                    sell_msg += f"🎯 매도사유: {sell_info['reason']}"
                    
                    discord_alert.SendMessage(sell_msg)
                
                return True
                
            else:
                # 매도 실패
                logger.error(f"❌ {stock_name} 매도 주문 실패: {order_result}")
                return False
                
        except Exception as e:
            logger.error(f"매도 주문 실행 오류 ({stock_code}): {str(e)}")
            return False

    def calculate_hold_days(self, entry_date_str):
        """보유 기간 계산"""
        try:
            entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d %H:%M:%S')
            hold_days = (datetime.now() - entry_date).days
            return max(hold_days, 0)  # 최소 0일
        except:
            return 0

    def update_positions_from_broker(self):
        """브로커 정보와 포지션 동기화"""
        try:
            # 실제 보유 종목 조회
            actual_holdings = KisKR.GetMyStockList()
            
            # 내부 포지션과 브로커 포지션 비교
            for holding in actual_holdings:
                stock_code = holding['StockCode']
                actual_amount = holding['StockAmt']
                actual_avg_price = holding['StockAvgPrice']
                
                if stock_code in self.positions:
                    # 포지션 정보 업데이트
                    internal_amount = self.positions[stock_code]['amount']
                    
                    if actual_amount != internal_amount:
                        logger.warning(f"⚠️ {stock_code} 수량 불일치: 내부({internal_amount}) vs 브로커({actual_amount})")
                        
                        if actual_amount == 0:
                            # 브로커에서 모두 매도됨 - 포지션 제거
                            del self.positions[stock_code]
                            logger.info(f"🗑️ {stock_code} 포지션 제거 (브로커에서 매도 완료)")
                        else:
                            # 수량 조정
                            self.positions[stock_code]['amount'] = actual_amount
                            self.positions[stock_code]['entry_price'] = actual_avg_price
                            logger.info(f"🔄 {stock_code} 포지션 동기화 완료")
                
                elif actual_amount > 0:
                    # 브로커에는 있지만 내부 포지션에 없는 경우
                    stock_name = KisKR.GetStockName(stock_code)
                    logger.warning(f"⚠️ {stock_name} 브로커 보유분 발견 - 내부 포지션 생성")
                    
                    self.positions[stock_code] = {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'entry_price': actual_avg_price,
                        'amount': actual_amount,
                        'entry_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'signal_type': 'MANUAL_OR_UNKNOWN',
                        'signal_data': {},
                        'order_num': 'SYNC'
                    }
            
            # 내부 포지션 중 브로커에 없는 것 제거
            broker_codes = {h['StockCode'] for h in actual_holdings if h['StockAmt'] > 0}
            internal_codes = set(self.positions.keys())
            
            for code in internal_codes - broker_codes:
                logger.warning(f"⚠️ {code} 브로커에서 제거됨 - 내부 포지션 삭제")
                del self.positions[code]
            
            self.save_trading_data()
            
        except Exception as e:
            logger.error(f"포지션 동기화 오류: {str(e)}")

    def run_trading_cycle(self):
        """메인 거래 사이클 실행"""
        try:
            logger.info("🔄 거래량 기반 매매 사이클 시작")
            
            # 1. 브로커 포지션 동기화
            self.update_positions_from_broker()
            
            # 2. 현재 보유 포지션 매도 체크
            for stock_code, position_info in list(self.positions.items()):
                try:
                    stock_name = position_info['stock_name']
                    
                    # 매도 조건 체크
                    should_sell, sell_reason, sell_info = self.check_sell_conditions(stock_code, position_info)
                    
                    if should_sell:
                        logger.info(f"📉 {stock_name} 매도 신호: {sell_reason}")
                        success = self.execute_sell_order(stock_code, position_info, sell_info)
                        
                        if success:
                            logger.info(f"✅ {stock_name} 매도 주문 성공")
                        else:
                            logger.error(f"❌ {stock_name} 매도 주문 실패")
                    
                except Exception as e:
                    logger.error(f"매도 체크 오류 ({stock_code}): {str(e)}")
                    continue
            
            # 3. 시장 스캔 및 매수 기회 탐색
            current_positions = len([p for p in self.positions.values() if p.get('amount', 0) > 0])
            max_positions = config.config["max_positions"]
            
            if current_positions < max_positions:
                # 거래량 신호 스캔
                target_stocks = self.scan_market_for_volume_signals()
                
                # 매수 기회 체크
                for stock_info in target_stocks:
                    if current_positions >= max_positions:
                        break
                    
                    stock_code = stock_info['code']
                    stock_name = stock_info['name']
                    
                    # 이미 보유 중이면 스킵
                    if stock_code in self.positions:
                        continue
                    
                    try:
                        # 매수 조건 체크
                        can_buy, buy_info = self.check_buy_conditions(stock_code, stock_name)
                        
                        if can_buy:
                            logger.info(f"📈 {stock_name} 매수 신호: {buy_info['signal_type']}")
                            success = self.execute_buy_order(stock_code, stock_name, buy_info)
                            
                            if success:
                                current_positions += 1
                                logger.info(f"✅ {stock_name} 매수 주문 성공")
                            else:
                                logger.error(f"❌ {stock_name} 매수 주문 실패")
                        
                    except Exception as e:
                        logger.error(f"매수 체크 오류 ({stock_code}): {str(e)}")
                        continue
            
            # 4. 거래 현황 로깅
            self.log_trading_status()
            
            logger.info("✅ 거래량 기반 매매 사이클 완료")
            
        except Exception as e:
            logger.error(f"거래 사이클 실행 오류: {str(e)}")

    def log_trading_status(self):
        """현재 거래 현황 로깅"""
        try:
            current_positions = len(self.positions)
            
            if current_positions > 0:
                logger.info(f"📊 현재 보유 포지션: {current_positions}개")
                
                total_investment = 0
                total_current_value = 0
                
                for stock_code, position in self.positions.items():
                    stock_name = position['stock_name']
                    entry_price = position['entry_price']
                    amount = position['amount']
                    
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price:
                        investment = entry_price * amount
                        current_value = current_price * amount
                        profit_rate = (current_price - entry_price) / entry_price * 100
                        
                        total_investment += investment
                        total_current_value += current_value
                        
                        logger.info(f"   {stock_name}: {profit_rate:+.2f}% ({amount:,}주)")
                
                if total_investment > 0:
                    total_profit_rate = (total_current_value - total_investment) / total_investment * 100
                    logger.info(f"💰 전체 수익률: {total_profit_rate:+.2f}% ({total_current_value - total_investment:+,.0f}원)")
            else:
                logger.info("📊 현재 보유 포지션 없음")
            
            # 오늘 거래 통계
            today = datetime.now().strftime('%Y-%m-%d')
            today_trades = [t for t in self.trading_data if t.get('entry_date', '').startswith(today) or t.get('sell_date', '').startswith(today)]
            
            if today_trades:
                buy_count = len([t for t in today_trades if t['trade_type'] == 'BUY'])
                sell_count = len([t for t in today_trades if t['trade_type'] == 'SELL'])
                logger.info(f"📈 오늘 거래: 매수 {buy_count}건, 매도 {sell_count}건")
            
        except Exception as e:
            logger.error(f"거래 현황 로깅 오류: {str(e)}")

    def send_daily_summary(self):
        """일일 요약 리포트 전송"""
        try:
            if not (config.config["notifications"]["daily_summary_alerts"] and 
                   config.config["notifications"]["use_discord_alert"]):
                return
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 오늘 거래 통계
            today_trades = [t for t in self.trading_data if t.get('sell_date', '').startswith(today)]
            
            summary_msg = f"📊 **거래량 봇 일일 요약** ({today})\n\n"
            
            if today_trades:
                total_profit = sum(t.get('profit', 0) for t in today_trades)
                winning_trades = len([t for t in today_trades if t.get('profit', 0) > 0])
                
                summary_msg += f"💰 오늘 수익: {total_profit:+,.0f}원\n"
                summary_msg += f"📈 거래 건수: {len(today_trades)}건\n"
                summary_msg += f"🎯 승률: {winning_trades/len(today_trades)*100:.1f}%\n\n"
                
                # 수익률 높은 거래 TOP 3
                sorted_trades = sorted(today_trades, key=lambda x: x.get('profit_rate', 0), reverse=True)
                summary_msg += "🏆 **오늘의 베스트 거래**\n"
                for i, trade in enumerate(sorted_trades[:3], 1):
                    summary_msg += f"{i}. {trade['stock_name']}: {trade.get('profit_rate', 0):+.2f}%\n"
                
            else:
                summary_msg += "📭 오늘 매도 거래 없음\n"
            
            # 현재 포지션
            if self.positions:
                summary_msg += f"\n🎯 **현재 보유 포지션** ({len(self.positions)}개)\n"
                for stock_code, position in list(self.positions.items())[:5]:  # 최대 5개만 표시
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price:
                        profit_rate = (current_price - position['entry_price']) / position['entry_price'] * 100
                        summary_msg += f"   {position['stock_name']}: {profit_rate:+.2f}%\n"
            
            # 전체 성과
            tracking = config.config["performance_tracking"]
            summary_msg += f"\n📈 **전체 성과**\n"
            summary_msg += f"총 거래: {tracking.get('total_trades', 0)}건\n"
            summary_msg += f"승률: {tracking.get('winning_trades', 0)/max(tracking.get('total_trades', 1), 1)*100:.1f}%\n"
            summary_msg += f"누적 수익: {tracking.get('total_profit', 0):+,.0f}원"
            
            discord_alert.SendMessage(summary_msg)
            logger.info("📨 일일 요약 리포트 전송 완료")
            
        except Exception as e:
            logger.error(f"일일 요약 전송 오류: {str(e)}")

################################### 메인 실행 함수 ##################################

def main():
    """메인 실행 함수"""
    try:
        logger.info("🚀 거래량 기반 자동매매 봇 시작")
        
        # 봇 인스턴스 생성
        trading_bot = VolumeBasedTradingBot()
        
        # 스케줄 설정
        # 장 중 매 5분마다 거래 사이클 실행
        schedule.every(5).minutes.do(trading_bot.run_trading_cycle)
        
        # 매 30분마다 시장 스캔
        schedule.every(30).minutes.do(trading_bot.scan_market_for_volume_signals)
        
        # 매일 오후 4시에 일일 요약 전송
        schedule.every().day.at("16:00").do(trading_bot.send_daily_summary)
        
        # 시작 알림
        if config.config["notifications"]["use_discord_alert"]:
            start_msg = f"🤖 **거래량 기반 매매봇 시작**\n\n"
            start_msg += f"💰 거래 예산: {config.config['trading_budget']:,}원\n"
            start_msg += f"📊 최대 포지션: {config.config['max_positions']}개\n"
            start_msg += f"⚡ 거래량 급증 기준: {config.config['buy_conditions']['volume_surge_ratio']}배\n"
            start_msg += f"🎯 목표 수익률: {config.config['sell_conditions']['profit_target']}%\n"
            start_msg += f"🛡️ 손절선: {config.config['sell_conditions']['stop_loss']}%\n"
            start_msg += f"🕐 실행 주기: 5분마다"
            discord_alert.SendMessage(start_msg)
        
        # 초기 포지션 동기화
        trading_bot.update_positions_from_broker()
        
        # 무한 루프로 스케줄 실행
        while True:
            try:
                # 현재 시간 체크 (장중에만 실행)
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                
                # 장중 시간 체크 (9:00 ~ 15:30)
                if "09:00" <= current_time <= "15:30":
                    schedule.run_pending()
                elif current_time == "16:00":
                    # 장 마감 후 일일 요약만 실행
                    trading_bot.send_daily_summary()
                
                time.sleep(60)  # 1분마다 체크
                
            except KeyboardInterrupt:
                logger.info("🛑 사용자에 의한 봇 종료")
                
                # 종료 알림
                if config.config["notifications"]["use_discord_alert"]:
                    stop_msg = f"🛑 **거래량 기반 매매봇 종료**\n\n"
                    if trading_bot.positions:
                        stop_msg += f"📊 보유 포지션: {len(trading_bot.positions)}개\n"
                        for stock_code, position in trading_bot.positions.items():
                            current_price = KisKR.GetCurrentPrice(stock_code)
                            if current_price:
                                profit_rate = (current_price - position['entry_price']) / position['entry_price'] * 100
                                stop_msg += f"   {position['stock_name']}: {profit_rate:+.2f}%\n"
                    else:
                        stop_msg += "📊 보유 포지션 없음"
                    
                    discord_alert.SendMessage(stop_msg)
                
                break
                
            except Exception as e:
                logger.error(f"스케줄 실행 오류: {str(e)}")
                time.sleep(300)  # 5분 대기 후 재시도
                continue
    
    except Exception as e:
        logger.error(f"메인 실행 오류: {str(e)}")
        
        # 오류 알림
        if config.config["notifications"]["use_discord_alert"]:
            error_msg = f"🚨 **거래량 봇 오류 발생**\n\n"
            error_msg += f"❌ 오류 내용: {str(e)}\n"
            error_msg += f"🔧 봇 재시작이 필요할 수 있습니다."
            discord_alert.SendMessage(error_msg)

################################### 추가 유틸리티 함수 ##################################

def create_volume_analysis_report(stock_code, days=30):
    """특정 종목의 거래량 분석 리포트 생성"""
    try:
        logger.info(f"📊 {stock_code} 거래량 분석 리포트 생성 중...")
        
        # 분석 엔진 초기화
        analysis_engine = VolumeAnalysisEngine()
        
        # 거래량 데이터 조회
        df = analysis_engine.get_volume_data(stock_code, "daily", days)
        if df is None:
            return "데이터 조회 실패"
        
        stock_name = KisKR.GetStockName(stock_code)
        
        # 분석 결과
        report = f"📈 **{stock_name} ({stock_code}) 거래량 분석 리포트**\n\n"
        
        # 기본 통계
        avg_volume = df['volume'].mean()
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume
        
        report += f"📊 **거래량 통계**\n"
        report += f"평균 거래량: {avg_volume:,.0f}주\n"
        report += f"현재 거래량: {current_volume:,.0f}주\n"
        report += f"거래량 비율: {volume_ratio:.2f}배\n\n"
        
        # 패턴 분석
        surge_detected, surge_info = analysis_engine.detect_volume_surge_pattern(stock_code)
        pullback_detected, pullback_info = analysis_engine.detect_pullback_opportunity(stock_code)
        distribution_detected, dist_info = analysis_engine.detect_distribution_pattern(stock_code)
        
        report += f"🔍 **패턴 분석 결과**\n"
        report += f"거래량 급증 패턴: {'✅ 감지' if surge_detected else '❌ 미감지'}\n"
        report += f"눌림목 기회: {'✅ 발견' if pullback_detected else '❌ 없음'}\n"
        report += f"분배 패턴: {'⚠️ 감지' if distribution_detected else '✅ 없음'}\n\n"
        
        # 상세 정보
        if surge_detected:
            report += f"⚡ **급증 패턴 상세**\n"
            report += f"패턴 타입: {surge_info.get('pattern_type', 'Unknown')}\n"
            report += f"거래량 비율: {surge_info.get('volume_surge_ratio', 0):.1f}배\n"
            report += f"가격 변동: {surge_info.get('price_change', 0):+.2f}%\n\n"
        
        if pullback_detected:
            report += f"📉 **눌림목 상세**\n"
            report += f"급증 후 경과: {pullback_info.get('days_since_surge', 0)}일\n"
            report += f"가격 조정: {pullback_info.get('price_pullback', 0):.2f}%\n\n"
        
        if distribution_detected:
            report += f"⚠️ **분배 패턴 상세**\n"
            report += f"고점 비율: {dist_info.get('high_ratio', 0):.2f}\n"
            report += f"거래량 급증: {dist_info.get('volume_surge_ratio', 0):.1f}배\n\n"
        
        # 투자 제안
        current_price = KisKR.GetCurrentPrice(stock_code)
        if current_price:
            # RSI 계산
            if len(df) >= 14:
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta).where(delta < 0, 0).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1]
                
                report += f"💡 **투자 제안**\n"
                report += f"현재가: {current_price:,}원\n"
                report += f"RSI: {current_rsi:.1f}\n"
                
                if surge_detected and current_rsi < 75:
                    report += f"🟢 매수 검토 권장 (거래량 급증 + RSI 적정)\n"
                elif pullback_detected:
                    report += f"🟡 눌림목 매수 기회 (조정 후 재진입)\n"
                elif distribution_detected:
                    report += f"🔴 매도 검토 권장 (분배 패턴 감지)\n"
                else:
                    report += f"⚪ 관망 권장 (명확한 신호 없음)\n"
        
        return report
        
    except Exception as e:
        logger.error(f"리포트 생성 오류: {str(e)}")
        return f"리포트 생성 실패: {str(e)}"

def emergency_stop_all_trading():
    """긴급 정지 - 모든 거래 중단"""
    try:
        logger.warning("🚨 긴급 정지 실행 - 모든 거래 중단")
        
        # 설정 파일에 긴급정지 플래그 추가
        config.config["emergency_stop"] = True
        config.config["emergency_stop_time"] = datetime.now().isoformat()
        config.save_config()
        
        # Discord 알림
        if config.config["notifications"]["use_discord_alert"]:
            emergency_msg = f"🚨 **긴급 정지 발동** 🚨\n\n"
            emergency_msg += f"⏰ 정지 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            emergency_msg += f"🛑 모든 자동 거래 중단\n"
            emergency_msg += f"🔧 수동으로 emergency_stop 플래그를 False로 변경하여 재개"
            discord_alert.SendMessage(emergency_msg)
        
        return True
        
    except Exception as e:
        logger.error(f"긴급 정지 실행 오류: {str(e)}")
        return False

def check_emergency_stop():
    """긴급 정지 상태 확인"""
    return config.config.get("emergency_stop", False)

################################### 실행 부분 ##################################

if __name__ == "__main__":
    try:
        # 긴급 정지 상태 체크
        if check_emergency_stop():
            logger.warning("🚨 긴급 정지 상태입니다. emergency_stop 플래그를 False로 변경해주세요.")
            exit(1)
        
        # 메인 함수 실행
        main()
        
    except Exception as e:
        logger.error(f"프로그램 실행 오류: {str(e)}")
        
        # 최종 오류 알림
        try:
            if config.config["notifications"]["use_discord_alert"]:
                final_error_msg = f"💥 **거래량 봇 치명적 오류**\n\n"
                final_error_msg += f"❌ {str(e)}\n"
                final_error_msg += f"🔄 프로그램 재시작 필요"
                discord_alert.SendMessage(final_error_msg)
        except:
            pass  # 알림 전송 실패해도 무시
        
        exit(1)