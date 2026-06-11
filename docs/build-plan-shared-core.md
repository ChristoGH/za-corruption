# Build Plan — Shared Core

Madlanga and Zondo are **not** two separate implementations. They are two commission
**adapters** over one shared ingestion, storage and ontology core. This file is that
core. The two commission plans (`build-plan-madlanga.md`, `build-plan-zondo.md`) contain
only adapter-specific deltas and point back here.

Canonical references: `ontology.md`, `qdrant-model.md`, `neo4j-model.md`,
`decisions/0004-shared-core-commission-adapters.md`.

## 1. Architecture

```
CommissionAdapter.discover_sources()  ─→  SourceRecord[]
        ↓ download (+SHA256)
        ↓ parse PDF  (adapter supplies day/date + speaker rules)
        ↓ speaker-aware chunk
        ↓ extract  (deterministic → spaCy → Claude LLM → human review)
        ↓
   ┌────────────────────────────┐     ┌──────────────────────────────┐
   │ Qdrant: commission_transcripts │ │ Neo4j: Document→Page→Chunk graph │
   └────────────────────────────┘     └──────────────────────────────┘
```

The pipeline is commission-agnostic. Everything site- or domain-specific is isolated
behind the adapter (§3).

## 2. Where the code lives

Per `directory-structure.md`, shared code lives in `packages/ingestion/commission_ingestion/`:

```
discovery/   base.py (SourceRecord, discovery helpers), <commission>.py adapters
download/    downloader.py (+SHA256), registry.py
parsing/     pdf_text.py, transcript.py, speakers.py   # engine; rules come from adapter
chunking/    speaker_chunks.py, chunk_ids.py
extraction/  entities.py, roles.py, events.py, claims.py, normalisation.py
stores/      qdrant_store.py, neo4j_store.py, source_store.py
pipeline/    run.py, steps.py, cli.py
```

The API (`apps/api`) and web app (`apps/web`) **query** the stores; they never own
ingestion logic.

## 3. The CommissionAdapter interface

Each commission supplies one adapter. The shared pipeline calls only this surface:

```python
class CommissionAdapter(Protocol):
    slug: str                      # "zondo" | "madlanga"
    name: str                      # "Zondo Commission"
    supported_source_types: list[str]   # ["transcript", "statement", "report"]
    ingestion_phases: list[str]         # ordered phase names

    def discover_sources(self) -> list[SourceRecord]: ...
    def parse_day_metadata(self, text: str) -> DayMetadata: ...   # day_no, date
    def speaker_regex(self) -> re.Pattern: ...
    def role_hint_map(self) -> dict[str, str]: ...   # speaker token → procedural role
    def taxonomy_overlay(self) -> TaxonomyOverlay: ...  # org/event/matter type maps
```

Everything that differs between commissions — base URL and discovery strategy, the
day/date regex, the speaker regex, the role-hint vocabulary, taxonomy classes, which
source types and phases are supported — is config on the adapter, not branching in the
core.

## 4. SourceRecord — standard discovery output

Discovery returns **structured records, never bare URL strings** (both adapters conform):

```python
class SourceRecord:
    schema_version: str = "1.1"
    commission_slug: str        # "zondo"
    commission_name: str        # "Zondo Commission"
    source_type: str            # "transcript"
    document_type: str          # "Transcript"  (DocumentType vocab)
    authoritative: bool = True  # False for DSFSI bootstrap plaintext
    day_no: int | None          # 327
    date: str | None            # "2021-01-13"
    title: str                  # "Day 327 - 2021-01-13"
    url: str                    # download URL (canonicalised for registry dedup)
    source_page_url: str        # page the link was discovered on
    discovered_at: datetime     # UTC timestamp
    downloaded: bool = False
    local_path: str | None = None
    sha256: str | None = None
    notes: str | None = None
```

Persist discovery output immediately to the **single combined**
`data/sources/source_registry.jsonl` so re-runs don't re-download and so out-of-band
metadata (day/date that appears *around* a link, not in it) is captured once. Primary
registry dedup is by `url`; `sha256` groups duplicate underlying documents for
logging/review only — multiple official URLs are provenance and must not be merged away.
Per-commission `<slug>_sources.jsonl` files in older layout docs are superseded by this
combined registry.

## 5. Shared pipeline stages

These stages are identical for every commission and live in the core:

1. **discover** — `adapter.discover_sources()` → `SourceRecord[]` → `source_store`.
2. **download** — stream to `data/raw/<slug>/`, compute SHA256, skip if present.
3. **parse** — PyMuPDF page text + `clean_page_text`; `adapter.parse_day_metadata()` for
   day/date; `adapter.speaker_regex()` to split speaker turns with page tracking.
4. **chunk** — group speaker turns up to `max_chars` (~1800), `chunk_id = sha256(text)`,
   record `page_start`/`page_end`/`speakers`.
5. **extract** — progressive, see §6.
6. **store Qdrant** — upsert into the single `commission_transcripts` collection with the
   full payload from `qdrant-model.md` (id = `chunk_id`).
7. **store Neo4j** — write the `Document → Page → Chunk` spine plus mentions/roles per
   `neo4j-model.md`.

`chunk_id` and `sha256` join the two stores; a chunk is written to both in the same run.

## 6. Progressive extraction (shared phases)

1. **Deterministic** — metadata, day/date, pages, speaker labels, chunk IDs, hashes,
   URLs. The provenance backbone; build first.
2. **NLP (spaCy `en_core_web_trf`)** — Person/Organisation/Place mentions; procedural
   role inference from speaker labels via `adapter.role_hint_map()`.
3. **LLM-assisted (Anthropic Claude SDK, direct, with prompt caching)** — events, claims,
   procedural roles, real-world positions, relationships, returned as structured JSON
   with `confidence` and `extraction_method`. Keep behind a pluggable extractor
   interface so phases 1–2 don't depend on it.
4. **Human review** — alias/duplicate resolution, confirmation of high-risk claims.

The LLM pass must never silently promote a claim to a fact or invent a field a witness
did not state. See `ontology.md` §1 (Mention ≠ Claim ≠ Finding ≠ Fact).

### Claim & event layer is canonical from the start
Even if the first milestone only writes mentions and procedural roles, the `:Claim` and
`:Event` provenance model (`ontology.md` §2) is part of the canonical schema. Claims are
written as `(:Claim {status, attribution, confidence})-[:SUPPORTED_BY]->(:Chunk)` and
`-[:STATED_BY]->(:Person)` — never as asserted fact edges.

## 7. Services (shared)

`docker-compose.yml` (Qdrant + Neo4j 5.26 with APOC):

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrant_storage:/qdrant/storage"]
  neo4j:
    image: neo4j:5.26
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
      NEO4J_PLUGINS: '["apoc"]'
    volumes: ["neo4j_data:/data", "neo4j_logs:/logs"]
volumes: { qdrant_storage:, neo4j_data:, neo4j_logs: }
```

## 8. Dependencies (shared)

Python ≥3.11: `requests`, `beautifulsoup4`, `playwright`, `pymupdf`, `qdrant-client`,
`neo4j`, `sentence-transformers`, `spacy`, `anthropic`, `python-dotenv`, `pydantic`,
`tqdm`. Post-install: `python -m spacy download en_core_web_trf` and
`playwright install chromium`.

## 9. MVP success test

Search `commission_transcripts` for a topic → open a hit → jump from that chunk into
Neo4j to see the connected people, organisations, places and hearing day — with mentions
clearly distinguished from claims/findings, and provenance (day, page, document, URL)
intact. Build the framework on **Zondo first**, then add Madlanga as a second adapter
over the same collection and graph.
