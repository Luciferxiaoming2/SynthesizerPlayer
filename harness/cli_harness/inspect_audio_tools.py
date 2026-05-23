"""Inspect optional external audio tools."""

from pathlib import Path

from core_engine.external_tools import detect_audio_tool, project_audio_tool_dirs


def main() -> None:
    search_dirs = project_audio_tool_dirs(Path.cwd())
    for executable in ("ffmpeg", "rubberband"):
        result = detect_audio_tool(executable, search_dirs=search_dirs)
        status = "available" if result.available else "missing"
        print(f"{executable}: {status} source={result.source} path={result.resolved_path}")


if __name__ == "__main__":
    main()
