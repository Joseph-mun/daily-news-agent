import os
import smtplib
import requests  # 구글 라이브러리 대신 requests 사용
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from fpdf import FPDF
from tavily import TavilyClient

# 1. 환경변수 설정
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
TO_EMAIL = os.environ.get("TO_EMAIL") # 받는 사람 (Secrets에 설정했다면)
if not TO_EMAIL:
    TO_EMAIL = EMAIL_USER # 설정 안했으면 내게 쓰기

# 2. 뉴스 검색 함수
def search_news(query):
    print(f"검색어 '{query}'로 검색을 시작합니다...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    response = tavily.search(query=query, search_depth="basic", max_results=5)
    return response['results']

# 3. AI 요약 함수 (REST API 방식 - 가장 안정적)
def summarize_news(news_list):
    print("Gemini에게 요약을 요청합니다...")
    
    # 모델 변경: gemini-1.5-flash -> gemini-pro (가장 안정적)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 보안 전문가야. 다음 뉴스들을 '일일 정보보호 브리핑' 보고서용으로 요약해줘.
    각 기사마다:
    1. [제목]
    2. [핵심내용 3줄 요약]
    3. [링크]
    형식으로 정리해줘.
    
    뉴스 목록:
    {news_list}
    """
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except KeyError:
            return "요약 실패: 응답 형식이 예상과 다릅니다."
    else:
        print(f"에러 발생: {response.text}")
        return f"요약 실패 (에러코드: {response.status_code})"

# 4. PDF 생성 함수
def create_pdf(text, filename="briefing.pdf"):
    print("PDF를 생성합니다...")
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 파일 확인 (없으면 에러 방지를 위해 기본 폰트 사용 시도)
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 11)
    else:
        print("경고: NanumGothic.ttf 폰트가 없습니다! 한글이 깨질 수 있습니다.")
        pdf.set_font("Arial", size=12) # 영문 대체 폰트
    
    # 줄바꿈 처리를 위해 multi_cell 사용
    pdf.multi_cell(0, 8, text)
    pdf.output(filename)

# 5. 이메일 발송 함수
def send_email(pdf_filename):
    print(f"{TO_EMAIL} 주소로 메일을 발송합니다...")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 정보보호 뉴스 브리핑"

    body = "오늘의 보안 뉴스 브리핑 PDF가 도착했습니다."
    msg.attach(MIMEText(body, 'plain'))

    with open(pdf_filename, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {pdf_filename}")
        msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.send_message(msg)
    server.quit()

# 실행 흐름
if __name__ == "__main__":
    try:
        news = search_news("정보보호 최신 뉴스")
        summary = summarize_news(news)
        create_pdf(summary)
        send_email("briefing.pdf")
        print("모든 작업이 성공적으로 완료되었습니다!")
    except Exception as e:
        print(f"치명적인 오류 발생: {e}")
