"""Search response schema.

chunk_id and source_url are REQUIRED (invariant 3): a hit with no join key or no
source link is a bug, so the schema rejects it rather than render it.
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchHit(BaseModel):
    score: float
    chunk_id: str
    source_url: str
    commission_slug: str | None = None
    commission_name: str | None = None
    day_no: int | None = None
    date: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    authoritative: bool = True
    speakers: list[str] = []
    snippet: str = ""


class SearchResponse(BaseModel):
    query: str
    count: int
    hits: list[SearchHit]
