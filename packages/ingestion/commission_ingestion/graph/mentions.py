"""spaCy-based entity mention detection for commission transcripts.

Lazily imports spaCy so the core package and CI never depend on it; tests
inject a fake detector through the MentionDetector protocol.

Install the extra first:
    uv sync --all-packages --all-extras
    python -m spacy download en_core_web_trf
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# spaCy NER label → ontology entity type (Person/Org/Place only).
_SPACY_TYPE_MAP: dict[str, str] = {
    "PERSON": "person",
    "ORG":    "org",
    "GPE":    "place",  # geo-political entity (country, city, state)
    "LOC":    "place",  # non-GPE location
    "FAC":    "place",  # facility (building, road, airport, etc.)
}


@dataclass(frozen=True)
class DetectedMention:
    surface: str       # verbatim as in the text — no normalisation
    entity_type: str   # "person" | "org" | "place"


@runtime_checkable
class MentionDetector(Protocol):
    def detect(self, text: str) -> list[DetectedMention]: ...


class SpacyDetector:
    """en_core_web_trf-backed detector — heavy (torch); import is lazy."""

    def __init__(self, model_name: str = "en_core_web_trf") -> None:
        try:
            import spacy
        except ImportError as exc:
            raise ImportError(
                "spaCy is required for NER detection; install the 'spacy' extra:\n"
                "  uv sync --all-packages --all-extras\n"
                f"  python -m spacy download {model_name}"
            ) from exc
        try:
            self._nlp = spacy.load(model_name)
        except OSError as exc:
            raise OSError(
                f"spaCy model '{model_name}' not found.\n"
                f"Run: python -m spacy download {model_name}"
            ) from exc

    def detect(self, text: str) -> list[DetectedMention]:
        doc = self._nlp(text)
        seen: set[tuple[str, str]] = set()
        results: list[DetectedMention] = []
        for ent in doc.ents:
            etype = _SPACY_TYPE_MAP.get(ent.label_)
            if etype is None:
                continue
            surface = ent.text.strip()
            if not surface:
                continue
            key = (surface, etype)
            if key not in seen:
                seen.add(key)
                results.append(DetectedMention(surface=surface, entity_type=etype))
        return results
