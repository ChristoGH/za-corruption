# Madlanga Commission Full-Day Video Extraction & Transcription — Complete Technology Blueprint

**Purpose:** Define the complete technology stack needed to discover, extract, transcribe, register, store, search, and later analyse a full day of Madlanga Commission video evidence and hearing material.

**Primary outcome:** A reliable ingestion pipeline that can take a full-day hearing video, produce a timestamped transcript, preserve provenance, and make the content searchable and linkable to documents, people, days, topics, and evidence.

---

## 1. System Goal

The system must support the following end-to-end workflow:

```text
Find hearing day
→ discover official pages, PDFs, uploads, livestream/video links
→ register every source
→ download or reference media
→ extract audio
→ split long audio
→ transcribe with timestamps
→ merge transcript chunks
→ clean and segment transcript
→ store transcript and provenance
→ index for search
→ optionally link entities and events in a graph
```

The important design principle is:

> Every object must become a registered source with provenance before it is processed further.

This prevents the project from becoming a pile of loose videos, PDFs, transcript text files, and half-trusted notes.

---

## 2. Core Technology Stack

| Layer | Technology | Purpose | Required Now? |
|---|---|---:|---:|
| Language | Python 3.11+ or 3.12+ | Main pipeline language | Yes |
| Environment | `uv` or `pip-tools` | Dependency management | Yes |
| Browser automation | Playwright | Discover hearing links from dynamic web pages | Yes |
| Static HTTP | `httpx` | Download pages/files where browser is unnecessary | Yes |
| HTML parsing | BeautifulSoup / selectolax / lxml | Extract links and metadata from hearing pages | Yes |
| Video/audio download | `yt-dlp` | Download or inspect YouTube/video/livestream sources | Yes |
| Media processing | FFmpeg / FFprobe | Extract audio, normalise audio, split long media | Yes |
| Speech-to-text | faster-whisper or OpenAI Whisper | Transcribe audio | Yes |
| PDF extraction | PyMuPDF | Extract text, tables, metadata from PDFs | Yes |
| Registry DB | SQLite | Source registry, manifests, hashes, job state | Yes |
| Full-text search | SQLite FTS5 | Lightweight local keyword search | Yes |
| Data models | Pydantic | Validate SourceRecord, TranscriptSegment, jobs | Yes |
| Logging | `structlog` or standard `logging` | Reproducible audit logs | Yes |
| Testing | pytest | Offline regression tests | Yes |
| CLI | Typer or argparse | Repeatable command-line execution | Yes |
| Vector DB | Qdrant | Semantic transcript/document search | Phase 2 |
| Graph DB | Neo4j | People, hearings, events, evidence relationships | Phase 3 |
| Embeddings | OpenAI / local sentence-transformers | Semantic indexing | Phase 2 |
| LLM extraction | OpenAI / Anthropic / local model | Summaries, entities, topics, Q&A | Phase 3 |
| UI | Streamlit / React+Vite | Search, browse, review, correction interface | Phase 4 |
| Containers | Docker / Docker Compose | Repeatable local services | Phase 2+ |

---

## 3. Recommended Architecture

```text
madlanga-ingest/
  README.md
  pyproject.toml
  .env.example
  .gitignore

  data/
    raw/
      pages/
      pdfs/
      videos/
      audio/
    processed/
      transcripts/
      chunks/
      extracted_pdf_text/
    registry/
      sources.sqlite
      source_records.jsonl
    logs/

  src/
    madlanga_ingest/
      __init__.py

      config.py
      models.py
      paths.py
      logging_config.py

      discovery/
        discover_hearing_pages.py
        discover_pdf_links.py
        discover_video_links.py
        normalise_urls.py

      registry/
        db.py
        source_registry.py
        hashing.py
        dedupe.py

      retrieval/
        download_pages.py
        download_pdfs.py
        inspect_video.py
        download_audio.py

      media/
        ffprobe_metadata.py
        extract_audio.py
        split_audio.py
        normalise_audio.py

      transcription/
        transcribe_faster_whisper.py
        transcribe_openai_whisper.py
        merge_transcript_chunks.py
        export_srt.py
        export_vtt.py
        export_jsonl.py

      pdf/
        extract_text_pymupdf.py
        extract_tables.py
        classify_documents.py

      processing/
        chunk_transcript.py
        clean_transcript.py
        align_timestamps.py
        speaker_labelling.py

      search/
        sqlite_fts.py
        qdrant_ingest.py
        qdrant_search.py

      graph/
        neo4j_schema.cypher
        neo4j_ingest.py

      cli.py

  tests/
    fixtures/
      hearing_page_sample.html
      video_metadata_sample.json
      transcript_sample.jsonl
    test_source_record.py
    test_registry.py
    test_dedupe.py
    test_transcript_merge.py
```

---

## 4. SourceRecord Model

Every discovered source must be represented as a `SourceRecord`.

```python
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, HttpUrl

class SourceType(str, Enum):
    hearing_page = "hearing_page"
    transcript_pdf = "transcript_pdf"
    evidence_pdf = "evidence_pdf"
    uploaded_document = "uploaded_document"
    video = "video"
    audio = "audio"
    generated_transcript = "generated_transcript"
    generated_chunks = "generated_chunks"

class SourceRecord(BaseModel):
    source_id: str
    commission: str = "madlanga"
    source_type: SourceType
    title: str | None = None
    hearing_date: str | None = None
    url: HttpUrl | None = None
    canonical_url: str | None = None
    local_path: str | None = None
    parent_source_id: str | None = None
    sha256: str | None = None
    mime_type: str | None = None
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    duration_seconds: float | None = None
    language: str | None = None
    provenance_notes: str | None = None
    processing_status: str = "registered"
```

### Why this matters

A transcript produced from a video is not merely a text file. It is a derived source that should point back to:

- the original hearing page,
- the original video URL,
- the downloaded audio file,
- the transcription model and settings,
- the time and method of processing.

---

## 5. Registry Storage

Use SQLite first. It is enough for the source registry, job tracking, deduplication, local full-text search, and audit trails.

Suggested tables:

```sql
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    commission TEXT NOT NULL,
    source_type TEXT NOT NULL,
    title TEXT,
    hearing_date TEXT,
    url TEXT,
    canonical_url TEXT,
    local_path TEXT,
    parent_source_id TEXT,
    sha256 TEXT,
    mime_type TEXT,
    retrieved_at TEXT,
    published_at TEXT,
    duration_seconds REAL,
    language TEXT,
    provenance_notes TEXT,
    processing_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_canonical_url
ON sources(canonical_url)
WHERE canonical_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sources_sha256
ON sources(sha256);

CREATE TABLE transcript_segments (
    segment_id TEXT PRIMARY KEY,
    transcript_source_id TEXT NOT NULL,
    parent_audio_source_id TEXT,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    speaker TEXT,
    text TEXT NOT NULL,
    confidence REAL,
    model_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE transcript_segments_fts
USING fts5(segment_id, text, speaker, content='transcript_segments', content_rowid='rowid');
```

---

## 6. Discovery Layer

### Purpose

Find all hearing-day assets:

- hearing pages,
- transcript PDFs,
- evidence PDFs,
- document uploads,
- livestream pages,
- YouTube/video links,
- embedded media URLs.

### Technologies

- `httpx` for simple pages and downloads.
- Playwright for dynamic pages, JavaScript-rendered pages, anti-bot loaders, or pages where links appear only after browser rendering.
- BeautifulSoup, lxml, or selectolax for parsing HTML.

### Discovery output

Discovery must not download everything immediately. It should first emit candidate `SourceRecord`s.

```text
input: hearing index URL
output: source_records.jsonl + sources.sqlite rows
```

Example CLI:

```bash
python -m madlanga_ingest.cli discover-hearings \
  --index-url "https://criminaljusticecommission.org.za/hearing.php" \
  --out data/registry/source_records.jsonl
```

---

## 7. Media Download Layer

### Purpose

Extract or reference the video/audio needed for transcription.

### Technologies

- `yt-dlp` for YouTube and many hosted video platforms.
- FFmpeg for media conversion.
- FFprobe for media metadata.

### Recommended strategy

Do not always download full video first. Prefer:

```text
video URL → audio-only download → normalised WAV/MP3 → transcription
```

For transcription, audio is usually enough.

### Example commands

Inspect video metadata:

```bash
yt-dlp --dump-json "VIDEO_URL" > data/raw/videos/video_metadata.json
```

Download best available audio:

```bash
yt-dlp \
  --extract-audio \
  --audio-format wav \
  --audio-quality 0 \
  -o "data/raw/audio/%(title)s.%(ext)s" \
  "VIDEO_URL"
```

Normalise audio for transcription:

```bash
ffmpeg -i input.wav \
  -ac 1 \
  -ar 16000 \
  -af loudnorm \
  data/processed/audio/input_16k_mono.wav
```

Split long full-day audio into chunks:

```bash
ffmpeg -i full_day_16k_mono.wav \
  -f segment \
  -segment_time 1800 \
  -c copy \
  data/processed/audio/chunks/chunk_%03d.wav
```

A 30-minute chunk size is a practical starting point for long hearings.

---

## 8. Transcription Layer

### Recommended default

Use `faster-whisper` for local transcription because it is designed for faster inference using CTranslate2 and supports efficient CPU/GPU workflows.

Alternative:

- OpenAI Whisper reference implementation for compatibility and simplicity.
- Cloud transcription API if local compute is too slow.

### Hardware guidance

| Hardware | Recommended model | Notes |
|---|---|---|
| CPU-only laptop | `small` / `medium` with int8 | Slower but workable |
| Apple Silicon Mac | `medium` or `large-v3` depending memory | Use local testing first |
| NVIDIA GPU | `large-v3` / `large-v3-turbo` if supported | Best for full-day processing |
| Cloud GPU | `large-v3` | Best for batch backlogs |

### Output formats

The transcriber should emit at least:

```text
transcript.jsonl     canonical machine-readable transcript
transcript.txt       human-readable transcript
transcript.srt       subtitle format
transcript.vtt       web subtitle format
segments.csv         QA/review format
```

### TranscriptSegment model

```python
class TranscriptSegment(BaseModel):
    segment_id: str
    transcript_source_id: str
    parent_audio_source_id: str
    start_seconds: float
    end_seconds: float
    speaker: str | None = None
    text: str
    confidence: float | None = None
    model_name: str
    language: str | None = "en"
```

### Minimal faster-whisper transcription script

```python
from faster_whisper import WhisperModel
from pathlib import Path
import json
import uuid

model = WhisperModel("large-v3", device="auto", compute_type="auto")

audio_path = Path("data/processed/audio/full_day_16k_mono.wav")
out_path = Path("data/processed/transcripts/full_day.transcript.jsonl")
out_path.parent.mkdir(parents=True, exist_ok=True)

segments, info = model.transcribe(
    str(audio_path),
    beam_size=5,
    vad_filter=True,
    word_timestamps=True,
)

with out_path.open("w", encoding="utf-8") as f:
    for seg in segments:
        row = {
            "segment_id": str(uuid.uuid4()),
            "start_seconds": seg.start,
            "end_seconds": seg.end,
            "text": seg.text.strip(),
            "model_name": "faster-whisper-large-v3",
            "language": info.language,
            "words": [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                }
                for w in (seg.words or [])
            ],
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

---

## 9. Speaker Diarisation

Whisper-style transcription does not reliably identify speakers by itself.

For Madlanga hearings, speaker identification matters because the value lies in knowing who said what.

### Options

| Option | Tooling | Accuracy | Complexity |
|---|---|---:|---:|
| Manual labels after transcript | CSV review interface | High after review | Low |
| Rule-based labels from transcript cues | Regex / heuristics | Medium | Low |
| Audio diarisation | pyannote.audio or equivalent | Medium to high | Medium/high |
| Hybrid | Diarisation + manual correction | Best | Higher |

### Recommended approach

Phase 1:

```text
No automatic diarisation. Preserve timestamps and make manual correction easy.
```

Phase 2:

```text
Add diarisation and speaker-labelling workflow.
```

Potential speaker labels:

```text
CHAIRPERSON
COMMISSIONER
COUNSEL
WITNESS
ADVOCATE
UNKNOWN_SPEAKER_01
UNKNOWN_SPEAKER_02
```

---

## 10. PDF and Document Extraction

### Purpose

Handle official transcript PDFs, evidence PDFs, uploaded documents, and notices.

### Technologies

- PyMuPDF for text extraction and document rendering.
- Optional OCR only if PDFs are scanned images.
- Optional table extraction for evidence schedules.

### Outputs

```text
extracted_pdf_text.jsonl
page_text.txt
tables.csv
pdf_metadata.json
```

### Minimal PyMuPDF extraction

```python
import pymupdf
from pathlib import Path

pdf_path = Path("data/raw/pdfs/example.pdf")
out_path = Path("data/processed/extracted_pdf_text/example.txt")
out_path.parent.mkdir(parents=True, exist_ok=True)

doc = pymupdf.open(pdf_path)
text_parts = []

for page_number, page in enumerate(doc, start=1):
    text = page.get_text("text")
    text_parts.append(f"\n\n--- PAGE {page_number} ---\n\n{text}")

out_path.write_text("".join(text_parts), encoding="utf-8")
```

---

## 11. Chunking Strategy

The transcript should be chunked for search and later RAG.

### Recommended chunk types

| Chunk type | Use |
|---|---|
| Time-window chunks | “What was said between 10:00 and 10:15?” |
| Semantic chunks | Search and Q&A |
| Speaker-turn chunks | Who said what |
| Evidence-reference chunks | Link testimony to evidence |
| Topic chunks | Summaries by issue |

### Initial chunking rule

Start simple:

```text
Chunk by 3–5 minutes or roughly 700–1200 words, preserving start/end timestamps.
```

Each chunk must include:

```python
{
    "chunk_id": "...",
    "transcript_source_id": "...",
    "hearing_date": "...",
    "start_seconds": 1234.5,
    "end_seconds": 1530.0,
    "text": "...",
    "speaker_set": ["UNKNOWN_SPEAKER_01", "COUNSEL"],
    "source_url": "...",
    "parent_video_source_id": "..."
}
```

---

## 12. Search Layer

### Phase 1: SQLite FTS5

Use SQLite FTS5 immediately for local keyword search.

This gives fast searches such as:

```text
"Mkhwanazi"
"political interference"
"case docket"
"minister"
"intelligence"
```

### Phase 2: Qdrant

Use Qdrant for semantic search:

```text
“Find moments where a witness explains why an investigation was delayed.”
```

Payload fields in Qdrant should include:

```python
{
    "chunk_id": "...",
    "commission": "madlanga",
    "hearing_date": "...",
    "start_seconds": 1234.5,
    "end_seconds": 1530.0,
    "source_url": "...",
    "speaker_set": ["..."],
    "source_type": "generated_transcript"
}
```

---

## 13. Graph Layer

Neo4j is not needed for the first working transcript pipeline, but it becomes valuable once you want to model relationships.

### Candidate graph model

```text
(:Commission {name})
(:HearingDay {date})
(:Source {source_id, type, url})
(:TranscriptSegment {segment_id, start, end})
(:Person {name, role})
(:Organisation {name})
(:EvidenceItem {id, title})
(:Topic {name})
(:Claim {text})

(:Commission)-[:HAS_HEARING_DAY]->(:HearingDay)
(:HearingDay)-[:HAS_SOURCE]->(:Source)
(:Source)-[:GENERATED]->(:TranscriptSegment)
(:Person)-[:SPOKE_IN]->(:TranscriptSegment)
(:TranscriptSegment)-[:MENTIONS]->(:Person)
(:TranscriptSegment)-[:MENTIONS]->(:Organisation)
(:TranscriptSegment)-[:REFERS_TO]->(:EvidenceItem)
(:TranscriptSegment)-[:ABOUT]->(:Topic)
(:TranscriptSegment)-[:CONTAINS_CLAIM]->(:Claim)
```

### What Neo4j enables

- Which people are mentioned together?
- Which evidence items are repeatedly discussed?
- Which topics recur across hearing days?
- What claims are supported by which transcript segments?
- Which witness referred to which document?

---

## 14. Quality Assurance

A legal/public-hearing transcript system must not pretend to be perfect. The pipeline should explicitly preserve confidence and review status.

### QA checks

| Check | Method |
|---|---|
| Audio duration equals transcript coverage | Compare FFprobe duration to final segment end time |
| Missing chunks | Ensure contiguous time ranges |
| Duplicate source | URL and SHA256 dedupe |
| Broken download | File exists, size > minimum, hash captured |
| Transcript hallucination risk | Spot-check silent/noisy periods |
| Speaker correctness | Manual review queue |
| Timestamp correctness | Spot-check random segments against video |
| Official transcript mismatch | Compare generated transcript to PDF transcript if available |

### Review status values

```text
unreviewed
machine_generated
spot_checked
speaker_corrected
official_transcript_available
human_verified
superseded
```

---

## 15. Implementation Phases

### Phase 0 — Repository and design

Deliver:

- repository skeleton,
- README,
- `.env.example`,
- `pyproject.toml`,
- SourceRecord model,
- registry schema,
- test fixtures.

Do not build Qdrant, Neo4j, UI, or LLM extraction yet.

---

### Phase 1 — Retrieval and registry

Deliver:

- discover hearing pages,
- discover PDF links,
- discover video links,
- register sources,
- deduplicate by canonical URL and SHA256,
- download PDFs,
- inspect videos,
- persist all provenance.

Success condition:

```text
Given the hearing index page, the system produces a clean registry of hearing pages, PDFs, and video sources.
```

---

### Phase 2 — Full-day video transcription

Deliver:

- audio download from video source,
- FFmpeg audio normalisation,
- audio splitting,
- faster-whisper transcription,
- transcript JSONL/TXT/SRT/VTT export,
- transcript source registration,
- SQLite FTS search.

Success condition:

```text
Given one full-day video URL, the system produces a searchable timestamped transcript.
```

---

### Phase 3 — Semantic search and graph

Deliver:

- chunking,
- embeddings,
- Qdrant collection,
- Neo4j graph schema,
- entity extraction,
- evidence/person/topic linking.

Success condition:

```text
The system can answer semantic questions and trace every answer back to source timestamps.
```

---

### Phase 4 — Review UI

Deliver:

- search interface,
- transcript browser,
- video timestamp links,
- speaker correction,
- export to Markdown/PDF/CSV,
- evidence/person/topic dashboards.

Success condition:

```text
A human reviewer can inspect, correct, and cite transcript segments reliably.
```

---

## 16. Minimal `pyproject.toml`

```toml
[project]
name = "madlanga-ingest"
version = "0.1.0"
description = "Madlanga Commission source discovery, video transcription, and evidence ingestion pipeline"
requires-python = ">=3.11"
dependencies = [
    "beautifulsoup4",
    "faster-whisper",
    "httpx",
    "lxml",
    "playwright",
    "pydantic",
    "pymupdf",
    "python-dotenv",
    "rich",
    "structlog",
    "typer",
    "yt-dlp",
]

[project.optional-dependencies]
search = [
    "qdrant-client",
    "sentence-transformers",
]
graph = [
    "neo4j",
]
dev = [
    "pytest",
    "pytest-cov",
    "ruff",
    "mypy",
]

[project.scripts]
madlanga-ingest = "madlanga_ingest.cli:app"

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## 17. System Dependencies

Python packages are not enough. The system also needs native tools.

### macOS

```bash
brew install ffmpeg sqlite
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,search,graph]"
python -m playwright install chromium
```

### Ubuntu / WSL

```bash
sudo apt update
sudo apt install -y ffmpeg sqlite3
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,search,graph]"
python -m playwright install chromium
```

### Verify tools

```bash
python --version
ffmpeg -version
ffprobe -version
yt-dlp --version
sqlite3 --version
python -m playwright --version
```

---

## 18. Suggested CLI Commands

```bash
# Discover hearing pages and candidate sources
madlanga-ingest discover \
  --index-url "https://criminaljusticecommission.org.za/hearing.php"

# Download registered PDFs
madlanga-ingest download-pdfs

# Inspect a video source without downloading it
madlanga-ingest inspect-video \
  --source-id SRC_VIDEO_001

# Download audio from a registered video source
madlanga-ingest download-audio \
  --source-id SRC_VIDEO_001

# Normalise and split audio
madlanga-ingest prepare-audio \
  --source-id SRC_AUDIO_001 \
  --segment-minutes 30

# Transcribe all chunks
madlanga-ingest transcribe \
  --audio-source-id SRC_AUDIO_001 \
  --model large-v3

# Merge transcript chunks
madlanga-ingest merge-transcript \
  --audio-source-id SRC_AUDIO_001

# Build local full-text index
madlanga-ingest build-fts

# Search transcript
madlanga-ingest search "political interference"
```

---

## 19. Data Formats to Preserve

For each full-day video, preserve:

```text
Original video URL
Video metadata JSON
Downloaded audio file
Audio metadata JSON
Audio chunk files
Raw transcript segments
Merged transcript JSONL
Human-readable transcript TXT
Subtitle SRT/VTT
Chunked transcript JSONL
SourceRecord JSONL
SQLite registry
Processing logs
```

Never keep only the final cleaned transcript.

---

## 20. Security, Ethics, and Legal Handling

Because this involves public commission material, the system should still be careful.

Required practices:

- Use official sources where possible.
- Preserve URLs and retrieval timestamps.
- Do not silently alter transcript content.
- Mark generated transcripts as machine-generated.
- Preserve confidence/review status.
- Keep a path back from every answer to a video timestamp or official document.
- Avoid presenting machine transcripts as official transcripts.
- Respect website terms and rate limits.

---

## 21. Recommended First Build

Build only this first:

```text
1. SourceRecord model
2. SQLite registry
3. hearing page discovery
4. PDF/video link discovery
5. yt-dlp video inspection
6. audio download
7. FFmpeg normalisation and splitting
8. faster-whisper transcription
9. transcript JSONL export
10. SQLite FTS search
```

Do not start with:

```text
Qdrant
Neo4j
LLM summaries
React UI
agent orchestration
complex diarisation
```

Those are valuable, but they come after the transcript pipeline is reliable.

---

## 22. Cursor / Claude Agent Build Prompt

```text
You are implementing the Madlanga Commission ingestion pipeline.

Build a retrieval-first, provenance-first Python project.

Do not implement Qdrant, Neo4j, LLM summarisation, or frontend UI yet.

The immediate goal is to support one full-day Madlanga Commission video and produce a searchable timestamped transcript.

Requirements:
1. Create the project skeleton shown in the technology blueprint.
2. Implement a Pydantic SourceRecord model.
3. Implement a SQLite source registry.
4. Implement canonical URL deduplication and SHA256 file deduplication.
5. Implement discovery for hearing pages, PDF links, and video links.
6. Use Playwright only where static httpx retrieval is insufficient.
7. Implement yt-dlp video metadata inspection.
8. Implement audio-only download from a video source.
9. Implement FFmpeg audio normalisation to 16 kHz mono.
10. Implement FFmpeg splitting into configurable chunk lengths.
11. Implement faster-whisper transcription with timestamped JSONL output.
12. Implement transcript merge across audio chunks.
13. Register generated transcripts as derived SourceRecords.
14. Implement SQLite FTS5 search over transcript segments.
15. Write offline tests using fixtures. Tests must not require network, Qdrant, Neo4j, external APIs, or a real browser.
16. Add clear README commands for each stage.

Definition of done:
- Given a registered video source, the pipeline can download audio, split it, transcribe it, merge the transcript, register all outputs, and search the resulting transcript locally.
```

---

## 23. Reference Links

- yt-dlp: https://github.com/yt-dlp/yt-dlp
- FFmpeg: https://ffmpeg.org/
- OpenAI Whisper: https://github.com/openai/whisper
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Playwright Python: https://playwright.dev/python/docs/intro
- PyMuPDF: https://pymupdf.readthedocs.io/
- SQLite FTS5: https://sqlite.org/fts5.html
- Qdrant: https://qdrant.tech/documentation/
- Qdrant Python client: https://github.com/qdrant/qdrant-client
- Neo4j Python driver: https://neo4j.com/docs/python-manual/current/

---

## 24. Final Technology Decision

Use this as the core stack:

```text
Python + Playwright + httpx + BeautifulSoup/selectolax
+ yt-dlp + FFmpeg
+ faster-whisper
+ PyMuPDF
+ SQLite + FTS5
+ Pydantic + Typer + pytest
```

Then add later:

```text
Qdrant + embeddings
Neo4j
LLM entity/topic extraction
Streamlit or React+Vite review UI
```

The first milestone should be brutally practical:

> One official hearing day video in, one reliable timestamped searchable transcript out, with every source and derived artifact registered.
