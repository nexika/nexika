"""mizan's own folder and settings: ~/.claude/nexika/mizan/ (MIZAN_HOME moves it).

    config.json   your settings: {"lang": "auto|en|ar", "daily_budget_usd": 0, "network": true}
    cache/        what gh and glab last answered, per repository
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {"lang": "auto", "daily_budget_usd": 0, "network": True}


def home() -> Path:
    return Path(os.path.expanduser(os.environ.get("MIZAN_HOME") or "~/.claude/nexika/mizan"))


def load() -> dict:
    try:
        with open(home() / "config.json", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **(data if isinstance(data, dict) else {})}


def budget() -> float:
    try:
        return max(0.0, float(load().get("daily_budget_usd") or 0))
    except (TypeError, ValueError):
        return 0.0


def network() -> bool:
    return os.environ.get("MIZAN_OFFLINE") != "1" and load().get("network") is not False
