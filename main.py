import os
import smtplib
import requests
import json
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from fpdf import FPDF
from tavily import TavilyClient

# 1. 환경변수
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
TO_EMAIL = os.environ.get("TO_EMAIL") or EMAIL_USER

# 2. 뉴스 검색
def search_news(query):
    print(f"검색어 '{query}'로 검색 중...")
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        response = tavily.search(query=query, search_depth="basic", max_results=5)
        return response['results']
    except Exception as e:
        return [{"content": f"검색 실패: {str(e)}"}]

# 3. 모델 목록 조회 (디버깅용)
def get_available_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            models = response.json().get('models', [])
            # 'generateContent' 기능을 지원하는 모델만 필터링
            chat_models = [m['name'] for m in models if 'generateContent' in m['supportedGenerationMethods']]
            return "\n".join(chat_models)
        else:
            return f"모델 목록 조회 실패: {response.status_code}"
    except Exception as e:
        return f"연결 오류: {str(e)}"

# 4. AI 요약 (자동 복구 기능 포함)
def summarize_news(news_list):
    print("AI 요약 시도 중...")
    
    # 시도해볼 모델 후보들 (가장 최신 모델인 2.5 Flash를 1순위로 설정)
    candidates = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro"]
    
    prompt = f"""
    뉴스 목록을 읽고 '보안 뉴스 브리핑'을 3줄로 요약해.
    뉴스: {news_list}
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}

    for model_name in candidates:
        print(f"모델 시도: {model_name}...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_KEY}"
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            try:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            except:
                continue # 응답 형식이 이상하면 다음 모델로
        elif response.status_code == 404:
            continue # 모델 없으면 다음 후보로 넘어감
        else:
            # 404가 아닌 다른 에러면 멈춤
            break
            
    # 모든 후보가 실패했을 때 -> 진단 리포트 작성
    available_list = get_available_models()
    error_msg = f"""
    [요약 실패 보고서]
    설정된 모델들({candidates})이 모두 404 에러를 냈거나 작동하지 않습니다.
    
    현재 API 키로 사용 가능한 모델 목록:
    -----------------------------------
    {available_list}
    -----------------------------------
    위 목록에 있는 이름 중 하나를 골라 main.py의 candidates 리스트에 넣으세요.
    """
    print(error_msg)
    return error_msg

# 5. PDF 생성
def create_pdf(text, filename="briefing.pdf"):
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 설정 (폰트 파일 없으면 영문 기본폰트)
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 11)
    else:
        pdf.set_font("Arial", size=10)
    
    # 텍스트가 너무 길거나 에러 메시지일 경우를 대비해 인코딩 처리
    # fpdf의 multi_cell은 자동 줄바꿈을 지원함
    pdf.multi_cell(0, 8, text)
    pdf.output(filename)

# 6. 이메일 발송
def send_email(pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 보안 뉴스 브리핑 (결과)"

    body = "첨부된 PDF를 확인해주세요."
    msg.attach(MIMEText(body, 'plain'))

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
    news = search_news("정보보호 최신 뉴스")
    summary = summarize_news(news) # 여기서 자동으로 모델을 찾거나 에러 리포트를 만듦
    create_pdf(summary)
    send_email("briefing.pdf")
