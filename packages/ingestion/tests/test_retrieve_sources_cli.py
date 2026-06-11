"""Tests for retrieve-sources CLI publication monitor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from commission_ingestion.cli.retrieve_sources import run_cli, run_discovery, run_downloads
from commission_ingestion.download.registry import SourceRegistry
from commission_ingestion.models.source_record import SourceRecord


def _record(
    url: str,
    *,
    commission_slug: str = "madlanga",
    downloaded: bool = False,
) -> SourceRecord:
    return SourceRecord(
        commission_slug=commission_slug,
        commission_name="Madlanga Commission",
        source_type="transcript",
        document_type="Transcript",
        url=url,
        title=f"Transcript at {url.rsplit('/', 1)[-1]}",
        day_no=110,
        date="2026-06-10",
        downloaded=downloaded,
    )


def test_run_discovery_returns_new_records(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    registry.upsert(_record("https://example.com/existing.pdf"))

    new_record = _record("https://example.com/new.pdf")

    with patch(
        "commission_ingestion.cli.retrieve_sources.MadlangaDiscoveryAdapter"
    ) as mock_adapter:
        mock_adapter.return_value.discover_sources.return_value = [
            _record("https://example.com/existing.pdf"),
            new_record,
        ]
        result = run_discovery("madlanga", registry)

    assert result.discovered_count == 2
    assert result.new_count == 1
    assert result.known_count == 1
    assert len(result.new_records) == 1
    assert result.new_records[0].url == "https://example.com/new.pdf"


def test_run_discovery_known_on_second_run(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    record = _record("https://example.com/same.pdf")

    with patch(
        "commission_ingestion.cli.retrieve_sources.MadlangaDiscoveryAdapter"
    ) as mock_adapter:
        mock_adapter.return_value.discover_sources.return_value = [record]
        first = run_discovery("madlanga", registry)
        second = run_discovery("madlanga", registry)

    assert first.new_count == 1
    assert second.new_count == 0
    assert second.known_count == 1


def test_run_downloads_only_urls(tmp_path: Path):
    registry = SourceRegistry(tmp_path / "registry.jsonl")
    new_url = "https://example.com/new.pdf"
    old_pending = "https://example.com/old-pending.pdf"
    registry.upsert(_record(new_url))
    registry.upsert(_record(old_pending))

    downloaded_record = _record(new_url, downloaded=True).model_copy(
        update={"sha256": "abc", "local_path": "/tmp/new.pdf", "filename": "new.pdf"}
    )

    with patch(
        "commission_ingestion.cli.retrieve_sources.download_source",
        return_value=downloaded_record,
    ) as mock_download:
        stats = run_downloads(
            registry,
            "madlanga",
            raw_dir=tmp_path / "raw",
            only_urls={new_url},
        )

    assert stats.downloaded == 1
    assert mock_download.call_count == 1
    assert mock_download.call_args[0][0].url == new_url


def test_cli_write_report_with_no_new_publications(tmp_path: Path, capsys):
    registry_path = tmp_path / "registry.jsonl"
    report_dir = tmp_path / "reports"

    with patch(
        "commission_ingestion.cli.retrieve_sources.MadlangaDiscoveryAdapter"
    ) as mock_adapter:
        mock_adapter.return_value.discover_sources.return_value = []
        exit_code = run_cli(
            [
                "--commission",
                "madlanga",
                "--discover-only",
                "--write-report",
                "--registry",
                str(registry_path),
                "--report-dir",
                str(report_dir),
            ]
        )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "New:              0" in output

    json_files = list(report_dir.glob("source-check_*.json"))
    md_files = list(report_dir.glob("source-check_*.md"))
    assert len(json_files) == 1
    assert len(md_files) == 1

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["summary"]["new"] == 0
    assert payload["new_publications"] == []
    assert "No new publications found" in md_files[0].read_text(encoding="utf-8")


def test_cli_download_new_only_and_report(tmp_path: Path, capsys):
    registry_path = tmp_path / "registry.jsonl"
    report_dir = tmp_path / "reports"
    new_url = "https://example.com/brand-new.pdf"
    old_pending = "https://example.com/stale-pending.pdf"

    registry = SourceRegistry(registry_path)
    registry.upsert(_record(old_pending))
    registry.save()

    downloaded = _record(new_url, downloaded=True).model_copy(
        update={
            "sha256": "deadbeef",
            "local_path": str(tmp_path / "raw" / "madlanga" / "brand-new.pdf"),
            "filename": "brand-new.pdf",
        }
    )

    with (
        patch(
            "commission_ingestion.cli.retrieve_sources.MadlangaDiscoveryAdapter"
        ) as mock_adapter,
        patch(
            "commission_ingestion.cli.retrieve_sources.download_source",
            return_value=downloaded,
        ) as mock_download,
    ):
        mock_adapter.return_value.discover_sources.return_value = [_record(new_url)]
        exit_code = run_cli(
            [
                "--commission",
                "madlanga",
                "--download-new-only",
                "--write-report",
                "--registry",
                str(registry_path),
                "--report-dir",
                str(report_dir),
                "--raw-dir",
                str(tmp_path / "raw"),
            ]
        )

    assert exit_code == 0
    assert mock_download.call_count == 1
    assert mock_download.call_args[0][0].url == new_url

    payload = json.loads(list(report_dir.glob("source-check_*.json"))[0].read_text())
    assert payload["summary"]["new"] == 1
    assert payload["summary"]["downloaded"] == 1
    assert len(payload["new_publications"]) == 1
    assert payload["new_publications"][0]["url"] == new_url
    assert payload["new_publications"][0]["downloaded"] is True
    assert payload["new_publications"][0]["sha256"] == "deadbeef"

    output = capsys.readouterr().out
    assert "New:              1" in output
    assert "Downloaded:       1" in output
