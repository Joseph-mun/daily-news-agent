import os
import smtplib
import requests
import json
import qrcode
from datetime import datetime, timedelta
from dateutil import parser
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.header import Header
from email import encoders
from fpdf import FPDF
from tavily import TavilyClient

# ==========================================
# 1. 환경변수 및 설정
# ==========================================
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
MAIN_RECIPIENT = os.environ.get("TO_EMAIL") or EMAIL_USER

# 수신자 리스트 구성
RECIPIENTS = []
if MAIN_RECIPIENT: 
    RECIPIENTS.append(MAIN_RECIPIENT)

ADDITIONAL_EMAIL = "joseph.moon@shinhan.com"
if ADDITIONAL_EMAIL not in RECIPIENTS: 
    RECIPIENTS.append(ADDITIONAL_EMAIL)

HISTORY_FILE = "history.json"

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
TODAY_COMPACT = NOW.strftime("%Y%m%d")
PDF_FILENAME = f"주요 뉴스 요약_{TODAY_COMPACT}.pdf"

# ==========================================
# 2. 유틸리티 함수 (중복 필터링)
# ==========================================
def filter_new_articles(results):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try: 
                history = json.load(f)
            except: 
                history = []
    else: 
        history = []

    new_results = []
    for item in results:
        # URL이 히스토리에 없으면 추가
        if item['url'] not in history: 
            new_results.append(item)
    return new_results, history

# ==========================================
# 3. 뉴스 검색 (Python 필터링 최소화)
# ==========================================
def search_news(query):
    # 검색어: 제외어 없이 광범위하게 검색
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안"
    
    print(f"'{optimized_query}' 광범위 검색 중...")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        response = tavily.search(
            query=optimized_query, 
            topic="news",
            search_depth="advanced", 
            max_results=50, # AI가 처리할 수 있을 만큼 넉넉히
            days=3 
        )
        
        raw_results = response.get('results', [])
        print(f"1차 API 검색결과: {len(raw_results)}개 확보.")
        
        # 중복(히스토리) 체크만 수행하고 나머지는 AI에게 넘김
        final_candidates, history = filter_new_articles(raw_results)
        
        print(f"중복 제거 후 AI 검수 요청 대상: {len(final_candidates)}개")

        # 히스토리 업데이트 (이번에 검색된 건은 일단 다 본 것으로 처리)
        for item in final_candidates: 
            history.append(item['url'])
        
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: 
            json.dump(history, f)

        return final_candidates

    except Exception as e:
        print(f"Search Error: {e}")
        return []

# ==========================================
# 4. AI 요약 및 필터링 (핵심 로직)
# ==========================================
def summarize_news(news_list):
    if not news_list: 
        return []

    print(f"Gemini에게 {len(news_list)}건에 대한 '필터링 및 요약' 요청 중...")
    
    # 모델 버전 확인 (gemini-1.5-flash 또는 gemini-2.0-flash 사용)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # 프롬프트: AI에게 편집장 역할을 부여하고 엄격한 필터링 요구
    # JSON 형식을 강제하기 위해 f-string 내 중괄호는 {{ }}로 이스케이프 처리함
    prompt = f"""
    너는 까다로운 'IT 보안 전문 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    아래 제공된 뉴스 기사 목록(JSON)을 보고 다음 단계를 수행해라.

    [1단계: 엄격한 필터링]
    - 제목과 내용을 분석하여 **'정보보호, 해킹, 보안, 개인정보 유출'**과 직접 관련된 기술/사회 뉴스만 남겨라.
    - **제외 대상(삭제):** 1. 스포츠 뉴스 (예: 야구장 '보안' 요원, 축구 경기 안전) -> 무조건 삭제.
      2. 연예/가십 (예: 배우 사생활 사진 유출) -> 보안 기술 이슈가 아니면 삭제.
      3. 단순 주식 시황, 홍보성 보도자료.
    
    [2단계: 요약 및 정제]
    - 살아남은 기사에 대해:
      1. 'source': 언론사명 추출.
      2. 'date': 발행일 추출.
      3. 'summary': 내용을 한국어로 3줄 이내 핵심 요약.

    [3단계: 출력 형식]
    - 오직 **JSON 리스트** 형식으로만 출력해라. (마크다운 코드블록 없이)
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [ {{ "title": "기사제목", "source": "언론사", "summary": "요약문", "date": "날짜", "url": "링크" }} ]
    """
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    data = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": safety_settings}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: 
                return []
            
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # JSON 파싱 (앞뒤 잡다한 텍스트 제거)
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1: 
                return []
            
            result = json.loads(text[start:end])
            print(f"✅ AI 필터링 및 요약 완료: {len(news_list)}개 -> {len(result)}개 선정됨.")
            return result
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Summarize Error: {e}")
        return []

# ==========================================
# 5. PDF 생성
# ==========================================
def create_pdf(articles, filename):
    if not articles: 
        return

    print(f"PDF 생성 중 ({filename})...")
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 설정 (시스템 폰트 또는 기본값)
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security Briefing ({TODAY_STR})", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        source_name = article.get('source', 'News')
        title_text = f"{idx}. {article['title']} ({source_name})"
        
        # 제목
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102) # 남색
        pdf.multi_cell(0, 8, title_text)
        
        # 날짜
        pdf.set_font_size(9)
        pdf.set_text_color(100, 100, 100)
        date_str = article.get('date', '')
        pdf.cell(0, 5, f"Date: {date_str}", ln=True)
        
        # 요약문
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        # QR 코드 생성 및 삽입
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        y_pos = pdf.get_y()
        # 페이지 넘어감 방지 로직
        if y_pos > 240: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        # 링크 텍스트
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[Link]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
