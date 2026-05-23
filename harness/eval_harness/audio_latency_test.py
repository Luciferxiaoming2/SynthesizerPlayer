"""Evaluate vocal/instrumental alignment latency."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

from core_engine.player.sync_buffer import read_audio


@dataclass(frozen=True)
class LatencyResult:
    latency_samples: int
    latency_seconds: float
    score: float
    passed: bool


def mono(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        return array
    if array.ndim == 2:
        return np.mean(array, axis=1, dtype=np.float32)
    raise ValueError("audio must be 1D or 2D")


def normalized_correlation(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    a_centered = a - float(np.mean(a))
    b_centered = b - float(np.mean(b))
    denominator = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a_centered, b_centered) / denominator)


def estimate_latency_samples(
    reference: np.ndarray,
    candidate: np.ndarray,
    max_lag_samples: int,
) -> tuple[int, float]:
    """Estimate candidate delay relative to reference.

    A positive result means ``candidate`` is delayed by that many samples.
    """

    if max_lag_samples < 0:
        raise ValueError("max_lag_samples must be non-negative")

    reference_mono = mono(reference)
    candidate_mono = mono(candidate)
    frame_count = min(reference_mono.size, candidate_mono.size)
    if frame_count == 0:
        raise ValueError("audio buffers must not be empty")

    reference_mono = reference_mono[:frame_count]
    candidate_mono = candidate_mono[:frame_count]
    max_lag_samples = min(max_lag_samples, frame_count - 1)

    best_lag = 0
    best_score = -1.0
    for lag in range(-max_lag_samples, max_lag_samples + 1):
        if lag >= 0:
            ref_window = reference_mono[: frame_count - lag]
            cand_window = candidate_mono[lag:frame_count]
        else:
            ref_window = reference_mono[-lag:frame_count]
            cand_window = candidate_mono[: frame_count + lag]

        score = normalized_correlation(ref_window, cand_window)
        if score > best_score:
            best_score = score
            best_lag = lag

    return best_lag, best_score


def evaluate_latency(
    reference: np.ndarray,
    candidate: np.ndarray,
    sample_rate: int,
    max_lag_ms: float = 100.0,
    tolerance_ms: float = 5.0,
) -> LatencyResult:
    max_lag_samples = round(sample_rate * max_lag_ms / 1000.0)
    tolerance_samples = round(sample_rate * tolerance_ms / 1000.0)
    latency_samples, score = estimate_latency_samples(reference, candidate, max_lag_samples)
    return LatencyResult(
        latency_samples=latency_samples,
        latency_seconds=latency_samples / sample_rate,
        score=score,
        passed=abs(latency_samples) <= tolerance_samples,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Estimate latency between two audio files.")
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--max-lag-ms", type=float, default=100.0)
    parser.add_argument("--tolerance-ms", type=float, default=5.0)
    return parser


def run_smoke_test() -> LatencyResult:
    reference = np.zeros(2_000, dtype=np.float32)
    candidate = np.zeros(2_000, dtype=np.float32)
    reference[400:460] = 1.0
    candidate[403:463] = 1.0
    return evaluate_latency(reference, candidate, sample_rate=1_000, tolerance_ms=5.0)


def main() -> None:
    if len(sys.argv) == 1:
        result = run_smoke_test()
        print(
            "smoke: "
            f"latency={result.latency_seconds * 1000.0:.3f}ms "
            f"samples={result.latency_samples} score={result.score:.4f}"
        )
        return

    args = build_parser().parse_args()
    reference, reference_rate = read_audio(args.reference)
    candidate, candidate_rate = read_audio(args.candidate)
    if reference_rate != candidate_rate:
        raise ValueError(f"sample rates differ: {reference_rate} != {candidate_rate}")

    result = evaluate_latency(
        reference=reference,
        candidate=candidate,
        sample_rate=reference_rate,
        max_lag_ms=args.max_lag_ms,
        tolerance_ms=args.tolerance_ms,
    )
    latency_ms = result.latency_seconds * 1000.0
    status = "passed" if result.passed else "failed"
    print(
        f"{status}: latency={latency_ms:.3f}ms "
        f"samples={result.latency_samples} score={result.score:.4f}"
    )
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
