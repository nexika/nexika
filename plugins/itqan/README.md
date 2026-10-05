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
| Skill | `/itqan:ship <task>` | The full pipeline with gates: branch check → plan approval → red tests → green → build/test/lint → review → commit proposal |
| Agents | `planner`, `code-reviewer`, `security-reviewer`, `test-writer`, `build-fixer` | Specialists the skills launch |
| Packs | `dotnet`, `python` | Checklists for implementing and reviewing, pointed to **only** in projects that use that stack |
| Hook | guard (PreToolUse) | Risk-based: silent for normal work, asks or refuses only for risky actions |
| Hooks | SessionStart / SessionEnd | One short note at start (stacks, packs, last session's guard summary); a silent summary at the end |

## Design choices

| | Typical all-in-one toolkit | itqan |
|---|---|---|
| Context | hundreds of skills listed every session | 3 skills, 5 agents; stack checklists are files read on demand, so they cost nothing until used |
| Guard | asks for justification on every first write | never blocks normal edits; stops only risky actions, with the reason |
| Noise | notices injected during work | silent while you work; one line at the next session start if the guard acted |
| Workflow | many overlapping commands | one pipeline with explicit gates |

## The guard

**Refused** (with the reason and the safe alternative):
- `rm -r` of `/`, `~`, the project root, or anything outside the project
- force-push to a protected branch (`main`, `master`, `develop`, `production`, `release/*`)
- committing a `.env` / key file, or staged changes that contain a secret token
- editing files inside `.git/`

**Asks you first:**
- `git reset --hard` with uncommitted changes, `git clean -f`, `git checkout .` with changes,
  `git branch -D`, `--no-verify`, `git add` of a secret file
- `curl … | sh`, `chmod 777`, `sudo`, SQL `DROP`/`TRUNCATE`, database resets, `terraform destroy`,
  `kubectl delete`, publishing a package
- editing `.env` / key files or lock files; writing content that contains a secret token

Everything else passes silently. Configure per project in `.itqan.json`:

```json
{ "guard": { "protected_branches": ["main", "release/*"], "mode": "on" } }
```

`"mode": "off"` (or `ITQAN_GUARD=off`) disables it. Decisions are logged to
`~/.claude/nexika/itqan/guard.jsonl` (`ITQAN_HOME` to move it).

## Works with the family
- **barq**: agents and skills use `barq` for cheap, batched context and short test/build output
  when it is installed (they fall back to normal tools otherwise).
- **prof**: after a review, juniors can ask `prof:walkthrough` to explain a finding.

## Try it

```bash
claude --plugin-dir ./plugins/itqan --plugin-dir ./plugins/barq
```
