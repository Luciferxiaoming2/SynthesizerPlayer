"""Optional ffmpeg/rubberband command adapters.

The legacy project bundled binaries. This project keeps the capability but
expects tools to be installed externally or configured by path.
"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class AudioToolAvailability:
    executable: str
    available: bool
    resolved_path: str | None


def detect_audio_tool(executable: str) -> AudioToolAvailability:
    resolved = shutil.which(executable)
    return AudioToolAvailability(
        executable=executable,
        available=resolved is not None,
        resolved_path=resolved,
    )


@dataclass(frozen=True)
class FfmpegConfig:
    executable: str = "ffmpeg"
    sample_rate: int = 44_100
    channels: int = 2


class FfmpegAudioStandardizer:
    """Convert arbitrary audio files to the internal wav format with ffmpeg."""

    def __init__(self, config: FfmpegConfig | None = None) -> None:
        self._config = config or FfmpegConfig()

    def standardize(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._command(source_path, output_path), check=True)
        if not output_path.exists():
            raise FileNotFoundError(f"ffmpeg did not create {output_path}")
        return output_path

    def _command(self, source_path: Path, output_path: Path) -> list[str]:
        return [
            self._config.executable,
            "-y",
            "-i",
            str(source_path),
            "-ar",
            str(self._config.sample_rate),
            "-ac",
            str(self._config.channels),
            str(output_path),
        ]


@dataclass(frozen=True)
class RubberbandConfig:
    executable: str = "rubberband"
    pitch_semitones: float = 0.0
    time_ratio: float = 1.0


class RubberbandTimePitchProcessor:
    """Optional wrapper for high quality external time-stretch/pitch-shift."""

    def __init__(self, config: RubberbandConfig | None = None) -> None:
        self._config = config or RubberbandConfig()

    def process(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._command(source_path, output_path), check=True)
        if not output_path.exists():
            raise FileNotFoundError(f"rubberband did not create {output_path}")
        return output_path

    def _command(self, source_path: Path, output_path: Path) -> list[str]:
        command = [self._config.executable]
        if self._config.pitch_semitones:
            command.extend(["--pitch", str(self._config.pitch_semitones)])
        if self._config.time_ratio != 1.0:
            command.extend(["--time", str(self._config.time_ratio)])
        command.extend([str(source_path), str(output_path)])
        return command
