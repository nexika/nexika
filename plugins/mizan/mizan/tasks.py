"""The session's task list: where Claude stands ("3/7: Writing tests").

The mod follows TodoWrite and TaskCreate/TaskUpdate calls live and sends the list; the status line
fallback reads the last TodoWrite from the end of the transcript instead.
"""
from __future__ import annotations

import json
import os

TAIL_BYTES = 4 * 1024 * 1024
STATUSES = ("pending", "in_progress", "completed")


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


def from_transcript(path: str) -> list[dict]:
    """The todos of the last TodoWrite call in a transcript (JSON lines), [] when none."""
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
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
