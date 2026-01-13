import json
import os
import requests
from datetime import datetime
from openai import OpenAI  # pip install openai

# ==========================================
# 1. 설정값 (API 키 및 파일 경로)
# ==========================================
OPENAI_API_KEY = "sk-..."  # 여기에 OpenAI API 키 입력
HISTORY_FILE = "news_history.json"
SEARCH_QUERY = '정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안 -야구 -축구 -스포츠 -연예 -포토'

# AI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================================
# 2. 히스토리(중복 방지) 관리 함수
# ==========================================
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return []

def save_history(new_links, existing_history):
    # 기존 히스토리에 새 링크 추가 (최신 1000개만 유지 등 관리 가능)
    updated_history = list(set(existing_history + new_links))
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(updated_history, f, ensure_ascii=False, indent=4)

# ==========================================
# 3. 검색 API (기존 코드 이식 필요)
# ==========================================
def fetch_search_results(query):
    print(f"[{query}] 검색 시작...")
    
    # ---------------------------------------------------------
    # [중요] 기존에 사용하시던 네이버/구글 검색 API 코드를 여기에 넣으세요.
    # 아래는 테스트를 위한 가짜 데이터(Dummy Data) 예시입니다.
    # 실제로는 api_response를 받아 리스트 형태로 반환해야 합니다.
    # ---------------------------------------------------------
    
    # 예시 데이터 구조
    results = [
        {"title": "OOO 해킹 사고 발생, 개인정보 유출 우려", "link": "https://news.com/1", "desc": "보안 업체 분석 결과..."},
        {"title": "프로야구 개막, 보안 요원 배치", "link": "https://sports.com/2", "desc": "야구장 안전을 위해..."}, # AI가 걸러내야 함
        {"title": "연예인 A씨 사생활 유출 논란", "link": "https://enter.com/3", "desc": "사진 유출로 곤욕..."}, # 애매하지만 보안 뉴스 아님
        {"title": "정부, 사이버 보안 강화 대책 발표", "link": "https://gov.com/4", "desc": "제로트러스트 도입..."},
    ]
    # 실제 코드에서는: return api_result_list
    return results

# ==========================================
# 4. AI에게 판단 및 요약 요청 (핵심 로직)
# ==========================================
def ai_judge_and_summarize(articles):
    print("AI에게 기사 선별 및 요약 요청 중...")

    # AI에게 보낼 프롬프트 구성
    # JSON 형식으로 강제하여 파이썬이 다시 읽을 수 있게 함
    prompt = f"""
    너는 베테랑 '정보보호 전문 기자'이자 '편집장'이다.
    아래 제공된 뉴스 기사 리스트(JSON)를 보고 다음 작업을 수행해라.

    [작업 지시]
    1. **필터링(Filtering):** '정보보호, 해킹, 보안, 개인정보'와 직접 관련이 없는 기사는 과감히 삭제해라.
       - 제외 대상: 스포츠(야구, 축구 등), 단순 연예 가십, 포토 뉴스, 광고성 보도자료, 주식 단순 시황.
       - 야구장에서의 '보안(Security)'요원 배치 같은 동음이의어도 문맥을 보고 제외해라.
    2. **요약(Summarizing):** 살아남은 보안 관련 기사는 내용을 3줄 이내로 핵심만 요약해라.
    3. **출력(Output):** 결과는 반드시 오직 **JSON 포맷의 리스트**로만 출력해라. 다른 말은 하지 마라.

    [입력 데이터]
    {json.dumps(articles, ensure_ascii=False)}

    [출력 예시 포맷]
    [
        {{"title": "기사제목", "link": "기사링크", "summary": "AI가 요약한 내용", "reason": "선정 이유(간략히)"}}
    ]
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # 가성비 좋은 모델 추천 (또는 gpt-4o)
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs strictly in JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"} # JSON 모드 활성화
        )
        
        content = response.choices[0].message.content
        # 가끔 JSON 리스트가 key 밑에 들어가는 경우가 있어 파싱 처리
        parsed_data = json.loads(content)
        
        # GPT가 {"articles": [...]} 형태로 줄 수도 있고 그냥 [...]로 줄 수도 있음 대응
        if isinstance(parsed_data, dict):
            return list(parsed_data.values())[0]
        return parsed_data

    except Exception as e:
        print(f"AI 처리 중 오류 발생: {e}")
        return []

# ==========================================
# 5. 메인 실행부
# ==========================================
def main():
    # 1. 히스토리 로드
    history_links = load_history()
    print(f"기존 히스토리: {len(history_links)}개 기사 저장됨.")

    # 2. 기사 수집 (Python)
    raw_articles = fetch_search_results(SEARCH_QUERY)
    print(f"1차 수집된 기사: {len(raw_articles)}개")

    # 3. 중복 제거 (이미 처리한 링크는 AI에게 보내지 않음 -> 비용 절약)
    new_articles = [art for art in raw_articles if art['link'] not in history_links]
    print(f"중복 제외 후 AI 검수 대상: {len(new_articles)}개")

    if not new_articles:
        print("새로운 기사가 없습니다. 종료합니다.")
        return

    # 4. AI에게 판단 맡기기 (Python은 배달만 함)
    # 한 번에 너무 많이 보내면 토큰 제한 걸릴 수 있으니 20~30개씩 끊어 보내는 로직 추가 가능
    # 여기서는 예시로 통째로 보냄
    final_news = ai_judge_and_summarize(new_articles)

    # 5. 결과 출력 및 히스토리 업데이트
    print(f"\n=== AI 최종 선정 뉴스 ({len(final_news)}개) ===")
    processed_links = []
    
    for news in final_news:
        print(f"[{news.get('title')}]")
        print(f" - 요약: {news.get('summary')}")
        print(f" - 링크: {news.get('link')}")
        print("-" * 30)
        
        # 결과에 포함된 링크 수집 (유효한 기사)
        processed_links.append(news.get('link'))
    
    # AI가 '버린' 기사들도 다시 검토하지 않도록 히스토리에 넣을지 결정해야 함.
    # 보통은 '검토했던 모든 링크'를 히스토리에 넣습니다. (다시 봐도 쓰레기일 확률이 높으므로)
    all_checked_links = [art['link'] for art in new_articles]
    save_history(all_checked_links, history_links)
    print("히스토리 업데이트 완료.")

if __name__ == "__main__":
    main()
