"""
금융권 보안 뉴스 수집 및 카카오톡/텔레그램 전송 봇

이 스크립트는 네이버 뉴스 API와 Tavily API를 사용하여
금융권 보안 관련 뉴스를 수집하고, Gemini AI로 선별한 후
카카오톡과 텔레그램으로 전송합니다.
"""

import os
import json
import requests
import re
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID")
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

logger.info(f"📅 기준 날짜: {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")


# ==========================================
# 국내 뉴스 검색 (네이버 API)
# ==========================================
def search_naver_news() -> List[Dict[str, str]]:
    """
    네이버 뉴스 API를 사용하여 국내 보안 뉴스를 검색합니다.
    
    Returns:
        List[Dict]: 수집된 뉴스 기사 리스트
    """
    keywords = ["정보보호", "해킹", "개인정보유출", "금융보안", "랜섬웨어"]
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
                    clean_title = clean_title.replace("&quot;", "'").replace("&amp;", "&")
                    
                    clean_desc = re.sub('<.+?>', '', item.get('description', ''))
                    clean_desc = clean_desc.replace("&quot;", "'").replace("&amp;", "&")

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
        
        # 1순위 키워드 (침해사고) - 10점
        high_priority = ['해킹', '유출', '랜섬웨어', '사이버공격', '보안사고', '침해']
        score += sum(10 for k in high_priority if k in title or k in desc)
        
        # 2순위 키워드 (제도/기술) - 5점
        mid_priority = ['금융보안원', '금감원', '규제', '보안기술', '제로데이', '취약점']
        score += sum(5 for k in mid_priority if k in title or k in desc)
        
        # 3순위 키워드 (신한) - 3점
        if '신한' in title or '신한' in desc:
            score += 3
        
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
            
            # 날짜 필터링 (2026년이 아니거나 'ago'가 포함된 경우 제외)
            if pub_date and ('2026' not in pub_date and 'ago' not in pub_date):
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
    제목 유사도 기반으로 중복 기사를 제거합니다.
    같은 사건을 다룬 여러 언론사의 기사 중 하나만 선택합니다.
    
    Args:
        articles: 중복 제거할 뉴스 기사 리스트
    
    Returns:
        List[Dict]: 중복이 제거된 뉴스 기사 리스트
    """
    if not articles:
        return []
    
    unique = []
    
    for article in articles:
        title = article.get('title', '')
        is_duplicate = False
        
        # 기존 unique 리스트의 기사들과 유사도 비교
        for i, existing in enumerate(unique):
            similarity = SequenceMatcher(
                None,
                title.lower(),
                existing['title'].lower()
            ).ratio()
            
            # 70% 이상 유사하면 중복으로 간주
            if similarity > 0.70:
                is_duplicate = True
                # 더 긴 제목(더 상세한 기사)을 선택
                if len(title) > len(existing['title']):
                    unique[i] = article
                    logger.debug(f"   🔄 중복 교체: '{existing['title'][:30]}...' → '{title[:30]}...'")
                break
        
        if not is_duplicate:
            unique.append(article)
    
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
    Groq API를 사용하여 국내·해외 뉴스를 한 번에 선별하고 요약합니다.
    (API 호출 2회 → 1회로 절감, Groq의 빠른 추론 속도 활용)
    
    Args:
        items: 선별할 뉴스 기사 리스트 (국내 + 해외)
    
    Returns:
        List[Dict]: 선별된 뉴스 기사 리스트 (요약 포함)
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
뉴스를 우선순위에 따라 선별하고 핵심 내용을 2줄로 요약한다.

우선순위:
1. 침해사고 (해킹/유출/랜섬웨어/사이버공격) - 최우선
2. 규제/정책 (금융당국·보안원 발표, 법규 개정)
3. 기술/취약점 (제로데이, 새 공격기법)
4. 신한 관련 (+가점)

제외: 홍보성, 단순 인사, 중복 내용"""
    
    # 사용자 프롬프트 (중복 제거 규칙 강화)
    user_prompt = f"""아래 기사 중에서:
- [국내] 태그 기사 중 상위 7개
- [해외] 태그 기사 중 상위 3개
총 10개를 선별하고, 각 기사를 2줄로 요약해라.

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
    "title": "제목 (원문 그대로)",
    "url": "링크",
    "detected_date": "YYYY-MM-DD",
    "summary": "핵심 내용 2줄 요약 (각 줄 25자 내외)"
  }}
]"""
    
    # Groq API 요청 (OpenAI 호환 형식)
    data = {
        "model": "llama-3.3-70b-versatile",  # Groq의 빠르고 강력한 모델
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"}
    }
    
    # 최대 3회 재시도
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=data, timeout=60)
            
            if res.status_code == 200:
                response_data = res.json()
                
                # Groq 응답에서 텍스트 추출
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    content = response_data['choices'][0]['message']['content']
                    clean_text = content.replace("```json", "").replace("```", "").strip()
                    
                    try:
                        # JSON 파싱 (배열 또는 객체)
                        parsed = json.loads(clean_text)
                        
                        # 배열이 아니라 객체로 감싸진 경우 처리
                        if isinstance(parsed, dict):
                            # {"articles": [...]} 형식일 경우
                            for key in ['articles', 'results', 'data', 'items']:
                                if key in parsed and isinstance(parsed[key], list):
                                    result = parsed[key]
                                    break
                            else:
                                logger.warning(f"   ⚠️ JSON 객체에서 배열을 찾을 수 없음")
                                result = []
                        else:
                            result = parsed
                        
                        if result:
                            # 해외 기사 개수 확인
                            overseas_count = len([a for a in result if '[해외]' in a.get('category', '')])
                            domestic_count = len(result) - overseas_count
                            
                            # 해외 기사 부족 시 경고
                            if overseas_count == 0:
                                logger.warning("   ⚠️ 해외 기사가 선별되지 않았습니다.")
                                logger.warning("   💡 Tavily 검색 결과 확인 또는 검색 키워드 조정 필요")
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
# [구 버전] Gemini 함수는 제거됨
# 현재는 Groq API (call_groq_batch_selection) 사용
# ==========================================
    
    if mode == 'KR':
        target_count = 7
        system_instruction = """
        너는 금융권 보안 뉴스 전문 큐레이터다.
        입력된 뉴스를 아래 평가 기준으로 점수화하고, 상위 7개를 선정해라.

        [평가 점수표]
        1. 침해사고 관련 (10점)
           - 실제 해킹/랜섬웨어 발생 사건
           - 개인정보/금융정보 유출 사고
           - 사이버 공격으로 인한 피해
           
        2. 규제/정책 (7점)
           - 금융보안원, 금감원 발표
           - 새로운 보안 규제/가이드라인
           - 법률 개정
           
        3. 기술/취약점 (5점)
           - 제로데이 취약점 발견
           - 새로운 공격 기법
           - 보안 기술 동향
           
        4. 신한 관련 (3점 가산)
           - 신한금융그룹 계열사 관련 뉴스
           
        5. 제외 대상 (-점수)
           - 단순 홍보성 기사
           - 인사 발령
           - 중복 내용

        [선정 절차]
        1. 각 기사를 위 기준으로 평가
        2. 같은 사건의 중복 기사는 1개만 선택
        3. 다양한 카테고리에서 균형있게 선택
        4. 최종 7개 선정

        [출력 규칙]
        - 제목은 원문 그대로 수정 없이
        - detected_date 형식: YYYY-MM-DD
        """
    else:
        target_count = 3
        system_instruction = """
        너는 '글로벌 보안 트렌드 분석가'이다.
        입력된 뉴스 목록 중에서 **가장 파급력이 큰 3개** 기사를 선정해라.
        1. 기사 제목을 반드시 **자연스러운 한국어**로 번역해라.
        2. 우선순위: 대규모 데이터 유출 > 제로데이 취약점 > 글로벌 보안 정책.
        """

    prompt = f"""
    [입력 데이터]
    {json.dumps(items, ensure_ascii=False, indent=2)}

    [지시사항]
    {system_instruction}
    
    [출력 포맷]
    선정된 {target_count}개의 기사를 아래 JSON 리스트 포맷으로 출력해라:
    [
      {{ "category": "[{ '국내' if mode == 'KR' else '해외' }]", "title": "제목", "url": "링크", "detected_date": "YYYY-MM-DD" }}
    ]
    """
    
    # temperature: 0.1 설정 (창의성 억제 -> 정확도 상승)
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1
        }
    }
    
    # 최대 3회 재시도
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=data, timeout=60)
            
            if res.status_code == 200:
                text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean_text = text.replace("```json", "").replace("```", "").strip()
                
                try:
                    # JSON 추출
                    start = clean_text.find('[')
                    end = clean_text.rfind(']') + 1
                    if start >= 0 and end > start:
                        result = json.loads(clean_text[start:end])
                        logger.info(f"   ✅ AI 선별 완료 ({mode}): {len(result)}개")
                        return result
                    else:
                        logger.warning(f"   ⚠️ JSON 구조를 찾을 수 없음 ({mode})")
                except json.JSONDecodeError as e:
                    logger.warning(f"   ⚠️ JSON 파싱 실패 ({mode}): {e}")
                    if attempt < 2:
                        continue
                    return []
                    
            elif res.status_code == 429:
                wait_time = (attempt + 1) * 10
                logger.warning(f"   ⏳ [AI 과부하] {wait_time}초 대기 후 재시도...")
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
            
    logger.error(f"   ❌ 3회 재시도 실패 ({mode})")
    return []


# ==========================================
# 뉴스 처리 메인 함수 (배치 처리 최적화)
# ==========================================
def process_news() -> List[Dict[str, str]]:
    """
    국내 및 해외 뉴스를 수집하고 AI로 선별합니다.
    (배치 처리: API 호출 2회 → 1회로 절감)
    
    Returns:
        List[Dict]: 최종 선별된 뉴스 기사 리스트 (요약 포함)
    """
    try:
        # 1. 국내 뉴스 수집
        logger.info("\n📰 [1단계] 뉴스 수집 중...")
        kr_candidates = search_naver_news()
        
        # 2. 해외 뉴스 수집
        en_candidates = search_tavily_news()
        
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
        
        logger.info(f"\n🤖 [3단계] AI가 국내 7개 + 해외 3개를 선별하고 요약합니다...")
        logger.info(f"   💡 배치 처리로 API 호출 1회만 사용 (Groq의 빠른 추론 속도)")
        
        final_list = call_groq_batch_selection(all_candidates)
        
        if final_list:
            logger.info(f"   ✅ 최종 {len(final_list)}개 선별 완료 (요약 포함)")
        else:
            logger.warning("   ⚠️ AI 선별 실패")
        
        return final_list
        
    except Exception as e:
        logger.error(f"❌ 뉴스 처리 중 오류: {e}")
        return []


# ==========================================
# 카카오톡 전송
# ==========================================
def get_kakao_access_token() -> Optional[str]:
    """
    카카오 API를 사용하여 액세스 토큰을 갱신합니다.
    
    Returns:
        Optional[str]: 액세스 토큰 또는 None
    """
    if not KAKAO_CLIENT_ID or not KAKAO_REFRESH_TOKEN:
        logger.error("❌ 카카오 API 키가 없습니다.")
        return None
        
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_CLIENT_ID,
        "refresh_token": KAKAO_REFRESH_TOKEN
    }
    
    try:
        res = requests.post(url, data=data, timeout=10)
        if res.status_code == 200:
            return res.json().get("access_token")
        else:
            logger.error(f"❌ 토큰 갱신 실패: {res.status_code} - {res.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"❌ 토큰 갱신 중 오류: {e}")
        return None


def send_kakaotalk(articles: List[Dict[str, str]]) -> bool:
    """
    선별된 뉴스 기사를 카카오톡으로 전송합니다.
    
    Args:
        articles: 전송할 뉴스 기사 리스트
    
    Returns:
        bool: 전송 성공 여부
    """
    if not articles:
        logger.warning("⚠️ 전송할 기사가 없습니다.")
        return False

    logger.info("\n🚀 카카오톡 전송 중...")
    access_token = get_kakao_access_token()
    
    if not access_token:
        logger.error("❌ 액세스 토큰을 가져올 수 없습니다.")
        return False

    # 메시지 구성 (요약 포함)
    message_text = f"🛡️ {TODAY_STR} 보안 브리핑\n\n"
    
    for i, item in enumerate(articles, 1):
        message_text += f"{i}. {item.get('category', '')} {item.get('title', '')}\n"
        
        # 요약 추가
        if 'summary' in item and item['summary']:
            message_text += f"   💬 {item['summary']}\n"
        
        message_text += f"   🔗 {item.get('url', '')}\n\n"
    
    message_text += "끝."

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": message_text,
            "link": {
                "web_url": "https://m.naver.com",
                "mobile_web_url": "https://m.naver.com"
            },
            "button_title": "뉴스 더보기"
        }, ensure_ascii=False)
    }
    
    try:
        res = requests.post(url, headers=headers, data=data, timeout=10)
        if res.status_code == 200:
            logger.info("✅ 카카오톡 전송 완료")
            return True
        else:
            logger.error(f"❌ 전송 실패: {res.status_code} - {res.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"❌ 전송 중 오류: {e}")
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
    
    # 텔레그램 메시지 구성 (4096자 제한 고려, 요약 포함)
    message_text = f"🛡️ <b>{TODAY_STR} 보안 브리핑</b>\n\n"
    
    for i, item in enumerate(articles, 1):
        title = escape_html(item.get('title', ''))
        url = item.get('url', '')
        category = escape_html(item.get('category', ''))
        
        message_text += f"{i}. {category} <b>{title}</b>\n"
        
        # 요약 추가
        if 'summary' in item and item['summary']:
            summary = escape_html(item['summary'])
            message_text += f"   💬 <i>{summary}</i>\n"
        
        message_text += f"   🔗 <a href=\"{url}\">{url}</a>\n\n"
    
    message_text += "<i>끝.</i>"
    
    # 텔레그램 메시지 길이 제한 (4096자) 확인 및 분할
    max_length = 4096
    if len(message_text) > max_length:
        # 메시지가 너무 길면 여러 개로 분할
        messages = []
        current_message = f"🛡️ <b>{TODAY_STR} 보안 브리핑</b>\n\n"
        
        for i, item in enumerate(articles, 1):
            title = escape_html(item.get('title', ''))
            url = item.get('url', '')
            category = escape_html(item.get('category', ''))
            
            new_line = f"{i}. {category} <b>{title}</b>\n"
            
            # 요약 추가
            if 'summary' in item and item['summary']:
                summary = escape_html(item['summary'])
                new_line += f"   💬 <i>{summary}</i>\n"
            
            new_line += f"   🔗 <a href=\"{url}\">{url}</a>\n\n"
            
            if len(current_message) + len(new_line) > max_length - 50:  # 여유 공간 확보
                messages.append(current_message + "<i>계속...</i>")
                current_message = f"🛡️ <b>{TODAY_STR} 보안 브리핑 (계속)</b>\n\n"
            
            current_message += new_line
        
        current_message += "<i>끝.</i>"
        messages.append(current_message)
    else:
        messages = [message_text]
    
    # 텔레그램 API로 메시지 전송
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    success_count = 0
    for msg in messages:
        try:
            data = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            
            res = requests.post(url, json=data, timeout=10)
            
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
    try:
        logger.info("=" * 50)
        logger.info("금융권 보안 뉴스 봇 시작")
        logger.info("=" * 50)
        
        final_news = process_news()
        
        if final_news:
            logger.info(f"\n📊 최종 선별된 뉴스: {len(final_news)}개")
            send_kakaotalk(final_news)
            send_telegram(final_news)
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
