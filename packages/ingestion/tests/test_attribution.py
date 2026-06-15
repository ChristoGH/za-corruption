"""Pre-step B — turn-speaker attribution validator tests.

Runs against the REAL seed so resolution matches production. Synthesizes one chunk
per bucket and asserts the partition lands each in exactly the right place — the
core guarantee is that MODEL-WRONG (bucket 1) and PARSER-GAP (bucket 2), which
both look like "speaker != turn speaker", are never conflated.
"""

from __future__ import annotations

import hashlib

import pytest

from commission_ingestion.eval.attribution import (
    BUCKET_MATCH,
    BUCKET_MODEL_WRONG,
    BUCKET_PARSER_GAP,
    BUCKET_QUOTE_UNRECOVERABLE,
    AttributionStats,
    classify_claim,
    validate_chunk,
)
from commission_ingestion.extraction.schema import ChunkExtraction, ExtractedClaim
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.resolution.canonical import DEFAULT_SEED_PATH, load_store


@pytest.fixture(scope="module")
def store():
    return load_store(DEFAULT_SEED_PATH)


def chunk_with(text: str) -> ChunkRecord:
    return ChunkRecord(
        commission_slug="madlanga", commission_name="Madlanga Commission",
        doc_sha256="ab" * 32, source_url="https://example.org/d.pdf",
        day_no=43, date="2025-12-03",
        chunk_id=hashlib.sha256(text.encode()).hexdigest(), chunk_index=0,
        page_start=1, page_end=1, speakers=[], text=text, char_count=len(text),
    )


def claim_with(speaker: str, quote: str, predicate: str = "stated something") -> ExtractedClaim:
    return ExtractedClaim(
        speaker=speaker, subject_refs=[], predicate=predicate,
        object_refs=[], quote=quote, certainty=None,
    )


def _bucket(store, text, speaker, quote):
    return classify_claim(chunk_with(text), claim_with(speaker, quote), store).bucket


# ── the four outcomes ─────────────────────────────────────────────────────────

def test_match_when_model_agrees_with_detected_turn(store):
    text = "ADV BALOYI SC: I put it to you that SAPS failed here."
    assert _bucket(store, text, "ADV BALOYI SC", "SAPS failed") == BUCKET_MATCH


def test_bucket1_model_wrong_against_detected_turn(store):
    # quote is inside a properly-detected CHAIRPERSON turn, model says BALOYI
    text = "CHAIRPERSON: The witness misled the commission today."
    assert _bucket(store, text, "ADV BALOYI SC", "misled the commission") == BUCKET_MODEL_WRONG


def test_bucket2_parser_gap_absorbed_commissioner_turn(store):
    # COMMISSIONER MKHWANAZI: is absorbed (LABEL_RE can't see it); model is right
    text = ("CHAIRPERSON: Please proceed. "
            "COMMISSIONER MKHWANAZI: I signed the plan myself today.")
    inst = classify_claim(
        chunk_with(text), claim_with("COMMISSIONER MKHWANAZI", "I signed the plan myself"),
        store,
    )
    assert inst.bucket == BUCKET_PARSER_GAP
    assert inst.model_speaker == "person:jd-mkhwanazi"
    assert inst.turn_speaker == "person:mbuyiseli-madlanga"   # parser saw CHAIRPERSON
    assert inst.augmented_speaker == "person:jd-mkhwanazi"    # augmented saw the witness


def test_bucket3_quote_unrecoverable(store):
    text = "ADV BALOYI SC: Something quite different was said here."
    assert _bucket(store, text, "ADV BALOYI SC",
                   "this phrase is absent from the chunk") == BUCKET_QUOTE_UNRECOVERABLE


# ── the discriminator must not be fooled ──────────────────────────────────────

def test_naming_absorbed_witness_without_an_absorbed_turn_is_bucket1(store):
    # model names COMMISSIONER MKHWANAZI, but he did NOT speak here (no inline
    # label) — the quote is in a real CHAIRPERSON turn. This is a genuine error,
    # NOT a parser gap.
    text = "CHAIRPERSON: The operational plan was signed in advance."
    assert _bucket(store, text, "COMMISSIONER MKHWANAZI",
                   "operational plan was signed") == BUCKET_MODEL_WRONG


# ── rate only counts bucket 1, over comparable claims ─────────────────────────

def test_rate_excludes_buckets_2_and_3(store):
    text = ("CHAIRPERSON: Please proceed. "
            "COMMISSIONER MKHWANAZI: I signed the plan myself today.")
    ext = ChunkExtraction(entities=[], mentions=[], claims=[
        claim_with("CHAIRPERSON", "Please proceed"),                    # match (CHAIRPERSON turn)
        claim_with("ADV SELLO SC", "Please proceed"),                   # model_wrong
        claim_with("COMMISSIONER MKHWANAZI", "I signed the plan myself"),  # parser_gap
        claim_with("ADV BALOYI SC", "absent phrase not present"),       # quote_unrecoverable
    ])
    stats = validate_chunk(chunk_with(text), ext, store)
    assert stats.match == 1
    assert stats.model_wrong == 1
    assert stats.parser_gap == 1
    assert stats.quote_unrecoverable == 1
    assert stats.comparable == 2                       # match + model_wrong only
    assert stats.attribution_error_rate == pytest.approx(0.5)  # 1/2, not 1/4


def test_stats_add_accumulates(store):
    a = AttributionStats(total=2, match=1, model_wrong=1)
    b = AttributionStats(total=1, parser_gap=1)
    a.add(b)
    assert (a.total, a.match, a.model_wrong, a.parser_gap) == (3, 1, 1, 1)
