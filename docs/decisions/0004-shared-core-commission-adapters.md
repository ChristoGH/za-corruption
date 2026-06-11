# 0004 — Shared core with commission adapters

- **Status:** Accepted
- **Date:** 2026-06-08
- **Supersedes detail in:** the original root-level `practical-build-plan-zondo.md` and
  `practical-build-plan-madlanga.md` (now `docs/build-plan-zondo.md`,
  `docs/build-plan-madlanga.md`).

## Context

The two original build plans had drifted into near-duplicate, partly-conflicting
implementations. Madlanga was a complete reference implementation; Zondo was a delta
document layered on it. They disagreed on discovery return type (bare URLs vs structured
records), Qdrant collection naming, the chunk provenance path, and relationship naming,
and only Zondo modelled real-world positions and a findings layer.

## Decision

Madlanga and Zondo are **not separate implementations**. They are **commission adapters**
over one shared ingestion, storage and ontology core.

1. **One shared Qdrant collection — `commission_transcripts`.** No per-commission
   collections for the MVP. Every point carries `commission_slug`, `commission_name`,
   `source_type`, `document_type`, `day_no`, `date`, `source_url`, `filename`, `sha256`,
   `page_start`, `page_end`, `chunk_id`, `speakers`. A future `collection_strategy`
   setting may add per-commission collections via config. Rationale: cross-commission
   ("which entities recur across Zondo and Madlanga?") is a primary goal; filter by
   `commission_slug` for single-commission views. See `qdrant-model.md`.
2. **Structured discovery records** (`SourceRecord`), never bare URL lists. Madlanga is
   upgraded to match. See `build-plan-shared-core.md` §4.
3. **Canonical Neo4j spine `Document → Page → Chunk`**, not a direct `Document → Chunk`.
   See `neo4j-model.md`.
4. **Settled relationship naming:** `MENTIONED_IN`, `SPOKE_IN`, `STATED_BY`,
   `SUPPORTED_BY`, `EVIDENCED_BY`, `HAS_PROCEDURAL_ROLE`, `HELD_POSITION`, `AT_ORG`.
   `APPEARS_IN` is banned.
5. **Procedural role vs real-world position is shared** (not Zondo-only):
   `(:Person)-[:HAS_PROCEDURAL_ROLE]->(:Role)` is distinct from
   `(:Person)-[:HELD_POSITION]->(:Position)-[:AT_ORG]->(:Organisation)`.
6. **Per-commission adapter config** holds the only real differences: discovery
   strategy, day/date regex, speaker regex, role-hint map, taxonomy overlay,
   `supported_source_types`, `ingestion_phases`.
7. **Claim/event provenance model is canonical from the start**, even if the first
   milestone only writes mentions and roles.
8. **LLM extraction uses the Anthropic Claude SDK directly** (with prompt caching),
   behind a pluggable extractor interface.

## Consequences

- Shared code lives once in `packages/ingestion`; each commission is a thin adapter.
- Cross-commission retrieval and graph queries are natural; single-commission views are a
  filter.
- The canonical model docs (`ontology.md`, `qdrant-model.md`, `neo4j-model.md`) are
  authoritative; build-plan files are reduced to adapter deltas pointing at them.
- Both adapters' Neo4j writers and the Madlanga discovery function require updating from
  their original drafts (Page layer; structured records).

## Document map

| File | Role |
|---|---|
| `build-plan-shared-core.md` | shared pipeline, adapter interface, services, deps |
| `build-plan-zondo.md` | Zondo adapter deltas |
| `build-plan-madlanga.md` | Madlanga adapter deltas |
| `ontology.md` | canonical nodes/relationships/overlays |
| `qdrant-model.md` | shared collection + payload |
| `neo4j-model.md` | provenance spine, constraints, queries |
