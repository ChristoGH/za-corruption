"""M3 graph layer tests — spine integrity, edge correctness, banned relationships.

Uses a FakeDriver that captures every Cypher query executed; no running Neo4j
and no spaCy/torch needed.  Covers:
  - hearing_key / page_key helpers
  - Paged spine uses :Page nodes (HAS_PAGE + HAS_CHUNK); rows carry page_key
  - Bootstrap spine skips :Page nodes; Document -[:HAS_CHUNK]-> Chunk only
  - All spine writes use MERGE, never bare CREATE
  - APPEARS_IN never appears in any query
  - :Claim never written by any write method
  - SPOKE_IN resolved via canonical store; unresolved labels skipped
  - MENTIONED_IN resolved via canonical store; unresolved mentions skipped
  - Same canonical entity mentioned twice in one chunk → one MENTIONED_IN row
  - Unresolved mentions leave the graph unchanged (not invented)
  - doc_sha256 stored on Chunk node for idempotency queries
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pytest

from commission_ingestion.graph.mentions import DetectedMention
from commission_ingestion.graph.neo4j_store import (
    GraphStats,
    Neo4jStore,
    hearing_key,
    page_key,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.resolution.canonical import CanonicalEntity, CanonicalStore


# ─── fake driver ──────────────────────────────────────────────────────────────

class _FakeResult:
    def single(self):
        return None


class _FakeTx:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[dict] = []

    def run(self, query: str, **params) -> _FakeResult:
        self.queries.append(query)
        self.params.append(params)
        return _FakeResult()


class _FakeSession:
    def __init__(self) -> None:
        self._tx = _FakeTx()

    @property
    def queries(self) -> list[str]:
        return self._tx.queries

    @property
    def params(self) -> list[dict]:
        return self._tx.params

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def execute_write(self, fn, *args, **kwargs):
        return fn(self._tx, *args, **kwargs)

    def execute_read(self, fn, *args, **kwargs):
        return fn(self._tx, *args, **kwargs)


class FakeDriver:
    """Captures all Cypher calls — no network, no Neo4j process."""

    def __init__(self) -> None:
        self._session = _FakeSession()

    def session(self, **_kwargs) -> _FakeSession:
        return self._session

    def close(self) -> None:
        pass

    @property
    def all_queries(self) -> list[str]:
        return self._session.queries

    @property
    def all_params(self) -> list[dict]:
        return self._session.params

    def combined_query_text(self) -> str:
        return "\n".join(self.all_queries)


# ─── fixtures ─────────────────────────────────────────────────────────────────

_SHA = "ab" * 32   # 64 hex chars


def make_source(**overrides) -> SourceRecord:
    defaults = dict(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        source_type="transcript",
        document_type="Transcript",
        day_no=1,
        date="2025-09-17",
        url="https://example.org/day1.pdf",
        filename="day1.pdf",
        downloaded=True,
        sha256=_SHA,
        authoritative=True,
    )
    defaults.update(overrides)
    return SourceRecord(**defaults)


def make_chunk(index: int = 0, *, sha: str = _SHA, **overrides) -> ChunkRecord:
    text = f"Testimony chunk {index}."
    defaults = dict(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        doc_sha256=sha,
        source_url="https://example.org/day1.pdf",
        day_no=1,
        date="2025-09-17",
        chunk_id=hashlib.sha256(f"{sha}:{index}".encode()).hexdigest(),
        chunk_index=index,
        page_start=index + 1,
        page_end=index + 2,
        speakers=["CHAIRPERSON"],
        n_turns=1,
        text=text,
        char_count=len(text),
    )
    defaults.update(overrides)
    return ChunkRecord(**defaults)


def minimal_canonical() -> CanonicalStore:
    return CanonicalStore([
        CanonicalEntity(
            entity_id="person:madlanga",
            name="Justice Mbuyiseli Madlanga",
            entity_type="person",
            aliases=["CHAIRPERSON", "THE CHAIRPERSON"],
        ),
        CanonicalEntity(
            entity_id="person:baloyi",
            name="Adv Sesi Baloyi SC",
            entity_type="person",
            aliases=["ADV BALOYI SC", "ADV BALOYI ISC"],
        ),
        CanonicalEntity(
            entity_id="org:saps",
            name="South African Police Service",
            entity_type="org",
            aliases=["SAPS"],
        ),
        CanonicalEntity(
            entity_id="place:johannesburg",
            name="Johannesburg",
            entity_type="place",
            aliases=["Joburg"],
        ),
    ])


@pytest.fixture()
def store() -> Neo4jStore:
    return Neo4jStore(driver=FakeDriver())


@pytest.fixture()
def canon() -> CanonicalStore:
    return minimal_canonical()


# ─── hearing_key / page_key helpers ───────────────────────────────────────────

def test_hearing_key_standard_case():
    assert hearing_key("madlanga", 36, "2025-11-07") == "madlanga-day-36-2025-11-07"


def test_hearing_key_fallback_when_day_or_date_missing():
    assert hearing_key("zondo", None, "2019-08-19") == "zondo-unknown"
    assert hearing_key("zondo", 1, None) == "zondo-unknown"


def test_page_key_format():
    assert page_key("ab" * 32, 7) == f"{'ab' * 32}:7"


# ─── paged spine ──────────────────────────────────────────────────────────────

def test_paged_spine_uses_page_nodes(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=True))
    text = store._driver.combined_query_text()
    assert "HAS_PAGE" in text
    assert "HAS_CHUNK" in text


def test_paged_spine_includes_page_key_in_rows(store: Neo4jStore):
    store.write_spine([make_chunk(0)], make_source(authoritative=True))
    rows = store._driver.all_params[0]["rows"]
    assert "page_key" in rows[0]
    assert rows[0]["page_key"] == page_key(_SHA, 1)  # page_start = chunk_index + 1


def test_paged_spine_stores_doc_sha256_on_chunk_rows(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=True))
    rows = store._driver.all_params[0]["rows"]
    assert rows[0]["doc_sha256"] == _SHA


# ─── bootstrap spine ──────────────────────────────────────────────────────────

def test_bootstrap_spine_skips_page_nodes(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=False))
    text = store._driver.combined_query_text()
    assert "HAS_PAGE" not in text


def test_bootstrap_spine_uses_has_chunk_on_document(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=False))
    text = store._driver.combined_query_text()
    # Document→Chunk is the bootstrap path — HAS_CHUNK must be present
    assert "HAS_CHUNK" in text


def test_bootstrap_spine_excludes_page_key_from_rows(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=False))
    rows = store._driver.all_params[0]["rows"]
    assert "page_key" not in rows[0]


# ─── safety invariants (apply to ALL write operations) ────────────────────────

def _do_all_writes(store: Neo4jStore, canon: CanonicalStore) -> None:
    chunk = make_chunk(speakers=["CHAIRPERSON"])
    source = make_source(authoritative=True)
    store.write_spine([chunk], source)
    store.write_speaker_edges([chunk], canon)
    store.write_mention_edges(
        [(chunk.chunk_id, [
            DetectedMention("South African Police Service", "org"),
            DetectedMention("Justice Mbuyiseli Madlanga", "person"),
        ])],
        canon,
    )


def test_no_appears_in_in_any_query(store: Neo4jStore, canon: CanonicalStore):
    _do_all_writes(store, canon)
    assert "APPEARS_IN" not in store._driver.combined_query_text()


def test_no_claim_nodes_written(store: Neo4jStore, canon: CanonicalStore):
    _do_all_writes(store, canon)
    # "Claim" must not appear as a node label in any write query
    for q in store._driver.all_queries:
        assert ":Claim" not in q, f"Claim node found in query: {q!r}"


def test_all_writes_use_merge_not_bare_create(store: Neo4jStore, canon: CanonicalStore):
    _do_all_writes(store, canon)
    for q in store._driver.all_queries:
        # Strip ON CREATE SET lines — those are legitimate MERGE sub-clauses
        lines_without_on_create = [
            ln for ln in q.splitlines()
            if not ln.strip().startswith("ON CREATE")
        ]
        joined = "\n".join(lines_without_on_create)
        assert "CREATE (" not in joined, (
            f"Bare CREATE node found in query (not inside ON CREATE SET):\n{q}"
        )


def test_paged_has_chunk_only_via_page_not_directly(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=True))
    queries = store._driver.all_queries
    # In the paged query the chain must be HAS_PAGE then HAS_CHUNK, never
    # a direct Document→HAS_CHUNK edge.
    assert any("HAS_PAGE" in q and "HAS_CHUNK" in q for q in queries)
    # There must be no query that has HAS_CHUNK WITHOUT HAS_PAGE in the paged path.
    for q in queries:
        if "HAS_CHUNK" in q:
            # If HAS_PAGE is not in the same query, that is the bootstrap query
            # on an authoritative doc — which would be the bug.
            # Here source is authoritative so HAS_PAGE must also be present.
            assert "HAS_PAGE" in q, (
                "Paged doc: found HAS_CHUNK without HAS_PAGE in same query"
            )


# ─── SPOKE_IN ─────────────────────────────────────────────────────────────────

def test_spoke_in_resolves_canonical_name(store: Neo4jStore, canon: CanonicalStore):
    chunk = make_chunk(speakers=["CHAIRPERSON"])
    written, unresolved = store.write_speaker_edges([chunk], canon)
    assert written == 1
    assert unresolved == 0
    rows = store._driver.all_params[0]["rows"]
    assert rows[0]["canonical_name"] == "Justice Mbuyiseli Madlanga"
    assert rows[0]["speaker_label"] == "CHAIRPERSON"
    assert "SPOKE_IN" in store._driver.all_queries[0]


def test_spoke_in_skips_unresolved_labels(store: Neo4jStore, canon: CanonicalStore):
    chunk = make_chunk(speakers=["UNKNOWN PERSON XYZ"])
    written, unresolved = store.write_speaker_edges([chunk], canon)
    assert written == 0
    assert unresolved == 1
    assert store._driver.all_queries == []  # no Neo4j call at all


def test_spoke_in_multiple_speakers_per_chunk(store: Neo4jStore, canon: CanonicalStore):
    chunk = make_chunk(speakers=["CHAIRPERSON", "ADV BALOYI SC"])
    written, unresolved = store.write_speaker_edges([chunk], canon)
    assert written == 2
    assert unresolved == 0


def test_spoke_in_query_has_speaker_label_property(store: Neo4jStore, canon: CanonicalStore):
    chunk = make_chunk(speakers=["CHAIRPERSON"])
    store.write_speaker_edges([chunk], canon)
    assert "speaker_label" in store._driver.all_queries[0]


# ─── MENTIONED_IN ─────────────────────────────────────────────────────────────

def test_mention_edges_written_for_resolved_entity(
    store: Neo4jStore, canon: CanonicalStore
):
    chunk = make_chunk()
    mentions = [DetectedMention("SAPS", "org")]
    written, unresolved = store.write_mention_edges(
        [(chunk.chunk_id, mentions)], canon
    )
    assert written == 1
    assert unresolved == 0
    assert "MENTIONED_IN" in store._driver.combined_query_text()


def test_mention_edges_skip_unresolved(store: Neo4jStore, canon: CanonicalStore):
    chunk = make_chunk()
    mentions = [DetectedMention("Unknown Entity ZZZ", "person")]
    written, unresolved = store.write_mention_edges(
        [(chunk.chunk_id, mentions)], canon
    )
    assert written == 0
    assert unresolved == 1
    assert store._driver.all_queries == []


def test_mention_edge_deduped_per_chunk(store: Neo4jStore, canon: CanonicalStore):
    chunk = make_chunk()
    # Same canonical entity via two different surface forms
    mentions = [
        DetectedMention("SAPS", "org"),
        DetectedMention("South African Police Service", "org"),
    ]
    written, _ = store.write_mention_edges([(chunk.chunk_id, mentions)], canon)
    # Should produce exactly one MENTIONED_IN row for org:saps
    assert written == 1


def test_mentioned_in_uses_correct_node_label_for_each_type(
    store: Neo4jStore, canon: CanonicalStore
):
    chunk = make_chunk()
    mentions = [
        DetectedMention("Justice Mbuyiseli Madlanga", "person"),
        DetectedMention("South African Police Service", "org"),
        DetectedMention("Johannesburg", "place"),
    ]
    store.write_mention_edges([(chunk.chunk_id, mentions)], canon)
    text = store._driver.combined_query_text()
    assert "Person" in text
    assert "Organisation" in text
    assert "Place" in text


def test_mention_edges_unresolved_never_create_nodes(
    store: Neo4jStore, canon: CanonicalStore
):
    chunk = make_chunk()
    # All three types with unresolvable surfaces
    mentions = [
        DetectedMention("Mystery Person", "person"),
        DetectedMention("Ghost Corp", "org"),
        DetectedMention("Atlantis", "place"),
    ]
    written, unresolved = store.write_mention_edges(
        [(chunk.chunk_id, mentions)], canon
    )
    assert written == 0
    assert unresolved == 3
    # Absolute silence — no Cypher executed at all
    assert store._driver.all_queries == []


# ─── zero :Claim after a full paged load cycle ────────────────────────────────

def test_zero_claim_nodes_after_full_load_cycle(store: Neo4jStore, canon: CanonicalStore):
    chunks = [make_chunk(i, speakers=["CHAIRPERSON"]) for i in range(3)]
    source = make_source(authoritative=True)
    store.write_spine(chunks, source)
    store.write_speaker_edges(chunks, canon)
    store.write_mention_edges(
        [(c.chunk_id, [DetectedMention("SAPS", "org")]) for c in chunks], canon
    )
    all_text = store._driver.combined_query_text()
    assert ":Claim" not in all_text
    assert "APPEARS_IN" not in all_text


# ─── idempotency: MERGE guarantees ────────────────────────────────────────────

def test_spine_queries_only_use_merge(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=True))
    for q in store._driver.all_queries:
        assert "MERGE" in q, f"Expected MERGE in spine query:\n{q}"


def test_bootstrap_spine_queries_only_use_merge(store: Neo4jStore):
    store.write_spine([make_chunk()], make_source(authoritative=False))
    for q in store._driver.all_queries:
        assert "MERGE" in q
