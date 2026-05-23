"""Inspect optional external audio tools."""

from core_engine.external_tools import detect_audio_tool


def main() -> None:
    for executable in ("ffmpeg", "rubberband"):
        result = detect_audio_tool(executable)
        status = "available" if result.available else "missing"
        print(f"{executable}: {status} path={result.resolved_path}")


if __name__ == "__main__":
    main()
