# CLAUDE.md

## Project Overview

Python tool that extracts reader comments from a single book (work) on **author.today**, parses them into a clean structure, and saves them as JSON (raw, nested) and CSV (flat) for later analysis. Analysis goals are not fixed yet, so prioritize **capturing complete raw data** over premature aggregation — we can always reprocess raw JSON, but we can't re-scrape deleted comments.

One book per run. The work is identified by its numeric ID from the URL: `https://author.today/work/{work_id}`.

## Tech Stack

- Python 3.11+
- `httpx` (or `requests`) for HTTP, `beautifulsoup4` + `lxml` for HTML parsing
- `pandas` only at the export/flatten step
- `pytest` for tests
- Dependency management: `uv` (or pip + `requirements.txt`)

## Commands

```bash
uv sync                                  # install deps
python -m atscraper --work-id 123456     # scrape one book
python -m atscraper --work-id 123456 --from-cache   # re-parse cached raw responses without hitting the site
pytest                                   # run tests (use cached fixtures, never live HTTP)
ruff check . && ruff format .            # lint / format
```

## Project Structure

```
atscraper/
  __main__.py      # CLI entry point (argparse)
  client.py        # HTTP session: headers, cookies/CSRF, rate limiting, retries
  fetcher.py       # downloads comment pages for a work, saves raw responses
  parser.py        # raw HTML/JSON -> Comment dataclasses (pure functions, no I/O)
  exporter.py      # writes comments.json and comments.csv
  models.py        # Comment, Work dataclasses
data/
  raw/{work_id}/         # untouched raw responses (one file per request) — never edit
  processed/{work_id}/   # comments.json, comments.csv, work_meta.json
tests/
  fixtures/              # saved sample responses for parser tests
```

`data/` is in `.gitignore`. Raw and processed are strictly separated: `fetcher` only writes to `raw/`, `parser`/`exporter` only read `raw/` and write to `processed/`.

## Site-Specific Notes (author.today)

- Comments are **not in the initial HTML** — they load dynamically via the endpoints below.

### Confirmed comment API (verified live 2026-06-11, work 170886)

**Endpoint 1 — paginated comment list:**

```
GET https://author.today/comment/load?rootId={work_id}&rootType=1&page={n}[&sorting=...]
```

- `rootType=1` = Work (same endpoint serves posts/profiles with other root types).
- Returns JSON: `{isSuccessful, isWarning, messages, data: {html, totalCount, lastViewTime, subscriptionId}}`.
- `data.html` is an HTML fragment: a `.pagination-container` block (links carry `page=N&sorting=reverse`; default sorting is `reverse`) plus the comment tree. ~32–35 comments per page; read the last page number from the pagination block and use `data.totalCount` as the site-reported total for cross-checking.
- **Works anonymously**: verified to return 200/JSON with no cookies and no CSRF token. The site's own JS sends a `RequestVerificationToken` header (value from the hidden `__RequestVerificationToken` input on the work page); `client.py` should still bootstrap the work page and send cookies + token to stay close to browser behavior.

**Endpoint 2 — collapsed reply branches:**

```
GET https://author.today/comment/loadThread?parentId={comment_id}&rootId={work_id}&rootType=1
```

- Page fragments inline only reply levels 0–1; deeper branches are collapsed (`div.comment-wrapper.collapsed-replies`, expand button calls `AppUtils.Comment.expand(this, parentId, rootId, 'Work')`).
- Returns the missing sub-tree (levels ≥ 2) as `data.html`; returns empty `html` if the branch is already inline. The fetcher must call this once per collapsed branch (~6 per page on the sample work).

**Comment markup (for the parser):**

- `div.comment` carries `data-id`, `data-level`, `data-thread` (thread-root id), `data-is-ignored`, `data-is-pinned`.
- Author: `a[href^="/u/"]` (profile slug) + `span.comment-user-name` (display name).
- Timestamp: `time span[data-time]` holds an **absolute ISO-8601 UTC** value (e.g. `2026-06-08T10:33:58.5309710Z`).
- Rating: `.comment-rating-count` text (e.g. `+3`) and its `data-hint` with separate 👍/👎 counts.
- Body: `article .rich-content` (HTML).
- Parent linkage: derive `parent_id` from DOM nesting inside `.replies` containers, combined with `data-level`.

Sample responses are saved in `tests/fixtures/` (page-1 fragment, loadThread fragment, work page).

### Other notes

- Comments are **threaded**: replies reference a parent comment. Preserve `parent_id` and thread structure in JSON; flatten with a `parent_id` column in CSV.
- Comments are **paginated**. Loop until an empty/short page; log page count.
- Text is Russian/Cyrillic: always read and write **UTF-8**. CSV must be written with `encoding="utf-8-sig"` so Excel opens it correctly.
- Timestamps: the `data-time` attribute is already absolute ISO-8601 UTC, so use it for `created_at` and store it as `created_at_raw` too. If the attribute is ever missing, fall back to whatever raw string is present and leave `created_at` null rather than guessing.
- Comment text may contain HTML (quotes, spoiler tags, images, emoji). Store both `text_html` (raw) and `text` (cleaned plain text).
- Deleted/hidden comments may appear as stubs — keep them with a `is_deleted` flag instead of skipping, so thread structure stays intact.

## Scraping Etiquette (non-negotiable)

- Minimum 1–2 s delay between requests, plus jitter; exponential backoff on 429/5xx.
- Single concurrent connection. No parallel fetching.
- Honest, identifiable User-Agent.
- Cache every raw response so re-runs and parser changes never require re-fetching (`--from-cache`).
- Personal/research use only; do not bypass authentication or paywalled content.

## Data Schema

`Comment` fields (keep stable — downstream analysis depends on it):

| field | type | notes |
|---|---|---|
| comment_id | str | site's ID |
| parent_id | str \| null | null for top-level |
| work_id | str | |
| author_name | str | display name |
| author_id | str \| null | profile ID if available |
| created_at_raw | str | exactly as shown on site |
| created_at | str \| null | ISO-8601 UTC if parseable |
| text | str | plain text |
| text_html | str | original HTML |
| likes | int \| null | |
| is_deleted | bool | |
| is_author | bool | comment by the book's author |
| page | int | pagination page it came from |
| scraped_at | str | ISO-8601 UTC |

`work_meta.json`: work_id, title, author, url, total_comments_reported, scraped_at, scraper_version.

## Conventions

- Parser functions are pure (bytes/str in, dataclasses out) and fully covered by tests against `tests/fixtures/` — never make live HTTP calls in tests.
- Fail loudly: if the page structure changes and a required field can't be parsed, raise with a saved copy of the offending response; don't silently emit partial rows.
- Log to stderr: pages fetched, comments parsed, comments written, mismatches vs the count reported by the site.
- Type hints everywhere; `ruff` clean before committing.
- Idempotent runs: re-running on the same work_id overwrites `processed/` but appends nothing to `raw/` unless content changed.

## Out of Scope (for now)

- Multi-work / bulk scraping, scheduling, databases.
- Any analysis (sentiment, stats) — keep exports analysis-agnostic.