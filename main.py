import os
import json
import requests
import re
import time
from datetime import datetime, timedelta

# ==========================================
# 1. 환경변수 설정
# ==========================================
NAVER_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

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
    
    # 검색량을 넉넉하게 50개 잡음
    display_count = 50
    
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
                # 1. 날짜 필터링 (파이썬이 1차로 확실히 거름)
                try:
                    pub_date_str = item['pubDate']
                    pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S +0900")
                    pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                    
                    # 어제보다 오래된 기사는 여기서 바로 탈락
                    if pub_date_fmt < YESTERDAY:
                        continue
                except:
                    # 날짜 파싱 실패하면 안전하게 오늘 날짜로 퉁침
                    pub_date_fmt = TODAY_STR

                # 2. 텍스트 정제
                clean_title = re.sub('<.+?>', '', item['title']).replace("&quot;", "'").replace("&amp;", "&")
                clean_desc = re.sub('<.+?>', '', item['description']).replace("&quot;", "'").replace("&amp;", "&")

                collected.append({
                    "category": category,
                    "title": clean_title,
                    "url": item['originallink'] or item['link'],
                    "published_date": pub_date_fmt,
                    "content": clean_desc
                })
            
            print(f"   👉 {len(collected)}건 확보 (파이썬 날짜 필터 통과)")
        else:
            print(f"❌ 네이버 API 에러: {res.status_code}")
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        
    return collected

# ==========================================
# 3. AI 필터링 (관대해진 버전)
# ==========================================
def call_gemini_batch(batch_items):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [핵심 수정] AI에게 "날짜 검증 하지마"라고 지시
    prompt = f"""
    오늘 날짜: {TODAY_STR}
    
    [입력 데이터]
    {json.dumps(batch_items)}

    [지시사항]
    1. 너는 '보안 뉴스 큐레이터'다.
    2. 입력된 기사들은 이미 날짜 검증이 끝난 것들이다. **날짜가 맞는지 의심하지 말고 무조건 최신 기사로 간주해라.**
    3. 기사의 주제가 **'보안, 해킹, IT 신기술, 개인정보'**와 관련 있다면 **절대 버리지 말고 포함시켜라.**
    4. [해외] 기사는 제목을 한국어로 자연스럽게 번역해라.
    5. 중복된 기사만 제거해라.
    
    [출력 포맷]
    JSON 리스트:
    [
      {{ "category": "[국내]or[해외]", "title": "제목", "url": "링크", "detected_date": "{TODAY_STR}" }}
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
    print("\n🤖 [2단계] AI 정밀 검수 중 (날짜 검증 면제)...")
    
    final_results = []
    BATCH_SIZE = 5 
    
    for i in range(0, len(news_list), BATCH_SIZE):
        batch = news_list[i : i + BATCH_SIZE]
        results = call_gemini_batch(batch)
        if results:
            for item in results:
                print(f"      ✅ 확보: {item['title'][:15]}...")
                final_results.extend(results)
        time.sleep(1)

    unique_results = {v['url']: v for v in final_results}.values()
    # 순서는 섞여도 상관없지만 일단 국내 우선
    sorted_results = list(unique_results)
    
    # 국내 7개, 해외 5개 (수집된 게 적으면 있는 만큼만)
    kr_list = [x for x in sorted_results if "[국내]" in x['category']][:7]
    en_list = [x for x in sorted_results if "[해외]" in x['category']][:5]
    
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
                # [버튼] 구글 뉴스 검색 링크 (보안 동향)
                "web_url": "https://www.google.com/search?q=보안+동향+뉴스&tbm=nws",
                "mobile_web_url": "https://www.google.com/search?q=보안+동향+뉴스&tbm=nws"
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
    # [국내 검색어] OR 연산자(|) 사용 안함 (네이버 기본 정확도 활용)
    kr_query = "해킹|보안관제|개인정보유출|악성코드|제로데이" 
    # -> 네이버 API는 띄어쓰기가 AND일 수 있어서, 파이프(|)를 쓰는게 OR 검색에 유리할 수 있지만,
    #    일단 기본적인 키워드로 진행하되, 검색 범위를 넓힘.
    kr_news = search_naver_news("정보보호 해킹 개인정보유출", "[국내]")
    
    # [해외 검색어 - 필살기]
    # 파이프(|)를 써서 '이것 OR 저것' 방식으로 검색하게 만듦
    # "해외 해킹" OR "글로벌 보안" OR "사이버 트렌드" ...
    en_query = "해외 해킹|글로벌 보안|미국 사이버 공격|보안 동향|최신 보안 기술|제로트러스트|AI 보안"
    en_news = search_naver_news(en_query, "[해외]")
    
    all_news = kr_news + en_news
    
    if all_news:
        final_list = ai_filter_and_format(all_news)
        if final_list:
            send_kakaotalk(final_list)
        else:
            print("⚠️ AI 필터링 결과 없음: AI가 너무 많이 걸러냈습니다.")
    else:
        print("⚠️ 검색 결과 없음: 키워드를 변경해보세요.")
