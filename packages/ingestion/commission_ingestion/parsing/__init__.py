"""Deterministic parsing: PDF text -> cleaned, reflowed -> speaker turns -> chunks.

Format verified against the live Madlanga corpus (see docs/parse-notes.md):
born-digital text, line-initial uppercase colon-terminated speaker labels, with
two hazards handled here — interleaved margin line-number tokens, and PyMuPDF
emitting one word per line on some pages (so we reflow before segmenting).
"""

from __future__ import annotations

from commission_ingestion.parsing.chunking import chunk_turns
from commission_ingestion.parsing.clean import reflow_pages
from commission_ingestion.parsing.pdf import PageText, extract_pages, is_scanned
from commission_ingestion.parsing.turns import Turn, detect_turns

__all__ = [
    "PageText",
    "extract_pages",
    "is_scanned",
    "reflow_pages",
    "Turn",
    "detect_turns",
    "chunk_turns",
]
