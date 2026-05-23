from pathlib import Path

from core_engine.library.offsets import OffsetStore
from core_engine.library.song_scanner import scan_song_library


def test_scan_song_library_finds_dual_track_folder(tmp_path: Path):
    song_dir = tmp_path / "Song A"
    song_dir.mkdir()
    (song_dir / "人声.mp3").write_bytes(b"")
    (song_dir / "伴奏.mp3").write_bytes(b"")
    (song_dir / "lyrics.lrc").write_text("[00:00.00]hi", encoding="utf-8")

    songs = scan_song_library(tmp_path)

    assert len(songs) == 1
    assert songs[0].name == "Song A"
    assert songs[0].lyrics_path == song_dir / "lyrics.lrc"


def test_offset_store_round_trips_values(tmp_path: Path):
    store_path = tmp_path / "offsets.json"
    store = OffsetStore(store_path)

    store.set("Song A", 2239)
    loaded = OffsetStore(store_path)

    assert loaded.get("Song A") == 2239
    assert loaded.get("missing") == 0

