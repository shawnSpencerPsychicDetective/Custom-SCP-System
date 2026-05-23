import sqlite3
import math

DB_NAME = "scp.db"


def compute_stats(values):
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance)
    return mean, std


def main():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Load clean data only
    c.execute("""
        SELECT link, rating, days_since_upload, is_joke
        FROM pages
        WHERE rating IS NOT NULL
          AND days_since_upload IS NOT NULL
    """)

    rows = c.fetchall()
    total = len(rows)

    print(f"Loaded {total} rows")

    # Extract columns
    ratings = [r[1] for r in rows]
    days = [r[2] for r in rows]

    # Compute stats
    rating_mean, rating_std = compute_stats(ratings)
    days_mean, days_std = compute_stats(days)

    print(f"\nRating mean/std: {rating_mean:.2f} / {rating_std:.2f}")
    print(f"Days mean/std  : {days_mean:.2f} / {days_std:.2f}")

    # Avoid division by zero (unlikely but safe)
    if rating_std == 0:
        rating_std = 1
    if days_std == 0:
        days_std = 1

    print("\nComputing scores...\n")

    for i, (link, rating, days_since, is_joke) in enumerate(rows, 1):

        rating_z = (rating - rating_mean) / rating_std
        days_z = (days_since - days_mean) / days_std

        score = rating_z - days_z

        c.execute("""
            UPDATE pages
            SET score = ?
            WHERE link = ?
        """, (score, link))

        if i % 1000 == 0:
            conn.commit()
            print(f"[{i}/{total}] updated...")

    conn.commit()
    conn.close()

    print("\nDone. Scores computed.")


if __name__ == "__main__":
    main()