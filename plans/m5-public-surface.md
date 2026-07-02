# M5 — Thin public surface (apps/api + apps/web). Build prompt.

Live per-task prompt (per `plans/README.md`). Move to `plans/archive/` when M5 lands green.
Single plan-of-record remains `docs/project-state.md §8` (this finishes stage 5).

Revised 2026-06-30 after a code-grounded review. The substantive change: `Neo4jStore` is
**write-only** today — the chunk-neighborhood and claim-detail reads do not exist and must be
added to the package store first (new deliverable 2). Plus four smaller fixes folded in
(`claim_id` join key, Neo4j ping, two speaker sources, demo pre-flight).

---

## Paste the block below into the implementation agent

```
GOAL — Finish M5: the thin, read-only public surface over the existing stores, ending at the
MVP success test from CLAUDE.md: search Qdrant for a topic → open a result chunk → jump into
Neo4j to see connected people/orgs/places/hearing-day and the claims on that chunk, with
MENTIONS visibly distinct from CLAIMS, every item traceable to day, page, and the official
source URL. Build apps/api (FastAPI) and apps/web (React+Vite+TS). Nothing more.

NON-NEGOTIABLE CONTEXT — read before writing code
- docs/neo4j-model.md, docs/qdrant-model.md, docs/ontology.md (settled relationship names,
  the Document→Page→Chunk spine, the Mention≠Claim principle).
- packages/ingestion/commission_ingestion/vector/qdrant_store.py — QdrantStore.search(...)
  returns list[qm.ScoredPoint] (.score, .payload); QdrantStore.count() is the cheap Qdrant ping.
- packages/ingestion/commission_ingestion/vector/embedder.py — BgeSmallEmbedder().embed_query.
- packages/ingestion/commission_ingestion/graph/neo4j_store.py — Neo4jStore. NOTE: it is
  WRITE-ONLY today (write_spine / write_speaker_edges / write_mention_edges / write_claims +
  count_chunks). There is NO read method for a chunk neighborhood or a claim, and NO ping.
  You will ADD those to this class (deliverable 2) before the endpoints can be built.
- packages/ingestion/commission_ingestion/cli/search.py — the existing CLI search surface;
  mirror its payload fields and snippet behaviour for /search.
- CLAUDE.md "Working agreements" + scripts/hooks/ — commit/branch discipline (below).

HARD INVARIANTS (assert these in tests; they are the legal/architectural spine)
1. READ-ONLY. The API opens read sessions only. It never writes, merges, or deletes in Qdrant
   or Neo4j. No ingestion logic in apps/ — it queries the stores, it does not own them.
2. REUSE, DON'T REIMPLEMENT. Import QdrantStore, BgeSmallEmbedder, Neo4jStore from
   commission_ingestion. No second embedder, no hand-rolled Qdrant/Neo4j client in apps/.
   ALL Cypher lives in Neo4jStore in the package (including the new reads) — apps/api/services
   are thin adapters that call store methods, never raw drivers.
3. PROVENANCE ON EVERY RESULT. Every search hit and every claim carries: commission_slug,
   day_no, page_start/page_end, source_url, chunk_id. A result with no source link is a bug.
4. MENTION ≠ CLAIM. The chunk-neighborhood response separates entities-MENTIONED_IN (leads)
   from claims-SUPPORTED_BY (attributed testimony) into distinct, separately-typed fields.
   Every claim object in that response MUST carry its claim_id (the deterministic claim_key)
   so /claim/{claim_id} is reachable — claim_id is the second join key alongside chunk_id.
   The web UI renders mentions and claims with visibly different treatment. Never one list.
5. CLAIMS ARE ALLEGATIONS. Every claim object exposes its STORED status, its STATED_BY
   speaker, and its SUPPORTED_BY chunk. Surface cl.status as written in the graph — do NOT
   hardcode "alleged". The writer sets status='alleged' ON CREATE only, so M6 human-review can
   later change a claim's status without a re-run clobbering it; the API must reflect whatever
   is stored. Current corpus is uniformly "alleged"; tests assert that on today's fixtures.
   The API must not synthesise a "fact" shape or drop attribution. Surface cl.quote as the
   ground truth; cl.text (predicate prose) is secondary and may be flagged. Also expose
   speaker_unresolved (bool): true means STATED_BY is a raw, uncanonicalised label (ADR 0007),
   not a seeded :Person — flag it so the UI can mark attribution as present-but-uncanonicalised.
6. NO SECRETS IN CODE. Credentials come from the environment / repo .env loader only.

NOTE — two speaker sources, not 1:1. /search returns speakers[] from the Qdrant payload (raw
labels, e.g. "CHAIRPERSON"); /chunk/{id}/graph returns speakers via (:Person)-[:SPOKE_IN]->,
which are RESOLVED persons. A raw label may have no resolved Person, so the two lists can
differ. Do not assume they match; label the UI sections accordingly.

PACKAGE READS (DELIVERABLE 1 — build first; the endpoints and /health all depend on them) —
add reads to Neo4jStore in packages/ingestion + unit tests:
- chunk_neighborhood(chunk_id) -> the chunk text + spine, entities via
  (e)-[:MENTIONED_IN]->(:Chunk) grouped by label (Person/Organisation/Place), speakers via
  (:Person)-[:SPOKE_IN]->, and claims via (:Claim)-[:SUPPORTED_BY]->(:Chunk) each with
  claim_id + STATED_BY + stored status + speaker_unresolved + quote. Mentions and claims
  SEPARATE. MUST handle BOTH provenance paths: paged official docs
  (:Document)-[:HAS_PAGE]->(:Page)-[:HAS_CHUNK]->(:Chunk) AND bootstrap docs
  (authoritative=false) where chunks attach directly under (:Document) with null page fields.
  Return page_start/page_end as nullable; never assume a :Page exists.
- claim_detail(claim_id) -> quote, text, stored status, certainty, attribution,
  speaker_unresolved, STATED_BY person, SUPPORTED_BY chunk (day_no, nullable page_start,
  source_url), MENTIONS entities.
- ping() -> RETURN 1 liveness check (Neo4jStore has none today; /health needs it).
Tests: the existing fake Neo4j driver mostly captures writes and returns no records — EXTEND
the fake session/result to return read rows so these methods are actually exercised. These
reads give apps/api a real seam to mock and keep all Cypher in the package (invariant 2).

SCOPE — apps/api  (FastAPI, added as a uv workspace member in root pyproject.toml)
Layout: apps/api/pyproject.toml, apps/api/app/{main,config,dependencies}.py,
apps/api/app/routes/{health,search,graph,claims}.py, apps/api/app/schemas/*.py,
apps/api/app/services/{qdrant_service,neo4j_service}.py (thin adapters over the package
classes — neo4j_service calls the new reads from deliverable 1), apps/api/README.md,
apps/api/tests/.
Exactly four endpoints — resist adding more:
- GET /health → {status, qdrant: up|down, neo4j: up|down}. qdrant via QdrantStore.count();
  neo4j via the new Neo4jStore.ping(). Never 500 the page when a store is down — report down.
- GET /search?q=&commission=&day=&speaker=&limit= → semantic search via
  BgeSmallEmbedder + QdrantStore.search. Returns ranked hits: score + the §3 provenance fields
  + speakers[] + snippet + chunk_id (the join key the UI uses for the next call).
- GET /chunk/{chunk_id}/graph → Neo4jStore.chunk_neighborhood(chunk_id). mentions and claims
  in SEPARATE response fields; each claim carries claim_id (invariant 4) and stored status.
- GET /claim/{claim_id} → Neo4jStore.claim_detail(claim_id): full provenance per invariant 5.
CORS: allow the local web origin only. Config via env (QDRANT_URL, NEO4J_URI/USER/PASSWORD,
WEB_ORIGIN) with the docker-compose defaults. Pydantic response schemas for every endpoint.

SCOPE — apps/web  (Vite + React + TypeScript; one read-only page; no router, no state lib)
- A single page: search box → results list → detail panel. useState only.
- Results list: each row shows commission, day (date), pp. start–end, speakers, snippet, and a
  source link to the official PDF. Clicking a row calls /chunk/{chunk_id}/graph.
- Detail panel: (a) connected entities grouped by type — Person/Org/Place — rendered as
  MENTIONS (clearly badged "mentioned — a lead, not a finding"); (b) CLAIMS on the chunk as
  cards, visibly distinct from mentions: each card shows STATED_BY, the verbatim quote, a
  status badge rendering the claim's stored status from the response (currently always
  "alleged" — do not hardcode it), and a source link. Clicking a claim calls /claim/{claim_id}.
- A persistent one-line disclaimer in the footer: "Allegations in the public record,
  attributed to named speakers under oath — not findings of fact."
- Point the dev server at the API via a VITE_API_BASE env var. No styling framework required;
  if used, Tailwind core classes only. No graph-viz library — a grouped list + cards is enough.

TESTS (must stay green; CI has no live stores)
- Package: unit-test the new Neo4jStore reads (chunk_neighborhood / claim_detail / ping)
  against the existing graph test fixtures in packages/ingestion/tests.
- apps/api/tests with FastAPI TestClient. Mock QdrantStore.search and the NEW Neo4jStore read
  methods (dependency-injection via app.dependencies overrides) so tests run with no
  Qdrant/Neo4j.
- Assert: search response carries chunk_id + source_url; /chunk/.../graph keeps mentions and
  claims in separate fields and every claim carries claim_id; every claim object echoes its
  STORED status (assert =="alleged" on current fixtures) and has a STATED_BY; a claim missing
  attribution raises (never silently rendered); a bootstrap chunk with null pages resolves
  without error; /health degrades gracefully when a store is down. Add an accusatory-claim
  fixture and assert it surfaces as an attributed claim, never a bare fact.
- Wire apps/api tests into the existing `make test` so the whole tree is one green suite.

MAKEFILE
- api-dev: uv run uvicorn app.main:app --reload --app-dir apps/api (depends on stores-up).
- web-install / web-dev / web-build in apps/web.
- Ensure `make test` includes the api tests.

DEMO PRE-FLIGHT (before claiming ACCEPTANCE on a live machine — not needed for CI)
- Qdrant parity: project-state §8 still lists "Qdrant load pending count-confirm". Run
  `make load-qdrant` and confirm point count ≈ 14,783 before the live demo.
- Loaded-claims state (ADR 0007, NOT the old "34% dropped"): the raw-speaker fallback now
  loads claims with a non-empty-but-unresolved speaker as a raw STATED_BY :Person flagged
  speaker_unresolved=true; only genuinely empty-speaker claims drop. Current live load is
  ~46,546 of 49,068 (per NEXT.md), so nearly every chunk has claims — the old "target chunks
  whose claims loaded" caveat is largely moot. Just confirm the graph you demo against is the
  post-ADR-0007 reload, not the superseded 30,274 load.
- License: going localhost-only sidesteps §7.3 for the demo, but does NOT discharge the
  license/publication decision, which still gates any public hosting (M6 / Track B).

ACCEPTANCE (M5 done when ALL hold)
- `make stores-up` + api-dev + web-dev gives a working loop on localhost: type a real query
  (e.g. "disbanding of the task team") → get ranked hits with day/page/source → click one →
  see connected Person/Org/Place AND the claims on that chunk, mentions visually distinct from
  claims → click a claim → see speaker + verbatim quote + "alleged" + source link.
- The flow is screen-recordable end-to-end on localhost (public hosting NOT required).
- `make test` green including the package read tests and the api tests. READMEs in apps/api
  and apps/web with run steps.
- Invariants 1–6 hold and are covered by tests.

OUT OF SCOPE — do not build (these are M6 / Track B, not M5)
- No auth, no write/edit endpoints, no public hosting, no Docker for the web app.
- No human-review / alias-merge UI (that is M6, §8 step 6).
- No evidentiary-completeness endpoints (corroborated/disputed/unanswered/not-asked) — that is
  the Track B plan; keep it out of M5.
- No new graph visualisation library; no cross-commission compare screen.

COMMIT & BRANCH DISCIPLINE (enforced by scripts/hooks/)
- Work on a new branch feat/m5-public-surface (never main).
- One atomic, green commit per logical sub-step; the pre-commit hook runs the suite — a red
  tree cannot commit; do not --no-verify.
- Conventional milestone-scoped messages: feat(m5): / test(m5): / docs(m5): .
- NEVER push, NEVER merge to main — stop at the milestone boundary for the human review gate.
- No LLM artifacts anywhere (no tool attribution, no em dashes, no robot emoji). Write plainly.

DELIVER, IN ORDER (atomic green commits)
1. feat(m5): add read methods to Neo4jStore (ping, chunk_neighborhood [both provenance paths,
   nullable pages], claim_detail) in packages/ingestion + unit tests, extending the fake
   driver to return read rows. (Build first — /health and every endpoint depend on these.)
2. feat(m5): scaffold apps/api as a uv workspace member; /health (real ping) + config + DI;
   api tests run.
3. feat(m5): /search over QdrantStore + BgeSmallEmbedder; schema + tests (mocked store).
4. feat(m5): /chunk/{id}/graph + /claim/{id} over the Neo4jStore reads; mentions/claims split
   (each claim carries claim_id + stored status + speaker_unresolved); tests.
5. feat(m5): scaffold apps/web (Vite+TS); search → results → detail panel; mentions vs claims
   distinct; disclaimer; source links.
6. test(m5): accusatory-claim fixture + invariant assertions; wire api tests into make test.
7. docs(m5): apps READMEs; Makefile targets; flip §8 step 5 to done; FIX the stale claim
   counts in docs/project-state.md (the 30,274 / "16,915 dropped" / "34% dropped" lines now
   read as the post-ADR-0007 reload, ~46,546 loaded with raw speakers); note the localhost
   demo + the load-qdrant parity pre-flight.
Then STOP and report Changed / Verified / Assumptions / Notes for the human review gate.
```

### Why this is the right next prompt
- M0–M4 are complete and the stores are loaded; M5 is the only thing between the corpus and a
  demonstrable product, and `apps/` does not exist yet (verified).
- It reuses the shaped store classes, so it cannot drift from the canonical models or the
  Mention≠Claim spine, and the legal posture is carried structurally, in tests.
- It is the MVP success test and nothing else — the milestone note says "scope ruthlessly".
  The review UI (M6) and the evidentiary layer (Track B) are explicitly fenced out.
- Two review passes hardened it: the package read seam (`Neo4jStore` had no reads) is now the
  first deliverable, status is read from the graph not hardcoded, both provenance paths are
  handled, and the stale speaker-drop numbers are corrected.
