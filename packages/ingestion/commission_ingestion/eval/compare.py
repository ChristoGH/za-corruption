"""Resolution-aware, framing-aware diff of extraction arms against a reference.

Entity agreement is measured AFTER canonical resolution — the question is not
"did the models emit the same strings" but "do their mentions land on the same
canonical entities". Mentions that fail to resolve are fragmentation: a dirtier
graph, counted separately. Claims soft-match on (subject canonical-ID overlap +
predicate similarity); everything here is deterministic — no API calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from commission_ingestion.eval.sample import HARD_STRATA
from commission_ingestion.extraction.schema import ChunkExtraction
from commission_ingestion.resolution.canonical import CanonicalStore, normalise

PREDICATE_SIMILARITY_THRESHOLD = 0.45


@dataclass
class ResolvedClaim:
    speaker: str
    predicate: str
    quote: str
    certainty: str | None
    subject_ids: frozenset[str]  # canonical ids; unresolved subjects become raw: forms


@dataclass
class ResolvedChunk:
    canonical_ids: set[str]
    fragments: set[str]  # normalized surface forms that failed resolution
    claims: list[ResolvedClaim]


def resolve_extraction(extraction: ChunkExtraction, store: CanonicalStore) -> ResolvedChunk:
    by_ref = {e.ref: e for e in extraction.entities}

    def resolve_entity(ref: str) -> tuple[str | None, str | None]:
        """(canonical_id, fragment_form) — exactly one is non-None."""
        entity = by_ref.get(ref)
        if entity is None:
            return None, None
        hit = store.lookup(entity.name, entity.type)
        if hit is not None:
            return hit.entity_id, None
        return None, f"raw:{normalise(entity.name)}"

    canonical_ids: set[str] = set()
    fragments: set[str] = set()
    for mention in extraction.mentions:
        cid, frag = resolve_entity(mention.entity_ref)
        if cid:
            canonical_ids.add(cid)
        elif frag:
            fragments.add(frag)

    claims: list[ResolvedClaim] = []
    for claim in extraction.claims:
        subject_ids: set[str] = set()
        for ref in claim.subject_refs:
            cid, frag = resolve_entity(ref)
            subject_ids.add(cid or frag or f"ref:{ref}")
        claims.append(
            ResolvedClaim(
                speaker=claim.speaker,
                predicate=claim.predicate,
                quote=claim.quote,
                certainty=claim.certainty,
                subject_ids=frozenset(subject_ids),
            )
        )
    return ResolvedChunk(canonical_ids=canonical_ids, fragments=fragments, claims=claims)


def predicate_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def match_claims(
    reference: list[ResolvedClaim],
    candidate: list[ResolvedClaim],
    *,
    threshold: float = PREDICATE_SIMILARITY_THRESHOLD,
) -> tuple[int, int, int]:
    """Greedy one-to-one soft matching. Returns (matched, dropped, invented):
    dropped = reference claims with no candidate match; invented = candidate
    claims with no reference match."""
    remaining = list(candidate)
    matched = 0
    for ref_claim in reference:
        best_index, best_score = None, 0.0
        for i, cand in enumerate(remaining):
            if not (ref_claim.subject_ids & cand.subject_ids):
                continue
            score = predicate_similarity(ref_claim.predicate, cand.predicate)
            if score >= threshold and score > best_score:
                best_index, best_score = i, score
        if best_index is not None:
            remaining.pop(best_index)
            matched += 1
    dropped = len(reference) - matched
    invented = len(remaining)
    return matched, dropped, invented


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, reference: set[str], candidate: set[str]) -> None:
        self.tp += len(reference & candidate)
        self.fp += len(candidate - reference)
        self.fn += len(reference - candidate)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class ArmComparison:
    model: str
    total_chunks: int = 0
    completed_chunks: int = 0
    entity_overall: PRF = field(default_factory=PRF)
    entity_hard: PRF = field(default_factory=PRF)
    entity_control: PRF = field(default_factory=PRF)
    fragmentation: int = 0
    claims_matched: int = 0
    claims_dropped: int = 0
    claims_invented: int = 0

    @property
    def completion_rate(self) -> float:
        return self.completed_chunks / self.total_chunks if self.total_chunks else 0.0

    @property
    def claim_recall(self) -> float:
        denom = self.claims_matched + self.claims_dropped
        return self.claims_matched / denom if denom else 0.0

    @property
    def claim_precision(self) -> float:
        denom = self.claims_matched + self.claims_invented
        return self.claims_matched / denom if denom else 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "completion": {
                "total": self.total_chunks,
                "completed": self.completed_chunks,
                "rate": round(self.completion_rate, 4),
            },
            "entity_agreement": {
                "overall": self.entity_overall.to_dict(),
                "hard_strata": self.entity_hard.to_dict(),
                "control": self.entity_control.to_dict(),
            },
            "fragmentation": self.fragmentation,
            "claims": {
                "matched": self.claims_matched,
                "dropped": self.claims_dropped,
                "invented": self.claims_invented,
                "recall_vs_reference": round(self.claim_recall, 4),
                "precision_vs_reference": round(self.claim_precision, 4),
            },
        }


def compare_arm(
    *,
    model: str,
    reference: dict[str, ChunkExtraction | None],
    candidate: dict[str, ChunkExtraction | None],
    strata: dict[str, str],
    store: CanonicalStore,
) -> ArmComparison:
    """Diff one candidate arm against the reference over the frozen sample.
    Chunks where the reference itself failed are excluded from agreement (there
    is nothing to agree with) but still count toward the candidate's completion
    rate."""
    result = ArmComparison(model=model)
    for chunk_id, ref_extraction in reference.items():
        cand_extraction = candidate.get(chunk_id)
        result.total_chunks += 1
        if cand_extraction is not None:
            result.completed_chunks += 1
        if ref_extraction is None or cand_extraction is None:
            continue

        ref_resolved = resolve_extraction(ref_extraction, store)
        cand_resolved = resolve_extraction(cand_extraction, store)

        result.entity_overall.add(ref_resolved.canonical_ids, cand_resolved.canonical_ids)
        bucket = (
            result.entity_hard
            if strata.get(chunk_id) in HARD_STRATA
            else result.entity_control
        )
        bucket.add(ref_resolved.canonical_ids, cand_resolved.canonical_ids)
        result.fragmentation += len(cand_resolved.fragments)

        matched, dropped, invented = match_claims(ref_resolved.claims, cand_resolved.claims)
        result.claims_matched += matched
        result.claims_dropped += dropped
        result.claims_invented += invented
    return result
