---
name: slim
description: Shrink CLAUDE.md (loaded into every session) by moving situational sections into siyaq entries that load only when relevant, keeping always-needed rules in place. Measures the context saved. Use when the user says "slim CLAUDE.md", "CLAUDE.md is too long", "reduce context", or "siyaq slim".
---

# Slim CLAUDE.md

CLAUDE.md costs context in every session. Knowledge that only matters for some tasks belongs
in siyaq entries, which load on demand.

1. Read `CLAUDE.md` (and `.claude/CLAUDE.md` if present). Measure it: characters / 4 ≈ tokens.
2. Classify each section:
   - **keep**: applies to almost every task (build/test commands, branch and commit rules,
     non-negotiable safety rules, how to run the project);
   - **move**: situational (how subsystem X works, deployment, a migration guide, a vendor
     integration, troubleshooting a specific error).
3. Show the plan as a table: section | keep/move | why | approx tokens. **Ask for approval.**
4. For each approved "move": create `.siyaq/entries/<slug>.md` (same format as `/siyaq:add`)
   with good `keywords` (including the team's languages) and `paths` for the files it is about.
   Copy the text faithfully; don't rewrite meaning.
5. Remove the moved sections from CLAUDE.md and add one line where they were:
   `Situational knowledge (deployment, <topics>) loads on demand via siyaq (.siyaq/entries/).`
6. Verify with `siyaq match "<a question for each moved topic>"` that each entry matches.
7. Report: tokens before → after for CLAUDE.md, entries created, files to commit.
