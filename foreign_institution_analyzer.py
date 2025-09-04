# -*- coding: utf-8 -*-
"""
외국인/기관 매매동향 분석 모듈
bb_trading.py와 완전히 독립된 구조
"""

import KIS_API_Helper_KR as KisKR
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ForeignInstitutionAnalyzer:
    """외국인/기관 매매동향 분석 클래스"""
    
    def __init__(self):
        self.cache = {}  # 종목별 매매동향 캐시
        self.cache_expiry = 3600  # 1시간 캐시
    
    def get_trading_trend_data(self, stock_code, days=20):
        """외국인/기관 매매동향 데이터 조회 및 캐싱"""
        try:
            cache_key = f"{stock_code}_{days}"
            current_time = datetime.now().timestamp()
            
            # 캐시 확인
            if cache_key in self.cache:
                cache_data = self.cache[cache_key]
                if current_time - cache_data['timestamp'] < self.cache_expiry:
                    return cache_data['data']
            
            # 날짜 계산
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=40)).strftime('%Y%m%d')
            
            # API 호출
            trading_data = KisKR.GetInvestorDailyByCode(stock_code, start_date, end_date)
            
            if not trading_data:
                logger.warning(f"{stock_code}: 매매동향 데이터 조회 실패")
                return None
            
            # 최근 days일로 제한
            recent_data = trading_data[-days:] if len(trading_data) > days else trading_data
            
            # 캐시 저장
            self.cache[cache_key] = {
                'data': recent_data,
                'timestamp': current_time
            }
            
            return recent_data
            
        except Exception as e:
            logger.error(f"매매동향 데이터 조회 오류 ({stock_code}): {str(e)}")
            return None
    
    def analyze_foreign_trend(self, trading_data, analysis_period=10):
        """외국인 매매 패턴 분석"""
        try:
            if not trading_data or len(trading_data) < analysis_period:
                return {
                    'trend_score': 0,
                    'trend_direction': 'neutral',
                    'confidence': 0,
                    'signals': ['데이터 부족']
                }
            
            # 최근 분석기간 데이터
            recent_data = trading_data[-analysis_period:]
            foreign_volumes = [data['frgn_ntby_qty'] for data in recent_data]
            
            # 추세 분석
            positive_days = sum(1 for vol in foreign_volumes if vol > 0)
            negative_days = sum(1 for vol in foreign_volumes if vol < 0)
            total_volume = sum(abs(vol) for vol in foreign_volumes)
            net_volume = sum(foreign_volumes)
            
            # 점수 계산
            trend_score = 0
            signals = []
            
            # 기본 추세 점수
            if positive_days >= 7:
                trend_score += 40
                signals.append(f"외국인 지속매수 ({positive_days}/{analysis_period}일)")
            elif positive_days >= 6:
                trend_score += 25
                signals.append(f"외국인 우세매수 ({positive_days}/{analysis_period}일)")
            elif negative_days >= 7:
                trend_score -= 30
                signals.append(f"외국인 지속매도 ({negative_days}/{analysis_period}일)")
            
            # 강도 점수
            if total_volume > 0:
                net_ratio = abs(net_volume) / total_volume
                if net_ratio >= 0.7:
                    intensity_score = 30
                    signals.append(f"외국인 강한 방향성 (순비율: {net_ratio:.1%})")
                elif net_ratio >= 0.5:
                    intensity_score = 20
                    signals.append(f"외국인 중간 방향성 (순비율: {net_ratio:.1%})")
                else:
                    intensity_score = 10
                
                trend_score += intensity_score if net_volume > 0 else -intensity_score
            
            # 최근 3일 가중치
            recent_3days = foreign_volumes[-3:]
            recent_trend = sum(1 for vol in recent_3days if vol > 0)
            
            if recent_trend == 3:
                trend_score += 30
                signals.append("외국인 3일 연속 순매수")
            elif recent_trend == 2:
                trend_score += 15
                signals.append("외국인 최근 매수 우세")
            elif recent_trend == 0:
                trend_score -= 25
                signals.append("외국인 3일 연속 순매도")
            
            # 추세 방향 결정
            if trend_score >= 50:
                trend_direction = 'bullish'
                confidence = min(100, trend_score) / 100
            elif trend_score <= -30:
                trend_direction = 'bearish'  
                confidence = min(100, abs(trend_score)) / 100
            else:
                trend_direction = 'neutral'
                confidence = 0.3
            
            return {
                'trend_score': trend_score,
                'trend_direction': trend_direction,
                'confidence': confidence,
                'signals': signals,
                'positive_days': positive_days,
                'negative_days': negative_days,
                'net_volume': net_volume,
                'analysis_period': analysis_period
            }
            
        except Exception as e:
            logger.error(f"외국인 매매 패턴 분석 오류: {str(e)}")
            return {
                'trend_score': 0,
                'trend_direction': 'neutral',
                'confidence': 0,
                'signals': [f'분석 오류: {str(e)}']
            }
    
    def analyze_institution_trend(self, trading_data, analysis_period=10):
        """기관 매매 패턴 분석"""
        try:
            if not trading_data or len(trading_data) < analysis_period:
                return {
                    'trend_score': 0,
                    'trend_direction': 'neutral',
                    'confidence': 0,
                    'signals': ['데이터 부족']
                }
            
            # 최근 분석기간 데이터
            recent_data = trading_data[-analysis_period:]
            institution_volumes = [data['orgn_ntby_qty'] for data in recent_data]
            
            # 추세 분석
            positive_days = sum(1 for vol in institution_volumes if vol > 0)
            negative_days = sum(1 for vol in institution_volumes if vol < 0)
            total_volume = sum(abs(vol) for vol in institution_volumes)
            net_volume = sum(institution_volumes)
            
            # 점수 계산
            trend_score = 0
            signals = []
            
            # 기본 추세 점수
            if positive_days >= 7:
                trend_score += 25
                signals.append(f"기관 지속매수 ({positive_days}/{analysis_period}일)")
            elif positive_days >= 6:
                trend_score += 15
                signals.append(f"기관 우세매수 ({positive_days}/{analysis_period}일)")
            elif negative_days >= 7:
                trend_score -= 20
                signals.append(f"기관 지속매도 ({negative_days}/{analysis_period}일)")
            
            # 강도 점수
            if total_volume > 0:
                net_ratio = abs(net_volume) / total_volume
                if net_ratio >= 0.6:
                    intensity_score = 20
                    signals.append(f"기관 강한 방향성 (순비율: {net_ratio:.1%})")
                elif net_ratio >= 0.4:
                    intensity_score = 12
                    signals.append(f"기관 중간 방향성 (순비율: {net_ratio:.1%})")
                else:
                    intensity_score = 6
                
                trend_score += intensity_score if net_volume > 0 else -intensity_score
            
            # 최근 5일 가중치
            recent_5days = institution_volumes[-5:]
            recent_trend = sum(1 for vol in recent_5days if vol > 0)
            
            if recent_trend >= 4:
                trend_score += 15
                signals.append("기관 최근 강한 매수")
            elif recent_trend >= 3:
                trend_score += 8
                signals.append("기관 최근 매수 우세")
            elif recent_trend <= 1:
                trend_score -= 12
                signals.append("기관 최근 강한 매도")
            
            # 추세 방향 결정
            if trend_score >= 30:
                trend_direction = 'bullish'
                confidence = min(100, trend_score * 1.5) / 100
            elif trend_score <= -20:
                trend_direction = 'bearish'
                confidence = min(100, abs(trend_score) * 1.5) / 100
            else:
                trend_direction = 'neutral'
                confidence = 0.2
            
            return {
                'trend_score': trend_score,
                'trend_direction': trend_direction,
                'confidence': confidence,
                'signals': signals,
                'positive_days': positive_days,
                'negative_days': negative_days,
                'net_volume': net_volume,
                'analysis_period': analysis_period
            }
            
        except Exception as e:
            logger.error(f"기관 매매 패턴 분석 오류: {str(e)}")
            return {
                'trend_score': 0,
                'trend_direction': 'neutral',
                'confidence': 0,
                'signals': [f'분석 오류: {str(e)}']
            }
    
    def calculate_combined_trading_signal(self, stock_code, foreign_weight=0.7, institution_weight=0.3):
        """외국인/기관 매매동향 종합 신호 계산"""
        try:
            # 매매동향 데이터 조회
            trading_data = self.get_trading_trend_data(stock_code, days=15)
            
            if not trading_data:
                return {
                    'combined_score': 0,
                    'signal_strength': 'NONE',
                    'direction': 'neutral',
                    'confidence': 0,
                    'foreign_analysis': None,
                    'institution_analysis': None,
                    'signals': ['매매동향 데이터 없음']
                }
            
            # 외국인/기관 분석
            foreign_analysis = self.analyze_foreign_trend(trading_data, analysis_period=10)
            institution_analysis = self.analyze_institution_trend(trading_data, analysis_period=10)
            
            # 가중평균으로 종합 점수 계산
            combined_score = (
                foreign_analysis['trend_score'] * foreign_weight + 
                institution_analysis['trend_score'] * institution_weight
            )
            
            # 신호 강도 결정
            abs_score = abs(combined_score)
            if abs_score >= 50:
                signal_strength = 'STRONG'
            elif abs_score >= 30:
                signal_strength = 'MODERATE'  
            elif abs_score >= 15:
                signal_strength = 'WEAK'
            else:
                signal_strength = 'NONE'
            
            # 방향 결정
            if combined_score >= 15:
                direction = 'bullish'
            elif combined_score <= -15:
                direction = 'bearish'
            else:
                direction = 'neutral'
            
            # 신뢰도 계산
            confidence = min(1.0, abs_score / 70)
            
            # 종합 신호 생성
            combined_signals = []
            if foreign_analysis['signals']:
                combined_signals.extend(foreign_analysis['signals'][:2])
            if institution_analysis['signals']:
                combined_signals.extend(institution_analysis['signals'][:2])
            
            return {
                'combined_score': round(combined_score, 1),
                'signal_strength': signal_strength,
                'direction': direction,
                'confidence': round(confidence, 2),
                'foreign_analysis': foreign_analysis,
                'institution_analysis': institution_analysis,
                'signals': combined_signals
            }
            
        except Exception as e:
            logger.error(f"종합 매매신호 계산 오류 ({stock_code}): {str(e)}")
            return {
                'combined_score': 0,
                'signal_strength': 'NONE',
                'direction': 'neutral',
                'confidence': 0,
                'foreign_analysis': None,
                'institution_analysis': None,
                'signals': [f'분석 오류: {str(e)}']
            }

# 전역 분석기 인스턴스
trading_trend_analyzer = ForeignInstitutionAnalyzer()

def enhance_buy_signal_with_foreign_institution(base_signals, stock_code):
    """기존 매수신호에 외국인/기관 매매동향 통합"""
    try:
        base_score = base_signals.get('score', 0)
        
        # 외국인/기관 매매동향 분석
        fi_analysis = trading_trend_analyzer.calculate_combined_trading_signal(stock_code)
        
        # 매매동향 보너스/페널티 계산
        fi_bonus = 0
        fi_signals = []
        
        if fi_analysis['signal_strength'] != 'NONE':
            if fi_analysis['direction'] == 'bullish':
                if fi_analysis['signal_strength'] == 'STRONG':
                    fi_bonus = 15
                elif fi_analysis['signal_strength'] == 'MODERATE':
                    fi_bonus = 10
                else:
                    fi_bonus = 5
                fi_signals.append(f"외국인/기관 매수우세 (+{fi_bonus}점)")
                
            elif fi_analysis['direction'] == 'bearish':
                if fi_analysis['signal_strength'] == 'STRONG':
                    fi_bonus = -20
                elif fi_analysis['signal_strength'] == 'MODERATE':
                    fi_bonus = -12
                else:
                    fi_bonus = -6
                fi_signals.append(f"외국인/기관 매도우세 ({fi_bonus}점)")
        
        # 최종 점수 계산
        enhanced_score = base_score + fi_bonus
        enhanced_score = max(0, min(100, enhanced_score))
        
        # 신호 통합
        enhanced_signals = base_signals.get('signals', []).copy()
        enhanced_signals.extend(fi_signals)
        
        # 매수 강도 재평가
        if enhanced_score >= 70:
            signal_strength = 'STRONG'
        elif enhanced_score >= 55:
            signal_strength = 'MODERATE'
        elif enhanced_score >= 45:
            signal_strength = 'WEAK'
        else:
            signal_strength = 'NONE'
        
        # 기존 신호 정보 복사하고 강화된 정보 추가
        enhanced_result = base_signals.copy()
        enhanced_result.update({
            'score': enhanced_score,
            'signal_strength': signal_strength,
            'signals': enhanced_signals,
            'base_score': base_score,
            'fi_bonus': fi_bonus,
            'fi_analysis': fi_analysis,
            'is_buy_signal': enhanced_score >= base_signals.get('min_score', 50)
        })
        
        return enhanced_result
        
    except Exception as e:
        logger.error(f"매수신호 외국인/기관 강화 오류: {str(e)}")
        # 오류 발생시 기존 신호 그대로 반환
        error_signals = base_signals.get('signals', []).copy()
        error_signals.append(f'외국인/기관 분석 오류: {str(e)}')
        
        result = base_signals.copy()
        result['signals'] = error_signals
        return result

def enhance_sell_signal_with_foreign_institution(base_sell_analysis, stock_code, current_price, entry_price):
    """기존 매도신호에 외국인/기관 매매동향 통합"""
    try:
        if entry_price <= 0:
            return base_sell_analysis
        
        profit_rate = (current_price - entry_price) / entry_price
        
        # 외국인/기관 매매동향 분석
        fi_analysis = trading_trend_analyzer.calculate_combined_trading_signal(stock_code)
        
        # 기존 매도 신호가 있는 경우
        if base_sell_analysis.get('is_sell_signal', False):
            sell_type = base_sell_analysis.get('sell_type', '')
            
            # 강한 외국인 매수 시 수익실현 매도 지연 검토
            should_delay = (
                fi_analysis['direction'] == 'bullish' and 
                fi_analysis['signal_strength'] == 'STRONG' and
                fi_analysis['confidence'] >= 0.6 and
                profit_rate > 0.02 and
                '손절' not in sell_type
            )
            
            if should_delay:
                enhanced_result = base_sell_analysis.copy()
                enhanced_result.update({
                    'is_sell_signal': False,
                    'sell_type': 'hold_extended_by_fi',
                    'reason': f"외국인/기관 강한매수로 보유연장 (기존: {base_sell_analysis['reason']})",
                    'fi_analysis': fi_analysis
                })
                return enhanced_result
            
            # 매도 신호 유지하되 외국인/기관 정보 추가
            enhanced_reason = base_sell_analysis['reason']
            if fi_analysis['direction'] == 'bearish':
                enhanced_reason += f" + 외국인/기관 {fi_analysis['signal_strength'].lower()} 매도"
            
            enhanced_result = base_sell_analysis.copy()
            enhanced_result.update({
                'reason': enhanced_reason,
                'fi_analysis': fi_analysis
            })
            return enhanced_result
        
        # 기존 매도 신호가 없는 경우 - 새로운 매도 신호 생성 가능성 검토
        if (fi_analysis['direction'] == 'bearish' and 
            fi_analysis['signal_strength'] in ['STRONG', 'MODERATE'] and
            profit_rate > -0.03):
            
            return {
                'is_sell_signal': True,
                'sell_type': 'foreign_institution_sell',
                'reason': f"외국인/기관 {fi_analysis['signal_strength'].lower()} 매도신호 (수익률: {profit_rate*100:.1f}%)",
                'urgent': fi_analysis['signal_strength'] == 'STRONG',
                'fi_analysis': fi_analysis
            }
        
        # 매도 신호 없음 - 외국인/기관 정보만 추가
        enhanced_result = base_sell_analysis.copy()
        enhanced_result.update({
            'fi_analysis': fi_analysis
        })
        
        if 'reason' in enhanced_result:
            enhanced_result['reason'] += f" (외국인/기관: {fi_analysis['direction']})"
        
        return enhanced_result
        
    except Exception as e:
        logger.error(f"매도신호 외국인/기관 강화 오류: {str(e)}")
        return base_sell_analysis