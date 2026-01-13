import os
import smtplib
import requests
import json
import qrcode
from datetime import datetime, timedelta
from dateutil import parser # 날짜 해석용 라이브러리
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

HISTORY_FILE = "history.json"

TARGET_DOMAINS = [
    "yna.co.kr", "etnews.com", "zdnet.co.kr", "boannews.com", 
    "dailysecu.com", "datanet.co.kr", "ddaily.co.kr", 
    "hani.co.kr", "chosun.com", "donga.com", "joongang.co.kr", "mk.co.kr"
]

# 2. 날짜 검증 함수 (문지기 역할)
def is_recent_article(date_string, days_limit=2):
    if not date_string:
        return False # 날짜 없으면 탈락
    
    try:
        # 다양한 날짜 형식을 자동으로 해석
        pub_date = parser.parse(date_string)
        # 타임존 정보가 있다면 제거 (단순 비교를 위해)
        pub_date = pub_date.replace(tzinfo=None)
        
        # 현재 시간
        now = datetime.now()
        
        # 차이 계산
        diff = now - pub_date
        
        # 미래의 날짜(내일자 신문 등)거나, 제한 기간 이내인 경우 통과
        return diff.days <= days_limit and diff.days >= -1
        
    except Exception as e:
        # 날짜 해석 실패시 안전하게 제외
        return False

# 3. 중복 기사 필터링
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
    
    # 1차: URL 중복 검사
    for item in results:
        if item['url'] not in history:
            new_results.append(item)
            # (여기서는 아직 history에 추가하지 않음, 최종 선택된 것만 추가할 예정)
            
    return new_results, history

# 4. 뉴스 검색 (도메인 제한 + 날짜 2차 필터)
def search_news(query):
    print(f"'{query}' 검색 중 (최근 48시간 엄격 필터)...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    # 1차 API 요청 (넉넉하게 20개 요청)
    response = tavily.search(
        query=query, 
        search_depth="basic", 
        max_results=20, 
        include_domains=TARGET_DOMAINS,
        days=3 # API에는 조금 여유있게 요청 (API가 시차 때문에 놓칠 수 있으므로)
    )
    
    raw_results = response['results']
    
    # 2차 Python 날짜 필터링 (엄격하게 자르기)
    date_filtered_results = []
    print(f"1차 검색결과: {len(raw_results)}개. 날짜 검증 시작...")
    
    for item in raw_results:
        pub_date = item.get('published_date')
        if is_recent_article(pub_date, days_limit=2):
            date_filtered_results.append(item)
        else:
            print(f"  - 제외됨(오래된 기사): {item['title']} ({pub_date})")

    # 3차 중복 필터링
    final_candidates, history = filter_new_articles(date_filtered_results)
    
    # 결과가 10개를 넘으면 자르기
    final_selection = final_candidates[:10]
    
    print(f"날짜 필터 후: {len(date_filtered_results)}개 -> 중복 제거 후 최종: {len(final_selection)}개")

    # 최종 선택된 기사들만 히스토리에 기록
    for item in final_selection:
        history.append(item['url'])
        
    if len(history) > 500:
        history = history[-500:]
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection

# 5. AI 상세 요약
def summarize_news(news_list):
    if not news_list:
        return []

    print("Gemini에게 요약 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 보안 뉴스 큐레이터야. 제공된 뉴스 데이터(JSON)를 바탕으로 다음 작업을 수행해:
    
    1. 각 뉴스의 내용을 분석하여 3줄 이내로 핵심을 요약해.
    2. '제목(title)'과 '링크(url)'는 절대 변경하지 말고 원본 데이터 그대로 사용해.
    3. 결과는 반드시 JSON 리스트 형식으로만 출력해.
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "기사 제목", "summary": "요약 내용", "url": "http://..."}},
        ...
    ]
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        try:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            print(f"JSON 파싱 실패: {e}")
            return []
    else:
        print(f"API 에러: {response.text}")
        return []

# 6. PDF 생성
def create_pdf(articles, filename="briefing.pdf"):
    print("PDF 생성 중...")
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists('NanumGothic.ttf'):
        pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True)
        pdf.set_font('Nanum', '', 10)
    else:
        pdf.set_font("Arial", size=10)

    pdf.set_font_size(16)
    pdf.cell(0, 10, f"Daily Security News ({datetime.now().strftime('%Y-%m-%d')})", ln=True, align='C')
    pdf.set_font_size(10)
    pdf.cell(0, 10, "Selected from Major Tech & Security Media", ln=True, align='C')
    pdf.ln(10)

    for idx, article in enumerate(articles, 1):
        pdf.set_font_size(13)
        pdf.set_text_color(0, 51, 102)
        pdf.multi_cell(0, 8, f"{idx}. {article['title']}")
        
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.multi_cell(0, 6, article['summary'])
        pdf.ln(2)
        
        qr_filename = f"qr_{idx}.png"
        qr = qrcode.make(article['url'])
        qr.save(qr_filename)
        
        y_pos = pdf.get_y()
        if y_pos > 250: 
            pdf.add_page()
            y_pos = pdf.get_y()

        pdf.image(qr_filename, x=170, y=y_pos, w=20)
        
        pdf.set_text_color(0, 102, 204)
        pdf.cell(0, 5, "[Read Original Article]", ln=True, link=article['url'])
        pdf.set_text_color(0, 0, 0)
        
        pdf.ln(15)
        os.remove(qr_filename)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.output(filename)

# 7. 이메일 발송
def send_email(pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 정보보호 뉴스 브리핑"

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
        # 키워드 확장
        news_data = search_news("정보보호 해킹 보안사고 개인정보유출")
        
        if not news_data:
            print("조건에 맞는 새로운 뉴스가 없습니다.")
        else:
            analyzed_data = summarize_news(news_data)
            if analyzed_data:
                create_pdf(analyzed_data)
                send_email("briefing.pdf")
                print("발송 완료!")
            else:
                print("요약할 데이터가 없습니다.")
                
    except Exception as e:
        print(f"오류 발생: {e}")
