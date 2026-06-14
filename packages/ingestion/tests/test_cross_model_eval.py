"""Cross-model eval harness tests — sampler determinism, compare metrics on a
known fixture, structural framing flags. Zero network, zero API calls."""

from __future__ import annotations

import hashlib

import pytest

from commission_ingestion.eval.compare import (
    ResolvedClaim,
    compare_arm,
    match_claims,
    resolve_extraction,
)
from commission_ingestion.eval.framing_judge import structurally_asserted
from commission_ingestion.eval.sample import (
    StratumContext,
    build_sample,
    classify_chunk,
    freeze_sample,
    load_sample,
)
from commission_ingestion.extraction.schema import (
    ChunkExtraction,
    ExtractedClaim,
    ExtractedEntity,
    ExtractedMention,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.resolution.canonical import CanonicalEntity, CanonicalStore


def make_store() -> CanonicalStore:
    return CanonicalStore([
        CanonicalEntity("person:sandile-khumalo", "Adv Sandile Khumalo SC",
                        "person", ["ADV KHUMALO SC"]),
        CanonicalEntity("person:dumisani-khumalo", "Lt-Gen Dumisani Khumalo",
                        "person", ["LT-GEN KHUMALO"]),
        CanonicalEntity("person:chaskalson", "Adv Matthew Chaskalson SC",
                        "person", ["ADV CHASKALSON SC", "ADV CH ASK ALSON SC"]),
        CanonicalEntity("org:saps", "South African Police Service",
                        "org", ["SAPS"]),
        CanonicalEntity("org:pktt", "Political Killings Task Team",
                        "org", ["PKTT"]),
    ])


def make_chunk(index: int, text: str) -> ChunkRecord:
    return ChunkRecord(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        doc_sha256="d0c5" * 16,
        source_url="https://example.org/d.pdf",
        day_no=1,
        date="2025-09-17",
        chunk_id=hashlib.sha256(f"{index}:{text}".encode()).hexdigest(),
        chunk_index=index,
        page_start=1,
        page_end=2,
        speakers=["CHAIRPERSON"],
        n_turns=2,
        text=text,
        char_count=len(text),
    )


FILLER = "The proceedings continued in the ordinary course of business. " * 5


@pytest.fixture()
def corpus() -> list[ChunkRecord]:
    chunks = []
    # 4 ambiguous-surname chunks (bare Khumalo, two canonical owners).
    for i in range(4):
        chunks.append(make_chunk(i, f"{FILLER} General Khumalo attended item {i}."))
    # 4 OCR-variant chunks.
    for i in range(4, 8):
        chunks.append(make_chunk(i, f"{FILLER} ADV CH ASK ALSON SC rose on item {i}."))
    # 4 acronym-dense chunks (short text, many acronyms).
    for i in range(8, 12):
        chunks.append(make_chunk(i, f"SAPS and the PKTT briefed SAPS on PKTT matters {i}."))
    # 4 allegation-dense chunks.
    for i in range(12, 16):
        chunks.append(make_chunk(
            i, f"He stated that he was told and alleged the payment {i}."))
    # 8 control chunks.
    for i in range(16, 24):
        chunks.append(make_chunk(i, f"{FILLER} Item {i} was adjourned."))
    return chunks


def test_classification_hits_expected_strata(corpus):
    ctx = StratumContext.from_store(make_store())
    strata = [classify_chunk(c, ctx) for c in corpus]
    assert strata[0] == "ambiguous_surname"
    assert strata[4] == "ocr_variant"
    assert strata[8] == "high_acronym"
    assert strata[12] == "allegation_dense"
    assert strata[20] == "control"


def test_sampler_is_deterministic_and_frozen(corpus, tmp_path):
    store = make_store()
    first = build_sample(corpus, store, sample_size=10, seed=7)
    second = build_sample(corpus, store, sample_size=10, seed=7)
    assert first == second
    assert len(first) == 10
    assert {s.stratum for s in first} == {
        "ambiguous_surname", "ocr_variant", "high_acronym",
        "allegation_dense", "control"}

    path = freeze_sample(first, tmp_path, seed=7)
    assert load_sample(path) == first
    # Freezing the identical sample again is a no-op...
    freeze_sample(first, tmp_path, seed=7)
    # ...but silently replacing a frozen sample is refused.
    different = build_sample(corpus, store, sample_size=10, seed=8)
    with pytest.raises(RuntimeError):
        freeze_sample(different, tmp_path, seed=7)


def _extraction(entities, mentions, claims) -> ChunkExtraction:
    return ChunkExtraction(
        entities=[ExtractedEntity(ref=r, name=n, type=t) for r, n, t in entities],
        mentions=[ExtractedMention(entity_ref=r, quote=q) for r, q in mentions],
        claims=[
            ExtractedClaim(speaker=s, subject_refs=subj, predicate=p,
                           object_refs=[], quote=q, certainty=None)
            for s, subj, p, q in claims
        ],
    )


def test_compare_metrics_on_known_fixture():
    store = make_store()
    # Reference (Opus): resolves Chaskalson + SAPS; one claim about Khumalo (D).
    reference_ex = _extraction(
        entities=[("e1", "ADV CHASKALSON SC", "person"),
                  ("e2", "SAPS", "acronym"),
                  ("e3", "LT-GEN KHUMALO", "person")],
        mentions=[("e1", "ADV CHASKALSON SC rose"), ("e2", "SAPS briefed"),
                  ("e3", "LT-GEN KHUMALO said")],
        claims=[("ADV CHASKALSON SC", ["e3"],
                 "stated that he received the instruction", "quote A")],
    )
    # Candidate: misses SAPS (FN), invents PKTT (FP), fragments an OCR name,
    # drops the reference claim and invents an unrelated one. Note: a variant
    # like "ADV CH ASK ALSON" (SC dropped) WOULD still resolve via the
    # title-stripped bare index — the fragment here is a truly unseen typo.
    candidate_ex = _extraction(
        entities=[("e1", "ADV CHASKILSON", "person"),  # unseen typo — unresolvable
                  ("e2", "PKTT", "acronym"),
                  ("e3", "LT-GEN KHUMALO", "person")],
        mentions=[("e1", "rose"), ("e2", "PKTT matters"), ("e3", "KHUMALO said")],
        claims=[("CHAIRPERSON", ["e2"], "ordered the adjournment", "quote B")],
    )

    strata = {"c1": "ocr_variant"}
    result = compare_arm(
        model="claude-test",
        reference={"c1": reference_ex},
        candidate={"c1": candidate_ex},
        strata=strata,
        store=store,
    )
    assert result.completion_rate == 1.0
    # Reference ids: chaskalson, saps, dumisani-khumalo. Candidate: pktt, dumisani.
    assert result.entity_overall.tp == 1   # dumisani-khumalo
    assert result.entity_overall.fp == 1   # pktt
    assert result.entity_overall.fn == 2   # chaskalson, saps
    assert result.entity_hard.tp == 1      # this chunk is a hard stratum
    assert result.entity_control.tp == 0
    assert result.fragmentation == 1       # "ADV CHASKILSON" fell through
    assert result.claims_matched == 0
    assert result.claims_dropped == 1
    assert result.claims_invented == 1
    assert result.claim_recall == 0.0 and result.claim_precision == 0.0


def test_claim_soft_match_requires_subject_and_predicate():
    a = ResolvedClaim("X", "stated that he received an instruction to disband",
                      "q", None, frozenset({"person:dumisani-khumalo"}))
    same_subject_similar = ResolvedClaim(
        "X", "stated he received instructions to disband the team",
        "q", None, frozenset({"person:dumisani-khumalo"}))
    same_subject_different = ResolvedClaim(
        "X", "confirmed his appointment date", "q", None,
        frozenset({"person:dumisani-khumalo"}))
    other_subject = ResolvedClaim(
        "X", "stated that he received an instruction to disband",
        "q", None, frozenset({"org:pktt"}))

    assert match_claims([a], [same_subject_similar]) == (1, 0, 0)
    assert match_claims([a], [same_subject_different]) == (0, 1, 1)
    assert match_claims([a], [other_subject]) == (0, 1, 1)


def test_structural_framing_flags():
    neutral = ResolvedClaim("MR X", "stated that the unit was disbanded",
                            "q", None, frozenset())
    asserted = ResolvedClaim("MR X", "ordered the disbandment of the unit",
                             "q", None, frozenset())
    no_speaker = ResolvedClaim("", "stated that the unit was disbanded",
                               "q", None, frozenset())
    assert not structurally_asserted(neutral)
    assert structurally_asserted(asserted)
    assert structurally_asserted(no_speaker)


def test_resolution_marks_fragments_with_raw_prefix():
    store = make_store()
    extraction = _extraction(
        entities=[("e1", "MR UNKNOWNPERSON", "person")],
        mentions=[("e1", "MR UNKNOWNPERSON spoke")],
        claims=[],
    )
    resolved = resolve_extraction(extraction, store)
    assert resolved.canonical_ids == set()
    assert resolved.fragments == {"raw:MR UNKNOWNPERSON"}
