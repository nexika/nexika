"""The tabib benchmark (#347): kind accuracy and failure accuracy on real failed CI runs may never drop
below the baseline, case by case. benchmarks/tabib/bench.py prints the full report."""
from __future__ import annotations

import importlib.util
import json

import pytest
from conftest import PLUGINS

BENCH_DIR = PLUGINS.parent / "benchmarks" / "tabib"
spec = importlib.util.spec_from_file_location("tabib_bench", BENCH_DIR / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
_spec = importlib.util.spec_from_file_location("nexika_secrets", PLUGINS.parent / "common" / "secrets.py")
common_secrets = importlib.util.module_from_spec(_spec)   # the shared one, not the standard library's
_spec.loader.exec_module(common_secrets)


@pytest.fixture(scope="module")
def report():
    return bench.run()


def test_no_case_the_baseline_got_right_is_now_wrong(report):
    baseline = json.loads(bench.BASELINE.read_text())
    lost = bench.regressions(report, baseline)
    assert not lost, "tabib got these right before and gets them wrong now:\n" + "\n".join(lost)


def test_a_lost_case_and_a_lower_accuracy_are_reported_and_a_new_case_is_not(report):
    every = [r["id"] for r in report["rows"]]
    wrong_kind = next(r for r in report["rows"] if not r["kind_right"])
    lost = bench.regressions(report, {"kind_right": every, "failures_right": every,
                                      "kind_accuracy": 1.0, "failure_accuracy": 1.0})
    assert any(line.startswith(f"kind: {wrong_kind['source']} ") for line in lost)
    assert any(line.startswith("kind_accuracy dropped") for line in lost)
    assert bench.regressions(report, {}) == []


def test_the_report_has_what_the_issue_asks_for(report):
    assert report["cases"] >= 150
    assert 0 < report["kind"]["accuracy"] <= 1 and 0 < report["failures"]["accuracy"] <= 1
    assert set(report["kind"]["confusion"]) <= set(bench.KINDS)
    assert {"trial", "held-out"} == set(report["sets"])
    assert report["cause"]["total"] >= 10
    assert report["tokens"] == {"triage": 0, "diagnostician": "not measured offline"}
    assert report["ms"]["median"] > 0
    for field in ("test", "file", "line"):
        assert report["failures"]["fields"][field]["total"] > 0


def test_every_case_is_labelled_and_its_log_is_stored_small_and_redacted():
    cases = bench.load_cases()
    assert len({c["id"] for c in cases}) == len(cases)
    total = 0
    for case in cases:
        assert case["label"].strip(), case["source"]
        assert isinstance(case["expected"]["failures"], list), case["source"]
        if not case["jobs"]:
            assert case["log"] is None, case["source"]   # a run with no jobs has no log
            continue
        path = BENCH_DIR / case["log"]
        text = path.read_text(encoding="utf-8")
        assert len(text) <= 200_000, f"{case['log']} is {len(text)} bytes"
        assert not common_secrets.has_secret(text), case["log"]
        total += len(text)
    assert total <= 3_500_000


def test_cases_need_a_known_kind(tmp_path, monkeypatch):
    (tmp_path / "x.json").write_text(json.dumps({"project": "a/b", "runs": [
        {"id": 1, "jobs": [], "log": None, "expected": {"kind": ["config"], "failures": []}}]}))
    monkeypatch.setattr(bench, "CASES", tmp_path)
    with pytest.raises(ValueError, match="expected kind must be one of"):
        bench.load_cases()


def test_the_diagnosis_runs_offline_and_puts_tabib_back(monkeypatch):
    """No GitHub call, no git, no model: forge's own command runner is never reached."""
    def refuse(*args, **kwargs):
        raise AssertionError(f"a command ran: {args}")

    monkeypatch.setattr(bench.forge, "run_tool", refuse)
    before = bench.forge.failed_log, bench.compare.own_modules
    case = next(c for c in bench.load_cases() if c["expected"]["failures"] and c["log"])
    record, took = bench.diagnose(case)
    assert record["failures"] and took > 0
    assert (bench.forge.failed_log, bench.compare.own_modules) == before


def test_a_failure_matches_by_test_file_line_and_message():
    found = {"failures": [{"test": "tests/test_x.py::test_y", "file": "tests/test_x.py", "line": 12,
                           "message": "AssertionError: 1 != 2"}]}
    assert bench.score_failures(found, [{"test": "test_y", "file": "tests/test_x.py", "line": 12}])["right"]
    assert bench.score_failures(found, [{"message": "assertionerror"}])["right"]
    missed = bench.score_failures(found, [{"file": "tests/test_x.py", "line": 13}])
    assert not missed["right"] and missed["fields"]["file"] == [1, 1] and missed["fields"]["line"] == [0, 1]
    assert not bench.score_failures({"failures": []}, [{"file": "a.py"}])["right"]


def test_the_costly_mistakes_are_named():
    assert bench.costly("code", "flaky") == "flaky for a real bug"
    assert bench.costly("infra", "code") == "code for infrastructure"
    assert bench.costly("setup", "code") == ""


def test_markdown_shows_the_baseline_and_the_confusion_table(report):
    text = bench.markdown(report, {"kind_accuracy": 0.5})
    assert "| Kind right |" in text and "(baseline 50.0%)" in text
    assert "## Kinds: expected (rows) and what tabib said (columns)" in text
    assert "## Costly mistakes" in text and "| **all held-out** |" in text


def test_a_temporary_folder_behind_a_link_changes_nothing(tmp_path, monkeypatch):
    """macOS's temporary folder is reached through a link (/var -> /private/var)."""
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "link"))
    monkeypatch.setattr(bench.tempfile, "tempdir", None)
    case = next(c for c in bench.load_cases() if c["log"])
    record, _ = bench.diagnose(case)
    assert record["kind"] in bench.KINDS


def _triage(source: str) -> dict:
    case = next(c for c in bench.load_cases() if c["source"] == source)
    return bench.diagnose(case)[0]


def test_npm_10_no_matching_version_is_a_dependency_failure():
    """express 35053857520 (#361): npm 10 prints 'npm error', not 'npm ERR!'."""
    record = _triage("express.json:35053857520")
    assert record["kind"] == "dependency"
    assert any("No matching version found for proxy-addr@^2.0.8" in e for e in record["evidence"])
    assert "npm error code ETARGET" in record["errors"]


def test_a_package_mirror_that_will_not_download_is_infra():
    """black 31070601941 (#361): yum could not download the epel mirror's metadata."""
    record = _triage("black.json:31070601941")
    assert (record["kind"], record["detail"]) == ("infra", {"signal": "download"})
    assert any("Failed to download metadata for repo 'epel'" in e for e in record["evidence"])


def test_a_setup_action_answered_with_an_html_page_is_infra():
    """fastify 30849839665 (#361): setup-nsolid's download site answered 403 with an HTML page."""
    record = _triage("fastify.json:30849839665")
    assert (record["kind"], record["detail"]) == ("infra", {"signal": "download"})
    assert any("<html>" in e for e in record["evidence"])


def test_a_link_checker_refused_by_a_known_site_is_setup():
    """fastify 32202758629 (#361): medium.com answers link checkers with 403; the fix allowed 403."""
    record = _triage("fastify.json:32202758629")
    assert record["kind"] == "setup"
    assert any("[403] https://medium.com/" in e for e in record["evidence"])


@pytest.mark.parametrize("run", ["30838060511", "30243111728", "30243111708", "30243109738"])
def test_an_input_the_action_does_not_know_is_quoted_for_setup(run):
    """black (#361): actions/setup-python 7.0.0 dropped the pip-install input, so nothing was installed."""
    record = _triage(f"black.json:{run}")
    assert record["kind"] == "setup"
    assert any("Unexpected input(s) 'pip-install'" in e for e in record["evidence"])
