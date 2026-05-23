.PHONY: install install-dev install-package generate-mock import-song inspect-audio-tools scan-songs load-song-session lyrics-at run-ui run-mix run-effects export-mix run-playback run-pitch run-tone-deaf-mix analyze-f0 run-lyric package-cli package-ui test-harness lint agent-checks collect-context cleanup-agent

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev,dsp]"

install-package:
	python -m pip install -e ".[package]"

run-ui:
	python -m ui.main_window

generate-mock:
	python -m harness.cli_harness.generate_mock_audio --output-dir harness/mock_data

import-song:
	python -m harness.cli_harness.import_song --input harness/mock_data/vocal.wav --projects-root projects

inspect-audio-tools:
	python -m harness.cli_harness.inspect_audio_tools

scan-songs:
	python -m harness.cli_harness.scan_songs --songs-dir "源代码/Synthesizer Player/Synthesizer Player/songs"

load-song-session:
	python -m harness.cli_harness.load_song_session --songs-dir "源代码/Synthesizer Player/Synthesizer Player/songs" --song "好像（cover：郭静）" --position-ms 20000

lyrics-at:
	python -m harness.cli_harness.lyrics_at --lyrics "源代码/Synthesizer Player/Synthesizer Player/songs/好像（cover：郭静）/lyrics.lrc" --position-ms 20000

run-mix:
	python -m harness.cli_harness.run_dual_mix --vocal harness/mock_data/vocal.wav --instrumental harness/mock_data/instrumental.wav --output harness/mock_data/mix.wav

run-effects:
	python -m harness.cli_harness.render_effect_chain --input harness/mock_data/vocal.wav --output harness/mock_data/vocal_gain.wav --gain-db -6

export-mix:
	python -m harness.cli_harness.export_mix --vocal harness/mock_data/vocal.wav --instrumental harness/mock_data/instrumental.wav --output harness/mock_data/export_mix.wav --tone-deaf-ratio 0.4 --master-gain-db -3

run-playback:
	python -m harness.cli_harness.run_playback --vocal harness/mock_data/vocal.wav --instrumental harness/mock_data/instrumental.wav

run-pitch:
	python -m harness.cli_harness.run_pitch_shift --input harness/mock_data/vocal.wav --output harness/mock_data/vocal_tone_deaf.wav --ratio 0.4

run-tone-deaf-mix:
	python -m harness.cli_harness.render_tone_deaf_mix --vocal harness/mock_data/vocal.wav --instrumental harness/mock_data/instrumental.wav --output harness/mock_data/tone_deaf_mix.wav --ratio 0.4

analyze-f0:
	python -m harness.cli_harness.analyze_f0_drift --original harness/mock_data/vocal.wav --processed harness/mock_data/vocal_tone_deaf.wav

run-lyric:
	python -m harness.cli_harness.run_lyric_ai --lyric "yi-er-san" --melody harness/mock_data/melody.mid --output harness/mock_data/rewrite.wav

package-cli:
	powershell -ExecutionPolicy Bypass -File scripts/packaging/build_windows.ps1

package-ui:
	powershell -ExecutionPolicy Bypass -File scripts/packaging/build_windows_ui.ps1

test-harness:
	python -m harness.eval_harness.audio_latency_test
	python -m harness.eval_harness.f0_drift_eval

lint:
	python -m ruff check core_engine harness ui

agent-checks:
	python scripts/run_agent_checks.py

collect-context:
	python scripts/collect_context.py

cleanup-agent:
	python scripts/cleanup_agent_workspaces.py
