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
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import classify as c
from . import powershell, secrets, state
from .paths import UNKNOWN, Where

PROFILE_INDEX = {name: i for i, name in enumerate(c.PROFILES)}
TAINT_TURNS = 3
READ_TOOLS = {"Read", "NotebookRead", "Grep", "Glob", "LS"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
MCP_DESTRUCTIVE = re.compile(r"(?i)(?:^|[_-])(?:delete|remove|drop|destroy|purge|merge|publish|release|"
                             r"deploy|"
                             r"transfer|revoke|archive|truncate|wipe|reset|terminate|uninstall|pay|charge|refund)"
                             r"(?:[_-]|$)")


@dataclass
class Decision:
    verdict: str
    cls: str
    reason: str
    findings: list = field(default_factory=list)
    tainted: bool = False


# ---------------------------------------------------------------- settings


def _strings(value) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def effective_config(root: str) -> dict:
    """Your settings, then the repository's, which can only make haris stricter."""
    user, repo = state.user_config(), state.repo_config(root)
    def known(value, names) -> bool:
        return isinstance(value, str) and value in names

    profile = user.get("profile") if known(user.get("profile"), PROFILE_INDEX) else "standard"
    if known(repo.get("profile"), PROFILE_INDEX) and PROFILE_INDEX[repo["profile"]] > PROFILE_INDEX[profile]:
        profile = repo["profile"]
    mode = user.get("mode") if known(user.get("mode"), ("on", "watch", "off")) else "on"
    turns = user.get("taint_turns", TAINT_TURNS)
    turns = turns if isinstance(turns, int) and 0 <= turns <= 50 else TAINT_TURNS
    repo_turns = repo.get("taint_turns")
    if isinstance(repo_turns, int) and turns < repo_turns <= 50:
        turns = repo_turns
    secret_globs = _strings(user.get("secret_paths"))
    secret_globs += [g if g.startswith("/") else os.path.join(root,
                                                              g) for g in _strings(repo.get("secret_paths"))]
    return {
        "profile": profile, "mode": mode, "taint_turns": turns,
        "ask": _strings(user.get("ask")) + _strings(repo.get("ask")),
        "deny": _strings(user.get("deny")) + _strings(repo.get("deny")),
        "allow": _strings(user.get("allow")),
        "protected_branches": (_strings(user.get("protected_branches"))
                               + _strings(repo.get("protected_branches"))),
        "secret_paths": secret_globs,
        "sources": [p for p, d in (("~/.claude/nexika/haris/config.json", user), (".haris.json", repo)) if d],
    }


def project_root(cwd: str) -> str:
    folder = os.path.realpath(cwd)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    cwd = os.path.realpath(cwd)
    home = os.path.realpath(os.path.expanduser("~"))
    if home == cwd or home.startswith(cwd.rstrip("/") + "/"):
        # Home, / or a folder above home is no project: nothing in it may count as project files.
        return os.path.join(cwd, ".haris-no-project")
    return cwd


def normalize(command: str) -> str:
    return " ".join(command.split())


# ---------------------------------------------------------------- checking each tool


def findings_for(tool: str, tool_input: dict, ctx: c.Ctx) -> list[c.Finding]:
    if tool == "Bash":
        return c.classify(str(tool_input.get("command") or ""), ctx)
    if tool == "PowerShell":
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
    text = "\n".join(str(tool_input.get(k) or "") for k in ("content", "new_string", "new_source"))
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            text += "\n" + str(edit.get("new_string") or "")
    if any(p.search(text) for p in secrets.PATTERNS):
        ctx.add("secret-write", f"Writes what looks like a real key or token into "
                                f"{os.path.basename(path)}. Load it "
                                "from an environment variable or a secret store instead.")


def web_fetch(url: str, ctx: c.Ctx) -> None:
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
    ctx = c.Ctx(Where(root, cfg.get("secret_paths")), cwd, cfg)
    findings = list(findings_for(tool, tool_input, ctx))
    findings += rule_findings(cfg, ctx.executed)
    if not findings:
        return Decision(c.PASS, "", "")
    session = session or {}
    tainted = int(session.get("taint") or 0) > 0
    command = str(tool_input.get("command") or "") if tool in ("Bash", "PowerShell") else ""
    approvals = list(approvals or []) + [{"kind": "command",
                                          "value": normalize(a)} for a in cfg.get("allow", [])]
    index = PROFILE_INDEX.get(cfg.get("profile", "standard"), 1)
    best: tuple[c.Finding, str] | None = None
    for f in findings:
        verdict = c.TABLE.get(f.cls, (c.ASK,) * 3)[index]
        if tainted and f.cls in c.TAINT_RAISED:
            verdict = {c.ALLOW: c.PASS, c.PASS: c.ASK, c.ASK: c.DENY}.get(verdict, verdict)
        if verdict != c.ALLOW and approved(f, command, approvals):
            verdict = c.ALLOW
        if best is None or c.LEVEL[verdict] > c.LEVEL[best[1]]:
            best = (f, verdict)
    finding, verdict = best
    reason = finding.reason
    if tainted and finding.cls in c.TAINT_RAISED and verdict in (c.ASK, c.DENY):
        reason += (" (Raised because this session read text that tried to give Claude orders: "
                   f"{session.get('taint_reason') or 'see /haris:why'}.)")
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


CONTROL = re.compile(r"[\x01-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def readable(text: str) -> str:
    """Text fit to show: a value haris could not know (computed by `...` or $(...)) reads <computed>,
    and control characters (terminal escapes, direction overrides) are shown as \uFFFD."""
    return CONTROL.sub("\uFFFD", text.replace(UNKNOWN, "<computed>"))
