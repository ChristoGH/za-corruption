# Canned Cypher Queries — Commission Evidence Graph

Run these against Neo4j after a successful `build-graph` load.  All queries
are read-only and commission-agnostic unless noted.

Connect via Browser at `http://localhost:7474` or with:

```bash
docker compose exec neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-changeme}"
```

---

## 1. People mentioned alongside a given organisation

Finds every person who co-appears with an organisation in the same chunk —
a proxy for "who was named in the same breath as this body?"

```cypher
MATCH (p:Person)-[:MENTIONED_IN]->(c:Chunk)<-[:MENTIONED_IN]-(o:Organisation)
WHERE toLower(o.name) CONTAINS "ipid"
RETURN p.name, count(c) AS co_mentions
ORDER BY co_mentions DESC
LIMIT 25;
```

Replace `"ipid"` with any org name fragment (e.g. `"saps"`, `"npa"`, `"hawks"`).

---

## 2. Speakers and their procedural roles

Lists every person who spoke in at least one chunk, with their resolved
canonical name and the speaker label they used most.

```cypher
MATCH (p:Person)-[r:SPOKE_IN]->(c:Chunk)
RETURN p.name,
       r.speaker_label AS most_common_label,
       count(c) AS chunks_spoken_in
ORDER BY chunks_spoken_in DESC
LIMIT 30;
```

---

## 3. Places mentioned by hearing day

Shows which locations come up in each day's testimony — useful for
identifying hearing days focused on a specific geography.

```cypher
MATCH (h:HearingDay)-[:HAS_DOCUMENT]->(:Document)-[:HAS_PAGE]->(:Page)
      -[:HAS_CHUNK]->(c:Chunk)<-[:MENTIONED_IN]-(pl:Place)
RETURN h.day_no, h.date, pl.name, count(c) AS mentions
ORDER BY h.day_no, mentions DESC;
```

For bootstrap (page-less) docs use the two-hop variant:

```cypher
MATCH (h:HearingDay)-[:HAS_DOCUMENT]->(:Document)-[:HAS_CHUNK]->(c:Chunk)
      <-[:MENTIONED_IN]-(pl:Place)
RETURN h.day_no, h.date, pl.name, count(c) AS mentions
ORDER BY h.day_no, mentions DESC;
```

---

## 4. Top co-mentioned entity pairs (person ↔ person)

Entity pairs that appear together most often — the highest-weight edges in
a co-mention network.

```cypher
MATCH (a:Person)-[:MENTIONED_IN]->(c:Chunk)<-[:MENTIONED_IN]-(b:Person)
WHERE a.name < b.name
RETURN a.name, b.name, count(DISTINCT c) AS shared_chunks
ORDER BY shared_chunks DESC
LIMIT 20;
```

---

## 5. Full provenance path from a chunk back to its source URL (paged doc)

Given a `chunk_id` from a Qdrant search hit, trace the spine to the
hearing day, document, and page — the MVP-adjacent check.

```cypher
MATCH (com:Commission)-[:HAS_HEARING]->(h:HearingDay)
      -[:HAS_DOCUMENT]->(d:Document)
      -[:HAS_PAGE]->(pg:Page)
      -[:HAS_CHUNK]->(ck:Chunk {chunk_id: $chunk_id})
RETURN com.slug AS commission,
       h.day_no AS day,
       h.date AS date,
       d.sha256 AS doc_sha256,
       d.source_url AS url,
       pg.page_no AS page,
       ck.speakers AS speakers;
```

For bootstrap docs (no `:Page`):

```cypher
MATCH (com:Commission)-[:HAS_HEARING]->(h:HearingDay)
      -[:HAS_DOCUMENT]->(d:Document)
      -[:HAS_CHUNK]->(ck:Chunk {chunk_id: $chunk_id})
RETURN com.slug, h.day_no, h.date, d.sha256, d.source_url, ck.speakers;
```

---

## 6. Cross-commission entity recurrence

Entities that appear in more than one commission — enabled by the shared
collection design (one graph, `commission_slug` on every node).

```cypher
MATCH (com:Commission)-[:HAS_HEARING]->(:HearingDay)-[:HAS_DOCUMENT]->
      (:Document)-[:HAS_PAGE]->(:Page)-[:HAS_CHUNK]->(c:Chunk)
      <-[:MENTIONED_IN]-(p:Person)
WITH p, collect(DISTINCT com.slug) AS commissions
WHERE size(commissions) > 1
RETURN p.name, commissions
ORDER BY p.name;
```

---

## 7. Hearing days with the most distinct entities mentioned

A rough measure of "dense" days — useful for choosing post-publication
examples.

```cypher
MATCH (h:HearingDay)-[:HAS_DOCUMENT]->(:Document)-[:HAS_PAGE]->(:Page)
      -[:HAS_CHUNK]->(c:Chunk)<-[:MENTIONED_IN]-(e)
WHERE e:Person OR e:Organisation OR e:Place
WITH h, count(DISTINCT e) AS distinct_entities, count(c) AS chunks
ORDER BY distinct_entities DESC
RETURN h.day_no, h.date, distinct_entities, chunks
LIMIT 15;
```

---

_All queries assume `build-graph` has been run and
`infra/neo4j/constraints.cypher` applied (`make neo4j-constraints`)._
