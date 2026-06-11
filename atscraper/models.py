"""Dataclasses for scraped author.today entities.

The ``Comment`` field set is part of the project's stable data schema
(see CLAUDE.md) — downstream analysis depends on it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Comment:
    comment_id: str
    parent_id: str | None
    work_id: str
    author_name: str
    author_id: str | None
    created_at_raw: str
    created_at: str | None
    text: str
    text_html: str
    likes: int | None
    is_deleted: bool
    is_author: bool
    page: int
    scraped_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Work:
    work_id: str
    title: str
    author: str
    url: str
    total_comments_reported: int | None
    scraped_at: str
    scraper_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
