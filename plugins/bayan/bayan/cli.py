"""bayan command line: check, clean, level, hook."""
from __future__ import annotations

import json
import sys

from . import config, hooks

USAGE = """usage:
  bayan check [FILE|-] [--level no-code|junior|developer] [--json] [--min-score N]
  bayan clean FILE... [--write] [--keep-dashes]
  bayan level [no-code|junior|developer]"""


def _read(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    with open(arg, encoding="utf-8", newline="") as fh:   # keep CRLF as it is
        return fh.read()


def _flag(args: list[str], name: str) -> str | None:
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            value = args[i + 1]
            del args[i:i + 2]
            return value
        raise ValueError(f"{name} needs a value")
    return None


def cmd_check(args: list[str]) -> int:
    from . import check, prose

    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    level = _flag(args, "--level") or config.load()["level"]
    min_score = _flag(args, "--min-score")
    if level not in config.LEVELS:
        raise ValueError(f"level must be one of: {', '.join(config.LEVELS)}")
    source = args[0] if args else "-"
    text = _read(source)
    findings = check.check(text, level)
    result = check.score(text, findings)
    if as_json:
        print(json.dumps({"file": source, "level": level, "score": result,
                          "findings": [f.to_dict() for f in findings]}, ensure_ascii=False, indent=1))
    else:
        sents = prose.sentences(text)
        print(f"bayan check: {source}  ({prose.words(text)} words, {len(sents)} sentences, reader: {level})")
        print(f"plainness score: {result}/100 (a style heuristic, not an AI detector)")
        fixes = [f.text for f in findings if f.kind == "fix"]
        if fixes:
            print("fixed by `bayan clean --write`: " + ", ".join(fixes))
        rewrites = sorted((f for f in findings if f.kind == "rewrite"),
                          key=lambda f: (f.line or 10**9, -f.weight))
        if rewrites:
            print("to rewrite:")
            for f in rewrites:
                print(f"  {'L' + str(f.line) if f.line else 'all':>5}  \"{f.text}\"  -> {f.advice}")
        if not findings:
            print("nothing to change")
    if min_score is not None and result < int(min_score):
        return 1
    return 0


def cmd_clean(args: list[str]) -> int:
    from . import clean

    write = "--write" in args
    dashes = "--keep-dashes" not in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        raise ValueError("clean needs at least one FILE (or - for stdin)")
    for name in files:
        text = _read(name)
        fixed, changes = clean.clean(text, dashes=dashes)
        if name == "-" or (not write and len(files) == 1):
            sys.stdout.write(fixed)
            if changes:
                print(f"\n[bayan: {clean.summary(changes)}]", file=sys.stderr)
            continue
        if write and fixed != text:
            with open(name, "w", encoding="utf-8", newline="") as fh:
                fh.write(fixed)
        verb = "cleaned" if write else "would clean"
        print(f"{name}: {verb} {clean.summary(changes)}" if changes else f"{name}: nothing to clean")
    return 0


def cmd_level(args: list[str]) -> int:
    if args:
        if args[0] not in config.LEVELS:
            raise ValueError(f"level must be one of: {', '.join(config.LEVELS)}")
        config.save(level=args[0])
    cfg = config.load()
    print(f"reader level: {cfg['level']}\n{hooks.LEVEL_RULE[cfg['level']]}")
    return 0


def cmd_hook(args: list[str]) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    try:
        if args[:1] == ["session-start"]:
            print(hooks.session_start(payload))
            return 0
        handler = {"post-write": hooks.post_write, "pre-bash": hooks.pre_bash}.get(args[0] if args else "")
        result = handler(payload) if handler else None
    except Exception:  # a hook must never break the session
        return 0
    if result:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, args = argv[0], list(argv[1:])
    try:
        if cmd == "check":
            return cmd_check(args)
        if cmd == "clean":
            return cmd_clean(args)
        if cmd == "level":
            return cmd_level(args)
        if cmd == "hook":
            return cmd_hook(args)
    except (ValueError, OSError) as exc:
        print(f"bayan: {exc}", file=sys.stderr)
        return 1
    print(USAGE)
    return 1


def entry() -> None:
    for stream in (sys.stdout, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
