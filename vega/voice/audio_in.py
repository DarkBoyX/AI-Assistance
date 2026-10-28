"""Microphone capture with adaptive voice-activity detection and barge-in."""
from __future__ import annotations

import logging
import queue
import threading
from collections import deque

import numpy as np
from PySide6.QtCore import QObject, Signal

RATE = 16000
FRAME = 480  # 30 ms
FRAME_MS = 30
log = logging.getLogger(__name__)


class Segmenter:
    """Pure-python VAD/utterance splitter. Feed 30 ms int16 frames; returns a list of events:
    ('level', float 0..1) ('start',) ('barge',) ('utterance', float32 array)."""

    def __init__(self, sensitivity: int = 5, silence_ms: int = 800, max_seconds: float = 30.0):
        self.sensitivity, self.silence_ms, self.max_frames = sensitivity, silence_ms, int(max_seconds * 1000 / FRAME_MS)
        self.noise = 0.004
        self.in_speech = False
        self.run = 0          # consecutive voiced frames before speech starts
        self.silence = 0
        self.voiced = 0
        self.buf: list[np.ndarray] = []
        self.pre: deque = deque(maxlen=10)

    def threshold(self, speaking: bool) -> float:
        ratio = max(1.4, 6.0 - 0.45 * self.sensitivity)
        thr = max(0.006, self.noise * ratio)
        return thr * (2.5 if speaking else 1.0)  # be harder to trigger on our own voice

    def reset(self):
        self.in_speech, self.run, self.silence, self.voiced, self.buf = False, 0, 0, 0, []
        self.pre.clear()

    def process(self, frame: np.ndarray, speaking: bool = False) -> list[tuple]:
        f = frame.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(f * f))) if f.size else 0.0
        events: list[tuple] = [("level", min(1.0, rms * 9))]
        voiced = rms > self.threshold(speaking)
        if not self.in_speech:
            self.pre.append(f)
            self.run = self.run + 1 if voiced else 0
            if not voiced:
                self.noise = min(0.05, max(0.0005, 0.97 * self.noise + 0.03 * rms))
            if self.run >= (8 if speaking else 3):
                self.in_speech, self.silence, self.voiced = True, 0, self.run
                self.buf = list(self.pre)
                events.append(("start",))
                if speaking:
                    events.append(("barge",))
            return events
        self.buf.append(f)
        if voiced:
            self.silence = 0
            self.voiced += 1
        else:
            self.silence += 1
        if self.silence * FRAME_MS >= self.silence_ms or len(self.buf) >= self.max_frames:
            audio = np.concatenate(self.buf)
            long_enough = self.voiced * FRAME_MS >= 250
            self.reset()
            if long_enough:
                events.append(("utterance", audio))
        return events


def list_input_devices() -> list[str]:
    try:
        import sounddevice as sd
        seen, names = set(), []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and d["name"] not in seen:
                seen.add(d["name"])
                names.append(d["name"])
        return names
    except Exception:
        return []


class Mic(QObject):
    level = Signal(float)
    speech_started = Signal()
    barge_in = Signal()
    utterance = Signal(object)
    error = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.assistant_speaking = False
        self._q: queue.Queue = queue.Queue(maxsize=200)
        self._stream = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._tick = 0

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
        except Exception as e:  # PortAudio missing
            self.error.emit(f"Audio input isn't available ({e}).")
            return False
        name = self.settings.get("mic.device", "")
        device = None
        if name:
            for i, d in enumerate(sd.query_devices()):
                if d["name"] == name and d["max_input_channels"] > 0:
                    device = i
                    break
        try:
            if not [d for d in sd.query_devices() if d["max_input_channels"] > 0]:
                raise RuntimeError("no microphone found")
            self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                          device=device, callback=self._cb)
            self._stream.start()
        except Exception as e:
            self._stream = None
            self.error.emit(f"I couldn't open the microphone ({e}). Check that it is plugged in, selected in "
                            "Settings > Microphone, and allowed under Windows Settings > Privacy > Microphone.")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="vad")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        with self._q.mutex:
            self._q.queue.clear()

    def _cb(self, indata, frames, time_info, status):
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def _loop(self):
        seg = Segmenter(int(self.settings.get("mic.sensitivity", 5)), int(self.settings.get("mic.silence_ms", 800)))
        while not self._stop.is_set():
            try:
                frame = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            speaking = self.assistant_speaking
            if speaking and not self.settings.get("mic.allow_interrupt", True):
                seg.reset()
                continue
            seg.sensitivity = int(self.settings.get("mic.sensitivity", 5))
            seg.silence_ms = int(self.settings.get("mic.silence_ms", 800))
            for ev in seg.process(frame, speaking):
                k = ev[0]
                if k == "level":
                    self._tick += 1
                    if self._tick % 2 == 0:
                        self.level.emit(ev[1])
                elif k == "start":
                    self.speech_started.emit()
                elif k == "barge":
                    self.barge_in.emit()
                elif k == "utterance":
                    self.utterance.emit(ev[1])
