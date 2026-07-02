# Neo4j Model

Canonical graph storage design, shared by all commissions. Node/relationship semantics
live in `ontology.md`; this file covers the **provenance spine, constraints, write
pattern and queries**.

## Canonical provenance spine: Document → Page → Chunk

```
(:Commission)-[:HAS_HEARING]->(:HearingDay)
(:HearingDay)-[:HAS_DOCUMENT]->(:Document)
(:Document)-[:HAS_PAGE]->(:Page)
(:Page)-[:HAS_CHUNK]->(:Chunk)
```

Do **not** write `(:Document)-[:HAS_CHUNK]->(:Chunk)` directly. A direct shortcut edge
may be added later only as an explicitly derived convenience relationship, never as the
source-of-truth path. `:Page` nodes give clean page-level provenance and queries; chunks
still carry `page_start`/`page_end` for chunks spanning pages.

**Bootstrap tier note:** DSFSI plaintext transcripts (`authoritative=false`) have no page
numbers. When parsing arrives, attach chunks directly under `:Document` with
`authoritative=false` on the document node — do **not** invent `:Page` nodes for
bootstrap text. Official PDFs use the full `Document → Page → Chunk` spine.

**Video caption tier note:** video-only hearing days ingested from YouTube caption
tracks (`ingest-video`, `source_type="video"`, `document_type="Video"`,
`authoritative=false`) take the same page-less path: chunks attach directly under the
`:Document` and carry `time_start`/`time_end` (seconds into the video) instead of
`page_start`/`page_end`. The registry record's `transcription_method` says how the text
was produced. Machine-transcribed text is never presented as official transcript.

## Relationship naming (settled)

| Use | Relationship |
|---|---|
| Entity mention in a chunk | `MENTIONED_IN` |
| Speaker → chunk they spoke in | `SPOKE_IN` |
| Claim → person who made it | `STATED_BY` |
| Claim → supporting evidence chunk | `SUPPORTED_BY` |
| Event → supporting evidence chunk | `EVIDENCED_BY` |
| Person → commission/procedural role | `HAS_PROCEDURAL_ROLE` |
| Person → real-world position | `HELD_POSITION` |
| Position → organisation | `AT_ORG` |

`APPEARS_IN` is **not** canonical — do not use it.

## Constraints

Run before any ingestion (`infra/neo4j/constraints.cypher`):

```cypher
CREATE CONSTRAINT commission_slug IF NOT EXISTS
FOR (c:Commission) REQUIRE c.slug IS UNIQUE;
CREATE CONSTRAINT hearing_day_key IF NOT EXISTS
FOR (h:HearingDay) REQUIRE h.key IS UNIQUE;
CREATE CONSTRAINT document_sha IF NOT EXISTS
FOR (d:Document) REQUIRE d.sha256 IS UNIQUE;
CREATE CONSTRAINT page_key IF NOT EXISTS
FOR (p:Page) REQUIRE p.key IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;
CREATE CONSTRAINT person_name IF NOT EXISTS
FOR (p:Person) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT organisation_name IF NOT EXISTS
FOR (o:Organisation) REQUIRE o.name IS UNIQUE;
CREATE CONSTRAINT place_name IF NOT EXISTS
FOR (p:Place) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT role_name IF NOT EXISTS
FOR (r:Role) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT position_title IF NOT EXISTS
FOR (p:Position) REQUIRE p.title IS UNIQUE;
CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (e:Event) REQUIRE e.event_id IS UNIQUE;
```

## Write pattern

The shared `neo4j_store` writes the spine including `:Page`, keyed by `commission_slug`.
Illustrative core (full code lives in `packages/ingestion`, see
`build-plan-shared-core.md`):

```cypher
MERGE (com:Commission {slug: $commission_slug})
  SET com.name = $commission_name
MERGE (h:HearingDay {key: $hearing_key})
  SET h.day_no = $day_no, h.date = $date, h.source_url = $source_url
MERGE (d:Document {sha256: $sha256})
  SET d.filename = $filename, d.url = $source_url, d.document_type = $document_type
MERGE (pg:Page {key: $sha256 + ':' + toString($page_no)})
  SET pg.page_no = $page_no
MERGE (c:Chunk {chunk_id: $chunk_id})
  SET c.text = $text, c.page_start = $page_start, c.page_end = $page_end,
      c.speakers = $speakers
MERGE (com)-[:HAS_HEARING]->(h)
MERGE (h)-[:HAS_DOCUMENT]->(d)
MERGE (d)-[:HAS_PAGE]->(pg)
MERGE (pg)-[:HAS_CHUNK]->(c)
```

A chunk attaches to the `:Page` of its `page_start`; chunks spanning pages keep the full
range in `page_start`/`page_end`.

## Example queries

People mentioned alongside a given organisation (any commission):
```cypher
MATCH (p:Person)-[:MENTIONED_IN]->(c:Chunk)<-[:MENTIONED_IN]-(o:Organisation)
WHERE toLower(o.name) CONTAINS "ipid"
RETURN p.name, count(c) AS mentions ORDER BY mentions DESC LIMIT 25;
```

Cross-commission entity recurrence (enabled by the shared model):
```cypher
MATCH (com:Commission)-[:HAS_HEARING]->(:HearingDay)-[:HAS_DOCUMENT]->
      (:Document)-[:HAS_PAGE]->(:Page)-[:HAS_CHUNK]->(c:Chunk)<-[:MENTIONED_IN]-(p:Person)
RETURN p.name, collect(DISTINCT com.slug) AS commissions
HAVING size(collect(DISTINCT com.slug)) > 1;
```

Procedural role vs held position for one person:
```cypher
MATCH (p:Person {name: "Anoj Singh"})
OPTIONAL MATCH (p)-[:HAS_PROCEDURAL_ROLE]->(r:Role)
OPTIONAL MATCH (p)-[:HELD_POSITION]->(pos:Position)-[:AT_ORG]->(o:Organisation)
RETURN p.name, collect(DISTINCT r.name) AS roles,
       collect(DISTINCT pos.title + " @ " + o.name) AS positions;
```
