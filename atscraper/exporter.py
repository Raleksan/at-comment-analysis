"""Re-parses cached raw responses and writes processed exports.

Reads only ``data/raw/{work_id}/``, writes only ``data/processed/{work_id}/``:
``comments.json`` (nested thread tree), ``comments.csv`` (flat, utf-8-sig for
Excel), ``work_meta.json``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from . import __version__, parser
from .fetcher import raw_dir
from .models import Comment, Work
from .parser import WorkPageInfo

logger = logging.getLogger(__name__)

PROCESSED_ROOT = Path("data/processed")

_LOAD_FILE_RE = re.compile(r"comment_load_p(\d+)\.json$")
_THREAD_FILE_RE = re.compile(r"comment_loadThread_p(\d+)_(\d+)\.json$")


def load_and_parse(work_id: str) -> tuple[WorkPageInfo, list[Comment], int]:
    """Parse all cached raw responses for a work.

    Returns work page info, deduplicated comments, and the site-reported total.
    """
    source = raw_dir(work_id)
    work_page = source / "work_page.html"
    if not work_page.exists():
        raise FileNotFoundError(
            f"{work_page} not found — run without --from-cache first"
        )
    info = parser.parse_work_page(work_page.read_text(encoding="utf-8"))

    comments: list[Comment] = []
    total_count = 0
    load_files = sorted(source.glob("comment_load_p*.json"))
    if not load_files:
        raise FileNotFoundError(f"no comment_load_p*.json files in {source}")
    for path in load_files:
        match = _LOAD_FILE_RE.search(path.name)
        if not match:
            continue
        result = parser.parse_load_response(
            path.read_bytes(),
            work_id=work_id,
            page=int(match.group(1)),
            scraped_at=_file_scraped_at(path),
            work_author_id=info.author_id,
        )
        total_count = result.total_count
        comments.extend(result.comments)
    for path in sorted(source.glob("comment_loadThread_p*.json")):
        match = _THREAD_FILE_RE.search(path.name)
        if not match:
            continue
        comments.extend(
            parser.parse_thread_response(
                path.read_bytes(),
                work_id=work_id,
                parent_id=match.group(2),
                page=int(match.group(1)),
                scraped_at=_file_scraped_at(path),
                work_author_id=info.author_id,
            )
        )

    deduped = _dedupe(comments)
    logger.info(
        "parsed %d comments (%d files, %d duplicates dropped), site reports %d",
        len(deduped),
        len(load_files),
        len(comments) - len(deduped),
        total_count,
    )
    if len(deduped) != total_count:
        logger.warning(
            "count mismatch: parsed %d vs %d reported by site",
            len(deduped),
            total_count,
        )
    return info, deduped, total_count


def export(
    work_id: str, info: WorkPageInfo, comments: list[Comment], total_count: int
) -> Path:
    """Write comments.json, comments.csv and work_meta.json; returns output dir."""
    out = PROCESSED_ROOT / work_id
    out.mkdir(parents=True, exist_ok=True)

    tree = _build_tree(comments)
    (out / "comments.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    df = pd.DataFrame([c.to_dict() for c in comments])
    df.to_csv(out / "comments.csv", index=False, encoding="utf-8-sig")

    meta = Work(
        work_id=work_id,
        title=info.title,
        author=info.author_name,
        url=f"https://author.today/work/{work_id}",
        total_comments_reported=total_count,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        scraper_version=__version__,
    )
    (out / "work_meta.json").write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("wrote %d comments to %s", len(comments), out)
    return out


def _build_tree(comments: list[Comment]) -> list[dict[str, Any]]:
    """Nest comments into a children-tree, preserving input order."""
    nodes: dict[str, dict[str, Any]] = {
        c.comment_id: {**c.to_dict(), "children": []} for c in comments
    }
    roots: list[dict[str, Any]] = []
    orphans = 0
    for c in comments:
        node = nodes[c.comment_id]
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id]["children"].append(node)
        else:
            if c.parent_id:
                orphans += 1
            roots.append(node)
    if orphans:
        logger.warning("%d comments reference a parent that was not scraped", orphans)
    return roots


def _dedupe(comments: list[Comment]) -> list[Comment]:
    seen: set[str] = set()
    unique: list[Comment] = []
    for c in comments:
        if c.comment_id in seen:
            continue
        seen.add(c.comment_id)
        unique.append(c)
    return unique


def _file_scraped_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(
        timespec="seconds"
    )
