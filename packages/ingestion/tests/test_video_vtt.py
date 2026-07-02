"""WebVTT parsing, rolling dedupe, and time-provenance segmenting."""

from commission_ingestion.video.vtt import (
    CaptionCue,
    dedupe_rolling,
    parse_timestamp,
    parse_vtt,
    segment_cues,
)

PLAIN_VTT = """\
WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500
Good morning, Chair.

00:00:03.500 --> 00:00:07.000
We begin with the evidence of the witness.

1:02:03.250 --> 1:02:05.000
Thank you.
"""

# YouTube auto-caption shape: cue settings after the end timestamp, inline
# word-timing tags, and rolling repetition (each cue re-shows the last line).
AUTO_VTT = """\
WEBVTT
Kind: captions
Language: en

00:00:00.320 --> 00:00:02.879 align:start position:0%
 
good<00:00:00.560><c> morning</c><00:00:01.199><c> chair</c>

00:00:02.879 --> 00:00:05.190 align:start position:0%
good morning chair
the<00:00:03.040><c> commission</c><00:00:03.360><c> resumes</c>

00:00:05.190 --> 00:00:07.910 align:start position:0%
the commission resumes
day<00:00:05.759><c> one</c><00:00:06.480><c> thirty</c>
"""


def test_parse_timestamp_forms():
    assert parse_timestamp("00:00:01.000") == 1.0
    assert parse_timestamp("01:02:03.250") == 3723.25
    assert parse_timestamp("02:03.250") == 123.25
    assert parse_timestamp("nonsense") is None


def test_parse_plain_vtt():
    cues = parse_vtt(PLAIN_VTT)
    assert [c.text for c in cues] == [
        "Good morning, Chair.",
        "We begin with the evidence of the witness.",
        "Thank you.",
    ]
    assert cues[0].start == 1.0
    assert cues[0].end == 3.5
    assert cues[2].start == 3723.25


def test_parse_auto_vtt_strips_tags():
    cues = parse_vtt(AUTO_VTT)
    assert cues[0].text == "good morning chair"
    assert "<c>" not in " ".join(c.text for c in cues)


def test_dedupe_rolling_removes_repeated_lines():
    cues = dedupe_rolling(parse_vtt(AUTO_VTT))
    joined = " ".join(c.text for c in cues)
    assert joined.count("good morning chair") == 1
    assert joined.count("the commission resumes") == 1
    assert "day one thirty" in joined


def test_dedupe_passes_manual_captions_through():
    cues = parse_vtt(PLAIN_VTT)
    assert dedupe_rolling(cues) == cues


def test_segment_cues_packs_and_keeps_time_range():
    cues = [
        CaptionCue(start=float(i), end=float(i) + 0.9, lines=(f"utterance {i:03d}",))
        for i in range(10)
    ]
    segments = segment_cues(cues, max_chars=40)
    assert all(s.char_count <= 40 for s in segments)
    assert segments[0].time_start == 0.0
    assert segments[-1].time_end == 9.9
    # every cue's text survives, in order
    assert " ".join(s.text for s in segments) == " ".join(c.text for c in cues)


def test_segment_cues_never_splits_a_cue():
    long_cue = CaptionCue(start=0.0, end=5.0, lines=("x" * 100,))
    segments = segment_cues([long_cue], max_chars=40)
    assert len(segments) == 1
    assert segments[0].text == "x" * 100
