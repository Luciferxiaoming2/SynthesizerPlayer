"""Stateful dual-track playback engine independent from audio devices."""

from dataclasses import dataclass, replace
from threading import RLock

import numpy as np

from core_engine.player.sync_buffer import StereoTrackBuffer, mix_aligned_tracks


@dataclass(frozen=True)
class TrackControls:
    vocal_gain: float = 1.0
    instrumental_gain: float = 1.0
    vocal_muted: bool = False
    instrumental_muted: bool = False
    vocal_solo: bool = False
    instrumental_solo: bool = False

    def __post_init__(self) -> None:
        if self.vocal_gain < 0.0:
            raise ValueError("vocal_gain must be non-negative")
        if self.instrumental_gain < 0.0:
            raise ValueError("instrumental_gain must be non-negative")

    def gains(self) -> tuple[float, float]:
        vocal_gain = self.vocal_gain
        instrumental_gain = self.instrumental_gain

        if self.vocal_solo or self.instrumental_solo:
            vocal_gain = vocal_gain if self.vocal_solo else 0.0
            instrumental_gain = instrumental_gain if self.instrumental_solo else 0.0

        if self.vocal_muted:
            vocal_gain = 0.0
        if self.instrumental_muted:
            instrumental_gain = 0.0

        return vocal_gain, instrumental_gain


@dataclass(frozen=True)
class PlaybackSnapshot:
    position_frames: int
    position_seconds: float
    duration_seconds: float
    is_playing: bool
    is_finished: bool
    controls: TrackControls


class DualTrackPlaybackEngine:
    """Render fixed-size playback blocks from an aligned dual-track buffer."""

    def __init__(self, buffers: StereoTrackBuffer, controls: TrackControls | None = None) -> None:
        self._buffers = buffers
        self._controls = controls or TrackControls()
        self._position = 0
        self._playing = False
        self._lock = RLock()

    @property
    def buffers(self) -> StereoTrackBuffer:
        with self._lock:
            return self._buffers

    @property
    def controls(self) -> TrackControls:
        with self._lock:
            return self._controls

    @property
    def position_frames(self) -> int:
        with self._lock:
            return self._position

    @property
    def position_seconds(self) -> float:
        with self._lock:
            return self._position / self._buffers.sample_rate

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    @property
    def is_finished(self) -> bool:
        with self._lock:
            return self._position >= self._buffers.frame_count

    def play(self) -> None:
        with self._lock:
            if self._position >= self._buffers.frame_count:
                self._position = 0
            self._playing = True

    def pause(self) -> None:
        with self._lock:
            self._playing = False

    def stop(self) -> None:
        with self._lock:
            self._playing = False
            self._position = 0

    def seek_frames(self, frame: int) -> None:
        if frame < 0:
            raise ValueError("frame must be non-negative")
        with self._lock:
            self._position = min(frame, self._buffers.frame_count)

    def seek_seconds(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        self.seek_frames(round(seconds * self._buffers.sample_rate))

    def set_controls(self, **changes: float | bool) -> None:
        with self._lock:
            self._controls = replace(self._controls, **changes)

    def replace_buffers(self, buffers: StereoTrackBuffer, keep_position: bool = True) -> None:
        with self._lock:
            self._buffers = buffers
            if keep_position:
                self._position = min(self._position, self._buffers.frame_count)
            else:
                self._position = 0

    def set_gains(
        self,
        vocal_gain: float | None = None,
        instrumental_gain: float | None = None,
    ) -> None:
        changes: dict[str, float] = {}
        if vocal_gain is not None:
            changes["vocal_gain"] = vocal_gain
        if instrumental_gain is not None:
            changes["instrumental_gain"] = instrumental_gain
        self.set_controls(**changes)

    def set_mute(
        self,
        vocal_muted: bool | None = None,
        instrumental_muted: bool | None = None,
    ) -> None:
        changes: dict[str, bool] = {}
        if vocal_muted is not None:
            changes["vocal_muted"] = vocal_muted
        if instrumental_muted is not None:
            changes["instrumental_muted"] = instrumental_muted
        self.set_controls(**changes)

    def set_solo(
        self,
        vocal_solo: bool | None = None,
        instrumental_solo: bool | None = None,
    ) -> None:
        changes: dict[str, bool] = {}
        if vocal_solo is not None:
            changes["vocal_solo"] = vocal_solo
        if instrumental_solo is not None:
            changes["instrumental_solo"] = instrumental_solo
        self.set_controls(**changes)

    def snapshot(self) -> PlaybackSnapshot:
        with self._lock:
            return PlaybackSnapshot(
                position_frames=self._position,
                position_seconds=self._position / self._buffers.sample_rate,
                duration_seconds=self._buffers.duration_seconds,
                is_playing=self._playing,
                is_finished=self._position >= self._buffers.frame_count,
                controls=self._controls,
            )

    def render_block(self, frame_count: int) -> np.ndarray:
        """Render the next playback block and advance when playing."""

        if frame_count <= 0:
            raise ValueError("frame_count must be positive")

        with self._lock:
            shape = (frame_count, self._buffers.channel_count)
            if not self._playing:
                return np.zeros(shape, dtype=np.float32)

            start = self._position
            end = min(start + frame_count, self._buffers.frame_count)
            available = end - start
            output = np.zeros(shape, dtype=np.float32)

            if available > 0:
                block = self._buffers.slice_frames(start, available)
                vocal_gain, instrumental_gain = self._controls.gains()
                output[:available] = mix_aligned_tracks(
                    block,
                    vocal_gain=vocal_gain,
                    instrumental_gain=instrumental_gain,
                )

            self._position = end
            if self._position >= self._buffers.frame_count:
                self._playing = False
            return output
