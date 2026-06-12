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
| Parse PDF → speaker-aware chunks | ✅ Implemented (Madlanga: 15,022 chunks) |
| Descriptive corpus statistics (Post #1) | ✅ Implemented |
| Embeddings → Qdrant (semantic search CLI) | ✅ Implemented (15,022 points, bge-small-en-v1.5) |
| Graph load → Neo4j | ⬜ Planned (constraints + docker service ready) |
| LLM-assisted claim/event extraction (Claude SDK) | ⬜ Planned |
| API + web (search → chunk → graph) | ⬜ Planned |

`57` passing tests across ingestion, parsing, statistics, and the vector store. See [docs/project-state.md](docs/project-state.md)
for a verified, detailed snapshot.

---

## The corpus today

Discovered and downloaded into a single source registry (URLs + hashes tracked in git;
the documents themselves are not):

**Madlanga Commission** — 181 records (109 transcripts, plus statements, reports, notices,
media, and supporting documents). Transcripts span **107 hearing days** (the Commission
has sat to **Day 110**); Days 4, 14, and 104 are not in the public record and Day 6 was
unreachable at source. All from the official site. Parsed (M1): **108 transcript documents
across 106 hearing days → 18,485 pages → 82,739 speaker turns → 15,022 chunks**, ~3.7M
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

## Quick start

Requires Python ≥3.12 and [uv](https://docs.astral.sh/uv/). Source retrieval works today;
later stages are in progress.

```bash
uv sync --all-packages --all-extras

# Discover sources into data/sources/source_registry.jsonl
uv run retrieve-sources --commission madlanga --discover-only
uv run retrieve-sources --commission zondo --discover-only      # DSFSI bootstrap (default)

# Discover, then download into data/raw/<commission>/
uv run retrieve-sources --commission both --download

make test
```

Full commands: [docs/getting-started.md](docs/getting-started.md).

---

## Roadmap

Madlanga-first; each milestone ends with a public, demonstrable artifact.

- [x] **M0 — Public-repo readiness:** Apache-2.0, secrets audit, this README, CI green.
- [x] **M1 — Parse + speaker-aware chunking + descriptive statistics** ✅ (108 transcripts
      → 15,022 chunks; stats: 18,485 pages, 82,739 turns, ~3.7M words; Post #1 charts).
- [x] **M2 — Embeddings + Qdrant** + local infra (docker-compose) ✅ (all 15,022 chunks
      embedded and searchable: `search-corpus "query" [--day N] [--speaker LABEL]`).
- [ ] **M3 — Mentions-only graph in Neo4j** + a co-occurrence network render.
- [ ] **M4 — Claims layer (Claude SDK)** behind a human-review gate.
- [ ] **M5 — Thin public surface** (FastAPI + a read-only web page) for the end-to-end flow.

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
