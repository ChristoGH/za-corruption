"""Cross-model extraction eval — Gate 2 decision support.

    cross-model-eval --from-slice --estimate-only
    cross-model-eval --from-slice --budget-usd 10

One variable only: every arm uses the identical extract_v1 prompt and schema;
the sole difference is the model string (asserted at runtime via prompt hash).
Cache-aware: arms re-use the (chunk_id, prompt_version, model) cache, so an
already-extracted arm adds $0 and a full re-run of the eval adds $0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

from commission_ingestion.cli.extract_corpus import select_chunks
from commission_ingestion.cli.parse_corpus import DEFAULT_PROCESSED_DIR
from commission_ingestion.download.registry import DEFAULT_REGISTRY_PATH
from commission_ingestion.eval.compare import compare_arm, resolve_extraction
from commission_ingestion.eval.framing_judge import (
    JUDGE_MODEL,
    judge_arm,
)
from commission_ingestion.eval.report import (
    build_metrics,
    write_hardcase_appendix,
    write_metrics_json,
    write_review_md,
)
from commission_ingestion.eval.sample import (
    DEFAULT_SAMPLE_SIZE,
    DEFAULT_SEED,
    SampledChunk,
    build_sample,
    freeze_sample,
    load_sample,
)
from commission_ingestion.extraction.cache import DEFAULT_CACHE_DIR, ExtractionCache
from commission_ingestion.extraction.extractor import (
    MODEL_PRICES_PER_MTOK,
    extract_chunk,
)
from commission_ingestion.extraction.schema import (
    PROMPT_VERSION,
    ChunkExtraction,
    load_prompt,
)
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.resolution.canonical import load_store

logger = logging.getLogger(__name__)

MODEL_SHORTNAMES = {
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}
REFERENCE_MODEL = "claude-opus-4-8"
SLICE_DAYS = "36,43,66"
DEFAULT_ARTIFACTS_DIR = Path("eval/artifacts")

# Estimation constants recalibrated from the measured smoke test (the
# extractor's verbatim quotes make output ≈2.1x chunk input tokens).
CHARS_PER_TOKEN = 3.6
OUTPUT_PER_INPUT = 2.1
JUDGE_CLAIMS_PER_CHUNK = 2.5
JUDGE_IN_PER_CALL = 800
JUDGE_OUT_PER_CALL = 160


def _estimate_arm_usd(chunks: list[ChunkRecord], model: str) -> float:
    in_price, out_price = MODEL_PRICES_PER_MTOK[model]
    total = 0.0
    for chunk in chunks:
        chunk_tokens = len(chunk.text) / CHARS_PER_TOKEN + 40
        input_tokens = chunk_tokens + 2300 * 0.1  # cached prompt read
        output_tokens = chunk_tokens * OUTPUT_PER_INPUT
        total += (input_tokens * in_price + output_tokens * out_price) / 1e6
    return total


def _estimate_judge_usd(n_chunks: int, n_arms: int) -> float:
    in_price, out_price = MODEL_PRICES_PER_MTOK[JUDGE_MODEL]
    calls = n_chunks * n_arms * 0.8  # ~80% of chunks carry claims
    return calls * (JUDGE_IN_PER_CALL * in_price + JUDGE_OUT_PER_CALL * out_price) / 1e6


def load_extraction(
    cache: ExtractionCache, chunk_id: str, model: str
) -> ChunkExtraction | None:
    payload = cache.get(chunk_id, PROMPT_VERSION, model)
    if payload is None:
        return None
    return ChunkExtraction.model_validate(payload["extraction"])


def measured_cost_per_chunk(
    cache: ExtractionCache, model: str, chunk_ids: set[str]
) -> float:
    """Real $/chunk from the spend audit log, normalized to the SYNC-equivalent
    price: batch-priced entries (already 50% off) are doubled so projections
    can apply the batch discount exactly once. Works for cache-hit arms too —
    the original extraction's cost was logged when it was paid for."""
    spend_path = cache.root / "spend.jsonl"
    if not spend_path.exists():
        return 0.0
    total, seen = 0.0, set()
    for line in spend_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("model") == model and record.get("chunk_id") in chunk_ids:
            cost = record.get("cost_usd", 0.0)
            if record.get("attempt") == "batch":
                cost *= 2  # normalize to sync-equivalent
            total += cost
            seen.add(record["chunk_id"])
    return total / len(seen) if seen else 0.0


def judge_spend_total(cache: ExtractionCache) -> float:
    """Cumulative judge spend from the audit log (this-run cost is zero on a
    cached re-run, which would misleadingly zero the artifact)."""
    spend_path = cache.root / "spend.jsonl"
    if not spend_path.exists():
        return 0.0
    total = 0.0
    for line in spend_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if str(record.get("model", "")).startswith("judge_"):
                total += record.get("cost_usd", 0.0)
    return total


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-model extraction diff vs the Opus reference (Gate 2 input).")
    parser.add_argument("--commission", choices=["zondo", "madlanga"], default="madlanga")
    parser.add_argument("--models", default="opus,sonnet,haiku",
                        help="Comma list of arms (reference 'opus' is required)")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--from-slice", action="store_true",
                        help=f"Draw the sample from the slice days ({SLICE_DAYS}) "
                             "so the Opus arm is cache hits for slice-drawn chunks")
    parser.add_argument("--days", default=None,
                        help="Explicit day list (overrides --from-slice)")
    parser.add_argument("--extra-days", default=None,
                        help="Days added to the sample universe beyond the slice "
                             "(e.g. 31 for the OCR-variant stratum). Sampled chunks "
                             "from these days are fresh spend on EVERY arm, "
                             "including the reference — itemized separately; the "
                             "100%%-cache-hit expectation applies to slice-drawn "
                             "chunks only.")
    parser.add_argument("--budget-usd", type=float, default=None)
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s")

    models = []
    for short in args.models.split(","):
        short = short.strip()
        model = MODEL_SHORTNAMES.get(short, short)
        if model not in MODEL_PRICES_PER_MTOK:
            raise SystemExit(f"unknown model {short!r}")
        models.append(model)
    if REFERENCE_MODEL not in models:
        raise SystemExit(f"the reference arm ({REFERENCE_MODEL}) is required")

    days = args.days or (SLICE_DAYS if args.from_slice else None)
    if days is None:
        raise SystemExit("pass --from-slice or --days")
    slice_day_set = {int(d) for d in days.split(",")}
    extra_day_set = (
        {int(d) for d in args.extra_days.split(",")} if args.extra_days else set()
    )
    day_set = slice_day_set | extra_day_set

    universe = select_chunks(
        registry_path=args.registry, processed_dir=args.processed_dir,
        commission=args.commission, days=day_set)
    if not universe:
        raise SystemExit("no chunks in scope")
    chunks_by_id = {c.chunk_id: c for c in universe}

    store = load_store()
    sample_path = args.artifacts_dir / f"sample_{args.seed}.txt"
    if sample_path.exists():
        sample = load_sample(sample_path)
        logger.info("loaded frozen sample %s (%d chunks)", sample_path, len(sample))
        missing = [s.chunk_id for s in sample if s.chunk_id not in chunks_by_id]
        if missing:
            raise SystemExit(f"frozen sample contains chunks outside scope: {missing[:3]}")
    else:
        sample = build_sample(universe, store,
                              sample_size=args.sample_size, seed=args.seed)
        freeze_sample(sample, args.artifacts_dir, args.seed)
        logger.info("froze sample to %s", sample_path)

    sample_chunks = [chunks_by_id[s.chunk_id] for s in sample]
    sample_ids = {s.chunk_id for s in sample}
    strata = {s.chunk_id: s.stratum for s in sample}
    cache = ExtractionCache(args.cache_dir)

    # One-variable assertion: identical prompt bytes + version for every arm.
    prompt_sha = hashlib.sha256(load_prompt().encode("utf-8")).hexdigest()

    if args.estimate_only:
        print(f"Cross-model eval estimate — sample n={len(sample)} "
              f"(seed {args.seed}), prompt {PROMPT_VERSION}. Zero API calls made.")
        total = 0.0
        for model in models:
            todo = [c for c in sample_chunks
                    if not cache.has(c.chunk_id, PROMPT_VERSION, model)]
            arm = _estimate_arm_usd(todo, model)
            total += arm
            print(f"  {model:<18} {len(todo):>3} uncached of {len(sample)} "
                  f"→ ≈US${arm:.2f}")
        judge = _estimate_judge_usd(len(sample), len(models))
        total += judge
        print(f"  judge ({JUDGE_MODEL}, all arms)        → ≈US${judge:.2f}")
        print(f"  TOTAL ≈US${total:.2f}  (output ≈{OUTPUT_PER_INPUT}x input — "
              "measured, not guessed; cached items cost 0)")
        return 0

    from commission_ingestion.extraction.extractor import AnthropicLLMClient

    client = AnthropicLLMClient()
    spent = 0.0
    arm_added_spend: dict[str, dict[str, float]] = {}
    extractions: dict[str, dict[str, ChunkExtraction | None]] = {}

    for model in models:
        added = {"slice_drawn": 0.0, "out_of_slice": 0.0}
        for chunk in sample_chunks:
            if args.budget_usd is not None and spent >= args.budget_usd:
                print(f"BUDGET CAP US${args.budget_usd:.2f} reached during "
                      f"{model} arm — checkpointed in cache; re-run to resume.")
                return 3
            outcome = extract_chunk(client, cache, chunk, model=model)
            bucket = ("slice_drawn" if chunk.day_no in slice_day_set
                      else "out_of_slice")
            added[bucket] += outcome.cost_usd
            spent += outcome.cost_usd
        arm_added_spend[model] = added
        extractions[model] = {
            cid: load_extraction(cache, cid, model) for cid in sample_ids}
        done = sum(1 for v in extractions[model].values() if v is not None)
        logger.info("%s arm: %d/%d extracted, added US$%.4f slice-drawn "
                    "+ US$%.4f out-of-slice", model, done, len(sample),
                    added["slice_drawn"], added["out_of_slice"])

    # Acceptance check (scoped per the Gate-1 authorization): with the slice
    # pre-extracted, the reference arm's SLICE-DRAWN chunks are pure cache
    # hits; out-of-slice strata chunks are legitimate fresh spend, itemized.
    if arm_added_spend[REFERENCE_MODEL]["slice_drawn"] > 0:
        logger.warning(
            "reference arm spent US$%.4f on slice-drawn chunks — the slice "
            "was not fully pre-extracted",
            arm_added_spend[REFERENCE_MODEL]["slice_drawn"])

    prompt_sha_after = hashlib.sha256(load_prompt().encode("utf-8")).hexdigest()
    assert prompt_sha == prompt_sha_after, "prompt changed mid-run — eval invalid"

    reference = extractions[REFERENCE_MODEL]
    comparisons = {
        model: compare_arm(model=model, reference=reference,
                           candidate=extractions[model], strata=strata, store=store)
        for model in models if model != REFERENCE_MODEL
    }

    resolved_by_model = {
        model: {cid: (resolve_extraction(ex, store) if ex else None)
                for cid, ex in arm.items()}
        for model, arm in extractions.items()
    }

    framing = {}
    judge_total = 0.0
    for model in models:
        claims_by_chunk = {
            cid: resolved.claims
            for cid, resolved in resolved_by_model[model].items()
            if resolved is not None and resolved.claims
        }
        result = judge_arm(
            client, cache, arm_model=model, claims_by_chunk=claims_by_chunk,
            spend_cap_usd=args.budget_usd, spent_so_far=spent)
        framing[model] = result
        judge_total += result.cost_usd
        spent += result.cost_usd

    cost_per_chunk = {
        model: measured_cost_per_chunk(cache, model, sample_ids) for model in models}

    metrics = build_metrics(
        seed=args.seed, sample=sample, prompt_version=PROMPT_VERSION,
        prompt_sha256=prompt_sha, reference_model=REFERENCE_MODEL,
        comparisons=comparisons, framing=framing,
        cost_per_chunk=cost_per_chunk,
        judge_cost_total=judge_spend_total(cache),
        arm_added_spend=arm_added_spend)
    metrics["slice_days"] = sorted(slice_day_set)
    metrics["extra_days"] = sorted(extra_day_set)

    metrics_path = write_metrics_json(metrics, args.artifacts_dir)
    review_path = write_review_md(metrics, args.artifacts_dir)
    appendix_path = write_hardcase_appendix(
        sample=sample, chunks_by_id=chunks_by_id,
        resolved_by_model=resolved_by_model, framing=framing,
        artifacts_dir=args.artifacts_dir)

    print("Cross-model eval complete")
    print(f"  Added spend this run: US${spent:.4f} "
          f"(judge: US${judge_total:.4f})")
    for model in models:
        added = arm_added_spend.get(model, {})
        note = ""
        if model == REFERENCE_MODEL and added.get("slice_drawn", 0) == 0:
            note = "  [slice-drawn: 100% cache hits]"
        print(f"    {model}: +US${added.get('slice_drawn', 0.0):.4f} slice-drawn "
              f"+US${added.get('out_of_slice', 0.0):.4f} out-of-slice "
              f"(measured ${cost_per_chunk.get(model, 0.0):.4f}/chunk){note}")
    print(f"  Artifacts: {metrics_path}, {review_path}, {appendix_path}")
    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
