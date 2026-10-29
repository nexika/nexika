# Skill routing check

Does a prompt still start the right skill after its description gets shorter? Claude Code loads every
skill description into every session, so shorter descriptions save tokens (#431). The model picks a skill
from those descriptions, though, so a cut can send "quiz me" to the wrong place or start a lesson when
someone asked a quick question. This check measures that, before and after.

```bash
python3 benchmarks/routing/bench.py --dry-run          # the cases and the command, no model calls
CLAUDE_CODE_OAUTH_TOKEN="$(cat ~/nexika-bench/.token)" flock ~/nexika-bench/.paid.lock \
  python3 benchmarks/routing/bench.py --refs main=origin/main,new=HEAD --runs 3 --out ~/nexika-bench/routing-N
python3 benchmarks/routing/bench.py --summary ~/nexika-bench/routing-N   # the report again
```

The run is paid. Each session costs about $0.05 with Sonnet, so 20 cases × 3 runs × 2 arms is about $6.

## How it works

Each case in `cases.tsv` runs as a fresh `claude -p` session, once per arm. An arm is the twelve plugins
exported from a git ref with `git archive`, so local edits don't count. The session runs in a tiny project
(`app.py` and a README), with a throwaway `HOME` and Claude Code config folder. Nothing from your own setup
gets in: no installed plugins, memory or CLAUDE.md. Each result records the plugins the session loaded,
so you can check this. Only Skill, Read, Grep and Glob are allowed, and a session stops after two turns.

A case passes when the model called the expected skill. A negative case (`-`) passes when no prof skill
ran. Other plugins' skills don't count against it.

| Kind | What it checks |
|---|---|
| kept | a phrase the description still names |
| dropped | a phrase a shorter description no longer names; the model has to route from meaning |
| negative | ordinary work and questions that must not start a lesson, a walkthrough or a report |

Learner data starts empty, so prof's session note stays quiet. The check tests the descriptions alone.
To add lawha or manar cases for their part of #431, add rows and add the plugin to `TESTED`.
