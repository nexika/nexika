# Changelog

All notable changes to tabib are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- Flaky tests: a failing test that also passed on the same commit, in an earlier attempt or another run of the same workflow, is named as flaky with the run links. Read from GitHub when needed; nothing new is stored. (#103)
- Suspect commits are ranked by git blame on the failing lines (the assertion line and the stack frames in the log, at the failing commit): the commit that last wrote a failing line comes first, with the lines it wrote. (#104)
- Playwright failures (leaving out tests that passed on a retry), JUnit XML reports printed in the log, and segmentation faults (a crash signal, and a failure at the running test when Python's faulthandler names it) are read from the CI log. (#105)

### Changed
- CI logs are scanned with haris's improved prompt-injection patterns (paraphrases and fake system blocks), and documentation that only quotes an attack phrase is no longer flagged. (#63)

### Fixed
- A failure in a single matrix job is no longer blamed on every value that job has; tabib now says "in one job" with low confidence unless two failed jobs share the value or it is the only value that differs. (#29)
- Stopping tabib mid-run (SIGTERM, SIGHUP, the Bash tool's 120 s limit) no longer leaves a git worktree, a temp folder or running tests behind; the local test run now stops after 90 s, and worktrees left by a run that died are cleaned up on the next one. (#30)
- tabib reproduces your own commit after a squash-merge deleted its branch (when CI says the run was not from a fork), and a dependency file from another ecosystem (a package-lock.json for a pytest failure) no longer blocks reproducing. (#31)
- cargo panics now land on the test that panicked, and each pytest failure gets its own line instead of the file's first one (#32)
- jest files reported with a duration (`FAIL x.test.ts (5.1 s)`) and `go test -v` locations printed before `--- FAIL` are read correctly (#32)
- mypy errors are read, and reproduced with the project's Python (#32)
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- A runner shutdown is no longer called a time limit (the most specific sign in the log now names the cause; "The operation was canceled" alone reads as a cancel), and the word "Killed" in a test's own message no longer raises an out-of-memory signal. (#89)
- Triage reuses its saved result for a CI run that has no update time, instead of redoing the work. (#101)

## [0.1.0] - 2026-10-06

### Added
- tabib finds out why CI failed, with evidence: it reads the failed GitHub Actions run or GitLab pipeline, pulls out the failing tests and errors (pytest, jest, vitest, go, dotnet, cargo, tsc, ruff, eslint), sorts the failure (code, one Python or OS only, flaky, infrastructure such as a cancelled run or the network, dependencies), compares with the last green run, runs the failing tests again in a throwaway git worktree, and reports the cause with evidence through /tabib:diagnose. It diagnoses only: it never edits code, pushes or re-runs CI; flaky and infrastructure failures come with the re-run command for you to run. English and Arabic.
