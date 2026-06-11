# Build Plan — Madlanga Adapter

Madlanga is a **commission adapter** over the shared core. Read
[`build-plan-shared-core.md`](build-plan-shared-core.md) first — it owns the pipeline,
stores, ontology, Qdrant model and Neo4j model. This file contains **only** the
Madlanga-specific deltas that populate the `CommissionAdapter` interface
(`build-plan-shared-core.md` §3).

## Commission

The **Judicial Commission of Inquiry into alleged criminality, political interference and
corruption in the criminal justice system** (Justice Mbuyiseli Madlanga). Mandate:
criminal-syndicate infiltration of law enforcement, intelligence, prosecution
authorities, judiciary and correctional services. Records published as one PDF per
hearing day (e.g. `MADLANGA_COMMISSION_RECORD_…`, Day 59 ≈ 170 pages).

```python
slug = "madlanga"
name = "Madlanga Commission"
supported_source_types = ["transcript"]      # statements/notices later
ingestion_phases = ["transcripts"]            # Phase 1 only for now
```

## 1. Discovery (`discover_sources`)

- Base URL: `https://criminaljusticecommission.org.za`
- Start pages: `/`, `/hearing.php`, `/media.php`, `/index.php?page=1..9`
- The hearings page has **anti-bot verification**, so use a two-layer strategy:
  1. try `requests`, 2. **fall back to Playwright** (`networkidle`), 3. also scan known
  `/uploads/` PDF links.
- Link/title match pattern: `(MADLANGA.*RECORD|COMMISSION.*RECORD|DAY\s*\d+|\.pdf)`,
  restricted to the commission host.
- Emit `SourceRecord`s (`source_type="transcript"`, `document_type="Transcript"`).
  **Upgrade note:** the original draft returned bare URL strings — it must now return the
  shared `SourceRecord` shape (`build-plan-shared-core.md` §4).

## 2. Day/date parsing (`parse_day_metadata`)

Madlanga headers put the **date before** the day number:

```python
DAY_RE = re.compile(r"(\d{1,2}\s+[A-Z]+\s+20\d{2})\s*[–-]\s*DAY\s*(\d+)", re.I)
# group(1) -> date_text (title-cased), group(2) -> day_no
```

## 3. Speaker regex (`speaker_regex`)

Labels are uppercase `LABEL:` lines. Base pattern:

```python
SPEAKER_RE = re.compile(r"^([A-Z][A-Z .'\-()]+):\s*(.*)$")
```

## 4. Role hints (`role_hint_map`)

Maps speaker-label tokens → **procedural** `:Role` (note the military ranks specific to
policing/justice testimony):

```python
ROLE_HINTS = {
    "CHAIRPERSON": "Commissioner", "COMMISSIONER": "Commissioner",
    "ADV": "Evidence Leader", "SC": "Senior Counsel",
    "MS": "Person", "MR": "Person", "DR": "Person",
    "LT GEN": "Witness", "GENERAL": "Witness",
}
```

These feed `HAS_PROCEDURAL_ROLE` only. Real-world positions (e.g. a general's command
posting) go through the shared `HELD_POSITION → Position → AT_ORG` path.

## 5. Taxonomy overlay (`taxonomy_overlay`)

Criminal-justice domain. Organisation types via `HAS_TYPE`: `LawEnforcementAgency`,
`ProsecutingAuthority`, `IntelligenceAgency`, `JudicialInstitution`,
`CorrectionalService`, `InvestigationUnit`, `CriminalSyndicate`, `OversightBody` (IPID).
Common institutions: SAPS, IPID, NPA, Crime Intelligence, Hawks, Correctional Services,
judiciary. Matters: case dockets, investigations, prosecutions, witness intimidation,
political interference, law-enforcement appointments. Salient `EventType`s: `Threat`,
`Assassination`, `Investigation`, `ProsecutionDecision`, `Complaint`.

Example graph questions: *Who interfered in which investigation? Which official was
linked to which syndicate? Which case docket was mentioned? Which witness described
threats? Which prosecution decision was questioned?*

## 6. Ingestion phases

- **Phase 1 (now):** transcripts → pipeline as in shared core §5.
- **Later:** statements/notices from the site's Media/Notices sections as additional
  `source_type`s; extend `supported_source_types` and `ingestion_phases` then.

## Notes / cautions specific to Madlanga
- Ongoing/recent commission — re-run discovery periodically; rely on the source registry
  to avoid re-downloading.
- Some PDFs may be scanned images; add OCR only if PyMuPDF text extraction comes back
  empty for a document.
