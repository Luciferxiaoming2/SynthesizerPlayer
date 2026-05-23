"""Print lyric playback state at a given position."""

import argparse
from pathlib import Path

from core_engine.lyrics.parsers import parse_lyrics_by_suffix
from core_engine.lyrics.playback_sync import LyricPlaybackSynchronizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve current lyric line at playback time.")
    parser.add_argument("--lyrics", required=True, type=Path)
    parser.add_argument("--position-ms", required=True, type=int)
    parser.add_argument("--offset-ms", type=int, default=0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    content = args.lyrics.read_text(encoding="utf-8")
    timeline = parse_lyrics_by_suffix(args.lyrics.suffix, content)
    state = LyricPlaybackSynchronizer(timeline, args.offset_ms).state_at(args.position_ms)
    print(f"position_ms={state.position_ms}")
    print(f"offset_ms={state.offset_ms}")
    print(f"current_index={state.current_index}")
    print(f"current_text={state.current_text}")
    print(f"line_progress={state.line_progress:.3f}")
    print(f"previous_text={state.previous_line.text if state.previous_line else ''}")
    print(f"next_text={state.next_line.text if state.next_line else ''}")


if __name__ == "__main__":
    main()

