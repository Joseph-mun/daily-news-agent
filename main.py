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
# 3. 뉴스 검색 (광범위 수집 -> 정밀 필터링 -> 상위 25개 추출)
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
            # [전략 변경] 일단 넉넉하게 40개씩 요청 (쓰레기 데이터 걸러낼 여유 확보)
            res = tavily.search(
                query=query, 
                topic="news", 
                days=2, 
                search_depth="advanced",
                include_domains=domains, 
                max_results=40 
            )
            
            temp_list = []
            
            for item in res.get('results', []):
                pub_date = item.get('published_date', '')
                if pub_date is None: pub_date = ""
                
                # [강력 필터] 날짜 정보가 있고, '2026'이나 'ago'(시간 전)가 없으면 과감히 버림
                # 예: '2021-05...', '2024-12...' -> 탈락
                # 예: '2026-01...', '2 hours ago' -> 통과
                if pub_date and ('2026' not in pub_date and 'ago' not in pub_date):
                     continue

                title = item.get('title', '')
                content = item.get('content', '')
                
                temp_list.append({
                    "category": category,
                    "title": title,
                    "url": item['url'],
                    "published_date": pub_date,
                    "content": content
                })
            
            # [최종 커팅] 필터를 통과한 '알짜배기' 중에서 앞에서부터 25개만 선정
            selected_items = temp_list[:25]
            collected.extend(selected_items)
            
            print(f"   👉 {category}: 40개 검색 -> 필터링 후 {len(selected_items)}개 선정")

        except Exception as e:
            print(f"❌ 검색 오류 ({category}): {e}")

    print(f"👉 총 수집된 기사: {len(collected)}건 (AI 정밀 검수 진행)")
    return collected

# ==========================================
# 4. AI 필터링 (배치 처리 + 본문 전체 분석)
# ==========================================
def call_gemini_batch(batch_items):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    오늘: {TODAY_STR} / 어제: {YESTERDAY}
    
    [입력 데이터]
    {json.dumps(batch_items)}

    [지시사항]
    1. 각 기사의 'published_date'와 'content'를 분석해 정확한 발행일을 찾아라.
    2. **반드시 {YESTERDAY} 또는 {TODAY_STR} (최근 24시간)** 기사만 남겨라.
    3. 남은 기사의 제목은 한국어로 번역하고, 요약 없이 제목/URL만 남겨라.
    
    [출력 포맷]
    JSON 리스트:
    [
      {{ "category": "[국내]or[해외]", "title": "제목", "url": "링크", "detected_date": "YYYY-MM-DD" }}
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
        print(f"    ⚠️ 배치 처리 중 에러: {e}")
    
    return []

def ai_filter_and_format(news_list):
    if not news_list: return []
    print("\n🤖 [2단계] AI 정밀 검수 (배치 처리 시작)...")
    
    final_results = []
    # 5개씩 끊어서 처리
    BATCH_SIZE = 5 
    
    for i in range(0, len(news_list), BATCH_SIZE):
        batch = news_list[i : i + BATCH_SIZE]
        print(f"   📡 {i+1}~{i+len(batch)}번째 기사 분석 중...")
        
        results = call_gemini_batch(batch)
        if results:
            for item in results:
                print(f"      ✅ 확보: {item.get('detected_date')} | {item['title'][:20]}...")
                final_results.extend(results)
        
        time.sleep(2)

    unique_results = {v['url']: v for v in final_results}.values()
    sorted_results = sorted(unique_results, key=lambda x: x.get('detected_date', ''), reverse=True)
    
    kr_list = [x for x in sorted_results if "[국내]" in x['category']][:7]
    en_list = [x for x in sorted_results if "[해외]" in x['category']][:3]
    
    return kr_list + en_list

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
