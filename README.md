# Commission Transcript Intelligence Platform

[![CI](https://github.com/ChristoGH/za-corruption/actions/workflows/ci.yml/badge.svg)](https://github.com/ChristoGH/za-corruption/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC_BY_4.0-lightgrey.svg)](DISCLAIMER.md)

> Make the public record of South Africa's commissions of inquiry **searchable,
> mappable, and checkable** — without ever presenting testimony as proven fact.

A reproducible pipeline that downloads official commission-of-inquiry transcripts,
extracts and speaker-chunks the text, stores passages in **Qdrant** for semantic search,
and builds an evidence-aware knowledge graph in **Neo4j**. First corpus: the **Madlanga
Commission**; designed so each additional commission (Zondo and beyond) is a new
collection, not a redesign.

---

## The principle: Mention ≠ Claim ≠ Finding ≠ Fact

This is an **evidence graph, not a truth graph**, and the data model enforces the
difference:

- A person **named** in a transcript is a *mention* — nothing more.
- Something a witness **said** is a **claim** — with attribution, status, and confidence,
  supported by the exact source passage — **not** a statement of fact.
- A commission **finding** is sourced to a report; a later **court outcome** is a separate
  status, not an overwrite of the claim.

Every extracted entity, claim, and event carries provenance: commission, hearing day,
document, source URL, file hash, page number, source passage, extraction method, and
confidence. Much of this corpus is **allegation about named, often private, individuals** —
see [DISCLAIMER.md](DISCLAIMER.md).

---

## Status

| Stage | Status |
|-------|--------|
| Source discovery (structured) | ✅ Implemented |
| Download (+SHA256, validation) | ✅ Implemented |
| Source registry (JSONL, idempotent upsert) | ✅ Implemented |
| Parse PDF → speaker-aware chunks | ✅ Implemented (Madlanga: 14,783 active chunks) |
| Descriptive corpus statistics + integrity pass (Post #1) | ✅ Implemented (blocking duplicate/reconciliation checks) |
| Embeddings → Qdrant (semantic search CLI) | ✅ Implemented (14,783 points, bge-small-en-v1.5) |
| Graph load → Neo4j (spine + mentions) | ✅ Implemented |
| LLM-assisted claim extraction (Claude SDK, Haiku) | ✅ Implemented (49,068 claims; ~46,546 loaded, ADR 0007) |
| API + web (search → chunk → graph → claim) | ✅ Implemented (read-only FastAPI + React; see Quick start) |

`168` passing tests across ingestion, parsing, statistics, integrity checks, charts, the
vector store, and the API. See [docs/project-state.md](docs/project-state.md)
for a verified, detailed snapshot.

---

## The corpus today

Discovered and downloaded into a single source registry (URLs + hashes tracked in git;
the documents themselves are not):

**Madlanga Commission** — 181 records (109 transcripts, plus statements, reports, notices,
media, and supporting documents). Transcripts span **107 hearing days** (the Commission
has sat to **Day 110**); Days 4, 14, and 104 are not in the public record and Day 6 was
unreachable at source. All from the official site. After a content-containment integrity
pass found two duplicate publications of the same sittings (recorded as `superseded_by`
in the registry, files retained), the active corpus is: **106 transcript documents
across 106 hearing days → 18,192 pages → 81,712 speaker turns → 14,783 chunks**, ~3.65M
words, 103 distinct speaker labels — every chunk traceable to its PDF page.

**Zondo / State Capture Commission** — 144 transcripts via a **non-authoritative**
plaintext bootstrap (DSFSI); the official PDFs sit behind Cloudflare and are not yet
harvested. Flagged `authoritative=false` everywhere it surfaces.

_(Numbers are generated from the registry, not typed by hand; gaps are stated, not hidden.)_

---

## Architecture

```
official site → discover → download (+SHA256) → parse PDF → speaker-aware chunk
   → extract (entities / roles / events / claims) → Qdrant (chunks) + Neo4j (graph) → API → Web
```

- **Qdrant** answers *"where is testimony about X?"* (semantic).
- **Neo4j** answers *"who/what/where co-occurs, in which hearing, with what role?"* (graph).
- The API queries both stores; **ingestion logic lives in `packages/ingestion`, not the API.**

---

## Quick start — run the search + evidence-graph app

Brings the read-only web surface up from a clean checkout: search testimony → open a
result → see its mentions and claims → drill into a claim's provenance.

**Prerequisites:** [uv](https://docs.astral.sh/uv/) (Python ≥3.12), Docker + Docker Compose,
and Node.js + npm (for the web app). Create a repo-root `.env` (git-ignored) with at least:

```bash
NEO4J_PASSWORD=changeme          # must match the value docker-compose starts Neo4j with
# ANTHROPIC_API_KEY=sk-...        # only needed to run claim extraction yourself
```

```bash
# 1. Install all workspace packages + extras (this pulls the embedder: sentence-transformers/torch).
make install

# 2. Start the stores and apply Neo4j constraints (one-time).
make stores-up                   # Qdrant :6333 + Neo4j :7687/:7474 via docker-compose
make neo4j-constraints

# 3. Populate the stores (they start EMPTY — this is the step that makes the app show data).
make load-qdrant                 # embed + load chunks (COMMISSION=madlanga by default)
uv run build-graph --commission madlanga --with-claims   # spine + mentions + the :Claim layer

# 4. Run the API (leave it running).
make api-dev                     # http://localhost:8000  (GET /health should report both stores up)

# 5. Run the web app (new terminal).
make web-install                 # once, installs node deps
make web-dev                     # http://localhost:5173
```

Then search `disbanding of task team`, click a result, and confirm mentions (leads) render
separately from claims (attributed testimony).

**Where the data comes from.** Steps 3+ assume the corpus is already parsed and extracted
locally. If you have a Neo4j snapshot, restore it instead of rebuilding:
`make restore FROM=backups/<timestamp>` (then still run `make load-qdrant`). A cold clone
with no local corpus must first run the ingestion pipeline (discover → download → parse →
extract) — see [docs/getting-started.md](docs/getting-started.md); claim extraction needs an
`ANTHROPIC_API_KEY`. `build-graph` without `--with-claims` loads mentions only.

**Notes.** `/search` embeds the query at request time, so the vector extra must be present —
`make install` handles it; installing the API alone will 500 on search. The first search
downloads the BGE model (~130 MB) once. `make test` runs the ingestion + API suites with no
live stores (DI-injected fakes).

Source-retrieval only, without the app: see [docs/getting-started.md](docs/getting-started.md).

---

## Roadmap

Madlanga-first; each milestone ends with a public, demonstrable artifact.

- [x] **M0 — Public-repo readiness:** Apache-2.0, secrets audit, this README, CI green.
- [x] **M1 — Parse + speaker-aware chunking + descriptive statistics** ✅ (now 106 active
      transcripts → 14,783 chunks; stats: 18,192 pages, 81,712 turns, ~3.65M words;
      Post #1 charts regenerate via `make post-assets` into `assets/post1/`).
- [x] **M2 — Embeddings + Qdrant** + local infra (docker-compose) ✅ (all 14,783 active
      chunks embedded and searchable: `search-corpus "query" [--day N] [--speaker LABEL]`;
      a blocking integrity pass caught two duplicate publications — both excluded via
      human-reviewed `superseded_by` registry records and purged from the store).
- [x] **M3 — Mentions-only graph in Neo4j** + a co-occurrence network render ✅.
- [x] **M4 — Claims layer (Claude SDK)** ✅ (Haiku full-corpus extraction; canary-signed;
      raw-speaker fallback per ADR 0007). Human-review gate (M6) still to build before
      publishing system-originated findings.
- [x] **M5 — Thin public surface** ✅ (read-only FastAPI + React; search → chunk graph →
      claim provenance, mentions kept distinct from claims). See **Quick start** above.

**MVP success test:** search Qdrant for a topic → open a result → jump from that chunk into
Neo4j to see the connected people, organisations, places, and hearing day — with mentions
clearly distinguished from claims and findings.

---

## Documentation

| Doc | What it covers |
|-----|----------------|
| [docs/project-state.md](docs/project-state.md) | Verified current state and the plan-forward gaps |
| [docs/ontology.md](docs/ontology.md) | Canonical nodes, relationships, claim/event layer |
| [docs/qdrant-model.md](docs/qdrant-model.md) | The shared `commission_transcripts` collection + payload |
| [docs/neo4j-model.md](docs/neo4j-model.md) | `Document → Page → Chunk` provenance spine + constraints |
| [docs/build-plan-shared-core.md](docs/build-plan-shared-core.md) | Shared ingestion core + `CommissionAdapter` interface |
| [docs/getting-started.md](docs/getting-started.md) | Setup and CLI usage |
| [docs/vision.md](docs/vision.md) | The original full project specification (narrative, historical) |

---

## Safety & ethics

This project processes serious allegations about named, often private, individuals. It
preserves source evidence, never presents testimony as proven fact, keeps confidence and
extraction-method metadata, and supports human review of high-risk claims. Read
[DISCLAIMER.md](DISCLAIMER.md) before using or citing anything here.

It is **not affiliated with, endorsed by, or operated by** any commission of inquiry or
the South African government.

---

## License

- **Code:** [Apache-2.0](LICENSE) (with explicit patent grant — see [NOTICE](NOTICE)).
- **Underlying records:** official public records, **not** relicensed by this project —
  obtain them from the official sources.
- **Derived artifacts** (chunk metadata, statistics, graph data): CC BY 4.0 with
  attribution to the official source. See [DISCLAIMER.md](DISCLAIMER.md).
