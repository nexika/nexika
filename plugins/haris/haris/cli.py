"""haris command line and hook entry point.

    haris why [-n N]                 the latest asks and refusals here, explained
    haris status                     profile, mode, settings, taint and approvals
    haris audit [--days N] ...       the audit log (commands already redacted)
    haris check [--tool T] COMMAND   what haris would decide (project approvals applied), not run
    haris approvals [--remove V]     approvals you typed (removing one only makes haris stricter)
    haris export --json              the nexika.haris/1 summary for the other Nexika plugins

Approvals are never added here: only what you type in Claude Code (/haris:allow) counts.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

from . import __version__, config, hooks, state

CLASS_HELP = {
    "self": "changes or switches off haris itself; only you can do that, outside Claude",
    "persistence": "writes somewhere that runs code later on its own (shell startup, cron, git hooks, "
                   "settings)",
    "destroy": "would delete far more than one project (home, disk, a parent folder)",
    "system": "changes the operating system or a disk",
    "secret-read": "reads keys, tokens or passwords into the conversation",
    "egress-secret": "sends a secret off this computer",
    "egress-risk": "sends something that may be a secret off this computer",
    "remote-irreversible": "deletes, merges, publishes or deploys something others rely on; always asked",
    "force-push-protected": "rewrites history on a shared branch",
    "history-rewrite": "replaces history on a remote branch",
    "discard": "throws away work that cannot be recovered",
    "download-run": "runs code from the internet without you seeing it first",
    "dynamic": "runs commands haris cannot see in advance",
    "unparsed": "haris could not read the command",
    "remote-shell": "gives someone on the network a shell on this computer",
    "risky": "weakens security, needs high rights, or affects the whole machine",
    "privileged": "runs with administrator rights",
    "write-outside": "writes outside the project",
    "delete-outside": "deletes outside the project",
    "unknown-target": "touches a path that is only known when it runs",
    "config-exec": "changes files that make your tools run commands",
    "git-internal": "edits files inside .git directly",
    "secret-write": "writes into a secret file, or writes a secret into a file",
    "commit-secret": "puts something that looks like a secret into git",
    "commit-secret-file": "commits a file that usually holds secrets",
    "skip-checks": "skips the repository's checks",
    "remote-command": "runs something risky on another machine or in a container",
    "fork-bomb": "would freeze the computer",
    "error": "haris failed while checking, so it asked instead",
    "rule-ask": "matches an ask rule in your settings",
    "rule-deny": "matches a deny rule in your settings",
    "prompt-injection": "a tool's output tried to give Claude orders",
}


def helper_command() -> str:
    return f"python3 {Path(__file__).resolve().parent.parent / 'bin' / 'haris'}"


def _root() -> str:
    return config.project_root(os.getcwd())


def _latest_session(root: str) -> tuple[str, dict]:
    best: tuple[str, dict] = ("", {})
    try:
        files = list((state.home() / "sessions").glob("*.json"))
    except OSError:
        files = []
    for path in files:
        data = state.load_json(path, {})
        if data.get("project") == root and data.get("updated", "") >= best[1].get("updated", ""):
            best = (path.stem, data)
    return best


def _entries(root: str, days: int = 0, decision: str = "", every_project: bool = False) -> list[dict]:
    name = os.path.basename(root)
    start = datetime.datetime.now() - datetime.timedelta(days=days)
    since = start.isoformat(timespec="seconds") if days else ""
    return [e for e in state.read_audit()
            if (every_project or e.get("project") == name) and (not since or e.get("ts", "") >= since)
            and (not decision or e.get("decision") == decision)]


def _approvals(root: str) -> list[dict]:
    session, _ = _latest_session(root)
    if session:
        return state.approvals(session, root)
    return [dict(a, scope="project") for a in state.project_approvals(root)]


def cmd_why(args) -> int:
    from . import policy

    entries = [e for e in _entries(_root(), every_project=args.all) if e.get("decision") in ("ask", "deny",
                                                                                             "taint")]
    if not entries:
        print("haris has not asked about or refused anything here yet.")
        return 0
    for e in entries[-args.n:]:
        verdict = {"ask": "asked", "deny": "refused", "taint": "marked the session"}.get(e.get("decision"),
                                                                                         "")
        print(f"{e.get('ts', '')}  {verdict} ({e.get('class')}): {policy.readable(str(e.get('detail', '')))}")
        print(f"  why: {policy.readable(str(e.get('reason', '')))}")
        if e.get("class") in CLASS_HELP:
            print(f"  meaning: {CLASS_HELP[e['class']]}")
    return 0


def cmd_status(args) -> int:
    root = _root()
    cfg = config.effective_config(root)
    _, data = _latest_session(root)
    print(f"haris {__version__}: {cfg['mode']} (profile {cfg['profile']})")
    print(f"  project: {root}")
    print(f"  settings: {', '.join(cfg['sources']) or 'defaults'}")
    for key in ("ask", "deny", "allow", "protected_branches", "secret_paths"):
        if cfg.get(key):
            print(f"  {key}: {', '.join(cfg[key])}")
    taint = int(data.get("taint") or 0)
    if taint:
        print(f"  session marked for {taint} more message(s): {data.get('taint_reason', '')}")
    for a in _approvals(root):
        print(f"  approved ({a.get('scope', 'session')}): {a.get('kind')} {a.get('value')}")
    week = _entries(root, days=7)
    counts = {k: sum(1 for e in week if e.get("decision") == k) for k in ("ask", "deny", "taint")}
    print(f"  last 7 days here: {counts['deny']} refused, {counts['ask']} asked, {counts['taint']} injection "
          "warnings")
    print(f"  data: {state.home()} (owner-only)")
    return 0


def cmd_audit(args) -> int:
    from . import policy

    entries = _entries(_root(), args.days, args.decision or "", args.all)[-args.limit:]
    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=1))
        return 0
    if not entries:
        print("Nothing in the audit log for this filter.")
    for e in entries:
        print(f"{e.get('ts', '')} {e.get('decision', ''):8} {e.get('class', ''):22} {e.get('tool', '')}: "
              f"{policy.readable(str(e.get('detail', '')))}")
    return 0


def cmd_check(args) -> int:
    from . import policy

    key = {"Bash": "command", "PowerShell": "command", "WebFetch": "url", "WebSearch": "query"}.get(args.tool,
                                                                                                   "file_path")
    event = {"tool_name": args.tool, "tool_input": {key: " ".join(args.command)}, "cwd": os.getcwd()}
    cfg = config.effective_config(_root())
    if args.profile:
        cfg["profile"] = args.profile
    approvals = [dict(a, scope="project") for a in state.project_approvals(_root())]
    decision = policy.decide(event, cfg, None, approvals)
    if args.json:
        findings = [{"cls": f.cls, "reason": f.reason, "target": f.target} for f in decision.findings]
        print(json.dumps({"decision": decision.verdict, "class": decision.cls, "reason": decision.reason,
                          "findings": findings, "approvals_applied": "project"},
                         ensure_ascii=False, indent=1))
        return 0
    if decision.cls:
        print(f"{decision.verdict} ({decision.cls}): {decision.reason}")
    else:
        print(f"{decision.verdict}: no objection; Claude Code's own permission rules decide")
    for f in decision.findings:
        print(f"  - {f.cls}: {f.reason}")
    print(f"  (with this project's {len(approvals)} project approval(s); approvals for one session and a "
          "session's extra caution are not applied)")
    return 0


def cmd_approvals(args) -> int:
    root = _root()
    if args.remove:
        session, _ = _latest_session(root)
        print(f"Removed {state.remove_approval(session, root, config.normalize(args.remove))} approval(s).")
        return 0
    items = _approvals(root)
    if not items:
        print("No approvals. Type /haris:allow <exact command> in Claude Code to approve one.")
    for a in items:
        print(f"{a.get('scope', 'session'):8} {a.get('kind'):8} {a.get('value')}  ({a.get('ts', '')})")
    return 0


def cmd_export(args) -> int:
    root = _root()
    cfg = config.effective_config(root)
    session, data = _latest_session(root)
    recent = [e for e in _entries(root, days=7) if e.get("decision") in ("ask", "deny", "approval")]
    print(json.dumps({
        "schema": "nexika.haris/1", "version": __version__, "profile": cfg["profile"], "mode": cfg["mode"],
        "session": {"id": session, "taint": int(data.get("taint") or 0),
                    "taint_reason": data.get("taint_reason", "")},
        "recent": [{k: e.get(k) for k in ("ts", "decision", "class", "reason",
                                          "detail")} for e in recent[-50:]],
    }, ensure_ascii=False, indent=1))
    return 0


def run_hook(name: str) -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    handlers = {
        "pre-tool-use": hooks.on_pre_tool_use,
        "post-tool-use": hooks.on_post_tool_use,
        "user-prompt-submit": hooks.on_user_prompt_submit,
        "session-start": lambda e: hooks.on_session_start(e, helper_command()),
    }
    try:
        out = handlers[name](event)
    except Exception as exc:  # a broken check asks; the other hooks stay quiet
        if name != "pre-tool-use":
            return 0
        out = json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "ask",
            "permissionDecisionReason": f"haris: an internal error ({type(exc).__name__}) stopped the "
                                        f"check, so it "
                                        "asks you instead."}})
    if out:
        print(out)
    return 0


HOOKS = ("pre-tool-use", "post-tool-use", "user-prompt-submit", "session-start")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "hook" and argv[1] in HOOKS:
        return run_hook(argv[1])  # every tool call runs a hook: skip argparse (#50)
    import argparse

    parser = argparse.ArgumentParser(prog="haris", description="haris: guards against harmful agent actions")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hook")
    p.add_argument("event", choices=HOOKS)
    p = sub.add_parser("why")
    p.add_argument("-n", type=int, default=3)
    p.add_argument("--all", action="store_true", help="every project, not only this one")
    sub.add_parser("status")
    p = sub.add_parser("audit")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--decision", choices=["ask", "deny", "taint", "approval"])
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--tool", default="Bash")
    p.add_argument("--profile", choices=["relaxed", "standard", "strict"])
    p.add_argument("--json", action="store_true")
    p.add_argument("command", nargs="+")
    p = sub.add_parser("approvals")
    p.add_argument("--remove", default="")
    p = sub.add_parser("export")
    p.add_argument("--json", action="store_true")
    sub.add_parser("version")
    args = parser.parse_args(argv)
    if args.cmd == "hook":
        return run_hook(args.event)
    if args.cmd == "version":
        print(__version__)
        return 0
    return {"why": cmd_why, "status": cmd_status, "audit": cmd_audit, "check": cmd_check,
            "approvals": cmd_approvals, "export": cmd_export}[args.cmd](args)


def entry() -> None:
    sys.exit(main())
