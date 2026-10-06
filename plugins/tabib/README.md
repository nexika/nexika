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
| **Failures** | pytest, jest, vitest, go test, dotnet test, cargo test, tsc, ruff, eslint: test, file, line, message |
| **Signals** | time limits, out of memory (exit 137), the network, rate limits, the runner, missing credentials, dependency resolution |
| **Kinds** | **code**; **matrix** (fails only on one Python, Node or OS); **flaky** (the same commit passed in another run); **infra** (cancelled, a time limit, the network, the runner, credentials); **dependency**; **unknown** |
| **History** | the last green run of the same workflow, the commits since (a commit that touched a failing file is a suspect), dependency files that changed |

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
