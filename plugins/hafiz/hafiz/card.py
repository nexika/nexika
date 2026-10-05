"""What Claude is told: the short start card, the handoff note, and the snapshot around compaction.

All three are built in priority order and cut to a character budget, so the most useful lines
always fit: the start card stays under 1.5 KB to share the startup budget with other plugins.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import capture, search, store

CARD_CHARS = 1500
RESTORE_CHARS = 3000
ISSUE_IN_BRANCH = re.compile(r"(?:^|/)(?:issue[-_]?|gh[-_]?|#)?(\d{1,6})(?=[-_/]|$)", re.I)
DATE_OR_VERSION = re.compile(r"^(?:(?:19|20)\d\d[-_.](?:\d|q\d)|\d+[._]\d)", re.I)


def issue_from_branch(name: str) -> str:
    """'feat/123-login' -> '123', 'fix/issue-45' -> '45', 'GH-7' -> '7'; '' for dates, versions, none."""
    for match in ISSUE_IN_BRANCH.finditer(name or ""):
        if not DATE_OR_VERSION.match((name or "")[match.start(1):]):
            return match.group(1)
    return ""


def fit(lines: list[str], budget: int) -> str:
    """Whole lines in order while they fit in `budget` bytes (UTF-8: Arabic letters count double)."""
    out, used = [], 0
    for line in lines:
        if not line:
            continue
        size = len(line.encode()) + 1
        if used + size > budget:
            room = budget - used - 5  # the "…" takes 3 bytes, the newline 1
            if room > 40:
                cut = line.encode()[:room].decode(errors="ignore")
                out.append(cut.rsplit(" ", 1)[0] + "…")
            break
        out.append(line)
        used += size
    return "\n".join(out)


def _join(items: list[str], limit: int, width: int = 90) -> str:
    shown = [i if len(i) <= width else i[: width - 1] + "…" for i in items[:limit]]
    more = f" (+{len(items) - limit})" if len(items) > limit else ""
    return "; ".join(shown) + more


def open_tasks(state: dict) -> list[str]:
    return [t["text"] for t in state.get("tasks", {}).values() if t["status"] == "open"]


def done_tasks(state: dict) -> list[str]:
    return [t["text"] for t in state.get("tasks", {}).values() if t["status"] == "done"]


def problems(state: dict, status: str) -> list[str]:
    return [p["text"] for p in state.get("problems", {}).values() if p["status"] == status]


def problem_title(text: str) -> str:
    """Only the failing command of an automatic problem: tool output is never put in a card, since it
    can carry text written to steer Claude. The details stay available through `recall`."""
    match = re.match(r"(`[^`]+`) failed", text)
    return f"{match.group(1)} failing (details: recall)" if match else text


def files(state: dict) -> list[str]:
    return [f for f, _ in sorted(state.get("files", {}).items(), key=lambda kv: -kv[1])]


# ------------------------------------------------------------------ sessions


def sessions(folder: Path) -> list[dict]:
    """Saved session states, most recently active first (empty sessions left out)."""
    out = []
    for path in (folder / "sessions").glob("*.json"):
        state = store.read_json(path, {})
        if state.get("session") and state.get("prompt_count"):
            out.append(state)
    return sorted(out, key=lambda s: s.get("updated", ""), reverse=True)


def last_session(folder: Path, branch: str = "", exclude: str = "") -> dict:
    for state in sessions(folder):
        if state["session"] != exclude and (not branch or state.get("branch") == branch):
            return state
    return {}


# ------------------------------------------------------------------ handoff


def handoff_text(state: dict) -> str:
    branch = state.get("branch") or "(no branch)"
    issue = issue_from_branch(branch)
    lines = [f"# Handoff: {branch}{f' (issue #{issue})' if issue else ''}",
             f"Session {state['session'][:8]}, {state.get('started', '')[:16].replace('T', ' ')} to "
             f"{(state.get('ended') or state.get('updated') or '')[:16].replace('T', ' ')}, "
             f"{state.get('prompt_count', 0)} messages"]
    if state.get("note"):
        lines += ["", "## Where we stopped", state["note"]]
    if state.get("first_prompt"):
        lines += ["", "## Goal", state["first_prompt"]]
    sections = [
        ("Latest requests", state.get("prompts", [])[-3:]),
        ("Open tasks", open_tasks(state)),
        ("Done", done_tasks(state)),
        ("Decisions", state.get("decisions", [])),
        ("Open problems", problems(state, "open")),
        ("Solved problems", problems(state, "solved")),
        ("Files changed", files(state)[:25]),
        ("Commits", [f"{c['hash']} {c['message']}" for c in state.get("commits", [])]),
        ("Links", state.get("links", [])),
    ]
    for title, items in sections:
        if items:
            lines += ["", f"## {title}", *[f"- {i}" for i in items]]
    return "\n".join(lines) + "\n"


def write_handoff(folder: Path, state: dict) -> Path | None:
    """The handoff note of the latest session on a branch (empty sessions never overwrite it)."""
    if not state.get("prompt_count"):
        return None
    path = folder / "handoffs" / f"{store.safe_name(state.get('branch') or 'no-branch')}.md"
    store.write_text(path, handoff_text(state))
    return path


def read_handoff(folder: Path, branch: str) -> str:
    try:
        return (folder / "handoffs" / f"{store.safe_name(branch or 'no-branch')}.md").read_text(
            encoding="utf-8")
    except OSError:
        return ""


# ------------------------------------------------------------------ start card


def start_card(root: Path, branch: str, helper: str, session: str = "", budget: int = CARD_CHARS) -> str:
    memory = store.Memory(root)
    items = memory.all()
    last = last_session(memory.dir, branch, exclude=session)
    issue = issue_from_branch(branch)
    head = f"## hafiz (Nexika): memory of this project, branch {branch or '(none)'}"
    if issue:
        head += f" (issue #{issue})"
    lines = [head]
    if not items and not last:
        lines.append("No memories yet. Decisions, tasks, problems, files and links are captured as you "
                     "work; nothing is sent anywhere.")
    else:
        lines.append(f"{len(items)} memories. Use them only when relevant; check the code before relying "
                     "on one.")
        elsewhere = {} if last else last_session(memory.dir, exclude=session)
        for state, where in ((last, "here"), (elsewhere, f"on {elsewhere.get('branch') or '(no branch)'}")):
            if state:
                when = state.get("updated", "")[:16].replace("T", " ")
                latest = state.get("note") or (state.get("prompts") or [state.get("first_prompt", "")])[-1]
                lines.append(f"Last session {where} ({when}, {state['session'][:8]}): {latest}")
        mine = search.newest_first([i for i in items if search.keep(i, branch=branch)])
        todo = [i["text"] for i in mine if i["type"] == "task" and i.get("status") == "open"]
        failing = [problem_title(i["text"]) for i in mine
                   if i["type"] == "problem" and i.get("status") == "open"]
        decisions = [i["text"] for i in mine if i["type"] == "decision"]
        if todo:
            lines.append("Open tasks: " + _join(todo, 4))
        if failing:
            lines.append("Open problems: " + _join(failing, 2, 140))
        if decisions:
            lines.append("Recent decisions: " + _join(decisions, 3, 140))
        if last.get("files"):
            lines.append("Files in play: " + _join(files(last), 6, 60))
    lines.append(f"Recall: `{helper} recall \"words\"` (or /hafiz:recall); handoff: /hafiz:handoff.")
    return fit(lines, budget)


# ------------------------------------------------------------------ compaction


def snapshot(folder: Path, state: dict) -> Path:
    data = {
        "created": store.now(), "session": state["session"], "branch": state.get("branch", ""),
        "goal": state.get("first_prompt", ""), "prompts": state.get("prompts", [])[-3:],
        "note": state.get("note", ""), "tasks": open_tasks(state), "done": done_tasks(state)[-5:],
        "decisions": state.get("decisions", [])[-8:],
        "problems": [problem_title(p) for p in problems(state, "open")],
        "files": files(state)[:15],
        "commits": [f"{c['hash']} {c['message']}" for c in state.get("commits", [])],
    }
    path = folder / "snapshots" / f"{store.safe_name(state['session'], 64)}.json"
    store.write_json(path, data)
    return path


def restore_text(folder: Path, session: str, helper: str, budget: int = RESTORE_CHARS) -> str:
    data = store.read_json(folder / "snapshots" / f"{store.safe_name(session, 64)}.json", {})
    if not data:
        return ""
    lines = ["## hafiz: restored after compaction",
             f"The conversation was just compacted. Before it, on branch {data.get('branch') or '(none)'}:"]
    if data.get("note"):
        lines.append(f"Where we stopped: {data['note']}")
    if data.get("goal"):
        lines.append(f"Goal of this session: {data['goal']}")
    lines += [f"Latest request: {p}" for p in data.get("prompts", [])[-2:]]
    for title, key, limit in (("Open tasks", "tasks", 8), ("Decisions", "decisions", 6),
                              ("Open problems", "problems", 3), ("Files changed", "files", 12),
                              ("Commits", "commits", 5), ("Done", "done", 5)):
        if data.get(key):
            lines.append(f"{title}: " + _join(data[key], limit, 160))
    lines.append(f"More: `{helper} recall \"words\"`.")
    return fit(lines, budget)


def current_state(folder: Path, branch: str = "") -> dict:
    """What the CLI means by "this session": the latest active one on this branch, else in the project.

    Worktrees share one memory, so the branch keeps a command in one worktree from writing into a
    session running in another.
    """
    found = last_session(folder, branch) if branch else {}
    found = found or last_session(folder)
    return capture.load_state(folder, found["session"]) if found else {}
