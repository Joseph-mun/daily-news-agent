"""
금융권 보안 뉴스 수집 및 텔레그램 전송 봇

이 스크립트는 네이버 뉴스 API와 Tavily API를 사용하여
금융권 보안 관련 뉴스를 수집하고, Groq API로 선별한 후
텔레그램으로 전송합니다.
"""

import os
import json
import html
import sqlite3
import requests
import re
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from tavily import TavilyClient

# ==========================================
# 로깅 설정
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==========================================
# 환경변수 설정
# ==========================================
NAVER_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 대한민국 서울 시간(KST, UTC+9) 기준 날짜
# Lambda 웜 컨테이너 캐시 방지를 위해 main()에서 재계산
KST = ZoneInfo("Asia/Seoul")
_kst_now = datetime.now(KST)
NOW = _kst_now
TODAY_STR = _kst_now.strftime("%Y-%m-%d")
YESTERDAY = (_kst_now - timedelta(days=1)).strftime("%Y-%m-%d")


# ==========================================
# 국내 뉴스 검색 (네이버 API)
# ==========================================
def search_naver_news() -> List[Dict[str, str]]:
    """
    네이버 뉴스 API를 사용하여 국내 보안 뉴스를 검색합니다.
    
    Returns:
        List[Dict]: 수집된 뉴스 기사 리스트
    """
    keywords = ["AI보안", "정보보호", "해킹", "개인정보유출", "금융보안", "랜섬웨어", "개인정보보호법", "KISA 사이버"]
    logger.info(f"🇰🇷 [국내] 네이버 분할 검색 시작: {keywords}")
    
    if not NAVER_ID or not NAVER_SECRET:
        logger.error("❌ 네이버 API 키가 없습니다.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET
    }
    
    all_collected = {}  # 중복 제거를 위한 딕셔너리

    for keyword in keywords:
        try:
            params = {"query": keyword, "display": 15, "sort": "date"}
            res = requests.get(url, headers=headers, params=params, timeout=10)
            
            if res.status_code == 200:
                items = res.json().get('items', [])
                for item in items:
                    try:
                        # 날짜 파싱 및 필터링
                        pub_date_str = item.get('pubDate', '')
                        if pub_date_str:
                            pub_dt = datetime.strptime(
                                pub_date_str,
                                "%a, %d %b %Y %H:%M:%S +0900"
                            )
                            pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                            if pub_date_fmt < YESTERDAY:
                                continue
                        else:
                            pub_date_fmt = TODAY_STR
                    except Exception as e:
                        logger.warning(f"날짜 파싱 실패: {e}, 기본값 사용")
                        pub_date_fmt = TODAY_STR

                    # 중복 체크
                    link = item.get('originallink') or item.get('link', '')
                    if not link or link in all_collected:
                        continue

                    # HTML 태그 제거 및 특수문자 처리
                    clean_title = re.sub('<.+?>', '', item.get('title', ''))
                    clean_title = html.unescape(clean_title)

                    clean_desc = re.sub('<.+?>', '', item.get('description', ''))
                    clean_desc = html.unescape(clean_desc)

                    all_collected[link] = {
                        "category": "[국내]",
                        "title": clean_title,
                        "url": link,
                        "published_date": pub_date_fmt,
                        "description": clean_desc
                    }
            else:
                logger.warning(f"네이버 API 요청 실패 (키워드: {keyword}): {res.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"네이버 API 요청 오류 (키워드: {keyword}): {e}")
        except Exception as e:
            logger.error(f"예상치 못한 오류 (키워드: {keyword}): {e}")
            
    final_list = list(all_collected.values())
    logger.info(f"   👉 국내 후보 총 {len(final_list)}건 확보")
    
    # 우선순위 점수 계산 함수
    def calculate_priority_score(article: Dict[str, str]) -> int:
        """기사의 우선순위 점수를 계산합니다."""
        score = 0
        title = article['title'].lower()
        desc = article['description'].lower()
        
        # 1순위 키워드 (AI보안, 침해사고) - 10점
        high_priority = ['ai보안', 'ai 보안', '해킹', '유출', '랜섬웨어', '사이버공격', '보안사고', '침해']
        score += sum(10 for k in high_priority if k in title or k in desc)

        # 1순위 키워드 (규제/정책/법률) - 10점
        regulation = ['개보법', '개인정보보호법', '신정법', '신용정보법', '전자금융거래법', '전자금융감독규정',
                      'kisa', '금보원', '금융보안원', '금감원', '금융감독원', '과기정통부', '개인정보위',
                      '사이버특사경', '수사권', '법개정', '법 개정', '재개정', '시행령']
        score += sum(10 for k in regulation if k in title or k in desc)

        # 2순위 키워드 (기술/취약점) - 5점
        mid_priority = ['보안기술', '제로데이', '취약점', 'cve-']
        score += sum(5 for k in mid_priority if k in title or k in desc)

        # 3순위 키워드 (금융권/신한) - 3점
        finance = ['신한', '금융권', '금융사', '은행']
        score += sum(3 for k in finance if k in title or k in desc)
        
        # 날짜 가중치 (당일 기사 우대) - 2점
        if article['published_date'] == TODAY_STR:
            score += 2
        
        return score
    
    # 점수순으로 정렬하여 상위 20개만 선택
    final_list.sort(key=calculate_priority_score, reverse=True)
    if len(final_list) > 20:
        final_list = final_list[:20]
        logger.info(f"   ✂️ 상위 20개로 압축 (우선순위 기반 선별)")
        
    return final_list


# ==========================================
# 해외 뉴스 검색 (Tavily API)
# ==========================================
def search_tavily_news() -> List[Dict[str, str]]:
    """
    Tavily API를 사용하여 해외 보안 뉴스를 검색합니다.
    
    Returns:
        List[Dict]: 수집된 뉴스 기사 리스트
    """
    logger.info(f"🇺🇸 [해외] Tavily 검색 시작...")
    
    if not TAVILY_KEY:
        logger.error("❌ Tavily API 키가 없습니다.")
        return []
        
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        
        domains = [
            "thehackernews.com",
            "bleepingcomputer.com",
            "darkreading.com",
            "securityweek.com",
            "wired.com",
            "techcrunch.com"
        ]
        
        res = tavily.search(
            query="Cyber Security Breach Hacking News",
            topic="news",
            days=2,
            include_domains=domains,
            max_results=40
        )
        
        collected = []
        for item in res.get('results', []):
            pub_date = item.get('published_date', '')
            if pub_date is None:
                pub_date = ""
            
            # 날짜 필터링 (현재 연도가 아니거나 'ago'가 포함된 경우 제외)
            current_year = str(NOW.year)
            if pub_date and (current_year not in pub_date and 'ago' not in pub_date):
                continue

            collected.append({
                "category": "[해외]",
                "title": item.get('title', ''),
                "url": item.get('url', ''),
                "published_date": pub_date,
                "description": item.get('content', '')[:200]
            })
        
        # 상위 20개로 제한
        collected = collected[:20]
        logger.info(f"   👉 해외 후보 {len(collected)}개 확보 (필터링 완료)")
        return collected
        
    except Exception as e:
        logger.error(f"❌ Tavily 오류: {e}")
        return []


# ==========================================
# 로컬 필터링 (API 사용량 절감)
# ==========================================
def simple_rule_filter(articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    명백한 제외 대상을 로컬에서 필터링하여 API 사용량을 줄입니다.
    
    Args:
        articles: 필터링할 뉴스 기사 리스트
    
    Returns:
        List[Dict]: 필터링된 뉴스 기사 리스트
    """
    if not articles:
        return []
    
    filtered = []
    exclude_keywords = ['채용', '인사발령', '이벤트', '프로모션', '광고', '모집']
    
    for article in articles:
        title = article.get('title', '').lower()
        desc = article.get('description', '').lower()
        
        # 명백히 관련 없는 것만 제외
        if any(kw in title or kw in desc for kw in exclude_keywords):
            continue
        
        filtered.append(article)
    
    logger.info(f"   🔍 로컬 필터링: {len(articles)}개 → {len(filtered)}개")
    return filtered


def remove_duplicate_articles(articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    제목 유사도 + 핵심 키워드 기반으로 중복 기사를 제거합니다.
    같은 사건을 다룬 여러 언론사의 기사 중 하나만 선택합니다.
    
    Args:
        articles: 중복 제거할 뉴스 기사 리스트
    
    Returns:
        List[Dict]: 중복이 제거된 뉴스 기사 리스트
    """
    if not articles:
        return []
    
    # 보안 뉴스 공통 불용어 (중복 판단에서 제외)
    STOPWORDS = {
        # 보안 분야 공통어
        '해킹', '해커', '보안', '사이버', '공격', '방어', '위협', '취약점', '악성코드',
        '랜섬웨어', '피싱', '유출', '침해', '탈취', '감염', '차단', '대응', '예방',
        '정보보호', '개인정보', '데이터', '시스템', '네트워크', '서버', '클라우드',
        # 일반 용어
        '발생', '발견', '확인', '조사', '분석', '대상', '관련', '통해', '위해',
        '피해', '사고', '사건', '문제', '경고', '주의', '강화', '도입', '추진',
        '기업', '기관', '업계', '국내', '해외', '글로벌', '올해', '최근',
    }

    def extract_keywords(title: str) -> set:
        """제목에서 고유명사 위주 키워드 추출 (공통 보안 용어 제외)"""
        words = re.findall(r'[가-힣a-zA-Z0-9]+', title)
        # 2글자 이상 단어 중 불용어 제외
        keywords = {w.lower() for w in words if len(w) >= 2 and w not in STOPWORDS}
        return keywords
    
    unique = []
    keywords_cache = []  # 기존 기사 키워드 캐시 (unique와 동일 인덱스)

    for article in articles:
        title = article.get('title', '')
        is_duplicate = False

        # 현재 기사의 키워드 추출
        current_keywords = extract_keywords(title)

        # 기존 unique 리스트의 기사들과 비교
        for i, existing in enumerate(unique):
            existing_title = existing['title']
            existing_keywords = keywords_cache[i]

            # 1. 제목 유사도 체크 (60% 이상 → 중복)
            similarity = SequenceMatcher(
                None,
                title.lower(),
                existing_title.lower()
            ).ratio()

            # 2. 키워드 중복률 체크 (공통 키워드가 50% 이상 → 중복)
            if current_keywords and existing_keywords:
                common_keywords = current_keywords & existing_keywords
                keyword_overlap = len(common_keywords) / min(len(current_keywords), len(existing_keywords))
            else:
                keyword_overlap = 0

            # 유사도 60% 이상 OR 키워드 중복 50% 이상 → 중복으로 간주
            if similarity > 0.60 or keyword_overlap > 0.50:
                is_duplicate = True
                # 더 긴 제목(더 상세한 기사)을 선택
                if len(title) > len(existing_title):
                    unique[i] = article
                    keywords_cache[i] = current_keywords
                    logger.debug(f"   🔄 중복 교체 (유사도:{similarity:.0%}, 키워드:{keyword_overlap:.0%})")
                    logger.debug(f"      '{existing_title[:30]}...' → '{title[:30]}...'")
                break

        if not is_duplicate:
            unique.append(article)
            keywords_cache.append(current_keywords)
    
    removed_count = len(articles) - len(unique)
    if removed_count > 0:
        logger.info(f"   🗑️ 중복 제거: {len(articles)}개 → {len(unique)}개 ({removed_count}개 제거)")
    else:
        logger.info(f"   ✅ 중복 없음: {len(articles)}개 유지")
    
    return unique


# ==========================================
# AI 선별 (Groq API) - 배치 처리 방식
# ==========================================
def call_groq_batch_selection(
    items: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """
    Groq API (Llama 3.3 70B)를 사용하여 국내·해외 뉴스를 한 번에 선별합니다.
    (API 호출 2회 → 1회로 절감)

    Args:
        items: 선별할 뉴스 기사 리스트 (국내 + 해외)

    Returns:
        List[Dict]: 선별된 뉴스 기사 리스트
    """
    if not items:
        return []

    if not GROQ_API_KEY:
        logger.error("❌ Groq API 키가 없습니다.")
        return []

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        'Authorization': f'Bearer {GROQ_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # 시스템 프롬프트 (역할 정의)
    system_prompt = """너는 금융권 보안 뉴스 전문 큐레이터다.
각 기사에 점수를 매기고, 점수가 높은 순서로 선별한다.

[점수 기준] (중복 적용 가능, 합산)
- AI보안 (AI 활용 공격/방어, LLM 보안): +5점
- 침해사고 (해킹/유출/랜섬웨어/사이버공격): +5점
- 규제/정책/법률 (개보법, 신정법, 전자금융거래법, 전자금융감독규정, KISA, 금보원, 금감원, 금융당국 발표, 법규 개정): +7점
- 기술/취약점 (제로데이, 새 공격기법, CVE): +5점
- 금융권 직접 관련: +3점
- 신한 관련: +3점
- 국내 최초 보도 / 단독: +2점
- 글로벌 대형 사건: +2점

[감점/제외]
- 홍보성·광고성 기사: -10점 (사실상 제외)
- 단순 인사·조직개편: -10점
- 이미 선택한 기사와 같은 사건: 제외 (중복)"""
    
    # 사용자 프롬프트 (중복 제거 규칙 강화)
    user_prompt = f"""아래 기사 중에서:
- [국내] 태그 기사 중 상위 7개
- [해외] 태그 기사 중 상위 3개
총 10개를 선별해라.

⚠️ **중복 제거 규칙 (매우 중요)**:
1. 같은 사건/사고를 다룬 기사는 **반드시 1개만** 선택
2. 제목이 비슷한 기사들 중 **가장 상세한 1개**만 선택
3. 예시:
   ✅ "SK쉴더스, 충전기 해킹 성공" (선택)
   ❌ "SK쉴더스, 폰투온서 충전기 해킹" (위와 중복, 제외)
   ❌ "전기차 충전기 해킹... SK쉴더스" (위와 중복, 제외)
4. 다양한 사건을 다룬 기사를 선택 (한 사건에 5개 X)

⚠️ **해외 기사 필수**:
- [해외] 태그 기사를 **반드시 찾아서** 3개 선택
- [해외] 기사가 3개 미만이면 있는 만큼만 포함
- [해외] 기사가 없으면 국내 기사로만 10개 구성

[입력 데이터]
{json.dumps(items, ensure_ascii=False, indent=2)}

[출력 포맷]
JSON 배열로만 출력:
[
  {{
    "category": "[국내 or 해외]",
    "title": "제목 (해외 기사는 한글로 번역)",
    "title_original": "원문 제목 (해외 기사만, 국내는 생략)",
    "url": "링크",
    "detected_date": "YYYY-MM-DD",
    "summary": "150자 이내 3줄 요약. 기사의 핵심 사실만 간결하게 정리"
  }}
]

⚠️ **summary 규칙**:
- summary: 기사의 핵심 사실을 150자 이내, 3줄로 요약
- 전략적 제언, 시사점, 대응방안 등은 쓰지 말 것
- 기사에 나온 사실(누가, 무엇을, 어떻게)만 간결하게 정리

⚠️ **해외 기사 번역 규칙**:
- [해외] 기사의 title은 **반드시 한글로 번역**
- title_original에 영어 원문 보관
- 번역은 자연스럽고 이해하기 쉽게 (직역X, 의역O)
- 국내 기사는 title_original 필드 생략"""
    
    # OpenAI API 요청
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096
    }
    
    # 최대 3회 재시도
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=data, timeout=60)
            
            if res.status_code == 200:
                response_data = res.json()
                
                # OpenAI 응답에서 텍스트 추출
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    content = response_data['choices'][0]['message']['content']
                    clean_text = content.replace("```json", "").replace("```", "").strip()
                    
                    try:
                        # JSON 파싱 (배열 또는 객체)
                        parsed = json.loads(clean_text)

                        # 배열이 아니라 객체로 감싸진 경우 처리
                        if isinstance(parsed, dict):
                            # 모든 키를 검사하여 배열 찾기
                            result = []
                            for key, value in parsed.items():
                                if isinstance(value, list) and len(value) > 0:
                                    result = value
                                    logger.info(f"   📋 JSON 키 '{key}'에서 {len(value)}개 항목 발견")
                                    break

                            if not result:
                                logger.warning(f"   ⚠️ JSON 객체에서 배열을 찾을 수 없음")
                                logger.warning(f"   📄 응답 키: {list(parsed.keys())}")
                        else:
                            result = parsed
                        
                        # 필수 필드 검증
                        required_fields = {'title', 'url', 'category'}
                        result = [
                            item for item in result
                            if isinstance(item, dict) and required_fields.issubset(item.keys())
                        ]

                        if result:
                            # 국내 → 해외 순서로 정렬
                            domestic = [a for a in result if '[국내]' in a.get('category', '')]
                            overseas = [a for a in result if '[해외]' in a.get('category', '')]
                            result = domestic + overseas

                            overseas_count = len(overseas)
                            domestic_count = len(domestic)

                            # 국내 기사 부족 시 재시도 (Groq 모델 불안정 대응)
                            if domestic_count < 5 and attempt < 2:
                                logger.warning(f"   ⚠️ 국내 기사 {domestic_count}개만 선별됨 (목표: 7개). 재시도...")
                                time.sleep(3)
                                continue

                            # 해외 기사 부족 시 경고
                            if overseas_count == 0:
                                logger.warning("   ⚠️ 해외 기사가 선별되지 않았습니다.")
                            elif overseas_count < 3:
                                logger.warning(f"   ⚠️ 해외 기사 {overseas_count}개만 선별됨 (목표: 3개)")

                            logger.info(f"   ✅ AI 배치 선별 완료 (Groq): {len(result)}개 (국내 {domestic_count}, 해외 {overseas_count})")
                            return result
                        else:
                            logger.warning(f"   ⚠️ 선별된 기사가 없음")
                    except json.JSONDecodeError as e:
                        logger.warning(f"   ⚠️ JSON 파싱 실패: {e}")
                        logger.debug(f"   응답 내용: {clean_text[:200]}")
                        if attempt < 2:
                            continue
                        return []
                else:
                    logger.warning(f"   ⚠️ 응답 형식 오류")
                    return []
                    
            elif res.status_code == 429:
                wait_time = (attempt + 1) * 10
                logger.warning(f"   ⏳ [API 과부하] {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"   ❌ API 오류: {res.status_code} - {res.text[:200]}")
                if res.status_code >= 500:
                    time.sleep(10)
                    continue
                return []
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"   ⚠️ [연결 불안정] {e}. 10초 후 재시도 ({attempt+1}/3)...")
            time.sleep(10)
            continue
        except Exception as e:
            logger.error(f"   ❌ 예상치 못한 오류: {e}")
            if attempt < 2:
                time.sleep(10)
                continue
            return []
            
    logger.error(f"   ❌ 3회 재시도 실패")
    return []


# ==========================================
# 뉴스 처리 메인 함수 (배치 처리 최적화)
# ==========================================
def process_news() -> List[Dict[str, str]]:
    """
    국내 및 해외 뉴스를 수집하고 AI로 선별합니다.
    (배치 처리: API 호출 2회 → 1회로 절감)
    
    Returns:
        List[Dict]: 최종 선별된 뉴스 기사 리스트
    """
    try:
        # 1. 국내 + 해외 뉴스 병렬 수집
        logger.info("\n📰 [1단계] 뉴스 수집 중 (병렬 처리)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            kr_future = executor.submit(search_naver_news)
            en_future = executor.submit(search_tavily_news)
            kr_candidates = kr_future.result()
            en_candidates = en_future.result()
        
        # 3. 로컬 필터링 (명백한 제외 대상 사전 제거)
        logger.info("\n🔍 [2단계] 로컬 필터링 중...")
        if kr_candidates:
            kr_filtered = simple_rule_filter(kr_candidates)
        else:
            kr_filtered = []
            logger.warning("   ⚠️ 국내 후보 기사가 없습니다.")
        
        if en_candidates:
            en_filtered = simple_rule_filter(en_candidates)
        else:
            en_filtered = []
            logger.warning("   ⚠️ 해외 후보 기사가 없습니다.")
        
        # 4. 중복 제거 (제목 유사도 기반)
        logger.info("\n🗑️ [2.5단계] 중복 기사 제거 중...")
        all_candidates = kr_filtered + en_filtered
        
        if not all_candidates:
            logger.warning("⚠️ 필터링 후 후보 기사가 없습니다.")
            return []
        
        # 국내, 해외 각각 중복 제거 후 합치기
        kr_unique = remove_duplicate_articles(kr_filtered) if kr_filtered else []
        en_unique = remove_duplicate_articles(en_filtered) if en_filtered else []
        all_candidates = kr_unique + en_unique
        
        logger.info(f"   📊 중복 제거 후: {len(all_candidates)}개 (국내 {len(kr_unique)} + 해외 {len(en_unique)})")
        
        if not all_candidates:
            logger.warning("⚠️ 중복 제거 후 후보 기사가 없습니다.")
            return []
        
        logger.info(f"\n🤖 [3단계] AI가 국내 7개 + 해외 3개를 선별합니다...")
        logger.info(f"   💡 배치 처리로 API 호출 1회만 사용 (Groq Llama-3.3-70B)")

        final_list = call_groq_batch_selection(all_candidates)

        if final_list:
            # Groq 결과 검증 및 fallback
            domestic = [a for a in final_list if '[국내]' in a.get('category', '')]
            overseas = [a for a in final_list if '[해외]' in a.get('category', '')]

            need_fallback = False

            # 국내 기사 부족 시 로컬 점수 기반 보충
            if len(domestic) < 5 and kr_unique:
                need_fallback = True
                logger.warning(f"   ⚠️ 국내 기사 {len(domestic)}개로 부족. 로컬 점수 기반 fallback 적용")
                selected_urls = {a['url'] for a in final_list}
                fallback_kr = [a for a in kr_unique if a['url'] not in selected_urls]
                needed = 7 - len(domestic)
                for art in fallback_kr[:needed]:
                    domestic.append({
                        "category": "[국내]",
                        "title": art['title'],
                        "url": art['url'],
                        "detected_date": art.get('published_date', TODAY_STR),
                        "summary": art.get('description', '')[:150]
                    })
                logger.info(f"   🔄 국내 기사 {len(domestic)}개로 보충 완료")

            # 해외 기사 부족 시 로컬 보충
            if len(overseas) < 3 and en_unique:
                need_fallback = True
                logger.warning(f"   ⚠️ 해외 기사 {len(overseas)}개로 부족. 로컬 fallback 적용")
                selected_urls = {a['url'] for a in domestic + overseas}
                fallback_en = [a for a in en_unique if a['url'] not in selected_urls]
                needed = 3 - len(overseas)
                for art in fallback_en[:needed]:
                    overseas.append({
                        "category": "[해외]",
                        "title": art['title'],
                        "url": art['url'],
                        "detected_date": art.get('published_date', TODAY_STR),
                        "summary": art.get('description', '')[:150]
                    })
                logger.info(f"   🔄 해외 기사 {len(overseas)}개로 보충 완료")

            if need_fallback:
                final_list = domestic + overseas

            logger.info(f"   ✅ 최종 {len(final_list)}개 선별 완료 (국내 {len(domestic)}, 해외 {len(overseas)})")
        else:
            # Groq 완전 실패 시 전체 로컬 fallback
            logger.warning("   ⚠️ AI 선별 실패. 로컬 점수 기반 전체 fallback 적용")
            domestic = []
            for art in kr_unique[:7]:
                domestic.append({
                    "category": "[국내]",
                    "title": art['title'],
                    "url": art['url'],
                    "detected_date": art.get('published_date', TODAY_STR),
                    "summary": art.get('description', '')[:150]
                })
            overseas = []
            for art in en_unique[:3]:
                overseas.append({
                    "category": "[해외]",
                    "title": art['title'],
                    "url": art['url'],
                    "detected_date": art.get('published_date', TODAY_STR),
                    "summary": art.get('description', '')[:150]
                })
            final_list = domestic + overseas
            logger.info(f"   🔄 로컬 fallback 완료: {len(final_list)}개 (국내 {len(domestic)}, 해외 {len(overseas)})")

        return final_list
        
    except Exception as e:
        logger.error(f"❌ 뉴스 처리 중 오류: {e}")
        return []


# ==========================================
# 전략적 분석 리포트 생성 (GPT-4o)
# ==========================================
def generate_strategic_analysis(articles: List[Dict[str, str]]) -> str:
    """
    선별된 기사를 기반으로 전략적 분석 리포트를 생성합니다.
    GPT-4o를 사용하여 CISO/정보보호팀장 수준의 분석을 제공합니다.

    Args:
        articles: 선별된 뉴스 기사 리스트 (10개)

    Returns:
        str: 마크다운 형식의 전략적 분석 리포트
    """
    if not articles:
        return ""

    if not OPENAI_API_KEY:
        logger.error("❌ OpenAI API 키가 없습니다.")
        return ""

    logger.info("\n📝 [전략적 분석] GPT-4o로 리포트 생성 중...")

    # 기사 요약 목록 구성
    article_list = ""
    for i, art in enumerate(articles, 1):
        category = art.get('category', '')
        title = art.get('title', '')
        summary = art.get('summary', '')
        article_list += f"[{i}] {category} {title}\n    요약: {summary}\n"

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }

    system_prompt = """너는 금융권 CISO 자문역이다.
매일 선별된 보안 뉴스 10건을 종합 분석하여, 금융사 정보보호팀장이 경영진에게 보고할 수 있는 수준의 전략적 브리핑을 작성한다.

작성 원칙:
- 단순 사실 나열이 아닌 맥락과 의미 해석
- 금융권 특수성(규제, 고객데이터, 신뢰)을 반영
- 기사 번호를 [N] 형식으로 참조
- 한글 기준 1,500~3,000자"""

    user_prompt = f"""아래 10개 기사를 분석하여 3파트 전략적 리포트를 작성하라.

[기사 목록]
{article_list}

[출력 형식 - 마크다운]

## 1. 요약: (핵심 테마를 포괄하는 소제목)

당일 기사를 2~3개 핵심 테마로 묶어 분석.
각 테마에 소제목을 부여하고, 관련 기사를 [번호]로 참조.

### A. (테마 소제목)
분석 내용... [N][M]

### B. (테마 소제목)
분석 내용... [N]

## 2. 금융사 정보보호팀을 위한 전략적 제언

즉시 실행 가능한 3개 내외 액션 아이템. 각각 Logic과 Action 포함.

### ① (제언 제목)
- Logic: ...
- Action: ...

### ② (제언 제목)
- Logic: ...
- Action: ...

## 3. 생각해볼 질문

정보보호팀 내 토론용 도발적 질문 2~3개. 당일 기사와 연결하되 자사 적용 관점.

### Q1
질문 내용

### Q2
질문 내용"""

    data = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.4,
        "max_tokens": 4000
    }

    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=data, timeout=90)

            if res.status_code == 200:
                response_data = res.json()
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    content = response_data['choices'][0]['message']['content']
                    logger.info(f"   ✅ 전략적 분석 리포트 생성 완료 ({len(content)}자)")
                    return content
                else:
                    logger.warning("   ⚠️ 응답 형식 오류")
                    return ""
            elif res.status_code == 429:
                wait_time = (attempt + 1) * 15
                logger.warning(f"   ⏳ [API 과부하] {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"   ❌ API 오류: {res.status_code} - {res.text[:200]}")
                if res.status_code >= 500:
                    time.sleep(10)
                    continue
                return ""

        except requests.exceptions.RequestException as e:
            logger.warning(f"   ⚠️ [연결 불안정] {e}. 10초 후 재시도 ({attempt+1}/3)...")
            time.sleep(10)
            continue
        except Exception as e:
            logger.error(f"   ❌ 예상치 못한 오류: {e}")
            if attempt < 2:
                time.sleep(10)
                continue
            return ""

    logger.error("   ❌ 전략적 분석 리포트 생성 3회 재시도 실패")
    return ""


# ==========================================
# SQLite 저장
# ==========================================
def save_to_sqlite(
    articles: List[Dict[str, str]],
    analysis: str,
    date_str: str
) -> bool:
    """
    선별된 기사와 전략적 분석 리포트를 SQLite DB에 저장합니다.

    Args:
        articles: 선별된 뉴스 기사 리스트
        analysis: 전략적 분석 리포트 (마크다운)
        date_str: 날짜 문자열 (YYYY-MM-DD)

    Returns:
        bool: 저장 성공 여부
    """
    if not articles:
        logger.warning("⚠️ 저장할 기사가 없습니다.")
        return False

    db_path = Path(__file__).parent / "web" / "data" / "news.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n💾 [SQLite] {db_path} 에 저장 중...")

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 테이블 생성 (없으면)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_briefings (
                date        TEXT PRIMARY KEY,
                analysis    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                category        TEXT,
                title           TEXT NOT NULL,
                title_original  TEXT,
                url             TEXT NOT NULL,
                summary         TEXT,
                insight         TEXT,
                detected_date   TEXT,
                created_at      TEXT NOT NULL
            )
        """)

        now_iso = datetime.now(KST).isoformat()

        # 기존 데이터 삭제 (같은 날짜 중복 방지)
        cursor.execute("DELETE FROM daily_briefings WHERE date = ?", (date_str,))
        cursor.execute("DELETE FROM articles WHERE date = ?", (date_str,))

        # 분석 리포트 저장
        if analysis:
            cursor.execute(
                "INSERT INTO daily_briefings (date, analysis, created_at) VALUES (?, ?, ?)",
                (date_str, analysis, now_iso)
            )

        # 기사 저장
        for art in articles:
            cursor.execute(
                """INSERT INTO articles
                   (date, category, title, title_original, url, summary, insight, detected_date, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    date_str,
                    art.get('category', ''),
                    art.get('title', ''),
                    art.get('title_original', ''),
                    art.get('url', ''),
                    art.get('summary', ''),
                    '',
                    art.get('detected_date', ''),
                    now_iso
                )
            )

        conn.commit()
        conn.close()
        logger.info(f"   ✅ SQLite 저장 완료: 기사 {len(articles)}건, 분석 리포트 1건")
        return True

    except Exception as e:
        logger.error(f"   ❌ SQLite 저장 오류: {e}")
        return False


# ==========================================
# 텔레그램 전송
# ==========================================
def send_telegram(articles: List[Dict[str, str]]) -> bool:
    """
    선별된 뉴스 기사를 텔레그램으로 전송합니다.
    
    Args:
        articles: 전송할 뉴스 기사 리스트
    
    Returns:
        bool: 전송 성공 여부
    """
    if not articles:
        logger.warning("⚠️ 전송할 기사가 없습니다.")
        return False

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ 텔레그램 설정이 없어 텔레그램 전송을 건너뜁니다.")
        return False

    # 채팅 ID 검증 및 변환 (숫자 문자열로 변환)
    try:
        chat_id = str(TELEGRAM_CHAT_ID).strip()
        # 숫자로 변환 가능한지 확인
        int(chat_id)
    except ValueError:
        logger.error(f"❌ 텔레그램 채팅 ID가 올바르지 않습니다: {TELEGRAM_CHAT_ID}")
        logger.error("   💡 채팅 ID는 숫자여야 합니다. 개인 채팅의 경우 봇에게 먼저 메시지를 보내야 합니다.")
        return False

    logger.info("\n📱 텔레그램 전송 중...")
    
    # HTML 특수문자 이스케이프 함수
    def escape_html(text: str) -> str:
        """HTML 모드에서 사용할 수 있도록 특수문자를 이스케이프합니다."""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;'))

    def escape_url(url: str) -> str:
        """URL을 HTML 속성에 안전하게 삽입할 수 있도록 이스케이프합니다."""
        if not url:
            return ""
        return escape_html(url).replace('"', '&quot;')
    
    # 텔레그램 메시지 구성 (4096자 제한 고려, 분할 로직 통일)
    max_length = 4096
    messages = []
    current_message = f"🛡️ <b>{TODAY_STR} 보안 브리핑</b>\n\n"

    for i, item in enumerate(articles, 1):
        title = escape_html(item.get('title', ''))
        safe_url = escape_url(item.get('url', ''))
        display_url = escape_html(item.get('url', ''))
        category = escape_html(item.get('category', ''))

        new_line = f"{i}. {category} <b>{title}</b>\n"

        # 해외 기사 원문 표시
        if '[해외]' in item.get('category', '') and 'title_original' in item and item['title_original']:
            title_original = escape_html(item['title_original'])
            new_line += f"   🌐 <i>{title_original}</i>\n"

        new_line += f"   🔗 <a href=\"{safe_url}\">{display_url}</a>\n\n"

        if len(current_message) + len(new_line) > max_length - 50:
            messages.append(current_message + "<i>계속...</i>")
            current_message = f"🛡️ <b>{TODAY_STR} 보안 브리핑 (계속)</b>\n\n"

        current_message += new_line

    current_message += "<i>끝.</i>"
    messages.append(current_message)
    
    # 텔레그램 API로 메시지 전송
    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    success_count = 0
    for msg in messages:
        try:
            data = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }

            res = requests.post(telegram_api_url, json=data, timeout=10)
            
            if res.status_code == 200:
                success_count += 1
                logger.info(f"   ✅ 텔레그램 메시지 {success_count}/{len(messages)} 전송 완료")
            else:
                error_response = res.json() if res.text else {}
                error_description = error_response.get('description', res.text[:200])
                error_code = error_response.get('error_code', res.status_code)
                
                logger.error(f"   ❌ 텔레그램 전송 실패: {error_code} - {error_description}")
                
                # 자세한 오류 안내
                if "chat not found" in error_description.lower():
                    logger.error("   💡 해결 방법:")
                    logger.error("      1. 개인 채팅: 봇에게 먼저 메시지를 보내세요 (/start)")
                    logger.error("      2. 그룹 채팅: 봇을 그룹에 추가하고 관리자 권한을 부여하세요")
                    logger.error("      3. 채팅 ID 확인: @userinfobot에게 메시지를 보내서 ID를 확인하세요")
                    logger.error(f"      4. 현재 채팅 ID: {chat_id}")
                elif "unauthorized" in error_description.lower():
                    logger.error("   💡 봇 토큰이 올바르지 않습니다. GitHub Secrets를 확인하세요.")
                
                return False
                
            # 메시지 간 짧은 대기 (API 레이트 리밋 방지)
            if len(messages) > 1:
                time.sleep(1)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"   ❌ 텔레그램 전송 중 네트워크 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"   ❌ 텔레그램 전송 중 오류: {e}")
            return False
    
    if success_count == len(messages):
        logger.info("✅ 텔레그램 전송 완료")
        return True
    else:
        logger.warning(f"⚠️ 텔레그램 전송 부분 실패 ({success_count}/{len(messages)})")
        return False


# ==========================================
# 메인 실행
# ==========================================
def main():
    """메인 실행 함수"""
    global NOW, TODAY_STR, YESTERDAY
    NOW = datetime.now(KST)
    TODAY_STR = NOW.strftime("%Y-%m-%d")
    YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
    logger.info(f"📅 기준 날짜(KST): {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")

    try:
        logger.info("=" * 50)
        logger.info("금융권 보안 뉴스 봇 시작")
        logger.info("=" * 50)
        
        final_news = process_news()

        if final_news:
            logger.info(f"\n📊 최종 선별된 뉴스: {len(final_news)}개")

            # 텔레그램 전송 (기존)
            send_telegram(final_news)

            # 웹사이트용 처리 - 기사만 저장 (분석은 텔레그램 /분석 명령어로 별도 제공)
            try:
                save_to_sqlite(final_news, "", TODAY_STR)
            except Exception as e:
                logger.error(f"❌ 웹사이트 데이터 처리 실패 (텔레그램 전송에는 영향 없음): {e}")
        else:
            logger.warning("⚠️ 최종 선별된 뉴스가 없습니다.")
            
        logger.info("=" * 50)
        logger.info("프로그램 종료")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"프로그램 실행 중 치명적 오류: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
