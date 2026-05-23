"""Scan a song folder using the project song-library model."""

import argparse
from pathlib import Path

from core_engine.library.song_scanner import scan_song_library


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan local dual-track song folders.")
    parser.add_argument("--songs-dir", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    songs = scan_song_library(args.songs_dir)
    for song in songs:
        print(f"{song.name}")
        print(f"  vocal: {song.vocal_path}")
        print(f"  instrumental: {song.instrumental_path}")
        print(f"  lyrics: {song.lyrics_path or '-'}")
    print(f"found {len(songs)} song(s)")


if __name__ == "__main__":
    main()

