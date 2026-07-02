"""Build the Neo4j mentions-only evidence graph for a commission corpus.

Idempotent: re-running adds zero nodes or edges (all writes use MERGE).

    build-graph --commission madlanga --dry-run
    build-graph --commission madlanga --limit 10
    build-graph --commission madlanga --no-ner
    build-graph --all

Flags:
  --dry-run    Count docs/chunks from disk; no Neo4j writes, no NER calls.
  --no-ner     Write spine + SPOKE_IN only; skip spaCy MENTIONED_IN pass.
  --force      Re-load even if chunk count already matches.
  --limit N    Cap documents per commission (smoke-test slice).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from commission_ingestion.cli.load_qdrant import read_chunk_files
from commission_ingestion.cli.parse_corpus import DEFAULT_PROCESSED_DIR
from commission_ingestion.download.registry import DEFAULT_REGISTRY_PATH, SourceRegistry
from commission_ingestion.extraction.cache import DEFAULT_CACHE_DIR, ExtractionCache
from commission_ingestion.extraction.schema import PROMPT_VERSION, ChunkExtraction
from commission_ingestion.graph.neo4j_store import (
    ClaimStats,
    GraphStats,
    Neo4jStore,
    build_claim_rows,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.resolution.canonical import DEFAULT_SEED_PATH, load_store

DEFAULT_EXTRACT_MODEL = "claude-haiku-4-5"

logger = logging.getLogger(__name__)

COMMISSIONS = ["zondo", "madlanga"]


def _source_by_sha(registry: SourceRegistry, commission: str) -> dict[str, SourceRecord]:
    return {
        rec.sha256: rec
        for rec in registry.filter(commission_slug=commission)
        if rec.sha256
    }


def _load_claim_inputs(
    chunks: list[ChunkRecord], cache: ExtractionCache, model: str
) -> tuple[list[tuple[ChunkRecord, ChunkExtraction]], int]:
    """Pair each chunk with its cached extraction; count chunks with no cache
    entry (claim extraction not run for them — surfaced, never assumed empty)."""
    inputs: list[tuple[ChunkRecord, ChunkExtraction]] = []
    no_extraction = 0
    for chunk in chunks:
        payload = cache.get(chunk.chunk_id, PROMPT_VERSION, model)
        if payload is None:
            no_extraction += 1
            continue
        inputs.append((chunk, ChunkExtraction.model_validate(payload["extraction"])))
    return inputs, no_extraction


def _fold_claim_stats(stats: GraphStats, cs: ClaimStats) -> None:
    stats.claims_written += cs.claims_written
    stats.claims_speaker_unresolved += cs.claims_speaker_unresolved
    stats.claims_quote_unrecovered += cs.claims_quote_unrecovered
    stats.claim_mentions_edges += cs.mentions_edges
    stats.claims_with_unresolved_subject += cs.claims_with_unresolved_subject


def _process_commission(
    commission: str,
    *,
    store: Neo4jStore | None,
    detector,
    canonical_store,
    sources: dict[str, SourceRecord],
    processed_dir: Path,
    limit: int | None,
    dry_run: bool,
    force: bool,
    with_claims: bool = False,
    extract_model: str = DEFAULT_EXTRACT_MODEL,
    cache: ExtractionCache | None = None,
) -> GraphStats:
    stats = GraphStats()
    documents = read_chunk_files(processed_dir, commission)
    if limit is not None:
        documents = documents[:limit]

    for chunks in documents:
        if not chunks:
            continue
        sha = chunks[0].doc_sha256
        source = sources.get(sha)
        if source is None:
            logger.warning("no registry record for %s — skipping", sha[:16])
            stats.docs_no_source += 1
            continue
        if source.superseded_by:
            logger.debug("skipping superseded doc %s", sha[:16])
            stats.docs_superseded += 1
            continue

        if dry_run:
            stats.docs_loaded += 1
            stats.chunks_written += len(chunks)
            if with_claims and cache is not None:
                inputs, no_ext = _load_claim_inputs(chunks, cache, extract_model)
                stats.chunks_no_extraction += no_ext
                doc_cs = ClaimStats()
                for chunk, extraction in inputs:
                    _, _, cs = build_claim_rows(
                        chunk, extraction, canonical_store,
                        extraction_method=f"{extract_model}:{PROMPT_VERSION}",
                    )
                    doc_cs.add(cs)
                _fold_claim_stats(stats, doc_cs)
            continue

        if not force and store.count_chunks(sha) == len(chunks):
            logger.debug("doc %s already loaded (%d chunks)", sha[:16], len(chunks))
            stats.docs_skipped += 1
            continue

        store.write_spine(chunks, source)
        stats.chunks_written += len(chunks)

        spoken, unresolved_s = store.write_speaker_edges(chunks, canonical_store)
        stats.speaker_edges += spoken
        stats.speaker_unresolved += unresolved_s

        mention_written = 0
        if detector is not None:
            mentions_by_chunk = [
                (chunk.chunk_id, detector.detect(chunk.text))
                for chunk in chunks
            ]
            mention_written, unresolved_m = store.write_mention_edges(
                mentions_by_chunk, canonical_store
            )
            stats.mention_edges += mention_written
            stats.mention_unresolved += unresolved_m

        # Claims load LAST — after spine + SPOKE_IN + MENTIONED_IN — so the
        # :Person and :Chunk targets the claim attaches to already exist.
        claims_written = 0
        if with_claims and cache is not None:
            inputs, no_ext = _load_claim_inputs(chunks, cache, extract_model)
            stats.chunks_no_extraction += no_ext
            cs = store.write_claims(
                inputs, canonical_store,
                extraction_method=f"{extract_model}:{PROMPT_VERSION}",
            )
            _fold_claim_stats(stats, cs)
            claims_written = cs.claims_written

        stats.docs_loaded += 1
        logger.info(
            "day %s: %d chunks → spine + %d SPOKE_IN + %d MENTIONED_IN + %d claims",
            chunks[0].day_no, len(chunks), spoken, mention_written, claims_written,
        )

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the Neo4j mentions-only evidence graph."
    )
    parser.add_argument(
        "--commission",
        choices=["zondo", "madlanga", "both"],
        default="madlanga",
    )
    parser.add_argument(
        "--all", dest="all_commissions", action="store_true",
        help="Process all commissions (equivalent to --commission both).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count without writes or NER — shows what would be loaded.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-load even if chunk count already matches.",
    )
    parser.add_argument(
        "--no-ner", action="store_true",
        help="Write spine + SPOKE_IN only; skip the spaCy MENTIONED_IN pass.",
    )
    parser.add_argument(
        "--with-claims", action="store_true",
        help="Also load the :Claim layer from cached LLM extractions "
             "(after spine + SPOKE_IN + MENTIONED_IN).",
    )
    parser.add_argument(
        "--extract-model", default=DEFAULT_EXTRACT_MODEL,
        help=f"Model whose cached extractions to load (default: {DEFAULT_EXTRACT_MODEL}).",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=DEFAULT_CACHE_DIR,
        help="Extraction cache root for --with-claims.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap documents per commission (for smoke tests).",
    )
    parser.add_argument(
        "--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR,
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-entities", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument(
        "--neo4j-uri", default=None,
        help="Default: $NEO4J_URI or bolt://localhost:7687.",
    )
    parser.add_argument(
        "--spacy-model", default="en_core_web_trf",
        help="spaCy model name (default: en_core_web_trf).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    commissions = (
        COMMISSIONS
        if args.all_commissions or args.commission == "both"
        else [args.commission]
    )

    registry = SourceRegistry(args.registry)
    registry.load()
    canonical_store = load_store(args.seed_entities)

    detector = None
    if not args.dry_run and not args.no_ner:
        from commission_ingestion.graph.mentions import SpacyDetector

        logger.info(
            "Loading spaCy model %r (may download on first run)…", args.spacy_model
        )
        detector = SpacyDetector(model_name=args.spacy_model)

    store: Neo4jStore | None = None
    if not args.dry_run:
        store = Neo4jStore(uri=args.neo4j_uri)

    cache = ExtractionCache(args.cache_dir) if args.with_claims else None

    total = GraphStats()
    try:
        for commission in commissions:
            sources = _source_by_sha(registry, commission)
            stats = _process_commission(
                commission,
                store=store,
                detector=detector,
                canonical_store=canonical_store,
                sources=sources,
                processed_dir=args.processed_dir,
                limit=args.limit,
                dry_run=args.dry_run,
                force=args.force,
                with_claims=args.with_claims,
                extract_model=args.extract_model,
                cache=cache,
            )
            total.docs_loaded        += stats.docs_loaded
            total.docs_skipped       += stats.docs_skipped
            total.docs_superseded    += stats.docs_superseded
            total.docs_no_source     += stats.docs_no_source
            total.chunks_written     += stats.chunks_written
            total.speaker_edges      += stats.speaker_edges
            total.speaker_unresolved += stats.speaker_unresolved
            total.mention_edges      += stats.mention_edges
            total.mention_unresolved += stats.mention_unresolved
            total.chunks_no_extraction          += stats.chunks_no_extraction
            total.claims_written                += stats.claims_written
            total.claims_speaker_unresolved     += stats.claims_speaker_unresolved
            total.claims_quote_unrecovered      += stats.claims_quote_unrecovered
            total.claim_mentions_edges          += stats.claim_mentions_edges
            total.claims_with_unresolved_subject += stats.claims_with_unresolved_subject
    finally:
        if store is not None:
            store.close()

    label = "[DRY RUN] " if args.dry_run else ""
    print(f"{label}Neo4j graph build summary")
    print(f"  Commissions:           {', '.join(commissions)}")
    print(f"  Documents loaded:      {total.docs_loaded}")
    print(f"  Documents skipped:     {total.docs_skipped}  (already current)")
    print(f"  Documents superseded:  {total.docs_superseded}")
    print(f"  Documents no source:   {total.docs_no_source}")
    print(f"  Chunks written:        {total.chunks_written}")
    print(f"  SPOKE_IN edges:        {total.speaker_edges}"
          f"  (unresolved: {total.speaker_unresolved})")
    print(f"  MENTIONED_IN edges:    {total.mention_edges}"
          f"  (unresolved: {total.mention_unresolved})")
    if args.with_claims:
        print(f"  Claims written:        {total.claims_written}"
              f"  (model: {args.extract_model})")
        print(f"  Claim MENTIONS edges:  {total.claim_mentions_edges}")
        print(f"  Claims w/ raw subject: {total.claims_with_unresolved_subject}")
        print(f"  Claims w/ raw speaker: {total.claims_speaker_unresolved}  "
              f"(loaded, STATED_BY uncanonicalised — ADR 0007)")
        print(f"  Claims skipped:        "
              f"quote_unrecovered={total.claims_quote_unrecovered}")
        print(f"  Chunks w/o extraction: {total.chunks_no_extraction}")

    if total.docs_no_source > 0:
        return 1
    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
