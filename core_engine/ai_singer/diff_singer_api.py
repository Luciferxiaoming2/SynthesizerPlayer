"""DiffSinger-style adapters for lyric-to-vocal synthesis."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from collections.abc import Sequence

import numpy as np

from core_engine.player.sync_buffer import read_audio, write_audio


@dataclass(frozen=True)
class SingingSegmentRequest:
    lyric: str
    melody_path: Path
    output_path: Path
    sample_rate: int = 16_000
    duration_seconds: float = 2.0


@dataclass(frozen=True)
class LyricContentEditRequest:
    lyric: str
    source_vocal_path: Path
    melody_path: Path
    output_path: Path
    sample_rate: int = 16_000
    duration_seconds: float = 2.0
    start_ms: int = 0
    end_ms: int = 0


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


class LocalSpeechSingingClient(DiffSingerClient):
    """CPU-only local rewrite preview using Windows SAPI speech synthesis.

    This is not a full singing model. It creates an audible local replacement
    voice for lightweight laptops so the lyric-edit workflow can be heard
    without GPU models or cloud inference.
    """

    def __init__(self, fallback: DiffSingerClient | None = None) -> None:
        self._fallback = fallback

    def synthesize(self, request: SingingSegmentRequest) -> Path:
        if sys.platform != "win32":
            if self._fallback is not None:
                return self._fallback.synthesize(request)
            raise RuntimeError("本机轻量改词唱需要 Windows 系统语音组件")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        language = lyric_language_hint(request.lyric)
        script_path = request.output_path.with_suffix(".sapi.ps1")
        lyric_path = request.output_path.with_suffix(".lyric.txt")
        lyric_path.write_text(request.lyric, encoding="utf-8")
        script_path.write_text(
            "\n".join(
                [
                    "param([string]$lyricPath, [string]$outPath, [string]$target)",
                    "$lyric = [System.IO.File]::ReadAllText($lyricPath, [System.Text.Encoding]::UTF8)",
                    "Add-Type -AssemblyName System.Speech",
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                    "$voice = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $target } | Select-Object -First 1",
                    "if ($voice -ne $null) { $s.SelectVoice($voice.VoiceInfo.Name) }",
                    "$s.Rate = -1",
                    "$s.Volume = 100",
                    "$s.SetOutputToWaveFile($outPath)",
                    "$s.Speak($lyric)",
                    "$s.Dispose()",
                ]
            ),
            encoding="utf-8",
        )
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    str(lyric_path),
                    str(request.output_path),
                    language,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not request.output_path.exists():
                raise FileNotFoundError(request.output_path)
            audio, sample_rate = read_audio(request.output_path)
            if audio.size == 0 or sample_rate <= 0:
                raise ValueError("empty local speech output")
            if float(np.max(np.abs(audio))) < 0.005:
                raise ValueError("silent local speech output")
            return request.output_path
        except Exception as exc:
            if self._fallback is not None:
                return self._fallback.synthesize(request)
            raise RuntimeError(f"本机语音合成不可用：{exc}") from exc
        finally:
            try:
                script_path.unlink()
            except OSError:
                pass
            try:
                lyric_path.unlink()
            except OSError:
                pass


def lyric_language_hint(lyric: str) -> str:
    cjk_count = sum(1 for char in lyric if "\u4e00" <= char <= "\u9fff")
    latin_count = sum(1 for char in lyric if char.isascii() and char.isalpha())
    return "zh" if cjk_count >= max(1, latin_count // 3) else "en"


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


class LyricContentEditor:
    def edit(self, request: LyricContentEditRequest) -> Path:
        raise NotImplementedError("Wire this adapter to a lyric/content editing runtime")


class ExternalLyricContentEditor(LyricContentEditor):
    """Command adapter for Vevo-style lyric/content editing runtimes."""

    def __init__(self, command_template: Sequence[str], extra_values: dict[str, str] | None = None) -> None:
        if not command_template:
            raise ValueError("command_template must not be empty")
        self._command_template = tuple(command_template)
        self._extra_values = dict(extra_values or {})

    def edit(self, request: LyricContentEditRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._render_command(request), check=True)
        if not request.output_path.exists():
            raise FileNotFoundError(f"external lyric content editor did not create {request.output_path}")
        return request.output_path

    def _render_command(self, request: LyricContentEditRequest) -> list[str]:
        values = {
            "lyric": request.lyric,
            "source": str(request.source_vocal_path),
            "melody": str(request.melody_path),
            "output": str(request.output_path),
            "sample_rate": str(request.sample_rate),
            "duration": str(request.duration_seconds),
            "start_ms": str(request.start_ms),
            "end_ms": str(request.end_ms),
        }
        values.update(self._extra_values)
        return [part.format(**values) for part in self._command_template]
