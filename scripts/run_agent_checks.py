"""Run the minimum local checks expected by the project harness."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_files() -> list[str]:
    ignored = {
        "__pycache__",
        ".agent",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "源代码",
    }
    files: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in ignored for part in path.parts):
            continue
        files.append(str(path.relative_to(ROOT)))
    return files


def run(command: list[str]) -> int:
    print(f"> {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main() -> int:
    cache_dir = tempfile.mkdtemp(prefix="audio_forge_pycache_")
    checks = [
        [sys.executable, "scripts/validate_architecture.py"],
        [sys.executable, "-X", f"pycache_prefix={cache_dir}", "-m", "py_compile", *python_files()],
    ]

    failures = 0
    for command in checks:
        exit_code = run(command)
        if exit_code != 0:
            failures += 1

    if failures:
        print(f"Agent checks failed: {failures} check(s)")
        return 1

    print("Agent checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
