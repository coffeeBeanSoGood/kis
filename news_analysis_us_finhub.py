# news_analysis_us_rklb_portfolio.py (RKLB 포트폴리오 최적화 버전)
from openai import OpenAI
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import re
import json
import logging
import hashlib
import pickle
import time

# 로깅 설정
logger = logging.getLogger(__name__)

def set_logger(external_logger):
    """외부에서 로거를 설정할 수 있는 함수"""
    global logger
    logger = external_logger

try:
    import auto_economic_calendar
    auto_economic_calendar.set_logger(logger)  # 로거 전달
    ECONOMIC_CALENDAR_AVAILABLE = True
    logger.info("📅 자동 경제 캘린더 모듈 로드 완료")
except ImportError as e:
    ECONOMIC_CALENDAR_AVAILABLE = False
    logger.warning(f"⚠️ 자동 경제 캘린더 모듈을 찾을 수 없습니다: {str(e)}")
    logger.warning("기존 키워드 시스템만 사용됩니다.")

# GPT 분석 캐시 관련 함수들
def create_stocks_hash(stocks_list):
    try:
        stock_codes = sorted([s.get('ticker') or s.get('StockCode') for s in stocks_list])
        hash_string = '_'.join(stock_codes)
        return hashlib.md5(hash_string.encode()).hexdigest()[:8]
    except Exception as e:
        logger.error(f"Hash 생성 오류: {e}")
        return "default"

def get_cached_gpt_analysis(cache_key, cache_minutes=240):  # 4시간 캐시
    try:
        cache_dir = "gpt_cache"
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"gpt_analysis_{cache_key}.pkl")

        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            age = datetime.now() - cache_data['timestamp']
            if age < timedelta(minutes=cache_minutes):
                logger.info(f"📰 GPT 분석 캐시 사용 (나이: {age.total_seconds()/60:.1f}분)")
                return cache_data['analysis']
            else:
                logger.info(f"📰 GPT 분석 캐시 만료 ({age.total_seconds()/60:.1f}분 경과)")
                os.remove(cache_file)  # 만료된 캐시 삭제
    except Exception as e:
        logger.error(f"캐시 조회 오류: {e}")
    return None

def cache_gpt_analysis(cache_key, analysis):
    try:
        cache_dir = "gpt_cache"
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"gpt_analysis_{cache_key}.pkl")
        with open(cache_file, 'wb') as f:
            pickle.dump({"timestamp": datetime.now(), "analysis": analysis}, f)
        logger.info(f"📰 GPT 분석 결과 캐시 저장 완료 (키: {cache_key})")
    except Exception as e:
        logger.error(f"캐시 저장 오류: {e}")

# 🔥 RKLB 포트폴리오 최적화 뉴스 영향 키워드 시스템
def get_impact_keywords():
    """RKLB 포트폴리오 최적화 + 자동 경제 캘린더 연동 키워드 시스템"""
    
    # 🔥 기존 RKLB 포트폴리오 특화 키워드 (그대로 유지)
    impact_keywords = [
        # 📊 기본 재무/실적 관련
        'earnings', 'revenue', 'profit', 'loss', 'guidance', 'forecast', 'outlook',
        'sales', 'income', 'margin', 'eps', 'beat', 'miss', 'estimate', 'consensus',
        'quarterly', 'annual', 'report', 'results', 'performance', 'growth',
        
        # 📈 주가/투자 관련  
        'upgrade', 'downgrade', 'rating', 'target', 'price target', 'buy', 'sell', 'hold',
        'outperform', 'underperform', 'overweight', 'underweight', 'recommendation',
        'analyst', 'research', 'coverage', 'initiate', 'maintain', 'raise', 'lower',
        
        # 🤝 기업 활동/거래
        'acquisition', 'merger', 'buyback', 'split', 'dividend', 'spinoff',
        'partnership', 'collaboration', 'joint venture', 'alliance', 'agreement',
        'contract', 'deal', 'transaction', 'investment', 'funding', 'raise',
        'IPO', 'SPAC', 'listing', 'offering', 'warrant', 'convertible',
        
        # 👥 경영진/리더십
        'CEO', 'CFO', 'CTO', 'president', 'chairman', 'executive', 'management',
        'hire', 'resign', 'retire', 'appoint', 'promote', 'leadership',
        'board', 'director', 'succession', 'change', 'transition',
        
        # ⚖️ 규제/법률
        'lawsuit', 'regulatory', 'approval', 'patent', 'license', 'compliance',
        'investigation', 'settlement', 'fine', 'violation', 'FDA', 'SEC', 'NRC',
        'DOE', 'NNSA', 'EPA', 'FTC', 'DOJ', 'court', 'legal', 'litigation',
        
        # 🔬 기술/혁신 (일반)
        'breakthrough', 'technology', 'innovation', 'research', 'development',
        'clinical', 'trial', 'study', 'product', 'launch', 'release',
        'patent', 'intellectual property', 'R&D', 'prototype', 'testing',
        
        # 🎯 CCJ (카메코 - 우라늄 마이닝) 특화 키워드
        'uranium', 'yellowcake', 'nuclear fuel', 'mining', 'Kazakhstan', 'Canada',
        'Cigar Lake', 'McArthur River', 'Key Lake', 'Rabbit Lake', 'Smith Ranch',
        'fuel cycle', 'enrichment', 'conversion', 'UF6', 'U3O8',
        'nuclear power', 'reactor', 'utility', 'long term contract', 'spot price',
        'cameco', 'CCO', 'athabasca', 'mine', 'production', 'reserves',
        'geological', 'exploration', 'deposit', 'ore', 'grade', 'mill',
        'tailings', 'environmental', 'indigenous', 'community', 'royalty',
        
        # 🏭 BWXT (BWX Technologies - 원자로 기술) 특화 키워드
        'nuclear reactor', 'SMR', 'small modular reactor', 'naval reactor', 'TRISO',
        'microreactor', 'nuclear fuel', 'reactor pressure vessel', 'steam generator',
        'nuclear components', 'nuclear services', 'navy contract', 'DOE contract',
        'BWX Technologies', 'BWXT', 'nuclear manufacturing', 'reactor design',
        'fuel assembly', 'control rod', 'reactor core', 'nuclear island',
        'HALEU', 'enriched uranium', 'fuel fabrication', 'nuclear testing',
        'Virginia', 'Ohio', 'Cambridge', 'Lynchburg', 'Barberton',
        'defense', 'naval', 'submarine', 'aircraft carrier', 'propulsion',
        
        # ❄️ VRT (버티브 - 데이터센터 인프라) 특화 키워드
        'data center', 'cooling', 'thermal management', 'UPS', 'power protection',
        'liquid cooling', 'immersion cooling', 'HVAC', 'infrastructure', 'edge computing',
        'hyperscale', 'colocation', 'cloud', 'AI infrastructure', 'GPU cooling',
        'vertiv', 'liebert', 'geist', 'avocent', 'trellis', 'smartaisle',
        'power distribution', 'PDU', 'battery', 'generator', 'chiller',
        'precision cooling', 'raised floor', 'rack', 'cabinet', 'monitoring',
        'energy efficiency', 'PUE', 'sustainability', 'green data center',
        'Microsoft', 'Amazon', 'Google', 'Meta', 'hyperscaler',
        
        # 🚀 RKLB (로켓랩 - 우주항공) 특화 키워드
        'rocket', 'space', 'satellite', 'launch', 'orbit', 'mission', 'payload',
        'spacecraft', 'aerospace', 'NASA', 'SpaceX', 'constellation', 'deployment',
        'electron', 'neutron', 'reusability', 'commercial space', 'defense',
        'rocket lab', 'RKLB', 'wallops', 'mahia', 'beck', 'photon',
        'kick stage', 'fairing', 'engine', 'rutherford', 'archimedes',
        'launch pad', 'range', 'trajectory', 'telemetry', 'recovery',
        'small satellite', 'cubesat', 'rideshare', 'dedicated launch',
        'space force', 'SDA', 'reconnaissance', 'communication satellite',
        
        # 💼 시장/경쟁 관련
        'market share', 'competition', 'competitor', 'rival', 'disruption',
        'expansion', 'growth', 'scale', 'capacity', 'demand', 'supply',
        'backlog', 'order', 'customer', 'client', 'win', 'award',
        'tender', 'bid', 'RFP', 'proposal', 'selection', 'preferred',
        
        # 💰 자금/투자 관련
        'debt', 'credit', 'loan', 'bond', 'equity', 'valuation',
        'cash', 'cash flow', 'working capital', 'capex', 'opex',
        'financing', 'refinancing', 'facility', 'line of credit',
        'institutional investor', 'fund', 'private equity', 'venture capital',
        
        # 📉 리스크/부정적 키워드
        'bankruptcy', 'default', 'restructure', 'layoff', 'closure', 'suspend',
        'recall', 'cyber attack', 'data breach', 'scandal', 'fraud',
        'accident', 'incident', 'failure', 'malfunction', 'outage',
        'delay', 'postpone', 'cancel', 'terminate', 'breach',
        
        # 🌍 글로벌/거시경제
        'inflation', 'interest rate', 'fed', 'federal reserve', 'tariff', 'trade war',
        'recession', 'recovery', 'stimulus', 'policy', 'geopolitical',
        'sanctions', 'export control', 'national security', 'critical minerals',
        'supply chain', 'logistics', 'shortage', 'disruption',
        
        # 🎯 성과/마일스톤
        'milestone', 'achievement', 'record', 'first', 'successful', 'completion',
        'delivery', 'deployment', 'operational', 'commercial', 'production',
        'commissioning', 'startup', 'ramp up', 'scale up', 'full capacity',
        'certification', 'qualification', 'validation', 'verification',
        
        # 🔮 미래/전망 키워드
        'pipeline', 'roadmap', 'timeline', 'schedule', 'plan', 'strategy',
        'vision', 'potential', 'opportunity', 'challenge', 'risk',
        'outlook', 'projection', 'estimate', 'target', 'goal', 'objective',
        
        # 🏛️ 정부/정책 키워드
        'government', 'federal', 'policy', 'regulation', 'subsidy', 'incentive',
        'clean energy', 'carbon neutral', 'net zero', 'climate', 'ESG',
        'IRA', 'inflation reduction act', 'infrastructure', 'CHIPS act',
        'national defense', 'strategic', 'critical', 'export control',
        
        # 🌟 업종별 특수 이벤트
        'uranium price', 'spot uranium', 'nuclear renaissance', 'reactor restart',
        'AI boom', 'generative AI', 'ChatGPT', 'machine learning', 'GPU demand',
        'space economy', 'NewSpace', 'satellite internet', 'lunar mission', 'mars'
    ]
    
    # 🔥 기존 RKLB 특화 고영향 키워드 (그대로 유지)
    high_impact_keywords = [
        # 기본 고영향 키워드
        'earnings beat', 'earnings miss', 'guidance raise', 'guidance cut',
        'FDA approval', 'NRC approval', 'patent approval', 'breakthrough', 'acquisition',
        'merger', 'CEO resign', 'lawsuit', 'investigation', 'bankruptcy',
        
        # CCJ (카메코) 고영향 키워드
        'uranium price surge', 'uranium shortage', 'mine restart', 'production halt',
        'Kazakhstan disruption', 'nuclear fuel shortage', 'utility contract',
        'long term agreement', 'reactor restart', 'nuclear policy',
        'uranium stockpile', 'enrichment capacity', 'fuel cycle disruption',
        
        # BWXT 고영향 키워드
        'SMR approval', 'reactor design approval', 'navy contract award',
        'DOE funding', 'nuclear fuel contract', 'HALEU production',
        'microreactor deployment', 'nuclear export license', 'fuel fabrication',
        'nuclear accident', 'safety incident', 'regulatory violation',
        
        # VRT (버티브) 고영향 키워드
        'data center boom', 'AI infrastructure demand', 'hyperscale expansion',
        'cooling technology breakthrough', 'power outage', 'cooling failure',
        'Microsoft partnership', 'Amazon contract', 'Google deal',
        'liquid cooling adoption', 'sustainability mandate', 'energy crisis',
        
        # RKLB (로켓랩) 고영향 키워드
        'launch success', 'launch failure', 'NASA contract', 'defense contract',
        'space force contract', 'satellite deployment', 'constellation launch',
        'rocket explosion', 'pad accident', 'mission failure',
        'reusability breakthrough', 'cost reduction', 'launch frequency',
        'competitor selection', 'SpaceX competition', 'market share gain',
        
        # 업종 공통 고영향 키워드
        'government contract', 'partnership announcement', 'technology breakthrough',
        'capacity expansion', 'facility closure', 'production increase',
        'supply disruption', 'raw material shortage', 'price increase',
        'demand surge', 'market consolidation', 'regulatory change'
    ]
    
    # 🔥🔥 NEW: 자동 경제 캘린더 기반 동적 키워드 추가 🔥🔥
    if ECONOMIC_CALENDAR_AVAILABLE:
        try:
            # 자동 캘린더에서 경제 이벤트 키워드 가져오기
            updater = auto_economic_calendar.AutoEconomicCalendarUpdater()
            calendar_data = updater.update_calendar_if_needed()
            
            if calendar_data:
                # 다가오는 경제 이벤트 키워드 추가
                upcoming_events = auto_economic_calendar.get_upcoming_events_from_calendar(calendar_data, days_ahead=7)
                
                economic_keywords = []
                high_impact_economic_keywords = []
                
                for event in upcoming_events:
                    # 이벤트별 키워드 추가
                    economic_keywords.extend(event.get("keywords", []))
                    
                    # 임박한 고중요 이벤트는 고영향 키워드로 승격 (3일 이내)
                    if event["days_ahead"] <= 3 and event["importance"] == "high":
                        high_impact_economic_keywords.extend(event.get("keywords", []))
                
                # 동적 검색어도 키워드로 추가
                dynamic_terms = auto_economic_calendar.generate_dynamic_search_terms()
                for term in dynamic_terms:
                    term_keywords = [word.lower() for word in term.split() if len(word) > 2]
                    economic_keywords.extend(term_keywords)
                
                # 🔥 기존 RKLB 키워드와 경제 키워드 병합
                impact_keywords.extend(economic_keywords)
                high_impact_keywords.extend(high_impact_economic_keywords)
                
                # 중복 제거
                impact_keywords = list(set(impact_keywords))
                high_impact_keywords = list(set(high_impact_keywords))
                
                logger.info(f"🤖 RKLB 특화 + 경제 캘린더 키워드 통합 완료")
                logger.info(f"   기존 RKLB 키워드 유지 + 경제 키워드 {len(economic_keywords)}개 추가")
                logger.info(f"   총 기본 키워드: {len(impact_keywords)}개")
                logger.info(f"   총 고영향 키워드: {len(high_impact_keywords)}개")
                
                # 임박한 고영향 이벤트 알림
                for event in upcoming_events:
                    if event["days_ahead"] <= 3 and event["importance"] == "high":
                        logger.info(f"🔥 RKLB 포트폴리오 관련 경제 이벤트 임박: {event['event']} ({event['days_ahead']}일 후)")
                
            else:
                logger.warning("⚠️ 자동 캘린더 로드 실패 - RKLB 기본 키워드만 사용")
                
        except Exception as e:
            logger.error(f"❌ 경제 캘린더 키워드 통합 오류: {e} - RKLB 기본 키워드만 사용")
    else:
        logger.info("📊 RKLB 특화 기본 키워드 시스템 사용 (경제 캘린더 없음)")
    
    return impact_keywords, high_impact_keywords

def calculate_relevance_score(headline, summary, impact_keywords, high_impact_keywords):
    """RKLB 특화 + 경제 이벤트 보너스 관련도 점수 계산"""

    if ECONOMIC_CALENDAR_AVAILABLE:
        try:
            # 자동 캘린더 기반 향상된 관련도 계산
            return auto_economic_calendar.calculate_enhanced_relevance_score(
                headline, summary, impact_keywords, high_impact_keywords
            )
        except Exception as e:
            logger.error(f"❌ 향상된 관련도 계산 오류: {e} - 기본 계산 사용")
  
    try:
        content_text = f"{headline} {summary}".lower()
        headline_lower = headline.lower()
        
        # 1. 기본 키워드 점수
        basic_score = sum(1 for keyword in impact_keywords if keyword in content_text)
        
        # 2. 고영향 키워드 점수 (2배 가중치)
        high_impact_score = sum(2 for keyword in high_impact_keywords if keyword in content_text)
        
        # 3. 제목에 키워드가 있으면 추가 점수 (제목이 더 중요)
        headline_bonus = sum(1 for keyword in impact_keywords if keyword in headline_lower)
        
        # 4. 고영향 키워드가 제목에 있으면 추가 보너스
        headline_high_impact_bonus = sum(2 for keyword in high_impact_keywords if keyword in headline_lower)
        
        # 5. 포트폴리오 특화 보너스
        portfolio_bonus = 0
        
        # CCJ 관련 특화 보너스
        ccj_terms = ['uranium', 'cameco', 'nuclear fuel', 'mining', 'yellowcake']
        if any(term in content_text for term in ccj_terms):
            portfolio_bonus += 1
            
        # BWXT 관련 특화 보너스
        bwxt_terms = ['BWX', 'BWXT', 'naval reactor', 'SMR', 'nuclear component']
        if any(term in content_text for term in bwxt_terms):
            portfolio_bonus += 1
            
        # VRT 관련 특화 보너스
        vrt_terms = ['vertiv', 'data center', 'cooling', 'infrastructure', 'AI']
        if any(term in content_text for term in vrt_terms):
            portfolio_bonus += 1
            
        # RKLB 관련 특화 보너스
        rklb_terms = ['rocket lab', 'electron', 'neutron', 'launch', 'satellite']
        if any(term in content_text for term in rklb_terms):
            portfolio_bonus += 1
        
        total_score = basic_score + high_impact_score + headline_bonus + headline_high_impact_bonus + portfolio_bonus
        
        return total_score
        
    except Exception as e:
        logger.error(f"관련도 점수 계산 오류: {e}")
        return 0

# Finnhub 기반 뉴스 수집 함수 (RKLB 포트폴리오 최적화)
def get_us_stock_news_finnhub(ticker, days_back=3, max_retries=3):
    """Finnhub API를 통한 미국 주식 뉴스 수집 (RKLB 포트폴리오 최적화)"""
    for attempt in range(max_retries):
        try:
            load_dotenv()
            finnhub_key = os.getenv("FINNHUB_API_KEY")
            if not finnhub_key:
                logger.error("FINNHUB_API_KEY가 .env 파일에 없습니다")
                return []

            today = datetime.now()
            from_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
            to_date = today.strftime("%Y-%m-%d")

            url = f"https://finnhub.io/api/v1/company-news"
            params = {
                "symbol": ticker.upper(), 
                "from": from_date, 
                "to": to_date, 
                "token": finnhub_key
            }
            
            logger.info(f"📰 {ticker} 뉴스 수집 중...")
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 429:
                wait_time = 60 * (attempt + 1)
                logger.warning(f"⏳ Finnhub API 한도 도달 - {wait_time}초 대기")
                time.sleep(wait_time)
                continue
            elif response.status_code == 401:
                logger.error(f"❌ API 키 인증 실패")
                return []
            elif response.status_code != 200:
                logger.error(f"❌ API 오류: {response.status_code}")
                return []
                
            data = response.json()

            if not isinstance(data, list):
                logger.warning(f"⚠️ {ticker}: 예상과 다른 응답 형태")
                return []

            if len(data) == 0:
                logger.info(f"📰 {ticker}: 해당 기간에 뉴스 없음")
                return []

            # 🔥 RKLB 포트폴리오 최적화 키워드 시스템 적용
            impact_keywords, high_impact_keywords = get_impact_keywords()
            
            articles = []
            for item in data:
                if not isinstance(item, dict) or "headline" not in item or "datetime" not in item:
                    continue
                    
                dt = datetime.fromtimestamp(item["datetime"])
                if dt < datetime.now() - timedelta(days=days_back):
                    continue
                    
                headline = item["headline"]
                summary = item.get("summary", "")
                source = item.get("source", "Unknown")
                date_str = dt.strftime("%Y-%m-%d %H:%M")

                # 🔥 RKLB 포트폴리오 최적화 관련도 점수 계산
                relevance_score = calculate_relevance_score(headline, summary, impact_keywords, high_impact_keywords)

                # 관련도가 0인 뉴스도 포함하되 우선순위에서 밀림
                articles.append({
                    "title": headline,
                    "snippet": summary[:150] if summary else headline[:150],
                    "source": source,
                    "date": date_str,
                    "relevance_score": relevance_score
                })

            # 관련도 순으로 정렬 (높은 점수부터)
            articles.sort(key=lambda x: x['relevance_score'], reverse=True)
            selected_articles = articles[:5]
            
            # 관련도 점수 로깅
            if selected_articles:
                avg_relevance = sum(a['relevance_score'] for a in selected_articles) / len(selected_articles)
                max_relevance = max(a['relevance_score'] for a in selected_articles)
                logger.info(f"✅ {ticker}: {len(selected_articles)}개 뉴스 수집 완료 (관련도: 평균 {avg_relevance:.1f}, 최고 {max_relevance})")
            else:
                logger.info(f"✅ {ticker}: {len(selected_articles)}개 뉴스 수집 완료")
            
            return selected_articles
            
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 {ticker} 네트워크 오류 (시도 {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
        except Exception as e:
            logger.error(f"❌ {ticker} 뉴스 수집 오류 (시도 {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    logger.warning(f"⚠️ {ticker} 뉴스 수집 최종 실패")
    return []

# RKLB 포트폴리오 종목 리스트 전체 분석 함수
def analyze_us_stocks_news(stocks_list):
    """RKLB 포트폴리오 미국 주식들의 뉴스를 종합 분석"""
    try:
        if not stocks_list:
            logger.warning("📰 분석 대상 종목이 없습니다")
            return {}

        # 캐시 확인
        cache_key = create_stocks_hash(stocks_list)
        cached_result = get_cached_gpt_analysis(cache_key, cache_minutes=240)
        if cached_result:
            logger.info("📰 캐시된 뉴스 분석 결과 사용")
            return cached_result

        logger.info(f"📰 RKLB 포트폴리오 뉴스 분석 시작 - 대상: {len(stocks_list)}개 종목")

        # 각 종목별 뉴스 수집
        news_data = {"stocks": {}}
        total_articles = 0
        
        for stock in stocks_list:
            ticker = stock.get("ticker")
            company_name = stock.get("company_name")
            
            if not ticker or not company_name:
                logger.warning(f"⚠️ 잘못된 종목 정보: {stock}")
                continue

            articles = get_us_stock_news_finnhub(ticker, days_back=2)  # 2일간 뉴스
            
            if not articles:
                logger.info(f"📰 {company_name}({ticker}): 뉴스 없음")
                continue

            news_data["stocks"][company_name] = {
                "stock_code": ticker,
                "ticker": ticker,
                "articles": [{
                    "title": a['title'],
                    "snippet": a['snippet'],
                    "source": a['source'],
                    "date": a['date'],
                    "relevance_score": a.get('relevance_score', 0)  # 관련도 점수 포함
                } for a in articles[:3]]  # 상위 3개만
            }
            
            total_articles += len(articles)

        if not news_data["stocks"]:
            logger.info("📰 분석할 뉴스가 없어서 빈 결과 반환")
            empty_result = {"stocks": {}}
            cache_gpt_analysis(cache_key, empty_result)
            return empty_result

        logger.info(f"📊 뉴스 수집 완료: {len(news_data['stocks'])}개 종목, {total_articles}개 뉴스")

        # OpenAI GPT로 뉴스 분석
        logger.info("🤖 OpenAI GPT로 RKLB 포트폴리오 뉴스 감정 분석 시작")
        
        load_dotenv()
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.error("OPENAI_API_KEY가 .env 파일에 없습니다")
            return news_data

        client = OpenAI(api_key=openai_key)

        # 🔥 RKLB 포트폴리오 특화 프롬프트
        system_prompt = """You are a professional financial analyst specializing in US stock market news analysis for the RKLB Portfolio.

Analyze the impact of news articles on stock prices for the provided companies in our focused portfolio.

For each company, provide your analysis in the following JSON format:
{
  "analyses": [
    {
      "stock_name": "Company Name",
      "decision": "POSITIVE" or "NEGATIVE" or "NEUTRAL",
      "percentage": 75,
      "reason": "Brief explanation of your decision"
    }
  ]
}

Guidelines:
- POSITIVE: News likely to increase stock price (earnings beat, new contracts, partnerships, breakthroughs, etc.)
- NEGATIVE: News likely to decrease stock price (earnings miss, lawsuits, downgrades, setbacks, etc.)
- NEUTRAL: No significant impact expected
- Percentage: 1-100 for impact strength, 0 for neutral
- Focus on recent news and actual business impact

Industry-Specific Analysis Focus:
* Uranium Mining (CCJ - Cameco Corp): 
  - Uranium spot prices, mine operations, utility contracts, nuclear policy changes
  - Kazakhstan geopolitical risks, production capacity, long-term fuel agreements
  - Nuclear renaissance trends, reactor restarts, new nuclear construction
  
* Nuclear Technology (BWXT - BWX Technologies): 
  - Naval reactor contracts, SMR developments, nuclear fuel services
  - DOE/NNSA funding, regulatory approvals, HALEU production capabilities
  - Defense contracts, nuclear component manufacturing, safety incidents
  
* Data Center Infrastructure (VRT - Vertiv Holdings): 
  - AI boom impact, hyperscale data center demand, cooling technology advances
  - Power infrastructure needs, sustainability mandates, efficiency breakthroughs
  - Major cloud provider partnerships (Microsoft, Amazon, Google contracts)
  
* Space Technology (RKLB - Rocket Lab USA): 
  - Launch successes/failures, satellite deployment missions, NASA partnerships
  - Defense/Space Force contracts, commercial space market developments
  - Competition with SpaceX, reusability achievements, cost reduction milestones

Priority Factors:
- Weight earnings reports, regulatory approvals, major contracts, and commodity prices heavily
- Consider government policies affecting nuclear energy, space industry, and AI infrastructure
- Pay special attention to supply chain disruptions, geopolitical risks, and technology breakthroughs
- Evaluate competitive positioning within each specialized industry sector
- Consider ESG factors and sustainability trends impacting energy and technology sectors"""

        try:
            # 뉴스 데이터를 더 간결하게 정리 (관련도 점수 포함)
            simplified_news = {}
            for company, data in news_data["stocks"].items():
                simplified_news[company] = {
                    "ticker": data["ticker"],
                    "recent_news": [
                        f"• [Score:{article.get('relevance_score', 0)}] {article['title']} - {article['snippet'][:100]}..."
                        for article in data["articles"]
                    ]
                }

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze the market impact of these news for our RKLB Portfolio (relevance scores indicate keyword relevance to our portfolio themes):\n\n{json.dumps(simplified_news, ensure_ascii=False, indent=2)}"}
            ]

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.1,
                max_tokens=1500,
                timeout=30
            )

            gpt_response = response.choices[0].message.content.strip()
            logger.info(f"🤖 GPT 응답 수신 완료 ({len(gpt_response)} chars)")

            # JSON 파싱
            try:
                # JSON 블록 추출
                if '```json' in gpt_response:
                    json_start = gpt_response.find('{', gpt_response.find('```json'))
                    json_end = gpt_response.rfind('}', 0, gpt_response.rfind('```')) + 1
                    json_str = gpt_response[json_start:json_end]
                elif gpt_response.strip().startswith('{'):
                    json_str = gpt_response.strip()
                else:
                    json_start = gpt_response.find('{')
                    json_end = gpt_response.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                        json_str = gpt_response[json_start:json_end]
                    else:
                        raise ValueError("JSON 형태를 찾을 수 없음")

                result = json.loads(json_str)
                
                if "analyses" not in result:
                    logger.error("GPT 응답에 'analyses' 키가 없습니다")
                    raise ValueError("Invalid response format")

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"❌ GPT 응답 JSON 파싱 실패: {e}")
                logger.error(f"원본 응답 (처음 500자): {gpt_response[:500]}")
                
                # 파싱 실패 시 중립으로 처리
                result = {"analyses": []}
                for company_name in news_data["stocks"].keys():
                    result["analyses"].append({
                        "stock_name": company_name,
                        "decision": "NEUTRAL",
                        "percentage": 0,
                        "reason": "GPT 응답 파싱 실패로 중립 처리"
                    })

            # 분석 결과를 news_data에 통합
            for analysis in result.get("analyses", []):
                stock_name = analysis.get("stock_name", "")
                if stock_name in news_data["stocks"]:
                    news_data["stocks"][stock_name]["analysis"] = {
                        "decision": analysis.get("decision", "NEUTRAL"),
                        "percentage": analysis.get("percentage", 0),
                        "reason": analysis.get("reason", "분석 결과 없음")
                    }

            # 결과 로깅
            logger.info("📊 RKLB 포트폴리오 뉴스 분석 결과:")
            for analysis in result.get("analyses", []):
                name = analysis.get("stock_name", "Unknown")
                decision = analysis.get("decision", "NEUTRAL")
                percentage = analysis.get("percentage", 0)
                reason = analysis.get("reason", "")
                
                # 포트폴리오별 이모지
                emoji_map = {
                    "Cameco Corp": "⚛️",
                    "BWX Technologies Inc": "🏭", 
                    "Vertiv Holdings Co": "❄️",
                    "Rocket Lab USA Inc": "🚀"
                }
                stock_emoji = emoji_map.get(name, {"POSITIVE": "📈", "NEGATIVE": "📉", "NEUTRAL": "➖"}.get(decision, "❓"))
                
                logger.info(f"  {stock_emoji} {name}: {decision} ({percentage}%) - {reason}")

            # 캐시 저장
            cache_gpt_analysis(cache_key, news_data)
            logger.info("✅ RKLB 포트폴리오 뉴스 분석 완료 및 캐시 저장")
            
            return news_data

        except Exception as e:
            logger.error(f"❌ OpenAI API 호출 오류: {e}")
            # OpenAI 오류 시에도 뉴스 데이터는 반환
            return news_data

    except Exception as e:
        logger.error(f"❌ RKLB 포트폴리오 전체 뉴스 분석 오류: {e}")
        import traceback
        traceback.print_exc()
        return {}

# 🧪 RKLB 포트폴리오 테스트 실행용
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 🎯 RKLB 포트폴리오 테스트 종목 (CCJ+BWXT+VRT+RKLB)
    test_stocks = [
        {"ticker": "CCJ", "company_name": "Cameco Corp"},
        {"ticker": "BWXT", "company_name": "BWX Technologies Inc"},
        {"ticker": "VRT", "company_name": "Vertiv Holdings Co"},
        {"ticker": "RKLB", "company_name": "Rocket Lab USA Inc"}
    ]
    
    print("🚀 RKLB 포트폴리오 뉴스 분석 테스트 시작")
    print("📋 대상 종목: CCJ(우라늄) + BWXT(원자로) + VRT(데이터센터) + RKLB(우주항공)")
    print("=" * 80)
    
    result = analyze_us_stocks_news(test_stocks)
    
    print(f"\n📊 RKLB 포트폴리오 분석 결과:")
    print("=" * 80)
    
    if result.get("stocks"):
        # 포트폴리오별 테마 구분
        themes = {
            "원전 독점 체인 (60%)": ["Cameco Corp", "BWX Technologies Inc"],
            "미래 기술 (40%)": ["Vertiv Holdings Co", "Rocket Lab USA Inc"]
        }
        
        for theme_name, companies in themes.items():
            print(f"\n🎯 {theme_name}")
            print("-" * 50)
            
            for company in companies:
                if company in result["stocks"]:
                    data = result["stocks"][company]
                    
                    # 회사별 이모지
                    company_emoji = {
                        "Cameco Corp": "⚛️", 
                        "BWX Technologies Inc": "🏭",
                        "Vertiv Holdings Co": "❄️", 
                        "Rocket Lab USA Inc": "🚀"
                    }.get(company, "🏢")
                    
                    print(f"\n{company_emoji} {company} ({data['ticker']}):")
                    
                    # 뉴스 출력 (관련도 점수 포함)
                    print("  📰 주요 뉴스:")
                    if data.get("articles"):
                        for i, article in enumerate(data["articles"], 1):
                            relevance = article.get('relevance_score', 0)
                            print(f"    [{i}] [관련도:{relevance}점] {article['title'][:70]}...")
                            print(f"        └─ {article['source']} | {article['date']}")
                    else:
                        print("    📭 최근 뉴스 없음")
                    
                    # 분석 결과 출력
                    if "analysis" in data:
                        analysis = data["analysis"]
                        decision_emoji = {"POSITIVE": "📈", "NEGATIVE": "📉", "NEUTRAL": "➖"}.get(analysis["decision"], "❓")
                        print(f"  {decision_emoji} 투자 영향: {analysis['decision']} ({analysis['percentage']}%)")
                        print(f"  💭 분석 근거: {analysis['reason']}")
                    else:
                        print("  ⚠️ 분석 결과 없음")
                else:
                    print(f"\n🏢 {company}: 📭 뉴스 없음")
        
        # 포트폴리오 종합 요약
        print(f"\n📈 포트폴리오 종합 요약:")
        print("=" * 50)
        
        positive_count = sum(1 for data in result["stocks"].values() 
                           if data.get("analysis", {}).get("decision") == "POSITIVE")
        negative_count = sum(1 for data in result["stocks"].values() 
                           if data.get("analysis", {}).get("decision") == "NEGATIVE")
        neutral_count = sum(1 for data in result["stocks"].values() 
                          if data.get("analysis", {}).get("decision") == "NEUTRAL")
        
        total_analyzed = positive_count + negative_count + neutral_count
        
        if total_analyzed > 0:
            print(f"📈 긍정적: {positive_count}개 종목 ({positive_count/total_analyzed*100:.1f}%)")
            print(f"📉 부정적: {negative_count}개 종목 ({negative_count/total_analyzed*100:.1f}%)")
            print(f"➖ 중립적: {neutral_count}개 종목 ({neutral_count/total_analyzed*100:.1f}%)")
            
            # 전체적인 포트폴리오 건강도
            if positive_count > negative_count:
                portfolio_health = "🟢 양호"
            elif positive_count < negative_count:
                portfolio_health = "🔴 주의"
            else:
                portfolio_health = "🟡 보통"
                
            print(f"🎯 포트폴리오 건강도: {portfolio_health}")
        else:
            print("📭 분석 가능한 뉴스가 없습니다")
            
    else:
        print("❌ 뉴스 또는 분석 결과 없음")
        
    # RKLB 포트폴리오 특화 키워드 통계 출력
    print(f"\n📈 RKLB 포트폴리오 키워드 시스템 통계:")
    print("=" * 50)
    
    impact_keywords, high_impact_keywords = get_impact_keywords()
    print(f"📝 기본 키워드: {len(impact_keywords)}개")
    print(f"⚡ 고영향 키워드: {len(high_impact_keywords)}개")
    print(f"📊 총 키워드: {len(impact_keywords) + len(high_impact_keywords)}개")
    
    # 포트폴리오별 특화 키워드 카운트
    ccj_keywords = [k for k in impact_keywords if any(term in k for term in ['uranium', 'cameco', 'nuclear fuel', 'mining', 'yellowcake'])]
    bwxt_keywords = [k for k in impact_keywords if any(term in k for term in ['reactor', 'BWXT', 'SMR', 'naval', 'nuclear component'])]
    vrt_keywords = [k for k in impact_keywords if any(term in k for term in ['data center', 'cooling', 'vertiv', 'infrastructure', 'AI'])]
    rklb_keywords = [k for k in impact_keywords if any(term in k for term in ['rocket', 'space', 'satellite', 'launch', 'electron'])]
    
    print(f"\n🎯 종목별 특화 키워드 분포:")
    print(f"  ⚛️ 우라늄(CCJ): {len(ccj_keywords)}개")
    print(f"  🏭 원자로(BWXT): {len(bwxt_keywords)}개") 
    print(f"  ❄️ 데이터센터(VRT): {len(vrt_keywords)}개")
    print(f"  🚀 우주항공(RKLB): {len(rklb_keywords)}개")
    
    print(f"\n🎉 RKLB 포트폴리오 뉴스 분석 테스트 완료!")
    print("=" * 80)