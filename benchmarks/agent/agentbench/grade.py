"""Grade the kept diffs with the official SWE-bench harness, in fresh containers.

The harness applies the diff, then the hidden test patch, and runs the task's tests:
FAIL_TO_PASS tests decide "resolved", PASS_TO_PASS tests that fail are regressions.
"""

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

DATASET = "SWE-bench/SWE-bench_Verified"


def model_label(pilot, arm, run):
    """The harness names its docker containers after this label, and docker allows only
    [a-zA-Z0-9_.-]: "haris+barq" becomes "haris-barq"."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", f"{pilot}__{arm}__r{run}")


def predictions(metas, diffs, pilot):
    """Group predictions by (arm, run): the harness grades one prediction per task per file."""
    groups = defaultdict(list)
    for meta in metas:
        key = (meta["arm"], meta["run"])
        groups[key].append({
            "instance_id": meta["instance_id"],
            "model_name_or_path": model_label(pilot, *key),
            "model_patch": diffs[(meta["instance_id"], meta["arm"], meta["run"])],
        })
    return dict(groups)


def command(python, preds_path, ids, run_id, workers, test_timeout=1800):
    return [python, "-m", "swebench.harness.run_evaluation", "--dataset_name", DATASET,
            "--predictions_path", str(preds_path), "--instance_ids", *ids,
            "--run_id", run_id, "--max_workers", str(workers), "--timeout", str(test_timeout)]


def report_path(grading_dir, run_id, label, instance_id):
    return Path(grading_dir) / "logs" / "run_evaluation" / run_id / label / instance_id / "report.json"


def parse_report(data, instance_id):
    """Plain numbers from one report.json. A missing report means an empty diff or a harness
    failure; both count as not resolved."""
    if not data or instance_id not in data:
        return {"graded": False, "applied": False, "resolved": False, "f2p_pass": 0, "f2p_fail": 0,
                "p2p_pass": 0, "p2p_fail": 0, "regression": False, "infra_failure": False}
    entry = data[instance_id]
    status = entry.get("tests_status") or {}
    f2p, p2p = status.get("FAIL_TO_PASS") or {}, status.get("PASS_TO_PASS") or {}
    p2p_fail = len(p2p.get("failure") or [])
    return {
        "graded": True,
        "applied": bool(entry.get("patch_successfully_applied")),
        "resolved": bool(entry.get("resolved")),
        "f2p_pass": len(f2p.get("success") or []), "f2p_fail": len(f2p.get("failure") or []),
        "p2p_pass": len(p2p.get("success") or []), "p2p_fail": p2p_fail,
        "regression": p2p_fail > 0,
        "infra_failure": bool(entry.get("infra_failure")),
    }


def run(groups, grading_dir, pilot, python, workers, test_timeout=1800, sh=subprocess.run):
    """Write one predictions file per (arm, run), run the harness on it, read every report."""
    grading_dir = Path(grading_dir)
    grading_dir.mkdir(parents=True, exist_ok=True)
    grades = {}
    for (arm, run_n), preds in sorted(groups.items()):
        label = model_label(pilot, arm, run_n)
        path = grading_dir / f"{label}.jsonl"
        path.write_text("".join(json.dumps(p) + "\n" for p in preds))
        nonempty = [p["instance_id"] for p in preds if p["model_patch"].strip()]
        if nonempty:
            sh(command(python, path, nonempty, label, workers, test_timeout), cwd=grading_dir, check=False)
        for p in preds:
            rp = report_path(grading_dir, label, label, p["instance_id"])
            data = json.loads(rp.read_text()) if rp.exists() else None
            grades[(p["instance_id"], arm, run_n)] = parse_report(data, p["instance_id"])
    return grades


def validate(ids, grading_dir, python, workers, test_timeout=1800, sh=subprocess.run):
    """Grade the gold patches: a task whose own fix is not graded resolved cannot grade the arms
    either (a flaky test, a network test, a broken image). No model calls."""
    grading_dir = Path(grading_dir)
    grading_dir.mkdir(parents=True, exist_ok=True)
    sh(command(python, "gold", ids, "gold-check", workers, test_timeout), cwd=grading_dir, check=False)
    out = {}
    for instance_id in ids:
        rp = report_path(grading_dir, "gold-check", "gold", instance_id)
        out[instance_id] = parse_report(json.loads(rp.read_text()) if rp.exists() else None, instance_id)
    return out
