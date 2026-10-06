---
name: report
description: Show the session's balance as text - branch and who started it, open PRs or MRs per person, the branch's CI, RAM and disk, context level, cost, running agents, the task list and haris's state - and explain any warning. Use when the user asks "mizan", "status", "how is my session", "is CI green", "how full is the context", "كيف الجلسة", "حالة الجلسة", or when the band is not shown.
---

# mizan report

1. Run `<mizan> report` (the helper path is in the session note: "Helper: python3 .../bin/mizan").
   For the itqan proof, run `<mizan> proof`. For JSON (schema `nexika.mizan/1`), `<mizan> export --json`.
2. Answer in the user's language, in a few plain lines. Lead with what needs attention:
   - **CI failed:** name the job; offer to look at its log (`gh run view --log-failed`, or the
     link in the report).
   - **RAM or disk above 85 %:** say which, and suggest closing what is not needed; above 95 %
     the machine may stop.
   - **Context mid or full:** at mid hafiz keeps the handoff fresh; at full mizan has saved it and
     put `/clear` in the prompt for the user to send. Never run `/clear` or compact yourself.
   - **Over the daily budget:** say how much is spent today across sessions.
3. In the terminal the user sees all of this live above the prompt, and `/mizan` opens the details.
