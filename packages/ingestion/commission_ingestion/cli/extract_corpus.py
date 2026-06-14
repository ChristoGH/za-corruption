"""LLM extraction over the parsed corpus — with a paid-call firewall.

Safety order: ``--estimate-only`` prices the run with ZERO API calls; the
content-addressed cache makes re-runs free; ``--budget-usd`` is a hard cap
that checkpoints cleanly (everything done so far is cached, resume by
re-running). Extraction reads only ACTIVE registry entries — superseded
documents are excluded from birth.

    extract-corpus --days 36,43,66 --estimate-only
    extract-corpus --days 36,43,66 --model claude-opus-4-8 --budget-usd 20
    extract-corpus --all --batch --budget-usd 150
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from commission_ingestion.cli.load_qdrant import read_chunk_files
from commission_ingestion.cli.corpus_stats import split_records
from commission_ingestion.cli.parse_corpus import DEFAULT_PROCESSED_DIR
from commission_ingestion.download.registry import DEFAULT_REGISTRY_PATH, SourceRegistry
from commission_ingestion.extraction.cache import DEFAULT_CACHE_DIR, ExtractionCache
from commission_ingestion.extraction.extractor import (
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    MODEL_PRICES_PER_MTOK,
    extract_chunk,
    parse_extraction,
)
from commission_ingestion.extraction.schema import (
    PROMPT_VERSION,
    load_prompt,
    output_json_schema,
)
from commission_ingestion.models.chunk_record import ChunkRecord

logger = logging.getLogger(__name__)

# ── Estimation heuristics (stated assumptions; estimate-only is API-free) ──
# English transcript text averages ~3.6 chars/token on the current tokenizer
# family; output is structured JSON roughly proportional to chunk length.
CHARS_PER_TOKEN = 3.6
OUTPUT_TOKENS_PER_INPUT_TOKEN = 0.40
OUTPUT_TOKENS_MIN = 120
BATCH_DISCOUNT = 0.5
BATCH_CHUNK_SIZE = 10_000
BATCH_POLL_SECONDS = 60


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def prompt_overhead_tokens() -> int:
    """System prompt + schema, charged on every request (caching reduces the
    real cost below this — the estimate is deliberately conservative)."""
    import json

    return estimate_tokens(load_prompt()) + estimate_tokens(
        json.dumps(output_json_schema())
    )


def estimate_cost(chunks: list[ChunkRecord], model: str, *, batch: bool) -> dict:
    overhead = prompt_overhead_tokens()
    in_price, out_price = MODEL_PRICES_PER_MTOK[model]
    input_tokens = output_tokens = 0
    for chunk in chunks:
        chunk_tokens = estimate_tokens(chunk.text) + 40  # per-chunk metadata header
        input_tokens += chunk_tokens + overhead
        output_tokens += max(
            OUTPUT_TOKENS_MIN, round(chunk_tokens * OUTPUT_TOKENS_PER_INPUT_TOKEN)
        )
    cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    if batch:
        cost *= BATCH_DISCOUNT
    return {
        "chunks": len(chunks),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
    }


def select_chunks(
    *,
    registry_path: Path,
    processed_dir: Path,
    commission: str,
    days: set[int] | None,
) -> list[ChunkRecord]:
    """Chunks from ACTIVE documents only, optionally filtered to hearing days."""
    registry = SourceRegistry(registry_path)
    registry.load()
    active, superseded = split_records(registry, commission)
    active_shas = {r.sha256 for r in active if r.sha256}
    if superseded:
        logger.info("excluding %d superseded document(s)", len(superseded))

    selected: list[ChunkRecord] = []
    for chunks in read_chunk_files(processed_dir, commission):
        if chunks[0].doc_sha256 not in active_shas:
            continue
        if days is not None and chunks[0].day_no not in days:
            continue
        selected.extend(chunks)
    return selected


def run_sync(
    chunks: list[ChunkRecord],
    cache: ExtractionCache,
    *,
    model: str,
    budget_usd: float | None,
) -> dict:
    from commission_ingestion.extraction.extractor import AnthropicLLMClient

    client = AnthropicLLMClient()
    stats = {"cached": 0, "extracted": 0, "dead_letter": 0, "spend_usd": 0.0,
             "stopped_at_budget": False}
    for i, chunk in enumerate(chunks, start=1):
        if budget_usd is not None and stats["spend_usd"] >= budget_usd:
            stats["stopped_at_budget"] = True
            logger.warning(
                "budget cap US$%.2f reached after %d/%d chunks — checkpointed; "
                "re-run to resume from cache", budget_usd, i - 1, len(chunks))
            break
        outcome = extract_chunk(client, cache, chunk, model=model)
        stats[outcome.status] += 1
        stats["spend_usd"] += outcome.cost_usd
        if i % 50 == 0 or i == len(chunks):
            logger.info("progress %d/%d — spend US$%.2f (cached %d, dead %d)",
                        i, len(chunks), stats["spend_usd"],
                        stats["cached"], stats["dead_letter"])
    return stats


def run_batch(
    chunks: list[ChunkRecord],
    cache: ExtractionCache,
    *,
    model: str,
    budget_usd: float | None,
) -> dict:
    """Full-corpus path: Batch API at 50% prices. Malformed batch results get
    one synchronous repair attempt each; failures dead-letter."""
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    from commission_ingestion.extraction.extractor import (
        AnthropicLLMClient,
        cost_usd,
    )

    todo = [c for c in chunks if not cache.has(c.chunk_id, PROMPT_VERSION, model)]
    stats = {"cached": len(chunks) - len(todo), "extracted": 0, "dead_letter": 0,
             "spend_usd": 0.0, "stopped_at_budget": False}
    if not todo:
        return stats

    projected = estimate_cost(todo, model, batch=True)["cost_usd"]
    if budget_usd is not None and projected > budget_usd:
        raise SystemExit(
            f"projected batch cost US${projected:.2f} exceeds budget "
            f"US${budget_usd:.2f} — narrow the scope or raise the budget")

    client = anthropic.Anthropic()
    system = load_prompt()
    schema = output_json_schema()
    by_id = {c.chunk_id: c for c in todo}
    repair_client = AnthropicLLMClient()

    from commission_ingestion.extraction.extractor import chunk_user_message

    for start in range(0, len(todo), BATCH_CHUNK_SIZE):
        window = todo[start : start + BATCH_CHUNK_SIZE]
        requests = [
            Request(
                custom_id=chunk.chunk_id[:64],
                params=MessageCreateParamsNonStreaming(
                    model=model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=[{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": chunk_user_message(chunk)}],
                    output_config={"format": {"type": "json_schema", "schema": schema}},
                ),
            )
            for chunk in window
        ]
        batch = client.messages.batches.create(requests=requests)
        logger.info("batch %s submitted (%d requests)", batch.id, len(requests))
        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            logger.info("batch %s: %s (processing %s)", batch.id,
                        batch.processing_status, batch.request_counts.processing)
            time.sleep(BATCH_POLL_SECONDS)

        for result in client.messages.batches.results(batch.id):
            chunk = by_id[result.custom_id]
            if result.result.type != "succeeded":
                cache.dead_letter(
                    chunk_id=chunk.chunk_id, model=model,
                    prompt_version=PROMPT_VERSION,
                    error=f"batch result: {result.result.type}", raw_response="")
                stats["dead_letter"] += 1
                continue
            message = result.result.message
            text = next((b.text for b in message.content if b.type == "text"), "")
            usage = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "cache_creation_input_tokens": getattr(
                    message.usage, "cache_creation_input_tokens", 0) or 0,
                "cache_read_input_tokens": getattr(
                    message.usage, "cache_read_input_tokens", 0) or 0,
            }
            call_cost = cost_usd(usage, model) * BATCH_DISCOUNT
            stats["spend_usd"] += call_cost
            cache.log_spend({
                "chunk_id": chunk.chunk_id, "model": model,
                "prompt_version": PROMPT_VERSION, "attempt": "batch",
                "usage": usage, "cost_usd": call_cost,
            })
            try:
                extraction = parse_extraction(text)
            except Exception:
                # One synchronous repair, then dead-letter (handled inside).
                outcome = extract_chunk(repair_client, cache, chunk, model=model)
                stats[outcome.status if outcome.status != "cached" else "extracted"] += 1
                stats["spend_usd"] += outcome.cost_usd
                continue
            cache.put(chunk.chunk_id, PROMPT_VERSION, model, {
                "chunk_id": chunk.chunk_id, "model": model,
                "prompt_version": PROMPT_VERSION,
                "extraction": extraction.model_dump(),
            })
            stats["extracted"] += 1
    return stats


def parse_days(value: str | None) -> set[int] | None:
    if value is None:
        return None
    return {int(part) for part in value.split(",") if part.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM extraction over parsed chunks (cached, budgeted).")
    parser.add_argument("--commission", choices=["zondo", "madlanga"], default="madlanga")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--days", help="Comma-separated hearing days, e.g. 36,43,66")
    scope.add_argument("--all", action="store_true", help="Whole active corpus")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        choices=sorted(MODEL_PRICES_PER_MTOK))
    parser.add_argument("--estimate-only", action="store_true",
                        help="Price the run; make zero API calls")
    parser.add_argument("--budget-usd", type=float, default=None,
                        help="Hard spend cap; run checkpoints cleanly at the cap")
    parser.add_argument("--batch", action="store_true",
                        help="Use the Batch API (50%% cost, async)")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Cap chunks (debug)")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s")

    chunks = select_chunks(
        registry_path=args.registry, processed_dir=args.processed_dir,
        commission=args.commission, days=parse_days(args.days))
    if args.limit is not None:
        chunks = chunks[: args.limit]
    if not chunks:
        print("No chunks in scope.")
        return 1

    if args.estimate_only:
        print(f"Extraction estimate — {len(chunks):,} chunks, "
              f"prompt {PROMPT_VERSION} (no API calls made)")
        print(f"  {'model':<18} {'input tok':>12} {'output tok':>12} "
              f"{'standard':>10} {'batch':>10}")
        for model in sorted(MODEL_PRICES_PER_MTOK):
            std = estimate_cost(chunks, model, batch=False)
            bat = estimate_cost(chunks, model, batch=True)
            print(f"  {model:<18} {std['input_tokens']:>12,} "
                  f"{std['output_tokens']:>12,} "
                  f"US${std['cost_usd']:>8.2f} US${bat['cost_usd']:>8.2f}")
        print("  Assumptions: ~3.6 chars/token; output ≈ 40% of chunk input "
              "tokens (min 120); prompt+schema charged per request — prompt "
              "caching will bring real spend below the standard estimate.")
        return 0

    cache = ExtractionCache(args.cache_dir)
    runner = run_batch if args.batch else run_sync
    stats = runner(chunks, cache, model=args.model, budget_usd=args.budget_usd)

    print("Extraction summary")
    print(f"  Scope:        {len(chunks):,} chunks ({args.model}, {PROMPT_VERSION})")
    print(f"  Cached:       {stats['cached']:,}")
    print(f"  Extracted:    {stats['extracted']:,}")
    print(f"  Dead letters: {stats['dead_letter']:,}")
    print(f"  Spend:        US${stats['spend_usd']:.4f}")
    if stats["stopped_at_budget"]:
        print("  STOPPED at budget cap — re-run to resume from cache.")
        return 3
    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
