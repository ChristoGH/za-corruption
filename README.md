Commission Transcript Intelligence Platform

A reproducible ingestion and intelligence pipeline for South African commission transcripts, starting with the Zondo Commission and extendable to the Madlanga Commission and other public commissions of inquiry.

The system downloads publicly available transcript PDFs, extracts and chunks the text, stores semantically searchable transcript passages in Qdrant, and builds an evidence-aware knowledge graph in Neo4j containing people, organisations, places, roles, hearings, documents, claims, events, findings and recommendations.

The main design principle is:

Mention ≠ Claim ≠ Finding ≠ Fact

This project treats commission records as an evidence graph, not a truth graph.

⸻

Quick start (source retrieval)

Milestone 1 (discover + download) is implemented. See [docs/getting-started.md](docs/getting-started.md) for full commands.

```bash
uv sync --all-packages --all-extras
uv run retrieve-sources --commission madlanga --discover-only
uv run retrieve-sources --commission zondo --discover-only          # DSFSI bootstrap (default)
uv run retrieve-sources --commission both --download
make test
```

Outputs: `data/sources/source_registry.jsonl` and `data/raw/{zondo,madlanga}/`.

⸻

1. Project Goals

This project aims to:

* Download official commission transcript PDFs.
* Preserve document-level provenance: source URL, filename, SHA256 hash, page numbers and hearing day.
* Extract transcript text from PDFs.
* Segment transcripts into speaker-aware chunks.
* Store chunks in Qdrant for semantic search and retrieval-augmented generation.
* Extract people, organisations, places, roles, events and claims.
* Store structured entities and relationships in Neo4j.
* Preserve source evidence for every extracted entity, claim and event.
* Support multiple commissions using a shared ontology and commission-specific taxonomies.

Initial supported commissions:

* Zondo / State Capture Commission
* Madlanga Commission

⸻

2. Architecture

Official commission website
        ↓
PDF discovery
        ↓
PDF download
        ↓
PDF text extraction
        ↓
Transcript parsing
        ↓
Speaker-aware chunking
        ↓
Entity / role / event / claim extraction
        ↓
 ┌────────────────────┐      ┌────────────────────┐
 │ Qdrant vector DB   │      │ Neo4j graph DB      │
 │ Semantic search    │      │ Evidence graph      │
 └────────────────────┘      └────────────────────┘

Qdrant is used for questions such as:

“Find testimony mentioning threats against investigators.”

Neo4j is used for questions such as:

“Which witnesses mentioned IPID, SAPS, a specific place and a specific person in the same hearing day?”

⸻

3. Core Design Principle

Commission transcripts contain allegations, questions, answers, denials, findings and recommendations. These must not be collapsed into one undifferentiated fact layer.

The graph separates:

Raw source text
Extracted mentions
Claims made in testimony
Commission findings
Recommendations
External confirmations or later legal findings

For example:

A witness said X happened.

should be represented as a claim:

(:Claim {
  text: "...",
  status: "Testified",
  attribution: "Witness testimony"
})-[:SUPPORTED_BY]->(:Chunk)

not as an unconditional fact.

⸻

4. Shared Ontology

The same high-level ontology is used across commissions.

Core Nodes

(:Commission)
(:HearingDay)
(:Session)
(:Document)
(:Transcript)
(:Page)
(:Chunk)
(:Person)
(:Organisation)
(:Place)
(:Role)
(:Position)
(:Claim)
(:Event)
(:Matter)
(:EvidenceItem)
(:Finding)
(:Recommendation)

Core Relationships

(:Commission)-[:HAS_HEARING]->(:HearingDay)
(:HearingDay)-[:HAS_DOCUMENT]->(:Document)
(:Document)-[:HAS_PAGE]->(:Page)
(:Page)-[:HAS_CHUNK]->(:Chunk)
(:Person)-[:SPOKE_IN]->(:Chunk)
(:Person)-[:MENTIONED_IN]->(:Chunk)
(:Organisation)-[:MENTIONED_IN]->(:Chunk)
(:Place)-[:MENTIONED_IN]->(:Chunk)
(:Claim)-[:SUPPORTED_BY]->(:Chunk)
(:Claim)-[:STATED_BY]->(:Person)
(:Event)-[:EVIDENCED_BY]->(:Chunk)
(:Person)-[:HAS_PROCEDURAL_ROLE]->(:Role)
(:Person)-[:HELD_POSITION]->(:Position)
(:Position)-[:AT_ORG]->(:Organisation)

⸻

5. Shared Taxonomy

The project uses controlled vocabularies for roles, document types, event types and claim statuses.

PersonRole

Commissioner
Chairperson
EvidenceLeader
Witness
LegalRepresentative
Investigator
AccusedPerson
MentionedPerson
PublicOfficial
PoliticalOfficeBearer
Executive
BoardMember
Whistleblower
Journalist
ExpertWitness

OrganisationType

Commission
StateOwnedEntity
GovernmentDepartment
LawEnforcementAgency
ProsecutingAuthority
IntelligenceAgency
JudicialInstitution
CorrectionalService
PrivateCompany
PoliticalParty
Regulator
OversightBody
FinancialInstitution
MediaOrganisation
CivilSocietyOrganisation

DocumentType

Transcript
WitnessStatement
Affidavit
Annexure
EvidenceBundle
Report
FinalReport
InterimReport
Notice
Ruling
Correspondence
Contract
Invoice
BankRecord
Presentation
MeetingMinutes

EventType

Hearing
Testimony
CrossExamination
Meeting
Appointment
Dismissal
ProcurementDecision
ContractAward
Payment
Instruction
Threat
Assassination
Investigation
ProsecutionDecision
Arrest
Complaint
ReportPublication
Recommendation

ClaimStatus

Mentioned
Alleged
Testified
Denied
Admitted
Disputed
Corroborated
CommissionFinding
CourtFinding
Unverified

⸻

6. Commission-Specific Taxonomies

The core ontology remains stable, while each commission gets an additional domain taxonomy.

Zondo Commission

The Zondo Commission focuses heavily on state capture, procurement, political influence, state-owned entities, contracts and public finance.

Useful domain classes include:

StateOwnedEntity
GovernmentDepartment
PrivateCompany
PoliticalOffice
BoardPosition
ExecutivePosition
Contract
Tender
Payment
Donation
Meeting
Instruction
Appointment
ProcurementProcess
IrregularExpenditure
ReportVolume
Finding
Recommendation

Common matters may include:

Eskom
Transnet
Denel
SAA
Prasa
Bosasa
Gupta family
Free State asbestos
Estina dairy
McKinsey
Trillian
SSA
Parliamentary oversight

Madlanga Commission

The Madlanga Commission is more focused on criminal justice, policing, syndicates, interference, investigations and prosecutions.

Useful domain classes include:

LawEnforcementAgency
ProsecutingAuthority
IntelligenceAgency
JudicialInstitution
CorrectionalService
InvestigationUnit
CriminalSyndicate
CaseDocket
Investigation
Prosecution
Threat
Assassination
PoliticalInterference
OperationalInterference
CorruptionAllegation
CriminalMatter
ProtectedDisclosure
SecurityIncident

Common matters may include:

SAPS
IPID
NPA
Crime Intelligence
Hawks
Correctional Services
Judiciary
case dockets
witness intimidation
criminal syndicates
political interference
law-enforcement appointments

⸻

7. Repository Structure

commission-intelligence-platform/
  README.md
  pyproject.toml          # uv workspace root
  uv.lock
  docker-compose.yml      # retrieval-only ingestion service
  Makefile
  .env.example
  data/
    sources/              # source_registry.jsonl (tracked)
    raw/zondo/            # downloads (gitignored)
    raw/madlanga/
  packages/
    ingestion/
      commission_ingestion/
        discovery/        # zondo, zondo_bootstrap, madlanga adapters
        download/
        models/
        cli/
      tests/
  scripts/
    retrieve_sources.py
  docs/
    getting-started.md
    ontology.md
    build-plan-shared-core.md

⸻

8. Services

The project uses:

* Qdrant for vector search
* Neo4j for graph storage
* Python for ingestion and extraction

docker-compose.yml

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
  neo4j:
    image: neo4j:5.26
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/password123
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
volumes:
  qdrant_storage:
  neo4j_data:
  neo4j_logs:

Start services:

docker compose up -d

Neo4j browser:

http://localhost:7474

Qdrant dashboard/API:

http://localhost:6333

⸻

9. Installation

Python 3.12+ (managed via `.python-version`). Use uv from the repo root:

```bash
uv sync --all-packages --all-extras
uv run playwright install chromium   # optional; for Zondo manual-session harvest
make test
```

For source retrieval only, see [docs/getting-started.md](docs/getting-started.md).

Future ingestion stages (spaCy, Qdrant, Neo4j) are not required yet.

⸻

10. Environment Variables

Create a .env file from .env.example.

cp .env.example .env

Example:

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=commission_transcripts
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

⸻

11. Ingestion Pipeline

The pipeline consists of the following stages:

discover
download
parse
chunk
extract
store in Qdrant
store in Neo4j

Run Zondo ingestion:

python -m src.ingestion.pipeline --commission zondo

Run Madlanga ingestion:

python -m src.ingestion.pipeline --commission madlanga

Run a dry run:

python -m src.ingestion.pipeline --commission zondo --dry-run

Process a single PDF:

python -m src.ingestion.pipeline \
  --commission zondo \
  --url "https://example.com/transcript.pdf"

⸻

12. Qdrant Payload Design

Each transcript chunk stored in Qdrant should include metadata.

{
  "chunk_id": "sha256-hash",
  "text": "CHAIRPERSON: ...",
  "commission": "Zondo Commission",
  "day_no": 327,
  "date_text": "2021-01-13",
  "source_url": "https://...",
  "filename": "Day_327_-_2021-01-13.pdf",
  "sha256": "...",
  "page_start": 12,
  "page_end": 14,
  "speakers": ["CHAIRPERSON", "ADV SELEKA SC"]
}

⸻

13. Neo4j Constraints

Run the constraints before ingestion.

CREATE CONSTRAINT commission_name IF NOT EXISTS
FOR (c:Commission) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT hearing_day_key IF NOT EXISTS
FOR (h:HearingDay) REQUIRE h.key IS UNIQUE;
CREATE CONSTRAINT document_sha IF NOT EXISTS
FOR (d:Document) REQUIRE d.sha256 IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;
CREATE CONSTRAINT person_name IF NOT EXISTS
FOR (p:Person) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT organisation_name IF NOT EXISTS
FOR (o:Organisation) REQUIRE o.name IS UNIQUE;
CREATE CONSTRAINT place_name IF NOT EXISTS
FOR (p:Place) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT role_name IF NOT EXISTS
FOR (r:Role) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT position_title IF NOT EXISTS
FOR (p:Position) REQUIRE p.title IS UNIQUE;
CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (e:Event) REQUIRE e.event_id IS UNIQUE;

⸻

14. Example Neo4j Queries

Find people mentioned with IPID:

MATCH (p:Person)-[:MENTIONED_IN]->(c:Chunk)<-[:MENTIONED_IN]-(o:Organisation)
WHERE toLower(o.name) CONTAINS "ipid"
RETURN p.name, count(c) AS mentions
ORDER BY mentions DESC
LIMIT 25;

Find speakers and their procedural roles:

MATCH (p:Person)-[:HAS_PROCEDURAL_ROLE]->(r:Role)
RETURN r.name AS role, collect(DISTINCT p.name) AS people
ORDER BY role;

Find places mentioned on a hearing day:

MATCH (h:HearingDay)-[:HAS_DOCUMENT]->(:Document)-[:HAS_CHUNK]->(c:Chunk)
MATCH (place:Place)-[:MENTIONED_IN]->(c)
WHERE h.day_no = 327
RETURN place.name, count(*) AS mentions
ORDER BY mentions DESC;

Find chunks where a person and place co-occur:

MATCH (person:Person {name: "Anoj Singh"})-[:MENTIONED_IN]->(c:Chunk)
MATCH (place:Place)-[:MENTIONED_IN]->(c)
RETURN place.name, c.page_start, c.page_end, left(c.text, 500) AS evidence
ORDER BY c.page_start;

Find claims supported by transcript chunks:

MATCH (claim:Claim)-[:SUPPORTED_BY]->(chunk:Chunk)
OPTIONAL MATCH (claim)-[:STATED_BY]->(person:Person)
RETURN claim.text, claim.status, person.name, chunk.page_start, chunk.page_end
LIMIT 25;

⸻

15. Example Semantic Search

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
client = QdrantClient(url="http://localhost:6333")
model = SentenceTransformer("BAAI/bge-small-en-v1.5")
query = "testimony about threats against investigators near Springs"
vector = model.encode(query, normalize_embeddings=True).tolist()
hits = client.search(
    collection_name="commission_transcripts",
    query_vector=vector,
    limit=10,
)
for hit in hits:
    print(hit.score)
    print(hit.payload["commission"])
    print(hit.payload["filename"], hit.payload["page_start"], hit.payload["page_end"])
    print(hit.payload["text"][:700])
    print("---")

⸻

16. Data Provenance

Every extracted entity, claim or event should be traceable to:

Commission
Hearing day
Document
Source URL
PDF hash
Page number
Chunk ID
Text evidence
Extraction method
Extraction confidence

This is essential for legal, investigative and journalistic use.

⸻

17. Extraction Strategy

The project uses progressive extraction.

Phase 1: Deterministic extraction

* PDF metadata
* Hearing day
* Date
* Page numbers
* Speaker labels
* Chunk IDs
* Source URLs
* SHA256 hashes

Phase 2: NLP extraction

* People
* Organisations
* Places
* Named entities
* Basic role inference

Phase 3: LLM-assisted extraction

* Events
* Claims
* Allegations
* Procedural roles
* Real-world positions
* Relationships between people and organisations
* Evidence references

Phase 4: Human review

* Merge duplicate people
* Resolve aliases
* Confirm high-risk claims
* Validate important graph relationships

⸻

18. Human Review Requirements

The following should not be treated as final without review:

* Allegations of criminal conduct
* Relationships implying corruption
* Identification of suspects
* Claims involving named private persons
* Events involving threats, assassinations or interference
* Commission findings linked to individuals
* Recommendations for prosecution or investigation

These should be stored with provenance and status fields.

⸻

19. Suggested MVP

The first working milestone is:

Download official Zondo transcript PDFs
Extract transcript text
Chunk by speaker turn
Store chunks in Qdrant
Extract Person / Organisation / Place mentions
Store mentions in Neo4j
Run semantic search and graph queries

The MVP is complete when the system can:

1. Search semantically for a topic in Qdrant.
2. Retrieve the relevant transcript passage.
3. Show the hearing day, PDF, page number and source URL.
4. Traverse from that chunk to people, organisations and places in Neo4j.
5. Distinguish a mere mention from a claim or finding.

⸻

20. Development Roadmap

Milestone 1: Source Discovery

* Zondo transcript discovery
* Madlanga transcript discovery
* URL deduplication
* Source metadata table

Milestone 2: Download and Parse

* PDF download
* SHA256 hashing
* Text extraction
* Page-level metadata

Milestone 3: Transcript Chunking

* Speaker detection
* Speaker-turn extraction
* Chunking with page provenance
* Stable chunk IDs

Milestone 4: Qdrant Ingestion

* Embedding generation
* Collection creation
* Payload design
* Semantic search test

Milestone 5: Neo4j Ingestion

* Constraints
* Commission, HearingDay, Document and Chunk nodes
* Person, Organisation and Place mentions
* Role nodes

Milestone 6: Claims and Events

* Claim extraction
* Event extraction
* Claim status taxonomy
* Evidence-backed event graph

Milestone 7: Review Interface

* Duplicate entity resolution
* Entity merge suggestions
* Claim review
* Graph correction workflow

Milestone 8: RAG Interface

* Search over transcripts
* Evidence-backed answer generation
* Citation to hearing day, page and document
* Hybrid vector + graph retrieval

⸻

21. Safety and Legal Notes

This project processes public commission records, but the content may include serious allegations, private individuals, contested testimony and legally sensitive claims.

The system should:

* Preserve original source evidence.
* Avoid presenting testimony as proven fact.
* Distinguish allegations, denials, admissions, findings and recommendations.
* Cite source transcript passages.
* Keep confidence scores and extraction method metadata.
* Allow human review before publication or operational use.

⸻

22. Example Use Cases

Research

Show all testimony mentioning a particular person, organisation or place.

Investigative Analysis

Find all people who were mentioned in relation to a specific contract, payment or investigation.

Legal Research

Distinguish between allegations made in testimony and findings made in final reports.

Knowledge Graph Exploration

Show connections between witnesses, organisations, contracts, places and events.

RAG Search

Answer questions using only transcript passages and cite the source hearing day and page.

⸻

23. Current Status

**Implemented:** source discovery + download (Milestone 1)
- Madlanga: ~108 transcript PDFs from `hearing.php` embedded JSON
- Zondo bootstrap: DSFSI plaintext transcripts (`authoritative=false`, CC-BY-SA-4.0)
- Registry: `data/sources/source_registry.jsonl`
- CLI: `uv run retrieve-sources`

**Blocked / unverified:** Zondo official PDFs (Cloudflare; manual session required)

**Planned next:** PDF/text parsing, speaker chunking, Qdrant, Neo4j, claims extraction, review UI, RAG.

⸻

24. License

Choose a license before publication.

Recommended options:

* MIT License for open-source code.
* Apache 2.0 if patent protection matters.
* Private repository if the project will become commercial or investigative infrastructure.

The original transcript PDFs remain the property of their respective official sources.

⸻

25. Disclaimer

This project is for research, analysis and information retrieval. It does not determine legal truth. Extracted claims, events and relationships are machine-generated unless reviewed and confirmed. Always refer back to the original official transcript and commission records.