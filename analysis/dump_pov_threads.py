"""Dump comment threads (since 2026-02-27) that discuss the future POV chapter.

A thread is included when any of its comments matches the keyword pattern.
Output: analysis/pov_threads.txt, threads in chronological order, replies
indented, author comments marked with [АВТОР].
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

WORK_ID = "302190"
SINCE = "2026-02-27"
CSV_IN = Path(f"data/processed/{WORK_ID}/comments.csv")
OUT = Path("analysis/pov_threads.txt")

KEYWORDS = re.compile(r"pov|пов\b|повов|угада|интерлюди", re.IGNORECASE)


def main() -> int:
    df = pd.read_csv(
        CSV_IN, encoding="utf-8-sig", dtype={"comment_id": str, "parent_id": str}
    )
    df = df[df.text.notna()]
    by_id = df.set_index("comment_id", drop=False)

    def root_of(cid: str) -> str:
        seen = set()
        while True:
            parent = by_id.at[cid, "parent_id"]
            if pd.isna(parent) or parent not in by_id.index or cid in seen:
                return cid
            seen.add(cid)
            cid = parent

    recent = df[df.created_at >= SINCE]
    matched = recent[recent.text.str.contains(KEYWORDS, na=False)]
    roots = sorted({root_of(cid) for cid in matched.comment_id})
    print(f"{len(matched)} matching comments in {len(roots)} threads", file=sys.stderr)

    children: dict[str, list[str]] = {}
    for c in df.itertuples():
        if pd.notna(c.parent_id):
            children.setdefault(c.parent_id, []).append(c.comment_id)

    lines: list[str] = []

    def emit(cid: str, depth: int) -> None:
        c = by_id.loc[cid]
        mark = " [АВТОР]" if c.is_author else ""
        text = re.sub(r"\s+", " ", str(c.text)).strip()
        lines.append(
            f"{'  ' * depth}- {c.created_at[:10]} {c.author_name}{mark} "
            f"(#{cid}): {text}"
        )
        for child in children.get(cid, []):
            emit(child, depth + 1)

    root_dates = sorted(roots, key=lambda r: str(by_id.at[r, "created_at"]))
    for root in root_dates:
        lines.append("")
        lines.append("=" * 80)
        emit(root, 0)

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(lines)} lines)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
