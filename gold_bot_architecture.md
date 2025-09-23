# 🥇 스마트 골드 트레이딩 봇 아키텍처 설계서

## 🏗️ **전체 시스템 아키텍처**

```
┌─────────────────────────────────────────────────────────────┐
│                    스마트 골드 트레이딩 봇                        │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐         ┌─────▼─────┐         ┌─────▼─────┐
   │ 데이터   │         │ 핵심 엔진  │         │ 외부 연동  │
   │ 계층     │         │ 계층      │         │ 계층      │
   └─────────┘         └───────────┘         └───────────┘
```

---

## 📁 **파일 구조 및 역할**

### **🔧 Core Engine (핵심 엔진)**

#### **SmartGoldTradingBot_KR.py** (메인 엔진)
```python
class SmartGoldTrading:
    ├── __init__()                    # 봇 초기화
    ├── execute_gold_trading()        # 메인 매매 로직
    ├── analyze_market_conditions()   # 시장 분석
    ├── should_buy_gold()            # 매수 조건 판단
    ├── should_sell_gold()           # 매도 조건 판단
    ├── calculate_gold_drop_requirement() # 동적 하락률 계산
    ├── get_technical_indicators_gold()   # 금 특화 기술지표
    ├── execute_gold_buy_order()     # 매수 주문 실행
    ├── execute_gold_sell_order()    # 매도 주문 실행
    ├── get_gold_performance_summary() # 성과 요약
    └── save_split_data()            # 데이터 저장
```

#### **GoldTradingConfig** (설정 관리)
```python
class GoldTradingConfig:
    ├── get_default_config()    # 기본 설정 생성
    ├── load_config()          # 설정 파일 로드
    ├── save_config()          # 설정 파일 저장
    └── _merge_config()        # 설정 병합
```

---

### **🔌 API Interface Layer (API 인터페이스)**

#### **KIS_API_Helper_KR.py** (한국투자증권 API)
```python
# 핵심 거래 함수들
├── GetCurrentPrice()          # 현재가 조회
├── MakeBuyLimitOrder()       # 매수 지정가 주문
├── MakeSellLimitOrder()      # 매도 지정가 주문
├── GetBalance()              # 계좌 잔고 조회
├── GetMyStockList()          # 보유 종목 조회
├── IsMarketOpen()            # 장 개장 여부
└── GetETF_Nav()              # ETF NAV 조회
```

#### **KIS_Common.py** (공통 유틸리티)
```python
# 데이터 및 유틸리티
├── GetOhlcv()               # OHLCV 차트 데이터
├── GetNowDateStr()          # 현재 날짜 문자열
├── GetToken()               # API 토큰 관리
├── SetChangeMode()          # 실계좌/모의계좌 전환
└── 기타 공통 함수들
```

---

### **📊 Data Layer (데이터 계층)**

#### **gold_trading_config.json** (설정 파일)
```json
{
  "gold_products": {...},        // 금 ETF 상품 정의
  "technical_indicators": {...}, // 기술지표 설정
  "gold_strategy": {...},        // 투자 전략 설정
  "dynamic_drop_requirements": {...}, // 하락률 설정
  "gold_stop_loss": {...},       // 손절 설정
  "performance_tracking": {...}  // 성과 추적
}
```

#### **GoldTrading_{BOT_NAME}.json** (거래 데이터)
```json
[
  {
    "ProductCode": "132030",
    "ProductName": "KODEX 골드선물(H)",
    "MagicDataList": [
      {
        "Number": 1,
        "EntryPrice": 11500,
        "EntryAmt": 100,
        "CurrentAmt": 100,
        "SellHistory": [],
        "IsBuy": true
      }
    ],
    "RealizedPNL": 0,
    "GoldMetrics": {...}
  }
]
```

#### **myStockInfo.yaml** (API 인증)
```yaml
REAL_APP_KEY: "실계좌_앱키"
REAL_APP_SECRET: "실계좌_시크릿"
REAL_CANO: "실계좌_번호"
VIRTUAL_APP_KEY: "모의_앱키"
VIRTUAL_APP_SECRET: "모의_시크릿"
VIRTUAL_CANO: "모의_계좌번호"
```

---

### **📡 External Integration (외부 연동)**

#### **discord_alert.py** (알림 시스템)
```python
├── SendMessage()            # Discord 메시지 전송
└── 매매 결과, 성과 보고서 등 실시간 알림
```

#### **로깅 시스템**
```
logs/
├── smart_gold_trading.log         # 메인 로그
├── smart_gold_trading.20250923    # 일별 로그
└── smart_gold_trading.20250924    # 로그 로테이션
```

---

## ⚡ **실행 흐름 (Execution Flow)**

### **🚀 시스템 시작**
```
1. 봇 인스턴스 생성
   ├── 설정 파일 로드
   ├── 매매 데이터 로드
   ├── 예산 업데이트
   └── JSON 구조 업그레이드

2. 스케줄 설정
   ├── 평일 30분마다 매매 실행
   ├── 장 시작 전 시작 메시지
   └── 장 마감 후 성과 보고서

3. 무한 루프 실행
   └── 스케줄 체크 및 실행
```

### **💹 매매 실행 흐름**
```
execute_gold_trading()
│
├── 1. 시장 개장 확인
│   └── IsMarketOpen()
│
├── 2. 시장 분석
│   ├── 달러 인덱스 조회
│   ├── 코스피 변동성 측정
│   └── 종합 신호 결정
│
├── 3. 각 금 ETF별 처리
│   ├── 기술적 지표 계산
│   ├── 종목 데이터 확인/생성
│   ├── 매도 로직 우선 실행
│   └── 매수 로직 실행
│
└── 4. 결과 저장 및 알림
    ├── 매매 데이터 저장
    └── Discord 알림 전송
```

### **🎯 매수 결정 흐름**
```
should_buy_gold()
│
├── 1차수 매수 판단
│   ├── 시장 신호 확인
│   ├── RSI + 트렌드 확인
│   └── 매수 결정
│
└── 2~5차수 매수 판단
    ├── 이전 차수 보유 확인
    ├── 하락률 계산 및 달성 확인
    ├── 추가 매수 조건 확인
    └── 매수 결정
```

---

## 🧠 **핵심 알고리즘**

### **🔍 시장 분석 엔진**
```python
def analyze_market_conditions():
    conditions = {
        'dollar_strength': analyze_dollar_index(),
        'safe_haven_demand': measure_market_stress(),
        'stock_market_stress': calculate_volatility(),
        'overall_signal': determine_signal()
    }
    return conditions
```

### **📊 동적 하락률 계산**
```python
def calculate_gold_drop_requirement():
    base_drop = get_base_drop(position_num)
    
    # 시장 상황별 조정
    if dollar_strength == 'strong':
        final_drop += dollar_strength_bonus
    if safe_haven_demand == 'high':
        final_drop += safe_haven_bonus
    
    # 안전 범위 제한
    final_drop = clamp(base_drop * 0.3, base_drop * 2.0)
    return final_drop
```

### **🎯 기술적 지표 (금 특화)**
```python
def get_technical_indicators_gold():
    # 장기 이동평균 (10, 50, 200일)
    # 긴 기간 RSI (21일)
    # ATR 변동성 (20일)
    # 52주 고저점 위치
    # 트렌드 스코어 계산
    return indicators
```

---

## 🛡️ **안전성 및 신뢰성**

### **💾 데이터 안전성**
```python
def save_split_data():
    # 1. 백업 파일 생성
    # 2. 임시 파일에 저장
    # 3. JSON 유효성 검증
    # 4. 원자적 파일 교체
    # 5. 최종 검증
    # 6. 오래된 백업 정리
```

### **🔄 복구 시스템**
- **백업 파일**: 자동 백업 및 복구
- **오류 처리**: 각 단계별 예외 처리
- **롤백 메커니즘**: 실패시 이전 상태 복원
- **로깅**: 상세한 실행 로그 기록

### **⚠️ 리스크 관리**
- **주문 타임아웃**: 60초 제한
- **최대 일일 매수**: 종목당 2회 제한
- **예산 초과 방지**: 잔고 기반 검증
- **긴급 중단**: 수동 전체 매도 기능

---

## 🔧 **확장성 및 유지보수**

### **모듈화 설계**
```
├── Core Logic (매매 로직)
├── Market Analysis (시장 분석)
├── Risk Management (리스크 관리)
├── Data Management (데이터 관리)
└── External Interface (외부 연동)
```

### **설정 기반 운영**
- **JSON 설정 파일**: 코드 수정 없이 전략 변경
- **동적 로딩**: 실행 중 설정 변경 가능
- **버전 관리**: 설정 히스토리 추적

### **확장 포인트**
- **새로운 ETF 추가**: 설정 파일만 수정
- **전략 개선**: 알고리즘 모듈 교체
- **외부 데이터**: API 추가 연동 가능
- **알림 채널**: Discord 외 다른 플랫폼 연동

---

## 📈 **모니터링 및 분석**

### **실시간 모니터링**
```python
# 성과 추적 메트릭
├── 총 수익률
├── 종목별 수익률
├── 매매 횟수 및 승률
├── 최대 낙폭 (MDD)
├── 샤프 비율
└── 벤치마크 대비 성과
```

### **리포팅 시스템**
- **일일 보고서**: 장 마감 후 자동 생성
- **성과 대시보드**: 주요 지표 실시간 추적
- **알림 시스템**: 중요 이벤트 즉시 알림

---

## 🎯 **핵심 설계 원칙**

| **원칙** | **구현** | **장점** |
|----------|----------|----------|
| **모듈화** | 기능별 클래스 분리 | 유지보수성 향상 |
| **설정 중심** | JSON 기반 설정 관리 | 유연한 전략 변경 |
| **안전성** | 다중 백업 및 검증 | 데이터 손실 방지 |
| **확장성** | 플러그인 방식 설계 | 새로운 기능 추가 용이 |
| **신뢰성** | 상세한 로깅 및 모니터링 | 문제 추적 및 해결 |

**🚀 결론: 안정적이고 확장 가능한 금 투자 전문 자동매매 시스템**