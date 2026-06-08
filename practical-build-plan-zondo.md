Yes — the Zondo / State Capture Commission transcripts are actually a very good target for the same system, and in some ways they are easier and richer than the Madlanga Commission data.

Finding

The official State Capture Commission site has a dedicated Transcripts page with downloadable transcript PDFs by hearing day. The page lists many transcript entries in the form “Day X - YYYY-MM-DD”, with file sizes typically around 0.3 MB to 1.3 MB for many days. For example, the official transcript page lists Day 399 through Day 423 and many earlier/later days with direct download links.  ￼

A sample official transcript, Day 327 - 13 January 2021, is a 167-page PDF. It contains structured proceedings metadata: commission name, venue, date, day number, transcription provider, certificate of veracity, and then detailed verbatim proceedings with speaker labels such as CHAIRPERSON:, ADV SELEKA SC:, and ADV VAN DEN HEEVER:.  ￼

The site also has a separate Statements and Documents section, which is very important for your Neo4j idea. It groups evidentiary documents by day and includes large witness bundles, correspondence, statements and annexures. For example, Day 428 contains several Ramaphosa-related document bundles, and other days list witness-specific files such as De Wee, Mhlongo, Nair, Makwetla, Gigaba, Govender and Pule.  ￼

There is also an existing public GitHub project that extracted plaintext versions of the published transcripts from the official State Capture site. It describes a dataset containing individual text files by day and a combined ZIP for transcripts Day 1–399. That could be useful as a bootstrap or cross-check, but I would still treat the official PDFs as the authoritative source.  ￼

⸻

Level of detail: high

The Zondo transcripts are detailed enough for your intended graph.

They include:

Day number
Hearing date
Venue
Page number
Speaker labels
Legal representatives
Witness names
Institutions
Evidence bundle references
Chronology of events
Monetary amounts
Contracts
Companies
Departments
State entities
Procedural exchanges
Questions and answers

For example, the Day 327 sample explicitly identifies the hearing as concerning Mr Anoj Singh, former CFO of Eskom, and mentions Eskom, Transnet, McKinsey, Trillian, Tegeta, Optimum, pre-payments of R1.68 billion and R659 million, penalties, guarantees, directives and affidavits.  ￼

That is exactly the kind of material where a hybrid Qdrant + Neo4j system becomes powerful.

⸻

Comparison with Madlanga-style ingestion

Aspect	Madlanga Commission	Zondo Commission
Official transcript PDFs	Yes	Yes
Day-based structure	Yes	Yes
Speaker labels	Yes	Yes, very consistent
Page metadata	Yes	Yes
Witness/legal role extraction	Good	Very good
Supporting documents	Yes	Very rich
Historical completeness	Still ongoing/recent	Mature archive
Graph value	High	Very high
Risk of duplicates	Moderate	High, especially in documents section
Need for provenance	Essential	Essential

The Zondo data is likely the better first corpus to develop the ingestion framework because it is larger, older, more complete, and has many linked reports, statements, bundles and named matters.

⸻

What to add to your data model for Zondo

Your earlier graph model still works, but I would add a few Zondo-specific node types:

(:StateEntity)
(:Company)
(:Contract)
(:EvidenceBundle)
(:Amount)
(:Position)
(:ReportVolume)
(:Recommendation)
(:Finding)

Example graph extension:

(:Person)-[:HELD_POSITION]->(:Position)-[:AT_ORG]->(:Organisation)
(:Person)-[:TESTIFIED_ON]->(:Matter)
(:Contract)-[:INVOLVED_ORG]->(:Organisation)
(:Contract)-[:MENTIONED_IN]->(:Chunk)
(:Amount)-[:RELATES_TO]->(:Contract)
(:EvidenceBundle)-[:CONTAINS]->(:Document)
(:Finding)-[:SUPPORTED_BY]->(:Chunk)
(:Recommendation)-[:AROSE_FROM]->(:Finding)

For Zondo, this matters because the transcripts repeatedly refer to formal positions and entities:

Former CFO of Eskom
Minister
Board member
Acting CEO
Evidence leader
Legal representative
Gupta-linked company
State-owned enterprise
Parliamentary Portfolio Committee

Those should not all be flat Person and Organisation nodes. You want role-in-context relationships.

⸻

Better schema for roles

For Zondo, avoid:

(:Person)-[:HAS_ROLE]->(:Role)

as your only model.

Use:

(:Person)-[:HELD_POSITION {
  from_text,
  date_text,
  confidence,
  source_chunk_id
}]->(:Position)
(:Position)-[:AT_ORG]->(:Organisation)

Example:

(:Person {name: "Anoj Singh"})
-[:HELD_POSITION {from_text: "former CFO of Eskom"}]->
(:Position {title: "Chief Financial Officer"})
-[:AT_ORG]->
(:Organisation {name: "Eskom"})

This lets the same person be:

CFO at Transnet
CFO at Eskom
Witness before Commission
Person mentioned in another witness’s evidence
Subject of a finding

without collapsing everything into one vague role.

⸻

Discovery code for Zondo

The Zondo site is easier to scrape because the transcripts page exposes many direct PDF links.

from __future__ import annotations
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
BASE_URL = "https://www.statecapture.org.za"
TRANSCRIPTS_URL = f"{BASE_URL}/site/transcripts"
DAY_RE = re.compile(r"Day\s+(\d+)\s*[-–]\s*(\d{4}-\d{2}-\d{2})", re.I)
def discover_zondo_transcripts() -> list[dict]:
    html = requests.get(
        TRANSCRIPTS_URL,
        headers={"User-Agent": "Mozilla/5.0 research-ingest/0.1"},
        timeout=60,
    ).text
    soup = BeautifulSoup(html, "html.parser")
    results = []
    current_day = None
    current_date = None
    for element in soup.find_all(["h6", "h5", "h4", "a"]):
        text = element.get_text(" ", strip=True)
        m = DAY_RE.search(text)
        if m:
            current_day = int(m.group(1))
            current_date = m.group(2)
        if element.name == "a" and element.get("href"):
            href = urljoin(BASE_URL, element["href"])
            if href.lower().endswith(".pdf") and "transcript" in href.lower():
                results.append(
                    {
                        "commission": "Zondo Commission",
                        "day_no": current_day,
                        "date": current_date,
                        "url": href,
                        "title": text,
                    }
                )
    return results

I would store the discovery output immediately in a small sources.sqlite database or a sources.jsonl file, because the official site contains duplicates and the metadata sometimes appears around, not inside, the link.

⸻

Parser differences from Madlanga

The Zondo transcript format is highly regular. A page contains line numbers and speaker labels. The sample Day 327 transcript has lines like:

CHAIRPERSON:
ADV SELEKA SC:
ADV VAN DEN HEEVER:

and later witness evidence.  ￼

So your speaker parser can be more aggressive:

SPEAKER_RE = re.compile(
    r"^(CHAIRPERSON|ADV [A-Z .'-]+(?: SC)?|MR [A-Z .'-]+|MS [A-Z .'-]+|DR [A-Z .'-]+|PROF [A-Z .'-]+|WITNESS):\s*(.*)$"
)

But I would also add a second pass to detect witnesses from headings such as:

MR ANOJ SINGH
ANOJ SINGH: 
EXAMINATION BY ADV ...
CROSS-EXAMINATION BY ...

because the transcript may not always label a witness as WITNESS.

⸻

Recommended ingestion priority

For Zondo, I would ingest in this order:

Phase 1: transcripts only

Transcript PDF
→ pages
→ speaker turns
→ chunks
→ Qdrant
→ Neo4j: HearingDay, Document, Chunk, Person, Organisation, Place, Speaker

Phase 2: supporting documents

Use the official Statements and Documents section, which has document bundles grouped by day. These are large and often witness-specific.  ￼

Add:

EvidenceBundle
WitnessStatement
Annexure
Correspondence
Contract
Affidavit

Phase 3: reports and findings

The final reports are available through government and presidency sources. They can be ingested as a separate “findings layer”, linked back to transcript chunks and evidence bundles where possible.  ￼

⸻

Important caution

Do not treat the transcript graph as a truth graph.

Treat it as an evidence graph.

Use labels such as:

TESTIFIED
ALLEGED
MENTIONED
QUESTIONED_ABOUT
FOUND_BY_COMMISSION
RECOMMENDED_BY_COMMISSION

For example:

(:Person)-[:TESTIFIED_ABOUT]->(:Contract)
(:Claim)-[:STATED_BY]->(:Person)
(:Claim)-[:SUPPORTED_BY]->(:Chunk)
(:Finding)-[:MADE_IN]->(:ReportVolume)
(:Finding)-[:REFERS_TO]->(:Person)

This keeps the distinction between:

A witness said X.
The Commission found X.
A report recommended X.
A court later confirmed/rejected X.

That distinction is legally and analytically important.

⸻

My practical recommendation

Build your framework first on the Zondo Commission, then apply it to the Madlanga Commission.

Reason: Zondo has a mature archive, many transcripts, rich supporting documents, consistent speaker structure, and known high-value entities like Eskom, Transnet, Denel, Bosasa, Prasa, SSA, Tegeta, Trillian, McKinsey, the Gupta family, ministers, boards and executives.

The Zondo corpus is almost ideal for proving the full system:

semantic search in Qdrant
+
entity/event/provenance graph in Neo4j
+
evidence-backed answers

Once it works there, the Madlanga corpus becomes a second collection using the same ingestion design.