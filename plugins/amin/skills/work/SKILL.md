---
name: work
description: Work a GitHub issue end to end in an isolated git worktree - plan, tests first, implement, verify, add a change note, open a pull request that closes the issue - then stop for the human to review and merge. Use when the user says "work on issue 42", "fix #42", "implement issue", or "amin work".
argument-hint: "<issue number>"
---

# Work an issue

Issue: $ARGUMENTS. The amin helper is printed in the session note; below it is written `amin`.

1. **Start.** Run `amin work start <N>`. It fetches the issue, creates a branch
   (`fix/<N>-...` for bugs, `feat/<N>-...` otherwise) and an isolated worktree next to the
   repo. **Do all work inside that worktree path** (use absolute paths); the user's main
   checkout stays untouched.
2. **Understand.** Restate the issue in two lines and the acceptance criteria. If anything is
   ambiguous, ask before planning.
3. **Build it properly.** If the itqan plugin is installed, follow `itqan:ship` (plan approval,
   failing tests first, implement until green, full checks, review). Otherwise: propose a short
   plan and get approval, write the failing test, implement, run the project's tests and build.
4. **Change note.** For every project the change touches, add one note in the worktree:
   `amin fragment add <project> <type> "<what changed, written for users>" --id <N>`.
   Type: `fixed` for bugs, `added` for new features, `changed` for behaviour changes,
   `breaking` if users must change something. `amin projects` lists the project names.
5. **Pull request.** Commit following the repo's conventions, push the branch, and open the PR:
   `gh pr create --title "<clear title>" --body "<what and why, how it was tested>\n\nCloses #<N>"`.
6. **Stop.** Show the PR link. **Never merge**: the user reviews and merges. After they merge,
   offer to remove the worktree (`git worktree remove <path>`) and the local branch.
