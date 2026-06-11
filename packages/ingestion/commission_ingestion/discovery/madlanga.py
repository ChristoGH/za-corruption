"""Madlanga / Criminal Justice Commission source discovery."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from commission_ingestion.discovery.base import (
    CommissionDiscoveryAdapter,
    absolute_url,
    canonical_url,
    fetch_html_resilient,
    is_pdf_href,
    looks_like_bot_challenge,
)
from commission_ingestion.models.source_record import SourceRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://criminaljusticecommission.org.za"
HEARING_URL = f"{BASE_URL}/hearing.php"

START_PAGES = [
    f"{BASE_URL}/",
    HEARING_URL,
    f"{BASE_URL}/media.php",
    f"{BASE_URL}/notices.php",
] + [f"{BASE_URL}/index.php?page={n}" for n in range(1, 10)]

DAY_IN_TEXT_RE = re.compile(r"\bday[_\s]*(\d+)", re.IGNORECASE)
DATE_IN_TEXT_RE = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2})")
DATE_EIGHT_DIGIT_RE = re.compile(r"(\d{8})")
TEXTUAL_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+"
    r"(\d{4})\b",
    re.IGNORECASE,
)

MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

TRANSCRIPT_FILE_PDF_RE = re.compile(
    r'"tab_type":"Transcript"[^}]*"item_type":"file"[^}]*"content_url":"([^"]+\.pdf)"',
    re.IGNORECASE,
)


class MadlangaDiscoveryAdapter(CommissionDiscoveryAdapter):
    commission_slug = "madlanga"
    commission_name = "Madlanga Commission"

    def discover_sources(self) -> list[SourceRecord]:
        seen_urls: set[str] = set()
        records: list[SourceRecord] = []

        for page_url in START_PAGES:
            try:
                html = fetch_html_resilient(
                    page_url,
                    escalate_if=looks_like_bot_challenge,
                )
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", page_url, exc)
                continue

            extractors = (
                self._extract_from_embedded_json,
                self._extract_from_html,
            )
            for extractor in extractors:
                for record in extractor(html, page_url):
                    key = record.url
                    if key in seen_urls:
                        continue
                    seen_urls.add(key)
                    records.append(record)

        transcript_count = sum(
            1 for r in records if r.source_type == "transcript"
        )
        logger.info(
            "Madlanga discovery: %d total records, %d transcripts",
            len(records),
            transcript_count,
        )
        return records

    def _extract_from_embedded_json(
        self, html: str, page_url: str
    ) -> list[SourceRecord]:
        """Parse hearing day tabs from data-tabs JSON attributes on hearing.php."""
        soup = BeautifulSoup(html, "html.parser")
        records: list[SourceRecord] = []

        for element in soup.find_all(attrs={"data-tabs": True}):
            raw_tabs = element.get("data-tabs", "")
            items: list[dict[str, str]] = []
            try:
                tabs_data = json.loads(raw_tabs)
                for tab_name in ("Transcript", "Documents"):
                    for item in tabs_data.get(tab_name, []):
                        if isinstance(item, dict):
                            items.append(item)
            except json.JSONDecodeError:
                for match in TRANSCRIPT_FILE_PDF_RE.finditer(raw_tabs):
                    items.append(
                        {
                            "tab_type": "Transcript",
                            "item_type": "file",
                            "content_url": match.group(1),
                            "title": "",
                        }
                    )

            blob_day, blob_date = _extract_blob_context(element, raw_tabs)

            for item in items:
                record = _record_from_json_item(
                    item,
                    page_url,
                    self.commission_name,
                    blob_day=blob_day,
                    blob_date=blob_date,
                )
                if record is not None:
                    records.append(record)

        return records

    def _extract_from_html(self, html: str, page_url: str) -> list[SourceRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[SourceRecord] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            url = canonical_url(absolute_url(page_url, href))
            text = anchor.get_text(" ", strip=True)
            if not _is_madlanga_pdf(url, text):
                continue

            filename = urlparse(url).path.rsplit("/", 1)[-1]
            source_type, document_type = classify_madlanga_link(
                text, filename, page_url
            )
            day_no, date_str = _extract_day_and_date(text, url)

            records.append(
                SourceRecord(
                    commission_slug="madlanga",
                    commission_name=self.commission_name,
                    source_type=source_type,
                    document_type=document_type,
                    title=text or filename,
                    day_no=day_no,
                    date=date_str,
                    url=url,
                    source_page_url=page_url,
                )
            )
        return records


def _extract_blob_context(
    element: Tag, raw_tabs: str
) -> tuple[int | None, str | None]:
    """Derive day/date from all items in a data-tabs blob and host element."""
    parts: list[str] = []
    for key, value in element.attrs.items():
        if key == "data-tabs":
            continue
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
    parts.append(element.get_text(" ", strip=True))

    try:
        tabs_data = json.loads(raw_tabs)
        for tab_items in tabs_data.values():
            if not isinstance(tab_items, list):
                continue
            for item in tab_items:
                if not isinstance(item, dict):
                    continue
                parts.append(item.get("title", ""))
                parts.append(item.get("content_url", ""))
    except json.JSONDecodeError:
        parts.append(raw_tabs)

    combined = " ".join(part for part in parts if part)
    return _extract_day_and_date(combined, "")


def _record_from_json_item(
    item: dict[str, str],
    page_url: str,
    commission_name: str,
    *,
    blob_day: int | None = None,
    blob_date: str | None = None,
) -> SourceRecord | None:
    content_url = item.get("content_url", "").replace("\\/", "/")
    if not content_url:
        return None

    item_type = item.get("item_type", "")
    tab_type = item.get("tab_type", "")
    title = item.get("title", "")

    url = canonical_url(absolute_url(BASE_URL, content_url))
    filename = urlparse(url).path.rsplit("/", 1)[-1]

    if tab_type == "Transcript":
        if item_type != "file" or not content_url.lower().endswith(".pdf"):
            return None
        source_type, document_type = "transcript", "Transcript"
    elif tab_type == "Documents":
        if not content_url.lower().endswith(".pdf"):
            return None
        # Same classifier as the HTML path: a COMMISSION_RECORD filed under the
        # Documents tab is still a transcript; interim/final reports become reports.
        source_type, document_type = classify_madlanga_link(
            title, filename, page_url
        )
    else:
        return None
    day_no, date_str = _extract_day_and_date(f"{title} {filename}", url)
    if day_no is None:
        day_no = blob_day
    if date_str is None:
        date_str = blob_date

    return SourceRecord(
        commission_slug="madlanga",
        commission_name=commission_name,
        source_type=source_type,
        document_type=document_type,
        title=title or filename,
        day_no=day_no,
        date=date_str,
        url=url,
        source_page_url=page_url,
    )


def _is_madlanga_pdf(url: str, text: str) -> bool:
    if "criminaljusticecommission.org.za" not in url:
        return False
    if is_pdf_href(url):
        return True
    combined = f"{text}".upper()
    return "RECORD" in combined


def classify_madlanga_link(
    text: str, filename: str, page_url: str
) -> tuple[str, str]:
    """Classify a Madlanga PDF link into controlled source_type/document_type.

    The filename is the artifact's own identity and takes precedence over the
    anchor text, which on news pages is often a long press-release blurb. A file
    named ``STATEMENT ...`` is a statement even when it mentions a report; a file
    named for an interim/final report (e.g. ``..._SECOND_INTERIM_...``,
    ``CJSC_InterimReport_...``) is a report even when the blurb opens "STATEMENT BY".
    """
    combined = f"{text} {filename}".upper()
    page_lower = page_url.lower()
    text_lower = f"{text} {filename}".lower()
    filename_upper = filename.upper()
    filename_lower = filename.lower()

    if "RECORD" in combined or "COMMISSION_RECORD" in combined:
        return "transcript", "Transcript"

    # The artifact names itself a statement -> statement, regardless of the blurb.
    if filename_upper.startswith("STATEMENT"):
        return "statement", "WitnessStatement"

    # Interim / final report documents (keyed on the filename, not the blurb).
    if "interim" in filename_lower or "report" in filename_lower:
        return "report", "Report"

    if "notice" in page_lower or "notice" in text_lower:
        return "notice", "Notice"

    if "media" in page_lower or "media" in text_lower:
        return "media", "MediaStatement"

    if "statement" in text_lower:
        return "statement", "WitnessStatement"

    if "report" in text_lower:
        return "report", "Report"

    return "supporting_document", "SupportingDocument"


def _parse_yyyymmdd(candidate: str) -> str | None:
    if len(candidate) != 8 or not candidate.isdigit():
        return None
    year = int(candidate[:4])
    month = int(candidate[4:6])
    day = int(candidate[6:8])
    if year < 2020 or year > 2030:
        return None
    try:
        date(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _extract_date_from_filename(filename: str) -> str | None:
    for match in DATE_EIGHT_DIGIT_RE.finditer(filename):
        parsed = _parse_yyyymmdd(match.group(1))
        if parsed is not None:
            return parsed
    return None


def _extract_textual_date(text: str) -> str | None:
    match = TEXTUAL_DATE_RE.search(text)
    if not match:
        return None
    day = int(match.group(1))
    month = MONTH_NAME_TO_NUMBER[match.group(2).lower()]
    year = int(match.group(3))
    try:
        date(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _extract_day_and_date(text: str, url: str) -> tuple[int | None, str | None]:
    day_no: int | None = None
    date_str: str | None = None

    filename = urlparse(url).path.rsplit("/", 1)[-1] if url else ""
    combined = f"{text} {filename}".strip()

    day_match = DAY_IN_TEXT_RE.search(combined)
    if day_match:
        day_no = int(day_match.group(1))

    date_match = DATE_IN_TEXT_RE.search(combined)
    if date_match:
        date_str = date_match.group(1).replace("/", "-")
    else:
        date_str = _extract_date_from_filename(filename)
        if date_str is None:
            date_str = _extract_textual_date(combined)

    return day_no, date_str
