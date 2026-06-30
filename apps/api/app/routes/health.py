"""GET /health — cheap liveness pings for both stores. Never 500s the page.

A store that is down is reported "down" (status "degraded"), not raised: the
health endpoint must stay answerable even when Qdrant or Neo4j is unreachable.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from ..dependencies import get_neo4j_store, get_qdrant_store
from ..schemas.health import HealthResponse

router = APIRouter()


def _alive(check: Callable[[], Any]) -> bool:
    """Run a liveness check, swallowing any error into a False (down)."""
    try:
        check()
        return True
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health(
    qdrant: Any = Depends(get_qdrant_store),
    neo4j: Any = Depends(get_neo4j_store),
) -> HealthResponse:
    qdrant_up = _alive(qdrant.count)        # cheap count() round-trip
    neo4j_up = _alive(neo4j.ping)           # RETURN 1
    status = "ok" if (qdrant_up and neo4j_up) else "degraded"
    return HealthResponse(
        status=status,
        qdrant="up" if qdrant_up else "down",
        neo4j="up" if neo4j_up else "down",
    )
