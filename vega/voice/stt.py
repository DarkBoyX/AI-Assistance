"""Speech-to-text with faster-whisper (runs locally; model downloads once)."""
from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

from ..paths import data_subdir

log = logging.getLogger(__name__)


class SttError(Exception):
    pass


class Transcriber:
    def __init__(self, settings, on_status: Callable[[str], None] | None = None):
        self.settings, self.on_status = settings, on_status
        self._model, self._loaded = None, None
        self._lock = threading.Lock()

    def _name(self) -> str:
        m = self.settings.get("mic.stt_model", "base.en")
        if self.settings.get("mic.stt_language", "en") != "en" and m.endswith(".en"):
            m = m[:-3]
        return m

    def ensure_loaded(self):
        name = self._name()
        with self._lock:
            if self._model is not None and self._loaded == name:
                return
            if self.on_status:
                self.on_status("Loading speech model (the first run downloads it)...")
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(name, device="cpu", compute_type="int8",
                                           download_root=str(data_subdir("models")))
                self._loaded = name
            except Exception as e:
                log.exception("whisper load failed")
                raise SttError("I couldn't load the speech-recognition model. The first run needs an internet "
                               f"connection to download it. ({e})")
            if self.on_status:
                self.on_status("")

    def transcribe(self, audio: np.ndarray) -> str:
        self.ensure_loaded()
        lang = self.settings.get("mic.stt_language", "en")
        prompt = f"{self.settings.name}. Open Chrome. Roblox Studio. Discord. Take a screenshot."
        try:
            segs, _ = self._model.transcribe(audio, language=None if lang == "auto" else lang, beam_size=1,
                                             vad_filter=True, condition_on_previous_text=False,
                                             initial_prompt=prompt)
            parts = [s.text.strip() for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -1.2]
        except Exception as e:
            raise SttError(f"Speech recognition failed: {e}")
        return " ".join(p for p in parts if p).strip()
