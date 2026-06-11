# Parse notes — Madlanga transcript format

What the M1 parser relies on, verified against all 108 downloaded Madlanga
transcripts (PyMuPDF). Read this before changing `parsing/`.

## Verified facts

- **Born-digital, not scanned.** 0 of 108 are image-only (mean ~1,300 chars/page;
  18,485 PDF pages). `is_scanned()` (mean < 100 chars/page) is a defensive guard, not
  an expected path.
- **Speaker labels** are line-initial, UPPERCASE, colon-terminated:
  `CHAIRPERSON:`, `COMMISSIONER:`, `ADV CHASKALSON SC:`, `MR MOGOTSI:`,
  `LT-GEN SIBIYA:`. Detected by **positive vocabulary** (title prefix / role /
  examination heading), not "any uppercase + colon".
- **Per-page furniture** (stripped, line-by-line, before reflow):
  - leading blank lines,
  - running header `<DAY-DATE> – DAY <N>` (e.g. `19 NOVEMBER 2025 – DAY 36`),
  - page marker `Page N of M`.
- **Cover page** (PDF page 1) carries the title block / venue, no `Page N of M`,
  and yields no turns.

## Hazards handled

1. **Margin line-number tokens** — the "every 10th line" numbers (`10`, `20`, …)
   extract as their own lines, interleaved mid-sentence (~37k corpus-wide). Dropped
   as standalone numeric lines **before** reflow, so they never land inside turn text.
   (Numbers that appear *in speech* — "pages 87 to 91", "File 2 of 3" — are untouched.)
2. **One-word-per-line fragmentation** — PyMuPDF emits one word per line on some
   pages, fragmenting both sentences and speaker labels. We therefore **strip
   furniture line-by-line, then reflow** surviving lines into one whitespace-collapsed
   stream and segment on that, keeping a per-character map back to the PDF page.
3. **Examination headings** (`EXAMINATION IN CHIEF BY ADV X (CONTINUES):`) are real
   turn boundaries; the label is normalised to the named counsel (`ADV X`).
4. **Label spelling drift** — `SEGEELS -NCUBE` → `SEGEELS-NCUBE`, `LT GEN` →
   `LT-GEN`. Normalised in `normalise_label()`.

## Decisions

- **`chunk_id = sha256(doc_sha256 : chunk_index : text)`**, not `sha256(text)`.
  Identical short turns ("Thank you, Chair.") recur across the corpus; a text-only
  hash collides (187 collisions observed), which would break `chunk_id` as a unique
  key in Qdrant/Neo4j. The chosen key is unique *and* deterministic (idempotent).
- **Oversized turns are split** on sentence boundaries so no chunk exceeds
  `CHUNK_MAX_CHARS` (1800) — some witnesses read long passages into the record
  (12k-char turns exist). Normal turns are never split; consecutive turns are packed.
- **Page numbers recorded are the 1-based PDF page index.** The printed "Page N of M"
  runs one behind (cover page); treat it as a cross-check, not the stored value.

## Data-quality verification (2026-06-11, before Post #1)

- **No scanned docs slipped through.** 0 of 108 parsed transcripts are image-only;
  the parse manifest is 108/108 `ok` (no `needs_ocr`, no errors).
- **Near-zero-page days are real short sittings, not parse failures.** Every day under
  ~30 pages was checked: Day 10 (2pp, postponement — "Khumalo is not at his seat"),
  Day 110 (2pp, a ruling), Days 11/13/39/61/67/70/100 (short procedural sittings, all
  with multiple parsed turns). None are parse failures.
- **The marathon day is genuine.** Day 43 ("…Day 43 Full.pdf", 462pp) has printed page
  markers running 1→461 monotonically with a single "of 462" — a real single transcript,
  not a doubled/combined upload.
- **Day-count reconciliation (state precisely in any published copy):**
  **106 distinct hearing days** parsed across **108 transcript documents** (Days 15 and
  80 each have two parts). The Commission has sat to **Day 110**. Day numbers not parsed:
  **4, 6, 14, 104** — Day 6 is a permanent 404 at source; 4/14/104 are absent from the
  public record. 109 transcript records exist in the registry (108 downloaded).

## Known limits (deferred)

- **Title ≠ role.** "ADV BEHARI" can be the *witness*, not counsel. Role/word-share
  attribution (Post #1) needs a small per-day witness map — a stats-layer concern, not
  parsing.
- **`SC` suffix is inconsistent** (`ADV X` vs `ADV X SC`). Recorded faithfully;
  speaker canonicalisation belongs with M3 alias resolution.
- **Short days are real.** Days 10/61/110 etc. parse to 1–3 chunks because they were
  postponements or short rulings, not parse failures.
