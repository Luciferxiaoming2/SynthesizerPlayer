"""Load a selected song into UI/harness friendly session metadata."""

from dataclasses import dataclass
from pathlib import Path

from core_engine.library.offsets import OffsetStore
from core_engine.library.song_scanner import SongAsset, scan_song_library
from core_engine.lyrics.parsers import parse_lyrics_by_suffix
from core_engine.lyrics.playback_sync import LyricPlaybackSynchronizer
from core_engine.lyrics.timeline import LyricLine, LyricTimeline
from core_engine.transcription import is_instruction_hallucination


@dataclass(frozen=True)
class SongSession:
    asset: SongAsset
    offset_ms: int
    lyrics: LyricTimeline

    def lyric_sync(self) -> LyricPlaybackSynchronizer:
        return LyricPlaybackSynchronizer(self.lyrics, self.offset_ms)


def load_lyrics_timeline(path: Path | None) -> LyricTimeline:
    if path is None or not path.exists():
        return LyricTimeline([])
    content = path.read_text(encoding="utf-8")
    timeline = parse_lyrics_by_suffix(path.suffix, content)
    return LyricTimeline(
        [
            LyricLine(line.start_ms, line.text, line.end_ms)
            for line in timeline.lines
            if not is_instruction_hallucination(line.text)
        ]
    )


def load_song_session(asset: SongAsset, offset_store: OffsetStore | None = None) -> SongSession:
    offset_ms = offset_store.get(asset.name) if offset_store is not None else 0
    return SongSession(
        asset=asset,
        offset_ms=offset_ms,
        lyrics=load_lyrics_timeline(asset.lyrics_path),
    )


def select_song_by_name(songs_root: Path, song_name: str, offset_store: OffsetStore | None = None) -> SongSession:
    for asset in scan_song_library(songs_root):
        if asset.name == song_name:
            return load_song_session(asset, offset_store)
    raise ValueError(f"song not found: {song_name}")
