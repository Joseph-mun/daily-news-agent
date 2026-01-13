import os
import json
from tavily import TavilyClient

# 1. 환경변수 확인
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")

# 2. 검색 대상 도메인
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
    print("🚀 [TEST] Tavily 검색 테스트 (검색어 강화 버전)")
    
    if not TAVILY_KEY:
        print("❌ 오류: TAVILY_API_KEY 환경변수가 설정되지 않았습니다.")
        return

    # [수정된 부분] 검색어에 '한국어', 제외 키워드(-english) 등을 명시
    query = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어 관련 최신 한국어 뉴스 기사 -english -sports -baseball -soccer"
    
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
            include_domains=TARGET_DOMAINS,
            max_results=20, 
            days=3 
        )
        
        results = response.get('results', [])
        
        print(f"\n✅ 검색 결과: 총 {len(results)}건 발견\n")
        
        korean_count = 0
        
        for i, item in enumerate(results, 1):
            title = item.get('title', '제목없음')
            url = item.get('url', 'URL없음')
            
            # 영문 기사 패턴 체크
            is_english = "/en/" in url or "/english/" in url or "cnn.com" in url
            
            status = "✅ [한글]"
            if is_english:
                status = "⚠️ [영문]"
            else:
                korean_count += 1

            print(f"{i}. {status} {title}")
            print(f"   🔗 URL: {url}")
            print("-" * 50)
            
        print(f"\n📊 결산: 총 {len(results)}개 중 한글 기사 {korean_count}개")

    except Exception as e:
        print(f"\n❌ 검색 중 오류 발생: {e}")

if __name__ == "__main__":
    test_search()
