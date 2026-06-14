"""Stratified, seeded, frozen chunk sampler for the cross-model eval.

The sample is drawn once, deterministically, and frozen to disk as an
auditable chunk-id list. Strata target the corpus's known failure axes; a
chunk is assigned to the FIRST stratum it matches (priority order below), so
strata are disjoint and per-stratum metrics are clean.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.resolution.canonical import (
    CanonicalStore,
    normalise,
    strip_titles,
)

STRATA = (
    "ambiguous_surname",
    "ocr_variant",
    "high_acronym",
    "allegation_dense",
    "control",
)
HARD_STRATA = frozenset(STRATA[:-1])

DEFAULT_SAMPLE_SIZE = 40
DEFAULT_SEED = 17

# Procedural labels that alias to a person but are not OCR damage — they would
# otherwise swallow the ocr_variant stratum (CHAIRPERSON appears everywhere).
_PROCEDURAL_FORMS = frozenset({"CHAIRPERSON", "THE CHAIRPERSON", "WITNESS", "WITNESS A"})

# Speaker-attribution / reported-speech markers (the allegation-density signal).
_ALLEGATION_RE = re.compile(
    r"\b(stated|testified|alleged|allegation|said|told|instructed|claimed|"
    r"denied|reported|accused|according to)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"\b[\w'-]+\b")

DEFAULT_ACRONYM_PER_1K = 6.0
DEFAULT_ALLEGATION_PER_1K = 12.0


def ambiguous_bare_surnames(store: CanonicalStore) -> set[str]:
    """Bare (title-stripped) person forms owned by MORE than one canonical
    entity — the four-Khumalos class. These never resolve; chunks containing
    them are where conflation would happen."""
    owners: dict[str, set[str]] = {}
    for entity in store.entities:
        if entity.entity_type != "person":
            continue
        for form in entity.surface_forms():
            bare = strip_titles(form)
            if bare:
                owners.setdefault(bare, set()).add(entity.entity_id)
    return {bare for bare, ids in owners.items() if len(ids) > 1}


def ocr_variant_forms(store: CanonicalStore) -> set[str]:
    """Person alias forms that resolve ONLY via the alias index — they share no
    surname token with the canonical name even after title-stripping (split or
    misspelled counsel labels: 'ADV CH ASK ALSON SC', 'MR NCAZI', ...)."""
    forms: set[str] = set()
    for entity in store.entities:
        if entity.entity_type != "person":
            continue
        name_tokens = set(strip_titles(normalise(entity.name)).split())
        for alias in entity.aliases:
            form = normalise(alias)
            if form in _PROCEDURAL_FORMS:
                continue
            alias_tokens = set(strip_titles(form).split())
            if alias_tokens and not (alias_tokens & name_tokens):
                forms.add(form)
    return forms


def acronym_forms(store: CanonicalStore) -> set[str]:
    """Short all-caps alias forms in the org/place groups (SAPS/PKTT/KZN-class)."""
    forms: set[str] = set()
    for entity in store.entities:
        if entity.entity_type not in ("org", "acronym", "place"):
            continue
        for form in entity.surface_forms():
            if re.fullmatch(r"[A-Z]{2,6}", form):
                forms.add(form)
    return forms


@dataclass(frozen=True)
class StratumContext:
    ambiguous_res: list[re.Pattern]
    ocr_res: list[re.Pattern]
    acronym_res: list[re.Pattern]
    acronym_per_1k: float
    allegation_per_1k: float

    @classmethod
    def from_store(
        cls,
        store: CanonicalStore,
        *,
        acronym_per_1k: float = DEFAULT_ACRONYM_PER_1K,
        allegation_per_1k: float = DEFAULT_ALLEGATION_PER_1K,
    ) -> "StratumContext":
        def patterns(forms: set[str]) -> list[re.Pattern]:
            return [
                re.compile(r"\b" + re.escape(f) + r"\b", re.IGNORECASE)
                for f in sorted(forms)
            ]

        return cls(
            ambiguous_res=patterns(ambiguous_bare_surnames(store)),
            ocr_res=patterns(ocr_variant_forms(store)),
            acronym_res=[
                re.compile(r"\b" + re.escape(f) + r"\b") for f in sorted(acronym_forms(store))
            ],
            acronym_per_1k=acronym_per_1k,
            allegation_per_1k=allegation_per_1k,
        )


def classify_chunk(chunk: ChunkRecord, ctx: StratumContext) -> str:
    """First matching stratum in priority order; 'control' when none match.

    Ambiguity caveat for the surname stratum: a bare-surname regex also hits
    inside a fully-titled form ('LT-GEN KHUMALO' contains 'KHUMALO'), which is
    fine — those chunks are exactly where a weaker model may drop the rank and
    emit the conflatable bare form.
    """
    text = chunk.text
    n_words = max(1, len(_WORD_RE.findall(text)))

    if any(p.search(text) for p in ctx.ambiguous_res):
        return "ambiguous_surname"
    if any(p.search(text) for p in ctx.ocr_res):
        return "ocr_variant"
    acronym_hits = sum(len(p.findall(text)) for p in ctx.acronym_res)
    if 1000 * acronym_hits / n_words >= ctx.acronym_per_1k:
        return "high_acronym"
    allegation_hits = len(_ALLEGATION_RE.findall(text))
    if 1000 * allegation_hits / n_words >= ctx.allegation_per_1k:
        return "allegation_dense"
    return "control"


@dataclass(frozen=True)
class SampledChunk:
    chunk_id: str
    stratum: str


def build_sample(
    chunks: list[ChunkRecord],
    store: CanonicalStore,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    ctx: StratumContext | None = None,
) -> list[SampledChunk]:
    """Deterministic stratified sample: equal quota per stratum, leftover
    capacity redistributed in stratum order, selection by seeded RNG over
    chunk-id-sorted candidates. Same (chunks, store, seed) → identical sample.
    """
    ctx = ctx or StratumContext.from_store(store)
    by_stratum: dict[str, list[ChunkRecord]] = {s: [] for s in STRATA}
    for chunk in sorted(chunks, key=lambda c: c.chunk_id):
        by_stratum[classify_chunk(chunk, ctx)].append(chunk)

    rng = random.Random(seed)
    quota = {s: sample_size // len(STRATA) for s in STRATA}
    # Redistribute capacity from under-filled strata (deterministic order).
    spare = sample_size - sum(min(quota[s], len(by_stratum[s])) for s in STRATA)
    while spare > 0:
        progressed = False
        for s in STRATA:
            if spare <= 0:
                break
            if len(by_stratum[s]) > quota[s]:
                quota[s] += 1
                spare -= 1
                progressed = True
        if not progressed:
            break  # corpus smaller than sample_size

    selected: list[SampledChunk] = []
    for stratum in STRATA:
        candidates = by_stratum[stratum]
        take = min(quota[stratum], len(candidates))
        for chunk in sorted(rng.sample(candidates, take), key=lambda c: c.chunk_id):
            selected.append(SampledChunk(chunk_id=chunk.chunk_id, stratum=stratum))
    return selected


def freeze_sample(sample: list[SampledChunk], artifacts_dir: Path, seed: int) -> Path:
    """Write the auditable frozen sample list. Refuses to silently change an
    existing frozen sample for the same seed."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / f"sample_{seed}.txt"
    body = "".join(f"{s.chunk_id}\t{s.stratum}\n" for s in sample)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != body:
            raise RuntimeError(
                f"{path} exists with DIFFERENT content — the frozen sample is "
                "an audit artifact; delete it explicitly if you mean to resample"
            )
        return path
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    return path


def load_sample(path: Path) -> list[SampledChunk]:
    sample = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunk_id, stratum = line.split("\t")
            sample.append(SampledChunk(chunk_id=chunk_id, stratum=stratum))
    return sample
