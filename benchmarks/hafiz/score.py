"""Score one run of the hafiz benchmark from what bench.py recorded, and summarize many runs.

Standard library only. A run folder holds:

    meta.json                    task, arm, run, sessions, repo path, the calls and the breaks in order
    call-<n>.jsonl               claude's stream-json output for each call (the steps, each /compact)
    transcript-<s>.jsonl         each session's transcript, copied from the run's throwaway home
    diff.patch                   everything the agent changed, against the starting commit
    snap-{base,final}.json       the repo's text files at the start and at the end
    snap-break<k>.json, tests-break<k>.json   the files and test results just before break k
                                 (a /compact, or a restart in a new session)
    tests-final.json             runtests.py output (the repo's tests and the task's hidden checks)

A v1 run has one break, a /compact, recorded as snap-compact.json, tests-compact.json and
transcript.jsonl; it is read the same way.

Three groups, each scored from 0 to 1, and the continuity score is their mean:

    decisions   the seeded decisions still hold at the end
    open_work   the plan's open steps were done and the deferred failing test was fixed (without
                editing the test)
    no_redo     work finished before a break still works and was not rewritten or copied after it
"""
from __future__ import annotations

import ast
import json
import re
import statistics
from pathlib import Path

API_FAILURE = re.compile(r"usage limit|rate limit|overloaded|API Error|authentication|"
                         r"Invalid API key|OAuth token|credit balance|bearer token", re.I)


# ---- reading what was recorded -------------------------------------------------------------------

def events(path: Path):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def hook_context(event: dict) -> str:
    """The text a hook added to the conversation: additionalContext when the hook printed JSON,
    else its plain output."""
    output = str(event.get("output") or event.get("stdout") or "")
    try:
        data = json.loads(output)
    except ValueError:
        return output
    if isinstance(data, dict):
        specific = data.get("hookSpecificOutput") or {}
        if isinstance(specific, dict) and specific.get("additionalContext"):
            return str(specific["additionalContext"])
        return str(data.get("systemMessage") or "")
    return output


def read_call(path: Path) -> dict:
    """One claude call: usage, cost, tool calls, hook output and whether it compacted."""
    out = {"result": None, "is_error": None, "result_text": "", "cost_usd": 0.0, "turns": 0,
           "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
           "first_prompt_tokens": None, "tool_uses": [], "hooks": [], "compacted": False,
           "plugins": [], "session_id": ""}
    for event in events(path):
        kind, sub = event.get("type"), event.get("subtype", "")
        if kind == "system" and sub == "init":
            out["session_id"] = event.get("session_id", "")
            out["plugins"] = sorted(str(p.get("name", "") if isinstance(p, dict) else p).split("@")[0]
                                    for p in event.get("plugins") or [])
        elif kind == "system" and sub == "compact_boundary":
            out["compacted"] = True
        elif kind == "system" and sub == "hook_response":
            out["hooks"].append({"name": str(event.get("hook_name") or event.get("hook_event") or ""),
                                 "chars": len(hook_context(event))})
        elif kind == "assistant":
            message = event.get("message") or {}
            usage = message.get("usage") or {}
            if usage and out["first_prompt_tokens"] is None:
                out["first_prompt_tokens"] = sum(usage.get(k) or 0 for k in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    out["tool_uses"].append({"name": block.get("name", ""),
                                             "input": block.get("input") or {}})
        elif kind == "result":
            usage = event.get("usage") or {}
            out.update(result=sub, is_error=event.get("is_error"),
                       result_text=str(event.get("result") or "")[:300],
                       cost_usd=event.get("total_cost_usd") or 0.0, turns=event.get("num_turns") or 0,
                       input_tokens=usage.get("input_tokens") or 0,
                       output_tokens=usage.get("output_tokens") or 0,
                       cache_read_tokens=usage.get("cache_read_input_tokens") or 0,
                       cache_write_tokens=usage.get("cache_creation_input_tokens") or 0)
    return out


def transcript_compactions(path: Path) -> int:
    """How many times the session in this transcript was compacted (its summaries or its
    boundaries, whichever the transcript records more of)."""
    summaries = boundaries = 0
    for event in events(path):
        summaries += bool(event.get("isCompactSummary"))
        boundaries += event.get("subtype") == "compact_boundary"
    return max(summaries, boundaries)


# ---- the code checks ------------------------------------------------------------------------------

def symbols(source: str | None) -> dict[str, list[str]]:
    """Top-level functions and classes of a module, name -> AST dumps (more than one when the
    module defines the name twice). Unparsable or missing source has none."""
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.setdefault(node.name, []).append(ast.dump(node, include_attributes=False))
    return out


def test_source(source: str | None, test_id: str) -> str | None:
    """The AST dump of one test method (tests.module.Class.method), or None when it is gone."""
    _, cls, method = test_id.rsplit(".", 2)
    if not source:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method:
                    return ast.dump(item, include_attributes=False)
    return None


def added_lines(diff: str) -> list[str]:
    return [line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]


def _nodes(source: str | None) -> list:
    """Top-level functions and classes of a module (none when it is missing or does not parse)."""
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def symbol_sources(source: str | None) -> dict[str, str]:
    """name -> the normalized source of its (last) definition."""
    return {node.name: ast.unparse(node) for node in _nodes(source)}


def body_lines(node) -> list[str]:
    """The statements of a function or class as normalized, stripped lines, without its def line
    and docstring: what "the same code" means when comparing two versions."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return [line.strip() for stmt in body for line in ast.unparse(stmt).splitlines() if line.strip()]


def _code_paths(snap: dict) -> list[str]:
    return sorted(p for p in snap if p.endswith(".py") and not p.startswith("tests/"))


def finished(task: dict, base: dict, snap: dict) -> list[tuple[str, object]]:
    """(path, node) for every function or class of the task's keep_files that the agent added or
    changed before this break."""
    out = []
    for path in task.get("keep_files", []):
        start = {}
        for node in _nodes(base.get(path)):
            start.setdefault(node.name, ast.dump(node))
        out += [(path, node) for node in _nodes(snap.get(path)) if ast.dump(node) != start.get(node.name)]
    return out


REWRITTEN_BELOW = 0.5   # less than half of a finished symbol's lines are left anywhere: rewritten
COPIED_FROM = 0.8       # a new symbol holds 80% of a finished symbol's lines, still in place: a copy
COPY_MIN_LINES = 3


def redone(task: dict, base: dict, breaks: list[dict], final: dict, tests_final: dict) -> dict:
    """What work finished before a break (a compaction or a new session) was done again after it,
    judged by behaviour, not by any change of text. breaks: [{"snap": files, "tests": outcomes}].

    broken      a test that passed at a break (the hidden checks or the repo's own) fails at the end;
                a test that is gone is not counted
    rewritten   a function or class finished before a break whose lines are mostly gone: fewer than
                half are left in its final version or in code added after the break (a helper it
                was moved to). Extending it, or moving code into a helper, keeps its lines.
    duplicated  a name defined twice in one module, or a function or class added after a break that
                copies one finished before it while the original stays in place
    """
    broken = sorted({t for brk in breaks for t, outcome in (brk.get("tests") or {}).items()
                     if outcome == "pass" and tests_final.get(t) in ("fail", "error")})
    final_nodes = {path: _nodes(final.get(path)) for path in _code_paths(final)}
    rewritten, copies = set(), set()
    for brk in breaks:
        snap = brk.get("snap") or {}
        before = {(path, node.name) for path in _code_paths(snap) for node in _nodes(snap.get(path))}
        added = [(path, node) for path, nodes in final_nodes.items() for node in nodes
                 if (path, node.name) not in before]
        added_lines = {line for _, node in added for line in body_lines(node)}
        for path, node in finished(task, base, snap):
            lines = body_lines(node)
            if not lines:
                continue
            same = [n for n in final_nodes.get(path, []) if n.name == node.name]
            own = set(body_lines(same[-1])) if same else set()
            kept = sum(1 for line in lines if line in own or line in added_lines)
            if kept / len(lines) < REWRITTEN_BELOW:
                rewritten.add(f"{path}:{node.name}")
            if len(lines) < COPY_MIN_LINES or sum(1 for line in lines if line in own) / len(lines) < 0.5:
                continue  # moved away, not copied
            for new_path, new in added:
                theirs = set(body_lines(new))
                if sum(1 for line in lines if line in theirs) / len(lines) >= COPIED_FROM:
                    copies.add(f"{new_path}:{new.name} copies {path}:{node.name}")
    twice = [f"{path}:{name}" for path, text in sorted(final.items()) if path.endswith(".py")
             for name, dumps in symbols(text).items() if len(dumps) > 1]
    return {"broken": broken, "rewritten": sorted(rewritten), "duplicated": twice + sorted(copies)}


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def check(spec: dict, tests: dict, diff: str, base: dict, final: dict) -> bool | None:
    """One decision or open-work check: True, False, or None when it does not apply."""
    if "when" in spec and tests.get(spec["when"]) != "pass":
        return None
    if "test" in spec:
        return tests.get(spec["test"]) == "pass"
    if "absent" in spec:
        pattern = re.compile(spec["absent"])
        return not any(pattern.search(line) for line in added_lines(diff))
    if "unchanged" in spec:
        return base.get(spec["unchanged"]) == final.get(spec["unchanged"])
    raise ValueError(f"unknown check: {spec}")


# ---- one run --------------------------------------------------------------------------------------

def breaks_of(run_dir: Path, meta: dict) -> list[dict]:
    """Every break of a run, in order: {"kind": "compact" | "restart", "at": the index of the first
    call made at or after it, "snap": the repo's files, "tests": test outcomes}. A v1 run has one
    compaction, recorded as snap-compact.json and tests-compact.json."""
    if meta.get("breaks"):
        return [{"kind": b["kind"], "at": b["at"], "snap": _json(run_dir / b["snap"], {}),
                 "tests": _json(run_dir / b["tests"], {}).get("tests", {})} for b in meta["breaks"]]
    calls = meta.get("calls", [])
    at = next((i for i, c in enumerate(calls) if c["phase"] == "compact"), None)
    if at is None:
        return []
    return [{"kind": "compact", "at": at, "snap": _json(run_dir / "snap-compact.json", {}),
             "tests": _json(run_dir / "tests-compact.json", {}).get("tests", {})}]


def score_run(run_dir: Path, task: dict) -> dict:
    run_dir = Path(run_dir)
    meta = _json(run_dir / "meta.json", {})
    calls = [dict(read_call(run_dir / c["file"]), phase=c["phase"],
                  kind=c.get("kind") or ("compact" if c["phase"] == "compact" else "say"))
             for c in meta.get("calls", [])]
    base = _json(run_dir / "snap-base.json", {})
    final = _json(run_dir / "snap-final.json", {})
    tests_final = _json(run_dir / "tests-final.json", {}).get("tests", {})
    breaks = breaks_of(run_dir, meta)
    try:
        diff = (run_dir / "diff.patch").read_text(encoding="utf-8", errors="replace")
    except OSError:
        diff = ""

    invalid = []
    if not calls or any(c["result"] is None for c in calls):
        invalid.append("a call did not finish")
    if any(c["is_error"] and API_FAILURE.search(c["result_text"]) for c in calls):
        invalid.append("API failure")
    # Every /compact must have compacted: from its own stream, else from the transcripts.
    wanted = sum(1 for c in calls if c["kind"] == "compact")
    seen = sum(1 for c in calls if c["kind"] == "compact" and c["compacted"])
    if seen < wanted:
        seen = max(seen, sum(transcript_compactions(t) for t in run_dir.glob("transcript*.jsonl")))
    compacted = seen >= wanted
    if not compacted:
        invalid.append("no compaction")
    # A restart must start a session claude has not seen in this run.
    for brk in breaks:
        if brk["kind"] != "restart":
            continue
        earlier = {c["session_id"] for c in calls[: brk["at"]]}
        later = calls[brk["at"]]["session_id"] if brk["at"] < len(calls) else ""
        if not later or later in earlier:
            invalid.append("restart did not start a new session")
    loaded = set().union(*(set(c["plugins"]) for c in calls)) if calls else set()
    if meta.get("arm") == "hafiz" and "hafiz" not in loaded:
        invalid.append("hafiz arm without hafiz")
    if meta.get("arm") == "plain" and "hafiz" in loaded:
        invalid.append("plain arm with hafiz")

    decisions = [{"id": s["id"], "ok": check(s, tests_final, diff, base, final)}
                 for s in task.get("decisions", [])]
    open_work = [{"id": s["id"], "ok": check(s, tests_final, diff, base, final)}
                 for s in task.get("open", [])]
    deferred = task["deferred_test"]
    path = deferred.rsplit(".", 2)[0].replace(".", "/") + ".py"
    fixed_early = bool(breaks) and breaks[0]["tests"].get(deferred) == "pass"
    test_edited = test_source(base.get(path), deferred) != test_source(final.get(path), deferred)
    open_work.append({"id": "deferred-test-fixed",
                      "ok": None if fixed_early
                      else tests_final.get(deferred) == "pass" and not test_edited})
    done = [{"id": s["id"], "ok": check(s, tests_final, diff, base, final)} for s in task.get("done", [])]

    redo = redone(task, base, breaks, final, tests_final)
    no_redo = 0.0 if any(redo.values()) else 1.0

    groups = {"decisions": _mean(c["ok"] for c in decisions),
              "open_work": _mean(c["ok"] for c in open_work),
              "no_redo": no_redo}

    first = breaks[0]["at"] if breaks else len(calls)
    after = [c for c in calls[first:] if c["kind"] == "say"]

    def after_sum(*keys):
        return sum(c[k] or 0 for c in after for k in keys)

    # What hafiz gives back at a break: the SessionStart hook after a compaction (source "compact"),
    # and the start card of the new session after a restart.
    restore = sum(h["chars"] for c in calls for h in c["hooks"] if h["name"] == "SessionStart:compact")
    restart_card = sum(h["chars"] for b in breaks if b["kind"] == "restart" and b["at"] < len(calls)
                       for h in calls[b["at"]]["hooks"] if h["name"] == "SessionStart:startup")
    hook_chars = sum(h["chars"] for c in calls for h in c["hooks"])
    return {
        "task": meta.get("task", task["id"]), "arm": meta.get("arm", ""), "run": meta.get("run"),
        "version": meta.get("version", 1),
        "valid": not invalid, "invalid": invalid, "compacted": compacted,
        "breaks": [b["kind"] for b in breaks],
        "continuity": _mean(groups.values()), **groups,
        "checks": {"decisions": decisions, "open_work": open_work, "done": done},
        "fixed_early": fixed_early, "test_edited": test_edited, "redo": redo,
        "cost_usd": round(sum(c["cost_usd"] or 0 for c in calls), 4),
        "tokens_after": after_sum("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"),
        "output_tokens_after": after_sum("output_tokens"),
        "turns_after": after_sum("turns"),
        "first_prompt_after": after[0]["first_prompt_tokens"] if after else None,
        "restore_chars": restore, "restart_card_chars": restart_card, "hook_chars": hook_chars,
    }


# ---- many runs ------------------------------------------------------------------------------------

def _fmt(value, digits=2):
    return "-" if value is None else f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _spread(values):
    values = [v for v in values if v is not None]
    if not values:
        return None, None
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0)


def _arm_summary(rows: list[dict], arm: str) -> dict:
    mine = [r for r in rows if r["arm"] == arm and r["valid"]]
    cont, sd = _spread(r["continuity"] for r in mine)
    return {
        "runs": len(mine), "invalid": sum(1 for r in rows if r["arm"] == arm and not r["valid"]),
        "continuity": cont, "continuity_sd": sd,
        **{g: _spread(r[g] for r in mine)[0] for g in ("decisions", "open_work", "no_redo")},
        "cost_usd": sum(r["cost_usd"] for r in rows if r["arm"] == arm),
        "tokens_after": _spread(r["tokens_after"] for r in mine)[0],
        "first_prompt_after": _spread(r["first_prompt_after"] for r in mine)[0],
        "restore_chars": _spread(r["restore_chars"] for r in mine)[0],
        "restart_card_chars": _spread(r.get("restart_card_chars", 0) for r in mine)[0],
        "hook_chars": _spread(r["hook_chars"] for r in mine)[0],
    }


def summarize(rows: list[dict]) -> dict:
    """Per arm: valid runs, the mean of each score and the cost, and hafiz's added context."""
    return {arm: _arm_summary(rows, arm) for arm in sorted({r["arm"] for r in rows})}


def by_task(rows: list[dict]) -> dict:
    """The same per task and arm: a difference can hide in one kind of break."""
    pairs = sorted({(r["task"], r["arm"]) for r in rows})
    return {(task, arm): _arm_summary([r for r in rows if r["task"] == task], arm) for task, arm in pairs}


def markdown(rows: list[dict]) -> str:
    lines = ["| Arm | Valid runs | Continuity | Decisions kept | Open work done | No redo | "
             "Restore note (chars) | Start card after restart (chars) | All hafiz context (chars) | "
             "1st request after the first break (tokens) | Tokens after the first break | Cost (USD) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm, s in summarize(rows).items():
        lines.append(
            f"| {arm} | {s['runs']} ({s['invalid']} invalid) | {_fmt(s['continuity'])} "
            f"± {_fmt(s['continuity_sd'])} | {_fmt(s['decisions'])} | {_fmt(s['open_work'])} | "
            f"{_fmt(s['no_redo'])} | {_fmt(s['restore_chars'], 0)} | {_fmt(s['restart_card_chars'], 0)} | "
            f"{_fmt(s['hook_chars'], 0)} | {_fmt(s['first_prompt_after'], 0)} | "
            f"{_fmt(s['tokens_after'], 0)} | {_fmt(s['cost_usd'])} |")
    lines += ["", "| Task | Arm | Valid runs | Continuity | Decisions kept | Open work done | No redo | "
              "Cost (USD) |", "|---|---|---|---|---|---|---|---|"]
    for (task, arm), s in by_task(rows).items():
        lines.append(f"| {task} | {arm} | {s['runs']} ({s['invalid']} invalid) | {_fmt(s['continuity'])} | "
                     f"{_fmt(s['decisions'])} | {_fmt(s['open_work'])} | {_fmt(s['no_redo'])} | "
                     f"{_fmt(s['cost_usd'])} |")
    lines += ["", "| Task | Arm | Run | Continuity | Decisions | Open work | No redo | Failed checks |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["task"], r["arm"], r["run"] or 0)):
        failed = [c["id"] for group in ("decisions", "open_work") for c in r["checks"][group]
                  if c["ok"] is False]
        failed += [f"redo {kind} {x}" for kind in ("broken", "rewritten", "duplicated")
                   for x in r["redo"].get(kind, [])]
        note = ", ".join(failed) if r["valid"] else "invalid: " + "; ".join(r["invalid"])
        lines.append(f"| {r['task']} | {r['arm']} | {r['run']} | {_fmt(r['continuity'])} | "
                     f"{_fmt(r['decisions'])} | {_fmt(r['open_work'])} | {_fmt(r['no_redo'])} | {note} |")
    return "\n".join(lines) + "\n"
