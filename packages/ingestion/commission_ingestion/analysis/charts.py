"""Chart rendering for Post #1. matplotlib is imported lazily so the core
package (and CI) need no plotting dependency — install the ``stats`` extra.

Charts use the series palette (from docs/series-cover-template.svg), plot on a
calendar-date axis where temporal (so the December recess shows as a plateau),
carry a source line, export at ~2x, and emit alt text. Numbers are rounded for
display; exact values live in the stats JSON.
"""

from __future__ import annotations

import datetime
from pathlib import Path

# Series palette (matches the cover template).
INK = "#101418"
GOLD = "#C9A227"
TEAL = "#2E7D6B"
PAPER = "#F4EFE6"
GREY = "#8A8F98"

# Calendar anchors derived from the data (52-day gap 5 Dec → 26 Jan).
RECESS_START = datetime.date(2025, 12, 5)
RECESS_END = datetime.date(2026, 1, 26)
INTERIM_REPORT = datetime.date(2025, 12, 17)
WAR_AND_PEACE_PAGES = 1225

SOURCE_LINE = (
    "Source: official Commission hearing records · criminaljusticecommission.org.za"
)
# Minimum turns before a day's median is trustworthy (small-sample guard).
MIN_TURNS_FOR_TEMPO = 50
# Consecutive hearing days further apart than this break the rolling lines —
# a recess must show as a gap, never a bridging segment.
MAX_BRIDGE_DAYS = 7


def _mpl():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError as exc:  # pragma: no cover - guard for missing extra
        raise RuntimeError(
            "Charting needs the 'stats' extra: uv sync --all-packages --extra stats"
        ) from exc
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "axes.titlesize": 15,
            "axes.titleweight": "bold",
        }
    )
    return plt, mdates


def _days(summary: dict) -> list[dict]:
    return [d for d in summary["per_day"] if d["day_no"] is not None and d["date"]]


def _date(d: dict) -> datetime.date:
    return datetime.date.fromisoformat(d["date"])


def _shade_recess(ax) -> None:
    ax.axvspan(RECESS_START, RECESS_END, color=GREY, alpha=0.18, lw=0)
    ax.axvline(INTERIM_REPORT, color=TEAL, lw=1.2, ls="--")


def _finish(fig, path: Path, *, source: bool = True) -> None:
    if source:
        fig.text(0.01, 0.01, SOURCE_LINE, fontsize=7, color=GREY, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=200, facecolor=PAPER)
    _mpl()[0].close(fig)


def _rolling(values: list[float], window: int = 5) -> list[float]:
    """Trailing mean over the *hearing-day sequence* — never calendar days."""
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        chunk = values[lo : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def insert_gaps(
    x: list[datetime.date], y: list[float], max_gap_days: int = MAX_BRIDGE_DAYS
) -> tuple[list[datetime.date], list[float]]:
    """NaN-break a plotted series wherever consecutive hearing days are more
    than ``max_gap_days`` apart, so matplotlib leaves a visible gap."""
    xs: list[datetime.date] = []
    ys: list[float] = []
    for i, (day, value) in enumerate(zip(x, y)):
        if i and (day - x[i - 1]).days > max_gap_days:
            xs.append(x[i - 1] + datetime.timedelta(days=1))
            ys.append(float("nan"))
        xs.append(day)
        ys.append(value)
    return xs, ys


def chart_cumulative_pages(summary: dict, path: Path) -> str:
    plt, mdates = _mpl()
    days = sorted(_days(summary), key=_date)
    x = [_date(d) for d in days]
    cum, total = [], 0
    for d in days:
        total += d["pages"]
        cum.append(total)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(x, cum, color=INK, alpha=0.12)
    ax.plot(x, cum, color=INK, lw=2)
    _shade_recess(ax)
    ax.text(INTERIM_REPORT, total * 0.08, " Interim report\n delivered, 17 Dec",
            color=TEAL, fontsize=9, va="bottom")
    multiple = total / WAR_AND_PEACE_PAGES
    # Reference at 1× near the bottom — the climb crosses it within weeks.
    ax.axhline(WAR_AND_PEACE_PAGES, color=GOLD, lw=1.2, ls=":")
    ax.text(x[-1], WAR_AND_PEACE_PAGES + total * 0.012,
            "War and Peace — all of it", color=GOLD, fontsize=10,
            fontweight="bold", va="bottom", ha="right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("Cumulative transcript pages")
    ax.set_title(
        f"The record so far — {total:,} pages, ≈{multiple:.0f}× War and Peace"
    )
    _finish(fig, path)
    return (f"Area chart: cumulative transcript pages over time reach {total:,} pages, "
            f"about {multiple:.0f} times the length of War and Peace. A gold dotted "
            f"line at {WAR_AND_PEACE_PAGES:,} pages (one War and Peace) sits near the "
            "bottom, crossed within the first weeks; the December–January recess shows "
            "as a plateau.")


def chart_pages_per_day(summary: dict, path: Path) -> str:
    plt, mdates = _mpl()
    days = sorted(_days(summary), key=_date)
    x = [_date(d) for d in days]
    y = [d["pages"] for d in days]
    peak = max(range(len(y)), key=lambda i: y[i])
    colors = [GOLD if i == peak else INK for i in range(len(y))]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar(x, y, color=colors, width=3)
    _shade_recess(ax)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("Transcript pages")
    ax.set_title("Day by day — transcript pages per sitting")
    _finish(fig, path)
    return ("Bar chart: transcript pages for each hearing day on a calendar axis; the "
            f"longest day ({y[peak]} pages) is highlighted, and the December recess shows "
            "as a gap. Several short sittings (rulings, postponements) appear as small bars.")


def chart_turn_tempo(summary: dict, path: Path) -> str:
    plt, mdates = _mpl()
    days = [d for d in sorted(_days(summary), key=_date) if d["turns"] >= MIN_TURNS_FOR_TEMPO]
    x = [_date(d) for d in days]
    y = _rolling([d["median_turn_words"] for d in days], 5)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(*insert_gaps(x, y), color=TEAL, lw=2)
    _shade_recess(ax)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("Median words per turn (5-day rolling)")
    ax.set_title(f"The tempo of testimony — median turn length (days ≥{MIN_TURNS_FOR_TEMPO} turns)")
    _finish(fig, path)
    return ("Line chart: 5-day rolling median of words per speaker turn across hearing "
            "days with at least 50 turns, on a calendar axis. The rolling window is "
            "over hearing days in sequence, not calendar days; the line breaks across "
            "the December–January recess rather than bridging it.")


def chart_interruption_proxy(summary: dict, path: Path) -> str:
    plt, mdates = _mpl()
    days = [d for d in sorted(_days(summary), key=_date) if d["turns"] >= MIN_TURNS_FOR_TEMPO]
    x = [_date(d) for d in days]
    y = _rolling([100 * d.get("short_turn_share", 0) for d in days], 5)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(*insert_gaps(x, y), color=GOLD, lw=2)
    _shade_recess(ax)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("Share of short (<15-word) turns, %")
    ax.set_title("The rhythm of cross-examination — share of short, rapid turns")
    _finish(fig, path)
    return ("Line chart: 5-day rolling share of turns under 15 words per hearing day — a "
            "proxy for rapid, contested back-and-forth — on a calendar axis. The rolling "
            "window is over hearing days in sequence, not calendar days; the line breaks "
            "across the December–January recess rather than bridging it.")


def chart_role_word_share(summary: dict, path: Path) -> str:
    plt, _ = _mpl()
    share = summary["role_word_share_pct"]
    items = sorted(
        [("Counsel", share.get("counsel", 0)),
         ("Witnesses", share.get("witness", 0)),
         ("The bench", share.get("bench", 0))],
        key=lambda kv: kv[1],
    )
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    colors = [INK] * len(values)
    colors[-1] = GOLD  # highlight the largest
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.barh(labels, values, color=colors)
    for i, v in enumerate(values):
        ax.text(v + 1, i, f"{v}%", va="center", fontweight="bold")
    ax.set_xlim(0, max(values) * 1.2)
    ax.set_xlabel("Share of words spoken")
    ax.set_title("Who does the talking  (provisional — heuristic role attribution)")
    _finish(fig, path)
    top = items[-1]
    return (f"Horizontal bar chart of share of words spoken: {top[0]} {top[1]}%, then "
            f"{items[-2][0]} {items[-2][1]}%, {items[-3][0]} {items[-3][1]}%. "
            "Role attribution is heuristic and provisional.")


def chart_marathon_days(summary: dict, path: Path, top: int = 10) -> str:
    plt, _ = _mpl()
    days = sorted(_days(summary), key=lambda d: d["pages"], reverse=True)[:top]
    days = days[::-1]  # largest at top of the horizontal bars
    labels = []
    for d in days:
        who = d["witness"] if d["witness"] else "legal argument"
        labels.append(f"Day {d['day_no']} · {d['date']} · {who}")
    values = [d["pages"] for d in days]
    colors = [INK] * len(values)
    colors[-1] = GOLD  # the single longest day
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.barh(labels, values, color=colors)
    for i, v in enumerate(values):
        ax.text(v + 2, i, f"{v}", va="center")
    ax.set_xlabel("Transcript pages")
    ax.set_title(f"The marathon days — longest {top} by pages")
    _finish(fig, path)
    return (f"Horizontal bar chart of the {top} longest hearing days by transcript pages; "
            f"the longest is Day {days[-1]['day_no']} ({values[-1]} pages). Days with no "
            "testifying witness are labelled 'legal argument'.")


RENDERERS = {
    "cumulative_pages": chart_cumulative_pages,
    "pages_per_day": chart_pages_per_day,
    "turn_tempo": chart_turn_tempo,
    "interruption_proxy": chart_interruption_proxy,
    "role_word_share": chart_role_word_share,
    "marathon_days": chart_marathon_days,
}


def render_all(summary: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    alt_lines = ["# Chart alt text (for LinkedIn accessibility)\n"]
    written: list[Path] = []
    for name, renderer in RENDERERS.items():
        path = out_dir / f"{name}.png"
        alt = renderer(summary, path)
        alt_lines.append(f"## {name}\n{alt}\n")
        written.append(path)
    (out_dir / "alt_text.md").write_text("\n".join(alt_lines), encoding="utf-8")
    return written
