"""Render an offline mix of aligned vocal and instrumental stems."""

import argparse
from pathlib import Path

from core_engine.player.sync_buffer import load_stem_pair, mix_aligned_tracks, write_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mix aligned vocal and instrumental stems.")
    parser.add_argument("--vocal", required=True, type=Path)
    parser.add_argument("--instrumental", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vocal-gain", type=float, default=1.0)
    parser.add_argument("--instrumental-gain", type=float, default=1.0)
    parser.add_argument("--alignment", choices=["strict", "pad", "trim"], default="pad")
    parser.add_argument("--no-clip", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    buffers = load_stem_pair(args.vocal, args.instrumental, alignment=args.alignment)
    mixed = mix_aligned_tracks(
        buffers,
        vocal_gain=args.vocal_gain,
        instrumental_gain=args.instrumental_gain,
        clip=not args.no_clip,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_audio(args.output, mixed, buffers.sample_rate)
    print(
        f"wrote {args.output} frames={mixed.shape[0]} "
        f"sample_rate={buffers.sample_rate} duration={buffers.duration_seconds:.3f}s"
    )


if __name__ == "__main__":
    main()

