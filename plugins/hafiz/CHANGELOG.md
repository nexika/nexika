# Changelog

All notable changes to hafiz are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- Decisions now include proposals from Claude that you agree to ("I suggest ..." followed by "yes" or "تمام"), more Arabic forms (نستخدم، خلّي), and the reason when one is given. (#57)

### Changed
- The background-call consent shares the one Nexika settings file (~/.claude/nexika/settings.json) with the family role; an existing settings.json keeps its answer and is stamped with schema nexika.settings/1 once. (#108)
- The detailed summary says how many model calls it made, refuses when background_calls is off, counts each call in ~/.claude/nexika/background.jsonl and runs it with NEXIKA_BACKGROUND=1, so no Nexika plugin's hooks fire inside it; hafiz's hooks exit inside other plugins' background calls. (#45)
- After compaction, hafiz no longer repeats the latest requests and finished tasks that Claude Code's own summary already carries; it gives the exact decisions, open tasks and problems, files and commits, and says the built-in summary is the main account. (#49)
- After compaction, the restore now follows recent work: the goal is your note or latest request instead of the first prompt, files are listed most recently touched first, pasted-content wrappers are stripped and files outside the repository are left out. (#58)
- Detailed summaries of long sessions now read the whole session in parts and merge the notes, instead of dropping the middle. (#73)

### Fixed
- Open tasks and failing commands now close when they are finished or pass in a later session, and open items untouched for 14 days expire instead of staying on the start card. (#36)
- Decisions are now taken only from sentences that state a choice, in prompts of any length, so ordinary requests are no longer recorded as decisions; commits made with `git commit -q` are now captured from `git log`. (#37)
- Over the memory cap, routine memories (files, links, closed tasks and problems) now go before decisions, files from other repositories no longer appear in "Files in play", and a search made only of common words returns nothing instead of unrelated memories. (#81)

## [0.1.0] - 2026-10-06

### Added
- hafiz, Claude remembers your work: decisions, tasks, problems, changed files and links captured as you work without AI calls (secrets replaced and `<private>` text dropped before saving), a short start card, a snapshot restored after compaction, automatic handoff notes per branch, Arabic and English search, a detailed session summary naming the issue and branch (Sonnet by default, Opus on request), and the `nexika.hafiz/1` export for the other Nexika plugins.
- `hafiz handoff --save --session ID --transcript PATH` captures the session and writes the handoff note on demand; mizan uses it as the context fills. Only a session transcript under ~/.claude/projects is read.
