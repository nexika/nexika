"""Settings: who the reader is, and what bayan does on its own. Stored in ~/.claude/nexika/bayan.

The reader level comes from, first to last: BAYAN_LEVEL, a level set with `bayan level`, the
Nexika family profile's role (family.py), the default."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from . import family

LEVELS = ("no-code", "junior", "developer")
DEFAULTS = {"level": "developer", "auto_clean": True, "block_signatures": True, "deny_signatures": False}
ROLE_LEVEL = {"developer": "developer", "learner": "junior", "writer": "no-code"}


def home() -> Path:
    return Path(os.environ.get("BAYAN_HOME") or Path.home() / ".claude" / "nexika" / "bayan")


def _stored() -> dict:
    try:
        data = json.loads((home() / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _typed(stored: dict) -> dict:
    """A known setting of the wrong type keeps its default: "false" is a word, not off (#394). A switch
    written by hand as 0 or 1 still counts."""
    out = {}
    for k, v in stored.items():
        if k in DEFAULTS and isinstance(DEFAULTS[k], bool) and type(v) is int and v in (0, 1):
            v = bool(v)
        if k not in DEFAULTS or type(v) is type(DEFAULTS[k]):
            out[k] = v
    return out


def load() -> dict:
    base = ROLE_LEVEL[family.role() or family.DEFAULT_ROLE]
    cfg = {**DEFAULTS, "level": base, **_typed(_stored())}
    if os.environ.get("BAYAN_LEVEL") in LEVELS:
        cfg["level"] = os.environ["BAYAN_LEVEL"]
    if cfg.get("level") not in LEVELS:
        cfg["level"] = base
    return cfg


def _locked():
    """Hold the settings lock while a change reads and saves, so two sessions saving at once both
    keep their change (#394). Without a file lock, changes go through unlocked."""
    try:
        import fcntl
        home().mkdir(parents=True, exist_ok=True)
        fd = os.open(home() / ".config.lock", os.O_WRONLY | os.O_CREAT, 0o600)
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


def _write(stored: dict) -> None:
    """Readers see the old settings or the new ones, never half: an owner-only temp file of this
    process and thread, renamed over config.json; removed on error."""
    import threading

    target = home() / "config.json"
    tmp = home() / f".config.json.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(stored, indent=1) + "\n")
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def save(**changes) -> dict:
    home().mkdir(parents=True, exist_ok=True)
    with _locked():
        _write(_stored() | changes)   # only what was set: a default or the profile's level is never pinned
    return load()
