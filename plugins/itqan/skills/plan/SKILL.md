---
name: plan
description: Plan a change before writing code - acceptance criteria, the existing code it plugs into, tests to write first, ordered steps, risks. Produces a plan for approval and does not edit code. Use when the user says "plan", "how should we build", "design this feature", or before a change touching several files.
argument-hint: "<feature or change to plan>"
---

# Plan a change

Task: $ARGUMENTS (if empty or ambiguous, ask 1-3 short questions first).

1. **Stack checklists.** The itqan session note lists the checklist packs for this project's
   stacks. Pass their paths to the planner.
2. **Plan.** Launch the `itqan:planner` agent with the task, the pack paths, and anything the
   user already decided.
3. **Check the plan yourself before showing it:**
   - cited files and symbols exist (`barq 'read:PATH:outline'` or Read);
   - there is a "Tests first" section and every acceptance criterion maps to a test;
   - steps are small and ordered; nothing out of scope sneaks in.
   Fix or send back anything that fails these checks.
4. **Present** the plan and ask for approval or changes. Do not edit code.
5. If the user wants it kept, save it as `docs/plans/<short-name>.md` (ask first).
