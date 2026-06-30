"""GET /claim/{claim_id} — one claim's full provenance."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_neo4j_store
from ..schemas.claims import ClaimDetailResponse
from ..services import neo4j_service

router = APIRouter()


@router.get("/claim/{claim_id}", response_model=ClaimDetailResponse)
def claim_detail(
    claim_id: str,
    store: Any = Depends(get_neo4j_store),
) -> ClaimDetailResponse:
    result = neo4j_service.claim_detail(store, claim_id)
    if result is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return result
