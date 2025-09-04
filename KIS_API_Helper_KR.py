# -*- coding: utf-8 -*-
import KIS_Common as Common


import requests
import json


from datetime import datetime
from pytz import timezone

import pprint
import math
import time


import pandas as pd

from pykrx import stock

import concurrent.futures

# KIS_API_Helper_KR.py
import logging

from datetime import datetime, timedelta  # timedelta 추가

import random

# 전역 logger 변수 선언
logger = None

def set_logger(external_logger):
    """외부 로거를 설정하는 함수"""
    global logger
    logger = external_logger

#마켓 상태..이로움님 코드
def MarketStatus(stock_code = '069500'):

    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)



    PATH = "uapi/domestic-stock/v1/quotations/inquire-price"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    headers = {
        "Content-Type" : "application/json",
        "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey": Common.GetAppKey(Common.GetNowDist()),
        "appSecret": Common.GetAppSecret(Common.GetNowDist()),
        "tr_id":"FHKST01010200"
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code                          # stock_code: 무조건 주식코드 입력이 필요해서 입력이 없을 경우 KODEX 200의 코드(069500)를 기본으로 사용
    }

    res = requests.get(URL, headers=headers, params=params)

    if res.status_code == 200 and res.json()["rt_cd"] == '0':
        output1 = res.json()['output1']
        #output2 = res.json()['output2']                     # 동시호가 신호가 필요할 경우

        result = {
            'Status': output1['new_mkop_cls_code'][0],     # '','1' : 장개시전,  '2' : 장중,  '3' : 장종료후,  '4' : 시간외단일가,  '0' : 동시호가(개장전,개장후)
        }

        return result
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]


#오늘 개장일인지 조회! (휴장일이면 'N'을 리턴!)
def IsTodayOpenCheck():
    time.sleep(0.2)

    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)
    now_time = datetime.now(timezone('Asia/Seoul'))
    formattedDate = now_time.strftime("%Y%m%d")
    logger.info(f"\n{pprint.pformat(formattedDate)}")


    PATH = "uapi/domestic-stock/v1/quotations/chk-holiday"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":"CTCA0903R"}

    params = {
        "BASS_DT":formattedDate,
        "CTX_AREA_NK":"",
        "CTX_AREA_FK":""
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)
    #logger.info(f"\n{pprint.pformat(res.json())}")

    if res.status_code == 200 and res.json()["rt_cd"] == '0':
        DayList = res.json()['output']

        IsOpen = 'Y'
        for dayInfo in DayList:
            if dayInfo['bass_dt'] == formattedDate:
                IsOpen = dayInfo['opnd_yn']
                break


        return IsOpen
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]


#시장이 열렸는지 여부 체크! #토요일 일요일은 확실히 안열리니깐 제외! 
def IsMarketOpen():


    now_time = datetime.now(timezone('Asia/Seoul'))
    logger.info(f"\n{pprint.pformat(now_time)}")
    strNow = now_time.strftime('%Y/%m/%d')
    
    
    date_week = now_time.weekday()

    IsOpen = False

    #주말은 무조건 장이 안열리니 False 리턴!
    if date_week == 5 or date_week == 6:  
        IsOpen = False
    else:
        #9시 부터 3시 반
        if now_time.hour >= 9 and now_time.hour <= 15:
            IsOpen = True

            if now_time.hour == 15 and now_time.minute > 30:
                IsOpen = False

    #평일 장 시간이어도 공휴일같은날 장이 안열린다.
    if IsOpen == True:
        
        logger.info(f"Time is OK... but one more checked!!!")
        
        
        Is_CheckTody = False


        CheckDict = dict()

        #파일 경로입니다.
        file_path = "./KR_Market_OpenCheck.json"
        try:
            with open(file_path, 'r') as json_file:
                CheckDict = json.load(json_file)

        except Exception as e:
            logger.error(f"Exception by First")


        #만약 키가 존재 하지 않는다 즉 아직 한번도 체크하지 않은 상황
        if CheckDict.get("CheckTody") == None:

            Is_CheckTody = True
            
        else:
      
            #날짜가 바뀌었다면 체크 해야 한다!
            if CheckDict['CheckTody'] != strNow:
                Is_CheckTody = True


        Is_Ok = False
        if Is_CheckTody == True:
            
            
            
            #NowDist = Common.GetNowDist() 
            try:

                #시간 정보를 읽는다
                time_info = time.gmtime()


                day_n = time_info.tm_mday
                df = Common.GetOhlcv("KR", "005930",10) 
                date = df.iloc[-1].name

                #날짜 정보를 획득
                date_format = "%Y-%m-%d %H:%M:%S"
                date_object = None

                try:
                    date_object = datetime.strptime(str(date), date_format)

                except Exception as e:
                    try:
                        date_format = "%Y%m%d"
                        date_object = datetime.strptime(str(date), date_format)

                    except Exception as e2:
                        date_format = "%Y-%m-%d"
                        date_object = datetime.strptime(str(date), date_format)
                        
                if int(date_object.strftime("%d")) == day_n:
                    Is_Ok = True


            except Exception as e:
                #Common.SetChangeMode(NowDist)
                logger.error(f"EXCEPTION {e}")


            market = MarketStatus()
            logger.info(f"\n{pprint.pformat(market)}")

            IsJangJung = False
            if (market['Status'] == '2'):
                IsJangJung = True
                
            

            #장운영시간이 아니라고 리턴되면 장이 닫힌거다!
            if IsTodayOpenCheck() == 'N' or IsJangJung == False:
                logger.info(f"Market is Close!!")
                
                return False
            #아니라면 열린거다
            else:

                if Is_Ok == True:
                    

                    #마켓이 열린 시간내에 가짜주문이 유효하다면 장이 열렸으니 더이상 이 시간내에 또 체크할 필요가 없다.
                    CheckDict['CheckTody'] = strNow
                    with open(file_path, 'w') as outfile:
                        json.dump(CheckDict, outfile)


                    logger.info(f"Market is Open!!!!")
                    return True
                else:
                    logger.info(f"Market is Close!!")
                
                    return False
        else:
            logger.info(f"Market is Open (Already Checked)!!!!")
            return True
    else:

        logger.info(f"Time is NO!!!")     
           
        return False


#price_pricision 호가 단위에 맞게 변형해준다. 지정가 매매시 사용
def PriceAdjust(price, stock_code):
    
    NowPrice = GetCurrentPrice(stock_code)

    price = int(price)

    data = GetCurrentStatus(stock_code)
    if data['StockMarket'] == 'ETF' or price <= NowPrice:
        
        hoga = GetHoga(stock_code)

        adjust_price = math.floor(price / hoga) * hoga
        
        return adjust_price

    else:
        #호가를 직접 구해서 개선!!!
        hoga = 1
        if price < 2000:
            hoga = 1
        elif price < 5000:
            hoga = 5
        elif price < 20000:
            hoga = 10
        elif price < 50000:
            hoga = 50
        elif price < 200000:
            hoga = 100
        elif price < 500000:
            hoga = 500
        elif price >= 500000:
            hoga = 1000
        

        adjust_price = math.floor(price / hoga) * hoga
        
        return adjust_price


    
#나의 계좌 잔고!
def GetBalance():

    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
        return GetBalanceIRP()
    else:

            
        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        PATH = "uapi/domestic-stock/v1/trading/inquire-balance"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        logger.info(f"URL ===== {URL}" )
        TrId = "TTTC8434R"
        if Common.GetNowDist() == "VIRTUAL":
            TrId = "VTTC8434R"


        # 헤더 설정
        headers = {"Content-Type":"application/json", 
                "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
                "appKey":Common.GetAppKey(Common.GetNowDist()),
                "appSecret":Common.GetAppSecret(Common.GetNowDist()),
                "tr_id": TrId,
                "custtype": "P"}

        params = {
            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
            "AFHR_FLPR_YN" : "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN" : "N",
            "FNCG_AMT_AUTO_RDPT_YN" : "N",
            "PRCS_DVSN" : "01",
            "CTX_AREA_FK100" : "",
            "CTX_AREA_NK100" : ""
        }

        # 호출
        res = requests.get(URL, headers=headers, params=params)
        #logger.info(f"\n{pprint.pformat(res.json())}")
        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            result = res.json()['output2'][0]
            #logger.info(f"\n{pprint.pformat(result)}")

            balanceDict = dict()
            #주식 총 평가 금액
            balanceDict['StockMoney'] = float(result['scts_evlu_amt'])
            #평가 손익 금액
            balanceDict['StockRevenue'] = float(result['evlu_pfls_smtl_amt'])
            
            
                
            #총 평가 금액
            balanceDict['TotalMoney'] = float(result['tot_evlu_amt'])

            #예수금이 아예 0이거나 총평가금액이랑 주식평가금액이 같은 상황일때는.. 좀 이상한 특이사항이다 풀매수하더라도 1원이라도 남을 테니깐
            #퇴직연금 계좌에서 tot_evlu_amt가 제대로 반영이 안되는 경우가 있는데..이때는 전일 총평가금액을 가져오도록 한다!
            if float(result['dnca_tot_amt']) == 0 or balanceDict['TotalMoney'] == balanceDict['StockMoney']:
                #장이 안열린 상황을 가정 
                #if IsMarketOpen() == False:
                balanceDict['TotalMoney'] = float(result['bfdy_tot_asst_evlu_amt'])


            #예수금 총금액 (즉 주문가능현금)
            balanceDict['RemainMoney'] = float(balanceDict['TotalMoney']) - float(balanceDict['StockMoney'])#result['dnca_tot_amt']
            
            #그래도 아직도 남은 금액이 0이라면 dnca_tot_amt 예수금 항목에서 정보를 가지고 온다
            if balanceDict['RemainMoney'] == 0:
                balanceDict['RemainMoney'] = float(result['dnca_tot_amt'])
                


            return balanceDict

        else:
            logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
            return res.json()["msg_cd"]
        



#나의 계좌 잔고!
def GetBalanceIRP():

    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/trading/pension/inquire-balance"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    TrId = "TTTC8434R"
    if Common.GetNowDist() == "VIRTUAL":
         TrId = "VTTC8434R"


    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": TrId,
            "custtype": "P"}

    params = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "AFHR_FLPR_YN" : "N",
        "OFL_YN": "",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN" : "N",
        "FNCG_AMT_AUTO_RDPT_YN" : "N",
        "PRCS_DVSN" : "01",
        "ACCA_DVSN_CD" : "00",
        "INQR_DVSN": "00",
        "CTX_AREA_FK100" : "",
        "CTX_AREA_NK100" : ""
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)
    #logger.info(f"\n{pprint.pformat(res.json())}")
    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        result = res.json()['output2'][0]

        #logger.info(f"\n{pprint.pformat(result)}")

        balanceDict = dict()
        #주식 총 평가 금액
        balanceDict['StockMoney'] = float(result['scts_evlu_amt'])
        #평가 손익 금액
        balanceDict['StockRevenue'] = float(result['evlu_pfls_smtl_amt'])
        
    

        Data = CheckPossibleBuyInfoIRP("069500",9140,"LIMIT")

        #예수금 총금액 (즉 주문가능현금)
        balanceDict['RemainMoney'] = float(Data['RemainMoney']) #float(balanceDict['TotalMoney']) - float(balanceDict['StockMoney'])
        

            
        #총 평가 금액
        balanceDict['TotalMoney'] = balanceDict['StockMoney'] + balanceDict['RemainMoney']

 

        return balanceDict

    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]




#한국 보유 주식 리스트!
def GetMyStockList():

    

    PATH = "uapi/domestic-stock/v1/trading/inquire-balance"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    TrId = "TTTC8434R"
    if Common.GetNowDist() == "VIRTUAL":
         TrId = "VTTC8434R"
         
         
    StockList = list()
    
    DataLoad = True
    
    FKKey = ""
    NKKey = ""
    PrevNKKey = ""
    tr_cont = ""
    
    count = 0

    #드물지만 보유종목이 아주 많으면 한 번에 못가져 오므로 SeqKey를 이용해 연속조회를 하기 위한 반복 처리 
    while DataLoad:



        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)
        # 헤더 설정
        headers = {"Content-Type":"application/json", 
                "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
                "appKey":Common.GetAppKey(Common.GetNowDist()),
                "appSecret":Common.GetAppSecret(Common.GetNowDist()),
                "tr_id": TrId,
                "tr_cont": tr_cont,
                "custtype": "P"}

        params = {
            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
            "AFHR_FLPR_YN" : "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN" : "N",
            "FNCG_AMT_AUTO_RDPT_YN" : "N",
            "PRCS_DVSN" : "00",
            "CTX_AREA_FK100" : FKKey,
            "CTX_AREA_NK100" : NKKey
        }


        # 호출
        res = requests.get(URL, headers=headers, params=params)
        
        if res.headers['tr_cont'] == "M" or res.headers['tr_cont'] == "F":
            tr_cont = "N"
        else:
            tr_cont = ""



        if res.status_code == 200 and res.json()["rt_cd"] == '0':
                
            NKKey = res.json()['ctx_area_nk100'].strip()
            if NKKey != "":
                logger.info(f"---> CTX_AREA_NK100: {NKKey}")

            FKKey = res.json()['ctx_area_fk100'].strip()
            if FKKey != "":
                logger.info(f"---> CTX_AREA_FK100: {FKKey}")



            if PrevNKKey == NKKey:
                DataLoad = False
            else:
                PrevNKKey = NKKey
                
            if NKKey == "":
                DataLoad = False
            
            
                
            ResultList = res.json()['output1']
            #logger.info(f"\n{pprint.pformat(ResultList)}")



            for stock in ResultList:
                #잔고 수량이 0 이상인것만
                if int(stock['hldg_qty']) > 0:

                    StockInfo = dict()
                    
                    StockInfo["StockCode"] = stock['pdno']
                    StockInfo["StockName"] = stock['prdt_name']
                    StockInfo["StockAmt"] = stock['hldg_qty']
                    StockInfo["StockAvgPrice"] = stock['pchs_avg_pric']
                    StockInfo["StockOriMoney"] = stock['pchs_amt']
                    StockInfo["StockNowMoney"] = stock['evlu_amt']
                    StockInfo["StockNowPrice"] = stock['prpr']
                # StockInfo["StockNowRate"] = stock['fltt_rt'] #등락률인데 해외 주식에는 없어서 통일성을 위해 여기도 없앰 ㅎ
                    StockInfo["StockRevenueRate"] = stock['evlu_pfls_rt']
                    StockInfo["StockRevenueMoney"] = stock['evlu_pfls_amt']
                    

                    Is_Duple = False
                    for exist_stock in StockList:
                        if exist_stock["StockCode"] == StockInfo["StockCode"]:
                            Is_Duple = True
                            break
                            

                    if Is_Duple == False:
                        StockList.append(StockInfo)


        else:
            logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
            #return res.json()["msg_cd"]

            if res.json()["msg_cd"] == "EGW00123":
                DataLoad = False

            count += 1
            if count > 10:
                DataLoad = False
    
    return StockList




############################################################################################################################################################

#국내 주식현재가 시세
def GetCurrentPrice(stock_code):
    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/quotations/inquire-price"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":"FHKST01010100"}

    params = {
        "FID_COND_MRKT_DIV_CODE":"J",
        "FID_INPUT_ISCD": stock_code
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)
    #logger.info(f"\n{pprint.pformat(res.json())}")

    if res.status_code == 200 and res.json()["rt_cd"] == '0':
        return int(res.json()['output']['stck_prpr'])
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]


#국내 주식 호가 단위!
def GetHoga(stock_code):
    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/quotations/inquire-price"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":"FHKST01010100"}

    params = {
        "FID_COND_MRKT_DIV_CODE":"J",
        "FID_INPUT_ISCD": stock_code
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)
    #logger.info(f"\n{pprint.pformat(res.json())}")

    if res.status_code == 200 and res.json()["rt_cd"] == '0':
        return int(res.json()['output']['aspr_unit'])
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]




#국내 주식 이름 
def GetStockName(stock_code):
    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"


    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":"FHKST03010100"}

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": Common.GetFromNowDateStr("KR","NONE",-7),
        "FID_INPUT_DATE_2": Common.GetNowDateStr("KR"),
        "FID_PERIOD_DIV_CODE": 'D',
        "FID_ORG_ADJ_PRC": "0"
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        return res.json()['output1']['hts_kor_isnm']
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]






#퀀트 투자를 위한 함수!    
#국내 주식 시총, PER, PBR, EPS, PBS 구해서 리턴하기!
def GetCurrentStatus(stock_code):
    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/quotations/inquire-price"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":"FHKST01010100"}

    params = {
        "FID_COND_MRKT_DIV_CODE":"J",
        "FID_INPUT_ISCD": stock_code
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)
    #logger.info(f"\n{pprint.pformat(res.json())}")

    if res.status_code == 200 and res.json()["rt_cd"] == '0':
        
        result = res.json()['output']
        
        #logger.info(f"\n{pprint.pformat(result)}")

        
        stockDataDict = dict()
        stockDataDict['StockCode'] = stock_code
        stockDataDict['StockName'] = GetStockName(stock_code)
        stockDataDict['StockNowPrice'] = int(result['stck_prpr'])
        stockDataDict['StockMarket'] = result['rprs_mrkt_kor_name'] #ETF인지 코스피, 코스닥인지

        try:
            stockDataDict['StockDistName'] = result['bstp_kor_isnm'] #금융주 등을 제외 하기 위해!!
        except Exception as e:
            stockDataDict['StockDistName'] = ""
            

        stockDataDict['StockNowStatus'] = result['iscd_stat_cls_code'] #관리종목,투자경고,투자주의,거래정지,단기과열을 제끼기 위해

        try:
            stockDataDict['StockMarketCap'] = float(result['hts_avls']) #시총
        except Exception as e:
            stockDataDict['StockMarketCap'] = 0

        try:
            stockDataDict['StockPER'] = float(result['per']) #PER
        except Exception as e:
            stockDataDict['StockPER'] = 0

        try:
            stockDataDict['StockPBR'] = float(result['pbr']) #PBR
        except Exception as e:
            stockDataDict['StockPBR'] = 0


        try:
            stockDataDict['StockEPS'] = float(result['eps']) #EPS
        except Exception as e:
            stockDataDict['StockEPS'] = 0
        
        try:
            stockDataDict['StockBPS'] = float(result['bps']) #BPS
        except Exception as e:
            stockDataDict['StockBPS'] = 0

        
        
        return stockDataDict
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]
    
    





############################################################################################################################################################
#시장가 주문하기!
def MakeBuyMarketOrder(stockcode, amt, adjustAmt = False):
    
    #매수가능 수량으로 보정할지 여부
    if adjustAmt == True:
        try:
            #매수 가능한수량으로 보정
            amt = AdjustPossibleAmt(stockcode, amt, "MARKET")

        except Exception as e:
            logger.error(f"Exception")

    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
        return MakeBuyMarketOrderIRP(stockcode, amt)
    else:
            

        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)
        TrId = "TTTC0802U"
        if Common.GetNowDist() == "VIRTUAL":
            TrId = "VTTC0802U"


        PATH = "uapi/domestic-stock/v1/trading/order-cash"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        data = {
            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
            "PDNO": stockcode,
            "ORD_DVSN": "01",
            "ORD_QTY": str(int(amt)),
            "ORD_UNPR": "0"
        }
        headers = {"Content-Type":"application/json", 
            "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": TrId,
            "custtype":"P",
            "hashkey" : Common.GetHashKey(data)
        }
        res = requests.post(URL, headers=headers, data=json.dumps(data))

        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            order = res.json()['output']

            OrderInfo = dict()
            

            OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
            OrderInfo["OrderNum2"] = order['ODNO']
            OrderInfo["OrderTime"] = order['ORD_TMD'] 



            return OrderInfo
        else:
            logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
            
            if res.json()["msg_cd"] == "APBK1744":
                MakeBuyMarketOrderIRP(stockcode, amt)
            
            
            return res.json()["msg_cd"]
            

#시장가 매도하기!
def MakeSellMarketOrder(stockcode, amt):

    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
        return MakeSellMarketOrderIRP(stockcode, amt)
    else:

        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        TrId = "TTTC0801U"
        if Common.GetNowDist() == "VIRTUAL":
            TrId = "VTTC0801U"


        PATH = "uapi/domestic-stock/v1/trading/order-cash"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        data = {
            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
            "PDNO": stockcode,
            "ORD_DVSN": "01",
            "ORD_QTY": str(int(amt)),
            "ORD_UNPR": "0",
        }
        headers = {"Content-Type":"application/json", 
            "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":TrId,
            "custtype":"P",
            "hashkey" : Common.GetHashKey(data)
        }
        res = requests.post(URL, headers=headers, data=json.dumps(data))

        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            order = res.json()['output']

            OrderInfo = dict()
            

            OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
            OrderInfo["OrderNum2"] = order['ODNO']
            OrderInfo["OrderTime"] = order['ORD_TMD'] 


            return OrderInfo
        else:
            logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
            
            if res.json()["msg_cd"] == "APBK1744":
                MakeSellMarketOrderIRP(stockcode, amt)
            
            return res.json()["msg_cd"]


#지정가 주문하기!
def MakeBuyLimitOrder(stockcode, amt, price, adjustAmt = False, ErrLog = "NO"):
    

    #매수가능 수량으로 보정할지 여부
    if adjustAmt == True:
        try:
            #매수 가능한수량으로 보정
            amt = AdjustPossibleAmt(stockcode, amt, "LIMIT")

        except Exception as e:
            logger.error(f"Exception")


    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
        return MakeBuyLimitOrderIRP(stockcode, amt, price)
    else:

        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)


        TrId = "TTTC0802U"
        if Common.GetNowDist() == "VIRTUAL":
            TrId = "VTTC0802U"


        PATH = "uapi/domestic-stock/v1/trading/order-cash"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        data = {
            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
            "PDNO": stockcode,
            "ORD_DVSN": "00",
            "ORD_QTY": str(int(amt)),
            "ORD_UNPR": str(PriceAdjust(price,stockcode)),
        }
        headers = {"Content-Type":"application/json", 
            "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": TrId,
            "custtype":"P",
            "hashkey" : Common.GetHashKey(data)
        }
        res = requests.post(URL, headers=headers, data=json.dumps(data))

        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            order = res.json()['output']

            OrderInfo = dict()
            

            OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
            OrderInfo["OrderNum2"] = order['ODNO']
            OrderInfo["OrderTime"] = order['ORD_TMD'] 


            return OrderInfo

        else:
            if ErrLog == "YES":
                logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
                
            if res.json()["msg_cd"] == "APBK1744":
                MakeBuyLimitOrderIRP(stockcode, amt, price)
                
            return res.json()["msg_cd"]
            

#지정가 매도하기!
def MakeSellLimitOrder(stockcode, amt, price, ErrLog="YES"):

    time.sleep(0.2)

    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)



    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
        return MakeSellLimitOrderIRP(stockcode, amt, price)
    else:

        TrId = "TTTC0801U"
        if Common.GetNowDist() == "VIRTUAL":
            TrId = "VTTC0801U"


        PATH = "uapi/domestic-stock/v1/trading/order-cash"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        data = {
            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
            "PDNO": stockcode,
            "ORD_DVSN": "00",
            "ORD_QTY": str(int(amt)),
            "ORD_UNPR": str(PriceAdjust(price,stockcode)),
        }
        headers = {"Content-Type":"application/json", 
            "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":TrId,
            "custtype":"P",
            "hashkey" : Common.GetHashKey(data)
        }
        res = requests.post(URL, headers=headers, data=json.dumps(data))
        
        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            order = res.json()['output']

            OrderInfo = dict()
            

            OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
            OrderInfo["OrderNum2"] = order['ODNO']
            OrderInfo["OrderTime"] = order['ORD_TMD'] 



            return OrderInfo
        else:
            if ErrLog == "YES":
                logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
                
            if res.json()["msg_cd"] == "APBK1744":
                MakeSellLimitOrderIRP(stockcode, amt, price)
                
            return res.json()["msg_cd"]


#보유한 주식을 모두 시장가 매도하는 극단적 함수 
def SellAllStock():
    StockList = GetMyStockList()

    #시장가로 모두 매도 한다
    for stock_info in StockList:
        logger.info(f"\n{pprint.pformat(MakeSellMarketOrder(stock_info['StockCode'],stock_info['StockAmt']))}")





############# #############   IRP 계좌를 위한 매수 매도 함수   ############# ############# ############# 

#시장가 주문하기!
def MakeBuyMarketOrderIRP(stockcode, amt):


    time.sleep(0.2)

    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    TrId = "TTTC0502U"


    PATH = "uapi/domestic-stock/v1/trading/order-pension"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
    data = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "SLL_BUY_DVSN_CD" : "02",
        "SLL_TYPE" : "01",
        "ORD_DVSN": "01",
        "PDNO": stockcode,
        "LNKD_ORD_QTY" : str(int(amt)),
        "LNKD_ORD_UNPR": "0",
        "RVSE_CNCL_DVSN_CD" : "00",
        "KRX_FWDG_ORD_ORGNO" : "",
        "ORGN_ODNO" : "",
        "CTAC_TLNO" : "",
        "ACCA_DVSN_CD" : "01"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey":Common.GetAppKey(Common.GetNowDist()),
        "appSecret":Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": TrId,
        "custtype":"P",
        "hashkey" : Common.GetHashKey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        order = res.json()['output']

        OrderInfo = dict()
        

        OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
        OrderInfo["OrderNum2"] = order['ODNO']
        OrderInfo["OrderTime"] = order['ORD_TMD'] 



        return OrderInfo
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        
        
        return res.json()["msg_cd"]
    
#시장가 매도하기!
def MakeSellMarketOrderIRP(stockcode, amt):


    time.sleep(0.2)

    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)


    TrId = "TTTC0502U"


    PATH = "uapi/domestic-stock/v1/trading/order-pension"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
    data = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "SLL_BUY_DVSN_CD" : "01",
        "SLL_TYPE" : "01",
        "ORD_DVSN": "01",
        "PDNO": stockcode,
        "LNKD_ORD_QTY" : str(int(amt)),
        "LNKD_ORD_UNPR": "0",
        "RVSE_CNCL_DVSN_CD" : "00",
        "KRX_FWDG_ORD_ORGNO" : "",
        "ORGN_ODNO" : "",
        "CTAC_TLNO" : "",
        "ACCA_DVSN_CD" : "01"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey":Common.GetAppKey(Common.GetNowDist()),
        "appSecret":Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": TrId,
        "custtype":"P",
        "hashkey" : Common.GetHashKey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        order = res.json()['output']

        OrderInfo = dict()
        

        OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
        OrderInfo["OrderNum2"] = order['ODNO']
        OrderInfo["OrderTime"] = order['ORD_TMD'] 



        return OrderInfo
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        
        
        return res.json()["msg_cd"]
    

#지정가 주문하기!
def MakeBuyLimitOrderIRP(stockcode, amt, price, ErrLog="YES"):


    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    TrId = "TTTC0502U"


    PATH = "uapi/domestic-stock/v1/trading/order-pension"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
    data = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "SLL_BUY_DVSN_CD" : "02",
        "SLL_TYPE" : "01",
        "ORD_DVSN": "00",
        "PDNO": stockcode,
        "LNKD_ORD_QTY" : str(int(amt)),
        "LNKD_ORD_UNPR": str(PriceAdjust(price,stockcode)),
        "RVSE_CNCL_DVSN_CD" : "00",
        "KRX_FWDG_ORD_ORGNO" : "",
        "ORGN_ODNO" : "",
        "CTAC_TLNO" : "",
        "ACCA_DVSN_CD" : "01"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey":Common.GetAppKey(Common.GetNowDist()),
        "appSecret":Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": TrId,
        "custtype":"P",
        "hashkey" : Common.GetHashKey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        order = res.json()['output']

        OrderInfo = dict()
        

        OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
        OrderInfo["OrderNum2"] = order['ODNO']
        OrderInfo["OrderTime"] = order['ORD_TMD'] 



        return OrderInfo
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        
        
        return res.json()["msg_cd"]

#지정가 매도하기!
def MakeSellLimitOrderIRP(stockcode, amt, price, ErrLog="YES"):


    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    TrId = "TTTC0502U"


    PATH = "uapi/domestic-stock/v1/trading/order-pension"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
    data = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "SLL_BUY_DVSN_CD" : "01",
        "SLL_TYPE" : "01",
        "ORD_DVSN": "00",
        "PDNO": stockcode,
        "LNKD_ORD_QTY" : str(int(amt)),
        "LNKD_ORD_UNPR": str(PriceAdjust(price,stockcode)),
        "RVSE_CNCL_DVSN_CD" : "00",
        "KRX_FWDG_ORD_ORGNO" : "",
        "ORGN_ODNO" : "",
        "CTAC_TLNO" : "",
        "ACCA_DVSN_CD" : "01"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey":Common.GetAppKey(Common.GetNowDist()),
        "appSecret":Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": TrId,
        "custtype":"P",
        "hashkey" : Common.GetHashKey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        order = res.json()['output']

        OrderInfo = dict()
        

        OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
        OrderInfo["OrderNum2"] = order['ODNO']
        OrderInfo["OrderTime"] = order['ORD_TMD'] 



        return OrderInfo
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        
        
        return res.json()["msg_cd"]
    
#보유한 주식을 모두 시장가 매도하는 극단적 함수 
def SellAllStockIRP():
    StockList = GetMyStockList()

    #시장가로 모두 매도 한다
    for stock_info in StockList:
        logger.info(f"\n{pprint.pformat(MakeSellMarketOrderIRP(stock_info['StockCode'],stock_info['StockAmt']))}")




############################################################################################################################################################




############################################################################################################################################################

#매수 가능한지 체크 하기!
def CheckPossibleBuyInfo(stockcode, price, type):

    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/trading/inquire-psbl-order"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    TrId = "TTTC8908R"
    if Common.GetNowDist() == "VIRTUAL":
         TrId = "VTTC8908R"

    type_code = "00" #지정가
    if type.upper() == "MAREKT":
        type_code = "01"



    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": TrId,
            "custtype": "P"}

    params = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "PDNO" : stockcode,
        "ORD_UNPR": str(PriceAdjust(price,stockcode)),
        "ORD_DVSN": type_code,
        "CMA_EVLU_AMT_ICLD_YN" : "N",
        "OVRS_ICLD_YN" : "N"
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        result = res.json()['output']
#        logger.info(f"\n{pprint.pformat(result)}")

        CheckDict = dict()

        CheckDict['RemainMoney'] = result['nrcvb_buy_amt']
        CheckDict['MaxAmt'] = result['nrcvb_buy_qty']

        return CheckDict

    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]


#매수 가능한수량으로 보정
def AdjustPossibleAmt(stockcode, amt ,type):
    NowPrice = GetCurrentPrice(stockcode)

    data = None

    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
            
        data = CheckPossibleBuyInfoIRP(stockcode,NowPrice,type)
    else:
            
        data = CheckPossibleBuyInfo(stockcode,NowPrice,type)
    

    MaxAmt = int(data['MaxAmt'])

    if MaxAmt <= int(amt):
        logger.info(f"!!!!!!!!!!!!MaxAmt Over!!!!!!!!!!!!!!!!!!")
        return MaxAmt
    else:
        logger.info(f"!!!!!!!!!!!!Amt OK!!!!!!!!!!!!!!!!!!")
        return int(amt)
        





#매수 가능한지 체크 하기! -IRP 계좌
def CheckPossibleBuyInfoIRP(stockcode, price, type):

    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/trading/pension/inquire-psbl-order"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    TrId = "TTTC0503R"


    type_code = "00" #지정가
    if type.upper() == "MAREKT":
        type_code = "01"



    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": TrId,
            "custtype": "P"}

    params = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "PDNO" : stockcode,
        "ORD_UNPR": str(PriceAdjust(price,stockcode)),
        "ORD_DVSN": type_code,
        "CMA_EVLU_AMT_ICLD_YN" : "N",
        "ACCA_DVSN_CD" : "00"
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        result = res.json()['output']
#        logger.info(f"\n{pprint.pformat(result)}")

        CheckDict = dict()

        CheckDict['RemainMoney'] = result['max_buy_amt']
        CheckDict['MaxAmt'] = result['max_buy_qty']

        return CheckDict

    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]








############################################################################################################################################################

#주문 리스트를 얻어온다! 종목 코드, side는 ALL or BUY or SELL, 상태는 OPEN or CLOSE
def GetOrderList(stockcode = "", side = "ALL", status = "ALL", limit = 5):
    
    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    TrId = "TTTC8001R"
    if Common.GetNowDist() == "VIRTUAL":
         TrId = "VTTC8001R"

    sell_buy_code = "00"
    if side.upper() == "BUY":
        sell_buy_code = "02"
    elif side.upper() == "SELL":
        sell_buy_code = "01"
    else:
        sell_buy_code = "00"

    status_code= "00"
    if status.upper() == "OPEN":
        status_code = "02"
    elif status.upper() == "CLOSE":
        status_code = "01"
    else:
        status_code = "00"


    PATH = "uapi/domestic-stock/v1/trading/inquire-daily-ccld"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
    

    params = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD": Common.GetPrdtNo(Common.GetNowDist()),
        "INQR_STRT_DT": Common.GetFromNowDateStr("KR","NONE", -limit),
        "INQR_END_DT": Common.GetNowDateStr("KR"),
        "SLL_BUY_DVSN_CD": sell_buy_code,
        "INQR_DVSN": "00",
        "PDNO": stockcode,
        "CCLD_DVSN": status_code,
        "ORD_GNO_BRNO": "",
        "ODNO": "",
        "INQR_DVSN_3": "00",
        "INQR_DVSN_1": "",
        "INQR_DVSN_2": "",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",

    }
    
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey":Common.GetAppKey(Common.GetNowDist()),
        "appSecret":Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": TrId,
        "custtype":"P",
        "hashkey" : Common.GetHashKey(params)
    }

    res = requests.get(URL, headers=headers, params=params) 
    #logger.info(f"\n{pprint.pformat(res.json())}")
    
    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        ResultList = res.json()['output1']

        OrderList = list()
        #logger.info(f"\n{pprint.pformat(ResultList)}")

        for order in ResultList:
            #잔고 수량이 0 이상인것만


            OrderInfo = dict()
            
            OrderInfo["OrderStock"] = order['pdno']
            OrderInfo["OrderStockName"] = order['prdt_name']

            #주문 구분
            if order['ord_dvsn_cd'] == "00":
                OrderInfo["OrderType"] = "Limit"
            else:
                OrderInfo["OrderType"] = "Market"

            #주문 사이드
            if order['sll_buy_dvsn_cd'] == "01":
                OrderInfo["OrderSide"] = "Sell"
            else:
                OrderInfo["OrderSide"] = "Buy"

            #주문 상태
            if float(order['ord_qty']) - (float(order['tot_ccld_qty']) + float(order['cncl_cfrm_qty'])) == 0:
                OrderInfo["OrderSatus"] = "Close"
            else:
                OrderInfo["OrderSatus"] = "Open"



            if Common.GetNowDateStr("KR") != order['ord_dt']: 
                OrderInfo["OrderSatus"] = "Close"     


            #주문 수량~
            OrderInfo["OrderAmt"] = int(float(order['ord_qty']))

            #주문 최종 수량~
            OrderInfo["OrderResultAmt"] = int(float(order['tot_ccld_qty']) + float(order['cncl_cfrm_qty']))


            #주문넘버..
            OrderInfo["OrderNum"] = order['ord_gno_brno']
            OrderInfo["OrderNum2"] = order['odno']

            #아직 미체결 주문이라면 주문 단가를
            if OrderInfo["OrderSatus"] == "Open":

                OrderInfo["OrderAvgPrice"] = order['ord_unpr']

            #체결된 주문이면 평균체결금액을!
            else:

                OrderInfo["OrderAvgPrice"] = order['avg_prvs']


            OrderInfo["OrderIsCancel"] = order['cncl_yn'] #주문 취소 여부!
            OrderInfo['OrderMarket'] = "KOR" #마켓인데 미국과 통일성을 위해!

            OrderInfo["OrderDate"] = order['ord_dt']
            OrderInfo["OrderTime"] = order['ord_tmd'] 

            Is_Ok = False
            
            if status == "ALL":
                Is_Ok = True
            else:
                if status.upper()  == OrderInfo["OrderSatus"].upper() :
                    Is_Ok = True


            if Is_Ok == True:
                Is_Ok = False

                if side.upper() == "ALL":
                    Is_Ok = True
                else:
                    if side.upper() == OrderInfo["OrderSide"].upper():
                        Is_Ok = True


            if Is_Ok == True:
                if stockcode != "":
                    if stockcode.upper() == OrderInfo["OrderStock"].upper():
                        OrderList.append(OrderInfo)
                else:

                    OrderList.append(OrderInfo)



        return OrderList

    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]



#주문 취소/수정 함수
def CancelModifyOrder(stockcode, order_num1 , order_num2 , order_amt , order_price, mode = "CANCEL" ,order_type = "LIMIT" , order_dist = "NONE"):


    #퇴직연금(29) 반영
    if int(Common.GetPrdtNo(Common.GetNowDist())) == 29:
        return CancelModifyOrderIRP(stockcode, order_num1 , order_num2 , order_amt , order_price, mode,order_type, order_dist)
    else:
            
        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)


        TrId = "TTTC0803U"
        if Common.GetNowDist() == "VIRTUAL":
            TrId = "VTTC0803U"

        order_type = "00"
        if order_type.upper() == "MARKET":
            order_type = "01"
    

        mode_type = "02"
        if mode.upper() == "MODIFY":
            mode_type = "01"



        PATH = "uapi/domestic-stock/v1/trading/order-rvsecncl"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        data = {

            "CANO": Common.GetAccountNo(Common.GetNowDist()),
            "ACNT_PRDT_CD": Common.GetPrdtNo(Common.GetNowDist()),
            "KRX_FWDG_ORD_ORGNO": order_num1,
            "ORGN_ODNO": order_num2,
            "ORD_DVSN": order_type,
            "RVSE_CNCL_DVSN_CD": mode_type,
            "ORD_QTY": str(order_amt),
            "ORD_UNPR": str(PriceAdjust(order_price,stockcode)),
            "QTY_ALL_ORD_YN": "N"

        }
        headers = {"Content-Type":"application/json", 
            "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": TrId,
            "custtype":"P",
            "hashkey" : Common.GetHashKey(data)
        }

        res = requests.post(URL, headers=headers, data=json.dumps(data))
        
        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            order = res.json()['output']

            OrderInfo = dict()
            

            OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
            OrderInfo["OrderNum2"] = order['ODNO']
            OrderInfo["OrderTime"] = order['ORD_TMD'] 


            return OrderInfo
        else:
            logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
            return res.json()["msg_cd"]






#연금IRP 계좌 주문 취소/수정 함수
def CancelModifyOrderIRP(stockcode, order_num1 , order_num2 , order_amt , order_price, mode = "CANCEL" ,order_type = "LIMIT", order_dist = "NONE"):


    time.sleep(0.2)
    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)


    order_dist = "02"
    if order_dist.upper() == "SELL":
        order_dist = "01"

    order_type = "00"
    if order_type.upper() == "MARKET":
        order_type = "01"


    mode_type = "02"
    if mode.upper() == "MODIFY":
        mode_type = "01"


    TrId = "TTTC0502U"


    PATH = "uapi/domestic-stock/v1/trading/order-pension"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
    data = {
        "CANO": Common.GetAccountNo(Common.GetNowDist()),
        "ACNT_PRDT_CD" : Common.GetPrdtNo(Common.GetNowDist()),
        "SLL_BUY_DVSN_CD" : order_dist,
        "SLL_TYPE" : "01",
        "ORD_DVSN": order_type,
        "PDNO": "",
        "LNKD_ORD_QTY" : str(int(order_amt)),
        "LNKD_ORD_UNPR": str(PriceAdjust(order_price,stockcode)),
        "RVSE_CNCL_DVSN_CD" : mode_type,
        "KRX_FWDG_ORD_ORGNO" : order_num1,
        "ORGN_ODNO" : order_num2,
        "CTAC_TLNO" : "",
        "ACCA_DVSN_CD" : "01"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey":Common.GetAppKey(Common.GetNowDist()),
        "appSecret":Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": TrId,
        "custtype":"P",
        "hashkey" : Common.GetHashKey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        order = res.json()['output']

        OrderInfo = dict()
        

        OrderInfo["OrderNum"] = order['KRX_FWDG_ORD_ORGNO']
        OrderInfo["OrderNum2"] = order['ODNO']
        OrderInfo["OrderTime"] = order['ORD_TMD'] 



        return OrderInfo
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        
        
        return res.json()["msg_cd"]
    



#모든 주문을 취소하는 함수
def CancelAllOrders(stockcode = "", side = "ALL"):

    OrderList = GetOrderList(stockcode,side)

    for order in OrderList:
        if order['OrderSatus'].upper() == "OPEN":
            logger.info(f"\n{pprint.pformat(CancelModifyOrder(order['OrderStock'], order['OrderNum'],order['OrderNum2'],order['OrderAmt'],order['OrderAvgPrice']))}")


#시장가 주문 정보를 읽어서 체결 평균가를 리턴! 에러나 못가져오면 현재가를 리턴!
def GetMarketOrderPrice(stockcode,ResultOrder):
    time.sleep(0.2)

    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    OrderList = GetOrderList(stockcode)
    
    OrderDonePrice = 0
    
    #넘어온 주문정보와 일치하는 주문을 찾아서 평균 체결가를 세팅!
    for orderInfo in OrderList:
        if orderInfo['OrderNum'] == ResultOrder['OrderNum'] and float(orderInfo['OrderNum2']) == float(ResultOrder['OrderNum2']):
            OrderDonePrice = int(orderInfo['OrderAvgPrice'])
            break
        
    #혹시나 없다면 현재가로 셋팅!
    if OrderDonePrice == 0:
        OrderDonePrice = GetCurrentPrice(stockcode)
        
    return OrderDonePrice
        
        


############################################################################################################################################################
    
#p_code -> D:일, W:주, M:월, Y:년
def GetOhlcv(stock_code,p_code, adj_ok = "1"):

    time.sleep(0.2)

    #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    FID_ORG_ADJ_PRC = "0"
    if adj_ok == "1":
        FID_ORG_ADJ_PRC = "0"
    else:
        FID_ORG_ADJ_PRC = "1"


    # 헤더 설정
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey":Common.GetAppKey(Common.GetNowDist()),
            "appSecret":Common.GetAppSecret(Common.GetNowDist()),
            "tr_id":"FHKST03010100"}

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": Common.GetFromNowDateStr("KR","NONE",-36500),
        "FID_INPUT_DATE_2": Common.GetNowDateStr("KR"),
        "FID_PERIOD_DIV_CODE": p_code,
        "FID_ORG_ADJ_PRC": FID_ORG_ADJ_PRC
    }

    # 호출
    res = requests.get(URL, headers=headers, params=params)

    if res.status_code == 200 and res.json()["rt_cd"] == '0':

        ResultList = res.json()['output2']


        df = list()


        if len(pd.DataFrame(ResultList)) > 0:

            OhlcvList = list()


            for ohlcv in ResultList:
                
                if len(ohlcv) == 0:
                    continue

                OhlcvData = dict()

                try:
                    if ohlcv['stck_oprc'] != "":
                        
                        OhlcvData['Date'] = ohlcv['stck_bsop_date']
                        OhlcvData['open'] = float(ohlcv['stck_oprc'])
                        OhlcvData['high'] = float(ohlcv['stck_hgpr'])
                        OhlcvData['low'] = float(ohlcv['stck_lwpr'])
                        OhlcvData['close'] = float(ohlcv['stck_clpr'])
                        OhlcvData['volume'] = float(ohlcv['acml_vol'])
                        OhlcvData['value'] = float(ohlcv['acml_tr_pbmn'])


                        OhlcvList.append(OhlcvData)
                except Exception as e:
                    logger.error(f"E: {e}" )
                    
            if len(OhlcvList) > 0:
                        
                df = pd.DataFrame(OhlcvList)
                df = df.set_index('Date')

                df = df.sort_values(by="Date")
                df.insert(6,'change',(df['close'] - df['close'].shift(1)) / df['close'].shift(1))
                    
                df[[ 'open', 'high', 'low', 'close', 'volume', 'change']] = df[[ 'open', 'high', 'low', 'close', 'volume', 'change']].apply(pd.to_numeric)


                df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')

        return df
    else:
        logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)
        return res.json()["msg_cd"]

#100개이상 가져오도록 수정!
def GetOhlcvNew(stock_code,p_code,get_count, adj_ok = "1"):


    PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    FID_ORG_ADJ_PRC = "0"
    if adj_ok == "1":
        FID_ORG_ADJ_PRC = "0"
    else:
        FID_ORG_ADJ_PRC = "1"


    OhlcvList = list()

    DataLoad = True
    
    
    count = 0
 

    now_date = Common.GetNowDateStr("KR")
    date_str_start = Common.GetFromDateStr(pd.to_datetime(now_date),"NONE",-100)
    date_str_end = now_date

    while DataLoad:

        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        logger.info(f"...Data.Length.. {len(OhlcvList)}--> {get_count}")
        if len(OhlcvList) >= get_count:
            DataLoad = False





        # 헤더 설정
        headers = {"Content-Type":"application/json", 
                "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
                "appKey":Common.GetAppKey(Common.GetNowDist()),
                "appSecret":Common.GetAppSecret(Common.GetNowDist()),
                "tr_id":"FHKST03010100"}

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": date_str_start,
            "FID_INPUT_DATE_2": date_str_end,
            "FID_PERIOD_DIV_CODE": p_code,
            "FID_ORG_ADJ_PRC": FID_ORG_ADJ_PRC
        }
  
        # 호출
        res = requests.get(URL, headers=headers, params=params)


        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            ResultList = res.json()['output2']


            df = list()

            add_cnt = 0
            if len(pd.DataFrame(ResultList)) > 0:


                for ohlcv in ResultList:
                    
                    if len(ohlcv) == 0:
                        continue

                    OhlcvData = dict()

                    try:
                        if ohlcv['stck_oprc'] != "":
                            
                            OhlcvData['Date'] = ohlcv['stck_bsop_date']
                            OhlcvData['open'] = float(ohlcv['stck_oprc'])
                            OhlcvData['high'] = float(ohlcv['stck_hgpr'])
                            OhlcvData['low'] = float(ohlcv['stck_lwpr'])
                            OhlcvData['close'] = float(ohlcv['stck_clpr'])
                            OhlcvData['volume'] = float(ohlcv['acml_vol'])
                            OhlcvData['value'] = float(ohlcv['acml_tr_pbmn'])


                            Is_Duple = False
            
                            for exist_stock in OhlcvList:
                                if exist_stock['Date'] == OhlcvData['Date']:
                                    Is_Duple = True
                                    break

                            if Is_Duple == False:
                                if len(OhlcvList) < get_count:
                                    OhlcvList.append(OhlcvData)
                                    add_cnt += 1
                              
                                    date_str_end = OhlcvData['Date']
                


                    except Exception as e:
                        logger.error(f"E: {e}" )

            if add_cnt == 0:
                DataLoad = False
            else:
                date_str_start = Common.GetFromDateStr(pd.to_datetime(date_str_end),"NONE",-100) 

        else:
            logger.error(f"Error Code : " + str(res.status_code) + " | " + res.text)


            count += 1
            if count > 10:
                DataLoad = False

    if len(OhlcvList) > 0:
                            
        df = pd.DataFrame(OhlcvList)
        df = df.set_index('Date')

        df = df.sort_values(by="Date")
        df.insert(6,'change',(df['close'] - df['close'].shift(1)) / df['close'].shift(1))
            
        df[[ 'open', 'high', 'low', 'close', 'volume', 'change']] = df[[ 'open', 'high', 'low', 'close', 'volume', 'change']].apply(pd.to_numeric)


        df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')


        return df
    else:
        return None


#당일 분봉 조회!

def GetOhlcvMinute(stock_code, MinSt = '1T'):


    PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"


    get_count = 500
    
    OhlcvList = list()

    DataLoad = True
    
    count = 0
 
    # 현재 시간과 타임존 설정
    timezone_info = timezone('Asia/Seoul')
    now = datetime.now(timezone_info)

    # 원하는 형식으로 변환 (초는 00으로 설정)
    formatted_time = now.strftime("%H:%M") + ":00"

    # 문자열로 변환
    time_str = formatted_time.replace(":", "")
    

    while DataLoad:

        time.sleep(0.2)
        #모의계좌는 초당 2건만 허용하게 변경 - 24.04.01
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        logger.info(f"get.data... {len(OhlcvList)}-->{get_count}")
        #print("...Data.Length..", len(OhlcvList), "-->", get_count)
        if len(OhlcvList) >= get_count:
            DataLoad = False

        # 헤더 설정
        headers = {"Content-Type":"application/json", 
                "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
                "appKey":Common.GetAppKey(Common.GetNowDist()),
                "appSecret":Common.GetAppSecret(Common.GetNowDist()),
                "tr_id":"FHKST03010200"}

        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": time_str,
            "FID_PW_DATA_INCU_YN": "N"
        }
  
        # 호출
        res = requests.get(URL, headers=headers, params=params)

        #pprint.pprint(res.json())
        

        if res.status_code == 200 and res.json()["rt_cd"] == '0':

            ResultList = res.json()['output2']


            df = list()

            add_cnt = 0
            if len(pd.DataFrame(ResultList)) > 0:


                for ohlcv in ResultList:
                    
                    if len(ohlcv) == 0:
                        continue

                    OhlcvData = dict()

                    try:
                        if ohlcv['stck_oprc'] != "":
                            
                            OhlcvData['Date'] = ohlcv['stck_cntg_hour']
                            OhlcvData['open'] = float(ohlcv['stck_oprc'])
                            OhlcvData['high'] = float(ohlcv['stck_hgpr'])
                            OhlcvData['low'] = float(ohlcv['stck_lwpr'])
                            OhlcvData['close'] = float(ohlcv['stck_prpr'])
                            OhlcvData['volume'] = float(ohlcv['cntg_vol'])
                            OhlcvData['value'] = float(ohlcv['acml_tr_pbmn'])


                            Is_Duple = False
            
                            for exist_stock in OhlcvList:
                                if exist_stock['Date'] == OhlcvData['Date']:
                                    Is_Duple = True
                                    break

                            if Is_Duple == False:
                                if len(OhlcvList) < get_count:
                                    OhlcvList.append(OhlcvData)
                                    add_cnt += 1
                              
                                    time_str = str(OhlcvData['Date'])
                


                    except Exception as e:
                        # print("E:", e)
                        logger.error(f"E: {e}" )

            if add_cnt == 0:
                DataLoad = False
           
                

        else:
            #print("Error Code : " + str(res.status_code) + " | " + res.text)
            logger.error(f"Error Code : {res.status_code} | {res.text}")

            count += 1
            if count > 10:
                DataLoad = False


                            
             
    if len(OhlcvList) > 0:
                            
        df = pd.DataFrame(OhlcvList)
        df = df.set_index('Date')

        df = df.sort_values(by="Date")


        # 인덱스를 datetime 형식으로 변환
        df.index = pd.to_datetime(df.index, format='%H%M%S')

        timezone_info = timezone('Asia/Seoul')
        # 오늘 날짜 가져오기
        today_date = datetime.now(timezone_info).date()

        # 인덱스의 날짜 부분만 오늘 날짜로 업데이트
        df.index = df.index.map(lambda x: x.replace(year=today_date.year, month=today_date.month, day=today_date.day))

        
        if MinSt != '1T':
        
            df = df.resample(MinSt).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
                'value': 'sum'
            })
            
            
        df.insert(6,'change',(df['close'] - df['close'].shift(1)) / df['close'].shift(1))
            
        df[[ 'open', 'high', 'low', 'close', 'volume', 'change']] = df[[ 'open', 'high', 'low', 'close', 'volume', 'change']].apply(pd.to_numeric)


        return df
    else:
        return None

def GetStockOpenPrice(stock_code, get_count=1):
    """
    특정 주식의 최근 시가를 조회하는 함수
    
    Parameters:
    stock_code (str): 조회할 주식 종목 코드
    get_count (int): 가져올 데이터 개수 (기본값 1, 가장 최근 시가)
    
    Returns:
    DataFrame or None: 시가 데이터, 데이터를 가져오지 못하면 None 반환
    """
    try:
        # GetOhlcvNew 함수를 사용해 최근 데이터 조회
        df = GetOhlcvNew(stock_code, 'D', get_count)
        
        if df is not None and not df.empty:
            return df
        else:
            logger.info(f"종목 {stock_code}의 시가 데이터를 찾을 수 없습니다.")
            return None
    
    except Exception as e:
        logger.error(f"시가 조회 중 오류 발생: {e}")
        return None
    

#ETF의 NAV얻기
def GetETF_Nav(stock_code,Log = "N"):

    IsExcept = False
    Nav = 0

    #영상과 다르게 먼저 네이버 크롤링해서 먼저 NAV를 가지고 온다 -> 이게 장중 실시간 NAV를 더 잘 반영!
    try:


        url = "https://finance.naver.com/item/main.naver?code=" + stock_code
        dfs = pd.read_html(url,encoding='euc-kr')
        #logger.info(f"\n{pprint.pformat(dfs)}")

        data_dict = dfs[8]

        '''
        data_keys = list(data_dict.keys())
        for key in data_keys:
            logger.info("key:",key)
            logger.info("data_dict[key]:",data_dict[key])

            Second_Key = list(data_dict[key].keys())
            for secondkey in Second_Key:
                logger.info("secondkey:",secondkey)
                logger.info("data_dict[key][secondkey]:", data_dict[key][secondkey])
        '''

        Nav = int(data_dict[1][0])

        time.sleep(0.3)


    except Exception as e:
        logger.error(f"EX: {e}" )

        IsExcept = True

    
    #만약 실패한다면 pykrx를 이용해 NAV값을 가지고 온다
    if IsExcept == True:
        try:

                    
            df = stock.get_etf_price_deviation(Common.GetFromNowDateStr("KR","NONE", -5), Common.GetNowDateStr("KR"), stock_code)


            if Log == 'Y':
                logger.info(f"\n{pprint.pformat(df)}")

            if len(df) == 0:
                IsExcept = True

            Nav = df['NAV'].iloc[-1]
            logger.info(Nav)
            

        except Exception as e:
            logger.error(f"except!!!!!!!!")
            Nav = GetCurrentPrice(stock_code)

    return Nav

    
    


#ETF의 괴리율 구하기!
def GetETFGapAvg(stock_code, Log = "N"):

    GapAvg = 0
    IsExcept = False

    #pykrx 모듈 통해서 괴리율 평균을 구해옴!!!
    try:
        df = stock.get_etf_price_deviation(Common.GetFromNowDateStr("KR","NONE", -120), Common.GetNowDateStr("KR"), stock_code)
        if Log == 'Y':
            logger.info(f"\n{pprint.pformat(df)}")
        if len(df) == 0:
            IsExcept = True

        TotalGap = 0

        for idx, row in df.iterrows():
            
            Gap = abs(float(row['괴리율']))   

            TotalGap += Gap

        GapAvg = TotalGap/len(df)

            
        logger.info(f"GapAvg {GapAvg}")
        

    except Exception as e:
        IsExcept = True
        logger.error(f"ex {e}")

    #만약 실패한다면 네이버 직접 크롤링을 통해 가져옴!!!!
    if IsExcept == True:
        try:

                
            url = "https://finance.naver.com/item/main.naver?code=" + stock_code
            dfs = pd.read_html(url,encoding='euc-kr')

            data_dict = dfs[4]

            data_list = data_dict["괴리율"].to_list()

            count = 0
            TotalGap = 0
            for data in data_list:
                if "%" in str(data):
                    Gap = float(data.replace('%', ''))
                    TotalGap += Gap
                    count += 1

            GapAvg = TotalGap/count


        except Exception as e:
            logger.error(f"except!!!!!!!!")


    return GapAvg



######################## 추가 함수 ###########################

def GetStockList():
    """주식 종목 리스트를 가져오는 함수"""
    time.sleep(0.2)
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    # 헤더 설정
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appKey": Common.GetAppKey(Common.GetNowDist()),
        "appSecret": Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": "FHKST03010100"  # 주식시세/종목 조회 TR
    }

    stock_list = []
    markets = ["J", "Q"]  # J: KOSPI, Q: KOSDAQ

    for market in markets:
        params = {
            "FID_COND_MRKT_DIV_CODE": market,
            "FID_INPUT_ISCD": "005930",  # 삼성전자 종목코드로 시작
            "FID_PERIOD_DIV_CODE": "D",  # 일봉 기준
            "FID_ORG_ADJ_PRC": "1",      # 수정주가 여부
        }

        try:
            # API 호출
            res = requests.get(URL, headers=headers, params=params)
            logger.info(f"Response status: {res.status_code}")
            logger.info(f"Response content: {res.text}")
            
            if res.status_code == 200 and res.json()["rt_cd"] == '0':
                output = res.json().get('output1', [])  # output1에 주식 정보가 있음
                for item in output:
                    stock_info = {
                        "단축코드": params["FID_INPUT_ISCD"],
                        "한글명": item.get("hts_kor_isnm", ""),
                        "시장구분": "KOSPI" if market == "J" else "KOSDAQ",
                        "업종명": "",  # 이 API에서는 업종명을 제공하지 않음
                        "시가총액": str(float(item.get("stck_prpr", "0")) * float(item.get("list_shrs", "0")))
                    }
                    stock_list.append(stock_info)
            else:
                logger.error(f"Error Code : {res.status_code} | {res.text}")
                logger.error(f"URL: {URL}")
                logger.error(f"Headers: {headers}")
                logger.error(f"Params: {params}")

        except Exception as e:
            logger.error(f"Error processing market {market}: {str(e)}")
            continue

    return stock_list

######################## 추가 함수 끝###########################


def get_stock_info_with_retry(code, market_type, max_retries=3):
    """
    단일 종목의 정보를 가져오는 함수 (재시도 로직 포함)
    
    Parameters:
    code (str): 종목 코드
    market_type (str): 시장 구분 ("KOSPI" 또는 "KOSDAQ")
    max_retries (int): 최대 재시도 횟수
    """
    for attempt in range(max_retries):
        try:
            time.sleep(0.5)  # API 호출 간격 증가
            if Common.GetNowDist() == "VIRTUAL":
                time.sleep(0.7)  # 모의계좌는 더 긴 대기시간 적용

            PATH = "uapi/domestic-stock/v1/quotations/inquire-price"
            URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
            
            headers = {
                "Content-Type": "application/json",
                "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
                "appKey": Common.GetAppKey(Common.GetNowDist()),
                "appSecret": Common.GetAppSecret(Common.GetNowDist()),
                "tr_id": "FHKST01010100"
            }
            
            params = {
                "FID_COND_MRKT_DIV_CODE": "J" if market_type == "KOSPI" else "Q",
                "FID_INPUT_ISCD": code
            }
            
            res = requests.get(URL, headers=headers, params=params)
            
            if res.status_code == 200 and res.json()["rt_cd"] == '0':
                return res.json()['output']
                
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 점진적으로 대기시간 증가
                logger.error(f"Attempt {attempt + 1} failed for {code}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to get data for {code} after {max_retries} attempts: {str(e)}")
                return None
    
    return None

def get_filtered_stock_codes(today, min_market_cap=50000000000, min_volume=100000):
    """
    시가총액과 거래량으로 1차 필터링된 종목 코드 리스트를 반환
    
    Parameters:
    today (str): 날짜 문자열 (YYYYMMDD)
    min_market_cap (int): 최소 시가총액 (기본값: 500억)
    min_volume (int): 최소 거래량 (기본값: 10만주)
    """
    from pykrx import stock
    filtered_codes = []
    
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            # 시가총액 정보 가져오기
            market_cap_df = stock.get_market_cap(today, market=market)
            
            # 거래량 정보 가져오기
            volume_df = stock.get_market_ohlcv(today, market=market)
            
            # 조건에 맞는 종목만 필터링
            for code in market_cap_df.index:
                try:
                    market_cap = market_cap_df.loc[code, '시가총액']
                    volume = volume_df.loc[code, '거래량'] if code in volume_df.index else 0
                    
                    if market_cap >= min_market_cap and volume >= min_volume:
                        filtered_codes.append((code, market))
                except Exception as e:
                    logger.error(f"Error filtering stock {code}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error processing market {market}: {str(e)}")
            continue
    
    return filtered_codes


def is_tradable_stock(status_code):
    """
    주식 상태 코드가 거래 가능한 상태인지 확인
    
    Args:
        status_code (str): StockNowStatus 코드
        
    Returns:
        bool: 거래 가능 여부
    """
    # 거래 불가능한 상태 코드들
    non_tradable_codes = {'51', '52', '53', '54', '58', '59'}
    
    return status_code not in non_tradable_codes

def process_stock(code, stock_data):
    """단일 종목 처리 함수"""
    try:
        time.sleep(0.15)  # API 호출 간격 조정
        status = GetCurrentStatus(code)
        
        if not is_tradable_stock(status['StockNowStatus']):
            return None
            
        return {
            'code': code,
            'name': GetStockName(code),
            'market': stock_data['market'],
            'market_cap': float(stock_data['시가총액']),
            'current_price': int(stock_data['종가']),
            'trading_volume': int(stock_data['거래량']),
            'status': status['StockNowStatus']
        }
    except Exception as e:
        logger.error(f"Error processing stock {code}: {str(e)}")
        return None



def get_institution_foreign_trading_info():
    """국내 기관 및 외국인 매매 종목 가집계 정보를 조회하는 함수"""
    time.sleep(0.2)
    
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/quotations/foreign-institution-total"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appkey": Common.GetAppKey(Common.GetNowDist()),
        "appsecret": Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": "FHPTJ04400000"
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "V",
        "FID_COND_SCR_DIV_CODE": "16449",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "0",
        "FID_RANK_SORT_CLS_CODE": "0",
        "FID_ETC_CLS_CODE": "0"
    }

    response = requests.get(URL, headers=headers, params=params)

    if response.status_code == 200 and response.json()["rt_cd"] == '0':
        return response.json()['output']
    else:
        logger.error(f"Error Code : " + str(response.status_code) + " | " + response.text)
        return None



# 전역 캐시 변수 추가
after_market_cache = {}  # {ticker: {'data': {...}, 'timestamp': time.time()}}
CACHE_EXPIRY = 600  # 10분(600초) 캐시 유효시간

def check_after_market_data(ticker):
    """시간외 거래 데이터 분석 - 캐싱 기능 추가"""
    try:
        global after_market_cache
        current_time = time.time()
        
        # 캐시 확인
        if ticker in after_market_cache:
            cache_data = after_market_cache[ticker]
            # 캐시 만료 시간 체크 (5분)
            if current_time - cache_data['timestamp'] < CACHE_EXPIRY:
                # logger.info(f"{ticker}: 시간외 데이터 캐시 사용 (남은 시간: {int(CACHE_EXPIRY - (current_time - cache_data['timestamp']))}초)")
                return cache_data['data']  # 캐시된 데이터 반환
        
        # 현재 시간 확인
        now = datetime.now()
        
        # 오전 9시 10분 이전에는 시간외 데이터 조회 스킵 (의미 없는 데이터 방지)
        if now.hour == 9 and now.minute < 10:
            return None
            
        time.sleep(0.2)
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        PATH = "uapi/domestic-stock/v1/quotations/inquire-daily-overtimeprice"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey": Common.GetAppKey(Common.GetNowDist()),
            "appSecret": Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": "FHPST02320000",
            "custtype": "P"
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker
        }
        
        res = requests.get(URL, headers=headers, params=params)
        
        if res.status_code == 200 and res.json()["rt_cd"] == '0':
            current_data = res.json().get('output1', {})
            if not current_data:
                return None
                
            # 데이터 파싱
            after_market_info = {
                'current_price': float(current_data.get('ovtm_untp_prpr', 0)),      # 시간외 현재가
                'price_change': float(current_data.get('ovtm_untp_prdy_vrss', 0)),  # 시간외 전일대비
                'change_rate': float(current_data.get('ovtm_untp_prdy_ctrt', 0)),   # 시간외 등락률
                'volume': float(current_data.get('ovtm_untp_vol', 0)),              # 시간외 거래량
                'value': float(current_data.get('ovtm_untp_tr_pbmn', 0))           # 시간외 거래대금
            }
            
            # 등락률이 양수이고 유의미한 거래량이 있는 경우만 반환
            if after_market_info['change_rate'] <= 0 or after_market_info['volume'] < 1000:
                # 캐시에 None 저장 (불필요한 재요청 방지)
                after_market_cache[ticker] = {
                    'data': None,
                    'timestamp': current_time
                }
                return None
                
            logger.info(f"시간외 거래 데이터 조회 성공: {ticker}")
            logger.info(f"- 시간외 현재가: {after_market_info['current_price']:,.0f}")
            logger.info(f"- 시간외 거래량: {after_market_info['volume']:,.0f}")
            logger.info(f"- 시간외 등락률: {after_market_info['change_rate']:.2f}%")
            
            # 캐시에 결과 저장
            after_market_cache[ticker] = {
                'data': after_market_info,
                'timestamp': current_time
            }
            
            return after_market_info
            
    except Exception as e:
        logger.error(f"시간외 거래 조회 중 오류: {str(e)}")
        return None



def GetMarketCodeList(price_limit=150000, min_market_cap=5000 * 100000000, min_volume=100000, max_stocks=30, is_morning_session=False, is_early_morning=False):
    logger.info(f"Starting market scan...")
    start_time = time.time()
    stock_list = []
    today = datetime.now().strftime("%Y%m%d")
    
    try:
        # 시간대별 완화된 기준 적용
        if is_early_morning:
            min_market_cap = min_market_cap * 0.4  # 40%로 완화
            min_volume = min_volume * 0.5      # 50%로 완화
        elif is_morning_session:
            min_market_cap = min_market_cap * 0.6  # 60%로 완화
            min_volume = min_volume * 0.7      # 70%로 완화
        
        logger.info(f"\n=== 시간대별 우선순위 ===")
        if is_morning_session:
            logger.info(f"오전장: 거래량 급증/가격 상승률 우선")
        else:
            logger.info(f"일반시간대: 시가총액/거래량 기준")
        
        momentum_stocks = {}
        
        for market in ["KOSPI", "KOSDAQ"]:
            try:
                df = stock.get_market_ohlcv(today, market=market)
                df_cap = stock.get_market_cap(today, market=market)
                
                filtered_df = df[
                    (df['종가'] <= price_limit) & 
                    (df['거래량'] >= min_volume)
                ].join(df_cap[['시가총액']])

                filtered_df = filtered_df[filtered_df['시가총액'] >= min_market_cap]

                # 모든 필터링된 종목 처리
                for code in filtered_df.index:
                    try:
                        # 0으로 나누기 방지
                        volume_ma5 = df['거래량'].rolling(window=5, min_periods=1).mean().loc[code]
                        
                        # current_volume 대신 직접 filtered_df 사용
                        volume_ratio = (filtered_df.loc[code, '거래량'] / volume_ma5) if volume_ma5 > 0 else 1.0
                        
                        current_price = float(filtered_df.loc[code, '종가'])
                        volume = float(filtered_df.loc[code, '거래량'])  # current_volume 대신 volume 사용
                        market_cap = float(filtered_df.loc[code, '시가총액'])
                        open_price = float(df.loc[code, '시가'])
                        
                        # 가격 변동률 계산 (0으로 나누기 방지)
                        price_change = ((current_price - open_price) / max(open_price, 0.0001)) * 100
                        
                        stock_data = {
                            'market': market,
                            '시가총액': market_cap,
                            '종가': current_price,
                            '거래량': volume,
                            'volume_ratio': volume_ratio,
                            'price_change': price_change
                        }
                        
                        # 오전장이면서 거래량이 일정 이상, 가격 변동이 있는 종목만 시간외 데이터 조회
                        # 개선: 모든 종목이 아닌 조건에 맞는 종목만 시간외 데이터 조회
                        if (is_morning_session and 
                            volume_ratio > 1.2 and  # 거래량 증가가 있는 종목만
                            abs(price_change) > 0.5):  # 가격 변동이 있는 종목만
                            after_market = check_after_market_data(code)
                            if after_market:
                                stock_data['after_market'] = after_market
                                
                        momentum_stocks[code] = stock_data
                        
                    except Exception as e:
                        logger.error(f"Error processing stock {code}: {str(e)}")
                        
            except Exception as e:
                logger.error(f"Error processing market {market}: {str(e)}")
        
        # 시간대별 다른 정렬 기준 적용
        if is_morning_session:
            sorted_stocks = sorted(momentum_stocks.items(), 
                key=lambda x: (
                    x[1]['price_change'],  # 당일 상승률 우선
                    x[1]['volume_ratio'],  # 거래량 증가율
                    # 개선: after_market 데이터가 있는 경우에만 사용
                    x[1].get('after_market', {}).get('change_rate', 0) if x[1].get('after_market') else 0,
                    x[1].get('after_market', {}).get('volume', 0) if x[1].get('after_market') else 0
                ), 
                reverse=True
            )
        else:
            sorted_stocks = sorted(momentum_stocks.items(), 
                key=lambda x: (
                    x[1]['volume_ratio'],  # 거래량 비율 우선
                    x[1]['price_change'],  # 가격 변동률
                    x[1]['시가총액']       # 시가총액
                ), 
                reverse=True
            )
        
        # 상위 종목 처리
        for code, stock_data in sorted_stocks[:max_stocks]:
            try:
                status = GetCurrentStatus(code)
                
                if status:
                    stock_info = {
                        'code': code,
                        'name': status['StockName'],
                        'current_price': stock_data['종가'],
                        'market_cap': stock_data['시가총액'],
                        'volume': stock_data['거래량'],
                        'price_change': stock_data['price_change'],
                        'volume_ratio': stock_data['volume_ratio']
                    }
                    
                    if is_morning_session and 'after_market' in stock_data:
                        stock_info['after_market_data'] = stock_data['after_market']
                    
                    stock_list.append(stock_info)
                    
                    # 시간대별 다른 로깅
                    logger.info(f"\n추가된 종목: {stock_info['name']} ({code})")
                    logger.info(f"시가총액: {stock_info['market_cap']/100000000:.0f}억원")
                    logger.info(f"거래량: {stock_info['volume']:,}주")
                    logger.info(f"거래량 증가율: {stock_info['volume_ratio']:.1f}배")
                    logger.info(f"가격 변동률: {stock_data['price_change']:.2f}%")
                    
                    if is_morning_session and 'after_market_data' in stock_info:
                        logger.info(f"시간외 등락률: {stock_info['after_market_data']['change_rate']:.2f}%")
                        logger.info(f"시간외 거래량: {stock_info['after_market_data']['volume']:,}주")
                    
            except Exception as e:
                logger.error(f"Error processing {code}: {str(e)}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"\n=== 스캔 완료 ({len(stock_list)}종목) ===")
        logger.info(f"소요시간: {elapsed_time:.1f}초")
        
    except Exception as e:
        logger.error(f"Critical error in market scan: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return stock_list



def GetOrderBook(stock_code, depth=5, debug=False):
    """
    주식 호가 정보 조회 함수
    
    Args:
        stock_code (str): 종목 코드 (6자리)
        depth (int): 호가 깊이 (최대 10단계)
        debug (bool): 디버그 모드 여부
    
    Returns:
        dict: 호가 정보를 포함한 딕셔너리 또는 None (에러 시)
    """
    try:
        time.sleep(0.2)
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        PATH = "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}{PATH}"

        headers = {
            "Content-Type": "application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey": Common.GetAppKey(Common.GetNowDist()),
            "appSecret": Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": "FHKST01010200",
            "custtype": "P"
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }

        res = requests.get(URL, headers=headers, params=params)
        
        if debug:
            logger.info(f"API 응답 전문:")
            logger.info(json.dumps(res.json(), indent=2, ensure_ascii=False))
        
        if res.status_code == 200 and res.json()["rt_cd"] == '0':
            data = res.json()['output1']
            
            # 모든 매수/매도 호가 건수 합산
            ask_cnt_total = sum(int(data.get(f'askp_cnt{i}', 0)) for i in range(1, 11))
            bid_cnt_total = sum(int(data.get(f'bidp_cnt{i}', 0)) for i in range(1, 11))
            
            orderbook = {
                'total_ask_cnt': ask_cnt_total,
                'total_bid_cnt': bid_cnt_total,
                'total_ask_rem': sum(int(data.get(f'askp_rsqn{i}', 0)) for i in range(1, 11)),
                'total_bid_rem': sum(int(data.get(f'bidp_rsqn{i}', 0)) for i in range(1, 11)),
                'levels': []
            }

            depth = min(depth, 10)
            for i in range(1, depth + 1):
                ask_price = float(data.get(f'askp{i}', 0))
                bid_price = float(data.get(f'bidp{i}', 0))
                ask_volume = int(data.get(f'askp_rsqn{i}', 0))
                bid_volume = int(data.get(f'bidp_rsqn{i}', 0))
                
                if ask_price == 0 and bid_price == 0:
                    continue
                    
                level = {
                    'ask_price': ask_price,
                    'ask_volume': ask_volume,
                    'bid_price': bid_price,
                    'bid_volume': bid_volume,
                    'ask_cnt': int(data.get(f'askp_cnt{i}', 0)),
                    'bid_cnt': int(data.get(f'bidp_cnt{i}', 0))
                }
                
                orderbook['levels'].append(level)

            return orderbook
            
        else:
            error_msg = f"호가 조회 실패: {res.status_code}"
            if debug:
                error_msg += f"\n에러 메시지: {res.text}"
            logger.error(error_msg)
            return None

    except Exception as e:
        error_msg = f"호가 조회 중 예외 발생: {str(e)}"
        if debug:
            import traceback
            error_msg += f"\n{traceback.format_exc()}"
        logger.error(error_msg)
        return None


def get_stock_info_by_code(stock_code):
    """종목코드로 종목 상세 정보를 조회하는 함수"""
    time.sleep(0.2)
    
    if Common.GetNowDist() == "VIRTUAL":
        time.sleep(0.31)

    PATH = "uapi/domestic-stock/v1/quotations/search-stock-info"
    URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
        "appkey": Common.GetAppKey(Common.GetNowDist()),
        "appsecret": Common.GetAppSecret(Common.GetNowDist()),
        "tr_id": "CTPF1002R",
        "custtype": "P"
    }

    params = {
        "PDNO": f"{stock_code}",
        "PRDT_TYPE_CD": "300"
    }

    response = requests.get(URL, headers=headers, params=params)

    if response.status_code == 200 and response.json()["rt_cd"] == '0':
        return response.json()['output']
    else:
        logger.error(f"Error Code : " + str(response.status_code) + " | " + response.text)
        return None

def get_sector_info(stock_code):
    """종목의 섹터(업종) 정보를 조회하는 함수"""
    try:
        stock_info = get_stock_info_by_code(stock_code)
        if stock_info:
            # 업종 정보
            sector = stock_info.get('idx_bztp_mcls_cd_name', 'Unknown')  # 중분류 업종
            detail_sector = stock_info.get('std_idst_clsf_cd_name', '')  # 세부 업종
            
            # 시장 구분 (STK: KOSPI, KSQ: KOSDAQ)
            market = 'KOSPI' if stock_info.get('mket_id_cd') == 'STK' else 'KOSDAQ'
            
            return {
                'sector': sector,
                'detail_sector': detail_sector,
                'market': market
            }
        
        return {
            'sector': 'Unknown',
            'detail_sector': '',
            'market': 'Unknown'
        }
        
    except Exception as e:
        logger.error(f"섹터 정보 조회 중 에러: {str(e)}")
        return {
            'sector': 'Unknown',
            'detail_sector': '',
            'market': 'Unknown'
        }


def GetVolumeRank(market_code="J", vol_type="20171", top_n=30, max_price=150000):
    """
    거래량 순위 종목 조회 함수
    
    Args:
        market_code (str): 시장 구분 코드 (J:코스피, U:코스닥)
        vol_type (str): 거래량 기준 (20171:거래량, 20172:거래대금)
        top_n (int): 가져올 종목 수
        max_price (int): 최대 주가 제한 (기본값: 150000)
        
    Returns:
        list: 거래량 상위 종목 리스트
    """
    try:
        time.sleep(0.2)
        if Common.GetNowDist() == "VIRTUAL":
            time.sleep(0.31)

        PATH = "uapi/domestic-stock/v1/quotations/volume-rank"
        URL = f"{Common.GetUrlBase(Common.GetNowDist())}/{PATH}"
        
        # 헤더 설정
        headers = {
            "Content-Type": "application/json", 
            "authorization": f"Bearer {Common.GetToken(Common.GetNowDist())}",
            "appKey": Common.GetAppKey(Common.GetNowDist()),
            "appSecret": Common.GetAppSecret(Common.GetNowDist()),
            "tr_id": "FHPST01710000",
            "custtype": "P"
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": market_code,     # J: 주식
            "FID_COND_SCR_DIV_CODE": vol_type,         # 20171: 거래량, 20172: 거래대금
            "FID_INPUT_ISCD": "0000",                  # 0000: 전체
            "FID_DIV_CLS_CODE": "0",                   # 0: 전체
            "FID_BLNG_CLS_CODE": "0",                  # 0: 전체
            "FID_TRGT_CLS_CODE": "111111111",          # 111111111: 전체
            "FID_TRGT_EXLS_CLS_CODE": "000000",        # 000000: 제외 없음
            "FID_INPUT_PRICE_1": "0",                  # 0: 가격조건 없음
            "FID_INPUT_PRICE_2": "0",                  # 0: 가격조건 없음
            "FID_VOL_CNT": "0",                        # 0: 거래량 조건 없음
            "FID_INPUT_DATE_1": "0"                    # 0: 당일
        }
        
        # API 호출
        res = requests.get(URL, headers=headers, params=params)
        
        if res.status_code == 200 and res.json()["rt_cd"] == '0':
            result_list = res.json().get('output', [])
            
            logger.info(f"거래량 순위 API 조회 성공 - {len(result_list)}개 종목")
            
            volume_rank_stocks = []
            for item in result_list:
                # 현재가 가져오기
                price = float(item.get('stck_prpr', 0))
                
                # 최대 주가 제한 적용
                if price <= max_price:
                    # 필요한 데이터만 추출
                    stock_info = {
                        'code': item.get('mksc_shrn_iscd', ''),
                        'name': item.get('hts_kor_isnm', ''),
                        'price': price,
                        'change_rate': float(item.get('prdy_ctrt', 0)),
                        'volume': int(item.get('acml_vol', 0)),
                        'volume_ratio': float(item.get('vol_inrt', 0)),  # 전일대비 거래량 비율
                        'market': "코스피" if market_code == "J" else "코스닥"
                    }
                    volume_rank_stocks.append(stock_info)
            
            # 상위 top_n개 종목만 반환
            return volume_rank_stocks[:top_n]
            
        else:
            logger.error(f"거래량 순위 조회 실패: {res.status_code} | {res.text}")
            return []
        
    except Exception as e:
        logger.error(f"거래량 순위 조회 중 오류: {str(e)}")
        return []

def GetInvestorDailyByCode(stock_code, from_date, to_date):
    """pykrx를 사용한 투자자별 일별 매매동향 조회"""
    try:
        df = stock.get_market_trading_value_by_date(
            fromdate=from_date,
            todate=to_date,
            ticker=stock_code
        )
        
        if df.empty:
            return None
        
        # 현재가 조회
        current_price = GetCurrentPrice(stock_code)
        if current_price <= 0:
            current_price = 50000  # 기본값
        
        result = []
        for date, row in df.iterrows():
            date_str = date.strftime('%Y%m%d')
            foreign_won = row['외국인합계']
            institution_won = row['기관합계']
            
            result.append({
                'stck_bsop_date': date_str,
                'frgn_ntby_qty': int(foreign_won / current_price),
                'orgn_ntby_qty': int(institution_won / current_price)
            })
        
        return result
        
    except Exception as e:
        logger.error(f"GetInvestorDailyByCode 오류: {str(e)}")
        return None

#계좌 잔고를 가지고 온다!
#Balance = GetBalance()
#Common.GetPrdtNo(Common.GetNowDist())

#Common.GetNowDist()

# logger.info("--------------내 보유 잔고---------------------")

#logger.info(f"\n{pprint.pformat(Balance)}")

# logger.info("--------------------------------------------")