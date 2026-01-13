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
from email import encoders
from fpdf import FPDF
from tavily import TavilyClient

# 1. 환경변수 설정
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
TO_EMAIL = os.environ.get("TO_EMAIL") or EMAIL_USER

HISTORY_FILE = "history.json"

# ★ 국내 주요 보안 및 IT 언론사 리스트
TARGET_DOMAINS = [
    "yna.co.kr",        # 연합뉴스
    "etnews.com",       # 전자신문
    "zdnet.co.kr",      # 지디넷코리아
    "boannews.com",     # 보안뉴스
    "dailysecu.com",    # 데일리시큐
    "datanet.co.kr",    # 데이터넷
    "ddaily.co.kr",     # 디지털데일리
    "digitaltoday.co.kr", # 디지털투데이
    "inews24.com",      # 아이뉴스24
    "bloter.net",       # 블로터
    "itworld.co.kr",    # ITWorld
    "ciokorea.com",     # CIO Korea
    "hani.co.kr",       # 한겨레
    "chosun.com",       # 조선일보
    "donga.com",        # 동아일보
    "joongang.co.kr",   # 중앙일보
    "mk.co.kr",         # 매일경제
    "hankyung.com",     # 한국경제
    "mt.co.kr",         # 머니투데이
    "newsis.com",       # 뉴시스
    "news1.kr"          # 뉴스1
]

# 2. 날짜 검증 함수
def is_recent_article(date_string, days_limit=3):
    if not date_string:
        return True # 날짜 없으면 API 믿고 통과
    
    try:
        pub_date = parser.parse(date_string)
        pub_date = pub_date.replace(tzinfo=None)
        now = datetime.now()
        diff = now - pub_date
        # 미래 날짜 포함, 설정된 일수 이내
        return diff.days <= days_limit and diff.days >= -1
    except Exception:
        return True

# 3. 중복 기사 필터링
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
        if item['url'] not in history:
            new_results.append(item)
            
    return new_results, history

# 4. 뉴스 검색 (국내 언론사 한정)
def search_news(query):
    # 검색어 최적화
    optimized_query = "정보보호 OR 개인정보유출 OR 해킹사고 OR 사이버보안"
    
    print(f"'{optimized_query}' 검색 중 (국내 주요 언론사 한정)...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    response = tavily.search(
        query=optimized_query, 
        topic="news",
        search_depth="advanced", 
        max_results=30, 
        include_domains=TARGET_DOMAINS, # 국내 사이트만 검색
        days=2
    )
    
    raw_results = response['results']
    print(f"1차 검색결과: {len(raw_results)}개. 날짜/중복 검증 시작...")
    
    date_filtered_results = []
    for item in raw_results:
        pub_date = item.get('published_date')
        if is_recent_article(pub_date, days_limit=3):
            date_filtered_results.append(item)

    final_candidates, history = filter_new_articles(date_filtered_results)
    
    # 10개 선정
    final_selection = final_candidates[:10]
    print(f"최종 선정된 기사: {len(final_selection)}개")

    # 히스토리 업데이트 (메모리상)
    for item in final_selection:
        history.append(item['url'])
        
    # 파일 저장
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection

# 5. AI 상세 요약 (필터링 제거: 무조건 요약 모드)
def summarize_news(news_list):
    if not news_list:
        return []

    print(f"Gemini에게 {len(news_list)}건 요약 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # 프롬프트 수정: "관련 기사만 남겨" -> "모든 기사를 요약해" 로 변경
    prompt = f"""
    너는 보안 뉴스 전문 편집장이야. 아래 뉴스 데이터를 분석해 JSON 리스트로 반환해.
    
    [규칙]
    1. 분석 대상: 필터링하지 말고, 입력된 '모든' 기사를 포함해서 요약해.
    2. 언어: 내용은 반드시 '한국어'로 작성해.
    3. 형식: 오직 JSON 리스트만 출력해. (설명이나 마크다운 없이)
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "기사 제목", "summary": "핵심 내용 3줄 요약", "url": "http://..."}},
        ...
    ]
    """
    
    # 안전 필터 해제
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
            
            if 'candidates' not in res_json or not res_json['candidates']:
                print("🚨 오류: AI가 답변을 생성하지 않았습니다.")
                print(f"응답 원본: {res_json}")
                return []
                
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # JSON 파싱 시도
            start_index = text.find('[')
            end_index = text.rfind(']') + 1
            
            if start_index == -1:
                print("🚨 오류: AI 답변에서 JSON 리스트([])를 찾을 수 없습니다.")
                print(f"🤖 AI가 한 말: {text}") 
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

# 6. PDF 생성
def create_pdf(articles, filename="briefing.pdf"):
    print("PDF 생성 중...")
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    # 타이틀
    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security News ({datetime.now().strftime('%Y-%m-%d')})", ln=True, align='C')
    pdf.set_font_size(10)
    pdf.cell(0, 10, "Domestic Security News Briefing", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        # 제목
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102)
        pdf.multi_cell(0, 8, f"{idx}. {article['title']}")
        
        # 요약
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        # QR 생성
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        # 페이지 넘김 체크
        y_pos = pdf.get_y()
        if y_pos > 240: 
            pdf.add_page()
            y_pos = pdf.get_y()

        # QR 배치
        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        # 링크 텍스트
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[기사 원문 보기]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        os.remove(qr_filename)
        
        # 구분선
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 7. 이메일 발송
def send_email(pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 정보보호 뉴스 브리핑"

    with open(pdf_filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={pdf_filename}")
        msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.send_message(msg)
    server.quit()

if __name__ == "__main__":
    try:
        news_data = search_news("") 
        
        if not news_data:
            print("조건에 맞는 국내 뉴스가 없습니다.")
        else:
            analyzed_data = summarize_news(news_data)
            if analyzed_data:
                create_pdf(analyzed_data)
                send_email("briefing.pdf")
                print("국내 뉴스 발송 완료!")
            else:
                print("요약 과정 실패 (데이터 없음)")
                
    except Exception as e:
        print(f"오류 발생: {e}")
