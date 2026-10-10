"""A lean session start (#336): lawha, prof, manar and bayan add little to a session they have no work in.

- Every skill and agent description says when to use it, in one line, within a length budget.
- lawha speaks only in a project with a frontend, manar only for a website, prof only when a lesson
  is due, a learner profile exists or the user is a learner.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import PLUGINS

LEAN = ("lawha", "prof", "manar", "bayan")
SKILL_BUDGET = 300   # characters: when to use it and the words people type, nothing more
AGENT_BUDGET = 200   # agents are started by the plugin's own skills, so "when" is short


def description(path: Path) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert match, path
    for line in match.group(1).splitlines():
        if line.startswith("description:"):
            return line.partition(":")[2].strip().strip('"')
    return ""


SKILLS = sorted(p for name in LEAN for p in (PLUGINS / name / "skills").glob("*/SKILL.md"))
AGENTS = sorted(p for name in LEAN for p in (PLUGINS / name / "agents").glob("*.md"))


def ids(paths):
    return [str(p.relative_to(PLUGINS)) for p in paths]


@pytest.mark.parametrize("path", SKILLS, ids=ids(SKILLS))
def test_skill_description_fits_its_budget(path):
    text = description(path)
    assert 40 < len(text) <= SKILL_BUDGET, f"{len(text)} characters"
    assert "Use " in text, "say when to use it"


@pytest.mark.parametrize("path", AGENTS, ids=ids(AGENTS))
def test_agent_description_fits_its_budget(path):
    text = description(path)
    assert 20 < len(text) <= AGENT_BUDGET, f"{len(text)} characters"


# The words people type that route a request to the skill: trimming must keep them.
TRIGGERS = {
    "lawha/skills/check/SKILL.md": ["is it responsive", "افحص الصفحة"],
    "lawha/skills/direct/SKILL.md": ["make it look good", "صمم الواجهة"],
    "lawha/skills/elevate/SKILL.md": ["make it beautiful", "اجعلها أجمل"],
    "lawha/skills/figma/SKILL.md": ["Figma link", "نفّذ هذا التصميم"],
    "lawha/skills/inspire/SKILL.md": ["make it like this", "استلهم من هذا الموقع"],
    "lawha/skills/system/SKILL.md": ["design system", "design drift"],
    "prof/skills/learn/SKILL.md": ["teach me", "Not for"],
    "prof/skills/walkthrough/SKILL.md": ["line by line", "Not for"],
    "prof/skills/onboard/SKILL.md": ["onboard me", "Not for"],
    "prof/skills/report/SKILL.md": ["what did I learn", "goodbye"],
    "prof/skills/quiz/SKILL.md": ["quiz me"],
    "prof/skills/warmup/SKILL.md": ["check what I remember"],
    "prof/skills/progress/SKILL.md": ["my progress"],
    "manar/skills/audit/SKILL.md": ["SEO audit", "ChatGPT"],
    "manar/skills/fix/SKILL.md": ["fix the SEO", "llms.txt"],
    "manar/skills/visibility/SKILL.md": ["AI visibility", "are we cited"],
    "bayan/skills/check/SKILL.md": ["does this sound like AI", "راجع النص"],
    "bayan/skills/write/SKILL.md": ["humanize this", "اكتبها بشكل أبسط"],
    "bayan/skills/level/SKILL.md": ["reader level"],
}


@pytest.mark.parametrize("rel", sorted(TRIGGERS))
def test_trimmed_descriptions_keep_the_trigger_words(rel):
    text = description(PLUGINS / rel)
    for words in TRIGGERS[rel]:
        assert words in text, f"{rel} lost {words!r}"


@pytest.mark.parametrize("plugin,helper", [("lawha", "${CLAUDE_PLUGIN_ROOT}/bin/lawha"),
                                           ("manar", "${CLAUDE_PLUGIN_ROOT}/bin/manar")])
def test_skills_find_the_helper_without_the_session_note(plugin, helper):
    """The session note is quiet in most projects, so a skill must not need it for the helper's path."""
    for path in (PLUGINS / plugin / "skills").glob("*/SKILL.md"):
        if "helper" in path.read_text(encoding="utf-8").lower():
            assert helper in path.read_text(encoding="utf-8"), path


def test_prof_skills_find_the_helper_and_session_id_without_the_session_note():
    for name in ("report", "warmup", "quiz", "progress"):
        text = (PLUGINS / "prof" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        if "<helper>" in text:
            assert "${CLAUDE_PLUGIN_ROOT}/scripts/prof_store.py" in text, name
    assert "${CLAUDE_SESSION_ID}" in (PLUGINS / "prof" / "skills" / "report" / "SKILL.md").read_text()


# ---------------------------------------------------------------- projects


def make(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


BACKENDS = {
    "python": {"pyproject.toml": "[project]\nname = 'api'\n", "app/main.py": "",
               "htmlcov/index.html": "<html>"},
    "node api": {"package.json": '{"dependencies": {"express": "4", "pg": "8"}}', "src/server.js": ""},
    "dotnet api": {"Api/Api.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>', "Api/Program.cs": ""},
    "go": {"go.mod": "module x\n", "cmd/main.go": ""},
    "empty": {},
}
FRONTENDS = {
    "react": {"package.json": '{"dependencies": {"react": "19", "react-dom": "19"}}'},
    "vue dev dependency": {"package.json": '{"devDependencies": {"vue": "3"}}'},
    "tailwind config": {"tailwind.config.ts": "export default {}"},
    "monorepo app": {"package.json": '{"workspaces": ["apps/*"]}',
                     "apps/web/package.json": '{"dependencies": {"next": "15"}}'},
    "frontend folder": {"frontend/package.json": '{"dependencies": {"svelte": "5"}}'},
    "plain html": {"index.html": "<!doctype html><title>x</title>"},
    "lawha used here": {".lawha/system.json": "{}"},
}


def lawha_hook(project: Path, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run(["sh", str(PLUGINS / "lawha" / "bin" / "lawha"), "hook", "session-start"],
                          cwd=cwd or project, capture_output=True, text=True, env=env, timeout=20)


@pytest.mark.parametrize("kind", sorted(BACKENDS))
def test_lawha_is_quiet_without_a_frontend(tmp_path, kind):
    done = lawha_hook(make(tmp_path / "p", BACKENDS[kind]))
    assert done.returncode == 0 and done.stdout == ""


@pytest.mark.parametrize("kind", sorted(FRONTENDS))
def test_lawha_speaks_in_a_frontend_project(tmp_path, kind):
    done = lawha_hook(make(tmp_path / "p", FRONTENDS[kind]))
    assert done.returncode == 0 and "lawha:" in done.stdout and "bin/lawha" in done.stdout


def test_lawha_is_quiet_when_the_project_folder_is_gone(tmp_path):
    done = lawha_hook(tmp_path / "missing", cwd=tmp_path)
    assert done.returncode == 0 and done.stdout == ""


# manar: a website (pages served to browsers), not every project


@pytest.fixture
def manar_hook():
    sys.path.insert(0, str(PLUGINS / "manar"))
    from manar import hook
    return hook


WEBSITES = {
    "next": {"package.json": '{"dependencies": {"next": "15"}}', "app/layout.tsx": ""},
    "astro": {"package.json": '{"dependencies": {"astro": "5"}}'},
    "jekyll": {"_config.yml": "title: x"},
    "static docs": {"docs/index.html": "<html></html>"},
    "razor": {"Web/Web.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>',
              "Web/Pages/Shared/_Layout.cshtml": ""},
    "manar used here": {".manar/panel.json": "{}"},
}


@pytest.mark.parametrize("kind", sorted(BACKENDS))
def test_manar_is_quiet_when_the_project_is_not_a_website(manar_hook, tmp_path, kind):
    assert manar_hook.session_note(make(tmp_path / "p", BACKENDS[kind])) == ""


@pytest.mark.parametrize("kind", sorted(WEBSITES))
def test_manar_speaks_for_a_website(manar_hook, tmp_path, kind):
    note = manar_hook.session_note(make(tmp_path / "p", WEBSITES[kind]))
    assert "manar" in note and "bin/manar" in note


def test_manar_hook_command_is_quiet_in_a_backend(tmp_path):
    project = make(tmp_path / "p", BACKENDS["python"])
    manar = PLUGINS / "manar" / "bin" / "manar"
    done = subprocess.run([sys.executable, str(manar), "hook", "session-start"], cwd=project,
                          input=json.dumps({"cwd": str(project)}), capture_output=True, text=True,
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)}, timeout=20)
    assert done.returncode == 0 and done.stdout == ""


def test_manar_hook_never_breaks_on_an_unreadable_project(manar_hook, tmp_path, monkeypatch):
    def boom(root):
        raise OSError("permission denied")
    monkeypatch.setattr(manar_hook.framework, "detect", boom)
    assert manar_hook.session_note(tmp_path) == ""


# prof: only when there is something to teach or review


def test_prof_is_quiet_with_no_profile_and_nothing_due(store, capsys):
    store.session_start({"session_id": "abcdef1234567"})
    assert capsys.readouterr().out == ""


def test_prof_quiet_session_does_not_use_up_the_family_question(store, family_profile, capsys):
    store.session_start({"session_id": "s1"})
    assert capsys.readouterr().out == ""
    assert not family_profile.exists() or "asked" not in json.loads(family_profile.read_text())


def test_prof_speaks_when_a_learner_profile_exists(store, capsys):
    store.PROFILE.parent.mkdir(parents=True, exist_ok=True)
    store.PROFILE.write_text("# Learner profile\n- Level: junior\n", encoding="utf-8")
    store.session_start({"session_id": "abcdef1234567"})
    assert "Prof plugin" in capsys.readouterr().out


def test_prof_speaks_when_a_lesson_is_due(store, capsys):
    store.save_topic("py", "Python", {"gen": ("missed", "generators", "no idea", "2026-10-01")})
    store.session_start({"session_id": "s1"})
    assert "Prof plugin" in capsys.readouterr().out


def test_prof_speaks_to_a_learner_with_no_profile_yet(store, family_profile, capsys):
    family_profile.parent.mkdir(parents=True, exist_ok=True)
    family_profile.write_text(json.dumps({"schema": "nexika.settings/1", "role": "learner"}))
    store.session_start({"session_id": "s1"})
    assert "Prof plugin" in capsys.readouterr().out


def test_prof_still_publishes_its_status_when_quiet(store, capsys):
    store.session_start({"session_id": "s1"})
    status = Path(os.environ["NEXIKA_STATUS_HOME"]) / "prof.json"
    assert json.loads(status.read_text())["due"] == 0


@pytest.mark.parametrize("profile,due,role,speaks", [
    (False, False, "", False), (False, False, "developer", False), (False, False, "writer", False),
    (True, False, "", True), (False, True, "", True), (False, False, "learner", True),
])
def test_prof_speak_rule(store, profile, due, role, speaks):
    assert store.has_something_to_say(profile=profile, due=due, role=role) is speaks


# bayan: the writing guide is the plugin's job (#336, option 4): tighter wording, the same rules


BAYAN_RULES = ["Reader level", "language the user writes in", "Lead with the answer", "One idea per sentence",
               "most under 20 words", "Be specific", "Cut words that add nothing", "no opening praise",
               "hope this helps", "no cheerleading", "no emoji", "at most one exclamation mark", "delve",
               "em dashes", "every list in", "bold label", "same sentence length", "Modern Standard Arabic",
               "من الجدير بالذكر", "في الختام", "Correct before simple", "uncertain", "Code, commands, paths",
               "commit messages", "pull request text", "rewrite those lines", "check FILE", "Full guide"]


def test_bayan_session_note_keeps_every_rule_in_fewer_words():
    sys.path.insert(0, str(PLUGINS / "bayan"))
    from bayan import hooks
    note = hooks.GUIDE.format(level="developer", level_rule=hooks.LEVEL_RULE["developer"], cmd="bayan",
                              guide="/g/writing.md")
    for rule in BAYAN_RULES:
        assert rule in note, rule
    assert len(note) <= 1700, len(note)  # 1,756 before #336
