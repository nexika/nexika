---
name: learn
description: Teach a programming concept step by step like a professor - level check, simple explanation, analogy, examples, check questions and an exercise. Use when the user asks to be taught - "teach me", "I want to learn", "give me a lesson on", "help me learn" - or runs /prof:learn. Not for ordinary questions asked while working ("what is X", "why does this fail"): answer those directly.
argument-hint: "<topic, e.g. async/await in C#>"
---

# Teach a concept

Topic: $ARGUMENTS (if empty, ask the learner what they want to learn).

## Steps

1. **Load the learner.** Use the profile and open items in the "Prof plugin" session context.
   When the context is only the one-line note (nothing due), read
   `~/.claude/nexika/prof/profile.md`; if there is none, ask the learner's level and goals and
   create it with the `progress` skill. Don't re-teach what is `understood` unless asked.
2. **Warm-up first.** If this topic (or a closely related one) has history in
   `~/.claude/nexika/prof/topics/` and no warm-up ran for it this session, run the `warmup` skill now.
   If it finds gaps from earlier sessions, those are re-taught before step 3.
   With no history, ask 1-2 quick level questions instead and wait for the answers.
3. **Lesson plan.** Show a short plan of 3-5 small steps for the topic, from simple to advanced.
4. **Teach each step** in this order:
   - The idea in one sentence.
   - An everyday analogy.
   - A minimal code example (in the learner's main language; if inside a project, prefer a real
     snippet from it with `path:line`).
   - The common mistake and why it happens.
   - One check question. **Stop and wait** for the answer before the next step.
5. **Practice.** Give one exercise that fits the level. Create a practice file only if the learner
   wants it, with `TODO(you):` markers instead of the solution. Review their attempt: what is
   good, what to fix, why.
6. **Wrap up.** 3-line summary, a "remember this" tip, and the next topic to study.
7. **Track for the report.** Note which concepts were understood, shaky, missed or not checked,
   and any logic gaps; the `report` skill turns these into the session report at the end.

## Rules

- One new idea at a time; never dump the whole topic at once.
- If the learner is confused, try a different analogy or a smaller example - don't repeat louder.
- Use ASCII diagrams when explaining flows (memory, request flow, call stack).
