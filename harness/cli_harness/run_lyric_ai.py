"""Run the lyric rewrite singing path without the UI."""

import argparse
from pathlib import Path
import shlex

from core_engine.ai_singer import (
    BypassRvcInferencer,
    ExternalDiffSingerClient,
    ExternalRvcInferencer,
    LyricRewriteSingingRequest,
    LyricRewriteSingingWorkflow,
    PreviewSingingClient,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a replacement sung lyric segment.")
    parser.add_argument("--lyric", required=True, help="Replacement lyric text.")
    parser.add_argument("--melody", required=True, type=Path, help="Extracted melody or MIDI path.")
    parser.add_argument("--output", required=True, type=Path, help="Generated vocal path.")
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--backend",
        choices=["preview", "external"],
        default="preview",
        help="preview writes a lightweight placeholder wav; external calls --diff-command.",
    )
    parser.add_argument(
        "--diff-command",
        default=None,
        help=(
            "External command template. Placeholders: {lyric}, {melody}, {output}, "
            "{sample_rate}, {duration}."
        ),
    )
    parser.add_argument("--rvc-model", type=Path, default=None)
    parser.add_argument(
        "--rvc-command",
        default=None,
        help="Optional external RVC command template. Placeholders: {source}, {model}, {output}.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.backend == "external":
        if args.diff_command is None:
            raise SystemExit("--diff-command is required when --backend external")
        singer = ExternalDiffSingerClient(split_command(args.diff_command))
    else:
        singer = PreviewSingingClient()

    voice_converter = None
    if args.rvc_model is not None:
        if args.rvc_command:
            voice_converter = ExternalRvcInferencer(split_command(args.rvc_command))
        else:
            voice_converter = BypassRvcInferencer()

    result = LyricRewriteSingingWorkflow(singer, voice_converter).run(
        LyricRewriteSingingRequest(
            lyric=args.lyric,
            melody_path=args.melody,
            output_path=args.output,
            sample_rate=args.sample_rate,
            duration_seconds=args.duration,
            rvc_model_path=args.rvc_model,
        )
    )
    print(
        f"wrote {result.output_path} "
        f"synthesized={result.synthesized_path} voice_conversion={result.used_voice_conversion}"
    )


def split_command(command: str) -> list[str]:
    return shlex.split(command, posix=False)


if __name__ == "__main__":
    main()
