import pytest
from pydantic import ValidationError

from commission_ingestion.models.source_record import SourceRecord


def test_valid_source_record():
    record = SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url="https://www.statecapture.org.za/uploads/day_1.pdf",
        source_page_url="https://www.statecapture.org.za/site/transcripts",
    )
    assert record.schema_version == "1.1"
    assert record.authoritative is True
    assert record.commission_slug == "zondo"


def test_authoritative_defaults_true():
    record = SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url="https://example.com/a.txt",
    )
    assert record.authoritative is True


def test_non_authoritative_bootstrap():
    record = SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url="https://example.com/a.txt",
        authoritative=False,
        notes="bootstrap",
    )
    assert record.authoritative is False


def test_invalid_commission_slug():
    with pytest.raises(ValidationError):
        SourceRecord(
            commission_slug="other",
            commission_name="Other",
            source_type="transcript",
            document_type="Transcript",
            url="https://example.com/a.pdf",
        )


def test_invalid_url_scheme():
    with pytest.raises(ValidationError):
        SourceRecord(
            commission_slug="zondo",
            commission_name="Zondo Commission",
            source_type="transcript",
            document_type="Transcript",
            url="ftp://example.com/a.pdf",
        )


def test_invalid_source_type():
    with pytest.raises(ValidationError):
        SourceRecord(
            commission_slug="zondo",
            commission_name="Zondo Commission",
            source_type="hearing_record",
            document_type="Transcript",
            url="https://example.com/a.pdf",
        )


def test_invalid_document_type():
    with pytest.raises(ValidationError):
        SourceRecord(
            commission_slug="zondo",
            commission_name="Zondo Commission",
            source_type="transcript",
            document_type="HearingRecord",
            url="https://example.com/a.pdf",
        )
