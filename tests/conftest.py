import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp()


# The Linux sandbox has no Qt Multimedia backend (constructing QMediaPlayer segfaults), so tests use a stand-in.
# On Windows the real QMediaPlayer is used.
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer as _RealPlayer


class _FakePlayer(QObject):
    mediaStatusChanged = Signal(object)
    errorOccurred = Signal(object, str)
    MediaStatus = _RealPlayer.MediaStatus
    def setAudioOutput(self, a): pass
    def setSource(self, u): pass
    def play(self): self.mediaStatusChanged.emit(_RealPlayer.MediaStatus.EndOfMedia)
    def stop(self): pass


class _FakeAudio(QObject):
    def setVolume(self, v): pass


@pytest.fixture(autouse=True)
def _no_multimedia(monkeypatch):
    import vega.voice.tts as tts
    monkeypatch.setattr(tts, "QMediaPlayer", _FakePlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudio)
