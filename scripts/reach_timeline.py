"""Render the commission's reach as a timeline ribbon.

Every hearing day plotted by its real date across the full span, so the cadence
shows truthfully: the December recess as a gap, the February-to-June run as a
dense band. Marquee witnesses (from the public record) are labelled at their
days. Days and dates come from the graph (:HearingDay {day_no, date}); the
witness anchors are a small curated overlay.

Run (Neo4j up; hearing-day structure loaded — claims not required):
    uv run python scripts/reach_timeline.py
Outputs: linkedin/commission_reach_timeline.png and .svg
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import commission_ingestion  # noqa: F401  (triggers .env load)
from neo4j import GraphDatabase

OUT_DIR = Path(__file__).resolve().parents[1] / "linkedin"
COMMISSION = "madlanga"

# Marquee witnesses: day_no -> short label. Public record; kept sparse and
# well-spaced so the ribbon stays readable. Edit freely.
WITNESSES: dict[int, str] = {
    2: "Mkhwanazi\n(KZN Commissioner)",
    5: "Masemola\n(Nat. Commissioner)",
    24: "Gen D. Khumalo",
    35: "Brown Mogotsi",
    47: "Maj-Gen Senona",
    62: "Lt-Gen Sibiya",
    73: "Suleiman Carrim",
    94: "Tshwane CFO Mnisi",
    110: "Senona (June)",
    122: "Senona returns",
    124: "Witness K",
}

INK = "#1a2238"
ACCENT = "#b8860b"
DAYDOT = "#33415c"
BAND = "#eef1f6"


def fetch_days() -> list[tuple[int, date]]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "changeme")
    rows: list[tuple[int, date]] = []
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (h:HearingDay) "
                "WHERE h.day_no IS NOT NULL AND h.date IS NOT NULL "
                "RETURN h.day_no AS day, h.date AS date ORDER BY day"
            )
            for rec in result:
                try:
                    d = datetime.strptime(str(rec["date"])[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
                rows.append((int(rec["day"]), d))
    finally:
        driver.close()
    # De-dup by day_no, keep first date seen.
    seen: dict[int, date] = {}
    for day_no, d in rows:
        seen.setdefault(day_no, d)
    return sorted(seen.items())


def render(days: list[tuple[int, date]]) -> None:
    if not days:
        raise SystemExit(
            "No hearing days returned. Is Neo4j up and loaded? "
            "Check NEO4J_PASSWORD and that build-graph has run."
        )
    day_to_date = dict(days)
    dates = [d for _, d in days]
    first, last = min(dates), max(dates)
    months = len({(d.year, d.month) for d in dates})

    fig, ax = plt.subplots(figsize=(16, 6.2))
    ax.set_ylim(-1.0, 1.0)
    span = (last - first).days or 1
    ax.set_xlim(
        mdates.date2num(first) - span * 0.03,
        mdates.date2num(last) + span * 0.03,
    )

    # Alternating month bands.
    ym = sorted({(d.year, d.month) for d in dates})
    for i, (y, m) in enumerate(ym):
        start = date(y, m, 1)
        nm = date(y + (m == 12), (m % 12) + 1, 1)
        if i % 2 == 0:
            ax.add_patch(
                Rectangle(
                    (mdates.date2num(start), -1.0),
                    mdates.date2num(nm) - mdates.date2num(start),
                    2.0,
                    color=BAND,
                    zorder=0,
                    linewidth=0,
                )
            )

    # Baseline ribbon.
    ax.plot(
        [mdates.date2num(first), mdates.date2num(last)],
        [0, 0],
        color=INK,
        linewidth=2.5,
        zorder=2,
        solid_capstyle="round",
    )
    # One tick per hearing day.
    xs = [mdates.date2num(d) for d in dates]
    ax.scatter(xs, [0] * len(xs), s=30, color=DAYDOT, zorder=3, edgecolors="white", linewidths=0.5)

    # Marquee witnesses, alternating above/below to avoid collisions.
    order = sorted(WITNESSES)
    for i, day_no in enumerate(order):
        if day_no not in day_to_date:
            continue
        x = mdates.date2num(day_to_date[day_no])
        up = i % 2 == 0
        y_text = 0.62 if up else -0.62
        y_dot = 0.0
        ax.plot([x, x], [y_dot, y_text * 0.82], color=ACCENT, linewidth=1.1, zorder=2)
        ax.scatter([x], [y_dot], s=70, color=ACCENT, zorder=4, edgecolors="white", linewidths=0.8)
        ax.annotate(
            f"Day {day_no}\n{WITNESSES[day_no]}",
            xy=(x, y_text),
            ha="center",
            va="bottom" if up else "top",
            fontsize=9.5,
            color=INK,
            linespacing=1.15,
            fontweight="medium",
            zorder=5,
        )

    # Month labels along the bottom.
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.tick_params(axis="x", length=0, labelsize=10, colors=INK, pad=10)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_yticks([])

    # Title and framing.
    fig.suptitle(
        f"The Madlanga Commission: {len(days)} hearing days",
        x=0.5,
        y=0.98,
        fontsize=21,
        fontweight="bold",
        color=INK,
    )
    ax.set_title(
        f"{first:%d %b %Y} to {last:%d %b %Y}  ·  {months} months  ·  "
        "each tick a day in the public record",
        fontsize=12,
        color="#4a5568",
        pad=18,
    )
    fig.text(
        0.5,
        0.02,
        "Allegations in the public record, not findings of fact.",
        ha="center",
        fontsize=9,
        color="#8a94a6",
    )

    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / "commission_reach_timeline.png"
    svg = OUT_DIR / "commission_reach_timeline.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"days: {len(days)}  span: {first} to {last}  months: {months}")
    print(f"wrote {png}")
    print(f"wrote {svg}")


if __name__ == "__main__":
    render(fetch_days())
