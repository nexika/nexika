---
name: add
description: Capture a piece of project knowledge as a siyaq entry so it is loaded automatically whenever a future prompt or file touches it - a convention, a gotcha, how a subsystem works, a deployment step. Use when the user says "remember this for the project", "add this to the docs/knowledge", "siyaq add", or after explaining something non-obvious about the codebase.
argument-hint: "[topic]"
---

# Add a knowledge entry

Topic: $ARGUMENTS (if empty, use the knowledge just discussed; if unclear, ask what to capture).

0. **Pick the right home.** An instruction that applies whenever Claude works on certain files
   ("never edit generated/ by hand") belongs in `.claude/rules/<slug>.md` with `paths:` frontmatter:
   Claude Code loads it itself. Write a siyaq entry for knowledge someone would ask about.
1. **Check it isn't there already.** Run the siyaq helper from the session note:
   `siyaq match "<a question someone would ask about this>"`. If an entry already matches,
   update that file instead of adding a new one.
2. **Write the entry** as `.siyaq/entries/<short-slug>.md`:
   ```markdown
   ---
   title: Rolling back a deployment
   keywords: rollback, revert release, undo deploy, تراجع, استرجاع
   paths: deploy/**, .github/workflows/deploy.yml
   ---
   What to do, in short steps or bullets. Facts only, with file paths.
   ```
   - `title`: what a person would search for.
   - `keywords`: other words people use for it, **including the languages the team writes
     prompts in** (e.g. Arabic): matching works on words, so synonyms widen recall.
   - `paths`: globs of files where this knowledge matters (it is shown when Claude reads or
     edits them). Prefer specific folders or files.
   - Body: short and concrete, under ~40 lines. Link to code with paths, not copies of code.
   - Add `inject: full` only for small, always-essential entries; the default lets siyaq
     send a summary first.
3. **Verify:** run `siyaq match "<the question>"` again and confirm the new entry is listed as
   `match`. If not, add the missing words to `keywords`.
4. Tell the user the file to commit so the whole team gets it.
