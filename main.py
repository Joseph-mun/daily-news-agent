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

# 중복 방지를 위한 히스토리 파일명
HISTORY_FILE = "history.json"

# 2. 중복 기사 필터링 함수 (핵심 로직)
def filter_new_articles(results):
    # 기존 기록 불러오기
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except:
                history = []
    else:
        history = []

    new_results = []
    # 이미 보낸 URL인지 확인
    for item in results:
        if item['url'] not in history:
            new_results.append(item)
            history.append(item['url']) # 기록에 추가
    
    # 기록이 너무 길어지면 최근 500개만 유지
    if len(history) > 500:
        history = history[-500:]
        
    # 변경된 기록 저장
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)
        
    return new_results

# 3. 뉴스 검색 (Top 10)
def search_news(query):
    print(f"'{query}' 검색 중...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    # 3. 요청하신 대로 Top 10개 검색
    response = tavily.search(query=query, search_depth="basic", max_results=10)
    
    # 5. 중복 제거 실행
    filtered = filter_new_articles(response['results'])
    print(f"검색된 {len(response['results'])}개 중 신규 기사 {len(filtered)}개를 찾았습니다.")
    return filtered

# 4. AI 상세 요약
def summarize_news(news_list):
    if not news_list:
        return []

    print("Gemini에게 상세 요약 요청 중...")
    
    # 모델: gemini-2.5-flash (사용자 환경에 맞춰진 최신 모델)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # JSON 형식으로 답변하라고 강제함
    prompt = f"""
    너는 보안 분석가야. 다음 뉴스 기사들을 분석해서 JSON 형식으로 반환해.
    각 기사마다 다음 정보를 포함해야 해:
    1. title: 기사 제목 (핵심을 담아 간결하게)
    2. summary: 기사의 핵심 내용을 3문장 정도로 상세하게 요약
    3. url: 기사 원문 링크 (제공된 url 그대로)
    
    [기사 목록]
    {json.dumps(news_list)}
    
    [응답 형식 예시]
    [
        {{"title": "북한 해킹 그룹의 신종 수법", "summary": "내용...", "url": "http://..."}},
        ...
    ]
    응답은 오직 JSON 리스트만 출력해. 마크다운 코드블럭(```json) 쓰지 마.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        try:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            # 혹시 마크다운이 섞여있을 경우 제거
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            print(f"JSON 파싱 실패: {e}")
            return []
    else:
        print(f"API 에러: {response.text}")
        return []

# 5. PDF 생성 (Bold, QR코드 포함)
def create_pdf(articles, filename="briefing.pdf"):
    print("PDF 생성 중...")
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 설정 (Bold 효과를 위해 폰트가 2개 필요하지만, 없으면 크기와 굵기 옵션으로 대체)
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    pdf.cell(0, 10, f"Daily Security Briefing ({datetime.now().strftime('%Y-%m-%d')})", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        # 1. 제목 (Bold 처리 대신 크기를 키우고 진하게)
        pdf.set_font_size(14)
        # FPDF 기본 bold('B')는 폰트 파일이 bold를 지원해야 함. 
        # 여기선 크기로 강조
        pdf.multi_cell(0, 8, f"{idx}. {article['title']}")
        
        # 2. 내용 요약
        pdf.set_font_size(10)
        pdf.ln(2)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        # 4. QR코드 생성
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        # QR코드 삽입 (오른쪽 아래에 배치)
        # 현재 Y 위치 저장
        y_before_qr = pdf.get_y()
        pdf.image(qr_filename, x=170, y=y_before_qr, w=20) # 우측 배치
        
        # URL 텍스트 출력
        pdf.set_text_color(0, 0, 255) # 파란색
        pdf.cell(0, 10, "Read More (Click or Scan) ->", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0) # 검은색 복귀
        
        # QR코드 공간만큼 띄우기
        pdf.ln(15)
        
        # 임시 QR 파일 삭제
        os.remove(qr_filename)
        
        # 구분선
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 6. 이메일 발송
def send_email(pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 보안 뉴스 브리핑 ({TO_EMAIL}님)"

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
        # 중복 방지 로직이 포함된 검색
        news_data = search_news("정보보호 최신 뉴스")
        
        if not news_data:
            print("새로운 뉴스가 없습니다.")
        else:
            # AI 분석
            analyzed_data = summarize_news(news_data)
            if analyzed_data:
                create_pdf(analyzed_data)
                send_email("briefing.pdf")
                print("발송 완료!")
            else:
                print("요약할 데이터가 없습니다.")
                
    except Exception as e:
        print(f"오류 발생: {e}")
