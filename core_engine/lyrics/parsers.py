"""LRC and SRT parsers extracted from the legacy player concept."""

import re

from core_engine.lyrics.timeline import LyricLine, LyricTimeline

LRC_TIME_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\](.*)")
SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{1,3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{1,3})"
)
LRC_METADATA_PREFIXES = ("[ti:", "[ar:", "[al:", "[by:", "[offset:")


def fraction_to_ms(value: str | None) -> int:
    if not value:
        return 0
    if len(value) == 1:
        return int(value) * 100
    if len(value) == 2:
        return int(value) * 10
    return int(value[:3])


def hms_to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + fraction_to_ms(millis)
    )


def ms_to_timestamp(minutes: str, seconds: str, fraction: str | None) -> int:
    return int(minutes) * 60_000 + int(seconds) * 1_000 + fraction_to_ms(fraction)


def parse_lrc(content: str) -> LyricTimeline:
    lines: list[LyricLine] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith(LRC_METADATA_PREFIXES):
            continue

        match = LRC_TIME_RE.match(line)
        if not match:
            continue

        text = match.group(4).strip()
        if not text:
            continue

        lines.append(
            LyricLine(
                start_ms=ms_to_timestamp(match.group(1), match.group(2), match.group(3)),
                text=text,
            )
        )

    return LyricTimeline(lines)


def parse_srt(content: str) -> LyricTimeline:
    lines: list[LyricLine] = []
    blocks = re.split(r"\r?\n\r?\n", content.strip())
    for block in blocks:
        parts = [part.strip() for part in block.splitlines() if part.strip()]
        if len(parts) < 2:
            continue

        time_line = parts[1] if parts[0].isdigit() and len(parts) >= 3 else parts[0]
        text_start = 2 if parts[0].isdigit() and len(parts) >= 3 else 1
        match = SRT_TIME_RE.search(time_line)
        if not match:
            continue

        text = " ".join(parts[text_start:]).strip()
        if not text:
            continue

        lines.append(
            LyricLine(
                start_ms=hms_to_ms(match.group(1), match.group(2), match.group(3), match.group(4)),
                end_ms=hms_to_ms(match.group(5), match.group(6), match.group(7), match.group(8)),
                text=text,
            )
        )

    return LyricTimeline(lines)


def parse_lyrics_by_suffix(path_suffix: str, content: str) -> LyricTimeline:
    suffix = path_suffix.lower()
    if suffix == ".srt":
        return parse_srt(content)
    if suffix == ".lrc":
        return parse_lrc(content)
    raise ValueError(f"unsupported lyric suffix: {path_suffix}")

