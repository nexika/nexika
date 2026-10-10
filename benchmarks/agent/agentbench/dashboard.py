"""One self-contained HTML page with every pilot: progress, each arm against A, and the context cost.

Only graded runs count: a run that has not been graded yet is left out instead of counted as not
resolved, so a pilot that is still running shows partial numbers, labelled as such. The statistics
are summary's (paired by task, bootstrap intervals over tasks, exact sign test).
"""

import html
import json
import statistics
import time
from pathlib import Path

from . import summary


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def find_pilots(root):
    """Folders under root that hold a pilot's runs or results, in name order."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir()
                  if p.is_dir() and ((p / "runs").is_dir() or (p / "results.csv").is_file()))


def _arm_values(rows, key, arm):
    by_task = summary.per_task(rows, key)
    return [arms[arm] for arms in by_task.values() if arm in arms]


def _mean(values):
    return statistics.fmean(values) if values else None


def _arm_view(rows, arm):
    resolved = _arm_values(rows, "resolved", arm)
    lo, hi = summary.bootstrap_ci(resolved)
    view = {
        "arm": arm, "tasks": len(resolved), "resolved": _mean(resolved), "ci": (lo, hi),
        "regression": _mean(_arm_values(rows, "regression", arm)),
        "ran_tests": _mean(_arm_values(rows, "ran_tests", arm)),
        "cost_run": _mean(_arm_values(rows, "cost_usd", arm)),
        "cost_solved": summary.cost_per_success(rows, arm),
        "first_prompt": _mean(_arm_values(rows, "first_prompt_tokens", arm)),
        "diff": None, "diff_ci": (None, None), "wins": None, "losses": None, "p": None,
        "first_prompt_extra": None,
    }
    if arm != "A":
        comp = summary.compare(rows, arm)
        wins, losses = summary.wins_losses(rows, arm)
        view.update(diff=comp["resolved"]["diff"], diff_ci=comp["resolved"]["ci"], wins=wins,
                    losses=losses, p=summary.sign_test(wins, losses),
                    first_prompt_extra=comp["first_prompt_tokens"]["diff"])
    return view


ACTIVE_S = 30 * 60   # a run written in the last half hour: the pilot is still running


def pilot_view(base, planned_tasks=None, note="", now=None):
    """Plain numbers for one pilot folder. planned_tasks: the pilot file's task count, if known."""
    base = Path(base)
    paths = sorted((base / "runs").glob("*/meta.json"))
    metas = [m for m in (_read_json(p, None) for p in paths) if isinstance(m, dict)]
    newest = max((p.stat().st_mtime for p in paths), default=0)
    grades = {(g["instance_id"], g["arm"], g["run"]): g for g in _read_json(base / "grades.json", [])}
    rows = summary.merge(metas, grades)
    graded = [r for r in rows if (r["instance_id"], r["arm"], r["run"]) in grades]
    arms_seen = summary.arms_in(rows)
    runs = max((m.get("run") or 1 for m in metas), default=0)
    planned = planned_tasks * len(arms_seen) * runs if planned_tasks and metas else None
    done = len(metas)
    return {
        "name": base.name, "note": note, "done": done, "planned": planned, "graded": len(graded),
        "partial": len(graded) < done or (planned is not None and done < planned),
        "active": bool(paths) and (time.time() if now is None else now) - newest < ACTIVE_S,
        "cost": sum(m.get("cost_usd") or 0 for m in metas),
        "invalid": sum(1 for m in metas if not m.get("valid")),
        "excluded": len(_read_json(base / "excluded.json", {})),
        "arms": [_arm_view(graded, arm) for arm in summary.arms_in(graded)],
        "difficulty": summary.by_difficulty(graded),
    }


def context_rows(base):
    """The first request's size per context session (pilot/context/<arm>/meta.json): A, then all of
    Nexika (B), then each plugin alone, most costly first. extra is the size minus A's."""
    sizes = {}
    for path in sorted((Path(base) / "context").glob("*/meta.json")):
        meta = _read_json(path, {})
        if meta.get("first_prompt_tokens"):
            sizes[path.parent.name] = (meta["first_prompt_tokens"], meta.get("hook_output_chars") or 0)
    if "A" not in sizes:
        return []
    baseline = sizes["A"][0]
    rows = [{"name": n, "tokens": t, "extra": t - baseline, "hook_chars": c} for n, (t, c) in sizes.items()]
    order = {"A": 0, "B": 1}
    return sorted(rows, key=lambda r: (order.get(r["name"], 2), -r["extra"], r["name"]))


# --- HTML ------------------------------------------------------------------------------------

CSS = """
:root { --bg: #fcfcfb; --surface: #ffffff; --text: #0b0b0b; --muted: #52514e; --line: #e4e3df;
  --track: #efeeea; --bar: #2a78d6; --base: #8a8984; --good: #006300; --warn: #8a5a00; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #1a1a19; --surface: #222220; --text: #f0efec; --muted: #c3c2b7; --line: #383835;
    --track: #2c2c2a; --bar: #3987e5; --base: #9a9990; --good: #0ca30c; --warn: #e0a42c; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.5rem; margin: 0 0 4px; } h2 { font-size: 1.2rem; margin: 0; }
h3 { font-size: 1rem; margin: 20px 0 8px; color: var(--muted); font-weight: 600; }
.sub { color: var(--muted); margin: 0 0 24px; }
section { background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px; margin: 0 0 20px; }
.head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 12px; }
.badge { font-size: .8rem; padding: 2px 8px; border-radius: 999px; border: 1px solid currentColor; }
.badge.done { color: var(--good); } .badge.partial { color: var(--warn); }
.progress { color: var(--muted); margin: 6px 0 0; }
.note { margin: 6px 0 0; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; white-space: normal; min-width: 7rem; }
th.arm { white-space: normal; min-width: 7rem; }
th { color: var(--muted); font-weight: 600; }
.bars { display: grid; gap: 10px; } .bars > div { min-width: 0; }
.bar-label { display: flex; justify-content: space-between; gap: 8px; font-size: .9rem; }
.bar-label .arm { min-width: 0; } .bar-label .val { color: var(--muted); white-space: nowrap; }
svg.bar { display: block; width: 100%; height: 14px; }
.axis { display: flex; justify-content: space-between; color: var(--muted); font-size: .75rem; }
.foot { color: var(--muted); font-size: .85rem; }
"""


def _e(text):
    return html.escape(str(text))


def _arm(name):
    """An arm name that may break after each "+" (the lean arm names eight plugins)."""
    return _e(name).replace("+", "+<wbr>")


def _pct(value):
    return summary._fmt(value, "resolved")


def _money(value):
    return summary._fmt(value, "cost_usd")


def _interval(lo, hi, name):
    if lo is None:
        return ""
    return f"{summary._fmt_diff(lo, name)} to {summary._fmt_diff(hi, name)}"


def _bar(arm):
    value = arm["resolved"] or 0
    lo, hi = arm["ci"]
    colour = "var(--base)" if arm["arm"] == "A" else "var(--bar)"
    interval = f" (95% interval {_pct(lo)} to {_pct(hi)})" if lo is not None else ""
    whisker = ""
    if lo is not None:
        pen = 'stroke="var(--text)" stroke-width="1.5" vector-effect="non-scaling-stroke"'
        whisker = (f'<line x1="{lo * 100:.2f}" x2="{hi * 100:.2f}" y1="5" y2="5" {pen}/>'
                   + "".join(f'<line x1="{x * 100:.2f}" x2="{x * 100:.2f}" y1="2" y2="8" {pen}/>'
                             for x in (lo, hi)))
    return (f'<div><div class="bar-label"><span class="arm">{_arm(arm["arm"])}</span>'
            f'<span class="val">{_pct(value)}{_e(interval)}</span></div>'
            f'<svg class="bar" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" '
            f'aria-label="{_e(arm["arm"])}: {_pct(value)} resolved{_e(interval)}">'
            f'<title>{_e(arm["arm"])}: {_pct(value)} resolved over {arm["tasks"]} tasks{_e(interval)}</title>'
            f'<rect x="0" y="1" width="100" height="8" fill="var(--track)"/>'
            f'<rect x="0" y="1" width="{value * 100:.2f}" height="8" fill="{colour}"/>{whisker}</svg></div>')


def _arms_table(arms):
    head = ("<tr><th>Arm</th><th>Tasks</th><th>Resolved</th><th>vs A</th><th>95% interval</th>"
            "<th>Only arm / only A</th><th>Sign test p</th><th>Regressions</th><th>Ran tests</th>"
            "<th>Cost per run</th><th>Cost per solved</th>"
            "<th>First prompt (A: size, others: extra)</th></tr>")
    body = []
    for a in arms:
        diff = summary._fmt_diff(a["diff"], "resolved") if a["diff"] is not None else "baseline"
        wl = f'{a["wins"]} / {a["losses"]}' if a["wins"] is not None else ""
        p = f'{a["p"]:.2f}' if a["p"] is not None else ""
        if a["first_prompt_extra"] is not None:
            extra = summary._fmt_diff(a["first_prompt_extra"], "first_prompt_tokens")
        else:
            extra = summary._fmt(a["first_prompt"], "first_prompt_tokens")
        body.append(
            f"<tr><td>{_arm(a['arm'])}</td><td>{a['tasks']}</td><td>{_pct(a['resolved'])}</td><td>{diff}</td>"
            f"<td>{_interval(*a['diff_ci'], 'resolved')}</td><td>{wl}</td><td>{p}</td>"
            f"<td>{_pct(a['regression'])}</td><td>{_pct(a['ran_tests'])}</td><td>{_money(a['cost_run'])}</td>"
            f"<td>{_money(a['cost_solved'])}</td><td>{extra}</td></tr>")
    return f'<div class="scroll"><table>{head}{"".join(body)}</table></div>'


def _difficulty_table(table, arms):
    names = [a["arm"] for a in arms]
    head = "<tr><th>Difficulty</th>" + "".join(f'<th class="arm">{_arm(n)}</th>' for n in names) + "</tr>"
    body = "".join(
        f"<tr><td>{_e(d)}</td>" + "".join("<td>{}/{}</td>".format(*cells.get(n, [0, 0])) for n in names)
        + "</tr>" for d, cells in sorted(table.items()))
    return f'<div class="scroll"><table>{head}{body}</table></div>'


def _pilot_section(view):
    if not view["partial"]:
        status = '<span class="badge done">finished</span>'
    elif view["active"]:
        status = '<span class="badge partial">in progress, partial</span>'
    else:
        status = '<span class="badge partial">partial: not every run is graded</span>'
    planned = f' of {view["planned"]}' if view["planned"] else ""
    progress = (f'Runs {view["done"]}{planned}, graded {view["graded"]}. Cost so far {_money(view["cost"])}. '
                f'Invalid runs {view["invalid"]}. Excluded tasks {view["excluded"]}.')
    parts = [f'<section><div class="head"><h2>{_e(view["name"])}</h2>{status}</div>',
             f'<p class="progress">{_e(progress)}</p>']
    if view["note"]:
        parts.append(f'<p class="note">{_e(view["note"])}</p>')
    if view["arms"]:
        parts += ["<h3>Resolved, with a 95% interval over tasks</h3>",
                  '<div class="bars">' + "".join(_bar(a) for a in view["arms"]) + "</div>",
                  '<div class="axis"><span>0%</span><span>50%</span><span>100%</span></div>',
                  "<h3>Each arm against A (Claude Code alone)</h3>", _arms_table(view["arms"]),
                  "<h3>Resolved by difficulty</h3>", _difficulty_table(view["difficulty"], view["arms"])]
    else:
        parts.append('<p class="foot">No graded runs yet.</p>')
    return "".join(parts) + "</section>"


def _context_section(rows):
    head = ("<tr><th>Session</th><th>First request</th><th>Extra vs A</th>"
            "<th>Hook output (characters)</th></tr>")
    names = {"A": "A: Claude Code alone", "B": "B: all of Nexika"}
    body = []
    for r in rows:
        extra = "" if r["name"] == "A" else f"+{r['extra']:,}"
        body.append(f"<tr><td>{_e(names.get(r['name'], r['name']))}</td><td>{r['tokens']:,}</td>"
                    f"<td>{extra}</td><td>{r['hook_chars']:,}</td></tr>")
    body = "".join(body)
    return ('<section><div class="head"><h2>What each plugin adds to every session</h2></div>'
            '<p class="progress">Tokens in the model\'s first request, one short session per plugin, '
            'before any work: skill and agent descriptions plus the hooks\' added context.</p>'
            f'<div class="scroll"><table>{head}{body}</table></div></section>')


def render(views, context, refresh=None, now=""):
    meta = f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else ""
    sections = "".join(_pilot_section(v) for v in views)
    if context:
        sections += _context_section(context)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">{meta}'
            f"<title>Agent benchmark</title><style>{CSS}</style></head><body><main>"
            f"<h1>Agent benchmark: Claude Code alone vs. with Nexika</h1>"
            f'<p class="sub">SWE-bench Verified. Updated {_e(now)}. An interval that contains 0 means the '
            f"sample cannot tell the arms apart.</p>{sections}</main></body></html>\n")
