"""Claude Code hooks: capture as you work, a short card at start, a snapshot around compaction.

    SessionStart  startup/resume/clear: the start card; compact: what was in play before it
    Stop          after every reply: read what is new, update memories and the handoff note
    PreCompact    the same, then save a snapshot to restore after compaction
    SessionEnd    the same, then close the session's handoff note
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import capture, card, export, store


def _context(event: dict) -> tuple[Path, Path, dict] | None:
    cwd = Path(event.get("cwd") or os.getcwd())
    root = store.project_root(cwd)
    config = store.load_config(store.worktree_root(cwd))
    if not store.enabled(config):
        return None
    return cwd, root, config


def _output(event_name: str, context: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": context}},
                      ensure_ascii=False)


def _capture(event: dict) -> tuple[Path, dict] | None:
    ctx = _context(event)
    session = str(event.get("session_id") or "")
    if not ctx or not session or session != store.safe_name(session, 64):
        return None
    cwd, root, _ = ctx
    state = capture.update(root, session, str(event.get("transcript_path") or ""), str(cwd))
    return root, state


def _publish(root: Path, state: dict) -> None:
    card.write_handoff(store.project_dir(root), state)
    export.write_latest(root, state)


def save_now(session: str, transcript: str, cwd: str) -> bool:
    """Capture now and write the handoff note, as after a reply (mizan asks for it as context fills).

    Only a session transcript (a .jsonl file under Claude Code's projects folder) is read.
    """
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"
    projects = (Path(os.path.expanduser(config_dir)) / "projects").resolve()
    path = Path(transcript).resolve() if transcript else None
    if not path or path.suffix != ".jsonl" or projects not in path.parents or not path.is_file():
        return False
    done = _capture({"session_id": session, "transcript_path": str(path), "cwd": cwd})
    if done:
        _publish(*done)
    return bool(done)


def on_session_start(event: dict, helper: str) -> str:
    ctx = _context(event)
    if not ctx:
        return ""
    cwd, root, config = ctx
    folder = store.project_dir(root)
    store.gc(folder)
    session = str(event.get("session_id") or "")
    if event.get("source") == "compact" and session:
        restored = card.restore_text(folder, session, helper)
        if restored:
            return _output("SessionStart", restored)
    try:
        budget = min(int(config.get("card_chars", card.CARD_CHARS)), card.CARD_CHARS)
    except (TypeError, ValueError):
        budget = card.CARD_CHARS
    return _output("SessionStart", card.start_card(root, store.branch(cwd), helper, session, budget))


def on_stop(event: dict) -> str:
    done = _capture(event)
    if done:
        _publish(*done)
    return ""


def on_pre_compact(event: dict) -> str:
    done = _capture(event)
    if done:
        root, state = done
        folder = store.project_dir(root)
        state["compactions"] = state.get("compactions", 0) + 1
        capture.save_state(folder, state)
        card.snapshot(folder, state)
        _publish(root, state)
    return ""


def on_session_end(event: dict) -> str:
    done = _capture(event)
    if done:
        root, state = done
        state["ended"] = store.now()
        capture.save_state(store.project_dir(root), state)
        _publish(root, state)
    return ""
