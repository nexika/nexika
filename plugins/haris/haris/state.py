"""haris's own data: settings, session state (taint, approvals), project approvals, the audit log.

Everything lives in ~/.claude/nexika/haris/ (HARIS_HOME moves it), owner-only: folders 0700,
files 0600. haris refuses any change to this folder that does not come from haris itself, so
Claude cannot write an approval, clear the taint or edit the log.

    config.json          your settings (profile, mode, extra rules)
    sessions/<id>.json   per session: taint and approvals typed by the user
    approvals.json       approvals typed with --project, per project folder
    audit.jsonl          every ask and deny (commands redacted), rotated at 1 MB
    active/<id>          "haris guards this session" (itqan's guard steps aside)
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
from pathlib import Path

from .paths import data_home

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
AUDIT_LIMIT = 1_000_000
KEEP_DAYS = 7


def home() -> Path:
    return Path(data_home())


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _ensure(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    return folder


def load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def save_json(path: Path, data) -> None:
    _ensure(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def safe_session(session: str) -> str:
    return session if SAFE_ID.match(session or "") else ""


# ---------------------------------------------------------------- settings


def user_config() -> dict:
    return load_json(home() / "config.json", {})


def repo_config(root: str) -> dict:
    return load_json(Path(root) / ".haris.json", {})


# ---------------------------------------------------------------- sessions


def session_path(session: str) -> Path:
    return home() / "sessions" / f"{session}.json"


def load_session(session: str) -> dict:
    if not safe_session(session):
        return {}
    return load_json(session_path(session), {})


def save_session(session: str, data: dict) -> None:
    if safe_session(session):
        data["updated"] = now()
        save_json(session_path(session), data)


def mark_active(session: str) -> None:
    if not safe_session(session):
        return
    marker = _ensure(home() / "active") / session
    if not marker.exists():
        os.close(os.open(marker, os.O_WRONLY | os.O_CREAT, 0o600))


def is_active(session: str) -> bool:
    return bool(safe_session(session)) and (home() / "active" / session).is_file()


def gc() -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    status_home = os.environ.get("NEXIKA_STATUS_HOME") or "~/.claude/nexika/status"
    status = Path(os.path.expanduser(status_home)) / "haris"
    for folder in (home() / "sessions", home() / "active", status):
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for path in entries:
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- approvals


def project_approvals(root: str) -> list[dict]:
    items = load_json(home() / "approvals.json", {}).get(root)
    return [a for a in items if isinstance(a, dict)] if isinstance(items, list) else []


def approvals(session: str, root: str) -> list[dict]:
    items = [a for a in load_session(session).get("approvals", []) if isinstance(a, dict)]
    return items + [{**a, "scope": "project"} for a in project_approvals(root)]


def add_approval(session: str, root: str, entry: dict, project: bool) -> None:
    entry = {**entry, "ts": now()}
    if project:
        data = load_json(home() / "approvals.json", {})
        items = [a for a in data.get(root, []) if (a.get("kind"), a.get("value")) != (entry["kind"],
                                                                                      entry["value"])]
        data[root] = (items + [entry])[-200:]
        save_json(home() / "approvals.json", data)
    else:
        state = load_session(session)
        items = [a for a in state.get("approvals", [])
                 if (a.get("kind"), a.get("value")) != (entry["kind"], entry["value"])]
        state["approvals"] = (items + [entry])[-100:]
        state["project"] = root
        save_session(session, state)


def remove_approval(session: str, root: str, value: str) -> int:
    removed = 0
    state = load_session(session)
    items = state.get("approvals", [])
    kept = [a for a in items if a.get("value") != value]
    if len(kept) != len(items):
        removed += len(items) - len(kept)
        state["approvals"] = kept
        save_session(session, state)
    data = load_json(home() / "approvals.json", {})
    items = data.get(root, [])
    kept = [a for a in items if a.get("value") != value]
    if len(kept) != len(items):
        removed += len(items) - len(kept)
        data[root] = kept
        save_json(home() / "approvals.json", data)
    return removed


# ---------------------------------------------------------------- audit log


def publish_status(session: str, cfg: dict) -> None:
    """status/haris/<session>.json (schema nexika.haris/1): the profile and mode, for mizan's band."""
    if not safe_session(session):
        return
    folder = Path(os.path.expanduser(os.environ.get("NEXIKA_STATUS_HOME") or "~/.claude/nexika/status"))
    path = folder / "haris" / f"{safe_session(session)}.json"
    before = load_json(path, {})
    if before.get("profile") == cfg.get("profile", "") and before.get("mode") == cfg.get("mode", ""):
        return
    try:
        save_json(path,
                  {"schema": "nexika.haris/1", "updated": int(time.time()), "session": session,
                   "profile": cfg.get("profile", ""), "mode": cfg.get("mode", "")})
    except OSError:
        pass


def log(entry: dict) -> None:
    """Append one decision; the command is redacted and cut short before it is written."""
    folder = _ensure(home())
    path = folder / "audit.jsonl"
    entry = {"ts": now(), **entry}
    from . import secrets  # only an ask or a deny is logged: a passing call never loads it
    for key in ("detail", "reason"):
        if key in entry:
            entry[key] = secrets.redact(str(entry[key]))[:600 if key == "reason" else 300]
    try:
        if path.exists() and path.stat().st_size > AUDIT_LIMIT:
            os.replace(path, folder / "audit.1.jsonl")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_audit(limit: int = 0) -> list[dict]:
    out: list[dict] = []
    for name in ("audit.1.jsonl", "audit.jsonl"):
        try:
            with open(home() / name, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(item, dict):
                        out.append(item)
        except OSError:
            continue
    return out[-limit:] if limit else out
