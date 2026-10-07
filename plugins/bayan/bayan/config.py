"""Settings: who the reader is, and what bayan does on its own. Stored in ~/.claude/nexika/bayan.

The reader level comes from, first to last: BAYAN_LEVEL, a level set with `bayan level`, the
Nexika family profile's role (family.py), the default."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import family

LEVELS = ("no-code", "junior", "developer")
DEFAULTS = {"level": "no-code", "auto_clean": True, "block_signatures": True, "deny_signatures": False}
ROLE_LEVEL = {"developer": "developer", "learner": "junior", "writer": "no-code"}


def home() -> Path:
    return Path(os.environ.get("BAYAN_HOME") or Path.home() / ".claude" / "nexika" / "bayan")


def _stored() -> dict:
    try:
        data = json.loads((home() / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load() -> dict:
    base = ROLE_LEVEL.get(family.role(), DEFAULTS["level"])
    cfg = {**DEFAULTS, "level": base, **_stored()}
    if os.environ.get("BAYAN_LEVEL") in LEVELS:
        cfg["level"] = os.environ["BAYAN_LEVEL"]
    if cfg.get("level") not in LEVELS:
        cfg["level"] = base
    return cfg


def save(**changes) -> dict:
    stored = _stored() | changes   # only what was set: a default or the profile's level is never pinned
    home().mkdir(parents=True, exist_ok=True)
    (home() / "config.json").write_text(json.dumps(stored, indent=1) + "\n", encoding="utf-8")
    return load()
