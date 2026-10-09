#!/usr/bin/env python3
"""Claude Code alone against Claude Code with Nexika, on SWE-bench Verified tasks.

  bench.py select                     pick the tasks (writes pilot.json; no model calls)
  bench.py validate --python VENV/python   check every task grades its own gold fix as resolved
  bench.py run --model opus           run every task in both arms (paid model calls)
  bench.py grade --python VENV/python grade the diffs with the SWE-bench harness
  bench.py summary                    results.csv and the paired comparison

Results go to $AGENTBENCH_HOME (default ~/nexika-bench/<pilot>). See README.md.
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agentbench import grade, runner, summary, tasks  # noqa: E402

REPO = HERE.parent.parent
PILOT = HERE / "pilot.json"
QUOTAS = {tasks.EASY: 6, tasks.MEDIUM: 10, tasks.HARD: 4}


def home(pilot):
    return Path(os.environ.get("AGENTBENCH_HOME") or Path.home() / "nexika-bench" / pilot["name"])


def load_task_rows(base, ids):
    cache = base / "tasks.json"
    if not cache.exists():
        print("fetching SWE-bench Verified ...", file=sys.stderr)
        tasks.save_tasks(cache, tasks.fetch_rows())
    rows = {r["instance_id"]: r for r in tasks.load_tasks(cache)}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise SystemExit(f"not in the dataset: {', '.join(missing)}")
    return {i: rows[i] for i in ids}


def cmd_select(args):
    rows = tasks.fetch_rows()
    picked = tasks.select(rows, QUOTAS, args.seed, args.max_per_repo)
    pilot = {
        "name": args.name, "dataset": tasks.DATASET, "seed": args.seed,
        "quotas": QUOTAS, "max_per_repo": args.max_per_repo,
        "instance_ids": [r["instance_id"] for r in picked],
    }
    PILOT.write_text(json.dumps(pilot, indent=1) + "\n")
    tasks.save_tasks(home(pilot) / "tasks.json", rows)
    for r in picked:
        print(f"{r['difficulty']:>16}  {r['instance_id']}")
    print(f"wrote {PILOT}")


def _metas(base):
    metas, diffs = [], {}
    for meta_path in sorted((base / "runs").glob("*/meta.json")):
        meta = json.loads(meta_path.read_text())
        metas.append(meta)
        diffs[(meta["instance_id"], meta["arm"], meta["run"])] = (meta_path.parent / "diff.patch").read_text()
    return metas, diffs


def cmd_run(args):
    pilot = tasks.load_pilot(args.pilot)
    base = home(pilot)
    ids = args.only or pilot["instance_ids"]
    rows = load_task_rows(base, ids)
    order = runner.plan(ids, args.runs, pilot["seed"], tuple(args.arms.split(",")))
    sha = runner.git_sha(REPO, args.ref)
    if args.dry_run:
        for task, run, arm in order:
            print(f"{task} arm {arm} run {run}: {runner.image_name(task)}")
        print(" ".join(runner.claude_args("B", args.model, args.budget)))
        return
    scratch = runner.scratch()
    cfg = {
        "model": args.model, "budget": args.budget, "timeout": args.timeout, "nexika_sha": sha,
        "claude_bin": runner.claude_binary(), "claude_version": runner.claude_version(),
        "credentials": str(Path.home() / ".claude" / ".credentials.json"),
        "plugins_dir": str(runner.export_plugins(REPO, sha, scratch)),
    }
    for n, (task, run, arm) in enumerate(order, 1):
        out = base / "runs" / runner.run_name(task, arm, run)
        if (out / "meta.json").exists():
            continue
        print(f"[{n}/{len(order)}] {task} arm {arm} run {run}", file=sys.stderr, flush=True)
        try:
            meta = runner.run_one(rows[task], arm, run, cfg, out)
        except RuntimeError as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            continue
        flag = "" if meta["valid"] else f"  INVALID: {meta['invalid_reason']}"
        print(f"  {meta['result'] or 'no result'}  ${meta['cost_usd'] or 0:.2f}  {meta['wall_s']:.0f}s  "
              f"{meta['files_changed']} files  {meta['permission_denials']} denials{flag}", file=sys.stderr)


def cmd_grade(args):
    pilot = tasks.load_pilot(args.pilot)
    base = home(pilot)
    metas, diffs = _metas(base)
    groups = grade.predictions(metas, diffs, pilot["name"])
    grades = grade.run(groups, base / "grading", pilot["name"], args.python, args.workers, args.test_timeout)
    out = [{"instance_id": k[0], "arm": k[1], "run": k[2], **v} for k, v in sorted(grades.items())]
    (base / "grades.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"graded {len(out)} runs; resolved {sum(g['resolved'] for g in out)}")


def cmd_validate(args):
    pilot = tasks.load_pilot(args.pilot)
    ids = args.only or pilot["instance_ids"]
    results = grade.validate(ids, home(pilot) / "grading", args.python, args.workers, args.test_timeout)
    bad = [i for i, g in results.items() if not g["resolved"]]
    for instance_id, g in results.items():
        verdict = "ok" if g["resolved"] else "NOT RESOLVED by its own gold patch"
        print(f"{instance_id}: {verdict} (FAIL_TO_PASS {g['f2p_pass']}/{g['f2p_pass'] + g['f2p_fail']}, "
              f"PASS_TO_PASS failures {g['p2p_fail']})")
    if bad:
        raise SystemExit(f"{len(bad)} task(s) cannot be graded reliably: replace them before the run")


def cmd_summary(args):
    pilot = tasks.load_pilot(args.pilot)
    base = home(pilot)
    metas, _ = _metas(base)
    grades_path = base / "grades.json"
    graded = json.loads(grades_path.read_text()) if grades_path.exists() else []
    grades = {(g["instance_id"], g["arm"], g["run"]): g for g in graded}
    rows = summary.merge(metas, grades)
    summary.write_csv(rows, base / "results.csv")
    text = summary.markdown(rows, pilot["name"])
    (base / "summary.md").write_text(text)
    print(text)
    print(f"wrote {base / 'results.csv'} and {base / 'summary.md'}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pilot", default=str(PILOT), help="pilot file (default: pilot.json here)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("select", help="pick the tasks with a fixed seed")
    s.add_argument("--name", default="pilot-1")
    s.add_argument("--seed", type=int, default=333)
    s.add_argument("--max-per-repo", type=int, default=4)
    s.set_defaults(fn=cmd_select)

    r = sub.add_parser("run", help="run the tasks in both arms (paid)")
    r.add_argument("--model", required=True, help="the same model for both arms, e.g. opus or sonnet")
    r.add_argument("--budget", type=float, default=5.0, help="max USD per run (default 5)")
    r.add_argument("--timeout", type=int, default=2700, help="max seconds per run (default 2700)")
    r.add_argument("--runs", type=int, default=1, help="runs per task per arm (default 1)")
    r.add_argument("--arms", default="A,B")
    r.add_argument("--ref", default="HEAD", help="Nexika commit for arm B (default HEAD)")
    r.add_argument("--only", nargs="*", help="only these instance ids (any task in Verified)")
    r.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    r.set_defaults(fn=cmd_run)

    for name, fn, text in (("validate", cmd_validate, "grade each task's gold patch (no model calls)"),
                           ("grade", cmd_grade, "grade the runs with the SWE-bench harness")):
        g = sub.add_parser(name, help=text + "; needs docker")
        g.add_argument("--python", required=True, help="a python with `pip install swebench`")
        g.add_argument("--workers", type=int, default=4)
        g.add_argument("--test-timeout", type=int, default=1800, help="seconds for a task's tests")
        if name == "validate":
            g.add_argument("--only", nargs="*", help="only these instance ids")
        g.set_defaults(fn=fn)

    m = sub.add_parser("summary", help="write results.csv and the paired comparison")
    m.set_defaults(fn=cmd_summary)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
