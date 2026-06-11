"""Report generation for new-publication source checks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from commission_ingestion.models.source_record import SourceRecord

DEFAULT_REPORT_DIR = Path("reports/source-checks")


@dataclass
class DiscoveryResult:
    """Outcome of a discovery pass."""

    discovered_count: int
    new_records: list[SourceRecord]
    known_count: int
    non_authoritative_count: int

    @property
    def new_count(self) -> int:
        return len(self.new_records)


@dataclass
class DownloadStats:
    """Outcome of a download pass."""

    downloaded: int = 0
    skipped: int = 0
    missing: int = 0
    failed: int = 0


@dataclass
class SourceCheckReport:
    """Structured report for a source-check run."""

    run_at: datetime
    commission: str
    zondo_source: str | None
    discovery: DiscoveryResult
    download: DownloadStats | None = None
    new_records: list[SourceRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at.isoformat(),
            "commission": self.commission,
            "zondo_source": self.zondo_source,
            "summary": {
                "discovered": self.discovery.discovered_count,
                "new": self.discovery.new_count,
                "known": self.discovery.known_count,
                "non_authoritative": self.discovery.non_authoritative_count,
                "downloaded": self.download.downloaded if self.download else None,
                "skipped": self.download.skipped if self.download else None,
                "missing": self.download.missing if self.download else None,
                "failed": self.download.failed if self.download else None,
            },
            "new_publications": [_record_to_dict(r) for r in self.new_records],
        }


def _record_to_dict(record: SourceRecord) -> dict:
    return {
        "commission_slug": record.commission_slug,
        "commission_name": record.commission_name,
        "authoritative": record.authoritative,
        "source_type": record.source_type,
        "document_type": record.document_type,
        "title": record.title,
        "day_no": record.day_no,
        "date": record.date,
        "url": record.url,
        "source_page_url": record.source_page_url,
        "downloaded": record.downloaded,
        "local_path": record.local_path,
        "sha256": record.sha256,
        "notes": record.notes,
    }


def _format_record_line(index: int, record: SourceRecord) -> str:
    parts = [f"{index}. **{record.document_type}**"]
    if record.day_no is not None:
        parts.append(f"Day {record.day_no}")
    if record.date:
        parts.append(record.date)
    if record.title:
        parts.append(f"— {record.title}")
    header = " ".join(parts)
    status = "downloaded" if record.downloaded else "not downloaded"
    lines = [
        header,
        f"   - Commission: {record.commission_name} ({record.commission_slug})",
        f"   - Type: {record.source_type} / {record.document_type}",
        f"   - Authoritative: {record.authoritative}",
        f"   - URL: {record.url}",
    ]
    if record.source_page_url:
        lines.append(f"   - Source page: {record.source_page_url}")
    lines.append(f"   - Status: {status}")
    if record.local_path:
        lines.append(f"   - Local path: {record.local_path}")
    if record.sha256:
        lines.append(f"   - SHA256: {record.sha256}")
    if record.notes:
        lines.append(f"   - Notes: {record.notes}")
    return "\n".join(lines)


def render_markdown(report: SourceCheckReport) -> str:
    """Render a human-readable Markdown report."""
    s = report.discovery
    lines = [
        "# Source Check Report",
        "",
        f"- **Run at:** {report.run_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- **Commission:** {report.commission}",
    ]
    if report.zondo_source:
        lines.append(f"- **Zondo source:** {report.zondo_source}")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Discovered: {s.discovered_count}",
            f"- New: {s.new_count}",
            f"- Already known: {s.known_count}",
            f"- Non-authoritative: {s.non_authoritative_count}",
        ]
    )
    if report.download is not None:
        d = report.download
        lines.extend(
            [
                f"- Downloaded: {d.downloaded}",
                f"- Skipped: {d.skipped}",
                f"- Missing: {d.missing}",
                f"- Failed: {d.failed}",
            ]
        )
    lines.extend(["", "## New Publications", ""])
    if not report.new_records:
        lines.append("No new publications found in this run.")
    else:
        for i, record in enumerate(report.new_records, start=1):
            lines.append(_format_record_line(i, record))
            lines.append("")
    return "\n".join(lines)


def write_report(
    report: SourceCheckReport,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> tuple[Path, Path]:
    """Write JSON and Markdown reports. Returns (json_path, markdown_path)."""
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.run_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"source-check_{stamp}.json"
    md_path = report_dir / f"source-check_{stamp}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def resolve_new_records(
    registry_urls: dict[str, SourceRecord],
    new_urls: list[str],
) -> list[SourceRecord]:
    """Re-read new records from the registry after downloads."""
    resolved: list[SourceRecord] = []
    for url in new_urls:
        record = registry_urls.get(url)
        if record is not None:
            resolved.append(record)
    return resolved
