import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from fpdf import FPDF
from tavily import TavilyClient
import google.generativeai as genai

# 1. 환경변수 설정 (GitHub Secrets에서 가져옴)
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")

# 2. 뉴스 검색 함수
def search_news(query):
    tavily = TavilyClient(api_key=TAVILY_KEY)
    response = tavily.search(query=query, search_depth="basic", max_results=5)
    return response['results']

# 3. AI 요약 함수 (Gemini)
def summarize_news(news_list):
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    다음 뉴스들을 '일일 정보보호 브리핑' 보고서용으로 요약해줘.
    각 기사마다 [제목], [핵심내용 3줄], [링크] 형식으로 정리해.
    
    뉴스 목록:
    {news_list}
    """
    response = model.generate_content(prompt)
    return response.text

# 4. PDF 생성 함수 (한글 폰트 필수!)
def create_pdf(text, filename="briefing.pdf"):
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 추가 (반드시 저장소에 폰트 파일이 있어야 함)
    # NanumGothic.ttf 파일이 같은 폴더에 있다고 가정
    pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
    pdf.set_font('Nanum', '', 12)
    
    pdf.multi_cell(0, 10, text)
    pdf.output(filename)

# 5. 이메일 발송 함수
def send_email(pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_USER
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 정보보호 뉴스 브리핑"

    body = "첨부된 PDF 파일을 확인해주세요."
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
    print("1. 검색 중...")
    news = search_news("정보보호 최신 뉴스")
    
    print("2. 요약 중...")
    summary = summarize_news(news)
    
    print("3. PDF 생성 중...")
    create_pdf(summary)
    
    print("4. 메일 발송 중...")
    send_email("briefing.pdf")
    print("완료!")