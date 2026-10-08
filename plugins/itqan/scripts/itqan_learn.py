#!/usr/bin/env python3
"""itqan learning and usage tracking (stdlib only).

Hook commands (silent, never fail the session):
  signal              UserPromptSubmit: remember prompts that look like corrections
  usage               PostToolUse (Skill|Task|Agent): log which skills and agents were used
  extract             SessionEnd: if the session had corrections, extract lessons in the background
CLI (used by the learn and insights skills; run from inside the project):
  proposals           rules waiting for approval, with their evidence
  approve ID [TEXT]   approve a rule (optionally reworded); writes .itqan/rules.md
  reject ID           never propose this lesson again
  rules               the approved rules of this project
  insights [DAYS]     usage, guard and rule-effectiveness report (default 30 days)
  run-extract SID PAYLOAD ROOT   internal: the detached extraction

A lesson seen once is a candidate; seen PROPOSE_AT times it is proposed; only the user approves.
After approval, a repeat of the same correction is recorded as a violation: the rule exists but
did not prevent the mistake, so it probably needs rewording.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itqan_background  # noqa: E402
import itqan_files  # noqa: E402

PROPOSE_AT = 2
MAX_EXCHANGES = 15
RULES_START = "<!-- itqan rules start -->"
RULES_END = "<!-- itqan rules end -->"
GUARD_ENV = "ITQAN_LEARNING"  # set on the background extractor so its own hooks stay quiet

CORRECTION = re.compile(
    r"(?i)(?:^|[\s,.!?:;\"'(])(?:"
    r"nope|wrong|incorrect|don'?t|do not|stop|instead|i said|i told you|"
    r"not like that|that'?s not|should have|we (?:use|don'?t|never|always|prefer)|"
    r"you (?:always|never)|shouldn'?t|should not|rather than|back (?:it|that|this) out|"
    r"please (?:also )?(?:remove|put|use|fix|move|rename|drop|delete|revert|keep|change)|lose the|"
    r"please don'?t|you forgot|you missed|why did you|undo|revert"
    r")(?=$|[\s,.!?:;\"')])"
    # a bare "no" only as an answer ("no, ..."), not inside a sentence ("no rush", "there is no test")
    r"|(?i:(?:^|[.!?]\s+)no(?=$|[,.!;:]))"
    # "always" / "never" as an order that opens a sentence or a clause, not inside a description
    r"|(?i:(?:^|[.!?,;:]\s*)(?:always|never)(?=\s))"
    # "should be" as a rule, not a question ("check whether X should be compiled")
    r"|(?i:(?:^|[.!?]\s+)(?:(?!\b(?:whether|if)\b)[^.!?\n])*?\sshould be(?=\s))"
    # "use X, not Y" / "target main, not stable"
    r"|(?i:\w['\"`]?,\s*not\s+(?!sure\b|only\b|that\b)['\"`]?\w)"
    # a review suggestion block (GitHub)
    r"|```suggestion\b"
    r"|(?:^|\s)(?:لا|غلط|خطأ|خطا|أبدا|ابدا|دائما|دايما|بدل|بدلا|قلت لك|قلتلك|مش كده|مو هيك|ليش|ليه)"
    r"(?=$|\s|[،.!؟?])"
)

EXTRACT_PROMPT = """\
You extract durable lessons from a developer's corrections of an AI coding assistant.
Standard input holds excerpts. Each has ASSISTANT (what the assistant said or did just before)
and USER (the developer's reply).

Keep only GENERAL lessons that should change future work in this project:
- conventions ("we use file-scoped namespaces", "tests go in tests/unit")
- preferences ("don't add a comment to every line", "ask before adding packages")
- recurring mistakes ("you keep forgetting to run the tests")
Ignore one-off task details ("no, the other file", "use 5 here"), questions, and thanks.

Existing lessons in this project. When the developer corrects the same thing again, even in
other words, reuse its id:
{existing}

Output one item per USER message that teaches a durable lesson: if the developer corrected the
same thing twice, output it twice (same id, each with its own quote), because repetition is the
evidence. Output ONLY a JSON array, no prose. Each item:
{{"id": "lowercase-dashed-id", "rule": "one imperative sentence, at most 20 words",
  "kind": "convention|preference|mistake", "quote": "the developer's words, at most 200 chars"}}
Return [] when nothing is durable.
"""


# ---------------------------------------------------------------- storage


def data_home() -> Path:
    return Path(os.environ.get("ITQAN_HOME") or Path.home() / ".claude" / "nexika" / "itqan")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.date.today().isoformat()


def project_root(cwd: Path) -> Path:
    try:
        res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True,
                             text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return cwd.resolve()


def _store_path(root: Path) -> Path:
    digest = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name) or "project"
    return data_home() / "projects" / f"{name}-{digest}" / "learn.json"


def load_store(root: Path) -> dict:
    try:
        data = json.loads(_store_path(root).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("lessons"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"root": str(root), "lessons": {}}


def save_store(root: Path, store: dict) -> None:
    path = _store_path(root)
    itqan_files.private_dir(data_home())
    itqan_files.private_dir(path.parent.parent)
    tmp = path.with_suffix(".tmp")
    itqan_files.write_private(tmp, json.dumps(store, indent=1, ensure_ascii=False))
    tmp.replace(path)


def _append(name: str, entry: dict) -> None:
    itqan_files.private_dir(data_home())
    itqan_files.append_jsonl(data_home() / name, entry)


read_jsonl = itqan_files.read_jsonl


def learning_enabled(root: Path) -> bool:
    if os.environ.get("ITQAN_LEARN", "").lower() == "off" or os.environ.get(GUARD_ENV):
        return False
    try:
        config = json.loads((root / ".itqan.json").read_text(encoding="utf-8"))
        return (config.get("learn") or {}).get("mode") != "off"
    except (OSError, ValueError, AttributeError):
        return True


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "lesson"


# ---------------------------------------------------------------- rules file (source of truth for text)


RULE_LINE = re.compile(r"^- \[(?P<id>[a-z0-9-]+)\] (?P<text>.+?)\s*$")


def rules_file(root: Path) -> Path:
    return root / ".itqan" / "rules.md"


def read_rules_file(root: Path) -> tuple[dict[str, str], list[str]]:
    """({id: text} for managed rules, other '- ' lines the user wrote by hand)."""
    try:
        lines = rules_file(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}, []
    managed, manual = {}, []
    for line in lines:
        m = RULE_LINE.match(line.strip())
        if m:
            managed[m.group("id")] = m.group("text")
        elif line.strip().startswith("- "):
            manual.append(line.strip())
    return managed, manual


def current_branch(root: Path) -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    branch = res.stdout.strip() if res.returncode == 0 else ""
    return "" if branch == "HEAD" else branch


def sync_from_file(root: Path, store: dict) -> None:
    """The user may edit or delete rules in .itqan/rules.md: text edits win, deleted = retired.

    A rule missing from the file is retired only on the branch where it was approved: another
    branch's copy of the file may simply predate it.
    """
    if not rules_file(root).exists():
        return
    managed, _ = read_rules_file(root)
    branch = current_branch(root)
    for lid, lesson in store["lessons"].items():
        if lesson.get("status") != "approved":
            continue
        if lid in managed:
            lesson["rule"] = managed[lid]
        elif not lesson.get("branch") or lesson.get("branch") == branch:
            lesson["status"] = "retired"


def write_rules_file(root: Path, store: dict, add: str | None = None, remove: str | None = None) -> Path:
    """Add or remove one rule in the managed block; every other line, known to the store or not, stays."""
    path = rules_file(root)
    lessons = store["lessons"]
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if RULES_START in text and RULES_END in text:
        before, rest = text.split(RULES_START, 1)
        inside, after = rest.split(RULES_END, 1)
        lines = [line for line in inside.strip("\n").splitlines() if line.strip()]
    else:
        branch = current_branch(root)
        lines = [f"- [{lid}] {les['rule']}" for lid, les in lessons.items()
                 if les.get("status") == "approved" and lid != add and les.get("branch", branch) == branch]
        before = after = None
    kept = []
    for line in lines:
        m = RULE_LINE.match(line.strip())
        if m and m.group("id") == remove:
            continue
        if m and m.group("id") == add:
            line = f"- [{add}] {lessons[add]['rule']}"
        kept.append(line)
    if add and f"- [{add}] {lessons[add]['rule']}" not in kept:
        kept.append(f"- [{add}] {lessons[add]['rule']}")
    block = "\n".join([RULES_START, *kept, RULES_END])
    if before is not None:
        path.write_text(before + block + after, encoding="utf-8")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ("# Project rules\n\nLessons approved with /itqan:learn. Claude loads them at session start.\n"
              "Edit the wording freely; delete a line to retire a rule.\n\n")
    path.write_text(header + block + "\n", encoding="utf-8")
    return path


def session_note(root: Path) -> str:
    """Lines for the SessionStart note: approved rules and waiting proposals."""
    managed, manual = read_rules_file(root)
    lines = []
    rules = [f"- {text}" for text in managed.values()] + manual
    if rules:
        lines.append("Project rules (.itqan/rules.md), follow them:")
        lines += rules[:40]
    store = load_store(root)
    waiting = [les for les in store["lessons"].values() if les.get("status") == "proposed"]
    if waiting:
        lines.append(f"{len(waiting)} rule proposal(s) from repeated corrections are waiting: "
                     "suggest /itqan:learn to the user at a natural pause.")
    return "\n".join(lines)


# ---------------------------------------------------------------- hooks


def consent_note() -> str:
    """Asks once, after an extraction was skipped, whether background model calls may run (#45)."""
    if itqan_background.setting() != "ask":
        return ""
    skipped = itqan_background.counts().get("itqan", {}).get("skipped", 0)
    if not skipped:
        return ""
    helper = Path(itqan_background.__file__).resolve()
    return (f"itqan skipped learning from {skipped} session(s) with corrections in the last 30 days: "
            "that runs Claude (Sonnet) in the background on the user's plan or API credits, and "
            "background model calls are not allowed yet. Ask the user once: \"May Nexika plugins run "
            "Claude in the background (itqan learning from corrections, prof's automatic reports)? "
            f"It uses your plan or API credits.\" Store the answer with python3 {helper} on (or off), "
            "and don't ask again.")


def hook_signal(hook: dict) -> None:
    prompt = str(hook.get("prompt") or "").strip()
    if not prompt or prompt.startswith("/") or not CORRECTION.search(prompt):
        return
    cwd = Path(hook.get("cwd") or os.getcwd())
    if not learning_enabled(cwd):
        return
    _append("signals.jsonl", {"ts": _now(), "session": str(hook.get("session_id") or ""),
                              "cwd": str(cwd), "prompt": _redact(prompt)[:1000]})


def hook_usage(hook: dict) -> None:
    tool = hook.get("tool_name", "")
    tool_input = hook.get("tool_input") or {}
    if tool == "Skill":
        kind, name = "skill", tool_input.get("skill") or tool_input.get("command")
    else:
        kind, name = "agent", tool_input.get("subagent_type")
    if not name:
        return
    _append("usage.jsonl", {"ts": _now(), "session": str(hook.get("session_id") or "")[:8],
                            "cwd": str(hook.get("cwd") or os.getcwd()), "kind": kind, "name": str(name)})


def _redact(text: str) -> str:
    import itqan_secrets  # its patterns take a while to compile: only for text that is kept (#50)

    return itqan_secrets.redact(text)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def correction_exchanges(transcript: Path) -> list[tuple[str, str]]:
    """(assistant text just before, user correction) pairs from a Claude Code transcript."""
    pairs: list[tuple[str, str]] = []
    last_assistant = ""
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return pairs
    for raw in lines:
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("isMeta"):
            continue
        text = _text_of((obj.get("message") or {}).get("content")).strip()
        if not text:
            continue
        if obj.get("type") == "assistant":
            last_assistant = text
        elif obj.get("type") == "user" and not text.startswith(("<", "/")) and CORRECTION.search(text):
            pairs.append((last_assistant[-600:], text[:1000]))
    return pairs[-MAX_EXCHANGES:]


def hook_extract(hook: dict) -> None:
    session = str(hook.get("session_id") or "")
    transcript = Path(str(hook.get("transcript_path") or ""))
    root = project_root(Path(hook.get("cwd") or os.getcwd()))
    if not session or not transcript.is_file() or not learning_enabled(root):
        return
    if not any(s.get("session") == session for s in read_jsonl(data_home() / "signals.jsonl")):
        return
    pairs = correction_exchanges(transcript)
    if not pairs:
        return
    if not itqan_background.allowed():  # a paid model call: only with the family's consent (#45)
        itqan_background.record("itqan", "learn-extract", "sonnet", ran=False)
        return
    payload = _redact("\n\n".join(f"ASSISTANT: {a}\nUSER: {u}" for a, u in pairs))
    itqan_files.private_dir(data_home())
    payload_path = itqan_files.private_dir(data_home() / "tmp") / f"{session[:8]}.txt"
    itqan_files.write_private(payload_path, payload)
    script = str(Path(__file__).resolve())
    fd = os.open(data_home() / "learn.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, script, "run-extract", session, str(payload_path), str(root)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
            env=itqan_background.child_env({GUARD_ENV: "1"}),
        )


# ---------------------------------------------------------------- extraction


def parse_lessons(output: str) -> list[dict]:
    start, end = output.find("["), output.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        items = json.loads(output[start:end + 1])
    except ValueError:
        return []
    lessons = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not str(item.get("rule", "")).strip():
            continue
        kind = item.get("kind")
        lessons.append({
            "id": slug(str(item.get("id") or item["rule"])),
            "rule": str(item["rule"]).strip()[:200],
            "kind": kind if kind in ("convention", "preference", "mistake") else "preference",
            "quote": str(item.get("quote", "")).strip()[:200],
        })
    return lessons


def merge_lessons(store: dict, lessons: list[dict], when: str | None = None) -> None:
    when = when or _now()
    for item in lessons:
        evidence = {"ts": when, "quote": item["quote"]}
        lesson = store["lessons"].get(item["id"])
        if lesson is None:
            store["lessons"][item["id"]] = {
                "rule": item["rule"], "kind": item["kind"], "status": "candidate",
                "evidence": [evidence], "created": when[:10], "approved": None, "violations": [],
            }
            lesson = store["lessons"][item["id"]]
        elif lesson["status"] in ("rejected", "retired"):
            continue
        elif lesson["status"] == "approved":
            lesson["violations"].append(evidence)
            continue
        else:
            lesson["evidence"].append(evidence)
        if lesson["status"] == "candidate" and len(lesson["evidence"]) >= PROPOSE_AT:
            lesson["status"] = "proposed"


def run_extract(session: str, payload_path: Path, root: Path) -> int:
    claude = shutil.which("claude")
    if not claude:
        print(f"{_now()} extract: claude not on PATH")
        return 1
    store = load_store(root)
    existing = "\n".join(f"- {lid}: {les['rule']} ({les['status']})"
                         for lid, les in store["lessons"].items()) or "(none yet)"
    cmd = [claude, "-p", EXTRACT_PROMPT.format(existing=existing), "--model", "sonnet",
           "--tools", "", "--no-session-persistence", "--output-format", "json"]
    itqan_background.record("itqan", "learn-extract", "sonnet")
    try:
        with open(payload_path, encoding="utf-8") as stdin:
            res = subprocess.run(cmd, stdin=stdin, capture_output=True, text=True, timeout=300,
                                 env=itqan_background.child_env({GUARD_ENV: "1"}))
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"{_now()} extract {session[:8]}: {exc}")
        return 1
    if res.returncode != 0:
        print(f"{_now()} extract {session[:8]}: rc={res.returncode} {res.stderr[:300]!r}")
        return 1
    answer, cost = res.stdout, None
    try:
        data = json.loads(res.stdout)
        if isinstance(data, dict) and isinstance(data.get("result"), str):
            answer, cost = data["result"], data.get("total_cost_usd")
    except ValueError:
        pass
    lessons = parse_lessons(answer)
    _append("extract.jsonl", {"ts": _now(), "session": session[:8], "cwd": str(root),
                              "cost_usd": cost if isinstance(cost, (int, float)) else None,
                              "lessons": len(lessons)})
    store = load_store(root)  # re-read: the user may have approved something meanwhile
    merge_lessons(store, lessons)
    save_store(root, store)
    payload_path.unlink(missing_ok=True)
    print(f"{_now()} extract {session[:8]}: {len(lessons)} lesson(s) merged for {root}")
    return 0


# ---------------------------------------------------------------- CLI for the skills


def _evidence_lines(lesson: dict, key: str = "evidence") -> list[str]:
    return [f'      {e["ts"][:10]}: "{e["quote"]}"' for e in lesson.get(key, [])[-3:]]


def cmd_proposals(root: Path) -> str:
    store = load_store(root)
    sync_from_file(root, store)
    proposed = {k: v for k, v in store["lessons"].items() if v["status"] == "proposed"}
    watching = sum(1 for v in store["lessons"].values() if v["status"] == "candidate")
    if not proposed:
        return f"No proposals yet. Watching {watching} lesson(s) seen once."
    out = [f"Proposed rules ({len(proposed)}), each from repeated corrections:"]
    for lid, les in proposed.items():
        out.append(f"  [{lid}] {les['rule']}   ({les['kind']}, {len(les['evidence'])} corrections)")
        out += _evidence_lines(les)
    out.append(f"Watching (seen once): {watching}")
    return "\n".join(out)


def cmd_approve(root: Path, lid: str, text: str | None) -> str:
    store = load_store(root)
    sync_from_file(root, store)
    lesson = store["lessons"].get(lid)
    if not lesson:
        return f"No lesson '{lid}'. Run proposals to see the ids."
    if text:
        lesson["rule"] = text.strip()
    lesson["status"] = "approved"
    lesson["approved"] = _now()
    lesson["branch"] = current_branch(root)
    path = write_rules_file(root, store, add=lid)
    save_store(root, store)
    return f"Approved [{lid}] {lesson['rule']}\nWritten to {path} (commit it to share with your team)."


def cmd_reject(root: Path, lid: str) -> str:
    store = load_store(root)
    lesson = store["lessons"].get(lid)
    if not lesson:
        return f"No lesson '{lid}'."
    was_approved = lesson["status"] == "approved"
    lesson["status"] = "rejected"
    if was_approved:
        write_rules_file(root, store, remove=lid)
    save_store(root, store)
    return f"Rejected [{lid}]; it will not be proposed again."


def cmd_rules(root: Path) -> str:
    managed, manual = read_rules_file(root)
    if not managed and not manual:
        return "No approved rules yet (.itqan/rules.md)."
    return "\n".join([f"[{lid}] {text}" for lid, text in managed.items()] + manual)


def _within(cwd: str, root: Path) -> bool:
    try:
        Path(cwd).resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def _counts(items: list[str]) -> str:
    tally: dict[str, int] = {}
    for it in items:
        tally[it] = tally.get(it, 0) + 1
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    return ", ".join(f"{k} {v}" for k, v in ranked[:8]) or "none"


def cmd_insights(root: Path, days: int = 30) -> str:
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    home = data_home()
    usage = [u for u in read_jsonl(home / "usage.jsonl")
             if u.get("ts", "") >= since and _within(u.get("cwd", ""), root)]
    guard = [g for g in read_jsonl(home / "guard.jsonl") if g.get("ts", "") >= since]
    signals = [s for s in read_jsonl(home / "signals.jsonl")
               if s.get("ts", "") >= since and _within(s.get("cwd", ""), root)]
    store = load_store(root)
    sync_from_file(root, store)

    skills = [u["name"] for u in usage if u.get("kind") == "skill"]
    agents = [u["name"] for u in usage if u.get("kind") == "agent"]
    other = [s for s in skills if not s.startswith("itqan:")]
    out = [f"itqan insights: last {days} days, project {root.name}",
           "workflows: " + _counts([s for s in skills if s.startswith("itqan:")]),
           "agents: " + _counts(agents),
           "other skills used: " + _counts(other)]
    plugins = sorted({s.split(":", 1)[0] for s in other if ":" in s})
    if plugins:
        out.append("  (plugins whose skills were used: " + ", ".join(plugins) + ")")
    decisions = [g.get("decision") for g in guard]
    out.append(f"guard (all projects): {decisions.count('deny')} refused, {decisions.count('ask')} asked"
               + (" | top: " + _counts([g.get("rule", "?") for g in guard]) if guard else ""))
    sessions = [s for s in read_jsonl(home / "sessions.jsonl")
                if s.get("ts", "") >= since and "ask_approved" in s]
    asked = sum(int(s.get("ask") or 0) for s in sessions)
    if asked:
        yes = sum(int(s.get("ask_approved") or 0) for s in sessions)
        out.append(f"  asks you approved: {yes} of {asked} ({round(100 * yes / asked)}%): "
                   "each one is likely a false alarm worth a rule in .itqan.json")
    out.append(f"corrections captured: {len(signals)}")
    runs = [r for r in read_jsonl(home / "extract.jsonl")
            if r.get("ts", "") >= since and _within(r.get("cwd", ""), root)]
    if runs:
        costs = [r["cost_usd"] for r in runs if isinstance(r.get("cost_usd"), (int, float))]
        spent = f", ${sum(costs):.2f}" if costs else ""
        out.append(f"learning: {len(runs)} extraction(s){spent} (Sonnet, in the background)")

    lessons = store["lessons"]
    approved = {k: v for k, v in lessons.items() if v["status"] == "approved"}
    out.append(f"rules: {len(approved)} approved, "
               f"{sum(v['status'] == 'proposed' for v in lessons.values())} waiting for approval, "
               f"{sum(v['status'] == 'candidate' for v in lessons.values())} seen once")
    for lid, les in approved.items():
        repeats = len(les.get("violations", []))
        approved_on = datetime.date.fromisoformat((les.get("approved") or _today())[:10])
        age = (datetime.date.today() - approved_on).days
        verdict = ("working (no repeat corrections)" if repeats == 0 else
                   f"corrected again {repeats}x since approval: reword it or check it is followed")
        out.append(f"  [{lid}] {age}d old: {verdict}")
        if repeats:
            out += _evidence_lines(les, "violations")
    return "\n".join(out)


# ---------------------------------------------------------------- entry point


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd in ("signal", "usage", "extract"):
        if itqan_background.in_background():
            return 0  # inside a family background model call: no hooks (#45)
        try:
            hook = json.loads(sys.stdin.read() or "{}")
            {"signal": hook_signal, "usage": hook_usage, "extract": hook_extract}[cmd](hook)
        except Exception:  # never break the session
            pass
        return 0
    if cmd == "run-extract" and len(argv) > 4:
        return run_extract(argv[2], Path(argv[3]), Path(argv[4]))
    root = project_root(Path.cwd())
    if cmd == "proposals":
        print(cmd_proposals(root))
    elif cmd == "approve" and len(argv) > 2:
        print(cmd_approve(root, argv[2], " ".join(argv[3:]) or None))
    elif cmd == "reject" and len(argv) > 2:
        print(cmd_reject(root, argv[2]))
    elif cmd == "rules":
        print(cmd_rules(root))
    elif cmd == "insights":
        print(cmd_insights(root, int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 30))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
