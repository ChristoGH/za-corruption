# Plan — staying current: ingest new days, fill video-only gaps, publish the delta

Status: spec. Owner: Christo. The commission is ongoing, so the corpus must stay live and each
new hearing day should be ingestible and *postable* with low effort.

Three components, in dependency order. Component 1 is runnable today; 2 and 3 are builds.

## 0. Coverage map (the thing that drives all three)

Enumerate every official hearing day and label it: **transcript ingested** · **video-only**
(no transcript yet) · **missing**. Cross-reference `data/sources/source_registry.jsonl` (what
discovery found) against what's parsed/loaded. This map is both a deliverable (a LinkedIn post
in its own right — "what the public record does and doesn't yet contain") and the controller
that tells components 1–3 what to do for each day.

## 1. Ingest the latest transcripts + missing pieces (runnable now)

`discovery/madlanga.py` already scrapes the live site for **all** hearing days, so "latest" is
just a re-run; upsert-by-URL adds new days and leaves existing ones untouched.

```bash
make retrieve-discover        # re-scrape → registry gains new days/transcripts
make retrieve-download        # fetch new PDFs
# then for the NEW days only (all idempotent — they skip what's already done):
uv run parse-corpus  --commission madlanga
uv run extract-corpus --all --batch --model claude-haiku-4-5 --budget-usd 15
uv run build-graph   --commission madlanga --with-claims
```

- "Missing pieces" = the few registry entries that are 404 at source, or days present as video
  but not transcript → handed to component 2.
- Wrap this as a single `make ingest-latest` target so it's one command.

## 2. Video-only extraction (the build — blueprint exists)

For days that exist **only as video**, ingest via the transcription path already designed in
`docs/madlanga_full_day_video_transcription_technology.md`:

```
discover video URL → yt-dlp audio-only → normalise WAV → faster-whisper (timestamps)
   → speaker diarisation → SourceRecord (source_type=video_transcript, authoritative=false)
   → chunks (timestamp provenance) → same Qdrant + Neo4j pipeline
```

Key invariants so it stays honest:
- A third **provenance spine** path: `Document → Segment → Chunk` (timestamps replace pages),
  alongside the existing paged-PDF and bootstrap paths.
- Machine-transcribed text is **flagged** (`authoritative=false`, transcription model recorded)
  so it is distinguishable from official transcripts and can be excluded or caveated in any post.
- Everything downstream is unchanged — chunk → extract → `:Claim` → graph all consume the same
  `ChunkRecord`, whether it came from a PDF or Whisper.

This is what closes the video-only gaps the coverage map surfaces. Scope as its own milestone
(`feat/m5-video-ingest`): yt-dlp + faster-whisper + diarisation + the Segment spine + tests.

**Status (captions lane BUILT):** the fast lane ships first: `ingest-video` fetches YouTube
caption tracks with yt-dlp (manual track preferred, else auto), parses the VTT (rolling-caption
dedupe), and writes time-provenanced ChunkRecords (`time_start`/`time_end` seconds, pages null)
into the normal processed dir; `load-qdrant` and `build-graph` pick them up unchanged via the
page-less spine. Records are `source_type="video"`, `authoritative=false`, with
`transcription_method` recorded. Discovery now also registers YouTube links on hearing.php.
The whisper + diarisation quality lane stays open as the upgrade path (same registry records,
same chunk shape, better text + speaker turns).

## 3. Publish-the-delta pipeline ("what the most recent day added")

After a new day loads, compute and surface **the delta**, so posting stays current:

- **New entities** first named on day N (a person/company entering the story).
- **New claims** and, in particular, **new ties to existing key figures** (e.g., "day N added 14
  new claims naming Matlala, 3 of them denials").
- **Stance shifts** — a previously-asserted tie that gained a denial; a newly-contested figure.
- Auto-generate: a one-paragraph "Day N added…" brief + a refreshed cosmograph centred on
  whatever the day moved most. Both as *drafts* — human review before publishing (named
  individuals; the allegations-not-findings line is mandatory).

Implementation: a `corpus-delta --since <day|date>` command diffing the graph/claims before and
after the new load, emitting the brief + the data for the cosmograph. Pairs with the live-from-
Neo4j cosmograph (`plans/live-cosmograph-from-neo4j.md`) so the visual is always current.

## Scheduling

A weekly (or post-hearing) **scheduled task**: run component 1, and if new days appeared, run
the delta (3) and ping Christo with the "Day N added…" draft to review and post. That turns
"stay current" from a chore into a notification.

## Acceptance

- `make ingest-latest` brings any new hearing days into Qdrant + Neo4j idempotently.
- The coverage map lists every day as transcript / video-only / missing.
- A new day yields a reviewable "what it added" brief + an updated cosmograph.
- Video-transcribed days are in the graph, flagged `authoritative=false`, never presented as
  official transcript text.

## Out of scope / gated

- Public hosting of any of this is gated on the §7.3 license/publication decision (project-state).
  Author-side posts (LinkedIn) are fine; an outward-facing product is not, yet.
