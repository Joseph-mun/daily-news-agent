import os
import json
import requests
import re
import time
from datetime import datetime, timedelta
from tavily import TavilyClient

# ==========================================
# 1. 환경변수 및 날짜 설정
# ==========================================
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID")
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"📅 기준 날짜: {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")

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
# 3. 뉴스 검색 (날짜 데이터 확보 및 1차 필터)
# ==========================================
def search_news():
    print(f"\n🔍 [1단계] Tavily 뉴스 검색 시작...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    collected = []

    # 검색 쿼리 그룹
    targets = [
        ("정보보호 해킹 개인정보유출", DOMAINS_KR, "[국내]"),
        ("Cyber Security Hacking Data Breach", DOMAINS_EN, "[해외]")
    ]

    for query, domains, category in targets:
        try:
            # days=3 옵션 추가: 최근 3일치만 1차로 가져오기
            res = tavily.search(
                query=query, 
                topic="news", 
                days=3, 
                search_depth="advanced",
                include_domains=domains, 
                max_results=15
            )
            
            for item in res.get('results', []):
                # AI에게 판단을 맡기기 위해 'published_date'와 'content'를 함께 수집
                pub_date = item.get('published_date', '날짜없음')
                content = item.get('content', '')[:300] # 본문 앞 300자만
                
                collected.append({
                    "category": category,
                    "title": item['title'],
                    "url": item['url'],
                    "published_date": pub_date,
                    "content": content
                })
        except Exception as e:
            print(f"❌ 검색 오류 ({category}): {e}")

    print(f"👉 1차 수집된 기사: {len(collected)}건 (AI에게 날짜 검증 요청)")
    return collected

# ==========================================
# 4. AI 필터링 (날짜 검증 로직 강화)
# ==========================================
def ai_filter_and_format(news_list):
    if not news_list: return []
    print("\n🤖 [2단계] AI 정밀 검수 (날짜 확인 중)...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [수정] 사용자 요청 사항 반영된 강력한 프롬프트
    prompt = f"""
    너는 깐깐한 보안 뉴스 편집장이다. 
    오늘 날짜: {TODAY_STR}
    어제 날짜: {YESTERDAY}
    
    [입력 데이터]
    {json.dumps(news_list)}

    [작업 지시]
    1. 각 기사의 'published_date'와 'content'를 분석하여 **기사가 발행된 정확한 날짜**를 찾아라.
    2. **반드시 {YESTERDAY} 또는 {TODAY_STR} (최근 24시간 이내)**에 발행된 기사만 남겨라. 
       (2021년, 2025년 등 과거 기사는 무조건 삭제해라.)
    3. 남은 기사 중 [국내] 상위 7개, [해외] 상위 3개를 중요도 순으로 선별해라.
    4. 해외 기사 제목은 **자연스러운 한국어**로 번역해라.
    
    [출력 포맷 - 중요]
    검증을 위해 **'detected_date'(AI가 찾은 날짜)** 필드를 반드시 포함해라.
    JSON 리스트 형식:
    [
      {{ 
        "category": "[국내] 또는 [해외]", 
        "title": "기사 제목", 
        "url": "링크", 
        "detected_date": "찾아낸 날짜(YYYY-MM-DD)" 
      }}
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
                results = json.loads(match.group())
                
                # [로그 출력] AI가 날짜를 어떻게 인식했는지 확인
                print("\n📊 AI 검수 결과 로그:")
                for item in results:
                    print(f"   ✅ 통과: {item['detected_date']} | {item['title'][:30]}...")
                    
                return results
            else:
                print("⚠️ JSON 파싱 실패")
        else:
            print(f"❌ API 오류: {res.status_code}")
    except Exception as e:
        print(f"❌ AI 연결 오류: {e}")
    
    return []

# ==========================================
# 5. 카카오톡 전송 (넘버링 추가)
# ==========================================
def get_kakao_access_token():
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_CLIENT_ID,
        "refresh_token": KAKAO_REFRESH_TOKEN
    }
    res = requests.post(url, data=data)
    if res.status_code != 200:
        print(f"❌ 토큰 갱신 실패: {res.text}")
        return None
    return res.json().get("access_token")

def send_kakaotalk(articles):
    if not articles:
        print("⚠️ 전송할 유효 기사가 없습니다.")
        return

    print("\n🚀 [3단계] 카카오톡 전송 중...")
    access_token = get_kakao_access_token()
    if not access_token: return

    # [수정] 넘버링 추가 로직
    message_text = f"🛡️ {TODAY_STR} 주요 보안 뉴스\n\n"
    
    for i, item in enumerate(articles, 1):
        # 1. [국내] 기사제목
        # URL
        message_text += f"{i}. {item['category']} {item['title']}\n{item['url']}\n\n"
    
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
            print("⚠️ AI 필터링 결과: 적합한 최신 기사가 없습니다.")
    else:
        print("⚠️ 검색된 기사가 없습니다.")
