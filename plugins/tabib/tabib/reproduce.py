"""Running only the failing tests locally, at the failing commit, in a throwaway git worktree.

Rules, in order:
- only a commit on a branch of this repository (never a fork's code, which would run on your machine)
- only when the dependency files match your checkout; otherwise "dependencies differ", never an install
- only the failing tests, with the project's own test tool and its existing environment (venv,
  node_modules), names checked so nothing from the log can become an option
- your working tree is never touched; the worktree is removed afterwards
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import compare, secrets

TIMEOUT = 600
SAFE_NAME = re.compile(r"^[\w][\w./:@\[\]=,+-]*$")
SAFE_PATH = re.compile(r"^[\w][\w./@+-]*$")
GO_NAME = re.compile(r"^[A-Za-z_]\w*(?:/[\w-]+)*$")
VERSION = re.compile(r"(?i)\b(?:py(?:thon)?[- ]?|node[- ]?|go[- ]?)(\d+(?:\.\d+)?)\b")
OS_WORDS = {"ubuntu": "linux", "linux": "linux", "macos": "darwin", "mac": "darwin", "windows": "win32"}


def _safe_paths(values: list[str]) -> list[str]:
    return [v for v in dict.fromkeys(values) if v and SAFE_PATH.match(v) and ".." not in v.split("/")]


def _python(root: Path) -> str:
    for candidate in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe",
                      "venv/Scripts/python.exe"):
        if (root / candidate).is_file():
            return str(root / candidate)
    return shutil.which("python3") or sys.executable


def _runner(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    return "npm"


def command(root: Path, failures: list[dict]) -> tuple[list[str], str] | None:
    """The command that runs just these failures, and how to show it; None when there is none."""
    if not failures:
        return None
    framework = failures[0]["framework"]
    mine = [f for f in failures if f["framework"] == framework][:20]
    if framework == "pytest":
        nodes = [f["test"] for f in mine if SAFE_NAME.match(f["test"]) and ".." not in f["test"]]
        if not nodes:
            return None
        return [_python(root), "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodes], "pytest"
    if framework == "jest":
        files = _safe_paths([f["file"] for f in mine])
        runner = _runner(root)
        extra = ["--", *files] if runner == "npm" else files
        return ([runner, "run", "test", *extra], f"{runner} test") if files else None
    if framework == "go":
        names = [f["test"] for f in mine if GO_NAME.match(f["test"])]
        packages = _safe_paths([f.get("package", "") for f in mine]) or ["./..."]
        if not names:
            return None
        pattern = "^(" + "|".join(n.split("/")[0] for n in dict.fromkeys(names)) + ")$"
        return (["go", "test", *packages, "-run", pattern], "go test")
    if framework == "cargo":
        names = [f["test"] for f in mine if SAFE_NAME.match(f["test"])]
        return (["cargo", "test", names[0]], "cargo test") if names else None
    if framework == "dotnet":
        names = [f["test"] for f in mine if SAFE_NAME.match(f["test"])]
        return (["dotnet", "test", "--filter", "|".join(f"FullyQualifiedName~{n}" for n in names)],
                "dotnet test") if names else None
    if framework == "ruff":
        files = _safe_paths([f["file"] for f in mine])
        return (["ruff", "check", *files], "ruff") if files else None
    if framework == "eslint":
        files = _safe_paths([f["file"].lstrip("/") for f in mine if not f["file"].startswith("/")])
        return (["npx", "--no-install", "eslint", *files], "eslint") if files else None
    if framework == "tsc":
        return (["npx", "--no-install", "tsc", "--noEmit"], "tsc")
    return None


def notes(jobs: list[dict], interpreter: str) -> list[str]:
    """Why a local run may differ from the failed job: another Python or Node version, another OS."""
    found = []
    names = " ".join(j["name"] for j in jobs)
    local = platform.python_version()
    try:
        out = subprocess.run([interpreter, "--version"], capture_output=True, text=True, timeout=10,
                             check=False)
        local = out.stdout.split()[-1] if out.stdout.split() else local
    except (OSError, subprocess.SubprocessError):
        pass
    for m in VERSION.finditer(names):
        if m.group(0).lower().startswith("py") and not local.startswith(m.group(1)):
            found.append(f"CI failed on Python {m.group(1)}; here it is Python {local}.")
            break
    for word, plat in OS_WORDS.items():
        if word in names.lower() and not sys.platform.startswith(plat):
            found.append(f"CI failed on {word}; this machine is {sys.platform}.")
            break
    return found


FORK = ("the commit is not on a branch of this repository (a fork's pull request?); its code would run "
        "on your machine, so tabib does not run it: run it yourself only if you trust it")


def run(repo: str, sha: str, branch: str, failures: list[dict], jobs: list[dict],
        fork: bool | None = False) -> dict:
    """`fork` is what the CI service says about the run's origin: only False (this repository) runs."""
    root = Path(repo)
    picked = command(root, failures)
    if picked is None:
        return {"status": "skipped", "why": "nothing tabib can run locally for this failure"}
    if fork is not False:
        return {"status": "skipped", "why": FORK}
    if not compare.fetch(repo, sha, branch):
        return {"status": "skipped", "why": "the failing commit is not available from origin"}
    if not compare.advertised_by_origin(repo, sha, branch):
        return {"status": "skipped", "why": FORK}
    _, names = compare.git(repo, "diff", "--name-only", "HEAD", sha)
    differ = compare.deps_changed(names.splitlines())
    if differ:
        return {"status": "skipped",
                "why": "dependencies differ from your checkout: " + ", ".join(differ[:5])}
    argv, label = picked
    parent = Path(tempfile.mkdtemp(prefix="tabib-"))  # 0700: nobody else can swap the folder
    place = parent / "worktree"
    code, _ = compare.git(repo, "worktree", "add", "--detach", "--quiet", str(place), sha, timeout=300)
    if code != 0:
        compare.git(repo, "worktree", "remove", "--force", str(place), timeout=60)
        shutil.rmtree(parent, ignore_errors=True)
        compare.git(repo, "worktree", "prune", timeout=30)
        return {"status": "error", "why": "could not create a worktree for the failing commit"}
    shown = " ".join([Path(argv[0]).name if os.path.isabs(argv[0]) else argv[0], *argv[1:]])
    try:
        if (root / "node_modules").is_dir() and not (place / "node_modules").exists():
            (place / "node_modules").symlink_to(root / "node_modules", target_is_directory=True)
        env = {**os.environ, "CI": "1"}
        if label == "pytest":  # the failing commit's code first, not an editable install of your checkout
            paths = [str(p) for p in (place / "src", place) if p.is_dir()]
            env["PYTHONPATH"] = os.pathsep.join([*paths, env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        start = time.monotonic()
        try:
            done = subprocess.run(argv, cwd=place, capture_output=True, text=True, timeout=TIMEOUT,
                                  check=False, stdin=subprocess.DEVNULL, env=env)
            exit_code, output = done.returncode, (done.stdout or "") + (done.stderr or "")
        except subprocess.TimeoutExpired:
            exit_code, output = 124, f"stopped after {TIMEOUT} s"
        except OSError as error:
            return {"status": "error", "why": f"{argv[0]}: {error}", "command": shown}
        seconds = round(time.monotonic() - start, 1)
    finally:
        compare.git(repo, "worktree", "remove", "--force", str(place), timeout=60)
        shutil.rmtree(parent, ignore_errors=True)
        compare.git(repo, "worktree", "prune", timeout=30)
    tail = [line[:300] for line in secrets.redact(output).splitlines() if line.strip()][-30:]
    if label == "pytest" and exit_code in (4, 5):
        status, why = "error", "pytest could not collect the failing tests at that commit"
    elif label == "go test" and "no tests to run" in output:
        status, why = "error", "go test found none of the failing tests at that commit"
    elif exit_code == 0:
        status, why = "not_reproduced", "the failing tests pass here"
    else:
        status, why = "reproduced", "the failing tests fail here too"
    return {"status": status, "why": why, "command": shown, "exit_code": exit_code, "seconds": seconds,
            "tail": tail, "notes": notes(jobs, argv[0]) if status == "not_reproduced" else []}
