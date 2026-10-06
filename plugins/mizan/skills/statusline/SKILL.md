---
name: statusline
description: Set up mizan's status line for Claude Code hosts that do not load mods - the same two lines as the band (branch, PRs, CI, RAM, disk, context, cost, task step) printed by Python. Use when the user says "mizan status line", "the band does not show", "set up mizan", "شريط الحالة".
---

# mizan status line

The band above the prompt is a mod; a host without the mod engine can show the same two lines
in Claude Code's status line instead.

1. Find the helper path in the session note ("Helper: python3 .../bin/mizan").
2. Show the user this block for their `~/.claude/settings.json`, with the real path:

   ```json
   {
     "statusLine": { "type": "command", "command": "python3 /path/to/mizan/bin/mizan statusline" }
   }
   ```

3. They add it themselves (haris does not let Claude change Claude Code settings), then restart
   Claude Code. If a `statusLine` is already set, say so and let them choose.
4. With the status line, mizan also follows the context: at mid it refreshes the hafiz handoff, at
   full it saves it and tells the user to type `/clear` (it cannot fill the prompt without the mod).
