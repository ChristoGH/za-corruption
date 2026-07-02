"""Ingest video-only hearing days via YouTube caption tracks.

Two idempotent stages, both on the source registry:

  fetch  video records without a caption file get one fetched by yt-dlp
         (manual track preferred, else auto captions); the registry record
         gains local_path, sha256, and transcription_method.
  parse  fetched .vtt files become time-provenanced ChunkRecord JSONL in the
         same processed dir the PDF pipeline writes to, so load-qdrant and
         build-graph pick them up with no further wiring.

Ad-hoc registration for a day whose video is known but not yet discovered:

    ingest-video --url https://www.youtube.com/live/XXXX --day 130 --date 2026-07-01

Machine-transcribed text is never presented as official transcript: the
record is authoritative=false and every chunk carries time provenance
(time_start/time_end seconds) instead of page provenance.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from commission_ingestion.cli.parse_corpus import (
    DEFAULT_PROCESSED_DIR,
    _chunk_id,
)
from commission_ingestion.download.downloader import DEFAULT_RAW_DIR, sha256_file
from commission_ingestion.download.registry import (
    DEFAULT_REGISTRY_PATH,
    SourceRegistry,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.video.fetch import fetch_captions
from commission_ingestion.video.vtt import dedupe_rolling, parse_vtt, segment_cues

logger = logging.getLogger(__name__)

VIDEO_MANIFEST = "_video_manifest.jsonl"


def register_video(
    registry: SourceRegistry,
    *,
    commission: str,
    commission_name: str,
    url: str,
    day_no: int | None,
    date: str | None,
    title: str | None,
) -> SourceRecord:
    """Upsert one ad-hoc video record (idempotent by URL)."""
    record = SourceRecord(
        commission_slug=commission,
        commission_name=commission_name,
        authoritative=False,
        source_type="video",
        document_type="Video",
        title=title or (f"Day {day_no} video" if day_no else url),
        day_no=day_no,
        date=date,
        url=url,
    )
    merged, is_new = registry.upsert(record)
    logger.info("%s video record %s", "registered" if is_new else "updated", url)
    return merged


def fetch_pending(
    registry: SourceRegistry,
    commission: str,
    *,
    captions_dir: Path,
    limit: int | None = None,
    force: bool = False,
    runner=None,
) -> dict[str, int]:
    """Fetch caption tracks for video records that lack one."""
    stats = {"fetched": 0, "skipped": 0, "failed": 0}
    records = registry.filter(commission_slug=commission, source_type="video")
    records.sort(key=lambda r: (r.day_no is None, r.day_no or 0))
    if limit is not None:
        records = records[:limit]

    for record in records:
        if record.downloaded and record.local_path and not force:
            stats["skipped"] += 1
            continue
        result = fetch_captions(record.url, captions_dir, runner=runner)
        if result.vtt_path is None:
            stats["failed"] += 1
            logger.warning("no captions for %s: %s", record.url, result.detail)
            registry.upsert(
                record.model_copy(
                    update={"notes": f"Caption fetch failed: {result.detail}"}
                )
            )
            continue
        vtt_path = result.vtt_path
        if record.day_no is not None and not vtt_path.name.startswith("day"):
            named = vtt_path.with_name(f"day{record.day_no:03d}_{vtt_path.name}")
            vtt_path = vtt_path.replace(named)
        digest = sha256_file(vtt_path)
        registry.upsert(
            record.model_copy(
                update={
                    "downloaded": True,
                    "local_path": str(vtt_path),
                    "filename": vtt_path.name,
                    "sha256": digest,
                    "size_bytes": vtt_path.stat().st_size,
                    "content_type": "text/vtt",
                    "transcription_method": result.method,
                    "notes": None,
                }
            )
        )
        stats["fetched"] += 1
        logger.info(
            "day %s: captions -> %s (%s)", record.day_no, vtt_path.name, result.method
        )
    return stats


def parse_video_document(record: SourceRecord) -> tuple[list[ChunkRecord], str]:
    """Parse one fetched caption file into time-provenanced chunks."""
    if not record.local_path or not Path(record.local_path).exists():
        return [], "missing_file"
    text = Path(record.local_path).read_text(encoding="utf-8", errors="replace")
    cues = dedupe_rolling(parse_vtt(text))
    if not cues:
        return [], "no_cues"
    segments = segment_cues(cues)
    doc_sha = record.sha256 or ""
    chunks = [
        ChunkRecord(
            commission_slug=record.commission_slug,
            commission_name=record.commission_name,
            doc_sha256=doc_sha,
            source_url=record.url,
            source_page_url=record.source_page_url,
            day_no=record.day_no,
            date=record.date,
            chunk_id=_chunk_id(doc_sha, index, segment.text),
            chunk_index=index,
            page_start=None,
            page_end=None,
            time_start=segment.time_start,
            time_end=segment.time_end,
            speakers=[],
            n_turns=0,
            text=segment.text,
            char_count=segment.char_count,
        )
        for index, segment in enumerate(segments)
    ]
    return chunks, "ok"


def parse_fetched(
    registry: SourceRegistry,
    commission: str,
    *,
    processed_dir: Path,
    limit: int | None = None,
    force: bool = False,
) -> list[dict]:
    """Write chunk JSONL for every fetched caption file. Idempotent."""
    out_dir = processed_dir / commission
    out_dir.mkdir(parents=True, exist_ok=True)

    records = registry.filter(commission_slug=commission, source_type="video")
    records = [r for r in records if r.downloaded and r.local_path]
    records.sort(key=lambda r: (r.day_no is None, r.day_no or 0))
    if limit is not None:
        records = records[:limit]

    manifest: list[dict] = []
    for record in records:
        sha = (record.sha256 or "nosha")[:16]
        day = f"day{record.day_no:03d}_" if record.day_no is not None else ""
        out_path = out_dir / f"{day}video_{sha}.jsonl"
        if out_path.exists() and not force:
            manifest.append(_manifest_row(record, out_path, "skipped_exists"))
            continue
        try:
            chunks, status = parse_video_document(record)
        except Exception as exc:  # noqa: BLE001 - record, don't crash the run
            logger.exception("Caption parse failed for %s", record.url)
            manifest.append(_manifest_row(record, out_path, f"error:{exc}"))
            continue
        if status != "ok":
            logger.warning("%s: %s", status, record.url)
            manifest.append(_manifest_row(record, out_path, status, n_chunks=0))
            continue
        with out_path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")
        manifest.append(_manifest_row(record, out_path, "ok", n_chunks=len(chunks)))
        logger.info(
            "day %s: %d caption chunks -> %s",
            record.day_no, len(chunks), out_path.name,
        )

    with (out_dir / VIDEO_MANIFEST).open("w", encoding="utf-8") as handle:
        for row in manifest:
            handle.write(json.dumps(row) + "\n")
    return manifest


def _manifest_row(
    record: SourceRecord, out_path: Path, status: str, *, n_chunks: int | None = None
) -> dict:
    return {
        "day_no": record.day_no,
        "date": record.date,
        "doc_sha256": record.sha256,
        "transcription_method": record.transcription_method,
        "status": status,
        "n_chunks": n_chunks,
        "output": out_path.name,
        "url": record.url,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and parse YouTube captions for video-only hearing days."
    )
    parser.add_argument(
        "--commission", choices=["zondo", "madlanga"], default="madlanga"
    )
    parser.add_argument(
        "--commission-name", default=None,
        help="Display name for ad-hoc --url registration "
             "(default: Madlanga Commission / Zondo Commission).",
    )
    parser.add_argument("--url", default=None, help="Register one video URL ad hoc")
    parser.add_argument("--day", type=int, default=None, help="Hearing day for --url")
    parser.add_argument("--date", default=None, help="Hearing date (YYYY-MM-DD) for --url")
    parser.add_argument("--title", default=None, help="Title for --url")
    parser.add_argument(
        "--fetch", action="store_true", help="Fetch caption tracks (yt-dlp)"
    )
    parser.add_argument(
        "--parse", action="store_true", help="Parse fetched captions into chunk JSONL"
    )
    parser.add_argument("--captions-dir", type=Path, default=None,
                        help="Default: data/raw/<commission>/captions")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


_COMMISSION_NAMES = {
    "madlanga": "Madlanga Commission",
    "zondo": "Zondo Commission",
}


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    do_fetch = args.fetch or not (args.fetch or args.parse)
    do_parse = args.parse or not (args.fetch or args.parse)

    registry = SourceRegistry(args.registry)
    registry.load()

    if args.url:
        register_video(
            registry,
            commission=args.commission,
            commission_name=args.commission_name
            or _COMMISSION_NAMES[args.commission],
            url=args.url,
            day_no=args.day,
            date=args.date,
            title=args.title,
        )
        registry.save()

    captions_dir = args.captions_dir or (
        DEFAULT_RAW_DIR / args.commission / "captions"
    )

    fetch_stats = None
    if do_fetch:
        fetch_stats = fetch_pending(
            registry, args.commission,
            captions_dir=captions_dir,
            limit=args.limit,
            force=args.force,
        )
        registry.save()

    manifest = None
    if do_parse:
        manifest = parse_fetched(
            registry, args.commission,
            processed_dir=args.processed_dir,
            limit=args.limit,
            force=args.force,
        )

    print("Video ingest summary")
    print(f"  Commission:   {args.commission}")
    if fetch_stats is not None:
        print(f"  Captions fetched: {fetch_stats['fetched']}"
              f"  skipped: {fetch_stats['skipped']}"
              f"  failed: {fetch_stats['failed']}")
    failures = 0
    if manifest is not None:
        by_status: dict[str, int] = {}
        total_chunks = 0
        for row in manifest:
            key = row["status"].split(":", 1)[0]
            by_status[key] = by_status.get(key, 0) + 1
            total_chunks += row.get("n_chunks") or 0
        print(f"  Documents parsed: {len(manifest)}")
        for status, count in sorted(by_status.items()):
            print(f"    {status:16} {count}")
        print(f"  Total chunks: {total_chunks}")
        print(f"  Output dir:   {(args.processed_dir / args.commission).resolve()}")
        failures = sum(
            by_status.get(s, 0) for s in ("error", "missing_file", "no_cues")
        )
    if fetch_stats is not None:
        failures += fetch_stats["failed"]
    return 1 if failures > 0 else 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
