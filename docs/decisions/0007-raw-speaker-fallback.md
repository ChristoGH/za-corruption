# 0007 — Raw-speaker fallback for the `:Claim` writer

Status: accepted · 2026-06-19 · Owner: Christo
Supersedes the "drop speaker-unresolved claims" behaviour of ADR 0005's writer.

## Context

The corpus-wide claim load (2026-06-19, `build-graph --with-claims`) wrote **30,274 of
49,068 claims**. The single largest loss was **16,915 claims (34%) dropped on
`speaker_unresolved`** — the claim's speaker label did not resolve to a seeded `:Person`,
so `build_claim_rows` had no `STATED_BY` target and dropped the claim.

This is asymmetric with subjects: ADR 0005 policy-(b) keeps a claim whose *subject* is
unresolved (recorded as a raw surface on the claim), but an unresolved *speaker* killed the
whole claim. The dropped speakers are real, attributable voices the seed simply doesn't list
— "WITNESS C", "BRIGADIER MATJENG", "SERGEANT NKOSI", many "COMMISSIONER \<surname\>" labels.

Losing a third of the evidence blocks the evidentiary-completeness track (Track B —
corroboration, dispute, who-accuses-whom), which needs the full cast of speakers.

## Decision

**Extend policy-(b) to speakers.** When a claim's speaker label does not resolve:

- If the label is **non-empty**, keep the claim with a **raw, uncanonicalised `STATED_BY`**:
  `speaker_id = "raw:" + LABEL` (claim-key input), `:Person {name: <raw label>}`, and the
  claim is flagged `speaker_unresolved = true`.
- If the label is **genuinely empty**, the claim is still dropped (no attribution possible).
- The `claims_speaker_unresolved` counter is retained but now means **"loaded with a raw
  speaker"**, not "dropped". The build summary reflects this ("Claims w/ raw speaker").

This is **not** a merge and does not violate the human-owned-resolution principle (§6.8):
a raw `:Person {name:"WITNESS C"}` is a distinct, clearly-flagged node, never auto-merged
into a canonical entity. A later seed addition reconciles it deliberately.

**Operative rule for publication/review:** a claim's `speaker_unresolved=true` flag marks
attribution as *uncanonicalised but present* — safe to count and traverse, but flagged for
human canonicalisation before it is presented as a named individual's testimony.

### Alternative considered (rejected)

*Property-only* (record the raw label on the claim, no `STATED_BY` edge) — more literally
parallel to subject policy-(b), but it makes "group claims by speaker" non-traversable,
which Track B needs. Rejected in favour of the raw `:Person` node.

## Consequences

- Claim coverage rises from ~62% to ~96% of extracted claims on reload — no re-extraction
  (claims are cached); a `build-graph --with-claims --force` reload is all that's required.
- `:Person` now contains raw, flagged speaker nodes alongside canonical ones. Queries that
  must restrict to canonical speakers filter on `cl.speaker_unresolved = false`.
- Reconciliation path: add a raw speaker's true identity to `seed_entities.yaml`; the next
  load resolves it canonically (the raw node is left behind and can be swept).
- Test `test_claim_speaker_unresolved_loads_raw_and_counted` replaces the old skip assertion.

## Acceptance

- `build-graph --commission madlanga --with-claims --force` reload shows
  `Claims written` ≈ 47k+ (was 30,274) and a non-zero "Claims w/ raw speaker".
- `MATCH (cl:Claim) WHERE cl.speaker_unresolved RETURN count(cl)` ≈ 16,915.
- Canonical-only views use `WHERE cl.speaker_unresolved = false` (or the resolved `:Person`).
