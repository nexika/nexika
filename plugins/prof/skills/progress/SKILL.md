---
name: progress
description: Show or update the learner's profile and learning progress stored in ~/.claude/nexika/prof/profile.md. Use after a lesson, quiz or onboarding session, or when the user says "my progress", "what have I learned", "set my level", or "what should I learn next".
argument-hint: "[show | update | reset]"
---

# Learner progress

Profile file: `~/.claude/nexika/prof/profile.md` (create the folder and file if missing).

## Format

```markdown
# Learner profile
- Level: beginner | junior | intermediate
- Main languages: C#, ...
- Goals: ...

## Mastered
- topic - YYYY-MM-DD

## Learning
- topic - YYYY-MM-DD - what is still shaky

## Weak spots
- ...

## Projects
- project name - areas understood - open questions

## Log
- YYYY-MM-DD - what was done (lesson / quiz score / onboarding step)
```

## Actions

- **show** (default): summarize level, recent log, weak spots, and recommend the next 3 topics.
  Also use the per-topic concept lists (`~/.claude/nexika/prof/topics/*.md`, or
  `python3 <helper> topic <slug>`) and the latest reports in `~/.claude/nexika/prof/reports/`.
- **update**: after a lesson/quiz/onboarding, edit the file - move topics between sections based
  on evidence (quiz score 4/5+ or a correct exercise → Mastered), add a log line with today's
  date. Keep the file under ~150 lines by trimming the oldest log entries.
- **reset**: only after the learner confirms, clear the file to the empty template.

Ask the learner for level and goals the first time, instead of guessing.
