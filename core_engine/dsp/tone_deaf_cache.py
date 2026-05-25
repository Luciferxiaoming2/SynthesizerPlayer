"""Cache tone-deaf vocal renders for playback buffer replacement."""

from dataclasses import dataclass

import numpy as np

from core_engine.dsp.tone_deaf import ToneDeafConfig, render_tone_deaf_vocal, suppress_vocal_bleed
from core_engine.player.sync_buffer import StereoTrackBuffer


@dataclass(frozen=True)
class ToneDeafRenderKey:
    drift_ratio: float
    random_seed: int | None
    max_drift_cents: float
    max_effect_mix: float
    timbre_crossover_hz: float
    rubberband_executable: str | None
    frame_count: int
    sample_rate: int
    source_fingerprint: int


class ToneDeafBufferCache:
    """In-memory cache keyed by render configuration and source buffer shape."""

    def __init__(self) -> None:
        self._cache: dict[ToneDeafRenderKey, np.ndarray] = {}

    @property
    def size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()

    def render_vocal(self, buffers: StereoTrackBuffer, config: ToneDeafConfig) -> np.ndarray:
        key = ToneDeafRenderKey(
            drift_ratio=round(config.drift_ratio, 4),
            random_seed=config.random_seed,
            max_drift_cents=round(config.max_drift_cents, 2),
            max_effect_mix=round(config.max_effect_mix, 4),
            timbre_crossover_hz=round(config.timbre_crossover_hz, 2),
            rubberband_executable=config.rubberband_executable,
            frame_count=buffers.frame_count,
            sample_rate=buffers.sample_rate,
            source_fingerprint=audio_fingerprint(buffers.vocal),
        )
        if key not in self._cache:
            self._cache[key] = render_tone_deaf_vocal(
                buffers.vocal,
                buffers.sample_rate,
                config,
            )
        return self._cache[key].copy()

    def render_buffer(self, buffers: StereoTrackBuffer, config: ToneDeafConfig) -> StereoTrackBuffer:
        rendered_vocal = self.render_vocal(buffers, config)
        cleaned_instrumental = suppress_vocal_bleed(
            buffers.instrumental,
            buffers.vocal,
            strength=min(1.0, 0.42 + config.drift_ratio * 0.72),
            max_subtraction=1.08,
            min_correlation=0.018,
            sample_rate=buffers.sample_rate,
        )
        return StereoTrackBuffer(
            vocal=rendered_vocal,
            instrumental=cleaned_instrumental,
            sample_rate=buffers.sample_rate,
        )


def audio_fingerprint(audio: np.ndarray) -> int:
    """Small stable fingerprint so same-length songs do not share stale renders."""

    array = np.asarray(audio, dtype=np.float32)
    if array.size == 0:
        return 0
    flat = array.reshape(-1)
    sample_count = min(512, flat.size)
    indices = np.linspace(0, flat.size - 1, sample_count, dtype=np.int64)
    quantized = np.round(flat[indices] * 32767.0).astype(np.int32)
    return hash(tuple(int(value) for value in quantized))
