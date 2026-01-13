import os
import smtplib
import requests
import json
import qrcode
import re  # [추가] 정규표현식 사용을 위해 추가
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
    "news.naver.com", "boannews.com", "dailysecu.com", "etnews.com", "zdnet.co.kr", 
    "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", "bloter.net", 
    "itworld.co.kr", "byline.network", "ciokorea.com"
]

# ==========================================
# 2. 유틸리티 함수
# ==========================================
def is_korean_article(url):
    url_lower = url.lower()
    exclude_patterns = ["/en/", "/english/", "/world-en/", "/sports-en/", "cnn.com", "bbc.com", "reuters.com"]
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
        if not is_korean_article(url):
            english_dropped += 1
            continue
        if url not in history: 
            new_results.append(item)
        else:
            history_dropped += 1

    print(f"  └ 영문/해외 기사 제외: {english_dropped}개")
    print(f"  └ 중복(히스토리) 제외: {history_dropped}개")
    print(f"  └ 최종 검수 대상: {len(new_results)}개")
    return new_results, history

# ==========================================
# 3. 뉴스 검색
# ==========================================
def search_news(query):
    optimized_query = "정보보호 OR 해킹 OR 개인정보유출 OR 사이버보안 OR 랜섬웨어"
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
        
        for item in final_candidates: 
            history.append(item['url'])
        
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: 
            json.dump(history, f)

        return final_candidates

    except Exception as e:
        print(f"❌ Search Error: {e}")
        return []

# ==========================================
# 4. AI 요약 (디버깅 강화 및 파싱 개선)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print("\n" + "="*60)
    print(f"[단계 3] AI(Gemini 2.5)에게 {len(news_list)}건 검수 요청")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 깐깐한 '보안 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    [작업 지시]
    1. 다음 뉴스 목록에서 '정보보호, 해킹, 보안, 개인정보'와 직접 관련된 기사만 남겨라.
    2. 스포츠, 연예, 주식 시황 기사는 무조건 삭제해라.
    3. 남은 기사는 한국어로 3줄 요약해라.
    4. **중요:** 결과는 반드시 순수한 JSON 리스트 포맷(`[...]`)으로만 출력해라. 
       - 마크다운 코드블록(```json)이나 다른 설명 텍스트를 절대 붙이지 마라.
       - 만약 적합한 기사가 하나도 없다면 빈 리스트 `[]`를 반환해라.

    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [ {{ "title": "제목", "source": "언론사", "summary": "요약", "date": "날짜", "url": "링크" }} ]
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
                print(f"응답 전문: {response.text}")
                return []
            
            raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # [디버깅] AI가 뱉은 텍스트가 뭔지 확인 (앞부분 200자만 출력)
            # print(f"🔍 AI Raw Response: {raw_text[:200]} ...")
            
            # 1. 마크다운 제거
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            
            # 2. JSON 파싱 (Regex로 리스트 부분만 추출 시도)
            # '['로 시작해서 ']'로 끝나는 구간을 찾음
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            
            if match:
                json_str = match.group()
                try:
                    result = json.loads(json_str)
                    print(f"\n[결과 3] AI 최종 선정: {len(result)}개")
                    for i, item in enumerate(result):
                        print(f"  {i+1}. {item.get('title')}")
                    return result
                except json.JSONDecodeError as je:
                    print(f"❌ JSON 파싱 실패: {je}")
                    print(f"❌ AI 원본 텍스트:\n{clean_text}")
                    return []
            else:
                print("❌ JSON 리스트 형식을 찾을 수 없습니다.")
                print(f"❌ AI 원본 텍스트:\n{raw_text}")
                return []
                
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
