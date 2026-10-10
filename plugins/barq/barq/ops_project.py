"""info (what is this project and how do I build/test it), run, and custom ops."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from collections import Counter
from pathlib import Path

from . import compress, files
from .core import EXEC, READ, Context, OpError, OpSpec, Result, int_arg
from .mask import mask_text

LANGUAGES = {
    ".cs": "C#", ".fs": "F#", ".vb": "VB.NET", ".py": "Python", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift",
    ".rb": "Ruby", ".php": "PHP", ".c": "C", ".h": "C/C++", ".cpp": "C++", ".hpp": "C++",
    ".dart": "Dart", ".scala": "Scala", ".vue": "Vue", ".svelte": "Svelte", ".sql": "SQL",
    ".sh": "Shell", ".ps1": "PowerShell", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
}
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "setup.py", "requirements.txt", "go.mod", "Cargo.toml",
    "pom.xml", "build.gradle", "build.gradle.kts", "Makefile", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yaml", "CMakeLists.txt", "Gemfile", "composer.json",
    "global.json", "Directory.Build.props",
}
RUN_TIMEOUT = 600
CUSTOM_MAX_LINES = 200


# ---------------------------------------------------------------- detection


def _package_manager(folder: Path) -> str:
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"),
                     ("bun.lock", "bun")):
        if (folder / lock).exists():
            return pm
    return "npm"


# Which package.json script is "test" (#277, maintainer's decision): one that runs test code -
# files under a test directory or files written with test syntax. A linter alone is not a test.
_TEST_RUNNERS = re.compile(
    r"(?:^|[\s/])(?:jest|vitest|mocha|ava|tap|tape|borp|uvu|jasmine|karma|tstyche|tsd|playwright"
    r"|cypress|node\s+(?:[^|&;]*\s)?--test)(?:\s|$)")
_TEST_PATHS = re.compile(r"(?:^|[\s'\"=/])(?:test|tests|__tests__|spec)(?:/|\s|$|['\"])"
                         r"|\.(?:test|spec)\.[cm]?[jt]sx?\b|\btest\b")
_LINTERS = re.compile(r"^(?:npx\s+)?(?:eslint|prettier|standard|neostandard|xo|stylelint|biome|"
                      r"markdownlint(?:-cli2?)?|tslint|oxlint|jshint|semistandard|ts-standard)\b")
_TEST_SYNTAX = re.compile(r"\bnode:test\b|\brequire\(['\"]assert|from ['\"](?:node:)?assert"
                          r"|^\s*(?:test|it|describe)\(|\bexpect\(", re.M)
_SCRIPT_REF = re.compile(r"^(?:npm|pnpm|yarn|bun)\s+(?:run(?:-script)?\s+)?([\w:.-]+)")
_NODE_FILE = re.compile(r"^node\s+(?:-\S+\s+)*([\w./-]+\.[cm]?js)\b")


def _script_parts(name: str, scripts: dict, folder: Path, seen: frozenset = frozenset()) -> set[str]:
    """The kinds of work a script does: 'test', 'lint' and 'other', following `npm run x`."""
    kinds: set[str] = set()
    body = scripts.get(name)
    if not isinstance(body, str) or name in seen:
        return {"other"}
    for part in re.split(r"&&|\|\||;|\|", body):
        part = part.strip()
        ref = _SCRIPT_REF.match(part)
        target = ref and ("test" if ref.group(1) == "test" else ref.group(1))
        if target and target in scripts:
            kinds |= _script_parts(target, scripts, folder, seen | {name})
        elif not part or part.startswith(("echo", "exit")):
            kinds.add("other")
        elif _LINTERS.match(part):
            kinds.add("lint")
        elif _TEST_RUNNERS.search(part) or _TEST_PATHS.search(part):
            kinds.add("test")
        else:
            node = _NODE_FILE.match(part)
            try:
                code = (folder / node.group(1)).read_text(encoding="utf-8", errors="replace") if node else ""
            except OSError:
                code = ""
            kinds.add("test" if _TEST_SYNTAX.search(code) else "other")
    return kinds


def node_test_script(scripts: dict, folder: Path) -> str | None:
    """The script to run as "test": `test` when it runs tests and no linter; otherwise the first
    script that does (test:ci, test:unit, unit, then any other); `test` itself when it runs tests
    but also lints and nothing else qualifies; None when no script runs test code."""
    kinds = {n: _script_parts(n, scripts, folder) for n in scripts}
    pure = [n for n, k in kinds.items() if "test" in k and "lint" not in k]
    if "test" in pure:
        return "test"
    preferred = ("test:ci", "test:unit", "unit", "test:all")
    for name in [*preferred, *sorted(pure, key=lambda n: (not n.startswith("test"), n))]:
        if name in pure:
            return name
    return "test" if "test" in kinds.get("test", set()) else None


FIXTURE_DIRS = {"docs", "doc", "fixtures", "__fixtures__", "testdata", "test_data"}


def _is_fixture(rel: str) -> bool:
    """A manifest in docs or test data (docs/compatible_configs/x/pyproject.toml,
    tests/data/x/pyproject.toml) is an example, not a project to build (#167)."""
    parts = rel.split("/")[:-1]
    if FIXTURE_DIRS.intersection(parts):
        return True
    return any(a.startswith("test") and b == "data" for a, b in zip(parts, parts[1:], strict=False))


def _pre_commit_hooks(root: Path) -> list[str]:
    try:
        text = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return list(dict.fromkeys(re.findall(r"^\s*-\s*id:\s*['\"]?([\w.-]+)", text, re.M)))


def _tox_envs(root: Path) -> list[str]:
    try:
        text = (root / "tox.ini").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    match = re.search(r"^envlist\s*=\s*(.+)$", text, re.M)
    envlist = match.group(1).strip() if match else ""
    named = [n for n in re.findall(r"^\[testenv:([^\]]+)\]", text, re.M) if n not in envlist]
    return ([envlist] if envlist else []) + named


def _stacks(root: Path, all_files: list[Path]) -> list[dict]:
    """Every build stack found, root project first: {name, where, commands}.

    A package.json or Python marker below the root (say plugins/x/engine/package.json) is a
    sub-project, so it ranks after anything at the root; run:test then runs the repo's own
    suite and the nested one stays listed under "also detected".
    """
    rels = [files.rel(f, root) for f in all_files]
    shallow = [r for r in rels if r.count("/") <= 3 and not _is_fixture(r)]
    stacks: list[dict] = []

    slns = sorted(r for r in shallow if r.endswith((".sln", ".slnx")))
    projs = sorted(r for r in shallow if r.endswith((".csproj", ".fsproj", ".vbproj")))
    if slns or projs:
        suffix = f" {slns[0]}" if len(slns) > 1 else ""
        stacks.append({"name": "dotnet", "where": ", ".join((slns or projs)[:3]), "commands": {
            "build": f"dotnet build{suffix}", "test": f"dotnet test{suffix}",
            "lint": f"dotnet format --verify-no-changes{suffix}",
        }})

    for pkg in sorted(r for r in shallow if r.endswith("package.json") and "node_modules" not in r):
        folder = (root / pkg).parent
        try:
            scripts = json.loads((root / pkg).read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError, AttributeError):
            scripts = {}
        pm = _package_manager(folder)
        prefix = "" if folder == root else f"cd {shlex.quote(files.rel(folder, root))} && "
        cmds = {}
        test_script = node_test_script(scripts, folder) if isinstance(scripts, dict) else None
        if test_script == "test":
            cmds["test"] = f"{prefix}{pm} test"
        elif test_script:
            cmds["test"] = f"{prefix}{pm} run {test_script}"
        for name in ("build", "lint"):
            if name in scripts:
                cmds[name] = f"{prefix}{pm} run {name}"
        stacks.append({"name": f"node ({pm})", "where": pkg, "commands": cmds,
                       "nested": folder != root})

    py_markers = [r for r in shallow if r.rsplit("/", 1)[-1] in ("pyproject.toml", "setup.py",
                                                                "requirements.txt", "pytest.ini")]
    if py_markers:
        cmds = {}
        pyproject = root / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.exists() else ""
        has_tests = any(r.startswith("tests/") or "/test_" in r or r.startswith("test_") for r in rels)
        if "pytest" in text or has_tests or (root / "pytest.ini").exists():
            cmds["test"] = "python -m pytest"
        if "[tool.ruff" in text or (root / "ruff.toml").exists():
            cmds["lint"] = "ruff check ."
        if re.search(r"^\[build-system\]", text, re.M):
            cmds["build"] = "python -m build"
        stacks.append({"name": "python", "where": ", ".join(py_markers[:3]), "commands": cmds,
                       "nested": all("/" in r for r in py_markers)})

    if (root / "go.mod").exists():
        stacks.append({"name": "go", "where": "go.mod", "commands": {
            "build": "go build ./...", "test": "go test ./...", "lint": "go vet ./..."}})
    if (root / "Cargo.toml").exists():
        stacks.append({"name": "rust", "where": "Cargo.toml", "commands": {
            "build": "cargo build", "test": "cargo test", "lint": "cargo clippy"}})
    if (root / "pom.xml").exists():
        stacks.append({"name": "maven", "where": "pom.xml", "commands": {
            "build": "mvn -q compile", "test": "mvn -q test"}})
    gradle = next((n for n in ("build.gradle.kts", "build.gradle") if (root / n).exists()), None)
    if gradle:
        g = "./gradlew" if (root / "gradlew").exists() else "gradle"
        stacks.append({"name": "gradle", "where": gradle, "commands": {
            "build": f"{g} build -x test", "test": f"{g} test"}})
    makefile = root / "Makefile"
    if makefile.exists():
        targets = set(re.findall(r"^([A-Za-z][\w-]*):", makefile.read_text(errors="replace"), re.M))
        cmds = {t: f"make {t}" for t in ("build", "test", "lint") if t in targets}
        if cmds:
            stacks.append({"name": "make", "where": "Makefile", "commands": cmds})
    # Tool runners that sit beside a stack: they fill a missing kind, never replace one (#167).
    hooks = _pre_commit_hooks(root)
    if (root / ".pre-commit-config.yaml").exists():
        stacks.append({"name": "pre-commit", "commands": {"lint": "pre-commit run -a"},
                       "where": ".pre-commit-config.yaml" + (f": {', '.join(hooks[:8])}" if hooks else "")})
    envs = _tox_envs(root)
    if (root / "tox.ini").exists():
        stacks.append({"name": "tox", "commands": {"test": "tox"},
                       "where": "tox.ini" + (f": {', '.join(envs)}" if envs else "")})
    for stack in stacks:
        stack.setdefault("nested", False)
    stacks.sort(key=lambda s: s["nested"])  # stable: order within each group is kept
    return stacks


# A nested build (benchmarks/starter, plugins/x/engine) builds one sub-project, not this one, so
# run:build never falls back to it (#109). Nested test/lint still fill in, as before.
ROOT_ONLY = {"build"}


def commands_for(ctx: Context, stacks: list[dict] | None = None) -> dict[str, tuple[str, str]]:
    """kind -> (command, source). .barq.json "commands" win, then the first stack that has it."""
    out: dict[str, tuple[str, str]] = {}
    for kind, cmd in (ctx.config.get("commands") or {}).items():
        out[kind] = (cmd, ".barq.json")
    if stacks is None:
        stacks = _stacks(ctx.root, files.list_files(ctx.root))
    for stack in stacks:
        for kind, cmd in stack["commands"].items():
            if not (stack.get("nested") and kind in ROOT_ONLY):
                out.setdefault(kind, (cmd, stack["name"]))
    return out


# ---------------------------------------------------------------- info


def op_info(ctx: Context) -> Result:
    all_files = files.list_files(ctx.root)
    langs = Counter(LANGUAGES[f.suffix.lower()] for f in all_files if f.suffix.lower() in LANGUAGES)
    stacks = _stacks(ctx.root, all_files)
    cmds = commands_for(ctx, stacks)
    branch = files._git(["rev-parse", "--abbrev-ref", "HEAD"], ctx.root)
    manifests = sorted(files.rel(f, ctx.root) for f in all_files
                       if (f.name in MANIFEST_NAMES or f.suffix in (".sln", ".slnx", ".csproj"))
                       and not _is_fixture(files.rel(f, ctx.root)))
    lines = [
        f"root: {ctx.root}" + (f"  (git branch: {branch.strip()})" if branch else "  (not a git repo)"),
        f"files: {len(all_files)}",
        "languages: " + (", ".join(f"{name} {n}" for name, n in langs.most_common(6)) or "unknown"),
        "stacks: " + ("; ".join(f"{s['name']} ({s['where']})" for s in stacks) or "none detected"),
        "commands (run:KIND uses these):",
    ]
    for kind in ("build", "test", "lint"):
        cmd, source = cmds.get(kind, ("-", ""))
        lines.append(f"  {kind:<6} {cmd}" + (f"   [{source}]" if source else ""))
    for kind in sorted(set(cmds) - {"build", "test", "lint"}):
        lines.append(f"  {kind:<6} {cmds[kind][0]}   [{cmds[kind][1]}]")
    others = [f"{s['name']}: {k}={c}" for s in stacks for k, c in s["commands"].items()
              if cmds.get(k, ("", ""))[0] != c]
    if others:
        lines.append("  also detected: " + "; ".join(others[:6]) +
                     '  (pick one with .barq.json {"commands": {"test": "..."}})')
    if manifests:
        shown = manifests[:15] + ([f"... {len(manifests) - 15} more"] if len(manifests) > 15 else [])
        lines.append("manifests: " + ", ".join(shown))
    custom = sorted((ctx.config.get("ops") or {}).keys())
    if custom:
        lines.append("custom ops (.barq.json): " + ", ".join(custom))
    return Result("info", "\n".join(lines))


# ---------------------------------------------------------------- run


def _execute(cmd: str, cwd: Path, timeout: int) -> tuple[str, int | None, float]:
    # Color settings stay as the caller has them: NO_COLOR=1 turned black's green suite red
    # (#165). Color codes in the output are stripped afterwards by compress.clean.
    env = dict(os.environ, CI="1", DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
    started = time.monotonic()
    # The command runs in its own process group, so a timeout ends the whole tree: killing only
    # the shell left `npx borp`'s node processes running (#271).
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
             else {"start_new_session": True})
    proc = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, **group)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # a grandchild that left the group still holds the pipes
            stdout, stderr = b"", b""
        rc = None
    out = (stdout or b"") + b"\n" + (stderr or b"")
    return out.decode("utf-8", "replace"), rc, time.monotonic() - started


def _kill_tree(proc: subprocess.Popen) -> None:
    """End a timed-out command and everything it started: SIGTERM to its group, then SIGKILL."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()
        return
    import signal

    for sig, grace in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            proc.poll()  # reap the shell, so only live members keep the group
            try:
                os.killpg(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.05)


def op_run(ctx: Context, what: str = "test", cmd: str | None = None, timeout=RUN_TIMEOUT) -> Result:
    seconds = int_arg(timeout, "timeout")
    if cmd is None:
        stacks = _stacks(ctx.root, files.list_files(ctx.root))
        known = commands_for(ctx, stacks)
        nested = [c for s in stacks if s["nested"] for k, c in s["commands"].items() if k == what]
        if what not in known and nested:
            raise OpError(
                f"no '{what}' command at the project root, so barq won't run a sub-project's. "
                "Nested ones: " + "; ".join(nested) +
                f'. Run one with {{"op":"run","cmd":"..."}} or set {{"commands": {{"{what}": "..."}}}} '
                "in .barq.json"
            )
        if what not in known:
            raise OpError(
                f"no '{what}' command detected for this project. Set one in .barq.json: "
                f'{{"commands": {{"{what}": "..."}}}} or pass {{"op":"run","cmd":"..."}}'
            )
        cmd = known[what][0]
        name = what
    else:
        name = cmd if len(cmd) <= 60 else cmd[:57] + "..."
    output, rc, elapsed = _execute(cmd, ctx.root, seconds)
    verdict, details, raw_count = compress.summarize(output, rc)
    status = "TIMED OUT" if rc is None else ("ok" if rc == 0 else f"FAILED (exit {rc})")
    header = (f"$ {cmd}\n{verdict}\n"
              f"[{elapsed:.1f}s, {raw_count} output lines -> {len(details)} shown]")
    body = mask_text(header + ("\n" + "\n".join(details) if details else ""))[0]
    return Result(f"run {name}: {status}", body, ok=rc == 0,
                  baseline=len(output.encode("utf-8")), masked=True)


def parse_run(parts: list[str]) -> dict:
    return {"what": parts[0]} if parts and parts[0] else {}


# ---------------------------------------------------------------- custom ops


def custom_specs(config: dict, builtin: set[str]) -> list[OpSpec]:
    specs = []
    for name, spec in (config.get("ops") or {}).items():
        if name in builtin or not isinstance(spec, dict) or not spec.get("cmd"):
            continue
        template = spec["cmd"]

        def run_custom(ctx: Context, args=None, _template=template, _name=name) -> Result:
            argv = args if isinstance(args, list) else ([] if args is None else [str(args)])
            cmd = _template.replace("{args}", " ".join(shlex.quote(str(a)) for a in argv))
            output, rc, elapsed = _execute(cmd, ctx.root, RUN_TIMEOUT)
            lines = [ln for ln in compress.clean(output).split("\n") if ln.strip()]
            shown = lines[:CUSTOM_MAX_LINES]
            if len(lines) > CUSTOM_MAX_LINES:
                shown.append(f"... {len(lines) - CUSTOM_MAX_LINES} more lines")
            status = "ok" if rc == 0 else ("TIMED OUT" if rc is None else f"FAILED (exit {rc})")
            return Result(f"{_name}: {status} [{elapsed:.1f}s]", mask_text("\n".join(shown))[0],
                          ok=rc == 0, masked=True)

        safety = READ if spec.get("safety") == READ else EXEC
        specs.append(OpSpec(name, run_custom, lambda parts: {"args": parts} if parts else {},
                            safety, f"{name}[:ARG...]",
                            spec.get("description", f"custom op from .barq.json: {template}")))
    return specs


OPS = [
    OpSpec("info", op_info, lambda parts: {}, READ, "info",
           "What this project is: languages, stacks, manifests, and the build/test/lint commands."),
    OpSpec("run", op_run, parse_run, EXEC, "run:test  run:build  run:lint  run:KIND",
           "Run the project's test/build/lint command and return only the verdict, failures and "
           'errors. JSON form takes any command: {"op":"run","cmd":"dotnet test --filter X"}.'),
]
