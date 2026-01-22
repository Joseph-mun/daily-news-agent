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
# 2. 국내 뉴스 검색 (네이버 API)
# ==========================================
def search_naver_news():
    # [키워드 전략] 신한 관련 키워드를 포함하여 검색풀에 무조건 걸리게 함
    query = "정보보호 해킹 개인정보유출 금융보안 IT보안 보안기술동향"
    print(f"\n🇰🇷 [국내] 네이버 검색 시작: {query}")
    
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 네이버 API 키가 없습니다.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    
    # AI에게 보낼 후보군 30~40개 확보 (이 중에서 7개를 뽑음)
    params = {"query": query, "display": 40, "sort": "date"}
    
    collected = []
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                # 파이썬 1차 날짜 필터 (AI 토큰 절약)
                try:
                    pub_date_str = item['pubDate']
                    pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S +0900")
                    pub_date_fmt = pub_dt.strftime("%Y-%m-%d")
                    if pub_date_fmt < YESTERDAY: continue
                except:
                    pub_date_fmt = TODAY_STR

                clean_title = re.sub('<.+?>', '', item['title']).replace("&quot;", "'").replace("&amp;", "&")
                clean_desc = re.sub('<.+?>', '', item['description']).replace("&quot;", "'").replace("&amp;", "&")

                collected.append({
                    "category": "[국내]",
                    "title": clean_title,
                    "url": item['originallink'] or item['link'],
                    "published_date": pub_date_fmt,
                    "description": clean_desc
                })
            print(f"   👉 국내 후보 {len(collected)}개 확보")
        else:
            print(f"❌ 네이버 API 에러: {res.status_code}")
    except Exception as e:
        print(f"❌ 네이버 요청 실패: {e}")
        
    return collected

# ==========================================
# 3. 해외 뉴스 검색 (Tavily API)
# ==========================================
def search_tavily_news():
    print(f"\n🇺🇸 [해외] Tavily 검색 시작...")
    if not TAVILY_KEY:
        print("❌ Tavily API 키가 없습니다.")
        return []
        
    tavily = TavilyClient(api_key=TAVILY_KEY)
    collected = []
    
    # 신뢰도 높은 보안 전문 매체 위주
    domains = [
        "thehackernews.com", "bleepingcomputer.com", "darkreading.com", 
        "infosecurity-magazine.com", "securityweek.com"
    ]
    
    try:
        # AI에게 보낼 후보군 20개 확보
        res = tavily.search(
            query="Cyber Security Breach Hacking News", 
            topic="news", 
            days=2, 
            search_depth="advanced",
            include_domains=domains, 
            max_results=20
        )
        
        for item in res.get('results', []):
            collected.append({
                "category": "[해외]",
                "title": item['title'],
                "url": item['url'],
                "published_date": item.get('published_date', TODAY_STR),
                "description": item.get('content', '')[:200]
            })
            
        print(f"   👉 해외 후보 {len(collected)}개 확보")
        
    except Exception as e:
        print(f"❌ Tavily 검색 오류: {e}")

    return collected

# ==========================================
# 4. AI 선별 (우선순위 로직 적용)
# ==========================================
def call_gemini_priority_selection(items, mode):
    if not items: return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [핵심] 프롬프트 분기 처리
    if mode == 'KR':
        target_count = 7
        # 국내 뉴스 우선순위 가이드라인
        system_instruction = """
        너는 '신한금융그룹 보안 뉴스 편집장'이다. 
        입력된 뉴스 목록 중에서 다음 **우선순위(Priority)**에 따라 **상위 7개** 기사를 엄선해라.
        **최우선이라고 하더라도 뉴스 기사 내용에 없으면 넘어가고, 반드시 포함해야하는건 아니다**

        [우선순위 채점 기준]
        1. **1순위 (최우선):** '신한금융', '신한은행', '신한라이프', '신한카드', '신한투자증권' 등 **신한** 관련 키워드가 포함된 기사.
        2. **2순위 (중요):** 해킹 사고, 개인정보 유출, 침해 사고, 랜섬웨어 등 실제 발생한 **보안 사건/사고**.
        3. **3순위 (참고):** 금융보안원 발표, 금감원 규제, 보안 기술 트렌드(AI 보안, 망분리 등).
        4. **제외 대상:** 단순 행사 홍보, 인사 발령, 중복된 내용.
        """
    else:
        target_count = 3
        # 해외 뉴스 우선순위 가이드라인
        system_instruction = """
        너는 '글로벌 보안 트렌드 분석가'이다.
        입력된 뉴스 목록 중에서 **가장 파급력이 큰 3개** 기사를 선정해라.
        
        [지시사항]
        1. 제목을 반드시 **자연스러운 한국어**로 번역해라.
        2. 우선순위: 대규모 데이터 유출 > 제로데이 취약점 > 글로벌 보안 정책.
        """

    prompt = f"""
    [입력 데이터]
    {json.dumps(items)}

    [지시사항]
    {system_instruction}
    
    [출력 포맷]
    선정된 {target_count}개의 기사를 아래 JSON 리스트 포맷으로 출력해라:
    [
      {{ "category": "[{ '국내' if mode == 'KR' else '해외' }]", "title": "제목", "url": "링크" }}
    ]
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    # 재시도 로직 (429 에러 방지)
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
    
    # 2. 국내 선별 (한 번의 호출로 7개 선별)
    if kr_candidates:
        print("\n🤖 [국내] AI 편집장이 우선순위에 따라 7개를 선별합니다...")
        kr_selected = call_gemini_priority_selection(kr_candidates, 'KR')
        final_list.extend(kr_selected)
        print(f"   ✅ 국내 {len(kr_selected)}개 선별 완료")
    else:
        print("   ⚠️ 국내 후보 기사가 없습니다.")
        
    # API 휴식
    time.sleep(2)
    
    # 3. 해외 선별 (한 번의 호출로 3개 선별)
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

    print("\n🚀 [4단계] 카카오톡 전송 중...")
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
        print("✅ 카카오톡 전송 완료!")
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
