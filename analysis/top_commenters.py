"""Markdown report: top 50 commenters by comment count.

Reads data/processed/302190/comments.csv, writes analysis/top_commenters.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

WORK_ID = "302190"
CSV_IN = Path(f"data/processed/{WORK_ID}/comments.csv")
META_IN = Path(f"data/processed/{WORK_ID}/work_meta.json")
MD_OUT = Path("analysis/top_commenters.md")
TOP_N = 50


def main() -> int:
    df = pd.read_csv(
        CSV_IN, encoding="utf-8-sig", dtype={"comment_id": str, "parent_id": str}
    )
    meta = json.loads(META_IN.read_text(encoding="utf-8"))

    # deleted stubs have no author/likes — count them separately, not per user
    alive = df[~df.is_deleted].copy()
    alive["author_key"] = alive.author_id.fillna(alive.author_name)

    grouped = (
        alive.sort_values("created_at")
        .groupby("author_key")
        .agg(
            name=("author_name", "last"),
            comments=("comment_id", "count"),
            avg_likes=("likes", "mean"),
            median_likes=("likes", "median"),
            total_likes=("likes", "sum"),
            is_author=("is_author", "any"),
        )
        .sort_values(["comments", "total_likes"], ascending=False)
    )

    assert grouped.comments.sum() == len(alive)
    top = grouped.head(TOP_N)

    lines = [
        f"# Топ-{TOP_N} комментаторов «{meta['title']}»",
        "",
        f"Книга: [{meta['url']}]({meta['url']}) (автор: {meta['author']}).",
        f"Всего: {len(df)} комментариев ({df.is_deleted.sum()} удалённых) "
        f"от {grouped.shape[0]} пользователей, "
        f"период {df.created_at.min()[:10]} — {df.created_at.max()[:10]}. "
        f"Данные собраны {meta['scraped_at'][:10]}.",
        "",
        "Лайки — число 👍 на комментарий. ✍ — автор книги.",
        "",
        "| # | Имя | Комментариев | Лайков в среднем | Лайков (медиана) | Лайков всего |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(top.itertuples(), start=1):
        mark = " ✍" if row.is_author else ""
        lines.append(
            f"| {rank} | {row.name}{mark} | {row.comments} "
            f"| {row.avg_likes:.1f} | {row.median_likes:.0f} | {row.total_likes:.0f} |"
        )
    lines.append("")

    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {MD_OUT}", file=sys.stderr)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
