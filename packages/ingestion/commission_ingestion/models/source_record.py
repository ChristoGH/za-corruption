from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SOURCE_TYPES = frozenset(
    {
        "transcript",
        "statement",
        "report",
        "notice",
        "media",
        "supporting_document",
    }
)

DOCUMENT_TYPES = frozenset(
    {
        "Transcript",
        "WitnessStatement",
        "Affidavit",
        "Annexure",
        "EvidenceBundle",
        "Report",
        "FinalReport",
        "InterimReport",
        "Notice",
        "Ruling",
        "Correspondence",
        "Contract",
        "Invoice",
        "BankRecord",
        "Presentation",
        "MeetingMinutes",
        "MediaStatement",
        "SupportingDocument",
    }
)

CommissionSlug = Literal["zondo", "madlanga"]


def _validate_http_url(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")
    return value


class SourceRecord(BaseModel):
    schema_version: str = "1.1"

    commission_slug: CommissionSlug
    commission_name: str

    authoritative: bool = True

    source_type: str = Field(
        description="Broad source category from controlled vocabulary"
    )
    document_type: str = Field(
        description="Controlled document type from DocumentType vocabulary"
    )

    title: str | None = None
    day_no: int | None = None
    date: str | None = None

    url: str
    source_page_url: str | None = None

    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None

    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    downloaded: bool = False
    local_path: str | None = None
    sha256: str | None = None

    notes: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        result = _validate_http_url(value, "url")
        assert result is not None
        return result

    @field_validator("source_page_url")
    @classmethod
    def validate_source_page_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value, "source_page_url")

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if value not in SOURCE_TYPES:
            raise ValueError(
                f"source_type must be one of {sorted(SOURCE_TYPES)}, got {value!r}"
            )
        return value

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        if value not in DOCUMENT_TYPES:
            raise ValueError(
                f"document_type must be one of {sorted(DOCUMENT_TYPES)}, got {value!r}"
            )
        return value

    def registry_key(self) -> str:
        """Primary deduplication key for the source registry."""
        return self.url
