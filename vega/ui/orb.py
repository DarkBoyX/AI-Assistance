"""The animated core: a glowing ring + radial waveform that reacts to the assistant's state."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .theme import STATE_COLORS

RINGS = [(0.98, 8, [2, 14]), (0.86, -14, [30, 10]), (0.74, 22, [6, 6, 1, 6])]
N = 96


class Orb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self._state, self._level, self._smooth, self._energy = "idle", 0.0, 0.0, 0.25
        self._color = QColor(STATE_COLORS["idle"])
        self._t0 = time.time()
        self._noise = [random.random() for _ in range(N)]
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps keeps CPU low
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, s: str):
        self._state = s

    def set_level(self, v: float):
        self._level = max(self._level * 0.6, v)

    def _tick(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        target = QColor(STATE_COLORS.get(self._state, "#6c6c78"))
        c = self._color
        self._color = QColor(c.red() + (target.red() - c.red()) // 4 + (1 if target.red() > c.red() else 0 if target.red() == c.red() else -1),
                             c.green() + (target.green() - c.green()) // 4 + (1 if target.green() > c.green() else 0 if target.green() == c.green() else -1),
                             c.blue() + (target.blue() - c.blue()) // 4 + (1 if target.blue() > c.blue() else 0 if target.blue() == c.blue() else -1))
        self._level *= 0.85
        self._smooth += (self._level - self._smooth) * 0.35
        e_target = {"idle": 0.25, "listening": 0.4 + self._smooth, "thinking": 0.6, "speaking": 0.9}[self._state]
        self._energy += (e_target - self._energy) * 0.1
        self.update()

    def paintEvent(self, _):
        t = time.time() - self._t0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = QPointF(w / 2, h / 2)
        R = min(w, h) / 2 - 8
        col, st = self._color, self._state

        glow = QRadialGradient(c, R * 1.15)
        g0 = QColor(col)
        g0.setAlpha(int(25 + 85 * min(1.0, self._energy)))
        g1 = QColor(col)
        g1.setAlpha(0)
        glow.setColorAt(0.0, g0)
        glow.setColorAt(1.0, g1)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(c, R * 1.15, R * 1.15)

        for i, (rf, speed, dash) in enumerate(RINGS):
            pen = QPen(QColor(col.red(), col.green(), col.blue(), 70 + 30 * i))
            pen.setWidthF(1.2)
            pen.setDashPattern(dash)
            p.save()
            p.translate(c)
            p.rotate((t * speed * (3 if st == "thinking" else 1)) % 360)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), R * rf, R * rf)
            p.restore()

        base = R * 0.5
        path = QPainterPath()
        for k in range(N + 1):
            a = 2 * math.pi * (k % N) / N
            if st == "speaking":
                amp = 0.16 * (0.5 + 0.4 * math.sin(t * 3.1)) * (
                    0.5 * math.sin(a * 5 + t * 6) + 0.3 * math.sin(a * 9 - t * 4.2) + 0.2 * math.sin(a * 3 + t * 2.3 + self._noise[k % N]))
            elif st == "listening":
                amp = (0.02 + 0.30 * self._smooth) * (0.6 * math.sin(a * 6 + t * 5) + 0.4 * math.sin(a * 11 - t * 7 + self._noise[k % N] * 3))
            elif st == "thinking":
                amp = 0.05 * math.sin(a * 6 - t * 5) + 0.02 * math.sin(a * 13 + t * 3)
            else:
                amp = 0.012 * math.sin(a * 4 + t) + 0.01 * math.sin(t * 0.8)
            r = base + R * amp
            pt = QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))
            path.moveTo(pt) if k == 0 else path.lineTo(pt)
        path.closeSubpath()
        pen = QPen(QColor(col.red(), col.green(), col.blue(), 235))
        pen.setWidthF(2.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        core = QRadialGradient(c, base * 0.9)
        k0 = QColor(col)
        k0.setAlpha(int(40 + 50 * self._energy))
        k1 = QColor(col)
        k1.setAlpha(0)
        core.setColorAt(0, k0)
        core.setColorAt(1, k1)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(c, base * 0.9, base * 0.9)
        p.end()
