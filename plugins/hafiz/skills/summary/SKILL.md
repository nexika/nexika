---
name: summary
description: Write a detailed summary of a work session that names the issue and the branch - goal, what was done and why, decisions, problems and fixes, files, commits, links and what is still open - using Sonnet by default (or Opus on request) to keep the cost low. Use when the user asks for a "detailed summary", "session report", "write up this session", "ملخص مفصل", "تقرير الجلسة", or wants a record to share with the team or attach to a pull request.
argument-hint: "[opus] [session id] [ar|en] [save path]"
---

# Detailed session summary

Request: $ARGUMENTS

This is the only part of hafiz that uses a model, and only when asked. It runs your own
`claude -p` in the background with **Sonnet** by default; the main conversation does not
spend its own tokens on it.

1. **Pick the options** from the request:
   - model: `--model opus` only if the user asked for Opus (or "best quality"); otherwise leave
     the default (Sonnet). `haiku` is allowed when the user asks for the cheapest.
   - session: `--session <first characters of the id>` for an earlier session; default is
     the latest one in this project.
   - language: `--lang Arabic` or `--lang English` if asked; default follows the user's prompts.
   - save a copy: `--out <path>` if the user wants it in the repo (e.g. `docs/sessions/...md`).
2. **Run** the hafiz helper from the session note, with a long timeout (up to 10 minutes):
   `<hafiz> summary [options]`. It finds the issue from the branch name, the branch's commit
   messages and the linked pull request (`gh`), redacts secrets and `<private>` text, and
   saves the summary in hafiz's data folder (path printed at the end).
3. **Show** the summary title, the issue and branch it names, and where it was saved. Do not
   paste the whole text back unless the user asks.
4. **If it fails** (no `claude` command, timeout), the helper saves the redacted material and
   prints its path. Tell the user, and ask before writing the summary yourself from that file,
   since doing it in this conversation uses the current, possibly more expensive, model.
5. To check what would be sent without calling anything: `<hafiz> summary --dry-run`.
