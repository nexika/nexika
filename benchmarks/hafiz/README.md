# hafiz benchmark: does work continue correctly after a compaction?

hafiz's job is continuity: after Claude Code compacts the conversation, the work should go on with
the decisions, open problems and files that matter. SWE-bench tasks end before a compaction, so the
agent benchmark can't measure this. This benchmark forces one in the middle of a planned piece of
work and checks what survives. Tracking issue: #348.

| | Arm `plain` | Arm `hafiz` |
|---|---|---|
| Agent | Claude Code (`claude -p`), Sonnet | the same |
| Plugins | none | only `plugins/hafiz`, exported from a commit (`--plugin-dir`) |
| Everything else | same fixture, prompts, permission mode, budget, fresh home | the same |

## The tasks

Every task starts from the same small repo, [`fixture/`](fixture): `shelf`, a book catalog in a
tab-separated file with a `list` command and unittest tests (standard library only). Each task adds
one deliberately failing test ([`tasks/<task>/overlay`](tasks)) and drives one session:

1. **The plan and the decisions.** Five numbered steps, two decisions, and "the failing test is a
   known bug: leave it alone until step 5". Then "do step 1 now".
2. **Step 2**, then **step 3**, one `claude -p --resume` call each.
3. **`/compact`**: a manual compaction of the same session (`claude -p /compact --resume`). The
   run checks that it compacted (a `compact_boundary` event, or a compact summary in the transcript).
4. **Continue**: one vague prompt, the same for every task: *"We're back after a break. Carry on with
   the plan from where we stopped, and stop when all of it is done."*

Left after the compaction, in every task: step 4 (new work that the decisions apply to) and step 5
(the deferred failing test).

| Task | Seeded decisions | Step 4 (open) | Deferred failing test |
|---|---|---|---|
| `export` | standard library `csv`/`json`, not pandas; `load_catalog` and `find` stay backwards compatible and return dicts | `load_catalog` also reads `.csv` | `format_price` drops a trailing zero |
| `models` | `dataclasses`, not pydantic or attrs; `load_catalog` keeps returning dicts | `shelf list` uses Book objects, `--sort title\|author\|year` | `shelf list` crashes on an empty catalog |
| `search` | `str.casefold()`, never `lower()` (German titles); `data/catalog.tsv` keeps its format; `find(year=)` is keyword-only | `shelf search --year`, `shelf list --title` matching like search | `load_catalog` breaks on a blank or indented comment line |

The prompts are in [`tasks.json`](tasks.json); the checks the agent never sees are in
`tasks/<task>/hidden_test.py`.

## Scoring

[`score.py`](score.py) reads what the run recorded: each call's stream-json, the transcript, the
final diff, and the repo's files and test results before `/compact` and at the end.
[`runtests.py`](runtests.py) runs the repo's own tests and the hidden checks. Three groups, each
from 0 to 1:

| Group | Passes when |
|---|---|
| **Decisions kept** | each decision holds at the end: a hidden test (backwards compatibility, dataclass, casefold matching), no added line that breaks it (`import pandas`, `.lower()`), or a file left unchanged (`data/catalog.tsv`). A decision check about step 4's code counts only when step 4 works. |
| **Open work done** | step 4's hidden tests pass, and the deferred test passes **without its test method being edited**. If the agent fixed the deferred test before the compaction, against the plan, that check is left out (`fixed_early`). |
| **No redo** | nothing finished before the compaction is done again: no function or class added or changed before it (in the task's `keep_files`) is different at the end, no file the agent had already changed is written again whole (`Write`), and no name is defined twice in one module. |

**Continuity** is the mean of the three. A run is **invalid** (kept, but left out of the comparison)
when a call did not finish, the API failed, `/compact` did not compact, or the arm loaded the wrong
plugins (read from claude's `init` event).

### The quality guardrail: what hafiz's note costs

Next to the continuity score, each run reports:
- `restore_chars`: the text hafiz's `SessionStart:compact` hook added after the compaction (about 4
  characters per token);
- `hook_chars`: everything hafiz added in the session (the start card at every resume and the
  restore);
- `first_prompt_after`: the size in tokens of the first model request after the compaction, so the
  two arms can be compared directly;
- `tokens_after` and the cost of the whole run.

A shorter note is only better if the continuity score holds.

## Run it

```bash
# The plan, no model calls
python3 benchmarks/hafiz/bench.py run --dry-run

# Paid: 3 tasks x 2 arms x 3 runs = 18 sessions of 5 calls each. Stops before $20 in total.
flock ~/nexika-bench/.paid.lock python3 benchmarks/hafiz/bench.py run --runs 3 --max-total 20

# Score every finished run: ~/nexika-bench/hafiz/results.json and summary.md
python3 benchmarks/hafiz/bench.py score
```

**Login.** `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` from the environment, else the token in
`--token-file` (default `~/nexika-bench/.token`, from `claude setup-token`). Nothing else: the runner
never reads `~/.claude` credentials.

**Isolation.** Every run gets its own repo and its own home under `~/nexika-bench/hafiz/runs/<task>__<arm>__r<n>/`
(or `$HAFIZBENCH_HOME`), so the transcripts and hafiz's memory start empty and never touch the real
`~/.claude`. The environment is rebuilt from scratch: none of the caller's Claude Code variables, and
never `NEXIKA_BACKGROUND` (it turns hafiz off).

**Options.** `--only export models` runs some tasks, `--arms plain,hafiz`, `--model sonnet`,
`--budget 1.5` (USD per call), `--max-total 20` (USD for everything in the data folder), `--timeout`
(seconds per call), `--ref` (the commit whose hafiz arm `hafiz` loads). A run that already has
`meta.json` is skipped; one without it is started again.

**Tests.** `tests/test_hafiz_bench.py` runs offline: it checks the fixture (only the deferred test
fails at the start, the hidden checks fail until the work is done), the scorer's rules, and the
whole runner end to end with a scripted stand-in for `claude` (`tests/fixtures/hafiz_bench/fake_claude.py`).

## Results

Pending: the paid runs have not been made yet (the benchmark token was revoked before the first
run). Once a fresh token is saved to `~/nexika-bench/.token`:

```bash
flock ~/nexika-bench/.paid.lock python3 benchmarks/hafiz/bench.py run --runs 1 --only export --max-total 3   # smoke
flock ~/nexika-bench/.paid.lock python3 benchmarks/hafiz/bench.py run --runs 3 --max-total 20
python3 benchmarks/hafiz/bench.py score
```
