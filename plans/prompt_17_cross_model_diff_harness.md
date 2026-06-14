# Prompt 17 — Cross-Model Diff Harness (slice-embedded, Gate 2 input)

## Context

The full-corpus model choice (Opus $200–210 / Sonnet $120–125 / Haiku $40, all batch) is currently a guess about quality degradation. This harness turns it into a measurement. It runs **inside the slice motion, before Gate 2**: the 658-chunk slice is extracted on Opus (the silver reference), then a small stratified sample is re-extracted on Sonnet and Haiku and diffed against the Opus reference along the axes this corpus actually fails on — the four Khumalos, OCR-variant counsel names, acronym density, and above all the neutral reported-speech framing the defamation posture rests on.

The output is a Gate 2 decision-support artifact, not an automated decision. A human makes the model call; this harness makes the call measurable.

## Invariants (do not violate)

- **Do not modify** `extractor.py`, `cache.py`, `schema.py`, `canonical.py`, or `extract_v1.md`. The harness *consumes* them. If something needs a seam (e.g. injecting the model string), add the minimal parameter, do not refactor.
- **One variable only.** Identical `extract_v1` prompt and identical schema across all three models. The sole difference between arms is the model string. No per-model prompt tweaks, no per-model schema relaxation.
- **One frozen sample.** The same chunk-id set is sent to all three models. No per-model resampling.
- **Cache-aware, no dollar re-spent.** Reuse the model-keyed `(chunk_id, prompt_version, model)` cache. If the slice ran first, the Opus arm must be cache hits. Sonnet/Haiku arms cache too, so a re-run is free.
- **Budget-respecting.** `--budget-usd` is a hard cap with clean checkpointing. `--estimate-only` makes **zero** API calls.

## Deliverables

1. `eval/sample.py` — stratified, seeded sampler.
2. `eval/compare.py` — resolution-aware, framing-aware diff engine.
3. `eval/framing_judge.py` — constant-judge claim-framing classifier.
4. `cli/cross_model_eval.py` — orchestration CLI.
5. `eval/artifacts/` — `gate2_model_review.md`, `metrics.json`, `hardcase_appendix.md`.
6. Tests: sampler determinism + compare metrics against a small fixture.

## Detail

### `eval/sample.py`
Stratified sample (default n≈40), seeded and **frozen to disk** as an auditable chunk-id list (`eval/artifacts/sample_<seed>.txt`). Strata, drawn from the slice's chunk set so the Opus arm is guaranteed cacheable:
- **Ambiguous-surname** chunks — contain a bare surname flagged ambiguous in the canonical store (Khumalo et al.).
- **OCR-variant** chunks — contain a counsel surface form that only resolves via an alias-index entry.
- **High-acronym-density** chunks — above a configurable acronym-per-token threshold (SAPS/PKTT/IPID-class).
- **Allegation-dense** chunks — high claim/reported-speech density (this is where framing slips show up).
- **Control** — low-complexity chunks, to establish a baseline agreement rate.
Same seed → identical sample, every run. Record which stratum each chunk came from (the appendix needs it).

### `eval/compare.py`
Opus is the reference. For each non-Opus model, per chunk and micro-averaged:
- **Completion rate** — chunks that parsed without refusal/dead-letter. A model that dead-letters allegation-dense chunks is disqualified regardless of agreement elsewhere; surface this first.
- **Entity agreement (post-resolution)** — run every model's mentions through `canonical.py`, compare the resulting **canonical-ID sets** (not raw strings) against Opus. Report precision / recall / F1, broken out separately for the hard-case strata vs control.
- **Fragmentation count** — mentions that fall through to a raw string instead of resolving. This is the OCR-variant / messy-surface-form signal; a higher count means a dirtier graph.
- **Claim recall/precision vs Opus** — soft-match claims on (subject canonical ID + predicate similarity); count dropped and invented claims.

### `eval/framing_judge.py`
The defamation-critical axis. Two passes:
- **Structural (deterministic, cheap):** flag any claim whose attribution/speaker field is null or whose predicate asserts directly. Pre-filter, no API cost.
- **Judged (constant judge):** classify each claim as `neutral_reported | asserted_as_fact | ambiguous` with a one-line rationale. **The judge is a single fixed model (Opus) applied identically to all three arms** — this keeps it fair (no model judging itself) and the comparison apples-to-apples. Headline metric: per-model `asserted_as_fact` rate. One framing slip on Haiku is worth more in the decision than a dozen entity misses.
Judge cost counts against `--budget-usd` and is reported as its own line.

### `cli/cross_model_eval.py`
Flags: `--models opus,sonnet,haiku`, `--sample-size`, `--seed`, `--from-slice` (draw sample from the existing slice chunk set so Opus is cache hits), `--budget-usd`, `--estimate-only`. Flow: sample → extract each arm via the existing extractor (cache-first) → compare → judge → write artifacts. Per-arm measured `$/chunk` from the extractor's cost accounting, projected to 14,783 chunks, printed beside the quality deltas.

### Artifacts
- `gate2_model_review.md` — per-model scorecard (completion, entity P/R/F1 overall + hard-case, fragmentation, claim P/R, framing-slip rate, measured $/chunk, projected full-corpus cost), then a **recommendation scaffold** that states the tradeoff for the human ("Sonnet saves ≈$85 at the cost of N framing slips and M fragmentations on the hard cases") **without auto-selecting**.
- `hardcase_appendix.md` — side-by-side extractions for each hard-case chunk across the three models, so the reviewer can eyeball whether Haiku actually conflated two Khumalos or dropped a reported-speech frame.
- `metrics.json` — machine-readable, for trend tracking across future re-runs.

## Acceptance criteria

- [ ] `--estimate-only` makes zero API calls and prices all three arms + the judge pass.
- [ ] Given a fixed seed, the sample is byte-identical across runs and frozen to disk.
- [ ] With the slice already extracted, the Opus arm is 100% cache hits (verified in the spend log: $0 added for Opus).
- [ ] Re-running the full eval adds $0 (all arms cached).
- [ ] `--budget-usd` halts cleanly at the cap with a resumable checkpoint; no partial-write corruption.
- [ ] All three arms use identical prompt + schema; only the model string differs (assert in code).
- [ ] `gate2_model_review.md` contains every axis above plus the non-deciding recommendation scaffold; `hardcase_appendix.md` shows per-stratum side-by-sides; `metrics.json` validates.
- [ ] Tests green: sampler determinism, and compare metrics produce known values on the fixture.

## Cost note
Sonnet + Haiku on ~40 chunks each plus an Opus judge pass over the union of claims ≈ a few dollars. That buys the difference between choosing the full-corpus model and measuring it.
