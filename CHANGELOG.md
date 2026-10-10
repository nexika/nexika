# Nexika changelog

Nexika is released as a whole (tag `nexika-vX.Y.Z`) and each plugin also has its own version, tag
(`<plugin>-vX.Y.Z`) and CHANGELOG in `plugins/<plugin>/CHANGELOG.md`.

## [0.3.0] - 2026-10-10

### Released
| Project | Version |
|---|---|
| [amin](plugins/amin/CHANGELOG.md) | 0.3.0 |
| [barq](plugins/barq/CHANGELOG.md) | 0.3.0 |
| [haris](plugins/haris/CHANGELOG.md) | 0.3.0 |
| [itqan](plugins/itqan/CHANGELOG.md) | 0.4.0 |
| [mizan](plugins/mizan/CHANGELOG.md) | 0.3.0 |
| [tabib](plugins/tabib/CHANGELOG.md) | 0.3.0 |

## [0.2.0] - 2026-10-08

### Released
| Project | Version |
|---|---|
| [amin](plugins/amin/CHANGELOG.md) | 0.2.0 |
| [barq](plugins/barq/CHANGELOG.md) | 0.2.0 |
| [bayan](plugins/bayan/CHANGELOG.md) | 0.2.0 |
| [hafiz](plugins/hafiz/CHANGELOG.md) | 0.2.0 |
| [haris](plugins/haris/CHANGELOG.md) | 0.2.0 |
| [itqan](plugins/itqan/CHANGELOG.md) | 0.3.0 |
| [lawha](plugins/lawha/CHANGELOG.md) | 0.1.0 |
| [manar](plugins/manar/CHANGELOG.md) | 0.2.0 |
| [mizan](plugins/mizan/CHANGELOG.md) | 0.2.0 |
| [prof](plugins/prof/CHANGELOG.md) | 0.2.0 |
| [siyaq](plugins/siyaq/CHANGELOG.md) | 0.2.0 |
| [tabib](plugins/tabib/CHANGELOG.md) | 0.2.0 |

## [0.1.0] - 2026-10-06

The first release of Nexika: 11 plugins for Claude Code that work alone and better together.

| Plugin | Version | What it does |
|---|---|---|
| [prof](plugins/prof/CHANGELOG.md) | 0.1.0 | A personal programming professor: lessons, onboarding juniors, warm-ups and learning reports |
| [barq](plugins/barq/CHANGELOG.md) | 0.1.0 | Many file and project operations in one call, with a seen-before cache and short test output |
| [itqan](plugins/itqan/CHANGELOG.md) | 0.2.0 | Quality workflow: plan, tests first, review, a risk-based guard, learned rules, and a proof that work is done |
| [siyaq](plugins/siyaq/CHANGELOG.md) | 0.1.0 | Project knowledge loaded only when relevant, loading less as the context fills |
| [amin](plugins/amin/CHANGELOG.md) | 0.1.0 | A repository maintainer that never merges for you: triage, issue work, change notes, releases |
| [manar](plugins/manar/CHANGELOG.md) | 0.1.0 | Be found by search engines and AI assistants |
| [bayan](plugins/bayan/CHANGELOG.md) | 0.1.0 | Claude writes like a clear, friendly person, in English and Arabic |
| [hafiz](plugins/hafiz/CHANGELOG.md) | 0.1.0 | Claude remembers your work: memories, handoff notes, search |
| [haris](plugins/haris/CHANGELOG.md) | 0.1.0 | Guards your machine and accounts from harmful agent actions |
| [mizan](plugins/mizan/CHANGELOG.md) | 0.1.0 | A band above the prompt that keeps the session in balance: CI, PRs, context, cost, device |
| [tabib](plugins/tabib/CHANGELOG.md) | 0.1.0 | Finds out why CI failed, with evidence; diagnoses only |

### Working together
- Shared status files under `~/.claude/nexika/status/` (`nexika.<plugin>/1`), protected by haris.
- mizan shows haris's state, itqan's proof and tabib's diagnosis; siyaq reads mizan's context level;
  hafiz saves the handoff when mizan says the context is full; tabib hands fixes to itqan.

### Install
```
/plugin marketplace add nexika/nexika
/plugin install <plugin>@nexika
```
