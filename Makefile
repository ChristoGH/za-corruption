.PHONY: install test browsers retrieve-discover retrieve-download docker-build docker-discover stores-up neo4j-constraints load-qdrant build-graph post-assets backup restore api-dev web-install web-dev web-build

COMMISSION ?= madlanga
ZONDO_SOURCE ?= bootstrap
# Docker named volume holding the Neo4j data (compose prefixes the project/dir name).
# Override if your compose project name differs:  make backup NEO4J_VOLUME=<name>_neo4j_data
NEO4J_VOLUME ?= za-corruption_neo4j_data

install:
	uv sync --all-packages --all-extras

test:
	uv run pytest packages/ingestion/tests apps/api/tests -v

browsers:
	uv run playwright install chromium

retrieve-discover:
	uv run retrieve-sources --commission $(COMMISSION) --zondo-source $(ZONDO_SOURCE) --discover-only

retrieve-download:
	uv run retrieve-sources --commission $(COMMISSION) --zondo-source $(ZONDO_SOURCE) --download

stores-up:
	docker compose up -d qdrant neo4j

# ── M5 public surface (apps/api + apps/web) ──────────────────────────────────
api-dev: stores-up
	uv run uvicorn app.main:app --reload --app-dir apps/api

web-install:
	npm --prefix apps/web install

web-dev:
	npm --prefix apps/web run dev

web-build:
	npm --prefix apps/web run build

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

# Snapshot the Neo4j graph to backups/<timestamp>/neo4j.dump (stops neo4j briefly for a
# consistent dump, then restarts it). Community edition can't dump online, hence the stop.
backup:
	@ts=$$(date +%Y%m%d-%H%M%S); mkdir -p backups/$$ts; \
	echo "stopping neo4j for a consistent dump…"; docker compose stop neo4j; \
	docker run --rm -v $(NEO4J_VOLUME):/data -v "$$(pwd)/backups/$$ts":/backup \
	  neo4j:5.26-community neo4j-admin database dump neo4j --to-path=/backup; rc=$$?; \
	echo "restarting neo4j…"; docker compose start neo4j; \
	if [ $$rc -eq 0 ]; then echo "✓ backup → backups/$$ts/neo4j.dump"; \
	else echo "⚠ dump failed (rc=$$rc); neo4j restarted — check output above"; fi

# Restore the graph from a dump dir. OVERWRITES the live graph.
#   make restore FROM=backups/20260619-204500
restore:
	@test -n "$(FROM)" || { echo "usage: make restore FROM=backups/<timestamp>"; exit 1; }
	@echo "⚠ this OVERWRITES the live graph with $(FROM)/neo4j.dump"
	docker compose stop neo4j
	-docker run --rm -v $(NEO4J_VOLUME):/data -v "$$(pwd)/$(FROM)":/backup \
	  neo4j:5.26-community neo4j-admin database load neo4j --from-path=/backup --overwrite-destination=true
	docker compose start neo4j
	@echo "✓ restored from $(FROM)"
