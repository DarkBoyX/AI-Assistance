"""Orchestrates mic -> STT -> agent(tools) -> TTS and publishes state to the UI."""
from __future__ import annotations

import difflib
import logging
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot

from . import tools
from .ai.agent import Agent
from .ai.providers import ProviderError
from .reminders import ReminderScheduler
from .tools.base import ToolContext
from .voice.audio_in import Mic
from .voice.stt import SttError, Transcriber
from .voice.tts import TTS

log = logging.getLogger(__name__)
YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "proceed", "okay", "ok", "affirmative", "allow",
       "do it", "go ahead", "please do"}
NO = {"no", "nope", "nah", "cancel", "stop", "deny", "negative", "abort", "don't", "do not", "never mind"}


def parse_yes_no(text: str):
    t = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    if not t or len(t.split()) > 5:
        return None
    if t in YES or t.split()[0] in YES or t.startswith(("go ahead", "do it")):
        return True
    if t in NO or t.split()[0] in NO or t.startswith(("do not", "never mind")):
        return False
    return None


class _Confirm:
    def __init__(self, question, tool):
        self.question, self.tool, self.event, self.result = question, tool, threading.Event(), False


class Controller(QObject):
    state_changed = Signal(str)
    level = Signal(float)
    message = Signal(str, str)      # role, text
    tool_event = Signal(str)
    error = Signal(str)
    hint = Signal(str)
    confirm_request = Signal(str, str)
    confirm_closed = Signal()
    notify = Signal(str, str)
    listening_changed = Signal(bool)
    _say = Signal(str)
    _turn_done = Signal()
    _transcribed = Signal(str)
    _due = Signal(str)

    def __init__(self, settings, storage):
        super().__init__()
        self.settings, self.storage = settings, storage
        self.registry = tools.load_all()
        self.agent = Agent(settings, storage, self.registry)
        self.tts = TTS(settings)
        self.mic = Mic(settings)
        self.stt = Transcriber(settings, on_status=lambda s: self.hint.emit(s))
        self.reminders = ReminderScheduler(storage, lambda t: self._due.emit(t))
        self._services = {"storage": storage, "reminders": self.reminders}
        self._turns: queue.Queue = queue.Queue()
        self._cancel: threading.Event | None = None
        self._busy = self._transcribing = 0
        self._pending: _Confirm | None = None
        self._last_interaction = 0.0
        self._state = "idle"
        self._stt_pool = ThreadPoolExecutor(1, thread_name_prefix="stt")
        self._stopping = False

        self.tts.started.connect(lambda: self._speaking(True))
        self.tts.finished.connect(lambda: self._speaking(False))
        self.tts.error.connect(self.error)
        self.mic.level.connect(self.level)
        self.mic.error.connect(self._mic_error)
        self.mic.barge_in.connect(self.interrupt)
        self.mic.utterance.connect(self._on_utterance)
        self._say.connect(self._on_say)
        self._turn_done.connect(self._on_turn_done)
        self._transcribed.connect(self._on_transcribed)
        self._due.connect(self._on_reminder)
        threading.Thread(target=self._worker, daemon=True, name="agent").start()

    # ---------- state ----------
    def _refresh(self):
        s = ("speaking" if self.tts.speaking else "thinking" if (self._busy or self._transcribing)
             else "listening" if self.mic.running else "idle")
        if s != self._state:
            self._state = s
            self.state_changed.emit(s)

    def _speaking(self, on: bool):
        self.mic.assistant_speaking = on
        if not on:
            self._last_interaction = time.time()
        self._refresh()

    @property
    def listening(self) -> bool:
        return self.mic.running

    # ---------- mic ----------
    def start_listening(self):
        if not self.mic.start():
            self._refresh()
            return
        self.listening_changed.emit(True)
        self.hint.emit("")
        threading.Thread(target=self._preload_stt, daemon=True).start()
        self._refresh()

    def _preload_stt(self):
        try:
            self.stt.ensure_loaded()
        except SttError as e:
            self.error.emit(str(e))

    def stop_listening(self):
        self.mic.stop()
        self.listening_changed.emit(False)
        self._refresh()

    def toggle_listening(self):
        self.stop_listening() if self.listening else self.start_listening()

    def _mic_error(self, msg):
        self.error.emit(msg)
        self.listening_changed.emit(False)
        self._refresh()

    @Slot(object)
    def _on_utterance(self, audio):
        self._transcribing += 1
        self.hint.emit("Transcribing...")
        self._refresh()

        def job():
            text = ""
            try:
                text = self.stt.transcribe(audio)
            except SttError as e:
                self.error.emit(str(e))
            except Exception as e:
                log.exception("stt")
                self.error.emit(f"Speech recognition failed: {e}")
            self._transcribed.emit(text)
        self._stt_pool.submit(job)

    @Slot(str)
    def _on_transcribed(self, text: str):
        self._transcribing = max(0, self._transcribing - 1)
        self.hint.emit("")
        self._refresh()
        text = self._apply_wake_word(text)
        if text:
            self.submit_text(text)

    def _apply_wake_word(self, text: str) -> str:
        text = text.strip()
        if not text or not self.settings.get("mic.wake_word", False):
            return text
        if self._pending or time.time() - self._last_interaction < float(self.settings.get("mic.wake_window_s", 45)):
            return text
        name = self.settings.name.lower()
        words = text.split()
        for i, w in enumerate(words[:4]):
            if difflib.SequenceMatcher(None, re.sub(r"\W", "", w.lower()), name).ratio() >= 0.75:
                return " ".join(words[i + 1:]).strip(" ,.!") or ""
        self.hint.emit(f"Say “{self.settings.name}” first...")
        return ""

    @Slot()
    def interrupt(self):
        """User started talking over the assistant (or pressed Stop)."""
        self.tts.stop()
        if self._cancel and self._pending is None:  # don't cancel a task that is waiting for yes/no
            self._cancel.set()

    # ---------- turns ----------
    @Slot(str)
    def submit_text(self, text: str):
        text = text.strip()
        if not text:
            return
        if self._pending is not None:
            v = parse_yes_no(text)
            if v is None:
                self.hint.emit("Waiting for your confirmation - say yes or no.")
            else:
                self.resolve_confirm(v)
            return
        self.interrupt()
        self._last_interaction = time.time()
        self.storage.add_message("user", text)
        self.message.emit("user", text)
        cancel = threading.Event()
        self._cancel = cancel
        self._busy += 1
        self._turns.put((text, cancel))
        self._refresh()

    def _worker(self):
        while True:
            item = self._turns.get()
            if item is None:
                return
            _, cancel = item
            try:
                ctx = ToolContext(self.settings, self._confirm_from_tool, cancel, self._services)
                history = self.storage.recent(int(self.settings.get("ai.context_messages", 24)))
                self.agent.run_turn(history, ctx, cancel, lambda t: self._say_cb(t, cancel), self._tool_cb)
            except ProviderError as e:
                if not cancel.is_set():
                    self.error.emit(str(e))
            except Exception as e:
                log.exception("turn failed")
                self.error.emit(f"Something went wrong: {e}")
            finally:
                self._turn_done.emit()

    def _say_cb(self, text, cancel):
        if cancel.is_set():
            return
        self.storage.add_message("assistant", text)
        self._say.emit(text)

    @Slot(str)
    def _on_say(self, text):
        self.message.emit("assistant", text)
        if self.settings.get("voice.speak_responses", True):
            self.tts.speak(text)
            self._refresh()

    def _tool_cb(self, name, args, result):
        short = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args or {}).items())
        self.tool_event.emit(f"{name}({short}) -> {result.splitlines()[0][:110] if result else ''}")

    @Slot()
    def _on_turn_done(self):
        self._busy = max(0, self._busy - 1)
        self._refresh()

    # ---------- confirmation ----------
    def _confirm_from_tool(self, question: str, tool: str) -> bool:
        req = _Confirm(question, tool)
        self._pending = req
        self.confirm_request.emit(question, tool)
        got = req.event.wait(120)
        self._pending = None
        self.confirm_closed.emit()
        return req.result if got else False

    @Slot(bool)
    def resolve_confirm(self, allowed: bool):
        req = self._pending
        if req and not req.event.is_set():
            req.result = allowed
            req.event.set()
            self.confirm_closed.emit()
            self.tts.stop()

    def speak(self, text: str):
        self.tts.speak(text)
        self._refresh()

    # ---------- reminders ----------
    @Slot(str)
    def _on_reminder(self, text: str):
        self.message.emit("assistant", f"Reminder: {text}")
        self.notify.emit("Reminder", text)
        self.tts.speak(f"Reminder: {text}")
        self._refresh()

    # ---------- lifecycle ----------
    def start(self, greet: bool = True):
        if self.settings.get("mic.continuous", True):
            self.start_listening()
        if greet and self.settings.get("voice.speak_responses", True):
            who = self.settings.get("assistant.user_name", "").strip()
            self.speak(f"{self.settings.name} online{', ' + who if who else ''}. How can I help?")

    def clear_history(self):
        self.storage.clear_messages()

    def shutdown(self):
        self.mic.stop()
        self.tts.stop()
        if self._cancel:
            self._cancel.set()
        if self._pending:
            self.resolve_confirm(False)
        self.reminders.stop()
        self._turns.put(None)
        self._stt_pool.shutdown(wait=False, cancel_futures=True)
