from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from commission_ingestion.download.downloader import (
    download_source,
    is_missing_at_source,
    safe_filename,
    sha256_file,
)
from commission_ingestion.models.source_record import SourceRecord


def test_safe_filename_strips_query_and_sanitizes():
    name = safe_filename(
        "https://example.com/files/Day%20327%20Transcript.pdf?token=abc",
        day_no=327,
    )
    assert name.endswith(".pdf")
    assert "?" not in name
    assert " " not in name


def test_safe_filename_preserves_txt_extension():
    name = safe_filename(
        "https://raw.githubusercontent.com/dsfsi/project-state-capture/main/data/interim/Day%20197%20-%202019-12-06.txt"
    )
    assert name.endswith(".txt")


def test_sha256_file(tmp_path: Path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.4 test content")
    digest = sha256_file(path)
    assert len(digest) == 64


def _base_record(url: str = "https://example.com/doc.pdf") -> SourceRecord:
    return SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url=url,
    )


def test_skip_when_already_hashed(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    out_dir = raw_dir / "zondo"
    out_dir.mkdir(parents=True)
    filename = safe_filename("https://example.com/doc.pdf")
    out_path = out_dir / filename
    out_path.write_bytes(b"%PDF-1.4 existing")

    digest = sha256_file(out_path)
    record = _base_record().model_copy(
        update={
            "downloaded": True,
            "sha256": digest,
            "filename": filename,
            "local_path": str(out_path),
        }
    )

    with patch("commission_ingestion.download.downloader.requests.get") as mock_get:
        updated = download_source(record, raw_dir=raw_dir, request_delay=0)
        mock_get.assert_not_called()

    assert updated.downloaded is True
    assert updated.sha256 == digest


def test_rejects_non_pdf_body(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    record = _base_record()

    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = lambda chunk_size: [b"<html>challenge</html>"]

    with patch(
        "commission_ingestion.download.downloader.requests.get",
        return_value=mock_response,
    ):
        updated = download_source(record, raw_dir=raw_dir, request_delay=0)

    assert updated.downloaded is False
    assert updated.notes is not None
    assert "not a PDF" in updated.notes


def test_accepts_valid_txt(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    record = _base_record(
        "https://raw.githubusercontent.com/dsfsi/project-state-capture/main/data/interim/Day%20197%20-%202019-12-06.txt"
    ).model_copy(update={"commission_slug": "zondo"})

    txt_bytes = b"Witness testimony for day 197.\n"

    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = lambda chunk_size: [txt_bytes]

    with patch(
        "commission_ingestion.download.downloader.requests.get",
        return_value=mock_response,
    ):
        updated = download_source(record, raw_dir=raw_dir, request_delay=0)

    assert updated.downloaded is True
    assert updated.filename.endswith(".txt")
    assert updated.sha256 is not None


def test_404_classified_as_missing_at_source(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    record = _base_record()

    response = requests.Response()
    response.status_code = 404

    with patch(
        "commission_ingestion.download.downloader.requests.get",
        side_effect=requests.HTTPError(response=response),
    ):
        updated = download_source(record, raw_dir=raw_dir, request_delay=0)

    assert updated.downloaded is False
    assert is_missing_at_source(updated)
    assert "HTTP 404" in (updated.notes or "")


def test_accepts_valid_pdf(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    record = _base_record()

    pdf_bytes = b"%PDF-1.4\n% test pdf"

    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "application/pdf"}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = lambda chunk_size: [pdf_bytes]

    with patch(
        "commission_ingestion.download.downloader.requests.get",
        return_value=mock_response,
    ):
        updated = download_source(record, raw_dir=raw_dir, request_delay=0)

    assert updated.downloaded is True
    assert updated.sha256 is not None
    assert updated.size_bytes == len(pdf_bytes)
    assert updated.content_type == "application/pdf"
