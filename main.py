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

RECIPIENTS = []
if MAIN_RECIPIENT: RECIPIENTS.append(MAIN_RECIPIENT)
ADDITIONAL_EMAIL = "joseph.moon@shinhan.com"
if ADDITIONAL_EMAIL not in RECIPIENTS: RECIPIENTS.append(ADDITIONAL_EMAIL)

DATA_DIR = "data"
OUTPUT_DIR = "output"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
TODAY_COMPACT = NOW.strftime("%Y%m%d")
PDF_FILENAME = os.path.join(OUTPUT_DIR, f"주요 뉴스 요약_{TODAY_COMPACT}.pdf")

# [핵심] 테스트에서 검증된 'IT/보안 전문지' 위주의 도메인 리스트
TARGET_DOMAINS = [
    "news.naver.com",      # 네이버 뉴스
    "boannews.com",        # 보안뉴스
    "dailysecu.com",       # 데일리시큐
    "etnews.com",          # 전자신문
    "zdnet.co.kr",         # 지디넷코리아
    "datanet.co.kr",       # 데이터넷
    "ddaily.co.kr",        # 디지털데일리
    "digitaltoday.co.kr",  # 디지털투데이
    "bloter.net",          # 블로터
    "itworld.co.kr",       # ITWorld
    "byline.network",      # 바이라인네트워크
    "ciokorea.com"         # CIO Korea
]

# ==========================================
# 2. 유틸리티 함수 (영문 필터링 안전장치 유지)
# ==========================================
def is_korean_article(url):
    """URL에 영어 섹션(/en/, /english/)이 포함되어 있으면 False 반환"""
    url_lower = url.lower()
    # 도메인을 좁혔지만 혹시 모를 영문 기사 유입을 방지하기 위한 2차 방어선
    exclude_patterns = [
        "/en/", "/english/", "/world-en/", "/sports-en/", 
        "cnn.com", "bbc.com", "reuters.com"
    ]
    for pat in exclude_patterns:
        if pat in url_lower:
            return False
    return True

def filter_new_articles(results):
    print("\n[단계 2] 기사 필터링 (영문 제외 및 중복 확인)...")
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []
    else: history = []

    new_results = []
    english_dropped = 0
    history_dropped = 0
    
    for item in results:
        url = item.get('url', '')
        
        # 1. 영문 기사 필터링
        if not is_korean_article(url):
            english_dropped += 1
            continue
            
        # 2. 히스토리 중복 필터링
        if url not in history: 
            new_results.append(item)
        else:
            history_dropped += 1

    print(f"  └ 영문/해외 기사 제외: {english_dropped}개")
    print(f"  └ 중복(히스토리) 제외: {history_dropped}개")
    print(f"  └ 최종 검수 대상: {len(new_results)}개")
    
    return new_results, history

# ==========================================
# 3. 뉴스 검색 (요청하신 쿼리 적용)
# ==========================================
def search_news(query):
    # 사용자 지정 검색어
    optimized_query = "정보보호 OR 해킹 OR 개인정보유출 OR 사이버보안 OR 랜섬웨어"
    
    print("="*60)
    print(f"[단계 1] Tavily 검색 시작: '{optimized_query}'")
    print(f"  └ 대상 도메인: {len(TARGET_DOMAINS)}개 (IT/보안 전문지)")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        
        response = tavily.search(
            query=optimized_query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS, 
            max_results=100
        )
        
        raw_results = response.get('results', [])
        print(f"\n[결과 1] Tavily 수집 기사: {len(raw_results)}개")
        
        final_candidates, history = filter_new_articles(raw_results)
        
        # 히스토리 업데이트
        for item in final_candidates: 
            history.append(item['url'])
        
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: 
            json.dump(history, f)

        return final_candidates

    except Exception as e:
        print(f"❌ Search Error: {e}")
        return []

# ==========================================
# 4. AI 요약 (Gemini 2.5 + 변수명 수정)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print("\n" + "="*60)
    print(f"[단계 3] AI(Gemini 2.5)에게 {len(news_list)}건 검수 요청")
    
    # [지정] gemini-2.5-flash 모델 URL 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [수정 완료] today_str -> TODAY_STR (전역변수)로 변경
    prompt = f"""
    너는 깐깐한 '보안 뉴스 편집장'이야. 
    오늘은 [ {TODAY_STR} ] 이야. 이 날짜를 기준으로 뉴스를 검수해.
    
    [작업 지시]
    1. 날짜 확인: 기사 내용이나 메타데이터를 보고, 오늘({TODAY_STR}) 기준으로 '2일 이내' 기사만 남겨. 
       (작년 기사나, 1주일 넘은 기사는 과감히 삭제해.)
    2. 주제 확인: '정보보호', '해킹', '보안' 관련 내용만 남겨. (스포츠, 단순홍보 제외)
    3. 대상 확정: 그 중에서 보안 뉴스 편집장으로서 판단하기에 중요도가 높은 기사를 최대 10개만 선정해
    4. 요약 작성: 핵심 내용을 한국어로 3줄 요약해.
    5. 날짜 추출: 기사의 발행일(YYYY-MM-DD)을 찾아서 'date' 필드에 넣어줘.

    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 포맷]
    [ {{ "title": "기사제목", "source": "언론사", "summary": "요약", "date": "날짜", "url": "링크" }} ]
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
            if 'candidates' not in res_json: 
                print("❌ AI 응답 오류 (Candidates 없음)")
                print(response.text)
                return []
            
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1: return []
            
            result = json.loads(text[start:end])
            print(f"\n[결과 3] AI 최종 선정: {len(result)}개")
            for i, item in enumerate(result):
                print(f"  {i+1}. {item.get('title')}")
            return result
        else:
            print(f"❌ API Error: {response.status_code}")
            print(response.text)
            return []
    except Exception as e:
        print(f"❌ Summarize Error: {e}")
        return []

# ==========================================
# 5. PDF 생성
# ==========================================
def create_pdf(articles, filename, is_empty=False):
    print("\n" + "="*60)
    print(f"[단계 4] PDF 생성: {filename}")
    pdf = FPDF()
    pdf.add_page()
    
    font_path = 'NanumGothic.ttf'
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security Briefing ({TODAY_STR})", ln=True, align='C')
    pdf.ln(10)

    if is_empty or not articles:
        pdf.set_font_size(12)
        pdf.multi_cell(0, 10, "No significant domestic security news found today.\n(주요 국내 보안 뉴스가 없습니다.)", align='C')
        pdf.output(filename)
        return

    for idx, article in enumerate(articles, 1):
        source_name = article.get('source', 'News')
        title_text = f"{idx}. {article['title']} ({source_name})"
        
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102)
        pdf.multi_cell(0, 8, title_text)
        
        pdf.set_font_size(9)
        pdf.set_text_color(100, 100, 100)
        date_str = article.get('date', '')
        pdf.cell(0, 5, f"Date: {date_str}", ln=True)
        
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
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
        pdf.cell(0, 5, "[Original Link]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        if os.path.exists(qr_filename):
            os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)
    print("  └ PDF 생성 완료")

# ==========================================
# 6. 이메일 발송
# ==========================================
def send_email(pdf_filename):
    print("\n" + "="*60)
    print("[단계 5] 이메일 발송")
    
    if not os.path.exists(pdf_filename): return
    if not RECIPIENTS: return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(RECIPIENTS)
    msg['Subject'] = Header(f"[{TODAY_STR}] 국내 주요 정보보호 뉴스 브리핑", 'utf-8')

    body = f"""
    안녕하세요.
    {TODAY_STR}일자 국내 주요 보안 뉴스 브리핑입니다.
    
    국내 주요 IT/보안 전문지의 최신 보안 뉴스만을 선별했습니다.
    
    감사합니다.
    """
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(pdf_filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
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
        
        # 3. 결과 처리
        if final_data:
            create_pdf(final_data, PDF_FILENAME, is_empty=False)
            send_email(PDF_FILENAME)
        else:
            print("\n[알림] 최종 선정된 뉴스가 없습니다. '뉴스 없음' PDF 생성.")
            create_pdf([], PDF_FILENAME, is_empty=True)
            # send_email(PDF_FILENAME)

    except Exception as e:
        print(f"\n🔥 Critical Error: {e}")
