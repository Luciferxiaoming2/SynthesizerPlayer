"""F0 drift based tone-deaf simulation."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class ToneDeafConfig:
    drift_ratio: float
    random_seed: int | None = None
    frame_ms: float = 40.0
    hop_ms: float = 20.0
    min_f0_hz: float = 70.0
    max_f0_hz: float = 900.0
    max_drift_cents: float = 520.0
    wobble_hz: float = 3.2
    max_effect_mix: float = 1.0
    timbre_crossover_hz: float = 2600.0
    note_transition_ms: float = 110.0
    phrase_min_seconds: float = 0.85
    phrase_max_seconds: float = 1.75
    rubberband_executable: str | None = None
    temporary_dir: Path | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.drift_ratio <= 1.0:
            raise ValueError("drift_ratio must be between 0.0 and 1.0")
        if self.frame_ms <= 0.0 or self.hop_ms <= 0.0:
            raise ValueError("frame_ms and hop_ms must be positive")
        if self.min_f0_hz <= 0.0 or self.max_f0_hz <= self.min_f0_hz:
            raise ValueError("invalid F0 range")
        if self.max_drift_cents <= 0.0 or self.wobble_hz < 0.0:
            raise ValueError("invalid tone-deaf drift settings")
        if not 0.0 <= self.max_effect_mix <= 1.0:
            raise ValueError("max_effect_mix must be between 0.0 and 1.0")
        if self.timbre_crossover_hz <= 0.0:
            raise ValueError("timbre_crossover_hz must be positive")
        if self.note_transition_ms <= 0.0:
            raise ValueError("note_transition_ms must be positive")
        if self.phrase_min_seconds <= 0.0 or self.phrase_max_seconds < self.phrase_min_seconds:
            raise ValueError("invalid phrase timing")


@dataclass(frozen=True)
class F0Track:
    times_seconds: np.ndarray
    frequencies_hz: np.ndarray
    confidence: np.ndarray
    hop_samples: int


@dataclass(frozen=True)
class DriftCurve:
    times_seconds: np.ndarray
    cents: np.ndarray


def render_tone_deaf_vocal(
    vocal: np.ndarray,
    sample_rate: int,
    config: ToneDeafConfig,
) -> np.ndarray:
    """Render an offline vocal buffer with human-like local pitch drift.

    This lightweight fallback avoids replacing the full vocal with a shifted
    signal. It keeps the original vocal as the dry anchor and blends in a
    deterministic, chunk-local pitch-drift layer. The result is audibly out of
    tune while keeping the singer's timbre close to the source.
    """

    audio = np.asarray(vocal, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.ndim != 2:
        raise ValueError("vocal must be mono or channel-last 2D")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if audio.shape[0] == 0:
        return audio.copy()

    if config.rubberband_executable:
        rubberband_rendered = try_render_rubberband_tone_deaf_vocal(audio, sample_rate, config)
        if rubberband_rendered is not None:
            return rubberband_rendered

    f0_track = estimate_f0_track(audio, sample_rate, config)
    drift_curve = generate_drift_curve(f0_track, config)

    chunk_size = max(2048, round(sample_rate * 0.22))
    overlap = max(512, chunk_size // 2)
    hop = chunk_size - overlap

    output = np.zeros_like(audio, dtype=np.float32)
    weights = np.zeros((audio.shape[0], 1), dtype=np.float32)

    for start in range(0, audio.shape[0], hop):
        end = min(start + chunk_size, audio.shape[0])
        chunk = audio[start:end]
        if chunk.shape[0] < 2:
            output[start:end] += chunk
            weights[start:end] += 1.0
            continue

        center_time = ((start + end) * 0.5) / sample_rate
        cents = drift_cents_at(drift_curve, center_time)
        rendered = resample_chunk_with_pitch_factor(chunk, cents_to_factor(cents))
        fade = raised_cosine_window(rendered.shape[0], overlap)
        output[start:end] += rendered * fade
        weights[start:end] += fade

    rendered = output / np.maximum(weights, 1.0)
    shifted_layer = smooth_output_level(audio, rendered)
    return blend_with_timbre_anchor(audio, shifted_layer, sample_rate, config)


def suppress_vocal_bleed(
    instrumental: np.ndarray,
    reference_vocal: np.ndarray,
    strength: float,
    max_subtraction: float = 0.92,
    min_correlation: float = 0.035,
    sample_rate: int = 44_100,
) -> np.ndarray:
    """Reduce original-vocal leakage in an accompaniment stem.

    Separation models often leave a quiet copy of the lead vocal in the
    accompaniment. When the lead vocal is pitch shifted, that leftover dry
    vocal is perceived as a second singer. This subtracts only the component
    that is linearly correlated with the original vocal stem.
    """

    inst = np.asarray(instrumental, dtype=np.float32)
    vocal = np.asarray(reference_vocal, dtype=np.float32)
    if inst.ndim == 1:
        inst = inst[:, np.newaxis]
    if vocal.ndim == 1:
        vocal = vocal[:, np.newaxis]
    if inst.shape != vocal.shape or inst.size == 0:
        return inst.copy()

    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 1e-6:
        return inst.copy()

    cleaned = inst.copy()
    strongest_correlation = 0.0
    for channel in range(inst.shape[1]):
        ref = vocal[:, channel]
        target = inst[:, channel]
        ref_energy = float(np.dot(ref, ref)) + 1e-9
        target_energy = float(np.dot(target, target)) + 1e-9
        correlation = float(np.dot(target, ref) / np.sqrt(ref_energy * target_energy))
        strongest_correlation = max(strongest_correlation, abs(correlation))
        if abs(correlation) < min_correlation:
            continue
        coefficient = float(np.dot(target, ref) / ref_energy)
        coefficient = max(-max_subtraction, min(max_subtraction, coefficient))
        cleaned[:, channel] = target - ref * coefficient * strength

    has_vocal_like_overlap = spectral_vocal_overlap(cleaned, vocal, sample_rate) >= 0.16
    if strongest_correlation >= min_correlation or (strength >= 0.72 and has_vocal_like_overlap):
        spectral_strength = min(0.995, 0.40 + strength * 0.68)
        cleaned = suppress_vocal_bleed_spectral(cleaned, vocal, spectral_strength, sample_rate=sample_rate)
    return np.clip(cleaned, -0.96, 0.96).astype(np.float32)


def spectral_vocal_overlap(
    instrumental: np.ndarray,
    reference_vocal: np.ndarray,
    sample_rate: int,
    low_hz: float = 90.0,
    high_hz: float = 7600.0,
) -> float:
    """Estimate whether the accompaniment still contains vocal-shaped energy."""

    inst = np.asarray(instrumental, dtype=np.float32)
    vocal = np.asarray(reference_vocal, dtype=np.float32)
    if inst.ndim == 2:
        inst = np.mean(inst, axis=1)
    if vocal.ndim == 2:
        vocal = np.mean(vocal, axis=1)
    frame_count = min(inst.size, vocal.size)
    if frame_count < 8:
        return 0.0
    fft_size = min(frame_count, 16384)
    inst = inst[:fft_size] * np.hanning(fft_size).astype(np.float32)
    vocal = vocal[:fft_size] * np.hanning(fft_size).astype(np.float32)
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
    band = (frequencies >= low_hz) & (frequencies <= high_hz)
    if not np.any(band):
        return 0.0
    inst_mag = np.abs(np.fft.rfft(inst))[band]
    vocal_mag = np.abs(np.fft.rfft(vocal))[band]
    denominator = float(np.linalg.norm(inst_mag) * np.linalg.norm(vocal_mag)) + 1e-9
    return float(np.dot(inst_mag, vocal_mag) / denominator)


def suppress_vocal_bleed_spectral(
    instrumental: np.ndarray,
    reference_vocal: np.ndarray,
    strength: float,
    fft_size: int = 4096,
    hop_size: int = 1024,
    low_hz: float = 90.0,
    high_hz: float = 7600.0,
    sample_rate: int = 44_100,
    tail_release_ms: float = 360.0,
) -> np.ndarray:
    """Frequency-domain residual vocal suppression.

    A separated accompaniment can contain a processed copy of the vocal whose
    phase/EQ no longer matches the vocal stem globally. Per-bin complex
    projection handles that better than a single full-band subtraction.
    """

    inst = np.asarray(instrumental, dtype=np.float32)
    vocal = np.asarray(reference_vocal, dtype=np.float32)
    if inst.ndim == 1:
        inst = inst[:, np.newaxis]
    if vocal.ndim == 1:
        vocal = vocal[:, np.newaxis]
    if inst.shape != vocal.shape or inst.shape[0] < 8:
        return inst.copy()

    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 1e-6:
        return inst.copy()

    frame_count, channel_count = inst.shape
    fft_size = min(max(256, int(fft_size)), max(256, next_power_of_two(frame_count)))
    hop_size = max(1, min(int(hop_size), fft_size // 2))
    window = np.hanning(fft_size).astype(np.float32)
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
    vocal_band = (frequencies >= low_hz) & (frequencies <= high_hz)
    release_frames = max(1, round((tail_release_ms / 1000.0) * sample_rate / hop_size))
    tail_frames_remaining = 0
    padded_frames = int(np.ceil(max(1, frame_count - fft_size) / hop_size)) * hop_size + fft_size
    output = np.zeros((padded_frames, channel_count), dtype=np.float32)
    weights = np.zeros((padded_frames, 1), dtype=np.float32)

    padded_inst = np.zeros((padded_frames, channel_count), dtype=np.float32)
    padded_vocal = np.zeros((padded_frames, channel_count), dtype=np.float32)
    padded_inst[:frame_count] = inst
    padded_vocal[:frame_count] = vocal

    for start in range(0, padded_frames - fft_size + 1, hop_size):
        end = start + fft_size
        frame_weight = window[:, np.newaxis]
        inst_frame = padded_inst[start:end] * frame_weight
        vocal_frame = padded_vocal[start:end] * frame_weight
        inst_spectrum = np.fft.rfft(inst_frame, axis=0)
        vocal_spectrum = np.fft.rfft(vocal_frame, axis=0)
        vocal_power = np.abs(vocal_spectrum) ** 2
        inst_power = np.abs(inst_spectrum) ** 2
        vocal_active = vocal_power > (np.percentile(vocal_power, 52, axis=0, keepdims=True) + 1e-10)
        band_mask = vocal_band[:, np.newaxis] & vocal_active
        if np.any(band_mask):
            tail_frames_remaining = release_frames
        elif tail_frames_remaining > 0:
            tail_frames_remaining -= 1

        projection = inst_spectrum * np.conj(vocal_spectrum) / (vocal_power + 1e-8)
        projection = clamp_complex_magnitude(projection, 1.15)
        subtraction = projection * vocal_spectrum
        cleaned_spectrum = np.where(
            band_mask,
            inst_spectrum - subtraction * strength,
            inst_spectrum,
        )

        if tail_frames_remaining > 0:
            tail_decay = tail_frames_remaining / release_frames
            tail_band_mask = vocal_band[:, np.newaxis] & ~band_mask
            # Phrase-ending reverb in the accompaniment is not aligned with
            # the dry vocal stem, so subtraction cannot fully catch it. Apply
            # a short language-agnostic vocal-band release duck only after a
            # detected vocal phrase.
            tail_duck = max(0.42, 1.0 - strength * 0.36 * tail_decay)
            cleaned_spectrum = np.where(tail_band_mask, cleaned_spectrum * tail_duck, cleaned_spectrum)

        # Avoid hollowing out accompaniment bins more than necessary.
        cleaned_power = np.abs(cleaned_spectrum) ** 2
        too_quiet = cleaned_power < inst_power * 0.08
        cleaned_spectrum = np.where(too_quiet & band_mask, inst_spectrum * 0.16, cleaned_spectrum)
        cleaned_frame = np.fft.irfft(cleaned_spectrum, n=fft_size, axis=0).astype(np.float32)
        output[start:end] += cleaned_frame * frame_weight
        weights[start:end] += frame_weight * frame_weight

    return (output[:frame_count] / np.maximum(weights[:frame_count], 1e-6)).astype(np.float32)


def clamp_complex_magnitude(values: np.ndarray, max_magnitude: float) -> np.ndarray:
    magnitudes = np.abs(values)
    scale = np.minimum(1.0, max_magnitude / (magnitudes + 1e-9))
    return values * scale


def next_power_of_two(value: int) -> int:
    if value <= 1:
        return 1
    return 1 << (int(value) - 1).bit_length()


def try_render_rubberband_tone_deaf_vocal(
    vocal: np.ndarray,
    sample_rate: int,
    config: ToneDeafConfig,
) -> np.ndarray | None:
    """Render a high-quality optional Rubber Band pitch layer.

    Rubber Band is treated as an optional delivery enhancement. If the binary
    is missing or rejects the command, callers fall back to the built-in path.
    """

    if not config.rubberband_executable:
        return None
    if config.drift_ratio <= 1e-6:
        return np.asarray(vocal, dtype=np.float32).copy()

    semitones = rubberband_base_shift_semitones(config)
    if abs(semitones) < 1e-3:
        return None

    try:
        with tempfile.TemporaryDirectory(dir=config.temporary_dir) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            source_path = temp_dir / "source.wav"
            shifted_path = temp_dir / "shifted.wav"
            pitchmap_path = temp_dir / "pitchmap.txt"
            sf.write(source_path, np.asarray(vocal, dtype=np.float32), sample_rate)
            write_rubberband_pitchmap(vocal, sample_rate, config, semitones, pitchmap_path)
            subprocess.run(
                rubberband_pitch_command(
                    config.rubberband_executable,
                    semitones,
                    source_path,
                    shifted_path,
                    pitchmap_path,
                ),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            shifted, shifted_rate = sf.read(shifted_path, always_2d=True, dtype="float32")
    except Exception:
        return None

    if shifted_rate != sample_rate:
        return None
    shifted = fit_audio_frame_count(shifted.astype(np.float32), vocal.shape[0], vocal.shape[1])
    return smooth_output_level(vocal, shifted)


def write_rubberband_pitchmap(
    vocal: np.ndarray,
    sample_rate: int,
    config: ToneDeafConfig,
    base_semitones: float,
    path: Path,
) -> Path:
    drift_config = ToneDeafConfig(
        drift_ratio=config.drift_ratio,
        random_seed=config.random_seed,
        frame_ms=config.frame_ms,
        hop_ms=config.hop_ms,
        min_f0_hz=config.min_f0_hz,
        max_f0_hz=config.max_f0_hz,
        max_drift_cents=config.max_drift_cents * 0.24,
        wobble_hz=0.0,
        max_effect_mix=config.max_effect_mix,
        timbre_crossover_hz=config.timbre_crossover_hz,
        note_transition_ms=max(config.note_transition_ms, 680.0),
        phrase_min_seconds=max(config.phrase_min_seconds, 1.15),
        phrase_max_seconds=max(config.phrase_max_seconds, 2.25),
    )
    f0_track = estimate_f0_track(vocal, sample_rate, drift_config)
    drift_curve = generate_drift_curve(f0_track, drift_config)
    lines = rubberband_pitchmap_lines(
        drift_curve,
        sample_rate,
        vocal.shape[0],
        base_semitones,
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def rubberband_pitchmap_lines(
    drift_curve: DriftCurve,
    sample_rate: int,
    frame_count: int,
    base_semitones: float,
    min_interval_ms: float = 260.0,
    min_change_semitones: float = 0.035,
) -> list[str]:
    """Build a sparse, slow pitch map to avoid word-level timbre jumps."""

    last_frame = max(0, frame_count - 1)
    if frame_count <= 1 or drift_curve.times_seconds.size == 0:
        return [f"0 {base_semitones:.6f}"]

    min_interval_frames = max(1, round(sample_rate * min_interval_ms / 1000.0))
    lines = [f"0 {base_semitones:.6f}"]
    last_written_frame = 0
    last_written_value = base_semitones

    for time_seconds, cents in zip(drift_curve.times_seconds, drift_curve.cents):
        frame = max(0, min(last_frame, round(float(time_seconds) * sample_rate)))
        value = base_semitones + float(cents) / 100.0
        if frame - last_written_frame < min_interval_frames:
            continue
        if abs(value - last_written_value) < min_change_semitones:
            continue
        lines.append(f"{frame} {value:.6f}")
        last_written_frame = frame
        last_written_value = value

    if last_written_frame != last_frame:
        lines.append(f"{last_frame} {base_semitones:.6f}")
    return lines


def rubberband_pitch_command(
    executable: str,
    semitones: float,
    source_path: Path,
    output_path: Path,
    pitchmap_path: Path | None = None,
) -> list[str]:
    quality_executable = rubberband_quality_executable(executable)
    command = [
        quality_executable,
        "--fine",
        "--formant",
        "--quiet",
    ]
    if pitchmap_path is None:
        command.extend(["--pitch", f"{semitones:.4f}"])
    else:
        command.extend(["--pitch", "0", "--pitchmap", str(pitchmap_path)])
    command.extend([str(source_path), str(output_path)])
    return command


def rubberband_quality_executable(executable: str) -> str:
    path = Path(executable)
    r3_candidate = path.with_name("rubberband-r3.exe")
    if r3_candidate.exists():
        return str(r3_candidate)
    return executable


def rubberband_base_shift_semitones(config: ToneDeafConfig) -> float:
    direction = -1.0 if (config.random_seed or 0) % 2 else 1.0
    return direction * (0.55 + config.drift_ratio * 2.35)


def fit_audio_frame_count(audio: np.ndarray, frame_count: int, channel_count: int) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, np.newaxis]
    if array.shape[1] < channel_count:
        array = np.repeat(array[:, :1], channel_count, axis=1)
    elif array.shape[1] > channel_count:
        array = array[:, :channel_count]
    if array.shape[0] == frame_count:
        return array.copy()
    if array.shape[0] <= 1:
        return np.zeros((frame_count, channel_count), dtype=np.float32)
    source_positions = np.linspace(0.0, 1.0, array.shape[0], dtype=np.float32)
    target_positions = np.linspace(0.0, 1.0, frame_count, dtype=np.float32)
    fitted = np.empty((frame_count, channel_count), dtype=np.float32)
    for channel in range(channel_count):
        fitted[:, channel] = np.interp(target_positions, source_positions, array[:, channel])
    return fitted


def estimate_f0_track(
    vocal: np.ndarray,
    sample_rate: int,
    config: ToneDeafConfig | None = None,
) -> F0Track:
    """Estimate an F0 track using a small autocorrelation detector."""

    config = config or ToneDeafConfig(drift_ratio=0.4)
    mono = to_mono(vocal)
    frame_samples = max(32, round(sample_rate * config.frame_ms / 1000.0))
    hop_samples = max(1, round(sample_rate * config.hop_ms / 1000.0))
    min_lag = max(1, int(sample_rate / config.max_f0_hz))
    max_lag = max(min_lag + 1, int(sample_rate / config.min_f0_hz))

    frequencies: list[float] = []
    confidence: list[float] = []
    times: list[float] = []
    for start in range(0, max(1, mono.size - frame_samples + 1), hop_samples):
        frame = mono[start : start + frame_samples]
        if frame.size < frame_samples:
            frame = np.pad(frame, (0, frame_samples - frame.size))

        frequency, score = estimate_frame_f0(frame, sample_rate, min_lag, max_lag)
        frequencies.append(frequency)
        confidence.append(score)
        times.append((start + frame_samples * 0.5) / sample_rate)

    return F0Track(
        times_seconds=np.asarray(times, dtype=np.float32),
        frequencies_hz=np.asarray(frequencies, dtype=np.float32),
        confidence=np.asarray(confidence, dtype=np.float32),
        hop_samples=hop_samples,
    )


def estimate_frame_f0(
    frame: np.ndarray,
    sample_rate: int,
    min_lag: int,
    max_lag: int,
) -> tuple[float, float]:
    frame = np.asarray(frame, dtype=np.float32)
    frame = frame - float(np.mean(frame))
    energy = float(np.dot(frame, frame))
    if energy < 1e-8:
        return 0.0, 0.0

    window = np.hanning(frame.size).astype(np.float32)
    frame = frame * window
    correlations = np.correlate(frame, frame, mode="full")[frame.size - 1 :]
    max_lag = min(max_lag, correlations.size - 1)
    if max_lag <= min_lag:
        return 0.0, 0.0

    search = correlations[min_lag : max_lag + 1]
    best_index = int(np.argmax(search))
    best_lag = min_lag + best_index
    zero_lag = float(correlations[0]) + 1e-9
    score = float(correlations[best_lag] / zero_lag)
    if score < 0.2:
        return 0.0, score
    return sample_rate / best_lag, score


def generate_drift_curve(f0_track: F0Track, config: ToneDeafConfig) -> DriftCurve:
    """Generate low-frequency pitch drift in cents from an F0 track."""

    rng = np.random.default_rng(config.random_seed)
    if f0_track.times_seconds.size == 0:
        return DriftCurve(
            times_seconds=np.asarray([0.0], dtype=np.float32),
            cents=np.asarray([0.0], dtype=np.float32),
        )

    max_cents = config.max_drift_cents * config.drift_ratio
    if max_cents <= 1e-6:
        return DriftCurve(
            times_seconds=f0_track.times_seconds,
            cents=np.zeros_like(f0_track.times_seconds, dtype=np.float32),
        )

    times = f0_track.times_seconds.astype(np.float32)
    random_wander = smooth_curve(
        rng.normal(0.0, max_cents * 0.19, size=times.size).astype(np.float32),
        window_size=transition_window_size(times, 320.0),
    )
    slow_wander = np.sin(times * np.pi * 2.0 * 0.42) * max_cents * 0.30
    voice_flutter = np.sin(times * np.pi * 2.0 * config.wobble_hz) * max_cents * 0.075
    phrase_offsets = natural_phrase_offsets(times, max_cents, rng, config)
    active_weight = np.where(
        f0_track.frequencies_hz > 0.0,
        np.clip(f0_track.confidence, 0.35, 1.0),
        0.0,
    )
    cents = (random_wander + slow_wander + voice_flutter + phrase_offsets) * active_weight
    cents = smooth_curve(cents, window_size=transition_window_size(times, config.note_transition_ms))
    cents = np.clip(cents, -max_cents, max_cents)
    return DriftCurve(
        times_seconds=f0_track.times_seconds,
        cents=np.asarray(cents, dtype=np.float32),
    )


def stepped_phrase_offsets(times_seconds: np.ndarray, max_cents: float, rng: np.random.Generator) -> np.ndarray:
    """Backward-compatible wrapper for phrase-level natural pitch offsets."""

    return natural_phrase_offsets(times_seconds, max_cents, rng, ToneDeafConfig(drift_ratio=1.0))


def natural_phrase_offsets(
    times_seconds: np.ndarray,
    max_cents: float,
    rng: np.random.Generator,
    config: ToneDeafConfig,
) -> np.ndarray:
    """Generate slow, sung phrase drift with softened note transitions."""

    if times_seconds.size == 0:
        return np.asarray([], dtype=np.float32)

    start_time = float(times_seconds[0])
    end_time = float(times_seconds[-1])
    anchor_times = [start_time]
    anchor_offsets = [float(rng.normal(0.0, max_cents * 0.16))]
    cursor = start_time
    previous_offset = anchor_offsets[0]
    while cursor < end_time + config.phrase_max_seconds:
        cursor += float(rng.uniform(config.phrase_min_seconds, config.phrase_max_seconds))
        if rng.random() < 0.72:
            direction = -1.0 if previous_offset >= 0.0 else 1.0
        else:
            direction = -1.0 if rng.random() < 0.5 else 1.0
        target = direction * float(rng.uniform(max_cents * 0.28, max_cents * 0.82))
        anchor_times.append(cursor)
        anchor_offsets.append(target)
        previous_offset = target

    raw_offsets = np.interp(times_seconds, np.asarray(anchor_times), np.asarray(anchor_offsets))
    return smooth_curve(
        np.asarray(raw_offsets, dtype=np.float32),
        window_size=transition_window_size(times_seconds, config.note_transition_ms),
    )


def drift_cents_at(curve: DriftCurve, time_seconds: float) -> float:
    if curve.times_seconds.size == 1:
        return float(curve.cents[0])
    return float(np.interp(time_seconds, curve.times_seconds, curve.cents))


def smooth_curve(values: np.ndarray, window_size: int) -> np.ndarray:
    if values.size < 3 or window_size <= 1:
        return values
    window_size = min(window_size, values.size)
    if window_size % 2 == 0:
        window_size -= 1
    if window_size <= 1:
        return values
    kernel = np.ones(window_size, dtype=np.float32) / window_size
    return np.convolve(values, kernel, mode="same")


def transition_window_size(times_seconds: np.ndarray, transition_ms: float) -> int:
    if times_seconds.size < 2:
        return 1
    diffs = np.diff(times_seconds.astype(np.float32))
    hop_seconds = float(np.median(diffs[diffs > 0.0])) if np.any(diffs > 0.0) else 0.02
    window_size = max(1, round((transition_ms / 1000.0) / max(hop_seconds, 1e-3)))
    if window_size % 2 == 0:
        window_size += 1
    return window_size


def to_mono(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        return array
    if array.ndim == 2:
        return np.mean(array, axis=1, dtype=np.float32)
    raise ValueError("audio must be mono or channel-last 2D")


def cents_to_factor(cents: float) -> float:
    return float(2.0 ** (cents / 1200.0))


def resample_chunk_with_pitch_factor(chunk: np.ndarray, factor: float) -> np.ndarray:
    """Resample a chunk locally and return the original frame count."""

    frame_count, channel_count = chunk.shape
    center = (frame_count - 1.0) * 0.5
    source_positions = center + (np.arange(frame_count, dtype=np.float32) - center) * factor
    source_positions = np.clip(source_positions, 0.0, frame_count - 1.0)
    base_positions = np.arange(frame_count, dtype=np.float32)
    rendered = np.empty((frame_count, channel_count), dtype=np.float32)
    for channel in range(channel_count):
        rendered[:, channel] = np.interp(source_positions, base_positions, chunk[:, channel])
    return rendered


def raised_cosine_window(frame_count: int, overlap: int) -> np.ndarray:
    window = np.ones((frame_count, 1), dtype=np.float32)
    fade = min(overlap, frame_count // 2)
    if fade <= 1:
        return window
    ramp = np.linspace(0.0, np.pi, fade, dtype=np.float32)
    fade_in = (1.0 - np.cos(ramp)) * 0.5
    fade_out = fade_in[::-1]
    window[:fade, 0] = fade_in
    window[-fade:, 0] = fade_out
    return window


def smooth_output_level(source: np.ndarray, rendered: np.ndarray) -> np.ndarray:
    """Keep the effect audible without letting resampling transients crackle."""

    source = np.asarray(source, dtype=np.float32)
    rendered = np.nan_to_num(np.asarray(rendered, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if rendered.size == 0:
        return rendered.astype(np.float32)

    source_rms = float(np.sqrt(np.mean(np.square(source, dtype=np.float32)))) + 1e-8
    rendered_rms = float(np.sqrt(np.mean(np.square(rendered, dtype=np.float32)))) + 1e-8
    gain = min(1.0, source_rms / rendered_rms)
    rendered = rendered * gain

    # Soft-limit before the final hard safety clamp. tanh keeps peaks rounded
    # instead of producing the harsh clipped sound users hear as "炸麦".
    limiter_threshold = 0.86
    over = np.abs(rendered) > limiter_threshold
    if np.any(over):
        limited = limiter_threshold * np.tanh(rendered / limiter_threshold)
        rendered = np.where(over, limited, rendered)

    return np.clip(rendered, -0.96, 0.96).astype(np.float32)


def blend_with_timbre_anchor(
    source: np.ndarray,
    shifted_layer: np.ndarray,
    sample_rate: int,
    config: ToneDeafConfig,
) -> np.ndarray:
    """Blend an audible pitch-drift layer while keeping upper timbre stable."""

    source = np.asarray(source, dtype=np.float32)
    shifted_layer = np.asarray(shifted_layer, dtype=np.float32)
    if config.drift_ratio <= 1e-6:
        return source.copy()

    shifted_low, shifted_high = split_frequency_bands(shifted_layer, sample_rate, config.timbre_crossover_hz)
    source_low, source_high = split_frequency_bands(source, sample_rate, config.timbre_crossover_hz)

    # Keep only a tiny dry anchor. A full dry high band on top of the shifted
    # vocal is perceived as a louder original singer masking the pitch effect.
    dry_low_anchor = max(0.0, 0.10 * (1.0 - config.drift_ratio))
    dry_high_anchor = max(0.0, 0.16 * (1.0 - config.drift_ratio))
    wet_amount = min(config.max_effect_mix, 0.88 + config.drift_ratio * 0.12)
    rendered_low = shifted_low * wet_amount + source_low * dry_low_anchor
    rendered_high = shifted_high * wet_amount + source_high * dry_high_anchor
    rendered = rendered_low + rendered_high
    return smooth_output_level(source, rendered)


def split_frequency_bands(audio: np.ndarray, sample_rate: int, crossover_hz: float) -> tuple[np.ndarray, np.ndarray]:
    array = np.asarray(audio, dtype=np.float32)
    if array.shape[0] == 0:
        return array.copy(), array.copy()
    block_size = max(4096, min(65536, round(sample_rate * 1.5)))
    low = np.zeros_like(array, dtype=np.float32)
    for start in range(0, array.shape[0], block_size):
        end = min(start + block_size, array.shape[0])
        block = array[start:end]
        frequencies = np.fft.rfftfreq(block.shape[0], d=1.0 / sample_rate)
        low_mask = (frequencies <= crossover_hz).astype(np.float32)[:, np.newaxis]
        spectrum = np.fft.rfft(block, axis=0)
        low[start:end] = np.fft.irfft(spectrum * low_mask, n=block.shape[0], axis=0).astype(np.float32)
    high = array - low
    return low, high
