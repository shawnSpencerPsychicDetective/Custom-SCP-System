import sqlite3

DB_NAME = "scp.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        link TEXT PRIMARY KEY,
        rating INTEGER,
        created_at TEXT,
        days_since_upload INTEGER,
        is_joke INTEGER,
        score REAL,
        last_checked TEXT,
        have_read INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()
    print("Database initialized.")

if __name__ == "__main__":
    init_db()