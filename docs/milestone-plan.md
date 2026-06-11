# Milestone Plan — Commission Transcript Intelligence Platform

_Drafted 2026-06-11 against `master @ 4957ff5` and `project-state.md`. Madlanga-first;
Zondo source decision parked (see M-Z at the end). Each milestone ends with something
you can screenshot or screen-record — that is the gate, not just the tests._

Conventions used below:

- **Repo paths** refer to the existing layout: `packages/ingestion` (package
  `commission_ingestion`), `data/sources/source_registry.jsonl`, `data/raw/<commission>/`,
  `docs/`, `infra/`. Adjust if your `src/` layout differs.
- **AC** = acceptance criteria (testable). **PA** = public artifact (the thing you post).
- Estimates assume evenings/weekends pace.

---

## M0 — Public-repo readiness (do first, ~2–3 evenings)

The repo *is* the consultant credibility anchor, so it goes public before Post #1,
not after.

**Build**

| Task | Where |
|---|---|
| Public README: one-paragraph pitch, architecture diagram (the §2 pipeline), the governing principle ("Mention ≠ Claim ≠ Finding ≠ Fact") above the fold, milestone roadmap with checkboxes | `README.md` |
| `LICENSE` (Apache-2.0) for the code + `NOTICE`; a **separate** data notice (`DISCLAIMER.md` / `LICENSE-DATA`): transcripts are official public records — no ownership claimed; derived artifacts (stats, graph, chunk metadata) offered CC BY 4.0 with attribution to the official source; testimony is allegation, not fact; takedown contact | repo root |
| Secrets & history audit: no API keys, no session cookies (`INGEST_ZONDO_STORAGE_STATE` values), no personal email in committed code; confirm PDFs/`.txt` corpora are gitignored (registry JSONL *is* committed — it's URLs + hashes, fine) | `.gitignore`, history scan |
| ✅ Orphan files already reconciled (180/180, state doc §4). **Remaining task:** in the README, note the 1 record missing at source (Day 6, HTTP 404) and the 3 days absent from the public record (Days 4, 14, 104) so the corpus numbers you publish — 109 records / 107 days, to Day 110 — are exact and caveated | `README.md` |
| CI: run the 33 tests on push (GitHub Actions, uv) | `.github/workflows/ci.yml` |

**AC**
- Fresh clone → `uv sync` → `uv run pytest packages/ingestion/tests/` passes on CI badge.
- README renders the pipeline diagram and roadmap; DISCLAIMER linked from README.
- `git log -p` contains no secrets; raw corpus not in history.

**PA** — the repo link itself (goes in the first comment of every post).

---

## M1 — Parse + speaker-aware chunking + descriptive statistics (~1–2 weeks)

The deterministic provenance backbone (state doc §7.5) **plus** the analysis script
that produces Post #1's charts. No NLP, no LLM, zero per-token cost, and zero
defamation exposure — everything published is structure, not characterization.

> **Pre-step (do before writing any parser — this is the schedule risk).** Open the
> actual text of 3–5 Madlanga PDFs and confirm the transcript format: are speaker
> labels really line-initial / uppercase, and is the furniture (headers, line numbers,
> timestamps) consistent? Post #1's lead chart ("who does the talking") depends on
> reliable speaker attribution. **If labels are inconsistent or OCR-garbled, fall back
> Post #1 to the corpus-size + sitting-calendar story** (needs only page counts + dates,
> not roles) and defer role analysis. Don't commit to word-share-by-role until the
> format is verified on real pages.

**Build**

| Task | Where |
|---|---|
| `parsing/` module: PyMuPDF page extraction → `{page_no, text, char_count}`; scanned-page detector (mean chars/page < threshold ⇒ flag `needs_ocr` in registry notes, skip — never emit empty chunks) | `packages/ingestion/.../parsing/pdf.py` |
| Transcript furniture stripping: inspect 3 real Madlanga records first, then strip recurring headers/footers, margin line-numbers, timestamps; patterns as named constants with a short `PARSE_NOTES.md` | `parsing/clean.py`, `docs/parse-notes.md` |
| Speaker-turn detection: line-initial, short, uppercase labels (`CHAIRPERSON:`, `ADV CHASKALSON SC:`, `LT GEN MKHWANAZI:`) → turns `{speaker_label, text, page_start, page_end}`; defensive against mid-sentence colons | `parsing/turns.py` |
| Chunking: pack consecutive turns ≤ `CHUNK_MAX_CHARS` (~1800), never split a turn; `chunk_id = sha256(text)`; carry `{doc_sha256, day_no, date, page_start, page_end, speakers[]}` | `parsing/chunking.py` |
| Output: one JSONL per document in `data/processed/madlanga/`, schema versioned like `SourceRecord` | `models/chunk_record.py` |
| `cli/parse_corpus.py`: reads registry (status=downloaded, source_type=transcript), writes processed JSONL, idempotent (skip if output exists with matching `doc_sha256`), `--limit`, `--day` | `cli/` |
| **Stats script** `cli/corpus_stats.py` → `data/processed/stats/` charts (PNG/SVG, matplotlib): see "Post #1 chart menu" in the LinkedIn kit | `cli/`, output gitignored except final post images in `docs/assets/` |
| Tests: turn detection on a real-page fixture; chunk page-range maps back to actual PDF page text; idempotent re-run | `packages/ingestion/tests/` |

**AC**
- ≥ 100 of 109 transcripts parse cleanly end-to-end; every failure is classified
  (`needs_ocr` / parse error) in the registry, not silent.
- Spot-check: 5 random chunks visually match the cited PDF pages.
- Furniture (headers, line numbers, timestamps) absent from turn text.
- Re-running `parse_corpus` is a no-op; stats script regenerates identical numbers.
- Stats script emits the headline numbers (days, pages, turns, words, distinct speaker
  labels) as a small JSON so the post copy is generated from data, not memory.

**PA / Post #1** — "The Madlanga Commission, by the numbers" (kit attached separately).

---

## M2 — Embeddings + Qdrant + infra (~1 week)

**Build**

| Task | Where |
|---|---|
| `docker-compose.yml`: Qdrant + Neo4j + APOC (state doc §7.7 — currently absent); pin the Neo4j version after confirming it (the 5.26/APOC value is from CLAUDE.md, not the canonical store docs — state doc §6); auth via env | `infra/docker/docker-compose.yml` |
| `infra/neo4j/constraints.cypher` (referenced by docs, not yet present) — write it now even though Neo4j loads in M3 | `infra/neo4j/` |
| Qdrant store: shared collection `commission_transcripts` (decision #1), `commission` payload field, bge-small-en-v1.5 384-dim cosine. **Point IDs must be UUID/uint — use `uuid5(NAMESPACE_URL, chunk_id)`, keep sha in payload** | `packages/ingestion/.../vector/qdrant_store.py` |
| Batch embed + upsert all Madlanga chunks; idempotent | `cli/load_qdrant.py` |
| Search CLI: `query "..." [--day N] [--speaker LABEL]` printing day, pages, snippet | `cli/search.py` |

**AC**
- Cold start: `docker compose up -d` → load → collection count equals chunk count.
- Re-load adds zero points.
- 5 thematic test queries (e.g. "disbanding of the task team", "threats against
  investigators") return relevant chunks with correct day/page payloads.

**PA / Post #2** — 30–45s screen recording: *"Ask [107] hearing days of testimony anything."*
Type a question, show the hit, open the official PDF at the cited page. The
provenance-to-page jump is the wow moment — keep it in frame.

---

## M3 — Mentions-only graph in Neo4j + the network render (~1–2 weeks)

**Build**

| Task | Where |
|---|---|
| Deterministic + spaCy mention extraction (entities only — no claims): Person/Org/Place per chunk, with a seed/alias file for SA entities (IPID, EMPD, PKTT, NPA, SAPS, Hawks; commission principals) and basic canonicalisation (strip honorifics, fuzzy-collapse via rapidfuzz) so the graph doesn't fragment | `extraction/mentions.py`, `extraction/aliases.yaml` |
| Graph load per `docs/neo4j-model.md`: `Document → Page → Chunk` spine; `MENTIONED_IN`, `SPOKE_IN`; `HAS_PROCEDURAL_ROLE` from speaker labels (decision #3); MERGE on canonical keys, idempotent | `graph/neo4j_store.py`, `cli/load_graph.py` |
| Co-mention projection + export for visual: entity-pair weights → Cosmograph/Gephi export (CSV) and a curated Bloom/Browser scene | `cli/export_comention.py` |
| 3 canned Cypher insight queries in the repo: top co-mentions with a given org; speakers by procedural role; places by hearing day | `docs/queries.md` |

**AC**
- Spine + mentions load idempotently; counts stable across re-runs.
- "Brown Mogotsi" / "Mr Mogotsi" / "B Mogotsi" resolve to one node (alias test).
- Every mention traceable to chunk → page → doc SHA → URL via one Cypher path.
- One exported network render at poster quality (≥ 2000px).

**PA / Post #3** — the network image: *"[107] hearing days of testimony as one picture."*
Annotate 3 clusters. Caption discipline: co-occurrence in testimony, not relationships
between people. This is the series' signature visual.

---

## M4 — Claims layer (Claude SDK) + human review gate (~2–3 weeks)

**Build**

| Task | Where |
|---|---|
| Pluggable LLM extractor (decision #6): Anthropic SDK, JSON-only output validated by pydantic; claims `{text, attribution, people[], confidence}`, events only for procedural facts; prompt caching for the fixed system prompt; cost log per run | `extraction/llm.py` |
| Hard rule encoded in prompt + post-validation: allegations about a person's conduct are **claims with attribution, never events/facts** | tests assert this on an accusatory fixture chunk |
| Graph load: `(:Claim)-[:SUPPORTED_BY]->(:Chunk)`, `STATED_BY`, status/confidence/method on every write (decision #5) | `graph/claims.py` |
| Minimal review workflow: low-confidence claims + alias merges exported to a reviewable CSV/JSONL; approved file is the only path into "reviewed" status | `cli/review_export.py`, `docs/review.md` |
| Run on a bounded slice first (e.g. days 1–10) to calibrate cost & quality before the full corpus | — |

**AC**
- 100% of claim nodes carry attribution, confidence, method, and a `SUPPORTED_BY` chunk.
- Zero allegation appears as an `:Event` (automated check).
- Cost per hearing day measured and documented.
- Review round-trip works: export → edit → import → status change.

**PA / Post #4** — methodology-forward: *"How do you let an AI read allegations
responsibly?"* Show the claim card UI/graph with its provenance chain. This is the
post that differentiates you from every reckless "AI over documents" demo — and the
one to clear with a media lawyer if it names individuals (20-minute consult; do it).

---

## M5 — Thin public surface + earned media (~2 weeks, scope ruthlessly)

**Build**

| Task | Where |
|---|---|
| `apps/api`: FastAPI, three endpoints only — semantic search, chunk→graph neighborhood, claim detail with provenance | `apps/api/` |
| `apps/web`: single read-only page implementing the MVP success test (search → result → connected entities/claims, mentions visually distinct from claims) | `apps/web/` |
| Medium long-read assembled from posts 1–4 + architecture narrative | external |
| Daily Maverick / TechCentral pitch (below) | external |

**AC** — the MVP success test, live, on a screen-recordable URL (even localhost is fine
for the recording; public hosting optional and only if anonymised/read-only).

**PA / Post #5** — the demo recording + Medium link + "what I'd build next."

---

## M-Z (parked) — Zondo authoritative source

Revisit only after M3. Options ranked: (a) manual browser session capture via the
existing `INGEST_ZONDO_STORAGE_STATE` hook; (b) formal acceptance of DSFSI bootstrap
with `authoritative=false` surfaced in every public artifact; (c) a polite data
request to the records custodian — which, written about, is itself good content.

---

## Publishing cadence & guardrails (applies to every PA)

1. One post per milestone, numbered series, same cover template, artifact-first.
2. Repo + Medium links in the **first comment**, never the post body.
3. M1–M3 publish structure only. Claim-level content waits for M4's review gate.
4. Named individuals: always "testimony before the commission alleged…", always a
   page-cited link to the official record. The provenance spine makes this one click —
   say so; it's the differentiator.
5. Disclaimer footer on every post: links to `DISCLAIMER.md`.
6. Daily Maverick pitch timing: after Post #3 (you'll have the killer image + a track
   record of three public artifacts). Pitch angle: "I indexed every available transcript
   of the Madlanga Commission — here's what the structure of the testimony itself
   reveals." (See the coverage caveat in M0; don't claim "every page.")
   TechCentral is the fallback with a more technical angle.
