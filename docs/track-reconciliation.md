# Two tracks, and where they collide

Status note, not a decision record. Reconciles the original milestone plan with the
post-M4 analytical work, and records the one dependency that links them. Live status
still lives in `NEXT.md`; the plan-of-record is `docs/project-state.md §8`.

Written 2026-06-30.

---

## The short version

The original plan is **complete up to M4 and abandoned at the product layer (M5/M6)**.
The real frontier moved to a **newer analytical track** that partly substitutes for M5
and partly depends on a review gate M6 was supposed to deliver.

## Track 1 — the original plan (milestones M0–M5 / §8 stages 0–6)

The plan from the start: build the pipeline, then ship a thin **public product** (a
search-to-graph web app — the MVP success test) plus a **human-review workflow**.

| Stage | What | Status |
|---|---|---|
| M0–M3 | repo, parse+chunk, Qdrant, mentions graph | done |
| M4 | claim extraction + corpus-wide load + sweep | done (2026-06-19) |
| M5 / §8 step 5 | `apps/api` (FastAPI) + `apps/web` (read-only page) | **not started — `apps/` not scaffolded** |
| M6 / §8 step 6 | human-review layer (alias/dup resolution, high-risk claim confirmation, export→review→approve, decisions persisted with provenance) | **not started** |
| M-Z | Zondo authoritative source | parked |

Roughly 80% done: the corpus is fully interrogable, but the product surface and the
reviewer workflow that were meant to come next were never built.

## Track 2 — the post-M4 analytical track (written 2026-06-19 onward)

Not in the original milestone plan. Created right after M4 completed; it is where active
work actually went. Different *kind* of work: not "build a generic product," but "extract
investigative value and publish it." It lives in:

- `plans/post-extraction-roadmap.md` — Track A: coverage map, high-value-day ranking.
- `plans/evidentiary-completeness-track.md` — Track B: corroborated / uncorroborated /
  disputed / unanswered / not-asked (LinkedIn Series B). Mostly spec; one per-witness
  prototype built (`scripts/interrogation_gaps.py`, `reports/interrogation_senona.md`).
- `plans/staying-current-pipeline.md` — ingest new days + video.
- `plans/live-cosmograph-from-neo4j.md` — the live explorer.

Most of this has shipped as scripts + LinkedIn posts (the Matlala cosmograph, the Senona
interrogation dossier), not as the M5 product.

## The collision (the part worth noticing)

The two tracks are not just parallel — they meet at one dependency.

The original plan expected **M5 (the product) next**; instead the work leapfrogged into
Track 2's analysis. But Track 2's riskiest output — **Series B: named-person disputes and
"questions that should have been asked"** — depends on the **human-review layer the
original plan (M6 / §8 step 6) never built.** That gate is a prerequisite the old plan
defined and the new plan now needs.

### Why Series B is the riskiest output

It is a question of *what kind of speech act each output is*, and which the law protects.

- **The safe lane (where M5 lives): republication under public-record privilege.**
  Faithfully republishing what a named witness said under oath — attributed, with a
  page-cited source — is a fair-and-accurate report of public proceedings (the Bogoshi
  reasonableness standard). The platform asserts nothing; it quotes the record. M5's
  product surface lives entirely here, which is why M5 is low-risk and does **not** need M6.

- **Series B leaves that lane: system-originated imputations.** These are the platform's
  own conclusions about named (often private) individuals, not republication:
  - *Disputed / contradiction* — the platform asserts that two named people conflict.
  - *Uncorroborated* — flagging a damaging allegation as single-source risks implying it
    is false.
  - *Not-asked / should-have-been-asked* — the platform forms a **view about an omission**
    (counsel failed, a party was shielded). `plans/evidentiary-completeness-track.md`
    rates this state **highest risk** — it is an inference the record does not state.

  Public-record privilege does **not** shield the platform's own editorial conclusions.
  That is the legal step-change between Track 1's product and Track 2's findings.

### Why the dependency is specifically the M6 human-review layer

1. **Entity-resolution correctness.** A dispute or not-asked finding pinned to the wrong
   "Khumalo" (four distinct Khumalos in this corpus) attaches one person's allegations to
   another — a misattribution that is itself defamatory. The no-auto-merge policy requires
   a human to confirm identities. That confirmation step is M6.
2. **An auditable approval gate.** Series B is synthesis, so before any named-person item
   is published it needs a confirm/flag round-trip and a "reviewed" status that publication
   can be gated on, with each decision persisted with provenance — the export→review→approve
   path M6 (M4's review AC, §8 step 6) was meant to deliver. Without it there is no
   defensible approval trail for system-originated claims.

(Separately, the "not-asked" / absence findings also require the ingestion-completeness
audit — the 119-vs-106 day gap — to close first, so an apparent absence is not just an
extraction artifact. That is a second gate, distinct from the M6 dependency above.)

## Implication for sequencing

- **M5 can proceed now**, independently — it only republishes attributed testimony with
  provenance, the low-risk lane. See `plans/m5-public-surface.md`.
- **Series B cannot ship for named individuals until M6 (human-review) exists** and a
  media-lawyer pass is done — and not-asked findings additionally wait on the
  ingestion-completeness audit.
- So the honest near-term order is: finish M5 (product, safe) → build M6 (the review gate)
  → then Track B's evidentiary findings become publishable, not before.
