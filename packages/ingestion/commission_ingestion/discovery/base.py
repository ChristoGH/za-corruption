"""Shared discovery helpers and the CommissionDiscoveryAdapter ABC.

The fuller CommissionAdapter protocol in docs/build-plan-shared-core.md (parse_day_metadata,
speaker_regex, role_hint_map, etc.) arrives with the parsing phase — not this retrieval layer.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

import requests

from commission_ingestion.models.source_record import SourceRecord

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "transcript-research-bot/0.1 (+https://github.com/ChristoGH/za-corruption)"
)
DEFAULT_REQUEST_DELAY_SECONDS = 0.75

# Module-global throttle is intentionally sequential-only (CLI), not thread-safe.
_last_request_at: float | None = None

CHALLENGE_MARKERS = (
    "just a moment",
    "enable javascript and cookies",
    "cf-challenge",
    "__cf_bm",
    "checking your browser",
)


def get_user_agent() -> str:
    return os.environ.get("INGEST_USER_AGENT", DEFAULT_USER_AGENT)


def get_request_delay() -> float:
    raw = os.environ.get("INGEST_REQUEST_DELAY_SECONDS")
    if raw is None:
        return DEFAULT_REQUEST_DELAY_SECONDS
    return float(raw)


class CommissionDiscoveryAdapter(ABC):
    commission_slug: str
    commission_name: str

    @abstractmethod
    def discover_sources(self) -> list[SourceRecord]:
        """Return structured source records without downloading files."""
        ...


def is_pdf_href(href: str) -> bool:
    path = urlparse(href).path.lower()
    return path.endswith(".pdf")


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href)


def canonical_url(url: str) -> str:
    """Normalise a URL for stable registry dedup keys."""
    parsed = urlparse(url.strip())
    path = unquote(parsed.path)
    # Quote each path segment once (spaces -> %20) without double-encoding.
    segments = path.split("/")
    encoded_segments = [quote(seg, safe="") if seg else "" for seg in segments]
    normalised_path = "/".join(encoded_segments)
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalised_path,
            "",
            parsed.query,
            "",
        )
    )


def looks_like_bot_challenge(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in CHALLENGE_MARKERS)


def fetch_html(
    url: str,
    *,
    user_agent: str | None = None,
    timeout: float = 60.0,
    request_delay: float | None = None,
    session: requests.Session | None = None,
    cookies: dict[str, str] | None = None,
) -> str:
    """Fetch page HTML with a polite User-Agent and inter-request delay."""
    global _last_request_at

    ua = user_agent or get_user_agent()
    delay = get_request_delay() if request_delay is None else request_delay

    if delay > 0 and _last_request_at is not None:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)

    client = session or requests
    response = client.get(
        url,
        headers={"User-Agent": ua},
        cookies=cookies or {},
        timeout=timeout,
    )
    response.raise_for_status()
    _last_request_at = time.monotonic()
    return response.text


def fetch_html_playwright(
    url: str,
    *,
    timeout_ms: int = 120_000,
    storage_state_path: str | None = None,
) -> str:
    """Fetch page HTML via headless Chromium (for Cloudflare / dynamic pages)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed; pip install commission-ingestion[playwright] "
            "and run: playwright install chromium"
        ) from exc

    storage_state = storage_state_path or os.environ.get("INGEST_ZONDO_STORAGE_STATE")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context_kwargs: dict[str, object] = {}
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(5000)
        html = page.content()
        context.close()
        browser.close()
        return html


def fetch_html_resilient(
    url: str,
    *,
    user_agent: str | None = None,
    timeout: float = 60.0,
    request_delay: float | None = None,
    escalate_if: Callable[[str], bool] | None = None,
    cookies: dict[str, str] | None = None,
    storage_state_path: str | None = None,
) -> str:
    """Try requests first; fall back to Playwright on HTTP errors or challenge pages."""
    ua = user_agent or get_user_agent()
    delay = get_request_delay() if request_delay is None else request_delay

    html: str | None = None
    try:
        html = fetch_html(
            url,
            user_agent=ua,
            timeout=timeout,
            request_delay=delay,
            cookies=cookies,
        )
        if escalate_if is not None and escalate_if(html):
            logger.warning(
                "requests HTML for %s matched escalate_if; trying Playwright", url
            )
            return fetch_html_playwright(
                url, storage_state_path=storage_state_path
            )
        return html
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status not in {403, 429, 503}:
            raise
        logger.warning("requests returned %s for %s; trying Playwright", status, url)
    except requests.RequestException as exc:
        logger.warning("requests failed for %s (%s); trying Playwright", url, exc)

    return fetch_html_playwright(url, storage_state_path=storage_state_path)


def zondo_session_cookies() -> dict[str, str] | None:
    """Optional manual Cloudflare cookie from env (short-lived, do not log)."""
    cf_cookie = os.environ.get("INGEST_ZONDO_CF_COOKIE")
    if not cf_cookie:
        return None
    return {"cf_clearance": cf_cookie}


def reset_request_throttle() -> None:
    """Reset inter-request throttle (useful in tests)."""
    global _last_request_at
    _last_request_at = None
