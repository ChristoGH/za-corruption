#!/usr/bin/env python
"""Recover an already-completed batch's results into the extraction cache — $0.

When `extract-corpus --batch` crashes *after* a batch ends but *before* all its
results are cached (e.g. a mid-run synchronous repair hits a 400), the batch's
results are still retrievable from the API for ~29 days and were already paid
for. This re-pulls them and writes the succeeded ones to cache, so the next
`extract-corpus --all --batch` only submits the genuine remainder instead of
re-paying for results that already exist.

No synchronous repair, so it needs no credits and cannot crash on a bad result:
succeeded+parseable → cached; everything else is left uncached for the re-run to
retry cleanly.

    uv run python scripts/recover_batch.py msgbatch_01JvxeXwgaUb4jJFS1RXPVbh
    # then re-run:  uv run extract-corpus --all --batch --model claude-haiku-4-5 --budget-usd 30
"""
from __future__ import annotations

import argparse

import anthropic

from commission_ingestion.extraction.cache import DEFAULT_CACHE_DIR, ExtractionCache
from commission_ingestion.extraction.extractor import parse_extraction
from commission_ingestion.extraction.schema import PROMPT_VERSION


def main() -> None:
    ap = argparse.ArgumentParser(description="Recover a completed batch's results into cache ($0)")
    ap.add_argument("batch_id")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    ap.add_argument("--prompt-version", default=PROMPT_VERSION)
    args = ap.parse_args()

    cache = ExtractionCache(args.cache_dir)
    client = anthropic.Anthropic()

    batch = client.messages.batches.retrieve(args.batch_id)
    if batch.processing_status != "ended":
        raise SystemExit(
            f"batch {args.batch_id} is {batch.processing_status}, not ended — "
            "wait for it to finish before recovering.")

    recovered = already = not_succeeded = unparseable = 0
    for result in client.messages.batches.results(args.batch_id):
        cid = result.custom_id  # == full chunk_id (chunk.chunk_id[:64])
        if cache.has(cid, args.prompt_version, args.model):
            already += 1
            continue
        if result.result.type != "succeeded":
            not_succeeded += 1  # leave uncached → re-run retries
            continue
        message = result.result.message
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            extraction = parse_extraction(text)
        except Exception:
            unparseable += 1  # leave uncached → re-run retries/repairs
            continue
        cache.put(cid, args.prompt_version, args.model, {
            "chunk_id": cid, "model": args.model,
            "prompt_version": args.prompt_version,
            "extraction": extraction.model_dump(),
        })
        recovered += 1

    print(f"batch {args.batch_id} ({batch.processing_status})")
    print(f"  recovered to cache : {recovered}")
    print(f"  already cached     : {already}")
    print(f"  not succeeded      : {not_succeeded}  (left for re-run)")
    print(f"  unparseable        : {unparseable}  (left for re-run)")
    print("Next: uv run extract-corpus --all --batch "
          f"--model {args.model} --budget-usd 30")


if __name__ == "__main__":
    main()
