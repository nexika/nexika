"""lawha and the other Nexika plugins: itqan's proof and mizan's band read lawha's checks safely."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import PLUGINS

sys.path.insert(0, str(PLUGINS / "itqan" / "scripts"))
import itqan_proof  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def homes(tmp_path, monkeypatch):
    status, lawha = tmp_path / "status", tmp_path / "lawha"
    monkeypatch.setenv("NEXIKA_STATUS_HOME", str(status))
    monkeypatch.setenv("LAWHA_HOME", str(lawha))
    return status, lawha


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "start")
    return root.resolve()


def lawha_record(homes, project: Path, *, verdict="fail", commit=None, inside=True, schema="nexika.lawha.check/1"):
    """What lawha's engine writes after a check: a record in its folder, pointed at by status/lawha.json."""
    status, lawha = homes
    folder = (lawha / "checks" / "abc") if inside else (project / ".lawha")
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / "latest.json"
    record.write_text(json.dumps({
        "schema": schema, "created": "2026-10-06T18:00:00", "project": str(project), "branch": "main",
        "commit": commit if commit is not None else git(project, "rev-parse", "--short", "HEAD"), "dirty": False,
        "url": "http://localhost:5173/pricing", "widths": [360, 390, 768, 1024, 1280, 1536],
        "themes": ["light", "dark"], "dirs": ["ltr", "rtl"], "verdict": verdict,
        "counts": {"fail": 2 if verdict == "fail" else 0, "warn": 1, "info": 0},
        "problems": [{"severity": "fail", "check": "layout.horizontal-scroll",
                      "message": "The page scrolls sideways: 900px wide in a 390px viewport.", "where": ["390px"]}],
        "report": str(project / ".lawha/runs/x/report.html"), "run": str(project / ".lawha/runs/x/run.json")}))
    status.mkdir(parents=True, exist_ok=True)
    pointer = {"schema": "nexika.lawha/1", "updated": 1, "checks": {str(project): str(record)}}
    (status / "lawha.json").write_text(json.dumps(pointer))
    return record


def test_itqan_proof_includes_lawhas_check_at_this_commit(homes, project):
    lawha_record(homes, project, verdict="fail")
    ui = itqan_proof.ui_check(project)
    assert ui["verdict"] == "fail" and ui["fail"] == 2 and ui["by"] == "lawha"
    assert ui["widths"] == [360, 390, 768, 1024, 1280, 1536] and ui["dirs"] == ["ltr", "rtl"]
    assert "scrolls sideways" in ui["problems"][0]
    lawha_record(homes, project, verdict="pass")
    assert itqan_proof.ui_check(project)["verdict"] == "pass"


@pytest.mark.parametrize("kind", ["outside lawha's folder", "another commit", "another schema"])
def test_itqan_ignores_checks_it_cannot_trust(homes, project, kind):
    if kind == "outside lawha's folder":
        lawha_record(homes, project, verdict="pass", inside=False)  # a file Claude could have written
    elif kind == "another commit":
        lawha_record(homes, project, verdict="pass", commit="0000000")
    else:
        lawha_record(homes, project, verdict="pass", schema="nexika.other/1")
    assert itqan_proof.ui_check(project) == {}


def test_a_failing_ui_check_fails_the_proof(homes, project):
    lawha_record(homes, project, verdict="fail")

    class Args:
        only, review, note, done, open, timeout = "tests", None, [], [], [], 30

    proof = itqan_proof.make(project, Args())
    assert proof["ui"]["verdict"] == "fail"
    assert proof["summary"]["checks_passed"] is False
    assert "pages on every screen (lawha): FAILED (2 to fix)" in itqan_proof.describe(proof)


def test_no_lawha_check_leaves_the_proof_as_before(homes, project):
    assert itqan_proof.ui_check(project) == {}
