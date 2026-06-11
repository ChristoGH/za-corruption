"""Descriptive corpus statistics (Post #1).

Pure computation lives in ``stats`` (no plotting deps); chart rendering in
``charts`` lazily imports matplotlib. Everything published is structure, not
characterisation — see the Post #1 guidance in docs/linkedin-post-1-kit.md.
"""

from __future__ import annotations

from commission_ingestion.analysis.stats import (
    DayStats,
    aggregate_day,
    detect_witness,
    role_of,
    summarise,
)

__all__ = ["DayStats", "aggregate_day", "detect_witness", "role_of", "summarise"]
