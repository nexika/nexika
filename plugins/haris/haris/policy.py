"""From findings to one decision: allow, pass, ask or deny, with a plain reason.

    allow  haris approves: only actions it can show are safe (reading, running the project's tests
           and builds), or exactly what you approved
    pass   no objection, but not provably safe: Claude Code's own permission rules decide
    ask    Claude Code asks you first
    deny   refused, with the reason and what to do instead

Settings: your ~/.claude/nexika/haris/config.json may loosen or tighten; a repository's
.haris.json may only tighten (a cloned repo must not be able to switch protection off).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex

from . import targets as c
from .config import (  # noqa: F401  (settings live in config, kept here by name)
    PROFILE_INDEX,
    READ_TOOLS,
    TAINT_TURNS,
    WRITE_TOOLS,
    effective_config,
    normalize,
    project_root,
)
from .paths import UNKNOWN, Where, guarded_inside, memory_folder, under

MCP_DESTRUCTIVE = re.compile(r"(?i)(?:^|[_-])(?:delete|remove|drop|destroy|purge|merge|publish|release|"
                             r"deploy|"
                             r"transfer|revoke|archive|truncate|wipe|reset|terminate|uninstall|pay|charge|refund)"
                             r"(?:[_-]|$)")


CLASS_RANK = {cls: n for n, cls in enumerate(c.TABLE)}  # TABLE lists the classes from mildest up


class Decision:
    """allow, pass, ask or deny, with the class and reason behind it (a plain class, like Finding).
    `unattended` is "passed" or "refused" when an ask was settled because nobody could answer it (#343)."""
    __slots__ = ("verdict", "cls", "reason", "findings", "tainted", "unattended")

    def __init__(self, verdict: str, cls: str, reason: str, findings: list | None = None,
                 tainted: bool = False, unattended: str = ""):
        self.verdict, self.cls, self.reason = verdict, cls, reason
        self.findings = [] if findings is None else findings
        self.tainted = tainted
        self.unattended = unattended

    def __eq__(self, other) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return all(getattr(self, k) == getattr(other, k) for k in self.__slots__)

    __hash__ = None

    def __repr__(self) -> str:
        return "Decision(" + ", ".join(f"{k}={getattr(self, k)!r}" for k in self.__slots__) + ")"


# ---------------------------------------------------------------- settings



# ---------------------------------------------------------------- checking each tool


def findings_for(tool: str, tool_input: dict, ctx: c.Ctx) -> list[c.Finding]:
    # The command parser is loaded only for shell commands; file and web tools need just the path
    # helpers (#102).
    if tool == "Bash":
        from . import classify
        return classify.classify(str(tool_input.get("command") or ""), ctx)
    if tool == "PowerShell":
        from . import powershell
        powershell.classify(str(tool_input.get("command") or ""), ctx)
    elif tool in READ_TOOLS:
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path")
                   or tool_input.get("path") or "")
        if path:
            c.read_paths([c.arg(path)], ctx, "reads", meta=tool in ("Glob", "LS"))
        else:
            ctx.add("read", f"Searches the project ({tool}).")
    elif tool in WRITE_TOOLS:
        write_tool(tool_input, ctx)
    elif tool == "WebFetch":
        web_fetch(str(tool_input.get("url") or ""), ctx)
    elif tool == "WebSearch":
        from . import secrets
        if secrets.has_secret(str(tool_input.get("query") or "")):
            ctx.add("egress-secret", "The web search contains what looks like a secret; it would be sent "
                                     "to the "
                                     "search engine.")
        else:
            ctx.add("egress", "Searches the web.")
    elif tool.startswith("mcp__"):
        mcp_tool(tool, tool_input, ctx)
    return ctx.findings


def write_tool(tool_input: dict, ctx: c.Ctx) -> None:
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    c.write_paths([c.arg(path or c.UNKNOWN)], ctx, "writes to")
    from . import secrets
    text = "\n".join(str(tool_input.get(k) or "") for k in ("content", "new_string", "new_source"))
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            text += "\n" + str(edit.get("new_string") or "")
    if os.path.basename(path) == ".npmrc":
        resolved = ctx.where.resolve(path, ctx.cwd)
        before = c.rc_text(resolved)
        old = "\n".join(str(tool_input.get(k) or "") for k in ("old_string",))
        dropped = c.IGNORE_SCRIPTS_ON.search(before) and (
            ("content" in tool_input and not c.IGNORE_SCRIPTS_ON.search(text))
            or ("ignore-scripts" in old and not c.IGNORE_SCRIPTS_ON.search(text)))
        if dropped or c.IGNORE_SCRIPTS_OFF.search(text):
            ctx.add("risky", c.IGNORE_SCRIPTS_OFF_REASON.format(path=os.path.basename(path)))
    if any(p.search(text) for p in secrets.PATTERNS):
        ctx.add("secret-write", f"Writes what looks like a real key or token into "
                                f"{os.path.basename(path)}. Load it "
                                "from an environment variable or a secret store instead.")


def web_fetch(url: str, ctx: c.Ctx) -> None:
    from urllib.parse import urlsplit

    from . import secrets
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        ctx.add("unparsed", "haris could not read this web address.")
        return
    if (parts.query and secrets.has_secret(parts.query)) or parts.password:
        ctx.add("egress-secret", f"The address sends what looks like a secret to {host}.")
    elif c.LOCAL_HOSTS.match(host):
        ctx.add("risky", f"Fetches {host}, an address on this computer or its private network (where cloud "
                         "login keys can be read).")
    else:
        ctx.add("egress", f"Fetches a page from {host}.")


def mcp_tool(tool: str, tool_input: dict, ctx: c.Ctx) -> None:
    parts = tool.split("__", 2)
    server, name = (parts[1] if len(parts) > 1 else "?"), parts[-1]
    payload = json.dumps(tool_input, ensure_ascii=False)[:20000]
    from . import secrets
    if secrets.has_secret(payload):
        ctx.add("egress-secret", f"The request to {server} contains what looks like a secret.")
    elif MCP_DESTRUCTIVE.search(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)):
        ctx.add("remote-irreversible", f"The tool {name} ({server}) deletes, merges, publishes or pays for "
                                       "something.")
    else:
        ctx.add("egress", f"Uses the tool {name} ({server}).")


# ---------------------------------------------------------------- user rules and approvals


def matches(rule: list[str], argv: list[str]) -> bool:
    """A user rule like `terraform apply` matches a command that starts with those words."""
    if len(argv) < len(rule):
        return False
    return all(fnmatch.fnmatchcase(str(a), w) for a, w in zip(argv[:len(rule)], rule, strict=True))


def rule_findings(cfg: dict, executed: list[list[str]]) -> list[c.Finding]:
    out = []
    for verdict in ("deny", "ask"):
        for rule in cfg.get(verdict, []):
            try:
                words = shlex.split(rule)
            except ValueError:
                continue
            if words and any(matches(words, argv) for argv in executed):
                reason = f"Your haris settings say to {verdict} about `{rule}`."
                out.append(c.Finding(f"rule-{verdict}", reason))
    return out


# What a path approval may lift: never persistence, system folders, destroying or sending secrets.
APPROVAL_LIFTS = {
    "read": {"read-outside", "read-unknown", "secret-read"},
    "write": {"write", "write-temp", "write-outside", "delete", "delete-outside", "secret-write",
              "git-internal", "config-exec"},
}


def approved(finding: c.Finding, command: str, approvals: list[dict]) -> bool:
    if finding.cls in c.NOT_APPROVABLE:
        return False
    for a in approvals:
        value = str(a.get("value") or "")
        if not value:
            continue
        if a.get("kind") == "command" and command and normalize(command) == value:
            return True
        if finding.cls in APPROVAL_LIFTS.get(str(a.get("kind")), ()) and finding.target:
            if value.endswith("/") and guarded_inside(finding.target, value):
                continue  # a folder you approved never covers its git hooks, CI or Claude settings
            if finding.target == value or (value.endswith("/") and finding.target.startswith(value)):
                return True
    return False


# ---------------------------------------------------------------- decision


def decide(event: dict, cfg: dict, session: dict | None = None,
           approvals: list[dict] | None = None) -> Decision:
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = os.path.realpath(str(event.get("cwd") or os.getcwd()))
    root = project_root(cwd)
    memory = memory_folder(str(event.get("transcript_path") or ""))
    session = session or {}
    tainted = int(session.get("taint") or 0) > 0
    ctx = c.Ctx(Where(root, cfg.get("secret_paths"), memory), cwd, cfg)
    ctx.cautious = tainted
    findings = list(findings_for(tool, tool_input, ctx))
    findings += rule_findings(cfg, ctx.executed)
    if not findings:
        return Decision(c.PASS, "", "")
    command = str(tool_input.get("command") or "") if tool in ("Bash", "PowerShell") else ""
    approvals = list(approvals or []) + [{"kind": "command",
                                          "value": normalize(a)} for a in cfg.get("allow", [])]
    index = PROFILE_INDEX.get(cfg.get("profile", "standard"), 1)
    best: tuple[c.Finding, str] | None = None
    asked: list[c.Finding] = []
    for f in findings:
        verdict = c.TABLE.get(f.cls, (c.ASK,) * 3)[index]
        if tainted and f.cls in c.TAINT_RAISED:
            verdict = {c.ALLOW: c.PASS, c.PASS: c.ASK, c.ASK: c.DENY}.get(verdict, verdict)
        if verdict != c.ALLOW and approved(f, command, approvals):
            verdict = c.ALLOW
        if verdict == c.ASK:
            asked.append(f)
        # On a tie the more telling step speaks: the script run, not the `cd` before it (#226).
        if best is None or (c.LEVEL[verdict], CLASS_RANK.get(f.cls, 0)) > \
                (c.LEVEL[best[1]], CLASS_RANK.get(best[0].cls, 0)):
            best = (f, verdict)
    finding, verdict = best
    away = str(cfg.get("unattended_why") or "")
    if verdict == c.ASK and away:  # nobody can answer: pass a reversible change in the project, or refuse
        from . import unattended
        if not tainted and unattended.may_pass(asked, findings, lambda p: restorable(p, ctx)):
            return Decision(c.PASS, finding.cls, readable(unattended.PASS_NOTE.format(why=away) + " "
                                                          + finding.reason), findings, tainted, "passed")
        return Decision(c.DENY, finding.cls, readable(finding.reason + unattended.DENY_NOTE.format(why=away)),
                        findings, tainted, "refused")
    reason = finding.reason
    if tainted and finding.cls in c.TAINT_RAISED and verdict in (c.ASK, c.DENY):
        reason += (" (Raised because this session read text that tried to give Claude orders: "
                   f"{session.get('taint_reason') or 'see /haris:why'}.)")
    if verdict == c.ASK and finding.cls == "write-outside" and finding.target:
        folder, count = shared_folder(finding.target, session.get("outside_asks"), ctx.where)
        if count > 1:
            reason += (f" This is the {ordinal(count)} ask about writes in {ctx.show(folder)}/ in this "
                       "session.")
        folder = folder or keepable_folder(finding.target, ctx.where)
        if folder:
            reason += (" To stop haris asking about writes there in this project, the user can type: "
                       f"/haris:allow --project write {folder}/")
    if verdict == c.DENY and finding.cls == "self":
        reason += (" Only you can change haris, outside Claude: edit ~/.claude/nexika/haris/config.json "
                   "or use /plugin.")
    elif verdict == c.DENY and finding.cls in c.ALWAYS_NO:
        reason += (" haris never lets this through, not even with /haris:allow; only you can do it, "
                   "outside Claude.")
    elif verdict == c.DENY and finding.cls not in c.NOT_APPROVABLE:
        if command:
            reason += (" If the user wants this anyway, they can type: "
                       f"/haris:allow {normalize(command)[:300]}")
        elif finding.target:
            kind = "write" if tool in WRITE_TOOLS else "read"
            reason += f" If the user wants this anyway, they can type: /haris:allow {kind} {finding.target}"
    return Decision(verdict, finding.cls, readable(reason), findings, tainted)


def inside_project(path: str, where: Where) -> bool:
    """An ordinary place in this project itself: not the project folder as a whole, .git, CI or tool
    settings that run commands (.github, .claude, .husky ...), another worktree, or a secret."""
    path = path.rstrip("/")
    if path == where.root or not under(path, where.root) or where.place(path) != "project":
        return False
    if any(under(path, t) or under(t, path) for t in where.trees()[1:]):
        return False
    top = path[len(where.root) + 1:].split("/")[0]
    return not guarded_inside(path + "/", where.root) and top != ".github"


# Folders a build or an install makes again: deleting one loses nothing (#343).
REGENERATED = {"build", "dist", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
               ".tox", "target", "coverage", "htmlcov", ".next", ".nuxt", ".turbo", ".parcel-cache"}


def restorable(path: str, ctx: c.Ctx) -> bool:
    """A delete target that git or a rebuild gives back, checked on disk now (#343): a file git tracks
    with no uncommitted change, or a build folder (REGENERATED) with nothing tracked or a repository in
    it. Never a pattern (`find -name`, a glob), a path that does not exist yet, or a link."""
    where = ctx.where
    raw = path.rstrip("/")
    if not raw or raw.endswith("/_") or UNKNOWN in raw or any(ch in raw for ch in "*?["):
        return False
    if not inside_project(raw, where) or os.path.islink(raw) or os.path.realpath(raw) != raw:
        return False
    git = ctx.git
    if os.path.isfile(raw):
        tracked = git.try_run("ls-files", "--", raw)
        clean = git.try_run("status", "--porcelain", "--ignored", "--untracked-files=all", "--", raw)
        return bool(tracked and tracked.strip()) and clean == ""
    if os.path.isdir(raw) and os.path.basename(raw) in REGENERATED:
        return git.try_run("ls-files", "--", raw) == "" and not os.path.lexists(os.path.join(raw, ".git"))
    return False


OUTSIDE_ASKS_KEPT = 50


def remember_ask(data: dict, decision: Decision) -> bool:
    """Note in the session's data the folder of a write outside the project that was asked about, so
    the next ask there can offer the folder they share (#210). True when `data` changed."""
    if decision.verdict != c.ASK or decision.cls != "write-outside":
        return False
    target = next((f.target for f in decision.findings if f.cls == "write-outside" and f.target), "")
    if not target:
        return False
    earlier = [d for d in data.get("outside_asks") or [] if isinstance(d, str)]
    data["outside_asks"] = (earlier + [os.path.dirname(target)])[-OUTSIDE_ASKS_KEPT:]
    return True


def shared_folder(target: str, earlier, where: Where) -> tuple[str, int]:
    """The deepest folder that holds `target` and a folder asked about earlier in the session, and is
    fit for a lasting approval; with how many asks (this one included) fell in it. ("", 0) if none."""
    earlier = [f for f in earlier if isinstance(f, str) and f.startswith("/")] \
        if isinstance(earlier, list) else []
    here = os.path.dirname(target)
    best = ""
    for folder in earlier:
        common = os.path.commonpath([here, folder])
        if len(common) > len(best) and ordinary_folder(common, where):
            best = common
    if not best:
        return "", 0
    return best, 1 + sum(1 for f in earlier if under(f, best))


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def ordinary_folder(folder: str, where: Where) -> bool:
    """A folder one may approve writes in for good: not home, a parent of the project, Claude Code's
    own folder or a protected place."""
    return bool(folder) and not (where.critical(folder) or under(folder, where.home + "/.claude")
                                 or where.place(folder + "/_") not in ("home", "outside"))


def keepable_folder(target: str, where: Where) -> str:
    """The folder to offer for a lasting approval of writes outside the project: the target's git
    checkout, or the folder it is in; "" when that would be too broad (home, a parent of the project,
    Claude Code's own folder) or is not an ordinary place."""
    folder = probe = os.path.dirname(target)
    while probe not in ("/", "", where.home) and not os.path.exists(probe + "/.git"):
        probe = os.path.dirname(probe)
    if probe not in ("/", "", where.home):
        folder = probe
    return folder if ordinary_folder(folder, where) else ""


CONTROL = re.compile(r"[\x01-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def readable(text: str) -> str:
    """Text fit to show: a value haris could not know (computed by `...` or $(...)) reads <computed>,
    and control characters (terminal escapes, direction overrides) are shown as \uFFFD."""
    return CONTROL.sub("\uFFFD", text.replace(UNKNOWN, "<computed>"))
