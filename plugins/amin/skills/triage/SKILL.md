---
name: triage
description: Triage the GitHub issue tracker - find issues without labels, likely duplicates and stale issues, propose labels and actions with reasons, and apply only what the user approves. Never closes issues. Use when the user says "triage", "sort the issues", "label the issues", "find duplicates", or "amin triage".
---

# Triage issues

The amin helper is printed in the session note; below it is written `amin`.

1. Run `amin triage`. It lists open issues without labels, possible duplicate pairs (by
   title), and issues with no activity for 90+ days, plus the labels the repo already has.
2. For each unlabeled issue, read it (`gh issue view N`) and propose labels **only from the
   existing vocabulary** (suggest a new label separately, never invent one silently), with a
   one-line reason. Use priority labels only if the repo has them.
3. For each possible duplicate pair, read both and decide: duplicate, related, or different.
   Title similarity alone proves nothing.
4. For stale issues, suggest: ask the author for an update, or leave as is.
5. Present one table: issue | proposal | reason. Ask the user what to apply (all, some, none).
6. Apply only the approved items:
   - labels: `gh issue edit N --add-label "x"`
   - duplicates: comment `Possible duplicate of #M` (`gh issue comment N --body ...`)
   - stale: comment asking for an update
   **Never close or lock an issue, and never delete labels**: the user does that.
7. Summarize what was applied.
