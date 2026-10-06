# Changelog

All notable changes to mizan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-06

### Added
- mizan, a band above the prompt that keeps your session in balance: the branch and who started it, open PRs or MRs per person (gh and glab), the branch's CI (passed, failed with the job, running), RAM and disk with warnings at 85 and 95 %, the context level (fresh, mid, full), the running agent and its task, the current task step and the session cost, in English and Arabic. /mizan opens the details and the itqan proof; at full context it saves a hafiz handoff and puts /clear in the prompt for you to send, never clearing by itself. Without the mod engine, a status line prints the same two lines.
- When CI fails, mizan asks tabib for a quick triage (no AI, once per run) and the band shows the kind of failure, like `tabib: only py3.10` or `tabib: flaky?`, with a Why? button that puts /tabib:diagnose in the prompt; the pane shows tabib's cause, and the proof pane shows the CI failure a change answers.
