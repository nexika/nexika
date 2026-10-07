# Nexika

[![CI](https://github.com/nexika/nexika/actions/workflows/ci.yml/badge.svg)](https://github.com/nexika/nexika/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> **The next wisdom for Claude Code.** *Nex*t + h*ika* (from *hikma*, حكمة - wisdom).
> Plugins that make Claude work smarter and help people learn deeper.

## Plugins

| Plugin | What it does | Status |
|---|---|---|
| [**prof**](plugins/prof/README.md) | Turns Claude into a personal programming professor: step-by-step lessons, onboarding juniors to a codebase, a warm-up check at the start of each session, and a learning report at the end | v0.1.0 |
| [**barq**](plugins/barq/README.md) ⚡ | Many file and project operations in one call: batched and symbol reads, a seen-before cache, short test/build output, git status with next steps, secret masking, savings stats | v0.1.0 |
| [**itqan**](plugins/itqan/README.md) | Quality workflow without the friction: plan, failing tests first, implement, verify, specialist review; a risk-based guard that only stops dangerous actions; stack checklists loaded only where they apply; learns project rules from your corrections | v0.2.0 |
| [**siyaq**](plugins/siyaq/README.md) | Project knowledge loaded only when relevant: entries generated from your docs, multilingual matching (Arabic included) with ranking and a token budget, file triggers, stats on what helped and what is missing | v0.1.0 |
| [**amin**](plugins/amin/README.md) | A repository maintainer that never merges for you: issue triage with approval, issues worked into pull requests in isolated worktrees, change notes enforced in CI, step-by-step releases (versions, CHANGELOG, tags, GitHub Releases) | v0.1.0 |
| [**manar**](plugins/manar/README.md) | Be found by search engines and AI assistants: deterministic SEO and AI-visibility audits, fixes written into your code (Next.js, Astro, ASP.NET Core, static), and measured mentions and citations in Gemini, Perplexity, ChatGPT and Claude, compared across releases | v0.1.0 |
| [**bayan**](plugins/bayan/README.md) | Claude writes like a clear, friendly person, in English and Arabic: explanations someone with no coding experience can follow, automatic clean-up of machine habits (hidden characters, AI signature lines, filler phrases) and a line-by-line style check | v0.1.0 |
| [**hafiz**](plugins/hafiz/README.md) | Claude remembers your work: decisions, tasks, problems, files and links captured as you work (no AI calls, secrets replaced before saving), a short start card, a snapshot restored after compaction, automatic handoff notes, Arabic and English search, and a detailed session summary naming the issue and branch (Sonnet by default) | v0.1.0 |
| [**haris**](plugins/haris/README.md) | Guards your machine and your accounts from harmful agent actions: every tool call read by a real shell parser (wrappers, pipes, substitutions, heredocs) and judged by action and target, so safe reads and project runs pass, risky actions ask and dangerous ones are refused with a plain reason; secrets, persistence spots and haris itself protected, secrets never sent off the machine, prompt-injection warnings, approvals only from what you type | v0.1.0 |
| [**mizan**](plugins/mizan/README.md) | Keeps your session in balance: a band above the prompt shows the branch and who started it, open PRs or MRs per person like `Loai(7) Jean(3)`, the branch's CI (passed, failed with the job, running), RAM and disk with warnings, the context level (fresh, mid, full), the running agent, the current task step and the cost; `/mizan` opens the details and the itqan proof. At full context it saves a hafiz handoff and puts `/clear` in the prompt for you to send. English and Arabic | v0.1.0 |
| [**tabib**](plugins/tabib/README.md) | Finds out why CI failed, with evidence: the failing tests and errors from the log, the kind of failure (code, one Python or OS only, flaky, infrastructure, dependencies), the commits since the last green run, the failing tests run again in a throwaway git worktree, and the cause backed by the code; mizan's band shows the kind as soon as CI fails and a "Why?" button. Diagnoses only: never edits code, pushes or re-runs CI. English and Arabic | v0.1.0 |
| [**lawha**](plugins/lawha/README.md) | Frontend you can see: every page checked in a real browser at six widths, light and dark, LTR and RTL and with reduced motion (sideways scrolling, clipped text, tap targets, accessibility, layout shift, motion, CSS that breaks Arabic), an eye that measures alignment, spacing rhythm, type and colour, a diff against design exports, fixes found from the screenshots, and your Tailwind, shadcn and TanStack design system indexed; mizan's band shows the result with a Fix button and itqan's proof includes it. React, TanStack, Tailwind, shadcn/ui. English and Arabic | v0.1.0 |

## Install

```
/plugin marketplace add nexika/nexika
/plugin install prof@nexika
/plugin install barq@nexika
/plugin install itqan@nexika
/plugin install siyaq@nexika
/plugin install amin@nexika
/plugin install manar@nexika
/plugin install bayan@nexika
/plugin install hafiz@nexika
/plugin install haris@nexika
/plugin install mizan@nexika
/plugin install tabib@nexika
/plugin install lawha@nexika
```

Restart Claude Code afterwards so the plugin's hooks load.

## Repository layout

```
nexika/
├─ .claude-plugin/marketplace.json   ← the catalogue: lists every plugin
└─ plugins/
   └─ prof/                          ← one folder per plugin
      ├─ .claude-plugin/plugin.json
      ├─ output-styles/  skills/  agents/  hooks/  scripts/
      └─ README.md
```

To add a plugin: create `plugins/<name>/` with its own `.claude-plugin/plugin.json`, then add
it to `.claude-plugin/marketplace.json`.

### The family profile: who the user is

`~/.claude/nexika/profile.json` (`NEXIKA_PROFILE` moves it) holds one role, `developer`,
`learner` or `writer`, so the plugins agree on who they work for: bayan picks its reader level
from it, prof decides whether to teach or just answer, and siyaq how loosely it matches docs. A
setting made in a plugin itself still wins. The first session asks once; change it later with
`python3 common/family.py role <role>` (each plugin ships a copy and prints its path).

### Status files: how the plugins talk to each other

A plugin that knows something the others can use publishes it as a small JSON file under
`~/.claude/nexika/status/` (`NEXIKA_STATUS_HOME` moves it): `<plugin>.json` for what holds across
sessions, `<plugin>/<session>.json` for one session. Every file carries
`"schema": "nexika.<plugin>/1"` and `"updated"` (seconds since the epoch); a reader ignores a file
with another schema or one too old, and a missing file means "nothing known". haris protects the
folder, so only the plugins write there, never Claude.

| File | Written by | Read by |
|---|---|---|
| `mizan/<session>.json` | mizan: context level, cost, device, tasks | siyaq (loads less as the context fills), mizan's daily cost |
| `haris/<session>.json` | haris: profile and mode | mizan's band |
| `itqan.json` | itqan: the latest proof per project | mizan's proof pane |
| `tabib.json` | tabib: the latest CI diagnosis per project and branch | mizan's band and pane, itqan's proof |
| `lawha.json` | lawha: the latest check of each project's pages on every screen (a pointer into lawha's own folder) | mizan's band and pane, itqan's proof |

## Develop locally

```bash
claude --plugin-dir ./plugins/prof          # run one plugin without installing
claude plugin validate .                    # check the marketplace
claude plugin validate ./plugins/prof/.claude-plugin/plugin.json
claude plugin test ./plugins/mizan          # a mod's own tests (*.test.ts)
pytest                                      # tests (pip install pytest)
ruff check .                                # lint (pip install ruff)
```

## Contributing

`main` is protected: every change goes through a pull request that must pass CI.

1. Branch from `main`: `git switch -c feat/<short-name>` (or `fix/`, `docs/`, `chore/`).
2. If you change a plugin, add a change note for it (see [changelog.d/](changelog.d/README.md)):
   `python3 plugins/amin/bin/amin fragment add <plugin> <type> "<what changed>" --id <PR>`.
3. Commit, push the branch, and open a pull request.
4. CI runs lint, tests (Python 3.10-3.14, Linux and macOS), `claude plugin validate`, the mod
   tests (`claude plugin test`) and the change-notes rule. The **CI passed** check must be green
   before merging.
5. Squash-merge; the branch is deleted automatically.
6. Releases are cut with `/amin:release`: one version, CHANGELOG and tag per plugin.

## License

MIT © 2026 Loai Elattar
