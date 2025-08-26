# 적정가치 기반 자동매매 시스템 설계 문서

## 시스템 개요

본 시스템은 OpenAI GPT-4o를 활용한 적정가치 분석과 한국주식 자동매매를 통합한 시스템입니다. 기존 분할매매 방식과 달리 적정가치 대비 할인율에 따른 차등 비중 조절 방식을 채택합니다.

### 핵심 차별점

- **5차수 분할매매 → 적정가치 기반 비중 조절**
- **기술적 지표 중심 → AI 기반 펀더멘털 분석**
- **고정 예산 → 성과 연동 동적 예산 조정**
- **단일 프로세스 → 분석/매매 분리 프로세스**

## 1. 시스템 아키텍처

### 1.1 전체 프로세스 플로우

```
Data Collection → JSON Transformation → OpenAI API → Return Parsing → Auto Trading
     ↓                    ↓                ↓             ↓            ↓
  Fundamental          구조화된         Fair Value      적정가/의견    매매 실행
  Market Data         JSON 데이터       AI 분석        파싱 및 저장
  Competitor/Sector
  Macro
  Sentiment
```

### 1.2 모듈 구조

```
fair_value_trading_system/
├── fair_value_analyzer.py      # AI 기반 적정가치 분석 엔진
├── fair_value_trading_bot.py   # 메인 자동매매 봇
├── fair_value_config.py        # 설정 관리 (선택사항)
├── fair_value_results/         # JSON 결과 저장소
│   ├── latest_fair_value_analysis.json
│   └── fair_value_analysis_YYYYMMDD_HHMMSS.json
├── fair_value_cache/           # 분석 결과 캐시
└── logs/                       # 로그 파일
```

## 2. 적정가치 분석 엔진 (fair_value_analyzer.py)

### 2.1 데이터 수집 단계

#### 2.1.1 기본 재무 데이터 (Fundamental)
```python
fundamental_data = {
    'stock_code': '005930',
    'stock_name': '삼성전자',
    'current_price': 75000,
    'market_cap': 450000000000,
    'per': 15.2,
    'pbr': 1.8,
    'eps': 4934,
    'bps': 41748
}
```

#### 2.1.2 시장 데이터 (Market)
```python
market_data = {
    'ma5': 74500,
    'ma20': 73200,
    'ma60': 71800,
    'volatility_20d': 2.3,
    'volume_ratio_5d': 1.15,
    'high_52w_ratio': -0.08,
    'low_52w_ratio': 0.23,
    'price_momentum': 0.025
}
```

#### 2.1.3 섹터 비교 데이터 (Competitor/Sector)
```python
sector_data = {
    'sector_type': 'semiconductor',
    'sector_avg_per': 20,
    'sector_avg_pbr': 2.8,
    'per_vs_sector': -0.24,  # 섹터 대비 24% 저평가
    'pbr_vs_sector': -0.36   # 섹터 대비 36% 저평가
}
```

#### 2.1.4 거시경제 데이터 (Macro)
```python
macro_data = {
    'kospi_index': 2580,
    'kospi_momentum': 0.015,
    'market_volatility': 1.8,
    'market_sentiment': 'positive'
}
```

### 2.2 JSON 변환 단계

수집된 데이터를 OpenAI API에 최적화된 구조화된 JSON으로 변환:

```json
{
  "stock_info": {
    "code": "005930",
    "name": "삼성전자",
    "sector": "semiconductor",
    "current_price": 75000
  },
  "valuation_metrics": {
    "per": 15.2,
    "pbr": 1.8,
    "market_cap": 450000000000
  },
  "fundamental_data": {
    "eps": 4934,
    "bps": 41748,
    "roe": 11.8
  },
  "market_data": { /* 시장 데이터 */ },
  "sector_comparison": { /* 섹터 비교 */ },
  "macro_environment": { /* 거시환경 */ }
}
```

### 2.3 OpenAI API 호출

#### 2.3.1 시스템 프롬프트 특징
- 한국주식 시장 특성 반영 (높은 개인투자자 비중, 재벌구조)
- 한국 특화 리스크 고려 (지정학적, 규제, 수출의존도)
- 섹터별 적정 밸류에이션 배수 적용
- ESG 및 지속가능성 요소 고려

#### 2.3.2 기대 응답 형태
```json
{
  "fair_value": 82000,
  "target_price_range": {"low": 78000, "high": 86000},
  "confidence": 75,
  "analysis_method": "DCF + PER Hybrid",
  "key_factors": ["Strong fundamentals", "Sector leadership"],
  "risks": ["Market volatility", "Regulatory changes"],
  "recommendation": "BUY",
  "reasoning": "DCF 분석 결과 적정가치 82,000원..."
}
```

### 2.4 결과 저장

- **실시간 파일**: `latest_fair_value_analysis.json`
- **이력 파일**: `fair_value_analysis_20241226_143022.json`
- **캐싱**: 6시간 캐시로 중복 분석 방지

## 3. 자동매매 봇 구조

### 3.1 기존 SmartMagicSplitBotNew_KR.py 활용 요소

#### 3.1.1 재사용 컴포넌트
- **API 시스템**: KIS_API_Helper_KR, KIS_Common
- **로깅 시스템**: TimedRotatingFileHandler 기반
- **알림 시스템**: discord_alert
- **설정 관리**: JSON 기반 설정 파일
- **거래 수수료 계산**: 한국주식 실제 수수료 반영
- **현재 보유량 조회**: GetBalance 연동
- **리스크 관리**: 하락 보호 시스템 프레임워크

#### 3.1.2 제거/수정 요소
- **5차수 분할매매 로직** → 적정가치 기반 비중 조절
- **기술적 지표 중심 매수 판단** → AI 분석 결과 기반
- **순차 진입 검증** → 단일 포지션 관리
- **쿠다운 시스템** → 단순화

### 3.2 새로운 매매 로직

#### 3.2.1 적정가치 기반 포지션 사이징

```python
def calculate_position_size(discount_rate, current_budget):
    if discount_rate >= 0.50:      # 50%+ 할인
        return current_budget * 0.40
    elif discount_rate >= 0.30:    # 30-50% 할인  
        return current_budget * 0.25
    elif discount_rate >= 0.10:    # 10-30% 할인
        return current_budget * 0.15
    elif discount_rate >= 0.00:    # 0-10% 할인
        return current_budget * 0.05
    else:                          # 고평가
        return 0  # 매수 안함
```

#### 3.2.2 매도 판단 로직

```python
def should_sell(discount_rate, profit_loss_ratio):
    # 고평가 기준 매도
    if discount_rate <= -0.10:  # 10% 이상 고평가
        return True, "OVERVALUED_SELL"
    
    # 손절 기준 매도  
    if profit_loss_ratio <= -0.20:  # 20% 손실
        return True, "STOP_LOSS"
    
    return False, "HOLD"
```

### 3.3 성과 기반 동적 예산 조정

```python
def adjust_budget_by_performance(initial_budget, performance_30d):
    if performance_30d >= 0.15:      # 15% 이상 수익
        return initial_budget * 1.40  # 140%로 확대
    elif performance_30d >= 0.05:    # 5% 이상 수익  
        return initial_budget * 1.20  # 120%로 확대
    elif performance_30d <= -0.10:   # 10% 이상 손실
        return initial_budget * 0.70  # 70%로 축소
    else:
        return initial_budget         # 유지
```

## 4. 거래 수수료 반영 시스템

### 4.1 한국주식 수수료 구조

```python
def calculate_trading_fees(price, quantity, is_buy=True):
    trade_amount = price * quantity
    
    # 위탁수수료 (0.015%)
    commission = max(trade_amount * 0.00015, 100)
    
    if not is_buy:  # 매도시에만 세금
        tax = trade_amount * 0.0025          # 증권거래세 0.25%
        special_tax = trade_amount * 0.00075  # 지방소득세 0.075%
        return commission + tax + special_tax
    else:
        return commission
```

### 4.2 실제 수익률 계산

```python
def calculate_net_return(buy_price, sell_price, quantity):
    gross_profit = (sell_price - buy_price) * quantity
    buy_fees = calculate_trading_fees(buy_price, quantity, is_buy=True)
    sell_fees = calculate_trading_fees(sell_price, quantity, is_buy=False)
    net_profit = gross_profit - buy_fees - sell_fees
    return net_profit / (buy_price * quantity + buy_fees)
```

## 5. 실행 스케줄링

### 5.1 적정가치 분석 스케줄
- **주기**: 하루 1-2회 (장 시작 전, 장 중간)
- **조건**: 캐시 만료시 또는 강제 업데이트 요청시
- **목적**: OpenAI API 비용 최적화

### 5.2 매매봇 실행 스케줄  
- **주기**: 실시간 (1-5분 간격)
- **조건**: 장중 시간대만 활성화
- **동작**: JSON 파일 읽어서 매매 판단

## 6. 데이터 플로우 예시

### 6.1 완전한 실행 사이클

```
09:00 - 적정가치 분석 실행
├── 삼성전자 데이터 수집
├── OpenAI API 호출  
├── fair_value: 82000, 현재가: 75000 (할인율 9.3%)
└── latest_fair_value_analysis.json 저장

09:05 - 매매봇 실행
├── JSON 파일 로드
├── 할인율 9.3% → 5% 투자 (50만원)
├── 매수 주문: 6주 × 75000원  
└── 체결 확인 및 로깅

14:00 - 적정가치 재분석 (선택사항)
15:20 - 장 마감 전 최종 매매 판단
```

### 6.2 JSON 데이터 구조 예시

```json
{
  "analysis_info": {
    "timestamp": "2024-12-26T14:30:22",
    "total_stocks": 3,
    "analysis_version": "1.0",
    "market": "KR"
  },
  "stocks": {
    "005930": {
      "stock_info": {
        "code": "005930",
        "name": "삼성전자", 
        "current_price": 75000
      },
      "fair_value_analysis": {
        "fair_value": 82000,
        "confidence": 75,
        "recommendation": "BUY"
      },
      "trading_signals": {
        "discount_rate": 0.093,
        "recommendation": "WEAK_BUY",
        "confidence": 75
      }
    }
  }
}
```

## 7. 리스크 관리

### 7.1 포지션 관리
- **단일 종목 최대 비중**: 25%
- **전체 투자 비율**: 예산의 85% 이내
- **현금 보유**: 최소 15% 현금 유지

### 7.2 손절 시스템
- **개별 종목 최대 손실**: -20%
- **전체 포트폴리오 최대 손실**: -15%
- **손절 후 재진입 제한**: 7일

### 7.3 시장 상황 대응
- 코스피 -10% 이상 하락시 신규 매수 중단
- 연속 3일 하락시 포지션 20% 축소
- VIX 상승시 (변동성 급증) 관망

## 8. 성과 평가 지표

### 8.1 수익률 지표
- **절대 수익률**: 기준 수익률 대비
- **샤프 비율**: 위험 조정 수익률  
- **최대 낙폭(MDD)**: 최대 손실폭
- **승률**: 수익 거래 비율

### 8.2 운영 지표
- **적정가치 정확도**: 실제가 vs 예측가
- **AI 신뢰도 검증**: 고신뢰도 예측의 정확성
- **거래 비용**: 전체 수익 대비 수수료 비중
- **포트폴리오 회전율**: 매매 빈도

## 9. 확장 계획

### 9.1 단기 개선사항
- 뉴스 감성 분석 통합 (news_analysis_us_finhub.py 참조)
- 실시간 공시 모니터링
- 기관/외국인 순매수 데이터 반영

### 9.2 중장기 발전방향  
- 다양한 AI 모델 앙상블 (Claude, GPT, 자체 모델)
- 옵션/선물 헤징 전략 통합
- 해외주식 확장 (미국, 일본, 중국)
- 암호화폐 적정가치 분석 확장

## 10. 기술 스택

### 10.1 필수 라이브러리
```python
# AI/API
openai==1.0.0
python-dotenv==1.0.0

# 데이터 처리
pandas>=1.5.0
numpy>=1.24.0
requests>=2.28.0

# 한국투자증권 API
# KIS_API_Helper_KR.py (기존)
# KIS_Common.py (기존)

# 스케줄링/유틸리티
schedule>=1.2.0
logging
json
pickle
```

### 10.2 설정 파일 구조
```json
{
  "initial_budget": 10000000,
  "target_stocks": {
    "005930": {"name": "삼성전자", "sector": "semiconductor"},  
    "000660": {"name": "SK하이닉스", "sector": "semiconductor"},
    "035420": {"name": "NAVER", "sector": "technology"}
  },
  "position_allocation": {
    "discount_50_plus": 0.40,
    "discount_30_to_50": 0.25,
    "discount_10_to_30": 0.15
  },
  "trading_fees": {
    "commission_rate": 0.00015,
    "tax_rate": 0.0025,
    "special_tax_rate": 0.00075
  }
}
```

---

이 문서는 적정가치 기반 자동매매 시스템의 완전한 설계 명세서입니다. 각 모듈의 역할과 데이터 흐름, 그리고 기존 코드 자산의 활용 방안을 상세히 기술했습니다.