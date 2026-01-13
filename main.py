import os
import smtplib
import requests
import json
import qrcode
import re
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

# [검색 대상 도메인] - 화이트리스트
TARGET_DOMAINS = [
    "news.naver.com", "boannews.com", "dailysecu.com", "etnews.com", 
    "zdnet.co.kr", "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", 
    "bloter.net", "itworld.co.kr", "byline.network", "ciokorea.com",
    "yna.co.kr", "news1.kr", "newsis.com"
]

# ==========================================
# 2. 유틸리티 함수 (도메인 검증)
# ==========================================
def is_valid_domain(url):
    """
    URL이 우리가 지정한 TARGET_DOMAINS 중 하나에 속하는지 확인.
    포함되지 않으면 False를 반환하여 가차없이 삭제.
    """
    if not url: return False
    url_lower = url.lower()
    for domain in TARGET_DOMAINS:
        if domain in url_lower:
            return True
    return False

def filter_new_articles(results):
    print("\n[단계 2] 기사 필터링 (도메인 검증 및 중복 확인)...")
    
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []
    else: history = []

    new_results = []
    domain_dropped = 0
    history_dropped = 0
    
    for item in results:
        url = item.get('url', '')
        
        # 1. 도메인 화이트리스트 체크
        if not is_valid_domain(url):
            domain_dropped += 1
            continue
            
        # 2. 히스토리 중복 필터링
        if url not in history: 
            new_results.append(item)
        else:
            history_dropped += 1

    print(f"  └ 지정된 도메인 외 제외: {domain_dropped}개")
    print(f"  └ 중복(히스토리) 제외: {history_dropped}개")
    print(f"  └ 최종 검수 대상: {len(new_results)}개")
    
    return new_results, history

# ==========================================
# 3. 뉴스 검색 (공백 구분 쿼리 사용)
# ==========================================
def search_news(query):
    # 가장 결과가 좋았던 공백 구분 쿼리
    optimized_query = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어"
    
    print("="*60)
    print(f"[단계 1] Tavily 검색 시작: '{optimized_query}'")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        
        response = tavily.search(
            query=optimized_query, 
            topic="news",
            search_depth="advanced",
            include_domains=TARGET_DOMAINS, 
            max_results=50
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
# 4. AI 요약 (키워드 추출 추가)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print("\n" + "="*60)
    print(f"[단계 3] AI(Gemini 2.5)에게 {len(news_list)}건 분석 요청")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 깐깐한 '보안 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    [작업 지시]
    1. 뉴스 목록에서 '정보보호, 해킹, 보안, 개인정보' 관련 핵심 기사를 선정해라.
    2. 오늘({TODAY_STR}) 기준으로 '2일 이내'의 기사만 남겨라. (오래된 기사 삭제)
    3. 남은 기사는 한국어로 3줄 요약해라.
    4. **[추가]** 각 기사의 핵심 키워드 3개를 뽑아서 'keywords' 리스트에 담아라.
    5. **중요:** 결과는 반드시 순수한 JSON 리스트 포맷(`[...]`)으로만 출력해라.

    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [ {{ 
        "title": "제목", 
        "source": "언론사명", 
        "summary": "요약내용", 
        "date": "YYYY-MM-DD", 
        "keywords": ["키워드1", "키워드2", "키워드3"],
        "url": "링크" 
    }} ]
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
            
            raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            
            # JSON 파싱 (Regex)
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                result = json.loads(match.group())
                print(f"\n[결과 3] AI 최종 선정: {len(result)}개")
                for i, item in enumerate(result):
                    print(f"  {i+1}. {item.get('title')} ({item.get('keywords')})")
                return result
            else:
                print("❌ JSON 파싱 실패")
                return []
        else:
            print(f"❌ API Error: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Summarize Error: {e}")
        return []

# ==========================================
# 5. PDF 생성 (해시태그 및 디자인 적용)
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

    # 헤더
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
        
        # 1. 제목 (진한 남색)
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102) 
        pdf.multi_cell(0, 8, title_text)
        
        # 2. 날짜 (회색)
        pdf.set_font_size(9)
        pdf.set_text_color(100, 100, 100)
        date_str = article.get('date', TODAY_STR)
        pdf.cell(0, 5, f"Date: {date_str}", ln=True)

        # 3. 해시태그 (파란색 강조)
        keywords = article.get('keywords', [])
        if keywords:
            hashtag_str = " ".join([f"#{k}" for k in keywords])
            pdf.set_text_color(0, 102, 204) # 밝은 파랑
            pdf.cell(0, 5, hashtag_str, ln=True)
        
        # 4. 요약 (검정)
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        # 5. QR 코드
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        y_pos = pdf.get_y()
        if y_pos > 240: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        # 6. 링크 (클릭 가능)
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[Original Link]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        if os.path.exists(qr_filename):
            os.remove(qr_filename)
        
        # 구분선
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
    첨부된 PDF 파일에서 상세 내용을 확인하실 수 있습니다.
    
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
        news_data = search_news("") 
        
        final_data = []
        if news_data:
            final_data = summarize_news(news_data)
        
        if final_data:
            create_pdf(final_data, PDF_FILENAME, is_empty=False)
            send_email(PDF_FILENAME)
        else:
            print("\n[알림] 최종 선정된 뉴스가 없습니다. '뉴스 없음' PDF 생성.")
            create_pdf([], PDF_FILENAME, is_empty=True)
            # send_email(PDF_FILENAME)

    except Exception as e:
        print(f"\n🔥 Critical Error: {e}")
