"""Neo4j spine + mention writers for the commission evidence graph.

All writes use MERGE on the unique keys from docs/neo4j-model.md — the
graph is idempotent: re-running the load adds zero nodes or edges.

Two provenance paths (settled, docs/project-state.md §6.2):
  authoritative PDFs:   Commission → HearingDay → Document → Page → Chunk
  bootstrap plaintext:  Commission → HearingDay → Document → Chunk

The direct (:Document)-[:HAS_CHUNK] shortcut is BANNED on paged docs and
is only used for the bootstrap (page-less) path. APPEARS_IN is banned
everywhere — use MENTIONED_IN (entities) or SPOKE_IN (speakers).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from commission_ingestion.graph.mentions import DetectedMention
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.resolution.canonical import CanonicalStore

logger = logging.getLogger(__name__)

DEFAULT_NEO4J_URI      = "bolt://localhost:7687"
DEFAULT_NEO4J_USER     = "neo4j"
DEFAULT_NEO4J_PASSWORD = "changeme"

BATCH_SIZE = 500  # rows per UNWIND call


# ─── key helpers ──────────────────────────────────────────────────────────────

def hearing_key(slug: str, day_no: int | None, date: str | None) -> str:
    """Stable unique key for a :HearingDay node per the ontology spec."""
    if day_no is not None and date:
        return f"{slug}-day-{day_no}-{date}"
    return f"{slug}-unknown"


def page_key(doc_sha256: str, page_no: int) -> str:
    """Stable unique key for a :Page node."""
    return f"{doc_sha256}:{page_no}"


# ─── Cypher constants ─────────────────────────────────────────────────────────
#
# Naming rules enforced here:
#   - MENTIONED_IN for entity → Chunk
#   - SPOKE_IN for speaker Person → Chunk
#   - APPEARS_IN is banned — must never appear in any query below
#   - HAS_CHUNK on a paged Document is banned — only valid on bootstrap

_SPINE_PAGED = """\
UNWIND $rows AS row
MERGE (com:Commission {slug: row.commission_slug})
  ON CREATE SET com.name = row.commission_name
MERGE (h:HearingDay {key: row.hearing_key})
  ON CREATE SET h.day_no = row.day_no, h.date = row.date
MERGE (d:Document {sha256: row.doc_sha256})
  ON CREATE SET d.source_url = row.source_url,
               d.filename = row.filename,
               d.authoritative = true,
               d.commission_slug = row.commission_slug,
               d.document_type = row.document_type
MERGE (pg:Page {key: row.page_key})
  ON CREATE SET pg.page_no = row.page_start
MERGE (ck:Chunk {chunk_id: row.chunk_id})
  ON CREATE SET ck.text = row.text,
               ck.page_start = row.page_start,
               ck.page_end = row.page_end,
               ck.speakers = row.speakers,
               ck.chunk_index = row.chunk_index,
               ck.doc_sha256 = row.doc_sha256,
               ck.commission_slug = row.commission_slug,
               ck.day_no = row.day_no
MERGE (com)-[:HAS_HEARING]->(h)
MERGE (h)-[:HAS_DOCUMENT]->(d)
MERGE (d)-[:HAS_PAGE]->(pg)
MERGE (pg)-[:HAS_CHUNK]->(ck)
"""

# Bootstrap: no :Page nodes — chunks attach directly under :Document.
# This is the ONLY place HAS_CHUNK is valid on a Document.
_SPINE_BOOTSTRAP = """\
UNWIND $rows AS row
MERGE (com:Commission {slug: row.commission_slug})
  ON CREATE SET com.name = row.commission_name
MERGE (h:HearingDay {key: row.hearing_key})
  ON CREATE SET h.day_no = row.day_no, h.date = row.date
MERGE (d:Document {sha256: row.doc_sha256})
  ON CREATE SET d.source_url = row.source_url,
               d.filename = row.filename,
               d.authoritative = false,
               d.commission_slug = row.commission_slug,
               d.document_type = row.document_type
MERGE (ck:Chunk {chunk_id: row.chunk_id})
  ON CREATE SET ck.text = row.text,
               ck.page_start = row.page_start,
               ck.page_end = row.page_end,
               ck.speakers = row.speakers,
               ck.chunk_index = row.chunk_index,
               ck.doc_sha256 = row.doc_sha256,
               ck.commission_slug = row.commission_slug,
               ck.day_no = row.day_no
MERGE (com)-[:HAS_HEARING]->(h)
MERGE (h)-[:HAS_DOCUMENT]->(d)
MERGE (d)-[:HAS_CHUNK]->(ck)
"""

_SPOKE_IN = """\
UNWIND $rows AS row
MERGE (ck:Chunk {chunk_id: row.chunk_id})
MERGE (p:Person {name: row.canonical_name})
MERGE (p)-[r:SPOKE_IN]->(ck)
  ON CREATE SET r.speaker_label = row.speaker_label
"""

_MENTIONED_IN_PERSON = """\
UNWIND $rows AS row
MERGE (ck:Chunk {chunk_id: row.chunk_id})
MERGE (e:Person {name: row.canonical_name})
MERGE (e)-[:MENTIONED_IN]->(ck)
"""

_MENTIONED_IN_ORG = """\
UNWIND $rows AS row
MERGE (ck:Chunk {chunk_id: row.chunk_id})
MERGE (e:Organisation {name: row.canonical_name})
MERGE (e)-[:MENTIONED_IN]->(ck)
"""

_MENTIONED_IN_PLACE = """\
UNWIND $rows AS row
MERGE (ck:Chunk {chunk_id: row.chunk_id})
MERGE (e:Place {name: row.canonical_name})
MERGE (e)-[:MENTIONED_IN]->(ck)
"""

_MENTIONED_IN_BY_TYPE: dict[str, str] = {
    "person": _MENTIONED_IN_PERSON,
    "org":    _MENTIONED_IN_ORG,
    "place":  _MENTIONED_IN_PLACE,
}

# Idempotency check — chunk nodes store doc_sha256 for a fast count.
_COUNT_CHUNKS = "MATCH (c:Chunk {doc_sha256: $sha256}) RETURN count(c) AS n"


# ─── stats ────────────────────────────────────────────────────────────────────

@dataclass
class GraphStats:
    docs_loaded: int = 0
    docs_skipped: int = 0
    docs_superseded: int = 0
    docs_no_source: int = 0
    chunks_written: int = 0
    speaker_edges: int = 0
    speaker_unresolved: int = 0
    mention_edges: int = 0
    mention_unresolved: int = 0


# ─── store ────────────────────────────────────────────────────────────────────

class Neo4jStore:
    """Thin driver wrapper.  All public methods are idempotent (MERGE only)."""

    def __init__(
        self,
        driver: Any = None,
        *,
        uri: str | None = None,
        auth: tuple[str, str] | None = None,
    ) -> None:
        if driver is not None:
            self._driver = driver
            return
        try:
            import neo4j as _neo4j
        except ImportError as exc:
            raise ImportError(
                "neo4j driver required; it is a core dependency — run: uv sync --all-packages"
            ) from exc
        _uri = uri or os.environ.get("NEO4J_URI", DEFAULT_NEO4J_URI)
        _user, _password = auth or (
            os.environ.get("NEO4J_USER", DEFAULT_NEO4J_USER),
            os.environ.get("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
        )
        self._driver = _neo4j.GraphDatabase.driver(_uri, auth=(_user, _password))

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── idempotency check ─────────────────────────────────────────────────────

    def count_chunks(self, doc_sha256: str) -> int:
        """Count :Chunk nodes already stored for a document SHA256."""
        with self._driver.session() as session:
            record = session.execute_read(
                lambda tx: tx.run(_COUNT_CHUNKS, sha256=doc_sha256).single()
            )
            return record["n"] if record else 0

    # ── spine ─────────────────────────────────────────────────────────────────

    def write_spine(
        self,
        chunks: list[ChunkRecord],
        source: SourceRecord,
    ) -> int:
        """Write the Document→(Page→)Chunk spine for one document.

        Picks the paged path when source.authoritative is True, bootstrap
        otherwise.  Returns the number of chunks written.
        """
        query = _SPINE_PAGED if source.authoritative else _SPINE_BOOTSTRAP
        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            row: dict[str, Any] = {
                "commission_slug": chunk.commission_slug,
                "commission_name": chunk.commission_name,
                "doc_sha256":      chunk.doc_sha256,
                "source_url":      chunk.source_url,
                "filename":        source.filename or "",
                "document_type":   source.document_type or "Transcript",
                "hearing_key":     hearing_key(
                    chunk.commission_slug, chunk.day_no, chunk.date
                ),
                "day_no":          chunk.day_no,
                "date":            chunk.date,
                "chunk_id":        chunk.chunk_id,
                "chunk_index":     chunk.chunk_index,
                "text":            chunk.text,
                "page_start":      chunk.page_start,
                "page_end":        chunk.page_end,
                "speakers":        chunk.speakers,
            }
            if source.authoritative:
                row["page_key"] = page_key(chunk.doc_sha256, chunk.page_start)
            rows.append(row)

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            with self._driver.session() as session:
                session.execute_write(lambda tx, b=batch: tx.run(query, rows=b))

        return len(chunks)

    # ── SPOKE_IN ──────────────────────────────────────────────────────────────

    def write_speaker_edges(
        self,
        chunks: list[ChunkRecord],
        canonical_store: CanonicalStore,
    ) -> tuple[int, int]:
        """Write (:Person)-[:SPOKE_IN]->(:Chunk) for every resolved speaker label.

        Returns (edges_written, labels_unresolved).
        """
        rows: list[dict[str, str]] = []
        unresolved = 0
        for chunk in chunks:
            for label in chunk.speakers:
                entity = canonical_store.lookup(label, entity_type="person")
                if entity is None:
                    unresolved += 1
                    logger.debug("unresolved speaker: %r", label)
                    continue
                rows.append({
                    "chunk_id":       chunk.chunk_id,
                    "canonical_name": entity.name,
                    "speaker_label":  label,
                })

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            with self._driver.session() as session:
                session.execute_write(lambda tx, b=batch: tx.run(_SPOKE_IN, rows=b))

        return len(rows), unresolved

    # ── MENTIONED_IN ──────────────────────────────────────────────────────────

    def write_mention_edges(
        self,
        mentions_by_chunk: list[tuple[str, list[DetectedMention]]],
        canonical_store: CanonicalStore,
    ) -> tuple[int, int]:
        """Write (:Entity)-[:MENTIONED_IN]->(:Chunk) for resolved NER detections.

        Args:
            mentions_by_chunk: list of (chunk_id, detections) — one entry per chunk.
            canonical_store:   resolver; unresolved mentions are skipped (not invented).

        Returns (edges_written, mentions_unresolved).
        """
        by_type: dict[str, list[dict[str, str]]] = {
            "person": [], "org": [], "place": [],
        }
        unresolved = 0

        for chunk_id, detected in mentions_by_chunk:
            # Dedup within the chunk so the same canonical entity is mentioned once.
            seen_in_chunk: set[str] = set()
            for mention in detected:
                etype = mention.entity_type
                entity = canonical_store.lookup(mention.surface, entity_type=etype)
                if entity is None:
                    unresolved += 1
                    logger.debug("unresolved mention: %r (%s)", mention.surface, etype)
                    continue
                if entity.entity_id in seen_in_chunk:
                    continue
                seen_in_chunk.add(entity.entity_id)
                target = by_type.get(etype)
                if target is not None:
                    target.append({
                        "chunk_id":       chunk_id,
                        "canonical_name": entity.name,
                    })

        written = 0
        for etype, rows in by_type.items():
            if not rows:
                continue
            query = _MENTIONED_IN_BY_TYPE[etype]
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start : start + BATCH_SIZE]
                with self._driver.session() as session:
                    session.execute_write(
                        lambda tx, q=query, b=batch: tx.run(q, rows=b)
                    )
            written += len(rows)

        return written, unresolved
