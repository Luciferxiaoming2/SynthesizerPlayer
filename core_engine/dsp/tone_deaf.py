"""F0 drift based tone-deaf simulation."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ToneDeafConfig:
    drift_ratio: float
    random_seed: int | None = None
    frame_ms: float = 40.0
    hop_ms: float = 20.0
    min_f0_hz: float = 70.0
    max_f0_hz: float = 900.0
    max_drift_cents: float = 720.0
    wobble_hz: float = 3.2

    def __post_init__(self) -> None:
        if not 0.0 <= self.drift_ratio <= 1.0:
            raise ValueError("drift_ratio must be between 0.0 and 1.0")
        if self.frame_ms <= 0.0 or self.hop_ms <= 0.0:
            raise ValueError("frame_ms and hop_ms must be positive")
        if self.min_f0_hz <= 0.0 or self.max_f0_hz <= self.min_f0_hz:
            raise ValueError("invalid F0 range")
        if self.max_drift_cents <= 0.0 or self.wobble_hz < 0.0:
            raise ValueError("invalid tone-deaf drift settings")


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

    This lightweight fallback avoids a global pitch shift. It applies
    deterministic, chunk-local resampling drift while preserving total length.
    A future PyWorld backend can replace this function behind the same contract.
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

    f0_track = estimate_f0_track(audio, sample_rate, config)
    drift_curve = generate_drift_curve(f0_track, config)

    chunk_size = max(512, round(sample_rate * (config.frame_ms / 1000.0) * 2.0))
    overlap = max(64, chunk_size // 8)
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

    return output / np.maximum(weights, 1.0)


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

    random_steps = rng.normal(0.0, max_cents * 0.24, size=f0_track.times_seconds.size)
    random_walk = np.cumsum(random_steps)
    if random_walk.size > 0:
        random_walk -= float(np.mean(random_walk))
    times = f0_track.times_seconds.astype(np.float32)
    slow_wander = np.sin(times * np.pi * 2.0 * 0.55) * max_cents * 0.38
    nervous_wobble = np.sin(times * np.pi * 2.0 * config.wobble_hz) * max_cents * 0.16
    phrase_steps = stepped_phrase_offsets(times, max_cents, rng)
    active_weight = np.where(
        f0_track.frequencies_hz > 0.0,
        np.clip(f0_track.confidence, 0.35, 1.0),
        0.0,
    )
    cents = (random_walk + slow_wander + nervous_wobble + phrase_steps) * active_weight
    cents = smooth_curve(cents, window_size=5)
    cents = np.clip(cents, -max_cents, max_cents)
    return DriftCurve(
        times_seconds=f0_track.times_seconds,
        cents=np.asarray(cents, dtype=np.float32),
    )


def stepped_phrase_offsets(times_seconds: np.ndarray, max_cents: float, rng: np.random.Generator) -> np.ndarray:
    """Generate phrase-level wrong-note jumps so the effect is easy to hear."""

    if times_seconds.size == 0:
        return np.asarray([], dtype=np.float32)

    offsets = np.zeros(times_seconds.size, dtype=np.float32)
    phrase_seconds = 0.42
    current_bucket = None
    current_offset = 0.0
    for index, time_seconds in enumerate(times_seconds):
        bucket = int(float(time_seconds) / phrase_seconds)
        if bucket != current_bucket:
            current_bucket = bucket
            direction = -1.0 if bucket % 2 else 1.0
            current_offset = direction * rng.uniform(max_cents * 0.20, max_cents * 0.55)
        offsets[index] = current_offset
    return offsets


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
    source_positions = np.arange(frame_count, dtype=np.float32) * factor
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
