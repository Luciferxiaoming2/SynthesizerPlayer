##  产品需求文档 (PRD)（包含技术版）

### 1. 项目概述

本项目是一款具备高度二次创作能力的高级音频播放应用。在传统双轨（人声+伴奏）播放器的基础上，引入 AI 语音合成与底层信号处理技术，为用户提供“真实跑调模拟”、“局部歌词 AI 篡改”以及“专业 VST 音效扩展”三大核心黑科技。

### 2. 核心功能与交互说明

- **F0: 单曲导入与自动工程初始化**
  - **需求**：客户只导入一首完整歌曲文件（MP3/WAV/FLAC 等），系统自动完成后续准备工作。
  - **人声分离**：导入后自动拆分为人声轨与伴奏轨，并缓存到该歌曲的工程目录，后续播放、跑调、VST、导出都基于拆分后的双轨资产。
  - **歌词生成/匹配**：优先读取同目录已有 `.lrc` / `.srt` 歌词；如果没有歌词，则进入自动识别/转写流程，生成可编辑歌词时间轴。
  - **用户体验要求**：普通用户不需要理解“stem”“vocal”“instrumental”等工程概念；界面应表现为“导入歌曲 -> 等待处理 -> 直接播放/编辑/导出”。
- **基础播放框架（已实现）**
  - 人声与伴奏独立轨道，支持独立音量调节与静音。
  - 右侧滚动歌词，支持时间轴拖拽校准。
- **F1: 真实跑调模拟器 (Tone-Deaf Simulator)**
  - **需求**：提供 1% - 80% 的“跑调比例”调节。处理后的人声必须与伴奏严格同步，无延迟。
  - **音效要求**：必须模拟人类真实的“五音不全”（音准漂移、颤音失控、找不到调），**绝对不能**是简单的全局升降调（Pitch Shift）。
- **F2: AI 歌词篡改 (AI Lyric-to-Vocal)**
  - **交互**：在右侧歌词面板，双击某一句歌词（如将“我爱你”改成“一二三”）。
  - **处理**：系统在后台自动合成出唱着“一二三”的人声，且旋律必须与原曲该句旋律一致，音色尽可能贴近原唱。
  - **无缝播放**：当进度条播放到该句时，自动将原声替换为 AI 合成的人声。
- **F3: VST 音频效果器宿主 (VST Host)**
  - **需求**：支持加载第三方标准的 `.dll` 或 `.vst3` 音频效果器插件。
  - **应用**：用户可将混响、电音（Auto-Tune）、EQ 等插件独立挂载到人声或伴奏轨道上实时生效。

## 🛠 技术整合文档 (Tech Spec)

### 1. 技术栈与开源项目矩阵

为了最小化开发成本，我们将完全基于 Python 生态进行“搭积木”式的整合。

| **功能模块** | **采用技术/库**          | **推荐开源项目地址**                                         | **整合方案说明**                                          |
| ------------ | ------------------------ | ------------------------------------------------------------ | --------------------------------------------------------- |
| **单曲导入工程化** | `soundfile` / `ffmpeg` / 自研工程缓存 | FFmpeg 官方工具链 | 将用户导入的完整歌曲转为内部标准 wav，创建工程目录，管理原曲、stem、歌词、缓存和导出结果。 |
| **人声/伴奏分离** | `Demucs` / `Spleeter` / `UVR5` | [Demucs Github](https://github.com/facebookresearch/demucs) / [Spleeter Github](https://github.com/deezer/spleeter) | MVP 优先走外部命令适配器，输出 `vocal.wav` 与 `instrumental.wav`；后续根据机器性能决定是否内置轻量模型。 |
| **歌词识别/转写** | `Whisper` / `faster-whisper` / 本地 LRC/SRT | [faster-whisper Github](https://github.com/SYSTRAN/faster-whisper) | 先匹配本地歌词文件；缺失时用 ASR 生成初始文本和时间戳，再开放用户校准。 |
| **真实跑调** | `PyWorld` (WORLD 声码器) | [PyWORLD Github](https://github.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder) | 直接提取人声的基频（F0），加入随机噪声后重构音频。        |
| **VST 宿主** | `Pedalboard` (Spotify)   | [Pedalboard Github](https://github.com/spotify/pedalboard)   | 几行代码即可在 Python 中加载并运行 VST3 插件，性能极高。  |
| **旋律生成** | `DiffSinger`             | [DiffSinger Github](https://github.com/MoonInTheRiver/DiffSinger) | B 站上最火的 AI 歌声合成框架，支持输入文字+音高生成干声。 |
| **音色克隆** | `RVC-WebUI`              | [RVC Github](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) | 将 DiffSinger 生成的干声，转换为原唱的音色。              |

### 2. 核心难点改造指南

#### 方案零：实现“导入一首歌自动拆解”

这是客户侧最重要的入口流程，优先级应高于高级 AI 改词唱。

1. **导入原曲**：用户选择一首完整歌曲文件，系统复制或引用该文件，并创建独立工程目录。
2. **标准化音频**：使用 `soundfile` 或可选 `ffmpeg` 将原曲转换为统一采样率/声道格式，避免后续 DSP 与播放链路出现格式差异。
3. **人声分离**：通过外部命令适配器调用 Demucs/Spleeter/UVR5，生成 `vocal.wav` 与 `instrumental.wav`。
4. **歌词处理**：先查找同名 `.lrc` / `.srt`；没有歌词时调用 Whisper/faster-whisper 生成初始歌词时间轴。
5. **进入双轨工程**：将分离结果和歌词时间轴加载到现有 `core_engine` 播放、跑调、VST、导出流程中。

#### 方案一：实现“真实跑调”（零延迟策略）

真正的跑调不是单纯变调，而是**基频（F0）的随机游离**。

1. **特征提取**：当用户加载人声轨道时，后台静默使用 `pyworld.wav2world` 提取整轨的 F0（音高曲线）、SP（频谱包络）和 AP。
2. **动态篡改**：根据用户设置的 1%-80% 跑调比例，生成一个低频振荡器（LFO）结合随机噪声，叠加到 F0 曲线上。比例越高，F0 偏离原本正确音高的幅度越大。
3. **防延迟策略**：因为 `pyworld.synthesize` 实时处理整首高质量歌曲会有延迟导致声画不同步。**最佳改造方案**：在拖动滑块松手时（或预先），在后台进行“分块离线渲染（Chunk processing）”替换内存中的播放 Buffer，从而保证与伴奏的完美对齐。

#### 方案二：实现 AI 歌词篡改（DiffSinger + RVC）

这个功能是缝合怪中的战斗机，需要串联两个模型。

1. **截取数据**：双击歌词后，根据你现有的时间轴系统，精准截取该句的原声音频。
2. **生成干声**：利用现成的音高提取算法（如 RMVPE）提取原声旋律。将新歌词（“一二三”）和旋律一起送入 **DiffSinger** 模型，生成一段有着正确旋律但音色通用的音频。
3. **音色还原**：将这小段音频送入 **RVC** API（需要你提前下好该歌手的 RVC 模型，或使用通用模型），将其转化为原唱音色。
4. **音频热替换**：在 Python 的播放引擎队列中，直接覆写这段时间戳对应的 Numpy 数组。

#### 方案三：实现 VST 宿主加载

这一步最简单，直接采用 Spotify 开源的 `pedalboard`。它在 Python 中释放了 GIL，支持多核处理，非常适合挂载在你现有播放器的输出流前。

Python

```
# 极其简单的 VST 整合伪代码
from pedalboard import Pedalboard, load_plugin

# 1. 加载用户选择的 VST3 插件
vst_plugin = load_plugin("C:/Program Files/Common Files/VST3/AutoTune.vst3")

# 2. 将其加入效果器链
board = Pedalboard([vst_plugin])

# 3. 在你的音频流回调函数(Stream Callback)中，用 board 处理音频块
processed_audio_chunk = board(raw_audio_chunk, sample_rate)
```

这套方案可以说是目前 Python 生态里能实现你需求的最优解了。特别是 `pedalboard` 和 `PyWorld`，它们不仅效果专业，而且不用你手撸底层的 C++ DSP 算法。
