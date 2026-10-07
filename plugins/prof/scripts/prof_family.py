"""The Nexika family profile: who the user is, set once for every plugin.

~/.claude/nexika/profile.json (NEXIKA_PROFILE moves it) holds one role:

    developer   writes code every day: technical words are fine, answer instead of teaching
    learner     learning to code: explain new terms, teach and check understanding
    writer      writes prose, not code: everyday words

Each plugin turns the role into its own defaults (bayan's reader level, prof's teaching, siyaq's
match threshold); a setting made in the plugin itself still wins. With no role, each plugin keeps
its own default. The first session note asks the question once (ask_note); later sessions don't ask.

Answer from the command line:  python3 family.py role developer|learner|writer
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROLES = ("developer", "learner", "writer")
SCHEMA = "nexika.profile/1"


def path() -> Path:
    return Path(os.path.expanduser(os.environ.get("NEXIKA_PROFILE") or "~/.claude/nexika/profile.json"))


def read() -> dict:
    try:
        with open(path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def role() -> str:
    """The role the user chose, or '' when not chosen."""
    value = read().get("role")
    return value if value in ROLES else ""


def _write(data: dict) -> None:
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({**data, "schema": SCHEMA}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, target)


def save_role(value: str) -> None:
    if value not in ROLES:
        raise ValueError(f"role must be one of: {', '.join(ROLES)}")
    _write({**read(), "role": value})


def ask_note(helper: str) -> str:
    """The once-only question for a session note, or '' when the role is set or was already asked.
    Showing it records the ask, so the other plugins (and later sessions) stay quiet."""
    data = read()
    if data.get("role") in ROLES or data.get("asked"):
        return ""
    try:
        _write({**data, "asked": datetime.date.today().isoformat()})
    except OSError:
        return ""
    return ("Nexika profile: not set yet. Ask the user once, in one short question, which fits best: "
            "developer (writes code every day), learner (learning to code) or writer (writes prose, "
            "not code). Save the answer with "
            f"`{helper} role <answer>`. If they skip it, don't ask again.")


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
    print(f"Nexika profile ({path()}): role {role() or 'not chosen'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
