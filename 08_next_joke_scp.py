import sqlite3
import webbrowser

DB_NAME = "scp.db"


def get_next_scp():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT link, score
        FROM pages
        WHERE have_read = 0 AND is_joke = 1
        ORDER BY (score * ABS(RANDOM())) DESC
        LIMIT 1
    """)

    row = c.fetchone()
    conn.close()

    return row


def mark_as_read(link):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        UPDATE pages
        SET have_read = 1
        WHERE link = ?
    """, (link,))

    conn.commit()
    conn.close()


def main():
    row = get_next_scp()

    if not row:
        print("No unread SCPs left.")
        return

    link, score = row

    print("\n=== YOUR NEXT SCP ===")
    print(f"Link : {link}")
    print(f"Score: {score:.3f}\n")

    # open in browser
    webbrowser.open(link)

    # ask user what to do
    choice = input("Mark as read? (y/n): ").strip().lower()

    if choice == "y":
        mark_as_read(link)
        print("Marked as read.")
    else:
        print("Left as unread.")


if __name__ == "__main__":
    main()