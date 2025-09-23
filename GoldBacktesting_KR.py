#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🥇 금 ETF 포트폴리오 백테스팅 시스템
완전한 SmartMagicSplit 로직 구현
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import warnings
import os
import time
warnings.filterwarnings('ignore')

# 한글 폰트 설정
plt.rcParams['font.family'] = ['Malgun Gothic', 'Arial Unicode MS', 'Apple Gothic']
plt.rcParams['axes.unicode_minus'] = False

# KIS API 사용 시도
try:
    import KIS_Common as Common
    import KIS_API_Helper_KR as KisKR
    
    try:
        if hasattr(Common, 'GetToken'):
            token = Common.GetToken(Common.GetNowDist())
            KIS_API_AVAILABLE = bool(token)
            print("✅ KIS API 사용 가능" if KIS_API_AVAILABLE else "⚠️ KIS API 토큰 없음")
        else:
            KIS_API_AVAILABLE = False
            print("⚠️ KIS API 함수 없음")
    except:
        KIS_API_AVAILABLE = False
        print("⚠️ KIS API 초기화 실패")
        
except ImportError:
    KIS_API_AVAILABLE = False
    print("⚠️ KIS API 모듈 없음 - 모의 데이터 사용")

class GoldETFBacktester:
    def __init__(self, initial_capital=600000, days_back=365):
        self.initial_capital = initial_capital
        self.days_back = days_back
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=days_back)
        
        # 포트폴리오 설정 (금 상승장 최적화)
        self.portfolio = {
            '132030': {
                'name': 'KODEX 골드선물(H)',
                'weight': 0.35,
                'hold_profit_target': 20,      # 10 → 20 (금 강세 대비)
                'quick_profit_target': 8,      # 5 → 8 상향
                'reentry_cooldown_hours': 2,   # 6 → 2 단축 (기회 놓침 방지)
                'rsi_upper_bound': 80,         # 65 → 80 (과매수 완화)
                'stop_loss_thresholds': [-0.15, -0.20, -0.25, -0.25, -0.25],  # 손절선 완화
                'trend_multiplier': 1.5        # 🆕 상승 추세 시 목표 배수
            },
            '319640': {
                'name': 'TIGER 골드선물',
                'weight': 0.35,
                'hold_profit_target': 20,      # 10 → 20 (금 강세 대비)
                'quick_profit_target': 8,      # 5 → 8 상향
                'reentry_cooldown_hours': 2,   # 6 → 2 단축
                'rsi_upper_bound': 80,         # 65 → 80 (과매수 완화)
                'stop_loss_thresholds': [-0.15, -0.20, -0.25, -0.25, -0.25],  # 손절선 완화
                'trend_multiplier': 1.5        # 🆕 상승 추세 시 목표 배수
            },
            '411060': {
                'name': 'ACE KRX 금현물',
                'weight': 0.30,
                'hold_profit_target': 15,      # 8 → 15 (금 강세 대비)
                'quick_profit_target': 6,      # 4 → 6 상향
                'reentry_cooldown_hours': 2,   # 8 → 2 단축
                'rsi_upper_bound': 80,         # 75 → 80 (과매수 완화)
                'stop_loss_thresholds': [-0.12, -0.18, -0.22, -0.22, -0.22],  # 손절선 완화 (현물은 보수적)
                'trend_multiplier': 1.3        # 🆕 상승 추세 시 목표 배수 (현물은 보수적)
            }
        }
        
        # 매매 파라미터 (금 상승장 최적화)
        self.div_num = 5
        self.base_drops = [0, 0.025, 0.030, 0.035, 0.040]  # 하락률 요구사항 완화 (진입 기회 확대)
        self.rsi_period = 14
        self.ma_short = 5
        self.ma_mid = 20
        self.ma_long = 60
        
        # 결과 저장
        self.data = {}
        self.trades = []
        self.daily_portfolio_value = []
        self.results = {}
        
    def calculate_rsi(self, prices, period=14):
        """RSI 계산"""
        if len(prices) < period + 1:
            return [50] * len(prices)
        
        delta = np.diff(prices)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = np.convolve(gain, np.ones(period)/period, mode='valid')
        avg_loss = np.convolve(loss, np.ones(period)/period, mode='valid')
        
        rsi_values = []
        for i in range(len(avg_gain)):
            if avg_loss[i] == 0:
                rsi = 100
            else:
                rs = avg_gain[i] / avg_loss[i]
                rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)
        
        padding = [50] * (len(prices) - len(rsi_values))
        return padding + rsi_values
    
    def calculate_sma(self, prices, period):
        """단순이동평균 계산"""
        if len(prices) < period:
            return [np.mean(prices)] * len(prices)
        
        sma_values = []
        for i in range(len(prices)):
            if i < period - 1:
                sma_values.append(np.mean(prices[:i+1]))
            else:
                sma_values.append(np.mean(prices[i-period+1:i+1]))
        return sma_values
    
    def generate_mock_data(self, symbol, current_price=None):
        """모의 데이터 생성"""
        config = self.portfolio[symbol]
        
        # 거래일 생성 (주말 제외)
        dates = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        dates = [d for d in dates if d.weekday() < 5]
        
        if len(dates) == 0:
            return None
        
        # 기본 가격 설정
        if current_price:
            base_price = current_price
        elif symbol == '132030':
            base_price = 15000
        elif symbol == '319640':
            base_price = 25000
        else:
            base_price = 18000
        
        # 변동성 설정
        volatility = 0.015 if symbol != '411060' else 0.012
        
        # 시드 설정
        np.random.seed(42 + int(symbol))
        
        # 가격 시뮬레이션
        if current_price:
            # 현재가 기반 역산
            prices = [current_price]
            for i in range(len(dates) - 1):
                daily_change = np.random.normal(-0.0001, volatility)
                new_price = prices[-1] * (1 + daily_change)
                new_price = max(base_price * 0.8, min(base_price * 1.3, new_price))
                prices.append(new_price)
            prices.reverse()
        else:
            # 기본 시뮬레이션 (실제 금 강세 반영)
            prices = [base_price]
            for i in range(1, len(dates)):
                # 🥇 금 강세장 트렌드 반영
                trend = 0.002  # 연간 약 80% 상승 트렌드
                cycle_factor = np.sin(i * 0.08) * 0.2  # 주기적 변동
                random_factor = np.random.normal(0, volatility)
                
                daily_return = trend + cycle_factor * volatility + random_factor
                new_price = prices[-1] * (1 + daily_return)
                
                # 실제 차트 반영한 가격 범위
                min_price = base_price * 0.6   # 더 넓은 하방
                max_price = base_price * 2.2   # 대폭 상향 (실제 +90% 반영)
                new_price = max(min_price, min(max_price, new_price))
                
                prices.append(new_price)
        
        # OHLCV 데이터 생성
        ohlcv_data = []
        for date, close in zip(dates, prices):
            daily_vol = volatility * 0.5
            high = close * (1 + np.random.uniform(0, daily_vol))
            low = close * (1 - np.random.uniform(0, daily_vol))
            open_price = (high + low) / 2 + np.random.normal(0, close * 0.002)
            volume = np.random.randint(50000, 200000)
            
            ohlcv_data.append({
                'Date': date,
                'Open': open_price,
                'High': high,
                'Low': low,
                'Close': close,
                'Volume': volume
            })
        
        # DataFrame 생성
        df = pd.DataFrame(ohlcv_data)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        
        # 기술적 지표 계산
        df['RSI'] = self.calculate_rsi(df['Close'].values, self.rsi_period)
        df['MA5'] = self.calculate_sma(df['Close'].values, self.ma_short)
        df['MA20'] = self.calculate_sma(df['Close'].values, self.ma_mid)
        df['MA60'] = self.calculate_sma(df['Close'].values, self.ma_long)
        df['Volatility'] = df['Close'].pct_change().rolling(20).std() * 100
        df['Volatility'] = df['Volatility'].fillna(volatility * 100)
        
        return df
    
    def fetch_data(self):
        """데이터 수집"""
        print("🚀 금 ETF 데이터 수집 시작...")
        
        for symbol, config in self.portfolio.items():
            print(f"  - {config['name']} ({symbol}) 데이터 수집...")
            
            current_price = None
            
            # KIS API로 현재가 시도
            if KIS_API_AVAILABLE:
                try:
                    current_price = KisKR.GetCurrentPrice(symbol)
                    if current_price and current_price > 0:
                        print(f"    ✅ 현재가 확인: {current_price:,.0f}원")
                    else:
                        current_price = None
                except:
                    current_price = None
            
            # 모의 데이터 생성
            try:
                mock_data = self.generate_mock_data(symbol, current_price)
                if mock_data is not None:
                    self.data[symbol] = mock_data
                    price_type = "현재가 기반" if current_price else "기본"
                    print(f"    ✅ {price_type} 모의 데이터 생성 완료 ({len(mock_data)}일)")
                    print(f"    📊 가격 범위: {mock_data['Close'].min():.0f}원 ~ {mock_data['Close'].max():.0f}원")
                else:
                    print(f"    ❌ 모의 데이터 생성 실패")
            except Exception as e:
                print(f"    ❌ 데이터 생성 오류: {str(e)}")
            
            time.sleep(0.3)  # API 제한 고려
        
        success = len(self.data) > 0
        if success:
            print(f"✅ 총 {len(self.data)}개 종목 데이터 수집 완료")
        else:
            print("❌ 데이터 수집 실패")
        
        return success
    
    def calculate_technical_indicators(self, symbol, date):
        """기술적 지표 기반 매매 신호 계산 (금 상승장 최적화)"""
        if symbol not in self.data:
            return {'can_buy': False, 'can_sell': False, 'strength': 0, 'trend_strength': 0}
        
        df = self.data[symbol]
        if date not in df.index:
            # 가장 가까운 날짜 찾기
            available_dates = df.index
            closest_date = min(available_dates, key=lambda x: abs((x - date).days))
            if abs((closest_date - date).days) > 7:
                return {'can_buy': False, 'can_sell': False, 'strength': 0, 'trend_strength': 0}
            date = closest_date
        
        row = df.loc[date]
        config = self.portfolio[symbol]
        
        # RSI 및 이동평균
        rsi = row['RSI'] if not pd.isna(row['RSI']) else 50
        ma5 = row['MA5']
        ma20 = row['MA20']
        ma60 = row['MA60']
        
        if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma60):
            return {'can_buy': False, 'can_sell': False, 'strength': 50, 'trend_strength': 0}
        
        # 🆕 상승 추세 강도 계산
        trend_strength = 0
        price_vs_ma60 = row['Close'] / ma60
        if ma5 > ma20 > ma60:
            trend_strength = min(100, (price_vs_ma60 - 1) * 100)  # MA60 대비 상승률
        
        # 🔥 개선된 매수 신호 (상승장 최적화)
        can_buy = (
            rsi < config['rsi_upper_bound'] and          # RSI 상한선 (80으로 상향)
            ma5 > ma20 and                               # 단기 상승 추세
            row['Close'] > ma60 and                      # 🆕 장기 상승 추세 필수
            price_vs_ma60 < 1.5                         # 🆕 과도한 고점 방지
        )
        
        # 🔥 개선된 기술적 매도 신호 (상승장에서 덜 민감)
        can_sell_technical = (
            rsi > 85 or                                  # 85 이상에서만 과매수 (기존 80)
            (ma5 < ma20 and row['Close'] < ma60)         # 🆕 장기 추세 이탈 시에만
        )
        
        # 🆕 강화된 신호 강도 계산
        strength = 50
        
        # RSI 기반 조정
        if rsi < 30:
            strength += 25    # 과매도 보너스 증가
        elif rsi < 50:
            strength += 10    # 중립 구간 보너스
        elif rsi > 80:
            strength -= 10    # 과매수 패널티 완화 (기존 -15)
        
        # 추세 기반 보너스
        if ma5 > ma20 > ma60:
            strength += 20    # 상승 추세 보너스 증가 (기존 15)
            if trend_strength > 10:  # 강한 상승 추세 시 추가 보너스
                strength += 10
        elif ma5 < ma20 < ma60:
            strength -= 15    # 하락 추세 패널티
        
        return {
            'can_buy': can_buy,
            'can_sell_technical': can_sell_technical,
            'strength': max(0, min(100, strength)),
            'rsi': rsi,
            'trend_strength': trend_strength,
            'price_vs_ma60': price_vs_ma60
        }
    
    def check_drop_requirement(self, symbol, date, position_level):
        """차수별 하락률 요구사항 체크"""
        if position_level <= 1:
            return True
        
        if symbol not in self.data:
            return False
        
        df = self.data[symbol]
        available_dates = df.index
        closest_date = min(available_dates, key=lambda x: abs((x - date).days))
        
        if abs((closest_date - date).days) > 7:
            return False
        
        required_drop = self.base_drops[position_level - 1]
        if required_drop <= 0:
            return True
        
        try:
            end_idx = df.index.get_loc(closest_date)
            start_idx = max(0, end_idx - 5)
            recent_data = df.iloc[start_idx:end_idx + 1]
            
            if len(recent_data) == 0:
                return False
            
            recent_high = recent_data['High'].max()
            current_price = df.loc[closest_date, 'Close']
            actual_drop = (recent_high - current_price) / recent_high
            
            return actual_drop >= required_drop
        except:
            return False
    
    def run_backtest(self):
        """백테스팅 실행"""
        print("🚀 금 ETF 포트폴리오 백테스팅 시작...")
        
        if not self.data:
            print("❌ 데이터가 없습니다.")
            return False
        
        # 모든 날짜 수집
        all_dates = set()
        for df in self.data.values():
            all_dates.update(df.index)
        all_dates = sorted(list(all_dates))
        
        if not all_dates:
            print("❌ 유효한 날짜 데이터가 없습니다.")
            return False
        
        # 포트폴리오 상태 초기화
        cash = self.initial_capital
        positions = {}
        last_sell_time = {}
        
        for symbol in self.portfolio.keys():
            positions[symbol] = []
            last_sell_time[symbol] = None
        
        print(f"📅 {len(all_dates)}일간 백테스팅 실행...")
        
        for i, date in enumerate(all_dates):
            if i % 50 == 0:
                progress = i / len(all_dates) * 100
                print(f"  진행률: {progress:.1f}% ({date.strftime('%Y-%m-%d')})")
            
            # 각 종목별 처리
            for symbol, config in self.portfolio.items():
                if symbol not in self.data or date not in self.data[symbol].index:
                    continue
                
                current_price = self.data[symbol].loc[date, 'Close']
                allocated_budget = self.initial_capital * config['weight']
                
                # 기술적 지표 계산
                indicators = self.calculate_technical_indicators(symbol, date)
                
                # 매도 로직 (금 상승장 최적화)
                positions_to_remove = []
                for pos_idx, position in enumerate(positions[symbol]):
                    entry_price = position['entry_price']
                    profit_pct = (current_price - entry_price) / entry_price * 100
                    
                    # 손절 체크 (완화된 손절선 적용)
                    stop_loss_threshold = config['stop_loss_thresholds'][position['level'] - 1] * 100
                    should_stop_loss = profit_pct <= stop_loss_threshold
                    
                    # 🆕 상승 추세 시 목표 수익률 동적 조정
                    base_profit_target = config['hold_profit_target']
                    quick_profit_target = config['quick_profit_target']
                    
                    # 강한 상승 추세에서는 목표 수익률 확대
                    if indicators.get('trend_strength', 0) > 15:  # 강한 상승 추세
                        trend_multiplier = config.get('trend_multiplier', 1.0)
                        base_profit_target *= trend_multiplier
                        quick_profit_target *= trend_multiplier
                    
                    # 🔥 개선된 수익 실현 체크
                    should_take_profit = (
                        profit_pct >= base_profit_target or
                        (profit_pct >= quick_profit_target and indicators['can_sell_technical'])
                    )
                    
                    # 매도 실행
                    if should_stop_loss or should_take_profit:
                        sell_value = position['shares'] * current_price
                        cash += sell_value
                        
                        # 거래 기록
                        self.trades.append({
                            'date': date,
                            'symbol': symbol,
                            'name': config['name'],
                            'action': 'SELL',
                            'level': position['level'],
                            'shares': position['shares'],
                            'price': current_price,
                            'value': sell_value,
                            'profit_pct': profit_pct,
                            'reason': 'STOP_LOSS' if should_stop_loss else 'PROFIT_TAKING',
                            'hold_days': (date - position['entry_date']).days,
                            'trend_strength': indicators.get('trend_strength', 0),  # 🆕 추세 강도 기록
                            'target_used': base_profit_target  # 🆕 실제 사용된 목표 기록
                        })
                        
                        positions_to_remove.append(pos_idx)
                        last_sell_time[symbol] = date
                
                # 매도된 포지션 제거
                for pos_idx in reversed(positions_to_remove):
                    positions[symbol].pop(pos_idx)
                
                # 매수 로직
                if indicators['can_buy']:
                    # 쿨다운 체크
                    if last_sell_time[symbol]:
                        hours_since_sell = (date - last_sell_time[symbol]).total_seconds() / 3600
                        if hours_since_sell < config['reentry_cooldown_hours']:
                            continue
                    
                    # 다음 매수할 차수 결정
                    current_levels = [pos['level'] for pos in positions[symbol]]
                    next_level = 1
                    
                    if current_levels:
                        for level in range(1, 6):
                            if level not in current_levels:
                                if level == 1 or (level - 1) in current_levels:
                                    next_level = level
                                    break
                        else:
                            continue
                    
                    # 하락률 요구사항 체크
                    if not self.check_drop_requirement(symbol, date, next_level):
                        continue
                    
                    # 매수 실행
                    position_budget = allocated_budget / self.div_num
                    if cash >= position_budget and position_budget > current_price:
                        shares = int(position_budget / current_price)
                        if shares > 0:
                            actual_cost = shares * current_price
                            cash -= actual_cost
                            
                            # 포지션 추가
                            positions[symbol].append({
                                'level': next_level,
                                'shares': shares,
                                'entry_price': current_price,
                                'entry_date': date
                            })
                            
                            # 거래 기록
                            self.trades.append({
                                'date': date,
                                'symbol': symbol,
                                'name': config['name'],
                                'action': 'BUY',
                                'level': next_level,
                                'shares': shares,
                                'price': current_price,
                                'value': actual_cost,
                                'profit_pct': 0,
                                'reason': f'LEVEL_{next_level}_ENTRY',
                                'hold_days': 0
                            })
            
            # 일일 포트폴리오 가치 계산
            total_position_value = 0
            for symbol, symbol_positions in positions.items():
                if symbol in self.data and date in self.data[symbol].index:
                    current_price = self.data[symbol].loc[date, 'Close']
                    for position in symbol_positions:
                        total_position_value += position['shares'] * current_price
            
            portfolio_value = cash + total_position_value
            self.daily_portfolio_value.append({
                'date': date,
                'cash': cash,
                'positions': total_position_value,
                'total': portfolio_value,
                'return_pct': (portfolio_value - self.initial_capital) / self.initial_capital * 100
            })
        
        print("✅ 백테스팅 완료!")
        self.analyze_results()
        return True
    
    def analyze_results(self):
        """결과 분석"""
        print("\n📊 백테스팅 결과 분석...")
        
        if not self.daily_portfolio_value:
            print("❌ 백테스팅 데이터가 없습니다.")
            return
        
        # 기본 통계
        final_value = self.daily_portfolio_value[-1]['total']
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        # 일별 수익률 계산
        daily_returns = []
        for i in range(1, len(self.daily_portfolio_value)):
            prev_value = self.daily_portfolio_value[i-1]['total']
            curr_value = self.daily_portfolio_value[i]['total']
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                daily_returns.append(daily_return)
        
        if not daily_returns:
            print("❌ 수익률 데이터 부족")
            return
        
        daily_returns = np.array(daily_returns)
        
        # 리스크 지표 계산
        trading_days = len(daily_returns)
        annualized_factor = 252 / trading_days if trading_days > 0 else 1
        
        volatility = np.std(daily_returns) * np.sqrt(252) * 100 if len(daily_returns) > 1 else 0
        mean_return = np.mean(daily_returns)
        sharpe_ratio = mean_return / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
        
        # 최대 낙폭 계산
        peak = self.initial_capital
        max_drawdown = 0
        for day in self.daily_portfolio_value:
            if day['total'] > peak:
                peak = day['total']
            if peak > 0:
                drawdown = (peak - day['total']) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        # 거래 분석
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            buy_trades = trades_df[trades_df['action'] == 'BUY']
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            
            winning_trades = sell_trades[sell_trades['profit_pct'] > 0] if len(sell_trades) > 0 else pd.DataFrame()
            losing_trades = sell_trades[sell_trades['profit_pct'] < 0] if len(sell_trades) > 0 else pd.DataFrame()
            
            # 종목별 성과
            symbol_performance = {}
            for symbol, config in self.portfolio.items():
                symbol_trades = sell_trades[sell_trades['symbol'] == symbol] if len(sell_trades) > 0 else pd.DataFrame()
                if len(symbol_trades) > 0:
                    total_profit = symbol_trades['profit_pct'].sum()
                    win_rate = len(symbol_trades[symbol_trades['profit_pct'] > 0]) / len(symbol_trades) * 100
                    avg_hold_days = symbol_trades['hold_days'].mean()
                    symbol_performance[symbol] = {
                        'name': config['name'],
                        'total_profit': total_profit,
                        'win_rate': win_rate,
                        'avg_hold_days': avg_hold_days,
                        'total_trades': len(symbol_trades)
                    }
        else:
            buy_trades = pd.DataFrame()
            sell_trades = pd.DataFrame()
            winning_trades = pd.DataFrame()
            losing_trades = pd.DataFrame()
            symbol_performance = {}
        
        # 결과 저장
        self.results = {
            'period': f"{self.start_date.strftime('%Y-%m-%d')} ~ {self.end_date.strftime('%Y-%m-%d')}",
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'annual_return': total_return * annualized_factor,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown * 100,
            'total_trades': len(self.trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'win_rate': len(winning_trades) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0,
            'avg_profit': winning_trades['profit_pct'].mean() if len(winning_trades) > 0 else 0,
            'avg_loss': losing_trades['profit_pct'].mean() if len(losing_trades) > 0 else 0,
            'avg_hold_days': sell_trades['hold_days'].mean() if len(sell_trades) > 0 else 0,
            'symbol_performance': symbol_performance
        }
        
        # 결과 출력
        print(f"""
🥇 금 ETF 포트폴리오 백테스팅 결과
{'='*50}
📅 기간: {self.results['period']}
📊 거래일수: {trading_days}일
💰 초기 자본: {self.initial_capital:,.0f}원
💎 최종 자산: {final_value:,.0f}원
📈 총 수익률: {total_return:.2f}%
📊 연환산 수익률: {self.results['annual_return']:.2f}%
⚡ 변동성: {volatility:.2f}%
🎯 샤프 비율: {sharpe_ratio:.2f}
📉 최대 낙폭: {max_drawdown*100:.2f}%

거래 통계:
🔄 총 거래 횟수: {len(self.trades)}회
📈 매수: {len(buy_trades)}회
📉 매도: {len(sell_trades)}회
🏆 승률: {self.results['win_rate']:.1f}%
⏰ 평균 보유일: {self.results['avg_hold_days']:.1f}일
💹 평균 수익: {self.results['avg_profit']:.2f}%
💸 평균 손실: {self.results['avg_loss']:.2f}%""")
        
        if symbol_performance:
            print("\n종목별 성과:")
            for symbol, perf in symbol_performance.items():
                print(f"""
📊 {perf['name']} ({symbol}):
   수익률: {perf['total_profit']:.2f}%
   승률: {perf['win_rate']:.1f}%
   거래횟수: {perf['total_trades']}회
   평균보유: {perf['avg_hold_days']:.1f}일""")
        
        return self.results
    
    def plot_results(self):
        """결과 시각화"""
        if not self.daily_portfolio_value:
            print("❌ 시각화할 데이터가 없습니다.")
            return
        
        # 데이터 준비
        df = pd.DataFrame(self.daily_portfolio_value)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # 벤치마크 계산 (Buy & Hold)
        benchmark_value = []
        initial_prices = {}
        
        for symbol, config in self.portfolio.items():
            if symbol in self.data and len(self.data[symbol]) > 0:
                initial_prices[symbol] = self.data[symbol].iloc[0]['Close']
        
        for date in df.index:
            total_value = 0
            for symbol, config in self.portfolio.items():
                if symbol in self.data and symbol in initial_prices:
                    df_symbol = self.data[symbol]
                    if date in df_symbol.index:
                        current_price = df_symbol.loc[date, 'Close']
                    else:
                        closest_date = min(df_symbol.index, key=lambda x: abs((x - date).days))
                        current_price = df_symbol.loc[closest_date, 'Close']
                    
                    initial_investment = self.initial_capital * config['weight']
                    shares = initial_investment / initial_prices[symbol]
                    current_value = shares * current_price
                    total_value += current_value
            
            benchmark_value.append(total_value if total_value > 0 else self.initial_capital)
        
        df['benchmark'] = benchmark_value
        df['benchmark_return'] = (df['benchmark'] - self.initial_capital) / self.initial_capital * 100
        
        # 시각화
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('🥇 금 ETF 포트폴리오 백테스팅 결과', fontsize=16, fontweight='bold')
        
        # 1. 포트폴리오 가치 추이
        axes[0, 0].plot(df.index, df['total'], label='SmartMagicSplit', linewidth=2, color='gold')
        axes[0, 0].plot(df.index, df['benchmark'], label='Buy & Hold', linewidth=2, color='gray', alpha=0.7)
        axes[0, 0].set_title('포트폴리오 가치 추이')
        axes[0, 0].set_ylabel('포트폴리오 가치 (원)')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        axes[0, 0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # 2. 누적 수익률
        axes[0, 1].plot(df.index, df['return_pct'], label='SmartMagicSplit', linewidth=2, color='gold')
        axes[0, 1].plot(df.index, df['benchmark_return'], label='Buy & Hold', linewidth=2, color='gray', alpha=0.7)
        axes[0, 1].set_title('누적 수익률')
        axes[0, 1].set_ylabel('수익률 (%)')
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)
        axes[0, 1].axhline(y=0, color='black', linestyle='-', alpha=0.3)
        
        # 3. 현금 vs 포지션 비율
        axes[1, 0].fill_between(df.index, 0, df['cash'], alpha=0.7, label='현금', color='lightblue')
        axes[1, 0].fill_between(df.index, df['cash'], df['total'], alpha=0.7, label='포지션', color='lightcoral')
        axes[1, 0].set_title('자산 구성')
        axes[1, 0].set_ylabel('금액 (원)')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)
        axes[1, 0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # 4. 수익률 분포
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            if len(sell_trades) > 0:
                axes[1, 1].hist(sell_trades['profit_pct'], bins=20, alpha=0.7, color='gold', edgecolor='black')
                axes[1, 1].axvline(x=0, color='red', linestyle='--', alpha=0.7, label='손익분기점')
                mean_profit = sell_trades['profit_pct'].mean()
                axes[1, 1].axvline(x=mean_profit, color='blue', linestyle='-', alpha=0.7, label=f'평균: {mean_profit:.1f}%')
                axes[1, 1].set_title('거래별 수익률 분포')
                axes[1, 1].set_xlabel('수익률 (%)')
                axes[1, 1].set_ylabel('빈도')
                axes[1, 1].legend()
                axes[1, 1].grid(True, alpha=0.3)
            else:
                axes[1, 1].text(0.5, 0.5, '매도 거래 없음', ha='center', va='center', transform=axes[1, 1].transAxes)
                axes[1, 1].set_title('거래별 수익률 분포')
        else:
            axes[1, 1].text(0.5, 0.5, '거래 데이터 없음', ha='center', va='center', transform=axes[1, 1].transAxes)
            axes[1, 1].set_title('거래별 수익률 분포')
        
        plt.tight_layout()
        plt.savefig('gold_etf_backtest_results.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        # 추가 상세 차트
        self.plot_detailed_analysis()
    
    def plot_detailed_analysis(self):
        """상세 분석 차트"""
        if not self.trades:
            return
        
        trades_df = pd.DataFrame(self.trades)
        trades_df['date'] = pd.to_datetime(trades_df['date'])
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('🥇 금 ETF 포트폴리오 상세 분석', fontsize=16, fontweight='bold')
        
        # 1. 종목별 수익률
        sell_trades = trades_df[trades_df['action'] == 'SELL']
        if len(sell_trades) > 0:
            symbol_profits = sell_trades.groupby('name')['profit_pct'].agg(['mean', 'sum', 'count'])
            
            x_pos = range(len(symbol_profits))
            axes[0, 0].bar(x_pos, symbol_profits['sum'], alpha=0.7, color=['gold', 'silver', 'orange'])
            axes[0, 0].set_title('종목별 총 수익률')
            axes[0, 0].set_ylabel('총 수익률 (%)')
            axes[0, 0].set_xticks(x_pos)
            axes[0, 0].set_xticklabels(symbol_profits.index, rotation=45, ha='right')
            axes[0, 0].grid(True, alpha=0.3)
            
            # 수치 표시
            for i, v in enumerate(symbol_profits['sum']):
                axes[0, 0].text(i, v + 0.1, f'{v:.1f}%', ha='center', va='bottom')
        
        # 2. 차수별 성과
        if len(sell_trades) > 0:
            level_performance = sell_trades.groupby('level')['profit_pct'].agg(['mean', 'count'])
            
            axes[0, 1].bar(level_performance.index, level_performance['mean'], alpha=0.7, color='lightblue')
            axes[0, 1].set_title('차수별 평균 수익률')
            axes[0, 1].set_xlabel('차수')
            axes[0, 1].set_ylabel('평균 수익률 (%)')
            axes[0, 1].grid(True, alpha=0.3)
            
            # 거래 횟수 텍스트 추가
            for level, row in level_performance.iterrows():
                axes[0, 1].text(level, row['mean'] + 0.1, f'{int(row["count"])}회', ha='center', va='bottom', fontsize=9)
        
        # 3. 월별 수익률
        daily_df = pd.DataFrame(self.daily_portfolio_value)
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        daily_df.set_index('date', inplace=True)
        
        monthly_returns = daily_df['return_pct'].resample('M').last().pct_change() * 100
        monthly_returns = monthly_returns.dropna()
        
        if len(monthly_returns) > 0:
            colors = ['green' if x > 0 else 'red' for x in monthly_returns]
            axes[1, 0].bar(range(len(monthly_returns)), monthly_returns, color=colors, alpha=0.7)
            axes[1, 0].set_title('월별 수익률')
            axes[1, 0].set_ylabel('월 수익률 (%)')
            axes[1, 0].axhline(y=0, color='black', linestyle='-', alpha=0.3)
            axes[1, 0].grid(True, alpha=0.3)
            
            # x축 라벨 (분기별)
            step = max(1, len(monthly_returns) // 4)
            axes[1, 0].set_xticks(range(0, len(monthly_returns), step))
            axes[1, 0].set_xticklabels([monthly_returns.index[i].strftime('%Y-%m') for i in range(0, len(monthly_returns), step)], rotation=45)
        
        # 4. 보유기간별 수익률
        if len(sell_trades) > 0:
            # 보유기간 구간별 분석
            hold_days = sell_trades['hold_days']
            
            # 보유기간 구간 설정
            bins = [0, 7, 14, 30, 60, 90, float('inf')]
            labels = ['1주미만', '1-2주', '2주-1개월', '1-2개월', '2-3개월', '3개월이상']
            
            sell_trades['hold_period'] = pd.cut(hold_days, bins=bins, labels=labels, right=False)
            period_performance = sell_trades.groupby('hold_period')['profit_pct'].agg(['mean', 'count'])
            
            axes[1, 1].bar(range(len(period_performance)), period_performance['mean'], alpha=0.7, color='purple')
            axes[1, 1].set_title('보유기간별 평균 수익률')
            axes[1, 1].set_ylabel('평균 수익률 (%)')
            axes[1, 1].set_xticks(range(len(period_performance)))
            axes[1, 1].set_xticklabels(period_performance.index, rotation=45, ha='right')
            axes[1, 1].grid(True, alpha=0.3)
            
            # 거래 횟수 표시
            for i, (_, row) in enumerate(period_performance.iterrows()):
                axes[1, 1].text(i, row['mean'] + 0.1, f'{int(row["count"])}회', ha='center', va='bottom', fontsize=9)
        
        plt.tight_layout()
        plt.savefig('gold_etf_detailed_analysis.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def export_trades(self, filename='gold_etf_trades.xlsx'):
        """거래 내역 엑셀 내보내기"""
        if not self.trades:
            print("❌ 내보낼 거래 데이터가 없습니다.")
            return
        
        try:
            trades_df = pd.DataFrame(self.trades)
            
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 전체 거래 내역
                trades_df.to_excel(writer, sheet_name='전체거래내역', index=False)
                
                # 매도 거래만
                sell_trades = trades_df[trades_df['action'] == 'SELL'].copy()
                if len(sell_trades) > 0:
                    sell_trades.to_excel(writer, sheet_name='매도거래내역', index=False)
                
                # 종목별 요약
                if len(sell_trades) > 0:
                    summary = sell_trades.groupby(['symbol', 'name']).agg({
                        'profit_pct': ['count', 'mean', 'sum', 'std'],
                        'hold_days': 'mean',
                        'value': 'sum'
                    }).round(2)
                    summary.columns = ['거래횟수', '평균수익률', '총수익률', '수익률변동성', '평균보유일', '총거래금액']
                    summary.to_excel(writer, sheet_name='종목별요약')
                
                # 성과 요약
                results_df = pd.DataFrame([self.results])
                results_df.to_excel(writer, sheet_name='성과요약', index=False)
            
            print(f"✅ 거래 내역이 '{filename}' 파일로 저장되었습니다.")
        except Exception as e:
            print(f"❌ 파일 저장 중 오류: {str(e)}")
    
    def get_performance_summary(self):
        """성과 요약 딕셔너리 반환"""
        return self.results


def main():
    """메인 실행 함수"""
    print("🥇 금 ETF 포트폴리오 백테스팅 시스템")
    print("="*50)
    
    # 백테스터 초기화
    backtest = GoldETFBacktester(
        initial_capital=600000,  # 60만원
        days_back=365  # 1년간
    )
    
    try:
        # 데이터 수집
        if not backtest.fetch_data():
            print("❌ 데이터 수집에 실패했습니다.")
            return
        
        # 백테스팅 실행
        if not backtest.run_backtest():
            print("❌ 백테스팅 실행에 실패했습니다.")
            return
        
        # 결과 시각화
        backtest.plot_results()
        
        # 거래 내역 저장
        backtest.export_trades()
        
        # 성과 요약
        results = backtest.get_performance_summary()
        
        print(f"\n🎯 핵심 성과 지표:")
        print(f"📈 총 수익률: {results['total_return']:.2f}%")
        print(f"📊 샤프 비율: {results['sharpe_ratio']:.2f}")
        print(f"🏆 승률: {results['win_rate']:.1f}%")
        print(f"📉 최대 낙폭: {results['max_drawdown']:.2f}%")
        
        # 전략 평가
        print(f"\n💡 전략 평가:")
        if results['total_return'] > 0:
            print(f"✅ 수익 달성! SmartMagicSplit 전략이 효과적입니다.")
        else:
            print(f"⚠️ 손실 발생. 시장 상황이나 파라미터 조정이 필요할 수 있습니다.")
        
        if results['sharpe_ratio'] > 1.0:
            print(f"✅ 우수한 위험 대비 수익률! (샤프 비율 > 1.0)")
        elif results['sharpe_ratio'] > 0.5:
            print(f"🔶 양호한 위험 대비 수익률 (샤프 비율 0.5-1.0)")
        else:
            print(f"⚠️ 위험 대비 수익률 개선 필요 (샤프 비율 < 0.5)")
        
        # 금 ETF 특성 분석
        print(f"\n🥇 금 ETF 포트폴리오 특성:")
        print(f"• 안전자산 특성으로 변동성 제한: {results['volatility']:.1f}%")
        print(f"• 분산투자 효과: 환헤지 + 환노출 + 현물 조합")
        print(f"• 하락 보호: 최대 낙폭 {results['max_drawdown']:.1f}%로 제한")
        
        # Buy & Hold와 비교
        daily_df = pd.DataFrame(backtest.daily_portfolio_value)
        if len(daily_df) > 0:
            final_strategy_return = daily_df.iloc[-1]['return_pct']
            final_benchmark_return = (daily_df.iloc[-1]['total'] / backtest.initial_capital - 1) * 100
            
            print(f"\n📊 전략 비교:")
            print(f"• SmartMagicSplit: {final_strategy_return:.2f}%")
            if 'benchmark_return' in daily_df.columns:
                benchmark_final = daily_df.iloc[-1]['benchmark_return']
                print(f"• Buy & Hold: {benchmark_final:.2f}%")
                if final_strategy_return > benchmark_final:
                    print(f"✅ SmartMagicSplit이 Buy & Hold보다 {final_strategy_return - benchmark_final:.2f}%p 우수!")
                else:
                    print(f"⚠️ Buy & Hold가 {benchmark_final - final_strategy_return:.2f}%p 더 좋음")
            
    except Exception as e:
        print(f"❌ 백테스팅 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


# 사용 예시:
"""
# 기본 실행
python GoldBacktesting_KR.py

# 사용자 정의 실행
backtest = GoldETFBacktester(
    initial_capital=1000000,  # 100만원
    days_back=730  # 2년간
)

backtest.fetch_data()
backtest.run_backtest()
backtest.plot_results()

# 결과 분석
results = backtest.get_performance_summary()
print(f"총 수익률: {results['total_return']:.2f}%")
print(f"샤프 비율: {results['sharpe_ratio']:.2f}")
"""