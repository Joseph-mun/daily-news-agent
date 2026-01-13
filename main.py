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

# 2. 날짜 검증 함수 (수정됨: 날짜가 없으면 API를 믿고 통과)
def is_recent_article(date_string, days_limit=2):
    # 날짜 정보가 아예 없는 경우 -> API의 days 필터를 믿고 통과시킴 (수정된 부분)
    if not date_string:
        return True 
    
    try:
        pub_date = parser.parse(date_string)
        pub_date = pub_date.replace(tzinfo=None)
        now = datetime.now()
        diff = now - pub_date
        
        # 미래의 날짜거나, 제한 기간 이내인 경우 통과
        return diff.days <= days_limit and diff.days >= -1
        
    except Exception as e:
        # 날짜 형식이 특이해서 해석 실패한 경우 -> 안전하게 통과시킴
        return True

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
    for item in results:
        if item['url'] not in history:
            new_results.append(item)
            
    return new_results, history

# 4. 뉴스 검색 (수정됨: topic="news" 추가)
def search_news(query):
    print(f"'{query}' 검색 중 (최근 48시간 뉴스 모드)...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    # ★ topic="news" 추가: 뉴스 전용 데이터를 요청하여 날짜 정확도 향상
    response = tavily.search(
        query=query, 
        topic="news",  # <--- [핵심] 뉴스 모드로 설정
        search_depth="basic", 
        max_results=20, 
        include_domains=TARGET_DOMAINS,
        days=2
    )
    
    raw_results = response['results']
    
    date_filtered_results = []
    print(f"1차 검색결과: {len(raw_results)}개. 검증 시작...")
    
    for item in raw_results:
        pub_date = item.get('published_date')
        if is_recent_article(pub_date, days_limit=2):
            date_filtered_results.append(item)
        else:
            # 날짜가 명확히 있고, 그게 오래된 경우에만 제외
            print(f"  - 제외됨(오래된 기사): {item['title']} ({pub_date})")

    final_candidates, history = filter_new_articles(date_filtered_results)
    final_selection = final_candidates[:10]
    
    print(f"필터링 후 남은 기사: {len(final_selection)}개")

    for item in final_selection:
        history.append(item['url'])
        
    if len(history) > 500:
        history = history[-500:]
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection


# 5. AI 상세 요약 (보안 관련성 검증 및 번역 기능 추가)
def summarize_news(news_list):
    if not news_list:
        return []

    print("Gemini에게 요약 및 검수(야구 기사 제외) 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # 프롬프트 대폭 강화: '엄격한 필터링'과 '번역' 지시 추가
    prompt = f"""
    너는 까다로운 '보안 뉴스 전문 편집장'이야. 
    제공된 뉴스 데이터(JSON)를 검토해서 다음 규칙을 엄격하게 적용해:

    1. [필터링]: 기사 내용이 '정보보호', '해킹', '개인정보 유출', '사이버 보안', 'IT 정책'과 직접적인 관련이 없다면 과감히 버려. 
       (특히 야구, 축구, 스포츠, 연예, 단순 사건사고는 절대 포함하지 마.)
    
    2. [번역]: 기사 제목이나 내용이 영어라면, 반드시 자연스러운 '한국어'로 번역해.
    
    3. [요약]: 살아남은 보안 기사들에 대해서만 핵심 내용을 3줄로 요약해.
    
    4. [형식]: '제목(title)', '요약(summary)', '링크(url)' 키를 가진 JSON 리스트로 반환해. 링크는 원본 그대로 유지해.
    
    [검토할 뉴스 목록]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "한국어 제목", "summary": "한국어 요약 내용...", "url": "http://original-link.com"}},
        ...
    ]
    만약 보안 관련 기사가 하나도 없다면 빈 리스트 [] 를 반환해.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        try:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            
            # 필터링 결과 로그 출력
            print(f"AI 검수 완료: {len(news_list)}개 중 {len(result)}개(보안 관련)만 통과.")
            return result
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
    msg['Subject'] = f"[{datetime.now().strftime('%Y-%m-%d')}] 주요 정보보호 뉴스 브리핑"

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
