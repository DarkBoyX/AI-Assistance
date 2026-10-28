from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class ConfirmDialog(QDialog):
    decided = Signal(bool)

    def __init__(self, question: str, tool_name: str, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Confirmation required")
        self.setMinimumWidth(440)
        self._done = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        tag = QLabel(f"PERMISSION  ·  {tool_name}")
        tag.setObjectName("hint")
        q = QLabel(question)
        q.setWordWrap(True)
        q.setStyleSheet("font-size: 15px;")
        hint = QLabel("Click a button, or say “yes” / “no”.")
        hint.setObjectName("hint")
        row = QHBoxLayout()
        row.addStretch()
        deny = QPushButton("Deny")
        deny.setObjectName("danger")
        allow = QPushButton("Allow")
        allow.setObjectName("primary")
        allow.setDefault(True)
        row.addWidget(deny)
        row.addWidget(allow)
        for w in (tag, q, hint):
            lay.addWidget(w)
        lay.addLayout(row)
        allow.clicked.connect(lambda: self._finish(True))
        deny.clicked.connect(lambda: self._finish(False))

    def _finish(self, ok: bool):
        if not self._done:
            self._done = True
            self.decided.emit(ok)
        self.close()

    def closeEvent(self, e):
        if not self._done:
            self._done = True
            self.decided.emit(False)
        super().closeEvent(e)

    def close_silently(self):
        self._done = True
        self.close()
