"""Runtime configuration for lyric rewrite singing backends."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from core_engine.ai_singer.diff_singer_api import (
    DiffSingerClient,
    ExternalDiffSingerClient,
    PreviewSingingClient,
)
from core_engine.ai_singer.rvc_infer import BypassRvcInferencer, ExternalRvcInferencer, RvcInferencer


@dataclass(frozen=True)
class LyricRewriteBackendConfig:
    backend: str = "preview"
    diff_command: tuple[str, ...] = ()
    rvc_model_path: Path | None = None
    rvc_command: tuple[str, ...] = ()
    config_path: Path | None = None

    @property
    def label(self) -> str:
        if self.backend == "external":
            return "外部真实模型"
        return "内置实验预览"

    def build_singer(self) -> DiffSingerClient:
        if self.backend == "external":
            if not self.diff_command:
                raise ValueError("外部改词唱后端缺少 diff_command")
            return ExternalDiffSingerClient(self.diff_command)
        return PreviewSingingClient()

    def build_voice_converter(self) -> RvcInferencer | None:
        if self.rvc_model_path is None:
            return None
        if self.rvc_command:
            return ExternalRvcInferencer(self.rvc_command)
        return BypassRvcInferencer()


def load_lyric_rewrite_backend_config(root: Path) -> LyricRewriteBackendConfig:
    for path in lyric_rewrite_config_candidates(root):
        if path.exists():
            return parse_lyric_rewrite_backend_config(path)
    return LyricRewriteBackendConfig()


def lyric_rewrite_config_candidates(root: Path) -> list[Path]:
    return [
        root / "ai_singer_backend.json",
        root / "plugins" / "config" / "ai_singer_backend.json",
    ]


def parse_lyric_rewrite_backend_config(path: Path) -> LyricRewriteBackendConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    backend = str(data.get("backend", "preview")).strip().lower()
    if backend not in {"preview", "external"}:
        raise ValueError(f"不支持的改词唱后端：{backend}")

    diff_command = parse_command_list(data.get("diff_command", ()), "diff_command")
    rvc_command = parse_command_list(data.get("rvc_command", ()), "rvc_command")
    rvc_model = data.get("rvc_model_path")
    rvc_model_path = None
    if rvc_model:
        rvc_model_path = resolve_config_path(path.parent, Path(str(rvc_model)))

    if backend == "external" and not diff_command:
        raise ValueError("外部改词唱后端必须配置 diff_command")

    return LyricRewriteBackendConfig(
        backend=backend,
        diff_command=tuple(diff_command),
        rvc_model_path=rvc_model_path,
        rvc_command=tuple(rvc_command),
        config_path=path,
    )


def parse_command_list(value, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
        raise ValueError(f"{field_name} 必须是字符串数组")
    return [part for part in value if part]


def resolve_config_path(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
