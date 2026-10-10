# Changelog

All notable changes to barq are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-10

### Added
- info finds pre-commit (lint: pre-commit run -a, with its hooks), tox envs and a pyproject build backend (build: python -m build), and no longer lists docs or test-data manifests as stacks (#167)
- run: Node's built-in test runner (node --test, borp) is parsed: the verdict gives the failed/passed/skipped counts, and the details show each failing test with its file:line, error and diff (TAP: the not ok lines with location and error) (#268)
- TypeScript outlines list interface members (method and property signatures, each overload on its own line), so @FastifyReply.send or @FastifyInstance.after finds them; parameters of call signatures are not taken for members (#277)

### Changed
- Python outlines show a short decorator tag (@property, @staticmethod, @overload, @dataclass, @click.option x29), list nested functions under their parent so read:FILE@outer.inner works, and print defaults as color: bool = False (#168)

### Fixed
- run no longer sets NO_COLOR, FORCE_COLOR or TERM, which could turn a passing suite red; color codes are stripped from the output instead (#165)
- run keeps every flake8, ruff and mypy line (path:line:col: CODE) and counts them, no longer repeats shown lines in the 'last lines' tail, and cuts very long lines (#166)
- git-status says when a merge, rebase, cherry-pick or revert is in progress and suggests finishing or aborting it instead of pushing; renames show the old name (#169)
- map names the source files that have no symbols instead of counting them silently, and a pytest collection error shows the module's real error (SyntaxError, ImportError) instead of a pytest internal frame (#170)
- run: ESLint's default (stylish) output is parsed: every finding keeps its file (path:line:col: level message (rule)), errors before warnings, with eslint's problem count as the verdict; paths under the project root are shown relative to it (#269)
- run: tstyche type tests get their own verdict (test files and assertions, failed and passed) and each error with its file:line:col; a run that exits non-zero is never summed up as only passed (#270)
- run and custom ops: a timeout now ends the command's whole process tree, so test runners such as borp no longer leave node processes running (#271)
- JS outlines show functions assigned at the top level (Reply.prototype.send = function, module.exports = function noopSet), and @Reply.send finds Reply.prototype.send; a short @name that matches several different symbols lists them with their lines instead of returning them all (#272)
- JS/TS outlines: a function with a destructured or default-object parameter (function f ({ a }) {, printRoutes (opts = {})) now spans its whole body instead of only its first line (#273)
- JS/TS outlines: a regex literal that contains a quote or a backtick (/^[\w!#$%&'*+.^`|~-]+$/) no longer hides the rest of the file; lib/content-type.js shows its class again (#274)
- JS outlines no longer list calls and object-literal values as symbols (createError(, new Set([, eos(..., ternary branches); an object-literal function (delete: function _delete, closeRoutes: () => {) is named by its key, so @delete and @hasPlugin find it (#275)
- TypeScript outlines: a type alias ends where its type ends (not at a later brace), a bodyless declare function overload ends at its own last line, and aliases whose generic parameters span several lines (export type X<\n ...\n> = ...) are found (#276)
- info and run:test pick a Node project's test command by what the script runs: a script that runs test code (test files or a test runner) and no linter wins, so fastify's run:test runs test:ci instead of stopping at eslint; a script that only lints, or npm's 'no test specified' placeholder, is no longer a test command (#277)

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
