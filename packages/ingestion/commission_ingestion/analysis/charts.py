"""Chart rendering for Post #1. matplotlib is imported lazily so the core
package (and CI) need no plotting dependency — install the ``stats`` extra.

Each renderer takes the summary dict from ``stats.summarise`` and writes one
image. Numbers are rounded for display; exact values live in the stats JSON.
"""

from __future__ import annotations

from pathlib import Path


def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - guard for missing extra
        raise RuntimeError(
            "Charting needs the 'stats' extra: uv sync --all-packages --extra stats"
        ) from exc
    return plt


def _days(summary: dict) -> list[dict]:
    return [d for d in summary["per_day"] if d["day_no"] is not None]


def chart_pages_per_day(summary: dict, path: Path) -> None:
    plt = _plt()
    days = _days(summary)
    x = [d["day_no"] for d in days]
    y = [d["pages"] for d in days]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(x, y, color="#2b3a67")
    ax.set_xlabel("Hearing day")
    ax.set_ylabel("Transcript pages")
    ax.set_title("The tempo of testimony — pages per hearing day")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_cumulative_pages(summary: dict, path: Path) -> None:
    plt = _plt()
    days = _days(summary)
    x = [d["day_no"] for d in days]
    cum: list[int] = []
    total = 0
    for d in days:
        total += d["pages"]
        cum.append(total)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.fill_between(x, cum, color="#2b3a67", alpha=0.25)
    ax.plot(x, cum, color="#2b3a67")
    ax.set_xlabel("Hearing day")
    ax.set_ylabel("Cumulative pages")
    ax.set_title(f"The record so far — {total:,} pages of testimony")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_turn_tempo(summary: dict, path: Path) -> None:
    plt = _plt()
    days = _days(summary)
    x = [d["day_no"] for d in days]
    y = [d["median_turn_words"] for d in days]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(x, y, color="#a3320b")
    ax.set_xlabel("Hearing day")
    ax.set_ylabel("Median words per turn")
    ax.set_title("Contested testimony has a tempo — median turn length per day")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_role_word_share(summary: dict, path: Path) -> None:
    plt = _plt()
    share = summary["role_word_share_pct"]
    labels = ["Counsel", "Witnesses", "The bench"]
    values = [share.get("counsel", 0), share.get("witness", 0), share.get("bench", 0)]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.barh(labels, values, color=["#2b3a67", "#a3320b", "#5f6c7b"])
    for i, v in enumerate(values):
        ax.text(v + 0.5, i, f"{v}%", va="center")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of words spoken")
    ax.set_title("Who does the talking")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_marathon_days(summary: dict, path: Path, top: int = 10) -> None:
    plt = _plt()
    days = sorted(_days(summary), key=lambda d: d["pages"], reverse=True)[:top]
    labels = [f"Day {d['day_no']} ({d['date']})" for d in days][::-1]
    values = [d["pages"] for d in days][::-1]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(labels, values, color="#2b3a67")
    ax.set_xlabel("Transcript pages")
    ax.set_title(f"The marathon days — longest {top} by pages")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


RENDERERS = {
    "pages_per_day": chart_pages_per_day,
    "cumulative_pages": chart_cumulative_pages,
    "turn_tempo": chart_turn_tempo,
    "role_word_share": chart_role_word_share,
    "marathon_days": chart_marathon_days,
}


def render_all(summary: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, renderer in RENDERERS.items():
        path = out_dir / f"{name}.png"
        renderer(summary, path)
        written.append(path)
    return written
