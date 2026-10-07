---
name: onboard
description: Onboard a junior developer to an existing project - map the architecture, explain how it runs, walk the main flows, and give a guided first task. Use when the user says "onboard me", "I'm new to this codebase, teach me", "help a junior learn this repo", or runs /prof:onboard. Not for a quick overview asked while working.
argument-hint: "[path or area of the project, optional]"
---

# Onboard a junior to a project

Scope: $ARGUMENTS (if empty, the current working directory).

## Phase 0 - Continue, don't restart

If `~/.claude/nexika/prof/topics/` has a topic for this project (slug like `project-<name>`), run the
`warmup` skill on it first: check what the learner kept from the last onboarding session and
re-explain missed parts before covering new areas. Then skip the layers already `understood`.

## Phase 1 - Map the project (silent research)

Launch the `prof:project-cartographer` agent on the scope. It returns a structured map:
stack, folders, entry points, main flows, data model, how to run/test, conventions, glossary.
For a large repo, launch up to 3 cartographers in parallel, each on a different top-level area.

## Phase 2 - Teach it in layers (wait for the learner between layers)

1. **The 30-second picture.** What the project does, who uses it, and the tech stack - in plain
   words. One ASCII diagram of the big parts and how they talk.
2. **The folder tour.** Each important folder in one line: "what lives here, when you touch it".
   Skip generated and vendor folders.
3. **How it runs.** Commands to install, run, test. What happens at startup, step by step, with
   `path:line` references.
4. **One real flow end to end.** Pick the most important user action (e.g. "a user logs in") and
   follow it through every layer with file references. Ask the learner to predict the next step
   before revealing it.
5. **Rules of the house.** Naming, patterns, testing style, branch/commit conventions, things
   that must never be done (found in CLAUDE.md, CONTRIBUTING, linters, existing code).
6. **Glossary.** Domain words and project-specific terms, one line each.

After each layer ask one check question and adapt depth to the answer.

## Phase 3 - Guided first task

Propose 2-3 small, safe starter tasks (small bug, add a test, small refactor) with the files
involved. Let the learner pick one, then guide with hints - the learner writes the code.

## Phase 4 - Leave a guide behind

Offer to write `ONBOARDING.md` in the project (only if the learner agrees) containing the map,
the flow walkthrough, glossary and starter tasks, so the next junior can read it.
Use the topic slug `project-<name>` for this project in the session report, with one concept
per layer or flow (e.g. "request flow: login", "folder structure", "how to run tests").
