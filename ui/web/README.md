# Audio Forge Web UI

Vue3 + Ant Design Vue 前端界面原型，用于替换或增强当前 PyQt/QML 界面的视觉层。

## 功能范围

- 暗色 / 亮色主题切换。
- 歌曲库、滚动歌词、播放控制、分离/歌词后端选择、VST 导出入口。
- 未完成能力保持置灰，例如真人唱功真实模型入口。
- 当前版本是前端壳和交互原型，尚未直接连接 Python 后端。

## 本地运行

```powershell
cd ui\web
npm install
npm run dev
```

浏览器打开 Vite 输出的本地地址。

## 构建

```powershell
cd ui\web
npm run build
```

构建结果会输出到 `ui/web/dist`。
