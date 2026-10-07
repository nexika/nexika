"""One guard and one consent for the family's paid background model calls (`claude -p`).

prof's automatic report, itqan's lesson extraction and hafiz's summary each start Claude Code
in the background, which uses the person's plan or API credits. Every such job:
- runs with NEXIKA_BACKGROUND=1 (`child_env()`), and every Nexika hook exits at once when it
  sees it, so no plugin's hooks fire inside another plugin's background call;
- asks `allowed()` first: "background_calls" in the family settings file (#108),
  ~/.claude/nexika/settings.json: "ask" (the default), "on" or "off" (NEXIKA_HOME moves the folder);
- writes one line per call to ~/.claude/nexika/background.jsonl (`record()`), so
  `python3 <this file> status` can say how many ran.

Standard library only: plugins ship a copy (see .amin.json). Edit common/background.py.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ENV = "NEXIKA_BACKGROUND"
KEY = "background_calls"
CHOICES = ("ask", "on", "off")
DEFAULT = "ask"


# ---------------------------------------------------------------- the family settings file
# One file for the whole family (#108): ~/.claude/nexika/settings.json (NEXIKA_HOME moves the
# folder), owner-only, holding the role (family.py) and the background-call consent
# (background.py). Both files carry this block word for word (tests/test_settings_file.py).

SETTINGS_SCHEMA = "nexika.settings/1"
_FROM_PROFILE = ("role", "asked")


def nexika_home() -> Path:
    return Path(os.path.expanduser(os.environ.get("NEXIKA_HOME") or "~/.claude/nexika"))


def settings_path() -> Path:
    return nexika_home() / "settings.json"


def _old_profile() -> Path:
    """Where the role lived before #108 (NEXIKA_PROFILE moved it)."""
    return Path(os.path.expanduser(os.environ.get("NEXIKA_PROFILE") or str(nexika_home() / "profile.json")))


def _load(path: Path) -> dict | None:
    """The file's JSON object; {} when there is no file; None when it holds anything else."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save(data: dict) -> None:
    target = settings_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({**data, "schema": SETTINGS_SCHEMA}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, target)


def read_settings() -> dict:
    """The family settings. The first read moves an older profile.json in (the settings file wins
    where both say something) and sets it aside as profile.json.migrated, so it happens once."""
    data = _load(settings_path())
    if data is None:
        return {}  # unreadable: a read never overwrites it, only a save does
    old = _old_profile()
    try:
        moving = old.is_file()
    except OSError:
        moving = False
    if not moving and (not data or data.get("schema") == SETTINGS_SCHEMA):
        return data
    profile = (_load(old) or {}) if moving else {}
    merged = {**{k: profile[k] for k in _FROM_PROFILE if k in profile}, **data}
    try:
        _save(merged)
        if moving:
            os.replace(old, old.with_name(old.name + ".migrated"))
    except OSError:
        pass  # read-only home: still answer from what was read
    return merged


def update_settings(**changes) -> dict:
    data = {**read_settings(), **changes}
    _save(data)
    return data

# ---------------------------------------------------------------- end of the family settings file


def in_background() -> bool:
    """True inside a family background call: hooks should exit before doing anything."""
    return os.environ.get(ENV) == "1"


def child_env(extra: dict | None = None) -> dict:
    """The environment for a background `claude -p`: the parent's, marked as background."""
    return {**os.environ, **(extra or {}), ENV: "1"}


def setting() -> str:
    """"ask" (never answered), "on" or "off"."""
    value = read_settings().get(KEY)
    return value if value in CHOICES else DEFAULT


def set_setting(value: str) -> None:
    if value not in CHOICES:
        raise ValueError(f"{KEY} must be one of {', '.join(CHOICES)}")
    update_settings(**{KEY: value})


def allowed(asked: bool = False) -> bool:
    """May a background call start now? `asked=True` when the person requested this very call
    (a command they ran) or already agreed for this plugin: then only "off" stops it."""
    value = setting()
    return value == "on" or (value == "ask" and asked)


def record(plugin: str, purpose: str, model: str = "", ran: bool = True) -> None:
    """One line per call started (or skipped by the setting); never raises."""
    entry = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "plugin": plugin,
             "purpose": purpose, "model": model, "ran": ran}
    try:
        nexika_home().mkdir(parents=True, exist_ok=True)
        fd = os.open(nexika_home() / "background.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def counts(days: int = 30) -> dict[str, dict[str, int]]:
    """{plugin: {"ran": n, "skipped": n}} over the last `days` days."""
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    out: dict[str, dict[str, int]] = {}
    try:
        lines = (nexika_home() / "background.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or str(entry.get("ts", "")) < since:
            continue
        row = out.setdefault(str(entry.get("plugin") or "?"), {"ran": 0, "skipped": 0})
        row["ran" if entry.get("ran") else "skipped"] += 1
    return out


def status_text(days: int = 30) -> str:
    rows = counts(days)
    lines = [f"Background model calls: {setting()} (set with: python3 {Path(__file__).resolve()} "
             "on|off|ask). Each one runs Claude in the background on your plan or API credits."]
    if not rows:
        lines.append(f"None in the last {days} days.")
    for plugin, row in sorted(rows.items()):
        lines.append(f"- {plugin}: {row['ran']} ran, {row['skipped']} skipped (last {days} days)")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd in CHOICES:
        set_setting(cmd)
        print(f"Background model calls: {cmd}")
        return 0
    if cmd == "status":
        print(status_text())
        return 0
    print("usage: background.py [status|ask|on|off]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
