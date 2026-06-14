"""Gate 2 artifact rendering — scorecards, hard-case side-by-sides, metrics.

The review document states the tradeoff; it never selects a model. All writes
are atomic (tmp + replace) so a halted run cannot leave corrupt artifacts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from commission_ingestion.eval.compare import ArmComparison, ResolvedChunk
from commission_ingestion.eval.framing_judge import FramingResult
from commission_ingestion.eval.sample import HARD_STRATA, SampledChunk
from commission_ingestion.models.chunk_record import ChunkRecord

FULL_CORPUS_CHUNKS = 14_783


def _atomic_write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def build_metrics(
    *,
    seed: int,
    sample: list[SampledChunk],
    prompt_version: str,
    prompt_sha256: str,
    reference_model: str,
    comparisons: dict[str, ArmComparison],
    framing: dict[str, FramingResult],
    cost_per_chunk: dict[str, float],
    judge_cost_total: float,
    arm_added_spend: dict[str, dict[str, float]],
) -> dict:
    strata_counts: dict[str, int] = {}
    for item in sample:
        strata_counts[item.stratum] = strata_counts.get(item.stratum, 0) + 1

    models: dict[str, dict] = {}
    all_models = sorted(set(comparisons) | set(framing) | set(cost_per_chunk))
    for model in all_models:
        per_chunk = cost_per_chunk.get(model, 0.0)
        entry: dict = {
            "cost": {
                "measured_usd_per_chunk": round(per_chunk, 5),
                "projected_full_corpus_usd": round(per_chunk * FULL_CORPUS_CHUNKS, 2),
                "projected_full_corpus_batch_usd": round(
                    per_chunk * FULL_CORPUS_CHUNKS * 0.5, 2),
                "added_spend_this_run_usd": {
                    bucket: round(value, 4)
                    for bucket, value in arm_added_spend.get(model, {}).items()
                },
            }
        }
        if model in comparisons:
            entry.update(comparisons[model].to_dict())
        else:
            entry["model"] = model
            entry["role"] = "reference"
        if model in framing:
            entry["framing"] = framing[model].to_dict()
        models[model] = entry

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "sample_size": len(sample),
        "strata_counts": strata_counts,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "reference_model": reference_model,
        "judge": {"model": "claude-opus-4-8", "total_cost_usd": round(judge_cost_total, 4)},
        "models": models,
    }


def write_metrics_json(metrics: dict, artifacts_dir: Path) -> Path:
    path = artifacts_dir / "metrics.json"
    _atomic_write(path, json.dumps(metrics, indent=2, ensure_ascii=False))
    return path


def write_review_md(metrics: dict, artifacts_dir: Path) -> Path:
    ref = metrics["reference_model"]
    lines = [
        "# Gate 2 — cross-model extraction review",
        "",
        f"_Generated {metrics['generated_at']} · sample n={metrics['sample_size']} "
        f"(seed {metrics['seed']}) · prompt {metrics['prompt_version']} "
        f"(sha {metrics['prompt_sha256'][:12]}) · reference: {ref} · "
        f"judge: {metrics['judge']['model']} "
        f"(US${metrics['judge']['total_cost_usd']:.2f})_",
        "",
        "Strata: " + ", ".join(
            f"{k}={v}" for k, v in sorted(metrics["strata_counts"].items())),
        "",
        "| model | completion | entity F1 (hard) | entity F1 (control) | "
        "fragmentation | claim recall | claim precision | asserted-as-fact rate | "
        "$/chunk | full corpus (batch) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, entry in sorted(metrics["models"].items()):
        cost = entry["cost"]
        if entry.get("role") == "reference":
            framing = entry.get("framing", {})
            lines.append(
                f"| {model} (reference) | — | — | — | — | — | — | "
                f"{framing.get('asserted_as_fact_rate', '—')} | "
                f"${cost['measured_usd_per_chunk']:.4f} | "
                f"${cost['projected_full_corpus_batch_usd']:.2f} |")
            continue
        comp = entry
        framing = entry.get("framing", {})
        lines.append(
            f"| {model} | {comp['completion']['rate']:.0%} "
            f"({comp['completion']['completed']}/{comp['completion']['total']}) | "
            f"{comp['entity_agreement']['hard_strata']['f1']:.3f} | "
            f"{comp['entity_agreement']['control']['f1']:.3f} | "
            f"{comp['fragmentation']} | "
            f"{comp['claims']['recall_vs_reference']:.3f} | "
            f"{comp['claims']['precision_vs_reference']:.3f} | "
            f"{framing.get('asserted_as_fact_rate', '—')} | "
            f"${cost['measured_usd_per_chunk']:.4f} | "
            f"${cost['projected_full_corpus_batch_usd']:.2f} |")

    lines += [
        "",
        "## Reading guide",
        "",
        "- **Completion** below 100% means refusals/dead-letters; a model that "
        "fails allegation-dense chunks is disqualified regardless of agreement "
        "elsewhere.",
        "- **Entity F1** is post-resolution (canonical-ID sets vs the reference), "
        "split hard-strata vs control. **Fragmentation** counts mentions that fell "
        "through to raw strings — a dirtier graph.",
        "- **Claims** are soft-matched on subject canonical-ID overlap + predicate "
        "similarity; dropped/invented counts are in metrics.json.",
        "- **Asserted-as-fact rate** is the defamation-critical axis, classified "
        "by a constant Opus judge across all arms (including the reference). One "
        "framing slip outweighs a dozen entity misses.",
        "",
        "## Decision scaffold (human call — intentionally not auto-selected)",
        "",
    ]
    ref_cost = metrics["models"].get(ref, {}).get("cost", {})
    ref_full = ref_cost.get("projected_full_corpus_batch_usd", 0.0)
    for model, entry in sorted(metrics["models"].items()):
        if entry.get("role") == "reference" or "claims" not in entry:
            continue
        cost = entry["cost"]
        framing = entry.get("framing", {})
        saving = ref_full - cost["projected_full_corpus_batch_usd"]
        lines.append(
            f"- **{model}** saves ≈US${saving:.0f} on the full batch burn at the "
            f"cost of: {entry['claims']['dropped']} dropped / "
            f"{entry['claims']['invented']} invented claims, "
            f"{entry['fragmentation']} fragmented mentions, "
            f"hard-case entity F1 {entry['entity_agreement']['hard_strata']['f1']:.3f}, "
            f"and {framing.get('counts', {}).get('asserted_as_fact', '?')} "
            f"asserted-as-fact framings "
            f"(vs {metrics['models'][ref].get('framing', {}).get('counts', {}).get('asserted_as_fact', '?')} "
            f"on the reference). See hardcase_appendix.md before deciding.")
    lines += [
        "",
        f"Reference full-corpus batch cost: ≈US${ref_full:.2f}. "
        "Approve a model and budget at Gate 2 to proceed.",
        "",
    ]
    path = artifacts_dir / "gate2_model_review.md"
    _atomic_write(path, "\n".join(lines))
    return path


def write_hardcase_appendix(
    *,
    sample: list[SampledChunk],
    chunks_by_id: dict[str, ChunkRecord],
    resolved_by_model: dict[str, dict[str, ResolvedChunk | None]],
    framing: dict[str, FramingResult],
    artifacts_dir: Path,
) -> Path:
    lines = [
        "# Hard-case appendix — side-by-side extractions",
        "",
        "_Per hard-stratum chunk: what each model resolved (canonical id or RAW "
        "fallthrough) and how each claim was framed. Eyeball the Khumalos._",
        "",
    ]
    for item in sample:
        if item.stratum not in HARD_STRATA:
            continue
        chunk = chunks_by_id[item.chunk_id]
        lines += [
            f"## {item.stratum} — day {chunk.day_no} ({chunk.date}), "
            f"pp. {chunk.page_start}–{chunk.page_end}",
            f"`chunk {item.chunk_id[:16]}…` speakers: {', '.join(chunk.speakers)}",
            "",
            "> " + chunk.text[:400].replace("\n", " ") + " …",
            "",
        ]
        for model in sorted(resolved_by_model):
            resolved = resolved_by_model[model].get(item.chunk_id)
            lines.append(f"### {model}")
            if resolved is None:
                lines += ["- (no extraction — dead-letter/refusal/not run)", ""]
                continue
            ids = ", ".join(sorted(resolved.canonical_ids)) or "—"
            frags = ", ".join(sorted(resolved.fragments)) or "—"
            lines.append(f"- entities: {ids}")
            lines.append(f"- fragments: {frags}")
            verdicts = framing.get(model)
            chunk_verdicts = (verdicts.rationales.get(item.chunk_id, [])
                              if verdicts else [])
            for i, claim in enumerate(resolved.claims):
                label = next(
                    (v["label"] for v in chunk_verdicts if v["index"] == i),
                    "(unjudged)")
                lines.append(
                    f"- claim [{label}] {claim.speaker}: {claim.predicate}")
            lines.append("")
    path = artifacts_dir / "hardcase_appendix.md"
    _atomic_write(path, "\n".join(lines))
    return path
