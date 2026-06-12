"""Embed parsed chunks and upsert them into the shared Qdrant collection.

Idempotent: point ids are deterministic (uuid5 of the chunk_id), and a document
whose chunks are already all present is skipped without re-embedding. Reads the
chunk JSONL written by parse-corpus plus the source registry, which supplies
the payload fields chunks don't carry (source_type, document_type,
authoritative, filename).

Registry records marked ``superseded_by`` (duplicate publications of the same
sitting) are never loaded, and any points they previously contributed are
purged — so a cold reload cannot resurrect them.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from commission_ingestion.cli.parse_corpus import DEFAULT_PROCESSED_DIR
from commission_ingestion.download.registry import (
    DEFAULT_REGISTRY_PATH,
    SourceRegistry,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.vector.embedder import Embedder
from commission_ingestion.vector.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 64


def read_chunk_files(processed_dir: Path, commission: str) -> list[list[ChunkRecord]]:
    """One list of ChunkRecords per document JSONL (manifest excluded)."""
    chunk_dir = processed_dir / commission
    documents: list[list[ChunkRecord]] = []
    for path in sorted(chunk_dir.glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        with path.open(encoding="utf-8") as handle:
            chunks = [
                ChunkRecord.model_validate_json(line)
                for line in handle
                if line.strip()
            ]
        if chunks:
            documents.append(chunks)
    return documents


def _source_by_sha(registry: SourceRegistry, commission: str) -> dict[str, SourceRecord]:
    return {
        record.sha256: record
        for record in registry.filter(commission_slug=commission)
        if record.sha256
    }


def load_corpus(
    store: QdrantStore,
    embedder: Embedder | None,
    documents: list[list[ChunkRecord]],
    sources: dict[str, SourceRecord],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
    make_embedder=None,
) -> dict[str, int]:
    """Embed + upsert per document. Returns counters for the run summary.

    The embedder is created lazily (via make_embedder) only when at least one
    document actually needs embedding, so a fully loaded corpus re-run is a
    fast no-op that never touches the model.
    """
    store.ensure_collection()
    stats = {
        "docs_loaded": 0,
        "docs_skipped": 0,
        "docs_no_source": 0,
        "docs_superseded": 0,
        "points_purged": 0,
        "chunks_upserted": 0,
    }

    for chunks in documents:
        sha256 = chunks[0].doc_sha256
        source = sources.get(sha256)
        if source is None:
            logger.warning("No registry record for doc %s — skipping", sha256[:16])
            stats["docs_no_source"] += 1
            continue

        if source.superseded_by:
            existing = store.count(sha256=sha256)
            if existing:
                store.delete_by_sha(sha256)
                stats["points_purged"] += existing
                logger.info(
                    "purged %d points of superseded doc %s (superseded_by %s)",
                    existing, sha256[:16], source.superseded_by[:16],
                )
            stats["docs_superseded"] += 1
            continue

        if not force and store.count(sha256=sha256) == len(chunks):
            stats["docs_skipped"] += 1
            continue

        if embedder is None:
            if make_embedder is None:
                raise ValueError("no embedder available but documents need embedding")
            embedder = make_embedder()

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embedder.embed_passages([chunk.text for chunk in batch])
            store.upsert_chunks(batch, vectors, source)
            stats["chunks_upserted"] += len(batch)
        stats["docs_loaded"] += 1
        logger.info(
            "day %s: %d chunks embedded -> qdrant", chunks[0].day_no, len(chunks)
        )

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Embed parsed chunks and load them into Qdrant."
    )
    parser.add_argument(
        "--commission", choices=["zondo", "madlanga"], default="madlanga"
    )
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--qdrant-url", default=None, help="Default: $QDRANT_URL or localhost:6333")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="Cap documents processed")
    parser.add_argument(
        "--force", action="store_true", help="Re-embed and upsert even if already loaded"
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
    sources = _source_by_sha(registry, args.commission)

    documents = read_chunk_files(args.processed_dir, args.commission)
    if args.limit is not None:
        documents = documents[: args.limit]
    superseded_shas = {sha for sha, rec in sources.items() if rec.superseded_by}
    active_chunks = sum(
        len(chunks)
        for chunks in documents
        if chunks[0].doc_sha256 not in superseded_shas
    )

    store = QdrantStore(url=args.qdrant_url)

    def make_embedder():
        from commission_ingestion.vector.embedder import BgeSmallEmbedder

        logger.info("Loading embedding model (first call may download it)…")
        return BgeSmallEmbedder()

    stats = load_corpus(
        store,
        None,
        documents,
        sources,
        batch_size=args.batch_size,
        force=args.force,
        make_embedder=make_embedder,
    )

    collection_count = store.count(commission=args.commission)
    print("Qdrant load summary")
    print(f"  Commission:        {args.commission}")
    print(f"  Documents:         {len(documents)}")
    print(f"    loaded:          {stats['docs_loaded']}")
    print(f"    skipped (done):  {stats['docs_skipped']}")
    print(f"    superseded:      {stats['docs_superseded']} "
          f"({stats['points_purged']} stale points purged)")
    print(f"    no source:       {stats['docs_no_source']}")
    print(f"  Chunks upserted:   {stats['chunks_upserted']}")
    print(f"  Active chunks:     {active_chunks} (superseded docs excluded)")
    print(f"  Points in Qdrant:  {collection_count} (commission filter)")

    if stats["docs_no_source"] > 0 or collection_count != active_chunks:
        print("  PARITY FAILED — point count must equal the active chunk total.")
        return 1
    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
