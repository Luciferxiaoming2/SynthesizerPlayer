"""Evaluate whether F0 drift resembles human pitch instability."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

from core_engine.dsp.tone_deaf import ToneDeafConfig, estimate_f0_track, render_tone_deaf_vocal
from core_engine.player.sync_buffer import read_audio


@dataclass(frozen=True)
class DriftResult:
    normalized_difference: float
    original_voiced_ratio: float
    processed_voiced_ratio: float
    median_f0_shift_cents: float
    passed: bool


def normalized_difference(original: np.ndarray, processed: np.ndarray) -> float:
    frame_count = min(original.shape[0], processed.shape[0])
    if frame_count == 0:
        raise ValueError("audio buffers must not be empty")
    original = np.asarray(original[:frame_count], dtype=np.float32)
    processed = np.asarray(processed[:frame_count], dtype=np.float32)
    denominator = float(np.sqrt(np.mean(np.square(original)))) + 1e-9
    return float(np.sqrt(np.mean(np.square(processed - original))) / denominator)


def evaluate_drift(
    original: np.ndarray,
    processed: np.ndarray,
    sample_rate: int,
    min_difference: float = 0.005,
    max_difference: float = 1.500,
) -> DriftResult:
    difference = normalized_difference(original, processed)
    config = ToneDeafConfig(drift_ratio=0.4)
    original_f0 = estimate_f0_track(original, sample_rate, config)
    processed_f0 = estimate_f0_track(processed, sample_rate, config)
    original_voiced = original_f0.frequencies_hz > 0.0
    processed_voiced = processed_f0.frequencies_hz > 0.0
    shared = original_voiced & processed_voiced
    median_shift = 0.0
    if np.any(shared):
        ratios = processed_f0.frequencies_hz[shared] / original_f0.frequencies_hz[shared]
        median_shift = float(np.median(1200.0 * np.log2(np.maximum(ratios, 1e-9))))

    return DriftResult(
        normalized_difference=difference,
        original_voiced_ratio=float(np.mean(original_voiced)) if original_voiced.size else 0.0,
        processed_voiced_ratio=float(np.mean(processed_voiced)) if processed_voiced.size else 0.0,
        median_f0_shift_cents=median_shift,
        passed=(
            min_difference <= difference <= max_difference
            and abs(median_shift) < 250.0
            and np.any(shared)
        ),
    )


def synthetic_vocal(sample_rate: int = 16_000, duration_seconds: float = 1.0) -> np.ndarray:
    frames = round(sample_rate * duration_seconds)
    time = np.arange(frames, dtype=np.float32) / sample_rate
    signal = 0.2 * np.sin(2.0 * np.pi * 220.0 * time)
    return signal[:, np.newaxis].astype(np.float32)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate tone-deaf drift amount.")
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--min-difference", type=float, default=0.005)
    parser.add_argument("--max-difference", type=float, default=1.500)
    return parser


def run_smoke_test() -> DriftResult:
    sample_rate = 16_000
    original = synthetic_vocal(sample_rate)
    processed = render_tone_deaf_vocal(
        original,
        sample_rate,
        ToneDeafConfig(drift_ratio=0.4, random_seed=11),
    )
    return evaluate_drift(original, processed, sample_rate)


def main() -> None:
    if len(sys.argv) == 1:
        result = run_smoke_test()
        print(
            "smoke: "
            f"normalized_difference={result.normalized_difference:.6f} "
            f"original_voiced_ratio={result.original_voiced_ratio:.3f} "
            f"processed_voiced_ratio={result.processed_voiced_ratio:.3f} "
            f"median_f0_shift_cents={result.median_f0_shift_cents:.3f} "
            f"status={'passed' if result.passed else 'failed'}"
        )
        if not result.passed:
            raise SystemExit(1)
        return

    args = build_parser().parse_args()
    original, original_rate = read_audio(args.original)
    processed, processed_rate = read_audio(args.processed)
    if original_rate != processed_rate:
        raise ValueError(f"sample rates differ: {original_rate} != {processed_rate}")

    result = evaluate_drift(
        original,
        processed,
        original_rate,
        min_difference=args.min_difference,
        max_difference=args.max_difference,
    )
    print(
        f"{'passed' if result.passed else 'failed'}: "
        f"normalized_difference={result.normalized_difference:.6f} "
        f"original_voiced_ratio={result.original_voiced_ratio:.3f} "
        f"processed_voiced_ratio={result.processed_voiced_ratio:.3f} "
        f"median_f0_shift_cents={result.median_f0_shift_cents:.3f}"
    )
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
