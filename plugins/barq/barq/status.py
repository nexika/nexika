"""The Nexika status files: how the plugins tell each other what they know.

Each plugin publishes small JSON files under ~/.claude/nexika/status/ (NEXIKA_STATUS_HOME moves it):

    <plugin>.json              plugin-wide state (haris: profile and mode; itqan: latest proof per project)
    <plugin>/<session>.json    one session's state (mizan: context level, cost, device)

Every file carries "schema": "nexika.<plugin>/1" and "updated" (seconds since the epoch). A reader
checks the schema and ignores a file it does not understand or one that is too old; a missing file
means "nothing known", never an error. Files are owner-only and written atomically.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
KEEP_SECONDS = 7 * 86400


def home() -> Path:
    return Path(os.path.expanduser(os.environ.get("NEXIKA_STATUS_HOME") or "~/.claude/nexika/status"))


def schema(plugin: str) -> str:
    return f"nexika.{plugin}/1"


def path_for(plugin: str, session: str = "") -> Path | None:
    if not SAFE_ID.match(plugin) or (session and not SAFE_ID.match(session)):
        return None
    return home() / plugin / f"{session}.json" if session else home() / f"{plugin}.json"


def ensure_dir(folder: Path) -> None:
    """Create a folder and its missing parents owner-only (mkdir's mode covers only the last one)."""
    missing = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for one in reversed(missing):
        one.mkdir(mode=0o700, exist_ok=True)
        os.chmod(one, 0o700)


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")  # threads too
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def updated(data: dict) -> float:
    """When the file was written, or 0 (long ago) when it holds no usable time."""
    try:
        return float(data.get("updated") or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def publish(plugin: str, data: dict, session: str = "") -> bool:
    path = path_for(plugin, session)
    if path is None:
        return False
    try:
        write_json(path, {**data, "schema": schema(plugin), "updated": int(time.time())})
    except OSError:
        return False
    return True


def _locked(path: Path):
    """Hold path's lock while a change reads and writes it. Without a file lock (Windows, some
    network homes) the change goes through unlocked."""
    import contextlib
    try:
        import fcntl
        ensure_dir(path.parent)
        fd = os.open(path.with_name(f".{path.name}.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
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


def update(plugin: str, change, session: str = "") -> dict | None:
    """Change a plugin's status file as it is on disk now, so two sessions publishing at once both
    keep their part (#394). `change(data)` edits the current data in place ({} when the file is
    missing or unusable). Returns what was saved, or None when it could not be."""
    path = path_for(plugin, session)
    if path is None:
        return None
    try:
        with _locked(path):
            data = read(plugin, session)
            change(data)
            data = {**data, "schema": schema(plugin), "updated": int(time.time())}
            write_json(path, data)
    except OSError:
        return None
    return data


def read(plugin: str, session: str = "", max_age: float = 0) -> dict:
    """A plugin's status, or {} when missing, of another schema, or older than max_age seconds."""
    path = path_for(plugin, session)
    data = read_json(path) if path else {}
    if data.get("schema") != schema(plugin):
        return {}
    if max_age and time.time() - updated(data) > max_age:
        return {}
    return data


def sessions(plugin: str) -> list[dict]:
    """Every session file of a plugin (week-old ones are removed on the way)."""
    folder = home() / plugin
    found = []
    try:
        entries = list(folder.glob("*.json"))
    except OSError:
        return []
    for path in entries:
        data = read_json(path)
        if data.get("schema") != schema(plugin):
            continue
        if time.time() - updated(data) > KEEP_SECONDS:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        found.append(data)
    return found
