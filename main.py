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

TARGET_DOMAINS = [
    "boannews.com", "dailysecu.com", "etnews.com", "zdnet.co.kr", 
    "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", "bloter.net", 
    "itworld.co.kr", "ciokorea.com", "byline.network",
    "yna.co.kr", "news1.kr", "newsis.com",
    "mk.co.kr", "hankyung.com", "mt.co.kr", "fnnews.com", "sedaily.com",
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "khan.co.kr"
]

# ==========================================
# 2. 유틸리티 함수 (로그 추가됨)
# ==========================================
def filter_new_articles(results):
    print("\n[단계 2] 중복(히스토리) 필터링 진행 중...")
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []
    else: history = []

    new_results = []
    dropped_count = 0
    
    for item in results:
        if item.get('url') and item['url'] not in history: 
            new_results.append(item)
        else:
            dropped_count += 1
            # (디버그) 중복된 기사 제목 출력
            # print(f"  - 중복 제외: {item.get('title')}")

    print(f"  └ 기존 히스토리 개수: {len(history)}개")
    print(f"  └ 이번에 중복으로 제외된 기사: {dropped_count}개")
    print(f"  └ 최종 살아남은 신규 기사: {len(new_results)}개")
    
    return new_results, history

# ==========================================
# 3. 뉴스 검색 (로그 추가됨)
# ==========================================
def search_news(query):
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안 OR 랜섬웨어"
    
    print("="*60)
    print(f"[단계 1] Tavily 검색 시작: '{optimized_query}'")
    print(f"  └ 대상 도메인: {len(TARGET_DOMAINS)}개 언론사")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        
        response = tavily.search(
            query=optimized_query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS, 
            max_results=50, 
            days=3 
        )
        
        raw_results = response.get('results', [])
        print(f"\n[결과 1] Tavily가 찾아낸 원본 기사: {len(raw_results)}개")
        for i, item in enumerate(raw_results):
            print(f"  {i+1}. {item.get('title')} ({item.get('url')})")
        
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
# 4. AI 요약 (로그 추가됨)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print("\n" + "="*60)
    print(f"[단계 3] AI(Gemini)에게 {len(news_list)}건 검수 및 요약 요청")
    
    # 모델명: 404 에러 방지를 위해 latest 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 대한민국 최고의 'IT 보안 전문 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    [작업 지시]
    다음 뉴스 목록을 엄격히 심사하여 '정보보호, 해킹, 보안'과 직접 관련된 뉴스만 남겨라.
    스포츠, 연예, 단순 주식 시황은 삭제해라.
    남은 기사는 한국어로 3줄 요약해라.
    결과는 오직 JSON 리스트 포맷으로만 출력해라.

    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [ {{ "title": "...", "source": "...", "summary": "...", "date": "...", "url": "..." }} ]
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
                print("❌ AI 응답에 'candidates' 필드가 없습니다. (차단되었거나 오류)")
                print("응답 전문:", response.text)
                return []
            
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # JSON 파싱 시도
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1: 
                print("❌ AI 응답에서 JSON 리스트를 찾을 수 없습니다.")
                print("AI 응답 내용:", text)
                return []
            
            result = json.loads(text[start:end])
            print(f"\n[결과 3] AI 최종 선정 기사: {len(result)}개")
            for i, item in enumerate(result):
                print(f"  {i+1}. [선정] {item.get('title')}")
            
            return result
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"메시지: {response.text}")
            return []
    except Exception as e:
        print(f"❌ Summarize Error: {e}")
        return []

# ==========================================
# 5. PDF 생성
# ==========================================
def create_pdf(articles, filename, is_empty=False):
    print("\n" + "="*60)
    print(f"[단계 4] PDF 생성 시작: {filename}")
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
        print("  └ 내용: 뉴스 없음 (No news found)")
        pdf.set_font_size(12)
        pdf.multi_cell(0, 10, "No significant domestic security news found today.\n(주요 국내 보안 뉴스가 없습니다.)", align='C')
        pdf.output(filename)
        return

    print(f"  └ 내용: {len(articles)}개 기사 수록 중...")
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
    print("  └ PDF 생성 완료.")

# ==========================================
# 6. 이메일 발송
# ==========================================
def send_email(pdf_filename):
    print("\n" + "="*60)
    print("[단계 5] 이메일 발송 시도")
    
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
        print(f"✅ 메일 발송 완료: {len(RECIPIENTS)}명에게 전송됨.")
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
        else:
            print("\n[알림] 1차 검색 결과가 0건입니다.")
        
        # 3. 결과 처리
        if final_data:
            create_pdf(final_data, PDF_FILENAME, is_empty=False)
            send_email(PDF_FILENAME)
        else:
            print("\n[알림] 최종 선정된 뉴스가 없습니다. '뉴스 없음' PDF를 생성합니다.")
            create_pdf([], PDF_FILENAME, is_empty=True)
            # send_email(PDF_FILENAME)

    except Exception as e:
        print(f"\n🔥 Critical Error: {e}")
