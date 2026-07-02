# Method, how this works, and how to check it

*The public methodology behind the Commission Transcript Intelligence work. Written so a
journalist, lawyer, or researcher can scrutinise it. Everything here is reproducible from the
official record; nothing is hand-curated to reach a conclusion.*

## The one principle that governs everything

**Mention ≠ Claim ≠ Finding ≠ Fact.** This is an **evidence graph, not a truth graph.**

- A person *named* in a transcript is a `MENTIONED_IN` edge, nothing more.
- Something a witness *said* is a `:Claim`, `STATED_BY` a person, `SUPPORTED_BY` the exact
  passage. It is written with `status = "alleged"`, always. There are **no "fact" edges**
  (no `Person -[:CORRUPTLY_INFLUENCED]-> Contract`), the schema makes them impossible.
- A commission *conclusion* would be a `:Finding`; a court outcome a separate status. The
  pipeline does not assert either.

Uncertainty lives in *structure* (status, attribution, who-said-it), never in softened text.

## The pipeline (official record → searchable evidence graph)

```
official site → discover → download (+SHA256) → parse PDF → speaker-aware chunk
   → LLM extract (entities / mentions / claims, as reported speech)
   → resolve names against a curated, human-owned store
   → Qdrant (semantic search) + Neo4j (the evidence graph)
```

1. **Discover & download.** Official Commission PDFs are fetched and fingerprinted (SHA256),
   so every passage traces to a specific document.
2. **Parse & chunk.** Text is split into speaker-aware passages, each carrying hearing day,
   page, and a stable `chunk_id`.
3. **Extract (LLM).** Each passage is read into structured **claims**, *who said what about
   whom*. Predicates are always reported speech ("stated/testified/alleged that…"), and every
   claim stores a **verbatim quote**. A quote that isn't an exact substring of the source is
   **dropped** as a possible fabrication, never stored.
4. **Resolve.** Names are matched against a **human-owned** canonical store (no automatic
   surname-merging: there are four distinct Khumalos in this corpus). A name that doesn't
   resolve is kept as a flagged raw entity, never silently dropped.
5. **Store.** Passages go to Qdrant (to answer *"where is testimony about X"* by meaning);
   the graph goes to Neo4j (to answer *"who/what co-occurs, in which hearing, how"*).

## How "association," "stance," and "contested" are computed

- **Association** = how often two entities are *named in the same sworn claim*. A line between
  two people means the testimony discusses them together, a lead, not a relationship.
- **Stance** (asserted / questioned / denied) is read from the reported-speech verb of each
  claim: *stated/testified* → asserted; *asked whether / put to* → a question put by counsel;
  *denied / disputed / vehemently* → a denial.
- **Contested** = a relationship that carries a meaningful cluster of *denials*. It flags where
  the testimony **fights**, not who is guilty.

## What this does NOT do (the honest limits)

- It does **not** decide what is true. Co-mention is association, not proof; a denial is a
  denial, not exoneration.
- Stance is a **first-order** read off the verb, not a full accuser-vs-defender model.
- Name resolution depends on a human seed; coverage is good for the principal cast, partial
  for the long tail (and a known share of claims carry an uncanonicalised speaker, flagged,
  not hidden).
- A claim's *predicate* is a machine paraphrase; the **verbatim quote** is the ground truth.
  Where they differ, the quote wins.

## Reproducibility

- Source: official Commission records (public domain). PDFs fingerprinted; nothing relicensed.
- Models: a fixed LLM for extraction, BGE embeddings for search, spaCy for entity detection,
  all behind a cache, so a re-run is deterministic and free.
- Specs: `docs/ontology.md`, `docs/neo4j-model.md`, `docs/qdrant-model.md`; decisions in
  `docs/decisions/`; the evidentiary framework in `plans/evidentiary-completeness-track.md`.

## Standing disclaimer

Everything surfaced is an **allegation in the public record, attributed to named speakers
under oath, not a finding of fact.** This corpus contains serious allegations about named,
often private, individuals. Identity and ownership claims flagged for verification are
confirmed against the record before any are presented as a named individual's conduct. See
`DISCLAIMER.md`.
