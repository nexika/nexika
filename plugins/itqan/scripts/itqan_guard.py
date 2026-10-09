#!/usr/bin/env python3
"""itqan guard: a risk-based PreToolUse hook.

Normal work is never interrupted: the guard is silent unless an action is risky.
  ask  -> Claude Code asks the user (risky but sometimes intended)
  deny -> refused with a reason Claude can act on (dangerous)

Reads the PreToolUse JSON on stdin; prints a decision JSON only when not allowing.
Never fails the session: any internal error means "allow".
"""
from __future__ import annotations

import json
import os
import sys

# ---------------------------------------------------------------- haris (the fast path: json and os only)

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
QUALITY_RULES = {"edit-secret-file", "edit-lock-file", "write-secret", "skip-hooks"}


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _haris_plugin_enabled(cwd: str) -> bool:
    """False when Claude Code's settings turn the haris plugin off (/plugin disable): user settings,
    then the project's, then the project's local settings, as Claude Code layers them."""
    config_dir = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
    files = [os.path.join(config_dir, "settings.json")]
    folder, project = os.path.abspath(cwd or "."), []
    while True:
        project = [os.path.join(folder, ".claude", "settings.json"),
                   os.path.join(folder, ".claude", "settings.local.json")]
        if any(os.path.isfile(f) for f in project) or os.path.exists(os.path.join(folder, ".git")):
            break
        parent = os.path.dirname(folder)
        if parent == folder:
            project = []
            break
        folder = parent
    enabled = True
    for path in files + project:
        data = _read_json(path)
        plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
        if isinstance(plugins, dict):
            for key, value in plugins.items():
                if str(key).split("@", 1)[0] == "haris" and isinstance(value, bool):
                    enabled = value
    return enabled


def haris_active(event: dict) -> bool:
    """haris, Nexika's protection plugin, really guards this session: it marked the session, it is on
    (not watching, not off) and the plugin is not disabled. It then covers the safety rules."""
    session = str(event.get("session_id") or "")
    if not session or len(session) > 80 or not all(ch.isalnum() or ch in "_-" for ch in session):
        return False
    home = os.path.expanduser(os.environ.get("HARIS_HOME") or "~/.claude/nexika/haris")
    if not os.path.isfile(os.path.join(home, "active", session)):
        return False
    if os.path.isfile(os.path.join(home, "config.json")):
        config = _read_json(os.path.join(home, "config.json"))
        mode = config.get("mode", "on") if isinstance(config, dict) else "invalid"
        if mode in ("off", "watch") or not isinstance(mode, str):
            return False  # haris is only watching or switched off: keep this guard on
    return _haris_plugin_enabled(str(event.get("cwd") or os.getcwd()))


def needs_quality_check(event: dict) -> bool:
    """Whether a call can hit one of the quality-only rules that itqan keeps beside haris."""
    tool = event.get("tool_name", "")
    if tool in EDIT_TOOLS:
        return True
    command = str((event.get("tool_input") or {}).get("command") or "")
    return tool in ("Bash", "PowerShell") and "git" in command and (
        "--no-verify" in command or "SKIP=" in command
        or any(w[:1] == "-" and w[1:2] != "-" and "n" in w for w in command.split()))


if __name__ == "__main__":
    try:
        EVENT = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        sys.exit(0)
    if not isinstance(EVENT, dict) or (haris_active(EVENT) and not needs_quality_check(EVENT)):
        sys.exit(0)  # haris covers this call: leave before loading anything else
else:
    EVENT = None

import datetime  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path, PurePath  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itqan_files  # noqa: E402
import itqan_secrets  # noqa: E402

DEFAULT_PROTECTED = ["main", "master", "develop", "production", "stable", "release/*"]

# The family's shared secret shapes (common/secrets.py), so the guard and the redactor agree on what
# a secret is.
SECRET_PATTERNS = itqan_secrets.PATTERNS
SECRET_FILE = re.compile(r"(^|/)(\.env(\.[\w-]+)?|\.pypirc|\.netrc|[^/]*\.(pem|key|p12|pfx)"
                         r"|id_(rsa|ed25519|ecdsa|dsa))$")
SECRET_FILE_OK = re.compile(r"\.(example|sample|template|dist)$")
LOCK_FILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "poetry.lock", "uv.lock",
    "Pipfile.lock", "Cargo.lock", "packages.lock.json", "composer.lock", "Gemfile.lock", "go.sum",
}
SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\n)\s*")
HOME_TARGETS = {"/", "/*", "~", "~/", "*", "$HOME", "${HOME}"}


# ---------------------------------------------------------------- helpers


def data_home() -> Path:
    return Path(os.environ.get("ITQAN_HOME") or Path.home() / ".claude" / "nexika" / "itqan")


def load_config(cwd: Path) -> dict:
    for folder in (cwd, *cwd.parents):
        path = folder / ".itqan.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                return {}
        if (folder / ".git").exists():
            break
    return {}


def _git(cwd: Path, *args: str) -> str:
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.decode("utf-8", "replace") if res.returncode == 0 else ""


def project_root(cwd: Path) -> Path:
    top = _git(cwd, "rev-parse", "--show-toplevel").strip()
    return Path(top).resolve() if top else cwd.resolve()


def _branch_matches(branch: str, patterns: list[str]) -> bool:
    return any(branch == p or PurePath(branch).match(p) for p in patterns)


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _strip_env(words: list[str]) -> tuple[str, list[str]]:
    """Leading `env` and `NAME=value` words removed; returns pre-commit's SKIP value and the rest."""
    skip, i = "", 0
    while i < len(words) and (words[i] == "env" or ENV_ASSIGN.match(words[i])):
        if words[i].startswith("SKIP="):
            skip = words[i][5:]
        i += 1
    return skip, words[i:]


def _skip_env_reason(skip: str) -> str:
    return f"`SKIP={skip} git commit` skips pre-commit hooks ({skip}), like `--no-verify`."


def _is_secret_file(path: str) -> bool:
    norm = path.replace("\\", "/")
    return bool(SECRET_FILE.search(norm)) and not SECRET_FILE_OK.search(norm)


def find_secret(text: str) -> str | None:
    """A short, non-revealing preview of the first secret-looking value, or None."""
    for pattern in SECRET_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)[:6] + "..."
    return None


# ---------------------------------------------------------------- Bash rules


def _check_rm(words: list[str], cwd: Path, root: Path):
    if not words or Path(words[0]).name != "rm":
        return None
    short = "".join(w[1:] for w in words[1:] if w.startswith("-") and not w.startswith("--"))
    if "r" not in short.lower() and "--recursive" not in words:
        return None
    for t in (w for w in words[1:] if not w.startswith("-")):
        if t in HOME_TARGETS or t.startswith(("~/", "$HOME/", "${HOME}/")):
            return "deny", "rm-dangerous-target", f"`rm -r {t}` would delete far more than the project."
        resolved = (cwd / t).resolve()
        if resolved == root:
            return "deny", "rm-project-root", f"`rm -r {t}` would delete the whole project."
        try:
            resolved.relative_to(root)
        except ValueError:
            return ("deny", "rm-outside-project",
                    f"`rm -r {t}` targets {resolved}, outside the project ({root}).")
    return None


def _check_push(rest: list[str], cwd: Path, protected: list[str]):
    force = any(a in ("-f", "--force", "--force-with-lease", "--force-if-includes")
                or a.startswith("--force-with-lease=") for a in rest)
    positional = [a for a in rest if not a.startswith("-")]
    refspecs = positional[1:]
    force = force or any(r.startswith("+") for r in refspecs)
    if force:
        current = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()
        targets = [r.lstrip("+").split(":")[-1] for r in refspecs] or [current]
        hit = [t for t in targets if t and _branch_matches(t, protected)]
        if hit:
            return ("deny", "force-push-protected",
                    f"Force-pushing to protected branch '{hit[0]}' rewrites shared history. "
                    "Push to a feature branch and open a pull request instead.")
    if "--no-verify" in rest:
        return "ask", "skip-hooks", "`git push --no-verify` skips the repository's push hooks."
    return None


COMMIT_VALUE_SHORT = set("mFCct")  # short options of `git commit` that take a value
COMMIT_VALUE_LONG = {"--message", "--file", "--reuse-message", "--reedit-message", "--template",
                     "--author", "--date", "--cleanup", "--fixup", "--squash", "--trailer"}


def _commit_skips_hooks(rest: list[str]) -> bool:
    """`git commit` arguments with `-n`/`--no-verify`, also inside a cluster such as `-nm` or `-anm`.
    A cluster is read left to right up to the first letter that takes a value: `-mn` is `-m "n"`."""
    i = 0
    while i < len(rest):
        word = rest[i]
        i += 1
        if word == "--":
            break
        if word == "--no-verify":
            return True
        if word in COMMIT_VALUE_LONG:
            i += 1
        elif word.startswith("-") and not word.startswith("--"):
            for pos, ch in enumerate(word[1:], start=1):
                if ch == "n":
                    return True
                if ch in COMMIT_VALUE_SHORT:
                    i += pos == len(word) - 1  # the value is the next word
                    break
    return False


def _check_commit(rest: list[str], cwd: Path):
    if _commit_skips_hooks(rest):
        return "ask", "skip-hooks", "`git commit --no-verify` skips pre-commit checks."
    all_flag = any(a in ("-a", "--all") or (a.startswith("-") and not a.startswith("--") and "a" in a)
                   for a in rest)
    diff = _git(cwd, "diff", "--cached", "-U0")
    if all_flag:
        diff += _git(cwd, "diff", "-U0")
    files = re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)
    secret_files = [f for f in files if _is_secret_file(f)]
    if secret_files:
        return ("deny", "commit-secret-file",
                f"This commit includes {secret_files[0]}, which usually holds secrets. "
                f"Unstage it (git restore --staged {secret_files[0]}) and add it to .gitignore.")
    added = "\n".join(ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    found = find_secret(added)
    if found:
        return ("deny", "commit-secret",
                f"The staged changes contain what looks like a secret ({found}). Remove it, load it "
                "from an environment variable or a secret store, then commit.")
    return None


def _check_git(words: list[str], cwd: Path, config: dict):
    skip, words = _strip_env(words)
    if len(words) < 2 or Path(words[0]).name != "git":
        return None
    args = words[1:]
    while len(args) > 1 and args[0] in ("-C", "-c"):
        args = args[2:]
    if not args:
        return None
    sub, rest = args[0], args[1:]
    protected = (config.get("guard") or {}).get("protected_branches", DEFAULT_PROTECTED)

    if sub == "push":
        return _check_push(rest, cwd, protected)
    if sub == "commit":
        decision = _check_commit(rest, cwd)
        if skip and not (decision and decision[0] == "deny"):
            return "ask", "skip-hooks", _skip_env_reason(skip)
        return decision
    if sub == "add":
        secret = [a for a in rest if not a.startswith("-") and _is_secret_file(a)]
        if secret:
            return "ask", "add-secret-file", f"`git add {secret[0]}`: this file usually holds secrets."
    if sub == "reset" and "--hard" in rest:
        dirty = _git(cwd, "status", "--porcelain").strip()
        if dirty:
            n = len(dirty.splitlines())
            return "ask", "reset-hard-dirty", f"`git reset --hard` would discard {n} uncommitted change(s)."
    if sub == "clean" and any(a.startswith("-") and not a.startswith("--") and "f" in a for a in rest):
        return "ask", "git-clean", "`git clean -f` permanently deletes untracked files."
    discards = (sub == "checkout" and "." in rest) or (sub == "restore" and "." in rest
                                                         and "--staged" not in rest)
    if discards and _git(cwd, "diff", "--name-only").strip():
        return "ask", "discard-changes", f"`git {sub} .` discards all unstaged changes."
    if sub == "branch" and "-D" in rest:
        return "ask", "branch-force-delete", "`git branch -D` deletes a branch even if it is not merged."
    return None


def skip_hooks(command: str):
    """Only the quality rule about skipping the repository's hooks (`--no-verify`, `SKIP=`)."""
    for segment in SEGMENT_SPLIT.split(command):
        skip, words = _strip_env(_words(segment.strip()))
        if len(words) < 2 or Path(words[0]).name != "git":
            continue
        args = words[1:]
        while len(args) > 1 and args[0] in ("-C", "-c"):
            args = args[2:]
        if args and args[0] == "commit" and skip:
            return "ask", "skip-hooks", _skip_env_reason(skip)
        if args and args[0] == "commit" and _commit_skips_hooks(args[1:]):
            return "ask", "skip-hooks", "`git commit --no-verify` skips pre-commit checks."
        if args and args[0] == "push" and "--no-verify" in args:
            return "ask", "skip-hooks", "`git push --no-verify` skips the repository's push hooks."
    return None


_ASK_PATTERNS = [
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?((ba|z|da)?sh\b|"
                r"(python[\d.]*|perl|ruby|node)(\s+-)?\s*($|[;&|)]))"), "pipe-to-shell",
     "Downloads a script and runs it without review."),
    (re.compile(r"\bchmod\s+(-R\s+)?0?777\b"), "chmod-777", "Makes files writable by everyone."),
    (re.compile(r"(?i)\b(drop\s+(database|schema|table)|truncate\s+table)\b"), "sql-drop",
     "Drops or truncates database objects."),
    (re.compile(r"\bdotnet\s+ef\s+database\s+drop\b|\bprisma\s+migrate\s+reset\b|"
                r"\brails\s+db:(drop|reset)\b|\bmanage\.py\s+flush\b"), "db-reset",
     "Deletes the database."),
    (re.compile(r"\bterraform\s+destroy\b|\bterraform\s+apply\b.*-auto-approve|\bkubectl\s+delete\b|"
                r"\bhelm\s+uninstall\b"), "infra-destroy", "Destroys infrastructure or cluster resources."),
    (re.compile(r"\b(npm|pnpm|yarn)\s+publish\b|\bdotnet\s+nuget\s+push\b|\btwine\s+upload\b|"
                r"\bcargo\s+publish\b|\b(hatch|uv|poetry|flit)\s+publish\b"), "publish-package",
     "Publishes a package to a public registry."),
    (re.compile(r"(^|[\s;&|(])sudo\s"), "sudo", "Runs a command with administrator rights."),
]


SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
SEARCH_TOOLS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}


def _shell_script(words: list[str]) -> str | None:
    """The script of `bash -c "..."` (also `-lc`, `-ec`), checked like a command of its own."""
    if Path(words[0]).name not in SHELLS:
        return None
    for i, word in enumerate(words[1:-1], start=1):
        if word.startswith("-") and not word.startswith("--") and "c" in word:
            return words[i + 1]
    return None


def _is_search(segment: str) -> bool:
    words = _words(segment.strip())
    return bool(words) and (Path(words[0]).name in SEARCH_TOOLS or words[:2] == ["git", "grep"])


def check_bash(command: str, cwd: Path, config: dict, depth: int = 0):
    root = project_root(cwd)
    for segment in SEGMENT_SPLIT.split(command):
        for piece in segment.split("|"):
            words = _words(piece.strip())
            if not words:
                continue
            decision = _check_rm(words, cwd, root) or _check_git(words, cwd, config)
            script = _shell_script(words) if depth < 3 else None
            if not decision and script:
                decision = check_bash(script, cwd, config, depth + 1)
            if decision:
                return decision
    for pattern, rule, reason in _ASK_PATTERNS:
        if rule == "sql-drop":  # SQL words inside a search pattern drop nothing
            hit = any(pattern.search(s) and not _is_search(s) for s in SEGMENT_SPLIT.split(command))
        else:
            hit = pattern.search(command)
        if hit:
            return "ask", rule, reason
    return None


# ---------------------------------------------------------------- file-edit rules


def check_edit(tool_input: dict):
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    norm = "/" + path.replace("\\", "/").lstrip("/")
    name = PurePath(norm).name
    if "/.git/" in norm:
        return "deny", "git-internals", f"{path} is inside .git; use git commands instead."
    if _is_secret_file(norm):
        return "ask", "edit-secret-file", f"{name} usually holds secrets; confirm this edit."
    if name in LOCK_FILES:
        return ("ask", "edit-lock-file",
                f"{name} is generated by the package manager; change dependencies with it instead.")
    new_text = "\n".join(str(tool_input.get(k) or "") for k in ("content", "new_string", "new_source"))
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            new_text += "\n" + str(edit.get("new_string") or "")
    found = find_secret(new_text)
    if found:
        return ("ask", "write-secret",
                f"The new content of {name} contains what looks like a secret ({found}).")
    return None


# ---------------------------------------------------------------- entry point


def decide(event: dict) -> tuple[str, str, str] | None:
    cwd = Path(event.get("cwd") or os.getcwd())
    config = load_config(cwd)
    if os.environ.get("ITQAN_GUARD", "").lower() == "off" or (config.get("guard") or {}).get("mode") == "off":
        return None
    beside_haris = haris_active(event)
    if beside_haris and not needs_quality_check(event):
        return None
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    decision = None
    if tool in ("Bash", "PowerShell"):
        command = str(tool_input.get("command") or "")
        decision = skip_hooks(command) if beside_haris else check_bash(command, cwd, config)
    elif tool in EDIT_TOOLS:
        decision = check_edit(tool_input)
    if decision and beside_haris and decision[1] not in QUALITY_RULES:
        return None  # a safety rule: haris decides it
    return decision


def log_decision(event: dict, decision: tuple[str, str, str]) -> None:
    try:
        tool_input = event.get("tool_input") or {}
        detail = str(tool_input.get("command") or tool_input.get("file_path") or "")
        detail = itqan_secrets.redact(detail)[:200]
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session": str(event.get("session_id") or "")[:8],
            "rule": decision[1], "decision": decision[0], "detail": detail,
            "tool_use_id": str(event.get("tool_use_id") or "")[:80],
        }
        itqan_files.append_jsonl(data_home() / "guard.jsonl", entry)
    except OSError:
        pass


def main() -> int:
    try:
        event = EVENT if EVENT is not None else json.loads(sys.stdin.read() or "{}")
        decision = decide(event)
    except Exception:  # never break the session
        return 0
    if not decision:
        return 0
    verdict, rule, reason = decision
    log_decision(event, decision)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": verdict,
        "permissionDecisionReason": f"itqan guard [{rule}]: {reason}",
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
