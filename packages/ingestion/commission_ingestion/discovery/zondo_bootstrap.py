"""Zondo bootstrap discovery via DSFSI plaintext transcripts (non-authoritative)."""

from __future__ import annotations

import logging
import os
import re

import requests

from commission_ingestion.discovery.base import (
    CommissionDiscoveryAdapter,
    canonical_url,
    get_user_agent,
)
from commission_ingestion.models.source_record import SourceRecord

logger = logging.getLogger(__name__)

DSFSI_REPO = "dsfsi/project-state-capture"
# Pinned commit SHA for reproducible bootstrap corpus (CC-BY-SA-4.0).
DSFSI_COMMIT = "e2bc9d9183f2cb3467ee808f9716c03cb0ea71f1"
DSFSI_RAW_BASE = (
    f"https://raw.githubusercontent.com/{DSFSI_REPO}/{DSFSI_COMMIT}"
)
DSFSI_LICENSE = "CC-BY-SA-4.0"
DSFSI_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

DAY_TRANSCRIPT_PATTERNS = (
    re.compile(r"(?i)^DAY\s+(\d+)\s+TRANSCRIPT\s+DD\s+(\d{4}-\d{2}-\d{2})"),
    re.compile(r"(?i)^Day\s+(\d+)\s*-\s*(\d{4}-\d{2}-\d{2})"),
)


class ZondoBootstrapDiscoveryAdapter(CommissionDiscoveryAdapter):
    commission_slug = "zondo"
    commission_name = "Zondo Commission"

    def discover_sources(self) -> list[SourceRecord]:
        paths = self._list_interim_txt_paths()
        records: list[SourceRecord] = []
        for path in paths:
            record = self._record_for_path(path)
            if record is not None:
                records.append(record)
        logger.info(
            "Zondo bootstrap (DSFSI %s): %d transcript records",
            DSFSI_COMMIT[:12],
            len(records),
        )
        return records

    def _list_interim_txt_paths(self) -> list[str]:
        api_url = (
            f"https://api.github.com/repos/{DSFSI_REPO}/git/trees/"
            f"{DSFSI_COMMIT}?recursive=1"
        )
        headers = {
            "User-Agent": get_user_agent(),
            "Accept": "application/vnd.github+json",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(api_url, headers=headers, timeout=60)
        response.raise_for_status()
        tree = response.json().get("tree", [])
        return sorted(
            entry["path"]
            for entry in tree
            if entry.get("path", "").startswith("data/interim/")
            and entry.get("path", "").endswith(".txt")
        )

    def _record_for_path(self, path: str) -> SourceRecord | None:
        filename = path.rsplit("/", 1)[-1]
        day_no, date = _parse_day_and_date(filename)
        if day_no is None:
            return None

        url = canonical_url(f"{DSFSI_RAW_BASE}/{path}")
        return SourceRecord(
            schema_version="1.1",
            commission_slug="zondo",
            commission_name=self.commission_name,
            source_type="transcript",
            document_type="Transcript",
            title=filename,
            day_no=day_no,
            date=date,
            url=url,
            source_page_url=f"https://github.com/{DSFSI_REPO}/tree/{DSFSI_COMMIT}/{path}",
            authoritative=False,
            notes=(
                f"DSFSI plaintext bootstrap (commit {DSFSI_COMMIT[:12]}); "
                f"not the official PDF. Licence: {DSFSI_LICENSE} ({DSFSI_LICENSE_URL})"
            ),
        )


def _parse_day_and_date(filename: str) -> tuple[int | None, str | None]:
    for pattern in DAY_TRANSCRIPT_PATTERNS:
        match = pattern.search(filename)
        if match:
            return int(match.group(1)), match.group(2)
    return None, None
