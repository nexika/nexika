# hafiz (حافظ) - Claude remembers your work

Part of [Nexika](../../README.md). *Hafiz* means the one who keeps and remembers.

A long session loses its details at compaction, and a new session starts from nothing. hafiz
keeps what happened in the work (the decisions, tasks, problems, files and links) and
gives Claude just enough of it at the right time: a short card at the start, a snapshot after
compaction, a handoff note between sessions, and a search when you ask.

## How it works

```
every reply (Stop) ──► read only the new part of the transcript ─► fixed rules, no AI:
                         decision  answers to Claude's questions, approved plans,
                                   "let's go with ...", "don't use ...", "قررنا", "خلينا نستخدم"
                         task      Claude's task list, kept up to date (open / done)
                         problem   a failing test, build or lint command; solved when it passes again
                         file      files Claude changed
                         link      URLs you share, pull requests and issues created
                       ─► memories + the handoff note for this branch (always fresh)
before compaction ───► snapshot: goal, latest requests, open tasks, decisions, problems, files
after compaction ────► the snapshot is given back to Claude (up to ~3 KB)
session start ───────► a short card (under 1.5 KB): last session, open tasks, problems, decisions
on request ──────────► search (Arabic and English), handoff note, detailed summary
```

Every memory records its **type**, **date**, **branch**, **commit**, **session** and **source**
(`transcript <session> L<line>`, or `manual`), so it can always be checked.

### Built to be trusted
- **No AI calls** while you work: capture is rules only, so it costs no tokens and no time.
- **Secrets are not stored.** API keys and tokens of the common services, passwords in
  assignments, flags (`--password`, `mysql -p`, `curl -u`), headers (`Authorization`, `Cookie`),
  connection strings and credentials in URLs are replaced with `[secret]` before anything is
  written. Anything between `<private>` and `</private>` is dropped, and its words (6+
  characters) are also masked later when Claude reuses them, in a command for example. Rules
  cannot know every format: put anything sensitive in `<private>` tags to be sure.
- **Outside the repo, owner-only:** data lives in `~/.claude/nexika/hafiz/<project>/` (folders
  0700, files 0600, like Claude Code's own transcripts) and is shared by all worktrees of a
  repository. Nothing is committed, nothing is sent anywhere.
- **Tool output stays out of the cards:** the start card and the compaction restore name a
  failing command but never repeat its output, which could carry text written to steer Claude.
- **Small and bounded:** at most 3,000 memories per project (old automatic file and link
  memories go first), session state kept 60 days, snapshots 7 days.
- **Branch-aware:** memories belong to a branch; `--project` ones hold everywhere.

## Skills

| Skill | What it does |
|---|---|
| `/hafiz:recall [words]` | Search memories in Arabic or English, then check them against the code before answering |
| `/hafiz:handoff [note]` | Show this branch's handoff note, or record where you stopped and the next step |
| `/hafiz:summary [opus] [session] [lang] [path]` | A detailed session record naming the **issue and branch**, written by **Sonnet** (or Opus on request) |
| `/hafiz:memory` | Remember by hand, list, forget (never captured again), status |

## The detailed summary

The only place hafiz uses a model, and only when you ask. It runs your own `claude -p` with
**Sonnet** by default (`--model opus` for the most careful write-up, `haiku` for the cheapest),
so your main conversation does not pay for it. It finds the issue from the branch name
(`feat/123-login`), then the branch's commit messages (`fixes #123`), then the pull request
linked to the branch (`gh`). Sections: issue and branch, goal, what was done, decisions,
problems and fixes, files, commits and links, still open. Saved in the data folder, and with
`--out` also in your repo.

The model only writes text: it runs with no tools, no MCP servers and none of the project's
settings, in an empty folder, and the session log is passed as data it must not take orders from.

## The helper

The session card prints its path. `hafiz recall "argon2"`, `hafiz list --type decision`,
`hafiz remember decision "..." --project`, `hafiz forget m1a2b3c4 --dry-run`, `hafiz handoff`,
`hafiz summary --dry-run` (see what would be sent, call nothing), `hafiz export --json`,
`hafiz status`.

## Working with the other Nexika plugins

mizan asks hafiz to save the handoff as the context fills (every few replies at mid, and before it
offers `/clear` at full) with `hafiz handoff --save --session <id> --transcript <path>`, which reads
only a session transcript under `~/.claude/projects`.

hafiz publishes one stable contract, schema `nexika.hafiz/1`:

- `hafiz export --json`: the latest session, newest memories by type, counts.
- `~/.claude/nexika/hafiz/<project>/latest-session.json`: the latest session, refreshed after
  every reply, for plugins that read files instead of running commands.

```json
{"schema": "nexika.hafiz/1", "branch": "feat/12-login", "issue": "12",
 "latest_session": {"id": "...", "goal": "...", "note": "...", "open_tasks": [], "decisions": [],
                    "open_problems": [], "files": [], "commits": [], "links": [], "handoff": "..."},
 "memories": {"decision": [], "task": [], "problem": [], "file": [], "link": []}}
```

Readers ignore fields they do not know; new fields are only ever added within `/1`. All text
is already redacted.

| Plugin | What it can take from hafiz |
|---|---|
| prof | decisions and solved problems of the session as material for the end-of-session learning report |
| barq | `files` in play, to read them in one batched call when work resumes |
| siyaq | project-wide decisions worth turning into knowledge entries (`/siyaq:add`) |
| itqan | open problems (failing tests) and approved plans, before review or shipping |
| amin | issue, branch, pull request and commits, for pull request descriptions and release notes |
| bayan | the summary and handoff text, written for the reader's level and language |

**Shared startup budget:** each Nexika plugin keeps its start note small. hafiz's card stays
under 1.5 KB (`card_chars` in `.hafiz.json` can only make it smaller).

## Configuration: `.hafiz.json` (optional, in the repo root)

```json
{"mode": "on", "card_chars": 1200}
```

`"mode": "off"` or `HAFIZ=off` turns hafiz off; `HAFIZ_HOME` moves the data folder.

## Limits
- Capture follows rules, so a decision stated in unusual words can be missed: save it with
  `/hafiz:memory`. The summary, written by a model, sees the whole session.
- Search matches words and stems (Arabic and English), not meaning; search with synonyms or in
  both languages.
- Memories describe the past. Claude is told to check them against the code before acting.
- The transcript format of Claude Code is not a public API; hafiz skips what it does not
  recognize rather than failing.
