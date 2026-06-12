"""Compute descriptive corpus statistics and (optionally) Post #1 charts.

Reuses the verified parsing pipeline to derive speaker turns per hearing day,
rolls them into a headline stats JSON (so the post copy is generated from data,
never typed from memory), and renders charts when the ``stats`` extra is present.

A blocking integrity pass runs first (duplicate-content detection across
same-day/same-date/adjacent-day documents, hard reconciliation of totals).
Registry records marked ``superseded_by`` are excluded from every number.
``day_no`` and ``date`` come from the registry only — in-PDF footers have been
observed to be wrong (the real day-80 record carries a "DAY 90" footer).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from commission_ingestion.analysis.integrity import (
    DocInfo,
    check_corpus,
    reconcile_summary,
    render_report,
)
from commission_ingestion.analysis.stats import (
    aggregate_day,
    infer_counsel_labels,
    summarise,
)
from commission_ingestion.download.registry import (
    DEFAULT_REGISTRY_PATH,
    SourceRegistry,
)
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.parsing import detect_turns, extract_pages, is_scanned, reflow_pages
from commission_ingestion.parsing.turns import Turn

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_DIR = Path("data/processed")


@dataclass
class ParsedDoc:
    """One transcript parsed once, shared by the integrity pass and the stats."""

    record: SourceRecord
    n_pages: int
    page_texts: list[str]
    turns: list[Turn]


def _load_role_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    import yaml  # lazy: only needed when a role map is supplied

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def _chunk_total(
    processed_dir: Path, commission: str, excluded_shas: frozenset[str]
) -> int | None:
    manifest = processed_dir / commission / "_parse_manifest.jsonl"
    if not manifest.exists():
        return None
    total = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("doc_sha256") in excluded_shas:
            continue
        total += entry.get("n_chunks") or 0
    return total


def split_records(
    registry: SourceRegistry, commission: str
) -> tuple[list[SourceRecord], list[SourceRecord]]:
    """Downloaded transcripts split into (active, superseded), day-ordered."""
    transcripts = [
        r
        for r in registry.filter(commission_slug=commission, source_type="transcript")
        if r.downloaded and r.local_path
    ]
    transcripts.sort(key=lambda r: (r.day_no is None, r.day_no or 0))
    active = [r for r in transcripts if not r.superseded_by]
    superseded = [r for r in transcripts if r.superseded_by]
    return active, superseded


def parse_documents(records: list[SourceRecord]) -> list[ParsedDoc]:
    parsed: list[ParsedDoc] = []
    for record in records:
        if not Path(record.local_path).exists():
            logger.warning("missing local file, skipping: %s", record.local_path)
            continue
        pages = extract_pages(record.local_path)
        if is_scanned(pages):
            logger.warning("skipping scanned doc: %s", record.url)
            continue
        parsed.append(
            ParsedDoc(
                record=record,
                n_pages=len(pages),
                page_texts=[p.text for p in pages],
                turns=detect_turns(reflow_pages(pages)),
            )
        )
    return parsed


def compute(
    parsed: list[ParsedDoc],
    *,
    n_chunks: int | None,
    role_map: dict[str, str],
) -> dict:
    # Counsel are inferred corpus-wide before attributing roles — counsel recur
    # across days, witnesses don't.
    counsel_labels = infer_counsel_labels([doc.turns for doc in parsed])
    days = [
        aggregate_day(
            day_no=doc.record.day_no,
            date=doc.record.date,
            n_pages=doc.n_pages,
            turns=doc.turns,
            role_map=role_map,
            counsel_labels=counsel_labels,
        )
        for doc in parsed
    ]
    return summarise(days, n_chunks=n_chunks, role_map_applied=bool(role_map))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute corpus statistics (Post #1).")
    parser.add_argument("--commission", choices=["zondo", "madlanga"], default="madlanga")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument(
        "--role-map", type=Path, default=None, help="Optional speaker->role override YAML"
    )
    parser.add_argument("--charts", action="store_true", help="Also render PNG charts")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Chart/alt-text output dir (default: <processed-dir>/stats/<commission>)",
    )
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
    active_records, superseded_records = split_records(registry, args.commission)

    parsed = parse_documents(active_records)
    docs = [
        DocInfo(record=p.record, n_pages=p.n_pages, page_texts=p.page_texts)
        for p in parsed
    ]

    report = check_corpus(
        docs, superseded_records, expected_active_records=len(active_records)
    )

    excluded_shas = frozenset(r.sha256 for r in superseded_records if r.sha256)
    summary = compute(
        parsed,
        n_chunks=_chunk_total(args.processed_dir, args.commission, excluded_shas),
        role_map=_load_role_map(args.role_map),
    )
    report.errors.extend(reconcile_summary(docs, summary))

    print(render_report(report))
    if not report.ok:
        print("\nIntegrity pass FAILED — no stats or charts written. "
              "Resolve via human-reviewed registry edits (superseded_by), then re-run.")
        return 2

    stats_dir = args.processed_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    json_path = stats_dir / f"{args.commission}_stats.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    t = summary["totals"]
    share = summary["role_word_share_pct"]
    print("Corpus statistics —", args.commission)
    print(f"  Hearing days:     {t['hearing_days']} (distinct day numbers)")
    print(f"  Transcript docs:  {t['transcript_documents']}")
    print(f"  PDF pages:        {t['pages']:,}")
    print(f"  Speaker turns:    {t['turns']:,}")
    print(f"  Words:            {t['words']:,}")
    print(f"  Chunks:           {t['chunks']}")
    print(f"  Distinct labels:  {t['distinct_speaker_labels']}")
    print(f"  Word share:       counsel {share['counsel']}% / "
          f"witnesses {share['witness']}% / bench {share['bench']}%")
    print(f"  Stats JSON:       {json_path}")

    if args.charts:
        from commission_ingestion.analysis.charts import render_all

        out_dir = args.out or (stats_dir / args.commission)
        written = render_all(summary, out_dir)
        print(f"  Charts:           {len(written)} -> {out_dir}")

    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
