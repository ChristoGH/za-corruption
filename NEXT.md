# NEXT — resume here

> Single re-entry point for this project. If you've been away for a while, read this first.
> Rule: keep **Next action** literal (a command or a concrete step), and update **Updated**.
> Vault hub: `knowledge-vault/10-Projects/Commission Intelligence.md`

**Project:** Commission Intelligence — Madlanga evidence graph
**Updated:** 2026-06-23

## Where it stands
- **Corpus loaded:** 14,783 chunks, 49,068 claims extracted (Haiku); **46,546 claims loaded**
  into Neo4j after the raw-speaker fallback (ADR 0007) recovered the 34% drop.
- **Hinge published.** Series A Post #2 is **LIVE on LinkedIn** (Matlala 62/106 days; Senona &
  Sibiya flagged *contested*). Visual: `linkedin/matlala_live_cosmograph.html`.
- **Method is now documented** for public scrutiny: `METHOD.md`.
- **Commit discipline enforced** (`scripts/hooks/` + CLAUDE.md): atomic green commits,
  conventional `<type>(mN)` messages, never commit to `main`, agent never pushes.

## Next action (literal) — two active tracks
1. **Stay current** (`plans/staying-current-pipeline.md`). Start now:
   `make retrieve-discover && make retrieve-download` → parse/extract/build-graph the new days.
   Then build `make ingest-latest`, the video-only (Whisper) path, and the "what day N added" delta.
2. **Evidentiary framework — bring it to the fore** (`plans/evidentiary-completeness-track.md`).
   This *is* the corroborated / uncorroborated / contested-disputed / unanswered / not-asked
   framework. Next build: the proposition + stance layer it needs (turns deny/assert/question
   into a real accuser-vs-defender model). This is LinkedIn Series B.
3. Engage the published post (first comment = method link to `METHOD.md`; @-mention outlets).
4. Optional integrity step: `scripts/validate_graph.cypher` + `make validate` (the "graph types
   for Community" schema sweep) wired into CI.

## Open / don't-forget
- Qdrant load parity still unverified: `curl -s localhost:6333/collections/commission_transcripts | jq '.result.points_count'` (expect ~14,783).
- `extract_v2` predicate-prose fix (42% pronoun predicates) before public *claim-text* display.
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
