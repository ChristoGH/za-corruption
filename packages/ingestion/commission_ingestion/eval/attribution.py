"""Pre-step B — turn-speaker attribution validator.

Independently checks that each claim's speaker (the model's inline attribution,
which the claim writer trusts for STATED_BY) matches the speaker of the turn its
quote actually falls in. This catches the wrong-speaker class the Gate 2
subject+predicate soft-match is blind to.

Mismatches are PARTITIONED by cause — an unpartitioned rate is meaningless
because two OPPOSITE failures both produce "claim.speaker != turn.speaker":

  bucket 1  MODEL-WRONG   — the quote falls in a turn the parser DID detect and
                            resolve, and the model named someone else. A real
                            attribution error (Haiku referent-collapse). This is
                            the only thing the "attribution-error rate" counts.
  bucket 2  PARSER-GAP    — the quote falls in an absorbed "COMMISSIONER <surname>:"
                            turn that parsing/turns.py LABEL_RE cannot see
                            (finding #1). The MODEL is right, the PARSED TURN is
                            wrong. Counted toward the turns.py re-chunk milestone,
                            never against the model, never a canary RED.
  bucket 3  QUOTE-UNRECOVERABLE — find_quote() returns None, so there is no offset
                            to map. The Tier 1 fabricated-quote gate; reported
                            separately, excluded from the rate.

Discriminator (1 vs 2), stated explicitly: re-derive turn boundaries from the
chunk text with two regexes — the parser's own LABEL_RE (what the spine sees) and
an AUGMENTED regex that additionally recognizes ROLE+surname labels LABEL_RE
misses. A mismatch is PARSER-GAP iff the nearest preceding label under augmented
segmentation is a parser blind-spot (matched by augmented, NOT by LABEL_RE) AND
the model's resolved speaker equals that label's resolved speaker. Otherwise the
mismatch is MODEL-WRONG.

Pure: reads turns (re-derived from chunk text) + extractions + the canonical
store. No live DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from commission_ingestion.extraction.schema import ChunkExtraction, find_quote
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.parsing.turns import LABEL_RE, normalise_label
from commission_ingestion.resolution.canonical import CanonicalStore

# ROLE+surname turn labels the parser's LABEL_RE cannot see (finding #1):
# "COMMISSIONER MKHWANAZI:", "COMMISSIONER SPIES:", etc. LABEL_RE's _ROLE branch
# matches the bare role word only, so these are absorbed into the prior turn.
_ROLE_SURNAME_RE = re.compile(
    r"(?:^|(?<=\s))("
    r"(?:COMMISSIONER|CHAIRPERSON|WITNESS|INTERPRETER|REGISTRAR)"
    r"\s+[A-Z][A-Z .'\-]*?"
    r")\s*:\s"
)

BUCKET_MATCH = "match"
BUCKET_MODEL_WRONG = "model_wrong"          # bucket 1
BUCKET_PARSER_GAP = "parser_gap"            # bucket 2
BUCKET_QUOTE_UNRECOVERABLE = "quote_unrecoverable"  # bucket 3
BUCKET_INDETERMINATE = "indeterminate"      # no turn could be established; reported, never blended


@dataclass(frozen=True)
class _Label:
    speaker: str        # normalised label
    start: int          # offset of the label in chunk text
    parser_detected: bool  # True if LABEL_RE matched it (i.e. the spine sees this turn)


def _labels(text: str) -> list[_Label]:
    """All turn labels in the chunk text, sorted by position. LABEL_RE matches are
    parser-detected; ROLE+surname matches LABEL_RE missed are blind-spots."""
    found: dict[int, _Label] = {}
    for m in LABEL_RE.finditer(text):
        found[m.start(1)] = _Label(normalise_label(m.group(1)), m.start(1), True)
    for m in _ROLE_SURNAME_RE.finditer(text):
        # only add if LABEL_RE didn't already claim this position (it won't —
        # LABEL_RE's _ROLE branch stops at the role word and fails the colon)
        if m.start(1) not in found:
            found[m.start(1)] = _Label(normalise_label(m.group(1)), m.start(1), False)
    return [found[k] for k in sorted(found)]


def _containing(labels: list[_Label], offset: int, *, parser_only: bool) -> _Label | None:
    """Nearest label at or before offset; if parser_only, ignore blind-spots."""
    candidate: _Label | None = None
    for lbl in labels:
        if lbl.start > offset:
            break
        if parser_only and not lbl.parser_detected:
            continue
        candidate = lbl
    return candidate


@dataclass
class AttributionInstance:
    chunk_id: str
    bucket: str
    claim_text: str
    quote: str
    model_speaker: str | None   # resolved canonical id (or raw label if unresolved)
    turn_speaker: str | None    # parser-detected containing turn speaker (resolved)
    augmented_speaker: str | None  # containing turn speaker under augmented segmentation


@dataclass
class AttributionStats:
    total: int = 0
    match: int = 0
    model_wrong: int = 0
    parser_gap: int = 0
    quote_unrecoverable: int = 0
    indeterminate: int = 0
    instances: list[AttributionInstance] = field(default_factory=list)

    def add(self, other: "AttributionStats") -> None:
        self.total += other.total
        self.match += other.match
        self.model_wrong += other.model_wrong
        self.parser_gap += other.parser_gap
        self.quote_unrecoverable += other.quote_unrecoverable
        self.indeterminate += other.indeterminate
        self.instances.extend(other.instances)

    @property
    def comparable(self) -> int:
        """Claims where a parser turn was detected and resolved, so the
        model-vs-parser comparison is valid (match + model_wrong)."""
        return self.match + self.model_wrong

    @property
    def attribution_error_rate(self) -> float:
        """Bucket-1 ONLY, over comparable claims. Buckets 2/3/indeterminate are
        NOT in the denominator — they are not valid model-vs-parser comparisons."""
        return self.model_wrong / self.comparable if self.comparable else 0.0


def _resolve(store: CanonicalStore, label: str | None) -> str | None:
    if not label:
        return None
    hit = store.lookup(label, entity_type="person")
    return hit.entity_id if hit else None


def classify_claim(
    chunk: ChunkRecord, claim, canonical_store: CanonicalStore
) -> AttributionInstance:
    """Classify one claim into exactly one bucket (see module docstring)."""
    span = find_quote(chunk.text, claim.quote)
    model_id = _resolve(canonical_store, claim.speaker) or claim.speaker
    if span is None:
        return AttributionInstance(
            chunk.chunk_id, BUCKET_QUOTE_UNRECOVERABLE,
            claim.predicate, claim.quote, model_id, None, None,
        )

    labels = _labels(chunk.text)
    parser_lbl = _containing(labels, span[0], parser_only=True)
    aug_lbl = _containing(labels, span[0], parser_only=False)
    parser_id = _resolve(canonical_store, parser_lbl.speaker if parser_lbl else None)
    aug_id = _resolve(canonical_store, aug_lbl.speaker if aug_lbl else None)

    # MATCH: model agrees with the parser-detected containing turn.
    if parser_id is not None and model_id == parser_id:
        bucket = BUCKET_MATCH
    # PARSER-GAP (bucket 2): the nearest label under augmented segmentation is a
    # blind-spot LABEL_RE can't see, and the model correctly named that speaker.
    elif (aug_lbl is not None and not aug_lbl.parser_detected
          and aug_id is not None and model_id == aug_id):
        bucket = BUCKET_PARSER_GAP
    # No turn could be established at all → indeterminate (reported, not blended).
    elif parser_id is None and aug_id is None:
        bucket = BUCKET_INDETERMINATE
    # Everything else is a genuine attribution error (bucket 1).
    else:
        bucket = BUCKET_MODEL_WRONG

    return AttributionInstance(
        chunk.chunk_id, bucket, claim.predicate, claim.quote,
        model_id, parser_id, aug_id,
    )


def validate_chunk(
    chunk: ChunkRecord, extraction: ChunkExtraction, canonical_store: CanonicalStore
) -> AttributionStats:
    stats = AttributionStats()
    for claim in extraction.claims:
        inst = classify_claim(chunk, claim, canonical_store)
        stats.total += 1
        setattr(stats, inst.bucket, getattr(stats, inst.bucket) + 1)
        stats.instances.append(inst)
    return stats


def validate(
    claim_inputs: list[tuple[ChunkRecord, ChunkExtraction]],
    canonical_store: CanonicalStore,
) -> AttributionStats:
    total = AttributionStats()
    for chunk, extraction in claim_inputs:
        total.add(validate_chunk(chunk, extraction, canonical_store))
    return total


def format_report(stats: AttributionStats) -> str:
    """Three-bucket breakdown. The canary's Tier 1 attribution invariant is the
    bucket-1 (MODEL-WRONG) rate ONLY; buckets 2/3 are reported and explained."""
    lines = [
        "## Turn-speaker attribution (pre-step B)",
        "",
        f"- claims checked:        {stats.total}",
        f"- comparable (b1 denom): {stats.comparable}  (match + model_wrong)",
        f"- MATCH:                 {stats.match}",
        f"- bucket 1 MODEL-WRONG:  {stats.model_wrong}  "
        f"→ attribution-error rate = {stats.attribution_error_rate:.3f} "
        f"(THE canary Tier-1 attribution invariant)",
        f"- bucket 2 PARSER-GAP:   {stats.parser_gap}  "
        f"(absorbed COMMISSIONER <surname> turns; model right, parser wrong; "
        f"→ turns.py re-chunk milestone, NOT a model error, NOT a canary RED)",
        f"- bucket 3 QUOTE-UNRECOVERABLE: {stats.quote_unrecoverable}  "
        f"(fabricated/unfindable quote; Tier-1 quote gate; excluded from rate)",
    ]
    if stats.indeterminate:
        lines.append(
            f"- indeterminate:         {stats.indeterminate}  "
            f"(no turn establishable; reported, excluded from rate)"
        )
    if stats.model_wrong:
        lines += ["", "### bucket 1 (MODEL-WRONG) instances — for Tier 3 human read"]
        for i in stats.instances:
            if i.bucket != BUCKET_MODEL_WRONG:
                continue
            lines.append(
                f"- chunk {i.chunk_id[:12]} | model={i.model_speaker} "
                f"turn={i.turn_speaker} | {i.claim_text!r} | quote={i.quote!r}"
            )
    return "\n".join(lines)
