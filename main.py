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
    print(f"\n🔎 [{category}] 네이버 검색: {query}")
    
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 네이버 API 키가 없습니다.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET
    }
    
    params = {
        "query": query,
        "display": 40, 
        "sort": "date" 
    }
    
    collected = []
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                clean_title = re.sub('<.+?>', '', item['title']).replace("&quot;", "'").replace("&amp;", "&")
                
                # 1. 날짜 필터링 (로그 추가)
                try:
                    pub_date_str = item['pubDate']
                    pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S +0900")
                    pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                    
                    if pub_date_fmt < YESTERDAY:
                        print(f"   🗑️ [날짜 미달] {pub_date_fmt} | {clean_title[:15]}...")
                        continue
                except:
                    pub_date_fmt = TODAY_STR

                clean_desc = re.sub('<.+?>', '', item['description']).replace("&quot;", "'").replace("&amp;", "&")

                collected.append({
                    "category": category,
                    "title": clean_title,
                    "url": item['originallink'] or item['link'],
                    "published_date": pub_date_fmt,
                    "content": clean_desc
                })
            
            print(f"   👉 {len(collected)}건 확보 (1차 필터 통과)")
        else:
            print(f"❌ 네이버 API 에러: {res.status_code}")
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        
    return collected

# ==========================================
# 3. AI 변환 (단순 포맷팅)
# ==========================================
def call_gemini_batch(batch_items):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    [입력 데이터]
    {json.dumps(batch_items)}

    [지시사항]
    1. 입력된 모든 기사를 **하나도 빠짐없이** JSON 리스트로 변환해라. (삭제 금지)
    2. [해외] 기사 제목은 **한국어로 번역**해라.
    3. 'detected_date' 필드에는 입력된 'published_date' 값을 그대로 넣어라.
    
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
            res_json = res.json()
            if 'candidates' in res_json:
                text = res_json['candidates'][0]['content']['parts'][0]['text']
                clean_text = text.replace("```json", "").replace("```", "").strip()
                
                try:
                    start = clean_text.find('[')
                    end = clean_text.rfind(']') + 1
                    if start != -1 and end != -1:
                        json_str = clean_text[start:end]
                        return json.loads(json_str)
                    else:
                        print(f"    ⚠️ [AI 에러] JSON 구조 못 찾음. 응답: {clean_text[:50]}...")
                except json.JSONDecodeError:
                    print(f"    ⚠️ [AI 에러] JSON 파싱 실패. 응답: {clean_text[:50]}...")
            else:
                print("    ⚠️ [AI 에러] 응답 내용 없음 (Blocked)")
        else:
            print(f"    ❌ [API 에러] 상태코드: {res.status_code}")
    except Exception as e:
        print(f"    ❌ [연결 에러] {e}")
        
    return []

def ai_filter_and_format(news_list):
    if not news_list: return []
    print("\n🤖 [2단계] AI 번역 및 포맷팅 (삭제 사유 추적)...")
    
    processed_results = []
    BATCH_SIZE = 5
    
    # 1. AI 처리 루프
    for i in range(0, len(news_list), BATCH_SIZE):
        batch = news_list[i : i + BATCH_SIZE]
        results = call_gemini_batch(batch)
        
        if results:
            # 요청 개수 vs 응답 개수 비교
            if len(results) < len(batch):
                print(f"   ⚠️ [AI 누락] 요청 {len(batch)}개 -> 응답 {len(results)}개 (AI가 일부를 임의 삭제함)")
            
            for item in results:
                processed_results.append(item)
        else:
            print(f"   🗑️ [배치 실패] {i}~{i+BATCH_SIZE}번 구간 AI 변환 실패로 전체 삭제됨")
            
        time.sleep(1)

    # 2. 중복 제거 및 최종 선별
    final_kr = []
    final_en = []
    seen_urls = set()
    
    print("\n📊 [3단계] 최종 선별 과정 로그:")
    
    # 날짜 최신순 정렬 (단순 문자열 비교)
    processed_results.sort(key=lambda x: x.get('detected_date', ''), reverse=True)

    for item in processed_results:
        # 중복 체크
        if item['url'] in seen_urls:
            print(f"   🗑️ [중복 제거] {item['title'][:15]}...")
            continue
        seen_urls.add(item['url'])
        
        # 카테고리별 분류 및 개수 제한 체크
        if "[국내]" in item['category']:
            if len(final_kr) < 5:
                final_kr.append(item)
                # print(f"   ✅ [국내 선정] {item['title'][:15]}...")
            else:
                print(f"   ✂️ [순위 밖] 국내 5개 초과로 제외: {item['title'][:15]}...")
                
        elif "[해외]" in item['category']:
            if len(final_en) < 3:
                final_en.append(item)
                # print(f"   ✅ [해외 선정] {item['title'][:15]}...")
            else:
                print(f"   ✂️ [순위 밖] 해외 3개 초과로 제외: {item['title'][:15]}...")

    print(f"\n✅ 최종 확정: 국내 {len(final_kr)}개 / 해외 {len(final_en)}개")
    return final_kr + final_en

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
                "web_url": "https://www.google.com/search?q=보안+뉴스&tbm=nws",
                "mobile_web_url": "https://www.google.com/search?q=보안+뉴스&tbm=nws"
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
    kr_news = search_naver_news("정보보호 해킹 개인정보유출", "[국내]")
    en_news_1 = search_naver_news("해외 해킹 사이버 공격", "[해외]")
    en_news_2 = search_naver_news("글로벌 보안 트렌드 AI 보안 기술", "[해외]")
    
    all_news = kr_news + en_news_1 + en_news_2
    
    if all_news:
        final_list = ai_filter_and_format(all_news)
        if final_list:
            send_kakaotalk(final_list)
        else:
            print("⚠️ 모든 기사가 탈락했습니다. (위 로그 확인)")
    else:
        print("⚠️ 검색된 기사가 하나도 없습니다.")
