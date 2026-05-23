"""Frozen-friendly command dispatcher for the Audio Forge MVP."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.cli_harness import (
    analyze_f0_drift,
    export_mix,
    generate_mock_audio,
    import_song,
    inspect_audio_tools,
    render_effect_chain,
    render_tone_deaf_mix,
    run_lyric_ai,
    run_pitch_shift,
)

CommandMain = Callable[[], None]

COMMANDS: dict[str, CommandMain] = {
    "generate-mock": generate_mock_audio.main,
    "import-song": import_song.main,
    "inspect-audio-tools": inspect_audio_tools.main,
    "run-pitch": run_pitch_shift.main,
    "analyze-f0": analyze_f0_drift.main,
    "run-tone-deaf-mix": render_tone_deaf_mix.main,
    "run-effects": render_effect_chain.main,
    "export-mix": export_mix.main,
    "run-lyric": run_lyric_ai.main,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audio Forge MVP command launcher.",
        epilog="Example: audio-forge-cli export-mix --vocal vocal.wav --instrumental inst.wav --output mix.wav",
    )
    parser.add_argument("command", choices=sorted(COMMANDS))
    return parser


def main() -> None:
    parser = build_parser()
    args, remaining = parser.parse_known_args()

    sys.argv = [f"audio-forge-cli {args.command}", *remaining]
    COMMANDS[args.command]()


if __name__ == "__main__":
    main()
