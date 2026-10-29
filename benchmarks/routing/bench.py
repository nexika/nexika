#!/usr/bin/env python3
"""Skill routing (#431): does a prompt start the skill it should, and leave ordinary work alone?

Shorter skill descriptions save tokens in every session, but the model picks a skill from its
description. This runs each prompt in cases.tsv as a fresh `claude -p` session, with all twelve
Nexika plugins exported from a git ref, and records which skills the model called. Two refs side by
side (main, and a branch with shorter descriptions) show whether routing held.

  bench.py --dry-run                       the cases and the command, no model calls
  bench.py --refs main=origin/main,new=HEAD --runs 3 --model sonnet --out DIR    (paid)
  bench.py --summary DIR                   the report again from saved runs

Each session is isolated: a throwaway HOME and Claude Code config folder, so nothing from the user's
own setup (installed plugins, memory, CLAUDE.md) reaches it. Login comes from CLAUDE_CODE_OAUTH_TOKEN
or ANTHROPIC_API_KEY. Only Skill, Read, Grep and Glob are allowed, and a session stops after
--max-turns turns, so nothing is edited or run.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CASES = HERE / "cases.tsv"
AUTH_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
ALLOWED = ("Skill", "Read", "Grep", "Glob")
DISALLOWED = ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent")

KINDS = ("kept", "dropped", "paraphrase", "negative")

# The small project each suite's prompts run in, so "app.py" or "this page" mean something.
FIXTURES = {}
FIXTURES["prof"] = {
    "README.md": "# tally\n\nCounts words in text files. Run `python3 app.py FILE...`.\n",
    "app.py": '''"""Count words in text files."""
import sys
from collections import Counter


def count_words(text):
    return Counter(word.lower() for word in text.split())


def main(paths):
    total = Counter()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            total += count_words(f.read())
    for word, n in total.most_common(10):
        print(f"{n:5} {word}")


if __name__ == "__main__":
    main(sys.argv[1:])
''',
}
# lawha's session note shows only in a frontend project, as in real use.
FIXTURES["lawha"] = {
    "package.json": json.dumps({
        "name": "shop", "private": True, "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "test": "vitest"},
        "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
        "devDependencies": {"vite": "^5.4.0", "tailwindcss": "^3.4.0", "vitest": "^2.1.0"},
    }, indent=2) + "\n",
    "index.html": '<!doctype html>\n<html lang="en">\n'
                  '<head><meta charset="utf-8"><title>Shop</title></head>\n'
                  '<body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body>\n'
                  "</html>\n",
    "src/main.jsx": 'import { createRoot } from "react-dom/client";\nimport App from "./App.jsx";\n'
                    'import "./index.css";\n\ncreateRoot(document.getElementById("root")).render(<App />);\n',
    "src/index.css": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n",
    "src/App.jsx": '''import { useEffect, useState } from "react";
import Button from "./Button.jsx";
import { formatPrice } from "./price.js";

export default function App() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    fetch("/api/items").then((r) => r.json()).then((data) => setItems(data.items));
  }, []);
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-bold">Shop</h1>
      <ul className="mt-4 space-y-2">
        {items.map((item) => (
          <li key={item.id} className="flex justify-between">
            {item.name} <span>{formatPrice(item.cents)}</span>
          </li>
        ))}
      </ul>
      <Button>Checkout</Button>
    </main>
  );
}
''',
    "src/Button.jsx": '''export default function Button({ children, ...props }) {
  return (
    <button className="mt-6 rounded bg-blue-600 px-4 py-2 text-white" {...props}>
      {children}
    </button>
  );
}
''',
    "src/price.js": "export function formatPrice(cents) {\n  return `$${(cents / 100).toFixed(2)}`;\n}\n",
}

# manar's session note shows only for a website: a small Astro marketing site.
FIXTURES["manar"] = {
    "package.json": json.dumps({
        "name": "billfast-site", "private": True, "type": "module",
        "scripts": {"dev": "astro dev", "build": "astro build"},
        "dependencies": {"astro": "^4.16.0"},
    }, indent=2) + "\n",
    "astro.config.mjs": 'import { defineConfig } from "astro/config";\n\n'
                        'export default defineConfig({ site: "https://billfast.example" });\n',
    "src/layouts/Base.astro": '''---
const { title } = Astro.props;
---
<html lang="en">
  <head><meta charset="utf-8" /><title>{title}</title></head>
  <body><slot /></body>
</html>
''',
    "src/pages/index.astro": '''---
import Base from "../layouts/Base.astro";
---
<Base title="BillFast">
  <section class="hero">
    <h1>Invoicng for small teams</h1>
    <p>Send an invoice in a minute and get paid sooner.</p>
    <a href="/pricing">See pricing</a>
  </section>
</Base>
''',
    "src/pages/pricing.astro": '''---
import Base from "../layouts/Base.astro";
---
<Base title="Pricing - BillFast">
  <h1>Pricing</h1>
  <div class="card"><h2>Solo</h2><p>$9 a month</p></div>
</Base>
''',
    "public/robots.txt": "User-agent: *\nAllow: /\n",
}


def load_cases(path=CASES):
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        suite, expected, kind, prompt = line.split("\t")
        cases.append({"id": len(cases) + 1, "suite": suite, "expected": expected, "kind": kind,
                      "prompt": prompt})
    return cases


def export_plugins(ref, dest, repo=REPO):
    """The plugins as committed at ref (no local edits), one --plugin-dir each."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", ref, "plugins"],
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    return sorted(p for p in (dest / "plugins").iterdir() if (p / ".claude-plugin").is_dir())


def claude_args(plugin_dirs, model, max_turns, budget):
    args = ["claude", "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--max-turns", str(max_turns), "--max-budget-usd", str(budget),
            "--strict-mcp-config", "--no-session-persistence",
            "--allowedTools", ",".join(ALLOWED), "--disallowedTools", ",".join(DISALLOWED)]
    for path in plugin_dirs:
        args += ["--plugin-dir", str(path)]
    return args


def isolated_env(home):
    """A throwaway HOME and config folder, the login and PATH, nothing else from this shell.
    NEXIKA_BACKGROUND is never set: it would silence every Nexika hook."""
    home = Path(home)
    env = {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude"), "PATH": os.environ.get("PATH", ""),
           "DISABLE_AUTOUPDATER": "1", "LANG": os.environ.get("LANG", "C.UTF-8")}
    for key in AUTH_VARS:
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def skills_called(lines):
    """The skills the model called, in order, from stream-json lines."""
    called = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                data = block.get("input") or {}
                name = str(data.get("skill") or data.get("command") or "").lstrip("/")
                if name:
                    called.append(name)
    return called


def plugins_loaded(lines):
    """The plugin names the session reported at start, to show nothing else got in."""
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            plugins = event.get("plugins") or []
            return sorted(str(p.get("name") if isinstance(p, dict) else p) for p in plugins)
    return []


def cost(lines):
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            return event.get("total_cost_usd") or 0.0
    return 0.0


def correct(case, called):
    """Right when the expected skill was called; for "-", when no skill of the case's suite was."""
    if case["expected"] != "-":
        return case["expected"] in called
    return not any(name.partition(":")[0] == case["suite"] for name in called)


def run_one(case, arm, run, plugin_dirs, cfg, out):
    path = Path(out) / arm / f"case{case['id']:02}_r{run}.json"
    if path.exists():
        return json.loads(path.read_text())
    with tempfile.TemporaryDirectory(prefix="routing-") as tmp:
        home, project = Path(tmp) / "home", Path(tmp) / "project"
        (home / ".claude").mkdir(parents=True)
        project.mkdir()
        for name, text in FIXTURES[case["suite"]].items():
            (project / name).parent.mkdir(parents=True, exist_ok=True)
            (project / name).write_text(text, encoding="utf-8")
        # The prompt goes on stdin: after a list of --plugin-dir options, a bare argument is easy to misread.
        proc = subprocess.run(claude_args(plugin_dirs, cfg["model"], cfg["max_turns"], cfg["budget"]),
                              input=case["prompt"], cwd=project, env=isolated_env(home), capture_output=True,
                              text=True, errors="replace", timeout=cfg["timeout"])
    lines = proc.stdout.splitlines()
    called = skills_called(lines)
    result = {"case": case["id"], "arm": arm, "run": run, "called": called, "correct": correct(case, called),
              "cost_usd": cost(lines), "exit": proc.returncode, "plugins": plugins_loaded(lines),
              "valid": any('"type":"result"' in line.replace(" ", "") for line in lines),
              "stderr": proc.stderr[-500:]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    return result


def load_results(out):
    return [json.loads(p.read_text()) for p in sorted(Path(out).glob("*/case*_r*.json"))]


def markdown(cases, results, arms):
    by_case = {c["id"]: c for c in cases}
    results = [r for r in results if r["case"] in by_case and r["arm"] in arms]   # --only, --refs
    valid = [r for r in results if r["valid"]]
    lines = ["# Skill routing", "", "Right answers out of valid runs, per kind of prompt.", "",
             "| Kind | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for kind in [k for k in KINDS if any(c["kind"] == k for c in cases)]:
        row = []
        for arm in arms:
            rs = [r for r in valid if r["arm"] == arm and by_case[r["case"]]["kind"] == kind]
            row.append(f"{sum(r['correct'] for r in rs)}/{len(rs)}")
        lines.append(f"| {kind} | " + " | ".join(row) + " |")
    lines += ["", "| # | Expected | Kind | Prompt | " + " | ".join(arms) + " |",
              "|---|---|---|---|" + "---|" * len(arms)]
    for case in cases:
        cells = []
        for arm in arms:
            rs = [r for r in valid if r["arm"] == arm and r["case"] == case["id"]]
            wrong = sorted({", ".join(r["called"]) or "none" for r in rs if not r["correct"]})
            got = f" (got {'; '.join(wrong)})" if wrong else ""
            cells.append(f"{sum(r['correct'] for r in rs)}/{len(rs)}{got}")
        lines.append(f"| {case['id']} | {case['expected']} | {case['kind']} | {case['prompt']} | "
                     + " | ".join(cells) + " |")
    invalid = len(results) - len(valid)
    spent = sum(r["cost_usd"] for r in results)
    lines += ["", f"{len(valid)} valid runs, {invalid} invalid, ${spent:.2f} in all."]
    return "\n".join(lines) + "\n"


def parse_refs(text):
    refs = {}
    for part in text.split(","):
        arm, _, ref = part.partition("=")
        if not ref:
            raise SystemExit(f"--refs: {part!r} is not ARM=REF")
        refs[arm.strip()] = ref.strip()
    return refs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refs", default="main=origin/main,new=HEAD", help="ARM=REF,... (default: %(default)s)")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--max-turns", type=int, default=2)
    p.add_argument("--budget", type=float, default=0.25, help="USD cap per session")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--cases", default=str(CASES))
    p.add_argument("--suite", help="only this suite's cases, e.g. lawha")
    p.add_argument("--only", help="case ids, comma-separated")
    p.add_argument("--out", help="folder for runs and summary.md")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--summary", metavar="DIR", help="print the report from saved runs")
    args = p.parse_args(argv)

    cases = load_cases(args.cases)
    if args.suite:
        cases = [c for c in cases if c["suite"] == args.suite]
    if args.only:
        keep = {int(i) for i in args.only.split(",")}
        cases = [c for c in cases if c["id"] in keep]
    refs = parse_refs(args.refs)
    if args.summary:
        print(markdown(cases, load_results(args.summary), list(refs)), end="")
        return 0
    cfg = {"model": args.model, "max_turns": args.max_turns, "budget": args.budget, "timeout": args.timeout}
    if args.dry_run:
        for c in cases:
            print(f"{c['id']:2} {c['expected']:18} {c['kind']:10} {c['prompt']}")
        print(f"\n{len(cases)} cases x {args.runs} runs x {len(refs)} arms = "
              f"{len(cases) * args.runs * len(refs)} sessions")
        print(" ".join(claude_args(["PLUGINS/<name>"], args.model, args.max_turns, args.budget)))
        return 0
    if not args.out:
        p.error("--out is required for a paid run")
    if not any(os.environ.get(k) for k in AUTH_VARS):
        p.error("set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY: the sessions don't see your login")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plugins = {}
    for arm, ref in refs.items():
        sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", ref], capture_output=True, text=True,
                             check=True).stdout.strip()
        shutil.rmtree(out / "plugins" / arm, ignore_errors=True)
        plugins[arm] = export_plugins(sha, out / "plugins" / arm)
        print(f"{arm}: {ref} = {sha[:12]}, {len(plugins[arm])} plugins", file=sys.stderr)
    (out / "config.json").write_text(json.dumps({**cfg, "refs": refs, "runs": args.runs}, indent=1))
    # Arms interleave, so a slow minute or a model change mid-run hits both alike.
    jobs = [(c, arm, run) for run in range(1, args.runs + 1) for c in cases for arm in refs]
    with ThreadPoolExecutor(args.jobs) as pool:
        for r in pool.map(lambda j: run_one(j[0], j[1], j[2], plugins[j[1]], cfg, out), jobs):
            mark = "ok" if r["correct"] else "WRONG"
            print(f"{r['arm']:6} case {r['case']:2} r{r['run']} {mark:5} {r['called']}"
                  + ("" if r["valid"] else " INVALID"), file=sys.stderr)
    text = markdown(cases, load_results(out), list(refs))
    (out / "summary.md").write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
