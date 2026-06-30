"""GET /search - semantic search over the shared Qdrant collection."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_embedder, get_qdrant_store
from ..schemas.search import SearchResponse
from ..services import qdrant_service

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="Natural-language query"),
    commission: str | None = Query(None, description="zondo | madlanga"),
    day: int | None = Query(None, description="Restrict to one hearing day"),
    speaker: str | None = Query(None, description="Restrict to a speaker label"),
    limit: int = Query(10, ge=1, le=50),
    embedder: Any = Depends(get_embedder),
    store: Any = Depends(get_qdrant_store),
) -> SearchResponse:
    hits = qdrant_service.search_hits(
        embedder=embedder,
        store=store,
        query=q,
        commission=commission,
        day=day,
        speaker=speaker,
        limit=limit,
    )
    return SearchResponse(query=q, count=len(hits), hits=hits)
