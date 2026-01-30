#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
키움 스마트 매직 스플릿 봇 (SmartMagicSplitBot_Kiwoom)
- 한투 test.py를 키움 API로 변환
- 5단계 분할매수 시스템
- 적응형 손절 시스템
- 브로커 데이터 동기화
- 미체결 주문 자동 관리
"""

import Kiwoom_Common as Common
import Kiwoom_API_Helper_KR
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
logger = logging.getLogger('SmartMagicSplitKiwoomLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'smart_magic_split_kiwoom.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=3,
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

try:
    KiwoomAPI = Kiwoom_API_Helper_KR.Kiwoom_Common(log_level=logging.INFO)
    
    # 설정 로드
    if not KiwoomAPI.LoadConfigData():
        logger.error("❌ 키움 API 설정 로드 실패")
        exit(1)
    
    # 토큰 발급
    if not KiwoomAPI.GetAccessToken():
        logger.error("❌ 키움 API 토큰 발급 실패")
        exit(1)
    
    logger.info("✅ 키움 API 초기화 성공")
except Exception as e:
    logger.error(f"❌ 키움 API 초기화 중 오류: {str(e)}")
    exit(1)

################################### 통합된 설정 관리 시스템 ##################################

class ConfigManager:
    """통합 설정 관리자 - JSON 기반"""
    
    def __init__(self, config_file='smart_magic_config.json'):
        self.config_file = config_file
        self.config = self.load_config()
        
        # 기본 설정 구조
        self.default_config = {
            "bot_name": "SmartMagicSplitBot_Kiwoom",
            "absolute_budget": 10000000,  # 절대 예산 (1천만원)
            "use_discord_alert": True,
            "market_timing_weight": 0.3,
            "technical_weight": 0.4,
            "sector_weight": 0.3,
            
            # 종목별 설정
            "target_stocks": {
                "005930": {  # 삼성전자
                    "name": "삼성전자",
                    "weight": 0.5,
                    "enabled": True
                },
                "000660": {  # SK하이닉스
                    "name": "SK하이닉스", 
                    "weight": 0.5,
                    "enabled": True
                }
            },
            
            # 동적 조정 설정
            "dynamic_adjustment": {
                "enabled": True,
                "min_ratio": 0.7,
                "max_ratio": 1.4,
                "evaluation_period_days": 30
            },
            
            # 매매 설정
            "trading_settings": {
                "commission_rate": 0.00015,
                "sell_tax_rate": 0.0023,
                "cooldown_hours": 24,
                "max_decline_for_next_buy": 0.05
            },
            
            # 성과 추적
            "performance_tracking": {
                "initial_budget": 10000000,
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "total_trades": 0,
                "winning_trades": 0,
                "total_pnl": 0
            },
            
            # 개선 통계
            "enhanced_metrics": {
                "cooldown_prevented_trades": 0,
                "sequential_blocked_trades": 0,
                "broker_sync_corrections": 0
            }
        }
        
        # 설정 업그레이드
        self._upgrade_config_if_needed()
    
    def load_config(self):
        """설정 파일 로드"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.info("설정 파일 없음, 기본 설정으로 초기화")
                return {}
        except Exception as e:
            logger.error(f"설정 로드 실패: {str(e)}")
            return {}
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.debug("✅ 설정 저장 완료")
        except Exception as e:
            logger.error(f"설정 저장 실패: {str(e)}")
    
    def _upgrade_config_if_needed(self):
        """설정 구조 업그레이드"""
        is_modified = False
        
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
                is_modified = True
                logger.info(f"설정 추가: {key}")
        
        if is_modified:
            self.save_config()
    
    def get(self, key, default=None):
        """설정 값 가져오기"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """설정 값 저장하기"""
        self.config[key] = value
        self.save_config()
    
    def update_performance(self, metric, value):
        """성과 업데이트"""
        if 'performance_tracking' not in self.config:
            self.config['performance_tracking'] = self.default_config['performance_tracking'].copy()
        
        self.config['performance_tracking'][metric] = value
        self.save_config()
    
    def update_enhanced_metrics(self, metric, increment=1):
        """개선 통계 업데이트"""
        if 'enhanced_metrics' not in self.config:
            self.config['enhanced_metrics'] = self.default_config['enhanced_metrics'].copy()
        
        current = self.config['enhanced_metrics'].get(metric, 0)
        self.config['enhanced_metrics'][metric] = current + increment
        self.save_config()

# 전역 설정 인스턴스
config = ConfigManager()

BOT_NAME = config.get("bot_name", "SmartMagicSplitBot_Kiwoom")

logger.info("="*60)
logger.info(f"🤖 {BOT_NAME} 시작")
logger.info(f"💰 절대 예산: {config.get('absolute_budget'):,}원")
logger.info("="*60)

################################### 키움 API 래퍼 함수 ##################################

def GetBalance():
    """잔고 조회 - 키움 API"""
    try:
        balance_data = KiwoomAPI.GetBalance()
        if balance_data:
            return {
                'RemainMoney': str(balance_data.get('OrderableAmt', 0)),
                'OrderableAmt': str(balance_data.get('OrderableAmt', 0)),
                'Deposit': str(balance_data.get('Deposit', 0))
            }
        return {'RemainMoney': '0', 'OrderableAmt': '0', 'Deposit': '0'}
    except Exception as e:
        logger.error(f"잔고 조회 오류: {str(e)}")
        return {'RemainMoney': '0', 'OrderableAmt': '0', 'Deposit': '0'}

def GetMyStockList():
    """보유 종목 리스트 조회 - 키움 API"""
    try:
        stock_list = KiwoomAPI.GetMyStockList()
        if not stock_list:
            return []
        
        # 한투 형식으로 변환
        result = []
        for stock in stock_list:
            result.append({
                'StockCode': stock['StockCode'],
                'StockName': stock['StockName'],
                'StockAmt': stock['StockQty'],
                'StockAvgPrice': stock['BuyPrice'],
                'StockNowPrice': stock['CurrentPrice'],
                'StockRevenueMoney': stock['ProfitLoss'],
                'StockRevenueRate': stock['ProfitRate']
            })
        return result
    except Exception as e:
        logger.error(f"보유 종목 조회 오류: {str(e)}")
        return []

def GetCurrentPrice(stock_code):
    """현재가 조회 - 키움 API"""
    try:
        stock_info = KiwoomAPI.GetStockInfo(stock_code)
        if stock_info:
            return stock_info['CurrentPrice']
        return 0
    except Exception as e:
        logger.error(f"현재가 조회 오류 ({stock_code}): {str(e)}")
        return 0

def GetStockName(stock_code):
    """종목명 조회 - 키움 API"""
    try:
        stock_info = KiwoomAPI.GetStockInfo(stock_code)
        if stock_info:
            return stock_info['StockName']
        return stock_code
    except Exception as e:
        logger.error(f"종목명 조회 오류 ({stock_code}): {str(e)}")
        return stock_code

def MakeBuyLimitOrder(stock_code, amount, price):
    """지정가 매수 - 키움 API"""
    try:
        result = Common.Buy(stock_code, amount, price, order_type="limit")
        if result:
            return {
                'OrderNum': result.get('order_no', ''),
                'OrderNum2': result.get('order_no', ''),
                'OrderTime': datetime.now().strftime("%H:%M:%S")
            }
        return None
    except Exception as e:
        logger.error(f"매수 주문 오류 ({stock_code}): {str(e)}")
        return None

def MakeSellLimitOrder(stock_code, amount, price):
    """지정가 매도 - 키움 API"""
    try:
        result = Common.Sell(stock_code, amount, price, order_type="limit")
        if result:
            return {
                'OrderNum': result.get('order_no', ''),
                'OrderNum2': result.get('order_no', ''),
                'OrderTime': datetime.now().strftime("%H:%M:%S")
            }
        return None
    except Exception as e:
        logger.error(f"매도 주문 오류 ({stock_code}): {str(e)}")
        return None

def GetOhlcv(stock_code, period='D', count=100):
    """OHLCV 데이터 조회 - Common 모듈 사용"""
    try:
        # KiwoomAPI.GetOhlcv 사용 (기존 로직 활용)
        df = KiwoomAPI.GetOhlcv("KR", stock_code, count)
        if df is not None and len(df) > 0:
            return df
        return None
    except Exception as e:
        logger.error(f"OHLCV 조회 오류 ({stock_code}): {str(e)}")
        return None

################################### 키움 API 래퍼 함수 끝 ##################################

################################### 스마트 매직 스플릿 봇 클래스 ##################################

class SmartMagicSplitBot:
    """
    키움 스마트 매직 스플릿 봇
    - 5단계 분할매수
    - 적응형 손절
    - 브로커 동기화
    """
    
    def __init__(self):
        # 절대 예산 기반 총 투자금
        self.total_money = config.get("absolute_budget", 10000000)
        
        # 분할 매매 데이터
        self.split_data_list = self.load_split_data()
        
        # JSON 구조 업그레이드
        self._upgrade_json_structure_if_needed()
        
        # 미체결 주문 추적
        self.pending_orders = {}
        
        # 시장 타이밍 캐시
        self._current_market_timing = None
        self._market_timing_update_time = None
        
        logger.info(f"봇 초기화 완료 - 총 투자금: {self.total_money:,}원")
    
    def save_split_data(self):
        """안전한 데이터 저장"""
        try:
            bot_file_path = f"KrStock_{BOT_NAME}.json"
            
            # 🔥 1. 백업 파일 생성
            backup_path = f"{bot_file_path}.backup"
            if os.path.exists(bot_file_path):
                try:
                    import shutil
                    shutil.copy2(bot_file_path, backup_path)
                    logger.debug(f"📁 백업 파일 생성: {backup_path}")
                except Exception as backup_e:
                    logger.warning(f"백업 파일 생성 실패: {str(backup_e)}")
            
            # 🔥 2. 임시 파일에 먼저 저장
            temp_path = f"{bot_file_path}.temp"
            with open(temp_path, 'w', encoding='utf-8') as temp_file:
                json.dump(self.split_data_list, temp_file, ensure_ascii=False, indent=2)
            
            # 🔥 3. JSON 유효성 검증
            with open(temp_path, 'r', encoding='utf-8') as verify_file:
                test_data = json.load(verify_file)
                if not isinstance(test_data, list):
                    raise ValueError("저장된 데이터가 올바른 형식이 아닙니다")
            
            # 🔥 4. 원자적 교체
            if os.name == 'nt':  # Windows
                if os.path.exists(bot_file_path):
                    os.remove(bot_file_path)
            os.rename(temp_path, bot_file_path)
            
            # 🔥 5. 최종 검증
            with open(bot_file_path, 'r', encoding='utf-8') as final_verify:
                json.load(final_verify)
            
            logger.debug("✅ 안전한 데이터 저장 완료")
            
        except Exception as e:
            logger.error(f"❌ 데이터 저장 중 오류: {str(e)}")
            
            # 🔥 복구 시도
            try:
                temp_path = f"{bot_file_path}.temp"
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                backup_path = f"{bot_file_path}.backup"
                if os.path.exists(backup_path):
                    import shutil
                    shutil.copy2(backup_path, bot_file_path)
                    logger.info("📁 백업 파일로 복구 완료")
            except Exception as recovery_e:
                logger.error(f"복구 시도 중 오류: {str(recovery_e)}")
    
    def load_split_data(self):
        """저장된 매매 데이터 로드"""
        try:
            bot_file_path = f"KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'r', encoding='utf-8') as json_file:
                return json.load(json_file)
        except Exception:
            return []
    
    def _upgrade_json_structure_if_needed(self):
        """JSON 구조 업그레이드"""
        is_modified = False
        
        for stock_data in self.split_data_list:
            for magic_data in stock_data['MagicDataList']:
                # CurrentAmt 필드 추가
                if 'CurrentAmt' not in magic_data and magic_data['IsBuy']:
                    magic_data['CurrentAmt'] = magic_data['EntryAmt']
                    is_modified = True
                
                # SellHistory 필드 추가
                if 'SellHistory' not in magic_data:
                    magic_data['SellHistory'] = []
                    is_modified = True
        
        if is_modified:
            self.save_split_data()
            logger.info("✅ JSON 구조 업그레이드 완료")
    
    def get_current_holdings(self, stock_code):
        """현재 보유 정보 조회"""
        try:
            stock_list = GetMyStockList()
            
            for stock in stock_list:
                if stock['StockCode'] == stock_code:
                    return {
                        'amount': int(stock['StockAmt']),
                        'avg_price': float(stock['StockAvgPrice']),
                        'revenue_rate': float(stock.get('StockRevenueRate', 0)),
                        'revenue_money': float(stock.get('StockRevenueMoney', 0))
                    }
            
            return {'amount': 0, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0}
        except Exception as e:
            logger.error(f"보유 정보 조회 오류: {str(e)}")
            return {'amount': 0, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0}
    
    def calculate_trading_fee(self, price, amount, is_buy=True):
        """거래 수수료 계산"""
        trading_settings = config.get("trading_settings", {})
        commission_rate = trading_settings.get("commission_rate", 0.00015)
        sell_tax_rate = trading_settings.get("sell_tax_rate", 0.0023)
        
        total_value = price * amount
        commission = total_value * commission_rate
        
        if is_buy:
            return commission
        else:
            tax = total_value * sell_tax_rate
            return commission + tax
    
    def get_technical_indicators(self, stock_code):
        """기술적 지표 계산"""
        try:
            df = GetOhlcv(stock_code, 'D', 100)
            
            if df is None or len(df) < 20:
                logger.warning(f"{stock_code} OHLCV 데이터 부족")
                return None
            
            current_price = df['close'].iloc[-1]
            
            # RSI 계산
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]
            
            # 이동평균선
            ma5 = df['close'].rolling(window=5).mean().iloc[-1]
            ma20 = df['close'].rolling(window=20).mean().iloc[-1]
            ma60 = df['close'].rolling(window=60).mean().iloc[-1] if len(df) >= 60 else ma20
            
            # 변동성
            volatility = df['close'].pct_change().std() * 100
            
            # 거래량 분석
            volume_ma20 = df['volume'].rolling(window=20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / volume_ma20 if volume_ma20 > 0 else 1.0
            
            indicators = {
                'current_price': current_price,
                'rsi': current_rsi,
                'ma5': ma5,
                'ma20': ma20,
                'ma60': ma60,
                'volatility': volatility,
                'volume_ratio': volume_ratio
            }
            
            return indicators
            
        except Exception as e:
            logger.error(f"기술적 지표 계산 오류 ({stock_code}): {str(e)}")
            return None
    
    def detect_market_timing(self):
        """시장 타이밍 감지"""
        try:
            # 캐시 확인 (5분마다 갱신)
            if self._market_timing_update_time:
                elapsed = (datetime.now() - self._market_timing_update_time).total_seconds()
                if elapsed < 300:  # 5분
                    return self._current_market_timing
            
            # KOSPI 지수로 시장 분석
            kospi_df = GetOhlcv("005930", 'D', 60)  # 삼성전자로 대체
            
            if kospi_df is None or len(kospi_df) < 30:
                logger.warning("시장 타이밍 데이터 부족")
                return "neutral"
            
            current_price = kospi_df['close'].iloc[-1]
            ma5 = kospi_df['close'].rolling(window=5).mean().iloc[-1]
            ma20 = kospi_df['close'].rolling(window=20).mean().iloc[-1]
            ma60 = kospi_df['close'].rolling(window=60).mean().iloc[-1]
            
            trend_score = 0
            
            # 이동평균 정배열 체크
            if current_price > ma5 > ma20:
                trend_score += 2
            if ma5 > ma20 > ma60:
                trend_score += 1
            
            # 하락 체크
            if current_price < ma5 < ma20:
                trend_score -= 2
            if ma5 < ma20 < ma60:
                trend_score -= 1
            
            # 최종 추세 판정
            if trend_score >= 2:
                market_trend = "uptrend"
            elif trend_score >= -1:
                market_trend = "neutral"
            else:
                market_trend = "downtrend"
            
            # 캐시 업데이트
            self._current_market_timing = market_trend
            self._market_timing_update_time = datetime.now()
            
            logger.debug(f"시장 타이밍: {market_trend} (점수: {trend_score})")
            return market_trend
            
        except Exception as e:
            logger.error(f"시장 타이밍 감지 오류: {str(e)}")
            return "neutral"
    
    def calculate_adaptive_stop_loss_threshold(self, stock_code, position_count, holding_days):
        """적응형 손절선 계산"""
        try:
            # 기본 손절선: -7%
            base_stop_loss = -7.0
            
            # 보유 기간에 따른 조정
            if holding_days <= 5:
                time_adjustment = 1.0  # 짧은 보유: 엄격
            elif holding_days <= 15:
                time_adjustment = 1.2  # 중간: 약간 완화
            else:
                time_adjustment = 1.5  # 장기: 완화
            
            # 포지션 수에 따른 조정
            if position_count == 1:
                position_adjustment = 0.8  # 1차수만: 엄격
            elif position_count <= 3:
                position_adjustment = 1.0
            else:
                position_adjustment = 1.3  # 다차수: 완화
            
            # 시장 상황 반영
            market_timing = self.detect_market_timing()
            if market_timing == "downtrend":
                market_adjustment = 0.7  # 하락장: 엄격
            elif market_timing == "uptrend":
                market_adjustment = 1.3  # 상승장: 완화
            else:
                market_adjustment = 1.0
            
            # 최종 손절선 계산
            final_threshold = base_stop_loss * time_adjustment * position_adjustment * market_adjustment
            
            # 범위 제한: -15% ~ -3%
            final_threshold = max(-15.0, min(-3.0, final_threshold))
            
            threshold_desc = f"기본:{base_stop_loss}% × 보유기간:{time_adjustment} × 차수:{position_adjustment} × 시장:{market_adjustment}"
            
            return final_threshold, threshold_desc
            
        except Exception as e:
            logger.error(f"적응형 손절선 계산 오류: {str(e)}")
            return -7.0, "기본 손절선"
    
    def check_cooldown_period(self, stock_code, magic_data_list):
        """재매수 쿨다운 체크"""
        try:
            trading_settings = config.get("trading_settings", {})
            cooldown_hours = trading_settings.get("cooldown_hours", 24)
            
            for magic_data in magic_data_list:
                if not magic_data.get('SellHistory'):
                    continue
                
                # 가장 최근 매도 확인
                last_sell = magic_data['SellHistory'][-1]
                sell_date_str = f"{last_sell['date']} {last_sell['time']}"
                
                try:
                    sell_datetime = datetime.strptime(sell_date_str, "%Y-%m-%d %H:%M:%S")
                except:
                    continue
                
                elapsed_hours = (datetime.now() - sell_datetime).total_seconds() / 3600
                
                if elapsed_hours < cooldown_hours:
                    remaining = cooldown_hours - elapsed_hours
                    return False, f"쿨다운 중 (남은 시간: {remaining:.1f}시간)"
            
            return True, "쿨다운 통과"
            
        except Exception as e:
            logger.error(f"쿨다운 체크 오류: {str(e)}")
            return True, "오류로 인한 허용"
    
    def check_sequential_entry_validation(self, stock_code, position_num, indicators):
        """순차 진입 검증"""
        try:
            if position_num <= 1:
                return True, "1차수는 항상 허용"
            
            # 종목 데이터 찾기
            stock_data = None
            for data in self.split_data_list:
                if data['StockCode'] == stock_code:
                    stock_data = data
                    break
            
            if not stock_data:
                return False, "종목 데이터 없음"
            
            magic_data_list = stock_data['MagicDataList']
            prev_position = magic_data_list[position_num - 2]
            
            # 이전 차수 보유 여부
            if not prev_position.get('IsBuy', False):
                return False, f"{position_num-1}차 미보유"
            
            # 이전 차수 대비 하락률 체크
            prev_entry_price = prev_position['EntryPrice']
            current_price = indicators['current_price']
            decline_rate = (current_price - prev_entry_price) / prev_entry_price
            
            # 동적 하락률 (시장 상황 반영)
            market_timing = self.detect_market_timing()
            trading_settings = config.get("trading_settings", {})
            
            if market_timing == "downtrend":
                required_decline = trading_settings.get("max_decline_for_next_buy", 0.05) * 0.7
            elif market_timing == "uptrend":
                required_decline = trading_settings.get("max_decline_for_next_buy", 0.05) * 1.5
            else:
                required_decline = trading_settings.get("max_decline_for_next_buy", 0.05)
            
            if decline_rate > -required_decline:
                return False, f"하락률 부족 (현재:{decline_rate*100:.1f}%, 필요:{-required_decline*100:.1f}%)"
            
            return True, f"하락률 충족 ({decline_rate*100:.1f}%)"
            
        except Exception as e:
            logger.error(f"순차 진입 검증 오류: {str(e)}")
            return False, f"오류: {str(e)}"
    
    def should_buy_enhanced(self, stock_code, position_num, indicators, magic_data_list, stock_info):
        """향상된 매수 판단"""
        try:
            current_price = indicators['current_price']
            rsi = indicators['rsi']
            
            # 1차수 매수 조건
            if position_num == 1:
                # RSI 과매도
                if rsi < 30:
                    return True, f"RSI과매도({rsi:.1f})"
                
                # 이동평균 지지
                if current_price < indicators['ma20'] * 0.97:
                    return True, f"MA20지지선({current_price/indicators['ma20']*100:.1f}%)"
                
                return False, "1차 매수 조건 미달"
            
            # 2차수 이상: 이전 차수 대비 하락
            prev_position = magic_data_list[position_num - 2]
            if not prev_position.get('IsBuy', False):
                return False, "이전 차수 미보유"
            
            prev_entry_price = prev_position['EntryPrice']
            decline_rate = (current_price - prev_entry_price) / prev_entry_price
            
            # 차수별 요구 하락률
            required_declines = {
                2: -0.05,  # 2차: -5%
                3: -0.07,  # 3차: -7%
                4: -0.10,  # 4차: -10%
                5: -0.15   # 5차: -15%
            }
            
            required_decline = required_declines.get(position_num, -0.05)
            
            if decline_rate <= required_decline:
                return True, f"{position_num}차하락조건충족({decline_rate*100:.1f}%)"
            
            return False, f"하락률 부족({decline_rate*100:.1f}%)"
            
        except Exception as e:
            logger.error(f"매수 판단 오류: {str(e)}")
            return False, f"오류: {str(e)}"

    def handle_buy(self, stock_code, amount, price):
        """매수 주문 처리"""
        try:
            result = MakeBuyLimitOrder(stock_code, amount, price)
            
            if result:
                # 체결 확인을 위해 대기
                time.sleep(2)
                
                # 실제 체결가 확인
                holdings = self.get_current_holdings(stock_code)
                actual_price = holdings.get('avg_price', price)
                
                return True, amount
            else:
                return False, 0
                
        except Exception as e:
            logger.error(f"매수 처리 오류: {str(e)}")
            return False, 0
    
    def handle_sell(self, stock_code, amount, price):
        """매도 주문 처리"""
        try:
            result = MakeSellLimitOrder(stock_code, amount, price)
            
            if result:
                time.sleep(2)
                return True, None
            else:
                return False, "매도 주문 실패"
                
        except Exception as e:
            logger.error(f"매도 처리 오류: {str(e)}")
            return False, str(e)
    
    def process_stop_loss_logic(self, stock_code, stock_info, magic_data_list, indicators, holdings):
        """적응형 손절 로직"""
        try:
            current_price = indicators['current_price']
            target_stocks = config.get('target_stocks', {})
            stock_name = target_stocks.get(stock_code, {}).get('name', stock_code)
            
            sells_executed = False
            
            for magic_data in magic_data_list:
                if not magic_data.get('IsBuy', False):
                    continue
                
                position_num = magic_data['Number']
                entry_price = magic_data['EntryPrice']
                current_amount = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                
                if current_amount <= 0:
                    continue
                
                # 수익률 계산
                individual_return = (current_price - entry_price) / entry_price * 100
                
                # 보유 기간 계산
                entry_date_str = magic_data.get('EntryDate', '')
                holding_days = 0
                if entry_date_str:
                    try:
                        entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
                        holding_days = (datetime.now() - entry_date).days
                    except:
                        holding_days = 0
                
                # 활성 포지션 수
                active_positions = [m for m in magic_data_list if m.get('IsBuy', False) and m.get('CurrentAmt', 0) > 0]
                position_count = len(active_positions)
                
                # 적응형 손절선 계산
                stop_threshold, threshold_desc = self.calculate_adaptive_stop_loss_threshold(
                    stock_code, position_count, holding_days
                )
                
                # 손절 조건 체크
                if individual_return <= stop_threshold:
                    logger.warning(f"🚨 {stock_name} {position_num}차 적응형 손절 발동!")
                    logger.warning(f"   수익률: {individual_return:.2f}% ≤ 손절선: {stop_threshold:.2f}%")
                    logger.warning(f"   {threshold_desc}")
                    
                    # 매도 실행
                    result, error = self.handle_sell(stock_code, current_amount, current_price)
                    
                    if result:
                        # 손절 기록
                        sell_record = {
                            'date': datetime.now().strftime("%Y-%m-%d"),
                            'time': datetime.now().strftime("%H:%M:%S"),
                            'price': current_price,
                            'amount': current_amount,
                            'reason': f"{position_num}차 적응형손절",
                            'return_pct': individual_return,
                            'entry_price': entry_price,
                            'stop_threshold': stop_threshold,
                            'threshold_desc': threshold_desc,
                            'holding_days': holding_days,
                            'position_count': position_count,
                            'stop_type': 'adaptive_stop_loss'
                        }
                        
                        if 'SellHistory' not in magic_data:
                            magic_data['SellHistory'] = []
                        magic_data['SellHistory'].append(sell_record)
                        
                        # 포지션 정리
                        magic_data['CurrentAmt'] = 0
                        magic_data['IsBuy'] = False
                        
                        self.save_split_data()
                        
                        # 알림
                        msg = f"🚨 **적응형 손절 실행** 🚨\n"
                        msg += f"종목: {stock_name}\n"
                        msg += f"차수: {position_num}차\n"
                        msg += f"수익률: {individual_return:.2f}%\n"
                        msg += f"손절선: {stop_threshold:.2f}%\n"
                        msg += f"사유: {threshold_desc}"
                        
                        logger.warning(msg)
                        if config.config.get("use_discord_alert", True):
                            discord_alert.SendMessage(msg)
                        
                        sells_executed = True
            
            return sells_executed
            
        except Exception as e:
            logger.error(f"손절 로직 오류: {str(e)}")
            return False
    
    def run_strategy(self):
        """메인 전략 실행"""
        try:
            target_stocks = config.get('target_stocks', {})
            
            # 잔고 조회
            balance = GetBalance()
            remain_money = float(balance.get('RemainMoney', 0))
            
            logger.info(f"💰 현재 잔고: {remain_money:,}원")
            
            for stock_code, stock_info in target_stocks.items():
                if not stock_info.get('enabled', True):
                    continue
                
                stock_name = stock_info.get('name', stock_code)
                
                # 기술적 지표 계산
                indicators = self.get_technical_indicators(stock_code)
                if not indicators:
                    logger.warning(f"❌ {stock_name} 기술적 지표 계산 실패")
                    continue
                
                # 현재 보유 정보
                holdings = self.get_current_holdings(stock_code)
                
                # 종목 데이터 찾기/생성
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                if stock_data_info is None:
                    # 새 종목 데이터 생성
                    magic_data_list = []
                    for i in range(5):
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
                        'RealizedPNL': 0
                    }
                    
                    self.split_data_list.append(stock_data_info)
                    self.save_split_data()
                    
                    logger.info(f"🎯 {stock_name} 스마트스플릿 준비 완료!")
                
                magic_data_list = stock_data_info['MagicDataList']
                
                # 🔥 1단계: 손절 로직
                stop_loss_executed = self.process_stop_loss_logic(
                    stock_code, stock_info, magic_data_list, indicators, holdings
                )
                
                if stop_loss_executed:
                    continue  # 손절 실행 시 매수 스킵
                
                # 🔥 2단계: 쿨다운 체크
                cooldown_ok, cooldown_msg = self.check_cooldown_period(stock_code, magic_data_list)
                if not cooldown_ok:
                    logger.debug(f"⏰ {stock_name} {cooldown_msg}")
                    config.update_enhanced_metrics("cooldown_prevented_trades", 1)
                    continue
                
                # 🔥 3단계: 매수 로직
                total_budget = self.total_money * stock_info['weight']
                
                for i, magic_data in enumerate(magic_data_list):
                    if magic_data['IsBuy']:
                        continue  # 이미 보유 중
                    
                    position_num = i + 1
                    
                    # 순차 진입 검증
                    if position_num > 1:
                        sequential_ok, sequential_reason = self.check_sequential_entry_validation(
                            stock_code, position_num, indicators
                        )
                        
                        if not sequential_ok:
                            logger.debug(f"🚫 {stock_name} {position_num}차 순차 검증 실패: {sequential_reason}")
                            continue
                    
                    # 매수 조건 판단
                    should_buy, buy_reason = self.should_buy_enhanced(
                        stock_code, position_num, indicators, magic_data_list, stock_info
                    )
                    
                    if should_buy:
                        # 투자 비중 (역피라미드)
                        investment_ratios = {1: 0.15, 2: 0.18, 3: 0.22, 4: 0.25, 5: 0.20}
                        investment_ratio = investment_ratios.get(position_num, 0.20)
                        
                        invest_amount = total_budget * investment_ratio
                        buy_amt = max(1, int(invest_amount / indicators['current_price']))
                        
                        estimated_fee = self.calculate_trading_fee(indicators['current_price'], buy_amt, True)
                        total_cost = (indicators['current_price'] * buy_amt) + estimated_fee
                        
                        logger.info(f"💰 {stock_name} {position_num}차 매수 시도:")
                        logger.info(f"   필요 자금: {total_cost:,}원, 보유 현금: {remain_money:,}원")
                        logger.info(f"   매수 이유: {buy_reason}")
                        
                        if total_cost <= remain_money:
                            success, executed_amount = self.handle_buy(
                                stock_code, buy_amt, indicators['current_price']
                            )
                            
                            if success and executed_amount:
                                # 데이터 업데이트
                                magic_data['IsBuy'] = True
                                magic_data['EntryPrice'] = indicators['current_price']
                                magic_data['EntryAmt'] = executed_amount
                                magic_data['CurrentAmt'] = executed_amount
                                magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                
                                self.save_split_data()
                                
                                msg = f"🚀 {stock_name} {position_num}차 매수 완료!\n"
                                msg += f"  💰 {indicators['current_price']:,.0f}원 × {executed_amount:,}주\n"
                                msg += f"  📊 투자비중: {investment_ratio*100:.1f}%\n"
                                msg += f"  🎯 {buy_reason}"
                                
                                logger.info(msg)
                                if config.config.get("use_discord_alert", True):
                                    discord_alert.SendMessage(msg)
                                
                                break  # 한 종목당 한 번만 매수
                
        except Exception as e:
            logger.error(f"전략 실행 오류: {str(e)}")

################################### 메인 실행 ##################################

def main():
    """메인 실행 함수"""
    bot_instance = SmartMagicSplitBot()
    
    logger.info("="*60)
    logger.info(f"🤖 {BOT_NAME} 시작")
    logger.info("="*60)
    
    # 시작 메시지
    if config.config.get("use_discord_alert", True):
        start_msg = f"🚀 **{BOT_NAME} 시작**\n"
        start_msg += f"💰 절대 예산: {config.get('absolute_budget'):,}원\n"
        start_msg += f"📊 투자 종목: {len(config.get('target_stocks', {}))}개"
        discord_alert.SendMessage(start_msg)
    
    def job():
        """스케줄 작업"""
        try:
            # 장 운영 시간 체크
            now = datetime.now()
            current_time = now.time()
            
            # 평일 체크
            if now.weekday() >= 5:  # 토(5), 일(6)
                logger.debug("주말 - 거래 없음")
                return
            
            # 장 시간 체크 (9:00 ~ 15:30)
            market_open = current_time >= datetime.strptime("09:00", "%H:%M").time()
            market_close = current_time <= datetime.strptime("15:30", "%H:%M").time()
            
            if not (market_open and market_close):
                logger.debug("장 시간 외 - 거래 없음")
                return
            
            logger.info(f"⏰ 스케줄 실행: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            bot_instance.run_strategy()
            
        except Exception as e:
            logger.error(f"스케줄 작업 오류: {str(e)}")
    
    # 스케줄 설정: 10분마다
    schedule.every(10).minutes.do(job)
    
    logger.info("⏰ 스케줄 시작 - 10분마다 실행")
    
    # 즉시 1회 실행
    job()
    
    # 무한 루프
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("👋 봇 종료")
            
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(f"👋 **{BOT_NAME} 종료**")
            
            break
        except Exception as e:
            logger.error(f"메인 루프 오류: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()        
