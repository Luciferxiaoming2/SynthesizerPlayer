import numpy as np

from core_engine.player.sync_buffer import (
    StereoTrackBuffer,
    align_by_frame_count,
    ensure_2d_float32,
    mix_aligned_tracks,
)


def test_ensure_2d_float32_promotes_mono():
    audio = ensure_2d_float32(np.array([0.0, 0.5, -0.5]))

    assert audio.dtype == np.float32
    assert audio.shape == (3, 1)


def test_align_by_frame_count_pads_shorter_track():
    vocal = np.ones((2, 1), dtype=np.float32)
    instrumental = np.ones((4, 1), dtype=np.float32)

    aligned_vocal, aligned_instrumental = align_by_frame_count(vocal, instrumental, mode="pad")

    assert aligned_vocal.shape == (4, 1)
    assert aligned_instrumental.shape == (4, 1)
    np.testing.assert_array_equal(aligned_vocal[2:], np.zeros((2, 1), dtype=np.float32))


def test_align_by_frame_count_matches_mono_to_stereo():
    vocal = np.ones((3, 1), dtype=np.float32)
    instrumental = np.ones((3, 2), dtype=np.float32)

    aligned_vocal, aligned_instrumental = align_by_frame_count(vocal, instrumental)

    assert aligned_vocal.shape == (3, 2)
    assert aligned_instrumental.shape == (3, 2)


def test_mix_aligned_tracks_clips_output():
    buffers = StereoTrackBuffer(
        vocal=np.full((4, 1), 0.75, dtype=np.float32),
        instrumental=np.full((4, 1), 0.75, dtype=np.float32),
        sample_rate=48_000,
    )

    mixed = mix_aligned_tracks(buffers)

    assert mixed.dtype == np.float32
    np.testing.assert_array_equal(mixed, np.ones((4, 1), dtype=np.float32))

