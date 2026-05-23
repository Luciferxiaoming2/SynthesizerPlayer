import numpy as np

from core_engine.player.playback_engine import DualTrackPlaybackEngine, TrackControls
from core_engine.player.sync_buffer import StereoTrackBuffer


def make_buffers() -> StereoTrackBuffer:
    vocal = np.ones((8, 1), dtype=np.float32)
    instrumental = np.full((8, 1), 0.5, dtype=np.float32)
    return StereoTrackBuffer(vocal=vocal, instrumental=instrumental, sample_rate=4)


def test_render_block_returns_silence_while_paused():
    engine = DualTrackPlaybackEngine(make_buffers())

    block = engine.render_block(4)

    np.testing.assert_array_equal(block, np.zeros((4, 1), dtype=np.float32))
    assert engine.position_frames == 0


def test_render_block_advances_while_playing():
    engine = DualTrackPlaybackEngine(make_buffers())
    engine.play()

    block = engine.render_block(3)

    np.testing.assert_array_equal(block, np.full((3, 1), 1.0, dtype=np.float32))
    assert engine.position_frames == 3
    assert engine.is_playing


def test_render_block_pads_tail_and_stops():
    engine = DualTrackPlaybackEngine(make_buffers())
    engine.play()
    engine.seek_frames(6)

    block = engine.render_block(4)

    np.testing.assert_array_equal(
        block,
        np.array([[1.0], [1.0], [0.0], [0.0]], dtype=np.float32),
    )
    assert engine.position_frames == 8
    assert not engine.is_playing


def test_controls_support_solo_and_mute():
    engine = DualTrackPlaybackEngine(make_buffers(), TrackControls(vocal_solo=True))
    engine.play()

    vocal_only = engine.render_block(2)

    np.testing.assert_array_equal(vocal_only, np.ones((2, 1), dtype=np.float32))

    engine.seek_frames(0)
    engine.play()
    engine.set_controls(vocal_muted=True, vocal_solo=False, instrumental_gain=0.5)
    instrumental_only = engine.render_block(2)

    np.testing.assert_array_equal(instrumental_only, np.full((2, 1), 0.25, dtype=np.float32))


def test_snapshot_reports_stable_playback_state():
    engine = DualTrackPlaybackEngine(make_buffers())
    engine.seek_seconds(1.0)
    engine.set_gains(vocal_gain=0.25)
    engine.play()

    snapshot = engine.snapshot()

    assert snapshot.position_frames == 4
    assert snapshot.position_seconds == 1.0
    assert snapshot.duration_seconds == 2.0
    assert snapshot.is_playing
    assert snapshot.controls.vocal_gain == 0.25


def test_set_mute_and_set_solo_helpers_update_controls():
    engine = DualTrackPlaybackEngine(make_buffers())

    engine.set_mute(vocal_muted=True)
    engine.set_solo(instrumental_solo=True)

    assert engine.controls.vocal_muted
    assert engine.controls.instrumental_solo


def test_negative_gain_is_rejected():
    engine = DualTrackPlaybackEngine(make_buffers())

    try:
        engine.set_gains(vocal_gain=-0.1)
    except ValueError as exc:
        assert "vocal_gain" in str(exc)
    else:
        raise AssertionError("negative vocal_gain should fail")
