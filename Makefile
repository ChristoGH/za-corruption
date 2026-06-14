.PHONY: install test browsers retrieve-discover retrieve-download docker-build docker-discover stores-up neo4j-constraints load-qdrant build-graph post-assets

COMMISSION ?= madlanga
ZONDO_SOURCE ?= bootstrap

install:
	uv sync --all-packages --all-extras

test:
	uv run pytest packages/ingestion/tests -v

browsers:
	uv run playwright install chromium

retrieve-discover:
	uv run retrieve-sources --commission $(COMMISSION) --zondo-source $(ZONDO_SOURCE) --discover-only

retrieve-download:
	uv run retrieve-sources --commission $(COMMISSION) --zondo-source $(ZONDO_SOURCE) --download

stores-up:
	docker compose up -d qdrant neo4j

neo4j-constraints:
	docker compose exec -T neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-changeme}" < infra/neo4j/constraints.cypher

load-qdrant:
	uv run load-qdrant --commission $(COMMISSION)

build-graph:
	uv run build-graph --commission $(COMMISSION)

build-graph-dry:
	uv run build-graph --commission $(COMMISSION) --dry-run

post-assets:
	uv run corpus-stats --commission $(COMMISSION) --charts --out assets/post1/

docker-build:
	docker compose build ingestion

docker-discover:
	docker compose run --rm ingestion --commission $(COMMISSION) --zondo-source $(ZONDO_SOURCE) --discover-only
