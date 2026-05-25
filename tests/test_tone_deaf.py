from pathlib import Path

import numpy as np

from core_engine.dsp.tone_deaf import (
    DriftCurve,
    ToneDeafConfig,
    estimate_f0_track,
    fit_audio_frame_count,
    generate_drift_curve,
    natural_phrase_offsets,
    rubberband_pitchmap_lines,
    rubberband_base_shift_semitones,
    rubberband_pitch_command,
    rubberband_quality_executable,
    render_tone_deaf_vocal,
    split_frequency_bands,
    suppress_vocal_bleed,
    suppress_vocal_bleed_spectral,
    write_rubberband_pitchmap,
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

    dry_similarity = float(np.corrcoef(vocal[:, 0], rendered[:, 0])[0, 1])
    assert dry_similarity < 0.995
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
    assert mean_delta > 0.018


def test_render_tone_deaf_vocal_avoids_dry_shifted_doubling():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (
        0.2 * np.sin(2.0 * np.pi * 220.0 * time)
        + 0.04 * np.sin(2.0 * np.pi * 3000.0 * time)
    )[:, np.newaxis]

    rendered = render_tone_deaf_vocal(
        vocal,
        sample_rate,
        ToneDeafConfig(drift_ratio=0.85, random_seed=8),
    )

    dry_similarity = float(np.corrcoef(vocal[:, 0], rendered[:, 0])[0, 1])
    assert dry_similarity < 0.98
    assert float(np.max(np.abs(rendered))) <= 0.96


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


def test_generate_drift_curve_uses_soft_human_transitions():
    sample_rate = 16_000
    time = np.arange(sample_rate * 3, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    config = ToneDeafConfig(drift_ratio=0.75, random_seed=44)
    f0_track = estimate_f0_track(vocal, sample_rate, config)

    curve = generate_drift_curve(f0_track, config)

    assert float(np.max(np.abs(np.diff(curve.cents)))) < 90.0
    assert float(np.max(np.abs(curve.cents))) > 60.0


def test_natural_phrase_offsets_are_not_rapid_mechanical_steps():
    times = np.linspace(0.0, 4.0, 201, dtype=np.float32)
    offsets = natural_phrase_offsets(
        times,
        300.0,
        np.random.default_rng(7),
        ToneDeafConfig(drift_ratio=1.0),
    )

    sign_changes = int(np.sum(np.diff(np.signbit(offsets)) != 0))
    assert sign_changes <= 6
    assert float(np.max(np.abs(np.diff(offsets)))) < 55.0


def test_rubberband_base_shift_gets_stronger_with_ratio():
    low = abs(rubberband_base_shift_semitones(ToneDeafConfig(drift_ratio=0.2, random_seed=7)))
    high = abs(rubberband_base_shift_semitones(ToneDeafConfig(drift_ratio=0.9, random_seed=7)))

    assert high > low
    assert high >= 2.0


def test_fit_audio_frame_count_matches_target_shape():
    audio = np.linspace(-0.5, 0.5, 10, dtype=np.float32)[:, np.newaxis]

    fitted = fit_audio_frame_count(audio, frame_count=16, channel_count=2)

    assert fitted.shape == (16, 2)
    assert fitted.dtype == np.float32


def test_rubberband_command_uses_formant_preservation(tmp_path):
    executable = tmp_path / "rubberband.exe"
    executable.write_text("fake", encoding="utf-8")
    r3_executable = tmp_path / "rubberband-r3.exe"
    r3_executable.write_text("fake", encoding="utf-8")

    command = rubberband_pitch_command(
        str(executable),
        -1.5,
        Path("in.wav"),
        Path("out.wav"),
        Path("pitchmap.txt"),
    )

    assert command[0] == str(r3_executable)
    assert "--formant" in command
    assert "--fine" in command
    assert "--centre-focus" not in command
    assert "--pitchmap" in command
    assert "--pitch" in command


def test_rubberband_quality_executable_falls_back_when_r3_missing(tmp_path):
    executable = tmp_path / "rubberband.exe"
    executable.write_text("fake", encoding="utf-8")

    assert rubberband_quality_executable(str(executable)) == str(executable)


def test_write_rubberband_pitchmap_contains_dynamic_offsets(tmp_path):
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    pitchmap = tmp_path / "pitchmap.txt"

    write_rubberband_pitchmap(
        vocal,
        sample_rate,
        ToneDeafConfig(drift_ratio=0.8, random_seed=9),
        -1.25,
        pitchmap,
    )

    lines = pitchmap.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 4
    assert lines[0].startswith("0 ")
    offsets = [float(line.split()[1]) for line in lines]
    assert max(offsets) - min(offsets) > 0.15


def test_rubberband_pitchmap_is_sparse_to_avoid_word_level_timbre_jumps():
    sample_rate = 16_000
    times = np.arange(0.0, 3.0, 0.02, dtype=np.float32)
    cents = (np.sin(times * np.pi * 2.0 * 4.0) * 95.0).astype(np.float32)
    lines = rubberband_pitchmap_lines(
        DriftCurve(times_seconds=times, cents=cents),
        sample_rate,
        frame_count=sample_rate * 3,
        base_semitones=-1.4,
    )

    frames = [int(line.split()[0]) for line in lines]
    assert len(lines) < 16
    assert all((right - left) >= round(sample_rate * 0.26) for left, right in zip(frames, frames[1:-1]))


def test_suppress_vocal_bleed_reduces_correlated_dry_vocal():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    accompaniment = (0.1 * np.sin(2.0 * np.pi * 110.0 * time))[:, np.newaxis]
    leaked = accompaniment + vocal * 0.45

    cleaned = suppress_vocal_bleed(leaked, vocal, strength=0.9)

    before = abs(float(np.dot(leaked[:, 0], vocal[:, 0])))
    after = abs(float(np.dot(cleaned[:, 0], vocal[:, 0])))
    assert after < before * 0.25
    assert cleaned.shape == leaked.shape


def test_suppress_vocal_bleed_preserves_uncorrelated_instrumental():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    instrumental = (0.1 * np.sin(2.0 * np.pi * 110.0 * time))[:, np.newaxis]

    cleaned = suppress_vocal_bleed(instrumental, vocal, strength=0.9)

    np.testing.assert_allclose(cleaned, instrumental, atol=1e-5)


def test_suppress_vocal_bleed_spectral_reduces_eq_changed_vocal_leak():
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    vocal = (
        0.18 * np.sin(2.0 * np.pi * 220.0 * time)
        + 0.09 * np.sin(2.0 * np.pi * 440.0 * time)
    )[:, np.newaxis]
    accompaniment = (0.1 * np.sin(2.0 * np.pi * 110.0 * time))[:, np.newaxis]
    delayed_leak = np.pad(vocal[:-17, 0], (17, 0))[:, np.newaxis] * 0.38
    eq_changed_leak = delayed_leak + (0.04 * np.sin(2.0 * np.pi * 880.0 * time))[:, np.newaxis]
    leaked = accompaniment + eq_changed_leak

    cleaned = suppress_vocal_bleed_spectral(leaked, vocal, strength=0.96, sample_rate=sample_rate)

    before = abs(float(np.dot(leaked[:, 0], vocal[:, 0])))
    after = abs(float(np.dot(cleaned[:, 0], vocal[:, 0])))
    assert after < before * 0.50
    assert cleaned.shape == leaked.shape


def test_suppress_vocal_bleed_spectral_reduces_phrase_tail_echo():
    sample_rate = 16_000
    time = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    phrase_frames = int(sample_rate * 0.75)
    tail_frames = int(sample_rate * 0.36)
    vocal = np.zeros_like(time)
    vocal[:phrase_frames] = 0.18 * np.sin(2.0 * np.pi * 220.0 * time[:phrase_frames])
    accompaniment = 0.08 * np.sin(2.0 * np.pi * 110.0 * time)
    tail_time = np.arange(tail_frames, dtype=np.float32) / sample_rate
    tail_envelope = np.exp(-tail_time * 5.5)
    tail_echo = np.zeros_like(time)
    tail_echo[phrase_frames : phrase_frames + tail_frames] = (
        0.055 * tail_envelope * np.sin(2.0 * np.pi * 220.0 * tail_time)
    )
    leaked = (accompaniment + tail_echo)[:, np.newaxis]

    cleaned = suppress_vocal_bleed_spectral(
        leaked,
        vocal[:, np.newaxis],
        strength=0.96,
        sample_rate=sample_rate,
    )

    tail_slice = slice(phrase_frames, phrase_frames + tail_frames)
    before = abs(float(np.dot(leaked[tail_slice, 0], tail_echo[tail_slice])))
    after = abs(float(np.dot(cleaned[tail_slice, 0], tail_echo[tail_slice])))
    assert after < before * 0.70
    assert cleaned.shape == leaked.shape
