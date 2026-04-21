# Auto-Deploy Setup (Cowork + GitHub Actions + Vercel)

Cowork 스케줄이 **단독으로 브리핑을 생성**하되, 배포(Vercel)와 알림(Telegram)은 **GitHub Actions가 받아서 처리**하는 구조. 2026-04-21 샌드박스 allowlist/인증 문제(api.telegram.org 차단, git push 불가)를 우회하기 위한 설계.

---

## 파이프라인 한 장 요약

```
08:10 KST ─► Cowork 스케줄
              │  수집 → 요약 → DB write
              │  git push origin main  (PAT HTTPS)
              ▼
         GitHub main 브랜치
              │
     ┌────────┴────────┐
     ▼                 ▼
   Vercel          GitHub Actions
   (자동 재빌드)   post-briefing.yml
                   │  script/post_briefing_telegram.py
                   ▼
              api.telegram.org
                   ▼
               Telegram 수신
```

모든 자동화가 **push 한 번**으로 연쇄 발동. Cowork는 push만 성공시키면 나머지는 따라옴.

---

## 1회성 설정 (Joseph — 로컬 브라우저/터미널)

### Step 1 — GitHub Fine-grained PAT 발급

1. https://github.com/settings/personal-access-tokens/new 접속
2. **Resource owner**: `Joseph-mun` (개인 계정)
3. **Repository access**: `Only select repositories` → `Joseph-mun/daily-news-agent` 선택
4. **Repository permissions**:
   - `Contents` → **Read and write** (필수 — push용)
   - `Metadata` → **Read-only** (자동 선택됨)
   - 나머지는 모두 **No access**
5. **Expiration**: 1 year (매년 갱신 권장) 또는 `No expiration`
6. **Generate token** 클릭 → 복사. 이 화면 떠나면 다시 못 봄.

PAT 스코프가 `Contents: Write`로만 제한돼 있어 유출 시에도 이 저장소 바깥으로는 확산 불가.

### Step 2 — GitHub repo에 Secrets 등록

1. https://github.com/Joseph-mun/daily-news-agent/settings/secrets/actions 접속
2. `New repository secret` 2개 추가:
   - **`TELEGRAM_BOT_TOKEN`** = `8237022848:AAHNqDZ-K16GqUMDV16B_m_b_Lz0njhL3Wg`
   - **`TELEGRAM_CHAT_ID`** = `1582270852`

이 값들은 Cowork 샌드박스 `.env` 에도 남겨두되, **GitHub Actions가 사용하는 건 repo secrets**. Cowork는 Telegram을 더 이상 직접 보내지 않음.

### Step 3 — Cowork 워크스페이스 `.env` 에 PAT 추가

Cowork 사이드바에서 `/sessions/.../01_dailynewsbot/.env` 열고 맨 아래에 추가:

```
# GitHub PAT (Contents: Read and write — daily-news-agent only)
# Issued: 2026-04-21, expires: 2027-04-21
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_OWNER=Joseph-mun
GITHUB_REPO=daily-news-agent
```

`.env`는 `.gitignore`에 등재돼 있어 commit 되지 않음 (확인: `grep '^\.env' .gitignore` → `.env` 존재).

### Step 4 — 레거시 워크플로 파일 삭제 (워크스페이스)

Cowork 워크스페이스 로컬에는 아직 `daily-news.yml`, `update-analysis.yml` 이 남아있음 (origin에선 이미 삭제됨). 다음 `git pull --rebase`가 자동으로 지워주지만, 명시적으로 없애려면:

```bash
cd /path/to/01_dailynewsbot
git fetch origin
git reset --hard origin/main   # 주의: 로컬 미푸시 커밋 있으면 먼저 백업
```

### Step 5 — 최초 배포 (오늘치 04-21 + 새 Actions 파일)

Cowork 샌드박스에서 푸시가 막혀있어 **처음 한 번만** 로컬 터미널 수동 푸시 필요:

```bash
cd /path/to/01_dailynewsbot
git fetch origin
git reset --hard origin/main

# Cowork가 생성한 오늘 DB + 새로 만든 Actions 파일을 로컬로 복사
#   (워크스페이스 경로가 로컬 경로와 같으면 이 단계 생략)
cp /sessions/vigilant-blissful-shannon/mnt/01_dailynewsbot/web/data/news.db web/data/news.db
cp /sessions/vigilant-blissful-shannon/mnt/01_dailynewsbot/scripts/post_briefing_telegram.py scripts/
cp /sessions/vigilant-blissful-shannon/mnt/01_dailynewsbot/.github/workflows/post-briefing.yml .github/workflows/

git add scripts/post_briefing_telegram.py \
        .github/workflows/post-briefing.yml \
        web/data/news.db \
        docs/AUTO_DEPLOY_SETUP.md \
        docs/prompts/briefing_prompt.md

git commit -m "feat: auto-deploy via Actions — delegate Telegram to GitHub (Cowork cannot reach api.telegram.org)

- scripts/post_briefing_telegram.py: reads today's daily_briefings + articles, sends 3-block Telegram
- .github/workflows/post-briefing.yml: triggered on push to web/data/news.db, runs the script
- docs/AUTO_DEPLOY_SETUP.md: one-time PAT + secrets setup
- briefing: 2026-04-21 (11 articles, 2948 char analysis)"

git push origin main
```

push 성공 시:
- Vercel이 2~3분 내 재빌드 → https://daily-news-agent-ten.vercel.app/daily/2026-04-21 공개
- Actions `post-briefing.yml` 자동 실행 → Telegram 3 블록 도착

### Step 6 — Actions 실행 검증

https://github.com/Joseph-mun/daily-news-agent/actions 접속 → `Post briefing to Telegram` 최신 run이 ✅ 녹색인지 확인.

실패 시 로그 열어서:
- `missing env: TELEGRAM_BOT_TOKEN` → Step 2 secrets 등록 재확인
- `HTTP 401 Unauthorized` → bot token 오타
- `HTTP 400 chat not found` → chat_id 오타

---

## 내일부터 (2026-04-22~) — 자동 동작

Cowork 스케줄이 매일 **08:10 KST** 자동 실행:

1. `git pull --rebase origin main`
2. 수집·요약·DB 쓰기
3. `git push https://$GITHUB_TOKEN@github.com/$GITHUB_OWNER/$GITHUB_REPO.git main`
4. Vercel 재빌드 (자동)
5. GitHub Actions `post-briefing.yml` 발동 → Telegram 전송 (자동)

**Joseph 쪽 수동 작업 없음**. 매일 아침 텔레그램 도착하면 정상.

---

## 아키텍처 결정 근거

### 왜 Cowork가 직접 Telegram 안 보내나?

Cowork 샌드박스 egress 프록시가 `api.telegram.org` 를 차단. 2026-04-21 스케줄 실행 시 `403 blocked-by-allowlist` 로 실패. 이 allowlist는 Anthropic 측 정책이라 사용자가 풀 수 없음 (organization admin이 추가 가능하지만, 전사 정책상 추가된다는 보장 없음).

Actions는 GitHub 서버에서 실행되므로 이 제약을 받지 않음.

### 왜 Cowork에서 `git push` 는 가능한가?

`github.com` 자체는 allowlist에 있고 git HTTPS 프로토콜로 접근 가능. PAT를 URL에 embedded 하면 `git push https://$TOKEN@github.com/.../...` 형태로 인증 됨.

### 왜 예전 Lambda/Actions 일원화(04-20)와 충돌 안 하나?

삭제한 `daily-news.yml` / `update-analysis.yml`은 **뉴스 수집·DB 커밋**을 수행해 Cowork와 같은 자원을 썼음 → 충돌.

새 `post-briefing.yml`은:
- `push` 트리거만 받음 (스케줄 없음)
- `permissions: contents: read` (쓰기 권한 없음)
- `git commit / git push` 안 함 — 순수 Telegram 전송
- Cowork의 일일 push에 반응만 하는 수동적(passive) 딜리버리

따라서 Cowork-only 원칙 유지. Actions는 '배달부' 역할만.

### 왜 PAT를 `.env`에? GitHub Secrets가 아닌가?

Secrets는 **GitHub Actions 런타임에서만** 읽힘. Cowork 샌드박스에서 `git push` 하려면 인증이 **샌드박스 로컬 파일**에 있어야 함. `.env` (gitignored, 600 perms)가 표준적 위치.

PAT 스코프가 `Contents: Write` + 단일 저장소로 제한돼 있어 blast radius가 작음. 유출 시 즉시 https://github.com/settings/personal-access-tokens 에서 revoke 후 재발급 + `.env` + secrets 교체.

---

## 향후 롤백

**Telegram만 끄고 싶다면**: `.github/workflows/post-briefing.yml` 의 `on:` 블록을 빈 `workflow_dispatch` 만 남기면 됨.

**전체 자동화 해제**: `.env`에서 `GITHUB_TOKEN` 삭제 → Cowork push 실패 → 아무것도 안 올라감. 복구는 PAT 재투입.

**PAT 만료**: GitHub에서 PAT 만료 알림 메일 수신 → 새로 발급 → `.env` 교체.

---

생성: 2026-04-21
관련: `docs/prompts/briefing_prompt.md` (v6.2+), `docs/DISABLE_LEGACY_AUTOMATION.md`, `docs/RECOVERY_20260420.md`
