from core_engine.lyrics.parsers import parse_lrc, parse_srt
from core_engine.lyrics.playback_sync import LyricPlaybackSynchronizer


def test_state_before_first_line_has_next_line():
    timeline = parse_lrc("[00:01.000]A\n[00:02.000]B")
    sync = LyricPlaybackSynchronizer(timeline)

    state = sync.state_at(500)

    assert state.current_index is None
    assert state.current_text == ""
    assert state.next_line is not None
    assert state.next_line.text == "A"


def test_state_at_current_line_returns_neighbors_and_progress():
    timeline = parse_lrc("[00:01.000]A\n[00:03.000]B\n[00:05.000]C")
    sync = LyricPlaybackSynchronizer(timeline)

    state = sync.state_at(2_000)

    assert state.current_index == 0
    assert state.current_text == "A"
    assert state.previous_line is None
    assert state.next_line is not None
    assert state.next_line.text == "B"
    assert state.line_progress == 0.5


def test_state_applies_offset():
    timeline = parse_lrc("[00:01.000]A\n[00:02.000]B")
    sync = LyricPlaybackSynchronizer(timeline, offset_ms=500)

    state = sync.state_at(2_200)

    assert state.current_index == 0
    assert state.current_text == "A"


def test_state_uses_srt_end_time_for_progress():
    timeline = parse_srt("1\n00:00:01,000 --> 00:00:05,000\nLong line\n")
    sync = LyricPlaybackSynchronizer(timeline)

    state = sync.state_at(3_000)

    assert state.current_text == "Long line"
    assert state.line_progress == 0.5


def test_empty_timeline_returns_empty_state():
    sync = LyricPlaybackSynchronizer(parse_lrc(""))

    state = sync.state_at(1000)

    assert state.current_index is None
    assert state.current_line is None
    assert state.next_line is None
    assert state.current_text == ""

