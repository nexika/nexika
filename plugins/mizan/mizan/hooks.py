"""mizan's settings hooks: the startup note, and the context-full flow for hosts without the mod.

With the mod loaded, the mod saves the handoff and fills /clear itself (it publishes "mod": true),
so the Stop hook here steps aside. Without it, the status line fallback publishes the context level
and this hook does what it can: refresh the hafiz handoff at mid, and at full save it and tell the
user to type /clear. mizan never clears or compacts a session itself.
"""
from __future__ import annotations

import json

from . import config, family, i18n, status

NOTE = ("mizan: branch, PRs, CI, device, context, cost and task step show above the prompt (/mizan opens "
        "details). Keep a TodoWrite list. At full context mizan saves a hafiz handoff and puts /clear in the "
        "prompt for the user; never clear or compact by yourself. Helper: python3 {helper}")
MID_EVERY = 3


def _output(event_name: str, **fields) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event_name, **fields}}, ensure_ascii=False)


def on_session_start(event: dict, helper: str) -> str:
    return _output("SessionStart", additionalContext=NOTE.format(helper=helper))


def _state_path(session: str):
    return config.home() / "sessions" / f"{session}.json"


def on_stop(event: dict) -> str:
    session = str(event.get("session_id") or "")
    if not status.SAFE_ID.match(session) or event.get("stop_hook_active"):
        return ""
    published = status.read("mizan", session, max_age=600)
    if not published or published.get("mod"):
        return ""
    level = published.get("level")
    path = _state_path(session)
    state = status.read_json(path)
    state["stops"] = int(state.get("stops") or 0) + 1
    message = ""
    transcript, cwd = str(event.get("transcript_path") or ""), str(event.get("cwd") or "")
    if level == "mid" and state["stops"] % MID_EVERY == 0:
        family.handoff(session, transcript, cwd)
    elif level == "full" and not state.get("warned_full"):
        saved = family.handoff(session, transcript, cwd)["saved"]
        state["warned_full"] = True
        message = i18n.t("full_type" if saved else "full_type_nosave")
    elif level in ("fresh", "mid"):
        state["warned_full"] = False
    try:
        status.write_json(path, state)
    except OSError:
        pass
    return json.dumps({"systemMessage": message}, ensure_ascii=False) if message else ""
