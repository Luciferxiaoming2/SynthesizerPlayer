"""Lyrics transcription adapters."""

from core_engine.transcription.lyrics_transcriber import (
    ExternalCommandLyricsTranscriber,
    FasterWhisperConfig,
    FasterWhisperLyricsTranscriber,
    LyricsTranscriptionRequest,
    LyricsTranscriber,
    PreviewLyricsTranscriber,
    is_instruction_hallucination,
    normalize_generated_lyric_text,
)

__all__ = [
    "ExternalCommandLyricsTranscriber",
    "FasterWhisperConfig",
    "FasterWhisperLyricsTranscriber",
    "LyricsTranscriptionRequest",
    "LyricsTranscriber",
    "PreviewLyricsTranscriber",
    "is_instruction_hallucination",
    "normalize_generated_lyric_text",
]
