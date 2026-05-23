#!/usr/bin/env python3
"""
SCP Wiki Article Info Extractor
================================
Extracts: Rating, Date of Creation, List of Tags
for any SCP Wiki URL (SCP, tale, GoI format, hub, etc.)

Usage:
    python scp_extractor.py https://scp-wiki.wikidot.com/scp-173
    python scp_extractor.py https://scp-wiki.wikidot.com/the-s-c-p-foundation

Requires:
    pip install requests beautifulsoup4
"""

import sys
import re
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# ─── Constants ───────────────────────────────────────────────────────────────

CROM_API = "https://api.crom.avn.sh/graphql"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_token() -> str:
    """Generate a random 8-char wikidot_token7 value."""
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(8))


def get_ajax_base(url: str) -> str:
    """Build the AJAX endpoint URL from the article URL."""
    # e.g. https://scp-wiki.wikidot.com → https://scp-wiki.wikidot.com/ajax-module-connector.php
    parts = url.split("/")
    base = "/".join(parts[:3])  # scheme + domain
    return base + "/ajax-module-connector.php"


# ─── Rating ──────────────────────────────────────────────────────────────────

def get_rating(soup: BeautifulSoup) -> int | None:
    """
    Extract the page rating from already-parsed HTML.

    Wikidot renders rating inside a <span id="prwXXXXX">+12345</span>.
    The id prefix 'prw' is stable even though the numeric suffix isn't.
    Fall back to .page-rate-widget-box .number if not found.
    """
    # Primary: span whose id starts with 'prw'
    for span in soup.find_all("span", id=re.compile(r"^prw\d+")):
        text = span.get_text(strip=True)
        try:
            return int(text.replace("+", ""))
        except ValueError:
            pass

    # Secondary: Wikidot rate widget box
    node = soup.select_one(".page-rate-widget-box .number")
    if node:
        try:
            return int(node.get_text(strip=True).replace("+", ""))
        except ValueError:
            pass

    # Tertiary: any span that looks like ±number
    for span in soup.find_all("span"):
        text = span.get_text(strip=True)
        if re.match(r"^[+-]\d+$", text):
            try:
                return int(text)
            except ValueError:
                pass

    return None


# ─── Tags ────────────────────────────────────────────────────────────────────

def get_tags(soup: BeautifulSoup) -> list[str]:
    """
    Extract page tags from already-parsed HTML.

    Wikidot renders tags in <div class="page-tags"><a>tag</a> ...</div>.
    """
    tags_div = soup.find("div", class_="page-tags")
    if not tags_div:
        return []
    return [a.get_text(strip=True) for a in tags_div.find_all("a")]


# ─── Creation Date via Crom API (primary) ────────────────────────────────────

def get_creation_date_crom(url: str) -> str | None:
    """
    Fetch creation date from the Crom GraphQL API.

    Crom (https://api.crom.avn.sh) is a community-maintained API that indexes
    the SCP Wiki, including accurate creation timestamps pulled from Wikidot.
    This is the cleanest and most reliable approach.

    Returns a date string like "26 Jul 2008", or None on failure.
    """
    query = """
    query GetPageInfo($url: URL!) {
      page(url: $url) {
        wikidotInfo {
          createdAt
        }
      }
    }
    """
    try:
        resp = requests.post(
            CROM_API,
            json={"query": query, "variables": {"url": url}},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Surface GraphQL-level errors
        if "errors" in data:
            print(f"  [Crom API] GraphQL errors: {data['errors']}", file=sys.stderr)
            return None

        page = (data.get("data") or {}).get("page")
        if not page:
            print(f"  [Crom API] Page not found in index.", file=sys.stderr)
            return None

        wikidot_info = page.get("wikidotInfo") or {}
        created_at = wikidot_info.get("createdAt")
        if not created_at:
            return None

        # ISO 8601 → readable date
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")

    except requests.exceptions.ConnectionError as e:
        print(f"  [Crom API] Cannot reach API (network/firewall?): {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [Crom API] Error: {e}", file=sys.stderr)
        return None


# ─── Creation Date via Wikidot AJAX (fallback) ───────────────────────────────

def get_page_id(soup: BeautifulSoup) -> int | None:
    """
    Extract the Wikidot page ID from an already-parsed page's inline JS.

    Wikidot always embeds:  WIKIREQUEST.info.pageId = 12345;
    """
    marker = "WIKIREQUEST.info.pageId = "
    for script in soup.find_all("script"):
        text = script.get_text()
        pos = text.find(marker)
        if pos == -1:
            continue
        pos += len(marker)
        end = text.find(";", pos)
        if end == -1:
            continue
        try:
            return int(text[pos:end].strip())
        except ValueError:
            pass
    return None


def get_creation_date_ajax(url: str, session: requests.Session, soup: BeautifulSoup) -> str | None:
    """
    Fetch creation date via the Wikidot AJAX history module.

    Key requirements (source of all previous failures):
      1. You must POST to /ajax-module-connector.php on the SAME domain.
      2. You must supply a random wikidot_token7 in BOTH the POST body AND cookies.
      3. You must use page_id (integer from page JS), NOT pageName.
      4. The oldest revision is on the LAST pagination page.

    Returns a date string like "26 Jul 2008", or None on failure.
    """
    page_id = get_page_id(soup)
    if page_id is None:
        print("  [AJAX] Could not find page_id in page JS.", file=sys.stderr)
        return None

    ajax_url = get_ajax_base(url)

    def fetch_history_page(page_num: int) -> BeautifulSoup | None:
            # Generate a fresh token each call and OVERWRITE the session cookie
            # so both the cookie jar and POST body carry the same value.
            # This is why "wrong_token7" happened before — the session cookie
            # set by Wikidot during the initial page.get() didn't match our
            # randomly generated token that we were only sending in the body.
            token = make_token()
            domain = ajax_url.split("/")[2]  # e.g. scp-wiki.wikidot.com
            session.cookies.set("wikidot_token7", token, domain=domain)

            payload = {
                "moduleName": "history/PageRevisionListModule",
                "page_id": str(page_id),
                "page": str(page_num),
                "perpage": "250",
                "options": '{"all":true}',
                "wikidot_token7": token,
            }
            try:
                r = session.post(ajax_url, data=payload, timeout=20)
                r.raise_for_status()
                data = r.json()
                if data.get("status") != "ok":
                    print(f"  [AJAX] Status: {data.get('status')}", file=sys.stderr)
                    return None
                return BeautifulSoup(data.get("body", ""), "html.parser")
            except Exception as e:
                print(f"  [AJAX] Request error: {e}", file=sys.stderr)
                return None

    # Page 1 — to discover total number of history pages
    body = fetch_history_page(1)
    if body is None:
        return None

    # Find the highest page number in the pager
    total_pages = 1
    pager = body.find("div", class_="pager")
    if pager:
        nums = [
            int(a.get_text(strip=True))
            for a in pager.find_all("a")
            if a.get_text(strip=True).isdigit()
        ]
        if nums:
            total_pages = max(nums)

    # If there are multiple pages, fetch the last one (oldest revisions)
    if total_pages > 1:
        body = fetch_history_page(total_pages)
        if body is None:
            return None

    # Find all rows that contain an .odate span
    rows = [tr for tr in body.find_all("tr") if tr.find("span", class_="odate")]
    if not rows:
        return None

    # The LAST row in the LAST page = oldest revision = creation
    last_row = rows[-1]
    span = last_row.find("span", class_="odate")
    if span:
        # Wikidot stores Unix timestamp in a class like "time_1217060621"
        for cls in span.get("class", []):
            if cls.startswith("time_"):
                try:
                    ts = int(cls[5:])
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    return dt.strftime("%d %b %Y")
                except ValueError:
                    pass
        # Fall back to text content of the span
        text = span.get_text(strip=True)
        if text:
            return text

    return None


# ─── Main Extractor ──────────────────────────────────────────────────────────

def extract_scp_info(url: str) -> dict:
    """
    Extract rating, creation date, and tags from any SCP Wiki URL.

    Strategy:
      - Rating  → parse from page HTML (always works)
      - Tags    → parse from page HTML (always works)
      - Created → Crom GraphQL API (primary, clean)
                → Wikidot AJAX module (fallback)
    """
    url = url.strip().rstrip("/")

    with requests.Session() as session:
        session.headers.update(HEADERS)

        # ── Fetch the article page ──────────────────────────────────────────
        print(f"  Fetching page HTML ...", file=sys.stderr)
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Could not fetch '{url}': {e}") from e

        soup = BeautifulSoup(resp.text, "html.parser")

        rating = get_rating(soup)
        tags = get_tags(soup)

        # ── Creation date: Crom first ───────────────────────────────────────
        print("  Querying Crom API for creation date ...", file=sys.stderr)
        creation_date = get_creation_date_crom(url)

        # ── Creation date: AJAX fallback ────────────────────────────────────
        if creation_date is None:
            print("  Crom unavailable — falling back to Wikidot AJAX ...", file=sys.stderr)
            creation_date = get_creation_date_ajax(url, session, soup)

    return {
        "url": url,
        "rating": rating,
        "creation_date": creation_date,
        "tags": tags,
    }


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python scp_extractor.py <url>")
        print("Example: python scp_extractor.py https://scp-wiki.wikidot.com/scp-173")
        sys.exit(1)

    url = sys.argv[1]
    print(f"\nExtracting info for: {url}\n", file=sys.stderr)

    try:
        result = extract_scp_info(url)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # ── Pretty output ───────────────────────────────────────────────────────
    sep = "=" * 55
    print(sep)
    print(f"  URL      : {result['url']}")
    print(f"  Rating   : {result['rating'] if result['rating'] is not None else 'N/A'}")
    print(f"  Created  : {result['creation_date'] or 'N/A'}")
    print(f"  Tags     : {', '.join(result['tags']) if result['tags'] else 'None'}")
    print(sep)


if __name__ == "__main__":
    main()
