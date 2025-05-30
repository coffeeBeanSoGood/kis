#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
개선된 스마트 매직 스플릿 봇 (SmartMagicSplitBot) - 절대 예산 기반 동적 조정 버전
1. 절대 예산 기반 투자 (다른 매매봇과 독립적 운영)
2. 성과 기반 동적 예산 조정 (70%~140% 범위)
3. 안전장치 강화 (현금 잔고 기반 검증)
4. 설정 파일 분리 (JSON 기반 관리)
5. 기존 스플릿 로직 유지 (5차수 분할 매매)
"""

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
try:
    KisKR.set_logger(logger)
    Common.set_logger(logger)
except:
    logger.warning("API 헬퍼 모듈에 로거를 전달할 수 없습니다.")

################################### 설정 파일 생성 함수 ##################################

def create_smart_split_config(config_path: str = "smart_split_config.json") -> None:
    """스마트 스플릿 기본 설정 파일 생성"""
    try:
        logger.info("🔧 스마트 스플릿 설정 파일 생성 시작...")
        
        # 샘플 종목 코드들 (거래량과 유동성이 확보된 종목들)
        sample_stocks = ["449450", "042660"]  # PLUS K방산, 한화오션
        
        # 종목별 정보 수집
        target_stocks = {}
        
        for i, stock_code in enumerate(sample_stocks):
            try:
                logger.info(f"종목 정보 수집 중: {stock_code}")
                
                # 종목명 조회
                stock_status = KisKR.GetCurrentStatus(stock_code)
                if stock_status and isinstance(stock_status, dict):
                    stock_name = stock_status.get("StockName", f"종목{stock_code}")
                else:
                    stock_name = f"종목{stock_code}"
                
                # 현재가 조회 (유효성 검증)
                current_price = KisKR.GetCurrentPrice(stock_code)
                if not current_price or current_price <= 0:
                    logger.warning(f"종목 {stock_code} 현재가 조회 실패")
                    continue
                
                # 종목별 비중 설정 (K방산 40%, 한화오션 60%)
                if stock_code == "449450":  # PLUS K방산
                    weight = 0.5
                elif stock_code == "042660":  # 한화오션
                    weight = 0.5
                else:
                    weight = 0.5  # 기타 종목
                
                # 종목 설정 생성
                stock_config = {
                    "name": stock_name,
                    "weight": weight,
                    "min_holding": 0,
                    "period": 60,
                    "recent_period": 30,
                    "recent_weight": 0.6,
                    "stock_type": "growth",
                    "hold_profit_target": 10,    # 10% 목표 수익률
                    "base_profit_target": 10,
                    "partial_sell_ratio": 0.3    # 30% 부분 매도
                }
                
                target_stocks[stock_code] = stock_config
                logger.info(f"종목 설정 완료: {stock_code}({stock_name}) - 비중 {weight*100:.1f}%")
                
                time.sleep(0.5)  # API 호출 간격
                
            except Exception as e:
                logger.warning(f"종목 {stock_code} 정보 수집 중 오류: {str(e)}")
                # 오류 발생시 기본값으로 설정
                target_stocks[stock_code] = {
                    "name": f"종목{stock_code}",
                    "weight": 0.5,
                    "min_holding": 0,
                    "period": 60,
                    "recent_period": 30,
                    "recent_weight": 0.6,
                    "stock_type": "growth",
                    "hold_profit_target": 10,
                    "base_profit_target": 10,
                    "partial_sell_ratio": 0.3
                }
        
        # 전체 설정 구성
        config = {
            # 🔥 절대 예산 설정
            "use_absolute_budget": True,
            "absolute_budget": 1000000,  # 🎯 기본 100만원
            "absolute_budget_strategy": "proportional",  # 성과 기반 동적 조정
            "initial_total_asset": 0,  # 봇 시작시 자동 설정
            
            # 🔥 동적 조정 설정
            "performance_multiplier_range": [0.7, 1.4],  # 70%~140% 범위
            "budget_loss_tolerance": 0.2,  # adaptive 모드용 20% 손실 허용
            "safety_cash_ratio": 0.8,  # 현금 잔고의 80%만 사용
            
            # 봇 기본 설정
            "bot_name": "SmartMagicSplitBot",
            "div_num": 5.0,  # 5차수 분할
            
            # 수수료 및 세금 설정
            "commission_rate": 0.00015,  # 수수료 0.015%
            "tax_rate": 0.0023,  # 매도 시 거래세 0.23%
            "special_tax_rate": 0.0015,  # 농어촌특별세 0.15%
            
            # 기술적 지표 설정
            "rsi_period": 14,
            "atr_period": 14,
            "pullback_rate": 5,  # 고점 대비 5% 조정 요구
            "rsi_lower_bound": 30,
            "rsi_upper_bound": 78,
            "ma_short": 5,
            "ma_mid": 20,
            "ma_long": 60,
            
            # 관심 종목 설정
            "target_stocks": target_stocks,
            
            # 성과 추적 초기화
            "performance_tracking": {
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "best_performance": 0.0,
                "worst_performance": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "total_realized_pnl": 0.0
            },
            
            # 기타 설정
            "use_discord_alert": True,
            "last_config_update": datetime.now().isoformat(),
            
            # 🔥 사용자 안내 메시지
            "_readme": {
                "설명": "스마트 매직 스플릿 봇 설정 파일",
                "절대예산": "absolute_budget을 원하는 금액으로 수정하세요 (예: 1000000 = 100만원)",
                "예산전략": "proportional=성과기반, strict=고정, adaptive=손실허용",
                "종목비중": "target_stocks의 weight 값을 조정하여 종목별 비중 설정",
                "알림설정": "use_discord_alert를 false로 설정하면 Discord 알림 비활성화",
                "주의사항": "_readme 섹션은 삭제해도 됩니다"
            }
        }
        
        # 파일 저장
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"✅ 스마트 스플릿 설정 파일 생성 완료: {config_path}")
        logger.info(f"🎯 주요 설정:")
        logger.info(f"  - 절대 예산: {config['absolute_budget']:,}원")
        logger.info(f"  - 예산 전략: {config['absolute_budget_strategy']}")
        logger.info(f"  - 분할 차수: {config['div_num']:.0f}차수")
        logger.info(f"  - 타겟 종목: {len(target_stocks)}개")
        
        for stock_code, stock_config in target_stocks.items():
            logger.info(f"    · {stock_config['name']}({stock_code}): {stock_config['weight']*100:.1f}% 비중")
        
        # Discord 알림 전송
        try:
            setup_msg = f"🔧 스마트 스플릿 설정 파일 생성 완료!\n"
            setup_msg += f"📁 파일: {config_path}\n"
            setup_msg += f"💰 초기 예산: {config['absolute_budget']:,}원\n"
            setup_msg += f"📊 예산 전략: {config['absolute_budget_strategy']}\n"
            setup_msg += f"🎯 분할 차수: {config['div_num']:.0f}차수\n\n"
            setup_msg += f"종목 설정:\n"
            for stock_code, stock_config in target_stocks.items():
                allocated = config['absolute_budget'] * stock_config['weight']
                setup_msg += f"• {stock_config['name']}: {stock_config['weight']*100:.1f}% ({allocated:,.0f}원)\n"
            setup_msg += f"\n⚙️ 설정 변경은 {config_path} 파일을 수정하세요."
            
            if config.get("use_discord_alert", True):
                discord_alert.SendMessage(setup_msg)
                
        except Exception as alert_e:
            logger.warning(f"Discord 알림 전송 중 오류: {str(alert_e)}")
        
    except Exception as e:
        logger.exception(f"설정 파일 생성 중 오류: {str(e)}")
        raise

def check_and_create_config():
    """설정 파일 존재 여부 확인 및 생성"""
    config_path = "smart_split_config.json"
    
    if not os.path.exists(config_path):
        logger.info(f"📋 설정 파일이 없습니다. 기본 설정 파일을 생성합니다: {config_path}")
        create_smart_split_config(config_path)
        
        # 생성 후 사용자 확인 메시지
        logger.info("=" * 60)
        logger.info("🎯 설정 파일이 생성되었습니다!")
        logger.info("📝 필요시 다음 항목들을 수정하세요:")
        logger.info("  1. absolute_budget: 투자할 총 금액 (기본: 50만원)")
        logger.info("  2. target_stocks의 weight: 종목별 비중")
        logger.info("  3. absolute_budget_strategy: 예산 전략")
        logger.info("     - proportional: 성과 기반 동적 조정 (추천)")
        logger.info("     - strict: 고정 예산")
        logger.info("     - adaptive: 손실 허용도 기반")
        logger.info("💡 설정 변경 후 봇을 재시작하면 자동 적용됩니다.")
        logger.info("=" * 60)
        
        return True
    else:
        logger.info(f"✅ 설정 파일 존재: {config_path}")
        return False

################################### 설정 클래스 ##################################

class SmartSplitConfig:
    """스마트 스플릿 설정 관리 클래스"""
    
    def __init__(self, config_path: str = "smart_split_config.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """설정 파일 로드"""
        default_config = {
            # 🔥 절대 예산 설정
            "use_absolute_budget": True,
            "absolute_budget": 5000000,  # 초기 500만원
            "absolute_budget_strategy": "proportional",  # strict, adaptive, proportional
            "initial_total_asset": 0,  # 봇 시작시 총 자산 (자동 설정)
            
            # 🔥 동적 조정 설정
            "performance_multiplier_range": [0.7, 1.4],  # 70%~140% 범위
            "budget_loss_tolerance": 0.2,  # adaptive 모드용
            "safety_cash_ratio": 0.9,  # 현금 잔고의 90%만 사용
            
            # 봇 기본 설정
            "bot_name": "SmartMagicSplitBot",
            "div_num": 5.0,  # 분할 수
            
            # 수수료 및 세금 설정
            "commission_rate": 0.00015,  # 수수료 0.015%
            "tax_rate": 0.0023,  # 매도 시 거래세 0.23%
            "special_tax_rate": 0.0015,  # 농어촌특별세 0.15%
            
            # 기술적 지표 설정
            "rsi_period": 14,
            "atr_period": 14,
            "pullback_rate": 5,  # 고점 대비 조정 요구 (5%)
            "rsi_lower_bound": 30,
            "rsi_upper_bound": 78,
            "ma_short": 5,
            "ma_mid": 20,
            "ma_long": 60,
            
            # 관심 종목 설정
            "target_stocks": {
                "449450": {
                    "name": "PLUS K방산",
                    "weight": 0.4,  # 40% 비중
                    "min_holding": 0,
                    "period": 60,
                    "recent_period": 30,
                    "recent_weight": 0.6,
                    "stock_type": "growth",
                    "hold_profit_target": 10,    # 목표 수익률 10%
                    "base_profit_target": 10,
                    "partial_sell_ratio": 0.3   # 부분 매도 비율 30%
                },
                "042660": {
                    "name": "한화오션",
                    "weight": 0.6,  # 60% 비중
                    "min_holding": 0,
                    "period": 60,
                    "recent_period": 30,
                    "recent_weight": 0.7,
                    "stock_type": "growth",
                    "hold_profit_target": 10,
                    "base_profit_target": 10
                }
            },
            
            # 성과 추적
            "performance_tracking": {
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "best_performance": 0.0,
                "worst_performance": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "total_realized_pnl": 0.0
            },
            
            # 기타 설정
            "use_discord_alert": True,
            "last_config_update": datetime.now().isoformat()
        }
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 기본 설정과 병합
            self.config = self._merge_config(default_config, loaded_config)
            logger.info(f"설정 파일 로드 완료: {self.config_path}")
            
        except FileNotFoundError:
            self.config = default_config
            self.save_config()
            logger.info(f"기본 설정 파일 생성: {self.config_path}")
            
        except Exception as e:
            logger.error(f"설정 파일 로드 중 오류: {str(e)}")
            self.config = default_config
    
    def _merge_config(self, default, loaded):
        """설정 병합 (기본값 + 로드된 값)"""
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            self.config["last_config_update"] = datetime.now().isoformat()
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"설정 파일 저장 완료: {self.config_path}")
        except Exception as e:
            logger.error(f"설정 파일 저장 중 오류: {str(e)}")
    
    # 속성 접근자들
    @property
    def use_absolute_budget(self):
        return self.config.get("use_absolute_budget", True)
    
    @property
    def absolute_budget(self):
        return self.config.get("absolute_budget", 5000000)
    
    @property
    def absolute_budget_strategy(self):
        return self.config.get("absolute_budget_strategy", "proportional")
    
    @property
    def initial_total_asset(self):
        return self.config.get("initial_total_asset", 0)
    
    @property
    def target_stocks(self):
        return self.config.get("target_stocks", {})
    
    @property
    def bot_name(self):
        return self.config.get("bot_name", "SmartMagicSplitBot")
    
    @property
    def div_num(self):
        return self.config.get("div_num", 5.0)
    
    def update_initial_asset(self, asset_value):
        """초기 자산 업데이트"""
        self.config["initial_total_asset"] = asset_value
        self.save_config()
    
    def update_performance(self, performance_rate):
        """성과 추적 업데이트"""
        tracking = self.config.get("performance_tracking", {})
        tracking["best_performance"] = max(tracking.get("best_performance", 0), performance_rate)
        tracking["worst_performance"] = min(tracking.get("worst_performance", 0), performance_rate)
        self.config["performance_tracking"] = tracking
        self.save_config()

# 전역 설정 인스턴스
config = SmartSplitConfig()

# 봇 이름 설정
BOT_NAME = Common.GetNowDist() + "_" + config.bot_name

################################### 메인 클래스 ##################################

class SmartMagicSplit:
    def __init__(self):
        self.split_data_list = self.load_split_data()
        self.total_money = 0
        self.update_budget()
        self._upgrade_json_structure_if_needed()

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

    def calculate_dynamic_budget(self):
        """🔥 성과 기반 동적 예산 계산"""
        try:
            balance = KisKR.GetBalance()
            if not balance:
                logger.error("계좌 정보 조회 실패")
                return config.absolute_budget
                
            current_total = float(balance.get('TotalMoney', 0))
            remain_money = float(balance.get('RemainMoney', 0))
            
            # 초기 자산 설정 (첫 실행시)
            if config.initial_total_asset == 0:
                config.update_initial_asset(current_total)
                logger.info(f"🎯 초기 총 자산 설정: {current_total:,.0f}원")
            
            # 성과율 계산
            initial_asset = config.initial_total_asset
            performance_rate = (current_total - initial_asset) / initial_asset if initial_asset > 0 else 0
            
            # 성과 추적 업데이트
            config.update_performance(performance_rate)
            
            # 🔥 전략별 예산 계산
            strategy = config.absolute_budget_strategy
            base_budget = config.absolute_budget
            
            if strategy == "proportional":
                # 성과 기반 동적 조정
                if performance_rate > 0.3:          # +30% 이상: 140% 예산
                    multiplier = 1.4
                elif performance_rate > 0.2:        # +20%: 130% 예산
                    multiplier = 1.3
                elif performance_rate > 0.15:       # +15%: 125% 예산
                    multiplier = 1.25
                elif performance_rate > 0.1:        # +10%: 120% 예산
                    multiplier = 1.2
                elif performance_rate > 0.05:       # +5%: 110% 예산
                    multiplier = 1.1
                elif performance_rate > -0.05:      # ±5%: 100% 예산
                    multiplier = 1.0
                elif performance_rate > -0.1:       # -10%: 95% 예산
                    multiplier = 0.95
                elif performance_rate > -0.15:      # -15%: 90% 예산
                    multiplier = 0.9
                elif performance_rate > -0.2:       # -20%: 85% 예산
                    multiplier = 0.85
                else:                               # -20% 초과: 70% 예산
                    multiplier = 0.7
                    
                dynamic_budget = base_budget * multiplier
                
            elif strategy == "adaptive":
                # 손실 허용도 기반 조정
                loss_tolerance = config.config.get("budget_loss_tolerance", 0.2)
                min_budget = base_budget * (1 - loss_tolerance)
                
                if current_total >= min_budget:
                    dynamic_budget = base_budget
                else:
                    dynamic_budget = max(current_total * 0.8, min_budget)
                    
            else:  # "strict"
                # 고정 예산
                dynamic_budget = base_budget
            
            # 🔥 안전장치: 현금 잔고 기반 제한
            safety_ratio = config.config.get("safety_cash_ratio", 0.9)
            max_safe_budget = remain_money * safety_ratio
            
            if dynamic_budget > max_safe_budget:
                logger.warning(f"💰 현금 잔고 기반 예산 제한: {dynamic_budget:,.0f}원 → {max_safe_budget:,.0f}원")
                dynamic_budget = max_safe_budget
            
            # 로깅
            logger.info(f"📊 동적 예산 계산 결과:")
            logger.info(f"  전략: {strategy}")
            logger.info(f"  초기 자산: {initial_asset:,.0f}원")
            logger.info(f"  현재 자산: {current_total:,.0f}원")
            logger.info(f"  현금 잔고: {remain_money:,.0f}원")
            logger.info(f"  성과율: {performance_rate*100:+.2f}%")
            if strategy == "proportional":
                logger.info(f"  예산 배수: {multiplier:.2f}x")
            logger.info(f"  최종 예산: {dynamic_budget:,.0f}원")
            
            return dynamic_budget
            
        except Exception as e:
            logger.error(f"동적 예산 계산 중 오류: {str(e)}")
            return config.absolute_budget

    def update_budget(self):
        """예산 업데이트 - 절대 예산 기반"""
        if config.use_absolute_budget:
            self.total_money = self.calculate_dynamic_budget()
            logger.info(f"💰 절대 예산 기반 운영: {self.total_money:,.0f}원")
        else:
            # 기존 방식 (호환성 유지)
            balance = KisKR.GetBalance()
            self.total_money = float(balance.get('TotalMoney', 0)) * 0.08  # 8%
            logger.info(f"💰 비율 기반 운영 (8%): {self.total_money:,.0f}원")

    def load_split_data(self):
        """저장된 매매 데이터 로드"""
        try:
            bot_file_path = f"/var/autobot/kis/KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'r') as json_file:
                return json.load(json_file)
        except Exception:
            return []

    def save_split_data(self):
        """매매 데이터 저장"""
        try:
            bot_file_path = f"/var/autobot/kis/KrStock_{BOT_NAME}.json"
            with open(bot_file_path, 'w') as outfile:
                json.dump(self.split_data_list, outfile)
        except Exception as e:
            logger.error(f"데이터 저장 중 오류 발생: {str(e)}")

    def calculate_trading_fee(self, price, quantity, is_buy=True):
        """거래 수수료 및 세금 계산"""
        commission = price * quantity * config.config.get("commission_rate", 0.00015)
        if not is_buy:  # 매도 시에만 세금 부과
            tax = price * quantity * config.config.get("tax_rate", 0.0023)
            special_tax = price * quantity * config.config.get("special_tax_rate", 0.0015)
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
        """종목의 특성과 시장 환경에 따라 최적의 분석 기간을 결정하는 함수"""
        try:
            target_stocks = config.target_stocks
            
            # 기본값 설정
            default_period = 60
            default_recent = 30
            default_weight = 0.6
            
            # 종목별 특성 확인
            if stock_code in target_stocks and "period" in target_stocks[stock_code]:
                # 미리 설정된 값이 있으면 사용
                stock_config = target_stocks[stock_code]
                return (
                    stock_config.get("period", default_period),
                    stock_config.get("recent_period", default_recent),
                    stock_config.get("recent_weight", default_weight)
                )
            
            # 없으면 기본 90일 데이터로 종목 특성 분석
            df = Common.GetOhlcv("KR", stock_code, 90)
            if df is None or len(df) < 45:
                return default_period, default_recent, default_weight
                    
            # 시장 환경 판단
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
                
            # 최근 상승률 계산
            if len(df) > rapid_rise_period:
                recent_return = ((df['close'].iloc[-1] - df['close'].iloc[-rapid_rise_period]) / df['close'].iloc[-rapid_rise_period]) * 100
            else:
                recent_return = 0
                
            # 급등주 판단
            is_rapid_rise = recent_return > rapid_rise_threshold
            
            # 변동성 분석
            volatility_90d = df['close'].pct_change().std() * 100
            
            # 급등주는 45-60일, 가중치 높게
            if is_rapid_rise:
                logger.info(f"{stock_code} 급등주 특성 발견: 최근 {rapid_rise_period}일 수익률 {recent_return:.2f}% (기준 {rapid_rise_threshold}%)")
                period = min(60, max(45, int(volatility_90d * 2)))
                recent_period = min(30, max(20, int(period / 2)))
                weight = 0.7
            else:
                # 일반 변동성 주식
                if volatility_90d > 3.0:  # 높은 변동성
                    period = 50
                    weight = 0.65
                elif volatility_90d < 1.5:  # 낮은 변동성
                    period = 75
                    weight = 0.55
                else:  # 중간 변동성
                    period = 60
                    weight = 0.6
                    
                recent_period = int(period / 2)
            
            logger.info(f"{stock_code} 최적 기간 분석 결과: 전체기간={period}일, 최근기간={recent_period}일, 가중치={weight}")
            return period, recent_period, weight
            
        except Exception as e:
            logger.error(f"최적 기간 결정 중 오류: {str(e)}")
            return default_period, default_recent, default_weight

    def calculate_dynamic_profit_target(self, stock_code, indicators):
        """동적으로 목표 수익률을 계산하는 함수 - 복리 효과 극대화 버전"""
        try:
            target_stocks = config.target_stocks
            base_target = target_stocks[stock_code].get('base_profit_target', 6)
            
            # 시장 상황에 따른 조정
            market_timing = self.detect_market_timing()
            market_factor = 1.0
            
            if market_timing in ["strong_uptrend", "uptrend"]:
                market_factor = 0.7  # 30% 더 낮춤
                logger.info(f"{stock_code} 상승장 감지: 회전율 극대화를 위해 목표 수익률 {market_factor:.1f}배 조정")
            elif market_timing in ["downtrend", "strong_downtrend"]:
                market_factor = 1.5  # 50% 높임
                logger.info(f"{stock_code} 하락장 감지: 리스크 관리를 위해 목표 수익률 {market_factor:.1f}배 조정")
            
            # 종목 모멘텀에 따른 추가 조정
            momentum_factor = 1.0
            if indicators['market_trend'] in ['strong_up', 'up'] and market_timing in ["strong_uptrend", "uptrend"]:
                momentum_factor = 0.8
            elif indicators['market_trend'] in ['strong_down', 'down']:
                momentum_factor = 1.3
            
            # 최종 목표 수익률 계산
            dynamic_target = base_target * market_factor * momentum_factor
            
            # 범위 제한 (3-15% 사이)
            dynamic_target = max(3, min(15, dynamic_target))
            
            logger.info(f"{stock_code} 복리 최적화 목표 수익률: {dynamic_target:.1f}% (기본:{base_target}%, 시장:{market_factor:.1f}, 모멘텀:{momentum_factor:.1f})")
            
            return dynamic_target
            
        except Exception as e:
            logger.error(f"동적 목표 수익률 계산 중 오류: {str(e)}")
            return 6

    def get_technical_indicators_weighted(self, stock_code, period=60, recent_period=30, recent_weight=0.7):
        """가중치를 적용한 기술적 지표 계산 함수"""
        try:
            # 전체 기간 데이터 가져오기
            df = Common.GetOhlcv("KR", stock_code, period)
            if df is None or len(df) < period // 2:
                return None
            
            # 설정값 가져오기
            ma_short = config.config.get("ma_short", 5)
            ma_mid = config.config.get("ma_mid", 20)
            ma_long = config.config.get("ma_long", 60)
            rsi_period = config.config.get("rsi_period", 14)
            atr_period = config.config.get("atr_period", 14)
            
            # 기본 이동평균선 계산
            ma_short_val = Common.GetMA(df, ma_short, -2)
            ma_short_before = Common.GetMA(df, ma_short, -3)
            ma_mid_val = Common.GetMA(df, ma_mid, -2)
            ma_mid_before = Common.GetMA(df, ma_mid, -3)
            ma_long_val = Common.GetMA(df, ma_long, -2)
            ma_long_before = Common.GetMA(df, ma_long, -3)
            
            # 최근 30일 고가
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
            
            # RSI 계산
            delta = df['close'].diff()
            gain = delta.copy()
            loss = delta.copy()
            gain[gain < 0] = 0
            loss[loss > 0] = 0
            avg_gain = gain.rolling(window=rsi_period).mean()
            avg_loss = abs(loss.rolling(window=rsi_period).mean())
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-2]
            
            # ATR 계산
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=atr_period).mean().iloc[-2]
            
            # 갭 계산
            gap = max_price - min_price
            step_gap = gap / config.div_num
            percent_gap = round((gap / min_price) * 100, 2)
            
            # 목표 수익률과 트리거 손실률 계산
            target_rate = round(percent_gap / config.div_num, 2)
            trigger_rate = -round((percent_gap / config.div_num), 2)
            
            # 조정폭 계산
            current_price = KisKR.GetCurrentPrice(stock_code)
            pullback_from_high = (max_high_30 - current_price) / max_high_30 * 100
            
            # 현재 구간 계산
            now_step = config.div_num
            for step in range(1, int(config.div_num) + 1):
                if prev_close < min_price + (step_gap * step):
                    now_step = step
                    break
            
            # 추세 판단
            is_uptrend = ma_short_val > ma_mid_val and ma_mid_val > ma_long_val and ma_short_val > ma_short_before
            is_downtrend = ma_short_val < ma_mid_val and ma_mid_val < ma_long_val and ma_short_val < ma_short_before
            
            market_trend = 'strong_up' if is_uptrend else 'strong_down' if is_downtrend else 'sideways'
            if ma_short_val > ma_mid_val and ma_short_val > ma_short_before:
                market_trend = 'up'
            elif ma_short_val < ma_mid_val and ma_short_val < ma_short_before:
                market_trend = 'down'
            
            # 급등주 특성 반영
            recent_rise_percent = ((recent_max_price - recent_min_price) / recent_min_price) * 100
            is_rapid_rise = recent_rise_percent > 30
            
            return {
                'current_price': current_price,
                'prev_open': prev_open,
                'prev_close': prev_close,
                'prev_high': prev_high,
                'ma_short': ma_short_val,
                'ma_short_before': ma_short_before,
                'ma_mid': ma_mid_val,
                'ma_mid_before': ma_mid_before,
                'ma_long': ma_long_val,
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
        """기존 기술적 지표 계산 함수 (호환성 유지)"""
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
            target_stocks = config.target_stocks
            
            # 성장주 확인
            if target_stocks.get(stock_code, {}).get('stock_type') != 'growth':
                return False
                
            # 우상향 확인
            ma_alignment = (indicators['ma_short'] > indicators['ma_mid'] and 
                        indicators['ma_mid'] > indicators['ma_long'])
                        
            # 작은 조정 확인 (1-3% 하락)
            small_pullback = (1.0 <= indicators['pullback_from_high'] <= 3.0)
            
            # 과매수 확인
            not_overbought = indicators['rsi'] < 75
            
            return ma_alignment and small_pullback and not_overbought
        except Exception as e:
            logger.error(f"작은 조정 매수 기회 확인 중 오류: {str(e)}")
            return False

    def get_split_meta_info(self, stock_code, indicators):
        """차수별 투자 정보 계산 - 동적 예산 기반"""
        try:
            target_stocks = config.target_stocks
            stock_weight = target_stocks[stock_code]['weight']
            
            # 🔥 동적 예산 기반 종목별 투자금액 계산
            stock_total_money = self.total_money * stock_weight
            
            # 종목 유형 확인
            stock_type = target_stocks[stock_code].get('stock_type', 'normal')
            
            # 성장주 여부에 따라 첫 진입 비중 조정
            if stock_type == 'growth':
                first_invest_ratio = 0.45  # 45%
                
                market_timing = self.detect_market_timing()
                if market_timing == "strong_uptrend":
                    first_invest_ratio = 0.5  # 50%
                elif market_timing == "downtrend":
                    first_invest_ratio = 0.35  # 35%
                    
                logger.info(f"{stock_code} 성장주 특성 반영: 첫 진입 비중 {first_invest_ratio:.2f}")
            else:
                first_invest_ratio = 0.3  # 30%
                
                if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                    rise_adj = max(0.5, 1.0 - (indicators['recent_rise_percent'] / 100))
                    first_invest_ratio = first_invest_ratio * rise_adj
                    logger.info(f"{stock_code} 급등주 특성 반영: 첫 진입 비중 {first_invest_ratio:.2f}")
                
            first_invest_money = stock_total_money * first_invest_ratio
            remain_invest_money = stock_total_money * (1 - first_invest_ratio)
            
            split_info_list = []
            
            for i in range(int(config.div_num)):
                number = i + 1
                
                # 1차수일 경우
                if number == 1:
                    final_invest_rate = 0
                    
                    # MA 골든크로스 상태 확인
                    if (indicators['ma_short'] > indicators['ma_mid'] and 
                        indicators['ma_mid'] > indicators['ma_long']):
                        final_invest_rate += 15
                    
                    # 각 이동평균선 상태 체크
                    if indicators['prev_close'] >= indicators['ma_short']:
                        final_invest_rate += 5
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
                    
                    # 현재 구간에 따른 투자 비율 결정
                    step_invest_rate = ((int(config.div_num) + 1) - indicators['now_step']) * (40.0 / config.div_num)
                    final_invest_rate += step_invest_rate
                    
                    # RSI 고려
                    rsi_lower = config.config.get("rsi_lower_bound", 30)
                    rsi_upper = config.config.get("rsi_upper_bound", 78)
                    
                    if indicators['rsi'] > rsi_upper:
                        final_invest_rate = final_invest_rate * 0.5
                    elif indicators['rsi'] < rsi_lower:
                        final_invest_rate = final_invest_rate * 0.7
                        
                    # 조정폭 고려
                    pullback_rate = config.config.get("pullback_rate", 5)
                    if indicators['pullback_from_high'] > pullback_rate:
                        final_invest_rate = final_invest_rate * 1.2
                    
                    # 급등주 특성 반영
                    if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                        if indicators['pullback_from_high'] < pullback_rate:
                            final_invest_rate = final_invest_rate * 0.7
                    
                    final_first_money = first_invest_money * (final_invest_rate / 100.0)
                    final_first_money = max(0, min(final_first_money, first_invest_money))
                    
                    # 성장주 여부에 따라 목표 수익률 조정
                    if stock_type == 'growth':
                        dynamic_target = self.calculate_dynamic_profit_target(stock_code, indicators)
                        target_rate_multiplier = max(1.2, dynamic_target / indicators['target_rate'])
                        logger.info(f"{stock_code} 성장주 특성 반영: 동적 목표 수익률 {dynamic_target:.2f}% (승수: {target_rate_multiplier:.2f})")
                    else:
                        target_rate_multiplier = 1.5
                        
                        if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                            target_rate_multiplier = max(1.0, 1.5 - (indicators['recent_rise_percent'] / 100))
                            logger.info(f"{stock_code} 급등주 특성 반영: 목표 수익률 승수 {target_rate_multiplier:.2f}")
                    
                    split_info_list.append({
                        "number": 1,
                        "target_rate": indicators['target_rate'] * target_rate_multiplier,
                        "trigger_rate": None,
                        "invest_money": round(final_first_money)
                    })
                    
                # 2차수 이상
                else:
                    # 성장주 여부에 따라 트리거 민감도 조정
                    if stock_type == 'growth':
                        trigger_multiplier = 0.5
                        
                        market_timing = self.detect_market_timing()
                        if market_timing in ["strong_uptrend", "uptrend"]:
                            trigger_multiplier = 0.7
                        elif market_timing in ["downtrend", "strong_downtrend"]:
                            trigger_multiplier = 0.9
                            
                        logger.info(f"{stock_code} 성장주 특성 반영: 트리거 민감도 {trigger_multiplier:.2f}")
                    else:
                        if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                            trigger_multiplier = min(1.2, 1.0 + (indicators['recent_rise_percent'] / 200))
                            logger.info(f"{stock_code} 급등주 특성 반영: 트리거 승수 {trigger_multiplier:.2f}")
                        else:
                            trigger_multiplier = 1.0

                    # 차수별 비중 설정
                    weight_multiplier = 1.0
                    if number <= 3:
                        weight_multiplier = 1.2
                    elif number >= 6:
                        weight_multiplier = 0.8
                    
                    # 나머지 차수의 합계 가중치 계산
                    total_weight = sum([1.2 if i <= 3 else 0.8 if i >= 6 else 1.0 for i in range(2, int(config.div_num)+1)])
                    
                    # 개별 차수 투자금액 계산
                    invest_money = remain_invest_money * (weight_multiplier / total_weight)
                    
                    # 차수별 목표 수익률 차등화
                    market_timing = self.detect_market_timing()
                    is_bullish = market_timing in ["strong_uptrend", "uptrend"]

                    if is_bullish and stock_type == 'growth':
                        if number <= 2:
                            target_multiplier = 0.6
                        elif number <= 4:
                            target_multiplier = 0.8
                        else:
                            target_multiplier = 1.0
                        logger.info(f"{stock_code} {number}차 상승장 차등 목표: {target_multiplier:.1f}배")
                    else:
                        target_multiplier = 1.0
                    
                    # 차수별 트리거 손실률 차등 적용
                    if number <= 3:
                        trigger_value = indicators['trigger_rate'] * trigger_multiplier * 0.6
                        split_info_list.append({
                            "number": number,
                            "target_rate": indicators['target_rate'] * target_multiplier,
                            "trigger_rate": trigger_value,
                            "invest_money": round(invest_money)
                        })
                    elif number <= 5:
                        split_info_list.append({
                            "number": number,
                            "target_rate": indicators['target_rate'] * target_multiplier,
                            "trigger_rate": indicators['trigger_rate'] * trigger_multiplier,
                            "invest_money": round(invest_money)
                        })
                    else:
                        split_info_list.append({
                            "number": number,
                            "target_rate": indicators['target_rate'] * target_multiplier,
                            "trigger_rate": indicators['trigger_rate'] * trigger_multiplier * 1.3,
                            "invest_money": round(invest_money)
                        })
            
            return split_info_list
        except Exception as e:
            logger.error(f"차수 정보 생성 중 오류: {str(e)}")
            return []

    def get_split_data_info(self, stock_data_list, number):
        """특정 차수 데이터 가져오기"""
        for save_data in stock_data_list:
            if number == save_data['Number']:
                return save_data
        return None

    def check_first_entry_condition(self, indicators):
        """개선된 1차 진입 조건 체크"""
        try:
            market_timing = self.detect_market_timing()
            is_bullish_market = market_timing in ["strong_uptrend", "uptrend"]
            
            pullback_rate = config.config.get("pullback_rate", 5)
            rsi_lower = config.config.get("rsi_lower_bound", 30)
            rsi_upper = config.config.get("rsi_upper_bound", 78)
            
            # 1. 기본 차트 패턴 조건
            if is_bullish_market:
                basic_condition = (
                    indicators['prev_close'] >= indicators['prev_open'] * 0.995 or
                    indicators['ma_short'] > indicators['ma_short_before'] or
                    indicators['current_price'] > indicators['ma_short'] * 0.98
                )
            else:
                basic_condition = (
                    indicators['prev_open'] < indicators['prev_close'] and
                    (indicators['prev_close'] >= indicators['ma_short'] or
                    indicators['ma_short_before'] <= indicators['ma_short'])
                )
            
            # 2. RSI 조건 완화
            if is_bullish_market:
                rsi_condition = (20 <= indicators['rsi'] <= 75)
            else:
                rsi_condition = (rsi_lower <= indicators['rsi'] <= rsi_upper)
            
            # 3. 고점 대비 조정 조건 완화
            pullback_required = pullback_rate
            if is_bullish_market:
                pullback_required = 2.0
                logger.info(f"상승장 감지: 필요 조정폭을 {pullback_required}%로 완화")
            
            pullback_condition = (
                indicators['pullback_from_high'] >= pullback_required
            )
            
            # 4. 이동평균선 정렬 상태 확인
            ma_condition = (
                indicators['ma_short'] > indicators['ma_mid'] or
                indicators['ma_short'] > indicators['ma_short_before']
            )
            
            # 5. 상승장 특별 진입 조건
            bullish_special_condition = False
            if is_bullish_market:
                bullish_special_condition = (
                    indicators['ma_short'] > indicators['ma_mid'] and
                    indicators['current_price'] > indicators['ma_short'] * 0.97 and
                    indicators['rsi'] < 80
                )
            
            # 6. 급등주 특별 조건
            special_condition = False
            if 'is_rapid_rise' in indicators and indicators['is_rapid_rise']:
                if indicators['pullback_from_high'] >= pullback_required * 1.5:
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
                final_condition = (
                    (basic_condition and rsi_condition) or
                    (pullback_condition and rsi_condition) or
                    bullish_special_condition
                )
            else:
                final_condition = (
                    (basic_condition and rsi_condition and (pullback_condition or ma_condition)) or
                    (indicators['rsi'] < rsi_lower and 
                    indicators['prev_close'] > indicators['prev_open'] * 1.02) or
                    special_condition
                )
            
            logger.info(f"1차 진입 최종 결정: {'진입 가능' if final_condition else '진입 불가'}")
            
            return final_condition
                        
        except Exception as e:
            logger.error(f"1차 진입 조건 체크 중 오류: {str(e)}")
            return False

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
        """실현 손익 업데이트 - 설정 파일에도 반영"""
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
                
                # 🔥 전체 성과 추적 업데이트
                tracking = config.config.get("performance_tracking", {})
                tracking["total_realized_pnl"] = tracking.get("total_realized_pnl", 0) + realized_pnl
                tracking["total_trades"] = tracking.get("total_trades", 0) + 1
                if realized_pnl > 0:
                    tracking["winning_trades"] = tracking.get("winning_trades", 0) + 1
                
                config.config["performance_tracking"] = tracking
                config.save_config()
                break

    def sync_with_actual_holdings(self):
        """실제 계좌와 봇 데이터 동기화"""
        is_modified = False
        
        for stock_data_info in self.split_data_list:
            stock_code = stock_data_info['StockCode']
            holdings = self.get_current_holdings(stock_code)
            
            # 봇 내부 데이터의 총 보유량 계산
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
        """매매 로직 처리 - 동적 예산 기반"""
        # 마켓 오픈 상태 확인
        is_market_open = KisKR.IsMarketOpen()
        
        # LP 유동성 공급자 활동 시간 확인
        time_info = time.gmtime()
        is_lp_ok = True
        if time_info.tm_hour == 0 and time_info.tm_min < 6:
            is_lp_ok = False
        
        if not (is_market_open and is_lp_ok):
            for stock_info in self.split_data_list:
                stock_info['IsReady'] = True
            self.save_split_data()
            return
        
        # 🔥 동적 예산 업데이트
        self.update_budget()
        
        # 실제 계좌와 봇 데이터 동기화
        sync_result = self.sync_with_actual_holdings()
        if sync_result:
            logger.info("계좌와 봇 데이터 동기화 완료")
                        
        # 각 종목별 처리
        target_stocks = config.target_stocks
        
        for stock_code, stock_info in target_stocks.items():
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
                
                # 작은 조정 매수 기회 체크
                is_small_pullback_opportunity = self.check_small_pullback_buy_opportunity(stock_code, indicators)
                if is_small_pullback_opportunity:
                    logger.info(f"{stock_info['name']}({stock_code}) 우상향 성장주 작은 조정 감지: 매수 기회 고려")
                
                # 1. 1차수 매수 처리
                first_magic_data = None
                for magic_data in stock_data_info['MagicDataList']:
                    if magic_data['Number'] == 1:
                        first_magic_data = magic_data
                        break
                
                if first_magic_data and not first_magic_data['IsBuy'] and stock_data_info['IsReady']:
                    if self.check_first_entry_condition(indicators) or is_small_pullback_opportunity:
                        stock_data_info['RealizedPNL'] = 0
                        
                        if holdings['amount'] > 0:
                            first_magic_data['IsBuy'] = True
                            first_magic_data['EntryPrice'] = holdings['avg_price']
                            first_magic_data['EntryAmt'] = holdings['amount']
                            first_magic_data['CurrentAmt'] = holdings['amount']
                            first_magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                            self.save_split_data()
                            
                            entry_reason = "작은 조정 매수 기회" if is_small_pullback_opportunity else "기본 진입 조건 충족"
                            msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 1차 투자를 하려고 했는데 잔고가 있어서 이를 1차투자로 가정하게 세팅했습니다! 진입 이유: {entry_reason}"
                            logger.info(msg)
                            discord_alert.SendMessage(msg)
                        else:
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
                        
                        # 목표 수익률 달성 시 매도 처리
                        if (current_rate >= split_meta['target_rate'] and 
                            holdings['amount'] > 0 and 
                            (holdings['revenue_money'] + stock_data_info['RealizedPNL']) > 0):
                            
                            # 종목 유형 확인
                            is_growth_stock = stock_info.get('stock_type') == 'growth'

                            # 성장주 동적 부분 매도 적용
                            if is_growth_stock:
                                current_amt = magic_data.get('CurrentAmt', magic_data['EntryAmt'])
                                
                                # 시장 상황에 따른 동적 부분 매도 비율 계산
                                market_timing = self.detect_market_timing()
                                base_sell_ratio = stock_info.get('partial_sell_ratio', 0.3)
                                
                                if market_timing in ["strong_uptrend", "uptrend"]:
                                    partial_sell_ratio = base_sell_ratio * 0.6
                                    logger.info(f"{stock_code} 상승장 감지: 부분 매도 비율을 {partial_sell_ratio:.1%}로 축소하여 복리 효과 극대화")
                                elif market_timing in ["downtrend", "strong_downtrend"]:
                                    partial_sell_ratio = min(0.5, base_sell_ratio * 1.5)
                                    logger.info(f"{stock_code} 하락장 감지: 부분 매도 비율을 {partial_sell_ratio:.1%}로 확대하여 리스크 관리")
                                else:
                                    partial_sell_ratio = base_sell_ratio
                                
                                # 추가 조건: 수익률이 높을수록 더 적게 매도
                                if market_timing in ["strong_uptrend", "uptrend"] and current_rate > 8:
                                    high_profit_factor = max(0.5, 1.0 - (current_rate - 8) / 20)
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
                                            stock_data_info['IsReady'] = True
                                            logger.info(f"{stock_code} 상승장 감지: 매도 후 즉시 재진입 준비 완료")
                                        else:
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
                                        market_timing = self.detect_market_timing()

                                        if market_timing in ["strong_uptrend", "uptrend"]:
                                            stock_data_info['IsReady'] = True
                                            logger.info(f"{stock_code} 상승장 감지: 매도 후 즉시 재진입 준비 완료")
                                        else:
                                            stock_data_info['IsReady'] = False
                                            logger.info(f"{stock_code} 일반장/하락장: 매도 후 하루 대기")

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
                                    magic_data['CurrentAmt'] = buy_amt
                                    magic_data['EntryDate'] = datetime.now().strftime("%Y-%m-%d")
                                    stock_data_info['IsReady'] = False
                                    self.save_split_data()
                                    
                                    msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 {magic_data['Number']}차 매수 완료! 이전 차수 손실률 {split_meta['trigger_rate']}% 만족"
                                    logger.info(msg)
                                    discord_alert.SendMessage(msg)
                            
                            # 성장주 작은 조정 추가 매수
                            elif (is_small_pullback_opportunity and 
                                stock_info.get('stock_type') == 'growth' and 
                                magic_data['Number'] <= 3):
                                
                                buy_amt = max(1, int(split_meta['invest_money'] * 0.7 / indicators['current_price']))
                                
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
                
                # 3. 풀매수 상태 확인 및 처리
                is_full_buy = all(data['IsBuy'] for data in stock_data_info['MagicDataList'])
                
                if is_full_buy:
                    last_split_meta = None
                    for meta in split_meta_list:
                        if meta['number'] == int(config.div_num):
                            last_split_meta = meta
                            break
                    
                    last_magic_data = self.get_split_data_info(stock_data_info['MagicDataList'], int(config.div_num))
                    
                    if last_split_meta and last_magic_data:
                        last_rate = (indicators['current_price'] - last_magic_data['EntryPrice']) / last_magic_data['EntryPrice'] * 100.0
                        
                        # 추가 하락 시 차수 재정리
                        if last_rate <= last_split_meta['trigger_rate']:
                            msg = f"{stock_info['name']}({stock_code}) 스마트스플릿 풀매수 상태인데 더 하락하여 2차수 손절 및 초기화!"
                            logger.info(msg)
                            discord_alert.SendMessage(msg)
                            
                            # 2차수 손절 및 차수 재정리
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
                                        for i in range(int(config.div_num)):
                                            number = i + 1
                                            
                                            if number >= 2:
                                                data = stock_data_info['MagicDataList'][i]
                                                
                                                if number == int(config.div_num):
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
        """장 종료 후 각 종목 및 전체 누적수익률 요약 알림 전송 - 개선된 버전"""
        try:
            # 동적 예산 정보 추가
            total_realized_pnl = 0
            summary_message = "📈 스마트매직스플릿 수익률 요약 📈\n\n"
            
            # 🔥 예산 정보 추가
            current_budget = self.total_money
            initial_asset = config.initial_total_asset
            performance_rate = 0
            
            if initial_asset > 0:
                balance = KisKR.GetBalance()
                current_total = float(balance.get('TotalMoney', 0)) if balance else initial_asset
                performance_rate = (current_total - initial_asset) / initial_asset * 100
            
            summary_message += f"💰 예산 현황:\n"
            summary_message += f"• 현재 예산: {current_budget:,.0f}원\n"
            summary_message += f"• 전략: {config.absolute_budget_strategy}\n"
            if initial_asset > 0:
                summary_message += f"• 전체 계좌 성과: {performance_rate:+.2f}%\n"
            summary_message += "\n"
            
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
            
            # 성과 추적 정보 추가
            tracking = config.config.get("performance_tracking", {})
            total_trades = tracking.get("total_trades", 0)
            winning_trades = tracking.get("winning_trades", 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            summary_message += f"📊 성과 통계:\n"
            summary_message += f"• 총 거래 횟수: {total_trades}회\n"
            summary_message += f"• 승률: {win_rate:.1f}% ({winning_trades}/{total_trades})\n"
            summary_message += f"• 최고 성과: {tracking.get('best_performance', 0)*100:+.2f}%\n"
            summary_message += f"• 최저 성과: {tracking.get('worst_performance', 0)*100:+.2f}%\n\n"
            
            # 현재 투자 예산 정보
            summary_message += f"💼 현재 할당된 총 투자 예산: {self.total_money:,.0f}원"
            
            # Discord로 알림 전송
            discord_alert.SendMessage(summary_message)
            logger.info("일일 요약 알림 전송 완료")
            
        except Exception as e:
            logger.error(f"일일 요약 알림 전송 중 오류: {str(e)}")

################################### 거래 시간 체크 ##################################

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
        
        # 장 시작 시점 체크
        current_time = datetime.now().time()
        is_market_open = (status_code == '0' and 
                         current_time.hour == 8)
        
        # 거래 가능 시간 체크
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

################################### 메인 실행 함수 ##################################

def run_bot():
    """봇 실행 함수"""
    try:
        # 클래스 변수 사용을 위해 SmartMagicSplit 클래스에 정적 변수 추가
        if not hasattr(SmartMagicSplit, '_daily_summary_sent_date'):
            SmartMagicSplit._daily_summary_sent_date = None

        Common.SetChangeMode()

        # 봇 초기화 및 실행
        bot = SmartMagicSplit()
        
        # 🔥 시작 시 예산 정보 출력
        logger.info(f"🚀 스마트 매직 스플릿 봇 시작!")
        logger.info(f"💰 예산 모드: {'절대 예산' if config.use_absolute_budget else '비율 기반'}")
        logger.info(f"💰 현재 예산: {bot.total_money:,.0f}원")
        logger.info(f"📊 예산 전략: {config.absolute_budget_strategy}")
        
        target_stocks = config.target_stocks
        
        # 첫 실행 시 매매 가능 상태 출력
        for data_info in bot.split_data_list:
            logger.info(f"{data_info['StockName']}({data_info['StockCode']}) 누적 실현 손익: {data_info['RealizedPNL']:,.0f}원")
        
        # 타겟 종목 현황 출력
        logger.info(f"🎯 타겟 종목 현황:")
        for stock_code, stock_config in target_stocks.items():
            weight = stock_config.get('weight', 0)
            allocated_budget = bot.total_money * weight
            logger.info(f"  - {stock_config['name']}({stock_code}): 비중 {weight*100:.1f}% ({allocated_budget:,.0f}원)")
        
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

def send_startup_message():
    """시작 메시지 전송"""
    try:
        target_stocks = config.target_stocks
        
        msg = "🚀 개선된 스마트 매직 스플릿 봇 시작!\n"
        msg += "=" * 40 + "\n"
        msg += f"💰 예산 관리: {'절대 예산 기반' if config.use_absolute_budget else '비율 기반'}\n"
        
        if config.use_absolute_budget:
            msg += f"📊 예산 전략: {config.absolute_budget_strategy}\n"
            msg += f"💵 설정 예산: {config.absolute_budget:,.0f}원\n"
            
            if config.initial_total_asset > 0:
                balance = KisKR.GetBalance()
                if balance:
                    current_total = float(balance.get('TotalMoney', 0))
                    performance = (current_total - config.initial_total_asset) / config.initial_total_asset * 100
                    msg += f"📈 계좌 성과: {performance:+.2f}%\n"
        
        msg += f"\n🎯 타겟 종목 ({len(target_stocks)}개):\n"
        for stock_code, stock_config in target_stocks.items():
            weight = stock_config.get('weight', 0)
            msg += f"• {stock_config['name']}: {weight*100:.1f}% 비중\n"
        
        msg += f"\n⚙️ 주요 설정:\n"
        msg += f"• 분할 수: {config.div_num}차수\n"
        msg += f"• 수수료: {config.config.get('commission_rate', 0.00015)*100:.3f}%\n"
        msg += f"• RSI 기준: {config.config.get('rsi_lower_bound', 30)}-{config.config.get('rsi_upper_bound', 78)}\n"
        msg += f"• 조정 요구: {config.config.get('pullback_rate', 5)}%\n"
        
        # 성과 추적 정보
        tracking = config.config.get("performance_tracking", {})
        if tracking.get("total_trades", 0) > 0:
            win_rate = (tracking.get("winning_trades", 0) / tracking["total_trades"]) * 100
            msg += f"\n📊 누적 성과:\n"
            msg += f"• 총 거래: {tracking['total_trades']}회\n"
            msg += f"• 승률: {win_rate:.1f}%\n"
            msg += f"• 실현손익: {tracking.get('total_realized_pnl', 0):,.0f}원\n"
        
        logger.info(msg)
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(msg)
            
    except Exception as e:
        logger.error(f"시작 메시지 전송 중 오류: {str(e)}")

def main():
    """메인 함수 - 설정 파일 자동 생성 포함"""
    
    # 🔥 1. 설정 파일 확인 및 생성 (가장 먼저 실행)
    config_created = check_and_create_config()
    
    if config_created:
        # 설정 파일이 새로 생성된 경우 사용자 안내
        user_msg = "🎯 스마트 스플릿 봇 초기 설정 완료!\n\n"
        user_msg += "📝 설정 확인 사항:\n"
        user_msg += f"1. 투자 예산: {config.absolute_budget:,}원\n"
        user_msg += f"2. 예산 전략: {config.absolute_budget_strategy}\n"
        user_msg += "3. 종목별 비중:\n"
        
        for stock_code, stock_config in config.target_stocks.items():
            allocated = config.absolute_budget * stock_config.get('weight', 0)
            user_msg += f"   • {stock_config.get('name', stock_code)}: {stock_config.get('weight', 0)*100:.1f}% ({allocated:,.0f}원)\n"
        
        user_msg += "\n💡 설정 변경이 필요하면 'smart_split_config.json' 파일을 수정 후 봇을 재시작하세요."
        user_msg += "\n\n🚀 10초 후 봇이 시작됩니다..."
        
        logger.info(user_msg)
        if config.config.get("use_discord_alert", True):
            discord_alert.SendMessage(user_msg)
        
        # 사용자가 설정을 확인할 시간 제공
        time.sleep(10)
    
    # 시작 메시지 전송
    send_startup_message()
    
    # 처음에 한 번 실행
    run_bot()
    
    # 47초마다 실행하도록 스케줄 설정
    schedule.every(47).seconds.do(run_bot)
    
    # 스케줄러 실행
    while True:
        # 장 시작 운영 시간 및 시작시간 체크
        is_trading_time, is_market_open = check_trading_time()    

        if not is_trading_time:
            logger.info("장 시간 외 입니다. 다음 장 시작까지 대기")
            
            # 🔥 장 시간 외에도 예산 상태 주기적 체크 (1시간마다)
            now = datetime.now()
            if now.minute == 0 and now.second < 50:  # 정시에 한 번만
                try:
                    bot = SmartMagicSplit()  # 임시 인스턴스 생성
                    logger.info(f"💰 장외 예산 체크: {bot.total_money:,.0f}원")
                    
                    # 설정 파일 변경 감지 및 자동 리로드
                    try:
                        import os
                        config_mtime = os.path.getmtime(config.config_path)
                        if not hasattr(main, '_last_config_mtime'):
                            main._last_config_mtime = config_mtime
                        elif config_mtime > main._last_config_mtime:
                            logger.info("📝 설정 파일 변경 감지 - 자동 리로드")
                            config.load_config()
                            main._last_config_mtime = config_mtime
                            
                            # 설정 변경 알림
                            reload_msg = "⚙️ 설정 파일이 자동으로 리로드되었습니다.\n"
                            reload_msg += f"💰 새 예산: {config.absolute_budget:,}원\n"
                            reload_msg += f"📊 예산 전략: {config.absolute_budget_strategy}\n"
                            reload_msg += "🔄 다음 거래부터 새 설정이 적용됩니다."
                            
                            logger.info(reload_msg)
                            if config.config.get("use_discord_alert", True):
                                discord_alert.SendMessage(reload_msg)
                    except Exception as reload_e:
                        logger.warning(f"설정 파일 리로드 체크 중 오류: {str(reload_e)}")
                        
                except Exception as check_e:
                    logger.warning(f"장외 예산 체크 중 오류: {str(check_e)}")
            
            time.sleep(300)  # 5분 대기
            continue    

        schedule.run_pending()
        time.sleep(1)  # CPU 사용량을 줄이기 위해 짧은 대기 시간 추가

if __name__ == "__main__":
    main()