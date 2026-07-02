#!/usr/bin/env python
"""Post-`--all` corpus-wide safety sweep — ADR 0006 Follow-up 3.

Deterministic, $0 (no API calls). Reads every cached extraction the batch wrote
and runs three passes over the resolved claims:

  1. STRUCTURAL FLOOR (the gate) — `structurally_asserted()`: claim has no
     speaker, or its predicate does not open with a reported-speech verb. This
     is the corpus-wide version of the canary's structural check; flagged
     claims must be individually read before graph-load.
  2. DANGLING SUBJECT (integrity) — a claim whose subject_ref does not resolve
     to any entity in its chunk (`subject_ids` contains a `ref:` form). A real
     data bug if present.
  3. PREDICATE-PRONOUN (advisory, extract_v2) — predicate subject is a pronoun
     ("…stated that he funded…"). Not a defamation issue (the structured
     subject_ref carries the truth — see reports/sectionC_bucket1_review.md);
     these route to the extract_v2 prose fix (Follow-up 1), not a block.

Run AFTER `extract-corpus --all` completes, BEFORE `build-graph`:

    uv run python scripts/postrun_sweep.py --model claude-haiku-4-5

Writes reports/postrun_sweep.md (human) + reports/postrun_sweep_flags.json (audit).
Exit code 1 if the structural-flag rate exceeds --max-structural-rate, so it can
gate CI / a Make target.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from commission_ingestion.eval.compare import resolve_extraction
from commission_ingestion.eval.framing_judge import _REPORTED_VERBS, structurally_asserted
from commission_ingestion.extraction.cache import DEFAULT_CACHE_DIR
from commission_ingestion.extraction.schema import PROMPT_VERSION, ChunkExtraction
from commission_ingestion.resolution.canonical import load_store

_PRONOUN_PRED = re.compile(
    r"\b(?:" + "|".join(_REPORTED_VERBS) + r")\b\s+(?:that\s+)?(he|she|they|it|his|her|their)\b",
    re.IGNORECASE,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Post---all corpus-wide safety sweep (ADR 0006 F3)")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--prompt-version", default=PROMPT_VERSION)
    ap.add_argument("--out-md", type=Path, default=Path("reports/postrun_sweep.md"))
    ap.add_argument("--out-json", type=Path, default=Path("reports/postrun_sweep_flags.json"))
    ap.add_argument("--max-structural-rate", type=float, default=0.02,
                    help="exit 1 if structural-flag rate exceeds this (gate)")
    ap.add_argument("--expected-chunks", type=int, default=None,
                    help="assert this many extraction files are present (e.g. 14783)")
    args = ap.parse_args()

    ext_dir = args.cache_dir / args.model / args.prompt_version
    if not ext_dir.is_dir():
        sys.exit(f"no extraction cache at {ext_dir} — has --all run for this model?")
    files = sorted(ext_dir.glob("*.json"))
    if not files:
        sys.exit(f"no extraction files in {ext_dir}")

    store = load_store()

    chunks = total_claims = struct = dangling = pronoun = bad_files = 0
    flags = {"structural": [], "dangling_subject": [], "predicate_pronoun": []}

    for fp in files:
        try:
            payload = json.loads(fp.read_text())
            ext = ChunkExtraction.model_validate(payload["extraction"])
        except Exception as exc:  # malformed / partial cache entry
            bad_files += 1
            flags.setdefault("unparseable", []).append({"file": fp.name, "error": str(exc)[:160]})
            continue
        cid = payload.get("chunk_id", fp.stem)
        chunks += 1
        resolved = resolve_extraction(ext, store)
        for rc in resolved.claims:
            total_claims += 1
            rec = {"chunk_id": cid, "speaker": rc.speaker,
                   "predicate": rc.predicate, "quote": rc.quote[:240]}
            if structurally_asserted(rc):
                struct += 1
                flags["structural"].append(rec)
            if any(s.startswith("ref:") for s in rc.subject_ids):
                dangling += 1
                flags["dangling_subject"].append({**rec, "subject_ids": sorted(rc.subject_ids)})
            if _PRONOUN_PRED.search(rc.predicate):
                pronoun += 1
                flags["predicate_pronoun"].append(rec)

    rate = (struct / total_claims) if total_claims else 0.0
    gate_ok = rate <= args.max_structural_rate
    coverage_ok = args.expected_chunks is None or chunks == args.expected_chunks

    summary = {
        "model": args.model, "prompt_version": args.prompt_version,
        "extraction_files": len(files), "chunks_parsed": chunks,
        "unparseable_files": bad_files, "total_claims": total_claims,
        "structural_flags": struct, "structural_rate": round(rate, 4),
        "dangling_subject_refs": dangling, "predicate_pronoun_claims": pronoun,
        "max_structural_rate": args.max_structural_rate,
        "gate_structural_ok": gate_ok, "coverage_ok": coverage_ok,
        "expected_chunks": args.expected_chunks,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({"summary": summary, "flags": flags}, indent=1, ensure_ascii=False))

    def sample(key: str, n: int = 40) -> str:
        rows = flags[key][:n]
        if not rows:
            return "_none_"
        out = []
        for r in rows:
            out.append(f"- `{r['chunk_id'][:16]}` speaker={r.get('speaker') or '(none)'} | "
                       f"{r['predicate']} | quote={r['quote'][:120]!r}")
        extra = len(flags[key]) - len(rows)
        if extra > 0:
            out.append(f"- …and {extra} more (full list in {args.out_json.name})")
        return "\n".join(out)

    verdict = "PASS" if (gate_ok and coverage_ok and bad_files == 0) else "REVIEW"
    md = f"""# Post-`--all` corpus-wide safety sweep (ADR 0006 Follow-up 3)

**Verdict: {verdict}** — structural gate {"OK" if gate_ok else "EXCEEDED"} · \
coverage {"OK" if coverage_ok else "MISMATCH"} · unparseable {bad_files}

| metric | value |
|---|---|
| extraction files | {len(files):,} |
| chunks parsed | {chunks:,}{"" if coverage_ok else f"  (expected {args.expected_chunks:,})"} |
| total claims | {total_claims:,} |
| **structural flags** (gate) | {struct:,}  (rate {rate:.3%}, cap {args.max_structural_rate:.1%}) |
| dangling subject_refs | {dangling:,} |
| predicate-pronoun (→ extract_v2) | {pronoun:,} |
| unparseable cache files | {bad_files} |

## 1. Structural flags — read before graph-load (gate)
`structurally_asserted()` = no speaker, or predicate lacks a reported-speech verb in its
opening. PASS condition: genuine slips (after this read) ≤ 0.2% and any imputing wrongdoing
to a named party remediated (fix subject_ref / re-attribute / drop). Doctrine: these ship as
correctly-attributed `:Claim`s; the writer always sets `status="alleged"`.

{sample("structural")}

## 2. Dangling subject_refs — integrity (should be 0)
{sample("dangling_subject")}

## 3. Predicate-pronoun — advisory, route to extract_v2 (NOT a blocker)
Subject carried by `subject_refs` (correct); only the predicate prose uses a pronoun. Same
class as the §C canary cases — see `reports/sectionC_bucket1_review.md`.

{sample("predicate_pronoun")}

Full machine-readable lists: `{args.out_json.name}`. Owner: Christo.
"""
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(md)

    print(json.dumps(summary, indent=1))
    print(f"\nwrote {args.out_md} and {args.out_json}")
    if not (gate_ok and coverage_ok and bad_files == 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
