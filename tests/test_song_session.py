from pathlib import Path

from core_engine.library.offsets import OffsetStore
from core_engine.library.song_session import load_song_session, select_song_by_name
from core_engine.library.song_scanner import SongAsset


def make_song(tmp_path: Path) -> SongAsset:
    song_dir = tmp_path / "Song A"
    song_dir.mkdir()
    vocal = song_dir / "人声.mp3"
    instrumental = song_dir / "伴奏.mp3"
    lyrics = song_dir / "lyrics.lrc"
    vocal.write_bytes(b"")
    instrumental.write_bytes(b"")
    lyrics.write_text("[00:01.000]A\n[00:02.000]B", encoding="utf-8")
    return SongAsset("Song A", song_dir, vocal, instrumental, lyrics)


def test_load_song_session_reads_lyrics_and_offset(tmp_path: Path):
    asset = make_song(tmp_path)
    offset_store = OffsetStore(tmp_path / "offsets.json")
    offset_store.set("Song A", 500)

    session = load_song_session(asset, offset_store)

    assert session.offset_ms == 500
    assert len(session.lyrics) == 2
    assert session.lyric_sync().state_at(1_600).current_text == "A"


def test_load_song_session_skips_prompt_leakage(tmp_path: Path):
    asset = make_song(tmp_path)
    asset.lyrics_path.write_text(
        "[00:00.000]歌词只输出歌曲中实际唱出的内容。\n[00:01.000]real lyric",
        encoding="utf-8",
    )

    session = load_song_session(asset)

    assert session.lyrics.texts() == ["real lyric"]


def test_select_song_by_name_scans_library(tmp_path: Path):
    make_song(tmp_path)

    session = select_song_by_name(tmp_path, "Song A")

    assert session.asset.name == "Song A"
    assert session.asset.vocal_path.name == "人声.mp3"
