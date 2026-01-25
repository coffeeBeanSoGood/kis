import requests
import json
import yaml
import time
import logging
import os
from datetime import datetime
import pandas as pd

class Kiwoom_Common:
    def __init__(self, log_level=logging.INFO):
        """키움증권 API 초기화"""
        self.real_url = "https://api.kiwoom.com"
        self.mock_url = "https://mockapi.kiwoom.com"
        
        self.appkey = ""
        self.secretkey = ""
        self.access_token = ""
        self.token_expires = ""
        
        self.account_no = ""
        self.is_mock = False
        self.token_path = "./kiwoom_token.json"
        
        # 로깅 설정
        self._setup_logging(log_level)
        
    def _setup_logging(self, log_level):
        """로깅 설정"""
        # 로그 디렉토리 생성
        log_dir = "./logs"
        os.makedirs(log_dir, exist_ok=True)
        
        # 로거 생성
        self.logger = logging.getLogger("KiwoomCommon")
        self.logger.setLevel(log_level)
        
        # 기존 핸들러 제거
        self.logger.handlers.clear()
        
        # 포매터 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 파일 핸들러
        today = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(log_dir, f"kiwoom_{today}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def LoadConfigData(self):
        """설정 파일 로드 (yaml)"""
        try:
            with open('myStockInfo.yaml', 'r', encoding='UTF-8') as f:
                config_data = yaml.safe_load(f)
                
            self.appkey = config_data.get("KIWOOM_APP_KEY", "")
            self.secretkey = config_data.get("KIWOOM_SECRET_KEY", "")
            self.account_no = config_data.get("KIWOOM_ACCOUNT_NO", "")
            self.is_mock = config_data.get("KIWOOM_IS_MOCK", False)
            self.token_path = config_data.get("KIWOOM_TOKEN_PATH", "./kiwoom_token.json")
            
            # URL 설정
            if self.is_mock:
                self.base_url = config_data.get("KIWOOM_MOCK_URL", self.mock_url)
            else:
                self.base_url = config_data.get("KIWOOM_REAL_URL", self.real_url)
            
            self.logger.info("="*60)
            self.logger.info("키움증권 설정 로드 완료")
            self.logger.info(f"계좌번호: {self.account_no}")
            self.logger.info(f"모의투자: {self.is_mock}")
            self.logger.info(f"URL: {self.base_url}")
            self.logger.info("="*60)
            
            return True
            
        except FileNotFoundError:
            self.logger.error("myStockInfo.yaml 파일을 찾을 수 없습니다.")
            return False
        except Exception as e:
            self.logger.error(f"설정 로드 실패: {e}")
            return False
    
    def GetBaseURL(self):
        """기본 URL 반환"""
        return self.base_url
    
    def SaveTokenToFile(self):
        """토큰을 파일에 저장"""
        try:
            token_data = {
                "access_token": self.access_token,
                "token_type": "Bearer",
                "expires_dt": self.token_expires,
                "issued_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(self.token_path, 'w', encoding='UTF-8') as f:
                json.dump(token_data, f, ensure_ascii=False, indent=4)
            
            self.logger.debug(f"토큰 저장 완료: {self.token_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"토큰 저장 실패: {e}")
            return False
    
    def LoadTokenFromFile(self):
        """파일에서 토큰 로드"""
        try:
            with open(self.token_path, 'r', encoding='UTF-8') as f:
                token_data = json.load(f)
            
            self.access_token = token_data.get("access_token", "")
            self.token_expires = token_data.get("expires_dt", "")
            
            # 토큰 만료 체크
            if self.token_expires:
                expire_time = datetime.strptime(self.token_expires, "%Y%m%d%H%M%S")
                now = datetime.now()
                
                if now < expire_time:
                    self.logger.info(f"토큰 로드 성공 (만료: {self.token_expires})")
                    return True
                else:
                    self.logger.warning(f"토큰 만료됨 (만료일: {self.token_expires})")
                    return False
            
            return False
            
        except FileNotFoundError:
            self.logger.debug(f"토큰 파일 없음: {self.token_path}")
            return False
        except Exception as e:
            self.logger.error(f"토큰 로드 실패: {e}")
            return False
    
    def GetAccessToken(self, force_refresh=False):
        """접근 토큰 발급 (au10001)"""
        try:
            # 기존 토큰 확인 (강제 갱신이 아닌 경우)
            if not force_refresh:
                if self.LoadTokenFromFile():
                    return True
            
            # 새 토큰 발급
            url = f"{self.GetBaseURL()}/oauth2/token"
            
            headers = {
                "api-id": "au10001",
                "Content-Type": "application/json;charset=UTF-8"
            }
            
            body = {
                "grant_type": "client_credentials",
                "appkey": self.appkey,
                "secretkey": self.secretkey
            }
            
            self.logger.info("접근 토큰 발급 요청...")
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("return_code") == 0:
                    self.access_token = result.get("token", "")
                    self.token_expires = result.get("expires_dt", "")
                    
                    # 토큰 파일 저장
                    self.SaveTokenToFile()
                    
                    self.logger.info("="*60)
                    self.logger.info("토큰 발급 성공")
                    self.logger.info(f"만료일시: {self.token_expires}")
                    self.logger.info("="*60)
                    return True
                else:
                    self.logger.error(f"토큰 발급 실패: {result.get('return_msg')}")
                    return False
            else:
                self.logger.error(f"HTTP 오류: {response.status_code}")
                self.logger.error(f"응답: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"토큰 발급 예외: {e}")
            return False
    
    def RevokeAccessToken(self):
        """접근 토큰 폐기 (au10002)"""
        try:
            url = f"{self.GetBaseURL()}/oauth2/revoke"
            
            headers = {
                "api-id": "au10002",
                "authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json;charset=UTF-8"
            }
            
            body = {
                "appkey": self.appkey,
                "secretkey": self.secretkey,
                "token": self.access_token
            }
            
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("return_code") == 0:
                    self.logger.info("토큰 폐기 성공")
                    self.access_token = ""
                    self.token_expires = ""
                    return True
            
            self.logger.warning("토큰 폐기 실패")
            return False
            
        except Exception as e:
            self.logger.error(f"토큰 폐기 예외: {e}")
            return False
    
    def GetCommonHeaders(self, api_id, cont_yn="", next_key=""):
        """공통 헤더 생성"""
        headers = {
            "api-id": api_id,
            "authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json;charset=UTF-8"
        }
        
        if cont_yn:
            headers["cont-yn"] = cont_yn
        if next_key:
            headers["next-key"] = next_key
            
        return headers
    
    def CallAPI(self, url, api_id, body=None, method="POST"):
        """API 공통 호출"""
        try:
            headers = self.GetCommonHeaders(api_id)
            
            start_time = time.time()
            
            if method == "POST":
                response = requests.post(url, headers=headers, json=body, timeout=10)
            else:
                response = requests.get(url, headers=headers, timeout=10)
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                self.logger.debug(f"API 호출 성공: {api_id} (응답시간: {elapsed:.3f}초)")
                return response.json()
            else:
                self.logger.error(f"API 호출 실패 ({api_id}): {response.status_code}")
                self.logger.error(f"응답: {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            self.logger.error(f"API 호출 타임아웃 ({api_id})")
            return None
        except Exception as e:
            self.logger.error(f"API 호출 예외 ({api_id}): {e}")
            return None
    
    def GetBalance(self, qry_type="3"):
        """예수금 상세 현황 조회 (kt00001)"""
        try:
            url = f"{self.GetBaseURL()}/api/dostk/acnt"
            
            body = {
                "qry_tp": qry_type  # 3:추정조회, 2:일반조회
            }
            
            result = self.CallAPI(url, "kt00001", body)
            
            if result and result.get("return_code") == 0:
                balance_data = {
                    "Deposit": int(result.get("entr", "0")),  # 예수금
                    "D1_Deposit": int(result.get("d1_entra", "0")),  # D+1 예수금
                    "D2_Deposit": int(result.get("d2_entra", "0")),  # D+2 예수금
                    "WithdrawableAmt": int(result.get("pymn_alow_amt", "0")),  # 출금가능
                    "OrderableAmt": int(result.get("ord_alow_amt", "0")),  # 주문가능
                    "SubstituteAmt": int(result.get("repl_amt", "0")),  # 대용금
                    "CashUnsettled": int(result.get("ch_uncla", "0")),  # 현금미수
                    "TotalLoan": int(result.get("loan_sum", "0")),  # 융자금 합계
                }
                
                self.logger.info(f"예수금 조회 성공 - 주문가능: {balance_data['OrderableAmt']:,}원")
                return balance_data
            else:
                self.logger.error(f"예수금 조회 실패: {result.get('return_msg') if result else 'No response'}")
                return None
                
        except Exception as e:
            self.logger.error(f"예수금 조회 예외: {e}")
            return None
    
    def GetMyStockList(self, exchange_type="KRX"):
        """보유 주식 리스트 조회 (kt00005 체결잔고요청)"""
        try:
            url = f"{self.GetBaseURL()}/api/dostk/acnt"
            
            body = {
                "dmst_stex_tp": exchange_type  # KRX, NXT
            }
            
            result = self.CallAPI(url, "kt00005", body)
            
            if result and result.get("return_code") == 0:
                stock_list = result.get("stk_cntr_remn", [])
                
                # 데이터 파싱
                my_stock_list = []
                for stock in stock_list:
                    # 종목코드 정제 (A005930 -> 005930)
                    stock_code = stock.get("stk_cd", "").replace("A", "").strip()
                    
                    stock_dict = {
                        "StockCode": stock_code,
                        "StockName": stock.get("stk_nm", "").strip(),
                        "CurrentPrice": int(stock.get("cur_prc", "0")),
                        "StockQty": int(stock.get("cur_qty", "0")),
                        "AvailableQty": int(stock.get("setl_remn", "0")),  # 결제잔고
                        "BuyPrice": int(stock.get("buy_uv", "0")),
                        "BuyAmt": int(stock.get("pur_amt", "0")),
                        "EvalAmt": int(stock.get("evlt_amt", "0")),
                        "ProfitLoss": int(stock.get("evltv_prft", "0")),
                        "ProfitRate": float(stock.get("pl_rt", "0")),
                        "CreditType": stock.get("crd_tp", "00"),
                        "LoanDate": stock.get("loan_dt", ""),
                        "ExpiryDate": stock.get("expr_dt", "")
                    }
                    my_stock_list.append(stock_dict)
                
                self.logger.info(f"잔고 조회 성공 - 보유종목: {len(my_stock_list)}개")
                return my_stock_list
            else:
                self.logger.error(f"잔고 조회 실패: {result.get('return_msg') if result else 'No response'}")
                return []
                
        except Exception as e:
            self.logger.error(f"잔고 조회 예외: {e}")
            return []
    
    def GetMyStockInfo(self, stock_code, exchange_type="KRX"):
        """특정 종목 보유 정보 조회"""
        try:
            stock_list = self.GetMyStockList(exchange_type)
            
            for stock in stock_list:
                if stock["StockCode"] == stock_code:
                    self.logger.debug(f"종목 정보 조회: {stock_code} - 수량: {stock['StockQty']}주")
                    return stock
            
            self.logger.debug(f"보유하지 않은 종목: {stock_code}")
            return None
            
        except Exception as e:
            self.logger.error(f"종목 정보 조회 예외: {e}")
            return None
    
    def GetStockInfo(self, stock_code, exchange_type="KRX"):
        """주식 기본 정보 조회 (ka10001)"""
        try:
            url = f"{self.GetBaseURL()}/api/dostk/stkinfo"
            
            body = {
                "stk_cd": stock_code
            }
            
            result = self.CallAPI(url, "ka10001", body)
            
            if result and result.get("return_code") == 0:
                # +, - 부호 제거 함수
                def clean_number(value):
                    if isinstance(value, str):
                        return value.replace("+", "").replace("-", "").strip()
                    return value
                
                stock_info = {
                    "StockCode": stock_code,
                    "StockName": result.get("stk_nm", ""),
                    "CurrentPrice": int(clean_number(result.get("cur_prc", "0"))),
                    "PrevPrice": int(clean_number(result.get("pred_pre", "0"))),
                    "ChangeRate": float(result.get("flu_rt", "0")),
                    "OpenPrice": int(clean_number(result.get("open_pric", "0"))),
                    "HighPrice": int(clean_number(result.get("high_pric", "0"))),
                    "LowPrice": int(clean_number(result.get("low_pric", "0"))),
                    "Volume": int(result.get("trde_qty", "0")),
                    "UpperLimit": int(clean_number(result.get("upl_pric", "0"))),
                    "LowerLimit": int(clean_number(result.get("lst_pric", "0"))),
                    "BasePrice": int(result.get("base_pric", "0"))
                }
                
                self.logger.debug(f"시세 조회: {stock_code} - 현재가: {stock_info['CurrentPrice']:,}원")
                return stock_info
            else:
                self.logger.error(f"시세 조회 실패: {result.get('return_msg') if result else 'No response'}")
                return None
                
        except Exception as e:
            self.logger.error(f"시세 조회 예외: {e}")
            return None
    
    def GetHoga(self, stock_code, exchange_type="KRX"):
        """호가 정보 조회 (ka10004)"""
        try:
            url = f"{self.GetBaseURL()}/api/dostk/mrkcond"
            
            body = {
                "stk_cd": stock_code
            }
            
            result = self.CallAPI(url, "ka10004", body)
            
            if result and result.get("return_code") == 0:
                hoga_data = {
                    "Time": result.get("bid_req_base_tm", ""),
                    "SellHoga": [],
                    "BuyHoga": [],
                    "TotalSellQty": int(result.get("tot_sel_req", "0")),
                    "TotalBuyQty": int(result.get("tot_buy_req", "0"))
                }
                
                # 매도호가 1~10 (역순으로 저장 - 높은 가격부터)
                for i in range(10, 0, -1):
                    suffix = self._get_order_suffix(i)
                    sell_price = int(result.get(f"sel_{suffix}_bid", "0"))
                    sell_qty = int(result.get(f"sel_{suffix}_req", "0"))
                    
                    if sell_price > 0 or sell_qty > 0:
                        hoga_data["SellHoga"].append({
                            "Price": sell_price,
                            "Qty": sell_qty,
                            "Level": i
                        })
                
                # 매수호가 1~10 (정순 - 높은 가격부터)
                for i in range(1, 11):
                    suffix = self._get_order_suffix(i)
                    buy_price = int(result.get(f"buy_{suffix}_bid", "0"))
                    buy_qty = int(result.get(f"buy_{suffix}_req", "0"))
                    
                    if buy_price > 0 or buy_qty > 0:
                        hoga_data["BuyHoga"].append({
                            "Price": buy_price,
                            "Qty": buy_qty,
                            "Level": i
                        })
                
                self.logger.debug(f"호가 조회: {stock_code}")
                return hoga_data
            else:
                self.logger.error(f"호가 조회 실패: {result.get('return_msg') if result else 'No response'}")
                return None
                
        except Exception as e:
            self.logger.error(f"호가 조회 예외: {e}")
            return None
    
    def _get_order_suffix(self, num):
        """호가 순서 접미사 반환"""
        suffix_map = {
            1: "fpr",   # 최우선
            2: "2th",
            3: "3th",
            4: "4th",
            5: "5th",
            6: "6th",
            7: "7th",
            8: "8th",
            9: "9th",
            10: "10th"
        }
        return suffix_map.get(num, "fpr")
    
    def GetUnfilledOrders(self, stock_code="", exchange_type="0"):
        """미체결 조회 (ka10075)"""
        try:
            url = f"{self.GetBaseURL()}/api/dostk/acnt"
            
            body = {
                "all_stk_tp": "0" if not stock_code else "1",  # 0:전체, 1:종목
                "trde_tp": "0",  # 0:전체, 1:매도, 2:매수
                "stk_cd": stock_code,
                "stex_tp": exchange_type  # 0:통합, 1:KRX, 2:NXT
            }
            
            result = self.CallAPI(url, "ka10075", body)
            
            if result and result.get("return_code") == 0:
                unfilled_list = []
                
                for order in result.get("oso", []):
                    order_dict = {
                        "OrderNo": order.get("ord_no", ""),
                        "StockCode": order.get("stk_cd", "").replace("A", "").strip(),
                        "StockName": order.get("stk_nm", "").strip(),
                        "OrderType": order.get("io_tp_nm", ""),
                        "TradeType": order.get("trde_tp", ""),
                        "OrderQty": int(order.get("ord_qty", "0")),
                        "OrderPrice": int(order.get("ord_pric", "0")),
                        "UnfilledQty": int(order.get("oso_qty", "0")),
                        "FilledQty": int(order.get("cntr_qty", "0")),
                        "FilledAmt": int(order.get("cntr_tot_amt", "0")),
                        "OrderTime": order.get("tm", ""),
                        "OrderStatus": order.get("ord_stt", ""),
                        "ExchangeType": order.get("stex_tp_txt", ""),
                        "OrigOrderNo": order.get("orig_ord_no", "")
                    }
                    unfilled_list.append(order_dict)
                
                self.logger.info(f"미체결 조회: {len(unfilled_list)}건")
                return unfilled_list
            else:
                self.logger.error(f"미체결 조회 실패: {result.get('return_msg') if result else 'No response'}")
                return []
                
        except Exception as e:
            self.logger.error(f"미체결 조회 예외: {e}")
            return []
    
    def GetFilledOrders(self, stock_code="", exchange_type="0"):
        """체결 내역 조회 (ka10076)"""
        try:
            url = f"{self.GetBaseURL()}/api/dostk/acnt"
            
            body = {
                "stk_cd": stock_code,
                "qry_tp": "0" if not stock_code else "1",  # 0:전체, 1:종목
                "sell_tp": "0",  # 0:전체, 1:매도, 2:매수
                "ord_no": "",
                "stex_tp": exchange_type  # 0:통합, 1:KRX, 2:NXT
            }
            
            result = self.CallAPI(url, "ka10076", body)
            
            if result and result.get("return_code") == 0:
                filled_list = []
                
                for order in result.get("cntr", []):
                    order_dict = {
                        "OrderNo": order.get("ord_no", ""),
                        "StockCode": order.get("stk_cd", "").replace("A", "").strip(),
                        "StockName": order.get("stk_nm", "").strip(),
                        "OrderType": order.get("io_tp_nm", ""),
                        "TradeType": order.get("trde_tp", ""),
                        "OrderPrice": int(order.get("ord_pric", "0")),
                        "OrderQty": int(order.get("ord_qty", "0")),
                        "FilledPrice": int(order.get("cntr_pric", "0")),
                        "FilledQty": int(order.get("cntr_qty", "0")),
                        "UnfilledQty": int(order.get("oso_qty", "0")),
                        "Commission": int(order.get("tdy_trde_cmsn", "0")),
                        "Tax": int(order.get("tdy_trde_tax", "0")),
                        "OrderTime": order.get("ord_tm", ""),
                        "OrderStatus": order.get("ord_stt", ""),
                        "ExchangeType": order.get("stex_tp_txt", ""),
                        "OrigOrderNo": order.get("orig_ord_no", "")
                    }
                    filled_list.append(order_dict)
                
                self.logger.info(f"체결 조회: {len(filled_list)}건")
                return filled_list
            else:
                self.logger.error(f"체결 조회 실패: {result.get('return_msg') if result else 'No response'}")
                return []
                
        except Exception as e:
            self.logger.error(f"체결 조회 예외: {e}")
            return []
    
    def IsStockMarketOpen(self):
        """장 운영 시간 체크"""
        now = datetime.now()
        current_time = now.time()
        
        # 평일 체크 (토: 5, 일: 6)
        if now.weekday() >= 5:
            self.logger.debug("주말 - 장 마감")
            return False
        
        # 장 운영 시간: 09:00 ~ 15:30
        market_open = datetime.strptime("09:00", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        is_open = market_open <= current_time <= market_close
        
        if is_open:
            self.logger.debug("장 운영 중")
        else:
            self.logger.debug("장 마감 시간")
        
        return is_open
    
    def GetAvailableCash(self):
        """주문 가능 현금 조회"""
        balance = self.GetBalance()
        if balance:
            return balance.get("OrderableAmt", 0)
        return 0
    
    def PrintBalance(self):
        """예수금 정보 출력"""
        try:
            balance = self.GetBalance()
            
            if balance:
                self.logger.info("="*60)
                self.logger.info("예수금 정보")
                self.logger.info("="*60)
                self.logger.info(f"예수금:           {balance['Deposit']:>15,} 원")
                self.logger.info(f"D+1 예수금:       {balance['D1_Deposit']:>15,} 원")
                self.logger.info(f"D+2 예수금:       {balance['D2_Deposit']:>15,} 원")
                self.logger.info(f"출금가능금액:     {balance['WithdrawableAmt']:>15,} 원")
                self.logger.info(f"주문가능금액:     {balance['OrderableAmt']:>15,} 원")
                self.logger.info(f"대용금:           {balance['SubstituteAmt']:>15,} 원")
                self.logger.info(f"현금미수:         {balance['CashUnsettled']:>15,} 원")
                self.logger.info(f"융자금:           {balance['TotalLoan']:>15,} 원")
                self.logger.info("="*60)
        except Exception as e:
            self.logger.error(f"예수금 출력 예외: {e}")
    
    def PrintMyStocks(self):
        """보유 주식 출력"""
        try:
            stock_list = self.GetMyStockList()
            
            self.logger.info("="*100)
            self.logger.info(f"{'종목코드':<10} {'종목명':<15} {'수량':<8} {'매입가':<10} {'현재가':<10} {'수익률':<10}")
            self.logger.info("="*100)
            
            for stock in stock_list:
                self.logger.info(
                    f"{stock['StockCode']:<10} {stock['StockName']:<15} "
                    f"{stock['StockQty']:<8} {stock['BuyPrice']:<10,} "
                    f"{stock['CurrentPrice']:<10,} {stock['ProfitRate']:>9.2f}%"
                )
            
            self.logger.info("="*100)
            
        except Exception as e:
            self.logger.error(f"보유주식 출력 예외: {e}")