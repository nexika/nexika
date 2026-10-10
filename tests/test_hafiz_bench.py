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
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hafiz_bench"
FAKE = FIXTURES / "fake_claude.py"
_spec = importlib.util.spec_from_file_location("hafiz_bench", HAFIZ_BENCH / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)
score = bench.score

TASKS = bench.all_tasks()
V2 = {t["id"] for t in bench.load_tasks()["tasks"]}


def _lines(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


# ---- the fixture and the tasks ---------------------------------------------------------------------

@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_each_task_starts_with_only_its_deferred_test_failing(task_id, tmp_path):
    task = TASKS[task_id]
    bench.make_repo(task, tmp_path / "repo")
    bench.run_tests(tmp_path / "repo", bench.folder(task), tmp_path / "tests.json")
    tests = json.loads((tmp_path / "tests.json").read_text())["tests"]
    own = {k: v for k, v in tests.items() if k.startswith("tests.")}
    assert own[task["deferred_test"]] in ("fail", "error")
    assert all(v == "pass" for k, v in own.items() if k != task["deferred_test"])
    # The open steps and the finished steps are not there yet, nor are the decisions about them.
    for spec in task["open"] + task["done"] + [d for d in task["decisions"] if "when" in d]:
        assert tests.get(spec["test"]) != "pass", spec["id"]
    # Every check names a test the hidden file has.
    named = {s.get(k) for s in task["decisions"] + task["open"] + task["done"] for k in ("test", "when")}
    assert named - {None} <= set(tests), named - {None} - set(tests)


def test_tasks_seed_decisions_and_a_deferred_test_in_the_first_prompt():
    for task in TASKS.values():
        first = task["script"][0]["say"]
        assert "Decisions:" in first and "leave it alone until then" in first
        assert task["decisions"] and task["open"] and task["done"]


def test_v2_tasks_have_harder_breaks_than_v1():
    breaks = {t: [p for p, _ in bench.calls_for(TASKS[t]["script"]) if not p.startswith("step")] for t in V2}
    assert breaks == {"loans-compact": ["compact1", "compact2"], "loans-restart": ["compact1", "restart"],
                      "search-restart": ["restart"]}
    # More steps before the first break than v1's three, and decisions stated once, early.
    first = [p for p, _ in bench.calls_for(TASKS["loans-compact"]["script"])].index("compact1")
    assert first == 4
    later = " ".join(i.get("say", "") for i in TASKS["loans-compact"]["script"][1:])
    assert "Decision:" in later.split("Do step 2")[0] and "25 cents" not in later and "casefold" not in later
    # After a restart only a memory of the first session has the decisions.
    for task in ("loans-restart", "search-restart"):
        script = TASKS[task]["script"]
        after = " ".join(i.get("say", "") for i in script[[i.get("restart") for i in script].index(True):])
        assert not any(word in after for word in ("25 cents", "casefold", "DD.MM", "lower", "Decision"))


def test_v1_calls_are_the_steps_then_compact_then_one_continue():
    phases = [p for p, _ in bench.calls_for(TASKS["export"]["script"])]
    assert phases == ["step1", "step2", "step3", "compact1", "step4"]
    assert TASKS["export"]["script"][-1]["say"].startswith("We're back after a break")


def test_describe_counts_the_calls_of_a_script():
    assert bench.describe(TASKS["loans-restart"]["script"]) == \
        "3 steps, /compact, 1 step, new session, 1 step (6 calls)"
    assert bench.describe(TASKS["loans-compact"]["script"]) == \
        "4 steps, /compact, 1 step, /compact, 1 step (8 calls)"


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
    assert "version 2: 12 runs planned, 12 to do (72 claude calls)" in out
    assert "loans-restart: 3 steps, /compact, 1 step, new session, 1 step (6 calls)" in out
    assert "search-restart__hafiz__r2" in out
    assert not (tmp_path / "runs").exists()


def test_the_default_data_folder_keeps_v2_apart_from_v1(monkeypatch):
    monkeypatch.delenv("HAFIZBENCH_HOME", raising=False)
    assert bench.bench_home().parts[-3:] == ("nexika-bench", "hafiz", "v2")


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


def test_redone_tracks_only_work_finished_before_the_break():
    task = {"keep_files": ["m.py"]}
    base = {"m.py": "def old():\n    return 1\n"}
    snap = {"m.py": "def old():\n    return 1\n\n\ndef new(x):\n    y = x + 1\n    return y\n"}
    breaks = [{"snap": snap, "tests": {"t.ok": "pass", "t.deferred": "fail"}}]
    # Rewriting a symbol nobody touched before the break is new work, not a redo; so is fixing a
    # test that failed at the break.
    final = {"m.py": "def old():\n    return 9\n\n\ndef new(x):\n    y = x + 1\n    return y\n"}
    tests = {"t.ok": "pass", "t.deferred": "pass"}
    assert score.redone(task, base, breaks, final, tests) == {"broken": [], "rewritten": [], "duplicated": []}
    # Rewriting a symbol finished before it, or breaking a test that passed then, is.
    final = {"m.py": "def old():\n    return 1\n\n\ndef new(x):\n    return x + 1\n"}
    assert score.redone(task, base, breaks, final, {"t.ok": "fail"}) == {
        "broken": ["t.ok"], "rewritten": ["m.py:new"], "duplicated": []}


# ---- "no redo" by behaviour (v2): the evidence from v1's search runs -------------------------------

V1_SEARCH = sorted((FIXTURES / "v1_search").glob("*.json"))
NOTHING = {"broken": [], "rewritten": [], "duplicated": []}


def _v1(path):
    run = json.loads(path.read_text())
    return run, [{"snap": run["compact"], "tests": run["tests_compact"]}]


def _redo(run, breaks, final=None, tests=None):
    return score.redone(TASKS["search"], run["base"], breaks, final or run["final"],
                        run["tests_final"] if tests is None else tests)


@pytest.mark.parametrize("path", V1_SEARCH, ids=lambda p: p.stem)
def test_v1_search_runs_reused_search_and_redid_nothing(path):
    run, breaks = _v1(path)
    # What v1 counted as redone work: search() is not the same text at the end as before /compact,
    # because step 4 reused its matching (a `fields` or `year` parameter).
    before = score.symbols(run["compact"]["shelf/catalog.py"])["search"]
    assert score.symbols(run["final"]["shelf/catalog.py"])["search"] != before
    # By behaviour nothing was redone: every test that passed before /compact still passes, and
    # search() was extended, not rewritten or copied.
    assert run["tests_final"]["hidden.HiddenTest.test_done_search_command"] == "pass"
    assert _redo(run, breaks) == NOTHING


def test_v1_search_fixtures_are_all_six_runs():
    assert len(V1_SEARCH) == 6


SEARCH_REWRITTEN = '''def search(books, text):
    """Rewritten from scratch: a regular expression per word."""
    import re

    patterns = [re.compile(re.escape(w), re.I) for w in text.split()]
    return [b for b in books if all(p.search(b["title"] + " " + b["author"]) for p in patterns)]
'''


def _replace_search(source, new):
    node = next(n for n in score.ast.parse(source).body if getattr(n, "name", "") == "search")
    lines = source.splitlines(keepends=True)
    return "".join(lines[: node.lineno - 1]) + new + "".join(lines[node.end_lineno:])


def test_a_finished_function_rewritten_from_scratch_is_redo():
    run, breaks = _v1(V1_SEARCH[0])
    final = dict(run["final"])
    final["shelf/catalog.py"] = _replace_search(final["shelf/catalog.py"], SEARCH_REWRITTEN)
    assert _redo(run, breaks, final)["rewritten"] == ["shelf/catalog.py:search"]


def test_a_finished_function_copied_under_a_new_name_is_redo():
    run, breaks = _v1(V1_SEARCH[0])
    final = dict(run["final"])
    source = score.symbol_sources(run["compact"]["shelf/catalog.py"])["search"]
    final["shelf/cli.py"] += "\n\n" + source.replace("def search(", "def search_books(", 1) + "\n"
    assert _redo(run, breaks, final)["duplicated"] == [
        "shelf/cli.py:search_books copies shelf/catalog.py:search"]


def test_a_name_defined_twice_is_redo():
    run, breaks = _v1(V1_SEARCH[0])
    final = dict(run["final"])
    final["shelf/catalog.py"] += "\n\ndef find(books):\n    return books\n"
    assert _redo(run, breaks, final)["duplicated"] == ["shelf/catalog.py:find"]


def test_finished_work_that_no_longer_passes_its_tests_is_redo():
    run, breaks = _v1(V1_SEARCH[0])
    tests = dict(run["tests_final"], **{"hidden.HiddenTest.test_done_search_command": "fail",
                                         "tests.test_catalog.CatalogTest.test_load": "error"})
    assert _redo(run, breaks, tests=tests)["broken"] == [
        "hidden.HiddenTest.test_done_search_command", "tests.test_catalog.CatalogTest.test_load"]
    # A test the agent removed is not counted, and one that failed before the break was not
    # finished work.
    tests = {k: v for k, v in run["tests_final"].items() if k != "tests.test_cli.CliTest.test_search"}
    assert _redo(run, breaks, tests=tests)["broken"] == []


def test_moving_finished_code_into_a_helper_is_a_refactor_not_redo():
    run, breaks = _v1(V1_SEARCH[3])
    compact = run["compact"]["shelf/catalog.py"]
    helper = score.symbol_sources(compact)["search"].replace("def search(", "def _search_all(", 1)
    final = dict(run["compact"])
    final["shelf/catalog.py"] = _replace_search(compact, helper + '''


def search(books, text, *, year=None):
    """search, then the year filter."""
    found = _search_all(books, text)
    return [b for b in found if year is None or b["year"] == year]
''')
    assert _redo(run, breaks, final) == NOTHING


def test_work_finished_before_a_later_break_is_checked_too():
    run, breaks = _v1(V1_SEARCH[0])
    # Two breaks, and search() was finished between them.
    breaks = [{"snap": dict(run["base"]), "tests": {}}, breaks[0]]
    final = dict(run["final"])
    final["shelf/catalog.py"] = _replace_search(final["shelf/catalog.py"], SEARCH_REWRITTEN)
    assert _redo(run, breaks, final)["rewritten"] == ["shelf/catalog.py:search"]


def test_test_source_finds_one_method():
    source = "class T:\n    def test_a(self):\n        assert 1\n"
    assert score.test_source(source, "tests.mod.T.test_a")
    assert score.test_source(source, "tests.mod.T.test_b") is None
    assert score.test_source("def (", "tests.mod.T.test_a") is None


# ---- end to end, with the scripted claude ------------------------------------------------------------

def _fake_claude(tmp_path, scenario):
    folder = tmp_path / f"bin-{scenario}"
    folder.mkdir(exist_ok=True)
    wrapper = folder / "claude"
    wrapper.write_text(f'#!/bin/sh\nFAKE_SCENARIO={scenario} exec "{sys.executable}" "{FAKE}" "$@"\n')
    wrapper.chmod(0o755)
    return folder


def _run(tmp_path, monkeypatch, scenario, arm, task_id="export", run=1, max_total=5.0):
    folder = _fake_claude(tmp_path, scenario)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")
    cfg = {"runs_dir": tmp_path / "runs", "auth": {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, "model": "sonnet",
           "budget": 1.0, "max_total": max_total, "timeout": 60, "plugin_dir": "/fake/hafiz"}
    task = TASKS[task_id]
    out = bench.run_one(task, arm, run, cfg, task["script"], 2 if task_id in V2 else 1)
    return out, score.score_run(out, task)


def _failed(row):
    return {c["id"] for g in ("decisions", "open_work") for c in row["checks"][g] if c["ok"] is False}


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
    assert [c["phase"] for c in meta["calls"]] == ["step1", "step2", "step3", "compact1", "step4"]
    assert [b["kind"] for b in meta["breaks"]] == ["compact"] and meta["breaks"][0]["at"] == 3
    assert "format_price" in (out / "diff.patch").read_text() or "money" in (out / "diff.patch").read_text()


def test_a_bad_plain_run_loses_decisions_open_work_and_redoes(tmp_path, monkeypatch):
    _, row = _run(tmp_path, monkeypatch, "bad", "plain")
    assert row["valid"], row["invalid"]
    assert {"no-pandas", "step4-load-csv", "deferred-test-fixed"} <= _failed(row)
    assert row["test_edited"]
    # export.py written again whole with pandas: the finished functions are rewritten and no longer work.
    assert row["redo"]["rewritten"] == ["shelf/export.py:export_csv", "shelf/export.py:export_json"]
    assert "hidden.HiddenTest.test_done_export_csv" in row["redo"]["broken"]
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


# v2: two compactions, and a restart in a new session.

def test_two_compactions_are_two_breaks_and_both_must_compact(tmp_path, monkeypatch):
    out, row = _run(tmp_path, monkeypatch, "good", "hafiz", "loans-compact")
    assert row["valid"], row["invalid"]
    assert row["breaks"] == ["compact", "compact"]
    assert (row["decisions"], row["open_work"], row["no_redo"]) == (1.0, 1.0, 1.0)
    assert all(c["ok"] for c in row["checks"]["done"])
    meta = json.loads((out / "meta.json").read_text())
    assert [c["phase"] for c in meta["calls"]] == ["step1", "step2", "step3", "step4", "compact1", "step5",
                                                   "compact2", "step6"]
    assert {c["session"] for c in meta["calls"]} == {1} and len(meta["sessions"]) == 1
    assert [b["at"] for b in meta["breaks"]] == [4, 6]
    # Step 5 was done between the two compactions: finished work at the second break only.
    first, second = (json.loads((out / b["tests"]).read_text())["tests"] for b in meta["breaks"])
    assert first["hidden.HiddenTest.test_done_days_late"] == "pass"
    assert first.get("hidden.HiddenTest.test_open_fine_cents") != "pass"
    assert second["hidden.HiddenTest.test_open_fine_cents"] == "pass"
    assert row["restore_chars"] == 1800 and row["restart_card_chars"] == 0
    # Tokens after the first break count the steps after it, not the /compact calls.
    assert row["turns_after"] == 6 and row["first_prompt_after"] == 21005


def test_a_good_restart_run_starts_a_new_session_in_the_same_repo(tmp_path, monkeypatch):
    out, row = _run(tmp_path, monkeypatch, "good", "hafiz", "loans-restart")
    assert row["valid"], row["invalid"]
    assert row["breaks"] == ["compact", "restart"]
    assert (row["decisions"], row["open_work"], row["no_redo"]) == (1.0, 1.0, 1.0)
    meta = json.loads((out / "meta.json").read_text())
    assert [c["session"] for c in meta["calls"]] == [1, 1, 1, 1, 1, 2]
    assert len(set(meta["sessions"])) == 2
    # The new session is started, not resumed: its id is new and claude saw --session-id.
    last = score.read_call(out / meta["calls"][-1]["file"])
    assert last["session_id"] == meta["sessions"][1]
    assert [h["name"] for h in last["hooks"]] == ["SessionStart:startup"]
    assert row["restart_card_chars"] == 700 and row["restore_chars"] == 900
    # Each session's transcript is kept.
    assert (out / "transcript-1.jsonl").is_file() and (out / "transcript-2.jsonl").is_file()


def test_a_bad_restart_run_forgets_the_decisions_and_redoes_finished_work(tmp_path, monkeypatch):
    _, row = _run(tmp_path, monkeypatch, "bad", "plain", "loans-restart")
    assert row["valid"], row["invalid"]
    assert {"fine-rule", "fines-in-overdue-command", "member-casefold", "no-lower", "dates-overdue-command",
            "deferred-test-fixed"} <= _failed(row)
    assert "dates-loans-command" not in _failed(row)  # done before the break, and kept
    assert row["redo"]["rewritten"] == ["shelf/loans.py:overdue"]
    assert row["redo"]["duplicated"] == ["shelf/loans.py:read_loans copies shelf/loans.py:load_loans"]
    assert row["redo"]["broken"] == []
    assert row["no_redo"] == 0.0 and row["continuity"] < 0.5
    assert row["restart_card_chars"] == 0


def test_a_restart_that_resumed_the_old_session_is_invalid(tmp_path, monkeypatch):
    _, row = _run(tmp_path, monkeypatch, "stuck", "plain", "loans-restart")
    assert "restart did not start a new session" in row["invalid"]


def test_a_compaction_only_the_transcript_shows_still_counts(tmp_path, monkeypatch):
    _, row = _run(tmp_path, monkeypatch, "quietcompact", "plain", "loans-compact")
    assert row["valid"], row["invalid"]
    out, row = _run(tmp_path, monkeypatch, "quietcompact", "plain", "loans-compact", run=2)
    (out / "transcript-1.jsonl").write_text("")
    assert "no compaction" in score.score_run(out, TASKS["loans-compact"])["invalid"]


def test_score_command_writes_the_summary_for_both_arms_and_every_task(tmp_path, monkeypatch, capsys):
    _run(tmp_path, monkeypatch, "good", "hafiz")
    _run(tmp_path, monkeypatch, "bad", "plain")
    _run(tmp_path, monkeypatch, "good", "hafiz", "loans-restart")
    _run(tmp_path, monkeypatch, "bad", "plain", "loans-restart")
    assert bench.main(["score", "--home", str(tmp_path)]) == 0
    summary = (tmp_path / "summary.md").read_text()
    assert "| hafiz | 2 (0 invalid) | 1.00" in summary
    assert "| plain | 2 (0 invalid) |" in summary
    assert "| loans-restart | hafiz | 1 (0 invalid) | 1.00 |" in summary
    assert "redo rewritten shelf/export.py:export_csv" in summary
    assert "redo duplicated shelf/loans.py:read_loans" in summary
    rows = json.loads((tmp_path / "results.json").read_text())
    assert {(r["task"], r["arm"], r["version"]) for r in rows} == {
        ("export", "hafiz", 1), ("export", "plain", 1), ("loans-restart", "hafiz", 2),
        ("loans-restart", "plain", 2)}


def test_the_total_budget_stops_a_run_before_the_next_call(tmp_path, monkeypatch):
    out, _ = _run(tmp_path, monkeypatch, "good", "plain", max_total=0.1)
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
