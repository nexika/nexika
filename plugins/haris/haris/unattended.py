"""Unattended sessions (#343): nobody is there to answer haris's questions.

In `claude -p`, CI or a background session an ask cannot be answered, so it ends as a refusal
anyway. There haris
  - lets an ask pass when every question in it is about a reversible change inside the project
    (MAY_PASS), and logs it, so /haris:audit and the end-of-run summary show it;
  - refuses every other ask itself, with its reason, so the agent learns why and what to do instead.
Everything haris refuses today stays refused. A session counts as unattended only on a clear signal;
an unknown session is attended.

Plain functions over plain values: the hook passes the environment and the project folder in.
"""
from __future__ import annotations

import json
import os

# The questions that may pass unattended: deleting files inside the project that git or a rebuild
# gives back (strict asks about deletes). Never a secret, a path outside the project or unknown, the
# network, publishing, pushing, destructive git (discard, history-rewrite), hidden code (dynamic) or a
# user's own ask rule.
MAY_PASS = frozenset({"delete"})
# What else the command may do: only read. Anything that writes, runs a program or links could put
# something else where a target was checked (`ln -s ~ build && rm -rf build/`).
BESIDE = frozenset({"read"})
TRUE = ("1", "true", "yes")


def detect(env, cwd: str, setting: str = "auto") -> str:
    """Why this session is unattended, or "" when someone may be there (the default).

    Claude Code says so itself (CLAUDE_CODE_SESSION_ATTENDED, set for every hook): 1 is attended, 0 is
    `claude -p` or a background session. Without it: HARIS_UNATTENDED=1, or CI=true. A signal that
    Claude settings in a project folder set (.claude/settings*.json "env" in the working folder, the
    Claude Code project folder or any folder above them below home) does not count: a cloned repository,
    or a submodule in it, must not be able to loosen haris."""
    if setting == "off":
        return ""
    attended = str(env.get("CLAUDE_CODE_SESSION_ATTENDED") or "").strip()
    if attended == "1":
        return ""
    if attended == "0":
        name, why = "CLAUDE_CODE_SESSION_ATTENDED", "Claude Code reports that no one attends this session"
    elif str(env.get("HARIS_UNATTENDED") or "").strip().lower() in TRUE:
        name, why = "HARIS_UNATTENDED", "HARIS_UNATTENDED is set"
    elif str(env.get("CI") or "").strip().lower() in TRUE:
        name, why = "CI", "it runs in CI"
    else:
        return ""
    return "" if name in project_env(project_folders(cwd, str(env.get("CLAUDE_PROJECT_DIR") or ""))) else why


def project_folders(*starts: str) -> list[str]:
    """Each start folder and the folders above it, stopping before home (whose .claude is the user's own)
    and the root."""
    home = os.path.realpath(os.path.expanduser("~"))
    out: list[str] = []
    for start in starts:
        folder = os.path.realpath(start) if start else ""
        while folder and folder not in (home, os.path.dirname(folder)) and folder not in out:
            out.append(folder)
            folder = os.path.dirname(folder)
    return out


def project_env(folders: list[str]) -> set[str]:
    """The environment variables Claude Code settings in these folders set."""
    names: set[str] = set()
    for folder in folders:
        names |= settings_env(folder)
    return names


def settings_env(root: str) -> set[str]:
    names: set[str] = set()
    for name in ("settings.json", "settings.local.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        env = data.get("env") if isinstance(data, dict) else None
        if isinstance(env, dict):
            names |= {str(k) for k in env}
    return names


def may_pass(asked: list, findings: list, restorable) -> bool:
    """Whether an ask may pass unattended: every finding it asks about is a delete that `restorable(path)`
    accepts (git or a rebuild gives it back), and the command does nothing else but read. `asked` holds
    the findings whose verdict is ask, `findings` all of them."""
    return bool(asked) and all(f.cls in MAY_PASS and f.target and restorable(f.target) for f in asked) \
        and all(f in asked or f.cls in BESIDE | MAY_PASS for f in findings)


PASS_NOTE = ("Passed without a question: this session is unattended ({why}), and git or a rebuild gives "
             "back what this deletes. haris logged it; /haris:audit shows it.")
DENY_NOTE = (" Nobody can answer a question in this session ({why}), so haris refuses what it would "
             "otherwise ask about. Find a way that stays inside the project, or leave this step for the "
             "user and say so.")


def summary(passed: list[str], refused: int) -> str:
    """The end-of-run note: the asks that passed unattended, and how many were refused."""
    lines = [f"haris: this unattended run let {len(passed)} question(s) pass and refused {refused} "
             "it would have asked about."]
    lines += [f"  - {p}" for p in passed[-10:]]
    if len(passed) > 10:
        lines.append(f"  ... and {len(passed) - 10} more")
    lines.append("haris audit --decision unattended lists them all.")
    return "\n".join(lines)
