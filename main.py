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

# 1. 환경변수
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
TO_EMAIL = os.environ.get("TO_EMAIL") or EMAIL_USER

HISTORY_FILE = "history.json"

# ★ 수정 1: 종합 일간지(조선,동아 등)를 빼고 'IT/보안 전문지' 위주로 압축
# (야구 기사 유입을 원천적으로 줄이기 위함)
TARGET_DOMAINS = [
    "boannews.com",     # 보안뉴스 (가장 정확함)
    "dailysecu.com",    # 데일리시큐
    "etnews.com",       # 전자신문
    "zdnet.co.kr",      # 지디넷코리아
    "datanet.co.kr",    # 데이터넷
    "ddaily.co.kr",     # 디지털데일리
    "digitaltoday.co.kr", # 디지털투데이
    "byline.network",   # 바이라인네트워크
    "itworld.co.kr",    # ITWorld
    "ciokorea.com",     # CIO Korea
    "bloter.net",       # 블로터
    "yna.co.kr"         # 연합뉴스 (종합지 중 유일하게 포함 - 속보용)
]

# 2. 날짜 검증 함수
def is_recent_article(date_string, days_limit=3):
    if not date_string:
        return True 
    try:
        pub_date = parser.parse(date_string)
        pub_date = pub_date.replace(tzinfo=None)
        now = datetime.now()
        diff = now - pub_date
        return diff.days <= days_limit and diff.days >= -1
    except:
        return True

# 3. 중복 필터링
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

# 4. 뉴스 검색 (수정: 스포츠 제외 키워드 추가)
def search_news(query):
    # ★ 수정 2: 검색어에 '-야구 -스포츠' 등을 넣어 야구 기사 원천 차단
    # "query" argument는 무시하고 여기서 정의한 강력한 쿼리를 사용합니다.
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안 -야구 -축구 -스포츠 -MLB -KBO -연예"
    
    print(f"'{optimized_query}' 검색 중 (보안 전문지 중심)...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    response = tavily.search(
        query=optimized_query, 
        topic="news",
        search_depth="advanced", 
        max_results=30, 
        include_domains=TARGET_DOMAINS,
        days=3
    )
    
    raw_results = response['results']
    print(f"1차 검색결과: {len(raw_results)}개. 검증 시작...")
    
    date_filtered_results = []
    for item in raw_results:
        # 제목에 '야구', '홈런' 같은 단어가 있으면 파이썬에서 한번 더 컷!
        title = item.get('title', '')
        if any(bad_word in title for bad_word in ['야구', '축구', '경기', '스포츠', '배우', '드라마']):
            continue

        pub_date = item.get('published_date')
        if is_recent_article(pub_date, days_limit=3):
            date_filtered_results.append(item)

    final_candidates, history = filter_new_articles(date_filtered_results)
    
    # 10개 선정
    final_selection = final_candidates[:10]
    print(f"최종 선정된 기사: {len(final_selection)}개")

    for item in final_selection:
        history.append(item['url'])
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection

# 5. AI 요약
def summarize_news(news_list):
    if not news_list:
        return []

    print(f"Gemini에게 {len(news_list)}건 요약 요청...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 보안 뉴스 전문 편집장이야. 아래 뉴스 데이터를 분석해 JSON 리스트로 반환해.
    
    [규칙]
    1. 주제 필터링: '정보보호', '해킹', '보안', '개인정보' 관련 기사만 남겨. (스포츠, 연예 절대 제외)
    2. 언어: 내용은 반드시 '한국어'로 작성해.
    3. 형식: 오직 JSON 리스트만 출력해. (마크다운 ```json 없이)
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "제목", "summary": "요약", "url": "http://..."}},
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
            if 'candidates' not in res_json or not res_json['candidates']:
                print("🚨 오류: AI 답변 없음")
                return []
                
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1: return []
            
            return json.loads(text[start:end])
        else:
            print(f"API Error: {response.text}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

# 6. PDF 생성
def create_pdf(articles, filename="briefing.pdf"):
    if not articles:
        print("PDF 생성 중단: 기사 없음")
        return

    print("PDF 생성 중...")
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security News ({datetime.now().strftime('%Y-%m-%d')})", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102)
        pdf.multi_cell(0, 8, f"{idx}. {article['title']}")
        
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        y_pos = pdf.get_y()
        if y_pos > 240: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[기사 원문 보기]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 7. 이메일 발송
def send_email(pdf_filename):
    if not os.path.exists(pdf_filename):
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 국내 보안 뉴스 브리핑"

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
        if news_data:
            analyzed_data = summarize_news(news_data)
            if analyzed_data:
                create_pdf(analyzed_data)
                send_email("briefing.pdf")
                print("발송 완료!")
            else:
                print("요약 결과가 없습니다 (모두 필터링됨)")
        else:
            print("검색된 기사가 없습니다")
                
    except Exception as e:
        print(f"오류 발생: {e}")
