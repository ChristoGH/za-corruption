"""Qdrant store for the shared `commission_transcripts` collection.

Canonical design: docs/qdrant-model.md — one collection for every commission,
filtered by `commission_slug`. Qdrant point IDs must be UUIDs or unsigned ints,
so the point id is `uuid5(NAMESPACE_URL, chunk_id)`; the sha256 `chunk_id`
stays in the payload as the join key to the Neo4j `:Chunk`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.vector.embedder import VECTOR_SIZE

COLLECTION_NAME = "commission_transcripts"
DEFAULT_QDRANT_URL = "http://localhost:6333"

# Payload fields filtered on routinely — indexed at collection bootstrap.
_KEYWORD_INDEXES = ("commission_slug", "source_type", "sha256", "speakers", "chunk_id")
_INTEGER_INDEXES = ("day_no",)


def point_id_for_chunk(chunk_id: str) -> str:
    """Deterministic Qdrant point UUID for a chunk's sha256 id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def chunk_payload(chunk: ChunkRecord, source: SourceRecord) -> dict:
    """Full point payload per docs/qdrant-model.md, plus the chunk text/ordering.

    `source` is the registry record for the chunk's document; it supplies the
    fields the ChunkRecord does not carry (source_type, document_type,
    authoritative, filename).
    """
    return {
        "commission_slug": chunk.commission_slug,
        "commission_name": chunk.commission_name,
        "source_type": source.source_type,
        "document_type": source.document_type,
        "day_no": chunk.day_no,
        "date": chunk.date,
        "source_url": chunk.source_url,
        "authoritative": source.authoritative,
        "filename": source.filename,
        "sha256": chunk.doc_sha256,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "time_start": chunk.time_start,
        "time_end": chunk.time_end,
        "transcription_method": source.transcription_method,
        "chunk_id": chunk.chunk_id,
        "speakers": chunk.speakers,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
    }


def build_filter(
    *,
    commission: str | None = None,
    day_no: int | None = None,
    speaker: str | None = None,
    sha256: str | None = None,
) -> qm.Filter | None:
    """Payload filter for the shared collection; None when no condition is set.

    `speaker` matches any element of the `speakers` array.
    """
    must: list[qm.Condition] = []
    if commission is not None:
        must.append(
            qm.FieldCondition(key="commission_slug", match=qm.MatchValue(value=commission))
        )
    if day_no is not None:
        must.append(qm.FieldCondition(key="day_no", match=qm.MatchValue(value=day_no)))
    if speaker is not None:
        must.append(qm.FieldCondition(key="speakers", match=qm.MatchValue(value=speaker)))
    if sha256 is not None:
        must.append(qm.FieldCondition(key="sha256", match=qm.MatchValue(value=sha256)))
    return qm.Filter(must=must) if must else None


class QdrantStore:
    def __init__(self, client: QdrantClient | None = None, url: str | None = None) -> None:
        self.client = client or QdrantClient(
            url=url or os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL),
            api_key=os.environ.get("QDRANT_API_KEY"),
        )

    def ensure_collection(self) -> None:
        """Create the shared collection and payload indexes if absent. Idempotent."""
        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=qm.VectorParams(
                    size=VECTOR_SIZE, distance=qm.Distance.COSINE
                ),
            )
        for field in _KEYWORD_INDEXES:
            self._ensure_index(field, qm.PayloadSchemaType.KEYWORD)
        for field in _INTEGER_INDEXES:
            self._ensure_index(field, qm.PayloadSchemaType.INTEGER)

    def _ensure_index(self, field: str, schema: qm.PayloadSchemaType) -> None:
        info = self.client.get_collection(COLLECTION_NAME)
        if field not in (info.payload_schema or {}):
            self.client.create_payload_index(
                collection_name=COLLECTION_NAME, field_name=field, field_schema=schema
            )

    def upsert_chunks(
        self,
        chunks: Sequence[ChunkRecord],
        vectors: Sequence[Sequence[float]],
        source: SourceRecord,
    ) -> None:
        """Upsert one document's chunks. Deterministic ids make re-runs idempotent."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        points = [
            qm.PointStruct(
                id=point_id_for_chunk(chunk.chunk_id),
                vector=list(vector),
                payload=chunk_payload(chunk, source),
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        self.client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)

    def count(self, *, sha256: str | None = None, commission: str | None = None) -> int:
        result = self.client.count(
            collection_name=COLLECTION_NAME,
            count_filter=build_filter(sha256=sha256, commission=commission),
            exact=True,
        )
        return result.count

    def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 5,
        commission: str | None = None,
        day_no: int | None = None,
        speaker: str | None = None,
    ) -> list[qm.ScoredPoint]:
        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=list(query_vector),
            query_filter=build_filter(
                commission=commission, day_no=day_no, speaker=speaker
            ),
            limit=limit,
            with_payload=True,
        )
        return response.points

    def delete_by_sha(self, sha256: str) -> None:
        """Remove every point of one document — used when its registry record
        is marked superseded_by (duplicate publication of the same sitting)."""
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qm.FilterSelector(filter=build_filter(sha256=sha256)),
            wait=True,
        )

    def existing_chunk_ids(self, sha256: str) -> set[str]:
        """chunk_ids already stored for a document — used for idempotent loads."""
        found: set[str] = set()
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=build_filter(sha256=sha256),
                limit=1000,
                offset=offset,
                with_payload=["chunk_id"],
                with_vectors=False,
            )
            for point in points:
                if point.payload and point.payload.get("chunk_id"):
                    found.add(point.payload["chunk_id"])
            if offset is None:
                return found
