"""Change notes ("fragments"): one small file per change, collected at release time.

    changelog.d/<project>/<id>.<type>.md     (single-project repos: changelog.d/<id>.<type>.md)

<id> is the PR or issue number (or a short slug); <type> is one of project.TYPES.
One file per PR means no merge conflicts in CHANGELOG.md, and the types decide the version.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .project import TYPES, Project

NAME = re.compile(r"^(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*)\.(?P<type>[a-z]+)\.md$")
SECTIONS = {
    "breaking": "Breaking", "added": "Added", "changed": "Changed", "deprecated": "Deprecated",
    "removed": "Removed", "fixed": "Fixed", "security": "Security",
}


@dataclass
class Fragment:
    path: str
    id: str
    type: str
    text: str
    pr: str | None = None    # the pull request that added the note, found at release time


def check_name(filename: str) -> str | None:
    """None if the file name is a valid note, else the problem."""
    m = NAME.match(filename)
    if not m:
        return f"{filename}: expected <id>.<type>.md"
    if m.group("type") not in TYPES:
        return f"{filename}: type must be one of {', '.join(TYPES)}"
    return None


def pending(root: Path, project: Project) -> tuple[list[Fragment], list[str]]:
    """(valid notes, problems) waiting in the project's notes folder."""
    folder = root / project.fragments
    if not folder.is_dir():
        return [], []
    notes, problems = [], []
    for path in sorted(folder.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        problem = check_name(path.name)
        if problem:
            problems.append(f"{project.fragments}/{problem}")
            continue
        m = NAME.match(path.name)
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            problems.append(f"{project.fragments}/{path.name}: empty note")
            continue
        notes.append(Fragment(path.relative_to(root).as_posix(), m.group("id"), m.group("type"), text))
    return notes, problems


def add(root: Path, project: Project, kind: str, text: str, note_id: str) -> Path:
    if kind not in TYPES:
        raise ValueError(f"type must be one of {', '.join(TYPES)}")
    if not text.strip():
        raise ValueError("a note needs text")
    note_id = re.sub(r"[^A-Za-z0-9_-]+", "-", note_id).strip("-") or "note"
    folder = root / project.fragments
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{note_id}.{kind}.md"
    n = 2
    while path.exists():
        path = folder / f"{note_id}-{n}.{kind}.md"
        n += 1
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _bullets(note: Fragment) -> list[str]:
    number = note.id if note.id.isdigit() else note.pr
    ref = f" (#{number})" if number else ""
    lines = [ln.strip() for ln in note.text.splitlines() if ln.strip()]
    if all(ln.startswith(("- ", "* ")) for ln in lines):
        return [f"- {ln[2:].strip()}{ref}" for ln in lines]
    return [f"- {' '.join(lines)}{ref}"]


def grouped(notes: list[Fragment]) -> dict[str, list[str]]:
    """Keep a Changelog sections, in their standard order, with bullet lines."""
    out: dict[str, list[str]] = {}
    for kind, title in SECTIONS.items():
        lines = [b for n in notes if n.type == kind for b in _bullets(n)]
        if lines:
            out[title] = lines
    return out
