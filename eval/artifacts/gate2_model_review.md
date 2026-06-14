# Gate 2 — cross-model extraction review

_Generated 2026-06-12T18:10:50.180770+00:00 · sample n=40 (seed 17) · prompt extract_v1 (sha abcd542d69f7) · reference: claude-opus-4-8 · judge: claude-opus-4-8 (US$1.29)_

Strata: allegation_dense=8, ambiguous_surname=8, control=8, high_acronym=8, ocr_variant=8

| model | completion | entity F1 (hard) | entity F1 (control) | fragmentation | claim recall | claim precision | asserted-as-fact rate | $/chunk | full corpus (batch) |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-4-5 | 100% (40/40) | 0.660 | 0.533 | 187 | 0.490 | 0.550 | 0.0429 | $0.0055 | $40.37 |
| claude-opus-4-8 (reference) | — | — | — | — | — | — | 0.1274 | $0.0381 | $281.79 |
| claude-sonnet-4-6 | 100% (40/40) | 0.696 | 0.500 | 202 | 0.497 | 0.494 | 0.1076 | $0.0140 | $103.65 |

## Reading guide

- **Completion** below 100% means refusals/dead-letters; a model that fails allegation-dense chunks is disqualified regardless of agreement elsewhere.
- **Entity F1** is post-resolution (canonical-ID sets vs the reference), split hard-strata vs control. **Fragmentation** counts mentions that fell through to raw strings — a dirtier graph.
- **Claims** are soft-matched on subject canonical-ID overlap + predicate similarity; dropped/invented counts are in metrics.json.
- **Asserted-as-fact rate** is the defamation-critical axis, classified by a constant Opus judge across all arms (including the reference). One framing slip outweighs a dozen entity misses.

## Decision scaffold (human call — intentionally not auto-selected)

- **claude-haiku-4-5** saves ≈US$241 on the full batch burn at the cost of: 80 dropped / 63 invented claims, 187 fragmented mentions, hard-case entity F1 0.660, and 6 asserted-as-fact framings (vs 20 on the reference). See hardcase_appendix.md before deciding.
- **claude-sonnet-4-6** saves ≈US$178 on the full batch burn at the cost of: 79 dropped / 80 invented claims, 202 fragmented mentions, hard-case entity F1 0.696, and 17 asserted-as-fact framings (vs 20 on the reference). See hardcase_appendix.md before deciding.

Reference full-corpus batch cost: ≈US$281.79. Approve a model and budget at Gate 2 to proceed.
