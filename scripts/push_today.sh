#!/usr/bin/env bash
# push_today.sh — 2026-04-21 auto-deploy 구성 + 오늘자 브리핑 DB push
# 실행: bash scripts/push_today.sh
# iCloud 폴더에서 직접 돌리는 플로우 (별도 로컬 clone 없을 때)

set -euo pipefail

# 안전망: 반드시 저장소 루트에서 실행되도록 cd
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
echo "[i] repo root: $REPO_ROOT"

# 0) stale lock / journal 정리
echo "[0] cleaning stale git locks and sqlite journal"
rm -f .git/index.lock .git/HEAD.lock web/data/news.db-journal

# 현재 상태 기록
echo "[i] current git status (before):"
git status --short | head -40 || true
echo "[i] ahead/behind:"
git rev-list --left-right --count HEAD...origin/main 2>/dev/null || git fetch origin && git rev-list --left-right --count HEAD...origin/main

# 1) 커밋할 파일을 먼저 stash로 빼둠 (rebase 중 덮어쓰기 방지)
echo "[1] stashing pending briefing outputs"
STASH_PATHS=(
  web/data/news.db
  scripts/post_briefing_telegram.py
  .github/workflows/post-briefing.yml
  docs/AUTO_DEPLOY_SETUP.md
  docs/prompts/briefing_prompt.md
)

# 존재하는 파일만 스태시 대상에 포함
EXISTING_PATHS=()
for p in "${STASH_PATHS[@]}"; do
  if [ -e "$p" ]; then
    EXISTING_PATHS+=("$p")
  else
    echo "[!] skip (missing): $p"
  fi
done

if [ ${#EXISTING_PATHS[@]} -eq 0 ]; then
  echo "[x] no files to commit. aborting."
  exit 1
fi

git stash push -u -m "push_today-$(date +%Y%m%d-%H%M%S)" -- "${EXISTING_PATHS[@]}"

# 2) origin/main과 정렬
echo "[2] fetching origin and rebasing local branch onto origin/main"
git fetch origin

# 로컬이 ahead/behind 혼재면 rebase 시도
if ! git pull --rebase origin main; then
  echo "[x] rebase 충돌 발생. 중단하고 stash 되돌립니다."
  git rebase --abort || true
  git stash pop || true
  echo "[!] 수동 해결 필요. 충돌 내용을 확인한 뒤 다시 시도하세요."
  exit 2
fi

# 3) stash 복구
echo "[3] re-applying stashed files"
git stash pop

# 4) 커밋할 파일만 정확히 스테이징
echo "[4] staging files"
for p in "${EXISTING_PATHS[@]}"; do
  git add "$p"
done

# 커밋할 게 있는지 확인
if git diff --cached --quiet; then
  echo "[!] nothing staged — skipping commit/push"
  exit 0
fi

# 5) 커밋 (괄호 포함 메시지는 here-doc 안전 버전 사용)
echo "[5] committing"
COMMIT_MSG=$(cat <<'COMMIT_EOF'
feat: auto-deploy via Actions + briefing 2026-04-21 (11 articles)

- Add scripts/post_briefing_telegram.py for post-commit Telegram delivery
- Add .github/workflows/post-briefing.yml to auto-send on push
- Add docs/AUTO_DEPLOY_SETUP.md with setup notes
- Update docs/prompts/briefing_prompt.md to v6.2 readability format
- Update web/data/news.db with 2026-04-21 briefing
COMMIT_EOF
)
git commit -m "$COMMIT_MSG"

# 6) push
echo "[6] pushing to origin/main"
git push origin main

echo "[OK] done. Vercel should start rebuild shortly."
echo "[i] 확인: https://daily-news-agent-ten.vercel.app/daily/$(date +%Y-%m-%d)"
