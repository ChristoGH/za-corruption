# Disclaimer & Data Notice

_This notice governs the **content** (the commission records and everything derived
from them). The **software** is separately licensed under Apache-2.0 — see `LICENSE`
and `NOTICE`._

## What this project is

The Commission Transcript Intelligence Platform is an independent, open-source
research tool that ingests, indexes, and structures **publicly available** transcripts
and documents from South African commissions of inquiry, to make that public record
searchable and navigable.

It is **not affiliated with, endorsed by, or operated by** any commission of inquiry,
the South African government, or any party to the proceedings.

## Source of the content

All processed material derives from official public records, including:

- **Madlanga Commission / Criminal Justice Commission** —
  https://criminaljusticecommission.org.za
- **Zondo / State Capture Commission** — official records (where reachable), with a
  clearly-flagged non-authoritative plaintext fallback where they are not.

The project claims **no ownership** of these records. Where the corpus numbers are
published, the known gaps are stated (e.g. days absent from the public record, and any
documents that were unreachable at source).

## The governing principle: Mention ≠ Claim ≠ Finding ≠ Fact

This is an **evidence graph, not a truth graph.** The data model deliberately enforces
the difference:

- A person being **named** in a transcript is a *mention* — nothing more.
- Something a witness **said** is a **claim**, carrying attribution, status, and
  confidence, supported by the exact source passage — **not** a statement of fact.
- A **commission finding** is sourced to a report; a later **court outcome** is a
  separate status, not an overwrite of the claim.

Every extracted entity, claim, and event carries provenance: commission, hearing day,
document, source URL, file hash, page number, source passage, extraction method, and
confidence.

**Testimony before a commission is allegation, not a finding of fact.** Nothing in this
project should be read as asserting that any named individual is guilty of, or
responsible for, any conduct. Allegations are presented as what was said, by whom, on
the record — not as conclusions.

## Terms applying to the content

- **Underlying records** (transcripts and source documents): remain the property of
  their respective official sources and are **not** relicensed by this project. Refer to
  and obtain them from the official sites linked above.
- **Derived artifacts produced by this project** (text chunks and their metadata,
  aggregate statistics, and graph/network data): offered under
  **[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)**,
  with attribution to both this project and the official source record. This applies only
  to the derived structure, not to the underlying record text itself.

## No legal advice; accuracy

This project is provided for research, journalistic, and civic-transparency purposes.
It may contain extraction errors. It does not constitute legal advice and must not be
relied upon as a substitute for the official record. Always verify against the
page-cited official source before relying on any item.

## Corrections & takedown

If you are a named individual, a rights holder, or an official source and you have a
correction request, a concern about how material is presented, or a takedown request,
please open an issue on the repository or contact the maintainer:

> **Contact:** _[add a project/role contact — repo issues or a dedicated address]_

Good-faith requests — particularly those affecting living, private individuals — will
be reviewed promptly.
