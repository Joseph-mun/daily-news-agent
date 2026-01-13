import os
import smtplib
import requests
import json
import qrcode
from datetime import datetime, timedelta
from dateutil import parser
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.header import Header
from email import encoders
from fpdf import FPDF
from tavily import TavilyClient

# ==========================================
# 1. 환경변수 및 설정
# ==========================================
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
MAIN_RECIPIENT = os.environ.get("TO_EMAIL") or EMAIL_USER

# 수신자 리스트 구성
RECIPIENTS = []
if MAIN_RECIPIENT: 
    RECIPIENTS.append(MAIN_RECIPIENT)

ADDITIONAL_EMAIL = "joseph.moon@shinhan.com"
if ADDITIONAL_EMAIL not in RECIPIENTS: 
    RECIPIENTS.append(ADDITIONAL_EMAIL)

HISTORY_FILE = "history.json"

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
TODAY_COMPACT = NOW.strftime("%Y%m%d")
PDF_FILENAME = f"주요 뉴스 요약_{TODAY_COMPACT}.pdf"

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
        if item['url'] not in history: 
            new_results.append(item)
    return new_results, history

# ==========================================
# 3. 뉴스 검색 (광범위 수집)
# ==========================================
def search_news(query):
    # Python에서는 최대한 넓게 긁어오고, 판단은 AI에게 맡김
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안"
    
    print(f"'{optimized_query}' 검색 시작...")
    
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        response = tavily.search(
            query=optimized_query, 
            topic="news",
            search_depth="advanced", 
            max_results=40, 
            days=3 
        )
        
        raw_results = response.get('results', [])
        print(f"1차 API 검색결과: {len(raw_results)}개 확보.")
        
        final_candidates, history = filter_new_articles(raw_results)
        print(f"중복 제거 후 AI 검수 대상: {len(final_candidates)}개")

        # 히스토리 업데이트
        for item in final_candidates: history.append(item['url'])
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(history, f)

        return final_candidates

    except Exception as e:
        print(f"Search Error: {e}")
        return []

# ==========================================
# 4. AI 요약 (국내 언론사 한정 필터링 추가)
# ==========================================
def summarize_news(news_list):
    if not news_list: return []

    print(f"Gemini에게 {len(news_list)}건 요청 중 (국내 언론사 필터링)...")
    
    # 모델 URL 설정 (Gemini 2.5 요청 반영)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # [핵심] 프롬프트에 '국내 언론사 한정' 지침 강력 추가
    prompt = f"""
    너는 대한민국 최고의 'IT 보안 전문 뉴스 편집장'이다. 오늘 날짜: {TODAY_STR}
    
    제공된 뉴스 기사 목록을 엄격하게 심사하여 아래 기준에 맞는 기사만 선별해라.

    [필수 필터링 기준]
    1. **[국내 언론사 한정]**: 반드시 **'대한민국 국내 언론사'** (주요 일간지, 방송사, IT/보안 전문지 등)의 기사만 남겨라.
       - 해외 외신(영어 등 외국어 사이트), 번역기 돌린 듯한 사이트는 무조건 삭제해라.
       - 개인 블로그, 커뮤니티(뽐뿌, 클리앙 등), 위키 글도 삭제해라.
    2. **[주제 적합성]**: '정보보호, 해킹, 보안, 개인정보'와 직접 관련된 뉴스만 남겨라.
    3. **[노이즈 제거]**: 
       - 스포츠(야구, 축구 등) 관련 기사는 '보안' 단어가 있어도 무조건 삭제.
       - 연예인 사생활, 단순 업체 홍보/광고 보도자료는 삭제.

    [요약 및 출력 지침]
    - 살아남은 기사는 한국어로 3줄 이내 핵심 요약해라.
    - 결과는 오직 JSON 리스트 형식으로만 출력해라.

    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 포맷]
    [ {{ "title": "기사제목", "source": "언론사명", "summary": "요약내용", "date": "날짜", "url": "링크" }} ]
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
            print(f"✅ AI 필터링(국내뉴스) 완료: {len(result)}개 선정됨.")
            return result
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Summarize Error: {e}")
        return []

# ==========================================
# 5. PDF 생성
# ==========================================
def create_pdf(articles, filename, is_empty=False):
    print(f"PDF 생성 중 ({filename})...")
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    # 타이틀
    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security Briefing ({TODAY_STR})", ln=True, align='C')
    pdf.ln(10)

    # 기사가 없을 때 안내
    if is_empty or not articles:
        pdf.set_font_size(12)
        pdf.multi_cell(0, 10, "No significant domestic security news found today.\n(오늘 AI가 선정한 국내 주요 보안 뉴스가 없습니다.)", align='C')
        pdf.output(filename)
        return

    # 기사 출력
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
        pdf.cell(0, 5, "[Link]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        if os.path.exists(qr_filename):
            os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# ==========================================
# 6. 이메일 발송
# ==========================================
def send_email(pdf_filename):
    if not os.path.exists(pdf_filename): return
    if not RECIPIENTS: return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(RECIPIENTS)
    msg['Subject'] = Header(f"[{TODAY_STR}] 주요 정보보호 뉴스 브리핑 (국내)", 'utf-8')

    body = f"안녕하세요.\n{TODAY_STR}일자 국내 주요 보안 뉴스 브리핑입니다.\n\n첨부된 PDF 파일을 확인해주세요."
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(pdf_filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=Header(pdf_filename, 'utf-8').encode())
        msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        print(f"메일 발송 완료: {len(RECIPIENTS)}명")
    except Exception as e:
        print(f"Email Error: {e}")

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
            print("ℹ️ 결과 없음: '뉴스 없음' PDF 생성")
            create_pdf([], PDF_FILENAME, is_empty=True)
            # send_email(PDF_FILENAME)

    except Exception as e:
        print(f"Critical Error: {e}")
