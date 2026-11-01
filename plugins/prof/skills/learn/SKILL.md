---
name: learn
description: Teach a programming concept step by step, with checks and an exercise. Use when the user says "teach me", "I want to learn", "give me a lesson on". Not for "what is X" while working.
argument-hint: "<topic, e.g. async/await in C#>"
---

# Teach a concept

Topic: $ARGUMENTS (if empty, ask the learner what they want to learn).

## Steps

1. **Load the learner.** Use the profile and open items in the "Prof plugin" session context.
   When there is no such context, or only the one-line note (nothing due), read
   `~/.claude/nexika/prof/profile.md`; if there is none, ask the learner's level and goals and
   create it with the `progress` skill. Don't re-teach what is `understood` unless asked.
2. **Warm-up first.** If this topic (or a closely related one) has history in
   `~/.claude/nexika/prof/topics/` and no warm-up ran for it this session, run the `warmup` skill now.
   If it finds gaps from earlier sessions, those are re-taught before step 3.
   With no history, ask 1-2 quick level questions instead and wait for the answers.
3. **Look for a reviewed course lesson.** Run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prof_courses.py find "<topic>" --lang <en|ar|fr>` in the
   learner's language (any other language: `en`). The first time it downloads Nexika's courses, which takes
   a few seconds. If it prints "teach as usual", go on with step 4. If it lists lessons:
   - Pick the one that fits the topic and the learner's level. If the learner hasn't covered a lesson in
     its "comes after" line, say so and offer that one first.
   - Tell the learner in one line that this lesson comes from Nexika's courses, its status (reviewed:
     two fact checks and a teaching review; verified: learners passed it too) and about how long it takes.
   - Teach from the lesson's text file instead of steps 4 and 5: read it and go through its sections in
     order, one at a time, keeping its examples and facts. Don't add facts the lesson doesn't make. If the
     learner asks something beyond it, say that this part is not from the reviewed lesson. When the
     learner asks where a fact comes from, give the source from `sources.json`.
   - For the check questions, use the questions in `quiz.json`, in the learner's language, one at a time.
     Their `answer` and `explain` fields give the feedback.
   - For practice, use the lesson's exercise. `exercise.json` has the goal and the runner. If the learner
     wants to do it, copy `starter/` and `tests/` into a folder they choose (by default
     `prof-practice/<lesson-id>/` in the current project), never `solution/`. Run the tests the runner
     names (`python-unittest`: `python3 -m unittest discover -s tests`). Open `solution/` only to compare
     after the learner passes, or when they ask for it.
   - Then go on with steps 7 and 8. In the report, name the lesson id.
4. **Lesson plan.** Show a short plan of 3-5 small steps for the topic, from simple to advanced.
5. **Teach each step** in this order:
   - The idea in one sentence.
   - An everyday analogy.
   - A minimal code example (in the learner's main language; if inside a project, prefer a real
     snippet from it with `path:line`).
   - The common mistake and why it happens.
   - One check question. **Stop and wait** for the answer before the next step.
6. **Practice.** Give one exercise that fits the level. Create a practice file only if the learner
   wants it, with `TODO(you):` markers instead of the solution. Review their attempt: what is
   good, what to fix, why.
7. **Wrap up.** 3-line summary, a "remember this" tip, and the next topic to study.
8. **Track for the report.** Note which concepts were understood, shaky, missed or not checked,
   and any logic gaps; the `report` skill turns these into the session report at the end.

## Rules

- One new idea at a time; never dump the whole topic at once.
- If the learner is confused, try a different analogy or a smaller example - don't repeat louder.
- Use ASCII diagrams when explaining flows (memory, request flow, call stack).
