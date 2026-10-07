"""Projects in a repository, their version files, and semantic versions.

Detection order:
1. .amin.json {"projects": [{"name", "path", "version_files", "changelog"?, "tag"?}]}
2. a plugin marketplace: every plugins/*/.claude-plugin/plugin.json is a project
   (tag "<name>-v<version>", changelog <path>/CHANGELOG.md, notes in changelog.d/<name>/)
3. one project at the root: package.json, pyproject.toml, .claude-plugin/plugin.json,
   Directory.Build.props or a .csproj with <Version> (tag "v<version>", notes in changelog.d/)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
TYPES = ("breaking", "added", "changed", "deprecated", "removed", "fixed", "security")
MAJOR_TYPES = {"breaking", "removed"}
MINOR_TYPES = {"added", "changed", "deprecated"}

JSON_VERSION = re.compile(r'("version"\s*:\s*")([^"]+)(")')
TOML_VERSION = re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")')
XML_VERSION = re.compile(r"(<Version>)([^<]+)(</Version>)")


@dataclass
class Project:
    name: str
    path: str                # repo-relative folder ("." for a single-project repo)
    version_files: list[str]
    changelog: str
    tag_format: str
    fragments: str           # repo-relative folder holding this project's notes

    def tag(self, version: str) -> str:
        return self.tag_format.format(name=self.name, version=version)

    def tag_prefix(self) -> str:
        return self.tag_format.split("{version}")[0].format(name=self.name)


# ---------------------------------------------------------------- semantic versions


def parse(version: str) -> tuple[int, int, int]:
    m = SEMVER.match(version.strip())
    if not m:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump(version: str, types: set[str]) -> tuple[str, str]:
    """(next version, reason) for the kinds of change in the notes.

    breaking/removed -> major (in 0.x: minor), added/changed/deprecated -> minor,
    fixed/security -> patch.
    """
    major, minor, patch = parse(version)
    if types & MAJOR_TYPES:
        if major == 0:
            return f"0.{minor + 1}.0", "breaking change (0.x: minor bump)"
        return f"{major + 1}.0.0", "breaking change: major bump"
    if types & MINOR_TYPES:
        return f"{major}.{minor + 1}.0", "new or changed behaviour: minor bump"
    if types:
        return f"{major}.{minor}.{patch + 1}", "fixes only: patch bump"
    return version, "no notes: no release"


# ---------------------------------------------------------------- version files


def _pattern(path: str) -> re.Pattern:
    if path.endswith(".json"):
        return JSON_VERSION
    if path.endswith(".toml"):
        return TOML_VERSION
    if path.endswith((".csproj", ".props", ".fsproj", ".vbproj")):
        return XML_VERSION
    raise ValueError(f"don't know how to read a version from {path}")


def read_version(root: Path, rel: str) -> str | None:
    try:
        m = _pattern(rel).search((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m.group(2).strip() if m else None


def write_version(root: Path, rel: str, version: str) -> None:
    path = root / rel
    content = path.read_text(encoding="utf-8")
    new, count = _pattern(rel).subn(lambda m: m.group(1) + version + m.group(3), content, count=1)
    if not count:
        raise ValueError(f"no version field found in {rel}")
    path.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------- detection


def load_config(root: Path) -> dict:
    try:
        data = json.loads((root / ".amin.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _from_config(entries: list[dict]) -> list[Project]:
    projects = []
    for item in entries:
        name, path = str(item["name"]), str(item.get("path", "."))
        single = path in (".", "")
        folder = path.rstrip("/")
        projects.append(Project(
            name=name, path="." if single else folder,
            version_files=list(item["version_files"]),
            changelog=item.get("changelog") or ("CHANGELOG.md" if single else f"{folder}/CHANGELOG.md"),
            tag_format=item.get("tag") or ("v{version}" if single else "{name}-v{version}"),
            fragments="changelog.d" if single else f"changelog.d/{name}",
        ))
    return projects


def detect(root: Path) -> list[Project]:
    config = load_config(root)
    if config.get("projects"):
        return _from_config(config["projects"])
    plugins = sorted(root.glob("plugins/*/.claude-plugin/plugin.json"))
    if plugins:
        projects = []
        for manifest in plugins:
            folder = manifest.parent.parent
            try:
                name = json.loads(manifest.read_text(encoding="utf-8"))["name"]
            except (OSError, ValueError, KeyError):
                name = folder.name
            rel = folder.relative_to(root).as_posix()
            projects.append(Project(name, rel, [manifest.relative_to(root).as_posix()], f"{rel}/CHANGELOG.md",
                                    "{name}-v{version}", f"changelog.d/{name}"))
        return projects
    candidates = ["package.json", "pyproject.toml", ".claude-plugin/plugin.json", "Directory.Build.props"]
    candidates += sorted(p.relative_to(root).as_posix() for p in root.glob("*.csproj"))
    candidates += sorted(p.relative_to(root).as_posix() for p in root.glob("src/*/*.csproj"))
    for rel in candidates:
        if (root / rel).is_file() and read_version(root, rel):
            return [Project(root.name, ".", [rel], "CHANGELOG.md", "v{version}", "changelog.d")]
    return []


def umbrella(root: Path) -> Project | None:
    """The whole repository released as one (a marketplace of plugins): tag <name>-v<version>, the root
    CHANGELOG.md, and the root version file if there is one. .amin.json {"umbrella": {...}} overrides."""
    item = load_config(root).get("umbrella")
    if isinstance(item, dict) and item.get("name"):
        return Project(str(item["name"]), ".", list(item.get("version_files") or []),
                       item.get("changelog") or "CHANGELOG.md", item.get("tag") or "{name}-v{version}",
                       "changelog.d")
    try:
        name = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["name"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    files = [rel for rel in ("pyproject.toml", "package.json") if read_version(root, rel)]
    return Project(str(name), ".", files, "CHANGELOG.md", "{name}-v{version}", "changelog.d")


def find(projects: list[Project], name: str) -> Project:
    for p in projects:
        if p.name == name:
            return p
    raise KeyError(f"unknown project '{name}'. Projects: {', '.join(p.name for p in projects) or 'none'}")


def owner_of(projects: list[Project], rel_file: str) -> Project | None:
    """The project a changed file belongs to (the most specific path wins)."""
    best = None
    for p in projects:
        if p.path == ".":
            if best is None:
                best = p
        elif rel_file == p.path or rel_file.startswith(p.path + "/"):
            if best is None or best.path == "." or len(p.path) > len(best.path):
                best = p
    return best
