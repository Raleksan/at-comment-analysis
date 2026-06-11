"""CLI entry point: python -m atscraper --work-id 123456 [--from-cache]"""

from __future__ import annotations

import argparse
import logging
import sys

from .client import Client
from .exporter import export, load_and_parse
from .fetcher import fetch_work


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    work_id = str(args.work_id)

    if not args.from_cache:
        with Client() as client:
            fetch_work(work_id, client, refresh=args.refresh)

    info, comments, total_count = load_and_parse(work_id)
    out = export(work_id, info, comments, total_count)
    print(out)
    return 0


def _parse_args() -> argparse.Namespace:
    cli = argparse.ArgumentParser(
        prog="atscraper",
        description="Extract reader comments from one author.today work.",
    )
    cli.add_argument("--work-id", required=True, type=int, help="numeric work ID")
    cli.add_argument(
        "--from-cache",
        action="store_true",
        help="re-parse cached raw responses without hitting the site",
    )
    cli.add_argument(
        "--refresh",
        action="store_true",
        help="re-download responses even when already cached",
    )
    return cli.parse_args()


if __name__ == "__main__":
    sys.exit(main())
