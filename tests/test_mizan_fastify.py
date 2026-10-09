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
    assert f"--commit={head_of('7089')}" in tool.calls[1]
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
