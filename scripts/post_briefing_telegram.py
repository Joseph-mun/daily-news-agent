#!/usr/bin/env python3
"""
Post today's briefing to Telegram.

Triggered by GitHub Actions on push to web/data/news.db.
Runs on GitHub infra (unrestricted internet), so api.telegram.org is reachable —
unlike the Cowork sandbox, which is allowlist-blocked.

Responsibilities (minimal — delivery only):
- Read daily_briefings row for today's KST date from web/data/news.db.
- If no row for today, exit 0 (nothing to deliver — this is a non-briefing push).
- Build 3 Telegram blocks (article list, 종합요약, Vercel link).
- Convert markdown bold (**...**) to Telegram HTML (<b>...</b>), escape HTML-sensitive chars.
- Split into ≤4000 char chunks and send sequentially.

Env:
- TELEGRAM_BOT_TOKEN  (GitHub secret)
- TELEGRAM_CHAT_ID    (GitHub secret)
- VERCEL_DOMAIN       (optional, defaults to daily-news-agent-ten.vercel.app)
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re
import sqlite3
import sys
import time

import requests

DB_PATH = "web/data/news.db"
KST = dt.timezone(dt.timedelta(hours=9))
CHUNK = 4000
API_BASE = "https://api.telegram.org"
VERCEL_DOMAIN = os.environ.get("VERCEL_DOMAIN", "daily-news-agent-ten.vercel.app")


def get_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"[ERROR] missing env: {name}", file=sys.stderr)
        sys.exit(1)
    return v


def md_to_html(text: str) -> str:
    """Convert a minimal markdown subset to Telegram HTML parse_mode.

    Rules:
    - Escape HTML-sensitive chars first (&, <, >) globally.
    - **x** -> <b>x</b>
    - `x`   -> <code>x</code>
    - URLs are left bare (Telegram auto-links with disable_web_page_preview=true).
    - [N] citations stay as-is (plain text).
    - Headings (### x) kept, surrounded with <b></b> to stay visible.
    """
    text = html.escape(text, quote=False)

    # ### Heading → bold heading line
    text = re.sub(r"(?m)^###\s*(.+?)\s*$", r"<b>\1</b>", text)

    # **bold** (non-greedy, single line)
    text = re.sub(r"\*\*([^\n*]+?)\*\*", r"<b>\1</b>", text)

    # `code` (inline)
    text = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", text)

    return text


def chunks(s: str, n: int = CHUNK):
    """Split `s` into chunks of up to `n` chars, preferring paragraph/line boundaries."""
    if len(s) <= n:
        yield s
        return
    while s:
        if len(s) <= n:
            yield s
            return
        # Try to split at the last blank line before n
        cut = s.rfind("\n\n", 0, n)
        if cut < n // 2:
            cut = s.rfind("\n", 0, n)
        if cut < n // 2:
            cut = n
        yield s[:cut]
        s = s[cut:].lstrip("\n")


def send(token: str, chat_id: str, text: str) -> None:
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(1, 4):
        try:
            r = requests.post(url, data=payload, timeout=30)
            if r.ok:
                return
            print(f"[WARN] Telegram send attempt {attempt} failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"[WARN] Telegram send attempt {attempt} exception: {e}", file=sys.stderr)
        time.sleep(2 * attempt)
    print("[ERROR] Telegram send failed after 3 attempts", file=sys.stderr)
    sys.exit(2)


def build_article_block(date: str, articles: list[tuple]) -> str:
    lines = [f"<b>📰 {date} 보안 브리핑 — {len(articles)}건</b>", ""]
    for i, (title, summary, url) in enumerate(articles, 1):
        lines.append(f"<b>{i}. {html.escape(title)}</b>")
        if summary:
            lines.append(html.escape(summary))
        lines.append(f"🔗 {html.escape(url)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_link_block(date: str) -> str:
    return f"🌐 <b>전체 브리핑 보기</b>\nhttps://{VERCEL_DOMAIN}/daily/{date}"


def main() -> int:
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")

    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    print(f"[INFO] Target date: {today} KST")

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB not found: {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    row = cur.execute(
        "SELECT analysis FROM daily_briefings WHERE date=?", (today,)
    ).fetchone()
    if not row:
        print(f"[INFO] No daily_briefings row for {today} — nothing to deliver")
        return 0

    analysis = row[0] or ""
    articles = cur.execute(
        "SELECT title, summary, url FROM articles WHERE date=? ORDER BY id",
        (today,),
    ).fetchall()
    conn.close()

    if not articles:
        print(f"[WARN] Briefing row exists for {today} but no articles — skip")
        return 0

    print(f"[INFO] Found {len(articles)} articles, analysis {len(analysis)} chars")

    # Block 1 — article list
    block1 = build_article_block(today, articles)
    for c in chunks(block1):
        send(token, chat_id, c)

    # Block 2 — 종합요약 (markdown → HTML)
    block2 = md_to_html(analysis)
    for c in chunks(block2):
        send(token, chat_id, c)

    # Block 3 — Vercel link
    send(token, chat_id, build_link_block(today))

    print("[OK] Telegram delivery complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
