"""Background reminder scheduler (persisted in SQLite, survives restarts)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .storage import Storage


class ReminderScheduler:
    def __init__(self, storage: Storage, on_due: Callable[[str], None]):
        self.storage, self.on_due = storage, on_due
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True, name="reminders")
        self._t.start()

    def add(self, text: str, due: float) -> int:
        return self.storage.add_reminder(text, due)

    def _loop(self):
        while not self._stop.wait(1.0):
            try:
                for r in self.storage.due_reminders(time.time()):
                    if self.storage.finish_reminder(r.id):
                        self.on_due(r.text)
            except Exception:
                logging.exception("reminder loop")

    def stop(self):
        self._stop.set()
