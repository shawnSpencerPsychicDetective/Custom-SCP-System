import sqlite3
from datetime import datetime, timezone

DB_NAME = "scp.db"


def compute_days_since(date_str):
    try:
        if not date_str:
            return None

        # Remove time if present
        date_str = date_str.split(",")[0].strip()

        dt = datetime.strptime(date_str, "%d %b %Y")
        dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return (now - dt).days

    except Exception:
        return None


def main():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Only rows that actually have a creation date
    c.execute("""
        SELECT link, created_at
        FROM pages
        WHERE created_at IS NOT NULL
    """)

    rows = c.fetchall()
    total = len(rows)

    print(f"Recomputing days_since_upload for {total} pages...\n")

    for i, (link, created) in enumerate(rows, 1):
        days = compute_days_since(created)

        c.execute("""
            UPDATE pages
            SET days_since_upload = ?
            WHERE link = ?
        """, (days, link))

        if i % 500 == 0:
            conn.commit()
            print(f"[{i}/{total}] updated...")

    conn.commit()
    conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()