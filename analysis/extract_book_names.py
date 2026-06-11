"""Ranked list of proper names appearing in the book text.

Reads data/book/slomannyj_mech.txt, writes analysis/book_names.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from namelib import (
    MIN_CAP_RATIO,
    STOPWORDS,
    WORD_RE,
    Lemmatizer,
    cap_ratio,
    lowercase_lemma_counts,
)

BOOK = Path("data/book/slomannyj_mech.txt")
CSV_OUT = Path("analysis/book_names.csv")


def main() -> int:
    text = BOOK.read_text(encoding="utf-8")
    print(f"book: {len(text)} chars", file=sys.stderr)

    lemmatize = Lemmatizer()
    lower_counts = lowercase_lemma_counts([text], lemmatize)

    rows: dict[str, dict] = {}
    for match in WORD_RE.finditer(text):
        lemma, is_name = lemmatize(match.group(0))
        if lemma in STOPWORDS:
            continue
        stats = rows.setdefault(
            lemma,
            {
                "name": lemma.capitalize(),
                "is_name_pos": is_name,
                "mentions": 0,
                "first_offset": match.start(),
            },
        )
        stats["mentions"] += 1
        stats["is_name_pos"] = stats["is_name_pos"] or is_name

    result = []
    for lemma, stats in rows.items():
        ratio = cap_ratio(stats["mentions"], lower_counts.get(lemma, 0))
        if ratio < MIN_CAP_RATIO and not stats["is_name_pos"]:
            continue
        result.append(
            {
                "name": stats["name"],
                "mentions": stats["mentions"],
                "name_pos": stats["is_name_pos"],
                "cap_ratio": round(ratio, 2),
                # position of first appearance as % of the book, to tell
                # early-introduced characters from late ones
                "first_pct": round(100 * stats["first_offset"] / len(text), 1),
            }
        )

    out = pd.DataFrame(result).sort_values("mentions", ascending=False)
    CSV_OUT.parent.mkdir(exist_ok=True)
    out.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"{len(out)} book names -> {CSV_OUT}", file=sys.stderr)
    print(out.head(40).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
