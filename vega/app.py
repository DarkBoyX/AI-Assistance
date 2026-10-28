from __future__ import annotations

import logging
import logging.handlers
import sys

from PySide6.QtCore import QLockFile, QDir, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__
from .config import Settings
from .controller import Controller
from .paths import app_dir
from .storage import Storage
from .tools import winutil
from .ui import theme
from .ui.main_window import MainWindow


def make_icon() -> QIcon:
    pm = QPixmap(128, 128)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#0a0a0c"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 120, 120)
    for r, a in ((52, 255), (38, 160), (24, 90)):
        pen = QPen(QColor(111, 208, 255, a))
        pen.setWidth(5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(64 - r, 64 - r, 2 * r, 2 * r)
    p.end()
    return QIcon(pm)


def setup_logging():
    h = logging.handlers.RotatingFileHandler(app_dir() / "vega.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])
    sys.excepthook = lambda t, v, tb: logging.getLogger("crash").error("Uncaught", exc_info=(t, v, tb))


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Vega")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.QSS)
    app.setQuitOnLastWindowClosed(False)
    icon = make_icon()
    app.setWindowIcon(icon)

    lock = QLockFile(QDir.temp().absoluteFilePath("vega-assistant.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        QMessageBox.information(None, "Vega", "Vega is already running - look for it in the system tray.")
        return 0

    settings, storage = Settings(), Storage()
    controller = Controller(settings, storage)
    winutil.start_foreground_tracker()

    def quit_all():
        controller.shutdown()
        tray.hide()
        app.quit()

    win = MainWindow(controller, settings, storage, quit_all)
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    act_show = QAction("Show", menu, triggered=lambda: (win.showNormal(), win.activateWindow()))
    act_listen = QAction("Toggle listening", menu, triggered=controller.toggle_listening)
    act_quit = QAction("Quit", menu, triggered=win.quit_app)
    for a in (act_show, act_listen, None, act_quit):
        menu.addSeparator() if a is None else menu.addAction(a)
    tray.setContextMenu(menu)
    tray.setToolTip("Vega assistant")
    tray.activated.connect(lambda r: act_show.trigger() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
    tray.show()
    controller.notify.connect(lambda t, m: tray.showMessage(t, m, QSystemTrayIcon.Information, 8000))
    controller.confirm_request.connect(lambda q, t: tray.showMessage("Vega needs your confirmation", q, QSystemTrayIcon.Warning, 8000)
                                       if not win.isVisible() else None)

    minimized = "--minimized" in sys.argv or settings.get("startup.start_minimized", False)
    if not minimized:
        win.show()
    controller.start(greet=not minimized)
    logging.info("Vega %s started", __version__)
    code = app.exec()
    lock.unlock()
    return code
