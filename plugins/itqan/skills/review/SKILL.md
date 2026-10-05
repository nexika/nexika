---
name: review
description: Review code changes for real defects and security issues with specialist reviewers, verify every serious finding against the code, and report a ranked verdict. Works on uncommitted changes, the current branch, or a pull request. Use when the user says "review", "check my changes", "is this ready", or before merging.
argument-hint: "[PR number | base branch | paths]"
---

# Review changes

Target: $ARGUMENTS

## 1. Find the diff
- PR number and `gh` available: `gh pr diff <n>`.
- A base branch: `git diff <base>...HEAD` plus uncommitted changes.
- Nothing given: uncommitted changes plus the branch against the default branch
  (`git merge-base HEAD origin/HEAD` or `main`).
Show the file list and size (`git diff --stat`). If empty, say so and stop.

## 2. Review in parallel
Launch together, passing the diff command and the stack pack paths from the session note:
- `itqan:code-reviewer` always;
- `itqan:security-reviewer` unless the diff only touches docs, tests or formatting.

## 3. Verify before reporting
For every critical or high finding, open the cited lines yourself and check that the failure
or attack scenario really holds in this code. Drop findings that don't, and downgrade ones
that need unusual conditions. Say how many were dropped.

## 4. Report
```
Verdict: ready to merge | fix first | needs discussion
| # | severity | where | problem | fix |
Missing tests: ...
Dropped after verification: N
```
Then offer to fix the critical/high findings. Apply fixes only after the user agrees, then
re-run the tests (`barq run:test`).
