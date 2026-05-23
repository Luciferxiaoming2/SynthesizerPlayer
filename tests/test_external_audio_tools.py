from pathlib import Path

from core_engine.external_tools import (
    FfmpegAudioStandardizer,
    FfmpegConfig,
    RubberbandConfig,
    RubberbandTimePitchProcessor,
    detect_audio_tool,
    project_audio_tool_dirs,
    resolve_audio_tool,
)


def test_detect_audio_tool_reports_missing_tool_name():
    result = detect_audio_tool("definitely_missing_audio_forge_tool")

    assert result.executable == "definitely_missing_audio_forge_tool"
    assert result.available is False
    assert result.resolved_path is None
    assert result.source == "missing"


def test_detect_audio_tool_prefers_local_search_dirs(tmp_path):
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    executable = tool_dir / "ffmpeg.exe"
    executable.write_text("fake", encoding="utf-8")

    result = detect_audio_tool("ffmpeg", search_dirs=[tool_dir])

    assert result.available is True
    assert result.resolved_path == str(executable)
    assert result.source == "local"


def test_resolve_audio_tool_returns_local_path(tmp_path):
    ffmpeg_dir = tmp_path / "plugins" / "models" / "ffmpeg"
    ffmpeg_dir.mkdir(parents=True)
    executable = ffmpeg_dir / "ffmpeg.exe"
    executable.write_text("fake", encoding="utf-8")

    assert resolve_audio_tool("ffmpeg", tmp_path) == str(executable)


def test_project_audio_tool_dirs_include_migrated_and_legacy_locations(tmp_path):
    dirs = project_audio_tool_dirs(tmp_path)

    assert dirs[0] == tmp_path / "plugins" / "models" / "ffmpeg"
    assert dirs[1] == (
        tmp_path / "源代码" / "Synthesizer Player" / "Synthesizer Player" / "ffmpeg" / "bin"
    )


def test_ffmpeg_standardizer_builds_command():
    standardizer = FfmpegAudioStandardizer(FfmpegConfig("ffmpeg-custom", 48_000, 1))

    command = standardizer._command(Path("in.mp3"), Path("out.wav"))

    assert command == [
        "ffmpeg-custom",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "in.mp3",
        "-ar",
        "48000",
        "-ac",
        "1",
        "out.wav",
    ]


def test_rubberband_processor_builds_command():
    processor = RubberbandTimePitchProcessor(
        RubberbandConfig("rubberband-custom", pitch_semitones=2.0, time_ratio=1.1)
    )

    command = processor._command(Path("in.wav"), Path("out.wav"))

    assert command == [
        "rubberband-custom",
        "--pitch",
        "2.0",
        "--time",
        "1.1",
        "in.wav",
        "out.wav",
    ]
