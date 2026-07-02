# NEXT — resume here

> Single re-entry point for this project. If you've been away for a while, read this first.
> Rule: keep **Next action** literal (a command or a concrete step), and update **Updated**.
> Vault hub: `knowledge-vault/10-Projects/Commission Intelligence.md`

**Project:** Commission Intelligence — Madlanga evidence graph
**Updated:** 2026-07-02

## Where it stands
- **Corpus loaded:** 49,068 claims extracted (Haiku); **~46,546 loaded** into Neo4j after the
  raw-speaker fallback (ADR 0007) recovered the 34% drop. Qdrant parity **confirmed live:
  17,149 madlanga points** (up from the old 14,783 after the +18 registry records this cycle).
- **M5 public surface BUILT** on `feat/m5-public-surface` (M0–M5 now feature-complete). Thin
  read-only FastAPI (`apps/api`) + React (`apps/web`) over the stores; new `Neo4jStore` reads
  (`chunk_neighborhood`, `claim_detail`, `ping`). `make test` green (168 pass / 1 skip).
  Spec + review history: `plans/m5-public-surface.md`.
- **M5 live demo — search leg PROVEN.** Against live stores, `/search "disbanding of the task
  team"` returns real hits with full provenance (Sibiya day 63, Chair day 3, Mkhwanazi day 2;
  scores ~0.76–0.78). Blocker found + fixed: the `vector` extra (sentence-transformers/torch)
  was not installed, so `/search` 500'd until `uv pip install "sentence-transformers>=3.0"`.
- **Hinge published.** Series A Post #2 LIVE on LinkedIn. Method documented: `METHOD.md`.
- **Commit discipline enforced** (`scripts/hooks/` + CLAUDE.md): atomic green commits,
  conventional `<type>(mN)` messages, never commit to `main`, agent never pushes.

## Next action (literal) — close out M5, then the tracks
Bring the branch to a clean, mergeable state at the human review gate:
1. **Finish the M5 acceptance loop.** Confirm the graph leg on live data:
   `curl -s "http://localhost:8000/chunk/<CID>/graph" | jq '{mentions,claims}'` → mentions and
   claims come back as separate fields, a claim resolves to quote+status+speaker+source. Then
   `make web-install && make web-dev` (localhost:5173) for the visual check.
2. **Land `fix(m5)`:** declare `commission-ingestion[vector]` in `apps/api/pyproject.toml` so
   the API cannot start without its search dependency (this is the gap the demo exposed).
3. **Human review gate → merge** `feat/m5-public-surface` to `main` (human, not the agent).
4. **Then pick a track:** (a) Track B evidentiary layer — proposition + stance + Q&A over the
   claim graph (`plans/evidentiary-completeness-track.md`, LinkedIn Series B); or
   (b) stay-current ingest (`plans/staying-current-pipeline.md`). Track B needs the M6 review
   gate before any named-person output ships — see `docs/track-reconciliation.md`.

## Open / don't-forget
- Qdrant parity: CONFIRMED 17,149 (live). The old "expect ~14,783" note is stale.
- M5 acceptance: web-UI visual pass + chunk/claim leg still to eyeball on live stores.
- `vector` extra undeclared for `apps/api` — see next-action #2.
- Two speaker sources, not 1:1: `/search` returns raw payload labels; `/chunk/graph` returns
  resolved `(:Person)-[:SPOKE_IN]` names — a raw label may have no resolved Person. Expected.
- `extract_v2` predicate-prose fix (pronoun predicates) before public *claim-text* display.
- Neo4j memory — container stopped under load once (bump Docker RAM if it recurs).
- Speaker-drop: RESOLVED via ADR 0007 (raw `:Person` speakers, flagged `speaker_unresolved`).

## Map
- `docs/track-reconciliation.md` — the two tracks (original M0–M6 plan vs post-M4 analytical
  work), where they collide, and why Series B depends on the unbuilt M6 review gate
- `plans/m5-public-surface.md` — the M5 build prompt (apps/api + apps/web; the safe lane)
- `METHOD.md` — public methodology (the "open to scrutiny" front door)
- `plans/staying-current-pipeline.md` — ingest latest + video-only + publish-the-delta
- `plans/evidentiary-completeness-track.md` — the evidentiary framework / LinkedIn Series B
- `plans/post-extraction-roadmap.md` — foundation & coverage (Track A)
- `plans/live-cosmograph-from-neo4j.md` — the live explorer spec
- `docs/decisions/0007-raw-speaker-fallback.md` — the 34% recovery
- `linkedin/series-a-post-2-FINAL.md` — the published post · `reports/` — sign-off & sweeps
