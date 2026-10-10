"""Score one run of the hafiz benchmark from what bench.py recorded, and summarize many runs.

Standard library only. A run folder holds:

    meta.json                    task, arm, run, session, repo path, the calls in order
    call-<n>.jsonl               claude's stream-json output for each call (steps, /compact, continue)
    transcript.jsonl             the session transcript, copied from the run's throwaway home
    diff.patch                   everything the agent changed, against the starting commit
    snap-{base,compact,final}.json   the repo's text files at the start, before /compact, at the end
    tests-{compact,final}.json   runtests.py output (the repo's tests and the task's hidden checks)

Three groups, each scored from 0 to 1, and the continuity score is their mean:

    decisions   the seeded decisions still hold at the end
    open_work   the plan's open step was done and the deferred failing test was fixed (without
                editing the test)
    no_redo     work finished before the compaction was not redone after it
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


def transcript_compacted(path: Path) -> bool:
    for event in events(path):
        if event.get("isCompactSummary") or event.get("subtype") == "compact_boundary":
            return True
    return False


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


def redone(task: dict, base: dict, compact: dict, final: dict, later_tools: list[dict], repo: str) -> dict:
    """What finished work was done again after the compaction.

    changed     a function or class in a keep_files module that was added or changed before the
                compaction, and is different (or gone) at the end
    rewritten   a file the agent had changed before the compaction, written again whole (Write)
    duplicated  a name defined twice in one module at the end
    """
    changed = []
    for path in task.get("keep_files", []):
        before, start, end = symbols(compact.get(path)), symbols(base.get(path)), symbols(final.get(path))
        for name, dumps in before.items():
            if dumps == start.get(name):
                continue  # not touched before the compaction: changing it later is new work
            if end.get(name) != dumps:
                changed.append(f"{path}:{name}")
    worked_on = {p for p in compact if compact.get(p) != base.get(p)}
    rewritten = set()
    prefix = repo.rstrip("/") + "/"
    for tool in later_tools:
        if tool.get("name") != "Write":
            continue
        path = str((tool.get("input") or {}).get("file_path") or "")
        path = path[len(prefix):] if path.startswith(prefix) else path
        if path in worked_on:
            rewritten.add(path)
    duplicated = [f"{path}:{name}" for path, text in sorted(final.items()) if path.endswith(".py")
                  for name, dumps in symbols(text).items() if len(dumps) > 1]
    return {"changed": sorted(changed), "rewritten": sorted(rewritten), "duplicated": duplicated}


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

def score_run(run_dir: Path, task: dict) -> dict:
    run_dir = Path(run_dir)
    meta = _json(run_dir / "meta.json", {})
    calls = [dict(read_call(run_dir / c["file"]), phase=c["phase"]) for c in meta.get("calls", [])]
    base = _json(run_dir / "snap-base.json", {})
    compact = _json(run_dir / "snap-compact.json", {})
    final = _json(run_dir / "snap-final.json", {})
    tests_compact = _json(run_dir / "tests-compact.json", {}).get("tests", {})
    tests_final = _json(run_dir / "tests-final.json", {}).get("tests", {})
    try:
        diff = (run_dir / "diff.patch").read_text(encoding="utf-8", errors="replace")
    except OSError:
        diff = ""

    compact_calls = [c for c in calls if c["phase"] == "compact"]
    compacted = any(c["compacted"] for c in compact_calls) or (
        bool(compact_calls) and transcript_compacted(run_dir / "transcript.jsonl"))
    invalid = []
    if not calls or any(c["result"] is None for c in calls):
        invalid.append("a call did not finish")
    if any(c["is_error"] and API_FAILURE.search(c["result_text"]) for c in calls):
        invalid.append("API failure")
    if not compacted:
        invalid.append("no compaction")
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
    fixed_early = tests_compact.get(deferred) == "pass"
    test_edited = test_source(base.get(path), deferred) != test_source(final.get(path), deferred)
    open_work.append({"id": "deferred-test-fixed",
                      "ok": None if fixed_early
                      else tests_final.get(deferred) == "pass" and not test_edited})
    done = [{"id": s["id"], "ok": check(s, tests_final, diff, base, final)} for s in task.get("done", [])]

    later = [t for c in calls if c["phase"] == "continue" for t in c["tool_uses"]]
    redo = redone(task, base, compact, final, later, meta.get("repo", ""))
    no_redo = 0.0 if any(redo.values()) else 1.0

    groups = {"decisions": _mean(c["ok"] for c in decisions),
              "open_work": _mean(c["ok"] for c in open_work),
              "no_redo": no_redo}

    def phase_sum(key, phases):
        return sum(c[key] or 0 for c in calls if c["phase"] in phases)

    # The restore is the SessionStart hook that runs with source "compact".
    restore = sum(h["chars"] for c in calls for h in c["hooks"] if h["name"] == "SessionStart:compact")
    hook_chars = sum(h["chars"] for c in calls for h in c["hooks"])
    later_calls = [c for c in calls if c["phase"] == "continue"]
    return {
        "task": meta.get("task", task["id"]), "arm": meta.get("arm", ""), "run": meta.get("run"),
        "valid": not invalid, "invalid": invalid, "compacted": compacted,
        "continuity": _mean(groups.values()), **groups,
        "checks": {"decisions": decisions, "open_work": open_work, "done": done},
        "fixed_early": fixed_early, "test_edited": test_edited, "redo": redo,
        "cost_usd": round(sum(c["cost_usd"] or 0 for c in calls), 4),
        "tokens_after": sum(phase_sum(k, {"continue"}) for k in (
            "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")),
        "output_tokens_after": phase_sum("output_tokens", {"continue"}),
        "turns_after": phase_sum("turns", {"continue"}),
        "first_prompt_after": later_calls[0]["first_prompt_tokens"] if later_calls else None,
        "restore_chars": restore, "hook_chars": hook_chars,
    }


# ---- many runs ------------------------------------------------------------------------------------

def _fmt(value, digits=2):
    return "-" if value is None else f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _spread(values):
    values = [v for v in values if v is not None]
    if not values:
        return None, None
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0)


def summarize(rows: list[dict]) -> dict:
    """Per arm: valid runs, the mean of each score and the cost, and hafiz's added context."""
    out = {}
    for arm in sorted({r["arm"] for r in rows}):
        mine = [r for r in rows if r["arm"] == arm and r["valid"]]
        cont, sd = _spread(r["continuity"] for r in mine)
        out[arm] = {
            "runs": len(mine), "invalid": sum(1 for r in rows if r["arm"] == arm and not r["valid"]),
            "continuity": cont, "continuity_sd": sd,
            **{g: _spread(r[g] for r in mine)[0] for g in ("decisions", "open_work", "no_redo")},
            "cost_usd": sum(r["cost_usd"] for r in rows if r["arm"] == arm),
            "tokens_after": _spread(r["tokens_after"] for r in mine)[0],
            "first_prompt_after": _spread(r["first_prompt_after"] for r in mine)[0],
            "restore_chars": _spread(r["restore_chars"] for r in mine)[0],
            "hook_chars": _spread(r["hook_chars"] for r in mine)[0],
        }
    return out


def markdown(rows: list[dict]) -> str:
    arms = summarize(rows)
    lines = ["| Arm | Valid runs | Continuity | Decisions kept | Open work done | No redo | "
             "Restore note (chars) | All hafiz context (chars) | 1st request after compaction (tokens) "
             "| Tokens after compaction | Cost (USD) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm, s in arms.items():
        lines.append(
            f"| {arm} | {s['runs']} ({s['invalid']} invalid) | {_fmt(s['continuity'])} "
            f"± {_fmt(s['continuity_sd'])} | {_fmt(s['decisions'])} | {_fmt(s['open_work'])} | "
            f"{_fmt(s['no_redo'])} | {_fmt(s['restore_chars'], 0)} | {_fmt(s['hook_chars'], 0)} | "
            f"{_fmt(s['first_prompt_after'], 0)} | {_fmt(s['tokens_after'], 0)} | {_fmt(s['cost_usd'])} |")
    lines += ["", "| Task | Arm | Run | Continuity | Decisions | Open work | No redo | Failed checks |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["task"], r["arm"], r["run"] or 0)):
        failed = [c["id"] for group in ("decisions", "open_work") for c in r["checks"][group]
                  if c["ok"] is False]
        failed += [f"redo {x}" for kind in ("changed", "rewritten", "duplicated") for x in r["redo"][kind]]
        note = ", ".join(failed) if r["valid"] else "invalid: " + "; ".join(r["invalid"])
        lines.append(f"| {r['task']} | {r['arm']} | {r['run']} | {_fmt(r['continuity'])} | "
                     f"{_fmt(r['decisions'])} | {_fmt(r['open_work'])} | {_fmt(r['no_redo'])} | {note} |")
    return "\n".join(lines) + "\n"
