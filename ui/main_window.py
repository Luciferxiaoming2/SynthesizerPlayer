"""PyQt6/QML application shell for the Audio Forge MVP."""

from pathlib import Path
import os
import sys
import traceback

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine

from core_engine.exporter.audio_export import AudioExportConfig, export_processed_mix
from core_engine.importer import SongImportConfig, import_single_song
from core_engine.library.song_scanner import SongAsset, scan_song_library
from core_engine.library.song_session import load_lyrics_timeline, load_song_session
from core_engine.lyrics.playback_sync import LyricPlaybackSynchronizer
from core_engine.lyrics.timeline import LyricTimeline
from core_engine.player.playback_engine import DualTrackPlaybackEngine
from core_engine.player.stem_separator import (
    DemucsSeparatorConfig,
    DemucsStemSeparator,
    PreviewStemSeparator,
)
from core_engine.player.sounddevice_output import (
    AudioOutputDevice,
    SoundDeviceOutput,
    SoundDeviceOutputConfig,
    list_output_devices,
)
from core_engine.player.sync_buffer import write_audio
from core_engine.player.sync_buffer import load_stem_pair
from core_engine.transcription import (
    FasterWhisperConfig,
    FasterWhisperLyricsTranscriber,
    PreviewLyricsTranscriber,
)
from harness.eval_harness.audio_latency_test import evaluate_latency
from harness.cli_harness.generate_mock_audio import build_mock_stems


class WorkbenchBridge(QObject):
    statusChanged = pyqtSignal()
    pathsChanged = pyqtSignal()
    playbackChanged = pyqtSignal()
    lyricsChanged = pyqtSignal()
    songsChanged = pyqtSignal()
    devicesChanged = pyqtSignal()
    importOptionsChanged = pyqtSignal()

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._mock_dir = root / "harness" / "mock_data"
        self._projects_root = root / "projects"
        self._songs_root = root / "源代码" / "Synthesizer Player" / "Synthesizer Player" / "songs"
        self._vocal_path = self._mock_dir / "vocal.wav"
        self._instrumental_path = self._mock_dir / "instrumental.wav"
        self._output_path = self._mock_dir / "ui_export_mix.wav"
        self._lyrics_path = self._mock_dir / "lyrics.lrc"
        self._status = "Ready"
        self._songs: list[SongAsset] = []
        self._audio_devices: list[AudioOutputDevice] = []
        self._selected_audio_device_index = -1
        self._separator_backend = "preview"
        self._lyrics_backend = "preview"
        self._playback: DualTrackPlaybackEngine | None = None
        self._audio_output: SoundDeviceOutput | None = None
        self._audio_output_active = False
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
        self._current_lyric = ""
        self._next_lyric = ""
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(100)
        self._playback_timer.timeout.connect(self.advancePlayback)

    @pyqtProperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @pyqtProperty(str, notify=songsChanged)
    def songsRoot(self) -> str:
        return str(self._songs_root)

    @songsRoot.setter
    def songsRoot(self, value: str) -> None:
        self._songs_root = Path(value)
        self.songsChanged.emit()

    @pyqtProperty("QStringList", notify=songsChanged)
    def songNames(self) -> list[str]:
        return [song.name for song in self._songs]

    @pyqtProperty("QStringList", notify=devicesChanged)
    def audioDeviceNames(self) -> list[str]:
        return [device.label for device in self._audio_devices]

    @pyqtProperty(int, notify=devicesChanged)
    def selectedAudioDeviceIndex(self) -> int:
        return self._selected_audio_device_index

    @pyqtProperty("QStringList", constant=True)
    def separatorBackends(self) -> list[str]:
        return ["preview", "demucs"]

    @pyqtProperty("QStringList", constant=True)
    def lyricsBackends(self) -> list[str]:
        return ["preview", "faster-whisper", "none"]

    @pyqtProperty(str, notify=importOptionsChanged)
    def separatorBackend(self) -> str:
        return self._separator_backend

    @pyqtProperty(str, notify=importOptionsChanged)
    def lyricsBackend(self) -> str:
        return self._lyrics_backend

    @pyqtProperty(str, notify=pathsChanged)
    def vocalPath(self) -> str:
        return str(self._vocal_path)

    @vocalPath.setter
    def vocalPath(self, value: str) -> None:
        self._vocal_path = Path(value)
        self.pathsChanged.emit()

    @pyqtProperty(str, notify=pathsChanged)
    def instrumentalPath(self) -> str:
        return str(self._instrumental_path)

    @instrumentalPath.setter
    def instrumentalPath(self, value: str) -> None:
        self._instrumental_path = Path(value)
        self.pathsChanged.emit()

    @pyqtProperty(str, notify=pathsChanged)
    def outputPath(self) -> str:
        return str(self._output_path)

    @outputPath.setter
    def outputPath(self, value: str) -> None:
        self._output_path = Path(value)
        self.pathsChanged.emit()

    @pyqtProperty(str, notify=pathsChanged)
    def lyricsPath(self) -> str:
        return str(self._lyrics_path)

    @lyricsPath.setter
    def lyricsPath(self, value: str) -> None:
        self._lyrics_path = Path(value)
        self.pathsChanged.emit()

    @pyqtProperty(float, notify=playbackChanged)
    def playbackProgress(self) -> float:
        if self._playback is None:
            return 0.0
        snapshot = self._playback.snapshot()
        if snapshot.duration_seconds <= 0.0:
            return 0.0
        return min(1.0, snapshot.position_seconds / snapshot.duration_seconds)

    @pyqtProperty(str, notify=playbackChanged)
    def playbackTime(self) -> str:
        if self._playback is None:
            return "00:00 / 00:00"
        snapshot = self._playback.snapshot()
        return f"{format_seconds(snapshot.position_seconds)} / {format_seconds(snapshot.duration_seconds)}"

    @pyqtProperty(bool, notify=playbackChanged)
    def isPlaying(self) -> bool:
        return False if self._playback is None else self._playback.is_playing

    @pyqtProperty(bool, notify=playbackChanged)
    def audioOutputActive(self) -> bool:
        return self._audio_output_active

    @pyqtProperty(str, notify=lyricsChanged)
    def currentLyric(self) -> str:
        return self._current_lyric

    @pyqtProperty(str, notify=lyricsChanged)
    def nextLyric(self) -> str:
        return self._next_lyric

    @pyqtSlot()
    def generateMockAudio(self) -> None:
        try:
            self._mock_dir.mkdir(parents=True, exist_ok=True)
            vocal, instrumental = build_mock_stems()
            write_audio(self._vocal_path, vocal, 16_000)
            write_audio(self._instrumental_path, instrumental, 16_000)
            self._lyrics_path.write_text(
                "[00:00.000]Mock intro\n[00:00.700]Tone drift preview\n[00:01.400]Export ready",
                encoding="utf-8",
            )
            self.loadPlayback()
            self._set_status(f"Mock ready: {self._mock_dir}")
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def loadPlayback(self) -> None:
        try:
            self._playback = DualTrackPlaybackEngine(load_stem_pair(self._vocal_path, self._instrumental_path))
            self._lyrics_sync = LyricPlaybackSynchronizer(load_lyrics_timeline(self._lyrics_path))
            self._update_lyrics()
            self.playbackChanged.emit()
            self._set_status("Playback loaded")
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def play(self) -> None:
        if self._playback is None:
            self.loadPlayback()
        if self._playback is None:
            return
        self._playback.play()
        self._audio_output_active = False
        self._playback_timer.start()
        self.playbackChanged.emit()

    @pyqtSlot()
    def pause(self) -> None:
        if self._playback is not None:
            self._playback.pause()
        self._stop_audio_output(reset_engine=False)
        self._playback_timer.stop()
        self.playbackChanged.emit()

    @pyqtSlot()
    def stop(self) -> None:
        if self._playback is not None:
            self._playback.stop()
        self._stop_audio_output(reset_engine=False)
        self._playback_timer.stop()
        self._update_lyrics()
        self.playbackChanged.emit()

    @pyqtSlot()
    def startAudioOutput(self) -> None:
        try:
            if self._playback is None:
                self.loadPlayback()
            if self._playback is None:
                return
            self._stop_audio_output(reset_engine=False)
            self._audio_output = SoundDeviceOutput(
                self._playback,
                SoundDeviceOutputConfig(device=self._selected_audio_device_id()),
            )
            self._audio_output.start()
            self._audio_output_active = True
            self._playback_timer.start()
            self._set_status("Audio output started")
            self.playbackChanged.emit()
        except Exception:
            self._audio_output_active = False
            self._audio_output = None
            self._set_status(traceback.format_exc(limit=1).strip())
            self.playbackChanged.emit()

    @pyqtSlot()
    def stopAudioOutput(self) -> None:
        self._stop_audio_output(reset_engine=True)
        self._update_lyrics()
        self.playbackChanged.emit()

    @pyqtSlot()
    def refreshAudioDevices(self) -> None:
        try:
            self._audio_devices = list_output_devices()
            if not self._audio_devices:
                self._selected_audio_device_index = -1
                self._set_status("No output audio device found")
            else:
                self._selected_audio_device_index = 0
                self._set_status(f"Found {len(self._audio_devices)} output devices")
            self.devicesChanged.emit()
        except Exception:
            self._audio_devices = []
            self._selected_audio_device_index = -1
            self.devicesChanged.emit()
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot(int)
    def selectAudioDevice(self, index: int) -> None:
        if index < 0 or index >= len(self._audio_devices):
            self._selected_audio_device_index = -1
            self._set_status("Default audio device selected")
        else:
            self._selected_audio_device_index = index
            self._set_status(f"Selected audio device: {self._audio_devices[index].label}")
        self.devicesChanged.emit()

    @pyqtSlot(float)
    def seekProgress(self, progress: float) -> None:
        if self._playback is None:
            self.loadPlayback()
        if self._playback is None:
            return
        snapshot = self._playback.snapshot()
        target = max(0.0, min(1.0, progress)) * snapshot.duration_seconds
        self._playback.seek_seconds(target)
        self._update_lyrics()
        self.playbackChanged.emit()

    @pyqtSlot(float, float)
    def setTrackGains(self, vocal_gain: float, instrumental_gain: float) -> None:
        if self._playback is None:
            return
        self._playback.set_gains(vocal_gain=vocal_gain, instrumental_gain=instrumental_gain)
        self.playbackChanged.emit()

    @pyqtSlot(str, str)
    def setPathFromUrl(self, target: str, url: str) -> None:
        path = Path(QUrl(url).toLocalFile())
        if target == "vocal":
            self._vocal_path = path
        elif target == "instrumental":
            self._instrumental_path = path
        elif target == "lyrics":
            self._lyrics_path = path
        elif target == "output":
            self._output_path = path
        else:
            self._set_status(f"Unknown path target: {target}")
            return
        self.pathsChanged.emit()
        self._set_status(f"Selected {target}: {path}")

    @pyqtSlot(str)
    def importSongFromUrl(self, url: str) -> None:
        self.importSongWithBackends(url, self._separator_backend, self._lyrics_backend)

    @pyqtSlot(str, str, str)
    def importSongWithBackends(self, url: str, separator_backend: str, lyrics_backend: str) -> None:
        try:
            source_path = Path(QUrl(url).toLocalFile())
            self._separator_backend = separator_backend
            self._lyrics_backend = lyrics_backend
            self.importOptionsChanged.emit()
            project = import_single_song(
                SongImportConfig(
                    source_path=source_path,
                    projects_root=self._projects_root,
                    separator=self._build_separator(separator_backend),
                    lyrics_transcriber=self._build_lyrics_transcriber(lyrics_backend),
                )
            )
            self._vocal_path = project.stems.vocal_path
            self._instrumental_path = project.stems.instrumental_path
            if project.lyrics_path is not None:
                self._lyrics_path = project.lyrics_path
            self._output_path = project.project_dir / f"{project.name}_export.wav"
            self.pathsChanged.emit()
            self._set_status(f"Imported song project: {project.project_dir}")
            self.loadPlayback()
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot(str)
    def setSeparatorBackend(self, backend: str) -> None:
        self._separator_backend = backend
        self.importOptionsChanged.emit()

    @pyqtSlot(str)
    def setLyricsBackend(self, backend: str) -> None:
        self._lyrics_backend = backend
        self.importOptionsChanged.emit()

    @pyqtSlot(str)
    def setSongsRootFromUrl(self, url: str) -> None:
        self._songs_root = Path(QUrl(url).toLocalFile())
        self.songsChanged.emit()
        self.scanSongs()

    @pyqtSlot()
    def scanSongs(self) -> None:
        try:
            self._songs = scan_song_library(self._songs_root)
            self.songsChanged.emit()
            self._set_status(f"Scanned {len(self._songs)} songs: {self._songs_root}")
        except Exception:
            self._songs = []
            self.songsChanged.emit()
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot(int)
    def loadSongAt(self, index: int) -> None:
        try:
            if index < 0 or index >= len(self._songs):
                self._set_status("No song selected")
                return
            session = load_song_session(self._songs[index])
            self._vocal_path = session.asset.vocal_path
            self._instrumental_path = session.asset.instrumental_path
            if session.asset.lyrics_path is not None:
                self._lyrics_path = session.asset.lyrics_path
            self._output_path = self._mock_dir / f"{sanitize_filename(session.asset.name)}_export.wav"
            self._lyrics_sync = session.lyric_sync()
            self.pathsChanged.emit()
            self.lyricsChanged.emit()
            self._set_status(f"Loaded song: {session.asset.name}")
            self.loadPlayback()
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def advancePlayback(self) -> None:
        if self._playback is None:
            self._playback_timer.stop()
            return
        if not self._audio_output_active:
            self._playback.render_block(max(1, round(self._playback.buffers.sample_rate * 0.1)))
        if not self._playback.is_playing:
            self._playback_timer.stop()
            self._stop_audio_output(reset_engine=False)
        self._update_lyrics()
        self.playbackChanged.emit()

    @pyqtSlot(float, float)
    def exportMix(self, tone_deaf_ratio: float, master_gain_db: float) -> None:
        try:
            result = export_processed_mix(
                AudioExportConfig(
                    vocal_path=self._vocal_path,
                    instrumental_path=self._instrumental_path,
                    output_path=self._output_path,
                    tone_deaf_ratio=tone_deaf_ratio,
                    master_gain_db=master_gain_db,
                )
            )
            self._set_status(
                f"Exported {result.output_path} "
                f"({result.duration_seconds:.2f}s / {result.sample_rate} Hz)"
            )
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def evaluateAlignment(self) -> None:
        try:
            buffers = load_stem_pair(self._vocal_path, self._instrumental_path)
            result = evaluate_latency(
                reference=buffers.instrumental,
                candidate=buffers.vocal,
                sample_rate=buffers.sample_rate,
                max_lag_ms=100.0,
                tolerance_ms=5.0,
            )
            status = "passed" if result.passed else "check"
            self._set_status(
                f"Alignment {status}: latency={result.latency_seconds * 1000.0:.2f}ms "
                f"score={result.score:.3f}"
            )
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    def _update_lyrics(self) -> None:
        position_ms = 0
        if self._playback is not None:
            position_ms = round(self._playback.position_seconds * 1_000)
        state = self._lyrics_sync.state_at(position_ms)
        self._current_lyric = state.current_text or "..."
        self._next_lyric = "" if state.next_line is None else state.next_line.text
        self.lyricsChanged.emit()

    def _stop_audio_output(self, reset_engine: bool) -> None:
        if self._audio_output is not None:
            try:
                if reset_engine:
                    self._audio_output.stop()
                else:
                    self._audio_output.close()
            finally:
                self._audio_output = None
        self._audio_output_active = False

    def _selected_audio_device_id(self) -> int | None:
        if self._selected_audio_device_index < 0:
            return None
        if self._selected_audio_device_index >= len(self._audio_devices):
            return None
        return self._audio_devices[self._selected_audio_device_index].id

    def _build_separator(self, backend: str):
        if backend == "demucs":
            # GUI 默认仍使用 CPU，避免在普通轻薄本上误选不可用 GPU。
            return DemucsStemSeparator(
                DemucsSeparatorConfig(executable=sys.executable, device="cpu")
            )
        return PreviewStemSeparator()

    def _build_lyrics_transcriber(self, backend: str):
        if backend == "faster-whisper":
            return FasterWhisperLyricsTranscriber(
                FasterWhisperConfig(model_size="base", device="cpu", compute_type="int8")
            )
        if backend == "none":
            return None
        return PreviewLyricsTranscriber()

    def _set_status(self, value: str) -> None:
        self._status = value
        self.statusChanged.emit()


def format_seconds(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "song"


def main() -> None:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    user_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else resource_root
    bridge = WorkbenchBridge(user_root)
    engine.rootContext().setContextProperty("audioWorkbench", bridge)
    engine.warnings.connect(lambda warnings: [print(warning.toString()) for warning in warnings])
    engine.load(QUrl.fromLocalFile(str(resource_root / "ui" / "qml" / "SingleScreenUI.qml")))

    if not engine.rootObjects():
        print("Audio Forge UI failed to load QML")
        raise SystemExit(1)
    if os.environ.get("AUDIO_FORGE_UI_SMOKE") == "1":
        print("Audio Forge UI smoke loaded")
        return
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
