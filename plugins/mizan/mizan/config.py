"""mizan's own folder and settings: ~/.claude/nexika/mizan/ (MIZAN_HOME moves it).

    config.json   your settings: {"lang": "auto|en|ar", "daily_budget_usd": 0, "network": true,
                  "context_mid": 40, "context_full": 75}
    cache/        what gh and glab last answered, per repository
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {"lang": "auto", "daily_budget_usd": 0, "network": True, "context_mid": 40, "context_full": 75}


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


def thresholds() -> tuple[float, float]:
    """(mid, full) context percentages; values that make no sense fall back to 40 and 75."""
    data = load()
    try:
        mid, full = float(data.get("context_mid")), float(data.get("context_full"))
    except (TypeError, ValueError):
        return 40.0, 75.0
    if not 0 < mid < full <= 100:
        return 40.0, 75.0
    return mid, full
