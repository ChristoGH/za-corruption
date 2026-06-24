# Task — live cosmograph from Neo4j

Status: spec (not built). Owner: Christo. Depends on: Neo4j loaded (done), the static
generator `scripts/build_cosmograph_data.py` (done, the data contract reference).

## Goal

Replace the *baked-in* cosmograph (`linkedin/matlala_live_cosmograph.html`, data frozen at
generation time) with one that **queries the live graph on load**, so it always reflects the
current data — including the raw-speaker claims recovered under ADR 0007 — and can re-centre on
**any** entity, not just Matlala. Same canvas renderer; only the data source changes.

## Why

- The static file is great for sharing/recording, but goes stale the moment the graph changes
  (a re-load, a seed addition, the next hearing day).
- "Re-centre on any figure" turns one poster into an **explorer** — type a name, see their web.
- It's the natural home for the stance/role toggles without re-generating a file each time.

## Approach — Neo4j HTTP Query API (no driver build step)

Neo4j 5 exposes an HTTP query endpoint, so a single static HTML page can query it with `fetch`
— no bundler, no server. Keep the page self-contained (matches the current cosmograph).

```
POST http://localhost:7474/db/neo4j/query/v2
Headers: Authorization: Basic base64(neo4j:<password>), Content-Type: application/json
Body: {"statement": "<cypher>", "parameters": {...}}
```

**Auth handling (the one real decision).** Options, in order of preference:
1. **Local-only prompt:** a tiny password field in the page (stored in `sessionStorage`), used to
   build the Basic header. Fine for a localhost tool; never commit a password.
2. **Read-only user:** create a Neo4j user with read-only privileges for this page
   (`CREATE USER viz SET PASSWORD '…'; GRANT ROLE reader TO viz;`) so a leaked credential can't write.
3. If ever hosted (not localhost), put a thin read-only proxy in front — never expose Neo4j directly.

CORS: Neo4j must allow the page origin. For `file://`/localhost, set
`server.http.cors.allowed_origins` (or serve the HTML from a `python -m http.server` on localhost
so origin is `http://localhost:<port>`).

## Queries (parameterised on a `$center` entity name + `$minShared`)

Reproduce the static generator's three passes as Cypher:

```cypher
// 1. ego nodes: the center + its top co-mentioned people/orgs
MATCH (c:Person {name:$center})-[:MENTIONED_IN]->(ck:Chunk)<-[:MENTIONED_IN]-(o)
WHERE (o:Person OR o:Organisation) AND o<>c
WITH o, count(DISTINCT ck) AS shared
WHERE shared >= $minShared
RETURN o.name AS name, labels(o)[0] AS type, shared ORDER BY shared DESC LIMIT 20;

// 2. pairwise edges among the chosen node set (run client-side over returned ids, or a second query)
MATCH (a)-[:MENTIONED_IN]->(ck:Chunk)<-[:MENTIONED_IN]-(b)
WHERE a.name IN $names AND b.name IN $names AND id(a)<id(b)
RETURN a.name AS s, b.name AS t, count(DISTINCT ck) AS w;

// 3. stance toward center: assert/deny/question per node, from claims naming both
MATCH (cl:Claim)-[:MENTIONS]->(c:Person {name:$center})
MATCH (cl)-[:MENTIONS]->(o) WHERE o.name IN $names
RETURN o.name AS name,
  sum(CASE WHEN cl.text =~ '(?i).*(denied|denies|disputed|vehemently).*' THEN 1 ELSE 0 END) AS deny,
  sum(CASE WHEN cl.text =~ '(?i).*(asked|whether|questioned|put to).*'     THEN 1 ELSE 0 END) AS question,
  count(*) AS total;
```

Role per node: map from the seed (ship a small `roles.json` alongside, or add a `role` property
to `:Person`/`:Organisation` during graph build — cleaner long-term). A representative claim per
node: one extra query per click (lazy-load the detail panel) rather than up front.

## Rendering

Reuse `linkedin/matlala_live_cosmograph.html` **as-is** — its renderer already consumes
`{nodes:[{id,name,role,ment,w,stance,sc,note?,claim?}], links:[{s,t,w}], MAT}`. Swap the inline
`const G = {...}` for an async `loadGraph($center)` that runs the queries, shapes the same object,
and calls an `init(G)`. Add: a search box (re-centre), and the role/stance legend already there.

## Acceptance

- Page loads, prompts for password once, renders Matlala's web from the live graph (counts match
  `scripts/build_cosmograph_data.py` ± the raw-speaker delta).
- Typing another name (e.g. "Lt-Gen Shadrack Sibiya") re-centres the graph on that figure.
- `cl.speaker_unresolved = true` claims are included (coverage reflects ADR 0007).
- No write capability from the page (read-only user or proxy).
- Still a single self-contained HTML file; works from `python -m http.server` on localhost.

## Out of scope (later)

- Hosting it publicly (gated on the §7.3 license/publication decision — do NOT expose Neo4j or
  named-individual claims outbound without that decision).
- The full ~30k-claim graph via the real Cosmograph WebGL library (separate perf track).
