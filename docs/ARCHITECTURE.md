# Audio Forge 架构说明

## 分层原则

Audio Forge 采用 Harness Engineering 思路：核心算法、测试执行脚手架、界面层完全解耦。底层音频算法必须能够在没有 UI 的情况下由命令行或评估脚本直接驱动。

## 目录职责

- `core_engine/`：核心引擎层，只放纯逻辑、无 UI 依赖的音频播放、DSP、VST、AI 歌声合成边界。
- `core_engine/player/`：双轨同步 Buffer、音轨分离、后续 SoundDevice 播放引擎。
- `core_engine/dsp/`：真实跑调、F0 漂移、VST 效果链等传统音频信号处理。
- `core_engine/ai_singer/`：DiffSinger、RVC 等外部 AI 推理运行时的适配边界。
- `harness/cli_harness/`：无 UI 命令行入口，用于快速验证跑调、歌词替换等核心链路。
- `harness/eval_harness/`：质量评估脚手架，用于自动测试双轨延迟、F0 漂移自然度等指标。
- `harness/mock_data/`：自动化测试样本，放标准干声、伴奏、旋律文件。
- `ui/`：PyQt/QML 视图层，只负责单屏界面、状态展示和用户事件绑定。
- `plugins/`：本地 VST3 插件与模型权重目录，重型二进制资源不应写入源码。

## 依赖方向

允许的依赖方向：

```text
ui -> core_engine
harness -> core_engine
core_engine -> numpy / sounddevice / pyworld / pedalboard / external AI runtimes
```

禁止的依赖方向：

```text
core_engine -> ui
core_engine -> PyQt6 / QML
eval_harness -> ui
```

## 当前状态

当前仓库已经完成基础目录、Python 包入口、命令行 harness、评估 harness、QML 主视图占位、`pyproject.toml`、`Makefile` 与 `.env.example`。算法实现仍保持为清晰边界和占位实现，后续应优先从 `harness` 跑通真实音频链路，再接 UI。

## 推荐下一步

1. 在 `core_engine/player/sync_buffer.py` 接入 `soundfile` 读取双轨 wav，并保持 sample-level 对齐。
2. 在 `harness/eval_harness/audio_latency_test.py` 实现互相关延迟检测。
3. 在 `core_engine/dsp/tone_deaf.py` 接入 PyWorld 的 F0 提取与分块离线渲染。
4. 用 `harness/cli_harness/run_pitch_shift.py` 验证无 UI 的跑调输出。
5. 再将 `ui/main_window.py` 绑定到已验证的 engine API。
