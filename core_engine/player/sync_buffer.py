"""Synchronized in-memory buffers for vocal and instrumental tracks."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

AlignmentMode = Literal["strict", "pad", "trim"]


@dataclass(frozen=True)
class StereoTrackBuffer:
    """A pair of aligned audio tracks with a shared sample rate."""

    vocal: np.ndarray
    instrumental: np.ndarray
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.vocal.ndim != 2 or self.instrumental.ndim != 2:
            raise ValueError("audio buffers must have shape (frames, channels)")
        if self.vocal.shape[0] != self.instrumental.shape[0]:
            raise ValueError("vocal and instrumental buffers must be sample-aligned")
        if self.vocal.shape[1] != self.instrumental.shape[1]:
            raise ValueError("vocal and instrumental buffers must have the same channel count")

    @property
    def frame_count(self) -> int:
        return int(self.vocal.shape[0])

    @property
    def channel_count(self) -> int:
        return int(self.vocal.shape[1])

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    def slice_frames(self, start_frame: int, frame_count: int) -> "StereoTrackBuffer":
        if start_frame < 0:
            raise ValueError("start_frame must be non-negative")
        if frame_count < 0:
            raise ValueError("frame_count must be non-negative")
        end_frame = min(start_frame + frame_count, self.frame_count)
        return StereoTrackBuffer(
            vocal=self.vocal[start_frame:end_frame].copy(),
            instrumental=self.instrumental[start_frame:end_frame].copy(),
            sample_rate=self.sample_rate,
        )

    def with_vocal(self, vocal: np.ndarray) -> "StereoTrackBuffer":
        return StereoTrackBuffer(
            vocal=ensure_2d_float32(vocal),
            instrumental=self.instrumental.copy(),
            sample_rate=self.sample_rate,
        )

    def with_instrumental(self, instrumental: np.ndarray) -> "StereoTrackBuffer":
        return StereoTrackBuffer(
            vocal=self.vocal.copy(),
            instrumental=ensure_2d_float32(instrumental),
            sample_rate=self.sample_rate,
        )


def ensure_2d_float32(audio: np.ndarray) -> np.ndarray:
    """Normalize audio arrays to ``(frames, channels)`` float32."""

    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, np.newaxis]
    if array.ndim != 2:
        raise ValueError("audio must be mono or channel-last 2D")
    return np.ascontiguousarray(array)


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    """Read an audio file as float32 frames and its sample rate."""

    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    return ensure_2d_float32(audio), int(sample_rate)


def match_channel_count(vocal: np.ndarray, instrumental: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Match mono/stereo channel counts without changing frame alignment."""

    if vocal.shape[1] == instrumental.shape[1]:
        return vocal, instrumental
    if vocal.shape[1] == 1:
        return np.repeat(vocal, instrumental.shape[1], axis=1), instrumental
    if instrumental.shape[1] == 1:
        return vocal, np.repeat(instrumental, vocal.shape[1], axis=1)
    raise ValueError("cannot match incompatible channel counts")


def align_by_frame_count(
    vocal: np.ndarray,
    instrumental: np.ndarray,
    mode: AlignmentMode = "pad",
) -> tuple[np.ndarray, np.ndarray]:
    """Align two tracks by frame count using strict, pad, or trim semantics."""

    vocal = ensure_2d_float32(vocal)
    instrumental = ensure_2d_float32(instrumental)
    vocal, instrumental = match_channel_count(vocal, instrumental)

    vocal_frames = vocal.shape[0]
    instrumental_frames = instrumental.shape[0]
    if vocal_frames == instrumental_frames:
        return vocal, instrumental

    if mode == "strict":
        raise ValueError(
            "vocal and instrumental frame counts differ: "
            f"{vocal_frames} != {instrumental_frames}"
        )

    if mode == "trim":
        target = min(vocal_frames, instrumental_frames)
        return vocal[:target].copy(), instrumental[:target].copy()

    if mode == "pad":
        target = max(vocal_frames, instrumental_frames)
        return pad_to_frame_count(vocal, target), pad_to_frame_count(instrumental, target)

    raise ValueError(f"unsupported alignment mode: {mode}")


def pad_to_frame_count(audio: np.ndarray, frame_count: int) -> np.ndarray:
    if frame_count < audio.shape[0]:
        raise ValueError("frame_count must not be shorter than audio")
    if frame_count == audio.shape[0]:
        return audio.copy()
    padding = np.zeros((frame_count - audio.shape[0], audio.shape[1]), dtype=np.float32)
    return np.concatenate([audio, padding], axis=0)


def load_stem_pair(
    vocal_path: Path,
    instrumental_path: Path,
    alignment: AlignmentMode = "pad",
) -> StereoTrackBuffer:
    """Load vocal and instrumental files into one sample-aligned buffer."""

    vocal, vocal_rate = read_audio(vocal_path)
    instrumental, instrumental_rate = read_audio(instrumental_path)
    if vocal_rate != instrumental_rate:
        raise ValueError(f"sample rates differ: {vocal_rate} != {instrumental_rate}")

    aligned_vocal, aligned_instrumental = align_by_frame_count(vocal, instrumental, alignment)
    return StereoTrackBuffer(
        vocal=aligned_vocal,
        instrumental=aligned_instrumental,
        sample_rate=vocal_rate,
    )


def mix_aligned_tracks(
    buffers: StereoTrackBuffer,
    vocal_gain: float = 1.0,
    instrumental_gain: float = 1.0,
    clip: bool = True,
) -> np.ndarray:
    """Mix two already-aligned tracks without changing timing."""

    mixed = (buffers.vocal * vocal_gain) + (buffers.instrumental * instrumental_gain)
    if clip:
        mixed = np.clip(mixed, -1.0, 1.0)
    return np.asarray(mixed, dtype=np.float32)


def write_audio(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write float audio with a stable shape."""

    sf.write(path, ensure_2d_float32(audio), sample_rate)
