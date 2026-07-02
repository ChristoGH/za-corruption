"""The legal/architectural spine, asserted directly (invariants 1-6).

These tests exist to fail loudly if a refactor ever erodes the Mention != Claim
separation, drops attribution, synthesises a "fact" shape, or softens a claim.
The accusatory fixture is a deliberately damaging, fully-specific allegation
naming individuals: the pipeline must surface it sharp and attributed, never
bleached and never as a bare fact.
"""

from __future__ import annotations

import pytest

from conftest import FakeNeo4jStore, FakeQdrantStore


# A precise, damaging allegation naming individuals, as it would arrive from the
# graph: an attributed claim (STATED_BY a witness), status 'alleged', verbatim
# quote preserved. Defamation protection here is structural, not lexical.
ACCUSATORY_CLAIM = {
    "claim": {
        "claim_id": "cl-acc",
        "status": "alleged",
        "quote": "Mr Bheki Cele personally instructed me to pay R2 million to "
                 "Vusimuzi Matlala in exchange for the tender.",
        "text": "alleges that the minister directed a corrupt payment for a tender.",
        "certainty": "high",
        "attribution": "first_person",
        "speaker_unresolved": False,
        "has_unresolved_subject": False,
        "unresolved_subjects": [],
        "unresolved_objects": [],
    },
    "speaker": "Brigadier Ncedi Mahlangu",
    "chunk": {
        "chunk_id": "ck-acc", "day_no": 42, "page_start": 118,
        "page_end": 119, "commission_slug": "madlanga",
    },
    "source_url": "https://example.org/day42.pdf",
    "mentions": [
        {"name": "Bheki Cele", "role": "subject", "labels": ["Person"]},
        {"name": "Vusimuzi Matlala", "role": "object", "labels": ["Person"]},
    ],
}


def test_accusatory_claim_surfaces_attributed_never_as_fact(client_factory):
    client = client_factory(neo4j=FakeNeo4jStore(claim=ACCUSATORY_CLAIM))
    body = client.get("/claim/cl-acc").json()

    # invariant 5: it is an allegation, attributed, never a bare fact.
    assert body["status"] == "alleged"
    assert body["speaker"] == "Brigadier Ncedi Mahlangu"   # STATED_BY, present
    # the API must not synthesise a fact/proven shape.
    assert "fact" not in body
    assert "proven" not in body

    # content stays sharp: the quote is preserved verbatim, names intact, not
    # softened or anonymised. Structure carries the qualification, not wording.
    assert "Bheki Cele" in body["quote"]
    assert "Vusimuzi Matlala" in body["quote"]
    assert "R2 million" in body["quote"]
    assert {m["name"] for m in body["mentions"]} == {"Bheki Cele", "Vusimuzi Matlala"}


def test_claim_missing_attribution_raises_never_silently_rendered(client_factory):
    # invariant 5: a claim with no STATED_BY speaker is never rendered as if it
    # stood on its own; the service refuses rather than drop attribution.
    no_speaker = dict(ACCUSATORY_CLAIM, speaker=None)
    client = client_factory(neo4j=FakeNeo4jStore(claim=no_speaker))
    with pytest.raises(Exception):
        client.get("/claim/cl-acc")


def test_graph_rejects_a_claim_with_no_speaker(client_factory):
    # invariant 4/5: a claim brief on a chunk must carry a STATED_BY speaker; an
    # unattributed claim must not be rendered in the neighborhood either.
    neighborhood = {
        "chunk": {"chunk_id": "ck-1", "text": "t", "page_start": 1,
                  "page_end": 1, "commission_slug": "madlanga", "day_no": 1,
                  "chunk_index": 0},
        "document": {"sha256": "ab" * 32, "source_url": "https://x/y.pdf",
                     "filename": "y.pdf", "authoritative": True,
                     "document_type": "Transcript", "commission_slug": "madlanga"},
        "hearing": {"day_no": 1, "date": "2025-09-17"},
        "mentions": {"person": [], "org": [], "place": []},
        "speakers": [],
        "claims": [{"claim_id": "cl-x", "status": "alleged", "quote": "q",
                    "text": "t", "speaker_unresolved": False, "speaker": None}],
    }
    client = client_factory(neo4j=FakeNeo4jStore(neighborhood=neighborhood))
    with pytest.raises(Exception):
        client.get("/chunk/ck-1/graph")


def test_search_every_hit_has_a_source_link(client_factory):
    # invariant 3, asserted on the search surface: provenance on every result.
    from types import SimpleNamespace

    point = SimpleNamespace(score=0.5, payload={
        "chunk_id": "ck-1", "source_url": "https://example.org/d.pdf",
        "commission_slug": "zondo", "day_no": 1, "page_start": 3, "page_end": 3,
        "speakers": [], "text": "testimony",
    })
    client = client_factory(qdrant=FakeQdrantStore(search_result=[point]))
    hit = client.get("/search", params={"q": "x"}).json()["hits"][0]
    assert hit["chunk_id"] and hit["source_url"]


def test_mentions_and_claims_are_never_one_list(client_factory):
    # invariant 4: the response keeps them in distinct, separately-typed fields.
    neighborhood = {
        "chunk": {"chunk_id": "ck-1", "text": "t", "page_start": 1, "page_end": 1,
                  "commission_slug": "madlanga", "day_no": 1, "chunk_index": 0},
        "document": {"sha256": "ab" * 32, "source_url": "https://x/y.pdf",
                     "filename": "y.pdf", "authoritative": True,
                     "document_type": "Transcript", "commission_slug": "madlanga"},
        "hearing": {"day_no": 1, "date": "2025-09-17"},
        "mentions": {"person": ["Someone Named"], "org": [], "place": []},
        "speakers": ["A Witness"],
        "claims": [{"claim_id": "cl-1", "status": "alleged", "quote": "q",
                    "text": "t", "speaker_unresolved": False, "speaker": "A Witness"}],
    }
    client = client_factory(neo4j=FakeNeo4jStore(neighborhood=neighborhood))
    body = client.get("/chunk/ck-1/graph").json()
    assert isinstance(body["mentions"], dict)      # grouped, not a flat list
    assert isinstance(body["claims"], list)
    # a mentioned name is not silently promoted into the claims list, nor vice versa.
    assert "Someone Named" not in [c["claim_id"] for c in body["claims"]]
