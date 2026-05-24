"""Optional ffmpeg/rubberband command adapters."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class AudioToolAvailability:
    executable: str
    available: bool
    resolved_path: str | None
    source: str = "missing"


def detect_audio_tool(
    executable: str,
    search_dirs: list[Path] | tuple[Path, ...] | None = None,
) -> AudioToolAvailability:
    for directory in search_dirs or ():
        candidate = directory / executable
        if candidate.exists():
            return AudioToolAvailability(executable, True, str(candidate), "local")
        if not executable.lower().endswith(".exe"):
            windows_candidate = directory / f"{executable}.exe"
            if windows_candidate.exists():
                return AudioToolAvailability(executable, True, str(windows_candidate), "local")

    resolved = shutil.which(executable)
    return AudioToolAvailability(
        executable=executable,
        available=resolved is not None,
        resolved_path=resolved,
        source="path" if resolved is not None else "missing",
    )


def project_audio_tool_dirs(root: Path) -> list[Path]:
    """Return local tool directories in preferred order.

    The migrated app prefers tools placed under plugins/models, but also reuses
    the legacy source folder when it is present locally.
    """

    return [
        root / "plugins" / "models" / "ffmpeg",
        root / "源代码" / "Synthesizer Player" / "Synthesizer Player" / "ffmpeg" / "bin",
    ]


def resolve_audio_tool(executable: str, root: Path | None = None) -> str:
    search_dirs = project_audio_tool_dirs(root) if root is not None else None
    result = detect_audio_tool(executable, search_dirs=search_dirs)
    if not result.available or result.resolved_path is None:
        raise FileNotFoundError(f"{executable} not found")
    return result.resolved_path


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
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-ar",
            str(self._config.sample_rate),
            "-ac",
            str(self._config.channels),
            str(output_path),
        ]


@dataclass(frozen=True)
class FfmpegMp3Config:
    executable: str = "ffmpeg"
    bitrate: str = "192k"


class FfmpegMp3Encoder:
    """Encode an exported wav mix to mp3 with ffmpeg."""

    def __init__(self, config: FfmpegMp3Config | None = None) -> None:
        self._config = config or FfmpegMp3Config()

    def encode(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._command(source_path, output_path), check=True)
        if not output_path.exists():
            raise FileNotFoundError(f"ffmpeg did not create {output_path}")
        return output_path

    def _command(self, source_path: Path, output_path: Path) -> list[str]:
        return [
            self._config.executable,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            self._config.bitrate,
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
