---
name: stats
description: Show how project knowledge is used - what siyaq injected, which entries were opened, which were never useful, which topics people asked about with no knowledge, and dead references in docs - with concrete recommendations. Use when the user asks "siyaq stats", "is the knowledge helping", "what docs are missing", or "clean up the docs".
argument-hint: "[days, default 30]"
---

# Knowledge stats

1. Run the siyaq helper from the session note: `siyaq stats $ARGUMENTS` (from the project).
2. Show the report, then give at most four concrete recommendations, only from what it shows:
   - **recurring topics with no knowledge** → offer `/siyaq:add` for the top one or two;
   - **never shown** entries → maybe missing keywords (check one with `siyaq match`), or obsolete;
   - **summaries shown but never opened** → the summary may be enough, or the entry is noise
     for those prompts (tighten its keywords);
   - **dead references** → the doc mentions files that no longer exist: update the doc;
   - very high token totals → lower `budget_tokens` or split large sections.
Never invent numbers.
