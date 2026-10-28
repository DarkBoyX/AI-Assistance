from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import secrets, startup
from ..ai.providers import ProviderError, make_provider
from ..paths import app_dir, data_subdir
from ..voice.audio_in import list_input_devices

FALLBACK_VOICES = ["en-GB-RyanNeural", "en-GB-ThomasNeural", "en-GB-SoniaNeural", "en-US-GuyNeural",
                   "en-US-AriaNeural", "en-US-JennyNeural", "en-US-ChristopherNeural", "en-AU-WilliamNeural",
                   "en-IN-PrabhatNeural", "ar-SA-HamedNeural", "fr-FR-HenriNeural", "de-DE-ConradNeural",
                   "es-ES-AlvaroNeural"]
STT_MODELS = ["tiny.en", "base.en", "small.en", "tiny", "base", "small", "medium"]
PERMS = [("apps", "Open, switch and close applications"), ("files", "Read, create, move and delete files and folders"),
         ("web", "Web searches, browser navigation, reading web pages"),
         ("input", "Keyboard, clipboard, screenshots, volume and media keys"),
         ("messaging", "Interact with messaging apps (always asks before sending)"),
         ("commands", "Run commands, approved scripts and install software (always asks)")]


class _Bridge(QObject):
    voices = Signal(list)
    test_result = Signal(str)


def _slider(lo, hi, val, suffix=""):
    row, s, lab = QHBoxLayout(), QSlider(Qt.Horizontal), QLabel()
    s.setRange(lo, hi)
    s.setValue(int(val))
    lab.setMinimumWidth(52)
    s.valueChanged.connect(lambda v: lab.setText(f"{v}{suffix}"))
    lab.setText(f"{int(val)}{suffix}")
    row.addWidget(s, 1)
    row.addWidget(lab)
    w = QWidget()
    w.setLayout(row)
    row.setContentsMargins(0, 0, 0, 0)
    return w, s


class SettingsDialog(QDialog):
    def __init__(self, settings, controller, storage, parent=None):
        super().__init__(parent)
        self.s, self.c, self.storage = settings, controller, storage
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 560)
        self.bridge = _Bridge()
        self.bridge.voices.connect(self._set_voices)
        self.bridge.test_result.connect(lambda t: self.test_lbl.setText(t))
        self._prov_state = {k: dict(v) for k, v in settings.get("ai.providers").items()}
        self._cur_prov = settings.provider_name

        tabs = QTabWidget()
        tabs.addTab(self._general(), "General")
        tabs.addTab(self._ai(), "AI")
        tabs.addTab(self._voice(), "Voice")
        tabs.addTab(self._mic(), "Microphone")
        tabs.addTab(self._perms(), "Permissions")
        tabs.addTab(self._startup(), "Startup & data")
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)
        threading.Thread(target=self._load_voices, daemon=True).start()

    # ---- tabs ----
    def _general(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.name = QLineEdit(self.s.get("assistant.name"))
        self.user = QLineEdit(self.s.get("assistant.user_name"))
        self.persona = QPlainTextEdit(self.s.get("assistant.personality"))
        self.persona.setMinimumHeight(140)
        f.addRow("Assistant name", self.name)
        f.addRow("Your name", self.user)
        f.addRow("Personality", self.persona)
        hint = QLabel("Describe how it should talk, e.g. “formal and witty”, “friendly and casual”, “brief and blunt”.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        f.addRow("", hint)
        return w

    def _ai(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.prov = QComboBox()
        for k, v in self.s.get("ai.providers").items():
            self.prov.addItem(v.get("label", k), k)
        self.prov.setCurrentIndex(self.prov.findData(self._cur_prov))
        self.model, self.base = QLineEdit(), QLineEdit()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.temp = QSlider(Qt.Horizontal)
        self.temp.setRange(0, 100)
        self.temp.setValue(int(float(self.s.get("ai.temperature", 0.5)) * 100))
        self.test_btn, self.test_lbl = QPushButton("Test connection"), QLabel("")
        self.test_lbl.setWordWrap(True)
        self.test_btn.clicked.connect(self._test_ai)
        self.prov.currentIndexChanged.connect(self._prov_changed)
        f.addRow("Provider", self.prov)
        f.addRow("Model", self.model)
        f.addRow("Base URL", self.base)
        f.addRow("API key", self.key)
        f.addRow("Creativity", self.temp)
        f.addRow("", self.test_btn)
        f.addRow("", self.test_lbl)
        note = QLabel("Keys are stored in the Windows Credential Manager, never in files. "
                      "Ollama needs no key. Any OpenAI-compatible server works under “Custom”.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        f.addRow("", note)
        self._load_prov(self._cur_prov)
        return w

    def _load_prov(self, name):
        cfg = self._prov_state[name]
        self.model.setText(cfg.get("model", ""))
        self.base.setText(cfg.get("base_url", ""))
        self.key.clear()
        has = secrets.has_api_key(name)
        self.key.setPlaceholderText("(saved - type to replace)" if has else
                                    ("not needed" if not cfg.get("needs_key", True) else "paste your API key"))

    def _stash_prov(self):
        cfg = self._prov_state[self._cur_prov]
        cfg["model"], cfg["base_url"] = self.model.text().strip(), self.base.text().strip()

    def _prov_changed(self):
        self._stash_prov()
        self._cur_prov = self.prov.currentData()
        self._load_prov(self._cur_prov)

    def _voice(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.engine = QComboBox()
        self.engine.addItem("Neural voice (edge-tts, online)", "edge")
        self.engine.addItem("Windows built-in voice (offline)", "windows")
        self.engine.setCurrentIndex(self.engine.findData(self.s.get("voice.engine", "edge")))
        self.voice = QComboBox()
        self.voice.setEditable(True)
        self.voice.addItems(FALLBACK_VOICES)
        self.voice.setCurrentText(self.s.get("voice.voice"))
        rw, self.rate = _slider(-50, 50, self.s.get("voice.rate", 0), "%")
        pw, self.pitch = _slider(-50, 50, self.s.get("voice.pitch", 0), " Hz")
        vw, self.vol = _slider(0, 100, self.s.get("voice.volume", 85), "%")
        self.speak = QCheckBox("Speak replies aloud")
        self.speak.setChecked(self.s.get("voice.speak_responses", True))
        test = QPushButton("Test voice")
        test.clicked.connect(self._test_voice)
        f.addRow("Engine", self.engine)
        f.addRow("Voice", self.voice)
        f.addRow("Speed", rw)
        f.addRow("Pitch", pw)
        f.addRow("Volume", vw)
        f.addRow("", self.speak)
        f.addRow("", test)
        return w

    def _mic(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.dev = QComboBox()
        self.dev.addItem("System default", "")
        for d in list_input_devices():
            self.dev.addItem(d, d)
        self.dev.setCurrentIndex(max(0, self.dev.findData(self.s.get("mic.device", ""))))
        sw, self.sens = _slider(1, 10, self.s.get("mic.sensitivity", 5))
        self.sil = QSpinBox()
        self.sil.setRange(300, 3000)
        self.sil.setSingleStep(100)
        self.sil.setSuffix(" ms")
        self.sil.setValue(int(self.s.get("mic.silence_ms", 800)))
        self.cont = QCheckBox("Listen continuously on startup (hands-free conversation)")
        self.cont.setChecked(self.s.get("mic.continuous", True))
        self.intr = QCheckBox("Let me interrupt while it is speaking (use headphones to avoid echo)")
        self.intr.setChecked(self.s.get("mic.allow_interrupt", True))
        self.wake = QCheckBox("Require the assistant's name to start a conversation (45 s follow-up window)")
        self.wake.setChecked(self.s.get("mic.wake_word", False))
        self.stt = QComboBox()
        self.stt.addItems(STT_MODELS)
        self.stt.setCurrentText(self.s.get("mic.stt_model", "base.en"))
        self.lang = QLineEdit(self.s.get("mic.stt_language", "en"))
        self.lang.setToolTip("Language code like en, ar, fr - or 'auto'. Use non-.en models for non-English.")
        f.addRow("Microphone", self.dev)
        f.addRow("Sensitivity", sw)
        f.addRow("End-of-speech pause", self.sil)
        f.addRow("Speech model", self.stt)
        f.addRow("Language", self.lang)
        f.addRow("", self.cont)
        f.addRow("", self.intr)
        f.addRow("", self.wake)
        return w

    def _perms(self):
        w, l = QWidget(), QVBoxLayout()
        w.setLayout(l)
        self.perm_boxes = {}
        for key, text in PERMS:
            cb = QCheckBox(text)
            cb.setChecked(self.s.get(f"permissions.{key}", True))
            self.perm_boxes[key] = cb
            l.addWidget(cb)
        n = QLabel("Sending messages, deleting/moving files, running commands and installing software always "
                   "require your confirmation, whatever is ticked here. Switching a category off removes those tools completely.")
        n.setObjectName("hint")
        n.setWordWrap(True)
        l.addSpacing(10)
        l.addWidget(n)
        l.addStretch()
        return w

    def _startup(self):
        w, l = QWidget(), QVBoxLayout()
        w.setLayout(l)
        self.autostart = QCheckBox("Start with Windows")
        self.autostart.setChecked(self.s.get("startup.start_with_windows", False))
        self.start_min = QCheckBox("Start minimized to the system tray")
        self.start_min.setChecked(self.s.get("startup.start_minimized", False))
        self.tray = QCheckBox("Closing the window minimizes to the tray")
        self.tray.setChecked(self.s.get("startup.minimize_to_tray_on_close", True))
        for x in (self.autostart, self.start_min, self.tray):
            l.addWidget(x)
        sc = QPushButton("Create desktop shortcut")
        sc.clicked.connect(self._shortcut)
        clr = QPushButton("Clear conversation history")
        clr.clicked.connect(self._clear)
        mem = QPushButton("Clear remembered facts")
        mem.clicked.connect(self._clear_mem)
        l.addSpacing(8)
        for b in (sc, clr, mem):
            l.addWidget(b)
        row = QHBoxLayout()
        for text, d in (("Data folder", None), ("Scripts folder", "scripts"), ("Plugins folder", "plugins")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, d=d: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(data_subdir(d) if d else app_dir()))))
            row.addWidget(b)
        l.addLayout(row)
        l.addStretch()
        return w

    # ---- actions ----
    def _load_voices(self):
        try:
            import asyncio
            import edge_tts
            vs = asyncio.run(edge_tts.list_voices())
            names = sorted(v["ShortName"] for v in vs if v["Locale"].lower().startswith(("en", "ar", "fr", "de", "es")))
            if names:
                self.bridge.voices.emit(names)
        except Exception:
            pass

    def _set_voices(self, names):
        cur = self.voice.currentText()
        self.voice.clear()
        self.voice.addItems(names)
        self.voice.setCurrentText(cur)

    def _collect(self):
        s = self.s
        self._stash_prov()
        s.set("assistant.name", self.name.text().strip() or "Vega")
        s.set("assistant.user_name", self.user.text().strip())
        s.set("assistant.personality", self.persona.toPlainText().strip())
        s.set("ai.provider", self.prov.currentData())
        s.set("ai.providers", self._prov_state)
        s.set("ai.temperature", self.temp.value() / 100)
        s.set("voice.engine", self.engine.currentData())
        s.set("voice.voice", self.voice.currentText().strip())
        s.set("voice.rate", self.rate.value())
        s.set("voice.pitch", self.pitch.value())
        s.set("voice.volume", self.vol.value())
        s.set("voice.speak_responses", self.speak.isChecked())
        s.set("mic.device", self.dev.currentData() or "")
        s.set("mic.sensitivity", self.sens.value())
        s.set("mic.silence_ms", self.sil.value())
        s.set("mic.continuous", self.cont.isChecked())
        s.set("mic.allow_interrupt", self.intr.isChecked())
        s.set("mic.wake_word", self.wake.isChecked())
        s.set("mic.stt_model", self.stt.currentText())
        s.set("mic.stt_language", self.lang.text().strip() or "en")
        for k, cb in self.perm_boxes.items():
            s.set(f"permissions.{k}", cb.isChecked())
        s.set("startup.start_with_windows", self.autostart.isChecked())
        s.set("startup.start_minimized", self.start_min.isChecked())
        s.set("startup.minimize_to_tray_on_close", self.tray.isChecked())

    def _store_key(self):
        k = self.key.text().strip()
        if k:
            try:
                secrets.set_api_key(self._cur_prov, k)
            except Exception as e:
                QMessageBox.warning(self, "API key", f"Couldn't store the key in Windows Credential Manager: {e}")

    def _test_voice(self):
        self._collect()
        self.c.tts.stop()
        self.c.speak(f"Hello. I'm {self.s.name}. This is how I sound.")

    def _test_ai(self):
        self._collect()
        self._store_key()
        self.test_lbl.setText("Testing...")

        def run():
            try:
                r = make_provider(self.s).chat("Reply with the single word OK.", [{"role": "user", "content": "ping"}], [])
                self.bridge.test_result.emit(f"Connected. Model replied: {r.text[:60] or '(empty)'}")
            except ProviderError as e:
                self.bridge.test_result.emit(f"Failed: {e}")
            except Exception as e:
                self.bridge.test_result.emit(f"Failed: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _shortcut(self):
        try:
            QMessageBox.information(self, "Shortcut", f"Created {startup.create_desktop_shortcut()}")
        except Exception as e:
            QMessageBox.warning(self, "Shortcut", f"Couldn't create the shortcut: {e}")

    def _clear(self):
        if QMessageBox.question(self, "Clear history", "Delete the whole conversation history?") == QMessageBox.Yes:
            self.c.clear_history()
            self.parent().chat.clear()

    def _clear_mem(self):
        if QMessageBox.question(self, "Forget", "Delete everything the assistant has remembered about you?") == QMessageBox.Yes:
            self.storage.clear_facts()

    def _save(self):
        self._collect()
        self._store_key()
        self.s.save()
        try:
            startup.set_start_with_windows(self.s.get("startup.start_with_windows"), self.s.get("startup.start_minimized"))
        except Exception as e:
            QMessageBox.warning(self, "Startup", f"Couldn't change the startup setting: {e}")
        if self.c.listening:  # re-open the mic so a new device takes effect
            self.c.stop_listening()
            self.c.start_listening()
        self.accept()
