import numpy as np

from core_engine.dsp.tone_deaf import ToneDeafConfig
from core_engine.dsp.tone_deaf_cache import ToneDeafBufferCache
from core_engine.player.playback_engine import DualTrackPlaybackEngine
from core_engine.player.sync_buffer import StereoTrackBuffer


def make_buffers() -> StereoTrackBuffer:
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    instrumental = (0.1 * np.sin(2.0 * np.pi * 110.0 * time))[:, np.newaxis]
    return StereoTrackBuffer(vocal=vocal, instrumental=instrumental, sample_rate=sample_rate)


def test_tone_deaf_cache_reuses_rendered_vocal():
    buffers = make_buffers()
    cache = ToneDeafBufferCache()
    config = ToneDeafConfig(drift_ratio=0.4, random_seed=3)

    first = cache.render_vocal(buffers, config)
    second = cache.render_vocal(buffers, config)

    assert cache.size == 1
    np.testing.assert_allclose(first, second)


def test_tone_deaf_cache_separates_same_length_sources():
    first_buffers = make_buffers()
    second_buffers = first_buffers.with_vocal(first_buffers.vocal * 0.5)
    cache = ToneDeafBufferCache()
    config = ToneDeafConfig(drift_ratio=0.4, random_seed=3)

    cache.render_vocal(first_buffers, config)
    cache.render_vocal(second_buffers, config)

    assert cache.size == 2


def test_tone_deaf_render_buffer_preserves_alignment():
    buffers = make_buffers()
    rendered = ToneDeafBufferCache().render_buffer(
        buffers,
        ToneDeafConfig(drift_ratio=0.4, random_seed=3),
    )

    assert rendered.frame_count == buffers.frame_count
    assert rendered.sample_rate == buffers.sample_rate
    np.testing.assert_array_equal(rendered.instrumental, buffers.instrumental)


def test_playback_engine_can_replace_buffers_keep_position():
    buffers = make_buffers()
    engine = DualTrackPlaybackEngine(buffers)
    engine.seek_frames(100)
    rendered = ToneDeafBufferCache().render_buffer(
        buffers,
        ToneDeafConfig(drift_ratio=0.4, random_seed=3),
    )

    engine.replace_buffers(rendered)

    assert engine.position_frames == 100
    assert engine.buffers is rendered
