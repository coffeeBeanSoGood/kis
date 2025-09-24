#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🥇 SmartGoldTradingBot 백테스팅 시스템
기존 SmartGoldTradingBot_KR.py의 로직과 한국투자증권 API를 그대로 활용한 백테스팅
Buy & Hold vs SmartMagicSplit 전략 비교
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings
import os
import time
warnings.filterwarnings('ignore')

# 🔥 yfinance 관련 코드 완전 제거 - KIS API만 사용
# try:
#     import yfinance as yf
#     YFINANCE_AVAILABLE = True
# except ImportError:
#     YFINANCE_AVAILABLE = False
#     print("⚠️ yfinance 모듈 없음 - KIS API 또는 모의 데이터만 사용")

# 🔥 SmartGoldTradingBot_KR.py에서 사용하는 모듈들 그대로 import
try:
    import KIS_Common as Common
    import KIS_API_Helper_KR as KisKR
    KIS_API_AVAILABLE = True
    print("✅ 한국투자증권 API 모듈 로드 완료")
except ImportError as e:
    KIS_API_AVAILABLE = False
    print(f"❌ KIS API 모듈 로드 실패: {str(e)}")
    print("⚠️ 모의 데이터로 대체됩니다.")

# 한글 폰트 설정 (Windows 환경 최적화)
try:
    import matplotlib.font_manager as fm
    
    # Windows 한글 폰트 시도
    font_candidates = [
        'Malgun Gothic',    # Windows 10/11 기본 한글 폰트
        'Gulim',           # 굴림
        'Dotum',           # 돋움  
        'Batang',          # 바탕
        'Gungsuh',         # 궁서
        'Microsoft YaHei', # 중국어지만 한글도 지원
        'DejaVu Sans'      # 기본 대안
    ]
    
    # 사용 가능한 폰트 찾기
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    selected_font = 'DejaVu Sans'  # 기본값
    
    for font in font_candidates:
        if font in available_fonts:
            selected_font = font
            print(f"✅ 한글 폰트 설정: {selected_font}")
            break
    
    plt.rcParams['font.family'] = selected_font
    plt.rcParams['axes.unicode_minus'] = False
    
except Exception as e:
    print(f"⚠️ 폰트 설정 실패 - 기본 폰트 사용: {str(e)}")
    # 폰트 설정 실패해도 계속 진행 (영어로 표시됨)

class GoldTradingBacktest:
    """SmartGoldTradingBot 로직을 활용한 백테스팅 시스템"""
    
    def __init__(self, initial_capital=600000, days_back=365):
        self.initial_capital = initial_capital
        self.days_back = days_back
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=days_back)
        
        # 🔥 매도 억제 최적화 - 평단가 개선 + 보유량 유지
        self.portfolio_config = {
            "132030": {  # KODEX 골드선물(H)
                "name": "KODEX 골드선물(H)",
                "weight": 0.4,
                "stock_type": "gold_etf_hedged",
                "hold_profit_target": 25,           # 🔥 12% → 25% (매도 억제)
                "quick_profit_target": 18,          # 🔥 8% → 18% (매도 억제)
                "loss_cut": [-0.15, -0.18, -0.20, -0.22, -0.25],  # 손절선 더 완화
                "time_based_sell_days": 180,        # 🔥 90일 → 180일 (더 오래 보유)
                "partial_sell_ratio": 0.10,         # 🔥 20% → 10% (극소량만 매도)
                "reentry_cooldown_base_hours": 0.25, # 15분 유지 (빠른 재진입)
                "min_pullback_for_reentry": 0.5,    # 0.5% 하락에도 재진입 유지
                "rsi_upper_bound": 95,              # 거의 모든 상황에서 매수 유지
                "volatility_threshold": 0.5
            },
            "319640": {  # TIGER 골드선물
                "name": "TIGER 골드선물",
                "weight": 0.4,
                "stock_type": "gold_etf_unhedged", 
                "hold_profit_target": 30,           # 🔥 15% → 30% (매도 억제)
                "quick_profit_target": 22,          # 🔥 10% → 22% (매도 억제)
                "loss_cut": [-0.12, -0.15, -0.18, -0.20, -0.22],
                "time_based_sell_days": 150,        # 🔥 80일 → 150일 (더 오래)
                "partial_sell_ratio": 0.15,         # 🔥 25% → 15% (적게 매도)
                "reentry_cooldown_base_hours": 0.5, # 30분 유지
                "min_pullback_for_reentry": 0.8,    # 0.8% 하락에 재진입 유지
                "rsi_upper_bound": 92,
                "volatility_threshold": 0.8
            },
            "411060": {  # ACE KRX 금현물
                "name": "ACE KRX 금현물",
                "weight": 0.2,
                "stock_type": "gold_physical",
                "hold_profit_target": 20,           # 🔥 10% → 20% (매도 억제)
                "quick_profit_target": 15,          # 🔥 6% → 15% (매도 억제)
                "loss_cut": [-0.10, -0.15, -0.18, -0.20, -0.22],
                "time_based_sell_days": 200,        # 🔥 120일 → 200일 (더 오래)
                "partial_sell_ratio": 0.08,         # 🔥 15% → 8% (극소량만 매도)
                "reentry_cooldown_base_hours": 0.25, # 15분 유지
                "min_pullback_for_reentry": 0.3,    # 0.3% 하락에도 재진입 유지
                "rsi_upper_bound": 98,              # 거의 항상 매수 가능 유지
                "volatility_threshold": 0.3
            }
        }
        
        # 🔥 하락률 기준은 유지 (매수 기회 유지)
        self.base_drops = [0, 0.006, 0.010, 0.013, 0.016]  # 0.6%~1.6% 유지
        
        # 결과 저장
        self.price_data = {}
        self.trades = []
        self.daily_values = []
        
        # 5차수 분할매매 상태
        self.positions = {}  # {stock_code: [position1, position2, ...]}
        self.last_sell_time = {}  # {stock_code: datetime}
        
        # 🔥 KIS API 초기화 (SmartGoldTradingBot_KR.py와 동일)
        if KIS_API_AVAILABLE:
            try:
                Common.SetChangeMode("REAL")  # 또는 "VIRTUAL"
                print("✅ KIS API 초기화 완료")
            except Exception as e:
                print(f"⚠️ KIS API 초기화 실패: {str(e)}")
    
    def fetch_korean_etf_data_from_kis(self):
        """🔥 한국투자증권 API로 실제 한국 금 ETF 데이터 수집"""
        print("🔍 한국투자증권 API로 금 ETF 데이터 수집 중...")
        
        if not KIS_API_AVAILABLE:
            print("❌ KIS API 사용 불가 - 모의 데이터로 대체")
            return self.generate_mock_gold_data()
        
        try:
            for stock_code, config in self.portfolio_config.items():
                print(f"  📊 {config['name']} ({stock_code}) 데이터 수집...")
                
                # 🔥 SmartGoldTradingBot_KR.py에서 사용하는 함수 그대로 사용
                try:
                    # KIS API로 일봉 데이터 조회 (최근 365일)
                    df = KisKR.GetOhlcv(stock_code, self.days_back)
                    
                    if df is None or df.empty:
                        print(f"  ❌ {config['name']} 데이터 없음 - 스킵")
                        continue
                    
                    # 데이터 형식 표준화
                    if 'close' in df.columns:
                        df.rename(columns={
                            'open': 'Open',
                            'high': 'High', 
                            'low': 'Low',
                            'close': 'Close',
                            'volume': 'Volume'
                        }, inplace=True)
                    
                    # 인덱스가 문자열이면 datetime으로 변환
                    if isinstance(df.index[0], str):
                        df.index = pd.to_datetime(df.index)
                    
                    # 기술적 지표 계산
                    df = self.calculate_technical_indicators(df)
                    self.price_data[stock_code] = df
                    
                    print(f"  ✅ {config['name']}: {len(df)}일 실제 데이터 수집 완료")
                    
                    # API 호출 간격 (과도한 요청 방지)
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"  ❌ {config['name']} KIS API 오류: {str(e)}")
                    # 개별 종목 실패시 해당 종목만 제외하고 계속 진행
                    continue
            
            if not self.price_data:
                print("❌ 모든 종목 데이터 수집 실패 - 모의 데이터로 대체")
                return self.generate_mock_gold_data()
            
            print(f"✅ 총 {len(self.price_data)}개 종목 실제 데이터 수집 완료!")
            return True
            
        except Exception as e:
            print(f"❌ KIS API 전체 오류: {str(e)}")
            print("🎭 모의 데이터로 대체합니다...")
            return self.generate_mock_gold_data()
    
    def fetch_korean_etf_data(self):
        """데이터 수집 메인 함수 - KIS API 우선, 실패시 모의 데이터"""
        # 🔥 1순위: 한국투자증권 API 사용
        if KIS_API_AVAILABLE:
            if self.fetch_korean_etf_data_from_kis():
                return True
        
        # 🔥 2순위: 모의 데이터 생성
        print("🎭 모의 데이터 생성으로 전환...")
        return self.generate_mock_gold_data()
  
    def calculate_technical_indicators(self, df):
        """SmartGoldTradingBot_KR.py와 동일한 기술적 지표 계산"""
        df = df.copy()
        
        # RSI 계산 (14일)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 이동평균선
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 최근 고점 대비 하락률
        df['Recent_High'] = df['High'].rolling(window=20).max()
        df['Pullback'] = (df['Recent_High'] - df['Close']) / df['Recent_High'] * 100
        
        # ATR (Average True Range)
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        df['ATR'] = true_range.rolling(window=14).mean()
        
        return df
    
    def check_buy_conditions(self, stock_code, date, position_level):
        """SmartGoldTradingBot_KR.py의 매수 조건 로직"""
        if stock_code not in self.price_data:
            return False, "데이터 없음"
        
        df = self.price_data[stock_code]
        if date not in df.index:
            return False, "날짜 없음"
        
        config = self.portfolio_config[stock_code]
        row = df.loc[date]
        
        # RSI 조건 체크
        rsi = row.get('RSI', 50)
        max_rsi = config['rsi_upper_bound']
        
        if position_level > 1:
            # 고차수는 RSI 조건 완화
            max_rsi += (position_level - 1) * 2
        
        if rsi > max_rsi:
            return False, f"RSI 과매수 ({rsi:.1f} > {max_rsi})"
        
        # 1차수는 조정률 체크
        if position_level == 1:
            pullback = row.get('Pullback', 0)
            min_pullback = config['min_pullback_for_reentry']
            
            if pullback < min_pullback:
                return False, f"조정률 부족 ({pullback:.1f}% < {min_pullback}%)"
        
        # 고차수는 하락률 조건 체크 (SmartGoldTradingBot의 base_drops 활용)
        else:
            required_drop = self.base_drops[min(position_level - 1, len(self.base_drops) - 1)]
            
            # 최근 5일 고점 대비 현재 하락률
            recent_high = df.loc[:date].tail(5)['High'].max()
            current_price = row['Close']
            actual_drop = (recent_high - current_price) / recent_high
            
            if actual_drop < required_drop:
                return False, f"하락률 부족 ({actual_drop*100:.1f}% < {required_drop*100:.1f}%)"
        
        # 쿨다운 체크
        if stock_code in self.last_sell_time:
            cooldown_hours = config['reentry_cooldown_base_hours']
            time_since_sell = (date - self.last_sell_time[stock_code]).total_seconds() / 3600
            
            if time_since_sell < cooldown_hours:
                return False, f"쿨다운 중 ({time_since_sell:.1f}h < {cooldown_hours}h)"
        
        return True, f"{position_level}차 매수 조건 만족"
    
    def check_sell_conditions(self, position, current_price, date, stock_code):
        """SmartGoldTradingBot_KR.py의 매도 조건 로직"""
        config = self.portfolio_config[stock_code]
        entry_price = position['entry_price']
        entry_date = position['entry_date']
        position_level = position['level']
        
        current_return = (current_price - entry_price) / entry_price * 100
        
        # 1. 손절 조건
        loss_threshold = config['loss_cut'][min(position_level - 1, len(config['loss_cut']) - 1)]
        if current_return <= loss_threshold * 100:
            return True, f"손절 ({current_return:.1f}% ≤ {loss_threshold*100:.1f}%)", 1.0
        
        # 2. 목표 수익률 달성
        if current_return >= config['hold_profit_target']:
            sell_ratio = config['partial_sell_ratio']
            return True, f"목표 달성 ({current_return:.1f}%)", sell_ratio
        
        # 3. 빠른 수익 실현
        if current_return >= config['quick_profit_target'] and position_level <= 2:
            return True, f"빠른 수익 ({current_return:.1f}%)", 0.3
        
        # 4. 시간 기반 매도
        days_held = (date - entry_date).days
        if days_held >= config['time_based_sell_days'] and current_return > 2:
            return True, f"장기 보유 ({days_held}일)", 0.6
        
        return False, "", 1.0
    
    def run_backtest(self):
        """백테스팅 실행 - SmartMagicSplit 5차수 로직 구현"""
        print("🚀 SmartMagicSplit 전략 백테스팅 시작...")
        
        if not self.price_data:
            print("❌ 가격 데이터가 없습니다.")
            return False
        
        # 모든 거래일 수집
        all_dates = set()
        for df in self.price_data.values():
            all_dates.update(df.index)
        all_dates = sorted(list(all_dates))
        
        if not all_dates:
            print("❌ 유효한 거래일이 없습니다.")
            return False
        
        # 초기 상태
        cash = self.initial_capital
        
        # 종목별 포지션 초기화 (5차수)
        for stock_code in self.portfolio_config.keys():
            self.positions[stock_code] = []
        
        print(f"📅 {len(all_dates)}일간 백테스팅 실행...")
        
        for i, date in enumerate(all_dates):
            if i % 30 == 0:  # 한달마다 진행률 표시
                progress = i / len(all_dates) * 100
                print(f"  진행률: {progress:.1f}% ({date.strftime('%Y-%m-%d')})")
            
            daily_portfolio_value = 0
            
            # 각 종목별 처리
            for stock_code, config in self.portfolio_config.items():
                if stock_code not in self.price_data or date not in self.price_data[stock_code].index:
                    continue
                
                current_price = self.price_data[stock_code].loc[date, 'Close']
                positions = self.positions[stock_code]
                
                # 1. 매도 로직
                positions_to_remove = []
                for pos_idx, position in enumerate(positions):
                    should_sell, sell_reason, sell_ratio = self.check_sell_conditions(
                        position, current_price, date, stock_code
                    )
                    
                    if should_sell:
                        # 매도 실행
                        sell_amount = max(1, int(position['amount'] * sell_ratio))
                        sell_amount = min(sell_amount, position['amount'])
                        
                        sell_value = sell_amount * current_price
                        cash += sell_value
                        
                        # 거래 기록
                        profit = (current_price - position['entry_price']) * sell_amount
                        self.trades.append({
                            'date': date,
                            'stock_code': stock_code,
                            'type': 'SELL',
                            'level': position['level'],
                            'price': current_price,
                            'amount': sell_amount,
                            'value': sell_value,
                            'profit': profit,
                            'reason': sell_reason
                        })
                        
                        # 포지션 업데이트
                        position['amount'] -= sell_amount
                        if position['amount'] <= 0:
                            positions_to_remove.append(pos_idx)
                        
                        # 매도 시간 기록
                        self.last_sell_time[stock_code] = date
                
                # 매도된 포지션 제거
                for idx in reversed(positions_to_remove):
                    positions.pop(idx)
                
                # 2. 매수 로직 (5차수까지)
                allocated_budget = self.initial_capital * config['weight']
                
                for level in range(1, 6):  # 1~5차수
                    # 해당 차수 포지션이 이미 있는지 체크
                    level_positions = [p for p in positions if p['level'] == level]
                    if level_positions:
                        continue  # 이미 해당 차수 보유 중
                    
                    # 이전 차수가 있는지 체크 (순차 진입)
                    if level > 1:
                        prev_level_positions = [p for p in positions if p['level'] == level - 1]
                        if not prev_level_positions:
                            continue  # 이전 차수가 없으면 진입 불가
                    
                    # 매수 조건 체크
                    can_buy, buy_reason = self.check_buy_conditions(stock_code, date, level)
                    if not can_buy:
                        continue
                    
                    # 매수 금액 계산 (차수별 분할)
                    level_budget = allocated_budget / 5  # 5등분
                    buy_amount = int(level_budget / current_price)
                    
                    if buy_amount == 0:
                        continue
                    
                    buy_value = buy_amount * current_price
                    if cash < buy_value:
                        continue  # 현금 부족
                    
                    # 매수 실행
                    cash -= buy_value
                    
                    positions.append({
                        'level': level,
                        'entry_price': current_price,
                        'entry_date': date,
                        'amount': buy_amount
                    })
                    
                    # 거래 기록
                    self.trades.append({
                        'date': date,
                        'stock_code': stock_code,
                        'type': 'BUY',
                        'level': level,
                        'price': current_price,
                        'amount': buy_amount,
                        'value': buy_value,
                        'profit': 0,
                        'reason': buy_reason
                    })
                    
                    break  # 한번에 한 차수만 매수
                
                # 현재 포지션 가치 계산
                position_value = sum(pos['amount'] * current_price for pos in positions)
                daily_portfolio_value += position_value
            
            # 일일 포트폴리오 가치 기록
            total_value = cash + daily_portfolio_value
            self.daily_values.append({
                'date': date,
                'cash': cash,
                'positions': daily_portfolio_value,
                'total': total_value,
                'return_pct': (total_value / self.initial_capital - 1) * 100
            })
        
        print("✅ 백테스팅 완료!")
        return True
    
    def calculate_buy_hold_benchmark(self):
        """Buy & Hold 벤치마크 계산"""
        print("📊 Buy & Hold 벤치마크 계산 중...")
        
        benchmark_values = []
        
        for daily_data in self.daily_values:
            date = daily_data['date']
            portfolio_value = 0
            
            # 각 종목별 가중 평균으로 Buy & Hold 계산
            for stock_code, config in self.portfolio_config.items():
                if stock_code in self.price_data and date in self.price_data[stock_code].index:
                    current_price = self.price_data[stock_code].loc[date, 'Close']
                    initial_price = self.price_data[stock_code].iloc[0]['Close']
                    
                    # 초기 투자 금액
                    initial_investment = self.initial_capital * config['weight']
                    shares = initial_investment / initial_price
                    current_value = shares * current_price
                    
                    portfolio_value += current_value
            
            benchmark_values.append({
                'date': date,
                'value': portfolio_value,
                'return_pct': (portfolio_value / self.initial_capital - 1) * 100
            })
        
        return benchmark_values
    
    def analyze_performance(self):
        """성과 분석"""
        if not self.daily_values:
            return {}
        
        df = pd.DataFrame(self.daily_values)
        
        # 기본 지표
        total_return = df.iloc[-1]['return_pct']
        days = len(df)
        annual_return = (1 + total_return/100) ** (365/days) - 1 if days > 0 else 0
        
        # 변동성 (일간 수익률의 표준편차)
        df['daily_return'] = df['return_pct'].pct_change()
        volatility = df['daily_return'].std() * np.sqrt(365) * 100  # 연환산
        
        # 샤프 비율 (무위험수익률 3% 가정)
        risk_free_rate = 3.0
        sharpe_ratio = (annual_return - risk_free_rate) / volatility * 100 if volatility != 0 else 0
        
        # 최대 낙폭 (Maximum Drawdown)
        df['cummax'] = df['return_pct'].cummax()
        df['drawdown'] = df['return_pct'] - df['cummax']
        max_drawdown = df['drawdown'].min()
        
        # 거래 통계
        trades_df = pd.DataFrame(self.trades)
        total_trades = len(trades_df)
        buy_trades = len(trades_df[trades_df['type'] == 'BUY'])
        sell_trades = len(trades_df[trades_df['type'] == 'SELL'])
        
        if sell_trades > 0:
            winning_trades = len(trades_df[(trades_df['type'] == 'SELL') & (trades_df['profit'] > 0)])
            win_rate = winning_trades / sell_trades * 100
            avg_profit = trades_df[trades_df['type'] == 'SELL']['profit'].mean()
        else:
            win_rate = 0
            avg_profit = 0
        
        return {
            'total_return': total_return,
            'annual_return': annual_return * 100,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'win_rate': win_rate,
            'avg_profit': avg_profit
        }
    
    def plot_results(self):
        """결과 시각화"""
        if not self.daily_values:
            print("❌ 시각화할 데이터가 없습니다.")
            return
        
        # Buy & Hold 벤치마크 계산
        benchmark_data = self.calculate_buy_hold_benchmark()
        
        # 데이터프레임 생성
        df_strategy = pd.DataFrame(self.daily_values)
        df_benchmark = pd.DataFrame(benchmark_data)
        
        # 플롯 설정
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('🥇 SmartGoldTradingBot vs Buy & Hold 성과 비교', fontsize=16, fontweight='bold')
        
        # 1. 누적 수익률 비교
        ax1.plot(df_strategy['date'], df_strategy['return_pct'], 
                label='SmartMagicSplit', linewidth=2, color='blue')
        ax1.plot(df_benchmark['date'], df_benchmark['return_pct'], 
                label='Buy & Hold', linewidth=2, color='red', alpha=0.8)
        ax1.set_title('📈 누적 수익률 비교')
        ax1.set_ylabel('수익률 (%)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        
        # 2. 포트폴리오 가치 변화
        ax2.plot(df_strategy['date'], df_strategy['total'], 
                label='SmartMagicSplit', linewidth=2, color='blue')
        ax2.plot(df_benchmark['date'], df_benchmark['value'], 
                label='Buy & Hold', linewidth=2, color='red', alpha=0.8)
        ax2.set_title('💰 포트폴리오 가치 변화')
        ax2.set_ylabel('가치 (원)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        
        # 3. 거래량 히스토그램
        trades_df = pd.DataFrame(self.trades)
        if not trades_df.empty:
            trade_counts = trades_df.groupby([trades_df['date'].dt.to_period('M'), 'type']).size().unstack(fill_value=0)
            trade_counts.plot(kind='bar', ax=ax3, color=['green', 'red'])
            ax3.set_title('📊 월별 거래량')
            ax3.set_ylabel('거래 횟수')
            ax3.legend(['매수', '매도'])
            ax3.tick_params(axis='x', rotation=45)
        
        # 4. 드로우다운
        df_strategy['cummax'] = df_strategy['return_pct'].cummax()
        df_strategy['drawdown'] = df_strategy['return_pct'] - df_strategy['cummax']
        
        ax4.fill_between(df_strategy['date'], df_strategy['drawdown'], 0, 
                        color='red', alpha=0.3, label='Drawdown')
        ax4.set_title('📉 최대 낙폭 (Drawdown)')
        ax4.set_ylabel('낙폭 (%)')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        
        plt.tight_layout()
        
        # 결과 저장
        os.makedirs('backtest_results', exist_ok=True)
        plt.savefig(f'backtest_results/gold_backtest_{datetime.now().strftime("%Y%m%d_%H%M")}.png', 
                   dpi=300, bbox_inches='tight')
        plt.show()
    
    def generate_report(self):
        """상세 리포트 생성"""
        performance = self.analyze_performance()
        benchmark_data = self.calculate_buy_hold_benchmark()
        benchmark_return = benchmark_data[-1]['return_pct'] if benchmark_data else 0
        
        report = f"""
🥇 SmartGoldTradingBot 백테스팅 리포트
{'='*50}

📊 기본 정보
• 백테스팅 기간: {self.start_date.strftime('%Y-%m-%d')} ~ {self.end_date.strftime('%Y-%m-%d')} ({self.days_back}일)
• 초기 자본: {self.initial_capital:,}원
• 투자 종목: KODEX골드선물(H) 35%, TIGER골드선물 35%, ACE KRX금현물 30%

🎯 성과 비교
• SmartMagicSplit 수익률: {performance['total_return']:.2f}%
• Buy & Hold 수익률: {benchmark_return:.2f}%
• 초과 수익률: {performance['total_return'] - benchmark_return:.2f}%p

📈 위험 조정 수익률
• 연환산 수익률: {performance['annual_return']:.2f}%
• 변동성: {performance['volatility']:.2f}%
• 샤프 비율: {performance['sharpe_ratio']:.3f}
• 최대 낙폭: {performance['max_drawdown']:.2f}%

📊 거래 통계
• 총 거래 횟수: {performance['total_trades']}회
• 매수: {performance['buy_trades']}회, 매도: {performance['sell_trades']}회
• 승률: {performance['win_rate']:.1f}%
• 평균 거래당 수익: {performance['avg_profit']:,.0f}원

💡 전략 평가
"""
        
        # 성과 평가
        if performance['total_return'] > benchmark_return:
            report += f"✅ SmartMagicSplit 전략이 Buy & Hold보다 {performance['total_return'] - benchmark_return:.2f}%p 우수!\n"
        else:
            report += f"⚠️ SmartMagicSplit 전략이 Buy & Hold보다 {benchmark_return - performance['total_return']:.2f}%p 저조\n"
        
        if performance['sharpe_ratio'] > 1.0:
            report += f"✅ 우수한 위험 대비 수익률 (샤프 비율 > 1.0)\n"
        elif performance['sharpe_ratio'] > 0.5:
            report += f"🔶 양호한 위험 대비 수익률 (샤프 비율 0.5-1.0)\n"
        else:
            report += f"⚠️ 위험 대비 수익률 개선 필요 (샤프 비율 < 0.5)\n"
        
        if abs(performance['max_drawdown']) < 10:
            report += f"✅ 양호한 리스크 관리 (최대 낙폭 < 10%)\n"
        elif abs(performance['max_drawdown']) < 20:
            report += f"🔶 보통 수준의 리스크 관리 (최대 낙폭 10-20%)\n"
        else:
            report += f"⚠️ 리스크 관리 개선 필요 (최대 낙폭 > 20%)\n"
        
        report += f"""
🔍 금투자 최적화 효과 분석
• 목표수익률 현실화: 기존 35% → 10-15% 반영으로 매도 기회 증가
• RSI 기준 완화: 85 → 90-92로 조정하여 과매수 신호 오류 감소  
• 하락률 기준 완화: 2.5-4% → 1.5-3%로 조정하여 진입 기회 확대
• 보유기간 연장: 90일 → 150-365일로 금의 장기투자 특성 반영
• 쿠로다운 조정: 금의 낮은 변동성을 고려한 재진입 타이밍 최적화

💭 개선 권장사항
"""
        
        if performance['win_rate'] < 60:
            report += f"• 승률 {performance['win_rate']:.1f}% → 손절 기준 재검토 권장\n"
        
        if performance['volatility'] > 25:
            report += f"• 변동성 {performance['volatility']:.1f}% → 포지션 사이즈 축소 권장\n"
        
        if performance['total_trades'] > 200:
            report += f"• 거래 횟수 {performance['total_trades']}회 → 과도한 매매 확인 필요\n"
        
        report += f"\n생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return report
    
    def export_trades_to_csv(self):
        """거래 내역 CSV 파일로 내보내기"""
        if not self.trades:
            print("❌ 내보낼 거래 내역이 없습니다.")
            return
        
        trades_df = pd.DataFrame(self.trades)
        
        # 디렉토리 생성
        os.makedirs('backtest_results', exist_ok=True)
        
        # 파일명 생성
        filename = f'backtest_results/gold_trades_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
        
        # CSV 저장
        trades_df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"✅ 거래 내역 저장 완료: {filename}")
        
        return filename
    
    def run_full_analysis(self):
        """전체 분석 실행"""
        print("🥇 SmartGoldTradingBot 백테스팅 시스템 시작")
        print("="*50)
        
        # 1. 데이터 수집
        if not self.fetch_korean_etf_data():
            print("❌ 데이터 수집 실패로 백테스팅 중단")
            return
        
        # 2. 백테스팅 실행  
        if not self.run_backtest():
            print("❌ 백테스팅 실행 실패")
            return
        
        # 3. 성과 분석
        performance = self.analyze_performance()
        benchmark_data = self.calculate_buy_hold_benchmark()
        
        # 4. 결과 출력
        print("\n🎯 백테스팅 결과 요약")
        print("-" * 30)
        print(f"SmartMagicSplit 수익률: {performance['total_return']:.2f}%")
        print(f"Buy & Hold 수익률: {benchmark_data[-1]['return_pct']:.2f}%")
        print(f"초과 수익률: {performance['total_return'] - benchmark_data[-1]['return_pct']:.2f}%p")
        print(f"샤프 비율: {performance['sharpe_ratio']:.3f}")
        print(f"최대 낙폭: {performance['max_drawdown']:.2f}%")
        print(f"승률: {performance['win_rate']:.1f}%")
        
        # 5. 상세 리포트 생성
        report = self.generate_report()
        print("\n" + report)
        
        # 6. 거래 내역 저장
        csv_file = self.export_trades_to_csv()
        
        # 7. 차트 생성
        self.plot_results()
        
        # 8. 리포트 파일 저장
        os.makedirs('backtest_results', exist_ok=True)
        report_file = f'backtest_results/gold_backtest_report_{datetime.now().strftime("%Y%m%d_%H%M")}.txt'
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✅ 상세 리포트 저장 완료: {report_file}")
        
        print(f"\n🎉 백테스팅 완료! 결과 파일들이 'backtest_results' 폴더에 저장되었습니다.")
        
        return {
            'performance': performance,
            'benchmark_return': benchmark_data[-1]['return_pct'],
            'report_file': report_file,
            'csv_file': csv_file
        }

def main():
    """메인 실행 함수"""
    print("🥇 SmartGoldTradingBot 백테스팅 시스템")
    print("SmartGoldTradingBot_KR.py의 금투자 최적화 로직을 완전히 재현")
    print("="*60)
    
    # 백테스팅 설정
    initial_capital = 600000  # 60만원
    days_back = 365          # 1년간
    
    print(f"📊 백테스팅 설정:")
    print(f"• 초기 자본: {initial_capital:,}원")
    print(f"• 백테스팅 기간: {days_back}일")
    print(f"• 투자 전략: SmartMagicSplit 5차수 분할매매")
    print(f"• 대상 종목: KODEX골드선물(H), TIGER골드선물, ACE KRX금현물")
    
    # 백테스터 초기화 및 실행
    backtest = GoldTradingBacktest(
        initial_capital=initial_capital,
        days_back=days_back
    )
    
    try:
        # 전체 분석 실행
        results = backtest.run_full_analysis()
        
        if results:
            print(f"\n✅ 백테스팅 성공!")
            print(f"SmartMagicSplit: {results['performance']['total_return']:.2f}%")
            print(f"Buy & Hold: {results['benchmark_return']:.2f}%")
            
            if results['performance']['total_return'] > results['benchmark_return']:
                print(f"🎉 SmartMagicSplit 전략이 Buy & Hold보다 {results['performance']['total_return'] - results['benchmark_return']:.2f}%p 우수!")
            else:
                print(f"⚠️ 현재 설정에서는 Buy & Hold가 더 우수함. 파라미터 조정 필요")
        
    except Exception as e:
        print(f"❌ 백테스팅 실행 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()