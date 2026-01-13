import os
import json
import requests
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
    """지정된 도메인인지 확인"""
    if not url: return False
    for domain in TARGET_DOMAINS:
        if domain in url.lower():
            return True
    return False

def call_ai_summarize(news_list):
    """Gemini에게 뉴스 선별 및 요약 요청"""
    print("\n" + "="*60)
    print(f"🤖 [TEST] AI(Gemini 2.5)에게 {len(news_list)}건 분석 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [사용자 요청 프롬프트 반영]
    prompt = f"""
    너는 깐깐한 '보안 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    [작업 지시]
    1. 다음 뉴스 목록에서 '정보보호, 해킹, 보안, 개인정보'와 관련성이 높은 기사를 선정해라.
    2. 해당 기사 텍스트나 메타데이터의 날짜를 확인하여, 오늘({TODAY_STR}) 기준으로 '2일 이내'의 기사인 경우에만 남겨라. (오래된 기사 삭제)
    3. 남은 기사는 한국어로 3줄 요약해라.
    
    [출력 포맷]
    반드시 아래와 같은 JSON 리스트 형식으로만 출력해라 (코드블록 없이):
    [ {{ "title": "제목", "source": "언론사", "summary": "요약내용", "date": "발행일", "url": "링크" }} ]

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
            if 'candidates' not in res_json:
                print("❌ AI 응답에 내용이 없습니다.")
                print(response.text)
                return []
            
            # AI 응답 텍스트 추출
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # JSON 파싱을 위해 마크다운 제거
            clean_text = text.replace("```json", "").replace("```", "").strip()
            
            try:
                # JSON 변환 시도
                result = json.loads(clean_text)
                return result
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 원본 텍스트 출력 (디버깅용)
                print("⚠️ JSON 파싱 실패. AI 원본 응답을 출력합니다:")
                print(clean_text)
                return []
        else:
            print(f"❌ API 호출 오류: {response.status_code}")
            print(response.text)
            return []
            
    except Exception as e:
        print(f"❌ AI 연결 중 오류: {e}")
        return []

# ==========================================
# 3. 메인 테스트 로직
# ==========================================
def test_full_process():
    print("="*60)
    print(f"🚀 [TEST] 뉴스 검색 -> 필터링 -> AI 요약 전체 테스트")
    print(f"📅 기준 날짜: {TODAY_STR}")
    
    if not TAVILY_KEY or not GEMINI_KEY:
        print("❌ 오류: API KEY가 환경변수에 설정되지 않았습니다.")
        return

    # 1. Tavily 검색
    query = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어"
    print(f"\n🔍 [1단계] 검색어: {query}")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        response = tavily.search(
            query=query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS,
            max_results=30 
        )
        raw_results = response.get('results', [])
        print(f"   👉 Tavily 수집 개수: {len(raw_results)}개")

        # 2. 도메인 1차 필터링 (파이썬)
        filtered_results = []
        for item in raw_results:
            if is_valid_domain(item.get('url')):
                filtered_results.append(item)
        
        print(f"   👉 도메인 필터링 후: {len(filtered_results)}개 (AI에게 전달)")
        
        if not filtered_results:
            print("⚠️ 전달할 기사가 없어 테스트를 종료합니다.")
            return

        # 3. AI 요약 요청
        final_articles = call_ai_summarize(filtered_results)
        
        # 4. 결과 출력
        print("\n" + "="*60)
        print(f"✅ [최종 결과] AI가 선정한 기사: {len(final_articles)}개")
        print("="*60)
        
        for i, article in enumerate(final_articles, 1):
            print(f"{i}. {article.get('title')}")
            print(f"   📰 출처: {article.get('source', 'Unknown')}")
            print(f"   📅 날짜: {article.get('date', 'Unknown')}")
            print(f"   📝 요약: {article.get('summary')}")
            print(f"   🔗 링크: {article.get('url')}")
            print("-" * 50)

    except Exception as e:
        print(f"\n❌ 테스트 중 치명적 오류: {e}")

if __name__ == "__main__":
    test_full_process()
