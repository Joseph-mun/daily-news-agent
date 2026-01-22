import os
import json
import requests
import re
import time
from datetime import datetime, timedelta
from tavily import TavilyClient

# ==========================================
# 1. 환경변수 설정
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
# 2. 국내 뉴스 검색 (네이버 API - 루프 검색 방식)
# ==========================================
def search_naver_news():
    # [수정] 단일 쿼리 대신 리스트로 분리하여 각각 검색 후 병합
    keywords = ["정보보호", "해킹", "개인정보유출", "금융보안", "랜섬웨어"]
    print(f"\n🇰🇷 [국내] 네이버 분할 검색 시작: {keywords}")
    
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 네이버 API 키가 없습니다.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    
    all_collected = {} # URL을 키로 사용하여 중복 제거

    for keyword in keywords:
        try:
            # 키워드당 15개씩만 가져와서 합침
            params = {"query": keyword, "display": 15, "sort": "date"}
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                items = res.json().get('items', [])
                count = 0
                for item in items:
                    # 파이썬 날짜 필터
                    try:
                        pub_date_str = item['pubDate']
                        pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S +0900")
                        pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                        if pub_date_fmt < YESTERDAY: continue
                    except:
                        pub_date_fmt = TODAY_STR

                    link = item['originallink'] or item['link']
                    
                    # 이미 수집된 기사면 패스 (중복 제거)
                    if link in all_collected:
                        continue

                    clean_title = re.sub('<.+?>', '', item['title']).replace("&quot;", "'").replace("&amp;", "&")
                    clean_desc = re.sub('<.+?>', '', item['description']).replace("&quot;", "'").replace("&amp;", "&")

                    all_collected[link] = {
                        "category": "[국내]",
                        "title": clean_title,
                        "url": link,
                        "published_date": pub_date_fmt,
                        "description": clean_desc
                    }
                    count += 1
                # print(f"   - '{keyword}': {count}건 추가")
            else:
                print(f"   ❌ '{keyword}' 검색 실패: {res.status_code}")
                
        except Exception as e:
            print(f"   ❌ 요청 오류: {e}")
            
    final_list = list(all_collected.values())
    print(f"   👉 국내 후보 총 {len(final_list)}건 확보 (중복 제거 완료)")
    return final_list

# ==========================================
# 3. 해외 뉴스 검색 (Tavily + 강력 날짜 필터)
# ==========================================
def search_tavily_news():
    print(f"\n🇺🇸 [해외] Tavily 검색 시작...")
    if not TAVILY_KEY:
        print("❌ Tavily API 키가 없습니다.")
        return []
        
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    domains = [
        "thehackernews.com", "bleepingcomputer.com", "darkreading.com", 
        "securityweek.com", "wired.com", "techcrunch.com"
    ]
    
    try:
        # 1. 넉넉하게 40개 요청
        res = tavily.search(
            query="Cyber Security Breach Hacking News", 
            topic="news", 
            days=2, 
            include_domains=domains, 
            max_results=40
        )
        
        # 2. 파이썬 강력 필터
        collected = []
        for item in res.get('results', []):
            pub_date = item.get('published_date', '')
            if pub_date is None: pub_date = ""
            
            # 2026년 또는 ago가 없으면 AI에게 보내지도 않음
            if pub_date and ('2026' not in pub_date and 'ago' not in pub_date):
                 continue

            collected.append({
                "category": "[해외]",
                "title": item['title'],
                "url": item['url'],
                "published_date": pub_date,
                "description": item.get('content', '')[:200]
            })
        
        # 3. 상위 20개만 AI 후보군으로 선정
        collected = collected[:20]
        print(f"   👉 해외 후보 {len(collected)}개 확보 (필터링 완료)")
        return collected
        
    except Exception as e:
        print(f"❌ Tavily 오류: {e}")
        return []

# ==========================================
# 4. AI 선별 (우선순위 로직)
# ==========================================
def call_gemini_priority_selection(items, mode):
    if not items: return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    if mode == 'KR':
        target_count = 7
        # 국내 뉴스 우선순위 가이드라인
        system_instruction = """
        너는 '금융권 보안 뉴스 큐레이터'다. 
        입력된 뉴스 목록 중에서 다음 **우선순위(Priority)**에 따라 **상위 7개** 기사를 엄선해라.

        [우선순위 채점 기준]
        1. **1순위 (최우선):** 해킹 사고, 개인정보 유출, 랜섬웨어 등 실제 발생한 **침해 사고**.
        2. **2순위 (중요):** 금융보안원 발표, 금감원 규제, 최신 보안 기술 동향(AI, 망분리 등).
        3. **3순위 (참고):** '신한금융', '신한은행' 등 신한 계열사의 보안/디지털 관련 소식.
        
        [주의사항]
        - **3순위(신한) 기사가 없으면 억지로 넣지 마라.** 1, 2순위 기사로 채워라.
        - 단순 행사 홍보, 인사 발령, 중복된 내용은 제외해라.
        """
    else:
        target_count = 3
        # 해외 뉴스 가이드라인
        system_instruction = """
        너는 '글로벌 보안 트렌드 분석가'이다.
        입력된 뉴스 목록 중에서 **가장 파급력이 큰 3개** 기사를 선정해라.
        
        [지시사항]
        1. 기사 제목을 반드시 **자연스러운 한국어**로 번역해라.
        2. 우선순위: 대규모 데이터 유출 > 제로데이 취약점 > 글로벌 보안 정책.
        3. 'detected_date' 필드에는 입력된 날짜를 그대로 유지해라.
        """

    prompt = f"""
    [입력 데이터]
    {json.dumps(items)}

    [지시사항]
    {system_instruction}
    
    [출력 포맷]
    선정된 {target_count}개의 기사를 아래 JSON 리스트 포맷으로 출력해라:
    [
      {{ "category": "[{ '국내' if mode == 'KR' else '해외' }]", "title": "제목", "url": "링크", "detected_date": "YYYY-MM-DD" }}
    ]
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    # 429 에러 방지용 재시도 로직
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=data)
            if res.status_code == 200:
                text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean_text = text.replace("```json", "").replace("```", "").strip()
                try:
                    start = clean_text.find('[')
                    end = clean_text.rfind(']') + 1
                    return json.loads(clean_text[start:end])
                except:
                    print(f"    ⚠️ JSON 파싱 실패 ({mode})")
                    return []
            elif res.status_code == 429:
                wait_time = (attempt + 1) * 10
                print(f"    ⏳ [AI 과부하] {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                print(f"    ❌ API 오류: {res.status_code}")
                return []
                
        except Exception as e:
            print(f"    ❌ 연결 오류: {e}")
            return []
            
    return []

def process_news():
    # 1. 수집
    kr_candidates = search_naver_news()
    en_candidates = search_tavily_news()
    
    final_list = []
    
    # 2. 국내 선별 (7개)
    if kr_candidates:
        print("\n🤖 [국내] AI가 우선순위에 따라 7개를 선별합니다...")
        kr_selected = call_gemini_priority_selection(kr_candidates, 'KR')
        final_list.extend(kr_selected)
        print(f"   ✅ 국내 {len(kr_selected)}개 선별 완료")
    else:
        print("   ⚠️ 국내 후보 기사가 없습니다.")
        
    # API 휴식
    time.sleep(2)
    
    # 3. 해외 선별 (3개)
    if en_candidates:
        print("\n🤖 [해외] AI가 중요 기사 3개를 선별하고 번역합니다...")
        en_selected = call_gemini_priority_selection(en_candidates, 'GLOBAL')
        final_list.extend(en_selected)
        print(f"   ✅ 해외 {len(en_selected)}개 선별 완료")
    else:
        print("   ⚠️ 해외 후보 기사가 없습니다.")
        
    return final_list

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
        print("⚠️ 전송할 기사가 없습니다.")
        return

    print("\n🚀 카카오톡 전송 중...")
    access_token = get_kakao_access_token()
    if not access_token: return

    message_text = f"🛡️ {TODAY_STR} 보안 브리핑\n\n"
    
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
        print("✅ 전송 완료")
    else:
        print(f"❌ 전송 실패: {res.text}")

# ==========================================
# 6. 메인 실행
# ==========================================
if __name__ == "__main__":
    final_news = process_news()
    
    if final_news:
        send_kakaotalk(final_news)
    else:
        print("⚠️ 최종 선별된 뉴스가 없습니다.")
