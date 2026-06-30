"""FastAPI app factory for the read-only public surface (M5).

Four endpoints, no more: /health, /search, /chunk/{id}/graph, /claim/{id}.
CORS is restricted to the configured web origin. The app owns no ingestion
logic — every route queries the commission_ingestion stores read-only.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import health, search


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Commission Transcript Intelligence API",
        version="0.1.0",
        description=(
            "Read-only search and evidence-graph surface over the Zondo and "
            "Madlanga commission transcripts. Allegations in the public record, "
            "attributed to named speakers under oath — not findings of fact."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(search.router, tags=["search"])
    return app


app = create_app()
