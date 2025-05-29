import KIS_Common as Common
import KIS_API_Helper_KR as KisKR
import discord_alert
import json
import time
from datetime import datetime
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
logger = logging.getLogger('SmartMagicSplitLogger')
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
# 이 부분은 해당 모듈이 로거를 받아들일 수 있는 경우에만 활성화
try:
    KisKR.set_logger(logger)
    Common.set_logger(logger)
except:
    logger.warning("API 헬퍼 모듈에 로거를 전달할 수 없습니다.")


# 봇 설정
BOT_NAME = Common.GetNowDist() + "_SmartMagicSplitBot"
SPLIT_BUDGET_RATIO = 0.08  # 전체 계좌의 8%를 스마트 스플릿 투자에 할당
DIV_NUM = 5.0  # 분할 수 설정

#상수 설정
COMMISSION_RATE = 0.00015  # 수수료 0.015%로 수정
TAX_RATE = 0.0023  # 매도 시 거래세 0.23%
SPECIAL_TAX_RATE = 0.0015  # 농어촌특별세 (매도금액의 0.15%)

RSI_PERIOD = 14
ATR_PERIOD = 14

PULLBACK_RATE = 5  # 고점 대비 충분한 조정 확인 (5%로 상향)
RSI_LOWER_BOUND = 30  # RSI 하한선
RSI_UPPER_BOUND = 78  # RSI 상한선

# 기술적 지표 설정
MA_SHORT = 5
MA_MID = 20
MA_LONG = 60

# 관심 종목 설정 (종목별 분석 기간 설정 추가)
TARGET_STOCKS = {
    "449450": {
        "name": "PLUS K방산", 
        "weight": 0.3, 
        "min_holding": 0, 
        "period": 60, 
        "recent_period": 30, 
        "recent_weight": 0.6,
        "stock_type": "growth",
        # "hold_profit_target": 15,  # 기존 15%
        "hold_profit_target": 10,    # 🔥 15% → 10%로 변경
        "base_profit_target": 10,    # 🔥 15% → 10%로 변경  
        "partial_sell_ratio": 0.3
    },
    "042660": {
        "name": "한화오션", 
        "weight": 0.4, 
        "min_holding": 0, 
        "period": 60, 
        "recent_period": 30, 
        "recent_weight": 0.7,
        "stock_type": "growth",
        # "hold_profit_target": 15,  # 기존 15%
        "hold_profit_target": 10,    # 🔥 15% → 10%로 변경
        "base_profit_target": 10     # 🔥 15% → 10%로 변경
    }
}

class SmartMagicSplit:
    def __init__(self):
        self.split_data_list = self.load_split_data()
        self.update_budget()
        self._upgrade_json_structure_if_needed()  # 여기에 추가


    # 여기에 _upgrade_json_structure_if_needed 함수 추가
    def _upgrade_json_structure_if_needed(self):
        """JSON 구조 업그레이드: 부분 매도를 지원하기 위한 필드 추가"""
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
                    
                # EntryDate 필드 추가
                if 'EntryDate' not in magic_data and magic_data['IsBuy']:
                    magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                    is_modified = True
        
        if is_modified:
            logger.info("JSON 구조를 부분 매도 지원을 위해 업그레이드했습니다.")
            self.save_split_data()

        
    def update_budget(self):
        # 계좌 잔고를 가져와서 투자 예산 계산
        balance = KisKR.GetBalance()
        self.total_money = float(balance.get('TotalMoney', 0)) * SPLIT_BUDGET_RATIO
        logger.info(f"총 포트폴리오에 할당된 투자 가능 금액: {self.total_money:,.0f}원")

    def load_split_data(self):
        # 저장된 매매 데이터 로드
        try:
            bot_file_path = f"/var/autobot/kis/KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'r') as json_file:
                return json.load(json_file)
        except Exception:
            return []

    def save_split_data(self):
        # 매매 데이터 저장
        try:
            bot_file_path = f"/var/autobot/kis/KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'w') as outfile:
                json.dump(self.split_data_list, outfile)
        except Exception as e:
            logger.error(f"데이터 저장 중 오류 발생: {str(e)}")

    def calculate_trading_fee(self, price, quantity, is_buy=True):
        """거래 수수료 및 세금 계산"""
        commission = price * quantity * COMMISSION_RATE
        if not is_buy:  # 매도 시에만 세금 부과
            tax = price * quantity * TAX_RATE
            special_tax = price * quantity * SPECIAL_TAX_RATE
        else:
            tax = 0
            special_tax = 0
        
        return commission + tax + special_tax


    def detect_market_timing(self):
        """시장 추세와 타이밍을 감지하는 함수"""
        try:
            # 코스피 지수 데이터 가져오기
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 90)
            if kospi_df is None or len(kospi_df) < 20:
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
            logger.error(f"마켓 타이밍 감지 중 오류: {str(e)}")
            return "neutral"


    def determine_optimal_period(self, stock_code):
        """
        종목의 특성과 시장 환경에 따라 최적의 분석 기간을 결정하는 함수
        
        Args:
            stock_code (str): 종목 코드
            
        Returns:
            tuple: (전체 기간, 최근 기간, 최근 가중치)
        """
        try:
            # 기본값 설정
            default_period = 60
            default_recent = 30
            default_weight = 0.6
            
            # 종목별 특성 확인
            if stock_code in TARGET_STOCKS and "period" in TARGET_STOCKS[stock_code]:
                # 미리 설정된 값이 있으면 사용
                return (
                    TARGET_STOCKS[stock_code].get("period", default_period),
                    TARGET_STOCKS[stock_code].get("recent_period", default_recent),
                    TARGET_STOCKS[stock_code].get("recent_weight", default_weight)
                )
            
            # 없으면 기본 90일 데이터로 종목 특성 분석
            df = Common.GetOhlcv("KR", stock_code, 90)
            if df is None or len(df) < 45:
                return default_period, default_recent, default_weight
                    
            # 시장 환경 판단 (코스피 또는 코스닥 지수 활용)
            # 예: 20일 이동평균선 대비 현재 지수 위치, MACD, RSI 등 기술적 지표 활용
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 60)  # 코스피 지수 데이터
            if kospi_df is not None and len(kospi_df) >= 20:
                # 20일 이동평균선 대비 현재 지수 위치
                current_index = kospi_df['close'].iloc[-1]
                ma20 = kospi_df['close'].rolling(window=20).mean().iloc[-1]
                
                # KOSPI 20일 상승률
                kospi_20d_return = ((current_index - kospi_df['close'].iloc[-20]) / kospi_df['close'].iloc[-20]) * 100
                
                # 시장 환경 판단
                is_bullish_market = current_index > ma20 and kospi_20d_return > 3
                is_bearish_market = current_index < ma20 and kospi_20d_return < -3
                
                # 시장 환경에 따라 급등 판단 기준 조정
                if is_bullish_market:
                    rapid_rise_threshold = 20  # 상승장에서는 20% 이상 상승을 급등으로 판단
                    rapid_rise_period = 20     # 더 짧은 기간 사용
                    logger.info(f"{stock_code} 상승장 환경 감지: 급등 기준 {rapid_rise_threshold}% / {rapid_rise_period}일")
                elif is_bearish_market:
                    rapid_rise_threshold = 40  # 하락장에서는 기준 강화
                    rapid_rise_period = 40     # 더 긴 기간 사용
                    logger.info(f"{stock_code} 하락장 환경 감지: 급등 기준 {rapid_rise_threshold}% / {rapid_rise_period}일")
                else:
                    rapid_rise_threshold = 30  # 일반 시장에서는 30% 기준 유지
                    rapid_rise_period = 30     # 기본 30일 유지
                    logger.info(f"{stock_code} 중립 시장 환경: 급등 기준 {rapid_rise_threshold}% / {rapid_rise_period}일")
            else:
                # 시장 데이터를 가져올 수 없는 경우 기본값 사용
                rapid_rise_threshold = 30
                rapid_rise_period = 30
                
            # 최근 rapid_rise_period일 상승률
            if len(df) > rapid_rise_period:
                recent_return = ((df['close'].iloc[-1] - df['close'].iloc[-rapid_rise_period]) / df['close'].iloc[-rapid_rise_period]) * 100
            else:
                recent_return = 0
                
            # 급등주 판단 (설정된 기간 동안 설정된 % 이상 상승)
            is_rapid_rise = recent_return > rapid_rise_threshold
            
            # 최근 90일 변동성 분석
            volatility_90d = df['close'].pct_change().std() * 100  # 일별 변동성 (%)
            
            # 급등주는 45-60일, 가중치 높게
            if is_rapid_rise:
                logger.info(f"{stock_code} 급등주 특성 발견: 최근 {rapid_rise_period}일 수익률 {recent_return:.2f}% (기준 {rapid_rise_threshold}%)")
                period = min(60, max(45, int(volatility_90d * 2)))  # 변동성에 따라 45-60일 사이
                recent_period = min(30, max(20, int(period / 2)))  # 전체 기간의 절반
                weight = 0.7  # 최근 데이터에 70% 가중치
                
            # 일반 변동성 주식
            else:
                # 변동성에 따라 기간 조정 (변동성이 높을수록 짧은 기간)
                if volatility_90d > 3.0:  # 높은 변동성
                    period = 50
                    weight = 0.65
                elif volatility_90d < 1.5:  # 낮은 변동성
                    period = 75
                    weight = 0.55
                else:  # 중간 변동성
                    period = 60
                    weight = 0.6
                    
                recent_period = int(period / 2)  # 전체 기간의 절반
            
            logger.info(f"{stock_code} 최적 기간 분석 결과: 전체기간={period}일, 최근기간={recent_period}일, 가중치={weight}")
            return period, recent_period, weight
            
        except Exception as e:
            logger.error(f"최적 기간 결정 중 오류: {str(e)}")
            return default_period, default_recent, default_weight

    def calculate_dynamic_profit_target(self, stock_code, indicators):
        """동적으로 목표 수익률을 계산하는 함수 - 복리 효과 극대화 버전"""
        try:
            # 기본 목표 수익률을 낮춤 (회전율 증대를 위해)
            base_target = TARGET_STOCKS[stock_code].get('base_profit_target', 6)  # 10% → 6%로 하향
            
            # 시장 상황에 따른 조정
            market_timing = self.detect_market_timing()
            market_factor = 1.0
            
            if market_timing in ["strong_uptrend", "uptrend"]:
                # 상승장에서는 목표 수익률을 더 낮춰 회전율 극대화
                market_factor = 0.7  # 30% 더 낮춤 (예: 6% → 4.2%)
                logger.info(f"{stock_code} 상승장 감지: 회전율 극대화를 위해 목표 수익률 {market_factor:.1f}배 조정")
            elif market_timing in ["downtrend", "strong_downtrend"]:
                # 하락장에서는 목표 수익률을 높여 리스크 관리
                market_factor = 1.5  # 50% 높임 (예: 6% → 9%)
                logger.info(f"{stock_code} 하락장 감지: 리스크 관리를 위해 목표 수익률 {market_factor:.1f}배 조정")
            
            # 종목 모멘텀에 따른 추가 조정
            momentum_factor = 1.0
            if indicators['market_trend'] in ['strong_up', 'up'] and market_timing in ["strong_uptrend", "uptrend"]:
                momentum_factor = 0.8  # 강한 상승 모멘텀에서는 더 빠른 회전
            elif indicators['market_trend'] in ['strong_down', 'down']:
                momentum_factor = 1.3  # 하락 모멘텀에서는 더 신중하게
            
            # 최종 목표 수익률 계산
            dynamic_target = base_target * market_factor * momentum_factor
            
            # 범위 제한 (3-15% 사이로 제한 - 기존 10-40%에서 대폭 하향)
            dynamic_target = max(3, min(15, dynamic_target))
            
            logger.info(f"{stock_code} 복리 최적화 목표 수익률: {dynamic_target:.1f}% (기본:{base_target}%, 시장:{market_factor:.1f}, 모멘텀:{momentum_factor:.1f})")
            
            return dynamic_target
            
        except Exception as e:
            logger.error(f"동적 목표 수익률 계산 중 오류: {str(e)}")
            return 6  # 오류 시 낮은 기본값 사용

    def get_technical_indicators_weighted(self, stock_code, period=60, recent_period=30, recent_weight=0.7):
        """
        가중치를 적용한 기술적 지표 계산 함수
        
        Args:
            stock_code (str): 종목 코드
            period (int): 전체 분석 기간 (기본값: 60일)
            recent_period (int): 최근 기간 (기본값: 30일)
            recent_weight (float): 최근 기간에 적용할 가중치 (기본값: 0.7)
        
        Returns:
            dict: 계산된 기술적 지표들
        """
        try:
            # 전체 기간 데이터 가져오기 (45-90일)
            df = Common.GetOhlcv("KR", stock_code, period)
            if df is None or len(df) < period // 2:  # 최소 절반 이상의 데이터 필요
                return None
            
            # 기본 이동평균선 계산
            ma_short = Common.GetMA(df, MA_SHORT, -2)
            ma_short_before = Common.GetMA(df, MA_SHORT, -3)
            ma_mid = Common.GetMA(df, MA_MID, -2)
            ma_mid_before = Common.GetMA(df, MA_MID, -3)
            ma_long = Common.GetMA(df, MA_LONG, -2)
            ma_long_before = Common.GetMA(df, MA_LONG, -3)
            
            # 최근 30일 고가 (고점 판단용)
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
            
            # RSI 계산 (과매수/과매도 판단용)
            delta = df['close'].diff()
            gain = delta.copy()
            loss = delta.copy()
            gain[gain < 0] = 0
            loss[loss > 0] = 0
            avg_gain = gain.rolling(window=RSI_PERIOD).mean()
            avg_loss = abs(loss.rolling(window=RSI_PERIOD).mean())
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-2]  # 전일 RSI
            
            # ATR 계산 (변동성 판단용)
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=ATR_PERIOD).mean().iloc[-2]
            
            # 갭 계산
            gap = max_price - min_price
            step_gap = gap / DIV_NUM
            percent_gap = round((gap / min_price) * 100, 2)
            
            # 목표 수익률과 트리거 손실률 계산
            target_rate = round(percent_gap / DIV_NUM, 2)
            trigger_rate = -round((percent_gap / DIV_NUM), 2)
            
            # 조정폭 계산 (고점 대비 얼마나 내려왔는지)
            current_price = KisKR.GetCurrentPrice(stock_code)
            pullback_from_high = (max_high_30 - current_price) / max_high_30 * 100
            
            # 현재 구간 계산
            now_step = DIV_NUM
            for step in range(1, int(DIV_NUM) + 1):
                if prev_close < min_price + (step_gap * step):
                    now_step = step
                    break
            
            # 추세 판단
            is_uptrend = ma_short > ma_mid and ma_mid > ma_long and ma_short > ma_short_before
            is_downtrend = ma_short < ma_mid and ma_mid < ma_long and ma_short < ma_short_before
            
            market_trend = 'strong_up' if is_uptrend else 'strong_down' if is_downtrend else 'sideways'
            if ma_short > ma_mid and ma_short > ma_short_before:
                market_trend = 'up'
            elif ma_short < ma_mid and ma_short < ma_short_before:
                market_trend = 'down'
            
            # 급등주 특성 반영: 최근 상승폭이 매우 큰 경우 추가 조정이 필요할 수 있음
            recent_rise_percent = ((recent_max_price - recent_min_price) / recent_min_price) * 100
            is_rapid_rise = recent_rise_percent > 30  # 최근 30% 이상 상승한 경우
            
            # 결과 반환
            return {
                'current_price': current_price,
                'prev_open': prev_open,
                'prev_close': prev_close,
                'prev_high': prev_high,
                'ma_short': ma_short,
                'ma_short_before': ma_short_before,
                'ma_mid': ma_mid,
                'ma_mid_before': ma_mid_before,
                'ma_long': ma_long,
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
            logger.error(f"가중치 적용 기술적 지표 계산 중 오류: {str(e)}")
            return None

    def get_technical_indicators(self, stock_code):
        # 기존 기술적 지표 계산 함수 (호환성 유지)
        # 자동으로 가중치 적용 함수로 리디렉션
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
            # 성장주 확인
            if TARGET_STOCKS.get(stock_code, {}).get('stock_type') != 'growth':
                return False
                
            # 우상향 확인 (단기>중기>장기)
            ma_alignment = (indicators['ma_short'] > indicators['ma_mid'] and 
                        indicators['ma_mid'] > indicators['ma_long'])
                        
            # 작은 조정 확인 (1-3% 하락)
            small_pullback = (1.0 <= indicators['pullback_from_high'] <= 3.0)
            
            # 과매수 확인
            not_overbought = indicators['rsi'] < 75  # 약간 여유
            
            return ma_alignment and small_pullback and not_overbought
        except Exception as e:
            logger.error(f"작은 조정 매수 기회 확인 중 오류: {str(e)}")
            return False

    def get_split_meta_info(self, stock_code, indicators):
        # 차수별 투자 정보 계산
        try:
            stock_weight = TARGET_STOCKS[stock_code]['weight']
            stock_total_money = self.total_money * stock_weight
            
            # 종목 유형 확인 (성장주 여부)
            stock_type = TARGET_STOCKS[stock_code].get('stock_type', 'normal')
            
            # ===== 변경 시작 =====
            # 성장주 여부에 따라 첫 진입 비중 조정
            if stock_type == 'growth':
                # 성장주는 첫 진입 비중 상향 (더 많은 물량 확보)
                first_invest_ratio = 0.45  # 기본 45%로 상향 (기존 30%에서 증가)
                
                # 시장 상황에 따른 추가 조정
                market_timing = self.detect_market_timing()
                if market_timing == "strong_uptrend":
                    first_invest_ratio = 0.5  # 강한 상승장에서는 50%로 더 상향
                elif market_timing == "downtrend":
                    first_invest_ratio = 0.35  # 하락장에서는 35%로 하향
                    
                logger.info(f"{stock_code} 성장주 특성 반영: 첫 진입 비중 {first_invest_ratio:.2f} (기본값 0.3)")
            else:
                # 기존 급등주 처리 로직
                first_invest_ratio = 0.3  # 기본 30%
                
                # 급등주는 첫 진입 비중을 더 낮게 설정 (리스크 관리)
                if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                    # 상승폭이 클수록 첫 진입 비중 축소
                    rise_adj = max(0.5, 1.0 - (indicators['recent_rise_percent'] / 100))  # 최소 50%까지 감소
                    first_invest_ratio = first_invest_ratio * rise_adj
                    logger.info(f"{stock_code} 급등주 특성 반영: 첫 진입 비중 {first_invest_ratio:.2f} (원래는 0.3)")
            # ===== 변경 끝 =====
                
            first_invest_money = stock_total_money * first_invest_ratio
            remain_invest_money = stock_total_money * (1 - first_invest_ratio)
            
            split_info_list = []
            
            for i in range(int(DIV_NUM)):
                number = i + 1
                
                # 1차수일 경우
                if number == 1:
                    # 기존 로직 유지하되 비중 계산 방식 개선
                    final_invest_rate = 0
                    
                    # MA 골든크로스 상태 확인 (단기>중기>장기)
                    if (indicators['ma_short'] > indicators['ma_mid'] and 
                        indicators['ma_mid'] > indicators['ma_long']):
                        final_invest_rate += 15  # 비중 상향
                    
                    # 각 이동평균선 상태 체크
                    if indicators['prev_close'] >= indicators['ma_short']:
                        final_invest_rate += 5  # 비중 하향 조정
                    if indicators['prev_close'] >= indicators['ma_mid']:
                        final_invest_rate += 5
                    if indicators['prev_close'] >= indicators['ma_long']:
                        final_invest_rate += 5
                    if indicators['ma_short'] >= indicators['ma_short_before']:
                        final_invest_rate += 5
                    if indicators['ma_mid'] >= indicators['ma_mid_before']:
                        final_invest_rate += 5
                    if indicators['ma_long'] >= indicators['ma_long_before']:
                        final_invest_rate += 5
                    
                    # 현재 구간에 따른 투자 비율 결정 (최대 40%)
                    step_invest_rate = ((int(DIV_NUM) + 1) - indicators['now_step']) * (40.0 / DIV_NUM)
                    final_invest_rate += step_invest_rate
                    
                    # RSI 고려 (과매수/과매도 상태에서 비중 조절)
                    if indicators['rsi'] > RSI_UPPER_BOUND:
                        final_invest_rate = final_invest_rate * 0.5  # 과매수 상태에서는 50% 축소
                    elif indicators['rsi'] < RSI_LOWER_BOUND:
                        final_invest_rate = final_invest_rate * 0.7  # 과매도 상태에서는 30% 축소 (더 떨어질 수 있음)
                        
                    # 조정폭 고려 (고점 대비 조정이 충분히 이루어진 경우 비중 확대)
                    if indicators['pullback_from_high'] > 5:  # 5% 이상 조정
                        final_invest_rate = final_invest_rate * 1.2  # 20% 확대
                    
                    # 급등주 특성 반영 (더 충분한 조정이 있을 때만 정상 비중 투자)
                    if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                        if indicators['pullback_from_high'] < 5:  # 충분한 조정이 없으면
                            final_invest_rate = final_invest_rate * 0.7  # 추가로 30% 축소
                    
                    final_first_money = first_invest_money * (final_invest_rate / 100.0)
                    
                    # 안전장치: 최소 0%, 최대 100% 제한
                    final_first_money = max(0, min(final_first_money, first_invest_money))
                    
                    # ===== 변경 시작 =====
                    # 성장주 여부에 따라 목표 수익률 조정
                    if stock_type == 'growth':
                        # 동적 목표 수익률 계산
                        dynamic_target = self.calculate_dynamic_profit_target(stock_code, indicators)
                        target_rate_multiplier = max(1.2, dynamic_target / indicators['target_rate'])    # 🔥 최소 1.2배로 완화
                        logger.info(f"{stock_code} 성장주 특성 반영: 동적 목표 수익률 {dynamic_target:.2f}% (승수: {target_rate_multiplier:.2f})")

                    else:
                        # 급등주 목표 수익률 조정 (기존 로직 유지)
                        target_rate_multiplier = 1.5  # 기본 1.5배
                        
                        if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                            # 급등 정도에 따라 목표 수익률 조정 (최소 1.0배)
                            target_rate_multiplier = max(1.0, 1.5 - (indicators['recent_rise_percent'] / 100))
                            logger.info(f"{stock_code} 급등주 특성 반영: 목표 수익률 승수 {target_rate_multiplier:.2f} (원래는 1.5)")
                    # ===== 변경 끝 =====
                    
                    # 1차 매수는 조정된 목표 수익률 적용
                    split_info_list.append({
                        "number": 1,
                        "target_rate": indicators['target_rate'] * target_rate_multiplier,
                        "trigger_rate": None,
                        "invest_money": round(final_first_money)
                    })
                    
                # 2차수 이상 - 비중 조정 (나머지 차수에 불균등 배분 - 초기 차수 비중 확대)
                else:
                    # ===== 변경 시작 =====
                    # 성장주 여부에 따라 트리거 민감도 조정
                    if stock_type == 'growth':
                        # 성장주는 작은 조정에도 추가 매수 가능하도록 트리거 민감도 상향
                        trigger_multiplier = 0.5  # 0.8에서 0.5로 더 민감하게 조정 (50% 더 작은 하락에도 매수)

                        
                        market_timing = self.detect_market_timing()
                        if market_timing in ["strong_uptrend", "uptrend"]:
                            # 상승장에서는 더 민감하게
                            trigger_multiplier = 0.7
                        elif market_timing in ["downtrend", "strong_downtrend"]:
                            # 하락장에서는 덜 민감하게
                            trigger_multiplier = 0.9
                            
                        logger.info(f"{stock_code} 성장주 특성 반영: 트리거 민감도 {trigger_multiplier:.2f} (기본값 1.0)")
                    else:
                        # 급등주 트리거 처리 (기존 로직 유지)
                        if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                            # 상승폭이 클수록 차수 간격 확대 (최대 1.2배로 제한)
                            trigger_multiplier = min(1.2, 1.0 + (indicators['recent_rise_percent'] / 200))
                            logger.info(f"{stock_code} 급등주 특성 반영: 트리거 승수 {trigger_multiplier:.2f} (조정됨)")
                        else:
                            trigger_multiplier = 1.0
                    # ===== 변경 끝 =====

                    # 차수별 비중 설정 (낮은 차수에 더 많은 비중 할당)
                    weight_multiplier = 1.0
                    if number <= 3:  # 2-3차수
                        weight_multiplier = 1.2
                    elif number >= 6:  # 6-7차수
                        weight_multiplier = 0.8
                    
                    # 나머지 차수의 합계 가중치 계산
                    total_weight = sum([1.2 if i <= 3 else 0.8 if i >= 6 else 1.0 for i in range(2, int(DIV_NUM)+1)])
                    
                    # 개별 차수 투자금액 계산
                    invest_money = remain_invest_money * (weight_multiplier / total_weight)
                    
                    # 차수별 목표 수익률 차등화 (복리 효과 극대화) - 5단계 추가
                    market_timing = self.detect_market_timing()
                    is_bullish = market_timing in ["strong_uptrend", "uptrend"]

                    # 차수별 목표 수익률 계산
                    if is_bullish and stock_type == 'growth':
                        # 상승장 성장주: 낮은 차수일수록 더 빠른 회전
                        if number <= 2:  # 1-2차: 매우 빠른 회전
                            target_multiplier = 0.6  # 40% 축소
                        elif number <= 4:  # 3-4차: 빠른 회전
                            target_multiplier = 0.8  # 20% 축소
                        else:  # 5차 이상: 일반
                            target_multiplier = 1.0
                        logger.info(f"{stock_code} {number}차 상승장 차등 목표: {target_multiplier:.1f}배")
                    else:
                        # 일반 상황: 기존 로직
                        target_multiplier = 1.0 if stock_type == 'growth' else 1.0
                    
                    # 차수별 트리거 손실률 차등 적용
                    if number <= 3:  # 2-3차수는 더 민감한 트리거 (손실률 60%)
                        trigger_value = indicators['trigger_rate'] * trigger_multiplier * 0.6
                        split_info_list.append({
                            "number": number,
                            "target_rate": indicators['target_rate'] * target_multiplier,
                            "trigger_rate": trigger_value,  # 60%로 축소된 트리거 값
                            "invest_money": round(invest_money)
                        })
                    elif number <= 5:  # 4-5차수는 기본 트리거 (100%)
                        split_info_list.append({
                            "number": number,
                            "target_rate": indicators['target_rate'] * target_multiplier,
                            "trigger_rate": indicators['trigger_rate'] * trigger_multiplier,  # 기본 트리거
                            "invest_money": round(invest_money)
                        })
                    else:  # 6-7차수는 더 큰 트리거 (130%)
                        split_info_list.append({
                            "number": number,
                            "target_rate": indicators['target_rate'] * target_multiplier,
                            "trigger_rate": indicators['trigger_rate'] * trigger_multiplier * 1.3,  # 130%로 확대된 트리거
                            "invest_money": round(invest_money)
                        })
            
            return split_info_list
        except Exception as e:
            logger.error(f"차수 정보 생성 중 오류: {str(e)}")
            return []

    def get_split_data_info(self, stock_data_list, number):
        # 특정 차수 데이터 가져오기
        for save_data in stock_data_list:
            if number == save_data['Number']:
                return save_data
        return None

    def check_first_entry_condition(self, indicators):
        """개선된 1차 진입 조건 체크 - 우상향 시장에서 적극 진입"""
        try:
            # 시장 상황 확인
            market_timing = self.detect_market_timing()
            is_bullish_market = market_timing in ["strong_uptrend", "uptrend"]
            
            # 1. 기본 차트 패턴 조건
            if is_bullish_market:
                # 상승장에서는 조건 대폭 완화
                basic_condition = (
                    indicators['prev_close'] >= indicators['prev_open'] * 0.995 or  # 0.5% 이상 하락 아니면 OK
                    indicators['ma_short'] > indicators['ma_short_before'] or        # 5일선 상승 추세면 OK
                    indicators['current_price'] > indicators['ma_short'] * 0.98     # 5일선 2% 근처면 OK
                )
            else:
                # 기존 조건 유지
                basic_condition = (
                    indicators['prev_open'] < indicators['prev_close'] and
                    (indicators['prev_close'] >= indicators['ma_short'] or
                    indicators['ma_short_before'] <= indicators['ma_short'])
                )
            
            # 2. RSI 조건 완화
            if is_bullish_market:
                # 상승장에서는 RSI 75까지 허용 (기존 78)
                rsi_condition = (20 <= indicators['rsi'] <= 75)
            else:
                rsi_condition = (RSI_LOWER_BOUND <= indicators['rsi'] <= RSI_UPPER_BOUND)
            
            # 3. 고점 대비 조정 조건 완화
            pullback_required = PULLBACK_RATE
            if is_bullish_market:
                # 상승장에서는 조정 요구 대폭 완화 (5% → 2%)
                pullback_required = 2.0
                logger.info(f"상승장 감지: 필요 조정폭을 {pullback_required}%로 완화")
            
            pullback_condition = (
                indicators['pullback_from_high'] >= pullback_required
            )
            
            # 4. 이동평균선 정렬 상태 확인 (기존 로직 유지)
            ma_condition = (
                # 골든크로스 상태 확인 (단기>중기) - 완화된 조건
                indicators['ma_short'] > indicators['ma_mid'] or
                # 단기 상승 추세 확인
                indicators['ma_short'] > indicators['ma_short_before']
            )
            
            # 5. 상승장 특별 진입 조건 추가
            bullish_special_condition = False
            if is_bullish_market:
                bullish_special_condition = (
                    indicators['ma_short'] > indicators['ma_mid'] and  # 단기>중기
                    indicators['current_price'] > indicators['ma_short'] * 0.97 and  # 5일선 3% 근처
                    indicators['rsi'] < 80  # 극도 과매수 아니면 OK
                )
            
            # 6. 급등주 특별 조건 (기존 로직 유지)
            special_condition = False
            if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                if indicators['pullback_from_high'] >= pullback_required * 1.5:  # 필요 조정의 1.5배 이상
                    special_condition = True
                    logger.info(f"급등주 특별 조건 적용: 충분한 조정 감지 ({indicators['pullback_from_high']:.2f}%)")
            
            # 로그 기록
            logger.info(f"1차 진입 조건 체크 ({'상승장 모드' if is_bullish_market else '일반 모드'}):")
            logger.info(f"- 차트 패턴 조건: {'통과' if basic_condition else '미달'}")
            logger.info(f"- RSI 조건: {indicators['rsi']:.1f} - {'통과' if rsi_condition else '미달'}")
            logger.info(f"- 고점 대비 조정({pullback_required:.1f}%): {indicators['pullback_from_high']:.2f}% - {'통과' if pullback_condition else '미달'}")
            logger.info(f"- 이동평균선 조건: {'통과' if ma_condition else '미달'}")
            if is_bullish_market:
                logger.info(f"- 상승장 특별 조건: {'통과' if bullish_special_condition else '미달'}")
            
            # 최종 판단
            if is_bullish_market:
                # 상승장에서는 여러 조건 중 하나만 만족해도 진입
                final_condition = (
                    (basic_condition and rsi_condition) or
                    (pullback_condition and rsi_condition) or
                    bullish_special_condition
                )
            else:
                # 기존 로직 유지
                final_condition = (
                    (basic_condition and rsi_condition and (pullback_condition or ma_condition)) or
                    (indicators['rsi'] < RSI_LOWER_BOUND and 
                    indicators['prev_close'] > indicators['prev_open'] * 1.02) or
                    special_condition
                )
            
            logger.info(f"1차 진입 최종 결정: {'진입 가능' if final_condition else '진입 불가'}")
            
            return final_condition
                        
        except Exception as e:
            logger.error(f"1차 진입 조건 체크 중 오류: {str(e)}")
            return False

    def get_current_holdings(self, stock_code):
        # 현재 보유 수량 및 상태 조회
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
            logger.error(f"보유 수량 조회 중 오류: {str(e)}")
            return {'amount': 0, 'avg_price': 0, 'revenue_rate': 0, 'revenue_money': 0}
    
    def handle_buy(self, stock_code, amount, price):
        # 매수 주문 처리
        try:
            order_price = price * 1.01  # 현재가보다 1% 위에 주문
            result = KisKR.MakeBuyLimitOrder(stock_code, amount, order_price)
            return result, None
        except Exception as e:
            return None, str(e)
    
    def handle_sell(self, stock_code, amount, price):
        # 매도 주문 처리
        try:
            order_price = price * 0.99  # 현재가보다 1% 아래에 주문
            result = KisKR.MakeSellLimitOrder(stock_code, amount, order_price)
            return result, None
        except Exception as e:
            return None, str(e)
    
    def update_realized_pnl(self, stock_code, realized_pnl):
        # 실현 손익 업데이트
        for data_info in self.split_data_list:
            if data_info['StockCode'] == stock_code:
                data_info['RealizedPNL'] += realized_pnl
                
                # 월별 실현 손익 추적
                current_month = datetime.now().strftime('%Y-%m')
                
                if 'MonthlyPNL' not in data_info:
                    data_info['MonthlyPNL'] = {}
                
                if current_month not in data_info['MonthlyPNL']:
                    data_info['MonthlyPNL'][current_month] = 0
                
                data_info['MonthlyPNL'][current_month] += realized_pnl
                self.save_split_data()
                break


    def sync_with_actual_holdings(self):
        is_modified = False  # 변경 여부 추적
        
        for stock_data_info in self.split_data_list:
            stock_code = stock_data_info['StockCode']
            holdings = self.get_current_holdings(stock_code)
            
            # 봇 내부 데이터의 총 보유량 계산
            bot_total_amt = 0
            highest_active_number = 0  # 가장 높은 활성 차수 추적
            
            for magic_data in stock_data_info['MagicDataList']:
                if magic_data['IsBuy']:
                    bot_total_amt += magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                    highest_active_number = max(highest_active_number, magic_data['Number'])
            
            # 추가 매수 감지
            if holdings['amount'] > bot_total_amt:
                additional_amt = holdings['amount'] - bot_total_amt
                
                # 가장 높은 활성 차수에 추가
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['Number'] == highest_active_number:
                        # 기존 수량
                        current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                        # 추가 수량 반영
                        magic_data['CurrentAmt'] = current_amt + additional_amt
                        # 변경 플래그 설정
                        is_modified = True
                        
                        # 평균 단가 업데이트 (수동 매수로 인한 평균 단가 변경 반영)
                        # 실제 계좌의 평균 단가 사용
                        if holdings['avg_price'] > 0:
                            magic_data['EntryPrice'] = holdings['avg_price']
                        
                        # 로그 기록
                        logger.info(f"{stock_data_info['StockName']}({stock_code}) 수동 매수 감지: {additional_amt}주를 {highest_active_number}차에 추가, 계좌 평균단가: {holdings['avg_price']}원")
                        break
            
            # 매도 감지 (계좌 보유량이 봇 내부 데이터보다 적은 경우)
            elif holdings['amount'] < bot_total_amt:
                sold_amt = bot_total_amt - holdings['amount']
                logger.info(f"{stock_data_info['StockName']}({stock_code}) 수동 매도 감지: 총 {sold_amt}주가 매도됨")
                
                # 가장 높은 차수부터 역순으로 순회하여 매도 처리
                active_positions = []
                for magic_data in sorted(stock_data_info['MagicDataList'], key=lambda x: x['Number'], reverse=True):
                    if magic_data['IsBuy'] and sold_amt > 0:
                        current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                        
                        if current_amt <= sold_amt:
                            # 해당 차수 전체 매도
                            sold_from_this_position = current_amt
                            magic_data['CurrentAmt'] = 0
                            magic_data['IsBuy'] = False if magic_data['CurrentAmt'] == 0 else True
                            sold_amt -= sold_from_this_position
                        else:
                            # 해당 차수 일부 매도
                            magic_data['CurrentAmt'] = current_amt - sold_amt
                            sold_from_this_position = sold_amt
                            sold_amt = 0
                        
                        # 매도 이력 추가
                        if 'SellHistory' not in magic_data:
                            magic_data['SellHistory'] = []
                        
                        # 수동 매도 이력 기록 (정확한 수익 계산 불가로 0으로 기록)
                        magic_data['SellHistory'].append({
                            "Date": datetime.now().strftime("%Y-%m-%d"),
                            "Amount": sold_from_this_position,
                            "Price": holdings['avg_price'] if holdings['avg_price'] > 0 else magic_data['EntryPrice'],
                            "Profit": 0,  # 수동 매도는 정확한 수익 계산 불가
                            "Manual": True  # 수동 매도 표시
                        })
                        
                        is_modified = True
                        logger.info(f"- {magic_data['Number']}차에서 {sold_from_this_position}주 매도 처리")
                    
                    if magic_data['IsBuy']:
                        current_return = ((holdings['avg_price'] - magic_data['EntryPrice']) / magic_data['EntryPrice']) * 100 if magic_data['EntryPrice'] > 0 else 0
                        active_positions.append(f"{magic_data['Number']}차({round(current_return, 2)}%)")
                
                if active_positions:
                    logger.info(f"- 남은 활성 차수: {', '.join(active_positions)}")
                else:
                    logger.info(f"- 모든 차수 매도 완료")
        
        # 변경사항이 있을 경우에만 저장
        if is_modified:
            logger.info("계좌 동기화로 인한 변경사항 저장")
            self.save_split_data()
            return True
        
        return False


    def process_trading(self):
        # 매매 로직 처리
        # 마켓 오픈 상태 확인
        is_market_open = KisKR.IsMarketOpen()
        
        # LP 유동성 공급자 활동 시간 확인 (오전 9시 6분 이후)
        time_info = time.gmtime()
        is_lp_ok = True
        if time_info.tm_hour == 0 and time_info.tm_min < 6:  # 9시 6분 이전
            is_lp_ok = False
        
        # 장이 열렸고 LP가 활동할 때만 매매 진행
        if not (is_market_open and is_lp_ok):
            # 장이 닫혔을 때는 다음날 매매 가능하도록 설정
            for stock_info in self.split_data_list:
                stock_info['IsReady'] = True
            self.save_split_data()
            return
        
        # 여기에 실제 계좌와 봇 데이터 동기화 함수 추가 (NEW)
        sync_result = self.sync_with_actual_holdings()

        if sync_result:
            logger.info("계좌와 봇 데이터 동기화 완료")
                        
        # 각 종목별 처리
        for stock_code, stock_info in TARGET_STOCKS.items():
            try:
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
                
                # 분할 매매 메타 정보 생성
                split_meta_list = self.get_split_meta_info(stock_code, indicators)
                
                # 종목 데이터 찾기
                stock_data_info = None
                for data_info in self.split_data_list:
                    if data_info['StockCode'] == stock_code:
                        stock_data_info = data_info
                        break
                
                # 종목 데이터가 없으면 새로 생성
                if stock_data_info is None:
                    magic_data_list = []
                    
                    # 각 차수별 데이터 초기화
                    for i in range(len(split_meta_list)):
                        magic_data_list.append({
                            'Number': i + 1,
                            'EntryPrice': 0,
                            'EntryAmt': 0,
                            'CurrentAmt': 0,  # 현재 보유 수량 필드 추가
                            'SellHistory': [],  # 매도 이력 필드 추가
                            'EntryDate': '',  # 진입 날짜 필드 추가
                            'IsBuy': False
                        })
                    
                    stock_data_info = {
                        'StockCode': stock_code,
                        'StockName': stock_info['name'],
                        'IsReady': True,
                        'MagicDataList': magic_data_list,
                        'RealizedPNL': 0,
                        'MonthlyPNL': {}
                    }
                    
                    self.split_data_list.append(stock_data_info)
                    self.save_split_data()
                    
                    msg = f"{stock_code} 스마트스플릿 투자 준비 완료!!!!!"
                    logger.info(msg)
                    discord_alert.SendMessage(msg)
                
                # ==== 새로운 부분: 작은 조정 매수 기회 체크 ====
                is_small_pullback_opportunity = self.check_small_pullback_buy_opportunity(stock_code, indicators)
                if is_small_pullback_opportunity:
                    logger.info(f"{stock_info['name']}({stock_code}) 우상향 성장주 작은 조정 감지: 매수 기회 고려")
                # ================================================
                
                # 1. 1차수 매수 처리
                first_magic_data = None
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['Number'] == 1:
                        first_magic_data = magic_data
                        break
                
                if first_magic_data and not first_magic_data['IsBuy'] and stock_data_info['IsReady']:
                    # 1차 진입 조건 체크 또는 작은 조정 매수 기회 활용
                    if self.check_first_entry_condition(indicators) or is_small_pullback_opportunity:
                        stock_data_info['RealizedPNL'] = 0  # 누적 실현손익 초기화
                        
                        if holdings['amount'] > 0:  # 이미 종목을 보유 중인 경우
                            first_magic_data['IsBuy'] = True
                            first_magic_data['EntryPrice'] = holdings['avg_price']
                            first_magic_data['EntryAmt'] = holdings['amount']
                            first_magic_data['CurrentAmt'] = holdings['amount']  # 현재 보유 수량 설정
                            first_magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")  # 진입 날짜 설정
                            self.save_split_data()
                            
                            entry_reason = "작은 조정 매수 기회" if is_small_pullback_opportunity else "기본 진입 조건 충족"
                            msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 1차 투자를 하려고 했는데 잔고가 있어서 이를 1차투자로 가정하게 세팅했습니다! 진입 이유: {entry_reason}"
                            logger.info(msg)
                            discord_alert.SendMessage(msg)
                        else:  # 새로 매수
                            first_split_meta = None
                            for meta in split_meta_list:
                                if meta['number'] == 1:
                                    first_split_meta = meta
                                    break
                            
                            if first_split_meta:
                                buy_amt = max(1, int(first_split_meta['invest_money'] / indicators['current_price']))
                                
                                result, error = self.handle_buy(stock_code, buy_amt, indicators['current_price'])
                                
                                if result:
                                    first_magic_data['IsBuy'] = True
                                    first_magic_data['EntryPrice'] = indicators['current_price']
                                    first_magic_data['EntryAmt'] = buy_amt
                                    first_magic_data['CurrentAmt'] = buy_amt  # 현재 보유 수량 설정
                                    first_magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")  # 진입 날짜 설정
                                    self.save_split_data()
                                    
                                    entry_reason = "작은 조정 매수 기회" if is_small_pullback_opportunity else "기본 진입 조건 충족"
                                    msg = f"{stock_code} 스마트스플릿 1차 투자 완료! 진입 이유: {entry_reason}"
                                    logger.info(msg)
                                    discord_alert.SendMessage(msg)
                
                # 2. 보유 차수 매도 및 다음 차수 매수 처리
                for magic_data in stock_data_info['MagicDataList']:
                    split_meta = None
                    for meta in split_meta_list:
                        if meta['number'] == magic_data['Number']:
                            split_meta = meta
                            break
                    
                    if not split_meta:
                        continue
                    
                    # 이미 매수된 차수 처리
                    if magic_data['IsBuy']:
                        current_rate = (indicators['current_price'] - magic_data['EntryPrice']) / magic_data['EntryPrice'] * 100.0
                        
                        logger.info(f"{stock_info['name']}({stock_code}) {magic_data['Number']}차 수익률 {round(current_rate, 2)}% 목표수익률 {split_meta['target_rate']}%")
                        
                        # ==== 매도 로직 수정: 부분 매도 지원 ====
                        # 목표 수익률 달성 시 매도 처리
                        if (current_rate >= split_meta['target_rate'] and 
                            holdings['amount'] > 0 and 
                            (holdings['revenue_money'] + stock_data_info['RealizedPNL']) > 0):
                            
                            # 종목 유형 확인 (성장주 여부)
                            is_growth_stock = stock_info.get('stock_type') == 'growth'

                            # 성장주 동적 부분 매도 적용
                            if is_growth_stock:
                                # 현재 차수의 보유 수량 확인 (부분 매도 후 남은 수량)
                                current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                                
                                # 시장 상황에 따른 동적 부분 매도 비율 계산
                                market_timing = self.detect_market_timing()
                                base_sell_ratio = stock_info.get('partial_sell_ratio', 0.3)
                                
                                if market_timing in ["strong_uptrend", "uptrend"]:
                                    # 상승장에서는 매도 비율을 줄여 더 많이 보유 (복리 효과)
                                    partial_sell_ratio = base_sell_ratio * 0.6  # 30% → 18%로 축소
                                    logger.info(f"{stock_code} 상승장 감지: 부분 매도 비율을 {partial_sell_ratio:.1%}로 축소하여 복리 효과 극대화")
                                elif market_timing in ["downtrend", "strong_downtrend"]:
                                    # 하락장에서는 매도 비율을 늘려 리스크 관리
                                    partial_sell_ratio = min(0.5, base_sell_ratio * 1.5)  # 30% → 45%로 확대 (최대 50%)
                                    logger.info(f"{stock_code} 하락장 감지: 부분 매도 비율을 {partial_sell_ratio:.1%}로 확대하여 리스크 관리")
                                else:
                                    partial_sell_ratio = base_sell_ratio
                                
                                # 추가 조건: 수익률이 높을수록 더 적게 매도 (상승장에서만)
                                if market_timing in ["strong_uptrend", "uptrend"] and current_rate > 8:
                                    # 8% 이상 수익에서는 매도 비율을 더욱 축소
                                    high_profit_factor = max(0.5, 1.0 - (current_rate - 8) / 20)  # 수익률이 높을수록 적게 매도
                                    partial_sell_ratio = partial_sell_ratio * high_profit_factor
                                    logger.info(f"{stock_code} 고수익({current_rate:.1f}%) 달성: 매도 비율을 {partial_sell_ratio:.1%}로 추가 축소")

                                sell_amt = max(1, int(current_amt * partial_sell_ratio))
                                
                                # 매도할 수량이 보유 수량보다 크면 조정
                                is_over = False
                                if sell_amt > holdings['amount']:
                                    sell_amt = holdings['amount']
                                    is_over = True
                                
                                # 최소 보유 수량 고려
                                if holdings['amount'] - sell_amt < stock_info['min_holding']:
                                    sell_amt = max(0, holdings['amount'] - stock_info['min_holding'])
                                
                                # 매도 진행
                                if sell_amt > 0:
                                    result, error = self.handle_sell(stock_code, sell_amt, indicators['current_price'])
                                    
                                    if result:
                                        # 현재 보유 수량 업데이트
                                        magic_data['CurrentAmt'] = current_amt - sell_amt
                                        
                                        # 완전 매도 여부 확인
                                        if magic_data['CurrentAmt'] <= 0:
                                            magic_data['IsBuy'] = False
                                        
                                        # 매도 이력 추가
                                        if 'SellHistory' not in magic_data:
                                            magic_data['SellHistory'] = []
                                        
                                        # 실현 손익 계산
                                        realized_pnl = holdings['revenue_money'] * sell_amt / holdings['amount']
                                        
                                        # 매도 이력 기록
                                        magic_data['SellHistory'].append({
                                            "Date": datetime.now().strftime("%Y-%m-%d"),
                                            "Amount": sell_amt,
                                            "Price": indicators['current_price'],
                                            "Profit": realized_pnl
                                        })
                                        
                                        # 매도 완료 후 재진입 준비 시간 동적 조정
                                        market_timing = self.detect_market_timing()

                                        if market_timing in ["strong_uptrend", "uptrend"]:
                                            # 상승장에서는 즉시 재진입 준비 (복리 효과 극대화)
                                            stock_data_info['IsReady'] = True
                                            logger.info(f"{stock_code} 상승장 감지: 매도 후 즉시 재진입 준비 완료")
                                        else:
                                            # 일반/하락장에서는 기존 로직 유지 (하루 대기)
                                            stock_data_info['IsReady'] = False
                                            logger.info(f"{stock_code} 일반장/하락장: 매도 후 하루 대기")

                                        # 누적 실현 손익 업데이트
                                        self.update_realized_pnl(stock_code, realized_pnl)
                                        
                                        # 매도 메시지 작성
                                        msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 {current_amt}주 중 {sell_amt}주 부분 매도 완료! 수익률: {current_rate:.2f}%"
                                        if is_over:
                                            msg += " (매도할 수량이 보유 수량보다 많은 상태라 모두 매도함)"
                                        
                                        logger.info(msg)
                                        discord_alert.SendMessage(msg)
                                        
                                        self.save_split_data()
                            else:
                                # 일반 종목은 기존 매도 로직 유지
                                sell_amt = magic_data['EntryAmt']
                                
                                # 매도할 수량이 보유 수량보다 크면 조정
                                is_over = False
                                if sell_amt > holdings['amount']:
                                    sell_amt = holdings['amount']
                                    is_over = True
                                
                                # 최소 보유 수량 고려
                                if holdings['amount'] - sell_amt < stock_info['min_holding']:
                                    sell_amt = max(0, holdings['amount'] - stock_info['min_holding'])
                                
                                if sell_amt > 0:
                                    result, error = self.handle_sell(stock_code, sell_amt, indicators['current_price'])
                                    
                                    if result:
                                        magic_data['IsBuy'] = False
                                        stock_data_info['IsReady'] = False
                                        
                                        realized_pnl = holdings['revenue_money'] * sell_amt / holdings['amount']
                                        self.update_realized_pnl(stock_code, realized_pnl)
                                        
                                        msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 수익 매도 완료! 차수 목표수익률 {split_meta['target_rate']}% 만족"
                                        if is_over:
                                            msg += " 매도할 수량이 보유 수량보다 많은 상태라 모두 매도함!"
                                        
                                        logger.info(msg)
                                        discord_alert.SendMessage(msg)
                    
                    # 매수되지 않은 차수 처리 (2차 이상)
                    elif magic_data['Number'] > 1:
                        prev_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], magic_data['Number'] - 1)
                        
                        if prev_magic_data and prev_magic_data['IsBuy']:
                            prev_rate = (indicators['current_price'] - prev_magic_data['EntryPrice']) / prev_magic_data['EntryPrice'] * 100.0
                            
                            logger.info(f"{stock_info['name']}({stock_code}) {magic_data['Number']}차 진입을 위한 {magic_data['Number']-1}차 수익률 {round(prev_rate, 2)}% 트리거 수익률 {split_meta['trigger_rate']}%")
                            
                            # 추가 조건 확인
                            additional_condition = True
                            
                            # 홀수 차수 추가 조건
                            if magic_data['Number'] % 2 == 1:
                                if not (indicators['prev_open'] < indicators['prev_close'] and 
                                    (indicators['prev_close'] >= indicators['ma_short'] or 
                                    indicators['ma_short_before'] <= indicators['ma_short'])):
                                    additional_condition = False
                            
                            # 이전 차수 손실률이 트리거 이하이고 추가 조건 만족 시 매수
                            if prev_rate <= split_meta['trigger_rate'] and additional_condition:
                                buy_amt = max(1, int(split_meta['invest_money'] / indicators['current_price']))
                                
                                result, error = self.handle_buy(stock_code, buy_amt, indicators['current_price'])
                                
                                if result:
                                    magic_data['IsBuy'] = True
                                    magic_data['EntryPrice'] = indicators['current_price']
                                    magic_data['EntryAmt'] = buy_amt
                                    magic_data['CurrentAmt'] = buy_amt  # 현재 보유 수량 설정
                                    magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")  # 진입 날짜 설정

                                    # 매도 완료 후 재진입 준비 시간 동적 조정
                                    market_timing = self.detect_market_timing()
                                    if market_timing in ["strong_uptrend", "uptrend"]:
                                        # 상승장에서는 즉시 재진입 준비 (복리 효과 극대화)
                                        stock_data_info['IsReady'] = True
                                        logger.info(f"{stock_code} 상승장 감지: 매도 후 즉시 재진입 준비 완료")
                                    else:
                                        # 일반/하락장에서는 기존 로직 유지 (하루 대기)
                                        stock_data_info['IsReady'] = False
                                        logger.info(f"{stock_code} 일반장/하락장: 매도 후 하루 대기")

                                    self.save_split_data()
                                    
                                    msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 매수 완료! 이전 차수 손실률 {split_meta['trigger_rate']}% 만족"
                                    logger.info(msg)
                                    discord_alert.SendMessage(msg)
                            
                            # ==== 새로운 부분: 성장주 작은 조정 추가 매수 ====
                            elif (is_small_pullback_opportunity and 
                                stock_info.get('stock_type') == 'growth' and 
                                magic_data['Number'] <= 3):  # 2-3차수만 작은 조정 추가 매수 적용
                                
                                # 작은 조정 시 추가 매수 (트리거에 도달하지 않아도)
                                buy_amt = max(1, int(split_meta['invest_money'] * 0.7 / indicators['current_price']))  # 예산의 70%만 사용
                                
                                result, error = self.handle_buy(stock_code, buy_amt, indicators['current_price'])
                                
                                if result:
                                    magic_data['IsBuy'] = True
                                    magic_data['EntryPrice'] = indicators['current_price']
                                    magic_data['EntryAmt'] = buy_amt
                                    magic_data['CurrentAmt'] = buy_amt
                                    magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                    stock_data_info['IsReady'] = False
                                    self.save_split_data()
                                    
                                    msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 매수 완료! 우상향 성장주 작은 조정 매수 기회 포착"
                                    logger.info(msg)
                                    discord_alert.SendMessage(msg)
                            # ================================================
                
                # 3. 풀매수 상태 확인 및 처리
                is_full_buy = all(data['IsBuy'] for data in stock_data_info['MagicDataList'])
                
                if is_full_buy:
                    # 마지막 차수 정보
                    last_split_meta = None
                    for meta in split_meta_list:
                        if meta['number'] == int(DIV_NUM):
                            last_split_meta = meta
                            break
                    
                    last_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], int(DIV_NUM))
                    
                    if last_split_meta and last_magic_data:
                        # 마지막 차수 손익률
                        last_rate = (indicators['current_price'] - last_magic_data['EntryPrice']) / last_magic_data['EntryPrice'] * 100.0
                        
                        # 추가 하락 시 차수 재정리
                        if last_rate <= last_split_meta['trigger_rate']:
                            msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 풀매수 상태인데 더 하락하여 2차수 손절 및 초기화!"
                            logger.info(msg)
                            discord_alert.SendMessage(msg)
                            
                            # 2차수 손절 및 차수 재정리
                            second_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], 2)
                            
                            if second_magic_data:
                                # 현재 보유 수량 확인
                                current_amt = second_magic_data.get('CurrentAmt', second_magic_data['EntryAmt'])
                                sell_amt = min(current_amt, holdings['amount'])
                                
                                if sell_amt > 0:
                                    result, error = self.handle_sell(stock_code, sell_amt, indicators['current_price'])
                                    
                                    if result:
                                        second_magic_data['IsBuy'] = False
                                        second_magic_data['CurrentAmt'] = 0  # 보유 수량 초기화
                                        stock_data_info['IsReady'] = False
                                        
                                        # 매도 이력 추가
                                        if 'SellHistory' not in second_magic_data:
                                            second_magic_data['SellHistory'] = []
                                        
                                        # 실현 손익 계산
                                        realized_pnl = holdings['revenue_money'] * sell_amt / holdings['amount']
                                        
                                        # 매도 이력 기록
                                        second_magic_data['SellHistory'].append({
                                            "Date": datetime.now().strftime("%Y-%m-%d"),
                                            "Amount": sell_amt,
                                            "Price": indicators['current_price'],
                                            "Profit": realized_pnl
                                        })
                                        
                                        # 누적 실현 손익 업데이트
                                        self.update_realized_pnl(stock_code, realized_pnl)
                                        
                                        # 차수 재조정 - 모든 차수를 한 단계씩 앞으로 당기고 마지막 차수 비움
                                        for i in range(int(DIV_NUM)):
                                            number = i + 1
                                            
                                            if number >= 2:  # 2차수부터 처리
                                                data = stock_data_info['MagicDataList'][i]
                                                
                                                if number == int(DIV_NUM):  # 마지막 차수는 비움
                                                    data['IsBuy'] = False
                                                    data['EntryAmt'] = 0
                                                    data['CurrentAmt'] = 0  # 현재 보유 수량도 초기화
                                                    data['EntryPrice'] = 0
                                                else:  # 나머지는 다음 차수 데이터로 덮어씀
                                                    next_data = stock_data_info['MagicDataList'][i + 1]
                                                    data['IsBuy'] = next_data['IsBuy']
                                                    data['EntryAmt'] = next_data['EntryAmt']
                                                    data['CurrentAmt'] = next_data.get('CurrentAmt', next_data['EntryAmt'])
                                                    data['EntryPrice'] = next_data['EntryPrice']
                                                    data['SellHistory'] = next_data.get('SellHistory', [])
                                                    data['EntryDate'] = next_data.get('EntryDate', datetime.now().strftime("%Y-%m-%d"))
                                        
                                        self.save_split_data()
                                        
                                        msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 차수 재정리 완료! {sell_amt}주 매도!"
                                        logger.info(msg)
                                        discord_alert.SendMessage(msg)
            
            except Exception as e:
                logger.error(f"{stock_code} 처리 중 오류 발생: {str(e)}")


    def send_daily_summary(self):
        """장 종료 후 각 종목 및 전체 누적수익률 요약 알림 전송"""
        try:

            # 각 종목별 현재 상태 및 누적 수익 계산
            total_realized_pnl = 0
            summary_message = "📈 오늘의 스마트매직스플릿 수익률 요약 📈\n\n"
            
            # 종목별 요약
            summary_message += "[ 종목별 누적 수익 ]\n"
            
            for data_info in self.split_data_list:
                stock_code = data_info['StockCode']
                stock_name = data_info['StockName']
                realized_pnl = data_info.get('RealizedPNL', 0)
                total_realized_pnl += realized_pnl
                
                # 현재 보유 상태 확인
                holdings = self.get_current_holdings(stock_code)
                current_price = KisKR.GetCurrentPrice(stock_code)
                
                # 미실현 손익 계산
                unrealized_pnl = 0
                if holdings['amount'] > 0:
                    unrealized_pnl = holdings['revenue_money']
                
                # 현재 활성화된 차수 확인
                active_positions = []
                for magic_data in data_info['MagicDataList']:
                    if magic_data['IsBuy']:
                        current_return = (current_price - magic_data['EntryPrice']) / magic_data['EntryPrice'] * 100
                        active_positions.append(f"{magic_data['Number']}차({round(current_return, 2)}%)")
                
                # 월별 수익 정보
                current_month = datetime.now().strftime('%Y-%m')
                monthly_pnl = data_info.get('MonthlyPNL', {}).get(current_month, 0)
                
                # 종목 요약 정보 추가
                summary_message += f"• {stock_name}({stock_code}):\n"
                summary_message += f"  - 누적실현손익: {realized_pnl:,.0f}원\n"
                summary_message += f"  - 이번달실현: {monthly_pnl:,.0f}원\n"
                
                if holdings['amount'] > 0:
                    summary_message += f"  - 현재보유: {holdings['amount']}주 (평균단가: {holdings['avg_price']:,.0f}원)\n"
                    summary_message += f"  - 미실현손익: {unrealized_pnl:,.0f}원 ({holdings['revenue_rate']:.2f}%)\n"
                else:
                    summary_message += f"  - 현재보유: 없음\n"
                    
                if active_positions:
                    summary_message += f"  - 진행차수: {', '.join(active_positions)}\n"
                else:
                    summary_message += f"  - 진행차수: 없음\n"
                
                summary_message += "\n"
            
            # 총 누적 수익 요약
            summary_message += "[ 총 누적 실현 손익 ]\n"
            summary_message += f"💰 {total_realized_pnl:,.0f}원\n\n"
            
            # 현재 투자 예산 정보
            summary_message += f"💼 현재 할당된 총 투자 예산: {self.total_money:,.0f}원"
            
            # Discord로 알림 전송
            discord_alert.SendMessage(summary_message)
            logger.info("일일 요약 알림 전송 완료")
            
        except Exception as e:
            logger.error(f"일일 요약 알림 전송 중 오류: {str(e)}")

def check_trading_time():
    """장중 거래 가능한 시간대인지 체크하고 장 시작 시점도 확인"""
    try:
        # 휴장일 체크
        if KisKR.IsTodayOpenCheck() == 'N':
            logger.info("휴장일 입니다.")
            return False, False

        # 장 상태 확인
        market_status = KisKR.MarketStatus()
        if market_status is None or not isinstance(market_status, dict):
            logger.info("장 상태 확인 실패")
            return False, False
            
        status_code = market_status.get('Status', '')
        
        # 장 시작 시점 체크 (동시호가 '0' 여부로 확인)
        # 장 시작 시점 체크 (동시호가 '0' 여부와 9시 체크)
        current_time = datetime.now().time()
        is_market_open = (status_code == '0' and # 동시호가
                         current_time.hour == 8)
        # is_market_open = (status_code == '0')

        # is_market_open = (status_code == '0')
        
        # 거래 가능 시간 체크 ('2'는 장중)
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
        logger.info(f"장 상태: {status_desc.get(status_code, '알 수 없음')}")
        
        return is_trading_time, is_market_open
        
    except Exception as e:
        logger.error(f"거래 시간 체크 중 에러 발생: {str(e)}")
        return False, False


def run_bot():
    try:
        # 클래스 변수 사용을 위해 SmartMagicSplit 클래스에 정적 변수 추가
        if not hasattr(SmartMagicSplit, '_daily_summary_sent_date'):
            SmartMagicSplit._daily_summary_sent_date = None

        Common.SetChangeMode()

        # 봇 초기화 및 실행
        bot = SmartMagicSplit()
        
        # 첫 실행 시 매매 가능 상태 출력
        for data_info in bot.split_data_list:
            logger.info(f"{data_info['StockName']}({data_info['StockCode']}) 누적 실현 손익: {data_info['RealizedPNL']:,.0f}원")
        
        # 매매 로직 실행
        bot.process_trading()

        # 장 개장일이면서 장 마감 시간이면 일일 보고서 전송
        now = datetime.now()
        if (KisKR.IsTodayOpenCheck() and 
            now.hour == 15 and 
            now.minute >= 20 and 
            now.minute < 40 and  # 15:20~15:30 사이
            SmartMagicSplit._daily_summary_sent_date != now.date()):  # 당일 미전송 확인
            
            # 장 종료 후 일일 요약 알림 전송
            bot.send_daily_summary()
            
            # 전송 날짜 기록
            SmartMagicSplit._daily_summary_sent_date = now.date()
        
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {str(e)}")

def main():

    # 처음에 한 번 실행
    run_bot()
    
    # 30초마다 실행하도록 스케줄 설정
    schedule.every(47).seconds.do(run_bot)
    
    # 스케줄러 실행
    while True:

        # 장 시작 운영 시간 및 시작시간 체크
        is_trading_time, is_market_open = check_trading_time()    

        if not is_trading_time:
            msg = "장 시간 외 입니다. 다음 장 시작까지 대기"
            logger.info(msg)
            time.sleep(300)  # 5분 대기
            continue    

        schedule.run_pending()
        time.sleep(1)  # CPU 사용량을 줄이기 위해 짧은 대기 시간 추가

if __name__ == "__main__":
    main()
