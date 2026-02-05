# AWS Lambda 배포 가이드

이 가이드는 Daily Security News Bot을 AWS Lambda에 배포하는 방법을 설명합니다.

## 목차

1. [왜 AWS Lambda인가?](#왜-aws-lambda인가)
2. [사전 요구사항](#사전-요구사항)
3. [AWS 설정](#aws-설정)
4. [배포 방법](#배포-방법)
5. [배포 후 관리](#배포-후-관리)
6. [비용](#비용)
7. [문제 해결](#문제-해결)

---

## 왜 AWS Lambda인가?

### GitHub Actions vs AWS Lambda 비교

| 항목 | GitHub Actions | AWS Lambda |
|------|----------------|------------|
| **비용** | 월 2,000분 무료 → 초과 시 유료 | 월 100만 요청 무료 → 하루 1회면 거의 무료 |
| **안정성** | 대규모 장애 발생 가능 | 99.95% SLA 보장 |
| **속도** | 러너 대기 시간 변동적 (수분~수십분) | 즉시 실행 (콜드스타트 최대 10초) |
| **관리** | 워크플로우 파일만 관리 | 인프라 관리 불필요 (서버리스) |
| **확장성** | 제한적 | 자동 스케일링 |

### 결론
- **하루 1회 실행**: AWS Lambda가 비용/안정성 면에서 우수
- **GitHub Actions 장애 시에도 영향 없음**
- **빠르고 안정적인 실행 보장**

---

## 사전 요구사항

### 1. AWS 계정
- AWS 계정이 없다면 [여기서 생성](https://aws.amazon.com/)
- 프리 티어 계정이면 충분합니다

### 2. AWS CLI 설치

**macOS:**
```bash
brew install awscli
```

**Windows:**
```powershell
msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi
```

**Linux:**
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

설치 확인:
```bash
aws --version
```

### 3. AWS SAM CLI 설치

**macOS:**
```bash
brew install aws-sam-cli
```

**Windows:**
- [설치 가이드](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html#install-sam-cli-instructions)

**Linux:**
```bash
wget https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip
unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
sudo ./sam-installation/install
```

설치 확인:
```bash
sam --version
```

### 4. Docker 설치 (선택사항, 권장)
- [Docker Desktop 다운로드](https://www.docker.com/products/docker-desktop/)
- Lambda 함수를 로컬에서 빌드/테스트할 때 필요

---

## AWS 설정

### 1. AWS CLI 자격 증명 설정

```bash
aws configure
```

입력 내용:
```
AWS Access Key ID: [IAM에서 생성한 액세스 키]
AWS Secret Access Key: [IAM에서 생성한 시크릿 키]
Default region name: ap-northeast-2  # 서울 리전
Default output format: json
```

**IAM 사용자 생성 방법:**
1. AWS 콘솔 → IAM → 사용자 → 사용자 추가
2. 이름: `daily-news-bot-deployer`
3. 권한: `AdministratorAccess` (또는 아래 최소 권한)
4. 액세스 키 생성 → CLI로 다운로드

**최소 권한 정책 (보안 강화 시):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "s3:*",
        "iam:*",
        "logs:*",
        "events:*",
        "secretsmanager:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2. AWS Secrets Manager에 API 키 저장

Lambda 함수가 API 키를 안전하게 사용하도록 Secrets Manager에 저장합니다.

#### Naver API 키 저장
```bash
aws secretsmanager create-secret \
  --name daily-news-bot/naver \
  --secret-string '{"client_id":"YOUR_NAVER_CLIENT_ID","client_secret":"YOUR_NAVER_CLIENT_SECRET"}' \
  --region ap-northeast-2
```

#### Tavily API 키 저장
```bash
aws secretsmanager create-secret \
  --name daily-news-bot/tavily \
  --secret-string '{"api_key":"YOUR_TAVILY_API_KEY"}' \
  --region ap-northeast-2
```

#### Groq API 키 저장
```bash
aws secretsmanager create-secret \
  --name daily-news-bot/groq \
  --secret-string '{"api_key":"YOUR_GROQ_API_KEY"}' \
  --region ap-northeast-2
```

#### Telegram 설정 저장
```bash
aws secretsmanager create-secret \
  --name daily-news-bot/telegram \
  --secret-string '{"bot_token":"YOUR_TELEGRAM_BOT_TOKEN","chat_id":"YOUR_TELEGRAM_CHAT_ID"}' \
  --region ap-northeast-2
```

**주의:** 위 명령어의 `YOUR_XXX` 부분을 실제 값으로 교체하세요!

**AWS 콘솔에서 설정하기:**
1. AWS 콘솔 → Secrets Manager → 새 보안 암호 저장
2. 보안 암호 유형: 다른 유형의 보안 암호
3. 키/값 쌍으로 입력
4. 보안 암호 이름: `daily-news-bot/naver` (나머지도 동일)

---

## 배포 방법

### 1. 처음 배포 (가이드 모드)

```bash
# 배포 스크립트 실행 권한 부여
chmod +x deploy.sh

# 가이드 모드로 배포
./deploy.sh --guided
```

가이드 모드에서 입력 내용:
```
Stack Name: daily-news-bot-stack
AWS Region: ap-northeast-2
Confirm changes before deploy: Y
Allow SAM CLI IAM role creation: Y
Disable rollback: N
Save arguments to configuration file: Y
```

### 2. 이후 배포 (자동 모드)

```bash
# samconfig.toml 설정을 사용한 자동 배포
./deploy.sh
```

### 3. 수동 배포 (세부 제어 필요 시)

```bash
# 1. 검증
sam validate --lint

# 2. 빌드
sam build --use-container

# 3. 배포
sam deploy
```

---

## 배포 후 관리

### 1. Lambda 함수 수동 실행 (테스트)

```bash
aws lambda invoke \
  --function-name daily-security-news-bot \
  --region ap-northeast-2 \
  output.json

# 결과 확인
cat output.json
```

### 2. 로그 확인

**실시간 로그 보기:**
```bash
sam logs -n daily-security-news-bot --tail
```

**특정 시간대 로그 보기:**
```bash
sam logs -n daily-security-news-bot \
  --start-time '2026-02-03T07:00:00' \
  --end-time '2026-02-03T08:00:00'
```

**AWS 콘솔에서 확인:**
1. CloudWatch → 로그 그룹 → `/aws/lambda/daily-security-news-bot`

### 3. 스케줄 변경

`template.yaml` 파일에서 cron 표현식 수정:

```yaml
Schedule: cron(20 22 * * ? *)  # UTC 22:20 = KST 07:20
```

**cron 표현식 예시:**
- `cron(0 0 * * ? *)` - 매일 09:00 KST
- `cron(0 12 * * ? *)` - 매일 21:00 KST
- `cron(0 6 ? * MON-FRI *)` - 평일 15:00 KST

변경 후 재배포:
```bash
./deploy.sh
```

### 4. 환경 변수 수정

Secrets Manager에서 값 수정:

```bash
# 기존 시크릿 업데이트
aws secretsmanager update-secret \
  --secret-id daily-news-bot/telegram \
  --secret-string '{"bot_token":"NEW_TOKEN","chat_id":"NEW_CHAT_ID"}' \
  --region ap-northeast-2
```

**주의:** Secrets 수정 시 Lambda 재배포 불필요 (자동 반영)

### 5. 함수 삭제

```bash
# 전체 스택 삭제
aws cloudformation delete-stack --stack-name daily-news-bot-stack

# 또는 SAM CLI 사용
sam delete --stack-name daily-news-bot-stack
```

---

## 비용

### 무료 티어 (월간)
- **Lambda 요청**: 100만 요청 무료
- **Lambda 실행 시간**: 40만 GB-초 무료
- **CloudWatch Logs**: 5GB 무료
- **Secrets Manager**: 30일 무료 (이후 $0.40/secret/월)

### 예상 비용 (하루 1회 실행)
- **Lambda**: $0 (무료 티어 범위 내)
- **Secrets Manager**: $1.60/월 (4개 시크릿)
- **CloudWatch Logs**: $0 (무료 티어 범위 내)

**총 예상 비용: 월 $1.60 ~ $2.00**

### 비용 절감 팁
1. **Secrets Manager 대신 환경 변수 사용** (비권장, 보안 취약)
   - `template.yaml`에서 직접 환경 변수 설정
   - 비용: $0, 단 GitHub에 올리면 안 됨!

2. **CloudWatch Logs 보관 기간 단축**
   - 현재: 30일 → 7일로 변경 가능

---

## 문제 해결

### 1. 배포 실패: "Unable to upload artifact"

**원인:** S3 버킷 권한 문제

**해결:**
```bash
# SAM이 자동으로 S3 버킷 생성하도록 설정
sam deploy --resolve-s3
```

### 2. Lambda 실행 실패: "Task timed out"

**원인:** 15분 타임아웃 초과

**해결:**
- `template.yaml`에서 `Timeout` 값 확인 (현재 900초 = 15분)
- 뉴스 수집 시간이 너무 길면 키워드 수 줄이기

### 3. 환경 변수 오류: "Unable to resolve secret"

**원인:** Secrets Manager에 시크릿이 없음

**해결:**
```bash
# 시크릿 존재 확인
aws secretsmanager list-secrets --region ap-northeast-2

# 없으면 위 "AWS 설정" 섹션 참고하여 생성
```

### 4. 텔레그램 전송 실패: "Chat not found"

**원인:** 텔레그램 봇에게 메시지를 먼저 보내지 않음

**해결:**
1. 텔레그램 앱에서 봇 검색
2. `/start` 명령어 전송
3. Lambda 재실행

### 5. 로그에 한글이 깨짐

**원인:** 인코딩 문제

**해결:**
- `template.yaml`에 이미 `PYTHONUNBUFFERED: "1"` 설정됨
- CloudWatch 콘솔에서 UTF-8 인코딩 확인

### 6. GitHub Actions와 동시 실행 방지

**해결:**
- GitHub Actions 워크플로우 비활성화:
  ```bash
  # .github/workflows/daily-news.yml 삭제 또는
  # 파일 내에서 schedule 부분만 주석 처리
  ```

---

## 추가 기능

### 1. Slack 알림 추가

`template.yaml`에 환경 변수 추가:
```yaml
Environment:
  Variables:
    SLACK_WEBHOOK_URL: '{{resolve:secretsmanager:daily-news-bot/slack:SecretString:webhook_url}}'
```

`news_bot.py`에서 Slack 전송 코드 추가 (직접 구현 필요)

### 2. 멀티 리전 배포

다른 리전에도 배포:
```bash
sam deploy --region us-east-1
```

### 3. 알람 설정 (실패 시 알림)

CloudWatch Alarm 설정:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name daily-news-bot-errors \
  --alarm-description "Lambda 실행 오류 알림" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 3600 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --dimensions Name=FunctionName,Value=daily-security-news-bot \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:ap-northeast-2:ACCOUNT_ID:your-sns-topic
```

---

## 참고 자료

- [AWS Lambda 공식 문서](https://docs.aws.amazon.com/lambda/)
- [AWS SAM 공식 문서](https://docs.aws.amazon.com/serverless-application-model/)
- [Secrets Manager 가격](https://aws.amazon.com/secrets-manager/pricing/)
- [Lambda 가격](https://aws.amazon.com/lambda/pricing/)

---

## 지원

문제가 발생하면 이슈를 남겨주세요!
