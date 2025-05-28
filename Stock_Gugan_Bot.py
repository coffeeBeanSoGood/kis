#-*-coding:utf-8 -*-
'''

관련 포스팅

https://blog.naver.com/zacra/223240069613

위 포스팅을 꼭 참고하세요!!!

하다가 잘 안되시면 계속 내용이 추가되고 있는 아래 FAQ를 꼭꼭 체크하시고

주식/코인 자동매매 FAQ
https://blog.naver.com/zacra/223203988739

그래도 안 된다면 구글링 해보시고
그래도 모르겠다면 클래스 댓글, 블로그 댓글, 단톡방( https://blog.naver.com/zacra/223111402375 )에 질문주세요! ^^


'''

import KIS_Common as Common
import KIS_API_Helper_US as KisUS

import time
import pprint

import json

import line_alert

#계좌 선택.. "VIRTUAL" 는 모의 계좌!
Common.SetChangeMode("VIRTUAL") #REAL or VIRTUAL


#시간 정보를 읽는다
time_info = time.gmtime()
day_n = time_info.tm_mday

BOT_NAME = Common.GetNowDist() + "_Gugan_Stock_Bot"

#포트폴리오 이름
PortfolioName = "구간전략!"


#마켓이 열렸는지 여부~!
IsMarketOpen = KisUS.IsMarketOpen()


#계좌 잔고를 가지고 온다!
Balance = KisUS.GetBalance()


print("--------------내 보유 잔고---------------------")

pprint.pprint(Balance)

######################################################################
######################################################################
print("--------------------------------------------")
#총 평가금액에서 해당 봇에게 할당할 총 금액비율 1.0 = 100%  0.5 = 50%
InvestRate = 0.5

DivNum = 15 #구간분할!
target_period = 20 #이 기간의 값의 변동으로 구간을 삼는다!


###투자할 종목!
InvestStockList = ["TSLA"]
######################################################################
######################################################################


#기준이 되는 내 총 평가금액에서 투자비중을 곱해서 나온 포트폴리오에 할당된 돈!!
InvestTotalMoney = float(Balance['TotalMoney']) * InvestRate

print("총 포트폴리오에 할당된 투자 가능 금액 : ", InvestTotalMoney)



#현재 구간 정보를 저장
GuganCoinInfoDict = dict()

#파일 경로입니다.
gugan_file_path = "/var/autobot/" + BOT_NAME + "Status.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(gugan_file_path, 'r') as json_file:
        GuganCoinInfoDict = json.load(json_file)

except Exception as e:
    #처음에는 파일이 존재하지 않을테니깐 당연히 예외처리가 됩니다!
    print("Exception by First")



#투자가 시작되었는지 여부
GuganStartCoinInfoDict = dict()

#파일 경로입니다.
startflag_file_path = "/var/autobot/" + BOT_NAME + "StargFlag.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(startflag_file_path, 'r') as json_file:
        GuganStartCoinInfoDict = json.load(json_file)

except Exception as e:
    #처음에는 파일이 존재하지 않을테니깐 당연히 예외처리가 됩니다!
    print("Exception by First")



#오늘 로직이 진행되었는지 날짜 저장 관리 하는 파일
DateDateTodayDict = dict()

#파일 경로입니다.
today_file_path = "/var/autobot/" + BOT_NAME + "InvestToday.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(today_file_path, 'r') as json_file:
        DateDateTodayDict = json.load(json_file)

except Exception as e:
    #처음에는 파일이 존재하지 않을테니깐 당연히 예외처리가 됩니다!
    print("Init..")
    
    #0으로 초기화!!!!!
    DateDateTodayDict['date'] = 0
    #파일에 저장
    with open(today_file_path, 'w') as outfile:
        json.dump(DateDateTodayDict, outfile)




##########################################################

print("--------------내 보유 주식---------------------")
#그리고 현재 이 계좌에서 보유한 주식 리스트를 가지고 옵니다!
MyStockList = KisUS.GetMyStockList()
pprint.pprint(MyStockList)
print("--------------------------------------------")
##########################################################

if IsMarketOpen == True:



    #매도 체크 날짜가 다르다면 맨 처음이거나 날이 바뀐것이다!!
    if DateDateTodayDict['date'] != day_n:




        for stock_code in InvestStockList:    

            InvestMoney = InvestTotalMoney / len(InvestStockList) #테스트 총 금액을 종목 수로 나눠서 각 할당 투자금을 계산한다!

            print(stock_code, " 종목당 할당 투자금:", InvestMoney)



            stock_name = ""
            stock_amt = 0 #수량
            stock_avg_price = 0 #평단
            stock_eval_totalmoney = 0 #총평가금액!
            stock_revenue_rate = 0 #종목 수익률
            stock_revenue_money = 0 #종목 수익금



            #내가 보유한 주식 리스트에서 매수된 잔고 정보를 가져온다
            for my_stock in MyStockList:
                if my_stock['StockCode'] == stock_code:
                    stock_name = my_stock['StockName']
                    stock_amt = int(my_stock['StockAmt'])
                    stock_avg_price = float(my_stock['StockAvgPrice'])
                    stock_eval_totalmoney = float(my_stock['StockNowMoney'])
                    stock_revenue_rate = float(my_stock['StockRevenueRate'])
                    stock_revenue_money = float(my_stock['StockRevenueMoney'])

                    break



            #분할된 가격!
            InvestMoneyCell = InvestMoney / DivNum
            print("InvestMoneyCell", InvestMoneyCell)


            df_day = Common.GetOhlcv("US", stock_code,200) 

            Ma5 = Common.GetMA(df_day,5,-2)   #전일 종가 기준 5일 이동평균선
            Ma20 = Common.GetMA(df_day,20,-2) #전일 종가 기준 20일 이동평균선

            CurrentPrice = KisUS.GetCurrentPrice(stock_code)

            #구간을 구하는 코드..
            high_list = list()
            low_list = list()

            for index in range(2,(target_period+2)):
                high_list.append(df_day['high'].iloc[-index])
                low_list.append(df_day['low'].iloc[-index])

            high_price = float(max(high_list))
            low_price =  float(min(low_list))

            Gap = (high_price - low_price) / DivNum

            now_step = DivNum 
            
            for step in range(1,DivNum+1):
                if CurrentPrice < low_price + (Gap * step):
                    now_step = step
                    break

            #현재 구간!
            print("-----------------",now_step,"-------------------\n")

            #딕셔너리에 구간 값이 없는 즉 봇 처음 실행하는 시점이라면 현재 구간을 저장해 둔다!!!
            if GuganCoinInfoDict.get(stock_code) == None:
                GuganCoinInfoDict[stock_code] = now_step
                #파일에 리스트를 저장합니다
                with open(gugan_file_path, 'w') as outfile:
                    json.dump(GuganCoinInfoDict, outfile)


            if GuganStartCoinInfoDict.get(stock_code) == None:
                if stock_amt > 0:
                    GuganStartCoinInfoDict[stock_code] = True
                else:
                    GuganStartCoinInfoDict[stock_code] = False
                #파일에 리스트를 저장합니다
                with open(startflag_file_path, 'w') as outfile:
                    json.dump(GuganStartCoinInfoDict, outfile)



            #잔고가 있거나 이 전략으로 스타트된 경우!!
            if stock_amt > 0 or GuganStartCoinInfoDict[stock_code] == True: 
                print("잔고가 있는 경우!")
                
                NowRealStockMoney = 0

                if stock_amt > 0 :
                    NowRealStockMoney = stock_eval_totalmoney
                    

                RemainMoney = InvestMoney - NowRealStockMoney

                AllAmt = 0
                if stock_amt > 0:
                    AllAmt = stock_amt #현재 수량
                    
                    
                print("현재 수량 :", AllAmt)
                print("현재 평가금 :", NowRealStockMoney, "남은 현금:", RemainMoney ," 10분할금 : ", InvestMoneyCell)


                #스텝(구간)이 다르다!
                if GuganCoinInfoDict[stock_code] != now_step:
                    print("")

                    step_gap = now_step - GuganCoinInfoDict[stock_code] #구간 갮을 구함!


                    GuganCoinInfoDict[stock_code] = now_step
                    #파일에 리스트를 저장합니다
                    with open(gugan_file_path, 'w') as outfile:
                        json.dump(GuganCoinInfoDict, outfile)


                    if step_gap >= 1: #스텝이 증가!! 매수!!

                        if Ma20 < df_day['close'].iloc[-2]:

                            #남은 현금이 있을 때만 
                            if RemainMoney >= InvestMoneyCell*abs(step_gap):

                                #10분할된 금액에 스텝 증가분을 곱해서 매수한다!
                                BuyMoney = InvestMoneyCell*abs(step_gap)

                                #매수할 수량을 계산한다!
                                BuyAmt = int(BuyMoney / CurrentPrice)
                                CurrentPrice *= 1.01
                                pprint.pprint(KisUS.MakeBuyLimitOrder(stock_code,BuyAmt,CurrentPrice))
                

                                msg = PortfolioName + " " + stock_code + " 구간이 증가되었어요! 그래서 매수했어요! ^^ " + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                                print(msg)
                                line_alert.SendMessage(msg)
                            else:
                                msg = PortfolioName + " " + stock_code + " 구간이 증가되어 매수해야되지만 그만한 할당 현금이 없어 하지 않았어요! ^^" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                                print(msg)
                                line_alert.SendMessage(msg)
                        else:
                            msg = PortfolioName + " " + stock_code + " 구간이 증가되어 매수해야되지만 이평선 조건을 만족하지 않아 하지 않았어요! ^^" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                            print(msg)
                            line_alert.SendMessage(msg)


                    elif step_gap <= -1: #스텝이 감소! 매도!!
                        
                        if stock_amt > 0 :

                            if Ma5 > df_day['close'].iloc[-2]:

                                SellAmt = int(InvestMoneyCell*abs(step_gap) / CurrentPrice) #매도 가능 수량을 구한다!


                                if AllAmt >= SellAmt:

                                    

                                    CurrentPrice *= 0.99
                                    pprint.pprint(KisUS.MakeSellLimitOrder(stock_code,abs(SellAmt),CurrentPrice))

                                    msg = PortfolioName + " " + stock_code + " 구간이 감소되었어요! 그래서 매도했어요! ^^" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                                    print(msg)
                                    line_alert.SendMessage(msg)

                                else:
                                    
                                    CurrentPrice *= 0.99
                                    pprint.pprint(KisUS.MakeSellLimitOrder(stock_code,abs(stock_amt),CurrentPrice))
                                                                                    
                                    msg = PortfolioName + " " + stock_code + " 구간이 감소되어 모두 매도처리 했어요!!" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                                    print(msg)
                                    line_alert.SendMessage(msg)

                            else:
                                msg = PortfolioName + " " + stock_code + " 구간이 감소되어 매도해야되지만 이평선 조건을 만족하지 않아 하지 않았어요! ^^" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                                print(msg)
                                line_alert.SendMessage(msg)
                        else:

                            msg = PortfolioName + " " + stock_code + " 구간이 감소되어 매도해야되지만 보유 잔고가 없어요! ^^" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                            print(msg)
                            line_alert.SendMessage(msg)
                    


                revenue_data = 0
                
                if stock_amt > 0:
                    #수익금과 수익률을 구한다!

                    msg = PortfolioName + " " + stock_code + "현재 수익률 : 약 " + str(round(stock_revenue_rate,2)) + "% 수익금 : 약" + str(format(round(stock_revenue_money), ',')) + "" + " 현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                    print(msg)
                    line_alert.SendMessage(msg)

                else:
                    msg = PortfolioName + " " + stock_code + "현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                    print(msg)
                    line_alert.SendMessage(msg)



            else:
                print("잔고없음")

                GuganCoinInfoDict[stock_code] = now_step
                #파일에 리스트를 저장합니다
                with open(gugan_file_path, 'w') as outfile:
                    json.dump(GuganCoinInfoDict, outfile)


                #10분할된 금액에 스텝 증가분을 곱해서 매수한다!
                BuyMoney = InvestMoneyCell

                #매수할 수량을 계산한다!
                BuyAmt = int(BuyMoney / CurrentPrice)
                CurrentPrice *= 1.01
                pprint.pprint(KisUS.MakeBuyLimitOrder(stock_code,BuyAmt,CurrentPrice))

                msg = PortfolioName + " " + stock_code + "장기 구간 분할 투자 봇 작동 개시!! : " + "현재 " + str(GuganCoinInfoDict[stock_code]) + "구간"
                print(msg)
                line_alert.SendMessage(msg)
                
                GuganStartCoinInfoDict[stock_code] = True
                #파일에 리스트를 저장합니다
                with open(startflag_file_path, 'w') as outfile:
                    json.dump(GuganStartCoinInfoDict, outfile)

        #체크 날짜가 다르다면 맨 처음이거나 날이 바뀐것이다!!
        DateDateTodayDict['date'] = day_n
        #파일에 저장
        with open(today_file_path, 'w') as outfile:
            json.dump(DateDateTodayDict, outfile)



        msg = PortfolioName + " 오늘 로직 끝!!"
        print(msg)
        line_alert.SendMessage(msg)

    else:
        print(PortfolioName + " 오늘 로직 이미 실행됨!")



else:
    print(PortfolioName + " 장이 열려있지 않아요!")











