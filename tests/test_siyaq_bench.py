"""The siyaq relevance benchmark (#452): no prompt siyaq got right may go wrong, and precision may not drop
below the baseline. benchmarks/siyaq/bench.py prints the full report."""
from __future__ import annotations

import importlib.util
import json

import pytest
from conftest import PLUGINS

BENCH_DIR = PLUGINS.parent / "benchmarks" / "siyaq"
spec = importlib.util.spec_from_file_location("siyaq_bench", BENCH_DIR / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.fixture(scope="module")
def report():
    return bench.run()  # also fails if a label names a section the corpus doesn't have


def test_no_prompt_the_baseline_got_right_is_now_wrong(report):
    lost = bench.regressions(report, json.loads(bench.BASELINE.read_text(encoding="utf-8")))
    assert not lost, "siyaq got these right before and gets them wrong now:\n" + "\n".join(lost)


def test_the_set_has_100_prompts_and_a_quarter_need_nothing(report):
    assert report["prompts"] == 100 and report["silent"] == 25
    assert report["sources"] == 30


def test_a_lost_prompt_and_a_lower_precision_are_reported(report):
    right = next(r for r in report["rows"] if r["right"])
    wrong = {**report, "rows": [{**right, "right": False}], "precision": 0.0}
    lost = bench.regressions(wrong, {"right": [right["prompt"]], "precision": 0.5})
    assert any(right["prompt"] in line for line in lost) and any("precision dropped" in x for x in lost)
    assert bench.regressions(report, {}) == []


def test_a_label_must_name_a_real_section():
    entries = [{"id": "a", "source": "README.md", "title": "Nexika > Installing"}]
    assert bench.resolve("README.md :: Installing", entries) == ["a"]
    assert bench.resolve("README.md :: Install", entries) == []
    assert bench.resolve("docs/README.md :: Installing", entries) == []
