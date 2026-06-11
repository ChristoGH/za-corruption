#!/usr/bin/env python3
"""Thin wrapper to run source retrieval from the repo root without editable install."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INGESTION_PKG = _REPO_ROOT / "packages" / "ingestion"

if str(_INGESTION_PKG) not in sys.path:
    sys.path.insert(0, str(_INGESTION_PKG))

from commission_ingestion.cli.retrieve_sources import run_cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_cli())
