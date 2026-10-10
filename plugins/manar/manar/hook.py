"""manar's SessionStart note: only for a website (#336). Light imports only: this runs in every session."""
from __future__ import annotations

from pathlib import Path

from . import framework

HELPER = Path(__file__).resolve().parent.parent / "bin" / "manar"


def is_website(root: Path) -> bool:
    """Pages served to browsers: a web framework, a static site, or manar already used here. An ASP.NET
    project with no layout (a Web API) is not a website."""
    if (root / ".manar").is_dir():
        return True
    found = framework.detect(root)
    if found["framework"] == "unknown":
        return False
    return not (found["framework"] == "aspnet" and found["where"].endswith(".csproj"))


def session_note(root: Path) -> str:
    """The note for a session in root, or "" when manar has nothing to do there. Never raises."""
    try:
        if not is_website(root):
            return ""
    except Exception:  # a hook must never break the session
        return ""
    return ("## manar (Nexika): be found by search engines and AI assistants\n"
            f"/manar:audit, /manar:fix, /manar:visibility. manar helper: python3 {HELPER}")


def main(stdin_text: str, env: dict) -> int:
    """`manar hook session-start`: Claude Code's hook JSON in, the note (or nothing) out."""
    import json
    try:
        data = json.loads(stdin_text or "{}")
    except ValueError:
        data = {}
    root = env.get("CLAUDE_PROJECT_DIR") or (data.get("cwd") if isinstance(data, dict) else "") or "."
    note = session_note(Path(root))
    if note:
        print(note)
    return 0
