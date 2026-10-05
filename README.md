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
| [**itqan**](plugins/itqan/README.md) | Quality workflow without the friction: plan, failing tests first, implement, verify, specialist review; a risk-based guard that only stops dangerous actions; stack checklists loaded only where they apply | v0.1.0 |

## Install

```
/plugin marketplace add nexika/nexika
/plugin install prof@nexika
/plugin install barq@nexika
/plugin install itqan@nexika
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
2. Commit, push the branch, and open a pull request.
3. CI runs lint, tests (Python 3.10-3.14, Linux and macOS) and `claude plugin validate`.
   The **CI passed** check must be green before merging.
4. Squash-merge; the branch is deleted automatically.

## License

MIT © 2026 Loai Elattar
