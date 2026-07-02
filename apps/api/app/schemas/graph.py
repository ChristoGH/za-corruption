"""Chunk-neighborhood response schema.

Invariant 4: mentions and claims are SEPARATE, separately-typed fields and are
never merged. A mention is a lead; a claim is attributed testimony. Each claim
carries its claim_id (the join key for /claim/{id}), its stored status, and its
STATED_BY speaker, which is required: a claim with no attribution is rejected.
"""

from __future__ import annotations

from pydantic import BaseModel


class Mentions(BaseModel):
    """Entities MENTIONED_IN the chunk, grouped by label. Leads, not findings."""

    person: list[str] = []
    org: list[str] = []
    place: list[str] = []


class ClaimBrief(BaseModel):
    """A claim SUPPORTED_BY the chunk. status is stored, never synthesised;
    speaker (STATED_BY) is required so an unattributed claim is never rendered."""

    claim_id: str
    status: str
    speaker: str
    speaker_unresolved: bool = False
    quote: str | None = None
    text: str | None = None


class ChunkGraphResponse(BaseModel):
    chunk_id: str
    text: str | None = None
    commission_slug: str | None = None
    day_no: int | None = None
    date: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_url: str | None = None
    authoritative: bool | None = None
    mentions: Mentions
    speakers: list[str] = []
    claims: list[ClaimBrief] = []
