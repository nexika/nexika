# Changelog

All notable changes to mizan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

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
