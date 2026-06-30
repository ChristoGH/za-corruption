"""Dependency providers (the DI seam tests override).

Each provider reuses a shaped class from commission_ingestion - no second
embedder, no hand-rolled store (invariant 2). Imports are lazy so importing the
app needs neither torch nor a live store; the heavy embedder is only built when
/search is actually called. Providers are cached: the BGE model and the store
connections are built once per process, not per request.

Tests replace these via app.dependency_overrides, so the real classes are never
constructed under pytest.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import get_settings


@lru_cache(maxsize=1)
def get_qdrant_store() -> Any:
    from commission_ingestion.vector.qdrant_store import QdrantStore

    return QdrantStore(url=get_settings().qdrant_url)


@lru_cache(maxsize=1)
def get_embedder() -> Any:
    # Loads sentence-transformers (torch) - built once, on first /search only.
    from commission_ingestion.vector.embedder import BgeSmallEmbedder

    return BgeSmallEmbedder()


@lru_cache(maxsize=1)
def get_neo4j_store() -> Any:
    from commission_ingestion.graph.neo4j_store import Neo4jStore

    settings = get_settings()
    return Neo4jStore(
        uri=settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
