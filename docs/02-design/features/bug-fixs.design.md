# Design: bug-fixs

> Plan 문서 기반 상세 수정 설계

## 1. 수정 대상 파일

| 파일 | 수정 이슈 | 변경 규모 |
|------|-----------|-----------|
| news_bot.py | C1, C2, M1, M3, m1, m2, m3 | 대 |
| template.yaml | M2 | 소 |
| deploy.sh | m4 | 소 |

## 2. 수정 순서 및 상세 설계

### 수정 1: [C1] Dead Code 삭제 (news_bot.py:514-639)

**설명**: `call_openai_batch_selection` 함수 뒤에 남은 구 Gemini 함수 잔해 제거

**삭제 범위**: line 514 ~ line 639 (총 126줄)

```python
# 삭제 시작 (line 514)
# ==========================================
# [구 버전] Gemini 함수는 제거됨
# 현재는 Groq API (call_groq_batch_selection) 사용
# ==========================================
    if mode == 'KR':
        ...
# 삭제 끝 (line 639)
    return []
```

**삭제 후 상태**: `call_openai_batch_selection` 함수 끝(line 511) 바로 다음에 `process_news` 함수(기존 line 645)가 오도록 함

---

### 수정 2: [C2] 하드코딩된 연도 → 동적 연도 (news_bot.py:207)

**Before**:
```python
if pub_date and ('2026' not in pub_date and 'ago' not in pub_date):
    continue
```

**After**:
```python
current_year = str(NOW.year)
if pub_date and (current_year not in pub_date and 'ago' not in pub_date):
    continue
```

**참고**: `NOW`는 m1 수정 후 함수 내부에서 접근하게 되므로, `global NOW` 선언 이후 사용 가능

---

### 수정 3: [M1] `.lower()` 키워드 매칭 버그 (news_bot.py:134-139)

**Before**:
```python
title = article['title'].lower()
desc = article['description'].lower()

high_priority = ['AI보안', '해킹', '유출', '랜섬웨어', '사이버공격', '보안사고', '침해']
score += sum(10 for k in high_priority if k in title or k in desc)

mid_priority = ['금융보안원', '금감원', '규제', '보안기술', '제로데이', '취약점']
score += sum(5 for k in mid_priority if k in title or k in desc)
```

**After**:
```python
title = article['title'].lower()
desc = article['description'].lower()

high_priority = ['ai보안', '해킹', '유출', '랜섬웨어', '사이버공격', '보안사고', '침해']
score += sum(10 for k in high_priority if k in title or k in desc)

mid_priority = ['금융보안원', '금감원', '규제', '보안기술', '제로데이', '취약점']
score += sum(5 for k in mid_priority if k in title or k in desc)
```

**변경 포인트**: `high_priority` 리스트의 `'AI보안'` → `'ai보안'`으로 변경 (`.lower()` 적용된 텍스트와 일치하도록)

---

### 수정 4: [M2] template.yaml 환경변수 수정 (template.yaml:42)

**Before**:
```yaml
GROQ_API_KEY: '{{resolve:secretsmanager:daily-news-bot/groq:SecretString:api_key}}'
```

**After**:
```yaml
OPENAI_API_KEY: '{{resolve:secretsmanager:daily-news-bot/openai:SecretString:api_key}}'
```

**주의**: AWS Secrets Manager에 `daily-news-bot/openai` 시크릿을 새로 생성하거나, 기존 `daily-news-bot/groq`를 이름 변경해야 함 (인프라 작업은 별도)

---

### 수정 5: [M3] 오래된 주석 업데이트 (news_bot.py)

**수정 A** (line 437):
- Before: `# Groq 응답에서 텍스트 추출`
- After: `# OpenAI 응답에서 텍스트 추출`

**수정 B**: C1에서 lines 514-517 주석이 이미 삭제되므로 추가 작업 불필요

---

### 수정 6: [m1] datetime을 main() 내부로 이동 (news_bot.py:42-47)

**목적**: Lambda 웜 컨테이너에서 날짜가 캐시되는 문제 방지

**Before** (모듈 레벨, line 42-47):
```python
KST = ZoneInfo("Asia/Seoul")
NOW = datetime.now(KST)
TODAY_STR = NOW.strftime("%Y-%m-%d")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

logger.info(f"📅 기준 날짜(KST): {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")
```

**After** (모듈 레벨 유지하되 초기값 제거, main()에서 재계산):

```python
# 모듈 레벨 (선언만)
KST = ZoneInfo("Asia/Seoul")
NOW = None
TODAY_STR = None
YESTERDAY = None
```

```python
# main() 함수 시작 부분에 추가
def main():
    """메인 실행 함수"""
    global NOW, TODAY_STR, YESTERDAY
    NOW = datetime.now(KST)
    TODAY_STR = NOW.strftime("%Y-%m-%d")
    YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
    logger.info(f"📅 기준 날짜(KST): {TODAY_STR} (어제: {YESTERDAY} 이후 기사만 허용)")
    ...
```

**영향 분석**: `NOW`, `TODAY_STR`, `YESTERDAY`를 사용하는 함수들:
- `search_naver_news()` → `YESTERDAY`, `TODAY_STR` (line 92, 95, 98)
- `search_tavily_news()` → `NOW` (C2 수정에서 사용)
- `calculate_priority_score()` → `TODAY_STR` (line 150)
- `send_telegram()` → `TODAY_STR` (line 754, 777, 795)

모두 `main()` 호출 이후 실행되므로 `global` 선언으로 충분

---

### 수정 7: [m2] 변수명 `url` 중복 해소 (news_bot.py:805)

**Before**:
```python
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
```

**After**:
```python
telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
```

**연쇄 수정**: line 817 `requests.post(url, ...)` → `requests.post(telegram_api_url, ...)`

---

### 수정 8: [m3] HTML 엔티티 처리 개선 (news_bot.py:106-110)

**Before**:
```python
clean_title = re.sub('<.+?>', '', item.get('title', ''))
clean_title = clean_title.replace("&quot;", "'").replace("&amp;", "&")

clean_desc = re.sub('<.+?>', '', item.get('description', ''))
clean_desc = clean_desc.replace("&quot;", "'").replace("&amp;", "&")
```

**After**:
```python
import html  # 파일 상단 import 추가

clean_title = re.sub('<.+?>', '', item.get('title', ''))
clean_title = html.unescape(clean_title)

clean_desc = re.sub('<.+?>', '', item.get('description', ''))
clean_desc = html.unescape(clean_desc)
```

---

### 수정 9: [m4] deploy.sh 시크릿 이름 수정 (deploy.sh:71,76)

**Before**:
```bash
echo "  - daily-news-bot/groq"
...
for secret in "daily-news-bot/naver" "daily-news-bot/tavily" "daily-news-bot/groq" "daily-news-bot/telegram"; do
```

**After**:
```bash
echo "  - daily-news-bot/openai"
...
for secret in "daily-news-bot/naver" "daily-news-bot/tavily" "daily-news-bot/openai" "daily-news-bot/telegram"; do
```

---

## 3. 구현 순서 체크리스트

```
[ ] 1. [m3] import html 추가 (파일 상단)
[ ] 2. [m1] 모듈 레벨 datetime → None 초기화
[ ] 3. [m1] main()에 global + 재계산 추가
[ ] 4. [C1] Dead code 삭제 (lines 514-639)
[ ] 5. [M3] Groq 주석 → OpenAI 주석
[ ] 6. [M1] 키워드 'AI보안' → 'ai보안'
[ ] 7. [C2] 하드코딩 연도 → 동적 연도
[ ] 8. [m3] HTML 엔티티 → html.unescape()
[ ] 9. [m2] url → telegram_api_url
[ ] 10. [M2] template.yaml GROQ → OPENAI
[ ] 11. [m4] deploy.sh groq → openai
```

## 4. 변경하지 않는 것

- `lambda_handler.py`: 변경 불필요
- `.github/workflows/daily-news.yml`: 이미 `OPENAI_API_KEY` 사용 중 (정상)
- `requirements.txt`: `html`은 표준 라이브러리이므로 추가 불필요
- `README_AWS.md`: Groq 관련 설명은 별도 문서 업데이트 태스크로 분리
