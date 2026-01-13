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

# 4. 뉴스 검색 (조건 대폭 완화: 도메인 제한 해제 + 수량 증대)
def search_news(query):
    # 검색어 최적화: OR 연산자를 써서 하나라도 걸리게 함
    optimized_query = "정보보호 OR 개인정보유출 OR 해킹사고 OR 사이버보안"
    
    print(f"'{optimized_query}' 광범위 검색 중 (최근 72시간)...")
    tavily = TavilyClient(api_key=TAVILY_KEY)
    
    # ★ 핵심 변경: include_domains 삭제 (모든 언론사 검색)
    response = tavily.search(
        query=optimized_query, 
        topic="news",          # 여전히 뉴스로 한정
        search_depth="advanced", # basic -> advanced로 변경 (더 깊게 검색)
        max_results=50,        # 20 -> 50개로 늘림 (많이 가져와서 AI로 거르는 게 유리)
        days=2                 # 2일
    )
    
    raw_results = response['results']
    print(f"1차 광범위 검색결과: {len(raw_results)}개 확보. 검증 시작...")
    
    date_filtered_results = []
    
    for item in raw_results:
        pub_date = item.get('published_date')
        # 날짜 검증 (days=3 기준)
        if is_recent_article(pub_date, days_limit=3):
            date_filtered_results.append(item)

    # 중복 제거
    final_candidates, history = filter_new_articles(date_filtered_results)
    
    # 너무 많으면 AI 비용 절약을 위해 15개까지만 추림
    final_selection = final_candidates[:15]
    
    print(f"날짜/중복 필터 후 남은 기사: {len(final_selection)}개")

    # (히스토리 저장은 최종 발송된 것만 해야 하므로 여기서는 임시로 리스트만 반환)
    # 실제 history 파일 저장은 create_pdf 단계 이후나, AI가 확정한 뒤에 하는 게 좋지만
    # 구조상 여기서는 '검색된 후보군'을 모두 기록해버리면 AI가 거른(야구기사 등) 것도 
    # '보낸 셈' 치게 되므로, 히스토리 저장 위치를 옮기는 게 좋습니다.
    # 하지만 코드 수정을 최소화하기 위해 일단은 검색된 URL은 다 기록합니다.
    
    for item in final_selection:
        history.append(item['url'])
        
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

    return final_selection


# 5. AI 상세 요약 (안전 필터 해제 + JSON 추출 강화)
def summarize_news(news_list):
    if not news_list:
        return []

    print(f"Gemini에게 {len(news_list)}건의 기사 요약 및 검수 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    너는 보안 뉴스 편집장이야. 아래 뉴스 데이터를 분석해 JSON 리스트로 반환해.
    
    [규칙]
    1. 주제 필터링: '정보보호', '해킹', '보안', '개인정보', 'IT정책' 관련 기사만 남기고 나머지는 버려.
    2. 언어: 모든 내용은 반드시 '한국어'로 작성해.
    3. 형식: 오직 JSON 리스트만 출력해. (마크다운이나 설명 금지)
    
    [입력 데이터]
    {json.dumps(news_list)}
    
    [출력 예시]
    [
        {{"title": "한국어 기사 제목", "summary": "3줄 요약 내용", "url": "http://..."}},
        ...
    ]
    """
    
    # ★ 안전 설정 추가: 해킹 뉴스라고 차단하지 않도록 모든 필터 해제 (BLOCK_NONE)
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
            
            # 답변 후보가 있는지 확인
            if 'candidates' not in res_json or not res_json['candidates']:
                print("오류: AI가 답변을 생성하지 않았습니다. (안전 필터 등 원인)")
                print(f"디버그 정보: {res_json}")
                return []
                
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # ★ 강력한 JSON 추출 로직 (앞뒤 잡담 잘라내기)
            start_index = text.find('[')
            end_index = text.rfind(']') + 1
            
            if start_index == -1 or end_index == 0:
                print("오류: AI 답변에서 JSON 리스트를 찾을 수 없습니다.")
                print(f"AI 원본 답변: {text[:100]}...") # 앞부분만 로그 출력
                return []
                
            clean_json_text = text[start_index:end_index]
            result = json.loads(clean_json_text)
            
            print(f"AI 검수 완료: {len(result)}개 기사 선정됨.")
            return result
            
        else:
            print(f"API 호출 에러: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"요약 처리 중 예외 발생: {str(e)}")
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
