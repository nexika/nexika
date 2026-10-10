# Changelog

All notable changes to haris are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-10

### Changed
- `pre-commit install` (and `--hook-type`, `init-templatedir`) now asks, naming the git hook it writes; `pre-commit run` is still allowed. (#140)
- Writes to `$GITHUB_OUTPUT`, `$GITHUB_ENV`, `$GITHUB_STEP_SUMMARY` and `$GITHUB_PATH` (CI step commands) are treated like temp files and no longer ask. (#142)
- `stable` is now a protected branch by default: force-pushing it is refused, like `main` and `release/*`. (#143)
- Fewer asks that are not risk: a write whose file name alone is computed (`> logs/$id.log` in a loop) is judged by its folder, `git branch -D` of a branch whose work is on a remote (pushed, or squash-merged with its remote branch gone) no longer asks, git in a repository inside a folder you approved is covered by that approval, and the second ask about writes in one folder offers that whole folder. `haris check` now applies your project approvals and says so. (#210)

### Fixed
- `haris check --json` works again (it crashed), and `head -50 FILE` no longer reads -50 as a file name. (#137)
- `python -m twine upload` and `python -m hatch publish` now ask like `twine upload` and `hatch publish`: a tool run as a Python module gets its own rule. (#138)
- Printing the environment through a filter for secret names (`env | grep -i token`, `printenv | grep KEY`, `set | grep -i password`) now asks, like `echo $GITHUB_TOKEN`. (#139)
- A git checkout, switch, restore, reset or clean in a folder outside the project (after `cd` or with `git -C`) now asks, like other writes outside the project. (#141)
- Arabic text that only describes someone ignoring rules (يتجاهل Claude القواعد) is no longer flagged as prompt injection; orders such as تجاهل جميع التعليمات or وتجاهل القواعد still are. (#212)
- curl ... | sh - and | bash /dev/stdin are seen as running a download, like | sh (#214)
- env | grep -i npm (or github, aws) asks: the filter would print NPM_TOKEN and similar secrets (#215)
- npm config set (and pnpm/yarn config set) is judged as a write to ~/.npmrc, which holds tokens, so it asks; a secret echoed into a file now says which file (#216)
- husky, lefthook install and simple-git-hooks ask like pre-commit install, also through npx and node_modules/.bin: they make git run hook scripts later (#217)
- gh workflow run asks when the workflow's name says it deploys, publishes or releases (deploy-website.yml, release.yml) (#218)
- gcloud builds submit --tag (or --config) asks: it builds and publishes an image, like docker push (#219)
- npx, npm exec and pnpm dlx of a URL or git repository (https://..., github:user/repo, user/repo) ask as download-and-run; registry packages keep passing (#220)
- The project's own test, lint and coverage tools from node_modules/.bin that its package.json scripts run (borp, c8, tstyche, markdownlint-cli2) are allowed like npm run; cross-env is read like env (#221)
- Reading a project .npmrc that git tracks and that holds no token no longer asks; turning off ignore-scripts in .npmrc (edit, sed, echo or npm config set) asks (#222)
- npm publish --dry-run (and pnpm/yarn) no longer asks: it sends nothing. The README's allow example now shows one that works (#223)
- Writing under /Applications on macOS asks as a write outside the project instead of being refused as the operating system; deleting all of /Applications is still refused (#224)
- Defining an alias no longer asks; when the same command uses the alias, what it stands for is checked (#225)
- npm pkg get, npm whoami and npm ping are allowed as reads; npm -v and cd ... && npm run show the reason of the step that decides (#226)
- Release lines like 4.x and 5.x, and next, are protected branches by default: force-pushing them is refused (#227)
- rimraf, del-cli and shx rm are judged like rm -r, also through npx and npm exec: rimraf ~ is refused, deleting outside the project asks (#264)
- Python's pass statement inside code handed to python -c from inline code is no longer read as the pass password manager (#266)
- git config core.hooksPath /dev/null and git -c core.hooksPath=/dev/null only switch hooks off and run nothing, so haris no longer refuses or asks about them (#267)

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
