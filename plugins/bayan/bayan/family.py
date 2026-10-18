"""The Nexika family profile: who the user is, set once for every plugin.

The family settings file, ~/.claude/nexika/settings.json (NEXIKA_HOME moves the folder), holds
one role (#108: it used to live in profile.json, which is moved in once):

    developer   writes code every day: technical words are fine, answer instead of teaching
    learner     learning to code: explain new terms, teach and check understanding
    writer      writes prose, not code: everyday words

Each plugin turns the role into its own defaults (bayan's reader level, prof's teaching, siyaq's
match threshold); a setting made in the plugin itself still wins. With no role, the plugins assume
a developer (DEFAULT_ROLE): most people running Claude Code write code. prof still teaches someone
who has lessons on record. The first session note asks once (ask_note); later sessions don't ask.

Answer from the command line:  python3 family.py role developer|learner|writer
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROLES = ("developer", "learner", "writer")
DEFAULT_ROLE = "developer"


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


def _merged() -> tuple[dict | None, bool]:
    """The settings with an older profile.json folded in (the settings file wins where both say
    something), and whether that still has to be saved; None when the file is unreadable."""
    data = _load(settings_path())
    if data is None:
        return None, False
    old = _old_profile()
    try:
        moving = old.is_file()
    except OSError:
        moving = False
    if not moving and (not data or data.get("schema") == SETTINGS_SCHEMA):
        return data, False
    profile = (_load(old) or {}) if moving else {}
    return {**{k: profile[k] for k in _FROM_PROFILE if k in profile}, **data}, True


def _save_merged(data: dict) -> None:
    """Save, and set an older profile.json aside as profile.json.migrated, so it moves in once."""
    _save(data)
    old = _old_profile()
    if old.is_file():
        os.replace(old, old.with_name(old.name + ".migrated"))


def read_settings() -> dict:
    """The family settings. The first read moves an older profile.json in."""
    data, pending = _merged()
    if not pending:
        return data or {}  # unreadable: a read never overwrites it, only a save does
    with _locked():
        data, pending = _merged()  # another session may have moved it in meanwhile
        try:
            if pending:
                _save_merged(data)
        except OSError:
            pass  # read-only home: still answer from what was read
    return data or {}


def _locked():
    """Hold the settings lock while a change reads and saves, so two sessions saving at once both
    keep their change (#394). Without a file lock (Windows, some network homes) changes go through
    unlocked."""
    import contextlib
    try:
        import fcntl
        nexika_home().mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(nexika_home() / ".settings.lock", os.O_WRONLY | os.O_CREAT, 0o600)
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


def update_settings(**changes) -> dict:
    with _locked():
        data, pending = _merged()
        data = {**(data or {}), **changes}
        (_save_merged if pending else _save)(data)
    return data

# ---------------------------------------------------------------- end of the family settings file


def role() -> str:
    """The role the user chose, or '' when not chosen."""
    value = read_settings().get("role")
    return value if value in ROLES else ""


def save_role(value: str) -> None:
    if value not in ROLES:
        raise ValueError(f"role must be one of: {', '.join(ROLES)}")
    update_settings(role=value)


def ask_note(helper: str) -> str:
    """The once-only question for a session note, or '' when the role is set or was already asked.
    Showing it records the ask, so the other plugins (and later sessions) stay quiet."""
    data = read_settings()
    if data.get("role") in ROLES or data.get("asked"):
        return ""
    try:
        update_settings(asked=datetime.date.today().isoformat())
    except OSError:
        return ""
    return ("Nexika profile: not set yet, so the plugins assume a developer. Ask the user once, in one "
            "short question, which fits best: developer (writes code every day), learner (learning to "
            f"code) or writer (writes prose, not code). Save the answer with `{helper} role <answer>`. "
            "If they skip it, don't ask again.")


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "role":
        try:
            save_role(argv[2])
        except (ValueError, OSError) as exc:
            print(f"profile: {exc}", file=sys.stderr)
            return 2
    elif argv[1:] not in ([], ["role"]):
        print(f"usage: {argv[0]} [role {'|'.join(ROLES)}]", file=sys.stderr)
        return 2
    print(f"Nexika profile ({settings_path()}): role {role() or DEFAULT_ROLE + ' (not chosen, the default)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
