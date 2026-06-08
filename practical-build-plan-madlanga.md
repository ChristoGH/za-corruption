I am assuming you mean the Madlanga Commission. The official site describes it as the Judicial Commission of Inquiry into alleged criminality, political interference and corruption in the criminal justice system, led by Justice Mbuyiseli Madlanga. Its mandate includes probing criminal syndicate infiltration into law enforcement, intelligence, prosecution authorities, the judiciary and correctional services.  ￼ The official site has Home, Media, Notices, Hearings, About and Contact sections, and publishes hearing records and statements.  ￼ I found official PDF records such as MADLANGA_COMMISSION_RECORD_20260212, a 170-page hearing record for Day 59, which confirms the “one PDF per hearing day” pattern you want to ingest.  ￼

Below is a practical build plan.

⸻

1. Target architecture

Use Qdrant for semantic retrieval and Neo4j for the structured knowledge graph.

Official website
   ↓
PDF discovery / download
   ↓
PDF text extraction
   ↓
Transcript segmentation
   ↓
Speaker / role / page / day metadata
   ↓
Entity + event extraction
   ↓
Qdrant chunks
   ↓
Neo4j graph

Use Qdrant for questions like:

“Where was Brown Mogotsi mentioned in relation to Carrim?”

Use Neo4j for questions like:

“Which witnesses mentioned IPID, Ekurhuleni, EMPD and threats in the same day of testimony?”

⸻

2. Suggested graph model

Use a graph that separates source evidence from extracted claims.

Nodes

(:Commission)
(:HearingDay {day_no, date, title, source_url})
(:Document {url, filename, sha256, downloaded_at})
(:Page {page_no})
(:Chunk {chunk_id, text, page_start, page_end})
(:Person {name, aliases})
(:Organisation {name})
(:Place {name})
(:Role {name})      // Commissioner, Witness, Evidence Leader, Chairperson, etc.
(:Event {name, date_text, event_type, summary})
(:Matter {name})    // e.g. PKTT, IPID investigation, Carrim application

Relationships

(:Commission)-[:HAS_HEARING]->(:HearingDay)
(:HearingDay)-[:HAS_DOCUMENT]->(:Document)
(:Document)-[:HAS_PAGE]->(:Page)
(:Page)-[:HAS_CHUNK]->(:Chunk)
(:Person)-[:APPEARS_IN]->(:Chunk)
(:Organisation)-[:MENTIONED_IN]->(:Chunk)
(:Place)-[:MENTIONED_IN]->(:Chunk)
(:Event)-[:EVIDENCED_BY]->(:Chunk)
(:Person)-[:HAS_ROLE {from_day, confidence}]->(:Role)
(:Person)-[:SPOKE_IN {speaker_label}]->(:Chunk)
(:Person)-[:MENTIONED_PERSON {confidence}]->(:Person)
(:Person)-[:AFFILIATED_WITH {role_text, confidence}]->(:Organisation)
(:Event)-[:INVOLVES_PERSON]->(:Person)
(:Event)-[:OCCURRED_AT]->(:Place)

Important: do not make extracted allegations look like facts. Store them as:

(:Claim {text, confidence, extraction_method})
(:Claim)-[:SUPPORTED_BY]->(:Chunk)
(:Claim)-[:MENTIONS]->(:Person)

That way the database preserves provenance.

⸻

3. Repo layout

madlanga-ingest/
  docker-compose.yml
  pyproject.toml
  .env.example
  data/
    raw_pdfs/
    processed/
  src/
    config.py
    discover.py
    download.py
    parse_pdf.py
    chunking.py
    extract_entities.py
    qdrant_store.py
    neo4j_store.py
    pipeline.py

⸻

4. Docker for Qdrant + Neo4j

# docker-compose.yml
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

Run:

docker compose up -d

⸻

5. Python dependencies

# pyproject.toml
[project]
name = "madlanga-ingest"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "requests",
  "beautifulsoup4",
  "playwright",
  "pymupdf",
  "qdrant-client",
  "neo4j",
  "sentence-transformers",
  "spacy",
  "python-dotenv",
  "pydantic",
  "tqdm"
]

Install:

uv venv
uv pip install -e .
python -m spacy download en_core_web_trf
playwright install chromium

⸻

6. Discover official PDFs

The official site has some anti-bot verification on the hearings page in normal browser access, so I would build discovery in two layers:

1. Try normal requests.
2. Fall back to Playwright.
3. Also scan known /uploads/ PDF links from the official pages.

# src/discover.py
from __future__ import annotations
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright
BASE_URL = "https://criminaljusticecommission.org.za"
START_PAGES = [
    f"{BASE_URL}/",
    f"{BASE_URL}/hearing.php",
    f"{BASE_URL}/media.php",
    f"{BASE_URL}/index.php?page=1",
    f"{BASE_URL}/index.php?page=2",
    f"{BASE_URL}/index.php?page=3",
    f"{BASE_URL}/index.php?page=4",
    f"{BASE_URL}/index.php?page=5",
    f"{BASE_URL}/index.php?page=6",
    f"{BASE_URL}/index.php?page=7",
    f"{BASE_URL}/index.php?page=8",
    f"{BASE_URL}/index.php?page=9",
]
PDF_PATTERN = re.compile(
    r"(MADLANGA.*RECORD|COMMISSION.*RECORD|DAY\s*\d+|\.pdf)",
    re.IGNORECASE,
)
def fetch_html_requests(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 transcript-research-bot/0.1 contact: your-email@example.com"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text
def fetch_html_playwright(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60_000)
        html = page.content()
        browser.close()
        return html
def extract_pdf_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        text = a.get_text(" ", strip=True)
        if href.lower().endswith(".pdf") or PDF_PATTERN.search(href) or PDF_PATTERN.search(text):
            if "criminaljusticecommission.org.za" in href:
                links.add(href)
    return sorted(links)
def discover_pdfs() -> list[str]:
    pdfs: set[str] = set()
    for url in START_PAGES:
        try:
            html = fetch_html_requests(url)
        except Exception:
            html = fetch_html_playwright(url)
        for link in extract_pdf_links(html, url):
            pdfs.add(link)
    return sorted(pdfs)
if __name__ == "__main__":
    for pdf in discover_pdfs():
        print(pdf)

Later, improve this by storing discovered URLs in SQLite or Postgres so you do not re-download.

⸻

7. Download PDFs safely

# src/download.py
from __future__ import annotations
import hashlib
from pathlib import Path
import requests
RAW_DIR = Path("data/raw_pdfs")
RAW_DIR.mkdir(parents=True, exist_ok=True)
def safe_filename(url: str) -> str:
    name = url.split("/")[-1].replace("%20", "_")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
def download_pdf(url: str) -> dict:
    out_path = RAW_DIR / safe_filename(url)
    if not out_path.exists():
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 transcript-research-bot/0.1"},
            timeout=60,
        )
        response.raise_for_status()
        out_path.write_bytes(response.content)
    return {
        "url": url,
        "path": str(out_path),
        "filename": out_path.name,
        "sha256": sha256_file(out_path),
    }

⸻

8. Parse transcripts from PDF

Use PyMuPDF. It works well for text-based PDFs. If some PDFs are scanned images, add OCR later.

# src/parse_pdf.py
from __future__ import annotations
import re
from pathlib import Path
import fitz
DAY_RE = re.compile(r"(\d{1,2}\s+[A-Z]+\s+20\d{2})\s*[–-]\s*DAY\s*(\d+)", re.I)
SPEAKER_RE = re.compile(r"^([A-Z][A-Z .'\-()]+):\s*(.*)$")
def extract_pages(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        pages.append(
            {
                "page_no": i,
                "text": clean_page_text(text),
            }
        )
    return pages
def clean_page_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
def infer_day_metadata(text: str) -> dict:
    match = DAY_RE.search(text)
    if not match:
        return {"date_text": None, "day_no": None}
    return {
        "date_text": match.group(1).title(),
        "day_no": int(match.group(2)),
    }
def extract_speaker_turns(page_text: str, page_no: int) -> list[dict]:
    turns = []
    current = None
    for line in page_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = SPEAKER_RE.match(line)
        if m:
            if current:
                turns.append(current)
            current = {
                "speaker_label": m.group(1).strip(),
                "text": m.group(2).strip(),
                "page_start": page_no,
                "page_end": page_no,
            }
        elif current:
            current["text"] += " " + line
            current["page_end"] = page_no
    if current:
        turns.append(current)
    return turns

⸻

9. Chunking strategy

Do not chunk blindly every 1,000 characters. For transcripts, speaker turns matter.

# src/chunking.py
from __future__ import annotations
import hashlib
def chunk_turns(turns: list[dict], max_chars: int = 1800) -> list[dict]:
    chunks = []
    buffer = []
    size = 0
    for turn in turns:
        turn_text = f"{turn['speaker_label']}: {turn['text']}"
        if size + len(turn_text) > max_chars and buffer:
            chunks.append(make_chunk(buffer))
            buffer = []
            size = 0
        buffer.append(turn)
        size += len(turn_text)
    if buffer:
        chunks.append(make_chunk(buffer))
    return chunks
def make_chunk(turns: list[dict]) -> dict:
    text = "\n".join(f"{t['speaker_label']}: {t['text']}" for t in turns)
    chunk_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "chunk_id": chunk_id,
        "text": text,
        "page_start": min(t["page_start"] for t in turns),
        "page_end": max(t["page_end"] for t in turns),
        "speakers": sorted(set(t["speaker_label"] for t in turns)),
    }

⸻

10. Entity and role extraction

Start with spaCy, then later add an LLM pass for better roles and events.

# src/extract_entities.py
from __future__ import annotations
import spacy
nlp = spacy.load("en_core_web_trf")
ROLE_HINTS = {
    "CHAIRPERSON": "Commissioner",
    "COMMISSIONER": "Commissioner",
    "ADV": "Evidence Leader",
    "SC": "Senior Counsel",
    "MS": "Person",
    "MR": "Person",
    "DR": "Person",
    "LT GEN": "Witness",
    "GENERAL": "Witness",
}
def infer_role_from_speaker_label(label: str) -> str | None:
    upper = label.upper()
    for hint, role in ROLE_HINTS.items():
        if hint in upper:
            return role
    return None
def extract_entities(text: str) -> dict:
    doc = nlp(text)
    people = set()
    orgs = set()
    places = set()
    for ent in doc.ents:
        value = ent.text.strip()
        if len(value) < 2:
            continue
        if ent.label_ == "PERSON":
            people.add(value)
        elif ent.label_ in {"ORG"}:
            orgs.add(value)
        elif ent.label_ in {"GPE", "LOC", "FAC"}:
            places.add(value)
    return {
        "people": sorted(people),
        "organisations": sorted(orgs),
        "places": sorted(places),
    }
def extract_chunk_annotations(chunk: dict) -> dict:
    entities = extract_entities(chunk["text"])
    speaker_roles = []
    for speaker in chunk["speakers"]:
        role = infer_role_from_speaker_label(speaker)
        if role:
            speaker_roles.append(
                {
                    "speaker_label": speaker,
                    "role": role,
                }
            )
    return {
        **entities,
        "speaker_roles": speaker_roles,
    }

For higher quality, add an LLM extraction step later that returns structured JSON like:

{
  "people": [
    {"name": "Nomsa Masuku", "role": "Witness", "confidence": 0.88}
  ],
  "events": [
    {
      "summary": "A witness described threats during investigations",
      "event_type": "Threat",
      "date_text": "December 2024",
      "places": ["N17", "Springs"],
      "people": ["Nomsa Masuku"]
    }
  ],
  "claims": [
    {
      "text": "The witness said her vehicle was fired at near Springs.",
      "attribution": "testimony",
      "confidence": 0.81
    }
  ]
}

⸻

11. Store chunks in Qdrant

# src/qdrant_store.py
from __future__ import annotations
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
COLLECTION = "madlanga_transcripts"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
model = SentenceTransformer(MODEL_NAME)
client = QdrantClient(url="http://localhost:6333")
def ensure_collection():
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
def upsert_chunks(chunks: list[dict]):
    ensure_collection()
    texts = [c["text"] for c in chunks]
    vectors = model.encode(texts, normalize_embeddings=True).tolist()
    points = []
    for chunk, vector in zip(chunks, vectors):
        points.append(
            PointStruct(
                id=chunk["chunk_id"],
                vector=vector,
                payload={
                    "text": chunk["text"],
                    "day_no": chunk.get("day_no"),
                    "date_text": chunk.get("date_text"),
                    "source_url": chunk.get("source_url"),
                    "filename": chunk.get("filename"),
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "speakers": chunk.get("speakers", []),
                },
            )
        )
    client.upsert(collection_name=COLLECTION, points=points)

⸻

12. Store graph in Neo4j

Create constraints first.

CREATE CONSTRAINT commission_name IF NOT EXISTS
FOR (c:Commission) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT hearing_day IF NOT EXISTS
FOR (h:HearingDay) REQUIRE h.key IS UNIQUE;
CREATE CONSTRAINT document_sha IF NOT EXISTS
FOR (d:Document) REQUIRE d.sha256 IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;
CREATE CONSTRAINT person_name IF NOT EXISTS
FOR (p:Person) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT org_name IF NOT EXISTS
FOR (o:Organisation) REQUIRE o.name IS UNIQUE;
CREATE CONSTRAINT place_name IF NOT EXISTS
FOR (p:Place) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT role_name IF NOT EXISTS
FOR (r:Role) REQUIRE r.name IS UNIQUE;

Python writer:

# src/neo4j_store.py
from __future__ import annotations
from neo4j import GraphDatabase
driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password123"),
)
def upsert_chunk_graph(chunk: dict, annotations: dict):
    with driver.session() as session:
        session.execute_write(_upsert_chunk_graph, chunk, annotations)
def _upsert_chunk_graph(tx, chunk: dict, ann: dict):
    tx.run(
        """
        MERGE (com:Commission {name: "Madlanga Commission"})
        MERGE (h:HearingDay {key: $hearing_key})
          SET h.day_no = $day_no,
              h.date_text = $date_text,
              h.source_url = $source_url
        MERGE (d:Document {sha256: $sha256})
          SET d.filename = $filename,
              d.url = $source_url
        MERGE (c:Chunk {chunk_id: $chunk_id})
          SET c.text = $text,
              c.page_start = $page_start,
              c.page_end = $page_end
        MERGE (com)-[:HAS_HEARING]->(h)
        MERGE (h)-[:HAS_DOCUMENT]->(d)
        MERGE (d)-[:HAS_CHUNK]->(c)
        """,
        hearing_key=f"day-{chunk.get('day_no')}-{chunk.get('date_text')}",
        day_no=chunk.get("day_no"),
        date_text=chunk.get("date_text"),
        source_url=chunk.get("source_url"),
        sha256=chunk.get("sha256"),
        filename=chunk.get("filename"),
        chunk_id=chunk["chunk_id"],
        text=chunk["text"],
        page_start=chunk.get("page_start"),
        page_end=chunk.get("page_end"),
    )
    for person in ann["people"]:
        tx.run(
            """
            MATCH (c:Chunk {chunk_id: $chunk_id})
            MERGE (p:Person {name: $name})
            MERGE (p)-[:MENTIONED_IN]->(c)
            """,
            chunk_id=chunk["chunk_id"],
            name=person,
        )
    for org in ann["organisations"]:
        tx.run(
            """
            MATCH (c:Chunk {chunk_id: $chunk_id})
            MERGE (o:Organisation {name: $name})
            MERGE (o)-[:MENTIONED_IN]->(c)
            """,
            chunk_id=chunk["chunk_id"],
            name=org,
        )
    for place in ann["places"]:
        tx.run(
            """
            MATCH (c:Chunk {chunk_id: $chunk_id})
            MERGE (p:Place {name: $name})
            MERGE (p)-[:MENTIONED_IN]->(c)
            """,
            chunk_id=chunk["chunk_id"],
            name=place,
        )
    for sr in ann["speaker_roles"]:
        tx.run(
            """
            MATCH (c:Chunk {chunk_id: $chunk_id})
            MERGE (p:Person {name: $speaker_label})
            MERGE (r:Role {name: $role})
            MERGE (p)-[:HAS_ROLE {source: "speaker_label"}]->(r)
            MERGE (p)-[:SPOKE_IN {speaker_label: $speaker_label}]->(c)
            """,
            chunk_id=chunk["chunk_id"],
            speaker_label=sr["speaker_label"],
            role=sr["role"],
        )

⸻

13. End-to-end pipeline

# src/pipeline.py
from __future__ import annotations
from discover import discover_pdfs
from download import download_pdf
from parse_pdf import extract_pages, infer_day_metadata, extract_speaker_turns
from chunking import chunk_turns
from extract_entities import extract_chunk_annotations
from qdrant_store import upsert_chunks
from neo4j_store import upsert_chunk_graph
def process_pdf(url: str):
    doc_meta = download_pdf(url)
    pages = extract_pages(doc_meta["path"])
    all_text = "\n".join(p["text"] for p in pages[:3])
    day_meta = infer_day_metadata(all_text)
    turns = []
    for page in pages:
        turns.extend(extract_speaker_turns(page["text"], page["page_no"]))
    chunks = chunk_turns(turns)
    enriched_chunks = []
    for chunk in chunks:
        enriched = {
            **chunk,
            **doc_meta,
            **day_meta,
            "source_url": url,
        }
        enriched_chunks.append(enriched)
    upsert_chunks(enriched_chunks)
    for chunk in enriched_chunks:
        annotations = extract_chunk_annotations(chunk)
        upsert_chunk_graph(chunk, annotations)
def main():
    urls = discover_pdfs()
    print(f"Discovered {len(urls)} PDFs")
    for url in urls:
        print(f"Processing {url}")
        process_pdf(url)
if __name__ == "__main__":
    main()

Run:

python src/pipeline.py

⸻

14. Example Qdrant search

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
client = QdrantClient(url="http://localhost:6333")
model = SentenceTransformer("BAAI/bge-small-en-v1.5")
query = "testimony about threats against investigators near Springs"
vector = model.encode(query, normalize_embeddings=True).tolist()
hits = client.search(
    collection_name="madlanga_transcripts",
    query_vector=vector,
    limit=10,
)
for hit in hits:
    print(hit.score)
    print(hit.payload["filename"], hit.payload["page_start"], hit.payload["page_end"])
    print(hit.payload["text"][:700])
    print("---")

⸻

15. Example Neo4j questions

Find people mentioned with IPID:

MATCH (p:Person)-[:MENTIONED_IN]->(c:Chunk)<-[:MENTIONED_IN]-(o:Organisation)
WHERE toLower(o.name) CONTAINS "ipid"
RETURN p.name, count(c) AS mentions
ORDER BY mentions DESC
LIMIT 25;

Find speakers and roles:

MATCH (p:Person)-[:HAS_ROLE]->(r:Role)
RETURN r.name AS role, collect(DISTINCT p.name) AS people
ORDER BY role;

Find places mentioned on a specific hearing day:

MATCH (h:HearingDay)-[:HAS_DOCUMENT]->(:Document)-[:HAS_CHUNK]->(c:Chunk)
MATCH (place:Place)-[:MENTIONED_IN]->(c)
WHERE h.day_no = 59
RETURN place.name, count(*) AS mentions
ORDER BY mentions DESC;

Find chunks where a person and place co-occur:

MATCH (person:Person {name: "Nomsa Masuku"})-[:MENTIONED_IN]->(c:Chunk)
MATCH (place:Place)-[:MENTIONED_IN]->(c)
RETURN place.name, c.page_start, c.page_end, left(c.text, 500) AS evidence
ORDER BY c.page_start;

⸻

16. The most important design decision

Keep three levels separate:

Raw transcript text
Extracted entity mentions
Interpreted claims/events

That protects you from accidentally turning testimony into fact. For example:

Witness says X happened

should become:

(:Claim {text: "Witness said X happened", attribution: "testimony"})

not:

(:Event {name: "X happened"})

unless you explicitly mark it as alleged, testified, or reported.

⸻

17. First MVP milestone

Build this in the following order:

1. Download all official PDFs and store URL, filename, SHA256.
2. Extract text and chunk by speaker turns.
3. Store chunks in Qdrant with day, page and URL metadata.
4. Store Person, Organisation, Place mentions in Neo4j.
5. Add role detection for CHAIRPERSON, ADV, SC, COMMISSIONER, MR, MS, DR.
6. Add LLM-based event and claim extraction only after the above works.

The MVP success test is:

“Search Qdrant for a topic, open the result, and jump from that chunk to Neo4j to see the people, organisations, places and hearing day connected to it.”

That gives you a working semantic + graph intelligence layer over the Commission records.