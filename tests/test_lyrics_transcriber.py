import numpy as np
import pytest

from core_engine.player.sync_buffer import write_audio
from core_engine.transcription import (
    FasterWhisperConfig,
    FasterWhisperLyricsTranscriber,
    LyricsTranscriptionRequest,
    PreviewLyricsTranscriber,
)


def test_preview_lyrics_transcriber_writes_lrc(tmp_path):
    audio_path = tmp_path / "song.wav"
    output_path = tmp_path / "lyrics.lrc"
    write_audio(audio_path, np.zeros((2_000, 1), dtype=np.float32), 1_000)

    result = PreviewLyricsTranscriber().transcribe(
        LyricsTranscriptionRequest(audio_path=audio_path, output_path=output_path)
    )

    text = output_path.read_text(encoding="utf-8")
    assert result == output_path
    assert "[00:00.000]" in text
    assert "[00:01.000]" in text


def test_faster_whisper_transcriber_reports_missing_optional_dependency(tmp_path):
    audio_path = tmp_path / "song.wav"
    write_audio(audio_path, np.zeros((100, 1), dtype=np.float32), 1_000)

    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="faster-whisper is not installed"):
            FasterWhisperLyricsTranscriber(FasterWhisperConfig()).transcribe(
                LyricsTranscriptionRequest(audio_path, tmp_path / "lyrics.lrc")
            )
    else:
        pytest.skip("faster-whisper is installed; missing-dependency path is not applicable")
