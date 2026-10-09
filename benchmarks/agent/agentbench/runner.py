"""Run one task in one arm: Claude Code inside the task's SWE-bench image, then keep the diff.

Both arms get the same image, model, prompt, permission mode, budget and time limit. Arm B adds
the Nexika plugins from a pinned commit with --plugin-dir. Nothing from the user's own Claude
Code setup reaches the container except the login.
"""

import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import metrics

PLUGIN_DIR = "/opt/nexika/plugins"
SHIM_DIR = "/opt/agentbench/bin"
BASE_PY = "/opt/miniconda3/bin/python3"
TESTBED_BIN = "/opt/miniconda3/envs/testbed/bin"
# The agent's python, python3, pip and pytest are the task's environment, as in a developer's
# activated venv. Nexika needs Python 3.10+, older than many task environments, so `python3` is a
# shim: a script under /opt/nexika runs on the image's conda base (3.11), anything else on the task's
# environment. The same shim is in both arms, and the plugins stay exactly as committed.
SHIM = f"""#!/bin/sh
case "$1" in /opt/nexika/*) exec {BASE_PY} "$@";; esac
exec {TESTBED_BIN}/python3 "$@"
"""
PATH = ":".join((SHIM_DIR, TESTBED_BIN, "/opt/miniconda3/bin", "/usr/local/sbin", "/usr/local/bin",
                 "/usr/sbin", "/usr/bin", "/sbin", "/bin"))
WORKDIR = "/testbed"
# A token from the environment is used first. Without one, the login file is copied in; a refresh
# inside the container can then sign the host out, so `claude setup-token` is the better choice.
AUTH_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")

PROMPT = """Fix the issue below in the repository in {workdir} (your current directory).
The project's environment is already installed. Change the source code so the issue is resolved.
Nobody will answer questions: decide for yourself and work until you are done.

<issue>
{problem}
</issue>
"""


def image_name(instance_id):
    return "swebench/sweb.eval.x86_64." + instance_id.replace("__", "_1776_").lower()


def build_prompt(problem):
    return PROMPT.format(workdir=WORKDIR, problem=problem.strip())


def plan(task_ids, runs, seed, arms=("A", "B")):
    """Every (task, run) gets both arms, in a random order fixed by the seed."""
    rng = random.Random(seed)
    order = []
    for run in range(1, runs + 1):
        for task in task_ids:
            pair = list(arms)
            rng.shuffle(pair)
            order.extend((task, run, arm) for arm in pair)
    return order


def run_name(task, arm, run):
    return f"{task}__{arm}__r{run}"


def claude_args(arm, model, budget):
    args = [
        "claude", "-p",
        "--output-format", "stream-json", "--verbose", "--include-hook-events",
        "--model", model,
        "--permission-mode", "bypassPermissions",
        # A prompt nobody can answer (a haris "ask") is denied, and counted as a denial.
        "--permission-prompts", "none",
        "--strict-mcp-config",
        "--max-budget-usd", str(budget),
    ]
    if arm == "B":
        args += ["--plugin-dir", PLUGIN_DIR]
    return args


def exec_env():
    """The environment claude gets inside the container. NEXIKA_BACKGROUND is never set: it makes
    every Nexika hook exit, which would quietly turn arm B into arm A."""
    env = {"IS_SANDBOX": "1", "DISABLE_AUTOUPDATER": "1", "PATH": PATH}
    for key in AUTH_VARS:
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def export_plugins(repo, sha, dest, sh=_sh):
    """The plugins as committed at sha (no local edits, no node_modules)."""
    archive = Path(dest) / "plugins.tar"
    out = sh(["git", "-C", str(repo), "archive", "-o", str(archive), sha, "plugins"])
    if out.returncode != 0:
        raise RuntimeError(f"git archive failed: {out.stderr.strip()}")
    sh(["tar", "-xf", str(archive), "-C", str(dest)])
    return Path(dest) / "plugins"


def run_one(task, arm, run, cfg, out_dir, sh=_sh, clock=time.monotonic):
    """Run claude on one task in one arm and write stream.jsonl, stderr.txt, diff.patch and
    meta.json (last, so a run without meta.json is redone on resume)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "agentbench-" + run_name(task["instance_id"], arm, run).lower().replace("__", "-")
    sh(["docker", "rm", "-f", name])
    started = sh(["docker", "run", "-d", "--name", name, "-w", WORKDIR,
                  image_name(task["instance_id"]), "sleep", "infinity"])
    if started.returncode != 0:
        raise RuntimeError(f"docker run failed: {started.stderr.strip()}")
    try:
        _prepare(name, arm, cfg, sh)
        cmd = ["docker", "exec", "-i", "-w", WORKDIR]
        for key, value in exec_env().items():
            cmd += ["-e", f"{key}={value}"]
        cmd += [name, *claude_args(arm, cfg["model"], cfg["budget"])]
        t0 = clock()
        timed_out = False
        try:
            proc = sh(cmd, input=build_prompt(task["problem_statement"]), timeout=cfg["timeout"])
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout, stderr, code = _text(exc.stdout), _text(exc.stderr), None
            sh(["docker", "exec", name, "pkill", "-f", "claude"])
        wall = clock() - t0
        (out_dir / "stream.jsonl").write_text(stdout)
        (out_dir / "stderr.txt").write_text(stderr)
        diff = sh(["docker", "exec", "-w", WORKDIR, name, "bash", "-c",
                   "git add -A >/dev/null 2>&1; git diff --cached HEAD"]).stdout
        (out_dir / "diff.patch").write_text(diff)
    finally:
        sh(["docker", "rm", "-f", name])

    meta = {
        "instance_id": task["instance_id"],
        "repo": task["repo"],
        "difficulty": task["difficulty"],
        "base_commit": task["base_commit"],
        "arm": arm,
        "run": run,
        "model": cfg["model"],
        "budget_usd": cfg["budget"],
        "timeout_s": cfg["timeout"],
        "nexika_sha": cfg["nexika_sha"] if arm == "B" else "",
        "claude_version": cfg.get("claude_version", ""),
        "exit_code": code,
        "timed_out": timed_out,
        "wall_s": round(wall, 1),
        **metrics.diff_stats(diff),
        **metrics.parse_stream(stdout.splitlines()),
    }
    meta["valid"], meta["invalid_reason"] = metrics.validity(meta, arm)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return meta


def _prepare(name, arm, cfg, sh):
    def check(args):
        out = sh(args)
        if out.returncode != 0:
            raise RuntimeError(f"{' '.join(args[:4])} failed: {out.stderr.strip()}")

    check(["docker", "cp", "-q", cfg["claude_bin"], f"{name}:/usr/local/bin/claude"])
    check(["docker", "exec", name, "mkdir", "-p", "/root/.claude", "/opt/nexika", SHIM_DIR])
    check(["docker", "exec", name, "test", "-x", f"{TESTBED_BIN}/python3"])
    check(["docker", "exec", name, "sh", "-c",
           f"cat > {SHIM_DIR}/python3 <<'EOF'\n{SHIM}EOF\nchmod +x {SHIM_DIR}/python3"])
    check(["docker", "exec", name, "sh", "-c",
           "echo '{\"hasCompletedOnboarding\": true}' > /root/.claude.json"])
    if not any(os.environ.get(key) for key in AUTH_VARS):
        check(["docker", "cp", "-q", cfg["credentials"], f"{name}:/root/.claude/.credentials.json"])
    if arm == "B":
        check(["docker", "cp", "-q", cfg["plugins_dir"], f"{name}:{PLUGIN_DIR}"])


def _text(value):
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def claude_binary():
    found = shutil.which("claude")
    if not found:
        raise RuntimeError("claude is not on PATH")
    return str(Path(found).resolve())


def claude_version(sh=_sh):
    out = sh(["claude", "--version"])
    return out.stdout.strip().split(" ")[0] if out.returncode == 0 else ""


def git_sha(repo, ref="HEAD", sh=_sh):
    out = sh(["git", "-C", str(repo), "rev-parse", ref])
    if out.returncode != 0:
        raise RuntimeError(f"unknown ref {ref}: {out.stderr.strip()}")
    return out.stdout.strip()


def scratch():
    return tempfile.mkdtemp(prefix="agentbench-")
