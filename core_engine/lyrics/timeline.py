"""Timed lyric data structures."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LyricLine:
    start_ms: int
    text: str
    end_ms: int | None = None

    def shifted(self, offset_ms: int) -> "LyricLine":
        end_ms = None if self.end_ms is None else self.end_ms + offset_ms
        return LyricLine(start_ms=self.start_ms + offset_ms, end_ms=end_ms, text=self.text)


class LyricTimeline:
    """A sorted collection of timed lyric lines."""

    def __init__(self, lines: list[LyricLine]) -> None:
        self._lines = sorted(lines, key=lambda line: line.start_ms)

    @property
    def lines(self) -> list[LyricLine]:
        return list(self._lines)

    def texts(self) -> list[str]:
        return [line.text for line in self._lines]

    def line_at(self, position_ms: int, offset_ms: int = 0) -> int | None:
        adjusted = position_ms - offset_ms
        current: int | None = None
        for index, line in enumerate(self._lines):
            if adjusted < line.start_ms:
                break
            if line.end_ms is None or adjusted < line.end_ms:
                current = index
            else:
                current = index
        return current

    def line_progress(self, index: int, position_ms: int, offset_ms: int = 0) -> float:
        if index < 0 or index >= len(self._lines):
            raise IndexError("lyric index out of range")

        line = self._lines[index]
        adjusted = position_ms - offset_ms
        end_ms = line.end_ms
        if end_ms is None:
            if index + 1 < len(self._lines):
                end_ms = self._lines[index + 1].start_ms
            else:
                end_ms = line.start_ms

        duration = max(1, end_ms - line.start_ms)
        return max(0.0, min(1.0, (adjusted - line.start_ms) / duration))

    def shifted(self, offset_ms: int) -> "LyricTimeline":
        return LyricTimeline([line.shifted(offset_ms) for line in self._lines])

    def __len__(self) -> int:
        return len(self._lines)

    def __bool__(self) -> bool:
        return bool(self._lines)
