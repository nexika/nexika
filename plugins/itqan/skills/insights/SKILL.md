---
name: insights
description: Show what actually helps in this project - which workflows, agents and skills (from any plugin) were used, what the guard stopped, how many corrections were captured, and whether each approved rule is working or keeps being broken. Use when the user asks "is this helping", "what do I use", "which skills are useless", "insights", or "stats".
argument-hint: "[days, default 30]"
---

# Insights

1. Run the itqan helper printed in the session note ("itqan helper: python3 .../itqan_learn.py")
   with `insights $ARGUMENTS`, from the project directory.
2. Show the report, then add at most three short, concrete recommendations, for example:
   - a rule "corrected again since approval" → propose clearer wording (then `/itqan:learn`);
   - proposals waiting → suggest `/itqan:learn`;
   - an installed plugin whose skills were never used → it costs context every session and may
     be worth disabling;
   - many guard refusals of the same kind → a workflow habit worth changing.
3. If barq is installed, `barq stats:month` adds token savings; include it if the user wants
   the full picture.

Don't invent numbers: only interpret what the report shows.
