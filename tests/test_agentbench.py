"""The agent benchmark harness (benchmarks/agent): selection, arms, run metrics, grading, summary."""

import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks" / "agent"))

from agentbench import dashboard, grade, metrics, runner, summary, tasks  # noqa: E402


def _row(i, difficulty, repo="o/r"):
    return {"instance_id": f"{repo.replace('/', '__')}-{i}", "repo": repo, "difficulty": difficulty,
            "base_commit": "c" * 40, "version": "1", "created_at": "", "problem_statement": f"bug {i}"}


# --- tasks ---------------------------------------------------------------------------------

def test_strip_never_keeps_the_answer():
    row = {"instance_id": "x", "patch": "GOLD", "test_patch": "TESTS", "hints_text": "HINT",
           "FAIL_TO_PASS": "[]", "PASS_TO_PASS": "[]", "problem_statement": "p"}
    kept = tasks.strip(row)
    assert "GOLD" not in json.dumps(kept) and "TESTS" not in json.dumps(kept)
    assert "HINT" not in json.dumps(kept)
    assert set(kept) == set(tasks.KEEP)


def test_fetch_rows_pages_until_a_short_page():
    pages = [[{"row": _row(i, tasks.EASY)} for i in range(100)],
             [{"row": _row(i, tasks.EASY)} for i in range(100, 130)]]
    calls = []

    def opener(url, timeout):
        calls.append(url)
        return io.BytesIO(json.dumps({"rows": pages[len(calls) - 1]}).encode())

    rows = tasks.fetch_rows(opener=opener)
    assert len(rows) == 130 and len(calls) == 2
    assert "offset=100" in calls[1]


def test_select_is_fixed_by_the_seed_and_meets_quotas():
    rows = [_row(i, d, repo) for i, (d, repo) in enumerate(
        [(tasks.EASY, "a/a"), (tasks.MEDIUM, "b/b"), (tasks.HARD, "c/c")] * 10)]
    quotas = {tasks.EASY: 3, tasks.MEDIUM: 4, tasks.HARD: 2}
    first = tasks.select(rows, quotas, seed=1, max_per_repo=10)
    assert first == tasks.select(list(reversed(rows)), quotas, seed=1, max_per_repo=10)
    got = [r["difficulty"] for r in first]
    assert got.count(tasks.EASY) == 3 and got.count(tasks.MEDIUM) == 4 and got.count(tasks.HARD) == 2


def test_select_caps_one_repository():
    rows = [_row(i, tasks.EASY, "django/django") for i in range(10)]
    rows += [_row(i, tasks.EASY, "x/x") for i in range(10)]
    picked = tasks.select(rows, {tasks.EASY: 6}, seed=3, max_per_repo=3)
    assert sum(r["repo"] == "django/django" for r in picked) == 3


def test_scarce_first_keeps_the_cap_for_rare_tasks():
    rows = [_row(i, tasks.EASY, "django/django") for i in range(10)]
    rows += [_row(i, tasks.HARD, "django/django") for i in range(10, 13)]
    quotas = {tasks.EASY: 3, tasks.HARD: 3}
    with pytest.raises(ValueError):
        tasks.select(rows, {tasks.EASY: 4, tasks.HARD: 3}, seed=1, max_per_repo=6)
    picked = tasks.select(rows, quotas, seed=1, max_per_repo=6, scarce_first=True)
    assert sum(r["difficulty"] == tasks.HARD for r in picked) == 3


def test_pilot_1_still_reproduces():
    rows = [_row(i, d, repo) for i, (d, repo) in enumerate(
        [(tasks.EASY, "a/a"), (tasks.MEDIUM, "b/b"), (tasks.HARD, "c/c")] * 10)]
    quotas = {tasks.EASY: 3, tasks.MEDIUM: 4, tasks.HARD: 2}
    assert tasks.select(rows, quotas, 1, 10) == tasks.select(rows, quotas, 1, 10, scarce_first=False)


def test_select_says_when_a_quota_cannot_be_met():
    with pytest.raises(ValueError, match="1-4 hours"):
        tasks.select([_row(1, tasks.EASY)], {tasks.HARD: 1}, seed=1, max_per_repo=5)


def test_committed_pilot_has_twenty_distinct_tasks():
    pilot = tasks.load_pilot(ROOT / "benchmarks" / "agent" / "pilot.json")
    ids = pilot["instance_ids"]
    assert len(ids) == len(set(ids)) == sum(pilot["quotas"].values()) == 20


# --- runner --------------------------------------------------------------------------------

def test_image_name_follows_swebench():
    assert runner.image_name("psf__requests-2317") == "swebench/sweb.eval.x86_64.psf_1776_requests-2317"
    assert runner.image_name("Django__Django-1") == "swebench/sweb.eval.x86_64.django_1776_django-1"


def test_plan_runs_both_arms_per_task_in_a_seeded_order():
    order = runner.plan(["t1", "t2", "t3", "t4"], runs=2, seed=5)
    assert len(order) == 16
    for task in ("t1", "t2", "t3", "t4"):
        for run in (1, 2):
            assert sorted(a for t, r, a in order if (t, r) == (task, run)) == ["A", "B"]
    assert order == runner.plan(["t1", "t2", "t3", "t4"], runs=2, seed=5)
    firsts = {order[i][2] for i in range(0, 16, 2)}
    assert firsts == {"A", "B"}, "the arm that goes first should vary"


def test_only_arm_b_loads_nexika_and_both_arms_match_otherwise():
    a = runner.claude_args("A", "opus", 5)
    b = runner.claude_args("B", "opus", 5)
    assert "--plugin-dir" not in a
    assert b[: len(a)] == a and b[len(a):] == ["--plugin-dir", runner.PLUGIN_DIR]
    assert "--strict-mcp-config" in a and a[a.index("--permission-prompts") + 1] == "none"


def test_ablation_arms_load_only_their_plugins():
    a = runner.claude_args("A", "sonnet", 5)
    one = runner.claude_args("itqan", "sonnet", 5)
    two = runner.claude_args("haris+barq", "sonnet", 5)
    assert one[len(a):] == ["--plugin-dir", f"{runner.PLUGIN_DIR}/itqan"]
    pd = runner.PLUGIN_DIR
    assert two[len(a):] == ["--plugin-dir", f"{pd}/haris", "--plugin-dir", f"{pd}/barq"]
    assert runner.arm_plugins("B") == metrics.NEXIKA and runner.arm_plugins("A") == ()
    with pytest.raises(ValueError, match="unknown arm"):
        runner.arm_plugins("itqan+ecc")
    assert runner.container_name("t__x-1", "haris+barq", 1) == "agentbench-t-x-1-haris-barq-r1"


def test_exec_env_never_sets_nexika_background(monkeypatch):
    monkeypatch.setenv("NEXIKA_BACKGROUND", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    env = runner.exec_env()
    assert "NEXIKA_BACKGROUND" not in env
    assert env["ANTHROPIC_API_KEY"] == "sk-test" and env["IS_SANDBOX"] == "1"


def test_shim_runs_nexika_on_base_python_and_the_rest_on_the_task_env(tmp_path):
    base, testbed = tmp_path / "base", tmp_path / "testbed"
    for fake in (base, testbed):
        fake.write_text(f"#!/bin/sh\necho {fake.name} \"$@\"\n")
        fake.chmod(0o755)
    shim = tmp_path / "python3"
    shim.write_text(runner.SHIM.replace(runner.BASE_PY, str(base))
                    .replace(f"{runner.TESTBED_BIN}/python3", str(testbed)))
    shim.chmod(0o755)

    def run(*args):
        return subprocess.run([str(shim), *args], capture_output=True, text=True).stdout.strip()

    haris = "/opt/nexika/plugins/haris/bin/haris"
    assert run(haris, "hook") == f"base {haris} hook"
    assert run("-m", "pytest", "tests/") == "testbed -m pytest tests/"
    assert run("setup.py") == "testbed setup.py"
    assert runner.exec_env()["PATH"].split(":")[:2] == [runner.SHIM_DIR, runner.TESTBED_BIN]


def test_prompt_holds_the_issue_and_nothing_about_tests():
    prompt = runner.build_prompt("  The widget breaks.\n")
    assert "<issue>\nThe widget breaks.\n</issue>" in prompt
    assert "FAIL_TO_PASS" not in prompt and "hidden" not in prompt


INIT_B = {"type": "system", "subtype": "init", "session_id": "s1", "model": "claude-opus",
          "plugins": [{"name": n, "path": f"/opt/nexika/plugins/{n}"} for n in metrics.NEXIKA]}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 1.25,
          "duration_ms": 60000, "duration_api_ms": 50000, "num_turns": 12,
          "usage": {"input_tokens": 100, "output_tokens": 200, "cache_read_input_tokens": 3000,
                    "cache_creation_input_tokens": 400},
          "permission_denials": [{"tool_name": "Bash"}]}


class FakeSh:
    """Records docker calls and answers them like a container where claude ran."""

    def __init__(self, stream, diff="", timeout=False):
        self.calls, self.stream, self.diff, self.timeout = [], stream, diff, timeout

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        if "--output-format" in args:
            if self.timeout:
                raise subprocess.TimeoutExpired(args, kw["timeout"], output=self.stream.encode())
            return SimpleNamespace(returncode=0, stdout=self.stream, stderr="")
        if args[-1].endswith("git diff --cached HEAD"):
            return SimpleNamespace(returncode=0, stdout=self.diff, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


CFG = {"model": "opus", "budget": 5, "timeout": 60, "nexika_sha": "abc", "claude_bin": "/bin/claude",
       "credentials": "/c.json", "plugins_dir": "/tmp/plugins", "claude_version": "2.1"}
TASK = {"instance_id": "psf__requests-1", "repo": "psf/requests", "difficulty": tasks.EASY,
        "base_commit": "c" * 40, "problem_statement": "It breaks."}
DIFF = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n-a\n+b\n+c\n"


def test_run_one_arm_b_copies_plugins_and_writes_meta(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    stream = "\n".join(json.dumps(e) for e in (INIT_B, RESULT))
    sh = FakeSh(stream, DIFF)
    ticks = iter([10.0, 70.5])
    meta = runner.run_one(TASK, "B", 1, CFG, tmp_path, sh=sh, clock=lambda: next(ticks))
    cmds = [" ".join(a) for a, _ in sh.calls]
    assert any(f"/tmp/plugins agentbench-psf-requests-1-b-r1:{runner.PLUGIN_DIR}" in c for c in cmds)
    assert any("/c.json" in c for c in cmds), "no token in the env: the login file is copied in"
    assert cmds[-1].startswith("docker rm -f"), "the container is always removed"
    claude = next(kw for a, kw in sh.calls if "--output-format" in a)
    assert "It breaks." in claude["input"]
    assert meta["valid"] and meta["cost_usd"] == 1.25 and meta["wall_s"] == 60.5
    assert meta["files_changed"] == 1 and meta["lines_added"] == 2 and meta["lines_removed"] == 1
    assert meta["permission_denials"] == 1 and meta["nexika_sha"] == "abc"
    assert json.loads((tmp_path / "meta.json").read_text()) == meta
    assert (tmp_path / "diff.patch").read_text() == DIFF


def test_run_one_arm_a_skips_plugins(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    init_a = {**INIT_B, "plugins": []}
    sh = FakeSh("\n".join(json.dumps(e) for e in (init_a, RESULT)))
    meta = runner.run_one(TASK, "A", 1, CFG, tmp_path, sh=sh, clock=lambda: 0.0)
    cmds = [" ".join(a) for a, _ in sh.calls]
    assert not any("/tmp/plugins" in c for c in cmds)
    assert not any("/c.json" in c for c in cmds), "a token in the env: no login file copied"
    assert meta["valid"] and meta["nexika_sha"] == ""


def test_run_one_keeps_the_diff_after_a_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    sh = FakeSh(json.dumps(INIT_B), DIFF, timeout=True)
    meta = runner.run_one(TASK, "B", 1, CFG, tmp_path, sh=sh, clock=lambda: 0.0)
    assert meta["timed_out"] and meta["valid"] and meta["cost_usd"] is None
    assert (tmp_path / "diff.patch").read_text() == DIFF
    assert any("pkill" in a for a, _ in sh.calls)


# --- metrics -------------------------------------------------------------------------------

def test_parse_stream_counts_tools_failures_and_hooks():
    lines = [json.dumps(INIT_B),
             json.dumps({"type": "assistant", "message": {"content": [
                 {"type": "text", "text": "hi"},
                 {"type": "tool_use", "name": "Bash"}, {"type": "tool_use", "name": "Read"}]}}),
             json.dumps({"type": "user", "message": {"content": [
                 {"type": "tool_result", "is_error": True}, {"type": "tool_result"}]}}),
             json.dumps({"type": "system", "subtype": "hook_response", "exit_code": 0}),
             json.dumps({"type": "system", "subtype": "hook_response", "exit_code": 2}),
             json.dumps({"type": "system", "subtype": "hook_response", "exit_code": 1}),
             "not json", "{broken", json.dumps(RESULT)]
    m = metrics.parse_stream(lines)
    assert m["tool_calls"] == 2 and m["bash_calls"] == 1 and m["failed_tool_calls"] == 1
    assert m["hook_runs"] == 3 and m["hook_errors"] == 1, "exit 2 is a hook's deliberate block"
    assert m["plugins_loaded"] == sorted(metrics.NEXIKA)
    assert m["cache_read_tokens"] == 3000 and m["turns"] == 12


def test_plugin_names_with_marketplace_suffix_count():
    m = metrics.parse_stream([json.dumps({**INIT_B, "plugins": [f"{n}@inline" for n in metrics.NEXIKA]})])
    assert m["plugins_loaded"] == sorted(metrics.NEXIKA)


def test_nexika_list_matches_the_marketplace():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert sorted(p["name"] for p in market["plugins"]) == sorted(metrics.NEXIKA)


@pytest.mark.parametrize("arm,plugins,ok,reason", [
    ("B", list(metrics.NEXIKA), True, ""),
    ("B", ["haris"], False, "arm B without amin"),
    ("A", [], True, ""),
    ("A", ["hafiz"], False, "arm A with extra Nexika plugins: hafiz"),
])
def test_validity_checks_the_arm_really_is_that_arm(arm, plugins, ok, reason):
    meta = {"result": "success", "session_id": "s", "plugins_loaded": plugins}
    valid, why = metrics.validity(meta, arm)
    assert valid is ok and reason in why


def test_validity_of_an_ablation_arm():
    meta = {"result": "success", "session_id": "s", "plugins_loaded": ["haris", "barq", "cc-plugin-x"]}
    assert metrics.validity(meta, "haris+barq", ("haris", "barq")) == (True, "")
    why = metrics.validity(meta, "itqan", ("itqan",))[1]
    assert why == "arm itqan with extra Nexika plugins: barq, haris"


def test_parse_stream_finds_test_runs_and_the_first_prompt_size():
    first = {"type": "assistant", "message": {
        "usage": {"input_tokens": 5, "cache_read_input_tokens": 1000,
                  "cache_creation_input_tokens": 200},
        "content": [{"type": "tool_use", "name": "Bash",
                     "input": {"command": "python -m pytest tests/x.py"}}]}}
    later = {"type": "assistant", "message": {
        "usage": {"input_tokens": 9, "cache_read_input_tokens": 9000},
        "content": [{"type": "tool_use", "name": "Bash",
                     "input": {"command": "./tests/runtests.py admin"}},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "grep -rn pytest_plugins ."}}]}}
    hook = {"type": "system", "subtype": "hook_response", "exit_code": 0, "output": "x" * 40}
    m = metrics.parse_stream([json.dumps(e) for e in (hook, first, later)])
    assert m["first_prompt_tokens"] == 1205
    assert m["test_commands"] == 2 and m["ran_tests"], "grep for a word is not a test run"
    assert m["hook_output_chars"] == 40


def test_an_api_failure_is_not_a_failed_task():
    stream = [json.dumps(INIT_B), json.dumps({**RESULT, "is_error": True,
                                              "result": "Claude AI usage limit reached|1760040000"})]
    meta = metrics.parse_stream(stream)
    valid, why = metrics.validity(meta, "B")
    assert not valid and why.startswith("API failure: Claude AI usage limit reached")
    ok = metrics.parse_stream([json.dumps(INIT_B), json.dumps({**RESULT, "is_error": True,
                                                              "result": "max turns"})])
    assert metrics.validity(ok, "B") == (True, "")


def test_validity_rejects_a_run_that_never_started():
    assert metrics.validity({"result": "", "session_id": ""}, "A") == (
        False, "no result event (claude did not finish)")
    assert metrics.validity({"timed_out": True, "session_id": ""}, "A")[0] is False


# --- grade ---------------------------------------------------------------------------------

def test_parse_report_reads_resolved_and_regressions():
    data = {"t": {"patch_successfully_applied": True, "resolved": False, "tests_status": {
        "FAIL_TO_PASS": {"success": ["a"], "failure": []},
        "PASS_TO_PASS": {"success": ["b", "c"], "failure": ["d"]}}}}
    g = grade.parse_report(data, "t")
    assert g["applied"] and not g["resolved"] and g["regression"]
    assert (g["f2p_pass"], g["p2p_pass"], g["p2p_fail"]) == (1, 2, 1)


def test_missing_report_is_not_resolved():
    g = grade.parse_report(None, "t")
    assert not g["graded"] and not g["resolved"] and not g["regression"]


def test_grade_run_skips_empty_diffs_and_reads_reports(tmp_path):
    metas = [{"instance_id": "t1", "arm": "A", "run": 1}, {"instance_id": "t2", "arm": "A", "run": 1}]
    diffs = {("t1", "A", 1): DIFF, ("t2", "A", 1): ""}
    groups = grade.predictions(metas, diffs, "p")
    calls = []

    def sh(cmd, cwd, check):
        calls.append(cmd)
        rp = grade.report_path(cwd, "p__A__r1", "p__A__r1", "t1")
        rp.parent.mkdir(parents=True)
        rp.write_text(json.dumps({"t1": {"resolved": True, "patch_successfully_applied": True}}))

    grades = grade.run(groups, tmp_path, "p", "py", 2, sh=sh)
    assert len(calls) == 1 and "t2" not in calls[0] and "t1" in calls[0]
    assert grades[("t1", "A", 1)]["resolved"] and not grades[("t2", "A", 1)]["resolved"]
    preds = (tmp_path / "p__A__r1.jsonl").read_text().splitlines()
    assert json.loads(preds[0])["model_name_or_path"] == "p__A__r1"


def test_model_label_is_a_valid_docker_name_for_ablation_arms():
    # The harness names its containers after the label; docker refused "+" and the haris+barq
    # arm of pilot 2 was never graded (every run counted as not resolved).
    label = grade.model_label("pilot-2", "haris+barq", 1)
    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", label)
    assert label != grade.model_label("pilot-2", "haris", 1)


def test_validate_grades_gold_patches(tmp_path):
    calls = []

    def sh(cmd, cwd, check):
        calls.append(cmd)
        rp = grade.report_path(cwd, "gold-check", "gold", "t1")
        rp.parent.mkdir(parents=True)
        rp.write_text(json.dumps({"t1": {"resolved": True}}))

    out = grade.validate(["t1", "t2"], tmp_path, "py", 2, test_timeout=60, sh=sh)
    cmd = calls[0]
    assert cmd[cmd.index("--predictions_path") + 1] == "gold" and cmd[cmd.index("--timeout") + 1] == "60"
    assert out["t1"]["resolved"] and not out["t2"]["resolved"]


# --- summary -------------------------------------------------------------------------------

def _run_row(task, arm, resolved, cost, valid=True, difficulty=tasks.EASY):
    return {"instance_id": task, "arm": arm, "run": 1, "valid": valid, "resolved": resolved,
            "regression": False, "cost_usd": cost, "wall_s": 10, "input_tokens": 1, "difficulty": difficulty}


def test_compare_pairs_tasks_and_drops_invalid_runs():
    rows = summary.merge([
        _run_row("t1", "A", False, 2.0), _run_row("t1", "B", True, 1.0),
        _run_row("t2", "A", True, 2.0), _run_row("t2", "B", True, 1.0),
        _run_row("t3", "A", True, 2.0), _run_row("t3", "B", False, 9.0, valid=False),
    ], {})
    comp = summary.compare(rows)
    assert comp["resolved"]["tasks"] == 2, "t3 has no valid run in arm B"
    assert comp["resolved"]["A"] == 0.5 and comp["resolved"]["B"] == 1.0
    assert comp["cost_usd"]["diff"] == -1.0
    lo, hi = comp["cost_usd"]["ci"]
    assert lo == hi == -1.0
    assert summary.cost_per_success(rows, "B") == 1.0


def test_grades_override_nothing_from_the_run_but_add_the_verdict():
    metas = [{"instance_id": "t", "arm": "A", "run": 1, "cost_usd": 1.0, "input_tokens": 5,
              "output_tokens": 5}]
    rows = summary.merge(metas, {("t", "A", 1): {"resolved": True}})
    assert rows[0]["resolved"] and rows[0]["cost_usd"] == 1.0 and rows[0]["tokens"] == 10


def test_bootstrap_is_reproducible():
    diffs = [0.0, 1.0, 0.0, 1.0, -1.0]
    assert summary.bootstrap_ci(diffs) == summary.bootstrap_ci(diffs)
    assert summary.bootstrap_ci([]) == (None, None)


def test_markdown_and_csv(tmp_path):
    rows = summary.merge([_run_row("t1", "A", False, 2.0), _run_row("t1", "B", True, 1.0),
                          _run_row("t2", "A", True, 2.0, valid=False)], {})
    rows[2]["invalid_reason"] = "claude did not start"
    text = summary.markdown(rows, "pilot-x")
    assert "| resolved (higher is better) | 0% | 100% | +100 pts |" in text
    assert "Relative cost reduction (C_A − C_B) / C_A: +50%." in text
    assert "t2 arm A run 1: claude did not start" in text
    summary.write_csv(rows, tmp_path / "r.csv")
    header = (tmp_path / "r.csv").read_text().splitlines()[0].split(",")
    assert header == list(summary.COLUMNS)


def test_sign_test():
    assert summary.sign_test(3, 0) == 0.25
    assert summary.sign_test(0, 0) is None
    assert summary.sign_test(5, 5) == 1.0


def test_ablation_arms_get_their_own_table():
    rows = summary.merge([
        _run_row("t1", "A", False, 1.0), _run_row("t1", "B", True, 2.0), _run_row("t1", "itqan", True, 1.5),
        _run_row("t2", "A", True, 1.0), _run_row("t2", "B", True, 2.0), _run_row("t2", "itqan", False, 1.5),
    ], {})
    for row in rows:
        row["first_prompt_tokens"] = {"A": 20000, "B": 32000, "itqan": 23500}[row["arm"]]
        row["ran_tests"] = row["arm"] != "A"
    text = summary.markdown(rows, "p")
    assert "Arms: A, B, itqan." in text
    assert "Resolved by B only: 1, by A only: 0 (exact sign test p = 1.00)." in text
    assert "| itqan | 2 | 50% → 50% | 1 / 1 | 100% (A 0%) |" in text
    assert "| +3.5k |" in text
    assert "| <15 min fix | 1/2 | 2/2 | 1/2 |" in text


# --- dashboard -----------------------------------------------------------------------------

def _fake_pilot(base, runs, grades, excluded=None):
    """runs: (task, arm, run, cost, difficulty); grades: {(task, arm, run): resolved}."""
    for task, arm, run, cost, difficulty in runs:
        d = base / "runs" / f"{task}__{arm}__r{run}"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({
            "instance_id": task, "arm": arm, "run": run, "valid": True, "invalid_reason": "",
            "difficulty": difficulty, "cost_usd": cost, "ran_tests": arm != "A",
            "first_prompt_tokens": 20000 if arm == "A" else 30000}))
    (base / "grades.json").write_text(json.dumps([
        {"instance_id": t, "arm": a, "run": r, "graded": True, "resolved": ok, "regression": False}
        for (t, a, r), ok in grades.items()]))
    if excluded is not None:
        (base / "excluded.json").write_text(json.dumps(excluded))
    return base


def test_dashboard_view_of_a_finished_pilot(tmp_path):
    runs = [(t, a, 1, 0.1 if a == "A" else 0.2, "1-4 hours") for t in ("t1", "t2") for a in ("A", "B")]
    grades = {("t1", "A", 1): False, ("t1", "B", 1): True, ("t2", "A", 1): True, ("t2", "B", 1): True}
    view = dashboard.pilot_view(_fake_pilot(tmp_path / "pilot-9", runs, grades), planned_tasks=2)
    assert (view["name"], view["done"], view["planned"], view["graded"]) == ("pilot-9", 4, 4, 4)
    assert not view["partial"] and view["invalid"] == 0
    a, b = view["arms"]
    assert (a["arm"], a["resolved"], b["arm"], b["resolved"]) == ("A", 0.5, "B", 1.0)
    assert (b["wins"], b["losses"], b["p"]) == (1, 0, 1.0)
    assert b["cost_solved"] == pytest.approx(0.2) and a["cost_solved"] == pytest.approx(0.2)
    assert b["ran_tests"] == 1.0 and b["first_prompt_extra"] == 10000
    assert view["difficulty"] == {"1-4 hours": {"A": [1, 2], "B": [2, 2]}}


def test_dashboard_counts_only_graded_runs_while_a_pilot_runs(tmp_path):
    runs = [("t1", "A", 1, 0.1, "x"), ("t1", "B", 1, 0.2, "x"), ("t2", "A", 1, 0.1, "x")]
    view = dashboard.pilot_view(_fake_pilot(tmp_path / "p", runs, {("t1", "A", 1): True},
                                            excluded={"t9": "gold patch not graded resolved"}),
                                planned_tasks=3)
    assert (view["done"], view["graded"], view["planned"], view["excluded"]) == (3, 1, 6, 1)
    assert view["partial"]
    assert [a["arm"] for a in view["arms"]] == ["A"]   # B has no graded run yet: not shown as 0%
    newest = max(p.stat().st_mtime for p in (tmp_path / "p" / "runs").glob("*/meta.json"))
    assert dashboard.pilot_view(tmp_path / "p", 3, now=newest + 60)["active"]
    assert not dashboard.pilot_view(tmp_path / "p", 3, now=newest + 3 * 3600)["active"]
    assert view["cost"] == pytest.approx(0.4)


def test_dashboard_html_is_self_contained_and_shows_the_numbers(tmp_path):
    runs = [(t, a, 1, 0.1, "easy") for t in ("t1", "t2") for a in ("A", "B")]
    grades = {(t, a, 1): a == "B" or t == "t1" for t in ("t1", "t2") for a in ("A", "B")}
    view = dashboard.pilot_view(_fake_pilot(tmp_path / "p", runs, grades), planned_tasks=2)
    page = dashboard.render([view], [], refresh=None, now="2026-10-10 14:00")
    assert "<svg" in page and "prefers-color-scheme: dark" in page
    assert "<script" not in page and "http" not in page.replace("http://www.w3.org/2000/svg", "")
    assert "50%" in page and "100%" in page and 'http-equiv="refresh"' not in page
    assert 'http-equiv="refresh" content="60"' in dashboard.render([view], [], refresh=60, now="x")


def test_dashboard_context_table_from_the_context_runs(tmp_path):
    for name, tokens, chars in (("A", 17000, 0), ("lawha", 18800, 182), ("B", 26900, 6812)):
        d = tmp_path / "context" / name
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"arm": name, "first_prompt_tokens": tokens,
                                                 "hook_output_chars": chars}))
    rows = dashboard.context_rows(tmp_path)
    assert rows[0] == {"name": "A", "tokens": 17000, "extra": 0, "hook_chars": 0}
    assert {r["name"]: r["extra"] for r in rows} == {"A": 0, "B": 9900, "lawha": 1800}
    assert [r["name"] for r in rows] == ["A", "B", "lawha"]   # baseline, all, then the most costly


def test_bench_dashboard_writes_the_page(tmp_path, monkeypatch):
    import bench
    runs = [(t, a, 1, 0.1, "easy") for t in ("t1",) for a in ("A", "B")]
    _fake_pilot(tmp_path / "pilot-2", runs, {("t1", "A", 1): True, ("t1", "B", 1): True})
    (tmp_path / "notes").mkdir()   # not a pilot: no runs/ or results.csv
    out = tmp_path / "dash.html"
    bench.main(["dashboard", "--root", str(tmp_path), "--out", str(out)])
    page = out.read_text()
    assert "pilot-2" in page and "notes" not in page
