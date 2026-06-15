# Pre-flight canary (v2) — spec / acceptance test for the claim layer

This is the canary **prompt/spec**, version-controlled so the acceptance test for the
`:Claim` writer (ADR 0005) and pre-steps A/B is reproducible. It is the gate between the
built-and-verified claim path and `extract-corpus --all`. Running it produces
`reports/preflight_canary.md`. **This spec does not authorise running `--all`.**

Tier-2 subject wording matches **ADR 0005 policy (b)** (raw subjects recorded on the
claim, no raw nodes). Tier-1 framing reuses cached Gate 2 judgments on overlap and judges
net-new only. Tier-2 idempotency is reported per node/edge type.

---

TASK: Pre-flight canary (v2) — exercise the full extraction → claim-load path on a
representative slice, assert extraction AND subject-edge invariants, gate --all on GREEN.

CONTEXT
Model settled (Haiku --all, ~$40, ADR <number>). Pre-steps A and B accepted. The
claim-extraction-and-load path has NEVER run on real data: M3 loaded zero :Claim nodes,
so the entire claim writer — STATED_BY, SUPPORTED_BY, status="alleged", the subject-edge
writer, AND its raw-fragment fallthrough policy (ADR 0005 policy (b)) — is exercised here
for the first time. This prompt runs a canary and emits a pass/fail report. It does NOT
run --all.

RUN ORDER: after pre-steps A and B. Do not start until both are accepted.

ISOLATION
   - Run the canary against a THROWAWAY Neo4j instance (separate container/volume), not a
     labelled namespace in the production DB. Reason: the canary validates claim-dedup
     idempotency; using claim-dedup to clean up that same test inside the constrained
     production spine is circular. A throwaway instance is dropped whole. Apply the same
     constraints.cypher to it so uniqueness behaviour is realistic.

CACHE-VERSION GUARD (first)
   - If A or B touched the extraction prompt, bump prompt_version deliberately and note it.
     If unchanged, the 40 Gate 2 chunks must be cache hits in Tier 0; if not, STOP.

CANARY SLICE
   - Days 36 and 43. NOTE these are Gate 2 slice days (metrics.json slice_days=[36,43,66]),
     so a large fraction of the slice overlaps the evaluated 40 chunks. This overlap is
     used deliberately in Tier 0/Tier 1 but must be partitioned out of the generalization
     checks.
   - Partition the slice into OVERLAP chunks (in the seed-17 sample) and NET-NEW chunks
     (not previously evaluated). Record both counts. Net-new is the real generalization test.

TIER 0 — regression vs evaluated path ($0, exact)
   - Re-run extract-corpus over the 40 Gate 2 chunks through the PRODUCTION path, Haiku.
   - ASSERT all 40 are cache hits AND output is byte-identical to the cached Gate 2
     extractions. (Validates the production CLI and eval harness compute the same cache
     key.) FAIL = hard stop.

TIER 1 — extraction invariants on the canary slice (Haiku batch + Opus judge)
   BUDGET: Haiku extraction over net-new chunks = a few dollars. framing_judge is OPUS and
   runs over NET-NEW CLAIMS ONLY (overlap reuses cached Gate 2 flags, below), so state the
   projected judge cost against the net-new claim count and log actual to spend.jsonl.
   Assert over the JSON:
   - NO SILENT LOSS: chunks_in == extractions_out + dead_letters. Print the equation.
   - DEAD-LETTERS READ IN FULL: dump every dead-letter; flag any refusal on allegation
     content explicitly.
   - QUOTES RECOVER: find_quote() non-None for every claim; list every None with chunk_id.
     (NB the claim writer already drops + counts these as quote_unrecovered — cross-check
     the writer's count against this list.)
   - ATTRIBUTION (pre-step B): run commission_ingestion.eval.attribution.validate over the
     slice and emit format_report. The attribution invariant is the bucket-1 (MODEL-WRONG)
     rate ONLY — model_wrong / comparable (match + model_wrong). Buckets 2 and 3 are
     reported and explained, NEVER folded into the rate:
       · bucket 2 PARSER-GAP: absorbed COMMISSIONER <surname> turns (Mkhwanazi, Spies,
         Faro, Bolhuis, Malatji) that turns.py LABEL_RE cannot see — model right, parser
         wrong. Attributable to the post-canary turns.py re-chunk milestone; NOT a model
         error and NOT a canary RED. (On the 40-chunk sample post-A: 34, all jd-mkhwanazi.)
       · bucket 3 QUOTE-UNRECOVERABLE: find_quote None — the Tier-1 quote gate; cross-check
         against the claim writer's quote_unrecovered count. (On the sample: 7.)
     List every bucket-1 instance for the Tier 3 packet. Note that some bucket-1 cases are
     "quote straddles an absorbed boundary" (model named the absorbed substantive speaker,
     quote starts in the absorbing counsel turn) — these are for human adjudication and
     will resolve once turns.py lands. (On the sample post-A: bucket-1 = 5, rate ≈ 0.051.)
   - FRAMING, PARTITIONED: OVERLAP claims reuse the RECORDED Gate 2 framing flags — do NOT
     re-judge them. (Extraction is byte-identical on overlap per Tier 0, so the claims fed
     to the judge are identical; reusing the recorded flags makes the overlap check exact
     and independent of judge determinism.) Run framing_judge ONLY on NET-NEW claims.
     Compute the asserted-as-fact drift tolerance against the NET-NEW claim count; because
     that n is large, set a TIGHTER tolerance than ≤~7% (propose one justified by the
     net-new n). List every asserted_as_fact claim (overlap-recorded + net-new-judged) for
     Tier 3.

TIER 2 — graph invariants after loading the slice into the throwaway Neo4j (Cypher)
   Include every query and its count in the report.
   SPEAKER SIDE:
   - Every :Claim has exactly one STATED_BY :Person and ≥1 SUPPORTED_BY :Chunk.
   - Every :Claim has status="alleged"; any other status counted, must be 0.
   - FLOOR: report count(:Claim) with NO STATED_BY. This must be 0 (the writer skips
     speaker-unresolved claims before they become nodes); a nonzero count means pre-step A
     did not cover the slice's speaker labels — investigate before proceeding.
   SUBJECT SIDE (ADR 0005 policy (b) — no raw nodes; do NOT look for "raw subject nodes",
   that check is vacuous):
   - For every claim, every subject_ref EITHER resolves to a canonical :Person/:Org/:Place
     via (:Claim)-[:MENTIONS {role:'subject'}]->(entity), OR is recorded in the claim's
     unresolved_subjects property with has_unresolved_subject=true. A claim with NEITHER
     (a subject that is silently absent) is RED. Count claims with neither; must be 0.
   - Report claims_with_unresolved_subject (the count of claims carrying ≥1 raw subject).
     This is EXPECTED NONZERO and is NOT asserted to 0 — instead every such claim is
     ENUMERATED into the Tier 3 packet for human read.
   - CROSS-CHECK: the graph's count of claims with has_unresolved_subject=true ==
     write_claims()'s logged claims_with_unresolved_subject for the slice. A mismatch
     means a load-vs-resolution discrepancy — RED.
   - PUBLICATION/REVIEW queries read the MENTIONS edge, never has_unresolved_subject (the
     flag is ON CREATE and may be stale-true after a later seed alias; ADR 0005 operative
     rule).
   BANNED + PROVENANCE:
   - Zero banned fact-edge types (count 0). No claim wired directly to a subject bypassing
     the :Claim node (MENTIONS originates at the claim).
   - No APPEARS_IN anywhere.
   - Full provenance from every :Claim: SUPPORTED_BY -> :Chunk -> (spine) ->
     commission -> day -> document -> sha256 -> page -> chunk; claims missing any hop
     must be 0.
   IDEMPOTENCY (per-type, not blanket):
   - build-graph the slice TWICE; report run-1 vs run-2 counts BROKEN DOWN by type:
     :Claim nodes, STATED_BY edges, SUPPORTED_BY edges, MENTIONS (subject) edges,
     MENTIONS (object) edges.
   - Assert each pair identical. A doubling LOCALIZES the non-idempotent writer rather
     than pre-attributing cause:
       :Claim doubling        -> non-deterministic :Claim MERGE-key (schema fix)
       MENTIONS doubling      -> non-deterministic entity key / role handling (separate fix)
   - These are INDEPENDENT defects. The report MUST NOT collapse them. A fix is proven
     ONLY by a full green Tier 2 re-run from scratch — never by re-checking the single
     assertion that was edited.

TIER 3 — human read (defamation gate, not self-certified)
   Review packet of ~25 claims on the highest-stakes named individuals (Khumalo cluster,
   Matlala, the two Mkhwanazis — distinguish person:jd-mkhwanazi (EMPD) from
   person:nhlanhla-mkhwanazi (KZN), Sibiya), PLUS every asserted_as_fact claim, every
   attribution mismatch (incl. the COMMISSIONER-witness parser class), AND every
   claim with has_unresolved_subject=true from Tier 2. For each: claim text, framing flag,
   STATED_BY, subject resolution (canonical id(s) + any raw surfaces), verbatim source
   quote, chunk deep-link. DELIVERABLE for human sign-off; agent does not self-certify.

DELIVERABLES
   - reports/preflight_canary.md: slice + overlap/net-new partition, Tier 0–2 assertions
     with pass/fail and actual counts, all Cypher, the Tier 3 packet, and separate
     Haiku/Opus spend.
   - The idempotency result is reported PER TYPE (:Claim / STATED_BY / SUPPORTED_BY /
     MENTIONS-subject / MENTIONS-object), each pass/fail independently. A doubling in ANY
     type is RED and names its own writer.
   - Top-line VERDICT: GREEN (all automated tiers pass, Tier 3 packet ready) or RED
     (enumerate failures). A subject silently absent (neither MENTIONS nor recorded), a
     :Claim with no STATED_BY, or a doubling in any idempotency type is RED.
   - Throwaway Neo4j instance dropped after assertions.

ACCEPTANCE CRITERIA
   - Tier 0 and Tier 2 pass; Tier 1 reported with explicit numbers, partitioned overlap vs
     net-new; Tier 3 packet generated; total spend (Haiku + Opus) stated.
   - git diff limited to reports/ and scratch/test scaffolding.

GATE
   extract-corpus --all is BLOCKED until VERDICT is GREEN and a human signs off the Tier 3
   packet. This prompt must not run --all.

NEXT PROMPT (do not execute)
   Run extract-corpus --all (Haiku, batch, ~$40 cap) — gated on GREEN + human Tier 3 sign-off.
