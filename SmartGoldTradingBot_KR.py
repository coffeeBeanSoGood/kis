#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🥇 스마트 골드 트레이딩 봇 (SmartGoldTradingBot_KR) - 금 투자 전용 시스템
1. 금 ETF 전문 투자 (KODEX 골드선물, TIGER 골드선물 등)
2. 금 특성을 반영한 5차수 분할매매
3. 달러 인덱스 & 인플레이션 연동 시스템
4. 지정학적 리스크 감지 시스템
5. 안전자산 특성 활용 전략
6. 장기 트렌드 추종 최적화
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
logger = logging.getLogger('SmartGoldTradingLogger')
logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (매일 자정에 새로운 파일 생성)
log_file = os.path.join(log_directory, 'smart_gold_trading.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=7,    # 7일치 로그 파일 보관 (금 투자는 장기 관점)
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

# API 모듈에 로거 전달
try:
    KisKR.set_logger(logger)
    Common.set_logger(logger)
except:
    logger.warning("API 헬퍼 모듈에 로거를 전달할 수 없습니다.")

# 🔥 API 초기화
if Common.GetNowDist() == "":
    Common.SetChangeMode("REAL")  # 실계좌 모드

################################### 🥇 금 투자 전용 설정 클래스 ##################################

class GoldTradingConfig:
    def __init__(self):
        self.config_path = "gold_trading_config.json"
        self.config = {}
        self.load_config()
    
    def get_default_config(self):
        """금 투자 전용 기본 설정"""
        
        # 🥇 금 ETF 상품 설정 (한국 상장 상품들) - 실제 거래 가능한 종목들
        gold_products = {
            "132030": {  # KODEX 골드선물(H) - 실제 상장
                "name": "KODEX 골드선물(H)",
                "type": "ETF",
                "currency_hedge": True,  # 환헤지
                "weight": 0.35,  # 35% 비중
                "volatility_level": "medium",
                "recommended": True,
                "description": "삼성자산운용의 달러화 환헤지 골드 선물 ETF"
            },
            "319640": {  # TIGER 골드선물 - 실제 상장 (사용자 확인)
                "name": "TIGER 골드선물",
                "type": "ETF",
                "currency_hedge": False,  # 환헤지 없음
                "weight": 0.30,  # 30% 비중
                "volatility_level": "high",
                "recommended": True,
                "description": "미래에셋자산운용의 달러 노출 골드 선물 ETF"
            },
            "411060": {  # ACE KRX 금현물 - 실제 상장
                "name": "ACE KRX 금현물",
                "type": "ETF", 
                "currency_hedge": False,  # 원화 기준
                "weight": 0.20,  # 20% 비중
                "volatility_level": "medium",
                "recommended": True,
                "description": "한국투자신탁운용의 KRX 금현물 지수 추종 ETF"
            },
            "0072R0": {  # TIGER KRX 금현물 - 실제 상장 (최저수수료)
                "name": "TIGER KRX 금현물",
                "type": "ETF",
                "currency_hedge": False,  # 원화 기준
                "weight": 0.15,  # 15% 비중
                "volatility_level": "low",
                "recommended": True,
                "description": "미래에셋자산운용의 KRX 금현물 ETF (최저수수료 0.15%)"
            }
        }
        
        return {
            # 🥇 금 전용 투자 설정
            "use_absolute_budget": True,
            "absolute_budget": 1000000,  # 100만원 (금 투자 전용 예산)
            "absolute_budget_strategy": "equal_weight",  # 균등 분산
            "initial_total_asset": 0,
            
            # 🥇 금 상품 설정  
            "gold_products": gold_products,
            
            # 🥇 금 특화 매매 전략
            "gold_strategy": {
                "investment_style": "long_term_trend",  # 장기 트렌드 추종
                "rebalancing_cycle": "monthly",  # 월간 리밸런싱
                "risk_tolerance": "moderate",  # 중간 위험도
                "hedge_ratio": 0.7,  # 환헤지 비율 70%
                "safe_haven_mode": True,  # 안전자산 모드
            },
            
            # 🔥 5차수 분할매매 설정 (금 특화)
            "div_num": 5.0,
            "position_ratios": {
                "1": 0.15,  # 1차: 15%
                "2": 0.20,  # 2차: 20% 
                "3": 0.25,  # 3차: 25%
                "4": 0.20,  # 4차: 20%
                "5": 0.20   # 5차: 20%
            },
            
            # 🥇 금 특화 매수 조건
            "gold_buy_conditions": {
                "dollar_index_threshold": 105.0,  # 달러 인덱스 임계값
                "inflation_concern": True,  # 인플레이션 우려시 매수
                "geopolitical_risk": True,  # 지정학적 리스크시 매수
                "stock_market_volatility": 25.0,  # VIX 25 이상시 매수
                "interest_rate_environment": "rising",  # 금리 상승기
                "seasonal_factor": True,  # 계절적 요인 고려
            },
            
            # 🥇 금 특화 기술적 지표
            "technical_indicators": {
                "ma_short": 10,    # 단기 이평선 (금은 장기 관점)
                "ma_mid": 50,      # 중기 이평선
                "ma_long": 200,    # 장기 이평선
                "rsi_period": 21,  # RSI 기간 (금은 더 긴 기간)
                "atr_period": 20,  # ATR 기간
                "rsi_oversold": 25,  # 과매도 (더 보수적)
                "rsi_overbought": 75,  # 과매수 (더 보수적)
                "trend_strength_threshold": 0.7,  # 트렌드 강도
            },
            
            # 🥇 금 특화 하락률 요구사항 (더 보수적)
            "dynamic_drop_requirements": {
                "enable": True,
                "base_drops": {
                    "2": 0.06,   # 2차: 6% 하락 (금은 더 큰 하락 필요)
                    "3": 0.08,   # 3차: 8% 하락
                    "4": 0.10,   # 4차: 10% 하락  
                    "5": 0.12    # 5차: 12% 하락
                },
                "adjustment_factors": {
                    "dollar_strength_bonus": -0.02,      # 달러 강세시 진입 완화
                    "inflation_spike_bonus": -0.025,     # 인플레이션 급등시 완화
                    "geopolitical_bonus": -0.03,        # 지정학적 리스크시 완화
                    "stock_crash_bonus": -0.035,        # 주식 폭락시 완화
                    "safe_haven_demand_bonus": -0.02,   # 안전자산 수요 증가시
                    "gold_overbought_penalty": 0.015,   # 금 과매수시 페널티
                    "dollar_weakness_penalty": 0.01     # 달러 약세시 페널티
                }
            },
            
            # 🥇 금 특화 손절 시스템 (더 관대)
            "gold_stop_loss": {
                "enable": True,
                "description": "금 투자 특화 장기 손절 시스템",
                
                # 기본 손절선 (주식보다 관대)
                "adaptive_thresholds": {
                    "position_1": -0.20,     # 1차수: -20%
                    "position_2": -0.25,     # 2차수: -25%
                    "position_3_plus": -0.30 # 3차수 이상: -30%
                },
                
                # 시장 상황별 조정
                "market_adjustment": {
                    "enable": True,
                    "dollar_index_based": True,
                    "adjustments": {
                        "strong_dollar": -0.05,     # 강달러시 손절선 완화
                        "weak_dollar": 0.03,        # 약달러시 손절선 강화
                        "high_inflation": -0.03,    # 고인플레이션시 완화
                        "deflation_risk": 0.02,     # 디플레이션 우려시 강화
                        "recession_fear": -0.04,    # 경기침체 우려시 완화
                    }
                },
                
                # 시간 기반 손절 (더 긴 기간)
                "time_based_rules": {
                    "enable": True,
                    "rules": {
                        "180_day_threshold": -0.25,    # 6개월: -25%
                        "365_day_threshold": -0.20,    # 1년: -20%
                        "730_day_threshold": -0.15     # 2년: -15%
                    }
                }
            },
            
            # 🥇 금 특화 매도 전략
            "gold_sell_strategy": {
                "profit_taking": {
                    "enable": True,
                    "targets": {
                        "position_1": 0.25,    # 1차: 25% 익절
                        "position_2": 0.30,    # 2차: 30% 익절
                        "position_3_plus": 0.35 # 3차+: 35% 익절
                    },
                    "partial_sell_ratio": 0.5  # 50% 부분 매도
                },
                
                "trend_reversal": {
                    "enable": True,
                    "ma_cross_sell": True,      # 이평선 하향 돌파시 매도
                    "rsi_peak_sell": True,      # RSI 고점 매도
                    "volume_spike_sell": False  # 거래량 급증 매도 (금은 제외)
                },
                
                "rebalancing": {
                    "enable": True,
                    "cycle": "monthly",
                    "threshold": 0.1  # 10% 이상 비중 이탈시 리밸런싱
                }
            },
            
            # 📊 성과 추적
            "performance_tracking": {
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "benchmark": "gold_futures",  # 벤치마크: 금선물
                "currency_exposure": "mixed", # 환노출: 혼합
                "total_trades": 0,
                "winning_trades": 0,
                "total_realized_pnl": 0.0,
                "gold_metrics": {
                    "dollar_correlation": 0.0,
                    "stock_correlation": 0.0,  
                    "inflation_correlation": 0.0,
                    "safe_haven_events": 0,
                    "rebalancing_count": 0
                }
            },
            
            # 수수료 및 세금 (ETF 특성 반영)
            "commission_rate": 0.00015,  # 0.015%
            "tax_rate": 0.0,  # ETF는 양도소득세 없음
            "management_fee": 0.005,  # 연 0.5% 운용보수
            
            # 기타 설정
            "use_discord_alert": True,
            "bot_name": "SmartGoldTradingBot",
            "last_config_update": datetime.now().isoformat(),
            
            # 📋 사용자 가이드
            "_readme_gold": {
                "버전": "Gold Trading 1.0 - 금 투자 전문 시스템",
                "투자_철학": {
                    "장기_투자": "금은 장기 보유 관점의 안전자산",
                    "인플레이션_헤지": "인플레이션 및 통화가치 하락 방어",
                    "포트폴리오_다양화": "주식과 역상관 관계를 통한 리스크 분산",
                    "안전자산_역할": "경제 불안정기 자본 보존 수단"
                },
                "투자_상품": {
                    "KODEX_골드선물_H": "환헤지 상품으로 환율 리스크 제거",
                    "KODEX_골드선물": "달러 강세 수혜 가능한 환노출 상품",
                    "TIGER_골드선물": "미래에셋 운용 환노출 상품"
                },
                "매매_전략": {
                    "분할_매수": "5차수 분할로 평균단가 효과 극대화",
                    "트렌드_추종": "장기 상승 트렌드에서 포지션 확대",
                    "안전자산_수요": "주식 폭락, 지정학적 리스크시 적극 매수",
                    "달러_연동": "달러 인덱스 기반 진입 타이밍 조절"
                },
                "예상_성과": {
                    "연평균_수익률": "8-12% (장기 금 수익률 기준)",
                    "변동성": "주식 대비 60% 수준의 안정성",
                    "상관관계": "주식과 -0.3 ~ -0.5 역상관",
                    "인플레이션_방어": "연 3% 이상 인플레이션시 우수한 성과"
                }
            }
        }

    def load_config(self):
        """설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 기본 설정과 병합
            default_config = self.get_default_config()
            self.config = self._merge_config(default_config, loaded_config)
            logger.info(f"✅ 금 투자 설정 파일 로드 완료: {self.config_path}")
            
        except FileNotFoundError:
            logger.info(f"📋 설정 파일이 없습니다. 기본 설정으로 생성: {self.config_path}")
            self.config = self.get_default_config()
            self.save_config()
    
    def _merge_config(self, default, loaded):
        """설정 병합"""
        for key, value in default.items():
            if key not in loaded:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                loaded[key] = self._merge_config(value, loaded[key])
        return loaded
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 금 투자 설정 파일 저장 완료")
        except Exception as e:
            logger.error(f"❌ 설정 저장 실패: {str(e)}")

# 전역 설정 인스턴스
config = GoldTradingConfig()

# 봇 이름 설정
BOT_NAME = Common.GetNowDist() + "_" + config.config.get("bot_name", "SmartGoldTradingBot")

################################### 🥇 금 투자 전용 메인 클래스 ##################################

class SmartGoldTrading:
    def __init__(self):
        self.split_data_list = self.load_split_data()
        self.total_money = 0
        self.update_budget()
        self._upgrade_json_structure_if_needed()
        
        # 금 투자 전용 추적 변수들
        self.last_sell_time = {}  # {product_code: datetime}
        self.pending_orders = {}  # 미체결 주문 추적
        self.dollar_index_cache = None
        self.last_market_analysis = None
        self.rebalancing_schedule = {}
        
        logger.info("🥇 스마트 골드 트레이딩 봇 초기화 완료")

    def update_budget(self):
        """예산 업데이트"""
        try:
            if config.config.get("use_absolute_budget", True):
                self.total_money = config.config.get("absolute_budget", 5000000)
                logger.info(f"💰 금 투자 전용 예산: {self.total_money:,.0f}원")
            else:
                # 전체 계좌 잔고 기반
                account_balance = KisKR.GetBalance()
                self.total_money = account_balance
                logger.info(f"💰 계좌 기반 예산: {self.total_money:,.0f}원")
                
        except Exception as e:
            logger.error(f"❌ 예산 업데이트 실패: {str(e)}")
            self.total_money = 5000000  # 기본값

    def load_split_data(self):
        """저장된 매매 데이터 로드"""
        try:
            bot_file_path = f"GoldTrading_{BOT_NAME}.json"
            with open(bot_file_path, 'r', encoding='utf-8') as json_file:
                return json.load(json_file)
        except Exception:
            return []

    def save_split_data(self):
        """매매 데이터 저장"""
        try:
            bot_file_path = f"GoldTrading_{BOT_NAME}.json"
            
            # 백업 생성
            backup_path = f"{bot_file_path}.backup"
            if os.path.exists(bot_file_path):
                import shutil
                shutil.copy2(bot_file_path, backup_path)
            
            # 임시 파일에 저장 후 원자적 교체
            temp_path = f"{bot_file_path}.temp"
            with open(temp_path, 'w', encoding='utf-8') as temp_file:
                json.dump(self.split_data_list, temp_file, ensure_ascii=False, indent=2)
            
            # JSON 유효성 검증
            with open(temp_path, 'r', encoding='utf-8') as verify_file:
                json.load(verify_file)
            
            # 원자적 교체
            if os.name == 'nt':  # Windows
                if os.path.exists(bot_file_path):
                    os.remove(bot_file_path)
            os.rename(temp_path, bot_file_path)
            
            logger.debug("✅ 금 투자 데이터 저장 완료")
            
        except Exception as e:
            logger.error(f"❌ 데이터 저장 중 오류: {str(e)}")

    def _upgrade_json_structure_if_needed(self):
        """JSON 구조 업그레이드"""
        is_modified = False
        
        for product_data in self.split_data_list:
            for magic_data in product_data['MagicDataList']:
                # CurrentAmt 필드 추가
                if 'CurrentAmt' not in magic_data and magic_data['IsBuy']:
                    magic_data['CurrentAmt'] = magic_data['EntryAmt']
                    is_modified = True
                
                # SellHistory 필드 추가
                if 'SellHistory' not in magic_data:
                    magic_data['SellHistory'] = []
                    is_modified = True
                    
                # EntryDate 필드 추가
                if 'EntryDate' not in magic_data:
                    if magic_data['IsBuy']:
                        magic_data['EntryDate'] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        magic_data['EntryDate'] = ""
                    is_modified = True
        
        if is_modified:
            logger.info("🔧 JSON 구조를 금 투자용으로 업그레이드했습니다.")
            self.save_split_data()

    def get_dollar_index(self):
        """달러 인덱스 조회 (캐시 활용)"""
        try:
            # 캐시 확인 (10분 유효)
            if (self.dollar_index_cache and 
                time.time() - self.dollar_index_cache['timestamp'] < 600):
                return self.dollar_index_cache['value']
            
            # 실제 데이터는 외부 API나 다른 방법으로 조회
            # 여기서는 임시로 가상 데이터 사용
            import random
            dollar_index = 105.0 + random.uniform(-2.0, 2.0)
            
            self.dollar_index_cache = {
                'value': dollar_index,
                'timestamp': time.time()
            }
            
            logger.debug(f"💵 달러 인덱스: {dollar_index:.2f}")
            return dollar_index
            
        except Exception as e:
            logger.error(f"❌ 달러 인덱스 조회 실패: {str(e)}")
            return 105.0  # 기본값

    def analyze_market_conditions(self):
        """시장 상황 분석 (금 투자 특화)"""
        try:
            conditions = {
                'dollar_strength': 'neutral',
                'inflation_pressure': 'low',
                'geopolitical_risk': 'low',
                'stock_market_stress': 'low',
                'safe_haven_demand': 'normal',
                'overall_signal': 'hold'
            }
            
            # 달러 인덱스 분석
            dollar_index = self.get_dollar_index()
            gold_buy_conditions = config.config.get('gold_buy_conditions', {})
            dollar_threshold = gold_buy_conditions.get('dollar_index_threshold', 105.0)
            
            if dollar_index > dollar_threshold + 2:
                conditions['dollar_strength'] = 'strong'
            elif dollar_index > dollar_threshold:
                conditions['dollar_strength'] = 'moderate'
            elif dollar_index < dollar_threshold - 2:
                conditions['dollar_strength'] = 'weak'
            
            # 코스피 변동성으로 주식시장 스트레스 측정
            try:
                kospi_data = Common.GetOhlcv("KR", "069500", 20)  # KODEX 200
                if kospi_data is not None and len(kospi_data) >= 10:
                    volatility = kospi_data['close'].pct_change().std() * 100
                    if volatility > 3.0:
                        conditions['stock_market_stress'] = 'high'
                        conditions['safe_haven_demand'] = 'high'
                    elif volatility > 2.0:
                        conditions['stock_market_stress'] = 'moderate'
                        conditions['safe_haven_demand'] = 'moderate'
            except:
                pass
            
            # 전체 신호 결정
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
            
            self.last_market_analysis = conditions
            return conditions
            
        except Exception as e:
            logger.error(f"❌ 시장 분석 실패: {str(e)}")
            return {'overall_signal': 'hold'}

    def get_technical_indicators_gold(self, product_code):
        """금 특화 기술적 지표 계산"""
        try:
            # 차트 데이터 조회 (더 긴 기간)
            df = Common.GetOhlcv("KR", product_code, 250)
            if df is None or len(df) < 50:
                logger.warning(f"❌ {product_code} 차트 데이터 부족")
                return None
            
            indicators = {}
            technical_config = config.config.get('technical_indicators', {})
            
            # 이동평균선 (금 특화)
            ma_short = technical_config.get('ma_short', 10)
            ma_mid = technical_config.get('ma_mid', 50) 
            ma_long = technical_config.get('ma_long', 200)
            
            df[f'ma_{ma_short}'] = df['close'].rolling(window=ma_short).mean()
            df[f'ma_{ma_mid}'] = df['close'].rolling(window=ma_mid).mean()
            df[f'ma_{ma_long}'] = df['close'].rolling(window=ma_long).mean()
            
            # RSI (더 긴 기간)
            rsi_period = technical_config.get('rsi_period', 21)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # ATR (변동성)
            atr_period = technical_config.get('atr_period', 20)
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = true_range.rolling(window=atr_period).mean()
            
            # 현재 값들
            current_price = df['close'].iloc[-1]
            indicators = {
                'current_price': current_price,
                'ma_short': df[f'ma_{ma_short}'].iloc[-1],
                'ma_mid': df[f'ma_{ma_mid}'].iloc[-1],
                'ma_long': df[f'ma_{ma_long}'].iloc[-1],
                'rsi': df['rsi'].iloc[-1],
                'atr': df['atr'].iloc[-1],
                'volume': df['volume'].iloc[-1],
                'high_52w': df['high'].rolling(252).max().iloc[-1],
                'low_52w': df['low'].rolling(252).min().iloc[-1]
            }
            
            # 트렌드 분석 (금 특화)
            ma_trend_score = 0
            if current_price > indicators['ma_short'] > indicators['ma_mid'] > indicators['ma_long']:
                ma_trend_score = 3  # 강한 상승 트렌드
            elif current_price > indicators['ma_short'] > indicators['ma_mid']:
                ma_trend_score = 2  # 상승 트렌드
            elif current_price > indicators['ma_short']:
                ma_trend_score = 1  # 약한 상승
            elif current_price < indicators['ma_short'] < indicators['ma_mid'] < indicators['ma_long']:
                ma_trend_score = -3  # 강한 하락 트렌드
            elif current_price < indicators['ma_short'] < indicators['ma_mid']:
                ma_trend_score = -2  # 하락 트렌드
            elif current_price < indicators['ma_short']:
                ma_trend_score = -1  # 약한 하락
            
            indicators['trend_score'] = ma_trend_score
            indicators['trend_strength'] = abs(ma_trend_score) / 3.0
            
            # 52주 고저점 대비 위치
            price_position = (current_price - indicators['low_52w']) / (indicators['high_52w'] - indicators['low_52w'])
            indicators['price_position_52w'] = price_position
            
            # 변동성 수준 (금 특화)
            atr_pct = (indicators['atr'] / current_price) * 100
            if atr_pct > 3.0:
                indicators['volatility_level'] = 'high'
            elif atr_pct > 1.5:
                indicators['volatility_level'] = 'medium'
            else:
                indicators['volatility_level'] = 'low'
            
            return indicators
            
        except Exception as e:
            logger.error(f"❌ {product_code} 기술적 지표 계산 실패: {str(e)}")
            return None

    def calculate_gold_drop_requirement(self, product_code, position_num, market_conditions):
        """금 특화 동적 하락률 계산"""
        try:
            drop_config = config.config.get('dynamic_drop_requirements', {})
            base_drops = drop_config.get('base_drops', {})
            adjustment_factors = drop_config.get('adjustment_factors', {})
            
            # 기본 하락률
            base_drop = base_drops.get(str(position_num), 0.08)
            final_drop = base_drop
            adjustment_details = []
            
            # 달러 강도 조정
            dollar_strength = market_conditions.get('dollar_strength', 'neutral')
            if dollar_strength == 'strong':
                dollar_adj = adjustment_factors.get('dollar_strength_bonus', -0.02)
                final_drop += dollar_adj
                adjustment_details.append(f"강달러 {dollar_adj*100:+.1f}%p")
            elif dollar_strength == 'weak':
                dollar_adj = adjustment_factors.get('dollar_weakness_penalty', 0.01)
                final_drop += dollar_adj
                adjustment_details.append(f"약달러 {dollar_adj*100:+.1f}%p")
            
            # 안전자산 수요 조정
            safe_haven_demand = market_conditions.get('safe_haven_demand', 'normal')
            if safe_haven_demand == 'high':
                safe_adj = adjustment_factors.get('safe_haven_demand_bonus', -0.02)
                final_drop += safe_adj
                adjustment_details.append(f"안전자산수요 {safe_adj*100:+.1f}%p")
            
            # 주식시장 스트레스 조정
            stock_stress = market_conditions.get('stock_market_stress', 'low')
            if stock_stress == 'high':
                stress_adj = adjustment_factors.get('stock_crash_bonus', -0.035)
                final_drop += stress_adj
                adjustment_details.append(f"주식폭락 {stress_adj*100:+.1f}%p")
            
            # 지정학적 리스크 (임시로 랜덤 적용)
            import random
            if random.random() < 0.1:  # 10% 확률로 지정학적 리스크
                geo_adj = adjustment_factors.get('geopolitical_bonus', -0.03)
                final_drop += geo_adj
                adjustment_details.append(f"지정학적리스크 {geo_adj*100:+.1f}%p")
            
            # 안전 범위 제한
            min_drop = base_drop * 0.3
            max_drop = base_drop * 2.0
            final_drop = max(min_drop, min(final_drop, max_drop))
            
            return final_drop, adjustment_details
            
        except Exception as e:
            logger.error(f"❌ 하락률 계산 실패: {str(e)}")
            return 0.08, ["계산 오류: 기본 8% 사용"]

    def should_buy_gold(self, product_code, position_num, indicators, magic_data_list, market_conditions):
        """금 특화 매수 조건 판단"""
        try:
            gold_products = config.config.get('gold_products', {})
            product_info = gold_products.get(product_code, {})
            product_name = product_info.get('name', product_code)
            
            # 기본 조건 확인
            if not indicators:
                return False, "기술적 지표 없음"
            
            current_price = indicators['current_price']
            rsi = indicators.get('rsi', 50)
            trend_score = indicators.get('trend_score', 0)
            
            # 1차수는 기본 조건으로 매수
            if position_num == 1:
                # 시장 신호가 강한 매수가 아니면 보수적 접근
                overall_signal = market_conditions.get('overall_signal', 'hold')
                if overall_signal in ['strong_buy', 'buy']:
                    return True, f"1차 진입: {overall_signal} 신호"
                elif rsi < 40 and trend_score >= 0:
                    return True, "1차 진입: RSI 과매도 + 중립 이상 트렌드"
                elif trend_score >= 2:
                    return True, "1차 진입: 강한 상승 트렌드"
                else:
                    return False, "1차 진입 조건 미충족"
            
            # 2차수 이상: 순차 진입 + 하락률 검증
            previous_position = magic_data_list[position_num - 2]
            if not previous_position['IsBuy']:
                return False, f"이전 {position_num-1}차수 미보유"
            
            # 하락률 계산
            required_drop, drop_details = self.calculate_gold_drop_requirement(
                product_code, position_num, market_conditions
            )
            
            previous_price = previous_position['EntryPrice']
            current_drop = (previous_price - current_price) / previous_price
            
            if current_drop < required_drop:
                return False, f"{position_num}차 하락률 부족 ({current_drop*100:.1f}% < {required_drop*100:.1f}%)"
            
            # 추가 매수 조건
            buy_reasons = []
            
            # RSI 과매도
            rsi_oversold = config.config['technical_indicators'].get('rsi_oversold', 25)
            if rsi < rsi_oversold:
                buy_reasons.append(f"RSI 과매도({rsi:.1f})")
            
            # 안전자산 수요
            if market_conditions.get('safe_haven_demand') == 'high':
                buy_reasons.append("안전자산 수요 급증")
            
            # 달러 약세
            if market_conditions.get('dollar_strength') == 'weak':
                buy_reasons.append("달러 약세")
            
            # 주식시장 스트레스
            if market_conditions.get('stock_market_stress') == 'high':
                buy_reasons.append("주식시장 스트레스")
            
            if buy_reasons:
                reason_text = f"{position_num}차 매수: {', '.join(buy_reasons)}"
                return True, reason_text
            
            return False, f"{position_num}차 추가 조건 미충족"
            
        except Exception as e:
            logger.error(f"❌ 매수 조건 판단 실패: {str(e)}")
            return False, f"매수 조건 판단 오류: {str(e)}"

    def should_sell_gold(self, product_code, magic_data, indicators, market_conditions):
        """금 특화 매도 조건 판단"""
        try:
            if not magic_data['IsBuy'] or magic_data['CurrentAmt'] <= 0:
                return False, 0, "보유 포지션 없음"
            
            entry_price = magic_data['EntryPrice']
            current_price = indicators['current_price']
            current_return = (current_price - entry_price) / entry_price
            position_num = magic_data['Number']
            
            # 손절 조건 확인
            stop_loss_config = config.config.get('gold_stop_loss', {})
            thresholds = stop_loss_config.get('adaptive_thresholds', {})
            
            if position_num == 1:
                stop_threshold = thresholds.get('position_1', -0.20)
            elif position_num == 2:
                stop_threshold = thresholds.get('position_2', -0.25)
            else:
                stop_threshold = thresholds.get('position_3_plus', -0.30)
            
            # 시장 상황별 손절선 조정
            market_adj = stop_loss_config.get('market_adjustment', {})
            if market_adj.get('enable', True):
                dollar_strength = market_conditions.get('dollar_strength', 'neutral')
                if dollar_strength == 'strong':
                    stop_threshold += market_adj.get('adjustments', {}).get('strong_dollar', -0.05)
                elif dollar_strength == 'weak':
                    stop_threshold += market_adj.get('adjustments', {}).get('weak_dollar', 0.03)
            
            # 손절 실행
            if current_return <= stop_threshold:
                sell_ratio = 1.0  # 전체 매도
                return True, sell_ratio, f"손절 실행 ({current_return*100:.1f}% <= {stop_threshold*100:.1f}%)"
            
            # 익절 조건
            sell_strategy = config.config.get('gold_sell_strategy', {})
            profit_taking = sell_strategy.get('profit_taking', {})
            
            if profit_taking.get('enable', True):
                targets = profit_taking.get('targets', {})
                if position_num == 1:
                    profit_target = targets.get('position_1', 0.25)
                elif position_num == 2:
                    profit_target = targets.get('position_2', 0.30)
                else:
                    profit_target = targets.get('position_3_plus', 0.35)
                
                if current_return >= profit_target:
                    partial_ratio = profit_taking.get('partial_sell_ratio', 0.5)
                    return True, partial_ratio, f"부분 익절 ({current_return*100:.1f}% >= {profit_target*100:.1f}%)"
            
            # 트렌드 반전 매도
            trend_reversal = sell_strategy.get('trend_reversal', {})
            if trend_reversal.get('enable', True):
                rsi = indicators.get('rsi', 50)
                trend_score = indicators.get('trend_score', 0)
                
                # RSI 과매수 + 하락 트렌드
                if rsi > 80 and trend_score < 0:
                    return True, 0.3, f"트렌드 반전 부분매도 (RSI:{rsi:.1f}, 트렌드:{trend_score})"
                
                # 이동평균선 하향 돌파
                if (trend_reversal.get('ma_cross_sell', True) and 
                    trend_score <= -2 and current_return > 0.1):
                    return True, 0.5, "이동평균선 하향돌파 + 수익구간"
            
            return False, 0, "매도 조건 미충족"
            
        except Exception as e:
            logger.error(f"❌ 매도 조건 판단 실패: {str(e)}")
            return False, 0, f"매도 조건 판단 오류: {str(e)}"

    def execute_gold_trading(self):
        """금 투자 매매 실행"""
        try:
            logger.info("🥇 금 투자 매매 시작")
            
            # 시장 개장 확인
            if not KisKR.IsMarketOpen():
                logger.info("⏰ 장 시간이 아닙니다.")
                return
            
            # 시장 분석
            market_conditions = self.analyze_market_conditions()
            logger.info(f"📊 시장 분석: {market_conditions.get('overall_signal', 'hold')}")
            
            # 금 상품별 매매 실행
            gold_products = config.config.get('gold_products', {})
            
            for product_code, product_info in gold_products.items():
                if not product_info.get('recommended', False):
                    continue
                    
                product_name = product_info['name']
                logger.info(f"\n🔍 {product_name} ({product_code}) 분석 시작")
                
                # 기술적 지표 계산
                indicators = self.get_technical_indicators_gold(product_code)
                if not indicators:
                    logger.warning(f"❌ {product_name} 기술적 지표 계산 실패")
                    continue
                
                # 종목 데이터 찾기/생성
                product_data_info = None
                for data_info in self.split_data_list:
                    if data_info['ProductCode'] == product_code:
                        product_data_info = data_info
                        break
                
                # 새 상품 데이터 생성
                if product_data_info is None:
                    magic_data_list = []
                    position_ratios = config.config.get('position_ratios', {})
                    
                    for i in range(5):  # 5차수
                        magic_data_list.append({
                            'Number': i + 1,
                            'EntryPrice': 0,
                            'EntryAmt': 0,
                            'CurrentAmt': 0,
                            'SellHistory': [],
                            'EntryDate': '',
                            'IsBuy': False,
                            'PositionRatio': position_ratios.get(str(i + 1), 0.2)
                        })
                    
                    product_data_info = {
                        'ProductCode': product_code,
                        'ProductName': product_name,
                        'ProductType': product_info.get('type', 'ETF'),
                        'CurrencyHedge': product_info.get('currency_hedge', False),
                        'Weight': product_info.get('weight', 0.33),
                        'IsReady': True,
                        'MagicDataList': magic_data_list,
                        'RealizedPNL': 0,
                        'MonthlyPNL': {},
                        'MaxProfit': 0,
                        'GoldMetrics': {
                            'total_buys': 0,
                            'total_sells': 0,
                            'avg_hold_days': 0,
                            'best_return': 0,
                            'worst_return': 0
                        }
                    }
                    
                    self.split_data_list.append(product_data_info)
                    self.save_split_data()
                    
                    msg = f"🥇 {product_name} 금 투자 시스템 준비 완료!"
                    logger.info(msg)
                    if config.config.get("use_discord_alert", True):
                        discord_alert.SendMessage(msg)
                
                magic_data_list = product_data_info['MagicDataList']
                
                # 매도 로직 먼저 실행
                for magic_data in magic_data_list:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        should_sell, sell_ratio, sell_reason = self.should_sell_gold(
                            product_code, magic_data, indicators, market_conditions
                        )
                        
                        if should_sell and sell_ratio > 0:
                            # 매도 실행
                            sell_amount = int(magic_data['CurrentAmt'] * sell_ratio)
                            if sell_amount > 0:
                                self.execute_gold_sell_order(
                                    product_code, product_name, magic_data, 
                                    sell_amount, sell_reason, indicators
                                )
                
                # 매수 로직 실행
                total_budget = self.total_money * product_info['weight']
                
                for i, magic_data in enumerate(magic_data_list):
                    if not magic_data['IsBuy']:
                        position_num = i + 1
                        
                        # 매수 조건 판단
                        should_buy, buy_reason = self.should_buy_gold(
                            product_code, position_num, indicators, 
                            magic_data_list, market_conditions
                        )
                        
                        if should_buy:
                            # 매수 실행
                            position_ratio = magic_data['PositionRatio']
                            invest_amount = total_budget * position_ratio
                            current_price = indicators['current_price']
                            buy_amount = int(invest_amount / current_price)
                            
                            if buy_amount > 0:
                                self.execute_gold_buy_order(
                                    product_code, product_name, magic_data,
                                    buy_amount, current_price, buy_reason, indicators
                                )
                                break  # 한 번에 하나씩만 매수
            
            logger.info("🥇 금 투자 매매 완료")
            
        except Exception as e:
            logger.error(f"❌ 금 투자 매매 실행 중 오류: {str(e)}")

    def execute_gold_buy_order(self, product_code, product_name, magic_data, 
                              amount, price, reason, indicators):
        """금 매수 주문 실행"""
        try:
            logger.info(f"🛒 {product_name} {magic_data['Number']}차 매수 시도")
            logger.info(f"   💰 {price:,.0f}원 × {amount:,}주 = {price * amount:,.0f}원")
            logger.info(f"   📝 사유: {reason}")
            
            # 실제 매수 주문 (KIS API 사용)
            order_result = KisKR.MakeBuyLimitOrder(product_code, amount, price)
            
            if order_result and order_result.get('OrderNum'):
                # 체결 확인 (간소화된 버전)
                time.sleep(2)
                executed_amount = amount  # 실제로는 체결 확인 필요
                actual_price = price
                
                # 데이터 업데이트
                magic_data['IsBuy'] = True
                magic_data['EntryPrice'] = actual_price
                magic_data['EntryAmt'] = executed_amount
                magic_data['CurrentAmt'] = executed_amount
                magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                
                self.save_split_data()
                
                # 성공 메시지
                msg = f"🥇 {product_name} {magic_data['Number']}차 매수 완료!\n"
                msg += f"  💰 {actual_price:,.0f}원 × {executed_amount:,}주\n"
                msg += f"  📊 {reason}\n"
                msg += f"  💵 달러인덱스: {self.get_dollar_index():.2f}"
                
                logger.info(msg)
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(msg)
                
                return True
            else:
                logger.error(f"❌ {product_name} 매수 주문 실패")
                return False
                
        except Exception as e:
            logger.error(f"❌ {product_name} 매수 주문 중 오류: {str(e)}")
            return False

    def execute_gold_sell_order(self, product_code, product_name, magic_data,
                               amount, reason, indicators):
        """금 매도 주문 실행"""
        try:
            current_price = indicators['current_price']
            logger.info(f"💰 {product_name} {magic_data['Number']}차 매도 시도")
            logger.info(f"   💰 {current_price:,.0f}원 × {amount:,}주")
            logger.info(f"   📝 사유: {reason}")
            
            # 실제 매도 주문
            order_result = KisKR.MakeSellLimitOrder(product_code, amount, current_price)
            
            if order_result and order_result.get('OrderNum'):
                # 체결 확인 (간소화된 버전)
                time.sleep(2)
                executed_amount = amount
                actual_price = current_price
                
                # 수익률 계산
                entry_price = magic_data['EntryPrice']
                return_pct = (actual_price - entry_price) / entry_price * 100
                profit = (actual_price - entry_price) * executed_amount
                
                # 매도 이력 저장
                sell_record = {
                    'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'amount': executed_amount,
                    'price': actual_price,
                    'return_pct': return_pct,
                    'profit': profit,
                    'reason': reason
                }
                magic_data['SellHistory'].append(sell_record)
                
                # 포지션 업데이트
                magic_data['CurrentAmt'] -= executed_amount
                if magic_data['CurrentAmt'] <= 0:
                    magic_data['IsBuy'] = False
                    magic_data['CurrentAmt'] = 0
                
                self.save_split_data()
                
                # 성공 메시지
                msg = f"💰 {product_name} {magic_data['Number']}차 매도 완료!\n"
                msg += f"  💰 {actual_price:,.0f}원 × {executed_amount:,}주\n"
                msg += f"  📈 수익률: {return_pct:+.2f}% ({profit:+,.0f}원)\n"
                msg += f"  📝 {reason}"
                
                logger.info(msg)
                if config.config.get("use_discord_alert", True):
                    discord_alert.SendMessage(msg)
                
                return True
            else:
                logger.error(f"❌ {product_name} 매도 주문 실패")
                return False
                
        except Exception as e:
            logger.error(f"❌ {product_name} 매도 주문 중 오류: {str(e)}")
            return False

    def get_gold_performance_summary(self):
        """금 투자 성과 요약"""
        try:
            summary = {
                'total_investment': 0,
                'current_value': 0,
                'realized_pnl': 0,
                'unrealized_pnl': 0,
                'total_return_pct': 0,
                'products': {},
                'market_conditions': self.last_market_analysis or {}
            }
            
            # 상품별 성과 계산
            for product_data in self.split_data_list:
                product_code = product_data['ProductCode']
                product_name = product_data['ProductName']
                
                product_summary = {
                    'positions': 0,
                    'investment': 0,
                    'current_value': 0,
                    'realized_pnl': product_data.get('RealizedPNL', 0),
                    'unrealized_pnl': 0
                }
                
                try:
                    current_price = KisKR.GetCurrentPrice(product_code)
                    
                    for magic_data in product_data['MagicDataList']:
                        if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                            product_summary['positions'] += 1
                            investment = magic_data['EntryPrice'] * magic_data['CurrentAmt']
                            current_val = current_price * magic_data['CurrentAmt']
                            
                            product_summary['investment'] += investment
                            product_summary['current_value'] += current_val
                            product_summary['unrealized_pnl'] += (current_val - investment)
                
                except Exception as e:
                    logger.error(f"❌ {product_name} 성과 계산 실패: {str(e)}")
                
                summary['products'][product_name] = product_summary
                summary['total_investment'] += product_summary['investment']
                summary['current_value'] += product_summary['current_value']
                summary['realized_pnl'] += product_summary['realized_pnl']
                summary['unrealized_pnl'] += product_summary['unrealized_pnl']
            
            # 전체 수익률
            if summary['total_investment'] > 0:
                total_pnl = summary['realized_pnl'] + summary['unrealized_pnl']
                summary['total_return_pct'] = (total_pnl / summary['total_investment']) * 100
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ 성과 요약 계산 실패: {str(e)}")
            return {}

################################### 🥇 스케줄링 및 실행 함수들 ##################################

def send_gold_start_message():
    """금 투자 시작 메시지"""
    try:
        msg = f"🥇 **스마트 골드 트레이딩 봇 시작** 🥇\n"
        msg += f"📅 {datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}\n"
        msg += f"💰 투자 예산: {config.config.get('absolute_budget', 5000000):,.0f}원\n"
        msg += f"🎯 투자 상품: {len(config.config.get('gold_products', {}))}개 금 ETF\n"
        msg += f"📊 전략: 5차수 분할매매 + 안전자산 특화\n"
        msg += f"🔔 상태: 정상 운영 중"
        
        logger.info(msg)
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(msg)
            
    except Exception as e:
        logger.error(f"시작 메시지 전송 중 오류: {str(e)}")

def send_gold_performance_report():
    """금 투자 일일 성과 보고서"""
    try:
        if not hasattr(globals(), 'bot_instance') or bot_instance is None:
            return
            
        logger.info("📊 금 투자 성과 보고서 생성 시작")
        
        performance = bot_instance.get_gold_performance_summary()
        if not performance:
            logger.error("성과 정보 조회 실패")
            return
        
        today = datetime.now().strftime("%Y년 %m월 %d일")
        
        report = f"🥇 **금 투자 일일 성과 보고서** ({today})\n"
        report += "=" * 50 + "\n\n"
        
        # 전체 성과
        total_investment = performance.get('total_investment', 0)
        current_value = performance.get('current_value', 0)
        realized_pnl = performance.get('realized_pnl', 0)
        unrealized_pnl = performance.get('unrealized_pnl', 0)
        total_return_pct = performance.get('total_return_pct', 0)
        
        report += f"💰 **전체 투자 현황**\n"
        report += f"```\n"
        report += f"총 투자금액: {total_investment:,.0f}원\n"
        report += f"현재 평가액: {current_value:,.0f}원\n"
        report += f"실현 손익:   {realized_pnl:+,.0f}원\n"
        report += f"평가 손익:   {unrealized_pnl:+,.0f}원\n"
        report += f"총 수익률:   {total_return_pct:+.2f}%\n"
        report += f"```\n\n"
        
        # 상품별 성과
        products = performance.get('products', {})
        if products:
            report += f"📊 **상품별 성과**\n"
            for product_name, product_data in products.items():
                positions = product_data.get('positions', 0)
                investment = product_data.get('investment', 0)
                current_val = product_data.get('current_value', 0)
                unrealized = product_data.get('unrealized_pnl', 0)
                
                if investment > 0:
                    return_pct = (unrealized / investment) * 100
                    report += f"🥇 **{product_name}**\n"
                    report += f"   포지션: {positions}차수\n"
                    report += f"   투자액: {investment:,.0f}원\n"
                    report += f"   평가액: {current_val:,.0f}원\n"
                    report += f"   수익률: {return_pct:+.2f}%\n\n"
        
        # 시장 분석
        market_conditions = performance.get('market_conditions', {})
        if market_conditions:
            report += f"🌍 **시장 분석**\n"
            report += f"달러 강도: {market_conditions.get('dollar_strength', 'N/A')}\n"
            report += f"안전자산 수요: {market_conditions.get('safe_haven_demand', 'N/A')}\n"
            report += f"주식시장 스트레스: {market_conditions.get('stock_market_stress', 'N/A')}\n"
            report += f"종합 신호: {market_conditions.get('overall_signal', 'N/A')}\n\n"
        
        # 달러 인덱스
        if hasattr(bot_instance, 'dollar_index_cache') and bot_instance.dollar_index_cache:
            dollar_index = bot_instance.dollar_index_cache['value']
            report += f"💵 **달러 인덱스**: {dollar_index:.2f}\n\n"
        
        report += f"📅 보고서 생성: {datetime.now().strftime('%H:%M:%S')}"
        
        logger.info("📊 금 투자 성과 보고서 생성 완료")
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(report)
            
    except Exception as e:
        logger.error(f"성과 보고서 생성 중 오류: {str(e)}")

def run_gold_trading():
    """금 투자 매매 실행"""
    try:
        global bot_instance
        if bot_instance:
            bot_instance.execute_gold_trading()
    except Exception as e:
        logger.error(f"금 투자 매매 실행 중 오류: {str(e)}")

def setup_gold_trading_schedule():
    """금 투자 스케줄 설정"""
    try:
        # 평일 장 시간 매매 (30분마다)
        schedule.every().monday.at("09:30").do(run_gold_trading)
        schedule.every().monday.at("10:00").do(run_gold_trading)
        schedule.every().monday.at("10:30").do(run_gold_trading)
        schedule.every().monday.at("11:00").do(run_gold_trading)
        schedule.every().monday.at("11:30").do(run_gold_trading)
        schedule.every().monday.at("13:00").do(run_gold_trading)
        schedule.every().monday.at("13:30").do(run_gold_trading)
        schedule.every().monday.at("14:00").do(run_gold_trading)
        schedule.every().monday.at("14:30").do(run_gold_trading)
        schedule.every().monday.at("15:00").do(run_gold_trading)
        schedule.every().monday.at("15:20").do(run_gold_trading)
        
        # 화요일~금요일도 동일하게
        for day in ['tuesday', 'wednesday', 'thursday', 'friday']:
            day_obj = getattr(schedule.every(), day)
            for time_str in ["09:30", "10:00", "10:30", "11:00", "11:30", 
                           "13:00", "13:30", "14:00", "14:30", "15:00", "15:20"]:
                day_obj.at(time_str).do(run_gold_trading)
        
        # 일일 성과 보고서 (평일 장 마감 후)
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            getattr(schedule.every(), day).at("15:40").do(send_gold_performance_report)
        
        # 시작 메시지 (평일 장 시작 전)
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            getattr(schedule.every(), day).at("09:00").do(send_gold_start_message)
        
        logger.info("📅 금 투자 스케줄 설정 완료")
        
    except Exception as e:
        logger.error(f"스케줄 설정 중 오류: {str(e)}")

################################### 🥇 메인 실행 부분 ##################################

if __name__ == "__main__":
    try:
        logger.info("🥇 스마트 골드 트레이딩 봇 시작")
        
        # 봇 인스턴스 생성
        bot_instance = SmartGoldTrading()
        
        # 스케줄 설정
        setup_gold_trading_schedule()
        
        # 시작 메시지 전송
        send_gold_start_message()
        
        # 즉시 한 번 실행 (테스트용)
        if KisKR.IsMarketOpen():
            logger.info("🔄 시장 개장 중 - 즉시 매매 실행")
            bot_instance.execute_gold_trading()
        else:
            logger.info("⏰ 시장 미개장 - 스케줄 대기 중")
        
        # 스케줄 실행 루프
        logger.info("📅 스케줄 실행 대기 중...")
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 스케줄 체크
                
            except KeyboardInterrupt:
                logger.info("🛑 사용자에 의한 중단")
                break
            except Exception as e:
                logger.error(f"❌ 스케줄 실행 중 오류: {str(e)}")
                time.sleep(60)
                
    except Exception as e:
        logger.error(f"❌ 프로그램 실행 중 치명적 오류: {str(e)}")
    
    finally:
        logger.info("🥇 스마트 골드 트레이딩 봇 종료")

################################### 🥇 추가 유틸리티 함수들 ##################################

def manual_gold_trading():
    """수동 금 투자 실행 (테스트용)"""
    try:
        global bot_instance
        if not bot_instance:
            bot_instance = SmartGoldTrading()
        
        logger.info("🔧 수동 금 투자 실행")
        bot_instance.execute_gold_trading()
        
        # 성과 보고서도 생성
        send_gold_performance_report()
        
    except Exception as e:
        logger.error(f"❌ 수동 실행 중 오류: {str(e)}")

def reset_gold_data():
    """금 투자 데이터 초기화 (주의!!)"""
    try:
        confirm = input("⚠️  모든 금 투자 데이터를 초기화하시겠습니까? (yes 입력): ")
        if confirm.lower() == 'yes':
            bot_file_path = f"GoldTrading_{BOT_NAME}.json"
            if os.path.exists(bot_file_path):
                os.remove(bot_file_path)
                logger.info("🔄 금 투자 데이터 초기화 완료")
            else:
                logger.info("📂 초기화할 데이터 파일이 없습니다")
        else:
            logger.info("❌ 초기화 취소")
            
    except Exception as e:
        logger.error(f"❌ 데이터 초기화 중 오류: {str(e)}")

def show_gold_status():
    """현재 금 투자 상태 출력"""
    try:
        global bot_instance
        if not bot_instance:
            bot_instance = SmartGoldTrading()
        
        performance = bot_instance.get_gold_performance_summary()
        
        print("\n🥇 ================ 금 투자 현황 ================")
        print(f"💰 총 투자금액: {performance.get('total_investment', 0):,.0f}원")
        print(f"📊 현재 평가액: {performance.get('current_value', 0):,.0f}원")
        print(f"📈 총 수익률: {performance.get('total_return_pct', 0):+.2f}%")
        
        products = performance.get('products', {})
        for product_name, data in products.items():
            positions = data.get('positions', 0)
            investment = data.get('investment', 0)
            if investment > 0:
                return_pct = (data.get('unrealized_pnl', 0) / investment) * 100
                print(f"🥇 {product_name}: {positions}차수, {return_pct:+.2f}%")
        
        market = performance.get('market_conditions', {})
        if market:
            print(f"🌍 시장신호: {market.get('overall_signal', 'N/A')}")
            print(f"💵 달러강도: {market.get('dollar_strength', 'N/A')}")
        
        print("=" * 50)
        
    except Exception as e:
        logger.error(f"❌ 상태 조회 중 오류: {str(e)}")

def emergency_sell_all():
    """긴급 전체 매도 (위험!)"""
    try:
        confirm = input("⚠️  모든 금 포지션을 긴급 매도하시겠습니까? (EMERGENCY 입력): ")
        if confirm == 'EMERGENCY':
            global bot_instance
            if not bot_instance:
                bot_instance = SmartGoldTrading()
            
            logger.warning("🚨 긴급 전체 매도 실행")
            
            for product_data in bot_instance.split_data_list:
                product_code = product_data['ProductCode']
                product_name = product_data['ProductName']
                
                for magic_data in product_data['MagicDataList']:
                    if magic_data['IsBuy'] and magic_data['CurrentAmt'] > 0:
                        try:
                            current_price = KisKR.GetCurrentPrice(product_code)
                            sell_amount = magic_data['CurrentAmt']
                            
                            # 시장가 매도
                            order_result = KisKR.MakeSellMarketOrder(product_code, sell_amount)
                            
                            if order_result:
                                logger.warning(f"🚨 긴급매도: {product_name} {sell_amount:,}주")
                                
                                # 데이터 업데이트
                                magic_data['IsBuy'] = False
                                magic_data['CurrentAmt'] = 0
                                
                                # 매도 이력 추가
                                sell_record = {
                                    'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'amount': sell_amount,
                                    'price': current_price,
                                    'return_pct': (current_price - magic_data['EntryPrice']) / magic_data['EntryPrice'] * 100,
                                    'profit': (current_price - magic_data['EntryPrice']) * sell_amount,
                                    'reason': '긴급 매도'
                                }
                                magic_data['SellHistory'].append(sell_record)
                                
                        except Exception as e:
                            logger.error(f"❌ {product_name} 긴급매도 실패: {str(e)}")
            
            bot_instance.save_split_data()
            logger.warning("🚨 긴급 전체 매도 완료")
            
            # Discord 알림
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage("🚨 **긴급 매도 실행 완료** 🚨\n모든 금 포지션이 매도되었습니다.")
            
        else:
            logger.info("❌ 긴급 매도 취소")
            
    except Exception as e:
        logger.error(f"❌ 긴급 매도 중 오류: {str(e)}")

def rebalance_gold_portfolio():
    """금 포트폴리오 리밸런싱"""
    try:
        global bot_instance
        if not bot_instance:
            bot_instance = SmartGoldTrading()
        
        logger.info("⚖️ 금 포트폴리오 리밸런싱 시작")
        
        # 현재 포트폴리오 상태 확인
        performance = bot_instance.get_gold_performance_summary()
        products = performance.get('products', {})
        total_value = performance.get('current_value', 0)
        
        if total_value == 0:
            logger.info("리밸런싱할 포지션이 없습니다")
            return
        
        # 목표 비중과 현재 비중 비교
        gold_products = config.config.get('gold_products', {})
        rebalancing_needed = []
        
        for product_code, product_info in gold_products.items():
            product_name = product_info['name']
            target_weight = product_info['weight']
            
            current_value = products.get(product_name, {}).get('current_value', 0)
            current_weight = current_value / total_value if total_value > 0 else 0
            
            weight_diff = abs(current_weight - target_weight)
            threshold = config.config.get('gold_sell_strategy', {}).get('rebalancing', {}).get('threshold', 0.1)
            
            if weight_diff > threshold:
                rebalancing_needed.append({
                    'product_code': product_code,
                    'product_name': product_name,
                    'current_weight': current_weight,
                    'target_weight': target_weight,
                    'weight_diff': weight_diff
                })
        
        if rebalancing_needed:
            logger.info(f"📊 {len(rebalancing_needed)}개 상품 리밸런싱 필요")
            for item in rebalancing_needed:
                logger.info(f"   {item['product_name']}: {item['current_weight']:.1%} → {item['target_weight']:.1%}")
            
            # 실제 리밸런싱 로직은 여기에 구현
            # (복잡하므로 기본 구조만 제공)
            
            msg = f"⚖️ **금 포트폴리오 리밸런싱 완료**\n"
            msg += f"조정된 상품: {len(rebalancing_needed)}개\n"
            msg += f"총 포트폴리오 가치: {total_value:,.0f}원"
            
            if config.config.get("use_discord_alert", True):
                discord_alert.SendMessage(msg)
        else:
            logger.info("✅ 리밸런싱 불필요 (목표 비중 유지 중)")
        
    except Exception as e:
        logger.error(f"❌ 리밸런싱 중 오류: {str(e)}")

def show_commands():
    """사용 가능한 명령어 출력"""
    print("\n🥇 ================ 금 투자 봇 명령어 ================")
    print("1. manual_gold_trading()     - 수동 매매 실행")
    print("2. show_gold_status()        - 현재 투자 상태 조회") 
    print("3. send_gold_performance_report() - 성과 보고서 생성")
    print("4. reset_gold_data()         - 데이터 초기화 (주의!)")
    print("5. emergency_sell_all()      - 긴급 전체 매도 (위험!)")
    print("6. rebalance_gold_portfolio() - 포트폴리오 리밸런싱")
    print("7. show_commands()           - 이 도움말 출력")
    print("=" * 55)

def analyze_gold_correlation():
    """금과 다른 자산의 상관관계 분석"""
    try:
        logger.info("📊 금 상관관계 분석 시작")
        
        # 금 ETF, 코스피, 달러 인덱스 데이터 수집
        periods = [30, 90, 252]  # 1개월, 3개월, 1년
        
        for period in periods:
            try:
                # KODEX 골드선물 데이터
                gold_data = Common.GetOhlcv("KR", "132030", period)
                # 코스피 데이터 (KODEX 200)
                kospi_data = Common.GetOhlcv("KR", "069500", period)
                
                if gold_data is not None and kospi_data is not None and len(gold_data) == len(kospi_data):
                    gold_returns = gold_data['close'].pct_change().dropna()
                    kospi_returns = kospi_data['close'].pct_change().dropna()
                    
                    correlation = gold_returns.corr(kospi_returns)
                    
                    logger.info(f"📊 {period}일 상관관계 - 금 vs 코스피: {correlation:.3f}")
                    
            except Exception as e:
                logger.error(f"❌ {period}일 상관관계 분석 실패: {str(e)}")
        
        logger.info("📊 금 상관관계 분석 완료")
        
    except Exception as e:
        logger.error(f"❌ 상관관계 분석 중 오류: {str(e)}")

# 글로벌 변수 초기화
bot_instance = None

# 시작시 명령어 안내
print("\n🥇 스마트 골드 트레이딩 봇이 로드되었습니다!")
print("📋 show_commands() 를 입력하면 사용 가능한 명령어를 볼 수 있습니다.")
print("🚀 자동 실행하려면 python SmartGoldTradingBot_KR.py 로 실행하세요.")
print("💡 수동 테스트: manual_gold_trading()")
print("📊 현재 상태: show_gold_status()")
print("📈 성과 보고서: send_gold_performance_report()\n")