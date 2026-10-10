#!/usr/bin/env python3
"""tabib benchmark: does it name the right failure and the right kind on real CI failures (#347)?

    python3 benchmarks/tabib/bench.py                  the report as Markdown
    python3 benchmarks/tabib/bench.py --json           the same as JSON
    python3 benchmarks/tabib/bench.py --check          exit 1 if a case the baseline got right is now wrong
                                                       (CI runs this as a test)
    python3 benchmarks/tabib/bench.py --save-baseline  record today's results as the baseline

Each case is a real failed CI run of a public project: the log tabib reads (an excerpt, redacted), the
run's jobs, and the expected answer (cases/<project>.json). tabib's own triage runs on it offline: GitHub
is replaced by the stored run, nothing is fetched, no code is run and no model is called.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CASES = HERE / "cases"
BASELINE = HERE / "baseline.json"
KINDS = ("code", "matrix", "flaky", "infra", "setup", "dependency", "unknown")
# Kinds that mean "the project's code or its pins are wrong: someone has to change something".
REAL = {"code", "matrix", "dependency"}
FIELDS = ("test", "file", "line", "message")
sys.path.insert(0, str(REPO / "plugins" / "tabib"))

from tabib import compare, diagnosis, forge  # noqa: E402


def load_cases() -> list[dict]:
    """Every run of every cases/<project>.json, with its project and the path of its log."""
    out = []
    for path in sorted(CASES.glob("*.json")):
        project = json.loads(path.read_text(encoding="utf-8"))
        for run in project["runs"]:
            expected = run.get("expected") or {}
            bad = [k for k in expected.get("kind") or [] if k not in KINDS]
            if not expected.get("kind") or bad:
                raise ValueError(f"{path.name}: run {run.get('id')}: the expected kind must be one of "
                                 f"{', '.join(KINDS)}, not {bad or 'nothing'}")
            out.append({**run, "project": project["project"], "set": project.get("set", "trial"),
                        "source": f"{path.name}:{run['id']}"})
    return out


def read_log(case: dict) -> str | None:
    return (HERE / case["log"]).read_text(encoding="utf-8") if case.get("log") else None


def as_run(case: dict) -> dict:
    """The run as tabib's forge layer returns it from GitHub."""
    return {"provider": "github", "id": int(case["id"]),
            "url": f"https://github.com/{case['project']}/actions/runs/{int(case['id'])}",
            "workflow": case.get("workflow", ""), "sha": case.get("sha", ""),
            "branch": case.get("branch", ""),
            "event": case.get("event", ""), "attempt": 1, "number": 1, "created": case.get("created", ""),
            "updated": case.get("created", ""), "conclusion": "failure", "status": "completed",
            "jobs": [{"id": None, "name": j["name"], "conclusion": j["conclusion"], "failed_step": ""}
                     for j in case.get("jobs") or []]}


@contextmanager
def offline(case: dict, log: str | None):
    """tabib's GitHub calls answered from the stored case, its data folders in a temporary folder."""
    github = case.get("github") or {}
    own = set(case.get("own_modules") or [])
    run = as_run(case)

    def failed_log(info, r, attempt=0):
        if log is None:
            raise forge.Off("gh failed: failed to get run log: log not found")
        return log

    patches = {
        (forge, "find_run"): lambda info, run_id=None: run,
        (forge, "failed_log"): failed_log,
        (forge, "from_fork"): lambda info, r: github.get("from_fork"),
        (forge, "history"): lambda info, r: {"same_commit_passed": github.get("same_commit_passed"),
                                             "last_green": None},
        (forge, "flaky_tests"): lambda info, r, failures: list(github.get("flaky_tests") or []),
        (forge, "base_failures"): lambda info, r: list(github.get("base_failures") or []),
        # Which missing module or crashing package is the project's own: answered from the project's
        # files at that commit when the case was collected (own_modules in the case).
        (compare, "own_modules"): lambda repo, sha, names: {n for n in names if n in own},
    }
    saved = {key: getattr(*key) for key in patches}
    keys = ("TABIB_HOME", "NEXIKA_HOME", "NEXIKA_STATUS_HOME")
    env = {k: os.environ.get(k) for k in keys}
    with tempfile.TemporaryDirectory(prefix="tabib-bench-") as tmp:
        base = Path(tmp).resolve()   # macOS keeps it under /var, a link to /private/var
        for k in keys:
            os.environ[k] = str(base / k.lower())
        for (module, name), fn in patches.items():
            setattr(module, name, fn)
        try:
            yield {"repo": str(base / "project"), "branch": case.get("branch", ""), "host": "github",
                   "default": "main", "head": ""}
        finally:
            for (module, name), fn in saved.items():
                setattr(module, name, fn)
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def diagnose(case: dict, log: str | None = None) -> tuple[dict, float]:
    """tabib's triage of the case (the no-AI part of a diagnosis), and the seconds it took."""
    log = read_log(case) if log is None else log
    with offline(case, log) as info:
        start = time.perf_counter()
        record = diagnosis.triage(info, int(case["id"]), refresh=True)
        took = time.perf_counter() - start
    return record, took


def same_name(found: str, wanted: str) -> bool:
    """A test or path named the same, allowing one to carry a prefix the other does not:
    'tests/test_x.py::test_y' and 'test_y', 'src/black/comments.py' and 'black/comments.py'."""
    found, wanted = (found or "").strip(), (wanted or "").strip()
    if not found or not wanted:
        return False
    if found == wanted:
        return True
    for sep in ("::", "/", " > ", " › ", " "):
        if found.endswith(sep + wanted) or wanted.endswith(sep + found):
            return True
    return False


def match(failure: dict, wanted: dict) -> dict:
    """Which of the expected test, file and line this failure gets right."""
    out = {}
    if wanted.get("test"):
        out["test"] = same_name(failure.get("test"), wanted["test"])
    if wanted.get("file"):
        out["file"] = same_name(failure.get("file"), wanted["file"])
    if "line" in wanted:   # 0: the log names no line in that file, so tabib must name none (#362)
        out["line"] = int(failure.get("line") or 0) == int(wanted["line"] or 0)
    if wanted.get("message"):   # a check with no test or file: its own message
        out["message"] = wanted["message"].lower() in (failure.get("message") or "").lower()
    return out


def score_failures(record: dict, expected: list[dict]) -> dict:
    """For each expected failure, the best match among what tabib read; the case is right when every
    expected failure is found with its test, file and line (those that are labelled)."""
    found = record.get("failures") or []
    fields = {k: [0, 0] for k in FIELDS}
    missed = []
    for wanted in expected:
        best = max((match(f, wanted) for f in found), key=lambda m: (all(m.values()), sum(m.values())),
                   default={k: False for k in FIELDS if wanted.get(k)})
        for k, ok in best.items():
            fields[k][0] += ok
            fields[k][1] += 1
        if not best or not all(best.values()):
            missed.append(wanted)
    return {"right": not missed, "missed": missed, "fields": fields}


def text_of(record: dict) -> str:
    """Everything the triage says, where a cause can be named."""
    parts = [json.dumps(record.get("detail") or {}), *(record.get("evidence") or []),
             *(record.get("errors") or [])]
    for f in record.get("failures") or []:
        parts += [f.get("test") or "", f.get("file") or "", f.get("message") or ""]
    parts += [s.get("line") or "" for s in record.get("signals") or []]
    return "\n".join(parts).lower()


def score(case: dict, record: dict, took: float) -> dict:
    expected = case["expected"]
    kinds = expected["kind"]
    out = {"id": int(case["id"]), "source": case["source"], "project": case["project"], "set": case["set"],
           "expected": kinds, "kind": record["kind"], "kind_right": record["kind"] in kinds,
           "ms": round(took * 1000, 2), "failures": None, "cause": None}
    if expected.get("failures"):
        out["failures"] = score_failures(record, expected["failures"])
    # A run where nothing failed in the code (a runner, a setup step): naming a failure there is a mistake.
    out["none_expected"] = expected.get("failures") == []
    cause = expected.get("cause") or {}
    if cause.get("fix") and cause.get("points"):
        text = text_of(record)
        out["cause"] = {"hit": any(p.lower() in text for p in cause["points"]), "points": cause["points"]}
    out["named"] = [f"{f.get('test') or f.get('file')}" + (f":{f['line']}" if f.get("line") else "")
                    for f in (record.get("failures") or [])[:5]]
    return out


def costly(expected: str, got: str) -> str:
    """The mistakes that send someone the wrong way, with the name the report gives them."""
    if expected in REAL and got == "flaky":
        return "flaky for a real bug"
    if expected in REAL and got == "infra":
        return "infra for a real bug"
    if expected in ("infra", "flaky") and got in ("code", "matrix"):
        return "code for infrastructure" if expected == "infra" else "code for a flaky failure"
    return ""


def run() -> dict:
    """Diagnose and score every case."""
    rows = []
    for case in load_cases():
        record, took = diagnose(case)
        rows.append(score(case, record, took))
    return summarise(rows)


def ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def summarise(rows: list[dict]) -> dict:
    confusion: dict[str, Counter] = {}
    for r in rows:
        truth = r["kind"] if r["kind_right"] else r["expected"][0]
        confusion.setdefault(truth, Counter())[r["kind"]] += 1
    with_failures = [r for r in rows if r["failures"] is not None]
    fields = {k: [0, 0] for k in FIELDS}
    for r in with_failures:
        for k, (hit, total) in r["failures"]["fields"].items():
            fields[k][0] += hit
            fields[k][1] += total
    failures_right = sum(r["failures"]["right"] for r in with_failures)
    no_failures = [r for r in rows if r["none_expected"]]
    causes = [r for r in rows if r["cause"] is not None]
    times = sorted(r["ms"] for r in rows)

    def by(key):
        groups = {}
        for r in rows:
            g = groups.setdefault(r[key], dict.fromkeys(("cases", "kind_right", "failure_cases",
                                                          "failures_right"), 0))
            g["cases"] += 1
            g["kind_right"] += r["kind_right"]
            if r["failures"] is not None:
                g["failure_cases"] += 1
                g["failures_right"] += r["failures"]["right"]
        return groups
    return {
        "cases": len(rows),
        "kind": {"right": sum(r["kind_right"] for r in rows), "total": len(rows),
                 "accuracy": ratio(sum(r["kind_right"] for r in rows), len(rows)),
                 "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
                 "costly": [{**r, "mistake": costly(r["expected"][0], r["kind"])} for r in rows
                            if not r["kind_right"] and costly(r["expected"][0], r["kind"])]},
        "failures": {"right": failures_right, "total": len(with_failures),
                     "accuracy": ratio(failures_right, len(with_failures)),
                     "fields": {k: {"right": v[0], "total": v[1]} for k, v in fields.items()},
                     "named_without_failure": [r["source"] for r in no_failures if r["named"]],
                     "without_failure": len(no_failures)},
        "cause": {"hit": sum(r["cause"]["hit"] for r in causes), "total": len(causes)},
        "ms": {"median": round(statistics.median(times), 2) if times else 0,
               "p95": times[int(len(times) * 0.95)] if times else 0, "max": times[-1] if times else 0},
        "tokens": {"triage": 0, "diagnostician": "not measured offline"},
        "projects": by("project"),
        "sets": by("set"),
        "rows": rows,
    }


def to_baseline(report: dict) -> dict:
    rows = report["rows"]
    return {"cases": report["cases"],
            "kind_accuracy": report["kind"]["accuracy"], "failure_accuracy": report["failures"]["accuracy"],
            "kind_right": sorted(r["id"] for r in rows if r["kind_right"]),
            "failures_right": sorted(r["id"] for r in rows if r["failures"] and r["failures"]["right"])}


def regressions(report: dict, baseline: dict) -> list[str]:
    """Cases the baseline got right that are now wrong, by kind or by failure, and a drop in either
    accuracy. A case the baseline does not know is new: reported, not held against the change."""
    out = []
    kind_right, failures_right = set(baseline.get("kind_right", [])), set(baseline.get("failures_right", []))
    for r in report["rows"]:
        if r["id"] in kind_right and not r["kind_right"]:
            out.append(f"kind: {r['source']} expected {'/'.join(r['expected'])}, now {r['kind']}")
        if r["id"] in failures_right and r["failures"] and not r["failures"]["right"]:
            missed = ", ".join(json.dumps(m, sort_keys=True) for m in r["failures"]["missed"])
            out.append(f"failures: {r['source']} no longer finds {missed} (finds {r['named']})")
    for key, name in (("kind", "kind_accuracy"), ("failures", "failure_accuracy")):
        if name in baseline and report[key]["accuracy"] < baseline[name]:
            out.append(f"{name} dropped: {report[key]['accuracy']:.1%} < {baseline[name]:.1%}")
    return out


def pct(part: int, whole: int) -> str:
    return f"{part}/{whole} = {part / whole:.1%}" if whole else "0/0"


def markdown(report: dict, baseline: dict | None = None) -> str:
    k, f, c = report["kind"], report["failures"], report["cause"]

    def was(name):
        old = (baseline or {}).get(name)
        return f" (baseline {old:.1%})" if old is not None else ""

    lines = [f"# tabib benchmark ({report['cases']} failed CI runs)", "",
             "| | |", "|---|---|",
             f"| Kind right | {pct(k['right'], k['total'])}{was('kind_accuracy')} |",
             f"| Failures right (test, file and line) | {pct(f['right'], f['total'])}"
             f"{was('failure_accuracy')} |",
             *(f"| ... {name} right | {pct(v['right'], v['total'])} |" for name, v in f["fields"].items()
               if v["total"]),
             f"| Cause named, runs with a known fix | {pct(c['hit'], c['total'])} |",
             f"| Costly kind mistakes | {len(k['costly'])} |",
             f"| Time per triage, median / p95 / max | {report['ms']['median']} / {report['ms']['p95']} / "
             f"{report['ms']['max']} ms |",
             "| Tokens per triage | 0 (no model call); the diagnostician agent is not measured offline |",
             "", "## By project", "", "| Project | Set | Kind right | Failures right |", "|---|---|---|---|"]
    sets = {r["project"]: r["set"] for r in report["rows"]}
    for name, p in sorted(report["projects"].items(), key=lambda kv: (sets[kv[0]] != "trial", kv[0])):
        lines.append(f"| {name} | {sets[name]} | {pct(p['kind_right'], p['cases'])} | "
                     f"{pct(p['failures_right'], p['failure_cases'])} |")
    for name, p in sorted(report["sets"].items(), key=lambda kv: kv[0] != "trial"):
        lines.append(f"| **all {name}** | | {pct(p['kind_right'], p['cases'])} | "
                     f"{pct(p['failures_right'], p['failure_cases'])} |")
    lines += ["", "## Kinds: expected (rows) and what tabib said (columns)", "",
              "| expected \\ tabib | " + " | ".join(KINDS) + " |", "|---|" + "---|" * len(KINDS)]
    for truth in KINDS:
        row = k["confusion"].get(truth)
        if row:
            lines.append(f"| {truth} | " + " | ".join(str(row.get(g, "")) if row.get(g) else "·"
                                                       for g in KINDS) + " |")
    lines += ["", "## Costly mistakes", ""]
    lines += [f"- **{r['mistake']}**: {r['source']} expected {'/'.join(r['expected'])}, "
              f"tabib said {r['kind']}" for r in k["costly"]] or ["None."]
    wrong = [r for r in report["rows"] if not r["kind_right"]]
    if wrong:
        lines += ["", "## Wrong kind", ""]
        lines += [f"- {r['source']}: expected {'/'.join(r['expected'])}, tabib said {r['kind']}"
                  for r in wrong]
    missed = [r for r in report["rows"] if r["failures"] and not r["failures"]["right"]]
    if missed:
        lines += ["", "## Failures missed", ""]
        for r in missed:
            want = "; ".join(":".join(str(m[x]) for x in FIELDS if m.get(x))
                             for m in r["failures"]["missed"][:3])
            named = ", ".join(r["named"]) or "nothing"
            lines.append(f"- {r['source']}: expected {want}; tabib named {named}")
    if f["named_without_failure"]:
        lines += ["", "## Failures named where there are none", ""]
        lines += [f"- {s}" for s in f["named_without_failure"]]
    no_cause = [r for r in report["rows"] if r["cause"] and not r["cause"]["hit"]]
    if no_cause:
        lines += ["", "## Known fixes the triage does not point at", ""]
        lines += [f"- {r['source']}: {', '.join(r['cause']['points'])}" for r in no_cause]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the results as JSON")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if a case the baseline got right is now wrong")
    ap.add_argument("--save-baseline", action="store_true", help="record these results as the baseline")
    args = ap.parse_args(argv)
    report = run()
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    if args.save_baseline:
        BASELINE.write_text(json.dumps(to_baseline(report), indent=1) + "\n")
    print(json.dumps(report, indent=1) if args.json else markdown(report, baseline), end="")
    if args.check:
        lost = regressions(report, baseline or {})
        if lost:
            print("\ntabib got these right before and gets them wrong now:\n" + "\n".join(lost),
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
