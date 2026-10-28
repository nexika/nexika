# haris in unattended agent runs: pilot 2 against 22c20fb (#386)

#386 asks whether #343's haris work cut the permission denials that unattended agent runs hit,
without costing solve rate or adding regressions. This note answers that from runs that already
exist. No new paid run was made for it.

**Answer: no. Denials went up, from 2 to 41 on the same 100 tasks.** 39 of the 41 come from one
haris rule. Inline Python that imports a package whose `__init__.py` names more than 32 modules is
asked about (`MAX_IMPORTS`, added in #402 on 2026-10-15, after pilot 2). In an unattended session an
ask is a refusal. Solve rate, regressions and cost stay within the noise. #386's
guardrail ("denials go down") is not met, so the rule needs reworking before #386 can close.

## Method

| | Before | After |
|---|---|---|
| Runs | pilot 2, arm B (2026-10-10) | #393 guardrail run, `main` arm B (2026-10-28) |
| Nexika | 3ddb676 (0.3 era) | 22c20fb (all of #343, #383, #402) |
| Claude Code | 2.1.296 | 2.1.312 |
| Tasks, model, settings | pilot 2's 100 tasks, Sonnet, `--permission-prompts none` | the same |
| Data | `~/nexika-bench/pilot-2/` | `~/nexika-bench/guard-393/main/` |

Both arms are B (all twelve plugins). The statistics are `bench.py summary`'s own: tasks paired,
95% bootstrap intervals over tasks (seed 333, 2000 draws) and the exact sign test, imported from
`agentbench/summary.py`. The denied calls come from each run's `stream.jsonl`: the result event
lists them, and the reason is haris's own text, from the tool result when haris refused, or from
the PreToolUse hook response when haris asked and Claude Code denied.

```bash
python3 benchmarks/agent/denials.py compare ~/nexika-bench/pilot-2 ~/nexika-bench/guard-393/main
python3 benchmarks/agent/denials.py kinds ~/nexika-bench/guard-393/main
```

## Results

| Measure (mean per task) | Before | After | After − before | 95% interval |
|---|---|---|---|---|
| permission_denials | 0.02 | 0.41 | +0.39 | +0.23 to +0.57 |
| tasks with any denial | 2% | 22% | +20 pts | +12 pts to +28 pts |
| resolved | 74% | 76% | +2 pts | -1 pts to +6 pts |
| regression | 4% | 5% | +1 pts | +0 pts to +3 pts |
| cost_usd | $0.12 | $0.12 | +$0.00 | -$0.01 to +$0.01 |
| tokens | 193.6k | 225.7k | +32.1k | +4.9k to +62.5k |
| tool_calls | 5.42 | 6.83 | +1.41 | +0.67 to +2.26 |
| ran_tests | 74% | 84% | +10 pts | +3 pts to +17 pts |

- Resolved: 100 tasks, only after 3, only before 1 (sign test p = 0.62).
- Regression: only after 1, only before 0 (p = 1).
- Any denial: only after 21, only before 1 (p = 0.00001).
- Cost per resolved task: $0.16 before, $0.15 after. Total spend $11.62 before, $11.72 after.

### Which calls were denied

| Reason (haris's text) | Before | After |
|---|---|---|
| The Python code imports more than 32 modules, too many for haris to read each one. | 0 | 39 calls in 20 runs |
| `python` runs shell commands from inside the code. | 2 calls in 2 runs | 1 call in 1 run |
| haris could not read this command (a `'` quote is never closed). | 0 | 1 call in 1 run |

All 41 are Bash calls refused by haris. None comes from Claude Code's own checks.

The 32-module rule hits ordinary checks of a task's own package: `python -c "from sympy import Max,
Min; print(Max(), Min())"`, `python -c "import sphinx.ext.autodoc.importer"`, and heredocs that edit a
file with `s.replace(...)` in django and sphinx. haris counts every name in `from pkg import (a, b, c,
...)` as a module it may have to read. sympy's `__init__.py` imports hundreds of names, so any inline
Python that imports sympy is asked about. 15 of the 21 sympy tasks had at least one denial. The
other denied runs were 3 in django, 3 in sphinx and 1 in pytest.

Reproduced offline with no model call. In a folder with `pkg/__init__.py` containing
`from pkg.core import (n0, ..., n39)`, this command:

```bash
haris check --unattended 'python -c "from pkg import x; print(x)"'
```

prints `deny (dynamic): The Python code imports more than 32 modules ...`. Attended, the same command
asks.

The other arm of the #393 run (branch f1e195f, `~/nexika-bench/guard-393/b-393/`) shows the same
thing: 36 denials in 21 runs, 33 of them from this rule. Pilot 2's haris+barq arm had 1 denial.

### Did the denials cost results?

Only weakly, and from one task. On the 22 tasks with a denial after, 12 were resolved before and 11
after. The one that flipped, `sympy__sympy-12489`, is also the only new regression. haris refused
both of the agent's checks of a `Permutation` subclass, and the agent stopped with "I couldn't run
a check on an actual subclass: the safety hook (haris) blocked the inline Python I tried to run for
it". The agent usually split the command or ran the test file instead, which costs turns without
changing the result. One task is not evidence of a solve-rate effect: the resolved and regression
intervals both contain 0 or touch it.

### `python3 benchmarks/haris/bench.py --check` at 22c20fb

It passes. haris has not changed between 22c20fb and the current `origin/main`
(`git log 22c20fb..origin/main -- plugins/haris` is empty). At standard, attended or unattended,
799/799 harmful cases are stopped and 9/545 ordinary cases are asked about. The benchmark misses
this problem because its cases run without the project's files: with no `sympy/__init__.py` to
read, the 32-module rule never fires. A case with a large package `__init__.py` would catch it.

## Limits

- **B, not the haris arm.** #386 asked for the haris (or haris+barq) arm. Both runs here load all
  twelve plugins, and the other plugins changed a lot between 0.3 and 22c20fb. Claude Code also
  changed, from 2.1.296 to 2.1.312. So the solve, regression, cost, token and ran-tests differences
  can't be pinned on haris. The +10 pts in ran-tests and +32k tokens are more likely itqan, siyaq
  and Claude Code than haris.
- **The denial increase is haris's, though.** Every denied call carries haris's own reason, and
  39 of the 41 come from a rule that did not exist at pilot 2 and is reproduced offline. Other
  plugins can change which commands the agent writes, for example more inline checks once
  ran-tests went up. But they can't make haris deny a command.
- **What #343 changed is not visible.** Pilot 2 had only 2 denials. That is too few to show a drop
  from #375, #377, #379 or #381. The "`python` runs shell commands" ask, which is the kind #343
  targeted, went from 2 to 1.
- **One run per task**, Sonnet, 100 tasks. The intervals are bootstrap intervals over tasks. They
  don't cover run-to-run noise on the same task.

## What a paid haris-arm run (~$15) would add

A haris+barq run at 22c20fb against pilot 2's haris+barq arm (73% resolved, 1 denial) would separate
haris from the other plugins on solve rate and cost. The denials would most likely look the same:
they come from haris's own rule on the agent's own checks, so expect about a fifth of the tasks
denied again, mostly sympy. It is better spent after the 32-module rule is fixed, as the
measurement that closes #386: it should show denials at or below pilot 2's, with solve and
regression rates within the noise.
