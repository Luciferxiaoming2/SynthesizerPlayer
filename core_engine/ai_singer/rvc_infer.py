"""RVC-style adapters for singer timbre conversion."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from collections.abc import Sequence


@dataclass(frozen=True)
class VoiceConversionRequest:
    source_vocal_path: Path
    model_path: Path | None
    output_path: Path


class RvcInferencer:
    def convert(self, request: VoiceConversionRequest) -> Path:
        raise NotImplementedError("Wire this adapter to an RVC inference runtime")


class BypassRvcInferencer(RvcInferencer):
    """Copies the synthesized vocal when no local RVC backend is configured."""

    def convert(self, request: VoiceConversionRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        if request.source_vocal_path.resolve() != request.output_path.resolve():
            shutil.copyfile(request.source_vocal_path, request.output_path)
        return request.output_path


class ExternalRvcInferencer(RvcInferencer):
    """Command adapter for external RVC inference runtimes."""

    def __init__(self, command_template: Sequence[str]) -> None:
        if not command_template:
            raise ValueError("command_template must not be empty")
        self._command_template = tuple(command_template)

    def convert(self, request: VoiceConversionRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._render_command(request), check=True)
        if not request.output_path.exists():
            raise FileNotFoundError(f"external RVC did not create {request.output_path}")
        return request.output_path

    def _render_command(self, request: VoiceConversionRequest) -> list[str]:
        values = {
            "source": str(request.source_vocal_path),
            "model": "" if request.model_path is None else str(request.model_path),
            "output": str(request.output_path),
        }
        return [part.format(**values) for part in self._command_template]
