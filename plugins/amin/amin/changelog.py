"""CHANGELOG.md in Keep a Changelog format: insert a version section, read one back."""
from __future__ import annotations

import re
from pathlib import Path

HEADER = (
    "# Changelog\n\n"
    "All notable changes to {name} are documented here. The format follows "
    "[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow "
    "[Semantic Versioning](https://semver.org/).\n"
)
SECTION_START = re.compile(r"^## \[", re.M)
VERSION_START = re.compile(r"^## \[(?!unreleased\])", re.M | re.I)   # Unreleased stays on top


def render(version: str, date: str, sections: dict[str, list[str]]) -> str:
    parts = [f"## [{version}] - {date}"]
    for title, lines in sections.items():
        parts.append(f"\n### {title}\n" + "\n".join(lines))
    return "\n".join(parts) + "\n"


def has_version(path: Path, version: str) -> bool:
    try:
        return f"## [{version}]" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def insert(path: Path, name: str, version: str, date: str, sections: dict[str, list[str]]) -> None:
    """Add a section for version at the top of the version list, below any [Unreleased] section
    (creating the file if needed)."""
    if has_version(path, version):
        raise ValueError(f"{path.name} already has a section for {version}")
    block = render(version, date, sections)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER.format(name=name) + "\n" + block, encoding="utf-8")
        return
    content = path.read_text(encoding="utf-8")
    m = VERSION_START.search(content)
    if m:
        content = content[: m.start()] + block + "\n" + content[m.start():]
    else:
        content = content.rstrip("\n") + "\n\n" + block
    path.write_text(content, encoding="utf-8")


def extract(path: Path, version: str) -> str | None:
    """The body of one version's section (the release notes), or None."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    start = content.find(f"## [{version}]")
    if start < 0:
        return None
    body_start = content.find("\n", start) + 1
    nxt = SECTION_START.search(content, body_start)
    return content[body_start: nxt.start() if nxt else len(content)].strip()
