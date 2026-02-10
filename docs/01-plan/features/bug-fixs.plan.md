# Plan: bug-fixs

> Code Review 기반 버그 수정 및 코드 정리

## 1. 개요

| 항목 | 내용 |
|------|------|
| Feature | bug-fixs |
| 우선순위 | High |
| 발견 경위 | Code Review (2026-02-10) |
| 영향 범위 | news_bot.py, template.yaml, deploy.sh |

## 2. 문제 목록

### Critical (즉시 수정)

| # | 파일:라인 | 이슈 | 영향 |
|---|-----------|------|------|
| C1 | news_bot.py:518-639 | Dead code (구 Gemini 함수 잔해 122줄) | 가독성 저해, 미정의 변수 `mode` 포함 |
| C2 | news_bot.py:207 | 하드코딩된 연도 `'2026'` | 2027년부터 해외 뉴스 0건 |

### Major (우선 수정)

| # | 파일:라인 | 이슈 | 영향 |
|---|-----------|------|------|
| M1 | news_bot.py:134-139 | `.lower()`로 'AI보안' 키워드 매칭 실패 | 우선순위 점수 오산정 |
| M2 | template.yaml:42 | `GROQ_API_KEY` → `OPENAI_API_KEY` 불일치 | Lambda 배포 시 AI 선별 실패 |
| M3 | news_bot.py:437,516 | Groq 관련 오래된 주석 | 유지보수 혼란 |

### Minor (개선)

| # | 파일:라인 | 이슈 | 영향 |
|---|-----------|------|------|
| m1 | news_bot.py:42-47 | 모듈 레벨 datetime (Lambda 캐시 위험) | 웜 컨테이너에서 날짜 오류 가능 |
| m2 | news_bot.py:805 | 변수명 `url` 중복 사용 | 가독성 저하 |
| m3 | news_bot.py:106-110 | HTML 엔티티 불완전 처리 | 일부 특수문자 미변환 |
| m4 | deploy.sh:71 | 시크릿 이름 `groq` → `openai` 불일치 | 배포 스크립트 검증 오류 |

## 3. 수정 전략

```
수정 순서: C1 → C2 → M1 → M2 → M3 → m1 → m2 → m3 → m4
```

1. **Dead code 제거** (C1): lines 514-639 삭제
2. **동적 연도 처리** (C2): `str(NOW.year)` 사용
3. **키워드 매칭 수정** (M1): 키워드도 `.lower()` 적용
4. **환경변수 통일** (M2+m4): template.yaml, deploy.sh에서 Groq → OpenAI 변경
5. **주석 업데이트** (M3): 정확한 주석으로 교체
6. **datetime 함수 내부 이동** (m1): `process_news()` 내부에서 계산
7. **변수명 정리** (m2): `telegram_url`로 변경
8. **HTML 엔티티 처리** (m3): `html.unescape()` 도입

## 4. 리스크

| 리스크 | 대응 |
|--------|------|
| Dead code 삭제 시 다른 코드 영향 | 삭제 범위를 정확히 특정 |
| datetime 이동 시 전역 참조 깨짐 | `YESTERDAY`, `TODAY_STR` 사용처 전수 검사 |
| template.yaml 변경 시 기존 AWS 배포 영향 | Secrets Manager 키 이름도 함께 변경 필요 |

## 5. 완료 조건

- [ ] 9개 이슈 모두 수정
- [ ] `python -c "import news_bot"` 정상 실행
- [ ] 기존 기능 동작에 영향 없음
