"""Corpus integrity checks — a blocking pre-step before stats and charts.

Born from a real incident: day 80 was registered under two PDFs (a partial
publication mislabelled "..._Full" plus the true full record), and day 16's
transcript was also published a second time under a wrong "DAY 15" header —
293 double-counted pages in the headline total. Filenames and in-PDF footers
lie (the real day-80 record carries a "DAY 90" running footer), so duplication
is detected from *content containment*, and ``day_no``/``date`` always come
from the registry, never from page text.

Resolution is never automatic. The check prints the evidence (containment
percentages, per-document page breakdowns) and fails; a human then records
``superseded_by`` (sha256 of the surviving document) on the losing registry
record. Superseded files stay on disk — the exclusion record is the provenance.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from itertools import combinations

from commission_ingestion.models.source_record import SourceRecord

SHINGLE_WORDS = 10
# Containment at/above this means the same sitting published twice. Verified
# real duplicates sit at 0.77–1.0; unrelated same-week sittings at ~0.001
# (shared boilerplate only).
DUPLICATE_CONTAINMENT = 0.6
# A day this far above the corpus median gets its breakdown printed (it is an
# error only if containment or reconciliation also fails).
PAGE_OUTLIER_FACTOR = 1.5

# Lines that are layout, not testimony: "Page 12 of 147", margin line numbers,
# and the "18 MARCH 2026 – DAY 80" running header/footer.
_LAYOUT_LINE_RE = re.compile(r"^Page \d+ of \d+$|^\d{1,3}$|–\s*DAY \d+\s*$")


@dataclass
class DocInfo:
    """What the integrity pass needs to know about one parsed document."""

    record: SourceRecord
    n_pages: int
    page_texts: list[str]


@dataclass
class ContainmentResult:
    doc_a: DocInfo
    doc_b: DocInfo
    a_in_b: float  # fraction of doc_a's shingles present in doc_b
    b_in_a: float

    @property
    def is_duplicate(self) -> bool:
        return max(self.a_in_b, self.b_in_a) >= DUPLICATE_CONTAINMENT


@dataclass
class IntegrityReport:
    multi_doc_days: dict[int, list[DocInfo]] = field(default_factory=dict)
    outlier_days: dict[int, list[DocInfo]] = field(default_factory=dict)
    containments: list[ContainmentResult] = field(default_factory=list)
    superseded: list[SourceRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalise_text(page_texts: list[str]) -> list[str]:
    """Testimony words only — layout lines stripped so pagination differences
    between two publications of the same sitting don't dilute containment."""
    words: list[str] = []
    for text in page_texts:
        for line in text.splitlines():
            line = line.strip()
            if line and not _LAYOUT_LINE_RE.search(line):
                words.extend(line.split())
    return words


def shingle_set(words: list[str], n: int = SHINGLE_WORDS) -> set[str]:
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def containment(doc_a: DocInfo, doc_b: DocInfo) -> ContainmentResult:
    sa = shingle_set(normalise_text(doc_a.page_texts))
    sb = shingle_set(normalise_text(doc_b.page_texts))
    shared = len(sa & sb)
    return ContainmentResult(
        doc_a=doc_a,
        doc_b=doc_b,
        a_in_b=shared / len(sa) if sa else 0.0,
        b_in_a=shared / len(sb) if sb else 0.0,
    )


def candidate_pairs(docs: list[DocInfo]) -> list[tuple[DocInfo, DocInfo]]:
    """Pairs worth a containment check: same day number, same calendar date,
    or adjacent day numbers — the classes a publication mislabel can produce."""
    pairs: list[tuple[DocInfo, DocInfo]] = []
    for a, b in combinations(docs, 2):
        ra, rb = a.record, b.record
        same_day = ra.day_no is not None and ra.day_no == rb.day_no
        same_date = ra.date is not None and ra.date == rb.date
        adjacent = (
            ra.day_no is not None
            and rb.day_no is not None
            and abs(ra.day_no - rb.day_no) == 1
        )
        if same_day or same_date or adjacent:
            pairs.append((a, b))
    return pairs


def check_corpus(
    docs: list[DocInfo],
    superseded: list[SourceRecord],
    *,
    expected_active_records: int,
) -> IntegrityReport:
    """Run every check over the parsed *active* (non-superseded) documents.

    ``expected_active_records`` is the count of active downloaded transcript
    records in the registry — if parsing silently dropped one (scanned PDF,
    missing file), reconciliation fails rather than understating the totals.
    """
    report = IntegrityReport(superseded=list(superseded))

    by_day: dict[int, list[DocInfo]] = {}
    for doc in docs:
        if doc.record.day_no is not None:
            by_day.setdefault(doc.record.day_no, []).append(doc)

    report.multi_doc_days = {
        day: day_docs for day, day_docs in by_day.items() if len(day_docs) > 1
    }

    day_pages = {day: sum(d.n_pages for d in day_docs) for day, day_docs in by_day.items()}
    if day_pages:
        median_pages = statistics.median(day_pages.values())
        report.outlier_days = {
            day: by_day[day]
            for day, pages in day_pages.items()
            if pages > PAGE_OUTLIER_FACTOR * median_pages
        }

    for doc_a, doc_b in candidate_pairs(docs):
        result = containment(doc_a, doc_b)
        report.containments.append(result)
        if result.is_duplicate:
            report.errors.append(
                f"duplicate content: {_doc_label(doc_a)} and {_doc_label(doc_b)} "
                f"(containment {result.a_in_b:.1%} / {result.b_in_a:.1%}) — "
                "the same sitting appears to be published twice; mark one record "
                "superseded_by the other's sha256 in the registry"
            )

    if len(docs) != expected_active_records:
        report.errors.append(
            f"reconciliation: parsed {len(docs)} documents but the registry has "
            f"{expected_active_records} active downloaded transcripts — a document "
            "was silently skipped; totals would understate the record"
        )

    return report


def reconcile_summary(report_docs: list[DocInfo], summary: dict) -> list[str]:
    """Hard reconciliation between the stats summary and the parsed documents."""
    errors: list[str] = []
    doc_pages = sum(d.n_pages for d in report_docs)
    summary_pages = summary["totals"]["pages"]
    if doc_pages != summary_pages:
        errors.append(
            f"reconciliation: per-day pages sum to {summary_pages} but parsed "
            f"documents total {doc_pages}"
        )
    doc_days = {d.record.day_no for d in report_docs if d.record.day_no is not None}
    summary_days = summary["totals"]["hearing_days"]
    if len(doc_days) != summary_days:
        errors.append(
            f"reconciliation: summary reports {summary_days} hearing days but the "
            f"registry has {len(doc_days)} distinct active day numbers"
        )
    return errors


def _doc_label(doc: DocInfo) -> str:
    r = doc.record
    name = r.filename or r.url.rsplit("/", 1)[-1]
    sha = (r.sha256 or "")[:12]
    return f"day {r.day_no} ({r.date}) {name} [{sha}] {doc.n_pages}pp"


def render_report(report: IntegrityReport) -> str:
    """Human-readable findings — printed before any stats or charts."""
    lines = ["Integrity pass"]
    if report.superseded:
        lines.append(f"  Superseded (excluded): {len(report.superseded)}")
        for r in report.superseded:
            lines.append(
                f"    - day {r.day_no} ({r.date}) {r.filename} "
                f"superseded_by {(r.superseded_by or '')[:12]}"
                + (f" — {r.notes}" if r.notes else "")
            )
    if report.multi_doc_days:
        lines.append("  Days registered under more than one document:")
        for day in sorted(report.multi_doc_days):
            for doc in report.multi_doc_days[day]:
                lines.append(f"    - {_doc_label(doc)}")
    if report.outlier_days:
        lines.append(
            f"  Days above {PAGE_OUTLIER_FACTOR}× the median page count "
            "(informational; breakdown per document):"
        )
        for day in sorted(report.outlier_days):
            for doc in report.outlier_days[day]:
                lines.append(f"    - {_doc_label(doc)}")
    if report.containments:
        lines.append("  Content containment (same-day / same-date / adjacent-day pairs):")
        for c in report.containments:
            flag = "DUPLICATE" if c.is_duplicate else "distinct"
            lines.append(
                f"    - [{flag}] {_doc_label(c.doc_a)}  vs  {_doc_label(c.doc_b)}: "
                f"{c.a_in_b:.1%} / {c.b_in_a:.1%}"
            )
    if report.errors:
        lines.append("  ERRORS:")
        for err in report.errors:
            lines.append(f"    ! {err}")
    else:
        lines.append("  OK — no duplicate content, reconciliation clean.")
    return "\n".join(lines)
