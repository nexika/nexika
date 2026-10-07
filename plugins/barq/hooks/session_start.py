#!/usr/bin/env python3
"""SessionStart hook: put barq on PATH, give it the session id, reset its cache after
compaction, and teach Claude how to use it. Must never fail the session."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN))

USAGE = """## barq ⚡ (Nexika): many file/project operations in ONE call
Prefer barq over separate cat/head/grep/find/ls/git status/test-runner calls: batch everything
you need next into one command. Quote every op (the shell would expand `*` and `@`).
  {cmd} 'read:PATH' 'read:PATH:START:END' 'read:PATH@Symbol' 'read:PATH:outline'
  {cmd} 'grep:REGEX[:PATH[:MAX]]' 'glob:**/*.cs' 'tree[:PATH[:DEPTH]]' 'map[:PATH]'
  {cmd} info  git-status  run:test  run:build  run:lint  stats
JSON form for args containing ':' or spaces: {cmd} '[{{"op":"grep","pattern":"a: b","path":"src"}}]'
Re-reading an unchanged file returns "unchanged"; a changed one returns a diff. If you no longer
have the content in context, use 'read:PATH:full'. Never copy a [masked] line into an edit: use
'read:PATH:raw' for exact text. `{cmd} ops` lists every op."""


def main() -> None:
    if os.environ.get("NEXIKA_BACKGROUND") == "1":
        return  # inside a family background model call: no hooks (#45)
    try:
        hook = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        hook = {}
    session = "".join(c for c in str(hook.get("session_id") or "") if c.isalnum() or c in "-_")
    source = hook.get("source", "startup")

    try:
        from barq import cache
        if session and source in ("compact", "clear"):
            cache.reset(session)  # Claude no longer holds what it read before
        cache.gc()
    except Exception:  # the hook must never break the session
        pass

    bin_dir = PLUGIN / "bin"
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    command = "barq"
    if env_file:
        try:
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(f"export BARQ_SESSION='{session}'\n")
                fh.write(f'export PATH="{bin_dir}:$PATH"\n')
        except OSError:
            env_file = None
    if not env_file:
        command = f"BARQ_SESSION={session} python3 {bin_dir / 'barq'}"
    print(USAGE.format(cmd=command))


if __name__ == "__main__":
    main()
