# 2026-05-23 faster-whisper 歌词识别适配器

## 本次目标

在不默认安装大依赖、不默认下载模型的前提下，为“导入完整歌曲后自动生成歌词”接入真实 ASR 开源后端 faster-whisper。

## 已完成

- 扩展 `core_engine/transcription/lyrics_transcriber.py`：
  - 新增 `FasterWhisperConfig`。
  - 新增 `FasterWhisperLyricsTranscriber`。
  - 使用懒加载导入 `faster_whisper.WhisperModel`，未安装时给出明确错误。
  - 将 segment 的 start time 和 text 写成 LRC 格式。
- 扩展 `harness/cli_harness/import_song.py`：
  - `--lyrics-backend faster-whisper`
  - `--whisper-model`
  - `--whisper-device`
  - `--whisper-compute-type`
  - `--whisper-language`
- 扩展 `pyproject.toml`：
  - 新增 optional extra：`asr = ["faster-whisper>=1.1"]`。
- 更新 agent/runbook 文档：
  - 记录 ASR 安装和命令示例。

## 当前边界

- 未自动安装 faster-whisper。
- 未下载 Whisper 模型。
- 在 Intel 轻薄本上建议先测 `base` + `cpu` + `int8`，确认速度和识别质量后再决定是否升级模型。
