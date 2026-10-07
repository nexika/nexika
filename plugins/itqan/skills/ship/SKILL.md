---
name: ship
description: Build a change end to end with quality gates - branch check, plan approval, failing tests first, minimal implementation until green, full verification, specialist review, then a commit proposal. Use when the user says "ship", "implement this properly", "build this feature", or "fix this bug with tests".
argument-hint: "<feature or bug to ship>"
---

# Ship a change

Task: $ARGUMENTS

Work through the gates in order. Do not skip a gate; if one fails, fix it or stop and ask.

## 0. Preflight
`barq git-status` (or `git status`).
- On the default branch → propose `feat/<short-name>` or `fix/<short-name>` and create it
  after the user agrees.
- Unrelated uncommitted changes → ask whether to stash, commit or include them.

## 1. Plan (gate: user approval)
Follow the `itqan:plan` skill. Continue only after the user approves the plan.

## 2. Tests first (gate: red for the right reason)
Launch `itqan:test-writer` with the approved plan. Check its report: the new tests exist and
fail because the behaviour is missing.

## 3. Implement (gate: green)
Implement the plan step by step, smallest change first. After each step run the tests itqan
detects: `itqan_proof.py checks` (the helper the session note names for `/itqan:proof`) lists
each check with its command; run the `tests:` ones. These are the same checks the proof in step 6
runs, so the suite you go green on is the one the proof records. On build or type errors, launch
`itqan:build-fixer`. Never make a test pass by weakening, skipping or deleting it.

## 4. Verify (gate: everything green)
Run every check `itqan_proof.py checks` lists (tests, lint, build). All must pass. With barq
installed you may run them through it to save tokens (`barq run:build run:test run:lint`) only
when `barq info` shows the same commands; if barq picked a different suite, use itqan's.

**Pages too, when the change touches the UI** (`.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.html`,
or the Tailwind theme) and lawha is installed (its session note names the helper): follow
`/lawha:check --fix` for each page the change affects. It checks every width, light and dark, LTR
and RTL, and records the result where `itqan:proof` reads it. Its "must fix" problems block this
gate like a failing test.

## 5. Review (gate: no critical/high findings left)
Follow the `itqan:review` skill on this branch's diff. Fix critical and high findings, then
repeat step 4.

## 6. Proof
Follow the `itqan:proof` skill: itqan runs the checks itself and saves the proof with the review
verdict and the requirements met.

## 7. Wrap up
Summarize: what changed (files), tests added, review result, the proof, anything deferred. Propose a
commit message (imperative subject, body explaining why). **Ask before committing, pushing,
or opening a pull request.**
