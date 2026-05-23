import sqlite3
import time
from datetime import datetime, timezone
import random

# --- CONFIG ---
DB_NAME = "scp.db"
DELAY = 0.2  # seconds between requests

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# --- IMPORT YOUR EXTRACTION FUNCTIONS ---
# Paste your Claude extractor functions here OR import them
from scp_extractor import extract_scp_info


from datetime import datetime, timezone


def compute_days_since(date_str):
    try:
        if not date_str:
            return None

        # Remove time if present (everything after comma)
        date_str = date_str.split(",")[0].strip()

        dt = datetime.strptime(date_str, "%d %b %Y")
        dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return (now - dt).days

    except Exception:
        return None


def is_joke(tags):
    return 1 if "joke" in tags else 0


def update_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Only process rows not yet filled
    c.execute("""
        SELECT link FROM pages
        WHERE rating IS NULL
    """)

    rows = c.fetchall()
    total = len(rows)

    print(f"Updating {total} pages...\n")

    for i, (link,) in enumerate(rows, 1):
        try:
            data = extract_scp_info(link)

            rating = data["rating"]
            created = data["creation_date"]
            tags = data["tags"]

            days = compute_days_since(created) if created else None
            joke = is_joke(tags)

            now = datetime.now(timezone.utc).isoformat()

            c.execute("""
                UPDATE pages
                SET rating = ?,
                    created_at = ?,
                    days_since_upload = ?,
                    is_joke = ?,
                    last_checked = ?
                WHERE link = ?
            """, (rating, created, days, joke, now, link))

            conn.commit()

            print(f"[{i}/{total}] Updated")

        except Exception as e:
            print(f"[{i}/{total}] ERROR: {link} → {e}")

        time.sleep(DELAY + random.uniform(0, 0.3))

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    update_db()