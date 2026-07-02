"""GET /health - degrades gracefully, never 500s when a store is down."""

from __future__ import annotations

from conftest import FakeNeo4jStore, FakeQdrantStore


def test_health_ok_when_both_stores_up(client_factory):
    client = client_factory(
        qdrant=FakeQdrantStore(count_ok=True),
        neo4j=FakeNeo4jStore(ping_ok=True),
    )
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "qdrant": "up", "neo4j": "up"}


def test_health_degrades_when_qdrant_down(client_factory):
    client = client_factory(
        qdrant=FakeQdrantStore(count_ok=False),
        neo4j=FakeNeo4jStore(ping_ok=True),
    )
    resp = client.get("/health")
    # never 500 - the page stays answerable.
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["qdrant"] == "down"
    assert body["neo4j"] == "up"


def test_health_degrades_when_neo4j_down(client_factory):
    client = client_factory(
        qdrant=FakeQdrantStore(count_ok=True),
        neo4j=FakeNeo4jStore(ping_ok=False),
    )
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["neo4j"] == "down"
