"""Pack speaker turns into retrieval-sized chunks.

Pack consecutive turns up to CHUNK_MAX_CHARS without splitting a turn — except
an oversized single turn (some witnesses read long passages into the record;
the live corpus has 12k-char turns), which is split on sentence boundaries so no
chunk exceeds the embedding model's context. Page provenance is preserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from commission_ingestion.parsing.turns import Turn

CHUNK_MAX_CHARS = 1800
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!])\s+")


@dataclass
class Chunk:
    text: str
    speakers: list[str] = field(default_factory=list)
    n_turns: int = 0
    page_start: int = 0
    page_end: int = 0

    @property
    def char_count(self) -> int:
        return len(self.text)


def _render(turn: Turn) -> str:
    return f"{turn.speaker}: {turn.text}"


def _split_long_turn(turn: Turn) -> list[str]:
    """Split one oversized turn's rendered text into <= MAX pieces on sentences."""
    prefix = f"{turn.speaker}: "
    budget = CHUNK_MAX_CHARS - len(prefix)
    sentences = _SENTENCE_SPLIT_RE.split(turn.text)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > budget:  # a single very long sentence: hard-split
            if current:
                pieces.append(current)
                current = ""
            for i in range(0, len(sentence), budget):
                pieces.append(sentence[i : i + budget])
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > budget and current:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return [f"{prefix}{p}" for p in pieces]


def chunk_turns(turns: list[Turn]) -> list[Chunk]:
    chunks: list[Chunk] = []
    cur_parts: list[str] = []
    cur_speakers: list[str] = []
    cur_turns = 0
    cur_pstart = 0
    cur_pend = 0

    def flush() -> None:
        nonlocal cur_parts, cur_speakers, cur_turns, cur_pstart, cur_pend
        if not cur_parts:
            return
        chunks.append(
            Chunk(
                text="\n".join(cur_parts),
                speakers=list(cur_speakers),
                n_turns=cur_turns,
                page_start=cur_pstart,
                page_end=cur_pend,
            )
        )
        cur_parts, cur_speakers, cur_turns = [], [], 0

    def add_speaker(name: str) -> None:
        if name not in cur_speakers:
            cur_speakers.append(name)

    for turn in turns:
        rendered = _render(turn)

        if len(rendered) > CHUNK_MAX_CHARS:
            flush()
            for piece in _split_long_turn(turn):
                chunks.append(
                    Chunk(
                        text=piece,
                        speakers=[turn.speaker],
                        n_turns=1,
                        page_start=turn.page_start,
                        page_end=turn.page_end,
                    )
                )
            continue

        prospective = len("\n".join(cur_parts + [rendered]))
        if cur_parts and prospective > CHUNK_MAX_CHARS:
            flush()

        if not cur_parts:
            cur_pstart = turn.page_start
        cur_parts.append(rendered)
        add_speaker(turn.speaker)
        cur_turns += 1
        cur_pend = turn.page_end

    flush()
    return chunks
