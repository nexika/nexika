# Nexika

> **The next wisdom for Claude Code.** *Nex*t + h*ika* (from *hikma*, حكمة - wisdom).
> Plugins that make Claude work smarter and help people learn deeper.

## Plugins

| Plugin | What it does | Status |
|---|---|---|
| [**prof**](plugins/prof/README.md) | Turns Claude into a personal programming professor: step-by-step lessons, onboarding juniors to a codebase, a warm-up check at the start of each session, and a learning report at the end | v0.1.0 |
| **tools** | Batched, token-saving operations for Claude Code (inspired by claude-supertool) | planned |

## Install

```
/plugin marketplace add nexika/nexika
/plugin install prof@nexika
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
```

## License

MIT © 2026 Loai Elattar
