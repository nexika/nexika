"""Per-session memory (what Claude already has) and usage events (what helped)."""
from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

from .index import data_home, project_dir

SESSION_TTL_DAYS = 7


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


def save_session(session: str, data: dict) -> None:
    if not _safe(session):
        return
    path = _session_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


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
