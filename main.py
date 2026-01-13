import os
import smtplib
import requests
import json
import qrcode
from datetime import datetime
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

# ★ 검색할 주요 언론사 및 보안 전문지 리스트 (원하는 곳이 있으면 추가/삭제 가능)
TARGET_DOMAINS = [
    "yna.co.kr",        # 연합뉴스
    "etnews.com",       # 전자신문
    "zdnet.co.kr",      # ZDNet Korea
    "boannews.com",     # 보안뉴스
    "dailysecu.com",    # 데일리시큐
    "datanet.co.kr",    # 데이터넷
    "ddaily.co.kr",     # 디지털데일리
    "hani.co.kr",       # 한겨레
    "chosun.com",       # 조선일보
    "donga.com",        # 동아일보
    "joongang.co.kr",   # 중앙일보
    "mk.co.kr"          # 매일경제
]

# 2. 중복 기사 필터링
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
        # URL이 이미 기록에 있으면 건너뜀
        if item['url'] not in history:
            new_results.append(item)
            history.append(item['url'])
    
    if len(history) > 500:
        history = history[-500:]
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)
        
    return new_results

# 3. 뉴스 검색 (도메인 제한 적용)
def search_news(query):
    print(f"'{query}' 검색 중 (신뢰할 수 있는 언론사 기준)...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    # include_domains 옵션으로 지정된 언론사에서만 검색
    response = tavily.search(
        query=query, 
        search_depth="basic", 
        max_results=10,
        include_domains=TARGET_DOMAINS,
        days=1
    )
    
    filtered = filter_new_articles(response['results'])
    print(f"검색된 {len(response['results'])}개 중 신규 기사 {len(filtered)}개를 찾았습니다.")
    return filtered

# 4. AI 상세 요약 (제목 원문 유지)
def summarize_news(news_list):
    if not news_list:
        return []

    print("Gemini에게 요약 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # 프롬프트 수정: 제목과 URL은 원본 유지 강조
    prompt = f"""
    너는 보안 뉴스 큐레이터야. 제공된 뉴스 데이터(JSON)를 바탕으로 다음 작업을 수행해:
    
    1. 각 뉴스의 내용을 분석하여 3줄 이내로 핵심을 요약해.
    2. '제목(title)'과 '링크(url)'는 절대 변경하지 말고 원본 데이터 그대로 사용해.
    3. 결과는 반드시 JSON 리스트 형식으로만 출력해.
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "원문 기사 제목 그대로", "summary": "AI가 요약한 내용...", "url": "http://original-link.com"}},
        ...
    ]
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        try:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            print(f"JSON 파싱 실패: {e}")
            # 파싱 실패 시 원본 리스트라도 반환 시도 (요약 없이)
            return [] 
    else:
        print(f"API 에러: {response.text}")
        return []

# 5. PDF 생성 (디자인 개선)
def create_pdf(articles, filename="briefing.pdf"):
    print("PDF 생성 중...")
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    # 헤더
    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security News ({datetime.now().strftime('%Y-%m-%d')})", ln=True, align='C')
    pdf.set_font_size(10)
    pdf.cell(0, 10, "Selected from Major Tech & Security Media", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        # 1. 신문사 원문 제목 (강조)
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102) # 남색 계열
        # 제목이 너무 길 경우를 대비해 multi_cell 사용하되 높이 조절
        pdf.multi_cell(0, 8, f"{idx}. {article['title']}")
        
        # 2. 요약 내용
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0) # 검정
        pdf.ln(2)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        # 3. QR 코드 (원문 링크 direct)
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url']) # 여기서 원문 URL 사용됨
        qr.save(qr_filename)
        
        # QR 코드 배치 (우측 하단)
        y_pos = pdf.get_y()
        # 페이지가 거의 다 찼으면 다음 페이지로 넘김
        if y_pos > 250: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        # 텍스트 링크
        pdf.set_text_color(0, 102, 204) # 파란색
        pdf.cell(0, 5, "[Read Original Article]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        os.remove(qr_filename)
        
        # 구분선
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 6. 이메일 발송
def send_email(pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 주요 언론사 보안 뉴스 브리핑"

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
        news_data = search_news("정보보호 해킹 보안사고") # 키워드 살짝 보강
        
        if not news_data:
            print("조건에 맞는 새로운 뉴스가 없습니다.")
        else:
            analyzed_data = summarize_news(news_data)
            if analyzed_data:
                create_pdf(analyzed_data)
                send_email("briefing.pdf")
                print("발송 완료!")
            else:
                print("요약 과정에서 문제가 발생했습니다.")
                
    except Exception as e:
        print(f"오류 발생: {e}")
