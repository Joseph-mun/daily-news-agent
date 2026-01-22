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
NAVER_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID")
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"📅 기준 날짜: {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")

# ==========================================
# 2. 국내 뉴스 (네이버 API)
# ==========================================
def search_naver_news():
    print(f"\n🇰🇷 [국내] 네이버 뉴스 검색 시작...")
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 네이버 API 키가 없습니다.")
        return []

    query = "정보보호 해킹 개인정보유출 보안 침해사고"
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    params = {"query": query, "display": 30, "sort": "date"}
    
    collected = []
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                try:
                    pub_date_str = item['pubDate']
                    pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S +0900")
                    pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                    if pub_date_fmt < YESTERDAY: continue
                except:
                    pub_date_fmt = "날짜파싱불가"

                clean_title = re.sub('<.+?>', '', item['title']).replace("&quot;", "'").replace("&amp;", "&")
                collected.append({
                    "category": "[국내]",
                    "title": clean_title,
                    "url": item['originallink'] or item['link'],
                    "published_date": pub_date_fmt,
                    "content": re.sub('<.+?>', '', item['description'])
                })
            print(f"   👉 네이버 최신 뉴스: {len(collected)}건 확보")
    except Exception as e:
        print(f"❌ 네이버 요청 실패: {e}")
    return collected

# ==========================================
# 3. 해외 뉴스 (Tavily - 필터 제거 / 수집량 확대)
# ==========================================
def search_tavily_news():
    print(f"\n🇺🇸 [해외] Tavily 뉴스 검색 시작...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    collected = []
    
    domains_en = [
        "thehackernews.com", "bleepingcomputer.com", "darkreading.com", 
        "infosecurity-magazine.com", "scmagazine.com", "cyberscoop.com",
        "securityweek.com", "wired.com", "techcrunch.com"
    ]
    
    try:
        # 20개를 요청해서 Tavily가 주는 대로 다 받아옵니다. (날짜 필터 제거됨)
        res = tavily.search(
            query="Cyber Security Hacking Data Breach", 
            topic="news", 
            days=2, 
            search_depth="advanced",
            include_domains=domains_en, 
            max_results=20
        )
        
        temp_list = []
        for item in res.get('results', []):
            # [수정됨] 강제 날짜 검문소 삭제!
            # Tavily가 '최신'이라고 판단해서 준 거면 일단 믿고 가져옵니다.
            
            temp_list.append({
                "category": "[해외]",
                "title": item['title'],
                "url": item['url'],
                "published_date": item.get('published_date', ''),
                "content": item.get('content', '')
            })
        
        # 앞에서부터 25개만 끊어서 가져갑니다.
        collected = temp_list[:20]
        print(f"   👉 Tavily 해외 뉴스: {len(temp_list)}개 중 {len(collected)}건 전달")
        
    except Exception as e:
        print(f"❌ Tavily 검색 오류: {e}")

    return collected

# ==========================================
# 4. AI 필터링 (배치 처리)
# ==========================================
def call_gemini_batch(batch_items):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    오늘: {TODAY_STR} / 어제: {YESTERDAY}
    
    [입력 데이터]
    {json.dumps(batch_items)}

    [지시사항]
    1. 각 기사의 'published_date'와 내용을 보고 **정확한 날짜**를 판단해라.
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
    except Exception:
        pass
    return []

def ai_filter_and_format(news_list):
    if not news_list: return []
    print("\n🤖 [3단계] AI 정밀 검수 (배치 처리)...")
    
    final_results = []
    BATCH_SIZE = 5 
    
    for i in range(0, len(news_list), BATCH_SIZE):
        batch = news_list[i : i + BATCH_SIZE]
        results = call_gemini_batch(batch)
        if results:
            for item in results:
                print(f"      ✅ 확보: {item.get('detected_date')} | {item['title'][:20]}...")
                final_results.extend(results)
        time.sleep(1)

    unique_results = {v['url']: v for v in final_results}.values()
    sorted_results = sorted(unique_results, key=lambda x: x.get('detected_date', ''), reverse=True)
    
    # 국내 7개, 해외 3개
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

    print("\n🚀 [4단계] 카카오톡 전송 중...")
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
                "web_url": "https://www.google.com/search?q=정보보호+해킹+뉴스&tbm=nws",
                "mobile_web_url": "https://www.google.com/search?q=정보보호+해킹+뉴스&tbm=nws"
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
    kr_news = search_naver_news()
    en_news = search_tavily_news()
    
    all_news = kr_news + en_news
    
    if all_news:
        final_list = ai_filter_and_format(all_news)
        if final_list:
            send_kakaotalk(final_list)
        else:
            print("⚠️ AI 필터링 결과: 적합한 최신 기사가 없습니다.")
    else:
        print("⚠️ 검색된 기사가 없습니다.")
