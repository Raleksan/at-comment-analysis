"""Ranked list of (character) names mentioned in comments since 2026-02-27.

Reads data/processed/302190/comments.csv, writes
analysis/names_since_feb27.csv and prints the top of the ranking.
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

WORK_ID = "302190"
SINCE = "2026-02-27"
CSV_IN = Path(f"data/processed/{WORK_ID}/comments.csv")
CSV_OUT = Path("analysis/names_since_feb27.csv")


def main() -> int:
    df = pd.read_csv(
        CSV_IN, encoding="utf-8-sig", dtype={"comment_id": str, "parent_id": str}
    )
    df = df[(df.created_at >= SINCE) & (~df.is_deleted) & df.text.notna()]
    print(f"analyzing {len(df)} comments since {SINCE}", file=sys.stderr)

    lemmatize = Lemmatizer()
    lower_counts = lowercase_lemma_counts(df.text, lemmatize)

    rows: dict[str, dict] = {}
    for c in df.itertuples():
        seen_here: set[str] = set()
        for token in WORD_RE.findall(c.text):
            lemma, is_name = lemmatize(token)
            if lemma in STOPWORDS:
                continue
            stats = rows.setdefault(
                lemma,
                {
                    "name": lemma.capitalize(),
                    "is_name_pos": is_name,
                    "mentions": 0,
                    "commenters": set(),
                    "author_mentions": 0,
                    "first_seen": c.created_at,
                    "last_seen": c.created_at,
                    "samples": [],
                },
            )
            stats["mentions"] += 1
            stats["is_name_pos"] = stats["is_name_pos"] or is_name
            stats["commenters"].add(c.author_id)
            if c.is_author:
                stats["author_mentions"] += 1
            stats["first_seen"] = min(stats["first_seen"], c.created_at)
            stats["last_seen"] = max(stats["last_seen"], c.created_at)
            if lemma not in seen_here and len(stats["samples"]) < 3:
                snippet = c.text.replace("\n", " ")[:160]
                stats["samples"].append(f"[{c.comment_id}] {snippet}")
            seen_here.add(lemma)

    result = []
    for lemma, stats in rows.items():
        ratio = cap_ratio(stats["mentions"], lower_counts.get(lemma, 0))
        # Name-tagged lemmas are kept regardless of ratio (recall-first)
        if ratio < MIN_CAP_RATIO and not stats["is_name_pos"]:
            continue
        result.append(
            {
                "name": stats["name"],
                "mentions": stats["mentions"],
                "commenters": len(stats["commenters"]),
                "author_mentions": stats["author_mentions"],
                "name_pos": stats["is_name_pos"],
                "cap_ratio": round(ratio, 2),
                "first_seen": stats["first_seen"][:10],
                "last_seen": stats["last_seen"][:10],
                "samples": " | ".join(stats["samples"]),
            }
        )

    out = pd.DataFrame(result).sort_values(["mentions", "commenters"], ascending=False)
    CSV_OUT.parent.mkdir(exist_ok=True)
    out.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"{len(out)} candidate names -> {CSV_OUT}", file=sys.stderr)

    top = out.head(60)[
        ["name", "mentions", "commenters", "author_mentions", "name_pos"]
    ]
    print(top.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
