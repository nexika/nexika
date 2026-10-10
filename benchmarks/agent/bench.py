#!/usr/bin/env python3
"""Claude Code alone against Claude Code with Nexika, on SWE-bench Verified tasks.

  bench.py select                     pick the tasks (writes pilot.json; no model calls)
  bench.py validate --python VENV/python   check every task grades its own gold fix as resolved
  bench.py run --model sonnet         run every task in every arm (paid model calls)
  bench.py grade --python VENV/python grade the diffs with the SWE-bench harness
  bench.py summary                    results.csv and the paired comparison
  bench.py pipeline --model sonnet --python VENV/python
                                      validate, run, grade in batches, deleting each batch's
                                      images after (the images take 4 to 11 GB each)
  bench.py context --model sonnet     the prompt tokens each plugin adds, one plugin at a time

An arm is A (no plugins), B (all of Nexika) or Nexika plugin names joined by "+" (an ablation).

Results go to $AGENTBENCH_HOME (default ~/nexika-bench/<pilot>). See README.md.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agentbench import grade, runner, summary, tasks  # noqa: E402

REPO = HERE.parent.parent
PILOT = HERE / "pilot.json"
QUOTAS = {tasks.EASY: 6, tasks.MEDIUM: 10, tasks.HARD: 4}
DIFFICULTY = {"easy": tasks.EASY, "medium": tasks.MEDIUM, "hard": tasks.HARD, "very_hard": tasks.VERY_HARD}
_print_lock = threading.Lock()


def say(text):
    with _print_lock:
        print(text, file=sys.stderr, flush=True)


def parse_quotas(text):
    """"easy=15,medium=40,hard=42,very_hard=3" -> {difficulty label: count}."""
    quotas = {}
    for part in text.split(","):
        key, _, count = part.partition("=")
        if key.strip() not in DIFFICULTY or not count.strip().isdigit():
            raise SystemExit(f"bad quota {part!r}: use {', '.join(DIFFICULTY)} with a count")
        quotas[DIFFICULTY[key.strip()]] = int(count)
    return quotas


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
    quotas = parse_quotas(args.quotas) if args.quotas else QUOTAS
    picked = tasks.select(rows, quotas, args.seed, args.max_per_repo, args.scarce_first)
    pilot = {
        "name": args.name, "dataset": tasks.DATASET, "seed": args.seed,
        "quotas": quotas, "max_per_repo": args.max_per_repo, "scarce_first": args.scarce_first,
        "instance_ids": [r["instance_id"] for r in picked],
    }
    out = Path(args.out)
    out.write_text(json.dumps(pilot, indent=1) + "\n")
    tasks.save_tasks(home(pilot) / "tasks.json", rows)
    for r in picked:
        print(f"{r['difficulty']:>16}  {r['instance_id']}")
    print(f"wrote {out}")


def _metas(base):
    metas, diffs = [], {}
    for meta_path in sorted((base / "runs").glob("*/meta.json")):
        meta = json.loads(meta_path.read_text())
        metas.append(meta)
        diffs[(meta["instance_id"], meta["arm"], meta["run"])] = (meta_path.parent / "diff.patch").read_text()
    return metas, diffs


def parse_arms(text):
    arms = tuple(a.strip() for a in text.split(",") if a.strip())
    for arm in arms:
        try:
            runner.arm_plugins(arm)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
    return arms


def make_cfg(args):
    sha = runner.git_sha(REPO, args.ref)
    return {
        "model": args.model, "budget": args.budget, "timeout": args.timeout, "nexika_sha": sha,
        "claude_bin": runner.claude_binary(), "claude_version": runner.claude_version(),
        "credentials": str(Path.home() / ".claude" / ".credentials.json"),
        "plugins_dir": str(runner.export_plugins(REPO, sha, runner.scratch())),
    }


def run_order(order, rows, cfg, base, jobs):
    """Run every (task, run, arm) without a valid run yet, `jobs` containers at a time. An invalid
    run (an API failure, a crash) is run again."""
    def done(task, run, arm):
        path = base / "runs" / runner.run_name(task, arm, run) / "meta.json"
        return path.exists() and json.loads(path.read_text()).get("valid")

    todo = [(n, item) for n, item in enumerate(order, 1) if not done(*item)]

    def one(numbered):
        n, (task, run, arm) = numbered
        out = base / "runs" / runner.run_name(task, arm, run)
        say(f"[{n}/{len(order)}] {task} arm {arm} run {run}")
        try:
            meta = runner.run_one(rows[task], arm, run, cfg, out)
        except RuntimeError as exc:
            say(f"  {task} {arm}: failed: {exc}")
            return
        flag = "" if meta["valid"] else f"  INVALID: {meta['invalid_reason']}"
        say(f"  {task} {arm}: {meta['result'] or 'no result'}  ${meta['cost_usd'] or 0:.2f}  "
            f"{meta['wall_s']:.0f}s  {meta['files_changed']} files  tests {meta['test_commands']}  "
            f"{meta['permission_denials']} denials{flag}")

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        list(pool.map(one, todo))


def cmd_run(args):
    pilot = tasks.load_pilot(args.pilot)
    base = home(pilot)
    ids = args.only or pilot["instance_ids"]
    rows = load_task_rows(base, ids)
    arms = parse_arms(args.arms)
    order = runner.plan(ids, args.runs, pilot["seed"], arms)
    if args.dry_run:
        for task, run, arm in order:
            print(f"{task} arm {arm} run {run}: {runner.image_name(task)}")
        for arm in arms:
            print(f"{arm}: " + " ".join(runner.claude_args(arm, args.model, args.budget)))
        return
    run_order(order, rows, make_cfg(args), base, args.jobs)


def cmd_grade(args):
    pilot = tasks.load_pilot(args.pilot)
    grade_all(pilot, home(pilot), args)


def grade_all(pilot, base, args):
    """Grade every kept diff; reports already written are not graded again."""
    metas, diffs = _metas(base)
    groups = grade.predictions(metas, diffs, pilot["name"])
    grades = grade.run(groups, base / "grading", pilot["name"], args.python, args.workers, args.test_timeout)
    out = [{"instance_id": k[0], "arm": k[1], "run": k[2], **v} for k, v in sorted(grades.items())]
    (base / "grades.json").write_text(json.dumps(out, indent=1) + "\n")
    say(f"graded {len(out)} runs; resolved {sum(g['resolved'] for g in out)}")
    missing = [g for g in out if not g["graded"] and diffs[(g["instance_id"], g["arm"], g["run"])].strip()]
    if missing:
        say(f"WARNING: {len(missing)} non-empty diffs have no report (harness error): see grading/logs")


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


def cmd_pipeline(args):
    """validate -> run -> grade, one batch of tasks at a time, then delete the batch's images.
    Tasks whose gold patch does not grade as resolved are skipped and listed in excluded.json."""
    pilot = tasks.load_pilot(args.pilot)
    base = home(pilot)
    ids = args.only or pilot["instance_ids"]
    rows = load_task_rows(base, ids)
    arms = parse_arms(args.arms)
    cfg = make_cfg(args)
    excluded_path = base / "excluded.json"
    excluded = json.loads(excluded_path.read_text()) if excluded_path.exists() else {}
    for start in range(0, len(ids), args.batch):
        batch = [i for i in ids[start:start + args.batch] if i not in excluded]
        say(f"== batch {start // args.batch + 1}: {len(batch)} tasks")
        checked = grade.validate(batch, base / "grading", args.python, args.workers, args.test_timeout)
        for instance_id, g in checked.items():
            if not g["resolved"]:
                excluded[instance_id] = "gold patch not graded resolved"
                say(f"  excluded {instance_id}: its own gold patch does not grade as resolved")
        excluded_path.write_text(json.dumps(excluded, indent=1) + "\n")
        batch = [i for i in batch if i not in excluded]
        run_order(runner.plan(batch, args.runs, pilot["seed"], arms), rows, cfg, base, args.jobs)
        grade_all(pilot, base, args)
        if not args.keep_images:
            subprocess.run(["docker", "rmi", "-f", *(runner.image_name(i) for i in batch)],
                           capture_output=True)
            subprocess.run(["docker", "image", "prune", "-f"], capture_output=True)
    cmd_summary(args)


CONTEXT_ARMS = ("A", *runner.metrics.NEXIKA, "B")


def cmd_context(args):
    """One session per arm on the same task, stopped after the model's first reply: the first
    request's size is everything the plugins add before any work."""
    pilot = tasks.load_pilot(args.pilot)
    base = home(pilot)
    task_id = args.task or pilot["instance_ids"][0]
    task = load_task_rows(base, [task_id])[task_id]
    cfg = make_cfg(args)
    results = {}
    for arm in CONTEXT_ARMS:
        out = base / "context" / arm
        meta_path = out / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            say(f"context: {arm}")
            meta = runner.run_one(task, arm, 1, cfg, out, extra_args=("--max-turns", "1"))
        if not meta["valid"]:
            say(f"  {arm}: INVALID: {meta['invalid_reason']}")
        results[arm] = meta
    text = context_markdown(results, task_id, cfg["model"])
    (base / "context.md").write_text(text)
    print(text)


def context_markdown(results, task_id, model):
    base = results["A"]["first_prompt_tokens"] or 0
    lines = [f"# Prompt tokens each Nexika plugin adds ({model}, task {task_id})", "",
             "Each row is one session with only that plugin, stopped after the first reply. Extra tokens is "
             "the first request's size minus the session without plugins. It is paid on every session.",
             "", "| Plugin | Extra tokens | Hook output (characters) | Hooks run |", "|---|---|---|---|"]
    singles = [a for a in results if a not in ("A", "B")]
    for arm in sorted(singles, key=lambda a: -(results[a]["first_prompt_tokens"] or 0)):
        m = results[arm]
        lines.append(f"| {arm} | {(m['first_prompt_tokens'] or 0) - base:+,} | {m['hook_output_chars']:,} "
                     f"| {m['hook_runs']} |")
    total = sum((results[a]["first_prompt_tokens"] or 0) - base for a in singles)
    lines += ["", f"Without plugins the first request is {base:,} tokens. The plugins one at a time add "
              f"{total:+,} in total."]
    if "B" in results:
        b = (results["B"]["first_prompt_tokens"] or 0) - base
        share = b / base * 100 if base else 0
        lines.append(f"All twelve together add {b:+,} ({share:.0f}% of the first request).")
    return "\n".join(lines) + "\n"


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
    s.add_argument("--quotas", help="e.g. easy=15,medium=40,hard=42,very_hard=3 (default: the pilot's)")
    s.add_argument("--out", default=str(PILOT), help="where to write the task list")
    s.add_argument("--scarce-first", action="store_true", help="fill the rarest difficulty first")
    s.set_defaults(fn=cmd_select)

    def run_options(r, arms=True):
        r.add_argument("--model", required=True, help="the same model for every arm, e.g. sonnet or opus")
        r.add_argument("--budget", type=float, default=5.0, help="max USD per run (default 5)")
        r.add_argument("--timeout", type=int, default=2700, help="max seconds per run (default 2700)")
        r.add_argument("--ref", default="HEAD", help="Nexika commit for the plugins (default HEAD)")
        if arms:
            r.add_argument("--runs", type=int, default=1, help="runs per task per arm (default 1)")
            r.add_argument("--arms", default="A,B", help='e.g. "A,B,itqan,siyaq,haris+barq"')
            r.add_argument("--jobs", type=int, default=1, help="containers at a time (default 1)")
            r.add_argument("--only", nargs="*", help="only these instance ids (any task in Verified)")

    def grader_options(g):
        g.add_argument("--python", required=True, help="a python with `pip install swebench`")
        g.add_argument("--workers", type=int, default=4)
        g.add_argument("--test-timeout", type=int, default=1800, help="seconds for a task's tests")

    r = sub.add_parser("run", help="run the tasks in every arm (paid)")
    run_options(r)
    r.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    r.set_defaults(fn=cmd_run)

    for name, fn, text in (("validate", cmd_validate, "grade each task's gold patch (no model calls)"),
                           ("grade", cmd_grade, "grade the runs with the SWE-bench harness")):
        g = sub.add_parser(name, help=text + "; needs docker")
        grader_options(g)
        if name == "validate":
            g.add_argument("--only", nargs="*", help="only these instance ids")
        g.set_defaults(fn=fn)

    pl = sub.add_parser("pipeline", help="validate, run and grade in batches, deleting images (paid)")
    run_options(pl)
    grader_options(pl)
    pl.add_argument("--batch", type=int, default=10, help="tasks per batch (default 10)")
    pl.add_argument("--keep-images", action="store_true", help="do not delete each batch's images")
    pl.set_defaults(fn=cmd_pipeline)

    c = sub.add_parser("context", help="prompt tokens each plugin adds (14 short paid sessions)")
    run_options(c, arms=False)
    c.add_argument("--task", help="instance id to measure on (default: the first task)")
    c.set_defaults(fn=cmd_context)

    m = sub.add_parser("summary", help="write results.csv and the paired comparison")
    m.set_defaults(fn=cmd_summary)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
