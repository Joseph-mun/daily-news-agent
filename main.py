import os
import smtplib
import requests
import json
import qrcode
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.header import Header
from email import encoders
from fpdf import FPDF
from tavily import TavilyClient

# ==========================================
# 1. 환경변수 및 경로 설정
# ==========================================
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
MAIN_RECIPIENT = os.environ.get("TO_EMAIL") or EMAIL_USER

# 수신자 리스트
RECIPIENTS = []
if MAIN_RECIPIENT: RECIPIENTS.append(MAIN_RECIPIENT)
ADDITIONAL_EMAIL = "joseph.moon@shinhan.com"
if ADDITIONAL_EMAIL not in RECIPIENTS: RECIPIENTS.append(ADDITIONAL_EMAIL)

# [NEW] 디렉토리 설정
DATA_DIR = "data"
OUTPUT_DIR = "output"

# 디렉토리가 없으면 생성
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 파일 경로 설정
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
TODAY_COMPACT = NOW.strftime("%Y%m%d")
PDF_FILENAME = os.path.join(OUTPUT_DIR, f"주요 뉴스 요약_{TODAY_COMPACT}.pdf")

# [핵심] 수집 대상 국내 주요 언론사 리스트
TARGET_DOMAINS = [
    # 1. IT & 보안 전문지 (최우선)
    "boannews.com", "dailysecu.com", "etnews.com", "zdnet.co.kr", 
    "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", "bloter.net", 
    "itworld.co.kr", "ciokorea.com", "byline.network",
    # 2. 주요 통신사 (속보)
    "yna.co.kr", "news1.kr", "newsis.com",
    # 3. 경제지 (금융/산업 이슈)
    "mk.co.kr", "hankyung.com", "mt.co.kr", "fnnews.com", "sedaily.com",
    # 4. 종합 일간지 (사회적 파장)
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "khan.co.kr"
]

# ==========================================
# 2. 유틸리티 함수 (중복 필터링)
# ==========================================
def filter_new_articles(results):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []
    else: history = []

    new_results = []
    for item in results:
        # 히스토리에 없는 URL만 통과
        if item.get('url') and item['url'] not in history: 
            new_results.append(item)
    return new_results, history

# ==========================================
# 3. 뉴스 검색 (Tavily 도메인 필터링 적용)
# ==========================================
def search_news(query):
    # 검색어 최적화
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안 OR 랜섬웨어"
    
    print(f"[{TODAY_STR}] '{optimized_query}' 검색 시작...")
    print(f"대상: 국내 {len(TARGET_DOMAINS)}개 주요 언론사")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        
        # 지정된 국내 도메인에서만 검색
        response = tavily.search(
            query=optimized_query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS, 
            max_results=50, 
            days=3 
        )
        
        raw_results = response.get('results', [])
        print(f"1차 API 검색결과: {len(raw_results)}개 확보.")
        
        final_candidates, history = filter_new_articles(raw_results)
        print(f"중복 제거 후 AI 검수 대상: {len(final_candidates)}개")

        # 히스토리 업데이트
        for item in final_candidates: 
            history.append(item['url'])
        
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: 
            json.dump(history, f)

        return final_candidates

    except Exception as e:
        print(f"Search Error: {e}")
        return []

# ==========================================
# 4. AI 요약 (Gemini 1.5 Flash)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print(f"Gemini에게 {len(news_list)}건 정밀 검수 및 요약 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 대한민국 최고의 'IT 보안 전문 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    Tavily가 국내 언론사에서 수집한 뉴스 목록이 아래에 있다.
    이를 검토하여 다음 기준에 맞춰 정제하고 요약해라.
    
    [심사 기준]
    1. **주제 적합성:** '정보보호, 해킹, 개인정보, 사이버보안'과 직접 관련된 기사만 남겨라.
    2. **노이즈 제거:**
       - 스포츠(야구, 축구), 연예, 단순 인사/부고, 주식 시황 기사 삭제.
       - 중복 기사는 대표적인 1개만 남김.
    3. **요약:** 선정된 기사는 한국어로 3줄 이내 핵심 요약.

    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 포맷 (JSON List Only)]
    [ {{ "title": "기사제목", "source": "언론사명", "summary": "요약내용", "date": "발행일", "url": "링크" }} ]
    """
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: return []
            
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # JSON 파싱
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1: return []
            
            result = json.loads(text[start:end])
            print(f"✅ AI 필터링 완료: {len(result)}개 선정됨.")
            return result
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Summarize Error: {e}")
        return []

# ==========================================
# 5. PDF 생성 (output 폴더 저장)
# ==========================================
def create_pdf(articles, filename, is_empty=False):
    print(f"PDF 생성 중 ({filename})...")
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 설정 (루트 경로에 있는 폰트 파일 사용)
    font_path = 'NanumGothic.ttf'
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    # 헤더
    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security Briefing ({TODAY_STR})", ln=True, align='C')
    pdf.ln(10)

    # 기사 없음 처리
    if is_empty or not articles:
        pdf.set_font_size(12)
        pdf.multi_cell(0, 10, "No significant domestic security news found today.\n(주요 국내 보안 뉴스가 없습니다.)", align='C')
        pdf.output(filename)
        return

    # 기사 출력
    for idx, article in enumerate(articles, 1):
        source_name = article.get('source', 'News')
        title_text = f"{idx}. {article['title']} ({source_name})"
        
        # 제목
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102)
        pdf.multi_cell(0, 8, title_text)
        
        # 날짜
        pdf.set_font_size(9)
        pdf.set_text_color(100, 100, 100)
        date_str = article.get('date', '')
        pdf.cell(0, 5, f"Date: {date_str}", ln=True)
        
        # 요약
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        # QR 코드 (임시 파일 생성 후 삭제)
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        y_pos = pdf.get_y()
        if y_pos > 240: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        # 링크
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[Original Link]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        if os.path.exists(qr_filename):
            os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# ==========================================
# 6. 이메일 발송 (경로 정리 포함)
# ==========================================
def send_email(pdf_filename):
    if not os.path.exists(pdf_filename): 
        print(f"❌ 발송 실패: 파일 없음 ({pdf_filename})")
        return
    if not RECIPIENTS: 
        print("❌ 발송 실패: 수신자 리스트 없음")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(RECIPIENTS)
    msg['Subject'] = Header(f"[{TODAY_STR}] 국내 주요 정보보호 뉴스 브리핑", 'utf-8')

    body = f"""
    안녕하세요.
    {TODAY_STR}일자 국내 주요 보안 뉴스 브리핑입니다.
    
    국내 주요 IT/보안 언론사 {len(TARGET_DOMAINS)}곳을 대상으로
    AI가 선별 및 요약한 내용을 첨부드립니다.
    
    감사합니다.
    """
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # 첨부파일 처리 (파일명 깔끔하게)
    with open(pdf_filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        
        # [중요] 경로(output/...)를 떼고 파일명만 메일에 표시
        clean_filename = os.path.basename(pdf_filename)
        part.add_header('Content-Disposition', 'attachment', filename=Header(clean_filename, 'utf-8').encode())
        msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        print(f"✅ 메일 발송 완료: {len(RECIPIENTS)}명")
    except Exception as e:
        print(f"❌ Email Error: {e}")

# ==========================================
# 7. 메인 실행
# ==========================================
if __name__ == "__main__":
    try:
        # 1. 뉴스 검색
        news_data = search_news("") 
        
        final_data = []
        if news_data:
            # 2. AI 필터링 및 요약
            final_data = summarize_news(news_data)
        
        # 3. 결과 처리 (항상 PDF 생성)
        if final_data:
            create_pdf(final_data, PDF_FILENAME, is_empty=False)
            send_email(PDF_FILENAME)
        else:
            print("ℹ️ 결과 없음: '뉴스 없음' PDF 생성")
            create_pdf([], PDF_FILENAME, is_empty=True)
            # send_email(PDF_FILENAME) # 필요 시 주석 해제

    except Exception as e:
        print(f"🔥 Critical Error: {e}")
