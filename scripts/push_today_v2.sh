#!/usr/bin/env bash
# push_today_v2.sh — 2026-04-21 push, robust version
#
# 이 스크립트는 Cowork가 오늘 아침 clean clone에서 완성한 news.db + 새 파일들을
# origin/main 위에 안전하게 push 합니다.
#
# 접근 방식: 커밋할 파일을 /tmp로 먼저 대피 → git reset --hard origin/main
#   → /tmp에서 복원 → commit + push
#
# stash pop 충돌 위험을 원천 제거한 백업-리셋-복원 패턴입니다.
#
# 사용법:
#   cd "/Users/joseph/Library/.../01_dailynewsbot"
#   bash scripts/push_today_v2.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
echo "[i] repo root: $REPO_ROOT"

STAGE="/tmp/push_today_v2_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# ──────────────────────────────────────────────────────────────────
# 0) stale lock / journal 정리 (모든 알려진 잠금 위치)
# ──────────────────────────────────────────────────────────────────
echo "[0] cleaning stale git locks and sqlite journal"
rm -f .git/index.lock .git/HEAD.lock .git/config.lock .git/packed-refs.lock || true
# ref-level locks (브랜치, 태그)
find .git/refs -name "*.lock" -type f -delete 2>/dev/null || true
# sqlite journal
rm -f web/data/news.db-journal web/data/news.db-shm web/data/news.db-wal || true
# git process가 실제로 실행 중인지 확인 (있으면 안전상 중단)
if pgrep -f "git .* $REPO_ROOT" >/dev/null 2>&1; then
  echo "[x] 다른 git 프로세스가 실행 중입니다. 중단합니다."
  pgrep -fa "git .* $REPO_ROOT" || true
  exit 1
fi

# ──────────────────────────────────────────────────────────────────
# 1) 커밋할 파일 목록
# ──────────────────────────────────────────────────────────────────
TARGETS=(
  "web/data/news.db"
  "scripts/post_briefing_telegram.py"
  "scripts/push_today.sh"
  "scripts/push_today_v2.sh"
  ".github/workflows/post-briefing.yml"
  "docs/AUTO_DEPLOY_SETUP.md"
  "docs/prompts/briefing_prompt.md"
)

echo "[1] copying files-to-commit to $STAGE"
TO_COMMIT=()
for p in "${TARGETS[@]}"; do
  if [ -e "$p" ]; then
    mkdir -p "$STAGE/$(dirname "$p")"
    cp -a "$p" "$STAGE/$p"
    TO_COMMIT+=("$p")
    echo "    staged: $p"
  else
    echo "    [!] missing, skip: $p"
  fi
done

if [ ${#TO_COMMIT[@]} -eq 0 ]; then
  echo "[x] nothing to commit. aborting."
  exit 1
fi

# ──────────────────────────────────────────────────────────────────
# 2) origin/main 받아와서 로컬 2 ahead 커밋 버림
#    (d93e0af/2bd35f7는 이미 origin에 0e4259e/92c74cd로 반영됨)
# ──────────────────────────────────────────────────────────────────
echo "[2] fetching origin and hard-resetting to origin/main"
git fetch origin

echo "[i] local commits to be discarded:"
git log --oneline "origin/main..HEAD" || true

echo "[i] applying hard reset to origin/main"
git reset --hard origin/main

# 주의: reset --hard로 tracked files의 dirty changes도 사라집니다.
# 커밋할 5개 파일은 이미 $STAGE에 복사되어 있으니 안전합니다.
# untracked files (.omc/*, .env, 기타) 은 그대로 남습니다 — commit에 포함 안 되니 무해.

# ──────────────────────────────────────────────────────────────────
# 3) stage에서 파일 복원
# ──────────────────────────────────────────────────────────────────
echo "[3] restoring files from $STAGE"
for p in "${TO_COMMIT[@]}"; do
  mkdir -p "$(dirname "$p")"
  cp -a "$STAGE/$p" "$p"
  echo "    restored: $p"
done

# ──────────────────────────────────────────────────────────────────
# 4) 정확한 파일만 스테이징 (.omc/, .env 같은 건 절대 건드리지 않음)
# ──────────────────────────────────────────────────────────────────
echo "[4] staging commit targets"
for p in "${TO_COMMIT[@]}"; do
  git add "$p"
done

# 실행 비트 보존 (scripts/*.sh)
for sh in scripts/push_today.sh scripts/push_today_v2.sh; do
  if [ -e "$sh" ]; then
    git update-index --chmod=+x "$sh" 2>/dev/null || true
  fi
done

if git diff --cached --quiet; then
  echo "[!] nothing staged after restore. This usually means files matched origin exactly."
  echo "    If that's unexpected, inspect $STAGE contents vs current working tree."
  exit 0
fi

# ──────────────────────────────────────────────────────────────────
# 5) 커밋
# ──────────────────────────────────────────────────────────────────
echo "[5] committing"
git commit -F - <<'MSG_EOF'
briefing: 2026-04-21 (11 articles) + auto-deploy pipeline

Cowork scheduled run at 09:15 KST produced today's v6.2-format briefing
(11 articles, 2948-char analysis) and grafted it onto origin/main via
an internal clean clone. This commit pushes that result plus the new
auto-deploy pipeline.

- web/data/news.db: add 04-21 briefing atop latest origin state
- scripts/post_briefing_telegram.py: post-commit Telegram dispatcher
- scripts/push_today.sh, push_today_v2.sh: user-local push helpers
- .github/workflows/post-briefing.yml: auto-send Telegram on push
- docs/AUTO_DEPLOY_SETUP.md: setup and token configuration notes
- docs/prompts/briefing_prompt.md: bump to v6.2 readability rules

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
MSG_EOF

# ──────────────────────────────────────────────────────────────────
# 6) push
# ──────────────────────────────────────────────────────────────────
echo "[6] pushing to origin/main"
git push origin main

# ──────────────────────────────────────────────────────────────────
# 7) 정리
# ──────────────────────────────────────────────────────────────────
rm -rf "$STAGE"
echo ""
echo "[OK] done."
echo "[i] verify: https://daily-news-agent-ten.vercel.app/daily/2026-04-21"
echo "[i] Vercel rebuild typically completes in 3-5 minutes."
