"""Minimal repo-root ``.env`` loader (no third-party dependency).

The CLIs read credentials (``NEO4J_PASSWORD``, ``ANTHROPIC_API_KEY``) from the
process environment. Without this, every fresh shell has to ``export`` them by
hand, which is the cause of recurring auth failures. This loads ``KEY=VALUE``
pairs from the nearest ``.env`` into ``os.environ`` once, at package import.

Shell-exported values always win: a key already present in the environment is
never overwritten, so an explicit ``export`` (or CI) still takes precedence and
the loader is a convenience, not an override.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_dotenv(start: Path | None = None) -> Path | None:
    """Return the nearest ``.env`` walking up from ``start`` (default: this file)."""
    origin = (start or Path(__file__)).resolve()
    bases = [origin, *origin.parents] if origin.is_file() else [origin, *origin.parents]
    for directory in bases:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_dotenv(start: Path | None = None) -> None:
    """Load ``KEY=VALUE`` lines from the nearest ``.env`` without overriding env."""
    if start is not None:
        path = find_dotenv(start)
    else:
        # Search from this module (in-tree runs) then the working directory.
        path = find_dotenv(Path(__file__)) or find_dotenv(Path.cwd())
    if path is None:
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
