"""Shared name-extraction helpers for comment and book analysis.

Recall-first philosophy: better to keep some junk than to lose the hidden
name readers were guessing.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

import pymorphy3

WORD_RE = re.compile(r"[А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁа-яё][а-яё]+)?")
LOWER_RE = re.compile(r"\b[а-яё]{3,}\b")

# Frequent capitalized non-name words that survive the ratio filter
# (sentence starters, site/meta words, months).
STOPWORDS = {
    "автор",
    "книга",
    "глава",
    "герой",
    "спасибо",
    "ждем",
    "ждём",
    "очень",
    "просто",
    "почему",
    "когда",
    "если",
    "может",
    "это",
    "так",
    "вот",
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
    "россия",
    "москва",
}
# A capitalized token counts as name-like when, corpus-wide, it appears
# capitalized at least this often relative to its lowercase occurrences.
MIN_CAP_RATIO = 0.6


class Lemmatizer:
    """Cached pymorphy3 wrapper returning (normal form, has-Name-grammeme)."""

    def __init__(self) -> None:
        self._morph = pymorphy3.MorphAnalyzer()
        self._cache: dict[str, tuple[str, bool]] = {}

    def __call__(self, token: str) -> tuple[str, bool]:
        if token not in self._cache:
            parse = self._morph.parse(token)[0]
            is_name = any(g in parse.tag for g in ("Name", "Surn", "Patr"))
            self._cache[token] = (parse.normal_form, is_name)
        return self._cache[token]


def lowercase_lemma_counts(
    texts: Iterable[str], lemmatize: Lemmatizer
) -> dict[str, int]:
    """Corpus-wide lowercase counts, to filter sentence-starter common words."""
    counts: dict[str, int] = defaultdict(int)
    for text in texts:
        for word in LOWER_RE.findall(text):
            counts[lemmatize(word.capitalize())[0]] += 1
    return counts


def cap_ratio(cap_count: int, lower_count: int) -> float:
    return cap_count / (cap_count + lower_count)
