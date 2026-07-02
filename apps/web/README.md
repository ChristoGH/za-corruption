# commission-web

The read-only public surface (M5): one page that searches the corpus, opens a
result's evidence neighborhood, and drills into a single claim. Vite + React +
TypeScript, `useState` only, no router and no state library.

## What it shows

- **Search** the shared Qdrant collection; each result row carries commission,
  hearing day and date, page range, speakers, a snippet, and a link to the
  official PDF.
- Clicking a result opens its **evidence neighborhood**:
  - **Mentions** (blue, low-key): people, organisations, and places named in the
    passage, badged "mentioned, a lead, not a finding".
  - **Claims** (red cards, visibly distinct): attributed testimony supported by
    the passage. Each card shows the STATED_BY speaker, the verbatim quote, a
    stored-status badge (currently always "alleged"), a flag for raw,
    uncanonicalised speakers, and a source link.
- Clicking a claim opens its **full provenance**: quote, day, page, certainty,
  attribution, the names in the claim, and the official source.

Mentions and claims are never merged: the topology, not the wording, carries the
qualification.

## Run

```sh
make stores-up      # Qdrant + Neo4j
make api-dev        # the API on http://localhost:8000
make web-install    # once, to install node deps
make web-dev        # Vite dev server on http://localhost:5173
```

Point the app at a non-default API with `VITE_API_BASE` (see `.env.example`).

These four commands assume the stores are installed and populated. For a full from-scratch
bring-up (deps, `.env`, starting and loading the stores, then both apps), follow the
**Quick start** in the [root README](../../README.md).

## Build

```sh
make web-build      # tsc + vite build into apps/web/dist
```
