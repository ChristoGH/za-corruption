# CLAUDE.md

Guidance for Claude Code (and other coding agents) working in this repository.

## What this repo is

The **Commission Transcript Intelligence Platform** — a reproducible ingestion and
retrieval pipeline for South African commission-of-inquiry transcripts. It downloads
official transcript PDFs, extracts and speaker-chunks the text, stores chunks in
**Qdrant** for semantic search, and builds an evidence-aware knowledge graph in
**Neo4j**.

First corpus: the **Zondo / State Capture Commission**. Second: the **Madlanga
Commission**. The system is designed so a third commission is a new collection, not a
redesign.

## Status

**Implemented (verified):** source retrieval in `packages/ingestion/` — discover,
registry (`data/sources/source_registry.jsonl`), download to `data/raw/`. Madlanga
transcript PDFs (~108) via embedded JSON on `hearing.php`. Zondo bootstrap via DSFSI
plaintext (`authoritative=false`). uv workspace + retrieval Docker image. See
`docs/getting-started.md`.

**Blocked:** Zondo official PDFs (Cloudflare; headless Playwright does not pass).

**Not yet implemented:** parsing, chunking, Qdrant, Neo4j, FastAPI, React, LLM extraction.

Do not claim a later pipeline stage works until the code exists and you have verified it.

## Source-of-truth documents

Read these before designing or implementing. They are the specification; this file is
the summary.

**Canonical model (authoritative — read first):**
- `docs/ontology.md` — canonical nodes, relationships, role-vs-position, claim/event
  layer, commission overlays, banned relationships. Supersedes the ontology sections of
  `README.md` and `taxonomy-ontologies.md` where they differ.
- `docs/qdrant-model.md` — the single shared `commission_transcripts` collection and its
  payload schema.
- `docs/neo4j-model.md` — the `Document → Page → Chunk` provenance spine, settled
  relationship naming, constraints, queries.

**Build plans (shared core + commission adapters):**
- `docs/build-plan-shared-core.md` — the shared ingestion pipeline, the
  `CommissionAdapter` interface, `SourceRecord`, services, dependencies. Madlanga and
  Zondo are adapters over this, not separate implementations.
- `docs/build-plan-zondo.md` — Zondo adapter deltas only. **Recommended first build target.**
- `docs/build-plan-madlanga.md` — Madlanga adapter deltas only.
- `docs/decisions/0004-shared-core-commission-adapters.md` — the reconciliation decisions
  (one Qdrant collection, structured discovery, Page spine, relationship naming,
  shared role/position, Claude SDK extraction).

**Background (superseded where they conflict with the canonical model):**
- `docs/vision.md` — the full original project spec (goals, architecture, roadmap, safety
  notes), preserved as narrative overview; defer to `docs/` for ontology/store/relationship
  detail. (The root `README.md` is now the concise public front door, not the spec.)
- `directory-structure.md` — the intended monorepo layout. **Decision: scaffold the full
  monorepo** — `apps/api` (FastAPI), `apps/web` (React+Vite),
  `packages/{ingestion,ontology,shared}` — not the doc's smaller "minimal starting
  version". Empty shells are acceptable until ingestion + search land.
- `taxonomy-ontologies.md` — original shared-ontology-vs-per-commission discussion and the
  controlled vocabularies (now formalised in `docs/ontology.md`).

When the documents disagree, precedence is: `docs/` canonical model → `docs/` build plans
→ `docs/vision.md` (original spec) → other root docs.

## The one principle that governs the whole design

**Mention ≠ Claim ≠ Finding ≠ Fact.** This is an *evidence graph*, not a *truth graph*.

- A person being named in a transcript is a `MENTIONED_IN` edge — nothing more.
- Something a witness said is a `(:Claim {status, attribution, confidence})`
  `SUPPORTED_BY` a `(:Chunk)`, `STATED_BY` a `(:Person)` — **not** a fact edge.
- A commission conclusion is a `(:Finding)`, sourced to a report.
- A later court outcome is a separate status, not an overwrite of the claim.

Do **not** model assertions like `(:Person)-[:CORRUPTLY_INFLUENCED]->(:Contract)`.
Every extracted entity, claim, and event must carry provenance: commission, hearing
day, document, source URL, PDF SHA256, page number, chunk ID, evidence text,
extraction method, and confidence. This matters legally — much of this content is
allegation about named individuals.

## Architecture (intended)

```
official site → discover → download (+SHA256) → parse PDF → speaker-aware chunk
   → extract (entities/roles/events/claims) → Qdrant (chunks) + Neo4j (graph)
```

- **Qdrant** answers "where is testimony about X" (semantic).
- **Neo4j** answers "who/what/where co-occurs, in which hearing, with what role" (graph).
- The **API queries** both stores; it must **not own ingestion logic**. Ingestion lives
  in `packages/ingestion`, the API in `apps/api`, the frontend in `apps/web`.

Intended stack (from the plans — confirm before pinning versions): Python ≥3.11,
PyMuPDF, spaCy `en_core_web_trf`, sentence-transformers (`BAAI/bge-small-en-v1.5`,
384-dim, cosine), qdrant-client, neo4j driver, requests/BeautifulSoup/Playwright for
discovery, pydantic. Frontend: React + Vite + TypeScript. Services run via
`docker-compose` (Qdrant + Neo4j 5.26 with APOC).

## Extraction is progressive — keep the phases separate

1. **Deterministic**: metadata, hearing day, date, pages, speaker labels, chunk IDs,
   hashes. (Do this first; it's the provenance backbone.)
2. **NLP**: spaCy entities (Person/Org/Place), basic role inference from speaker labels.
3. **LLM-assisted**: events, claims, procedural roles, real-world positions,
   relationships — always written with `confidence` and `extraction_method`. **Decision:
   use the official Anthropic Claude SDK directly** for this structured-JSON pass (with
   prompt caching); keep it behind a pluggable extractor interface so the deterministic
   and spaCy phases don't depend on it.
4. **Human review**: alias/duplicate resolution, confirmation of high-risk claims.

Never let an LLM pass silently promote a claim to a fact, or invent a field a witness
did not state. Prefer deterministic checks over LLM arithmetic/parsing where possible.

## Modelling conventions

- Procedural role (`HAS_PROCEDURAL_ROLE` → `:Role`) is **distinct** from real-world
  position (`HELD_POSITION` → `:Position` `-[:AT_ORG]->` `:Organisation`). Don't collapse them.
- Keep broad node labels (`:Person`, `:Organisation`, `:Document`, `:Event`) and attach
  taxonomy via `HAS_TYPE`/`HAS_STATUS` edges, so one entity can carry multiple
  classifications and the schema stays stable across commissions.
- Run `infra/neo4j/constraints.cypher` (uniqueness on commission/document SHA/chunk/
  person/etc.) before any ingestion.

## Recommended build order

Per the plans, build the framework on **Zondo first** (mature, consistent, rich), then
reuse it for Madlanga as a second collection.

MVP success test: *search Qdrant for a topic → open a result → jump from that chunk
into Neo4j to see the connected people, organisations, places, and hearing day — with
mentions clearly distinguished from claims/findings.*

## Working agreements

These supplement, and never override, the always-on `.cursor` rules:
`.cursor/rules/agent-operating-rules.mdc` and
`.cursor/rules/karpathy-behavioral-guidelines.mdc` (understand before changing, surgical
diffs, simplicity first, verify honestly, don't invent context, dependency discipline,
the `Changed / Verified / Assumptions / Notes` final-report format). Read them.

Repo-specific notes:
- **`.cursor/rules/30-medvoice-project-rules.mdc` belongs to a different project**
  (med-voice). It is scoped off (`alwaysApply: false`, medvoice glob) and does **not**
  apply here. It should probably be removed; do not treat its POPIA/medical rules as
  relevant to this repo.
- Treat downloaded PDFs and the official sites as authoritative sources to preserve, not
  to mutate. Don't reformat or "clean" original evidence text in a way that loses
  provenance.
- This corpus contains serious allegations about named, often private, individuals.
  Keep the safety posture from `docs/vision.md` §21 (and `DISCLAIMER.md`): preserve source
  evidence, never present testimony as proven fact, keep confidence + method metadata,
  support human review.
- License: **Apache-2.0** for the code (`LICENSE`/`NOTICE`); the underlying records are
  official public records (not relicensed) and derived artifacts are CC BY 4.0 — see
  `DISCLAIMER.md`.
