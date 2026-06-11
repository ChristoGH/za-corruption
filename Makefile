.PHONY: install test browsers retrieve-discover retrieve-download docker-build docker-discover

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

docker-build:
	docker compose build ingestion

docker-discover:
	docker compose run --rm ingestion --commission $(COMMISSION) --zondo-source $(ZONDO_SOURCE) --discover-only
