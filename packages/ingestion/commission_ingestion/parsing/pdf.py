"""PyMuPDF page extraction and the scanned/image-only detector.

Thin wrapper over fitz: pull per-page raw text plus char counts so downstream
stages keep page provenance, and flag image-only PDFs (which would yield empty
chunks) rather than emitting silent empties.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

# Below this mean chars/page a PDF is almost certainly image-only (needs OCR).
# The live Madlanga corpus runs ~1,300 chars/page; 0 of 108 fall under this.
SCANNED_MEAN_CHARS_PER_PAGE = 100


@dataclass(frozen=True)
class PageText:
    page_no: int  # 1-based PDF page number
    text: str
    char_count: int


def extract_pages(path: str | Path) -> list[PageText]:
    """Extract raw text per page. page_no is 1-based to match human page talk."""
    pages: list[PageText] = []
    with fitz.open(path) as doc:
        for index in range(doc.page_count):
            text = doc[index].get_text()
            pages.append(
                PageText(page_no=index + 1, text=text, char_count=len(text))
            )
    return pages


def mean_chars_per_page(pages: list[PageText]) -> float:
    if not pages:
        return 0.0
    return sum(p.char_count for p in pages) / len(pages)


def is_scanned(pages: list[PageText]) -> bool:
    """True if the PDF looks image-only (would need OCR before parsing)."""
    return mean_chars_per_page(pages) < SCANNED_MEAN_CHARS_PER_PAGE
