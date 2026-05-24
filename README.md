# Audio Forge / Synthesizer Player 迁移版

Audio Forge 是从旧版 Synthesizer Player 业务逻辑迁移出来的本地音频工作台。当前交付形态是 PyQt6 + QML 桌面应用，重点支持歌曲导入、双轨播放、滚动歌词、跑调/混音导出、VST 离线导出入口，以及可选的人声分离和歌词生成后端。

## 当前状态

- 界面：中文单屏 K 歌风格 UI，支持暗色界面。
- 歌曲导入：支持 `wav/mp3/flac/ogg/m4a/aac` 等常见音频格式。
- 歌曲库：可扫描普通音乐文件夹，也可识别人声/伴奏双轨工程目录。
- 播放：支持真实音频输出、无声预览、进度拖动、人声/伴奏静音、音量调节和跑调预览。
- 歌词：支持 `.lrc/.srt`，播放时滚动高亮；英文歌曲会保留英文歌词。
- 生成歌词：提供“占位提示”和“智能识别歌词”两种方式；完整安装包会内置识别组件。
- 导出：可导出混音 wav，跑调强度会写入导出结果，主输出 VST 目前在导出时生效。
- 打包：已支持 PyInstaller 生成便携版 exe。

## 直接运行便携版

打包后的应用放在：

```text
release\AudioForgePortable_next\audio-forge-ui.exe
```

双击 `audio-forge-ui.exe` 即可启动。若旧目录 `release\AudioForgePortable` 正在运行或被占用，推荐使用 `AudioForgePortable_next`。

## 开发环境

项目默认使用本机虚拟环境：

```powershell
D:\uv\venvs\audio_forge\Scripts\activate
```

安装开发依赖：

```powershell
uv pip install -e ".[dev,dsp,package]"
```

如需在开发环境里测试智能歌词识别，再额外安装：

```powershell
uv pip install -e ".[asr]"
```

识别模型不提交仓库；交付便携包时优先放入 `plugins\models\faster-whisper\small`，打包脚本会自动随包带上。若只存在 `plugins\models\faster-whisper\base`，应用会回退使用 base 模型。

## 常用命令

启动开发版 UI：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m ui.main_window
```

运行测试：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m pytest
```

检查架构约束：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe scripts\validate_architecture.py
```

打包 Windows UI：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaging\build_windows_ui.ps1
```

生成测试音频：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.generate_mock_audio --output-dir harness\mock_data
```

生成明显跑调的人声：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.run_pitch_shift --input harness\mock_data\vocal.wav --output harness\mock_data\vocal_tone_deaf.wav --ratio 0.8
```

导入单首歌曲：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m harness.cli_harness.import_song --input D:\music\song.mp3 --projects-root projects --backend preview --lyrics-backend preview
```

## 目录说明

- `core_engine/`：音频播放、DSP、歌词、导出、VST、AI 演唱等核心业务逻辑。此层不依赖 PyQt/QML。
- `ui/`：PyQt6/QML 桌面界面和桥接层。
- `harness/`：命令行工具和自动化验证入口，用于脱离 UI 验证业务链路。
- `scripts/`：打包、架构检查和本地工具脚本。
- `docs/`：产品、架构、迁移和开发记录。
- `plugins/`：本地插件、ffmpeg、模型等运行时资源目录，重型文件不提交仓库。
- `projects/`：导入歌曲后生成的本地工程目录，不提交仓库。
- `release/`、`dist/`、`build/`：本地打包输出，不提交仓库。

## 后端说明

### 分离方式

- `快速预览`：轻量占位分离，用于快速跑通导入和播放流程。
- `Demucs 人声分离`：真实分离后端，需要本机具备 Demucs 运行环境、ffmpeg 和模型缓存。

### 歌词方式

- `占位提示`：不会识别歌词内容，只生成中文提示 LRC，确保歌词区不空白。
- `智能识别歌词`：使用随包识别组件和本地模型生成歌词，用户不需要了解底层依赖。
- `不生成歌词`：适合纯音乐或暂时不需要歌词的歌曲。

## 注意事项

- 仓库只提交业务代码、测试和文档；音频文件、模型、打包结果、导入工程和 harness 规范文件都已放入 `.gitignore`。
- 智能歌词识别默认使用 `plugins\models\faster-whisper\small`；缺少 small 时可回退 `plugins\models\faster-whisper\base`。
- 当前“真人唱功/改词唱”仍是实验性适配层，不是完整商业模型效果。
- “跑调强度”会影响播放和导出；长歌曲拖动滑杆后重新处理人声可能需要等待几秒。
- VST 加载目前用于离线导出，不是实时播放链路。
- 如播放无声，请在界面右下角刷新输出设备，并选择当前耳机或扬声器。
