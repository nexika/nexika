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
import shlex
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


def _node_install_hint(root: Path) -> str:
    """How to install the project's Node dependencies, following its lockfile: `npm ci` needs
    package-lock.json and fails without one (fastify has none: `.npmrc` package-lock=false)."""
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm install --frozen-lockfile"
    if (root / "yarn.lock").is_file():
        return "yarn install --immutable"
    if (root / "package-lock.json").is_file() or (root / "npm-shrinkwrap.json").is_file():
        return "npm ci"
    return "npm install"


def _node_deps_missing(root: Path, package: dict) -> bool:
    """package.json declares dependencies but they are not installed (no node_modules, no Yarn PnP)."""
    declared = package.get("dependencies") or package.get("devDependencies")
    installed = (root / "node_modules").is_dir() or (root / ".pnp.cjs").is_file()
    return bool(declared) and not installed


RUN_SCRIPT = re.compile(r"^(?:npm\s+run(?:-script)?|pnpm(?:\s+run)?|yarn(?:\s+run)?)\s+([\w:.@/-]+)$")
CI_RUN_SCRIPT = re.compile(r"(?:^|[\s;&|(])(?:npm\s+run(?:-script)?|pnpm(?:\s+run)?|yarn(?:\s+run)?)"
                           r"\s+([\w:.@/-]+)")
TYPE_SCRIPT = re.compile(r"(?i)type|tsd|tstyche")
LINT_SCRIPT = re.compile(r"(?i)lint|markdown|prettier|format")
TEST_SCRIPT = re.compile(r"(?i)test|unit|coverage|spec|e2e")


def _script_check_name(runner: str, script: str) -> str:
    """A name the user can run: npm runs only test, start and stop without `run` (`npm lint` fails);
    pnpm and yarn run any script by its name."""
    if runner == "npm" and script not in ("test", "start", "stop"):
        return f"npm run {script}"
    return f"{runner} {script}"


def _script_kind(name: str) -> str | None:
    """The check family a package script's name says: type tests and linters are lint, the rest
    of the test names are tests; None for a script that does not look like a check."""
    if TYPE_SCRIPT.search(name) or LINT_SCRIPT.search(name):
        return "lint"
    if TEST_SCRIPT.search(name):
        return "tests"
    return None


def _script_steps(body: str, scripts: dict, least: int = 2) -> list[str] | None:
    """The scripts of a pure `npm run a && npm run b ...` chain, or None for any other body."""
    steps = []
    for piece in str(body).split("&&"):
        m = RUN_SCRIPT.match(piece.strip())
        if not m or m.group(1) not in scripts:
            return None
        steps.append(m.group(1))
    return steps if len(steps) >= least else None


def _reached(names, scripts: dict) -> set[str]:
    """The scripts these run, themselves included, following `npm run x` chains."""
    seen, todo = set(), list(names)
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo += _script_steps(scripts.get(name, ""), scripts, least=1) or []
    return seen


def _ci_scripts(root: Path, scripts: dict) -> dict[str, str]:
    """Package scripts the CI workflows run (`npm run x`, or the script's own tool from
    node_modules/.bin or npx): script -> workflow file."""
    found: dict[str, str] = {}
    folder = root / ".github" / "workflows"
    files = sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")]) if folder.is_dir() else []
    tools = {}
    for name, body in scripts.items():
        words = str(body).split()
        if len(words) == 1:  # a script that is one tool: `"lint:markdown": "markdownlint-cli2"`
            tools.setdefault(words[0], name)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in CI_RUN_SCRIPT.findall(text):
            if name in scripts:
                found.setdefault(name, path.name)
        for tool, name in tools.items():
            if re.search(rf"(?:node_modules/\.bin/|npx\s+){re.escape(tool)}(?![\w-])", text):
                found.setdefault(name, path.name)
    return found


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


LINT_ENV = re.compile(r"(?i)\b(lint|flake8|mypy|pylint|ruff|isort|pre-commit|type-?check|typing|style)\b"
                      r"|--check\b")


def tox_envs(root: Path) -> dict[str, str]:
    """tox.ini's environments: name -> its commands ("" names the default [testenv]). Generative names
    like `{,ci-}py{310,311}` are left out: they are variants of the default."""
    import configparser
    path = root / "tox.ini"
    if not path.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(path.read_text(encoding="utf-8", errors="replace"))
    except (configparser.Error, OSError):
        return {}
    envs = {}
    for section in parser.sections():
        if section == "testenv":
            envs[""] = parser.get(section, "commands", fallback="")
        elif section.startswith("testenv:") and not set(section[8:]) & set("{},"):
            envs[section[8:].strip()] = parser.get(section, "commands", fallback="")
    return envs


def detect(root: Path, not_run: list | None = None) -> list[dict]:
    """The project's checks, from its own files: {name, kind, argv}. Checks found but not run (a tool
    not installed, a tox env that is neither tests nor lint) are added to `not_run` when given."""
    found: list[dict] = []
    skipped = not_run if not_run is not None else []

    def add(name: str, kind: str, argv: list[str], defined: str = "") -> None:
        if shutil.which(argv[0]):
            found.append({"name": name, "kind": kind, "argv": argv, "defined": defined})
        else:
            skipped.append({"name": name, "kind": kind, "command": " ".join(argv),
                            "reason": f"{Path(argv[0]).name} is not installed"})

    pyproject = root / "pyproject.toml"
    py_text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.is_file() else ""
    has_tests = (root / "tests").is_dir() or (root / "test").is_dir() or any(root.glob("test_*.py"))
    envs = tox_envs(root)
    tox = _python_tool(root, "tox")
    if "" in envs and shutil.which(tox[0]):
        # the project's own way to test: tox installs the package and sets up its environment
        add("tox -e py", "tests", [*tox, "-e", "py"], envs[""].strip()[:300])
    elif has_tests and (py_text or (root / "setup.cfg").is_file() or (root / "pytest.ini").is_file()
                        or (root / "tox.ini").is_file()):
        add("pytest", "tests", [*_python_tool(root, "pytest"), "-q"])
    if "[tool.ruff" in py_text or (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
        add("ruff", "lint", [*_python_tool(root, "ruff"), "check", "."])
    pre_commit = root / ".pre-commit-config.yaml"
    hooks = pre_commit.read_text(encoding="utf-8", errors="replace") if pre_commit.is_file() else ""
    if hooks:
        add("pre-commit", "lint", [*_python_tool(root, "pre-commit"), "run", "--all-files"])
    setup_cfg = root / "setup.cfg"
    cfg_text = setup_cfg.read_text(encoding="utf-8", errors="replace") if setup_cfg.is_file() else ""
    mypy_config = ("[tool.mypy]" in py_text or "[mypy]" in cfg_text
                   or (root / "mypy.ini").is_file() or (root / ".mypy.ini").is_file())
    if mypy_config and not re.search(r"id:\s*mypy\b", hooks):
        add("mypy", "lint", [*_python_tool(root, "mypy"), "."])
    for env, commands in envs.items():
        if not env:
            continue
        if LINT_ENV.search(env) or LINT_ENV.search(commands):
            add(f"tox -e {env}", "lint", [*tox, "-e", env])
        else:
            skipped.append({"name": f"tox -e {env}", "kind": "other", "command": f"tox -e {env}",
                            "reason": "a tox environment the proof does not run (not tests or lint)"})

    package = root / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            data = data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            data = {}
        scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        runner = _package_runner(root)
        missing = _node_deps_missing(root, data)
        planned: dict[str, str] = {}  # script -> kind, in the order they run
        for script, kind in (("test", "tests"), ("lint", "lint"), ("build", "build")):
            if script not in scripts:
                continue
            steps = _script_steps(scripts[script], scripts) if script == "test" else None
            if steps:  # each step on its own: one failing step no longer hides the next ones
                for step in steps:
                    planned.setdefault(step, _script_kind(step) or ("build" if "build" in step else "tests"))
            else:
                planned.setdefault(script, kind)
        covered = _reached([*planned, *(["test"] if "test" in scripts else [])], scripts)
        for script, workflow in _ci_scripts(root, scripts).items():
            kind = _script_kind(script)
            steps = _script_steps(scripts[script], scripts, least=1) or [script]
            if kind is None or script in covered or set(steps) <= covered:
                continue  # a CI gate the checks already run
            if kind == "lint":
                planned[script] = kind
            else:
                skipped.append({"name": _script_check_name(runner, script), "kind": "other",
                                "command": f"{runner} run {script}",
                                "reason": f"run by CI ({workflow}); the proof does not run it"})
        for script, kind in planned.items():
            if missing:  # `eslint: command not found` would be a false red proof
                skipped.append({"name": _script_check_name(runner, script), "kind": kind,
                                "command": f"{runner} run {script}",
                                "reason": "dependencies not installed (no node_modules): install them with "
                                          f"`{_node_install_hint(root)}`, then make the proof again"})
            else:  # what the script runs is recorded, so `"test": "exit 0"` shows
                add(_script_check_name(runner, script), kind, [runner, "run", script],
                    str(scripts[script])[:300])

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
    result = {"name": check["name"], "kind": check["kind"], "command": " ".join(shown),
              "defined": redact(check.get("defined", "")), "exit_code": code,
              "passed": code == 0, "seconds": round(time.monotonic() - start, 1), "tail": lines[-TAIL:]}
    missing = _own_package_missing(root, output) if code != 0 and check["kind"] == "tests" else ""
    if missing:
        result["not_installed"] = f"No module named '{missing}'"
    return result


def own_packages(root: Path) -> set[str]:
    """The project's own importable names: its [project] name and the packages at the root or in src/."""
    names = set()
    try:
        text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            names.add(re.sub(r"[-.]", "_", m.group(1)).lower())
    except OSError:
        pass
    for folder in (root, root / "src"):
        names.update(p.parent.name for p in folder.glob("*/__init__.py"))
    return names


def _own_package_missing(root: Path, output: str) -> str:
    """The project's own package that the tests could not import: its dependencies are not installed
    (no virtualenv, a src layout without PYTHONPATH), not a failure of the change."""
    own = own_packages(root)
    for name in re.findall(r"No module named '([\w.]+)'", output):
        if name.split(".")[0] in own:
            return name
    return ""


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
    not_run: list[dict] = []
    checks = [run_check(c, root, args.timeout) for c in detect(root, not_run) if c["kind"] in kinds]
    not_run = [n for n in not_run if n["kind"] in kinds or n["kind"] == "other"]
    # a test or lint check the project defines but that did not run leaves the change unproven
    skipped = any(n["kind"] in KINDS for n in not_run)
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
            "requirements": requirements, "ui": ui, "not_run": not_run,
            "summary": {"checks_passed": bool(checks) and all(c["passed"] for c in checks)
                        and not skipped and ui.get("verdict", "pass") == "pass",
                        "requirements_done": f"{len(args.done)}/{len(args.done) + len(args.open)}"}}


def describe(proof: dict) -> str:
    out = [f"Proof for {proof['project']} ({proof.get('branch') or '-'} at {proof.get('commit') or '-'}"
           f"{', with uncommitted changes' if proof.get('dirty') else ''}), {proof['created']}"]
    if not proof["checks"]:
        out.append("  No checks found for this project (tests, lint or build).")
    for check in proof["checks"]:
        if check.get("not_installed"):
            out.append(f"  {check['name']}: NOT RUN - the project's dependencies are not installed "
                       f"({check['not_installed']}). Install the project in a virtualenv (pip install -e .) "
                       f"or run its tests through tox, then make the proof again.  ({check['command']})")
            continue
        mark = "passed" if check["passed"] else f"FAILED (exit {check['exit_code']})"
        out.append(f"  {check['name']}: {mark} in {check['seconds']} s  ({check['command']})")
        if not check["passed"]:
            out += [f"      {line}" for line in check["tail"][-8:]]
    for item in proof.get("not_run") or []:
        out.append(f"  not run: {item['command']} ({item['kind']}) - {item['reason']}")
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
        not_run: list[dict] = []
        found = detect(root, not_run)
        lines = [f"{c['kind']}: {c['name']}  ({shlex.join(c['argv'])})" for c in found]
        lines += [f"not run: {n['command']} ({n['kind']}) - {n['reason']}" for n in not_run]
        print("\n".join(lines) or "No checks found for this project.")
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
