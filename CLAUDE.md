# Nexika: notes for Claude

Twelve Claude Code plugins in one marketplace (`plugins/<name>/`, listed in
`.claude-plugin/marketplace.json`). Each plugin installs on its own: Python standard library only,
no imports from another plugin. The README has the layout and the contributing steps; this file is
what past sessions learned the hard way.

## Before every commit

```bash
ruff check .                         # line length 110
pytest -q                            # ~1500 tests, ~35 s
python3 plugins/amin/bin/amin copies --check
```

A lint warning can be a real bug: an "unused import" once meant a new local variable `check`
was hiding the `check` module, which would have broken `amin check-fragment` in CI.

Changed `plugins/lawha/engine/`? Also `cd plugins/lawha/engine && npm run build && npm test` and
commit `dist/` (CI fails when `dist/` is out of date).

## Shared code lives in `common/`

`secrets.py`, `inject.py`, `status.py`, `gitinfo.py`, `family.py` and `background.py` are copied
into the plugins that ship them; `.amin.json` "copies" lists every copy. **Edit the file in
`common/`, then run `python3 plugins/amin/bin/amin copies`.** Never edit a plugin's copy: a test
compares every copy byte for byte. A new shared file goes in `common/` and `.amin.json`, and in
the list in `tests/test_common.py`.

## Keep the logic portable

Nexika runs inside Claude Code today, but its logic should not depend on Claude Code or on
Claude: one day an adapter will run it with other agents and open-source models (#114).
- Logic lives in plain functions and command-line tools (`bin/<plugin>`), standard library only.
  They take plain values and return plain values, never Claude Code's hook JSON.
- A hook entry point only translates: read Claude Code's JSON, call the logic, write Claude Code's
  JSON. Keep it thin, with no decisions in it.
- Model calls should have one door. Today hafiz, itqan and prof each start `claude -p`
  themselves; `common/background.py` only checks consent and logs. Don't add a new place that
  starts a model: extend `common/background.py` instead.
- Skills and agent prompts say what to do, not which Claude feature does it, where they can.

## Family rules every plugin follows

- One settings file for the family: `~/.claude/nexika/settings.json` (`NEXIKA_HOME` moves it),
  read through `common/family.py` (role) and `common/background.py` (background-call consent).
- A paid background call (`claude -p`) asks `background.allowed()` first, runs with
  `background.child_env()`, and calls `background.record()`. Every Nexika hook exits at once
  when `NEXIKA_BACKGROUND=1`.
- Hooks must never break a session (any error means "do nothing") and must start fast: import
  heavy modules inside the function that needs them. Measure with `python3
  plugins/mizan/bin/mizan doctor` before and after.
- Anything stored is redacted with the shared `secrets.redact` first.

## Tests

- `tests/conftest.py` already keeps every data folder (`NEXIKA_HOME`, `NEXIKA_STATUS_HOME`,
  `PROF_HOME`, ...) in `tmp_path` and gives git a test identity. Use its `_git` helper; never
  touch the real `~/.claude`.
- Never compare times from two separate calls: pin the clock (`monkeypatch.setattr(mod, "now",
  ...)`). A test that passed only when both calls fell within the same second failed in CI.
- Each fix starts with a failing test that reproduces the issue. Show that it fails before the
  fix.

## Changes, commits and PRs

- Branch from `origin/main`. One commit per issue, with the message ending in `Fixes #N`.
- Every changed plugin needs a change note:
  `python3 plugins/amin/bin/amin fragment add <plugin> <type> "<what changed for users>" --id <N>`.
  Never edit `CHANGELOG.md` or version files: `/amin:release` does that.
- No Claude attribution or `Co-Authored-By` lines in commits or PR descriptions.
- `main` needs the **CI passed** check and an up-to-date branch; PRs are squash-merged.
- When a decision belongs to the maintainer (security trade-offs, new storage, scope), do the
  safe part and write the open question in the PR instead of guessing.

## Several sessions at once

- Split the work by plugin so no two sessions edit the same files; issues that touch many
  plugins go last, in one session.
- After a squash merge, start the next batch on a new branch from `origin/main`. Reusing the old
  branch brings back its commits.
- Merge overlapping PRs one at a time, then merge `main` into the next one and re-run the tests.
  Don't just accept both sides blindly: the other PR may have changed behavior your tests assume.
