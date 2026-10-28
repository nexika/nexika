"""The lawha benchmark scorer (benchmarks/score/score.mjs) reads each tool's run.json through
read-run.mjs; one damaged file must not stop the scoring of the others (#416). Re-scoring needs npm
and Playwright, so only the reading step is tested here, with node's own test runner."""
from __future__ import annotations

import shutil
import subprocess

import pytest
from conftest import PLUGINS

SCORE = PLUGINS.parent / "benchmarks" / "score"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_scorer_reads_past_a_damaged_run_json():
    done = subprocess.run(["node", "--test", str(SCORE / "read-run.test.mjs")],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
