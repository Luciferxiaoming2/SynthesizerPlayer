"""Run the tone-deaf DSP path without the UI."""

import argparse
from pathlib import Path

from core_engine.dsp.tone_deaf import ToneDeafConfig, render_tone_deaf_vocal
from core_engine.player.sync_buffer import read_audio, write_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render tone-deaf vocal drift offline.")
    parser.add_argument("--input", required=True, type=Path, help="Input vocal wav path.")
    parser.add_argument("--output", required=True, type=Path, help="Rendered wav path.")
    parser.add_argument("--ratio", required=True, type=float, help="Drift ratio from 0.01 to 0.80.")
    parser.add_argument("--seed", type=int, default=7, help="Deterministic random seed.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    vocal, sample_rate = read_audio(args.input)
    rendered = render_tone_deaf_vocal(
        vocal=vocal,
        sample_rate=sample_rate,
        config=ToneDeafConfig(drift_ratio=args.ratio, random_seed=args.seed),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_audio(args.output, rendered, sample_rate)
    print(f"wrote {args.output} frames={rendered.shape[0]} sample_rate={sample_rate}")


if __name__ == "__main__":
    main()
