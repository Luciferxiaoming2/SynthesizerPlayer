"""Generate deterministic mock audio for local harness testing."""

import argparse
from pathlib import Path

import numpy as np

from core_engine.player.sync_buffer import write_audio


def sine_wave(frequency: float, sample_rate: int, frames: int, amplitude: float) -> np.ndarray:
    time = np.arange(frames, dtype=np.float32) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * frequency * time)


def build_mock_stems(
    sample_rate: int = 16_000,
    duration_seconds: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    frames = round(sample_rate * duration_seconds)
    vocal = sine_wave(220.0, sample_rate, frames, 0.22)
    vocal += 0.06 * sine_wave(330.0, sample_rate, frames, 1.0)

    instrumental = sine_wave(110.0, sample_rate, frames, 0.18)
    instrumental += 0.08 * sine_wave(440.0, sample_rate, frames, 1.0)

    return vocal[:, np.newaxis].astype(np.float32), instrumental[:, np.newaxis].astype(np.float32)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate mock vocal and instrumental wav files.")
    parser.add_argument("--output-dir", type=Path, default=Path("harness/mock_data"))
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--duration", type=float, default=2.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    vocal, instrumental = build_mock_stems(args.sample_rate, args.duration)
    vocal_path = args.output_dir / "vocal.wav"
    instrumental_path = args.output_dir / "instrumental.wav"
    write_audio(vocal_path, vocal, args.sample_rate)
    write_audio(instrumental_path, instrumental, args.sample_rate)
    print(f"wrote {vocal_path}")
    print(f"wrote {instrumental_path}")


if __name__ == "__main__":
    main()

