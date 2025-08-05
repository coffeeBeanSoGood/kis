#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
미체결 주문 관리 라이브러리 (Pending Order Manager)
pending_order_manager.py

타겟 종목 매매봇용 미체결 주문 추적, 중복 방지, 자동 취소 기능 제공
"""

import datetime
import time
import logging
from typing import Dict, List, Optional, Tuple, Any

class PendingOrderManager:
    """미체결 주문 관리 클래스"""
    
    def __init__(self, kis_api, trading_config, discord_alert=None, logger=None, fee_calculator=None):
        """
        초기화
        
        Args:
            kis_api: KIS API 모듈 (KisKR)
            trading_config: 거래 설정 객체
            discord_alert: 디스코드 알림 모듈 (선택사항)
            logger: 로거 객체 (선택사항)
            fee_calculator: 수수료 계산 함수 (선택사항)
        """
        self.kis_api = kis_api
        self.trading_config = trading_config
        self.discord_alert = discord_alert
        self.logger = logger or logging.getLogger(__name__)
        
        # 수수료 계산 함수
        self.calculate_trading_fee = fee_calculator
    
    def set_fee_calculator(self, fee_calculator_func):
        """수수료 계산 함수 설정 (선택적 사용)"""
        self.calculate_trading_fee = fee_calculator_func
    
    def check_pending_orders(self, stock_code: str, trading_state: Dict = None) -> bool:
        """
        특정 종목의 미체결 주문이 있는지 확인
        
        Args:
            stock_code (str): 종목코드
            trading_state (Dict): 트레이딩 상태
            
        Returns:
            bool: 미체결 주문이 있으면 True, 없으면 False
        """
        try:
            # 1. 내부 상태 확인
            if trading_state:
                pending_orders = trading_state.get('pending_orders', {})
                if stock_code in pending_orders:
                    order_info = pending_orders[stock_code]
                    if order_info.get('status', '') in ['pending', 'submitted']:
                        stock_name = self._get_stock_name(stock_code)
                        self.logger.info(f"🕐 {stock_name}({stock_code}): 내부 상태에 미체결 주문 있음 - 매수 건너뜀")
                        return True
            
            # 2. API 확인   
            try:
                open_orders = self.kis_api.GetOrderList()
                
                if isinstance(open_orders, str):
                    self.logger.warning(f"주문 목록 조회 오류: {open_orders}")
                    return stock_code in pending_orders if trading_state else False
                
                # 해당 종목의 미체결 매수 주문 필터링
                if open_orders:
                    for order in open_orders:
                        order_stock = order.get('StockCode', order.get('OrderStock', ''))
                        order_side = order.get('OrderSide', order.get('Side', ''))
                        order_status = order.get('OrderStatus', order.get('Status', ''))
                        
                        if (order_stock == stock_code and 
                            order_side in ['BUY', 'Buy', '매수', '01'] and
                            order_status in ['OPEN', 'Open', '미체결', '접수']):
                            
                            stock_name = self._get_stock_name(stock_code)
                            self.logger.info(f"🕐 {stock_name}({stock_code}): API에서 미체결 주문 확인 - 매수 건너뜀")
                            return True
                
            except Exception as api_e:
                self.logger.warning(f"API 주문 조회 중 오류: {str(api_e)}")
                return stock_code in pending_orders if trading_state and 'pending_orders' in trading_state else False
            
            return False
                
        except Exception as e:
            self.logger.error(f"미체결 주문 확인 중 에러 ({stock_code}): {str(e)}")
            if trading_state and 'pending_orders' in trading_state:
                return stock_code in trading_state['pending_orders']
            return False
    
    def track_pending_order(self, trading_state: Dict, stock_code: str, order_info: Dict) -> None:
        """
        미체결 주문 추가
        
        Args:
            trading_state (Dict): 트레이딩 상태
            stock_code (str): 종목코드
            order_info (Dict): 주문 정보
        """
        try:
            if 'pending_orders' not in trading_state:
                trading_state['pending_orders'] = {}
            
            stock_name = self._get_stock_name(stock_code)
            
            trading_state['pending_orders'][stock_code] = {
                'stock_name': stock_name,
                'order_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'quantity': order_info['quantity'],
                'price': order_info['price'],
                'order_amount': order_info['quantity'] * order_info['price'],
                'order_id': order_info.get('order_id', ''),
                'status': 'pending',
                'target_config': order_info.get('target_config', {}),
                'signal_strength': order_info.get('signal_strength', 'NORMAL'),
                'daily_score': order_info.get('daily_score', 0)
            }
            
            self.logger.info(f"📝 미체결 주문 등록: {stock_name}({stock_code}) - {order_info['quantity']}주 @ {order_info['price']:,}원")
            
        except Exception as e:
            self.logger.error(f"미체결 주문 등록 중 오류: {str(e)}")
    
    def remove_pending_order(self, trading_state: Dict, stock_code: str, reason: str = "주문 완료") -> None:
        """
        주문 완료시 미체결 목록에서 제거
        
        Args:
            trading_state (Dict): 트레이딩 상태
            stock_code (str): 종목코드
            reason (str): 제거 이유
        """
        try:
            if 'pending_orders' in trading_state and stock_code in trading_state['pending_orders']:
                order_info = trading_state['pending_orders'][stock_code]
                stock_name = order_info.get('stock_name', stock_code)
                
                del trading_state['pending_orders'][stock_code]
                self.logger.info(f"🗑️ 미체결 주문 제거: {stock_name}({stock_code}) - {reason}")
                
        except Exception as e:
            self.logger.error(f"미체결 주문 제거 중 오류: {str(e)}")

    def cancel_order(self, order_id: str) -> bool:
        """
        주문 취소
        
        Args:
            order_id (str): 주문번호
            
        Returns:
            bool: 취소 성공 여부
        """
        try:
            # KIS API로 주문 정보 상세 조회
            order_details = self.kis_api.GetOrderList()
            
            if isinstance(order_details, str):
                self.logger.error(f"주문 목록 조회 오류: {order_details}")
                return False
                
            if not order_details:
                self.logger.error(f"조회된 주문 목록이 없음")
                return False
                
            # 주문번호로 주문 찾기
            target_order = None
            for order in order_details:
                order_num1 = order.get('OrderNum', '')
                order_num2 = order.get('OrderNum2', '')
                
                # 주문번호 매칭 (OrderNum 또는 OrderNum2로 확인)
                if order_num1 == order_id or order_num2 == order_id:
                    target_order = order
                    break
                    
            if not target_order:
                self.logger.error(f"취소할 주문을 찾을 수 없음: {order_id}")
                return False
            
            # 주문 정보 추출
            stock_code = target_order.get('OrderStock', '')
            order_num1 = target_order.get('OrderNum', '')
            order_num2 = target_order.get('OrderNum2', '')
            order_amt = target_order.get('OrderAmt', 0)
            order_price = target_order.get('OrderAvgPrice', 0)
            
            if not all([stock_code, order_num1, order_num2]):
                self.logger.error(f"주문 정보 부족: {target_order}")
                return False
            
            # ✅ CancelModifyOrder 함수 사용 (수정된 부분)
            result = self.kis_api.CancelModifyOrder(
                stockcode=stock_code,
                order_num1=order_num1,
                order_num2=order_num2,
                order_amt=order_amt,
                order_price=order_price,
                mode="CANCEL",
                order_type="LIMIT"
            )
            
            if result and isinstance(result, dict):
                self.logger.info(f"✅ 주문 취소 성공: {order_id}")
                return True
            else:
                self.logger.error(f"❌ 주문 취소 실패: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"주문 취소 중 에러: {str(e)}")
            return False

    def auto_cancel_pending_orders(self, trading_state: Dict, max_pending_minutes: int = 60) -> Dict:
        """
        일정 시간 이상 경과된 미체결 주문 자동 취소
        
        Args:
            trading_state (Dict): 트레이딩 상태
            max_pending_minutes (int): 미체결 상태 최대 허용 시간(분)
            
        Returns:
            Dict: 업데이트된 트레이딩 상태
        """
        try:
            if 'pending_orders' not in trading_state or not trading_state['pending_orders']:
                return trading_state
            
            cancelled_orders = []
            orders_to_clean = []
            
            self.logger.info(f"🔍 미체결 주문 점검 시작: {len(trading_state['pending_orders'])}개 주문")
            
            for stock_code, order_info in trading_state['pending_orders'].items():
                try:
                    order_time_str = order_info.get('order_time', '')
                    stock_name = order_info.get('stock_name', stock_code)
                    
                    if not order_time_str:
                        orders_to_clean.append(stock_code)
                        continue
                    
                    # 주문 경과 시간 계산
                    order_time = datetime.datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (datetime.datetime.now() - order_time).total_seconds() / 60
                    
                    if elapsed_minutes > max_pending_minutes:
                        self.logger.info(f"⏰ 장시간 미체결 주문 취소 시도: {stock_name} ({elapsed_minutes:.0f}분)")
                        
                        try:
                            # ✅ 수정된 부분: CancelModifyOrder 직접 사용
                            order_id = order_info.get('order_id', '')
                            order_num2 = order_info.get('order_num2', '')
                            quantity = order_info.get('quantity', 0)
                            price = order_info.get('price', 0)
                            
                            if order_id and quantity > 0:
                                # CancelModifyOrder 함수 직접 호출
                                cancel_result = self.kis_api.CancelModifyOrder(
                                    stockcode=stock_code,
                                    order_num1=order_id,
                                    order_num2=order_num2 or order_id,  # order_num2가 없으면 order_id 사용
                                    order_amt=quantity,
                                    order_price=price,
                                    mode="CANCEL",
                                    order_type="LIMIT"
                                )
                                
                                if cancel_result and isinstance(cancel_result, dict):
                                    self.logger.info(f"✅ 주문 취소 성공: {stock_name}")
                                    cancelled_orders.append(stock_code)
                                    
                                    # 취소 알림
                                    self.send_order_alert('cancel', stock_code, {
                                        'elapsed_minutes': elapsed_minutes
                                    })
                                else:
                                    self.logger.warning(f"⚠️ 주문 취소 실패: {stock_name} - {cancel_result}")
                                    # 취소 실패해도 정리 대상에 추가 (너무 오래된 주문)
                                    orders_to_clean.append(stock_code)
                            else:
                                self.logger.warning(f"⚠️ 주문정보 부족으로 취소 불가: {stock_name}")
                                orders_to_clean.append(stock_code)
                                
                        except Exception as cancel_error:
                            self.logger.error(f"주문 취소 중 에러: {str(cancel_error)}")
                            # 취소 실패한 경우에도 너무 오래된 주문은 정리
                            orders_to_clean.append(stock_code)
                    
                except Exception as e:
                    self.logger.error(f"미체결 주문 점검 중 에러 ({stock_code}): {str(e)}")
                    orders_to_clean.append(stock_code)
            
            # 취소/정리된 주문들 제거
            all_removed = cancelled_orders + orders_to_clean
            for stock_code in all_removed:
                if stock_code in trading_state['pending_orders']:
                    del trading_state['pending_orders'][stock_code]
            
            self.logger.info(f"📊 미체결 주문 처리 완료: 취소 {len(cancelled_orders)}개, 정리 {len(orders_to_clean)}개")
            
            return trading_state
            
        except Exception as e:
            self.logger.error(f"❌ 미체결 주문 자동 관리 중 전체 오류: {str(e)}")
            return trading_state
    
    def get_committed_budget_for_stock(self, stock_code: str, trading_state: Dict, 
                                     get_invested_amount_func) -> float:
        """
        투자된 금액 + 주문 중인 금액 계산
        
        Args:
            stock_code (str): 종목코드
            trading_state (Dict): 트레이딩 상태
            get_invested_amount_func: 기존 투자 금액 계산 함수
            
        Returns:
            float: 총 사용 중인 금액
        """
        try:
            # 기존 투자된 금액
            invested_amount = get_invested_amount_func(stock_code, trading_state)
            
            # 미체결 주문 금액 추가
            pending_amount = 0
            if 'pending_orders' in trading_state and stock_code in trading_state['pending_orders']:
                order_info = trading_state['pending_orders'][stock_code]
                if order_info.get('status') in ['pending', 'submitted']:
                    pending_amount = order_info.get('order_amount', 0)
            
            total_committed = invested_amount + pending_amount
            
            if pending_amount > 0:
                stock_name = self._get_stock_name(stock_code)
                self.logger.debug(f"💰 {stock_name}({stock_code}) 사용중 금액: "
                                f"투자됨 {invested_amount:,}원 + 주문중 {pending_amount:,}원 = {total_committed:,}원")
            
            return total_committed
            
        except Exception as e:
            self.logger.error(f"사용중 금액 계산 오류 ({stock_code}): {str(e)}")
            return get_invested_amount_func(stock_code, trading_state)
    
    def send_order_alert(self, alert_type: str, stock_code: str, order_info: Dict) -> None:
        """
        주문 관련 알림 발송
        
        Args:
            alert_type (str): 알림 타입 ('submit', 'fill', 'cancel', 'pending')
            stock_code (str): 종목코드
            order_info (Dict): 주문 정보
        """
        try:
            if not self.discord_alert:
                return
            
            stock_name = self._get_stock_name(stock_code)
            
            if alert_type == 'submit':
                msg = f"📋 매수 주문 접수: {stock_name}({stock_code})\n"
                msg += f"주문량: {order_info.get('quantity', 0)}주 @ {order_info.get('price', 0):,}원\n"
                msg += f"주문금액: {order_info.get('order_amount', 0):,}원\n"
                msg += f"체결 대기 중..."
                
            elif alert_type == 'fill':
                msg = f"✅ 매수 체결 완료: {stock_name}({stock_code})\n"
                msg += f"체결가: {order_info.get('executed_price', 0):,}원 × {order_info.get('executed_amount', 0)}주"
                
            elif alert_type == 'cancel':
                msg = f"🕒 미체결 주문 자동 취소: {stock_name}({stock_code})\n"
                msg += f"경과시간: {order_info.get('elapsed_minutes', 0):.1f}분"
                
            elif alert_type == 'pending':
                msg = f"⏱️ 매수 미체결: {stock_name}({stock_code})\n"
                msg += f"주문량: {order_info.get('quantity', 0)}주 @ {order_info.get('price', 0):,}원\n"
                msg += f"자동 관리 대상으로 등록됨"
                
            elif alert_type == 'recover':
                msg = f"🔄 포지션 상태 복구: {stock_name}({stock_code})\n"
                msg += f"보유량: {order_info.get('amount', 0)}주, 평균가: {order_info.get('avg_price', 0):,.0f}원\n"
                msg += f"미체결 주문에서 실제 포지션으로 복구 완료"
            
            else:
                return
            
            self.logger.info(msg)
            self.discord_alert.SendMessage(msg)
            
        except Exception as e:
            self.logger.error(f"알림 발송 중 오류: {str(e)}")
    
    def get_pending_orders_status(self, trading_state: Dict) -> Dict:
        """
        미체결 주문 현황 정보 반환
        
        Args:
            trading_state (Dict): 트레이딩 상태
            
        Returns:
            Dict: 미체결 주문 현황 정보
        """
        try:
            pending_orders = trading_state.get('pending_orders', {})
            
            if not pending_orders:
                return {'count': 0, 'orders': []}
            
            current_time = datetime.datetime.now()
            status_info = {
                'count': len(pending_orders),
                'orders': []
            }
            
            for stock_code, order_info in pending_orders.items():
                try:
                    order_time = datetime.datetime.strptime(order_info['order_time'], '%Y-%m-%d %H:%M:%S')
                    elapsed_minutes = (current_time - order_time).total_seconds() / 60
                    
                    order_status = {
                        'stock_code': stock_code,
                        'stock_name': order_info.get('stock_name', stock_code),
                        'quantity': order_info.get('quantity', 0),
                        'price': order_info.get('price', 0),
                        'order_amount': order_info.get('order_amount', 0),
                        'elapsed_minutes': elapsed_minutes,
                        'status': order_info.get('status', 'unknown')
                    }
                    
                    status_info['orders'].append(order_status)
                    
                except Exception as e:
                    self.logger.warning(f"미체결 주문 상태 조회 오류 ({stock_code}): {str(e)}")
                    continue
            
            return status_info
            
        except Exception as e:
            self.logger.error(f"미체결 주문 현황 조회 오류: {str(e)}")
            return {'count': 0, 'orders': []}
    
    def _get_stock_name(self, stock_code: str) -> str:
        """종목명 조회"""
        try:
            if hasattr(self.trading_config, 'target_stocks'):
                return self.trading_config.target_stocks.get(stock_code, {}).get('name', stock_code)
            return stock_code
        except:
            return stock_code
    
    def _recover_position_from_pending(self, trading_state: Dict, stock_code: str, 
                                     order_info: Dict, actual_amount: int, my_stocks: List) -> Dict:
        """미체결 주문에서 실제 포지션으로 복구"""
        try:
            if stock_code not in trading_state.get('positions', {}):
                # 실제 평균가 조회
                avg_price = 0
                for stock in my_stocks:
                    if stock['StockCode'] == stock_code:
                        avg_price = float(stock.get('AvrPrice', order_info.get('price', 0)))
                        break
                
                if avg_price <= 0:
                    avg_price = order_info.get('price', 0)
                
                # 포지션 정보 복원
                target_config = order_info.get('target_config', {})
                
                position_info = {
                    'stock_code': stock_code,
                    'stock_name': order_info.get('stock_name', stock_code),
                    'entry_price': avg_price,
                    'amount': actual_amount,
                    'buy_fee': self.calculate_trading_fee(avg_price, actual_amount, True) if self.calculate_trading_fee else 0,
                    'entry_time': order_info.get('order_time', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    'high_price': avg_price,
                    'trailing_stop': avg_price * (1 - target_config.get('trailing_stop', 0.018)),
                    'target_config': target_config,
                    'signal_strength': order_info.get('signal_strength', 'NORMAL'),
                    'daily_score': order_info.get('daily_score', 0),
                    'entry_method': 'recovered_from_pending'
                }
                
                if 'positions' not in trading_state:
                    trading_state['positions'] = {}
                trading_state['positions'][stock_code] = position_info
                
                # 복구 알림
                self.send_order_alert('recover', stock_code, {
                    'amount': actual_amount,
                    'avg_price': avg_price
                })
            
            # 미체결 주문 상태 업데이트
            order_info['status'] = 'filled'
            order_info['fill_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            return trading_state
            
        except Exception as e:
            self.logger.error(f"포지션 복구 중 오류 ({stock_code}): {str(e)}")
            return trading_state

    def _try_cancel_order(self, stock_code: str, stock_name: str, elapsed_minutes: float) -> bool:
        """주문 취소 시도"""
        try:
            # API에서 실제 미체결 주문 확인
            open_orders = self.kis_api.GetOrderList(stock_code, "BUY", "OPEN")
            
            if open_orders and not isinstance(open_orders, str):
                for order in open_orders:
                    order_stock = order.get('StockCode', order.get('OrderStock', ''))
                    if order_stock == stock_code:
                        # 주문 정보 추출
                        order_num1 = order.get('OrderNum', '')
                        order_num2 = order.get('OrderNum2', '')
                        order_amt = order.get('OrderAmt', 0)
                        order_price = order.get('OrderAvgPrice', 0)
                        
                        if order_num1 and order_amt > 0:
                            # ✅ CancelModifyOrder 함수 사용
                            cancel_result = self.kis_api.CancelModifyOrder(
                                stockcode=stock_code,
                                order_num1=order_num1,
                                order_num2=order_num2 or order_num1,
                                order_amt=order_amt,
                                order_price=order_price,
                                mode="CANCEL",
                                order_type="LIMIT"
                            )
                            
                            if cancel_result and isinstance(cancel_result, dict):
                                self.send_order_alert('cancel', stock_code, {
                                    'elapsed_minutes': elapsed_minutes
                                })
                                return True
                        break
            
            return False
            
        except Exception as e:
            self.logger.error(f"주문 취소 시도 중 오류 ({stock_code}): {str(e)}")
            return False

# 편의 함수들 (기존 코드와의 호환성을 위해)
def create_pending_order_manager(kis_api, trading_config, discord_alert=None, logger=None):
    """PendingOrderManager 인스턴스 생성 편의 함수"""
    return PendingOrderManager(kis_api, trading_config, discord_alert, logger)


def enhance_trading_state(trading_state: Dict) -> Dict:
    """트레이딩 상태에 pending_orders 필드 추가 (기존 파일 호환성)"""
    if 'pending_orders' not in trading_state:
        trading_state['pending_orders'] = {}
    return trading_state