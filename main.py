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
# 1. 환경변수 및 기본 설정
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
TODAY_STR = NOW.strftime("%Y-%m-%d")     # 예: 2026-01-14
TODAY_COMPACT = NOW.strftime("%Y%m%d")
PDF_FILENAME = os.path.join(OUTPUT_DIR, f"주요 뉴스 요약_{TODAY_COMPACT}.pdf")

# ==========================================
# 2. 도메인 리스트 분리 (국내/해외)
# ==========================================
# [국내] IT/보안 전문지 + 주요 뉴스
DOMAINS_KR = [
    "news.naver.com", "boannews.com", "dailysecu.com", "etnews.com", 
    "zdnet.co.kr", "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", 
    "bloter.net", "itworld.co.kr", "byline.network", "ciokorea.com",
    "yna.co.kr", "news1.kr", "newsis.com"
]

# [해외] 글로벌 Top 보안 미디어
DOMAINS_EN = [
    "thehackernews.com",       # 더 해커 뉴스
    "bleepingcomputer.com",    # 블리핑 컴퓨터
    "darkreading.com",         # 다크 리딩
    "infosecurity-magazine.com",
    "scmagazine.com",
    "cyberscoop.com",
    "securityweek.com",
    "wired.com",
    "techcrunch.com"
]

# ==========================================
# 3. 유틸리티 함수
# ==========================================
def is_valid_domain(url, domain_type="ALL"):
    """URL이 지정된 도메인 리스트에 속하는지 검사"""
    if not url: return False
    url_lower = url.lower()
    
    target_list = []
    if domain_type == "KR": target_list = DOMAINS_KR
    elif domain_type == "EN": target_list = DOMAINS_EN
    else: target_list = DOMAINS_KR + DOMAINS_EN
    
    for domain in target_list:
        if domain in url_lower:
            return True
    return False

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return []
    return []

def save_history(new_urls):
    history = load_history()
    # 최근 1000개까지만 유지 (용량 관리)
    updated_history = (history + new_urls)[-1000:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_history, f)

# ==========================================
# 4. 이원화된 검색 로직 (국내/해외 분리 수집)
# ==========================================
def search_news():
    print("="*60)
    print(f"[단계 1] 뉴스 수집 시작 (현재 시각: {TODAY_STR})")
    
    tavily = TavilyClient(api_key=TAVILY_KEY)
    history = load_history()
    collected_articles = []

    # --- [Track 1] 국내 뉴스 검색 ---
    try:
        query_kr = "정보보호 해킹 개인정보유출 사이버보안 랜섬웨어"
        print(f"  🔍 [국내] 검색 중... ({query_kr})")
        
        res_kr = tavily.search(
            query=query_kr, topic="news", search_depth="advanced",
            include_domains=DOMAINS_KR, max_results=30
        )
        
        count_kr = 0
        for item in res_kr.get('results', []):
            if item['url'] not in history and is_valid_domain(item['url'], "KR"):
                # 식별자 추가
                item['category'] = "[국내]"
                collected_articles.append(item)
                count_kr += 1
        print(f"     └ 국내 기사 확보: {count_kr}건")

    except Exception as e:
        print(f"❌ 국내 검색 실패: {e}")

    # --- [Track 2] 해외 뉴스 검색 ---
    try:
        query_en = "Cyber Security Hacking Data Breach Ransomware Vulnerability"
        print(f"  🔍 [해외] 검색 중... ({query_en})")
        
        res_en = tavily.search(
            query=query_en, topic="news", search_depth="advanced",
            include_domains=DOMAINS_EN, max_results=20
        )
        
        count_en = 0
        for item in res_en.get('results', []):
            if item['url'] not in history and is_valid_domain(item['url'], "EN"):
                # 식별자 추가
                item['category'] = "[해외]"
                collected_articles.append(item)
                count_en += 1
        print(f"     └ 해외 기사 확보: {count_en}건")

    except Exception as e:
        print(f"❌ 해외 검색 실패: {e}")

    print(f"  👉 총 수집된 후보군: {len(collected_articles)}개")
    return collected_articles

# ==========================================
# 5. AI 요약 및 선정 (강력한 날짜 필터링)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print("\n" + "="*60)
    print(f"[단계 2] AI(Gemini 2.5)에게 검수 및 요약 요청")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [핵심] 2026년 강제 및 비율 할당 프롬프트
    prompt = f"""
    너는 대한민국 최고의 '보안 뉴스 브리핑 편집장'이다.
    오늘은 **{TODAY_STR}** 이다.
    
    [입력된 기사 목록]
    {json.dumps(news_list)}

    [절대 원칙 - 날짜 검증]
    1. **반드시 2026년 1월에 발생한 사건만 남겨라.**
    2. 과거의 사건(예: 2021년 쿠팡, 2022년 몽클레르, 2023년 사건 등)이 검색되었더라도 **가차 없이 삭제**해라.
    3. 날짜가 불분명하면 삭제해라.

    [작업 지시]
    1. 위 날짜 검증을 통과한 기사 중에서 다음 비율로 선별해라.
       - **[국내] 기사: 상위 10개** (중요도 순)
       - **[해외] 기사: 상위 5개** (중요도 순)
       - 만약 적합한 기사가 부족하면 있는 만큼만 출력해라.
    2. 해외 기사의 제목과 요약은 **반드시 자연스러운 한국어**로 번역해라.
    3. 각 기사의 핵심 키워드 3개를 추출해라.
    
    [출력 포맷]
    반드시 아래 JSON 포맷으로만 출력해라 (코드블록 금지).
    [
      {{
        "category": "[국내] 또는 [해외]",
        "title": "기사 제목 (해외는 한국어 번역)",
        "source": "언론사명",
        "summary": "3줄 핵심 요약 (한국어)",
        "date": "YYYY-MM-DD",
        "keywords": ["키워드1", "키워드2", "키워드3"],
        "url": "원본 링크"
      }}
    ]
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
            
            # JSON 파싱
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                result = json.loads(match.group())
                
                # 히스토리 저장
                new_urls = [item['url'] for item in result]
                save_history(new_urls)
                
                print(f"\n[결과] AI 최종 선정: {len(result)}개")
                for i, item in enumerate(result, 1):
                    print(f"  {i}. {item.get('category')} {item.get('title')}")
                return result
            else:
                print("❌ JSON 파싱 실패 (AI 응답 오류)")
                print(clean_text[:500])
                return []
        else:
            print(f"❌ API Error: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Summarize Error: {e}")
        return []

# ==========================================
# 6. PDF 생성 ([국내]/[해외] 반영)
# ==========================================
def create_pdf(articles, filename):
    print("\n" + "="*60)
    print(f"[단계 3] PDF 생성: {filename}")
    pdf = FPDF()
    pdf.add_page()
    
    font_path = 'NanumGothic.ttf'
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    # 타이틀
    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security Briefing ({TODAY_STR})", ln=True, align='C')
    pdf.ln(10)

    if not articles:
        pdf.set_font_size(12)
        pdf.multi_cell(0, 10, "No significant security news found today.\n(주요 보안 뉴스가 없습니다.)", align='C')
        pdf.output(filename)
        return

    for idx, article in enumerate(articles, 1):
        category = article.get('category', '[일반]')
        source_name = article.get('source', 'News')
        # 제목 예: [국내] 교원그룹 랜섬웨어... (보안뉴스)
        title_text = f"{idx}. {category} {article['title']} ({source_name})"
        
        # 1. 제목 (카테고리별 색상 구분 가능하나 여기선 통일)
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102) 
        pdf.multi_cell(0, 8, title_text)
        
        # 2. 날짜
        pdf.set_font_size(9)
        pdf.set_text_color(100, 100, 100)
        date_str = article.get('date', TODAY_STR)
        pdf.cell(0, 5, f"Date: {date_str}", ln=True)

        # 3. 해시태그 (파란색)
        keywords = article.get('keywords', [])
        if keywords:
            hashtag_str = " ".join([f"#{k}" for k in keywords])
            pdf.set_text_color(0, 102, 204)
            pdf.cell(0, 5, hashtag_str, ln=True)
        
        # 4. 요약
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
        
        # 6. 링크
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
# 7. 이메일 발송
# ==========================================
def send_email(pdf_filename):
    print("\n" + "="*60)
    print("[단계 4] 이메일 발송")
    
    if not os.path.exists(pdf_filename): return
    if not RECIPIENTS: return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(RECIPIENTS)
    msg['Subject'] = Header(f"[{TODAY_STR}] 국내/해외 주요 보안 뉴스 브리핑", 'utf-8')

    body = f"""
    안녕하세요.
    {TODAY_STR}일자 보안 뉴스 브리핑입니다.
    
    [구성]
    - 국내 주요 보안 뉴스 (최대 10건)
    - 해외 핵심 보안 뉴스 (최대 5건)
    
    AI가 2026년 최신 기사 위주로 선별하였으며,
    상세 내용은 첨부된 PDF를 확인해 주시기 바랍니다.
    
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
# 8. 메인 실행
# ==========================================
if __name__ == "__main__":
    try:
        news_data = search_news()
        
        if news_data:
            final_data = summarize_news(news_data)
            if final_data:
                create_pdf(final_data, PDF_FILENAME)
                send_email(PDF_FILENAME)
            else:
                print("⚠️ 선별된 기사가 없습니다 (AI 필터링 결과 0건).")
        else:
            print("⚠️ 검색된 기사가 없습니다.")

    except Exception as e:
        print(f"\n🔥 Critical Error: {e}")
