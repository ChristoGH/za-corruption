"""Adapter over Neo4jStore's read methods.

Holds no Cypher (it lives in the package store, invariant 2): it shapes the
store's dicts into API schemas and enforces the legal invariants structurally.
Mentions and claims stay separate (invariant 4); a claim with no STATED_BY
speaker raises rather than render unattributed (invariant 5).
"""

from __future__ import annotations

from typing import Any

from ..schemas.claims import ClaimDetailResponse, ClaimMention
from ..schemas.graph import ChunkGraphResponse, ClaimBrief, Mentions


def chunk_graph(store: Any, chunk_id: str) -> ChunkGraphResponse | None:
    data = store.chunk_neighborhood(chunk_id)
    if data is None:
        return None
    chunk = data.get("chunk") or {}
    document = data.get("document") or {}
    hearing = data.get("hearing") or {}
    mentions = data.get("mentions") or {}
    return ChunkGraphResponse(
        chunk_id=chunk.get("chunk_id"),
        text=chunk.get("text"),
        commission_slug=chunk.get("commission_slug") or document.get("commission_slug"),
        day_no=chunk.get("day_no") if chunk.get("day_no") is not None else hearing.get("day_no"),
        date=hearing.get("date"),
        page_start=chunk.get("page_start"),
        page_end=chunk.get("page_end"),
        source_url=document.get("source_url"),
        authoritative=document.get("authoritative"),
        mentions=Mentions(
            person=mentions.get("person") or [],
            org=mentions.get("org") or [],
            place=mentions.get("place") or [],
        ),
        speakers=data.get("speakers") or [],
        # ClaimBrief requires claim_id + status + speaker, so an unattributed or
        # un-joinable claim is rejected here rather than rendered (invariants 4/5).
        claims=[
            ClaimBrief(
                claim_id=c.get("claim_id"),
                status=c.get("status"),
                speaker=c.get("speaker"),
                speaker_unresolved=bool(c.get("speaker_unresolved")),
                quote=c.get("quote"),
                text=c.get("text"),
            )
            for c in (data.get("claims") or [])
        ],
    )


def claim_detail(store: Any, claim_id: str) -> ClaimDetailResponse | None:
    data = store.claim_detail(claim_id)
    if data is None:
        return None
    claim = data.get("claim") or {}
    speaker = data.get("speaker")
    if not speaker:
        # invariant 5: a claim with no STATED_BY is an integrity violation; never
        # present an unattributed allegation as if it stood on its own.
        raise ValueError(
            f"claim {claim_id} has no STATED_BY speaker; refusing to render "
            "an unattributed allegation"
        )
    chunk = data.get("chunk") or {}
    return ClaimDetailResponse(
        claim_id=claim.get("claim_id"),
        status=claim.get("status"),
        speaker=speaker,
        speaker_unresolved=bool(claim.get("speaker_unresolved")),
        quote=claim.get("quote"),
        text=claim.get("text"),
        certainty=claim.get("certainty"),
        attribution=claim.get("attribution"),
        chunk_id=chunk.get("chunk_id"),
        day_no=chunk.get("day_no"),
        page_start=chunk.get("page_start"),
        page_end=chunk.get("page_end"),
        source_url=data.get("source_url"),
        mentions=[
            ClaimMention(
                name=m.get("name"),
                role=m.get("role"),
                labels=m.get("labels") or [],
            )
            for m in (data.get("mentions") or [])
        ],
    )
