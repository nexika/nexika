---
name: audit
description: Review haris's audit log - every ask, refusal, approval, prompt-injection warning and ask let pass in an unattended session with time, tool, class and the redacted command - for this project or all projects. Use when the user asks "what did haris block this week", "show the haris log", "audit", "سجل haris".
argument-hint: "[--days N] [--decision ask|deny|taint|approval|unattended] [--all]"
---

# haris audit log

1. Run `<haris> audit --days 7` (the helper path is in the session note), or with the options
   in $ARGUMENTS; add `--json` when you need to count or group.
2. Summarize: how many refusals and asks, the most common classes, anything unusual (the same
   refusal again and again, a prompt-injection warning followed by attempts to send data out).
   Entries with decision `unattended` are asks that passed without a question because nobody
   attended the session (`claude -p`, CI, a background session); list them separately, with the
   reason in their `unattended` field. A refusal with that field was an ask refused for the same
   reason.
3. Point out patterns worth acting on: a rule worth adding to `.haris.json` (`"ask"` or
   `"deny"` command prefixes), an exact approval the user may want with `/haris:allow
   --project`, or a workflow that keeps hitting the same wall.

The log lives in `~/.claude/nexika/haris/audit.jsonl`, owner-only, with secrets in commands
already replaced by `[secret]`. Do not try to edit or delete it; haris refuses that.
