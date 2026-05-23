import json
import os
from pathlib import Path

import numpy as np

from core_engine.importer import SongImportConfig, import_single_song
from core_engine.external_tools import FfmpegAudioStandardizer
from core_engine.player.demucs_soundfile_runner import save_audio_with_soundfile
from core_engine.player.stem_separator import DemucsSeparatorConfig, DemucsStemSeparator, PreviewStemSeparator
from core_engine.player.sync_buffer import read_audio, write_audio
from core_engine.transcription import PreviewLyricsTranscriber


def test_import_single_song_creates_project_stems_and_manifest(tmp_path):
    sample_rate = 16_000
    time = np.arange(1_600, dtype=np.float32) / sample_rate
    source_audio = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, None]
    source_path = tmp_path / "My Song.wav"
    lyrics_path = tmp_path / "My Song.lrc"
    write_audio(source_path, source_audio, sample_rate)
    lyrics_path.write_text("[00:00.000]hello", encoding="utf-8")

    project = import_single_song(
        SongImportConfig(
            source_path=source_path,
            projects_root=tmp_path / "projects",
            separator=PreviewStemSeparator(),
        )
    )

    vocal, vocal_rate = read_audio(project.stems.vocal_path)
    instrumental, instrumental_rate = read_audio(project.stems.instrumental_path)
    manifest = json.loads((project.project_dir / "project.json").read_text(encoding="utf-8"))

    assert project.project_dir.name == "My_Song"
    assert project.source_path.exists()
    assert project.lyrics_path is not None
    assert project.lyrics_path.name == "lyrics.lrc"
    assert vocal.shape == instrumental.shape == source_audio.shape
    assert vocal_rate == instrumental_rate == sample_rate
    assert manifest["lyrics_path"] == str(project.lyrics_path)
    assert manifest["separator_backend"] == "preview"
    assert manifest["lyrics_backend"] == "none"
    assert manifest["standardized_audio"] is False
    assert manifest["copied_source"] is True


def test_import_single_song_uses_unique_project_dirs(tmp_path):
    source_path = tmp_path / "song.wav"
    write_audio(source_path, np.zeros((200, 1), dtype=np.float32), 1_000)

    first = import_single_song(SongImportConfig(source_path, tmp_path / "projects"))
    second = import_single_song(SongImportConfig(source_path, tmp_path / "projects"))

    assert first.project_dir.name == "song"
    assert second.project_dir.name == "song_2"


def test_import_single_song_can_generate_preview_lyrics(tmp_path):
    source_path = tmp_path / "song.wav"
    write_audio(source_path, np.zeros((1_000, 1), dtype=np.float32), 1_000)

    project = import_single_song(
        SongImportConfig(
            source_path,
            tmp_path / "projects",
            lyrics_transcriber=PreviewLyricsTranscriber(),
        )
    )

    assert project.lyrics_path is not None
    assert project.lyrics_path.name == "lyrics.lrc"
    assert "未找到歌词文件" in project.lyrics_path.read_text(encoding="utf-8")


def test_import_single_song_can_standardize_audio_before_separation(tmp_path):
    class CopyStandardizer(FfmpegAudioStandardizer):
        def standardize(self, source_path, output_path):
            output_path.write_bytes(source_path.read_bytes())
            return output_path

    source_path = tmp_path / "song.wav"
    write_audio(source_path, np.zeros((200, 1), dtype=np.float32), 1_000)

    project = import_single_song(
        SongImportConfig(
            source_path,
            tmp_path / "projects",
            audio_standardizer=CopyStandardizer(),
        )
    )

    assert project.source_path.name == "original_standard.wav"
    assert project.source_path.exists()
    manifest = json.loads((project.project_dir / "project.json").read_text(encoding="utf-8"))
    assert manifest["standardized_audio"] is True


def test_demucs_separator_builds_cpu_command():
    separator = DemucsStemSeparator(
        DemucsSeparatorConfig(executable="py", model_name="htdemucs", device="cpu")
    )

    command = separator._command(Path("song.wav"), Path("out"))

    assert command == [
        "py",
        "-m",
        "core_engine.player.demucs_soundfile_runner",
        "--two-stems",
        "vocals",
        "-n",
        "htdemucs",
        "-d",
        "cpu",
        "-o",
        "out",
        "--segment",
        "7",
        "song.wav",
    ]


def test_demucs_separator_can_use_runner_script():
    separator = DemucsStemSeparator(
        DemucsSeparatorConfig(executable="py", runner_script=Path("runner.py"))
    )

    command = separator._command(Path("song.wav"), Path("out"))

    assert command[:2] == ["py", "runner.py"]
    assert "-m" not in command


def test_demucs_separator_can_inject_local_runtime_environment(tmp_path, monkeypatch):
    ffmpeg_dir = tmp_path / "ffmpeg"
    torch_home = tmp_path / "torch"
    separator = DemucsStemSeparator(
        DemucsSeparatorConfig(ffmpeg_dir=ffmpeg_dir, torch_home=torch_home)
    )
    monkeypatch.setenv("PATH", "existing-path")

    environment = separator._environment()

    assert environment["TORCH_HOME"] == str(torch_home)
    assert environment["PATH"].split(os.pathsep)[0] == str(ffmpeg_dir)


def test_demucs_soundfile_runner_writes_wav_without_torchaudio(tmp_path):
    import torch

    output_path = tmp_path / "stem.wav"
    wav = torch.zeros((2, 1_000), dtype=torch.float32)

    save_audio_with_soundfile(wav, output_path, samplerate=16_000)

    audio, sample_rate = read_audio(output_path)
    assert audio.shape == (1_000, 2)
    assert sample_rate == 16_000
