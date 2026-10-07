"""Per-session memory (what Claude already has) and usage events (what helped)."""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import tempfile
import time
from pathlib import Path

from .index import data_home, project_dir

SESSION_TTL_DAYS = 7
LOCK_WAIT = 3.0    # seconds a hook waits for another hook of the same session
STALE_LOCK = 30    # seconds; a lock older than this was left by a killed process


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe(session: str) -> str:
    return "".join(c for c in session if c.isalnum() or c in "-_")[:64]


def _session_path(session: str) -> Path:
    return data_home() / "sessions" / f"{_safe(session)}.json"


def load_session(session: str) -> dict:
    if not _safe(session):
        return {"shown": {}, "opened": []}
    try:
        data = json.loads(_session_path(session).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {"shown": data.get("shown", {}), "opened": data.get("opened", [])}
    except (OSError, ValueError):
        pass
    return {"shown": {}, "opened": []}


def write_atomic(path: Path, text: str) -> None:
    """Through a new temporary file, so a reader never sees half a file and writers never collide."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def save_session(session: str, data: dict) -> None:
    if not _safe(session):
        return
    write_atomic(_session_path(session), json.dumps(data))


@contextlib.contextmanager
def session_lock(session: str):
    """One hook of a session at a time between reading what Claude has and recording what it got, so
    parallel tool calls (four Reads at once) never inject the same block twice. A hook that cannot
    get the lock in time goes ahead: a repeat is better than a stuck session."""
    lock = _session_path(session).with_suffix(".lock") if _safe(session) else None
    held = False
    if lock is not None:
        lock.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                lock.mkdir()
                held = True
                break
            except FileExistsError:
                with contextlib.suppress(OSError):
                    if time.time() - lock.stat().st_mtime > STALE_LOCK:
                        lock.rmdir()
                        continue
                if time.monotonic() > deadline:
                    break
                time.sleep(0.02)
            except OSError:
                break
    try:
        yield
    finally:
        if held:
            with contextlib.suppress(OSError):
                lock.rmdir()


def reset_session(session: str) -> None:
    if _safe(session):
        _session_path(session).unlink(missing_ok=True)


def gc(max_age_days: int = SESSION_TTL_DAYS) -> None:
    folder = data_home() / "sessions"
    if not folder.is_dir():
        return
    cutoff = time.time() - max_age_days * 86400
    for path in folder.glob("*.json"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def log_event(root: Path, event: dict) -> None:
    folder = project_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": _now(), **event}, ensure_ascii=False) + "\n")


def read_events(root: Path, since: str = "") -> list[dict]:
    try:
        lines = (project_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("ts", "") >= since:
            out.append(item)
    return out
