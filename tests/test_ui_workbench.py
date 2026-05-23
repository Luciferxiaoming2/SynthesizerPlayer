from ui.main_window import WorkbenchBridge, resolve_demucs_python
from core_engine.player.sounddevice_output import AudioOutputDevice


def test_workbench_bridge_generates_and_exports_mock_audio(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.exportMix(0.2, -3.0)

    assert (tmp_path / "harness" / "mock_data" / "vocal.wav").exists()
    assert (tmp_path / "harness" / "mock_data" / "instrumental.wav").exists()
    assert (tmp_path / "harness" / "mock_data" / "ui_export_mix.wav").exists()
    assert "Exported" in bridge.status


def test_workbench_bridge_playback_and_lyrics_state(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.play()
    bridge.advancePlayback()

    assert bridge.isPlaying
    assert bridge.playbackProgress > 0.0
    assert bridge.currentLyric

    bridge.seekProgress(0.8)
    assert bridge.playbackProgress >= 0.75

    bridge.pause()
    assert not bridge.isPlaying

    bridge.stop()
    assert bridge.playbackProgress == 0.0


def test_workbench_bridge_accepts_file_urls(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    selected = tmp_path / "selected.wav"

    bridge.setPathFromUrl("vocal", selected.as_uri())

    assert bridge.vocalPath == str(selected)
    assert "Selected vocal" in bridge.status


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
    assert "Playback loaded" in bridge.status


def test_workbench_bridge_selects_audio_device_without_opening_it(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge._audio_devices = [
        AudioOutputDevice(3, "USB Speakers", 2, 48_000.0),
    ]

    bridge.selectAudioDevice(0)

    assert bridge.audioDeviceNames == ["3: USB Speakers"]
    assert bridge.selectedAudioDeviceIndex == 0
    assert bridge._selected_audio_device_id() == 3


def test_workbench_bridge_evaluates_alignment(tmp_path):
    bridge = WorkbenchBridge(tmp_path)

    bridge.generateMockAudio()
    bridge.evaluateAlignment()

    assert "Alignment" in bridge.status
    assert "latency=" in bridge.status


def test_workbench_bridge_imports_complete_song(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = tmp_path / "complete_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())

    bridge.importSongFromUrl(complete_song.as_uri())

    assert "projects" in bridge.vocalPath
    assert bridge.vocalPath.endswith("vocal.wav")
    assert bridge.instrumentalPath.endswith("instrumental.wav")
    assert "Imported song project" in bridge.status
    assert "separator=preview" in bridge.status


def test_workbench_bridge_imports_with_selected_backends(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge.generateMockAudio()
    complete_song = tmp_path / "complete_song.wav"
    complete_song.write_bytes((tmp_path / "harness" / "mock_data" / "vocal.wav").read_bytes())

    bridge.importSongWithBackends(complete_song.as_uri(), "preview", "none")

    assert bridge.separatorBackend == "preview"
    assert bridge.lyricsBackend == "none"
    assert bridge.vocalPath.endswith("vocal.wav")
    assert "separator=preview" in bridge.status


def test_workbench_bridge_reports_busy_import_guard(tmp_path):
    bridge = WorkbenchBridge(tmp_path)
    bridge._set_import_busy(True)

    bridge.importSongWithBackendsAsync((tmp_path / "song.wav").as_uri(), "preview", "none")

    assert bridge.importBusy is True
    assert bridge.status == "Import already running"


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
