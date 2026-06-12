"""Vector store layer: embeddings + the shared Qdrant collection (M2)."""

from commission_ingestion.vector.embedder import (
    EMBEDDING_MODEL,
    QUERY_PREFIX,
    VECTOR_SIZE,
    BgeSmallEmbedder,
    Embedder,
)
from commission_ingestion.vector.qdrant_store import (
    COLLECTION_NAME,
    QdrantStore,
    build_filter,
    chunk_payload,
    point_id_for_chunk,
)

__all__ = [
    "BgeSmallEmbedder",
    "COLLECTION_NAME",
    "EMBEDDING_MODEL",
    "Embedder",
    "QUERY_PREFIX",
    "QdrantStore",
    "VECTOR_SIZE",
    "build_filter",
    "chunk_payload",
    "point_id_for_chunk",
]
