# 5. AI 상세 요약 (디버깅 로그 추가)
def summarize_news(news_list):
    if not news_list:
        return []

    print(f"Gemini에게 {len(news_list)}건 요약 요청...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 보안 뉴스 전문 편집장이야. 아래 뉴스 데이터를 분석해 JSON 리스트로 반환해.
    
    [규칙]
    1. 주제 필터링: '정보보호', '해킹', '보안', '개인정보', 'IT정책' 관련 기사만 남겨.
    2. 언어: 내용은 반드시 '한국어'로 작성해.
    3. 형식: 오직 JSON 리스트만 출력해. (마크다운 코드블럭 ```json 없이 순수 텍스트로만)
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "기사 제목", "summary": "핵심 내용 3줄 요약", "url": "http://..."}},
        ...
    ]
    """
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": safety_settings
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            res_json = response.json()
            
            # 1. 답변 자체가 비어있는 경우 (안전 필터 등에 걸림)
            if 'candidates' not in res_json or not res_json['candidates']:
                print("🚨 오류: AI가 답변을 생성하지 않았습니다. (Finish Reason 확인 필요)")
                print(f"응답 원본: {res_json}")
                return []
                
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # 2. JSON 파싱 시도
            start_index = text.find('[')
            end_index = text.rfind(']') + 1
            
            if start_index == -1:
                print("🚨 오류: AI 답변에서 JSON 리스트([])를 찾을 수 없습니다.")
                print(f"🤖 AI가 한 말: {text}") # AI의 변명을 들어봅시다
                return []
                
            clean_json = text[start_index:end_index]
            result = json.loads(clean_json)
            print(f"✅ AI 요약 성공: {len(result)}건")
            return result
            
        else:
            print(f"🚨 API 호출 에러: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"🚨 시스템 예외 발생: {e}")
        return []
