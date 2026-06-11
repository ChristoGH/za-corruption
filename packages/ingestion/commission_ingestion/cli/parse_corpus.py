"""Parse downloaded transcripts into speaker-aware chunk JSONL.

Deterministic, idempotent: reads the source registry, parses each downloaded
transcript PDF into ChunkRecords, and writes one JSONL per document plus a
run manifest. Re-running is a no-op for documents already processed (output is
content-addressed by the document SHA256).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

from commission_ingestion.download.registry import (
    DEFAULT_REGISTRY_PATH,
    SourceRegistry,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.parsing import (
    chunk_turns,
    detect_turns,
    extract_pages,
    is_scanned,
    reflow_pages,
)

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_DIR = Path("data/processed")


def _chunk_id(doc_sha256: str, chunk_index: int, text: str) -> str:
    """Unique, deterministic chunk id.

    Keyed on document + position + text (not text alone): identical short turns
    ("Thank you, Chair.") recur across the corpus, so a text-only hash collides —
    which would break chunk_id as a unique key in Qdrant/Neo4j.
    """
    key = f"{doc_sha256}:{chunk_index}:{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_document(record: SourceRecord) -> tuple[list[ChunkRecord], str]:
    """Parse one downloaded transcript. Returns (chunks, status)."""
    if not record.local_path or not Path(record.local_path).exists():
        return [], "missing_file"

    pages = extract_pages(record.local_path)
    if is_scanned(pages):
        return [], "needs_ocr"

    reflowed = reflow_pages(pages)
    turns = detect_turns(reflowed)
    if not turns:
        return [], "no_turns"

    chunks = chunk_turns(turns)
    records: list[ChunkRecord] = []
    for index, chunk in enumerate(chunks):
        records.append(
            ChunkRecord(
                commission_slug=record.commission_slug,
                commission_name=record.commission_name,
                doc_sha256=record.sha256 or "",
                source_url=record.url,
                source_page_url=record.source_page_url,
                day_no=record.day_no,
                date=record.date,
                chunk_id=_chunk_id(record.sha256 or "", index, chunk.text),
                chunk_index=index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                speakers=chunk.speakers,
                n_turns=chunk.n_turns,
                text=chunk.text,
                char_count=chunk.char_count,
            )
        )
    return records, "ok"


def _output_path(out_dir: Path, record: SourceRecord) -> Path:
    sha = (record.sha256 or "nosha")[:16]
    day = f"day{record.day_no:03d}_" if record.day_no is not None else ""
    return out_dir / f"{day}{sha}.jsonl"


def run_parse(
    registry: SourceRegistry,
    commission: str,
    *,
    processed_dir: Path,
    day: int | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[dict]:
    out_dir = processed_dir / commission
    out_dir.mkdir(parents=True, exist_ok=True)

    transcripts = registry.filter(
        commission_slug=commission, source_type="transcript"
    )
    transcripts = [r for r in transcripts if r.downloaded]
    if day is not None:
        transcripts = [r for r in transcripts if r.day_no == day]
    transcripts.sort(key=lambda r: (r.day_no is None, r.day_no or 0))
    if limit is not None:
        transcripts = transcripts[:limit]

    manifest: list[dict] = []
    for record in transcripts:
        out_path = _output_path(out_dir, record)
        if out_path.exists() and not force:
            manifest.append(_manifest_row(record, out_path, "skipped_exists"))
            continue
        try:
            chunks, status = parse_document(record)
        except Exception as exc:  # noqa: BLE001 - record, don't crash the run
            logger.exception("Parse failed for %s", record.url)
            manifest.append(_manifest_row(record, out_path, f"error:{exc}"))
            continue

        if status != "ok":
            logger.warning("%s: %s", status, record.url)
            manifest.append(_manifest_row(record, out_path, status, n_chunks=0))
            continue

        with out_path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")
        manifest.append(
            _manifest_row(record, out_path, "ok", n_chunks=len(chunks))
        )
        logger.info("day %s: %d chunks -> %s", record.day_no, len(chunks), out_path.name)

    _write_manifest(out_dir, manifest)
    return manifest


def _manifest_row(
    record: SourceRecord, out_path: Path, status: str, *, n_chunks: int | None = None
) -> dict:
    return {
        "day_no": record.day_no,
        "date": record.date,
        "doc_sha256": record.sha256,
        "status": status,
        "n_chunks": n_chunks,
        "output": out_path.name,
        "url": record.url,
    }


def _write_manifest(out_dir: Path, manifest: list[dict]) -> None:
    with (out_dir / "_parse_manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in manifest:
            handle.write(json.dumps(row) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse downloaded transcripts into speaker-aware chunk JSONL."
    )
    parser.add_argument(
        "--commission", choices=["zondo", "madlanga"], default="madlanga"
    )
    parser.add_argument("--day", type=int, default=None, help="Parse only this hearing day")
    parser.add_argument("--limit", type=int, default=None, help="Cap documents processed")
    parser.add_argument("--force", action="store_true", help="Re-parse even if output exists")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    registry = SourceRegistry(args.registry)
    registry.load()

    manifest = run_parse(
        registry,
        args.commission,
        processed_dir=args.processed_dir,
        day=args.day,
        limit=args.limit,
        force=args.force,
    )

    by_status: dict[str, int] = {}
    total_chunks = 0
    for row in manifest:
        key = row["status"].split(":", 1)[0]
        by_status[key] = by_status.get(key, 0) + 1
        total_chunks += row.get("n_chunks") or 0

    print("Parse summary")
    print(f"  Commission:   {args.commission}")
    print(f"  Documents:    {len(manifest)}")
    for status, count in sorted(by_status.items()):
        print(f"    {status:16} {count}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Output dir:   {(args.processed_dir / args.commission).resolve()}")

    failures = sum(
        by_status.get(s, 0) for s in ("error", "missing_file", "no_turns")
    )
    return 1 if failures > 0 else 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
