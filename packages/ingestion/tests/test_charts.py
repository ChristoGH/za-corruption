"""Chart-layer tests — run only when the ``stats`` extra (matplotlib) is
installed, against a small synthetic summary, never the real corpus."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("matplotlib")

from commission_ingestion.analysis.charts import (  # noqa: E402
    WAR_AND_PEACE_PAGES,
    insert_gaps,
    render_all,
)

import datetime  # noqa: E402


def fixture_summary() -> dict:
    """Five September sittings, then one after a 45-day gap (a recess)."""
    per_day = []
    dates = ["2025-09-01", "2025-09-02", "2025-09-03", "2025-09-04", "2025-09-05",
             "2025-10-20"]
    pages = [400, 410, 390, 420, 405, 425]  # total 2,450 = 2x War and Peace
    for i, (date, n_pages) in enumerate(zip(dates, pages), start=1):
        per_day.append(
            {
                "day_no": i,
                "date": date,
                "pages": n_pages,
                "turns": 60,
                "words": 9000,
                "median_turn_words": 20 + i,
                "short_turn_share": 0.2 + i / 100,
                "witness": "MR MOGOTSI" if i % 2 else None,
            }
        )
    return {
        "totals": {"pages": sum(pages), "hearing_days": 6},
        "role_word_share_pct": {"counsel": 60.0, "witness": 30.0, "bench": 10.0},
        "per_day": per_day,
    }


def _dates(per_day: list[dict]) -> list[datetime.date]:
    return [datetime.date.fromisoformat(d["date"]) for d in per_day]


def test_insert_gaps_breaks_long_gaps_with_nan():
    summary = fixture_summary()
    x = _dates(summary["per_day"])
    y = [float(d["median_turn_words"]) for d in summary["per_day"]]
    xs, ys = insert_gaps(x, y)
    assert sum(1 for v in ys if math.isnan(v)) == 1  # exactly the 45-day gap
    # The NaN sits between the September block and the post-recess day.
    assert math.isnan(ys[5]) and not math.isnan(ys[4]) and not math.isnan(ys[6])


def test_insert_gaps_leaves_consecutive_days_unbroken():
    x = [datetime.date(2025, 9, 1) + datetime.timedelta(days=i) for i in range(5)]
    y = [float(i) for i in range(5)]
    xs, ys = insert_gaps(x, y)
    assert (xs, ys) == (x, y)


def test_render_all_writes_six_charts_and_alt_text(tmp_path):
    written = render_all(fixture_summary(), tmp_path)
    assert len(written) == 6
    for path in written:
        assert path.exists() and path.stat().st_size > 0

    alt = (tmp_path / "alt_text.md").read_text(encoding="utf-8")
    assert "2,450 pages" in alt  # fixture total, interpolated not hardcoded
    assert f"{WAR_AND_PEACE_PAGES:,}" in alt  # the 1x reference is stated
    assert "Day 6 (425 pages)" in alt  # longest fixture day in marathon entry
    assert "hearing days in sequence, not calendar days" in alt
    assert alt.count("provisional") >= 1  # role chart keeps its caveat


def test_chart_titles_are_unique_and_ratio_is_computed(tmp_path, monkeypatch):
    import matplotlib.axes

    titles: list[str] = []
    original = matplotlib.axes.Axes.set_title

    def spy(self, label, *args, **kwargs):
        titles.append(label)
        return original(self, label, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "set_title", spy)
    summary = fixture_summary()
    render_all(summary, tmp_path)

    assert len(titles) == 6
    assert len(set(titles)) == 6, f"duplicate chart titles: {titles}"

    total = summary["totals"]["pages"]
    ratio = total / WAR_AND_PEACE_PAGES
    cumulative_title = next(t for t in titles if "record so far" in t)
    assert f"{total:,} pages" in cumulative_title
    assert f"≈{ratio:.0f}× War and Peace" in cumulative_title
