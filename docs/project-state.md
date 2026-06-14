# Project State — Commission Transcript Intelligence Platform

_Snapshot for planning. Last updated: 2026-06-13. Repo public at
`github.com/ChristoGH/za-corruption` (CI green on `main`). **M0, M1, M2, and M3 complete**,
plus a blocking corpus-integrity pass that found and excluded **two duplicate
publications** of the same sittings (the day-80 "_Full" partial and a "DAY 15"-headed
republication of day 16 — human-reviewed `superseded_by` registry records, files
retained). Active corpus: **106 transcript docs / 106 hearing days, 18,192 pages,
81,712 turns, ~3.65M words, 103 speaker labels → 14,783 chunks** in Qdrant at exact
parity (101 tests). Role/word-share attribution is heuristic and
flagged PROVISIONAL (verify per-day witness, override via `--role-map`, before publishing).
Parsing details: `docs/parse-notes.md`. Post assets: `make post-assets` → `assets/post1/`.
Extraction infrastructure built; Gate 2 cross-model eval complete (40-chunk stratified
sample, seed 17) — model selection and budget approval awaiting human decision before
full-corpus extraction run. M3 graph layer: `build-graph` CLI and full Neo4j spine +
SPOKE_IN + MENTIONED_IN pipeline implemented and tested (25 graph tests); live load
requires `docker compose up` and `make neo4j-constraints` first. Canned queries:
`docs/queries.md`. Next: M4 (LLM claims layer — gated on §7.4 model decision)._

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
| Speaker-aware chunking | ✅ Implemented (14,783 active chunks; 15,022 on disk incl. 2 superseded docs) | `parsing/turns.py`, `chunking.py`, `cli/parse_corpus.py` |
| Deterministic extraction (provenance backbone) | ✅ Implemented | `models/chunk_record.py` |
| Descriptive corpus statistics (Post #1) | ✅ Implemented | `analysis/stats.py`, `charts.py`, `cli/corpus_stats.py` |
| Embeddings → Qdrant | ✅ Implemented & verified (M2 complete) | `vector/embedder.py`, `vector/qdrant_store.py`, `cli/load_qdrant.py`, `cli/search.py` |
| LLM extraction infrastructure | ✅ Infrastructure implemented; Gate 2 eval complete; **awaiting model-selection & budget approval** | `extraction/`, `eval/`, `resolution/`, `cli/extract_corpus.py`, `cli/cross_model_eval.py` |
| spaCy NER detection | ✅ Implemented (M3); lazy-load behind `spacy` extra; `MentionDetector` protocol for test injection | `graph/mentions.py` |
| Graph load → Neo4j — spine + mentions | ✅ Implemented & tested (M3); idempotent MERGE; two provenance paths; SPOKE_IN + MENTIONED_IN | `graph/neo4j_store.py`, `cli/build_graph.py`; canned queries: `docs/queries.md` |
| NLP extraction (spaCy entities/roles into Neo4j) | ✅ Implemented (M3) — spaCy detects Person/Org/Place, resolved via canonical store | `graph/mentions.py`, `graph/neo4j_store.py` |
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
`requests`, `beautifulsoup4`, `pydantic` (+ optional extras: `playwright`, `stats`,
`vector`, `extract`).

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
- `parsing/pdf.py`, `parsing/clean.py` — PyMuPDF text + page extraction; line-number
  token removal, furniture stripping, speaker-label normalisation.
- `parsing/turns.py`, `parsing/chunking.py` — speaker-aware turn segmentation;
  chunk packing (small turns merged, oversized turns split on sentence boundaries).
- `cli/parse_corpus.py` — per-document parse → chunk JSONL files under
  `data/processed/`; re-runnable, skips already-parsed.
- `analysis/stats.py`, `analysis/charts.py`, `analysis/integrity.py` — corpus
  statistics, Post #1 chart generation, duplicate-publication detection.
- `cli/corpus_stats.py` — `corpus-stats` CLI; outputs `data/processed/stats/`.
- `vector/embedder.py` — `BAAI/bge-small-en-v1.5` (384-dim, cosine) via
  sentence-transformers; batched with progress bar.
- `vector/qdrant_store.py` — `QdrantStore` wrapping `qdrant-client`; stable
  `uuid5(chunk_id)` point IDs, full payload schema per `docs/qdrant-model.md`,
  superseded-doc purge, idempotent upsert, day/speaker filter search.
- `cli/load_qdrant.py` — `load-qdrant` CLI; loads `commission_transcripts` collection,
  skips fully-loaded docs.
- `cli/search.py` — `search-corpus` CLI; semantic search with optional day/speaker
  filters.
- `extraction/schema.py` — `ChunkExtraction` schema: `entities` (person/org/role/
  place/acronym, surface form verbatim), `mentions` (verbatim quote spans),
  `claims` (reported-speech only: speaker, subject_refs, predicate, object_refs,
  quote, certainty). `PROMPT_VERSION = "extract_v1"`. `find_quote()` for deterministic
  character-offset recovery (exact match → whitespace-tolerant fallback; returns None
  rather than guessing).
- `extraction/extractor.py` — `LLMClient` protocol + `AnthropicLLMClient` (SDK
  imported lazily behind `extract` extra); `extract_chunk()`: caching, strict Pydantic
  parse, one repair retry, dead-letter on refusal or second parse failure. Cost
  accounting for Opus/Sonnet/Haiku with cache read/write factors.
- `extraction/cache.py` — content-addressed JSON cache keyed on
  `(chunk_id, prompt_version, model)`; `spend.jsonl` cost log; dead-letter store.
  **Populated:** 672 Opus + 40 Haiku + 1 Sonnet chunk extractions cached (~US$15.40
  total spend logged across eval and sampling runs).
- `extraction/prompts/extract_v1.md` — system prompt: neutral reported-speech framing
  (predicates always "stated/testified/alleged that …"), strictly verbatim quotes, no
  `status` field (graph writer always writes `status="alleged"`).
- `eval/sample.py` — stratified sampler: 5 strata × 8 chunks = 40 (ambiguous_surname,
  ocr_variant, high_acronym, allegation_dense, control); seed-frozen at 17.
- `eval/compare.py` — resolution-aware entity/claim diff: entity F1 measured after
  canonical resolution (TP/FP/FN on canonical IDs, not raw strings); claim soft-match
  on subject canonical-ID overlap + predicate similarity (threshold 0.45); fragmentation
  counted separately.
- `eval/framing_judge.py` — Opus judge classifying each extracted claim as
  `neutral_reported` / `asserted_as_fact` / `ambiguous` (the defamation-safety axis).
- `eval/report.py` — writes `eval/artifacts/metrics.json`,
  `eval/artifacts/gate2_model_review.md`, `eval/artifacts/hardcase_appendix.md`.
- `resolution/canonical.py` — `CanonicalStore`: alias index + title-stripped bare index,
  both scoped by entity-type group so the same surface can resolve differently by type
  (e.g. "CHAIRPERSON" → the person or the procedural role). Surname-only aliases
  forbidden (four distinct Khumalos in this corpus alone).
- `resolution/seed_entities.yaml` — 268-line human-owned canonical entity seed for the
  Madlanga corpus (bench, counsel, witnesses, organisations, places); resolver matches
  against this, never adds to it.
- `graph/mentions.py` — `DetectedMention` + `MentionDetector` protocol +
  `SpacyDetector` (lazy `en_core_web_trf` import behind `spacy` extra; maps spaCy
  PERSON/ORG/GPE/LOC/FAC labels → person/org/place; deduplicates by surface+type).
- `graph/neo4j_store.py` — `Neo4jStore`: driver wrapper (accepts injected driver for
  tests); `write_spine()` (paged vs bootstrap path, UNWIND batched, MERGE only);
  `write_speaker_edges()` (SPOKE_IN); `write_mention_edges()` (MENTIONED_IN per type,
  per-chunk dedup on canonical entity ID); `count_chunks()` for idempotency. Banned
  relationships enforced by construction: no `APPEARS_IN`, no direct paged
  `Document-[:HAS_CHUNK]->Chunk`, no `:Claim` writes.
- `graph/__init__.py` — module marker (no longer a stub).
- `cli/build_graph.py` — `build-graph` CLI: `--commission {zondo,madlanga,both}`,
  `--all`, `--dry-run` (counts only, no writes/NER), `--no-ner` (spine + SPOKE_IN
  only), `--force`, `--limit N`. Loads canonical store from `seed_entities.yaml`.
- `cli/extract_corpus.py` — `extract-corpus` CLI: `--estimate-only` (zero API calls),
  `--budget-usd` hard cap with clean checkpoint, `--days`/`--all`, `--batch` flag.
- `cli/cross_model_eval.py` — `cross-model-eval` CLI: runs Gate 2 evaluation against
  the frozen stratified sample; cache-aware (re-runs cost $0 if arms already cached).

### Tests
**101 passing** (`uv run pytest packages/ingestion/tests/`): madlanga discovery +
classification, zondo + zondo-bootstrap discovery, downloader (incl. 404→missing),
registry upsert, source-record model, PDF parsing + chunking, corpus statistics,
corpus integrity (duplicate detection, reconciliation), Qdrant store (idempotency,
payload, superseded-doc purge, search filters), charts, cross-model eval (sampler,
compare metrics, framing flags, resolution), **graph layer** (hearing_key/page_key,
paged and bootstrap spine paths, SPOKE_IN, MENTIONED_IN, banned-relationship
enforcement, idempotency-via-MERGE, zero `:Claim` nodes).

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
   The extraction schema enforces this structurally: there is no `status` field — the
   graph writer always writes `status="alleged"`.
6. **Progressive extraction in separate phases:** deterministic → spaCy → LLM (official
   **Anthropic Claude SDK** for structured JSON, behind a pluggable extractor interface)
   → human review. An LLM pass must never silently promote a claim to a fact.
7. **Build Zondo-first, reuse for Madlanga** (Madlanga is now further along on data, but
   the shared-core/adapter shape is the agreed architecture).
8. **Canonical entity resolution is human-owned.** The resolver (`resolution/canonical.py`)
   only matches against `seed_entities.yaml` — it never merges autonomously. Surname-only
   aliases are forbidden (multiple Khumalos). A proposed merge must be human-approved by
   adding the alias to the YAML and re-running.

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

4. **LLM extraction model & budget — Gate 2 complete, human decision required (high).**
   Cross-model eval run on 40-chunk stratified sample (seed 17, strata: ambiguous_surname,
   ocr_variant, high_acronym, allegation_dense, control). Results locked in
   `eval/artifacts/gate2_model_review.md` and `metrics.json`:

   | model | entity F1 (hard) | asserted-as-fact rate | $/chunk | full corpus (batch) |
   |-------|------------------|-----------------------|---------|---------------------|
   | claude-haiku-4-5 | 0.660 | **4.3%** | $0.0055 | **$40** |
   | claude-sonnet-4-6 | 0.696 | 10.8% | $0.0140 | $104 |
   | claude-opus-4-8 (reference) | — | 12.7% | $0.0381 | $282 |

   **Asserted-as-fact rate is the defamation-critical axis** — one framing slip outweighs
   a dozen entity misses. Haiku has the lowest rate and lowest cost; Sonnet has slightly
   better entity recall. See `eval/artifacts/hardcase_appendix.md` before deciding.
   **Action required:** approve a model and budget cap to unlock `extract-corpus --all`.

### Build-readiness gaps (known work, no decision needed)

5. **`apps/api` and `apps/web` not scaffolded.** CLAUDE.md mandates the full monorepo;
   only `packages/ingestion` exists.

6. **`infra` is skeletal for Docker.** `infra/neo4j/constraints.cypher` exists (29 lines);
   `docker-compose.yml` defines Qdrant + Neo4j 5.26 services. `make stores-up` brings
   both up; `make neo4j-constraints` applies constraints. `infra/docker/ingestion/`
   exists but no compose file for running the full ingestion pipeline in containers.

7. **Live Neo4j load not yet smoke-tested end-to-end.** `build-graph` is implemented
   and unit-tested with a `FakeDriver`. A full live run against a running Neo4j instance
   (e.g. `make stores-up && make neo4j-constraints && build-graph --limit 5`) should be
   done before treating M3 as fully accepted.

8. **LLM extraction safety design.** Beyond cost: confidence/method metadata enforcement,
   deterministic-checks-first, and never silently promoting a claim to a fact. The
   extraction schema enforces reported-speech framing and the graph writer enforces
   `status="alleged"`, but the full safety design (human review gate for high-risk claims,
   alias-resolution review queue) is not yet implemented.

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

| # | Stage | Depends on | Status | Done when (acceptance) |
|---|-------|-----------|--------|------------------------|
| 0 | **Decide first corpus + Zondo source** (§7.1–7.2); stand up `docker-compose` (Qdrant+Neo4j) and `infra/neo4j/constraints.cypher` | — | §7.1 decided; constraints.cypher written; docker-compose not yet verified | Chosen corpus agreed; both stores reachable locally; constraints applied |
| 1 | **Parse + speaker-aware chunk** (two paths: paged PDF / page-less bootstrap) | 0 | ✅ **M1 complete** | Every downloaded doc → chunks with `chunk_id`, page provenance (PDFs), speaker label, SHA256 lineage; deterministic, re-runnable |
| 2 | **Embed + Qdrant load** into `commission_transcripts` | 1 | ✅ **M2 complete** | Semantic search returns relevant chunks with full payload (commission, day, page, chunk_id) |
| 3 | **Deterministic + spaCy graph load** into Neo4j (spine + Person/Org/Place **mentions only**) | 1 | ✅ **M3 implemented & tested** — live smoke-test pending (see §7.7) | `Document→Page→Chunk` populated; `MENTIONED_IN` edges; **no claims/facts** |
| 4 | **LLM-assisted extraction** (Claude SDK) — claims/events/roles/positions | 3 (+model selection §7.4) | Infrastructure ✅; Gate 2 eval ✅; **awaiting model approval + budget** | Every write carries `confidence`+`extraction_method`; claims modelled as `:Claim … SUPPORTED_BY/STATED_BY`, never fact edges |
| 5 | **API (`apps/api`)** over both stores, then **Web (`apps/web`)** | 2,4 (+license §7.3) | ❌ Not started (dirs not scaffolded) | MVP success-test flow works end-to-end; mentions visibly distinct from claims/findings |
| 6 | **Human-review layer** — alias/dup resolution, high-risk claim confirmation | 4 | ❌ Not started | Reviewers can confirm/merge/flag; decisions persisted with provenance |

**Earliest demonstrable slice:** corpus → step 1 → step 2 gives a working semantic search
over real testimony without touching Neo4j or the LLM — **already live as of M2**.
**M3 slice:** `make stores-up && make neo4j-constraints && build-graph --commission madlanga`
loads spine + SPOKE_IN + MENTIONED_IN; then take any `chunk_id` from a Qdrant hit and
traverse to its connected Person/Org/Place in Neo4j — the MVP-adjacent check.
See `docs/queries.md` query #5 for the provenance path Cypher.

---

_Source-of-truth specs: `docs/ontology.md`, `docs/qdrant-model.md`, `docs/neo4j-model.md`,
`docs/build-plan-shared-core.md`, `docs/build-plan-{zondo,madlanga}.md`,
`docs/decisions/0004-shared-core-commission-adapters.md`. Precedence: canonical model →
build plans → `README.md` → other root docs._
