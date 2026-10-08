# Changelog

All notable changes to haris are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Changed
- Read, Edit, Write and the other file and web tools are checked without loading the command parser: the path helpers (read_paths, write_paths, Ctx) moved to haris/targets.py, which classify.py re-exports, and the secret patterns, injection scanner and temp-folder lookup load only for the calls that use them. Their pre-tool-use hook went from about 90-110 ms to about 45-55 ms; decisions are unchanged. (#102)
- A source checkout of haris, mizan or tabib in a git repo (the Nexika repo) is now ordinary project code: Claude can import and run it. Only the installed copies under ~/.claude/plugins and the plugins' data stay protected. Running a checkout's haris hook by hand is refused when it would use your real haris data (no HARIS_HOME or HOME of its own), and asked about when its data folder is only known when it runs. (#119)
- The prompt-injection scanner now catches paraphrased orders and fake system blocks, no longer flags documentation that only names an attack, is checked against a labelled corpus, and asks for caution for one message instead of three when the text came from a file the repository tracks. (#63)
- haris guards lawha's check records (`~/.claude/nexika/lawha`) like itqan's proofs and tabib's diagnoses, so a passing lawha check in mizan's band or an itqan proof always comes from lawha, never from Claude. (#18)

### Fixed
- A script that deletes a path haris cannot work out (a variable, a computed name) now gets an ask that says so, instead of the never-overridable "Deletes /" refusal taken from an unrelated "/" elsewhere in the script. Deletes that really name / or your home folder are still refused. (#116)
- Far fewer false asks on everyday work (14.7% of tool calls in a replay of 277 past sessions, now 11.3%): Python scripts that edit files are no longer "running shell commands" because of Markdown backticks or code they hold as text, a script's writes go where its write call says (a stray "/" is no longer "Writes to /"), git fetch never asks where the repository is, and git in a temporary folder such as the session scratchpad counts as a temporary write. (#117)
- haris asks less: another worktree of the same repository counts as the project, Claude Code's memory folder for this project counts too, and an ask about writing outside the project ends with the /haris:allow --project line that keeps your yes for that folder. A folder you approve no longer covers its .git, hooks, CI workflows or Claude settings. (#122)
- The session-start and prompt hooks exit inside a Nexika background model call (NEXIKA_BACKGROUND=1); the tool guard stays on, so setting the variable by hand never switches it off. (#45)
- Hooks start faster: the classifier loads only for a call haris checks (shell, file, web and MCP tools), so tools it never objects to (TodoWrite, Task, Skill, ...), tool output scans, prompts and session start skip it, and hooks skip argparse. Settings and the tool list moved to haris/config.py; policy still exports the same names. (#50)
- Reasons and the audit log no longer show raw control characters (a computed branch name reads <computed>), and gh api calls that send a body are labelled POST, as gh sends them, instead of GET. (#90)

## [0.1.0] - 2026-10-06

### Added
- haris, a guard against harmful agent actions: every tool call (subagents included) is read by a real shell parser that unwraps wrappers and judged by its action and target; safe reads and project runs are allowed, risky actions asked about and dangerous ones refused with a plain reason; secrets, persistence spots and haris itself are protected, data leaving the machine is checked for secrets, prompt injection in tool output is flagged, approvals count only when you type them, and every ask and refusal is kept in an owner-only, redacted audit log. Profiles relaxed, standard and strict; a watch mode. Actions refused in every profile cannot be approved; a script written and run in the same command is read and judged before it runs; HTTP DELETE to another computer asks, like `gh api -X DELETE`.

### Changed
- haris also guards mizan (its code, its folder and settings) and the shared Nexika status files under ~/.claude/nexika/status, refuses running mizan's hooks or publishing its status by hand, and publishes its own profile and mode for mizan's band.
- haris also guards tabib's diagnoses (~/.claude/nexika/tabib) and refuses running tabib's code outside its helper.
