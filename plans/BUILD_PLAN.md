# Build Plan — Plan of Record

Three Claude Code prompts, where they live, what they generate, and the order to run them.

## Files & repo placement

Prompt docs are version-controlled under `plan/`. The code each one generates lands in the module shown.

| Prompt doc (lives in `plan/`) | Generates | Lands in | Cost |
|---|---|---|---|
| `prompt_repo_ground_truth_audit.md` | `STATE.md` (ground-truth report) | repo root | $0, read-only |
| `prompt_17_cross_model_diff_harness.md` | sampler, diff engine, framing judge, CLI, tests | `eval/` | a few $ (runs with the slice) |
| `video_acquisition_slice_V0-V3.md` | scaffold, manifest, watcher, downloader, transcribe | `video_pipeline/` | transcription compute only |

```
repo/
├── plan/                                   # ← put the three prompt docs here
│   ├── prompt_repo_ground_truth_audit.md
│   ├── prompt_17_cross_model_diff_harness.md
│   └── video_acquisition_slice_V0-V3.md
├── resolution/        (exists)  canonical.py, seed_entities.yaml
├── extraction/        (exists)  schema.py, prompts/extract_v1.md, cache.py, extractor.py
├── cli/               (exists)  extract_corpus.py
├── eval/              ← created by prompt 17
├── video_pipeline/    ← created by the acquisition slice
└── STATE.md           ← created by the audit (run this first)
```

## Execution order

**STEP 1 — NOW. Run the audit.** Read-only, $0, ~5 min. Emits `STATE.md`. This is the gate: it tells you whether the spine is real and answers the video-track question from the filesystem. Do not authorize any paid run until this is read.

**STEP 2 — Confirm the eval harness.** It was reported in-progress. Finish/verify it against `prompt_17` so it's green before the slice.

**STEP 3 — Authorize the slice (Gate-2 path).** Opus, 658 chunks, sync, `--budget-usd 30`, day 31 added to the sample universe, cross-model sample (Sonnet + Haiku + Opus judge). Produces the silver reference + the model-decision data → Gate 2.

**PARALLEL TRACK — ungated by everything above.** Run the video acquisition slice (V0–V3) on a daily cron, stopping at `transcribed`. Banks the perishable daily stream; yields the first content asset (one safe deep-link).

## Branch after STEP 1
- Audit clean → proceed to STEP 2/3 on verified ground.
- Audit surfaces drift (stubbed writer, untested resolver, cache mismatch) → close that gap before any paid run. Every downstream dollar assumes the spine.
