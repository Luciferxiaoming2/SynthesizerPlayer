"""Optional SoundDevice output adapter for the dual-track playback engine."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Sequence

import numpy as np

from core_engine.player.playback_engine import DualTrackPlaybackEngine


@dataclass(frozen=True)
class SoundDeviceOutputConfig:
    block_size: int = 1024
    device: int | str | None = None


@dataclass(frozen=True)
class AudioOutputDevice:
    id: int
    name: str
    max_output_channels: int
    default_sample_rate: float

    @property
    def label(self) -> str:
        return f"{self.id}: {self.name}"


def list_output_devices(
    query_devices: Callable[[], Sequence[dict[str, object]]] | None = None,
) -> list[AudioOutputDevice]:
    """List output-capable devices without importing sounddevice at module import time."""

    if query_devices is None:
        import sounddevice as sd

        query_devices = sd.query_devices

    devices: list[AudioOutputDevice] = []
    for index, info in enumerate(query_devices()):
        max_output_channels = int(info.get("max_output_channels", 0))
        if max_output_channels <= 0:
            continue
        devices.append(
            AudioOutputDevice(
                id=index,
                name=str(info.get("name", f"Device {index}")),
                max_output_channels=max_output_channels,
                default_sample_rate=float(info.get("default_samplerate", 0.0)),
            )
        )
    return devices


class SoundDeviceOutput:
    """Thin adapter around sounddevice.OutputStream.

    Importing sounddevice is deferred so tests and non-audio environments can use
    the playback engine without a native audio stack.
    """

    def __init__(
        self,
        engine: DualTrackPlaybackEngine,
        config: SoundDeviceOutputConfig | None = None,
    ) -> None:
        self._engine = engine
        self._config = config or SoundDeviceOutputConfig()
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        self._engine.play()
        self._stream = sd.OutputStream(
            samplerate=self._engine.buffers.sample_rate,
            channels=self._engine.buffers.channel_count,
            blocksize=self._config.block_size,
            device=self._config.device,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        self._engine.stop()
        self.close()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, outdata: np.ndarray, frames: int, _time: object, status: object) -> None:
        if status:
            print(status)
        outdata[:] = self._engine.render_block(frames)
