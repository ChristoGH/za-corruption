"""GET /search — provenance on every hit; CLI-mirrored query shaping."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from conftest import FakeQdrantStore


def _point(**payload):
    full = {
        "chunk_id": "ck-1",
        "source_url": "https://example.org/day3.pdf",
        "commission_slug": "madlanga",
        "commission_name": "Madlanga Commission",
        "day_no": 3,
        "date": "2025-09-19",
        "page_start": 12,
        "page_end": 13,
        "authoritative": True,
        "speakers": ["CHAIRPERSON"],
        "text": "A long passage of testimony about the disbanding of the task team. " * 8,
    }
    full.update(payload)
    return SimpleNamespace(score=0.91, payload=full)


def test_search_hits_carry_provenance(client_factory):
    client = client_factory(qdrant=FakeQdrantStore(search_result=[_point()]))
    body = client.get("/search", params={"q": "disbanding of the task team"}).json()
    assert body["count"] == 1
    hit = body["hits"][0]
    # invariant 3: chunk_id (join key) + source_url + day/page on every hit.
    assert hit["chunk_id"] == "ck-1"
    assert hit["source_url"].endswith("day3.pdf")
    assert hit["day_no"] == 3
    assert hit["page_start"] == 12
    assert hit["snippet"].endswith("…")           # shortened like the CLI


def test_search_mirrors_cli_query_shaping(client_factory):
    store = FakeQdrantStore(search_result=[_point()])
    client = client_factory(qdrant=store)
    client.get(
        "/search",
        params={"q": "money", "commission": "madlanga", "day": 3,
                "speaker": "chairperson", "limit": 7},
    )
    call = store.search_calls[0]
    assert call["limit"] == 7
    assert call["commission"] == "madlanga"
    assert call["day_no"] == 3
    assert call["speaker"] == "CHAIRPERSON"        # upper-cased, as in the CLI


def test_search_requires_a_query(client):
    # q is required; an empty query is a 422, not an empty search.
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": ""}).status_code == 422


def test_search_rejects_a_hit_with_no_source_link(client_factory):
    # invariant 3: a payload missing chunk_id/source_url is a bug, not rendered.
    bad = _point()
    bad.payload.pop("chunk_id")
    client = client_factory(qdrant=FakeQdrantStore(search_result=[bad]))
    with pytest.raises(Exception):
        client.get("/search", params={"q": "x"})
