# Video Pipeline — Acquisition Slice (Prompts V0–V3)

**Runnable today. Gated on nothing in the extraction/PDF track.** Produces the two perishable, expensive-to-recompute assets — audio and diarized transcripts — and stops cleanly at `transcribed`. No chunking, no extraction, no graph writes. Those wait for Gate 2 and inherit the validated spine later.

**Why now:** the commission sits ~daily until ~end of August 2026, so a backlog is accumulating and the raw VODs are the one input you can't regenerate if a video is pulled or ages out. This slice also yields your first public content asset — a timestamp-anchored deep-link to the record (capability post #3).

## Invariants
- **Stop at `transcribed`.** Do not implement chunker / extract / ingest in this slice. Status enum is truncated accordingly.
- **Idempotent, cron-safe.** Re-running any stage on an already-advanced video is a no-op.
- **No paid LLM calls.** WhisperX + pyannote run locally or on a GPU you control. The only external cost is transcription compute (or a managed batch API if you swap V3).
- **Polite acquisition.** Audio-only, rate-limited, skip in-progress livestreams.
- Reuse existing repo conventions (logging, Makefile, config patterns) where they exist.

---

## V0 — Scaffold

```
Create a new module `video_pipeline/` in the existing repo:

video_pipeline/
├── __init__.py
├── config.py        # pydantic-settings: YT_CHANNEL_ID, ANTHROPIC_API_KEY (unused this
│                    # slice), HF_TOKEN (pyannote), AUDIO_DIR, TRANSCRIPT_DIR, DEVICE
├── manifest.py      # SQLite state store
├── watcher.py       # channel polling
├── downloader.py    # yt-dlp audio acquisition
├── transcribe.py    # WhisperX ASR + diarization
└── tests/

Add deps to pyproject.toml behind a `video` extra: yt-dlp, whisperx, pyannote.audio,
pydantic-settings, tenacity. Provide .env.example. Do NOT scaffold chunker/extract/
ingest in this slice. README section describing the acquisition stages only.

Acceptance: `python -c "from video_pipeline.config import settings"` works with .env.
```

## V1 — Manifest (truncated state store)

```
Implement `manifest.py` (stdlib sqlite3, no ORM).

Table `videos`: video_id PK, title, published_at, duration_s, url, status,
audio_path, transcript_path, error, updated_at.

Status enum (this slice only): discovered → downloaded → transcribed | failed

API: upsert_video, get_videos_by_status, advance, mark_failed. All transitions
idempotent. Tests cover idempotency and failed → retry.

Acceptance: pytest green; upsert twice → one row; advancing an advanced video is a no-op.
```

## V2 — Watcher + Downloader

```
Implement `watcher.py` and `downloader.py`.

watcher.py: yt-dlp Python API, extract_flat=True on the channel uploads URL. Filter
OUT live/in-progress (only completed VODs). Optional --since YYYY-MM-DD. New videos →
manifest as `discovered`.

downloader.py: for each `discovered`: yt-dlp bestaudio → 16kHz mono WAV (ffmpeg
postprocessor). Also fetch auto-subs (--write-auto-subs, en) as {video_id}.autosub.vtt
(free baseline, do not parse). Save metadata JSON alongside. Advance to `downloaded`.
tenacity retry (3, exp backoff); sleep 5–10s between downloads.

CLI: python -m video_pipeline.watcher --channel <id>
     python -m video_pipeline.downloader --limit N

Acceptance: run against the real channel with --limit 1; one WAV + metadata on disk;
manifest reflects state.
```

## V3 — Transcribe + Diarize (terminal stage)

```
Implement `transcribe.py` using WhisperX. Per `downloaded` video:
1. load_model("large-v3", device, float16 on CUDA / int8 on CPU/MPS).
2. Transcribe (language="en"; log detected-language warnings — expect isiZulu/
   Afrikaans code-switching).
3. Forced alignment → word-level timestamps.
4. Diarize via whisperx.DiarizationPipeline (pyannote, HF_TOKEN) → assign_word_speakers.
5. Write {video_id}.transcript.json:
   {video_id, model, created_at,
    segments: [{segment_id, start, end, speaker, text, avg_confidence}]}

Constraints: slice audio into 30-min windows if >2h, stitch with global timestamps.
Flag avg_confidence < 0.6 as low_confidence. Device autodetect cuda>mps>cpu with
--device override; warn if diarizing on non-CUDA (pyannote unreliable on MPS).
Advance to `transcribed`. STOP HERE — no chunking/extraction.

Acceptance: transcript JSON for one short test clip first; monotonic timestamps;
speaker labels present.
```

## Daily cron

```
A thin runner (Makefile target or cron entry) that runs watcher → downloader (bounded
--limit) → transcribe, idempotently, once daily. Safe to run unattended; advances each
video as far as `transcribed` and stops. Logs a one-line summary per run.
```

## Content checkpoint (the payoff)
From one `transcribed` hearing, generate a single YouTube deep-link (`...&t=<start>s`)
to a **non-sensitive** segment — a session opening or a procedural exchange, never an
allegation. That link, plus the diarized snippet, is the concrete proof-of-capability
for the "deep-linkable testimony" post. One safe link is the whole demo.

## Swap option
If standing up GPU + pyannote is friction, V3 can call a managed batch API
(AssemblyAI / Deepgram, with the diarization add-on) for ~a few hundred dollars across
the full backlog. Same `transcript.json` output contract; the rest of the slice is
unchanged.
```
