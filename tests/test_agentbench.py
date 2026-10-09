"""The agent benchmark harness (benchmarks/agent): selection, arms, run metrics, grading, summary."""

import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks" / "agent"))

from agentbench import grade, metrics, runner, summary, tasks  # noqa: E402


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
    ("B", ["haris"], False, "missing"),
    ("A", [], True, ""),
    ("A", ["hafiz"], False, "arm A with Nexika"),
])
def test_validity_checks_the_arm_really_is_that_arm(arm, plugins, ok, reason):
    meta = {"result": "success", "session_id": "s", "plugins_loaded": plugins}
    valid, why = metrics.validity(meta, arm)
    assert valid is ok and reason in why


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
