"""Neo4j spine + mention writers for the commission evidence graph.

All writes use MERGE on the unique keys from docs/neo4j-model.md — the
graph is idempotent: re-running the load adds zero nodes or edges.

Two provenance paths (settled, docs/project-state.md §6.2):
  authoritative PDFs:   Commission → HearingDay → Document → Page → Chunk
  bootstrap plaintext:  Commission → HearingDay → Document → Chunk

The direct (:Document)-[:HAS_CHUNK] shortcut is BANNED on paged docs and
is only used for the bootstrap (page-less) path. APPEARS_IN is banned
everywhere — use MENTIONED_IN (entities) or SPOKE_IN (speakers).

Claim layer (M4 — see docs/decisions/0005-claim-writer-schema.md):
  - Decision 1 (MERGE key): claim_id is a deterministic sha256 over
    (chunk_id, speaker_entity_id, normalized_predicate, quote_span_offsets) —
    never a random UUID, so re-runs are idempotent. status="alleged" is a
    Cypher literal written ON CREATE only (never from model output, never
    clobbering a later human-review status).
  - Decision 2 (raw-subject fallthrough): resolved subjects/objects get
    (:Claim)-[:MENTIONS {role}]->(:Person|:Organisation|:Place); unresolved
    surfaces are recorded ON the claim (unresolved_subjects/_objects +
    has_unresolved_subject), never as a separate node and never silently
    dropped — countable and surfaceable for human review.
  Banned by construction here too: no fact-edges, no claim wired to a subject
  bypassing the :Claim node (MENTIONS originates at the claim).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from commission_ingestion.extraction.schema import ChunkExtraction, find_quote
from commission_ingestion.graph.mentions import DetectedMention
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.resolution.canonical import (
    _TYPE_GROUP,
    CanonicalStore,
)

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


_PRED_WS_RE = re.compile(r"\s+")


def claim_key(
    chunk_id: str, speaker_entity_id: str, predicate: str, start: int, end: int
) -> str:
    """Deterministic :Claim MERGE key (docs/decisions/0005).

    Content-addressed over (chunk_id, resolved speaker id, normalized predicate,
    quote span offsets) so re-running the load is idempotent. Predicate is
    lowercased + whitespace-collapsed; the quote *span* (not text) disambiguates
    two distinct claims by the same speaker with identical predicate text.
    """
    norm_pred = _PRED_WS_RE.sub(" ", predicate.strip().lower())
    raw = f"{chunk_id}|{speaker_entity_id}|{norm_pred}|{start}:{end}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


# ─── claim layer (M4) ─────────────────────────────────────────────────────────
#
# status='alleged' is a literal set ON CREATE — never sourced from a row, never
# overwriting a later human-review status. The chunk is MATCHed (must pre-exist
# from the spine), so a :Claim cannot be created detached from its provenance.
_CLAIM_CORE = """\
UNWIND $rows AS row
MATCH (ck:Chunk {chunk_id: row.chunk_id})
MERGE (cl:Claim {claim_id: row.claim_id})
  ON CREATE SET cl.text = row.text,
               cl.status = 'alleged',
               cl.attribution = row.attribution,
               cl.extraction_method = row.extraction_method,
               cl.quote = row.quote,
               cl.quote_start = row.quote_start,
               cl.quote_end = row.quote_end,
               cl.certainty = row.certainty,
               cl.has_unresolved_subject = row.has_unresolved_subject,
               cl.unresolved_subjects = row.unresolved_subjects,
               cl.unresolved_objects = row.unresolved_objects
MERGE (sp:Person {name: row.speaker_name})
MERGE (cl)-[:STATED_BY]->(sp)
MERGE (cl)-[:SUPPORTED_BY]->(ck)
"""

# Subject/object edges: one MENTIONS per (claim, canonical entity), role on the
# edge. The claim is MATCHed (created by _CLAIM_CORE first), the entity MERGEd.
_CLAIM_MENTIONS_PERSON = """\
UNWIND $rows AS row
MATCH (cl:Claim {claim_id: row.claim_id})
MERGE (e:Person {name: row.entity_name})
MERGE (cl)-[m:MENTIONS]->(e)
  ON CREATE SET m.role = row.role
"""

_CLAIM_MENTIONS_ORG = """\
UNWIND $rows AS row
MATCH (cl:Claim {claim_id: row.claim_id})
MERGE (e:Organisation {name: row.entity_name})
MERGE (cl)-[m:MENTIONS]->(e)
  ON CREATE SET m.role = row.role
"""

_CLAIM_MENTIONS_PLACE = """\
UNWIND $rows AS row
MATCH (cl:Claim {claim_id: row.claim_id})
MERGE (e:Place {name: row.entity_name})
MERGE (cl)-[m:MENTIONS]->(e)
  ON CREATE SET m.role = row.role
"""

_CLAIM_MENTIONS_BY_TYPE: dict[str, str] = {
    "person": _CLAIM_MENTIONS_PERSON,
    "org":    _CLAIM_MENTIONS_ORG,
    "place":  _CLAIM_MENTIONS_PLACE,
}


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
    # claim layer (M4) — headline totals; full detail in ClaimStats
    chunks_no_extraction: int = 0
    claims_written: int = 0
    claims_speaker_unresolved: int = 0
    claims_quote_unrecovered: int = 0
    claim_mentions_edges: int = 0
    claims_with_unresolved_subject: int = 0


@dataclass
class ClaimStats:
    """Per-type counts from write_claims — the canary reads these to assert load
    invariants and (via two runs) idempotency. Counts reflect rows the writer
    *attempted*; live DB node/edge counts are asserted separately in the canary."""
    claims_written: int = 0
    claims_speaker_unresolved: int = 0   # skipped: no STATED_BY :Person possible
    claims_quote_unrecovered: int = 0    # skipped: find_quote None == fabricated quote
    stated_by_edges: int = 0
    supported_by_edges: int = 0
    mentions_edges: int = 0               # canonical subject+object MENTIONS edges
    claims_with_unresolved_subject: int = 0
    unresolved_subject_refs: int = 0
    unresolved_object_refs: int = 0

    def add(self, other: "ClaimStats") -> None:
        self.claims_written += other.claims_written
        self.claims_speaker_unresolved += other.claims_speaker_unresolved
        self.claims_quote_unrecovered += other.claims_quote_unrecovered
        self.stated_by_edges += other.stated_by_edges
        self.supported_by_edges += other.supported_by_edges
        self.mentions_edges += other.mentions_edges
        self.claims_with_unresolved_subject += other.claims_with_unresolved_subject
        self.unresolved_subject_refs += other.unresolved_subject_refs
        self.unresolved_object_refs += other.unresolved_object_refs


# ─── claim row building (pure — no driver, fully unit-testable) ───────────────

_MENTION_GROUPS = ("person", "org", "place")


def build_claim_rows(
    chunk: ChunkRecord,
    extraction: ChunkExtraction,
    canonical_store: CanonicalStore,
    *,
    extraction_method: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, str]]], ClaimStats]:
    """Resolve one chunk's claims into Cypher rows (docs/decisions/0005).

    Pure function: resolution, quote recovery, claim_id and the raw-subject
    fallthrough policy all live here so they can be tested without a driver.
    Returns (core_rows, mention_rows_by_type, stats).

    A claim is dropped (counted, not silently lost) when its speaker does not
    resolve (no STATED_BY :Person is possible) or its quote is not recoverable
    (find_quote None == a fabricated quote that must never be written).
    """
    core_rows: list[dict[str, Any]] = []
    mention_rows: dict[str, list[dict[str, str]]] = {g: [] for g in _MENTION_GROUPS}
    stats = ClaimStats()
    ref_map = {e.ref: e for e in extraction.entities}

    for claim in extraction.claims:
        speaker = canonical_store.lookup(claim.speaker, entity_type="person")
        if speaker is None:
            stats.claims_speaker_unresolved += 1
            logger.debug("claim speaker unresolved: %r", claim.speaker)
            continue
        span = find_quote(chunk.text, claim.quote)
        if span is None:
            stats.claims_quote_unrecovered += 1
            logger.warning(
                "claim quote not recoverable in %s — dropping (fabricated quote?)",
                chunk.chunk_id[:16],
            )
            continue
        start, end = span
        cid = claim_key(chunk.chunk_id, speaker.entity_id, claim.predicate, start, end)

        unresolved_subjects: list[str] = []
        unresolved_objects: list[str] = []
        seen: set[str] = set()  # dedup canonical entity per claim

        def _resolve(refs: list[str], role: str, sink: list[str]) -> None:
            for ref in refs:
                ent = ref_map.get(ref)
                if ent is None:
                    sink.append(ref)  # dangling chunk-local handle
                    continue
                group = _TYPE_GROUP.get(ent.type)
                if group not in _MENTION_GROUPS:  # e.g. role — not a MENTIONS target
                    sink.append(ent.name)
                    continue
                hit = canonical_store.lookup(ent.name, entity_type=ent.type)
                if hit is None:
                    sink.append(ent.name)  # raw fallthrough — kept on the claim
                    continue
                if hit.entity_id in seen:
                    continue
                seen.add(hit.entity_id)
                mention_rows[group].append(
                    {"claim_id": cid, "entity_name": hit.name, "role": role}
                )
                stats.mentions_edges += 1

        _resolve(claim.subject_refs, "subject", unresolved_subjects)
        _resolve(claim.object_refs, "object", unresolved_objects)

        has_unresolved_subject = bool(unresolved_subjects)
        if has_unresolved_subject:
            stats.claims_with_unresolved_subject += 1
            stats.unresolved_subject_refs += len(unresolved_subjects)
        stats.unresolved_object_refs += len(unresolved_objects)

        core_rows.append({
            "chunk_id":               chunk.chunk_id,
            "claim_id":               cid,
            "text":                   claim.predicate,
            "attribution":            claim.speaker,
            "extraction_method":      extraction_method,
            "speaker_name":           speaker.name,
            "quote":                  claim.quote,
            "quote_start":            start,
            "quote_end":              end,
            "certainty":              claim.certainty,
            "has_unresolved_subject": has_unresolved_subject,
            "unresolved_subjects":    unresolved_subjects,
            "unresolved_objects":     unresolved_objects,
        })
        stats.claims_written += 1
        stats.stated_by_edges += 1
        stats.supported_by_edges += 1

    return core_rows, mention_rows, stats


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

    # ── claims (M4) ───────────────────────────────────────────────────────────

    def write_claims(
        self,
        claim_inputs: list[tuple[ChunkRecord, ChunkExtraction]],
        canonical_store: CanonicalStore,
        *,
        extraction_method: str,
    ) -> ClaimStats:
        """Write the :Claim layer for a set of (chunk, extraction) pairs.

        Per docs/decisions/0005: :Claim MERGEd on a deterministic claim_id with
        status='alleged' written ON CREATE; exactly one STATED_BY :Person, one
        SUPPORTED_BY :Chunk, and MENTIONS edges for resolved subjects/objects.
        Unresolved subjects are recorded on the claim, never dropped. All writes
        are MERGE-only and idempotent. Core rows are written before MENTIONS so
        the claim node exists for the MENTIONS MATCH.
        """
        total = ClaimStats()
        core_rows: list[dict[str, Any]] = []
        mention_rows: dict[str, list[dict[str, str]]] = {g: [] for g in _MENTION_GROUPS}

        for chunk, extraction in claim_inputs:
            rows, mentions, stats = build_claim_rows(
                chunk, extraction, canonical_store,
                extraction_method=extraction_method,
            )
            core_rows.extend(rows)
            for group in _MENTION_GROUPS:
                mention_rows[group].extend(mentions[group])
            total.add(stats)

        for start in range(0, len(core_rows), BATCH_SIZE):
            batch = core_rows[start : start + BATCH_SIZE]
            with self._driver.session() as session:
                session.execute_write(lambda tx, b=batch: tx.run(_CLAIM_CORE, rows=b))

        for group in _MENTION_GROUPS:
            rows = mention_rows[group]
            if not rows:
                continue
            query = _CLAIM_MENTIONS_BY_TYPE[group]
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start : start + BATCH_SIZE]
                with self._driver.session() as session:
                    session.execute_write(
                        lambda tx, q=query, b=batch: tx.run(q, rows=b)
                    )

        return total
