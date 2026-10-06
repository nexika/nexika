# Changelog

All notable changes to haris are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-06

### Added
- haris, a guard against harmful agent actions: every tool call (subagents included) is read by a real shell parser that unwraps wrappers and judged by its action and target; safe reads and project runs are allowed, risky actions asked about and dangerous ones refused with a plain reason; secrets, persistence spots and haris itself are protected, data leaving the machine is checked for secrets, prompt injection in tool output is flagged, approvals count only when you type them, and every ask and refusal is kept in an owner-only, redacted audit log. Profiles relaxed, standard and strict; a watch mode. Actions refused in every profile cannot be approved; a script written and run in the same command is read and judged before it runs; HTTP DELETE to another computer asks, like `gh api -X DELETE`.

### Changed
- haris also guards mizan (its code, its folder and settings) and the shared Nexika status files under ~/.claude/nexika/status, refuses running mizan's hooks or publishing its status by hand, and publishes its own profile and mode for mizan's band.
- haris also guards tabib's diagnoses (~/.claude/nexika/tabib) and refuses running tabib's code outside its helper.
