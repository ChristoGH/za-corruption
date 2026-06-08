Here is a repo structure that will work for the current ingestion/knowledge-graph work while leaving a clean path to a React + Vite frontend and Python API/backend later.

commission-intelligence-platform/
│
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── package.json
├── pnpm-workspace.yaml
│
├── docs/
│   ├── architecture.md
│   ├── ontology.md
│   ├── taxonomy.md
│   ├── data-provenance.md
│   ├── ingestion-pipeline.md
│   ├── neo4j-model.md
│   ├── qdrant-model.md
│   ├── api-spec.md
│   └── decisions/
│       ├── 0001-use-qdrant-and-neo4j.md
│       ├── 0002-evidence-graph-not-truth-graph.md
│       └── 0003-monorepo-structure.md
│
├── data/
│   ├── README.md
│   ├── sources/
│   │   ├── zondo_sources.jsonl
│   │   ├── madlanga_sources.jsonl
│   │   └── source_registry.sqlite
│   │
│   ├── raw/
│   │   ├── zondo/
│   │   │   └── .gitkeep
│   │   └── madlanga/
│   │       └── .gitkeep
│   │
│   ├── interim/
│   │   ├── zondo/
│   │   └── madlanga/
│   │
│   ├── processed/
│   │   ├── zondo/
│   │   └── madlanga/
│   │
│   └── exports/
│       ├── graph/
│       ├── qdrant/
│       └── reports/
│
├── infra/
│   ├── docker/
│   │   ├── neo4j/
│   │   │   └── plugins/
│   │   ├── qdrant/
│   │   └── api/
│   │       └── Dockerfile
│   │
│   ├── neo4j/
│   │   ├── constraints.cypher
│   │   ├── seed_taxonomy.cypher
│   │   ├── indexes.cypher
│   │   └── reset_database.cypher
│   │
│   ├── qdrant/
│   │   ├── collections.yaml
│   │   └── payload_schema.md
│   │
│   └── deployment/
│       ├── local.md
│       ├── staging.md
│       └── production.md
│
├── apps/
│   │
│   ├── api/
│   │   ├── README.md
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── dependencies.py
│   │   │   │
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py
│   │   │   │   ├── search.py
│   │   │   │   ├── graph.py
│   │   │   │   ├── documents.py
│   │   │   │   ├── entities.py
│   │   │   │   └── claims.py
│   │   │   │
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── search.py
│   │   │   │   ├── graph.py
│   │   │   │   ├── document.py
│   │   │   │   ├── entity.py
│   │   │   │   └── claim.py
│   │   │   │
│   │   │   └── services/
│   │   │       ├── __init__.py
│   │   │       ├── qdrant_service.py
│   │   │       ├── neo4j_service.py
│   │   │       ├── hybrid_search_service.py
│   │   │       └── citation_service.py
│   │   │
│   │   └── tests/
│   │       ├── test_health.py
│   │       ├── test_search.py
│   │       └── test_graph.py
│   │
│   └── web/
│       ├── README.md
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── index.html
│       ├── public/
│       │   └── favicon.svg
│       │
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── styles/
│           │   ├── globals.css
│           │   └── theme.css
│           │
│           ├── api/
│           │   ├── client.ts
│           │   ├── search.ts
│           │   ├── graph.ts
│           │   ├── documents.ts
│           │   └── entities.ts
│           │
│           ├── components/
│           │   ├── layout/
│           │   │   ├── AppShell.tsx
│           │   │   ├── Sidebar.tsx
│           │   │   └── Header.tsx
│           │   │
│           │   ├── search/
│           │   │   ├── SearchBox.tsx
│           │   │   ├── SearchResultCard.tsx
│           │   │   ├── CitationBadge.tsx
│           │   │   └── FiltersPanel.tsx
│           │   │
│           │   ├── graph/
│           │   │   ├── GraphCanvas.tsx
│           │   │   ├── EntityNodeCard.tsx
│           │   │   └── RelationshipPanel.tsx
│           │   │
│           │   ├── documents/
│           │   │   ├── DocumentViewer.tsx
│           │   │   ├── TranscriptChunk.tsx
│           │   │   └── PageReference.tsx
│           │   │
│           │   └── review/
│           │       ├── ClaimReviewPanel.tsx
│           │       ├── EntityMergePanel.tsx
│           │       └── ExtractionConfidenceBadge.tsx
│           │
│           ├── pages/
│           │   ├── DashboardPage.tsx
│           │   ├── SearchPage.tsx
│           │   ├── GraphPage.tsx
│           │   ├── DocumentPage.tsx
│           │   ├── EntityPage.tsx
│           │   └── ReviewPage.tsx
│           │
│           ├── hooks/
│           │   ├── useSearch.ts
│           │   ├── useGraph.ts
│           │   └── useDocument.ts
│           │
│           ├── types/
│           │   ├── search.ts
│           │   ├── graph.ts
│           │   ├── document.ts
│           │   ├── entity.ts
│           │   └── claim.ts
│           │
│           └── utils/
│               ├── formatters.ts
│               ├── citations.ts
│               └── constants.ts
│
├── packages/
│   │
│   ├── ingestion/
│   │   ├── README.md
│   │   ├── commission_ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   │
│   │   │   ├── discovery/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── zondo.py
│   │   │   │   └── madlanga.py
│   │   │   │
│   │   │   ├── download/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── downloader.py
│   │   │   │   └── registry.py
│   │   │   │
│   │   │   ├── parsing/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── pdf_text.py
│   │   │   │   ├── transcript.py
│   │   │   │   └── speakers.py
│   │   │   │
│   │   │   ├── chunking/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── speaker_chunks.py
│   │   │   │   └── chunk_ids.py
│   │   │   │
│   │   │   ├── extraction/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── entities.py
│   │   │   │   ├── roles.py
│   │   │   │   ├── events.py
│   │   │   │   ├── claims.py
│   │   │   │   └── normalisation.py
│   │   │   │
│   │   │   ├── stores/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── qdrant_store.py
│   │   │   │   ├── neo4j_store.py
│   │   │   │   └── source_store.py
│   │   │   │
│   │   │   └── pipeline/
│   │   │       ├── __init__.py
│   │   │       ├── run.py
│   │   │       ├── steps.py
│   │   │       └── cli.py
│   │   │
│   │   └── tests/
│   │       ├── test_discovery_zondo.py
│   │       ├── test_discovery_madlanga.py
│   │       ├── test_pdf_text.py
│   │       ├── test_speakers.py
│   │       ├── test_chunking.py
│   │       └── test_entity_extraction.py
│   │
│   ├── ontology/
│   │   ├── README.md
│   │   ├── ontology/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── taxonomies.py
│   │   │   ├── validators.py
│   │   │   └── provenance.py
│   │   │
│   │   └── resources/
│   │       ├── shared_taxonomy.yaml
│   │       ├── zondo_taxonomy.yaml
│   │       └── madlanga_taxonomy.yaml
│   │
│   └── shared/
│       ├── README.md
│       ├── shared/
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   ├── hashing.py
│       │   ├── text.py
│       │   ├── dates.py
│       │   └── paths.py
│       │
│       └── tests/
│           ├── test_hashing.py
│           └── test_text.py
│
├── scripts/
│   ├── discover_zondo.py
│   ├── discover_madlanga.py
│   ├── download_sources.py
│   ├── ingest_commission.py
│   ├── reset_neo4j.py
│   ├── seed_taxonomy.py
│   ├── export_graph.py
│   └── smoke_test_search.py
│
├── notebooks/
│   ├── 01_pdf_exploration.ipynb
│   ├── 02_speaker_parsing.ipynb
│   ├── 03_entity_extraction.ipynb
│   ├── 04_qdrant_search.ipynb
│   └── 05_neo4j_queries.ipynb
│
└── tests/
    ├── integration/
    │   ├── test_qdrant_connection.py
    │   ├── test_neo4j_connection.py
    │   └── test_pipeline_small_pdf.py
    │
    └── fixtures/
        ├── sample_transcript_page.txt
        ├── sample_chunk.json
        └── sample_entities.json

Recommended shape

Use this as a monorepo:

apps/
  api/      Python FastAPI backend
  web/      React + Vite frontend
packages/
  ingestion/  PDF discovery, parsing, chunking, extraction
  ontology/   shared ontology, taxonomy and provenance rules
  shared/     utilities used by ingestion and API

This avoids mixing the ingestion pipeline directly into the API. The API should query Qdrant and Neo4j, not own the ingestion logic.

Minimal starting version

To avoid overbuilding on day one, start with this subset:

commission-intelligence-platform/
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── .env.example
│
├── data/
│   ├── raw/
│   │   ├── zondo/
│   │   └── madlanga/
│   ├── processed/
│   └── sources/
│
├── infra/
│   ├── neo4j/
│   │   ├── constraints.cypher
│   │   └── seed_taxonomy.cypher
│   └── qdrant/
│       └── collections.yaml
│
├── packages/
│   ├── ingestion/
│   ├── ontology/
│   └── shared/
│
├── apps/
│   ├── api/
│   └── web/
│
└── scripts/
    ├── ingest_commission.py
    └── smoke_test_search.py

