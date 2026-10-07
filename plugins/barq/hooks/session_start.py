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

# barq complements the built-in tools, it doesn't replace them: Read, Grep and Glob stay Claude's
# way to look at files (Edit needs a prior Read), and barq covers what they can't do in one call.
USAGE = """## barq ⚡ (Nexika): test results, git status and code outlines, short
Keep using Read, Grep and Glob to look at files (Edit needs a Read first). Use barq for:
  {cmd} run:test  run:build  run:lint      only the verdict, the failures and the errors
  {cmd} git-status                         branch, ahead/behind, changes, and the next step
  {cmd} 'read:PATH:outline' 'read:PATH@Symbol' 'map[:PATH]'   signatures, one symbol, a folder
  {cmd} info                               languages, stacks and the build/test/lint commands
Several ops in one command run in one call. Quote every op (the shell would expand `*` and `@`).
Never copy a [masked] line into an edit; Read the file instead."""


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
