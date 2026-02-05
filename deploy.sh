#!/bin/bash

# ==========================================
# AWS SAM 배포 자동화 스크립트
# ==========================================
# 이 스크립트는 Lambda 함수를 빌드하고 AWS에 배포합니다.
#
# 사용법:
#   ./deploy.sh           # 일반 배포
#   ./deploy.sh --guided  # 가이드 모드 (처음 배포 시)
#   ./deploy.sh --test    # 테스트 실행만

set -e  # 에러 발생 시 즉시 종료

# 색상 코드
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}AWS SAM 배포 시작${NC}"
echo -e "${GREEN}=====================================${NC}"

# 1. 사전 체크
echo -e "\n${YELLOW}[1/5] 사전 요구사항 확인...${NC}"

# SAM CLI 설치 확인
if ! command -v sam &> /dev/null; then
    echo -e "${RED}❌ AWS SAM CLI가 설치되지 않았습니다.${NC}"
    echo -e "${YELLOW}설치 방법: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html${NC}"
    exit 1
fi
echo -e "${GREEN}✅ SAM CLI 확인 완료${NC}"

# AWS CLI 설정 확인
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS 자격 증명이 설정되지 않았습니다.${NC}"
    echo -e "${YELLOW}AWS CLI를 설정하세요: aws configure${NC}"
    exit 1
fi
echo -e "${GREEN}✅ AWS 자격 증명 확인 완료${NC}"

# 현재 AWS 계정 정보 출력
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region || echo "ap-northeast-2")
echo -e "${GREEN}   계정 ID: ${ACCOUNT_ID}${NC}"
echo -e "${GREEN}   리전: ${REGION}${NC}"

# 2. 템플릿 검증
echo -e "\n${YELLOW}[2/5] SAM 템플릿 검증...${NC}"
sam validate --lint

# 3. 빌드
echo -e "\n${YELLOW}[3/5] Lambda 함수 빌드...${NC}"
sam build --use-container

# 테스트 모드인 경우 여기서 종료
if [[ "$1" == "--test" ]]; then
    echo -e "\n${GREEN}=====================================${NC}"
    echo -e "${GREEN}테스트 빌드 완료${NC}"
    echo -e "${GREEN}=====================================${NC}"
    exit 0
fi

# 4. Secrets Manager 설정 확인
echo -e "\n${YELLOW}[4/5] AWS Secrets Manager 확인...${NC}"
echo -e "${YELLOW}다음 Secrets가 필요합니다:${NC}"
echo "  - daily-news-bot/naver"
echo "  - daily-news-bot/tavily"
echo "  - daily-news-bot/groq"
echo "  - daily-news-bot/telegram"

# Secrets 존재 여부 확인
MISSING_SECRETS=()
for secret in "daily-news-bot/naver" "daily-news-bot/tavily" "daily-news-bot/groq" "daily-news-bot/telegram"; do
    if ! aws secretsmanager describe-secret --secret-id "$secret" &> /dev/null; then
        MISSING_SECRETS+=("$secret")
    fi
done

if [ ${#MISSING_SECRETS[@]} -gt 0 ]; then
    echo -e "${RED}❌ 다음 Secrets가 없습니다:${NC}"
    for secret in "${MISSING_SECRETS[@]}"; do
        echo -e "${RED}   - $secret${NC}"
    done
    echo -e "\n${YELLOW}Secrets 생성 방법은 README_AWS.md를 참고하세요.${NC}"

    read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✅ 모든 Secrets 확인 완료${NC}"
fi

# 5. 배포
echo -e "\n${YELLOW}[5/5] AWS에 배포...${NC}"

if [[ "$1" == "--guided" ]]; then
    # 가이드 모드 (처음 배포 시)
    sam deploy --guided
else
    # 일반 배포 (samconfig.toml 사용)
    sam deploy
fi

# 배포 완료
echo -e "\n${GREEN}=====================================${NC}"
echo -e "${GREEN}✅ 배포 완료!${NC}"
echo -e "${GREEN}=====================================${NC}"

# 배포된 리소스 정보 출력
echo -e "\n${YELLOW}배포된 리소스:${NC}"
aws cloudformation describe-stacks \
    --stack-name daily-news-bot-stack \
    --query 'Stacks[0].Outputs' \
    --output table

# 로그 확인 명령어 안내
echo -e "\n${YELLOW}로그 확인:${NC}"
echo "  sam logs -n daily-security-news-bot --tail"

# 수동 실행 명령어 안내
echo -e "\n${YELLOW}수동 실행:${NC}"
echo "  aws lambda invoke --function-name daily-security-news-bot output.json"

echo -e "\n${GREEN}배포가 완료되었습니다!${NC}"
