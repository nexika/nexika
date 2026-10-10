"""Claude Code hooks: inject matching knowledge on prompts and on files being touched."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import index as idx
from . import rank, state, text

FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
HEADER = ("siyaq: project knowledge matched to this {what} (from the repo's docs; if they disagree "
          "with the code, trust the code and mention the mismatch):\n\n")
# Read again on every turn (#345): the knowledge itself comes with the prompt or file it matches, so
# the note only says so and names the helper (the skills run it; `match` searches on demand).
NOTE = ("siyaq (Nexika): project knowledge is added when a prompt or a file you touch matches it. "
        "siyaq helper: {helper} (match TEXT | entries | stats | index)")


def _context(event: dict) -> tuple[Path, dict] | None:
    root = idx.project_root(Path(event.get("cwd") or os.getcwd()))
    config = idx.load_config(root)
    if os.environ.get("SIYAQ", "").lower() == "off" or config.get("mode") == "off":
        return None
    return root, config


def context_level(session: str) -> str:
    """mizan's context level for this session (fresh, mid, full), from its status file
    (~/.claude/nexika/status/mizan/<session>.json, schema nexika.mizan/1); '' when unknown or stale."""
    if not re.match(r"^[A-Za-z0-9_-]{1,80}$", session or ""):
        return ""
    home = Path(os.path.expanduser(os.environ.get("NEXIKA_STATUS_HOME") or "~/.claude/nexika/status"))
    try:
        data = json.loads((home / "mizan" / f"{session}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict) or data.get("schema") != "nexika.mizan/1":
        return ""
    if time.time() - float(data.get("updated") or 0) > 600:
        return ""
    level = data.get("level")
    return level if level in ("fresh", "mid", "full") else ""


def _output(event_name: str, context: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": context}},
                      ensure_ascii=False)


def _remember(root: Path, session: str, picked: list[dict], trigger: str) -> None:
    data = state.load_session(session)
    for p in picked:
        entry = p["entry"]
        data["shown"][entry["id"]] = p["level"]
        state.log_event(root, {"session": session[:8], "type": "shown", "id": entry["id"],
                               "level": p["level"], "score": p["score"], "chars": len(p["text"]),
                               "trigger": trigger})
    state.save_session(session, data)


def on_prompt(event: dict) -> str | None:
    prompt = text.typed_words(str(event.get("prompt") or ""))
    if not prompt:
        return None
    ctx = _context(event)
    if not ctx:
        return None
    root, config = ctx
    if prompt.startswith("/"):
        prompt = prompt.split(maxsplit=1)[1] if " " in prompt else ""
    session = str(event.get("session_id") or "")
    index = idx.load_ready(root, config)
    if not index["n"]:
        return None
    cfg = rank.squeeze(rank.settings(config), context_level(session))
    with state.session_lock(session):
        picked = rank.select_for_prompt(index, prompt, cfg, state.load_session(session)["shown"])
        if picked:
            _remember(root, session, picked, "prompt")
    if not picked:
        unknown = [t for t in dict.fromkeys(text.tokens(prompt)) if t not in index["df"]]
        if unknown:
            state.log_event(root, {"session": session[:8], "type": "miss", "terms": unknown[:6]})
        return None
    return _output("UserPromptSubmit", HEADER.format(what="prompt") + "\n\n".join(p["text"] for p in picked))


def on_tool(event: dict) -> str | None:
    if event.get("tool_name") not in FILE_TOOLS:
        return None
    ctx = _context(event)
    tool_input = event.get("tool_input") or {}
    file_path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if not ctx or not file_path:
        return None
    root, config = ctx
    try:
        rel = Path(file_path).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return None
    session = str(event.get("session_id") or "")
    index = idx.load_ready(root, config)
    if event.get("tool_name") != "Read" and rel.endswith(".md") and rel not in index["sources"]:
        idx.forget_files(root)  # a new doc: the next call lists the files again and indexes it
    with state.session_lock(session):
        picked = _pick_for_path(root, rel, index, config, session, event.get("tool_name") == "Read")
    if not picked:
        return None
    return _output("PreToolUse", HEADER.format(what=f"file ({rel})") + "\n\n".join(p["text"] for p in picked))


def _pick_for_path(root: Path, rel: str, index: dict, config: dict, session: str, read: bool) -> list[dict]:
    data = state.load_session(session)
    if read:
        opened = [e["id"] for e in index["entries"]
                  if e["source"] == rel and e["id"] in data["shown"] and e["id"] not in data["opened"]]
        for entry_id in opened:
            data["opened"].append(entry_id)
            state.log_event(root, {"session": session[:8], "type": "opened", "id": entry_id})
        if opened:
            state.save_session(session, data)
    picked = rank.select_for_path(index, rel, rank.squeeze(rank.settings(config), context_level(session)),
                                  data["shown"])
    if picked:
        _remember(root, session, picked, "path")
    return picked


def on_session_start(event: dict, helper: str) -> str:
    session = str(event.get("session_id") or "")
    if session and event.get("source") in ("compact", "clear"):
        state.reset_session(session)  # Claude no longer has what was injected before
    state.gc()
    ctx = _context(event)
    if not ctx:
        return ""
    root, config = ctx
    idx.load_ready(root, config, wait=idx.SESSION_START_WAIT)  # starts or refreshes the index
    return NOTE.format(helper=helper)
