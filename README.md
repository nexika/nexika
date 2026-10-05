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

## Develop locally

```bash
claude --plugin-dir ./plugins/prof          # run one plugin without installing
claude plugin validate .                    # check the marketplace
claude plugin validate ./plugins/prof/.claude-plugin/plugin.json
pytest                                      # tests (pip install pytest)
ruff check .                                # lint (pip install ruff)
```

## Contributing

`main` is protected: every change goes through a pull request that must pass CI.

1. Branch from `main`: `git switch -c feat/<short-name>` (or `fix/`, `docs/`, `chore/`).
2. If you change a plugin, add a change note for it (see [changelog.d/](changelog.d/README.md)):
   `python3 plugins/amin/bin/amin fragment add <plugin> <type> "<what changed>" --id <PR>`.
3. Commit, push the branch, and open a pull request.
4. CI runs lint, tests (Python 3.10-3.14, Linux and macOS), `claude plugin validate` and the
   change-notes rule. The **CI passed** check must be green before merging.
5. Squash-merge; the branch is deleted automatically.
6. Releases are cut with `/amin:release`: one version, CHANGELOG and tag per plugin.

## License

MIT © 2026 Loai Elattar
