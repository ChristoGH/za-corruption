"""Speaker-turn detection on reflowed transcript text.

A turn boundary is a line-initial uppercase, colon-terminated speaker label.
Detection is by *positive vocabulary* (title prefixes / roles / examination
headings) rather than "any uppercase + colon", so procedural lines and stray
acronyms don't create false turns. Labels are normalised (whitespace/hyphen
drift, and examination headings collapse to the named counsel).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from commission_ingestion.parsing.clean import ReflowedDoc

# Title prefixes (longest-first within each family so the regex prefers the
# specific form, e.g. ADVOCATE before ADV, LT-GEN before GEN).
_TITLE = (
    r"(?:ADVOCATE|ADV|MRS|MR|MISS|MS|DR|PROF|LT[-\s]?GEN|MAJ[-\s]?GEN|BRIG|"
    r"GENERAL|GEN|COL|CAPT|MAJ|SGT|CONST|W/O|LIEUTENANT)"
)
_ROLE = r"(?:THE\s+)?(?:CHAIRPERSON|COMMISSIONER|WITNESS|INTERPRETER|REGISTRAR)"
_HEADING = (
    r"(?:CROSS[-\s]?|RE[-\s]?)?EXAMINATION(?:\s+IN\s+CHIEF)?\s+BY\s+"
    r"[A-Z][A-Z .'\-]*?(?:\s*\(CONTINUES?\))?"
)

# A label must start at a whitespace boundary (true after reflow) and end "...: ".
LABEL_RE = re.compile(
    r"(?:^|(?<=\s))("
    + _TITLE
    + r"\s+[A-Z][A-Z .'\-]*?"
    + r"|" + _ROLE
    + r"|" + _HEADING
    + r")\s*:\s"
)

_HEADING_TO_NAME_RE = re.compile(
    r"(?:CROSS[- ]?|RE[- ]?)?EXAMINATION(?:\s+IN\s+CHIEF)?\s+BY\s+"
    r"(?P<name>.*?)(?:\s*\(CONTINUES?\))?$"
)


def normalise_label(label: str) -> str:
    label = re.sub(r"\s+", " ", label).strip()
    heading = _HEADING_TO_NAME_RE.match(label)
    if heading:  # "EXAMINATION IN CHIEF BY ADV X (CONTINUES)" -> "ADV X"
        label = heading.group("name").strip()
    label = re.sub(r"\s*-\s*", "-", label)  # "SEGEELS -NCUBE" -> "SEGEELS-NCUBE"
    label = re.sub(r"\bLT GEN\b", "LT-GEN", label)
    label = re.sub(r"\bMAJ GEN\b", "MAJ-GEN", label)
    return label.strip()


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    page_start: int
    page_end: int


def detect_turns(doc: ReflowedDoc) -> list[Turn]:
    turns: list[Turn] = []
    matches = list(LABEL_RE.finditer(doc.text))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc.text)
        body = re.sub(r"\s+", " ", doc.text[start:end]).strip()
        if not body:
            continue
        turns.append(
            Turn(
                speaker=normalise_label(match.group(1)),
                text=body,
                page_start=doc.page_of(match.start()),
                page_end=doc.page_of(end - 1),
            )
        )
    return turns
