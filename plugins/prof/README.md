# prof - a personal programming professor for Claude Code

Part of [Nexika](../../README.md).

Turns Claude into a patient teacher: it explains step by step, asks questions, lets you write
the code, and remembers your progress. It also onboards junior developers to an existing project.

## What's inside

| Part | Name | What it does |
|---|---|---|
| Output style | `Professor` | Changes Claude's whole personality into a teacher (`/output-style` → Professor) |
| Skill | `/prof:learn <topic>` | Lesson on a concept: level check → analogy → examples → questions → exercise |
| Skill | `/prof:onboard [path]` | Explains a project to a newcomer in layers, then guides a first task |
| Skill | `/prof:walkthrough <file\|symbol>` | Line-by-line explanation of a piece of code with a traced example |
| Skill | `/prof:quiz [topic]` | 5 questions, one at a time, with feedback and score |
| Skill | `/prof:warmup [topic]` | Start of session: tests what you kept from past sessions, estimates your level, re-teaches gaps **before** anything new |
| Skill | `/prof:report` | End of session: what you learned, what you did, check results, weak areas & logic gaps, level, what to review next |
| Skill | `/prof:progress [show\|update\|reset]` | Your learner profile and what to learn next |
| Agent | `project-cartographer` | Read-only explorer that maps a codebase for the onboard skill |
| Hook | SessionStart | Silent unless there is a learner: no learner profile, nothing due and a Nexika role other than learner means no note at all. When something is due for review: injects profile, last report's weak areas, open items per topic, and the warm-up rule. Otherwise a one-line note, so working sessions stay working sessions. When the Nexika profile says you are a developer or a writer, always the one-line note: questions about code get answers, not lessons |
| Hook | SessionEnd | If a tutoring session ended without a report and you agreed to automatic reports, writes one in the background (`claude -p`, Sonnet) |

## The learning loop

```
 SESSION START                       DURING                       SESSION END
 ─────────────                       ──────                       ───────────
 hook prints:                        Professor style +            /prof:report (or the
  • profile                          learn/onboard/quiz           SessionEnd hook if you
  • last weak areas        ──►       teach, and track each   ──►  just quit) writes
  • open items per topic             concept as:                  reports/DATE_HHMM_SID.md
  • warm-up rule                     understood / shaky /              │
        │                            missed / not-checked              ▼
        ▼                                                         merge-report updates
 /prof:warmup on the topic                                       topics/<slug>.md
  → questions on missed/shaky/                                         │
    unchecked + retention                                              │
  → level estimate                                                     │
  → re-teach gaps FIRST  ◄─────────────── next session reads ─────────┘
```

## Data (`~/.claude/nexika/prof/`)

```
profile.md                    level, goals, mastered, weak spots, log (progress skill)
reports/2026-10-05_1430_ab12cd34.md   one report per session
topics/csharp-async.json      concept checklist (the data: status, evidence, date, successes in a row)
topics/csharp-async.md        the same, rendered worst first (status edits here are kept):
                              - [missed] async void vs async Task — guessed "slower" (2026-10-05)
                              - [understood] Task.WhenAll — wrote a correct example (2026-10-04)
settings.json                 your answer about automatic reports
hook.log                      what the hooks did (auto reports, errors)
```

Retention checks use spaced repetition: a concept you just understood comes back after 3 days,
then 7, 14, 30, 60 and 120 days for each success in a row. A miss starts it over.

Helper (stdlib Python): `python3 scripts/prof_store.py topic <slug>` · `merge-report <file>`.
Set `PROF_HOME` to keep data somewhere else (e.g. one folder per junior).

Automatic reports run Claude (Sonnet) in the background, which uses your plan or API credits, so
they are off until you agree: in your first tutoring session Claude asks once and stores the
answer (`python3 scripts/prof_store.py auto-report on|off|status`). They only run for tutoring
sessions (you ran a `/prof:` command, Claude used a `prof:` skill, or the output style is
Professor; a message that only mentions `/prof:` doesn't count) with at least 3 learner messages,
and never twice for the same session. `background_calls: off` stops them even after a yes, and
`on` allows them without asking.
One family setting covers every Nexika background model call: `background_calls` in
`~/.claude/nexika/settings.json` is `ask` (the default), `on` or `off`, and
`python3 scripts/prof_background.py status` shows it with how many calls ran or were skipped in the last 30 days.
Background calls run with `NEXIKA_BACKGROUND=1`, so no Nexika plugin's hooks fire inside them.

## Try it locally

```bash
claude --plugin-dir ~/nexika/plugins/prof
```

Then inside Claude Code:

```
/output-style            # choose "Professor"
/prof:learn async/await in C#
/prof:onboard
```

## Install

```
/plugin marketplace add nexika/nexika
/plugin install prof@nexika
```
