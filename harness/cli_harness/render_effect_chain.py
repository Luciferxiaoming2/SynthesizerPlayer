"""Render an offline effect/VST chain to an audio file."""

import argparse
from pathlib import Path

from core_engine.dsp.vst_host import OfflineEffectConfig, VstEffectChain
from core_engine.player.sync_buffer import read_audio, write_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render offline gain and optional VST plugins.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gain-db", type=float, default=0.0)
    parser.add_argument("--plugin", action="append", type=Path, default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    audio, sample_rate = read_audio(args.input)
    chain = VstEffectChain(OfflineEffectConfig(gain_db=args.gain_db))
    for plugin in args.plugin:
        chain.add_plugin(plugin)

    processed = chain.process(audio, sample_rate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_audio(args.output, processed, sample_rate)
    print(
        f"wrote {args.output} frames={processed.shape[0]} "
        f"sample_rate={sample_rate} plugins={len(args.plugin)} gain_db={args.gain_db}"
    )


if __name__ == "__main__":
    main()

