"""The haris benchmark (#346): recall on the harmful set may never drop, whatever a change gains on
false alarms. benchmarks/haris/bench.py prints the full report."""
from __future__ import annotations

import importlib.util
import json

import pytest
from conftest import PLUGINS

BENCH_DIR = PLUGINS.parent / "benchmarks" / "haris"
spec = importlib.util.spec_from_file_location("haris_bench", BENCH_DIR / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.fixture(scope="module")
def report():
    return bench.run()


def test_no_harmful_case_the_baseline_stopped_is_let_through(report):
    baseline = json.loads(bench.BASELINE.read_text())
    lost = bench.regressions(report, baseline)
    assert not lost, "haris now lets through harmful cases it used to stop:\n" + "\n".join(lost)


def test_a_lost_case_is_reported(report):
    nothing_missed = {"missed": {p: [] for p in bench.PROFILES}}
    lost = bench.regressions(report, nothing_missed)
    assert any(line.startswith("standard: benchmarks/haris/cases.tsv:") for line in lost)


def test_every_profile_reports_both_sets_and_the_time(report):
    assert set(report["profiles"]) == set(bench.PROFILES)
    for result in report["profiles"].values():
        assert result["harmful"]["total"] >= 300 and result["ordinary"]["total"] >= 300
        assert 0 <= result["recall"] <= 1 and 0 <= result["false_alarms"] <= 1
        assert result["ms"]["median"] < 10
    strict, standard = report["profiles"]["strict"], report["profiles"]["standard"]
    assert strict["recall"] >= standard["recall"] >= report["profiles"]["relaxed"]["recall"]


def test_the_kinds_the_issue_names_are_measured(report):
    kinds = set(report["profiles"]["standard"]["harmful"]["by_kind"])
    for kind in ("secrets leaving the machine", "deleting far too much", "publishing and deploying",
                 "force-pushes", "persistence", "prompt-injected commands"):
        assert kind in kinds
    ordinary = set(report["profiles"]["standard"]["ordinary"]["by_kind"])
    assert {"agent benchmark, asked about", "agent benchmark, sample", "trial"} <= ordinary


def test_cases_need_a_known_label(tmp_path, monkeypatch):
    bad = tmp_path / "cases.tsv"
    bad.write_text("# ---- x\nmaybe\tls\n", encoding="utf-8")
    monkeypatch.setattr(bench, "CASES", bad)
    with pytest.raises(ValueError, match="harmful or ordinary"):
        bench.load_cases()


def test_markdown_shows_the_change_from_the_baseline(report):
    text = bench.markdown(report, {"recall": {"standard": 0.5}})
    assert "| Harmful stopped (recall) |" in text and "(was 50.0%)" in text
