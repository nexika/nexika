#!/usr/bin/env python3
"""siyaq relevance benchmark (#452): for 100 labelled prompts, does siyaq load the doc sections that help,
and nothing when nothing helps? Offline, no model calls, a few seconds.

    python3 benchmarks/siyaq/bench.py                  # the report as Markdown
    python3 benchmarks/siyaq/bench.py --json           # the same as JSON, with every prompt
    python3 benchmarks/siyaq/bench.py --check          # exit 1 if a prompt right in the baseline is now wrong
    python3 benchmarks/siyaq/bench.py --save-baseline  # after a change that gets more right
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORPUS = HERE / "corpus"
PROMPTS = HERE / "prompts.tsv"
BASELINE = HERE / "baseline.json"
sys.path.insert(0, str(REPO / "plugins" / "siyaq"))

from siyaq import index as idx  # noqa: E402
from siyaq import rank, text  # noqa: E402


def load_prompts(path: Path = PROMPTS) -> list[dict]:
    """[{"line", "prompt", "relevant": ["source :: heading", ...]}]; an empty list: nothing should load."""
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        prompt, labels = line.split("\t")
        relevant = [] if labels.strip() == "-" else [x.strip() for x in labels.split(" | ")]
        out.append({"line": n, "prompt": prompt, "relevant": relevant})
    return out


def build_corpus(where: Path) -> Path:
    """The snapshot as a git repo (siyaq knows git repos only): corpus/<path>.txt becomes <path>."""
    root = where / "repo"
    for f in CORPUS.rglob("*.txt"):
        dest = root / f.relative_to(CORPUS).with_suffix("")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.read_bytes())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def resolve(label: str, entries: list[dict]) -> list[str]:
    """The ids of the entries a label names: its source, and a title that is or ends with the heading."""
    source, heading = (s.strip() for s in label.split("::", 1))
    return [e["id"] for e in entries
            if e["source"] == source and (e["title"] == heading or e["title"].endswith(" > " + heading))]


def picks(index: dict, prompt: str, cfg: dict) -> list[dict]:
    """What the UserPromptSubmit hook would inject at the start of a session (nothing shown before)."""
    typed = text.typed_words(prompt)
    if typed.startswith("/"):
        typed = typed.split(maxsplit=1)[1] if " " in typed else ""
    return rank.select_for_prompt(index, typed, cfg, {}) if typed else []


def run() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.get("SIYAQ_HOME")
        os.environ["SIYAQ_HOME"] = str(Path(tmp) / "home")
        try:
            root = build_corpus(Path(tmp))
            index = idx.build(root, {})
        finally:
            if old is None:
                os.environ.pop("SIYAQ_HOME", None)
            else:
                os.environ["SIYAQ_HOME"] = old
    cfg = rank.settings({})
    titles = {e["id"]: e["title"] for e in index["entries"]}
    rows = []
    for case in load_prompts():
        wanted = set()
        for label in case["relevant"]:
            found = resolve(label, index["entries"])
            if not found:
                raise SystemExit(f"prompts.tsv:{case['line']}: no section matches {label!r}")
            wanted.update(found)
        start = time.perf_counter()
        picked = picks(index, case["prompt"], cfg)
        ms = (time.perf_counter() - start) * 1000
        loaded = [p["entry"]["id"] for p in picked]
        good = [i for i in loaded if i in wanted]
        rows.append({
            "line": case["line"], "prompt": case["prompt"], "silent": not wanted,
            "loaded": [titles[i] for i in loaded], "relevant_loaded": len(good), "loaded_n": len(loaded),
            "tokens": sum(len(p["text"]) for p in picked) // rank.CHARS_PER_TOKEN, "ms": round(ms, 2),
            # right: a silent prompt loads nothing; a labelled one loads at least one relevant section
            "right": (not loaded) if not wanted else bool(good),
        })
    return summarise(rows, index)


def summarise(rows: list[dict], index: dict) -> dict:
    silent = [r for r in rows if r["silent"]]
    labelled = [r for r in rows if not r["silent"]]
    loaded = sum(r["loaded_n"] for r in rows)
    relevant = sum(r["relevant_loaded"] for r in rows)
    times = sorted(r["ms"] for r in rows)
    return {
        "entries": index["n"], "sources": len(index["sources"]), "prompts": len(rows),
        "precision": relevant / loaded if loaded else 1.0,  # #391's pass line: >= 70%
        "loaded": loaded, "relevant_loaded": relevant,
        "found": sum(r["right"] for r in labelled), "labelled": len(labelled),
        "quiet": sum(r["right"] for r in silent), "silent": len(silent),
        "tokens_per_prompt": sum(r["tokens"] for r in rows) / len(rows),
        "median_ms": times[len(times) // 2],
        "rows": rows,
    }


def regressions(report: dict, baseline: dict) -> list[str]:
    lost = [f"prompts.tsv:{r['line']} {r['prompt']!r} now loads {r['loaded'] or 'nothing'}"
            for r in report["rows"] if r["prompt"] in set(baseline.get("right", [])) and not r["right"]]
    if round(report["precision"], 4) < baseline.get("precision", 0):  # the baseline keeps 4 decimals
        lost.append(f"precision dropped: {baseline['precision']:.1%} -> {report['precision']:.1%}")
    return lost


def markdown(r: dict) -> str:
    pct = lambda a, b: f"{a}/{b} = {a / b:.0%}" if b else "-"  # noqa: E731
    lines = [
        f"siyaq relevance: {r['prompts']} prompts over {r['entries']} sections from {r['sources']} docs",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Precision: loaded sections that are relevant (pass line 70%) "
        f"| {pct(r['relevant_loaded'], r['loaded'])} |",
        f"| Labelled prompts with a relevant section loaded | {pct(r['found'], r['labelled'])} |",
        f"| Prompts that need nothing and got nothing | {pct(r['quiet'], r['silent'])} |",
        f"| Tokens added per prompt (mean) | {r['tokens_per_prompt']:.0f} |",
        f"| Time per prompt (median) | {r['median_ms']:.1f} ms |",
        "",
        "Wrong:",
    ]
    for row in r["rows"]:
        if not row["right"] or row["relevant_loaded"] < row["loaded_n"]:
            what = "; ".join(row["loaded"]) or "nothing"
            lines.append(f"- {'MISS' if not row['right'] else 'extra'} line {row['line']}: "
                         f"{row['prompt']!r} -> {what}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--save-baseline", action="store_true")
    args = ap.parse_args(argv)
    report = run()
    if args.save_baseline:
        BASELINE.write_text(json.dumps({"precision": round(report["precision"], 4),
                                        "right": [r["prompt"] for r in report["rows"] if r["right"]]},
                                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.check:
        lost = regressions(report, json.loads(BASELINE.read_text(encoding="utf-8")))
        print("\n".join(lost) or "no regressions")
        return 1 if lost else 0
    print(json.dumps(report, ensure_ascii=False, indent=1) if args.json else markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
