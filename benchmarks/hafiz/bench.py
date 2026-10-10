#!/usr/bin/env python3
"""hafiz benchmark: does work continue correctly after a compaction? (#348)

    python3 benchmarks/hafiz/bench.py run --dry-run           the plan, no model calls
    python3 benchmarks/hafiz/bench.py run --runs 3            paid: every task, both arms, 3 runs each
    python3 benchmarks/hafiz/bench.py score                   results.json and summary.md

Each run copies the fixture repo plus the task's overlay (one deliberately failing test) into a
fresh folder and a fresh home, then follows the task's script with `claude -p`:

    say         a prompt in the current session: the plan and the seeded decisions first, then one
                step per call (--resume)
    compact     /compact: a manual compaction of the same session
    restart     the next prompt starts a new session (--session-id, no --resume) in the same repo and
                home: Claude Code's summary does not carry over, hafiz's memory does

The repo's files and test results are recorded just before every compact and restart (a break).

Arm "plain" loads no plugins. Arm "hafiz" loads only plugins/hafiz, exported from a commit
(--plugin-dir). Everything else is the same: model, prompts, permission mode, budget, fixture.

Login: CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY from the environment, else the token in
--token-file (default ~/nexika-bench/.token). Nothing else is read: no ~/.claude credentials.
Raw data goes to ~/nexika-bench/hafiz/v2 (or $HAFIZBENCH_HOME), never into the repo. Version 1's
data stays in ~/nexika-bench/hafiz; `score --home ~/nexika-bench/hafiz` scores it again.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name: str, path: Path):
    """Load a module of this folder by path: other benchmarks also have a bench.py, so this folder
    never goes on sys.path."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


score = _load("hafiz_bench_score", HERE / "score.py")

ARMS = ("plain", "hafiz")
AUTH_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}


def bench_home() -> Path:
    return Path(os.environ.get("HAFIZBENCH_HOME") or Path.home() / "nexika-bench" / "hafiz" / "v2")


def load_tasks(path: Path = HERE / "tasks.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def all_tasks() -> dict:
    """Every task of every version by id, each with its script, for scoring old and new runs."""
    out = {}
    for name in ("tasks-v1.json", "tasks.json"):
        data = load_tasks(HERE / name)
        for task in data["tasks"]:
            out[task["id"]] = dict(task, script=script_for(task, data))
    return out


def folder(task: dict) -> str:
    """The task's folder under tasks/ (overlay and hidden checks); tasks can share one."""
    return task.get("folder") or task["id"]


def run_name(task: str, arm: str, run: int) -> str:
    return f"{task}__{arm}__r{run}"


def plan(tasks: list[str], arms: list[str], runs: int, seed: int = 348) -> list[tuple[str, str, int]]:
    """Every (task, arm, run), run by run so a stopped batch still has both arms of each task;
    the arm order inside each pair is random, fixed by the seed."""
    rng = random.Random(seed)
    order = []
    for run in range(1, runs + 1):
        for task in tasks:
            pair = list(arms)
            rng.shuffle(pair)
            order.extend((task, arm, run) for arm in pair)
    return order


def claude_args(prompt: str, arm: str, model: str, budget: float, session: str, first: bool,
                plugin_dir: str | None) -> list[str]:
    args = ["claude", "-p", prompt,
            "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--model", model,
            "--permission-mode", "bypassPermissions",
            "--permission-prompts", "none",
            "--strict-mcp-config",
            "--max-budget-usd", str(budget)]
    args += ["--session-id", session] if first else ["--resume", session]
    if arm == "hafiz":
        if not plugin_dir:
            raise ValueError("arm hafiz needs the exported plugin folder")
        args += ["--plugin-dir", plugin_dir]
    elif arm != "plain":
        raise ValueError(f"unknown arm: {arm}")
    return args


def script_for(task: dict, data: dict) -> list[dict]:
    """The task's script: {"say": prompt}, {"compact": true} and {"restart": true} items in order. A
    v1 task is its steps, one /compact, then the one continue prompt."""
    if task.get("script"):
        return task["script"]
    return [{"say": text} for text in task["steps"]] + [{"compact": True}, {"say": data["continue"]}]


def calls_for(script: list[dict]) -> list[tuple[str, str]]:
    """(phase, prompt) for every claude call, and ("restart", "") where a new session starts.
    Phases: step<n> for the prompts, compact<k> for each /compact."""
    out, steps, compacts = [], 0, 0
    for item in script:
        if item.get("restart"):
            out.append(("restart", ""))
        elif item.get("compact"):
            compacts += 1
            out.append((f"compact{compacts}", "/compact"))
        else:
            steps += 1
            out.append((f"step{steps}", item["say"]))
    return out


def describe(script: list[dict]) -> str:
    """'3 steps, /compact, 1 step, new session, 1 step (6 calls)'."""
    parts, steps = [], 0
    for phase, _ in calls_for(script) + [("end", "")]:
        if phase.startswith("step"):
            steps += 1
            continue
        if steps:
            parts.append(f"{steps} step{'s' if steps > 1 else ''}")
            steps = 0
        if phase != "end":
            parts.append("new session" if phase == "restart" else "/compact")
    calls = sum(1 for phase, _ in calls_for(script) if phase != "restart")
    return f"{', '.join(parts)} ({calls} calls)"


def auth_env(token_file: Path) -> dict:
    env = {k: os.environ[k] for k in AUTH_VARS if os.environ.get(k)}
    if not env and token_file.is_file():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def run_env(home: Path, auth: dict) -> dict:
    """A clean environment: none of the caller's Claude Code variables, a throwaway home (so
    transcripts and hafiz's data stay in the run folder), and NEXIKA_BACKGROUND never set (it would
    turn hafiz off)."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "LANG": "C.UTF-8",
            "TERM": "dumb", "DISABLE_AUTOUPDATER": "1", "NEXIKA_HOME": str(home / ".claude" / "nexika"),
            **auth}


def snapshot(repo: Path) -> dict:
    """The repo's text files (path -> content), without .git and caches."""
    out = {}
    for path in sorted(repo.rglob("*")):
        rel = path.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts) or not path.is_file():
            continue
        if path.stat().st_size > 200_000:
            continue
        out[rel.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _git(repo: Path, *args: str) -> str:
    who = ["-c", "user.name=bench", "-c", "user.email=bench@example.com"]
    return subprocess.run(["git", "-C", str(repo), *who, *args], capture_output=True, text=True,
                          check=True).stdout


def make_repo(task: dict, dest: Path) -> str:
    """The fixture with the task's overlay, committed on main, then the task branch checked out.
    Returns the starting commit."""
    shutil.copytree(HERE / "fixture", dest, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(HERE / "tasks" / folder(task) / "overlay", dest, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    (dest / ".gitignore").write_text("__pycache__/\n")
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "shelf: the catalog, list command and tests")
    _git(dest, "checkout", "-q", "-b", task["branch"])
    return _git(dest, "rev-parse", "HEAD").strip()


def make_home(home: Path) -> None:
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text('{"hasCompletedOnboarding": true}\n')
    (home / ".gitconfig").write_text("[user]\n\tname = Bench\n\temail = bench@example.com\n")


def run_tests(repo: Path, task_folder: str, out: Path) -> None:
    hidden = HERE / "tasks" / task_folder / "hidden_test.py"
    try:
        done = subprocess.run([sys.executable, str(HERE / "runtests.py"), str(repo), "--hidden", str(hidden)],
                              capture_output=True, text=True, timeout=180)
        data = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {}
    except (subprocess.TimeoutExpired, ValueError) as exc:
        data = {"tests": {}, "load_errors": [f"runtests: {type(exc).__name__}"]}
    out.write_text(json.dumps(data, indent=1))


def export_hafiz(ref: str, dest: Path) -> Path:
    """plugins/hafiz as committed at ref (no local edits)."""
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", ref], capture_output=True,
                         text=True, check=True).stdout.strip()
    folder = dest / f"plugins-{sha}"
    if not (folder / "hafiz").is_dir():
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / "hafiz.tar"
        subprocess.run(["git", "-C", str(REPO), "archive", "-o", str(archive), sha, "plugins/hafiz"],
                       check=True)
        subprocess.run(["tar", "-xf", str(archive), "-C", str(folder), "--strip-components", "1"], check=True)
        archive.unlink()
    return folder / "hafiz"


def spent(runs_dir: Path) -> float:
    """What every run so far cost, from the result events of its calls."""
    total = 0.0
    for stream in runs_dir.glob("*/call-*.jsonl"):
        total += score.read_call(stream)["cost_usd"] or 0.0
    return total


def run_one(task: dict, arm: str, run: int, cfg: dict, script: list[dict], version: int = 2) -> Path:
    out = cfg["runs_dir"] / run_name(task["id"], arm, run)
    if out.exists():
        shutil.rmtree(out)  # a run without meta.json did not finish: start it again
    repo, home = out / "repo", out / "home"
    out.mkdir(parents=True)
    make_home(home)
    base = make_repo(task, repo)
    (out / "snap-base.json").write_text(json.dumps(snapshot(repo)))
    env = run_env(home, cfg["auth"])
    sessions = [str(uuid.uuid4())]
    meta = {"version": version, "task": task["id"], "arm": arm, "run": run, "model": cfg["model"],
            "sessions": sessions, "repo": str(repo), "base": base,
            "plugin_dir": cfg["plugin_dir"] if arm == "hafiz" else None,
            "calls": [], "breaks": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    new_session = True
    for phase, prompt in calls_for(script):
        if spent(cfg["runs_dir"]) >= cfg["max_total"]:
            meta["stopped"] = f"the total budget of ${cfg['max_total']} was reached"
            break
        if phase == "restart" or phase.startswith("compact"):
            k = len(meta["breaks"]) + 1
            (out / f"snap-break{k}.json").write_text(json.dumps(snapshot(repo)))
            run_tests(repo, folder(task), out / f"tests-break{k}.json")
            meta["breaks"].append({"kind": "restart" if phase == "restart" else "compact",
                                   "at": len(meta["calls"]), "snap": f"snap-break{k}.json",
                                   "tests": f"tests-break{k}.json"})
        if phase == "restart":
            sessions.append(str(uuid.uuid4()))
            new_session = True
            continue
        n = len(meta["calls"]) + 1
        name = f"call-{n}.jsonl"
        args = claude_args(prompt, arm, cfg["model"], cfg["budget"], sessions[-1], new_session,
                           meta["plugin_dir"])
        new_session = False
        with open(out / name, "w", encoding="utf-8") as stdout, open(out / f"call-{n}.err", "w") as stderr:
            try:
                subprocess.run(args, cwd=repo, env=env, stdout=stdout, stderr=stderr, timeout=cfg["timeout"],
                               stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                meta.setdefault("timed_out", []).append(phase)
        meta["calls"].append({"phase": phase, "file": name, "session": len(sessions),
                              "kind": "compact" if phase.startswith("compact") else "say"})
        call = score.read_call(out / name)
        if call["result"] is None or (call["is_error"] and score.API_FAILURE.search(call["result_text"])):
            meta["stopped"] = f"{phase}: {call['result_text'][:200] or 'no result'}"
            break
    _git(repo, "add", "-A")
    (out / "diff.patch").write_text(_git(repo, "diff", "--cached", base))
    (out / "snap-final.json").write_text(json.dumps(snapshot(repo)))
    run_tests(repo, folder(task), out / "tests-final.json")
    for k, session in enumerate(sessions, 1):
        for transcript in (home / ".claude" / "projects").glob(f"*/{session}.jsonl"):
            shutil.copyfile(transcript, out / f"transcript-{k}.jsonl")
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return out


def cmd_run(args) -> int:
    data = load_tasks()
    tasks = {t["id"]: t for t in data["tasks"]}
    chosen = args.only or list(tasks)
    order = plan(chosen, args.arms.split(","), args.runs, args.seed)
    home = bench_home()
    runs_dir = home / "runs"
    todo = [(t, a, r) for t, a, r in order if not (runs_dir / run_name(t, a, r) / "meta.json").exists()]
    calls = sum(1 for t, _, _ in todo for phase, _ in calls_for(script_for(tasks[t], data))
                if phase != "restart")
    print(f"version {data['version']}: {len(order)} runs planned, {len(todo)} to do ({calls} claude calls), "
          f"{len(chosen)} tasks, arms {args.arms}, model {args.model}, ${args.budget} per call, "
          f"${args.max_total} in total, data in {home}")
    if args.dry_run:
        for task in chosen:
            print(f"  {task}: {describe(script_for(tasks[task], data))}")
        for t, a, r in todo:
            print("  ", run_name(t, a, r))
        return 0
    auth = auth_env(Path(os.path.expanduser(args.token_file)))
    if not auth:
        print("no login: set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY, or save a token to "
              f"{args.token_file}", file=sys.stderr)
        return 2
    cfg = {"runs_dir": runs_dir, "auth": auth, "model": args.model, "budget": args.budget,
           "max_total": args.max_total, "timeout": args.timeout,
           "plugin_dir": str(export_hafiz(args.ref, home)) if "hafiz" in args.arms else None}
    for task, arm, run in todo:
        if spent(runs_dir) >= args.max_total:
            print(f"stopped: ${spent(runs_dir):.2f} spent, the limit is ${args.max_total}")
            return 1
        out = run_one(tasks[task], arm, run, cfg, script_for(tasks[task], data), data["version"])
        row = score.score_run(out, tasks[task])
        print(f"{run_name(task, arm, run)}: continuity {row['continuity']} valid {row['valid']} "
              f"${row['cost_usd']:.2f} (total ${spent(runs_dir):.2f})", flush=True)
        if not row["valid"]:
            print("   invalid:", "; ".join(row["invalid"]), flush=True)
    return 0


def cmd_score(args) -> int:
    tasks = all_tasks()
    home = Path(args.home) if args.home else bench_home()
    rows = []
    for meta in sorted((home / "runs").glob("*/meta.json")):
        task = json.loads(meta.read_text())["task"]
        rows.append(score.score_run(meta.parent, tasks[task]))
    (home / "results.json").write_text(json.dumps(rows, indent=1))
    text = score.markdown(rows)
    (home / "summary.md").write_text(text)
    print(text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the tasks (paid)")
    run.add_argument("--arms", default="plain,hafiz")
    run.add_argument("--runs", type=int, default=3)
    run.add_argument("--only", nargs="*", help="task ids")
    run.add_argument("--model", default="sonnet")
    run.add_argument("--budget", type=float, default=1.5, help="USD per claude call")
    run.add_argument("--max-total", type=float, default=20.0, help="stop before spending more (USD)")
    run.add_argument("--timeout", type=int, default=1200, help="seconds per claude call")
    run.add_argument("--ref", default="HEAD", help="the commit whose plugins/hafiz arm hafiz loads")
    run.add_argument("--seed", type=int, default=348)
    run.add_argument("--token-file", default="~/nexika-bench/.token")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)
    scored = sub.add_parser("score", help="score every finished run")
    scored.add_argument("--home", help="the data folder (default ~/nexika-bench/hafiz/v2; "
                                       "v1's is ~/nexika-bench/hafiz)")
    scored.set_defaults(func=cmd_score)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
