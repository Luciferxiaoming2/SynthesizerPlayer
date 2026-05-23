"""Import a complete song into an Audio Forge project directory."""

import argparse
import shlex
from pathlib import Path

from core_engine.external_tools import FfmpegAudioStandardizer, FfmpegConfig
from core_engine.importer import SongImportConfig, import_single_song
from core_engine.player.stem_separator import (
    DemucsSeparatorConfig,
    DemucsStemSeparator,
    ExternalCommandStemSeparator,
    PreviewStemSeparator,
)
from core_engine.transcription import (
    ExternalCommandLyricsTranscriber,
    FasterWhisperConfig,
    FasterWhisperLyricsTranscriber,
    PreviewLyricsTranscriber,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import one complete song and create stems.")
    parser.add_argument("--input", required=True, type=Path, help="Complete source song file.")
    parser.add_argument("--projects-root", type=Path, default=Path("projects"))
    parser.add_argument(
        "--backend",
        choices=["preview", "demucs", "external"],
        default="preview",
        help="preview is lightweight; demucs calls python -m demucs; external calls --separator-command.",
    )
    parser.add_argument("--demucs-python", default="python", help="Python executable used for -m demucs.")
    parser.add_argument("--demucs-model", default="htdemucs")
    parser.add_argument("--demucs-device", default="cpu", help="Use cpu by default for Intel laptops.")
    parser.add_argument(
        "--separator-command",
        default=None,
        help=(
            "External separator command template. Placeholders: "
            "{source}, {output_dir}, {vocal}, {instrumental}."
        ),
    )
    parser.add_argument(
        "--lyrics-backend",
        choices=["none", "preview", "faster-whisper", "external"],
        default="preview",
        help="Generate placeholder lyrics by default when no LRC/SRT is found.",
    )
    parser.add_argument("--whisper-model", default="base")
    parser.add_argument("--whisper-device", default="cpu")
    parser.add_argument("--whisper-compute-type", default="int8")
    parser.add_argument("--whisper-language", default=None)
    parser.add_argument(
        "--lyrics-command",
        default=None,
        help="External ASR command template. Placeholders: {audio}, {output}, {output_dir}.",
    )
    parser.add_argument("--no-copy-source", action="store_true")
    parser.add_argument(
        "--standardize-audio",
        action="store_true",
        help="Use external ffmpeg to convert imported audio to internal wav before separation.",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path or command name.")
    parser.add_argument("--standard-sample-rate", type=int, default=44_100)
    parser.add_argument("--standard-channels", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.backend == "demucs":
        separator = DemucsStemSeparator(
            DemucsSeparatorConfig(
                executable=args.demucs_python,
                model_name=args.demucs_model,
                device=args.demucs_device,
            )
        )
    elif args.backend == "external":
        if not args.separator_command:
            raise SystemExit("--separator-command is required when --backend external")
        separator = ExternalCommandStemSeparator(shlex.split(args.separator_command, posix=False))
    else:
        separator = PreviewStemSeparator()

    if args.lyrics_backend == "faster-whisper":
        lyrics_transcriber = FasterWhisperLyricsTranscriber(
            FasterWhisperConfig(
                model_size=args.whisper_model,
                device=args.whisper_device,
                compute_type=args.whisper_compute_type,
                language=args.whisper_language,
            )
        )
    elif args.lyrics_backend == "external":
        if not args.lyrics_command:
            raise SystemExit("--lyrics-command is required when --lyrics-backend external")
        lyrics_transcriber = ExternalCommandLyricsTranscriber(
            shlex.split(args.lyrics_command, posix=False)
        )
    elif args.lyrics_backend == "preview":
        lyrics_transcriber = PreviewLyricsTranscriber()
    else:
        lyrics_transcriber = None

    audio_standardizer = None
    if args.standardize_audio:
        audio_standardizer = FfmpegAudioStandardizer(
            FfmpegConfig(
                executable=args.ffmpeg,
                sample_rate=args.standard_sample_rate,
                channels=args.standard_channels,
            )
        )

    project = import_single_song(
        SongImportConfig(
            source_path=args.input,
            projects_root=args.projects_root,
            separator=separator,
            lyrics_transcriber=lyrics_transcriber,
            audio_standardizer=audio_standardizer,
            copy_source=not args.no_copy_source,
        )
    )
    print(f"project={project.project_dir}")
    print(f"source={project.source_path}")
    print(f"vocal={project.stems.vocal_path}")
    print(f"instrumental={project.stems.instrumental_path}")
    print(f"lyrics={project.lyrics_path}")


if __name__ == "__main__":
    main()
