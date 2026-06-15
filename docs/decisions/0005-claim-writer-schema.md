# 0005 — :Claim writer schema (MERGE key + raw-subject fallthrough)

- **Status:** Accepted
- **Date:** 2026-06-15
- **Scope:** M4 net-new code — the `:Claim` graph writer (`graph/neo4j_store.py`
  `write_claims` + `cli/build_graph.py` wiring). M3 wrote zero `:Claim` nodes by
  construction; this is the zero-to-one for the claim layer.
- **Governs:** the two hardest-to-change things once `:Claim` nodes exist. Decided
  *before* any node is written. The pre-flight canary (`reports/preflight_canary.md`,
  when run) is the acceptance test for the code that implements this ADR.

## Context

Claim extraction (`extraction/extractor.py`, `schema.py`) already produces per-chunk
JSON: `ExtractedClaim {speaker, subject_refs, predicate, object_refs, quote, certainty}`,
cached under `data/cache/extraction/<model>/<prompt_version>/<chunk_id>.json`. This ADR
covers only how that output is written to Neo4j. Relationship naming is already settled
in `docs/ontology.md` (`STATED_BY`, `SUPPORTED_BY`, `MENTIONS`) and `docs/neo4j-model.md`
(`claim_id` unique constraint); this ADR does not introduce new edge names.

Two decisions are not yet settled and are the most expensive to reverse after live data
exists: the `:Claim` MERGE key (governs idempotency) and what the writer does when a
claim's subject does not resolve to a canonical entity (governs the defamation-relevant
"floating allegation" failure mode).

## Decision 1 — `:Claim` MERGE key (`claim_id`)

The MERGE key MUST be deterministic from claim content so re-runs are idempotent (a
random UUID is wrong and would double-load on every re-run). `claim_id` is:

```
claim_id = sha256( "{chunk_id}|{speaker_entity_id}|{normalized_predicate}|{start}:{end}" )
```

composed of, and only of:

| field | why it is in the key | failure mode if omitted / of the chosen form |
|---|---|---|
| `chunk_id` | provenance + locality; a claim belongs to exactly one source chunk | omitting it would merge identical sentences spoken on different days |
| `speaker_entity_id` (canonical) | distinguishes two speakers making a similar statement in one chunk | raw label would split one speaker across alias spellings; we use the resolved canonical id, so alias variants collapse correctly |
| `normalized_predicate` (lowercased, whitespace-collapsed) | the assertion itself | raw predicate text would mint a new id on trivial reformatting; normalizing absorbs that. (Extractions are cached, so within one model/prompt the bytes are already stable — normalization is belt-and-suspenders for cross-reformat stability) |
| quote span `start:end` (offsets, not text) | distinguishes two genuinely distinct claims by the same speaker with the same predicate but different evidence | quote *text* would collapse two identical-text quotes at different positions into one claim; offsets are stable because `chunk_id` is the hash of the chunk text, so `find_quote` is deterministic given the chunk |

A claim is only written if its speaker resolves (so `speaker_entity_id` exists) and its
quote is recoverable by `find_quote` (so `start:end` exists). Claims failing either are
**skipped, counted, and logged** — never written with a fabricated speaker or quote, and
never silently dropped (see "Surfaced, not dropped" below).

`status` is set by the writer via `ON CREATE SET cl.status = 'alleged'` — a Cypher
literal, never sourced from model output (the schema has no `status` field). `ON CREATE`
(not plain `SET`) is deliberate: it makes the writer the authority for the *initial*
status only, so re-running `build-graph` never clobbers a later human-review status change
(e.g. `corroborated`). The same applies to all claim properties.

## Decision 2 — raw-subject fallthrough policy

A claim's `subject_refs`/`object_refs` point at chunk-local entities whose verbatim
surface may or may not resolve against the human-owned `seed_entities.yaml`. The eval
found 187 raw (unresolved) fragments corpus-wide; the claim layer must define what
happens to a subject that does not resolve.

**Chosen: option (b) — record the raw surface on the `:Claim` node, no edge, flagged and
counted.** Resolved subjects/objects get `(:Claim)-[:MENTIONS {role}]->(:Person|:Org|
:Place)`. Unresolved ones are stored as node properties:

- `unresolved_subjects: [<verbatim surface>, …]` and `has_unresolved_subject: bool`
- `unresolved_objects: [<verbatim surface>, …]`

Rejected alternatives:

- **(a) a `:RawSubject`/`:Mention` node per surface.** Rejected: it proliferates one node
  per unresolved fragment (187+), and — worse — invites exactly the forbidden
  surname-only merge the canonical resolver exists to prevent (someone later `MATCH`-ing
  and merging two `KHUMALO` raw nodes). Inert claim-property data carries no such
  temptation.
- **(c) a held/review state blocking the claim from loading.** Rejected: the claim text
  and its resolved subjects are still evidence worth loading; withholding the whole claim
  over a partially-unresolved subject loses signal. Partial resolution is handled
  per-subject instead.

**Hard constraint satisfied.** A damaging allegation is never silently detached from the
named individual it is about: the verbatim surface travels *on the claim itself*, so the
claim is always answerable to "who/what was this about." It is:

- **countable** — `MATCH (c:Claim) WHERE c.has_unresolved_subject RETURN count(c)`, and
  `write_claims` returns `claims_with_unresolved_subject` / `unresolved_subject_refs`;
- **surfaceable** — the canary's Tier 3 packet selects every `has_unresolved_subject`
  claim, and the human-review queue (§8 step 6) keys on the same flag.

**Human-review interaction.** Resolving a raw subject is the existing human-owned loop:
add the alias to `seed_entities.yaml`, re-run `build-graph`. On re-run the surface now
resolves → a `MENTIONS` edge is created and the writer no longer adds the surface to
`unresolved_subjects`. (Because claim properties use `ON CREATE SET`, clearing the flag on
an existing claim is a follow-up review action, not an automatic side effect — noted as a
known limitation; the flag is advisory and the live edge is the source of truth.)

**Operative rule (not just a limitation).** `has_unresolved_subject` /
`unresolved_subjects` are written `ON CREATE` and are **advisory**. After a seed alias
lands (pre-step A), an existing claim's `MENTIONS {role:'subject'}` edge becomes correct on
the next `build-graph`, but its `has_unresolved_subject` flag can remain **stale-true** (it
was set when the claim node was first created and is never re-written). Therefore:

> Any query that gates publication, review, or "is this allegation attached to its named
> subject?" MUST read the `MENTIONS` edge — never the `has_unresolved_subject` flag.

The flag is only a *triage hint* for assembling the review queue / Tier 3 packet; the
edge is the source of truth. (A later review action may reconcile stale flags, but no
correctness decision may depend on the flag.)

**Canary note.** Because policy (b) creates *no* raw nodes, the canary's per-type
idempotency breakdown has no "raw subject node" type to count — that count is structurally
0 by design, and the unresolved-subject signal is the `claims_with_unresolved_subject`
count instead. The canary Tier 2 wording should read the count, not look for raw nodes.

## Consequences

- `:Claim` carries: `claim_id`, `text` (the predicate), `status="alleged"`,
  `attribution` (verbatim speaker label), `extraction_method`
  (`"<model>:<prompt_version>"`), `quote` + `quote_start`/`quote_end`, `certainty` (the
  speaker's own hedging, verbatim-ish or null), `has_unresolved_subject`,
  `unresolved_subjects`, `unresolved_objects`.
- **`confidence` is intentionally unset at this layer.** The `extract_v1` pass emits no
  per-claim confidence; `certainty` (the speaker's hedging) is stored instead. A numeric
  `confidence` is reserved for a later calibrated/human pass — the writer does not
  fabricate one.
- Provenance is structural: `write_claims` `MATCH`es the `:Chunk` (it must already exist
  from the spine pass), so a `:Claim` cannot be created detached from its provenance
  chunk; reachability `Claim -SUPPORTED_BY-> Chunk -(spine)-> Commission` is guaranteed.
- Subject/object refs use one `MENTIONS` edge per (claim, canonical entity), carrying
  `role: "subject" | "object"`; subjects are processed first so a dual-role entity is
  recorded as `subject`.
- Banned by construction: no fact-edges, no `APPEARS_IN`, no claim wired to a subject
  bypassing the `:Claim` node (`MENTIONS` originates at the claim).
