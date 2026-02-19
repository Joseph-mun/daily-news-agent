"""
수동 분석 리포트를 news.db에 업데이트하는 스크립트.
GitHub Actions에서 repository_dispatch 이벤트로 호출됩니다.

Usage:
    python update_analysis.py <date> <analysis_text>
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def main():
    if len(sys.argv) < 3:
        print("Usage: python update_analysis.py <YYYY-MM-DD> <analysis_text>")
        sys.exit(1)

    date_str = sys.argv[1]
    analysis = sys.argv[2]

    db_path = Path(__file__).parent / "web" / "data" / "news.db"

    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)

    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if briefing exists for this date
    cursor.execute("SELECT date FROM daily_briefings WHERE date = ?", (date_str,))
    row = cursor.fetchone()

    if row:
        cursor.execute(
            "UPDATE daily_briefings SET analysis = ?, created_at = ? WHERE date = ?",
            (analysis, now_iso, date_str)
        )
        print(f"Updated analysis for {date_str}")
    else:
        cursor.execute(
            "INSERT INTO daily_briefings (date, analysis, created_at) VALUES (?, ?, ?)",
            (date_str, analysis, now_iso)
        )
        print(f"Inserted analysis for {date_str}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
