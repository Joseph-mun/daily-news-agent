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
MAIN_RECIPIENT = os.environ.get("TO_EMAIL") or EMAIL_USER

# 수신자 리스트 구성
RECIPIENTS = []
if MAIN_RECIPIENT:
    RECIPIENTS.append(MAIN_RECIPIENT)

# 추가 수신자
ADDITIONAL_EMAIL = "joseph.moon@shinhan.com"
if ADDITIONAL_EMAIL not in RECIPIENTS:
    RECIPIENTS.append(ADDITIONAL_EMAIL)

HISTORY_FILE = "history.json"

# 검증된 도메인 리스트 (이 리스트에 포함된 URL만 남김)
TARGET_DOMAINS = [
    "yna.co.kr", "etnews.com", "zdnet.co.kr", "boannews.com", 
    "dailysecu.com", "datanet.co.kr", "ddaily.co.kr", "digitaltoday.co.kr", 
    "inews24.com", "bloter.net", "itworld.co.kr", "ciokorea.com", 
    "hani.co.kr", "chosun.com", "donga.com", "joongang.co.kr", 
    "mk.co.kr", "hankyung.com", "mt.co.kr", "newsis.com", "news1.kr"
]

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

# 3. 뉴스 검색 (수정됨: API 제한을 풀고 파이썬 필터링 강화)
def search_news(query):
    # 스포츠/연예 제외 쿼리 유지
    optimized_query = "정보보호 OR 해킹사고 OR 개인정보유출 OR 사이버보안 -야구 -축구 -스포츠 -연예 -포토"
    
    print(f"'{optimized_query}' 광범위 검색 중...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    # [핵심 변경] include_domains 옵션을 제거하여 API가 넓게 검색하도록 함
    # max_results를 60개로 늘려 충분한 모수를 확보
    response = tavily.search(
        query=optimized_query, 
        topic="news",
        search_depth="advanced", 
        max_results=60, 
        days=2  
    )
    
    raw_results = response['results']
    print(f"1차 API 검색결과: {len(raw_results)}개 확보.")
    
    # [파이썬 필터링] 여기서 우리가 원하는 도메인인지 직접 검사
    candidates = []
    for item in raw_results:
        url = item.get('url', '')
        title = item.get('title', '')
        
        # 1. 도메인 검사 (TARGET_DOMAINS 중 하나라도 URL에 포함되어야 합격)
        domain_match = any(domain in url for domain in TARGET_DOMAINS)
        if not domain_match:
            continue # 리스트에 없는 사이트면 버림
            
        # 2. 제목 노이즈 검사 (스포츠 등)
        if any(bad in title for bad in ['야구', '축구', '경기', '스포츠', '배우', '드라마', '홈런', '타자', '투수']):
            continue
            
        candidates.append(item)

    print(f"도메인/키워드 필터 후 남은 기사: {len(candidates)}개")

    # 중복 제거
    final_candidates, history = filter_new_articles(candidates)
    
    # AI에게 보낼 기사 선정 (최대 15개)
    final_selection = final_candidates[:15]
    print(f"최종 AI 검수 요청 대상: {len(final_selection)}개")

    for item in final_selection:
        history.append(item['url'])
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection

# 4. AI 상세 요약
def summarize_news(news_list):
    if not news_list:
        return []

    print(f"Gemini에게 {len(news_list)}건 정밀 분석 요청...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 '보안 뉴스 편집장'이야. 오늘은 [ {TODAY_STR} ].
    
    데이터를 분석해 JSON으로 반환해:
    
    1. [날짜 검증]: 오늘({TODAY_STR}) 기준 '만 2일' 이내 기사만 남겨.
    2. [주제 필터링]: '정보보호', '해킹', '보안', '개인정보' 관련 기사만 남겨.
    3. [언론사 추출]: URL이나 내용을 보고 언론사명(예: 조선일보, 보안뉴스)을 파악해 'source'에 넣어.
    4. [요약]: 내용을 한국어 3줄로 요약해.
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{
            "title": "제목", 
            "source": "보안뉴스", 
            "summary": "요약", 
            "date": "YYYY-MM-DD", 
            "url": "링크"
        }}
    ]
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

# 5. PDF 생성
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
        # 제목 + (언론사명)
        source_name = article.get('source', 'News')
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
        pdf.cell(0, 5, "[Link]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 6. 이메일 발송
def send_email(pdf_filename):
    if not os.path.exists(pdf_filename):
        return

    if not RECIPIENTS:
        print("수신자 없음")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
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
    server.send_message(msg)
    server.quit()
    print(f"메일 발송 완료: {len(RECIPIENTS)}명")

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
