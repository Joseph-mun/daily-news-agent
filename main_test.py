import os
import json
from tavily import TavilyClient

# 1. 환경변수 확인
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")

# 2. 검색 대상 도메인 (main.py와 동일)
TARGET_DOMAINS = [
    "news.naver.com", "boannews.com", "dailysecu.com", "etnews.com", "zdnet.co.kr", 
    "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", "bloter.net", 
    "itworld.co.kr", "ciokorea.com", "byline.network",
    "yna.co.kr", "news1.kr", "newsis.com",
    "mk.co.kr", "hankyung.com", "mt.co.kr", "fnnews.com", "sedaily.com",
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "khan.co.kr"
]

def test_search():
    print("="*60)
    print("🚀 [TEST] Tavily 검색 테스트 시작")
    
    if not TAVILY_KEY:
        print("❌ 오류: TAVILY_API_KEY 환경변수가 설정되지 않았습니다.")
        return

    # 검색어 (한글 위주)
    query = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어 (뉴스 OR 보도)"
    
    print(f"🔎 검색어: {query}")
    print(f"🎯 대상 도메인: {len(TARGET_DOMAINS)}개 언론사")
    print("="*60)

    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        
        # Tavily API 호출
        response = tavily.search(
            query=query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS, # 도메인 필터링 적용
            max_results=20, # 테스트용으로 20개만
            days=3 
        )
        
        results = response.get('results', [])
        
        print(f"\n✅ 검색 결과: 총 {len(results)}건 발견\n")
        
        if len(results) == 0:
            print("⚠️ 결과가 0건입니다. 도메인 리스트나 검색어를 점검해야 합니다.")
        
        # 결과 상세 출력
        for i, item in enumerate(results, 1):
            title = item.get('title', '제목없음')
            url = item.get('url', 'URL없음')
            
            print(f"{i}. {title}")
            print(f"   🔗 URL: {url}")
            
            # 영문 기사인지 체크 (디버깅용)
            if "/en/" in url or "/english/" in url:
                print("   ⚠️ [주의] 영문판(English) URL 패턴 감지됨")
                
            print("-" * 50)

    except Exception as e:
        print(f"\n❌ 검색 중 치명적 오류 발생: {e}")

if __name__ == "__main__":
    test_search()