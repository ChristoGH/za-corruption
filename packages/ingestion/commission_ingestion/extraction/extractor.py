"""LLM extraction over chunks — strict parse, one repair retry, dead-letter.

The Anthropic SDK is imported lazily behind the ``extract`` extra so the core
package and CI never depend on it; tests inject a fake client through the
``LLMClient`` protocol. Pricing constants follow the official model table —
keep them in sync with platform.claude.com/docs (cached 2026-06).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from commission_ingestion.extraction.cache import ExtractionCache
from commission_ingestion.extraction.schema import (
    PROMPT_VERSION,
    ChunkExtraction,
    load_prompt,
    output_json_schema,
)
from commission_ingestion.models.chunk_record import ChunkRecord

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"
MAX_OUTPUT_TOKENS = 4000

# USD per million tokens: (input, output). Batch API halves both.
MODEL_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


class LLMClient(Protocol):
    """The one call the extractor needs; satisfied by AnthropicLLMClient or a
    test fake. Returns (response_text, usage_dict)."""

    def complete(
        self, *, model: str, system: str, user: str, schema: dict, max_tokens: int
    ) -> tuple[str, dict]: ...


class AnthropicLLMClient:
    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - guard for missing extra
            raise ImportError(
                "the anthropic SDK is required for extraction; install the "
                "'extract' extra: uv sync --all-packages --all-extras"
            ) from exc
        self._client = anthropic.Anthropic()

    def complete(
        self, *, model: str, system: str, user: str, schema: dict, max_tokens: int
    ) -> tuple[str, dict]:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            # Stable prefix cached across the run (5-minute TTL refreshed per call).
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "refusal":
            raise ExtractionRefused(getattr(response, "stop_details", None))
        text = next((b.text for b in response.content if b.type == "text"), "")
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", 0) or 0,
        }
        return text, usage


class ExtractionRefused(Exception):
    """Safety classifiers declined the request — dead-letter, don't crash."""


def cost_usd(usage: dict, model: str) -> float:
    in_price, out_price = MODEL_PRICES_PER_MTOK[model]
    return (
        usage.get("input_tokens", 0) * in_price
        + usage.get("cache_creation_input_tokens", 0) * in_price * CACHE_WRITE_FACTOR
        + usage.get("cache_read_input_tokens", 0) * in_price * CACHE_READ_FACTOR
        + usage.get("output_tokens", 0) * out_price
    ) / 1_000_000


def chunk_user_message(chunk: ChunkRecord) -> str:
    """Per-chunk content — provenance metadata comes from the registry/chunk
    record only; the model never derives day/date (in-PDF footers lie)."""
    speakers = ", ".join(chunk.speakers)
    return (
        f"Hearing day {chunk.day_no} ({chunk.date}), "
        f"pages {chunk.page_start}-{chunk.page_end}. Speakers: {speakers}.\n"
        f"--- CHUNK TEXT ---\n{chunk.text}"
    )


def parse_extraction(text: str) -> ChunkExtraction:
    return ChunkExtraction.model_validate_json(text)


@dataclass
class ExtractOutcome:
    chunk_id: str
    status: str  # "cached" | "extracted" | "dead_letter"
    cost_usd: float = 0.0


def extract_chunk(
    client: LLMClient,
    cache: ExtractionCache,
    chunk: ChunkRecord,
    *,
    model: str = DEFAULT_MODEL,
) -> ExtractOutcome:
    """Extract one chunk with caching, strict parsing, one repair retry, and
    dead-lettering. Never raises on a malformed response."""
    if cache.has(chunk.chunk_id, PROMPT_VERSION, model):
        return ExtractOutcome(chunk.chunk_id, "cached")

    system = load_prompt()
    user = chunk_user_message(chunk)
    schema = output_json_schema()
    total_cost = 0.0
    raw = ""

    for attempt in ("first", "repair"):
        try:
            if attempt == "repair":
                user_msg = (
                    user
                    + "\n\nYour previous response was not valid against the schema:\n"
                    + raw[:2000]
                    + "\nReturn ONLY the corrected JSON object."
                )
            else:
                user_msg = user
            raw, usage = client.complete(
                model=model, system=system, user=user_msg,
                schema=schema, max_tokens=MAX_OUTPUT_TOKENS,
            )
            call_cost = cost_usd(usage, model)
            total_cost += call_cost
            cache.log_spend({
                "chunk_id": chunk.chunk_id, "model": model,
                "prompt_version": PROMPT_VERSION, "attempt": attempt,
                "usage": usage, "cost_usd": call_cost,
            })
            extraction = parse_extraction(raw)
        except ExtractionRefused as exc:
            cache.dead_letter(
                chunk_id=chunk.chunk_id, model=model, prompt_version=PROMPT_VERSION,
                error=f"refusal: {exc}", raw_response="",
            )
            return ExtractOutcome(chunk.chunk_id, "dead_letter", total_cost)
        except (ValidationError, ValueError) as exc:
            logger.warning("parse failure (%s attempt) for %s: %s",
                           attempt, chunk.chunk_id[:16], exc)
            if attempt == "repair":
                cache.dead_letter(
                    chunk_id=chunk.chunk_id, model=model,
                    prompt_version=PROMPT_VERSION,
                    error=str(exc), raw_response=raw,
                )
                return ExtractOutcome(chunk.chunk_id, "dead_letter", total_cost)
            continue

        cache.put(chunk.chunk_id, PROMPT_VERSION, model, {
            "chunk_id": chunk.chunk_id,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "extraction": extraction.model_dump(),
        })
        return ExtractOutcome(chunk.chunk_id, "extracted", total_cost)

    raise AssertionError("unreachable")
