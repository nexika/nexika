"""Real gh JSON from psf/black (MIT), trimmed (fixtures/mizan_black.json), and a fake gh answering from it."""
from __future__ import annotations

import json
from pathlib import Path

BLACK = json.loads((Path(__file__).parent / "fixtures" / "mizan_black.json").read_text(encoding="utf-8"))


def fake_gh(answer):
    """A forge.run_tool that calls answer(argv) for the JSON gh would print, and records every call."""
    calls = []

    def tool(argv, cwd, accept_codes=(0,)):
        calls.append(argv)
        return json.dumps(answer(argv))

    tool.calls = calls
    return tool


def info_at(repo, sha: str, **over) -> dict:
    """What gitinfo.read gives for black at this commit, on its branch."""
    runs = BLACK["runs"][sha]
    return {"repo": str(repo), "branch": runs[0]["headBranch"], "head": runs[0]["headSha"], "host": "github",
            "remote": "x", **over}
