"""
AWS Lambda Handler for Daily News Bot

Lambda 진입점. news_bot.py의 main() 함수를 호출합니다.
"""
import logging
import sys

# Lambda 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 로컬 모듈 임포트
from news_bot import main

def lambda_handler(event, context):
    """
    AWS Lambda 핸들러 함수

    Args:
        event: EventBridge에서 전달하는 이벤트 데이터
        context: Lambda 실행 컨텍스트

    Returns:
        dict: 실행 결과
    """
    try:
        logger.info("=" * 50)
        logger.info("AWS Lambda 뉴스봇 실행 시작")
        logger.info(f"Request ID: {context.request_id}")
        logger.info(f"Function: {context.function_name}")
        logger.info("=" * 50)

        # 뉴스봇 실행
        main()

        logger.info("=" * 50)
        logger.info("AWS Lambda 뉴스봇 실행 완료")
        logger.info("=" * 50)

        return {
            'statusCode': 200,
            'body': 'News bot executed successfully'
        }

    except Exception as e:
        logger.error(f"Lambda 실행 중 오류: {e}", exc_info=True)

        return {
            'statusCode': 500,
            'body': 'Internal server error'
        }
