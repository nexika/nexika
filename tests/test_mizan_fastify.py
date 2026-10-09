"""mizan on fastify/fastify (#52): real gh JSON, trimmed (fixtures/mizan_fastify.json)."""
from __future__ import annotations

import json
import sys
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
