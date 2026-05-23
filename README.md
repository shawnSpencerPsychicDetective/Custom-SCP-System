# SCP Wiki Local Reader

A personal project to build a local, searchable database of every article on the SCP Wiki, then rank them by both **rating** and **recency** so I can read the best new content first.

> The SCP Foundation is a fictional organization featured in stories created by contributors on the SCP Wiki, a wiki-based collaborative writing project launched in 2008. Within the project's shared universe, the SCP Foundation is a secret organization responsible for capturing, containing, and studying various paranormal, supernatural, and other mysterious phenomena (known as "anomalies" or "SCPs"), while keeping their existence hidden from society.

I am a fan, and I wanted a way to surface good, recent articles without scrolling through thousands of pages manually. This toolchain scrapes, stores, scores, and serves SCP articles locally.

---

## How it works

The core idea is simple: high rating is good, newness is good. We combine both using z-scores.

**Score = z(rating) - z(days_since_upload)**

- `z(rating) = (rating - mean_rating) / std_rating`
- `z(days) = (days_since_upload - mean_days) / std_days`

Subtracting the days z-score means newer articles (fewer days) get a boost. The result ranks articles that are both well-liked *and* fresh.

The database also tracks whether you've read an article, and whether it's a joke SCP.

---

## Project structure

| File | Purpose |
| --- | --- |
| **01_init_db.py** | Creates `scp.db` with the `pages` table. |
| **02_discover_all_pages.py** | Crawls `https://scp-wiki.wikidot.com/system:list-all-pages` (477 pages) and inserts every valid link into the database. Filters out `fragment:`, `archived:`, `unlisted:`, `workbench:` namespaces. |
| **03_scp_extractor.py** | Standalone extractor. Given a URL, it returns rating, creation date, and tags. Uses Crom GraphQL API as primary source for creation date, falls back to Wikidot AJAX history module with proper `wikidot_token7` handling. |
| **04_update_database.py** | Loops through all links with `rating IS NULL`, calls the extractor, and fills `rating`, `created_at`, `days_since_upload`, `is_joke`, `last_checked`. |
| **05_recompute_days.py** | Recomputes `days_since_upload` for all entries. Needed because step 04 can take over 24 hours, making earlier day counts stale. |
| **06_compute_scores.py** | Calculates mean and standard deviation for ratings and days, then computes the final score for each article. |
| **07_next_scp.py** | Picks your next unread article, weighted by score (`ORDER BY score * ABS(RANDOM()) DESC`), opens it in browser, and optionally marks as read. |
| **08_next_joke_scp.py** | Same as above, but filtered to only articles tagged `joke`. |

---

## Database schema

`scp.db` → table `pages`

```sql
CREATE TABLE pages (
    link TEXT PRIMARY KEY,
    rating INTEGER,
    created_at TEXT,           -- e.g. "26 Jul 2008"
    days_since_upload INTEGER,
    is_joke INTEGER,           -- 1 if tagged 'joke', else 0
    score REAL,
    last_checked TEXT,
    have_read INTEGER DEFAULT 0
);
```

---

## Installation

```bash
git clone <your-repo>
cd scp-reader
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install requests beautifulsoup4
```

Python 3.9+ recommended.

---

## Usage

Run in order. The first full run takes a long time.

1. **Initialize**
   ```bash
   python 01_init_db.py
   ```

2. **Discover all pages** (~5 minutes)
   ```bash
   python 02_discover_all_pages.py
   ```

3. **Extract metadata** (this is the slow part - thousands of HTTP requests)
   ```bash
   python 04_update_database.py
   ```
   > Uses `03_scp_extractor.py` internally. Expect 0.2-0.5s per page. Run overnight.

4. **Fix day counts**
   ```bash
   python 05_recompute_days.py
   ```

5. **Compute scores**
   ```bash
   python 06_compute_scores.py
   ```

6. **Read**
   ```bash
   python 07_next_scp.py
   # or for jokes only
   python 08_next_joke_scp.py
   ```

Each run opens the top-weighted unread article in your default browser. Answer `y` to mark as read, `n` to keep it in the pool.

---

## Why this approach

- **Local first**: No API keys, no rate-limited official API. Everything lives in SQLite.
- **Accurate dates**: Wikidot doesn't show creation dates in HTML. I use Crom (community GraphQL) first, then fall back to parsing the full revision history via AJAX with correct token handling.
- **Recency matters**: SCP-173 has +2000 rating but is from 2008. I want to find the next SCP-173, not re-read the old one. Z-score balancing prevents old classics from dominating forever.
- **Joke separation**: Joke SCPs are great but have a different tone. `08_next_joke_scp.py` keeps them in their own queue.

---

## Limitations

- Wikidot blocks aggressive scraping. The scripts sleep 0.2-0.5s between requests. Be polite.
- Crom API coverage is ~99% but not perfect; fallback handles the rest.
- Ratings change over time. Re-run steps 4-6 monthly to refresh.
- Only the English SCP Wiki (`scp-wiki.wikidot.com`) is supported.

---

## Future ideas

- Add tag-based filtering (`python next_scp.py --tag keter`)
- Web UI instead of CLI
- Export top 100 to markdown reading list
- Track reading streaks

---

## License

Personal use only. SCP Wiki content is licensed under CC BY-SA 3.0. This code is MIT (or do what you want - it's a spare-time project).
