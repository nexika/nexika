# hafiz benchmark: does work continue correctly after a compaction or a new session?

hafiz's job is continuity: after Claude Code compacts the conversation, or when work goes on in a
new session, the work should go on with the decisions, open problems and files that matter.
SWE-bench tasks end before a compaction, so the agent benchmark can't measure this. This benchmark
breaks a planned piece of work in the middle (with `/compact`, or by starting a new session) and
checks what survives. Tracking issue: #348.

This is **version 2**. Version 1 (three tasks, one `/compact` each) could not tell the arms apart:
see [Results](#results).

| | Arm `plain` | Arm `hafiz` |
|---|---|---|
| Agent | Claude Code (`claude -p`), Sonnet | the same |
| Plugins | none | only `plugins/hafiz`, exported from a commit (`--plugin-dir`) |
| Everything else | same fixture, prompts, permission mode, budget, fresh home | the same |

## The tasks

Every task starts from the same small repo, [`fixture/`](fixture): `shelf`, a book catalog in a
tab-separated file with a `list` command and unittest tests (standard library only). Each task adds
one deliberately failing test (and, for loans, a loans file) from [`tasks/<folder>/overlay`](tasks)
and follows a script of calls ([`tasks.json`](tasks.json)):

- **say**: a prompt in the current session (`claude -p --resume`). The first one gives the whole
  plan, the decisions, and "the failing test is a known bug: leave it alone until then".
- **compact**: `/compact` in the same session. The run checks that it compacted (a
  `compact_boundary` event, or a compact summary in the transcript).
- **restart**: the next prompt starts a **new session** (`--session-id`, no `--resume`) in the same
  repo and the same home. Claude Code's compaction summary does not carry over; hafiz's memory,
  kept in the home, does. This is where hafiz should matter most.

Just before every compact and restart (a *break*), the run records the repo's files and test
results.

| Task | Script | Decisions (stated once, early) | Left after the breaks |
|---|---|---|---|
| `loans-compact` | 4 steps, `/compact`, "do the next step", `/compact`, "carry on with the plan" (8 calls) | fines: 25 cents a day after 3 free days, capped at the book's price; money in whole cents, no floats; member names compared with `casefold()`, not `lower()` (all in the plan); dates printed as DD.MM.YYYY (in the second prompt) | step 5 (`fine_cents`) between the compactions; the `overdue` command, the `--member` filter and the deferred test after both |
| `loans-restart` | 3 steps, `/compact`, "do the next step", **new session**: "still to do: fine_cents, the overdue command, the --member filter, the failing test" (6 calls) | the same | the same three steps and the deferred test; the new prompt names the steps but none of the decisions |
| `search-restart` | v1's `search` plan: 3 steps, **new session**: "carry on with the plan" (4 calls) | `casefold()`, never `lower()`; `data/catalog.tsv` keeps its format; `find(year=)` is keyword-only | step 4 (`search --year`, `list --title`) and the deferred test; the new session has neither the plan nor the decisions unless a memory brings them |

The loans decisions are worded the way hafiz's capture rules recognise ("Let's use ...", "Don't use
...", "We'll use ..."); `search-restart` keeps v1's wording, which the rules do not capture (see
[Found by the benchmark](#found-by-the-benchmark)). The checks the agent never sees are in
`tasks/<folder>/hidden_test.py`. Version 1's tasks are kept in [`tasks-v1.json`](tasks-v1.json) so
its runs can be scored again.

## Scoring

[`score.py`](score.py) reads what the run recorded: each call's stream-json, the transcripts, the
final diff, and the repo's files and test results at every break and at the end.
[`runtests.py`](runtests.py) runs the repo's own tests and the hidden checks. Three groups, each
from 0 to 1:

| Group | Passes when |
|---|---|
| **Decisions kept** | each decision holds at the end: a hidden test (fine rule, whole cents, casefold matching, DD.MM.YYYY dates, backwards compatibility), no added line that breaks it (`float(`, `.lower()`), or a file left unchanged (`data/catalog.tsv`). A decision check about an open step's code counts only when that step works. |
| **Open work done** | the open steps' hidden tests pass, and the deferred test passes **without its test method being edited**. If the agent fixed the deferred test before the first break, against the plan, that check is left out (`fixed_early`). |
| **No redo** | work finished before a break was not done again after it, judged by behaviour (below). |

**No redo, by behaviour (new in v2).** For every break, the work finished before it is each test
that passed then, and each function or class of the task's `keep_files` that the agent had added or
changed by then. It counts as redone when:
- **broken**: a test that passed at a break (a hidden check or the repo's own) fails at the end. A
  test the agent removed is not counted.
- **rewritten**: fewer than half of a finished function's statements are left, in its final version
  or in code added after the break. Extending it (a new parameter, a filter), or moving its code
  into a helper, keeps its statements, so a refactor that keeps behaviour passes.
- **duplicated**: a name defined twice in one module, or a function added after the break that
  holds 80% of a finished one's statements while the original stays in place (a copy).

Statements are compared after `ast.unparse`, so formatting and quotes do not matter; docstrings and
the `def` line are left out.

Version 1 counted *any* change to a finished function as redone work, and every `search` run failed
it in both arms. Step 4 asks for a `--title` filter "that matches text the same way search does",
and the natural way is to give `search()` a `fields` or `year` parameter. Those six runs are kept as
test fixtures in `tests/fixtures/hafiz_bench/v1_search/` (only the `shelf/` modules and the test
results). The v1 rule flags all six, the v2 rule none. The tests also check that a rewrite from
scratch, a copy under a new name, a name defined twice and a broken finished test are still caught.

**Continuity** is the mean of the three. A run is **invalid** (kept, but left out of the comparison)
when a call did not finish, the API failed, a `/compact` did not compact, a restart did not start a
new session, or the arm loaded the wrong plugins (read from claude's `init` event).

### The quality guardrail: what hafiz's note costs

Next to the continuity score, each run reports:
- `restore_chars`: the text hafiz's `SessionStart:compact` hook added after each compaction (about
  4 characters per token);
- `restart_card_chars`: hafiz's start card in the new session after a restart;
- `hook_chars`: everything hafiz added in the run (the start card at every resume, the restores);
- `first_prompt_after`: the size in tokens of the first model request after the first break, so the
  two arms can be compared directly;
- `tokens_after` (the prompts after the first break, not the `/compact` calls) and the cost of the
  whole run.

A shorter note is only better if the continuity score holds. The summary has one table per arm and
one per task and arm: a difference can hide in one kind of break.

## Run it

```bash
# The plan, no model calls
python3 benchmarks/hafiz/bench.py run --dry-run

# Paid: 3 tasks x 2 arms x 3 runs = 18 runs, 108 claude calls. Stops before $25 in total.
flock ~/nexika-bench/.paid.lock python3 benchmarks/hafiz/bench.py run --runs 3 --max-total 25

# Score every finished run: ~/nexika-bench/hafiz/v2/results.json and summary.md
python3 benchmarks/hafiz/bench.py score

# Score version 1's runs again with the current scorer (writes into ~/nexika-bench/hafiz)
python3 benchmarks/hafiz/bench.py score --home ~/nexika-bench/hafiz
```

**Cost estimate.** Version 1 cost $0.62 a run (5 calls, about $0.12 a call, more for the calls late
in a session). Using v1's cost per call by position, a run costs about $1.10 for `loans-compact`,
$0.80 for `loans-restart` and $0.50 for `search-restart`. That is about $2.40 for one run of every
task in one arm, and **about $15 for the 18 runs** (3 runs of 3 tasks in 2 arms). `--max-total 25`
leaves room for longer sessions than expected.

**Login.** `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` from the environment, else the token in
`--token-file` (default `~/nexika-bench/.token`, from `claude setup-token`). Nothing else: the runner
never reads `~/.claude` credentials.

**Isolation.** Every run gets its own repo and its own home under
`~/nexika-bench/hafiz/v2/runs/<task>__<arm>__r<n>/` (or `$HAFIZBENCH_HOME`). The transcripts and
hafiz's memory start empty and never touch the real `~/.claude`. A restart keeps the run's home, so
hafiz's memory of the first session is there and nothing else is. The environment is rebuilt from
scratch: none of the caller's Claude Code variables, and never `NEXIKA_BACKGROUND` (it turns hafiz
off). Version 1's data stays in `~/nexika-bench/hafiz/runs`, so the `--max-total` of a v2 batch
counts only v2 runs.

**Options.** `--only loans-restart search-restart` runs some tasks, `--arms plain,hafiz`, `--model
sonnet`, `--budget 1.5` (USD per call), `--max-total 25` (USD for everything in the data folder),
`--timeout` (seconds per call), `--ref` (the commit whose hafiz arm `hafiz` loads). A run that already
has `meta.json` is skipped; one without it is started again.

**Tests.** `tests/test_hafiz_bench.py` runs offline: it checks the fixture (only the deferred test
fails at the start, the hidden checks fail until the work is done), the scorer's rules (with v1's
recorded `search` runs), and the whole runner end to end with a scripted stand-in for `claude`
(`tests/fixtures/hafiz_bench/fake_claude.py`, and `fake_loans.py` for the v2 tasks): two
compactions, a restart in a new session, a restart that resumed the old session (invalid), a
compaction only the transcript shows, good and bad runs.

## Results

### Version 2

Pending: the paid runs need the maintainer's approval first.

### Version 1 (2026-10-10): no difference, and it could not show one

3 tasks (`export`, `models`, `search`), 2 arms, 3 runs each, Sonnet, every run compacted and valid.
Cost $12.32 including the smoke run.

| Arm | Continuity | Decisions kept | Open work done | No redo | Restore note | Tokens after compaction | Cost |
|---|---|---|---|---|---|---|---|
| plain | 0.89 | 1.00 | 1.00 | 0.67 | none | 116k | $5.54 |
| hafiz | 0.89 | 1.00 | 1.00 | 0.67 | 321 chars | 122k (+5%) | $5.60 |

Why it could not separate the arms:
- **The tasks were too easy.** Each session had three short steps before one `/compact`, and Claude
  Code's own compaction summary carried every seeded decision and every open step. Both arms scored
  the same in all 18 runs.
- **The "no redo" failures were the scorer's.** All 6 `search` runs, in both arms, failed it because
  step 4 legitimately reuses `search()`'s matching. Scored again with the v2 rule, every v1 run
  passes "no redo", and both arms score 1.00 continuity: still no difference.
- **hafiz had little to give back.** Its restore note was 321 characters ("Working on: Good. Do step
  3 now, with tests, then stop."), about 5% more tokens after the compaction, with no gain.

Version 2 answers each point: longer sessions with two compactions, decisions stated once and early
and needed only after the breaks, a restart in a new session where the built-in summary does not
help, and "no redo" judged by behaviour.

## Found by the benchmark

From version 1's recorded data (the hafiz arm's data folders) and from replaying hafiz's hooks
offline on it. hafiz's code is not changed here; these are for separate issues.

1. **Decisions worded as "Decisions: use X, not Y" are not captured.** None of v1's seeded decisions
   ("use the standard library csv and json modules, not pandas", "compare text with
   str.casefold(), never lower()", "don't change the format of data/catalog.tsv") matched the capture
   rules: 0 decisions in all 9 hafiz runs. The v2 loans decisions use the recognised forms; all four
   are captured.
2. **Files changed through Bash are not recorded.** In v1 the agent mostly edited with Bash
   (heredocs, `python3 - <<EOF` scripts, `cat >>`), not Edit or Write: 7 of 9 hafiz runs recorded
   no changed file at all.
3. **`python3 -m unittest` is not recognised as a test command**, so the deferred failing test was
   never recorded as an open problem (0 problems in all 9 runs).
4. **The restore note and the start card name the latest prompt, not the plan.** After `/compact`:
   "Working on: Good. Do step 3 now, with tests, then stop." In a new session: "Last session: We're
   back after a break. Carry on with the plan ...". The plan is kept only as the session's first
   prompt, cut at 400 characters, so steps after the first two or three are lost; a new session
   cannot learn the rest of the plan from hafiz.
5. **The start card shows three decisions.** Replaying `loans-restart`'s prompts through hafiz's
   hooks, the new session's card lists three of the four decisions and "(+1)"; the casefold rule is
   behind `hafiz recall`.
