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

打包产物不默认内置旧歌曲资源。需要真实 Demucs 分离时，交付包不能要求普通用户自行安装 Python、Demucs、torch 或模型；正式交付必须在 exe 同级目录放置可直接运行的 sidecar 环境和本地资源：

```text
dist\audio-forge-ui\
  audio-forge-ui.exe
  python\python.exe
  python\Lib\site-packages\demucs\...
  python\Lib\site-packages\torch\...
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
2. exe 同级 `demucs_python.txt`
3. `plugins\models\python\python.exe`
4. `python\python.exe`
5. 开发态使用当前解释器，打包态回退到系统 `python`

开发阶段可以临时依赖本机环境：

```powershell
$env:AUDIO_FORGE_DEMUCS_PYTHON = "D:\uv\venvs\audio_forge\Scripts\python.exe"
dist\audio-forge-ui\audio-forge-ui.exe
```

也可以在便携目录放 `demucs_python.txt`，内容为一行 Python 路径：

```text
D:\uv\venvs\audio_forge\Scripts\python.exe
```

开发阶段可用这个文件让直接双击 `audio-forge-ui.exe` 也能找到当前机器上的 Demucs 环境。正式交付时，`demucs_python.txt` 应改为指向包内 `python\python.exe`，或直接放置 `python\python.exe` 让程序自动发现。

正式交付时不应依赖上面的开发机路径。交付包应满足：

- 双击 `启动 Audio Forge.bat` 或 `audio-forge-ui.exe` 后即可执行真实人声分离。
- Demucs、torch、模型 checkpoint、ffmpeg/ffprobe 均来自包内目录。
- `save\` 作为用户导入歌曲工程目录，随程序首次启动自动创建，不能进入 git。
- 如包体过大，可拆成“基础包 + 模型环境包”，但安装/解压后仍要做到用户无需手动安装 Python 依赖。

## 当前限制

- 不默认打包 VST 插件、AI 模型权重、旧歌曲资源。
- GUI 包当前仍是 MVP，不包含安装器、图标、自动更新和模型管理。
- 当前开发包的 Demucs 真实分离可依赖开发机 `D:\uv\venvs\audio_forge`；正式交付必须改为包内 sidecar Python 环境。
- 真实 DiffSinger/RVC 后端需要用户额外放置模型和推理脚本，再通过外部命令模板接入。
