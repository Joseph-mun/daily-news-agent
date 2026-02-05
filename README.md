# 금융권 보안 뉴스 봇

매일 아침 금융권 보안 관련 뉴스를 수집하고 AI로 선별하여 카카오톡으로 전송하는 자동화 봇입니다.

## 주요 기능

- 🇰🇷 **국내 뉴스 수집**: 네이버 뉴스 API를 통해 AI보안, 정보보호, 해킹, 개인정보유출, 금융보안, 랜섬웨어 관련 뉴스 수집 (AI보안 최우선)
- 🇺🇸 **해외 뉴스 수집**: Tavily API를 통해 글로벌 보안 뉴스 수집
- 🤖 **AI 선별 및 요약**: OpenAI API (GPT-4o-mini)를 사용하여 중요 뉴스 선별 + 2줄 요약 (국내 7개, 해외 3개)
- 📱 **텔레그램 전송**: 선별된 뉴스를 요약과 함께 자동 전송
- ⏰ **자동 실행**: GitHub Actions를 통해 매일 아침 자동 실행
- ⚡ **배치 처리**: API 호출 횟수 50% 절감 (2회 → 1회)

## 프로젝트 구조

```
dailynewsbot/
├── news_bot.py          # 메인 뉴스봇 스크립트
├── requirements.txt     # Python 패키지 의존성
├── .env.example        # 환경변수 예시 파일
├── README.md           # 프로젝트 설명서
└── .github/
    └── workflows/
        └── daily-news.yml  # GitHub Actions 워크플로우
```

## 설정 방법

### 1. 필요한 API 키 발급

#### 네이버 뉴스 API
1. [네이버 개발자 센터](https://developers.naver.com/) 접속
2. 애플리케이션 등록
3. Client ID와 Client Secret 발급

#### Tavily API
1. [Tavily](https://tavily.com/) 접속
2. 회원가입 후 API 키 발급

#### OpenAI API
1. [OpenAI Platform](https://platform.openai.com/) 접속
2. 회원가입 후 API 키 생성
3. GPT-4o-mini 모델 사용 (비용 효율적)

#### 텔레그램 봇 (선택사항)
1. 텔레그램에서 @BotFather 검색
2. `/newbot` 명령으로 봇 생성
3. 봇 토큰 발급
4. 봇에게 메시지를 보내거나 그룹에 추가한 후 채팅 ID 확인

### 2. GitHub Secrets 설정

GitHub 저장소에서 다음 Secrets를 설정해야 합니다:

1. 저장소 페이지로 이동
2. **Settings** → **Secrets and variables** → **Actions** 클릭
3. **New repository secret** 클릭하여 다음 값들을 추가:

   - `NAVER_CLIENT_ID`: 네이버 Client ID
   - `NAVER_CLIENT_SECRET`: 네이버 Client Secret
   - `TAVILY_API_KEY`: Tavily API 키
   - `OPENAI_API_KEY`: OpenAI API 키
   - `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
   - `TELEGRAM_CHAT_ID`: 텔레그램 채팅 ID

### 3. 로컬 테스트 (선택사항)

로컬에서 테스트하려면:

```bash
# 1. 가상환경 생성 (선택사항)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 환경변수 설정
# .env 파일을 생성하고 .env.example을 참고하여 값 입력
# 또는 직접 환경변수로 설정:
export NAVER_CLIENT_ID="your_id"
export NAVER_CLIENT_SECRET="your_secret"
# ... (나머지 환경변수들)

# 4. 실행
python news_bot.py
```

## 뉴스 우선순위

봇은 다음 우선순위에 따라 뉴스를 선별합니다:

1. **AI보안** (최우선) - AI 보안 관련 뉴스
2. **침해사고** (최우선) - 해킹, 유출, 랜섬웨어, 사이버공격, 보안사고
3. **규제/정책** - 금융당국·보안원 발표, 법규 개정
4. **기술/취약점** - 제로데이, 새 공격기법
5. **신한 관련** - 신한금융그룹 계열사 관련 뉴스 (+가점)

## GitHub Actions 실행 시간 설정

`.github/workflows/daily-news.yml` 파일에서 실행 시간을 변경할 수 있습니다.

현재 설정: 매일 아침 8시 (KST)
```yaml
schedule:
  - cron: '0 23 * * *'  # UTC 23:00 = KST 08:00 (다음날)
```

다른 시간으로 변경하려면:
- `cron` 형식: `분 시 일 월 요일`
- UTC 기준으로 설정 (KST는 UTC+9)
- 예: 오전 9시 (KST) = `'0 0 * * *'` (UTC 00:00)

## 코드 개선 사항

### 에러 핸들링 강화
- 모든 API 호출에 타임아웃 설정
- 재시도 로직 개선
- 상세한 로깅 추가

### 코드 구조 개선
- 함수별 명확한 역할 분리
- 타입 힌트 추가
- 주석 및 docstring 추가
- 로깅 시스템 도입

### 안정성 향상
- 중복 뉴스 제거 로직 개선
- 날짜 파싱 에러 처리
- JSON 파싱 에러 처리

## 문제 해결

### 뉴스가 수집되지 않는 경우
1. API 키가 올바르게 설정되었는지 확인
2. GitHub Actions 로그 확인: **Actions** 탭 → 최근 워크플로우 실행 클릭
3. 네이버 API 할당량 확인 (일일 제한 있음)

### 텔레그램 전송이 안 되는 경우
1. 봇 토큰이 올바른지 확인
2. 채팅 ID가 올바른지 확인 (개인 채팅의 경우 봇에게 먼저 메시지를 보내야 함)
3. 봇이 그룹에 추가되어 있고 관리자 권한이 있는지 확인

### AI 선별이 제대로 안 되는 경우
1. OpenAI API 키 확인
2. API 할당량 및 크레딧 확인
3. 로그에서 JSON 파싱 에러 확인

## 라이선스

이 프로젝트는 개인 사용 목적으로 제작되었습니다.
