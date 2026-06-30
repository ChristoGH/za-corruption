# commission-api

Read-only FastAPI surface over the commission stores (M5). It queries Qdrant
(semantic search) and Neo4j (evidence graph) through the shaped store classes in
`commission_ingestion`; it owns no ingestion logic and opens read sessions only.

## Endpoints

- `GET /health` — liveness of both stores (`{status, qdrant, neo4j}`); never 500s.
- `GET /search?q=&commission=&day=&speaker=&limit=` — semantic search; ranked hits
  with day, page, source URL, speakers, snippet, and `chunk_id` (the join key).
- `GET /chunk/{chunk_id}/graph` — one chunk's neighborhood: entities **mentioned**
  (leads) and the **claims** supported by it (attributed testimony), in separate
  fields. Each claim carries `claim_id`.
- `GET /claim/{claim_id}` — one claim's full provenance: quote, stored status,
  STATED_BY speaker, the SUPPORTED_BY chunk (day, page, source URL), and mentions.

Mentions are never merged with claims: a mention is a lead, a claim is an
attributed allegation in the public record — not a finding of fact.

## Run

```sh
make stores-up          # Qdrant + Neo4j via docker-compose
make api-dev            # uvicorn on http://localhost:8000 (reload)
```

Config comes from the environment (defaults match docker-compose):
`QDRANT_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `WEB_ORIGIN`.
CORS allows the `WEB_ORIGIN` only.

## Test

```sh
uv run pytest apps/api/tests        # no live stores needed (DI-injected fakes)
```

The tests inject fake stores through `app.dependency_overrides`, so the real
embedder (torch) and store connections are never constructed under pytest.
