---
name: walkthrough
description: Explain a specific file, function, class or code snippet line by line for a learner, then check understanding. Use when the user asks to learn from the code - "walk me through this line by line", "teach me how this file works", "I'm learning, explain this slowly" - or runs /prof:walkthrough. Not for a quick "what does this do" while working: answer that directly.
argument-hint: "<file path, symbol name, or pasted code>"
---

# Code walkthrough

Target: $ARGUMENTS

1. **Read** the target and just enough of its callers/callees to know where it fits.
2. **Purpose first:** one sentence - what this code is for and who calls it (`path:line`).
3. **Split into blocks** of a few lines. For each block: what it does, why it is written this
   way, and any language feature a junior might not know (explain that feature briefly).
4. **Trace an example:** run one concrete input through the code by hand, showing the values
   step by step in a small table.
5. **Spot the lessons:** patterns used, possible bugs or smells, and how a senior might improve
   it - framed as learning points, not as changes to make.
6. **Check:** ask 2 questions (e.g. "what happens if the list is empty?"). Wait, then correct.
7. Offer to go deeper on any concept that came up (hand off to the `learn` skill).
