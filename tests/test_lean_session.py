"""A lean session start (#336): lawha, prof, manar and bayan add little to a session they have no work in.

- Every skill and agent description says when to use it, in one line, within a length budget.
- lawha speaks only in a project with a frontend, manar only for a website, prof only when a lesson
  is due, in a tutoring session or with a question for a learner (#393).
- bayan gives the short rules every session and the full guide on demand, the whole list to a writer.
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


PROF_SKILL_BUDGET = 200   # #431: prof's seven skills load in every session, and most sessions aren't lessons
PROF_SKILLS = sorted((PLUGINS / "prof" / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("path", PROF_SKILLS, ids=ids(PROF_SKILLS))
def test_prof_skill_description_fits_the_tighter_budget(path):
    assert len(description(path)) <= PROF_SKILL_BUDGET, f"{len(description(path))} characters"


@pytest.mark.parametrize("path", AGENTS, ids=ids(AGENTS))
def test_agent_description_fits_its_budget(path):
    text = description(path)
    assert 20 < len(text) <= AGENT_BUDGET, f"{len(text)} characters"


# The words people type that route a request to the skill: trimming must keep them. #431's routing check
# (benchmarks/routing) showed prof's second phrases matter: without them the request went elsewhere.
TRIGGERS = {
    "lawha/skills/check/SKILL.md": ["is it responsive", "افحص الصفحة"],
    "lawha/skills/direct/SKILL.md": ["make it look good", "صمم الواجهة"],
    "lawha/skills/elevate/SKILL.md": ["make it beautiful", "اجعلها أجمل"],
    "lawha/skills/figma/SKILL.md": ["Figma link", "نفّذ هذا التصميم"],
    "lawha/skills/inspire/SKILL.md": ["make it like this", "استلهم من هذا الموقع"],
    "lawha/skills/system/SKILL.md": ["design system", "design drift"],
    "prof/skills/learn/SKILL.md": ["teach me", "Not for"],
    "prof/skills/walkthrough/SKILL.md": ["line by line", "Not for"],
    "prof/skills/onboard/SKILL.md": ["onboard me", "I'm new to this codebase", "Not for"],
    "prof/skills/report/SKILL.md": ["what did I learn", "goodbye"],
    "prof/skills/quiz/SKILL.md": ["quiz me", "check my understanding"],
    "prof/skills/warmup/SKILL.md": ["check what I remember", "where was I in my lessons"],
    "prof/skills/progress/SKILL.md": ["my progress", "what have I learned"],
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


# #393: prof speaks when something is due, in a tutoring session (Professor output style), or when a
# learner has a question waiting to be asked once. A learner with nothing due and nothing to ask gets
# nothing: /prof:learn and "teach me" read the profile themselves.
@pytest.mark.parametrize("due,professor,learner,question,speaks", [
    (False, False, False, False, False), (False, False, False, True, False),
    (False, False, True, False, False), (True, False, False, False, True),
    (False, True, False, False, True), (False, False, True, True, True),
])
def test_prof_speak_rule(store, due, professor, learner, question, speaks):
    assert store.has_something_to_say(due=due, professor_style=professor, learner=learner,
                                      question=question) is speaks


def _learner_with_nothing_to_ask(store, family_profile, role="learner"):
    store.set_auto_report(False)
    store.PROFILE.parent.mkdir(parents=True, exist_ok=True)
    store.PROFILE.write_text("# Learner profile\n- Level: junior\n", encoding="utf-8")
    family_profile.parent.mkdir(parents=True, exist_ok=True)
    family_profile.write_text(json.dumps({"schema": "nexika.settings/1", "role": role}))


@pytest.mark.parametrize("role", ["learner", "developer", "writer"])
def test_prof_is_quiet_when_nothing_is_due_and_nothing_to_ask(store, family_profile, tmp_path, capsys, role):
    _learner_with_nothing_to_ask(store, family_profile, role)
    store.session_start({"session_id": "s1", "cwd": str(make(tmp_path / "p", BACKENDS["python"]))})
    assert capsys.readouterr().out == ""


def test_prof_speaks_in_a_tutoring_session(store, family_profile, tmp_path, capsys):
    _learner_with_nothing_to_ask(store, family_profile)
    project = make(tmp_path / "p", {".claude/settings.local.json": '{"outputStyle": "prof:Professor"}'})
    store.session_start({"session_id": "s1", "cwd": str(project)})
    assert "Prof plugin" in capsys.readouterr().out


def test_prof_speaks_to_a_developer_with_reviews_due(store, family_profile, tmp_path, capsys):
    _learner_with_nothing_to_ask(store, family_profile, "developer")
    store.save_topic("py", "Python", {"gen": ("missed", "generators", "no idea", "2026-10-01")})
    store.session_start({"session_id": "s1", "cwd": str(tmp_path)})
    assert "concepts are due for review" in capsys.readouterr().out


# bayan: the writing guide is the plugin's job (#336, option 4). #393: the short rules every session,
# the full guide on demand; a writer (prose is their work) still gets the whole rule list each session.


@pytest.fixture
def bayan_hooks():
    sys.path.insert(0, str(PLUGINS / "bayan"))
    from bayan import hooks
    return hooks


BAYAN_RULES = ["Reader level", "language the user writes in", "Lead with the answer", "One idea per sentence",
               "most under 20 words", "Be specific", "Cut words that add nothing", "no opening praise",
               "hope this helps", "no cheerleading", "no emoji", "at most one exclamation mark", "delve",
               "em dashes", "every list in", "bold label", "same sentence length", "Modern Standard Arabic",
               "من الجدير بالذكر", "في الختام", "Correct before simple", "uncertain", "Code, commands, paths",
               "commit messages", "pull request text", "rewrite those lines", "check FILE", "Full guide"]
SHORT_RULES = ["Reader level", "language the user writes in", "Lead with the answer", "Be specific",
               "no opening praise", "hope this helps", "no emoji", "Correct before simple",
               "Code, commands, paths", "commit messages", "pull request text", "check FILE", "full guide"]
# what leaves the short note must still be in the guide Claude reads on demand
GUIDE_RULES = ["language the user writes in", "One idea per sentence", "under 20 words", "no cheerleading",
               "exclamation mark", "delve", "tapestry", "testament", "realm", "game-changer", "em dashes",
               "exactly three items", "bold label", "same sentence length", "Modern Standard Arabic",
               "من الجدير بالذكر", "في الختام", "uncertain"]


def _note(hooks, full):
    return hooks.note(full=full, level="developer", cmd="bayan", guide="/g/writing.md")


def test_bayan_full_note_keeps_every_rule_in_fewer_words(bayan_hooks):
    note = _note(bayan_hooks, True)
    for rule in BAYAN_RULES:
        assert rule in note, rule
    assert len(note) <= 1700, len(note)  # 1,756 before #336


def test_bayan_short_note_keeps_the_rules_that_shape_every_answer(bayan_hooks):
    note = _note(bayan_hooks, False)
    for rule in SHORT_RULES:
        assert rule in note, rule
    assert "/g/writing.md" in note
    assert len(note) <= 800, len(note)  # the full note is about 1,650


def test_bayan_guide_holds_every_rule_the_short_note_leaves_out():
    guide = (PLUGINS / "bayan" / "guide" / "writing.md").read_text(encoding="utf-8")
    for rule in GUIDE_RULES:
        assert rule in guide, rule


@pytest.mark.parametrize("role,full", [("", False), ("developer", False), ("learner", False),
                                       ("writer", True)])
def test_bayan_full_guide_only_for_a_writer(bayan_hooks, role, full):
    assert bayan_hooks.full_guide_here(role) is full


def test_bayan_session_start_is_short_in_a_coding_session(bayan_hooks, family_profile):
    family_profile.parent.mkdir(parents=True, exist_ok=True)
    family_profile.write_text(json.dumps({"schema": "nexika.settings/1", "role": "developer"}))
    note = bayan_hooks.session_start({})
    assert "Lead with the answer" in note and "tapestry" not in note and "Modern Standard" not in note


def test_bayan_session_start_gives_a_writer_the_whole_list(bayan_hooks, family_profile):
    family_profile.parent.mkdir(parents=True, exist_ok=True)
    family_profile.write_text(json.dumps({"schema": "nexika.settings/1", "role": "writer"}))
    note = bayan_hooks.session_start({})
    assert "Modern Standard Arabic" in note and "delve" in note


def test_bayan_skills_find_the_helper_and_guide_without_the_session_note():
    for name in ("check", "write", "level"):
        text = (PLUGINS / "bayan" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "${CLAUDE_PLUGIN_ROOT}/bin/bayan" in text, name
    write = (PLUGINS / "bayan" / "skills" / "write" / "SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/guide/writing.md" in write
