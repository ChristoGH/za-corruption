"""Furniture stripping and reflow, with per-character page provenance.

Two corpus-verified hazards drive this module (docs/parse-notes.md):

1. ~37k standalone margin line-number tokens (``10``, ``20`` …) extract as their
   own lines, interleaved mid-sentence — they must be dropped *before* reflow or
   they land inside turn text.
2. PyMuPDF emits one word per line on some pages, fragmenting sentences and even
   speaker labels — so we drop furniture line-by-line, then reflow surviving
   lines into one stream and segment on that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from commission_ingestion.parsing.pdf import PageText

# Standalone margin line-number token (the "every 10th line" numbers).
LINE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*$")
# Per-page running header: "19 NOVEMBER 2025 – DAY 36".
RUNNING_HEADER_RE = re.compile(
    r"^\s*\d{1,2}\s+[A-Z]+\s+\d{4}\s*[–-]\s*DAY\s+\d+\s*$"
)
# Per-page page marker: "Page 2 of 79".
PAGE_MARKER_RE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE)


def is_furniture(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    return bool(
        LINE_NUMBER_RE.match(s)
        or RUNNING_HEADER_RE.match(s)
        or PAGE_MARKER_RE.match(s)
    )


def clean_page_lines(text: str) -> list[str]:
    """Surviving content lines for one page (furniture and blanks removed)."""
    return [ln.strip() for ln in text.split("\n") if not is_furniture(ln)]


@dataclass(frozen=True)
class ReflowedDoc:
    text: str
    # page_at[i] is the 1-based PDF page number of character text[i].
    page_at: list[int]

    def page_of(self, char_index: int) -> int:
        if not self.page_at:
            return 0
        i = max(0, min(char_index, len(self.page_at) - 1))
        return self.page_at[i]


def reflow_pages(pages: list[PageText]) -> ReflowedDoc:
    """Drop furniture, join surviving lines into one whitespace-normalised stream,
    keeping a per-character map back to the source PDF page."""
    parts: list[str] = []
    page_at: list[int] = []
    for page in pages:
        for line in clean_page_lines(page.text):
            if not line:
                continue
            if parts:  # single space separator between surviving lines
                parts.append(" ")
                page_at.append(page.page_no)
            parts.append(line)
            page_at.extend([page.page_no] * len(line))
    text = "".join(parts)
    # Collapse any internal whitespace runs while keeping page_at aligned.
    return _collapse_whitespace(text, page_at)


def _collapse_whitespace(text: str, page_at: list[int]) -> ReflowedDoc:
    out_chars: list[str] = []
    out_pages: list[int] = []
    prev_space = False
    for ch, pg in zip(text, page_at):
        if ch.isspace():
            if prev_space:
                continue
            out_chars.append(" ")
            out_pages.append(pg)
            prev_space = True
        else:
            out_chars.append(ch)
            out_pages.append(pg)
            prev_space = False
    return ReflowedDoc(text="".join(out_chars).strip(), page_at=_trim(out_pages, out_chars))


def _trim(pages: list[int], chars: list[str]) -> list[int]:
    # Mirror the .strip() applied to the text so page_at stays length-aligned.
    start = 0
    end = len(chars)
    while start < end and chars[start] == " ":
        start += 1
    while end > start and chars[end - 1] == " ":
        end -= 1
    return pages[start:end]
