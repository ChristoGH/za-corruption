# plans/

This directory holds **live, per-task prompt documents** — one file per in-flight piece
of work, discarded here once the work lands.

## Rules

- The **single plan-of-record** is `docs/project-state.md §8`. Add milestones and
  stages there; do not maintain a parallel build plan here.
- A prompt doc lives here only while its work is in progress. The moment the code
  lands and tests pass, move the file to `plans/archive/` with a one-line reason.
- Plan docs are never committed alongside `docs/` as if they were canonical
  specification. Specs live in `docs/`; this directory is scratch.

## Current live prompts

_(empty — all work currently tracked in `docs/project-state.md §8`)_

## Archive

Spent and wrong-project plans are in [`plans/archive/`](archive/README.md) with
retirement reasons.
