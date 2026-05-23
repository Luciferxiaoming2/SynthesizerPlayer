# UI Layer Spec

## Purpose

`ui/` contains the PyQt/QML single-screen view layer and view models.

## Rules

- UI code may call `core_engine` services.
- UI code should not implement DSP, AI inference, or playback algorithms.
- QML should remain a presentation surface backed by Python view models.

