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

# 1. 환경변수
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
# 기본 수신자 (GitHub Secrets)
MAIN_RECIPIENT = os.environ.get("TO_EMAIL") or EMAIL_USER

# [요구사항 2] 추가 수신자 리스트
# (환경변수 TO_EMAIL이 있다면 그것과 합쳐서 리스트로 관리)
RECIPIENTS = []
if MAIN_RECIPIENT:
    RECIPIENTS.append(MAIN_RECIPIENT)

# 추가 요청된 수신자 (중복 방지)
ADDITIONAL_EMAIL = "joseph.moon@shinhan.com"
if ADDITIONAL_EMAIL not in RECIPIENTS:
    RECIPIENTS.append(ADDITIONAL_EMAIL)

HISTORY_FILE = "history.json"

# [요구사항 1] 요청하신 도메인 리스트 적용
TARGET_DOMAINS = [
    "yna.co.kr",        # 연합뉴스
    "etnews.com",       # 전자신문
    "zdnet.co.kr",      # 지디넷코리아
    "boannews.com",     # 보안뉴스
    "dailysecu.com",    # 데일리시큐
    "datanet.co.kr",    # 데이터넷
    "ddaily.co.kr",     # 디지털데일리
    "digitaltoday.co.kr", # 디지털투데이
    "inews24.com",      # 아이뉴스24
    "bloter.net",       # 블로터
    "itworld.co.kr",    # ITWorld
    "ciokorea.com",     # CIO Korea
    "hani.co.kr",       # 한겨레
    "chosun.com",       # 조선일보
    "donga.com",        # 동아일보
    "joongang.co.kr",   # 중앙일보
    "mk.co.kr",         # 매일경제
    "hankyung.com",     # 한국경제
    "mt.co.kr",         # 머니투데이
    "newsis.com",       # 뉴시스
    "news1.kr"          # 뉴스1
]

# 날짜 포맷팅
NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
TODAY_COMPACT = NOW.strftime("%Y%m%d")
PDF_FILENAME = f"주요 뉴스 요약_{TODAY_COMPACT}.pdf"

# 2. 중복 기사 필터링
def filter_new_articles(results):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except:
                history = []
    else:
        history = []

    new_results = []
    for item in results:
        if item['url'] not in history:
            new_results.append(item)
    return new_results, history

# 3. 뉴스 검색
def search_news(query):
    # 스포츠/연예 기사 유입 방지를 위한 강력한 필터 유지
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안 -야구 -축구 -스포츠 -연예 -포토 -드라마"
    
    print(f"'{optimized_query}' 검색 중...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    response = tavily.search(
        query=optimized_query, 
        topic="news",
        search_depth="advanced", 
        max_results=40, # 도메인이 늘어났으므로 검색량 증대
        include_domains=TARGET_DOMAINS,
        days=2  
    )
    
    raw_results = response['results']
    print(f"1차 검색결과: {len(raw_results)}개.")
    
    # 제목 기반 노이즈 1차 제거
    candidates = []
    for item in raw_results:
        title = item.get('title', '')
        # 스포츠 관련 단어가 제목에 있으면 제외
        if any(bad in title for bad in ['야구', '축구', '경기', '스포츠', '배우', '드라마', '홈런', '타자', '투수']):
            continue
        candidates.append(item)

    final_candidates, history = filter_new_articles(candidates)
    final_selection = final_candidates[:15]
    print(f"AI에게 검수 요청할 기사: {len(final_selection)}개")

    for item in final_selection:
        history.append(item['url'])
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection

# 4. AI 상세 요약 (언론사명 추출 추가)
def summarize_news(news_list):
    if not news_list:
        return []

    print(f"Gemini에게 {len(news_list)}건 정밀 분석 요청...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 깐깐한 '보안 뉴스 편집장'이야. 
    오늘은 [ {TODAY_STR} ] 이야.
    
    데이터를 분석해서 다음 작업을 수행해:
    
    1. [날짜 검증]: 오늘({TODAY_STR}) 기준 '만 2일(48시간)' 이내 최신 기사만 남겨. (오래된 것 삭제)
    2. [주제 필터링]: '정보보호', '해킹', '보안', '개인정보' 관련 기사만 남겨.
    3. [언론사 추출]: 기사 내용이나 URL을 보고 언론사 이름(예: 조선일보, 보안뉴스, ZDNet)을 파악해.
    4. [요약]: 핵심 내용을 한국어로 3줄 요약해.
    
    [출력 형식 (JSON)]
    [
        {{
            "title": "기사 제목", 
            "source": "언론사명", 
            "summary": "요약 내용", 
            "date": "YYYY-MM-DD", 
            "url": "원문링크"
        }}
    ]
    
    [입력 데이터]
    {json.dumps(news_list)}
    """
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": safety_settings
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json or not res_json['candidates']:
                return []
            
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1: return []
            
            result = json.loads(text[start:end])
            print(f"✅ AI 검수 완료: {len(result)}개")
            return result
        else:
            print(f"API Error: {response.text}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

# 5. PDF 생성 (제목 옆에 언론사명 추가)
def create_pdf(articles, filename):
    if not articles:
        return

    print(f"PDF 생성 중 ({filename})...")
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security Briefing ({TODAY_STR})", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        # [요구사항 3] 제목 + (언론사명)
        source_name = article.get('source', 'Unknown')
        title_text = f"{idx}. {article['title']} ({source_name})"
        
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
        
        # QR
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        y_pos = pdf.get_y()
        if y_pos > 240: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[Link Click or QR code]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 6. 이메일 발송 (다중 수신자 처리)
def send_email(pdf_filename):
    if not os.path.exists(pdf_filename):
        return

    # 수신자가 없으면 중단
    if not RECIPIENTS:
        print("수신자(TO_EMAIL)가 설정되지 않았습니다.")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    # 여러 수신자를 콤마로 연결해 표기
    msg['To'] = ", ".join(RECIPIENTS)
    
    subject_text = f"[{TODAY_STR}] 주요 정보보호 뉴스 브리핑"
    msg['Subject'] = Header(subject_text, 'utf-8')

    body = f"""
    안녕하세요.
    {TODAY_STR}일자 주요 보안 뉴스 브리핑입니다.
    
    첨부된 PDF 파일({pdf_filename})을 확인해주세요.
    감사합니다.
    """
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(pdf_filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=Header(pdf_filename, 'utf-8').encode())
        msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    
    # [중요] 실제 발송은 리스트에 있는 모든 사람에게 수행
    server.send_message(msg) 
    server.quit()
    print(f"메일 발송 완료: {', '.join(RECIPIENTS)}")

if __name__ == "__main__":
    try:
        news_data = search_news("") 
        if news_data:
            analyzed_data = summarize_news(news_data)
            if analyzed_data:
                create_pdf(analyzed_data, PDF_FILENAME)
                send_email(PDF_FILENAME)
            else:
                print("결과 없음: AI 필터링 0건")
        else:
            print("검색 결과 없음")
                
    except Exception as e:
        print(f"오류 발생: {e}")
