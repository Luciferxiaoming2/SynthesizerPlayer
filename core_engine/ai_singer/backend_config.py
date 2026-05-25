"""Runtime configuration for lyric rewrite singing backends."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path

from core_engine.ai_singer.diff_singer_api import (
    DiffSingerClient,
    ExternalDiffSingerClient,
    ExternalLyricContentEditor,
    LocalSpeechSingingClient,
    LyricContentEditor,
    PreviewSingingClient,
)
from core_engine.ai_singer.rvc_infer import BypassRvcInferencer, ExternalRvcInferencer, RvcInferencer


@dataclass(frozen=True)
class LyricRewriteBackendConfig:
    backend: str = "preview"
    diff_command: tuple[str, ...] = ()
    edit_command: tuple[str, ...] = ()
    rvc_model_path: Path | None = None
    rvc_command: tuple[str, ...] = ()
    ace_model_path: Path | None = None
    config_path: Path | None = None

    @property
    def label(self) -> str:
        if self.backend == "local_tts":
            return "本机轻量改词唱"
        if self.backend == "ace_step":
            return "ACE-Step v1.5 歌词编辑"
        if self.backend == "content_edit":
            return "Vevo/内容编辑后端"
        if self.backend == "external_svs":
            return "外部唱声合成 + 音色转换"
        return "内置安全预览"

    @property
    def uses_content_editor(self) -> bool:
        return self.backend in {"content_edit", "ace_step"} and bool(self.edit_command)

    @property
    def can_replace_audio(self) -> bool:
        if self.backend == "local_tts":
            return True
        if self.backend == "preview":
            return False
        if self.backend == "ace_step":
            return bool(self.edit_command) and self.ace_model_path is not None
        if self.backend == "content_edit":
            return bool(self.edit_command)
        return True

    @property
    def readiness_label(self) -> str:
        if self.backend == "ace_step":
            if self.ace_model_path is None:
                return "ACE-Step 模型未放置"
            if not self.edit_command:
                return "ACE-Step 模型已放置，运行环境未安装，当前只改歌词文本"
            return "ACE-Step 模型与运行环境已就绪"
        if self.backend == "preview":
            return "未接入真实AI改唱模型，当前只改歌词文本"
        if self.backend == "local_tts":
            return "使用本机语音合成生成新词试听，不需要显卡；自然度低于云端/大模型"
        return "真实改唱后端已配置"

    def build_singer(self) -> DiffSingerClient:
        if self.backend == "local_tts":
            return LocalSpeechSingingClient(fallback=PreviewSingingClient())
        if self.backend == "external_svs":
            if not self.diff_command:
                raise ValueError("外部唱声合成后端缺少 diff_command")
            return ExternalDiffSingerClient(self.diff_command)
        return PreviewSingingClient()

    def build_content_editor(self) -> LyricContentEditor | None:
        if not self.uses_content_editor:
            return None
        extra_values = {}
        if self.ace_model_path is not None:
            extra_values["model_dir"] = str(self.ace_model_path)
        return ExternalLyricContentEditor(self.edit_command, extra_values=extra_values)

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
    ace_model_path = find_ace_step_model_path(root)
    if ace_model_path is not None:
        edit_command = tuple(default_ace_step_command(root, ace_model_path))
        if not edit_command:
            return LyricRewriteBackendConfig(backend="local_tts")
        return LyricRewriteBackendConfig(
            backend="ace_step",
            ace_model_path=ace_model_path,
            edit_command=edit_command,
        )
    return LyricRewriteBackendConfig(backend="local_tts")


def lyric_rewrite_config_candidates(root: Path) -> list[Path]:
    return [
        root / "ai_singer_backend.json",
        root / "plugins" / "config" / "ai_singer_backend.json",
    ]


def parse_lyric_rewrite_backend_config(path: Path) -> LyricRewriteBackendConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    backend = normalize_backend_name(str(data.get("backend", "preview")).strip().lower())
    if backend not in {"preview", "local_tts", "external_svs", "content_edit", "ace_step"}:
        raise ValueError(f"不支持的改词唱后端：{backend}")

    diff_command = parse_command_list(data.get("diff_command", []), "diff_command")
    edit_command = parse_command_list(
        data.get("edit_command", data.get("content_edit_command", [])),
        "edit_command",
    )
    rvc_command = parse_command_list(data.get("rvc_command", []), "rvc_command")
    rvc_model = data.get("rvc_model_path")
    rvc_model_path = resolve_optional_path(path.parent, rvc_model)
    ace_model_path = resolve_optional_path(path.parent, data.get("ace_model_path"))

    if backend == "external_svs" and not diff_command:
        raise ValueError("外部唱声合成后端必须配置 diff_command")
    if backend == "content_edit" and not edit_command:
        raise ValueError("Vevo/内容编辑后端必须配置 edit_command")
    if backend == "ace_step":
        if ace_model_path is None:
            ace_model_path = find_ace_step_model_path(path.parent)
        if ace_model_path is not None and not edit_command:
            edit_command = default_ace_step_command(path.parent, ace_model_path)

    return LyricRewriteBackendConfig(
        backend=backend,
        diff_command=tuple(diff_command),
        edit_command=tuple(edit_command),
        rvc_model_path=rvc_model_path,
        rvc_command=tuple(rvc_command),
        ace_model_path=ace_model_path,
        config_path=path,
    )


def normalize_backend_name(backend: str) -> str:
    aliases = {
        "preview": "preview",
        "local": "local_tts",
        "local_tts": "local_tts",
        "local_speech": "local_tts",
        "sapi": "local_tts",
        "external": "external_svs",
        "external_svs": "external_svs",
        "svs": "external_svs",
        "diffsinger": "external_svs",
        "content_edit": "content_edit",
        "external_content_editor": "content_edit",
        "vevo": "content_edit",
        "vevo1.5": "content_edit",
        "vevo15": "content_edit",
        "ace": "ace_step",
        "ace-step": "ace_step",
        "ace_step": "ace_step",
        "acestep": "ace_step",
        "acestep-v15": "ace_step",
    }
    return aliases.get(backend, backend)


def parse_command_list(value, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
        raise ValueError(f"{field_name} 必须是字符串数组")
    return [part for part in value if part]


def resolve_optional_path(base_dir: Path, value) -> Path | None:
    if not value:
        return None
    return resolve_config_path(base_dir, Path(str(value)))


def resolve_config_path(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def find_ace_step_model_path(root: Path) -> Path | None:
    candidates = [
        root / "plugins" / "models" / "ace-step" / "acestep-v15-sft",
        root / "_internal" / "plugins" / "models" / "ace-step" / "acestep-v15-sft",
        root / "ace-step" / "acestep-v15-sft",
    ]
    if len(root.parents) >= 2:
        candidates.append(root.parents[1] / "plugins" / "models" / "ace-step" / "acestep-v15-sft")
    for candidate in candidates:
        if is_ace_step_model_dir(candidate):
            return candidate
    return None


def is_ace_step_model_dir(path: Path) -> bool:
    return (
        path.exists()
        and (path / "model.safetensors").exists()
        and (path / "config.json").exists()
        and (path / "configuration_acestep_v15.py").exists()
        and (path / "modeling_acestep_v15_base.py").exists()
        and (path / "silence_latent.pt").exists()
    )


def default_ace_step_command(root: Path, model_path: Path) -> list[str]:
    if importlib.util.find_spec("acestep") is None or importlib.util.find_spec("diffusers") is None:
        return []
    runner = root / "scripts" / "ai_singer" / "run_ace_step_edit.py"
    if not runner.exists():
        return []
    return [
        "python",
        str(runner),
        "--model-dir",
        str(model_path),
        "--source",
        "{source}",
        "--lyric",
        "{lyric}",
        "--output",
        "{output}",
        "--start-ms",
        "{start_ms}",
        "--end-ms",
        "{end_ms}",
    ]
