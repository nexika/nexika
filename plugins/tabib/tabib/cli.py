"""tabib command line: triage (mizan, no AI), diagnose and record (the skill), show (people)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, diagnosis, forge, gitinfo, hooks, parse
from .i18n import label, lang, t

STDIN_LIMIT = 1_000_000


def helper_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "bin" / "tabib")


def emit(data) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def summary(record: dict, language: str = "") -> dict:
    """The few fields mizan's band needs."""
    return {"run": record["run"]["id"], "sha": record["run"]["sha"], "kind": record["kind"],
            "detail": record["detail"], "confidence": record["confidence"],
            "label": label(record["kind"], record["detail"], language),
            "cause_found": bool(record.get("cause"))}


def report(record: dict, language: str = "") -> str:
    lg = language or lang()
    run = record["run"]
    out = [t("title", lg, run=run["id"], workflow=run.get("workflow") or "-", branch=record["branch"],
             sha=(run.get("sha") or "")[:8]), run.get("url") or ""]
    out += ["", t("h_failed", lg)]
    for f in record["failures"][:10]:
        where = f"{f['file']}:{f['line']}" if f["file"] and f["line"] else f["file"]
        place = f" ({where})" if f["test"] and where else ""
        out.append(f"  [{f['job'] or '-'}] {f['test'] or where}{place}")
        if f["message"]:
            out.append(f"      {f['message']}")
    if not record["failures"]:
        out += [f"  {e}" for e in record["errors"][:5]] or ["  -"]
    out += ["", f"{t('h_kind', lg)}: {label(record['kind'], record['detail'], lg)} "
                f"({t('confidence', lg, level=record['confidence'])})"]
    out += [f"  {e}" for e in record["evidence"][:5]]
    suspects = record.get("suspects") or {}
    out += ["", t("h_since", lg)]
    if suspects.get("available"):
        out.append("  " + t("since", lg, count=len(suspects["commits"]), run=suspects.get("green_run")))
        for c in suspects["commits"][:8]:
            mark = f"  <- {t('suspect', lg)}" if c["suspect"] else ""
            out.append(f"    {c['sha']} {c['author']}: {c['subject']}{mark}")
        if suspects.get("deps_changed"):
            out.append("  " + t("deps", lg, files=", ".join(suspects["deps_changed"][:5])))
    else:
        out.append("  " + t("no_green", lg))
    repro = record.get("reproduction")
    out += ["", t("h_repro", lg)]
    if repro:
        out.append("  " + t(f"r_{repro['status']}", lg, why=repro.get("why", ""),
                            command=repro.get("command", "")))
        out += [f"  {note}" for note in repro.get("notes", [])]
    else:
        out.append("  " + t("r_none", lg))
    cause = record.get("cause")
    if cause:
        out += ["", t("h_cause", lg), f"  {cause['text']} ({t('confidence', lg, level=cause['confidence'])})"]
        out += [f"    - {e}" for e in cause.get("evidence", [])]
    out += ["", t("h_next", lg)]
    if record["kind"] == "flaky":
        out.append("  " + t("next_rerun", lg, command=record["rerun"]))
    elif record["kind"] == "infra":
        out.append("  " + t("next_infra", lg, command=record["rerun"]))
    elif record["failures"]:
        out.append("  " + t("next_fix", lg))
    else:
        out.append("  " + t("next_unknown", lg, url=run.get("url") or "-"))
    if record.get("injection"):
        out += ["", t("injection", lg, labels=", ".join(record["injection"]))]
    return "\n".join(parse.clean_text(line) for line in out)


def _info(args) -> dict:
    info = gitinfo.read(args.cwd or os.getcwd())
    if not info:
        raise forge.Off("not a git repository")
    return info


def cmd_triage(args) -> int:
    record = diagnosis.triage(_info(args), args.run, refresh=args.refresh)
    if args.json:
        emit(summary(record))
    else:
        print(report(record))
    return 0


def cmd_diagnose(args) -> int:
    record = diagnosis.diagnose(_info(args), args.run, local_run=not args.no_run)
    if args.json:
        where = diagnosis.path_for(record["repo"], record["run"]["id"])
        emit({**diagnosis.facts(record), "path": str(where)})
    else:
        print(report(record))
    return 0


def cmd_show(args) -> int:
    record = diagnosis.latest(_info(args), args.run)
    if not record:
        print(t("none"))
        return 1
    if args.json:
        emit(record)
    else:
        print(report(record))
    return 0


def cmd_record(args) -> int:
    record = diagnosis.record_cause(_info(args), args.run, args.cause, args.confidence, args.evidence)
    if not record:
        print(t("none"))
        return 1
    print(report(record))
    return 0


def cmd_hook(args) -> int:
    if sys.stdin is not None and not sys.stdin.isatty():
        sys.stdin.read(STDIN_LIMIT)
    sys.stdout.write(hooks.on_session_start({}, helper_path()) + "\n")
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="tabib", description="Finds out why CI failed, with evidence.",
                                  allow_abbrev=False)
    top.add_argument("--version", action="version", version=f"tabib {__version__}")
    sub = top.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--run", type=int,
                       help="the run (GitHub) or pipeline (GitLab) id; default: the newest failed")
        p.add_argument("--cwd")

    p = sub.add_parser("triage", allow_abbrev=False,
                       help="what failed and what kind of failure (no AI, no code run)")
    common(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(run_cmd=cmd_triage)

    p = sub.add_parser("diagnose", allow_abbrev=False,
                       help="triage, compare with the last green run, run the failing tests in a worktree")
    common(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-run", action="store_true", help="do not run the failing tests locally")
    p.set_defaults(run_cmd=cmd_diagnose)

    p = sub.add_parser("show", allow_abbrev=False, help="the latest diagnosis of this branch")
    common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run_cmd=cmd_show)

    p = sub.add_parser("record", allow_abbrev=False, help="save the cause found (reported by Claude)")
    common(p)
    p.add_argument("--cause", required=True)
    p.add_argument("--confidence", choices=diagnosis.CONFIDENCE, required=True)
    p.add_argument("--evidence", action="append", default=[])
    p.set_defaults(run_cmd=cmd_record)

    p = sub.add_parser("hook", help=argparse.SUPPRESS)
    p.add_argument("event", choices=["session-start"])
    p.set_defaults(run_cmd=cmd_hook)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run_cmd(args)
    except forge.Off as off:
        if getattr(args, "json", False):
            emit({"error": str(off)})
        else:
            print(f"tabib: {off}", file=sys.stderr)
        return 2


def entry() -> None:
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    except Exception as error:  # the hook must never break the session
        sys.stderr.write(f"tabib: {type(error).__name__}: {error}\n")
        code = 0 if len(sys.argv) > 1 and sys.argv[1] == "hook" else 1
    sys.exit(code)
