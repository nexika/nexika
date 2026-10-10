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

# The questions that may pass unattended: deleting files inside the project (strict asks about it;
# git or a rebuild restores them). Never a secret, a path outside the project or unknown, the network,
# publishing, pushing, destructive git (discard, history-rewrite), hidden code (dynamic) or a user's
# own ask rule.
MAY_PASS = frozenset({"delete"})
TRUE = ("1", "true", "yes")


def detect(env, root: str, setting: str = "auto") -> str:
    """Why this session is unattended, or "" when someone may be there (the default).

    Claude Code says so itself (CLAUDE_CODE_SESSION_ATTENDED, set for every hook): 1 is attended, 0 is
    `claude -p` or a background session. Without it: HARIS_UNATTENDED=1, or CI=true. A signal the
    project's own Claude settings set (.claude/settings*.json "env") does not count: a cloned
    repository must not be able to loosen haris."""
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
    return "" if name in project_env(root) else why


def project_env(root: str) -> set[str]:
    """The environment variables the project's Claude Code settings set."""
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


def may_pass(asked: list, inside) -> bool:
    """Whether an ask may pass unattended: every finding it asks about is a reversible change inside the
    project. `asked` holds the findings whose verdict is ask; `inside(path)` says whether a path is an
    ordinary place in the project (not .git, CI or Claude settings)."""
    return bool(asked) and all(f.cls in MAY_PASS and f.target and inside(f.target) for f in asked)


PASS_NOTE = ("Passed without a question: this session is unattended ({why}), and this is a reversible "
             "change inside the project. haris logged it; /haris:audit shows it.")
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
