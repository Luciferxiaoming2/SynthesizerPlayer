"""Map playback position to UI-ready lyric state."""

from dataclasses import dataclass

from core_engine.lyrics.timeline import LyricLine, LyricTimeline


@dataclass(frozen=True)
class LyricPlaybackState:
    position_ms: int
    offset_ms: int
    current_index: int | None
    current_line: LyricLine | None
    previous_line: LyricLine | None
    next_line: LyricLine | None
    current_text: str
    line_progress: float


class LyricPlaybackSynchronizer:
    """Pure state mapper for playback position and lyric timeline."""

    def __init__(self, timeline: LyricTimeline, offset_ms: int = 0) -> None:
        self._timeline = timeline
        self._offset_ms = offset_ms

    @property
    def offset_ms(self) -> int:
        return self._offset_ms

    def with_offset(self, offset_ms: int) -> "LyricPlaybackSynchronizer":
        return LyricPlaybackSynchronizer(self._timeline, offset_ms)

    def state_at(self, position_ms: int) -> LyricPlaybackState:
        if position_ms < 0:
            raise ValueError("position_ms must be non-negative")

        lines = self._timeline.lines
        current_index = self._timeline.line_at(position_ms, self._offset_ms)
        current_line = lines[current_index] if current_index is not None else None
        previous_line = None
        next_line = None
        line_progress = 0.0

        if current_index is not None:
            if current_index > 0:
                previous_line = lines[current_index - 1]
            if current_index + 1 < len(lines):
                next_line = lines[current_index + 1]
            line_progress = self._timeline.line_progress(
                current_index,
                position_ms,
                self._offset_ms,
            )
        elif lines:
            next_line = lines[0]

        return LyricPlaybackState(
            position_ms=position_ms,
            offset_ms=self._offset_ms,
            current_index=current_index,
            current_line=current_line,
            previous_line=previous_line,
            next_line=next_line,
            current_text=current_line.text if current_line is not None else "",
            line_progress=line_progress,
        )

