"""Pure descriptive statistics over speaker turns — no plotting dependencies.

Role attribution is deliberately conservative and auditable (Post #1 is about
structure, not characterisation):

- **bench**  — CHAIRPERSON / COMMISSIONER (reliable from the label).
- **witness** — per day, the non-bench speaker who answers the most questions
  (a turn immediately following a different speaker's question). "ADV BEHARI"
  can be the witness, so this is detected from behaviour, not the title.
- **counsel** — everyone else (evidence leaders + party representatives).

A caller-supplied ``role_map`` (speaker label -> role) overrides the heuristic,
so a human can correct or refine attribution before anything is published.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from commission_ingestion.parsing.turns import Turn

BENCH_PREFIXES = ("CHAIRPERSON", "COMMISSIONER", "THE CHAIRPERSON", "THE COMMISSIONER")
ROLES = ("bench", "witness", "counsel")

# Minimum answer-turns before we are willing to call a speaker "the witness".
WITNESS_MIN_ANSWERS = 5
# A speaker appearing on at least this many hearing days is counsel, not a witness
# (the standing legal teams recur; witnesses testify in short blocks).
COUNSEL_MIN_DAYS = 10
_WORD_RE = re.compile(r"\b[\w'-]+\b")
_SC_RE = re.compile(r"\bSC\b")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def is_bench(label: str) -> bool:
    return label.startswith(BENCH_PREFIXES)


def has_sc(label: str) -> bool:
    """Senior Counsel suffix — a reliable 'this is counsel, not a witness' signal."""
    return bool(_SC_RE.search(label))


def infer_counsel_labels(days_turns: list[list[Turn]]) -> frozenset[str]:
    """Corpus-wide counsel set: any speaker with 'SC' or present on many days."""
    days_present: Counter[str] = Counter()
    for turns in days_turns:
        for label in {t.speaker for t in turns}:
            days_present[label] += 1
    counsel = {
        label
        for label, days in days_present.items()
        if has_sc(label) or days >= COUNSEL_MIN_DAYS
    }
    return frozenset(counsel)


def detect_witness(
    turns: list[Turn], counsel_labels: frozenset[str] = frozenset()
) -> str | None:
    """The witness-candidate answering the most questions this day, if clear.

    Excludes the bench, Senior Counsel, and corpus-inferred counsel — so counsel
    answering the Chairperson's procedural questions are not mistaken for witnesses.
    """
    answers: Counter[str] = Counter()
    for i, turn in enumerate(turns):
        if i == 0:
            continue
        prev = turns[i - 1]
        speaker = turn.speaker
        if (
            prev.speaker != speaker
            and prev.text.rstrip().endswith("?")
            and not is_bench(speaker)
            and not has_sc(speaker)
            and speaker not in counsel_labels
        ):
            answers[speaker] += 1
    if not answers:
        return None
    speaker, count = answers.most_common(1)[0]
    return speaker if count >= WITNESS_MIN_ANSWERS else None


def role_of(label: str, witness: str | None, role_map: dict[str, str] | None) -> str:
    if role_map and label in role_map:
        return role_map[label]
    if is_bench(label):
        return "bench"
    if witness and label == witness:
        return "witness"
    return "counsel"


@dataclass
class DayStats:
    day_no: int | None
    date: str | None
    n_pages: int
    n_turns: int
    n_words: int
    witness: str | None
    median_turn_words: float
    speakers: dict[str, int] = field(default_factory=dict)  # label -> words
    role_words: dict[str, int] = field(default_factory=dict)  # role -> words


def aggregate_day(
    *,
    day_no: int | None,
    date: str | None,
    n_pages: int,
    turns: list[Turn],
    role_map: dict[str, str] | None = None,
    counsel_labels: frozenset[str] = frozenset(),
) -> DayStats:
    witness = detect_witness(turns, counsel_labels)
    speakers: Counter[str] = Counter()
    role_words: Counter[str] = Counter()
    turn_lengths: list[int] = []
    for turn in turns:
        words = word_count(turn.text)
        speakers[turn.speaker] += words
        role_words[role_of(turn.speaker, witness, role_map)] += words
        turn_lengths.append(words)
    return DayStats(
        day_no=day_no,
        date=date,
        n_pages=n_pages,
        n_turns=len(turns),
        n_words=sum(turn_lengths),
        witness=witness,
        median_turn_words=statistics.median(turn_lengths) if turn_lengths else 0.0,
        speakers=dict(speakers),
        role_words=dict(role_words),
    )


def summarise(
    days: list[DayStats],
    *,
    n_chunks: int | None = None,
    role_map_applied: bool = False,
) -> dict:
    """Roll day stats into the headline JSON the Post #1 copy is generated from."""
    days_sorted = sorted(days, key=lambda d: (d.day_no is None, d.day_no or 0))
    role_totals: Counter[str] = Counter()
    speaker_words: Counter[str] = Counter()
    speaker_days: Counter[str] = Counter()
    for d in days_sorted:
        for role, w in d.role_words.items():
            role_totals[role] += w
        for label, w in d.speakers.items():
            speaker_words[label] += w
            speaker_days[label] += 1

    total_words = sum(role_totals.values())
    role_share = {
        r: round(100 * role_totals.get(r, 0) / total_words, 1) if total_words else 0.0
        for r in ROLES
    }

    return {
        "totals": {
            "hearing_days": len(days_sorted),
            "pages": sum(d.n_pages for d in days_sorted),
            "turns": sum(d.n_turns for d in days_sorted),
            "words": total_words,
            "chunks": n_chunks,
            "distinct_speaker_labels": len(speaker_words),
        },
        "role_attribution": {
            # Heuristic: bench from labels; witness = per-day question-answerer
            # excluding Senior Counsel and recurring counsel. PROVISIONAL — verify
            # the per-day 'witness' column and override via --role-map before
            # publishing the role-share chart.
            "method": "role_map" if role_map_applied else "heuristic",
            "reviewed": role_map_applied,
            "days_with_witness": sum(1 for d in days_sorted if d.witness),
            "days_total": len(days_sorted),
        },
        "role_word_share_pct": role_share,
        "role_words": dict(role_totals),
        "per_day": [
            {
                "day_no": d.day_no,
                "date": d.date,
                "pages": d.n_pages,
                "turns": d.n_turns,
                "words": d.n_words,
                "median_turn_words": d.median_turn_words,
                "witness": d.witness,
            }
            for d in days_sorted
        ],
        "speakers": {
            label: {"words": speaker_words[label], "days": speaker_days[label]}
            for label, _ in speaker_words.most_common()
        },
    }
