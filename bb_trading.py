import json
import pandas as pd
import numpy as np
import discord_alert
import concurrent.futures
import threading
import time
from datetime import datetime, timedelta
from pytz import timezone
import os
import logging
from logging.handlers import TimedRotatingFileHandler

# 기존 API 라이브러리 import
import KIS_Common as Common
import KIS_API_Helper_KR as KisKR

################################### 상수 정의 ##################################

# 전략 설정
TRADE_BUDGET_RATIO = 0.08           # 전체 계좌의 8%를 이 봇이 사용
MAX_POSITION_SIZE = 0.25            # 단일 종목 최대 비중 25%
MAX_POSITIONS = 3                   # 최대 보유 종목 수
MIN_STOCK_PRICE = 5000              # 최소 주가 5,000원
MAX_STOCK_PRICE = 100000            # 최대 주가 100,000원

# 볼린저밴드 설정
BB_PERIOD = 20                      # 볼린저밴드 기간
BB_STD = 2                          # 표준편차 배수
BB_SQUEEZE_THRESHOLD = 0.1          # 볼린저밴드 수축 임계값

# RSI 설정
RSI_PERIOD = 14                     # RSI 계산 기간
RSI_OVERSOLD = 30                   # 과매도 구간
RSI_OVERBOUGHT = 70                 # 과매수 구간
RSI_BUY_THRESHOLD = 35              # 매수 신호 RSI
RSI_SELL_THRESHOLD = 65             # 매도 신호 RSI

# 거래량 설정
VOLUME_MA_PERIOD = 20               # 거래량 이동평균 기간
VOLUME_SURGE_RATIO = 1.5            # 거래량 급증 비율

# 손익 관리 설정
STOP_LOSS_RATIO = -0.03             # 손절 비율 (-3%)
TAKE_PROFIT_RATIO = 0.06            # 익절 비율 (6%)
TRAILING_STOP_RATIO = 0.02          # 트레일링 스탑 비율 (2%)
MAX_DAILY_LOSS = -0.05              # 일일 최대 손실 한도 (-5%)
MAX_DAILY_PROFIT = 0.08             # 일일 최대 수익 한도 (8%)

# 지지/저항선 설정
SUPPORT_RESISTANCE_PERIOD = 50      # 지지/저항선 계산 기간
PRICE_TOUCH_THRESHOLD = 0.01        # 가격 접촉 임계값 (1%)

# 봇 네임 설정
BOT_NAME = Common.GetNowDist() + "_BollingerBandBot"

################################### 로깅 처리 ##################################

# 로그 디렉토리 생성
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

def log_namer(default_name):
    """로그 파일 이름 생성 함수"""
    base_filename, ext, date = default_name.split(".")
    return f"{base_filename}.{date}.{ext}"

# 로거 설정
logger = logging.getLogger('BollingerBandLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정
log_file = os.path.join(log_directory, 'bollinger_trading.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=7,
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

# KIS API 모듈에 로거 전달
KisKR.set_logger(logger)
Common.set_logger(logger)

################################### 유틸리티 함수 ##################################

def calculate_trading_fee(price, quantity, is_buy=True):
    """거래 수수료 및 세금 계산"""
    commission_rate = 0.0000156  # 수수료 0.00156%
    tax_rate = 0  # 매도 시 거래세 0%
    special_tax_rate = 0.0015  # 농어촌특별세 (매도금액의 0.15%)
    
    commission = price * quantity * commission_rate
    if not is_buy:  # 매도 시에만 세금 부과
        tax = price * quantity * tax_rate
        special_tax = price * quantity * special_tax_rate
    else:
        tax = 0
        special_tax = 0
    
    return commission + tax + special_tax

def check_trading_time():
    """장중 거래 가능한 시간대인지 체크"""
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
        
        # 장 시작 시점 체크
        current_time = datetime.now().time()
        is_market_open = (status_code == '0' and current_time.hour == 8)
        
        # 거래 가능 시간 체크
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

################################### 기술적 분석 함수 ##################################

def calculate_bollinger_bands(df, period=BB_PERIOD, std_dev=BB_STD):
    """볼린저밴드 계산"""
    try:
        close_prices = df['close']
        
        # 이동평균선 계산
        sma = close_prices.rolling(window=period).mean()
        
        # 표준편차 계산
        std = close_prices.rolling(window=period).std()
        
        # 볼린저밴드 계산
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        # 밴드폭 계산 (변동성 측정)
        band_width = (upper_band - lower_band) / sma
        
        return {
            'upper_band': upper_band.iloc[-1] if not pd.isna(upper_band.iloc[-1]) else 0,
            'middle_band': sma.iloc[-1] if not pd.isna(sma.iloc[-1]) else 0,
            'lower_band': lower_band.iloc[-1] if not pd.isna(lower_band.iloc[-1]) else 0,
            'band_width': band_width.iloc[-1] if not pd.isna(band_width.iloc[-1]) else 0,
            'upper_series': upper_band,
            'middle_series': sma,
            'lower_series': lower_band
        }
    except Exception as e:
        logger.error(f"볼린저밴드 계산 중 에러: {str(e)}")
        return None

def calculate_rsi(df, period=RSI_PERIOD):
    """RSI 계산"""
    try:
        close_prices = df['close']
        delta = close_prices.diff()
        
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss.replace(0, 0.00001)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    except Exception as e:
        logger.error(f"RSI 계산 중 에러: {str(e)}")
        return 50

def calculate_volume_analysis(df, period=VOLUME_MA_PERIOD):
    """거래량 분석"""
    try:
        volume = df['volume']
        volume_ma = volume.rolling(window=period).mean()
        
        current_volume = volume.iloc[-1]
        avg_volume = volume_ma.iloc[-1] if not pd.isna(volume_ma.iloc[-1]) else current_volume
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        is_volume_surge = volume_ratio >= VOLUME_SURGE_RATIO
        
        return {
            'current_volume': current_volume,
            'average_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'is_surge': is_volume_surge
        }
    except Exception as e:
        logger.error(f"거래량 분석 중 에러: {str(e)}")
        return None

def find_support_resistance(df, period=SUPPORT_RESISTANCE_PERIOD):
    """지지선과 저항선 찾기"""
    try:
        if len(df) < period:
            return None
            
        recent_data = df.tail(period)
        highs = recent_data['high']
        lows = recent_data['low']
        
        # 최근 기간의 최고가/최저가
        resistance = highs.max()
        support = lows.min()
        
        # 현재가와의 거리 계산
        current_price = df['close'].iloc[-1]
        resistance_distance = (resistance - current_price) / current_price
        support_distance = (current_price - support) / current_price
        
        return {
            'resistance': resistance,
            'support': support,
            'resistance_distance': resistance_distance,
            'support_distance': support_distance,
            'near_resistance': resistance_distance <= PRICE_TOUCH_THRESHOLD,
            'near_support': support_distance <= PRICE_TOUCH_THRESHOLD
        }
    except Exception as e:
        logger.error(f"지지/저항선 계산 중 에러: {str(e)}")
        return None

def get_stock_data(stock_code):
    """종목 데이터 조회 및 기술적 분석"""
    try:
        # 일봉 데이터 조회
        df = Common.GetOhlcv("KR", stock_code, 60)  # 60일 데이터
        
        if df is None or len(df) < 30:
            logger.error(f"{stock_code}: 데이터 부족")
            return None
        
        # 현재가 조회
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price or current_price <= 0:
            logger.error(f"{stock_code}: 현재가 조회 실패")
            return None
        
        # 기술적 분석 수행
        bb_data = calculate_bollinger_bands(df)
        rsi = calculate_rsi(df)
        volume_data = calculate_volume_analysis(df)
        sr_data = find_support_resistance(df)
        
        # 볼린저밴드 위치 계산
        bb_position = None
        if bb_data:
            if current_price <= bb_data['lower_band']:
                bb_position = 'below_lower'
            elif current_price >= bb_data['upper_band']:
                bb_position = 'above_upper'
            elif current_price <= bb_data['middle_band']:
                bb_position = 'below_middle'
            else:
                bb_position = 'above_middle'
        
        return {
            'stock_code': stock_code,
            'current_price': current_price,
            'ohlcv_data': df,
            'bollinger_bands': bb_data,
            'rsi': rsi,
            'volume_analysis': volume_data,
            'support_resistance': sr_data,
            'bb_position': bb_position
        }
        
    except Exception as e:
        logger.error(f"종목 데이터 조회 중 에러: {str(e)}")
        return None

################################### 매매 신호 분석 ##################################

def analyze_buy_signal(stock_data):
    """매수 신호 분석"""
    try:
        signals = []
        score = 0
        
        current_price = stock_data['current_price']
        bb_data = stock_data['bollinger_bands']
        rsi = stock_data['rsi']
        volume_data = stock_data['volume_analysis']
        sr_data = stock_data['support_resistance']
        bb_position = stock_data['bb_position']
        
        # 1. 볼린저밴드 신호 (30점)
        if bb_position == 'below_lower':
            score += 20
            signals.append("볼린저밴드 하단 터치 (+20)")
        elif bb_position == 'below_middle':
            score += 10
            signals.append("볼린저밴드 중간선 하단 (+10)")
        
        # 볼린저밴드 수축 확인 (변동성 축소)
        if bb_data and bb_data['band_width'] < BB_SQUEEZE_THRESHOLD:
            score += 10
            signals.append("볼린저밴드 수축 (+10)")
        
        # 2. RSI 신호 (25점)
        if rsi <= RSI_OVERSOLD:
            score += 15
            signals.append(f"RSI 과매도 {rsi:.1f} (+15)")
        elif rsi <= RSI_BUY_THRESHOLD:
            score += 10
            signals.append(f"RSI 매수신호 {rsi:.1f} (+10)")
        
        # 3. 거래량 신호 (20점)
        if volume_data and volume_data['is_surge']:
            score += 15
            signals.append(f"거래량 급증 {volume_data['volume_ratio']:.1f}배 (+15)")
        elif volume_data and volume_data['volume_ratio'] > 1.2:
            score += 10
            signals.append(f"거래량 증가 {volume_data['volume_ratio']:.1f}배 (+10)")
        
        # 4. 지지선 신호 (15점)
        if sr_data and sr_data['near_support']:
            score += 15
            signals.append(f"지지선 근처 {sr_data['support']:,.0f}원 (+15)")
        
        # 5. 추가 확인 신호 (10점)
        # 가격이 상승 추세인지 확인
        df = stock_data['ohlcv_data']
        if len(df) >= 5:
            recent_trend = df['close'].tail(5).iloc[-1] > df['close'].tail(5).iloc[0]
            if recent_trend:
                score += 5
                signals.append("단기 상승 추세 (+5)")
        
        # 매수 신호 판정 (70점 이상)
        is_buy_signal = score >= 70
        
        return {
            'is_buy_signal': is_buy_signal,
            'score': score,
            'signals': signals,
            'analysis': {
                'bb_position': bb_position,
                'rsi': rsi,
                'volume_ratio': volume_data['volume_ratio'] if volume_data else 0,
                'near_support': sr_data['near_support'] if sr_data else False
            }
        }
        
    except Exception as e:
        logger.error(f"매수 신호 분석 중 에러: {str(e)}")
        return {'is_buy_signal': False, 'score': 0, 'signals': []}

def analyze_sell_signal(stock_data, position):
    """매도 신호 분석"""
    try:
        signals = []
        score = 0
        
        current_price = stock_data['current_price']
        entry_price = position['entry_price']
        bb_data = stock_data['bollinger_bands']
        rsi = stock_data['rsi']
        volume_data = stock_data['volume_analysis']
        sr_data = stock_data['support_resistance']
        bb_position = stock_data['bb_position']
        
        # 수익률 계산
        profit_rate = (current_price - entry_price) / entry_price
        
        # 1. 손익 관리 신호 (최우선)
        if profit_rate <= STOP_LOSS_RATIO:
            return {
                'is_sell_signal': True,
                'sell_type': 'stop_loss',
                'score': 100,
                'signals': [f"손절 실행 {profit_rate*100:.1f}%"],
                'urgent': True
            }
        
        if profit_rate >= TAKE_PROFIT_RATIO:
            return {
                'is_sell_signal': True,
                'sell_type': 'take_profit',
                'score': 100,
                'signals': [f"익절 실행 {profit_rate*100:.1f}%"],
                'urgent': True
            }
        
        # 트레일링 스탑 확인
        if 'high_price' in position:
            trailing_loss = (position['high_price'] - current_price) / position['high_price']
            if trailing_loss >= TRAILING_STOP_RATIO:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop',
                    'score': 100,
                    'signals': [f"트레일링 스탑 {trailing_loss*100:.1f}%"],
                    'urgent': True
                }
        
        # 2. 볼린저밴드 신호 (30점)
        if bb_position == 'above_upper':
            score += 20
            signals.append("볼린저밴드 상단 터치 (+20)")
        elif bb_position == 'above_middle':
            score += 10
            signals.append("볼린저밴드 중간선 상단 (+10)")
        
        # 3. RSI 신호 (25점)
        if rsi >= RSI_OVERBOUGHT:
            score += 15
            signals.append(f"RSI 과매수 {rsi:.1f} (+15)")
        elif rsi >= RSI_SELL_THRESHOLD:
            score += 10
            signals.append(f"RSI 매도신호 {rsi:.1f} (+10)")
        
        # 4. 거래량 신호 (20점)
        if volume_data and volume_data['is_surge'] and profit_rate > 0:
            score += 15
            signals.append(f"수익 중 거래량 급증 {volume_data['volume_ratio']:.1f}배 (+15)")
        
        # 5. 저항선 신호 (15점)
        if sr_data and sr_data['near_resistance']:
            score += 15
            signals.append(f"저항선 근처 {sr_data['resistance']:,.0f}원 (+15)")
        
        # 6. 하락 추세 신호 (10점)
        df = stock_data['ohlcv_data']
        if len(df) >= 5:
            recent_trend = df['close'].tail(5).iloc[-1] < df['close'].tail(5).iloc[0]
            if recent_trend:
                score += 10
                signals.append("단기 하락 추세 (+10)")
        
        # 매도 신호 판정 (65점 이상)
        is_sell_signal = score >= 65
        
        return {
            'is_sell_signal': is_sell_signal,
            'sell_type': 'technical',
            'score': score,
            'signals': signals,
            'urgent': False,
            'profit_rate': profit_rate
        }
        
    except Exception as e:
        logger.error(f"매도 신호 분석 중 에러: {str(e)}")
        return {'is_sell_signal': False, 'score': 0, 'signals': []}

################################### 상태 관리 ##################################

def load_trading_state():
    """트레이딩 상태 로드"""
    try:
        with open(f"BollingerBot_{BOT_NAME}.json", 'r') as f:
            return json.load(f)
    except:
        return {
            'positions': {},
            'daily_stats': {
                'date': '',
                'total_profit': 0,
                'total_trades': 0,
                'winning_trades': 0,
                'start_balance': 0
            }
        }

def save_trading_state(state):
    """트레이딩 상태 저장"""
    with open(f"BollingerBot_{BOT_NAME}.json", 'w') as f:
        json.dump(state, f, indent=2)

################################### 매매 실행 ##################################

def calculate_position_size(available_budget, stock_price, current_positions):
    """포지션 크기 계산"""
    try:
        # 계좌 잔고 확인
        balance = KisKR.GetBalance()
        if not balance:
            return 0
            
        actual_balance = float(balance.get('RemainMoney', 0))
        
        # 실제 사용 가능한 금액
        usable_budget = min(available_budget, actual_balance)
        
        # 단일 종목 최대 투자 금액
        max_single_investment = usable_budget * MAX_POSITION_SIZE
        
        # 매수 가능 수량 계산
        max_quantity = int(max_single_investment / stock_price)
        
        # 최소 1주는 매수 가능하도록
        return max(1, max_quantity) if max_quantity > 0 else 0
        
    except Exception as e:
        logger.error(f"포지션 크기 계산 중 에러: {str(e)}")
        return 0

def execute_buy_order(stock_code, stock_name, quantity, price):
    """매수 주문 실행"""
    try:
        logger.info(f"{stock_name}({stock_code}) 매수 주문: {quantity}주 @ {price:,.0f}원")
        
        # 지정가 매수 주문
        order_result = KisKR.MakeBuyLimitOrder(stock_code, quantity, int(price))
        
        if not order_result or isinstance(order_result, str):
            logger.error(f"매수 주문 실패: {order_result}")
            return None, None
        
        # 체결 확인 (최대 30초 대기)
        start_time = time.time()
        while time.time() - start_time < 30:
            # 보유 종목 확인
            my_stocks = KisKR.GetMyStockList()
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    executed_amount = int(stock.get('StockAmt', 0))
                    if executed_amount > 0:
                        avg_price = float(stock.get('AvrPrice', price))
                        logger.info(f"매수 체결 확인: {executed_amount}주 @ {avg_price:,.0f}원")
                        return avg_price, executed_amount
            time.sleep(2)
        
        logger.warning(f"매수 체결 확인 실패: {stock_code}")
        return None, None
        
    except Exception as e:
        logger.error(f"매수 주문 실행 중 에러: {str(e)}")
        return None, None

def execute_sell_order(stock_code, stock_name, quantity):
    """매도 주문 실행"""
    try:
        logger.info(f"{stock_name}({stock_code}) 매도 주문: {quantity}주")
        
        # 시장가 매도 주문
        order_result = KisKR.MakeSellMarketOrder(stock_code, quantity)
        
        if not order_result or isinstance(order_result, str):
            logger.error(f"매도 주문 실패: {order_result}")
            return None, None
        
        # 체결 확인 (최대 30초 대기)
        start_time = time.time()
        initial_amount = quantity
        
        while time.time() - start_time < 30:
            # 보유 종목 확인
            my_stocks = KisKR.GetMyStockList()
            current_amount = 0
            
            for stock in my_stocks:
                if stock['StockCode'] == stock_code:
                    current_amount = int(stock.get('StockAmt', 0))
                    break
            
            # 수량이 줄어들었으면 매도 체결
            if current_amount < initial_amount:
                executed_amount = initial_amount - current_amount
                current_price = KisKR.GetCurrentPrice(stock_code)
                logger.info(f"매도 체결 확인: {executed_amount}주 @ {current_price:,.0f}원")
                return current_price, executed_amount
            
            time.sleep(2)
        
        logger.warning(f"매도 체결 확인 실패: {stock_code}")
        return None, None
        
    except Exception as e:
        logger.error(f"매도 주문 실행 중 에러: {str(e)}")
        return None, None

################################### 보고서 생성 ##################################

def send_daily_report(trading_state):
    """일일 거래 성과 보고서"""
    try:
        balance = KisKR.GetBalance()
        my_stocks = KisKR.GetMyStockList()
        daily_stats = trading_state['daily_stats']
        
        total_money = float(balance.get('TotalMoney', 0))
        stock_revenue = float(balance.get('StockRevenue', 0))
        
        msg = "📊 볼린저밴드 봇 일일 성과 보고서 📊\n"
        msg += f"========== {datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
        msg += f"[전체 계좌 현황]\n"
        msg += f"총 평가금액: {total_money:,.0f}원\n"
        msg += f"누적 손익: {stock_revenue:,.0f}원\n"
        
        if my_stocks:
            msg += "\n[보유 종목 현황]\n"
            for stock in my_stocks:
                if stock['StockCode'] in trading_state['positions']:
                    msg += f"- {stock['StockName']}({stock['StockCode']}): "
                    msg += f"{stock['StockAmt']}주, {float(stock['StockRevenueMoney']):,.0f}원 "
                    msg += f"({stock['StockRevenueRate']}%)\n"
        else:
            msg += "\n현재 보유 종목 없음\n"
        
        if daily_stats['total_trades'] > 0:
            winning_rate = (daily_stats['winning_trades'] / daily_stats['total_trades']) * 100
            msg += f"\n[봇 거래 성과]\n"
            msg += f"일일 실현손익: {daily_stats['total_profit']:,.0f}원\n"
            msg += f"총 거래: {daily_stats['total_trades']}회 (승률: {winning_rate:.1f}%)"
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
    except Exception as e:
        logger.error(f"일일 보고서 생성 중 에러: {str(e)}")

################################### 메인 로직 ##################################

def get_candidate_stocks():
    """매수 후보 종목 조회"""
    try:
        # 시가총액 상위 종목들 중에서 선별
        stock_list = KisKR.GetMarketCodeList(
            price_limit=MAX_STOCK_PRICE,
            min_market_cap=500000000000,  # 5천억원 이상
            min_volume=50000,             # 최소 거래량
            max_stocks=50
        )
        
        if not stock_list:
            logger.info("후보 종목 리스트가 비어있습니다.")
            return []
        
        logger.info(f"총 {len(stock_list)}개 후보 종목 조회 완료")
        return stock_list
        
    except Exception as e:
        logger.error(f"후보 종목 조회 중 에러: {str(e)}")
        return []

def scan_buy_opportunities(trading_state):
    """매수 기회 스캔"""
    try:
        candidate_stocks = get_candidate_stocks()
        if not candidate_stocks:
            return []
        
        buy_opportunities = []
        current_positions = len(trading_state['positions'])
        
        # 최대 보유 종목 수 확인
        if current_positions >= MAX_POSITIONS:
            logger.info(f"최대 보유 종목 수({MAX_POSITIONS}개) 도달")
            return []
        
        logger.info(f"매수 기회 스캔 시작: {len(candidate_stocks)}개 종목 분석")
        
        for stock in candidate_stocks:
            try:
                stock_code = stock['code']
                stock_name = stock['name']
                
                # 이미 보유 중인 종목은 제외
                if stock_code in trading_state['positions']:
                    continue
                
                # 가격 필터링
                current_price = KisKR.GetCurrentPrice(stock_code)
                if not current_price or current_price < MIN_STOCK_PRICE:
                    continue
                
                # 종목 데이터 분석
                stock_data = get_stock_data(stock_code)
                if not stock_data:
                    continue
                
                # 매수 신호 분석
                buy_analysis = analyze_buy_signal(stock_data)
                
                if buy_analysis['is_buy_signal']:
                    buy_opportunities.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'price': current_price,
                        'score': buy_analysis['score'],
                        'signals': buy_analysis['signals'],
                        'analysis': buy_analysis['analysis']
                    })
                    
                    logger.info(f"✅ 매수 기회 발견: {stock_name}({stock_code})")
                    logger.info(f"   점수: {buy_analysis['score']}점")
                    for signal in buy_analysis['signals']:
                        logger.info(f"   - {signal}")
            
            except Exception as e:
                logger.error(f"종목 분석 중 에러 ({stock_code}): {str(e)}")
                continue
        
        # 점수 순으로 정렬
        buy_opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"매수 기회 스캔 완료: {len(buy_opportunities)}개 발견")
        return buy_opportunities
        
    except Exception as e:
        logger.error(f"매수 기회 스캔 중 에러: {str(e)}")
        return []

def update_trailing_stop(position, current_price):
    """트레일링 스탑 업데이트"""
    try:
        # 고점 업데이트
        if 'high_price' not in position or current_price > position['high_price']:
            position['high_price'] = current_price
            position['trailing_stop'] = current_price * (1 - TRAILING_STOP_RATIO)
            logger.info(f"트레일링 스탑 업데이트: 고점 {current_price:,.0f}원, 스탑 {position['trailing_stop']:,.0f}원")
        
        return position
        
    except Exception as e:
        logger.error(f"트레일링 스탑 업데이트 중 에러: {str(e)}")
        return position

def process_positions(trading_state):
    """보유 포지션 관리"""
    try:
        my_stocks = KisKR.GetMyStockList()
        positions_to_remove = []
        
        for stock_code, position in trading_state['positions'].items():
            try:
                # 실제 보유 여부 확인
                actual_holding = None
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        actual_holding = stock
                        break
                
                if not actual_holding:
                    logger.warning(f"{stock_code}: 포지션 정보는 있으나 실제 보유하지 않음")
                    positions_to_remove.append(stock_code)
                    continue
                
                stock_name = KisKR.GetStockName(stock_code)
                current_amount = int(actual_holding.get('StockAmt', 0))
                
                if current_amount <= 0:
                    positions_to_remove.append(stock_code)
                    continue
                
                # 종목 데이터 조회
                stock_data = get_stock_data(stock_code)
                if not stock_data:
                    continue
                
                current_price = stock_data['current_price']
                
                # 트레일링 스탑 업데이트
                position = update_trailing_stop(position, current_price)
                trading_state['positions'][stock_code] = position
                
                # 매도 신호 분석
                sell_analysis = analyze_sell_signal(stock_data, position)
                
                if sell_analysis['is_sell_signal']:
                    logger.info(f"🔴 매도 신호 감지: {stock_name}({stock_code})")
                    logger.info(f"   유형: {sell_analysis['sell_type']}")
                    logger.info(f"   점수: {sell_analysis['score']}점")
                    for signal in sell_analysis['signals']:
                        logger.info(f"   - {signal}")
                    
                    # 매도 주문 실행
                    executed_price, executed_amount = execute_sell_order(
                        stock_code, stock_name, current_amount
                    )
                    
                    if executed_price and executed_amount:
                        # 손익 계산
                        entry_price = position['entry_price']
                        buy_fee = position.get('buy_fee', 0)
                        sell_fee = calculate_trading_fee(executed_price, executed_amount, False)
                        
                        gross_profit = (executed_price - entry_price) * executed_amount
                        net_profit = gross_profit - buy_fee - sell_fee
                        profit_rate = (net_profit / (entry_price * executed_amount)) * 100
                        
                        # 일일 통계 업데이트
                        trading_state['daily_stats']['total_profit'] += net_profit
                        trading_state['daily_stats']['total_trades'] += 1
                        if net_profit > 0:
                            trading_state['daily_stats']['winning_trades'] += 1
                        
                        # 매도 완료 알림
                        msg = f"💰 매도 완료: {stock_name}({stock_code})\n"
                        msg += f"매도가: {executed_price:,.0f}원\n"
                        msg += f"수량: {executed_amount}주\n"
                        msg += f"순손익: {net_profit:,.0f}원 ({profit_rate:.2f}%)\n"
                        msg += f"매도사유: {sell_analysis['sell_type']}"
                        
                        logger.info(msg)
                        discord_alert.SendMessage(msg)
                        
                        # 포지션 제거
                        positions_to_remove.append(stock_code)
                    else:
                        logger.error(f"매도 주문 실패: {stock_name}({stock_code})")
                
            except Exception as e:
                logger.error(f"포지션 처리 중 에러 ({stock_code}): {str(e)}")
                continue
        
        # 제거할 포지션 정리
        for stock_code in positions_to_remove:
            if stock_code in trading_state['positions']:
                del trading_state['positions'][stock_code]
                logger.info(f"포지션 제거: {stock_code}")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"포지션 관리 중 에러: {str(e)}")
        return trading_state

def execute_buy_opportunities(buy_opportunities, trading_state):
    """매수 기회 실행"""
    try:
        if not buy_opportunities:
            return trading_state
        
        # 계좌 정보 조회
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return trading_state
        
        total_money = float(balance.get('TotalMoney', 0))
        available_budget = total_money * TRADE_BUDGET_RATIO
        
        # 일일 손실 한도 확인
        daily_loss_rate = trading_state['daily_stats']['total_profit'] / trading_state['daily_stats']['start_balance'] if trading_state['daily_stats']['start_balance'] > 0 else 0
        
        if daily_loss_rate <= MAX_DAILY_LOSS:
            logger.info(f"일일 손실 한도 도달: {daily_loss_rate*100:.1f}%")
            return trading_state
        
        # 일일 수익 한도 확인
        if daily_loss_rate >= MAX_DAILY_PROFIT:
            logger.info(f"일일 수익 한도 도달: {daily_loss_rate*100:.1f}%")
            return trading_state
        
        current_positions = len(trading_state['positions'])
        max_new_positions = MAX_POSITIONS - current_positions
        
        # 상위 종목들에 대해 매수 실행
        for i, opportunity in enumerate(buy_opportunities[:max_new_positions]):
            try:
                stock_code = opportunity['stock_code']
                stock_name = opportunity['stock_name']
                stock_price = opportunity['price']
                
                # 포지션 크기 계산
                quantity = calculate_position_size(
                    available_budget / max_new_positions,
                    stock_price,
                    trading_state['positions']
                )
                
                if quantity < 1:
                    logger.info(f"매수 수량 부족: {stock_name}({stock_code})")
                    continue
                
                logger.info(f"🔵 매수 시도: {stock_name}({stock_code})")
                logger.info(f"   수량: {quantity}주, 가격: {stock_price:,.0f}원")
                
                # 매수 주문 실행
                executed_price, executed_amount = execute_buy_order(
                    stock_code, stock_name, quantity, stock_price
                )
                
                if executed_price and executed_amount:
                    # 매수 수수료 계산
                    buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                    
                    # 포지션 정보 저장
                    trading_state['positions'][stock_code] = {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'entry_price': executed_price,
                        'amount': executed_amount,
                        'buy_fee': buy_fee,
                        'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'high_price': executed_price,
                        'trailing_stop': executed_price * (1 - TRAILING_STOP_RATIO),
                        'buy_analysis': opportunity['analysis']
                    }
                    
                    # 매수 완료 알림
                    msg = f"✅ 매수 완료: {stock_name}({stock_code})\n"
                    msg += f"매수가: {executed_price:,.0f}원\n"
                    msg += f"수량: {executed_amount}주\n"
                    msg += f"투자금액: {executed_price * executed_amount:,.0f}원\n"
                    msg += f"수수료: {buy_fee:,.0f}원"
                    
                    logger.info(msg)
                    discord_alert.SendMessage(msg)
                else:
                    logger.error(f"매수 주문 실패: {stock_name}({stock_code})")
                
            except Exception as e:
                logger.error(f"매수 실행 중 에러: {str(e)}")
                continue
        
        return trading_state
        
    except Exception as e:
        logger.error(f"매수 기회 실행 중 에러: {str(e)}")
        return trading_state

def main():
    """메인 함수"""
    msg = "🤖 볼린저밴드 매매 봇 시작!"
    logger.info(msg)
    discord_alert.SendMessage(msg)
    
    # 초기 상태
    daily_report_sent = False
    market_open_notified = False
    
    while True:
        try:
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            
            # 거래 시간 체크
            is_trading_time, is_market_open = check_trading_time()
            
            # 트레이딩 상태 로드
            trading_state = load_trading_state()
            
            # 날짜가 바뀌면 일일 통계 초기화
            if trading_state['daily_stats']['date'] != today:
                balance = KisKR.GetBalance()
                start_balance = float(balance.get('TotalMoney', 0)) if balance else 0
                
                trading_state['daily_stats'] = {
                    'date': today,
                    'total_profit': 0,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'start_balance': start_balance
                }
                daily_report_sent = False
                market_open_notified = False
                save_trading_state(trading_state)
            
            # 장 시작 알림
            if is_market_open and not market_open_notified:
                balance = KisKR.GetBalance()
                if balance:
                    total_money = float(balance.get('TotalMoney', 0))
                    msg = f"🔔 장 시작!\n총 자산: {total_money:,.0f}원\n"
                    msg += f"봇 운용자금: {total_money * TRADE_BUDGET_RATIO:,.0f}원"
                    logger.info(msg)
                    discord_alert.SendMessage(msg)
                market_open_notified = True
            
            # 거래 시간이 아니면 대기
            if not is_trading_time:
                logger.info("장 시간 외입니다.")
                time.sleep(300)  # 5분 대기
                continue
            
            # 포지션 관리 (매도 신호 체크)
            logger.info("=== 보유 포지션 관리 ===")
            trading_state = process_positions(trading_state)
            save_trading_state(trading_state)
            
            # 새로운 매수 기회 스캔 (15시 이전까지만)
            if now.hour < 15:
                logger.info("=== 매수 기회 스캔 ===")
                buy_opportunities = scan_buy_opportunities(trading_state)
                
                if buy_opportunities:
                    # 매수 실행
                    trading_state = execute_buy_opportunities(buy_opportunities, trading_state)
                    save_trading_state(trading_state)
            
            # 장 마감 후 일일 보고서 (15:30 이후)
            if now.hour >= 15 and now.minute >= 30 and not daily_report_sent:
                send_daily_report(trading_state)
                daily_report_sent = True
            
            # 30초 대기
            time.sleep(30)
            
        except Exception as e:
            error_msg = f"⚠️ 메인 루프 에러: {str(e)}"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            time.sleep(60)  # 에러 발생 시 1분 대기

if __name__ == "__main__":
    # 실제 거래 모드로 설정 (테스트 시에는 주석 해제)
    # Common.SetChangeMode("VIRTUAL")
    Common.SetChangeMode()
    
    main()