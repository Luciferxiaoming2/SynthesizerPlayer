# Audio Forge

Audio Forge is structured around a strict split between the UI-free audio engine,
command-line/evaluation harnesses, and the PyQt/QML view layer.

## Architecture

- `core_engine/`: pure playback, DSP, VST, and AI singer logic. This layer must not import PyQt or QML.
- `harness/`: CLI execution and automated evaluation entry points for engine-only workflows.
- `ui/`: PyQt/QML shell and view models. This layer binds user gestures to `core_engine`.
- `plugins/`: local VST3 plugins and AI model weights. Heavy binaries should stay out of source control.
- `docs/`: PRD and technical planning documents.
- `.agent/`: task/context templates plus ignored runtime traces, reports, and workspaces.
- `scripts/`: local architecture and agent-harness checks.

## First Milestones

1. Wire `core_engine.player.sync_buffer` to SoundDevice/PySoundFile for aligned dual-track playback.
2. Implement `harness.eval_harness.audio_latency_test` with cross-correlation based sync metrics.
3. Replace the placeholder in `core_engine.dsp.tone_deaf` with PyWorld F0 extraction and chunked offline rendering.
4. Add DiffSinger and RVC adapters behind `core_engine.ai_singer` boundaries.
5. Bind the QML single-screen view to lightweight view models only after the harness paths run.

## Commands

```powershell
D:\uv\venvs\audio_forge\Scripts\activate
uv pip install -e ".[dev,dsp]"
make run-pitch
make test-harness
make run-ui
D:\uv\venvs\audio_forge\Scripts\python.exe scripts\run_agent_checks.py
```

The project virtual environment is expected at `D:\uv\venvs\audio_forge`.

## Local Audio Harness

Generate deterministic local stems:

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.generate_mock_audio --output-dir harness\mock_data
```

Render an offline dual-track mix:

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.run_dual_mix --vocal harness\mock_data\vocal.wav --instrumental harness\mock_data\instrumental.wav --output harness\mock_data\mix.wav
```

Render and analyze tone-deaf drift:

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.run_pitch_shift --input harness\mock_data\vocal.wav --output harness\mock_data\vocal_tone_deaf.wav --ratio 0.4
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.analyze_f0_drift --original harness\mock_data\vocal.wav --processed harness\mock_data\vocal_tone_deaf.wav
```

Play through SoundDevice after confirming your output device and volume:

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.run_playback --vocal harness\mock_data\vocal.wav --instrumental harness\mock_data\instrumental.wav
```

During playback, the CLI accepts:

```text
status
play
pause
stop
seek 1.5
gain vocal 0.6
gain instrumental 0.8
mute vocal on
solo instrumental on
quit
```
