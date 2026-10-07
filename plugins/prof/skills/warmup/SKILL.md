---
name: warmup
description: Start-of-session comprehension check. Tests what the learner kept from previous sessions on a topic, estimates their current level, and re-teaches anything missed BEFORE new material. Use at the start of a tutoring session, before any new lesson on a topic that has history, or when the user says "check what I remember", "where was I in my lessons", or "test my level".
argument-hint: "[topic or topic-slug, optional]"
---

# Warm-up: check before moving on

Topic: $ARGUMENTS (if empty: the topic the learner is about to study; if unknown, the most
recent topic with open items in the session context, and ask the learner to confirm).

## 1. Gather the history

- Run `python3 <helper> topic <topic-slug>` (the helper path is in the "Prof plugin" session
  context) to list every concept taught on this topic with its status:
  `missed`, `shaky`, `not-checked`, `understood`.
- Read the most recent report in `~/.claude/nexika/prof/reports/` that covers this topic
  (grep for the slug) - especially "Weak areas & logic gaps" and "Review next time".
- If there is no history, say this is the first session on the topic, ask 2 quick level
  questions instead, and skip to step 4.

## 2. Ask the check questions (one at a time, wait for each answer)

Pick 3-5 questions, in this priority:
1. every `missed` concept,
2. `shaky` concepts and the logic gaps named in the last report,
3. `not-checked` concepts (explained but never tested),
4. 1 retention question on an `understood` concept older than 2 weeks,
5. 1 slightly harder "stretch" question to find the ceiling of their level.

Mix question types: explain in your own words, predict the output, find the bug, "what would
happen if". Test **reasoning**, not memorized words: ask a follow-up "why?" when an answer is
right but might be a lucky guess.

Do NOT explain between questions; only say "noted" and move on. Feedback comes in step 3.

## 3. Verdict

Show a small table: concept | previous status | today | why. Then:
- **Level now:** beginner | junior | intermediate for this topic, with one line of evidence.
- **Gaps found:** list them.

## 4. Fix gaps first (mandatory)

If anything was missed or shaky: tell the learner "before we continue, let's fix these" and
re-teach each gap with a NEW angle (different analogy, smaller example, or their own code), then
ask one confirmation question per gap. Only when the gaps are confirmed, or the learner
explicitly asks to move on, continue to the new material they requested.

## 5. Record

Keep the warm-up results for the end-of-session report (prof:report puts them in
"Comprehension checks" and the concept checklist). Don't write files here.
