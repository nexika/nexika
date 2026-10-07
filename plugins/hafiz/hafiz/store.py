"""Where memories live and how they are read, written, capped and forgotten.

Everything is stored outside the repository, in ~/.claude/nexika/hafiz/<project>/ (HAFIZ_HOME
moves it). <project> is the main repository folder name plus a short hash, so every worktree of
a repository shares one memory.

A memory is one JSON line in memories.jsonl:
    id, type (decision|task|problem|file|link), text, date, branch, commit, session,
    source (where it came from: "transcript <session> L<line>" or "manual"),
    reason (why, for a decision, when it was given),
    origin (auto|manual), scope (branch|project), status (open|done|solved|dropped|expired|""),
    key (for updates)
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import secrets

TYPES = ("decision", "task", "problem", "file", "link")
MAX_MEMORIES = 3000          # per project; over it, routine automatic memories go first (see prune)
MAX_TEXT = 500               # characters per memory
SESSION_KEEP_DAYS = 60
OPEN_KEEP_DAYS = 14          # an open task or problem not touched for this long is marked expired
SNAPSHOT_KEEP_DAYS = 7
STALE_LOCK = 120             # seconds; far longer than any hook may run


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def data_home() -> Path:
    return Path(os.environ.get("HAFIZ_HOME") or Path.home() / ".claude" / "nexika" / "hafiz")


def enabled(config: dict | None = None) -> bool:
    if os.environ.get("HAFIZ", "").lower() == "off":
        return False
    return (config or {}).get("mode", "on") != "off"


def _git(cwd: Path, *args: str) -> str:
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.strip() if res.returncode == 0 else ""


def project_root(cwd: Path) -> Path:
    """The main working tree of the repository (the same for all its worktrees), else cwd."""
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        path = Path(common)
        if path.name == ".git":
            return path.parent.resolve()
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else cwd.resolve()


def worktree_root(cwd: Path) -> Path:
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else cwd.resolve()


def branch(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or ""


def head_commit(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "--short", "HEAD")


def project_dir(root: Path) -> Path:
    digest = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name) or "project"
    return data_home() / f"{name}-{digest}"


def load_config(root: Path) -> dict:
    try:
        data = json.loads((root / ".hafiz.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def safe_name(value: str, limit: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:limit] or "none"


def private_dir(folder: Path) -> Path:
    """Create a folder; inside hafiz's data home every folder is readable by its owner only."""
    folder.mkdir(parents=True, exist_ok=True)
    home = data_home().resolve()
    for path in (folder.resolve(), *folder.resolve().parents):
        if path != home and home not in path.parents:
            break
        with contextlib.suppress(OSError):
            os.chmod(path, 0o700)
    return folder


def write_text(path: Path, content: str, private: bool = True) -> None:
    """Write through a new temporary file (O_EXCL, never a planted link) so no reader sees half a file.

    Memory files are owner-only (0600), like Claude Code's own transcripts; `private=False` is for
    a copy the user asked for in their repo.
    """
    if private:
        private_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        if not private:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def write_json(path: Path, data) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=1))


@contextlib.contextmanager
def locked(folder: Path, timeout: float = 5.0):
    """A simple cross-platform lock (a directory) so two hooks never rewrite memories at once."""
    private_dir(folder)
    lock = folder / ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK:  # left behind by a killed process
                    lock.rmdir()
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("hafiz memory is busy") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.rmdir()


class Memory:
    """The memories of one project."""

    def __init__(self, root: Path):
        self.root = root
        self.dir = project_dir(root)
        self.path = self.dir / "memories.jsonl"

    # ------------------------------------------------------------ reading

    def all(self) -> list[dict]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("type") in TYPES and item.get("text"):
                out.append(item)
        return out

    def forgotten(self) -> set[str]:
        return set(read_json(self.dir / "forgotten.json", []))

    # ------------------------------------------------------------ writing

    def _save(self, items: list[dict]) -> None:
        write_text(self.path, "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))

    @staticmethod
    def make(kind: str, text: str, **fields) -> dict:
        clean = re.sub(r"\s+", " ", secrets.redact(text)).strip()
        if len(clean) > MAX_TEXT:
            clean = clean[: MAX_TEXT - 1].rsplit(" ", 1)[0] + "…"
        item = {
            "id": "", "type": kind, "text": clean, "date": fields.get("date") or now(),
            "branch": fields.get("branch", ""), "commit": fields.get("commit", ""),
            "session": fields.get("session", "")[:8], "source": fields.get("source", "manual"),
            "origin": fields.get("origin", "manual"), "scope": fields.get("scope", "branch"),
            "status": fields.get("status", ""), "key": secrets.redact(fields.get("key", "")),
            "reason": secrets.redact(re.sub(r"\s+", " ", fields.get("reason") or "")).strip()[:300],
        }
        item["source"] = secrets.redact(item["source"])
        seed = item["key"] or f"{kind}|{clean}|{item['date']}|{item['session']}"
        item["id"] = "m" + hashlib.sha1(seed.encode()).hexdigest()[:7]
        return item

    def upsert(self, new: list[dict]) -> int:
        """Add memories; one with a known key updates the stored one. Returns how many changed."""
        new = [m for m in new if m.get("text") and m.get("type") in TYPES]
        if not new:
            return 0
        with locked(self.dir):
            items = self.all()
            forgotten = self.forgotten()
            by_key = {i["key"]: n for n, i in enumerate(items) if i.get("key")}
            ids = {i["id"] for i in items}
            changed = 0
            for item in new:
                if item["id"] in forgotten or (item.get("key") and item["key"] in forgotten):
                    continue
                at = by_key.get(item.get("key") or "")
                if at is not None:
                    old = items[at]
                    if old["text"] == item["text"] and old.get("status") == item.get("status"):
                        continue
                    items[at] = {**old, "text": item["text"], "status": item.get("status", ""),
                                 "commit": item.get("commit") or old.get("commit", "")}
                elif item["id"] in ids:
                    continue
                else:
                    items.append(item)
                    ids.add(item["id"])
                    if item.get("key"):
                        by_key[item["key"]] = len(items) - 1
                changed += 1
            if changed:
                self._save(prune(items))
            return changed

    def expire_open(self, days: int = OPEN_KEEP_DAYS) -> int:
        """Mark open tasks and problems older than `days` as expired, so stale ones stop showing."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        with locked(self.dir):
            items = self.all()
            stale = [i for i in items if i["type"] in ("task", "problem") and i.get("status") == "open"
                     and i.get("date", "")[:19] < cutoff]
            for item in stale:
                item["status"] = "expired"
            if stale:
                self._save(items)
            return len(stale)

    def forget(self, match) -> list[dict]:
        """Remove memories for which match(item) is true; auto capture never brings them back."""
        with locked(self.dir):
            items = self.all()
            gone = [i for i in items if match(i)]
            if gone:
                self._save([i for i in items if not match(i)])
                keep = self.forgotten() | {i["id"] for i in gone} | {i["key"] for i in gone if i.get("key")}
                write_json(self.dir / "forgotten.json", sorted(keep)[-5000:])
            return gone


CLOSED = ("done", "solved", "dropped", "expired")


def _keep_rank(item: dict) -> int:
    """Lower goes first when over the cap: routine automatic memories before decisions, and anything
    automatic before what you wrote yourself."""
    if item.get("origin") != "auto":
        return 9
    kind, status = item["type"], item.get("status", "")
    if kind in ("file", "link"):
        return 0
    if kind in ("problem", "task"):
        return 1 if status in CLOSED else 2
    return 3  # decisions


def prune(items: list[dict], limit: int = MAX_MEMORIES) -> list[dict]:
    """Over the cap, drop by type: old automatic files and links first, then closed tasks and problems,
    then open ones, then decisions; what you wrote yourself goes last."""
    if len(items) <= limit:
        return items
    order = sorted(range(len(items)), key=lambda n: (_keep_rank(items[n]), items[n].get("date", "")))
    drop = set(order[: len(items) - limit])
    return [i for n, i in enumerate(items) if n not in drop]


def gc(folder: Path) -> None:
    """Remove old per-session state and snapshots that will not be needed again."""
    for sub, days in (("sessions", SESSION_KEEP_DAYS), ("snapshots", SNAPSHOT_KEEP_DAYS)):
        path = folder / sub
        if not path.is_dir():
            continue
        cutoff = time.time() - days * 86400
        for item in path.glob("*.json"):
            with contextlib.suppress(OSError):
                if item.stat().st_mtime < cutoff:
                    item.unlink()
