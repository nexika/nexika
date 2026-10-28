#!/usr/bin/env python3
"""Which tool calls were denied in agent benchmark runs, and why; and the same arm compared across two
result folders (before and after a change), with bench.py summary's paired statistics.

  denials.py kinds HOME [--arm B]            every denied call, grouped by the reason it was denied
  denials.py compare BEFORE AFTER [--arm B]  paired comparison of one arm in two result folders

HOME, BEFORE and AFTER are $AGENTBENCH_HOME folders (results.csv and runs/<run>/stream.jsonl).

In an unattended run every permission prompt is denied. The reason is the denying hook's own text: in
the tool result when the hook refused, or in the PreToolUse hook_response that asked (Claude Code then
writes only "no approval surface" in the tool result). Used for #386.
"""

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agentbench import summary  # noqa: E402

BOOL = {"True": True, "False": False}
UNKNOWN = "(no reason recorded)"


def _events(lines):
    for line in lines:
        line = line.strip()
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event


def _blocks(event):
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _hook_reason(event):
    """The reason a PreToolUse hook gave for "ask" or "deny", or None."""
    if event.get("subtype") != "hook_response" or event.get("hook_event") != "PreToolUse":
        return None
    try:
        out = json.loads(event.get("stdout") or event.get("output") or "")
    except ValueError:
        return None
    spec = out.get("hookSpecificOutput") if isinstance(out, dict) else None
    if isinstance(spec, dict) and spec.get("permissionDecision") in ("ask", "deny"):
        return str(spec.get("permissionDecisionReason") or "")
    return None


def _text(content):
    if isinstance(content, list):
        return " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return str(content or "")


def denied_calls(lines):
    """[{tool, input, reason}] for every call listed in the run's result event as denied."""
    events = list(_events(lines))
    result = [e for e in events if e.get("type") == "result"]
    denied = {d.get("tool_use_id"): d for d in (result[-1].get("permission_denials") or [] if result else [])
              if isinstance(d, dict)}
    reasons, pending = {}, None
    for event in events:
        hook = _hook_reason(event)
        if hook is not None:
            pending = hook
        for block in _blocks(event):
            if block.get("type") == "tool_use":
                pending = None
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in denied:
                text = _text(block.get("content"))
                found = re.search(r"hook error: (haris: .*)", text, re.S)
                reasons[block["tool_use_id"]] = found.group(1) if found else pending
    return [{"tool": d.get("tool_name"), "input": d.get("tool_input"),
             "reason": reasons.get(uid) or UNKNOWN} for uid, d in denied.items()]


def kind(reason):
    """The reason's first sentence, with the parts that differ from call to call (program names in
    backticks, file paths) left out, so the same rule groups together."""
    reason = re.sub(r"^\w+: ", "", reason.strip())
    first = re.split(r"(?<=[.!?])\s", reason, maxsplit=1)[0]
    first = re.sub(r"`[^`]*`", "`…`", first)
    return re.sub(r"\s*\([^)]*\)", "", first)


def load(home, arm, label):
    rows = []
    with open(Path(home) / "results.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["arm"] != arm:
                continue
            row = {k: BOOL.get(v, None if v == "" else v) for k, v in row.items()}
            row["arm"] = label
            row["tokens"] = sum(float(row.get(k) or 0) for k in (
                "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))
            row["any_denial"] = float(row.get("permission_denials") or 0) > 0
            rows.append(row)
    return rows


def run_denials(home, arm):
    """{run name: [denied calls]} for the arm's runs that have a stream."""
    out = {}
    for stream in sorted(Path(home, "runs").glob(f"*__{arm}__r*/stream.jsonl")):
        with open(stream, errors="replace") as fh:
            calls = denied_calls(fh)
        if calls:
            out[stream.parent.name] = calls
    return out


def kinds_table(by_run):
    calls, runs = Counter(), defaultdict(set)
    for name, denied in by_run.items():
        for call in denied:
            calls[kind(call["reason"])] += 1
            runs[kind(call["reason"])].add(name)
    lines = ["| Reason | Denied calls | Runs |", "|---|---|---|"]
    lines += [f"| {k} | {n} | {len(runs[k])} |" for k, n in calls.most_common()]
    return "\n".join(lines)


MEASURES = ("permission_denials", "any_denial", "resolved", "regression", "cost_usd", "tokens",
            "tool_calls", "ran_tests")
PERCENT = ("any_denial", "resolved", "regression", "ran_tests")


def _fmt(value, name, diff=False):
    """bench.py summary's formats, with two decimals for counts (denials per task are well under 1)."""
    unit = "resolved" if name in PERCENT else name
    if value is not None and unit not in ("resolved", "cost_usd", "tokens"):
        return f"{value:+.2f}" if diff else f"{value:.2f}"
    return summary._fmt_diff(value, unit) if diff else summary._fmt(value, unit)


def compare(before, after):
    """bench.py summary's paired comparison (tasks with a valid run in both, bootstrap 95% intervals,
    exact sign test), with "A" = before and "B" = after."""
    rows = before + after
    lines = ["| Measure (mean per task) | Before | After | After − before | 95% interval |",
             "|---|---|---|---|---|"]
    for name in MEASURES:
        _tasks, a, b = summary.paired(rows, name)
        diffs = [y - x for x, y in zip(a, b, strict=True)]
        lo, hi = summary.bootstrap_ci(diffs)
        a, b, d = (statistics.fmean(v) if v else None for v in (a, b, diffs))
        interval = f"{_fmt(lo, name, True)} to {_fmt(hi, name, True)}" if lo is not None else "–"
        lines.append(f"| {name} | {_fmt(a, name)} | {_fmt(b, name)} | {_fmt(d, name, True)} | {interval} |")
    lines.append("")
    for key in ("resolved", "regression", "any_denial"):
        tasks, a, b = summary.paired(rows, key)
        up, down = sum(y > x for x, y in zip(a, b, strict=True)), \
            sum(y < x for x, y in zip(a, b, strict=True))
        p = summary.sign_test(up, down)
        lines.append(f"- {key}: {len(tasks)} tasks; only after {up}, only before {down}"
                     + (f" (exact sign test p = {p:.2g})" if p is not None else ""))
    for label, arm in (("Before", "A"), ("After", "B")):
        valid = [r for r in rows if r["arm"] == arm and r.get("valid")]
        total = sum(float(r.get("permission_denials") or 0) for r in valid)
        lines.append(f"- {label}: {len(valid)} valid runs, {total:.0f} denials in all, "
                     f"cost per resolved task {_fmt(summary.cost_per_success(rows, arm), 'cost_usd')}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kinds")
    k.add_argument("home")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    for p in (k, c):
        p.add_argument("--arm", default="B")
    args = parser.parse_args(argv)
    if args.cmd == "kinds":
        by_run = run_denials(args.home, args.arm)
        print(kinds_table(by_run))
        print(f"\n{sum(map(len, by_run.values()))} denied calls in {len(by_run)} runs")
    else:
        print(compare(load(args.before, args.arm, "A"), load(args.after, args.arm, "B")))


if __name__ == "__main__":
    main()
