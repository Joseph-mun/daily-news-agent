"""
금융권 보안 뉴스 수집 및 카카오톡 전송 봇

이 스크립트는 네이버 뉴스 API와 Tavily API를 사용하여
금융권 보안 관련 뉴스를 수집하고, Gemini AI로 선별한 후
카카오톡으로 전송합니다.
"""

import os
import json
import requests
import re
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
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
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID")
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")

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
    
    # 신한 관련 기사 우선 배치
    final_list.sort(key=lambda x: 0 if '신한' in x['title'] or '신한' in x['description'] else 1)
    
    # 상위 40개로 제한
    if len(final_list) > 40:
        final_list = final_list[:40]
        logger.info(f"   ✂️ 상위 40개로 압축 (신한 우선)")
        
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
# AI 선별 (Gemini API)
# ==========================================
def call_gemini_priority_selection(
    items: List[Dict[str, str]],
    mode: str
) -> List[Dict[str, str]]:
    """
    Gemini API를 사용하여 뉴스 기사를 우선순위에 따라 선별합니다.
    
    Args:
        items: 선별할 뉴스 기사 리스트
        mode: 'KR' (국내) 또는 'GLOBAL' (해외)
    
    Returns:
        List[Dict]: 선별된 뉴스 기사 리스트
    """
    if not items:
        return []
    
    if not GEMINI_KEY:
        logger.error("❌ Gemini API 키가 없습니다.")
        return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    if mode == 'KR':
        target_count = 7
        system_instruction = """
        너는 '금융권 보안 뉴스 큐레이터'다. 
        입력된 뉴스 목록 중에서 다음 **우선순위**에 따라 **상위 7개** 기사를 엄선해라.

        [우선순위 채점 기준]
        1. **1순위 (최우선):** 해킹 사고, 개인정보 유출, 랜섬웨어 등 실제 발생한 **침해 사고**.
        2. **2순위 (중요):** 금융보안원 발표, 금감원 규제, 최신 보안 기술 동향.
        3. **3순위 (참고):** '신한금융', '신한은행' 등 신한 계열사 소식 (없으면 생략).
        
        [절대 규칙]
        - **제목을 절대 수정하거나 요약하지 마라.** (오타 발생 원인이 된다. 원문 그대로 복사해라.)
        - 단순 홍보, 인사 발령, 중복된 내용은 제외해라.
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
            res = requests.post(url, headers=headers, json=data, timeout=30)
            
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
                    time.sleep(5)
                    continue
                return []
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"   ⚠️ [연결 불안정] {e}. 5초 후 재시도 ({attempt+1}/3)...")
            time.sleep(5)
            continue
        except Exception as e:
            logger.error(f"   ❌ 예상치 못한 오류: {e}")
            if attempt < 2:
                time.sleep(5)
                continue
            return []
            
    logger.error(f"   ❌ 3회 재시도 실패 ({mode})")
    return []


# ==========================================
# 뉴스 처리 메인 함수
# ==========================================
def process_news() -> List[Dict[str, str]]:
    """
    국내 및 해외 뉴스를 수집하고 AI로 선별합니다.
    
    Returns:
        List[Dict]: 최종 선별된 뉴스 기사 리스트
    """
    final_list = []
    
    # 1. 국내 뉴스 수집 및 선별
    try:
        kr_candidates = search_naver_news()
        
        if kr_candidates:
            logger.info("\n🤖 [국내] AI가 중요 뉴스 7개를 선별합니다 (오타 방지 모드)...")
            kr_selected = call_gemini_priority_selection(kr_candidates, 'KR')
            final_list.extend(kr_selected)
            logger.info(f"   ✅ 국내 {len(kr_selected)}개 선별 완료")
        else:
            logger.warning("   ⚠️ 국내 후보 기사가 없습니다.")
    except Exception as e:
        logger.error(f"국내 뉴스 처리 중 오류: {e}")
        
    time.sleep(3)  # API 레이트 리밋 방지
    
    # 2. 해외 뉴스 수집 및 선별
    try:
        en_candidates = search_tavily_news()
        
        if en_candidates:
            logger.info("\n🤖 [해외] AI가 중요 기사 3개를 선별하고 번역합니다...")
            en_selected = call_gemini_priority_selection(en_candidates, 'GLOBAL')
            final_list.extend(en_selected)
            logger.info(f"   ✅ 해외 {len(en_selected)}개 선별 완료")
        else:
            logger.warning("   ⚠️ 해외 후보 기사가 없습니다.")
    except Exception as e:
        logger.error(f"해외 뉴스 처리 중 오류: {e}")
        
    return final_list


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

    # 메시지 구성
    message_text = f"🛡️ {TODAY_STR} 보안 브리핑\n\n"
    
    for i, item in enumerate(articles, 1):
        message_text += f"{i}. {item.get('category', '')} {item.get('title', '')}\n"
        message_text += f"{item.get('url', '')}\n\n"
    
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
