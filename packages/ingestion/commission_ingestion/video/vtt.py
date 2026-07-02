"""WebVTT caption parsing and time-provenance segmenting.

Hand-rolled parser (no dependency) for the two caption shapes this pipeline
meets: YouTube auto-generated captions (rolling two-line cues with inline
``<00:00:01.199><c>`` word timing tags and heavy line repetition) and plain
manually-authored VTT. Output is a list of clean, deduplicated cues which
``segment_cues`` packs into retrieval-sized segments whose provenance is a
time range (seconds into the video) instead of a PDF page range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from commission_ingestion.parsing.chunking import CHUNK_MAX_CHARS

_TIMESTAMP_RE = re.compile(
    r"(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})[.,](?P<ms>\d{3})"
)
_CUE_LINE_RE = re.compile(
    r"^\s*(?P<start>[\d:.,]+)\s+-->\s+(?P<end>[\d:.,]+)"
)
_INLINE_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class CaptionCue:
    """One caption cue: payload lines visible from ``start`` to ``end`` (seconds).

    Lines are kept separate (not joined) because YouTube auto captions roll:
    each cue re-displays the previous cue's last line, and the repetition is
    only detectable line by line.
    """

    start: float
    end: float
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass(frozen=True)
class CaptionSegment:
    """A retrieval-sized run of consecutive cues with a time range."""

    text: str
    time_start: float
    time_end: float
    n_cues: int

    @property
    def char_count(self) -> int:
        return len(self.text)


def parse_timestamp(value: str) -> float | None:
    """``HH:MM:SS.mmm`` or ``MM:SS.mmm`` to seconds; None when malformed."""
    match = _TIMESTAMP_RE.fullmatch(value.strip())
    if match is None:
        return None
    hours = int(match.group("h") or 0)
    return (
        hours * 3600.0
        + int(match.group("m")) * 60.0
        + int(match.group("s"))
        + int(match.group("ms")) / 1000.0
    )


def _clean_line(line: str) -> str:
    return _WS_RE.sub(" ", _INLINE_TAG_RE.sub("", line)).strip()


def parse_vtt(text: str) -> list[CaptionCue]:
    """Parse WebVTT into cues. Tolerant: skips headers, NOTE/STYLE blocks,
    cue identifiers, settings after the end timestamp, and empty cues."""
    cues: list[CaptionCue] = []
    current: tuple[float, float] | None = None
    lines_buffer: list[str] = []

    def flush() -> None:
        nonlocal current, lines_buffer
        if current is not None and lines_buffer:
            cues.append(
                CaptionCue(start=current[0], end=current[1], lines=tuple(lines_buffer))
            )
        current, lines_buffer = None, []

    for raw_line in text.splitlines():
        line = raw_line.lstrip("﻿").rstrip("\r")
        cue_match = _CUE_LINE_RE.match(line)
        if cue_match:
            flush()
            start = parse_timestamp(cue_match.group("start"))
            end = parse_timestamp(cue_match.group("end"))
            if start is None or end is None:
                current = None
                continue
            current = (start, end)
            continue
        if line.strip() == "" and line != "":
            # YouTube auto captions pad cues with a single-space payload line;
            # only a truly empty line terminates the cue.
            continue
        if line == "":
            flush()
            continue
        if current is not None:
            cleaned = _clean_line(line)
            if cleaned:
                lines_buffer.append(cleaned)
    flush()
    return cues


def dedupe_rolling(cues: list[CaptionCue]) -> list[CaptionCue]:
    """Collapse YouTube auto-caption rolling repetition.

    Auto captions re-display the previous cue's line(s) while the next line
    types in, so consecutive cues share payload lines. Keep, per cue, only
    the lines not shown by the previous cue; drop cues that add nothing.
    Manual captions (no repetition) pass through unchanged.
    """
    result: list[CaptionCue] = []
    prev_lines: tuple[str, ...] = ()
    for cue in cues:
        new_lines = tuple(line for line in cue.lines if line not in prev_lines)
        if new_lines:
            result.append(CaptionCue(start=cue.start, end=cue.end, lines=new_lines))
        prev_lines = cue.lines
    return result


def segment_cues(
    cues: list[CaptionCue], *, max_chars: int = CHUNK_MAX_CHARS
) -> list[CaptionSegment]:
    """Pack consecutive cues into segments of at most ``max_chars``.

    A cue is never split; a single oversized cue becomes its own oversized
    segment (embedding truncation is preferable to fabricating a boundary
    inside one cue's time range).
    """
    segments: list[CaptionSegment] = []
    parts: list[str] = []
    seg_start = 0.0
    seg_end = 0.0
    n_cues = 0

    def flush() -> None:
        nonlocal parts, n_cues
        if parts:
            segments.append(
                CaptionSegment(
                    text=" ".join(parts),
                    time_start=seg_start,
                    time_end=seg_end,
                    n_cues=n_cues,
                )
            )
        parts, n_cues = [], 0

    for cue in cues:
        prospective = len(" ".join([*parts, cue.text]))
        if parts and prospective > max_chars:
            flush()
        if not parts:
            seg_start = cue.start
        parts.append(cue.text)
        seg_end = cue.end
        n_cues += 1
    flush()
    return segments
