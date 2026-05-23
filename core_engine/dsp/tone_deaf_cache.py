"""Cache tone-deaf vocal renders for playback buffer replacement."""

from dataclasses import dataclass

import numpy as np

from core_engine.dsp.tone_deaf import ToneDeafConfig, render_tone_deaf_vocal
from core_engine.player.sync_buffer import StereoTrackBuffer


@dataclass(frozen=True)
class ToneDeafRenderKey:
    drift_ratio: float
    random_seed: int | None
    frame_count: int
    sample_rate: int


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
            frame_count=buffers.frame_count,
            sample_rate=buffers.sample_rate,
        )
        if key not in self._cache:
            self._cache[key] = render_tone_deaf_vocal(
                buffers.vocal,
                buffers.sample_rate,
                config,
            )
        return self._cache[key].copy()

    def render_buffer(self, buffers: StereoTrackBuffer, config: ToneDeafConfig) -> StereoTrackBuffer:
        return buffers.with_vocal(self.render_vocal(buffers, config))

