from pathlib import Path

from core_engine.external_tools import (
    FfmpegAudioStandardizer,
    FfmpegConfig,
    RubberbandConfig,
    RubberbandTimePitchProcessor,
    detect_audio_tool,
)


def test_detect_audio_tool_reports_missing_tool_name():
    result = detect_audio_tool("definitely_missing_audio_forge_tool")

    assert result.executable == "definitely_missing_audio_forge_tool"
    assert result.available is False
    assert result.resolved_path is None


def test_ffmpeg_standardizer_builds_command():
    standardizer = FfmpegAudioStandardizer(FfmpegConfig("ffmpeg-custom", 48_000, 1))

    command = standardizer._command(Path("in.mp3"), Path("out.wav"))

    assert command == [
        "ffmpeg-custom",
        "-y",
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
