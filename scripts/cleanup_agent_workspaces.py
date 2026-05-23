"""Report stale agent runtime files without deleting them by default."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIRS = (
    ROOT / ".agent" / "traces",
    ROOT / ".agent" / "reports",
    ROOT / ".agent" / "workspaces",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find stale .agent runtime files.")
    parser.add_argument("--older-than-days", type=int, default=7)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cutoff = time.time() - (args.older_than_days * 24 * 60 * 60)
    stale: list[Path] = []

    for directory in RUNTIME_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                stale.append(path)

    if not stale:
        print("No stale agent runtime files found")
        return 0

    print("Stale agent runtime files:")
    for path in stale:
        print(f"- {path.relative_to(ROOT)}")
    print("No files were deleted. Review and remove manually if appropriate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

