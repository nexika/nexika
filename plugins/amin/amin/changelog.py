"""The changelog (CHANGELOG.md, CHANGES.md, HISTORY.md): insert a version section, read one back.

New files use Keep a Changelog (`## [1.2.0] - 2026-10-06`). An existing file keeps its own heading
style, such as `## Version 26.10.0` or `## 1.2.0 (2026-10-06)`.
"""
from __future__ import annotations

import re
from pathlib import Path

HEADER = (
    "# Changelog\n\n"
    "All notable changes to {name} are documented here. The format follows "
    "[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow "
    "[Semantic Versioning](https://semver.org/).\n"
)
KEEP_A_CHANGELOG = "## [{version}] - {date}"
SECTION_START = re.compile(r"^## ", re.M)
# a version heading: "## [1.2.0] - date", "## Version 26.10.0", "## v1.2.0", "## 1.2.0 (date)";
# "## Unreleased" has no version, so it stays on top
VERSION_HEADING = re.compile(r"^## +\[?(?:version +|v)?(\d+\.\d+[^\s\]]*)\]?(.*)$", re.M | re.I)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def render(version: str, date: str, sections: dict[str, list[str]], heading: str = KEEP_A_CHANGELOG) -> str:
    parts = [heading.format(version=version, date=date)]
    for title, lines in sections.items():
        parts.append(f"\n### {title}\n" + "\n".join(lines))
    return "\n".join(parts) + "\n"


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _heading(content: str, version: str) -> re.Match | None:
    return next((m for m in VERSION_HEADING.finditer(content) if m.group(1) == version), None)


def heading_style(content: str) -> str:
    """The file's own version heading as a template, from its newest version section."""
    m = VERSION_HEADING.search(content)
    if not m:
        return KEEP_A_CHANGELOG
    line = m.group(0).replace("{", "{{").replace("}", "}}")
    start = m.start(1) - m.start()
    line = line[:start] + "{version}" + line[start + len(m.group(1)):]
    return DATE.sub("{date}", line, count=1)


def has_version(path: Path, version: str) -> bool:
    content = _read(path)
    return bool(content and _heading(content, version))


def insert(path: Path, name: str, version: str, date: str, sections: dict[str, list[str]]) -> None:
    """Add a section for version at the top of the version list, below any Unreleased section
    (creating the file if needed)."""
    if has_version(path, version):
        raise ValueError(f"{path.name} already has a section for {version}")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER.format(name=name) + "\n" + render(version, date, sections), encoding="utf-8")
        return
    content = path.read_text(encoding="utf-8")
    block = render(version, date, sections, heading_style(content))
    m = VERSION_HEADING.search(content)
    if m:
        content = content[: m.start()] + block + "\n" + content[m.start():]
    else:
        content = content.rstrip("\n") + "\n\n" + block
    path.write_text(content, encoding="utf-8")


def latest(path: Path) -> str | None:
    """The newest version with a section (the first below any Unreleased section), or None."""
    m = VERSION_HEADING.search(_read(path) or "")
    return m.group(1) if m else None


def extract(path: Path, version: str) -> str | None:
    """The body of one version's section (the release notes), or None."""
    content = _read(path) or ""
    m = _heading(content, version)
    if not m:
        return None
    body_start = m.end() + 1
    nxt = SECTION_START.search(content, body_start)
    return content[body_start: nxt.start() if nxt else len(content)].strip()
