"""Downloads comment pages for a work and caches raw responses.

Writes only to ``data/raw/{work_id}/`` (one file per request); never parses
beyond what is needed to drive pagination and thread expansion. Files are
rewritten only when content changed, so re-runs are idempotent.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import parser
from .client import Client

logger = logging.getLogger(__name__)

RAW_ROOT = Path("data/raw")


def raw_dir(work_id: str) -> Path:
    return RAW_ROOT / work_id


def fetch_work(work_id: str, client: Client, refresh: bool = False) -> None:
    """Download the work page, every comment page, and all collapsed branches.

    Already-cached responses are reused (resume after interruption) unless
    ``refresh`` forces re-downloading everything.
    """
    target = raw_dir(work_id)
    scraped_at = datetime.now(timezone.utc).isoformat()

    work_page_path = target / "work_page.html"
    raw = _get_or_fetch(
        work_page_path, lambda: client.get_work_page(work_id).content, refresh
    )
    info = parser.parse_work_page(raw.decode("utf-8"))
    logger.info("work %s: «%s» by %s", work_id, info.title, info.author_name)
    if info.csrf_token:
        client.set_csrf_token(info.csrf_token)

    page = 1
    last_page = 1
    total_count = 0
    while page <= last_page:
        raw = _get_or_fetch(
            target / f"comment_load_p{page:04d}.json",
            lambda: client.get_comments_page(work_id, page).content,
            refresh,
        )
        result = parser.parse_load_response(
            raw, work_id=work_id, page=page, scraped_at=scraped_at
        )
        last_page = result.last_page
        total_count = result.total_count
        logger.info("page %d/%d: %d comments", page, last_page, len(result.comments))
        _fetch_collapsed_threads(work_id, page, raw, client, target, refresh)
        page += 1
    logger.info(
        "fetch done: %d pages, site reports %d comments", last_page, total_count
    )


def _fetch_collapsed_threads(
    work_id: str,
    page: int,
    load_raw: bytes,
    client: Client,
    target: Path,
    refresh: bool,
) -> None:
    """Fetch every collapsed reply branch on a page, recursively."""
    pending = parser.extract_collapsed_parent_ids(_fragment_html(load_raw))
    seen: set[str] = set()
    while pending:
        parent_id = pending.pop(0)
        if parent_id in seen:
            continue
        seen.add(parent_id)
        raw = _get_or_fetch(
            target / f"comment_loadThread_p{page:04d}_{parent_id}.json",
            lambda: client.get_thread(work_id, parent_id).content,
            refresh,
        )
        nested = parser.extract_collapsed_parent_ids(_fragment_html(raw))
        if nested:
            logger.info(
                "thread %s: %d nested collapsed branches", parent_id, len(nested)
            )
        pending.extend(nested)
    if seen:
        logger.info("page %d: expanded %d collapsed threads", page, len(seen))


def _get_or_fetch(path: Path, fetch: Callable[[], bytes], refresh: bool) -> bytes:
    if path.exists() and not refresh:
        return path.read_bytes()
    raw = fetch()
    _save(path, raw)
    return raw


def _fragment_html(raw: bytes) -> str:
    return json.loads(raw).get("data", {}).get("html", "") or ""


def _save(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
    path.write_bytes(content)
