# Changelog

All notable changes to amin are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-10

### Added
- A project whose changelog is its GitHub releases can set "changelog": "github" in .amin.json: prepare writes no changelog file and prints the notes for the release PR, and publish builds the release notes from the notes the release commit consumed. projects says when the changelog file is missing. (#238)

### Changed
- triage ranks possible duplicates most similar first, leaves out title templates and the repo name, and compares open issues with the 200 most recently closed ones too. (#156)

### Fixed
- A project whose pyproject.toml takes its version from tags (hatch-vcs, setuptools-scm) now gets its version from tags, and prepare no longer overwrites the version template; only a version directly under [project] or [tool.poetry] is read from pyproject.toml. (#152)
- Bare version tags such as 26.10.0 (no v) are found: a single project uses the tag style its tags already have, and history reads only the latest 200 merged PRs when no tag exists instead of timing out. (#153)
- An existing CHANGES.md or HISTORY.md is used instead of a new CHANGELOG.md, and its own heading style (such as ## Version 26.10.0) is kept: new versions go above the newest one and publish finds their notes. (#154)
- Calendar versions (YY.M.patch, such as 26.10.0) are detected from the tags: plan proposes YY.M.0 for a new month or a patch within the same month instead of a SemVer bump. (#155)
- triage lists stale issues oldest first and leaves out issues labelled accepted or for discussion (more such labels can go in .amin.json as triage.keep_labels). (#157)
- history no longer lists the release PR that was merged as the tagged commit, and marks bot PRs [bot] and PRs that change only CI files [ci only] so release notes can skip them. (#158)
- The last release is the newest tag on the current branch, so main's alpha line and a 5.x maintenance branch each plan from their own last tag (a 5.x tag no longer counts on main, nor v6.0.0 on 5.x). (#235)
- Alpha, beta and other SemVer prereleases (6.0.0-alpha.4) are understood: plan continues the line (6.0.0-alpha.5), prepare --pre[=LABEL] makes the next one, publish marks them as prereleases, and prepare no longer writes a version lower than the version file's without --allow-lower. (#236)
- A version kept in a second place (fastify.js const VERSION) can be listed in .amin.json version_files with a pattern, and prepare writes it too; projects and plan warn about a source file that holds the version but is not listed. (#237)
- publish on a branch other than the default one gives one true reason (it no longer also says local main differs from origin/main), and a release of an older line is created with --latest=false when a newer final release exists. (#239)
- history lists only the PRs whose merge commit is on the current branch since the tag, so main and a maintenance branch no longer mix each other's PRs; history NAME --from TAG --to TAG lists what went into one release. (#240)
- history no longer marks a bot's backport PR ([Backport 5.x] title or a backport label) as [bot]: it carries a human change and is the maintenance release's content. Dependency bumps and other bot PRs are still marked. (#241)
- The check-fragment hint works in any repository: it names the note file to add (changelog.d/<PR>.fixed.md, with the PR number in CI) and the amin command by the path it runs from, not a path only Nexika has. (#242)

## [0.2.0] - 2026-10-08

### Added
- `amin copies` keeps files listed under "copies" in .amin.json identical to their source, and `amin prepare` refreshes them in the release PR. (#44)
- amin prepare --umbrella also releases the whole marketplace: the root version and a root CHANGELOG section listing the released plugins, published with amin publish <marketplace name>. (#56)
- Notes named by a slug get the number of the pull request that added them in the CHANGELOG. (#56)
- amin prepare --dry-run shows the versions, files and CHANGELOG sections without changing anything, and prepare refuses to run on the default branch or with uncommitted changes. (#56)
- Publishes the projects ready to release to the shared status file (status/amin.json) after plan, a note, prepare or publish, so mizan can show them. (#67)
- Release candidates: amin prepare --rc releases 1.3.0-rc.1, -rc.2 and so on as GitHub pre-releases, and a later prepare promotes to the final version with every note. (#69)
- Single-project repos also keep package-lock.json, Cargo.toml (including a [workspace.package] version) and Cargo.lock in step with the release version. (#69)

### Fixed
- The change-note check no longer passes a pull request that deletes another project's pending note, adds an empty note, or puts a note where it is never released; the CI job runs the base branch's copy of the checker. (#33)
- amin publish can be run again after the GitHub Release step failed: when the tag is already on the release commit and the release is missing, it creates only the release instead of stopping at "tag already exists". (#34)
- amin prepare puts the new version below the [Unreleased] section instead of above it, and refuses a version below what the notes require (a breaking note released as a minor) unless you pass --allow-lower. (#35)
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- amin history no longer drops pull requests merged just after a tag made in a non-UTC time zone, and it asks GitHub for every PR merged since the tag instead of only the last 200. Inside an amin work worktree, a single-project repo keeps its own name from package.json, pyproject.toml or the .csproj instead of being named after the issue number. (#85)

## [0.1.0] - 2026-10-06

### Added
- amin, a repository maintainer that never merges for you: issue triage with approval, issues worked in isolated worktrees into pull requests, change notes enforced in CI, and step-by-step releases with versions, CHANGELOGs, tags and GitHub Releases.
