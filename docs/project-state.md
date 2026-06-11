# Project State — Commission Transcript Intelligence Platform

_Snapshot for planning. Last updated: 2026-06-11. Repo public at
`github.com/ChristoGH/za-corruption` (CI green on `main`). **M0 and M1 complete**: all 108
Madlanga transcripts parse → 15,022 speaker-aware chunks (idempotent, full page
provenance), and corpus statistics are generated — **18,485 pages, 82,739 turns, ~3.7M
words, 103 speaker labels** (46 tests). Role/word-share attribution is heuristic and
flagged PROVISIONAL (verify per-day witness, override via `--role-map`, before publishing).
Parsing details: `docs/parse-notes.md`. Next: M2 (embeddings + Qdrant)._

This document is a **factual snapshot** of what exists and works today, what is
blocked, and what is not yet built — enough to ground a comprehensive plan forward.
Everything under "Implemented & verified" was checked against the code and the live
registry on the date above. Everything under "Not yet implemented" is design intent
only (see `docs/` for the specifications).

---

## 1. What the project is

A reproducible **ingestion → retrieval** pipeline for South African commission-of-inquiry
transcripts. It discovers source documents (official PDFs where reachable; an
authoritative-flagged plaintext fallback otherwise), will extract and speaker-chunk the
text, store chunks in **Qdrant** (semantic search), and build an evidence-aware
knowledge graph in **Neo4j**.

- **First corpus:** Zondo / State Capture Commission.
- **Second corpus:** Madlanga Commission (Criminal Justice / "Criminality, Political
  Interference and Corruption in the Criminal Justice System").
- **Design goal:** a third commission is a *new collection*, not a redesign — a shared
  core with thin `CommissionAdapter`s.

**Governing principle:** _Mention ≠ Claim ≠ Finding ≠ Fact._ This is an **evidence
graph**, not a truth graph. Every extracted entity/claim/event must carry provenance
(commission, hearing day, document, URL, PDF SHA256, page, chunk ID, evidence text,
extraction method, confidence). Much of the corpus is allegation about named, often
private, individuals — the safety posture is non-negotiable.

---

## 2. Intended end-to-end architecture (status per stage)

```
official site → discover → download (+SHA256) → parse PDF → speaker-aware chunk
   → extract (entities/roles/events/claims) → Qdrant (chunks) + Neo4j (graph) → API → Web
```

| Stage | Status | Where |
|-------|--------|-------|
| Discover (structured) | ✅ Implemented & verified | `discovery/` |
| Download (+SHA256, validate) | ✅ Implemented & verified | `download/downloader.py` |
| Source registry (JSONL, upsert) | ✅ Implemented & verified | `download/registry.py` |
| Parse PDF (text + pages) | ✅ Implemented (Madlanga) | `parsing/pdf.py`, `clean.py` |
| Speaker-aware chunking | ✅ Implemented (15,022 chunks) | `parsing/turns.py`, `chunking.py`, `cli/parse_corpus.py` |
| Deterministic extraction (provenance backbone) | ✅ Implemented | `models/chunk_record.py` |
| Descriptive corpus statistics (Post #1) | ✅ Implemented | `analysis/stats.py`, `charts.py`, `cli/corpus_stats.py` |
| NLP extraction (spaCy entities/roles) | ❌ Not started | — |
| LLM-assisted extraction (Claude SDK, claims/events) | ❌ Not started | — |
| Embeddings → Qdrant | ❌ Not started | spec: `docs/qdrant-model.md` |
| Graph load → Neo4j | ❌ Not started | spec: `docs/neo4j-model.md`, `infra/neo4j/` (constraints not yet present) |
| FastAPI query layer (`apps/api`) | ❌ Not started (dir not scaffolded) | — |
| React/Vite frontend (`apps/web`) | ❌ Not started (dir not scaffolded) | — |
| Human review workflow | ❌ Not started | — |

**M1 feasibility verified (2026-06-11, PyMuPDF over all 108 downloaded transcripts):**
parsing is "Not started" as *code*, but the input is de-risked — **0 of 108 are scanned**
(born-digital, mean ~1,300 chars/page, **18,485 PDF pages**), speaker labels are
line-initial/uppercase/colon-terminated as assumed (~109k corpus-wide), and the main
cleaning hazard is ~37k interleaved line-number tokens (not OCR). See the M1 pre-step in
`docs/milestone-plan.md`.

**MVP success test (still the target):** search Qdrant for a topic → open a result →
jump from that chunk into Neo4j to see connected people/orgs/places/hearing day, with
mentions clearly distinguished from claims/findings.

---

## 3. Implemented & verified — the ingestion layer

A uv workspace (`requires-python >=3.12`) with a single member package
`packages/ingestion` (`commission_ingestion`). Runtime deps are deliberately minimal:
`requests`, `beautifulsoup4`, `pydantic` (+ optional `playwright` extra).

### Modules
- `models/source_record.py` — `SourceRecord` (pydantic, `schema_version 1.1`). Fields:
  commission, `authoritative`, `source_type`/`document_type`, `title`, `day_no`, `date`,
  `url`/`source_page_url`, `filename`/`content_type`/`size_bytes`, `discovered_at`,
  `downloaded`/`local_path`/`sha256`, `notes`.
- `discovery/base.py` — adapter base, resilient HTML fetch, bot-challenge detection,
  URL canonicalisation, optional Zondo session cookies.
- `discovery/madlanga.py` — embedded-JSON (`data-tabs` on `hearing.php`) + HTML anchor
  discovery; date/day-number extraction; **source-type classification** (transcript /
  report / statement / notice / media / supporting_document).
- `discovery/zondo.py` — official-site adapter (currently **blocked**, see §5).
- `discovery/zondo_bootstrap.py` — DSFSI plaintext fallback adapter (non-authoritative).
- `download/downloader.py` — streamed download, SHA256, PDF/`.txt`/empty validation,
  HTTP 404/410 classified as "missing at source", bot-protection (403/429/503) noted.
- `download/registry.py` — JSONL registry, upsert-by-URL (preserves download metadata),
  duplicate-SHA256 grouping.
- `cli/retrieve_sources.py` — `--commission {zondo,madlanga,both}`,
  `--discover-only`/`--download`, exit 1 only on real failures (missing ≠ failed).

### Tests
**33 passing** (`uv run pytest packages/ingestion/tests/`): madlanga discovery +
classification, zondo + zondo-bootstrap discovery, downloader (incl. 404→missing),
registry upsert, source-record model.

---

## 4. Corpus state (live registry, 325 records)

`data/sources/source_registry.jsonl` — 325 records; downloaded files in
`data/raw/<commission>/` (PDFs gitignored; only `.gitkeep` tracked).

### Madlanga — 181 records, 180 downloaded (~774 MB PDFs)
| source_type | count |
|-------------|-------|
| transcript | 109 |
| supporting_document | 34 |
| statement (WitnessStatement) | 31 |
| report | 2 |
| media | 4 |
| notice | 1 |

- **Transcripts: 109/109 have valid `day_no` and `date`. 0 invalid dates.**
- All 181 are `authoritative=true` (official site).
- 1 not downloaded: `MADLANGA_COMMISSION_RECORD_20250925.pdf` — permanent **HTTP 404**
  at source (classified "missing", not a failure).
- _Reconciled (2026-06-11):_ `data/raw/madlanga/` now holds 180 PDFs matching the 180
  tracked downloads. Two earlier orphans
  (`CJS_COMMISSION_CHAIR_OPENING_REMARKS__FINAL_17092025.pdf`,
  `_Unsigned_Ruling_Ex_Parte_Carrim_09.03.2026_.pdf`) — stale copies from an earlier
  `safe_filename` sanitization scheme, unreferenced by any record — have been deleted.

### Zondo — 144 records, 144 downloaded (~38 MB, all `.txt`)
- All 144 are **transcripts** but **`authoritative=false`** — these are **DSFSI
  plaintext bootstrap** files, *not* the official PDFs.
- This is the single biggest data-quality caveat: the Zondo corpus is currently a
  convenience mirror, not the authoritative source-of-record.

---

## 5. Blocked

- **Zondo official PDFs.** The official site sits behind **Cloudflare**; headless
  Playwright does not pass the challenge. `discovery/zondo.py` exists but cannot harvest
  authoritative PDFs without a manual browser session (an `INGEST_ZONDO_STORAGE_STATE`
  hook exists for a hand-captured session). Until resolved, Zondo provenance is
  bootstrap-grade.

---

## 6. Key design decisions already settled (don't relitigate)

From `docs/` (canonical model) and `docs/decisions/0004-...`. _The relationship names,
the collection, and the embedding model below were re-verified against `docs/ontology.md`,
`docs/neo4j-model.md`, and `docs/qdrant-model.md` on 2026-06-11._
1. **One shared Qdrant collection** `commission_transcripts` with a `commission` payload
   field — not a collection per commission. Embedding `BAAI/bge-small-en-v1.5`, 384-dim,
   cosine.
2. **`Document → Page → Chunk`** provenance spine in Neo4j — **but with two paths**:
   official PDFs use the full spine (`Document → Page → Chunk`); bootstrap plaintext
   attaches chunks **directly under `:Document` with `authoritative=false` and no `:Page`
   nodes**. The chunking/load stages must implement both. Banned: a direct
   `(:Document)-[:HAS_CHUNK]` shortcut on paged docs, and `APPEARS_IN` (use `MENTIONED_IN`
   for entities / `SPOKE_IN` for speakers).
3. **Procedural role ≠ real-world position** — `HAS_PROCEDURAL_ROLE → :Role` is distinct
   from `HELD_POSITION → :Position -[:AT_ORG]→ :Organisation`.
4. **Broad node labels + `HAS_TYPE`/`HAS_STATUS` edges** so one entity carries multiple
   classifications and the schema stays stable across commissions.
5. **Claims carry status/attribution/confidence**, `SUPPORTED_BY` a `:Chunk`, `STATED_BY`
   a `:Person`. **No fact edges** like `(:Person)-[:CORRUPTLY_INFLUENCED]->(:Contract)`.
6. **Progressive extraction in separate phases:** deterministic → spaCy → LLM (official
   **Anthropic Claude SDK** for structured JSON, behind a pluggable extractor interface)
   → human review. An LLM pass must never silently promote a claim to a fact.
7. **Build Zondo-first, reuse for Madlanga** (Madlanga is now further along on data, but
   the shared-core/adapter shape is the agreed architecture).

Intended stack (confirm versions before pinning): Python ≥3.12, PyMuPDF, spaCy
`en_core_web_trf`, sentence-transformers `BAAI/bge-small-en-v1.5` (384-dim, cosine),
qdrant-client, neo4j driver, FastAPI, React+Vite+TS. Services via docker-compose
(Qdrant + Neo4j 5.26 + APOC — the version/APOC pin is from `CLAUDE.md`/`README.md`, not
the canonical store docs, so confirm before pinning).

---

## 7. Gaps, risks & open questions to resolve in the plan

### Decisions the plan must make (these change *what* gets built)

1. **First-corpus decision — ✅ DECIDED: Madlanga-first.** ADR/build-plans originally said
   Zondo-first, but *today* Zondo is blocked and bootstrap-grade, while **Madlanga has 109
   authoritative PDFs with 109/109 valid `day_no`+`date`** (and verified born-digital — 0
   scanned) — a clean, paged corpus ready for parsing now. The shared-core/adapter
   architecture is unchanged. The pipeline is built on **Madlanga first** (real PDFs, full
   provenance spine); Zondo bootstrap stays a second/parallel collection, with Zondo-official
   revisited when the harvest is unblocked (M-Z). The build is sequenced this way in
   `docs/milestone-plan.md`.

2. **Zondo authoritative source (high).** Either solve the Cloudflare harvest (manual
   session capture, residential proxy, or official data request) or formally accept the
   DSFSI bootstrap as the Zondo source-of-record and label provenance accordingly. Note
   the canonical model already anticipates this: bootstrap text loads as `:Document`
   with `authoritative=false`, no `:Page` spine.

3. **License & publication posture (high — gates the public surface).** No license is
   chosen (README §24). More importantly, this system will expose **allegations about
   named, often private, individuals** via an API/web frontend. The legal/publication
   decision (what is shown, to whom, with what disclaimers, redaction, and takedown
   process) is a prerequisite for the `apps/api`/`apps/web` stages — not a footnote.
   Resolve before building any outward-facing surface.

4. **LLM extraction cost & scale envelope (high).** No order-of-magnitude exists yet.
   Inputs to size: ~774 MB Madlanga PDFs (+ full Zondo PDFs if unblocked) → an estimated
   tens of thousands of chunks to embed (cheap, local `bge-small`) and to run through the
   **Claude SDK structured-extraction pass** (the real cost driver). The plan needs a
   rough per-corpus token/$ estimate, a prompt-caching strategy, and a batching/cost cap
   before committing to a full-corpus extraction run.

### Build-readiness gaps (known work, no decision needed)

5. **No parsing/chunking yet.** The next build and the gate to everything downstream.
   Needs PyMuPDF text+page extraction, speaker-label detection, chunk IDs, per-page
   provenance — **two paths** (paged PDFs vs page-less bootstrap text, per §6.2).
6. **`apps/api` and `apps/web` not scaffolded.** CLAUDE.md mandates the full monorepo;
   only `packages/ingestion` exists.
7. **`infra` is skeletal.** `infra/neo4j/constraints.cypher` is specified (run before
   ingestion) but absent; only `infra/docker/ingestion/Dockerfile` exists. No
   `docker-compose` services for Qdrant/Neo4j yet.
8. **LLM extraction safety design.** Beyond cost: confidence/method metadata enforcement,
   deterministic-checks-first, and never silently promoting a claim to a fact.

### Lower-risk cleanups

9. **Classification heuristics are filename-driven.** Madlanga source-typing keys on
   filenames; robust but heuristic. A second commission (or a relabel) may need review.
10. **Registry merge quirk (low).** `upsert` keeps `record.date or existing.date`; a
    corrected parse returning `None` can't override a stale-but-valid stored date.
11. **Orphan files — resolved.** The 2 stale-sanitization PDFs in `data/raw/madlanga`
    have been deleted (see §4); disk now reconciles 180/180. Optional follow-up: add a
    registry-vs-disk reconcile check to the CLI to catch future drift automatically.

---

## 8. Suggested shape for the plan forward (discussion starter, not decided)

Dependencies, not a strict line. **Critical path:** 0 → 1 → (2 ∥ 3) → 4 → 5 → 6.
After chunking (step 1), the **Qdrant path (2)** and the **Neo4j path (3)** are largely
independent and can proceed in parallel. The web frontend (5) and human-review layer (6)
are gated by the license/publication decision (§7.3), not by the data pipeline.

| # | Stage | Depends on | Done when (acceptance) |
|---|-------|-----------|------------------------|
| 0 | **Decide first corpus + Zondo source** (§7.1–7.2); stand up `docker-compose` (Qdrant+Neo4j) and `infra/neo4j/constraints.cypher` | — | Chosen corpus agreed; both stores reachable locally; constraints applied |
| 1 | **Parse + speaker-aware chunk** (two paths: paged PDF / page-less bootstrap) | 0 | Every downloaded doc → chunks with `chunk_id`, page provenance (PDFs), speaker label, SHA256 lineage; deterministic, re-runnable |
| 2 | **Embed + Qdrant load** into `commission_transcripts` | 1 | Semantic search returns relevant chunks with full payload (commission, day, page, chunk_id) |
| 3 | **Deterministic + spaCy graph load** into Neo4j (spine + Person/Org/Place **mentions only**) | 1 | `Document→Page→Chunk` populated; `MENTIONED_IN` edges; **no claims/facts** |
| 4 | **LLM-assisted extraction** (Claude SDK) — claims/events/roles/positions | 3 (+cost plan §7.4) | Every write carries `confidence`+`extraction_method`; claims modelled as `:Claim … SUPPORTED_BY/STATED_BY`, never fact edges |
| 5 | **API (`apps/api`)** over both stores, then **Web (`apps/web`)** | 2,4 (+license §7.3) | MVP success-test flow works end-to-end; mentions visibly distinct from claims/findings |
| 6 | **Human-review layer** — alias/dup resolution, high-risk claim confirmation | 4 | Reviewers can confirm/merge/flag; decisions persisted with provenance |

**Earliest demonstrable slice:** corpus → step 1 → step 2 gives a working semantic search
over real testimony without touching Neo4j or the LLM — a cheap, high-signal milestone.

---

_Source-of-truth specs: `docs/ontology.md`, `docs/qdrant-model.md`, `docs/neo4j-model.md`,
`docs/build-plan-shared-core.md`, `docs/build-plan-{zondo,madlanga}.md`,
`docs/decisions/0004-shared-core-commission-adapters.md`. Precedence: canonical model →
build plans → `README.md` → other root docs._
