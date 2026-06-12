"""Sentence embeddings for chunk text — BAAI/bge-small-en-v1.5 per docs/qdrant-model.md.

384-dim, cosine distance, normalised at encode time. BGE asymmetric retrieval:
queries get the instruction prefix, passages are embedded as-is.

sentence-transformers (and its torch dependency) is an optional extra
(`commission-ingestion[vector]`); import lazily so the rest of the package —
and code that injects a fake embedder — works without it.
"""

from __future__ import annotations

from typing import Protocol

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
VECTOR_SIZE = 384
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    """What the store/CLIs need; satisfied by BgeSmallEmbedder or a test fake."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class BgeSmallEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise ImportError(
                "sentence-transformers is required for embedding; install the "
                "'vector' extra: uv sync --all-packages --all-extras"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode(
            QUERY_PREFIX + text, normalize_embeddings=True, show_progress_bar=False
        )
        return vector.tolist()
