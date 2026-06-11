# Canonical Ontology

This is the **single source of truth** for the graph schema shared by all commissions.
`README.md` §4–5 and `taxonomy-ontologies.md` are background discussion; where they
differ from this file, **this file wins**.

Governing principle: **Mention ≠ Claim ≠ Finding ≠ Fact.** This is an evidence graph,
not a truth graph. See `decisions/0002-evidence-graph-not-truth-graph.md` (planned).

**Provenance tier:** `authoritative=true` marks official commission PDFs;
`authoritative=false` marks non-authoritative bootstrap sources (e.g. DSFSI plaintext).
Downstream stores and the UI must surface this distinction — bootstrap text is not an
official PDF and carries no page-level provenance.

## 1. Core nodes (all commissions)

| Label | Key / identifying property | Notes |
|---|---|---|
| `:Commission` | `slug` (unique), `name` | e.g. `slug: "zondo"`, `name: "Zondo Commission"` |
| `:HearingDay` | `key` (unique) | `key = "<slug>-day-<day_no>-<date>"`; props `day_no`, `date`, `title`, `source_url` |
| `:Session` | `key` | optional sub-day grouping |
| `:Document` | `sha256` (unique) | props `url`, `filename`, `document_type`, `authoritative`, `downloaded_at` |
| `:Page` | `key` (unique) | `key = "<sha256>:<page_no>"`; prop `page_no` |
| `:Chunk` | `chunk_id` (unique) | props `text`, `page_start`, `page_end`, `speakers` |
| `:Person` | `name` (unique) | prop `aliases` |
| `:Organisation` | `name` (unique) | classified via `HAS_TYPE` |
| `:Place` | `name` (unique) | |
| `:Role` | `name` (unique) | **procedural** role (Witness, Chairperson, Evidence Leader…) |
| `:Position` | `title` (unique) | **real-world** position (CFO, Minister, Board Member…) |
| `:Claim` | `claim_id` (unique) | props `text`, `status`, `attribution`, `confidence`, `extraction_method` |
| `:Event` | `event_id` (unique) | props `event_type`, `summary`, `date_text` |
| `:Matter` | `name` (unique) | named topic/strand (e.g. "Estina dairy", "PKTT") |
| `:Finding` | `finding_id` (unique) | props `text`, `source`, `status` |
| `:Recommendation` | `recommendation_id` (unique) | prop `text` |
| `:ReportVolume` | `name` (unique) | final/interim report volume |

Controlled-vocabulary type nodes (attached, not hardcoded as labels):
`:OrganisationType {name}`, `:DocumentType {name}`, `:EventType {name}`,
`:ClaimStatus {name}`. Vocabularies are listed in `README.md` §5.

## 2. Canonical relationships (settled naming)

Provenance spine — **always `Document → Page → Chunk`**, never a direct
`Document → Chunk`:

```
(:Commission)-[:HAS_HEARING]->(:HearingDay)
(:HearingDay)-[:HAS_DOCUMENT]->(:Document)
(:Document)-[:HAS_PAGE]->(:Page)
(:Page)-[:HAS_CHUNK]->(:Chunk)
```

Entity mentions and speech:

```
(:Person)-[:SPOKE_IN {speaker_label}]->(:Chunk)
(:Person)-[:MENTIONED_IN]->(:Chunk)
(:Organisation)-[:MENTIONED_IN]->(:Chunk)
(:Place)-[:MENTIONED_IN]->(:Chunk)
```

Procedural role vs real-world position — **kept distinct, both shared (not Zondo-only)**:

```
(:Person)-[:HAS_PROCEDURAL_ROLE {commission, source_chunk_id}]->(:Role)
(:Person)-[:HELD_POSITION {date_text, confidence, source_chunk_id}]->(:Position)
(:Position)-[:AT_ORG]->(:Organisation)
```

Claims and events (the interpreted layer — always provenance-backed):

```
(:Claim)-[:STATED_BY]->(:Person)
(:Claim)-[:SUPPORTED_BY]->(:Chunk)
(:Claim)-[:MENTIONS]->(:Person|:Organisation|:Place)
(:Event)-[:EVIDENCED_BY]->(:Chunk)
(:Event)-[:INVOLVES_PERSON]->(:Person)
(:Event)-[:OCCURRED_AT]->(:Place)
```

Findings layer (reports):

```
(:Finding)-[:REFERS_TO]->(:Person)
(:Finding)-[:SUPPORTED_BY]->(:Chunk)
(:Finding)-[:MADE_IN]->(:ReportVolume)
(:Recommendation)-[:AROSE_FROM]->(:Finding)
```

Classification edges:

```
(:Organisation)-[:HAS_TYPE]->(:OrganisationType)
(:Document)-[:HAS_TYPE]->(:DocumentType)
(:Event)-[:HAS_TYPE]->(:EventType)
(:Claim)-[:HAS_STATUS]->(:ClaimStatus)
```

### Banned relationships
- **`APPEARS_IN`** — do not use; use `MENTIONED_IN` (entity) or `SPOKE_IN` (speaker).
- **Asserted fact edges** such as `(:Person)-[:CORRUPTLY_INFLUENCED]->(:Contract)`.
  Model the assertion as a `:Claim` or `:Finding` with provenance instead.

## 3. Commission taxonomy overlays

The structure above is stable across commissions. Domain vocabulary is layered on via
`HAS_TYPE` edges and a small set of overlay nodes/relationships, supplied by each
**commission adapter** (see `build-plan-shared-core.md` §3).

**Zondo overlay** (state capture / procurement):
```
(:Contract)-[:INVOLVED_ORG]->(:Organisation)
(:Contract)-[:MENTIONED_IN]->(:Chunk)
(:Amount)-[:RELATES_TO]->(:Contract)
(:EvidenceBundle)-[:CONTAINS]->(:Document)
```
Overlay nodes: `:StateEntity`, `:Company`, `:Contract`, `:Amount`, `:EvidenceBundle`,
`:ReportVolume`. Org types: `StateOwnedEntity`, `GovernmentDepartment`, `PrivateCompany`,
`Regulator`, `FinancialInstitution`.

**Madlanga overlay** (criminal justice):
Overlay node types via `HAS_TYPE`: `LawEnforcementAgency`, `ProsecutingAuthority`,
`IntelligenceAgency`, `JudicialInstitution`, `CorrectionalService`, `InvestigationUnit`,
`CriminalSyndicate`. Matters: case dockets, investigations, prosecutions, threats,
interference. Events: `Threat`, `Assassination`, `Investigation`, `ProsecutionDecision`.

## 4. Provenance requirement

Every `:Person`/`:Organisation`/`:Place` mention, `:Claim`, `:Event` and `:Finding`
must be traceable to: commission, hearing day, document (SHA256), source URL, page,
chunk ID, evidence text, extraction method and confidence. Relationships in the
interpreted layer carry `confidence` and `source_chunk_id`. See `data-provenance.md`
(planned) and `README.md` §16.
