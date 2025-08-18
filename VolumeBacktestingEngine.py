#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
거래량 기반 자동매매 봇 백테스팅 엔진 (VolumeBacktestingEngine.py)
기존 VolumeBasedTradingBot_KR의 매매 로직을 과거 데이터로 시뮬레이션
"""

import KIS_Common as Common
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import logging
import time

################################### 로깅 설정 ##################################
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# KIS_Common 모듈에 로거 설정
Common.set_logger(logger)

################################### 백테스팅 엔진 클래스 ##################################

class VolumeBacktestingEngine:
    """거래량 기반 매매 백테스팅 엔진"""
    
    def __init__(self, initial_capital=5000000, max_positions=5, commission_rate=0.00015):
        """
        Args:
            initial_capital (int): 초기 투자금액 (기본 500만원)
            max_positions (int): 최대 보유 종목 수
            commission_rate (float): 거래 수수료율 (기본 0.015%)
        """
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.commission_rate = commission_rate
        
        # 백테스팅 설정 (기존 봇과 동일 - 원본 설정)
        self.config = {
            "buy_conditions": {
                # 거래량 급증 패턴 감지 강화
                "volume_surge_ratio": 1.8,        # 2.0 → 1.8 (더 많은 신호 포착)
                "volume_surge_ratio_strong": 2.5, # 강한 신호용 추가 기준
                "consecutive_pattern_days": 3,
                "pullback_volume_decrease": 0.75,  # 0.7 → 0.75 (눌림목 조건 완화)
                "candle_body_ratio": 0.55,        # 0.6 → 0.55 (양봉 조건 완화)
                "min_price_increase": 2.5,        # 3.0 → 2.5 (가격 상승 조건 완화)
                "rsi_upper_limit": 70,             # 75 → 70 (과매수 구간 진입 전 매수)
                "volume_ma_period": 20,
                # 신호 강도별 차별화 추가
                "strong_signal_rsi_limit": 75,     # 강한 신호는 RSI 75까지 허용
                "min_hold_days": 2                 # 최소 보유 기간 추가
            },
            "sell_conditions": {
                "high_volume_surge": 2.8,          # 3.0 → 2.8 (분배 패턴 조기 감지)
                "negative_candle_threshold": 0.5,
                # 신호별 차별화된 목표 수익률
                "profit_target_normal": 25.0,      # 일반 신호: 25%
                "profit_target_strong": 40.0,      # 강한 신호: 40%
                "profit_target_pullback": 15.0,    # 눌림목: 15%
                "quick_profit_target": 8.0,        # 빠른 수익실현: 8%
                "stop_loss": -12.0,                # -15.0 → -12.0 (손절선 강화)
                "volume_decrease_days": 2,          # 3 → 2 (너무 빠른 매도 방지)
                "rsi_sell_threshold": 75,           # 80 → 75 (조기 수익실현)
                # 보유기간별 매도 조건 추가
                "min_hold_before_tech_sell": 3,     # 기술적 매도 전 최소 보유일
                "trailing_stop_activation": 15.0,   # 15% 수익시 트레일링 스톱 활성화
                "trailing_stop_ratio": 0.85        # 고점 대비 85% 하락시 매도
            }
        }
        
        # 백테스팅 상태 변수
        self.current_cash = initial_capital
        self.positions = {}  # {종목코드: {amount, entry_price, entry_date, signal_type}}
        self.trade_history = []
        self.daily_portfolio_value = []
        
        logger.info(f"백테스팅 엔진 초기화 완료 - 초기자금: {initial_capital:,}원")

    def get_historical_data(self, stock_code, days=365):
        """과거 데이터 조회"""
        try:
            logger.info(f"{stock_code} 데이터 조회 시작...")
            
            # KIS API를 통한 데이터 조회 시도
            try:
                import KIS_API_Helper_KR as KisKR
                # KIS API에 로거 설정
                KisKR.set_logger(logger)
                
                # # 모의계좌 모드로 설정 (데이터 조회용)
                # Common.SetChangeMode("VIRTUAL")
                
                df = KisKR.GetOhlcvNew(stock_code, "D", days)
                
                if df is None or len(df) < 50:
                    logger.warning(f"{stock_code}: KIS API 데이터 부족, 대체 방법 시도...")
                    # 대체 방법으로 Common.GetOhlcv 사용
                    df = Common.GetOhlcv("KR", stock_code, days)
                
            except Exception as e:
                logger.warning(f"{stock_code}: KIS API 조회 실패 ({str(e)}), 대체 방법 사용...")
                # 대체 방법으로 Common.GetOhlcv 사용
                df = Common.GetOhlcv("KR", stock_code, days)
            
            if df is None or len(df) < 50:
                logger.warning(f"{stock_code}: 데이터 부족 (길이: {len(df) if df is not None else 0})")
                return None
            
            logger.info(f"{stock_code}: 데이터 로드 완료 ({len(df)}일치)")
            
            # 거래량 관련 지표 계산
            df['volume_ma5'] = df['volume'].rolling(5).mean()
            df['volume_ma20'] = df['volume'].rolling(20).mean()
            
            # 0으로 나누기 방지
            df['volume_ratio'] = df['volume'] / df['volume_ma20'].replace(0, 1)
            df['price_change'] = (df['close'] - df['open']) / df['open'].replace(0, 0.0001) * 100
            
            # 고가-저가가 0인 경우 방지
            price_range = (df['high'] - df['low']).replace(0, 0.0001)
            df['candle_body_ratio'] = abs(df['close'] - df['open']) / price_range
            
            # RSI 계산
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta).where(delta < 0, 0).rolling(14).mean()
            rs = gain / loss.replace(0, 1)  # 0으로 나누기 방지
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # NaN 값 처리 (최신 pandas 문법 사용)
            df = df.ffill().bfill()
            
            return df
            
        except Exception as e:
            logger.error(f"{stock_code} 데이터 조회 오류: {str(e)}")
            return None

    def detect_volume_surge_pattern(self, df, idx):
        """거래량 급증 패턴 감지 (개선된 버전)"""
        try:
            if idx < 20:
                return False, {}
            
            buy_conditions = self.config["buy_conditions"]
            
            current_volume_ratio = df['volume_ratio'].iloc[idx]
            current_price_change = df['price_change'].iloc[idx]
            current_candle_body_ratio = df['candle_body_ratio'].iloc[idx]
            current_rsi = df['rsi'].iloc[idx]
            
            # 신호 강도 판별
            is_strong_signal = current_volume_ratio >= buy_conditions.get("volume_surge_ratio_strong", 2.5)
            rsi_limit = buy_conditions.get("strong_signal_rsi_limit", 75) if is_strong_signal else buy_conditions["rsi_upper_limit"]
            
            # 1. 강화된 거래량 급증 + 양봉 패턴
            volume_surge = current_volume_ratio >= buy_conditions["volume_surge_ratio"]
            positive_candle = current_price_change >= buy_conditions["min_price_increase"]
            strong_candle = current_candle_body_ratio >= buy_conditions["candle_body_ratio"]
            rsi_ok = current_rsi <= rsi_limit
            
            # 2. 연속 거래량 증가 패턴 체크 (추가)
            volume_momentum = False
            if idx >= 2:
                recent_volume_trend = df['volume_ratio'].iloc[idx-2:idx+1]
                volume_momentum = (recent_volume_trend.iloc[1] > recent_volume_trend.iloc[0] and 
                                recent_volume_trend.iloc[2] > recent_volume_trend.iloc[1])
            
            if volume_surge and positive_candle and strong_candle and rsi_ok:
                signal_strength = "Strong" if is_strong_signal else "Normal"
                return True, {
                    'pattern_type': f'장대양봉_대량거래_{signal_strength}',
                    'volume_surge_ratio': current_volume_ratio,
                    'price_change': current_price_change,
                    'candle_body_ratio': current_candle_body_ratio,
                    'rsi': current_rsi,
                    'signal_strength': signal_strength,
                    'volume_momentum': volume_momentum
                }
            
            # 3. 개선된 3일 연속 패턴
            if idx >= 2:
                day1_volume_surge = df['volume_ratio'].iloc[idx-2] >= buy_conditions["volume_surge_ratio"]
                day1_positive = df['price_change'].iloc[idx-2] > 0
                
                day2_volume_decrease = df['volume_ratio'].iloc[idx-1] < df['volume_ratio'].iloc[idx-2]
                
                day3_volume_increase = df['volume_ratio'].iloc[idx] > df['volume_ratio'].iloc[idx-1]
                day3_positive = df['price_change'].iloc[idx] > 0
                
                if (day1_volume_surge and day1_positive and day2_volume_decrease and 
                    day3_volume_increase and day3_positive and rsi_ok):
                    return True, {
                        'pattern_type': '3일_연속_매집_패턴_개선',
                        'volume_surge_ratio': current_volume_ratio,
                        'price_change': current_price_change,
                        'rsi': current_rsi,
                        'signal_strength': "Normal"
                    }
            
            return False, {}
            
        except Exception as e:
            logger.error(f"거래량 급증 패턴 감지 오류: {str(e)}")
            return False, {}

    def detect_pullback_opportunity(self, df, idx):
        """눌림목 매수 기회 감지"""
        try:
            if idx < 5:
                return False, {}
            
            buy_conditions = self.config["buy_conditions"]
            
            # 최근 5일 내 거래량 급증 확인
            recent_surge = False
            surge_idx = -1
            
            for i in range(1, 6):
                if idx - i >= 0 and df['volume_ratio'].iloc[idx - i] >= buy_conditions["volume_surge_ratio"]:
                    recent_surge = True
                    surge_idx = idx - i
                    break
            
            if not recent_surge:
                return False, {}
            
            # 급증 이후 거래량 감소 + 가격 조정 확인
            current_volume_ratio = df['volume_ratio'].iloc[idx]
            surge_volume_ratio = df['volume_ratio'].iloc[surge_idx]
            
            volume_decreased = current_volume_ratio <= surge_volume_ratio * buy_conditions["pullback_volume_decrease"]
            
            surge_price = df['close'].iloc[surge_idx]
            current_price = df['close'].iloc[idx]
            price_pullback = (current_price - surge_price) / surge_price * 100
            
            current_rsi = df['rsi'].iloc[idx]
            rsi_ok = current_rsi <= buy_conditions["rsi_upper_limit"]
            
            if volume_decreased and -10 <= price_pullback <= -2 and rsi_ok:
                return True, {
                    'pattern_type': '눌림목_매수_기회',
                    'surge_volume_ratio': surge_volume_ratio,
                    'current_volume_ratio': current_volume_ratio,
                    'price_pullback': price_pullback,
                    'days_since_surge': idx - surge_idx,
                    'rsi': current_rsi
                }
            
            return False, {}
            
        except Exception as e:
            logger.error(f"눌림목 기회 감지 오류: {str(e)}")
            return False, {}

    def detect_distribution_pattern(self, df, idx):
        """상투권 분배 패턴 감지"""
        try:
            if idx < 20:
                return False, {}
            
            sell_conditions = self.config["sell_conditions"]
            
            # 고점 구간 확인 (최근 20일 최고가 대비)
            recent_high = df['high'].iloc[max(0, idx-19):idx+1].max()
            current_price = df['close'].iloc[idx]
            high_ratio = current_price / recent_high
            
            if high_ratio < 0.9:  # 고점 대비 10% 이상 하락시 분배 패턴 아님
                return False, {}
            
            # 대량거래 + 장대음봉 체크
            current_volume_ratio = df['volume_ratio'].iloc[idx]
            price_change = df['price_change'].iloc[idx]
            candle_body_ratio = df['candle_body_ratio'].iloc[idx]
            
            # 위꼬리 긴 캔들 체크
            upper_shadow = (df['high'].iloc[idx] - max(df['open'].iloc[idx], df['close'].iloc[idx])) / (df['high'].iloc[idx] - df['low'].iloc[idx])
            
            volume_surge = current_volume_ratio >= sell_conditions["high_volume_surge"]
            negative_candle = price_change < 0 and candle_body_ratio >= sell_conditions["negative_candle_threshold"]
            long_upper_shadow = upper_shadow > 0.3
            
            if volume_surge and (negative_candle or long_upper_shadow):
                return True, {
                    'pattern_type': '상투권_분배_패턴',
                    'volume_surge_ratio': current_volume_ratio,
                    'price_change': price_change,
                    'upper_shadow_ratio': upper_shadow,
                    'high_ratio': high_ratio
                }
            
            return False, {}
            
        except Exception as e:
            logger.error(f"분배 패턴 감지 오류: {str(e)}")
            return False, {}

    def check_buy_conditions(self, stock_code, df, idx):
        """매수 조건 종합 체크"""
        try:
            # 현재 포지션 수 체크
            if len(self.positions) >= self.max_positions:
                return False, "최대 포지션 수 초과"
            
            # 이미 보유 중인지 체크
            if stock_code in self.positions:
                return False, "이미 보유 중"
            
            # 거래량 패턴 분석
            surge_detected, surge_info = self.detect_volume_surge_pattern(df, idx)
            pullback_detected, pullback_info = self.detect_pullback_opportunity(df, idx)
            
            if not (surge_detected or pullback_detected):
                return False, "거래량 패턴 미감지"
            
            # 매수 가격 및 수량 계산
            current_price = df['close'].iloc[idx]
            
            # 포지션 크기 = 총 자금 / 최대 포지션 수
            position_size = self.initial_capital / self.max_positions
            
            if self.current_cash < position_size:
                return False, f"잔고 부족 (필요: {position_size:,.0f}원, 보유: {self.current_cash:,.0f}원)"
            
            signal_type = "거래량_급증" if surge_detected else "눌림목_매수"
            signal_data = surge_info if surge_detected else pullback_info
            
            return True, {
                'signal_type': signal_type,
                'signal_data': signal_data,
                'position_size': position_size,
                'current_price': current_price
            }
            
        except Exception as e:
            logger.error(f"매수 조건 체크 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}"

    def check_sell_conditions(self, stock_code, position_info, df, idx):
        """매도 조건 종합 체크 (개선된 버전)"""
        try:
            sell_conditions = self.config["sell_conditions"]
            
            current_price = df['close'].iloc[idx]
            entry_price = position_info['entry_price']
            profit_rate = (current_price - entry_price) / entry_price * 100
            
            # 보유 기간 계산
            hold_days = idx - position_info['entry_idx']
            signal_strength = position_info.get('signal_data', {}).get('signal_strength', 'Normal')
            
            # 1. 강화된 손절선
            if profit_rate <= sell_conditions["stop_loss"]:
                return True, "손절선_도달", {
                    'sell_type': '손절매',
                    'profit_rate': profit_rate,
                    'reason': f'손절선 도달 ({profit_rate:.1f}%)'
                }
            
            # 2. 신호별 차별화된 목표 수익률
            if signal_strength == "Strong":
                target_profit = sell_conditions["profit_target_strong"]
            elif "눌림목" in position_info.get('signal_type', ''):
                target_profit = sell_conditions["profit_target_pullback"]
            else:
                target_profit = sell_conditions["profit_target_normal"]
                
            if profit_rate >= target_profit:
                return True, "목표수익_달성", {
                    'sell_type': '익절매',
                    'profit_rate': profit_rate,
                    'reason': f'목표 수익률 달성 ({profit_rate:.1f}% >= {target_profit}%)'
                }
            
            # 3. 빠른 수익실현 (단기 보유시)
            if hold_days <= 2 and profit_rate >= sell_conditions["quick_profit_target"]:
                return True, "빠른수익실현", {
                    'sell_type': '익절매',
                    'profit_rate': profit_rate,
                    'reason': f'빠른 수익실현 ({hold_days}일차, {profit_rate:.1f}%)'
                }
            
            # 4. 트레일링 스톱 (15% 이상 수익시)
            if profit_rate >= sell_conditions["trailing_stop_activation"]:
                # 최근 5일 최고가 대비 현재가 체크
                if idx >= 5:
                    recent_high = df['high'].iloc[idx-4:idx+1].max()
                    trailing_ratio = current_price / recent_high
                    
                    if trailing_ratio <= sell_conditions["trailing_stop_ratio"]:
                        return True, "트레일링스톱", {
                            'sell_type': '익절매',
                            'profit_rate': profit_rate,
                            'reason': f'트레일링 스톱 ({trailing_ratio:.2f} <= {sell_conditions["trailing_stop_ratio"]})'
                        }
            
            # 5. 분배 패턴 (기존과 동일하지만 조건 완화)
            distribution_detected, dist_info = self.detect_distribution_pattern(df, idx)
            if distribution_detected:
                return True, "분배패턴_감지", {
                    'sell_type': '기술적매도',
                    'profit_rate': profit_rate,
                    'reason': f"분배 패턴 감지: {dist_info.get('pattern_type', 'Unknown')}",
                    'pattern_info': dist_info
                }
            
            # 6. 개선된 거래량 감소 + 하락 조건 (최소 보유일 고려)
            min_hold_days = sell_conditions.get("min_hold_before_tech_sell", 3)
            volume_decrease_days = sell_conditions["volume_decrease_days"]
            
            if hold_days >= min_hold_days and idx >= volume_decrease_days:
                recent_volume_trend = df['volume_ratio'].iloc[idx-volume_decrease_days+1:idx+1].mean()
                recent_price_trend = df['price_change'].iloc[idx-volume_decrease_days+1:idx+1].mean()
                
                volume_decreasing = recent_volume_trend < 0.8  # 0.8배 이하로 감소
                price_declining = recent_price_trend < -1.0    # 1% 이상 하락
                
                # 수익 상황에 따라 다르게 적용
                if volume_decreasing and price_declining:
                    if profit_rate < 5:  # 수익이 적으면 빠르게 매도
                        return True, "거래량감소_하락지속", {
                            'sell_type': '기술적매도',
                            'profit_rate': profit_rate,
                            'reason': f'{volume_decrease_days}일간 거래량 감소 + 가격 하락 (보유 {hold_days}일)'
                        }
            
            # 7. RSI 과매수 (수익 상황에서만)
            if profit_rate > 10 and idx >= 14:  # 10% 이상 수익시에만
                current_rsi = df['rsi'].iloc[idx]
                if current_rsi >= sell_conditions["rsi_sell_threshold"]:
                    return True, "RSI_과매수", {
                        'sell_type': '기술적매도',
                        'profit_rate': profit_rate,
                        'reason': f'RSI 과매수 ({current_rsi:.1f}) + 수익 실현'
                    }
            
            return False, "매도 조건 미충족", {}
            
        except Exception as e:
            logger.error(f"매도 조건 체크 오류 ({stock_code}): {str(e)}")
            return False, f"분석 오류: {str(e)}", {}

    def execute_buy(self, stock_code, buy_info, df, idx, date):
        """매수 실행"""
        try:
            current_price = buy_info['current_price']
            position_size = buy_info['position_size']
            
            # 수수료 고려한 실제 매수 가능 금액
            available_amount = position_size / (1 + self.commission_rate)
            buy_amount = int(available_amount / current_price)
            
            if buy_amount <= 0:
                return False
            
            total_cost = buy_amount * current_price * (1 + self.commission_rate)
            
            if total_cost > self.current_cash:
                return False
            
            # 포지션 추가
            self.positions[stock_code] = {
                'amount': buy_amount,
                'entry_price': current_price,
                'entry_date': date,
                'entry_idx': idx,
                'signal_type': buy_info['signal_type'],
                'signal_data': buy_info['signal_data']
            }
            
            # 현금 차감
            self.current_cash -= total_cost
            
            # 거래 기록
            trade_record = {
                'date': date,
                'stock_code': stock_code,
                'type': 'BUY',
                'price': current_price,
                'amount': buy_amount,
                'total_amount': total_cost,
                'commission': total_cost - (buy_amount * current_price),
                'signal_type': buy_info['signal_type'],
                'cash_after': self.current_cash
            }
            self.trade_history.append(trade_record)
            
            logger.info(f"[{date}] 매수: {stock_code} {buy_amount:,}주 @ {current_price:,}원 (신호: {buy_info['signal_type']})")
            return True
            
        except Exception as e:
            logger.error(f"매수 실행 오류: {str(e)}")
            return False

    def execute_sell(self, stock_code, position_info, sell_info, df, idx, date):
        """매도 실행"""
        try:
            current_price = df['close'].iloc[idx]
            sell_amount = position_info['amount']
            
            # 매도 수익 계산 (수수료 차감)
            gross_proceeds = sell_amount * current_price
            commission = gross_proceeds * self.commission_rate
            net_proceeds = gross_proceeds - commission
            
            # 손익 계산
            entry_cost = position_info['amount'] * position_info['entry_price']
            profit = net_proceeds - entry_cost
            profit_rate = sell_info['profit_rate']
            
            # 현금 증가
            self.current_cash += net_proceeds
            
            # 보유 기간 계산
            hold_days = idx - position_info['entry_idx']
            
            # 거래 기록
            trade_record = {
                'date': date,
                'stock_code': stock_code,
                'type': 'SELL',
                'price': current_price,
                'amount': sell_amount,
                'total_amount': gross_proceeds,
                'commission': commission,
                'profit': profit,
                'profit_rate': profit_rate,
                'hold_days': hold_days,
                'sell_reason': sell_info['reason'],
                'entry_price': position_info['entry_price'],
                'entry_date': position_info['entry_date'],
                'cash_after': self.current_cash
            }
            self.trade_history.append(trade_record)
            
            # 포지션 제거
            del self.positions[stock_code]
            
            logger.info(f"[{date}] 매도: {stock_code} {sell_amount:,}주 @ {current_price:,}원 "
                       f"(수익률: {profit_rate:+.2f}%, 보유: {hold_days}일, 사유: {sell_info['reason']})")
            return True
            
        except Exception as e:
            logger.error(f"매도 실행 오류: {str(e)}")
            return False

    def calculate_portfolio_value(self, stock_data_dict, idx, date):
        """포트폴리오 가치 계산"""
        try:
            stock_value = 0
            
            for stock_code, position in self.positions.items():
                if stock_code in stock_data_dict:
                    df = stock_data_dict[stock_code]
                    if idx < len(df):
                        current_price = df['close'].iloc[idx]
                        stock_value += position['amount'] * current_price
            
            total_value = self.current_cash + stock_value
            
            self.daily_portfolio_value.append({
                'date': date,
                'cash': self.current_cash,
                'stock_value': stock_value,
                'total_value': total_value,
                'return_rate': (total_value - self.initial_capital) / self.initial_capital * 100
            })
            
            return total_value
            
        except Exception as e:
            logger.error(f"포트폴리오 가치 계산 오류: {str(e)}")
            return self.current_cash

    def run_backtest(self, stock_list, start_date=None, end_date=None):
        """백테스팅 실행"""
        try:
            logger.info(f"백테스팅 시작 - 대상 종목: {len(stock_list)}개")
            
            # 날짜 설정
            if end_date is None:
                end_date = datetime.now()
            if start_date is None:
                start_date = end_date - timedelta(days=365)
            
            # 모든 종목의 데이터 로드
            stock_data_dict = {}
            for stock_code in stock_list:
                logger.info(f"데이터 로딩: {stock_code}")
                df = self.get_historical_data(stock_code, 400)  # 여유분 포함
                if df is not None:
                    stock_data_dict[stock_code] = df
                time.sleep(0.1)  # API 호출 간격
            
            if not stock_data_dict:
                logger.error("사용 가능한 데이터가 없습니다.")
                return None
            
            # 백테스팅 기간 내의 모든 거래일 추출
            all_dates = set()
            for df in stock_data_dict.values():
                all_dates.update(df.index)
            
            trading_dates = sorted([d for d in all_dates 
                                  if start_date.strftime('%Y-%m-%d') <= d <= end_date.strftime('%Y-%m-%d')])
            
            logger.info(f"백테스팅 기간: {trading_dates[0]} ~ {trading_dates[-1]} ({len(trading_dates)}일)")
            
            # 일자별 시뮬레이션
            for date_idx, date in enumerate(trading_dates):
                try:
                    # 매도 체크 (보유 종목에 대해)
                    for stock_code in list(self.positions.keys()):
                        if stock_code in stock_data_dict:
                            df = stock_data_dict[stock_code]
                            if date in df.index:
                                idx = df.index.get_loc(date)
                                position_info = self.positions[stock_code]
                                
                                should_sell, sell_reason, sell_info = self.check_sell_conditions(
                                    stock_code, position_info, df, idx)
                                
                                if should_sell:
                                    self.execute_sell(stock_code, position_info, sell_info, df, idx, date)
                    
                    # 매수 체크 (모든 종목에 대해)
                    for stock_code, df in stock_data_dict.items():
                        if date in df.index and stock_code not in self.positions:
                            idx = df.index.get_loc(date)
                            
                            can_buy, buy_info = self.check_buy_conditions(stock_code, df, idx)
                            
                            if can_buy:
                                success = self.execute_buy(stock_code, buy_info, df, idx, date)
                                if success and len(self.positions) >= self.max_positions:
                                    break  # 최대 포지션 수 도달시 더 이상 매수 안함
                    
                    # 일일 포트폴리오 가치 계산
                    self.calculate_portfolio_value(stock_data_dict, 
                                                 stock_data_dict[list(stock_data_dict.keys())[0]].index.get_loc(date), 
                                                 date)
                    
                    # 진행률 표시 (10%씩)
                    if (date_idx + 1) % max(1, len(trading_dates) // 10) == 0:
                        progress = (date_idx + 1) / len(trading_dates) * 100
                        logger.info(f"진행률: {progress:.1f}% ({date})")
                
                except Exception as e:
                    logger.error(f"날짜 {date} 처리 중 오류: {str(e)}")
                    continue
            
            # 최종 포지션 정리 (마지막 날 시장가 매도)
            final_date = trading_dates[-1]
            for stock_code in list(self.positions.keys()):
                if stock_code in stock_data_dict:
                    df = stock_data_dict[stock_code]
                    if final_date in df.index:
                        idx = df.index.get_loc(final_date)
                        position_info = self.positions[stock_code]
                        
                        # 강제 매도
                        current_price = df['close'].iloc[idx]
                        profit_rate = (current_price - position_info['entry_price']) / position_info['entry_price'] * 100
                        
                        sell_info = {
                            'profit_rate': profit_rate,
                            'reason': '백테스팅_종료_강제매도'
                        }
                        
                        self.execute_sell(stock_code, position_info, sell_info, df, idx, final_date)
            
            logger.info("백테스팅 완료!")
            return self.generate_backtest_report()
            
        except Exception as e:
            logger.error(f"백테스팅 실행 오류: {str(e)}")
            return None

    def generate_backtest_report(self):
        """백테스팅 결과 리포트 생성"""
        try:
            if not self.daily_portfolio_value:
                return {"error": "백테스팅 데이터가 없습니다."}
            
            # 기본 통계
            final_value = self.daily_portfolio_value[-1]['total_value']
            total_return = (final_value - self.initial_capital) / self.initial_capital * 100
            
            # 거래 통계
            buy_trades = [t for t in self.trade_history if t['type'] == 'BUY']
            sell_trades = [t for t in self.trade_history if t['type'] == 'SELL']
            
            if sell_trades:
                winning_trades = [t for t in sell_trades if t['profit'] > 0]
                losing_trades = [t for t in sell_trades if t['profit'] <= 0]
                
                win_rate = len(winning_trades) / len(sell_trades) * 100
                avg_profit_rate = np.mean([t['profit_rate'] for t in sell_trades])
                avg_hold_days = np.mean([t['hold_days'] for t in sell_trades])
                
                best_trade = max(sell_trades, key=lambda x: x['profit_rate'])
                worst_trade = min(sell_trades, key=lambda x: x['profit_rate'])
                
                total_profit = sum([t['profit'] for t in sell_trades])
                total_commission = sum([t['commission'] for t in self.trade_history])
                
            else:
                win_rate = 0
                avg_profit_rate = 0
                avg_hold_days = 0
                best_trade = None
                worst_trade = None
                total_profit = 0
                total_commission = 0
            
            # 최대 낙폭 계산
            portfolio_values = [d['total_value'] for d in self.daily_portfolio_value]
            peak = self.initial_capital
            max_drawdown = 0
            
            for value in portfolio_values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            # 샤프 비율 계산 (일간 수익률 기준)
            daily_returns = []
            for i in range(1, len(self.daily_portfolio_value)):
                prev_value = self.daily_portfolio_value[i-1]['total_value']
                curr_value = self.daily_portfolio_value[i]['total_value']
                daily_return = (curr_value - prev_value) / prev_value
                daily_returns.append(daily_return)
            
            if daily_returns:
                avg_daily_return = np.mean(daily_returns)
                std_daily_return = np.std(daily_returns)
                sharpe_ratio = (avg_daily_return / std_daily_return * np.sqrt(252)) if std_daily_return > 0 else 0
            else:
                sharpe_ratio = 0
            
            # 월별 수익률 계산
            monthly_returns = {}
            for data in self.daily_portfolio_value:
                month_key = data['date'][:7]  # YYYY-MM
                monthly_returns[month_key] = data['return_rate']
            
            report = {
                "백테스팅_기간": {
                    "시작일": self.daily_portfolio_value[0]['date'],
                    "종료일": self.daily_portfolio_value[-1]['date'],
                    "총_거래일": len(self.daily_portfolio_value)
                },
                "수익성_지표": {
                    "초기자금": f"{self.initial_capital:,}원",
                    "최종자금": f"{final_value:,.0f}원",
                    "총_수익률": f"{total_return:+.2f}%",
                    "순_수익": f"{total_profit:+,.0f}원",
                    "총_수수료": f"{total_commission:,.0f}원"
                },
                "거래_통계": {
                    "총_매수_횟수": len(buy_trades),
                    "총_매도_횟수": len(sell_trades),
                    "승률": f"{win_rate:.1f}%",
                    "평균_수익률": f"{avg_profit_rate:+.2f}%",
                    "평균_보유기간": f"{avg_hold_days:.1f}일"
                },
                "리스크_지표": {
                    "최대_낙폭": f"{max_drawdown:.2f}%",
                    "샤프_비율": f"{sharpe_ratio:.3f}",
                    "변동성": f"{std_daily_return * np.sqrt(252) * 100:.2f}%" if 'std_daily_return' in locals() else "0.00%"
                },
                "베스트_거래": {
                    "종목": best_trade['stock_code'] if best_trade else "없음",
                    "수익률": f"{best_trade['profit_rate']:+.2f}%" if best_trade else "0.00%",
                    "수익금액": f"{best_trade['profit']:+,.0f}원" if best_trade else "0원",
                    "보유기간": f"{best_trade['hold_days']}일" if best_trade else "0일"
                } if best_trade else {"정보": "매도 거래 없음"},
                "워스트_거래": {
                    "종목": worst_trade['stock_code'] if worst_trade else "없음",
                    "수익률": f"{worst_trade['profit_rate']:+.2f}%" if worst_trade else "0.00%",
                    "손실금액": f"{worst_trade['profit']:+,.0f}원" if worst_trade else "0원",
                    "보유기간": f"{worst_trade['hold_days']}일" if worst_trade else "0일"
                } if worst_trade else {"정보": "매도 거래 없음"},
                "월별_수익률": monthly_returns,
                "거래_상세": {
                    "매수_신호별_통계": self._analyze_buy_signals(),
                    "매도_사유별_통계": self._analyze_sell_reasons()
                }
            }
            
            return report
            
        except Exception as e:
            logger.error(f"리포트 생성 오류: {str(e)}")
            return {"error": f"리포트 생성 실패: {str(e)}"}

    def _analyze_buy_signals(self):
        """매수 신호별 통계 분석"""
        try:
            buy_signals = {}
            sell_trades = [t for t in self.trade_history if t['type'] == 'SELL']
            
            for trade in sell_trades:
                # 매수 거래 찾기
                buy_trade = None
                for bt in self.trade_history:
                    if (bt['type'] == 'BUY' and bt['stock_code'] == trade['stock_code'] and 
                        bt['date'] == trade['entry_date']):
                        buy_trade = bt
                        break
                
                if buy_trade:
                    signal_type = buy_trade.get('signal_type', 'Unknown')
                    
                    if signal_type not in buy_signals:
                        buy_signals[signal_type] = {
                            'count': 0,
                            'winning_count': 0,
                            'total_profit': 0,
                            'avg_profit_rate': 0,
                            'avg_hold_days': 0
                        }
                    
                    buy_signals[signal_type]['count'] += 1
                    if trade['profit'] > 0:
                        buy_signals[signal_type]['winning_count'] += 1
                    buy_signals[signal_type]['total_profit'] += trade['profit']
            
            # 평균값 계산
            for signal_type in buy_signals:
                stats = buy_signals[signal_type]
                if stats['count'] > 0:
                    stats['win_rate'] = f"{stats['winning_count'] / stats['count'] * 100:.1f}%"
                    
                    # 해당 신호 타입의 거래들로 평균 계산
                    signal_trades = []
                    for trade in sell_trades:
                        buy_trade = None
                        for bt in self.trade_history:
                            if (bt['type'] == 'BUY' and bt['stock_code'] == trade['stock_code'] and 
                                bt['date'] == trade['entry_date']):
                                buy_trade = bt
                                break
                        
                        if buy_trade and buy_trade.get('signal_type') == signal_type:
                            signal_trades.append(trade)
                    
                    if signal_trades:
                        stats['avg_profit_rate'] = f"{np.mean([t['profit_rate'] for t in signal_trades]):+.2f}%"
                        stats['avg_hold_days'] = f"{np.mean([t['hold_days'] for t in signal_trades]):.1f}일"
                    
                    # 정리를 위해 불필요한 키 제거
                    del stats['winning_count']
            
            return buy_signals
            
        except Exception as e:
            logger.error(f"매수 신호 분석 오류: {str(e)}")
            return {}

    def _analyze_sell_reasons(self):
        """매도 사유별 통계 분석"""
        try:
            sell_reasons = {}
            sell_trades = [t for t in self.trade_history if t['type'] == 'SELL']
            
            for trade in sell_trades:
                reason = trade.get('sell_reason', 'Unknown')
                
                if reason not in sell_reasons:
                    sell_reasons[reason] = {
                        'count': 0,
                        'total_profit': 0,
                        'avg_profit_rate': 0,
                        'avg_hold_days': 0
                    }
                
                sell_reasons[reason]['count'] += 1
                sell_reasons[reason]['total_profit'] += trade['profit']
            
            # 평균값 계산
            for reason in sell_reasons:
                reason_trades = [t for t in sell_trades if t.get('sell_reason') == reason]
                
                if reason_trades:
                    sell_reasons[reason]['avg_profit_rate'] = f"{np.mean([t['profit_rate'] for t in reason_trades]):+.2f}%"
                    sell_reasons[reason]['avg_hold_days'] = f"{np.mean([t['hold_days'] for t in reason_trades]):.1f}일"
                    sell_reasons[reason]['total_profit'] = f"{sell_reasons[reason]['total_profit']:+,.0f}원"
            
            return sell_reasons
            
        except Exception as e:
            logger.error(f"매도 사유 분석 오류: {str(e)}")
            return {}

    def save_detailed_results(self, filename="backtest_results.json"):
        """상세 결과를 JSON 파일로 저장"""
        try:
            detailed_results = {
                "config": self.config,
                "initial_capital": self.initial_capital,
                "max_positions": self.max_positions,
                "commission_rate": self.commission_rate,
                "trade_history": self.trade_history,
                "daily_portfolio_value": self.daily_portfolio_value,
                "final_positions": self.positions
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(detailed_results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"상세 결과 저장 완료: {filename}")
            
        except Exception as e:
            logger.error(f"결과 저장 오류: {str(e)}")

################################### 실행 함수 ##################################

def run_volume_backtest(stock_list, initial_capital=5000000, max_positions=5, 
                       start_date=None, end_date=None):
    """
    거래량 기반 백테스팅 실행
    
    Args:
        stock_list (list): 백테스팅 대상 종목 리스트 ['005930', '000660', ...]
        initial_capital (int): 초기 투자금액
        max_positions (int): 최대 동시 보유 종목 수
        start_date (str): 백테스팅 시작일 (YYYY-MM-DD 형식, 예: "2023-01-01")
        end_date (str): 백테스팅 종료일 (YYYY-MM-DD 형식, 예: "2024-12-31")
    
    Returns:
        dict: 백테스팅 결과 리포트
    """
    
    logger.info("=" * 60)
    logger.info("거래량 기반 자동매매 백테스팅 시작")
    logger.info("=" * 60)
    
    # 백테스팅 엔진 생성
    engine = VolumeBacktestingEngine(
        initial_capital=initial_capital,
        max_positions=max_positions,
        commission_rate=0.00015  # 한국 주식 수수료 0.015%
    )
    
    # 날짜 변환
    start_datetime = None
    end_datetime = None
    
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            logger.info(f"백테스팅 시작일: {start_date}")
        except ValueError:
            logger.error(f"잘못된 시작일 형식: {start_date} (YYYY-MM-DD 형식으로 입력하세요)")
            return None
    
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            logger.info(f"백테스팅 종료일: {end_date}")
        except ValueError:
            logger.error(f"잘못된 종료일 형식: {end_date} (YYYY-MM-DD 형식으로 입력하세요)")
            return None
    
    # 백테스팅 실행
    report = engine.run_backtest(stock_list, start_datetime, end_datetime)
    
    if report:
        # 결과 출력 (기존 코드와 동일)
        print("\n" + "=" * 60)
        print("📊 백테스팅 결과 리포트")
        print("=" * 60)
        
        # 기간 정보
        period_info = report["백테스팅_기간"]
        print(f"\n📅 백테스팅 기간:")
        print(f"   시작일: {period_info['시작일']}")
        print(f"   종료일: {period_info['종료일']}")
        print(f"   총 거래일: {period_info['총_거래일']}일")
        
        # 수익성 지표
        profit_info = report["수익성_지표"]
        print(f"\n💰 수익성 지표:")
        print(f"   초기자금: {profit_info['초기자금']}")
        print(f"   최종자금: {profit_info['최종자금']}")
        print(f"   총 수익률: {profit_info['총_수익률']}")
        print(f"   순 수익: {profit_info['순_수익']}")
        print(f"   총 수수료: {profit_info['총_수수료']}")
        
        # 거래 통계
        trade_info = report["거래_통계"]
        print(f"\n📈 거래 통계:")
        print(f"   총 매수 횟수: {trade_info['총_매수_횟수']}회")
        print(f"   총 매도 횟수: {trade_info['총_매도_횟수']}회")
        print(f"   승률: {trade_info['승률']}")
        print(f"   평균 수익률: {trade_info['평균_수익률']}")
        print(f"   평균 보유기간: {trade_info['평균_보유기간']}")
        
        # 리스크 지표
        risk_info = report["리스크_지표"]
        print(f"\n⚠️ 리스크 지표:")
        print(f"   최대 낙폭: {risk_info['최대_낙폭']}")
        print(f"   샤프 비율: {risk_info['샤프_비율']}")
        print(f"   변동성: {risk_info['변동성']}")
        
        # 베스트/워스트 거래
        if "정보" not in report["베스트_거래"]:
            best_trade = report["베스트_거래"]
            print(f"\n🏆 베스트 거래:")
            print(f"   종목: {best_trade['종목']}")
            print(f"   수익률: {best_trade['수익률']}")
            print(f"   수익금액: {best_trade['수익금액']}")
            print(f"   보유기간: {best_trade['보유기간']}")
        
        if "정보" not in report["워스트_거래"]:
            worst_trade = report["워스트_거래"]
            print(f"\n💸 워스트 거래:")
            print(f"   종목: {worst_trade['종목']}")
            print(f"   수익률: {worst_trade['수익률']}")
            print(f"   손실금액: {worst_trade['손실금액']}")
            print(f"   보유기간: {worst_trade['보유기간']}")
        
        # 매수 신호별 통계
        buy_signals = report["거래_상세"]["매수_신호별_통계"]
        if buy_signals:
            print(f"\n🎯 매수 신호별 통계:")
            for signal_type, stats in buy_signals.items():
                print(f"   {signal_type}:")
                print(f"     거래 횟수: {stats['count']}회")
                print(f"     승률: {stats['win_rate']}")
                print(f"     평균 수익률: {stats['avg_profit_rate']}")
                print(f"     평균 보유기간: {stats['avg_hold_days']}")
        
        # 매도 사유별 통계
        sell_reasons = report["거래_상세"]["매도_사유별_통계"]
        if sell_reasons:
            print(f"\n📉 매도 사유별 통계:")
            for reason, stats in sell_reasons.items():
                print(f"   {reason}:")
                print(f"     거래 횟수: {stats['count']}회")
                print(f"     평균 수익률: {stats['avg_profit_rate']}")
                print(f"     총 손익: {stats['total_profit']}")
        
        # 상세 결과 저장
        engine.save_detailed_results("volume_backtest_details.json")
        
        print("\n" + "=" * 60)
        print("백테스팅 완료! 상세 결과는 'volume_backtest_details.json' 파일에 저장되었습니다.")
        print("=" * 60)
        
        return report
    
    else:
        logger.error("백테스팅 실행 실패")
        return None

################################### 사용 예시 ##################################

if __name__ == "__main__":
    # API 초기화
    try:
        Common.SetChangeMode("REAL")  # 실시간 데이터 조회 모드로 설정
        logger.info("API 초기화 완료")
    except Exception as e:
        logger.error(f"API 초기화 실패: {str(e)}")
        print("myStockInfo.yaml 파일을 확인해주세요.")
        exit(1)
    
    # 백테스팅 대상 종목 리스트 (예시)
    test_stocks = [
        "272210",  # 한화시스템
        "042660",  # 한화오션
        "017960",  # 한국카본
        "007660",  # 이수페타시스
        "034020"   # 두산에너빌리티
    ]
    
    print("백테스팅할 종목 리스트:")
    for i, stock_code in enumerate(test_stocks, 1):
        print(f"{i:2d}. {stock_code}")
    
    # 백테스팅 실행
    try:
        result = run_volume_backtest(
            stock_list=test_stocks,
            initial_capital=5000000,
            max_positions=5,
            start_date="2025-03-10",  # 시작일 설정
            end_date="2025-08-18"     # 종료일 설정
        )
        
        if result:
            print("\n백테스팅이 성공적으로 완료되었습니다!")
        else:
            print("\n백테스팅 실행 중 오류가 발생했습니다.")
            
    except Exception as e:
        logger.error(f"백테스팅 실행 오류: {str(e)}")
        print(f"\n오류 발생: {str(e)}")
        print("myStockInfo.yaml 파일 설정과 API 연결을 확인해주세요.")