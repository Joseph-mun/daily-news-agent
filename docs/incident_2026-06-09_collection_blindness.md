# 인시던트 리포트 — 2026-06-09 브리핑 미발행 (수집 불가)

**상태**: 브리핑 미발행(ABORT). DB 미기록·미푸시. 워크스페이스 무변경.
**작성**: 2026-06-09, Cowork 스케줄 실행(`daily-security-briefing`, 08:10 KST 무인) 사후 분석.

---

## 1. 증상

6/9 정기 실행에서 48시간(pubDate ≥ 2026-06-07) 신선 **국내 금융보안 기사를 0건** 확보. 스펙의 하드 가드(국내 ≥8 / 전체 ≥10 / A·B ≥4)를 모두 미달하여, "stale 항목 패딩 금지·저품질 푸시 금지" 원칙에 따라 정상 중단.

48시간 내 확보 가능했던 신선 항목은 해외 취약점 공시뿐: MS 6월 정기패치(73개 취약점), Check Point VPN 제로데이 **CVE-2026-50751**(Qilin 랜섬웨어, 패치 전 ~1개월 악용). 국내 후보(티빙 민관합동조사 6/5, 성형외과 다크웹 6/4, 72h 통지 의무화 6/2 등)는 모두 윈도우 밖 + 6/7·6/8 브리핑과 주제 중복.

---

## 2. 원인 진단 (근거 실측)

근본 원인은 "뉴스 가뭄"이 아니라 **무인 실행 환경의 신선 수집 경로 부재**다. 세 가지가 겹쳤다.

### (A) bash 샌드박스 egress = github.com 단일 허용 화이트리스트
프록시 `localhost:3128` CONNECT 실측 결과:

| 대상 | 결과 |
|---|---|
| github.com | **200 (허용)** |
| api.github.com / raw.githubusercontent.com / codeload.github.com | 000 (차단) |
| openapi.naver.com (네이버 뉴스 API) | 000 (차단) |
| api.tavily.com | 000 (차단) |
| api.openai.com | 000 (차단) |
| www.dailysecu.com / www.boannews.com | 000 (차단) |

→ git clone/push만 통과(어제 정상 작동한 이유). repo의 검증된 수집기 `news_bot.py`의 `search_naver_news()`(openapi.naver.com)·`search_tavily_news()`는 **bash에서 호출 불가**. 네이버/Tavily는 AWS Lambda 경로 전용이며, Cowork 무인 실행에서는 죽은 경로.

### (B) web_fetch = URL별 제각각 시점의 CDN 캐시 (최신 강제 불가)
동일 목록을 URL 변형별로 호출 시 서로 다른 과거 스냅샷 반환:

| URL | 반환된 발행일 스냅샷 |
|---|---|
| `articleList.html?view_type=sm` | 2026-05-13 |
| `articleList.html` (파라미터 없음) | 2026-06-01 |
| `dailysecu.com/` (홈) | 2026-06-08 오전 |
| WebSearch가 본 실제 기사수 | 149,348건(최신) ↔ web_fetch는 149,088건(구캐시) |

→ web_fetch는 **provenance 잠금**(검색/이전 fetch에 등장한 URL만 호출 가능)이라 캐시버스터 파라미터·임의 기사 ID 탐침 불가. **기사 상세 페이지는 발행시점 캐시라 정확**하지만, 그 URL을 먼저 "발견"할 신선 목록을 못 얻는 게 병목.

### (C) WebSearch는 미국 인덱스 + 라이브 브라우저 없음
WebSearch는 작동하나 당일 한국 기사 색인이 늦어 6/8 오후~6/9 항목을 거의 못 띄움. Chrome 확장(라이브 JS 렌더링) 폴백은 **무인 실행 시점(08:10 KST)에 브라우저 미연결**이라 사용 불가(`list_connected_browsers` → `[]`).

### 종합
무인 실행이 신선 기사를 "발견"할 수 있는 경로는 사실상 WebSearch뿐인데 당일 한국 색인이 약하고, 유일하게 신선했던 dailysecu 홈(6/8 오전)은 이미 6/8 브리핑이 소비. → 6/9(월요일 다음 화요일) 증분 윈도우에서 신선 국내 = 0. 중단은 스펙상 올바른 결과.

---

## 3. 조치 방안 (우선순위)

### P1 — 네이버/Tavily egress 허용 (가장 견고, 기존 코드 재사용) ★권장
Cowork 샌드박스 프록시 화이트리스트에 `openapi.naver.com`, `api.tavily.com`(요약에 쓰면 `api.openai.com`/`api.groq.com`) 추가.
- **방법**: Team/Enterprise면 Admin settings → Capabilities → 네트워크 접근에서 도메인 허용. 개인 플랜이면 해당 옵션 부재 → P2/P3로.
- **효과**: 스케줄 태스크가 repo의 `search_naver_news()`(pubDate 정렬·dedup 내장)를 bash에서 직접 실행 → 캐시·색인 문제 원천 제거. 유지보수 최소.
- **검증**: 허용 후 `python -c "from news_bot import search_naver_news; print(len(search_naver_news()))"`로 확인.

### P2 — RSS 우선 디스커버리로 프롬프트 수정 (인프라 변경 불필요)
dailysecu RSS(`/rss/allArticle.xml`, `/rss/S1N2.xml`), boannews RSS 존재. 절차: ① WebSearch로 RSS URL을 provenance에 시드 → ② web_fetch로 RSS(XML, pubDate 포함) 취득 → ③ 신선 항목의 상세 URL만 web_fetch(상세는 발행시점 캐시라 정확).
- **한계**: RSS도 web_fetch 캐시 지연 가능성 잔존(검증 필요). 목록 HTML보다는 신선할 확률이 높음.
- **작업**: `docs/prompts/briefing_prompt.md`의 Collect 단계에 "RSS 우선" 지시 추가.

### P3 — AWS Lambda 경로를 정본(system of record)으로 유지
repo에 네이버/Tavily/OpenAI/Telegram 완결 파이프라인(`template.yaml`, `lambda_handler.py`, `samconfig.toml`)이 이미 존재하고 egress 제약 없음.
- **결정 필요**: 자동 브리핑의 정본을 Lambda로 둘지, Cowork로 둘지. Lambda가 아직 배포 상태면 그게 신뢰 가능한 경로이고 Cowork 태스크는 보조/수동으로 격하. (현재 run_log상 5월 중순 이후 Cowork가 일일 구동 → 둘이 중복 가능성. 정리 권장.)

### P4 — 수동 재실행용 브라우저 보조
지금처럼 즉석 재실행 시에는 Chrome+Claude 확장을 열어두면 라이브 페이지로 캐시 우회 가능(navigate→get_page_text). **무인 08:10 cron엔 부적합**, 수동 보강용.

### P5 — 중단의 가시화(사일런트 실패 방지)
현재 중단은 Telegram·로그 흔적이 없어 "돌았는지 실패인지" 불명. 개선:
- 중단 시 `docs/run_log.md`에 `ABORT — 사유` 한 줄 append 후 push. **이 경로는 안전**: `post-briefing.yml`은 `web/data/news.db` 변경 시에만 트리거되므로 run_log push는 Telegram 오발송 없음.
- (선택) 별도 경량 알림으로 "오늘 미발행 + 사유" 통지.

### (보조) 윈도우 정책 미세조정
월→화 등 주말 인접일은 증분이 얇음. 단 6/9 문제의 본질은 윈도우 폭이 아니라 **디스커버리 실명**이므로, 48h→72h 확대는 차순위. 디스커버리(P1/P2) 해결이 선행.

---

## 4. 권장 실행 순서

1. **P5 즉시 적용** — 중단 가시화(저비용, 안전). 사일런트 실패부터 제거.
2. **P3 결정** — Lambda vs Cowork 정본 확정. Lambda 살아있으면 그걸 신뢰 경로로.
3. **P1 시도** — 플랜이 egress 허용을 지원하면 최우선 적용(가장 견고).
4. P1 불가 시 **P2(RSS) 프롬프트 패치 + 검증**.
5. P4는 수동 재실행 시에만.

---

## 부록 — 확정 사실 요약
- 스케줄: `0 8 * * *`(08:10 KST, jitter ~10분), 무인. 다음 실행 6/10 08:09 KST.
- `post-briefing.yml` 트리거: `web/data/news.db` push only → 중단 시 미푸시로 오발송 방지됨(정상).
- bash egress: github.com만 허용. 네이버/Tavily/OpenAI/뉴스사이트 전부 차단.
- web_fetch: URL별 상이한 과거 캐시 + provenance 잠금. 상세 페이지는 정확, 목록 발견이 병목.
- 라이브 브라우저: 무인 실행 시 미연결.
