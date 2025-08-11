#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
타겟 종목 매매봇 (Target Stock Trading Bot) - Config 클래스 적용 완전 개선 버전
bb_trading.py의 방식을 참고하여 trend_trading.py의 기술적 분석을 적용
1. 미리 설정된 타겟 종목들에 대해서만 매매 진행
2. 종목별 개별 매매 파라미터 적용
3. technical_analysis.py의 고도화된 기술적 분석 활용
4. bb_trading.py의 체계적인 리스크 관리 적용
5. Config 클래스로 모든 설정 통합 관리
"""

import os
import sys
import time
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
import numpy as np
import pandas as pd
import concurrent.futures
import threading
from typing import List, Dict, Tuple, Optional, Union

# KIS API 함수 임포트
import KIS_Common as Common
import KIS_API_Helper_KR as KisKR
import discord_alert

# trend_trading.py에서 기술적 분석 클래스들 임포트
from technical_analysis import TechnicalIndicators, AdaptiveMarketStrategy, TrendFilter

import requests
from bs4 import BeautifulSoup

from pending_order_manager import PendingOrderManager, enhance_trading_state

# ================================== 섹터별 대표 종목 데이터베이스 ==================================

SECTOR_REPRESENTATIVE_STOCKS = {
    # 우주항공과국방 (타겟: 272210 한화시스템)
    '우주항공과국방': {
        'core_stocks': ['272210', '012450', '079550', '000880', '047810', '011210', '103140'],
        'names': ['한화시스템', '한화에어로스페이스', 'LIG넥스원', '한화', 'KAI한국항공우주산업', '현대위아', '풍산'],
        'keywords': ['우주항공과국방', '방산', '항공우주', '국방', '무기', '항공방산', '레이더', '엔진', '화약']
    },
    
    # 조선 (타겟: 010140 삼성중공업)
    '조선': {
        'core_stocks': ['010140', '009540', '067250', '329180', '042660'],
        'names': ['삼성중공업', 'HD한국조선해양', '현대미포조선', '현대중공업홀딩스', '한화오션'],
        'keywords': ['조선', '선박', '해양', '조선업', '해양플랜트']
    },
    
    # LNG밸류체인 (타겟: 017960 한국카본, 033500 동성화인텍)
    'LNG밸류체인': {
        'core_stocks': ['017960', '033500', '100090', '014620', '075580', '010140', '009540'],
        'names': ['한국카본', '동성화인텍', 'SK오션플랜트', '성광벤드', '세진중공업', '삼성중공업', 'HD한국조선해양'],
        'keywords': ['LNG', '보냉재', '복합소재', '탱크', '모듈', '배관', '피팅', '저온배관', 'LNG선']
    },
    
    # 반도체소재 (타겟: 007660 이수페타시스)
    '반도체소재': {
        'core_stocks': ['007660', '357780', '005290', '093370', '213420', '319660'],
        'names': ['이수페타시스', '솔브레인', '동진세미켐', '후성', '덕산네오룩스', '피에스케이'],
        'keywords': ['반도체', '소재', '특수가스', '세정액', 'OLED', '전자재료', '웨이퍼', '반도체장비']
    },
    
    # 화학 (이수페타시스 제거)
    '화학': {
        'core_stocks': ['011170', '009830', '010950', '051910', '001570', '004090'],
        'names': ['롯데케미칼', '한화솔루션', 'S-Oil', 'LG화학', '금양', '한국석유'],
        'keywords': ['화학', '석유화학', '정유', '화학제품', '범용화학']
    },
    
    # 건설 (타겟: 051600 한전KPS, 000720 현대건설)
    '건설': {
        'core_stocks': ['000720', '051600', '028260', '047040', '006360', '375500'],
        'names': ['현대건설', '한전KPS', '삼성물산', '대우건설', 'GS건설', 'DL이앤씨'],
        'keywords': ['건설', '건축', '토목', '인프라', '플랜트', '전력설비']
    },
    
    # 원전발전밸류체인 (타겟: 034020 두산에너빌리티)
    '원전발전밸류체인': {
        'core_stocks': ['034020', '051600', '010120', '064350', '005490', '000720', '028260'],
        'names': ['두산에너빌리티', '한전KPS', 'LS일렉트릭', '현대로템', 'POSCO홀딩스', '현대건설', '삼성물산'],
        'keywords': ['원전', '발전', '원자력', '터빈', '발전소', '전력', '원자로', '증기발생기', '보일러', '발전설비', '전력설비']
    },
    
    # 기계 (원전발전 제외한 일반 기계)
    '기계': {
        'core_stocks': ['267250', '010060', '008560', '003380', '042670'],
        'names': ['HD현대중공업', '두산밥캣', '삼양사', '현대중공업', '유니슨'],
        'keywords': ['기계', '산업기계', '중장비', '건설기계', '공작기계']
    }
}


################################### 설정 클래스 ##################################

class TradingConfig:
    """거래 설정 관리 클래스"""
    
    def __init__(self, config_path: str = "target_stock_config.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """설정 파일 로드"""
        self.config = self._load_config_file(self.config_path)
        if hasattr(self, '_logger_initialized'):
            logger.info("거래 설정 로드 완료")
            logger.info(f"예산 비율: {self.trade_budget_ratio*100}%, 최대 보유: {self.max_positions}개")
    
    def save_config(self):
        """설정 파일 저장"""
        self._save_config_file(self.config, self.config_path)
    
    def _load_config_file(self, config_path: str) -> Dict[str, any]:
        """설정 파일 로드 (내부 함수)"""

        default_config = {
            "target_stocks": {},
            
            # 전략 설정
            "trade_budget_ratio": 0.90,
            "max_positions": 8,
            "min_stock_price": 3000,
            "max_stock_price": 200000,
            
            # 🔥 손익 관리 설정 - 개선된 버전
            "stop_loss_ratio": -0.04,          # -2.5% → -4.0%로 완화
            "take_profit_ratio": 0.05,          # 분할매도 도입 후 8%에서 하향
            "trailing_stop_ratio": 0.025,       # 1.8% → 2.5%로 완화
            "max_daily_loss": -0.06,            # -4% → -6%로 완화
            "max_daily_profit": 0.08,           # 6% → 8%로 상향
            
            # 🔥 손절 지연 설정 (새로 추가)
            "stop_loss_delay_hours": 2,         # 매수 후 2시간은 손절 지연
            "volatility_stop_multiplier": 1.5,  # 변동성 기반 손절 배수
            "use_adaptive_stop": True,          # 적응형 손절 사용
            "min_holding_hours": 4,             # 최소 보유시간 4시간
            
            # 기술적 분석 설정
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,
            
            # 기타 설정
            "last_sector_update": "",
            "bot_name": "TargetStockBot",
            "use_discord_alert": True,
            "check_interval_minutes": 30
        }
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 기본 설정과 로드된 설정 병합
            def merge_config(default, loaded):
                result = default.copy()
                for key, value in loaded.items():
                    if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                        result[key] = merge_config(result[key], value)
                    else:
                        result[key] = value
                return result
            
            merged_config = merge_config(default_config, loaded_config)
            if hasattr(self, '_logger_initialized'):
                logger.info(f"설정 파일 로드 완료: {config_path}")
            return merged_config
        
        except FileNotFoundError:
            if hasattr(self, '_logger_initialized'):
                logger.warning(f"설정 파일 {config_path}을 찾을 수 없습니다. 기본값을 사용합니다.")
            return default_config
        
        except json.JSONDecodeError:
            if hasattr(self, '_logger_initialized'):
                logger.error(f"설정 파일 {config_path}의 형식이 올바르지 않습니다. 기본값을 사용합니다.")
            return default_config
        
        except Exception as e:
            if hasattr(self, '_logger_initialized'):
                logger.exception(f"설정 파일 로드 중 오류: {str(e)}")
            return default_config
    
    def _save_config_file(self, config: dict, config_path: str) -> None:
        """설정 파일 저장 (내부 함수)"""
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            if hasattr(self, '_logger_initialized'):
                logger.info(f"설정 파일 저장 완료: {config_path}")
        except Exception as e:
            if hasattr(self, '_logger_initialized'):
                logger.exception(f"설정 파일 저장 중 오류: {str(e)}")
    
    # =========================== 전략 설정 ===========================
    @property
    def trade_budget_ratio(self):
        """거래 예산 비율"""
        return self.config.get("trade_budget_ratio", 0.90)
    
    # =========================== 후보종목 풀 설정 (새로 추가) ===========================
    @property
    def use_candidate_pool(self):
        """후보종목 풀 방식 사용 여부"""
        return self.config.get("use_candidate_pool", False)
    
    @property
    def target_holding_count(self):
        """목표 보유 종목 수"""
        return self.config.get("target_holding_count", 3)
    
    @property
    def candidate_selection_method(self):
        """후보 선택 방식 (score/signal_strength)"""
        return self.config.get("candidate_selection_method", "score")
    
    @property
    def min_selection_score(self):
        """후보 선택 최소 점수"""
        return self.config.get("min_selection_score", 45)
    
    @property
    def rebalance_interval_hours(self):
        """재선택 주기 (시간)"""
        return self.config.get("rebalance_interval_hours", 24)
    
    @property
    def max_candidate_positions(self):
        """최대 후보종목 동시 보유 수"""
        return self.config.get("max_candidate_positions", 4)
    
    # =========================== 기존 max_positions 수정 ===========================

    @property 
    def max_positions(self):
        """최대 보유 종목 수 - 후보종목 풀 방식에서는 target_holding_count 사용"""
        if self.use_candidate_pool:
            return self.target_holding_count
        else:
            # 기존 방식: 활성 타겟 종목 수 기반
            active_count = 0
            for stock_code, config in self.target_stocks.items():
                if config.get('enabled', True):
                    active_count += 1
            return active_count if active_count > 0 else 1
    
    @property
    def min_stock_price(self):
        """최소 주가"""
        return self.config.get("min_stock_price", 3000)
    
    @property
    def max_stock_price(self):
        """최대 주가"""
        return self.config.get("max_stock_price", 200000)
    
    # =========================== 손익 관리 ===========================
    @property
    def stop_loss_ratio(self):
        """손절 비율"""
        return self.config.get("stop_loss_ratio", -0.025)
    
    @property
    def take_profit_ratio(self):
        """익절 비율"""
        return self.config.get("take_profit_ratio", 0.055)
    
    @property
    def trailing_stop_ratio(self):
        """트레일링 스탑 비율"""
        return self.config.get("trailing_stop_ratio", 0.018)
    
    @property
    def max_daily_loss(self):
        """일일 최대 손실 한도"""
        return self.config.get("max_daily_loss", -0.04)
    
    @property
    def max_daily_profit(self):
        """일일 최대 수익 한도"""
        return self.config.get("max_daily_profit", 0.06)

    @property
    def absolute_budget_strategy(self):
        """절대 예산 관리 전략 (strict, adaptive, proportional)"""
        return self.config.get("absolute_budget_strategy", "strict")
    
    @property
    def budget_loss_tolerance(self):
        """예산 손실 허용 비율 (adaptive 모드용)"""
        return self.config.get("budget_loss_tolerance", 0.2)
    
    @property
    def initial_total_asset(self):
        """초기 총 자산 (proportional 모드용)"""
        return self.config.get("initial_total_asset", 0)

    
    # =========================== 기술적 분석 ===========================
    @property
    def rsi_period(self):
        """RSI 기간"""
        return self.config.get("rsi_period", 14)
    
    @property
    def rsi_oversold(self):
        """RSI 과매도 기준"""
        return self.config.get("rsi_oversold", 30)
    
    @property
    def rsi_overbought(self):
        """RSI 과매수 기준"""
        return self.config.get("rsi_overbought", 70)
    
    @property
    def macd_fast(self):
        """MACD 빠른 기간"""
        return self.config.get("macd_fast", 12)
    
    @property
    def macd_slow(self):
        """MACD 느린 기간"""
        return self.config.get("macd_slow", 26)
    
    @property
    def macd_signal(self):
        """MACD 시그널 기간"""
        return self.config.get("macd_signal", 9)
    
    @property
    def bb_period(self):
        """볼린저밴드 기간"""
        return self.config.get("bb_period", 20)
    
    @property
    def bb_std(self):
        """볼린저밴드 표준편차"""
        return self.config.get("bb_std", 2.0)
    
    # =========================== 타겟 종목 관리 ===========================
    @property
    def target_stocks(self):
        """타겟 종목 딕셔너리"""
        return self.config.get("target_stocks", {})
    
    def get_stock_config(self, stock_code: str):
        """특정 종목의 설정 반환"""
        return self.target_stocks.get(stock_code, {})
    
    def update_target_stocks(self, target_stocks: dict):
        """타겟 종목 업데이트"""
        self.config["target_stocks"] = target_stocks
        self.save_config()
    
    # =========================== 기타 설정 ===========================
    @property
    def bot_name(self):
        """봇 이름"""
        return self.config.get("bot_name", "TargetStockBot")
    
    @property
    def last_sector_update(self):
        """마지막 섹터 업데이트 날짜"""
        return self.config.get("last_sector_update", "")
    
    def update_last_sector_update(self, date_str: str):
        """마지막 섹터 업데이트 날짜 갱신"""
        self.config["last_sector_update"] = date_str
        self.save_config()
    
    def update_setting(self, key: str, value):
        """설정 값 업데이트"""
        self.config[key] = value
        self.save_config()
        if hasattr(self, '_logger_initialized'):
            logger.info(f"설정 업데이트: {key} = {value}")
    
    def reload_config(self):
        """설정 파일 다시 로드"""
        self.load_config()

    # 기존 속성들 다음에 추가
    @property
    def use_absolute_budget(self):
        """절대 예산 사용 여부"""
        return self.config.get("use_absolute_budget", False)

    @property
    def absolute_budget(self):
        """절대 예산 금액 (원)"""
        return self.config.get("absolute_budget", 5000000)

    @property
    def use_adaptive_strategy(self):
        """적응형 전략 사용 여부"""
        return self.config.get("use_adaptive_strategy", True)

    @property
    def use_trend_filter(self):
        """트렌드 필터 사용 여부"""
        return self.config.get("use_trend_filter", True)
    
    # =========================== 분봉 타이밍 설정 ===========================
    @property
    def use_intraday_timing(self):
        """분봉 진입 타이밍 사용 여부"""
        return self.config.get("use_intraday_timing", False)  # 기본값 False (백테스트 고려)
    
    @property
    def intraday_check_interval(self):
        """분봉 체크 주기 (초)"""
        return self.config.get("intraday_check_interval", 30)
    
    @property
    def max_candidate_wait_hours(self):
        """최대 대기 시간"""
        return self.config.get("max_candidate_wait_hours", 2)


    def get_candidate_stocks(self):
        """후보종목 리스트 반환"""
        if not self.use_candidate_pool:
            return self.target_stocks  # 기존 방식
        
        candidates = {}
        for stock_code, config in self.target_stocks.items():
            if config.get('enabled', True) and config.get('is_candidate', True):
                candidates[stock_code] = config
        return candidates
    
################################### 로깅 처리 ##################################

log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

def log_namer(default_name):
    """로그 파일 이름 생성 함수"""
    base_filename, ext, date = default_name.split(".")
    return f"{base_filename}.{date}.{ext}"

# 로거 설정
logger = logging.getLogger('TargetStockTrader')
logger.setLevel(logging.INFO)

if logger.handlers:
    logger.handlers.clear()

log_file = os.path.join(log_directory, 'bb_trading.log')
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=3,
    encoding='utf-8'
)
file_handler.suffix = "%Y%m%d"
file_handler.namer = log_namer

console_handler = logging.StreamHandler()

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

KisKR.set_logger(logger)
Common.set_logger(logger)

import technical_analysis
technical_analysis.set_logger(logger)

# import news_analysis
# news_analysis.set_logger(logger)

# =========================== 전역 설정 인스턴스 ===========================
trading_config = None
pending_manager = None

def initialize_pending_manager():
    """미체결 주문 관리자 초기화"""
    global pending_manager
    
    pending_manager = PendingOrderManager(
        kis_api=KisKR,
        trading_config=trading_config, 
        discord_alert=discord_alert,
        logger=logger,
        fee_calculator=calculate_trading_fee  # 🎯 초기화시 바로 전달
    )
    
    logger.info("🔧 미체결 주문 관리자 초기화 완료")

def initialize_config(config_path: str = "target_stock_config.json"):
    """설정 초기화"""
    global trading_config
    trading_config = TradingConfig(config_path)
    trading_config._logger_initialized = True  # 로거 초기화 완료 표시
    trading_config.load_config()  # 로거 초기화 후 다시 로드하여 로그 출력
    return trading_config

def get_bot_name():
    """봇 이름 반환"""
    if trading_config:
        return Common.GetNowDist() + "_" + trading_config.bot_name
    else:
        return Common.GetNowDist() + "_TargetStockBot"

################################### 유틸리티 함수 ##################################

def select_target_stocks_from_candidates(buy_opportunities):
    """후보종목에서 매수 대상 선택 - 개별 분석 기준점수 사용 (개선됨)"""
    try:
        if not trading_config.use_candidate_pool:
            return buy_opportunities  # 기존 방식은 모든 기회 반환
        
        target_count = trading_config.target_holding_count
        selection_method = trading_config.candidate_selection_method
        
        logger.info(f"🎯 후보종목 선택: {len(buy_opportunities)}개 → 최대 {target_count}개 선택")
        
        # 🔥 핵심 변경: 개별 분석에서 사용한 기준점수 적용
        qualified_opportunities = []
        for opp in buy_opportunities:
            individual_min_score = opp.get('min_score', trading_config.min_selection_score)
            
            if opp['score'] >= individual_min_score:
                qualified_opportunities.append(opp)
                logger.info(f"✅ {opp['stock_name']}: {opp['score']}≥{individual_min_score}점")
            else:
                logger.info(f"❌ {opp['stock_name']}: {opp['score']}<{individual_min_score}점")
        
        if not qualified_opportunities:
            logger.info("   ⚠️ 개별 기준을 충족하는 종목이 없습니다")
            return []
        
        # 선택 방식에 따른 정렬 (기존 로직 유지)
        if selection_method == "score":
            qualified_opportunities.sort(key=lambda x: x['score'], reverse=True)
        elif selection_method == "signal_strength":
            def signal_priority(opp):
                strength = opp.get('signal_strength', 'NORMAL')
                score = opp['score']
                return (2 if strength == 'STRONG' else 1, score)
            qualified_opportunities.sort(key=signal_priority, reverse=True)
        
        # 현재 보유 종목 수 확인 후 남은 슬롯만큼만 선택 (기존 로직 유지)
        trading_state = load_trading_state()
        current_positions = len(trading_state.get('positions', {}))
        available_slots = max(0, target_count - current_positions)
        
        logger.info(f"   💼 현재 보유: {current_positions}개, 추가 가능: {available_slots}개")
        
        if available_slots == 0:
            logger.info("   ✋ 목표 보유 종목 수 달성, 추가 매수 없음")
            return []
        
        # 사용 가능한 슬롯만큼만 선택
        selected = qualified_opportunities[:available_slots]
        
        logger.info(f"🎯 최종 선택된 종목들:")
        for i, opp in enumerate(selected, 1):
            logger.info(f"   {i}. {opp['stock_name']}({opp['stock_code']}): "
                       f"{opp['score']}점 ({opp.get('signal_strength', 'NORMAL')})")
        
        return selected
        
    except Exception as e:
        logger.error(f"후보종목 선택 중 오류: {str(e)}")
        return []

def get_sector_info(stock_code):
    """네이버 금융을 통한 섹터 정보 조회"""
    try:
        logger.info(f"네이버 금융 조회 시작 (종목코드: {stock_code})...")
        
        # 네이버 금융 종목 페이지
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            response.encoding = 'euc-kr'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 업종 정보 찾기
            industry_element = soup.select_one('#content > div.section.trade_compare > h4 > em > a')
            if industry_element:
                sector = industry_element.get_text(strip=True)
                logger.info(f"네이버 금융에서 업종 정보를 찾았습니다: {sector}")
                
                return {
                    'sector': sector,
                    'industry': sector
                }
            else:
                logger.info("업종 정보를 찾을 수 없습니다.")
        else:
            logger.info(f"네이버 금융 접속 실패. 상태 코드: {response.status_code}")
            
        return {
            'sector': 'Unknown',
            'industry': 'Unknown'
        }
        
    except Exception as e:
        logger.info(f"섹터 정보 조회 중 에러: {str(e)}")
        return {
            'sector': 'Unknown',
            'industry': 'Unknown'
        }

def analyze_sector_risk(stock_code, target_config):
    """개선된 섹터별 위험도 분석 - 사전 정의된 섹터 대표 종목 활용"""
    try:
        stock_sector = target_config.get('sector', 'Unknown')
        stock_name = target_config.get('name', stock_code)
        
        logger.debug(f"섹터 위험도 분석 시작: {stock_name}({stock_code}) - {stock_sector}")
        
        # 1단계: 정확한 섹터 매칭
        matched_sector = None
        sector_data = None
        
        # 직접 매칭 시도
        if stock_sector in SECTOR_REPRESENTATIVE_STOCKS:
            matched_sector = stock_sector
            sector_data = SECTOR_REPRESENTATIVE_STOCKS[stock_sector]
            logger.debug(f"직접 섹터 매칭 성공: {matched_sector}")
        else:
            # 키워드 기반 매칭
            for sector_name, data in SECTOR_REPRESENTATIVE_STOCKS.items():
                keywords = data.get('keywords', [])
                if any(keyword in stock_sector for keyword in keywords):
                    matched_sector = sector_name
                    sector_data = data
                    logger.debug(f"키워드 매칭 성공: {stock_sector} → {matched_sector}")
                    break
                
                # 종목 코드 직접 포함 체크
                if stock_code in data.get('core_stocks', []):
                    matched_sector = sector_name
                    sector_data = data
                    logger.debug(f"종목코드 매칭 성공: {stock_code} → {matched_sector}")
                    break
        
        if not matched_sector or not sector_data:
            logger.debug(f"섹터 매칭 실패: {stock_sector}")
            return {
                'sector_risk': 'UNKNOWN_SECTOR', 
                'sector_decline_rate': 0, 
                'affected_stocks': [],
                'matched_sector': None
            }
        
        # 2단계: 대표 종목들의 변화율 분석
        core_stocks = sector_data.get('core_stocks', [])
        stock_names = sector_data.get('names', [])
        
        # 자기 자신 제외
        analysis_stocks = [(code, name) for code, name in zip(core_stocks, stock_names) if code != stock_code]
        
        if len(analysis_stocks) < 2:
            logger.debug(f"분석 대상 종목 부족: {len(analysis_stocks)}개")
            return {
                'sector_risk': 'INSUFFICIENT_STOCKS', 
                'sector_decline_rate': 0, 
                'affected_stocks': [],
                'matched_sector': matched_sector
            }
        
        # 3단계: 각 종목의 당일 변화율 조회
        declining_stocks = []
        total_decline = 0
        valid_count = 0
        analysis_results = []
        
        for stock_code_analysis, stock_name_analysis in analysis_stocks[:6]:  # 최대 6개 종목 분석
            try:
                current_price = KisKR.GetCurrentPrice(stock_code_analysis)
                if not current_price:
                    continue
                
                # 전일 대비 변화율 계산
                stock_data = get_stock_data(stock_code_analysis)
                if stock_data and stock_data.get('ohlcv_data') is not None:
                    df = stock_data['ohlcv_data']
                    if len(df) >= 2:
                        yesterday_close = df['close'].iloc[-2]
                        today_change = (current_price - yesterday_close) / yesterday_close * 100
                        
                        total_decline += today_change
                        valid_count += 1
                        
                        analysis_results.append({
                            'code': stock_code_analysis,
                            'name': stock_name_analysis,
                            'change_rate': today_change
                        })
                        
                        if today_change < -1.5:  # 1.5% 이상 하락
                            declining_stocks.append({
                                'code': stock_code_analysis,
                                'name': stock_name_analysis,
                                'decline_rate': today_change
                            })
                
                time.sleep(0.1)  # API 호출 간격
                
            except Exception as e:
                logger.debug(f"섹터 종목 분석 오류 ({stock_code_analysis}): {str(e)}")
                continue
        
        if valid_count == 0:
            return {
                'sector_risk': 'DATA_ERROR', 
                'sector_decline_rate': 0, 
                'affected_stocks': [],
                'matched_sector': matched_sector
            }
        
        # 4단계: 섹터 위험도 판정
        avg_decline_rate = total_decline / valid_count
        decline_ratio = len(declining_stocks) / valid_count
        
        # 위험도 등급 결정
        if avg_decline_rate < -3.0 and decline_ratio >= 0.7:  # 평균 -3% + 70% 종목 하락
            risk_level = 'CRITICAL'
        elif avg_decline_rate < -2.0 and decline_ratio >= 0.6:  # 평균 -2% + 60% 종목 하락
            risk_level = 'HIGH'
        elif avg_decline_rate < -1.0 and decline_ratio >= 0.5:  # 평균 -1% + 50% 종목 하락
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        # 5단계: 결과 로깅
        logger.info(f"📊 섹터 위험도 분석 완료: {matched_sector}")
        logger.info(f"   대상 종목: {stock_name}({stock_code})")
        logger.info(f"   위험도: {risk_level}")
        logger.info(f"   평균 변화율: {avg_decline_rate:.2f}%")
        logger.info(f"   하락 종목: {len(declining_stocks)}/{valid_count}개 ({decline_ratio*100:.1f}%)")
        
        # 주요 하락 종목 로깅
        if declining_stocks:
            logger.info(f"   주요 하락 종목:")
            for stock in declining_stocks[:3]:
                logger.info(f"     - {stock['name']}: {stock['decline_rate']:.2f}%")
        
        return {
            'sector_risk': risk_level,
            'sector_decline_rate': avg_decline_rate,
            'affected_stocks': declining_stocks,
            'matched_sector': matched_sector,
            'total_checked': valid_count,
            'analysis_results': analysis_results,
            'decline_ratio': decline_ratio
        }
        
    except Exception as e:
        logger.error(f"개선된 섹터 위험도 분석 중 오류: {str(e)}")
        return {
            'sector_risk': 'ERROR', 
            'sector_decline_rate': 0, 
            'affected_stocks': [],
            'matched_sector': None
        }

def _update_stock_info(target_stocks):
    """종목별 이름과 섹터 정보 자동 업데이트"""
    try:
        updated_count = 0
        
        for stock_code, stock_info in target_stocks.items():
            try:
                # 1. 종목명 조회 (KIS API)
                if "name" not in stock_info or not stock_info.get("name"):
                    stock_status = KisKR.GetCurrentStatus(stock_code)
                    if stock_status and isinstance(stock_status, dict):
                        stock_name = stock_status.get("StockName", f"종목{stock_code}")
                        target_stocks[stock_code]["name"] = stock_name
                        logger.info(f"종목명 업데이트: {stock_code} -> {stock_name}")
                
                # 2. 섹터 정보 조회 (네이버 금융)
                if stock_info.get("sector") == "Unknown" or not stock_info.get("sector"):
                    sector_info = get_sector_info(stock_code)
                    
                    if sector_info['sector'] != 'Unknown':
                        target_stocks[stock_code]["sector"] = sector_info['sector']
                        updated_count += 1
                        logger.info(f"섹터 정보 업데이트: {stock_code}({target_stocks[stock_code]['name']}) -> {sector_info['sector']}")
                    
                    # 연속 요청 방지
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.warning(f"종목 {stock_code} 정보 업데이트 중 오류: {str(e)}")
                # 기본값 설정
                if "name" not in target_stocks[stock_code]:
                    target_stocks[stock_code]["name"] = f"종목{stock_code}"
                if "sector" not in target_stocks[stock_code]:
                    target_stocks[stock_code]["sector"] = "Unknown"
        
        if updated_count > 0:
            logger.info(f"{updated_count}개 종목의 정보를 업데이트했습니다.")
        
        return target_stocks
        
    except Exception as e:
        logger.exception(f"종목 정보 업데이트 중 오류: {str(e)}")
        return target_stocks

def get_active_target_stock_count():
    """활성화된 타겟 종목 수 계산 - 후보종목 풀 방식 지원"""
    try:
        if trading_config.use_candidate_pool:
            return trading_config.target_holding_count
        else:
            active_count = 0
            for stock_code, config in trading_config.target_stocks.items():
                if config.get('enabled', True):
                    active_count += 1
            return active_count if active_count > 0 else 1
        
    except Exception as e:
        logger.error(f"활성 종목 수 계산 중 오류: {str(e)}")
        
        # 🔥 간단하고 안전한 기본값 처리
        try:
            # trading_config가 있고 후보종목 풀 방식이면 target_holding_count 사용
            if (trading_config and 
                hasattr(trading_config, 'use_candidate_pool') and 
                trading_config.use_candidate_pool):
                return getattr(trading_config, 'target_holding_count', 3)
            else:
                # 기존 방식이거나 설정이 없으면 최소값
                return 1
        except:
            # 최악의 상황: 아무것도 접근할 수 없을 때
            logger.error("모든 설정 접근 실패, 최소 안전값 사용")
            return 1

def get_per_stock_budget_limit():
    """종목별 예산 한도 계산 - 활성 종목 수 기반"""
    try:
        if trading_config.use_absolute_budget:
            total_budget = trading_config.absolute_budget
        else:
            balance = KisKR.GetBalance()
            if not balance:
                return 0
            total_money = float(balance.get('TotalMoney', 0))
            total_budget = total_money * trading_config.trade_budget_ratio
        
        active_stock_count = get_active_target_stock_count()
        
        if active_stock_count == 0:
            logger.warning("활성화된 타겟 종목이 없습니다")
            return 0
        
        per_stock_limit = total_budget / active_stock_count
        
        logger.debug(f"종목별 예산 한도: {per_stock_limit:,.0f}원 (총예산: {total_budget:,.0f}원 ÷ {active_stock_count}종목)")
        return per_stock_limit
        
    except Exception as e:
        logger.error(f"종목별 예산 한도 계산 중 오류: {str(e)}")
        return 0
    
def get_total_invested_amount(trading_state):
    """현재 총 투자된 금액 계산"""
    try:
        total_invested = 0
        for stock_code, position in trading_state['positions'].items():
            if stock_code in trading_config.target_stocks:
                invested_amount = position['entry_price'] * position['amount']
                total_invested += invested_amount
                logger.debug(f"투자된 금액 - {stock_code}: {invested_amount:,.0f}원")
        
        logger.info(f"📊 총 투자된 금액: {total_invested:,.0f}원")
        return total_invested
        
    except Exception as e:
        logger.error(f"총 투자 금액 계산 중 오류: {str(e)}")
        return 0

def get_invested_amount_for_stock(stock_code, trading_state):
    """현재 실제 보유 중인 투자금액 반환"""
    if stock_code in trading_state['positions']:
        position = trading_state['positions'][stock_code]
        return position['entry_price'] * position['amount']
    return 0

def get_available_budget(trading_state=None):
    """사용 가능한 예산 계산 - 이미 투자된 금액 차감 (개선됨)"""
    try:
        if trading_state is None:
            trading_state = load_trading_state()
        
        balance = KisKR.GetBalance()
        if not balance:
            logger.error("계좌 정보 조회 실패")
            return 0
            
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        
        if total_money <= 0:
            logger.warning("계좌 총 자산이 0 이하입니다.")
            return 0
        
        # 총 투자 가능 예산 계산
        if trading_config.use_absolute_budget:
            total_target_budget = trading_config.absolute_budget
            strategy = trading_config.absolute_budget_strategy
            
            logger.info(f"💰 절대금액 예산 모드: {strategy}")
            
            if strategy == "proportional":
                initial_asset = trading_config.initial_total_asset
                
                if initial_asset <= 0:
                    initial_asset = total_money
                    trading_config.config["initial_total_asset"] = initial_asset
                    trading_config.save_config()
                    logger.info(f"🎯 초기 총자산 설정: {initial_asset:,.0f}원")
                
                performance = (total_money - initial_asset) / initial_asset
                
                if performance > 0.2:
                    multiplier = min(1.4, 1.0 + performance * 0.3)
                elif performance > 0.1:
                    multiplier = 1.0 + performance * 0.5
                elif performance > 0.05:
                    multiplier = 1.0 + performance * 0.8
                elif performance > -0.05:
                    multiplier = 1.0
                elif performance > -0.1:
                    multiplier = max(0.95, 1.0 + performance * 0.2)
                elif performance > -0.2:
                    multiplier = max(0.85, 1.0 + performance * 0.15)
                else:
                    multiplier = max(0.7, 1.0 + performance * 0.1)
                
                total_target_budget = total_target_budget * multiplier
                
                logger.info(f"  - 성과 기반 조정: {performance*100:+.1f}% → 배율 {multiplier:.3f}")
                
            elif strategy == "adaptive":
                loss_tolerance = trading_config.budget_loss_tolerance
                min_budget = total_target_budget * (1 - loss_tolerance)
                
                if total_money >= min_budget:
                    total_target_budget = total_target_budget
                else:
                    total_target_budget = max(total_money, min_budget)
            
            # strategy == "strict"는 그대로 유지
        else:
            # 비율 기반 예산
            total_target_budget = total_money * trading_config.trade_budget_ratio
        
        # 🎯 핵심: 이미 투자된 금액 차감
        total_invested = get_total_invested_amount(trading_state)
        remaining_target_budget = total_target_budget - total_invested
        
        # 현금 잔고와 비교하여 최종 사용 가능 예산 결정
        available_budget = min(remaining_target_budget, remain_money)
        
        logger.info(f"📊 개선된 예산 계산:")
        logger.info(f"  - 목표 총예산: {total_target_budget:,.0f}원")
        logger.info(f"  - 이미 투자됨: {total_invested:,.0f}원")
        logger.info(f"  - 남은 목표예산: {remaining_target_budget:,.0f}원")
        logger.info(f"  - 현금 잔고: {remain_money:,.0f}원")
        logger.info(f"  - 사용가능 예산: {available_budget:,.0f}원")
        
        return max(0, available_budget)
        
    except Exception as e:
        logger.error(f"개선된 예산 계산 중 에러: {str(e)}")
        return 0

def get_remaining_budget_for_stock(stock_code, trading_state):
    """종목별 남은 예산 계산 - 디버깅 로그 추가"""
    per_stock_limit = get_per_stock_budget_limit()
    
    # 현재 보유 금액
    current_invested = get_invested_amount_for_stock(stock_code, trading_state)
    
    # 미체결 주문 금액
    pending_amount = pending_manager.get_committed_budget_for_stock(
        stock_code, trading_state, lambda code, state: 0  # 수정된 함수 사용
    )
    
    # 총 커밋된 금액
    total_committed = current_invested + pending_amount
    remaining = per_stock_limit - total_committed
    
    # 🔥 디버깅 로그 추가
    stock_name = trading_config.target_stocks.get(stock_code, {}).get('name', stock_code)
    logger.debug(f"💰 {stock_name}({stock_code}) 예산 계산:")
    logger.debug(f"   종목별 한도: {per_stock_limit:,}원")
    logger.debug(f"   현재 보유: {current_invested:,}원")
    logger.debug(f"   미체결 주문: {pending_amount:,}원")
    logger.debug(f"   총 사용중: {total_committed:,}원")
    logger.debug(f"   남은 예산: {remaining:,}원")
    
    return max(0, remaining)

def get_budget_info_message():
    """예산 정보 메시지 생성 - 후보종목 풀 방식 지원 (완전 개선 버전)"""
    try:
        trading_state = load_trading_state()
        balance = KisKR.GetBalance()
        
        if not balance:
            return "계좌 정보 조회 실패"
        
        total_money = float(balance.get('TotalMoney', 0))
        remain_money = float(balance.get('RemainMoney', 0))
        
        # 예산 계산
        total_available_budget = get_available_budget(trading_state)
        total_invested = get_total_invested_amount(trading_state)
        per_stock_limit = get_per_stock_budget_limit()
        
        # 🔥 후보종목 풀 방식 여부에 따른 메시지 구성
        if trading_config.use_candidate_pool:
            # 후보종목 풀 방식
            candidate_stocks = trading_config.get_candidate_stocks()
            msg = f"🎯 후보종목 풀 운용 방식\n"
            msg += f"후보 풀: {len(candidate_stocks)}개\n"
            msg += f"목표 보유: {trading_config.target_holding_count}개\n"
            msg += f"선택 방식: {trading_config.candidate_selection_method}\n"
            msg += f"최소 점수: {trading_config.min_selection_score}점\n"
        else:
            # 기존 방식
            if trading_config.use_absolute_budget:
                strategy = trading_config.absolute_budget_strategy
                absolute_budget = trading_config.absolute_budget
                msg = f"📊 기존 타겟 종목 운용 ({strategy})\n"
                msg += f"설정 예산: {absolute_budget:,}원\n"
            else:
                msg = f"📊 기존 타겟 종목 운용 (비율)\n"
                msg += f"설정 비율: {trading_config.trade_budget_ratio*100:.1f}%\n"
        
        msg += f"현재 자산: {total_money:,}원\n"
        msg += f"현금 잔고: {remain_money:,}원\n"
        msg += f"\n📈 투자 현황:\n"
        msg += f"• 총 투자됨: {total_invested:,}원\n"
        msg += f"• 사용가능: {total_available_budget:,}원\n"
        msg += f"• 종목별 한도: {per_stock_limit:,}원\n"
        
        # 현재 보유 종목 현황
        current_positions = len(trading_state.get('positions', {}))
        target_count = get_active_target_stock_count()
        
        msg += f"\n🎯 보유 현황:\n"
        msg += f"• 현재 보유: {current_positions}개\n"
        msg += f"• 목표/최대: {target_count}개\n"
        
        if trading_config.use_candidate_pool:
            available_slots = max(0, target_count - current_positions)
            msg += f"• 추가 가능: {available_slots}개\n"
        
        # 🔥 종목별 투자 현황 (방식별로 다르게 표시)
        if trading_config.use_candidate_pool:
            # 후보종목 풀: 현재 보유 종목만 표시
            msg += f"\n🎯 현재 선택된 종목:\n"
            
            if current_positions > 0:
                for stock_code, position in trading_state.get('positions', {}).items():
                    if stock_code in trading_config.target_stocks:
                        stock_name = trading_config.target_stocks[stock_code].get('name', stock_code)
                        invested = get_invested_amount_for_stock(stock_code, trading_state)
                        usage_rate = (invested / per_stock_limit * 100) if per_stock_limit > 0 else 0
                        
                        # 추가 정보: 수익률 표시
                        try:
                            entry_price = position.get('entry_price', 0)
                            current_price = KisKR.GetCurrentPrice(stock_code)
                            if entry_price > 0 and current_price:
                                profit_rate = (current_price - entry_price) / entry_price * 100
                                profit_sign = "📈" if profit_rate > 0 else "📉" if profit_rate < 0 else "➡️"
                                msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%) {profit_sign} {profit_rate:+.1f}%\n"
                            else:
                                msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%)\n"
                        except:
                            msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%)\n"
                
                # 후보종목 풀 추가 정보
                if available_slots > 0:
                    candidate_stocks = trading_config.get_candidate_stocks()
                    unselected_candidates = []
                    for code, config in candidate_stocks.items():
                        if code not in trading_state.get('positions', {}):
                            unselected_candidates.append(config.get('name', code))
                    
                    if unselected_candidates:
                        msg += f"\n📋 대기 중인 후보종목:\n"
                        for i, name in enumerate(unselected_candidates[:3], 1):  # 최대 3개만 표시
                            msg += f"{i}. {name}\n"
                        if len(unselected_candidates) > 3:
                            msg += f"... 외 {len(unselected_candidates)-3}개\n"
            else:
                msg += "• 현재 보유 종목 없음\n"
                
                # 후보종목 리스트 표시
                candidate_stocks = trading_config.get_candidate_stocks()
                msg += f"\n📋 후보종목 풀 ({len(candidate_stocks)}개):\n"
                for i, (code, config) in enumerate(candidate_stocks.items(), 1):
                    name = config.get('name', code)
                    msg += f"{i}. {name}\n"
        else:
            # 기존 방식: 모든 활성 종목 표시
            msg += f"\n🎯 종목별 투자 현황:\n"
            for stock_code, stock_config in trading_config.target_stocks.items():
                if not stock_config.get('enabled', True):
                    continue
                    
                stock_name = stock_config.get('name', stock_code)
                invested = get_invested_amount_for_stock(stock_code, trading_state)
                remaining = get_remaining_budget_for_stock(stock_code, trading_state)
                usage_rate = (invested / per_stock_limit * 100) if per_stock_limit > 0 else 0
                
                if invested > 0:
                    # 수익률 정보 추가
                    try:
                        if stock_code in trading_state.get('positions', {}):
                            position = trading_state['positions'][stock_code]
                            entry_price = position.get('entry_price', 0)
                            current_price = KisKR.GetCurrentPrice(stock_code)
                            if entry_price > 0 and current_price:
                                profit_rate = (current_price - entry_price) / entry_price * 100
                                profit_sign = "📈" if profit_rate > 0 else "📉" if profit_rate < 0 else "➡️"
                                msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%) {profit_sign} {profit_rate:+.1f}%\n"
                            else:
                                msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%)\n"
                        else:
                            msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%)\n"
                    except:
                        msg += f"• {stock_name}: {invested:,}원 ({usage_rate:.1f}%)\n"
                else:
                    msg += f"• {stock_name}: 투자 대기 (가능: {remaining:,}원)\n"
        
        # 🔥 추가 정보: 매수 대기 종목이 있으면 표시
        if 'buy_candidates' in trading_state and trading_state['buy_candidates']:
            candidate_count = len(trading_state['buy_candidates'])
            msg += f"\n⏳ 매수 대기 종목: {candidate_count}개\n"
            for stock_code, candidate_info in trading_state['buy_candidates'].items():
                stock_name = candidate_info['opportunity']['stock_name']
                wait_start = datetime.datetime.fromisoformat(candidate_info['wait_start_time'])
                wait_hours = (datetime.datetime.now() - wait_start).total_seconds() / 3600
                daily_score = candidate_info.get('daily_score', 0)
                msg += f"• {stock_name}: {wait_hours:.1f}시간 대기 ({daily_score}점)\n"
        
        return msg
        
    except Exception as e:
        logger.error(f"개선된 예산 정보 메시지 생성 중 에러: {str(e)}")
        logger.exception("상세 에러 정보:")
        return f"예산 정보 조회 실패: {str(e)}"

def get_safe_config_value(target_config, key, default_value):
    """종목별 설정에서 안전하게 값 가져오기"""
    try:
        # 종목별 설정에서 먼저 찾기
        if key in target_config and target_config[key] is not None:
            return target_config[key]
        
        # 전역 설정에서 찾기
        if hasattr(trading_config, key):
            return getattr(trading_config, key)
        
        # 기본값 반환
        return default_value
        
    except Exception as e:
        logger.warning(f"설정값 조회 중 오류 ({key}): {str(e)}")
        return default_value        

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
    """거래 시간 체크 - 장 초반 안정화 대기 적용 (완전 개선 버전)"""
    try:
        # 1단계: 휴장일 체크
        if KisKR.IsTodayOpenCheck() == 'N':
            logger.info("📅 오늘은 휴장일입니다.")
            return False, False

        # 2단계: 장 상태 조회
        market_status = KisKR.MarketStatus()
        if market_status is None or not isinstance(market_status, dict):
            logger.warning("⚠️ 장 상태 확인 실패")
            return False, False
            
        status_code = market_status.get('Status', '')
        current_time = datetime.datetime.now().time()
        
        # 3단계: 상태 코드별 상세 로그
        status_desc = {
            '': '장 개시전',
            '1': '장 개시전', 
            '2': '장중',
            '3': '장 종료후',
            '4': '시간외단일가',
            '0': '동시호가'
        }
        
        current_status = status_desc.get(status_code, f'알 수 없음({status_code})')
        logger.debug(f"🕐 현재 시각: {current_time.strftime('%H:%M:%S')} - 장 상태: {current_status}")
        
        # 4단계: 동시호가 시간 (8:30-9:00)
        is_market_open = False
        if status_code == '0':
            if (current_time >= datetime.time(8, 30) and 
                current_time < datetime.time(9, 0)):
                is_market_open = True
                logger.info(f"📊 동시호가 시간: {current_time.strftime('%H:%M:%S')}")
            else:
                logger.debug(f"⏰ 동시호가 시간 외: {current_time.strftime('%H:%M:%S')}")
        
        # 5단계: 정규장 시간 체크 (9:00-15:30) + 장 초반 안정화 적용
        is_trading_time = False
        if status_code == '2':
            # 🔥 핵심 개선: 장 초반 안정화 대기 설정
            market_open_time = datetime.time(9, 0)
            market_close_time = datetime.time(15, 30)
            
            # 설정에서 대기 시간 가져오기 (기본 15분)
            wait_minutes = getattr(trading_config, 'market_open_wait_minutes', 15)
            stabilization_time = datetime.time(9, wait_minutes)  # 기본 09:15
            
            # 🚨 장 초반 안정화 대기 (09:00~09:15)
            if (current_time >= market_open_time and 
                current_time < stabilization_time):
                logger.info(f"⏰ 장 초반 안정화 대기 중: {current_time.strftime('%H:%M:%S')} "
                          f"(대기 종료: {stabilization_time.strftime('%H:%M')})")
                logger.info(f"   📊 이유: 분봉 데이터 부족 및 변동성 과열 방지")
                logger.info(f"   🕐 남은 시간: {(datetime.datetime.combine(datetime.date.today(), stabilization_time) - datetime.datetime.combine(datetime.date.today(), current_time)).total_seconds() / 60:.0f}분")
                return False, False
            
            # ✅ 정상 거래 시간 (09:15~15:30)
            elif (current_time >= stabilization_time and 
                  current_time < market_close_time):
                is_trading_time = True
                
                # 첫 거래 시간 진입시 알림
                if current_time < datetime.time(9, 20):  # 09:20 이전에만
                    logger.info(f"🎯 정상 거래 시간 진입: {current_time.strftime('%H:%M:%S')} "
                              f"(안정화 완료)")
            
            # 장 시작 전 (09:00 이전)
            elif current_time < market_open_time:
                logger.debug(f"⏰ 장 시작 전: {current_time.strftime('%H:%M:%S')} "
                           f"(시작 예정: {market_open_time.strftime('%H:%M')})")
            
            # 장 마감 후 (15:30 이후)
            elif current_time >= market_close_time:
                logger.debug(f"📊 장 마감: {current_time.strftime('%H:%M:%S')} "
                           f"(마감 시간: {market_close_time.strftime('%H:%M')})")
            
        # 6단계: 기타 상태 처리
        elif status_code == '1':  # 장 개시전
            logger.debug(f"⏰ 장 개시 전 대기 중: {current_time.strftime('%H:%M:%S')}")
        elif status_code == '3':  # 장 종료후
            logger.debug(f"📊 장 종료 후: {current_time.strftime('%H:%M:%S')}")
        elif status_code == '4':  # 시간외단일가
            logger.debug(f"📊 시간외단일가: {current_time.strftime('%H:%M:%S')}")
        else:
            logger.warning(f"⚠️ 알 수 없는 장 상태: {status_code} at {current_time.strftime('%H:%M:%S')}")
        
        # 7단계: 결과 요약 로그
        if is_trading_time:
            logger.debug(f"✅ 거래 가능: {current_time.strftime('%H:%M:%S')} (상태: {current_status})")
        elif is_market_open:
            logger.debug(f"📊 동시호가: {current_time.strftime('%H:%M:%S')} (상태: {current_status})")
        else:
            logger.debug(f"⏸️ 거래 불가: {current_time.strftime('%H:%M:%S')} (상태: {current_status})")
        
        return is_trading_time, is_market_open
        
    except Exception as e:
        logger.error(f"❌ 거래 시간 체크 중 오류: {str(e)}")
        logger.exception("❌ 거래 시간 체크 상세 오류 정보:")
        
        # 🔥 예외 발생시 안전 모드 (거래 중단)
        return False, False

def detect_stock_environment(stock_code):
    """개별 종목의 환경 감지 - 시장 환경 감지 로직 적용"""
    try:
        # 개별 종목 데이터 조회
        stock_data = KisKR.GetOhlcvNew(stock_code, 'D', 60, adj_ok=1)
        
        if stock_data is None or stock_data.empty:
            return "sideways"  # 기본값
        
        # 이동평균선 계산
        stock_data['MA5'] = stock_data['close'].rolling(window=5).mean()
        stock_data['MA20'] = stock_data['close'].rolling(window=20).mean()
        stock_data['MA60'] = stock_data['close'].rolling(window=60).mean()
        
        # RSI 계산 추가
        stock_data['RSI'] = TechnicalIndicators.calculate_rsi(stock_data)
        
        # MACD 계산 추가
        stock_data[['MACD', 'Signal', 'Histogram']] = TechnicalIndicators.calculate_macd(
            stock_data, 
            fast_period=12, 
            slow_period=26, 
            signal_period=9
        )
        
        # 볼린저 밴드 계산 추가
        stock_data[['MiddleBand', 'UpperBand', 'LowerBand']] = TechnicalIndicators.calculate_bollinger_bands(
            stock_data,
            period=20,
            num_std=2.0
        )
        
        # 추세 강도 계산 (ADX 대용)
        trend_strength = abs((stock_data['MA20'].iloc[-1] / stock_data['MA20'].iloc[-21] - 1) * 100)
        
        # 이동평균선 방향성
        ma5_slope = (stock_data['MA5'].iloc[-1] / stock_data['MA5'].iloc[-6] - 1) * 100
        ma20_slope = (stock_data['MA20'].iloc[-1] / stock_data['MA20'].iloc[-21] - 1) * 100
        
        # 변동성 측정 (볼린저 밴드 폭)
        recent_bandwidth = (stock_data['UpperBand'].iloc[-1] - stock_data['LowerBand'].iloc[-1]) / stock_data['MiddleBand'].iloc[-1] * 100
        avg_bandwidth = ((stock_data['UpperBand'] - stock_data['LowerBand']) / stock_data['MiddleBand']).rolling(window=20).mean().iloc[-1] * 100
        
        # 볼륨 트렌드 (거래량 증가 여부)
        volume_trend = (stock_data['volume'].iloc[-5:].mean() / stock_data['volume'].iloc[-20:-5].mean()) > 1.0
        
        # MACD 히스토그램 방향
        histogram_direction = stock_data['Histogram'].diff().iloc[-1] > 0
        
        # 최근 연속 상승/하락 일수 계산
        price_changes = stock_data['close'].pct_change().iloc[-10:]
        consecutive_up = 0
        consecutive_down = 0
        current_consecutive_up = 0
        current_consecutive_down = 0
        
        for change in price_changes:
            if change > 0:
                current_consecutive_up += 1
                current_consecutive_down = 0
            elif change < 0:
                current_consecutive_down += 1
                current_consecutive_up = 0
            else:
                current_consecutive_up = 0
                current_consecutive_down = 0
                
            consecutive_up = max(consecutive_up, current_consecutive_up)
            consecutive_down = max(consecutive_down, current_consecutive_down)
        
        # 상승장 지표 점수
        uptrend_score = 0
        if ma5_slope > 0.8: uptrend_score += 2
        if ma20_slope > 0.3: uptrend_score += 2
        if stock_data['MA5'].iloc[-1] > stock_data['MA20'].iloc[-1]: uptrend_score += 1
        if stock_data['close'].iloc[-1] > stock_data['MA20'].iloc[-1]: uptrend_score += 1
        if stock_data['RSI'].iloc[-1] > 55: uptrend_score += 1
        if histogram_direction: uptrend_score += 1
        if volume_trend: uptrend_score += 1
        if consecutive_up >= 3: uptrend_score += 1
        
        # 하락장 지표 점수
        downtrend_score = 0
        if ma5_slope < -0.8: downtrend_score += 2
        if ma20_slope < -0.3: downtrend_score += 2
        if stock_data['MA5'].iloc[-1] < stock_data['MA20'].iloc[-1]: downtrend_score += 1
        if stock_data['close'].iloc[-1] < stock_data['MA20'].iloc[-1]: downtrend_score += 1
        if stock_data['RSI'].iloc[-1] < 45: downtrend_score += 1
        if not histogram_direction: downtrend_score += 1
        if not volume_trend: downtrend_score += 1
        if consecutive_down >= 3: downtrend_score += 1
        
        # 횡보장 지표 - 변동성 관련
        sideways_score = 0
        if abs(ma5_slope) < 0.5: sideways_score += 2  # 단기 이동평균 기울기가 완만함
        if abs(ma20_slope) < 0.3: sideways_score += 2  # 중기 이동평균 기울기가 완만함
        if recent_bandwidth < avg_bandwidth: sideways_score += 2  # 최근 변동성이 평균보다 낮음
        if stock_data['RSI'].iloc[-1] > 40 and stock_data['RSI'].iloc[-1] < 60: sideways_score += 2  # RSI가 중간 영역
        if abs(stock_data['close'].iloc[-1] - stock_data['MA20'].iloc[-1]) / stock_data['MA20'].iloc[-1] < 0.02: sideways_score += 2  # 종가가 20일선 근처
        
        # 점수 기반 종목 환경 판단
        logger.debug(f"종목 {stock_code} 환경 점수 - 상승: {uptrend_score}, 하락: {downtrend_score}, 횡보: {sideways_score}")
        
        # 명확한 상승장/하락장 조건
        if uptrend_score >= 7 and uptrend_score > downtrend_score + 3 and uptrend_score > sideways_score + 2:
            result = "uptrend"
        elif downtrend_score >= 7 and downtrend_score > uptrend_score + 3 and downtrend_score > sideways_score + 2:
            result = "downtrend"
        # 횡보장 조건 강화
        elif sideways_score >= 6 and abs(uptrend_score - downtrend_score) <= 2:
            result = "sideways"
        # 약한 상승/하락 추세
        elif uptrend_score > downtrend_score + 2:
            result = "uptrend"
        elif downtrend_score > uptrend_score + 2:
            result = "downtrend"
        # 그 외는 횡보장으로 판단
        else:
            result = "sideways"
        
        logger.debug(f"종목 {stock_code} 환경 판정: {result}")
        return result
        
    except Exception as e:
        logger.warning(f"종목 {stock_code} 환경 감지 중 오류: {str(e)}")
        return "sideways"  # 기본값

################################### 기술적 분석 함수 ##################################

def get_stock_data(stock_code):
    """종목 데이터 조회 및 기술적 분석 (Config 적용)"""
    try:
        # 일봉 데이터 조회
        df = Common.GetOhlcv("KR", stock_code, 60)
        
        if df is None or len(df) < 30:
            logger.error(f"{stock_code}: 데이터 부족")
            return None
        
        # 현재가 조회
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price or current_price <= 0:
            logger.error(f"{stock_code}: 현재가 조회 실패")
            return None
        
        # Config에서 기술적 지표 설정값 사용
        df['RSI'] = TechnicalIndicators.calculate_rsi(df, trading_config.rsi_period)
        
        macd_data = TechnicalIndicators.calculate_macd(
            df, trading_config.macd_fast, trading_config.macd_slow, trading_config.macd_signal
        )
        df[['MACD', 'Signal', 'Histogram']] = macd_data
        
        bb_data = TechnicalIndicators.calculate_bollinger_bands(
            df, trading_config.bb_period, trading_config.bb_std
        )
        df[['MiddleBand', 'UpperBand', 'LowerBand']] = bb_data
        
        # 이동평균선 계산
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        
        # ATR 계산
        df['ATR'] = TechnicalIndicators.calculate_atr(df)
        
        # 지지/저항선 분석
        sr_data = TechnicalIndicators.detect_support_resistance(df)
        
        return {
            'stock_code': stock_code,
            'current_price': current_price,
            'ohlcv_data': df,
            'rsi': df['RSI'].iloc[-1] if not pd.isna(df['RSI'].iloc[-1]) else 50,
            'macd': df['MACD'].iloc[-1] if not pd.isna(df['MACD'].iloc[-1]) else 0,
            'macd_signal': df['Signal'].iloc[-1] if not pd.isna(df['Signal'].iloc[-1]) else 0,
            'macd_histogram': df['Histogram'].iloc[-1] if not pd.isna(df['Histogram'].iloc[-1]) else 0,
            'bb_upper': df['UpperBand'].iloc[-1] if not pd.isna(df['UpperBand'].iloc[-1]) else 0,
            'bb_middle': df['MiddleBand'].iloc[-1] if not pd.isna(df['MiddleBand'].iloc[-1]) else 0,
            'bb_lower': df['LowerBand'].iloc[-1] if not pd.isna(df['LowerBand'].iloc[-1]) else 0,
            'ma5': df['MA5'].iloc[-1] if not pd.isna(df['MA5'].iloc[-1]) else 0,
            'ma20': df['MA20'].iloc[-1] if not pd.isna(df['MA20'].iloc[-1]) else 0,
            'ma60': df['MA60'].iloc[-1] if not pd.isna(df['MA60'].iloc[-1]) else 0,
            'support': sr_data.get("support", 0),
            'resistance': sr_data.get("resistance", 0),
            'atr': df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0
        }
        
    except Exception as e:
        logger.error(f"종목 데이터 조회 중 에러: {str(e)}")
        return None

################################### 매매 신호 분석 ##################################

def check_sector_based_market_trend(target_stocks):
    """섹터 기반 시장 추세 분석 - 기존 지수 분석 대체"""
    try:
        logger.info("📊 섹터 기반 시장 추세 분석 시작...")
        
        # ===== 1단계: 타겟 종목들의 섹터 분류 =====
        sector_groups = {}
        total_stocks = 0
        
        for stock_code, target_config in target_stocks.items():
            if not target_config.get('enabled', True):
                continue
                
            sector = target_config.get('sector', 'Unknown')
            if sector not in sector_groups:
                sector_groups[sector] = []
            
            sector_groups[sector].append({
                'code': stock_code,
                'name': target_config.get('name', stock_code),
                'config': target_config
            })
            total_stocks += 1
        
        logger.info(f"📋 섹터별 분류 완료: {len(sector_groups)}개 섹터, {total_stocks}개 종목")
        for sector, stocks in sector_groups.items():
            stock_names = [s['name'] for s in stocks]
            logger.info(f"   📊 {sector}: {len(stocks)}개 - {', '.join(stock_names)}")
        
        # ===== 2단계: 각 섹터별 추세 분석 =====
        sector_trends = {}
        overall_trends = {
            'bullish_sectors': [],
            'bearish_sectors': [],
            'mixed_sectors': [],
            'unknown_sectors': []
        }
        
        for sector, stocks in sector_groups.items():
            logger.info(f"\n🔍 {sector} 섹터 분석 중...")
            
            sector_analysis_results = []
            
            # 각 종목의 섹터 위험도 분석
            for stock_info in stocks:
                stock_code = stock_info['code']
                stock_name = stock_info['name']
                target_config = stock_info['config']
                
                try:
                    # 기존 analyze_sector_risk 함수 활용
                    sector_analysis = analyze_sector_risk(stock_code, target_config)
                    
                    sector_analysis_results.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'sector_risk': sector_analysis.get('sector_risk', 'UNKNOWN'),
                        'sector_decline_rate': sector_analysis.get('sector_decline_rate', 0),
                        'matched_sector': sector_analysis.get('matched_sector', sector),
                        'analysis_results': sector_analysis.get('analysis_results', [])
                    })
                    
                    logger.debug(f"   📈 {stock_name}: {sector_analysis.get('sector_risk', 'UNKNOWN')} "
                               f"({sector_analysis.get('sector_decline_rate', 0):.2f}%)")
                    
                except Exception as e:
                    logger.warning(f"   ❌ {stock_name} 섹터 분석 실패: {str(e)}")
                    continue
            
            # ===== 3단계: 섹터별 종합 판단 =====
            if not sector_analysis_results:
                logger.warning(f"⚠️ {sector} 섹터: 분석 데이터 없음")
                sector_trends[sector] = 'UNKNOWN'
                overall_trends['unknown_sectors'].append(sector)
                continue
            
            # 섹터 내 평균 변화율 계산
            valid_rates = [r['sector_decline_rate'] for r in sector_analysis_results 
                          if r['sector_decline_rate'] != 0]
            
            if not valid_rates:
                sector_avg_change = 0
            else:
                sector_avg_change = sum(valid_rates) / len(valid_rates)
            
            # 위험도 분포 계산
            risk_distribution = {}
            for result in sector_analysis_results:
                risk = result['sector_risk']
                risk_distribution[risk] = risk_distribution.get(risk, 0) + 1
            
            # 섹터 추세 판정
            total_analyzed = len(sector_analysis_results)
            critical_ratio = risk_distribution.get('CRITICAL', 0) / total_analyzed
            high_ratio = risk_distribution.get('HIGH', 0) / total_analyzed
            medium_ratio = risk_distribution.get('MEDIUM', 0) / total_analyzed
            low_ratio = risk_distribution.get('LOW', 0) / total_analyzed
            
            # 섹터 추세 결정 로직
            if critical_ratio >= 0.5 or (critical_ratio + high_ratio) >= 0.7:
                # 50% 이상이 CRITICAL이거나, 70% 이상이 HIGH 이상
                sector_trend = 'BEARISH'
                overall_trends['bearish_sectors'].append(sector)
                logger.info(f"📉 {sector} 섹터: 하락 추세 (위험 {critical_ratio+high_ratio:.1%})")
                
            elif low_ratio >= 0.6 and sector_avg_change >= -0.5:
                # 60% 이상이 LOW 위험도이고 평균 변화율이 양호
                sector_trend = 'BULLISH'
                overall_trends['bullish_sectors'].append(sector)
                logger.info(f"📈 {sector} 섹터: 상승 추세 (안전 {low_ratio:.1%}, 평균 {sector_avg_change:.2f}%)")
                
            else:
                # 그 외는 혼조
                sector_trend = 'MIXED'
                overall_trends['mixed_sectors'].append(sector)
                logger.info(f"📊 {sector} 섹터: 혼조 (평균 {sector_avg_change:.2f}%)")
            
            sector_trends[sector] = sector_trend
            
            # 섹터 상세 정보 저장
            sector_trends[f"{sector}_detail"] = {
                'average_change': sector_avg_change,
                'risk_distribution': risk_distribution,
                'analyzed_count': total_analyzed,
                'trend': sector_trend,
                'stocks': sector_analysis_results
            }
        
        # ===== 4단계: 전체 시장 상황 종합 판단 =====
        logger.info(f"\n📊 전체 시장 상황 종합 판단...")
        
        total_sectors = len(sector_groups)
        bullish_count = len(overall_trends['bullish_sectors'])
        bearish_count = len(overall_trends['bearish_sectors'])
        mixed_count = len(overall_trends['mixed_sectors'])
        unknown_count = len(overall_trends['unknown_sectors'])
        
        # 전체 시장 조건 판정
        if bearish_count >= total_sectors * 0.6:
            # 60% 이상 섹터가 하락
            market_condition = 'BEARISH'
            logger.info("📉 전체 시장: 하락장 (다수 섹터 약세)")
            
        elif bullish_count >= total_sectors * 0.6:
            # 60% 이상 섹터가 상승
            market_condition = 'BULLISH'
            logger.info("📈 전체 시장: 상승장 (다수 섹터 강세)")
            
        elif (bullish_count + mixed_count) >= total_sectors * 0.7:
            # 70% 이상이 상승+혼조
            market_condition = 'BULLISH'
            logger.info("📈 전체 시장: 상승장 (섹터 전반 양호)")
            
        elif (bearish_count + mixed_count) >= total_sectors * 0.7:
            # 70% 이상이 하락+혼조
            market_condition = 'BEARISH'
            logger.info("📉 전체 시장: 하락장 (섹터 전반 약세)")
            
        else:
            # 그 외는 혼조
            market_condition = 'MIXED'
            logger.info("📊 전체 시장: 혼조장 (섹터별 엇갈림)")
        
        # ===== 5단계: 결과 요약 및 반환 =====
        logger.info(f"\n📊 섹터 기반 시장 분석 완료:")
        logger.info(f"   전체 판단: {market_condition}")
        logger.info(f"   상승 섹터: {bullish_count}개 - {', '.join(overall_trends['bullish_sectors'])}")
        logger.info(f"   하락 섹터: {bearish_count}개 - {', '.join(overall_trends['bearish_sectors'])}")
        logger.info(f"   혼조 섹터: {mixed_count}개 - {', '.join(overall_trends['mixed_sectors'])}")
        
        if unknown_count > 0:
            logger.info(f"   분석불가: {unknown_count}개 - {', '.join(overall_trends['unknown_sectors'])}")
        
        # 결과 반환
        market_trend_result = {
            'market_condition': market_condition,
            'analysis_method': 'SECTOR_BASED',
            'total_sectors': total_sectors,
            'sector_distribution': {
                'bullish': bullish_count,
                'bearish': bearish_count, 
                'mixed': mixed_count,
                'unknown': unknown_count
            },
            'sector_trends': sector_trends,
            'sector_details': overall_trends,
            'analysis_time': datetime.datetime.now().isoformat()
        }
        
        return market_trend_result
        
    except Exception as e:
        logger.error(f"❌ 섹터 기반 시장 분석 중 오류: {str(e)}")
        logger.exception("❌ 섹터 분석 상세 오류:")
        
        # 에러 발생시 안전한 기본값 반환
        return {
            'market_condition': 'UNKNOWN',
            'analysis_method': 'SECTOR_BASED_ERROR',
            'error': str(e),
            'sector_trends': {},
            'analysis_time': datetime.datetime.now().isoformat()
        }

def get_sector_trend_for_stock(stock_code, target_config, market_trend_data):
    """특정 종목의 섹터 추세 점수 계산"""
    try:
        stock_sector = target_config.get('sector', 'Unknown')
        stock_name = target_config.get('name', stock_code)
        
        # 섹터 추세 데이터 가져오기
        sector_trends = market_trend_data.get('sector_trends', {})
        sector_trend = sector_trends.get(stock_sector, 'UNKNOWN')
        sector_detail = sector_trends.get(f"{stock_sector}_detail", {})
        
        # 섹터 점수 계산
        if sector_trend == 'BULLISH':
            sector_score = 10  # 강한 가점
            trend_description = "섹터 상승 추세"
        elif sector_trend == 'MIXED':
            sector_score = 0   # 중립
            trend_description = "섹터 혼조"
        elif sector_trend == 'BEARISH':
            sector_score = -10  # 강한 감점
            trend_description = "섹터 하락 추세"
        else:
            sector_score = 0   # 분석 불가시 중립
            trend_description = "섹터 분석 불가"
        
        # 상세 정보
        avg_change = sector_detail.get('average_change', 0)
        risk_distribution = sector_detail.get('risk_distribution', {})
        
        logger.debug(f"📊 {stock_name} 섹터 점수: {sector_score}점 ({trend_description})")
        if avg_change != 0:
            logger.debug(f"   섹터 평균 변화율: {avg_change:.2f}%")
        
        return {
            'sector_score': sector_score,
            'sector_trend': sector_trend,
            'trend_description': trend_description,
            'sector_average_change': avg_change,
            'sector_risk_distribution': risk_distribution
        }
        
    except Exception as e:
        logger.warning(f"종목 {stock_code} 섹터 점수 계산 오류: {str(e)}")
        return {
            'sector_score': 0,
            'sector_trend': 'UNKNOWN',
            'trend_description': "섹터 점수 계산 오류",
            'sector_average_change': 0,
            'sector_risk_distribution': {}
        }

def check_market_trend():
    """기존 함수 호환성을 위한 래퍼 함수"""
    try:
        # 섹터 기반 분석 실행
        market_trend_data = check_sector_based_market_trend(trading_config.target_stocks)
        
        # 기존 형식으로 변환하여 반환
        market_condition = market_trend_data.get('market_condition', 'UNKNOWN')
        
        # 기존 코드와의 호환성을 위해 kospi_trend, kosdaq_trend도 추가
        if market_condition == 'BULLISH':
            kospi_trend = kosdaq_trend = 'UP'
        elif market_condition == 'BEARISH':
            kospi_trend = kosdaq_trend = 'DOWN'
        else:
            kospi_trend = kosdaq_trend = 'MIXED'
        
        compatible_result = {
            'kospi_trend': kospi_trend,
            'kosdaq_trend': kosdaq_trend, 
            'market_condition': market_condition,
            'analysis_method': 'SECTOR_BASED',
            'sector_data': market_trend_data  # 추가 정보
        }
        
        logger.info(f"📊 시장 추세 분석 완료 (섹터 기반): {market_condition}")
        return compatible_result
        
    except Exception as e:
        logger.error(f"❌ 시장 추세 분석 오류: {str(e)}")
        
        # 기존 형식의 안전한 기본값
        return {
            'kospi_trend': 'UNKNOWN',
            'kosdaq_trend': 'UNKNOWN',
            'market_condition': 'UNKNOWN',
            'analysis_method': 'SECTOR_BASED_ERROR',
            'error': str(e)
        }

def analyze_index_trend(index_data, index_name="지수"):
    """지수 추세 분석 - 디버깅 강화 버전"""
    try:
        logger.debug(f"📊 {index_name} 추세 분석 시작...")
        
        if index_data is None:
            logger.error(f"❌ {index_name} 데이터가 None")
            return 'UNKNOWN'
        
        if len(index_data) < 10:
            logger.error(f"❌ {index_name} 데이터 부족: {len(index_data)}일 (최소 10일 필요)")
            return 'UNKNOWN'
        
        logger.debug(f"✅ {index_name} 데이터 충분: {len(index_data)}일")
        
        # 데이터 컬럼 확인
        required_columns = ['close']
        for col in required_columns:
            if col not in index_data.columns:
                logger.error(f"❌ {index_name} 데이터에 {col} 컬럼 없음")
                logger.error(f"   사용가능 컬럼: {list(index_data.columns)}")
                return 'UNKNOWN'
        
        # 이동평균 계산
        try:
            ma5 = index_data['close'].rolling(5).mean().iloc[-1]
            ma20 = index_data['close'].rolling(20).mean().iloc[-1]
            current_price = index_data['close'].iloc[-1]
            
            logger.debug(f"📊 {index_name} 가격 정보:")
            logger.debug(f"   현재가: {current_price:.2f}")
            logger.debug(f"   5일 평균: {ma5:.2f}")
            logger.debug(f"   20일 평균: {ma20:.2f}")
            
        except Exception as ma_error:
            logger.error(f"❌ {index_name} 이동평균 계산 오류: {str(ma_error)}")
            return 'UNKNOWN'
        
        # 추세 방향 판단
        ma_trend = 'SIDEWAYS'
        if ma5 > ma20:
            ma_trend = 'UP'
        elif ma5 < ma20:
            ma_trend = 'DOWN'
        
        price_position = 'SIDEWAYS'
        if current_price > ma5:
            price_position = 'UP'
        elif current_price < ma5:
            price_position = 'DOWN'
        
        logger.debug(f"📊 {index_name} 추세 요소:")
        logger.debug(f"   이동평균 추세: {ma_trend} (5일평균 vs 20일평균)")
        logger.debug(f"   가격 위치: {price_position} (현재가 vs 5일평균)")
        
        # 최근 5일 변화율 계산
        price_change_5d = 0
        try:
            if len(index_data) >= 6:
                price_5d_ago = index_data['close'].iloc[-6]
                price_change_5d = (current_price / price_5d_ago - 1) * 100
                logger.debug(f"📊 {index_name} 5일 변화율: {price_change_5d:.2f}%")
            else:
                logger.warning(f"⚠️ {index_name} 5일 변화율 계산 불가 (데이터 부족)")
        except Exception as change_error:
            logger.error(f"❌ {index_name} 변화율 계산 오류: {str(change_error)}")
        
        # 종합 판단
        result = 'SIDEWAYS'
        
        if ma_trend == 'UP' and price_position == 'UP' and price_change_5d > 1:
            result = 'UP'
            logger.debug(f"📈 {index_name} 상승 추세: 이동평균↑ + 가격위치↑ + 5일변화율{price_change_5d:.1f}%")
        elif ma_trend == 'DOWN' and price_position == 'DOWN' and price_change_5d < -1:
            result = 'DOWN'
            logger.debug(f"📉 {index_name} 하락 추세: 이동평균↓ + 가격위치↓ + 5일변화율{price_change_5d:.1f}%")
        else:
            logger.debug(f"📊 {index_name} 횡보 추세: 명확한 방향성 없음")
        
        logger.debug(f"✅ {index_name} 추세 분석 완료: {result}")
        return result
            
    except Exception as e:
        logger.error(f"❌ {index_name} 추세 분석 중 오류: {str(e)}")
        logger.exception(f"❌ {index_name} 추세 분석 상세 오류:")
        return 'UNKNOWN'

def analyze_buy_signal(stock_data, target_config, market_trend=None):
    """매수 신호 분석 - 조건부 차단 방식 (균형잡힌 버전) - 시장 추세 필터 추가"""
    try:
        signals = []
        score = 0
        
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        rsi = stock_data['rsi']
        df = stock_data['ohlcv_data']
        
        # ========== 디버깅 로그 시작 ==========
        stock_name = target_config.get('name', stock_code)
        logger.info(f"🎯 [{stock_code}] {stock_name} 매수 신호 분석 시작")
        logger.info(f"📊 [{stock_code}] 기본 데이터: 현재가 {current_price:,}원, RSI {rsi:.1f}")
        
        # 🔍 극한 조건들 미리 계산
        
        # 1) 가격 위치 계산
        price_position = 0.5  # 기본값
        if len(df) >= 20:
            recent_low_20d = df['low'].iloc[-20:].min()
            recent_high_20d = df['high'].iloc[-20:].max()
            if recent_high_20d > recent_low_20d:
                price_position = (current_price - recent_low_20d) / (recent_high_20d - recent_low_20d)
        
        logger.info(f"📍 [{stock_code}] 가격 위치: {price_position*100:.1f}% (20일 구간)")
        
        # 2) 볼린저밴드 위치 계산
        bb_upper = stock_data.get('bb_upper', 0)
        bb_position_ratio = 0.5  # 기본값
        if bb_upper > 0:
            bb_position_ratio = current_price / bb_upper
        
        logger.info(f"📈 [{stock_code}] 볼린저밴드: 상단 {bb_upper:,.0f}원, 비율 {bb_position_ratio:.3f}")
        
        # 3) 거래량 비율 계산
        volume_ratio = 1.0
        if len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume_20d = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = recent_volume / avg_volume_20d if avg_volume_20d > 0 else 1
        
        logger.info(f"📊 [{stock_code}] 거래량: 최근 {recent_volume:,}주, 평균 대비 {volume_ratio:.2f}배")
        
        # 4) 연속 상승 일수 계산
        consecutive_up_days = 0
        if len(df) >= 5:
            recent_changes = df['close'].pct_change().iloc[-5:]
            for change in recent_changes:
                if change > 0.025:  # 2.5% 이상 상승
                    consecutive_up_days += 1
                else:
                    break
        
        logger.info(f"📈 [{stock_code}] 연속 상승: {consecutive_up_days}일")
        
        # 🚨 극한 조건 정의 (4개 중 2개 이상시 차단)
        extreme_conditions = [
            rsi >= 90,                      # RSI 90% 이상 (일진파워 94% 해당)
            price_position >= 0.90,         # 20일 구간 90% 이상 고점  
            bb_position_ratio >= 1.01,      # 볼밴 상단 1% 돌파
            volume_ratio >= 4.0,            # 거래량 4배 이상 급증
        ]
        
        extreme_count = sum(extreme_conditions)
        
        logger.info(f"⚠️ [{stock_code}] 극한 조건: {extreme_count}/4개 (RSI≥90: {extreme_conditions[0]}, 고점≥90%: {extreme_conditions[1]}, 볼밴돌파: {extreme_conditions[2]}, 거래량≥4배: {extreme_conditions[3]})")
        
        # 🚨 2개 이상 극한 조건 만족시 차단
        if extreme_count >= 2:
            extreme_reasons = []
            if extreme_conditions[0]: extreme_reasons.append(f"RSI 극과매수({rsi:.1f}%)")
            if extreme_conditions[1]: extreme_reasons.append(f"고점권({price_position*100:.1f}%)")
            if extreme_conditions[2]: extreme_reasons.append(f"볼밴상단돌파({bb_position_ratio:.3f})")
            if extreme_conditions[3]: extreme_reasons.append(f"거래량급증({volume_ratio:.1f}배)")
            
            logger.info(f"❌ [{stock_code}] 극한 조건 차단: {', '.join(extreme_reasons)}")
            
            return {
                'is_buy_signal': False,
                'signal_strength': 'REJECTED',
                'score': 0,
                'min_score': 0,
                'signals': [f"❌ 극한 조건 {extreme_count}개로 매수 차단: {', '.join(extreme_reasons)}"],
                'analysis': {
                    'rejection_reason': 'multiple_extreme_conditions',
                    'extreme_count': extreme_count,
                    'extreme_details': {
                        'rsi': rsi,
                        'price_position': price_position,
                        'bb_ratio': bb_position_ratio,
                        'volume_ratio': volume_ratio
                    }
                },
                'bb_position': 'rejected'
            }

        # 🔥 동적 파라미터 적용
        logger.info(f"🧠 [{stock_code}] 동적 파라미터 적용 시작...")
        
        if trading_config.use_adaptive_strategy:
            try:
                from technical_analysis import AdaptiveMarketStrategy
                adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
                market_env = detect_stock_environment(stock_code)
                
                logger.info(f"🌍 [{stock_code}] 시장 환경: {market_env}")
                
                if hasattr(adaptive_strategy, 'get_dynamic_parameters'):
                    dynamic_params = adaptive_strategy.get_dynamic_parameters(stock_code, market_env)
                    rsi_threshold = dynamic_params['rsi_threshold']
                    min_score = dynamic_params['min_score']
                    logger.info(f"🧠 [{stock_code}] 동적 파라미터: RSI기준 {rsi_threshold}, 점수기준 {min_score} (환경: {market_env})")
                else:
                    rsi_threshold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
                    min_score = target_config.get('min_score', 42)
                    logger.info(f"🔧 [{stock_code}] 기본 파라미터 (동적 메서드 없음): RSI기준 {rsi_threshold}, 점수기준 {min_score}")
                    
            except Exception as e:
                logger.warning(f"⚠️ [{stock_code}] 동적 파라미터 적용 실패: {e}")
                rsi_threshold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
                min_score = target_config.get('min_score', 42)
                logger.info(f"🔧 [{stock_code}] 기본 파라미터 (예외 발생): RSI기준 {rsi_threshold}, 점수기준 {min_score}")
        else:
            rsi_threshold = target_config.get('rsi_oversold', trading_config.rsi_oversold)
            min_score = target_config.get('min_score', 42)
            logger.info(f"🔧 [{stock_code}] 기본 파라미터 (적응형 비활성): RSI기준 {rsi_threshold}, 점수기준 {min_score}")
    
        # 🎯 매수 신호 점수 계산 시작
        logger.info(f"🎯 [{stock_code}] 점수 계산 시작...")
        
        # 1) RSI 신호 (과매수 페널티 포함)
        rsi_score = 0
        if rsi <= 20:  # 극과매도
            rsi_score = 40
            signals.append(f"RSI 극과매도 {rsi:.1f} (+40)")
        elif rsi <= 25:  # 강과매도  
            rsi_score = 35
            signals.append(f"RSI 강과매도 {rsi:.1f} (+35)")
        elif rsi <= 30:  # 과매도
            rsi_score = 30
            signals.append(f"RSI 과매도 {rsi:.1f} (+30)")
        elif rsi <= rsi_threshold:  # 동적 기준
            rsi_score = 20
            signals.append(f"RSI 조정구간 {rsi:.1f} (+20)")
        elif rsi >= 85:  # 🔥 극과매수 페널티 (차단 아닌 페널티)
            rsi_score = -30
            signals.append(f"RSI 극과매수 페널티 {rsi:.1f} (-30)")
        elif rsi >= 75:  # 과매수 페널티
            rsi_score = -20
            signals.append(f"RSI 과매수 페널티 {rsi:.1f} (-20)")
        elif rsi >= 70:  # 과매수 주의
            rsi_score = -10
            signals.append(f"RSI 과매수 주의 {rsi:.1f} (-10)")
        
        score += rsi_score
        logger.info(f"📊 [{stock_code}] RSI 점수: {rsi_score}점 (누적: {score}점)")

        # 2) 볼린저밴드 신호 (상단 근처 페널티 포함)
        bb_lower = stock_data.get('bb_lower', 0)
        bb_middle = stock_data.get('bb_middle', 0)
        bb_position = "middle"
        bb_score = 0
        
        if bb_lower > 0:
            bb_lower_distance = (current_price - bb_lower) / bb_lower * 100
            
            if bb_lower_distance <= -2:  # 하단 돌파
                bb_score = 35
                signals.append("볼린저밴드 하단 돌파 (+35)")
                bb_position = "breakthrough"
            elif bb_lower_distance <= 3:  # 하단 근처
                bb_score = 25
                signals.append("볼린저밴드 하단 근처 (+25)")
                bb_position = "lower"
            elif current_price <= bb_middle:
                bb_score = 15
                signals.append("볼린저밴드 중간선 하단 (+15)")
                bb_position = "below_middle"
            elif bb_position_ratio >= 1.0:  # 🔥 상단 돌파 페널티 (차단 아닌 페널티)
                bb_score = -25
                signals.append(f"볼린저밴드 상단 돌파 페널티 (-25)")
                bb_position = "upper_break"
            elif bb_position_ratio >= 0.97:  # 상단 근접 페널티
                bb_score = -15
                signals.append(f"볼린저밴드 상단 근접 페널티 (-15)")
                bb_position = "upper_near"
        
        score += bb_score
        logger.info(f"📈 [{stock_code}] 볼린저밴드 점수: {bb_score}점 (누적: {score}점)")
        
        # 3) 이동평균선 추세 (기존 로직 유지)
        ma5 = stock_data['ma5']
        ma20 = stock_data['ma20']
        ma60 = stock_data['ma60']
        
        ma_score = 0
        if ma5 > ma20:
            if ma20 > ma60:
                ma_score = 20
                signals.append("완전 정배열 (+20)")
            else:
                ma_score = 15
                signals.append("단기 상승 추세 (+15)")
        elif ma5 > ma20 * 0.995:
            ma_score = 12
            signals.append("골든크로스 임박 (+12)")
        
        score += ma_score
        logger.info(f"📊 [{stock_code}] 이동평균 점수: {ma_score}점 (누적: {score}점)")

        # 4) 가격 위치 기반 점수 (페널티 포함)
        price_score = 0
        if price_position >= 0.85:  # 85% 이상 고점권 페널티
            price_score = -20
            signals.append(f"20일 고점권 페널티 {price_position*100:.1f}% (-20)")
        elif price_position >= 0.75:  # 75% 이상 페널티
            price_score = -10
            signals.append(f"20일 상위권 페널티 {price_position*100:.1f}% (-10)")
        elif price_position <= 0.2:  # 20일 저점 근처
            price_score = 25
            signals.append("20일 저점 근처 (+25)")
        elif price_position <= 0.3:
            price_score = 20
            signals.append("20일 하위 30% 구간 (+20)")
        elif price_position <= 0.4:
            price_score = 15
            signals.append("20일 하위 40% 구간 (+15)")
        
        score += price_score
        logger.info(f"📍 [{stock_code}] 가격위치 점수: {price_score}점 (누적: {score}점)")
        
        # 5) MACD 신호 (기존 로직 유지)
        macd = stock_data['macd']
        macd_signal = stock_data['macd_signal']
        macd_histogram = stock_data['macd_histogram']
        
        macd_score = 0
        if macd > macd_signal and macd_histogram > 0:
            macd_score = 15
            signals.append("MACD 골든크로스 + 상승 (+15)")
        elif macd > macd_signal:
            macd_score = 10
            signals.append("MACD 골든크로스 (+10)")
        elif macd_histogram > 0:
            macd_score = 8
            signals.append("MACD 모멘텀 상승 (+8)")
        
        score += macd_score
        logger.info(f"📊 [{stock_code}] MACD 점수: {macd_score}점 (누적: {score}점)")
        
        # 6) 거래량 신호 (과열 페널티 포함)
        volume_score = 0
        if volume_ratio >= 3.0:  # 🔥 3배 이상 급등시 페널티 (과열 우려)
            volume_score = -15
            signals.append(f"거래량 과열 페널티 {volume_ratio:.1f}배 (-15)")
        elif volume_ratio >= 1.5:  # 거래량 증가
            volume_score = 12
            signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+12)")
        elif volume_ratio >= 1.2:
            volume_score = 8
            signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+8)")
        
        score += volume_score
        logger.info(f"📊 [{stock_code}] 거래량 점수: {volume_score}점 (누적: {score}점)")
        
        # 7) 연속 상승 페널티
        consecutive_score = 0
        if consecutive_up_days >= 4:  # 4일 연속 급등 페널티
            consecutive_score = -20
            signals.append(f"연속 급등 페널티 {consecutive_up_days}일 (-20)")
        elif consecutive_up_days >= 3:  # 3일 연속 상승 주의
            consecutive_score = -10
            signals.append(f"연속 상승 주의 {consecutive_up_days}일 (-10)")
        
        score += consecutive_score
        logger.info(f"📈 [{stock_code}] 연속상승 점수: {consecutive_score}점 (누적: {score}점)")
        
        # 8) 연속 하락 후 반등 신호 (기존 로직 유지)
        reversal_score = 0
        if len(df) >= 5:
            consecutive_down = 0
            for i in range(1, 4):
                if df['close'].iloc[-i] < df['close'].iloc[-i-1]:
                    consecutive_down += 1
                else:
                    break
            
            if consecutive_down >= 2 and df['close'].iloc[-1] > df['close'].iloc[-2]:
                reversal_score = 20
                signals.append(f"연속하락 후 반등 ({consecutive_down}일) (+20)")
        
        score += reversal_score
        logger.info(f"🔄 [{stock_code}] 반등신호 점수: {reversal_score}점 (누적: {score}점)")
        
        # 🔥 NEW: 시장 추세 필터 적용 (기존 점수 계산 후)
        trend_analysis = {'market_condition': 'UNKNOWN'}
        
        if market_trend and trading_config.config.get('use_market_trend_filter', True):
            stock_env = detect_stock_environment(stock_code)
            market_condition = market_trend['market_condition']
            
            logger.info(f"📊 [{stock_code}] 추세 분석: 시장 {market_condition}, 개별 {stock_env}")
            
            # 추세 기반 점수 조정
            trend_penalty = 0
            
            if market_condition == 'BEARISH':
                if stock_env == 'downtrend':
                    trend_penalty = -50
                    signals.append("❌ 시장하락+개별하락 페널티 -50점")
                elif stock_env == 'sideways':
                    trend_penalty = -25
                    signals.append("⚠️ 시장하락+개별횡보 페널티 -25점")
                else:  # uptrend
                    trend_penalty = -10
                    signals.append("🟡 시장하락 중 역행상승 -10점")
                    
            elif market_condition == 'MIXED':
                if stock_env == 'downtrend':
                    trend_penalty = -15
                    signals.append("⚠️ 혼조장+개별하락 페널티 -15점")
                    
            elif market_condition == 'BULLISH':
                if stock_env == 'uptrend':
                    trend_penalty = +10
                    signals.append("🚀 상승장+개별상승 보너스 +10점")
            
            score += trend_penalty
            
            trend_analysis = {
                'market_condition': market_condition,
                'stock_environment': stock_env,
                'trend_penalty': trend_penalty
            }
            
            logger.info(f"📊 [{stock_code}] 추세 조정: {trend_penalty}점 (누적: {score}점)")
        
        # 🎯 최종 매수 판단
        signal_strength = 'NORMAL'
        
        # 강력한 매수 신호 조건 (적당히 강화)
        strong_conditions = [
            rsi <= 25,  # RSI 극과매도
            bb_position in ["breakthrough", "lower"],  # 볼린저밴드 하단권
            score >= 75,  # 🎯 70 → 75 (적당히 상향)
            any("연속하락 후 반등" in s for s in signals),  # 반등 신호
            price_position <= 0.4,  # 🎯 하위 40% 구간
        ]

        # 강력한 신호는 2개 이상 조건 만족시
        if sum(strong_conditions) >= 2:
            signal_strength = 'STRONG'

        is_buy_signal = score >= min_score
        
        logger.info(f"🎯 [{stock_code}] 최종 판정: 점수 {score}/{min_score}점, 신호강도 {signal_strength}")

        # 🔥 하락장 예외 조건 체크
        if (market_trend and market_trend['market_condition'] == 'BEARISH' and 
            not is_buy_signal and trend_analysis.get('trend_penalty', 0) < 0):
            
            # 예외 조건들 체크
            allow_conditions = []
            
            # 1. 극도 과매도 + 거래량 급증
            if rsi <= 15 and volume_ratio >= 2.0:
                allow_conditions.append("극도과매도+거래량급증")
            
            # 2. 볼린저밴드 하단 크게 이탈
            if bb_position == "breakthrough" and price_position <= 0.2:
                allow_conditions.append("볼밴하단돌파+저점권")
            
            # 3. 연속 하락 후 반등 신호
            if any("연속하락 후 반등" in s for s in signals):
                allow_conditions.append("연속하락후반등")
            
            if allow_conditions:
                # 예외 허용하되 높은 기준 적용
                exception_min_score = min_score + 15  # 기준 15점 상향
                if score >= exception_min_score:
                    is_buy_signal = True
                    signals.append(f"🔥 하락장예외허용: {', '.join(allow_conditions)} (기준+15점)")
                    logger.info(f"🔥 [{stock_code}] 하락장 예외 허용: {', '.join(allow_conditions)}")

        # 🎯 특별조건 할인 (조건 완화)
        if rsi <= 18 and bb_position == "breakthrough" and price_position <= 0.3:  # 정말 극한 상황에만
            discounted_score = max(25, min_score * 0.75)  # 할인 폭 적당히
            if score >= discounted_score and not is_buy_signal:
                signals.append(f"극한조건 점수할인: {discounted_score:.0f}점")
                is_buy_signal = True
                logger.info(f"🎁 [{stock_code}] 극한조건 할인 적용: {discounted_score:.0f}점")

        # target_config에 신호 강도 저장
        target_config['last_signal_strength'] = signal_strength
        target_config['last_signal_score'] = score

        logger.info(f"{'🎯' if is_buy_signal else '⏳'} [{stock_code}] 최종 결과: {'매수 신호' if is_buy_signal else '대기'} (점수: {score}/{min_score}점, 강도: {signal_strength})")

        return {
            'is_buy_signal': is_buy_signal,
            'signal_strength': signal_strength,
            'score': score,
            'min_score': min_score,
            'signals': signals if signals else ["매수 신호 부족"],
            'bb_position': bb_position,
            'analysis': trend_analysis,  # 🔥 시장 추세 분석 정보
            'used_parameters': {
                'rsi_threshold': rsi_threshold,
                'min_score': min_score,
                'market_env': detect_stock_environment(stock_code) if trading_config.use_adaptive_strategy else 'unknown'
            }
        }
        
    except Exception as e:
        logger.error(f"❌ [{stock_data.get('stock_code', 'UNKNOWN')}] 매수 신호 분석 중 에러: {str(e)}")
        logger.exception(f"❌ [{stock_data.get('stock_code', 'UNKNOWN')}] 상세 에러 정보:")
        return {'is_buy_signal': False, 'score': 0, 'min_score': 0, 'signals': [f"분석 오류: {str(e)}"]}

# 🎯 분봉 타이밍도 조건부 차단으로 수정
def analyze_intraday_entry_timing(stock_code, target_config):
    """분봉 기준 최적 진입 타이밍 분석 - 장 초반 안정화 적용"""
    try:
        stock_name = target_config.get('name', stock_code)
        
        # 🔥 1단계: 현재가 조회
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price:
            logger.warning(f"⚠️ {stock_name}: 현재가 조회 실패")
            return {
                'enter_now': False,  # True → False (보수적 변경)
                'entry_score': 0,
                'reason': '현재가 조회 실패로 진입 대기'
            }
        
        # 🔥 2단계: 장 초반 시간대 체크
        current_time = datetime.datetime.now().time()
        is_early_market = current_time < datetime.time(9, 30)  # 09:30 이전
        is_very_early = current_time < datetime.time(9, 15)    # 09:15 이전 (극초반)
        
        logger.debug(f"🕐 {stock_name} 분봉 분석: {current_time.strftime('%H:%M:%S')} "
                    f"(초반: {is_early_market}, 극초반: {is_very_early})")
        
        # 🔥 3단계: 분봉 데이터 조회 (다단계 시도)
        df_5m = None
        data_source = "unknown"
        
        try:
            # 시도 1: KIS API 분봉 조회
            df_5m = KisKR.GetOhlcvNew(stock_code, 'M', 24, adj_ok=1)
            if df_5m is not None and len(df_5m) >= 10:
                data_source = "KIS_minute"
                logger.debug(f"📊 {stock_name}: KIS 분봉 데이터 조회 성공 ({len(df_5m)}개)")
            else:
                logger.debug(f"📊 {stock_name}: KIS 분봉 데이터 부족")
                
        except Exception as api_e:
            logger.debug(f"📊 {stock_name}: KIS 분봉 API 실패 - {str(api_e)}")
        
        # 시도 2: Common API 일봉 조회 (백업)
        if df_5m is None or len(df_5m) < 10:
            try:
                df_5m = Common.GetOhlcv("KR", stock_code, 24)
                if df_5m is not None and len(df_5m) >= 10:
                    data_source = "Common_daily"
                    logger.debug(f"📊 {stock_name}: Common 일봉 데이터로 대체 ({len(df_5m)}개)")
            except Exception as common_e:
                logger.debug(f"📊 {stock_name}: Common API도 실패 - {str(common_e)}")
        
        # 🔥 4단계: 데이터 부족시 시간대별 처리
        if df_5m is None or len(df_5m) < 10:
            if is_very_early:  # 09:15 이전
                logger.info(f"⏰ {stock_name}: 극초반 데이터 부족으로 대기 (시간: {current_time.strftime('%H:%M')})")
                return {
                    'enter_now': False,
                    'entry_score': 0,
                    'entry_signals': ['극초반 분봉 데이터 부족'],
                    'reason': f'극초반({current_time.strftime("%H:%M")}) 분봉 데이터 부족으로 대기',
                    'data_info': {'data_length': 0, 'data_source': 'none'}
                }
            elif is_early_market:  # 09:15~09:30
                logger.info(f"⏰ {stock_name}: 장 초반 데이터 부족으로 대기 (시간: {current_time.strftime('%H:%M')})")
                return {
                    'enter_now': False,
                    'entry_score': 0,
                    'entry_signals': ['장 초반 분봉 데이터 부족'],
                    'reason': f'장 초반({current_time.strftime("%H:%M")}) 분봉 데이터 부족으로 대기',
                    'data_info': {'data_length': 0, 'data_source': 'none'}
                }
            else:  # 09:30 이후
                logger.warning(f"⚠️ {stock_name}: 장중 데이터 부족 - 조건부 진입")
                return {
                    'enter_now': True,  # 장중에는 진입 허용
                    'entry_score': 10,  # 최소 점수 부여
                    'entry_signals': ['장중 데이터 부족으로 조건부 진입'],
                    'reason': f'장중({current_time.strftime("%H:%M")}) 데이터 부족하지만 진입',
                    'data_info': {'data_length': 0, 'data_source': 'none'}
                }
        
        # 🔥 5단계: 데이터 길이 및 지표 설정
        data_length = len(df_5m)
        rsi_period = min(14, data_length // 2)
        ma_short = min(5, data_length // 4)
        ma_long = min(20, data_length // 2)
        bb_period = min(20, data_length // 2)
        
        logger.debug(f"📊 {stock_name} 분봉 데이터: {data_length}개 ({data_source})")
        
        # RSI 계산 최소 요구사항 체크
        if rsi_period < 3:
            if is_early_market:
                logger.info(f"⏰ {stock_name}: RSI 계산 불가로 장 초반 대기")
                return {
                    'enter_now': False,
                    'entry_score': 0,
                    'reason': 'RSI 계산 불가로 장 초반 대기',
                    'data_info': {'data_length': data_length, 'rsi_period': rsi_period}
                }
            else:
                return {
                    'enter_now': True,
                    'entry_score': 5,
                    'reason': 'RSI 계산 불가하지만 장중 진입',
                    'data_info': {'data_length': data_length, 'rsi_period': rsi_period}
                }
        
        # 🔥 6단계: 기술적 지표 계산
        try:
            df_5m['RSI'] = TechnicalIndicators.calculate_rsi(df_5m, rsi_period)
            df_5m['MA_Short'] = df_5m['close'].rolling(window=ma_short).mean()
            df_5m['MA_Long'] = df_5m['close'].rolling(window=ma_long).mean()
            
            # 볼린저밴드 계산
            if data_length >= bb_period:
                bb_data = TechnicalIndicators.calculate_bollinger_bands(df_5m, bb_period, 2.0)
                df_5m[['BB_Mid', 'BB_Upper', 'BB_Lower']] = bb_data
            else:
                # 볼린저밴드 계산 불가시 더미 값
                df_5m['BB_Mid'] = df_5m['close']
                df_5m['BB_Upper'] = df_5m['close'] * 1.02
                df_5m['BB_Lower'] = df_5m['close'] * 0.98
                
        except Exception as calc_e:
            logger.error(f"❌ {stock_name}: 기술적 지표 계산 실패 - {str(calc_e)}")
            if is_early_market:
                return {
                    'enter_now': False,
                    'entry_score': 0,
                    'reason': f'장 초반 지표 계산 실패로 대기: {str(calc_e)}',
                    'data_info': {'data_length': data_length, 'error': str(calc_e)}
                }
            else:
                return {
                    'enter_now': True,
                    'entry_score': 5,
                    'reason': f'지표 계산 실패하지만 장중 진입: {str(calc_e)}',
                    'data_info': {'data_length': data_length, 'error': str(calc_e)}
                }
        
        # 🔥 7단계: 극한 조건 체크
        intraday_rsi = df_5m['RSI'].iloc[-1] if not pd.isna(df_5m['RSI'].iloc[-1]) else 50
        bb_upper_5m = df_5m['BB_Upper'].iloc[-1]
        intraday_bb_ratio = current_price / bb_upper_5m if bb_upper_5m > 0 else 0.5
        
        # 분봉 극한 조건 정의
        intraday_extreme = [
            intraday_rsi >= 85,           # RSI 85% 이상
            intraday_bb_ratio >= 1.02,    # 볼밴 상단 2% 돌파
        ]
        
        intraday_extreme_count = sum(intraday_extreme)
        
        logger.debug(f"🚨 {stock_name} 극한 조건: RSI {intraday_rsi:.1f}, BB비율 {intraday_bb_ratio:.3f}, 극한수 {intraday_extreme_count}/2")
        
        # 극한 조건 2개 만족시 진입 거부
        if intraday_extreme_count >= 2:
            logger.info(f"🚨 {stock_name}: 분봉 극한 조건 차단")
            return {
                'enter_now': False,
                'entry_score': 0,
                'entry_signals': [f'분봉 극한 조건 {intraday_extreme_count}개로 진입 거부'],
                'reason': f'분봉 과열(RSI:{intraday_rsi:.1f}%, BB:{intraday_bb_ratio:.3f})로 진입 거부',
                'data_info': {
                    'data_length': data_length,
                    'extreme_count': intraday_extreme_count,
                    'rsi': intraday_rsi,
                    'bb_ratio': intraday_bb_ratio
                }
            }
        
        # 🔥 8단계: 분봉 진입 점수 계산
        entry_signals = []
        entry_score = 0
        
        # RSI 신호 (페널티 포함)
        if intraday_rsi <= 30:
            entry_score += 30
            entry_signals.append(f"분봉 RSI 과매도 {intraday_rsi:.1f} (+30)")
        elif intraday_rsi <= 45:
            entry_score += 20
            entry_signals.append(f"분봉 RSI 조정 {intraday_rsi:.1f} (+20)")
        elif intraday_rsi >= 80:
            entry_score -= 20
            entry_signals.append(f"분봉 RSI 과매수 페널티 {intraday_rsi:.1f} (-20)")
        elif intraday_rsi >= 70:
            entry_score -= 10
            entry_signals.append(f"분봉 RSI 과매수 주의 {intraday_rsi:.1f} (-10)")
        
        # 볼린저밴드 신호
        bb_lower_5m = df_5m['BB_Lower'].iloc[-1]
        if not pd.isna(bb_lower_5m) and current_price <= bb_lower_5m * 1.02:
            entry_score += 25
            entry_signals.append("분봉 볼린저 하단 근접 (+25)")
        elif intraday_bb_ratio >= 1.0:
            entry_score -= 15
            entry_signals.append(f"분봉 볼밴 상단 페널티 (-15)")
        elif intraday_bb_ratio >= 0.98:
            entry_score -= 8
            entry_signals.append(f"분봉 볼밴 상단 주의 (-8)")
        
        # 이동평균 지지 신호
        try:
            ma_short_current = df_5m['MA_Short'].iloc[-1]
            if not pd.isna(ma_short_current):
                distance_ratio = abs(current_price - ma_short_current) / ma_short_current
                if distance_ratio <= 0.01:
                    entry_score += 20
                    entry_signals.append(f"{ma_short}MA 지지 (+20)")
        except:
            pass
        
        # 거래량 신호
        try:
            if data_length >= 10:
                recent_volume = df_5m['volume'].iloc[-3:].mean()
                past_volume = df_5m['volume'].iloc[-10:-3].mean()
                
                if past_volume > 0:
                    volume_ratio = recent_volume / past_volume
                    if volume_ratio >= 1.3:
                        entry_score += 15
                        entry_signals.append(f"분봉 거래량 증가 {volume_ratio:.1f}배 (+15)")
        except:
            pass
        
        # 반등 신호 및 고점 페널티
        try:
            if data_length >= 5:
                recent_changes = df_5m['close'].pct_change().iloc[-4:]
                down_count = sum(1 for x in recent_changes if x < -0.01)
                last_change = df_5m['close'].pct_change().iloc[-1]
                
                if down_count >= 2 and last_change > 0.005:
                    entry_score += 20
                    entry_signals.append("분봉 반등 신호 (+20)")
                
                recent_high = df_5m['high'].iloc[-min(10, data_length):].max()
                if current_price >= recent_high * 0.98:
                    entry_score -= 10
                    entry_signals.append("분봉 단기 고점 페널티 (-10)")
        except:
            pass
        
        # 🔥 9단계: 진입 기준 결정 (시간대별 차등)
        base_min_score = target_config.get('min_entry_score', 20)
        
        if is_very_early:  # 09:15 이전
            min_entry_score = base_min_score + 10  # 더 엄격
            time_penalty_reason = "극초반 엄격 모드"
        elif is_early_market:  # 09:15~09:30
            min_entry_score = base_min_score + 5   # 약간 엄격
            time_penalty_reason = "장 초반 엄격 모드"
        else:  # 09:30 이후
            min_entry_score = base_min_score        # 기본 기준
            time_penalty_reason = "정상 시간대"
        
        # 데이터 부족시 기준 완화
        if data_length < 20:
            discount = min(8, base_min_score // 3)
            min_entry_score = max(10, min_entry_score - discount)
            entry_signals.append(f"데이터 부족으로 기준 완화 ({data_length}개, -{discount}점)")
        
        # 🔥 10단계: 최종 진입 결정
        enter_now = entry_score >= min_entry_score
        
        result = {
            'enter_now': enter_now,
            'entry_score': entry_score,
            'entry_signals': entry_signals if entry_signals else ["분봉 신호 없음"],
            'reason': f"{'분봉 진입 타이밍 양호' if enter_now else '분봉 진입 대기'} (점수: {entry_score}/{min_entry_score}, {time_penalty_reason})",
            'data_info': {
                'data_length': data_length,
                'data_source': data_source,
                'rsi_period': rsi_period,
                'ma_periods': [ma_short, ma_long],
                'intraday_extreme_count': intraday_extreme_count,
                'time_zone': 'very_early' if is_very_early else 'early' if is_early_market else 'normal',
                'min_score_used': min_entry_score,
                'base_min_score': base_min_score
            }
        }
        
        # 상세 로그
        if enter_now:
            logger.info(f"✅ {stock_name}: 분봉 진입 타이밍 양호 ({entry_score}/{min_entry_score}점)")
        else:
            logger.info(f"⏳ {stock_name}: 분봉 진입 대기 ({entry_score}/{min_entry_score}점)")
        
        # 주요 신호들 로그 (상위 3개만)
        for signal in entry_signals[:3]:
            logger.debug(f"   📊 {signal}")
        
        return result
            
    except Exception as e:
        logger.error(f"❌ {stock_name if 'stock_name' in locals() else stock_code}: 분봉 분석 중 오류 - {str(e)}")
        logger.exception(f"❌ {stock_code}: 분봉 분석 상세 오류")
        
        # 🔥 예외시에도 시간대별 처리
        try:
            current_time = datetime.datetime.now().time()
            is_early = current_time < datetime.time(9, 30)
            
            if is_early:
                return {
                    'enter_now': False,
                    'entry_score': 0,
                    'entry_signals': [f"장 초반 분석 오류로 대기"],
                    'reason': f'장 초반 분봉 분석 오류로 대기: {str(e)}',
                    'data_info': {'error': str(e), 'time_zone': 'early'}
                }
            else:
                return {
                    'enter_now': True,
                    'entry_score': 5,  # 최소 점수 부여
                    'entry_signals': [f"장중 분석 오류로 조건부 진입"],
                    'reason': f'분봉 분석 오류하지만 장중 조건부 진입: {str(e)}',
                    'data_info': {'error': str(e), 'time_zone': 'normal'}
                }
        except:
            # 최악의 상황: 시간 체크도 실패
            return {
                'enter_now': False,
                'entry_score': 0,
                'entry_signals': ["치명적 오류로 진입 금지"],
                'reason': f'치명적 분봉 분석 오류: {str(e)}'
            }

def should_use_intraday_timing(opportunity, target_config):
    """신호 강도별 분봉 타이밍 사용 여부 결정"""
    try:
        # 전역 설정에서 분봉 타이밍이 비활성화된 경우
        if not getattr(trading_config, 'use_intraday_timing', False):
            return False, 0, "분봉 타이밍 비활성화"
        
        daily_score = opportunity['score']
        signal_strength = opportunity.get('signal_strength', 'NORMAL')
        
        # 🎯 신호 강도별 차등 적용
        if signal_strength == 'STRONG' and daily_score >= 70:
            # 매우 강한 신호: 즉시 매수
            return False, 0, f"강력한 신호로 즉시 매수 (점수: {daily_score})"
            
        elif daily_score >= 60:
            # 강한 신호: 30분만 대기
            return True, 0.5, f"강한 신호로 30분 대기 (점수: {daily_score})"
            
        elif daily_score >= 50:
            # 중간 신호: 1시간 대기
            return True, 1.0, f"중간 신호로 1시간 대기 (점수: {daily_score})"
            
        elif daily_score >= 40:
            # 보통 신호: 2시간 대기 (기존)
            return True, 2.0, f"보통 신호로 2시간 대기 (점수: {daily_score})"
            
        else:
            # 약한 신호: 분봉 타이밍 더 엄격하게
            return True, 1.5, f"약한 신호로 1.5시간 대기 (점수: {daily_score})"
            
    except Exception as e:
        logger.error(f"분봉 타이밍 결정 중 오류: {str(e)}")
        return True, 2.0, "오류로 기본 대기"

def calculate_adaptive_stop_loss(stock_data, position, target_config):
    """적응형 손절 계산 - 변동성과 시장 환경 고려"""
    try:
        entry_price = position['entry_price']
        current_price = stock_data['current_price']
        
        # 기본 손절 비율
        base_stop_ratio = target_config.get('stop_loss', trading_config.stop_loss_ratio)
        
        # 1. 변동성 기반 조정
        atr = stock_data.get('atr', 0)
        if atr > 0:
            # ATR 기반 변동성 손절 (ATR의 1.5배)
            volatility_multiplier = target_config.get('volatility_stop_multiplier', 1.5)
            volatility_stop = (atr * volatility_multiplier) / entry_price
            
            # 변동성이 높으면 손절폭 확대
            adjusted_stop_ratio = min(base_stop_ratio, -volatility_stop)
        else:
            adjusted_stop_ratio = base_stop_ratio
        
        # 2. 시장 환경별 조정
        if trading_config.use_adaptive_strategy:
            stock_env = detect_stock_environment(stock_data['stock_code'])
            
            if stock_env == "uptrend":
                # 상승장: 손절폭 20% 확대
                adjusted_stop_ratio *= 1.2
            elif stock_env == "downtrend":
                # 하락장: 손절폭 10% 축소 (빠른 손절)
                adjusted_stop_ratio *= 0.9
            # 횡보장: 기본값 유지
        
        # 3. 보유시간 기반 조정
        entry_time = datetime.datetime.strptime(position['entry_time'], '%Y-%m-%d %H:%M:%S')
        holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
        min_holding = target_config.get('min_holding_hours', 4)
        
        # 최소 보유시간 미달시 손절 지연
        if holding_hours < min_holding:
            delay_hours = target_config.get('stop_loss_delay_hours', 2)
            if holding_hours < delay_hours:
                # 초기 2시간은 손절폭 50% 확대
                adjusted_stop_ratio *= 1.5
                logger.info(f"손절 지연 적용: {holding_hours:.1f}시간 < {delay_hours}시간")
        
        # 4. 기술적 지지선 고려
        support = stock_data.get('support', 0)
        if support > 0:
            support_based_stop = (support - entry_price) / entry_price
            # 지지선이 기본 손절선보다 낮으면 지지선 기준 사용
            if support_based_stop < adjusted_stop_ratio:
                adjusted_stop_ratio = min(adjusted_stop_ratio, support_based_stop * 0.98)  # 지지선 2% 아래
                logger.info(f"지지선 기반 손절 적용: {support:,.0f}원")
        
        # 5. 최대/최소 손절 한계 설정
        max_stop_ratio = -0.08  # 최대 8% 손절
        min_stop_ratio = -0.02  # 최소 2% 손절
        adjusted_stop_ratio = max(max_stop_ratio, min(min_stop_ratio, adjusted_stop_ratio))
        
        logger.debug(f"적응형 손절 계산: {base_stop_ratio:.1%} → {adjusted_stop_ratio:.1%}")
        
        return adjusted_stop_ratio
        
    except Exception as e:
        logger.error(f"적응형 손절 계산 중 오류: {str(e)}")
        return target_config.get('stop_loss', trading_config.stop_loss_ratio)

def calculate_total_trading_cost_rate(price, amount):
    """총 거래비용률 계산 (매수+매도 수수료+세금)"""
    try:
        total_value = price * amount
        
        # 매수 수수료 (0.00156%)
        buy_commission = total_value * 0.000156
        # 매도 수수료 (0.00156%)  
        sell_commission = total_value * 0.000156
        # 농특세 (매도시 0.15%)
        special_tax = total_value * 0.0015
        
        total_cost = buy_commission + sell_commission + special_tax
        cost_rate = total_cost / total_value
        
        logger.debug(f"거래비용 계산: 투자금액 {total_value:,}원, 총비용 {total_cost:.0f}원, 비용률 {cost_rate*100:.3f}%")
        return cost_rate
        
    except Exception as e:
        logger.error(f"거래비용 계산 오류: {str(e)}")
        return 0.002  # 기본값 0.2%

def detect_market_condition(stock_data):
    """시장 상황 감지 - 약세장/강세장/불안정 구분"""
    try:
        df = stock_data.get('ohlcv_data')
        if df is None or len(df) < 20:
            return 'uncertain'
        
        # 최근 10일 변동성 체크
        recent_volatility = df['close'].pct_change().iloc[-10:].std()
        
        # 20일 이동평균 기울기
        ma20 = df['close'].rolling(20).mean()
        ma20_slope = (ma20.iloc[-1] / ma20.iloc[-11] - 1) * 100 if len(ma20) >= 11 else 0
        
        # RSI 상태
        rsi = stock_data.get('rsi', 50)
        
        # 거래량 변화
        volume_change = 1.0
        if len(df) >= 10:
            recent_volume = df['volume'].iloc[-5:].mean()
            past_volume = df['volume'].iloc[-15:-5].mean()
            volume_change = recent_volume / past_volume if past_volume > 0 else 1.0
        
        logger.debug(f"시장상황 분석: 변동성 {recent_volatility:.3f}, MA기울기 {ma20_slope:.1f}%, RSI {rsi:.1f}")
        
        # 🌧️ 약세장/불안정 조건
        if (recent_volatility > 0.035 or  # 일일 변동성 3.5% 이상
            (ma20_slope < -1.5 and rsi < 45) or  # 하락추세 + 약세
            volume_change > 2.5):  # 거래량 급증 (불안정)
            return 'bearish_volatile'
        
        # 🌞 강세장 조건
        elif (ma20_slope > 2 and rsi > 55 and recent_volatility < 0.025):
            return 'bullish'
        
        # 🌤️ 보통/불확실
        else:
            return 'uncertain'
            
    except Exception as e:
        logger.error(f"시장상황 감지 오류: {str(e)}")
        return 'uncertain'

def calculate_market_adaptive_partial_sell(stock_data, position, target_config):
    """시장 상황 적응형 분할매도 전략 계산"""
    try:
        entry_price = position.get('entry_price', 0)
        current_price = stock_data['current_price']
        total_amount = position.get('amount', 0)
        high_price = position.get('high_price', entry_price)
        stock_name = position.get('stock_name', 'Unknown')
        
        if entry_price <= 0 or total_amount <= 0:
            return None
        
        profit_rate = (current_price - entry_price) / entry_price
        drawdown_from_high = (high_price - current_price) / high_price if high_price > entry_price else 0
        
        # 🎯 시장 상황 감지
        market_condition = detect_market_condition(stock_data)
        
        # 🔥 수수료 고려한 최소 수익률 계산
        trading_cost_rate = calculate_total_trading_cost_rate(entry_price, total_amount)
        min_profit_threshold = trading_cost_rate * 8  # 수수료의 8배 이상
        
        # 🎯 과열도 체크 (시장상황별 기준 조정)
        rsi = stock_data.get('rsi', 50)
        bb_upper = stock_data.get('bb_upper', 0)
        bb_ratio = current_price / bb_upper if bb_upper > 0 else 0.5
        
        # 거래량 급증 체크
        df = stock_data.get('ohlcv_data')
        volume_surge = 1.0
        if df is not None and len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_surge = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        # 시장상황별 과열 기준 조정
        if market_condition == 'bearish_volatile':
            rsi_threshold = 65  # 약세장에서는 더 민감하게
            bb_threshold = 0.93
            volume_threshold = 2.0
        else:
            rsi_threshold = 75  # 일반적인 기준
            bb_threshold = 0.98
            volume_threshold = 3.0
        
        is_overheated = (
            rsi >= rsi_threshold or 
            bb_ratio >= bb_threshold or 
            volume_surge >= volume_threshold
        )
        
        logger.info(f"🔍 {stock_name} 분할매도 분석:")
        logger.info(f"   수익률: {profit_rate*100:.2f}%, 최소기준: {min_profit_threshold*100:.2f}%")
        logger.info(f"   시장상황: {market_condition}, 과열여부: {is_overheated}")
        logger.info(f"   고점대비: -{drawdown_from_high*100:.1f}%")
        
        # 최소 수익 기준 미달시 분할매도 안함
        if profit_rate < min_profit_threshold:
            logger.debug(f"   → 최소 수익 기준 미달로 분할매도 안함")
            return None
        
        # 🎯 시장상황별 분할매도 전략
        partial_strategies = []
        
        if market_condition == 'bearish_volatile':
            # 🌧️ 약세장/불안정: 방어적 분할매도
            partial_strategies = calculate_defensive_partial_strategies(
                profit_rate, total_amount, is_overheated, drawdown_from_high, min_profit_threshold
            )
        else:
            # 🌞 강세장/보통: 기존 공격적 분할매도
            partial_strategies = calculate_normal_partial_strategies(
                profit_rate, total_amount, is_overheated, drawdown_from_high, min_profit_threshold
            )
        
        # 🎯 최우선 전략 선택
        if partial_strategies:
            best_strategy = max(partial_strategies, key=lambda x: x['priority'])
            
            # 실제 매도 수량 계산
            sell_quantity = max(1, int(total_amount * best_strategy['sell_ratio']))
            sell_quantity = min(sell_quantity, total_amount)  # 보유량 초과 방지
            
            logger.info(f"   ✅ 분할매도 전략: {best_strategy['reason']}")
            logger.info(f"   📊 매도 수량: {sell_quantity}주 / {total_amount}주 ({best_strategy['sell_ratio']*100:.0f}%)")
            
            return {
                'should_partial_sell': True,
                'sell_quantity': sell_quantity,
                'sell_ratio': sell_quantity / total_amount,
                'strategy_type': best_strategy['type'],
                'reason': best_strategy['reason'],
                'remaining_amount': total_amount - sell_quantity,
                'market_condition': market_condition,
                'analysis': {
                    'profit_rate': profit_rate,
                    'drawdown_from_high': drawdown_from_high,
                    'is_overheated': is_overheated,
                    'rsi': rsi,
                    'volume_surge': volume_surge,
                    'min_profit_threshold': min_profit_threshold
                }
            }
        
        logger.debug(f"   → 분할매도 조건 불만족")
        return None
        
    except Exception as e:
        logger.error(f"시장 적응형 분할매도 계산 중 오류: {str(e)}")
        return None

def calculate_defensive_partial_strategies(profit_rate, total_amount, is_overheated, drawdown_from_high, min_threshold):
    """방어적 분할매도 전략 (약세장/불안정 시장용)"""
    strategies = []
    
    # 🔥 점진적 단계별 매도 (수수료 고려)
    if profit_rate >= 0.15:  # 15% 이상 - 거의 확정
        strategies.append({
            'type': 'defensive_high_profit',
            'sell_ratio': 0.8,  # 80% 매도 (20% 만 남김)
            'reason': f'약세장 고수익 확정 {profit_rate*100:.1f}%',
            'priority': 10
        })
        
    elif profit_rate >= 0.12:  # 12% 이상 - 대량 확정
        strategies.append({
            'type': 'defensive_target_profit',
            'sell_ratio': 0.6,  # 60% 매도
            'reason': f'약세장 목표수익 달성 {profit_rate*100:.1f}%',
            'priority': 9
        })
        
    elif profit_rate >= 0.08:  # 8% 이상 - 절반 확정
        strategies.append({
            'type': 'defensive_good_profit',
            'sell_ratio': 0.5,  # 50% 매도
            'reason': f'약세장 양호수익 확정 {profit_rate*100:.1f}%',
            'priority': 8
        })
        
    elif profit_rate >= 0.05:  # 5% 이상 - 부분 확정
        strategies.append({
            'type': 'defensive_moderate_profit',
            'sell_ratio': 0.4,  # 40% 매도
            'reason': f'약세장 중간수익 확정 {profit_rate*100:.1f}%',
            'priority': 7
        })
        
    elif profit_rate >= 0.03:  # 3% 이상 - 소량 확정
        strategies.append({
            'type': 'defensive_small_profit',
            'sell_ratio': 0.3,  # 30% 매도
            'reason': f'약세장 소량수익 확정 {profit_rate*100:.1f}%',
            'priority': 6
        })
        
    elif profit_rate >= 0.015:  # 1.5% 이상 - 최소 확정
        if is_overheated:  # 과열 상태일 때만
            strategies.append({
                'type': 'defensive_minimal_profit',
                'sell_ratio': 0.25,  # 25% 매도
                'reason': f'약세장 최소수익 보호 {profit_rate*100:.1f}%',
                'priority': 5
            })
    
    # 🔥 고점 보호 (더 민감하게)
    if profit_rate > min_threshold and drawdown_from_high >= 0.015:  # 고점대비 1.5% 하락
        strategies.append({
            'type': 'defensive_high_protection',
            'sell_ratio': 0.4,  # 40% 매도
            'reason': f'약세장 고점보호 (고점대비 -{drawdown_from_high*100:.1f}%)',
            'priority': 8
        })
    
    return strategies

def calculate_normal_partial_strategies(profit_rate, total_amount, is_overheated, drawdown_from_high, min_threshold):
    """현실적인 분할매도 전략 (강세장/보통 시장용)"""
    strategies = []
    
    # 🔥 현실적인 간격으로 조정
    if profit_rate >= 0.15:  # 15% 이상
        strategies.append({
            'type': 'normal_very_high_profit',
            'sell_ratio': 0.7,  # 70% 매도
            'reason': f'매우 높은 수익 달성 {profit_rate*100:.1f}%',
            'priority': 10
        })
        
    elif profit_rate >= 0.10:  # 10% 이상
        strategies.append({
            'type': 'normal_high_profit', 
            'sell_ratio': 0.5,  # 50% 매도
            'reason': f'높은 수익 달성 {profit_rate*100:.1f}%',
            'priority': 9
        })
        
    elif profit_rate >= 0.06:  # 6% 이상
        strategies.append({
            'type': 'normal_good_profit',
            'sell_ratio': 0.4,  # 40% 매도  
            'reason': f'양호한 수익 {profit_rate*100:.1f}%',
            'priority': 8
        })
        
    elif profit_rate >= 0.03:  # 3% 이상
        strategies.append({
            'type': 'normal_moderate_profit',
            'sell_ratio': 0.3,  # 30% 매도
            'reason': f'적당한 수익 {profit_rate*100:.1f}%',
            'priority': 7
        })
        
    elif profit_rate >= 0.015:  # 1.5% 이상
        if is_overheated:
            strategies.append({
                'type': 'normal_small_profit_overheated',
                'sell_ratio': 0.25,  # 25% 매도
                'reason': f'과열상태 소량익절 {profit_rate*100:.1f}%',
                'priority': 6
            })
    
    # 고점 보호 (기존과 동일)
    if profit_rate > min_threshold and drawdown_from_high >= 0.025:
        strategies.append({
            'type': 'normal_high_protection',
            'sell_ratio': 0.3,  # 30% 매도
            'reason': f'고점보호 부분매도 (고점대비 -{drawdown_from_high*100:.1f}%)',
            'priority': 7
        })
    
    return strategies

def should_execute_partial_sell(partial_strategy, position, target_config):
    """분할매도 실행 여부 최종 검증"""
    try:
        if not partial_strategy:
            return False
        
        # 🔥 분할매도 기능 활성화 체크
        use_partial_sell = target_config.get('use_partial_sell', True)
        if not use_partial_sell:
            logger.debug("분할매도 기능 비활성화됨")
            return False
        
        # 🔥 최소 보유량 체크
        remaining_amount = partial_strategy['remaining_amount']
        min_holding = target_config.get('min_holding_amount', 1)
        
        if remaining_amount < min_holding:
            # 남은 수량이 너무 적으면 전량매도로 전환
            partial_strategy['sell_quantity'] = position['amount']
            partial_strategy['strategy_type'] = 'full_sell_min_holding'
            partial_strategy['reason'] += ' (최소보유량 미달로 전량매도)'
            logger.info(f"최소보유량 미달로 전량매도 전환: {remaining_amount}주 < {min_holding}주")
        
        # 🔥 매도 쿨다운 체크 (너무 자주 매도 방지)
        last_partial_sell = position.get('last_partial_sell_time')
        if last_partial_sell:
            try:
                last_sell_time = datetime.datetime.fromisoformat(last_partial_sell)
                cooldown_hours = target_config.get('partial_sell_cooldown_hours', 1)
                elapsed_hours = (datetime.datetime.now() - last_sell_time).total_seconds() / 3600
                
                if elapsed_hours < cooldown_hours:
                    logger.debug(f"분할매도 쿨다운 중: {elapsed_hours:.1f}/{cooldown_hours}시간")
                    return False
            except:
                pass
        
        return True
        
    except Exception as e:
        logger.error(f"분할매도 실행 검증 중 오류: {str(e)}")
        return False        

def analyze_sell_signal(stock_data, position, target_config):
    """통합 매도 신호 분석 - 분할매도 우선, 전량매도 후순위"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position.get('entry_price', 0)
        stock_name = position.get('stock_name', stock_code)
        
        if entry_price <= 0:
            return {'is_sell_signal': False, 'sell_type': None, 'reason': 'entry_price 정보 없음'}
        
        profit_rate = (current_price - entry_price) / entry_price
        
        logger.debug(f"🔍 {stock_name} 매도 신호 분석 시작: 수익률 {profit_rate*100:.2f}%")
        
        # 🎯 1단계: 긴급 전량매도 우선 (손절, 급락 등)
        legacy_result = analyze_sell_signal_legacy(stock_data, position, target_config)
        
        if legacy_result['is_sell_signal']:
            sell_type = legacy_result.get('sell_type', '')
            
            # 긴급 매도는 분할매도보다 우선
            urgent_types = [
                'emergency_exit', 'improved_stop_loss', 'time_based_stop_loss',
                'consecutive_decline', 'emergency_stop_loss'
            ]
            
            if any(urgent_type in sell_type for urgent_type in urgent_types):
                logger.info(f"🚨 {stock_name} 긴급 전량매도: {legacy_result['reason']}")
                legacy_result['sell_quantity'] = position['amount']
                legacy_result['remaining_amount'] = 0
                legacy_result['sell_method'] = 'urgent_full_sell'
                return legacy_result
        
        # 🎯 2단계: 분할매도 검토 (수익 상태에서)
        if profit_rate > 0:  # 수익 상태에서만 분할매도 고려
            partial_strategy = calculate_market_adaptive_partial_sell(stock_data, position, target_config)
            
            if partial_strategy and should_execute_partial_sell(partial_strategy, position, target_config):
                logger.info(f"🎯 {stock_name} 분할매도 신호: {partial_strategy['reason']}")
                
                return {
                    'is_sell_signal': True,
                    'sell_type': 'partial_sell',
                    'sell_quantity': partial_strategy['sell_quantity'],
                    'remaining_amount': partial_strategy['remaining_amount'],
                    'strategy_type': partial_strategy['strategy_type'],
                    'reason': partial_strategy['reason'],
                    'market_condition': partial_strategy['market_condition'],
                    'analysis': partial_strategy['analysis'],
                    'sell_method': 'partial_sell',
                    'urgent': False
                }
        
        # 🎯 3단계: 일반 전량매도 (기준 조정)
        if legacy_result['is_sell_signal']:
            sell_type = legacy_result.get('sell_type', '')
            
            # 익절의 경우 기준 상향 조정 (분할매도 후에만 전량매도)
            if 'profit' in sell_type:
                if profit_rate >= 0.18:  # 18% 이상에서만 전량매도
                    logger.info(f"✅ {stock_name} 고수익 전량매도: {legacy_result['reason']}")
                    legacy_result['sell_quantity'] = position['amount']
                    legacy_result['remaining_amount'] = 0
                    legacy_result['sell_method'] = 'high_profit_full_sell'
                    return legacy_result
                else:
                    logger.debug(f"📊 {stock_name} 익절 기준 미달: {profit_rate*100:.1f}% < 18%")
            else:
                # 손절, 트레일링 스탑 등은 그대로 적용
                logger.info(f"📉 {stock_name} 일반 전량매도: {legacy_result['reason']}")
                legacy_result['sell_quantity'] = position['amount']
                legacy_result['remaining_amount'] = 0
                legacy_result['sell_method'] = 'normal_full_sell'
                return legacy_result
        
        # 매도 신호 없음
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"매도 신호 없음 (수익률: {profit_rate*100:.2f}%)",
            'sell_quantity': 0,
            'remaining_amount': position['amount'],
            'sell_method': 'hold'
        }
        
    except Exception as e:
        logger.error(f"통합 매도 신호 분석 중 에러: {str(e)}")
        logger.exception("상세 에러 정보:")
        return {
            'is_sell_signal': False, 
            'sell_type': None, 
            'reason': f'분석 오류: {str(e)}',
            'sell_method': 'error'
        }        

def detect_crash_signals(stock_data, position, target_config):
    """폭락조짐 감지 - RSI 급락 + 거래량 급증 + 개선된 섹터 하락률 조합"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position.get('entry_price', 0)
        stock_name = position.get('stock_name', stock_code)
        
        # 수익 상태 체크 (1% 이상)
        if entry_price <= 0:
            return {'has_crash_signal': False, 'reason': 'entry_price 정보 없음'}
        
        profit_rate = (current_price - entry_price) / entry_price
        if profit_rate < 0.01:  # 1% 미만 수익시에는 체크 안함
            return {'has_crash_signal': False, 'reason': f'수익 부족 ({profit_rate*100:.2f}%)'}
        
        crash_signals = []
        signal_count = 0
        
        # 1) RSI 급락 체크
        rsi = stock_data.get('rsi', 50)
        if rsi < 45:
            signal_count += 1
            crash_signals.append(f"RSI 급락 {rsi:.1f}")
            logger.debug(f"폭락조짐 1: RSI 급락 {rsi:.1f}")
        
        # 2) 거래량 급증 체크
        df = stock_data.get('ohlcv_data')
        volume_surge = False
        if df is not None and len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
            
            if volume_ratio >= 1.5:
                signal_count += 1
                volume_surge = True
                crash_signals.append(f"거래량 급증 {volume_ratio:.1f}배")
                logger.debug(f"폭락조짐 2: 거래량 급증 {volume_ratio:.1f}배")
        
        # 3) 개선된 섹터 위험도 체크
        sector_analysis = analyze_sector_risk(stock_code, target_config)
        sector_risk = sector_analysis.get('sector_risk', 'UNKNOWN')
        sector_decline = sector_analysis.get('sector_decline_rate', 0)
        matched_sector = sector_analysis.get('matched_sector', 'Unknown')
        
        # 섹터 위험 신호 판정 (기준 완화)
        sector_signal = False
        if sector_risk == 'CRITICAL':
            signal_count += 1
            sector_signal = True
            crash_signals.append(f"섹터 치명적 위험 ({matched_sector}: {sector_decline:.1f}%)")
        elif sector_risk == 'HIGH' and sector_decline < -2.0:
            signal_count += 1
            sector_signal = True
            crash_signals.append(f"섹터 고위험 ({matched_sector}: {sector_decline:.1f}%)")
        elif sector_risk == 'MEDIUM' and sector_decline < -2.5:
            signal_count += 1
            sector_signal = True
            crash_signals.append(f"섹터 중위험 강화 ({matched_sector}: {sector_decline:.1f}%)")
        
        if sector_signal:
            logger.debug(f"폭락조짐 3: 섹터 위험 {sector_risk} - {matched_sector} ({sector_decline:.1f}%)")
        
        # 폭락조짐 판정 (3개 중 2개 이상)
        has_crash_signal = signal_count >= 2
        
        if has_crash_signal:
            logger.info(f"🚨 {stock_name} 폭락조짐 감지!")
            logger.info(f"   신호 수: {signal_count}/3개")
            logger.info(f"   감지 신호: {', '.join(crash_signals)}")
            logger.info(f"   현재 수익률: {profit_rate*100:.2f}%")
            logger.info(f"   매칭 섹터: {matched_sector}")
        else:
            logger.debug(f"폭락조짐 미감지: {stock_name} ({signal_count}/3개, 섹터: {matched_sector})")
        
        return {
            'has_crash_signal': has_crash_signal,
            'signal_count': signal_count,
            'crash_signals': crash_signals,
            'profit_rate': profit_rate,
            'rsi': rsi,
            'volume_surge': volume_surge,
            'sector_analysis': sector_analysis,
            'matched_sector': matched_sector,
            'reason': f"폭락조짐 {signal_count}/3개 감지 (섹터: {matched_sector})" if has_crash_signal else f"폭락조짐 {signal_count}/3개로 미감지 (섹터: {matched_sector})"
        }
        
    except Exception as e:
        logger.error(f"폭락조짐 감지 중 오류: {str(e)}")
        return {'has_crash_signal': False, 'reason': f'분석 오류: {str(e)}'}        

def analyze_sell_signal_legacy(stock_data, position, target_config):
    """개선된 매도 신호 분석 - 자본 보호 우선 손절 + 트레일링 스탑 보완"""
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position.get('entry_price', 0)
        
        if entry_price <= 0:
            return {'is_sell_signal': False, 'sell_type': None, 'reason': 'entry_price 정보 없음'}
        
        profit_rate = (current_price - entry_price) / entry_price
        entry_signal_strength = position.get('signal_strength', 'NORMAL')
        trailing_mode = position.get('trailing_mode', 'UNKNOWN')
        
        # 🚨 1단계: 긴급 매도 (기준 강화)
        df = stock_data.get('ohlcv_data')
        if df is not None and len(df) >= 3:
            daily_drop = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100
            if daily_drop < -10:  # -15% → -10% (더 엄격하게)
                return {
                    'is_sell_signal': True,
                    'sell_type': 'emergency_exit',
                    'reason': f"급락 긴급매도 {daily_drop:.1f}%",
                    'urgent': True
                }
        
        # 🎯 2단계: 익절 로직 (기존 유지 - 좋음)
        if entry_signal_strength == 'STRONG':
            profit_targets = {
                'quick': 0.08,      # 8% 빠른 익절
                'normal': 0.15,     # 15% 일반 익절  
                'extended': 0.25    # 25% 확장 익절
            }
        else:
            profit_targets = {
                'quick': 0.06,      # 6% 빠른 익절
                'normal': 0.12,     # 12% 일반 익절
                'extended': 0.20    # 20% 확장 익절
            }
        
        # RSI와 볼린저밴드 과열 확인
        rsi = stock_data.get('rsi', 50)
        bb_upper = stock_data.get('bb_upper', 0)
        
        is_overheated = (rsi >= 80) or (bb_upper > 0 and current_price >= bb_upper)
        is_very_overheated = (rsi >= 85) or (bb_upper > 0 and current_price >= bb_upper * 1.02)
        
        # 익절 실행
        if profit_rate >= profit_targets['quick']:
            if is_very_overheated:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'quick_profit_overheated',
                    'reason': f"과열상태 빠른익절 {profit_rate*100:.1f}%",
                    'urgent': False
                }
            elif profit_rate >= profit_targets['normal'] and is_overheated:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'normal_profit_overheated',
                    'reason': f"과열상태 일반익절 {profit_rate*100:.1f}%",
                    'urgent': False
                }
        
        if profit_rate >= profit_targets['extended']:
            return {
                'is_sell_signal': True,
                'sell_type': 'extended_profit',
                'reason': f"확장목표 달성 {profit_rate*100:.1f}%",
                'urgent': False
            }
        
        # 보유시간 계산
        holding_hours = 0
        try:
            entry_time_str = position.get('entry_time', '')
            if entry_time_str:
                if len(entry_time_str) > 10:
                    try:
                        entry_time = datetime.datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        entry_time = datetime.datetime.strptime(entry_time_str, '%Y-%m-%d')
                else:
                    entry_time = datetime.datetime.strptime(entry_time_str, '%Y-%m-%d')
                holding_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
        except:
            holding_days = position.get('holding_days', 0)
            holding_hours = holding_days * 24
        
        # 🔥 3단계: 개선된 손절 로직 - 자본 보호 우선
        
        # 신호별 손절 기준 (대폭 강화)
        if entry_signal_strength == 'STRONG':
            base_stop_loss = -0.08  # -18% → -8% (대폭 강화)
        else:
            base_stop_loss = -0.06  # -15% → -6% (대폭 강화)
        
        # 🎯 시간별 손절 로직 (대폭 단축)
        if holding_hours < 4:  # 2시간 → 4시간 (연장)    
            # 극한 상황 손절 기준 강화
            if profit_rate <= -0.12:  # -25% → -12% (대폭 강화)
                return {
                    'is_sell_signal': True,
                    'sell_type': 'emergency_stop_loss',
                    'reason': f"극한상황 손절 {profit_rate*100:.1f}% (보유 {holding_hours:.1f}시간)",
                    'urgent': True
                }
            else:
                return {
                    'is_sell_signal': False,
                    'sell_type': None,
                    'reason': f"초기보유 손절지연 {profit_rate*100:.1f}% (보유 {holding_hours:.1f}시간)",
                    'urgent': False
                }
        
        elif holding_hours < 12:  # 24시간 → 12시간 (단축)
            # 손절 기준 20% 완화 (50% → 20%)
            adjusted_stop_loss = base_stop_loss * 1.2
        elif holding_hours < 24:  # 72시간 → 24시간 (대폭 단축)
            # 손절 기준 10% 완화 (25% → 10%)
            adjusted_stop_loss = base_stop_loss * 1.1
        else:
            # 기본 손절 기준 적용
            adjusted_stop_loss = base_stop_loss
        
        # 🔥 4단계: RSI 기반 손절 지연 (조건 대폭 강화)
        if profit_rate <= adjusted_stop_loss:
            # 🎯 극도 과매도에서만 지연 (조건 대폭 강화)
            if rsi <= 20:  # 25 → 20 (더 극한 상황에만)
                # 추가 조건: 볼린저밴드 하단 -3% 돌파시에만
                if current_price <= stock_data.get('bb_lower', 0) * 0.97:  # 3% 아래만
                    return {
                        'is_sell_signal': False,
                        'sell_type': None,
                        'reason': f"극도과매도+볼밴하단 손절지연 {profit_rate*100:.1f}% (RSI: {rsi:.1f})",
                        'urgent': False
                    }
            
            # 🔥 기본: 즉시 손절 실행 (지연 조건 대폭 축소)
            return {
                'is_sell_signal': True,
                'sell_type': 'improved_stop_loss',
                'reason': f"자본보호 손절 {profit_rate*100:.1f}% (기준: {adjusted_stop_loss*100:.1f}%)",
                'urgent': True
            }
        
        # 🔥 5단계: 개선된 트레일링 스탑 로직
        trailing_stop = position.get('trailing_stop', 0)
        
        if trailing_stop > 0 and current_price <= trailing_stop:
            # 🎯 트레일링 스탑 조건별 세분화
            
            if trailing_mode == 'PROFIT_PROTECTION':
                # 수익 보호 모드: 정상적인 트레일링 스탑
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop_profit_protection',
                    'reason': f"수익보호 트레일링스탑 {current_price:,}원 ≤ {trailing_stop:,}원 (수익률: {profit_rate*100:.1f}%)",
                    'urgent': False
                }
                
            elif trailing_mode == 'CONSERVATIVE_PROTECTION':
                # 보수적 보호: 소폭 수익 보호
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop_conservative',
                    'reason': f"보수적 트레일링스탑 {current_price:,}원 ≤ {trailing_stop:,}원 (수익률: {profit_rate*100:.1f}%)",
                    'urgent': False
                }
                
            elif trailing_mode in ['BREAKEVEN_PROTECTION', 'LOSS_PROTECTION_ONLY']:
                # 손익분기/손실 보호: 기본 손절선 역할만
                if profit_rate <= -0.03:  # -3% 이상 손실시에만 매도
                    return {
                        'is_sell_signal': True,
                        'sell_type': 'stop_loss_protection',
                        'reason': f"기본 손절 보호 {current_price:,}원 ≤ {trailing_stop:,}원 (수익률: {profit_rate*100:.1f}%)",
                        'urgent': True
                    }
                else:
                    # 손실이 적으면 매도하지 않음 - 🔥 핵심 개선점!
                    logger.info(f"💡 트레일링 스탑 도달했지만 손실이 적어 보유 지속 (수익률: {profit_rate*100:.1f}%)")
                    return {
                        'is_sell_signal': False,
                        'sell_type': None,
                        'reason': f"트레일링 도달하지만 경미한 손실로 보유지속 (수익률: {profit_rate*100:.1f}%)",
                        'urgent': False
                    }
            else:
                # 알 수 없는 모드: 안전하게 매도하지 않음
                logger.warning(f"⚠️ 알 수 없는 트레일링 모드: {trailing_mode}")
                return {
                    'is_sell_signal': False,
                    'sell_type': None,
                    'reason': f"알 수 없는 트레일링 모드로 보유지속 ({trailing_mode})",
                    'urgent': False
                }
        
        # 🔄 6단계: 기존 트레일링 스탑 (호환성 유지)
        high_price = position.get('high_price', entry_price)
        trailing_stop_ratio = target_config.get('trailing_stop', 0.03)
        
        if high_price > entry_price and profit_rate > 0.04:  # 5% → 4% (기준 낮춤)
            trailing_loss = (high_price - current_price) / high_price
            
            # 수익률별 차등 트레일링 (더 타이트하게)
            if profit_rate > 0.20:  # 20% 이상 수익시
                adjusted_trailing = trailing_stop_ratio * 0.5  # 0.6 → 0.5 (더 타이트)
            elif profit_rate > 0.15:  # 15% 이상 수익시
                adjusted_trailing = trailing_stop_ratio * 0.7  # 0.8 → 0.7 (더 타이트)
            elif profit_rate > 0.10:  # 10% 이상 수익시
                adjusted_trailing = trailing_stop_ratio * 0.9  # 1.0 → 0.9 (더 타이트)
            else:
                adjusted_trailing = trailing_stop_ratio * 1.1  # 1.3 → 1.1 (덜 관대)
            
            if trailing_loss >= adjusted_trailing:
                return {
                    'is_sell_signal': True,
                    'sell_type': 'trailing_stop',
                    'reason': f"트레일링스탑 {trailing_loss*100:.1f}% (수익: {profit_rate*100:.1f}%)",
                    'urgent': True
                }

        # 🔥 7단계: 추세 반전 감지 매도 (대폭 개선)
        ma5 = stock_data.get('ma5', 0)
        ma20 = stock_data.get('ma20', 0)

        # 🚨 중요: 수익 상태에서만 추세반전 매도 적용
        if profit_rate > 0.015:  # 1.5% 이상 수익 상태에서만
            # 🆕 보유시간 체크
            min_holding_for_trend_sell = 6  # 6시간
            if holding_hours >= min_holding_for_trend_sell:
                # 더 엄격한 추세반전 조건
                if ma5 < ma20 * 0.96:  # MA5가 MA20보다 4% 아래
                    if rsi < 30:  # RSI 30 미만 (강한 약세)
                        # 🆕 추가 확인 조건
                        df = stock_data.get('ohlcv_data')
                        confirmation_score = 0
                        
                        if df is not None and len(df) >= 5:
                            # 연속 하락 확인
                            recent_changes = df['close'].pct_change().iloc[-3:]
                            down_days = sum(1 for x in recent_changes if x < -0.015)  # 1.5% 이상 하락
                            if down_days >= 2:
                                confirmation_score += 1
                            
                            # 거래량 증가 확인
                            if len(df) >= 10:
                                recent_volume = df['volume'].iloc[-3:].mean()
                                past_volume = df['volume'].iloc[-10:-3].mean()
                                volume_ratio = recent_volume / past_volume if past_volume > 0 else 1.0
                                if volume_ratio > 1.3:  # 30% 이상 거래량 증가
                                    confirmation_score += 1
                            
                            # MACD 확인
                            macd_histogram = stock_data.get('macd_histogram', 0)
                            if macd_histogram < -0.1:  # MACD 히스토그램 음수 확대
                                confirmation_score += 1
                        
                        # 🎯 최소 2개 이상 확인 신호 필요
                        if confirmation_score >= 2:
                            return {
                                'is_sell_signal': True,
                                'sell_type': 'confirmed_trend_reversal',
                                'reason': f"확인된 추세반전 {profit_rate*100:.1f}% (확인신호 {confirmation_score}개, 보유 {holding_hours:.1f}시간)",
                                'urgent': False
                            }
                        else:
                            logger.info(f"추세반전 의심되나 확인 부족 (신호: {confirmation_score}/3개, 수익률: {profit_rate*100:.1f}%)")
            else:
                logger.info(f"보유시간 부족으로 추세반전 매도 제외 ({holding_hours:.1f}/{min_holding_for_trend_sell}시간)")
        else:
            logger.debug(f"수익 부족으로 추세반전 매도 비적용 (수익률: {profit_rate*100:.1f}%)")

        
        # 🔥 8단계: 추가 안전장치 - 연속 하락 손절 (🔥 수정 2: 기준 완화)
        if len(df) >= 3:
            # 최근 3일 연속 하락 + 손실 상태면 매도
            recent_changes = df['close'].pct_change().iloc[-3:]
            consecutive_down = sum(1 for x in recent_changes if x < -0.02)  # 2% 이상 하락
            
            # 🔥 기존: if consecutive_down >= 2 and profit_rate < -0.03: (3% 손실)
            # 🔥 수정: if consecutive_down >= 2 and profit_rate < -0.025: (2.5% 손실)실
            if consecutive_down >= 3 and profit_rate < -0.04:  # 3일 연속 + 4% 손실로 완화    
                return {
                    'is_sell_signal': True,
                    'sell_type': 'consecutive_decline',
                    'reason': f"연속하락 안전매도 {profit_rate*100:.1f}% (연속하락 {consecutive_down}일)",
                    'urgent': True
                }
        
        # 🔥 9단계: 시간 기반 손절 (🔥 수정 3: 새로 추가)
        if holding_hours >= 48 and profit_rate <= -0.05:  # 48시간 + 5% 손실로 완화    
            return {
                'is_sell_signal': True,
                'sell_type': 'time_based_stop_loss',
                'reason': f"장기보유 손절 {profit_rate*100:.1f}% (보유: {holding_hours:.1f}시간)",
                'urgent': True
            }
        
        # 기본: 보유 지속
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"보유지속 (수익률: {profit_rate*100:.1f}%, 보유: {holding_hours:.1f}시간, 모드: {trailing_mode})",
            'urgent': False,
            'profit_rate': profit_rate,
            'holding_hours': holding_hours,
            'trailing_mode': trailing_mode
        }
        
    except Exception as e:
        logger.error(f"개선된 매도 신호 분석 중 에러: {str(e)}")
        return {'is_sell_signal': False, 'sell_type': None, 'reason': f'분석 오류: {str(e)}'}

#//////////////////////////// 상승 강도 기반 적응형 분할매도//////////////////////////////////////////////

def detect_surge_strength(stock_data, position):
    """
    상승 강도 분석하여 매도 전략 결정
    기존 함수들을 재활용하여 복잡도 최소화
    """
    try:
        df = stock_data.get('ohlcv_data')
        current_price = stock_data['current_price']
        
        if df is None or len(df) < 10:
            return {
                'surge_score': 0,
                'surge_signals': ['데이터 부족'],
                'surge_strength': 'WEAK'
            }
        
        surge_signals = []
        surge_score = 0
        
        # 🔥 1. 거래량 급증 분석 (기존 로직 재활용)
        try:
            recent_volume = df['volume'].iloc[-1]
            avg_volume_20d = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = recent_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0
            
            if volume_ratio >= 4.0:
                surge_score += 40
                surge_signals.append(f"거래량 폭증 {volume_ratio:.1f}배")
            elif volume_ratio >= 2.5:
                surge_score += 30
                surge_signals.append(f"거래량 급증 {volume_ratio:.1f}배")
            elif volume_ratio >= 1.5:
                surge_score += 15
                surge_signals.append(f"거래량 증가 {volume_ratio:.1f}배")
                
        except Exception as e:
            logger.debug(f"거래량 분석 오류: {str(e)}")
        
        # 🔥 2. 연속 상승 패턴 분석 (기존 로직 개선)
        try:
            recent_changes = df['close'].pct_change().iloc[-5:]  # 최근 5일
            consecutive_up = 0
            total_gain = 0
            
            for change in recent_changes:
                if change > 0.01:  # 1% 이상 상승
                    consecutive_up += 1
                    total_gain += change
                else:
                    break
            
            avg_daily_gain = total_gain / max(consecutive_up, 1)
            
            if consecutive_up >= 3 and avg_daily_gain >= 0.04:
                surge_score += 35
                surge_signals.append(f"강한 연속상승 {consecutive_up}일({avg_daily_gain*100:.1f}%)")
            elif consecutive_up >= 3 and avg_daily_gain >= 0.02:
                surge_score += 25
                surge_signals.append(f"연속상승 {consecutive_up}일({avg_daily_gain*100:.1f}%)")
            elif consecutive_up >= 2:
                surge_score += 10
                surge_signals.append(f"단기상승 {consecutive_up}일")
                
        except Exception as e:
            logger.debug(f"연속상승 분석 오류: {str(e)}")
        
        # 🔥 3. 기술적 돌파 분석 (기존 볼린저밴드/저항선 로직 활용)
        try:
            bb_upper = stock_data.get('bb_upper', 0)
            resistance = stock_data.get('resistance', 0)
            
            # 볼린저밴드 상단 돌파
            if bb_upper > 0 and current_price >= bb_upper * 1.02:
                surge_score += 25
                surge_signals.append("볼린저밴드 돌파")
            elif bb_upper > 0 and current_price >= bb_upper * 0.98:
                surge_score += 15
                surge_signals.append("볼린저밴드 근접")
            
            # 저항선 돌파
            if resistance > 0 and current_price >= resistance * 1.01:
                surge_score += 20
                surge_signals.append("저항선 돌파")
                
        except Exception as e:
            logger.debug(f"기술적 돌파 분석 오류: {str(e)}")
        
        # 🔥 4. 모멘텀 분석 (기존 RSI 로직 활용)
        try:
            rsi = stock_data.get('rsi', 50)
            
            if rsi >= 85:
                surge_score += 25
                surge_signals.append(f"강한 모멘텀(RSI {rsi:.1f})")
            elif rsi >= 75:
                surge_score += 15
                surge_signals.append(f"상승 모멘텀(RSI {rsi:.1f})")
            elif rsi >= 70:
                surge_score += 5
                surge_signals.append(f"약한 모멘텀(RSI {rsi:.1f})")
                
        except Exception as e:
            logger.debug(f"모멘텀 분석 오류: {str(e)}")
        
        # 🔥 5. 단기 급등률 분석
        try:
            if len(df) >= 3:
                price_3days_ago = df['close'].iloc[-4]  # 3일 전
                recent_gain = (current_price - price_3days_ago) / price_3days_ago
                
                if recent_gain >= 0.20:  # 3일간 20% 이상
                    surge_score += 40
                    surge_signals.append(f"3일간 급등 {recent_gain*100:.1f}%")
                elif recent_gain >= 0.15:  # 3일간 15% 이상
                    surge_score += 30
                    surge_signals.append(f"3일간 강상승 {recent_gain*100:.1f}%")
                elif recent_gain >= 0.10:  # 3일간 10% 이상
                    surge_score += 20
                    surge_signals.append(f"3일간 상승 {recent_gain*100:.1f}%")
                    
        except Exception as e:
            logger.debug(f"단기 급등률 분석 오류: {str(e)}")
        
        # 🔥 6. 상승 강도 분류
        surge_strength = classify_surge_strength(surge_score)
        
        logger.debug(f"상승 강도 분석 완료: 점수 {surge_score}, 강도 {surge_strength}")
        
        return {
            'surge_score': surge_score,
            'surge_signals': surge_signals,
            'surge_strength': surge_strength
        }
        
    except Exception as e:
        logger.error(f"상승 강도 분석 중 오류: {str(e)}")
        return {
            'surge_score': 0,
            'surge_signals': [f"분석 오류: {str(e)}"],
            'surge_strength': 'WEAK'
        }

def classify_surge_strength(surge_score):
    """상승 강도 분류"""
    if surge_score >= 100:
        return 'EXPLOSIVE'      # 폭발적 상승 (100점 이상)
    elif surge_score >= 70:
        return 'STRONG'         # 강한 상승 (70-99점)
    elif surge_score >= 40:
        return 'MODERATE'       # 중간 상승 (40-69점)
    else:
        return 'WEAK'           # 약한 상승 (0-39점)

def calculate_surge_adaptive_partial_sell(stock_data, position, target_config):
    """
    상승 강도 기반 적응형 분할매도 전략
    기존 calculate_market_adaptive_partial_sell 함수를 개선
    """
    try:
        entry_price = position.get('entry_price', 0)
        current_price = stock_data['current_price']
        total_amount = position.get('amount', 0)
        high_price = position.get('high_price', entry_price)
        stock_name = position.get('stock_name', 'Unknown')
        
        if entry_price <= 0 or total_amount <= 0:
            return None
        
        profit_rate = (current_price - entry_price) / entry_price
        drawdown_from_high = (high_price - current_price) / high_price if high_price > entry_price else 0
        
        # 🔥 상승 강도 분석
        surge_analysis = detect_surge_strength(stock_data, position)
        surge_strength = surge_analysis['surge_strength']
        surge_score = surge_analysis['surge_score']
        surge_signals = surge_analysis['surge_signals']
        
        logger.info(f"🔍 {stock_name} 상승 강도 분석:")
        logger.info(f"   강도: {surge_strength} (점수: {surge_score})")
        logger.info(f"   신호: {', '.join(surge_signals[:3])}")
        
        # 🔥 기존 수수료 및 최소 수익률 로직 재활용
        trading_cost_rate = calculate_total_trading_cost_rate(entry_price, total_amount)
        min_profit_threshold = trading_cost_rate * 8
        
        if profit_rate < min_profit_threshold:
            logger.debug(f"   → 최소 수익 기준 미달로 분할매도 안함")
            return None
        
        # 🔥 기존 과열도 체크 로직 재활용
        rsi = stock_data.get('rsi', 50)
        bb_upper = stock_data.get('bb_upper', 0)
        bb_ratio = current_price / bb_upper if bb_upper > 0 else 0.5
        
        df = stock_data.get('ohlcv_data')
        volume_surge = 1.0
        if df is not None and len(df) >= 20:
            recent_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_surge = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        is_overheated = (rsi >= 80 or bb_ratio >= 1.0 or volume_surge >= 5.0)
        
        # 🔥 상승 강도별 분할매도 전략 선택
        if surge_strength == 'EXPLOSIVE':
            partial_strategies = calculate_explosive_surge_strategies(
                profit_rate, total_amount, is_overheated, min_profit_threshold, surge_score
            )
        elif surge_strength == 'STRONG':
            partial_strategies = calculate_strong_surge_strategies(
                profit_rate, total_amount, is_overheated, min_profit_threshold, surge_score
            )
        elif surge_strength == 'MODERATE':
            partial_strategies = calculate_moderate_surge_strategies(
                profit_rate, total_amount, is_overheated, min_profit_threshold, surge_score
            )
        else:  # WEAK
            partial_strategies = calculate_weak_surge_strategies(
                profit_rate, total_amount, is_overheated, min_profit_threshold, surge_score
            )
        
        # 🎯 최우선 전략 선택 (기존 로직 재활용)
        if partial_strategies:
            best_strategy = max(partial_strategies, key=lambda x: x['priority'])
            
            sell_quantity = max(1, int(total_amount * best_strategy['sell_ratio']))
            sell_quantity = min(sell_quantity, total_amount)
            
            logger.info(f"   ✅ 상승강도별 분할매도: {best_strategy['reason']}")
            logger.info(f"   📊 매도 수량: {sell_quantity}주 / {total_amount}주 ({best_strategy['sell_ratio']*100:.0f}%)")
            
            return {
                'should_partial_sell': True,
                'sell_quantity': sell_quantity,
                'sell_ratio': sell_quantity / total_amount,
                'strategy_type': best_strategy['type'],
                'reason': best_strategy['reason'],
                'remaining_amount': total_amount - sell_quantity,
                'surge_analysis': surge_analysis,  # 🔥 상승 분석 정보 추가
                'analysis': {
                    'profit_rate': profit_rate,
                    'drawdown_from_high': drawdown_from_high,
                    'is_overheated': is_overheated,
                    'surge_strength': surge_strength,
                    'surge_score': surge_score,
                    'min_profit_threshold': min_profit_threshold
                }
            }
        
        logger.debug(f"   → 분할매도 조건 불만족")
        return None
        
    except Exception as e:
        logger.error(f"상승강도 적응형 분할매도 계산 중 오류: {str(e)}")
        return None

def calculate_explosive_surge_strategies(profit_rate, total_amount, is_overheated, min_threshold, surge_score):
    """폭발적 상승 시: 매도 지연으로 큰 수익 추구"""
    strategies = []
    
    # 매우 높은 수익률까지 기다림 (기존보다 2-3배 높은 기준)
    if profit_rate >= 0.25:  # 25% 이상에서 60% 매도
        strategies.append({
            'type': 'explosive_major_sell',
            'sell_ratio': 0.6,
            'reason': f'폭발적 상승 주요 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 10
        })
    elif profit_rate >= 0.18:  # 18% 이상에서 40% 매도
        strategies.append({
            'type': 'explosive_moderate_sell',
            'sell_ratio': 0.4,
            'reason': f'폭발적 상승 중간 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 8
        })
    elif profit_rate >= 0.12:  # 12% 이상에서 25% 매도
        strategies.append({
            'type': 'explosive_minimal_sell',
            'sell_ratio': 0.25,
            'reason': f'폭발적 상승 최소 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 6
        })
    
    # 과열시에도 덜 적극적으로 매도
    if is_overheated and profit_rate >= 0.08:
        strategies.append({
            'type': 'explosive_overheated',
            'sell_ratio': 0.3,
            'reason': f'폭발적 상승 중 과열 보호 {profit_rate*100:.1f}%',
            'priority': 7
        })
    
    return strategies

def calculate_strong_surge_strategies(profit_rate, total_amount, is_overheated, min_threshold, surge_score):
    """강한 상승 시: 보수적 분할매도"""
    strategies = []
    
    if profit_rate >= 0.15:  # 15% 이상에서 70% 매도
        strategies.append({
            'type': 'strong_major_sell',
            'sell_ratio': 0.7,
            'reason': f'강한 상승 주요 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 10
        })
    elif profit_rate >= 0.10:  # 10% 이상에서 50% 매도
        strategies.append({
            'type': 'strong_moderate_sell',
            'sell_ratio': 0.5,
            'reason': f'강한 상승 중간 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 9
        })
    elif profit_rate >= 0.06:  # 6% 이상에서 30% 매도
        strategies.append({
            'type': 'strong_partial_sell',
            'sell_ratio': 0.3,
            'reason': f'강한 상승 부분 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 7
        })
    elif profit_rate >= 0.04:  # 4% 이상에서 20% 매도
        strategies.append({
            'type': 'strong_minimal_sell',
            'sell_ratio': 0.2,
            'reason': f'강한 상승 최소 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 5
        })
    
    # 과열시 추가 매도
    if is_overheated and profit_rate >= 0.03:
        strategies.append({
            'type': 'strong_overheated',
            'sell_ratio': 0.4,
            'reason': f'강한 상승 중 과열 보호 {profit_rate*100:.1f}%',
            'priority': 8
        })
    
    return strategies

def calculate_moderate_surge_strategies(profit_rate, total_amount, is_overheated, min_threshold, surge_score):
    """중간 상승 시: 기본 분할매도 (기존보다 약간 적극적)"""
    strategies = []
    
    if profit_rate >= 0.12:  # 12% 이상에서 80% 매도
        strategies.append({
            'type': 'moderate_major_sell',
            'sell_ratio': 0.8,
            'reason': f'중간 상승 주요 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 10
        })
    elif profit_rate >= 0.08:  # 8% 이상에서 60% 매도
        strategies.append({
            'type': 'moderate_high_sell',
            'sell_ratio': 0.6,
            'reason': f'중간 상승 고확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 9
        })
    elif profit_rate >= 0.05:  # 5% 이상에서 40% 매도
        strategies.append({
            'type': 'moderate_partial_sell',
            'sell_ratio': 0.4,
            'reason': f'중간 상승 부분 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 8
        })
    elif profit_rate >= 0.03:  # 3% 이상에서 25% 매도
        strategies.append({
            'type': 'moderate_minimal_sell',
            'sell_ratio': 0.25,
            'reason': f'중간 상승 최소 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 6
        })
    
    # 과열시 적극적 매도
    if is_overheated and profit_rate >= 0.02:
        strategies.append({
            'type': 'moderate_overheated',
            'sell_ratio': 0.5,
            'reason': f'중간 상승 중 과열 보호 {profit_rate*100:.1f}%',
            'priority': 9
        })
    
    return strategies

def calculate_weak_surge_strategies(profit_rate, total_amount, is_overheated, min_threshold, surge_score):
    """약한 상승 시: 적극적 분할매도 (한화시스템 케이스 방지)"""
    strategies = []
    
    # 🔥 핵심: 낮은 수익률부터 적극적 매도 (한화시스템 케이스 방지)
    if profit_rate >= 0.08:  # 8% 이상에서 85% 매도
        strategies.append({
            'type': 'weak_aggressive_major',
            'sell_ratio': 0.85,
            'reason': f'약한 상승 적극 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 10
        })
    elif profit_rate >= 0.05:  # 5% 이상에서 70% 매도
        strategies.append({
            'type': 'weak_aggressive_sell',
            'sell_ratio': 0.7,
            'reason': f'약한 상승 대량 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 9
        })
    elif profit_rate >= 0.03:  # 3% 이상에서 50% 매도
        strategies.append({
            'type': 'weak_moderate_sell',
            'sell_ratio': 0.5,
            'reason': f'약한 상승 중간 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 8
        })
    elif profit_rate >= 0.02:  # 2% 이상에서 35% 매도
        strategies.append({
            'type': 'weak_early_sell',
            'sell_ratio': 0.35,
            'reason': f'약한 상승 조기 확정 {profit_rate*100:.1f}% (점수:{surge_score})',
            'priority': 7
        })
    
    # 과열시 즉시 대량 매도
    if is_overheated and profit_rate >= 0.015:
        strategies.append({
            'type': 'weak_overheated_emergency',
            'sell_ratio': 0.8,
            'reason': f'약한 상승 과열 긴급매도 {profit_rate*100:.1f}%',
            'priority': 11  # 최우선
        })
    
    return strategies

def analyze_sell_signal_with_surge_adaptive(stock_data, position, target_config):
    """
    기존 analyze_sell_signal 함수를 개선
    상승 강도 기반 적응형 분할매도 통합
    """
    try:
        stock_code = stock_data['stock_code']
        current_price = stock_data['current_price']
        entry_price = position.get('entry_price', 0)
        stock_name = position.get('stock_name', stock_code)
        
        if entry_price <= 0:
            return {'is_sell_signal': False, 'sell_type': None, 'reason': 'entry_price 정보 없음'}
        
        profit_rate = (current_price - entry_price) / entry_price
        
        logger.debug(f"🔍 {stock_name} 통합 매도 신호 분석 시작: 수익률 {profit_rate*100:.2f}%")
        
        # 🎯 1단계: 긴급 전량매도 우선 (기존 로직 재활용)
        legacy_result = analyze_sell_signal_legacy(stock_data, position, target_config)
        
        if legacy_result['is_sell_signal']:
            sell_type = legacy_result.get('sell_type', '')
            
            # 긴급 매도는 분할매도보다 우선
            urgent_types = [
                'emergency_exit', 'improved_stop_loss', 'time_based_stop_loss',
                'consecutive_decline', 'emergency_stop_loss'
            ]
            
            if any(urgent_type in sell_type for urgent_type in urgent_types):
                logger.info(f"🚨 {stock_name} 긴급 전량매도: {legacy_result['reason']}")
                legacy_result['sell_quantity'] = position['amount']
                legacy_result['remaining_amount'] = 0
                legacy_result['sell_method'] = 'urgent_full_sell'
                return legacy_result


        # 🆕 2단계: 수익보존 전량매도 검토 (NEW!)
        if profit_rate > 0.01:  # 1% 이상 수익 상태에서만
            crash_analysis = detect_crash_signals(stock_data, position, target_config)
            
            if crash_analysis['has_crash_signal']:
                logger.info(f"🛡️ {stock_name} 수익보존 전량매도 신호!")
                logger.info(f"   수익률: {profit_rate*100:.2f}%")
                logger.info(f"   폭락조짐: {', '.join(crash_analysis['crash_signals'])}")
                
                return {
                    'is_sell_signal': True,
                    'sell_type': 'profit_protection_full_sell',  # 새로운 매도 타입
                    'sell_quantity': position['amount'],
                    'remaining_amount': 0,
                    'strategy_type': 'profit_protection',
                    'reason': f"수익보존 전량매도 {profit_rate*100:.2f}% - {crash_analysis['reason']}",
                    'crash_analysis': crash_analysis,
                    'sell_method': 'profit_protection_full_sell',
                    'urgent': False,
                    'protection_mode': True  # 수익보존 모드 표시
                }

        # 🎯 3단계: 상승 강도 기반 분할매도 검토 (수익 상태에서)
        if profit_rate > 0:  # 수익 상태에서만 분할매도 고려
            # 🔥 기존 함수 대신 개선된 함수 호출
            partial_strategy = calculate_surge_adaptive_partial_sell(stock_data, position, target_config)
            
            if partial_strategy and should_execute_partial_sell(partial_strategy, position, target_config):
                logger.info(f"🎯 {stock_name} 상승강도별 분할매도: {partial_strategy['reason']}")
                
                return {
                    'is_sell_signal': True,
                    'sell_type': 'surge_adaptive_partial_sell',  # 🔥 새로운 타입
                    'sell_quantity': partial_strategy['sell_quantity'],
                    'remaining_amount': partial_strategy['remaining_amount'],
                    'strategy_type': partial_strategy['strategy_type'],
                    'reason': partial_strategy['reason'],
                    'surge_analysis': partial_strategy['surge_analysis'],  # 🔥 상승 분석 정보
                    'analysis': partial_strategy['analysis'],
                    'sell_method': 'surge_adaptive_partial_sell',
                    'urgent': False
                }
        
        # 🎯 4단계: 일반 전량매도 (기존 로직 재활용)
        if legacy_result['is_sell_signal']:
            sell_type = legacy_result.get('sell_type', '')
            
            # 익절의 경우 기준 상향 조정 (분할매도 후에만 전량매도)
            if 'profit' in sell_type:
                if profit_rate >= 0.20:  # 18% → 20%로 상향 (더 엄격)
                    logger.info(f"✅ {stock_name} 고수익 전량매도: {legacy_result['reason']}")
                    legacy_result['sell_quantity'] = position['amount']
                    legacy_result['remaining_amount'] = 0
                    legacy_result['sell_method'] = 'high_profit_full_sell'
                    return legacy_result
                else:
                    logger.debug(f"📊 {stock_name} 익절 기준 미달: {profit_rate*100:.1f}% < 20%")
            else:
                # 손절, 트레일링 스탑 등은 그대로 적용
                logger.info(f"📉 {stock_name} 일반 전량매도: {legacy_result['reason']}")
                legacy_result['sell_quantity'] = position['amount']
                legacy_result['remaining_amount'] = 0
                legacy_result['sell_method'] = 'normal_full_sell'
                return legacy_result
        
        # 매도 신호 없음
        return {
            'is_sell_signal': False,
            'sell_type': None,
            'reason': f"매도 신호 없음 (수익률: {profit_rate*100:.2f}%)",
            'sell_quantity': 0,
            'remaining_amount': position['amount'],
            'sell_method': 'hold'
        }
        
    except Exception as e:
        logger.error(f"상승강도 통합 매도 신호 분석 중 에러: {str(e)}")
        logger.exception("상세 에러 정보:")
        return {
            'is_sell_signal': False, 
            'sell_type': None, 
            'reason': f'분석 오류: {str(e)}',
            'sell_method': 'error'
        }

#////////////////////////////////////////////////////////////////////////////////////////

def analyze_intraday_entry_timing(stock_code, target_config):
    """분봉 기준 최적 진입 타이밍 분석 - API 호출 방식 수정"""
    try:
        # 🔥 KIS API 정확한 사용법으로 수정
        try:
            # 방법 1: KisKR.GetOhlcvNew 사용 (분봉)
            # 'M' = 분봉, 개수, adj_ok=1 (수정주가 적용)
            df_5m = KisKR.GetOhlcvNew(stock_code, 'M', 24, adj_ok=1)
            
            if df_5m is None or len(df_5m) < 10:
                logger.debug(f"KisKR.GetOhlcvNew 분봉 조회 실패: {stock_code}")
                
                # 방법 2: Common.GetOhlcv 기본 호출 (일봉을 짧게)
                df_5m = Common.GetOhlcv("KR", stock_code, 24)  # period 파라미터 제거
                
        except Exception as api_e:
            logger.debug(f"분봉 API 호출 실패: {str(api_e)}, 일봉으로 대체")
            # 방법 3: 일봉 데이터로 대체 (기존 방식)
            df_5m = Common.GetOhlcv("KR", stock_code, 24)
        
        if df_5m is None or len(df_5m) < 10:
            logger.debug(f"모든 데이터 조회 실패: {stock_code}")
            return {'enter_now': True, 'reason': '데이터 부족으로 즉시 진입'}
        
        current_price = KisKR.GetCurrentPrice(stock_code)
        if not current_price:
            return {'enter_now': True, 'reason': '현재가 조회 실패로 즉시 진입'}
        
        # 🔥 데이터 길이에 따른 적응적 분석
        data_length = len(df_5m)
        logger.debug(f"{stock_code} 데이터 길이: {data_length}")
        
        # 기술적 지표 계산 (데이터 길이에 맞게 조정)
        rsi_period = min(14, data_length // 2)
        ma_short = min(5, data_length // 4)
        ma_long = min(20, data_length // 2)
        bb_period = min(20, data_length // 2)
        
        if rsi_period < 3:
            return {'enter_now': True, 'reason': '데이터 부족으로 즉시 진입'}
        
        # 기술적 지표 계산
        df_5m['RSI'] = TechnicalIndicators.calculate_rsi(df_5m, rsi_period)
        df_5m['MA_Short'] = df_5m['close'].rolling(window=ma_short).mean()
        df_5m['MA_Long'] = df_5m['close'].rolling(window=ma_long).mean()
        
        # 볼린저밴드 (데이터가 충분할 때만)
        if data_length >= bb_period:
            bb_data = TechnicalIndicators.calculate_bollinger_bands(df_5m, bb_period, 2.0)
            df_5m[['BB_Mid', 'BB_Upper', 'BB_Lower']] = bb_data
        else:
            # 볼린저밴드 계산 불가시 더미 값
            df_5m['BB_Mid'] = df_5m['close']
            df_5m['BB_Upper'] = df_5m['close'] * 1.02
            df_5m['BB_Lower'] = df_5m['close'] * 0.98
        
        entry_signals = []
        entry_score = 0
        
        # 🎯 1) RSI 기반 신호
        try:
            rsi_current = df_5m['RSI'].iloc[-1]
            if not pd.isna(rsi_current):
                if rsi_current <= 30:
                    entry_score += 30
                    entry_signals.append(f"RSI 과매도 {rsi_current:.1f} (+30)")
                elif rsi_current <= 40:
                    entry_score += 20
                    entry_signals.append(f"RSI 조정 {rsi_current:.1f} (+20)")
                elif rsi_current >= 70:
                    entry_score -= 20
                    entry_signals.append(f"RSI 과매수 {rsi_current:.1f} (-20)")
        except:
            pass
        
        # 🎯 2) 볼린저밴드 기반 신호
        try:
            bb_lower = df_5m['BB_Lower'].iloc[-1]
            bb_upper = df_5m['BB_Upper'].iloc[-1]
            
            if not pd.isna(bb_lower) and current_price <= bb_lower * 1.02:
                entry_score += 25
                entry_signals.append("볼린저 하단 근접 (+25)")
            elif not pd.isna(bb_upper) and current_price >= bb_upper * 0.98:
                entry_score -= 15
                entry_signals.append("볼린저 상단 근접 (-15)")
        except:
            pass
        
        # 🎯 3) 이동평균선 지지
        try:
            ma_short_current = df_5m['MA_Short'].iloc[-1]
            if not pd.isna(ma_short_current):
                distance_ratio = abs(current_price - ma_short_current) / ma_short_current
                if distance_ratio <= 0.01:  # 1% 이내
                    entry_score += 20
                    entry_signals.append(f"{ma_short}MA 지지 (+20)")
        except:
            pass
        
        # 🎯 4) 거래량 신호
        try:
            if data_length >= 10:
                recent_volume = df_5m['volume'].iloc[-3:].mean()
                past_volume = df_5m['volume'].iloc[-10:-3].mean()
                
                if past_volume > 0:
                    volume_ratio = recent_volume / past_volume
                    if volume_ratio >= 1.2:
                        entry_score += 15
                        entry_signals.append(f"거래량 증가 {volume_ratio:.1f}배 (+15)")
        except:
            pass
        
        # 🎯 5) 가격 추세 신호
        try:
            if data_length >= 5:
                # 최근 변화율 계산
                recent_changes = df_5m['close'].pct_change().iloc[-4:]
                down_count = sum(1 for x in recent_changes if x < -0.01)  # 1% 이상 하락
                last_change = df_5m['close'].pct_change().iloc[-1]
                
                if down_count >= 2 and last_change > 0.005:  # 연속 하락 후 반등
                    entry_score += 20
                    entry_signals.append("반등 신호 (+20)")
                
                # 고점 근처 체크
                recent_high = df_5m['high'].iloc[-min(10, data_length):].max()
                if current_price >= recent_high * 0.98:
                    entry_score -= 10
                    entry_signals.append("단기 고점 근처 (-10)")
        except:
            pass
        
        # 🎯 진입 결정
        min_entry_score = target_config.get('min_entry_score', 20)  # 기준 완화
        
        # 데이터 부족시 기준 완화
        if data_length < 20:
            min_entry_score = max(10, min_entry_score - 10)
            entry_signals.append(f"데이터 부족으로 기준 완화 ({data_length}개)")
        
        enter_now = entry_score >= min_entry_score
        
        result = {
            'enter_now': enter_now,
            'entry_score': entry_score,
            'entry_signals': entry_signals,
            'reason': f"{'진입 타이밍 양호' if enter_now else '진입 대기'} (점수: {entry_score}/{min_entry_score})",
            'data_info': {
                'data_length': data_length,
                'rsi_period': rsi_period,
                'ma_periods': [ma_short, ma_long]
            }
        }
        
        logger.debug(f"{stock_code} 분봉 분석 결과: {result['reason']}")
        return result
            
    except Exception as e:
        logger.error(f"분봉 진입 타이밍 분석 중 오류: {str(e)}")
        # 오류 발생시에도 매수 기회를 놓치지 않도록 즉시 진입
        return {
            'enter_now': True, 
            'entry_score': 0,
            'entry_signals': [f"분석 오류: {str(e)}"],
            'reason': '분석 오류로 즉시 진입'
        }
    
################################### 상태 관리 ##################################

def load_trading_state():
    """트레이딩 상태 로드 - pending_orders 필드 추가"""
    try:
        bot_name = get_bot_name()
        with open(f"TargetStockBot_{bot_name}.json", 'r') as f:
            state = json.load(f)
        
        # 🆕 pending_orders 필드 추가 (라이브러리 사용)
        state = enhance_trading_state(state)
        return state
        
    except:
        return enhance_trading_state({
            'positions': {},
            'daily_stats': {
                'date': '',
                'total_profit': 0,
                'total_trades': 0,
                'winning_trades': 0,
                'start_balance': 0
            }
        })

def save_trading_state(state):
    """트레이딩 상태 저장 - numpy 타입 처리 및 에러 로깅"""
        
    def json_serializer(obj):
        """numpy 타입을 JSON 호환 타입으로 변환"""
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.bool_, np.bool)):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    bot_name = get_bot_name()
    filename = f"TargetStockBot_{bot_name}.json"
    
    try:
        logger.info("💾 트레이딩 상태 저장 시작")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=json_serializer)
        
        logger.info(f"✅ 트레이딩 상태 저장 완료: {filename}")
        
        # 저장 내용 요약 로그
        logger.info(f"📊 저장된 데이터:")
        logger.info(f"  - 보유 포지션: {len(state.get('positions', {}))}개")
        logger.info(f"  - 매수 대기: {len(state.get('buy_candidates', {}))}개")
        
    except Exception as e:
        error_msg = f"❌ 트레이딩 상태 저장 실패: {str(e)}"
        logger.error(error_msg)
        logger.exception("저장 실패 상세 정보:")
        
        # Discord 알림으로 중요한 에러 통지
        if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
            discord_alert.SendMessage(f"⚠️ 상태 저장 실패\n{error_msg}\n수동 확인 필요")
        
        raise e  # 에러를 다시 발생시켜 호출자가 인지할 수 있도록

################################### 매매 실행 ##################################

def calculate_position_size(target_config, stock_code, stock_price, trading_state):
    """포지션 크기 계산 - 종목별 예산 한도 적용 (완전 개선 버전)"""
    try:
        stock_name = target_config.get('name', stock_code)
        
        # 🔥 1단계: 기본 유효성 검사
        if stock_price <= 0:
            logger.warning(f"❌ {stock_name}: 주가 오류 ({stock_price})")
            return 0
        
        logger.info(f"💰 {stock_name}({stock_code}) 포지션 크기 계산 시작")
        logger.info(f"   현재가: {stock_price:,}원")
        
        # 🔥 2단계: 예산 한도 계산
        per_stock_limit = get_per_stock_budget_limit()
        if per_stock_limit <= 0:
            logger.warning(f"❌ {stock_name}: 종목별 예산 한도 없음")
            return 0
        
        # 🔥 3단계: 현재 투자 상태 확인 (수정된 함수 사용)
        current_invested = get_invested_amount_for_stock(stock_code, trading_state)
        
        # 🔥 4단계: 미체결 주문 확인
        pending_amount = 0
        if 'pending_orders' in trading_state and stock_code in trading_state['pending_orders']:
            pending_order = trading_state['pending_orders'][stock_code]
            pending_quantity = pending_order.get('quantity', 0)
            pending_price = pending_order.get('price', 0)
            pending_amount = pending_quantity * pending_price
        
        # 🔥 5단계: 실제 사용 가능 예산 계산
        total_committed = current_invested + pending_amount
        remaining_budget_for_stock = per_stock_limit - total_committed
        
        logger.info(f"💰 {stock_name} 예산 현황:")
        logger.info(f"   종목별 한도: {per_stock_limit:,}원")
        logger.info(f"   현재 보유: {current_invested:,}원")
        logger.info(f"   미체결 주문: {pending_amount:,}원")
        logger.info(f"   총 사용중: {total_committed:,}원")
        logger.info(f"   남은 예산: {remaining_budget_for_stock:,}원")
        
        if remaining_budget_for_stock <= 0:
            logger.info(f"❌ {stock_name}: 종목별 예산 한도 초과 (남은예산: {remaining_budget_for_stock:,}원)")
            return 0
        
        # 🔥 6단계: 전체 사용 가능 예산 확인
        total_available_budget = get_available_budget(trading_state)
        if total_available_budget <= 0:
            logger.info(f"❌ {stock_name}: 전체 사용 가능 예산 부족 ({total_available_budget:,}원)")
            return 0
        
        # 🔥 7단계: 실제 사용할 예산 결정 (둘 중 작은 값)
        usable_budget = min(remaining_budget_for_stock, total_available_budget)
        logger.info(f"💰 {stock_name} 사용 가능 예산: {usable_budget:,}원")
        
        # 🔥 8단계: 배분율 적용
        base_allocation = get_safe_config_value(target_config, 'allocation_ratio', 0.35)
        
        # 신호 강도별 배분 조정
        signal_strength = target_config.get('last_signal_strength', 'NORMAL')
        if signal_strength == 'STRONG':
            strength_multiplier = 1.2  # 20% 증가
            logger.info(f"🎯 {stock_name}: 강한 신호 감지 - 배분율 20% 증가")
        else:
            strength_multiplier = 1.0   # 기본값
        
        # 최종 배분율
        enhanced_allocation = base_allocation * strength_multiplier

        # 🆕 여기에 추가 - 바로 다음 줄에
        if enhanced_allocation > 1.0:
            logger.warning(f"⚠️ {stock_name}: 계산된 배분율 {enhanced_allocation:.3f} > 1.0, 1.0으로 제한")
            enhanced_allocation = 1.0

        allocated_budget = usable_budget * enhanced_allocation
        
        logger.info(f"💰 {stock_name} 배분 계산:")
        logger.info(f"   기본 배분율: {base_allocation*100:.1f}%")
        logger.info(f"   신호 배수: {strength_multiplier:.2f}x ({signal_strength})")
        logger.info(f"   최종 배분율: {enhanced_allocation*100:.1f}%")
        logger.info(f"   배분 예산: {allocated_budget:,}원")
        
        # 🔥 9단계: 최소 주문 금액 체크
        min_order_amount = get_safe_config_value(target_config, 'min_order_amount', 10000)
        if allocated_budget < min_order_amount:
            logger.info(f"❌ {stock_name}: 최소 주문금액 미달 ({allocated_budget:,}원 < {min_order_amount:,}원)")
            return 0
        
        # 🔥 10단계: 기본 수량 계산
        base_quantity = int(allocated_budget / stock_price)
        
        if base_quantity <= 0:
            logger.info(f"❌ {stock_name}: 계산된 수량 부족 ({base_quantity}주)")
            return 0
        
        logger.info(f"💰 {stock_name} 기본 계산:")
        logger.info(f"   기본 수량: {base_quantity}주")
        logger.info(f"   기본 금액: {base_quantity * stock_price:,}원")
        
        # 🔥 11단계: 수수료 고려한 조정
        estimated_fee = calculate_trading_fee(stock_price, base_quantity, True)
        total_needed = (stock_price * base_quantity) + estimated_fee
        
        # 예산 내에서 수량 조정
        adjusted_quantity = base_quantity
        while total_needed > allocated_budget and adjusted_quantity > 0:
            adjusted_quantity -= 1
            if adjusted_quantity > 0:
                estimated_fee = calculate_trading_fee(stock_price, adjusted_quantity, True)
                total_needed = (stock_price * adjusted_quantity) + estimated_fee
            else:
                break
        
        if adjusted_quantity <= 0:
            logger.info(f"❌ {stock_name}: 수수료 고려 후 수량 부족")
            return 0
        
        if adjusted_quantity != base_quantity:
            logger.info(f"🔧 {stock_name} 수수료 조정:")
            logger.info(f"   조정 전: {base_quantity}주")
            logger.info(f"   조정 후: {adjusted_quantity}주")
            logger.info(f"   절약된 수수료: {calculate_trading_fee(stock_price, base_quantity, True) - estimated_fee:,}원")
        
        # 🔥 12단계: 최종 안전 검증
        final_amount = stock_price * adjusted_quantity
        final_fee = calculate_trading_fee(stock_price, adjusted_quantity, True)
        final_total = final_amount + final_fee
        
        # 종목별 한도 재검증 (엄격)
        if (total_committed + final_total) > per_stock_limit:
            logger.error(f"❌ {stock_name} 최종 검증 실패 - 종목별 한도 초과:")
            logger.error(f"   기존 투자: {total_committed:,}원")
            logger.error(f"   신규 투자: {final_total:,}원")
            logger.error(f"   합계: {total_committed + final_total:,}원")
            logger.error(f"   한도: {per_stock_limit:,}원")
            logger.error(f"   초과: {(total_committed + final_total) - per_stock_limit:,}원")
            return 0
        
        # 전체 예산 재검증
        if final_total > total_available_budget:
            logger.error(f"❌ {stock_name} 최종 검증 실패 - 전체 예산 초과:")
            logger.error(f"   필요 금액: {final_total:,}원")
            logger.error(f"   사용가능: {total_available_budget:,}원")
            return 0
        
        # 🔥 13단계: 최종 결과 로그
        investment_ratio = (final_total / per_stock_limit) * 100
        usage_after_invest = ((total_committed + final_total) / per_stock_limit) * 100
        
        logger.info(f"✅ {stock_name} 최종 포지션 계산 완료:")
        logger.info(f"   📊 수량: {adjusted_quantity}주")
        logger.info(f"   💰 투자금액: {final_amount:,}원")
        logger.info(f"   💸 수수료: {final_fee:,}원")
        logger.info(f"   💵 총 소요: {final_total:,}원")
        logger.info(f"   📈 종목별 사용률: {usage_after_invest:.1f}% ({total_committed:,}원 → {total_committed + final_total:,}원)")
        logger.info(f"   🎯 투자 비중: {investment_ratio:.1f}%")
        
        # 🔥 14단계: 위험도 체크 및 경고
        if usage_after_invest > 90:
            logger.warning(f"⚠️ {stock_name}: 종목별 한도 90% 초과 ({usage_after_invest:.1f}%)")
        elif usage_after_invest > 80:
            logger.info(f"🟡 {stock_name}: 종목별 한도 80% 이상 ({usage_after_invest:.1f}%)")
        
        # 🔥 15단계: 성공 반환
        return adjusted_quantity
        
    except Exception as e:
        logger.error(f"❌ {stock_code} 포지션 크기 계산 중 오류: {str(e)}")
        logger.exception(f"❌ {stock_code} 상세 오류 정보:")
        return 0

def execute_buy_order(stock_code, target_config, quantity, price):
    """매수 주문 실행 - 최종 중복 방지 체크 강화"""
    try:
        stock_name = target_config.get('name', stock_code)
        
        logger.info(f"🔥 execute_buy_order 시작: {stock_name}({stock_code})")
        logger.info(f"   주문 수량: {quantity}주")
        logger.info(f"   주문 가격: {price:,}원")
        
        # ===== 🔥 1단계: 최종 안전장치 - 주문 실행 직전 마지막 체크 =====
        logger.info("🛡️ 주문 실행 직전 최종 안전 체크...")
        
        # 1-1. 최신 상태 강제 로드
        final_check_state = load_trading_state()
        
        # 1-2. pending_orders 최종 체크
        if 'pending_orders' in final_check_state and stock_code in final_check_state['pending_orders']:
            existing_order = final_check_state['pending_orders'][stock_code]
            
            logger.error(f"🚨 최종 안전장치 작동: {stock_name}")
            logger.error(f"   주문 실행 직전 미체결 주문 재발견!")
            logger.error(f"   기존 주문: {existing_order.get('quantity', 0)}주 @ {existing_order.get('price', 0):,}원")
            logger.error(f"   주문시간: {existing_order.get('order_time', 'Unknown')}")
            logger.error(f"   상태: {existing_order.get('status', 'Unknown')}")
            logger.error(f"   → 매수 주문 긴급 중단!")
            
            # 긴급 Discord 알림
            emergency_msg = f"🚨 긴급! 최종 안전장치 작동\n"
            emergency_msg += f"종목: {stock_name}({stock_code})\n"
            emergency_msg += f"주문 실행 직전 미체결 주문 발견!\n"
            emergency_msg += f"기존: {existing_order.get('quantity', 0)}주 @ {existing_order.get('price', 0):,}원\n"
            emergency_msg += f"→ 중복 주문 긴급 차단됨"
            
            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                discord_alert.SendMessage(emergency_msg)
            
            return None, None
        
        # 1-3. positions 최종 체크
        if 'positions' in final_check_state and stock_code in final_check_state['positions']:
            logger.error(f"🚨 최종 안전장치 작동: {stock_name}")
            logger.error(f"   주문 실행 직전 포지션 재발견!")
            logger.error(f"   → 매수 주문 긴급 중단!")
            return None, None
        
        logger.info(f"✅ 최종 안전 체크 통과: {stock_name}")
        logger.info(f"   매수 주문 실행 진행...")
        
        # 최신 상태 사용
        trading_state = final_check_state
        
        # ===== 🔥 2단계: 기존 중복 주문 방지 로직도 유지 =====
        logger.info("🔍 pending_manager 라이브러리 최종 체크...")
        if pending_manager.check_pending_orders(stock_code, trading_state):
            logger.error(f"❌ pending_manager 최종 체크 실패: {stock_name}")
            logger.error(f"   라이브러리에서 미체결 주문 감지")
            return None, None
        
        logger.info(f"✅ pending_manager 체크 통과: {stock_name}")
        
        # ===== 🔥 3단계: 매수 전 보유량 기록 =====
        initial_holdings = 0
        logger.info("📊 매수 전 보유량 확인 중...")
        try:
            my_stocks = KisKR.GetMyStockList()
            if my_stocks:
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        initial_holdings = int(stock.get('StockAmt', 0))
                        break
            logger.info(f"📊 매수 전 보유량: {initial_holdings}주")
            
            # 보유량이 있다면 중단
            if initial_holdings > 0:
                logger.error(f"🚨 매수 전 보유량 발견: {stock_name}")
                logger.error(f"   보유량: {initial_holdings}주")
                logger.error(f"   → 매수 주문 중단")
                return None, None
                
        except Exception as e:
            logger.warning(f"⚠️ 초기 보유량 확인 실패: {str(e)}")
        
        # ===== 🔥 4단계: 미체결 주문 추적 시작 (라이브러리 사용) =====
        logger.info("📝 미체결 주문 추적 등록 중...")
        order_info = {
            'quantity': quantity,
            'price': price,
            'target_config': target_config,
            'signal_strength': target_config.get('last_signal_strength', 'NORMAL'),
            'daily_score': target_config.get('last_signal_score', 0),
            'order_time': datetime.datetime.now().isoformat()
        }
        
        pending_manager.track_pending_order(trading_state, stock_code, order_info)
        # save_trading_state(trading_state)
        trading_state = save_and_verify_trading_state(trading_state, "미체결 주문 등록")
        
        # ===== 🔥 5단계: 현재가 재조회 (최종 확인) =====
        logger.info("💰 주문 실행 전 현재가 최종 재조회...")
        old_price = price
        try:
            current_price = KisKR.GetCurrentPrice(stock_code)
            if current_price and current_price > 0:
                actual_price = current_price
                price_diff = actual_price - old_price
                logger.info(f"💰 매수 전 현재가 재조회: {stock_name}")
                logger.info(f"   대기시 가격: {old_price:,}원")
                logger.info(f"   현재 가격: {actual_price:,}원")
                logger.info(f"   가격 변화: {price_diff:+,}원")
                
                # 가격 변화가 클 경우 추가 검증
                price_change_rate = abs(price_diff) / old_price
                if price_change_rate > 0.02:  # 2% 이상 변화
                    logger.warning(f"⚠️ 가격 변화 {price_change_rate*100:.1f}% 감지")
                    
            else:
                actual_price = old_price
                logger.warning(f"⚠️ 현재가 조회 실패, 대기시 가격 사용: {actual_price:,}원")
                
        except Exception as price_error:
            actual_price = old_price
            logger.error(f"❌ 현재가 조회 중 오류: {str(price_error)}")
        
        # ===== 🔥 6단계: 주문 접수 알림 (실제 주문가격으로) =====
        order_amount = quantity * actual_price
        estimated_fee = calculate_trading_fee(actual_price, quantity, True)
        
        order_info['price'] = actual_price  # 실제 주문가격으로 업데이트
        order_info['order_amount'] = order_amount
        order_info['estimated_fee'] = estimated_fee
        pending_manager.send_order_alert('submit', stock_code, order_info)
        
        # ===== 🔥 7단계: 실제 주문 실행 =====
        logger.info(f"📋 매수 주문 접수: {stock_name}({stock_code})")
        logger.info(f"주문량: {quantity}주 @ {actual_price:,}원")
        logger.info(f"주문금액: {order_amount:,}원")
        logger.info(f"체결 대기 중...")
        logger.info("")  # 빈 줄 추가
        
        logger.info(f"🔵 {stock_name}({stock_code}) 매수 주문: {quantity}주 @ {actual_price:,}원")
        
        order_result = KisKR.MakeBuyLimitOrder(stock_code, quantity, int(actual_price))
        
        if not order_result or isinstance(order_result, str):
            # ===== 🔥 8단계: 주문 실패시 처리 =====
            logger.error(f"❌ 매수 주문 실패: {stock_name}({stock_code}) - {order_result}")
            
            # pending 제거 (라이브러리 사용)
            trading_state = load_trading_state()
            pending_manager.remove_pending_order(trading_state, stock_code, "주문 실패")
            save_trading_state(trading_state)
            
            # Discord 알림
            error_msg = f"❌ 매수 주문 실패\n"
            error_msg += f"종목: {stock_name}({stock_code})\n"
            error_msg += f"수량: {quantity}주 @ {actual_price:,}원\n"
            error_msg += f"사유: {order_result}\n"
            error_msg += f"→ 미체결 주문 추적 해제됨"
            
            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                discord_alert.SendMessage(error_msg)
            
            return None, None
        
        # ===== 🔥 9단계: 주문 성공시 order_id 업데이트 =====
        logger.info(f"✅ 매수 주문 접수 성공: {stock_name}")
        
        if isinstance(order_result, dict):
            order_id = order_result.get('OrderNum', order_result.get('OrderNo', ''))
            if order_id:
                trading_state = load_trading_state()
                if stock_code in trading_state.get('pending_orders', {}):
                    trading_state['pending_orders'][stock_code]['order_id'] = order_id
                    trading_state['pending_orders'][stock_code]['status'] = 'submitted'
                    save_trading_state(trading_state)
                    logger.info(f"📋 주문번호 등록: {stock_name}({stock_code}) - {order_id}")
        
        # ===== 🔥 10단계: 체결 확인 대기 =====
        logger.info(f"⏱️ 체결 확인 대기 시작: {stock_name}")
        start_time = time.time()
        max_wait_seconds = 600  # 10분
        check_interval = 30     # 30초마다 체크
        
        while time.time() - start_time < max_wait_seconds:
            try:
                # 30초마다 체결 확인
                elapsed_time = time.time() - start_time
                elapsed_minutes = elapsed_time / 60
                remaining_minutes = (max_wait_seconds - elapsed_time) / 60
                
                logger.info(f"⏱️ 체결 대기 중: {elapsed_minutes:.0f}분/{max_wait_seconds/60:.0f}분 (남은시간: {remaining_minutes:.0f}분)")
                
                # 보유량 변화 확인
                my_stocks = KisKR.GetMyStockList()
                current_amount = 0
                
                if my_stocks:
                    for stock in my_stocks:
                        if stock['StockCode'] == stock_code:
                            current_amount = int(stock.get('StockAmt', 0))
                            break
                
                # 보유량이 증가했으면 체결됨
                if current_amount > initial_holdings:
                    executed_amount = current_amount - initial_holdings
                    
                    logger.info(f"✅ 체결 확인: {stock_name}")
                    logger.info(f"   보유량 변화: {initial_holdings}주 → {current_amount}주")
                    logger.info(f"   체결 수량: {executed_amount}주")
                    logger.info(f"   체결 시간: {elapsed_minutes:.1f}분")
                    
                    # ===== 🔥 11단계: 체결 성공 처리 =====
                    # pending 제거
                    trading_state = load_trading_state()
                    pending_manager.remove_pending_order(trading_state, stock_code, "체결 완료")
                    # save_trading_state(trading_state)
                    trading_state = save_and_verify_trading_state(trading_state, "체결 완료 후")
                    
                    # 체결가 조회
                    try:
                        executed_price = KisKR.GetCurrentPrice(stock_code)
                        if not executed_price or executed_price <= 0:
                            executed_price = actual_price
                    except:
                        executed_price = actual_price
                    
                    logger.info(f"📈 최종 체결 결과:")
                    logger.info(f"   체결가: {executed_price:,}원")
                    logger.info(f"   체결량: {executed_amount}주")
                    logger.info(f"   체결금액: {executed_price * executed_amount:,}원")
                    
                    # Discord 체결 알림
                    execution_msg = f"✅ 매수 체결 완료\n"
                    execution_msg += f"종목: {stock_name}({stock_code})\n"
                    execution_msg += f"체결: {executed_amount}주 @ {executed_price:,}원\n"
                    execution_msg += f"투자금액: {executed_price * executed_amount:,}원\n"
                    execution_msg += f"체결시간: {elapsed_minutes:.1f}분"
                    
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(execution_msg)
                    
                    return executed_price, executed_amount
                
                # 체결되지 않았으면 30초 대기
                time.sleep(check_interval)
                
            except Exception as e:
                logger.warning(f"⚠️ 체결 확인 중 오류: {str(e)}")
                time.sleep(check_interval)
        
        # ===== 🔥 12단계: 체결 확인 시간 초과 처리 =====
        elapsed_minutes = (time.time() - start_time) / 60
        logger.warning(f"⏱️ 체결 확인 시간 초과: {stock_code} ({elapsed_minutes:.0f}분)")
        logger.warning(f"⏱️ 매수 미체결: {stock_name}({stock_code})")
        logger.warning(f"주문량: {quantity}주 @ {actual_price:,}원")
        logger.warning(f"자동 관리 대상으로 등록됨")
        
        # Discord 미체결 알림
        pending_msg = f"⏰ 매수 미체결\n"
        pending_msg += f"종목: {stock_name}({stock_code})\n"
        pending_msg += f"주문: {quantity}주 @ {actual_price:,}원\n"
        pending_msg += f"대기시간: {elapsed_minutes:.0f}분\n"
        pending_msg += f"→ 자동 관리 대상으로 등록"
        
        if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
            discord_alert.SendMessage(pending_msg)
        
        # ===== 🔥 13단계: 지연 체결 반환 =====
        # 미체결 상태로 두고 지연 체결 플래그 반환
        logger.info(f"📋 미체결 주문으로 관리 계속: {stock_name}")
        logger.info(f"   다음 루프에서 자동 체결 확인 예정")
        
        return "DELAYED_EXECUTION", quantity
        
    except Exception as e:
        logger.error(f"❌ execute_buy_order 전체 오류 ({stock_code}): {str(e)}")
        logger.exception("❌ 상세 에러 정보:")
        
        # 에러 발생시 pending 제거
        try:
            trading_state = load_trading_state()
            if stock_code in trading_state.get('pending_orders', {}):
                pending_manager.remove_pending_order(trading_state, stock_code, "실행 에러")
                save_trading_state(trading_state)
                logger.info(f"🗑️ 에러로 인한 pending 제거: {stock_code}")
        except:
            pass
        
        return None, None

def process_buy_candidates(trading_state):
    """매수 대기 후보들의 진입 타이밍 재확인 - 중복 매수 방지 강화"""
    try:
        if 'buy_candidates' not in trading_state:
            return trading_state
        
        if not trading_state['buy_candidates']:
            return trading_state
        
        logger.info("🔄 매수 대기 후보 관리 시작")
        logger.info(f"📋 현재 대기 종목: {len(trading_state['buy_candidates'])}개")
        
        # 🔥 1단계: 실제 보유량 조회로 중복 매수 방지
        actual_holdings = {}
        try:
            my_stocks = KisKR.GetMyStockList()
            if my_stocks:
                for stock in my_stocks:
                    stock_code = stock['StockCode']
                    if stock_code in trading_config.target_stocks:
                        actual_holdings[stock_code] = int(stock.get('StockAmt', 0))
                logger.info(f"📊 실제 보유량 조회 완료: {len(actual_holdings)}개 종목")
        except Exception as e:
            logger.warning(f"⚠️ 실제 보유량 조회 실패: {str(e)}")
        
        candidates_to_remove = []
        candidates_executed = []
        candidates_expired = []
        
        for stock_code, candidate_info in trading_state['buy_candidates'].items():
            try:
                # 기본 정보 추출
                opportunity = candidate_info['opportunity']
                stock_name = opportunity['stock_name']
                daily_score = candidate_info.get('daily_score', 0)
                signal_strength = candidate_info.get('signal_strength', 'NORMAL')
                timing_reason = candidate_info.get('timing_reason', '알 수 없음')
                
                logger.info(f"\n🔍 대기 종목 검토: {stock_name}({stock_code})")
                
                # 🔥 2단계: 중복 매수 방지 - 다중 체크
                # 2-1. 봇 기록 체크
                if stock_code in trading_state['positions']:
                    logger.info(f"   ❌ 봇 기록상 이미 보유 중 - 대기 해제")
                    candidates_to_remove.append(stock_code)
                    candidates_expired.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'reason': '봇 기록상 이미 보유',
                        'daily_score': daily_score,
                        'wait_time': 0
                    })
                    continue
                
                # 2-2. 실제 보유량 체크
                actual_amount = actual_holdings.get(stock_code, 0)
                if actual_amount > 0:
                    logger.warning(f"   ❌ 실제 보유 중: {actual_amount}주 - 대기 해제")
                    
                    # 보유량 불일치 알림
                    mismatch_msg = f"⚠️ 대기 중 보유량 불일치 감지\n"
                    mismatch_msg += f"종목: {stock_name}({stock_code})\n"
                    mismatch_msg += f"봇 기록: 대기 중, 실제 보유: {actual_amount}주\n"
                    mismatch_msg += f"→ 대기 해제"
                    
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(mismatch_msg)
                    
                    candidates_to_remove.append(stock_code)
                    candidates_expired.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'reason': f'실제 보유 중 ({actual_amount}주)',
                        'daily_score': daily_score,
                        'wait_time': 0
                    })
                    continue
                
                # 2-3. 미체결 주문 중복 체크
                if pending_manager.check_pending_orders(stock_code, trading_state):
                    logger.info(f"   ❌ 미체결 주문 있음 - 대기 해제")
                    candidates_to_remove.append(stock_code)
                    candidates_expired.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'reason': '미체결 주문 중',
                        'daily_score': daily_score,
                        'wait_time': 0
                    })
                    continue
                
                # 대기 시간 계산
                wait_start = datetime.datetime.fromisoformat(candidate_info['wait_start_time'])
                wait_hours = (datetime.datetime.now() - wait_start).total_seconds() / 3600
                max_wait_hours = candidate_info.get('max_wait_hours', 3.0)
                
                logger.info(f"   ⏰ 대기시간: {wait_hours:.1f}/{max_wait_hours}시간")
                logger.info(f"   📊 일봉점수: {daily_score}점 ({signal_strength})")
                logger.info(f"   🎯 대기전략: {timing_reason}")
                
                # 🕐 3단계: 대기 시간 초과 체크
                if wait_hours > max_wait_hours:
                    logger.info(f"   ⏰ 대기 시간 초과!")
                    
                    # 🎯 강제 매수 여부 결정 (신호 강도별)
                    should_force_buy = False
                    force_reason = ""
                    
                    if signal_strength == 'STRONG':
                        # 강한 신호는 항상 강제 매수
                        should_force_buy = True
                        force_reason = "강한 신호로 강제 매수"
                        
                    elif daily_score >= 60:
                        # 60점 이상은 강제 매수
                        should_force_buy = True
                        force_reason = f"고점수({daily_score}점)로 강제 매수"
                        
                    elif daily_score >= 50:
                        # 50점 이상은 조건부 강제 매수 (현재 RSI 체크)
                        try:
                            stock_data = get_stock_data(stock_code)
                            if stock_data and stock_data.get('rsi', 50) <= 40:
                                should_force_buy = True
                                force_reason = f"중간점수({daily_score}점) + RSI과매도({stock_data['rsi']:.1f})로 강제 매수"
                            else:
                                force_reason = f"중간점수({daily_score}점)지만 RSI({stock_data.get('rsi', 50):.1f})로 매수 포기"
                        except:
                            force_reason = f"중간점수({daily_score}점)지만 데이터 오류로 매수 포기"
                            
                    elif daily_score >= 40:
                        # 40점대는 매수 포기
                        force_reason = f"보통점수({daily_score}점)로 매수 포기"
                        
                    else:
                        # 40점 미만은 매수 포기
                        force_reason = f"낮은점수({daily_score}점)로 매수 포기"
                    
                    logger.info(f"   🎯 강제매수 결정: {force_reason}")
                    
                    if should_force_buy:
                        # 🆕 과열 상태 재검증 (강제매수 전 최종 체크)
                        try:
                            current_stock_data = get_stock_data(stock_code)
                            if current_stock_data:
                                current_buy_analysis = analyze_buy_signal(current_stock_data, trading_config.target_stocks[stock_code])
                                if not current_buy_analysis['is_buy_signal']:
                                    logger.info(f"   ❌ 강제매수 차단: 과열 상태 감지")
                                    candidates_expired.append({
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'reason': '강제매수시 과열 상태 감지',
                                        'daily_score': daily_score,
                                        'wait_time': wait_hours
                                    })
                                    candidates_to_remove.append(stock_code)
                                    continue
                        except Exception as e:
                            logger.warning(f"   ⚠️ 과열 상태 체크 실패: {str(e)}")
                        
                        # 💰 예산 재확인
                        remaining_budget = get_remaining_budget_for_stock(stock_code, trading_state)
                        total_available_budget = get_available_budget(trading_state)
                        
                        if remaining_budget <= 10000 or total_available_budget <= 10000:
                            logger.info(f"   ❌ 예산 부족으로 강제매수 불가")
                            logger.info(f"      종목별 예산: {remaining_budget:,.0f}원")
                            logger.info(f"      전체 예산: {total_available_budget:,.0f}원")
                            candidates_expired.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name, 
                                'reason': '예산 부족',
                                'daily_score': daily_score,
                                'wait_time': wait_hours
                            })
                        else:
                            # 🚀 강제 매수 실행
                            logger.info(f"   🚀 강제 매수 실행 시작")
                            
                            target_config = opportunity['target_config']
                            stock_price = opportunity['price']
                            
                            # 현재가 재확인
                            try:
                                current_price = KisKR.GetCurrentPrice(stock_code)
                                if current_price and current_price > 0:
                                    stock_price = current_price
                                    logger.info(f"      현재가 업데이트: {stock_price:,.0f}원")
                                else:
                                    logger.warning(f"      현재가 조회 실패, 기존 가격 사용: {stock_price:,.0f}원")
                            except Exception as price_error:
                                logger.warning(f"      현재가 조회 중 오류: {str(price_error)}")
                            
                            # 포지션 크기 계산
                            quantity = calculate_position_size(target_config, stock_code, stock_price, trading_state)
                            
                            if quantity < 1:
                                logger.info(f"   ❌ 매수 수량 부족 (계산수량: {quantity})")
                                candidates_expired.append({
                                    'stock_code': stock_code,
                                    'stock_name': stock_name,
                                    'reason': '수량 부족',
                                    'daily_score': daily_score,
                                    'wait_time': wait_hours
                                })
                            else:
                                # 📝 매수 실행
                                logger.info(f"      수량: {quantity}주, 가격: {stock_price:,.0f}원")
                                
                                executed_price, executed_amount = execute_buy_order(
                                    stock_code, target_config, quantity, stock_price
                                )
                                
                                if executed_price and executed_amount:
                                    # ✅ 매수 성공
                                    buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                                    actual_investment = executed_price * executed_amount
                                    
                                    logger.info(f"   ✅ 강제 매수 성공!")
                                    logger.info(f"      체결가: {executed_price:,.0f}원")
                                    logger.info(f"      체결량: {executed_amount}주")
                                    logger.info(f"      투자금액: {actual_investment:,.0f}원")
                                    
                                    # 포지션 정보 저장
                                    position_info = {
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'entry_price': executed_price,
                                        'amount': executed_amount,
                                        'buy_fee': buy_fee,
                                        'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        'high_price': executed_price,
                                        'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', trading_config.trailing_stop_ratio)),
                                        'target_config': target_config,
                                        'buy_analysis': opportunity['analysis'],
                                        'signal_strength': signal_strength,
                                        'daily_score': daily_score,
                                        'entry_method': 'forced_buy_after_wait',  # 🔥 강제매수 표시
                                        'wait_time_hours': wait_hours,
                                        'force_reason': force_reason
                                    }
                                    
                                    trading_state['positions'][stock_code] = position_info
                                    
                                    # 당일 투자 기록
                                    today = datetime.datetime.now().strftime('%Y-%m-%d')
                                    if 'daily_investments' not in trading_state:
                                        trading_state['daily_investments'] = {}
                                    if today not in trading_state['daily_investments']:
                                        trading_state['daily_investments'][today] = {}
                                    
                                    previous_daily = trading_state['daily_investments'][today].get(stock_code, 0)
                                    trading_state['daily_investments'][today][stock_code] = previous_daily + actual_investment
                                    
                                    # 성공 기록
                                    candidates_executed.append({
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'executed_price': executed_price,
                                        'executed_amount': executed_amount,
                                        'investment_amount': actual_investment,
                                        'daily_score': daily_score,
                                        'signal_strength': signal_strength,
                                        'wait_time': wait_hours,
                                        'force_reason': force_reason
                                    })
                                    
                                    # 🎉 Discord 알림
                                    msg = f"⏰ 대기 후 강제 매수: {stock_name}({stock_code})\n"
                                    msg += f"매수가: {executed_price:,.0f}원 × {executed_amount}주\n"
                                    msg += f"투자금액: {actual_investment:,.0f}원\n"
                                    msg += f"대기시간: {wait_hours:.1f}시간\n"
                                    msg += f"일봉점수: {daily_score}점 ({signal_strength})\n"
                                    msg += f"매수사유: {force_reason}"
                                    
                                    logger.info(msg)
                                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                                        discord_alert.SendMessage(msg)
                                        
                                else:
                                    # ❌ 매수 실패
                                    logger.error(f"   ❌ 강제 매수 실패")
                                    candidates_expired.append({
                                        'stock_code': stock_code,
                                        'stock_name': stock_name,
                                        'reason': '주문 실패',
                                        'daily_score': daily_score,
                                        'wait_time': wait_hours
                                    })
                    else:
                        # 📉 매수 포기
                        candidates_expired.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'reason': force_reason,
                            'daily_score': daily_score,
                            'wait_time': wait_hours
                        })
                    
                    # 대기 목록에서 제거
                    candidates_to_remove.append(stock_code)
                    continue
                
                # 🔍 4단계: 아직 대기 시간 내 - 분봉 진입 타이밍 재확인
                logger.info(f"   🕐 대기 시간 내: 분봉 타이밍 재확인")
                
                target_config = opportunity['target_config']
                timing_analysis = analyze_intraday_entry_timing(stock_code, target_config)
                
                current_intraday_score = timing_analysis.get('entry_score', 0)
                min_intraday_score = candidate_info.get('min_intraday_score', 20)
                previous_intraday_score = candidate_info.get('last_intraday_score', 0)
                
                logger.info(f"   분봉 점수: {current_intraday_score}/{min_intraday_score}점 (이전: {previous_intraday_score}점)")
                
                # 점수 변화 분석
                score_change = current_intraday_score - previous_intraday_score
                if score_change != 0:
                    change_direction = "상승" if score_change > 0 else "하락"
                    logger.info(f"   점수 변화: {score_change:+d}점 ({change_direction})")
                
                if timing_analysis['enter_now']:
                    # 🎯 분봉 타이밍 도래!
                    logger.info(f"   🎯 분봉 진입 타이밍 도래!")
                    logger.info(f"      사유: {timing_analysis['reason']}")
                    logger.info(f"      대기시간: {wait_hours:.1f}시간")
                    
                    # 분봉 신호 출력
                    if timing_analysis.get('entry_signals'):
                        logger.info(f"      분봉 신호:")
                        for signal in timing_analysis['entry_signals'][:3]:
                            logger.info(f"        - {signal}")
                    
                    # 💰 예산 재확인
                    remaining_budget = get_remaining_budget_for_stock(stock_code, trading_state)
                    total_available_budget = get_available_budget(trading_state)
                    
                    if remaining_budget <= 10000 or total_available_budget <= 10000:
                        logger.info(f"   ❌ 예산 부족으로 매수 불가")
                        candidates_expired.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'reason': '예산 부족 (분봉 타이밍)',
                            'daily_score': daily_score,
                            'wait_time': wait_hours
                        })
                        candidates_to_remove.append(stock_code)
                        continue
                    
                    # 📝 매수 실행
                    target_config = opportunity['target_config']
                    stock_price = opportunity['price']
                    
                    # 현재가 재확인
                    try:
                        current_price = KisKR.GetCurrentPrice(stock_code)
                        if current_price and current_price > 0:
                            stock_price = current_price
                    except:
                        pass
                    
                    quantity = calculate_position_size(target_config, stock_code, stock_price, trading_state)
                    
                    if quantity < 1:
                        logger.info(f"   ❌ 매수 수량 부족")
                        candidates_expired.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'reason': '수량 부족 (분봉 타이밍)',
                            'daily_score': daily_score,
                            'wait_time': wait_hours
                        })
                    else:
                        logger.info(f"   🔵 분봉 타이밍 매수 실행")
                        
                        executed_price, executed_amount = execute_buy_order(
                            stock_code, target_config, quantity, stock_price
                        )
                        
                        if executed_price and executed_amount:
                            # ✅ 매수 성공
                            buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                            actual_investment = executed_price * executed_amount
                            
                            logger.info(f"   ✅ 분봉 타이밍 매수 성공!")
                            
                            # 포지션 정보 저장
                            position_info = {
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'entry_price': executed_price,
                                'amount': executed_amount,
                                'buy_fee': buy_fee,
                                'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'high_price': executed_price,
                                'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', trading_config.trailing_stop_ratio)),
                                'target_config': target_config,
                                'buy_analysis': opportunity['analysis'],
                                'signal_strength': signal_strength,
                                'daily_score': daily_score,
                                'entry_method': 'intraday_timing_after_wait',
                                'wait_time_hours': wait_hours,
                                'intraday_analysis': timing_analysis,
                                'intraday_score': current_intraday_score
                            }
                            
                            trading_state['positions'][stock_code] = position_info
                            
                            # 당일 투자 기록
                            today = datetime.datetime.now().strftime('%Y-%m-%d')
                            if 'daily_investments' not in trading_state:
                                trading_state['daily_investments'] = {}
                            if today not in trading_state['daily_investments']:
                                trading_state['daily_investments'][today] = {}
                            
                            previous_daily = trading_state['daily_investments'][today].get(stock_code, 0)
                            trading_state['daily_investments'][today][stock_code] = previous_daily + actual_investment
                            
                            # 성공 기록
                            candidates_executed.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'executed_price': executed_price,
                                'executed_amount': executed_amount,
                                'investment_amount': actual_investment,
                                'daily_score': daily_score,
                                'signal_strength': signal_strength,
                                'wait_time': wait_hours,
                                'intraday_score': current_intraday_score,
                                'entry_method': '분봉 타이밍'
                            })
                            
                            # 🎉 Discord 알림
                            msg = f"🎯 분봉 타이밍 매수: {stock_name}({stock_code})\n"
                            msg += f"매수가: {executed_price:,.0f}원 × {executed_amount}주\n"
                            msg += f"투자금액: {actual_investment:,.0f}원\n"
                            msg += f"대기시간: {wait_hours:.1f}시간\n"
                            msg += f"일봉점수: {daily_score}점 ({signal_strength})\n"
                            msg += f"분봉점수: {current_intraday_score}점\n"
                            msg += f"진입사유: {timing_analysis['reason']}"
                            
                            logger.info(msg)
                            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                                discord_alert.SendMessage(msg)
                        else:
                            logger.error(f"   ❌ 분봉 타이밍 매수 실패")
                            candidates_expired.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'reason': '주문 실패 (분봉 타이밍)',
                                'daily_score': daily_score,
                                'wait_time': wait_hours
                            })
                    
                    candidates_to_remove.append(stock_code)
                
                else:
                    # 🔄 계속 대기: 정보 업데이트
                    logger.info(f"   🔄 분봉 타이밍 대기 계속")
                    logger.info(f"      사유: {timing_analysis['reason']}")
                    
                    # 대기 정보 업데이트
                    candidate_info['last_intraday_score'] = current_intraday_score
                    candidate_info['last_check_time'] = datetime.datetime.now().isoformat()
                    candidate_info['check_count'] = candidate_info.get('check_count', 0) + 1
                    
                    # 분봉 신호 변화 추적
                    if timing_analysis.get('entry_signals'):
                        candidate_info['latest_intraday_signals'] = timing_analysis['entry_signals'][:3]
                
            except Exception as e:
                logger.error(f"매수 후보 처리 중 오류 ({stock_code}): {str(e)}")
                logger.exception(f"매수 후보 상세 오류 ({stock_code}):")
                candidates_to_remove.append(stock_code)
                candidates_expired.append({
                    'stock_code': stock_code,
                    'stock_name': stock_code,
                    'reason': f'처리 오류: {str(e)}',
                    'daily_score': 0,
                    'wait_time': 0
                })
        
        # 🗑️ 처리 완료된 후보들 제거
        for stock_code in candidates_to_remove:
            if stock_code in trading_state['buy_candidates']:
                del trading_state['buy_candidates'][stock_code]
        
        # 📊 처리 결과 요약
        total_processed = len(candidates_executed) + len(candidates_expired)
        remaining_candidates = len(trading_state.get('buy_candidates', {}))
        
        logger.info(f"\n📊 매수 대기 후보 처리 완료:")
        logger.info(f"   - 처리된 종목: {total_processed}개")
        logger.info(f"   - 매수 실행: {len(candidates_executed)}개")
        logger.info(f"   - 매수 포기: {len(candidates_expired)}개")
        logger.info(f"   - 계속 대기: {remaining_candidates}개")
        
        # 🎯 실행된 종목 상세 정보
        if candidates_executed:
            logger.info(f"\n✅ 매수 실행된 종목들:")
            for exec_info in candidates_executed:
                logger.info(f"   - {exec_info['stock_name']}({exec_info['stock_code']}): "
                          f"{exec_info['executed_price']:,.0f}원×{exec_info['executed_amount']}주, "
                          f"대기 {exec_info['wait_time']:.1f}시간")
        
        # 📉 포기된 종목 상세 정보
        if candidates_expired:
            logger.info(f"\n❌ 매수 포기된 종목들:")
            for exp_info in candidates_expired:
                logger.info(f"   - {exp_info['stock_name']}({exp_info['stock_code']}): "
                          f"{exp_info['reason']}, 대기 {exp_info['wait_time']:.1f}시간")
        
        # 🔄 계속 대기 중인 종목들
        if remaining_candidates > 0:
            logger.info(f"\n⏳ 계속 대기 중인 종목들:")
            for stock_code, info in trading_state['buy_candidates'].items():
                try:
                    wait_start = datetime.datetime.fromisoformat(info['wait_start_time'])
                    wait_hours = (datetime.datetime.now() - wait_start).total_seconds() / 3600
                    max_wait = info.get('max_wait_hours', 2.0)
                    stock_name = info['opportunity']['stock_name']
                    daily_score = info.get('daily_score', 0)
                    
                    remaining_time = max_wait - wait_hours
                    logger.info(f"   - {stock_name}({stock_code}): "
                              f"{wait_hours:.1f}시간 대기 중 (남은시간: {remaining_time:.1f}시간, {daily_score}점)")
                except Exception as e:
                    logger.warning(f"   - {stock_code}: 대기 정보 오류 ({str(e)})")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"매수 후보 관리 중 전체 오류: {str(e)}")
        logger.exception("매수 후보 관리 상세 에러 정보:")        

def execute_partial_sell_order(stock_code, target_config, sell_quantity, remaining_amount, strategy_type, reason):
    """분할매도 주문 실행"""
    try:
        stock_name = target_config.get('name', stock_code)
        total_amount = sell_quantity + remaining_amount
        
        logger.info(f"🎯 {stock_name}({stock_code}) 분할매도 주문: {sell_quantity}주 (전체 {total_amount}주 중)")
        logger.info(f"   매도 사유: {reason}")
        logger.info(f"   잔여 수량: {remaining_amount}주")
        
        # 기존 매도 함수 활용
        executed_price, executed_amount = execute_sell_order(stock_code, target_config, sell_quantity)
        
        if executed_price == "DELAYED_EXECUTION":
            # 🆕 지연 체결 처리
            logger.warning(f"⏰ 분할매도 지연 체결: {stock_name}")
            logger.warning(f"   📋 주문 접수됨 - 다음 루프에서 수익 기록 예정")
            
            # 지연 매도 정보 임시 저장
            trading_state = load_trading_state()
            if 'delayed_sells' not in trading_state:
                trading_state['delayed_sells'] = {}
            
            trading_state['delayed_sells'][stock_code] = {
                'expected_amount': executed_amount,  # quantity와 동일
                'strategy_type': strategy_type,
                'reason': reason,
                'order_time': datetime.datetime.now().isoformat()
            }
            save_trading_state(trading_state)
            
            return "DELAYED", executed_amount, remaining_amount
            
        elif executed_price and executed_amount:
            # 즉시 체결 성공 (기존 로직)
            logger.info(f"✅ 분할매도 체결: {executed_amount}주 @ {executed_price:,.0f}원")
            return executed_price, executed_amount, remaining_amount
            
        else:
            # 진짜 실패
            logger.error(f"❌ 분할매도 주문 실패: {stock_name}")
            return None, None, total_amount
           
    except Exception as e:
        logger.error(f"분할매도 주문 실행 중 에러: {str(e)}")
        return None, None, sell_quantity + remaining_amount    

def execute_sell_order(stock_code, target_config, quantity):
   """매도 주문 실행 - 체결 확인 개선"""
   try:
       stock_name = target_config.get('name', stock_code)
       logger.info(f"{stock_name}({stock_code}) 매도 주문: {quantity}주")
       
       # 🔥 매도 전 보유량 정확히 기록
       my_stocks_before = KisKR.GetMyStockList()
       initial_amount = 0
       if my_stocks_before:
           for stock in my_stocks_before:
               if stock['StockCode'] == stock_code:
                   initial_amount = int(stock.get('StockAmt', 0))
                   break
       
       # 시장가 매도 주문
       order_result = KisKR.MakeSellMarketOrder(stock_code, quantity)
       
       if not order_result or isinstance(order_result, str):
           logger.error(f"매도 주문 실패: {order_result}")
           return None, None
       
       # 🔥 체결 확인 (60초 → 180초)
       start_time = time.time()
       
       while time.time() - start_time < 180:  # 3분으로 연장
           my_stocks = KisKR.GetMyStockList()
           current_amount = 0
           
           for stock in my_stocks:
               if stock['StockCode'] == stock_code:
                   current_amount = int(stock.get('StockAmt', 0))
                   break
           
           # 보유량이 감소했으면 체결됨
           if current_amount < initial_amount:
               executed_amount = initial_amount - current_amount
               current_price = KisKR.GetCurrentPrice(stock_code)
               logger.info(f"✅ 매도 체결 확인: {executed_amount}주 @ {current_price:,.0f}원")
               return current_price, executed_amount
           
           time.sleep(5)  # 3초 → 5초 (API 부하 고려)
       
       # 🔥 180초 후에도 체결 확인 안됨 - 지연 가능성 높음
       elapsed_time = time.time() - start_time
       logger.warning(f"⏰ 매도 체결 확인 지연: {stock_code} ({elapsed_time:.0f}초)")
       logger.warning(f"   📋 주문 접수됨 - 실제 체결 가능성 높음")
       logger.warning(f"   🔄 다음 포지션 관리에서 보유량 기준 재확인 예정")

       # 🆕 지연 매도 플래그 반환 (None 대신)
       return "DELAYED_EXECUTION", quantity
       
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
        
        msg = "📊 타겟 종목 매매봇 일일 성과 보고서 📊\n"
        msg += f"========== {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} ==========\n"
        msg += f"[전체 계좌 현황]\n"
        msg += f"총 평가금액: {total_money:,.0f}원\n"
        msg += f"누적 손익: {stock_revenue:,.0f}원\n"
        
        if my_stocks:
            msg += "\n[보유 종목 현황]\n"
            for stock in my_stocks:
                stock_code = stock['StockCode']
                if stock_code in trading_state['positions'] and stock_code in trading_config.target_stocks:
                    target_config = trading_config.target_stocks[stock_code]
                    msg += f"- {target_config.get('name', stock_code)}({stock_code}): "
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

def send_target_stock_status():
    """타겟 종목 현황 보고서"""
    try:
        msg = "📋 타겟 종목 현황 📋\n"
        msg += f"====== {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} =====\n"
        
        for stock_code, config in trading_config.target_stocks.items():
            if not config.get('enabled', True):
                continue
                
            current_price = KisKR.GetCurrentPrice(stock_code)
            if current_price:
                stock_data = get_stock_data(stock_code)
                if stock_data:
                    buy_analysis = analyze_buy_signal(stock_data, config)
                    
                    msg += f"\n[{config.get('name', stock_code)}({stock_code})]\n"
                    msg += f"현재가: {current_price:,}원\n"
                    msg += f"RSI: {stock_data['rsi']:.1f} (기준: {config.get('rsi_oversold', trading_config.rsi_oversold)})\n"
                    msg += f"매수점수: {buy_analysis['score']}/{config.get('min_score', 70)}\n"
                    
                    if buy_analysis['is_buy_signal']:
                        msg += "✅ 매수 신호 발생!\n"
                    else:
                        msg += "⏳ 매수 대기 중\n"
        
        logger.info(msg)
        discord_alert.SendMessage(msg)
        
    except Exception as e:
        logger.error(f"타겟 종목 현황 보고서 생성 중 에러: {str(e)}")

################################### 메인 로직 ##################################

def scan_target_stocks(trading_state):
    """타겟 종목 매수 기회 스캔 - 뉴스 분석 통합 (캐시 적용)"""
    try:
        # 기존 로직들...
        if 'recent_sells' in trading_state:
            expired_stocks = []
            now = datetime.datetime.now()
            
            for stock_code, sell_info in trading_state['recent_sells'].items():
                try:
                    sell_time = datetime.datetime.fromisoformat(sell_info['sell_time'])
                    cooldown_hours = sell_info.get('cooldown_hours', 2)
                    
                    if (now - sell_time).total_seconds() / 3600 > cooldown_hours:
                        expired_stocks.append(stock_code)
                except:
                    expired_stocks.append(stock_code)
            
            for stock_code in expired_stocks:
                del trading_state['recent_sells'][stock_code]
            
            if expired_stocks:
                logger.info(f"재매수 방지 만료: {len(expired_stocks)}개 종목")
        
        # 🔥 뉴스 캐시 초기화
        if 'news_cache' not in trading_state:
            trading_state['news_cache'] = {}
        
        # 만료된 뉴스 캐시 정리
        news_cache_hours = trading_config.config.get('news_cache_hours', 6)
        expired_news = []
        for stock_code, cache_data in trading_state['news_cache'].items():
            try:
                last_check = datetime.datetime.fromisoformat(cache_data['last_check'])
                if (datetime.datetime.now() - last_check).total_seconds() / 3600 > news_cache_hours:
                    expired_news.append(stock_code)
            except:
                expired_news.append(stock_code)
        
        for stock_code in expired_news:
            del trading_state['news_cache'][stock_code]
        
        if expired_news:
            logger.info(f"뉴스 캐시 만료: {len(expired_news)}개 종목")
            save_trading_state(trading_state)  # 캐시 정리 저장
        
        buy_opportunities = []
        current_positions = len(trading_state['positions'])

        # 🔥 NEW: 시장 추세 한 번 확인 (모든 종목에 공통 적용)
        market_trend = None
        if trading_config.config.get('use_market_trend_filter', True):
            logger.info("📊 시장 추세 필터 활성화 - 분석 시작...")

            # 첫 실행시 연결 테스트 (한 번만)
            if not hasattr(scan_target_stocks, 'connection_tested'):
                test_market_data_connection()
                scan_target_stocks.connection_tested = True

            market_trend = check_market_trend()
            logger.info(f"📊 오늘 시장 추세: {market_trend['market_condition']} "
                       f"(코스피: {market_trend['kospi_trend']}, 코스닥: {market_trend['kosdaq_trend']})")

        # 🔥 수정 1: 후보종목 풀 또는 기존 타겟 종목 가져오기
        if trading_config.use_candidate_pool:
            scan_stocks = trading_config.get_candidate_stocks()
            logger.info(f"후보종목 풀 스캔 시작: {len(scan_stocks)}개 후보종목 분석")
        else:
            scan_stocks = trading_config.target_stocks
            logger.info(f"기존 타겟 종목 스캔 시작: {len(scan_stocks)}개 종목 분석")        
        
        if current_positions >= get_active_target_stock_count():
            logger.info(f"최대 보유 종목 수 도달({get_active_target_stock_count()}개)")
            return []
        
        logger.info(f"타겟 종목 매수 기회 스캔 시작: {len(trading_config.target_stocks)}개 종목 분석")
        
        # 🔥 뉴스 분석을 위한 종목 리스트 준비
        stocks_for_news = []
        technical_results = {}  # 기술적 분석 결과 저장
        cached_news_count = 0  # 캐시 히트 카운트
        
        # 1단계: 기술적 분석 먼저 수행
        # 🔥 실제 보유량 한 번에 조회 (성능 개선 + 중복 주문 방지)
        actual_holdings = {}
        try:
            my_stocks = KisKR.GetMyStockList()
            if my_stocks:
                for stock in my_stocks:
                    stock_code = stock['StockCode']
                    if stock_code in trading_config.target_stocks:
                        actual_holdings[stock_code] = int(stock.get('StockAmt', 0))
                logger.info(f"📊 실제 보유량 조회 완료: {len(actual_holdings)}개 종목")
        except Exception as e:
            logger.warning(f"⚠️ 실제 보유량 조회 실패: {str(e)}")

        for stock_code, target_config in trading_config.target_stocks.items():
            # ========== 디버깅 코드 시작 ==========
            logger.info(f"🔍 [{stock_code}] 스캔 시작")
            
            try:
                if not target_config.get('enabled', True):
                    logger.info(f"❌ [{stock_code}] 비활성화됨")
                    continue
                    
                if stock_code in trading_state['positions']:
                    logger.info(f"❌ [{stock_code}] 이미 보유 중")
                    continue
                
                # 🆕 미체결 주문 체크 (라이브러리 사용)
                if pending_manager.check_pending_orders(stock_code, trading_state):
                    logger.info(f"❌ [{stock_code}] 미체결 주문 있음")
                    continue

                # 🔥 실제 보유량 체크 (새로 추가되는 핵심 부분!)
                actual_amount = actual_holdings.get(stock_code, 0)
                if actual_amount > 0:
                    stock_name = target_config.get('name', stock_code)
                    logger.info(f"❌ [{stock_code}] 실제 보유 중: {actual_amount}주")
                    
                    # 봇 기록과 실제 보유량 불일치 감지
                    if stock_code not in trading_state['positions']:
                        logger.warning(f"⚠️ 보유량 불일치 감지: {stock_code}")
                        logger.warning(f"   봇 기록: 없음")
                        logger.warning(f"   실제 보유: {actual_amount}주")
                        
                        # Discord 알림
                        if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                            discord_alert.SendMessage(
                                f"⚠️ 보유량 불일치 감지\n"
                                f"종목: {stock_name}({stock_code})\n"
                                f"봇 기록: 없음\n"
                                f"실제 보유: {actual_amount}주\n"
                                f"→ 다른 앱에서 매수한 것으로 추정\n"
                                f"→ 매수 스캔에서 제외"
                            )
                    continue
                
                # 재매수 방지 체크
                if 'recent_sells' in trading_state and stock_code in trading_state['recent_sells']:
                    sell_info = trading_state['recent_sells'][stock_code]
                    try:
                        sell_time = datetime.datetime.fromisoformat(sell_info['sell_time'])
                        cooldown_hours = sell_info.get('cooldown_hours', 2)
                        elapsed_hours = (datetime.datetime.now() - sell_time).total_seconds() / 3600
                        
                        if elapsed_hours < cooldown_hours:
                            remaining_hours = cooldown_hours - elapsed_hours
                            stock_name = target_config.get('name', stock_code)
                            logger.info(f"❌ [{stock_code}] 재매수 방지: 남은시간 {remaining_hours:.1f}시간")
                            continue
                    except:
                        pass
                
                # 가격 필터링 - 디버깅 추가
                logger.info(f"📊 [{stock_code}] 현재가 조회 중...")
                current_price = KisKR.GetCurrentPrice(stock_code)
                logger.info(f"📊 [{stock_code}] 현재가: {current_price}")
                
                if not current_price:
                    logger.info(f"❌ [{stock_code}] 현재가 조회 실패 (None)")
                    continue
                    
                if current_price < trading_config.min_stock_price:
                    logger.info(f"❌ [{stock_code}] 최소가격 미달: {current_price} < {trading_config.min_stock_price}")
                    continue
                    
                if current_price > trading_config.max_stock_price:
                    logger.info(f"❌ [{stock_code}] 최대가격 초과: {current_price} > {trading_config.max_stock_price}")
                    continue
                
                # 종목 데이터 분석 - 디버깅 추가
                logger.info(f"📈 [{stock_code}] 종목 데이터 조회 시작...")
                stock_data = get_stock_data(stock_code)
                
                if not stock_data:
                    logger.info(f"❌ [{stock_code}] 종목 데이터 조회 실패")
                    continue
                
                logger.info(f"✅ [{stock_code}] 매수 신호 분석 시작")
                
                # 매수 신호 분석
                buy_analysis = analyze_buy_signal(stock_data, target_config, market_trend)
                
                # 기술적 분석 결과 저장
                technical_results[stock_code] = {
                    'stock_data': stock_data,
                    'target_config': target_config,
                    'buy_analysis': buy_analysis,
                    'current_price': current_price
                }
                
                # 뉴스 체크가 필요한 종목 선별
                if trading_config.config.get('use_news_analysis', False):
                    news_threshold = trading_config.config.get('news_check_threshold', 35)
                    if buy_analysis['score'] >= news_threshold:
                        # 🔥 캐시 확인
                        if stock_code in trading_state['news_cache']:
                            cache_data = trading_state['news_cache'][stock_code]
                            try:
                                last_check = datetime.datetime.fromisoformat(cache_data['last_check'])
                                cache_age_hours = (datetime.datetime.now() - last_check).total_seconds() / 3600
                                
                                if cache_age_hours < news_cache_hours:
                                    # 캐시 유효 - 바로 사용
                                    cached_news_count += 1
                                    logger.info(f"📰 [{stock_code}] 뉴스 캐시 사용 (캐시 나이: {cache_age_hours:.1f}시간)")
                                else:
                                    # 캐시 만료 - 새로 분석 필요
                                    stocks_for_news.append({
                                        'StockCode': stock_code,
                                        'StockName': target_config.get('name', stock_code)
                                    })
                                    logger.info(f"📰 [{stock_code}] 뉴스 캐시 만료 - 재분석 필요")
                            except:
                                # 캐시 데이터 오류 - 새로 분석
                                stocks_for_news.append({
                                    'StockCode': stock_code,
                                    'StockName': target_config.get('name', stock_code)
                                })
                        else:
                            # 캐시 없음 - 새로 분석
                            stocks_for_news.append({
                                'StockCode': stock_code,
                                'StockName': target_config.get('name', stock_code)
                            })
                            logger.info(f"📰 [{stock_code}] 뉴스 분석 대상 추가 (점수: {buy_analysis['score']})")
                
                if buy_analysis['is_buy_signal']:
                    logger.info(f"🎯 [{stock_code}] 매수 기회 발견! (점수: {buy_analysis.get('score', 0)})")
                else:
                    logger.info(f"⏳ [{stock_code}] 매수 신호 없음 (점수: {buy_analysis.get('score', 0)}/{buy_analysis.get('min_score', 40)})")
                
            except Exception as e:
                logger.error(f"❌ [{stock_code}] 예외 발생: {str(e)}")
                continue
            # ========== 디버깅 코드 끝 ==========
        
        # 2단계: 뉴스 분석 (캐시되지 않은 종목만)
        news_results = {}
        
        # 🔥 캐시된 뉴스 먼저 로드
        if cached_news_count > 0:
            logger.info(f"📰 캐시에서 {cached_news_count}개 종목 뉴스 로드")
            for stock_code in technical_results:
                if stock_code in trading_state['news_cache']:
                    cache_data = trading_state['news_cache'][stock_code]
                    if 'news_score' in cache_data:
                        news_results[stock_code] = cache_data['news_score']
        
        # 🔥 새로운 뉴스 분석 수행
        if stocks_for_news and trading_config.config.get('use_news_analysis', False):
            logger.info(f"📰 {len(stocks_for_news)}개 종목 뉴스 신규 분석 시작")
            try:
                import news_analysis
                news_analysis.set_logger(logger)  # logger 설정
                news_data = news_analysis.analyze_all_stocks_news(stocks_for_news)
                
                # 뉴스 결과를 종목별로 매핑 및 캐시 저장
                if news_data and 'stocks' in news_data:
                    for stock_name, stock_news in news_data['stocks'].items():
                        stock_code = stock_news.get('stock_code')
                        if stock_code and 'analysis' in stock_news:
                            news_score = stock_news['analysis']
                            news_results[stock_code] = news_score
                            
                            # 🔥 캐시에 저장
                            trading_state['news_cache'][stock_code] = {
                                'last_check': datetime.datetime.now().isoformat(),
                                'news_score': news_score,
                                'articles': stock_news.get('articles', [])[:2]  # 최근 2개 기사 제목만 저장
                            }
                            
                            logger.info(f"📰 {stock_name}({stock_code}): {news_score['decision']} "
                                      f"({news_score['percentage']}%) - 캐시 저장")
                    
                    # 캐시 업데이트 저장
                    save_trading_state(trading_state)
                            
            except Exception as e:
                logger.error(f"뉴스 일괄 분석 실패: {str(e)}")
        
        # 3단계: 기술적 분석과 뉴스 분석 결합
        for stock_code, tech_result in technical_results.items():
            buy_analysis = tech_result['buy_analysis']
            target_config = tech_result['target_config']
            stock_name = target_config.get('name', stock_code)
            
            # 뉴스 점수 반영
            if stock_code in news_results:
                news_impact = news_results[stock_code]
                decision = news_impact.get('decision', 'NEUTRAL')
                percentage = news_impact.get('percentage', 0)
                reason = news_impact.get('reason', '')
                
                # 뉴스 점수 계산
                news_weight = trading_config.config.get('news_weight', {})
                positive_mult = news_weight.get('positive_multiplier', 0.3)
                negative_mult = news_weight.get('negative_multiplier', 0.5)
                
                original_score = buy_analysis['score']
                
                if decision == 'POSITIVE':
                    news_score = int(percentage * positive_mult)
                    buy_analysis['score'] += news_score
                    buy_analysis['signals'].append(f"긍정 뉴스 +{news_score}점: {reason[:50]}")
                    logger.info(f"📰 {stock_name}: 긍정 뉴스 +{news_score}점 (기존 {original_score} → {buy_analysis['score']})")
                    
                    # 매우 긍정적 뉴스는 신호 강도 상향
                    if percentage >= 70 and buy_analysis.get('signal_strength') == 'NORMAL':
                        buy_analysis['signal_strength'] = 'STRONG'
                        target_config['last_signal_strength'] = 'STRONG'
                    
                elif decision == 'NEGATIVE':
                    news_score = -int(percentage * negative_mult)
                    
                    # 매우 부정적 뉴스는 스킵
                    if percentage >= 70:
                        logger.info(f"❌ {stock_name}: 강한 부정 뉴스로 제외")
                        continue
                    
                    buy_analysis['score'] += news_score
                    buy_analysis['signals'].append(f"부정 뉴스 {news_score}점: {reason[:50]}")
                    logger.info(f"📰 {stock_name}: 부정 뉴스 {news_score}점 (기존 {original_score} → {buy_analysis['score']})")
                
                buy_analysis['news_impact'] = news_impact
                
                # 뉴스 반영 후 재판단
                buy_analysis['is_buy_signal'] = buy_analysis['score'] >= buy_analysis['min_score']
            
            # 최종 매수 신호 판단
            if buy_analysis['is_buy_signal']:
                buy_opportunities.append({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'price': tech_result['current_price'],
                    'score': buy_analysis['score'],
                    'min_score': buy_analysis['min_score'],
                    'signals': buy_analysis['signals'],
                    'analysis': buy_analysis['analysis'],
                    'target_config': target_config,
                    'signal_strength': buy_analysis.get('signal_strength', 'NORMAL'),
                    'news_impact': buy_analysis.get('news_impact')
                })
                
                logger.info(f"✅ 매수 기회 발견: {stock_name}({stock_code})")
                logger.info(f"   점수: {buy_analysis['score']}/{buy_analysis['min_score']}점")
                for signal in buy_analysis['signals'][:3]:
                    logger.info(f"   - {signal}")
        
        # 점수 순으로 정렬
        # 🔥 4단계: 후보종목 풀 방식에서는 최적 종목 선택
        if trading_config.use_candidate_pool and buy_opportunities:
            logger.info(f"🔍 후보종목 풀에서 최적 종목 선택 시작")
            selected_opportunities = select_target_stocks_from_candidates(buy_opportunities)
            logger.info(f"🎯 후보종목 선택 완료: {len(buy_opportunities)}개 → {len(selected_opportunities)}개")
            
            # 캐시 상태 로깅
            total_cache_entries = len(trading_state.get('news_cache', {}))
            logger.info(f"📰 뉴스 캐시 현황: 총 {total_cache_entries}개 종목, 이번 스캔에서 {cached_news_count}개 재사용")
            
            return selected_opportunities
        else:
            # 기존 방식: 점수 순으로 정렬만
            buy_opportunities.sort(key=lambda x: x['score'], reverse=True)
            
            # 캐시 상태 로깅
            total_cache_entries = len(trading_state.get('news_cache', {}))
            logger.info(f"📰 뉴스 캐시 현황: 총 {total_cache_entries}개 종목, 이번 스캔에서 {cached_news_count}개 재사용")
            
            logger.info(f"📊 기존 방식 매수 기회 스캔 완료: {len(buy_opportunities)}개 발견")
            return buy_opportunities
        
    except Exception as e:
        logger.error(f"매수 기회 스캔 중 에러: {str(e)}")
        return []

def update_trailing_stop(position, current_price, target_config):
    """
    개선된 트레일링 스탑 업데이트 
    - 수익 구간별 차등 적용
    - 분할매도 중 특별 보호
    """
    try:
        entry_price = position.get('entry_price', 0)
        
        if entry_price <= 0:
            logger.warning("매수가 정보가 없어 트레일링 스탑 업데이트 실패")
            return position
        
        # 🔥 1단계: 고점 업데이트 (기존 로직 유지)
        if 'high_price' not in position or current_price > position['high_price']:
            position['high_price'] = current_price
            logger.info(f"고점 업데이트: {current_price:,.0f}원")
        
        high_price = position['high_price']
        current_profit_rate = (current_price - entry_price) / entry_price
        
        # 🆕 분할매도 상태 확인
        partial_sell_count = position.get('partial_sell_count', 0)
        is_partial_mode = partial_sell_count > 0
        
        # 🔥 2단계: 수익 구간별 + 분할매도 상태별 트레일링 비율 결정
        if is_partial_mode:
            # 분할매도 중: 더 관대한 트레일링 (이미 수익 확정했으니)
            if current_profit_rate >= 0.07:  # 7% 이상
                trailing_ratio = 0.03  # 3%
            elif current_profit_rate >= 0.03:  # 3% 이상
                trailing_ratio = 0.035  # 3.5%
            else:
                trailing_ratio = 0.04  # 4%
            mode_desc = "분할매도중"
        else:
            # 일반 상황: 수익 구간별 차등
            if current_profit_rate >= 0.07:  # 7% 이상
                trailing_ratio = 0.03  # 3%
            elif current_profit_rate >= 0.03:  # 3-7%
                trailing_ratio = 0.035  # 3.5%
            elif current_profit_rate >= 0.01:  # 1-3%
                trailing_ratio = 0.04  # 4%
            else:
                trailing_ratio = 0.05  # 5% (더 관대)
            mode_desc = "일반"
        
        # 🔥 3단계: 트레일링 스탑 계산
        basic_trailing_stop = high_price * (1 - trailing_ratio)
        
        # 🎯 매수가 기준 최소 보호선 설정
        min_protection_ratio = target_config.get('min_protection_ratio', 0.03)
        entry_protection_stop = entry_price * (1 - min_protection_ratio)
        
        # 🔥 4단계: 수익 상태별 트레일링 스탑 결정
        if current_profit_rate >= 0.04:  # 4% 이상 수익시
            # 수익 상태: 고점 기준 트레일링 스탑 사용 (단, 매수가 이상 보장)
            safe_trailing_stop = max(basic_trailing_stop, entry_price * 1.005)
            position['trailing_stop'] = safe_trailing_stop
            position['trailing_mode'] = 'PROFIT_PROTECTION'
            
            logger.info(f"🟢 {mode_desc} 수익보호 트레일링: {safe_trailing_stop:,.0f}원 "
                       f"(고점: {high_price:,.0f}원, 수익률: {current_profit_rate*100:.1f}%, 비율: {trailing_ratio*100:.1f}%)")
            
        elif current_profit_rate >= 0.02:  # 2-4% 수익시
            # 소폭 수익: 매수가 기준 보호 (손실 방지)
            conservative_trailing_stop = max(basic_trailing_stop, entry_price * 0.999)
            position['trailing_stop'] = conservative_trailing_stop
            position['trailing_mode'] = 'CONSERVATIVE_PROTECTION'
            
            logger.info(f"🟡 {mode_desc} 보수적 보호: {conservative_trailing_stop:,.0f}원 "
                       f"(매수가 기준, 수익률: {current_profit_rate*100:.1f}%, 비율: {trailing_ratio*100:.1f}%)")
            
        elif current_profit_rate >= -0.02:  # -2% ~ +2% 구간
            # 손익 분기점: 트레일링 스탑 비활성화, 기본 손절만 적용
            position['trailing_stop'] = entry_protection_stop
            position['trailing_mode'] = 'BREAKEVEN_PROTECTION'
            
            logger.info(f"⚪ {mode_desc} 손익분기 보호: {entry_protection_stop:,.0f}원 "
                       f"(기본 손절, 수익률: {current_profit_rate*100:.1f}%)")
            
        else:  # -2% 미만 손실
            # 손실 상태: 트레일링 스탑 완전 비활성화
            position['trailing_stop'] = entry_protection_stop
            position['trailing_mode'] = 'LOSS_PROTECTION_ONLY'
            
            logger.info(f"🔴 {mode_desc} 손실 보호: {entry_protection_stop:,.0f}원 "
                       f"(트레일링 비활성, 수익률: {current_profit_rate*100:.1f}%)")
        
        # 🔥 5단계: 안전성 검증 (기존 로직 유지)
        final_trailing_stop = position['trailing_stop']
        
        if final_trailing_stop > current_price:
            logger.warning(f"⚠️ 트레일링 스탑이 현재가보다 높음 - 조정")
            position['trailing_stop'] = min(final_trailing_stop, current_price * 0.995)
        
        max_loss_stop = entry_price * 0.90
        if position['trailing_stop'] < max_loss_stop:
            logger.warning(f"⚠️ 과도한 손실 방지 - 트레일링 스탑 조정")
            position['trailing_stop'] = max_loss_stop
            
        # 🔥 6단계: 로깅
        logger.info(f"📊 {mode_desc} 트레일링 스탑 업데이트 완료:")
        logger.info(f"   매수가: {entry_price:,.0f}원")
        logger.info(f"   현재가: {current_price:,.0f}원")
        logger.info(f"   고점: {high_price:,.0f}원")
        logger.info(f"   트레일링 스탑: {position['trailing_stop']:,.0f}원")
        logger.info(f"   보호 모드: {position.get('trailing_mode', 'UNKNOWN')}")
        if is_partial_mode:
            logger.info(f"   분할매도 이력: {partial_sell_count}회")
        
        return position
        
    except Exception as e:
        logger.error(f"개선된 트레일링 스탑 업데이트 중 에러: {str(e)}")
        return position

def check_delayed_executions(trading_state):
    """미체결 주문의 지연 체결 확인 - 지정가 주문 지연 체결 대응"""
    try:
        if 'pending_orders' not in trading_state or not trading_state['pending_orders']:
            return trading_state
        
        logger.info(f"🔍 지연 체결 확인 시작: {len(trading_state['pending_orders'])}개 미체결 주문")
        
        my_stocks = KisKR.GetMyStockList()
        if not my_stocks:
            logger.warning("⚠️ 보유종목 조회 실패 - 지연 체결 확인 건너뜀")
            return trading_state
        
        executed_orders = []
        
        for stock_code, pending_info in trading_state['pending_orders'].items():
            try:
                stock_name = pending_info.get('target_config', {}).get('name', stock_code)
                expected_quantity = pending_info.get('quantity', 0)
                order_time_str = pending_info.get('order_time', '')
                
                logger.debug(f"🔍 {stock_name}({stock_code}) 지연 체결 확인 중...")
                
                # 실제 보유량 확인
                actual_amount = 0
                avg_price = 0
                
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        actual_amount = int(stock.get('StockAmt', 0))
                        avg_price = float(stock.get('AvrPrice', 0))
                        break
                
                logger.debug(f"   예상 수량: {expected_quantity}주, 실제 수량: {actual_amount}주")
                
                # 🎯 체결 조건: 실제 보유량이 예상 수량 이상이고 평균가가 있음
                if actual_amount >= expected_quantity and avg_price > 0:
                    
                    # 주문 지연 시간 계산
                    delay_minutes = calculate_order_delay_minutes(order_time_str)
                    
                    logger.info(f"✅ 지연 체결 감지: {stock_name}({stock_code})")
                    logger.info(f"   예상 수량: {expected_quantity}주 → 실제 수량: {actual_amount}주")
                    logger.info(f"   체결 평균가: {avg_price:,.0f}원")
                    logger.info(f"   주문 지연: {delay_minutes}분")
                    
                    # 🔥 포지션 생성
                    target_config = pending_info.get('target_config', {})
                    signal_strength = pending_info.get('signal_strength', 'NORMAL')
                    daily_score = pending_info.get('daily_score', 0)
                    
                    # 트레일링 스탑 계산
                    trailing_stop_ratio = target_config.get('trailing_stop', trading_config.trailing_stop_ratio)
                    trailing_stop = avg_price * (1 - trailing_stop_ratio)
                    
                    position_info = {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'entry_price': avg_price,
                        'amount': actual_amount,
                        'buy_fee': calculate_trading_fee(avg_price, actual_amount, True),
                        'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'high_price': avg_price,
                        'trailing_stop': trailing_stop,
                        'target_config': target_config,
                        'signal_strength': signal_strength,
                        'daily_score': daily_score,
                        'entry_method': 'delayed_execution',  # 🔥 지연 체결 표시
                        'original_order_time': order_time_str,
                        'execution_delay_minutes': delay_minutes,
                        'buy_analysis': {'delayed_execution': True}
                    }
                    
                    # 포지션 저장
                    trading_state['positions'][stock_code] = position_info
                    executed_orders.append(stock_code)
                    
                    # 🎉 지연 체결 알림
                    actual_investment = avg_price * actual_amount
                    msg = f"⏰ 지연 체결 확인: {stock_name}({stock_code})\n"
                    msg += f"체결가: {avg_price:,.0f}원 × {actual_amount}주\n"
                    msg += f"투자금액: {actual_investment:,.0f}원\n"
                    msg += f"주문 지연: {delay_minutes}분\n"
                    msg += f"신호 강도: {signal_strength} ({daily_score}점)\n"
                    msg += f"→ 포지션 자동 등록 완료"
                    
                    logger.info(msg)
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(msg)
                
                else:
                    logger.debug(f"   아직 미체결: {stock_name}({stock_code})")
                    
            except Exception as e:
                logger.error(f"❌ 지연 체결 확인 중 오류 ({stock_code}): {str(e)}")
                continue
        
        # 🗑️ 체결된 주문들을 미체결 목록에서 제거
        for stock_code in executed_orders:
            if stock_code in trading_state['pending_orders']:
                pending_info = trading_state['pending_orders'][stock_code]
                stock_name = pending_info.get('target_config', {}).get('name', stock_code)
                
                del trading_state['pending_orders'][stock_code]
                logger.info(f"🗑️ 미체결 주문 제거: {stock_name}({stock_code}) - 지연 체결 완료")
        
        if executed_orders:
            logger.info(f"✅ 지연 체결 처리 완료: {len(executed_orders)}개 주문")
        else:
            logger.debug("🔍 지연 체결된 주문 없음")
        
        return trading_state
        
    except Exception as e:
        logger.error(f"❌ 지연 체결 확인 중 전체 오류: {str(e)}")
        logger.exception("❌ 지연 체결 확인 상세 오류:")
        return trading_state

def calculate_order_delay_minutes(order_time_str):
    """주문 시간부터 현재까지의 지연 시간 계산 (분)"""
    try:
        if not order_time_str:
            return 0
        
        order_time = datetime.datetime.fromisoformat(order_time_str)
        delay = datetime.datetime.now() - order_time
        return int(delay.total_seconds() / 60)
        
    except Exception as e:
        logger.debug(f"주문 지연 시간 계산 오류: {str(e)}")
        return 0

def process_positions(trading_state):
    """보유 포지션 관리 - API 보유 vs 봇 미기록 케이스 처리 + 분할매도 통합"""
    try:
        logger.info("🔍 포지션 관리 시작 - GetMyStockList 호출 전")
        
        # API 호출 전 로그
        logger.info("📞 KisKR.GetMyStockList() 호출 시작...")
        start_time = time.time()
        
        my_stocks = KisKR.GetMyStockList()
        
        # API 호출 후 로그
        elapsed_time = time.time() - start_time
        logger.info(f"📞 KisKR.GetMyStockList() 완료 - 소요시간: {elapsed_time:.2f}초")
        
        if my_stocks is None:
            logger.error("❌ GetMyStockList 반환값이 None입니다")
            return trading_state
        elif not my_stocks:
            logger.warning("⚠️ GetMyStockList 반환값이 빈 리스트입니다")
            return trading_state
        else:
            logger.info(f"✅ 보유종목 조회 성공: {len(my_stocks)}개 종목")
            # 보유종목 상세 로그
            for stock in my_stocks:
                stock_code = stock.get('StockCode', 'Unknown')
                stock_amt = stock.get('StockAmt', 0)
                now_price = stock.get('NowPrice', 0)
                logger.info(f"   📈 {stock_code}: {stock_amt}주 @ {now_price}원")
        
        positions_to_remove = []
        
        logger.info(f"🔄 봇 기록 포지션 처리 시작: {len(trading_state['positions'])}개")
        
        # 🔥 1단계: 지연 체결 확인 먼저
        trading_state = check_delayed_executions(trading_state)
        
        # 🔥 2단계: 봇 기록 종목들 처리 (기존 로직 + 분할매도 통합)
        for stock_code, position in trading_state['positions'].items():
            try:
                logger.info(f"🔍 포지션 처리 시작: {stock_code}")
                
                # 타겟 종목이 아닌 경우 스킵
                if stock_code not in trading_config.target_stocks:
                    logger.info(f"⏭️ 타겟 종목 아님: {stock_code}")
                    continue
                
                # API에서 실제 보유 확인
                actual_holding = None
                if my_stocks:
                    for stock in my_stocks:
                        if stock['StockCode'] == stock_code:
                            actual_holding = stock
                            break
                
                target_config = trading_config.target_stocks[stock_code]
                stock_name = target_config.get('name', stock_code)
                
                logger.info(f"📊 {stock_name}({stock_code}) 분석 시작")
                
                # 🔥 봇 기록의 수량 사용 (API와 무관)
                current_amount = position.get('amount', 0)
                
                if current_amount <= 0:
                    logger.info(f"❌ 봇 기록상 보유 수량 0 - 포지션 제거: {stock_name}({stock_code})")
                    positions_to_remove.append(stock_code)
                    continue
                
                logger.info(f"💼 봇 기록 수량: {current_amount}주")
                
                # 🔥 실제 보유량과 봇 기록 검증
                actual_amount = 0
                if my_stocks and actual_holding:
                    actual_amount = int(actual_holding.get('StockAmt', 0))
                    logger.info(f"💼 실제 보유량: {actual_amount}주")
                
                # 실제 보유량이 봇 기록보다 적으면 매도 불가
                sell_amount = current_amount  # 기본값: 봇 기록 수량
                
                if my_stocks:  # API 조회 성공시에만 검증
                    if actual_amount == 0:
                        # 실제 보유 없음 - 매도 불가, 포지션만 정리
                        warning_msg = f"⚠️ 실제 보유량 0으로 매도 불가: {stock_name}({stock_code})\n"
                        warning_msg += f"봇 기록: {current_amount}주 → 포지션 정리"
                        logger.warning(warning_msg)
                        discord_alert.SendMessage(warning_msg)
                        positions_to_remove.append(stock_code)
                        continue

                    elif actual_amount < current_amount:
                        # 실제 보유량이 적음 - 부분 매도 감지
                        sold_amount = current_amount - actual_amount
                        current_price = stock_data['current_price']
                        entry_price = position.get('entry_price', 0)
                        
                        warning_msg = f"⚠️ 보유량 불일치로 매도량 조정: {stock_name}\n"
                        warning_msg += f"봇 기록: {current_amount}주 → 실제: {actual_amount}주\n"
                        warning_msg += f"감지된 매도: {sold_amount}주"
                        
                        # 🆕 지연 매도 수익 계산 및 기록
                        if entry_price > 0 and current_price > 0:
                            # 수수료 계산 (추정)
                            buy_fee_ratio = sold_amount / current_amount if current_amount > 0 else 0
                            allocated_buy_fee = position.get('buy_fee', 0) * buy_fee_ratio
                            estimated_sell_fee = calculate_trading_fee(current_price, sold_amount, False)
                            
                            # 수익 계산
                            gross_profit = (current_price - entry_price) * sold_amount
                            net_profit = gross_profit - allocated_buy_fee - estimated_sell_fee
                            
                            # 🔥 일일 통계 업데이트 (핵심!)
                            trading_state['daily_stats']['total_profit'] += net_profit
                            trading_state['daily_stats']['total_trades'] += 1
                            if net_profit > 0:
                                trading_state['daily_stats']['winning_trades'] += 1
                            
                            # 로그 및 알림 추가
                            warning_msg += f"\n📊 추정 수익: {net_profit:,.0f}원 ({((current_price-entry_price)/entry_price)*100:.2f}%)"
                            warning_msg += f"\n일일 통계에 자동 반영됨"
                            
                            logger.info(f"📊 지연 매도 수익 기록: {stock_name}")
                            logger.info(f"   매도량: {sold_amount}주")
                            logger.info(f"   매도가: {current_price:,}원 (추정)")
                            logger.info(f"   총수익: {gross_profit:,}원")
                            logger.info(f"   순수익: {net_profit:,}원")
                            logger.info(f"   수익률: {((current_price-entry_price)/entry_price)*100:.2f}%")
                        
                        discord_alert.SendMessage(warning_msg)
                        
                        # 봇 기록을 실제 수량으로 조정
                        position['amount'] = actual_amount
                        
                        # 🆕 매도 이력 기록 (선택사항)
                        if 'delayed_sell_history' not in position:
                            position['delayed_sell_history'] = []
                        
                        position['delayed_sell_history'].append({
                            'sell_time': datetime.datetime.now().isoformat(),
                            'sold_amount': sold_amount,
                            'estimated_price': current_price,
                            'estimated_profit': net_profit if 'net_profit' in locals() else 0,
                            'detection_method': 'holdings_mismatch'
                        })
                        
                        trading_state['positions'][stock_code] = position

                else:
                    logger.warning(f"⚠️ API 조회 실패 - 봇 기록으로만 관리: {stock_name}({stock_code})")
                
                # 종목 데이터 조회
                logger.info(f"📈 {stock_name} 종목 데이터 조회 시작...")
                stock_data = get_stock_data(stock_code)
                
                if not stock_data:
                    logger.error(f"❌ {stock_name} 종목 데이터 조회 실패")
                    continue
                
                current_price = stock_data['current_price']
                entry_price = position['entry_price']
                profit_rate = (current_price - entry_price) / entry_price
                
                logger.info(f"💰 {stock_name} 가격 정보:")
                logger.info(f"   매수가: {entry_price:,.0f}원")
                logger.info(f"   현재가: {current_price:,.0f}원")
                logger.info(f"   수익률: {profit_rate*100:.2f}%")
                
                # 트레일링 스탑 정보
                trailing_stop = position.get('trailing_stop', 0)
                high_price = position.get('high_price', entry_price)
                
                logger.info(f"🎯 트레일링 스탑 정보:")
                logger.info(f"   고점: {high_price:,.0f}원")
                logger.info(f"   트레일링 스탑: {trailing_stop:,.0f}원")
                logger.info(f"   스탑과 차이: {current_price - trailing_stop:,.0f}원")
                
                # 트레일링 스탑 업데이트
                logger.info(f"🔄 트레일링 스탑 업데이트 체크...")
                position = update_trailing_stop(position, current_price, target_config)
                trading_state['positions'][stock_code] = position
                
                # 🔥 통합 매도 신호 분석 (분할매도 + 전량매도)
                logger.info(f"🔍 {stock_name} 매도 신호 분석 시작...")
                # sell_analysis = analyze_sell_signal(stock_data, position, target_config)
                sell_analysis = analyze_sell_signal_with_surge_adaptive(stock_data, position, target_config)
                
                logger.info(f"📊 매도 신호 분석 결과:")
                logger.info(f"   매도 신호: {sell_analysis['is_sell_signal']}")
                logger.info(f"   매도 유형: {sell_analysis.get('sell_type', 'None')}")
                logger.info(f"   매도 이유: {sell_analysis.get('reason', 'None')}")
                
                if sell_analysis['is_sell_signal']:
                    sell_type = sell_analysis.get('sell_type', 'unknown')
                    sell_quantity = sell_analysis.get('sell_quantity', current_amount)
                    remaining_amount = sell_analysis.get('remaining_amount', 0)
                    sell_method = sell_analysis.get('sell_method', 'unknown')
                    
                    logger.info(f"🔴 매도 신호 감지: {stock_name}({stock_code})")
                    logger.info(f"   매도 유형: {sell_type}")
                    logger.info(f"   매도 방식: {sell_method}")
                    logger.info(f"   매도 사유: {sell_analysis['reason']}")
                    logger.info(f"   매도 수량: {sell_quantity}주 / {current_amount}주")
                    
                    # 🎯 분할매도 vs 전량매도 처리
                    # if sell_method == 'partial_sell' and remaining_amount > 0:
                    if (sell_method in ['partial_sell', 'surge_adaptive_partial_sell'] and 
                        remaining_amount > 0 and 
                        sell_quantity < current_amount):

                        # 🎯 분할매도 실행
                        logger.info(f"🎯 분할매도 실행: {stock_name}")
                        
                        # 실제 보유량과 매도 수량 재검증
                        actual_sell_quantity = min(sell_quantity, sell_amount)  # 실제 보유량 고려
                        
                        executed_price, executed_amount = execute_sell_order(
                            stock_code, target_config, actual_sell_quantity
                        )
                        
                        if executed_price and executed_amount:
                            # 🔥 포지션 업데이트 (전량매도 아님!)
                            sell_fee = calculate_trading_fee(executed_price, executed_amount, False)
                            
                            # 부분 손익 계산
                            buy_fee = position.get('buy_fee', 0)
                            partial_gross_profit = (executed_price - entry_price) * executed_amount
                            
                            # 수수료 배분 (매도 수량 비율로)
                            fee_ratio = executed_amount / current_amount
                            allocated_buy_fee = buy_fee * fee_ratio
                            
                            partial_net_profit = partial_gross_profit - allocated_buy_fee - sell_fee
                            profit_rate_partial = (partial_net_profit / (entry_price * executed_amount)) * 100
                            
                            # 일일 통계 업데이트 (부분 거래)
                            trading_state['daily_stats']['total_profit'] += partial_net_profit
                            trading_state['daily_stats']['total_trades'] += 1
                            if partial_net_profit > 0:
                                trading_state['daily_stats']['winning_trades'] += 1
                            
                            # 🔥 포지션 수량 차감 (핵심!)
                            new_amount = current_amount - executed_amount
                            position['amount'] = new_amount
                            position['buy_fee'] = position.get('buy_fee', 0) - allocated_buy_fee  # 수수료도 차감
                            position['last_partial_sell_time'] = datetime.datetime.now().isoformat()
                            position['last_partial_sell_price'] = executed_price
                            position['last_partial_sell_amount'] = executed_amount
                            position['partial_sell_count'] = position.get('partial_sell_count', 0) + 1
                            position['partial_sell_history'] = position.get('partial_sell_history', [])
                            
                            # 분할매도 이력 기록
                            position['partial_sell_history'].append({
                                'sell_time': datetime.datetime.now().isoformat(),
                                'sell_price': executed_price,
                                'sell_amount': executed_amount,
                                'gross_profit': partial_gross_profit,
                                'net_profit': partial_net_profit,
                                'profit_rate': profit_rate_partial,
                                'strategy_type': sell_analysis.get('strategy_type', 'unknown'),
                                'market_condition': sell_analysis.get('market_condition', 'unknown'),
                                'sell_fee': sell_fee,
                                'allocated_buy_fee': allocated_buy_fee
                            })
                            
                            # 포지션 업데이트 저장
                            trading_state['positions'][stock_code] = position
                            
                            # 🎉 분할매도 완료 알림
                            strategy_type = sell_analysis.get('strategy_type', 'unknown')
                            market_condition = sell_analysis.get('market_condition', 'unknown')
                            
                            msg = f"🎯 분할매도 완료: {stock_name}({stock_code})\n"
                            msg += f"매도: {executed_price:,.0f}원 × {executed_amount}주\n"
                            msg += f"총손익: {partial_gross_profit:,.0f}원\n"
                            msg += f"순손익: {partial_net_profit:,.0f}원 ({profit_rate_partial:.2f}%)\n"
                            msg += f"남은보유: {new_amount}주\n"
                            msg += f"시장상황: {market_condition}\n"
                            msg += f"매도전략: {strategy_type}\n"
                            msg += f"매도사유: {sell_analysis['reason']}"
                            
                            # 분할매도 이력 추가 정보
                            total_partial_count = position['partial_sell_count']
                            if total_partial_count > 1:
                                msg += f"\n분할매도 횟수: {total_partial_count}회"
                            
                            logger.info(msg)
                            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                                discord_alert.SendMessage(msg)
                            
                            logger.info(f"✅ 분할매도 완료: {stock_name} - {executed_amount}주 매도, {new_amount}주 보유")
                            
                        else:
                            logger.error(f"❌ 분할매도 실패: {stock_name}")
                    
                    else:
                        # 🔥 전량매도 실행 (기존 로직)
                        logger.info(f"🔥 전량매도 실행: {stock_name}")
                        logger.info(f"   매도 방식: {sell_method}")
                        
                        # 실제 보유량과 매도 수량 재검증
                        actual_sell_quantity = min(sell_quantity, sell_amount)
                        
                        executed_price, executed_amount = execute_sell_order(
                            stock_code, target_config, actual_sell_quantity
                        )
                        
                        if executed_price and executed_amount:
                            # 기존 전량매도 처리 로직 그대로 사용
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
                            
                            # 🔥 재매수 방지 기록
                            if 'recent_sells' not in trading_state:
                                trading_state['recent_sells'] = {}
                            
                            # 매도 유형별 쿨다운 차등 적용
                            if 'overheated' in sell_analysis.get('sell_type', ''):
                                cooldown_hours = 24
                            elif sell_method == 'high_profit_full_sell':
                                cooldown_hours = 12  # 고수익 전량매도는 짧은 쿨다운
                            elif sell_method == 'urgent_full_sell':
                                cooldown_hours = 6   # 긴급매도는 기본 쿨다운
                            else:
                                cooldown_hours = 6
                            
                            trading_state['recent_sells'][stock_code] = {
                                'sell_time': datetime.datetime.now().isoformat(),
                                'sell_reason': sell_analysis.get('sell_type', 'unknown'),
                                'sell_method': sell_method,
                                'cooldown_hours': cooldown_hours
                            }
                            
                            # 전량매도 완료 알림

                            # 전량매도 완료 알림 (수익보존 매도 구분)
                            if sell_method == 'profit_protection_full_sell':

                                # 수익보존 전량매도 알림 (섹터 정보 강화)
                                crash_analysis = sell_analysis.get('crash_analysis', {})
                                crash_signals = crash_analysis.get('crash_signals', [])
                                sector_analysis = crash_analysis.get('sector_analysis', {})
                                matched_sector = crash_analysis.get('matched_sector', 'Unknown')
                                
                                msg = f"🛡️ 수익보존 전량매도: {stock_name}({stock_code})\n"
                                msg += f"매도가: {executed_price:,.0f}원 × {executed_amount}주\n"
                                msg += f"보존수익: {gross_profit:,.0f}원\n"
                                msg += f"순수익: {net_profit:,.0f}원 ({profit_rate:.2f}%)\n"
                                msg += f"\n🚨 폭락조짐 감지:\n"
                                
                                for signal in crash_signals:
                                    msg += f"• {signal}\n"
                                
                                # 섹터 상세 정보 추가
                                if matched_sector != 'Unknown':
                                    msg += f"\n📊 섹터 분석: {matched_sector}\n"
                                    msg += f"• 위험도: {sector_analysis.get('sector_risk', 'Unknown')}\n"
                                    msg += f"• 평균 변화율: {sector_analysis.get('sector_decline_rate', 0):.2f}%\n"
                                    
                                    # 주요 하락 종목 표시
                                    affected_stocks = sector_analysis.get('affected_stocks', [])
                                    if affected_stocks:
                                        msg += f"• 하락 종목: "
                                        stock_names = [s['name'] for s in affected_stocks[:3]]
                                        msg += f"{', '.join(stock_names)}\n"
                                
                                msg += f"\n⏰ 재매수 방지: {cooldown_hours}시간"
                                msg += f"\n💡 큰 손실 방지 성공!"
                                
                                logger.info(f"🛡️ 수익보존 매도로 {matched_sector} 섹터 위험 회피!")

                            else:                            
                                msg = f"💰 전량매도 완료: {stock_name}({stock_code})\n"
                                msg += f"매도가: {executed_price:,.0f}원 × {executed_amount}주\n"
                                msg += f"총손익: {gross_profit:,.0f}원\n"
                                msg += f"순손익: {net_profit:,.0f}원 ({profit_rate:.2f}%)\n"
                                msg += f"매도방식: {sell_method}\n"
                                msg += f"매도사유: {sell_analysis['reason']}\n"
                                msg += f"재매수 방지: {cooldown_hours}시간"
                            
                            # 분할매도 이력이 있었다면 추가 정보
                            partial_count = position.get('partial_sell_count', 0)
                            if partial_count > 0:
                                msg += f"\n분할매도 이력: {partial_count}회"
                                
                                # 분할매도 총 수익 계산
                                partial_history = position.get('partial_sell_history', [])
                                total_partial_profit = sum(h.get('net_profit', 0) for h in partial_history)
                                total_profit_with_partial = net_profit + total_partial_profit
                                msg += f"\n총 누적손익: {total_profit_with_partial:,.0f}원"
                            
                            logger.info(msg)
                            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                                discord_alert.SendMessage(msg)
                            
                            # 적응형 전략 학습 (기존 로직 유지)
                            if trading_config.use_adaptive_strategy:
                                try:
                                    from technical_analysis import AdaptiveMarketStrategy
                                    stock_env = sell_analysis.get('stock_environment', 'sideways')
                                    adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
                                    adaptive_strategy.update_performance(
                                        stock_code, 
                                        stock_env, 
                                        win=(net_profit > 0)
                                    )
                                    win_lose = "승리" if net_profit > 0 else "패배"
                                    logger.info(f"🧠 적응형 전략 학습: {stock_code} ({stock_env}) - {win_lose}")
                                except Exception as e:
                                    logger.error(f"적응형 전략 학습 오류: {str(e)}")
                            
                            # 포지션 완전 제거
                            positions_to_remove.append(stock_code)
                        
                        else:
                            logger.error(f"❌ 전량매도 주문 실패: {stock_name}")

                else:
                    logger.info(f"⏳ 매도 신호 없음: {stock_name} - 포지션 유지")
                
                logger.info(f"✅ {stock_name}({stock_code}) 포지션 처리 완료")
                
            except Exception as e:
                logger.error(f"❌ 포지션 처리 오류 ({stock_code}): {str(e)}")
                logger.exception(f"❌ {stock_code} 상세 에러 정보:")
                continue
        
        # 🔥 3단계: API에는 있지만 봇 기록에 없는 종목 체크 (지연 체결 고려)
        logger.info("🔍 API 보유 vs 봇 미기록 종목 체크 시작...")
        if my_stocks:  # API 조회 성공시에만
            bot_tracked_stocks = set(trading_state['positions'].keys())
            
            for stock in my_stocks:
                stock_code = stock['StockCode']
                actual_amount = int(stock.get('StockAmt', 0))
                
                # 타겟 종목이고, 실제 보유량이 있고, 봇 기록에 없는 경우
                if (stock_code in trading_config.target_stocks and 
                    trading_config.target_stocks[stock_code].get('enabled', True) and  # ← 이 줄 추가
                    actual_amount > 0 and 
                    stock_code not in bot_tracked_stocks):
                    
                    stock_name = trading_config.target_stocks[stock_code].get('name', stock_code)
                    current_price = float(stock.get('NowPrice', 0))
                    
                    # 🎯 미체결 주문 확인
                    is_pending_order = stock_code in trading_state.get('pending_orders', {})
                    
                    if is_pending_order:
                        # 미체결 주문이 있으면 지연 체결 가능성으로 판단
                        pending_info = trading_state['pending_orders'][stock_code]
                        order_time_str = pending_info.get('order_time', '')
                        
                        try:
                            order_time = datetime.datetime.fromisoformat(order_time_str)
                            delay_minutes = (datetime.datetime.now() - order_time).total_seconds() / 60
                        except:
                            delay_minutes = 0
                        
                        logger.info(f"⏳ 미체결 주문 대기 중: {stock_name}({stock_code})")
                        logger.info(f"   실제 보유: {actual_amount}주")
                        logger.info(f"   주문 경과: {delay_minutes:.0f}분")
                        logger.info(f"   → 다음 지연 체결 확인에서 자동 처리 예정")
                        
                        # 30분 이상 지연시에만 알림
                        if delay_minutes >= 30:
                            delay_warning = f"⏰ 장시간 미체결: {stock_name}({stock_code})\n"
                            delay_warning += f"주문 경과: {delay_minutes:.0f}분\n"
                            delay_warning += f"실제 보유: {actual_amount}주\n"
                            delay_warning += f"→ 지연 체결 확인 중..."
                            
                            logger.warning(delay_warning)
                            discord_alert.SendMessage(delay_warning)
                    else:
                        # 미체결 주문도 없으면 정말 외부 매수
                        warning_msg = f"🤔 확인 필요: {stock_name}({stock_code})\n"
                        warning_msg += f"실제 계좌: {actual_amount}주 (현재가: {current_price:,.0f}원)\n"
                        warning_msg += f"봇 기록: 없음\n"
                        warning_msg += f"미체결 주문: 없음\n"
                        warning_msg += f"→ 외부 매수 또는 데이터 불일치\n"
                        warning_msg += f"→ 수동 확인 후 필요시 포지션 등록"
                        
                        logger.warning(warning_msg)
                        discord_alert.SendMessage(warning_msg)
        
        # 🗑️ 제거할 포지션 정리
        logger.info(f"🗑️ 포지션 정리 시작: {len(positions_to_remove)}개")
        for stock_code in positions_to_remove:
            if stock_code in trading_state['positions']:
                removed_position = trading_state['positions'][stock_code]
                stock_name = removed_position.get('stock_name', stock_code)
                
                # 분할매도 이력이 있었다면 최종 정리 로그
                partial_count = removed_position.get('partial_sell_count', 0)
                if partial_count > 0:
                    partial_history = removed_position.get('partial_sell_history', [])
                    total_partial_profit = sum(h.get('net_profit', 0) for h in partial_history)
                    
                    logger.info(f"📊 {stock_name} 최종 거래 요약:")
                    logger.info(f"   분할매도 횟수: {partial_count}회")
                    logger.info(f"   분할매도 총손익: {total_partial_profit:,.0f}원")
                
                del trading_state['positions'][stock_code]
                logger.info(f"🗑️ 포지션 제거 완료: {stock_name}({stock_code})")
        
        logger.info(f"🏁 모든 포지션 처리 완료")
        return trading_state
        
    except Exception as e:
        logger.error(f"❌ 포지션 관리 전체 오류: {str(e)}")
        logger.exception("❌ 포지션 관리 상세 에러 정보:")
        return trading_state

def execute_buy_opportunities(buy_opportunities, trading_state):
    """매수 기회 실행 - 중복 매수 방지 강화 및 디버깅 로그 개선"""
    try:
        logger.info("🚀 execute_buy_opportunities 함수 시작")
        
        # ===== 🔥 1단계: 강제 상태 재로드 (동기화 보장) =====
        logger.info("💾 최신 상태 파일 강제 재로드 시작...")
        fresh_trading_state = load_trading_state()
        
        # 기존 trading_state와 비교 로그
        old_pending_count = len(trading_state.get('pending_orders', {}))
        new_pending_count = len(fresh_trading_state.get('pending_orders', {}))
        
        logger.info(f"📊 상태 동기화 결과:")
        logger.info(f"   기존 메모리: pending_orders {old_pending_count}개")
        logger.info(f"   파일에서 로드: pending_orders {new_pending_count}개")
        
        if old_pending_count != new_pending_count:
            logger.warning(f"⚠️ 메모리와 파일 상태 불일치 감지!")
            logger.warning(f"   메모리: {list(trading_state.get('pending_orders', {}).keys())}")
            logger.warning(f"   파일: {list(fresh_trading_state.get('pending_orders', {}).keys())}")
        
        # 최신 상태 사용
        trading_state = fresh_trading_state
        
        # ===== 🔥 2단계: pending_orders 상태 상세 출력 =====
        pending_orders = trading_state.get('pending_orders', {})
        logger.info(f"📋 현재 미체결 주문 현황: {len(pending_orders)}개")
        
        for stock_code, order_info in pending_orders.items():
            stock_name = order_info.get('stock_name', stock_code)
            quantity = order_info.get('quantity', 0)
            price = order_info.get('price', 0)
            status = order_info.get('status', 'unknown')
            order_time = order_info.get('order_time', 'unknown')
            
            logger.info(f"   📝 {stock_name}({stock_code}): {quantity}주 @ {price:,}원")
            logger.info(f"       상태: {status}, 주문시간: {order_time}")
        
        if not buy_opportunities:
            logger.info("🔍 매수 기회 없음 - 함수 종료")
            return trading_state
        
        # ===== 3단계: 예산 및 제한 확인 =====
        # 전체 사용 가능 예산 확인
        total_available_budget = get_available_budget(trading_state)
        
        if total_available_budget <= 0:
            logger.info("💰 전체 사용 가능 예산이 없습니다.")
            return trading_state
        
        # 현재 포지션 수 확인
        current_positions = len(trading_state['positions'])
        max_allowed_positions = get_active_target_stock_count()
        
        if current_positions >= max_allowed_positions:
            logger.info(f"📊 최대 보유 종목 수 도달: {current_positions}/{max_allowed_positions}개")
            return trading_state
        
        # 새로 매수 가능한 종목 수
        max_new_positions = max_allowed_positions - current_positions
        logger.info(f"💰 매수 실행 준비 (중복 방지 강화):")
        logger.info(f"  - 전체 사용가능 예산: {total_available_budget:,.0f}원")
        logger.info(f"  - 이미 투자된 금액: {get_total_invested_amount(trading_state):,.0f}원")
        
        # 활성 타겟 종목 수 및 종목별 한도
        active_stock_count = get_active_target_stock_count()
        per_stock_limit = get_per_stock_budget_limit()
        
        logger.info(f"  - 활성 타겟 종목 수: {active_stock_count}개")
        logger.info(f"  - 종목별 예산 한도: {per_stock_limit:,.0f}원")
        logger.info(f"  - 현재/최대 보유종목: {current_positions}/{max_allowed_positions}개")
        
        # ===== 4단계: 실제 보유량 조회 (중복 매수 방지) =====
        actual_holdings = {}
        try:
            my_stocks = KisKR.GetMyStockList()
            if my_stocks:
                for stock in my_stocks:
                    stock_code = stock['StockCode']
                    if stock_code in trading_config.target_stocks:
                        actual_holdings[stock_code] = int(stock.get('StockAmt', 0))
                logger.info(f"📊 실제 보유량 조회 완료: {len(actual_holdings)}개 종목")
        except Exception as e:
            logger.warning(f"⚠️ 실제 보유량 조회 실패: {str(e)}")
        
        # ===== 5단계: 매수 실행 루프 시작 =====
        executed_count = 0
        executed_stocks = []  # 🔥 실행된 종목 추적
        
        for i, opportunity in enumerate(buy_opportunities[:max_new_positions]):
            try:
                stock_code = opportunity['stock_code']
                stock_name = opportunity['stock_name']
                stock_price = opportunity['price']
                target_config = opportunity['target_config']
                daily_score = opportunity['score']
                signal_strength = opportunity.get('signal_strength', 'NORMAL')
                
                logger.info(f"\n" + "="*60)
                logger.info(f"🔍 매수 검토 시작: {stock_name}({stock_code}) [{i+1}/{len(buy_opportunities)}]")
                logger.info(f"   일봉 점수: {daily_score}점 ({signal_strength})")
                logger.info(f"="*60)
                
                # ===== 🔥 6단계: 강화된 중복 매수 방지 - 6단계 검증 =====
                logger.info(f"🛡️ 중복 매수 방지 검증 시작: {stock_name}")
                
                # ✅ 검증 1: 최신 상태 다시 로드 (실시간 동기화)
                logger.info("   1️⃣ 최신 상태 재로드 중...")
                real_time_state = load_trading_state()
                
                # ✅ 검증 2: pending_orders 직접 체크 (가장 중요!)
                logger.info("   2️⃣ pending_orders 직접 체크 중...")
                pending_orders_check = real_time_state.get('pending_orders', {})
                
                if stock_code in pending_orders_check:
                    pending_info = pending_orders_check[stock_code]
                    order_time = pending_info.get('order_time', '')
                    quantity = pending_info.get('quantity', 0)
                    price = pending_info.get('price', 0)
                    status = pending_info.get('status', '')
                    
                    logger.error(f"❌ 중복 매수 차단 (pending_orders): {stock_name}")
                    logger.error(f"   기존 미체결 주문 발견:")
                    logger.error(f"     주문시간: {order_time}")
                    logger.error(f"     수량: {quantity}주")
                    logger.error(f"     가격: {price:,}원")
                    logger.error(f"     상태: {status}")
                    logger.error(f"   → 새로운 매수 주문 완전 차단")
                    
                    # Discord 긴급 알림
                    duplicate_msg = f"🚨 중복 매수 주문 차단!\n"
                    duplicate_msg += f"종목: {stock_name}({stock_code})\n"
                    duplicate_msg += f"기존 미체결: {quantity}주 @ {price:,}원\n"
                    duplicate_msg += f"주문시간: {order_time}\n"
                    duplicate_msg += f"상태: {status}\n"
                    duplicate_msg += f"→ 중복 주문 방지 시스템 작동"
                    
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(duplicate_msg)
                    
                    continue  # 매수 건너뛰기
                
                logger.info(f"   ✅ pending_orders 체크 통과: {stock_name}")
                
                # ✅ 검증 3: positions 체크
                logger.info("   3️⃣ positions 체크 중...")
                if stock_code in real_time_state.get('positions', {}):
                    logger.error(f"❌ 중복 매수 차단 (positions): {stock_name}")
                    logger.error(f"   이미 포지션 보유 중")
                    continue
                
                logger.info(f"   ✅ positions 체크 통과: {stock_name}")
                
                # ✅ 검증 4: 실제 보유량 체크
                logger.info("   4️⃣ 실제 보유량 체크 중...")
                actual_amount = actual_holdings.get(stock_code, 0)
                if actual_amount > 0:
                    logger.error(f"❌ 중복 매수 차단 (실제 보유): {stock_name}")
                    logger.error(f"   실제 계좌 보유량: {actual_amount}주")
                    logger.error(f"   → 봇 기록과 실제 보유량 불일치 감지!")
                    
                    # Discord 알림
                    mismatch_msg = f"⚠️ 보유량 불일치 감지\n"
                    mismatch_msg += f"종목: {stock_name}({stock_code})\n"
                    mismatch_msg += f"봇 기록: 없음, 실제 보유: {actual_amount}주\n"
                    mismatch_msg += f"→ 매수 스킵"
                    
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(mismatch_msg)
                    
                    continue
                
                logger.info(f"   ✅ 실제 보유량 체크 통과: {stock_name}")
                
                # ✅ 검증 5: 라이브러리 체크
                logger.info("   5️⃣ pending_manager 라이브러리 체크 중...")
                if pending_manager.check_pending_orders(stock_code, real_time_state):
                    logger.error(f"❌ 중복 매수 차단 (라이브러리): {stock_name}")
                    logger.error(f"   pending_manager에서 미체결 주문 감지")
                    continue
                
                logger.info(f"   ✅ pending_manager 체크 통과: {stock_name}")
                
                # ✅ 검증 6: 이번 루프 실행 이력 체크
                logger.info("   6️⃣ 이번 루프 실행 이력 체크 중...")
                if stock_code in executed_stocks:
                    logger.error(f"❌ 중복 매수 차단 (루프 중복): {stock_name}")
                    logger.error(f"   이번 루프에서 이미 매수 실행됨")
                    continue
                
                logger.info(f"   ✅ 루프 중복 체크 통과: {stock_name}")
                
                # ===== 🔥 7단계: 모든 검증 통과 =====
                logger.info(f"🎉 모든 중복 방지 검증 통과: {stock_name}")
                logger.info(f"   6단계 검증 모두 클리어 ✅")
                logger.info(f"   매수 주문 진행 가능 상태")
                
                # 최신 상태로 업데이트
                trading_state = real_time_state
                
                # ===== 8단계: 매수 대기 리스트에서 제거 (중복 방지) =====
                if 'buy_candidates' in trading_state and stock_code in trading_state['buy_candidates']:
                    del trading_state['buy_candidates'][stock_code]
                    logger.info(f"   🗑️ 매수 대기 리스트에서 제거: {stock_name}")
                
                # ===== 9단계: 분봉 타이밍 체크 (설정된 경우) =====

                timing_result = "immediate"  # 기본값

                if hasattr(trading_config, 'use_intraday_timing') and trading_config.use_intraday_timing:
                    # should_use_intraday_timing으로 사용 여부 먼저 체크
                    use_timing, wait_hours, reason = should_use_intraday_timing(opportunity, target_config)
                    
                    if use_timing:
                        # analyze_intraday_entry_timing으로 실제 분석
                        timing_analysis = analyze_intraday_entry_timing(stock_code, target_config)
                        timing_result = "immediate" if timing_analysis.get('enter_now', False) else "wait"
                        
                        logger.info(f"   📊 분봉 타이밍 전략: {timing_result} (점수: {daily_score})")
                        logger.info(f"   📊 분석 결과: {timing_analysis.get('reason', '정보 없음')}")
                        
                        if timing_analysis.get('entry_signals'):
                            logger.info(f"   📊 분봉 신호:")
                            for signal in timing_analysis['entry_signals'][:3]:
                                logger.info(f"      - {signal}")
                    else:
                        logger.info(f"   📊 분봉 타이밍 비활성화: {reason}")

                if timing_result == "wait":
                    # 분봉 타이밍 대기 필요
                    logger.info(f"   ⏰ 분봉 타이밍 대기: {stock_name}")
                    
                    # 매수 대기 리스트에 추가
                    if 'buy_candidates' not in trading_state:
                        trading_state['buy_candidates'] = {}
                    
                    trading_state['buy_candidates'][stock_code] = {
                        'opportunity': opportunity,
                        'add_time': datetime.datetime.now().isoformat(),
                        'daily_score': daily_score,
                        'signal_strength': signal_strength,
                        'timing_reason': '분봉 타이밍 대기'
                    }
                    
                    logger.info(f"   📝 매수 대기 리스트에 추가: {stock_name}")
                    continue

                elif timing_result in ["immediate", "강력한 신호로 즉시 매수"]:
                    # 즉시 매수 진행
                    if timing_result == "강력한 신호로 즉시 매수":
                        logger.info(f"   🚀 일봉 신호 강도로 즉시 매수 진행")
                    else:
                        logger.info(f"   ✅ 분봉 타이밍 조건 충족 - 즉시 매수")
                
                # ===== 10단계: 현재가 재조회 =====
                logger.info(f"💰 즉시매수 전 현재가 재조회: {stock_name}")
                old_price = stock_price
                try:
                    current_price = KisKR.GetCurrentPrice(stock_code)
                    if current_price and current_price > 0:
                        actual_price = current_price
                        price_diff = actual_price - old_price
                        logger.info(f"   스캔시 가격: {old_price:,}원")
                        logger.info(f"   현재 가격: {actual_price:,}원")
                        logger.info(f"   가격 변화: {price_diff:+,}원")
                        
                        # 가격 변화가 클 경우 추가 검증
                        price_change_rate = abs(price_diff) / old_price
                        if price_change_rate > 0.02:  # 2% 이상 변화
                            logger.warning(f"⚠️ 가격 변화 {price_change_rate*100:.1f}% 감지")
                    else:
                        actual_price = old_price
                        logger.warning(f"⚠️ 현재가 조회 실패, 스캔시 가격 사용: {actual_price:,}원")
                except Exception as price_error:
                    actual_price = old_price
                    logger.error(f"❌ 현재가 조회 중 오류: {str(price_error)}")
                
                # ===== 11단계: 포지션 크기 계산 =====
                logger.info(f"💰 {stock_name}({stock_code}) 포지션 크기 계산 시작")
                logger.info(f"   현재가: {actual_price:,}원")
                
                quantity = calculate_position_size(target_config, stock_code, actual_price, trading_state)
                
                if quantity < 1:
                    logger.info(f"   ❌ 매수 수량 부족 (계산된 수량: {quantity})")
                    continue
                
                # ===== 12단계: 최종 투자금액 계산 및 로그 =====
                estimated_investment = actual_price * quantity
                estimated_fee = calculate_trading_fee(actual_price, quantity, True)
                total_cost = estimated_investment + estimated_fee
                
                logger.info(f"   💰 매수 계획:")
                logger.info(f"      수량: {quantity}주")
                logger.info(f"      가격: {actual_price:,}원")
                logger.info(f"      투자금액: {estimated_investment:,}원")
                logger.info(f"      예상 수수료: {estimated_fee:,.0f}원")
                logger.info(f"      총 소요: {total_cost:,.0f}원")
                
                # ===== 🔥 13단계: 매수 주문 실행 =====
                logger.info(f"   🔵 매수 주문 실행: {stock_name}({stock_code})")
                executed_price, executed_amount = execute_buy_order(
                    stock_code, target_config, quantity, actual_price
                )
                
                if executed_price and executed_amount:
                    # ===== 14단계: 매수 성공 처리 =====
                    executed_stocks.append(stock_code)  # 실행된 종목 추가
                    executed_count += 1
                    
                    # 매수 수수료 계산
                    buy_fee = calculate_trading_fee(executed_price, executed_amount, True)
                    actual_investment = executed_price * executed_amount
                    
                    logger.info(f"   ✅ 매수 체결 성공!")
                    logger.info(f"      체결가: {executed_price:,}원")
                    logger.info(f"      체결수량: {executed_amount}주")
                    logger.info(f"      실제투자: {actual_investment:,}원")
                    logger.info(f"      매수수수료: {buy_fee:.2f}원")
                    
                    # 포지션 생성
                    trading_state['positions'][stock_code] = {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'entry_price': executed_price,
                        'amount': executed_amount,
                        'buy_fee': buy_fee,
                        'entry_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'high_price': executed_price,
                        'trailing_stop': executed_price * (1 - target_config.get('trailing_stop', 0.025)),
                        'target_config': target_config,
                        'buy_analysis': opportunity.get('analysis', {}),
                        'signal_strength': signal_strength,
                        'daily_score': daily_score,
                        'entry_method': 'daily_signal_only',
                        'scan_price': stock_price,
                        'order_price': actual_price,
                        'price_improvement': executed_price - actual_price,
                        'was_in_candidates': False,
                        'trailing_mode': 'LOSS_PROTECTION_ONLY'
                    }
                    
                    # Discord 매수 알림
                    buy_msg = f"📈 매수 체결 완료\n"
                    buy_msg += f"종목: {stock_name}({stock_code})\n"
                    buy_msg += f"체결: {executed_amount}주 @ {executed_price:,}원\n"
                    buy_msg += f"투자금액: {actual_investment:,}원\n"
                    buy_msg += f"신호강도: {signal_strength} ({daily_score}점)\n"
                    buy_msg += f"가격개선: {executed_price - actual_price:+,}원"
                    
                    if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                        discord_alert.SendMessage(buy_msg)
                    
                    # 상태 저장
                    # save_trading_state(trading_state)
                    trading_state = save_and_verify_trading_state(trading_state, "매수 체결 후")
                    
                    logger.info(f"   🎯 매수 성공 카운터: {executed_count}/{max_new_positions}")
                    
                    # 최대 매수 수 도달시 종료
                    if executed_count >= max_new_positions:
                        logger.info(f"📊 최대 신규 매수 수 도달: {executed_count}개")
                        break
                        
                elif executed_price == "DELAYED_EXECUTION":
                    # 지연 체결 처리
                    logger.warning(f"⏰ 지연 체결: {stock_name}")
                    logger.warning(f"   📋 주문 접수됨 - 다음 루프에서 포지션 생성 예정")
                    executed_stocks.append(stock_code)  # 중복 방지를 위해 추가
                    executed_count += 1
                    
                    # 최대 매수 수 도달시 종료
                    if executed_count >= max_new_positions:
                        logger.info(f"📊 최대 신규 매수 수 도달 (지연 포함): {executed_count}개")
                        break
                        
                else:
                    # 매수 실패
                    logger.error(f"   ❌ 매수 주문 실패: {stock_name}({stock_code})")
                    logger.error(f"      주문 결과: {executed_price}, {executed_amount}")
                    
            except Exception as e:
                logger.error(f"❌ 매수 검토 중 에러 ({stock_code}): {str(e)}")
                logger.exception(f"❌ 상세 에러 정보:")
                continue
        
        # ===== 15단계: 실행 결과 요약 =====
        logger.info(f"\n📊 매수 실행 완료 요약:")
        logger.info(f"   처리한 기회: {len(buy_opportunities[:max_new_positions])}개")
        logger.info(f"   실행 성공: {executed_count}개")
        logger.info(f"   실행 종목: {executed_stocks}")
        
        logger.info("🏁 execute_buy_opportunities 함수 완료")
        return trading_state
        
    except Exception as e:
        logger.error(f"❌ execute_buy_opportunities 전체 오류: {str(e)}")
        logger.exception("❌ 상세 에러 정보:")
        return trading_state

def create_config_file(config_path: str = "target_stock_config.json") -> None:
    """기본 설정 파일 생성 (시장 추세 필터 + 분봉 타이밍 + 뉴스 분석 포함한 완전 개선 버전)"""
    try:
        logger.info("후보종목 풀 방식 설정 파일 생성 시작...")
        # 🔥 후보종목 풀 확장 (기존 4개 + 추가 4개)
        sample_codes = [
            "272210", "034020", "010140", "007660",  # 기존: 한화시스템, 두산에너빌리티, 삼성중공업, 이수페타시스
            "017960", "033500", "051600", "000720"   # 추가: 한국카본, 동성화인텍, 한전KPS, 현대건설
        ]

        # 🎯 특성별 파라미터 수정 (시장 추세 필터 반영)
        characteristic_params = {
            "growth": {
                "allocation_ratio": 0.7,
                "profit_target": 0.05,
                "stop_loss": -0.035,           # 손절 기준 강화
                "rsi_oversold": 55,
                "rsi_overbought": 75,
                "min_score": 40,               # 매수 기준 상향
                "trailing_stop": 0.025,        
                "min_holding_hours": 24,       
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.5,
                "stop_loss_delay_hours": 2,
                
                # 🎯 분봉 진입 타이밍 설정
                "min_entry_score": 20,              
                "intraday_rsi_oversold": 35,
                "intraday_rsi_overbought": 70,
                "intraday_volume_threshold": 1.2,
                "use_bb_entry_timing": True,
                "bb_lower_margin": 0.02,
                "ma_support_margin": 0.01,

                # 🆕 분할매도 설정
                "use_partial_sell": True,
                "min_holding_amount": 1,
                "partial_sell_cooldown_hours": 1,
                "partial_sell_min_profit": 0.015,
                "defensive_mode_threshold": 0.015,
                "normal_mode_threshold": 0.02,
                "full_sell_profit_threshold": 0.18,
                "emergency_full_sell_loss": -0.08,
                "min_order_amount": 10000
            },
            "balanced": {
                "allocation_ratio": 0.6,
                "profit_target": 0.05,
                "stop_loss": -0.035,           
                "rsi_oversold": 55,
                "rsi_overbought": 75,
                "min_score": 40,               
                "trailing_stop": 0.025,       
                "min_holding_hours": 24,      
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.4,
                "stop_loss_delay_hours": 2,
                "min_entry_score": 25,              
                "intraday_rsi_oversold": 40,
                "intraday_rsi_overbought": 65,
                "intraday_volume_threshold": 1.15,
                "use_bb_entry_timing": True,
                "bb_lower_margin": 0.025,
                "ma_support_margin": 0.015,
                "use_partial_sell": True,
                "min_holding_amount": 1,
                "partial_sell_cooldown_hours": 1,
                "partial_sell_min_profit": 0.015,
                "defensive_mode_threshold": 0.015,
                "normal_mode_threshold": 0.02,
                "full_sell_profit_threshold": 0.15,
                "emergency_full_sell_loss": -0.07,
                "min_order_amount": 10000
            },
            "value": {
                "allocation_ratio": 0.5,
                "profit_target": 0.05,
                "stop_loss": -0.035,           
                "rsi_oversold": 60,
                "rsi_overbought": 70,
                "min_score": 45,               # value는 더 보수적
                "trailing_stop": 0.025,        
                "min_holding_hours": 24,      
                "use_adaptive_stop": True,
                "volatility_stop_multiplier": 1.3,
                "stop_loss_delay_hours": 1,
                "min_entry_score": 30,              
                "intraday_rsi_oversold": 45,
                "intraday_rsi_overbought": 60,
                "intraday_volume_threshold": 1.1,
                "use_bb_entry_timing": True,
                "bb_lower_margin": 0.03,
                "ma_support_margin": 0.02,
                "use_partial_sell": True,
                "min_holding_amount": 1,
                "partial_sell_cooldown_hours": 2,            
                "partial_sell_min_profit": 0.02,             
                "defensive_mode_threshold": 0.02,
                "normal_mode_threshold": 0.025,
                "full_sell_profit_threshold": 0.12,         
                "emergency_full_sell_loss": -0.06,
                "min_order_amount": 10000
            }
        }

        # 🔥 후보종목 정보 수집 (실제 종목명 및 섹터 조회)
        candidate_stocks = {}
        stock_configs = [
            {"code": "272210", "name": "한화시스템", "sector": "우주항공과국방", "enabled": True, "type": "growth"},
            {"code": "034020", "name": "두산에너빌리티", "sector": "기계", "enabled": False, "type": "growth"},  # 비활성
            {"code": "010140", "name": "삼성중공업", "sector": "조선", "enabled": True, "type": "growth"},
            {"code": "007660", "name": "이수페타시스", "sector": "화학", "enabled": True, "type": "growth"},
            {"code": "017960", "name": "한국카본", "sector": "화학", "enabled": True, "type": "balanced"},
            {"code": "033500", "name": "동성화인텍", "sector": "화학", "enabled": False, "type": "growth"},  # 비활성
            {"code": "051600", "name": "한전KPS", "sector": "건설", "enabled": True, "type": "balanced"},
            {"code": "000720", "name": "현대건설", "sector": "건설", "enabled": True, "type": "balanced"}
        ]

        for stock_config in stock_configs:
            stock_code = stock_config["code"]
            char_type = stock_config["type"]
            
            # 특성별 파라미터 적용
            params = characteristic_params[char_type].copy()
            params.update({
                "name": stock_config["name"],
                "sector": stock_config["sector"],
                "enabled": stock_config["enabled"],
                "characteristic_type": char_type,
                "is_candidate": stock_config["enabled"]  # enabled와 동일하게 설정
            })
            
            candidate_stocks[stock_code] = params
            logger.info(f"후보종목 설정: {stock_code}({stock_config['name']}) - {char_type} ({'활성' if stock_config['enabled'] else '비활성'})")
        
        # 전체 설정 구성 (시장 추세 필터 포함)
        config = {
            # 🔥 후보종목을 target_stocks로 설정 (기존 구조 유지)
            "target_stocks": candidate_stocks,
            
            # 🔥 후보종목 풀 방식 설정
            "use_candidate_pool": True,              
            "target_holding_count": 2,               
            "candidate_selection_method": "score",   
            "min_selection_score": 45,              
            "rebalance_interval_hours": 24,          
            "max_candidate_positions": 4,            
            "max_positions": 3,
            
            # 기본 거래 설정
            "trade_budget_ratio": 0.9,
            "min_stock_price": 3000,
            "max_stock_price": 200000,
            "market_open_wait_minutes": 30,
            
            # 🎯 손익 관리 설정 (개선된 버전)
            "stop_loss_ratio": -0.04,
            "take_profit_ratio": 0.05,
            "trailing_stop_ratio": 0.025,
            "max_daily_loss": -0.06,
            "max_daily_profit": 0.08,
            "stop_loss_delay_hours": 2,
            "volatility_stop_multiplier": 1.5,
            "use_adaptive_stop": True,
            "min_holding_hours": 4,
            
            # 트레일링 스탑 고도화 설정
            "min_protection_ratio": 0.03,
            "trailing_activation_profit": 0.02,
            "profit_protection_threshold": 0.04,
            "conservative_threshold": 0.02,
            "breakeven_range": 0.02,
            "max_trailing_loss": 0.1,
            "trailing_safety_margin": 0.005,
            
            # 🎯 기술적 분석 설정
            "rsi_period": 14,
            "rsi_oversold": 35,
            "rsi_overbought": 75,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,
            "default_min_score": 40,
            
            # 적응형 전략 사용 설정
            "use_adaptive_strategy": True,
            "use_trend_filter": True,
            
            # 🔥 분봉 타이밍 전역 설정
            "use_intraday_timing": True,
            "intraday_check_interval": 10,
            "default_check_interval": 30,
            "max_candidate_wait_hours": 2,
            "intraday_data_period": "5m",
            "intraday_data_count": 24,
            "force_buy_after_wait": True,
            
            # 🔥 뉴스 분석 설정
            "use_news_analysis": True,
            "news_check_threshold": 20,
            "always_check_news": False,
            "news_cache_hours": 6,
            "news_weight": {
                "positive_multiplier": 0.15,
                "negative_multiplier": 0.25
            },
            
            # 🔥 예산 설정
            "use_absolute_budget": True,
            "absolute_budget_strategy": "proportional",
            "absolute_budget": 600000,
            "initial_total_asset": 0,
            "budget_loss_tolerance": 0.2,
            
            # 🔥 NEW: 시장 추세 필터 설정
            "use_market_trend_filter": True,
            "trend_filter_strict_mode": False,
            "trend_filter_settings": {
                "bearish_market_penalty": -25,          # 하락장 페널티 (중간 강도)
                "bullish_market_bonus": 10,             # 상승장 보너스
                "mixed_market_penalty": -15,            # 혼조장 페널티
                "individual_trend_weight": 0.7,         # 개별 종목 추세 가중치
                "market_trend_weight": 0.3,             # 시장 추세 가중치
                "trend_confirmation_days": 5,           # 추세 확인 일수
                "min_trend_strength": 0.02,             # 최소 추세 강도 (2%)
                "trend_cache_minutes": 30,              # 시장 추세 캐시 시간
                "bearish_strict_block": False,          # 하락장 완전 차단 여부
                "emergency_exceptions": {
                    "extreme_oversold_rsi": 15,         # 극도 과매도 예외 기준
                    "strong_news_threshold": 80,        # 강한 호재 뉴스 예외 기준
                    "bb_breakthrough_margin": -0.05,    # 볼밴 하단 돌파 예외 기준
                    "volume_surge_threshold": 2.0       # 거래량 급증 예외 기준
                }
            },
            
            # 🔥 NEW: 성과 추적 설정
            "trend_performance_tracking": {
                "track_by_market_condition": True,      # 시장 상황별 성과 추적
                "save_trend_decisions": True,           # 추세 결정 기록 저장
                "performance_review_days": 30           # 성과 리뷰 기간
            },
            
            # 🎯 분봉 타이밍 관련 알림 설정
            "alert_intraday_wait": True,
            "alert_intraday_entry": True,
            "alert_candidate_summary": True,
            
            # 기타 설정
            "last_sector_update": datetime.datetime.now().strftime('%Y%m%d'),
            "bot_name": "TargetStockBot",
            "use_discord_alert": True,
            "check_interval_minutes": 30
        }

        # 파일 저장
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

        logger.info(f"🎯 완전한 후보종목 풀 설정 파일 생성 완료: {config_path}")
        logger.info(f"주요 설정:")
        logger.info(f"  - 후보종목 풀: {len(candidate_stocks)}개")
        active_count = sum(1 for stock in candidate_stocks.values() if stock.get('enabled', True))
        logger.info(f"  - 활성 후보종목: {active_count}개")
        logger.info(f"  - 목표 보유 종목: {config['target_holding_count']}개")
        logger.info(f"  - 선택 방식: {config['candidate_selection_method']}")
        logger.info(f"  - 선택 최소 점수: {config['min_selection_score']}점")
        logger.info(f"  - 예산: {config['absolute_budget']:,}원")
        logger.info(f"  - 시장 추세 필터: {'ON' if config['use_market_trend_filter'] else 'OFF'}")
        logger.info(f"  - 분봉 타이밍: {'ON' if config['use_intraday_timing'] else 'OFF'}")
        logger.info(f"  - 뉴스 분석: {'ON' if config['use_news_analysis'] else 'OFF'}")
        logger.info(f"  - 하락장 페널티: {config['trend_filter_settings']['bearish_market_penalty']}점")
        logger.info(f"  - 상승장 보너스: {config['trend_filter_settings']['bullish_market_bonus']}점")
        
        # 적응형 전략 파일 초기화
        try:
            from technical_analysis import AdaptiveMarketStrategy
            adaptive_strategy = AdaptiveMarketStrategy("bb_adaptive_strategy.json")
            adaptive_strategy.save_strategy()
            logger.info("적응형 전략 파일 초기화 완료")
        except Exception as e:
            logger.warning(f"적응형 전략 파일 초기화 중 오류 (무시): {str(e)}")
        
    except Exception as e:
        logger.exception(f"설정 파일 생성 중 오류: {str(e)}")
        raise

def end_of_day_candidate_management(trading_state):
    """장마감시 대기 종목 관리 - 하이브리드 방식"""
    try:
        if 'buy_candidates' not in trading_state or not trading_state['buy_candidates']:
            return trading_state
        
        now = datetime.datetime.now()
        kept_candidates = {}
        removed_candidates = []
        
        logger.info("🕐 장마감 대기 종목 관리 시작")
        
        for stock_code, candidate in trading_state['buy_candidates'].items():
            try:
                opportunity = candidate['opportunity']
                stock_name = opportunity['stock_name']
                daily_score = candidate.get('daily_score', 0)
                signal_strength = candidate.get('signal_strength', 'NORMAL')
                
                # 뉴스 영향 확인
                has_positive_news = False
                news_impact = opportunity.get('news_impact')
                if news_impact and news_impact.get('decision') == 'POSITIVE':
                    news_percentage = news_impact.get('percentage', 0)
                    has_positive_news = news_percentage >= 60
                
                # 대기 유지/해제 결정
                keep_candidate = False
                keep_reason = ""
                
                if signal_strength == 'STRONG' and daily_score >= 60:
                    keep_candidate = True
                    keep_reason = f"매우 강한 신호 (STRONG + {daily_score}점)"
                elif signal_strength == 'STRONG' and daily_score >= 50:
                    keep_candidate = True
                    keep_reason = f"강한 신호 (STRONG + {daily_score}점)"
                elif daily_score >= 55 and has_positive_news:
                    keep_candidate = True
                    news_score = news_impact.get('percentage', 0)
                    keep_reason = f"중간신호+호재 ({daily_score}점 + 뉴스{news_score}%)"
                elif daily_score >= 50 and has_positive_news:
                    news_score = news_impact.get('percentage', 0)
                    if news_score >= 70:
                        keep_candidate = True
                        keep_reason = f"보통신호+강한호재 ({daily_score}점 + 뉴스{news_score}%)"
                
                if keep_candidate:
                    # 익일 우선 검토 표시
                    candidate['carry_over'] = True
                    candidate['carry_over_reason'] = keep_reason
                    candidate['carry_over_date'] = now.strftime('%Y-%m-%d')
                    candidate['priority'] = 'HIGH' if signal_strength == 'STRONG' else 'NORMAL'
                    candidate['extended_wait'] = True
                    candidate['max_wait_hours'] = 24.5  # 다음날 09:30까지
                    
                    kept_candidates[stock_code] = candidate
                    logger.info(f"✅ 대기 유지: {stock_name}({stock_code}) - {keep_reason}")
                else:
                    remove_reason = f"신호 약화 ({daily_score}점, {signal_strength}"
                    if not has_positive_news:
                        remove_reason += ", 뉴스 없음"
                    remove_reason += ")"
                    
                    removed_candidates.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'reason': remove_reason
                    })
                    logger.info(f"❌ 대기 해제: {stock_name}({stock_code}) - {remove_reason}")
                
            except Exception as e:
                logger.error(f"대기 종목 처리 중 오류 ({stock_code}): {str(e)}")
        
        # 상태 업데이트
        trading_state['buy_candidates'] = kept_candidates
        
        # 결과 요약
        kept_count = len(kept_candidates)
        removed_count = len(removed_candidates)
        
        logger.info(f"📊 장마감 대기 종목 관리 완료: 유지 {kept_count}개, 해제 {removed_count}개")
        
        # Discord 알림
        if kept_count > 0 or removed_count > 0:
            msg = f"🕐 장마감 대기 종목 관리\n"
            msg += f"========== {now.strftime('%Y-%m-%d %H:%M')} ==========\n"
            
            if kept_count > 0:
                msg += f"✅ 익일 우선 검토 ({kept_count}개):\n"
                for stock_code, candidate in kept_candidates.items():
                    stock_name = candidate['opportunity']['stock_name']
                    reason = candidate['carry_over_reason']
                    msg += f"• {stock_name}: {reason}\n"
            
            if removed_count > 0:
                msg += f"❌ 대기 해제 ({removed_count}개):\n"
                for removed in removed_candidates:
                    msg += f"• {removed['stock_name']}: {removed['reason']}\n"
            
            msg += f"📅 익일 장 시작시 우선 검토 예정"
            
            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                discord_alert.SendMessage(msg)
        
        return trading_state
        
    except Exception as e:
        logger.error(f"장마감 대기 종목 관리 중 전체 오류: {str(e)}")
        return trading_state

def next_day_priority_check(trading_state):
    """익일 장 시작시 우선 검토"""
    try:
        if 'buy_candidates' not in trading_state or not trading_state['buy_candidates']:
            return trading_state
        
        logger.info("🌅 익일 우선 검토 시작")
        
        carry_over_count = 0
        for stock_code, candidate in trading_state['buy_candidates'].items():
            if candidate.get('carry_over', False):
                stock_name = candidate['opportunity']['stock_name']
                priority = candidate.get('priority', 'NORMAL')
                reason = candidate.get('carry_over_reason', '전일 대기')
                
                logger.info(f"🎯 우선 검토: {stock_name}({stock_code}) - {reason} ({priority})")
                carry_over_count += 1
        
        if carry_over_count > 0:
            msg = f"🌅 익일 우선 검토 대상: {carry_over_count}개\n"
            msg += "상세 내용은 로그를 확인하세요."
            
            logger.info(msg)
            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                discord_alert.SendMessage(msg)
        
        return trading_state
        
    except Exception as e:
        logger.error(f"익일 우선 검토 중 오류: {str(e)}")
        return trading_state

def save_and_verify_trading_state(trading_state, operation_name="상태저장"):
    """상태 저장 후 검증하여 동기화 보장"""
    try:
        logger.debug(f"💾 {operation_name}: 저장 시작")
        
        # 1. 저장 전 pending_orders 기록
        before_pending = list(trading_state.get('pending_orders', {}).keys())
        logger.debug(f"   저장 전 pending_orders: {before_pending}")
        
        # 2. 저장 실행
        save_trading_state(trading_state)
        
        # 3. 즉시 다시 로드하여 검증
        reloaded_state = load_trading_state()
        after_pending = list(reloaded_state.get('pending_orders', {}).keys())
        
        logger.debug(f"   저장 후 pending_orders: {after_pending}")
        
        # 4. 저장/로드 일치성 확인
        if before_pending != after_pending:
            logger.error(f"❌ {operation_name}: 저장/로드 불일치!")
            logger.error(f"   저장 전: {before_pending}")
            logger.error(f"   로드 후: {after_pending}")
            
            # Discord 알림
            sync_error_msg = f"🚨 상태 동기화 오류!\n"
            sync_error_msg += f"작업: {operation_name}\n"
            sync_error_msg += f"저장 전: {len(before_pending)}개\n"
            sync_error_msg += f"로드 후: {len(after_pending)}개\n"
            sync_error_msg += f"→ 수동 확인 필요"
            
            if hasattr(trading_config, 'use_discord_alert') and trading_config.config.get('use_discord_alert', True):
                discord_alert.SendMessage(sync_error_msg)
        else:
            logger.debug(f"✅ {operation_name}: 저장/로드 일치 확인")
        
        return reloaded_state
        
    except Exception as e:
        logger.error(f"❌ {operation_name} 중 오류: {str(e)}")
        return trading_state

def test_market_data_connection():
    """시장 데이터 연결 테스트 - 디버깅용"""
    try:
        logger.info("🔧 시장 데이터 연결 테스트 시작...")
        
        # 1. 코스피 지수 테스트
        logger.info("1️⃣ 코스피 지수 연결 테스트...")
        try:
            kospi_test = KisKR.GetOhlcvNew("KS11", 'D', 5, adj_ok=1)
            if kospi_test is not None and len(kospi_test) > 0:
                logger.info("✅ 코스피 연결 성공")
                logger.info(f"   데이터 형태: {type(kospi_test)}")
                logger.info(f"   데이터 크기: {kospi_test.shape}")
                logger.info(f"   컬럼: {list(kospi_test.columns)}")
                logger.info(f"   최신 데이터: {kospi_test.iloc[-1]['close']:.2f}")
            else:
                logger.error("❌ 코스피 연결 실패")
        except Exception as e:
            logger.error(f"❌ 코스피 테스트 오류: {str(e)}")
        
        # 2. 코스닥 지수 테스트
        logger.info("2️⃣ 코스닥 지수 연결 테스트...")
        try:
            kosdaq_test = KisKR.GetOhlcvNew("KQ11", 'D', 5, adj_ok=1)
            if kosdaq_test is not None and len(kosdaq_test) > 0:
                logger.info("✅ 코스닥 연결 성공")
                logger.info(f"   데이터 형태: {type(kosdaq_test)}")
                logger.info(f"   데이터 크기: {kosdaq_test.shape}")
                logger.info(f"   컬럼: {list(kosdaq_test.columns)}")
                logger.info(f"   최신 데이터: {kosdaq_test.iloc[-1]['close']:.2f}")
            else:
                logger.error("❌ 코스닥 연결 실패")
        except Exception as e:
            logger.error(f"❌ 코스닥 테스트 오류: {str(e)}")
        
        # 3. 대체 방법 테스트
        logger.info("3️⃣ 대체 API 테스트...")
        try:
            # 삼성전자로 API 연결 테스트
            samsung_test = KisKR.GetOhlcvNew("005930", 'D', 5, adj_ok=1)
            if samsung_test is not None and len(samsung_test) > 0:
                logger.info("✅ 대체 API 연결 성공 (삼성전자)")
                logger.info("   → API 자체는 정상 작동 중")
            else:
                logger.error("❌ 대체 API도 실패")
                logger.error("   → API 전체 문제 가능성")
        except Exception as e:
            logger.error(f"❌ 대체 API 테스트 오류: {str(e)}")
        
        logger.info("🔧 시장 데이터 연결 테스트 완료")
        
    except Exception as e:
        logger.error(f"❌ 데이터 연결 테스트 중 오류: {str(e)}")

def main():
    """메인 함수 (Config 적용)"""
    
    # 1. 설정 초기화 (가장 먼저!)
    config_path = "target_stock_config.json"
    
    # 설정 파일이 없으면 생성
    if not os.path.exists(config_path):
        create_config_file(config_path)
        logger.info(f"기본 설정 파일 생성 완료: {config_path}")
    
    # Config 클래스 초기화
    config = initialize_config(config_path)

    # 🆕 미체결 주문 관리자 초기화
    initialize_pending_manager()
    
    # 섹터 정보 업데이트 (날짜가 바뀌었거나 처음 실행시)
    today = datetime.datetime.now().strftime('%Y%m%d')
    
    if config.last_sector_update != today:
        logger.info("섹터 정보 자동 업데이트 시작...")
        updated_stocks = _update_stock_info(config.target_stocks)
        config.update_target_stocks(updated_stocks)
        config.update_last_sector_update(today)

    msg = "🎯 타겟 종목 매매봇 시작!"
    logger.info(msg)
    discord_alert.SendMessage(msg)
    
    # 타겟 종목 현황 출력 (Config 사용)
    # enabled_count = sum(1 for stock_config in config.target_stocks.values() if stock_config.get('enabled', True))
    # logger.info(f"활성화된 타겟 종목: {enabled_count}개")
    enabled_count = get_active_target_stock_count()
    logger.info(f"활성화된 타겟 종목: {enabled_count}개 (자동 계산)")

    for stock_code, stock_config in config.target_stocks.items():
        if stock_config.get('enabled', True):
            logger.info(f"  - {stock_config.get('name', stock_code)}({stock_code}): "
                       f"목표수익률 {stock_config.get('profit_target', config.take_profit_ratio)*100:.1f}%, "
                       f"손절률 {stock_config.get('stop_loss', config.stop_loss_ratio)*100:.1f}%, "
                       f"배분비율 {stock_config.get('allocation_ratio', 0)*100:.1f}%")
    
    # 초기 상태
    daily_report_sent = False
    market_open_notified = False
    last_status_report = datetime.datetime.now()
    last_pending_check = datetime.datetime.now()  # 🆕 미체결 주문 체크 시간

    # 🆕 하이브리드 관리를 위한 변수들
    end_of_day_managed = False
    next_day_priority_checked = False

    while True:
        try:
            now = datetime.datetime.now()
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

                # 🔥 당일 투자 기록 정리 (여기에 추가)
                if 'daily_investments' in trading_state:
                    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
                    trading_state['daily_investments'] = {
                        date: data for date, data in trading_state['daily_investments'].items() 
                        if date > cutoff_date
                    }
                    logger.info(f"📅 당일 투자 기록 정리: 3일 이전 데이터 삭제")

                daily_report_sent = False
                market_open_notified = False

                # 🆕 날짜 변경시 플래그 리셋 (여기에 추가)
                end_of_day_managed = False
                next_day_priority_checked = False
                save_trading_state(trading_state)

            # 🆕 ===== 여기부터 새로운 코드 삽입 시작 =====
            
            # 장마감 대기 종목 관리 (15:25~15:35 사이 한 번)
            if (now.hour == 15 and 25 <= now.minute <= 35 and not end_of_day_managed):
                logger.info("🕐 장마감 대기 종목 관리 실행")
                trading_state = end_of_day_candidate_management(trading_state)
                save_trading_state(trading_state)
                end_of_day_managed = True
            
            # 익일 우선 검토 (09:00~09:05 사이 한 번)
            if (now.hour == 9 and now.minute <= 5 and is_trading_time and not next_day_priority_checked):
                logger.info("🌅 익일 우선 검토 실행")
                trading_state = next_day_priority_check(trading_state)
                next_day_priority_checked = True
                end_of_day_managed = False  # 다음 장마감을 위해 리셋
            # 🆕 ===== 새로운 코드 삽입 끝 =====

            # 장 시작 알림 (Config 사용)
            if is_market_open and not market_open_notified:
                msg = f"🔔 장 시작!\n"
                msg += get_budget_info_message()
                msg += f"\n타겟 종목: {enabled_count}개"

                # 🆕 미체결 주문 현황 추가 (라이브러리 사용)
                pending_status = pending_manager.get_pending_orders_status(trading_state)
                if pending_status['count'] > 0:
                    msg += f"\n미체결 주문: {pending_status['count']}개 (자동 관리 중)"
 
                logger.info(msg)
                discord_alert.SendMessage(msg)
                market_open_notified = True

            # 거래 시간이 아니면 대기
            if not is_trading_time:

                # 장 마감 후 일일 보고서
                if now.hour >= 15 and now.minute >= 30 and not daily_report_sent:
                    send_daily_report(trading_state)
                    
                    # 🆕 미체결 주문 정리 보고서 (라이브러리 사용)
                    pending_status = pending_manager.get_pending_orders_status(trading_state)
                    if pending_status['count'] > 0:
                        final_pending_msg = f"📋 장 마감 미체결 주문 현황: {pending_status['count']}개\n"
                        for order in pending_status['orders']:
                            final_pending_msg += f"• {order['stock_name']}: {order['quantity']}주 @ {order['price']:,}원\n"
                        final_pending_msg += "→ 내일 장 시작 전 자동 정리됩니다."
                        
                        logger.info(final_pending_msg)
                        discord_alert.SendMessage(final_pending_msg)
                    
                    daily_report_sent = True
               
                logger.info("장 시간 외입니다.")
                time.sleep(300)  # 5분 대기
                continue

            # 🆕 미체결 주문 지연 체결 확인 및 자동 관리 (5분마다)
            if (now - last_pending_check).total_seconds() >= 180:
                logger.info("🔍 지연 체결 확인 및 미체결 주문 자동 관리 실행")
                
                # 🎯 1단계: 지연 체결 확인 먼저 실행
                trading_state = check_delayed_executions(trading_state)
                
                # 🎯 2단계: 여전히 미체결인 주문들 관리
                trading_state = pending_manager.auto_cancel_pending_orders(trading_state, max_pending_minutes=60)
                
                save_trading_state(trading_state)
                last_pending_check = now

            # 🆕 지연 체결 확인 (기존 함수 활용)
            trading_state = check_delayed_executions(trading_state)

            # 포지션 관리 (매도 신호 체크)
            logger.info("=== 타겟 종목 포지션 관리 ===")
            trading_state = process_positions(trading_state)
            save_trading_state(trading_state)

            # 🎯 분봉 타이밍 사용시에만 매수 대기 후보 관리
            if hasattr(trading_config, 'use_intraday_timing') and trading_config.use_intraday_timing:
                trading_state = process_buy_candidates(trading_state)
                save_trading_state(trading_state)
            
            # 새로운 매수 기회 스캔 (15시 이전까지만)
            if now.hour < 15:
                logger.info("=== 타겟 종목 매수 기회 스캔 ===")
                buy_opportunities = scan_target_stocks(trading_state)

                if buy_opportunities:
                    # 매수 실행
                    trading_state = execute_buy_opportunities(buy_opportunities, trading_state)
                    save_trading_state(trading_state)
            
            # 1시간마다 타겟 종목 현황 보고
            if (now - last_status_report).seconds >= 3600:
                send_target_stock_status()
                
                # 🆕 미체결 주문 현황 보고 (라이브러리 사용)
                pending_status = pending_manager.get_pending_orders_status(trading_state)
                if pending_status['count'] > 0:
                    pending_msg = f"\n📋 미체결 주문 현황: {pending_status['count']}개\n"
                    for order in pending_status['orders']:
                        pending_msg += f"• {order['stock_name']}: {order['quantity']}주 ({order['elapsed_minutes']:.0f}분 경과)\n"
                    
                    logger.info(pending_msg)
                    discord_alert.SendMessage(pending_msg)
                
                last_status_report = now

            # 30초 대기
            # time.sleep(30)

            # 🎯 분봉 타이밍 사용시 체크 주기 조정
            if hasattr(trading_config, 'use_intraday_timing') and trading_config.use_intraday_timing:
                check_interval = getattr(trading_config, 'intraday_check_interval', 10)
            else:
                check_interval = 30  # 기존 주기
                
            time.sleep(check_interval)

        except Exception as e:
            error_msg = f"⚠️ 메인 루프 에러: {str(e)}"
            logger.error(error_msg)
            discord_alert.SendMessage(error_msg)
            time.sleep(60)  # 에러 발생 시 1분 대기

if __name__ == "__main__":
    # 실제 거래 모드로 설정
    Common.SetChangeMode()
    
    main()