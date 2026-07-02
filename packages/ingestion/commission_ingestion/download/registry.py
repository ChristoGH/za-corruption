"""Local JSONL source registry."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import defaultdict
from pathlib import Path

from commission_ingestion.models.source_record import SourceRecord

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path("data/sources/source_registry.jsonl")


class SourceRegistry:
    def __init__(self, path: Path | str = DEFAULT_REGISTRY_PATH) -> None:
        self.path = Path(path)
        self._by_url: dict[str, SourceRecord] = {}

    def load(self) -> None:
        self._by_url.clear()
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = SourceRecord.model_validate_json(line)
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid registry line %s:%s: %s",
                        self.path,
                        line_no,
                        exc,
                    )
                    continue
                self._by_url[record.url] = record

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = sorted(self._by_url.values(), key=lambda r: (r.commission_slug, r.url))
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            delete=False,
        ) as tmp:
            for record in records:
                tmp.write(record.model_dump_json())
                tmp.write("\n")
            tmp_path = tmp.name
        os.replace(tmp_path, self.path)

    def upsert(self, record: SourceRecord) -> tuple[SourceRecord, bool]:
        """Insert or update by URL. Returns (record, is_new)."""
        existing = self._by_url.get(record.url)
        if existing is None:
            self._by_url[record.url] = record
            return record, True

        updates: dict[str, object] = {
            "title": record.title or existing.title,
            "day_no": record.day_no if record.day_no is not None else existing.day_no,
            "date": record.date or existing.date,
            "source_page_url": record.source_page_url or existing.source_page_url,
            "source_type": record.source_type,
            "document_type": record.document_type,
        }
        if record.downloaded:
            updates.update(
                {
                    "downloaded": record.downloaded,
                    "local_path": record.local_path,
                    "filename": record.filename,
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                    "content_type": record.content_type,
                    "transcription_method": record.transcription_method,
                    "notes": record.notes,
                }
            )
        elif record.notes and not existing.downloaded:
            updates["notes"] = record.notes

        merged = existing.model_copy(update=updates)
        self._by_url[record.url] = merged
        return merged, False

    def all(self) -> list[SourceRecord]:
        return list(self._by_url.values())

    def filter(
        self,
        *,
        commission_slug: str | None = None,
        source_type: str | None = None,
    ) -> list[SourceRecord]:
        results = self.all()
        if commission_slug is not None:
            results = [r for r in results if r.commission_slug == commission_slug]
        if source_type is not None:
            results = [r for r in results if r.source_type == source_type]
        return results

    def duplicate_sha256_groups(self) -> dict[str, list[SourceRecord]]:
        """Group records sharing a sha256. Non-destructive — all URLs retained."""
        groups: dict[str, list[SourceRecord]] = defaultdict(list)
        for record in self.all():
            if record.sha256:
                groups[record.sha256].append(record)
        return {digest: recs for digest, recs in groups.items() if len(recs) > 1}

    def known_urls(self) -> set[str]:
        return set(self._by_url.keys())

    def get(self, url: str) -> SourceRecord | None:
        return self._by_url.get(url)
