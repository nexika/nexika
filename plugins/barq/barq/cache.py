"""Seen-before cache: don't send Claude a file it already has.

Per Claude session (BARQ_SESSION), remembers the exact text of every full read. A repeated
full read of an unchanged file returns a one-line notice; a changed file returns only the
diff when that is smaller. The SessionStart hook resets a session's cache after compaction,
because Claude no longer holds the earlier content then.
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

DIFF_RATIO = 0.6  # send a diff only when it is smaller than 60% of the full text
SESSION_TTL_DAYS = 7


def data_home() -> Path:
    return Path(os.environ.get("BARQ_HOME") or Path.home() / ".claude" / "nexika" / "barq")


def _sessions_dir() -> Path:
    return data_home() / "sessions"


def _safe_id(session: str) -> str:
    return "".join(c for c in session if c.isalnum() or c in "-_")[:64]


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


class Cache:
    def __init__(self, session: str | None):
        self.session = _safe_id(session) if session else ""
        self.enabled = bool(self.session)
        self._lock = threading.Lock()
        self._index: dict[str, dict] = {}
        self._dirty = False
        if self.enabled:
            try:
                self._index = json.loads(self._index_path().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._index = {}

    def _index_path(self) -> Path:
        return _sessions_dir() / f"{self.session}.json"

    def _snap_path(self, key: str) -> Path:
        return _sessions_dir() / self.session / f"{hashlib.sha1(key.encode()).hexdigest()}.txt"

    def check(self, key: str, text: str) -> tuple[str, str | None]:
        """Compare text with what Claude last saw for key.

        Returns ("new", None), ("unchanged", "HH:MM") or ("changed", diff_text).
        A "changed" result with diff None means the diff is not worth it: send it all.
        """
        if not self.enabled:
            return "new", None
        with self._lock:
            entry = self._index.get(key)
        if not entry:
            return "new", None
        if entry.get("hash") == _digest(text):
            return "unchanged", entry.get("ts", "")
        try:
            old = self._snap_path(key).read_text(encoding="utf-8")
        except OSError:
            return "changed", None
        diff = "".join(difflib.unified_diff(
            old.splitlines(keepends=True), text.splitlines(keepends=True),
            "before", "now", n=2,
        ))
        if diff and len(diff) < DIFF_RATIO * len(text):
            return "changed", diff
        return "changed", None

    def remember(self, key: str, text: str) -> None:
        if not self.enabled:
            return
        snap = self._snap_path(key)
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(text, encoding="utf-8")
        with self._lock:
            self._index[key] = {
                "hash": _digest(text),
                "lines": text.count("\n") + 1,
                "ts": datetime.datetime.now().strftime("%H:%M"),
            }
            self._dirty = True

    def save(self) -> None:
        if not (self.enabled and self._dirty):
            return
        path = self._index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._index), encoding="utf-8")
        tmp.replace(path)


def reset(session: str) -> None:
    sid = _safe_id(session)
    if not sid:
        return
    (_sessions_dir() / f"{sid}.json").unlink(missing_ok=True)
    shutil.rmtree(_sessions_dir() / sid, ignore_errors=True)


def gc(max_age_days: int = SESSION_TTL_DAYS) -> int:
    """Delete session caches older than max_age_days. Returns how many were removed."""
    root = _sessions_dir()
    if not root.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for index in root.glob("*.json"):
        if index.stat().st_mtime < cutoff:
            reset(index.stem)
            removed += 1
    return removed
