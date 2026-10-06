---
name: status
description: Show how haris is protecting this project - profile (relaxed, standard, strict), mode (on or watch), settings and extra rules, whether the session is marked after a prompt-injection warning, approvals, and counts of the last week's asks and refusals. Use when the user asks "is haris on", "what does haris protect", "haris settings", "حالة haris".
---

# haris status

1. Run `<haris> status` (the helper path is in the session note).
2. Summarize in a few lines, in the user's language:
   - mode and profile, and what the profile means: **relaxed** approves project writes and
     only asks about clearly risky actions; **standard** (default) approves reads and project
     runs, leaves project edits to Claude Code's own rules, and asks or refuses for the rest;
     **strict** also asks before deleting in the project and refuses secret reads.
   - where the settings come from (`~/.claude/nexika/haris/config.json` can loosen or tighten;
     the repo's `.haris.json` can only tighten);
   - a session marked after text that tried to give orders, and for how many more messages;
   - approvals the user typed;
   - last week's counts, with `/haris:why` and `/haris:audit` for details.
3. To change settings, show the user the file and the keys (`profile`, `mode`, `ask`, `deny`,
   `allow`, `protected_branches`, `secret_paths`, `taint_turns`); they edit it themselves, since
   haris refuses changes to its own files from Claude.
