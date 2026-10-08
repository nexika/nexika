# Changelog

All notable changes to barq are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- Publishes today's savings to the shared status file (status/barq.json), keeping the bytes it sent beyond the built-in tools apart, so mizan can show an honest figure. (#67)

### Changed
- barq's session note no longer tells Claude to use barq instead of Read, Grep and Glob (Edit needs a Read first, so that added round-trips). It now points Claude at test, build and lint results, git-status, outlines and info; the other ops still work when called. (#49)

### Fixed
- run:build no longer runs a sub-project's build (say benchmarks/starter) when the root has none; it says so and lists the nested build commands instead. (#109)
- barq no longer masks ordinary code as secrets: keys that only mention a secret (`MAX_TOKENS`, `token_type`, `jsonwebtoken` in package.json), versions, code expressions and prose stay as written, so masked text no longer ends up in your files. A read that masks something says so, and the new `read:PATH:raw` gives the exact text for editing. (#22)
- barq stats no longer inflate savings: a line range is compared with the same range from the built-in Read, grep with Grep's file list, and ops that sent more count as negative. A full read stops near 25 KB (Claude Code cuts longer output) and is then not remembered as seen, and each subagent gets its own seen-before cache, so it never gets "unchanged" for a file only the main agent read. (#39)
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- run:test and info now pick the root project's own suite (pyproject.toml with tests/) over a package.json in a subfolder; the nested one is still listed under "also detected". (#47)
- barq run recognises pytest -q summaries, read@Type.Method finds Go methods by receiver (Server.Start), outlines include TypeScript class arrow fields and type aliases, multi-line template literals no longer cut a function short, and a symbol read whose end wasn't found says it may be partial. (#86)

## [0.1.0] - 2026-10-06

### Added
- barq, many file and project operations in one call: batched and symbol reads, a seen-before cache that skips files Claude already read, short test and build output, git status with the next steps, secret masking, and stats on what it saved. (#2)
