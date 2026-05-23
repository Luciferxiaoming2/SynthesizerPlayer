"""Offline VST/effect hosting boundary built around optional pedalboard."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core_engine.player.sync_buffer import ensure_2d_float32


class PedalboardUnavailableError(RuntimeError):
    """Raised when plugin processing is requested without pedalboard installed."""


class PluginLoadError(RuntimeError):
    """Raised when a plugin cannot be loaded."""


@dataclass(frozen=True)
class OfflineEffectConfig:
    gain_db: float = 0.0


class VstEffectChain:
    """Offline effect chain with optional VST plugin support."""

    def __init__(self, config: OfflineEffectConfig | None = None) -> None:
        self._config = config or OfflineEffectConfig()
        self._plugin_paths: list[Path] = []
        self._loaded_plugins: list[object] | None = None

    def add_plugin(self, plugin_path: Path) -> None:
        if not plugin_path.exists():
            raise FileNotFoundError(plugin_path)
        self._plugin_paths.append(plugin_path)
        self._loaded_plugins = None

    @property
    def plugin_paths(self) -> list[Path]:
        return list(self._plugin_paths)

    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        processed = ensure_2d_float32(audio)
        processed = apply_gain(processed, self._config.gain_db)
        if self._plugin_paths:
            processed = self._process_plugins(processed, sample_rate)
        return np.asarray(processed, dtype=np.float32)

    def _process_plugins(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        try:
            from pedalboard import Pedalboard, load_plugin
        except ImportError as exc:
            raise PedalboardUnavailableError(
                "pedalboard is required to load VST plugins. "
                "Install it with `uv pip install pedalboard --python D:\\uv\\venvs\\audio_forge\\Scripts\\python.exe`."
            ) from exc

        if self._loaded_plugins is None:
            loaded = []
            for path in self._plugin_paths:
                try:
                    loaded.append(load_plugin(str(path)))
                except Exception as exc:  # pragma: no cover - depends on external plugins
                    raise PluginLoadError(f"failed to load plugin {path}: {exc}") from exc
            self._loaded_plugins = loaded

        board = Pedalboard(self._loaded_plugins)
        channels_first = audio.T
        processed = board(channels_first, sample_rate)
        return ensure_2d_float32(np.asarray(processed).T)


def apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    linear = float(10.0 ** (gain_db / 20.0))
    return np.asarray(audio * linear, dtype=np.float32)
