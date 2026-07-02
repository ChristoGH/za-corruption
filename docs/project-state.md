# Project State — Commission Transcript Intelligence Platform

> **Live status lives in `NEXT.md` (repo root) — if this snapshot and `NEXT.md` disagree,
> `NEXT.md` wins.** This file is a periodic snapshot, not the running state. As of 2026-06-19
> **M4 is COMPLETE** (full `extract-corpus --all` run + corpus-wide `:Claim` load done + sweep
> GREEN); the "run `--all` now vs fix the parser first" call was **executed, not still open** —
> do not re-open it. Re-reads without live-code access should defer to `NEXT.md`.

_Snapshot for planning. Last updated: 2026-06-22. Repo public at
`github.com/ChristoGH/za-corruption` (CI green on `main`). **M0–M3 complete; M4 COMPLETE
(2026-06-19) — the full Haiku `extract-corpus --all` was run and the `:Claim` layer is
loaded corpus-wide.** A blocking corpus-integrity pass
earlier excluded **two duplicate publications** of the same sittings (the day-80 "_Full"
partial and a "DAY 15"-headed republication of day 16 — human-reviewed `superseded_by`
registry records, files retained). Active corpus: **106 transcript docs / 106 hearing
days, 18,192 pages, 81,712 turns, ~3.65M words, 103 speaker labels → 14,783 chunks** in
Qdrant at exact parity. Role/word-share attribution is heuristic and flagged PROVISIONAL
(verify per-day witness, override via `--role-map`, before publishing). Parsing details:
`docs/parse-notes.md`. Post assets: `make post-assets` → `assets/post1/`.
**139 tests pass** (with the `stats`/matplotlib extra installed; `test_charts` self-skips
via `pytest.importorskip` when it is absent).

**M4 status (COMPLETE 2026-06-19).** The §7.4 model/budget decision is
**RESOLVED**: **Haiku approved and human Tier-3 sign-off given (2026-06-16,
`reports/canary_signoff_triage.md`)** — full corpus ≈ US$40 sync / US$20 batch. The
`:Claim` graph writer is **built** (`write_claims`, `build-graph --with-claims`, ADR
0005) with two speaker/attribution pre-steps and a resolver fix (pre-steps A/B + finding
#2). The **pre-flight canary v2 ran GREEN** on the days 36+43 slice
(`reports/preflight_canary.md`, spec `docs/preflight-canary-v2.md`): both structural REDs
clear (idempotent per-type load; no silent subject detachment), provenance intact, no
fact edges, ~US$5.5 spend. Two follow-ups were **deliberately deferred** (ADR 0006), neither a
gate. **`extract-corpus --all` HAS NOW BEEN RUN (2026-06-19):** full Haiku pass over all
**14,783 chunks → 49,068 claims**, 0 dead-letters, ≈US$20 (batch + sync finish). The free
corpus-wide **`structurally_asserted` sweep ran GREEN** (0.72% structural flags; §C triaged
to 0 genuine misattributions), and the **`:Claim` layer is loaded corpus-wide** — ~46,546
claims (of 49,068) after the **raw-speaker fallback (ADR 0007)** recovered the prior 34%
speaker-unresolved drop; only ~1,877 quote-unrecovered and genuinely empty-speaker claims
remain out. Remaining: API/web is **built (M5: `apps/api` + `apps/web`, tests green)**, pending
the live localhost demo at the human review gate and the license/publication decision (§7.3).
Canned queries: `docs/queries.md`._

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
| LLM extraction infrastructure | ✅ Implemented; Gate 2 eval complete; **model decided (Haiku) + Tier-3 sign-off 2026-06-16** | `extraction/`, `eval/`, `resolution/`, `cli/extract_corpus.py`, `cli/cross_model_eval.py` |
| LLM claim extraction over corpus (`extract-corpus --all`) | ✅ **Run 2026-06-19** — 14,783 chunks → 49,068 claims cached, 0 dead-letters, ≈US$20 | `cli/extract_corpus.py` |
| spaCy NER detection | ✅ Implemented (M3); lazy-load behind `spacy` extra; `MentionDetector` protocol for test injection | `graph/mentions.py` |
| Graph load → Neo4j — spine + mentions | ✅ Implemented & tested (M3); idempotent MERGE; two provenance paths; SPOKE_IN + MENTIONED_IN | `graph/neo4j_store.py`, `cli/build_graph.py`; canned queries: `docs/queries.md` |
| NLP extraction (spaCy entities/roles into Neo4j) | ✅ Implemented (M3) — spaCy detects Person/Org/Place, resolved via canonical store | `graph/mentions.py`, `graph/neo4j_store.py` |
| **`:Claim` graph layer → Neo4j (M4)** | ✅ **Loaded corpus-wide 2026-06-19; reloaded under ADR 0007** — ~46,546 claims (of 49,068) with the raw-speaker fallback (only quote-unrecovered + genuinely empty-speaker out), `MENTIONS` + `MENTIONED_IN`, `status='alleged'` | `graph/neo4j_store.py` (`write_claims`), `cli/build_graph.py` (`--with-claims`) |
| Turn-speaker attribution validator (pre-step B) | ✅ Implemented (3-bucket partition: model-wrong / parser-gap / quote-unrecoverable) | `eval/attribution.py` |
| FastAPI query layer (`apps/api`) | 🟡 **Built (M5)** — `/health`, `/search`, `/chunk/{id}/graph`, `/claim/{id}`; read-only; tests green | `apps/api/` |
| React/Vite frontend (`apps/web`) | 🟡 **Built (M5)** — one read-only page (search → results → chunk graph → claim); mentions visibly distinct from claims | `apps/web/` |
| Human review workflow | ❌ Not started | — |

**M1 feasibility verified (2026-06-11, PyMuPDF over all 108 downloaded transcripts):**
parsing is "Not started" as *code*, but the input is de-risked — **0 of 108 are scanned**
(born-digital, mean ~1,300 chars/page, **18,485 PDF pages**), speaker labels are
line-initial/uppercase/colon-terminated as assumed (~109k corpus-wide), and the main
cleaning hazard is ~37k interleaved line-number tokens (not OCR). See the M1 pre-step in
`docs/milestone-plan.md`.

**MVP success test (Neo4j half now LIVE; confirm Qdrant load to close the loop):** search
Qdrant for a topic → open a result → jump from that chunk into Neo4j to see connected
people/orgs/places/hearing day, with mentions clearly distinguished from claims/findings.
The Neo4j side is loaded (spine + SPOKE_IN + MENTIONED_IN + `:Claim`) and the Matlala hinge
traversal works live across all 106 days; verify `load-qdrant` parity to complete the loop.

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
  **Populated:** **14,783 Haiku** (full corpus, `extract_v1`) + 672 Opus + 1 Sonnet chunk
  extractions, plus the Opus framing-judge cache; cumulative logged spend ≈ US$40 (eval +
  sampling + canary + the ~US$20 full Haiku run). 0 dead-letters corpus-wide.
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
- `eval/attribution.py` (**pre-step B**) — deterministic turn-speaker attribution
  validator: maps each claim's `find_quote` span to its containing turn (re-derived from
  chunk text via the parser's `LABEL_RE` + an augmented role+surname regex) and partitions
  every mismatch into **bucket 1 MODEL-WRONG** (the only "attribution-error rate"),
  **bucket 2 PARSER-GAP** (absorbed `COMMISSIONER <surname>` turns — model right, parser
  wrong), **bucket 3 QUOTE-UNRECOVERABLE**. Pure; no live DB. Tested both directions.
- `resolution/canonical.py` — `CanonicalStore`: alias index + title-stripped bare index,
  both scoped by entity-type group so the same surface can resolve differently by type
  (e.g. "CHAIRPERSON" → the person or the procedural role). Surname-only aliases
  forbidden (four distinct Khumalos in this corpus alone). **Finding #2 fix:** the bare
  index now suppresses any single-token surname owned by >1 canonical entity — derived
  from the seed by surname-token ownership (not the older strip-based count), so bare
  `MKHWANAZI` no longer auto-resolves to the KZN general now that ≥2 Mkhwanazis are seeded.
  `ambiguous_surnames` is exposed for the regression guard; full-form/speaker resolution
  unaffected.
- `resolution/seed_entities.yaml` — human-owned canonical entity seed for the Madlanga
  corpus (bench, counsel, witnesses, organisations, places); resolver matches against
  this, never adds to it. **Expanded in pre-step A** with 5 metro/EMPD "COMMISSIONER
  <surname>" witness entities — `jd-mkhwanazi` (EMPD, **distinct** from
  `nhlanhla-mkhwanazi`), `revo-spies`, `commissioner-faro`/`-bolhuis`/`-malatji` — each
  its own scoped entity, no bare-surname aliases, all VERIFY-flagged (identities inferred
  from testimony; confirm before publication).
- `graph/mentions.py` — `DetectedMention` + `MentionDetector` protocol +
  `SpacyDetector` (lazy `en_core_web_trf` import behind `spacy` extra; maps spaCy
  PERSON/ORG/GPE/LOC/FAC labels → person/org/place; deduplicates by surface+type).
- `graph/neo4j_store.py` — `Neo4jStore`: driver wrapper (accepts injected driver for
  tests); `write_spine()` (paged vs bootstrap path, UNWIND batched, MERGE only);
  `write_speaker_edges()` (SPOKE_IN); `write_mention_edges()` (MENTIONED_IN per type,
  per-chunk dedup on canonical entity ID); `count_chunks()` for idempotency. **M4 claim
  layer (ADR 0005):** `claim_key()` (deterministic `claim_id` = sha256 over chunk_id +
  resolved speaker id + normalized predicate + quote-span offsets), `build_claim_rows()`
  (pure resolver: speaker→`STATED_BY`, subject/object refs→`MENTIONS{role}`, **policy-(b)**
  raw-subject fallthrough recorded on the claim, drops+counts speaker-unresolved and
  quote-unrecoverable claims), `write_claims()` (MERGE-only; `status='alleged'` set
  `ON CREATE` so re-runs never clobber a human-review status), `ClaimStats`. Banned
  relationships enforced by construction: no `APPEARS_IN`, no direct paged
  `Document-[:HAS_CHUNK]->Chunk`, no fact edges; the spine/mention writers still write
  zero `:Claim` — claims come only from `write_claims`.
- `graph/__init__.py` — module marker (no longer a stub).
- `cli/build_graph.py` — `build-graph` CLI: `--commission {zondo,madlanga,both}`,
  `--all`, `--dry-run` (counts only, no writes/NER), `--no-ner` (spine + SPOKE_IN
  only), `--force`, `--limit N`, **`--with-claims`** (load the `:Claim` layer from cached
  extractions, after spine+SPOKE_IN+MENTIONED_IN), **`--extract-model`** (default
  `claude-haiku-4-5`), **`--cache-dir`**. Loads canonical store from `seed_entities.yaml`.
- `cli/extract_corpus.py` — `extract-corpus` CLI: `--estimate-only` (zero API calls),
  `--budget-usd` hard cap with clean checkpoint, `--days`/`--all`, `--batch` flag.
- `cli/cross_model_eval.py` — `cross-model-eval` CLI: runs Gate 2 evaluation against
  the frozen stratified sample; cache-aware (re-runs cost $0 if arms already cached).

### Two `eval/` directories — intentional split

- **`eval/artifacts/`** (repo root) — output artifacts from completed eval runs:
  `gate2_model_review.md`, `hardcase_appendix.md`, `metrics.json`, `sample_17.txt`.
  These are versioned results, not code.
- **`packages/ingestion/commission_ingestion/eval/`** — the harness code that produces
  them: `sample.py`, `compare.py`, `framing_judge.py`, `report.py`. Importable as
  `commission_ingestion.eval`.

The split is intentional: harness code belongs with the package it depends on;
run-specific artifacts belong at repo root alongside other output directories
(`assets/`, `data/`).

### Tests
**139 passing** (`uv run pytest packages/ingestion/tests/`; `test_charts` runs when the
`stats`/matplotlib extra is installed and `pytest.importorskip`s out otherwise). Covers: madlanga discovery + classification, zondo + zondo-bootstrap discovery,
downloader (incl. 404→missing), registry upsert, source-record model, PDF parsing +
chunking, corpus statistics, corpus integrity (duplicate detection, reconciliation),
Qdrant store (idempotency, payload, superseded-doc purge, search filters), charts,
cross-model eval (sampler, compare metrics, framing flags, resolution), **graph layer
(42 tests)** — spine paths, SPOKE_IN, MENTIONED_IN, banned-relationship enforcement,
idempotency-via-MERGE, **and the M4 claim writer** (claim_id determinism/idempotency,
`status='alleged'` writer-authored, STATED_BY/SUPPORTED_BY + chunk-MATCH provenance,
canonical subject→MENTIONS, raw-subject recorded-not-dropped, skip+count of
speaker-unresolved/quote-unrecoverable). New files: **`test_attribution.py`** (pre-step B
3-bucket partition + discriminator) and **`test_seed_resolution.py`** (the 5 commissioner
labels resolve to distinct ids; Mkhwanazi/Khumalo pairs stay distinct; the seed-derived
ambiguity guard — every surname owned by >1 entity returns `None` on bare lookup).

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

From `docs/` (canonical model) and `docs/decisions/{0004,0005,0006}`. _The relationship
names, the collection, and the embedding model below were re-verified against
`docs/ontology.md`, `docs/neo4j-model.md`, and `docs/qdrant-model.md` on 2026-06-11; the
claim-writer and resolver decisions (#9–#10) were added at the M4 canary, 2026-06-16._
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
9. **`:Claim` writer schema (`docs/decisions/0005`).** Deterministic `claim_id` MERGE key
   (content-addressed: chunk_id + resolved speaker id + normalized predicate + quote-span
   offsets) so re-loads are idempotent — never a random UUID. Raw (unresolved) subjects use
   **policy (b)**: recorded on the `:Claim` (`unresolved_subjects` + `has_unresolved_subject`),
   never a separate raw node, never silently dropped — countable and surfaceable for review.
   `status='alleged'` is written `ON CREATE` only (the writer owns the *initial* status; it
   must not clobber later human review). **Operative rule:** publication/review queries read
   the `MENTIONS` edge, never the advisory `has_unresolved_subject` flag (which can go
   stale-true after a seed alias lands).
10. **Bare-surname ambiguity suppression is seed-derived (finding #2).** Any single-token
    surname owned by >1 canonical entity must not auto-resolve on the bare index — enforced
    structurally so the next colliding surname is protected with no code change.

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

4. **LLM extraction model & budget — ✅ RESOLVED (Haiku approved, Tier-3 signed off
   2026-06-16).** Gate 2 cross-model eval (40-chunk stratified sample, seed 17) found
   Haiku lowest on both the defamation-critical asserted-as-fact axis (4.3% vs Sonnet
   10.8% / Opus 12.7%) and cost. **Decision: `claude-haiku-4-5`**, full corpus ≈ US$40
   sync / US$20 batch (`eval/artifacts/gate2_model_review.md`, `metrics.json`).

   The decision was gated through a **pre-flight canary v2** (spec
   `docs/preflight-canary-v2.md`, results `reports/preflight_canary.md`) on the days 36+43
   slice (408 chunks, 388 net-new): **GREEN** — Tier 0 cache-key regression passed; Tier 2
   structural REDs both clear (per-type idempotency identical on load-twice; no silent
   subject detachment; provenance intact; no fact edges; `status='alleged'` on all). The
   one flag for the human read was the **net-new asserted-as-fact rate 7.5%** (above the
   hard-sample 4.3%); triaged in `reports/canary_signoff_triage.md` to **exactly 1 of 93
   genuine structural slips** (the other ~92 are judge lexical-strictness on doctrine-
   compliant `stated that…` predicates — structural, not lexical, protection per CLAUDE.md
   93–102). **Christo gave Tier-3 sign-off: SHIP `--all` as-is.**

   **DONE (2026-06-19):** `extract-corpus --all` ran (Haiku batch + sync finish) — 14,783
   chunks → 49,068 claims, ≈US$20. The corpus-wide `structurally_asserted` sweep ran GREEN —
   **354 structural flags / 49,068 = 0.72%** (under the 2% gate), 0 unparseable; §C attribution
   triaged to **0 genuine graph-level misattributions** (`reports/sectionC_bucket1_review.md`).
   The `:Claim` layer was first loaded at 30,274 claims with **34% (16,915) dropped on
   `speaker_unresolved`**; that drop was **RESOLVED by the raw-speaker fallback (ADR 0007)**,
   reloading to ~46,546 — see the "Post-`--all` reality" subsection below.

### Post-`--all` reality (NEW — 2026-06-19, supersedes the "not yet run" framing above)

- **Full extraction + corpus-wide claim load are DONE.** 49,068 claims extracted; first
  loaded at 30,274, then **reloaded to ~46,546 under ADR 0007** (spine + SPOKE_IN +
  MENTIONED_IN + `:Claim`); post-`--all` sweep GREEN.
- **Speaker-unresolved claim drop (HIGH — highest-value data fix). RESOLVED (ADR 0007).**
  16,915 claims (34%) were dropped because the speaker label didn't resolve to a seeded
  `:Person` (subjects fall through to policy-(b); speakers did not). The fix gave speakers the
  same `raw:` fallback subjects get: a non-empty unresolved speaker now loads as a raw,
  flagged `STATED_BY :Person` (`speaker_unresolved=true`), recovering coverage to ~46,546;
  only genuinely empty-speaker (and ~1,877 quote-unrecovered) claims stay out.
- **ADR 0006 Follow-up 3 added:** the post-`--all` corpus-wide sweep (`scripts/postrun_sweep.py`
  — `structurally_asserted` + subject-faithfulness) is now the graph-load acceptance gate;
  ran GREEN (0.72% structural, 0 genuine misattributions).
- **`extract_v2` case strengthened (deferred #10):** 20,818 claims (42%) carry a pronoun
  predicate — the real surfaced number behind the deferred fix (the doc's earlier "~8" was an estimate).
- **Hinge verified at full scale:** Matlala named in 62/106 days — #1 non-procedural figure
  (`scripts/association_analysis.py`; visual `linkedin/matlala_web.svg`). Two analytical tracks
  + LinkedIn series postmarked in `plans/`; vault hub at `knowledge-vault/10-Projects/`.

### Build-readiness gaps (known work, no decision needed)

5. **`apps/api` and `apps/web` not scaffolded.** CLAUDE.md mandates the full monorepo;
   only `packages/ingestion` exists.

6. **`infra` is skeletal for Docker.** `infra/neo4j/constraints.cypher` exists (29 lines);
   `docker-compose.yml` defines Qdrant + Neo4j 5.26 services. `make stores-up` brings
   both up; `make neo4j-constraints` applies constraints. `infra/docker/ingestion/`
   exists but no compose file for running the full ingestion pipeline in containers.

7. **Live Neo4j smoke-test complete (2026-06-14).** `build-graph --commission madlanga
   --limit 3 --force` against a running Neo4j instance produced: 530 chunks in the paged
   `Document→Page→Chunk` spine, 928 SPOKE_IN edges, 1 279 MENTIONED_IN edges, 0 `:Claim`
   nodes, 0 `APPEARS_IN` edges, 0 direct `Document-[:HAS_CHUNK]->Chunk` shortcuts on
   paged docs. M3 is fully accepted.

8. **LLM extraction safety design — partly built.** The extraction schema enforces
   reported-speech framing, the graph writer enforces `status="alleged"` and records
   `extraction_method` + raw-subject surfaces, and pre-step B independently audits
   speaker attribution. **Still not built:** the human review gate for high-risk claims
   and the alias-resolution review queue (the canary's Tier-3 packet is a manual
   stand-in). A `confidence` value is intentionally unset at the `extract_v1` layer
   (`certainty` — the speaker's own hedging — is stored instead; no fabricated number).

### Deferred from the M4 canary (ADR 0006 — tracked, not gates)

9. **`turns.py` parser gap → re-chunk milestone (medium).** `LABEL_RE` has no surname
   slot, so `COMMISSIONER <surname>:` turns (Mkhwanazi, Spies, Faro, Bolhuis, Malatji —
   ~7k inline turns) are absorbed into the preceding speaker and are absent as turn
   speakers. This drives the canary's **bucket-2** attribution mismatches (643 on the
   slice, all `jd-mkhwanazi`; model right, parser wrong). The claim writer still gets the
   right `STATED_BY` from the model's inline attribution (pre-step A aliases), but
   `SPOKE_IN` mis-attributes these witnesses. The fix re-chunks the corpus → new
   `chunk_id`s → **invalidates the extraction cache, the Gate 2 baseline, and the Qdrant
   load** (requires Gate 2 re-baseline), so it is sequenced as its own post-`--all`
   milestone, batched with #10.
10. **`extract_v2` predicate-verb fix (low).** Make every predicate open with a
    reported-speech verb (closes the 1 genuine §B slip + 8 corpus-wide structural flags at
    source). Deferred because bumping `PROMPT_VERSION` re-extracts the whole corpus
    (~US$20 batch); batch with #9 rather than pay a second full run for 1-in-93.
11. **5 commissioner identities are VERIFY-flagged.** `jd-mkhwanazi`, `revo-spies`,
    `commissioner-faro`/`-bolhuis`/`-malatji` in `seed_entities.yaml` are inferred from
    testimony context — a human confirms before *publication*, per the seed convention.

### Lower-risk cleanups

12. **Classification heuristics are filename-driven.** Madlanga source-typing keys on
    filenames; robust but heuristic. A second commission (or a relabel) may need review.
13. **Registry merge quirk (low).** `upsert` keeps `record.date or existing.date`; a
    corrected parse returning `None` can't override a stale-but-valid stored date.
14. **Orphan files — resolved.** The 2 stale-sanitization PDFs in `data/raw/madlanga`
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
| 0 | **Decide first corpus + Zondo source** (§7.1–7.2); stand up `docker-compose` (Qdrant+Neo4j) and `infra/neo4j/constraints.cypher` | — | ✅ **stores verified up 2026-06-19** — `make stores-up` + `neo4j-constraints` + `build-graph` ran against live Neo4j; Qdrant load pending count-confirm | Chosen corpus agreed; both stores reachable locally; constraints applied |
| 1 | **Parse + speaker-aware chunk** (two paths: paged PDF / page-less bootstrap) | 0 | ✅ **M1 complete** | Every downloaded doc → chunks with `chunk_id`, page provenance (PDFs), speaker label, SHA256 lineage; deterministic, re-runnable |
| 2 | **Embed + Qdrant load** into `commission_transcripts` | 1 | ✅ **M2 complete** | Semantic search returns relevant chunks with full payload (commission, day, page, chunk_id) |
| 3 | **Deterministic + spaCy graph load** into Neo4j (spine + Person/Org/Place **mentions only**) | 1 | ✅ **M3 complete** — live smoke-tested 2026-06-14 (see §7.7) | `Document→Page→Chunk` populated; `MENTIONED_IN` edges; **no claims/facts** |
| 4 | **LLM-assisted extraction** (Claude SDK) — claims (events/roles/positions later) | 3 (model §7.4 ✅) | ✅ **M4 COMPLETE 2026-06-19** — `--all` run, `:Claim` layer loaded corpus-wide | 49,068 claims extracted; ~46,546 loaded under ADR 0007 (`STATED_BY`/`SUPPORTED_BY`/`MENTIONS`, `status='alleged'`), sweep GREEN; the prior 34% speaker-unresolved drop is RESOLVED (raw-speaker fallback) |
| 5 | **API (`apps/api`)** over both stores, then **Web (`apps/web`)** | 2,4 (+license §7.3) | 🟡 **Built (M5) — code complete, tests green; pending live localhost demo at the review gate.** `apps/api` (FastAPI: `/health`, `/search`, `/chunk/{id}/graph`, `/claim/{id}`) + `apps/web` (Vite/React, one read-only page). Demo pre-flight: confirm `make load-qdrant` parity (~14,783 points). License (§7.3) still gates public hosting, not the localhost demo | MVP success-test flow works end-to-end; mentions visibly distinct from claims/findings |
| 6 | **Human-review layer** — alias/dup resolution, high-risk claim confirmation | 4 | ❌ Not started | Reviewers can confirm/merge/flag; decisions persisted with provenance |

**Earliest demonstrable slice:** corpus → step 1 → step 2 gives a working semantic search
over real testimony without touching Neo4j or the LLM — **already live as of M2**.
**M3 slice:** `make stores-up && make neo4j-constraints && build-graph --commission madlanga`
loads spine + SPOKE_IN + MENTIONED_IN; then take any `chunk_id` from a Qdrant hit and
traverse to its connected Person/Org/Place in Neo4j — the MVP-adjacent check.
See `docs/queries.md` query #5 for the provenance path Cypher.
**M4 slice (canary-proven 2026-06-16):** `extract-corpus --days 36,43` then
`build-graph --commission madlanga --with-claims` adds `:Claim` nodes
(`STATED_BY`/`SUPPORTED_BY`/`MENTIONS`) onto the spine — 1,221 claims loaded idempotently
on the slice into a throwaway instance, both structural REDs clear. **The full `extract-corpus
--all` + `build-graph --with-claims` + corpus-wide sweep are now DONE (2026-06-19)** — see
"Post-`--all` reality" in §7. The speaker-unresolved 34% drop is RESOLVED (ADR 0007 raw-speaker
fallback, ~46,546 loaded) and **M5 (`apps/api` + `apps/web`) is built and green**. **Immediate
next action:** the M5 demo pre-flight — confirm `make load-qdrant` parity (~14,783 points), then
run the localhost loop (`make stores-up` + `make api-dev` + `make web-dev`) as the review gate.

---

_Source-of-truth specs: `docs/ontology.md`, `docs/qdrant-model.md`, `docs/neo4j-model.md`,
`docs/build-plan-shared-core.md`, `docs/build-plan-{zondo,madlanga}.md`,
`docs/decisions/0004-shared-core-commission-adapters.md`,
`docs/decisions/0005-claim-writer-schema.md`,
`docs/decisions/0006-post-canary-followups.md`. M4 canary: `docs/preflight-canary-v2.md`
(spec), `reports/preflight_canary.md` (results), `reports/canary_signoff_triage.md`
(sign-off). Precedence: canonical model → build plans → `README.md` → other root docs._
