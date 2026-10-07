"""The contract other Nexika plugins read: `hafiz export --json` and latest-session.json.

Schema "nexika.hafiz/1". Fields are only ever added within a schema version; readers must
ignore fields they do not know. Text is already redacted (no secrets, no <private> spans).

    schema, generated, project {name, root, data}, branch, issue,
    latest_session {id, branch, started, updated, ended, goal, note, open_tasks, done_tasks,
                    decisions, open_problems, solved_problems, files, commits, links, handoff},
    memories {decision, task, problem, file, link: [{id, type, text, date, branch, commit,
              session, source, status, scope}]}      (export only; open tasks and problems)
    counts {decision, task, problem, file, link}       (export only)
"""
from __future__ import annotations

from pathlib import Path

from . import card, search, store

SCHEMA = "nexika.hafiz/1"
PUBLIC = ("id", "type", "text", "date", "branch", "commit", "session", "source", "status", "scope", "reason")


def session_view(folder: Path, state: dict) -> dict:
    if not state:
        return {}
    handoff = folder / "handoffs" / f"{store.safe_name(state.get('branch') or 'no-branch')}.md"
    return {
        "id": state["session"], "branch": state.get("branch", ""), "started": state.get("started", ""),
        "updated": state.get("updated", ""), "ended": state.get("ended", ""),
        "goal": state.get("first_prompt", ""), "note": state.get("note", ""),
        "open_tasks": card.open_tasks(state), "done_tasks": card.done_tasks(state),
        "decisions": state.get("decisions", []), "open_problems": card.problems(state, "open"),
        "solved_problems": card.problems(state, "solved"), "files": card.files(state),
        "commits": state.get("commits", []), "links": state.get("links", []),
        "handoff": str(handoff) if handoff.is_file() else "",
    }


def header(root: Path, branch: str) -> dict:
    return {"schema": SCHEMA, "generated": store.now(),
            "project": {"name": root.name, "root": str(root), "data": str(store.project_dir(root))},
            "branch": branch, "issue": card.issue_from_branch(branch)}


def latest(root: Path, state: dict) -> dict:
    folder = store.project_dir(root)
    return {**header(root, state.get("branch", "")), "latest_session": session_view(folder, state)}


def write_latest(root: Path, state: dict) -> None:
    if state.get("prompt_count"):
        store.write_json(store.project_dir(root) / "latest-session.json", latest(root, state))


def full(root: Path, branch: str = "", limit: int = 20) -> dict:
    memory = store.Memory(root)
    items = search.newest_first(memory.all())
    if branch:
        items = [i for i in items if search.keep(i, branch=branch)]
    state = card.last_session(memory.dir, branch) or card.last_session(memory.dir)
    groups: dict[str, list[dict]] = {}
    counts = {}
    for kind in store.TYPES:
        of_kind = [i for i in items if i["type"] == kind]
        counts[kind] = len(of_kind)
        if kind in ("task", "problem"):
            of_kind = [i for i in of_kind if i.get("status") == "open"]
        groups[kind] = [{k: i.get(k, "") for k in PUBLIC} for i in of_kind[:limit]]
    return {**header(root, branch or state.get("branch", "")),
            "latest_session": session_view(memory.dir, state), "memories": groups, "counts": counts}
