"""Integrity-pass tests — synthetic fixtures only, never the real corpus.

The fixtures replay the real failure modes: the same sitting published twice
(full containment), a partial publication, and a transcript whose running
footer contradicts the registry's day number (the real day-80 record says
"DAY 90" in its footer).
"""

from __future__ import annotations

import fitz
import pytest

from commission_ingestion.analysis.integrity import (
    DocInfo,
    candidate_pairs,
    check_corpus,
    containment,
    reconcile_summary,
)
from commission_ingestion.cli.corpus_stats import (
    compute,
    parse_documents,
    split_records,
)
from commission_ingestion.download.registry import SourceRegistry
from commission_ingestion.models.source_record import SourceRecord


def make_record(*, day_no: int, date: str, sha: str, **overrides) -> SourceRecord:
    defaults = dict(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        source_type="transcript",
        document_type="Transcript",
        day_no=day_no,
        date=date,
        url=f"https://example.org/day{day_no}-{sha[:4]}.pdf",
        filename=f"day{day_no}-{sha[:4]}.pdf",
        downloaded=True,
        local_path=f"/tmp/day{day_no}-{sha[:4]}.pdf",
        sha256=sha * 16,
    )
    defaults.update(overrides)
    return SourceRecord(**defaults)


def make_doc(
    *, day_no: int, date: str, sha: str, words: list[str], n_pages: int = 100
) -> DocInfo:
    record = make_record(day_no=day_no, date=date, sha=sha)
    return DocInfo(record=record, n_pages=n_pages, page_texts=[" ".join(words)])


def _words(start: int, count: int) -> list[str]:
    return [f"testimony{i}" for i in range(start, start + count)]


def test_candidate_pairs_same_day_same_date_and_adjacent_only():
    same_day_a = make_doc(day_no=15, date="2025-10-20", sha="aa01", words=_words(0, 50))
    same_day_b = make_doc(day_no=15, date="2025-10-21", sha="bb02", words=_words(100, 50))
    same_date = make_doc(day_no=16, date="2025-10-21", sha="cc03", words=_words(200, 50))
    far_away = make_doc(day_no=40, date="2025-12-01", sha="dd04", words=_words(300, 50))

    pairs = candidate_pairs([same_day_a, same_day_b, same_date, far_away])
    keyed = {
        tuple(sorted((a.record.sha256[:4], b.record.sha256[:4]))) for a, b in pairs
    }
    assert ("aa01", "bb02") in keyed  # same day_no
    assert ("bb02", "cc03") in keyed  # same date (and adjacent day)
    assert ("aa01", "cc03") in keyed  # adjacent day_no
    assert not any("dd04" in pair for pair in keyed)


def test_full_containment_is_flagged_as_duplicate():
    # The day-80 incident: the "partial" is wholly contained in the full record.
    full = make_doc(day_no=80, date="2026-03-18", sha="f0f0", words=_words(0, 600))
    partial = make_doc(
        day_no=80, date="2026-03-18", sha="0e0e", words=_words(0, 400), n_pages=70
    )
    result = containment(partial, full)
    assert result.a_in_b > 0.95
    assert result.is_duplicate

    report = check_corpus([full, partial], [], expected_active_records=2)
    assert not report.ok
    assert any("duplicate content" in err for err in report.errors)
    assert 80 in report.multi_doc_days


def test_distinct_same_day_documents_are_not_duplicates():
    # The day-15 situation: two sittings under one day number, disjoint content.
    sitting_a = make_doc(day_no=15, date="2025-10-20", sha="a1a1", words=_words(0, 400))
    sitting_b = make_doc(day_no=15, date="2025-10-21", sha="b2b2", words=_words(1000, 400))
    report = check_corpus([sitting_a, sitting_b], [], expected_active_records=2)
    assert report.ok
    assert 15 in report.multi_doc_days  # still surfaced for human eyes


def test_superseded_records_are_excluded_from_active_set(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    keeper = make_record(day_no=80, date="2026-03-18", sha="f0f0")
    loser = make_record(
        day_no=80,
        date="2026-03-18",
        sha="0e0e",
        superseded_by=keeper.sha256,
        notes="partial publication",
    )
    registry.upsert(keeper)
    registry.upsert(loser)

    active, superseded = split_records(registry, "madlanga")
    assert [r.sha256 for r in active] == [keeper.sha256]
    assert [r.sha256 for r in superseded] == [loser.sha256]

    # With the loser excluded, the corpus is clean — and the exclusion is reported.
    doc = make_doc(day_no=80, date="2026-03-18", sha="f0f0", words=_words(0, 600))
    report = check_corpus([doc], superseded, expected_active_records=len(active))
    assert report.ok
    assert report.superseded == superseded


def test_reconciliation_fails_when_a_document_is_silently_dropped():
    doc = make_doc(day_no=1, date="2025-09-17", sha="aaaa", words=_words(0, 50))
    report = check_corpus([doc], [], expected_active_records=2)
    assert not report.ok
    assert any("reconciliation" in err for err in report.errors)


def test_reconcile_summary_flags_page_and_day_mismatches():
    doc = make_doc(day_no=1, date="2025-09-17", sha="aaaa", words=_words(0, 50), n_pages=80)
    good = {"totals": {"pages": 80, "hearing_days": 1}}
    assert reconcile_summary([doc], good) == []

    bad_pages = {"totals": {"pages": 99, "hearing_days": 1}}
    bad_days = {"totals": {"pages": 80, "hearing_days": 3}}
    assert any("pages" in e for e in reconcile_summary([doc], bad_pages))
    assert any("day" in e for e in reconcile_summary([doc], bad_days))


def test_page_outliers_are_reported_but_not_errors():
    docs = [
        make_doc(day_no=i, date=f"2025-09-{i:02d}", sha=f"a{i:03d}", words=_words(i * 100, 30), n_pages=100)
        for i in range(1, 6)
    ] + [
        make_doc(day_no=6, date="2025-09-06", sha="cafe", words=_words(900, 30), n_pages=500)
    ]
    report = check_corpus(docs, [], expected_active_records=6)
    assert report.ok
    assert 6 in report.outlier_days


@pytest.fixture()
def contradictory_footer_pdf(tmp_path):
    """A born-digital fixture transcript whose running footer says DAY 90 —
    replaying the real day-80 record. The registry says day 80; the registry
    must win everywhere."""
    path = tmp_path / "day80_fixture.pdf"
    pdf = fitz.open()
    for _ in range(2):
        page = pdf.new_page()
        y = 72.0
        for line in [
            "JUDICIAL COMMISSION OF INQUIRY",
            "CHAIRPERSON:   Please proceed with the evidence for today.",
            "MR NKOSI:   Thank you Chairperson, I confirm my earlier statement.",
            "CHAIRPERSON:   And were you present at the meeting in question?",
            "MR NKOSI:   Yes, I was present together with my commander that day.",
            "18 MARCH 2026 – DAY 90",
        ]:
            page.insert_text((72, y), line)
            y += 18
    pdf.save(path)
    pdf.close()
    return path


def test_day_no_comes_from_registry_never_from_footers(contradictory_footer_pdf):
    record = make_record(
        day_no=80,
        date="2026-03-18",
        sha="80f0",
        local_path=str(contradictory_footer_pdf),
    )
    parsed = parse_documents([record])
    assert len(parsed) == 1 and parsed[0].turns  # the fixture really parses

    summary = compute(parsed, n_chunks=None, role_map={})
    (day,) = summary["per_day"]
    assert day["day_no"] == 80  # registry value, not the "DAY 90" footer
    assert day["date"] == "2026-03-18"
