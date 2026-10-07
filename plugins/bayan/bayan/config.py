"""Settings: who the reader is, and what bayan does on its own. Stored in ~/.claude/nexika/bayan."""
from __future__ import annotations

import json
import os
from pathlib import Path

LEVELS = ("no-code", "junior", "developer")
DEFAULTS = {"level": "no-code", "auto_clean": True, "block_signatures": True, "deny_signatures": False}


def home() -> Path:
    return Path(os.environ.get("BAYAN_HOME") or Path.home() / ".claude" / "nexika" / "bayan")


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads((home() / "config.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if os.environ.get("BAYAN_LEVEL") in LEVELS:
        cfg["level"] = os.environ["BAYAN_LEVEL"]
    if cfg.get("level") not in LEVELS:
        cfg["level"] = DEFAULTS["level"]
    return cfg


def save(**changes) -> dict:
    cfg = load() | changes
    home().mkdir(parents=True, exist_ok=True)
    (home() / "config.json").write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    return cfg
