"""Persistent lyric offset storage."""

import json
from pathlib import Path


class OffsetStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._offsets: dict[str, int] = {}
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            self._offsets = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._offsets = {}
            return
        self._offsets = {str(key): int(value) for key, value in raw.items()}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._offsets, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, song_name: str) -> int:
        return self._offsets.get(song_name, 0)

    def set(self, song_name: str, offset_ms: int) -> None:
        self._offsets[song_name] = int(offset_ms)
        self.save()

