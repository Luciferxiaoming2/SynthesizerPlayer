"""Create a reusable project from one complete song file."""

from dataclasses import dataclass
from pathlib import Path
import json
import shutil

from core_engine.external_tools import FfmpegAudioStandardizer
from core_engine.library.song_scanner import SongAsset
from core_engine.player.stem_separator import PreviewStemSeparator, StemPair, StemSeparator
from core_engine.transcription import LyricsTranscriber, LyricsTranscriptionRequest

LYRIC_SUFFIXES = (".lrc", ".srt")


@dataclass(frozen=True)
class SongImportConfig:
    source_path: Path
    projects_root: Path
    separator: StemSeparator | None = None
    lyrics_transcriber: LyricsTranscriber | None = None
    audio_standardizer: FfmpegAudioStandardizer | None = None
    copy_source: bool = True


@dataclass(frozen=True)
class ImportedSongProject:
    name: str
    project_dir: Path
    source_path: Path
    stems: StemPair
    lyrics_path: Path | None
    asset: SongAsset


def import_single_song(config: SongImportConfig) -> ImportedSongProject:
    source_path = config.source_path
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"source song not found: {source_path}")

    project_dir = unique_project_dir(config.projects_root, source_path.stem)
    stems_dir = project_dir / "stems"
    project_dir.mkdir(parents=True, exist_ok=True)

    project_source = project_dir / f"original{source_path.suffix.lower()}"
    if config.copy_source:
        # 导入工程默认保留一份原曲副本，后续重跑分离或重新生成歌词时不用依赖外部路径。
        shutil.copyfile(source_path, project_source)
    else:
        project_source = source_path

    if config.audio_standardizer is not None:
        # ffmpeg 只作为可选外部工具：负责格式标准化，不把旧项目二进制搬进仓库。
        standardized_source = project_dir / "original_standard.wav"
        project_source = config.audio_standardizer.standardize(project_source, standardized_source)

    # 分离器是可插拔端口：MVP 可用 preview，真实交付时切换到 Demucs/Spleeter/UVR5。
    separator = config.separator or PreviewStemSeparator()
    stems = separator.separate(project_source, stems_dir)
    lyrics_path = copy_matching_lyrics(source_path, project_dir)
    if lyrics_path is None and config.lyrics_transcriber is not None:
        # 没有现成 LRC/SRT 时，交给可插拔 ASR 后端生成初始歌词时间轴。
        lyrics_path = config.lyrics_transcriber.transcribe(
            LyricsTranscriptionRequest(
                audio_path=project_source,
                output_path=project_dir / "lyrics.lrc",
            )
        )
    asset = SongAsset(
        name=project_dir.name,
        root=project_dir,
        vocal_path=stems.vocal_path,
        instrumental_path=stems.instrumental_path,
        lyrics_path=lyrics_path,
    )
    write_manifest(project_dir, source_path, project_source, stems, lyrics_path)
    return ImportedSongProject(
        name=project_dir.name,
        project_dir=project_dir,
        source_path=project_source,
        stems=stems,
        lyrics_path=lyrics_path,
        asset=asset,
    )


def unique_project_dir(projects_root: Path, raw_name: str) -> Path:
    projects_root.mkdir(parents=True, exist_ok=True)
    base = sanitize_project_name(raw_name)
    candidate = projects_root / base
    index = 2
    while candidate.exists():
        candidate = projects_root / f"{base}_{index}"
        index += 1
    return candidate


def sanitize_project_name(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return sanitized.strip("_") or "song"


def copy_matching_lyrics(source_path: Path, project_dir: Path) -> Path | None:
    for suffix in LYRIC_SUFFIXES:
        candidate = source_path.with_suffix(suffix)
        if candidate.exists() and candidate.is_file():
            target = project_dir / f"lyrics{suffix}"
            shutil.copyfile(candidate, target)
            return target
    return None


def write_manifest(
    project_dir: Path,
    original_source: Path,
    project_source: Path,
    stems: StemPair,
    lyrics_path: Path | None,
) -> None:
    manifest = {
        "original_source": str(original_source),
        "project_source": str(project_source),
        "vocal_path": str(stems.vocal_path),
        "instrumental_path": str(stems.instrumental_path),
        "lyrics_path": None if lyrics_path is None else str(lyrics_path),
    }
    (project_dir / "project.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
