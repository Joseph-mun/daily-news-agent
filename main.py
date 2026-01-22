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
# 3. 뉴스 검색 (파이썬 강제 필터링 추가)
# ==========================================
def search_news():
    print(f"\n🔍 [1단계] Tavily 뉴스 검색 시작...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    collected = []

    targets = [
        ("정보보호 해킹 개인정보유출", DOMAINS_KR, "[국내]"),
        ("Cyber Security Hacking Data Breach", DOMAINS_EN, "[해외]")
    ]

    for query, domains, category in targets:
        try:
            # days=2로 더 쪼임
            res = tavily.search(
                query=query, 
                topic="news", 
                days=2, 
                search_depth="advanced",
                include_domains=domains, 
                max_results=50
            )
            
            for item in res.get('results', []):
                pub_date = item.get('published_date', '')
                title = item.get('title', '')
                url = item.get('url', '')
                
                # [★ 핵심 추가] 파이썬 강제 검문소
                # Tavily가 준 날짜 데이터가 있는데, '2026'이 없으면 가차 없이 삭제
                # (None이거나 날짜가 아예 없으면 AI에게 판단을 넘김)
                if pub_date and '2026' not in pub_date:
                    print(f"   🗑️ [삭제됨/과거기사] {pub_date} | {title[:20]}...")
                    continue

                content = item.get('content', '')
                
                collected.append({
                    "category": category,
                    "title": title,
                    "url": url,
                    "published_date": pub_date,
                    "content": content
                })
        except Exception as e:
            print(f"❌ 검색 오류 ({category}): {e}")

    print(f"👉 1차 필터링 후 남은 기사: {len(collected)}건 (AI 정밀 검수 진행)")
    return collected

# ==========================================
# 4. AI 필터링 (본문 전체 정밀 분석)
# ==========================================
def ai_filter_and_format(news_list):
    if not news_list: return []
    print("\n🤖 [2단계] AI 정밀 검수 (본문 전체 분석 중)...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 깐깐한 보안 뉴스 편집장이다. 
    오늘 날짜: {TODAY_STR}
    어제 날짜: {YESTERDAY}
    
    [입력 데이터]
    {json.dumps(news_list)}

    [작업 지시]
    1. 각 기사의 'published_date'와 **'content'(본문 전체)**를 분석하여 **기사가 발행된 정확한 날짜**를 찾아라.
    2. **반드시 {YESTERDAY} 또는 {TODAY_STR} (최근 24시간 이내)**에 발행된 기사만 남겨라. 
    3. 남은 기사 중 [국내] 상위 7개, [해외] 상위 3개를 중요도 순으로 선별해라.
    4. 해외 기사 제목은 **자연스러운 한국어**로 번역해라.
    5. **요약은 하지 마라.** 오직 제목과 URL만 필요하다.
    
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
            res_json = res.json()
            if 'candidates' not in res_json:
                print("❌ AI 응답 없음 (Candidates Empty)")
                return []

            text = res_json['candidates'][0]['content']['parts'][0]['text']
            clean_text = text.replace("```json", "").replace("```", "").strip()
            
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                results = json.loads(match.group())
                
                print("\n📊 AI 검수 결과 로그:")
                for item in results:
                    print(f"   ✅ 통과: {item['detected_date']} | {item['title'][:30]}...")
                    
                return results
            else:
                print("⚠️ JSON 파싱 실패")
        else:
            print(f"❌ API 오류: {res.status_code}")
            print(res.text)
    except Exception as e:
        print(f"❌ AI 연결 오류: {e}")
    
    return []

# ==========================================
# 5. 카카오톡 전송
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

    message_text = f"🛡️ {TODAY_STR} 주요 보안 뉴스\n\n"
    
    for i, item in enumerate(articles, 1):
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
