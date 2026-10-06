# Changelog

All notable changes to hafiz are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-06

### Added
- hafiz, Claude remembers your work: decisions, tasks, problems, changed files and links captured as you work without AI calls (secrets replaced and `<private>` text dropped before saving), a short start card, a snapshot restored after compaction, automatic handoff notes per branch, Arabic and English search, a detailed session summary naming the issue and branch (Sonnet by default, Opus on request), and the `nexika.hafiz/1` export for the other Nexika plugins.
- `hafiz handoff --save --session ID --transcript PATH` captures the session and writes the handoff note on demand; mizan uses it as the context fills. Only a session transcript under ~/.claude/projects is read.
