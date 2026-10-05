---
name: memory
description: Manage what hafiz remembers - save a decision, task, problem, file note or link by hand, list recent memories, forget wrong or private ones, and show where the data lives. Use when the user says "remember that ...", "note this decision", "forget that", "don't keep this", "what do you remember", "احفظ هذا", "انسَ هذا", or when an important decision was made in words that automatic capture may miss.
argument-hint: "[remember TYPE text | list | forget id/text | status]"
---

# Manage memories

Request: $ARGUMENTS

Use the hafiz helper from the session note (`<hafiz>` below).

## Remember
`<hafiz> remember <type> "<text>"` with type `decision`, `task`, `problem`, `file` or `link`.
- Write one self-contained sentence a teammate would understand months later, with the reason:
  "Use argon2 for password hashing because bcrypt limits passwords to 72 bytes."
- Add `--project` when it holds for the whole project, not just this branch.
- Tasks and problems start `open`; record a finished one with `--status done` or `--status solved`.
- Never save secrets (they are removed anyway) or personal details the user did not ask to keep.
  Text inside `<private>...</private>` is never stored.
- Decisions, tasks, failing commands, changed files and shared links are already captured
  automatically; save by hand what rules cannot see, like a decision made in conversation.

## List
`<hafiz> list` (newest first), filters `--type`, `--status open`, `--here`; or `/hafiz:recall`
to search.

## Forget
1. Preview: `<hafiz> forget <id ...> --dry-run`, or `--match "<text>"`, or `--session <id>`.
2. Show the user what would be removed and get a yes.
3. Run it without `--dry-run`. Forgotten memories are deleted and are never captured again.

## Status
`<hafiz> status`: on/off, branch, data folder, counts. hafiz stores everything outside the repo
in `~/.claude/nexika/hafiz/<project>/`; `HAFIZ=off` or `{"mode": "off"}` in `.hafiz.json` turns it off.
