"""Workflow object for replacement-lyric singing experiments."""

from dataclasses import dataclass
from pathlib import Path

from core_engine.ai_singer.diff_singer_api import (
    DiffSingerClient,
    LyricContentEditRequest,
    LyricContentEditor,
    SingingSegmentRequest,
)
from core_engine.ai_singer.rvc_infer import RvcInferencer, VoiceConversionRequest


@dataclass(frozen=True)
class LyricRewriteSingingRequest:
    lyric: str
    melody_path: Path
    output_path: Path
    sample_rate: int = 16_000
    duration_seconds: float = 2.0
    rvc_model_path: Path | None = None
    intermediate_path: Path | None = None
    source_vocal_path: Path | None = None
    start_ms: int = 0
    end_ms: int = 0


@dataclass(frozen=True)
class LyricRewriteSingingResult:
    output_path: Path
    synthesized_path: Path
    converted_path: Path
    used_voice_conversion: bool
    used_content_editor: bool = False


class LyricRewriteSingingWorkflow:
    """Runs singing synthesis and optional timbre conversion behind stable ports."""

    def __init__(
        self,
        singer: DiffSingerClient,
        voice_converter: RvcInferencer | None = None,
        content_editor: LyricContentEditor | None = None,
    ) -> None:
        self._singer = singer
        self._voice_converter = voice_converter
        self._content_editor = content_editor

    def run(self, request: LyricRewriteSingingRequest) -> LyricRewriteSingingResult:
        if self._content_editor is not None:
            if request.source_vocal_path is None:
                raise ValueError("内容编辑后端需要 source_vocal_path")
            edited = self._content_editor.edit(
                LyricContentEditRequest(
                    lyric=request.lyric,
                    source_vocal_path=request.source_vocal_path,
                    melody_path=request.melody_path,
                    output_path=request.output_path,
                    sample_rate=request.sample_rate,
                    duration_seconds=request.duration_seconds,
                    start_ms=request.start_ms,
                    end_ms=request.end_ms,
                )
            )
            return LyricRewriteSingingResult(
                output_path=edited,
                synthesized_path=edited,
                converted_path=edited,
                used_voice_conversion=False,
                used_content_editor=True,
            )

        synthesized_path = request.intermediate_path or request.output_path
        if request.rvc_model_path is not None and synthesized_path == request.output_path:
            synthesized_path = request.output_path.with_name(f"{request.output_path.stem}.synth.wav")

        synthesized = self._singer.synthesize(
            SingingSegmentRequest(
                lyric=request.lyric,
                melody_path=request.melody_path,
                output_path=synthesized_path,
                sample_rate=request.sample_rate,
                duration_seconds=request.duration_seconds,
            )
        )

        if request.rvc_model_path is None or self._voice_converter is None:
            return LyricRewriteSingingResult(
                output_path=synthesized,
                synthesized_path=synthesized,
                converted_path=synthesized,
                used_voice_conversion=False,
                used_content_editor=False,
            )

        converted = self._voice_converter.convert(
            VoiceConversionRequest(
                source_vocal_path=synthesized,
                model_path=request.rvc_model_path,
                output_path=request.output_path,
            )
        )
        return LyricRewriteSingingResult(
            output_path=converted,
            synthesized_path=synthesized,
            converted_path=converted,
            used_voice_conversion=True,
            used_content_editor=False,
        )
