"""Run the tone-deaf DSP path without the UI."""

import argparse
from pathlib import Path

from core_engine.dsp.tone_deaf import ToneDeafConfig, render_tone_deaf_vocal
from core_engine.player.sync_buffer import read_audio, write_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="离线渲染明显跑调的人声音轨。")
    parser.add_argument("--input", required=True, type=Path, help="输入人声 wav 路径。")
    parser.add_argument("--output", required=True, type=Path, help="输出 wav 路径。")
    parser.add_argument("--ratio", required=True, type=float, help="跑调强度，范围 0.0 到 1.0。")
    parser.add_argument("--seed", type=int, default=7, help="固定随机种子，便于复现。")
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
