from pathlib import Path

from commission_ingestion.discovery.madlanga import (
    MadlangaDiscoveryAdapter,
    _extract_day_and_date,
    classify_madlanga_link,
)


FIXTURE = Path(__file__).parent / "fixtures" / "madlanga_hearings.html"
EMBEDDED_FIXTURE = Path(__file__).parent / "fixtures" / "madlanga_hearing_embedded.html"
DAY109_FIXTURE = Path(__file__).parent / "fixtures" / "madlanga_hearing_day109.html"


def test_classify_record_pdf_as_transcript():
    source_type, document_type = classify_madlanga_link(
        "Day 59 Hearing Record",
        "MADLANGA_COMMISSION_RECORD_20260212.pdf",
        "https://criminaljusticecommission.org.za/hearing.php",
    )
    assert source_type == "transcript"
    assert document_type == "Transcript"


def test_classify_unknown_pdf_as_supporting_document():
    source_type, document_type = classify_madlanga_link(
        "Evidence bundle",
        "random_bundle.pdf",
        "https://criminaljusticecommission.org.za/hearing.php",
    )
    assert source_type == "supporting_document"
    assert document_type == "SupportingDocument"


def test_classify_second_interim_report_filename():
    source_type, document_type = classify_madlanga_link(
        "MADLANGA_SECOND_INTERIM",
        "MADLANGA_SECOND_INTERIM_29052026.pdf",
        "https://criminaljusticecommission.org.za/index.php?page=2",
    )
    assert source_type == "report"
    assert document_type == "Report"


def test_classify_interim_report_despite_statement_blurb():
    # Filename names the report artifact; the anchor blurb opens "STATEMENT BY".
    source_type, document_type = classify_madlanga_link(
        "STATEMENT BY JEREMY MICHAELS ... delivered its Interim Report to President",
        "CJSC_InterimReport_Delivered_17122025.pdf",
        "https://criminaljusticecommission.org.za/index.php?page=5",
    )
    assert source_type == "report"
    assert document_type == "Report"


def test_classify_statement_mentioning_report_stays_statement():
    # Filename names a STATEMENT artifact even though it mentions the report.
    source_type, document_type = classify_madlanga_link(
        "STATEMENT MADLANGA COMMISSION ... AHEAD OF SECOND INTERIM REPORT",
        "STATEMENT MADLANGA COMMISSION TO CONTINUE FOCUS ... SECOND INTERIM REPORT.pdf",
        "https://criminaljusticecommission.org.za/index.php?page=2",
    )
    assert source_type == "statement"
    assert document_type == "WitnessStatement"


def test_madlanga_discovery_from_anchor_fixture(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")

    def fake_resilient(url: str, **kwargs: object) -> str:
        if "hearing.php" in url:
            return html
        return ""

    monkeypatch.setattr(
        "commission_ingestion.discovery.madlanga.fetch_html_resilient",
        fake_resilient,
    )

    records = MadlangaDiscoveryAdapter().discover_sources()
    assert len(records) == 3

    record_map = {r.url.rsplit("/", 1)[-1]: r for r in records}
    record_pdf = record_map["MADLANGA_COMMISSION_RECORD_20260212.pdf"]
    assert record_pdf.source_type == "transcript"
    assert record_pdf.document_type == "Transcript"
    assert record_pdf.date == "2026-02-12"

    notice = record_map["misc_notice_jan2026.pdf"]
    assert notice.source_type == "notice"
    assert notice.document_type == "Notice"

    bundle = record_map["random_bundle.pdf"]
    assert bundle.source_type == "supporting_document"
    assert bundle.document_type == "SupportingDocument"


def test_madlanga_embedded_json_transcripts(monkeypatch):
    html = EMBEDDED_FIXTURE.read_text(encoding="utf-8")

    def fake_resilient(url: str, **kwargs: object) -> str:
        return html if "hearing.php" in url else ""

    monkeypatch.setattr(
        "commission_ingestion.discovery.madlanga.fetch_html_resilient",
        fake_resilient,
    )

    records = MadlangaDiscoveryAdapter().discover_sources()
    transcripts = [r for r in records if r.source_type == "transcript"]
    assert len(transcripts) >= 1
    t = transcripts[0]
    assert t.document_type == "Transcript"
    assert t.day_no == 59
    assert t.date == "2026-02-12"
    assert "MADLANGA_COMMISSION_RECORD_20260212.pdf" in t.url


def test_timestamp_prefixed_filename_date():
    day_no, date_str = _extract_day_and_date(
        "Transcript File",
        "https://criminaljusticecommission.org.za/uploads/"
        "1760640393_MADLANGA_COMMISSION_RECORD_20251016.pdf",
    )
    assert day_no is None
    assert date_str == "2025-10-16"


def test_textual_title_date():
    day_no, date_str = _extract_day_and_date(
        "Transcript - 16 OCTOBER 2025",
        "https://criminaljusticecommission.org.za/uploads/transcript.pdf",
    )
    assert day_no is None
    assert date_str == "2025-10-16"


def test_friday_title_does_not_extract_day_number():
    day_no, _ = _extract_day_and_date(
        "Friday 15 hearing summary",
        "https://criminaljusticecommission.org.za/uploads/summary.pdf",
    )
    assert day_no is None


def test_madlanga_blob_context_day_from_audio_sibling(monkeypatch):
    html = DAY109_FIXTURE.read_text(encoding="utf-8")

    def fake_resilient(url: str, **kwargs: object) -> str:
        return html if "hearing.php" in url else ""

    monkeypatch.setattr(
        "commission_ingestion.discovery.madlanga.fetch_html_resilient",
        fake_resilient,
    )

    records = MadlangaDiscoveryAdapter().discover_sources()
    transcripts = [r for r in records if r.source_type == "transcript"]
    assert len(transcripts) == 1
    transcript = transcripts[0]
    assert transcript.day_no == 109
    assert transcript.date == "2025-10-16"
    assert "1760640393_MADLANGA_COMMISSION_RECORD_20251016.pdf" in transcript.url
