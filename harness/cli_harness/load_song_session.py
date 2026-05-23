"""Load a song session and print UI-ready metadata."""

import argparse
from pathlib import Path

from core_engine.library.offsets import OffsetStore
from core_engine.library.song_session import select_song_by_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load a song session from a scanned library.")
    parser.add_argument("--songs-dir", required=True, type=Path)
    parser.add_argument("--song", required=True)
    parser.add_argument("--offset-file", type=Path, default=None)
    parser.add_argument("--position-ms", type=int, default=0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    offset_store = OffsetStore(args.offset_file) if args.offset_file else None
    session = select_song_by_name(args.songs_dir, args.song, offset_store)
    lyric_state = session.lyric_sync().state_at(args.position_ms)
    print(f"name={session.asset.name}")
    print(f"vocal={session.asset.vocal_path}")
    print(f"instrumental={session.asset.instrumental_path}")
    print(f"lyrics={session.asset.lyrics_path or ''}")
    print(f"offset_ms={session.offset_ms}")
    print(f"lyric_count={len(session.lyrics)}")
    print(f"current_lyric_index={lyric_state.current_index}")
    print(f"current_lyric_text={lyric_state.current_text}")


if __name__ == "__main__":
    main()

