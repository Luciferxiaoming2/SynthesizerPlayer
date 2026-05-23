"""PyQt6/QML application shell for the Audio Forge MVP."""

from pathlib import Path
import importlib.util
import os
import sys
import traceback

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine

from core_engine.external_tools import FfmpegAudioStandardizer, FfmpegConfig, resolve_audio_tool
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


class ImportSongWorker(QObject):
    finished = pyqtSignal(object, str, str)
    failed = pyqtSignal(str)

    def __init__(self, config: SongImportConfig, separator_backend: str, lyrics_backend: str) -> None:
        super().__init__()
        self._config = config
        self._separator_backend = separator_backend
        self._lyrics_backend = lyrics_backend

    @pyqtSlot()
    def run(self) -> None:
        try:
            project = import_single_song(self._config)
            self.finished.emit(project, self._separator_backend, self._lyrics_backend)
        except Exception:
            self.failed.emit(traceback.format_exc(limit=1).strip())


class WorkbenchBridge(QObject):
    statusChanged = pyqtSignal()
    pathsChanged = pyqtSignal()
    playbackChanged = pyqtSignal()
    lyricsChanged = pyqtSignal()
    songsChanged = pyqtSignal()
    devicesChanged = pyqtSignal()
    importOptionsChanged = pyqtSignal()
    importBusyChanged = pyqtSignal()

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
        self._master_plugin_paths: list[Path] = []
        self._status = "Ready"
        self._songs: list[SongAsset] = []
        self._current_song_key: tuple[str, str | None] | None = None
        self._audio_devices: list[AudioOutputDevice] = []
        self._selected_audio_device_index = -1
        self._separator_backend = "preview"
        self._lyrics_backend = "preview"
        self._import_busy = False
        self._import_thread: QThread | None = None
        self._import_worker: ImportSongWorker | None = None
        self._playback: DualTrackPlaybackEngine | None = None
        self._audio_output: SoundDeviceOutput | None = None
        self._audio_output_active = False
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
        self._lyric_lines: list[str] = []
        self._current_lyric_index = -1
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

    @pyqtProperty(str, notify=importOptionsChanged)
    def lyricsBackendStatus(self) -> str:
        if self._lyrics_backend == "faster-whisper":
            if is_module_available("faster_whisper"):
                return "faster-whisper 已启用，导入时会尝试识别原始语言歌词"
            return "faster-whisper 未安装，当前不会生效"
        if self._lyrics_backend == "preview":
            return "preview 只生成无歌词占位提示"
        return "不生成歌词；纯音乐或暂无歌词时歌词区为空"

    @pyqtProperty(bool, notify=importBusyChanged)
    def importBusy(self) -> bool:
        return self._import_busy

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

    @pyqtProperty(str, notify=pathsChanged)
    def masterPluginPath(self) -> str:
        if not self._master_plugin_paths:
            return ""
        return str(self._master_plugin_paths[-1])

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

    @pyqtProperty(bool, notify=playbackChanged)
    def vocalMuted(self) -> bool:
        if self._playback is None:
            return False
        return self._playback.controls.vocal_muted

    @pyqtProperty(bool, notify=playbackChanged)
    def instrumentalMuted(self) -> bool:
        if self._playback is None:
            return False
        return self._playback.controls.instrumental_muted

    @pyqtProperty(str, notify=lyricsChanged)
    def currentLyric(self) -> str:
        return self._current_lyric

    @pyqtProperty(str, notify=lyricsChanged)
    def nextLyric(self) -> str:
        return self._next_lyric

    @pyqtProperty("QStringList", notify=lyricsChanged)
    def lyricLines(self) -> list[str]:
        return list(self._lyric_lines)

    @pyqtProperty(int, notify=lyricsChanged)
    def currentLyricIndex(self) -> int:
        return self._current_lyric_index

    @pyqtSlot()
    def generateMockAudio(self) -> None:
        try:
            self._mock_dir.mkdir(parents=True, exist_ok=True)
            vocal, instrumental = build_mock_stems()
            write_audio(self._vocal_path, vocal, 16_000)
            write_audio(self._instrumental_path, instrumental, 16_000)
            self._lyrics_path.write_text(
                "[00:00.000]样例前奏\n[00:00.700]跑调预览\n[00:01.400]可以导出",
                encoding="utf-8",
            )
            self.loadPlayback()
            self._set_status(f"样例音频已生成：{self._mock_dir}")
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def loadPlayback(self) -> None:
        try:
            self._playback = DualTrackPlaybackEngine(load_stem_pair(self._vocal_path, self._instrumental_path))
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline)
            self._lyric_lines = timeline.texts()
            self._update_lyrics()
            self.playbackChanged.emit()
            self._set_status("音频已加载，可以点击“播放”试听")
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
            if self._audio_output_active:
                self._set_status("正在播放")
                return
            self._stop_audio_output(reset_engine=False)
            self._audio_output = SoundDeviceOutput(
                self._playback,
                SoundDeviceOutputConfig(device=self._selected_audio_device_id()),
            )
            self._audio_output.start()
            self._audio_output_active = True
            self._playback_timer.start()
            self._set_status("正在播放；如果听不到声音，请刷新并选择右下角输出设备")
            self.playbackChanged.emit()
        except Exception:
            self._audio_output_active = False
            self._audio_output = None
            self._set_status(f"音频播放失败：{traceback.format_exc(limit=1).strip()}")
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
                self._set_status("没有找到可用输出设备，请检查系统声音设置")
            else:
                self._selected_audio_device_index = 0
                self._set_status(f"已找到 {len(self._audio_devices)} 个输出设备，可在右下角选择耳机或扬声器")
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
            self._set_status(f"已选择输出设备：{self._audio_devices[index].label}")
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

    @pyqtSlot(str)
    def setMasterPluginFromUrl(self, url: str) -> None:
        path = Path(QUrl(url).toLocalFile())
        if not path.exists():
            self._set_status(f"VST 文件不存在：{path}")
            return
        self._master_plugin_paths = [path]
        self.pathsChanged.emit()
        self._set_status(f"已加载主输出 VST：{path.name}。下次导出时生效。")

    @pyqtSlot()
    def clearMasterPlugin(self) -> None:
        self._master_plugin_paths = []
        self.pathsChanged.emit()
        self._set_status("已移除主输出 VST")

    @pyqtSlot()
    def toggleVocalMute(self) -> None:
        if self._playback is None:
            self.loadPlayback()
        if self._playback is None:
            return
        muted = not self._playback.controls.vocal_muted
        self._playback.set_mute(vocal_muted=muted)
        self._set_status("人声已静音" if muted else "人声已恢复")
        self.playbackChanged.emit()

    @pyqtSlot()
    def toggleInstrumentalMute(self) -> None:
        if self._playback is None:
            self.loadPlayback()
        if self._playback is None:
            return
        muted = not self._playback.controls.instrumental_muted
        self._playback.set_mute(instrumental_muted=muted)
        self._set_status("伴奏已静音" if muted else "伴奏已恢复")
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
                self._build_import_config(source_path, separator_backend, lyrics_backend)
            )
            self._apply_imported_project(project, separator_backend, lyrics_backend)
        except Exception:
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))

    @pyqtSlot(str, str, str)
    def importSongWithBackendsAsync(
        self, url: str, separator_backend: str, lyrics_backend: str
    ) -> None:
        if self._import_busy:
            self._set_status("Import already running")
            return
        if lyrics_backend == "faster-whisper" and not is_module_available("faster_whisper"):
            self._lyrics_backend = lyrics_backend
            self.importOptionsChanged.emit()
            self._set_status("faster-whisper 未安装，无法识别歌词。请安装后重试，或切换到 preview/none。")
            return
        source_path = Path(QUrl(url).toLocalFile())
        self._separator_backend = separator_backend
        self._lyrics_backend = lyrics_backend
        self.importOptionsChanged.emit()
        self._set_import_busy(True)
        self._set_status(f"正在导入歌曲... 分离={separator_backend}，歌词={lyrics_backend}")

        self._import_thread = QThread(self)
        self._import_worker = ImportSongWorker(
            self._build_import_config(source_path, separator_backend, lyrics_backend),
            separator_backend,
            lyrics_backend,
        )
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.finished.connect(self._handle_import_finished)
        self._import_worker.failed.connect(self._handle_import_failed)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.failed.connect(self._import_thread.quit)
        self._import_worker.finished.connect(self._import_worker.deleteLater)
        self._import_worker.failed.connect(self._import_worker.deleteLater)
        self._import_thread.finished.connect(self._cleanup_import_thread)
        self._import_thread.start()

    @pyqtSlot(str)
    def setSeparatorBackend(self, backend: str) -> None:
        self._separator_backend = backend
        self.importOptionsChanged.emit()

    @pyqtSlot(str)
    def setLyricsBackend(self, backend: str) -> None:
        self._lyrics_backend = backend
        self.importOptionsChanged.emit()
        if backend == "faster-whisper" and not is_module_available("faster_whisper"):
            self._set_status("faster-whisper 未安装，选择后不会生效；请安装依赖或切换歌词后端。")
        else:
            self._set_status(f"已选择歌词后端：{backend}")

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
            self._set_status(f"已扫描到 {len(self._songs)} 首歌曲：{self._songs_root}")
        except Exception:
            self._songs = []
            self.songsChanged.emit()
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))

    @pyqtSlot(int)
    def loadSongAt(self, index: int) -> None:
        try:
            if index < 0 or index >= len(self._songs):
                self._set_status("请先在左侧选择歌曲")
                return
            selected = self._songs[index]
            if selected.source_path is not None:
                self.importSongWithBackendsAsync(
                    QUrl.fromLocalFile(str(selected.source_path)).toString(),
                    self._separator_backend,
                    self._lyrics_backend,
                )
                return
            session = load_song_session(selected)
            self._current_song_key = song_key(selected)
            self._vocal_path = session.asset.vocal_path
            self._instrumental_path = session.asset.instrumental_path
            if session.asset.lyrics_path is not None:
                self._lyrics_path = session.asset.lyrics_path
            self._output_path = self._mock_dir / f"{sanitize_filename(session.asset.name)}_export.wav"
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline)
            self._lyric_lines = timeline.texts()
            self.pathsChanged.emit()
            self.lyricsChanged.emit()
            self._set_status(f"已加载歌曲：{session.asset.name}")
            self.loadPlayback()
        except Exception:
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))

    @pyqtSlot(int)
    def deleteSongAt(self, index: int) -> None:
        if index < 0 or index >= len(self._songs):
            self._set_status("请先在左侧选择要删除的歌曲")
            return
        removed = self._songs.pop(index)
        removed_current = self._current_song_key == song_key(removed)
        self.songsChanged.emit()
        self._set_status(f"已从列表移除：{removed.name}")
        if not removed_current:
            return

        self.stop()
        if self._songs:
            next_index = min(index, len(self._songs) - 1)
            self.loadSongAt(next_index)
        else:
            self._current_song_key = None
            self._playback = None
            self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
            self._lyric_lines = []
            self._current_lyric = ""
            self._next_lyric = ""
            self._current_lyric_index = -1
            self.lyricsChanged.emit()
            self.playbackChanged.emit()

    @pyqtSlot()
    def clearSongList(self) -> None:
        self.stop()
        self._songs = []
        self._current_song_key = None
        self._playback = None
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
        self._lyric_lines = []
        self._current_lyric = ""
        self._next_lyric = ""
        self._current_lyric_index = -1
        self.songsChanged.emit()
        self.lyricsChanged.emit()
        self.playbackChanged.emit()
        self._set_status("已清空左侧歌曲列表，不会删除磁盘文件")

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
                    master_plugins=list(self._master_plugin_paths),
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
        self._current_lyric_index = -1 if state.current_index is None else state.current_index
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

    def _build_import_config(
        self, source_path: Path, separator_backend: str, lyrics_backend: str
    ) -> SongImportConfig:
        return SongImportConfig(
            source_path=source_path,
            projects_root=self._projects_root,
            separator=self._build_separator(separator_backend),
            lyrics_transcriber=self._build_lyrics_transcriber(lyrics_backend),
            audio_standardizer=self._build_audio_standardizer(source_path),
            separator_backend=separator_backend,
            lyrics_backend=lyrics_backend,
        )

    def _apply_imported_project(self, project, separator_backend: str, lyrics_backend: str) -> None:
        self._vocal_path = project.stems.vocal_path
        self._instrumental_path = project.stems.instrumental_path
        if project.lyrics_path is not None:
            self._lyrics_path = project.lyrics_path
        else:
            self._lyric_lines = []
            self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
        self._output_path = project.project_dir / f"{project.name}_export.wav"
        self._current_song_key = song_key(project.asset)
        self.pathsChanged.emit()
        self.loadPlayback()
        self._upsert_song(project.asset)
        self._set_status(
            f"导入成功：{project.name}（分离={separator_backend}，歌词={lyrics_backend}）。"
            f"{lyrics_backend_status_text(lyrics_backend)}已加入左侧歌曲库。"
        )

    @pyqtSlot(object, str, str)
    def _handle_import_finished(self, project, separator_backend: str, lyrics_backend: str) -> None:
        self._set_import_busy(False)
        self._apply_imported_project(project, separator_backend, lyrics_backend)

    @pyqtSlot(str)
    def _handle_import_failed(self, message: str) -> None:
        self._set_import_busy(False)
        self._set_status(format_user_error(message))

    @pyqtSlot()
    def _cleanup_import_thread(self) -> None:
        if self._import_thread is not None:
            self._import_thread.deleteLater()
        self._import_thread = None
        self._import_worker = None

    def _set_import_busy(self, value: bool) -> None:
        if self._import_busy == value:
            return
        self._import_busy = value
        self.importBusyChanged.emit()

    def _upsert_song(self, asset: SongAsset) -> None:
        self._songs = [
            song for song in self._songs
            if song.root != asset.root and song.source_path != asset.source_path
        ]
        self._songs.insert(0, asset)
        self.songsChanged.emit()

    def _build_separator(self, backend: str):
        if backend == "demucs":
            # GUI 默认仍使用 CPU，避免在普通轻薄本上误选不可用 GPU。
            ffmpeg_dir = first_existing_dir(
                self._root / "plugins" / "models" / "ffmpeg",
                self._root
                / "源代码"
                / "Synthesizer Player"
                / "Synthesizer Player"
                / "ffmpeg"
                / "bin",
            )
            torch_home = self._root / "plugins" / "models" / "torch"
            return DemucsStemSeparator(
                DemucsSeparatorConfig(
                    executable=resolve_demucs_python(self._root),
                    device="cpu",
                    ffmpeg_dir=ffmpeg_dir,
                    torch_home=torch_home if torch_home.exists() else None,
                    runner_script=demucs_runner_script(self._root),
                )
            )
        return PreviewStemSeparator()

    def _build_lyrics_transcriber(self, backend: str):
        if backend == "faster-whisper":
            if not is_module_available("faster_whisper"):
                raise RuntimeError("faster-whisper 未安装，无法识别歌词。请安装依赖后重试。")
            return FasterWhisperLyricsTranscriber(
                FasterWhisperConfig(model_size="base", device="cpu", compute_type="int8")
            )
        if backend == "none":
            return None
        return PreviewLyricsTranscriber()

    def _build_audio_standardizer(self, source_path: Path) -> FfmpegAudioStandardizer | None:
        if source_path.suffix.lower() == ".wav":
            return None
        try:
            ffmpeg = resolve_audio_tool("ffmpeg", self._root)
        except FileNotFoundError:
            return None
        return FfmpegAudioStandardizer(FfmpegConfig(executable=ffmpeg))

    def _set_status(self, value: str) -> None:
        self._status = value
        self.statusChanged.emit()


def format_seconds(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "song"


def song_key(song: SongAsset) -> tuple[str, str | None]:
    return (str(song.root), None if song.source_path is None else str(song.source_path))


def is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def lyrics_backend_status_text(backend: str) -> str:
    if backend == "faster-whisper":
        return "faster-whisper 已执行。"
    if backend == "preview":
        return "未找到真实歌词时会显示占位提示。"
    return "未生成歌词，纯音乐或暂无歌词时歌词区为空。"


def format_user_error(message: str) -> str:
    if "faster-whisper" in message or "faster_whisper" in message:
        return "歌词识别失败：faster-whisper 未安装或不可用。请安装依赖后重试，或切换到 preview/none。"
    if "Format not recognised" in message or "Format not recognized" in message:
        return "导入失败：当前音频格式不能直接读取。请确认 ffmpeg 已放在 plugins/models/ffmpeg，或先转换为 wav。"
    if "ffmpeg" in message and "not found" in message:
        return "导入失败：没有找到 ffmpeg，无法兼容 mp3/m4a/aac 等格式。请把 ffmpeg 放到 plugins/models/ffmpeg。"
    if "FileNotFoundError" in message or "source song not found" in message:
        return "导入失败：没有找到选择的音乐文件，请检查文件是否被移动或删除。"
    if "CalledProcessError" in message:
        return "导入失败：外部工具执行失败，请换一首歌测试，或查看文件是否损坏。"
    return message


def first_existing_dir(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_demucs_python(root: Path) -> str:
    configured = os.environ.get("AUDIO_FORGE_DEMUCS_PYTHON")
    if configured:
        return configured

    candidates = [
        root / "plugins" / "models" / "python" / "python.exe",
        root / "python" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    if not getattr(sys, "frozen", False):
        return sys.executable
    return "python"


def demucs_runner_script(root: Path) -> Path | None:
    candidates = [
        root / "core_engine" / "player" / "demucs_soundfile_runner.py",
        root / "_internal" / "core_engine" / "player" / "demucs_soundfile_runner.py",
        Path(__file__).resolve().parents[1] / "core_engine" / "player" / "demucs_soundfile_runner.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


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
