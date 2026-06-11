# at-comment-analysis

Scraper and analysis toolkit for reader comments on [author.today](https://author.today) works.
Downloads every comment of a single book (one work per run), preserves the full thread
structure, and exports clean JSON/CSV for later analysis.

Built around a simple principle: **capture complete raw data first, analyze later** —
raw responses are cached forever, so parser changes never require re-scraping
(and deleted comments can't be re-scraped anyway).

## Features

- Uses the site's own comment API (verified live):
  `GET /comment/load` for paginated comment pages and `GET /comment/loadThread`
  for collapsed reply branches — including recursively nested ones.
- **Threaded structure preserved**: every comment keeps its `parent_id`;
  JSON export is a nested tree, CSV is flat with a `parent_id` column.
- **Raw-response cache**: every HTTP response is stored under `data/raw/{work_id}/`.
  Interrupted runs resume for free; `--from-cache` re-parses without touching the site.
- **Deleted comments kept as stubs** (`is_deleted` flag) so threads stay intact.
- Timestamps come from the site's absolute UTC values (`data-time` attribute) —
  no fuzzy "2 часа назад" parsing.
- CSV written as `utf-8-sig`, so Cyrillic opens correctly in Excel.
- Polite by design: single connection, 1.5–2 s delay with jitter between requests,
  exponential backoff on 429/5xx, honest User-Agent.

## Quick start

Requires Python 3.11+.

```bash
make install                     # create .venv and install dependencies

# scrape one book: https://author.today/work/302190 -> work id 302190
.venv/bin/python -m atscraper --work-id 302190

# re-parse cached raw responses without hitting the site
.venv/bin/python -m atscraper --work-id 302190 --from-cache

# force re-download even when responses are already cached
.venv/bin/python -m atscraper --work-id 302190 --refresh
```

Output lands in `data/processed/{work_id}/`:

| file | contents |
|---|---|
| `comments.json` | nested comment tree (replies inside `children`) |
| `comments.csv` | flat table, one row per comment, `utf-8-sig` |
| `work_meta.json` | title, author, URL, site-reported comment count, scrape time |

Progress (pages fetched, comments parsed, mismatches vs the count reported by
the site) is logged to stderr.

## Project layout

```
atscraper/           the scraper package
  __main__.py        CLI entry point
  client.py          HTTP session: rate limiting, retries, CSRF bootstrap
  fetcher.py         downloads pages + collapsed threads, caches raw responses
  parser.py          pure functions: raw JSON/HTML -> Comment dataclasses
  exporter.py        raw cache -> comments.json / comments.csv / work_meta.json
  models.py          Comment, Work dataclasses
analysis/            standalone analysis scripts (see below)
data/
  raw/{work_id}/         untouched raw responses — never edited
  processed/{work_id}/   exports
tests/
  fixtures/          saved real responses; tests never make live HTTP calls
```

`fetcher` only writes to `raw/`; `parser`/`exporter` only read `raw/` and write
to `processed/`. Strict separation, idempotent re-runs.

## Comment schema

| field | type | notes |
|---|---|---|
| comment_id | str | site's ID |
| parent_id | str \| null | null for top-level |
| work_id | str | |
| author_name | str | display name |
| author_id | str \| null | profile slug |
| created_at_raw | str | as provided by the site |
| created_at | str \| null | ISO-8601 UTC |
| text | str | plain text |
| text_html | str | original HTML |
| likes | int \| null | 👍 count |
| is_deleted | bool | deleted/hidden stub |
| is_author | bool | comment by the book's author |
| page | int | pagination page it came from |
| scraped_at | str | ISO-8601 UTC |

## Analysis example

The `analysis/` directory contains a worked example: hunting for the unannounced
POV-chapter character of one book by cross-referencing reader guesses with the
book text.

- `extract_names.py` — proper-name extraction from comments (Cyrillic tokenization
  + [pymorphy3](https://github.com/no-plagiarism/pymorphy3) lemmatization, so
  declined Russian names group correctly), ranked by frequency.
- `extract_book_names.py` — same pipeline over the full book text.
- `compare_names.py` — classifies every book name: guessed by readers / mentioned
  but never guessed / never mentioned at all.

The scraper itself stays analysis-agnostic; these scripts are consumers of its exports.

## Development

```bash
make test      # pytest against saved fixtures (no network)
make lint      # ruff check
make format    # ruff format
```

Parser functions are pure (bytes in, dataclasses out) and fail loudly when the
site markup changes, rather than silently emitting partial rows.

## Etiquette & disclaimer

For personal/research use only. The scraper reads only publicly visible
comments, identifies itself with an honest User-Agent, keeps a single
connection with generous delays, and does not bypass authentication or
paywalled content. Scraped content belongs to its authors; treat exported data
accordingly and respect the site's terms of service.
