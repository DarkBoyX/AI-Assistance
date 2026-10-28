from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QTextBrowser, QVBoxLayout,
                               QWidget)

from . import theme
from .confirm_dialog import ConfirmDialog
from .orb import Orb
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, controller, settings, storage, on_quit):
        super().__init__()
        self.c, self.settings, self.storage, self._quit = controller, settings, storage, on_quit
        self._dialog: ConfirmDialog | None = None
        self._really_quit = False
        self.setMinimumSize(560, 720)
        self.resize(640, 820)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(22, 16, 22, 18)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("title")
        self.dot = QLabel("●")
        self.status = QLabel()
        self.status.setStyleSheet("letter-spacing: 3px; font-size: 11px;")
        self.mute = QPushButton("🔊")
        self.mute.setObjectName("icon")
        self.mute.setCheckable(True)
        self.mute.setToolTip("Mute / unmute spoken replies")
        gear = QPushButton("⚙")
        gear.setObjectName("icon")
        gear.setToolTip("Settings")
        top.addWidget(self.title)
        top.addStretch()
        top.addWidget(self.dot)
        top.addWidget(self.status)
        top.addSpacing(10)
        top.addWidget(self.mute)
        top.addWidget(gear)
        lay.addLayout(top)

        self.orb = Orb()
        lay.addWidget(self.orb, 3)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setMinimumHeight(18)
        lay.addWidget(self.hint)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        lay.addWidget(self.chat, 4)

        bottom = QHBoxLayout()
        self.mic = QPushButton("🎙")
        self.mic.setObjectName("mic")
        self.mic.setCheckable(True)
        self.mic.setToolTip("Toggle continuous listening")
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message, or just speak...")
        send = QPushButton("Send")
        send.setObjectName("primary")
        stop = QPushButton("■")
        stop.setObjectName("icon")
        stop.setToolTip("Stop speaking / cancel")
        bottom.addWidget(self.mic)
        bottom.addWidget(self.input, 1)
        bottom.addWidget(stop)
        bottom.addWidget(send)
        lay.addLayout(bottom)

        gear.clicked.connect(self.open_settings)
        send.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)
        stop.clicked.connect(self.c.interrupt)
        self.mic.clicked.connect(self.c.toggle_listening)
        self.mute.toggled.connect(self._mute)
        c = self.c
        c.state_changed.connect(self._state)
        c.level.connect(self.orb.set_level)
        c.message.connect(self.add_message)
        c.tool_event.connect(lambda t: self._append(f'<span style="color:{theme.MUTED};font-size:12px">⚙ {html.escape(t)}</span>'))
        c.error.connect(self.add_error)
        c.hint.connect(self.hint.setText)
        c.confirm_request.connect(self._show_confirm)
        c.confirm_closed.connect(self._close_confirm)
        c.listening_changed.connect(self.mic.setChecked)
        self.refresh_labels()
        self._state("idle")
        self.mute.setChecked(not self.settings.get("voice.speak_responses", True))
        for role, text in self.storage.recent(40):
            self.add_message(role, text)

    # ---- helpers ----
    def refresh_labels(self):
        name = self.settings.name.upper()
        self.title.setText(name)
        self.setWindowTitle(f"{self.settings.name} - AI Assistant")
        self.chat.setPlaceholderText(f"Conversation with {self.settings.name} appears here.")

    def _state(self, s: str):
        col = theme.STATE_COLORS[s]
        self.dot.setStyleSheet(f"color:{col}; font-size:10px;")
        self.status.setText(theme.STATE_LABELS[s])
        self.status.setStyleSheet(f"color:{col}; letter-spacing:3px; font-size:11px;")
        self.orb.set_state(s)

    def _append(self, h: str):
        self.chat.append(f'<div style="margin:5px 0">{h}</div>')
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def add_message(self, role: str, text: str):
        if role == "user":
            self._append(f'<span style="color:{theme.STATE_COLORS["listening"]};font-weight:600;font-size:11px;letter-spacing:2px">YOU</span><br>{html.escape(text)}')
        else:
            self._append(f'<span style="color:#ffffff;font-weight:600;font-size:11px;letter-spacing:2px">{html.escape(self.settings.name.upper())}</span><br>{html.escape(text)}')

    def add_error(self, text: str):
        self._append(f'<span style="color:#ff8a8a">⚠ {html.escape(text)}</span>')

    def _send(self):
        t = self.input.text().strip()
        if t:
            self.input.clear()
            self.c.submit_text(t)

    def _mute(self, muted: bool):
        self.mute.setText("🔇" if muted else "🔊")
        self.settings.set("voice.speak_responses", not muted)
        self.settings.save()
        if muted:
            self.c.tts.stop()

    # ---- confirmation ----
    def _show_confirm(self, question: str, tool: str):
        self._close_confirm()
        self._dialog = ConfirmDialog(question, tool, self)
        self._dialog.decided.connect(self.c.resolve_confirm)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        self.c.speak(f"{question} Say yes or no.")

    def _close_confirm(self):
        d, self._dialog = self._dialog, None
        if d:
            d.close_silently()

    # ---- settings / lifecycle ----
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.c, self.storage, self)
        if dlg.exec():
            self.refresh_labels()
            self.mute.setChecked(not self.settings.get("voice.speak_responses", True))
        else:
            self.settings.load()

    def quit_app(self):
        self._really_quit = True
        self.close()

    def closeEvent(self, e: QCloseEvent):
        if not self._really_quit and self.settings.get("startup.minimize_to_tray_on_close", True):
            e.ignore()
            self.hide()
            return
        self._quit()
        e.accept()
