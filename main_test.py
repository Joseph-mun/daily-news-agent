import os
import json
import requests
import re
from datetime import datetime
from tavily import TavilyClient

# ==========================================
# 1. 설정 및 환경변수
# ==========================================
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")

# [검색 대상 도메인]
TARGET_DOMAINS = [
    "news.naver.com", "boannews.com", "dailysecu.com", "etnews.com", 
    "zdnet.co.kr", "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", 
    "bloter.net", "itworld.co.kr", "byline.network", "ciokorea.com",
    "yna.co.kr", "news1.kr", "newsis.com"
]

# ==========================================
# 2. 유틸리티 함수
# ==========================================
def is_valid_domain(url):
    if not url: return False
    for domain in TARGET_DOMAINS:
        if domain in url.lower():
            return True
    return False

def call_ai_summarize(news_list):
    print("\n" + "="*60)
    print(f"🤖 [TEST] AI(Gemini 2.5)에게 {len(news_list)}건 분석 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 깐깐한 '보안 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    [작업 지시]
    1. 뉴스 목록에서 '정보보호, 해킹, 보안, 개인정보' 관련 핵심 기사를 선정해라.
    2. 오늘({TODAY_STR}) 기준으로 '2일 이내'의 기사만 남겨라.
    3. 남은 기사는 한국어로 3줄 요약해라.
    4. **중요:** 결과는 반드시 순수 JSON 리스트 포맷(`[...]`)으로만 출력해라.

    [입력 데이터]
    {json.dumps(news_list)}
    """
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: return []
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # 마크다운 제거
            clean_text = text.replace("```json", "").replace("```", "").strip()
            
            # JSON 파싱 (Regex 활용)
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return []
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []

# ==========================================
# 3. 메인 테스트 로직
# ==========================================
def test_full_process():
    print("="*60)
    print(f"🚀 [TEST] 검색어 롤백 (공백 구분)")
    print(f"📅 기준 날짜: {TODAY_STR}")
    
    if not TAVILY_KEY or not GEMINI_KEY:
        print("❌ 오류: API KEY가 없습니다.")
        return

    # [수정됨] OR 제거하고 공백으로 복귀 (관련성 중심 검색)
    query = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어"
    print(f"\n🔍 [1단계] 검색어: {query}")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        response = tavily.search(
            query=query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS,
            max_results=40 
        )
        raw_results = response.get('results', [])
        print(f"   👉 Tavily 수집 개수: {len(raw_results)}개")

        filtered_results = []
        for item in raw_results:
            if is_valid_domain(item.get('url')):
                filtered_results.append(item)
        
        print(f"   👉 도메인 필터링 후: {len(filtered_results)}개")

        if not filtered_results:
            print("⚠️ 기사가 없습니다.")
            return

        final_articles = call_ai_summarize(filtered_results)
        
        print("\n" + "="*60)
        print(f"✅ [최종 결과] AI 선정 기사: {len(final_articles)}개")
        print("="*60)
        
        for i, article in enumerate(final_articles, 1):
            print(f"{i}. {article.get('title')}")
            print(f"   📅 날짜: {article.get('date')}")
            print(f"   📝 요약: {article.get('summary')}")
            print("-" * 50)

    except Exception as e:
        print(f"\n❌ 테스트 중 오류: {e}")

if __name__ == "__main__":
    test_full_process()
