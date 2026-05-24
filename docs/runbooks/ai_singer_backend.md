# 改词唱后端配置说明

当前应用已经具备改词唱 UI 流程：

1. 双击歌词行。
2. 输入新歌词。
3. 生成试听。
4. 自动替换当前人声音轨的对应片段并重新加载播放器。

默认后端是 `preview`，不需要模型，只用于验证流程。真实唱声模型后续通过配置文件接入，不把模型文件提交到 git。

## 配置位置

应用启动和生成改词唱时会依次查找：

- `ai_singer_backend.json`
- `plugins/config/ai_singer_backend.json`

正式交付时建议放在便携包目录，例如：

```text
AudioForgePortable_next/
  audio-forge-ui.exe
  ai_singer_backend.json
  plugins/
    models/
      ai-singer/
```

## preview 默认配置

不写配置文件时等同于：

```json
{
  "backend": "preview"
}
```

## 外部真实模型配置

外部后端使用命令模板数组，避免路径里有空格时被错误拆分。

```json
{
  "backend": "external",
  "diff_command": [
    "D:/uv/venvs/ai_singer/Scripts/python.exe",
    "D:/models/OpenVPI/infer.py",
    "--lyric",
    "{lyric}",
    "--melody",
    "{melody}",
    "--output",
    "{output}",
    "--sample-rate",
    "{sample_rate}",
    "--duration",
    "{duration}"
  ],
  "rvc_model_path": "plugins/models/ai-singer/voice.pth",
  "rvc_command": [
    "D:/uv/venvs/ai_singer/Scripts/python.exe",
    "D:/models/RVC/infer.py",
    "--source",
    "{source}",
    "--model",
    "{model}",
    "--output",
    "{output}"
  ]
}
```

## 占位符

`diff_command` 支持：

- `{lyric}`：用户输入的新歌词
- `{melody}`：当前人声音轨路径，后续可替换为独立旋律/MIDI
- `{output}`：外部唱声后端需要写出的 wav
- `{sample_rate}`：采样率
- `{duration}`：当前歌词片段时长

`rvc_command` 支持：

- `{source}`：唱声合成阶段输出的 wav
- `{model}`：`rvc_model_path`
- `{output}`：RVC 转换后需要写出的 wav

## 当前限制

- 还没有内置真实模型，也没有锁定最终推荐模型。
- 目前按整句歌词时间片段替换，不做音素级对齐。
- 外部命令必须自己保证输出 wav 存在，否则应用会提示生成失败。
- 模型、checkpoint、运行环境和大文件必须放在 `plugins/models/` 或便携包运行目录，不进 git。
