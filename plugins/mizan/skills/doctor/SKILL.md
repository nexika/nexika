---
name: doctor
description: Check how the Nexika plugins installed here work together - which are installed and enabled, the hooks each adds and how long each takes, known conflicts (bayan with Claude Code's signature line on, itqan without haris) and stale or unsafe status files. Use when the user asks "nexika doctor", "mizan doctor", "are my plugins OK", "why is every commit stopped", "plugins conflict", "is something slowing my session", "فحص الإضافات", "هل الإضافات تعمل معًا".
---

# mizan doctor

1. Run `<mizan> doctor` (the helper path is in the session note: "Helper: python3 .../bin/mizan").
   It runs each plugin's command hooks once with a dummy event in a throwaway home and empty folder,
   so it touches no data and no project; `--no-latency` skips that. `--json` gives schema
   `nexika.doctor/1`.
2. Answer in the user's language, in a few plain lines. Lead with the problems:
   - **bayan with the signature line on:** offer to set `"attribution": {"commit": "", "pr": ""}`
     in the settings file the user chooses; never change settings without asking.
   - **itqan without haris:** suggest installing or enabling haris for the full guard.
   - **A slow, failing or timed-out hook:** name the plugin and the event.
   - **A status file stale, of an unknown schema or readable by others:** say which; a stale file
     only means that plugin has not run lately.
   - **The family settings file readable by others:** suggest `chmod 600` on the path shown.
   Then mention the family settings (role, background calls) only if the user asked about them or
   the role is not chosen.
3. If nothing is wrong, say so in one line and list the plugins found.
