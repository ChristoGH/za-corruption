"""Compute descriptive corpus statistics and (optionally) Post #1 charts.

Reuses the verified parsing pipeline to derive speaker turns per hearing day,
rolls them into a headline stats JSON (so the post copy is generated from data,
never typed from memory), and renders charts when the ``stats`` extra is present.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from commission_ingestion.analysis.stats import (
    aggregate_day,
    infer_counsel_labels,
    summarise,
)
from commission_ingestion.download.registry import (
    DEFAULT_REGISTRY_PATH,
    SourceRegistry,
)
from commission_ingestion.parsing import detect_turns, extract_pages, is_scanned, reflow_pages

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_DIR = Path("data/processed")


def _load_role_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    import yaml  # lazy: only needed when a role map is supplied

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def _chunk_total(processed_dir: Path, commission: str) -> int | None:
    manifest = processed_dir / commission / "_parse_manifest.jsonl"
    if not manifest.exists():
        return None
    total = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += json.loads(line).get("n_chunks") or 0
    return total


def compute(
    registry: SourceRegistry,
    commission: str,
    *,
    processed_dir: Path,
    role_map: dict[str, str],
) -> dict:
    transcripts = [
        r
        for r in registry.filter(commission_slug=commission, source_type="transcript")
        if r.downloaded and r.local_path
    ]
    transcripts.sort(key=lambda r: (r.day_no is None, r.day_no or 0))

    # Pass 1: parse every day's turns (so we can infer counsel corpus-wide before
    # attributing roles — counsel recur across days, witnesses don't).
    parsed: list[tuple] = []
    for record in transcripts:
        if not Path(record.local_path).exists():
            continue
        pages = extract_pages(record.local_path)
        if is_scanned(pages):
            logger.warning("skipping scanned doc: %s", record.url)
            continue
        turns = detect_turns(reflow_pages(pages))
        parsed.append((record.day_no, record.date, len(pages), turns))

    counsel_labels = infer_counsel_labels([turns for *_, turns in parsed])

    # Pass 2: aggregate with counsel context (and any human role-map override).
    days = [
        aggregate_day(
            day_no=day_no,
            date=date,
            n_pages=n_pages,
            turns=turns,
            role_map=role_map,
            counsel_labels=counsel_labels,
        )
        for day_no, date, n_pages, turns in parsed
    ]
    return summarise(
        days,
        n_chunks=_chunk_total(processed_dir, commission),
        role_map_applied=bool(role_map),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute corpus statistics (Post #1).")
    parser.add_argument("--commission", choices=["zondo", "madlanga"], default="madlanga")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument(
        "--role-map", type=Path, default=None, help="Optional speaker->role override YAML"
    )
    parser.add_argument("--charts", action="store_true", help="Also render PNG charts")
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

    summary = compute(
        registry,
        args.commission,
        processed_dir=args.processed_dir,
        role_map=_load_role_map(args.role_map),
    )

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

        written = render_all(summary, stats_dir / args.commission)
        print(f"  Charts:           {len(written)} -> {stats_dir / args.commission}")

    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
