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
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def publish(plugin: str, data: dict, session: str = "") -> bool:
    path = path_for(plugin, session)
    if path is None:
        return False
    try:
        write_json(path, {**data, "schema": schema(plugin), "updated": int(time.time())})
    except OSError:
        return False
    return True


def read(plugin: str, session: str = "", max_age: float = 0) -> dict:
    """A plugin's status, or {} when missing, of another schema, or older than max_age seconds."""
    path = path_for(plugin, session)
    data = read_json(path) if path else {}
    if data.get("schema") != schema(plugin):
        return {}
    if max_age and time.time() - float(data.get("updated") or 0) > max_age:
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
        if time.time() - float(data.get("updated") or 0) > KEEP_SECONDS:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        found.append(data)
    return found
