# 🎧 AI 实时悬浮字幕翻译工具

一个基于 Python 的桌面工具，可以**实时监听系统正在播放的视频声音**，并将语音内容自动识别并翻译成中文，以悬浮字幕的形式显示在屏幕上。

---

## ✨ 功能特性

🚀 **实时语音识别**

* 使用 `faster-whisper` 模型
* 支持英文 / 日文等多语言

🌍 **自动翻译**

* 自动检测语言 → 翻译为中文
* 基于 Google 翻译接口

🖥️ **悬浮字幕窗口**

* 永远置顶（不挡操作）
* 半透明 + 圆角 UI
* 支持鼠标拖动

⚡ **低延迟优化**

* 使用 `tiny` 模型（优先速度）
* 后台线程处理识别与翻译
* 实际延迟约 **0.5 ~ 1 秒**

---

## 🧠 使用场景

📺 看 B站 / YouTube 英文视频
🎌 看日语动画无字幕
📚 听国外课程 / 公开课
💼 实时翻译会议音频

---

## 📦 安装依赖

建议使用虚拟环境：

```bash
pip install numpy sounddevice faster-whisper deep-translator PyQt5 pyinstaller
```

或：

```bash
pip install -r requirements.txt
```

---

## ▶️ 运行项目

```bash
python main_app.py
```

运行后你会看到：

✅ 屏幕出现一个悬浮字幕框
✅ 播放视频时自动出现翻译字幕

---

## ⚠️ 必做设置（Windows）

本项目依赖 **系统声音采集（立体声混音）**

### 👉 开启步骤：

1. 右键任务栏音量图标 🔊
2. 点击 **声音设置**
3. 进入 **更多声音设置**
4. 切换到 **录制**
5. 找到：

```text
立体声混音 / Stereo Mix
```

6. 如果没有：

👉 右键空白区域 → ✔ 显示禁用设备
👉 启用它

---

## 🎬 实际效果

显示效果如下：

```text
Hello everyone, welcome back.
大家好，欢迎回来。
```

👉 上面原文
👉 下面翻译

---

## ⚙️ 性能说明

当前默认配置：

```python
WhisperModel("tiny", device="cpu", compute_type="int8")
```

| 模式    | 延迟      | 准确率 |
| ----- | ------- | --- |
| tiny  | ⭐ 快（推荐） | ⭐⭐  |
| small | ⭐⭐      | ⭐⭐⭐ |

👉 如果你想更准：

```python
WhisperModel("small")
```

⚠️ 但延迟会变高

---

## 📦 打包为 exe（Windows）

```bash
pyinstaller --noconsole --onefile main_app.py
```

生成：

```text
dist/main_app.exe
```

双击即可运行 🎉

---

## ⚠️ 已知限制

❗ 依赖 Windows 的“立体声混音”
❗ 翻译需要联网
❗ Whisper 不是完全流式（存在轻微延迟）
❗ tiny 模型精度有限

---

## 🚀 后续优化方向

你可以继续升级这个项目：

* 🎨 字幕透明度调节
* 🔤 字体大小设置
* 🌐 多语言切换
* ⚡ 超低延迟（流式识别）
* 📱 GUI 设置界面
* 🤖 本地翻译模型（离线）

---

## 🧾 项目结构

```text
ai-subtitle-translator/
├── main_app.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

## 🧑‍💻 作者说明

这是一个基于语音识别的 AI 工具项目，适合作为：

* 🎓 课程设计
* 💼 项目作品集
* 🚀 GitHub 开源项目

---

## 📄 License

MIT License

