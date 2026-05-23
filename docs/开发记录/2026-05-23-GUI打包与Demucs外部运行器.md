# 2026-05-23 GUI 打包与 Demucs 外部运行器

## 本次目标

继续推进打包交付验证：GUI 包需要能启动 QML，并且不能因为 Demucs runner 把 torch/torchaudio/scipy 全部打进 GUI 主包。真实 Demucs 分离继续走外部 Python 或 sidecar Python。

## 已完成

- 调整 `ui/main_window.py`：
  - GUI Demucs 后端不再固定使用 `sys.executable`。
  - 新增 `resolve_demucs_python()`，按环境变量、sidecar Python、开发态解释器、系统 Python 的顺序选择。
  - 新增 `demucs_runner_script()`，支持查找源码态路径和 PyInstaller `_internal` 数据路径。
- 调整 `core_engine/player/stem_separator.py`：
  - `DemucsSeparatorConfig` 新增 `runner_script`。
  - 提供 runner script 时，命令改为 `python demucs_soundfile_runner.py ...`，不再要求外部 Python 能 `-m core_engine...`。
- 调整 PyInstaller spec：
  - CLI/GUI 包都把 `demucs_soundfile_runner.py` 作为 data 文件放入包内。
  - 不再 hidden import Demucs runner，避免触发 torch 大依赖收集。
- 扩展 `scripts/packaging/audio_forge_cli.py`：
  - 新增 `inspect-audio-tools` 打包后诊断命令。
- 更新 `docs/runbooks/packaging_windows.md`：
  - 说明本地 ffmpeg、模型缓存和 sidecar Python 放置方式。
  - 说明 `AUDIO_FORGE_DEMUCS_PYTHON` 环境变量。

## 本机验证

- runner script 方式真实 Demucs 导入：
  - 成功生成 `vocal.wav` 和 `instrumental.wav`。
- `powershell -ExecutionPolicy Bypass -File scripts\packaging\build_windows_ui.ps1`
  - 成功生成 `dist\audio-forge-ui\audio-forge-ui.exe`。
- 打包后 GUI smoke：
  - `Audio Forge UI smoke loaded`
- 包内 runner 文件：
  - `dist\audio-forge-ui\_internal\core_engine\player\demucs_soundfile_runner.py` 存在。
- `D:\uv\venvs\audio_forge\Scripts\python.exe -m pytest`
  - 70 passed
- `D:\uv\venvs\audio_forge\Scripts\python.exe scripts\validate_architecture.py`
  - Architecture validation passed

## 当前边界

- GUI 包仍不内置 Demucs、torch、模型权重和 Python 运行时。
- 真实 Demucs 分离需要配置系统 Python、`AUDIO_FORGE_DEMUCS_PYTHON` 或 sidecar Python。
- 后续如要做一键安装包，需要增加模型/运行时管理器，而不是把大模型直接塞进主 exe。
