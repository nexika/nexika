# Changelog

All notable changes to amin are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

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
