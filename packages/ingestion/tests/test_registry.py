from pathlib import Path

from commission_ingestion.download.registry import SourceRegistry
from commission_ingestion.models.source_record import SourceRecord


def _record(url: str, *, sha256: str | None = None, downloaded: bool = False) -> SourceRecord:
    return SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url=url,
        sha256=sha256,
        downloaded=downloaded,
        local_path="/tmp/x.pdf" if downloaded else None,
        filename="x.pdf" if downloaded else None,
        size_bytes=100 if downloaded else None,
    )


def test_url_dedup(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    r1 = SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url="https://example.com/a.pdf",
        day_no=1,
    )
    r2 = SourceRecord(
        commission_slug="zondo",
        commission_name="Zondo Commission",
        source_type="transcript",
        document_type="Transcript",
        url="https://example.com/a.pdf",
        day_no=1,
        title="Updated title",
    )
    _, is_new1 = registry.upsert(r1)
    _, is_new2 = registry.upsert(r2)
    assert is_new1 is True
    assert is_new2 is False
    assert len(registry.all()) == 1
    assert registry.all()[0].title == "Updated title"


def test_download_metadata_update(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    discovered = _record("https://example.com/a.pdf")
    registry.upsert(discovered)

    downloaded = _record(
        "https://example.com/a.pdf",
        sha256="abc123",
        downloaded=True,
    )
    registry.upsert(downloaded)

    stored = registry.get("https://example.com/a.pdf")
    assert stored is not None
    assert stored.downloaded is True
    assert stored.sha256 == "abc123"


def test_duplicate_sha256_groups_non_destructive(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    registry.upsert(
        _record("https://example.com/a.pdf", sha256="samehash", downloaded=True)
    )
    registry.upsert(
        _record("https://example.com/b.pdf", sha256="samehash", downloaded=True)
    )
    groups = registry.duplicate_sha256_groups()
    assert "samehash" in groups
    assert len(groups["samehash"]) == 2
    assert len(registry.all()) == 2


def test_filter_by_commission_and_source_type(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    registry.upsert(_record("https://example.com/a.pdf"))
    registry.upsert(
        SourceRecord(
            commission_slug="madlanga",
            commission_name="Madlanga Commission",
            source_type="notice",
            document_type="Notice",
            url="https://example.com/notice.pdf",
        )
    )
    zondo = registry.filter(commission_slug="zondo")
    notices = registry.filter(source_type="notice")
    assert len(zondo) == 1
    assert len(notices) == 1
