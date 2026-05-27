# Audio Forge / Synthesizer Player 迁移版

Audio Forge 是从旧版 Synthesizer Player 迁移出来的本地音频工作台。当前形态是 PyQt6 + QML 桌面应用，重点支持歌曲导入、双轨播放、滚动歌词、跑调处理、混音导出、VST 离线导出入口，以及可选的人声分离、歌词识别和 AI 改词唱能力。

## 当前状态

- 界面：中文单屏工作台 UI，支持暗色、亮色、浅绿色主题。
- 歌曲导入：支持 `wav/mp3/flac/ogg/m4a/aac` 等常见音频格式。
- 本地歌曲库：导入歌曲、分离音轨、歌词、AI 改唱试听都保存到本地歌曲库中。
- 播放：支持真实音频输出、进度拖动、人声/伴奏静音、音量调节和跑调预览。
- 歌词：支持 `.lrc/.srt`，播放时滚动高亮；英文歌曲保留英文歌词，中文歌曲尽量规范为简体中文。
- 歌词生成：支持占位提示和智能识别歌词，完整模型能力取决于交付包中是否包含对应模型。
- 改词唱：当前已接入 ACE-Step 本地 API 工作流，但完整本地运行包体积和硬件要求较高。
- 打包：支持 PyInstaller 生成 Windows 便携版。

## 交付方案

项目目前不建议把所有模型和运行环境都塞进一个安装包。完整离线包会超过 20GB，并且对客户电脑 CPU、内存和显卡要求较高。更推荐按业务场景拆分交付。

### 方案一：轻量标准版

目标体积：约 500MB - 1GB。

包含：

- 主程序和 UI
- 播放、导入、本地歌曲库
- 歌词导入和滚动歌词
- 跑调、音量、人声/伴奏混音
- ffmpeg、rubberband 等基础音频工具
- 可选轻量歌词识别模型

不包含：

- ACE-Step 完整运行时
- Demucs 完整分离环境
- 大型 Whisper 模型
- 大型本地改词唱模型

适合：普通客户首次安装、演示、基础音频处理和轻量使用。

### 方案二：插件包模式

主程序保持轻量，高级能力拆成独立插件包：

- `AudioForge_Separation_Pack`：人声分离模型和运行环境。
- `AudioForge_ACE_Pack`：AI 改词唱/ACE-Step 运行环境。
- `AudioForge_ASR_Pack`：更高质量歌词识别模型。

应用启动或点击对应功能时检查插件是否存在。如果缺失，提示用户安装对应插件包。

适合：商业交付和后续升级。优点是主程序小、更新快，高级功能按需安装。

### 方案三：完整离线版

当前完整离线目录：

```text
release\AudioForgePortable_next
```

该目录包含主程序、生产 Python、Demucs、faster-whisper、ACE-Step 运行时和模型资源。体积约 20GB 以上。

适合：必须纯离线、客户允许大体积交付、目标电脑配置较高的场景。

风险：

- 安装和传输成本高。
- 低配电脑运行 ACE-Step 或 Demucs 会很慢。
- 更新困难，每次升级都可能需要重新分发大包。

### 方案四：阿里百炼 / DashScope API

可以把部分音乐生成能力接入阿里百炼。百炼提供音乐相关模型，例如 `fun-music-v1`，支持通过 prompt 或歌词生成音乐。

适合：

- 根据歌词生成歌曲或试听版本。
- 云端生成候选音乐片段。
- 降低本地模型体积和客户电脑配置要求。

限制：

- 它更偏“根据歌词/提示生成新音乐”，不一定等同于“保留原唱音色并精确替换某一句”。
- API Key 不应直接放在客户端，最好由后端服务代理调用。
- 需要考虑费用、并发、网络、数据合规和客户隐私。

### 方案五：独立后端服务器

把复杂模型和重计算放到后端服务器，客户端只保留轻量桌面应用。

客户端负责：

- UI、播放、导入、试听
- 本地基础跑调和混音
- 上传任务、展示进度、下载结果

后端负责：

- 人声分离
- 歌词识别
- ACE-Step 或其它改词唱模型
- 阿里百炼 API 代理
- GPU/CPU 队列、缓存清理、任务进度推送

适合：正式商业化交付。优点是安装包小、客户电脑要求低、模型更新集中管理。缺点是需要服务器成本、账号体系、任务队列和数据安全设计。

### 推荐路线

短期建议：

1. 保留 `AudioForgePortable_dev` 作为开发调试版，指向本机虚拟环境。
2. 输出 `AudioForge_Lite` 作为轻量客户版。
3. 把人声分离、AI 改词唱、高清歌词识别拆成插件包。

中期建议：

1. 增加“组件中心”，显示高级组件是否已安装。
2. 增加“后端服务地址/API Key”配置。
3. 优先把 AI 改词唱和真实分离迁移到后端任务模式。

长期建议：

1. 对本地插件包做模型量化和瘦身。
2. 评估 ONNX Runtime、DirectML、C++/GGML 类实现，降低对 PyTorch 的依赖。
3. 对客户提供“轻量客户端 + 私有化后端”或“轻量客户端 + 云端 API”的两种商业交付形态。

## 环境与模型准备

本仓库只提交业务代码、测试和文档，不提交大模型、ACE-Step 运行时、ffmpeg、rubberband、生产 Python 环境和本地歌曲库。`git clone` 后需要按文档准备本地环境：

```text
docs\环境准备与模型下载.md
```

开发调试默认使用：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe
```

交付版建议使用 `release\AudioForgePortable_dev` 或后续轻量安装包；完整离线版和插件包需要额外放置模型与运行时。

## 运行方式

开发调试版：

```text
release\AudioForgePortable_dev\启动 Audio Forge Dev.bat
```

完整离线便携版：

```text
release\AudioForgePortable_next\audio-forge-ui.exe
```

开发环境默认使用：

```powershell
D:\uv\venvs\audio_forge\Scripts\activate
```

启动开发版 UI：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m ui.main_window
```

运行测试：

```powershell
D:\uv\venvs\audio_forge\Scripts\python.exe -m pytest
```

打包 Windows UI：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaging\build_windows_ui.ps1
```

创建生产环境：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaging\create_production_env.ps1
```

生成完整安装包需要先安装 Inno Setup，然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaging\build_full_installer.ps1
```

## 目录说明

- `core_engine/`：音频播放、DSP、歌词、导出、VST、AI 演唱等核心业务逻辑。该层不依赖 PyQt/QML。
- `ui/`：PyQt6/QML 桌面界面和桥接层。
- `harness/`：命令行工具和自动化验证入口，用于脱离 UI 验证业务链路。
- `scripts/`：打包、架构检查和本地工具脚本。
- `docs/`：产品、架构、迁移和开发记录。
- `plugins/`：本地插件、ffmpeg、模型等运行时资源目录，重型文件不提交仓库。
- `save/`：本地歌曲库，保存导入歌曲、分离音轨、歌词和改词试听。
- `release/`、`dist/`、`build/`：本地打包输出，不提交仓库。

## 注意事项

- 仓库只提交业务代码、测试和文档；音频文件、模型、打包结果、导入工程和临时输出不提交。
- 智能歌词识别默认优先使用 `plugins\models\faster-whisper\small`，缺少时可回退到 `base`。
- AI 改词唱仍是高成本能力，建议优先走插件包或后端服务器。
- VST 加载目前主要用于离线导出，不是完整实时宿主。
- 如果播放无声，请在界面右上角刷新输出设备，并选择当前耳机或扬声器。
