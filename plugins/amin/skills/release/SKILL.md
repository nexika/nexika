---
name: release
description: Release one or more projects of the repo - collect change notes, propose versions with reasons, prepare a release pull request (versions, CHANGELOG sections), and after the human merges it, publish tags and GitHub Releases. Handles first releases by drafting notes from merged PRs. Use when the user says "release", "cut a release", "publish a version", "new version", or "amin release".
argument-hint: "[project ...]"
---

# Release

The amin helper is printed in the session note; below it is written `amin`. Every step that
changes something needs the user's approval. **A human always merges.**

## 1. Plan
Run `amin plan` and show it. Statuses: `release` (notes waiting), `first-release` (never tagged,
has notes), `needs-notes` (changes but no notes, or a first release without notes), `nothing`.

## 2. Notes (only if needed)
For `needs-notes` projects the user wants to release: run `amin history <project>` to list the
merged PRs that touched it. Draft one user-facing note per meaningful PR (type + one sentence,
not the commit title; PRs marked `[bot]` or `[ci only]` usually need none), show them, and after approval add each:
`amin fragment add <project> <type> "<text>" --id <PR number>`. Re-run `amin plan`.

## 3. Versions
Show each proposed version with its reason (`added` → minor, `fixed` only → patch, `breaking`
→ major, or minor while the version is 0.x). The user may override (`NAME=VERSION`). Ask
explicitly before any major version. For a release candidate add `--rc` to prepare (`1.3.0-rc.1`,
published as a pre-release; notes are kept); preparing again without `--rc` promotes it to final.
On an alpha or beta line (`6.0.0-alpha.4`) the plan proposes the next one (`6.0.0-alpha.5`); offer
the promotion (`--pre=beta`, or `<project>=6.0.0`) as a choice, never pick it yourself.

## 4. Release pull request
1. From an up-to-date default branch with a clean tree, create `release/<project>-<version>`
   (several projects: `release/<date>`).
2. Run `amin prepare <project>[=<version>] ... --dry-run` and show the result, then the same
   without `--dry-run`; show the CHANGELOG sections it wrote. It refuses to run on the default
   branch or with uncommitted changes. A version below what the notes require is refused; add
   `--allow-lower` only if the user insists. In a plugin marketplace, add `--umbrella` when the
   whole repo is released too (root version and CHANGELOG; publish it with
   `amin publish <marketplace name>` after the project tags).
3. Commit (`Release <project> <version>, ...`), push, and open the PR with the sections in the
   body (for a `"changelog": "github"` project, the release notes `prepare` printed). **Stop and ask the user to review and merge it.**

## 5. Publish (after the user says the release PR is merged)
1. `git switch <default branch> && git pull`.
2. For each project: `amin publish <project> --dry-run` and show the checks (default branch,
   clean, up to date, version, CHANGELOG section, tag free, CI green).
3. After approval: `amin publish <project>`. Show the release links.

If any check fails, explain it and stop; never work around a failed check.
