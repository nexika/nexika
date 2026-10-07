#!/usr/bin/env python3
"""itqan session hooks.

  session-start  Detect the project's stacks and print ONE short note: which checklist
                 packs apply, the commands, and last session's guard summary if any.
  session-end    Summarize this session's guard decisions into sessions.jsonl. Silent.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from collections import Counter
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
PACKS = PLUGIN / "packs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import itqan_files  # noqa: E402

SKIP_DIRS = {"node_modules", "bin", "obj", "dist", "build", "venv", "__pycache__", "target", "vendor"}
MAX_DEPTH = 3

# stack -> file-name test, in display order
STACK_MARKERS = {
    "dotnet": lambda n: n.endswith((".sln", ".slnx", ".csproj", ".fsproj")),
    "python": lambda n: n in ("pyproject.toml", "setup.py", "requirements.txt", "Pipfile"),
    "node": lambda n: n == "package.json",
    "go": lambda n: n == "go.mod",
    "rust": lambda n: n == "Cargo.toml",
    "java": lambda n: n in ("pom.xml", "build.gradle", "build.gradle.kts"),
}


def data_home() -> Path:
    return Path(os.environ.get("ITQAN_HOME") or Path.home() / ".claude" / "nexika" / "itqan")


def detect_stacks(root: Path) -> list[str]:
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [] if depth >= MAX_DEPTH else [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            found.update(stack for stack, test in STACK_MARKERS.items() if test(name))
    return [s for s in STACK_MARKERS if s in found]


_read_jsonl = itqan_files.read_jsonl


def last_session_note(current: str) -> str:
    sessions = [s for s in _read_jsonl(data_home() / "sessions.jsonl") if s.get("session") != current[:8]]
    if not sessions:
        return ""
    last = sessions[-1]
    if not (last.get("deny") or last.get("ask")):
        return ""
    rules = ", ".join(last.get("rules", [])[:5])
    return (f"Last session the guard refused {last.get('deny', 0)} and asked about "
            f"{last.get('ask', 0)} risky action(s): {rules}.")


def session_start(hook: dict) -> None:
    cwd = Path(hook.get("cwd") or os.getcwd())
    try:
        import itqan_learn
        root = itqan_learn.project_root(cwd)
    except Exception:  # the repo root is a nicety: fall back to the current folder
        root = cwd
    stacks = detect_stacks(root)
    packs = [(s, PACKS / f"{s}.md") for s in stacks if (PACKS / f"{s}.md").is_file()]
    lines = ["## itqan (Nexika): plan, test-first, review, ship"]
    if stacks:
        lines.append(f"Project stacks: {', '.join(stacks)}.")
    if packs:
        lines.append("Before implementing or reviewing code in these stacks, read the checklist:")
        lines += [f"  {s}: {p}" for s, p in packs]
    lines.append("Workflows: /itqan:plan (plan only), /itqan:review (review changes), "
                 "/itqan:ship (plan -> tests first -> implement -> verify -> review), "
                 "/itqan:learn (approve rules learned from corrections), /itqan:insights.")
    lines.append("Guard: normal edits are never blocked; only risky actions are refused or need approval.")
    lines.append(f"itqan helper (for /itqan:learn and /itqan:insights): "
                 f"python3 {Path(__file__).resolve().parent / 'itqan_learn.py'}")
    lines.append(f"itqan proof (for /itqan:proof): "
                 f"python3 {Path(__file__).resolve().parent / 'itqan_proof.py'}")
    note = last_session_note(str(hook.get("session_id") or ""))
    if note:
        lines.append(note)
    try:
        import itqan_learn
        rules = itqan_learn.session_note(itqan_learn.project_root(cwd))
    except Exception:  # learning data must never break the session note
        rules = ""
    if rules:
        lines.append(rules)
    print("\n".join(lines))


REJECTED = ("doesn't want to proceed", "was rejected", "permission denied by user")


def approved_asks(transcript: str, asked: set[str]) -> int:
    """How many of the guard's questions the user answered yes: the tool then ran (its result is not
    a rejection). A yes means the guard asked about something the user wanted: a likely false alarm."""
    if not transcript or not asked:
        return 0
    approved = set()
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_result"' not in line:
                    continue
                try:
                    content = json.loads(line).get("message", {}).get("content")
                except (ValueError, AttributeError):
                    continue
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict) or block.get("tool_use_id") not in asked:
                        continue
                    body = json.dumps(block.get("content"), ensure_ascii=False).lower()
                    if not (block.get("is_error") and any(r in body for r in REJECTED)):
                        approved.add(block["tool_use_id"])
    except OSError:
        return 0
    return len(approved)


def session_end(hook: dict) -> None:
    session = str(hook.get("session_id") or "")[:8]
    if not session:
        return
    events = [e for e in _read_jsonl(data_home() / "guard.jsonl") if e.get("session") == session]
    counts = Counter(e.get("decision") for e in events)
    asked = {e["tool_use_id"] for e in events if e.get("decision") == "ask" and e.get("tool_use_id")}
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "session": session,
        "deny": counts.get("deny", 0),
        "ask": counts.get("ask", 0),
        "ask_approved": approved_asks(str(hook.get("transcript_path") or ""), asked),
        "rules": sorted({e.get("rule", "?") for e in events}),
    }
    itqan_files.append_jsonl(data_home() / "sessions.jsonl", entry)


def main(argv: list[str]) -> int:
    try:
        hook = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        hook = {}
    try:
        if len(argv) > 1 and argv[1] == "session-start":
            session_start(hook)
        elif len(argv) > 1 and argv[1] == "session-end":
            session_end(hook)
    except Exception:  # never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
