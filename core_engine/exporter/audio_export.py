"""Unified offline export workflow for processed dual-track audio."""

from dataclasses import dataclass, field
from pathlib import Path

from core_engine.dsp.tone_deaf import ToneDeafConfig
from core_engine.dsp.tone_deaf_cache import ToneDeafBufferCache
from core_engine.dsp.vst_host import OfflineEffectConfig, VstEffectChain
from core_engine.player.sync_buffer import (
    StereoTrackBuffer,
    load_stem_pair,
    mix_aligned_tracks,
    write_audio,
)


@dataclass(frozen=True)
class AudioExportConfig:
    vocal_path: Path
    instrumental_path: Path
    output_path: Path
    vocal_gain: float = 1.0
    instrumental_gain: float = 1.0
    vocal_effect_gain_db: float = 0.0
    instrumental_effect_gain_db: float = 0.0
    master_gain_db: float = 0.0
    tone_deaf_ratio: float | None = None
    tone_deaf_seed: int = 7
    vocal_plugins: list[Path] = field(default_factory=list)
    instrumental_plugins: list[Path] = field(default_factory=list)
    master_plugins: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class AudioExportResult:
    output_path: Path
    frame_count: int
    sample_rate: int
    duration_seconds: float


def export_processed_mix(config: AudioExportConfig) -> AudioExportResult:
    buffers = load_stem_pair(config.vocal_path, config.instrumental_path)

    if config.tone_deaf_ratio is not None:
        buffers = ToneDeafBufferCache().render_buffer(
            buffers,
            ToneDeafConfig(
                drift_ratio=config.tone_deaf_ratio,
                random_seed=config.tone_deaf_seed,
            ),
        )

    buffers = StereoTrackBuffer(
        vocal=process_effect_chain(
            buffers.vocal,
            buffers.sample_rate,
            config.vocal_effect_gain_db,
            config.vocal_plugins,
        ),
        instrumental=process_effect_chain(
            buffers.instrumental,
            buffers.sample_rate,
            config.instrumental_effect_gain_db,
            config.instrumental_plugins,
        ),
        sample_rate=buffers.sample_rate,
    )

    mixed = mix_aligned_tracks(
        buffers,
        vocal_gain=config.vocal_gain,
        instrumental_gain=config.instrumental_gain,
    )
    mixed = process_effect_chain(
        mixed,
        buffers.sample_rate,
        config.master_gain_db,
        config.master_plugins,
    )

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    write_audio(config.output_path, mixed, buffers.sample_rate)
    return AudioExportResult(
        output_path=config.output_path,
        frame_count=mixed.shape[0],
        sample_rate=buffers.sample_rate,
        duration_seconds=buffers.duration_seconds,
    )


def process_effect_chain(
    audio,
    sample_rate: int,
    gain_db: float,
    plugin_paths: list[Path],
):
    chain = VstEffectChain(OfflineEffectConfig(gain_db=gain_db))
    for plugin_path in plugin_paths:
        chain.add_plugin(plugin_path)
    return chain.process(audio, sample_rate)

