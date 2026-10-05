---
name: learn
description: Review the project rules itqan learned from the user's repeated corrections and let the user approve, reword or reject each one. Approved rules are written to .itqan/rules.md and loaded every session. Use when the user says "learn", "what have you learned", "rules", "stop making that mistake", or when the session note says proposals are waiting.
argument-hint: "[approve ID | reject ID | rules]"
---

# Learned rules

The helper command is printed in the itqan session note ("itqan helper: python3
.../itqan_learn.py"). Run it from the project directory; below it is written `itqan_learn.py`.

## With arguments
- `approve ID` / `reject ID` / `rules`: run that helper command and show the result.

## Without arguments
1. Run `itqan_learn.py proposals`. Each proposal comes from at least two corrections; the
   evidence lines are the user's own words.
2. If there are none, say so and how many lessons are being watched (seen once). Stop.
3. Show each proposal as: the rule, why (the quoted corrections), and your one-line opinion:
   is it really a general rule for this project, or was it about one task?
4. Ask the user, for each: **approve**, **reword** (they give the new text), or **reject**.
5. Run `approve ID` (with the new text when reworded) or `reject ID` for each answer.
6. Tell the user the rules are in `.itqan/rules.md` and should be committed so the team and
   future sessions share them.

Never approve a rule the user did not explicitly accept.
