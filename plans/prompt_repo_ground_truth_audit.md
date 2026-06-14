# Prompt — Repo Ground-Truth Audit (read-only, $0)

## Context

Do not trust summaries, task lists, prior HANDOFF notes, or plan documents. They describe intent, not state. Your job is to report what this repository *actually contains right now*, distinguishing four levels for every component: **absent → scaffolded (file exists, no real logic) → implemented (real logic) → wired+tested (reachable end-to-end with passing tests)**. Every status you report must be backed by an evidence line — a path with line count, a test name with pass/fail, a row/record count — not an assertion. If you cannot find evidence, say "no evidence found," never "probably done."

The single highest-value question: **is the `video_pipeline/` module real code, or is the only video artifact a markdown prompt plan?** Answer it categorically.

## Invariants

- **Read-only.** Do not edit, create, or delete any repo file. The only file you write is `STATE.md` at repo root.
- **Zero paid API calls.** If you run anything, it is `--estimate-only` / dry-run only. No extraction, no ingestion.
- **Evidence over vibes.** "Implemented" requires you to have read the logic. "Tested" requires you to have run the tests and seen them pass.

## Procedure

1. **Inventory.** Full tree excluding `.venv`, `data/`, `cache/`, `__pycache__`, `.git`. For every Python module: line count, and a stub-scan flagging files that are only `pass` / `NotImplementedError` / `TODO` / `...` / docstring. A 12-line file claiming to be `extractor.py` is scaffold, not implementation — call it.

2. **PDF/extraction track reality.** For each of `resolution/canonical.py`, `resolution/seed_entities.yaml`, `extraction/schema.py`, `extraction/prompts/extract_v1.md`, `extraction/cache.py`, `extraction/extractor.py`, `cli/extract_corpus.py`: confirm it imports cleanly, summarise what its logic actually does (one line, from reading it), and list any tests covering it with their pass/fail. Run `extract-corpus --estimate-only` (zero calls) and report the chunk counts it actually sees for the slice and full corpus. Confirm the registered entry points exist and are invocable.

3. **Pipeline data state — interrogate the stores, not the code.** How many extraction records are in `data/cache/extraction/`? What is the total in the spend/audit log (the report claims ~$0.08)? What is in the dead-letter JSONL? Row counts by status in the SQLite registry/manifest. If Neo4j/Qdrant connections are configured, report node/point counts; if not reachable, say so — do not assume empty.

4. **Video track reality check — the question.** Does `video_pipeline/` exist as importable Python? For each of the 11 planned stages (scaffold, manifest, watcher, downloader, transcribe, speakers, chunker, extract, ingest_qdrant, ingest_neo4j, orchestrator), classify absent / scaffolded / implemented / tested with evidence. State explicitly whether the only video artifact found is the prompt plan markdown. "A plan exists" must be reported as **plan-only, no code** unless code is found.

5. **Git truth.** `git status` (is anything uncommitted?), `git log --oneline -20`, and the delta between committed tree and working tree. The report claims "nothing committed" — verify or refute it.

6. **Gap list.** Diff the project's claimed task state (3 done / 1 in-progress / 5 open, plus whatever the tracker says) against what the repo actually supports. Flag any task marked **done** whose artifacts are missing, stubbed, or untested — those are the dangerous ones.

## Output: `STATE.md`

Structured as: a per-component table (component | level | evidence), then the four numbered findings sections above, then a closing **"True state in one paragraph"** that a stranger could read cold, and a single line: **"Most logical next action given this evidence: …"** — derived from what you found, not from the plan.

## Acceptance criteria

- [ ] `STATE.md` is the only file written; no other repo file touched.
- [ ] Zero paid API calls (estimator/dry-run only).
- [ ] Every status claim carries an evidence line; no unevidenced "done."
- [ ] The video-track question is answered categorically: code (with stage-by-stage levels) **or** plan-only.
- [ ] Any task marked done-but-unsupported is explicitly flagged.
