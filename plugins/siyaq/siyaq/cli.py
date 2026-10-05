"""siyaq command line and hook entry point."""
from __future__ import annotations

import datetime
import json
import sys
from collections import Counter
from pathlib import Path

from . import __version__, hooks, rank, state, text
from . import index as idx

USAGE = f"""siyaq {__version__} - project knowledge on demand (Nexika)

  siyaq match TEXT...     what a prompt would load, with scores (ignores the session memory)
  siyaq entries [WORD]    list entries (optionally filtered)
  siyaq index             rebuild the index and report sources, entries, dead references
  siyaq stats [DAYS]      what was injected, opened, never used, and what is missing
  siyaq hook prompt|tool|session-start   (used by Claude Code)
"""


def helper_command() -> str:
    return f"python3 {Path(__file__).resolve().parent.parent / 'bin' / 'siyaq'}"


def cmd_match(root: Path, query: str) -> str:
    config = idx.load_config(root)
    cfg = rank.settings(config)
    index = idx.load(root, config)
    tokens = text.tokens(query)
    lines = [f"query tokens: {' '.join(tokens) or '(none: only stop words)'}"]
    for value, entry, matched in rank.score(index, tokens)[:10]:
        ok = "match" if rank.qualifies(entry, matched, value, cfg) else "below rule"
        lines.append(f"  {value:6.2f}  {ok:<10} {entry['title']}  [{', '.join(matched)}]")
    picked = rank.select_for_prompt(index, query, cfg, {})
    total = sum(len(p["text"]) for p in picked)
    lines.append(f"\nwould inject {len(picked)} entr{'y' if len(picked) == 1 else 'ies'}, "
                 f"~{total // rank.CHARS_PER_TOKEN} tokens:")
    lines += [f"--- [{p['level']}] ---\n{p['text']}" for p in picked]
    return "\n".join(lines)


def cmd_entries(root: Path, word: str = "") -> str:
    index = idx.load(root)
    rows = [e for e in index["entries"] if not word or word.lower() in (e["title"] + e["source"]).lower()]
    out = [f"{len(rows)} of {index['n']} entries"]
    for e in rows:
        extra = f"  paths: {', '.join(e['paths'][:3])}" if e["paths"] else ""
        out.append(f"  [{e['kind']}] {e['title']}  ({e['source']}:{e['start']}-{e['end']}){extra}")
    return "\n".join(out)


def cmd_index(root: Path) -> str:
    index = idx.build(root)
    cache = idx.project_dir(root) / "index.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    manual = sum(1 for e in index["entries"] if e["kind"] == "manual")
    dead = [(e["title"], d) for e in index["entries"] for d in e["dead_refs"]]
    out = [f"{index['n']} entries ({manual} hand-written) from {len(index['sources'])} sources:"]
    out += [f"  {s}" for s in index["sources"][:30]]
    if dead:
        out.append(f"dead references ({len(dead)}):")
        out += [f"  {title} -> {path} (missing)" for title, path in dead[:20]]
    return "\n".join(out)


def cmd_stats(root: Path, days: int = 30) -> str:
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    index = idx.load(root)
    events = state.read_events(root, since)
    shown = [e for e in events if e.get("type") == "shown"]
    opened = Counter(e["id"] for e in events if e.get("type") == "opened")
    misses = [e for e in events if e.get("type") == "miss"]
    by_id = {e["id"]: e for e in index["entries"]}
    shown_count = Counter(e["id"] for e in shown)
    manual = sum(1 for e in index["entries"] if e["kind"] == "manual")
    dead = [(e["title"], d) for e in index["entries"] for d in e["dead_refs"]]

    out = [f"siyaq stats: last {days} days, project {root.name}",
           f"index: {index['n']} entries from {len(index['sources'])} sources ({manual} hand-written), "
           f"{len(dead)} dead reference(s)"]
    levels = Counter(e.get("level") for e in shown)
    tokens = sum(e.get("chars", 0) for e in shown) // rank.CHARS_PER_TOKEN
    triggers = Counter(e.get("trigger") for e in shown)
    out.append(f"injections: {len(shown)} ({levels.get('summary', 0)} summary, {levels.get('full', 0)} full; "
               f"{triggers.get('prompt', 0)} from prompts, {triggers.get('path', 0)} from files) "
               f"~{tokens:,} tokens; prompts with no match: {len(misses)}")
    if shown_count:
        top = shown_count.most_common(5)
        def title(i: str) -> str:
            return by_id[i]["title"] if i in by_id else i

        used = [f"{title(i)} (shown {n}, opened {opened.get(i, 0)})" for i, n in top]
        out.append("most used: " + "; ".join(used))
    never = [e for e in index["entries"] if e["id"] not in shown_count]
    if never and index["n"]:
        names = ", ".join(e["title"] for e in never[:5])
        out.append(f"never shown: {len(never)} of {index['n']} (e.g. {names})")
    summary_only = {e["id"] for e in shown if e.get("level") == "summary"} - {
        e["id"] for e in shown if e.get("level") == "full"}
    unopened = [i for i in summary_only if shown_count[i] >= 2 and not opened.get(i)]
    if unopened:
        out.append("summaries shown 2+ times but never opened: "
                   + ", ".join(by_id[i]["title"] if i in by_id else i for i in sorted(unopened)[:5]))
    gaps = Counter(t for m in misses for t in m.get("terms", []) if t not in index["df"])
    recurring = [(t, n) for t, n in gaps.most_common(8) if n >= 2]
    if recurring:
        out.append("recurring topics with no knowledge: " + ", ".join(f"{t} {n}" for t, n in recurring)
                   + "  -> /siyaq:add")
    if dead:
        out.append("dead references: " + "; ".join(f"{t} -> {d}" for t, d in dead[:5]))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if cmd == "hook":
        kind = argv[1] if len(argv) > 1 else ""
        try:
            event = json.loads(sys.stdin.read() or "{}")
            if kind == "prompt":
                out = hooks.on_prompt(event)
            elif kind == "tool":
                out = hooks.on_tool(event)
            elif kind == "session-start":
                out = hooks.on_session_start(event, helper_command())
            else:
                out = None
            if out:
                sys.stdout.write(out + "\n")
        except Exception:  # a hook must never break the session
            pass
        return 0
    root = idx.project_root(Path.cwd())
    if cmd == "match" and len(argv) > 1:
        print(cmd_match(root, " ".join(argv[1:])))
    elif cmd == "entries":
        print(cmd_entries(root, " ".join(argv[1:])))
    elif cmd == "index":
        print(cmd_index(root))
    elif cmd == "stats":
        print(cmd_stats(root, int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 30))
    else:
        print(USAGE)
        return 0 if cmd in ("-h", "--help", "help") else 2
    return 0


def entry() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
