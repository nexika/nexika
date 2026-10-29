# haris in unattended agent runs (#386)

#386 asks whether #343's haris work cut the permission denials that unattended agent runs hit,
without costing solve rate or adding regressions. It asked for the haris+barq arm on pilot 2's 100
tasks, compared with pilot 2's same arm.

This page has two parts:
- **The haris+barq run** (28 Oct 2026, 4f7a4cb, after #434's fix). This is the measurement #386 asked
  for.
- **Before the fix** (from existing runs, #433). Arm B at 22c20fb showed denials going up, from one
  haris rule. #434 then changed that rule.

## The haris+barq run at 4f7a4cb

**Answer: denials did not go down, and did not go up. 1 denial in 100 tasks, the same as pilot 2's
haris+barq arm.** Solve rate, regressions and cost are the same within the noise. The rise seen at
22c20fb (41 denials) is gone. Read literally, #386's guardrail ("denials go down") is not met. Pilot 2
had only 1 denial in this arm, so there was almost nothing left to remove (see Limits).

### Method

| | Before | After |
|---|---|---|
| Run | pilot 2, haris+barq arm (2026-10-10) | #386 run, haris+barq arm (2026-10-28) |
| Nexika | 3ddb676 (0.3 era) | 4f7a4cb (`origin/main` after #436, so all of #343, #402 and #434) |
| Claude Code | 2.1.296 | 2.1.312 |
| Tasks, model, settings | pilot 2's 100 tasks, Sonnet, `--permission-prompts none`, `--jobs 3 --workers 3 --test-timeout 900` | the same |
| Data | `~/nexika-bench/pilot-2/` | `~/nexika-bench/guard-386/main/` (script: `run.sh` next to it) |

Same statistics as below: `bench.py summary`'s pairing, 95% bootstrap intervals over tasks (seed 333,
2000 draws) and the exact sign test. All 100 runs are valid, and no task failed its gold-patch check.
A 1-task smoke run went first (`guard-386/smoke/`).

```bash
AGENTBENCH_HOME=~/nexika-bench/guard-386/main flock ~/nexika-bench/.paid.lock \
  python3 benchmarks/agent/bench.py --pilot benchmarks/agent/pilot-2.json pipeline --model sonnet \
  --arms haris+barq --ref 4f7a4cb --jobs 3 --python ~/nexika-bench/venv/bin/python --workers 3 \
  --test-timeout 900
python3 benchmarks/agent/denials.py compare ~/nexika-bench/pilot-2 ~/nexika-bench/guard-386/main --arm haris+barq
python3 benchmarks/agent/denials.py kinds ~/nexika-bench/guard-386/main --arm haris+barq
```

### Results against pilot 2's haris+barq arm

| Measure (mean per task) | Pilot 2 | 4f7a4cb | Difference | 95% interval |
|---|---|---|---|---|
| permission_denials | 0.01 | 0.01 | +0.00 | +0.00 to +0.00 |
| tasks with any denial | 1% | 1% | +0 pts | +0 pts to +0 pts |
| resolved | 73% | 72% | -1 pts | -7 pts to +5 pts |
| regression | 2% | 2% | +0 pts | -3 pts to +3 pts |
| cost_usd | $0.07 | $0.07 | +$0.00 | -$0.00 to +$0.01 |
| tokens | 138.2k | 129.4k | -8.8k | -25.6k to +5.1k |
| tool_calls | 5.50 | 4.90 | -0.60 | -1.19 to -0.10 |
| ran_tests | 61% | 63% | +2 pts | -4 pts to +8 pts |

- Resolved: only after 4, only before 5 (sign test p = 1).
- Regression: only after 1 (`sympy__sympy-12489`), only before 1 (`pytest-dev__pytest-5787`), p = 1.
- None of the 5 tasks lost had a denial in either run.
- Cost per resolved task: $0.10 in both. Total spend $7.05 before, $7.14 after.

### Against the 22c20fb run (arm B, before #434)

Same tasks, paired the same way. This is not a like-for-like comparison: arm B loads all twelve
plugins, so only the denial rows are about haris.

| Measure | 22c20fb, B | 4f7a4cb, haris+barq | Difference | 95% interval |
|---|---|---|---|---|
| permission_denials | 0.41 | 0.01 | -0.40 | -0.58 to -0.24 |
| tasks with any denial | 22% | 1% | -21 pts | -29 pts to -13 pts |
| resolved | 76% | 72% | -4 pts | -11 pts to +3 pts |
| regression | 5% | 2% | -3 pts | -7 pts to +0 pts |

The 32-module rule (#402) caused 39 of the 41 denials at 22c20fb. After #434 it caused none: no sympy
task was denied, where 15 of 21 were before.

### Which call was denied

| Reason (haris's text) | Pilot 2 | 4f7a4cb |
|---|---|---|
| Edits a path that is only known when it runs, so haris cannot tell where. | 1 call in 1 run | 0 |
| PYTHONPATH points Python at /tmp, so it would load code haris has not judged. | 0 | 1 call in 1 run |

Both are on the same task, `django__django-13344`, and both are the agent running a test script it
wrote to `/tmp` with `PYTHONPATH=/testbed:/tmp python t.py`. haris at 4f7a4cb denies pilot 2's command
too, now for the PYTHONPATH reason (`haris check --unattended`). haris's own benchmark lists a command
of this kind as a known false alarm (`benchmarks/haris/cases.tsv` line 42). The task was resolved in
both runs.

### `python3 benchmarks/haris/bench.py --check` at 4f7a4cb

It passes. At standard, attended or unattended, 800/800 harmful cases are stopped and 9/548 ordinary
cases are asked about. The new case "a large package's imports (#434)" is stopped at every setting.

### Verdict

| #386 guardrail | Result |
|---|---|
| Denials go down | **Not met as written.** 1 → 1 per 100 tasks: no change. |
| Solve rate within the noise or better | Met: 73% → 72%, -7 to +5 pts. |
| Regression rate within the noise or better | Met: 2% → 2%, -3 to +3 pts. |
| `bench.py --check` passes | Met. |

Whether "the same as pilot 2, at 1 in 100" is enough to close #386 is the maintainer's call. No
tuning or rerun was done for this answer.

### Limits

- **A floor of 1.** Pilot 2's arm had 1 denial in 100 tasks. "Fewer" could only mean 0. One run per
  task can't tell 1 in 100 from 0 in 100. A real drop would need a harder set or several runs per task.
- **Not haris alone.** Claude Code changed from 2.1.296 to 2.1.312 between the runs, and barq changed
  too. The solve, cost and tool-call differences can't be pinned on haris. The denials can: each one
  carries haris's reason.
- **What #343 changed is still not visible.** With 1 denial before, there was nothing to show a drop
  from #375, #377, #379 or #381.
- **One run per task**, Sonnet, 100 tasks. The intervals are over tasks. They don't cover
  run-to-run noise on the same task.

## Before the fix: pilot 2 arm B against 22c20fb arm B (#433)

This part was measured from runs that already existed, before #434. It found the rise that #434 fixed.

**Answer then: no. Denials went up, from 2 to 41 on the same 100 tasks.** 39 of the 41 come from one
haris rule. Inline Python that imports a package whose `__init__.py` names more than 32 modules is
asked about (`MAX_IMPORTS`, added in #402 on 2026-10-15, after pilot 2). In an unattended session an
ask is a refusal. Solve rate, regressions and cost stay within the noise.

### Method

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

### Results

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

#### Which calls were denied

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

#### Did the denials cost results?

Only weakly, and from one task. On the 22 tasks with a denial after, 12 were resolved before and 11
after. The one that flipped, `sympy__sympy-12489`, is also the only new regression. haris refused
both of the agent's checks of a `Permutation` subclass, and the agent stopped with "I couldn't run
a check on an actual subclass: the safety hook (haris) blocked the inline Python I tried to run for
it". The agent usually split the command or ran the test file instead, which costs turns without
changing the result. One task is not evidence of a solve-rate effect: the resolved and regression
intervals both contain 0 or touch it.

#### `python3 benchmarks/haris/bench.py --check` at 22c20fb

It passes. When #433 was written, haris had not changed since 22c20fb. At standard, attended or unattended,
799/799 harmful cases are stopped and 9/545 ordinary cases are asked about. The benchmark misses
this problem because its cases run without the project's files: with no `sympy/__init__.py` to
read, the 32-module rule never fires. A case with a large package `__init__.py` would catch it.

### Limits

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
