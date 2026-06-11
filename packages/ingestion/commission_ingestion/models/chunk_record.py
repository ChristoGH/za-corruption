"""Speaker-aware chunk record — the deterministic provenance backbone.

One :Chunk-to-be, carrying full lineage back to the source document, hearing day,
and PDF page range. Produced by the parsing pipeline; consumed later by Qdrant
(semantic search) and Neo4j (graph). Schema-versioned like SourceRecord.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

CHUNK_SCHEMA_VERSION = "1.0"


class ChunkRecord(BaseModel):
    schema_version: str = CHUNK_SCHEMA_VERSION

    # Provenance back to the source document / registry record.
    commission_slug: str
    commission_name: str
    doc_sha256: str
    source_url: str
    source_page_url: str | None = None

    # Hearing context.
    day_no: int | None = None
    date: str | None = None

    # Chunk identity and ordering within the document.
    chunk_id: str = Field(description="sha256 hex of the chunk text — stable/idempotent")
    chunk_index: int = Field(description="0-based order of this chunk within the document")

    # Page provenance (1-based PDF page numbers; see docs/parse-notes.md on the
    # printed 'Page N of M' offset).
    page_start: int
    page_end: int

    # Speaker-aware content.
    speakers: list[str] = Field(default_factory=list)
    n_turns: int = 0
    text: str
    char_count: int = 0
