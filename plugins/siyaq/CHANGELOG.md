# Changelog

All notable changes to siyaq are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- siyaq reads the Nexika profile (~/.claude/nexika/profile.json): a learner gets looser matches (min_score 0.7), so more of the project's docs show up; a min_score in .siyaq.json still wins. (#65)
- Arabic questions now find English docs and English questions find Arabic docs through a built-in glossary of common software and business words, and summaries keep tables and code blocks whole. (#72)

### Changed
- The family role now lives in the one Nexika settings file, ~/.claude/nexika/settings.json, next to the background-call consent; an older ~/.claude/nexika/profile.json is moved in once (kept as profile.json.migrated), so a role already chosen or a question already asked is never asked again. (#108)
- siyaq never indexes what Claude Code loads by itself (CLAUDE.local.md and anything under .claude/, such as .claude/rules), even when .siyaq.json includes it. /siyaq:slim and /siyaq:add send instructions for one area of the code to .claude/rules with paths: instead of a siyaq entry. (#49)
- With no Nexika profile role, siyaq matches as it does for a developer (min_score 1.0, as before), so the family agrees on one default. (#51)

### Fixed
- The prompt hook no longer freezes on large repositories: after 0.3 s it answers from the last saved index while a background process builds the new one. Task notifications, pasted blocks and the compaction prompt no longer get project knowledge (the words typed around a pasted block still do). (#118)
- Far fewer irrelevant injections: only a section's own heading counts as a title hit, short prompts need two matching words, acknowledgements inject nothing, back-links to a parent README are not triggers, and a section already shown no longer pulls in weaker ones. (#38)
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- Hooks are much faster on big repos: each glob is compiled once, and hooks reuse the list of doc files for up to 30 seconds (sooner after a commit, checkout or staging, a config change or a new doc Claude writes). On a 30,000-file repo a tool call's hook went from about 1.2 s to about 50 ms. (#50)
- Parallel tool calls (several Reads at once) no longer inject the same knowledge twice, and the index cache can be rebuilt by two hooks at once without an error. (#79)
- Words like test, fix, index, docs and spec now count when matching ("run the tests locally" no longer loses "tests"), and the usage events file is readable only by you and rotated at 1 MB. (#80)

## [0.1.0] - 2026-10-06

### Added
- siyaq, project knowledge loaded only when relevant: entries generated from your docs, multilingual matching (Arabic included) with ranking and a token budget, triggers on the files being touched, and stats on what helped and what is missing. (#9)

### Changed
- siyaq loads less as the context fills, by mizan's level: half the budget and one entry fewer at mid, only the strongest match as a summary when full.
