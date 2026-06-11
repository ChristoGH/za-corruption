"""Tests for the pure descriptive-statistics layer (no plotting deps)."""

from __future__ import annotations

from commission_ingestion.analysis.stats import (
    aggregate_day,
    detect_witness,
    role_of,
    summarise,
    word_count,
)
from commission_ingestion.parsing.turns import Turn


def _qa_turns():
    # A short Q&A: counsel asks, witness answers; the bench interjects.
    return [
        Turn("CHAIRPERSON", "Please proceed.", 1, 1),
        Turn("ADV CHASKALSON SC", "Did you attend the meeting?", 1, 1),
        Turn("MR MOGOTSI", "Yes, I attended the meeting on that day.", 1, 1),
        Turn("ADV CHASKALSON SC", "And who else was present?", 1, 1),
        Turn("MR MOGOTSI", "The General was present, as was his colleague.", 1, 1),
        Turn("ADV CHASKALSON SC", "What did he say to you?", 1, 1),
        Turn("MR MOGOTSI", "He said the task team would be disbanded.", 1, 1),
        Turn("ADV CHASKALSON SC", "When did this happen?", 1, 1),
        Turn("MR MOGOTSI", "It happened in July of that year.", 1, 1),
        Turn("ADV CHASKALSON SC", "Are you certain of that?", 1, 1),
        Turn("MR MOGOTSI", "I am certain.", 1, 1),
        Turn("ADV CHASKALSON SC", "Thank you.", 1, 1),
    ]


def test_word_count_ignores_punctuation():
    assert word_count("Yes, I attended the meeting.") == 5


def test_detect_witness_is_the_answerer_not_the_title():
    # MR MOGOTSI answers 5 questions -> the witness, despite ADV speaking more turns.
    assert detect_witness(_qa_turns()) == "MR MOGOTSI"


def test_detect_witness_returns_none_without_enough_answers():
    turns = [
        Turn("ADV X SC", "A question?", 1, 1),
        Turn("ADV Y SC", "An answer.", 1, 1),
    ]
    assert detect_witness(turns) is None


def test_role_of_bench_witness_counsel_and_override():
    assert role_of("CHAIRPERSON", None, None) == "bench"
    assert role_of("COMMISSIONER SOME", None, None) == "bench"
    assert role_of("MR MOGOTSI", "MR MOGOTSI", None) == "witness"
    assert role_of("ADV CHASKALSON SC", "MR MOGOTSI", None) == "counsel"
    # explicit override wins
    assert role_of("ADV BEHARI", None, {"ADV BEHARI": "witness"}) == "witness"


def test_aggregate_and_summarise_role_shares():
    day = aggregate_day(day_no=36, date="2025-11-19", n_pages=79, turns=_qa_turns())
    assert day.witness == "MR MOGOTSI"
    assert set(day.role_words) <= {"bench", "witness", "counsel"}

    summary = summarise([day], n_chunks=199)
    t = summary["totals"]
    assert t["hearing_days"] == 1
    assert t["pages"] == 79
    assert t["turns"] == 12
    assert t["chunks"] == 199
    shares = summary["role_word_share_pct"]
    assert abs(sum(shares[r] for r in ("bench", "witness", "counsel")) - 100.0) < 0.5
    assert summary["per_day"][0]["witness"] == "MR MOGOTSI"
