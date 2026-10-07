# mizan (ميزان) - keeps your session in balance

Part of [Nexika](../../README.md). *Mizan* means scale, or balance.

A long Claude Code session drifts out of balance without telling you: the context fills, the
cost climbs, CI fails on the branch, the machine runs out of memory (a full machine once stopped
a build halfway). mizan keeps all of it in one band above the prompt:

```
⎇ feat/login (Loai) · PRs Loai(7) Jean(3) · CI failed: test (py3.10) · RAM 64% · Disk 81%
Context mid 52% · $1.84 · Agent Explore: find the auth code · Task 3/7: Writing tests · haris standard
```

In Arabic (`"lang": "ar"`, or an Arabic system locale):

```
⎇ feat/login (Loai) · طلبات الدمج Loai(7) Jean(3) · فشل الفحص: test (py3.10) · الذاكرة 64% · القرص 81%
السياق متوسط 52% · $1.84 · الوكيل Explore: find the auth code · المهمة 3/7: Writing tests · حارس standard
```

| Part | What it shows |
|---|---|
| **Branch** | the branch and who started it: the author of its pull request when there is one, else of its first commit of its own, else you |
| **PRs / MRs** | open pull requests (GitHub, `gh`) or merge requests (GitLab, `glab`) per person, and `Reviews for you 2` when some wait for your review |
| **CI** | the branch's checks: passed, failed with the job's name, or running with how long so far and about how long is left (`CI running 3m · ~4m left`, from its recent runs) (checked every 90 s, 45 s while running, four times less often after 10 minutes with nothing new); with tabib, the kind of failure (`tabib: only py3.10`, `tabib: flaky?`) and a **Why?** button |
| **Pages** | with lawha, its latest check of the project's pages at this commit: `lawha ✓ 6 widths`, or `lawha: 3 to fix` with a **Fix** button |
| **RAM, Disk** | in use, yellow from 85 %, red from 95 % with a notice |
| **Context** | fresh under 40 %, mid 40-75 %, full above 75 % (`context_mid` and `context_full` move them) |
| **Cost** | this session in dollars; with a daily budget set, today's total across sessions |
| **Agent** | the running agent and its task, `+n more` when several run |
| **Task** | where Claude stands in its task list, like `3/7: Writing tests`; without one, its agents are the list (started since your last message, done when they finish) |
| **haris** | its profile, or `haris watching` in watch mode |

`/mizan` opens the details in a pane; `/mizan proof` opens itqan's proof.

## When the context fills

- **mid:** hafiz refreshes the handoff note every few replies, so nothing is lost if you stop.
- **full:** mizan has hafiz save the handoff, then puts `/clear` in the prompt box and says
  *"Context full: your work is saved. Press Enter to start fresh."* You press Enter; mizan
  never clears or compacts the session itself, and never writes over text you are typing (then
  it asks you to type `/clear`). The new session starts with hafiz's handoff card.

## When the work is done

When every task in Claude's list is done, the band asks **"Done. Show me the proof?"**. Yes opens
itqan's proof in the pane: the tests, lint and build checks itqan ran itself, the review verdict
and the requirement checklist (both marked as reported by Claude). With no proof yet, mizan puts
`/itqan:proof` in the prompt for you to send.

## How it works

```
mod (hooks/register.tsx)                             Python core (bin/mizan, stdlib only)
  every 15 s, after each reply,          stdin  ─►     git: branch, creator, remote
  on context/cost changes:                             cache of gh / glab (refreshed in the
  context, cost, agents, task list  ───────────►        background, never waited for)
                                                       RAM, disk; haris and itqan status files
  draws the band and the pane       ◄───────────       the band lines and pane text (EN / AR)
```

The mod only draws and asks. It runs one program, `python3 <plugin>/bin/mizan`, with one of three
fixed subcommands (`status`, `handoff`, `proof`) and the session's figures as JSON on stdin; it
makes no model calls. The core runs only read commands: `git`, and `gh pr list`, `gh pr checks`,
`gh run list`, `gh run view`, `glab mr list`, `glab ci get`, with arguments as a list (no shell).

**Without the mod** (a host that does not load mods): add the status line, which prints the same
two lines (`/mizan:statusline` shows how):

```json
{ "statusLine": { "type": "command", "command": "python3 /path/to/mizan/bin/mizan statusline" } }
```

With it, the Stop hook refreshes the handoff at mid and, at full, saves it and tells you to type
`/clear`.

## Commands

| Command | What it does |
|---|---|
| `/mizan` | details pane: branch, PRs per person, CI jobs, device, context, cost, agents, tasks, haris |
| `/mizan proof` | the latest itqan proof in the pane |
| `/mizan:report` | the same as text, for any host |
| `/mizan:statusline` | set up the status line fallback |
| `mizan status [--json]`, `report`, `export --json`, `proof [--json]`, `refresh` | the helper itself |

`export --json` prints the whole snapshot (schema `nexika.mizan/1`).

## Settings

`~/.claude/nexika/mizan/config.json` (yours to edit; haris keeps Claude out of it):

```json
{ "lang": "auto", "daily_budget_usd": 0, "network": true, "context_mid": 40, "context_full": 75 }
```

- `lang`: `auto` (Arabic for an Arabic locale), `en` or `ar`. `MIZAN_LANG` overrides it.
- `daily_budget_usd`: off at `0`; set, the cost turns yellow at 80 % and red at 100 % of it.
- `context_mid`, `context_full`: where the context turns mid and full (the handoff and the `/clear` offer follow them).
- `network`: `false` stops the gh and glab reads (`MIZAN_OFFLINE=1` too).

## The Nexika family

- **hafiz** saves the handoff (`hafiz handoff --save`), at mid every few replies and at full.
- **haris** guards mizan's code, its folder and the shared status files from Claude, and shows its
  profile in the band.
- **siyaq** reads mizan's level and loads less project knowledge as the context fills: normal,
  half at mid, only the strongest match as a summary when full.
- **itqan** makes the proof (`/itqan:proof`) that mizan shows.
- **tabib** sorts a failed CI run once per run (no AI) when mizan sees it; Why? puts
  `/tabib:diagnose` in the prompt, and the pane shows the cause it found.
- **lawha** checks the project's pages on every screen; the band shows its latest check of this
  commit, Fix puts `/lawha:check --fix` in the prompt, and the pane lists the problems and the
  report. mizan reads only checks lawha saved in its own (haris-guarded) folder.
- All of them share status files under `~/.claude/nexika/status/`, each `nexika.<plugin>/1`
  (see the [root README](../../README.md#status-files-how-the-plugins-talk-to-each-other)).

## Data

`~/.claude/nexika/mizan/` holds your settings and the gh/glab cache; `~/.claude/nexika/status/mizan/`
one small file per session (level, cost, device, tasks), removed after a week. All owner-only.
Nothing leaves your machine except the gh and glab reads you are already signed in to.

## Credits

The idea, the levels and the "save, then start fresh" flow come from Loai Elattar's own long
sessions. The status line fallback reads Claude Code's own status line JSON.
