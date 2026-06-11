"""Download commission source files with SHA256 hashing and validation."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from commission_ingestion.discovery.base import get_request_delay, get_user_agent
from commission_ingestion.models.source_record import SourceRecord

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
DEFAULT_RAW_DIR = Path("data/raw")
MISSING_AT_SOURCE_PREFIX = "Missing at source:"


def is_missing_at_source(record: SourceRecord) -> bool:
    return bool(
        record.notes and record.notes.startswith(MISSING_AT_SOURCE_PREFIX)
    )


def safe_filename(url: str, *, day_no: int | None = None) -> str:
    """Build a filesystem-safe filename from a URL, preserving the real extension."""
    path = urlparse(url).path
    name = unquote(path.rsplit("/", 1)[-1]).strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^\w.\-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "document"
    if "." not in name:
        name = f"{name}.bin"

    if day_no is not None and f"day_{day_no}" not in name.lower():
        stem, dot, ext = name.rpartition(".")
        if dot:
            name = f"{stem}_day_{day_no}.{ext}"
        else:
            name = f"{name}_day_{day_no}"

    return name[:200]


def file_extension(url: str, filename: str | None = None) -> str:
    name = filename or unquote(urlparse(url).path.rsplit("/", 1)[-1])
    if "." in name:
        return "." + name.rsplit(".", 1)[-1].lower()
    return ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_source(
    record: SourceRecord,
    *,
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    force: bool = False,
    user_agent: str | None = None,
    request_delay: float | None = None,
) -> SourceRecord:
    """Download a source file and update the record with file metadata."""
    out_dir = Path(raw_dir) / record.commission_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    ua = user_agent or get_user_agent()
    delay = get_request_delay() if request_delay is None else request_delay

    filename = record.filename or safe_filename(record.url, day_no=record.day_no)
    out_path = out_dir / filename
    ext = file_extension(record.url, filename)

    if (
        not force
        and record.downloaded
        and record.sha256
        and out_path.exists()
        and sha256_file(out_path) == record.sha256
    ):
        return record.model_copy(
            update={
                "local_path": str(out_path),
                "filename": filename,
            }
        )

    if delay > 0:
        import time

        time.sleep(delay)

    try:
        response = requests.get(
            record.url,
            headers={"User-Agent": ua},
            timeout=120,
            stream=True,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in {404, 410}:
            return record.model_copy(
                update={
                    "downloaded": False,
                    "notes": f"{MISSING_AT_SOURCE_PREFIX} HTTP {status}",
                }
            )
        if status not in {403, 429, 503}:
            raise
        reason = (
            f"Download rejected: HTTP {status} (likely bot protection). "
            f"Try again from a browser session or use bootstrap sources."
        )
        return record.model_copy(update={"downloaded": False, "notes": reason})

    content_type = response.headers.get("Content-Type")
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    try:
        with tmp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)

        valid, reason = _validate_download(tmp_path, ext)
        if not valid:
            logger.warning(reason)
            tmp_path.unlink(missing_ok=True)
            return record.model_copy(
                update={
                    "downloaded": False,
                    "notes": reason,
                    "content_type": content_type,
                }
            )

        tmp_path.replace(out_path)
        digest = sha256_file(out_path)
        size_bytes = out_path.stat().st_size

        return record.model_copy(
            update={
                "downloaded": True,
                "local_path": str(out_path),
                "filename": filename,
                "sha256": digest,
                "size_bytes": size_bytes,
                "content_type": content_type,
                "notes": None,
            }
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _validate_download(path: Path, ext: str) -> tuple[bool, str]:
    if ext == ".pdf":
        with path.open("rb") as handle:
            header = handle.read(len(PDF_MAGIC))
        if not header.startswith(PDF_MAGIC):
            return False, (
                f"Download rejected: response is not a PDF (path={path.name})"
            )
        return True, ""

    if ext == ".txt":
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False, (
                f"Download rejected: .txt is not valid UTF-8 (path={path.name})"
            )
        if not text.strip():
            return False, f"Download rejected: .txt is empty (path={path.name})"
        return True, ""

    if path.stat().st_size == 0:
        return False, f"Download rejected: file is empty (path={path.name})"
    return True, ""
