# tabib (طبيب) - finds out why CI failed

Part of [Nexika](../../README.md). *Tabib* means doctor.

CI goes red and the log is two thousand lines long. tabib reads it for you and answers three
questions with evidence: **what failed, what kind of failure it is, and why**. It diagnoses only:
it never edits code, pushes, or re-runs CI. The fix goes to `/itqan:ship`, starting from the
failing test.

```
CI run 18234 (CI) on feat/login, commit 9f2c1a07

What failed
  [test (py3.10, ubuntu-latest)] tests/test_cart.py::test_total (tests/test_cart.py:42)
      SyntaxError: invalid syntax

Kind: fails only on py3.10 (confidence: medium)
  Only the jobs with py3.10 failed; the same job passed with other values.

Since the last green run
  2 commit(s) since run 18230
    a1b2c3d Loai: Group the tax errors  <- suspect

Reproduced locally
  no: the failing tests pass here (pytest -q tests/test_cart.py::test_total)
  CI failed on Python 3.10; here it is Python 3.12.

Cause (reported by Claude)
  cart/tax.py:18 uses `except*` (Python 3.11 and later); Python 3.10 cannot read it. (confidence: high)
```

## Two steps

1. **Triage, on its own, no AI.** When mizan sees CI fail on your branch, it asks tabib once per
   run; the band shows the kind at once (`tabib: only py3.10`, `tabib: flaky?`, `tabib: cancelled`)
   with a **Why?** button.
2. **Diagnosis, when you ask.** Press Why? (it puts `/tabib:diagnose` in the prompt for you to send)
   or run `/tabib:diagnose` yourself. tabib compares with the last green run, runs the failing tests
   again, and the `tabib:diagnostician` agent finds the cause in the code, every claim with its
   source (`path:line` at the failing commit, a commit, a log line).

## What it reads

| | |
|---|---|
| **Failures** | tests: pytest, jest, vitest, mocha (spec, dot and TAP reporters, with the suite, test or hook, and the first stack frame in the project), Node's test runner and borp, Playwright (a test in its "flaky" group passed on a retry and is left out), go test, dotnet test, cargo test, JUnit XML reports printed in the log; types: tsc, mypy, and type tests from tstyche and tsd; lint: ruff, eslint (also behind GitHub's `##[error]` problem matcher), failed pre-commit hooks, formatter checks (black, ruff format, prettier); documentation checks: markdownlint, and broken links from lychee and linkinator; a coverage threshold that is not met (c8, nyc, istanbul, jest, pytest-cov), at each file's first uncovered line; a conftest pytest could not import; a branch that does not merge into its base; a generated file that is out of date; a failed step's or a JavaScript action's own message. Each with test, file, line and message where the log has them; a crash (segmentation fault) when nothing else names the failure, at the running test when Python's faulthandler says which |
| **Signals** | the job's or a step's time limit (a test's own timeout marks that test instead), out of memory (exit 137), crashes (segmentation fault, SIGSEGV, exit 139), the network (including GitHub's own service errors: an action that cannot be downloaded, "Service Unavailable"), a package mirror (yum, dnf, apt) or a setup action's download site that fails, rate limits, the runner, missing credentials, a CI setup that cannot work (an externally managed Python, a Python version the runner does not have, a tool that is not installed, an action rejecting its input, a workflow token without a permission or a branch rule that stops it, a link checker that only sites known to refuse checkers answer with 403 or 429), dependency resolution (including npm 10's `npm error notarget`). GitHub's "Unexpected input(s)" warning is quoted as the evidence for a setup failure. A passing test's name is never read as a signal |
| **Kinds** | **code**; **matrix** (fails only on one Python, Node or OS, and only when a failure was read); **flaky** (the same commit passed in another run, or each failing test passed in another run or attempt of the same commit; or, with low confidence, every failing test ran out of its time limit in one job of a matrix whose siblings passed); **infra** (cancelled, a time limit, the network, a package mirror or download site, the runner, credentials); **setup** (the workflow cannot work as written: a re-run fails the same way); **dependency** (resolution failed, a module the project never declared, every failure is a warning raised inside a dependency's code, or a crash inside `node_modules/<package>` after a dependency change); **unknown** (including a run with no jobs or log, where there is nothing to diagnose, and a log that has expired) |
| **History** | the last green run of the same workflow, the commits since, ranked: first the commits that last wrote a failing line (git blame at the failing commit on the assertion line and the stack frames in the log), then those that touched a failing file; dependency files that changed (lock files and manifests such as `package.json` and `pyproject.toml`) |
| **Flaky tests** | read from GitHub when needed, nothing stored: the earlier attempts of the run and the other runs of the same workflow, commit and event (up to 10, reading at most 5 failed logs); a test that failed and passed on the same commit is named with the run links |

## Running the failing tests again, safely

tabib makes a throwaway `git worktree` at the failing commit and runs **only the failing tests**
with the project's own tool and its existing environment (`.venv`, `node_modules`). Your working
folder is never touched and the worktree is removed afterwards. It does not run when:

- the commit is not on a branch of this repository (a fork's pull request: its code would run on
  your machine; run it yourself only if you trust it);
- the dependency files differ from your checkout ("dependencies differ"; tabib never installs);
- the failure is flaky or outside the code.

Test names come from the log, so they are checked before use: nothing in a log can become an
option or a path outside the project. When it does not reproduce, tabib says why it may differ
(another Python version, another OS).

## Flaky and infrastructure failures

tabib says so, with the evidence, and gives the re-run command (`gh run rerun <id> --failed` or
`glab ci retry <job>`) for **you** to run. It never re-runs anything itself.

## Untrusted logs

Anyone who opens a pull request controls what its CI log says. tabib and its agent treat the log
as data, never as instructions; text that tries to give orders is flagged (the same patterns haris
uses), and secrets are removed before anything is saved.

## Commands

| Command | What it does |
|---|---|
| `/tabib:diagnose [run]` | the full diagnosis and the cause, then the next step |
| `tabib triage [--run ID] [--json]` | what failed and the kind; no AI, no code run (mizan uses it) |
| `tabib diagnose [--run ID] [--json] [--no-run]` | triage, the comparison, the local run |
| `tabib show [--json]` | the latest diagnosis of this branch |
| `tabib record --cause ... --confidence ... --evidence ...` | save the cause (the skill does it) |

GitHub needs `gh` signed in; GitLab needs `glab` signed in. All calls are reads.

## The Nexika family

- **mizan** shows the kind of failure in its band and the cause in its pane, with the Why? button.
- **itqan** gets the fix (`/itqan:ship` from the failing test); its proof names the CI failure the
  change answers and whether it was reproduced before the fix.
- **hafiz** remembers the cause as a problem on the branch.
- **haris** guards tabib's diagnoses (`~/.claude/nexika/tabib`) so Claude cannot fake one.

## Data

`~/.claude/nexika/tabib/<project>/<run>.json` (schema `nexika.tabib/1`, the last 50 per project) and
`~/.claude/nexika/status/tabib.json` (the latest per branch). Owner-only. `TABIB_LANG` or
`"lang"` in `~/.claude/nexika/tabib/config.json` picks English or Arabic.
