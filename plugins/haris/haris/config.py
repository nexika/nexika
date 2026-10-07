"""haris settings and the cheap facts a hook needs before it decides anything.

Kept apart from the classifier (classify.py, policy.py), which takes most of a hook's start-up
time: a hook loads the classifier only for a call haris actually checks (#50).
"""
from __future__ import annotations

import os

from . import state

PROFILES = ("relaxed", "standard", "strict")
PROFILE_INDEX = {name: i for i, name in enumerate(PROFILES)}
TAINT_TURNS = 3
READ_TOOLS = {"Read", "NotebookRead", "Grep", "Glob", "LS"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
WEB_TOOLS = {"WebFetch", "WebSearch"}


def checked(tool: str) -> bool:
    """Whether haris has anything to say about this tool (policy.findings_for). Every other tool
    (TodoWrite, Task, Skill, ...) always passes, so its hook can leave before loading the classifier."""
    return tool in SHELL_TOOLS | READ_TOOLS | WRITE_TOOLS | WEB_TOOLS or tool.startswith("mcp__")


# ---------------------------------------------------------------- settings


def _strings(value) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def effective_config(root: str) -> dict:
    """Your settings, then the repository's, which can only make haris stricter."""
    user, repo = state.user_config(), state.repo_config(root)
    def known(value, names) -> bool:
        return isinstance(value, str) and value in names

    profile = user.get("profile") if known(user.get("profile"), PROFILE_INDEX) else "standard"
    if known(repo.get("profile"), PROFILE_INDEX) and PROFILE_INDEX[repo["profile"]] > PROFILE_INDEX[profile]:
        profile = repo["profile"]
    mode = user.get("mode") if known(user.get("mode"), ("on", "watch", "off")) else "on"
    turns = user.get("taint_turns", TAINT_TURNS)
    turns = turns if isinstance(turns, int) and 0 <= turns <= 50 else TAINT_TURNS
    repo_turns = repo.get("taint_turns")
    if isinstance(repo_turns, int) and turns < repo_turns <= 50:
        turns = repo_turns
    secret_globs = _strings(user.get("secret_paths"))
    secret_globs += [g if g.startswith("/") else os.path.join(root,
                                                              g) for g in _strings(repo.get("secret_paths"))]
    return {
        "profile": profile, "mode": mode, "taint_turns": turns,
        "ask": _strings(user.get("ask")) + _strings(repo.get("ask")),
        "deny": _strings(user.get("deny")) + _strings(repo.get("deny")),
        "allow": _strings(user.get("allow")),
        "protected_branches": (_strings(user.get("protected_branches"))
                               + _strings(repo.get("protected_branches"))),
        "secret_paths": secret_globs,
        "sources": [p for p, d in (("~/.claude/nexika/haris/config.json", user), (".haris.json", repo)) if d],
    }


def project_root(cwd: str) -> str:
    folder = os.path.realpath(cwd)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    cwd = os.path.realpath(cwd)
    home = os.path.realpath(os.path.expanduser("~"))
    if home == cwd or home.startswith(cwd.rstrip("/") + "/"):
        # Home, / or a folder above home is no project: nothing in it may count as project files.
        return os.path.join(cwd, ".haris-no-project")
    return cwd


def normalize(command: str) -> str:
    return " ".join(command.split())
