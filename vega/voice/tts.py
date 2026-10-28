"""Text-to-speech: neural voices via edge-tts (needs internet) with automatic fallback to the Windows SAPI voice.
Playback is on the Qt main thread (QMediaPlayer) so it can be stopped instantly for barge-in."""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import tempfile
import threading
import time
import uuid
from collections import deque

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

log = logging.getLogger(__name__)


def clean_text(t: str) -> str:
    t = re.sub(r"https?://\S+", "link", t)
    t = re.sub(r"[`*_#>~|]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(t: str, max_len: int = 280) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", t) if p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = max(p.rfind(", ", 0, max_len), p.rfind(" ", 0, max_len))
            cut = cut if cut > 40 else max_len
            out.append(p[:cut].strip(" ,"))
            p = p[cut:].strip(" ,")
        if out and len(out[-1]) < 25 and len(out[-1]) + len(p) < max_len:
            out[-1] += " " + p
        elif p:
            out.append(p)
    return out


class TTS(QObject):
    started = Signal()
    finished = Signal()
    error = Signal(str)
    _ready = Signal(str, int)
    _sapi_done = Signal(int)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_player_error)
        self._ready.connect(self._on_ready)
        self._sapi_done.connect(self._on_sentence_done)
        self._gen, self._pending, self._active = 0, 0, False
        self._playq: deque[str] = deque()
        self._current: str | None = None
        self._jobs: queue.Queue = queue.Queue()
        self._fallback_until = 0.0
        threading.Thread(target=self._worker, daemon=True, name="tts").start()

    @property
    def speaking(self) -> bool:
        return self._active

    # ---- public (main thread) ----
    def speak(self, text: str):
        sentences = split_sentences(clean_text(text))
        if not sentences:
            return
        self.audio.setVolume(max(0.0, min(1.0, self.settings.get("voice.volume", 85) / 100)))
        if not self._active:
            self._active = True
            self.started.emit()
        for s in sentences:
            self._pending += 1
            self._jobs.put((self._gen, s))

    def stop(self):
        self._gen += 1
        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass
        for p in list(self._playq):
            self._remove(p)
        self._playq.clear()
        self.player.stop()
        self._release_current()
        self._pending = 0
        if self._active:
            self._active = False
            self.finished.emit()

    # ---- worker thread ----
    def _use_sapi(self) -> bool:
        return self.settings.get("voice.engine", "edge") == "windows" or time.time() < self._fallback_until

    def _worker(self):
        while True:
            gen, text = self._jobs.get()
            if gen != self._gen:
                continue
            try:
                if self._use_sapi():
                    self._speak_sapi(text, gen)
                    self._sapi_done.emit(gen)
                else:
                    path = self._synth_edge(text)
                    if gen != self._gen:
                        self._remove(path)
                    else:
                        self._ready.emit(path, gen)
            except Exception as e:
                log.warning("TTS failed: %s", e)
                if not self._use_sapi():
                    self._fallback_until = time.time() + 120
                    self.error.emit("The neural voice isn't reachable (offline?). Using the Windows voice for now.")
                    try:
                        self._speak_sapi(text, gen)
                    except Exception as e2:
                        self.error.emit(f"I couldn't speak: {e2}")
                else:
                    self.error.emit(f"I couldn't speak: {e}")
                if gen == self._gen:
                    self._sapi_done.emit(gen)

    def _synth_edge(self, text: str) -> str:
        import edge_tts
        v = self.settings
        path = os.path.join(tempfile.gettempdir(), f"vega_{uuid.uuid4().hex}.mp3")
        comm = edge_tts.Communicate(text, v.get("voice.voice", "en-GB-RyanNeural"),
                                    rate=f"{int(v.get('voice.rate', 0)):+d}%", pitch=f"{int(v.get('voice.pitch', 0)):+d}Hz")
        asyncio.run(asyncio.wait_for(comm.save(path), 25))
        return path

    def _speak_sapi(self, text: str, gen: int):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Volume = int(self.settings.get("voice.volume", 85))
            voice.Rate = max(-10, min(10, int(self.settings.get("voice.rate", 0)) // 10))
            voice.Speak(text, 1)  # async
            while not voice.WaitUntilDone(100):
                if gen != self._gen:
                    voice.Speak("", 3)  # purge
                    break
        finally:
            pythoncom.CoUninitialize()

    # ---- main-thread playback ----
    @staticmethod
    def _remove(path: str | None):
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def _release_current(self):
        p, self._current = self._current, None
        self.player.setSource(QUrl())
        self._remove(p)

    def _on_ready(self, path: str, gen: int):
        if gen != self._gen:
            self._remove(path)
            return
        self._playq.append(path)
        self._maybe_play()

    def _maybe_play(self):
        if self._current is None and self._playq:
            self._current = self._playq.popleft()
            self.player.setSource(QUrl.fromLocalFile(self._current))
            self.player.play()

    def _on_status(self, status):
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia) and self._current:
            self._release_current()
            self._on_sentence_done(self._gen)
            self._maybe_play()

    def _on_player_error(self, err, msg):
        log.warning("player error: %s", msg)
        self.error.emit(f"Audio playback failed: {msg}")
        if self._current:
            self._release_current()
            self._on_sentence_done(self._gen)
            self._maybe_play()

    def _on_sentence_done(self, gen: int):
        if gen != self._gen:
            return
        self._pending = max(0, self._pending - 1)
        if self._pending == 0 and self._current is None and not self._playq and self._active:
            self._active = False
            self.finished.emit()
