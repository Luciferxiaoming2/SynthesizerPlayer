"""Export processed dual-track audio through the unified workflow."""

import argparse
from pathlib import Path

from core_engine.exporter.audio_export import AudioExportConfig, export_processed_mix


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a processed dual-track mix.")
    parser.add_argument("--vocal", required=True, type=Path)
    parser.add_argument("--instrumental", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vocal-gain", type=float, default=1.0)
    parser.add_argument("--instrumental-gain", type=float, default=1.0)
    parser.add_argument("--vocal-effect-gain-db", type=float, default=0.0)
    parser.add_argument("--instrumental-effect-gain-db", type=float, default=0.0)
    parser.add_argument("--master-gain-db", type=float, default=0.0)
    parser.add_argument("--tone-deaf-ratio", type=float, default=None)
    parser.add_argument("--tone-deaf-seed", type=int, default=7)
    parser.add_argument("--vocal-plugin", action="append", type=Path, default=[])
    parser.add_argument("--instrumental-plugin", action="append", type=Path, default=[])
    parser.add_argument("--master-plugin", action="append", type=Path, default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = export_processed_mix(
        AudioExportConfig(
            vocal_path=args.vocal,
            instrumental_path=args.instrumental,
            output_path=args.output,
            vocal_gain=args.vocal_gain,
            instrumental_gain=args.instrumental_gain,
            vocal_effect_gain_db=args.vocal_effect_gain_db,
            instrumental_effect_gain_db=args.instrumental_effect_gain_db,
            master_gain_db=args.master_gain_db,
            tone_deaf_ratio=args.tone_deaf_ratio,
            tone_deaf_seed=args.tone_deaf_seed,
            vocal_plugins=args.vocal_plugin,
            instrumental_plugins=args.instrumental_plugin,
            master_plugins=args.master_plugin,
        )
    )
    print(
        f"wrote {result.output_path} frames={result.frame_count} "
        f"sample_rate={result.sample_rate} duration={result.duration_seconds:.3f}s"
    )


if __name__ == "__main__":
    main()

