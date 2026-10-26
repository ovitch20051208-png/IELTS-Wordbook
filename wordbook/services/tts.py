"""SAPI objects belong exclusively to the COM worker thread, never the UI thread."""
from dataclasses import dataclass
import locale
import queue
import sys
import threading

from PySide6.QtCore import QObject, Signal

VOICE_HELP = ("添加英语语音：Windows 设置 → 时间和语言 → 语言和区域 → 添加 English (United Kingdom)，"
              "在语言选项中安装“语音”，然后重启本软件。此处列出 SAPI5 可访问的本机语音；"
              "部分仅用于讲述人的自然语音不支持 SAPI5。没有英式语音时会明确标示实际语言。")


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    languages: tuple[str, ...]

    @property
    def label(self):
        return f"{self.name} · {', '.join(self.languages) or '语言未知'}"


def preferred_voice(voices):
    for prefix in ("en-GB", "en"):
        for voice in voices:
            if any(lang == prefix or lang.startswith(prefix + "-") for lang in voice.languages):
                return voice.id
    return ""


class SapiBackend:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("本地 SAPI5 朗读仅在 Windows 上提供。")
        import pythoncom
        import win32com.client.dynamic
        self.com = pythoncom
        self.com.CoInitialize()
        try:
            self.engine = win32com.client.dynamic.Dispatch("SAPI.SpVoice")
            tokens = self.engine.GetVoices()
            self.tokens = {tokens.Item(i).Id: tokens.Item(i) for i in range(tokens.Count)}
        except Exception:
            self.com.CoUninitialize()
            raise

    def voices(self):
        result = []
        for key, token in self.tokens.items():
            codes = []
            try:
                for code in token.GetAttribute("Language").split(";"):
                    value = locale.windows_locale.get(int(code, 16), "")
                    if value:
                        codes.append(value.replace("_", "-"))
            except Exception:
                # An individual voice without language metadata must not disable TTS.
                codes = []
            result.append(Voice(key, token.GetDescription(), tuple(codes)))
        return result

    def speak(self, text, voice_id, speed, repeat):
        self.stop()
        self.engine.Voice = self.tokens[voice_id]
        # SAPI rate uses engine-specific steps. 0.8x is an approximate slow preset.
        self.engine.Rate = -2 if speed < 0.95 else 0
        for _ in range(repeat):
            self.engine.Speak(text, 1 | 16)  # async + SVSFIsNotXML: treat imported text as plain text

    def stop(self):
        self.engine.Speak("", 1 | 2 | 16)  # async + purge

    def close(self):
        try:
            self.stop()
        finally:
            self.tokens.clear()
            self.engine = None
            self.com.CoUninitialize()


class SpeechService(QObject):
    voices_changed = Signal(object)
    error = Signal(str)
    message = Signal(str)

    def __init__(self, parent=None, backend_factory=SapiBackend):
        super().__init__(parent)
        self.voices = []
        self.voice_id = ""
        self.speed = 1.0
        self.repeat = 1
        self.available = False
        self.last_error = "正在检测 Windows 本地语音…"
        self._queue = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._run, args=(backend_factory,), daemon=True, name="SAPI5-worker")
        self._thread.start()

    def _run(self, factory):
        backend = None
        try:
            backend = factory()
            voices = backend.voices()
            self.voices = voices
            self.voice_id = preferred_voice(voices)
            self.available = bool(voices)
            self.last_error = "" if self.voice_id else "未检测到可用英语语音。请在设置中查看语音列表和安装说明。"
            self.voices_changed.emit(voices)
            if self.last_error:
                self.error.emit(self.last_error)
            while True:
                command = self._queue.get()
                # Coalesce pending commands: rapid clicks only play the newest request.
                while not self._queue.empty() and command[0] != "close":
                    command = self._queue.get()
                if command[0] == "close":
                    break
                try:
                    if command[0] == "stop":
                        backend.stop()
                    else:
                        backend.speak(*command[1:])
                        self.message.emit("正在使用本机语音朗读")
                except Exception as exc:
                    self.last_error = f"朗读失败：{exc}。词卡学习仍可继续。"
                    self.error.emit(self.last_error)
        except Exception as exc:
            self.available = False
            self.last_error = f"本地朗读服务不可用：{exc}。词卡学习仍可继续。"
            self.error.emit(self.last_error)
            self.voices_changed.emit([])
        finally:
            if backend:
                try:
                    backend.close()
                except Exception:
                    pass

    def speak(self, text: str):
        text = text.strip()
        if not text:
            self.error.emit("没有可朗读的英文内容。")
            return False
        if not self.available or not self.voice_id or self._closed:
            self.error.emit(self.last_error or "请在设置中选择可用的英语发音人。")
            return False
        self._queue.put(("speak", text, self.voice_id, self.speed, self.repeat))
        return True

    def stop(self):
        if not self._closed:
            self._queue.put(("stop",))

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._queue.put(("close",))
        self._thread.join(timeout=3)
