"""CLI for commission source discovery and download."""

from __future__ import annotations

import argparse
import logging
import sys
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
) -> tuple[int, int, int, int]:
    """Discover sources and upsert into registry.

    Returns (discovered, new, known, non_authoritative).
    """
    slugs = ["zondo", "madlanga"] if commission == "both" else [commission]
    discovered = 0
    new_count = 0
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
            _, is_new = registry.upsert(record)
            if is_new:
                new_count += 1
            else:
                known_count += 1

    registry.save()
    return discovered, new_count, known_count, non_authoritative


def run_downloads(
    registry: SourceRegistry,
    commission: str,
    *,
    force: bool = False,
    raw_dir: Path | None = None,
) -> tuple[int, int, int, int]:
    """Download pending records for the selected commission(s).

    Returns (downloaded, skipped, missing, failed).
    """
    slugs = {"zondo", "madlanga"} if commission == "both" else {commission}
    downloaded = 0
    skipped = 0
    missing = 0
    failed = 0

    for record in registry.all():
        if record.commission_slug not in slugs:
            continue
        if record.downloaded and not force:
            skipped += 1
            continue
        try:
            updated = download_source(
                record,
                raw_dir=raw_dir or Path("data/raw"),
                force=force,
            )
            registry.upsert(updated)
            if updated.downloaded:
                downloaded += 1
            elif is_missing_at_source(updated):
                missing += 1
            else:
                failed += 1
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
            failed += 1

    registry.save()
    return downloaded, skipped, missing, failed


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
        help="Discover sources, then download files",
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

    discovered, new_count, known_count, non_auth = run_discovery(
        args.commission,
        registry,
        zondo_source=args.zondo_source,
    )

    downloaded = 0
    skipped = 0
    missing = 0
    failed = 0
    if args.download:
        downloaded, skipped, missing, failed = run_downloads(
            registry,
            args.commission,
            force=args.force,
            raw_dir=args.raw_dir,
        )
        _log_duplicate_sha256_groups(registry)

    print("Source retrieval summary")
    print(f"  Commission:       {args.commission}")
    if args.commission in {"zondo", "both"}:
        print(f"  Zondo source:     {args.zondo_source}")
    print(f"  Discovered:       {discovered}")
    print(f"  New:              {new_count}")
    print(f"  Already known:    {known_count}")
    print(f"  Non-authoritative:{non_auth}")
    if args.download:
        print(f"  Downloaded:       {downloaded}")
        print(f"  Skipped:          {skipped}")
        print(f"  Missing:          {missing}")
        print(f"  Failed:           {failed}")
    print(f"  Registry (total): {len(registry.known_urls())} (was {known_before})")
    print(f"  Registry path:    {args.registry.resolve()}")

    return 1 if failed > 0 else 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
