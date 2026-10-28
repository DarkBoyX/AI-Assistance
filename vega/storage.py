"""Local SQLite store: conversation history, remembered facts, reminders."""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .paths import app_dir


@dataclass
class Reminder:
    id: int
    text: str
    due: float


class Storage:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or app_dir() / "vega.db")
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        with self._lock:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ts REAL, role TEXT, text TEXT);
                CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, ts REAL, text TEXT);
                CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, text TEXT, due REAL, done INTEGER DEFAULT 0);
            """)
            self._db.commit()

    def _q(self, sql, args=()):
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    # messages
    def add_message(self, role: str, text: str) -> None:
        self._q("INSERT INTO messages(ts,role,text) VALUES(?,?,?)", (time.time(), role, text))

    def recent(self, n: int = 24) -> list[tuple[str, str]]:
        rows = self._q("SELECT role,text FROM messages ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return rows[::-1]

    def clear_messages(self) -> None:
        self._q("DELETE FROM messages")

    # facts
    def add_fact(self, text: str) -> None:
        if not self._q("SELECT 1 FROM facts WHERE lower(text)=lower(?)", (text,)).fetchone():
            self._q("INSERT INTO facts(ts,text) VALUES(?,?)", (time.time(), text))

    def facts(self) -> list[str]:
        return [r[0] for r in self._q("SELECT text FROM facts ORDER BY id").fetchall()]

    def remove_facts(self, needle: str) -> int:
        return self._q("DELETE FROM facts WHERE lower(text) LIKE ?", (f"%{needle.lower()}%",)).rowcount

    def clear_facts(self) -> None:
        self._q("DELETE FROM facts")

    # reminders
    def add_reminder(self, text: str, due: float) -> int:
        return self._q("INSERT INTO reminders(text,due) VALUES(?,?)", (text, due)).lastrowid

    def due_reminders(self, now: float) -> list[Reminder]:
        rows = self._q("SELECT id,text,due FROM reminders WHERE done=0 AND due<=? ORDER BY due", (now,)).fetchall()
        return [Reminder(*r) for r in rows]

    def pending_reminders(self) -> list[Reminder]:
        rows = self._q("SELECT id,text,due FROM reminders WHERE done=0 ORDER BY due").fetchall()
        return [Reminder(*r) for r in rows]

    def finish_reminder(self, rid: int) -> bool:
        return self._q("UPDATE reminders SET done=1 WHERE id=? AND done=0", (rid,)).rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._db.close()
