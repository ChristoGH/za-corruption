# Post-extraction roadmap — from claims to value

Written 2026-06-19, right after full-corpus extraction completed. Decision owner: Christo.
This is the map from "we have 14,783 extracted chunks" to the analytical aims: unasked
questions, contradictions, commissioner disputes, coverage gaps, high-value days — and the
next LinkedIn post built on the full corpus instead of a 2-day slice.

---

## 1. Where we are (verified)

**Done.**
- Full Madlanga corpus extracted: **14,783 chunks, Haiku `extract_v1`, 0 dead letters**, in cache.
- Canary v2 signed off (`reports/canary_signoff_triage.md`); §C resolved to **0 graph-level
  misattributions** (`reports/sectionC_bucket1_review.md`).
- Knowledge model documented (`knowledge-model/…taxonomy-ontology.md`); ontology/Qdrant/Neo4j
  models settled in `docs/`.
- Tooling: `scripts/postrun_sweep.py` (the gate), `scripts/recover_batch.py`.
- LinkedIn slice: cosmograph + draft post (2 arbitrary days).

**Deferred but tracked (ADR 0006).**
- `extract_v2` — predicates must open with a reported-speech verb (cleans pronoun prose).
- `turns.py` — fixes the absorbed-witness attribution straddle.
- Post-`--all` corpus-wide sweep (Follow-up 3) — **not yet run; it's the immediate gate.**

**Not built yet.**
- Qdrant not loaded; Neo4j not built. **The claims exist only as cached JSON — there is no
  searchable/queryable store yet.** Everything analytical below depends on this.
- No analysis layer, no Q&A structure modeling, no contradiction index.

---

## 2. Critical path — do in this order, nothing analytical works without it

1. **Run the sweep (the gate).** `uv run python scripts/postrun_sweep.py --model
   claude-haiku-4-5 --expected-chunks 14783`. Read the structural flags; confirm corpus
   genuine-slip rate ≈ 0. This converts the 408-chunk sign-off into a 14,783-chunk guarantee.
2. **Build the stores.** `make stores-up` → `make neo4j-constraints` → `make load-qdrant`
   → `make build-graph` (try `build-graph-dry` first). This is mostly mechanical — the CLIs
   exist — but it's the moment the corpus becomes interrogable.
3. **Verify the MVP loop on the full corpus.** The success test from CLAUDE.md: search Qdrant
   for a topic → open a chunk → jump into Neo4j to see connected people/orgs/places/day, with
   mentions distinguished from claims. Re-run the **Matlala hinge** query across all 106 days
   instead of 2 — that's the proof the foundation holds and the seed of LinkedIn post #2.

Until steps 1–3 are done, the value-extraction work has nothing to run against.

---

## 3. The value-extraction backlog — prioritized by (value × narrative) ÷ (effort × risk)

Three tiers. Do them roughly in order; the early ones build momentum, produce public output,
and carry low defamation risk. The later ones are where the real investigative value is — and
where the framing discipline matters most.

### Tier A — Foundation analytics (low risk, high narrative, start here)

**A1. Coverage map — days with transcripts vs YouTube-only vs missing.**
- *What:* enumerate every official hearing day, cross-reference the source registry
  (`data/sources/source_registry.jsonl`) + downloaded transcripts, and surface the delta:
  which hearing days are in the searchable record, which exist only as YouTube video, which
  are missing entirely.
- *Why first:* low effort (source inventory, no new modeling), **high journalistic value**
  ("here's what the public record doesn't yet contain"), and **near-zero defamation risk** —
  it's about process and availability, not allegations.
- *Output:* a table/chart + a short brief. Directly feeds a LinkedIn post.

**A2. High-value-day ranking.**
- *What:* rank all ~106 days by presence/centrality of key players (graph degree, mention
  counts, bridge/hinge scores) — the cosmograph method generalized from 2 days to the corpus.
- *Why early:* moderate effort (graph analytics on Neo4j), factual ("who testified, when, how
  central"), and it's the natural sequel to the slice post.
- *Output:* a ranked day list + per-day mini-cosmographs for the top days.

### Tier B — Claim-layer analytics (the real value; medium-high risk; needs modeling)

Prereq: a **claims index** (resolved claims with speaker, subject, predicate, quote,
STATED_BY) queryable in Neo4j, and ideally `extract_v2` for clean predicates. Framing
discipline is non-negotiable here — every output is *attributed allegation, not finding*.

**B1. Contradictions & corroborations.**
- *What:* cluster claims by proposition (same subject + predicate + object), compare stance
  across speakers. Corroboration = independent speakers agree; contradiction = opposing
  stance / one asserts, another denies. (We sketched this earlier — proposition clustering +
  modality tags `asserts/denies/qualifies/cannot-recall`.)
- *Risk:* the clustering is a semantic judgement (NLP/LLM-assisted) and surfaces disagreements
  about named people. Output *flags* disagreements for a human to read; it never adjudicates.

**B2. Commissioner disputes — answers challenged from the bench.**
- *What:* claims where a Chairperson/Commissioner turn challenges or questions the witness's
  answer. Detectable via speaker role (the bench) + adjacency/challenge cues.
- *Why valuable:* a commissioner pushing back is a strong signal of contested testimony — a
  curated reading list of the moments that mattered.

### Tier C — Inferential frontier (highest effort & risk; later, research-grade)

**C1. "Questions that should have been asked and weren't."**
- *What:* model the Q&A structure (counsel question → witness answer), then find: assertions
  made but never tested/challenged, topics raised but not followed up, named entities
  implicated but never put to the witness.
- *Why last:* this is genuinely inferential — it's the tool forming a *view* about what
  counsel missed. It needs the full claim+Q&A graph, LLM-assisted reasoning, and **heavy human
  review**, with output framed strictly as "questions the record raises," never as accusation.

---

## 4. Sequencing rationale & risk posture

- **Foundation before analysis:** A-tier and everything else is blocked on the stores (§2).
- **Low-risk public output first:** A1/A2 are factual and process-level — they build the
  audience and the narrative *without* putting attributed allegations into the world before
  the claim layer is hardened. They also stress-test the graph at corpus scale.
- **Claim-layer second:** B1/B2 carry the investigative payload and the legal weight. They
  ride on the structural protection (`STATED_BY`, `status="alleged"`, subject_refs) — content
  stays sharp, qualification lives in structure. Don't ship B-tier publicly until the sweep,
  human review, and `extract_v2` framing are in place.
- **Inference last and carefully:** C1 is the highest-value but most defamation-sensitive —
  it's the tool reasoning about omissions. Build it only on a verified claim graph, with a
  human in the loop on every surfaced item.

---

## 5. The LinkedIn arc

- **Post #2 (next):** upgrade the slice story to the full corpus. Lead with **A1 coverage map**
  ("the whole commission is now searchable — and here's what's still missing") and **A2
  high-value days**. Keep the taxonomy/ontology explainer and the *allegations-not-findings*
  line. This is the "we scaled it" post — concrete, factual, journalist-bait, low risk.
- **Later posts:** the B-tier findings — a contradiction, a commissioner dispute — each as a
  carefully-framed, fully-attributed mini-story with the source chunk. These are the ones that
  get picked up, so they ship only after human review.

---

## 6. Immediate next action

**Run the sweep.** Then we build the stores together and re-run the Matlala hinge across the
full corpus — that single query is both the foundation check and the spine of post #2.

```bash
uv run python scripts/postrun_sweep.py --model claude-haiku-4-5 --expected-chunks 14783
```
