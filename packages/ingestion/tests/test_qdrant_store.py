"""Tests for the M2 vector layer: payloads, ids, idempotent load, filtered search.

Uses qdrant-client's in-memory local mode and a deterministic fake embedder —
no running Qdrant and no sentence-transformers/torch needed.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from qdrant_client import QdrantClient

from commission_ingestion.cli.load_qdrant import load_corpus
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.vector.embedder import VECTOR_SIZE
from commission_ingestion.vector.qdrant_store import (
    COLLECTION_NAME,
    QdrantStore,
    chunk_payload,
    point_id_for_chunk,
)


class FakeEmbedder:
    """Deterministic unit vectors derived from the text hash."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [(digest[i % len(digest)] - 128) / 128 for i in range(VECTOR_SIZE)]
        norm = sum(value * value for value in raw) ** 0.5
        return [value / norm for value in raw]


def make_source(**overrides) -> SourceRecord:
    defaults = dict(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        source_type="transcript",
        document_type="Transcript",
        day_no=3,
        date="2025-09-19",
        url="https://example.org/day3.pdf",
        filename="day3.pdf",
        downloaded=True,
        sha256="doc3" * 16,
    )
    defaults.update(overrides)
    return SourceRecord(**defaults)


def make_chunk(index: int, text: str, *, sha256: str = "doc3" * 16, **overrides) -> ChunkRecord:
    defaults = dict(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        doc_sha256=sha256,
        source_url="https://example.org/day3.pdf",
        day_no=3,
        date="2025-09-19",
        chunk_id=hashlib.sha256(f"{sha256}:{index}:{text}".encode()).hexdigest(),
        chunk_index=index,
        page_start=index + 1,
        page_end=index + 2,
        speakers=["CHAIRPERSON", "ADV CHASKALSON SC"],
        n_turns=2,
        text=text,
        char_count=len(text),
    )
    defaults.update(overrides)
    return ChunkRecord(**defaults)


@pytest.fixture()
def store() -> QdrantStore:
    return QdrantStore(client=QdrantClient(":memory:"))


def test_point_id_is_stable_uuid5_of_chunk_id():
    chunk_id = "ab" * 32
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
    assert point_id_for_chunk(chunk_id) == expected
    assert point_id_for_chunk(chunk_id) == point_id_for_chunk(chunk_id)


def test_payload_carries_every_field_from_qdrant_model_doc():
    payload = chunk_payload(make_chunk(0, "Some testimony."), make_source())
    required = {
        "commission_slug",
        "commission_name",
        "source_type",
        "document_type",
        "day_no",
        "date",
        "source_url",
        "authoritative",
        "filename",
        "sha256",
        "page_start",
        "page_end",
        "chunk_id",
        "speakers",
    }
    assert required <= payload.keys()
    assert payload["authoritative"] is True
    assert payload["sha256"] == "doc3" * 16
    assert payload["text"] == "Some testimony."  # needed for snippets


def test_upsert_is_idempotent_and_count_matches(store: QdrantStore):
    source = make_source()
    chunks = [make_chunk(i, f"Testimony chunk number {i}.") for i in range(5)]
    embedder = FakeEmbedder()

    store.ensure_collection()
    vectors = embedder.embed_passages([c.text for c in chunks])
    store.upsert_chunks(chunks, vectors, source)
    assert store.count() == 5

    # Re-upsert: same deterministic ids, zero new points.
    store.upsert_chunks(chunks, vectors, source)
    assert store.count() == 5
    assert store.count(sha256=source.sha256) == 5
    assert store.existing_chunk_ids(source.sha256) == {c.chunk_id for c in chunks}


def test_load_corpus_skips_fully_loaded_documents(store: QdrantStore):
    source = make_source()
    chunks = [make_chunk(i, f"Testimony chunk number {i}.") for i in range(3)]
    sources = {source.sha256: source}

    stats = load_corpus(store, FakeEmbedder(), [chunks], sources)
    assert stats["docs_loaded"] == 1
    assert stats["chunks_upserted"] == 3

    # Second run: already loaded — no embedding, no upserts, and no need for
    # an embedder at all.
    stats = load_corpus(store, None, [chunks], sources, make_embedder=None)
    assert stats["docs_skipped"] == 1
    assert stats["chunks_upserted"] == 0
    assert store.count() == 3


def test_load_corpus_flags_missing_registry_record(store: QdrantStore):
    chunks = [make_chunk(0, "Orphan doc.", sha256="feed" * 16)]
    stats = load_corpus(store, FakeEmbedder(), [chunks], sources={})
    assert stats["docs_no_source"] == 1
    assert store.count() == 0


def test_search_filters_by_day_and_speaker(store: QdrantStore):
    embedder = FakeEmbedder()
    day3_source = make_source()
    day4_source = make_source(
        url="https://example.org/day4.pdf",
        filename="day4.pdf",
        sha256="doc4" * 16,
        day_no=4,
        date="2025-09-22",
    )
    day3 = [make_chunk(i, f"Day three testimony {i}.") for i in range(2)]
    day4 = [
        make_chunk(
            i,
            f"Day four testimony {i}.",
            sha256="doc4" * 16,
            source_url="https://example.org/day4.pdf",
            day_no=4,
            date="2025-09-22",
            speakers=["MR MOGOTSI"],
        )
        for i in range(2)
    ]
    load_corpus(
        store,
        embedder,
        [day3, day4],
        {day3_source.sha256: day3_source, day4_source.sha256: day4_source},
    )

    query = embedder.embed_query("testimony")
    assert len(store.search(query, limit=10)) == 4

    day4_hits = store.search(query, limit=10, day_no=4)
    assert {hit.payload["day_no"] for hit in day4_hits} == {4}

    mogotsi_hits = store.search(query, limit=10, speaker="MR MOGOTSI")
    assert len(mogotsi_hits) == 2
    assert all("MR MOGOTSI" in hit.payload["speakers"] for hit in mogotsi_hits)

    chair_day4 = store.search(query, limit=10, speaker="CHAIRPERSON", day_no=4)
    assert chair_day4 == []
