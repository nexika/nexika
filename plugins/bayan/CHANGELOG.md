# Changelog

All notable changes to bayan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- bayan reads the Nexika profile (~/.claude/nexika/profile.json): your role (developer, learner or writer) sets the reader level unless you chose one with /bayan:level, and the first session asks the role once. Changing another bayan setting no longer pins the reader level. (#65)

### Changed
- The family role now lives in the one Nexika settings file, ~/.claude/nexika/settings.json, next to the background-call consent; an older ~/.claude/nexika/profile.json is moved in once (kept as profile.json.migrated), so a role already chosen or a question already asked is never asked again. (#108)
- When you keep Claude Code's signature with the attribution setting (or includeCoAuthoredBy), bayan no longer tells Claude to drop it from commits and pull requests. (#49)
- bayan's default reader is now a developer, not someone who has never written code: words like branch or API are no longer flagged as jargon unless you choose another level or role. (#51)

### Fixed
- Commits and pull requests that carry Claude Code's signature line are no longer denied and retried: bayan lets them through and tells Claude to leave the line out and how to turn it off with the attribution setting (set deny_signatures to block them as before). Git's global options such as git -c x=y commit no longer hide a commit from the check. (#25)
- bayan no longer rewrites prompt files (SKILL.md, CLAUDE.md, AGENTS.md, .claude/, agents/, output-styles/) or text people wrote: when Claude rewrites a whole existing file only the changed lines are cleaned, and dashes in headings, table rows and ranges such as Mon – Fri stay. (#26)
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- Hooks leave before loading the word lists when there is nothing to do: a command that is not a commit, tag, pull request or release, or a write to a file that is not prose (about 60-90 ms down to about 35 ms). (#50)

## [0.1.0] - 2026-10-06

### Added
- bayan, Claude writes like a clear, friendly person in English and Arabic: a reader level (no-code, junior, developer), automatic clean-up of hidden characters, AI signature lines, filler sentences and wordy phrases in written documents, a line-by-line style check, and a guard against signed commits and pull requests.
