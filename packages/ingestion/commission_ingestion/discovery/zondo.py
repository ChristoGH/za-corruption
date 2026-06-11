"""Zondo / State Capture Commission source discovery (official site)."""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from commission_ingestion.discovery.base import (
    CommissionDiscoveryAdapter,
    absolute_url,
    canonical_url,
    fetch_html_resilient,
    is_pdf_href,
    looks_like_bot_challenge,
    zondo_session_cookies,
)
from commission_ingestion.models.source_record import SourceRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://www.statecapture.org.za"
TRANSCRIPTS_URL = f"{BASE_URL}/site/transcripts"
DOCUMENTS_URL = f"{BASE_URL}/site/statements-and-documents"

DAY_RE = re.compile(r"Day\s+(\d+)\s*[-–]\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


class ZondoDiscoveryAdapter(CommissionDiscoveryAdapter):
    commission_slug = "zondo"
    commission_name = "Zondo Commission"

    def discover_sources(self) -> list[SourceRecord]:
        cookies = zondo_session_cookies()
        storage_state = None

        if os.environ.get("INGEST_ZONDO_STORAGE_STATE"):
            storage_state = os.environ["INGEST_ZONDO_STORAGE_STATE"]
        elif cookies is None:
            logger.warning(
                "Zondo official site is Cloudflare-blocked without a manual session. "
                "Set INGEST_ZONDO_CF_COOKIE or INGEST_ZONDO_STORAGE_STATE, or use "
                "--zondo-source bootstrap."
            )
            return []

        records = self._discover_transcripts(
            cookies=cookies, storage_state_path=storage_state
        )
        try:
            records.extend(
                self._discover_supporting_documents(
                    cookies=cookies, storage_state_path=storage_state
                )
            )
        except Exception as exc:
            logger.warning(
                "Zondo supporting-documents discovery skipped: %s", exc, exc_info=True
            )
        return _dedupe_by_url(records)

    def _discover_transcripts(
        self,
        *,
        cookies: dict[str, str] | None,
        storage_state_path: str | None,
    ) -> list[SourceRecord]:
        html = fetch_html_resilient(
            TRANSCRIPTS_URL,
            escalate_if=looks_like_bot_challenge,
            cookies=cookies,
            storage_state_path=storage_state_path,
        )
        if looks_like_bot_challenge(html):
            logger.warning(
                "Zondo transcripts page still shows Cloudflare challenge after fallback"
            )
            return []

        soup = BeautifulSoup(html, "html.parser")
        records: list[SourceRecord] = []
        current_day: int | None = None
        current_date: str | None = None

        for element in soup.find_all(["h4", "h5", "h6", "a"]):
            text = element.get_text(" ", strip=True)
            match = DAY_RE.search(text)
            if match:
                current_day = int(match.group(1))
                current_date = match.group(2)

            if element.name != "a":
                continue
            href = element.get("href")
            if not href:
                continue
            url = canonical_url(absolute_url(BASE_URL, href))
            if not is_pdf_href(url):
                continue
            filename = urlparse(url).path.rsplit("/", 1)[-1]
            if (
                "transcript" not in filename.lower()
                and "transcript" not in text.lower()
            ):
                continue

            title = text or f"Day {current_day} - {current_date}"
            records.append(
                SourceRecord(
                    commission_slug="zondo",
                    commission_name=self.commission_name,
                    source_type="transcript",
                    document_type="Transcript",
                    title=title,
                    day_no=current_day,
                    date=current_date,
                    url=url,
                    source_page_url=TRANSCRIPTS_URL,
                    authoritative=True,
                )
            )
        return records

    def _discover_supporting_documents(
        self,
        *,
        cookies: dict[str, str] | None,
        storage_state_path: str | None,
    ) -> list[SourceRecord]:
        """Best-effort discovery from Statements and Documents section."""
        html = fetch_html_resilient(
            DOCUMENTS_URL,
            escalate_if=looks_like_bot_challenge,
            cookies=cookies,
            storage_state_path=storage_state_path,
        )
        if looks_like_bot_challenge(html):
            return []

        soup = BeautifulSoup(html, "html.parser")
        records: list[SourceRecord] = []
        current_day: int | None = None
        current_date: str | None = None

        for element in soup.find_all(["h4", "h5", "h6", "a"]):
            text = element.get_text(" ", strip=True)
            match = DAY_RE.search(text)
            if match:
                current_day = int(match.group(1))
                current_date = match.group(2)

            if element.name != "a":
                continue
            href = element.get("href")
            if not href:
                continue
            url = canonical_url(absolute_url(BASE_URL, href))
            if not is_pdf_href(url):
                continue

            filename = urlparse(url).path.rsplit("/", 1)[-1]
            source_type, document_type = _classify_zondo_document(text, filename)
            records.append(
                SourceRecord(
                    commission_slug="zondo",
                    commission_name=self.commission_name,
                    source_type=source_type,
                    document_type=document_type,
                    title=text or filename,
                    day_no=current_day,
                    date=current_date,
                    url=url,
                    source_page_url=DOCUMENTS_URL,
                    authoritative=True,
                )
            )
        return records


def _classify_zondo_document(text: str, filename: str) -> tuple[str, str]:
    combined = f"{text} {filename}".lower()
    if "affidavit" in combined:
        return "statement", "Affidavit"
    if "statement" in combined:
        return "statement", "WitnessStatement"
    if "annexure" in combined:
        return "supporting_document", "Annexure"
    if "report" in combined:
        return "report", "Report"
    return "supporting_document", "SupportingDocument"


def _dedupe_by_url(records: list[SourceRecord]) -> list[SourceRecord]:
    seen: set[str] = set()
    unique: list[SourceRecord] = []
    for record in records:
        if record.url in seen:
            continue
        seen.add(record.url)
        unique.append(record)
    return unique
