import requests
from bs4 import BeautifulSoup
import sqlite3
import time

BASE = "https://scp-wiki.wikidot.com"
DB_NAME = "scp.db"

TOTAL_PAGES = 477  # you observed this

EXCLUDE_PREFIXES = [
    "fragment:",
    "archived:",
    "unlisted:",
    "workbench:"
]


def is_valid(href):
    if not href:
        return False

    if not href.startswith("/"):
        return False

    # remove leading slash
    page = href[1:]

    for prefix in EXCLUDE_PREFIXES:
        if page.startswith(prefix):
            return False

    return True


def get_links(page_num):
    url = f"{BASE}/system:list-all-pages/p/{page_num}"

    res = requests.get(url)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    links = set()

    # this page structure is simple: all links are in <a>
    for a in soup.find_all("a"):
        href = a.get("href")

        if is_valid(href):
            full = BASE + href
            links.add(full)

    return links


def save_links_batch(links):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.executemany("""
        INSERT OR IGNORE INTO pages (link)
        VALUES (?)
    """, [(link,) for link in links])

    conn.commit()
    conn.close()


def main():
    total_links = 0

    for i in range(1, TOTAL_PAGES + 1):
        print(f"Scraping page {i}/{TOTAL_PAGES}...")

        links = get_links(i)
        total_links += len(links)

        save_links_batch(links)

        print(f"  Found: {len(links)} | Total collected: {total_links}")

        time.sleep(0.2)  # polite but fast

    print("\nDone.")


if __name__ == "__main__":
    main()