# 🎧 AI 实时悬浮字幕翻译工具

一个基于 Python 的桌面工具，可以**实时监听 Windows 系统正在播放的视频声音**，将语音内容通过 `faster-whisper` 自动识别，再用 `deep-translator` 翻译成中文，并以悬浮字幕窗口显示在屏幕上。

---

## ✨ 功能特性

🚀 **实时语音识别**

* 使用 `faster-whisper`
* 默认模型为 `base`，兼顾准确率和演示速度
* 支持英文 / 日文等多语言识别

🌍 **自动翻译**

* 自动检测原文语言
* 默认翻译为简体中文
* 基于 Google 翻译接口，需要联网

🖥️ **悬浮字幕窗口**

* 永远置顶
* 半透明双行字幕：上方原文，下方中文
* 支持鼠标拖动
* 支持字体大小、透明度快捷调整

⚡ **低延迟与稳定优化**

* 后台线程处理音频、识别、翻译，避免 UI 卡顿
* 滚动音频窗口 + 静音检测
* 文本稳定器减少重复翻译、半句话翻译和碎片化字幕
* 翻译失败会提示重试，不会把英文原文伪装成译文

---

## 📦 安装依赖

建议使用虚拟环境：

```bash
pip install -r requirements.txt
```

依赖包括：

```text
numpy
sounddevice
faster-whisper
deep-translator
PyQt5
pyinstaller
```

---

## ▶️ 运行项目

```bash
python Maincode.py
```

运行后：

* ✅ 控制台会打印可用输入音频设备列表
* ✅ 屏幕会出现悬浮字幕框
* ✅ 播放英文 / 日文视频时，原文会先出现，中文翻译随后补齐

---

## ⚙️ config.json 配置说明

程序启动时会优先读取同目录下的 `config.json`。如果文件不存在，会使用默认配置；程序退出时会保存窗口位置、字体大小、透明度和当前音频设备编号。

示例：

```json
{
  "model_size": "base",
  "device": "cpu",
  "compute_type": "int8",
  "target_lang": "zh-CN",
  "font_size_original": 21,
  "font_size_translation": 25,
  "opacity": 0.88,
  "window_width": 900,
  "window_x": 300,
  "window_y": 760,
  "audio_device_index": null
}
```

常用字段：

| 字段 | 说明 |
| --- | --- |
| `model_size` | Whisper 模型，推荐 `base`；低配电脑可改为 `tiny` |
| `device` | 默认 `cpu` |
| `compute_type` | 默认 `int8`，适合 CPU |
| `target_lang` | 翻译目标语言，默认 `zh-CN` |
| `font_size_original` | 原文字体大小 |
| `font_size_translation` | 译文字体大小 |
| `opacity` | 窗口透明度，范围建议 `0.35 ~ 1.0` |
| `window_width` | 字幕窗口宽度 |
| `window_x` / `window_y` | 字幕窗口位置 |
| `audio_device_index` | 手动指定系统音频输入设备编号 |

也可以用环境变量临时覆盖部分配置：

```bash
set SUBTITLE_MODEL=tiny
python Maincode.py
```

---

## 🎧 音频设备设置

本项目需要能录到“系统正在播放的声音”。Windows 上常见方案是启用：

```text
立体声混音 / Stereo Mix
```

### 如何查看音频设备编号

直接运行程序：

```bash
python Maincode.py
```

控制台会打印类似：

```text
可用输入音频设备:
[1] Microphone Array | 输入通道: 2
[3] Stereo Mix | 输入通道: 2
```

如果程序没有自动找到系统声音设备，可以把编号写入 `config.json`：

```json
{
  "audio_device_index": 3
}
```

### 找不到“立体声混音”怎么办

1. 右键任务栏音量图标 🔊
2. 打开 **声音设置**
3. 进入 **更多声音设置**
4. 切换到 **录制**
5. 右键空白区域，勾选 **显示禁用设备**
6. 找到 **立体声混音 / Stereo Mix** 并启用
7. 重新运行 `python Maincode.py`

如果声卡驱动不提供“立体声混音”，可以使用带 loopback 能力的虚拟声卡或录音设备，并在 `config.json` 中手动设置 `audio_device_index`。

---

## ⌨️ 快捷键

悬浮字幕窗口获得焦点后可使用：

| 快捷键 | 功能 |
| --- | --- |
| `Esc` | 退出程序并保存当前配置 |
| `Ctrl + +` | 增大原文和译文字体 |
| `Ctrl + -` | 减小原文和译文字体 |
| `Ctrl + ↑` | 增加字幕窗口透明度 |
| `Ctrl + ↓` | 降低字幕窗口透明度 |

鼠标左键拖动字幕窗口后，退出时会保存新位置。

---

## 🎬 显示效果

```text
Hello everyone, welcome back.
大家好，欢迎回来。
```

上方显示识别原文，下方显示中文翻译。

---

## ⚙️ 性能说明

当前默认配置：

```python
WhisperModel("base", device="cpu", compute_type="int8")
```

| 模型 | 延迟 | 准确率 | 建议 |
| --- | --- | --- | --- |
| `tiny` | 更低 | 一般 | 低配电脑或演示低延迟 |
| `base` | 平衡 | 较好 | 默认推荐 |
| `small` | 较高 | 更好 | 对准确率要求更高 |

想降低延迟可以在 `config.json` 中把 `model_size` 改为 `tiny`。想提高准确率可以改为 `small`，但加载和识别会更慢。

---

## 📦 打包为 exe（Windows）

```bash
pyinstaller --noconsole --onefile Maincode.py
```

生成文件：

```text
dist/Maincode.exe
```

---

## ❓ FAQ

### Q: 程序提示“未找到系统音频设备”怎么办？

先看控制台打印的输入设备列表。如果有类似 `Stereo Mix`、`立体声混音`、`loopback` 的设备，把对应编号写入 `config.json` 的 `audio_device_index`。

### Q: 为什么有时字幕不是逐字实时出现？

Whisper 不是完全流式识别。程序会用短音频窗口和文本稳定器减少碎片化，所以译文通常会比原文稍晚一点出现。

### Q: 为什么翻译偶尔失败？

`deep-translator` 使用网络翻译服务，网络不稳定或服务限流时可能失败。程序会重试，失败超过 2 次会在字幕窗口和控制台提示。

### Q: 如何让字幕更快？

把 `config.json` 中的 `model_size` 改为 `tiny`，或通过环境变量运行：

```bash
set SUBTITLE_MODEL=tiny
python Maincode.py
```

### Q: 如何让字幕更准确？

把 `model_size` 改为 `small`，但延迟会增加。

---

## 🧾 项目结构

```text
AI-Subtitle-Translator/
├── Maincode.py
├── README.md
├── requirements.txt
└── config.json
```

---

## ⚠️ 已知限制

* ❗ 需要 Windows 上可录到系统声音的输入设备
* ❗ 翻译需要联网
* ❗ Whisper 并非真正逐字流式识别
* ❗ CPU 上使用更大模型会增加延迟
