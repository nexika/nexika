# itqan (إتقان) - quality without the friction

Part of [Nexika](../../README.md). *Itqan* means doing work with excellence.

A small, sharp quality workflow for Claude Code: plan, write failing tests first, implement,
verify, review with specialists, then ship. It learns from what made big all-in-one toolkits
heavy: it stays out of the way until something is actually risky.

## What's inside

| Part | Name | What it does |
|---|---|---|
| Skill | `/itqan:plan <task>` | A verified plan: acceptance criteria, existing code (file:line), tests first, steps, risks. No code edits |
| Skill | `/itqan:review [PR \| base \| paths]` | Code + security reviewers in parallel; every serious finding is re-checked against the code before it is reported |
| Skill | `/itqan:ship <task>` | The full pipeline with gates: branch check → plan approval → red tests → green → build/test/lint → review → proof → commit proposal |
| Skill | `/itqan:proof` | The proof a change is done, saved as JSON: itqan runs the project's own tests, lint and build checks itself (found from its files, never a command Claude passes in), and records the review verdict and the requirement checklist, marked as reported by Claude. An `approve` verdict is refused while a critical or high finding is still open |
| Skill | `/itqan:learn` | Approve, reword or reject rules learned from your repeated corrections → `.itqan/rules.md` |
| Skill | `/itqan:insights [days]` | What is actually used and whether each rule works |
| Agents | `planner`, `code-reviewer`, `security-reviewer`, `test-writer`, `build-fixer` | Specialists the skills launch |
| Packs | `dotnet`, `python`, `node`, `go` | Checklists for implementing and reviewing, pointed to **only** in projects that use that stack |
| Hook | guard (PreToolUse) | Risk-based: silent for normal work, asks or refuses only for risky actions |
| Hooks | learning (UserPromptSubmit, SessionEnd) | Notices corrections; after the session, extracts general lessons in the background |
| Hook | usage (PostToolUse) | Records which skills and agents (of any plugin) are used |
| Hooks | SessionStart / SessionEnd | One short note at start (stacks, packs, project rules, waiting proposals, last guard summary) |

## Learning from your corrections

```
you correct Claude ──► a cheap word filter (English + Arabic) flags the message, silently
session ends ───────► a background extractor reads only those exchanges and keeps lessons that
                      apply generally ("we use X", "never Y"), ignoring one-off fixes
same lesson twice ──► PROPOSED rule ──► /itqan:learn: approve / reword / reject
approved ───────────► .itqan/rules.md (commit it: your team and future sessions share it)
corrected again ────► counted against the rule: /itqan:insights says it needs rewording
```

Nothing becomes a rule without your approval. Edit `.itqan/rules.md` freely: your wording wins,
and deleting a line retires the rule. Turn learning off with `"learn": {"mode": "off"}` in
`.itqan.json` or `ITQAN_LEARN=off`.

Extracting lessons runs Claude (Sonnet) in the background on your plan or API credits, so it only
runs once you allow background model calls; until then itqan skips it and asks you once.
One family setting covers every Nexika background model call: `background_calls` in
`~/.claude/nexika/settings.json` is `ask` (the default), `on` or `off`, and
`python3 scripts/itqan_background.py status` shows it with how many calls ran or were skipped in the last 30 days.
Background calls run with `NEXIKA_BACKGROUND=1`, so no Nexika plugin's hooks fire inside them.

## Insights

`/itqan:insights` answers "is this helping?" from real usage:

```
workflows: itqan:review 6, itqan:ship 2
agents: itqan:code-reviewer 6, itqan:security-reviewer 5, Explore 3
other skills used: prof:learn 2, ecc:code-review 1   (plugins whose skills were used: ecc, prof)
guard (all projects): 1 refused, 3 asked | top: reset-hard-dirty 2, force-push-protected 1
  asks you approved: 2 of 3 (67%): each one is likely a false alarm worth a rule in .itqan.json
corrections captured: 9
learning: 4 extraction(s), $0.06 (Sonnet, in the background)
rules: 3 approved, 1 waiting for approval, 4 seen once
  [use-file-scoped-namespaces] 12d old: working (no repeat corrections)
  [run-tests-before-commit] 5d old: corrected again 2x since approval: reword it or check it is followed
```

A plugin with hundreds of skills of which you used one is a context cost worth questioning.

## Design choices

| | Typical all-in-one toolkit | itqan |
|---|---|---|
| Context | hundreds of skills listed every session | 5 skills, 5 agents; stack checklists are files read on demand, so they cost nothing until used |
| Learning | patterns saved automatically | lessons proposed only after repeated corrections, applied only after your approval, and measured afterwards |
| Guard | asks for justification on every first write | never blocks normal edits; stops only risky actions, with the reason |
| Noise | notices injected during work | silent while you work; one line at the next session start if the guard acted |
| Workflow | many overlapping commands | one pipeline with explicit gates |

## The guard

**Refused** (with the reason and the safe alternative):
- `rm -r` of `/`, `~`, the project root, or anything outside the project
- force-push to a protected branch (`main`, `master`, `develop`, `production`, `stable`,
  `release/*`)
- committing a `.env` / key file, or staged changes that contain a secret token
- editing files inside `.git/`

**Asks you first:**
- `git reset --hard` with uncommitted changes, `git clean -f`, `git checkout .` with changes,
  `git branch -D`, `--no-verify` or `SKIP=<hook> git commit`, `git add` of a secret file
- `curl … | sh`, `chmod 777`, `sudo`, SQL `DROP`/`TRUNCATE`, database resets, `terraform destroy`,
  `kubectl delete`, publishing a package
- editing `.env` / key files or lock files; writing content that contains a secret token

Everything else passes silently. When [haris](../haris/README.md) is installed and on, haris
covers the safety rules in the sessions it guards, and this guard keeps only its quality rules:
editing secret files and lock files, writing a secret, and skipping hooks with `--no-verify` or `SKIP=`.
If haris is switched off, set to watch, or disabled with `/plugin`, the full guard is back.

Configure per project in `.itqan.json`:

```json
{ "guard": { "protected_branches": ["main", "release/*"], "mode": "on" } }
```

`"mode": "off"` (or `ITQAN_GUARD=off`) disables it.

## Data

In `~/.claude/nexika/itqan/` (`ITQAN_HOME` to move it): `guard.jsonl` (guard decisions),
`sessions.jsonl` (per-session guard summary), `signals.jsonl` (messages flagged as corrections),
`usage.jsonl` (skills/agents used), `projects/<name>-<hash>/learn.json` (lessons and their
evidence). In the project: `.itqan/rules.md` (approved rules, meant to be committed).
Files are readable only by you (0600 in a 0700 folder), known secret shapes are replaced with
`[secret]` before anything is written, and each `.jsonl` file is rotated to `<name>.1.jsonl` at 1 MB.

## Works with the family
- **barq**: agents and skills use `barq` for cheap, batched context and short test/build output
  when it is installed (they fall back to normal tools otherwise).
- **prof**: after a review, juniors can ask `prof:walkthrough` to explain a finding.
- **mizan**: when every task is done, mizan asks "Done. Show me the proof?" and shows the latest
  proof in its pane. itqan announces it in `~/.claude/nexika/status/itqan.json` (schema
  `nexika.itqan/1`); the proof itself is `nexika.itqan.proof/1`, under
  `~/.claude/nexika/itqan/proofs/<project>/latest.json`.
- **tabib**: a proof made after `/tabib:diagnose` names the CI failure it answers and whether it
  was reproduced before the fix.

## Try it

```bash
claude --plugin-dir ./plugins/itqan --plugin-dir ./plugins/barq
```
