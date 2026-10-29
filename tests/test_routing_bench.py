"""The skill routing check (#431): benchmarks/routing/bench.py. The paid run isn't part of the tests;
these check the cases, the isolation and how a session's output is read."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest
from conftest import PLUGINS

BENCH_DIR = PLUGINS.parent / "benchmarks" / "routing"
spec = importlib.util.spec_from_file_location("routing_bench", BENCH_DIR / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.mark.parametrize("suite", ["prof", "lawha", "manar"])
def test_every_skill_of_a_suite_has_a_case_and_ordinary_work_has_some(suite):
    cases = [c for c in bench.load_cases() if c["suite"] == suite]
    expected = {c["expected"] for c in cases}
    skills = {f"{suite}:{p.parent.name}" for p in (PLUGINS / suite / "skills").glob("*/SKILL.md")}
    assert skills <= expected
    assert sum(c["kind"] == "negative" for c in cases) >= 5
    assert suite in bench.FIXTURES


def test_a_case_expects_a_skill_of_its_own_suite_and_a_known_kind():
    for case in bench.load_cases():
        assert case["expected"] == "-" or case["expected"].startswith(case["suite"] + ":"), case
        assert case["kind"] in bench.KINDS, case


def test_case_ids_stay_put_so_saved_runs_still_match():
    """Ids are row numbers: new cases go at the end. These are the first prof rows (#438's runs)."""
    cases = bench.load_cases()
    assert cases[0]["prompt"] == "Teach me async/await in Python."
    assert cases[8]["prompt"] == "Check my understanding of closures in JavaScript."
    assert cases[19]["prompt"] == "Thanks, that's all for today. Bye!"


def test_the_lawha_project_looks_like_a_frontend_to_lawha(tmp_path):
    for name, text in bench.FIXTURES["lawha"].items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    out = subprocess.run(["sh", str(PLUGINS / "lawha" / "bin" / "lawha"), "has-frontend", str(tmp_path)],
                         capture_output=True, text=True)
    assert out.stdout.strip() == "yes"


def test_every_expected_skill_exists():
    for case in bench.load_cases():
        if case["expected"] != "-":
            plugin, _, skill = case["expected"].partition(":")
            assert (PLUGINS / plugin / "skills" / skill / "SKILL.md").exists(), case


def test_sessions_cannot_edit_or_run_anything():
    args = bench.claude_args(["/p/prof"], "sonnet", 2, 0.25)
    allowed = args[args.index("--allowedTools") + 1].split(",")
    denied = args[args.index("--disallowedTools") + 1].split(",")
    assert set(allowed) == {"Skill", "Read", "Grep", "Glob"}
    assert {"Bash", "Edit", "Write"} <= set(denied)
    assert "bypassPermissions" not in args and "--dangerously-skip-permissions" not in args


def test_the_session_gets_a_throwaway_home_and_only_the_login(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("NEXIKA_BACKGROUND", "1")
    monkeypatch.setenv("SOME_SECRET", "x")
    env = bench.isolated_env(tmp_path)
    assert env["HOME"] == str(tmp_path)
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / ".claude")
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    assert "NEXIKA_BACKGROUND" not in env and "SOME_SECRET" not in env


def _stream(*blocks):
    events = [{"type": "system", "subtype": "init", "plugins": [{"name": "prof", "path": "/p/prof"}]}]
    events += [{"type": "assistant", "message": {"content": [b]}} for b in blocks]
    events.append({"type": "result", "total_cost_usd": 0.03})
    return [json.dumps(e) for e in events] + ["not json"]


def test_skills_called_reads_skill_tool_calls_in_order():
    lines = _stream({"type": "tool_use", "name": "Read", "input": {"file_path": "app.py"}},
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "prof:walkthrough"}},
                    {"type": "tool_use", "name": "Skill", "input": {"command": "/prof:report"}},
                    {"type": "text", "text": "Skill"})
    assert bench.skills_called(lines) == ["prof:walkthrough", "prof:report"]
    assert bench.cost(lines) == 0.03
    assert bench.plugins_loaded(lines) == ["prof"]


def test_the_manar_project_is_a_website_to_manar(tmp_path):
    sys.path.insert(0, str(PLUGINS / "manar"))
    from manar import hook
    for name, text in bench.FIXTURES["manar"].items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    assert "manar" in hook.session_note(tmp_path)


def test_a_case_is_right_when_its_skill_ran_and_a_negative_when_its_suite_stayed_out():
    learn = {"suite": "prof", "expected": "prof:learn"}
    none = {"suite": "prof", "expected": "-"}
    assert bench.correct(learn, ["prof:warmup", "prof:learn"])
    assert not bench.correct(learn, ["prof:quiz"])
    assert not bench.correct(learn, [])
    assert bench.correct(none, [])
    assert bench.correct(none, ["bayan:check"])
    assert not bench.correct(none, ["prof:learn"])
    assert not bench.correct({"suite": "lawha", "expected": "-"}, ["lawha:check"])
    assert bench.correct({"suite": "lawha", "expected": "-"}, ["prof:learn"])


def test_the_report_counts_valid_runs_per_kind_and_arm():
    cases = [{"id": 1, "suite": "prof", "expected": "prof:quiz", "kind": "kept", "prompt": "Quiz me"},
             {"id": 2, "suite": "prof", "expected": "-", "kind": "negative", "prompt": "What is X?"}]
    results = [
        {"case": 1, "arm": "main", "called": ["prof:quiz"], "correct": True, "valid": True, "cost_usd": 0.02},
        {"case": 1, "arm": "new", "called": ["prof:learn"], "correct": False, "valid": True,
         "cost_usd": 0.02},
        {"case": 2, "arm": "new", "called": [], "correct": True, "valid": False, "cost_usd": 0.01},
    ]
    text = bench.markdown(cases, results, ["main", "new"])
    assert "| kept | 1/1 | 0/1 |" in text
    assert "| negative | 0/0 | 0/0 |" in text
    assert "paraphrase" not in text   # only the kinds the cases use
    assert "(got prof:learn)" in text
    assert "2 valid runs, 1 invalid, $0.05 in all." in text


def test_refs_are_arm_equals_ref():
    assert bench.parse_refs("main=origin/main, new=HEAD") == {"main": "origin/main", "new": "HEAD"}
