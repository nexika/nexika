"""Turn runs and grades into results.csv and a paired comparison of arm A and arm B.

Pairs are tasks: each task's runs in one arm are averaged, and only tasks with a valid run in
both arms are compared. Intervals are 95% bootstrap intervals over tasks, so they show how much
the result could move with another sample of tasks of the same kind.
"""

import csv
import random
import statistics
from collections import defaultdict

COLUMNS = (
    "instance_id", "repo", "difficulty", "arm", "run", "valid", "invalid_reason",
    "resolved", "regression", "applied", "f2p_pass", "f2p_fail", "p2p_pass", "p2p_fail",
    "cost_usd", "wall_s", "duration_ms", "turns", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "tool_calls", "bash_calls", "failed_tool_calls",
    "permission_denials", "hook_runs", "hook_errors", "files_changed", "lines_added",
    "lines_removed", "result", "timed_out", "model", "claude_version", "nexika_sha",
    "base_commit", "session_id",
)

MEASURES = (  # (name, row key, better when)
    ("resolved", "resolved", "higher"),
    ("regression", "regression", "lower"),
    ("cost_usd", "cost_usd", "lower"),
    ("wall_s", "wall_s", "lower"),
    ("tokens", "tokens", "lower"),
    ("tool_calls", "tool_calls", "lower"),
    ("failed_tool_calls", "failed_tool_calls", "lower"),
    ("permission_denials", "permission_denials", "lower"),
)


def merge(metas, grades):
    rows = []
    for meta in metas:
        grade = grades.get((meta["instance_id"], meta["arm"], meta["run"]), {})
        row = {**meta, **grade}
        row["tokens"] = sum(row.get(k) or 0 for k in ("input_tokens", "output_tokens",
                                                       "cache_read_tokens", "cache_write_tokens"))
        rows.append(row)
    return rows


def write_csv(rows, path):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in COLUMNS})


def _num(value):
    if value is None or value == "":
        return None
    return float(value)


def per_task(rows, key):
    """{task: {arm: mean over that arm's valid runs}}, skipping missing values."""
    values = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if not row.get("valid"):
            continue
        value = _num(row.get(key))
        if value is not None:
            values[row["instance_id"]][row["arm"]].append(value)
    return {task: {arm: statistics.fmean(v) for arm, v in arms.items()} for task, arms in values.items()}


def paired(rows, key):
    by_task = per_task(rows, key)
    tasks = sorted(t for t, arms in by_task.items() if "A" in arms and "B" in arms)
    return tasks, [by_task[t]["A"] for t in tasks], [by_task[t]["B"] for t in tasks]


def bootstrap_ci(diffs, seed=333, n=2000):
    if not diffs:
        return None, None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def compare(rows):
    out = {}
    for name, key, better in MEASURES:
        tasks, a, b = paired(rows, key)
        diffs = [y - x for x, y in zip(a, b, strict=True)]
        lo, hi = bootstrap_ci(diffs)
        out[name] = {
            "tasks": len(tasks), "better": better,
            "A": statistics.fmean(a) if a else None, "B": statistics.fmean(b) if b else None,
            "diff": statistics.fmean(diffs) if diffs else None, "ci": (lo, hi),
        }
    return out


def cost_per_success(rows, arm):
    valid = [r for r in rows if r.get("valid") and r["arm"] == arm]
    spent = sum(_num(r.get("cost_usd")) or 0 for r in valid)
    wins = sum(1 for r in valid if r.get("resolved"))
    return spent / wins if wins else None


def by_difficulty(rows):
    table = defaultdict(lambda: {"A": [0, 0], "B": [0, 0]})
    for row in rows:
        if row.get("valid"):
            cell = table[row["difficulty"]][row["arm"]]
            cell[0] += bool(row.get("resolved"))
            cell[1] += 1
    return dict(table)


def _fmt(value, name):
    if value is None:
        return "–"
    if name in ("resolved", "regression"):
        return f"{value * 100:.0f}%"
    if name == "cost_usd":
        return f"${value:.2f}"
    if name == "tokens":
        return f"{value / 1000:.0f}k"
    return f"{value:.1f}"


def _fmt_diff(value, name):
    if value is None:
        return "–"
    if name in ("resolved", "regression"):
        return f"{value * 100:+.0f} pts"
    if name == "cost_usd":
        return f"{'+' if value >= 0 else '-'}${abs(value):.2f}"
    if name == "tokens":
        return f"{value / 1000:+.0f}k"
    return f"{value:+.1f}"


def markdown(rows, pilot):
    comp = compare(rows)
    valid = [r for r in rows if r.get("valid")]
    invalid = [r for r in rows if not r.get("valid")]
    lines = [
        f"# Agent benchmark: {pilot}",
        "",
        f"Runs: {len(rows)} ({len(valid)} valid). Tasks compared in both arms: {comp['resolved']['tasks']}.",
        "",
        "| Measure (mean per task) | A: Claude Code | B: + Nexika | B − A | 95% interval |",
        "|---|---|---|---|---|",
    ]
    for name, _key, better in MEASURES:
        c = comp[name]
        lo, hi = c["ci"]
        interval = f"{_fmt_diff(lo, name)} to {_fmt_diff(hi, name)}" if lo is not None else "–"
        lines.append(f"| {name} ({better} is better) | {_fmt(c['A'], name)} | {_fmt(c['B'], name)} "
                     f"| {_fmt_diff(c['diff'], name)} | {interval} |")
    cost = comp["cost_usd"]
    if cost["A"]:
        reduction = (cost["A"] - cost["B"]) / cost["A"] * 100
        lines += ["", f"Relative cost reduction (C_A − C_B) / C_A: {reduction:+.0f}%."]
    cps = {arm: cost_per_success(rows, arm) for arm in ("A", "B")}
    lines.append(f"Cost per resolved task: A {_fmt(cps['A'], 'cost_usd')}, B {_fmt(cps['B'], 'cost_usd')}.")
    lines += ["", "| Difficulty | A resolved | B resolved |", "|---|---|---|"]
    for difficulty, cells in sorted(by_difficulty(rows).items()):
        lines.append(f"| {difficulty} | {cells['A'][0]}/{cells['A'][1]} | {cells['B'][0]}/{cells['B'][1]} |")
    if invalid:
        lines += ["", "Left out of the comparison:"]
        lines += [f"- {r['instance_id']} arm {r['arm']} run {r['run']}: {r.get('invalid_reason')}"
                  for r in invalid]
    lines += ["", "An interval that contains 0 means this sample cannot tell the arms apart on that measure."]
    return "\n".join(lines) + "\n"
