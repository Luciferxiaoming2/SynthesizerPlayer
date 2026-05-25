import numpy as np

import pytest

from core_engine.ai_singer import (
    BypassRvcInferencer,
    LocalSpeechSingingClient,
    LyricContentEditRequest,
    LyricContentEditor,
    LyricRewriteSingingRequest,
    LyricRewriteSingingWorkflow,
    PreviewSingingClient,
)
from core_engine.player.sync_buffer import write_audio
from core_engine.player.sync_buffer import read_audio


class CopyingContentEditor(LyricContentEditor):
    def edit(self, request: LyricContentEditRequest):
        audio, sample_rate = read_audio(request.source_vocal_path)
        write_audio(request.output_path, audio, sample_rate)
        return request.output_path


def test_preview_singing_workflow_writes_vocal(tmp_path):
    output_path = tmp_path / "rewrite.wav"

    result = LyricRewriteSingingWorkflow(PreviewSingingClient()).run(
        LyricRewriteSingingRequest(
            lyric="hello new lyric",
            melody_path=tmp_path / "melody.mid",
            output_path=output_path,
            sample_rate=16_000,
            duration_seconds=0.25,
        )
    )

    audio, sample_rate = read_audio(output_path)
    assert result.output_path == output_path
    assert result.used_voice_conversion is False
    assert sample_rate == 16_000
    assert audio.shape == (4_000, 1)
    assert float(np.max(np.abs(audio))) > 0.01


def test_local_speech_singing_client_reports_when_sapi_is_unavailable(tmp_path, monkeypatch):
    output_path = tmp_path / "rewrite.wav"

    def fail_run(*_args, **_kwargs):
        raise OSError("no powershell")

    monkeypatch.setattr("core_engine.ai_singer.diff_singer_api.subprocess.run", fail_run)

    with pytest.raises(RuntimeError, match="本机语音合成不可用|本机轻量改词唱需要 Windows"):
        LocalSpeechSingingClient().synthesize(
            LyricRewriteSingingRequest(
                lyric="唱出新的歌词",
                melody_path=tmp_path / "melody.wav",
                output_path=output_path,
                sample_rate=16_000,
                duration_seconds=0.25,
            )
        )


def test_local_speech_singing_client_can_use_explicit_preview_fallback(tmp_path, monkeypatch):
    output_path = tmp_path / "rewrite.wav"

    def fail_run(*_args, **_kwargs):
        raise OSError("no powershell")

    monkeypatch.setattr("core_engine.ai_singer.diff_singer_api.subprocess.run", fail_run)

    result = LocalSpeechSingingClient(fallback=PreviewSingingClient()).synthesize(
        LyricRewriteSingingRequest(
            lyric="唱出新的歌词",
            melody_path=tmp_path / "melody.wav",
            output_path=output_path,
            sample_rate=16_000,
            duration_seconds=0.25,
        )
    )

    audio, sample_rate = read_audio(result)
    assert result == output_path
    assert sample_rate == 16_000
    assert float(np.max(np.abs(audio))) > 0.01


def test_workflow_can_route_through_bypass_voice_conversion(tmp_path):
    output_path = tmp_path / "converted.wav"

    result = LyricRewriteSingingWorkflow(PreviewSingingClient(), BypassRvcInferencer()).run(
        LyricRewriteSingingRequest(
            lyric="changed words",
            melody_path=tmp_path / "melody.mid",
            output_path=output_path,
            sample_rate=8_000,
            duration_seconds=0.1,
            rvc_model_path=tmp_path / "voice.pth",
        )
    )

    audio, sample_rate = read_audio(output_path)
    assert result.used_voice_conversion is True
    assert result.synthesized_path != output_path
    assert result.synthesized_path.exists()
    assert sample_rate == 8_000
    assert audio.shape == (800, 1)


def test_workflow_can_route_through_content_editor(tmp_path):
    source_path = tmp_path / "source.wav"
    output_path = tmp_path / "edited.wav"
    write_audio(source_path, np.ones((400, 1), dtype=np.float32) * 0.1, 8_000)

    result = LyricRewriteSingingWorkflow(
        PreviewSingingClient(),
        content_editor=CopyingContentEditor(),
    ).run(
        LyricRewriteSingingRequest(
            lyric="new words",
            melody_path=source_path,
            source_vocal_path=source_path,
            output_path=output_path,
            sample_rate=8_000,
            duration_seconds=0.05,
            start_ms=100,
            end_ms=150,
        )
    )

    audio, sample_rate = read_audio(output_path)
    assert result.used_content_editor is True
    assert result.used_voice_conversion is False
    assert sample_rate == 8_000
    assert audio.shape == (400, 1)
