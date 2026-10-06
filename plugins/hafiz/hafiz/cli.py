"""hafiz command line and hook entry point."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, capture, card, export, hooks, search, secrets, store, summary

HOOKS = {
    "session-start": lambda event: hooks.on_session_start(event, helper_command()),
    "stop": hooks.on_stop,
    "pre-compact": hooks.on_pre_compact,
    "session-end": hooks.on_session_end,
}
STATUSES = ("open", "done", "solved", "dropped")


def helper_command() -> str:
    return f"python3 {Path(__file__).resolve().parent.parent / 'bin' / 'hafiz'}"


def line_of(item: dict, score: float | None = None) -> str:
    status = f"/{item['status']}" if item.get("status") else ""
    where = item.get("branch") or "-"
    if item.get("scope") == "project":
        where += " (project)"
    lead = f"{score:5.2f} " if score else ""
    commit = f", {item['commit']}" if item.get("commit") else ""
    return (f"{lead}{item['id']} [{item['type']}{status}] {item.get('date', '')[:10]} {where}: {item['text']}"
            f"  ({item.get('source', '')}{commit})")


def _where() -> tuple[Path, Path]:
    cwd = Path.cwd()
    return cwd, store.project_root(cwd)


def cmd_recall(args) -> int:
    cwd, root = _where()
    here = store.branch(cwd)
    branch = args.branch or (here if args.here else "")
    found = search.find(store.Memory(root).all(), " ".join(args.query), args.limit, prefer_branch=here,
                        kind=args.type or "", branch=branch, days=args.days or 0)
    if args.json:
        print(json.dumps([{**i, "score": s} for s, i in found], ensure_ascii=False, indent=1))
        return 0
    if not found:
        print("No matching memory. Try other words (Arabic or English), --type, or a wider --days.")
        return 0
    print(f"{len(found)} memor{'y' if len(found) == 1 else 'ies'} (best first; check the code or the "
          "source line before relying on one):")
    for score, item in found:
        print("  " + line_of(item, score))
    return 0


def cmd_remember(args) -> int:
    cwd, root = _where()
    text = " ".join(args.text).strip()
    if not secrets.drop_private(text).strip():
        print("Nothing to remember (empty or only <private> text).")
        return 2
    memory = store.Memory(root)
    current = card.current_state(memory.dir, store.branch(cwd))
    status = args.status or ("open" if args.type in ("task", "problem") else "")
    item = store.Memory.make(args.type, text, branch=store.branch(cwd), commit=store.head_commit(cwd),
                             session=current.get("session", ""), source="manual", origin="manual",
                             scope="project" if args.project else "branch", status=status)
    memory.upsert([item])
    if secrets.has_secret(text):
        print("Note: a secret was removed before saving.")
    print("Remembered: " + line_of(item))
    return 0


def cmd_list(args) -> int:
    cwd, root = _where()
    branch = store.branch(cwd) if args.here else ""
    items = [i for i in search.newest_first(store.Memory(root).all())
             if search.keep(i, kind=args.type or "", branch=branch, status=args.status or "")]
    if args.json:
        print(json.dumps(items[: args.limit], ensure_ascii=False, indent=1))
        return 0
    shown = f", showing {args.limit}" if len(items) > args.limit else ""
    print(f"{len(items)} memories in {store.project_dir(root)}{shown}")
    for item in items[: args.limit]:
        print("  " + line_of(item))
    return 0


def cmd_forget(args) -> int:
    _, root = _where()
    ids = set(args.ids)
    needle = (args.match or "").lower()
    session = (args.session or "")[:8]
    if not ids and not needle and not session:
        print("Say what to forget: memory ids, --match TEXT or --session ID.")
        return 2

    def match(item: dict) -> bool:
        return bool(item["id"] in ids or (needle and needle in item["text"].lower())
                    or (session and item.get("session", "").startswith(session)))

    memory = store.Memory(root)
    if args.dry_run:
        gone = [i for i in memory.all() if match(i)]
        print(f"Would forget {len(gone)}:")
    else:
        gone = memory.forget(match)
        print(f"Forgot {len(gone)} (automatic capture will not bring them back):")
    for item in gone[:50]:
        print("  " + line_of(item))
    return 0


def cmd_handoff(args) -> int:
    cwd, root = _where()
    folder = store.project_dir(root)
    if args.save:
        if not hooks.save_now(args.session or "", args.transcript or "", str(cwd)):
            print("Nothing saved: give --session and the session's --transcript (a .jsonl under "
                  "~/.claude/projects).", file=sys.stderr)
            return 1
    if args.note is not None:
        state = card.current_state(folder, store.branch(cwd))
        if not state:
            print("No recorded session yet in this project.")
            return 1
        state["note"] = " ".join(secrets.redact(args.note).split())[:600]
        capture.save_state(folder, state)
        card.write_handoff(folder, state)
        export.write_latest(root, state)
    branch = args.branch or store.branch(cwd)
    note = card.read_handoff(folder, branch)
    if not note:
        last = card.last_session(folder, branch)
        note = card.handoff_text(last) if last else ""
    print(note.rstrip() or f"No handoff note yet for branch {branch or '(none)'}.")
    return 0


def cmd_summary(args) -> int:
    _, root = _where()
    try:
        code, out = summary.run(root, args.session or "", args.model, args.lang or "", args.dry_run,
                                args.out or "")
    except ValueError as exc:
        print(exc)
        return 2
    print(out)
    return code


def cmd_export(args) -> int:
    _, root = _where()
    data = export.full(root, args.branch or "", args.limit)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    counts = ", ".join(f"{n} {k}" for k, n in data["counts"].items())
    print(f"{data['schema']} for {data['project']['name']}: {counts}")
    latest = data["latest_session"]
    if latest:
        print(f"latest session {latest['id'][:8]} on {latest['branch'] or '(none)'}: "
              f"{len(latest['open_tasks'])} open tasks, {len(latest['decisions'])} decisions, "
              f"{len(latest['files'])} files")
    print("Use --json for the full contract.")
    return 0


def cmd_status(args) -> int:
    cwd, root = _where()
    memory = store.Memory(root)
    items = memory.all()
    counts = ", ".join(f"{sum(1 for i in items if i['type'] == k)} {k}" for k in store.TYPES)
    last = card.last_session(memory.dir)
    config = store.load_config(store.worktree_root(cwd))
    state = "on" if store.enabled(config) else "off (HAFIZ=off or \"mode\": \"off\" in .hafiz.json)"
    print(f"hafiz {__version__}: {state}")
    print(f"project {root.name}, branch {store.branch(cwd) or '(none)'}")
    print(f"data {memory.dir}")
    print(f"memories: {counts} (cap {store.MAX_MEMORIES})")
    latest = f"; latest {last['session'][:8]} at {last.get('updated', '')[:16]}" if last else ""
    print(f"sessions recorded: {len(card.sessions(memory.dir))}{latest}")
    return 0


def run_hook(kind: str) -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        handler = HOOKS.get(kind)
        out = handler(event) if handler and isinstance(event, dict) else ""
        if out:
            sys.stdout.write(out + "\n")
    except Exception:  # a hook must never break the session
        pass
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="hafiz",
                                  description=f"hafiz {__version__} - memory of your work (Nexika)")
    sub = top.add_subparsers(dest="command")

    p = sub.add_parser("recall", help="search memories (Arabic and English)")
    p.add_argument("query", nargs="*")
    p.add_argument("--type", choices=store.TYPES)
    p.add_argument("--here", action="store_true", help="only this branch (and project-wide memories)")
    p.add_argument("--branch")
    p.add_argument("--days", type=int)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_recall)

    p = sub.add_parser("remember", help="save a memory by hand")
    p.add_argument("type", choices=store.TYPES)
    p.add_argument("text", nargs="+")
    p.add_argument("--project", action="store_true", help="true for the whole project, not just this branch")
    p.add_argument("--status", choices=STATUSES)
    p.set_defaults(run=cmd_remember)

    p = sub.add_parser("list", help="newest memories")
    p.add_argument("--type", choices=store.TYPES)
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--here", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_list)

    p = sub.add_parser("forget", help="delete memories for good")
    p.add_argument("ids", nargs="*")
    p.add_argument("--match")
    p.add_argument("--session")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(run=cmd_forget)

    p = sub.add_parser("handoff", help="show the handoff note, or say where you stopped with --note")
    p.add_argument("--note")
    p.add_argument("--branch")
    p.add_argument("--save", action="store_true",
                   help="capture the session now and write the note (mizan uses it)")
    p.add_argument("--session")
    p.add_argument("--transcript")
    p.set_defaults(run=cmd_handoff)

    p = sub.add_parser("summary", help="detailed session summary written by Claude (Sonnet by default)")
    p.add_argument("--model", default=summary.DEFAULT_MODEL,
                   help="sonnet (default), opus, haiku or a claude-* id")
    p.add_argument("--session", help="session id or its first characters (default: the latest)")
    p.add_argument("--lang", help="language of the summary (default: the one you wrote in)")
    p.add_argument("--out", help="also save it here (for example docs/sessions/x.md)")
    p.add_argument("--dry-run", action="store_true", help="print what would be sent and call nothing")
    p.set_defaults(run=cmd_summary)

    p = sub.add_parser("export", help="the nexika.hafiz/1 contract for other plugins")
    p.add_argument("--json", action="store_true")
    p.add_argument("--branch")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(run=cmd_export)

    p = sub.add_parser("status", help="where data lives and how much is stored")
    p.set_defaults(run=cmd_status)
    return top


def main(argv: list[str]) -> int:
    if argv[:1] == ["hook"]:
        return run_hook(argv[1] if len(argv) > 1 else "")
    top = parser()
    args = top.parse_args(argv)
    if not getattr(args, "run", None):
        top.print_help()
        return 0
    try:
        return args.run(args)
    except TimeoutError:
        print("hafiz memory is busy (another session is saving); try again in a few seconds.")
        return 1


def entry() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
