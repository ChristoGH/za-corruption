"""Semantic search adapter over BgeSmallEmbedder + QdrantStore.

Mirrors the existing CLI surface (commission_ingestion/cli/search.py): same
payload fields, same snippet width, same speaker upper-casing. No second
embedder and no hand-rolled Qdrant client (invariant 2).
"""

from __future__ import annotations

import textwrap
from typing import Any

from ..schemas.search import SearchHit

SNIPPET_CHARS = 320  # mirror cli/search.py


def search_hits(
    *,
    embedder: Any,
    store: Any,
    query: str,
    commission: str | None = None,
    day: int | None = None,
    speaker: str | None = None,
    limit: int = 10,
) -> list[SearchHit]:
    """Embed the query, search Qdrant, and shape ranked hits.

    Speaker labels are upper-cased to match how they are stored (as in the CLI).
    Every hit carries the §3 provenance fields; SearchHit enforces chunk_id and
    source_url structurally, so a payload missing either is rejected, not shown.
    """
    vector = embedder.embed_query(query)
    points = store.search(
        vector,
        limit=limit,
        commission=commission,
        day_no=day,
        speaker=speaker.upper() if speaker else None,
    )
    hits: list[SearchHit] = []
    for point in points:
        payload = point.payload or {}
        snippet = textwrap.shorten(
            payload.get("text") or "", width=SNIPPET_CHARS, placeholder=" …"
        )
        hits.append(
            SearchHit(
                score=point.score,
                chunk_id=payload.get("chunk_id"),
                source_url=payload.get("source_url"),
                commission_slug=payload.get("commission_slug"),
                commission_name=payload.get("commission_name"),
                day_no=payload.get("day_no"),
                date=payload.get("date"),
                page_start=payload.get("page_start"),
                page_end=payload.get("page_end"),
                authoritative=payload.get("authoritative", True),
                speakers=payload.get("speakers") or [],
                snippet=snippet,
            )
        )
    return hits
