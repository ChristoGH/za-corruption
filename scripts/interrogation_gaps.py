"""Surface the open threads in a witness's account, then draft sourced questions.

This is the Track B "unanswered / not-asked" layer for a single person. It pulls
a grounded dossier from Neo4j (every claim made ABOUT the person by others, and
every claim the person themselves stated), then asks the model to identify the
gaps and draft a pointed question for each, with every gap and question cited to
a day and claim id. The model only ever sees real claims and is told to invent
nothing; the raw dossier is appended so each question is checkable against source.

Run (Neo4j up + claims loaded; .env supplies NEO4J_PASSWORD + ANTHROPIC_API_KEY):
    uv run python scripts/interrogation_gaps.py --person "Senona"
    uv run python scripts/interrogation_gaps.py --person "Sibiya" --model claude-haiku-4-5

Output: reports/interrogation_<person>.md  (reports/ is gitignored)
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import date
from pathlib import Path

import anthropic

import commission_ingestion  # noqa: F401  (triggers .env load)
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "claude-sonnet-4-6"

Q_ALLEGATIONS = """
MATCH (cl:Claim)-[:MENTIONS]->(p:Person)
WHERE toLower(p.name) CONTAINS toLower($name)
MATCH (cl)-[:STATED_BY]->(sp:Person)
WHERE NOT toLower(sp.name) CONTAINS toLower($name)
MATCH (cl)-[:SUPPORTED_BY]->(c:Chunk)
OPTIONAL MATCH (cl)-[:MENTIONS]->(m:Person) WHERE toLower(m.name) CONTAINS 'matlala'
RETURN cl.claim_id AS id, coalesce(cl.quote, cl.text) AS text, sp.name AS speaker,
       c.day_no AS day, c.page_start AS page, cl.certainty AS certainty,
       count(m) > 0 AS matlala_linked
ORDER BY matlala_linked DESC, day, page
"""

Q_STATEMENTS = """
MATCH (cl:Claim)-[:STATED_BY]->(sp:Person)
WHERE toLower(sp.name) CONTAINS toLower($name)
MATCH (cl)-[:SUPPORTED_BY]->(c:Chunk)
RETURN cl.claim_id AS id, coalesce(cl.quote, cl.text) AS text,
       c.day_no AS day, c.page_start AS page
ORDER BY day, page
"""

Q_LINKS = """
MATCH (cl:Claim)-[:MENTIONS]->(s:Person)
WHERE toLower(s.name) CONTAINS toLower($name)
MATCH (cl)-[:MENTIONS]->(e)
WHERE NOT toLower(e.name) CONTAINS toLower($name)
RETURN labels(e)[0] AS type, e.name AS name, count(DISTINCT cl) AS claims
ORDER BY claims DESC LIMIT 30
"""


def _clean(text: str, limit: int = 300) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:limit] + ("…" if len(t) > limit else "")


def fetch_dossier(name: str) -> dict:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "changeme")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        with driver.session() as s:
            allegations = [dict(r) for r in s.run(Q_ALLEGATIONS, name=name)]
            statements = [dict(r) for r in s.run(Q_STATEMENTS, name=name)]
            links = [dict(r) for r in s.run(Q_LINKS, name=name)]
    finally:
        driver.close()
    return {"allegations": allegations, "statements": statements, "links": links}


def _fmt_claims(rows: list[dict], with_speaker: bool) -> str:
    out = []
    for r in rows:
        cid = (r.get("id") or "")[:10]
        day = r.get("day")
        page = r.get("page")
        loc = f"Day {day}" + (f", p.{page}" if page is not None else "")
        who = f" — {r['speaker']}" if with_speaker and r.get("speaker") else ""
        tag = "  [Matlala-linked]" if r.get("matlala_linked") else ""
        out.append(f"- [{cid} | {loc}{who}]{tag} {_clean(r.get('text', ''))}")
    return "\n".join(out)


def build_prompt(name: str, dossier: dict, max_each: int) -> tuple[str, str]:
    alle = dossier["allegations"][:max_each]
    stmt = dossier["statements"][:max_each]
    links = dossier["links"]
    links_txt = "\n".join(
        f"- {l['name']} ({l['type']}): {l['claims']} shared claims" for l in links
    )
    data = (
        f"PERSON: {name}\n\n"
        f"=== ALLEGATIONS AND STATEMENTS MADE ABOUT {name} BY OTHER WITNESSES "
        f"({len(alle)} of {len(dossier['allegations'])}) ===\n"
        "Each line: [claim_id | Day, page — speaker] claim text.\n"
        f"{_fmt_claims(alle, with_speaker=True)}\n\n"
        f"=== WHAT {name} HIMSELF STATED ON THE STAND "
        f"({len(stmt)} of {len(dossier['statements'])}) ===\n"
        "Each line: [claim_id | Day, page] claim text.\n"
        f"{_fmt_claims(stmt, with_speaker=False)}\n\n"
        f"=== ENTITIES THE TESTIMONY TIES TO {name} (by shared claims) ===\n"
        f"{links_txt}\n"
    )
    instructions = f"""\
You are an investigative analyst preparing to question a commission witness. Using ONLY
the claims supplied above, produce a briefing in Markdown with exactly two parts.

Hard rules:
- Use only the supplied claims. Invent no facts, names, dates, or allegations.
- Cite every gap and every question with its source as (Day N, claim_id-prefix). Use the
  10-char claim_id prefix shown in brackets.
- Everything is ALLEGED testimony, never established fact. Phrase accordingly.
- Be conservative: only call an allegation "unanswered" if nothing in the person's own
  statements addresses its substance. If they addressed it, it is not a gap.
- Questions must be neutral in form (genuine questions, not accusations) but specific and
  pointed, each anchored to the exact allegation it probes.

Part 1 — "The missing information: open threads in {name}'s account"
Three subsections, each a short list:
  a) Unanswered allegations — asserted about {name} by others, with no statement from him
     addressing the substance.
  b) Uncorroborated denials — points {name} denied or disputed that no other witness
     supports or contradicts in the supplied claims (his word standing alone).
  c) Unexplored links — people, organisations, or companies tied to him by shared claims
     that the supplied testimony never follows up.

Part 2 — "Questions to put to {name}"
A numbered list. Each question probes one open thread from Part 1, names the specific
allegation and who made it, and ends with its (Day N, claim_id-prefix) citation.

Keep it tight and usable. No preamble, start at the Part 1 heading."""
    return data, instructions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True, help="Name substring, e.g. 'Senona'.")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-each", type=int, default=80,
                    help="Cap on allegations and statements fed to the model.")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    dossier = fetch_dossier(args.person)
    n_alle, n_stmt = len(dossier["allegations"]), len(dossier["statements"])
    if n_alle == 0 and n_stmt == 0:
        raise SystemExit(
            f"No claims found for '{args.person}'. Check the name (try a surname only) "
            "and that claims are loaded (build-graph --with-claims)."
        )
    print(f"dossier: {n_alle} allegations about, {n_stmt} statements by, "
          f"{len(dossier['links'])} linked entities")

    data, instructions = build_prompt(args.person, dossier, args.max_each)
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=args.model,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": data, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": instructions},
            ],
        }],
    )
    body = "".join(b.text for b in resp.content if b.type == "text")

    slug = re.sub(r"[^a-z0-9]+", "-", args.person.lower()).strip("-")
    out = args.out or (ROOT / "reports" / f"interrogation_{slug}.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    appendix = (
        "\n\n---\n\n## Source dossier (every claim above is checkable here)\n\n"
        f"### Allegations about {args.person} ({n_alle})\n"
        f"{_fmt_claims(dossier['allegations'], with_speaker=True)}\n\n"
        f"### Statements by {args.person} ({n_stmt})\n"
        f"{_fmt_claims(dossier['statements'], with_speaker=False)}\n"
    )
    header = (
        f"# Interrogation gaps: {args.person}\n\n"
        f"*Generated {date.today().isoformat()} from the Madlanga evidence graph. "
        f"{n_alle} allegations about {args.person}, {n_stmt} of his own statements. "
        "Everything here is alleged testimony in the public record, attributed under "
        "oath, not a finding of fact. Questions are leads, not accusations.*\n\n"
    )
    out.write_text(header + body + appendix, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
