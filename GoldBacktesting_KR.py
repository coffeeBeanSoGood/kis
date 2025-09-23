#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🥇 금투자 백테스팅 시스템 (GoldBacktesting_KR.py)
- 스마트 골드 트레이딩 봇의 실제 로직을 과거 데이터로 검증
- 5차수 분할매매 전략 성과 분석
- 다양한 시나리오 테스트 및 최적화
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import json
import os
import warnings
warnings.filterwarnings('ignore')

# 기존 모듈 임포트
import KIS_Common as Common
import KIS_API_Helper_KR as KisKR
from SmartGoldTradingBot_KR import SmartGoldTrading, GoldTradingConfig

# 한글 폰트 설정
plt.rcParams['font.family'] = ['Malgun Gothic', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

################################### 📊 백테스팅 엔진 클래스 ##################################

class GoldBacktestingEngine:
    def __init__(self, config_path=None):
        """백테스팅 엔진 초기화"""
        self.config = GoldTradingConfig()
        if config_path:
            self.config.config_path = config_path
            self.config.load_config()
        
        # 백테스팅 전용 설정
        self.commission_rate = self.config.config.get('commission_rate', 0.00015)
        self.slippage_rate = 0.001  # 슬리피지 0.1%
        
        # 결과 저장용
        self.backtest_results = {}
        self.trade_history = []
        self.daily_portfolio = []
        
        print("🥇 금투자 백테스팅 엔진 초기화 완료")

    def load_historical_data(self, product_codes, start_date, end_date):
        """과거 데이터 로드"""
        print(f"📈 과거 데이터 로딩: {start_date} ~ {end_date}")
        
        historical_data = {}
        
        for product_code in product_codes:
            try:
                print(f"   📊 {product_code} 데이터 로딩...")
                
                # 실제 차트 데이터 조회 (더 긴 기간)
                df = Common.GetOhlcv("KR", product_code, 1000)
                
                if df is None or len(df) == 0:
                    print(f"   ❌ {product_code} 데이터 없음")
                    continue
                
                # 날짜 범위 필터링
                df.index = pd.to_datetime(df.index)
                mask = (df.index >= start_date) & (df.index <= end_date)
                df = df[mask]
                
                if len(df) < 50:
                    print(f"   ⚠️ {product_code} 데이터 부족 ({len(df)}일)")
                    continue
                
                # 기술적 지표 계산
                df = self.calculate_technical_indicators(df)
                
                historical_data[product_code] = df
                print(f"   ✅ {product_code} 데이터 로드 완료 ({len(df)}일)")
                
            except Exception as e:
                print(f"   ❌ {product_code} 데이터 로딩 실패: {str(e)}")
        
        return historical_data

    def calculate_technical_indicators(self, df):
        """기술적 지표 계산 (실제 봇과 동일)"""
        # 이동평균선
        df['ma_10'] = df['close'].rolling(window=10).mean()
        df['ma_50'] = df['close'].rolling(window=50).mean()
        df['ma_200'] = df['close'].rolling(window=200).mean()
        
        # RSI (21일)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=21).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=21).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR (20일)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=20).mean()
        
        # 52주 고저점
        df['high_52w'] = df['high'].rolling(252).max()
        df['low_52w'] = df['low'].rolling(252).min()
        
        # 트렌드 스코어
        df['trend_score'] = 0
        current_price = df['close']
        
        for i in range(len(df)):
            if i < 200:  # 데이터 부족시 건너뛰기
                continue
                
            price = current_price.iloc[i]
            ma_10 = df['ma_10'].iloc[i]
            ma_50 = df['ma_50'].iloc[i]
            ma_200 = df['ma_200'].iloc[i]
            
            if pd.isna(ma_10) or pd.isna(ma_50) or pd.isna(ma_200):
                continue
                
            if price > ma_10 > ma_50 > ma_200:
                df.loc[df.index[i], 'trend_score'] = 3
            elif price > ma_10 > ma_50:
                df.loc[df.index[i], 'trend_score'] = 2
            elif price > ma_10:
                df.loc[df.index[i], 'trend_score'] = 1
            elif price < ma_10 < ma_50 < ma_200:
                df.loc[df.index[i], 'trend_score'] = -3
            elif price < ma_10 < ma_50:
                df.loc[df.index[i], 'trend_score'] = -2
            elif price < ma_10:
                df.loc[df.index[i], 'trend_score'] = -1
        
        return df

    def simulate_market_conditions(self, current_date, df):
        """시장 상황 시뮬레이션"""
        try:
            # 과거 시점의 시장 상황을 시뮬레이션
            conditions = {
                'dollar_strength': 'neutral',
                'inflation_pressure': 'low', 
                'geopolitical_risk': 'low',
                'stock_market_stress': 'low',
                'safe_haven_demand': 'normal',
                'overall_signal': 'hold'
            }
            
            # 변동성 기반 시장 스트레스 계산
            if len(df) >= 20:
                recent_data = df.tail(20)
                volatility = recent_data['close'].pct_change().std() * 100
                
                if volatility > 3.0:
                    conditions['stock_market_stress'] = 'high'
                    conditions['safe_haven_demand'] = 'high'
                elif volatility > 2.0:
                    conditions['stock_market_stress'] = 'moderate'
                    conditions['safe_haven_demand'] = 'moderate'
            
            # 달러 강도 시뮬레이션 (단순화)
            import random
            random.seed(int(current_date.timestamp()))  # 일관된 결과를 위한 시드
            dollar_rand = random.random()
            
            if dollar_rand > 0.7:
                conditions['dollar_strength'] = 'strong'
            elif dollar_rand < 0.3:
                conditions['dollar_strength'] = 'weak'
            
            # 종합 신호 결정
            buy_signals = 0
            if conditions['dollar_strength'] == 'weak':
                buy_signals += 2
            if conditions['safe_haven_demand'] == 'high':
                buy_signals += 2
            if conditions['stock_market_stress'] == 'high':
                buy_signals += 1
            
            if buy_signals >= 3:
                conditions['overall_signal'] = 'strong_buy'
            elif buy_signals >= 2:
                conditions['overall_signal'] = 'buy'
            elif buy_signals <= -2:
                conditions['overall_signal'] = 'sell'
            
            return conditions
            
        except Exception as e:
            print(f"❌ 시장 상황 시뮬레이션 실패: {str(e)}")
            return {'overall_signal': 'hold'}

    def simulate_buy_decision(self, product_code, position_num, current_data, 
                            magic_data_list, market_conditions):
        """매수 결정 시뮬레이션 (실제 봇 로직 활용)"""
        try:
            current_price = current_data['close']
            rsi = current_data.get('rsi', 50)
            trend_score = current_data.get('trend_score', 0)
            
            if pd.isna(rsi):
                rsi = 50
            if pd.isna(trend_score):
                trend_score = 0
            
            # 1차수 매수 조건
            if position_num == 1:
                overall_signal = market_conditions.get('overall_signal', 'hold')
                if overall_signal in ['strong_buy', 'buy']:
                    return True, f"1차 진입: {overall_signal} 신호"
                elif rsi < 40 and trend_score >= 0:
                    return True, "1차 진입: RSI 과매도 + 중립 이상 트렌드"
                elif trend_score >= 2:
                    return True, "1차 진입: 강한 상승 트렌드"
                else:
                    return False, "1차 진입 조건 미충족"
            
            # 2차수 이상: 하락률 검증
            if position_num > len(magic_data_list) or position_num < 2:
                return False, "잘못된 포지션 번호"
            
            previous_position = magic_data_list[position_num - 2]
            if not previous_position['IsBuy']:
                return False, f"이전 {position_num-1}차수 미보유"
            
            # 동적 하락률 계산
            required_drop, _ = self.calculate_drop_requirement(
                position_num, market_conditions
            )
            
            previous_price = previous_position['EntryPrice']
            current_drop = (previous_price - current_price) / previous_price
            
            if current_drop < required_drop:
                return False, f"{position_num}차 하락률 부족 ({current_drop*100:.1f}% < {required_drop*100:.1f}%)"
            
            # 추가 매수 조건
            buy_reasons = []
            
            if rsi < 25:
                buy_reasons.append(f"RSI 과매도({rsi:.1f})")
            
            if market_conditions.get('safe_haven_demand') == 'high':
                buy_reasons.append("안전자산 수요 급증")
            
            if market_conditions.get('dollar_strength') == 'weak':
                buy_reasons.append("달러 약세")
            
            if buy_reasons:
                reason_text = f"{position_num}차 매수: {', '.join(buy_reasons)}"
                return True, reason_text
            
            return False, f"{position_num}차 추가 조건 미충족"
            
        except Exception as e:
            return False, f"매수 조건 판단 오류: {str(e)}"

    def simulate_sell_decision(self, magic_data, current_data, market_conditions):
        """매도 결정 시뮬레이션"""
        try:
            if not magic_data['IsBuy'] or magic_data['CurrentAmt'] <= 0:
                return False, 0, "보유 포지션 없음"
            
            entry_price = magic_data['EntryPrice']
            current_price = current_data['close']
            current_return = (current_price - entry_price) / entry_price
            position_num = magic_data['Number']
            
            # 손절 조건
            stop_thresholds = {1: -0.20, 2: -0.25, 3: -0.30, 4: -0.30, 5: -0.30}
            stop_threshold = stop_thresholds.get(position_num, -0.30)
            
            # 시장 상황별 손절선 조정
            dollar_strength = market_conditions.get('dollar_strength', 'neutral')
            if dollar_strength == 'strong':
                stop_threshold -= 0.05  # 손절선 완화
            elif dollar_strength == 'weak':
                stop_threshold += 0.03  # 손절선 강화
            
            if current_return <= stop_threshold:
                return True, 1.0, f"손절 실행 ({current_return*100:.1f}% <= {stop_threshold*100:.1f}%)"
            
            # 익절 조건
            profit_targets = {1: 0.25, 2: 0.30, 3: 0.35, 4: 0.35, 5: 0.35}
            profit_target = profit_targets.get(position_num, 0.35)
            
            if current_return >= profit_target:
                return True, 0.5, f"부분 익절 ({current_return*100:.1f}% >= {profit_target*100:.1f}%)"
            
            # 트렌드 반전 매도
            rsi = current_data.get('rsi', 50)
            trend_score = current_data.get('trend_score', 0)
            
            if not pd.isna(rsi) and not pd.isna(trend_score):
                if rsi > 80 and trend_score < 0:
                    return True, 0.3, f"트렌드 반전 부분매도 (RSI:{rsi:.1f}, 트렌드:{trend_score})"
                
                if trend_score <= -2 and current_return > 0.1:
                    return True, 0.5, "이동평균선 하향돌파 + 수익구간"
            
            return False, 0, "매도 조건 미충족"
            
        except Exception as e:
            return False, 0, f"매도 조건 판단 오류: {str(e)}"

    def calculate_drop_requirement(self, position_num, market_conditions):
        """동적 하락률 계산 (실제 봇 로직)"""
        base_drops = {2: 0.06, 3: 0.08, 4: 0.10, 5: 0.12}
        base_drop = base_drops.get(position_num, 0.08)
        final_drop = base_drop
        
        # 시장 상황별 조정
        dollar_strength = market_conditions.get('dollar_strength', 'neutral')
        if dollar_strength == 'strong':
            final_drop -= 0.02
        elif dollar_strength == 'weak':
            final_drop += 0.01
        
        safe_haven_demand = market_conditions.get('safe_haven_demand', 'normal')
        if safe_haven_demand == 'high':
            final_drop -= 0.02
        
        # 안전 범위 제한
        min_drop = base_drop * 0.3
        max_drop = base_drop * 2.0
        final_drop = max(min_drop, min(final_drop, max_drop))
        
        return final_drop, []

    def run_backtest(self, product_codes, start_date, end_date, initial_budget=5000000):
        """백테스팅 실행"""
        print(f"\n🚀 백테스팅 시작: {start_date} ~ {end_date}")
        print(f"💰 초기 자본: {initial_budget:,.0f}원")
        print(f"📊 대상 종목: {product_codes}")
        
        # 과거 데이터 로드
        historical_data = self.load_historical_data(product_codes, start_date, end_date)
        
        if not historical_data:
            print("❌ 사용 가능한 과거 데이터가 없습니다.")
            return None
        
        # 백테스팅 초기화
        portfolio = {
            'cash': initial_budget,
            'total_value': initial_budget,
            'positions': {}
        }
        
        # 각 종목별 매매 데이터 초기화
        for product_code in product_codes:
            portfolio['positions'][product_code] = {
                'magic_data_list': [],
                'realized_pnl': 0
            }
            
            # 5차수 초기화
            for i in range(5):
                portfolio['positions'][product_code]['magic_data_list'].append({
                    'Number': i + 1,
                    'EntryPrice': 0,
                    'EntryAmt': 0,
                    'CurrentAmt': 0,
                    'EntryDate': '',
                    'IsBuy': False,
                    'PositionRatio': [0.15, 0.20, 0.25, 0.20, 0.20][i]
                })
        
        # 공통 날짜 인덱스 생성
        all_dates = set()
        for df in historical_data.values():
            all_dates.update(df.index)
        
        trading_dates = sorted(list(all_dates))
        print(f"📅 백테스팅 기간: {len(trading_dates)}일")
        
        # 일별 백테스팅 실행
        for i, current_date in enumerate(trading_dates):
            try:
                # 진행률 표시
                if i % 50 == 0 or i == len(trading_dates) - 1:
                    progress = (i + 1) / len(trading_dates) * 100
                    print(f"   🔄 진행률: {progress:.1f}% ({current_date.strftime('%Y-%m-%d')})")
                
                # 해당 날짜의 시장 상황 분석
                market_conditions = self.simulate_market_conditions(current_date, None)
                
                # 각 종목별 매매 처리
                for product_code in product_codes:
                    if current_date not in historical_data[product_code].index:
                        continue
                    
                    current_data = historical_data[product_code].loc[current_date]
                    magic_data_list = portfolio['positions'][product_code]['magic_data_list']
                    
                    # 매도 처리 (우선)
                    for magic_data in magic_data_list:
                        if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                            should_sell, sell_ratio, sell_reason = self.simulate_sell_decision(
                                magic_data, current_data, market_conditions
                            )
                            
                            if should_sell and sell_ratio > 0:
                                self.execute_backtest_sell(
                                    portfolio, product_code, magic_data, 
                                    current_data, sell_ratio, sell_reason, current_date
                                )
                    
                    # 매수 처리
                    for position_num in range(1, 6):
                        magic_data = magic_data_list[position_num - 1]
                        
                        if not magic_data['IsBuy']:
                            should_buy, buy_reason = self.simulate_buy_decision(
                                product_code, position_num, current_data,
                                magic_data_list, market_conditions
                            )
                            
                            if should_buy:
                                self.execute_backtest_buy(
                                    portfolio, product_code, magic_data,
                                    current_data, buy_reason, current_date
                                )
                                break  # 한 번에 하나씩만 매수
                
                # 일일 포트폴리오 가치 계산
                daily_value = self.calculate_portfolio_value(
                    portfolio, historical_data, current_date
                )
                
                self.daily_portfolio.append({
                    'date': current_date,
                    'total_value': daily_value,
                    'cash': portfolio['cash'],
                    'return_pct': (daily_value - initial_budget) / initial_budget * 100
                })
                
            except Exception as e:
                print(f"❌ {current_date} 처리 중 오류: {str(e)}")
        
        # 백테스팅 결과 분석
        results = self.analyze_backtest_results(portfolio, initial_budget, trading_dates)
        self.backtest_results = results
        
        print(f"\n✅ 백테스팅 완료!")
        print(f"📊 총 수익률: {results['total_return_pct']:.2f}%")
        print(f"📈 연환산 수익률: {results['annual_return_pct']:.2f}%")
        print(f"📉 최대 낙폭: {results['max_drawdown_pct']:.2f}%")
        print(f"💹 총 매매 횟수: {len(self.trade_history)}회")
        
        return results

    def execute_backtest_buy(self, portfolio, product_code, magic_data, 
                           current_data, reason, current_date):
        """백테스트 매수 실행"""
        try:
            current_price = current_data['close']
            position_ratio = magic_data['PositionRatio']
            
            # 종목별 배정 예산 계산 (균등 분할)
            gold_products = self.config.config.get('gold_products', {})
            num_products = len([p for p in gold_products.values() if p.get('recommended', False)])
            if num_products == 0:
                num_products = 1
            
            product_budget = portfolio['cash'] * (1.0 / num_products)
            invest_amount = product_budget * position_ratio
            
            # 매수 가능 수량 계산
            buy_amount = int(invest_amount / current_price)
            actual_cost = buy_amount * current_price
            
            # 수수료 계산
            commission = actual_cost * self.commission_rate
            slippage = actual_cost * self.slippage_rate
            total_cost = actual_cost + commission + slippage
            
            if buy_amount > 0 and portfolio['cash'] >= total_cost:
                # 매수 실행
                magic_data['IsBuy'] = True
                magic_data['EntryPrice'] = current_price
                magic_data['EntryAmt'] = buy_amount
                magic_data['CurrentAmt'] = buy_amount
                magic_data['EntryDate'] = current_date.strftime('%Y-%m-%d')
                
                portfolio['cash'] -= total_cost
                
                # 거래 이력 저장
                self.trade_history.append({
                    'date': current_date,
                    'product_code': product_code,
                    'action': 'BUY',
                    'position': magic_data['Number'],
                    'price': current_price,
                    'amount': buy_amount,
                    'cost': actual_cost,
                    'commission': commission,
                    'slippage': slippage,
                    'reason': reason
                })
                
                return True
            
        except Exception as e:
            print(f"❌ 백테스트 매수 실행 오류: {str(e)}")
        
        return False

    def execute_backtest_sell(self, portfolio, product_code, magic_data,
                            current_data, sell_ratio, reason, current_date):
        """백테스트 매도 실행"""
        try:
            current_price = current_data['close']
            sell_amount = int(magic_data['CurrentAmt'] * sell_ratio)
            
            if sell_amount > 0:
                # 매도 수익 계산
                revenue = sell_amount * current_price
                commission = revenue * self.commission_rate
                slippage = revenue * self.slippage_rate
                net_revenue = revenue - commission - slippage
                
                # 손익 계산
                entry_cost = sell_amount * magic_data['EntryPrice']
                profit = net_revenue - entry_cost
                return_pct = profit / entry_cost * 100
                
                # 포지션 업데이트
                magic_data['CurrentAmt'] -= sell_amount
                if magic_data['CurrentAmt'] <= 0:
                    magic_data['IsBuy'] = False
                    magic_data['CurrentAmt'] = 0
                
                portfolio['cash'] += net_revenue
                portfolio['positions'][product_code]['realized_pnl'] += profit
                
                # 거래 이력 저장
                self.trade_history.append({
                    'date': current_date,
                    'product_code': product_code,
                    'action': 'SELL',
                    'position': magic_data['Number'],
                    'price': current_price,
                    'amount': sell_amount,
                    'revenue': revenue,
                    'commission': commission,
                    'slippage': slippage,
                    'profit': profit,
                    'return_pct': return_pct,
                    'reason': reason
                })
                
                return True
                
        except Exception as e:
            print(f"❌ 백테스트 매도 실행 오류: {str(e)}")
        
        return False

    def calculate_portfolio_value(self, portfolio, historical_data, current_date):
        """포트폴리오 총 가치 계산"""
        total_value = portfolio['cash']
        
        try:
            for product_code, position_data in portfolio['positions'].items():
                if current_date not in historical_data[product_code].index:
                    continue
                
                current_price = historical_data[product_code].loc[current_date, 'close']
                
                for magic_data in position_data['magic_data_list']:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        position_value = magic_data['CurrentAmt'] * current_price
                        total_value += position_value
        
        except Exception as e:
            print(f"❌ 포트폴리오 가치 계산 오류: {str(e)}")
        
        return total_value

    def analyze_backtest_results(self, portfolio, initial_budget, trading_dates):
        """백테스팅 결과 분석"""
        try:
            if not self.daily_portfolio:
                return {}
            
            # 기본 통계
            final_value = self.daily_portfolio[-1]['total_value']
            total_return_pct = (final_value - initial_budget) / initial_budget * 100
            
            # 기간 계산
            start_date = trading_dates[0]
            end_date = trading_dates[-1]
            total_days = (end_date - start_date).days
            years = total_days / 365.25
            
            # 연환산 수익률
            annual_return_pct = ((final_value / initial_budget) ** (1/years) - 1) * 100 if years > 0 else 0
            
            # 일별 수익률 계산
            daily_returns = []
            values = [d['total_value'] for d in self.daily_portfolio]
            
            for i in range(1, len(values)):
                daily_return = (values[i] - values[i-1]) / values[i-1]
                daily_returns.append(daily_return)
            
            daily_returns = np.array(daily_returns)
            
            # 최대 낙폭 (MDD) 계산
            peak = initial_budget
            max_drawdown = 0
            
            for value in values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            max_drawdown_pct = max_drawdown * 100
            
            # 샤프 비율 (무위험 수익률 3% 가정)
            risk_free_rate = 0.03
            if len(daily_returns) > 0 and daily_returns.std() > 0:
                excess_return = annual_return_pct / 100 - risk_free_rate
                volatility = daily_returns.std() * np.sqrt(252)  # 연환산 변동성
                sharpe_ratio = excess_return / volatility
            else:
                sharpe_ratio = 0
                volatility = 0
            
            # 매매 통계
            buy_trades = [t for t in self.trade_history if t['action'] == 'BUY']
            sell_trades = [t for t in self.trade_history if t['action'] == 'SELL']
            
            if sell_trades:
                profitable_trades = [t for t in sell_trades if t['profit'] > 0]
                win_rate = len(profitable_trades) / len(sell_trades) * 100
                avg_profit = np.mean([t['profit'] for t in sell_trades])
                avg_return = np.mean([t['return_pct'] for t in sell_trades])
            else:
                win_rate = 0
                avg_profit = 0
                avg_return = 0
            
            # 실현 손익
            total_realized_pnl = sum([pos['realized_pnl'] for pos in portfolio['positions'].values()])
            
            # 결과 딕셔너리
            results = {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'trading_days': len(trading_dates),
                'total_days': total_days,
                'years': years,
                
                'initial_budget': initial_budget,
                'final_value': final_value,
                'total_return': final_value - initial_budget,
                'total_return_pct': total_return_pct,
                'annual_return_pct': annual_return_pct,
                'volatility': volatility * 100,
                
                'max_drawdown': max_drawdown,
                'max_drawdown_pct': max_drawdown_pct,
                'sharpe_ratio': sharpe_ratio,
                
                'total_trades': len(self.trade_history),
                'buy_trades': len(buy_trades),
                'sell_trades': len(sell_trades),
                'win_rate': win_rate,
                'avg_profit': avg_profit,
                'avg_return_pct': avg_return,
                'total_realized_pnl': total_realized_pnl,
                
                'final_cash': portfolio['cash'],
                'commission_paid': sum([t.get('commission', 0) for t in self.trade_history]),
                'slippage_cost': sum([t.get('slippage', 0) for t in self.trade_history])
            }
            
            return results
            
        except Exception as e:
            print(f"❌ 결과 분석 중 오류: {str(e)}")
            return {}

    def generate_report(self, save_file=True):
        """백테스팅 리포트 생성"""
        if not self.backtest_results:
            print("❌ 백테스팅 결과가 없습니다.")
            return
        
        results = self.backtest_results
        
        report = f"""
🥇 =================== 금투자 백테스팅 결과 리포트 ===================

📅 백테스팅 기간: {results['start_date']} ~ {results['end_date']} ({results['trading_days']}일)
💰 초기 자본: {results['initial_budget']:,.0f}원
💎 최종 자산: {results['final_value']:,.0f}원

📊 =================== 수익성 분석 ===================
총 수익률:        {results['total_return_pct']:+.2f}% ({results['total_return']:+,.0f}원)
연환산 수익률:    {results['annual_return_pct']:+.2f}%
연환산 변동성:    {results['volatility']:.2f}%
샤프 비율:       {results['sharpe_ratio']:.3f}

📉 =================== 리스크 분석 ===================
최대 낙폭(MDD):   {results['max_drawdown_pct']:.2f}%
실현 손익:       {results['total_realized_pnl']:+,.0f}원

💹 =================== 매매 통계 ===================
총 매매 횟수:     {results['total_trades']}회 (매수: {results['buy_trades']}, 매도: {results['sell_trades']})
승률:           {results['win_rate']:.1f}%
평균 수익률:     {results['avg_return_pct']:+.2f}%
평균 손익:       {results['avg_profit']:+,.0f}원

💸 =================== 비용 분석 ===================
수수료 총액:     {results['commission_paid']:,.0f}원
슬리피지 비용:   {results['slippage_cost']:,.0f}원
최종 현금:       {results['final_cash']:,.0f}원

=================================================================
"""
        
        print(report)
        
        if save_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"GoldBacktest_Report_{timestamp}.txt"
            
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(report)
                print(f"📄 리포트가 저장되었습니다: {filename}")
            except Exception as e:
                print(f"❌ 리포트 저장 실패: {str(e)}")
        
        return report

    def plot_results(self, save_charts=True):
        """백테스팅 결과 차트 생성"""
        if not self.daily_portfolio:
            print("❌ 차트를 그릴 데이터가 없습니다.")
            return
        
        try:
            # 데이터 준비
            dates = [d['date'] for d in self.daily_portfolio]
            values = [d['total_value'] for d in self.daily_portfolio]
            returns = [d['return_pct'] for d in self.daily_portfolio]
            
            # 벤치마크 데이터 (KODEX 골드선물 H - 132030)
            benchmark_data = None
            try:
                start_date = dates[0].strftime('%Y-%m-%d')
                end_date = dates[-1].strftime('%Y-%m-%d')
                benchmark_df = Common.GetOhlcv("KR", "132030", 1000)
                
                if benchmark_df is not None:
                    benchmark_df.index = pd.to_datetime(benchmark_df.index)
                    mask = (benchmark_df.index >= start_date) & (benchmark_df.index <= end_date)
                    benchmark_df = benchmark_df[mask]
                    
                    if len(benchmark_df) > 0:
                        initial_price = benchmark_df['close'].iloc[0]
                        benchmark_returns = ((benchmark_df['close'] / initial_price) - 1) * 100
                        benchmark_data = benchmark_returns
            except:
                pass
            
            # 차트 생성
            fig, axes = plt.subplots(3, 2, figsize=(16, 12))
            fig.suptitle('🥇 금투자 백테스팅 결과 분석', fontsize=16, fontweight='bold')
            
            # 1. 포트폴리오 가치 변화
            ax1 = axes[0, 0]
            ax1.plot(dates, values, color='gold', linewidth=2, label='포트폴리오 가치')
            ax1.set_title('📈 포트폴리오 가치 변화')
            ax1.set_ylabel('자산 가치 (원)')
            ax1.grid(True, alpha=0.3)
            ax1.legend()
            
            # y축 포맷팅
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M'))
            
            # 2. 누적 수익률 vs 벤치마크
            ax2 = axes[0, 1]
            ax2.plot(dates, returns, color='gold', linewidth=2, label='포트폴리오')
            
            if benchmark_data is not None and len(benchmark_data) > 0:
                # 벤치마크 데이터와 날짜 매칭
                bench_dates = benchmark_df.index
                common_dates = [d for d in dates if d in bench_dates]
                
                if common_dates:
                    bench_values = [benchmark_data.loc[d] for d in common_dates if d in benchmark_data.index]
                    if bench_values:
                        ax2.plot(common_dates, bench_values, color='blue', linewidth=1, 
                                alpha=0.7, label='KODEX 골드선물(H)')
            
            ax2.set_title('📊 누적 수익률 비교')
            ax2.set_ylabel('수익률 (%)')
            ax2.grid(True, alpha=0.3)
            ax2.legend()
            
            # 3. 드로우다운
            ax3 = axes[1, 0]
            peak = values[0]
            drawdowns = []
            
            for value in values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100
                drawdowns.append(drawdown)
            
            ax3.fill_between(dates, 0, drawdowns, color='red', alpha=0.3)
            ax3.plot(dates, drawdowns, color='red', linewidth=1)
            ax3.set_title('📉 드로우다운')
            ax3.set_ylabel('드로우다운 (%)')
            ax3.grid(True, alpha=0.3)
            ax3.invert_yaxis()
            
            # 4. 월별 수익률
            ax4 = axes[1, 1]
            monthly_returns = []
            monthly_labels = []
            
            # 월별 데이터 계산
            current_month = None
            month_start_value = None
            
            for i, (date, value) in enumerate(zip(dates, values)):
                month_key = date.strftime('%Y-%m')
                
                if current_month != month_key:
                    if month_start_value is not None and current_month is not None:
                        # 이전 달 수익률 계산
                        month_return = (values[i-1] - month_start_value) / month_start_value * 100
                        monthly_returns.append(month_return)
                        monthly_labels.append(current_month)
                    
                    current_month = month_key
                    month_start_value = value
            
            # 마지막 달 처리
            if month_start_value is not None:
                month_return = (values[-1] - month_start_value) / month_start_value * 100
                monthly_returns.append(month_return)
                monthly_labels.append(current_month)
            
            if monthly_returns:
                colors = ['green' if r >= 0 else 'red' for r in monthly_returns]
                bars = ax4.bar(range(len(monthly_returns)), monthly_returns, color=colors, alpha=0.7)
                ax4.set_title('📅 월별 수익률')
                ax4.set_ylabel('월 수익률 (%)')
                ax4.set_xticks(range(len(monthly_labels)))
                ax4.set_xticklabels(monthly_labels, rotation=45)
                ax4.grid(True, alpha=0.3)
                ax4.axhline(y=0, color='black', linestyle='-', alpha=0.5)
            
            # 5. 매매 포인트 표시
            ax5 = axes[2, 0]
            ax5.plot(dates, returns, color='gold', linewidth=1, alpha=0.5, label='수익률')
            
            # 매수/매도 포인트 표시
            buy_dates = [t['date'] for t in self.trade_history if t['action'] == 'BUY']
            sell_dates = [t['date'] for t in self.trade_history if t['action'] == 'SELL']
            
            for buy_date in buy_dates:
                if buy_date in dates:
                    idx = dates.index(buy_date)
                    ax5.scatter(buy_date, returns[idx], color='blue', marker='^', s=30, alpha=0.7)
            
            for sell_date in sell_dates:
                if sell_date in dates:
                    idx = dates.index(sell_date)
                    ax5.scatter(sell_date, returns[idx], color='red', marker='v', s=30, alpha=0.7)
            
            ax5.set_title('💹 매매 포인트')
            ax5.set_ylabel('수익률 (%)')
            ax5.grid(True, alpha=0.3)
            ax5.legend(['수익률', '매수', '매도'])
            
            # 6. 통계 요약
            ax6 = axes[2, 1]
            ax6.axis('off')
            
            stats_text = f"""
📊 주요 통계

총 수익률: {self.backtest_results.get('total_return_pct', 0):.2f}%
연환산 수익률: {self.backtest_results.get('annual_return_pct', 0):.2f}%
최대 낙폭: {self.backtest_results.get('max_drawdown_pct', 0):.2f}%
샤프 비율: {self.backtest_results.get('sharpe_ratio', 0):.3f}

매매 통계:
총 매매: {self.backtest_results.get('total_trades', 0)}회
승률: {self.backtest_results.get('win_rate', 0):.1f}%
평균 수익률: {self.backtest_results.get('avg_return_pct', 0):.2f}%

비용:
수수료: {self.backtest_results.get('commission_paid', 0):,.0f}원
슬리피지: {self.backtest_results.get('slippage_cost', 0):,.0f}원
            """
            
            ax6.text(0.1, 0.9, stats_text, transform=ax6.transAxes, fontsize=10,
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
            
            # 레이아웃 조정
            plt.tight_layout()
            
            if save_charts:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"GoldBacktest_Charts_{timestamp}.png"
                try:
                    plt.savefig(filename, dpi=300, bbox_inches='tight')
                    print(f"📊 차트가 저장되었습니다: {filename}")
                except Exception as e:
                    print(f"❌ 차트 저장 실패: {str(e)}")
            
            plt.show()
            
        except Exception as e:
            print(f"❌ 차트 생성 중 오류: {str(e)}")

    def export_trade_history(self):
        """거래 이력 엑셀 파일로 내보내기"""
        if not self.trade_history:
            print("❌ 거래 이력이 없습니다.")
            return
        
        try:
            # DataFrame 생성
            df = pd.DataFrame(self.trade_history)
            
            # 날짜 포맷팅
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            
            # 컬럼 순서 정리
            columns_order = ['date', 'product_code', 'action', 'position', 'price', 'amount']
            
            if 'profit' in df.columns:
                columns_order.extend(['cost', 'revenue', 'profit', 'return_pct', 'commission', 'slippage', 'reason'])
            else:
                columns_order.extend(['cost', 'commission', 'slippage', 'reason'])
            
            # 존재하는 컬럼만 선택
            available_columns = [col for col in columns_order if col in df.columns]
            df = df[available_columns]
            
            # 컬럼명 한글화
            column_mapping = {
                'date': '일자',
                'product_code': '종목코드', 
                'action': '매매구분',
                'position': '차수',
                'price': '가격',
                'amount': '수량',
                'cost': '매수금액',
                'revenue': '매도금액',
                'profit': '손익',
                'return_pct': '수익률(%)',
                'commission': '수수료',
                'slippage': '슬리피지',
                'reason': '사유'
            }
            
            df = df.rename(columns=column_mapping)
            
            # 파일 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"GoldBacktest_TradeHistory_{timestamp}.xlsx"
            
            df.to_excel(filename, index=False, engine='openpyxl')
            print(f"📁 거래 이력이 저장되었습니다: {filename}")
            
        except Exception as e:
            print(f"❌ 거래 이력 내보내기 실패: {str(e)}")

################################### 🎯 실행 함수들 ##################################

def run_simple_backtest():
    """간단한 백테스팅 실행"""
    try:
        print("🚀 간단한 금투자 백테스팅 시작")
        
        # 백테스팅 엔진 생성
        engine = GoldBacktestingEngine()
        
        # 기본 설정
        product_codes = ["132030"]  # KODEX 골드선물(H)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)  # 1년
        initial_budget = 5000000  # 500만원
        
        print(f"📊 테스트 종목: {product_codes}")
        print(f"📅 테스트 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
        
        # 백테스팅 실행
        results = engine.run_backtest(product_codes, start_date, end_date, initial_budget)
        
        if results:
            # 결과 출력
            engine.generate_report()
            
            # 차트 생성
            engine.plot_results()
            
            # 거래 이력 내보내기
            engine.export_trade_history()
        
        return engine, results
        
    except Exception as e:
        print(f"❌ 백테스팅 실행 중 오류: {str(e)}")
        return None, None

def run_multi_period_backtest():
    """다양한 기간 백테스팅"""
    try:
        print("🎯 다기간 금투자 백테스팅 시작")
        
        periods = [
            ("1년", 365),
            ("2년", 730), 
            ("3년", 1095)
        ]
        
        results_summary = []
        
        for period_name, days in periods:
            print(f"\n🔍 {period_name} 백테스팅 시작...")
            
            engine = GoldBacktestingEngine()
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            product_codes = ["132030", "319640"]  # 2개 금 ETF
            
            results = engine.run_backtest(product_codes, start_date, end_date, 5000000)
            
            if results:
                results_summary.append({
                    'period': period_name,
                    'total_return_pct': results['total_return_pct'],
                    'annual_return_pct': results['annual_return_pct'],
                    'max_drawdown_pct': results['max_drawdown_pct'],
                    'sharpe_ratio': results['sharpe_ratio'],
                    'win_rate': results['win_rate']
                })
        
        # 기간별 결과 비교
        print(f"\n📊 =================== 기간별 성과 비교 ===================")
        print(f"{'기간':<10} {'총수익률':<10} {'연수익률':<10} {'MDD':<10} {'샤프':<10} {'승률':<10}")
        print("-" * 65)
        
        for result in results_summary:
            print(f"{result['period']:<10} "
                  f"{result['total_return_pct']:>8.2f}% "
                  f"{result['annual_return_pct']:>8.2f}% "
                  f"{result['max_drawdown_pct']:>8.2f}% "
                  f"{result['sharpe_ratio']:>8.3f} "
                  f"{result['win_rate']:>8.1f}%")
        
        return results_summary
        
    except Exception as e:
        print(f"❌ 다기간 백테스팅 중 오류: {str(e)}")
        return []

def run_parameter_optimization():
    """파라미터 최적화 백테스팅"""
    try:
        print("⚡ 파라미터 최적화 백테스팅 시작")
        
        # 최적화할 파라미터들
        rsi_periods = [14, 21, 28]
        drop_multipliers = [0.8, 1.0, 1.2]  # 기본 하락률에 곱할 값
        
        best_result = None
        best_params = None
        optimization_results = []
        
        for rsi_period in rsi_periods:
            for drop_mult in drop_multipliers:
                print(f"\n🔧 테스트 중: RSI {rsi_period}일, 하락률 배수 {drop_mult}")
                
                # 설정 수정
                engine = GoldBacktestingEngine()
                engine.config.config['technical_indicators']['rsi_period'] = rsi_period
                
                # 하락률 조정
                base_drops = engine.config.config['dynamic_drop_requirements']['base_drops']
                for key in base_drops:
                    base_drops[key] = base_drops[key] * drop_mult
                
                # 백테스팅 실행
                end_date = datetime.now()
                start_date = end_date - timedelta(days=730)  # 2년
                
                results = engine.run_backtest(["132030"], start_date, end_date, 5000000)
                
                if results:
                    # 성과 점수 계산 (수익률 + 샤프비율 - MDD)
                    score = results['annual_return_pct'] + results['sharpe_ratio'] * 10 - results['max_drawdown_pct']
                    
                    optimization_results.append({
                        'rsi_period': rsi_period,
                        'drop_multiplier': drop_mult,
                        'annual_return': results['annual_return_pct'],
                        'sharpe_ratio': results['sharpe_ratio'],
                        'max_drawdown': results['max_drawdown_pct'],
                        'score': score
                    })
                    
                    if best_result is None or score > best_result['score']:
                        best_result = optimization_results[-1]
                        best_params = {'rsi_period': rsi_period, 'drop_multiplier': drop_mult}
                    
                    print(f"   📈 연수익률: {results['annual_return_pct']:.2f}%")
                    print(f"   📊 샤프비율: {results['sharpe_ratio']:.3f}")
                    print(f"   📉 MDD: {results['max_drawdown_pct']:.2f}%")
                    print(f"   ⭐ 점수: {score:.2f}")
        
        # 최적화 결과 출력
        print(f"\n🏆 =================== 최적화 결과 ===================")
        print(f"최적 파라미터:")
        print(f"  RSI 기간: {best_params['rsi_period']}일")
        print(f"  하락률 배수: {best_params['drop_multiplier']}")
        print(f"최적 성과:")
        print(f"  연환산 수익률: {best_result['annual_return']:.2f}%")
        print(f"  샤프 비율: {best_result['sharpe_ratio']:.3f}")
        print(f"  최대 낙폭: {best_result['max_drawdown']:.2f}%")
        print(f"  종합 점수: {best_result['score']:.2f}")
        
        return optimization_results, best_params
        
    except Exception as e:
        print(f"❌ 파라미터 최적화 중 오류: {str(e)}")
        return [], None

def show_backtest_commands():
    """백테스팅 명령어 안내"""
    print("""
🥇 ================ 금투자 백테스팅 명령어 ================
1. run_simple_backtest()        - 기본 1년 백테스팅
2. run_multi_period_backtest()  - 다기간(1,2,3년) 비교 백테스팅  
3. run_parameter_optimization() - 파라미터 최적화 백테스팅
4. show_backtest_commands()     - 이 도움말 출력

🔧 커스텀 백테스팅:
engine = GoldBacktestingEngine()
results = engine.run_backtest(
    product_codes=["132030", "319640"],
    start_date=datetime(2022, 1, 1), 
    end_date=datetime(2024, 12, 31),
    initial_budget=10000000
)
engine.generate_report()
engine.plot_results()
engine.export_trade_history()
========================================================
""")

################################### 🎯 메인 실행 부분 ##################################

if __name__ == "__main__":
    print("🥇 금투자 백테스팅 시스템 로드 완료!")
    print("📋 show_backtest_commands() 를 입력하면 사용법을 볼 수 있습니다.")
    print("🚀 빠른 시작: run_simple_backtest()")
    
    # 간단한 데모 실행 (옵션)
    demo_run = input("\n데모 백테스팅을 실행하시겠습니까? (y/n): ")
    if demo_run.lower() == 'y':
        run_simple_backtest()