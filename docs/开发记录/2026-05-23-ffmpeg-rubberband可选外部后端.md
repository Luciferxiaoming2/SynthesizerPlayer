# 2026-05-23 ffmpeg/rubberband 可选外部后端

## 本次目标

保留旧项目里 ffmpeg/rubberband 的能力价值，但不迁移旧二进制和旧实现。新项目只提供可选外部工具适配层。

## 已完成

- 新增 `core_engine/external_tools/audio_tools.py`：
  - `detect_audio_tool()`：探测 PATH 中是否存在工具。
  - `FfmpegAudioStandardizer`：用外部 ffmpeg 将导入音频标准化为内部 wav。
  - `RubberbandTimePitchProcessor`：预留外部 rubberband 高质量变速/变调处理。
- 扩展 `core_engine/importer/song_importer.py`：
  - `SongImportConfig` 新增 `audio_standardizer`。
  - 导入时可先用 ffmpeg 生成 `original_standard.wav`，再进入分离流程。
- 扩展 `harness/cli_harness/import_song.py`：
  - `--standardize-audio`
  - `--ffmpeg`
  - `--standard-sample-rate`
  - `--standard-channels`
- 新增 `harness/cli_harness/inspect_audio_tools.py`：
  - 输出 ffmpeg/rubberband 是否可用。
- 新增测试：
  - `tests/test_external_audio_tools.py`
  - 扩展 `tests/test_song_importer.py`

## 本机验证

- 外部工具适配测试通过。
- 当前 PATH 探测结果：
  - `ffmpeg: missing`
  - `rubberband: missing`

## 决策说明

- 保留能力，不保留旧二进制。
- ffmpeg 优先服务格式兼容、重采样、声道标准化和未来 mp3 导出。
- rubberband 暂时只作为低优先级可选能力，不替代当前 F0 跑调管线。
