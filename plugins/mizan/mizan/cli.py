"""mizan command line: the mod, the status line, the hooks and people all come through here."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, doctor, family, forge, gitinfo, hooks, i18n, render, snapshot

STDIN_LIMIT = 1_000_000
HOOKS = {"session-start": lambda event: hooks.on_session_start(event, helper_path()), "stop": hooks.on_stop}


def helper_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "bin" / "mizan")


def read_stdin() -> dict:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        data = json.loads(sys.stdin.read(STDIN_LIMIT) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def emit(data) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def cmd_status(args) -> int:
    payload = read_stdin() if args.stdin else {}
    if args.cwd:
        payload["cwd"] = args.cwd
    snap = snapshot.build(payload, publish=args.publish)
    if args.json:
        emit(snap)
    else:
        print(render.plain(snap["band"]))
    return 0


def cmd_statusline(args) -> int:
    snap = snapshot.build(read_stdin(), publish=True)
    print(render.ansi(snap["band"]))
    return 0


def _cli_snapshot(cwd: str) -> dict:
    return snapshot.build(snapshot.latest_payload(cwd or os.getcwd()))


def cmd_report(args) -> int:
    snap = _cli_snapshot(args.cwd)
    print(render.plain(snap["band"]))
    print()
    print(render.sections_text(snap["detail"]))
    return 0


def cmd_export(args) -> int:
    emit(_cli_snapshot(args.cwd))
    return 0


def cmd_refresh(args) -> int:
    info = gitinfo.read(args.cwd or os.getcwd())
    try:
        if info:
            forge.refresh(info)
    finally:
        if args.locked:
            forge.release_lock(info["repo"] if info else (args.cwd or ""))
    return 0


def cmd_handoff(args) -> int:
    payload = read_stdin()
    emit(family.handoff(str(payload.get("session") or ""), str(payload.get("transcript") or ""),
                        str(payload.get("cwd") or os.getcwd())))
    return 0


def cmd_proof(args) -> int:
    info = gitinfo.read(args.cwd or os.getcwd())
    proof = family.proof(info.get("repo", "")) if info else {}
    sections = render.proof_view(proof, i18n.lang(), info.get("head", "") if info else "")
    if args.json:
        emit({"available": bool(proof), "sections": sections, "proof": proof})
    else:
        print(render.sections_text(sections))
    return 0


def cmd_doctor(args) -> int:
    found = doctor.run(Path(args.cwd or os.getcwd()), latency=not args.no_latency)
    if args.json:
        emit(found)
    else:
        print(doctor.text(found))
    return doctor.exit_code(found)


def cmd_hook(args) -> int:
    out = HOOKS[args.event](read_stdin())
    if out:
        sys.stdout.write(out + "\n")
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="mizan", description="Keeps a Claude Code session in balance.",
                                  allow_abbrev=False)
    top.add_argument("--version", action="version", version=f"mizan {__version__}")
    sub = top.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", allow_abbrev=False,
                       help="the band (two lines), or the whole snapshot with --json")
    p.add_argument("--json", action="store_true")
    p.add_argument("--stdin", action="store_true", help="read the session's figures as JSON on stdin")
    p.add_argument("--publish", action="store_true", help="also write status/mizan/<session>.json")
    p.add_argument("--cwd")
    p.set_defaults(run=cmd_status)

    p = sub.add_parser("statusline", help="Claude Code statusLine command: its JSON in, two lines out")
    p.set_defaults(run=cmd_statusline)

    p = sub.add_parser("report", help="everything mizan knows, as text")
    p.add_argument("--cwd")
    p.set_defaults(run=cmd_report)

    p = sub.add_parser("export", help="the snapshot as JSON (schema nexika.mizan/1)")
    p.add_argument("--json", action="store_true", required=True)
    p.add_argument("--cwd")
    p.set_defaults(run=cmd_export)

    p = sub.add_parser("refresh", help="ask gh or glab now and update the cache")
    p.add_argument("--cwd")
    p.add_argument("--locked", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(run=cmd_refresh)

    p = sub.add_parser("handoff", help="have hafiz save the handoff note (session, transcript, cwd on stdin)")
    p.set_defaults(run=cmd_handoff)

    p = sub.add_parser("proof", help="the latest itqan proof for this project")
    p.add_argument("--json", action="store_true")
    p.add_argument("--cwd")
    p.set_defaults(run=cmd_proof)

    p = sub.add_parser("doctor", allow_abbrev=False,
                       help="the Nexika plugins installed together: hooks, conflicts, status files, latency")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-latency", action="store_true", help="do not run the hooks to time them")
    p.add_argument("--cwd")
    p.set_defaults(run=cmd_doctor)

    p = sub.add_parser("hook", help=argparse.SUPPRESS)
    p.add_argument("event", choices=sorted(HOOKS))
    p.set_defaults(run=cmd_hook)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.run(args)


def entry() -> None:
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    except Exception as error:  # a hook or the status line must never break the session
        sys.stderr.write(f"mizan: {type(error).__name__}: {error}\n")
        code = 0 if len(sys.argv) > 1 and sys.argv[1] in ("hook", "statusline") else 1
    sys.exit(code)
