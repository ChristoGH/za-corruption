# extract_v2 — clean reported-speech predicates. Build prompt.

Live per-task prompt (`plans/README.md`). The first buildable step of the Track B
evidentiary layer (`plans/evidentiary-completeness-track.md` §4.1): proposition clustering
needs predicates that open with a reported-speech verb, not bare "he funded…" prose. The
post-run sweep flagged **20,818 predicate-pronoun claims**; ADR 0006 Follow-up 1 drafted the
fix and deferred it to "the next deliberate version bump" — this is that bump.

**This run costs money (~$20 batch, Haiku, re-extracts the whole corpus).** A human
cost-approval gate is required before the paid run — the agent prepares and verifies on a
tiny slice, then stops for sign-off. Do not launch `--all` without it.

---

## Paste the block below into the implementation agent

```
GOAL — Ship extract_v2: make every claim predicate OPEN with a reported-speech verb, so the
extracted claim text reads as testimony ("testified that he helped with the application"),
never as a bare asserted event ("helped with the application"). This is a prompt + schema
version bump, re-extraction, reload, and re-verification. It is defamation-hygiene of
predicate SHAPE only — it never changes claim specificity, names, quotes, or the STATED_BY
structural protection.

NON-NEGOTIABLE CONTEXT — read first
- docs/decisions/0006-post-canary-followups.md, Follow-up 1 — the drafted prompt change and
  the exact new hard rule. This plan implements it verbatim; do not redesign it.
- packages/ingestion/commission_ingestion/extraction/schema.py — PROMPT_VERSION
  ("extract_v1"), PROMPT_PATH (prompts/<version>.md), ExtractedClaim.predicate. The cache key
  is (chunk_id, PROMPT_VERSION, model), so bumping the version self-invalidates the cache and
  forces re-extraction.
- packages/ingestion/commission_ingestion/eval/framing_judge.py — structurally_asserted():
  the deterministic gate. A predicate whose first four words carry no reported-speech verb
  (or a claim with no speaker) is flagged. extract_v2 must drive this floor toward 0.
- reports/postrun_sweep.md + scripts/postrun_sweep.py — the corpus-wide sweep; 20,818
  predicate-pronoun flags today. This is the before/after metric.
- CLAUDE.md investigative-stance + commit discipline.

INVARIANTS
1. Content unchanged, shape only. Do NOT bleach, anonymise, soften, or drop claim content.
   Names, figures, dates, quotes stay at full specificity. Only the predicate's opening verb
   framing changes. The verbatim quote remains the ground truth.
2. No status in extraction. schema.py stays status-free; the graph writer keeps writing
   status="alleged". extract_v2 does not add a status/modality field.
3. Deterministic quote check unchanged. A predicate is a paraphrase; the quote must still be
   an exact (whitespace-tolerant) substring or the claim is flagged, never guessed.
4. Reproducible + cached. Bump the version so re-runs are deterministic; never hand-edit
   cached extractions.

DELIVERABLES, IN ORDER (atomic green commits)
1. feat(m4): add extraction/prompts/extract_v2.md — copy extract_v1.md, then apply the two
   Follow-up-1 edits verbatim:
   - predicate bullet: MUST begin with a reported-speech verb (stated / testified / alleged /
     confirmed / denied / said / claimed / explained / put it to), with the ADR's examples.
   - new hard rule #6: every predicate must OPEN with a reported-speech verb naming the
     speaker's act of asserting; a predicate stating an event directly is malformed — reframe,
     never emit.
   Bump PROMPT_VERSION = "extract_v2" in schema.py. Unit test: the version constant and the
   prompt file resolve; schema unchanged otherwise.
2. test(m4): a fixture asserting structurally_asserted() rejects a bare-predicate claim and
   accepts the reframed one, so the gate encodes the v2 contract.
3. SLICE + STOP FOR COST APPROVAL. Re-extract a small calibration slice only
   (e.g. extract-corpus --days 36,43) under extract_v2, run structurally_asserted() over it,
   and report: structural-flag count before (v1) vs after (v2) on the slice, plus 3-5 concrete
   before/after predicate pairs. Do NOT run --all. Post the slice result and wait for the
   human go/no-go on the ~$20 batch.  <-- HUMAN GATE
4. (after approval) chore(m4): run the paid batch re-extraction of the full corpus under
   extract_v2 (batch mode, ~$20), 0 dead letters; record counts.
5. chore(m4): reload the graph — build-graph --commission madlanga --with-claims — so the
   :Claim nodes carry the v2 predicates. Idempotent MERGE on claim_id; confirm claim count is
   stable and quotes unchanged.
6. docs(m4): re-run scripts/postrun_sweep.py; record the new predicate-pronoun / structural
   count in reports/postrun_sweep.md (expect the 20,818 predicate-pronoun figure to collapse
   and the structural floor to approach 0). Update NEXT.md: extract_v2 done, predicate-prose
   clean, Track B proposition clustering unblocked.
Then STOP and report Changed / Verified / Assumptions / Notes.

ACCEPTANCE
- structurally_asserted() corpus floor approaches 0 (ADR 0006 target); any residual is
  eyeballed and is lexical-strictness, not a bare-event predicate.
- Claim count and quotes unchanged from v1 (shape-only change verified, not just asserted).
- The API /claim and /chunk/graph endpoints now surface reported-speech predicates (the
  web card's paraphrase line reads as testimony) — spot-check one on the running app.

OUT OF SCOPE
- Proposition clustering, stance tagging, Q&A model (the NEXT Track B steps — this only
  unblocks them). No M6 review UI. No new schema fields.

COMMIT & BRANCH DISCIPLINE (scripts/hooks/)
- Branch feat/extract-v2 (never main). Atomic green commits; conventional feat/test/chore/docs
  (mN) messages. NEVER push, NEVER merge to main — stop at the milestone boundary. No LLM
  artifacts, no em dashes.
```

---

### Why this is the right first Track B step
- It is the documented prerequisite (`evidentiary-completeness-track.md` §4.1, ADR 0006
  Follow-up 1): clean predicates before proposition clustering.
- It is bounded and cheap (~$20), with the design already drafted — low risk, high unblock.
- It carries a real human cost gate, matching the project's "cost approval before any paid
  API call" rule — the agent calibrates on a slice, then stops.
- It improves what is already public: the claim cards in the M5 app will read as testimony,
  not bare assertions, the moment the graph reloads.
