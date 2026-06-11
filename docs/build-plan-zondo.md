# Build Plan — Zondo Adapter

Zondo is a **commission adapter** over the shared core. Read
[`build-plan-shared-core.md`](build-plan-shared-core.md) first — it owns the pipeline,
stores, ontology, Qdrant model and Neo4j model. This file contains **only** the
Zondo-specific deltas that populate the `CommissionAdapter` interface
(`build-plan-shared-core.md` §3).

**Zondo is the recommended first build target** — a mature, complete archive with
consistent speaker structure, rich supporting documents and high-value named entities. A
sample (Day 327, 13 Jan 2021, 167 pages) covers Anoj Singh / Eskom / Transnet / McKinsey
/ Trillian / Tegeta / Optimum with named amounts, contracts and affidavits.

## Commission

The **Judicial Commission of Inquiry into Allegations of State Capture** (Zondo). Heavy
on state capture, procurement, SOEs, political influence, contracts and public finance.

```python
slug = "zondo"
name = "Zondo Commission"
supported_source_types = ["transcript", "statement", "report"]
ingestion_phases = ["transcripts", "supporting_documents", "reports_findings"]
```

## 1. Discovery (`discover_sources`)

- Base URL: `https://www.statecapture.org.za`; transcripts at `/site/transcripts`.
- Easier than Madlanga — the transcripts page exposes many direct PDF links; plain
  `requests` is usually enough (Playwright fallback available from the shared helper but
  rarely needed).
- Day/date often appears **around** the link, not inside it; parse from nearby headings:
  ```python
  DAY_RE = re.compile(r"Day\s+(\d+)\s*[-–]\s*(\d{4}-\d{2}-\d{2})", re.I)
  ```
- Emit `SourceRecord`s (`source_type="transcript"`, `document_type="Transcript"`). This
  adapter already returns structured records — keep that shape
  (`build-plan-shared-core.md` §4); persist to the registry to handle the site's
  duplicates.

## 2. Day/date parsing (`parse_day_metadata`)

Zondo headers put the **day number before** the ISO date — the inverse of Madlanga:

```python
# "Day 327 - 2021-01-13"  ->  day_no=327, date="2021-01-13"
```

## 3. Speaker regex (`speaker_regex`)

The format is highly regular (line numbers + `LABEL:`), so a more aggressive,
explicitly-enumerated pattern works well:

```python
SPEAKER_RE = re.compile(
    r"^(CHAIRPERSON|ADV [A-Z .'-]+(?: SC)?|MR [A-Z .'-]+|MS [A-Z .'-]+"
    r"|DR [A-Z .'-]+|PROF [A-Z .'-]+|WITNESS):\s*(.*)$"
)
```

Add a **second pass** for witness identification, since witnesses aren't always labelled
`WITNESS:` — detect headings like `EXAMINATION BY ADV …`, `CROSS-EXAMINATION BY …`, and
bare names (`MR ANOJ SINGH`, `ANOJ SINGH:`).

## 4. Role hints (`role_hint_map`)

Maps speaker-label tokens → **procedural** `:Role`:

```python
ROLE_HINTS = {
    "CHAIRPERSON": "Commissioner", "COMMISSIONER": "Commissioner",
    "ADV": "Evidence Leader", "SC": "Senior Counsel",
    "MR": "Person", "MS": "Person", "DR": "Person", "PROF": "Expert Witness",
    "WITNESS": "Witness",
}
```

**Real-world positions are first-class for Zondo.** Procedural role (Witness) must not be
collapsed with real-world position (CFO of Eskom). Use the shared distinction
(`ontology.md` §2):

```
(:Person {name:"Anoj Singh"})-[:HELD_POSITION {from_text:"former CFO of Eskom"}]
    ->(:Position {title:"Chief Financial Officer"})-[:AT_ORG]->(:Organisation {name:"Eskom"})
```

This lets one person be CFO at Transnet, CFO at Eskom, a witness, a mentioned person, and
the subject of a finding — without collapsing into one vague role.

## 5. Taxonomy overlay (`taxonomy_overlay`)

State-capture domain. Overlay nodes (`ontology.md` §3): `:StateEntity`, `:Company`,
`:Contract`, `:Amount`, `:EvidenceBundle`, `:ReportVolume`. Overlay relationships:
`(:Contract)-[:INVOLVED_ORG]->(:Organisation)`, `(:Contract)-[:MENTIONED_IN]->(:Chunk)`,
`(:Amount)-[:RELATES_TO]->(:Contract)`, `(:EvidenceBundle)-[:CONTAINS]->(:Document)`.
Organisation types: `StateOwnedEntity`, `GovernmentDepartment`, `PrivateCompany`,
`Regulator`, `FinancialInstitution`. Common matters: Eskom, Transnet, Denel, SAA, Prasa,
Bosasa, Gupta family, Free State asbestos, Estina dairy, McKinsey/Trillian, SSA.

Example graph questions: *Who held what position at which SOE? Who influenced which
appointment? Which contract involved which company? Which payment was linked to which
entity? Which finding was made against which person?*

## 6. Ingestion phases

- **Phase 1:** transcripts → pipeline as in shared core §5.
- **Phase 2:** the official **Statements and Documents** section (witness bundles,
  affidavits, annexures, correspondence) grouped by day → `:EvidenceBundle`,
  `:WitnessStatement`, `:Annexure`, `:Correspondence`, `:Contract`, `:Affidavit`.
- **Phase 3:** final/interim **reports and findings** (presidency/government sources) as a
  separate findings layer: `(:Finding)-[:MADE_IN]->(:ReportVolume)`,
  `(:Finding)-[:REFERS_TO]->(:Person)`, linked back to transcript chunks where possible.

## Notes / cautions specific to Zondo
- High duplicate risk in the documents section — dedupe on `sha256` via the registry.
- An existing public GitHub project has plaintext Day 1–399 transcripts; usable as a
  bootstrap/cross-check, but treat the official PDFs as authoritative.
- Evidence graph, not truth graph: a witness saying X is a `:Claim`/`TESTIFIED`-status
  edge, the Commission concluding X is a `:Finding`, a later court outcome is a separate
  status — never overwrite one with another.
