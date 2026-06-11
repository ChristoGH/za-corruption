# commission-ingestion

Source discovery, registry, and download for commission transcript PDFs and bootstrap text.

**Operational guide:** see [docs/getting-started.md](../../docs/getting-started.md) at repo root.

## Package layout

- `commission_ingestion/discovery/` — `MadlangaDiscoveryAdapter`, `ZondoDiscoveryAdapter`, `ZondoBootstrapDiscoveryAdapter`
- `commission_ingestion/download/` — `SourceRegistry`, `download_source`
- `commission_ingestion/models/` — `SourceRecord` (schema 1.1)
- `commission_ingestion/cli/` — `retrieve-sources` entrypoint

## Development

From repo root (uv workspace):

```bash
uv sync --all-packages --all-extras
uv run pytest packages/ingestion/tests -v
```
