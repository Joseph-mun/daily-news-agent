import os
import json
import requests
import re
import time
from datetime import datetime
from tavily import TavilyClient

# ==========================================
# 1. 환경변수 설정
# ==========================================
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID")       # REST API 키
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN") # 리프레시 토큰

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")

# ==========================================
# 2. 도메인 리스트
# ==========================================
DOMAINS_KR = [
    "news.naver.com", "boannews.com", "dailysecu.com", "etnews.com", 
    "zdnet.co.kr", "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", 
    "bloter.net", "itworld.co.kr", "byline.network", "ciokorea.com",
    "yna.co.kr", "news1.kr", "newsis.com"
]
DOMAINS_EN = [
    "thehackernews.com", "bleepingcomputer.com", "darkreading.com", 
    "infosecurity-magazine.com", "scmagazine.com", "cyberscoop.com",
    "securityweek.com", "wired.com", "techcrunch.com"
]

# ==========================================
# 3. 뉴스 검색
# ==========================================
def search_news():
    print(f"🔍 뉴스 수집 시작: {TODAY_STR}")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    collected = []

    # 통합 검색 (쿼리 단순화)
    targets = [
        ("정보보호 해킹 개인정보유출", DOMAINS_KR, "[국내]"),
        ("Cyber Security Hacking Data Breach", DOMAINS_EN, "[해외]")
    ]

    for query, domains, category in targets:
        try:
            res = tavily.search(
                query=query, topic="news", search_depth="advanced",
                include_domains=domains, max_results=20
            )
            for item in res.get('results', []):
                item['category'] = category
                # 토큰 절약을 위해 본문은 아예 제거하고 제목/URL만 남김
                collected.append({
                    "title": item['title'],
                    "url": item['url'],
                    "category": category
                })
        except Exception as e:
            print(f"❌ 검색 오류 ({category}): {e}")

    print(f"👉 총 수집 기사: {len(collected)}건")
    return collected

# ==========================================
# 4. AI 필터링 (제목/URL만 추출)
# ==========================================
def ai_filter_and_format(news_list):
    if not news_list: return []
    print("🤖 AI 필터링 시작...")
    
    # 배치 처리 없이 한 번에 보내도 됨 (요약이 없어서 데이터가 작음)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    오늘 날짜: {TODAY_STR}
    
    [입력 데이터]
    {json.dumps(news_list)}

    [지시사항]
    1. 기사 전체를 스캔하여 날짜 중에서 **기사가 발행된 날짜**를 찾아라
    2. **오늘 날짜로부터 1일 이내**에 발생한 최신 보안 뉴스만 남겨라. (과거 기사 삭제)
    3. [국내] 상위 7개, [해외] 상위 3개를 선별해라.
    4. 해외 기사 제목은 **한국어로 번역**해라.
    5. **요약은 하지 마라.** 오직 제목과 URL만 필요하다.
    
    [출력 포맷]
    JSON 리스트:
    [
      {{ "category": "[국내] 또는 [해외]", "title": "기사 제목", "url": "링크" }}
    ]
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        res = requests.post(url, headers=headers, json=data)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            clean_text = text.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                return json.loads(match.group())
    except Exception as e:
        print(f"❌ AI 오류: {e}")
    
    return []

# ==========================================
# 5. 카카오톡 전송 로직
# ==========================================
def get_kakao_access_token():
    """리프레시 토큰으로 새로운 액세스 토큰 발급"""
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_CLIENT_ID,
        "refresh_token": KAKAO_REFRESH_TOKEN
    }
    res = requests.post(url, data=data)
    tokens = res.json()
    
    if "access_token" in tokens:
        return tokens["access_token"]
    else:
        print(f"❌ 토큰 갱신 실패: {tokens}")
        return None

def send_kakaotalk(articles):
    if not articles:
        print("⚠️ 보낼 기사가 없습니다.")
        return

    print("🚀 카카오톡 전송 준비...")
    access_token = get_kakao_access_token()
    if not access_token: return

    # 메시지 본문 구성 (텍스트 형태)
    message_text = f"🛡️ {TODAY_STR} 주요 보안 뉴스\n\n"
    
    for item in articles:
        # 예: [국내] 해킹 사고 발생\nhttp://...\n
        message_text += f"{item['category']} {item['title']}\n{item['url']}\n\n"
    
    message_text += "끝."

    # 카톡 나에게 보내기 API 호출
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": message_text,
            "link": {
                "web_url": "https://www.google.com",
                "mobile_web_url": "https://www.google.com"
            },
            "button_title": "뉴스 확인"
        })
    }
    
    res = requests.post(url, headers=headers, data=data)
    if res.status_code == 200:
        print("✅ 카카오톡 전송 완료!")
    else:
        print(f"❌ 전송 실패: {res.text}")

# ==========================================
# 6. 메인 실행
# ==========================================
if __name__ == "__main__":
    news = search_news()
    if news:
        final_list = ai_filter_and_format(news)
        if final_list:
            send_kakaotalk(final_list)
        else:
            print("⚠️ AI 필터링 결과 없음")
    else:
        print("⚠️ 검색 결과 없음")
