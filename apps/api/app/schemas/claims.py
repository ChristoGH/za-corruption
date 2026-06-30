"""Claim-detail response schema.

Invariant 5: the claim is an allegation. status is read as stored (never a
synthesised "fact" shape); the STATED_BY speaker is required and never dropped;
the quote is the ground truth and text (predicate prose) is secondary. The
SUPPORTED_BY chunk carries the official source link and (nullable) page.
"""

from __future__ import annotations

from pydantic import BaseModel


class ClaimMention(BaseModel):
    name: str
    role: str | None = None
    labels: list[str] = []


class ClaimDetailResponse(BaseModel):
    claim_id: str
    status: str
    speaker: str
    speaker_unresolved: bool = False
    quote: str | None = None
    text: str | None = None
    certainty: str | None = None
    attribution: str | None = None
    # provenance of the SUPPORTED_BY chunk
    chunk_id: str | None = None
    day_no: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_url: str | None = None
    mentions: list[ClaimMention] = []
