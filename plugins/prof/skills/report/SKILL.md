---
name: report
description: Write the end-of-session learning report - what the learner learned today, exactly what they did, comprehension check results, weak areas and logic gaps, level estimate, and what to review next time - then update the per-topic memory. Use when a tutoring session (a prof lesson, quiz, warm-up, walkthrough or onboarding ran in this session) ends, or when the user says "what did I learn" or runs /prof:report. A goodbye at the end of an ordinary working session is not a reason to run it.
argument-hint: "[optional note]"
---

# End-of-session report

## 1. Build the report from THIS session only

Use the whole conversation: lessons, warm-up results, quiz answers, exercises, code the learner
wrote, questions they asked, and every place they hesitated or reasoned wrongly.

Be honest and specific:
- "What you learned today" = concepts actually covered, each in one line at their level.
- "What you did" = exact chronological summary (files created/edited, exercises, quizzes).
- "Weak areas & logic gaps" = concrete evidence: quote or paraphrase the wrong answer or the
  broken reasoning step, and name the underlying misconception ("thinks `await` blocks the
  thread"). Include logic gaps that aren't about the topic itself (off-by-one thinking, not
  considering null/empty input, confusing cause and effect). If none, say so - never invent.
- Concept checklist: one line per concept taught or checked today, with a status:
  `understood` (answered/applied correctly), `shaky` (partly right, needed hints),
  `missed` (wrong / couldn't answer), `not-checked` (explained but never tested).
  The topic-slug names the BROAD subject (`csharp-async`), never a single concept. Before
  writing, list `~/.claude/nexika/prof/topics/` and reuse an existing slug and the exact existing
  concept names (`python3 <helper> topic <slug>`), so history stays in one place.
  Concept names are short (2-6 words).

## 2. Save it

1. Get the file name: `date +%F_%H%M` and the short session id from the "Prof plugin" session
   context → `~/.claude/nexika/prof/reports/<date>_<HHMM>_<sid8>.md`.
   The `<sid8>` suffix matters: it tells the SessionEnd hook this session already has a
   report, so no duplicate is generated.
2. Write the file with exactly this structure:

```markdown
# Tutor session report - YYYY-MM-DD
Session: <sid8> · Source: in-session

## What you learned today
- concept: one-line explanation

## What you did
- step by step

## Comprehension checks
| Question | Learner's answer (short) | Verdict |
|---|---|---|

## Weak areas & logic gaps
- misconception - evidence

## Level estimate
- topic: beginner | junior | intermediate - why

## Review next time
- most important first

## Concept checklist
- [status] topic-slug :: Topic Title :: concept :: evidence
```

3. Merge it into the topic memory:
   `python3 <helper> merge-report <report file>` (helper path is in the session context).
4. Update the profile with the `progress` skill (log line + move mastered/weak topics).

## 3. Show the learner

Print a short version: what you learned (3-5 bullets), your weak spots, your level, and what
the next session will start with. Encourage them with one specific thing they did well.
