from core_engine.lyrics.parsers import parse_lrc, parse_srt


def test_parse_lrc_supports_three_digit_milliseconds():
    timeline = parse_lrc("[00:00.042]Title\n[01:02.30]Line")

    lines = timeline.lines
    assert lines[0].start_ms == 42
    assert lines[0].text == "Title"
    assert lines[1].start_ms == 62_300


def test_parse_srt_reads_start_end_and_text():
    timeline = parse_srt("1\n00:00:01,500 --> 00:00:03,250\nHello\nworld\n")

    lines = timeline.lines
    assert lines[0].start_ms == 1_500
    assert lines[0].end_ms == 3_250
    assert lines[0].text == "Hello world"


def test_timeline_line_at_applies_offset():
    timeline = parse_lrc("[00:01.000]A\n[00:02.000]B")

    assert timeline.line_at(2_200, offset_ms=500) == 0
    assert timeline.line_at(2_600, offset_ms=500) == 1

