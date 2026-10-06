# lawha (لوحة, "board"): design v0.1

A local, read-only learner dashboard for prof. It shows what prof knows about you: what to review today, your topics and how well you know each concept, your session reports, and the course you follow. It is the first of three pieces that share one data core. The other two come later: an MCP server, then a chat tutor on Telegram (and maybe WhatsApp).

Status: **approved 2026-10-06** (name lawha, demo switch yes, local courses clone).

## Goals and non-goals

**Goals (v0.1):**
- One command, `/lawha`, opens an attractive dashboard in the browser, in English, Arabic (right to left) and French.
- Everything stays on the learner's machine. The server listens on `127.0.0.1` only.
- Read-only. lawha never writes to prof's files, so prof keeps working with or without it.
- Learners need nothing beyond Python 3.10+ and a browser. Node is needed only to develop the frontend.

**Not in v0.1:** the MCP server, phone access, the chat tutor, search by meaning (RAG), writing progress, and accounts.

## Data: what lawha reads

prof keeps its data in `~/.claude/nexika/prof/` (or `$PROF_HOME`):

| File | Format | lawha uses |
|---|---|---|
| `profile.md` | free markdown | Profile screen |
| `topics/SLUG.md` | `# Title`, then `- [status] concept — evidence (YYYY-MM-DD)` | Topics, Today |
| `reports/YYYY-MM-DD_HHMM_SID8.md` | fixed headings (What you learned today, What you did, Comprehension checks, Weak areas & logic gaps, Level estimate, Review next time, Concept checklist) | Sessions |

Statuses, worst first: `missed`, `shaky`, `not-checked`, `understood`. An `understood` concept is
**stale** after 14 days, matching prof's own rule.

The course comes from a local clone of nexika/courses, whose path is set by `LAWHA_COURSES` (default `~/nexika-courses`). If the clone is missing, the Course screen says so and links to the repo.

**Change from what we discussed:** v0.1 reads the files directly on each request, with no SQLite index. prof's data is small (tens of files), so a cache would add sync bugs and give no speed. SQLite with sqlite-vec arrives when search by meaning does, together with the MCP server and chat tutor.

**Parsing:** lawha cannot import prof's code, because plugins install separately. It therefore has its own small parser, and a test pins it to prof's real formats: the test reads prof_store.py's `REPORT_FORMAT` and line regexes from this repo, so a format change in prof fails lawha's test.

## API (JSON, GET only)

Every request needs the session token (see Security).

```
GET /api/summary
  { "today": { "review": [Concept], "counts": {"missed":n,"shaky":n,"not-checked":n,"understood":n,"stale":n} },
    "topics": n, "sessions": n, "last_session": "YYYY-MM-DD" | null, "has_data": bool }

GET /api/topics
  [ { "slug", "title", "last": "YYYY-MM-DD", "counts": {…}, "mastery": 0.0-1.0 } ]   most recent first

GET /api/topics/{slug}
  { "slug", "title", "concepts": [Concept] }                                        worst first

GET /api/sessions
  [ { "id": "2026-10-06_1430_ab12cd34", "date", "time", "learned": [str], "review_next": [str] } ]

GET /api/sessions/{id}
  { "id", "date", "time", "sections": { "learned": [str], "did": [str], "checks": [{q, answer, verdict}],
    "weak": [str], "levels": [str], "review_next": [str], "checklist": [Concept] } }

GET /api/profile
  { "markdown": str | null }

GET /api/course
  { "available": bool, "course": {id, title{en,ar,fr}}, "modules": [ {id, level, title{…},
    "lessons": [ {id, title{…}, minutes, status} ] } ] }

Concept = { "topic", "concept", "status", "evidence", "date", "stale": bool }
```

**Mastery** is the share of a topic's concepts that are `understood` and not stale. It is a simple fraction, labelled as such in the UI and never called a score.

**Lesson status** (planned, draft, checked, reviewed, verified) comes from `courses status --json`, which the courses tool already has. It runs once per server start; the tool runs no lesson code for `status`.

## Screens

```
┌────────────────────────────────────────────────────────────┐
│ لوحة lawha      Today  Topics  Course  Sessions  Profile  EN│AR│FR │
├────────────────────────────────────────────────────────────┤
│ Today                                                      │
│  ┌ 3 missed ┐ ┌ 2 shaky ┐ ┌ 4 to refresh ┐  (cards count up)│
│  Review now                                                │
│   ● missed  csharp-async · await in loops   "said it blocks"│
│   ● shaky   git · rebase vs merge           "needed a hint" │
│   ○ stale   python · list comprehensions    last 2026-09-12 │
│  Next: run /prof:warmup to start with these                │
└────────────────────────────────────────────────────────────┘
```

- **Today:** counts, then the review list (missed, shaky, stale), each with its evidence, and a hint to run prof's warm-up.
- **Topics:** a grid of cards, each with a title, a mastery bar, the counts and the last-seen date. Opening one lists its concepts grouped by status, with evidence and dates.
- **Course:** modules and lessons in order, with minutes and status badges. Each lesson links to its file on GitHub.
- **Sessions:** a timeline, newest first. Opening a report shows its sections, with the comprehension checks as a table.
- **Profile:** prof's profile, rendered as markdown.
- **Empty state:** with no prof data yet, each screen says how to start (`/prof:learn`). A "show demo" switch loads built-in sample data, clearly labelled as a demo.

**Motion:** page transitions; cards that stagger in; mastery bars that fill; counts that tick up; the timeline revealing on scroll. All of it is off when the system asks for reduced motion.

**Look:** a calm, readable palette with light and dark themes, and status colours that also differ in shape and label, so colour is never the only signal. Arabic uses a proper Arabic font (IBM Plex Sans Arabic). Layout is right to left, with logical CSS properties throughout.

## Stack

- **Frontend:** Vite, React 19, TypeScript, Tailwind CSS 4, shadcn/ui components, Motion, react-router, and a small i18n layer with `en.json`, `ar.json` and `fr.json`.
- **Build:** `web/dist/` is built and committed, so learners never run Node. CI rebuilds it and fails if the committed `dist` differs from the source.
- **Server:** Python stdlib (`http.server` plus `json`), no dependencies, the same as every other Nexika plugin script. It serves `web/dist` and `/api/*`.

## Security

- The server binds to `127.0.0.1` only, on a random free port.
- **A random token is generated per run.** `/lawha` opens `http://127.0.0.1:PORT/#t=TOKEN`. The token is in the URL fragment, so the browser never sends it over the network or in a referrer. The page keeps the token in memory and sends it as a header; requests without it get 403. Other local programs and websites therefore cannot read the data.
- **The `Host` header must be `127.0.0.1:PORT`.** This blocks DNS-rebinding attacks.
- The server sends no CORS headers, so other origins get nothing.
- **Read-only.** There are no write routes, and paths are resolved inside prof's folder only, so a slug like `../x` is refused.
- The server stops when `/lawha stop` runs or after 2 hours idle. Its port and pid are in `~/.claude/nexika/lawha/server.json`, and the file is removed on exit.

## Files

```
plugins/lawha/
  .claude-plugin/plugin.json
  skills/lawha/SKILL.md          /lawha [stop]: start or stop the server, print and open the URL
  scripts/lawha_server.py        HTTP server, token, routes (stdlib)
  scripts/lawha_data.py          read-only parsers for prof's files and the course pack
  web/                           Vite project (src/, i18n/, components/)
  web/dist/                      built frontend (committed)
  README.md  CHANGELOG.md  DESIGN.md
tests/test_lawha.py              parsers against prof's formats, API, token, Host check, path safety
```

## How it is tested

- **Parser tests** run on sample prof data (fixtures), plus the format-pinning test against prof_store.py.
- **Server tests:** each route's JSON shape; 403 without the token; a bad `Host` refused; `../` slugs refused; nothing written to prof's folder.
- **Frontend:** a type-check and build in CI. Each screen is checked by hand in all three languages, with demo data and with an empty state, at desktop and phone width.

## Open questions

1. **Name:** is lawha (لوحة) right?
2. **Demo data:** should the "show demo" switch exist? It makes the dashboard look alive before you have any prof history.
3. **Course screen:** is a local clone of nexika/courses fine for now? Later, prof would load packs itself.
