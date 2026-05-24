"""PyQt6/QML application shell for the Audio Forge MVP."""

from pathlib import Path
import importlib.util
import json
import os
import sys
import traceback

from PyQt6.QtCore import QCoreApplication, QObject, QThread, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine

from core_engine.external_tools import (
    FfmpegAudioStandardizer,
    FfmpegConfig,
    FfmpegMp3Config,
    FfmpegMp3Encoder,
    resolve_audio_tool,
)
from core_engine.dsp.tone_deaf import ToneDeafConfig
from core_engine.dsp.tone_deaf_cache import ToneDeafBufferCache
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
    LyricsTranscriptionRequest,
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


class LyricsGenerationWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, transcriber, audio_path: Path, output_path: Path) -> None:
        super().__init__()
        self._transcriber = transcriber
        self._audio_path = audio_path
        self._output_path = output_path

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.progress.emit(15, "正在准备音频")
            self.progress.emit(45, "正在识别歌词，界面可以继续操作")
            path = self._transcriber.transcribe(
                LyricsTranscriptionRequest(audio_path=self._audio_path, output_path=self._output_path)
            )
            self.progress.emit(90, "正在整理歌词时间轴")
            self.finished.emit(str(path))
        except Exception:
            self.failed.emit(traceback.format_exc(limit=1).strip())


class WorkbenchBridge(QObject):
    statusChanged = pyqtSignal()
    pathsChanged = pyqtSignal()
    playbackChanged = pyqtSignal()
    lyricsChanged = pyqtSignal()
    lyricLinesChanged = pyqtSignal()
    lyricPositionChanged = pyqtSignal()
    songsChanged = pyqtSignal()
    devicesChanged = pyqtSignal()
    importOptionsChanged = pyqtSignal()
    importBusyChanged = pyqtSignal()
    lyricsGenerationPromptRequested = pyqtSignal(str)
    lyricsGenerationChanged = pyqtSignal()

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._mock_dir = root / "harness" / "mock_data"
        self._projects_root = root / "导入歌曲"
        self._projects_root.mkdir(parents=True, exist_ok=True)
        self._songs_root = self._projects_root
        self._vocal_path = self._mock_dir / "vocal.wav"
        self._instrumental_path = self._mock_dir / "instrumental.wav"
        self._output_path = self._mock_dir / "ui_export_mix.wav"
        self._lyrics_path = self._mock_dir / "lyrics.lrc"
        self._current_source_path: Path | None = None
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
        self._lyrics_generation_busy = False
        self._lyrics_generation_progress = 0
        self._lyrics_generation_status = ""
        self._lyrics_thread: QThread | None = None
        self._lyrics_worker: LyricsGenerationWorker | None = None
        self._playback: DualTrackPlaybackEngine | None = None
        self._audio_output: SoundDeviceOutput | None = None
        self._audio_output_active = False
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
        self._lyric_lines: list[str] = []
        self._current_lyric_index = -1
        self._current_lyric = ""
        self._next_lyric = ""
        self._lyrics_offset_ms = 0
        self._tone_deaf_ratio = 0.4
        self._last_alignment_latency_ms: float | None = None
        self._last_alignment_passed: bool | None = None
        self._tone_deaf_cache = ToneDeafBufferCache()
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
    def separatorBackendLabels(self) -> list[str]:
        return [separator_backend_label(backend) for backend in self.separatorBackends]

    @pyqtProperty("QStringList", constant=True)
    def lyricsBackends(self) -> list[str]:
        return ["preview", "faster-whisper", "none"]

    @pyqtProperty("QStringList", constant=True)
    def lyricsBackendLabels(self) -> list[str]:
        return [lyrics_backend_label(backend) for backend in self.lyricsBackends]

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
                if self._local_lyrics_model_path() is not None:
                    return "智能识别已就绪：会自动生成中文或英文歌词"
                return "智能识别组件已安装，模型文件未随包放入；请联系交付人员补齐模型包"
            return "智能识别组件未打包，请使用包含歌词识别的完整版本"
        if self._lyrics_backend == "preview":
            return "占位提示：不会识别内容，只提示用户导入歌词或安装识别依赖"
        return "不生成歌词：适合纯音乐，歌词区会显示暂无歌词"

    @pyqtProperty(bool, notify=importBusyChanged)
    def importBusy(self) -> bool:
        return self._import_busy

    @pyqtProperty(bool, notify=lyricsGenerationChanged)
    def lyricsGenerationBusy(self) -> bool:
        return self._lyrics_generation_busy

    @pyqtProperty(int, notify=lyricsGenerationChanged)
    def lyricsGenerationProgress(self) -> int:
        return self._lyrics_generation_progress

    @pyqtProperty(str, notify=lyricsGenerationChanged)
    def lyricsGenerationStatus(self) -> str:
        return self._lyrics_generation_status

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

    @pyqtProperty(str, notify=lyricPositionChanged)
    def currentLyric(self) -> str:
        return self._current_lyric

    @pyqtProperty(str, notify=lyricPositionChanged)
    def nextLyric(self) -> str:
        return self._next_lyric

    @pyqtProperty("QStringList", notify=lyricLinesChanged)
    def lyricLines(self) -> list[str]:
        return list(self._lyric_lines)

    @pyqtProperty(int, notify=lyricPositionChanged)
    def currentLyricIndex(self) -> int:
        return self._current_lyric_index

    @pyqtProperty(int, notify=lyricPositionChanged)
    def lyricsOffsetMs(self) -> int:
        return self._lyrics_offset_ms

    @pyqtProperty(str, notify=lyricPositionChanged)
    def lyricsOffsetLabel(self) -> str:
        return format_offset_ms(self._lyrics_offset_ms)

    @pyqtProperty(float, notify=playbackChanged)
    def toneDeafRatio(self) -> float:
        return self._tone_deaf_ratio

    @pyqtProperty(int, notify=importOptionsChanged)
    def rightPanelPresetIndex(self) -> int:
        return 1 if self._separator_backend == "demucs" else 0

    @pyqtProperty(str, notify=playbackChanged)
    def sampleRateLabel(self) -> str:
        if self._playback is None:
            return "未加载"
        return f"{round(self._playback.buffers.sample_rate / 1000)}kHz"

    @pyqtProperty(str, notify=playbackChanged)
    def toneMonitorStatus(self) -> str:
        if self._playback is None:
            return "请先导入或加载歌曲"
        if self._tone_deaf_ratio <= 0.01:
            return "原声稳定"
        if self._tone_deaf_ratio < 0.35:
            return "轻微跑调预览中"
        if self._tone_deaf_ratio < 0.7:
            return "明显跑调已应用"
        return "强跑调已应用，注意音量"

    @pyqtProperty(str, notify=playbackChanged)
    def alignmentLatencyStatus(self) -> str:
        if self._last_alignment_latency_ms is None:
            return "未检测"
        status = "通过" if self._last_alignment_passed else "需检查"
        return f"{self._last_alignment_latency_ms:.2f}ms（{status}）"

    @pyqtProperty(str, notify=playbackChanged)
    def outputEngineStatus(self) -> str:
        if self._audio_output_active:
            return "播放中"
        if self._audio_devices:
            return "已就绪"
        return "未检测到设备"

    @pyqtProperty(str, notify=pathsChanged)
    def masterPluginStatus(self) -> str:
        if not self._master_plugin_paths:
            return "未加载 VST"
        return f"已加载：{self._master_plugin_paths[-1].name}"

    @pyqtProperty(str, notify=importOptionsChanged)
    def lyricsEngineStatus(self) -> str:
        return lyrics_backend_label(self._lyrics_backend)

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
            self._current_source_path = self._vocal_path
            self.loadPlayback()
            self._set_status(f"样例音频已生成：{self._mock_dir}")
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def loadPlayback(self) -> None:
        try:
            buffers = self._build_playback_buffers()
            self._playback = DualTrackPlaybackEngine(buffers)
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
            self._lyric_lines = timeline.texts()
            self._emit_lyrics_reloaded()
            self._update_lyrics()
            self.playbackChanged.emit()
            tone_text = "，已应用跑调" if self._tone_deaf_ratio > 0.01 else ""
            self._set_status(f"音频已加载{tone_text}，可以点击“播放”试听")
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
            self._set_status("已切换为系统默认输出设备")
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

    @pyqtSlot(float)
    def setToneDeafRatio(self, ratio: float) -> None:
        self._tone_deaf_ratio = max(0.0, min(1.0, float(ratio)))
        if self._playback is None:
            self._set_status("已设置跑调强度；导入、加载或导出时生效")
            self.playbackChanged.emit()
            return

        try:
            buffers = self._build_playback_buffers()
            self._playback.replace_buffers(buffers, keep_position=True)
            self.playbackChanged.emit()
            if self._playback.is_playing:
                self._set_status(
                    f"已实时应用跑调强度：{round(self._tone_deaf_ratio * 100)}%，播放会继续"
                )
            else:
                self._set_status(f"已应用跑调强度：{round(self._tone_deaf_ratio * 100)}%")
        except Exception:
            self._set_status(f"跑调处理失败：{traceback.format_exc(limit=1).strip()}")

    @pyqtSlot(int)
    def setRightPanelPreset(self, index: int) -> None:
        if index == 1:
            self.setSeparatorBackend("demucs")
            self._set_status("右栏预设已切换为“极致消除”：下一次导入会使用 Demucs 人声分离")
            return
        self.setSeparatorBackend("preview")
        self._set_status("右栏预设已切换为“标准人声”：下一次导入会使用快速预览分离")

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

    @pyqtSlot(int)
    def setLyricsOffsetMs(self, offset_ms: int) -> None:
        self._lyrics_offset_ms = max(-10_000, min(10_000, int(offset_ms)))
        self._lyrics_sync = self._lyrics_sync.with_offset(self._lyrics_offset_ms)
        self._update_lyrics()
        self.lyricPositionChanged.emit()
        if self._lyrics_offset_ms == 0:
            self._set_status("歌词对齐已恢复为 0 秒，不做校正")
        elif self._lyrics_offset_ms > 0:
            self._set_status(f"歌词已延迟 {format_offset_ms(self._lyrics_offset_ms)}")
        else:
            self._set_status(f"歌词已提前 {format_offset_ms(abs(self._lyrics_offset_ms))}")

    @pyqtSlot(int)
    def adjustLyricsOffsetMs(self, delta_ms: int) -> None:
        self.setLyricsOffsetMs(self._lyrics_offset_ms + int(delta_ms))

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
            self._set_status(f"不支持的文件类型：{target}")
            return
        self.pathsChanged.emit()
        self._set_status(f"已选择{path_target_label(target)}：{path}")

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
            self._set_status("歌曲正在导入中，请稍等")
            return
        if lyrics_backend == "faster-whisper" and not is_module_available("faster_whisper"):
            self._lyrics_backend = lyrics_backend
            self.importOptionsChanged.emit()
            self._set_status(
                "当前版本没有内置智能歌词识别组件，请使用完整安装包，"
                "或先切换为“占位提示/不生成歌词”。"
            )
            return
        source_path = Path(QUrl(url).toLocalFile())
        self._separator_backend = separator_backend
        self._lyrics_backend = lyrics_backend
        self.importOptionsChanged.emit()
        self._set_import_busy(True)
        self._set_status(
            "正在导入歌曲... "
            f"分离={separator_backend_label(separator_backend)}，"
            f"歌词={lyrics_backend_label(lyrics_backend)}"
        )

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
        self._set_status(f"已选择分离方式：{separator_backend_label(backend)}")

    @pyqtSlot(str)
    def setLyricsBackend(self, backend: str) -> None:
        self._lyrics_backend = backend
        self.importOptionsChanged.emit()
        if backend == "faster-whisper" and not is_module_available("faster_whisper"):
            self._set_status("当前版本没有内置智能歌词识别组件，请使用完整安装包。")
        else:
            self._set_status(f"已选择歌词方式：{lyrics_backend_label(backend)}")

    @pyqtSlot()
    def generateLyrics(self) -> None:
        if self._lyrics_generation_busy:
            self._set_status("歌词正在生成中，请稍等。")
            return
        if self._lyrics_backend == "none":
            self._set_status("当前歌词方式是“不生成歌词”。请先切换为“占位提示”或“本地识别”。")
            return
        if self._lyrics_backend == "faster-whisper" and not is_module_available("faster_whisper"):
            self._set_status(
                "当前版本没有内置智能歌词识别组件，请使用完整安装包；"
                "也可以先选择“占位提示”，或导入同名 .lrc/.srt 歌词文件。"
            )
            return

        audio_path = self._lyrics_source_audio_path()
        if audio_path is None or not audio_path.exists():
            self._set_status("请先导入或加载一首歌曲，再生成歌词。")
            return

        try:
            transcriber = self._build_lyrics_transcriber(self._lyrics_backend)
            if transcriber is None:
                self._set_status("当前设置为不生成歌词，请先切换歌词方式。")
                return
            if QCoreApplication.instance() is None:
                self._lyrics_path = transcriber.transcribe(
                    LyricsTranscriptionRequest(audio_path=audio_path, output_path=self._lyrics_output_path())
                )
                self._reload_lyrics_after_generation()
                self._set_status(
                    f"歌词已生成：{self._lyrics_path}。{lyrics_backend_status_text(self._lyrics_backend)}"
                )
                return
            self._start_lyrics_generation(transcriber, audio_path, self._lyrics_output_path())
        except Exception:
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))

    @pyqtSlot()
    def generateSmartLyrics(self) -> None:
        if is_module_available("faster_whisper") and self._local_lyrics_model_path() is not None:
            self._lyrics_backend = "faster-whisper"
            self.importOptionsChanged.emit()
        self.generateLyrics()

    @pyqtSlot(int, str)
    def _handle_lyrics_progress(self, progress: int, message: str) -> None:
        self._lyrics_generation_progress = max(0, min(100, int(progress)))
        self._lyrics_generation_status = message
        self.lyricsGenerationChanged.emit()
        self._set_status(message)

    @pyqtSlot(str)
    def _handle_lyrics_finished(self, path: str) -> None:
        self._lyrics_path = Path(path)
        self._reload_lyrics_after_generation()
        self._lyrics_generation_progress = 100
        self._lyrics_generation_status = "歌词生成完成"
        self._set_lyrics_generation_busy(False)
        self._set_status(
            f"歌词已生成：{self._lyrics_path}。{lyrics_backend_status_text(self._lyrics_backend)}"
        )

    def _reload_lyrics_after_generation(self) -> None:
        timeline = load_lyrics_timeline(self._lyrics_path)
        self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
        self._lyric_lines = timeline.texts()
        self.pathsChanged.emit()
        self._emit_lyrics_reloaded()
        self._update_lyrics()

    @pyqtSlot(str)
    def _handle_lyrics_failed(self, message: str) -> None:
        self._lyrics_generation_status = "歌词生成失败"
        self._set_lyrics_generation_busy(False)
        self._set_status(format_user_error(message))

    @pyqtSlot()
    def _cleanup_lyrics_thread(self) -> None:
        if self._lyrics_thread is not None:
            self._lyrics_thread.deleteLater()
        self._lyrics_thread = None
        self._lyrics_worker = None

    def _start_lyrics_generation(self, transcriber, audio_path: Path, output_path: Path) -> None:
        self._lyrics_generation_progress = 5
        self._lyrics_generation_status = f"正在生成歌词：{lyrics_backend_label(self._lyrics_backend)}"
        self._set_lyrics_generation_busy(True)
        self._set_status(self._lyrics_generation_status)

        self._lyrics_thread = QThread(self)
        self._lyrics_worker = LyricsGenerationWorker(transcriber, audio_path, output_path)
        self._lyrics_worker.moveToThread(self._lyrics_thread)
        self._lyrics_thread.started.connect(self._lyrics_worker.run)
        self._lyrics_worker.progress.connect(self._handle_lyrics_progress)
        self._lyrics_worker.finished.connect(self._handle_lyrics_finished)
        self._lyrics_worker.failed.connect(self._handle_lyrics_failed)
        self._lyrics_worker.finished.connect(self._lyrics_thread.quit)
        self._lyrics_worker.failed.connect(self._lyrics_thread.quit)
        self._lyrics_thread.finished.connect(self._lyrics_worker.deleteLater)
        self._lyrics_thread.finished.connect(self._cleanup_lyrics_thread)
        self._lyrics_thread.start()

    def _set_lyrics_generation_busy(self, value: bool) -> None:
        self._lyrics_generation_busy = value
        self.lyricsGenerationChanged.emit()

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
            self._current_source_path = self._project_source_path(selected.root) or selected.vocal_path
            self._vocal_path = session.asset.vocal_path
            self._instrumental_path = session.asset.instrumental_path
            if session.asset.lyrics_path is not None:
                self._lyrics_path = session.asset.lyrics_path
            self._output_path = self._mock_dir / f"{sanitize_filename(session.asset.name)}_export.wav"
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
            self._lyric_lines = timeline.texts()
            self.pathsChanged.emit()
            self._emit_lyrics_reloaded()
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
            self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]), self._lyrics_offset_ms)
            self._lyric_lines = []
            self._current_lyric = ""
            self._next_lyric = ""
            self._current_lyric_index = -1
            self._emit_lyrics_reloaded()
            self.playbackChanged.emit()

    @pyqtSlot()
    def clearSongList(self) -> None:
        self.stop()
        self._songs = []
        self._current_song_key = None
        self._current_source_path = None
        self._playback = None
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]), self._lyrics_offset_ms)
        self._lyric_lines = []
        self._current_lyric = ""
        self._next_lyric = ""
        self._current_lyric_index = -1
        self.songsChanged.emit()
        self._emit_lyrics_reloaded()
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
                    mp3_encoder=self._build_mp3_encoder(self._output_path),
                )
            )
            self._set_status(
                f"已导出：{result.output_path} "
                f"（{result.duration_seconds:.2f} 秒 / {result.sample_rate} Hz）"
            )
        except Exception:
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))

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
            status = "通过" if result.passed else "需检查"
            self._last_alignment_latency_ms = result.latency_seconds * 1000.0
            self._last_alignment_passed = result.passed
            self._set_status(
                f"对齐检测{status}：延迟={self._last_alignment_latency_ms:.2f}ms，"
                f"得分={result.score:.3f}"
            )
            self.playbackChanged.emit()
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    def _update_lyrics(self) -> None:
        position_ms = 0
        if self._playback is not None:
            position_ms = round(self._playback.position_seconds * 1_000)
        state = self._lyrics_sync.state_at(position_ms)
        current_index = -1 if state.current_index is None else state.current_index
        current_lyric = state.current_text or "..."
        next_lyric = "" if state.next_line is None else state.next_line.text
        if (
            current_index == self._current_lyric_index
            and current_lyric == self._current_lyric
            and next_lyric == self._next_lyric
        ):
            return
        self._current_lyric_index = current_index
        self._current_lyric = current_lyric
        self._next_lyric = next_lyric
        self.lyricPositionChanged.emit()
        self.lyricsChanged.emit()

    def _emit_lyrics_reloaded(self) -> None:
        self.lyricLinesChanged.emit()
        self.lyricPositionChanged.emit()
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

    def _build_playback_buffers(self):
        buffers = load_stem_pair(self._vocal_path, self._instrumental_path)
        if self._tone_deaf_ratio <= 0.01:
            return buffers
        return self._tone_deaf_cache.render_buffer(
            buffers,
            ToneDeafConfig(
                drift_ratio=self._tone_deaf_ratio,
                random_seed=7,
            ),
        )

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
        self._current_source_path = project.source_path
        if project.lyrics_path is not None:
            self._lyrics_path = project.lyrics_path
        else:
            self._lyrics_path = project.project_dir / "lyrics.lrc"
            self._lyric_lines = []
            self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]), self._lyrics_offset_ms)
        self._output_path = project.project_dir / f"{project.name}_export.wav"
        self._current_song_key = song_key(project.asset)
        self.pathsChanged.emit()
        self.loadPlayback()
        self._upsert_song(project.asset)
        self._set_status(
            f"导入成功：{project.name}"
            f"（分离={separator_backend_label(separator_backend)}，"
            f"歌词={lyrics_backend_label(lyrics_backend)}）。"
            f"{lyrics_backend_status_text(lyrics_backend)}已加入左侧歌曲库。"
        )
        if self._lyrics_needs_generation():
            self.lyricsGenerationPromptRequested.emit(
                "这首歌没有可用歌词。是否现在使用智能识别生成歌词？"
            )

    def _lyrics_source_audio_path(self) -> Path | None:
        if self._current_source_path is not None and self._current_source_path.exists():
            return self._current_source_path
        if self._vocal_path.exists():
            return self._vocal_path
        if self._instrumental_path.exists():
            return self._instrumental_path
        return None

    def _lyrics_output_path(self) -> Path:
        if self._current_source_path is not None:
            return self._current_source_path.parent / "lyrics.lrc"
        if self._lyrics_path:
            return self._lyrics_path.with_suffix(".lrc")
        return self._mock_dir / "lyrics.lrc"

    def _lyrics_needs_generation(self) -> bool:
        if not self._lyrics_path or not self._lyrics_path.exists():
            return True
        try:
            text = self._lyrics_path.read_text(encoding="utf-8")
        except OSError:
            return True
        placeholders = (
            "未找到歌词文件",
            "请导入 .lrc/.srt",
            "使用智能识别歌词",
            "纯音乐或未识别到歌词",
        )
        return any(placeholder in text for placeholder in placeholders)

    def _project_source_path(self, project_dir: Path) -> Path | None:
        manifest_path = project_dir / "project.json"
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = manifest.get("project_source") or manifest.get("original_source")
        if not value:
            return None
        return Path(value)

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
                raise RuntimeError("智能歌词识别组件未打包，无法生成歌词。")
            model_size = str(self._local_lyrics_model_path() or "small")
            return FasterWhisperLyricsTranscriber(
                FasterWhisperConfig(model_size=model_size, device="cpu", compute_type="int8")
            )
        if backend == "none":
            return None
        return PreviewLyricsTranscriber()

    def _local_lyrics_model_path(self) -> Path | None:
        candidates = [
            self._root / "plugins" / "models" / "faster-whisper" / "small",
            self._root / "plugins" / "models" / "faster-whisper" / "base",
            Path(getattr(sys, "_MEIPASS", self._root)) / "plugins" / "models" / "faster-whisper" / "small",
            Path(getattr(sys, "_MEIPASS", self._root)) / "plugins" / "models" / "faster-whisper" / "base",
        ]
        for candidate in candidates:
            if (candidate / "model.bin").exists() and (candidate / "config.json").exists():
                return candidate
        return None

    def _build_audio_standardizer(self, source_path: Path) -> FfmpegAudioStandardizer | None:
        if source_path.suffix.lower() == ".wav":
            return None
        try:
            ffmpeg = resolve_audio_tool("ffmpeg", self._root)
        except FileNotFoundError:
            return None
        return FfmpegAudioStandardizer(FfmpegConfig(executable=ffmpeg))

    def _build_mp3_encoder(self, output_path: Path) -> FfmpegMp3Encoder | None:
        if output_path.suffix.lower() != ".mp3":
            return None
        ffmpeg = resolve_audio_tool("ffmpeg", self._root)
        return FfmpegMp3Encoder(FfmpegMp3Config(executable=ffmpeg))

    def _set_status(self, value: str) -> None:
        self._status = value
        self.statusChanged.emit()


def format_seconds(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def format_offset_ms(offset_ms: int) -> str:
    seconds = abs(offset_ms) / 1000.0
    if seconds.is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:.1f}s"


def sanitize_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "song"


def song_key(song: SongAsset) -> tuple[str, str | None]:
    return (str(song.root), None if song.source_path is None else str(song.source_path))


def is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def separator_backend_label(backend: str) -> str:
    labels = {
        "preview": "快速预览",
        "demucs": "Demucs 人声分离",
    }
    return labels.get(backend, backend)


def lyrics_backend_label(backend: str) -> str:
    labels = {
        "preview": "占位提示",
        "faster-whisper": "智能识别歌词",
        "none": "不生成歌词",
    }
    return labels.get(backend, backend)


def path_target_label(target: str) -> str:
    labels = {
        "vocal": "人声文件",
        "instrumental": "伴奏文件",
        "lyrics": "歌词文件",
        "output": "导出位置",
    }
    return labels.get(target, target)


def lyrics_backend_status_text(backend: str) -> str:
    if backend == "faster-whisper":
        return "智能识别已执行；如果歌曲是英文，歌词会尽量保持英文。"
    if backend == "preview":
        return "未找到真实歌词时会显示占位提示。"
    return "未生成歌词，纯音乐或暂无歌词时歌词区为空。"


def format_user_error(message: str) -> str:
    if "faster-whisper" in message or "faster_whisper" in message:
        return "歌词识别失败：当前完整识别组件不可用。请使用包含智能识别的完整安装包，或切换到“占位提示/不生成歌词”。"
    if "智能歌词识别组件" in message:
        return "歌词识别失败：当前完整识别组件不可用。请使用包含智能识别的完整安装包，或切换到“占位提示/不生成歌词”。"
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
