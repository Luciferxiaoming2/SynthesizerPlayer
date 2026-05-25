"""PyQt6/QML application shell for the Audio Forge MVP."""

from pathlib import Path
import gc
import importlib.util
import json
import os
import re
import shutil
import sys
import time
import traceback
import urllib.error
import urllib.request

import soundfile as sf
from PyQt6.QtCore import QCoreApplication, QObject, QThread, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine

from core_engine.ai_singer import (
    LyricRewriteBackendConfig,
    LyricRewriteSingingRequest,
    LyricRewriteSingingWorkflow,
    load_lyric_rewrite_backend_config,
)
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
from core_engine.player.sync_buffer import read_audio, write_audio
from core_engine.player.sync_buffer import load_stem_pair
from core_engine.transcription import (
    FasterWhisperConfig,
    FasterWhisperLyricsTranscriber,
    LyricsTranscriptionRequest,
    PreviewLyricsTranscriber,
    is_instruction_hallucination,
)
from harness.eval_harness.audio_latency_test import evaluate_latency
from harness.cli_harness.generate_mock_audio import build_mock_stems


class ImportSongWorker(QObject):
    progress = pyqtSignal(int, str)
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
            self.progress.emit(10, "正在创建歌曲工程")
            self.progress.emit(
                35,
                "正在分离人声和伴奏，真实分离可能需要几分钟，请不要关闭应用",
            )
            project = import_single_song(self._config)
            self.progress.emit(90, "正在加载分离结果")
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


class ToneDeafRenderWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object, float, int)
    failed = pyqtSignal(str, int)

    def __init__(
        self,
        vocal_path: Path,
        instrumental_path: Path,
        config: ToneDeafConfig | None,
        job_id: int,
    ) -> None:
        super().__init__()
        self._vocal_path = vocal_path
        self._instrumental_path = instrumental_path
        self._config = config
        self._job_id = job_id

    @pyqtSlot()
    def run(self) -> None:
        try:
            ratio = 0.0 if self._config is None else self._config.drift_ratio
            self.progress.emit(10, "正在读取当前人声和伴奏")
            buffers = load_stem_pair(self._vocal_path, self._instrumental_path)
            if self._config is None or ratio <= 0.01:
                self.progress.emit(90, "正在恢复原始音高")
                self.finished.emit(buffers, ratio, self._job_id)
                return
            self.progress.emit(35, "正在渲染跑调人声，播放可以继续")
            rendered = ToneDeafBufferCache().render_buffer(buffers, self._config)
            self.progress.emit(92, "正在替换试听缓冲")
            self.finished.emit(rendered, ratio, self._job_id)
        except Exception:
            self.failed.emit(traceback.format_exc(limit=1).strip(), self._job_id)


class ExportMixWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, config: AudioExportConfig) -> None:
        super().__init__()
        self._config = config

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.progress.emit(15, "正在准备导出音频")
            result = export_processed_mix(self._config)
            self.progress.emit(95, "正在完成导出")
            self.finished.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc(limit=1).strip())


class LyricRewriteWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, str, int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        lyric: str,
        lyric_index: int,
        start_ms: int,
        end_ms: int,
        vocal_path: Path,
        output_path: Path,
        backend_config: LyricRewriteBackendConfig,
        manifest_path: Path,
    ) -> None:
        super().__init__()
        self._lyric = lyric
        self._lyric_index = lyric_index
        self._start_ms = start_ms
        self._end_ms = end_ms
        self._vocal_path = vocal_path
        self._output_path = output_path
        self._backend_config = backend_config
        self._manifest_path = manifest_path

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.progress.emit(10, "正在读取当前人声音轨")
            if not self._vocal_path.exists():
                raise FileNotFoundError(f"current vocal track not found: {self._vocal_path}")
            vocal, sample_rate = read_audio(self._vocal_path)
            start_frame = max(0, round(self._start_ms * sample_rate / 1000))
            end_frame = max(start_frame + 1, round(self._end_ms * sample_rate / 1000))
            end_frame = min(end_frame, vocal.shape[0])
            if start_frame >= vocal.shape[0]:
                raise ValueError("选中的歌词时间超出当前音频长度")

            duration_seconds = max(0.2, (end_frame - start_frame) / sample_rate)
            segment_path = self._output_path.with_name(f"{self._output_path.stem}.segment.wav")
            source_segment_path = self._output_path.with_name(f"{self._output_path.stem}.source.wav")
            source_segment_path.parent.mkdir(parents=True, exist_ok=True)
            write_audio(source_segment_path, vocal[start_frame:end_frame], sample_rate)

            if is_ace_api_ready():
                self.progress.emit(25, "正在提交 ACE-Step 真唱改写任务")
                ace_output_path = self._output_path.with_name(f"{self._output_path.stem}.ace.wav")
                ace_result_path = run_ace_repaint_task(
                    source_audio_path=self._vocal_path,
                    output_path=ace_output_path,
                    lyric=self._lyric,
                    start_ms=self._start_ms,
                    end_ms=self._end_ms,
                    progress=self.progress.emit,
                )
                self.progress.emit(82, "正在把 ACE 真唱结果写入当前歌曲")
                ace_audio, ace_rate = read_audio(ace_result_path)
                if ace_rate != sample_rate:
                    ace_audio = resample_audio(ace_audio, ace_rate, sample_rate)
                if ace_audio.shape[0] >= end_frame:
                    segment = fit_audio_segment(ace_audio[start_frame:end_frame], end_frame - start_frame, vocal.shape[1])
                else:
                    segment = fit_generated_audio_segment(
                        ace_audio,
                        end_frame - start_frame,
                        vocal.shape[1],
                        allow_time_stretch=False,
                    )
                segment = apply_source_energy_envelope(vocal[start_frame:end_frame], segment, sample_rate)
                output = vocal.copy()
                output[start_frame:end_frame] = crossfade_replace(output[start_frame:end_frame], segment, sample_rate)
                self._output_path.parent.mkdir(parents=True, exist_ok=True)
                write_audio(self._output_path, output, sample_rate)
                write_lyric_rewrite_manifest(
                    self._manifest_path,
                    {
                        "lyric": self._lyric,
                        "lyric_index": self._lyric_index,
                        "start_ms": self._start_ms,
                        "end_ms": self._end_ms,
                        "backend": "ace_step_api",
                        "backend_label": "ACE-Step REST 真唱改写",
                        "preview_vocal_path": str(self._output_path),
                        "segment_path": str(ace_result_path),
                        "source_segment_path": str(source_segment_path),
                        "used_voice_conversion": False,
                        "used_content_editor": True,
                        "audio_replaced": True,
                    },
                )
                self.progress.emit(95, "正在准备 ACE 真唱试听")
                self.finished.emit(str(self._output_path), self._lyric, self._lyric_index)
                return

            if not self._backend_config.can_replace_audio:
                self.progress.emit(35, "当前AI改唱运行环境未就绪，仅更新歌词文本")
                self._output_path.parent.mkdir(parents=True, exist_ok=True)
                write_audio(self._output_path, vocal, sample_rate)
                write_lyric_rewrite_manifest(
                    self._manifest_path,
                    {
                        "lyric": self._lyric,
                        "lyric_index": self._lyric_index,
                        "start_ms": self._start_ms,
                        "end_ms": self._end_ms,
                        "backend": self._backend_config.backend,
                        "backend_label": self._backend_config.label,
                        "preview_vocal_path": str(self._output_path),
                        "segment_path": str(segment_path),
                        "source_segment_path": str(source_segment_path),
                        "used_voice_conversion": False,
                        "used_content_editor": False,
                        "audio_replaced": False,
                    },
                )
                self.progress.emit(95, "正在准备试听")
                self.finished.emit(str(self._output_path), self._lyric, self._lyric_index)
                return

            self.progress.emit(35, "正在生成改词唱片段")
            workflow = LyricRewriteSingingWorkflow(
                self._backend_config.build_singer(),
                self._backend_config.build_voice_converter(),
                self._backend_config.build_content_editor(),
            )
            synthesized = workflow.run(
                LyricRewriteSingingRequest(
                    lyric=self._lyric,
                    melody_path=self._vocal_path,
                    output_path=segment_path,
                    sample_rate=sample_rate,
                    duration_seconds=duration_seconds,
                    rvc_model_path=self._backend_config.rvc_model_path,
                    source_vocal_path=source_segment_path,
                    start_ms=self._start_ms,
                    end_ms=self._end_ms,
                )
            )

            self.progress.emit(70, "正在替换选中歌词片段")
            segment, segment_rate = read_audio(synthesized.output_path)
            if segment_rate != sample_rate:
                segment = resample_audio(segment, segment_rate, sample_rate)
            segment = fit_generated_audio_segment(
                segment,
                end_frame - start_frame,
                vocal.shape[1],
                allow_time_stretch=self._backend_config.backend != "local_tts",
            )
            segment = apply_source_energy_envelope(vocal[start_frame:end_frame], segment, sample_rate)
            output = vocal.copy()
            output[start_frame:end_frame] = crossfade_replace(
                output[start_frame:end_frame],
                segment,
                sample_rate,
            )
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            write_audio(self._output_path, output, sample_rate)
            write_lyric_rewrite_manifest(
                self._manifest_path,
                {
                    "lyric": self._lyric,
                    "lyric_index": self._lyric_index,
                    "start_ms": self._start_ms,
                    "end_ms": self._end_ms,
                    "backend": self._backend_config.backend,
                    "backend_label": self._backend_config.label,
                    "preview_vocal_path": str(self._output_path),
                    "segment_path": str(segment_path),
                    "source_segment_path": str(source_segment_path),
                    "used_voice_conversion": synthesized.used_voice_conversion,
                    "used_content_editor": synthesized.used_content_editor,
                    "audio_replaced": True,
                },
            )
            self.progress.emit(95, "正在准备试听")
            self.finished.emit(str(self._output_path), self._lyric, self._lyric_index)
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
    importProgressChanged = pyqtSignal()
    lyricsGenerationPromptRequested = pyqtSignal(str)
    lyricsGenerationChanged = pyqtSignal()
    lyricRewriteChanged = pyqtSignal()
    toneDeafProcessingChanged = pyqtSignal()

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._mock_dir = root / "harness" / "mock_data"
        self._projects_root = root / "save"
        self._projects_root.mkdir(parents=True, exist_ok=True)
        self._songs_root = self._projects_root
        self._migrate_legacy_project_outputs()
        self._vocal_path = self._mock_dir / "vocal.wav"
        self._instrumental_path = self._mock_dir / "instrumental.wav"
        self._output_path = self._mock_dir / "ui_export_mix.wav"
        self._lyrics_path = self._mock_dir / "lyrics.lrc"
        self._current_source_path: Path | None = None
        self._master_plugin_paths: list[Path] = []
        self._status = "Ready"
        self._songs: list[SongAsset] = []
        self._song_duration_label_cache: dict[str, str] = {}
        self._current_song_key: tuple[str, str | None] | None = None
        self._current_song_index = -1
        self._audio_devices: list[AudioOutputDevice] = []
        self._selected_audio_device_index = -1
        self._separator_backend = "demucs"
        self._lyrics_backend = "preview"
        self._import_busy = False
        self._import_progress = 0
        self._import_progress_status = ""
        self._import_thread: QThread | None = None
        self._import_worker: ImportSongWorker | None = None
        self._lyrics_generation_busy = False
        self._lyrics_generation_progress = 0
        self._lyrics_generation_status = ""
        self._lyrics_thread: QThread | None = None
        self._lyrics_worker: LyricsGenerationWorker | None = None
        self._lyric_rewrite_busy = False
        self._lyric_rewrite_progress = 0
        self._lyric_rewrite_status = "双击歌词可生成实验版改词唱预览"
        self._lyric_rewrite_preview_path: Path | None = None
        self._lyric_rewrite_manifest_path: Path | None = None
        self._lyric_rewrite_original_vocal_path: Path | None = None
        self._lyric_rewrite_versions: list[Path] = []
        self._lyric_rewrite_thread: QThread | None = None
        self._lyric_rewrite_worker: LyricRewriteWorker | None = None
        self._ace_service_last_check = 0.0
        self._ace_service_reachable = False
        self._ace_api_last_check = 0.0
        self._ace_api_reachable = False
        self._playback: DualTrackPlaybackEngine | None = None
        self._vocal_gain = 1.0
        self._instrumental_gain = 0.8
        self._audio_output: SoundDeviceOutput | None = None
        self._audio_output_active = False
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]))
        self._lyric_lines: list[str] = []
        self._lyric_time_labels: list[str] = []
        self._current_lyric_index = -1
        self._current_lyric = ""
        self._next_lyric = ""
        self._current_lyric_progress = 0.0
        self._lyrics_offset_ms = 0
        self._tone_deaf_ratio = 0.0
        self._tone_deaf_busy = False
        self._tone_deaf_progress = 0
        self._tone_deaf_status = ""
        self._tone_deaf_thread: QThread | None = None
        self._tone_deaf_worker: ToneDeafRenderWorker | None = None
        self._export_thread: QThread | None = None
        self._export_worker: ExportMixWorker | None = None
        self._export_busy = False
        self._tone_deaf_job_id = 0
        self._tone_deaf_pending_ratio: float | None = None
        self._navigation_busy = False
        self._last_interaction_at: dict[str, float] = {}
        self._last_alignment_latency_ms: float | None = None
        self._last_alignment_passed: bool | None = None
        self._play_mode = "list"
        self._tone_deaf_cache = ToneDeafBufferCache()
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(100)
        self._playback_timer.timeout.connect(self.advancePlayback)
        self._songs = scan_song_library(self._songs_root)
        self._load_first_song_if_needed()

    def _migrate_legacy_project_outputs(self) -> None:
        legacy_projects = self._root / "projects"
        if legacy_projects.exists() and legacy_projects.is_dir():
            for item in sorted(legacy_projects.iterdir()):
                target = unique_child_path(self._projects_root, item.name)
                shutil.move(str(item), str(target))
                if target.is_dir():
                    repair_migrated_project_manifest(target)
            try:
                legacy_projects.rmdir()
            except OSError:
                pass

        legacy_outputs = [
            path
            for path in self._root.iterdir()
            if path.is_file() and not path.suffix and looks_like_wave_file(path)
        ]
        if not legacy_outputs:
            return
        target_dir = self._projects_root / "_legacy_root_outputs"
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in legacy_outputs:
            target = unique_child_path(target_dir, f"{path.name}.wav")
            shutil.move(str(path), str(target))

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

    @pyqtProperty("QStringList", notify=songsChanged)
    def songDurationLabels(self) -> list[str]:
        return [self._song_duration_label(song) for song in self._songs]

    @pyqtProperty(int, notify=songsChanged)
    def currentSongIndex(self) -> int:
        return self._current_song_index

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

    @pyqtProperty(int, notify=importProgressChanged)
    def importProgress(self) -> int:
        return self._import_progress

    @pyqtProperty(str, notify=importProgressChanged)
    def importProgressStatus(self) -> str:
        return self._import_progress_status

    @pyqtProperty(bool, notify=importProgressChanged)
    def importProgressIndeterminate(self) -> bool:
        return self._import_busy and self._separator_backend == "demucs" and self._import_progress < 90

    @pyqtProperty(bool, notify=lyricsGenerationChanged)
    def lyricsGenerationBusy(self) -> bool:
        return self._lyrics_generation_busy

    @pyqtProperty(int, notify=lyricsGenerationChanged)
    def lyricsGenerationProgress(self) -> int:
        return self._lyrics_generation_progress

    @pyqtProperty(str, notify=lyricsGenerationChanged)
    def lyricsGenerationStatus(self) -> str:
        return self._lyrics_generation_status

    @pyqtProperty(bool, notify=lyricRewriteChanged)
    def lyricRewriteBusy(self) -> bool:
        return self._lyric_rewrite_busy

    @pyqtProperty(int, notify=lyricRewriteChanged)
    def lyricRewriteProgress(self) -> int:
        return self._lyric_rewrite_progress

    @pyqtProperty(str, notify=lyricRewriteChanged)
    def lyricRewriteStatus(self) -> str:
        return self._lyric_rewrite_status

    @pyqtProperty(str, notify=lyricRewriteChanged)
    def lyricRewritePreviewPath(self) -> str:
        return "" if self._lyric_rewrite_preview_path is None else str(self._lyric_rewrite_preview_path)

    @pyqtProperty(str, notify=lyricRewriteChanged)
    def lyricRewriteManifestPath(self) -> str:
        return "" if self._lyric_rewrite_manifest_path is None else str(self._lyric_rewrite_manifest_path)

    @pyqtProperty(str, notify=lyricRewriteChanged)
    def lyricRewriteBackendStatus(self) -> str:
        try:
            config = load_lyric_rewrite_backend_config(self._root)
        except Exception as exc:
            return f"改词唱配置有误：{exc}"
        source = "自动检测" if config.config_path is None else config.config_path.name
        ace_status = self._ace_web_status_label()
        return f"改词唱后端：{config.label}（{source}）。{config.readiness_label}。{ace_status}"

    @pyqtProperty(bool, notify=lyricRewriteChanged)
    def aceWebReady(self) -> bool:
        return self._is_ace_web_ready()

    @pyqtProperty(str, notify=lyricRewriteChanged)
    def aceWebStatus(self) -> str:
        return self._ace_web_status_label()

    @pyqtProperty(bool, notify=lyricRewriteChanged)
    def aceApiReady(self) -> bool:
        return self._is_ace_api_ready()

    @pyqtProperty("QStringList", notify=lyricRewriteChanged)
    def lyricRewriteVersionLabels(self) -> list[str]:
        return [lyric_rewrite_version_label(path, index) for index, path in enumerate(self._lyric_rewrite_versions)]

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

    @pyqtProperty(str, notify=playbackChanged)
    def playModeLabel(self) -> str:
        return "单曲循环" if self._play_mode == "loop" else "列表播放"

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

    @pyqtProperty(float, notify=playbackChanged)
    def vocalGain(self) -> float:
        if self._playback is not None:
            return self._playback.controls.vocal_gain
        return self._vocal_gain

    @pyqtProperty(float, notify=playbackChanged)
    def instrumentalGain(self) -> float:
        if self._playback is not None:
            return self._playback.controls.instrumental_gain
        return self._instrumental_gain

    @pyqtProperty(str, notify=lyricPositionChanged)
    def currentLyric(self) -> str:
        return self._current_lyric

    @pyqtProperty(str, notify=lyricPositionChanged)
    def nextLyric(self) -> str:
        return self._next_lyric

    @pyqtProperty("QStringList", notify=lyricLinesChanged)
    def lyricLines(self) -> list[str]:
        return list(self._lyric_lines)

    @pyqtProperty("QStringList", notify=lyricLinesChanged)
    def lyricTimeLabels(self) -> list[str]:
        return list(self._lyric_time_labels)

    @pyqtProperty(int, notify=lyricPositionChanged)
    def currentLyricIndex(self) -> int:
        return self._current_lyric_index

    @pyqtProperty(float, notify=lyricPositionChanged)
    def currentLyricProgress(self) -> float:
        return self._current_lyric_progress

    @pyqtProperty(int, notify=lyricPositionChanged)
    def lyricsOffsetMs(self) -> int:
        return self._lyrics_offset_ms

    @pyqtProperty(str, notify=lyricPositionChanged)
    def lyricsOffsetLabel(self) -> str:
        return format_offset_ms(self._lyrics_offset_ms)

    @pyqtProperty(float, notify=playbackChanged)
    def toneDeafRatio(self) -> float:
        return self._tone_deaf_ratio

    @pyqtProperty(bool, notify=toneDeafProcessingChanged)
    def toneDeafBusy(self) -> bool:
        return self._tone_deaf_busy

    @pyqtProperty(int, notify=toneDeafProcessingChanged)
    def toneDeafProgress(self) -> int:
        return self._tone_deaf_progress

    @pyqtProperty(str, notify=toneDeafProcessingChanged)
    def toneDeafStatus(self) -> str:
        return self._tone_deaf_status

    @pyqtProperty(bool, notify=toneDeafProcessingChanged)
    def toneDeafProgressIndeterminate(self) -> bool:
        return self._tone_deaf_busy and self._tone_deaf_progress < 90

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
        if self._tone_deaf_busy:
            return self._tone_deaf_status or "正在处理跑调效果"
        if self._playback is None:
            return "请先导入或加载歌曲"
        if self._tone_deaf_ratio <= 0.01:
            return "原声稳定"
        if self._tone_deaf_ratio < 0.35:
            return "轻微跑调预览中"
        if self._tone_deaf_ratio < 0.7:
            return "明显跑调已应用"
        return "强跑调已应用，注意音量"

    @pyqtProperty("QVariantList", notify=playbackChanged)
    def f0MonitorLevels(self) -> list[float]:
        if self._playback is None:
            return default_monitor_levels()
        return monitor_levels_from_playback(self._playback)

    @pyqtProperty(str, notify=playbackChanged)
    def f0MonitorBackend(self) -> str:
        return "aubio F0" if is_module_available("aubio") else "音量波动"

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
            self._playback.set_gains(
                vocal_gain=self._vocal_gain,
                instrumental_gain=self._instrumental_gain,
            )
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
            self._set_lyric_timeline_view(timeline)
            self._emit_lyrics_reloaded()
            self._update_lyrics()
            self.playbackChanged.emit()
            tone_text = "，已应用跑调" if self._tone_deaf_ratio > 0.01 else ""
            self._set_status(f"音频已加载{tone_text}，可以点击“播放”试听")
        except Exception:
            self._set_status(traceback.format_exc(limit=1).strip())

    @pyqtSlot()
    def play(self) -> None:
        if self._navigation_busy:
            self._set_status("歌曲正在切换，请稍等")
            return
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
    def cyclePlayMode(self) -> None:
        self._play_mode = "loop" if self._play_mode == "list" else "list"
        self.playbackChanged.emit()
        self._set_status(f"播放模式：{self.playModeLabel}")

    @pyqtSlot()
    def startAudioOutput(self) -> None:
        try:
            if self._navigation_busy:
                self._set_status("歌曲正在切换，请稍等")
                return
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
        if self._navigation_busy:
            return
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
        self._vocal_gain = max(0.0, float(vocal_gain))
        self._instrumental_gain = max(0.0, float(instrumental_gain))
        if self._playback is None:
            self.playbackChanged.emit()
            return
        self._playback.set_gains(
            vocal_gain=self._vocal_gain,
            instrumental_gain=self._instrumental_gain,
        )
        self.playbackChanged.emit()

    @pyqtSlot(float)
    def setToneDeafRatio(self, ratio: float) -> None:
        target_ratio = max(0.0, min(1.0, float(ratio)))
        self._tone_deaf_ratio = target_ratio
        if self._playback is None:
            self._set_status("已设置跑调强度；导入、加载或导出时生效")
            self.playbackChanged.emit()
            return

        if self._tone_deaf_busy:
            self._tone_deaf_pending_ratio = target_ratio
            self._set_tone_deaf_progress(
                self._tone_deaf_progress,
                f"正在处理上一版跑调，稍后应用最新强度：{round(target_ratio * 100)}%",
            )
            self.playbackChanged.emit()
            return

        if QCoreApplication.instance() is not None:
            self._start_tone_deaf_render(target_ratio)
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
            self._set_status("右栏预设已切换为“真实分离”：下一次导入会使用 Demucs 人声分离")
            return
        self.setSeparatorBackend("preview")
        self._set_status("右栏预设已切换为“快速预览”：只用于快速测试，不会真正消除人声")

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
        if not source_path.exists():
            self._set_status("导入失败：没有找到选择的音乐文件，请检查文件是否被移动或删除。")
            return
        self._separator_backend = separator_backend
        self._lyrics_backend = lyrics_backend
        self.importOptionsChanged.emit()
        self._set_import_busy(True)
        self._set_import_progress(
            5,
            f"正在导入歌曲：{separator_backend_label(separator_backend)}",
        )
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
        self._import_worker.progress.connect(self._handle_import_progress)
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
        repair_question_mark_lyrics_from_backup(self._lyrics_path)
        timeline = load_lyrics_timeline(self._lyrics_path)
        self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
        self._set_lyric_timeline_view(timeline)
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

    @pyqtSlot(int, str)
    def generateLyricRewrite(self, lyric_index: int, new_lyric: str) -> None:
        if self._lyric_rewrite_busy:
            self._set_status("改词唱正在生成中，请稍等。")
            return
        if (
            QCoreApplication.instance() is not None
            and self._is_ace_web_ready()
            and not self._is_ace_api_ready(force=True)
        ):
            self._set_status(
                "ACE 网页已运行，但未启用自动调用接口。请停止 ACE 后用 uv run acestep --enable-api 重新启动。"
            )
            self.lyricRewriteChanged.emit()
            return
        text = new_lyric.strip()
        if not text:
            self._set_status("请先输入要改唱的新歌词。")
            return
        if is_question_mark_pollution(text):
            self._set_status("改词唱失败：新歌词看起来是编码错误产生的问号，请重新输入中文或英文。")
            return
        timeline = load_lyrics_timeline(self._lyrics_path)
        lines = timeline.lines
        if lyric_index < 0 or lyric_index >= len(lines):
            self._set_status("请先双击一行歌词，再生成改词唱。")
            return
        rewrite_vocal_path = self._resolve_lyric_rewrite_vocal_path()
        if rewrite_vocal_path is None:
            self._set_status("当前歌曲缺少可用人声音轨。请重新加载左侧歌曲，或重新导入一次歌曲。")
            return

        line = lines[lyric_index]
        start_ms = max(0, line.start_ms)
        if line.end_ms is not None:
            end_ms = line.end_ms
        elif lyric_index + 1 < len(lines):
            end_ms = lines[lyric_index + 1].start_ms
        else:
            end_ms = start_ms + max(1200, min(5000, len(text) * 260))
        if end_ms <= start_ms:
            end_ms = start_ms + max(1200, min(5000, len(text) * 260))

        try:
            backend_config = load_lyric_rewrite_backend_config(self._root)
        except Exception as exc:
            self._set_status(f"改词唱配置有误：{exc}")
            return

        source_vocal_path = self._lyric_rewrite_original_vocal_path or rewrite_vocal_path
        output_path = self._lyric_rewrite_output_path(lyric_index)
        manifest_path = output_path.with_suffix(".json")
        if QCoreApplication.instance() is None:
            worker = LyricRewriteWorker(
                text,
                lyric_index,
                start_ms,
                end_ms,
                source_vocal_path,
                output_path,
                backend_config,
                manifest_path,
            )
            worker.progress.connect(self._handle_lyric_rewrite_progress)
            worker.finished.connect(self._handle_lyric_rewrite_finished)
            worker.failed.connect(self._handle_lyric_rewrite_failed)
            worker.run()
            return

        self._lyric_rewrite_progress = 5
        self._lyric_rewrite_status = "正在生成实验版改词唱预览"
        self._set_lyric_rewrite_busy(True)
        self._set_status(self._lyric_rewrite_status)
        self._lyric_rewrite_thread = QThread(self)
        self._lyric_rewrite_worker = LyricRewriteWorker(
            text,
            lyric_index,
            start_ms,
            end_ms,
            source_vocal_path,
            output_path,
            backend_config,
            manifest_path,
        )
        self._lyric_rewrite_worker.moveToThread(self._lyric_rewrite_thread)
        self._lyric_rewrite_thread.started.connect(self._lyric_rewrite_worker.run)
        self._lyric_rewrite_worker.progress.connect(self._handle_lyric_rewrite_progress)
        self._lyric_rewrite_worker.finished.connect(self._handle_lyric_rewrite_finished)
        self._lyric_rewrite_worker.failed.connect(self._handle_lyric_rewrite_failed)
        self._lyric_rewrite_worker.finished.connect(self._lyric_rewrite_thread.quit)
        self._lyric_rewrite_worker.failed.connect(self._lyric_rewrite_thread.quit)
        self._lyric_rewrite_thread.finished.connect(self._lyric_rewrite_worker.deleteLater)
        self._lyric_rewrite_thread.finished.connect(self._cleanup_lyric_rewrite_thread)
        self._lyric_rewrite_thread.start()

    def _resolve_lyric_rewrite_vocal_path(self) -> Path | None:
        candidates: list[Path] = []
        if self._lyric_rewrite_original_vocal_path is not None:
            candidates.append(self._lyric_rewrite_original_vocal_path)
        candidates.append(self._vocal_path)

        if 0 <= self._current_song_index < len(self._songs):
            song = self._songs[self._current_song_index]
            candidates.append(song.vocal_path)
            if song.source_path is not None:
                candidates.append(song.source_path)
            if song.is_imported_project:
                try:
                    session = load_song_session(song)
                    candidates.append(session.asset.vocal_path)
                    if session.asset.source_path is not None:
                        candidates.append(session.asset.source_path)
                except Exception:
                    pass

        if self._current_source_path is not None:
            candidates.append(self._current_source_path)
        candidates.append(self._instrumental_path)

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                self._vocal_path = candidate
                return candidate
        return None

    @pyqtSlot()
    def reloadOriginalVocal(self) -> None:
        restored_lyrics = self._restore_original_lyrics()
        self._delete_lyric_rewrite_version_files()
        if self._lyric_rewrite_original_vocal_path is not None and self._lyric_rewrite_original_vocal_path.exists():
            self._vocal_path = self._lyric_rewrite_original_vocal_path
            self._set_project_active_vocal(None)
            self._clear_lyric_rewrite_preview_state()
            self.loadPlayback()
            suffix = "，歌词也已恢复" if restored_lyrics else ""
            self._set_status(f"已恢复改词唱前的人声音轨{suffix}")
            return
        if restored_lyrics and not (0 <= self._current_song_index < len(self._songs)):
            self._clear_lyric_rewrite_preview_state()
            self._reload_lyrics_after_generation()
            self._set_status("已恢复原歌词")
            return
        if self._current_song_index >= 0 and self._current_song_index < len(self._songs):
            self._set_project_active_vocal(None)
            self._clear_lyric_rewrite_preview_state()
            self._load_song_at(self._current_song_index, throttle=False)
            self._set_status("已恢复当前歌曲的原始人声音轨")
            return
        self._set_status("当前没有可恢复的歌曲工程。")

    @pyqtSlot(int, str)
    def _handle_lyric_rewrite_progress(self, progress: int, message: str) -> None:
        self._lyric_rewrite_progress = max(0, min(100, int(progress)))
        self._lyric_rewrite_status = message
        self.lyricRewriteChanged.emit()
        self._set_status(message)

    @pyqtSlot(str, str, int)
    def _handle_lyric_rewrite_finished(self, path: str, lyric: str, lyric_index: int) -> None:
        self._lyric_rewrite_preview_path = Path(path)
        self._lyric_rewrite_manifest_path = self._lyric_rewrite_preview_path.with_suffix(".json")
        if self._lyric_rewrite_original_vocal_path is None:
            self._lyric_rewrite_original_vocal_path = self._vocal_path
        self._vocal_path = self._lyric_rewrite_preview_path
        self._set_project_active_vocal(self._lyric_rewrite_preview_path)
        self._refresh_lyric_rewrite_versions()
        self._lyric_rewrite_progress = 100
        self._lyric_rewrite_status = f"歌词修改已生成：{lyric}"
        self._set_lyric_rewrite_busy(False)
        self._apply_lyric_rewrite_text(lyric_index, lyric)
        self.pathsChanged.emit()
        self.loadPlayback()
        try:
            manifest = json.loads(self._lyric_rewrite_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, AttributeError):
            manifest = {}
        if manifest.get("audio_replaced") is False:
            self._set_status("已更新歌词文本。当前AI改唱运行环境未就绪，所以播放仍是原唱人声，不会读出新歌词。")
        else:
            self._set_status("改词唱音频已套用到当前人声，点击播放即可试听。")

    @pyqtSlot(str)
    def _handle_lyric_rewrite_failed(self, message: str) -> None:
        self._lyric_rewrite_status = "改词唱生成失败"
        self._set_lyric_rewrite_busy(False)
        self._set_status(format_lyric_rewrite_error(message))

    @pyqtSlot()
    def _cleanup_lyric_rewrite_thread(self) -> None:
        if self._lyric_rewrite_thread is not None:
            self._lyric_rewrite_thread.deleteLater()
        self._lyric_rewrite_thread = None
        self._lyric_rewrite_worker = None

    def _set_lyric_rewrite_busy(self, value: bool) -> None:
        self._lyric_rewrite_busy = value
        self.lyricRewriteChanged.emit()

    def _clear_lyric_rewrite_preview_state(self) -> None:
        self._lyric_rewrite_preview_path = None
        self._lyric_rewrite_manifest_path = None
        self._lyric_rewrite_original_vocal_path = None
        self._lyric_rewrite_versions = []
        self._lyric_rewrite_progress = 0
        self._lyric_rewrite_status = "双击歌词可生成实验版改词唱预览"
        self.lyricRewriteChanged.emit()

    @pyqtSlot(int)
    def deleteLyricRewriteVersion(self, index: int) -> None:
        if index < 0 or index >= len(self._lyric_rewrite_versions):
            self._set_status("请先选择要删除的试听版本。")
            return
        path = self._lyric_rewrite_versions[index]
        active_deleted = self._vocal_path.resolve() == path.resolve()
        for candidate in [
            path,
            path.with_suffix(".json"),
            path.with_name(f"{path.stem}.segment.wav"),
            path.with_name(f"{path.stem}.source.wav"),
        ]:
            try:
                if candidate.exists():
                    candidate.unlink()
            except OSError:
                pass
        if active_deleted:
            self.reloadOriginalVocal()
            return
        self._refresh_lyric_rewrite_versions()
        self._set_status("已删除选中的改词唱试听版本。")

    @pyqtSlot()
    def clearLyricRewriteVersions(self) -> None:
        self._delete_lyric_rewrite_version_files()
        self._lyric_rewrite_versions = []
        self.lyricRewriteChanged.emit()
        self._set_status("已清空改词唱试听版本。")

    def _delete_lyric_rewrite_version_files(self) -> None:
        output_dir = self._lyric_rewrite_output_dir()
        if not output_dir.exists():
            return
        for candidate in output_dir.glob("*"):
            if candidate.is_file():
                try:
                    candidate.unlink()
                except OSError:
                    pass
    @pyqtSlot(int)
    def applyLyricRewriteVersion(self, index: int) -> None:
        if index < 0 or index >= len(self._lyric_rewrite_versions):
            self._set_status("请先选择一个改词唱试听版本。")
            return
        path = self._lyric_rewrite_versions[index]
        if not path.exists():
            self._refresh_lyric_rewrite_versions()
            self._set_status("该改词唱版本文件不存在，已刷新列表。")
            return
        if self._lyric_rewrite_original_vocal_path is None and self._vocal_path.exists():
            self._lyric_rewrite_original_vocal_path = self._vocal_path
        self._lyric_rewrite_preview_path = path
        self._lyric_rewrite_manifest_path = path.with_suffix(".json")
        self._vocal_path = path
        self._set_project_active_vocal(path)
        self._apply_lyric_rewrite_manifest_text(self._lyric_rewrite_manifest_path)
        self.pathsChanged.emit()
        self.lyricRewriteChanged.emit()
        self.loadPlayback()
        self._set_status(f"已切换到改词唱试听版本：{path.name}")

    def _lyric_rewrite_output_path(self, lyric_index: int) -> Path:
        output_dir = self._lyric_rewrite_output_dir()
        song_name = sanitize_filename(self._current_song_name())
        base = output_dir / f"{song_name}_rewrite_{lyric_index + 1:03d}.wav"
        if not base.exists():
            return base
        for version in range(2, 1000):
            candidate = output_dir / f"{song_name}_rewrite_{lyric_index + 1:03d}_v{version:02d}.wav"
            if not candidate.exists():
                return candidate
        return output_dir / f"{song_name}_rewrite_{lyric_index + 1:03d}_{len(list(output_dir.glob('*.wav'))) + 1}.wav"

    def _lyric_rewrite_output_dir(self) -> Path:
        base_dir = self._lyrics_path.parent if self._lyrics_path else self._projects_root
        return base_dir / "ai_singer"

    def _current_song_name(self) -> str:
        if 0 <= self._current_song_index < len(self._songs):
            return self._songs[self._current_song_index].name
        if self._current_source_path is not None:
            return self._current_source_path.stem
        return "song"

    def _apply_lyric_rewrite_text(self, lyric_index: int, lyric: str) -> None:
        if not self._lyrics_path.exists():
            return
        if is_question_mark_pollution(lyric):
            self._set_status("改词唱音频已生成，但新歌词疑似编码错误，已拒绝写入歌词文件。")
            return
        try:
            backup_lyrics_file_once(self._lyrics_path)
            replace_timed_lyric_text(self._lyrics_path, lyric_index, lyric)
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
            self._set_lyric_timeline_view(timeline)
            self._emit_lyrics_reloaded()
            self._update_lyrics()
        except Exception as exc:
            self._set_status(f"改词唱已生成，但歌词文件更新失败：{exc}")

    def _apply_lyric_rewrite_manifest_text(self, manifest_path: Path | None) -> None:
        if manifest_path is None or not manifest_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        lyric = str(manifest.get("lyric", "")).strip()
        lyric_index = manifest.get("lyric_index")
        if not lyric or not isinstance(lyric_index, int):
            return
        self._apply_lyric_rewrite_text(lyric_index, lyric)

    def _refresh_lyric_rewrite_versions(self) -> None:
        output_dir = self._lyric_rewrite_output_dir()
        if not output_dir.exists():
            self._lyric_rewrite_versions = []
            self.lyricRewriteChanged.emit()
            return
        manifests = sorted(output_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        versions: list[Path] = []
        for manifest_path in manifests:
            audio_path = lyric_rewrite_audio_path_from_manifest(manifest_path)
            if audio_path is not None and audio_path.exists():
                versions.append(audio_path)
        self._lyric_rewrite_versions = versions
        self.lyricRewriteChanged.emit()

    def _restore_original_lyrics(self) -> bool:
        if not self._lyrics_path.exists():
            return False
        backup_path = original_lyrics_backup_path(self._lyrics_path)
        if not backup_path.exists():
            return False
        shutil.copyfile(backup_path, self._lyrics_path)
        timeline = load_lyrics_timeline(self._lyrics_path)
        self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
        self._set_lyric_timeline_view(timeline)
        self._emit_lyrics_reloaded()
        self._update_lyrics()
        return True

    def _set_project_active_vocal(self, vocal_path: Path | None) -> None:
        project_dir = self._project_dir_for_current_assets()
        if project_dir is None:
            return
        update_project_active_vocal(project_dir / "project.json", vocal_path)

    def _project_dir_for_current_assets(self) -> Path | None:
        if self._lyrics_path and self._lyrics_path.parent.exists():
            manifest_path = self._lyrics_path.parent / "project.json"
            if manifest_path.exists():
                return self._lyrics_path.parent
        if self._vocal_path and self._vocal_path.parent.exists():
            parent = self._vocal_path.parent
            if (parent / "project.json").exists():
                return parent
            if parent.name == "stems" and (parent.parent / "project.json").exists():
                return parent.parent
        return None

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
            self._load_first_song_if_needed()
            self._set_status(f"已扫描到 {len(self._songs)} 首歌曲：{self._songs_root}")
        except Exception:
            self._songs = []
            self.songsChanged.emit()
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))

    @pyqtSlot()
    def openSongsRootFolder(self) -> None:
        self._songs_root.mkdir(parents=True, exist_ok=True)
        self._open_folder(self._songs_root, "歌曲库文件夹")

    @pyqtSlot()
    def openCurrentSongFolder(self) -> None:
        if 0 <= self._current_song_index < len(self._songs):
            self._open_folder(self._songs[self._current_song_index].root, "当前歌曲文件夹")
            return
        self.openSongsRootFolder()

    @pyqtSlot()
    def openLyricRewriteFolder(self) -> None:
        if self._lyric_rewrite_preview_path is not None:
            self._open_folder(self._lyric_rewrite_preview_path.parent, "改词唱版本文件夹")
            return
        base_dir = self._lyrics_path.parent if self._lyrics_path else self._songs_root
        self._open_folder(base_dir / "ai_singer", "改词唱版本文件夹")

    @pyqtSlot()
    def openAceWorkbench(self) -> None:
        url = QUrl("http://127.0.0.1:7860")
        opened = QDesktopServices.openUrl(url)
        if opened:
            if self._is_ace_web_ready(force=True):
                self._set_status("已打开 ACE-Step 工作台。请在网页中选择 Repaint/改写片段模式进行真实 AI 生成测试。")
            else:
                self._set_status("已尝试打开 ACE-Step 工作台；如果浏览器打不开，请先启动 ACE 模型到 7860 端口。")
        else:
            self._set_status("无法自动打开 ACE-Step 工作台，请手动访问：http://127.0.0.1:7860")

    @pyqtSlot()
    def refreshAceWorkbenchStatus(self) -> None:
        ready = self._is_ace_web_ready(force=True)
        api_ready = self._is_ace_api_ready(force=True)
        self.lyricRewriteChanged.emit()
        if api_ready:
            self._set_status("ACE-Step 自动改唱接口已就绪，右侧按钮会调用 ACE 真唱改写。")
        elif ready:
            self._set_status("ACE-Step 工作台已运行，但自动接口未开启。请用 uv run acestep --enable-api 重启。")
        else:
            self._set_status("未检测到 ACE-Step 工作台。请先在 ACE-Step-1.5 目录执行 uv run acestep。")

    def _open_folder(self, folder: Path, label: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if opened:
            self._set_status(f"已打开{label}：{folder}")
        else:
            self._set_status(f"无法自动打开{label}，请手动进入：{folder}")

    def _is_ace_web_ready(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._ace_service_last_check < 5.0:
            return self._ace_service_reachable
        self._ace_service_last_check = now
        try:
            with urllib.request.urlopen("http://127.0.0.1:7860/config", timeout=0.35) as response:
                self._ace_service_reachable = 200 <= response.status < 500
        except (OSError, urllib.error.URLError, TimeoutError):
            self._ace_service_reachable = False
        return self._ace_service_reachable

    def _is_ace_api_ready(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._ace_api_last_check < 5.0:
            return self._ace_api_reachable
        self._ace_api_last_check = now
        self._ace_api_reachable = is_ace_api_ready()
        return self._ace_api_reachable

    def _ace_web_status_label(self) -> str:
        if self._is_ace_api_ready():
            return "ACE-Step 自动改唱接口已就绪，点击生成会调用 ACE 真唱改写"
        if self._is_ace_web_ready():
            return "ACE-Step Web 工作台已运行，但未启用自动接口；请用 uv run acestep --enable-api 重启"
        return "未检测到 ACE-Step Web 工作台；如需真唱生成，请先启动 uv run acestep"

    def _load_first_song_if_needed(self) -> None:
        if self._playback is not None or self._current_song_index >= 0:
            return
        if not self._songs:
            return
        first_song = self._songs[0]
        if first_song.source_path is not None:
            return
        self._load_song_at(0, throttle=False)

    @pyqtSlot(int)
    def loadSongAt(self, index: int) -> None:
        self._load_song_at(index, throttle=True)

    def _load_song_at(self, index: int, throttle: bool) -> None:
        if throttle and not self._accept_interaction("load_song", 450):
            return
        if self._navigation_busy or self._import_busy or self._tone_deaf_busy:
            self._set_status("正在处理上一项操作，请稍等")
            return
        self._navigation_busy = True
        try:
            if index < 0 or index >= len(self._songs):
                self._set_status("请先在左侧选择歌曲")
                return
            self._release_heavy_audio_state()
            selected = self._songs[index]
            if selected.source_path is not None:
                self._current_song_index = index
                self.songsChanged.emit()
                self.importSongWithBackendsAsync(
                    QUrl.fromLocalFile(str(selected.source_path)).toString(),
                    self._separator_backend,
                    self._lyrics_backend,
                )
                return
            session = load_song_session(selected)
            self._current_song_key = song_key(selected)
            self._current_song_index = index
            self._current_source_path = self._project_source_path(selected.root) or selected.vocal_path
            self._vocal_path = session.asset.vocal_path
            self._instrumental_path = session.asset.instrumental_path
            if session.asset.lyrics_path is not None:
                self._lyrics_path = session.asset.lyrics_path
            self._output_path = self._mock_dir / f"{sanitize_filename(session.asset.name)}_export.wav"
            self._refresh_lyric_rewrite_versions()
            repair_question_mark_lyrics_from_backup(self._lyrics_path)
            timeline = load_lyrics_timeline(self._lyrics_path)
            self._lyrics_sync = LyricPlaybackSynchronizer(timeline, self._lyrics_offset_ms)
            self._set_lyric_timeline_view(timeline)
            self.pathsChanged.emit()
            self._emit_lyrics_reloaded()
            self.songsChanged.emit()
            self._set_status(f"已加载歌曲：{session.asset.name}")
            self.loadPlayback()
        except Exception:
            self._set_status(format_user_error(traceback.format_exc(limit=1).strip()))
        finally:
            self._navigation_busy = False

    @pyqtSlot(int)
    def deleteSongAt(self, index: int) -> None:
        if index < 0 or index >= len(self._songs):
            self._set_status("请先在左侧选择要删除的歌曲")
            return
        removed = self._songs.pop(index)
        deleted_paths = self._delete_song_storage(removed)
        removed_current = self._current_song_key == song_key(removed)
        if self._current_song_index == index:
            removed_current = True
        elif self._current_song_index > index:
            self._current_song_index -= 1
        self.songsChanged.emit()
        delete_text = "并删除磁盘文件" if deleted_paths else "，但未找到可删除的磁盘文件"
        self._set_status(f"已从列表移除：{removed.name}{delete_text}")
        self._release_heavy_audio_state()
        if not removed_current:
            return

        self.stop()
        self._clear_lyric_rewrite_preview_state()
        if self._songs:
            next_index = min(index, len(self._songs) - 1)
            self._load_song_at(next_index, throttle=False)
        else:
            self._clear_current_song_state()

    @pyqtSlot()
    def clearSongList(self) -> None:
        self.stop()
        deleted_count = 0
        for song in list(self._songs):
            if self._delete_song_storage(song):
                deleted_count += 1
        self._songs = []
        self._clear_current_song_state()
        self._release_heavy_audio_state()
        self.songsChanged.emit()
        self._set_status(f"已清空左侧歌曲列表，并删除 {deleted_count} 个磁盘项目")

    def _clear_current_song_state(self) -> None:
        self._release_heavy_audio_state()
        self._current_song_key = None
        self._current_song_index = -1
        self._current_source_path = None
        self._playback = None
        self._clear_lyric_rewrite_preview_state()
        self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]), self._lyrics_offset_ms)
        self._set_lyric_timeline_view(LyricTimeline([]))
        self._current_lyric = ""
        self._next_lyric = ""
        self._current_lyric_index = -1
        self._current_lyric_progress = 0.0
        self._emit_lyrics_reloaded()
        self.playbackChanged.emit()

    def _release_heavy_audio_state(self) -> None:
        self._tone_deaf_cache.clear()
        gc.collect()

    def _delete_song_storage(self, song: SongAsset) -> list[Path]:
        targets: list[Path] = []
        if song.is_imported_project:
            targets.append(song.root)
        elif song.source_path is not None:
            targets.append(song.source_path)
            for suffix in (".lrc", ".srt"):
                targets.append(song.source_path.with_suffix(suffix))

        deleted: list[Path] = []
        for target in unique_paths(targets):
            if not target.exists() or not self._is_safe_song_delete_target(target):
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            deleted.append(target)
        return deleted

    def _is_safe_song_delete_target(self, target: Path) -> bool:
        try:
            root = self._songs_root.resolve()
            resolved = target.resolve()
            return resolved == root or resolved.is_relative_to(root)
        except (OSError, RuntimeError):
            return False

    @pyqtSlot()
    def advancePlayback(self) -> None:
        if self._playback is None:
            self._playback_timer.stop()
            return
        if not self._audio_output_active:
            self._playback.render_block(max(1, round(self._playback.buffers.sample_rate * 0.1)))
        if not self._playback.is_playing:
            snapshot = self._playback.snapshot()
            if snapshot.is_finished:
                self._handle_playback_finished(was_audio_active=self._audio_output_active)
            else:
                self._playback_timer.stop()
                self._stop_audio_output(reset_engine=False)
        self._update_lyrics()
        self.playbackChanged.emit()

    @pyqtSlot(float, float)
    def exportMix(self, tone_deaf_ratio: float, master_gain_db: float) -> None:
        if self._export_busy:
            self._set_status("正在导出音频，请稍等。")
            return
        config = AudioExportConfig(
            vocal_path=self._vocal_path,
            instrumental_path=self._instrumental_path,
            output_path=self._output_path,
            tone_deaf_ratio=tone_deaf_ratio,
            master_gain_db=master_gain_db,
            master_plugins=list(self._master_plugin_paths),
            mp3_encoder=self._build_mp3_encoder(self._output_path),
        )
        if QCoreApplication.instance() is None:
            try:
                result = export_processed_mix(config)
                self._handle_export_finished(result)
            except Exception:
                self._handle_export_failed(traceback.format_exc(limit=1).strip())
            return

        self._export_busy = True
        self._set_status("正在后台导出音频，界面可以继续操作")
        self._export_thread = QThread(self)
        self._export_worker = ExportMixWorker(config)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(self._handle_export_progress)
        self._export_worker.finished.connect(self._handle_export_finished)
        self._export_worker.failed.connect(self._handle_export_failed)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._cleanup_export_thread)
        self._export_thread.start()

    @pyqtSlot(int, str)
    def _handle_export_progress(self, _progress: int, message: str) -> None:
        self._set_status(message)

    @pyqtSlot(object)
    def _handle_export_finished(self, result) -> None:
        self._export_busy = False
        self._set_status(
            f"已导出：{result.output_path} "
            f"（{result.duration_seconds:.2f} 秒 / {result.sample_rate} Hz）"
        )

    @pyqtSlot(str)
    def _handle_export_failed(self, message: str) -> None:
        self._export_busy = False
        self._set_status(format_user_error(message))

    @pyqtSlot()
    def _cleanup_export_thread(self) -> None:
        if self._export_thread is not None:
            self._export_thread.deleteLater()
        self._export_thread = None
        self._export_worker = None

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
        current_progress = round(max(0.0, min(1.0, state.line_progress)), 2)
        if (
            current_index == self._current_lyric_index
            and current_lyric == self._current_lyric
            and next_lyric == self._next_lyric
            and current_progress == self._current_lyric_progress
        ):
            return
        self._current_lyric_index = current_index
        self._current_lyric = current_lyric
        self._next_lyric = next_lyric
        self._current_lyric_progress = current_progress
        self.lyricPositionChanged.emit()
        self.lyricsChanged.emit()

    def _emit_lyrics_reloaded(self) -> None:
        self.lyricLinesChanged.emit()
        self.lyricPositionChanged.emit()
        self.lyricsChanged.emit()

    def _set_lyric_timeline_view(self, timeline: LyricTimeline) -> None:
        lines = timeline.lines
        self._lyric_lines = [line.text for line in lines]
        self._lyric_time_labels = [format_timestamp_ms(line.start_ms) for line in lines]

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

    def _accept_interaction(self, key: str, cooldown_ms: int) -> bool:
        now = time.monotonic()
        previous = self._last_interaction_at.get(key, 0.0)
        if (now - previous) * 1000.0 < cooldown_ms:
            return False
        self._last_interaction_at[key] = now
        return True

    def _start_tone_deaf_render(self, ratio: float) -> None:
        self._tone_deaf_job_id += 1
        job_id = self._tone_deaf_job_id
        self._tone_deaf_pending_ratio = None
        self._set_tone_deaf_busy(True)
        self._set_tone_deaf_progress(5, f"正在准备跑调效果：{round(ratio * 100)}%")
        self._set_status(self._tone_deaf_status)

        self._tone_deaf_thread = QThread(self)
        self._tone_deaf_worker = ToneDeafRenderWorker(
            self._vocal_path,
            self._instrumental_path,
            self._tone_deaf_config(ratio),
            job_id,
        )
        self._tone_deaf_worker.moveToThread(self._tone_deaf_thread)
        self._tone_deaf_thread.started.connect(self._tone_deaf_worker.run)
        self._tone_deaf_worker.progress.connect(self._handle_tone_deaf_progress)
        self._tone_deaf_worker.finished.connect(self._handle_tone_deaf_finished)
        self._tone_deaf_worker.failed.connect(self._handle_tone_deaf_failed)
        self._tone_deaf_worker.finished.connect(self._tone_deaf_thread.quit)
        self._tone_deaf_worker.failed.connect(self._tone_deaf_thread.quit)
        self._tone_deaf_thread.finished.connect(self._tone_deaf_worker.deleteLater)
        self._tone_deaf_thread.finished.connect(self._cleanup_tone_deaf_thread)
        self._tone_deaf_thread.start()

    @pyqtSlot(int, str)
    def _handle_tone_deaf_progress(self, progress: int, message: str) -> None:
        self._set_tone_deaf_progress(progress, message)
        self._set_status(message)

    @pyqtSlot(object, float, int)
    def _handle_tone_deaf_finished(self, buffers, ratio: float, job_id: int) -> None:
        if job_id != self._tone_deaf_job_id:
            return
        if self._playback is not None:
            self._playback.replace_buffers(buffers, keep_position=True)
        self._tone_deaf_ratio = max(0.0, min(1.0, float(ratio)))
        self._set_tone_deaf_progress(100, f"跑调效果已应用：{round(self._tone_deaf_ratio * 100)}%")
        self._set_tone_deaf_busy(False)
        self.playbackChanged.emit()
        if self._playback is not None and self._playback.is_playing:
            self._set_status(f"已实时应用跑调程度：{round(self._tone_deaf_ratio * 100)}%，播放会继续")
        else:
            self._set_status(f"已应用跑调程度：{round(self._tone_deaf_ratio * 100)}%")

        pending = self._tone_deaf_pending_ratio
        self._tone_deaf_pending_ratio = None
        if pending is not None and abs(pending - self._tone_deaf_ratio) > 0.005:
            QTimer.singleShot(0, lambda value=pending: self.setToneDeafRatio(value))

    @pyqtSlot(str, int)
    def _handle_tone_deaf_failed(self, message: str, job_id: int) -> None:
        if job_id != self._tone_deaf_job_id:
            return
        self._set_tone_deaf_progress(0, "跑调处理失败")
        self._set_tone_deaf_busy(False)
        self._set_status(f"跑调处理失败：{format_user_error(message)}")

    @pyqtSlot()
    def _cleanup_tone_deaf_thread(self) -> None:
        if self._tone_deaf_thread is not None:
            self._tone_deaf_thread.deleteLater()
        self._tone_deaf_thread = None
        self._tone_deaf_worker = None

    def _set_tone_deaf_busy(self, value: bool) -> None:
        self._tone_deaf_busy = value
        self.toneDeafProcessingChanged.emit()
        self.playbackChanged.emit()

    def _set_tone_deaf_progress(self, progress: int, message: str) -> None:
        self._tone_deaf_progress = max(0, min(100, int(progress)))
        self._tone_deaf_status = message
        self.toneDeafProcessingChanged.emit()

    def _tone_deaf_config(self, ratio: float | None = None) -> ToneDeafConfig | None:
        target_ratio = self._tone_deaf_ratio if ratio is None else max(0.0, min(1.0, float(ratio)))
        if target_ratio <= 0.01:
            return None
        rubberband_executable = None
        try:
            rubberband_executable = resolve_audio_tool("rubberband", self._root)
        except FileNotFoundError:
            rubberband_executable = None
        return ToneDeafConfig(
            drift_ratio=target_ratio,
            random_seed=7,
            rubberband_executable=rubberband_executable,
            temporary_dir=self._root / "save" / ".tmp",
        )

    def _build_playback_buffers(self):
        buffers = load_stem_pair(self._vocal_path, self._instrumental_path)
        config = self._tone_deaf_config()
        if config is None:
            return buffers
        return self._tone_deaf_cache.render_buffer(buffers, config)

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
            self._lyrics_sync = LyricPlaybackSynchronizer(LyricTimeline([]), self._lyrics_offset_ms)
            self._set_lyric_timeline_view(LyricTimeline([]))
        self._output_path = project.project_dir / f"{project.name}_export.wav"
        self._current_song_key = song_key(project.asset)
        self._current_song_index = 0
        self.pathsChanged.emit()
        self.loadPlayback()
        self._refresh_songs_after_import(project.asset)
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

    def _handle_playback_finished(self, was_audio_active: bool) -> None:
        self._stop_audio_output(reset_engine=False)
        if self._play_mode == "loop" and self._playback is not None:
            self._playback.seek_seconds(0)
            if was_audio_active:
                self.startAudioOutput()
            else:
                self.play()
            self._set_status("单曲循环：已从头播放")
            return

        if self._play_mode == "list" and self._songs:
            next_index = self._next_song_index()
            self._load_song_at(next_index, throttle=False)
            if was_audio_active:
                self.startAudioOutput()
            else:
                self.play()
            self._set_status(f"列表播放：已切到 {self._songs[next_index].name}")
            return

        self._playback_timer.stop()

    def _next_song_index(self) -> int:
        if not self._songs:
            return -1
        if self._current_song_index < 0:
            return 0
        return (self._current_song_index + 1) % len(self._songs)

    def _lyrics_source_audio_path(self) -> Path | None:
        if self._current_source_path is not None and self._current_source_path.exists():
            return self._current_source_path
        if self._vocal_path.exists():
            return self._vocal_path
        if self._instrumental_path.exists():
            return self._instrumental_path
        return None

    def _lyrics_output_path(self) -> Path:
        if 0 <= self._current_song_index < len(self._songs):
            song = self._songs[self._current_song_index]
            if song.is_imported_project:
                return song.root / "lyrics.lrc"
            return self._projects_root / sanitize_filename(song.name) / "lyrics.lrc"
        project_dir = self._current_project_dir()
        if project_dir is not None:
            return project_dir / "lyrics.lrc"
        if self._lyrics_path:
            if self._is_path_inside_save(self._lyrics_path):
                return self._lyrics_path.with_suffix(".lrc")
            return self._projects_root / sanitize_filename(self._current_song_name()) / "lyrics.lrc"
        return self._projects_root / sanitize_filename(self._current_song_name()) / "lyrics.lrc"

    def _current_project_dir(self) -> Path | None:
        candidates = [
            self._vocal_path.parent,
            self._instrumental_path.parent,
            None if self._lyrics_path is None else self._lyrics_path.parent,
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            for folder in [candidate, *candidate.parents]:
                if folder.parent == self._projects_root:
                    return folder
        return None

    def _is_path_inside_save(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self._projects_root.resolve())
        except (OSError, RuntimeError):
            return False

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
        self._set_import_progress(100, "导入完成")
        self._set_import_busy(False)
        self._apply_imported_project(project, separator_backend, lyrics_backend)

    @pyqtSlot(int, str)
    def _handle_import_progress(self, progress: int, message: str) -> None:
        self._set_import_progress(progress, message)
        self._set_status(message)

    @pyqtSlot(str)
    def _handle_import_failed(self, message: str) -> None:
        self._set_import_progress(0, "导入失败")
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
        self.importProgressChanged.emit()

    def _set_import_progress(self, progress: int, message: str) -> None:
        self._import_progress = max(0, min(100, int(progress)))
        self._import_progress_status = message
        self.importProgressChanged.emit()

    def _upsert_song(self, asset: SongAsset) -> None:
        self._songs = [
            song for song in self._songs
            if song.root != asset.root and song.source_path != asset.source_path
        ]
        self._songs.insert(0, asset)
        self._current_song_index = 0
        self.songsChanged.emit()

    def _refresh_songs_after_import(self, asset: SongAsset) -> None:
        imported_key = song_key(asset)
        self._songs = scan_song_library(self._songs_root)
        for index, song in enumerate(self._songs):
            if song_key(song) == imported_key or song.root == asset.root:
                self._current_song_index = index
                self._current_song_key = song_key(song)
                self.songsChanged.emit()
                return
        self._upsert_song(asset)

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

    def _song_duration_label(self, song: SongAsset) -> str:
        path = song.source_path or song.vocal_path
        cache_key = str(path)
        cached = self._song_duration_label_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            info = sf.info(str(path))
            duration = info.frames / info.samplerate if info.samplerate > 0 else 0.0
            label = format_seconds(duration)
        except Exception:
            label = "--:--"
        self._song_duration_label_cache[cache_key] = label
        return label


def format_seconds(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def format_offset_ms(offset_ms: int) -> str:
    seconds = abs(offset_ms) / 1000.0
    if seconds.is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:.1f}s"


def format_timestamp_ms(position_ms: int) -> str:
    total_seconds = max(0, position_ms // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def default_monitor_levels(count: int = 22) -> list[float]:
    return [0.22 + ((index * 7) % 11) / 40.0 for index in range(count)]


def monitor_levels_from_playback(playback, count: int = 22) -> list[float]:
    import numpy as np

    buffers = playback.buffers
    frame_count = buffers.frame_count
    if frame_count <= 0:
        return default_monitor_levels(count)

    center = max(0, min(frame_count - 1, playback.position_frames))
    window_frames = max(count, round(buffers.sample_rate * 0.55))
    start = max(0, center - window_frames // 3)
    end = min(frame_count, start + window_frames)
    start = max(0, end - window_frames)
    vocal = buffers.vocal[start:end]
    if vocal.size == 0:
        return default_monitor_levels(count)

    mono_signal = np.mean(vocal, axis=1).astype(np.float32, copy=False)
    pitch_levels = aubio_pitch_levels(mono_signal, buffers.sample_rate, count)
    if pitch_levels is not None:
        return pitch_levels

    mono = np.abs(mono_signal)
    chunks = np.array_split(mono, count)
    rms = np.array([float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0 for chunk in chunks])
    peak = float(np.max(rms))
    if peak <= 1e-6:
        return [0.12 for _ in range(count)]
    normalized = np.clip(rms / peak, 0.08, 1.0)
    return [float(value) for value in normalized]


def aubio_pitch_levels(audio, sample_rate: int, count: int) -> list[float] | None:
    try:
        import aubio
        import numpy as np
    except Exception:
        return None

    if audio.size == 0:
        return None

    hop_size = 1024
    buffer_size = 2048
    try:
        detector = aubio.pitch("yinfft", buffer_size, hop_size, sample_rate)
        detector.set_unit("Hz")
        detector.set_silence(-48)
    except Exception:
        return None

    chunks = np.array_split(audio, count)
    pitches: list[float] = []
    for chunk in chunks:
        if chunk.size == 0:
            pitches.append(0.0)
            continue
        if chunk.size < hop_size:
            frame = np.pad(chunk, (0, hop_size - chunk.size))
        else:
            frame = chunk[:hop_size]
        try:
            pitch = float(detector(frame.astype(np.float32))[0])
        except Exception:
            return None
        pitches.append(pitch if 45.0 <= pitch <= 1200.0 else 0.0)

    valid = [pitch for pitch in pitches if pitch > 0.0]
    if len(valid) < 2:
        return None

    min_hz = 70.0
    max_hz = 700.0
    levels = []
    for pitch in pitches:
        if pitch <= 0.0:
            levels.append(0.08)
            continue
        normalized = (np.log2(min(max(pitch, min_hz), max_hz)) - np.log2(min_hz)) / (
            np.log2(max_hz) - np.log2(min_hz)
        )
        levels.append(float(np.clip(0.12 + normalized * 0.88, 0.08, 1.0)))
    return levels


def fit_audio_segment(audio, frame_count: int, channel_count: int):
    if audio.shape[1] != channel_count:
        if audio.shape[1] == 1:
            audio = audio.repeat(channel_count, axis=1)
        elif channel_count == 1:
            audio = audio.mean(axis=1, keepdims=True)
        else:
            audio = audio[:, :channel_count]
    if audio.shape[0] > frame_count:
        return audio[:frame_count].copy()
    if audio.shape[0] == frame_count:
        return audio.copy()
    import numpy as np

    padding = np.zeros((frame_count - audio.shape[0], channel_count), dtype=audio.dtype)
    return np.concatenate([audio, padding], axis=0)


def fit_generated_audio_segment(
    audio,
    frame_count: int,
    channel_count: int,
    *,
    allow_time_stretch: bool = True,
):
    import numpy as np

    if audio.shape[1] != channel_count:
        if audio.shape[1] == 1:
            audio = audio.repeat(channel_count, axis=1)
        elif channel_count == 1:
            audio = audio.mean(axis=1, keepdims=True)
        else:
            audio = audio[:, :channel_count]
    if audio.shape[0] <= 1 or frame_count <= 1:
        return fit_audio_segment(audio, frame_count, channel_count)
    if abs(audio.shape[0] - frame_count) <= max(256, frame_count // 20):
        return fit_audio_segment(audio, frame_count, channel_count)
    if not allow_time_stretch:
        return fit_audio_segment(audio, frame_count, channel_count)

    source_positions = np.linspace(0.0, 1.0, audio.shape[0], dtype=np.float32)
    target_positions = np.linspace(0.0, 1.0, frame_count, dtype=np.float32)
    rendered = np.empty((frame_count, channel_count), dtype=np.float32)
    for channel in range(channel_count):
        rendered[:, channel] = np.interp(target_positions, source_positions, audio[:, channel])
    return rendered


ACE_API_BASE_URL = "http://127.0.0.1:7860"


def is_ace_api_ready(base_url: str = ACE_API_BASE_URL) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=0.6) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def run_ace_repaint_task(
    *,
    source_audio_path: Path,
    output_path: Path,
    lyric: str,
    start_ms: int,
    end_ms: int,
    progress,
    base_url: str = ACE_API_BASE_URL,
) -> Path:
    import requests

    if not source_audio_path.exists():
        raise FileNotFoundError(source_audio_path)
    duration_seconds = max(10.0, (end_ms - start_ms) / 1000.0)
    language = "zh" if any("\u4e00" <= char <= "\u9fff" for char in lyric) else "en"
    form_data = {
        "prompt": "保持原歌曲音色、旋律和伴奏质感，只把选中片段改唱为新歌词。",
        "lyrics": lyric,
        "task_type": "repaint",
        "repainting_start": f"{max(0.0, start_ms / 1000.0):.3f}",
        "repainting_end": f"{max(0.1, end_ms / 1000.0):.3f}",
        "audio_duration": f"{duration_seconds:.3f}",
        "vocal_language": language,
        "thinking": "false",
        "inference_steps": "8",
        "batch_size": "1",
        "audio_format": "wav",
    }
    with source_audio_path.open("rb") as audio_file:
        response = requests.post(
            f"{base_url}/release_task",
            data=form_data,
            files={"src_audio": (source_audio_path.name, audio_file, "audio/wav")},
            timeout=60,
        )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", payload)
    task_id = data.get("task_id") if isinstance(data, dict) else None
    if not task_id:
        raise RuntimeError(f"ACE-Step 未返回任务 ID：{payload}")

    deadline = time.monotonic() + 60 * 30
    last_message = ""
    while time.monotonic() < deadline:
        time.sleep(5.0)
        query = requests.post(
            f"{base_url}/query_result",
            json={"task_id_list": [task_id]},
            timeout=30,
        )
        query.raise_for_status()
        query_payload = query.json()
        items = query_payload.get("data", query_payload)
        if isinstance(items, dict):
            items = items.get("data") or items.get("result") or []
        item = items[0] if isinstance(items, list) and items else {}
        status = item.get("status")
        progress(55, "ACE-Step 正在 CPU 推理，可能需要较长时间")
        if item.get("progress_text") and item.get("progress_text") != last_message:
            last_message = str(item.get("progress_text"))
            progress(58, f"ACE-Step：{last_message}")
        if status == 2:
            raise RuntimeError(f"ACE-Step 生成失败：{item}")
        if status == 1:
            audio_url = extract_ace_audio_url(item)
            if not audio_url:
                raise RuntimeError(f"ACE-Step 结果中没有音频地址：{item}")
            if audio_url.startswith("/"):
                audio_url = f"{base_url}{audio_url}"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(audio_url, stream=True, timeout=120) as download:
                download.raise_for_status()
                with output_path.open("wb") as out_file:
                    for chunk in download.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            out_file.write(chunk)
            return output_path
    raise TimeoutError("ACE-Step 生成超时，请稍后在工作台查看任务状态。")


def extract_ace_audio_url(item: dict) -> str | None:
    for key in ("first_audio_path", "file", "audio_path"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    result = item.get("result")
    if isinstance(result, str) and result.strip():
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list) and parsed:
            return extract_ace_audio_url(parsed[0])
        if isinstance(parsed, dict):
            return extract_ace_audio_url(parsed)
    return None


def resample_audio(audio, source_rate: int, target_rate: int):
    import numpy as np

    if source_rate == target_rate:
        return audio
    if source_rate <= 0 or target_rate <= 0 or audio.shape[0] <= 1:
        return audio
    target_frames = max(1, round(audio.shape[0] * target_rate / source_rate))
    source_positions = np.linspace(0.0, 1.0, audio.shape[0], dtype=np.float32)
    target_positions = np.linspace(0.0, 1.0, target_frames, dtype=np.float32)
    rendered = np.empty((target_frames, audio.shape[1]), dtype=np.float32)
    for channel in range(audio.shape[1]):
        rendered[:, channel] = np.interp(target_positions, source_positions, audio[:, channel])
    return rendered


def apply_source_energy_envelope(source, replacement, sample_rate: int):
    import numpy as np

    if source.shape != replacement.shape or replacement.size == 0:
        return replacement
    frame_count = replacement.shape[0]
    window = max(64, min(frame_count, round(sample_rate * 0.08)))
    if window <= 1:
        return replacement
    kernel = np.ones(window, dtype=np.float32) / window
    source_energy = np.sqrt(
        np.convolve(np.mean(np.square(source), axis=1), kernel, mode="same") + 1e-8
    )
    replacement_energy = np.sqrt(
        np.convolve(np.mean(np.square(replacement), axis=1), kernel, mode="same") + 1e-8
    )
    envelope = source_energy / np.maximum(replacement_energy, 1e-4)
    envelope = np.clip(envelope, 0.20, 1.45).astype(np.float32)[:, np.newaxis]
    return np.clip(replacement * envelope, -0.96, 0.96).astype(np.float32)


def crossfade_replace(original, replacement, sample_rate: int):
    import numpy as np

    frame_count = min(original.shape[0], replacement.shape[0])
    if frame_count <= 0:
        return original
    output = replacement[:frame_count].copy()
    fade_frames = min(frame_count // 2, max(32, round(sample_rate * 0.025)))
    if fade_frames > 1:
        fade_in = np.linspace(0.0, 1.0, fade_frames, dtype=np.float32)[:, np.newaxis]
        fade_out = np.linspace(1.0, 0.0, fade_frames, dtype=np.float32)[:, np.newaxis]
        output[:fade_frames] = original[:fade_frames] * (1.0 - fade_in) + output[:fade_frames] * fade_in
        output[-fade_frames:] = original[-fade_frames:] * (1.0 - fade_out) + output[-fade_frames:] * fade_out
    return np.clip(output, -1.0, 1.0)


def write_lyric_rewrite_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def lyric_rewrite_audio_path_from_manifest(manifest_path: Path) -> Path | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = manifest.get("preview_vocal_path")
    if not value:
        return None
    audio_path = Path(str(value))
    if not audio_path.is_absolute():
        audio_path = manifest_path.parent / audio_path
    return audio_path


def lyric_rewrite_version_label(audio_path: Path, index: int) -> str:
    manifest_path = audio_path.with_suffix(".json")
    lyric = ""
    lyric_index = None
    backend = ""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        lyric = str(manifest.get("lyric", "")).strip()
        lyric_index = manifest.get("lyric_index")
        backend = str(manifest.get("backend_label") or manifest.get("backend") or "").strip()
    except (OSError, json.JSONDecodeError):
        pass
    line_label = f"第 {lyric_index + 1} 句" if isinstance(lyric_index, int) else f"版本 {index + 1}"
    lyric_label = lyric if lyric else audio_path.stem
    if len(lyric_label) > 18:
        lyric_label = lyric_label[:18] + "..."
    suffix = f" · {backend}" if backend else ""
    return f"{line_label}：{lyric_label}{suffix}"


def update_project_active_vocal(manifest_path: Path, vocal_path: Path | None) -> None:
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if vocal_path is None:
        manifest.pop("active_vocal_path", None)
    else:
        manifest["active_vocal_path"] = str(vocal_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def backup_lyrics_file_once(path: Path) -> Path:
    backup_path = original_lyrics_backup_path(path)
    if not backup_path.exists():
        shutil.copyfile(path, backup_path)
    return backup_path


def original_lyrics_backup_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.original{path.suffix}")


def replace_timed_lyric_text(path: Path, lyric_index: int, new_text: str) -> None:
    if is_question_mark_pollution(new_text):
        raise ValueError("新歌词疑似编码错误，拒绝写入纯问号文本")
    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8")
    if suffix == ".lrc":
        updated = replace_lrc_line_text(content, lyric_index, new_text)
    elif suffix == ".srt":
        updated = replace_srt_line_text(content, lyric_index, new_text)
    else:
        raise ValueError(f"暂不支持更新歌词格式：{path.suffix}")
    path.write_text(updated, encoding="utf-8")


def replace_lrc_line_text(content: str, lyric_index: int, new_text: str) -> str:
    timed_index = -1
    output: list[str] = []
    pattern = re.compile(r"^(\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\])(.*)$")
    for line in content.splitlines():
        match = pattern.match(line.strip())
        if match and match.group(2).strip() and not is_instruction_hallucination(match.group(2).strip()):
            timed_index += 1
            if timed_index == lyric_index:
                output.append(f"{match.group(1)}{new_text}")
                continue
        output.append(line)
    if timed_index < lyric_index:
        raise IndexError("歌词行不存在，无法写入改词")
    return "\n".join(output) + ("\n" if content.endswith("\n") else "")


def replace_srt_line_text(content: str, lyric_index: int, new_text: str) -> str:
    blocks = re.split(r"(\r?\n\r?\n)", content)
    timed_index = -1
    for block_index in range(0, len(blocks), 2):
        block = blocks[block_index]
        parts = block.splitlines()
        if not parts:
            continue
        time_line_index = 1 if parts[0].strip().isdigit() and len(parts) >= 2 else 0
        if time_line_index >= len(parts) or "-->" not in parts[time_line_index]:
            continue
        text_start = time_line_index + 1
        text = " ".join(part.strip() for part in parts[text_start:] if part.strip())
        if text and is_instruction_hallucination(text):
            continue
        timed_index += 1
        if timed_index == lyric_index:
            blocks[block_index] = "\n".join(parts[:text_start] + [new_text])
            return "".join(blocks)
    raise IndexError("歌词行不存在，无法写入改词")


def is_question_mark_pollution(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 2:
        return False
    meaningful = [char for char in stripped if not char.isspace()]
    return bool(meaningful) and all(char in {"?", "？"} for char in meaningful)


def repair_question_mark_lyrics_from_backup(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    backup_path = original_lyrics_backup_path(path)
    if not backup_path.exists():
        return False
    try:
        current = path.read_text(encoding="utf-8")
        original = backup_path.read_text(encoding="utf-8")
    except OSError:
        return False
    repaired = repair_question_mark_lyric_content(current, original)
    if repaired == current:
        return False
    path.write_text(repaired, encoding="utf-8")
    return True


def repair_question_mark_lyric_content(current: str, original: str) -> str:
    original_lines = original.splitlines()
    output: list[str] = []
    changed = False
    pattern = re.compile(r"^(\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\])(.*)$")
    for index, line in enumerate(current.splitlines()):
        match = pattern.match(line.strip())
        if not match or not is_question_mark_pollution(match.group(2)):
            output.append(line)
            continue
        if index >= len(original_lines):
            output.append(line)
            continue
        original_match = pattern.match(original_lines[index].strip())
        if original_match and original_match.group(2).strip():
            output.append(original_lines[index])
            changed = True
        else:
            output.append(line)
    if not changed:
        return current
    return "\n".join(output) + ("\n" if current.endswith("\n") else "")


def sanitize_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "song"


def unique_child_path(parent: Path, name: str) -> Path:
    candidate = parent / name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = parent / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def looks_like_wave_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    return header.startswith(b"RIFF") and header[8:12] == b"WAVE"


def repair_migrated_project_manifest(project_dir: Path) -> None:
    manifest_path = project_dir / "project.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    changed = False
    for key in ("project_source", "vocal_path", "instrumental_path", "lyrics_path", "active_vocal_path"):
        value = manifest.get(key)
        if not value:
            continue
        current = Path(str(value))
        if current.exists():
            continue
        repaired = remap_migrated_project_path(project_dir, current)
        if repaired is not None:
            manifest[key] = str(repaired)
            changed = True
    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def remap_migrated_project_path(project_dir: Path, old_path: Path) -> Path | None:
    parts = old_path.parts
    if project_dir.name in parts:
        index = len(parts) - 1 - list(reversed(parts)).index(project_dir.name)
        candidate = project_dir.joinpath(*parts[index + 1 :])
        if candidate.exists():
            return candidate
    matches = list(project_dir.rglob(old_path.name))
    return matches[0] if matches else None


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            key = path.resolve()
        except (OSError, RuntimeError):
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def song_key(song: SongAsset) -> tuple[str, str | None]:
    return (str(song.root), None if song.source_path is None else str(song.source_path))


def is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def separator_backend_label(backend: str) -> str:
    labels = {
        "preview": "快速预览（不消人声）",
        "demucs": "真实人声分离（较慢）",
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
    if "Demucs 人声分离执行失败" in message:
        return f"导入失败：真实人声分离执行失败。{short_error_detail(message)}"
    if "No module named demucs" in message or "demucs" in message and "No module named" in message:
        return "导入失败：真实人声分离组件不可用。请使用包含 Demucs 的完整环境，或在设置里临时切换为“快速预览（不消人声）”。"
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


def format_lyric_rewrite_error(message: str) -> str:
    if "FileNotFoundError" in message or "not found" in message:
        return (
            "改词唱失败：没有找到当前歌曲的人声音轨或模型文件。"
            "请先确认左侧歌曲已正常加载，或重新导入这首歌后再试。"
        )
    if "选中的歌词时间超出当前音频长度" in message:
        return "改词唱失败：选中的歌词时间超出当前人声音轨长度，请先重新生成或校正歌词时间。"
    if "CalledProcessError" in message:
        return "改词唱失败：外部改唱工具执行失败，请检查模型环境或先切回本机轻量试听。"
    if "No module named" in message:
        return "改词唱失败：当前改唱运行环境缺少组件，请使用完整安装包或本机轻量试听模式。"
    return f"改词唱失败：{short_error_detail(message)}"


def short_error_detail(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "请换一首歌测试，或检查文件是否损坏。"
    return lines[-1][:220]


def first_existing_dir(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_demucs_python(root: Path) -> str:
    configured = os.environ.get("AUDIO_FORGE_DEMUCS_PYTHON")
    if configured:
        return configured

    config_path = root / "demucs_python.txt"
    if config_path.exists():
        try:
            configured_path = config_path.read_text(encoding="utf-8").strip().strip('"')
        except OSError:
            configured_path = ""
        if configured_path:
            return configured_path

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
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
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
