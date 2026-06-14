"""Extraction output schema — what the LLM must return per chunk.

Design rules (docs/defamation-hygiene.md):
- Claims are reported speech: who said what about whom, where. The schema has
  NO status field — extraction can never set one; the graph writer always
  writes ``status="alleged"``.
- Spans are verbatim quotes, not char offsets: LLMs are unreliable at
  character arithmetic, so offsets are computed deterministically in code by
  exact substring search (a quote that doesn't match is flagged, never
  guessed).
- ``PROMPT_VERSION`` is part of the extraction cache key — bump it whenever
  the prompt or this schema changes meaning, and the cache invalidates itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

PROMPT_VERSION = "extract_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"

EntityType = Literal["person", "org", "role", "place", "acronym"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedEntity(_Strict):
    ref: str  # chunk-local handle, e.g. "e1" — referenced by mentions/claims
    name: str  # exactly as written in the chunk, no normalization
    type: EntityType


class ExtractedMention(_Strict):
    entity_ref: str
    quote: str  # verbatim substring of the chunk containing the mention


class ExtractedClaim(_Strict):
    speaker: str  # speaker label exactly as it appears in the chunk
    subject_refs: list[str]  # entities the claim is about
    predicate: str  # neutral reported-speech summary ("stated that ...")
    object_refs: list[str]  # other entities involved, possibly empty
    quote: str  # verbatim supporting span from the chunk
    certainty: str | None  # the speaker's own hedging, verbatim-ish, or null


class ChunkExtraction(_Strict):
    entities: list[ExtractedEntity]
    mentions: list[ExtractedMention]
    claims: list[ExtractedClaim]


def output_json_schema() -> dict:
    """JSON schema for the API's structured-output format (strict-compatible:
    pydantic emits additionalProperties=false via extra='forbid')."""
    return ChunkExtraction.model_json_schema()


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def find_quote(chunk_text: str, quote: str) -> tuple[int, int] | None:
    """Deterministic offset recovery: exact match first, then a whitespace-
    tolerant fallback. Returns None when the quote is not really in the text —
    callers must flag, never guess."""
    index = chunk_text.find(quote)
    if index >= 0:
        return index, index + len(quote)
    # Whitespace-tolerant: collapse runs of whitespace on both sides.
    import re

    pattern = re.escape(quote)
    pattern = re.sub(r"(\\\s)+", r"\\s+", pattern.replace("\\ ", "\\s"))
    match = re.search(pattern, chunk_text)
    if match:
        return match.start(), match.end()
    return None
