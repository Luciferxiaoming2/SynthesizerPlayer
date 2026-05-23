from harness.cli_harness.run_playback import apply_playback_command, parse_bool
from core_engine.player.playback_engine import DualTrackPlaybackEngine
from core_engine.player.sync_buffer import StereoTrackBuffer
import numpy as np


def make_buffers() -> StereoTrackBuffer:
    vocal = np.ones((8, 1), dtype=np.float32)
    instrumental = np.full((8, 1), 0.5, dtype=np.float32)
    return StereoTrackBuffer(vocal=vocal, instrumental=instrumental, sample_rate=4)


def test_parse_bool_accepts_on_and_off():
    assert parse_bool("on")
    assert not parse_bool("off")


def test_apply_playback_command_controls_engine():
    engine = DualTrackPlaybackEngine(make_buffers())

    keep_running, message = apply_playback_command(engine, "play")
    assert keep_running
    assert message == "playing"
    assert engine.is_playing

    apply_playback_command(engine, "seek 1.0")
    assert engine.position_frames == 4

    apply_playback_command(engine, "gain vocal 0.25")
    assert engine.controls.vocal_gain == 0.25

    apply_playback_command(engine, "mute instrumental on")
    assert engine.controls.instrumental_muted

    keep_running, message = apply_playback_command(engine, "quit")
    assert not keep_running
    assert message == "stopping"
