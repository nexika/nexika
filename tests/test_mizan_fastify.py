"""mizan on fastify/fastify (#52): real gh JSON, trimmed (fixtures/mizan_fastify.json)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from conftest import PLUGINS

MIZAN_ROOT = PLUGINS / "mizan"
if str(MIZAN_ROOT) not in sys.path:
    sys.path.insert(0, str(MIZAN_ROOT))

from mizan import forge, render  # noqa: E402

FASTIFY = json.loads((Path(__file__).parent / "fixtures" / "mizan_fastify.json").read_text(encoding="utf-8"))
RUNS, CHECKS = FASTIFY["runs"], FASTIFY["checks"]


def head_of(pr: str) -> str:
    return RUNS[pr][0]["headSha"]


def info_for(tmp_path, pr: str, branch: str = "feature") -> dict:
    return {"repo": str(tmp_path), "branch": branch, "head": head_of(pr), "host": "github", "remote": "x"}


def fake_gh(runs: list, checks: list | None = None, jobs: dict | None = None):
    """A forge.run_tool answering `gh run list`, `gh run view` and `gh pr checks`; it records every call."""
    calls = []

    def tool(argv, cwd, accept_codes=(0,)):
        calls.append(argv)
        if argv[1:3] == ["run", "list"]:
            return json.dumps(runs)
        if argv[1:3] == ["run", "view"]:
            return json.dumps((jobs or {}).get(argv[3], {"jobs": []}))
        if argv[1:3] == ["pr", "checks"]:
            return json.dumps(checks or [])
        raise AssertionError(argv)

    tool.calls = calls
    return tool


# ---------------------------------------------------------------- #243: waiting for approval, or expired

def test_runs_waiting_for_approval_are_not_passed():
    # PR 7089: a first-time contributor's six workflows wait for a maintainer; only the labeler ran.
    found = forge.parse_gh_runs(json.dumps(RUNS["7089"]), head_of("7089"))
    assert found["state"] == "approval" and not found.get("expired")
    assert render._ci(found, "en")["text"] == "CI waiting for approval"
    assert render._ci(found, "ar")["text"] != render._ci(found, "en")["text"]
    # PR 7087: a bot-made backport, every run waiting.
    assert forge.parse_gh_runs(json.dumps(RUNS["7087"]), head_of("7087"))["state"] == "approval"


def test_runs_expired_waiting_for_approval_are_not_failed(tmp_path, monkeypatch):
    # PR 6994 at a detached HEAD: GitHub marked the never-approved runs failed after 30 days, with no jobs.
    info = info_for(tmp_path, "6994")
    info["branch"] = info["head"][:8]
    tool = fake_gh(RUNS["6994"])
    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info, None)
    assert (found["state"], found.get("expired")) == ("approval", True)
    assert render._ci(found, "en")["text"] == "CI not run: approval expired"
    assert len([argv for argv in tool.calls if argv[1:3] == ["run", "view"]]) == 1, "one look is enough"
    # The same old runs with jobs that really failed stay failed.
    jobs = {str(r["databaseId"]): {"jobs": [{"name": "test", "conclusion": "failure"}]} for r in RUNS["6994"]}
    monkeypatch.setattr(forge, "run_tool", fake_gh(RUNS["6994"], jobs=jobs))
    assert forge.fetch_ci(info, None)["state"] == "failed"


def test_a_pr_whose_only_check_is_the_labeler_asks_the_run_list(tmp_path, monkeypatch):
    # `gh pr checks 7089` lists only the pull_request_target labeler: not a reason to say passed.
    tool = fake_gh(RUNS["7089"], CHECKS["7089"])
    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info_for(tmp_path, "7089"), {"number": 7089})
    assert found["state"] == "approval"
    assert tool.calls[1][1:3] == ["run", "list"]
    tool = fake_gh(RUNS["6994"], CHECKS["6994"])
    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info_for(tmp_path, "6994"), {"number": 6994})
    assert (found["state"], found.get("expired")) == ("approval", True)


def test_a_pr_with_its_own_passing_checks_costs_no_extra_call(tmp_path, monkeypatch):
    # PR 6926: every workflow ran; `gh pr checks` alone answers.
    tool = fake_gh([], CHECKS["6926"])
    monkeypatch.setattr(forge, "run_tool", tool)
    assert forge.fetch_ci(info_for(tmp_path, "6926"), {"number": 6926})["state"] == "passed"
    assert len(tool.calls) == 1


# ---------------------------------------------------------------- #247: two workflows named ci

def _ci_running(now: float) -> list:
    """PR 6957's runs with its `ci` run (workflow 40370) going for two minutes, the rest finished."""
    runs = [dict(r, workflowDatabaseId=40370 if r["name"] == "ci" else 1) for r in RUNS["6957"]]
    for r in runs:
        if r["name"] == "ci":
            r.update(status="in_progress", conclusion="", startedAt=_iso(now - 120), updatedAt=_iso(now))
    return runs


def _iso(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def test_time_left_asks_for_the_workflow_by_id(tmp_path, monkeypatch):
    # fastify has two workflows named `ci`: `gh run list --workflow=ci` fails ("not a unique workflow").
    now = 1_791_367_380.0
    monkeypatch.setattr(forge.time, "time", lambda: now)
    calls = []

    def tool(argv, cwd, accept_codes=(0,)):
        calls.append(argv)
        if "--workflow=ci" in argv:
            raise forge.Off("off_error", "gh")
        if any(a.startswith("--workflow=") for a in argv):
            return json.dumps([{"name": "ci", "status": "completed", "conclusion": "success",
                                "startedAt": _iso(now - 9000), "updatedAt": _iso(now - 9000 + 326)}])
        return json.dumps(_ci_running(now))

    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info_for(tmp_path, "6957"), None)
    assert (found["state"], found["elapsed"], found["eta"]) == ("running", 120, 206)
    assert "--workflow=40370" in calls[-1]


def test_a_failed_time_left_lookup_keeps_ci_running(tmp_path, monkeypatch):
    now = 1_791_367_380.0
    monkeypatch.setattr(forge.time, "time", lambda: now)

    def tool(argv, cwd, accept_codes=(0,)):
        if any(a.startswith("--workflow=") for a in argv):
            raise forge.Off("off_error", "gh")
        runs = _ci_running(now)
        for r in runs:
            del r["workflowDatabaseId"]  # an older gh: the lookup goes by name, and fails
        return json.dumps(runs)

    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info_for(tmp_path, "6957"), None)
    assert (found["state"], found["elapsed"], found["eta"]) == ("running", 120, None)
    assert render._ci(found, "en")["text"] == "CI running 2m"


# ---------------------------------------------------------------- #245: a newer run of the same workflow

def test_a_rerun_of_the_same_workflow_supersedes_the_old_one():
    # PR 6926 and 6833: the title was edited and `pull request title check` re-ran green at the same commit.
    for pr in ("6926", "6833"):
        assert forge.parse_gh_runs(json.dumps(RUNS[pr]), head_of(pr))["state"] == "passed", pr
    # PR 6571: both title check runs failed: still failed, named once.
    found = forge.parse_gh_runs(json.dumps(RUNS["6571"]), head_of("6571"))
    assert found["state"] == "failed"
    assert found["failed"] == ["pull request title check", "Internal Links Check"]


# ---------------------------------------------------------------- #244: runs that are not the commit's CI

def test_schedule_and_dynamic_runs_are_not_the_commits_ci():
    # main 3 behind at 19d5be0d: monthly schedule jobs failed at it, its push CI is green.
    assert forge.parse_gh_runs(json.dumps(RUNS["runs-origin_main_3"]), head_of("runs-origin_main_3"))[
        "state"] == "passed"
    # PR 6699: only the labeler and a Copilot code review (dynamic) ran: no CI.
    assert forge.parse_gh_runs(json.dumps(RUNS["6699"]), head_of("6699"))["state"] == "none"


def test_the_post_merge_backport_is_not_the_commits_ci(tmp_path, monkeypatch):
    # dependabot PR 6917: ci failed in its automerge job; the pull_request_target Backport is not CI.
    found = forge.parse_gh_runs(json.dumps(RUNS["6917"]), head_of("6917"))
    assert found["failed"] == ["ci"]
    jobs = {"31110527305": {"jobs": [{"name": "automerge", "conclusion": "failure"}]}}
    info = info_for(tmp_path, "6917")
    info["branch"] = info["head"][:8]
    monkeypatch.setattr(forge, "run_tool", fake_gh(RUNS["6917"], jobs=jobs))
    assert render._ci(forge.fetch_ci(info, None), "en")["text"] == "CI failed: ci/automerge"


def test_a_labeler_alone_is_no_ci(tmp_path, monkeypatch):
    # PR 6518 (docs fork): `gh pr checks` lists only the pull_request_target labeler.
    assert forge.parse_gh_checks(json.dumps(CHECKS["6518"]))["state"] == "none"
    monkeypatch.setattr(forge, "run_tool", fake_gh(RUNS["6518"], CHECKS["6518"]))
    found = forge.fetch_ci(info_for(tmp_path, "6518"), {"number": 6518})
    assert render._ci(found, "en")["text"] == "no CI yet"
    monkeypatch.setattr(forge, "run_tool", fake_gh(RUNS["6699"], CHECKS["6699"]))
    assert forge.fetch_ci(info_for(tmp_path, "6699"), {"number": 6699})["state"] == "none"


# ---------------------------------------------------------------- #246: jobs allowed to fail

def test_jobs_allowed_to_fail_in_a_green_run_are_not_failures(tmp_path, monkeypatch):
    # PR 6381: `ci Alternative Runtimes` has continue-on-error on test-unit; its run ended success.
    tool = fake_gh(RUNS["6381"], CHECKS["6381"])
    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info_for(tmp_path, "6381"), {"number": 6381})
    assert (found["state"], found["failed"]) == ("cancelled", [])
    assert f"--commit={head_of('6381')}" in tool.calls[1]
    assert len(found["allowed"]) == 3
    # PR 6957 and 7060: ci really failed (coverage); the allowed jobs are not listed next to it.
    for pr in ("6957", "7060"):
        monkeypatch.setattr(forge, "run_tool", fake_gh(RUNS[pr], CHECKS[pr]))
        found = forge.fetch_ci(info_for(tmp_path, pr), {"number": int(pr)})
        assert found["state"] == "failed" and found["workflows"] == ["ci"], pr
        assert all(job.startswith("ci/coverage-") for job in found["failed"]), pr
    text = render.sections_text(render.detail({"git": {"branch": "x"}, "ci": found}, "en"))
    assert "allowed to fail: ci Alternative Runtimes/test-unit" in text


def test_failed_checks_cost_one_run_list_call(tmp_path, monkeypatch):
    # PR 6957 checks without a run list answer (gh error): the failures are shown as before.
    def tool(argv, cwd, accept_codes=(0,)):
        if argv[1:3] == ["run", "list"]:
            raise forge.Off("off_error", "gh")
        return json.dumps(CHECKS["6957"])

    monkeypatch.setattr(forge, "run_tool", tool)
    found = forge.fetch_ci(info_for(tmp_path, "6957"), {"number": 6957})
    assert found["state"] == "failed" and len(found["failed"]) == 5
