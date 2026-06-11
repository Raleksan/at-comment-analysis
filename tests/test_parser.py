"""Parser tests against saved fixtures (no live HTTP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atscraper.parser import (
    ParseError,
    extract_collapsed_parent_ids,
    parse_load_response,
    parse_thread_response,
    parse_work_page,
)

FIXTURES = Path(__file__).parent / "fixtures"
WORK_ID = "170886"
SCRAPED_AT = "2026-06-11T00:00:00+00:00"


@pytest.fixture(scope="module")
def page1_raw() -> str:
    return (FIXTURES / "comment_load_page1_170886.json").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page1(page1_raw: str):
    return parse_load_response(
        page1_raw, work_id=WORK_ID, page=1, scraped_at=SCRAPED_AT
    )


def test_load_response_counts(page1) -> None:
    assert page1.total_count == 414
    assert page1.last_page == 8
    assert len(page1.comments) == 32


def test_known_comment_fields(page1) -> None:
    by_id = {c.comment_id: c for c in page1.comments}
    c = by_id["41507027"]
    assert c.author_name == "Смолин Александр"
    assert c.author_id == "katmandu06"
    assert c.parent_id is None
    assert c.created_at_raw == "2026-06-08T10:33:58.5309710Z"
    assert c.created_at == "2026-06-08T10:33:58.530971+00:00"
    assert c.likes == 3
    assert not c.is_deleted
    assert not c.is_author
    assert c.work_id == WORK_ID
    assert c.page == 1
    assert c.scraped_at == SCRAPED_AT
    assert "с удовольствием прочитал" in c.text
    assert c.text_html.startswith("<p>")


def test_thread_structure(page1) -> None:
    ids = {c.comment_id for c in page1.comments}
    top = [c for c in page1.comments if c.parent_id is None]
    replies = [c for c in page1.comments if c.parent_id is not None]
    assert top and replies
    # every reply's parent must be present on the same page
    assert all(c.parent_id in ids for c in replies)


def test_all_comments_have_required_fields(page1) -> None:
    for c in page1.comments:
        assert c.comment_id
        if not c.is_deleted:
            assert c.author_name
            assert c.created_at is not None
            assert c.text_html


def test_thread_response() -> None:
    raw = (FIXTURES / "comment_loadThread_39310378.json").read_text(encoding="utf-8")
    comments = parse_thread_response(
        raw, work_id=WORK_ID, parent_id="39310378", page=1, scraped_at=SCRAPED_AT
    )
    assert len(comments) == 2
    level2, level3 = comments
    assert level2.parent_id == "39310378"
    assert level3.parent_id == level2.comment_id


def test_collapsed_parent_ids(page1_raw: str) -> None:
    html = json.loads(page1_raw)["data"]["html"]
    ids = extract_collapsed_parent_ids(html)
    assert len(ids) == 6
    assert "39310378" in ids


def test_is_author_flag(page1_raw: str) -> None:
    page = parse_load_response(
        page1_raw,
        work_id=WORK_ID,
        page=1,
        scraped_at=SCRAPED_AT,
        work_author_id="katmandu06",
    )
    flagged = [c for c in page.comments if c.is_author]
    assert flagged
    assert all(c.author_id == "katmandu06" for c in flagged)


def test_parse_work_page() -> None:
    html = (FIXTURES / "work_page_170886.html").read_text(encoding="utf-8")
    info = parse_work_page(html)
    assert info.work_id == WORK_ID
    assert info.title == "Терра Инкогнита"
    assert info.author_name == "Евгений Капба"
    assert info.author_id == "eugene_kapba"
    assert info.csrf_token


def test_deleted_comment_stub() -> None:
    raw = (FIXTURES / "comment_load_page6_302190_deleted_stub.json").read_text(
        encoding="utf-8"
    )
    page = parse_load_response(raw, work_id="302190", page=6, scraped_at=SCRAPED_AT)
    by_id = {c.comment_id: c for c in page.comments}
    c = by_id["41275303"]
    assert c.is_deleted
    assert c.author_name == "Rafail22"
    assert c.author_id == "raf301202"
    assert c.created_at is not None
    assert "удалил свой комментарий" in c.text
    # the rest of the page still parses normally
    assert sum(not x.is_deleted for x in page.comments) > 30


def test_failure_envelope_raises() -> None:
    raw = json.dumps(
        {"isSuccessful": False, "messages": ["Произошла ошибка"], "data": None}
    )
    with pytest.raises(ParseError, match="Произошла ошибка"):
        parse_load_response(raw, work_id=WORK_ID, page=1, scraped_at=SCRAPED_AT)


def test_invalid_json_raises() -> None:
    with pytest.raises(ParseError, match="not valid JSON"):
        parse_load_response("<html>", work_id=WORK_ID, page=1, scraped_at=SCRAPED_AT)
