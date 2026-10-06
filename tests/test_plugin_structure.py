"""Static checks: every plugin in the marketplace is complete and self-consistent."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import PLUGINS, REPO

MARKETPLACE = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
PLUGIN_DIRS = [REPO / p["source"] for p in MARKETPLACE["plugins"]]


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path} has no frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            fields[key.strip()] = value.strip().strip('"')
    return fields


def ids(paths):
    return [str(p.relative_to(REPO)) for p in paths]


ALL_JSON = [p for p in REPO.rglob("*.json") if ".git" not in p.parts and "node_modules" not in p.parts]


@pytest.mark.parametrize("path", ALL_JSON, ids=ids(ALL_JSON))
def test_json_files_parse(path):
    json.loads(path.read_text(encoding="utf-8"))


def test_marketplace_lists_every_plugin_folder():
    listed = {p.resolve() for p in PLUGIN_DIRS}
    on_disk = {p.resolve() for p in PLUGINS.iterdir() if p.is_dir()}
    assert listed == on_disk


@pytest.mark.parametrize("plugin", PLUGIN_DIRS, ids=ids(PLUGIN_DIRS))
def test_plugin_manifest_matches_marketplace(plugin):
    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
    entry = next(p for p in MARKETPLACE["plugins"] if (REPO / p["source"]).resolve() == plugin.resolve())
    assert manifest["name"] == entry["name"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert (plugin / "README.md").is_file()


SKILLS = sorted(PLUGINS.glob("*/skills/*/SKILL.md"))


@pytest.mark.parametrize("skill", SKILLS, ids=ids(SKILLS))
def test_skill_frontmatter(skill):
    fields = frontmatter(skill)
    assert fields.get("name") == skill.parent.name
    assert len(fields.get("description", "")) > 40, "description must say what it does and when to use it"


DEFINITIONS = sorted(PLUGINS.glob("*/agents/*.md")) + sorted(PLUGINS.glob("*/output-styles/*.md"))


@pytest.mark.parametrize("path", DEFINITIONS, ids=ids(DEFINITIONS))
def test_agent_and_style_frontmatter(path):
    fields = frontmatter(path)
    assert fields.get("name")
    assert fields.get("description")


HOOK_FILES = sorted(PLUGINS.glob("*/hooks/hooks.json"))


@pytest.mark.parametrize("hooks_file", HOOK_FILES, ids=ids(HOOK_FILES))
def test_hook_commands_point_to_existing_files(hooks_file):
    plugin = hooks_file.parent.parent
    commands = [h["command"] for groups in json.loads(hooks_file.read_text())["hooks"].values()
                for group in groups for h in group["hooks"]]
    assert commands
    for command in commands:
        for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"' ]+)", command):
            assert (plugin / ref).is_file(), f"{command} -> missing {ref}"


@pytest.mark.parametrize("plugin", PLUGIN_DIRS, ids=ids(PLUGIN_DIRS))
def test_skill_references_resolve(plugin):
    """Every `<plugin>:<skill>` mentioned in the plugin's text is a real skill."""
    name = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())["name"]
    skills = {p.parent.name for p in plugin.glob("skills/*/SKILL.md")}
    agents = {p.stem for p in plugin.glob("agents/*.md")}
    for path in [*plugin.rglob("*.md"), *plugin.rglob("*.py")]:
        if "node_modules" in path.parts or path.name == "DESIGN.md":  # DESIGN.md describes planned commands
            continue
        for ref in re.findall(rf"\b{name}:([a-z][a-z-]+)", path.read_text(encoding="utf-8")):
            assert ref in skills | agents, f"{path.relative_to(REPO)} mentions unknown {name}:{ref}"


def test_no_leftover_tutor_prefix():
    """The plugin was renamed tutor -> prof; old command prefixes must not come back."""
    for path in PLUGINS.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".py", ".json"}:
            assert not re.search(r"\btutor:[a-z]", path.read_text(encoding="utf-8")), path
