"""Run Demucs with a soundfile-based wav writer.

Recent torchaudio versions can route wav saving through torchcodec, which needs
shared FFmpeg DLLs on Windows. The migrated app already depends on soundfile, so
this small runner keeps Demucs for separation while using soundfile for wav
output.
"""

from pathlib import Path
import sys

import soundfile as sf


def save_audio_with_soundfile(
    wav,
    path,
    samplerate: int,
    bitrate: int = 320,
    clip: str = "rescale",
    bits_per_sample: int = 16,
    as_float: bool = False,
    preset: int = 2,
) -> None:
    from demucs.audio import prevent_clip, save_audio as original_save_audio

    output_path = Path(path)
    if output_path.suffix.lower() != ".wav":
        original_save_audio(
            wav,
            path,
            samplerate=samplerate,
            bitrate=bitrate,
            clip=clip,
            bits_per_sample=bits_per_sample,
            as_float=as_float,
            preset=preset,
        )
        return

    wav = prevent_clip(wav, mode=clip)
    data = wav.detach().cpu().numpy().T
    subtype = "FLOAT" if as_float else ("PCM_24" if bits_per_sample == 24 else "PCM_16")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, data, samplerate, subtype=subtype)


def main(argv: list[str] | None = None) -> None:
    import demucs.audio
    import demucs.separate

    demucs.audio.save_audio = save_audio_with_soundfile
    demucs.separate.save_audio = save_audio_with_soundfile
    demucs.separate.main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
