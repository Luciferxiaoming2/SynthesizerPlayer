"""Analyze F0 drift between original and processed vocals."""

import argparse
from pathlib import Path

from harness.eval_harness.f0_drift_eval import evaluate_drift
from core_engine.player.sync_buffer import read_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze F0 drift metrics.")
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--processed", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    original, original_rate = read_audio(args.original)
    processed, processed_rate = read_audio(args.processed)
    if original_rate != processed_rate:
        raise ValueError(f"sample rates differ: {original_rate} != {processed_rate}")

    result = evaluate_drift(original, processed, original_rate)
    print(f"status={'passed' if result.passed else 'failed'}")
    print(f"normalized_difference={result.normalized_difference:.6f}")
    print(f"original_voiced_ratio={result.original_voiced_ratio:.3f}")
    print(f"processed_voiced_ratio={result.processed_voiced_ratio:.3f}")
    print(f"median_f0_shift_cents={result.median_f0_shift_cents:.3f}")
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

