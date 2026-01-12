#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 기반 수익보호 시스템 v3.1 - 뉴스감성+취약성분석+프롬프트개선
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[v3.1 신규 기능]
✅ 7개 봇 뉴스 캐시 통합 (API 비용 0원)
✅ 포트폴리오 취약성 분석 (+5~20% 구간)
✅ 과거 유사 사례 자동 검색 (Few-shot)
✅ 17단계 프롬프트 가중치 명시
✅ VIX 구간별 전략 가이드

[v3.0 기존 기능]
✅ 오예측 패턴 자동 감지
✅ 구조화된 학습 피드백
✅ 신뢰도 기반 자동 조정
✅ 상세 학습 리포트 생성

작성: NamSu & Claude
버전: 3.1
최종 수정: 2025-01-12
"""

import os
import sys
import json
import logging
import pickle
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
import yfinance as yf

# 🔥 KisUS 모듈 import
import KIS_Common as Common
import KIS_API_Helper_US as KisUS
from api_resilience import retry_manager, SafeKisUS, set_logger as set_resilience_logger

################################### 로깅 설정 시작 ##################################
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

formatter = logging.Formatter(
    '[%(levelname)s] %(asctime)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)
logger.setLevel(log_level)

log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

if not logger.handlers:
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    file_handler = logging.FileHandler(
        os.path.join(log_dir, 'ai_profit_protector.log'),
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
################################### 로깅 설정 끝 ##################################


# 🔥 API 초기화
Common.SetChangeMode("REAL")
logger.info("✅ 미국주식 API 초기화 완료")

try:
    KisUS.set_logger(logger)
    Common.set_logger(logger)
    set_resilience_logger(logger)
    logger.info("✅ 모든 모듈에 로거 전달 완료")
except Exception as e:
    logger.warning(f"⚠️ 모듈에 로거 전달 중 오류: {str(e)}")

# 🔥 Discord 모듈
try:
    import discord_alert
    discord_alert.set_logger(logger)
    DISCORD_AVAILABLE = True
    logger.info("✅ discord_alert 모듈 로드 완료")
except ImportError:
    DISCORD_AVAILABLE = False
    logger.warning("⚠️ discord_alert 모듈 없음")

# 🔥 경제 캘린더 모듈
try:
    import auto_economic_calendar
    auto_economic_calendar.set_logger(logger)
    ECONOMIC_CALENDAR_AVAILABLE = True
    logger.info("📅 자동 경제 캘린더 모듈 로드 완료")
except ImportError:
    ECONOMIC_CALENDAR_AVAILABLE = False
    logger.warning("⚠️ 경제 캘린더 모듈 없음")


class AIProfitProtector:
    """AI 기반 수익보호 시스템 v3.1 - 뉴스+취약성+프롬프트 개선"""
    
    def __init__(self):
        self.output_file = "profit_protection.json"
        self.history_file = "ai_decision_history.json"
        self.data_directory = os.path.dirname(os.path.abspath(__file__))
        
        self.history_dir = os.path.join(self.data_directory, 'history')
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
        
        self.real_account_budget = 5010
    
    def run_analysis(self):
        """메인 분석 실행 - v3.1 뉴스+취약성 통합"""
        try:
            logger.info("=" * 80)
            logger.info("🤖 AI 수익보호 시스템 v3.1 분석 시작 (뉴스+취약성 통합)")
            logger.info("=" * 80)
            
            # 1. 데이터 수집
            logger.info("📊 Step 1: 강화된 데이터 수집 중...")
            portfolio_data = self.collect_portfolio_data()
            market_data = self.collect_market_data()
            sentiment_data = self.collect_sentiment_data()
            sector_data = self.collect_sector_rotation_data()
            bond_data = self.collect_bond_market_data()
            safe_haven_data = self.collect_safe_haven_data()
            bitcoin_data = self.collect_bitcoin_sentiment()
            breadth_data = self.collect_market_breadth_data()
            vix_structure_data = self.collect_vix_term_structure()
            past_decisions = self.collect_past_decisions()
            
            # 🔥 v3.1 신규: 뉴스 감성 + 포트폴리오 취약성
            news_sentiment = self.collect_news_sentiment_all_bots()
            portfolio_vuln = self.analyze_portfolio_vulnerability(portfolio_data)
            
            # 2. 자동 outcome 업데이트
            logger.info("🔄 Step 2: 과거 판단 결과 자동 검증 중...")
            self.auto_update_outcomes()
            
            # 3. 오예측 패턴 감지 (v3.0)
            logger.info("🔍 Step 3: 오예측 패턴 자동 감지 중...")
            error_patterns = self.detect_error_patterns()
            
            # 4. 학습 피드백 생성 (v3.0)
            logger.info("🧠 Step 4: 학습 피드백 생성 중...")
            learning_feedback = self.generate_learning_feedback(past_decisions, error_patterns)
            
            # 5. 학습 리포트 생성 (v3.0)
            logger.info("📊 Step 5: 상세 학습 리포트 생성 중...")
            self.generate_learning_report(past_decisions, error_patterns)
            
            # 6. AI 호출 (뉴스+취약성 포함) 🔥
            logger.info("🤖 Step 6: AI 분석 중 (뉴스+취약성 반영)...")
            ai_decision = self.ask_ai_with_enhanced_prompt(
                portfolio_data, market_data, sentiment_data,
                sector_data, bond_data, safe_haven_data,
                bitcoin_data, breadth_data, vix_structure_data,
                past_decisions, learning_feedback,
                news_sentiment, portfolio_vuln  # 🔥 v3.1 추가
            )
            
            # 7. 결과 검증
            logger.info("✅ Step 7: 결과 검증 중...")
            validated_decision = self.validate_decision_enhanced(ai_decision, market_data)
            
            # 8. 신뢰도 기반 자동 조정 (v3.0)
            logger.info("🔧 Step 8: 신뢰도 기반 자동 조정 중...")
            accuracy = past_decisions.get('accuracy_rate', 100) if past_decisions else 100
            validated_decision = self.apply_confidence_adjustment(
                validated_decision, accuracy, error_patterns or {}
            )
            
            # 9. 저장
            logger.info("💾 Step 9: 결과 저장 중...")
            self.save_protection_decision(validated_decision)
            self.save_decision_to_history(validated_decision)
            
            # 10. 알림
            if validated_decision['risk_level'] in ['CRITICAL', 'HIGH']:
                self.send_discord_alert(validated_decision)
            
            logger.info("=" * 80)
            logger.info("✅ AI 수익보호 분석 v3.1 완료 (뉴스+취약성 통합)")
            logger.info("=" * 80)
            
            return validated_decision
            
        except Exception as e:
            logger.error(f"❌ AI 수익보호 분석 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 데이터 수집 함수들
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def collect_portfolio_data(self):
        """포트폴리오 데이터 수집"""
        try:
            logger.info("📊 포트폴리오 데이터 수집 시작")
            
            # 브로커 보유 종목 조회
            broker_holdings = {}
            stock_value = 0
            positions = []
            
            try:
                stock_list = KisUS.GetMyStockList("USD")
                if stock_list and isinstance(stock_list, list):
                    valid_stocks = [s for s in stock_list if isinstance(s, dict)]
                    logger.info(f"✅ 브로커 보유 종목: {len(valid_stocks)}개")
                    
                    for stock in valid_stocks:
                        stock_code = stock.get('StockCode', '')
                        if stock_code:
                            eval_amt = float(stock.get('StockNowMoney', 0))
                            avg_price = float(stock.get('StockAvgPrice', 0))
                            current_price = float(stock.get('StockNowPrice', 0))
                            pnl = float(stock.get('StockRevenMoney', 0))
                            
                            stock_value += eval_amt
                            
                            # 수익률 계산
                            profit_pct = 0
                            if avg_price > 0:
                                profit_pct = ((current_price - avg_price) / avg_price) * 100
                            
                            broker_holdings[stock_code] = {
                                'amount': int(stock.get('StockAmt', 0)),
                                'avg_price': avg_price,
                                'current_price': current_price,
                                'eval_amt': eval_amt,
                                'pnl': pnl,
                                'profit_pct': profit_pct
                            }
                            
                            positions.append({
                                'stock_code': stock_code,
                                'eval_amt': eval_amt,
                                'profit_pct': profit_pct
                            })
            except Exception as e:
                logger.warning(f"⚠️ 브로커 종목 데이터 로드 오류: {str(e)}")
                broker_holdings = {}
            
            # 현금 조회
            current_cash = 0
            total_assets = 0
            try:
                balance = KisUS.GetBalance("USD")
                if balance and isinstance(balance, dict):
                    current_cash = float(balance.get('RemainMoney', 0))
                    total_assets = float(balance.get('TotalMoney', 0))
                    
                    if total_assets <= 0:
                        total_assets = stock_value + current_cash
            except Exception as e:
                logger.warning(f"⚠️ 현금 조회 오류: {str(e)}")
                total_assets = stock_value + current_cash
            
            # 수익률 계산
            initial_budget = self.real_account_budget
            total_return = total_assets - initial_budget
            total_return_pct = (total_return / initial_budget * 100) if initial_budget > 0 else 0
            
            # 현금 비율
            cash_ratio = current_cash / total_assets if total_assets > 0 else 0
            
            result = {
                'total': {
                    'total_value': total_assets,
                    'current_cash': current_cash,
                    'stock_value': stock_value,
                    'cash_ratio': cash_ratio,
                    'total_return': total_return,
                    'total_return_pct': total_return_pct,
                    'position_count': len(broker_holdings)
                },
                'positions': positions,
                'holdings': broker_holdings
            }
            
            logger.info(f"📊 포트폴리오: ${total_assets:.0f} (현금 {cash_ratio*100:.1f}%, 수익 {total_return_pct:.2f}%)")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 포트폴리오 데이터 수집 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def collect_market_data(self):
        """시장 데이터 수집"""
        try:
            logger.info("📈 시장 데이터 수집 시작")
            
            spy_price = SafeKisUS.safe_get_current_price("SPY")
            if not spy_price or spy_price <= 0:
                return self.get_default_market_data()
            
            try:
                spy_data = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 2)
                if spy_data is not None and len(spy_data) >= 2:
                    spy_prev = float(spy_data['close'].iloc[-2])
                    spy_change = ((spy_price / spy_prev) - 1) * 100
                else:
                    spy_change = 0.0
            except:
                spy_change = 0.0
            
            vix_price = SafeKisUS.safe_get_current_price("VIXY")
            if not vix_price or vix_price <= 0:
                vix_price = 15.0
            
            if vix_price < 12:
                vix_level = '매우 안정'
            elif vix_price < 18:
                vix_level = '안정'
            elif vix_price < 25:
                vix_level = '경계'
            else:
                vix_level = '공포'
            
            result = {
                'spy': {
                    'current_price': spy_price,
                    'change_pct': spy_change,
                    'status': 'bullish' if spy_change > 1 else 'bearish' if spy_change < -1 else 'neutral'
                },
                'vix': {
                    'current_price': vix_price,
                    'change_pct': 0.0,
                    'level': vix_level
                },
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"📈 SPY: ${spy_price:.2f} ({spy_change:+.2f}%)")
            logger.info(f"📊 VIXY: ${vix_price:.2f} ({vix_level})")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 시장 데이터 수집 오류: {str(e)}")
            return self.get_default_market_data()
    
    def get_default_market_data(self):
        """기본 시장 데이터"""
        return {
            'spy': {'current_price': 480.0, 'change_pct': 0.0, 'status': 'neutral'},
            'vix': {'current_price': 15.0, 'change_pct': 0.0, 'level': '안정'},
            'timestamp': datetime.now().isoformat()
        }
    
    def collect_sentiment_data(self):
        """경제 이벤트 데이터 수집"""
        try:
            upcoming_events = []
            
            if ECONOMIC_CALENDAR_AVAILABLE:
                try:
                    updater = auto_economic_calendar.AutoEconomicCalendarUpdater()
                    calendar_data = updater.update_calendar_if_needed()
                    
                    if calendar_data:
                        upcoming_events = auto_economic_calendar.get_upcoming_events_from_calendar(
                            calendar_data, days_ahead=7
                        )
                        logger.info(f"📅 경제 캘린더: {len(upcoming_events)}개 이벤트")
                except Exception as e:
                    logger.warning(f"⚠️ 경제 캘린더 오류: {str(e)}")
            
            return {
                'upcoming_events': [
                    {
                        'date': evt.get('date_str', ''),
                        'event': evt.get('event', ''),
                        'importance': evt.get('importance', 'medium'),
                        'days_ahead': evt.get('days_ahead', 0)
                    }
                    for evt in upcoming_events[:5]
                ],
                'event_count': len(upcoming_events)
            }
            
        except Exception as e:
            logger.error(f"❌ 감성 데이터 수집 오류: {str(e)}")
            return {'upcoming_events': [], 'event_count': 0}

    def collect_sector_rotation_data(self):
        """섹터 로테이션 데이터"""
        try:
            sectors = {
                'XLK': '기술',
                'XLE': '에너지',
                'XLF': '금융',
                'XLV': '헬스케어',
                'XLI': '산업재'
            }
            
            sector_performance = {}
            for ticker, name in sectors.items():
                try:
                    data = yf.download(ticker, period='5d', progress=False)
                    if len(data) >= 2:
                        change = ((data['Close'].iloc[-1] / data['Close'].iloc[0]) - 1) * 100
                        sector_performance[name] = round(change, 2)
                except:
                    pass
            
            return {'sectors': sector_performance}
        except:
            return None

    def collect_bond_market_data(self):
        """채권 시장 데이터"""
        try:
            tlt_price = SafeKisUS.safe_get_current_price("TLT")
            if not tlt_price or tlt_price <= 0:
                return None
            
            try:
                tlt_data = SafeKisUS.safe_get_ohlcv_new("TLT", "D", 6)
                if tlt_data is not None and len(tlt_data) >= 6:
                    tlt_5d_ago = float(tlt_data['close'].iloc[0])
                    tlt_change = ((tlt_price / tlt_5d_ago) - 1) * 100
                else:
                    tlt_change = 0.0
            except:
                tlt_change = 0.0
            
            if tlt_change > 2:
                signal = 'RISK_OFF'
            elif tlt_change < -2:
                signal = 'RISK_ON'
            else:
                signal = 'NEUTRAL'
            
            return {
                'tlt_price': tlt_price,
                'tlt_change_5d': tlt_change,
                'signal': signal
            }
        except:
            return None

    def collect_safe_haven_data(self):
        """안전자산 데이터"""
        try:
            gld_price = SafeKisUS.safe_get_current_price("GLD")
            uup_price = SafeKisUS.safe_get_current_price("UUP")
            
            if not gld_price or gld_price <= 0:
                gld_price = 185.0
            if not uup_price or uup_price <= 0:
                uup_price = 28.0
            
            try:
                gld_data = SafeKisUS.safe_get_ohlcv_new("GLD", "D", 6)
                if gld_data is not None and len(gld_data) >= 6:
                    gld_5d_ago = float(gld_data['close'].iloc[0])
                    gld_change = ((gld_price / gld_5d_ago) - 1) * 100
                else:
                    gld_change = 0.0
            except:
                gld_change = 0.0
            
            if gld_change > 1.5:
                signal = 'FEAR'
            else:
                signal = 'NEUTRAL'
            
            return {
                'gold_price': gld_price,
                'gold_change_5d': gld_change,
                'dollar_price': uup_price,
                'signal': signal
            }
        except:
            return None

    def collect_bitcoin_sentiment(self):
        """비트코인 심리"""
        try:
            data = yf.download('BTC-USD', period='5d', progress=False)
            if len(data) >= 2:
                btc_change = ((data['Close'].iloc[-1] / data['Close'].iloc[0]) - 1) * 100
                
                if btc_change > 5:
                    signal = 'GREED'
                elif btc_change < -5:
                    signal = 'FEAR'
                else:
                    signal = 'NEUTRAL'
                
                return {
                    'btc_change_5d': round(btc_change, 2),
                    'signal': signal
                }
        except:
            return None

    def collect_market_breadth_data(self):
        """시장 내부 강도"""
        try:
            spy_data = SafeKisUS.safe_get_ohlcv_new("SPY", "D", 11)
            if spy_data is None or len(spy_data) < 11:
                return None
            
            changes = []
            for i in range(1, len(spy_data)):
                prev = float(spy_data['close'].iloc[i-1])
                curr = float(spy_data['close'].iloc[i])
                if prev > 0:
                    changes.append(1 if curr > prev else -1)
            
            breadth_ratio = (sum(1 for x in changes if x > 0) / len(changes)) if changes else 0.5
            
            if breadth_ratio >= 0.7:
                signal = 'STRONG'
            elif breadth_ratio >= 0.5:
                signal = 'NEUTRAL'
            else:
                signal = 'WEAK'
            
            return {
                'up_days': sum(1 for x in changes if x > 0),
                'total_days': len(changes),
                'breadth_ratio': breadth_ratio,
                'signal': signal
            }
        except:
            return None
    
    def collect_vix_term_structure(self):
        """VIX 기간 구조"""
        try:
            vixy_current = SafeKisUS.safe_get_current_price("VIXY")
            if not vixy_current or vixy_current <= 0:
                return None
            
            vixy_data = SafeKisUS.safe_get_ohlcv_new("VIXY", "D", 6)
            if vixy_data is None or len(vixy_data) < 6:
                return None
            
            vixy_6d_ago = float(vixy_data['close'].iloc[0])
            vixy_change = ((vixy_current / vixy_6d_ago) - 1) * 100
            
            if vixy_change > 10:
                signal = 'FEAR_SPIKE'
            elif vixy_change > 5:
                signal = 'FEAR_RISING'
            elif vixy_change < -5:
                signal = 'FEAR_EASING'
            else:
                signal = 'NEUTRAL'
            
            return {
                'vix_spot': vixy_current,
                'vxx_change_5d': vixy_change,
                'signal': signal
            }
        except:
            return None
    
    def collect_past_decisions(self):
        """과거 AI 판단 이력"""
        try:
            history_path = os.path.join(self.history_dir, self.history_file)
            if not os.path.exists(history_path):
                return None
            
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            if not history.get('decisions'):
                return None
            
            recent = history['decisions'][-10:]
            
            # 검증된 판단 개수
            verified = [d for d in history['decisions'] if d.get('outcome_3days')]
            correct = [d for d in verified if d['outcome_3days'].get('accuracy') == 'CORRECT']
            
            accuracy_rate = (len(correct) / len(verified) * 100) if verified else 0
            
            return {
                'recent_decisions': recent,
                'verified_count': len(verified),
                'correct_count': len(correct),
                'accuracy_rate': accuracy_rate
            }
        except:
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.1 신규 함수: 7개 봇 뉴스 캐시 통합
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def collect_news_sentiment_all_bots(self):
        """7개 봇의 뉴스 캐시 파일에서 감성 분석 결과 통합 (API 비용 0원)"""
        try:
            logger.info("📰 7개 봇 뉴스 캐시 파일 읽기 시작")
            
            # 7개 봇의 타겟 종목 정의 (섹터별)
            bot_configs = {
                '원전': {
                    'stocks': ['CCJ', 'LEU', 'BWXT'],
                    'library': 'finhub'
                },
                'AI': {
                    'stocks': ['NVDA', 'VRT', 'PLTR'],
                    'library': 'finhub'
                },
                'BigTech': {
                    'stocks': ['MSFT', 'GOOGL', 'META', 'AMZN'],
                    'library': 'finhub'
                },
                'Future': {
                    'stocks': ['IONQ', 'RGTI', 'QUBT'],
                    'library': 'futuretech'
                },
                'Silver': {
                    'stocks': ['PAAS', 'AG', 'HL'],
                    'library': 'finhub'
                },
                '반도체': {
                    'stocks': ['TSM', 'ASML', 'AMAT', 'LRCX'],
                    'library': 'semiconductor'
                },
                'Mining': {
                    'stocks': ['FCX', 'ALB', 'MP'],
                    'library': 'mining'
                }
            }
            
            sector_sentiment = {}
            total_negative = 0
            total_positive = 0
            total_neutral = 0
            total_stocks = 0
            
            cache_dir = "gpt_cache"
            
            # 섹터별 뉴스 감성 분석
            for sector, config in bot_configs.items():
                stocks = config['stocks']
                
                try:
                    # 캐시 키 생성 (각 라이브러리 방식 동일)
                    stock_codes = sorted(stocks)
                    hash_string = '_'.join(stock_codes)
                    cache_key = hashlib.md5(hash_string.encode()).hexdigest()[:8]
                    
                    # 캐시 파일 경로
                    cache_file = os.path.join(cache_dir, f"gpt_analysis_{cache_key}.pkl")
                    
                    if not os.path.exists(cache_file):
                        logger.warning(f"  ⚠️ {sector}: 캐시 파일 없음")
                        sector_sentiment[sector] = {
                            'negative': 0, 'positive': 0, 'neutral': len(stocks),
                            'risk_level': 'UNKNOWN', 'negative_ratio': 0,
                            'cache_status': 'NOT_FOUND'
                        }
                        total_neutral += len(stocks)
                        total_stocks += len(stocks)
                        continue
                    
                    # 캐시 파일 읽기
                    with open(cache_file, 'rb') as f:
                        cache_data = pickle.load(f)
                    
                    # 캐시 유효성 확인 (240분)
                    cache_time = cache_data.get('timestamp')
                    if cache_time:
                        age = datetime.now() - cache_time
                        if age > timedelta(minutes=240):
                            logger.warning(f"  ⚠️ {sector}: 캐시 만료 ({age.total_seconds()/60:.1f}분)")
                            sector_sentiment[sector] = {
                                'negative': 0, 'positive': 0, 'neutral': len(stocks),
                                'risk_level': 'EXPIRED', 'negative_ratio': 0,
                                'cache_status': 'EXPIRED'
                            }
                            total_neutral += len(stocks)
                            total_stocks += len(stocks)
                            continue
                    
                    # 분석 결과 파싱
                    analysis_data = cache_data.get('analysis', {})
                    
                    negative_count = 0
                    positive_count = 0
                    neutral_count = 0
                    
                    # 라이브러리별 데이터 구조 처리
                    if config['library'] == 'futuretech':
                        # futuretech: {ticker: {decision, percentage, ...}}
                        for ticker in stocks:
                            sentiment = analysis_data.get(ticker, {})
                            decision = sentiment.get('decision', 'NEUTRAL')
                            
                            if decision == 'NEGATIVE':
                                negative_count += 1
                            elif decision == 'POSITIVE':
                                positive_count += 1
                            else:
                                neutral_count += 1
                    else:
                        # finhub/semiconductor/mining: {stocks: {company_name: {analysis: {...}}}}
                        stocks_data = analysis_data.get('stocks', {})
                        
                        for company_name, data in stocks_data.items():
                            ticker = data.get('ticker', '')
                            if ticker not in stocks:
                                continue
                            
                            analysis = data.get('analysis', {})
                            decision = analysis.get('decision', 'NEUTRAL')
                            
                            if decision == 'NEGATIVE':
                                negative_count += 1
                            elif decision == 'POSITIVE':
                                positive_count += 1
                            else:
                                neutral_count += 1
                    
                    stock_count = len(stocks)
                    negative_ratio = negative_count / stock_count if stock_count > 0 else 0
                    
                    # 섹터 위험도 판정
                    if negative_ratio >= 0.67:  # 2/3 이상 부정
                        risk = 'HIGH_RISK'
                    elif negative_ratio >= 0.5:  # 절반 이상 부정
                        risk = 'RISK'
                    elif negative_count == 0 and positive_count >= stock_count * 0.5:
                        risk = 'POSITIVE'
                    else:
                        risk = 'NEUTRAL'
                    
                    sector_sentiment[sector] = {
                        'negative': negative_count,
                        'positive': positive_count,
                        'neutral': neutral_count,
                        'risk_level': risk,
                        'negative_ratio': round(negative_ratio * 100, 1),
                        'cache_status': 'VALID',
                        'cache_age_minutes': round(age.total_seconds() / 60, 1) if cache_time else 0
                    }
                    
                    total_negative += negative_count
                    total_positive += positive_count
                    total_neutral += neutral_count
                    total_stocks += stock_count
                    
                    logger.info(f"  📊 {sector}: {risk} (부정 {negative_ratio*100:.0f}%)")
                    
                except Exception as e:
                    logger.warning(f"  ⚠️ {sector} 캐시 읽기 실패: {str(e)}")
                    sector_sentiment[sector] = {
                        'negative': 0, 'positive': 0, 'neutral': len(stocks),
                        'risk_level': 'ERROR', 'negative_ratio': 0,
                        'cache_status': 'ERROR'
                    }
                    total_neutral += len(stocks)
                    total_stocks += len(stocks)
            
            # 전체 종합
            overall_sentiment = {
                'negative_ratio': round(total_negative / total_stocks * 100, 1) if total_stocks > 0 else 0,
                'positive_ratio': round(total_positive / total_stocks * 100, 1) if total_stocks > 0 else 0,
                'neutral_ratio': round(total_neutral / total_stocks * 100, 1) if total_stocks > 0 else 0
            }
            
            # 고위험 섹터 카운트
            high_risk_sectors = [s for s, data in sector_sentiment.items() 
                                if data['risk_level'] in ['HIGH_RISK', 'RISK']]
            
            # 유효 캐시 비율
            valid_caches = sum(1 for data in sector_sentiment.values() 
                              if data.get('cache_status') == 'VALID')
            cache_validity = round(valid_caches / len(bot_configs) * 100, 1)
            
            logger.info(f"📰 뉴스 감성 종합: 부정 {overall_sentiment['negative_ratio']}%, "
                       f"고위험 섹터 {len(high_risk_sectors)}개")
            logger.info(f"💾 캐시 유효율: {cache_validity}% ({valid_caches}/{len(bot_configs)})")
            
            return {
                'sectors': sector_sentiment,
                'overall': overall_sentiment,
                'high_risk_count': len(high_risk_sectors),
                'high_risk_sectors': high_risk_sectors,
                'cache_validity': cache_validity,
                'api_cost': 0.0  # 캐시 사용으로 API 비용 0
            }
            
        except Exception as e:
            logger.error(f"❌ 뉴스 캐시 읽기 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.1 신규 함수: 포트폴리오 취약성 분석
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def analyze_portfolio_vulnerability(self, portfolio_data):
        """포트폴리오 취약 구간 상세 분석"""
        try:
            logger.info("🔍 포트폴리오 취약성 분석 시작")
            
            if not portfolio_data or 'positions' not in portfolio_data:
                return None
            
            positions = portfolio_data['positions']
            
            # 수익 구간별 분류
            vulnerable_positions = []      # +5% ~ +20% (트레일링 스톱 미작동)
            high_profit_protected = []     # +50% 이상 (트레일링 스톱 작동)
            medium_profit = []             # +20% ~ +50%
            low_profit = []                # 0% ~ +5%
            loss_positions = []            # -5% 이하
            minor_loss = []                # -5% ~ 0%
            
            total_value = 0
            vulnerable_value = 0
            
            for pos in positions:
                profit_pct = pos.get('profit_pct', 0)
                eval_amt = pos.get('eval_amt', 0)
                stock_code = pos.get('stock_code', 'UNKNOWN')
                
                total_value += eval_amt
                
                if profit_pct >= 50:
                    high_profit_protected.append({
                        'stock': stock_code,
                        'profit_pct': profit_pct,
                        'value': eval_amt
                    })
                elif profit_pct >= 20:
                    medium_profit.append({
                        'stock': stock_code,
                        'profit_pct': profit_pct,
                        'value': eval_amt
                    })
                elif profit_pct >= 5:
                    vulnerable_positions.append({
                        'stock': stock_code,
                        'profit_pct': profit_pct,
                        'value': eval_amt
                    })
                    vulnerable_value += eval_amt
                elif profit_pct >= 0:
                    low_profit.append({
                        'stock': stock_code,
                        'profit_pct': profit_pct,
                        'value': eval_amt
                    })
                elif profit_pct >= -5:
                    minor_loss.append({
                        'stock': stock_code,
                        'profit_pct': profit_pct,
                        'value': eval_amt
                    })
                else:
                    loss_positions.append({
                        'stock': stock_code,
                        'profit_pct': profit_pct,
                        'value': eval_amt
                    })
            
            # 취약 구간 비율 계산
            vulnerable_ratio = vulnerable_value / total_value if total_value > 0 else 0
            
            # 위험도 평가
            if vulnerable_ratio >= 0.4:  # 40% 이상
                vulnerability_level = 'HIGH'
            elif vulnerable_ratio >= 0.25:  # 25% 이상
                vulnerability_level = 'MEDIUM'
            else:
                vulnerability_level = 'LOW'
            
            result = {
                'vulnerable_positions': vulnerable_positions,
                'vulnerable_count': len(vulnerable_positions),
                'vulnerable_ratio': round(vulnerable_ratio * 100, 1),
                'vulnerable_value': round(vulnerable_value, 0),
                'vulnerability_level': vulnerability_level,
                
                'high_profit_protected': high_profit_protected,
                'high_profit_count': len(high_profit_protected),
                
                'medium_profit': medium_profit,
                'medium_profit_count': len(medium_profit),
                
                'low_profit': low_profit,
                'low_profit_count': len(low_profit),
                
                'loss_positions': loss_positions,
                'loss_count': len(loss_positions),
                
                'minor_loss': minor_loss,
                'minor_loss_count': len(minor_loss)
            }
            
            logger.info(f"🔍 취약 구간 분석 완료:")
            logger.info(f"   ⚠️ 취약(+5~20%): {len(vulnerable_positions)}개 ({vulnerable_ratio*100:.1f}%) - {vulnerability_level}")
            logger.info(f"   ✅ 고수익(+50%↑): {len(high_profit_protected)}개")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 포트폴리오 취약성 분석 오류: {str(e)}")
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.1 신규 함수: 과거 유사 사례 검색 (Few-shot)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def find_similar_past_cases(self, past_decisions, current_vix, current_spy_change):
        """과거 유사 상황 찾기 (few-shot 학습)"""
        try:
            if not past_decisions or not past_decisions.get('recent_decisions'):
                return []
            
            recent = past_decisions['recent_decisions']
            similar = []
            
            for decision in recent:
                # 검증된 판단만
                if not decision.get('outcome_3days'):
                    continue
                
                # VIX와 SPY 변화율이 비슷한 경우
                past_vix = decision.get('vix', {}).get('current_price', 0)
                past_spy_change = decision.get('spy', {}).get('change_pct', 0)
                
                vix_diff = abs(current_vix - past_vix)
                spy_diff = abs(current_spy_change - past_spy_change)
                
                # 유사도 계산 (VIX ±3, SPY ±1.5% 이내)
                if vix_diff <= 3 and spy_diff <= 1.5:
                    outcome = decision['outcome_3days']
                    similar.append({
                        'date': decision['timestamp'][:10],
                        'vix': past_vix,
                        'spy_change': past_spy_change,
                        'phase': decision['market_phase'],
                        'confidence': decision.get('phase_confidence', 0),
                        'outcome': outcome.get('result', 'UNKNOWN'),
                        'accuracy': outcome.get('accuracy', 'N/A'),
                        'similarity_score': 100 - (vix_diff * 10 + spy_diff * 20)
                    })
            
            # 유사도 순으로 정렬
            similar.sort(key=lambda x: x['similarity_score'], reverse=True)
            return similar[:3]
            
        except Exception as e:
            logger.error(f"❌ 유사 사례 검색 오류: {str(e)}")
            return []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.0 함수: 자동 outcome 업데이트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def auto_update_outcomes(self):
        """과거 판단 결과 자동 검증 - 3일 후 SPY 변화 확인"""
        try:
            history_path = os.path.join(self.history_dir, self.history_file)
            if not os.path.exists(history_path):
                return
            
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            if not history.get('decisions'):
                return
            
            updated = False
            for decision in history['decisions']:
                # 이미 검증됐으면 스킵
                if decision.get('outcome_3days'):
                    continue
                
                # 3일 지났는지 확인
                decision_time = datetime.fromisoformat(decision['timestamp'])
                if datetime.now() - decision_time < timedelta(days=3):
                    continue
                
                # SPY 데이터 조회
                try:
                    spy_at_decision = decision.get('spy', {}).get('current_price')
                    if not spy_at_decision:
                        continue
                    
                    spy_current = SafeKisUS.safe_get_current_price("SPY")
                    if not spy_current or spy_current <= 0:
                        continue
                    
                    spy_change = ((spy_current - spy_at_decision) / spy_at_decision) * 100
                    
                    # 판단 평가
                    phase = decision['market_phase']
                    if phase == 'defense':
                        # defense 판단 시 -5% 이상 하락하면 CORRECT
                        if spy_change <= -5:
                            accuracy = 'CORRECT'
                        elif spy_change >= 2:
                            accuracy = 'INCORRECT'
                        else:
                            accuracy = 'NEUTRAL'
                    elif phase == 'reinvestment':
                        # reinvestment 판단 시 +3% 이상 상승하면 CORRECT
                        if spy_change >= 3:
                            accuracy = 'CORRECT'
                        elif spy_change <= -3:
                            accuracy = 'INCORRECT'
                        else:
                            accuracy = 'NEUTRAL'
                    else:  # normal
                        # normal 판단 시 ±3% 이내면 CORRECT
                        if abs(spy_change) <= 3:
                            accuracy = 'CORRECT'
                        else:
                            accuracy = 'INCORRECT'
                    
                    decision['outcome_3days'] = {
                        'result': phase,
                        'spy_change': round(spy_change, 2),
                        'accuracy': accuracy,
                        'verified_at': datetime.now().isoformat()
                    }
                    
                    updated = True
                    logger.info(f"✅ 판단 검증: {decision_time.date()} → {accuracy} (SPY {spy_change:+.2f}%)")
                    
                except Exception as e:
                    logger.error(f"❌ 판단 검증 오류: {str(e)}")
                    continue
            
            if updated:
                with open(history_path, 'w', encoding='utf-8') as f:
                    json.dump(history, f, indent=2, ensure_ascii=False)
                logger.info("💾 검증 결과 저장 완료")
                
        except Exception as e:
            logger.error(f"❌ outcome 업데이트 오류: {str(e)}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.0 함수: 오예측 패턴 감지
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def detect_error_patterns(self):
        """오예측 패턴 자동 감지"""
        try:
            history_path = os.path.join(self.history_dir, self.history_file)
            if not os.path.exists(history_path):
                return None
            
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            verified = [d for d in history['decisions'] if d.get('outcome_3days')]
            if len(verified) < 2:
                return None
            
            patterns = {
                'consecutive_errors': 0,
                'overconfidence_pattern': [],
                'underestimate_pattern': [],
                'vix_error_analysis': {
                    'low': {'range': '<18', 'errors': [], 'total': 0, 'accuracy': 0},
                    'medium': {'range': '18-25', 'errors': [], 'total': 0, 'accuracy': 0},
                    'high': {'range': '>25', 'errors': [], 'total': 0, 'accuracy': 0}
                },
                'error_insights': [],
                'total_verified': len(verified)
            }
            
            # 연속 오예측 감지
            consecutive = 0
            for d in verified[-5:]:
                if d['outcome_3days']['accuracy'] == 'INCORRECT':
                    consecutive += 1
                else:
                    consecutive = 0
            patterns['consecutive_errors'] = consecutive
            
            # 패턴 분석
            for d in verified:
                outcome = d['outcome_3days']
                vix = d.get('vix', {}).get('current_price', 15)
                
                # VIX 구간별 분류
                if vix < 18:
                    vix_range = 'low'
                elif vix < 25:
                    vix_range = 'medium'
                else:
                    vix_range = 'high'
                
                patterns['vix_error_analysis'][vix_range]['total'] += 1
                
                if outcome['accuracy'] == 'INCORRECT':
                    patterns['vix_error_analysis'][vix_range]['errors'].append({
                        'date': d['timestamp'][:10],
                        'vix': vix,
                        'spy_change': outcome['spy_change']
                    })
                    
                    # 과신 패턴 (defense인데 안 떨어짐)
                    if d['market_phase'] == 'defense' and outcome['spy_change'] > -5:
                        patterns['overconfidence_pattern'].append({
                            'date': d['timestamp'][:10],
                            'vix': vix,
                            'actual_change': outcome['spy_change']
                        })
                    
                    # 과소평가 패턴 (normal인데 큰 조정)
                    if d['market_phase'] == 'normal' and outcome['spy_change'] < -5:
                        patterns['underestimate_pattern'].append({
                            'date': d['timestamp'][:10],
                            'vix': vix,
                            'actual_change': outcome['spy_change']
                        })
            
            # VIX 구간별 정확도 계산
            for range_name, data in patterns['vix_error_analysis'].items():
                if data['total'] > 0:
                    data['accuracy'] = ((data['total'] - len(data['errors'])) / data['total'] * 100)
            
            # 인사이트 생성
            if patterns['consecutive_errors'] >= 3:
                patterns['error_insights'].append(
                    f"⚠️ 연속 {patterns['consecutive_errors']}회 오예측 - 신뢰도 매우 낮음"
                )
            
            if len(patterns['overconfidence_pattern']) >= 2:
                patterns['error_insights'].append(
                    f"⚠️ 과신 패턴 {len(patterns['overconfidence_pattern'])}회 감지"
                )
            
            if len(patterns['underestimate_pattern']) >= 2:
                patterns['error_insights'].append(
                    f"⚠️ 과소평가 패턴 {len(patterns['underestimate_pattern'])}회 감지"
                )
            
            for range_name, data in patterns['vix_error_analysis'].items():
                if data['total'] >= 2 and data['accuracy'] < 50:
                    patterns['error_insights'].append(
                        f"⚠️ VIX {data['range']} 구간 취약: 정확도 {data['accuracy']:.0f}%"
                    )
            
            logger.info(f"🔍 오예측 패턴 분석 완료: {len(patterns['error_insights'])}개 인사이트")
            return patterns
            
        except Exception as e:
            logger.error(f"❌ 오예측 패턴 분석 오류: {e}")
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.0 함수: 학습 피드백 생성
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def generate_learning_feedback(self, past_decisions, error_patterns):
        """AI에게 전달할 구조화된 학습 피드백 생성"""
        try:
            if not past_decisions or not error_patterns:
                return ""
            
            accuracy = past_decisions.get('accuracy_rate', 0)
            total = error_patterns.get('total_verified', 0)
            
            feedback = "\n" + "="*60 + "\n"
            feedback += "【🧠 학습 피드백 - 과거 판단으로부터 배운 점】\n"
            feedback += "="*60 + "\n\n"
            
            # 신뢰도 평가
            if accuracy >= 80:
                confidence_level = "높음 ✅"
                advice = "현재 판단 로직이 잘 작동 중입니다."
            elif accuracy >= 60:
                confidence_level = "보통 ⚠️"
                advice = "일부 개선 필요. 아래 취약점을 참고하세요."
            else:
                confidence_level = "낮음 🚨"
                advice = "심각한 신뢰도 문제! 매우 보수적으로 판단하세요."
            
            feedback += f"📊 현재 시스템 신뢰도: {accuracy:.0f}% ({confidence_level})\n"
            feedback += f"   검증 완료: {total}건 중 {past_decisions.get('correct_count', 0)}건 정확\n\n"
            feedback += f"💡 조언: {advice}\n\n"
            
            # 최근 오예측
            if error_patterns.get('error_insights'):
                feedback += "🔴 최근 오예측 이력:\n"
                for insight in error_patterns['error_insights'][:3]:
                    feedback += f"   • {insight}\n"
                feedback += "\n"
            
            # 과신 패턴
            if error_patterns.get('overconfidence_pattern'):
                feedback += "⚠️ 과신 패턴 (조정 예측했는데 안 온 경우):\n"
                for case in error_patterns['overconfidence_pattern'][-2:]:
                    feedback += f"   • {case['date']}: VIX {case['vix']:.1f}, 실제 {case['actual_change']:+.1f}%\n"
                feedback += "   → 이런 상황에서는 더 보수적으로!\n\n"
            
            # 과소평가 패턴
            if error_patterns.get('underestimate_pattern'):
                feedback += "⚠️ 과소평가 패턴 (NORMAL인데 조정 온 경우):\n"
                for case in error_patterns['underestimate_pattern'][-2:]:
                    feedback += f"   • {case['date']}: VIX {case['vix']:.1f}, 실제 {case['actual_change']:+.1f}%\n"
                feedback += "   → 이런 상황에서는 더 공격적으로 방어!\n\n"
            
            # VIX 구간별 취약점
            vix_analysis = error_patterns.get('vix_error_analysis', {})
            for range_name, data in vix_analysis.items():
                if data['total'] >= 2 and data['accuracy'] < 60:
                    feedback += f"📊 VIX {data['range']} 구간 취약점:\n"
                    feedback += f"   정확도: {data['accuracy']:.0f}% ({data['total']}건 중 {len(data['errors'])}건 오류)\n"
                    feedback += f"   → 이 구간에서 특히 신중하게!\n\n"
            
            feedback += "="*60 + "\n"
            feedback += "⚠️ 위 학습 내용을 반드시 반영하여 판단하세요!\n"
            feedback += "="*60 + "\n"
            
            return feedback
            
        except Exception as e:
            logger.error(f"❌ 학습 피드백 생성 오류: {e}")
            return ""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # v3.0 함수: 학습 리포트 생성
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def generate_learning_report(self, past_decisions, error_patterns):
        """상세 학습 리포트 생성 및 저장"""
        try:
            if not past_decisions or not error_patterns:
                return None
            
            report = {
                'generated_at': datetime.now().isoformat(),
                'overall_accuracy': past_decisions.get('accuracy_rate', 0),
                'total_verified': error_patterns.get('total_verified', 0),
                'correct_count': past_decisions.get('correct_count', 0),
                'consecutive_errors': error_patterns.get('consecutive_errors', 0),
                
                'error_patterns': {
                    'overconfidence': len(error_patterns.get('overconfidence_pattern', [])),
                    'underestimate': len(error_patterns.get('underestimate_pattern', [])),
                },
                
                'vix_performance': error_patterns.get('vix_error_analysis', {}),
                
                'recent_errors': error_patterns.get('error_insights', []),
                
                'recommendations': []
            }
            
            # 권장사항 생성
            accuracy = report['overall_accuracy']
            if accuracy < 50:
                report['recommendations'].append({
                    'priority': 'CRITICAL',
                    'action': '시스템 전면 재검토 필요',
                    'detail': f'정확도 {accuracy:.0f}%는 심각한 수준'
                })
            elif accuracy < 70:
                report['recommendations'].append({
                    'priority': 'HIGH',
                    'action': '보수적 조정 강화',
                    'detail': '신뢰도 기반 자동 조정 활성화'
                })
            
            if report['consecutive_errors'] >= 3:
                report['recommendations'].append({
                    'priority': 'CRITICAL',
                    'action': '연속 오예측 - 시스템 점검 필요',
                    'detail': f"{report['consecutive_errors']}회 연속 실패"
                })
            
            # 저장
            report_path = os.path.join(self.history_dir, 'ai_learning_report.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📊 학습 리포트 저장: {report_path}")
            return report
            
        except Exception as e:
            logger.error(f"❌ 학습 리포트 생성 오류: {e}")
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # AI 호출 및 프롬프트 (v3.1 개선)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def ask_ai_with_enhanced_prompt(self, portfolio_data, market_data, sentiment_data,
                                     sector_data, bond_data, safe_haven_data,
                                     bitcoin_data, breadth_data, vix_structure_data,
                                     past_decisions, learning_feedback,
                                     news_sentiment=None, portfolio_vuln=None):
        """강화된 프롬프트로 AI 호출 - v3.1 뉴스+취약성 통합"""
        try:
            load_dotenv()
            openai_key = os.getenv("OPENAI_API_KEY")
            
            if not openai_key:
                logger.error("OPENAI_API_KEY 없음")
                return None
            
            client = OpenAI(api_key=openai_key)
            
            prompt = self.generate_enhanced_prompt(
                portfolio_data, market_data, sentiment_data,
                sector_data, bond_data, safe_haven_data,
                bitcoin_data, breadth_data, vix_structure_data,
                past_decisions, learning_feedback,
                news_sentiment, portfolio_vuln
            )
            
            logger.info("🤖 OpenAI GPT-4 분석 시작 (v3.1 뉴스+취약성)")
            
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 전문 퀀트 트레이더입니다. 과거 실수로부터 배우고, 17단계 구조화 추론을 거쳐 JSON으로만 응답하세요."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            ai_response = response.choices[0].message.content
            
            if "```json" in ai_response:
                ai_response = ai_response.split("```json")[1].split("```")[0].strip()
            elif "```" in ai_response:
                ai_response = ai_response.split("```")[1].split("```")[0].strip()
            
            ai_decision = json.loads(ai_response)
            
            logger.info("✅ AI 분석 완료 (v3.1)")
            logger.info(f"   Phase: {ai_decision.get('market_phase', 'unknown')}")
            logger.info(f"   신뢰도: {ai_decision.get('phase_confidence', 0)}%")
            
            return ai_decision
            
        except Exception as e:
            logger.error(f"❌ OpenAI API 오류: {str(e)}")
            return None
    
    def generate_enhanced_prompt(self, portfolio_data, market_data, sentiment_data,
                                 sector_data, bond_data, safe_haven_data,
                                 bitcoin_data, breadth_data, vix_structure_data,
                                 past_decisions, learning_feedback,
                                 news_sentiment=None, portfolio_vuln=None):
        """v3.1 개선 프롬프트 - 가중치+뉴스+취약성"""
        
        total = portfolio_data['total']
        spy = market_data['spy']
        vix = market_data['vix']
        
        # VIX 구간별 전략 가이드
        vix_current = vix['current_price']
        if vix_current < 12:
            vix_strategy = "【매우 안정】일반 매수 모드, 현금 10-15% 유지"
        elif vix_current < 18:
            vix_strategy = "【안정】정상 운영, 현금 15-20% 유지"
        elif vix_current < 25:
            vix_strategy = "【경계】선제 방어 검토, 현금 25-35% 목표"
        else:
            vix_strategy = "【공포】적극 방어, 현금 40-50% 확보"
        
        # 과거 유사 상황
        similar_cases = self.find_similar_past_cases(past_decisions, vix_current, spy['change_pct'])
        similar_cases_text = ""
        if similar_cases:
            similar_cases_text = "\n━━━ 📚 과거 유사 상황 참고 ━━━\n"
            for i, case in enumerate(similar_cases, 1):
                similar_cases_text += f"{i}. {case['date']}: VIX {case['vix']:.1f}, SPY {case['spy_change']:+.1f}%\n"
                similar_cases_text += f"   → 판단: {case['phase']} (신뢰도 {case['confidence']}%)\n"
                if case.get('outcome'):
                    similar_cases_text += f"   → 결과: {case['outcome']}\n"
        
        # 뉴스 감성 섹션
        news_section = ""
        if news_sentiment:
            overall = news_sentiment.get('overall', {})
            high_risk = news_sentiment.get('high_risk_sectors', [])
            news_section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【뉴스 감성 분석】⭐⭐⭐⭐ 중요도: 4/5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
전체 종목: 부정 {overall.get('negative_ratio', 0)}% / 긍정 {overall.get('positive_ratio', 0)}%
고위험 섹터: {len(high_risk)}개 - {', '.join(high_risk) if high_risk else '없음'}
캐시 유효율: {news_sentiment.get('cache_validity', 0)}% (API 비용: $0)

⚠️ 뉴스 해석 가이드:
  • 고위험 섹터 2개 이상 → 해당 섹터 현금 확보 우선
  • 부정 비율 40% 이상 → 전체 포트폴리오 방어 모드 검토
  • 부정 비율 60% 이상 → 적극적 현금 확보 (35%+)
"""
        
        # 취약성 섹션
        vuln_section = ""
        if portfolio_vuln:
            vuln_ratio = portfolio_vuln.get('vulnerable_ratio', 0)
            vuln_level = portfolio_vuln.get('vulnerability_level', 'LOW')
            vuln_count = portfolio_vuln.get('vulnerable_count', 0)
            
            vuln_section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【포트폴리오 취약성 분석】⭐⭐⭐⭐⭐ 중요도: 5/5 (최우선)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 취약 구간(+5~20%): {vuln_count}개, {vuln_ratio}% - 위험도: {vuln_level}
   → 이 구간은 트레일링 스톱 미작동! 조정 시 수익 증발 위험!

✅ 고수익(+50%↑): {portfolio_vuln.get('high_profit_count', 0)}개 (트레일링 보호 중)
📊 중수익(+20~50%): {portfolio_vuln.get('medium_profit_count', 0)}개

⚠️ 취약성 대응 전략:
  • HIGH: 취약 구간 40%+ → 즉시 방어 (현금 40%+)
  • MEDIUM: 취약 구간 25-40% → 선제 방어 (현금 30%+)
  • LOW: 취약 구간 25% 미만 → 정상 운영 (현금 20%)
  
💡 핵심: 취약 구간 비율이 높을수록 조정장에서 타격이 크다!
"""
        
        prompt = f"""
당신은 전문 퀀트 트레이더입니다. 아래 **17단계 구조화 추론**을 **반드시 모두** 거쳐 판단하세요.
각 단계에는 중요도(⭐1~5)가 표시되어 있습니다. 높은 중요도 단계에 더 집중하세요.

{learning_feedback}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【포트폴리오 현황】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총 자산: ${total['total_value']:.0f}
보유 현금: ${total['current_cash']:.0f} ({total['cash_ratio']*100:.1f}%)
총 수익률: {total['total_return_pct']:.2f}%
포지션 수: {total['position_count']}개

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【시장 지표】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPY: ${spy['current_price']:.2f} ({spy['change_pct']:+.2f}%)
VIX: {vix['current_price']:.2f} ({vix['level']})

VIX 구간별 전략: {vix_strategy}
{vuln_section}
{news_section}
{similar_cases_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【17단계 구조화 추론 과정】⭐ 중요도 표시
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 주의: 위의 【학습 피드백】, 【취약성 분석】, 【뉴스 감성】을 **반드시** 참고하세요.

1. [포트폴리오 진단] ⭐⭐⭐ 중요도: 3/5
   - 현재 현금비율 {total['cash_ratio']*100:.1f}%는 적정한가?
   - 취약 구간 비율을 고려했을 때 위험도는?

2. [시장 환경 분석] ⭐⭐⭐⭐ 중요도: 4/5
   - SPY 추세: {spy['status']}
   - VIX: {vix_strategy}

3. [조정 가능성 평가] ⭐⭐⭐⭐⭐ 중요도: 5/5 (최우선)
   - 다음 1-2일 내 조정(>5% 하락) 올 확률은?
   - 뉴스 감성이 미치는 영향은?

4. [시나리오 분석] ⭐⭐⭐⭐ 중요도: 4/5
   - 낙관/중립/비관 시나리오별 확률과 대응

5. [섹터 분석] ⭐⭐ 중요도: 2/5
6. [채권 신호] ⭐⭐ 중요도: 2/5
7. [안전자산] ⭐⭐ 중요도: 2/5
8. [비트코인] ⭐ 중요도: 1/5
9. [시장 내부 강도] ⭐⭐⭐ 중요도: 3/5
10. [VIX 구조] ⭐⭐⭐ 중요도: 3/5
11. [경제 이벤트] ⭐⭐ 중요도: 2/5
12. [과거 학습] ⭐⭐⭐⭐ 중요도: 4/5
13. [리스크 종합] ⭐⭐⭐⭐⭐ 중요도: 5/5 (최우선)
14. [반대 의견] ⭐⭐⭐⭐ 중요도: 4/5
15. [신뢰도 평가] ⭐⭐⭐⭐ 중요도: 4/5
16. [현금 전략] ⭐⭐⭐⭐⭐ 중요도: 5/5 (최우선)
17. [최종 판단] ⭐⭐⭐⭐⭐ 중요도: 5/5 (최우선)

**JSON 형식으로만 응답:**
{{
  "market_phase": "defense",
  "phase_confidence": 75,
  "risk_level": "HIGH",
  "reasoning": "상세한 판단 근거 (취약성, 뉴스, VIX 모두 언급)",
  "key_insights": ["인사이트1", "인사이트2"],
  "cash_strategy": {{
    "target_cash_ratio": 0.35,
    "reason": "이유 (취약 구간, VIX, 뉴스 반영)"
  }}
}}
"""
        return prompt

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 검증 및 저장 함수들
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def validate_decision_enhanced(self, decision, market_data):
        """결과 검증"""
        if not decision or not isinstance(decision, dict):
            return self.create_fallback_decision(market_data)
        
        required_keys = ['market_phase', 'risk_level', 'cash_strategy']
        if not all(k in decision for k in required_keys):
            return self.create_fallback_decision(market_data)
        
        decision['validated'] = True
        decision['timestamp'] = datetime.now().isoformat()
        decision['vix'] = market_data.get('vix', {})
        decision['spy'] = market_data.get('spy', {})
        decision['protection_required'] = (decision['risk_level'] in ['CRITICAL', 'HIGH'])
        
        return decision
    
    def create_fallback_decision(self, market_data):
        """폴백 결정"""
        vix_level = market_data.get('vix', {}).get('current_price', 15.0)
        
        if vix_level > 25:
            risk = 'HIGH'
            phase = 'defense'
            cash = 0.35
        elif vix_level > 18:
            risk = 'NORMAL'
            phase = 'normal'
            cash = 0.20
        else:
            risk = 'LOW'
            phase = 'normal'
            cash = 0.10
        
        return {
            'market_phase': phase,
            'phase_confidence': 50,
            'risk_level': risk,
            'reasoning': 'AI 분석 실패 - VIX 기반 폴백',
            'key_insights': ['AI 분석 실패'],
            'cash_strategy': {
                'target_cash_ratio': cash,
                'reason': f'VIX {vix_level:.1f} 기반 자동 설정'
            },
            'timestamp': datetime.now().isoformat(),
            'validated': False,
            'protection_required': (risk in ['CRITICAL', 'HIGH'])
        }
    
    def apply_confidence_adjustment(self, decision, accuracy, error_patterns):
        """신뢰도 기반 자동 조정 (v3.0)"""
        try:
            original_cash = decision['cash_strategy']['target_cash_ratio']
            original_risk = decision['risk_level']
            adjustments = []
            
            # 정확도 기반 조정
            if accuracy < 40:
                decision['cash_strategy']['target_cash_ratio'] = min(0.5, original_cash + 0.15)
                decision['risk_level'] = 'CRITICAL' if original_risk != 'CRITICAL' else original_risk
                adjustments.append("신뢰도 매우 낮음(<40%) → 현금+15%, 리스크 상향")
            elif accuracy < 60:
                decision['cash_strategy']['target_cash_ratio'] = min(0.5, original_cash + 0.10)
                if original_risk == 'LOW':
                    decision['risk_level'] = 'NORMAL'
                elif original_risk == 'NORMAL':
                    decision['risk_level'] = 'HIGH'
                adjustments.append("신뢰도 낮음(<60%) → 현금+10%, 리스크 상향")
            elif accuracy < 70:
                decision['cash_strategy']['target_cash_ratio'] = min(0.5, original_cash + 0.05)
                adjustments.append("신뢰도 보통(<70%) → 현금+5%")
            
            # 연속 오예측 조정
            consecutive = error_patterns.get('consecutive_errors', 0)
            if consecutive >= 3:
                decision['cash_strategy']['target_cash_ratio'] = min(0.5, decision['cash_strategy']['target_cash_ratio'] + 0.10)
                adjustments.append(f"연속 {consecutive}회 오예측 → 현금+10% 추가")
            
            # 과신 패턴 조정
            if len(error_patterns.get('overconfidence_pattern', [])) >= 2:
                decision['phase_confidence'] = max(0, decision.get('phase_confidence', 50) - 15)
                adjustments.append("과신 패턴 감지 → 신뢰도 -15%")
            
            if adjustments:
                decision['confidence_adjustments'] = adjustments
                decision['original_cash_ratio'] = original_cash
                decision['original_risk_level'] = original_risk
                
                logger.info(f"🔧 신뢰도 기반 자동 조정:")
                for adj in adjustments:
                    logger.info(f"   • {adj}")
                logger.info(f"   최종 현금: {original_cash*100:.0f}% → {decision['cash_strategy']['target_cash_ratio']*100:.0f}%")
            
            return decision
            
        except Exception as e:
            logger.error(f"❌ 신뢰도 조정 오류: {str(e)}")
            return decision
    
    def save_protection_decision(self, decision):
        """판단 결과 저장"""
        try:
            output_path = os.path.join(self.data_directory, self.output_file)
            
            if os.path.exists(output_path):
                backup_name = f"profit_protection_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                backup_path = os.path.join(self.history_dir, backup_name)
                with open(output_path, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(decision, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 판단 결과 저장: {output_path}")
            logger.info(f"   Phase: {decision['market_phase']}")
            logger.info(f"   목표 현금: {decision['cash_strategy']['target_cash_ratio']*100:.1f}%")
            
        except Exception as e:
            logger.error(f"판단 결과 저장 오류: {str(e)}")
    
    def save_decision_to_history(self, decision):
        """판단 이력 저장"""
        try:
            history_path = os.path.join(self.history_dir, self.history_file)
            
            if os.path.exists(history_path):
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = {'decisions': []}
            
            decision_record = {
                'timestamp': decision['timestamp'],
                'market_phase': decision['market_phase'],
                'phase_confidence': decision.get('phase_confidence', 0),
                'cash_strategy': decision['cash_strategy'],
                'risk_level': decision['risk_level'],
                'spy': decision.get('spy', {}),
                'vix': decision.get('vix', {})
            }
            
            history['decisions'].append(decision_record)
            
            if len(history['decisions']) > 50:
                history['decisions'] = history['decisions'][-50:]
            
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            
            logger.info(f"🧠 판단 이력 저장")
            
        except Exception as e:
            logger.error(f"판단 이력 저장 오류: {str(e)}")

    def send_discord_alert(self, decision):
        """Discord 알림"""
        try:
            if not DISCORD_AVAILABLE:
                return
            
            phase = decision['market_phase']
            risk = decision['risk_level']
            confidence = decision.get('phase_confidence', 0)
            cash_ratio = decision['cash_strategy']['target_cash_ratio'] * 100
            reasoning = decision.get('reasoning', 'AI 분석 결과')
            
            msg = f"🛡️ **AI 수익보호 v3.1 - 뉴스+취약성 통합**\n\n"
            msg += f"**Phase:** {phase}\n"
            msg += f"**위험 수준:** {risk}\n"
            msg += f"**신뢰도:** {confidence}%\n"
            msg += f"**목표 현금:** {cash_ratio:.0f}%\n\n"
            msg += f"**판단 이유:** {reasoning}\n"
            
            if 'confidence_adjustments' in decision:
                msg += f"\n**🔧 자동 조정:**\n"
                for adj in decision['confidence_adjustments'][:2]:
                    msg += f"  • {adj}\n"
            
            discord_alert.SendMessage(msg)
            logger.info("✅ Discord 알림 전송 완료")
            
        except Exception as e:
            logger.error(f"Discord 알림 오류: {str(e)}")


def main():
    """메인 실행"""
    try:
        logger.info("=" * 80)
        logger.info("🚀 AI 수익보호 시스템 v3.1 시작 (뉴스+취약성 통합)")
        logger.info("=" * 80)
        
        protector = AIProfitProtector()
        result = protector.run_analysis()
        
        if result:
            logger.info("=" * 80)
            logger.info("✅ 분석 성공")
            logger.info("=" * 80)
            return True
        else:
            logger.error("❌ 분석 실패")
            return False
            
    except Exception as e:
        logger.error(f"❌ 실행 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)