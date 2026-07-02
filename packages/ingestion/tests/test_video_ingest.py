"""Caption fetch (fake runner), video discovery, and the ingest-video CLI."""

import json
import subprocess
from pathlib import Path

from commission_ingestion.cli.ingest_video import run_cli
from commission_ingestion.discovery.madlanga import _record_from_json_item
from commission_ingestion.download.registry import SourceRegistry
from commission_ingestion.models.chunk_record import ChunkRecord
from commission_ingestion.models.source_record import SourceRecord
from commission_ingestion.vector.qdrant_store import chunk_payload
from commission_ingestion.video.fetch import (
    METHOD_AUTO,
    METHOD_MANUAL,
    fetch_captions,
)

VTT = """\
WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
Good morning, Chair.

00:00:03.000 --> 00:00:06.000
The commission resumes with the witness.
"""


class FakeYtDlp:
    """Writes a .vtt into the -o target dir for the chosen track kinds."""

    def __init__(self, *, manual: bool, auto: bool):
        self.manual = manual
        self.auto = auto
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        out_tmpl = Path(cmd[cmd.index("--output") + 1])
        wants_auto = "--write-auto-subs" in cmd
        available = self.auto if wants_auto else self.manual
        if available:
            (out_tmpl.parent / "abc123.en.vtt").write_text(VTT, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def test_fetch_prefers_manual_track(tmp_path):
    fake = FakeYtDlp(manual=True, auto=True)
    result = fetch_captions("https://youtu.be/abc123", tmp_path, runner=fake)
    assert result.method == METHOD_MANUAL
    assert result.vtt_path is not None and result.vtt_path.exists()
    assert len(fake.calls) == 1


def test_fetch_falls_back_to_auto(tmp_path):
    fake = FakeYtDlp(manual=False, auto=True)
    result = fetch_captions("https://youtu.be/abc123", tmp_path, runner=fake)
    assert result.method == METHOD_AUTO
    assert result.vtt_path is not None and result.vtt_path.exists()
    assert len(fake.calls) == 2


def test_fetch_reports_no_captions(tmp_path):
    fake = FakeYtDlp(manual=False, auto=False)
    result = fetch_captions("https://youtu.be/abc123", tmp_path, runner=fake)
    assert result.vtt_path is None
    assert result.method is None


def test_discovery_accepts_videos_tab_item():
    record = _record_from_json_item(
        {
            "tab_type": "Videos",
            "item_type": "link",
            "content_url": "https://www.youtube.com/live/JL8TCtE1GFA",
            "title": "Day 130 Livestream",
        },
        "https://criminaljusticecommission.org.za/hearing.php",
        "Madlanga Commission",
        blob_day=130,
        blob_date="2026-07-01",
    )
    assert record is not None
    assert record.source_type == "video"
    assert record.document_type == "Video"
    assert record.authoritative is False
    assert record.day_no == 130
    assert record.date == "2026-07-01"
    assert record.url == "https://www.youtube.com/live/JL8TCtE1GFA"


def test_discovery_accepts_youtube_url_under_any_tab():
    record = _record_from_json_item(
        {
            "tab_type": "Documents",
            "item_type": "link",
            "content_url": "https://youtu.be/JL8TCtE1GFA",
            "title": "Livestream day 130",
        },
        "https://criminaljusticecommission.org.za/hearing.php",
        "Madlanga Commission",
    )
    assert record is not None
    assert record.source_type == "video"
    assert record.day_no == 130


def test_discovery_rejects_non_youtube_videos_tab_item():
    record = _record_from_json_item(
        {
            "tab_type": "Videos",
            "item_type": "link",
            "content_url": "https://example.com/clip.mp4",
            "title": "Day 130",
        },
        "https://criminaljusticecommission.org.za/hearing.php",
        "Madlanga Commission",
    )
    assert record is None


def _registry_with_video(tmp_path, *, url="https://youtu.be/abc123"):
    registry_path = tmp_path / "registry.jsonl"
    registry = SourceRegistry(registry_path)
    registry.load()
    return registry, registry_path


def test_cli_ad_hoc_url_fetch_and_parse(tmp_path, monkeypatch):
    """End to end with a fake yt-dlp: register --url, fetch, parse, verify."""
    registry_path = tmp_path / "registry.jsonl"
    captions_dir = tmp_path / "captions"
    processed_dir = tmp_path / "processed"

    fake = FakeYtDlp(manual=False, auto=True)
    monkeypatch.setattr(
        "commission_ingestion.cli.ingest_video.fetch_captions",
        lambda url, out_dir, runner=None: fetch_captions(url, out_dir, runner=fake),
    )

    exit_code = run_cli([
        "--commission", "madlanga",
        "--url", "https://www.youtube.com/live/JL8TCtE1GFA",
        "--day", "130",
        "--date", "2026-07-01",
        "--registry", str(registry_path),
        "--captions-dir", str(captions_dir),
        "--processed-dir", str(processed_dir),
    ])
    assert exit_code == 0

    registry = SourceRegistry(registry_path)
    registry.load()
    (record,) = registry.filter(commission_slug="madlanga", source_type="video")
    assert record.downloaded is True
    assert record.sha256
    assert record.transcription_method == METHOD_AUTO
    assert record.local_path and Path(record.local_path).name.startswith("day130_")

    out_files = list((processed_dir / "madlanga").glob("day130_video_*.jsonl"))
    assert len(out_files) == 1
    chunks = [
        ChunkRecord.model_validate_json(line)
        for line in out_files[0].read_text().splitlines()
    ]
    assert chunks
    first = chunks[0]
    assert first.doc_sha256 == record.sha256
    assert first.page_start is None and first.page_end is None
    assert first.time_start == 1.0
    assert first.time_end == 6.0
    assert first.day_no == 130
    assert "Good morning, Chair." in first.text

    # payload carries time provenance + transcription method for deep links
    payload = chunk_payload(first, record)
    assert payload["time_start"] == 1.0
    assert payload["time_end"] == 6.0
    assert payload["transcription_method"] == METHOD_AUTO
    assert payload["authoritative"] is False
    assert payload["page_start"] is None

    # manifest written, idempotent re-run skips
    manifest_path = processed_dir / "madlanga" / "_video_manifest.jsonl"
    rows = [json.loads(l) for l in manifest_path.read_text().splitlines()]
    assert rows[0]["status"] == "ok"

    exit_code = run_cli([
        "--commission", "madlanga",
        "--parse",
        "--registry", str(registry_path),
        "--processed-dir", str(processed_dir),
    ])
    assert exit_code == 0
    rows = [json.loads(l) for l in manifest_path.read_text().splitlines()]
    assert rows[0]["status"] == "skipped_exists"


def test_cli_parse_deterministic_chunk_ids(tmp_path):
    """Same captions in, same chunk ids out (idempotent loads downstream)."""
    from commission_ingestion.cli.ingest_video import parse_video_document

    vtt_path = tmp_path / "day.vtt"
    vtt_path.write_text(VTT, encoding="utf-8")
    record = SourceRecord(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        authoritative=False,
        source_type="video",
        document_type="Video",
        url="https://youtu.be/abc123",
        day_no=130,
        date="2026-07-01",
        downloaded=True,
        local_path=str(vtt_path),
        sha256="f" * 64,
    )
    chunks_a, status_a = parse_video_document(record)
    chunks_b, status_b = parse_video_document(record)
    assert status_a == status_b == "ok"
    assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]


def test_video_record_roundtrips_registry(tmp_path):
    registry_path = tmp_path / "registry.jsonl"
    registry = SourceRegistry(registry_path)
    registry.load()
    record = SourceRecord(
        commission_slug="madlanga",
        commission_name="Madlanga Commission",
        authoritative=False,
        source_type="video",
        document_type="Video",
        url="https://youtu.be/abc123",
        transcription_method=METHOD_AUTO,
    )
    registry.upsert(record)
    registry.save()
    reloaded = SourceRegistry(registry_path)
    reloaded.load()
    (got,) = reloaded.filter(source_type="video")
    assert got.transcription_method == METHOD_AUTO
    assert got.authoritative is False
