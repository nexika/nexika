"""prof teaches from reviewed nexika/courses lessons (#442): prof_courses.py clones the courses, finds a
lesson for a topic and lists its files. A fake courses repo stands in for GitHub."""
from __future__ import annotations

import datetime
import importlib.util
import json
import sys

import pytest
from conftest import PLUGINS, _git

COURSES_PATH = PLUGINS / "prof" / "scripts" / "prof_courses.py"
DAY = datetime.date(2026, 10, 29)

# A stand-in for the courses repo's own tool: prints the statuses in statuses.json and records its
# arguments, so a test can check prof never asks it to run lesson code.
FAKE_TOOL = """#!/usr/bin/env python3
import json, os, sys
root = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
with open(os.path.join(root, "calls.log"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
statuses = json.load(open(os.path.join(root, "statuses.json")))
print(json.dumps([{"course": "ai-engineering", "lesson": k, "status": v} for k, v in statuses.items()]))
"""

LESSONS = {
    "l1-tokens-and-context": ({"en": "Tokens and the context window", "ar": "الرموز ونافذة السياق",
                               "fr": "Les tokens et la fenêtre de contexte"}, "m1-llm-basics", ["c1.tokens"]),
    "l2-tool-use": ({"en": "Give Claude a tool", "ar": "أعطِ Claude أداة", "fr": "Donner un outil à Claude"},
                    "m2-tools", ["c2.tool-use"]),
    "l2-what-is-mcp": ({"en": "What MCP is", "ar": "ما هو MCP", "fr": "Ce qu'est MCP"}, "m2-tools",
                       ["c2.mcp-concepts"]),
    "l0-plan-to-commit": ({"en": "From plan to commit", "ar": "من الخطة إلى الإيداع",
                           "fr": "Du plan au commit"}, "m0-claude-code", ["c0.claude-code-workflow"]),
}
STATUSES = {"l1-tokens-and-context": "reviewed", "l2-tool-use": "verified", "l2-what-is-mcp": "reviewed",
            "l0-plan-to-commit": "checked", "l2-build-an-mcp-server": "planned"}
# What each lesson says it teaches, and the first paragraph of its idea: matched at the lowest weight.
GOALS = {"l2-tool-use": "Run the tool loop until Claude answers."}
IDEAS = {"l2-tool-use": {"en": "Tool use (also called function calling) lets Claude call your functions.",
                         "ar": "استخدام الأدوات يتيح لـ Claude أن يستدعي دوالك.",
                         "fr": "L'utilisation d'outils permet à Claude d'appeler vos fonctions."}}
LATER = "Recursion and the borrow checker appear only deep in the lesson, never in its goals or idea."
COMPETENCIES = [
    {"id": "c1.tokens", "concepts": ["tokens", "context window"],
     "can": {"en": "Count the tokens of a request and relate them to the context window and to cost.",
             "ar": "تحسب الرموز في الطلب.", "fr": "Compter les tokens d'une requête."}},
    {"id": "c2.tool-use", "concepts": ["tool definition", "tool_use", "tool_result", "the tool loop"],
     "can": {"en": "Define a tool and run one round of the tool exchange.",
             "ar": "تعرّف أداة وتنفّذ جولة من تبادل الأدوات.", "fr": "Définir un outil."}},
    {"id": "c2.mcp-concepts", "concepts": ["Model Context Protocol", "MCP server", "MCP client"],
     "can": {"en": "Explain what an MCP server gives Claude.", "ar": "تشرح ما يقدمه خادم MCP.",
             "fr": "Expliquer ce qu'un serveur MCP apporte."}},
    {"id": "c0.claude-code-workflow", "concepts": ["plan mode", "commit"],
     "can": {"en": "Go from a plan to a reviewed commit.", "ar": "من الخطة إلى الإيداع.",
             "fr": "Du plan au commit."}},
]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def remote(tmp_path):
    """A git repo laid out like nexika/courses, for prof to clone."""
    root = tmp_path / "remote"
    course = root / "courses" / "ai-engineering"
    modules = {}
    for lid, (title, module, comps) in LESSONS.items():
        modules.setdefault(module, []).append(lid)
        base = course / "lessons" / lid
        write(base / "lesson.json", json.dumps({"id": lid, "title": title, "module": module,
                                                "level": int(lid[1]), "minutes": 30, "competencies": comps,
                                                "prerequisites": []}))
        for lang in ("en", "ar", "fr"):
            write(base / f"{lang}.md", f"# {title[lang]}\n\n## Goals\n\n- {GOALS.get(lid, '')}\n\n## Idea\n\n"
                                       f"{IDEAS.get(lid, {}).get(lang, '')}[^src]\n\nMore text.\n\n"
                                       f"## Later\n\n{LATER}\n")
        write(base / "quiz.json", "{}")
        write(base / "sources.json", "{}")
        write(base / "exercise" / "exercise.json", "{}")
    write(course / "course.json", json.dumps({
        "id": "ai-engineering", "title": {"en": "AI Engineering with Claude Code"},
        "languages": ["en", "ar", "fr"],
        "modules": [{"id": m, "lessons": members} for m, members in modules.items()]}))
    write(course / "competencies.json", json.dumps({"competencies": COMPETENCIES}))
    write(root / "bin" / "courses", FAKE_TOOL)
    write(root / "statuses.json", json.dumps(STATUSES))
    write(root / ".gitignore", "calls.log\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "courses")
    return root


@pytest.fixture
def courses(tmp_path, monkeypatch, remote):
    monkeypatch.setenv("PROF_HOME", str(tmp_path / "prof"))
    monkeypatch.setenv("PROF_COURSES_URL", str(remote))
    spec = importlib.util.spec_from_file_location("prof_courses", COURSES_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["prof_courses"] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "today", lambda: DAY)
    yield module
    sys.modules.pop("prof_courses", None)


def ids(found):
    return [lesson["id"] for lesson in found]


def test_the_first_look_clones_the_courses(courses):
    ok, _ = courses.update()
    assert ok
    assert (courses.CLONE / "courses" / "ai-engineering" / "course.json").exists()
    assert json.loads(courses.STATE.read_text())["fetched"] == DAY.isoformat()


def test_it_pulls_at_most_once_a_week(courses, remote, monkeypatch):
    courses.update()
    statuses = dict(STATUSES, **{"l0-plan-to-commit": "reviewed"})
    write(remote / "statuses.json", json.dumps(statuses))
    _git(remote, "commit", "-q", "-am", "Module 0 reviewed")

    monkeypatch.setattr(courses, "today", lambda: DAY + datetime.timedelta(days=6))
    courses.update()
    assert "l0-plan-to-commit" not in ids(courses.lessons())

    monkeypatch.setattr(courses, "today", lambda: DAY + datetime.timedelta(days=7))
    courses.update()
    assert "l0-plan-to-commit" in ids(courses.lessons())


def test_a_clone_that_fails_leaves_no_lessons_and_no_error(courses, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(courses, "URL", str(tmp_path / "nowhere"))
    ok, message = courses.update()
    assert not ok and message
    assert courses.lessons() == []
    assert courses.main(["prof_courses.py", "find", "tool use"]) == 0
    assert "teach as usual" in capsys.readouterr().out


def test_only_reviewed_and_verified_lessons_are_taught(courses):
    courses.update()
    found = ids(courses.lessons())
    assert sorted(found) == ["l1-tokens-and-context", "l2-tool-use", "l2-what-is-mcp"]
    assert {lesson["status"] for lesson in courses.lessons()} == {"reviewed", "verified"}


def test_the_status_tool_never_runs_lesson_code(courses):
    courses.update()
    courses.lessons()
    calls = (courses.CLONE / "calls.log").read_text().splitlines()
    assert calls and all("--run" not in call.split() for call in calls)
    assert all(call.split()[0] == "status" and "--json" in call.split() for call in calls)


def test_a_broken_status_tool_means_no_lessons(courses):
    courses.update()
    write(courses.CLONE / "bin" / "courses", "#!/usr/bin/env python3\nraise SystemExit(3)\n")
    assert courses.lessons() == []


@pytest.mark.parametrize("topic,first", [
    ("tool use", "l2-tool-use"),
    ("how do I give Claude tools", "l2-tool-use"),
    ("the tool loop", "l2-tool-use"),
    ("context window", "l1-tokens-and-context"),
    ("tokens", "l1-tokens-and-context"),
    ("MCP", "l2-what-is-mcp"),
    ("Model Context Protocol", "l2-what-is-mcp"),
    ("أعطِ Claude أداة", "l2-tool-use"),
    ("fenêtre de contexte", "l1-tokens-and-context"),
    ("function calling", "l2-tool-use"),
    ("علمني استخدام الأدوات", "l2-tool-use"),
])
def test_find_matches_titles_in_every_language_and_the_skills_taught(courses, topic, first):
    courses.update()
    found = courses.find(topic, courses.lessons())
    assert found and found[0]["id"] == first


@pytest.mark.parametrize("topic", ["rust borrow checker", "CSS grid", "teach me", "", "recursion",
                                   "give me a lesson on recursion"])
def test_an_unrelated_topic_finds_nothing(courses, topic):
    courses.update()
    assert courses.find(topic, courses.lessons()) == []


def test_a_tie_goes_to_the_lesson_that_comes_first_in_the_course(courses, remote):
    courses.update()
    found = courses.find("tool", courses.lessons() + [dict(courses.lessons()[1], id="l2-tool-errors")])
    assert [lesson["id"] for lesson in found][:2] == ["l2-tool-use", "l2-tool-errors"]


def test_a_checked_lesson_is_never_found_even_on_an_exact_title(courses):
    courses.update()
    assert courses.find("From plan to commit", courses.lessons()) == []


def test_lesson_files_come_in_the_learners_language_with_english_as_fallback(courses):
    courses.update()
    lesson = next(item for item in courses.lessons() if item["id"] == "l2-tool-use")
    ar = courses.files(lesson, "ar")
    assert ar["text"].name == "ar.md" and ar["text"].exists()
    assert courses.files(lesson, "de")["text"].name == "en.md"
    for key in ("quiz", "sources", "exercise"):
        assert courses.files(lesson, "en")[key].exists(), key


def test_find_prints_the_lesson_and_its_files(courses, capsys):
    assert courses.main(["prof_courses.py", "find", "tool use", "--lang", "ar"]) == 0
    out = capsys.readouterr().out
    assert "l2-tool-use" in out and "verified" in out and "أعطِ Claude أداة" in out
    assert str(courses.CLONE) in out and "ar.md" in out


def test_find_with_no_match_says_to_teach_as_usual(courses, capsys):
    assert courses.main(["prof_courses.py", "find", "rust borrow checker"]) == 0
    assert "teach as usual" in capsys.readouterr().out


def test_no_hook_runs_the_courses_helper():
    """Cloning or pulling happens only when a lesson is looked for, never at session start or end."""
    hooks = (PLUGINS / "prof" / "hooks" / "hooks.json").read_text()
    assert "prof_courses" not in hooks


def test_learn_looks_for_a_course_lesson_before_planning_its_own():
    text = (PLUGINS / "prof" / "skills" / "learn" / "SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/prof_courses.py find" in text
    assert text.index("prof_courses.py find") < text.index("Lesson plan")
