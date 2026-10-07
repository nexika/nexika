#!/usr/bin/env python3
"""itqan proof: what shows that a change is done, saved as JSON (stdlib only).

itqan runs the project's own checks itself (tests, lint, build: detected from the project's files,
never a command Claude passes in) and records their results; the review verdict and the
requirement checklist are what Claude reports, and the proof says so. mizan shows the latest proof
when the user asks for it.

  run [--only tests,lint,build] [--review approve|changes]
      [--note TEXT]... [--done TEXT]... [--open TEXT]...
  show [--json]       the latest proof of this project
  checks              the checks itqan would run here, without running them

Saved in ~/.claude/nexika/itqan/proofs/<project>/ (latest.json and the last 20), and announced in
the shared status file ~/.claude/nexika/status/itqan.json (schema nexika.itqan/1).

When lawha checked the project's pages at this commit (status/lawha.json, a record in lawha's own
haris-guarded folder), the proof includes that check as "ui": its verdict, the widths, themes and
directions it covered, and the problems it found. A failing UI check fails the proof.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itqan_secrets  # noqa: E402
from itqan_guard import SECRET_PATTERNS  # noqa: E402
from itqan_learn import data_home, project_root  # noqa: E402

SCHEMA = "nexika.itqan.proof/1"
STATUS_SCHEMA = "nexika.itqan/1"
KEEP = 20
TAIL = 20
KINDS = ("tests", "lint", "build")
BLOCKING_NOTE = re.compile(r"^\s*[\[(]?\s*(?:critical|high|حرج|خطير|عالي)\b", re.I)


# ------------------------------------------------------------------ which checks

def _package_runner(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    return "npm"


def _python_tool(root: Path, tool: str) -> list[str]:
    """How the project runs a Python tool: `uv run` when it has uv.lock, else its virtualenv, else the
    python on PATH (never the interpreter that runs itqan, which has none of the project's packages)."""
    if (root / "uv.lock").is_file() and shutil.which("uv"):
        return ["uv", "run", tool]
    for venv in (".venv", "venv", "env"):
        for folder, exe in (("bin", "python"), ("Scripts", "python.exe")):
            python = root / venv / folder / exe
            if python.is_file() and os.access(python, os.X_OK):
                if tool == "pytest":
                    return [str(python), "-m", "pytest"]
                own = python.with_name(tool + (".exe" if exe.endswith(".exe") else ""))
                return [str(own)] if own.is_file() else [tool]
    if tool == "pytest":
        return [shutil.which("python3") or shutil.which("python") or sys.executable, "-m", "pytest"]
    return [tool]


def detect(root: Path) -> list[dict]:
    """The project's checks, from its own files: {name, kind, argv}."""
    found: list[dict] = []

    def add(name: str, kind: str, argv: list[str], defined: str = "") -> None:
        if shutil.which(argv[0]):
            found.append({"name": name, "kind": kind, "argv": argv, "defined": defined})

    pyproject = root / "pyproject.toml"
    py_text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.is_file() else ""
    has_tests = (root / "tests").is_dir() or (root / "test").is_dir() or any(root.glob("test_*.py"))
    if has_tests and (py_text or (root / "setup.cfg").is_file() or (root / "pytest.ini").is_file()
                      or (root / "tox.ini").is_file()):
        add("pytest", "tests", [*_python_tool(root, "pytest"), "-q"])
    if "[tool.ruff" in py_text or (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
        add("ruff", "lint", [*_python_tool(root, "ruff"), "check", "."])

    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts") or {}
        except (ValueError, OSError, AttributeError):
            scripts = {}
        runner = _package_runner(root)
        for script, kind in (("test", "tests"), ("lint", "lint"), ("build", "build")):
            if script in scripts:  # what the script runs is recorded, so `"test": "exit 0"` shows
                add(f"{runner} {script}", kind, [runner, "run", script], str(scripts[script])[:300])

    if (root / "go.mod").is_file():
        add("go vet", "lint", ["go", "vet", "./..."])
        add("go test", "tests", ["go", "test", "./..."])
    if (root / "Cargo.toml").is_file():
        add("cargo build", "build", ["cargo", "build", "--quiet"])
        add("cargo test", "tests", ["cargo", "test", "--quiet"])
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        add("dotnet build", "build", ["dotnet", "build", "--nologo"])
        add("dotnet test", "tests", ["dotnet", "test", "--nologo"])
    return found


# ------------------------------------------------------------------ running and saving

def redact(text: str) -> str:
    """The family's shared redaction (common/secrets.py), then the guard's own patterns."""
    text = itqan_secrets.redact(text)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(itqan_secrets.MARK, text)
    return text


def run_check(check: dict, root: Path, timeout: int) -> dict:
    start = time.monotonic()
    try:
        done = subprocess.run(check["argv"], cwd=root, capture_output=True, text=True, timeout=timeout,
                              check=False, stdin=subprocess.DEVNULL)
        code, output = done.returncode, (done.stdout or "") + (done.stderr or "")
    except subprocess.TimeoutExpired:
        code, output = 124, f"stopped after {timeout} s"
    except OSError as error:
        code, output = 127, str(error)
    lines = [redact(line)[:300] for line in output.splitlines() if line.strip()]
    shown = [Path(check["argv"][0]).name if check["argv"][0] == sys.executable else check["argv"][0],
             *check["argv"][1:]]
    return {"name": check["name"], "kind": check["kind"], "command": " ".join(shown),
            "defined": redact(check.get("defined", "")), "exit_code": code,
            "passed": code == 0, "seconds": round(time.monotonic() - start, 1), "tail": lines[-TAIL:]}


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def proof_dir(root: Path) -> Path:
    return data_home() / "proofs" / hashlib.sha1(str(root).encode()).hexdigest()[:16]


def _ensure_dir(folder: Path) -> None:
    missing = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for one in reversed(missing):
        one.mkdir(mode=0o700, exist_ok=True)
        os.chmod(one, 0o700)


def _write(path: Path, data: dict) -> None:
    _ensure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def status_path() -> Path:
    home = os.environ.get("NEXIKA_STATUS_HOME") or str(Path.home() / ".claude" / "nexika" / "status")
    return Path(home) / "itqan.json"


def publish(root: Path, latest: Path) -> None:
    """status/itqan.json: the latest proof per project, for mizan."""
    path = status_path()
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = {}
    proofs = current.get("proofs") if isinstance(current, dict) else None
    proofs = {k: v for k, v in (proofs or {}).items() if isinstance(v, str) and Path(v).is_file()}
    proofs[str(root)] = str(latest)
    _write(path, {"schema": STATUS_SCHEMA, "updated": int(time.time()), "proofs": proofs})


def save(root: Path, proof: dict) -> Path:
    folder = proof_dir(root)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    _write(folder / f"{stamp}.json", proof)
    latest = folder / "latest.json"
    _write(latest, proof)
    for old in sorted(p for p in folder.glob("2*.json"))[:-KEEP]:
        old.unlink(missing_ok=True)
    publish(root, latest)
    return latest


def clean(text: str) -> str:
    return " ".join(redact(re.sub(r"[\x00-\x1f\x7f]", " ", text)).split())[:500]


def ci_failure(root: Path, branch: str) -> dict:
    """The CI failure tabib diagnosed on this branch (status/tabib.json), so the proof shows it was
    reproduced before the fix; {} when there is none."""
    try:
        data = json.loads((status_path().parent / "tabib.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != "nexika.tabib/1":
        return {}
    entry = ((data.get("runs") or {}).get(str(root)) or {}).get(branch) or {}
    if not isinstance(entry, dict) or not entry.get("run"):
        return {}
    sha = str(entry.get("sha") or "")
    if not re.match(r"^[0-9a-f]{7,64}$", sha) or subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=root, capture_output=True,
            timeout=10, check=False).returncode != 0:
        return {}  # a failure of another line of work is not what this change answers
    return {"run": entry.get("run"), "kind": entry.get("kind", ""), "reproduced": entry.get("reproduced", ""),
            "cause": clean(str(entry.get("cause") or ""))}


def lawha_home() -> Path:
    return Path(os.path.expanduser(os.environ.get("LAWHA_HOME") or "~/.claude/nexika/lawha")).resolve()


def ui_check(root: Path) -> dict:
    """lawha's latest check of this project at this commit (status/lawha.json), or {}. Only a record
    in lawha's own folder counts: haris guards it, so Claude cannot write a passing one."""
    try:
        data = json.loads((status_path().parent / "lawha.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != "nexika.lawha/1":
        return {}
    path = (data.get("checks") or {}).get(str(root))
    if not isinstance(path, str):
        return {}
    try:
        record_path = Path(path).resolve()
        if lawha_home() / "checks" not in record_path.parents:
            return {}
        rec = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(rec, dict) or rec.get("schema") != "nexika.lawha.check/1":
        return {}
    if rec.get("commit") != _git(root, "rev-parse", "--short", "HEAD"):
        return {}  # a check of another commit says nothing about this change
    counts = rec.get("counts") or {}
    problems = [p for p in (rec.get("problems") or [])[:8] if isinstance(p, dict)]
    return {"verdict": "pass" if rec.get("verdict") == "pass" else "fail",
            "url": clean(str(rec.get("url") or "")),
            "widths": [w for w in rec.get("widths") or [] if isinstance(w, int)][:12],
            "themes": [str(t) for t in rec.get("themes") or []][:2],
            "dirs": [str(d) for d in rec.get("dirs") or []][:2],
            "fail": int(counts.get("fail") or 0), "warn": int(counts.get("warn") or 0),
            "problems": [clean(str(p.get("message") or "")) for p in problems],
            "created": str(rec.get("created") or ""), "dirty": bool(rec.get("dirty")), "by": "lawha"}


def make(root: Path, args) -> dict:
    kinds = set(args.only.split(",")) if args.only else set(KINDS)
    checks = [run_check(c, root, args.timeout) for c in detect(root) if c["kind"] in kinds]
    review = {"verdict": args.review, "notes": [clean(n) for n in args.note], "by": "reported by Claude"} \
        if args.review else {}
    requirements = [{"text": clean(t), "done": True} for t in args.done] + \
                   [{"text": clean(t), "done": False} for t in args.open]
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    ui = ui_check(root)
    return {"schema": SCHEMA, "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "project": str(root), "branch": branch, "ci_failure": ci_failure(root, branch),
            "commit": _git(root, "rev-parse", "--short", "HEAD"),
            "dirty": bool(_git(root, "status", "--porcelain")), "checks": checks, "review": review,
            "requirements": requirements, "ui": ui,
            "summary": {"checks_passed": bool(checks) and all(c["passed"] for c in checks)
                        and ui.get("verdict", "pass") == "pass",
                        "requirements_done": f"{len(args.done)}/{len(args.done) + len(args.open)}"}}


def describe(proof: dict) -> str:
    out = [f"Proof for {proof['project']} ({proof.get('branch') or '-'} at {proof.get('commit') or '-'}"
           f"{', with uncommitted changes' if proof.get('dirty') else ''}), {proof['created']}"]
    if not proof["checks"]:
        out.append("  No checks found for this project (tests, lint or build).")
    for check in proof["checks"]:
        mark = "passed" if check["passed"] else f"FAILED (exit {check['exit_code']})"
        out.append(f"  {check['name']}: {mark} in {check['seconds']} s  ({check['command']})")
        if not check["passed"]:
            out += [f"      {line}" for line in check["tail"][-8:]]
    ui = proof.get("ui") or {}
    if ui:
        themes = "/".join(ui.get("themes") or [])
        dirs = "/".join(d.upper() for d in ui.get("dirs") or [])
        covered = f"{len(ui.get('widths') or [])} widths, {themes}, {dirs}"
        mark = "passed" if ui["verdict"] == "pass" else f"FAILED ({ui.get('fail', 0)} to fix)"
        out.append(f"  pages on every screen (lawha): {mark} - {covered} - {ui.get('url', '')}")
        if ui["verdict"] != "pass":
            out += [f"      {p}" for p in ui.get("problems", [])[:5]]
    review = proof.get("review") or {}
    if review:
        out.append(f"  review (reported by Claude): {review['verdict']}")
        out += [f"      {note}" for note in review.get("notes", [])]
    for req in proof.get("requirements", []):
        out.append(f"  [{'x' if req['done'] else ' '}] {req['text']}")
    return "\n".join(out)


# ------------------------------------------------------------------ command line

def main(argv: list[str] | None = None) -> int:
    top = argparse.ArgumentParser(prog="itqan_proof.py", description="Record what shows a change is done.")
    sub = top.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="run the project's checks and save the proof")
    p.add_argument("--only", help="comma-separated kinds to run: tests,lint,build")
    p.add_argument("--review", choices=["approve", "changes"], help="the review verdict")
    p.add_argument("--note", action="append", default=[], help="a review finding still open")
    p.add_argument("--done", action="append", default=[], help="a requirement met")
    p.add_argument("--open", action="append", default=[], help="a requirement not met yet")
    p.add_argument("--timeout", type=int, default=900, help="seconds per check")
    p = sub.add_parser("show", help="the latest proof of this project")
    p.add_argument("--json", action="store_true")
    sub.add_parser("checks", help="the checks itqan would run here")
    args = top.parse_args(argv)

    root = project_root(Path.cwd())
    if args.command == "checks":
        found = detect(root)
        print("\n".join(f"{c['kind']}: {c['name']}" for c in found) or "No checks found for this project.")
        return 0
    if args.command == "show":
        try:
            proof = json.loads((proof_dir(root) / "latest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("No proof saved for this project yet. Make one with /itqan:proof.")
            return 1
        print(json.dumps(proof, ensure_ascii=False, indent=1) if args.json else describe(proof))
        return 0
    blocking = [n for n in args.note if BLOCKING_NOTE.match(n)]
    if args.review == "approve" and blocking:
        print(f"Refused: --review approve with a critical or high finding still open ({clean(blocking[0])}). "
              "Fix it first, or record the review as --review changes.", file=sys.stderr)
        return 2
    proof = make(root, args)
    path = save(root, proof)
    print(describe(proof))
    print(f"\nSaved: {path}\nThe user can see it with /mizan proof (mizan) or `itqan_proof.py show`.")
    return 0 if proof["summary"]["checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
