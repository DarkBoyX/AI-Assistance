import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from vega.config import Settings
from vega.storage import Storage
from vega.controller import Controller
from vega.ui.main_window import MainWindow
from vega.ai.providers import LLMResponse, ToolCall


class Fake:
    def __init__(self, folder): self.n, self.folder = 0, folder
    def chat(self, system, msgs, tools):
        self.n += 1
        last = msgs[-1]
        if last["role"] == "tool":
            return LLMResponse("Folder created.")
        return LLMResponse("Right away.", [ToolCall("1", "create_folder", {"path": self.folder})])


def pump(app, cond, timeout=8):
    end = time.time() + timeout
    while time.time() < end and not cond():
        app.processEvents(); time.sleep(0.01)
    return cond()


def test_full_text_turn_with_gui_and_confirm(tmp_path):
    app = QApplication.instance() or QApplication([])
    s, st = Settings(tmp_path / "s.json"), Storage(tmp_path / "d.db")
    s.set("voice.speak_responses", False)
    c = Controller(s, st)
    target = tmp_path / "made"
    c.agent.provider_factory = lambda _s: Fake(str(target))
    win = MainWindow(c, s, st, lambda: None); win.show()
    states = []; c.state_changed.connect(states.append)
    c.submit_text("make a folder")
    assert pump(app, lambda: target.is_dir() and "Folder created." in win.chat.toPlainText())
    assert "thinking" in states and states[-1] == "idle"
    assert "Right away." in win.chat.toPlainText() and "create_folder" in win.chat.toPlainText()
    assert [r for r, _ in st.recent()] == ["user", "assistant", "assistant"]

    # sensitive action goes through the confirmation dialog and can be answered by voice ("yes")
    f = tmp_path / "doomed.txt"; f.write_text("x")
    class Del(Fake):
        def chat(self, system, msgs, tools):
            return LLMResponse("Done.") if msgs[-1]["role"] == "tool" else LLMResponse("", [ToolCall("2", "delete_path", {"path": str(f)})])
    c.agent.provider_factory = lambda _s: Del("")
    c.submit_text("delete the doomed file")
    assert pump(app, lambda: win._dialog is not None)
    c.submit_text("uh what")                 # unrelated speech must NOT resolve it
    app.processEvents(); assert f.exists() and win._dialog is not None
    c.submit_text("yes please")              # hmm: 2 words, starts with yes
    assert pump(app, lambda: not f.exists() and c._busy == 0)
    assert win._dialog is None
    c.shutdown(); win.quit_app()


def test_provider_error_is_shown(tmp_path):
    app = QApplication.instance() or QApplication([])
    s, st = Settings(tmp_path / "s.json"), Storage(tmp_path / "d.db"); s.set("voice.speak_responses", False)
    c = Controller(s, st); win = MainWindow(c, s, st, lambda: None)
    c.submit_text("hello")  # no API key saved -> friendly error
    assert pump(app, lambda: "API key" in win.chat.toPlainText())
    c.shutdown()


def test_settings_dialog_roundtrip(tmp_path):
    from vega.ui.settings_dialog import SettingsDialog
    app = QApplication.instance() or QApplication([])
    s, st = Settings(tmp_path / "s.json"), Storage(tmp_path / "d.db")
    c = Controller(s, st); win = MainWindow(c, s, st, lambda: None)
    d = SettingsDialog(s, c, st, win)
    d.name.setText("Jarvis"); d.rate.setValue(15); d.perm_boxes["files"].setChecked(False)
    d.prov.setCurrentIndex(d.prov.findData("ollama")); d.model.setText("qwen2.5")
    d._collect(); s.save()
    s2 = Settings(tmp_path / "s.json")
    assert s2.name == "Jarvis" and s2.get("voice.rate") == 15 and s2.get("permissions.files") is False
    assert s2.provider_name == "ollama" and s2.provider_cfg["model"] == "qwen2.5"
    c.shutdown()


def test_tts_pipeline_signals_and_stop(tmp_path, monkeypatch):
    import os
    from vega.voice.tts import TTS
    app = QApplication.instance() or QApplication([])
    s = Settings(tmp_path / "s.json"); t = TTS(s)
    made = []
    def fake_synth(text):
        p = tmp_path / f"{len(made)}.mp3"; p.write_bytes(b"x"); made.append(str(p)); return str(p)
    monkeypatch.setattr(t, "_synth_edge", fake_synth)
    ev = []; t.started.connect(lambda: ev.append("s")); t.finished.connect(lambda: ev.append("f"))
    t.speak("First sentence here, sir. Second one follows. And a third?")
    assert pump(app, lambda: "f" in ev) and ev == ["s", "f"] and len(made) >= 2
    assert not any(os.path.exists(p) for p in made)  # temp files are cleaned up
    t.speak("Another one."); t.stop(); app.processEvents()
    assert ev[-1] == "f" and not t.speaking


def test_edge_failure_falls_back_to_sapi_message(tmp_path, monkeypatch):
    from vega.voice.tts import TTS
    app = QApplication.instance() or QApplication([])
    t = TTS(Settings(tmp_path / "s.json")); errs = []; t.error.connect(errs.append)
    monkeypatch.setattr(t, "_synth_edge", lambda text: (_ for _ in ()).throw(OSError("offline")))
    t.speak("Hello there.")
    assert pump(app, lambda: len(errs) >= 1)
    assert "Windows voice" in errs[0]
