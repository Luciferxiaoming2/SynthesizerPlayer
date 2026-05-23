# Audio Engine Spec

## Purpose

`core_engine/` contains UI-free audio logic for playback, DSP, VST hosting, and
AI singing adapters.

## Contracts

- Inputs and outputs should be explicit paths, numpy arrays, sample rates, or
  small dataclasses.
- Engine code must be callable from CLI and eval harnesses.
- Engine code must not import PyQt, PySide, QML, or `ui`.
- Long-running or external AI runtimes must sit behind adapter classes.

## Initial Modules

- `core_engine/player/sync_buffer.py`: sample-aligned vocal/instrumental buffers.
- `core_engine/player/stem_separator.py`: boundary for Spleeter/UVR5.
- `core_engine/dsp/tone_deaf.py`: F0 drift based offline render path.
- `core_engine/dsp/vst_host.py`: Pedalboard/VST effect boundary.
- `core_engine/ai_singer/`: DiffSinger and RVC adapter boundaries.

