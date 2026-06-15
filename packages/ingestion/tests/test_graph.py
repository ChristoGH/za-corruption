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

from commission_ingestion.extraction.schema import (
    ChunkExtraction,
    ExtractedClaim,
    ExtractedEntity,
)
from commission_ingestion.graph.mentions import DetectedMention
from commission_ingestion.graph.neo4j_store import (
    GraphStats,
    Neo4jStore,
    build_claim_rows,
    claim_key,
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


# ─── claim layer (M4) — docs/decisions/0005 ───────────────────────────────────

_METHOD = "claude-haiku-4-5:extract_v1"


def make_claim(
    *, speaker="ADV BALOYI SC", subject_refs=None, object_refs=None,
    predicate="stated that SAPS acted unlawfully", quote="SAPS acted unlawfully",
    certainty=None,
) -> ExtractedClaim:
    return ExtractedClaim(
        speaker=speaker,
        subject_refs=subject_refs if subject_refs is not None else [],
        predicate=predicate,
        object_refs=object_refs if object_refs is not None else [],
        quote=quote,
        certainty=certainty,
    )


def make_extraction(claims, entities=None) -> ChunkExtraction:
    return ChunkExtraction(
        entities=entities or [],
        mentions=[],
        claims=claims,
    )


def claim_chunk(text="ADV BALOYI SC: SAPS acted unlawfully in Johannesburg.") -> ChunkRecord:
    return make_chunk(text=text)


# ── claim_id MERGE key (Decision 1) ───────────────────────────────────────────

def test_claim_key_is_deterministic():
    a = claim_key("chunkA", "person:baloyi", "stated that X", 3, 10)
    b = claim_key("chunkA", "person:baloyi", "stated that X", 3, 10)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_claim_key_differs_on_distinct_fields():
    base = claim_key("chunkA", "person:baloyi", "stated that X", 3, 10)
    assert base != claim_key("chunkB", "person:baloyi", "stated that X", 3, 10)
    assert base != claim_key("chunkA", "person:madlanga", "stated that X", 3, 10)
    assert base != claim_key("chunkA", "person:baloyi", "stated that Y", 3, 10)
    assert base != claim_key("chunkA", "person:baloyi", "stated that X", 4, 11)


def test_claim_key_normalizes_predicate_whitespace_and_case():
    assert (
        claim_key("c", "p", "Stated  that\nX", 0, 1)
        == claim_key("c", "p", "stated that x", 0, 1)
    )


def test_claim_rows_idempotent_same_claim_id(canon: CanonicalStore):
    chunk = claim_chunk()
    ext = make_extraction([make_claim()])
    rows1, _, _ = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    rows2, _, _ = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert rows1[0]["claim_id"] == rows2[0]["claim_id"]


# ── status is writer-authored, never from input ───────────────────────────────

def test_status_alleged_is_cypher_literal_never_a_row_field(
    store: Neo4jStore, canon: CanonicalStore
):
    chunk = claim_chunk()
    ext = make_extraction([make_claim()])
    store.write_claims([(chunk, ext)], canon, extraction_method=_METHOD)
    core_q = next(q for q in store._driver.all_queries if ":Claim" in q)
    assert "cl.status = 'alleged'" in core_q
    # status set ON CREATE so re-runs never clobber a human-review status
    assert "ON CREATE SET" in core_q
    for params in store._driver.all_params:
        for row in params.get("rows", []):
            assert "status" not in row


# ── STATED_BY / SUPPORTED_BY (speaker + provenance) ───────────────────────────

def test_claim_has_stated_by_supported_by_and_matches_chunk(
    store: Neo4jStore, canon: CanonicalStore
):
    chunk = claim_chunk()
    store.write_claims([(chunk, make_extraction([make_claim()]))], canon,
                       extraction_method=_METHOD)
    core_q = next(q for q in store._driver.all_queries if ":Claim" in q)
    assert "STATED_BY" in core_q
    assert "SUPPORTED_BY" in core_q
    # Provenance is structural: the chunk is MATCHed (must pre-exist), never created
    assert "MATCH (ck:Chunk" in core_q
    row = next(p["rows"] for p in store._driver.all_params if p.get("rows"))[0]
    assert row["speaker_name"] == "Adv Sesi Baloyi SC"
    assert row["extraction_method"] == _METHOD


def test_claim_speaker_unresolved_is_skipped_and_counted(canon: CanonicalStore):
    chunk = claim_chunk()
    ext = make_extraction([make_claim(speaker="UNKNOWN SPEAKER ZZZ")])
    rows, mentions, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert rows == []
    assert stats.claims_written == 0
    assert stats.claims_speaker_unresolved == 1


def test_claim_quote_unrecoverable_is_skipped_and_counted(canon: CanonicalStore):
    chunk = claim_chunk(text="ADV BALOYI SC: Something entirely different was said.")
    ext = make_extraction([make_claim(quote="this phrase is not in the chunk at all")])
    rows, _, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert rows == []
    assert stats.claims_written == 0
    assert stats.claims_quote_unrecovered == 1


# ── subject edges + raw-subject fallthrough (Decision 2) ──────────────────────

def test_canonical_subject_becomes_mentions_edge(canon: CanonicalStore):
    chunk = claim_chunk()
    ext = make_extraction(
        [make_claim(subject_refs=["e1"])],
        entities=[ExtractedEntity(ref="e1", name="SAPS", type="org")],
    )
    rows, mentions, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert stats.claims_written == 1
    assert stats.mentions_edges == 1
    assert mentions["org"][0]["entity_name"] == "South African Police Service"
    assert mentions["org"][0]["role"] == "subject"
    assert rows[0]["has_unresolved_subject"] is False
    assert rows[0]["unresolved_subjects"] == []


def test_raw_subject_recorded_on_claim_not_dropped(canon: CanonicalStore):
    chunk = claim_chunk(text="ADV BALOYI SC: Maj-Gen Khumalo acted unlawfully here.")
    ext = make_extraction(
        [make_claim(subject_refs=["e1"], quote="acted unlawfully")],
        entities=[ExtractedEntity(ref="e1", name="MAJ-GEN KHUMALO", type="person")],
    )
    rows, mentions, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    # the claim IS written — the allegation is not lost
    assert stats.claims_written == 1
    # but no canonical MENTIONS edge, and the surface is kept on the claim, flagged
    assert mentions["person"] == []
    assert stats.mentions_edges == 0
    assert rows[0]["has_unresolved_subject"] is True
    assert rows[0]["unresolved_subjects"] == ["MAJ-GEN KHUMALO"]
    assert stats.claims_with_unresolved_subject == 1
    assert stats.unresolved_subject_refs == 1


def test_mixed_subject_partial_resolution(canon: CanonicalStore):
    chunk = claim_chunk(text="ADV BALOYI SC: SAPS and Maj-Gen Khumalo were involved.")
    ext = make_extraction(
        [make_claim(subject_refs=["e1", "e2"], quote="were involved")],
        entities=[
            ExtractedEntity(ref="e1", name="SAPS", type="org"),
            ExtractedEntity(ref="e2", name="MAJ-GEN KHUMALO", type="person"),
        ],
    )
    rows, mentions, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert stats.mentions_edges == 1          # SAPS resolved
    assert mentions["org"][0]["entity_name"] == "South African Police Service"
    assert rows[0]["unresolved_subjects"] == ["MAJ-GEN KHUMALO"]  # khumalo kept
    assert rows[0]["has_unresolved_subject"] is True


def test_object_ref_gets_role_object(canon: CanonicalStore):
    chunk = claim_chunk()
    ext = make_extraction(
        [make_claim(subject_refs=["e1"], object_refs=["e2"])],
        entities=[
            ExtractedEntity(ref="e1", name="SAPS", type="org"),
            ExtractedEntity(ref="e2", name="Johannesburg", type="place"),
        ],
    )
    _, mentions, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert mentions["org"][0]["role"] == "subject"
    assert mentions["place"][0]["role"] == "object"
    assert stats.mentions_edges == 2


def test_same_entity_subject_and_object_deduped(canon: CanonicalStore):
    chunk = claim_chunk()
    ext = make_extraction(
        [make_claim(subject_refs=["e1"], object_refs=["e1"])],
        entities=[ExtractedEntity(ref="e1", name="SAPS", type="org")],
    )
    _, mentions, stats = build_claim_rows(chunk, ext, canon, extraction_method=_METHOD)
    assert stats.mentions_edges == 1               # one edge, not two
    assert mentions["org"][0]["role"] == "subject"  # subject processed first


# ── banned relationships + MERGE-only (mirror M3 safety tests) ─────────────────

def _write_full_claim(store: Neo4jStore, canon: CanonicalStore) -> None:
    chunk = claim_chunk()
    ext = make_extraction(
        [make_claim(subject_refs=["e1"])],
        entities=[ExtractedEntity(ref="e1", name="SAPS", type="org")],
    )
    store.write_claims([(chunk, ext)], canon, extraction_method=_METHOD)


def test_claim_writer_no_appears_in(store: Neo4jStore, canon: CanonicalStore):
    _write_full_claim(store, canon)
    assert "APPEARS_IN" not in store._driver.combined_query_text()


def test_claim_writer_only_uses_canonical_claim_relationships(
    store: Neo4jStore, canon: CanonicalStore
):
    _write_full_claim(store, canon)
    text = store._driver.combined_query_text()
    # the only relationship types the claim writer may emit
    assert "STATED_BY" in text
    assert "SUPPORTED_BY" in text
    assert "MENTIONS" in text
    # MENTIONS originates AT the claim — never a subject wired bypassing it
    for q in store._driver.all_queries:
        if "MENTIONS" in q:
            assert "(cl)-[m:MENTIONS]->(e" in q


def test_claim_writer_uses_merge_not_bare_create(
    store: Neo4jStore, canon: CanonicalStore
):
    _write_full_claim(store, canon)
    for q in store._driver.all_queries:
        lines = [ln for ln in q.splitlines() if not ln.strip().startswith("ON CREATE")]
        assert "CREATE (" not in "\n".join(lines), f"bare CREATE in:\n{q}"


def test_claim_writer_returns_per_type_counts(store: Neo4jStore, canon: CanonicalStore):
    chunk = claim_chunk()
    ext = make_extraction(
        [make_claim(subject_refs=["e1"])],
        entities=[ExtractedEntity(ref="e1", name="SAPS", type="org")],
    )
    stats = store.write_claims([(chunk, ext)], canon, extraction_method=_METHOD)
    assert stats.claims_written == 1
    assert stats.stated_by_edges == 1
    assert stats.supported_by_edges == 1
    assert stats.mentions_edges == 1
