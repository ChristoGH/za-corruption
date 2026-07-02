"""GET /chunk/{chunk_id}/graph - one chunk's evidence neighborhood."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_neo4j_store
from ..schemas.graph import ChunkGraphResponse
from ..services import neo4j_service

router = APIRouter()


@router.get("/chunk/{chunk_id}/graph", response_model=ChunkGraphResponse)
def chunk_graph(
    chunk_id: str,
    store: Any = Depends(get_neo4j_store),
) -> ChunkGraphResponse:
    result = neo4j_service.chunk_graph(store, chunk_id)
    if result is None:
        raise HTTPException(status_code=404, detail="chunk not found")
    return result
