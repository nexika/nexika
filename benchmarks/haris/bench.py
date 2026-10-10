#!/usr/bin/env python3
"""haris benchmark: how often it stops real harm, and how often it gets in the way (#346).

    python3 benchmarks/haris/bench.py                  the report, per profile, as Markdown
    python3 benchmarks/haris/bench.py --json           the same as JSON
    python3 benchmarks/haris/bench.py --check          exit 1 if a harmful case is missed that the
                                                       baseline stopped (CI runs this as a test)
    python3 benchmarks/haris/bench.py --save-baseline  record today's results as the baseline

The cases are tests/haris_corpus.tsv (labelled by its expected verdict; the kind is the section it sits
in) and cases.tsv here (real commands from the agent benchmark and the trial, and prompt-injected ones).
Every case is only parsed and judged, in a throwaway home and project, never run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CASES = HERE / "cases.tsv"
BASELINE = HERE / "baseline.json"
PROFILES = ("relaxed", "standard", "strict")
STOPPED, LET_THROUGH = {"ask", "deny"}, {"allow", "pass"}
sys.path.insert(0, str(REPO / "tests"))

import haris_world  # noqa: E402  (puts haris on sys.path)

from haris import policy  # noqa: E402  # isort: skip


def case_id(tool: str, value: str) -> str:
    return hashlib.sha1(f"{tool}\t{value}".encode()).hexdigest()[:12]


def load_cases() -> list[dict]:
    """Every case as {id, set (harmful or ordinary), kind, source, tool, value}. Values keep their
    {PROJECT} placeholder here; it is filled in once the world exists."""
    out = []
    for n, expected, tool, value, section in haris_world.corpus_lines():
        kind = section.split(": ", 1)[1] if section.startswith(("dangerous: ", "ordinary: ")) else section
        out.append({"set": "harmful" if expected in STOPPED else "ordinary", "kind": kind,
                    "source": f"tests/haris_corpus.tsv:{n}", "tool": tool, "value": value})
    kind = ""
    for n, line in enumerate(CASES.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("# ---"):
            kind = line.lstrip("# -").strip()
        if not line.strip() or line.startswith("#"):
            continue
        label, _, rest = line.partition("\t")
        if label not in ("harmful", "ordinary"):
            raise ValueError(f"cases.tsv:{n}: the label must be harmful or ordinary, not {label!r}")
        tool, value = "Bash", rest
        if rest.startswith("@"):
            tool, _, value = rest[1:].partition("\t")
        value = value.replace("↵", "\n").replace("{PLUGIN}", str(haris_world.HARIS_ROOT))
        out.append({"set": label, "kind": kind, "source": f"benchmarks/haris/cases.tsv:{n}", "tool": tool,
                    "value": value})
    for c in out:
        c["id"] = case_id(c["tool"], c["value"])
    return out


@contextmanager
def throwaway_world():
    """A home and project in a temporary folder, with every Nexika data folder inside it."""
    keys = ("HOME", "HARIS_HOME", "NEXIKA_HOME", "NEXIKA_STATUS_HOME", "HARIS", "NEXIKA_BACKGROUND")
    saved, cwd = {k: os.environ.get(k) for k in keys}, os.getcwd()
    with tempfile.TemporaryDirectory(prefix="haris-bench-") as tmp:
        base = Path(tmp)
        os.environ.update(HOME=str(base / "home"), HARIS_HOME=str(base / "home/.claude/nexika/haris"),
                          NEXIKA_HOME=str(base / "home/.claude/nexika"),
                          NEXIKA_STATUS_HOME=str(base / "status"))
        os.environ.pop("HARIS", None)
        os.environ.pop("NEXIKA_BACKGROUND", None)
        try:
            home, project = haris_world.build_world(base)
            os.chdir(project)
            yield home, project
        finally:
            os.chdir(cwd)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def run(profiles=PROFILES) -> dict:
    """Judge every case under each profile: who was stopped, who was let through, and how fast."""
    cases = load_cases()
    report = {"cases": len(cases), "profiles": {}}
    with throwaway_world() as (home, project):
        base_cfg = policy.effective_config(str(project))
        for profile in profiles:
            cfg = dict(base_cfg, profile=profile)
            sets = {s: {"total": 0, "stopped": 0, "by_kind": {}, "cases": []}
                    for s in ("harmful", "ordinary")}
            times = []
            for c in cases:
                value = haris_world.home_path(c["tool"], c["value"].replace("{PROJECT}", str(project)), home)
                start = time.perf_counter()
                d = haris_world.decide(project, c["tool"], value, cfg)
                times.append(time.perf_counter() - start)
                stopped = d.verdict in STOPPED
                s = sets[c["set"]]
                kind = s["by_kind"].setdefault(c["kind"], {"total": 0, "stopped": 0})
                s["total"] += 1
                kind["total"] += 1
                if stopped:
                    s["stopped"] += 1
                    kind["stopped"] += 1
                # the harmful cases let through and the ordinary ones stopped: what a reader checks
                if stopped == (c["set"] == "ordinary"):
                    s["cases"].append({"id": c["id"], "source": c["source"], "kind": c["kind"],
                                       "verdict": d.verdict, "class": d.cls, "value": preview(c["value"])})
            times.sort()
            report["profiles"][profile] = {
                "recall": ratio(sets["harmful"]["stopped"], sets["harmful"]["total"]),
                "false_alarms": ratio(sets["ordinary"]["stopped"], sets["ordinary"]["total"]),
                "harmful": sets["harmful"], "ordinary": sets["ordinary"],
                "ms": {"median": round(statistics.median(times) * 1000, 2),
                       "p95": round(times[int(len(times) * 0.95)] * 1000, 2),
                       "max": round(times[-1] * 1000, 2)},
            }
    return report


def ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def preview(value: str, width: int = 100) -> str:
    one = value.replace("\n", "↵")
    return one if len(one) <= width else one[:width - 1] + "…"


def regressions(report: dict, baseline: dict) -> list[str]:
    """Harmful cases the baseline stopped that are now let through, per profile. Recall may never drop,
    whatever a change gains on false alarms (#346). A case the baseline does not know is new: it is
    reported, not held against the change."""
    out = []
    for profile, result in report["profiles"].items():
        stopped = set(baseline.get("stopped", {}).get(profile, []))
        for c in result["harmful"]["cases"]:
            if c["id"] in stopped:
                out.append(f"{profile}: {c['source']} [{c['kind']}] now {c['verdict']}: {c['value']}")
    return out


def to_baseline(report: dict) -> dict:
    """The ratios for the report, and the harmful cases each profile stopped for the guardrail."""
    harmful = [c for c in load_cases() if c["set"] == "harmful"]
    out = {"cases": report["cases"],
           "recall": {p: r["recall"] for p, r in report["profiles"].items()},
           "false_alarms": {p: r["false_alarms"] for p, r in report["profiles"].items()},
           "stopped": {}}
    for p, r in report["profiles"].items():
        missed = {c["id"] for c in r["harmful"]["cases"]}
        out["stopped"][p] = sorted({c["id"] for c in harmful} - missed)
    return out


def markdown(report: dict, baseline: dict | None = None) -> str:
    profiles = report["profiles"]
    lines = [f"# haris benchmark ({report['cases']} cases)", "",
             "| | " + " | ".join(profiles) + " |", "|---|" + "---|" * len(profiles)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(r, p) for p, r in profiles.items()) + " |")

    def was(key, p):
        old = (baseline or {}).get(key, {}).get(p)
        return f" (was {old:.1%})" if old is not None else ""

    row("Harmful stopped (recall)", lambda r, p: f"{r['harmful']['stopped']}/{r['harmful']['total']} = "
                                                 f"{r['recall']:.1%}{was('recall', p)}")
    row("Ordinary stopped (false alarms)",
        lambda r, p: f"{r['ordinary']['stopped']}/{r['ordinary']['total']} = "
                     f"{r['false_alarms']:.1%}{was('false_alarms', p)}")
    row("Decision time, median / p95 / max", lambda r, p: f"{r['ms']['median']} / {r['ms']['p95']} / "
                                                          f"{r['ms']['max']} ms")
    for title, key, word in (("Recall by kind (harmful cases stopped)", "harmful", "stopped"),
                             ("False alarms by kind (ordinary cases stopped)", "ordinary", "stopped")):
        kinds = sorted({k for r in profiles.values() for k in r[key]["by_kind"]})
        lines += ["", f"## {title}", "", "| Kind | " + " | ".join(profiles) + " |",
                  "|---|" + "---|" * len(profiles)]
        for k in kinds:
            cells = []
            for r in profiles.values():
                v = r[key]["by_kind"].get(k, {"total": 0, word: 0})
                cells.append(f"{v[word]}/{v['total']}")
            lines.append(f"| {k} | " + " | ".join(cells) + " |")
    for p, r in profiles.items():
        for title, key in (("Harmful let through", "harmful"), ("Ordinary stopped", "ordinary")):
            if r[key]["cases"]:
                lines += ["", f"## {title}, {p}", ""]
                lines += [f"- `{c['verdict']}` {c['source']} [{c['kind']}]: `{c['value']}`"
                          for c in r[key]["cases"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the results as JSON")
    ap.add_argument("--check", action="store_true", help="exit 1 if recall dropped below the baseline")
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
            print("\nharis now lets through harmful cases it used to stop:\n" + "\n".join(lost),
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
