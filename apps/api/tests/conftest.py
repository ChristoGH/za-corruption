"""Shared test fixtures: a TestClient wired to fake stores via DI overrides.

CI has no live Qdrant/Neo4j, so every test injects fakes through
app.dependency_overrides. The real QdrantStore/Neo4jStore/BgeSmallEmbedder are
never constructed under pytest (no torch, no network).
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_embedder, get_neo4j_store, get_qdrant_store
from app.main import create_app


class FakeQdrantStore:
    """Stands in for QdrantStore. `search_result` is the list of hits returned;
    `count_ok` toggles whether count() raises (store down) for /health."""

    def __init__(
        self,
        search_result: list[Any] | None = None,
        count_ok: bool = True,
    ) -> None:
        self._search_result = search_result or []
        self._count_ok = count_ok
        self.search_calls: list[dict] = []

    def count(self, **_kwargs) -> int:
        if not self._count_ok:
            raise ConnectionError("qdrant down")
        return 123

    def search(self, vector, **kwargs) -> list[Any]:
        self.search_calls.append({"vector": vector, **kwargs})
        return self._search_result


class FakeNeo4jStore:
    """Stands in for Neo4jStore reads. Each read returns a preset value;
    `ping_ok` toggles whether ping() raises (store down) for /health."""

    def __init__(
        self,
        neighborhood: dict | None = None,
        claim: dict | None = None,
        ping_ok: bool = True,
    ) -> None:
        self._neighborhood = neighborhood
        self._claim = claim
        self._ping_ok = ping_ok

    def ping(self) -> bool:
        if not self._ping_ok:
            raise ConnectionError("neo4j down")
        return True

    def chunk_neighborhood(self, chunk_id: str) -> dict | None:
        return self._neighborhood

    def claim_detail(self, claim_id: str) -> dict | None:
        return self._claim


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0] * 384


def make_client(
    *,
    qdrant: FakeQdrantStore | None = None,
    neo4j: FakeNeo4jStore | None = None,
    embedder: FakeEmbedder | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_qdrant_store] = lambda: qdrant or FakeQdrantStore()
    app.dependency_overrides[get_neo4j_store] = lambda: neo4j or FakeNeo4jStore()
    app.dependency_overrides[get_embedder] = lambda: embedder or FakeEmbedder()
    return TestClient(app)


@pytest.fixture()
def client_factory() -> Callable[..., TestClient]:
    return make_client


@pytest.fixture()
def client() -> TestClient:
    return make_client()
