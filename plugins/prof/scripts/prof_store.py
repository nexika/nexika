#!/usr/bin/env python3
"""prof_store - storage and hook helper for the Nexika prof plugin (stdlib only).

Commands:
  session-start            SessionStart hook. Prints the learner context: profile, what to
                           review from past sessions, and the warm-up rule. (stdin: hook JSON)
  session-end              SessionEnd hook. If this session was a tutoring session and no
                           report was written, generates one in the background. (stdin: hook JSON)
  merge-report FILE        Apply a report's "Concept checklist" to the per-topic files.
  topic SLUG               Print everything known about one topic (used by the warmup skill).
  write-auto-report SID CONVO   Internal: runs detached, asks `claude -p` for the report.

Data lives in ~/.claude/nexika/prof (override with PROF_HOME):
  profile.md                 learner profile (managed by the progress skill)
  reports/DATE_HHMM_SID8.md  one report per session
  topics/SLUG.md             concept checklist per topic, merged from the reports
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("PROF_HOME") or Path.home() / ".claude" / "nexika" / "prof")
REPORTS = HOME / "reports"
TOPICS = HOME / "topics"
TMP = HOME / "tmp"
PROFILE = HOME / "profile.md"
LOG = HOME / "hook.log"
MERGED = REPORTS / ".merged"

# Set on the background `claude -p` run so its own hooks don't recurse.
GUARD_ENV = "PROF_REPORTING"

# Worst first: this is also the order items are shown and re-taught in.
STATUSES = ("missed", "shaky", "not-checked", "understood")
STALE_DAYS = 14  # an "understood" concept older than this gets a retention question

# Report line:  - [status] topic-slug :: Topic Title :: concept :: evidence
CHECK_RE = re.compile(
    r"^\s*-\s*\[(missed|shaky|not-checked|understood)\]\s*"
    r"(.+?)\s*::\s*(.+?)\s*::\s*(.+?)\s*::\s*(.*?)\s*$"
)
# Topic file line: - [status] concept — evidence (YYYY-MM-DD)
TOPIC_LINE_RE = re.compile(
    r"^- \[(missed|shaky|not-checked|understood)\] (.+?) — (.*) \((\d{4}-\d{2}-\d{2})\)$"
)
REPORT_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")

REPORT_FORMAT = """\
# Tutor session report - {date}
Session: {sid8} · Source: {source}

## What you learned today
- concept: one-line explanation at the learner's level

## What you did
- chronological summary: lessons, exercises, code written, files touched, questions asked

## Comprehension checks
| Question | Learner's answer (short) | Verdict |
|---|---|---|

## Weak areas & logic gaps
- the misunderstanding or broken reasoning, with the evidence (what they said/did)

## Level estimate
- topic: beginner | junior | intermediate - one line why

## Review next time
- what to re-check or re-teach first next session, most important first

## Concept checklist
- [status] topic-slug :: Topic Title :: concept :: evidence
"""

AUTO_REPORT_PROMPT = """\
You are the Nexika prof plugin's report writer. Standard input holds the transcript of a tutoring
session between a TUTOR (Claude) and a LEARNER. Write the end-of-session report.

Rules:
- Output ONLY the report markdown, nothing before or after it. Do not use tools.
- Follow this exact structure and headings:

{fmt}
- "Weak areas & logic gaps" must be concrete: quote or paraphrase the wrong answer or flawed
  reasoning. If none were observed, say so honestly; do not invent weaknesses.
- Concept checklist: one line per concept taught or checked. status is one of:
  understood (answered/applied correctly), shaky (partly right, hesitant, needed hints),
  missed (wrong or could not answer), not-checked (explained but never tested).
  topic-slug names the BROAD subject (e.g. csharp-async), never a single concept; it is
  lowercase-with-dashes. Concept names are short (2-6 words). Keep the 4 `::` separators exactly.
- Reuse an existing topic slug and the exact existing concept name whenever the session
  touched them, so the learner's history stays in one place. Known topics:
{known}
"""


def known_topics_text() -> str:
    lines = []
    for slug, title, _last, _open, _stale in topic_summaries():
        _, entries = load_topic(slug)
        names = "; ".join(e[1] for e in entries.values())
        lines.append(f"  - {slug} ({title}): {names}")
    return "\n".join(lines) or "  (none yet)"


# ---------------------------------------------------------------- helpers

def _today() -> str:
    return datetime.date.today().isoformat()


def _log(msg: str) -> None:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _read_hook_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "general"


def report_for_session(sid: str) -> Path | None:
    if not sid or not REPORTS.is_dir():
        return None
    found = sorted(REPORTS.glob(f"*_{sid[:8]}.md"))
    return found[-1] if found else None


# ---------------------------------------------------------------- topic store

Entry = tuple[str, str, str, str]  # status, concept, evidence, date


def load_topic(slug: str) -> tuple[str, dict[str, Entry]]:
    path = TOPICS / f"{slug}.md"
    title, entries = slug, {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                continue
            m = TOPIC_LINE_RE.match(line.strip())
            if m:
                status, concept, evidence, date = m.groups()
                entries[concept.lower()] = (status, concept, evidence, date)
    return title, entries


def save_topic(slug: str, title: str, entries: dict[str, Entry]) -> None:
    TOPICS.mkdir(parents=True, exist_ok=True)
    rank = {s: i for i, s in enumerate(STATUSES)}
    rows = sorted(entries.values(), key=lambda e: (rank[e[0]], e[1].lower()))
    lines = [f"# {title}", "",
             "<!-- managed by prof_store.py merge-report; edit statuses freely -->", ""]
    lines += [f"- [{s}] {c} — {ev} ({d})" for s, c, ev, d in rows]
    (TOPICS / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_report(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    m = REPORT_DATE_RE.match(path.name)
    date = m.group(1) if m else _today()
    updates: dict[str, list[tuple[str, str, str, str]]] = {}
    for line in text.splitlines():
        cm = CHECK_RE.match(line)
        if cm:
            status, slug, title, concept, evidence = cm.groups()
            updates.setdefault(slugify(slug), []).append((status, title, concept, evidence))
    count = 0
    for slug, rows in updates.items():
        title, entries = load_topic(slug)
        for status, new_title, concept, evidence in rows:
            title = new_title or title
            entries[concept.lower()] = (status, concept, evidence or "-", date)
            count += 1
        save_topic(slug, title, entries)
    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(MERGED, "a", encoding="utf-8") as fh:
        fh.write(path.name + "\n")
    return count


def topic_summaries() -> list[tuple[str, str, str, list[Entry], list[Entry]]]:
    """(slug, title, last_date, open_items, stale_items) per topic, most recent first."""
    out = []
    if not TOPICS.is_dir():
        return out
    cutoff = (datetime.date.today() - datetime.timedelta(days=STALE_DAYS)).isoformat()
    for path in TOPICS.glob("*.md"):
        title, entries = load_topic(path.stem)
        if not entries:
            continue
        values = list(entries.values())
        open_items = [e for e in values if e[0] != "understood"]
        stale = [e for e in values if e[0] == "understood" and e[3] < cutoff]
        last = max(e[3] for e in values)
        out.append((path.stem, title, last, open_items, stale))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def _section(text: str, heading: str, limit: int) -> list[str]:
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith(heading.lower())
            continue
        if inside and line.strip():
            lines.append(line)
    return lines[:limit]


# ---------------------------------------------------------------- hooks

def session_start(hook: dict) -> None:
    if os.environ.get(GUARD_ENV):
        return
    sid = hook.get("session_id", "")
    script = Path(__file__).resolve()
    p = print

    p("## Prof plugin")
    p(f"Session id: {sid} (short: {sid[:8]}) · data: {HOME} · helper: python3 {script}")

    if PROFILE.is_file():
        p("\n### Learner profile")
        p("\n".join(PROFILE.read_text(encoding="utf-8").splitlines()[:60]))
    else:
        p("\nNo learner profile yet: on the first tutoring request ask level + goals, then "
          "create it with the prof:progress skill.")

    reports = sorted(REPORTS.glob("*.md")) if REPORTS.is_dir() else []
    if reports:
        last = reports[-1]
        text = last.read_text(encoding="utf-8")
        p(f"\n### Last session report ({last.name})")
        for heading in ("Weak areas", "Review next time"):
            body = _section(text, heading, 12)
            if body:
                p(f"{heading}:")
                p("\n".join(body))

    topics = topic_summaries()
    pending = [t for t in topics if t[3] or t[4]]
    if pending:
        p("\n### Open items from past sessions (worst first)")
        for slug, title, last, open_items, stale in pending[:6]:
            p(f"- {title} [{slug}], last studied {last}")
            for s, c, ev, d in open_items[:6]:
                p(f"    - [{s}] {c} — {ev} ({d})")
            for _s, c, _ev, d in stale[:2]:
                p(f"    - [retention check] {c} — understood on {d}")

    if topics:
        p("\n### Warm-up rule (mandatory)")
        p("Before teaching anything NEW in a tutoring request, run the prof:warmup skill "
          "for the topic first when that topic appears above or in "
          f"{TOPICS}. Test the open items and retention checks, estimate the level, and if "
          "the learner missed something from earlier sessions, re-teach it before any new "
          "concept. Do the warm-up once per topic per session.")
    p("\nAt the end of a tutoring session (learner says bye/done/that's all), run "
      "prof:report. If the session ends without one, a report is generated automatically.")


def _settings_style_is_professor(cwd: str) -> bool:
    candidates = [Path(cwd) / ".claude" / "settings.local.json",
                  Path(cwd) / ".claude" / "settings.json",
                  Path.home() / ".claude" / "settings.json"]
    for path in candidates:
        try:
            style = json.loads(path.read_text(encoding="utf-8")).get("outputStyle")
        except (OSError, ValueError, AttributeError):
            continue
        if style:
            return "professor" in str(style).lower()
    return False


def extract_conversation(transcript: Path) -> tuple[str, bool, int]:
    """Condensed TUTOR/LEARNER text, whether a tutor skill was used, learner turn count."""
    parts: list[str] = []
    tutoring, turns = False, 0
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            kind = obj.get("type")
            if kind not in ("user", "assistant") or obj.get("isMeta"):
                continue
            content = (obj.get("message") or {}).get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
            texts = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    if block.get("name") == "Skill" and str(inp.get("skill", "")).startswith("prof:"):
                        tutoring = True
                        texts.append(f"[used skill {inp.get('skill')} {inp.get('args', '')}]")
                    elif block.get("name") in ("Write", "Edit"):
                        texts.append(f"[{block.get('name')} {inp.get('file_path', '')}]")
            text = "\n".join(t for t in texts if t).strip()
            if not text:
                continue
            if kind == "user":
                if "/prof:" in text:
                    tutoring = True
                if not text.startswith("<system-reminder>"):
                    turns += 1
            who = "LEARNER" if kind == "user" else "TUTOR"
            parts.append(f"{who}: {text[:4000]}")
    convo = "\n\n".join(parts)
    return convo[-150_000:], tutoring, turns


def session_end(hook: dict) -> None:
    if os.environ.get(GUARD_ENV):
        return
    sid = hook.get("session_id", "")
    transcript = Path(hook.get("transcript_path") or "")
    if not sid or not transcript.is_file() or report_for_session(sid):
        return
    convo, tutoring, turns = extract_conversation(transcript)
    if not tutoring:
        tutoring = _settings_style_is_professor(hook.get("cwd") or os.getcwd())
    if not tutoring or turns < 3:
        return
    TMP.mkdir(parents=True, exist_ok=True)
    convo_path = TMP / f"{sid[:8]}.txt"
    convo_path.write_text(convo, encoding="utf-8")
    env = dict(os.environ, **{GUARD_ENV: "1"})
    # Detached: Claude Code does not wait for this, so exiting stays instant.
    with open(LOG, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "write-auto-report", sid, str(convo_path)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, start_new_session=True,
        )
    _log(f"auto-report started for {sid[:8]} ({turns} learner turns)")


def write_auto_report(sid: str, convo_path: Path) -> int:
    claude = shutil.which("claude")
    if not claude:
        _log("auto-report: `claude` not on PATH")
        return 1
    now = datetime.datetime.now()
    fmt = REPORT_FORMAT.format(date=now.date().isoformat(), sid8=sid[:8], source="automatic")
    prompt = AUTO_REPORT_PROMPT.format(fmt=fmt, known=known_topics_text())
    cmd = [claude, "-p", prompt, "--model", "sonnet",
           "--tools", "", "--no-session-persistence"]
    try:
        with open(convo_path, encoding="utf-8") as stdin:
            res = subprocess.run(cmd, stdin=stdin, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log(f"auto-report {sid[:8]}: {exc}")
        return 1
    report = res.stdout.strip()
    if res.returncode != 0 or "## Concept checklist" not in report:
        _log(f"auto-report {sid[:8]}: rc={res.returncode} unexpected output: "
             f"{res.stderr[:300]!r} {report[:200]!r}")
        return 1
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{now:%Y-%m-%d_%H%M}_{sid[:8]}.md"
    out.write_text(report + "\n", encoding="utf-8")
    n = merge_report(out)
    convo_path.unlink(missing_ok=True)
    _log(f"auto-report written: {out.name} ({n} concepts merged)")
    return 0


def print_topic(slug: str) -> int:
    slug = slugify(slug)
    known_slugs = sorted(p.stem for p in TOPICS.glob("*.md")) if TOPICS.is_dir() else []
    if slug not in known_slugs:
        # "C# async" -> c-async: accept the one known slug containing every word.
        words = slug.split("-")
        close = [k for k in known_slugs if all(w in k for w in words)]
        if len(close) == 1:
            slug = close[0]
    title, entries = load_topic(slug)
    if not entries:
        known = ", ".join(known_slugs)
        print(f"No history for topic '{slug}'. Known topics: {known or 'none'}")
        return 0
    print(f"# {title} [{slug}]")
    for status in STATUSES:
        rows = [e for e in entries.values() if e[0] == status]
        if rows:
            print(f"\n{status}:")
            for _, c, ev, d in rows:
                print(f"- {c} — {ev} ({d})")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "session-start":
            session_start(_read_hook_input())
        elif cmd == "session-end":
            session_end(_read_hook_input())
        elif cmd == "merge-report" and len(argv) > 2:
            n = merge_report(Path(argv[2]))
            print(f"merged {n} concepts from {argv[2]} into {TOPICS}")
        elif cmd == "topic" and len(argv) > 2:
            return print_topic(argv[2])
        elif cmd == "write-auto-report" and len(argv) > 3:
            return write_auto_report(argv[2], Path(argv[3]))
        else:
            print(__doc__)
            return 2
    except Exception as exc:  # a hook must never break the session
        _log(f"{cmd}: {type(exc).__name__}: {exc}")
        return 0 if cmd.startswith("session-") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
