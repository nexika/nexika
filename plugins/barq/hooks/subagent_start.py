#!/usr/bin/env python3
"""SubagentStart hook: give the subagent its own seen-before cache. A subagent starts with an
empty context, so "unchanged since your read" answers meant for the main agent would leave it
without the file. Must never fail the subagent."""
from __future__ import annotations

import json
import os
import sys


def main() -> None:
    if os.environ.get("NEXIKA_BACKGROUND") == "1":
        return  # inside a family background model call: no hooks (#45)
    try:
        hook = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        hook = {}
    agent = "".join(c for c in str(hook.get("agent_id") or "") if c.isalnum() or c in "-_")[:48]
    if not agent:
        return
    context = (f"barq: you are a subagent with your own context. Start every barq command with "
               f"BARQ_AGENT={agent} (for example: BARQ_AGENT={agent} barq 'read:PATH'), so barq "
               "never answers \"unchanged\" for a file only the main agent has read.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                             "additionalContext": context}}))


if __name__ == "__main__":
    main()
