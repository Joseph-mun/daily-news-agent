import os
import json
from tavily import TavilyClient

# 1. 환경변수 확인
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")

# [핵심 수정] 영문판 이슈가 있는 종합 일간지를 제거하고, 
# 'IT/보안 전문지' 위주로 리스트를 압축했습니다.
TARGET_DOMAINS = [
    "news.naver.com",      # 네이버 뉴스 (가장 강력)
    "boannews.com",        # 보안뉴스 (영문판 없음/적음)
    "dailysecu.com",       # 데일리시큐
    "etnews.com",          # 전자신문
    "zdnet.co.kr",         # 지디넷코리아
    "datanet.co.kr",       # 데이터넷
    "ddaily.co.kr",        # 디지털데일리
    "digitaltoday.co.kr",  # 디지털투데이
    "bloter.net",          # 블로터
    "itworld.co.kr",       # ITWorld
    "byline.network",      # 바이라인네트워크
    "ciokorea.com"         # CIO Korea
]

def test_search():
    print("="*60)
    print("🚀 [TEST] Tavily 검색 테스트 (도메인 최적화 버전)")
    
    if not TAVILY_KEY:
        print("❌ 오류: TAVILY_API_KEY 환경변수가 설정되지 않았습니다.")
        return

    # 검색어는 심플하게 되돌립니다. 도메인이 확실하면 영어 배제 키워드는 굳이 필요 없습니다.
    query = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어"
    
    print(f"🔎 검색어: {query}")
    print(f"🎯 대상 도메인: {len(TARGET_DOMAINS)}개 (IT/보안 전문지 중심)")
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
