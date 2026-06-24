# Evidentiary Completeness Track — analytical spec & LinkedIn series B

Postmarked 2026-06-19. Owner: Christo. Status: spec (not yet built).
A second analytical track, distinct from the foundation/coverage track in
`plans/post-extraction-roadmap.md`. Where that one asks *who connects whom*, this one asks
**what is the evidentiary state of each answer** — corroborated, uncorroborated, disputed,
unanswered — and where the gaps are. It rides on the claim layer (`:Claim`, `STATED_BY`,
`SUPPORTED_BY`) + Qdrant semantic search.

> Governing rule, unchanged: every output is an **allegation attributed in the public
> record, not a finding of fact**. Uncertainty lives in structure (`status`, `attribution`,
> `confidence`), never in softened text. "Questions raised," never "accusations."

---

## 0. The prerequisite layer (what must exist first)

These analyses need three things the current graph doesn't fully have yet:

1. **A proposition index.** Cluster claims by *what they assert* — normalised
   subject + predicate + object — so "Matlala funded the application" and "the application
   was funded by Matlala" land in one proposition. (Needs `extract_v2` clean predicates;
   LLM-assisted clustering with human review.)
2. **A Q&A turn model.** Pair counsel/chair *question* turns with witness *answer* turns
   (adjacency in the transcript). Without this, "unanswered" and "should-be-asked" can't be
   computed. The `SPOKE_IN` + `Chunk` ordering is the raw material.
3. **Stance tagging.** Each claim/answer tagged `asserts | denies | qualifies |
   cannot_recall | puts_to_witness`. This is the axis that separates corroboration from
   dispute. (LLM-assisted, the §B framing-judge pattern, human-reviewed.)

---

## 1. The core typology (the six states)

For each: definition → method → output → risk.

### 1a. Corroborated answer
- **Def:** a proposition asserted by ≥2 *independent* speakers (and/or backed by a document
  / `:Finding`).
- **Method:** group claims by proposition; count distinct `STATED_BY` speakers; flag where
  ≥2 independent + same stance. Strength tiers: testimony×1, testimony×2+, testimony+document.
- **Output:** ranked corroboration list; per-proposition "who backs it" panel.
- **Risk:** low — corroboration *strengthens* without asserting truth. Still "attributed."

### 1b. Uncorroborated answer
- **Def:** a proposition asserted by exactly one speaker, never independently restated.
- **Method:** single `STATED_BY`, no corroborating proposition, no supporting document.
- **Output:** "stands alone" list — the claims resting on a single voice.
- **Risk:** medium — naming a damaging single-source allegation; frame as *uncorroborated*,
  not *false*. Absence of corroboration ≠ untruth.

### 1c. Disputed answer
- **Def:** a proposition with opposing stances — one asserts, another denies/contradicts —
  **or** challenged from the bench (a Chairperson/Commissioner turn pushing back).
- **Method:** proposition cluster with conflicting stance tags; or speaker-role = bench +
  challenge adjacency to a witness answer.
- **Output:** the contested-testimony reading list; per-dispute for/against/recall tally.
- **Risk:** medium — surfaces conflict between named people. Show both sides, attributed.

### 1d. Unanswered question
- **Def:** a question put to a witness that received no responsive answer (deflected,
  "I don't recall," ran out of time, never returned to).
- **Method:** Q&A model — question turns with no matching responsive answer turn; or answer
  stance = `cannot_recall` / non-responsive.
- **Output:** the "left on the table" list, per witness/day.
- **Risk:** low–medium — it's about *process*, not allegation. Strong journalistic signal.

### 1e. Questions that should be asked (to complete the evidence)
- **Def:** gaps the record itself implies — a proposition asserted but never tested, a named
  party implicated but never put to a witness, a dangling thread.
- **Method:** inferential — propositions with no challenge/corroboration; entities mentioned
  in claims but never a `subject` of a question; chains with a missing link.
- **Output:** a researcher's "open questions" brief.
- **Risk:** **highest** — this is the tool forming a *view* about omissions. Frame strictly
  as "questions the record raises"; heavy human review; never an accusation of cover-up.

### 1f. Inadvertent answers (the cross-reference showpiece)
- **Def:** an answer given by witness B (day Y) that addresses a question left *unanswered*
  by witness A (day X) — the corpus answering its own open questions across time.
- **Method:** embed each unanswered question (1d) in Qdrant; semantic-search the full answer
  corpus for responsive passages on other days; rank candidate matches for human confirmation.
- **Output:** "the corpus answered this" pairings — open question ↔ later answer, with both
  sources.
- **Risk:** medium — the *match* is a semantic suggestion, confirmed by a human, framed as
  "may bear on," never "proves."

---

## 2. Other angles worth extracting (brainstorm)

- **Shifting testimony** — one witness whose answer on a topic changes across days
  (intra-witness contradiction over time). High value, deterministic once propositions exist.
- **Triangulation strength** — explicit tiers: single testimony < multi-witness < testimony
  corroborated by a document/exhibit < matches a `:Finding`/court outcome.
- **Asymmetric naming** — A implicates B repeatedly; B never addresses A. One-directional
  implication is a lead.
- **Non-denial / unrebutted** — a damaging proposition put to a witness who does not deny it.
  Powerful but the *most* defamation-sensitive; frame as "not rebutted in the record," never
  "admitted."
- **Promissory testimony** — "X will deal with this," "that will be covered later." Did the
  promised evidence ever arrive? Forward-reference fulfilment.
- **Recantations / withdrawals** — claims later withdrawn (e.g. the "I am withdrawing the
  fraud" line). A `status` lifecycle, not a deletion.
- **Document/exhibit gaps** — claims referencing exhibits/MOUs/reports not in the corpus —
  what evidence is cited but absent.
- **Timeline conflicts** — events with dates assembled into a chronology; flag impossible or
  contradictory sequences.
- **Corroboration network** — a who-backs-whom graph between witnesses (the trust topology).
- **Contested-evidence concentration** — overlay dispute/uncorroborated density onto the
  high-value-day ranking: *where* the contested evidence clusters.
- **Directed chains** — follow-the-instruction / follow-the-money: payment and instruction
  claims linked into directed paths (always `alleged`).
- **Status escalation** — claims that later match a commission `:Finding` or court outcome —
  the allegation→finding lifecycle, tracked, never overwritten.

---

## 3. LinkedIn Series B — "Reading the evidence"

Distinct from Series A (the "we built it / coverage / high-value days" track). Series B is
about the *method of evidentiary reading* — the investigative payoff. Each post = one state,
one carefully-framed, fully-attributed example with its source chunk. Ships only after human
review.

- **B1 — Not all testimony is equal.** The framework: corroborated vs uncorroborated vs
  disputed, and why a graph can tell them apart. (Sets up the series; low risk.)
- **B2 — Corroborated vs standing alone.** A claim three witnesses back vs one resting on a
  single voice — same topic, different evidentiary weight.
- **B3 — Disputed.** Where witnesses (or the bench) clash on the same proposition.
- **B4 — The unanswered question.** What counsel left on the table — process, not allegation.
- **B5 — The accidental answer.** One witness answers another's open question, days apart —
  the corpus closing its own loop. *The showpiece; most shareable.*
- **B6 — What should have been asked.** The inferential frontier. Most sensitive; publish
  last, most heavily reviewed, framed strictly as questions the record raises.

**Cadence/framing:** one post per state, paced; every claim attributed (speaker, day, page),
every post carries the allegations-not-findings line; B-tier examples human-reviewed before
publication; lead with the method, let the example illustrate.

---

## 4. Build order (when this track is picked up)

1. `extract_v2` (clean predicates) → enables proposition clustering.
2. Proposition index + stance tagging (LLM-assisted, human-reviewed).
3. Q&A turn model (question ↔ answer adjacency).
4. States 1a–1c (corroborated / uncorroborated / disputed) — deterministic once 1–3 exist.
5. States 1d (unanswered) → 1f (inadvertent answers, via Qdrant) → 1e (should-be-asked).
6. Series B drafts, each gated on human review.

Depends on the foundation track's stores being live (they now are) and on the claim-layer
speaker-coverage fix (the 34% `speaker_unresolved` drop) for full-corpus completeness.
