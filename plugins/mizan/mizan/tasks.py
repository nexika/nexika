"""The session's task list: where Claude stands ("3/7: Writing tests").

The mod follows TodoWrite and TaskCreate/TaskUpdate calls live and sends the list; the status line
fallback reads the last TodoWrite from the end of the transcript instead. A session that works through
Agent calls and keeps no list gets one from its agents: those started since the person's last
message, each done when its result (or, for a background agent, its task notification) came back.
"""
from __future__ import annotations

import json
import os
import re

TAIL_BYTES = 4 * 1024 * 1024
STATUSES = ("pending", "in_progress", "completed")
NOTICE = re.compile(r"<task-notification>.*?<tool-use-id>([\w-]+)</tool-use-id>.*?<status>(\w+)</status>", re.S)
FINISHED = ("completed", "failed", "killed", "stopped", "error")


def summarize(items: list[dict]) -> dict:
    items = [i for i in items if isinstance(i, dict) and i.get("status") in STATUSES]
    total = len(items)
    done = sum(1 for i in items if i["status"] == "completed")
    current = next((i for i in items if i["status"] == "in_progress"), None)
    if current is None:
        current = next((i for i in items if i["status"] == "pending"), None)
    step = items.index(current) + 1 if current else done
    text = ""
    if current:
        active = current.get("active") if current["status"] == "in_progress" else ""
        text = active or current.get("text", "")
    return {"items": items, "total": total, "done": done, "step": step, "current": text,
            "all_done": bool(total) and done == total}


def from_todos(todos: list) -> list[dict]:
    return [{"text": str(t.get("content", "")), "status": t.get("status", "pending"),
             "active": str(t.get("activeForm", ""))} for t in todos if isinstance(t, dict)]


def _tail(path: str) -> list[str]:
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            return fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(row: dict) -> bool:
    """A message the person typed: not a tool result, a notification or the engine's own note."""
    if row.get("type") != "user" or row.get("isMeta"):
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    text = _text_of(content)
    return bool(text.strip()) and "<task-notification>" not in text


def agents_from_transcript(path: str) -> list[dict]:
    """The Agent calls since the person's last message: {id, type, description, status running|completed}."""
    rows = []
    for line in _tail(path):
        if '"Agent"' not in line and '"type":"user"' not in line and '"type": "user"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    start = next((i for i in range(len(rows) - 1, -1, -1) if _is_prompt(rows[i])), -1)
    found: dict[str, dict] = {}
    for row in rows[start + 1:]:
        content = (row.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Agent" and block.get("id"):
                given = block.get("input") or {}
                found[block["id"]] = {"id": block["id"], "type": str(given.get("subagent_type") or "general-purpose"),
                                      "description": str(given.get("description") or ""), "status": "running"}
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in found:
                launched = (row.get("toolUseResult") or {}).get("status") == "async_launched" \
                    if isinstance(row.get("toolUseResult"), dict) else "launched" in _text_of(block.get("content"))
                if not launched:
                    found[block["tool_use_id"]]["status"] = "completed"
        for use_id, state in NOTICE.findall(_text_of(content)):
            if use_id in found and state in FINISHED:
                found[use_id]["status"] = "completed"
    return list(found.values())


def from_agents(agents: list[dict]) -> list[dict]:
    """Agents as task items: a running one is in progress, a finished one (even failed) is done."""
    return [{"text": str(a.get("description") or a.get("type") or ""),
             "status": "completed" if a.get("status") in FINISHED else "in_progress",
             "active": str(a.get("description") or "")} for a in agents if isinstance(a, dict)]


def from_transcript(path: str) -> list[dict]:
    """The todos of the last TodoWrite call in a transcript (JSON lines), [] when none."""
    lines = _tail(path)
    for line in reversed(lines):
        if '"TodoWrite"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        content = (row.get("message") or {}).get("content") or []
        for block in reversed(content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") == "tool_use" \
                    and block.get("name") == "TodoWrite":
                return from_todos((block.get("input") or {}).get("todos") or [])
    return []
