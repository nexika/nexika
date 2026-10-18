"""Seen-before cache: don't send Claude a file it already has.

Per Claude session (BARQ_SESSION) and agent (BARQ_AGENT, set in subagents), remembers the
exact text of every full read. A repeated full read of an unchanged file returns a one-line
notice; a changed file returns only the diff when that is smaller. The SessionStart hook resets
a session's cache after compaction, because Claude no longer holds the earlier content then.
"""
from __future__ import annotations

import contextlib
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
    return "".join(c for c in session if c.isalnum() or c in "-_")[:128]


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def _load_index(path: Path) -> dict[str, dict]:
    """A session's index; one of the wrong shape reads as empty, entries of the wrong shape are
    dropped (#394)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _write_whole(path: Path, text: str) -> None:
    """Readers see the old file or the new one, never half of it: a temp file of this process and
    thread in the same folder, owner-only, renamed over the file; removed on error (#394)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:  # CRLF kept: the hash must match
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _locked(folder: Path):
    """Hold the index lock while a call reads and saves its session's index, so two barq calls of
    one session both keep their reads. Without a file lock, saves go through unlocked."""
    try:
        import fcntl
        folder.mkdir(parents=True, exist_ok=True)
        fd = os.open(folder / ".index.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    except (ImportError, OSError):
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def held():
        try:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)  # closing releases the lock
    return held()


class Cache:
    def __init__(self, session: str | None):
        self.session = _safe_id(session) if session else ""
        self.enabled = bool(self.session)
        self._lock = threading.Lock()
        self._index: dict[str, dict] = {}
        self._mine: set[str] = set()   # keys this call remembered: they win when saving
        if self.enabled:
            self._index = _load_index(self._index_path())

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
            with open(self._snap_path(key), encoding="utf-8", newline="") as fh:
                old = fh.read()
        except (OSError, ValueError):
            return "changed", None
        if _digest(old) != entry.get("hash"):
            return "changed", None  # not the text Claude saw (cut short, or another call's): no diff
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
        try:
            _write_whole(self._snap_path(key), text)
        except OSError:
            pass  # no snapshot: the next change is sent whole, never as a diff against nothing
        with self._lock:
            self._index[key] = {
                "hash": _digest(text),
                "lines": text.count("\n") + 1,
                "ts": datetime.datetime.now().strftime("%H:%M"),
            }
            self._mine.add(key)

    def save(self) -> None:
        """Save the index. Reads another call of this session saved since this one loaded it are
        kept; this call's own reads win."""
        if not (self.enabled and self._mine):
            return
        path = self._index_path()
        with self._lock, _locked(path.parent):
            index = _load_index(path)
            index.update({key: self._index[key] for key in self._mine})
            _write_whole(path, json.dumps(index))


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
