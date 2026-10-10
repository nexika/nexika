"""What a call reads or writes, and the verdict table: the light part of the classifier.

Read, Edit, Write and the other file tools only need to know where a path lives, so they load
this module and never the command parser (classify.py, shell.py), which is most of a hook's
start-up time (#102). classify.py builds on these helpers and re-exports them by name.
"""
from __future__ import annotations

import copy
import glob
import os
import re

from .paths import UNKNOWN, Where, guarded_inside

ALLOW, PASS, ASK, DENY = "allow", "pass", "ask", "deny"
LEVEL = {ALLOW: 0, PASS: 1, ASK: 2, DENY: 3}

# class: (relaxed, standard, strict)
TABLE = {
    "read": (ALLOW, ALLOW, ALLOW),
    "read-outside": (ALLOW, ALLOW, PASS),
    "read-unknown": (PASS, PASS, PASS),
    "run": (ALLOW, ALLOW, PASS),
    "exec": (PASS, PASS, PASS),
    "write": (ALLOW, PASS, PASS),
    "delete": (ALLOW, PASS, ASK),
    "write-temp": (ALLOW, PASS, PASS),
    "write-memory": (PASS, PASS, PASS),  # read into later sessions: a tainted session asks first
    "write-outside": (PASS, ASK, ASK),
    "delete-outside": (ASK, ASK, DENY),
    "unknown-target": (PASS, ASK, ASK),
    "secret-write": (ASK, ASK, ASK),
    "git-internal": (ASK, ASK, ASK),
    "config-exec": (ASK, ASK, DENY),
    "system": (DENY, DENY, DENY),
    "destroy": (DENY, DENY, DENY),
    "secret-read": (ASK, ASK, DENY),
    "persistence": (DENY, DENY, DENY),
    "force-push-protected": (DENY, DENY, DENY),
    "history-rewrite": (PASS, ASK, ASK),
    "discard": (PASS, ASK, ASK),
    "skip-checks": (PASS, ASK, ASK),
    "remote-irreversible": (ASK, ASK, ASK),
    "download-run": (ASK, ASK, DENY),
    "egress": (PASS, PASS, ASK),
    "egress-risk": (ASK, ASK, ASK),
    "egress-secret": (DENY, DENY, DENY),
    "commit-secret": (ASK, ASK, ASK),
    "commit-secret-file": (DENY, DENY, DENY),
    "remote-shell": (DENY, DENY, DENY),
    "self": (DENY, DENY, DENY),
    "privileged": (ASK, ASK, ASK),
    "dynamic": (ASK, ASK, ASK),
    "risky": (ASK, ASK, ASK),
    "remote-command": (ASK, ASK, ASK),
    "fork-bomb": (DENY, DENY, DENY),
    "unparsed": (ASK, ASK, ASK),
    "error": (ASK, ASK, ASK),
    "rule-ask": (ASK, ASK, ASK),
    "rule-deny": (DENY, DENY, DENY),
}
# A tainted session (text that tried to give orders was read) raises these one level.
TAINT_RAISED = {"egress", "egress-risk", "remote-irreversible", "download-run", "remote-command",
                "write-memory"}
# Refused in every profile: no approval lifts these; the user can only do them outside Claude.
ALWAYS_NO = {cls for cls, verdicts in TABLE.items() if verdicts == (DENY, DENY, DENY)}
# The user's exact approval never lifts these.
NOT_APPROVABLE = {"self", "remote-irreversible"} | ALWAYS_NO
LOCAL_HOSTS = re.compile(r"^(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|::1|\[::1\]|169\.254\.\d+\.\d+|"
                         r"metadata\.google\.internal|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
                         r"172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)$")


class Finding:
    """One thing a call does: a class (what kind of action), a plain reason and the path it touches.
    A plain class: dataclasses loads inspect, a tenth of a light hook's start-up time (#102)."""
    __slots__ = ("cls", "reason", "target")

    def __init__(self, cls: str, reason: str, target: str = ""):
        self.cls, self.reason, self.target = cls, reason, target

    def __eq__(self, other) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return (self.cls, self.reason, self.target) == (other.cls, other.reason, other.target)

    __hash__ = None  # like the dataclass it replaces: mutable, so not hashable

    def __repr__(self) -> str:
        return f"Finding(cls={self.cls!r}, reason={self.reason!r}, target={self.target!r})"


class Arg(str):
    """A word's value, remembering what its substitutions did (read a secret, downloaded ...)."""
    marks: frozenset = frozenset()


def arg(value: str, marks=frozenset()) -> Arg:
    a = Arg(value)
    a.marks = frozenset(marks)
    return a


def joined_marks(args: list[Arg]) -> frozenset:
    out: set = set()
    for a in args:
        out |= getattr(a, "marks", frozenset())
    return frozenset(out)



class Git:
    """Facts about the project's repository, read from .git; git runs only when it must."""

    def __init__(self, root: str):
        self.root = root
        self._dirs: tuple[str, str] | None = None
        self._aliases: dict[str, str] | None = None

    def dirs(self) -> tuple[str, str] | None:
        if self._dirs is None:
            self._dirs = ("", "")
            dot = os.path.join(self.root, ".git")
            try:
                if os.path.isdir(dot):
                    self._dirs = (dot, dot)
                elif os.path.isfile(dot):
                    with open(dot, encoding="utf-8") as fh:
                        gitdir = os.path.join(self.root, fh.read().split("gitdir:", 1)[-1].strip())
                    common = gitdir
                    if os.path.isfile(os.path.join(gitdir, "commondir")):
                        with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as fh:
                            common = os.path.normpath(os.path.join(gitdir, fh.read().strip()))
                    self._dirs = (gitdir, common)
            except OSError:
                pass
        return self._dirs if self._dirs[0] else None

    @staticmethod
    def _ref(path: str, prefix: str) -> str:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read().strip()
        except OSError:
            return ""
        return text[len("ref: " + prefix):] if text.startswith("ref: " + prefix) else ""

    def branch(self) -> str:
        dirs = self.dirs()
        return self._ref(os.path.join(dirs[0], "HEAD"), "refs/heads/") if dirs else ""

    def default(self) -> str:
        dirs = self.dirs()
        if not dirs:
            return ""
        return self._ref(os.path.join(dirs[1], "refs", "remotes", "origin", "HEAD"), "refs/remotes/origin/")

    def aliases(self) -> dict[str, str]:
        if self._aliases is None:
            self._aliases = {}
            files = [os.path.expanduser("~/.gitconfig"), os.path.expanduser("~/.config/git/config")]
            dirs = self.dirs()
            if dirs:
                files.append(os.path.join(dirs[1], "config"))
            for path in files:
                self._aliases.update(read_aliases(path))
        return self._aliases

    def run(self, *args: str) -> str:
        """Read-only git; nothing in the repository's config may make it run a program."""
        return self.try_run(*args) or ""

    def try_run(self, *args: str) -> str | None:
        """Like run, but None when git failed (so an empty answer can be told from an error)."""
        cmd = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "--no-pager", *args]
        env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
        env.pop("GIT_EXTERNAL_DIFF", None)
        import subprocess  # only when git must run: most calls never need it
        try:
            res = subprocess.run(cmd, cwd=self.root, capture_output=True, timeout=5, env=env)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return res.stdout.decode("utf-8", "replace") if res.returncode == 0 else None

    def dirty(self) -> bool:
        return bool(self.run("status", "--porcelain", "--untracked-files=no").strip())


def read_aliases(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    section = ""
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
        elif section == "alias" and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] == '"':
                value = value[1:-1]
            out[key.strip().lower()] = value
    return out


class Ctx:
    def __init__(self, where: Where, cwd: str | None, config: dict | None = None, git: Git | None = None):
        self.where, self.cwd, self.config = where, cwd, config or {}
        self.git = git or Git(where.root)
        self.vars: dict[str, str] = {}
        self.prefix: dict[str, str] = {}  # NAME=value given to the command being judged
        self.args: list[str] | None = []
        self.vars_lost = False
        self.depth = 0
        self.findings: list[Finding] = []
        self.executed: list[list[str]] = []
        self.funcs: dict[str, object] = {}
        self.aliases: dict[str, str] = {}  # aliases this command defined (alias x='...')
        self.marks: set[str] = set()
        self.downloaded: set[str] = set()
        self.written: dict[str, str] = {}  # files this command wrote with known text (scripts it may run)
        self.git_aliases: dict[str, str] = {}
        self.cautious = False  # the session read text that tried to give orders: computed paths ask
        # loop bodies one command may judge word by word, shared with every child: nested loops would
        # multiply the work, and a slow check is no check (#342)
        self.unroll_budget = [64]

    def child(self, marks: bool = False, findings: list | None = None) -> Ctx:
        c = copy.copy(self)
        c.vars = dict(self.vars)
        c.depth = self.depth + 1
        if c.depth > 30:
            from . import shell  # only the command parser makes children, and it has shell loaded
            raise shell.ParseError("commands are nested too deeply")
        if marks:
            c.marks = set()
        if findings is not None:
            c.findings = findings
        return c

    def add(self, cls: str, reason: str, target: str = "") -> None:
        self.findings.append(Finding(cls, reason, target))
        if cls in ("secret-read", "egress-secret"):
            self.marks.add("secret")

    def forget(self, args: bool = False) -> None:
        """Something haris does not follow (a function, eval, source) may have changed the variables."""
        self.vars = {}
        self.vars_lost = True
        if args:
            self.args = None

    def in_project(self) -> bool:
        return self.cwd is not None and (self.cwd + "/").startswith(self.where.root + "/")

    def show(self, path: str | None) -> str:
        if path is None:
            return "an unknown path"
        if path.startswith(self.where.root + "/"):
            return path[len(self.where.root) + 1:]
        if path.startswith(self.where.home + "/"):
            return "~/" + path[len(self.where.home) + 1:]
        return path



# ---------------------------------------------------------------- reading and writing paths


def targets(value: Arg, ctx: Ctx) -> list[tuple[str | None, str | None]]:
    """(resolved path, the folder whose whole content it is) for each path a word can name."""
    if UNKNOWN in value:
        return [(None, None)]
    if not re.search(r"[*?[]", value):
        return [(ctx.where.resolve(value, ctx.cwd), None)]
    pattern = ctx.where.home + value[1:] if value.startswith("~") else str(value)
    if not pattern.startswith("/"):
        if ctx.cwd is None:
            return [(None, None)]
        pattern = ctx.cwd + "/" + pattern
    head, tail = os.path.split(pattern)
    out: list[tuple[str | None, str | None]] = []
    if not re.search(r"[*?[]", head):
        folder = ctx.where.resolve(head or "/", None)
        if folder and tail in ("*", ".*", "*.*"):
            out.append((None, folder))
        elif folder:
            out.append((folder.rstrip("/") + "/_", None))
    for match in sorted(glob.glob(pattern))[:200]:
        out.append((ctx.where.resolve(match, None), None))
    return out or [(None, None)]


PACKAGE_RC = (".npmrc", ".yarnrc.yml")
RC_AUTH = re.compile(r"(?im)_auth|_password|^\s*//|npmauth|^\s*(?:cert|key)file\s*=")
IGNORE_SCRIPTS_ON = re.compile(r"(?im)^\s*ignore-scripts\s*=\s*true\s*$")
IGNORE_SCRIPTS_OFF = re.compile(r"(?im)^\s*ignore-scripts\s*=\s*false\b")
IGNORE_SCRIPTS_OFF_REASON = ("Turns off ignore-scripts in {path}: packages' install scripts would run "
                             "again on the next install.")


def public_rc(path: str | None, ctx: Ctx) -> bool:
    """A project's .npmrc that git tracks and that holds no token is public config, not a secret (#222)."""
    if not path or os.path.basename(path) not in PACKAGE_RC or not path.startswith(ctx.where.root + "/"):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read(65536)
    except (OSError, UnicodeDecodeError):
        return False
    if RC_AUTH.search(text):
        return False
    return ctx.git.try_run("ls-files", "--error-unmatch", "--", path) is not None


def rc_text(path: str | None) -> str:
    try:
        with open(path or "", encoding="utf-8") as fh:
            return fh.read(65536)
    except (OSError, UnicodeDecodeError):
        return ""


def read_paths(values_: list[Arg], ctx: Ctx, verb: str = "reads", meta: bool = False) -> None:
    for value in values_:
        for path, contents in targets(value, ctx):
            path = path or (contents + "/_" if contents else None)
            place = ctx.where.place(path)
            if place == "secret" and public_rc(path, ctx):
                place = "project"
            if place == "unknown":
                ctx.add("read-unknown", f"{verb.capitalize()} a path that is only known when it runs.")
            elif (place == "secret" or (path and place in ("persistence", "system", "home", "outside")
                                        and ctx.where.is_secret(path))) and not meta:
                ctx.add("secret-read", f"{verb.capitalize()} {ctx.show(path)}, which holds secrets (keys, "
                                       f"tokens or "
                                       "passwords), into the conversation.", path)
            elif place in ("project", "memory", "temp", "null", "git", "config-exec", "self") or meta:
                ctx.add("read", f"{verb.capitalize()} {ctx.show(path)}.", path)
            else:
                ctx.add("read-outside", f"{verb.capitalize()} {ctx.show(path)}, outside the project.", path)


WRITE_REASONS = {
    "self": ("self", "{verb} {path}, which is part of haris itself or of what it guards (mizan and the "
                     "Nexika status files). haris does not let Claude change or switch off this protection; "
                     "you can do that yourself."),
    "persistence": ("persistence", "{verb} {path}, which runs code later on its own (at login, on a "
                                   "schedule, "
                                   "in git or in Claude Code). That is how harmful changes stay hidden."),
    "secret": ("secret-write", "{verb} {path}, which holds secrets."),
    "system": ("system", "{verb} {path}, which belongs to the operating system."),
    "config-exec": ("config-exec", "{verb} {path}, which makes your tools run commands (MCP servers, direnv, "
                                   "editor tasks or Claude Code agents)."),
    "git": ("git-internal", "{verb} {path} inside .git; git commands are the safe way to change it."),
    "project": ("write", "{verb} {path} in the project."),
    "memory": ("write-memory", "{verb} {path}, Claude Code's memory for this project."),
    "temp": ("write-temp", "{verb} {path} in a temporary folder."),
    "home": ("write-outside", "{verb} {path}, outside the project."),
    "outside": ("write-outside", "{verb} {path}, outside the project."),
    "unknown": ("unknown-target", "{verb} a path that is only known when it runs, so haris cannot tell "
                                  "where."),
}


# Files a CI runner (GitHub Actions) owns and names in these variables; unset in a developer's shell (#142).
CI_RUNNER_FILES = {"GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY", "GITHUB_PATH"}


def write_paths(values_: list[Arg], ctx: Ctx, verb: str = "writes to") -> None:
    for value in values_:
        ci = [m[8:] for m in getattr(value, "marks", ()) if m.startswith("ci-file:")]
        if ci and value == UNKNOWN:
            ctx.add("write-temp", f"{verb.capitalize()} ${ci[0]}, a file the CI runner owns for this step.")
            continue
        for path, contents in targets(value, ctx):
            path = path or (contents + "/_" if contents else None)
            place = ctx.where.place(path)
            if place == "null":
                continue
            if place == "unknown":
                path, place = named_in_folder(value, ctx) or (path, place)
            if place == "secret" and path and path.startswith(ctx.where.root + "/"):
                place = "project"  # filling in the project's own .env is ordinary; reading secrets is not
            cls, text = WRITE_REASONS[place]
            shown = ctx.show(path).replace(UNKNOWN, "<computed>")
            ctx.add(cls, text.format(verb=verb.capitalize(), path=shown), path or "")


ORDINARY_PLACES = ("project", "temp", "home", "outside")


def named_in_folder(value: str, ctx: Ctx) -> tuple[str, str] | None:
    """(path, place) for a write whose file name alone is computed (`logs/$id.log`, `/tmp/x/b$n.md`):
    the folder is known, so the write is judged by it (#210). None, so haris keeps asking, when the
    folder is computed too (`$DIR/x`, `${a}/../b`), when a name there could run code or hold secrets
    (home, ~/.config, .git, .claude, CI workflows ...), or in a cautious session."""
    if ctx.cautious or re.search(r"[*?[]", value):
        return None
    head, _, name = value.rpartition("/")
    if UNKNOWN in head or UNKNOWN not in name:
        return None
    where = ctx.where
    folder = where.resolve(head or ("/" if value.startswith("/") else "."), ctx.cwd)
    if not folder or folder == where.home or where.holds(folder):
        return None
    probe = folder.rstrip("/") + "/" + name.replace(UNKNOWN, "x")
    for p in (probe, folder.rstrip("/") + "/_"):
        if where.place(p) not in ORDINARY_PLACES or guarded_inside(p, where.root):
            return None
    return folder.rstrip("/") + "/" + name, where.place(probe)
