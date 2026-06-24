# 0006 — Post-canary deferred follow-ups (framing-verb + attribution)

- **Status:** Accepted
- **Date:** 2026-06-16
- **Scope:** Two known data-quality items surfaced by the v2 pre-flight canary
  (`reports/preflight_canary.md`, triaged in `reports/canary_signoff_triage.md`).
  Both were **deliberately deferred** at Tier-3 sign-off so the full Haiku extraction
  run (`extract-corpus --all --batch`) could ship.
- **Governs:** what is *not* fixed before the full corpus run, why that is safe, and the
  exact follow-up each item needs. Neither is a gate; both are data-quality, not
  defamation.

## Context

The canary passed all structural tiers (GREEN): idempotent load, no claim-MERGE-key
doubling, no silent subject detachment, provenance intact, no fact edges. The only open
items at sign-off were two content/parser issues. Per `CLAUDE.md` (93–102), defamation
protection is **structural, not lexical** — both items below concern *predicate shape*
and *speaker attribution*, never the specificity or content of claim text, and neither
weakens the `STATED_BY` structural protection.

Sign-off decision: **ship `--all` as-is**, fix both in scheduled follow-ups.

## Follow-up 1 — `extract_v2`: predicate must open with a reported-speech verb

**Problem.** The deterministic `structurally_asserted()` check
(`eval/framing_judge.py`) flags a claim whose predicate's first four words contain no
reported-speech verb (or which has no speaker). The canary's net-new slice produced
**9 such structural flags across 1,214 judged claims**; exactly **1** of them lands in
the defamation-critical §B asserted-as-fact list:

| Chunk | Speaker | Predicate | Quote |
|---|---|---|---|
| d36 pp37-39 `fb8ad958578016f4` | Brown Mogotsi | `helped with the application` | "Not funded, he helped that time" |

The remaining ~82 §B flags are judge *lexical*-strictness (embedded that-clause asserts
fact while the predicate still carries `stated that…/testified that…`) — doctrine-
compliant content, not defects. The 8 other deterministic structural flags sit elsewhere
in the corpus under non-asserted judge labels.

**Why deferred, not fixed now.** The single slip is already protected by its `STATED_BY`
edge, so it is safe in the graph. The fix changes the extraction prompt, which means
bumping `PROMPT_VERSION` (`extraction/schema.py`, currently `"extract_v1"`) →
`"extract_v2"` — and the cache is keyed by `(chunk_id, PROMPT_VERSION, model)`, so a new
version **re-extracts the whole corpus at Haiku rates** (~$20 batch). Not worth a second
full run for 1-in-93; batch it into the next deliberate version bump.

**The fix (drafted, ready to apply at v2):**

- Predicate bullet → make the opening verb mandatory, not stylistic:
  > `predicate`: a neutral reported-speech summary, always framed as testimony. It MUST
  > begin with a reported-speech verb — stated / testified / alleged / confirmed /
  > denied / said / claimed / explained / put it to — e.g. "stated that he received an
  > instruction from X to disband the unit", never a bare predicate like "helped with
  > the application" (write "testified that he helped with the application"). The verb
  > names who is asserting; the underlying fact is never asserted in your own voice.
- New hard rule #6:
  > Every `predicate` must OPEN with a reported-speech verb naming the speaker's act of
  > asserting. A predicate whose first words state an event directly is malformed —
  > reframe it, never emit it.

**Acceptance.** Re-canary after the bump: deterministic `structural_flags` floor → 0;
net-new asserted-as-fact rate re-measured. Cache makes the *judge* re-run cheap; the
*extraction* re-run is the ~$20 batch cost noted above.

## Follow-up 2 — `turns.py`: absorbed-witness attribution straddle

**Problem.** Attribution bucket-1 (model-vs-turn speaker mismatch) was 49 on the canary
slice. **~46/49 are the same shape:** the model assigns the *witness* as speaker while
the turn parser assigns *counsel* (Sello / Chaskalson / Baloyi), because the supporting
quote opens inside counsel's turn (counsel puts a proposition the witness then adopts —
e.g. "you reported to…", "your foundation interdicted…"). Model is likely right, parser
is wrong. Bucket-2 (643, all `jd-mkhwanazi`) is the related parser gap from absorbed
COMMISSIONER turns.

**Why deferred, not fixed now.** This is a parser/segmentation issue, not extraction or
graph correctness, and it is already tracked against the **`turns.py` re-chunk
milestone** (`docs/preflight-canary-v2.md`, `docs/milestone-plan.md`). Resolving it at
ingestion is cleaner than patching downstream. On the post-step-A sample, bucket-1 falls
to ≈5 (rate ≈0.051), confirming most of it is the straddle.

**Acceptance.** After the `turns.py` milestone lands, re-run attribution on the canary
slice: bucket-1 absorbed-witness cases resolve at segmentation time; bucket-2
`jd-mkhwanazi` parser gap closes.

## Follow-up 3 — post-`--all` corpus-wide safety sweep (acceptance gate)

**Problem.** The canary sign-off measured framing/attribution safety on the 408-chunk
slice (genuine-slip rate 1/1,214 ≈ 0.08%; §C content slips 2/1,214 ≈ 0.16%). `--all` is
14,783 chunks. The guarantee must be *confirmed* corpus-wide, not extrapolated — and the
detectors are deterministic and free.

**Acceptance.** After `extract-corpus --all` completes, before any `build-graph`/publication:

1. Run `structurally_asserted()` over **every** extracted claim (deterministic, $0).
2. Run the **subject_ref-vs-quote scan** over every claim — confirm the structured
   `subject_refs` (which build the graph) match the quote's subject corpus-wide. NB: on the
   canary the two predicates this flagged (`987fc61d…` funder, `3ccf0352…` de-facto-Chief)
   had **correct** `subject_refs` — the issue was predicate *prose* pronouns, an `extract_v2`
   item, not a structural misattribution. The scan is belt-and-suspenders, not a gap in
   `structurally_asserted()`.
3. PASS iff corpus genuine-slip rate ≤ 0.2% **and** every flagged claim is reviewed. A claim
   with a genuinely wrong `subject_ref` imputing wrongdoing/causation to a named party is
   remediated (fix subject_ref / re-attribute / drop) before graph-load — not cleared by
   averaging. Predicate-prose pronoun cases route to `extract_v2` (Follow-up 1), not a block.
4. Record sweep counts + reviewed claims as the corpus-level audit trail.

Gates: graph-load & publication, **not** the extraction run. Owner: Christo.
Slice precedent: `reports/sectionC_bucket1_review.md` — §C genuine graph-level misattribution
was **0**; carry forward the predicate-prose pattern as an `extract_v2` known case.

## Consequences

- The full `extract-corpus --all --batch` run proceeds under `extract_v1` predicates;
  the 1 §B slip ships as a correctly-attributed `:Claim` (safe per structural doctrine).
- Graph-load is gated on the Follow-up 3 corpus-wide sweep (structural + content-faithfulness),
  not just the slice sign-off.
- Both fixes are re-extraction / re-chunk events, sequenced together to avoid a second
  paid full run for either alone.
- This ADR is the tracked home for both items so they are not lost once the batch run
  starts. Close each section when its acceptance check passes.
