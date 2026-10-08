# Changelog

All notable changes to prof are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- prof reads the Nexika profile (~/.claude/nexika/profile.json): when it says you are a developer or a writer, the session note is one line and Claude answers questions about code instead of starting a lesson. The first session asks the role once. (#65)
- Publishes the retention checks due and open items to the shared status file (status/prof.json) at session start and after a report, so mizan can show them. (#67)

### Changed
- The family role now lives in the one Nexika settings file, ~/.claude/nexika/settings.json, next to the background-call consent; an older ~/.claude/nexika/profile.json is moved in once (kept as profile.json.migrated), so a role already chosen or a question already asked is never asked again. The background-call consent shares the one Nexika settings file (~/.claude/nexika/settings.json) with the family role; an existing settings.json keeps its answer and is stamped with schema nexika.settings/1 once. (#108)
- Automatic reports follow the family setting for background model calls (background_calls: ask, on or off in ~/.claude/nexika/settings.json): off stops them even after a yes, on allows them without asking. Each one is counted in ~/.claude/nexika/background.jsonl, runs with NEXIKA_BACKGROUND=1 so no Nexika hooks fire inside it, and prof's hooks exit inside other plugins' background calls. (#45)
- The once-only Nexika profile question now says the plugins assume a developer until it is answered; prof still runs its warm-up for anyone with lessons on record. (#51)
- prof stays quiet while you work: sessions with nothing due for review get a one-line note instead of the full tutoring context, lessons start only when you ask to learn ("teach me", /prof:learn), C# and C++ get their own topics (c-sharp, cpp), and an "explained but not tested" result no longer erases one you already showed. (#61)
- Topic history is stored as JSON (topics/SLUG.json) with a readable Markdown copy whose status edits are kept, and retention checks follow spaced repetition (3, 7, 14, 30, 60, 120 days for each success in a row) instead of one 14-day cutoff. Existing Markdown topics keep loading. (#75)

### Fixed
- prof no longer starts a paid background report without asking: Claude asks once whether to write automatic reports and remembers the answer (prof_store.py auto-report on|off), and a message that only mentions /prof: no longer marks a session as tutoring. (#43)
- Topic files and session reports carry a bayan: off marker, so bayan no longer turns their separators into commas and prof no longer answers "No history for topic" afterwards. (#46)
- A concept whose name contains a dash keeps its history instead of reloading as a different concept. (#87)

## [0.1.0] - 2026-10-06

### Added
- prof, a personal programming professor: step-by-step lessons, project onboarding for juniors, a warm-up check at the start of each session and a learning report at the end; it remembers each learner's progress.
