import numpy as np
import pytest

from core_engine.exporter.audio_export import AudioExportConfig, export_processed_mix
from core_engine.player.sync_buffer import read_audio, write_audio


def write_stem_pair(tmp_path):
    sample_rate = 16_000
    frames = 2_000
    time = np.arange(frames, dtype=np.float32) / sample_rate
    vocal = (0.2 * np.sin(2.0 * np.pi * 220.0 * time))[:, np.newaxis]
    instrumental = (0.1 * np.sin(2.0 * np.pi * 110.0 * time))[:, np.newaxis]
    vocal_path = tmp_path / "vocal.wav"
    instrumental_path = tmp_path / "instrumental.wav"
    write_audio(vocal_path, vocal, sample_rate)
    write_audio(instrumental_path, instrumental, sample_rate)
    return vocal_path, instrumental_path


def test_export_processed_mix_writes_wav(tmp_path):
    vocal_path, instrumental_path = write_stem_pair(tmp_path)
    output_path = tmp_path / "mix.wav"

    result = export_processed_mix(
        AudioExportConfig(
            vocal_path=vocal_path,
            instrumental_path=instrumental_path,
            output_path=output_path,
            vocal_gain=0.5,
            instrumental_gain=0.5,
            master_gain_db=-3.0,
        )
    )

    exported, sample_rate = read_audio(output_path)
    assert result.output_path == output_path
    assert result.frame_count == 2_000
    assert sample_rate == 16_000
    assert exported.shape == (2_000, 1)


def test_export_processed_mix_supports_tone_deaf(tmp_path):
    vocal_path, instrumental_path = write_stem_pair(tmp_path)
    output_path = tmp_path / "tone_deaf_mix.wav"

    result = export_processed_mix(
        AudioExportConfig(
            vocal_path=vocal_path,
            instrumental_path=instrumental_path,
            output_path=output_path,
            tone_deaf_ratio=0.4,
        )
    )

    assert result.frame_count == 2_000
    assert output_path.exists()


def test_export_processed_mix_requires_encoder_for_mp3(tmp_path):
    vocal_path, instrumental_path = write_stem_pair(tmp_path)
    output_path = tmp_path / "mix.mp3"

    with pytest.raises(RuntimeError, match="mp3 export requires ffmpeg"):
        export_processed_mix(
            AudioExportConfig(
                vocal_path=vocal_path,
                instrumental_path=instrumental_path,
                output_path=output_path,
            )
        )
