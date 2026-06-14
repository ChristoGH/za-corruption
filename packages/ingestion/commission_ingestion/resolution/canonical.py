"""Canonical entity store — the human-owned side of entity resolution.

The store is a YAML file of canonical entities with aliases. The resolver only
ever *matches against* this store; it never adds to it. A human approves a
merge by adding an alias here and re-running resolution — resolution is a pure
function of (extractions, this store).

Alias matching is on the FULL normalized surface form. Surname-only aliases
are forbidden by design: this corpus alone has four distinct Khumalos, and a
wrong merge attaches one person's allegations to another person's node — the
exact failure defamation hygiene exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ENTITY_TYPES = ("person", "org", "role", "place", "acronym")

DEFAULT_SEED_PATH = Path(__file__).parent / "seed_entities.yaml"

# Title/rank/honorific tokens — used only for the *unambiguous* bare-form
# index (see CanonicalStore.bare_index): a title-stripped form is matchable
# only if exactly one canonical entity owns it.
_TITLE_TOKENS = frozenset(
    "ADV ADVOCATE MR MRS MS MISS DR PROF JUSTICE JUDGE MINISTER GENERAL GEN "
    "LT-GEN MAJ-GEN BRIG COL CAPT MAJ SGT SERGEANT CONST W/O LIEUTENANT THE SC ISC".split()
)

_NON_ALNUM_RE = re.compile(r"[^A-Z0-9\- ]+")
_WS_RE = re.compile(r"\s+")


def normalise(surface: str) -> str:
    """Canonical comparison form: uppercase, punctuation stripped, single spaces."""
    text = _NON_ALNUM_RE.sub(" ", surface.upper())
    return _WS_RE.sub(" ", text).strip()


def strip_titles(normalised: str) -> str:
    """Remove honorific/rank tokens — for the unambiguous bare index only."""
    kept = [tok for tok in normalised.split() if tok not in _TITLE_TOKENS]
    return " ".join(kept)


@dataclass
class CanonicalEntity:
    entity_id: str
    name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    note: str = ""

    def surface_forms(self) -> set[str]:
        """All normalized forms this entity answers to (name + aliases)."""
        forms = {normalise(self.name)}
        forms.update(normalise(a) for a in self.aliases if a.strip())
        return forms


# Acronyms resolve against organisations: an extracted "acronym" is almost
# always an org short-form (SAPS, PKTT), and canonical entries model them as
# org aliases.
_TYPE_GROUP = {
    "person": "person",
    "org": "org",
    "acronym": "org",
    "role": "role",
    "place": "place",
}


class CanonicalStore:
    """Indexes are scoped by entity-type group, so the same surface form can
    legitimately resolve differently by context — "CHAIRPERSON" is the person
    Justice Madlanga when resolving a speaker label, and the procedural role
    when resolving an extracted role entity. Collisions *within* a type group
    are a configuration error."""

    def __init__(self, entities: list[CanonicalEntity]) -> None:
        self.entities = entities
        self.by_id = {e.entity_id: e for e in entities}
        self.alias_index: dict[tuple[str, str], CanonicalEntity] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        for entity in self.entities:
            group = _TYPE_GROUP[entity.entity_type]
            for form in entity.surface_forms():
                key = (group, form)
                existing = self.alias_index.get(key)
                if existing is not None and existing.entity_id != entity.entity_id:
                    raise ValueError(
                        f"alias collision in type group {group!r}: {form!r} maps to "
                        f"both {existing.entity_id} and {entity.entity_id}"
                    )
                self.alias_index[key] = entity

        # Bare (title-stripped) index — only forms owned by exactly one entity
        # within the group, and not already a full-form alias there.
        owners: dict[tuple[str, str], set[str]] = {}
        for entity in self.entities:
            group = _TYPE_GROUP[entity.entity_type]
            for form in entity.surface_forms():
                bare = strip_titles(form)
                if bare and bare != form:
                    owners.setdefault((group, bare), set()).add(entity.entity_id)
        self.bare_index = {
            key: self.by_id[next(iter(ids))]
            for key, ids in owners.items()
            if len(ids) == 1 and key not in self.alias_index
        }

    def lookup(self, surface: str, entity_type: str = "person") -> CanonicalEntity | None:
        """Exact alias match on the full normalized form, then the unambiguous
        title-stripped form — both scoped to the entity type's group. Anything
        else is the resolver's problem (provisional or review queue)."""
        group = _TYPE_GROUP.get(entity_type, entity_type)
        form = normalise(surface)
        hit = self.alias_index.get((group, form))
        if hit is not None:
            return hit
        return self.bare_index.get((group, strip_titles(form)))


def load_store(path: Path | str = DEFAULT_SEED_PATH) -> CanonicalStore:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw_entities = data.get("entities") or []
    entities: list[CanonicalEntity] = []
    seen_ids: set[str] = set()
    for raw in raw_entities:
        entity_id = str(raw["id"])
        if entity_id in seen_ids:
            raise ValueError(f"duplicate canonical id: {entity_id}")
        seen_ids.add(entity_id)
        entity_type = str(raw["type"])
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"{entity_id}: unknown type {entity_type!r}")
        entities.append(
            CanonicalEntity(
                entity_id=entity_id,
                name=str(raw["name"]),
                entity_type=entity_type,
                aliases=[str(a) for a in (raw.get("aliases") or [])],
                note=str(raw.get("note") or ""),
            )
        )
    return CanonicalStore(entities)
