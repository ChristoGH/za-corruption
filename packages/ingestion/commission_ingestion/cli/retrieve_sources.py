"""CLI for commission source discovery and download."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from commission_ingestion.discovery.madlanga import MadlangaDiscoveryAdapter
from commission_ingestion.discovery.zondo import ZondoDiscoveryAdapter
from commission_ingestion.discovery.zondo_bootstrap import ZondoBootstrapDiscoveryAdapter
from commission_ingestion.download.downloader import (
    download_source,
    is_missing_at_source,
)
from commission_ingestion.download.registry import DEFAULT_REGISTRY_PATH, SourceRegistry
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.reporting.source_check import (
    DEFAULT_REPORT_DIR,
    DiscoveryResult,
    DownloadStats,
    SourceCheckReport,
    resolve_new_records,
    write_report,
)

logger = logging.getLogger(__name__)


def _discover_zondo(zondo_source: str) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    if zondo_source in {"bootstrap", "both"}:
        records.extend(ZondoBootstrapDiscoveryAdapter().discover_sources())
    if zondo_source in {"official", "both"}:
        records.extend(ZondoDiscoveryAdapter().discover_sources())
    return _dedupe_by_url(records)


def _dedupe_by_url(records: list[SourceRecord]) -> list[SourceRecord]:
    seen: set[str] = set()
    unique: list[SourceRecord] = []
    for record in records:
        if record.url in seen:
            continue
        seen.add(record.url)
        unique.append(record)
    return unique


def run_discovery(
    commission: str,
    registry: SourceRegistry,
    *,
    zondo_source: str = "bootstrap",
) -> DiscoveryResult:
    """Discover sources and upsert into registry."""
    slugs = ["zondo", "madlanga"] if commission == "both" else [commission]
    discovered = 0
    new_records: list[SourceRecord] = []
    known_count = 0
    non_authoritative = 0

    for slug in slugs:
        if slug == "zondo":
            records = _discover_zondo(zondo_source)
        else:
            records = MadlangaDiscoveryAdapter().discover_sources()

        discovered += len(records)
        non_authoritative += sum(1 for r in records if not r.authoritative)

        for record in records:
            merged, is_new = registry.upsert(record)
            if is_new:
                new_records.append(merged)
            else:
                known_count += 1

    registry.save()
    return DiscoveryResult(
        discovered_count=discovered,
        new_records=new_records,
        known_count=known_count,
        non_authoritative_count=non_authoritative,
    )


def run_downloads(
    registry: SourceRegistry,
    commission: str,
    *,
    force: bool = False,
    raw_dir: Path | None = None,
    only_urls: set[str] | None = None,
) -> DownloadStats:
    """Download pending records for the selected commission(s)."""
    slugs = {"zondo", "madlanga"} if commission == "both" else {commission}
    stats = DownloadStats()

    for record in registry.all():
        if record.commission_slug not in slugs:
            continue
        if only_urls is not None and record.url not in only_urls:
            continue
        if record.downloaded and not force:
            stats.skipped += 1
            continue
        if record.source_type == "video":
            # Video sources are ingested via `ingest-video` (caption fetch),
            # never by HTTP download of the page URL.
            stats.skipped += 1
            continue
        try:
            updated = download_source(
                record,
                raw_dir=raw_dir or Path("data/raw"),
                force=force,
            )
            registry.upsert(updated)
            if updated.downloaded:
                stats.downloaded += 1
            elif is_missing_at_source(updated):
                stats.missing += 1
            else:
                stats.failed += 1
        except Exception as exc:
            logger.exception("Download failed for %s", record.url)
            registry.upsert(
                record.model_copy(
                    update={
                        "downloaded": False,
                        "notes": f"Download failed: {exc}",
                    }
                )
            )
            stats.failed += 1

    registry.save()
    return stats


def _log_duplicate_sha256_groups(registry: SourceRegistry) -> None:
    groups = registry.duplicate_sha256_groups()
    if not groups:
        return
    logger.info("Duplicate SHA256 groups (non-destructive, all URLs retained):")
    for digest, records in groups.items():
        logger.info("  %s: %d URLs", digest[:12], len(records))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover and download official commission source documents."
    )
    parser.add_argument(
        "--commission",
        choices=["zondo", "madlanga", "both"],
        required=True,
        help="Commission to process",
    )
    parser.add_argument(
        "--zondo-source",
        choices=["official", "bootstrap", "both"],
        default="bootstrap",
        help=(
            "Zondo discovery source: bootstrap (DSFSI plaintext, default), "
            "official (Cloudflare-blocked without manual session), or both"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--discover-only",
        action="store_true",
        help="Discover sources and update registry (default when --download is omitted)",
    )
    mode.add_argument(
        "--download",
        action="store_true",
        help="Discover sources, then download all pending files",
    )
    mode.add_argument(
        "--download-new-only",
        action="store_true",
        help="Discover sources, then download only records newly found in this run",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="Path to source_registry.jsonl",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory for downloaded files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when SHA256 is already recorded",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write JSON and Markdown reports for this run",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory for generated reports (default: reports/source-checks)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    registry = SourceRegistry(args.registry)
    registry.load()
    known_before = len(registry.known_urls())
    run_at = datetime.now(timezone.utc)

    discovery = run_discovery(
        args.commission,
        registry,
        zondo_source=args.zondo_source,
    )
    new_urls = [r.url for r in discovery.new_records]

    download_stats: DownloadStats | None = None
    if args.download or args.download_new_only:
        only_urls = set(new_urls) if args.download_new_only else None
        download_stats = run_downloads(
            registry,
            args.commission,
            force=args.force,
            raw_dir=args.raw_dir,
            only_urls=only_urls,
        )
        _log_duplicate_sha256_groups(registry)

    report_records = resolve_new_records(
        {r.url: r for r in registry.all()},
        new_urls,
    )

    print("Source retrieval summary")
    print(f"  Commission:       {args.commission}")
    if args.commission in {"zondo", "both"}:
        print(f"  Zondo source:     {args.zondo_source}")
    print(f"  Discovered:       {discovery.discovered_count}")
    print(f"  New:              {discovery.new_count}")
    print(f"  Already known:    {discovery.known_count}")
    print(f"  Non-authoritative:{discovery.non_authoritative_count}")
    if download_stats is not None:
        print(f"  Downloaded:       {download_stats.downloaded}")
        print(f"  Skipped:          {download_stats.skipped}")
        print(f"  Missing:          {download_stats.missing}")
        print(f"  Failed:           {download_stats.failed}")
    print(f"  Registry (total): {len(registry.known_urls())} (was {known_before})")
    print(f"  Registry path:    {args.registry.resolve()}")

    if args.write_report:
        report = SourceCheckReport(
            run_at=run_at,
            commission=args.commission,
            zondo_source=args.zondo_source if args.commission in {"zondo", "both"} else None,
            discovery=discovery,
            download=download_stats,
            new_records=report_records,
        )
        json_path, md_path = write_report(report, report_dir=args.report_dir)
        print(f"  Report (JSON):    {json_path.resolve()}")
        print(f"  Report (MD):      {md_path.resolve()}")

    failed = download_stats.failed if download_stats is not None else 0
    return 1 if failed > 0 else 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
