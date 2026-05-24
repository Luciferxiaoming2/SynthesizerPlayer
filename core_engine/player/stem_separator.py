"""Adapters for stem separation backends such as Demucs, Spleeter, or UVR5."""

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import shutil
from collections.abc import Sequence

import numpy as np

from core_engine.player.sync_buffer import read_audio, write_audio


@dataclass(frozen=True)
class StemPair:
    vocal_path: Path
    instrumental_path: Path


class StemSeparator:
    """Boundary object for invoking external stem separation engines."""

    def separate(self, source_path: Path, output_dir: Path) -> StemPair:
        raise NotImplementedError("Wire this to Spleeter, UVR5, or another separator")


class PreviewStemSeparator(StemSeparator):
    """Deterministic lightweight separator for import flow testing.

    This is not real source separation. It creates a plausible vocal/accompaniment
    split so the engineering workflow can run before a heavy model is configured.
    """

    def separate(self, source_path: Path, output_dir: Path) -> StemPair:
        output_dir.mkdir(parents=True, exist_ok=True)
        audio, sample_rate = read_audio(source_path)
        time = np.arange(audio.shape[0], dtype=np.float32) / sample_rate
        envelope = (0.5 + 0.5 * np.sin(2.0 * np.pi * 0.7 * time))[:, np.newaxis]
        vocal = np.asarray(audio * (0.42 + 0.18 * envelope), dtype=np.float32)
        instrumental = np.asarray(audio - vocal * 0.55, dtype=np.float32)
        pair = StemPair(output_dir / "vocal.wav", output_dir / "instrumental.wav")
        write_audio(pair.vocal_path, vocal, sample_rate)
        write_audio(pair.instrumental_path, instrumental, sample_rate)
        return pair


class ExternalCommandStemSeparator(StemSeparator):
    """Command adapter for external stem separation runtimes."""

    def __init__(self, command_template: Sequence[str]) -> None:
        if not command_template:
            raise ValueError("command_template must not be empty")
        self._command_template = tuple(command_template)

    def separate(self, source_path: Path, output_dir: Path) -> StemPair:
        output_dir.mkdir(parents=True, exist_ok=True)
        pair = StemPair(output_dir / "vocal.wav", output_dir / "instrumental.wav")
        subprocess.run(self._render_command(source_path, output_dir, pair), check=True)
        if not pair.vocal_path.exists() or not pair.instrumental_path.exists():
            raise FileNotFoundError(
                "external separator must create vocal.wav and instrumental.wav "
                f"inside {output_dir}"
            )
        return pair

    def _render_command(self, source_path: Path, output_dir: Path, pair: StemPair) -> list[str]:
        values = {
            "source": str(source_path),
            "output_dir": str(output_dir),
            "vocal": str(pair.vocal_path),
            "instrumental": str(pair.instrumental_path),
        }
        return [part.format(**values) for part in self._command_template]


@dataclass(frozen=True)
class DemucsSeparatorConfig:
    executable: str = "python"
    model_name: str = "htdemucs"
    device: str = "cpu"
    two_stems: str = "vocals"
    segment: int | None = 7
    jobs: int = 1
    ffmpeg_dir: Path | None = None
    torch_home: Path | None = None
    prefer_python_api: bool = True
    use_soundfile_writer: bool = True
    runner_script: Path | None = None


class DemucsStemSeparator(StemSeparator):
    """Adapter for the open-source Demucs command line separator."""

    def __init__(self, config: DemucsSeparatorConfig | None = None) -> None:
        self._config = config or DemucsSeparatorConfig()

    def separate(self, source_path: Path, output_dir: Path) -> StemPair:
        output_dir.mkdir(parents=True, exist_ok=True)
        work_dir = output_dir / "_demucs"

        # Demucs 会输出到 <out>/<model>/<歌曲名>/vocals.wav 和 no_vocals.wav；
        # 这里统一搬运成项目内部固定命名，避免后续播放/导出层关心后端差异。
        completed = subprocess.run(
            self._command(source_path, work_dir),
            env=self._environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            detail = demucs_error_detail(completed.stdout, completed.stderr)
            raise RuntimeError(f"Demucs 人声分离执行失败：{detail}")
        demucs_song_dir = work_dir / self._config.model_name / source_path.stem
        source_vocal = demucs_song_dir / "vocals.wav"
        source_instrumental = demucs_song_dir / "no_vocals.wav"
        if not source_vocal.exists() or not source_instrumental.exists():
            raise FileNotFoundError(
                "Demucs did not create expected vocals.wav/no_vocals.wav "
                f"under {demucs_song_dir}"
            )

        pair = StemPair(output_dir / "vocal.wav", output_dir / "instrumental.wav")
        shutil.copyfile(source_vocal, pair.vocal_path)
        shutil.copyfile(source_instrumental, pair.instrumental_path)
        return pair

    def _command(self, source_path: Path, work_dir: Path) -> list[str]:
        command = [self._config.executable]
        if self._config.use_soundfile_writer and self._config.runner_script is not None:
            command.append(str(self._config.runner_script))
        else:
            command.extend(
                [
                    "-m",
                    "core_engine.player.demucs_soundfile_runner"
                    if self._config.use_soundfile_writer
                    else "demucs",
                ]
            )
        command.extend([
            "--two-stems",
            self._config.two_stems,
            "-n",
            self._config.model_name,
            "-d",
            self._config.device,
            "-o",
            str(work_dir),
        ])
        if self._config.segment is not None:
            command.extend(["--segment", str(self._config.segment)])
        if self._config.jobs > 1:
            command.extend(["-j", str(self._config.jobs)])
        command.append(str(source_path))
        return command

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if self._config.torch_home is not None:
            environment["TORCH_HOME"] = str(self._config.torch_home)
        if self._config.ffmpeg_dir is not None:
            existing_path = environment.get("PATH", "")
            environment["PATH"] = str(self._config.ffmpeg_dir) + os.pathsep + existing_path
        return environment


def demucs_error_detail(stdout: str | None, stderr: str | None) -> str:
    lines = [line.strip() for line in ((stderr or "") + "\n" + (stdout or "")).splitlines()]
    detail_lines = [line for line in lines if line][-10:]
    return " / ".join(detail_lines) if detail_lines else "外部进程没有返回错误详情"
