import numpy as np

from core_engine.ai_singer import (
    BypassRvcInferencer,
    LyricRewriteSingingRequest,
    LyricRewriteSingingWorkflow,
    PreviewSingingClient,
)
from core_engine.player.sync_buffer import read_audio


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
