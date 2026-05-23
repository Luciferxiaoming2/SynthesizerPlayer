"""DiffSinger-style adapters for lyric-to-vocal synthesis."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
from collections.abc import Sequence

import numpy as np

from core_engine.player.sync_buffer import write_audio


@dataclass(frozen=True)
class SingingSegmentRequest:
    lyric: str
    melody_path: Path
    output_path: Path
    sample_rate: int = 16_000
    duration_seconds: float = 2.0


@dataclass(frozen=True)
class SingingSegmentResult:
    output_path: Path
    backend_name: str
    lyric: str
    sample_rate: int
    duration_seconds: float


class DiffSingerClient:
    def synthesize(self, request: SingingSegmentRequest) -> Path:
        raise NotImplementedError("Wire this adapter to a DiffSinger runtime")


class PreviewSingingClient(DiffSingerClient):
    """Lightweight deterministic preview backend for harness and UI flow testing."""

    def synthesize(self, request: SingingSegmentRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        frames = max(1, round(request.sample_rate * request.duration_seconds))
        time = np.arange(frames, dtype=np.float32) / request.sample_rate
        lyric_factor = max(1, len(request.lyric.strip()))
        base_frequency = 180.0 + float(lyric_factor % 12) * 8.0
        vibrato = 1.0 + 0.015 * np.sin(2.0 * np.pi * 5.0 * time)
        envelope = np.sin(np.pi * np.linspace(0.0, 1.0, frames, dtype=np.float32))
        vocal = 0.22 * envelope * np.sin(2.0 * np.pi * base_frequency * vibrato * time)
        vocal += 0.04 * envelope * np.sin(2.0 * np.pi * base_frequency * 2.0 * time)
        write_audio(request.output_path, vocal[:, np.newaxis].astype(np.float32), request.sample_rate)
        return request.output_path


class ExternalDiffSingerClient(DiffSingerClient):
    """Command adapter for external open-source singing synthesis runtimes."""

    def __init__(self, command_template: Sequence[str]) -> None:
        if not command_template:
            raise ValueError("command_template must not be empty")
        self._command_template = tuple(command_template)

    def synthesize(self, request: SingingSegmentRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._render_command(request), check=True)
        if not request.output_path.exists():
            raise FileNotFoundError(f"external singer did not create {request.output_path}")
        return request.output_path

    def _render_command(self, request: SingingSegmentRequest) -> list[str]:
        values = {
            "lyric": request.lyric,
            "melody": str(request.melody_path),
            "output": str(request.output_path),
            "sample_rate": str(request.sample_rate),
            "duration": str(request.duration_seconds),
        }
        return [part.format(**values) for part in self._command_template]
