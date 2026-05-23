"""Adapters for generating editable lyrics when no LRC/SRT file exists."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
from collections.abc import Sequence

from core_engine.player.sync_buffer import read_audio


@dataclass(frozen=True)
class LyricsTranscriptionRequest:
    audio_path: Path
    output_path: Path


class LyricsTranscriber:
    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        raise NotImplementedError("Wire this adapter to Whisper, faster-whisper, or another ASR backend")


class PreviewLyricsTranscriber(LyricsTranscriber):
    """Writes a deterministic placeholder LRC so the import workflow is complete."""

    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        audio, sample_rate = read_audio(request.audio_path)
        duration_seconds = audio.shape[0] / sample_rate
        midpoint_ms = max(0, round(duration_seconds * 500.0))

        # 这不是 ASR 结果，只是让没有歌词的歌曲也能进入“可编辑时间轴”。
        # 后续接 faster-whisper 时，只需要替换这个 adapter。
        request.output_path.write_text(
            "\n".join(
                [
                    "[00:00.000]未找到歌词文件",
                    f"[{format_lrc_timestamp(midpoint_ms)}]请导入 .lrc/.srt，或使用 faster-whisper 识别原始语言歌词",
                ]
            ),
            encoding="utf-8",
        )
        return request.output_path


class ExternalCommandLyricsTranscriber(LyricsTranscriber):
    """Command adapter for optional ASR tools such as faster-whisper."""

    def __init__(self, command_template: Sequence[str]) -> None:
        if not command_template:
            raise ValueError("command_template must not be empty")
        self._command_template = tuple(command_template)

    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._render_command(request), check=True)
        if not request.output_path.exists():
            raise FileNotFoundError(f"external transcriber did not create {request.output_path}")
        return request.output_path

    def _render_command(self, request: LyricsTranscriptionRequest) -> list[str]:
        values = {
            "audio": str(request.audio_path),
            "output": str(request.output_path),
            "output_dir": str(request.output_path.parent),
        }
        return [part.format(**values) for part in self._command_template]


@dataclass(frozen=True)
class FasterWhisperConfig:
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = None
    beam_size: int = 5


class FasterWhisperLyricsTranscriber(LyricsTranscriber):
    """Local ASR adapter for faster-whisper.

    The import is intentionally lazy so the app can run without faster-whisper installed.
    """

    def __init__(self, config: FasterWhisperConfig | None = None) -> None:
        self._config = config or FasterWhisperConfig()

    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install it only when real ASR is needed."
            ) from exc

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(
            self._config.model_size,
            device=self._config.device,
            compute_type=self._config.compute_type,
        )
        segments, _info = model.transcribe(
            str(request.audio_path),
            language=self._config.language,
            beam_size=self._config.beam_size,
        )

        lines = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            start_ms = round(float(segment.start) * 1000.0)
            lines.append(f"[{format_lrc_timestamp(start_ms)}]{text}")

        if not lines:
            lines = ["[00:00.000]No lyrics detected"]
        request.output_path.write_text("\n".join(lines), encoding="utf-8")
        return request.output_path


def format_lrc_timestamp(position_ms: int) -> str:
    minutes, remainder = divmod(max(0, position_ms), 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"
