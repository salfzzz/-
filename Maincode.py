import os
import json
import queue
import re
import sys
import threading
import time
from collections import OrderedDict
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import sounddevice as sd
from deep_translator import GoogleTranslator
from faster_whisper import WhisperModel

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


SAMPLE_RATE = 16000
CHANNELS = 2

CONFIG_PATH = Path(__file__).with_name("config.json")

DEFAULT_CONFIG = {
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
    "audio_device_index": None,
}


def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as file:
                saved_config = json.load(file)
            if isinstance(saved_config, dict):
                config.update(saved_config)
        except Exception as exc:
            print("读取 config.json 失败，将使用默认配置:", exc)
    return config


def save_config(config):
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("保存 config.json 失败:", exc)


CONFIG = load_config()


def env_value(name, fallback):
    return os.getenv(name, str(fallback))


MODEL_SIZE = env_value("SUBTITLE_MODEL", CONFIG["model_size"])
DEVICE = env_value("SUBTITLE_DEVICE", CONFIG["device"])
COMPUTE_TYPE = env_value("SUBTITLE_COMPUTE_TYPE", CONFIG["compute_type"])
TARGET_LANG = env_value("SUBTITLE_TARGET_LANG", CONFIG["target_lang"])

CHUNK_SECONDS = float(env_value("SUBTITLE_CHUNK_SECONDS", "0.1"))
WINDOW_SECONDS = float(env_value("SUBTITLE_WINDOW_SECONDS", "0.8"))
OVERLAP_SECONDS = float(env_value("SUBTITLE_OVERLAP_SECONDS", "0.3"))
SILENCE_RMS_THRESHOLD = float(env_value("SUBTITLE_SILENCE_RMS", "0.008"))

MIN_TEXT_LENGTH = int(env_value("SUBTITLE_MIN_TEXT_LENGTH", "12"))
STABLE_TEXT_DELAY = float(env_value("SUBTITLE_STABLE_TEXT_DELAY", "0.45"))
MAX_PENDING_SECONDS = float(env_value("SUBTITLE_MAX_PENDING_SECONDS", "1.3"))

BEAM_SIZE = int(env_value("SUBTITLE_BEAM_SIZE", "3"))
TRANSLATION_CACHE_LIMIT = int(env_value("SUBTITLE_TRANSLATION_CACHE_LIMIT", "128"))


audio_queue = queue.Queue(maxsize=30)


class SubtitleSignals(QObject):
    subtitle_changed = pyqtSignal(str, str, bool)
    status_changed = pyqtSignal(str)


def audio_callback(indata, frames, stream_time, status):
    if status:
        print(status)

    chunk = indata.copy()
    try:
        audio_queue.put_nowait(chunk)
    except queue.Full:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            pass
        audio_queue.put_nowait(chunk)


def list_audio_devices():
    print("\n可用输入音频设备:")
    print("-" * 72)
    devices = sd.query_devices()
    found_input = False
    for index, dev in enumerate(devices):
        max_channels = int(dev.get("max_input_channels", 0))
        if max_channels <= 0:
            continue
        found_input = True
        default_rate = dev.get("default_samplerate", "")
        print(
            f"[{index}] {dev['name']} | 输入通道: {max_channels} | 默认采样率: {default_rate}"
        )
    if not found_input:
        print("未发现输入设备。")
    print("-" * 72)
    print("如果自动检测失败，请把上面的设备编号写入 config.json 的 audio_device_index。")


def get_loopback_device():
    devices = sd.query_devices()
    configured_index = CONFIG.get("audio_device_index")
    if configured_index is not None:
        try:
            configured_index = int(configured_index)
            dev = devices[configured_index]
            if int(dev.get("max_input_channels", 0)) > 0:
                return configured_index
            print(f"config.json 中的 audio_device_index={configured_index} 不是输入设备。")
        except Exception as exc:
            print("config.json 中的 audio_device_index 无效:", exc)

    for index, dev in enumerate(devices):
        if int(dev.get("max_input_channels", 0)) <= 0:
            continue
        name = dev["name"].lower()
        if (
            "loopback" in name
            or "stereo mix" in name
            or "立体声混音" in dev["name"]
            or "what u hear" in name
            or "wave out" in name
        ):
            return index
    return None


def normalize_text(text):
    return " ".join(text.strip().split())


def text_signature(text):
    return re.sub(r"\W+", "", text.lower(), flags=re.UNICODE)


def is_repeated_text(text, previous):
    if not text or not previous:
        return False

    current_sig = text_signature(text)
    previous_sig = text_signature(previous)
    if not current_sig or not previous_sig:
        return False

    if current_sig == previous_sig:
        return True

    if current_sig in previous_sig or previous_sig in current_sig:
        length_delta = abs(len(current_sig) - len(previous_sig))
        return length_delta <= max(8, int(len(previous_sig) * 0.25))

    return SequenceMatcher(None, current_sig, previous_sig).ratio() >= 0.9


def looks_unfinished(text):
    if not text:
        return False
    if len(text_signature(text)) < MIN_TEXT_LENGTH:
        return True
    return text[-1] not in ".!?。！？"


class TextStabilizer:
    def __init__(self):
        self.pending_text = ""
        self.pending_since = 0.0
        self.last_emitted = ""

    def accept(self, text):
        now = time.monotonic()
        text = normalize_text(text)
        if not text or is_repeated_text(text, self.last_emitted):
            return None

        if not self.pending_text:
            self.pending_text = text
            self.pending_since = now
            if looks_unfinished(text):
                return None
            return self._emit()

        if is_repeated_text(text, self.pending_text):
            if len(text_signature(text)) > len(text_signature(self.pending_text)):
                self.pending_text = text
            if now - self.pending_since >= STABLE_TEXT_DELAY and not looks_unfinished(self.pending_text):
                return self._emit()
            if now - self.pending_since >= MAX_PENDING_SECONDS:
                return self._emit()
            return None

        if self._is_extension(text, self.pending_text):
            self.pending_text = text
            if now - self.pending_since >= STABLE_TEXT_DELAY and not looks_unfinished(text):
                return self._emit()
            if now - self.pending_since >= MAX_PENDING_SECONDS:
                return self._emit()
            return None

        previous = self.pending_text
        if previous and not looks_unfinished(previous):
            emitted = self._emit_text(previous)
            self.pending_text = text
            self.pending_since = now
            return emitted

        self.pending_text = text
        self.pending_since = now
        return None

    def flush(self):
        if self.pending_text:
            return self._emit()
        return None

    def flush_if_due(self):
        if self.pending_text and time.monotonic() - self.pending_since >= MAX_PENDING_SECONDS:
            return self._emit()
        return None

    def _is_extension(self, text, previous):
        current_sig = text_signature(text)
        previous_sig = text_signature(previous)
        if not current_sig or not previous_sig:
            return False
        return current_sig.startswith(previous_sig) or previous_sig in current_sig

    def _emit(self):
        return self._emit_text(self.pending_text)

    def _emit_text(self, text):
        text = normalize_text(text)
        if not text or is_repeated_text(text, self.last_emitted):
            return None
        self.last_emitted = text
        self.pending_text = ""
        self.pending_since = 0.0
        return text


def audio_to_mono(audio):
    if len(audio.shape) > 1:
        return np.mean(audio, axis=1).astype(np.float32)
    return audio.astype(np.float32)


def is_silent(audio):
    if audio.size == 0:
        return True
    rms = float(np.sqrt(np.mean(np.square(audio))))
    return rms < SILENCE_RMS_THRESHOLD


def put_latest(target_queue, item):
    try:
        target_queue.put_nowait(item)
    except queue.Full:
        try:
            target_queue.get_nowait()
        except queue.Empty:
            pass
        target_queue.put_nowait(item)


class TranslationCache:
    def __init__(self, limit):
        self.limit = limit
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def get(self, text):
        with self._lock:
            value = self._items.get(text)
            if value is not None:
                self._items.move_to_end(text)
            return value

    def set(self, text, translated):
        with self._lock:
            self._items[text] = translated
            self._items.move_to_end(text)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)


class SubtitleWindow(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)

        self.original_label = QLabel("等待视频声音...", self)
        self.translation_label = QLabel("", self)

        for label in (self.original_label, self.translation_label):
            label.setWordWrap(True)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.original_label)
        layout.addWidget(self.translation_label)

        self.setFixedWidth(int(self.config["window_width"]))
        self.move(int(self.config["window_x"]), int(self.config["window_y"]))
        self._drag_offset = None
        self.apply_visual_settings()

    def update_subtitle(self, original, translated="", translating=False):
        self.original_label.setText(original or "等待视频声音...")

        if translated:
            self.translation_label.setText(translated)
        elif translating:
            self.translation_label.setText("翻译中...")
        else:
            self.translation_label.setText("")

        self.adjustSize()

    def apply_visual_settings(self):
        original_size = int(self.config["font_size_original"])
        translation_size = int(self.config["font_size_translation"])
        opacity = min(1.0, max(0.35, float(self.config["opacity"])))
        self.config["opacity"] = opacity
        self.setWindowOpacity(opacity)

        self.original_label.setStyleSheet(
            f"color: #f8fafc; font-size: {original_size}px; "
            "background-color: rgba(8,12,20,178); padding: 12px 16px 4px 16px; "
            "border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        self.translation_label.setStyleSheet(
            f"color: #fef3c7; font-size: {translation_size}px; font-weight: 600; "
            "background-color: rgba(8,12,20,178); padding: 4px 16px 12px 16px; "
            "border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
        )
        self.adjustSize()

    def increase_font(self):
        self.config["font_size_original"] = min(42, int(self.config["font_size_original"]) + 1)
        self.config["font_size_translation"] = min(48, int(self.config["font_size_translation"]) + 1)
        self.apply_visual_settings()

    def decrease_font(self):
        self.config["font_size_original"] = max(12, int(self.config["font_size_original"]) - 1)
        self.config["font_size_translation"] = max(14, int(self.config["font_size_translation"]) - 1)
        self.apply_visual_settings()

    def increase_opacity(self):
        self.config["opacity"] = min(1.0, float(self.config["opacity"]) + 0.05)
        self.apply_visual_settings()

    def decrease_opacity(self):
        self.config["opacity"] = max(0.35, float(self.config["opacity"]) - 0.05)
        self.apply_visual_settings()

    def sync_window_config(self):
        self.config["window_width"] = int(self.width())
        self.config["window_x"] = int(self.x())
        self.config["window_y"] = int(self.y())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return

        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                self.increase_font()
                return
            if event.key() in (Qt.Key_Minus, Qt.Key_Underscore):
                self.decrease_font()
                return
            if event.key() == Qt.Key_Up:
                self.increase_opacity()
                return
            if event.key() == Qt.Key_Down:
                self.decrease_opacity()
                return

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self.sync_window_config()
        event.accept()


class SubtitlePipeline:
    def __init__(self, signals, config):
        self.signals = signals
        self.config = config
        self.stop_event = threading.Event()
        self.recognition_queue = queue.Queue(maxsize=2)
        self.translation_queue = queue.Queue(maxsize=2)
        self.translation_cache = TranslationCache(TRANSLATION_CACHE_LIMIT)
        self.text_stabilizer = TextStabilizer()
        self.last_recognized = ""
        self.last_translated = ""
        self.stream = None
        self.threads = []
        self.model = None
        self.translator = GoogleTranslator(source="auto", target=TARGET_LANG)

    def start(self):
        list_audio_devices()
        device = get_loopback_device()
        if device is None:
            message = "未找到系统音频设备，请查看控制台设备列表，并在 config.json 中设置 audio_device_index"
            print(message)
            self.signals.status_changed.emit(message)
            return

        device_name = sd.query_devices(device)["name"]
        print("使用音频设备:", device_name)
        self.config["audio_device_index"] = int(device)

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=audio_callback,
            device=device,
            blocksize=max(1, int(SAMPLE_RATE * CHUNK_SECONDS)),
        )
        self.stream.start()

        self.threads = [
            threading.Thread(target=self._audio_worker, name="audio-window", daemon=True),
            threading.Thread(target=self._recognition_worker, name="whisper", daemon=True),
            threading.Thread(target=self._translation_worker, name="translator", daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()

    def _audio_worker(self):
        window_samples = max(1, int(WINDOW_SECONDS * SAMPLE_RATE))
        overlap_samples = max(0, int(OVERLAP_SECONDS * SAMPLE_RATE))
        step_samples = max(1, window_samples - overlap_samples)
        audio_buffer = np.empty(0, dtype=np.float32)
        samples_since_emit = 0

        while not self.stop_event.is_set():
            try:
                chunk = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            mono = audio_to_mono(chunk)
            audio_buffer = np.concatenate((audio_buffer, mono))

            if audio_buffer.size > window_samples:
                audio_buffer = audio_buffer[-window_samples:]

            samples_since_emit += mono.size
            if audio_buffer.size < window_samples or samples_since_emit < step_samples:
                continue

            samples_since_emit = 0
            if is_silent(audio_buffer):
                continue

            put_latest(self.recognition_queue, audio_buffer.copy())

    def _recognition_worker(self):
        self.signals.status_changed.emit("正在加载识别模型...")
        try:
            self.model = WhisperModel(
                MODEL_SIZE,
                device=DEVICE,
                compute_type=COMPUTE_TYPE,
            )
        except Exception as exc:
            message = f"启动失败：识别模型加载失败：{exc}"
            print(message)
            self.signals.status_changed.emit(message)
            self.stop_event.set()
            return

        print(
            "字幕配置:",
            f"model={MODEL_SIZE}",
            f"device={DEVICE}",
            f"compute={COMPUTE_TYPE}",
            f"target={TARGET_LANG}",
        )
        self.signals.status_changed.emit("等待视频声音...")

        while not self.stop_event.is_set():
            try:
                audio = self.recognition_queue.get(timeout=0.1)
            except queue.Empty:
                stable_text = self.text_stabilizer.flush_if_due()
                if stable_text:
                    self._publish_recognized_text(stable_text)
                continue

            try:
                segments, _ = self.model.transcribe(
                    audio,
                    beam_size=BEAM_SIZE,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                text = normalize_text("".join(segment.text for segment in segments))
            except Exception as exc:
                print("识别失败:", exc)
                continue

            if not text:
                continue

            stable_text = self.text_stabilizer.accept(text)
            if stable_text:
                self._publish_recognized_text(stable_text)

    def _publish_recognized_text(self, text):
        if is_repeated_text(text, self.last_recognized):
            return
        self.last_recognized = text
        self.signals.subtitle_changed.emit(text, "", True)
        put_latest(self.translation_queue, text)
        print("\n原文:", text)

    def _translation_worker(self):
        while not self.stop_event.is_set():
            try:
                text = self.translation_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            cached = self.translation_cache.get(text)
            if cached is not None:
                self.last_translated = cached
                if text == self.last_recognized:
                    self.signals.subtitle_changed.emit(text, cached, False)
                print("翻译:", cached)
                continue

            translated = self._translate_with_retry(text)
            if translated is None:
                if text == self.last_recognized:
                    fallback = self.last_translated or "翻译失败，请检查网络"
                    self.signals.subtitle_changed.emit(text, fallback, False)
                continue

            self.translation_cache.set(text, translated)
            self.last_translated = translated
            if text == self.last_recognized:
                self.signals.subtitle_changed.emit(text, translated, False)
            print("翻译:", translated)

    def _translate_with_retry(self, text):
        for attempt in range(2):
            try:
                translated = self.translator.translate(text)
                if translated:
                    return translated
            except Exception as exc:
                print(f"翻译失败，第 {attempt + 1} 次:", repr(exc))
                if attempt == 0 and text == self.last_recognized:
                    self.signals.subtitle_changed.emit(text, "翻译失败，正在重试...", False)
                time.sleep(0.3)
        print("网络翻译失败超过 2 次，原文:", text)
        if text == self.last_recognized:
            self.signals.subtitle_changed.emit(text, "翻译失败，请检查网络", False)
        return None


class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.config = CONFIG
        self.window = SubtitleWindow(self.config)
        self.window.show()
        self._saved = False

        self.signals = SubtitleSignals()
        self.signals.subtitle_changed.connect(self.window.update_subtitle)
        self.signals.status_changed.connect(lambda text: self.window.update_subtitle(text))
        self.app.aboutToQuit.connect(self.save_current_config)

        self.pipeline = None
        try:
            self.pipeline = SubtitlePipeline(self.signals, self.config)
            self.pipeline.start()
        except Exception as exc:
            message = f"启动失败：{exc}"
            print(message)
            self.window.update_subtitle(message)

    def run(self):
        exit_code = self.app.exec_()
        if self.pipeline is not None:
            self.pipeline.stop()
        self.save_current_config()
        sys.exit(exit_code)

    def save_current_config(self):
        if self._saved:
            return
        self.window.sync_window_config()
        self.config["model_size"] = MODEL_SIZE
        self.config["device"] = DEVICE
        self.config["compute_type"] = COMPUTE_TYPE
        self.config["target_lang"] = TARGET_LANG
        save_config(self.config)
        self._saved = True


if __name__ == "__main__":
    App().run()
