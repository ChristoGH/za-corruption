# Qdrant Model

Canonical vector-store design, shared by all commissions.

## Collection strategy: one shared collection

**Decision (ADR 0004):** use a single collection **`commission_transcripts`** for every
commission. Do **not** create per-commission collections (`zondo_transcripts`,
`madlanga_transcripts`) for the MVP.

Rationale: cross-commission questions are a primary goal — e.g. *"Which people, places
or institutions recur across both Zondo and Madlanga?"* A shared collection makes
comparative retrieval natural; filter by `commission_slug` when you want one commission.

A `collection_strategy` config setting **may** later introduce per-commission
collections, but canonical docs and the MVP implementation assume the shared collection.

## Vectors

| Setting | Value |
|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` |
| Vector size | `384` |
| Distance | `Cosine` |
| Normalisation | `normalize_embeddings=True` at encode time |

Point `id` = the chunk's `chunk_id` (sha256 of chunk text), so re-ingesting a chunk
upserts rather than duplicates.

## Payload schema

Every point **must** carry these fields so the shared collection can be filtered to any
slice:

| Field | Type | Purpose |
|---|---|---|
| `commission_slug` | string | primary filter (`"zondo"`, `"madlanga"`) |
| `commission_name` | string | display |
| `source_type` | string | `"transcript"`, `"statement"`, `"report"`, … |
| `document_type` | string | `DocumentType` vocab (`"Transcript"`, `"Affidavit"`, …) |
| `day_no` | int \| null | hearing day number |
| `date` | string | ISO `YYYY-MM-DD` where known |
| `source_url` | string | download URL |
| `authoritative` | bool | `true` for official PDFs; `false` for DSFSI bootstrap plaintext |
| `filename` | string | |
| `sha256` | string | document hash (links to Neo4j `:Document`) |
| `page_start` | int | |
| `page_end` | int | |
| `chunk_id` | string | links to Neo4j `:Chunk` |
| `speakers` | string[] | speaker labels in the chunk |

## Filtering examples

- One commission: filter `commission_slug == "zondo"`.
- Transcripts only: `source_type == "transcript"`.
- A single hearing day: `commission_slug == "madlanga" AND day_no == 59`.
- Cross-commission (comparative): no `commission_slug` filter.

## Cross-store contract

`chunk_id` and `sha256` are the join keys between Qdrant and Neo4j. A Qdrant hit must be
resolvable to its `:Chunk` (and from there the provenance spine) in Neo4j. Keep the two
stores consistent: a chunk written to one is written to the other in the same pipeline
run. See `neo4j-model.md` and `build-plan-shared-core.md` §5.
