"""GET /chunk/{id}/graph - mentions and claims stay distinct; both spines work."""

from __future__ import annotations

from conftest import FakeNeo4jStore


def _neighborhood(**overrides) -> dict:
    data = {
        "chunk": {
            "chunk_id": "ck-1", "text": "Testimony about the task team.",
            "page_start": 12, "page_end": 13, "commission_slug": "madlanga",
            "day_no": 3, "chunk_index": 0,
        },
        "document": {
            "sha256": "ab" * 32, "source_url": "https://example.org/day3.pdf",
            "filename": "day3.pdf", "authoritative": True,
            "document_type": "Transcript", "commission_slug": "madlanga",
        },
        "hearing": {"day_no": 3, "date": "2025-09-19"},
        "mentions": {
            "person": ["Justice Mbuyiseli Madlanga"],
            "org": ["South African Police Service"],
            "place": ["Johannesburg"],
        },
        "speakers": ["Justice Mbuyiseli Madlanga"],
        "claims": [{
            "claim_id": "cl-1", "status": "alleged",
            "quote": "He told me to pay.", "text": "alleges X paid Y.",
            "speaker_unresolved": False, "speaker": "Adv Sesi Baloyi SC",
        }],
    }
    data.update(overrides)
    return data


def test_chunk_graph_separates_mentions_and_claims(client_factory):
    client = client_factory(neo4j=FakeNeo4jStore(neighborhood=_neighborhood()))
    body = client.get("/chunk/ck-1/graph").json()
    # invariant 4: distinct, separately-typed fields.
    assert body["mentions"]["person"] == ["Justice Mbuyiseli Madlanga"]
    assert body["mentions"]["org"] == ["South African Police Service"]
    assert [c["claim_id"] for c in body["claims"]] == ["cl-1"]
    assert "claims" not in body["mentions"]
    assert body["source_url"].endswith("day3.pdf")
    assert body["date"] == "2025-09-19"


def test_chunk_graph_claims_carry_join_key_status_and_speaker(client_factory):
    client = client_factory(neo4j=FakeNeo4jStore(neighborhood=_neighborhood()))
    claim = client.get("/chunk/ck-1/graph").json()["claims"][0]
    assert claim["claim_id"] == "cl-1"
    assert claim["status"] == "alleged"
    assert claim["speaker"] == "Adv Sesi Baloyi SC"


def test_chunk_graph_404_when_chunk_absent(client_factory):
    client = client_factory(neo4j=FakeNeo4jStore(neighborhood=None))
    assert client.get("/chunk/nope/graph").status_code == 404


def test_chunk_graph_handles_bootstrap_null_pages(client_factory):
    boot = _neighborhood(
        chunk={
            "chunk_id": "ck-b", "text": "Bootstrap.", "page_start": None,
            "page_end": None, "commission_slug": "zondo", "day_no": 1,
            "chunk_index": 0,
        },
        document={
            "sha256": "cd" * 32, "source_url": "https://example.org/zondo.txt",
            "filename": "zondo.txt", "authoritative": False,
            "document_type": "Transcript", "commission_slug": "zondo",
        },
    )
    client = client_factory(neo4j=FakeNeo4jStore(neighborhood=boot))
    body = client.get("/chunk/ck-b/graph").json()
    assert body["page_start"] is None
    assert body["authoritative"] is False
