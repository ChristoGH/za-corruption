"""Runtime configuration, read from the environment only (invariant 6).

Importing commission_ingestion loads the repo-root .env (shell exports win), so
credentials never need hand-exporting. Defaults match docker-compose.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Importing the package triggers its .env loader (commission_ingestion/__init__).
import commission_ingestion  # noqa: F401


@dataclass(frozen=True)
class Settings:
    qdrant_url: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    web_origin: str


def get_settings() -> Settings:
    """Build Settings from the process environment (no secrets in code)."""
    return Settings(
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", "changeme"),
        web_origin=os.environ.get("WEB_ORIGIN", "http://localhost:5173"),
    )
