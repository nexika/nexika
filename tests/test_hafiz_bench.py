"""The hafiz continuity benchmark (benchmarks/hafiz, #348): fixture, runner and scorer, offline.

The end-to-end tests drive bench.run_one with a scripted stand-in for `claude -p`
(fixtures/hafiz_bench/fake_claude.py), so the real runner, test reporter and scorer run together
without a model.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HAFIZ_BENCH = ROOT / "benchmarks" / "hafiz"
FAKE = Path(__file__).resolve().parent / "fixtures" / "hafiz_bench" / "fake_claude.py"
_spec = importlib.util.spec_from_file_location("hafiz_bench", HAFIZ_BENCH / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)
score = bench.score

TASKS = {t["id"]: t for t in bench.load_tasks()["tasks"]}


def _lines(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


# ---- the fixture and the tasks ---------------------------------------------------------------------

@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_each_task_starts_with_only_its_deferred_test_failing(task_id, tmp_path):
    task = TASKS[task_id]
    bench.make_repo(task, tmp_path / "repo")
    bench.run_tests(tmp_path / "repo", task_id, tmp_path / "tests.json")
    tests = json.loads((tmp_path / "tests.json").read_text())["tests"]
    own = {k: v for k, v in tests.items() if k.startswith("tests.")}
    assert own[task["deferred_test"]] in ("fail", "error")
    assert all(v == "pass" for k, v in own.items() if k != task["deferred_test"])
    # The open steps and the finished steps are not there yet.
    for spec in task["open"] + task["done"]:
        assert tests.get(spec["test"]) != "pass", spec["id"]
    # Every check names a test the hidden file has.
    named = {s.get("test") for s in task["decisions"] + task["open"] + task["done"]} - {None}
    assert named <= set(tests), named - set(tests)


def test_tasks_seed_decisions_and_a_deferred_test_in_the_first_step():
    for task in TASKS.values():
        first = task["steps"][0]
        assert "Decisions:" in first and "leave it alone until then" in first
        assert len(task["steps"]) >= 3 and task["decisions"] and task["open"]


def test_calls_are_the_steps_then_compact_then_one_continue():
    phases = [p for p, _ in bench.calls_for(TASKS["export"], "go on")]
    assert phases == ["step1", "step2", "step3", "compact", "continue"]


# ---- the runner's pieces ---------------------------------------------------------------------------

def test_plan_pairs_both_arms_for_every_task_and_run():
    order = bench.plan(["a", "b"], ["plain", "hafiz"], 2)
    assert len(order) == 8 and len(set(order)) == 8
    assert order == bench.plan(["a", "b"], ["plain", "hafiz"], 2)
    assert {arm for t, arm, r in order[:2]} == {"plain", "hafiz"}


def test_claude_args_differ_between_arms_only_in_the_plugin():
    plain = bench.claude_args("p", "plain", "sonnet", 1.0, "s1", True, None)
    hafiz = bench.claude_args("p", "hafiz", "sonnet", 1.0, "s1", True, "/x/hafiz")
    assert hafiz == plain + ["--plugin-dir", "/x/hafiz"]
    assert ["--session-id", "s1"] == plain[plain.index("--session-id"):][:2]
    later = bench.claude_args("/compact", "plain", "sonnet", 1.0, "s1", False, None)
    assert "--resume" in later and "--session-id" not in later
    with pytest.raises(ValueError):
        bench.claude_args("p", "hafiz", "sonnet", 1.0, "s1", True, None)


def test_auth_comes_from_the_environment_or_the_token_file_only(tmp_path, monkeypatch):
    for key in bench.AUTH_VARS:
        monkeypatch.delenv(key, raising=False)
    token = tmp_path / "token"
    assert bench.auth_env(token) == {}
    token.write_text("abc\n")
    assert bench.auth_env(token) == {"CLAUDE_CODE_OAUTH_TOKEN": "abc"}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert bench.auth_env(token) == {"ANTHROPIC_API_KEY": "k"}


def test_run_env_is_clean_and_keeps_hafiz_on(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXIKA_BACKGROUND", "1")
    monkeypatch.setenv("CLAUDECODE", "1")
    env = bench.run_env(tmp_path / "home", {"CLAUDE_CODE_OAUTH_TOKEN": "t"})
    assert env["HOME"] == str(tmp_path / "home")
    assert "NEXIKA_BACKGROUND" not in env and "CLAUDECODE" not in env
    assert env["NEXIKA_HOME"].startswith(str(tmp_path))


def test_dry_run_lists_the_plan_and_calls_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HAFIZBENCH_HOME", str(tmp_path))
    assert bench.main(["run", "--dry-run", "--runs", "2"]) == 0
    out = capsys.readouterr().out
    assert "12 runs planned, 12 to do" in out and "export__hafiz__r2" in out
    assert not (tmp_path / "runs").exists()


def test_run_refuses_to_start_without_a_login(tmp_path, monkeypatch):
    monkeypatch.setenv("HAFIZBENCH_HOME", str(tmp_path))
    for key in bench.AUTH_VARS:
        monkeypatch.delenv(key, raising=False)
    assert bench.main(["run", "--token-file", str(tmp_path / "missing")]) == 2


# ---- the scorer's rules ----------------------------------------------------------------------------

def test_hook_context_reads_additional_context_or_plain_output():
    as_json = {"output": json.dumps({"hookSpecificOutput": {"additionalContext": "abc"}})}
    assert score.hook_context(as_json) == "abc"
    assert score.hook_context({"output": "plain text\n"}) == "plain text\n"


def test_read_call_counts_usage_tools_hooks_and_the_compaction(tmp_path):
    stream = tmp_path / "call.jsonl"
    stream.write_text(_lines(
        {"type": "system", "subtype": "init", "session_id": "s", "plugins": [{"name": "hafiz@inline"}]},
        {"type": "system", "subtype": "hook_response", "hook_name": "SessionStart:compact",
         "output": json.dumps({"hookSpecificOutput": {"additionalContext": "x" * 40}})},
        {"type": "system", "subtype": "compact_boundary"},
        {"type": "assistant", "message": {"usage": {"input_tokens": 3, "cache_read_input_tokens": 100},
                                          "content": [{"type": "tool_use", "name": "Write", "input": {}}]}},
        {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.2, "num_turns": 2,
         "usage": {"input_tokens": 3, "output_tokens": 7}},
    ) + "not json\n")
    call = score.read_call(stream)
    assert call["plugins"] == ["hafiz"] and call["compacted"]
    assert call["hooks"] == [{"name": "SessionStart:compact", "chars": 40}]
    assert call["first_prompt_tokens"] == 103 and call["cost_usd"] == 0.2
    assert [t["name"] for t in call["tool_uses"]] == ["Write"]


def test_checks_absent_unchanged_test_and_when():
    diff = "+++ b/shelf/export.py\n+import pandas\n-import pandas as old\n"
    assert score.check({"absent": r"^\+.*\bimport\s+pandas"}, {}, diff, {}, {}) is False
    assert score.check({"absent": r"^\+.*\bimport\s+pandas"}, {}, "-import pandas\n", {}, {}) is True
    assert score.check({"unchanged": "a"}, {}, "", {"a": "1"}, {"a": "1"}) is True
    assert score.check({"unchanged": "a"}, {}, "", {"a": "1"}, {"a": "2"}) is False
    tests = {"t": "pass", "u": "fail"}
    assert score.check({"test": "t"}, tests, "", {}, {}) is True
    assert score.check({"test": "u"}, tests, "", {}, {}) is False
    assert score.check({"test": "t", "when": "u"}, tests, "", {}, {}) is None
    no_lower = {"absent": TASKS["search"]["decisions"][0]["absent"]}
    assert score.check(no_lower, {}, "+    # not .lower() here\n", {}, {}) is True
    assert score.check(no_lower, {}, "+    t = text.lower()\n", {}, {}) is False


def test_redone_tracks_only_work_finished_before_the_compaction():
    task = {"keep_files": ["m.py"]}
    base = {"m.py": "def old():\n    return 1\n"}
    compact = {"m.py": "def old():\n    return 1\n\n\ndef new():\n    return 2\n", "n.py": "x = 1\n"}
    # Changing a symbol nobody touched before the compaction is new work, not a redo.
    final = {"m.py": "def old():\n    return 9\n\n\ndef new():\n    return 2\n"}
    assert score.redone(task, base, compact, final, [], "/r") == {"changed": [], "rewritten": [],
                                                                    "duplicated": []}
    # Changing a symbol finished before it, or defining it twice, is.
    final = {"m.py": "def new():\n    return 3\n\n\ndef new():\n    return 2\n"}
    later = [{"name": "Write", "input": {"file_path": "/r/n.py"}}]
    redo = score.redone(task, base, compact, final, later, "/r")
    assert redo == {"changed": ["m.py:new"], "rewritten": ["n.py"], "duplicated": ["m.py:new"]}


def test_test_source_finds_one_method():
    source = "class T:\n    def test_a(self):\n        assert 1\n"
    assert score.test_source(source, "tests.mod.T.test_a")
    assert score.test_source(source, "tests.mod.T.test_b") is None
    assert score.test_source("def (", "tests.mod.T.test_a") is None


# ---- end to end, with the scripted claude ------------------------------------------------------------

def _fake_claude(tmp_path, scenario):
    folder = tmp_path / f"bin-{scenario}"
    folder.mkdir()
    wrapper = folder / "claude"
    wrapper.write_text(f'#!/bin/sh\nFAKE_SCENARIO={scenario} exec "{sys.executable}" "{FAKE}" "$@"\n')
    wrapper.chmod(0o755)
    return folder


def _run(tmp_path, monkeypatch, scenario, arm, run=1):
    folder = _fake_claude(tmp_path, scenario)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")
    cfg = {"runs_dir": tmp_path / "runs", "auth": {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, "model": "sonnet",
           "budget": 1.0, "max_total": 5.0, "timeout": 60, "plugin_dir": "/fake/hafiz"}
    out = bench.run_one(TASKS["export"], arm, run, cfg, "We're back. Carry on.")
    return out, score.score_run(out, TASKS["export"])


def test_a_good_hafiz_run_keeps_everything(tmp_path, monkeypatch):
    out, row = _run(tmp_path, monkeypatch, "good", "hafiz")
    assert row["valid"], row["invalid"]
    assert row["compacted"] and not row["fixed_early"]
    assert (row["decisions"], row["open_work"], row["no_redo"], row["continuity"]) == (1.0, 1.0, 1.0, 1.0)
    assert all(c["ok"] for c in row["checks"]["done"])
    assert row["restore_chars"] == 900 and row["hook_chars"] > 900
    assert row["cost_usd"] == pytest.approx(0.25)
    assert row["first_prompt_after"] == 21005
    meta = json.loads((out / "meta.json").read_text())
    assert [c["phase"] for c in meta["calls"]] == ["step1", "step2", "step3", "compact", "continue"]
    assert "format_price" in (out / "diff.patch").read_text() or "money" in (out / "diff.patch").read_text()


def test_a_bad_plain_run_loses_decisions_open_work_and_redoes(tmp_path, monkeypatch):
    _, row = _run(tmp_path, monkeypatch, "bad", "plain")
    assert row["valid"], row["invalid"]
    failed = {c["id"] for g in ("decisions", "open_work") for c in row["checks"][g] if c["ok"] is False}
    assert {"no-pandas", "step4-load-csv", "deferred-test-fixed"} <= failed
    assert row["test_edited"]
    assert row["redo"]["rewritten"] == ["shelf/export.py"]
    assert "shelf/export.py:export_csv" in row["redo"]["changed"]
    assert row["no_redo"] == 0.0 and row["continuity"] < 0.5
    assert row["restore_chars"] == 0 and row["hook_chars"] == 0


def test_a_run_that_did_not_compact_is_invalid(tmp_path, monkeypatch):
    _, row = _run(tmp_path, monkeypatch, "nocompact", "plain")
    assert not row["valid"] and "no compaction" in row["invalid"]


def test_an_arm_that_did_not_load_what_it_claims_is_invalid(tmp_path, monkeypatch):
    out, _ = _run(tmp_path, monkeypatch, "good", "plain")
    meta = json.loads((out / "meta.json").read_text())
    meta["arm"] = "hafiz"
    (out / "meta.json").write_text(json.dumps(meta))
    assert "hafiz arm without hafiz" in score.score_run(out, TASKS["export"])["invalid"]


def test_score_command_writes_the_summary_for_both_arms(tmp_path, monkeypatch, capsys):
    _run(tmp_path, monkeypatch, "good", "hafiz")
    _run(tmp_path, monkeypatch, "bad", "plain")
    assert bench.main(["score", "--home", str(tmp_path)]) == 0
    summary = (tmp_path / "summary.md").read_text()
    assert "| hafiz | 1 (0 invalid) | 1.00" in summary
    assert "| plain | 1 (0 invalid) |" in summary
    assert "redo shelf/export.py" in summary
    rows = json.loads((tmp_path / "results.json").read_text())
    assert {r["arm"] for r in rows} == {"plain", "hafiz"}


def test_the_total_budget_stops_a_run_before_the_next_call(tmp_path, monkeypatch):
    folder = _fake_claude(tmp_path, "good")
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")
    cfg = {"runs_dir": tmp_path / "runs", "auth": {"X": "t"}, "model": "sonnet", "budget": 1.0,
           "max_total": 0.1, "timeout": 60, "plugin_dir": None}
    out = bench.run_one(TASKS["export"], "plain", 1, cfg, "go on")
    meta = json.loads((out / "meta.json").read_text())
    assert len(meta["calls"]) == 2 and "total budget" in meta["stopped"]


def test_runtests_reports_a_module_that_does_not_import(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_x.py").write_text("import missing_module_xyz\n")
    done = subprocess.run([sys.executable, str(HAFIZ_BENCH / "runtests.py"), str(tmp_path)],
                          capture_output=True, text=True, check=True)
    data = json.loads(done.stdout)
    assert data["load_errors"] and data["tests"]
