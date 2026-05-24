import numpy as np

from core_engine.dsp.tone_deaf import (
    ToneDeafConfig,
    estimate_f0_track,
    generate_drift_curve,
    render_tone_deaf_vocal,
    split_frequency_bands,
)


def test_render_tone_deaf_vocal_preserves_shape_and_changes_signal():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]

    rendered = render_tone_deaf_vocal(
        vocal,
        sample_rate,
        ToneDeafConfig(drift_ratio=0.5, random_seed=1),
    )

    assert rendered.shape == vocal.shape
    assert rendered.dtype == np.float32
    assert float(np.mean(np.abs(rendered - vocal))) > 0.0001
    assert float(np.max(np.abs(rendered))) <= 0.96


def test_render_tone_deaf_vocal_controls_loud_source_peaks():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.95 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]

    rendered = render_tone_deaf_vocal(
        vocal,
        sample_rate,
        ToneDeafConfig(drift_ratio=1.0, random_seed=2),
    )

    assert rendered.shape == vocal.shape
    assert float(np.max(np.abs(rendered))) <= 0.96


def test_render_tone_deaf_vocal_keeps_source_timbre_dominant():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (
        0.18 * np.sin(2.0 * np.pi * 220.0 * time)
        + 0.08 * np.sin(2.0 * np.pi * 440.0 * time)
        + 0.04 * np.sin(2.0 * np.pi * 660.0 * time)
    )[:, np.newaxis]

    rendered = render_tone_deaf_vocal(
        vocal,
        sample_rate,
        ToneDeafConfig(drift_ratio=1.0, random_seed=4),
    )

    _, vocal_high = split_frequency_bands(vocal, sample_rate, 2600.0)
    _, rendered_high = split_frequency_bands(rendered, sample_rate, 2600.0)
    high_correlation = float(np.corrcoef(vocal_high[:, 0], rendered_high[:, 0])[0, 1])
    assert high_correlation > 0.80
    assert float(np.mean(np.abs(rendered - vocal))) > 0.0001


def test_render_tone_deaf_vocal_is_audible_at_high_strength():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (
        0.18 * np.sin(2.0 * np.pi * 220.0 * time)
        + 0.07 * np.sin(2.0 * np.pi * 440.0 * time)
    )[:, np.newaxis]

    rendered = render_tone_deaf_vocal(
        vocal,
        sample_rate,
        ToneDeafConfig(drift_ratio=1.0, random_seed=5),
    )

    mean_delta = float(np.mean(np.abs(rendered - vocal)))
    assert mean_delta > 0.01


def test_estimate_f0_track_detects_sine_frequency():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]

    f0_track = estimate_f0_track(vocal, sample_rate, ToneDeafConfig(drift_ratio=0.4))
    voiced = f0_track.frequencies_hz[f0_track.frequencies_hz > 0.0]

    assert voiced.size > 10
    assert abs(float(np.median(voiced)) - 220.0) < 8.0


def test_generate_drift_curve_is_deterministic_and_bounded():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    config = ToneDeafConfig(drift_ratio=0.5, random_seed=123)
    f0_track = estimate_f0_track(vocal, sample_rate, config)

    first = generate_drift_curve(f0_track, config)
    second = generate_drift_curve(f0_track, config)

    np.testing.assert_allclose(first.cents, second.cents)
    assert float(np.max(np.abs(first.cents))) <= 360.0
