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

# KIS_API_Helper_KR과 KIS_Common 모듈에 로거 전달
try:
    KisKR.set_logger(logger)
    Common.set_logger(logger)
except:
    logger.warning("API 헬퍼 모듈에 로거를 전달할 수 없습니다.")

# 봇 설정
BOT_NAME = Common.GetNowDist() + "_SmartMagicSplitBot"
SPLIT_BUDGET_RATIO = 0.08  # 전체 계좌의 8%를 스마트 스플릿 투자에 할당
DIV_NUM = 5.0  # 분할 수 설정

# 상수 설정
COMMISSION_RATE = 0.00015  # 수수료 0.015%
TAX_RATE = 0.0023  # 매도 시 거래세 0.23%
SPECIAL_TAX_RATE = 0.0015  # 농어촌특별세 0.15%

RSI_PERIOD = 14
ATR_PERIOD = 14

PULLBACK_RATE = 5  # 고점 대비 충분한 조정 확인
RSI_LOWER_BOUND = 30  # RSI 하한선
RSI_UPPER_BOUND = 78  # RSI 상한선

# 기술적 지표 설정
MA_SHORT = 5
MA_MID = 20
MA_LONG = 60

# 관심 종목 설정
TARGET_STOCKS = {
    "449450": {
        "name": "PLUS K방산", 
        "weight": 0.3, 
        "min_holding": 0, 
        "period": 60, 
        "recent_period": 30, 
        "recent_weight": 0.6,
        "stock_type": "growth",
        "hold_profit_target": 10,
        "base_profit_target": 10,    
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
        "hold_profit_target": 10,
        "base_profit_target": 10
    }
}

class SmartMagicSplit:
    def __init__(self):
        self.split_data_list = self.load_split_data()
        self.update_budget()
        self._upgrade_json_structure_if_needed()

    def _upgrade_json_structure_if_needed(self):
        """JSON 구조 업그레이드: 부분 매도를 지원하기 위한 필드 추가"""
        is_modified = False
        
        for stock_data in self.split_data_list:
            for magic_data in stock_data['MagicDataList']:
                if 'CurrentAmt' not in magic_data and magic_data['IsBuy']:
                    magic_data['CurrentAmt'] = magic_data['EntryAmt']
                    is_modified = True
                
                if 'SellHistory' not in magic_data:
                    magic_data['SellHistory'] = []
                    is_modified = True
                    
                if 'EntryDate' not in magic_data and magic_data['IsBuy']:
                    magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                    is_modified = True
        
        if is_modified:
            logger.info("JSON 구조를 부분 매도 지원을 위해 업그레이드했습니다.")
            self.save_split_data()
        
    def update_budget(self):
        balance = KisKR.GetBalance()
        self.total_money = float(balance.get('TotalMoney', 0)) * SPLIT_BUDGET_RATIO
        logger.info(f"총 포트폴리오에 할당된 투자 가능 금액: {self.total_money:,.0f}원")

    def load_split_data(self):
        try:
            bot_file_path = f"/var/autobot/kis/KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'r') as json_file:
                return json.load(json_file)
        except Exception:
            return []

    def save_split_data(self):
        try:
            bot_file_path = f"/var/autobot/kis/KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'w') as outfile:
                json.dump(self.split_data_list, outfile)
        except Exception as e:
            logger.error(f"데이터 저장 중 오류 발생: {str(e)}")

    def calculate_trading_fee(self, price, quantity, is_buy=True):
        """거래 수수료 및 세금 계산"""
        commission = price * quantity * COMMISSION_RATE
        if not is_buy:
            tax = price * quantity * TAX_RATE
            special_tax = price * quantity * SPECIAL_TAX_RATE
        else:
            tax = 0
            special_tax = 0
        
        return commission + tax + special_tax

    def detect_market_timing_enhanced(self):
        """강화된 시장 추세와 타이밍을 감지하는 함수"""
        try:
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 120)
            if kospi_df is None or len(kospi_df) < 60:
                return "neutral", 0
                
            # 다양한 기간의 이동평균선 계산
            kospi_ma5 = kospi_df['close'].rolling(window=5).mean().iloc[-1]
            kospi_ma10 = kospi_df['close'].rolling(window=10).mean().iloc[-1]
            kospi_ma20 = kospi_df['close'].rolling(window=20).mean().iloc[-1]
            kospi_ma60 = kospi_df['close'].rolling(window=60).mean().iloc[-1]
            
            current_index = kospi_df['close'].iloc[-1]
            
            # 최근 수익률 계산
            return_5d = ((current_index - kospi_df['close'].iloc[-6]) / kospi_df['close'].iloc[-6]) * 100
            return_10d = ((current_index - kospi_df['close'].iloc[-11]) / kospi_df['close'].iloc[-11]) * 100
            return_20d = ((current_index - kospi_df['close'].iloc[-21]) / kospi_df['close'].iloc[-21]) * 100
            
            # RSI 계산
            delta = kospi_df['close'].diff()
            gain = delta.copy()
            loss = delta.copy()
            gain[gain < 0] = 0
            loss[loss > 0] = 0
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = abs(loss.rolling(window=14).mean())
            rs = avg_gain / avg_loss
            kospi_rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            # 거래량 분석
            volume_ma20 = kospi_df['volume'].rolling(window=20).mean().iloc[-1]
            current_volume = kospi_df['volume'].iloc[-1]
            volume_ratio = current_volume / volume_ma20
            
            # 추세 강도 점수 계산
            trend_score = 0
            
            # 이동평균선 정렬 점수 (최대 40점)
            if current_index > kospi_ma5: trend_score += 10
            if kospi_ma5 > kospi_ma10: trend_score += 10
            if kospi_ma10 > kospi_ma20: trend_score += 10
            if kospi_ma20 > kospi_ma60: trend_score += 10
            
            # 수익률 점수 (최대 30점)
            if return_5d > 2: trend_score += 10
            elif return_5d > 1: trend_score += 5
            if return_10d > 3: trend_score += 10
            elif return_10d > 1.5: trend_score += 5
            if return_20d > 5: trend_score += 10
            elif return_20d > 2.5: trend_score += 5
            
            # RSI 점수 (최대 15점)
            if kospi_rsi < 30:
                trend_score += 15
            elif kospi_rsi < 50:
                trend_score += 10
            elif kospi_rsi < 70:
                trend_score += 5
            else:
                trend_score -= 5
            
            # 거래량 점수 (최대 15점)
            if volume_ratio > 1.5: trend_score += 15
            elif volume_ratio > 1.2: trend_score += 10
            elif volume_ratio > 1.0: trend_score += 5
            
            # 추세 상태 결정
            if trend_score >= 80:
                trend_state = "very_strong_uptrend"
            elif trend_score >= 65:
                trend_state = "strong_uptrend"
            elif trend_score >= 50:
                trend_state = "uptrend"
            elif trend_score >= 35:
                trend_state = "neutral"
            elif trend_score >= 20:
                trend_state = "downtrend"
            else:
                trend_state = "strong_downtrend"
            
            logger.info(f"시장 추세 분석 - 상태: {trend_state}, 점수: {trend_score}, RSI: {kospi_rsi:.1f}, 거래량비율: {volume_ratio:.2f}")
            
            return trend_state, trend_score
            
        except Exception as e:
            logger.error(f"강화된 마켓 타이밍 감지 중 오류: {str(e)}")
            return "neutral", 0

    def get_dynamic_trading_params(self, stock_code, market_trend, trend_score):
            """시장 상황에 따른 동적 매매 파라미터 조정"""
            try:
                base_config = {
                    'pullback_required': 5.0,
                    'target_multiplier': 1.0,
                    'partial_sell_ratio': 0.3,
                    'trigger_sensitivity': 1.0,
                    'entry_aggressiveness': 1.0
                }
                
                if market_trend == "very_strong_uptrend":
                    config = {
                        'pullback_required': 1.5,
                        'target_multiplier': 0.7,
                        'partial_sell_ratio': 0.6,
                        'trigger_sensitivity': 0.5,
                        'entry_aggressiveness': 1.5
                    }
                    logger.info(f"{stock_code} 매우 강한 상승장 모드: 적극적 회전 매매")
                    
                elif market_trend == "strong_uptrend":
                    config = {
                        'pullback_required': 2.5,
                        'target_multiplier': 0.8,
                        'partial_sell_ratio': 0.5,
                        'trigger_sensitivity': 0.6,
                        'entry_aggressiveness': 1.3
                    }
                    logger.info(f"{stock_code} 강한 상승장 모드: 빠른 회전 매매")
                    
                elif market_trend == "uptrend":
                    config = {
                        'pullback_required': 3.5,
                        'target_multiplier': 0.9,
                        'partial_sell_ratio': 0.4,
                        'trigger_sensitivity': 0.8,
                        'entry_aggressiveness': 1.1
                    }
                    logger.info(f"{stock_code} 상승장 모드: 균형 매매")
                    
                elif market_trend == "neutral":
                    config = base_config.copy()
                    logger.info(f"{stock_code} 중립 모드: 기본 매매")
                    
                elif market_trend == "downtrend":
                    config = {
                        'pullback_required': 7.0,
                        'target_multiplier': 1.2,
                        'partial_sell_ratio': 0.2,
                        'trigger_sensitivity': 1.3,
                        'entry_aggressiveness': 0.8
                    }
                    logger.info(f"{stock_code} 하락장 모드: 보수적 매매")
                    
                else:  # strong_downtrend
                    config = {
                        'pullback_required': 10.0,
                        'target_multiplier': 1.5,
                        'partial_sell_ratio': 0.1,
                        'trigger_sensitivity': 1.5,
                        'entry_aggressiveness': 0.6
                    }
                    logger.info(f"{stock_code} 강한 하락장 모드: 매우 보수적 매매")
                
                # 추세 강도에 따른 미세 조정
                strength_factor = min(1.2, max(0.8, trend_score / 50.0))
                config['entry_aggressiveness'] *= strength_factor
                
                # 성장주 특성 추가 반영
                if TARGET_STOCKS[stock_code].get('stock_type') == 'growth':
                    config['target_multiplier'] *= 0.9
                    config['trigger_sensitivity'] *= 0.8
                    logger.info(f"{stock_code} 성장주 특성 추가 반영")
                
                return config
                
            except Exception as e:
                logger.error(f"동적 매매 파라미터 조정 중 오류: {str(e)}")
                return base_config

    def check_enhanced_first_entry_condition(self, stock_code, indicators, trading_params):
        """개선된 1차 진입 조건 체크"""
        try:
            pullback_required = trading_params['pullback_required']
            entry_aggressiveness = trading_params['entry_aggressiveness']
            
            # 1. 기본 차트 패턴 조건 (완화)
            basic_condition = (
                indicators['prev_open'] < indicators['prev_close'] or
                indicators['ma_short'] > indicators['ma_short_before']
            )
            
            # 2. RSI 조건 (시장 상황에 따라 완화)
            market_trend, _ = self.detect_market_timing_enhanced()
            
            if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                rsi_condition = indicators['rsi'] <= 85
            elif market_trend == "uptrend":
                rsi_condition = indicators['rsi'] <= RSI_UPPER_BOUND
            else:
                rsi_condition = (RSI_LOWER_BOUND <= indicators['rsi'] <= RSI_UPPER_BOUND)
            
            # 3. 동적 조정폭 조건
            pullback_condition = (indicators['pullback_from_high'] >= pullback_required)
            
            # 4. 강화된 이동평균선 조건
            ma_condition = (
                indicators['ma_short'] > indicators['ma_mid'] or
                indicators['ma_short'] > indicators['ma_short_before'] or
                (market_trend in ["very_strong_uptrend", "strong_uptrend"] and 
                 indicators['prev_close'] >= indicators['ma_short'])
            )
            
            # 5. 시장 모멘텀 조건
            momentum_condition = True
            if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                momentum_condition = True
            elif market_trend == "downtrend":
                momentum_condition = (indicators['rsi'] < 35 and 
                                    indicators['prev_close'] > indicators['prev_open'])
            
            # 6. 진입 적극성 반영
            if entry_aggressiveness > 1.2:
                aggressive_condition = (
                    basic_condition or 
                    pullback_condition or 
                    (indicators['rsi'] < 50 and ma_condition)
                )
            else:
                aggressive_condition = False
            
            # 로그 기록
            logger.info(f"개선된 1차 진입 조건 체크 ({market_trend}):")
            logger.info(f"- 차트 패턴: {'통과' if basic_condition else '미달'}")
            logger.info(f"- RSI 조건: {indicators['rsi']:.1f} - {'통과' if rsi_condition else '미달'}")
            logger.info(f"- 조정 조건({pullback_required:.1f}%): {indicators['pullback_from_high']:.2f}% - {'통과' if pullback_condition else '미달'}")
            logger.info(f"- MA 조건: {'통과' if ma_condition else '미달'}")
            logger.info(f"- 모멘텀 조건: {'통과' if momentum_condition else '미달'}")
            logger.info(f"- 적극성({entry_aggressiveness:.1f}): {'통과' if aggressive_condition else '미달'}")
            
            # 최종 판단
            final_condition = (
                (basic_condition and rsi_condition and pullback_condition and ma_condition and momentum_condition) or
                aggressive_condition or
                (indicators['rsi'] < 25 and indicators['prev_close'] > indicators['prev_open'] * 1.03) or
                (TARGET_STOCKS[stock_code].get('stock_type') == 'growth' and 
                 market_trend in ["very_strong_uptrend", "strong_uptrend"] and
                 1.0 <= indicators['pullback_from_high'] <= 3.0 and
                 indicators['ma_short'] > indicators['ma_mid'])
            )
            
            logger.info(f"1차 진입 최종 결정: {'진입 가능' if final_condition else '진입 불가'}")
            return final_condition
                    
        except Exception as e:
            logger.error(f"개선된 1차 진입 조건 체크 중 오류: {str(e)}")
            return False

    def check_enhanced_sell_condition(self, stock_code, magic_data, current_rate, split_meta, 
                                        trading_params, market_trend, holdings, stock_data_info):
            """개선된 매도 조건 체크"""
            try:
                target_rate = split_meta['target_rate']
                
                # 기본 목표 수익률 달성 체크
                basic_target_reached = (current_rate >= target_rate and 
                                    holdings['amount'] > 0 and 
                                    (holdings['revenue_money'] + stock_data_info['RealizedPNL']) > 0)
                
                if not basic_target_reached:
                    return False
                
                # 시장 상황별 추가 매도 조건
                if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                    logger.info(f"{stock_code} {magic_data['Number']}차 상승장 빠른 매도 조건 충족")
                    return True
                    
                elif market_trend == "uptrend":
                    return True
                    
                elif market_trend == "neutral":
                    enhanced_target = target_rate * 1.1
                    if current_rate >= enhanced_target:
                        logger.info(f"{stock_code} {magic_data['Number']}차 중립장 강화된 목표 달성")
                        return True
                        
                else:  # downtrend, strong_downtrend
                    enhanced_target = target_rate * 1.2
                    if current_rate >= enhanced_target:
                        logger.info(f"{stock_code} {magic_data['Number']}차 하락장 확실한 수익 실현")
                        return True
                
                return False
                
            except Exception as e:
                logger.error(f"개선된 매도 조건 체크 중 오류: {str(e)}")
                return False

    def check_enhanced_next_buy_condition(self, stock_code, magic_data, prev_rate, split_meta, 
                                        trading_params, market_trend, indicators):
        """개선된 추가 매수 조건 체크"""
        try:
            trigger_rate = split_meta['trigger_rate']
            
            # 기본 트리거 조건
            basic_trigger = prev_rate <= trigger_rate
            
            # 기존 추가 조건 (홀수 차수)
            additional_condition = True
            if magic_data['Number'] % 2 == 1:
                if market_trend not in ["very_strong_uptrend", "strong_uptrend"]:
                    additional_condition = (
                        indicators['prev_open'] < indicators['prev_close'] and 
                        (indicators['prev_close'] >= indicators['ma_short'] or 
                         indicators['ma_short_before'] <= indicators['ma_short'])
                    )
            
            # 시장 상황별 추가 매수 조건
            market_enhanced_condition = False
            
            if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                small_pullback = (-3.0 <= prev_rate <= -1.0)
                market_enhanced_condition = small_pullback
                
            elif market_trend == "uptrend":
                medium_pullback = (-5.0 <= prev_rate <= -2.0)
                market_enhanced_condition = medium_pullback
            
            # 성장주 특별 조건
            growth_condition = False
            if (TARGET_STOCKS[stock_code].get('stock_type') == 'growth' and 
                magic_data['Number'] <= 3 and 
                market_trend in ["very_strong_uptrend", "strong_uptrend"]):
                tiny_pullback = (-2.0 <= prev_rate <= -0.5)
                growth_condition = tiny_pullback
            
            # 최종 판단
            final_condition = (
                (basic_trigger and additional_condition) or
                market_enhanced_condition or
                growth_condition
            )
            
            if final_condition:
                condition_type = "기본" if basic_trigger else "시장상황" if market_enhanced_condition else "성장주특별"
                logger.info(f"{stock_code} {magic_data['Number']}차 추가 매수 조건 충족 ({condition_type})")
            
            return final_condition
            
        except Exception as e:
            logger.error(f"개선된 추가 매수 조건 체크 중 오류: {str(e)}")
            return False

    def get_enhanced_split_meta_info(self, stock_code, indicators, trading_params):
        """개선된 차수별 투자 정보 계산"""
        try:
            stock_weight = TARGET_STOCKS[stock_code]['weight']
            stock_total_money = self.total_money * stock_weight
            stock_type = TARGET_STOCKS[stock_code].get('stock_type', 'normal')
            
            # 동적 파라미터 적용
            target_multiplier = trading_params['target_multiplier']
            trigger_sensitivity = trading_params['trigger_sensitivity']
            entry_aggressiveness = trading_params['entry_aggressiveness']
            
            # 시장 상황에 따른 첫 진입 비중 조정
            if stock_type == 'growth':
                first_invest_ratio = 0.45 * entry_aggressiveness
            else:
                first_invest_ratio = 0.3 * entry_aggressiveness
            
            # 안전장치: 최소 20%, 최대 60%
            first_invest_ratio = max(0.2, min(0.6, first_invest_ratio))
            
            first_invest_money = stock_total_money * first_invest_ratio
            remain_invest_money = stock_total_money * (1 - first_invest_ratio)
            
            split_info_list = []
            
            for i in range(int(DIV_NUM)):
                number = i + 1
                
                if number == 1:
                    # 1차수 진입 비율 계산
                    final_invest_rate = 0
                    
                    if (indicators['ma_short'] > indicators['ma_mid'] and 
                        indicators['ma_mid'] > indicators['ma_long']):
                        final_invest_rate += 20 * entry_aggressiveness
                    
                    # 이동평균선 상태별 점수
                    if indicators['prev_close'] >= indicators['ma_short']:
                        final_invest_rate += 8
                    if indicators['prev_close'] >= indicators['ma_mid']:
                        final_invest_rate += 8
                    if indicators['prev_close'] >= indicators['ma_long']:
                        final_invest_rate += 8
                    if indicators['ma_short'] >= indicators['ma_short_before']:
                        final_invest_rate += 8
                    if indicators['ma_mid'] >= indicators['ma_mid_before']:
                        final_invest_rate += 8
                    if indicators['ma_long'] >= indicators['ma_long_before']:
                        final_invest_rate += 8
                    
                    # 현재 구간에 따른 투자 비율
                    step_invest_rate = ((int(DIV_NUM) + 1) - indicators['now_step']) * (50.0 / DIV_NUM)
                    final_invest_rate += step_invest_rate
                    
                    # RSI 조건 완화
                    market_trend, _ = self.detect_market_timing_enhanced()
                    if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                        if indicators['rsi'] > 80:
                            final_invest_rate *= 0.8
                        elif indicators['rsi'] > 70:
                            final_invest_rate *= 0.9
                    else:
                        if indicators['rsi'] > RSI_UPPER_BOUND:
                            final_invest_rate *= 0.5
                        elif indicators['rsi'] < RSI_LOWER_BOUND:
                            final_invest_rate *= 0.7
                    
                    # 조정폭 고려
                    pullback_bonus = max(1.0, indicators['pullback_from_high'] / trading_params['pullback_required'])
                    final_invest_rate *= pullback_bonus
                    
                    final_first_money = first_invest_money * (final_invest_rate / 100.0)
                    final_first_money = max(0, min(final_first_money, first_invest_money))
                    
                    # 동적 목표 수익률 계산
                    dynamic_target = indicators['target_rate'] * target_multiplier
                    
                    # 성장주 추가 조정
                    if stock_type == 'growth':
                        if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                            dynamic_target *= 0.8
                    
                    split_info_list.append({
                        "number": 1,
                        "target_rate": dynamic_target,
                        "trigger_rate": None,
                        "invest_money": round(final_first_money)
                    })
                    
                else:
                    # 2차수 이상 - 동적 트리거 적용
                    trigger_multiplier = trigger_sensitivity
                    
                    # 성장주 특별 처리
                    if stock_type == 'growth':
                        trigger_multiplier *= 0.7
                        
                        if market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                            trigger_multiplier *= 0.8
                    
                    # 차수별 비중
                    weight_multiplier = 1.2 if number <= 3 else 0.8 if number >= 6 else 1.0
                    total_weight = sum([1.2 if i <= 3 else 0.8 if i >= 6 else 1.0 
                                      for i in range(2, int(DIV_NUM)+1)])
                    invest_money = remain_invest_money * (weight_multiplier / total_weight)
                    
                    # 차수별 차등 트리거 적용
                    if number <= 3:
                        trigger_value = indicators['trigger_rate'] * trigger_multiplier * 0.6
                    elif number <= 5:
                        trigger_value = indicators['trigger_rate'] * trigger_multiplier
                    else:
                        trigger_value = indicators['trigger_rate'] * trigger_multiplier * 1.3
                    
                    # 동적 목표 수익률
                    target_rate = indicators['target_rate']
                    if stock_type == 'growth' and market_trend in ["very_strong_uptrend", "strong_uptrend"]:
                        target_rate *= 0.9
                    
                    split_info_list.append({
                        "number": number,
                        "target_rate": target_rate,
                        "trigger_rate": trigger_value,
                        "invest_money": round(invest_money)
                    })
            
            return split_info_list
            
        except Exception as e:
            logger.error(f"개선된 차수 정보 생성 중 오류: {str(e)}")
            return []

# 기존 함수들 (변경 없음)
    def determine_optimal_period(self, stock_code):
        """종목의 특성과 시장 환경에 따라 최적의 분석 기간을 결정하는 함수"""
        try:
            default_period = 60
            default_recent = 30
            default_weight = 0.6
            
            if stock_code in TARGET_STOCKS and "period" in TARGET_STOCKS[stock_code]:
                return (
                    TARGET_STOCKS[stock_code].get("period", default_period),
                    TARGET_STOCKS[stock_code].get("recent_period", default_recent),
                    TARGET_STOCKS[stock_code].get("recent_weight", default_weight)
                )
            
            df = Common.GetOhlcv("KR", stock_code, 90)
            if df is None or len(df) < 45:
                return default_period, default_recent, default_weight
                    
            kospi_df = Common.GetOhlcv("KR", "KOSPI", 60)
            if kospi_df is not None and len(kospi_df) >= 20:
                current_index = kospi_df['close'].iloc[-1]
                ma20 = kospi_df['close'].rolling(window=20).mean().iloc[-1]
                kospi_20d_return = ((current_index - kospi_df['close'].iloc[-20]) / kospi_df['close'].iloc[-20]) * 100
                
                is_bullish_market = current_index > ma20 and kospi_20d_return > 3
                is_bearish_market = current_index < ma20 and kospi_20d_return < -3
                
                if is_bullish_market:
                    rapid_rise_threshold = 20
                    rapid_rise_period = 20
                elif is_bearish_market:
                    rapid_rise_threshold = 40
                    rapid_rise_period = 40
                else:
                    rapid_rise_threshold = 30
                    rapid_rise_period = 30
            else:
                rapid_rise_threshold = 30
                rapid_rise_period = 30
                
            if len(df) > rapid_rise_period:
                recent_return = ((df['close'].iloc[-1] - df['close'].iloc[-rapid_rise_period]) / df['close'].iloc[-rapid_rise_period]) * 100
            else:
                recent_return = 0
                
            is_rapid_rise = recent_return > rapid_rise_threshold
            volatility_90d = df['close'].pct_change().std() * 100
            
            if is_rapid_rise:
                logger.info(f"{stock_code} 급등주 특성 발견: 최근 {rapid_rise_period}일 수익률 {recent_return:.2f}%")
                period = min(60, max(45, int(volatility_90d * 2)))
                recent_period = min(30, max(20, int(period / 2)))
                weight = 0.7
            else:
                if volatility_90d > 3.0:
                    period = 50
                    weight = 0.65
                elif volatility_90d < 1.5:
                    period = 75
                    weight = 0.55
                else:
                    period = 60
                    weight = 0.6
                    
                recent_period = int(period / 2)
            
            logger.info(f"{stock_code} 최적 기간 분석 결과: 전체기간={period}일, 최근기간={recent_period}일, 가중치={weight}")
            return period, recent_period, weight
            
        except Exception as e:
            logger.error(f"최적 기간 결정 중 오류: {str(e)}")
            return default_period, default_recent, default_weight

    def get_technical_indicators_weighted(self, stock_code, period=60, recent_period=30, recent_weight=0.7):
        """가중치를 적용한 기술적 지표 계산 함수"""
        try:
            df = Common.GetOhlcv("KR", stock_code, period)
            if df is None or len(df) < period // 2:
                return None
            
            ma_short = Common.GetMA(df, MA_SHORT, -2)
            ma_short_before = Common.GetMA(df, MA_SHORT, -3)
            ma_mid = Common.GetMA(df, MA_MID, -2)
            ma_mid_before = Common.GetMA(df, MA_MID, -3)
            ma_long = Common.GetMA(df, MA_LONG, -2)
            ma_long_before = Common.GetMA(df, MA_LONG, -3)
            
            max_high_30 = df['high'].iloc[-recent_period:].max()
            prev_open = df['open'].iloc[-2]
            prev_close = df['close'].iloc[-2]
            prev_high = df['high'].iloc[-2]
            
            full_min_price = df['close'].min()
            full_max_price = df['close'].max()
            recent_min_price = df['close'].iloc[-recent_period:].min()
            recent_max_price = df['close'].iloc[-recent_period:].max()
            
            min_price = (recent_weight * recent_min_price) + ((1 - recent_weight) * full_min_price)
            max_price = (recent_weight * recent_max_price) + ((1 - recent_weight) * full_max_price)
            
            # RSI 계산
            delta = df['close'].diff()
            gain = delta.copy()
            loss = delta.copy()
            gain[gain < 0] = 0
            loss[loss > 0] = 0
            avg_gain = gain.rolling(window=RSI_PERIOD).mean()
            avg_loss = abs(loss.rolling(window=RSI_PERIOD).mean())
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-2]
            
            # ATR 계산
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=ATR_PERIOD).mean().iloc[-2]
            
            gap = max_price - min_price
            step_gap = gap / DIV_NUM
            percent_gap = round((gap / min_price) * 100, 2)
            target_rate = round(percent_gap / DIV_NUM, 2)
            trigger_rate = -round((percent_gap / DIV_NUM), 2)
            
            current_price = KisKR.GetCurrentPrice(stock_code)
            pullback_from_high = (max_high_30 - current_price) / max_high_30 * 100
            
            now_step = DIV_NUM
            for step in range(1, int(DIV_NUM) + 1):
                if prev_close < min_price + (step_gap * step):
                    now_step = step
                    break
            
            is_uptrend = ma_short > ma_mid and ma_mid > ma_long and ma_short > ma_short_before
            is_downtrend = ma_short < ma_mid and ma_mid < ma_long and ma_short < ma_short_before
            
            market_trend = 'strong_up' if is_uptrend else 'strong_down' if is_downtrend else 'sideways'
            if ma_short > ma_mid and ma_short > ma_short_before:
                market_trend = 'up'
            elif ma_short < ma_mid and ma_short < ma_short_before:
                market_trend = 'down'
            
            recent_rise_percent = ((recent_max_price - recent_min_price) / recent_min_price) * 100
            is_rapid_rise = recent_rise_percent > 30
            
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
        period, recent_period, recent_weight = self.determine_optimal_period(stock_code)
        return self.get_technical_indicators_weighted(
            stock_code, 
            period=period, 
            recent_period=recent_period, 
            recent_weight=recent_weight
        )

    def get_split_data_info(self, stock_data_list, number):
            """특정 차수 데이터 가져오기"""
            for save_data in stock_data_list:
                if number == save_data['Number']:
                    return save_data
            return None

    def get_current_holdings(self, stock_code):
        """현재 보유 수량 및 상태 조회"""
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
        """매수 주문 처리"""
        try:
            order_price = price * 1.01
            result = KisKR.MakeBuyLimitOrder(stock_code, amount, order_price)
            return result, None
        except Exception as e:
            return None, str(e)
    
    def handle_sell(self, stock_code, amount, price):
        """매도 주문 처리"""
        try:
            order_price = price * 0.99
            result = KisKR.MakeSellLimitOrder(stock_code, amount, order_price)
            return result, None
        except Exception as e:
            return None, str(e)
    
    def update_realized_pnl(self, stock_code, realized_pnl):
        """실현 손익 업데이트"""
        for data_info in self.split_data_list:
            if data_info['StockCode'] == stock_code:
                data_info['RealizedPNL'] += realized_pnl
                
                current_month = datetime.now().strftime('%Y-%m')
                
                if 'MonthlyPNL' not in data_info:
                    data_info['MonthlyPNL'] = {}
                
                if current_month not in data_info['MonthlyPNL']:
                    data_info['MonthlyPNL'][current_month] = 0
                
                data_info['MonthlyPNL'][current_month] += realized_pnl
                self.save_split_data()
                break

    def sync_with_actual_holdings(self):
        """실제 계좌와 봇 데이터 동기화"""
        is_modified = False
        
        for stock_data_info in self.split_data_list:
            stock_code = stock_data_info['StockCode']
            holdings = self.get_current_holdings(stock_code)
            
            bot_total_amt = 0
            highest_active_number = 0
            
            for magic_data in stock_data_info['MagicDataList']:
                if magic_data['IsBuy']:
                    bot_total_amt += magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                    highest_active_number = max(highest_active_number, magic_data['Number'])
            
            # 추가 매수 감지
            if holdings['amount'] > bot_total_amt:
                additional_amt = holdings['amount'] - bot_total_amt
                
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['Number'] == highest_active_number:
                        current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                        magic_data['CurrentAmt'] = current_amt + additional_amt
                        is_modified = True
                        
                        if holdings['avg_price'] > 0:
                            magic_data['EntryPrice'] = holdings['avg_price']
                        
                        logger.info(f"{stock_data_info['StockName']}({stock_code}) 수동 매수 감지: {additional_amt}주를 {highest_active_number}차에 추가")
                        break
            
            # 매도 감지
            elif holdings['amount'] < bot_total_amt:
                sold_amt = bot_total_amt - holdings['amount']
                logger.info(f"{stock_data_info['StockName']}({stock_code}) 수동 매도 감지: 총 {sold_amt}주가 매도됨")
                
                for magic_data in sorted(stock_data_info['MagicDataList'], key=lambda x: x['Number'], reverse=True):
                    if magic_data['IsBuy'] and sold_amt > 0:
                        current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                        
                        if current_amt <= sold_amt:
                            sold_from_this_position = current_amt
                            magic_data['CurrentAmt'] = 0
                            magic_data['IsBuy'] = False if magic_data['CurrentAmt'] == 0 else True
                            sold_amt -= sold_from_this_position
                        else:
                            magic_data['CurrentAmt'] = current_amt - sold_amt
                            sold_from_this_position = sold_amt
                            sold_amt = 0
                        
                        if 'SellHistory' not in magic_data:
                            magic_data['SellHistory'] = []
                        
                        magic_data['SellHistory'].append({
                            "Date": datetime.now().strftime("%Y-%m-%d"),
                            "Amount": sold_from_this_position,
                            "Price": holdings['avg_price'] if holdings['avg_price'] > 0 else magic_data['EntryPrice'],
                            "Profit": 0,
                            "Manual": True
                        })
                        
                        is_modified = True
                        logger.info(f"- {magic_data['Number']}차에서 {sold_from_this_position}주 매도 처리")
        
        if is_modified:
            logger.info("계좌 동기화로 인한 변경사항 저장")
            self.save_split_data()
            return True
        
        return False

    def process_trading(self):
            """개선된 매매 로직 처리"""
            # 마켓 오픈 상태 확인
            is_market_open = KisKR.IsMarketOpen()
            
            # LP 유동성 공급자 활동 시간 확인
            time_info = time.gmtime()
            is_lp_ok = True
            if time_info.tm_hour == 0 and time_info.tm_min < 6:
                is_lp_ok = False
            
            # 장이 열렸고 LP가 활동할 때만 매매 진행
            if not (is_market_open and is_lp_ok):
                for stock_info in self.split_data_list:
                    stock_info['IsReady'] = True
                self.save_split_data()
                return
            
            # 실제 계좌와 봇 데이터 동기화
            sync_result = self.sync_with_actual_holdings()
            if sync_result:
                logger.info("계좌와 봇 데이터 동기화 완료")
                            
            # 각 종목별 처리
            for stock_code, stock_info in TARGET_STOCKS.items():
                try:
                    # === 개선된 부분: 시장 상황 분석 및 동적 파라미터 ===
                    market_trend, trend_score = self.detect_market_timing_enhanced()
                    trading_params = self.get_dynamic_trading_params(stock_code, market_trend, trend_score)
                    # ================================================
                    
                    # 기술적 지표 계산
                    indicators = self.get_technical_indicators(stock_code)
                    if not indicators:
                        continue
                    
                    # 현재 보유 정보 조회
                    holdings = self.get_current_holdings(stock_code)
                    
                    # === 개선된 부분: 분할 매매 메타 정보 생성 ===
                    split_meta_list = self.get_enhanced_split_meta_info(stock_code, indicators, trading_params)
                    # ============================================
                    
                    # 종목 데이터 찾기
                    stock_data_info = None
                    for data_info in self.split_data_list:
                        if data_info['StockCode'] == stock_code:
                            stock_data_info = data_info
                            break
                    
                    # 종목 데이터가 없으면 새로 생성
                    if stock_data_info is None:
                        magic_data_list = []
                        
                        for i in range(len(split_meta_list)):
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
                    
                    # === 개선된 부분: 1차수 매수 처리 ===
                    first_magic_data = None
                    for magic_data in stock_data_info['MagicDataList']:
                        if magic_data['Number'] == 1:
                            first_magic_data = magic_data
                            break
                    
                    if first_magic_data and not first_magic_data['IsBuy'] and stock_data_info['IsReady']:
                        # 개선된 1차 진입 조건 체크
                        if self.check_enhanced_first_entry_condition(stock_code, indicators, trading_params):
                            stock_data_info['RealizedPNL'] = 0
                            
                            if holdings['amount'] > 0:  # 이미 종목을 보유 중인 경우
                                first_magic_data['IsBuy'] = True
                                first_magic_data['EntryPrice'] = holdings['avg_price']
                                first_magic_data['EntryAmt'] = holdings['amount']
                                first_magic_data['CurrentAmt'] = holdings['amount']
                                first_magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                self.save_split_data()
                                
                                msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 1차 투자를 하려고 했는데 잔고가 있어서 이를 1차투자로 가정! 시장상황: {market_trend}"
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
                                        first_magic_data['CurrentAmt'] = buy_amt
                                        first_magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                        self.save_split_data()
                                        
                                        msg = f"{stock_code} 스마트스플릿 1차 투자 완료! 시장상황: {market_trend}"
                                        logger.info(msg)
                                        discord_alert.SendMessage(msg)

    # === 개선된 부분: 보유 차수 매도 및 다음 차수 매수 처리 ===
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
                            
                            # === 개선된 매도 조건 체크 ===
                            should_sell = self.check_enhanced_sell_condition(
                                stock_code, magic_data, current_rate, split_meta, 
                                trading_params, market_trend, holdings, stock_data_info
                            )
                            
                            if should_sell:
                                # 종목 유형 확인 (성장주 여부)
                                is_growth_stock = stock_info.get('stock_type') == 'growth'
                                
                                # 성장주 부분 매도 적용
                                if is_growth_stock:
                                    current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                                    partial_sell_ratio = trading_params['partial_sell_ratio']
                                    sell_amt = max(1, int(current_amt * partial_sell_ratio))
                                    
                                    is_over = False
                                    if sell_amt > holdings['amount']:
                                        sell_amt = holdings['amount']
                                        is_over = True
                                    
                                    if holdings['amount'] - sell_amt < stock_info['min_holding']:
                                        sell_amt = max(0, holdings['amount'] - stock_info['min_holding'])
                                    
                                    if sell_amt > 0:
                                        result, error = self.handle_sell(stock_code, sell_amt, indicators['current_price'])
                                        
                                        if result:
                                            magic_data['CurrentAmt'] = current_amt - sell_amt
                                            
                                            if magic_data['CurrentAmt'] <= 0:
                                                magic_data['IsBuy'] = False
                                            
                                            if 'SellHistory' not in magic_data:
                                                magic_data['SellHistory'] = []
                                            
                                            realized_pnl = holdings['revenue_money'] * sell_amt / holdings['amount']
                                            
                                            magic_data['SellHistory'].append({
                                                "Date": datetime.now().strftime("%Y-%m-%d"),
                                                "Amount": sell_amt,
                                                "Price": indicators['current_price'],
                                                "Profit": realized_pnl
                                            })
                                            
                                            stock_data_info['IsReady'] = False
                                            self.update_realized_pnl(stock_code, realized_pnl)
                                            
                                            msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 {current_amt}주 중 {sell_amt}주 부분 매도! 수익률: {current_rate:.2f}% (시장: {market_trend})"
                                            if is_over:
                                                msg += " (보유량 초과로 전량 매도)"
                                            
                                            logger.info(msg)
                                            discord_alert.SendMessage(msg)
                                            self.save_split_data()
                                else:
                                    # 일반 종목 매도 로직
                                    sell_amt = magic_data['EntryAmt']
                                    
                                    is_over = False
                                    if sell_amt > holdings['amount']:
                                        sell_amt = holdings['amount']
                                        is_over = True
                                    
                                    if holdings['amount'] - sell_amt < stock_info['min_holding']:
                                        sell_amt = max(0, holdings['amount'] - stock_info['min_holding'])
                                    
                                    if sell_amt > 0:
                                        result, error = self.handle_sell(stock_code, sell_amt, indicators['current_price'])
                                        
                                        if result:
                                            magic_data['IsBuy'] = False
                                            stock_data_info['IsReady'] = False
                                            
                                            realized_pnl = holdings['revenue_money'] * sell_amt / holdings['amount']
                                            self.update_realized_pnl(stock_code, realized_pnl)
                                            
                                            msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 수익 매도! 목표수익률 {split_meta['target_rate']}% 달성 (시장: {market_trend})"
                                            if is_over:
                                                msg += " 보유량 초과로 전량 매도!"
                                            
                                            logger.info(msg)
                                            discord_alert.SendMessage(msg)
                        
                        # === 개선된 추가 매수 처리 (2차 이상) ===
                        elif magic_data['Number'] > 1:
                            prev_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], magic_data['Number'] - 1)
                            
                            if prev_magic_data and prev_magic_data['IsBuy']:
                                prev_rate = (indicators['current_price'] - prev_magic_data['EntryPrice']) / prev_magic_data['EntryPrice'] * 100.0
                                
                                logger.info(f"{stock_info['name']}({stock_code}) {magic_data['Number']}차 진입을 위한 {magic_data['Number']-1}차 수익률 {round(prev_rate, 2)}% 트리거 수익률 {split_meta['trigger_rate']}%")
                                
                                # 개선된 추가 매수 조건 체크
                                should_buy_next = self.check_enhanced_next_buy_condition(
                                    stock_code, magic_data, prev_rate, split_meta, 
                                    trading_params, market_trend, indicators
                                )
                                
                                if should_buy_next:
                                    buy_amt = max(1, int(split_meta['invest_money'] / indicators['current_price']))
                                    
                                    result, error = self.handle_buy(stock_code, buy_amt, indicators['current_price'])
                                    
                                    if result:
                                        magic_data['IsBuy'] = True
                                        magic_data['EntryPrice'] = indicators['current_price']
                                        magic_data['EntryAmt'] = buy_amt
                                        magic_data['CurrentAmt'] = buy_amt
                                        magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                        stock_data_info['IsReady'] = False
                                        self.save_split_data()
                                        
                                        msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 매수 완료! (시장: {market_trend})"
                                        logger.info(msg)
                                        discord_alert.SendMessage(msg)
                    
                    # 3. 풀매수 상태 확인 및 처리 (기존 로직 유지)
                    is_full_buy = all(data['IsBuy'] for data in stock_data_info['MagicDataList'])
                    
                    if is_full_buy:
                        last_split_meta = None
                        for meta in split_meta_list:
                            if meta['number'] == int(DIV_NUM):
                                last_split_meta = meta
                                break
                        
                        last_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], int(DIV_NUM))
                        
                        if last_split_meta and last_magic_data:
                            last_rate = (indicators['current_price'] - last_magic_data['EntryPrice']) / last_magic_data['EntryPrice'] * 100.0
                            
                            if last_rate <= last_split_meta['trigger_rate']:
                                msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 풀매수 상태인데 더 하락하여 2차수 손절 및 초기화!"
                                logger.info(msg)
                                discord_alert.SendMessage(msg)
                                
                                second_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], 2)
                                
                                if second_magic_data:
                                    current_amt = second_magic_data.get('CurrentAmt', second_magic_data['EntryAmt'])
                                    sell_amt = min(current_amt, holdings['amount'])
                                    
                                    if sell_amt > 0:
                                        result, error = self.handle_sell(stock_code, sell_amt, indicators['current_price'])
                                        
                                        if result:
                                            second_magic_data['IsBuy'] = False
                                            second_magic_data['CurrentAmt'] = 0
                                            stock_data_info['IsReady'] = False
                                            
                                            if 'SellHistory' not in second_magic_data:
                                                second_magic_data['SellHistory'] = []
                                            
                                            realized_pnl = holdings['revenue_money'] * sell_amt / holdings['amount']
                                            
                                            second_magic_data['SellHistory'].append({
                                                "Date": datetime.now().strftime("%Y-%m-%d"),
                                                "Amount": sell_amt,
                                                "Price": indicators['current_price'],
                                                "Profit": realized_pnl
                                            })
                                            
                                            self.update_realized_pnl(stock_code, realized_pnl)
                                            
                                            # 차수 재조정
                                            for i in range(int(DIV_NUM)):
                                                number = i + 1
                                                
                                                if number >= 2:
                                                    data = stock_data_info['MagicDataList'][i]
                                                    
                                                    if number == int(DIV_NUM):
                                                        data['IsBuy'] = False
                                                        data['EntryAmt'] = 0
                                                        data['CurrentAmt'] = 0
                                                        data['EntryPrice'] = 0
                                                    else:
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
            total_realized_pnl = 0
            summary_message = "📈 오늘의 스마트매직스플릿 수익률 요약 📈\n\n"
            
            summary_message += "[ 종목별 누적 수익 ]\n"
            
            for data_info in self.split_data_list:
                stock_code = data_info['StockCode']
                stock_name = data_info['StockName']
                realized_pnl = data_info.get('RealizedPNL', 0)
                total_realized_pnl += realized_pnl
                
                holdings = self.get_current_holdings(stock_code)
                current_price = KisKR.GetCurrentPrice(stock_code)
                
                unrealized_pnl = 0
                if holdings['amount'] > 0:
                    unrealized_pnl = holdings['revenue_money']
                
                active_positions = []
                for magic_data in data_info['MagicDataList']:
                    if magic_data['IsBuy']:
                        current_return = (current_price - magic_data['EntryPrice']) / magic_data['EntryPrice'] * 100
                        active_positions.append(f"{magic_data['Number']}차({round(current_return, 2)}%)")
                
                current_month = datetime.now().strftime('%Y-%m')
                monthly_pnl = data_info.get('MonthlyPNL', {}).get(current_month, 0)
                
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
            
            summary_message += "[ 총 누적 실현 손익 ]\n"
            summary_message += f"💰 {total_realized_pnl:,.0f}원\n\n"
            summary_message += f"💼 현재 할당된 총 투자 예산: {self.total_money:,.0f}원"
            
            discord_alert.SendMessage(summary_message)
            logger.info("일일 요약 알림 전송 완료")
            
        except Exception as e:
            logger.error(f"일일 요약 알림 전송 중 오류: {str(e)}")

    def check_trading_time():
        """장중 거래 가능한 시간대인지 체크하고 장 시작 시점도 확인"""
        try:
            if KisKR.IsTodayOpenCheck() == 'N':
                logger.info("휴장일 입니다.")
                return False, False

            market_status = KisKR.MarketStatus()
            if market_status is None or not isinstance(market_status, dict):
                logger.info("장 상태 확인 실패")
                return False, False
                
            status_code = market_status.get('Status', '')
            
            current_time = datetime.now().time()
            is_market_open = (status_code == '0' and current_time.hour == 8)
            is_trading_time = (status_code == '2')
            
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
            now.minute < 40 and
            SmartMagicSplit._daily_summary_sent_date != now.date()):
            
            bot.send_daily_summary()
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
        time.sleep(1)

if __name__ == "__main__":
    main()