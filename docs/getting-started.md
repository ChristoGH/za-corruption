# Getting Started — Source Retrieval

Operational guide for discovering and downloading commission source artifacts.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (recommended) or Python 3.12+
- Optional: Docker (reproducible runs with Playwright preinstalled)
- **No Qdrant or Neo4j required** for source retrieval

## Setup (uv)

```bash
# From repo root
uv sync --all-packages --all-extras
cp .env.example .env   # optional overrides

# Local Playwright (only needed for Zondo manual-session harvest)
uv run playwright install chromium
```

## Artifact pipeline

| Stage | Status | Command | Output |
|---|---|---|---|
| Discover (Madlanga) | **Implemented + verified** | `uv run retrieve-sources --commission madlanga --discover-only` | `data/sources/source_registry.jsonl` |
| Download (Madlanga) | **Implemented + verified** | `uv run retrieve-sources --commission madlanga --download` | `data/raw/madlanga/` |
| Check for new publications | **Implemented** | `uv run retrieve-sources --commission madlanga --discover-only --write-report` | `reports/source-checks/` |
| Download new only | **Implemented** | `uv run retrieve-sources --commission madlanga --download-new-only --write-report` | registry + `data/raw/` + reports |
| Discover (Zondo bootstrap) | **Implemented, non-authoritative** | `uv run retrieve-sources --commission zondo --zondo-source bootstrap --discover-only` | same registry |
| Download (Zondo bootstrap) | **Implemented** | `uv run retrieve-sources --commission zondo --zondo-source bootstrap --download` | `data/raw/zondo/*.txt` |
| Discover (Zondo official PDFs) | **Blocked (Cloudflare)** | `uv run retrieve-sources --commission zondo --zondo-source official --discover-only` | requires manual session |
| Parse / chunk | Planned | — | `data/interim/`, `data/processed/` |
| Qdrant ingest | Planned | — | `commission_transcripts` collection |
| Neo4j ingest | Planned | — | evidence graph |

```mermaid
flowchart LR
  subgraph live [Implemented]
    discover[retrieve-sources --discover-only]
    registry[source_registry.jsonl]
    download[retrieve-sources --download]
    raw[data/raw/slug/]
    discover --> registry --> download --> raw
  end
  subgraph future [Planned]
    parse[parse PDF/txt]
    chunk[speaker chunks]
    stores[Qdrant + Neo4j]
    raw --> parse --> chunk --> stores
  end
```

## Commands

### Madlanga (official site, ~108 transcript PDFs)

```bash
uv run retrieve-sources --commission madlanga --discover-only
uv run retrieve-sources --commission madlanga --download
```

Transcripts are embedded in `hearing.php` as JSON inside `data-tabs` attributes (not plain anchor links).

### Zondo bootstrap (DSFSI plaintext, default)

```bash
uv run retrieve-sources --commission zondo --discover-only
uv run retrieve-sources --commission zondo --download
```

- Source: [dsfsi/project-state-capture](https://github.com/dsfsi/project-state-capture) pinned to commit `e2bc9d9183f2`.
- Licence: **CC-BY-SA-4.0** — attribution required if redistributed.
- Records have `authoritative=false` and `notes` citing the bootstrap provenance.
- Plaintext files have **no page numbers** — the `Document → Page → Chunk` spine cannot be built for this tier when parsing arrives.

### Zondo official PDFs (manual session only)

The official site (`statecapture.org.za`) is behind Cloudflare. Headless Chromium alone does not pass the challenge.

To attempt official PDF discovery:

1. Solve the Cloudflare challenge in a real browser.
2. Export either:
   - `cf_clearance` cookie → `INGEST_ZONDO_CF_COOKIE` in `.env` (short-lived, ~30 min, IP/UA-bound), or
   - Playwright `storage_state` JSON → `INGEST_ZONDO_STORAGE_STATE=/path/outside/repo/state.json`
3. Run:

```bash
uv run retrieve-sources --commission zondo --zondo-source official --discover-only
```

**Do not commit** session files or cookie values.

### Both commissions

```bash
uv run retrieve-sources --commission both --zondo-source bootstrap --download
```

### Check for new publications

Re-run discovery against the live site and compare URLs to the registry. A publication is "new" when its canonical URL is not yet in `source_registry.jsonl`.

```bash
# Discover only — prints New: N in the summary
uv run retrieve-sources --commission madlanga --discover-only

# Discover and write JSON + Markdown reports (even when New: 0)
uv run retrieve-sources --commission madlanga --discover-only --write-report

# Discover, download only newly found records, and write reports
uv run retrieve-sources --commission madlanga --download-new-only --write-report
```

Reports are written to `reports/source-checks/` (gitignored, regenerable). Each run produces a timestamped pair:

- `source-check_YYYYMMDDTHHMMSSZ.json` — machine-readable summary and new-publication list
- `source-check_YYYYMMDDTHHMMSSZ.md` — human-readable summary

**Limitations:**

- New means a newly discovered URL, not a content revision at an existing URL (use `--force` to re-download known URLs).
- Zondo official PDF monitoring requires a manual Cloudflare session; Madlanga and Zondo bootstrap are fully supported.
- No scheduler is included — run manually or wire into cron/CI yourself.

### Makefile shortcuts

```bash
make install
make test
make retrieve-discover COMMISSION=madlanga
make retrieve-download COMMISSION=both ZONDO_SOURCE=bootstrap
```

## Docker (retrieval only)

Reproducible environment with Playwright 1.49 + Chromium preinstalled.

```bash
docker compose build ingestion
docker compose run --rm ingestion --commission madlanga --discover-only
docker compose run --rm ingestion --commission zondo --zondo-source bootstrap --download
```

Docker reliably runs **Madlanga + Zondo-bootstrap**. It does **not** bypass Zondo official Cloudflare without a mounted manual session.

## Registry

- Path: `data/sources/source_registry.jsonl` (single combined file, versioned in git)
- Dedup: primary key is `url` (canonicalised)
- SHA256 groups duplicate underlying files for review only — URLs are never merged away
- Downloaded PDFs/txt under `data/raw/` are gitignored

## Verification

```bash
make test
head -3 data/sources/source_registry.jsonl
ls data/raw/madlanga/ | head
```

## Known limitations

1. **Zondo official site**: Cloudflare blocks automated access; use bootstrap or manual session.
2. **Zondo bootstrap**: plaintext only, ~147 per-day files in `data/interim/` (not all 399 days as separate files); no page metadata.
3. **Madlanga date parsing**: some filename date formats may parse incorrectly; RECORD PDFs with `YYYYMMDD` are reliable.
4. **Madlanga mixed artefacts**: press releases and notices on index pages may classify as `supporting_document` unless heuristics match.
