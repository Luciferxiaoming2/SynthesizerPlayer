from ui.main_window import (
    WorkbenchBridge,
    format_user_error,
    lyrics_backend_label,
    resolve_demucs_python,
    separator_backend_label,
)
from core_engine.player.sounddevice_output import AudioOutputDevice


def test_workbench_bridge_generates_and_exports_mock_audio(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.exportMix(0.2, -3.0)

    assert (tmp_path / "harness" / "mock_data" / "vocal.wav").exists()
    assert (tmp_path / "harness" / "mock_data" / "instrumental.wav").exists()
    assert (tmp_path / "harness" / "mock_data" / "ui_export_mix.wav").exists()
    assert "已导出" in bridge.status


def test_workbench_bridge_defaults_to_portable_import_library(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    assert bridge.songsRoot == str(tmp_path / "导入歌曲")
    assert (tmp_path / "导入歌曲").exists()


def test_workbench_bridge_playback_and_lyrics_state(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.play()
    bridge.advancePlayback()

    assert bridge.isPlaying
    assert bridge.playbackProgress > 0.0
    assert bridge.currentLyric
    assert bridge.lyricLines == ["样例前奏", "跑调预览", "可以导出"]
    assert bridge.currentLyricIndex >= 0

    bridge.seekProgress(0.8)
    assert bridge.playbackProgress >= 0.75

    bridge.pause()
    assert not bridge.isPlaying

    bridge.stop()
    assert bridge.playbackProgress == 0.0


def test_workbench_bridge_applies_lyrics_offset(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.seekProgress(0.25)

    bridge.setLyricsOffsetMs(500)

    assert bridge.lyricsOffsetMs == 500
    assert bridge.lyricsOffsetLabel == "0.5s"
    assert "延迟 0.5s" in bridge.status
    assert bridge._lyrics_sync.offset_ms == 500

    bridge.setLyricsOffsetMs(0)

    assert bridge.lyricsOffsetMs == 0
    assert bridge.lyricsOffsetLabel == "0s"
    assert "0 秒" in bridge.status


def test_workbench_bridge_applies_tone_deaf_to_loaded_playback(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    before = bridge._playback.buffers.vocal.copy()
    bridge.setToneDeafRatio(0.8)

    assert bridge.toneDeafRatio == 0.8
    assert bridge._playback is not None
    assert bridge._playback.buffers.vocal.shape == before.shape
    assert float(abs(bridge._playback.buffers.vocal - before).mean()) > 0.0001
    assert "已应用跑调强度" in bridge.status


def test_workbench_bridge_applies_tone_deaf_without_interrupting_playback(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.play()
    playback = bridge._playback
    playback.seek_frames(1000)

    bridge.setToneDeafRatio(0.8)

    assert bridge._playback is playback
    assert bridge.isPlaying
    assert bridge._playback.position_frames == 1000
    assert "实时应用跑调强度" in bridge.status


def test_workbench_bridge_toggles_track_mutes(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()

    bridge.toggleVocalMute()
    assert bridge.vocalMuted is True
    assert "人声已静音" in bridge.status

    bridge.toggleInstrumentalMute()
    assert bridge.instrumentalMuted is True
    assert "伴奏已静音" in bridge.status

    bridge.toggleVocalMute()
    bridge.toggleInstrumentalMute()
    assert bridge.vocalMuted is False
    assert bridge.instrumentalMuted is False


def test_workbench_bridge_sets_and_clears_master_vst_plugin(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    plugin = tmp_path / "example.vst3"
    plugin.write_text("fake plugin", encoding="utf-8")

    bridge.setMasterPluginFromUrl(plugin.as_uri())

    assert bridge.masterPluginPath == str(plugin)
    assert "已加载主输出 VST" in bridge.status

    bridge.clearMasterPlugin()
    assert bridge.masterPluginPath == ""
    assert "已移除主输出 VST" in bridge.status


def test_workbench_bridge_accepts_file_urls(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    selected = tmp_path / "selected.wav"

    bridge.setPathFromUrl("vocal", selected.as_uri())

    assert bridge.vocalPath == str(selected)
    assert "已选择人声文件" in bridge.status


def test_workbench_bridge_scans_and_loads_song_folder(tmp_path):
    songs_root = tmp_path / "songs"
    song_dir = songs_root / "Song A"
    song_dir.mkdir(parents=True)
    vocal = song_dir / "vocal.wav"
    instrumental = song_dir / "instrumental.wav"
    lyrics = song_dir / "lyrics.lrc"

    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    source_vocal = tmp_path / "harness" / "mock_data" / "vocal.wav"
    source_inst = tmp_path / "harness" / "mock_data" / "instrumental.wav"
    vocal.write_bytes(source_vocal.read_bytes())
    instrumental.write_bytes(source_inst.read_bytes())
    lyrics.write_text("[00:00.000]Song lyric", encoding="utf-8")

    bridge.setSongsRootFromUrl(songs_root.as_uri())
    bridge.loadSongAt(0)

    assert bridge.songNames == ["Song A"]
    assert bridge.vocalPath == str(vocal)
    assert bridge.instrumentalPath == str(instrumental)
    assert bridge.lyricsPath == str(lyrics)
    assert "音频已加载" in bridge.status


def test_workbench_bridge_preserves_english_sidecar_lyrics(tmp_path):
    songs_root = tmp_path / "songs"
    songs_root.mkdir()
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = songs_root / "english_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())
    complete_song.with_suffix(".lrc").write_text(
        "[00:00.000]Hello from the other side\n[00:01.000]I must have called a thousand times",
        encoding="utf-8",
    )

    bridge.importSongWithBackends(complete_song.as_uri(), "preview", "preview")

    assert bridge.lyricLines == [
        "Hello from the other side",
        "I must have called a thousand times",
    ]


def test_workbench_bridge_scans_plain_music_folder(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "Song A.mp3").write_bytes(b"fake")
    (music / "Song B.m4a").write_bytes(b"fake")

    bridge = WorkbenchBridge(tmp_path)
    bridge.setSongsRootFromUrl(music.as_uri())

    assert bridge.songNames == ["Song A", "Song B"]
    assert "已扫描到 2 首歌曲" in bridge.status


def test_workbench_bridge_delete_current_song_loads_next(tmp_path):
    songs_root = tmp_path / "songs"
    song_a = songs_root / "Song A"
    song_b = songs_root / "Song B"
    song_a.mkdir(parents=True)
    song_b.mkdir()

    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    source_vocal = tmp_path / "harness" / "mock_data" / "vocal.wav"
    source_inst = tmp_path / "harness" / "mock_data" / "instrumental.wav"
    for folder in (song_a, song_b):
        (folder / "vocal.wav").write_bytes(source_vocal.read_bytes())
        (folder / "instrumental.wav").write_bytes(source_inst.read_bytes())
        (folder / "lyrics.lrc").write_text("[00:00.000]line", encoding="utf-8")

    bridge.setSongsRootFromUrl(songs_root.as_uri())
    bridge.loadSongAt(0)
    bridge.play()

    bridge.deleteSongAt(0)

    assert bridge.songNames == ["Song B"]
    assert "Song B" in bridge.status or "音频已加载" in bridge.status
    assert bridge.vocalPath == str(song_b / "vocal.wav")


def test_workbench_bridge_clear_song_list_keeps_files(tmp_path):
    songs_root = tmp_path / "music"
    songs_root.mkdir()
    audio = songs_root / "Song A.mp3"
    audio.write_bytes(b"fake")
    bridge = WorkbenchBridge(tmp_path)
    bridge.setSongsRootFromUrl(songs_root.as_uri())

    bridge.clearSongList()

    assert bridge.songNames == []
    assert audio.exists()
    assert "不会删除磁盘文件" in bridge.status


def test_workbench_bridge_loops_current_song_when_finished(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    bridge.cyclePlayMode()
    assert bridge.playModeLabel == "单曲循环"

    bridge.play()
    assert bridge._playback is not None
    bridge._playback.seek_frames(bridge._playback.buffers.frame_count - 1)
    bridge.advancePlayback()

    assert bridge.isPlaying
    assert bridge.playbackProgress == 0.0
    assert "单曲循环" in bridge.status


def test_workbench_bridge_advances_to_next_song_in_list_mode(tmp_path):
    songs_root = tmp_path / "songs"
    song_a = songs_root / "Song A"
    song_b = songs_root / "Song B"
    song_a.mkdir(parents=True)
    song_b.mkdir()

    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    source_vocal = tmp_path / "harness" / "mock_data" / "vocal.wav"
    source_inst = tmp_path / "harness" / "mock_data" / "instrumental.wav"
    for folder in (song_a, song_b):
        (folder / "vocal.wav").write_bytes(source_vocal.read_bytes())
        (folder / "instrumental.wav").write_bytes(source_inst.read_bytes())
        (folder / "lyrics.lrc").write_text("[00:00.000]line", encoding="utf-8")

    bridge.setSongsRootFromUrl(songs_root.as_uri())
    bridge.loadSongAt(0)
    bridge.play()
    assert bridge._playback is not None
    bridge._playback.seek_frames(bridge._playback.buffers.frame_count - 1)

    bridge.advancePlayback()

    assert bridge.currentSongIndex == 1
    assert bridge.vocalPath == str(song_b / "vocal.wav")
    assert bridge.isPlaying
    assert "列表播放" in bridge.status


def test_workbench_bridge_blocks_missing_faster_whisper(tmp_path, monkeypatch):
    bridge = WorkbenchBridge(tmp_path)
    song = tmp_path / "song.wav"
    song.write_bytes(b"fake")
    monkeypatch.setattr("ui.main_window.is_module_available", lambda _name: False)

    bridge.importSongWithBackendsAsync(song.as_uri(), "preview", "faster-whisper")

    assert not bridge.importBusy
    assert "没有内置智能歌词识别组件" in bridge.status


def test_format_user_error_translates_missing_faster_whisper():
    assert "歌词识别失败" in format_user_error("No module named 'faster_whisper'")


def test_workbench_bridge_selects_audio_device_without_opening_it(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge._audio_devices = [
        AudioOutputDevice(3, "USB Speakers", 2, 48_000.0),
    ]

    bridge.selectAudioDevice(0)

    assert bridge.audioDeviceNames == ["3: USB Speakers"]
    assert bridge.selectedAudioDeviceIndex == 0
    assert bridge._selected_audio_device_id() == 3


def test_workbench_bridge_reports_audio_output_failure_in_chinese(tmp_path, monkeypatch):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()

    class FailingOutput:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("device unavailable")

    monkeypatch.setattr("ui.main_window.SoundDeviceOutput", FailingOutput)

    bridge.startAudioOutput()

    assert not bridge.audioOutputActive
    assert "音频播放失败" in bridge.status


def test_workbench_bridge_evaluates_alignment(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.evaluateAlignment()

    assert "对齐检测" in bridge.status
    assert "延迟=" in bridge.status


def test_workbench_bridge_imports_complete_song(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = tmp_path / "complete_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())

    bridge.importSongFromUrl(complete_song.as_uri())

    assert "导入歌曲" in bridge.vocalPath
    assert bridge.vocalPath.endswith("vocal.wav")
    assert bridge.instrumentalPath.endswith("instrumental.wav")
    assert bridge.songNames[0].startswith("complete_song")
    assert "导入成功" in bridge.status
    assert "分离=快速预览" in bridge.status


def test_workbench_bridge_imports_with_selected_backends(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = tmp_path / "complete_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())

    bridge.importSongWithBackends(complete_song.as_uri(), "preview", "none")

    assert bridge.separatorBackend == "preview"
    assert bridge.lyricsBackend == "none"
    assert bridge.vocalPath.endswith("vocal.wav")
    assert "分离=快速预览" in bridge.status


def test_workbench_bridge_standardizes_compressed_import_when_ffmpeg_exists(tmp_path, monkeypatch):
    bridge = WorkbenchBridge(tmp_path)
    compressed = tmp_path / "song.m4a"
    compressed.write_bytes(b"fake")
    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_text("fake", encoding="utf-8")

    monkeypatch.setattr("ui.main_window.resolve_audio_tool", lambda _name, _root: str(fake_ffmpeg))

    config = bridge._build_import_config(compressed, "preview", "preview")

    assert config.audio_standardizer is not None


def test_workbench_bridge_does_not_standardize_wav_import(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    wav = tmp_path / "song.wav"
    wav.write_bytes(b"fake")

    config = bridge._build_import_config(wav, "preview", "preview")

    assert config.audio_standardizer is None


def test_format_user_error_translates_unreadable_audio_format():
    assert "导入失败" in format_user_error("soundfile.LibsndfileError: Format not recognised")
    assert "ffmpeg" in format_user_error("soundfile.LibsndfileError: Format not recognised")


def test_workbench_bridge_reports_busy_import_guard(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge._set_import_busy(True)

    bridge.importSongWithBackendsAsync((tmp_path / "song.wav").as_uri(), "preview", "none")

    assert bridge.importBusy is True
    assert bridge.status == "歌曲正在导入中，请稍等"


def test_workbench_bridge_builds_mp3_encoder_only_for_mp3(tmp_path, monkeypatch):
    bridge = WorkbenchBridge(tmp_path)
    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_text("fake", encoding="utf-8")
    monkeypatch.setattr("ui.main_window.resolve_audio_tool", lambda _name, _root: str(fake_ffmpeg))

    assert bridge._build_mp3_encoder(tmp_path / "mix.wav") is None
    assert bridge._build_mp3_encoder(tmp_path / "mix.mp3") is not None


def test_right_panel_preset_updates_separator_backend(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.setRightPanelPreset(1)

    assert bridge.separatorBackend == "demucs"
    assert bridge.rightPanelPresetIndex == 1
    assert "极致消除" in bridge.status

    bridge.setRightPanelPreset(0)

    assert bridge.separatorBackend == "preview"
    assert bridge.rightPanelPresetIndex == 0
    assert "标准人声" in bridge.status


def test_right_panel_status_reflects_loaded_audio_and_diagnostics(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    assert bridge.sampleRateLabel == "未加载"
    assert bridge.toneMonitorStatus == "请先导入或加载歌曲"
    assert bridge.alignmentLatencyStatus == "未检测"

    bridge.generateMockAudio()

    assert bridge.sampleRateLabel == "16kHz"
    assert "跑调" in bridge.toneMonitorStatus

    bridge.evaluateAlignment()

    assert "ms" in bridge.alignmentLatencyStatus
    assert "未检测" not in bridge.alignmentLatencyStatus


def test_right_panel_plugin_and_lyrics_status_are_chinese(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    assert bridge.masterPluginStatus == "未加载 VST"
    assert bridge.lyricsEngineStatus == "占位提示"

    plugin = tmp_path / "demo.vst3"
    plugin.write_text("fake", encoding="utf-8")
    bridge.setMasterPluginFromUrl(plugin.as_uri())
    bridge.setLyricsBackend("none")

    assert bridge.masterPluginStatus == "已加载：demo.vst3"
    assert bridge.lyricsEngineStatus == "不生成歌词"


def test_backend_labels_are_chinese_for_ui():
    assert separator_backend_label("preview") == "快速预览"
    assert separator_backend_label("demucs") == "Demucs 人声分离"
    assert lyrics_backend_label("preview") == "占位提示"
    assert lyrics_backend_label("faster-whisper") == "智能识别歌词"
    assert lyrics_backend_label("none") == "不生成歌词"


def test_workbench_bridge_generates_preview_lyrics_for_loaded_audio(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()

    bridge.generateLyrics()

    assert bridge.lyricsPath.endswith("lyrics.lrc")
    assert bridge.lyricLines[0] == "未找到歌词文件"
    assert "歌词已生成" in bridge.status


def test_workbench_bridge_generate_lyrics_warns_for_missing_song(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateLyrics()

    assert "请先导入或加载一首歌曲" in bridge.status


def test_workbench_bridge_generate_lyrics_warns_when_backend_is_none(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.setLyricsBackend("none")

    bridge.generateLyrics()

    assert "不生成歌词" in bridge.status


def test_workbench_bridge_prompts_to_generate_when_import_has_no_lyrics(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = tmp_path / "complete_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())
    prompts: list[str] = []
    bridge.lyricsGenerationPromptRequested.connect(prompts.append)

    bridge.importSongWithBackends(complete_song.as_uri(), "preview", "none")

    assert prompts == ["这首歌没有可用歌词。是否现在使用智能识别生成歌词？"]
    assert bridge.lyricLines == []


def test_workbench_bridge_does_not_prompt_when_sidecar_lyrics_exist(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = tmp_path / "complete_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())
    complete_song.with_suffix(".lrc").write_text("[00:00.000]real lyric", encoding="utf-8")
    prompts: list[str] = []
    bridge.lyricsGenerationPromptRequested.connect(prompts.append)

    bridge.importSongWithBackends(complete_song.as_uri(), "preview", "preview")

    assert prompts == []
    assert bridge.lyricLines == ["real lyric"]


def test_workbench_bridge_prefers_bundled_lyrics_model(tmp_path):
    model_dir = tmp_path / "plugins" / "models" / "faster-whisper" / "base"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"fake")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    bridge = WorkbenchBridge(tmp_path)

    assert bridge._local_lyrics_model_path() == model_dir


def test_workbench_bridge_prefers_small_lyrics_model_over_base(tmp_path):
    base_dir = tmp_path / "plugins" / "models" / "faster-whisper" / "base"
    small_dir = tmp_path / "plugins" / "models" / "faster-whisper" / "small"
    for model_dir in [base_dir, small_dir]:
        model_dir.mkdir(parents=True)
        (model_dir / "model.bin").write_bytes(b"fake")
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
    bridge = WorkbenchBridge(tmp_path)

    assert bridge._local_lyrics_model_path() == small_dir


def test_resolve_demucs_python_prefers_configured_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_FORGE_DEMUCS_PYTHON", "D:/tools/python.exe")

    assert resolve_demucs_python(tmp_path) == "D:/tools/python.exe"


def test_resolve_demucs_python_uses_sidecar_python(tmp_path, monkeypatch):
    monkeypatch.delenv("AUDIO_FORGE_DEMUCS_PYTHON", raising=False)
    sidecar = tmp_path / "plugins" / "models" / "python" / "python.exe"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("fake", encoding="utf-8")

    assert resolve_demucs_python(tmp_path) == str(sidecar)


def test_demucs_runner_script_finds_pyinstaller_internal_data(tmp_path):
    runner = tmp_path / "_internal" / "core_engine" / "player" / "demucs_soundfile_runner.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("fake", encoding="utf-8")

    from ui.main_window import demucs_runner_script

    assert demucs_runner_script(tmp_path) == runner
