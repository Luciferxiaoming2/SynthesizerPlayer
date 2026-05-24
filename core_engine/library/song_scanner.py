"""Scan local song folders for vocal, instrumental, and lyric assets."""

from dataclasses import dataclass
import json
from pathlib import Path

VOCAL_MARKERS = ("vocal", "vocals", "voice", "人声", "干声")
INSTRUMENTAL_MARKERS = ("instrumental", "accompaniment", "伴奏", "inst")
LYRIC_SUFFIXES = (".lrc", ".srt")
AUDIO_SUFFIXES = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac")


@dataclass(frozen=True)
class SongAsset:
    name: str
    root: Path
    vocal_path: Path
    instrumental_path: Path
    lyrics_path: Path | None = None
    source_path: Path | None = None

    @property
    def is_imported_project(self) -> bool:
        return self.source_path is None


def find_matching_file(folder: Path, markers: tuple[str, ...]) -> Path | None:
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        lowered = path.name.lower()
        if any(marker.lower() in lowered for marker in markers):
            return path
    return None


def find_lyrics_file(folder: Path) -> Path | None:
    for suffix in LYRIC_SUFFIXES:
        candidates = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == suffix)
        if candidates:
            return candidates[0]
    return None


def scan_song_library(root: Path) -> list[SongAsset]:
    if not root.exists():
        return []

    songs: list[SongAsset] = []
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        if path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        songs.append(
            SongAsset(
                name=path.stem,
                root=root,
                vocal_path=path,
                instrumental_path=path,
                lyrics_path=find_sidecar_lyrics(path),
                source_path=path,
            )
        )

    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_paths = project_manifest_audio_paths(folder)
        vocal = manifest_paths[0] or find_matching_file(folder, VOCAL_MARKERS)
        instrumental = manifest_paths[1] or find_matching_file(folder, INSTRUMENTAL_MARKERS)
        if vocal is None or instrumental is None:
            continue
        vocal = active_vocal_path(folder) or vocal

        songs.append(
            SongAsset(
                name=folder.name,
                root=folder,
                vocal_path=vocal,
                instrumental_path=instrumental,
                lyrics_path=find_lyrics_file(folder),
            )
        )
    return songs


def project_manifest_audio_paths(project_dir: Path) -> tuple[Path | None, Path | None]:
    manifest_path = project_dir / "project.json"
    if not manifest_path.exists():
        return None, None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    return (
        resolve_project_file(project_dir, manifest.get("vocal_path")),
        resolve_project_file(project_dir, manifest.get("instrumental_path")),
    )


def active_vocal_path(project_dir: Path) -> Path | None:
    manifest_path = project_dir / "project.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = manifest.get("active_vocal_path")
    if not value:
        return None
    return resolve_project_file(project_dir, value)


def resolve_project_file(project_dir: Path, value) -> Path | None:
    if not value:
        return None
    candidate = Path(str(value))
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def find_sidecar_lyrics(audio_path: Path) -> Path | None:
    for suffix in LYRIC_SUFFIXES:
        candidate = audio_path.with_suffix(suffix)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None
