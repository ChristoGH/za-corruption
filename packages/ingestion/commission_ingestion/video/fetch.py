"""Fetch YouTube caption tracks with yt-dlp (no video download).

Manual (human-authored) tracks are preferred over auto-generated ones; the
chosen track is recorded as ``transcription_method`` so downstream consumers
can distinguish caption quality. The subprocess runner is injectable so tests
never touch the network or require yt-dlp.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SUB_LANGS = "en.*,en"
YTDLP_TIMEOUT_SECONDS = 300

METHOD_MANUAL = "youtube_manual_captions"
METHOD_AUTO = "youtube_auto_captions"

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


@dataclass(frozen=True)
class FetchResult:
    """Outcome of one caption fetch. ``vtt_path`` is None on failure."""

    vtt_path: Path | None
    method: str | None
    detail: str = ""


def _default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        timeout=YTDLP_TIMEOUT_SECONDS,
        check=False,
    )


def _ytdlp_cmd(url: str, out_dir: Path, *, auto: bool, sub_langs: str) -> list[str]:
    subs_flag = "--write-auto-subs" if auto else "--write-subs"
    return [
        "yt-dlp",
        "--skip-download",
        "--no-playlist",
        subs_flag,
        "--sub-langs", sub_langs,
        "--sub-format", "vtt",
        "--output", str(out_dir / "%(id)s.%(ext)s"),
        url,
    ]


def _scratch_dir(out_dir: Path, url: str) -> Path:
    tag = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return out_dir / f".fetch-{tag}"


def fetch_captions(
    url: str,
    out_dir: Path,
    *,
    sub_langs: str = DEFAULT_SUB_LANGS,
    runner: Runner | None = None,
) -> FetchResult:
    """Fetch the best available caption track for one video into ``out_dir``.

    Tries the manual track first, then falls back to auto-generated captions.
    Returns the path of the fetched ``.vtt`` and which kind it was.
    """
    run = runner or _default_runner
    if runner is None and shutil.which("yt-dlp") is None:
        return FetchResult(
            vtt_path=None,
            method=None,
            detail="yt-dlp not found on PATH (install: uv tool install yt-dlp)",
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = _scratch_dir(out_dir, url)

    try:
        for auto, method in ((False, METHOD_MANUAL), (True, METHOD_AUTO)):
            if scratch.exists():
                shutil.rmtree(scratch)
            scratch.mkdir(parents=True)
            cmd = _ytdlp_cmd(url, scratch, auto=auto, sub_langs=sub_langs)
            try:
                proc = run(cmd)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return FetchResult(
                    vtt_path=None, method=None, detail=f"yt-dlp failed: {exc}"
                )
            if proc.returncode != 0:
                tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
                logger.warning(
                    "yt-dlp exit %s for %s: %s", proc.returncode, url, tail[0]
                )
                continue
            fetched = sorted(scratch.glob("*.vtt"))
            if fetched:
                if len(fetched) > 1:
                    logger.info(
                        "multiple caption tracks for %s, keeping %s",
                        url, fetched[0].name,
                    )
                target = out_dir / fetched[0].name
                os.replace(fetched[0], target)
                return FetchResult(vtt_path=target, method=method)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)

    return FetchResult(
        vtt_path=None, method=None, detail="no caption track available"
    )
