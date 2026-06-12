"""Semantic search over the shared Qdrant collection.

    uv run search-corpus "disbanding of the task team" --day 3 --speaker CHAIRPERSON

Prints day, date, pages, speakers, a snippet, and the official source URL for
each hit — every result is traceable to a page of the official PDF.
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap

from commission_ingestion.vector.qdrant_store import QdrantStore

SNIPPET_CHARS = 320


def format_hit(rank: int, score: float, payload: dict) -> str:
    day = payload.get("day_no")
    date = payload.get("date") or "?"
    pages = f"pp. {payload.get('page_start')}–{payload.get('page_end')}"
    speakers = ", ".join(payload.get("speakers") or []) or "—"
    snippet = textwrap.shorten(
        payload.get("text") or "", width=SNIPPET_CHARS, placeholder=" …"
    )
    authoritative = "" if payload.get("authoritative", True) else "  [non-authoritative]"
    lines = [
        f"{rank}. [{score:.3f}] {payload.get('commission_slug')} "
        f"day {day} ({date}), {pages}{authoritative}",
        f"   speakers: {speakers}",
        f"   {snippet}",
        f"   source: {payload.get('source_url')}",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Semantic search over commission transcripts in Qdrant."
    )
    parser.add_argument("query", help="Natural-language query")
    parser.add_argument("--day", type=int, default=None, help="Restrict to one hearing day")
    parser.add_argument("--speaker", default=None, help="Restrict to a speaker label")
    parser.add_argument(
        "--commission",
        choices=["zondo", "madlanga"],
        default=None,
        help="Restrict to one commission (default: all)",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--qdrant-url", default=None, help="Default: $QDRANT_URL or localhost:6333")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    from commission_ingestion.vector.embedder import BgeSmallEmbedder

    embedder = BgeSmallEmbedder()
    store = QdrantStore(url=args.qdrant_url)

    hits = store.search(
        embedder.embed_query(args.query),
        limit=args.limit,
        commission=args.commission,
        day_no=args.day,
        speaker=args.speaker.upper() if args.speaker else None,
    )

    if not hits:
        print("No results.")
        return 1

    for rank, hit in enumerate(hits, start=1):
        print(format_hit(rank, hit.score, hit.payload or {}))
        print()
    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
