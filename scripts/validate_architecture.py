"""Validate Audio Forge harness and architecture guardrails."""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_CORE_IMPORTS = ("PyQt6", "PySide6", "from ui", "import ui")
FORBIDDEN_EVAL_IMPORTS = ("PyQt6", "PySide6", "from ui", "import ui")
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]{16,}"),
)
SECRET_SCAN_GLOBS = ("*.py", "*.md", "*.toml", "*.yaml", "*.yml")
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
IGNORED_SECRET_PREFIXES = (
    ".agent/traces/",
    ".agent/reports/",
    ".agent/workspaces/",
)
HEAVY_ARTIFACT_GLOBS = (
    "*.wav",
    "*.mp3",
    "*.flac",
    "*.pth",
    "*.pt",
    "*.onnx",
    "*.safetensors",
    "*.vst3",
)


def iter_files(base: Path, pattern: str = "*") -> list[Path]:
    files: list[Path] = []
    for path in base.rglob(pattern):
        if not path.is_file():
            continue
        if any(part in IGNORED_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_forbidden_imports(paths: list[Path], forbidden: tuple[str, ...], label: str) -> list[str]:
    errors: list[str] = []
    for path in paths:
        text = read_text(path)
        for needle in forbidden:
            if needle in text:
                errors.append(f"{label}: {rel(path)} contains forbidden import marker `{needle}`")
    return errors


def check_secret_like_values() -> list[str]:
    errors: list[str] = []
    candidates: list[Path] = []
    for glob in SECRET_SCAN_GLOBS:
        candidates.extend(iter_files(ROOT, glob))

    for path in sorted(set(candidates)):
        relative = rel(path)
        if any(relative.startswith(prefix) for prefix in IGNORED_SECRET_PREFIXES):
            continue
        if relative == ".env.example":
            continue
        text = read_text(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"security: {relative} contains a secret-like value")
                break
    return errors


def check_heavy_artifacts() -> list[str]:
    warnings: list[str] = []
    for path in iter_files(ROOT):
        relative = rel(path)
        if relative.startswith(
            ("plugins/models/", "plugins/vst3/", "harness/mock_data/", "源代码/")
        ):
            continue
        if any(fnmatch.fnmatch(path.name, glob) for glob in HEAVY_ARTIFACT_GLOBS):
            warnings.append(f"artifact: {relative} looks like a heavy runtime artifact")
    return warnings


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(
        check_forbidden_imports(
            iter_files(ROOT / "core_engine", "*.py"),
            FORBIDDEN_CORE_IMPORTS,
            "architecture",
        )
    )
    errors.extend(
        check_forbidden_imports(
            iter_files(ROOT / "harness" / "eval_harness", "*.py"),
            FORBIDDEN_EVAL_IMPORTS,
            "architecture",
        )
    )
    errors.extend(check_secret_like_values())
    warnings.extend(check_heavy_artifacts())

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"Architecture validation failed: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"Architecture validation passed: 0 error(s), {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
