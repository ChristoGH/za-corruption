"""GET /claim/{id} - full provenance; attribution never dropped."""

from __future__ import annotations

from conftest import FakeNeo4jStore


def _claim(**overrides) -> dict:
    data = {
        "claim": {
            "claim_id": "cl-1", "status": "alleged",
            "quote": "He told me to pay the money.",
            "text": "alleges that the minister directed the payment.",
            "certainty": "high", "attribution": "first_person",
            "speaker_unresolved": False, "has_unresolved_subject": False,
            "unresolved_subjects": [], "unresolved_objects": [],
        },
        "speaker": "Adv Sesi Baloyi SC",
        "chunk": {
            "chunk_id": "ck-1", "day_no": 3, "page_start": 12,
            "page_end": 13, "commission_slug": "madlanga",
        },
        "source_url": "https://example.org/day3.pdf",
        "mentions": [
            {"name": "The Minister", "role": "subject", "labels": ["Person"]},
        ],
    }
    data.update(overrides)
    return data


def test_claim_detail_full_provenance(client_factory):
    client = client_factory(neo4j=FakeNeo4jStore(claim=_claim()))
    body = client.get("/claim/cl-1").json()
    assert body["status"] == "alleged"             # stored status, not synthesised
    assert body["speaker"] == "Adv Sesi Baloyi SC"  # STATED_BY, never dropped
    assert body["quote"].startswith("He told me")
    assert body["source_url"].endswith("day3.pdf")
    assert body["day_no"] == 3
    assert body["mentions"][0]["role"] == "subject"


def test_claim_detail_preserves_raw_speaker_flag(client_factory):
    raw = _claim(
        claim={
            "claim_id": "cl-2", "status": "alleged", "quote": "I saw it.",
            "text": "alleges presence.", "certainty": "medium",
            "attribution": "first_person", "speaker_unresolved": True,
            "has_unresolved_subject": False, "unresolved_subjects": [],
            "unresolved_objects": [],
        },
        speaker="WITNESS C",
    )
    client = client_factory(neo4j=FakeNeo4jStore(claim=raw))
    body = client.get("/claim/cl-2").json()
    assert body["speaker_unresolved"] is True       # ADR 0007 flag surfaced
    assert body["speaker"] == "WITNESS C"


def test_claim_detail_404_when_absent(client_factory):
    client = client_factory(neo4j=FakeNeo4jStore(claim=None))
    assert client.get("/claim/nope").status_code == 404
