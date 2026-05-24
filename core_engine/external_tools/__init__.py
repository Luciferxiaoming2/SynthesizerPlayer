"""Optional external audio tool adapters."""

from core_engine.external_tools.audio_tools import (
    AudioToolAvailability,
    FfmpegAudioStandardizer,
    FfmpegConfig,
    FfmpegMp3Config,
    FfmpegMp3Encoder,
    RubberbandConfig,
    RubberbandTimePitchProcessor,
    detect_audio_tool,
    project_audio_tool_dirs,
    resolve_audio_tool,
)

__all__ = [
    "AudioToolAvailability",
    "FfmpegAudioStandardizer",
    "FfmpegConfig",
    "FfmpegMp3Config",
    "FfmpegMp3Encoder",
    "RubberbandConfig",
    "RubberbandTimePitchProcessor",
    "detect_audio_tool",
    "project_audio_tool_dirs",
    "resolve_audio_tool",
]
