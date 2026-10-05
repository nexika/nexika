---
name: quiz
description: Quiz the learner on a topic or on a project they are learning, one question at a time, with feedback and a score. Use when the user says "quiz me", "test me", "check my understanding", or "am I ready".
argument-hint: "[topic or project area]"
---

# Quiz

Topic: $ARGUMENTS (if empty, use the open items and recent topics in the "Prof plugin"
session context; `python3 <helper> topic <slug>` lists a topic's concepts and statuses).

1. Make 5 questions, easy → hard, mixed types: multiple choice, "predict the output",
   "find the bug", and "explain in your own words". For a project, base them on its real code.
2. Ask **one question at a time** and wait for the answer.
3. After each answer: correct or not, why, and the key idea in one line. Never reveal the next
   question's answer.
4. At the end: score, strong areas, weak areas, and 1-2 topics to review next.
5. Keep each question's verdict for the session report (`report` skill): it becomes a row in
   "Comprehension checks" and updates the concept's status.
