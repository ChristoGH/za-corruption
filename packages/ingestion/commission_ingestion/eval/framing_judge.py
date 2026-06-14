"""Claim-framing classification — the defamation-critical axis.

Two passes:
1. Structural (deterministic, free): flag claims with missing speaker
   attribution or a predicate that asserts directly instead of reporting
   speech. Catches the obvious slips without an API call.
2. Judged: a SINGLE FIXED judge model (Opus — never the model under test
   judging itself) classifies every claim from every arm identically as
   neutral_reported | asserted_as_fact | ambiguous with a one-line rationale.

Judge calls are content-cached like extractions, so re-runs are free, and the
judge's spend is accounted separately against the budget.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commission_ingestion.eval.compare import ResolvedClaim
from commission_ingestion.extraction.cache import ExtractionCache
from commission_ingestion.extraction.extractor import LLMClient, cost_usd

logger = logging.getLogger(__name__)

JUDGE_MODEL = "claude-opus-4-8"  # constant judge — identical for all arms
JUDGE_PROMPT_VERSION = "judge_v1"
JUDGE_MAX_TOKENS = 2000

# Reported-speech verbs that must govern a neutral predicate. A predicate that
# opens without one ("ordered the disbandment of...") asserts directly.
_REPORTED_VERBS = (
    "stated", "testified", "alleged", "said", "told", "claimed", "denied",
    "confirmed", "clarified", "explained", "described", "recounted",
    "maintained", "submitted", "argued", "suggested", "asserted", "indicated",
    "conceded", "agreed", "disputed", "responded", "answered", "estimated",
    "recalled", "reported",
)

JUDGE_SYSTEM = """You audit extracted claims from South African commission-of-inquiry \
transcripts for framing discipline. Each claim must be NEUTRAL REPORTED SPEECH: it \
records that a speaker asserted something, without the extraction itself asserting \
the underlying fact.

Classify each numbered claim:
- neutral_reported — the predicate clearly frames the content as the speaker's \
assertion ("stated that he received an instruction...", "alleged that...").
- asserted_as_fact — the predicate asserts the underlying act or state directly \
("instructed the disbandment of the unit", "received payments from X"), so a reader \
could mistake an allegation for a finding.
- ambiguous — attribution is present but the framing could be read either way.

Judge ONLY the framing of the predicate, not whether the content is plausible. \
Give a one-line rationale per claim. Return only the JSON object."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JudgeVerdict(_Strict):
    index: int
    label: Literal["neutral_reported", "asserted_as_fact", "ambiguous"]
    rationale: str


class JudgeResponse(_Strict):
    verdicts: list[JudgeVerdict]


def judge_output_schema() -> dict:
    return JudgeResponse.model_json_schema()


def structurally_asserted(claim: ResolvedClaim) -> bool:
    """Deterministic pre-filter: no speaker, or no reported-speech verb in the
    predicate's opening words."""
    if not claim.speaker or not claim.speaker.strip():
        return True
    opening = claim.predicate.lower().split()[:4]
    return not any(verb in opening for verb in _REPORTED_VERBS)


def _claims_payload(claims: list[ResolvedClaim]) -> str:
    lines = []
    for i, claim in enumerate(claims):
        lines.append(
            f"{i}. speaker: {claim.speaker or '(none)'}\n"
            f"   predicate: {claim.predicate}\n"
            f"   supporting quote: {claim.quote[:300]}"
        )
    return "\n".join(lines)


def _cache_key(arm_model: str, chunk_id: str, claims: list[ResolvedClaim]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            [(c.speaker, c.predicate, c.quote) for c in claims], ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{chunk_id[:32]}__{arm_model}__{digest}"


@dataclass
class FramingResult:
    counts: dict[str, int]
    structural_flags: int
    judged_claims: int
    cost_usd: float
    rationales: dict[str, list[dict]]  # chunk_id -> per-claim verdicts

    @property
    def asserted_rate(self) -> float:
        return (
            self.counts.get("asserted_as_fact", 0) / self.judged_claims
            if self.judged_claims
            else 0.0
        )

    def to_dict(self) -> dict:
        return {
            "judged_claims": self.judged_claims,
            "counts": self.counts,
            "asserted_as_fact_rate": round(self.asserted_rate, 4),
            "structural_flags": self.structural_flags,
            "judge_cost_usd": round(self.cost_usd, 4),
        }


def judge_arm(
    client: LLMClient | None,
    cache: ExtractionCache,
    *,
    arm_model: str,
    claims_by_chunk: dict[str, list[ResolvedClaim]],
    spend_cap_usd: float | None = None,
    spent_so_far: float = 0.0,
) -> FramingResult:
    """Judge every claim of one arm with the constant judge. ``client=None``
    is allowed when everything is already cached (re-runs are free)."""
    counts = {"neutral_reported": 0, "asserted_as_fact": 0, "ambiguous": 0}
    structural_flags = 0
    judged = 0
    cost = 0.0
    rationales: dict[str, list[dict]] = {}
    schema = judge_output_schema()

    for chunk_id, claims in sorted(claims_by_chunk.items()):
        if not claims:
            continue
        structural_flags += sum(1 for c in claims if structurally_asserted(c))

        key = _cache_key(arm_model, chunk_id, claims)
        cached = cache.get(key, JUDGE_PROMPT_VERSION, f"judge_{JUDGE_MODEL}")
        if cached is not None:
            verdicts = JudgeResponse.model_validate(cached["response"]).verdicts
        else:
            if client is None:
                raise RuntimeError(
                    "judge results not cached and no client provided")
            if spend_cap_usd is not None and (spent_so_far + cost) >= spend_cap_usd:
                logger.warning("judge halted at budget cap — resumable from cache")
                break
            raw, usage = client.complete(
                model=JUDGE_MODEL,
                system=JUDGE_SYSTEM,
                user=_claims_payload(claims),
                schema=schema,
                max_tokens=JUDGE_MAX_TOKENS,
            )
            call_cost = cost_usd(usage, JUDGE_MODEL)
            cost += call_cost
            cache.log_spend({
                "chunk_id": chunk_id, "model": f"judge_{JUDGE_MODEL}",
                "prompt_version": JUDGE_PROMPT_VERSION,
                "attempt": f"judge:{arm_model}",
                "usage": usage, "cost_usd": call_cost,
            })
            try:
                response = JudgeResponse.model_validate_json(raw)
            except (ValidationError, ValueError) as exc:
                cache.dead_letter(
                    chunk_id=key, model=f"judge_{JUDGE_MODEL}",
                    prompt_version=JUDGE_PROMPT_VERSION,
                    error=str(exc), raw_response=raw)
                continue
            cache.put(key, JUDGE_PROMPT_VERSION, f"judge_{JUDGE_MODEL}",
                      {"response": response.model_dump()})
            verdicts = response.verdicts

        chunk_verdicts = []
        for verdict in verdicts:
            if verdict.index < len(claims):
                counts[verdict.label] += 1
                judged += 1
                chunk_verdicts.append(verdict.model_dump())
        rationales[chunk_id] = chunk_verdicts

    return FramingResult(
        counts=counts,
        structural_flags=structural_flags,
        judged_claims=judged,
        cost_usd=cost,
        rationales=rationales,
    )
