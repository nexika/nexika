# Changelog

All notable changes to mizan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-10

### Added
- The band names tabib's new "CI setup" kind instead of showing a raw key. (#127)

### Fixed
- When CI fails, the band names every failed workflow, each job with its workflow ("changelog/check, test +3"), instead of one job of one workflow. (#159)
- Cancelled CI jobs are no longer counted as failures: the band names the real failure, shows how many were cancelled, and says "CI superseded" when every run was cancelled. (#160)
- CI is found for a detached HEAD and for a commit older than the branch's last 20 runs (read by commit), and a detached HEAD no longer names you as the one who started it. (#161)
- One gh error no longer erases a known CI result or PR list: the last good result stays (dimmed), and the band says "gh: rate limited" or "gh: timed out". (#162)
- Names in the band: a fork pull request's branch shows the PR author's name (the same as in the PR list), bots show as "dependabot" instead of "app/dependabot", and titles like Mr. or Dr. are skipped when taking a first name. (#163)
- "CI running" shows the time left on a fork's branch too: the usual duration comes from the branch's other runs, or from the workflow's recent runs. (#164)
- The band names tabib's new code failures (a failed check, a merge conflict, a generated file out of date) in English and Arabic, and a kind it does not know yet shows as failures instead of a raw key. (#208)
- CI whose workflows wait for a maintainer's approval now shows "CI waiting for approval" (and "CI not run: approval expired" after GitHub's 30 days) instead of passed or failed. (#243)
- Only the commit's CI counts (push, pull_request and merge_group runs): monthly schedule jobs, Copilot reviews, dependabot updates and pull_request_target runs such as a labeler or a post-merge backport no longer make CI passed or failed; a PR where only those ran shows "no CI yet". (#244)
- A workflow re-run at the same commit (a title check after a title edit) replaces the old run: the old red run no longer keeps CI failed. (#245)
- Jobs allowed to fail (continue-on-error) in a workflow run that succeeded no longer show as CI failures on a PR; the report lists them as "allowed to fail". (#246)
- CI running keeps showing when two workflows share a name (fastify has two called ci): the time left is looked up by workflow id, and a failed lookup only drops the time left. (#247)
- A fork's pull request checked out under another name (`gh pr checkout` calls a fork's main `<owner>/main`) is linked again: when no PR matches the branch name, the one open PR at this exact commit is used. (#248)
- Names: a GitHub profile name that is the word "undefined" (or "null", "none") is replaced by the login, and a branch started by a bot is credited to "dependabot", not "dependabot[bot]", as in the PR list. (#249)
- `mizan refresh` no longer calls gh or glab when the network is off (MIZAN_OFFLINE=1 or "network": false); it says so and exits. (#250)
- For a CI run with no jobs or log, the band says "no jobs or log" instead of sending you to a log that does not exist. (#331)

## [0.2.0] - 2026-10-08

### Added
- mizan doctor shows the family settings file (~/.claude/nexika/settings.json): the role and the background-call consent, and warns when other users can read it. Its hook timing run also keeps NEXIKA_HOME and NEXIKA_PROFILE pointed at the throwaway home. (#108)
- Shows the rest of the family: amin's projects ready to release and prof's reviews due in the band; manar's last score and barq's savings for today in the pane. (#67)
- mizan doctor (and /mizan:doctor) looks at the installed Nexika plugins together: the hooks each adds and how long each takes, known conflicts (bayan with Claude Code's signature line on, itqan without haris) and status files that are stale, of an unknown schema or readable by others. (#68)
- The context's mid and full levels are settings (`context_mid`, `context_full` in config.json) (#77)
- A running CI shows how long it has run and about how long is left, from its recent runs (`CI running 3m · ~4m left`) (#77)
- The band shows pull requests waiting for your review (`Reviews for you 2`) (#77)
- With lawha installed, mizan's band shows its latest check of the project's pages at this commit (`lawha ✓ 6 widths` or `lawha: 3 to fix`) with a Fix button that puts `/lawha:check --fix` in the prompt, and the pane lists the problems, what was covered and the report; the proof pane shows the pages check itqan recorded. (#18)

### Changed
- mizan calls gh or glab far less: the pull request list is kept for its 5 minutes, polling slows to a quarter after 10 minutes with nothing new (a new commit is still fetched at once), and a new CI failure shows at once instead of after tabib's triage. (#60)

### Fixed
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- Sessions that work through Agent calls instead of a task list now get the task step from their agents and the "Done. Show me the proof?" question when all of them finish; the status-line fallback shows running agents too. (#59)

## [0.1.0] - 2026-10-06

### Added
- mizan, a band above the prompt that keeps your session in balance: the branch and who started it, open PRs or MRs per person (gh and glab), the branch's CI (passed, failed with the job, running), RAM and disk with warnings at 85 and 95 %, the context level (fresh, mid, full), the running agent and its task, the current task step and the session cost, in English and Arabic. /mizan opens the details and the itqan proof; at full context it saves a hafiz handoff and puts /clear in the prompt for you to send, never clearing by itself. Without the mod engine, a status line prints the same two lines.
- When CI fails, mizan asks tabib for a quick triage (no AI, once per run) and the band shows the kind of failure, like `tabib: only py3.10` or `tabib: flaky?`, with a Why? button that puts /tabib:diagnose in the prompt; the pane shows tabib's cause, and the proof pane shows the CI failure a change answers.
