"""Tests for the M1 parsing pipeline: extract -> clean/reflow -> turns -> chunks."""

from __future__ import annotations

from pathlib import Path

import fitz

from commission_ingestion.parsing.chunking import CHUNK_MAX_CHARS, chunk_turns
from commission_ingestion.parsing.clean import clean_page_lines, reflow_pages
from commission_ingestion.parsing.pdf import PageText, extract_pages, is_scanned
from commission_ingestion.parsing.turns import Turn, detect_turns, normalise_label


# Synthetic page text mirroring the real Madlanga layout: leading blanks, a
# running header, a "Page N of M" marker, interleaved line-number tokens, and
# PyMuPDF-style one-word-per-line fragmentation.
PAGE_1 = (
    " \n \n \n19 NOVEMBER 2025 – DAY 36 \n \nPage 1 of 2 \n \n"
    "PROCEEDINGS ON 19 NOVEMBER 2025 \n \n"
    "CHAIRPERSON:   Good afternoon. \n"
    "ADV CHASKALSON SC:   Thank you, Chair.  Mr Mogotsi, I \n10 \n"
    "want to ask you about the \nstatement. \n"
    "MR MOGOTSI:   That is correct. \n"
)
PAGE_2 = (
    " \n \n \n19 NOVEMBER 2025 – DAY 36 \n \nPage 2 of 2 \n \n"
    "continuing the answer here. \n"
    "ADV CHASKALSON SC:   Next question. \n"
)


def _doc():
    return reflow_pages([PageText(1, PAGE_1, len(PAGE_1)), PageText(2, PAGE_2, len(PAGE_2))])


def test_furniture_and_line_numbers_stripped():
    lines = clean_page_lines(PAGE_1)
    assert "10" not in lines  # margin line-number token
    assert not any("Page 1 of 2" in ln for ln in lines)
    assert not any("DAY 36" in ln for ln in lines)


def test_reflow_drops_line_number_from_body_and_spans_pages():
    turns = detect_turns(_doc())
    speakers = [t.speaker for t in turns]
    assert speakers == [
        "CHAIRPERSON",
        "ADV CHASKALSON SC",
        "MR MOGOTSI",
        "ADV CHASKALSON SC",
    ]
    chask = turns[1]
    assert "10" not in chask.text.split()  # line number not embedded mid-sentence
    assert "want to ask you about the statement." in chask.text  # fragmented lines rejoined

    mogotsi = turns[2]
    assert mogotsi.text == "That is correct. continuing the answer here."
    assert mogotsi.page_start == 1 and mogotsi.page_end == 2  # turn spans the page break


def test_examination_heading_normalises_to_named_counsel():
    doc = reflow_pages([PageText(1, "EXAMINATION IN CHIEF BY ADV SEGEELS -NCUBE:   Good morning. \n", 0)])
    turns = detect_turns(doc)
    assert len(turns) == 1
    assert turns[0].speaker == "ADV SEGEELS-NCUBE"


def test_label_spelling_normalised():
    assert normalise_label("LT GEN  SIBIYA") == "LT-GEN SIBIYA"
    assert normalise_label("ADV SEGEELS -NCUBE") == "ADV SEGEELS-NCUBE"


def test_procedural_line_is_not_a_turn():
    # All-caps, no colon -> must not be detected as a speaker turn.
    doc = reflow_pages([PageText(1, "MR MOGOTSI:   Yes. \nKEMRAH PREM BEHARI   (duly sworn states) \n", 0)])
    turns = detect_turns(doc)
    assert [t.speaker for t in turns] == ["MR MOGOTSI"]


def test_chunk_packing_groups_small_turns():
    turns = [Turn("CHAIRPERSON", "Short remark.", 1, 1) for _ in range(20)]
    chunks = chunk_turns(turns)
    assert all(c.char_count <= CHUNK_MAX_CHARS for c in chunks)
    assert sum(c.n_turns for c in chunks) == 20
    assert len(chunks) < 20  # multiple small turns packed together


def test_oversized_turn_split_on_sentences_same_speaker():
    body = "This is a sentence. " * 200  # ~4000 chars, one turn
    chunks = chunk_turns([Turn("ADV BEHARI", body.strip(), 5, 7)])
    assert len(chunks) > 1
    assert all(c.char_count <= CHUNK_MAX_CHARS for c in chunks)
    assert all(c.speakers == ["ADV BEHARI"] for c in chunks)
    assert all(c.page_start == 5 and c.page_end == 7 for c in chunks)


def test_extract_pages_and_scanned_detection(tmp_path: Path):
    pdf = tmp_path / "tiny.pdf"
    doc = fitz.open()
    body = "\n".join(
        f"CHAIRPERSON: Good morning, this is line {i} of the hearing record."
        for i in range(8)
    )
    for n in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {n + 1}\n{body}")
    doc.save(pdf)
    doc.close()

    pages = extract_pages(pdf)
    assert [p.page_no for p in pages] == [1, 2]  # 1-based
    assert "CHAIRPERSON" in pages[0].text
    assert not is_scanned(pages)
    # An image-only PDF would yield near-zero text per page:
    assert is_scanned([PageText(1, " ", 1), PageText(2, "", 0)])
