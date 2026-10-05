---
name: handoff
description: Show the handoff note for this branch (goal, open tasks, decisions, problems, files, commits, links) and record where the work stopped and the next step, so the next session - or a teammate - can continue without re-reading everything. Use when the user says "handoff", "where did we stop", "wrap up", "I'm done for today", "نكمل بكرة", "وين وقفنا", or at the start of a session to pick up where the last one ended.
argument-hint: "[note about where we stopped]"
---

# Handoff

hafiz writes the handoff note automatically after every reply; this skill reads it and adds
the one thing rules cannot know: where you stopped and what comes next.

1. **Read it.** Run the hafiz helper from the session note: `<hafiz> handoff`
   (another branch: `--branch <name>`).
2. **Picking up work?** Summarize the note for the user in a few lines: the goal, what is still
   open, the next step. Check open tasks and problems against the code before continuing.
3. **Wrapping up?** Write the note: 1-3 plain sentences saying where the work stopped and the
   very next concrete step (a file, a command, a decision still needed). Use $ARGUMENTS if the
   user gave it. Save it with
   `<hafiz> handoff --note "<where we stopped>. Next: <next step>."`
   Never put secrets in it. Show the user the final note.
4. If the user wants a full written record of the session for others, suggest `/hafiz:summary`.
