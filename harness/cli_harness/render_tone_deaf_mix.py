"""Render a tone-deaf vocal buffer and export a mixed wav."""

import argparse
from pathlib import Path

from core_engine.dsp.tone_deaf import ToneDeafConfig
from core_engine.dsp.tone_deaf_cache import ToneDeafBufferCache
from core_engine.player.sync_buffer import load_stem_pair, mix_aligned_tracks, write_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render tone-deaf vocal and export a mixed wav.")
    parser.add_argument("--vocal", required=True, type=Path)
    parser.add_argument("--instrumental", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ratio", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--vocal-gain", type=float, default=1.0)
    parser.add_argument("--instrumental-gain", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    buffers = load_stem_pair(args.vocal, args.instrumental)
    rendered = ToneDeafBufferCache().render_buffer(
        buffers,
        ToneDeafConfig(drift_ratio=args.ratio, random_seed=args.seed),
    )
    mixed = mix_aligned_tracks(
        rendered,
        vocal_gain=args.vocal_gain,
        instrumental_gain=args.instrumental_gain,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_audio(args.output, mixed, rendered.sample_rate)
    print(
        f"wrote {args.output} frames={mixed.shape[0]} "
        f"sample_rate={rendered.sample_rate} ratio={args.ratio}"
    )


if __name__ == "__main__":
    main()

