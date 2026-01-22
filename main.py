import os
import json
import requests
import re
import time
from datetime import datetime, timedelta

# ==========================================
# 1. 환경변수 설정
# ==========================================
# [네이버 키]
NAVER_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# [카카오 키]
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID")
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"📅 기준 날짜: {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")

# ==========================================
# 2. 통합 뉴스 검색 (네이버 API)
# ==========================================
def search_naver_news(query, category):
    print(f"\n🔎 [{category}] 네이버 뉴스 검색 시작: {query}")
    
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 네이버 API 키가 없습니다.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET
    }
    
    # 해외는 검색 풀을 넓히기 위해 40개, 국내는 30개 요청
    display_count = 40 if category == "[해외]" else 30
    
    params = {
        "query": query,
        "display": display_count,
        "sort": "date" 
    }
    
    collected = []
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                # 1. 날짜 필터링
                try:
                    pub_date_str = item['pubDate']
                    # 네이버 포맷: "Thu, 23 Jan 2026 10:00:00 +0900"
                    pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S +0900")
                    pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                    
                    # 어제 이후 기사만 통과
                    if pub_date_fmt < YESTERDAY:
                        continue
                except:
                    pub_date_fmt = "날짜파싱불가"

                # 2. 텍스트 정제 (HTML 태그 제거)
                clean_title = re.sub('<.+?>', '', item['title']).replace("&quot;", "'").replace("&amp;", "&")
                clean_desc = re.sub('<.+?>', '', item['description']).replace("&quot;", "'").replace("&amp;", "&")

                collected.append({
                    "category": category,
                    "title": clean_title,
                    "url": item['originallink'] or item['link'],
                    "published_date": pub_date_fmt,
                    "content": clean_desc
                })
            
            print(f"   👉 {len(collected)}건 확보 완료")
        else:
            print(f"❌ 네이버 API 에러: {res.status_code}")
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        
    return collected

# ==========================================
# 3. AI 필터링 (배치 처리)
# ==========================================
def call_gemini_batch(batch_items):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    오늘: {TODAY_STR} / 어제: {YESTERDAY}
    
    [입력 데이터]
    {json.dumps(batch_items)}

    [지시사항]
    1. 각 기사의 날짜와 내용을 보고 **최근 24시간({YESTERDAY} ~ {TODAY_STR})** 기사인지 재확인해라.
    2. [해외] 기사는 제목을 **자연스러운 한국어**로 번역해라.
    3. 중복된 내용이 있다면 하나만 남겨라.
    
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
    print("\n🤖 [2단계] AI 정밀 검수 중...")
    
    final_results = []
    BATCH_SIZE = 5 
    
    for i in range(0, len(news_list), BATCH_SIZE):
        batch = news_list[i : i + BATCH_SIZE]
        results = call_gemini_batch(batch)
        if results:
            for item in results:
                print(f"      ✅ 확보: {item.get('detected_date')} | {item['title'][:15]}...")
                final_results.extend(results)
        time.sleep(1)

    unique_results = {v['url']: v for v in final_results}.values()
    sorted_results = sorted(unique_results, key=lambda x: x.get('detected_date', ''), reverse=True)
    
    # 국내 7개, 해외 3개 선정
    kr_list = [x for x in sorted_results if "[국내]" in x['category']][:7]
    en_list = [x for x in sorted_results if "[해외]" in x['category']][:3]
    
    return kr_list + en_list

# ==========================================
# 4. 카카오톡 전송
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
        print("⚠️ 전송할 기사가 없습니다.")
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
# 5. 메인 실행
# ==========================================
if __name__ == "__main__":
    # 국내 뉴스 검색
    kr_news = search_naver_news("정보보호 해킹 개인정보유출 보안 침해사고", "[국내]")
    
    # 해외 뉴스 검색 (영어로 검색해서 네이버가 찾은 해외 관련 기사 수집)
    en_news = search_naver_news("Cyber Security Data Breach", "[해외]")
    
    all_news = kr_news + en_news
    
    if all_news:
        final_list = ai_filter_and_format(all_news)
        if final_list:
            send_kakaotalk(final_list)
        else:
            print("⚠️ AI 필터링 결과 없음")
    else:
        print("⚠️ 검색 결과 없음")
