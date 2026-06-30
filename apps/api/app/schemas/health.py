"""Health response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

StoreState = Literal["up", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    qdrant: StoreState
    neo4j: StoreState
