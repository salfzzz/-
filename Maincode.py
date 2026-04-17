
import sys
import queue
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator

from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer

# ======================
# 音频队列
# ======================
audio_queue = queue.Queue()


def audio_callback(indata, frames, time, status):
    if status:
        print(status)
    audio_queue.put(indata.copy())


# ======================
# 获取系统音频设备（关键）
# ======================
def get_loopback_device():
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if 'loopback' in dev['name'].lower() or '立体声混音' in dev['name']:
            return i
    return None


# ======================
# 悬浮字幕窗口
# ======================
class SubtitleWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

        self.label = QLabel("等待视频声音...", self)
        self.label.setStyleSheet(
            "color: white; font-size: 24px; background-color: rgba(0,0,0,160); padding: 12px; border-radius: 12px;"
        )

        self.resize(900, 120)
        self.move(300, 800)

    def update_text(self, text):
        self.label.setText(text)
        self.label.adjustSize()


# ======================
# Whisper（更快）
# ======================
model = WhisperModel(
    "tiny",
    device="cpu",          # 🔥关键：强制CPU
    compute_type="int8"
)


def transcribe(audio):
    segments, _ = model.transcribe(audio, beam_size=1)
    return "".join([seg.text for seg in segments]).strip()


def translate(text):
    try:
        return GoogleTranslator(source='auto', target='zh-CN').translate(text)
    except:
        return text


# ======================
# 主程序
# ======================
class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = SubtitleWindow()
        self.window.show()
        self.text_buffer = ""
        self.last_time = 0
        self.buffer = []

        self.timer = QTimer()
        self.timer.timeout.connect(self.process_audio)
        self.timer.start(700)  # 更低延迟

        # 🎧 关键：使用系统声音
        device = get_loopback_device()

        if device is None:
            print("❌ 没找到系统音频设备，请开启【立体声混音】")
            sys.exit(1)

        print("✅ 使用音频设备:", sd.query_devices(device)['name'])

        self.stream = sd.InputStream(
            samplerate=16000,
            channels=2,
            dtype='float32',
            callback=audio_callback,
            device=device
        )

        self.stream.start()

    def process_audio(self):
        while not audio_queue.empty():
            self.buffer.append(audio_queue.get())

        if len(self.buffer) < 2:
            return

        audio = np.concatenate(self.buffer, axis=0)
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)
        self.buffer = []

        text = transcribe(audio)

        if text:
            translated = translate(text)
            self.window.update_text(translated)

            print("\n🗣 原文:", text)
            print("🌏 翻译:", translated)

    def run(self):
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    App().run()


# ======================
# ⚠️ 必做设置（Windows）
# ======================
# 1. 右键音量图标 → 声音设置
# 2. 输入设备 → 开启【立体声混音】
# 3. 如果没有：右键“显示禁用设备”→ 启用


# ======================
# 打包
# ======================
# pyinstaller --noconsole --onefile main_app.py