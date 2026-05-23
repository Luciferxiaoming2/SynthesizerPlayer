# Windows 打包说明

## 目标

当前打包目标分为两类：

- `audio-forge-cli`：命令行 MVP。
- `audio-forge-ui`：PyQt6/QML 图形界面 MVP。

命令行 MVP 覆盖普通用户可验证的核心能力：

- 生成 mock 音频。
- 导入完整歌曲并创建本地工程目录。
- 探测本地 ffmpeg/rubberband 工具。
- 跑调渲染与 F0 评估。
- 离线效果链处理。
- 双轨混音导出。
- 改词唱 preview 流程。

图形界面 MVP 覆盖歌曲库扫描、文件选择、播放预览、真实音频输出入口、歌词显示和导出。

## 准备依赖

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m pip install -e ".[package]"
```

如果还没有安装项目运行依赖：

```powershell
uv pip install -e ".[dev,dsp,package]"
```

## 执行打包

```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaging\build_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\packaging\build_windows_ui.ps1
```

输出位置：

```text
dist\audio-forge-cli\audio-forge-cli.exe
dist\audio-forge-ui\audio-forge-ui.exe
```

## 打包后自测

```powershell
dist\audio-forge-cli\audio-forge-cli.exe inspect-audio-tools

dist\audio-forge-cli\audio-forge-cli.exe generate-mock --output-dir dist\audio-forge-cli\mock_data

dist\audio-forge-cli\audio-forge-cli.exe import-song `
  --input dist\audio-forge-cli\mock_data\vocal.wav `
  --projects-root dist\audio-forge-cli\projects

dist\audio-forge-cli\audio-forge-cli.exe export-mix `
  --vocal dist\audio-forge-cli\mock_data\vocal.wav `
  --instrumental dist\audio-forge-cli\mock_data\instrumental.wav `
  --output dist\audio-forge-cli\mock_data\export_mix.wav `
  --tone-deaf-ratio 0.4 `
  --master-gain-db -3

dist\audio-forge-cli\audio-forge-cli.exe run-lyric `
  --lyric "new words preview" `
  --melody dist\audio-forge-cli\mock_data\melody.mid `
  --output dist\audio-forge-cli\mock_data\rewrite_preview.wav
```

GUI smoke 自测：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QSG_RHI_BACKEND = "software"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
$env:AUDIO_FORGE_UI_SMOKE = "1"
dist\audio-forge-ui\audio-forge-ui.exe
```

看到 `Audio Forge UI smoke loaded` 即表示 QML 已成功加载。

## 本地工具与模型目录

打包产物不默认内置大模型和旧歌曲资源。需要真实 Demucs 分离时，推荐在 exe 同级目录放置这些本地资源：

```text
dist\audio-forge-ui\
  audio-forge-ui.exe
  plugins\models\ffmpeg\ffmpeg.exe
  plugins\models\ffmpeg\ffprobe.exe
  plugins\models\torch\hub\checkpoints\*.th
```

GUI 选择 Demucs 后端时会自动查找：

1. `plugins\models\ffmpeg`
2. 旧源码目录中的 `源代码\Synthesizer Player\Synthesizer Player\ffmpeg\bin`
3. 系统 PATH

Demucs 需要可执行 Python。GUI 会按以下顺序查找：

1. 环境变量 `AUDIO_FORGE_DEMUCS_PYTHON`
2. `plugins\models\python\python.exe`
3. `python\python.exe`
4. 开发态使用当前解释器，打包态回退到系统 `python`

示例：

```powershell
$env:AUDIO_FORGE_DEMUCS_PYTHON = "D:\uv\venvs\audio_forge\Scripts\python.exe"
dist\audio-forge-ui\audio-forge-ui.exe
```

## 当前限制

- 不默认打包 VST 插件、AI 模型权重、旧歌曲资源。
- GUI 包当前仍是 MVP，不包含安装器、图标、自动更新和模型管理。
- Demucs 真实分离依赖外部 Python 环境或 sidecar Python。
- 真实 DiffSinger/RVC 后端需要用户额外放置模型和推理脚本，再通过外部命令模板接入。
