"""Parsers for author.today comment API responses.

Pure functions: bytes/str in, dataclasses out. No I/O, no HTTP.

Endpoints whose responses are parsed here (verified 2026-06-11, see CLAUDE.md):

- ``GET /comment/load?rootId={work_id}&rootType=1&page={n}`` — JSON envelope,
  ``data.html`` holds a fragment with a pagination block and the comment tree
  (reply levels 0-1 inline, deeper branches collapsed).
- ``GET /comment/loadThread?parentId={id}&rootId={work_id}&rootType=1`` — same
  envelope, ``data.html`` holds the collapsed sub-tree (levels >= 2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag

from .models import Comment


class ParseError(Exception):
    """Raised when a response does not match the expected structure."""


@dataclass(frozen=True)
class LoadPage:
    """Parsed result of one /comment/load response."""

    comments: list[Comment]
    total_count: int
    last_page: int


@dataclass(frozen=True)
class WorkPageInfo:
    """Metadata extracted from the initial /work/{id} HTML page."""

    work_id: str
    title: str
    author_name: str
    author_id: str | None
    csrf_token: str | None


_TIME_FRACTION_RE = re.compile(r"(\.\d{6})\d+")
_PAGE_PARAM_RE = re.compile(r"[?&]page=(\d+)")
_PROFILE_HREF_RE = re.compile(r"^/u/([^/?#]+)")
_LIKES_HINT_RE = re.compile(r"\U0001f44d\s*(\d+)")
_WORK_ID_RE = re.compile(r"commentRootId:\s*(\d+)")


def parse_load_response(
    raw: str | bytes,
    *,
    work_id: str,
    page: int,
    scraped_at: str,
    work_author_id: str | None = None,
) -> LoadPage:
    """Parse one /comment/load JSON response into comments + pagination info."""
    data = _unwrap_envelope(raw)
    html = data.get("html", "")
    total_count = data.get("totalCount")
    if not isinstance(total_count, int):
        raise ParseError(f"data.totalCount missing or not an int: {total_count!r}")
    comments = parse_comments_fragment(
        html,
        work_id=work_id,
        page=page,
        scraped_at=scraped_at,
        work_author_id=work_author_id,
    )
    return LoadPage(
        comments=comments, total_count=total_count, last_page=_last_page(html)
    )


def parse_thread_response(
    raw: str | bytes,
    *,
    work_id: str,
    parent_id: str,
    page: int,
    scraped_at: str,
    work_author_id: str | None = None,
) -> list[Comment]:
    """Parse one /comment/loadThread JSON response (collapsed branch).

    Top-level comments of the fragment get ``parent_id`` of the branch root.
    An empty ``data.html`` (branch already inline) yields an empty list.
    """
    data = _unwrap_envelope(raw)
    return parse_comments_fragment(
        data.get("html", ""),
        work_id=work_id,
        page=page,
        scraped_at=scraped_at,
        root_parent_id=parent_id,
        work_author_id=work_author_id,
    )


def parse_comments_fragment(
    html: str,
    *,
    work_id: str,
    page: int,
    scraped_at: str,
    root_parent_id: str | None = None,
    work_author_id: str | None = None,
) -> list[Comment]:
    """Parse an HTML comment-tree fragment into a flat list of Comments.

    ``parent_id`` is derived from DOM nesting: a comment sitting inside the
    ``.replies`` container of another comment's wrapper is its child; comments
    at the fragment's top level get ``root_parent_id``.
    """
    soup = BeautifulSoup(html, "lxml")
    comments: list[Comment] = []
    for div in soup.find_all("div", class_="comment"):
        assert isinstance(div, Tag)
        comments.append(
            _parse_comment(
                div,
                work_id=work_id,
                page=page,
                scraped_at=scraped_at,
                root_parent_id=root_parent_id,
                work_author_id=work_author_id,
            )
        )
    return comments


def extract_collapsed_parent_ids(html: str) -> list[str]:
    """IDs of comments whose reply branch is collapsed and needs /comment/loadThread."""
    soup = BeautifulSoup(html, "lxml")
    ids: list[str] = []
    for wrapper in soup.find_all("div", class_="collapsed-replies"):
        assert isinstance(wrapper, Tag)
        comment = wrapper.find("div", class_="comment", recursive=False)
        if isinstance(comment, Tag) and comment.get("data-id"):
            ids.append(str(comment["data-id"]))
    return ids


def parse_work_page(html: str) -> WorkPageInfo:
    """Extract work metadata and session bootstrap values from /work/{id} HTML."""
    soup = BeautifulSoup(html, "lxml")

    work_id_match = _WORK_ID_RE.search(html)
    if not work_id_match:
        raise ParseError("commentRootId not found in work page")
    work_id = work_id_match.group(1)

    title_el = soup.find("h1", class_="book-title")
    if not isinstance(title_el, Tag):
        raise ParseError("h1.book-title not found in work page")
    title = title_el.get_text(strip=True)

    author_el = soup.find("span", itemprop="author")
    if not isinstance(author_el, Tag):
        raise ParseError("span[itemprop=author] not found in work page")
    name_meta = author_el.find("meta", itemprop="name")
    author_name = (
        str(name_meta["content"])
        if isinstance(name_meta, Tag) and name_meta.get("content")
        else author_el.get_text(strip=True)
    )
    author_id: str | None = None
    author_link = author_el.find("a", href=True)
    if isinstance(author_link, Tag):
        href_match = _PROFILE_HREF_RE.match(str(author_link["href"]))
        if href_match:
            author_id = href_match.group(1)

    csrf_token: str | None = None
    token_input = soup.find("input", attrs={"name": "__RequestVerificationToken"})
    if isinstance(token_input, Tag) and token_input.get("value"):
        csrf_token = str(token_input["value"])

    return WorkPageInfo(
        work_id=work_id,
        title=title,
        author_name=author_name,
        author_id=author_id,
        csrf_token=csrf_token,
    )


def _unwrap_envelope(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"response is not valid JSON: {exc}") from exc
    if not envelope.get("isSuccessful"):
        raise ParseError(f"API reported failure: {envelope.get('messages')!r}")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise ParseError(f"envelope has no data object: {envelope!r:.200}")
    return data


def _last_page(html: str) -> int:
    pages = [int(m.group(1)) for m in _PAGE_PARAM_RE.finditer(html)]
    return max(pages, default=1)


def _parse_comment(
    div: Tag,
    *,
    work_id: str,
    page: int,
    scraped_at: str,
    root_parent_id: str | None,
    work_author_id: str | None,
) -> Comment:
    comment_id = div.get("data-id")
    if not comment_id:
        raise ParseError(f"comment without data-id: {str(div)[:300]}")
    comment_id = str(comment_id)

    name_el = div.find("span", class_="comment-user-name")
    is_deleted = not isinstance(name_el, Tag)

    author_name = ""
    author_id: str | None = None
    if isinstance(name_el, Tag):
        author_name = name_el.get_text(strip=True)
        profile_link = name_el.find_parent("a", href=True)
        if isinstance(profile_link, Tag):
            href_match = _PROFILE_HREF_RE.match(str(profile_link["href"]))
            if href_match:
                author_id = href_match.group(1)

    created_at_raw = ""
    time_el = div.find("span", attrs={"data-time": True})
    if isinstance(time_el, Tag):
        created_at_raw = str(time_el["data-time"])
    elif not is_deleted:
        raise ParseError(f"comment {comment_id} has no [data-time] timestamp")

    # Deleted-by-user stubs keep author/time but the <article> holds a plain
    # "Пользователь удалил свой комментарий." paragraph instead of .rich-content.
    body_el = div.find("div", class_="rich-content")
    article_el = div.find("article")
    if isinstance(body_el, Tag):
        text_html = body_el.decode_contents().strip()
        text = body_el.get_text(separator="\n", strip=True)
    elif isinstance(article_el, Tag):
        is_deleted = True
        text_html = article_el.decode_contents().strip()
        text = article_el.get_text(separator="\n", strip=True)
    elif is_deleted:
        text_html = ""
        text = ""
    else:
        raise ParseError(f"comment {comment_id} has no .rich-content body")

    return Comment(
        comment_id=comment_id,
        parent_id=_parent_id(div, root_parent_id),
        work_id=work_id,
        author_name=author_name,
        author_id=author_id,
        created_at_raw=created_at_raw,
        created_at=_normalize_timestamp(created_at_raw),
        text=text,
        text_html=text_html,
        likes=_likes(div),
        is_deleted=is_deleted,
        is_author=work_author_id is not None and author_id == work_author_id,
        page=page,
        scraped_at=scraped_at,
    )


def _parent_id(div: Tag, root_parent_id: str | None) -> str | None:
    replies = div.find_parent("div", class_="replies")
    if not isinstance(replies, Tag):
        return root_parent_id
    wrapper = replies.find_parent("div", class_="comment-wrapper")
    if not isinstance(wrapper, Tag):
        raise ParseError(f"comment {div.get('data-id')!r}: .replies without wrapper")
    parent = wrapper.find("div", class_="comment", recursive=False)
    if not isinstance(parent, Tag) or not parent.get("data-id"):
        raise ParseError(f"comment {div.get('data-id')!r}: parent comment not found")
    return str(parent["data-id"])


def _likes(div: Tag) -> int | None:
    rating = div.find(class_="comment-rating-count")
    if not isinstance(rating, Tag):
        return None
    hint = rating.get("data-hint")
    if hint:
        hint_match = _LIKES_HINT_RE.search(str(hint))
        if hint_match:
            return int(hint_match.group(1))
    try:
        return int(rating.get_text(strip=True).replace("+", ""))
    except ValueError:
        return None


def _normalize_timestamp(raw: str) -> str | None:
    """``2026-06-08T10:33:58.5309710Z`` -> ISO-8601 UTC, or None if unparseable."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(_TIME_FRACTION_RE.sub(r"\1", raw))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
