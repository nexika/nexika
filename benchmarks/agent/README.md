# Agent benchmark: Claude Code alone vs. Claude Code with Nexika

Does Nexika help the agent finish more coding tasks correctly, with fewer regressions, fewer
interventions or lower cost? This benchmark answers that with a paired A/B on tasks we did not write.
Tracking issue: #333.

| | Arm A | Arm B |
|---|---|---|
| Agent | Claude Code (`claude -p`) | the same |
| Plugins | none | the 12 Nexika plugins, from a pinned commit (`--plugin-dir`) |
| Everything else | same image, model, prompt, permission mode, budget, time limit | the same |

## The tasks

The pilot uses 20 tasks from [SWE-bench Verified](https://www.swebench.com/), listed in
[`pilot.json`](pilot.json). They were picked by `bench.py select` with seed 333: 6 under 15 minutes,
10 from 15 minutes to an hour, and 4 from 1 to 4 hours. Hard tasks are over-sampled so the pilot sees
some, and there are at most 4 per repository (django is almost half of Verified).

Each task's hidden tests do the grading:
- the FAIL_TO_PASS tests decide whether the task is resolved;
- a PASS_TO_PASS test that fails counts as a regression.

The agent sees only the issue text. The gold patch, the tests and the hints are never stored.

## How a run works

1. Start the task's own SWE-bench image (`swebench/sweb.eval.x86_64.<task>`). The repository is at
   `/testbed` with its environment installed, so both arms can run the project's tests.
2. Copy in the `claude` binary and the login. For arm B, also copy in `plugins/` as committed at `--ref`.
3. Run `claude -p` in `/testbed` with the issue as the prompt. The output is stream-json.
4. Keep `git diff` of everything the agent changed, then remove the container.
5. Grade later with the official SWE-bench harness. It applies the diff and the hidden tests in a
   fresh container, so the agent never grades itself.

The arms are run in a random order for each task, fixed by the seed. Each container starts with an
empty home, so Nexika's memory and settings start empty too.

## Confounds it handles

- **`NEXIKA_BACKGROUND=1` makes every Nexika hook exit.** `bench.py` never sets it in the container.
- **Python versions.** Nexika's hooks need Python 3.10 or newer, and a task's environment can be
  older. The hooks run `python3` from the image's conda base (3.11). The agent's Bash tool reads
  `/root/.bashrc`, which activates the task's `testbed` environment.
- **Asks with no human.** `--permission-prompts none` denies anything that would prompt, such as a
  haris "ask", and the run counts it under `permission_denials`. That number is the run's human
  interventions.
- **Did arm B really load Nexika?** Each run reads the plugins from claude's init event. An arm B run
  without all 12 plugins, or an arm A run with any of them, is kept but marked invalid and left out
  of the comparison.
- **No MCP servers, no user settings.** Both arms use `--strict-mcp-config` and start with an empty
  `/root/.claude`.

## Run it

```bash
# 1. Pick tasks (already done; pilot.json is committed). Fetches the dataset, no model calls.
python3 benchmarks/agent/bench.py select

# 2. Check that every task grades its own gold fix as resolved. No model calls. Replace any
#    task that fails: it would grade both arms wrong.
python3 -m venv ~/nexika-bench/venv && ~/nexika-bench/venv/bin/pip install swebench
python3 benchmarks/agent/bench.py validate --python ~/nexika-bench/venv/bin/python

# 3. Check the plan, then run it. Paid: every run is a full Claude Code session.
python3 benchmarks/agent/bench.py run --model opus --dry-run
python3 benchmarks/agent/bench.py run --model opus --budget 5 --timeout 2700

# 4. Grade with the SWE-bench harness.
python3 benchmarks/agent/bench.py grade --python ~/nexika-bench/venv/bin/python

# 5. results.csv and the paired comparison
python3 benchmarks/agent/bench.py summary
```

You need Docker and the `claude` CLI. A run that stopped can be started again: runs that already
have `meta.json` are skipped. `--only <task> ...` runs just those tasks, and `--ref <commit>` pins
arm B's Nexika.

**Login.** Set `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY`, and the
container uses it. Without either, `bench.py` copies `~/.claude/.credentials.json` into the
container. A token refresh inside the container can then sign the host out, so set a token for
long runs.

**Cost.** Each run is capped by `--budget` (USD) and `--timeout` (seconds). The pilot is 40 runs.

## Ablations, batches and the context cost

An arm is `A` (no plugins), `B` (all of Nexika) or plugin names joined by `+`, such as `itqan` or
`haris+barq`. That arm loads only those plugins. Each run checks that it loaded exactly its arm's set.

```bash
# 100 tasks with every hard one (pilot-2.json), five arms, three containers at a time.
# Each batch of 10 is validated, run, graded, and then its images are deleted.
python3 benchmarks/agent/bench.py --pilot benchmarks/agent/pilot-2.json pipeline \
  --model sonnet --arms A,B,itqan,siyaq,haris+barq --jobs 3 \
  --python ~/nexika-bench/venv/bin/python --workers 3 --test-timeout 900

# The prompt tokens each plugin adds, one short session per plugin (14 sessions)
python3 benchmarks/agent/bench.py context --model sonnet --task django__django-11848
```

`pipeline` skips any task whose own gold patch doesn't grade as resolved, and lists it in
`excluded.json`. A run that ends on an API failure, such as a usage limit, is marked invalid and
run again on the next start. It never counts as a failed task.

Each run also records:
- `ran_tests`: whether the agent ran the project's tests;
- `first_prompt_tokens`: the size of the model's first request, before any work.

The summary has one table per ablation arm, compared with A.

## What you get

`~/nexika-bench/<pilot>/` (or `$AGENTBENCH_HOME`):

| Path | What |
|---|---|
| `runs/<task>__<arm>__r<n>/stream.jsonl` | the whole session, as claude printed it |
| `runs/.../diff.patch` | what the agent changed |
| `runs/.../meta.json` | the run's numbers (below) |
| `grades.json` | resolved, FAIL_TO_PASS and PASS_TO_PASS counts per run |
| `results.csv` | one row per run, all of the above |
| `summary.md` | the paired comparison |

Each run records:
- the outcome: resolved and regression;
- the cost: USD, wall time, turns, input, output and cache tokens;
- the tool calls: all, Bash, failed ones, permission denials, hook runs and hook errors;
- the diff: files changed, lines added and removed;
- the setup: model, claude version and Nexika commit.

## Reading the result

The summary pairs tasks. Each measure is the mean per task in each arm, the difference B − A, and a
95% bootstrap interval over tasks. **An interval that contains 0 means this sample cannot tell the
arms apart on that measure.**

With 20 tasks and one run each, the interval on the resolve rate is about ±20 points. So the pilot
can show differences in cost, time, tokens and interventions, but not a 10-point gain in success.
The pilot is for:
- finding what breaks in the harness;
- a first reading on cost and regressions;
- deciding whether to scale to about 100 tasks with ablations.

## Not covered here

- **Continuity across sessions (hafiz, siyaq).** SWE-bench has no tasks that span sessions. Those
  need their own tasks with seeded decisions.
- **bayan, prof, manar, mizan and lawha.** They don't aim at "task solved". lawha has its own
  benchmark in [`../README.md`](../README.md).
