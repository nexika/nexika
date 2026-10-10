# Changelog

All notable changes to tabib are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-10

### Added
- A workflow that cannot work as written (an externally managed Python, a tool that is not installed, an action rejecting its input) is now its own kind, "the CI setup is broken", with advice to fix the workflow instead of re-running it. (#127)
- tabib reads failures from Node's built-in test runner (the '✖ failing tests:' block, with each test's file and line) and borp's 'failed: <file>' lines, so fastify-style runs name the failing test instead of being unclear (#251)
- tabib reads a coverage threshold that is not met (c8, nyc, istanbul, jest, pytest-cov) as a code failure, naming each file below 100% at its first uncovered line (#257)
- tabib reads TypeScript type-test failures from tstyche ('Error: ...' at './x.tst.ts:L:C') and tsd ('✖  L:C  ...'), with the file and line of each (#258)
- tabib reads documentation checks: markdownlint errors (file and line), and broken links from lychee (with the page) and linkinator; a link to a site that is down is not counted as a broken link (#259)

### Changed
- The README's "What it reads" table and parse.py's overview list every log tabib now reads: Node's test runner and borp, type tests, coverage thresholds, documentation checks, problem-matcher lint and the new signals and kinds. (#332)

### Fixed
- When one job of a matrix fails and GitHub cancels the others, tabib now reports the real failure instead of "the run was cancelled" with advice to re-run. (#126)
- A test that fails because a package was never installed ("No module named 'jsonschema'") is now reported as a dependency problem that names the package, not as a failing test. A missing module of the project itself is still a code problem. (#128)
- A pre-commit job whose hooks failed (for example ruff-format changing files) is now reported as lint errors that name each hook, with the command to run them locally, instead of "unclear: read the log". (#131)
- When pytest cannot import a conftest ("ImportError while loading conftest"), tabib now reports that conftest file and the error under it, instead of "unclear: read the log". (#132)
- When every failure is a warning raised inside a dependency's code (for example a new DeprecationWarning from a library's development version), tabib now reports a dependency problem that names the package, instead of failing tests with advice to fix them. (#133)
- A formatter's check (black --check, ruff format --check, prettier --check) is now a lint failure naming the files that would be reformatted, with the command that fixes them, instead of unknown. (#171)
- A failed step whose only output is a message the workflow itself prints (such as a missing changelog line) is reported as a failed check with that message, instead of unknown; when the same commit passes later (after a skip label), it is no longer called flaky. (#172)
- A pull request that does not merge into its base ("CONFLICT ... Merge conflict in <file>") is reported as code, "the branch does not merge into its base: rebase", naming the conflicting files, instead of unknown. (#173)
- A generated file that is out of date (a step that regenerates files and fails on `git diff --exit-code`) is reported as code, "generated file out of date: <path>", with the step's regenerate command, instead of unknown. (#174)
- When one job of a matrix fails and the base branch's recent runs fail the same job on the same system (a Windows job, say), tabib says likely flaky instead of blaming the change; a test failing in several jobs is counted once, "1 failing test(s), in 26 jobs". (#175)
- More broken CI setups are read as "the CI setup is broken" instead of unknown: a Python version the runner does not have, a tool option from the workflow's env that the tool rejects, a missing artifact from the run a workflow follows, and a crashing CI helper script (scripts/, .github/), including one that cannot import a module. (#176)
- A failed run with no jobs (and so no log) now gets a kind, "the CI setup is broken", with plain advice (the workflow file did not parse or no job could start; open the run page) instead of the raw gh error; an expired log says "the log has expired". (#177)
- Arabic text that only describes someone ignoring rules (يتجاهل Claude القواعد) is no longer flagged as prompt injection in CI logs; orders such as تجاهل جميع التعليمات still are. (#212)
- The shared git reader names a bot's commits as the PR list does ("dependabot", not "dependabot[bot]"); tabib's output does not change. (#249)
- A passing test's name (such as '✔ ignores ECONNRESET') is no longer read as a network, timeout or other outside-the-code signal (#252)
- A test's own timeout (node:test's 'test timed out after 30000ms', jest's 'Exceeded timeout of', pytest-timeout's 'Timeout >') is no longer read as the CI job's time limit; the failing test is marked as timed out instead (#253)
- GitHub's own service errors (an action that cannot be downloaded, '##[error]Service Unavailable', a link checker's HTTP 5xx) are now read as an outside-the-code network problem instead of unclear (#254)
- tabib no longer says a run 'fails only on <value>' when it read no failure: with nothing read and no signal, the run is unclear (#255)
- Lint errors behind GitHub's problem matcher ('##[error]  100:80  error ...') are read for eslint, ruff, mypy and tsc, and eslint's file paths are made relative to the checkout (#256)
- A JavaScript action that fails with its own message (a pull-request title check, an ecosystem-order check) is read as a failed check with that message, and is no longer called flaky when the same commit passes after the title is edited (#260)
- A crash inside node_modules/<package> after a dependency change (package.json or a lock file changed, or a Dependabot/Renovate branch) is now a dependency problem naming that package; package.json counts as a dependency file (#261)
- A workflow token that lacks a permission ('Resource not accessible by integration' on the repository's own run) or a branch rule that stops it ('Repository rule violations found') is now a CI setup problem, not missing credentials to re-run; a fork's pull request stays 'missing credentials' (#262)
- A CI run with no jobs and no log is no longer called 'the CI setup is broken': tabib says the run has no jobs or logs, so there is nothing to diagnose, with only the facts it can see (event, a fork's pull request, the run page) (#263)

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
