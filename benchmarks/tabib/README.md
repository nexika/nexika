# tabib benchmark

When CI fails, does tabib name the right failing test, file and line, and the right kind of failure? This benchmark
checks tabib on 170 real failed CI runs from six public projects, each with an answer labelled by hand. It runs
offline in under 10 seconds.

```bash
python3 benchmarks/tabib/bench.py                  # the report as Markdown
python3 benchmarks/tabib/bench.py --json           # the same as JSON, with every case
python3 benchmarks/tabib/bench.py --check          # exit 1 if a case the baseline got right is now wrong
python3 benchmarks/tabib/bench.py --save-baseline  # after adding cases, or after a change that gets more right
```

## What it measures

- **Kind**: how often tabib picks the labelled kind (code, matrix, flaky, infra, setup, dependency, unknown). The
  report includes a confusion table and lists the costly mistakes. "Flaky" or "infra" for a real bug sends the
  person to re-run instead of fixing. "Code" for infrastructure or a flaky failure sends them looking for a bug
  that is not there. Where two kinds are both fair, the label accepts either (for example
  `dependency`/`matrix` for a pin that excludes one Python).
- **Failures**: for runs with a labelled failure, whether tabib names every labelled failure with the right test,
  file and line (each one only when the label has it). For a check with no test or file, such as a pull request
  title check, the label gives a phrase of the check's own message instead. The report also counts runs where
  nothing failed in the code but tabib still names a failure (none today).
- **Cause**: for the 26 runs with a known fix (a fixing commit, or the change the label names), whether the
  triage's text names the place the fix touched (`expected.cause.points`): the file, package or setting.
- **Time** per triage on this machine, and **tokens**: tabib's triage makes no model call, so 0. The
  `tabib:diagnostician` agent (the model step of `/tabib:diagnose`) is not measured: it needs a model and the
  project's code, so this benchmark cannot run it offline.

Each case runs `diagnosis.triage`, tabib's own code, with its GitHub calls answered from the stored case (see
"What offline leaves out"). No code from the projects runs, nothing is fetched and no model is called.

## Results (2026-10-10, tabib 0.3.0 with #360, #361, #362 and #366)

| | All 170 | Trial set (150) | Held-out set (20) |
|---|---|---|---|
| Kind right | 167 = 98.2% | 148 = 98.7% | 19 = 95.0% |
| Failures right (test, file and line) | 111/111 = 100% | 93/93 = 100% | 18/18 = 100% |
| Cause named, runs with a known fix | 25/26 = 96.2% | 25/26 | none labelled |
| Costly kind mistakes | 0 | 0 | 0 |
| Triage time on the stored excerpts, median / p95 / max | 21 / 98 / 327 ms | | |
| Triage time on the whole logs (not stored), median / p95 / max | 55 ms / 1.1 s / 6.0 s | | |
| Tokens | 0 | | |

Times depend on the machine and its load: the excerpt times were taken on a busy machine (three runs, the
fastest kept; a quiet one gave 15 / 72 / 240 ms with #359). The whole-log times were measured once, with #359,
on the trial's own copies of the logs; those logs are not stored here, so this benchmark does not re-run them.

| Project | Set | Runs | Kind right | Failures right |
|---|---|---|---|---|
| psf/black | trial | 40 | 40 | 22/22 |
| fastify/fastify | trial | 40 | 38 | 21/21 |
| pallets/flask | trial | 40 | 40 | 35/35 |
| flypythoncom/python | trial | 30 | 30 | 15/15 |
| pallets/click | held-out | 12 | 12 | 12/12 |
| expressjs/express | held-out | 8 | 7 | 6/6 |

How it got here, on the same 170 runs:

| | Kind right | Held-out kind right | Failures right | Cause named | Costly mistakes |
|---|---|---|---|---|---|
| First run (#359) | 156 = 91.8% | 12/20 | 105/111 | 21/26 | 1 |
| With #360, #361 and #362 | 165 = 97.1% | 17/20 | 111/111 | 25/26 | 2 |
| With #366 | 167 = 98.2% | 19/20 | 111/111 | 25/26 | 0 |

#362 removed the first run's costly mistake (a fastify test that timed out in one job, called `matrix`). #360
taught tabib mocha, which named express's failing tests but also made two flaky express runs `code` instead of
`unknown`: the two costly mistakes that #366 removes.

**Read the trial number with care.** tabib was fixed against the four trial projects during the two-week trial
(#53), so 99% there is how well it fits the logs it was tuned on. The held-out set was the honest estimate for a
new project when it was collected: click (Python, pytest, pre-commit, mypy) was 12/12 and express (mocha) 0/8.
Since then, #360, #361 and #366 were fixed against express's runs, so its 7/8 is no longer held out in the strict
sense. With 20 runs it was a small sample anyway; new held-out projects would make it a real one again.

What tabib gets wrong:
- **express, 1 run.** Coveralls finding nothing to report (35727627772) is `unknown`, where the label says
  `setup`.
- **fastify, 2 runs.** A CodeQL upload that failed with no message (34748583815) is `unknown`, where the label
  says `infra` (a judgement, low confidence). A backport bot's pull request title (31715822603) is `code`, where
  the label says `setup`.
- **Cause not named.** For fastify's version test (33853095623), the fix was in `fastify.js`, which the log
  never names.

## The cases

| File | Runs | Licence | Collected |
|---|---|---|---|
| `cases/black.json` | 40 | MIT | the trial (#53), from black's last 1000 failed runs, July to October 2026 |
| `cases/fastify.json` | 40 | MIT | the trial, from fastify's last 1000 failed runs, July to October 2026 |
| `cases/flask.json` | 40 | BSD-3-Clause | the trial, failed runs from May to October 2026 |
| `cases/flypython.json` | 30 | MIT (code), CC BY 4.0 (prose) | the trial, the Validate workflow, September and October 2026 |
| `cases/click.json` | 12 | BSD-3-Clause | 10 Oct 2026: the 12 newest failed runs with a log, none skipped |
| `cases/express.json` | 8 | MIT | 10 Oct 2026: the 8 newest failed runs with a log; 15 newer runs had no jobs and were skipped |

By label: code 76, dependency 37, setup 30, infra 11, unknown 8 (runs with no jobs and no log), flaky 7, matrix 1
(as the first accepted kind). Several groups are near repeats of one cause (17 flask runs fail on the same Werkzeug
deprecation, 10 flypython runs on the same contourpy pin): they weigh the averages, so the per-project table matters
more than the total.

Each run in `cases/<project>.json` has:
- the run as GitHub lists it: `workflow`, `event`, `branch`, `sha`, `created` and every job with its conclusion;
- `log`: an excerpt of `gh run view --log-failed` in `logs/<project>/<run>.log` (none for a run with no jobs);
- `github`: what tabib would read from GitHub besides the log, where the trial recorded it. That is whether the
  run came from a fork, another run of the same commit that passed, and the base branch's failed runs of the same
  job (black's flaky Windows runs). Without it, tabib sees no history;
- `own_modules`: which missing module or crashing package belongs to the project (checked against the
  project's files when the case was collected), since the project's code is not stored;
- `expected`: the accepted kinds, the failures and, where known, the cause (a failure's `"line": 0` means the
  log names no line in that file, so tabib must name none); `label`: how it was decided; and
  `uncertain` where the label is a judgement.

### How each label was decided

By hand, from the log, the job list, the workflow file and, where one exists, the commit that fixed it. The trial
labels (#53) were checked again for this benchmark, and some changed. flypython's "config" is now `setup` (the
name tabib uses since #127). Two flypython runs that the trial called `dependency` also fail ruff in a second job,
so they accept `code` too. Failures are what the test runner or checker prints itself, up to three per run:
pytest's `FAILED` lines and `path:line` frames, mypy, ruff and eslint lines, pre-commit's hook id and the file in
its diff, a formatter's "would reformat", coverage tables, Node's `✖` and stack frames, mocha's numbered failures.

17 labels are judgements and say so in `uncertain`. The ones that change a kind:
- flaky by reading, with no re-run on record: fastify 31128098312 (two listen tests timed out in one job) and
  express 37533322411 and 34755690134 (a cookie's Expires one second off);
- infra or setup: fastify 30849839665 (a download site answering 403), fastify 34748583815 (a CodeQL upload that
  failed silently, low confidence), express 35727627772 (coveralls finding nothing to report), black 31070601941
  (a yum mirror);
- setup, not code: fastify 31715822603 (the backport bot's title, accepted after the workflow changed);
- code, though the line came from main: fastify 36454200650 and 36346607205.

### How the logs are stored

Whole logs would be about 40 MB; the excerpts are 2.9 MB. Each log was:
1. redacted with the shared `secrets.redact` (common/secrets.py), the way tabib redacts a log before reading it;
2. cut to each step's first lines, the end of each failed step, and the lines near an error, a failed test or a
   signal;
3. for the few still over 60 KB, shrunk further by dropping blocks of lines. Lines that name a failure (a
   runner's summary line, a `path:line`, an error, a `✖`, a hook id, and the few lines after each) were never
   dropped, so a better parser would still find what a person reads.

An excerpt was kept only when tabib's triage of it equals its triage of the whole log: the same kind, detail,
confidence, failures (test, file, line and message), evidence, signals and errors. The test checks that every
stored log is free of anything `secrets.has_secret` finds, and stays small. Logs are untrusted text: tabib only
matches them against fixed patterns, and nothing here runs or follows them.

### What offline leaves out

- the last green run and the commits since it (no "suspects"), and the local re-run of the failing tests: both
  need the project's repository;
- GitHub history beyond what `github` records: for the black, flask, flypython, click and express runs, tabib does
  not know whether the same commit passed elsewhere;
- the diagnostician agent's cause, which needs a model. "Cause named" here only asks whether the triage's own
  text points at the fixed place.

## The guardrail

`tests/test_tabib_bench.py` runs the benchmark in CI and fails if any run that `baseline.json` lists as right (by
kind, or by failures) is now wrong, or if kind accuracy or failure accuracy drops below the baseline. The triage is
deterministic, so there is no measurement noise: a change that saves time or tokens must not lose a single case.
After a change that gets more right, or after adding cases, run `--save-baseline` and commit `baseline.json`
with the change. Time is reported, not checked: it depends on the machine.

To add cases: collect failed runs with `gh run view <id> --log-failed` and `gh run view <id> --json jobs`, label
them by hand, redact and cut the log as above, and check that tabib's triage of the excerpt equals its triage of
the whole log. Prefer runs from projects tabib was not tuned on, and take them newest first rather than choosing.
