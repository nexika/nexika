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

import contextlib
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
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def locked(path: Path):
    """Hold path's lock while a change reads and saves it, so two sessions (or two hooks of parallel
    tool calls) writing at once both keep their change (#394). Without a file lock (Windows) changes
    go through unlocked."""
    fd = None
    try:
        import fcntl
        _ensure(path.parent)
        fd = os.open(path.with_name(f".{path.name}.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except (ImportError, OSError):
        pass
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)  # closing releases the lock


def count(value) -> int:
    """A counter from a file haris wrote; 0 when it holds anything else."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


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


def update_session(session: str, change) -> None:
    """Apply `change(data) -> bool` to the session as it is now on disk, and save it when that says it
    changed. Never save a copy loaded earlier: another hook may have set the taint since."""
    if not safe_session(session):
        return
    with locked(session_path(session)):
        data = load_session(session)
        if change(data):
            save_session(session, data)


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
                if path.name.endswith(".lock"):  # opening it never touches it: it goes with its file
                    if not path.with_name(path.name[1:-len(".lock")]).exists():
                        path.unlink()
                elif path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- approvals


def project_approvals(root: str) -> list[dict]:
    items = load_json(home() / "approvals.json", {}).get(root)
    return [a for a in items if isinstance(a, dict)] if isinstance(items, list) else []


def _entries(items) -> list[dict]:
    return [a for a in items if isinstance(a, dict)] if isinstance(items, list) else []


def approvals(session: str, root: str) -> list[dict]:
    items = _entries(load_session(session).get("approvals"))
    return items + [{**a, "scope": "project"} for a in project_approvals(root)]


def add_approval(session: str, root: str, entry: dict, project: bool) -> None:
    entry = {**entry, "ts": now()}
    same = (entry["kind"], entry["value"])
    if project:
        path = home() / "approvals.json"
        with locked(path):
            data = load_json(path, {})
            items = [a for a in _entries(data.get(root)) if (a.get("kind"), a.get("value")) != same]
            data[root] = (items + [entry])[-200:]
            save_json(path, data)
    else:
        def add(state: dict) -> bool:
            items = [a for a in _entries(state.get("approvals")) if (a.get("kind"), a.get("value")) != same]
            state["approvals"] = (items + [entry])[-100:]
            state["project"] = root
            return True
        update_session(session, add)


def remove_approval(session: str, root: str, value: str) -> int:
    removed = []

    def drop(data: dict, key) -> bool:
        items = _entries(data.get(key))
        kept = [a for a in items if a.get("value") != value]
        removed.append(len(items) - len(kept))
        data[key] = kept
        return len(kept) != len(items)
    update_session(session, lambda state: drop(state, "approvals"))
    path = home() / "approvals.json"
    with locked(path):
        data = load_json(path, {})
        if drop(data, root):
            save_json(path, data)
    return sum(removed)


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
        with locked(path):  # two sessions past the limit at once rotate it once (#394)
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
            with open(home() / name, encoding="utf-8", errors="replace") as fh:
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
