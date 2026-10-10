# Changelog

All notable changes to itqan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-10-10

### Changed
- The guard asks before SKIP=<hook> git commit, which skips pre-commit hooks like --no-verify, and protects the stable branch from force pushes by default. (#148)
- Release lines named like `4.x` or `5.x` and the `next` branch are now protected by default: the guard refuses a force-push to them. The guard also asks before ignore-scripts is turned off in `.npmrc` (removing `ignore-scripts=true`, setting it to `false`, or `npm config set ignore-scripts false`). (#267)

### Fixed
- The proof now runs a Python project's pre-commit hooks, mypy and lint-style tox environments, lists the checks it found but could not run, and no longer reports passed when a test or lint check was skipped. (#144)
- The proof runs a Python project's tests with tox -e py when tox.ini defines them, and says the dependencies are not installed, instead of reporting failed tests, when the tests cannot import the project's own package. (#145)
- The guard now treats a PyPI token, and every other token shape Nexika redacts, as a secret: writing one asks and committing one is refused. Editing .pypirc or .netrc asks like .env. (#146)
- The guard now checks commands inside bash -c, asks about curl piped to python and about hatch, uv, poetry and flit publish, and no longer asks when grep searches for DROP TABLE. (#147)
- Learning from corrections now catches "use X, not Y", polite requests (please remove, rather than, shouldn't, back it out) and GitHub suggestion blocks, and no longer treats "no rush", a quoted "never" or "whether X should be" as a correction. (#149)
- The session note now lists the project's own test and lint commands (tox environments, pre-commit, pytest, ruff), the ones the proof runs, and the python pack no longer suggests ruff ahead of them. (#151)
- A Node project whose dependencies are not installed (no node_modules) no longer gets a false red proof: its package-script checks are listed as not run, with the install command that matches its lockfile (npm ci, pnpm install --frozen-lockfile, yarn install --immutable, or npm install when there is none). (#228)
- The proof splits a package `test` script that is a chain (`npm run lint && npm run unit && npm run test:types`) into one check per step, so lint runs once, a failing step no longer hides the next ones, and each step gets its own kind. Package scripts the CI workflows run are no longer invisible: a lint script is run, and another check script (such as a coverage gate) is listed as not run. (#229)
- Proof checks from package scripts are named by a command that runs: `npm run lint` instead of `npm lint`, which npm does not know (`npm test` keeps its short name). (#230)
- The Node pack now points to the project's own checks (the session note's Project checks line) before any default command, names the type-test scripts (test:types, typecheck, tsd, tstyche), offers `npx tsc --noEmit` only when a root tsconfig.json exists, and covers node:test, borp, tap and in-process HTTP tests (fastify.inject, supertest). (#231)
- The guard asks before `git commit -nm` and `-anm`, which skip the hooks like `--no-verify`, on its own and beside haris; `git commit -mn` (message "n") still passes. (#232)
- The guard reads npm, pnpm and yarn publish from the command's words: `npm --tag next publish`, `pnpm -r publish` and `npm -w a publish` now ask, and `npm publish --dry-run` no longer does. (#233)
- The correction detector now catches review wording such as "can you avoid ...", "must not", "I prefer X to Y", "prefer X over Y", "please rewrite" and "before committing", and ignores quoted lines (`> ...`) in a pasted review thread, whose words are the other person's. (#234)
- The guard now applies the rm -r target rules to rimraf, del-cli and shx rm -r, also through npx and npm exec: `npx rimraf ~` is refused like `rm -rf ~`. (#265)

## [0.3.0] - 2026-10-08

### Added
- The proof refuses an approve verdict while a critical or high review finding is still open, and /itqan:insights now reports what background learning cost and how often you approved what the guard asked about (its likely false alarms). (#76)
- When a change touches the UI and lawha is installed, /itqan:ship checks the affected pages on every screen with /lawha:check --fix, and the proof shows lawha's check of that commit as "pages on every screen"; a failing one fails the proof. (#18)

### Changed
- The background-call consent shares the one Nexika settings file (~/.claude/nexika/settings.json) with the family role; an existing settings.json keeps its answer and is stamped with schema nexika.settings/1 once. (#108)
- Learning from corrections no longer runs Claude in the background without consent: it needs the family setting background_calls on (scripts/itqan_background.py on); until then the extraction is skipped and itqan asks once. Each call is counted, runs with NEXIKA_BACKGROUND=1 so no Nexika hooks fire inside it, and itqan's session hooks exit inside other plugins' background calls (the guard stays on). (#45)

### Fixed
- Approving a rule on one branch no longer retires or deletes rules approved on another branch, and rules in .itqan/rules.md that itqan did not write are never rewritten. (#24)
- /itqan:ship runs the same tests the proof runs (itqan's own detection) instead of barq's pick, and itqan_proof.py checks now shows each check's command. (#47)
- With haris active, itqan now keeps its quality rules (secret files, lock files, secrets in new content, skipping git hooks) instead of going silent, takes the full guard back when haris is switched off or disabled, and costs almost nothing on calls haris covers. (#48)
- The learning hooks load the secret patterns only when they keep text (a correction or an extraction), not on every prompt or skill use. (#50)
- /itqan:proof now runs Python checks the way the project does (uv run when there is a uv.lock, else the project's virtualenv), and the start note detects stacks from the repository root, not the current folder. (#88)

### Security
- Prompts, guard decisions and usage logs are now stored with secrets redacted, readable only by you, and rotated at 1 MB. (#23)
- Proofs now hide every secret the rest of the family hides (Stripe keys, JWTs, Bearer tokens and more), not only 9 token shapes; hidden values read [secret]. (#44)

## [0.2.0] - 2026-10-06

### Added
- itqan, a quality workflow without the friction: plan, failing tests first, implement, verify and a specialist review (/itqan:plan, /itqan:review, /itqan:ship), a guard that only stops risky actions, and checklists loaded only for the stacks a project uses (Python, .NET, Node, Go). (#3)
- itqan learns project rules from your corrections and proposes them for your approval (/itqan:learn), and /itqan:insights shows which skills, agents and rules help. (#4)
- /itqan:proof: itqan runs the project's own tests, lint and build checks itself and saves the proof as JSON with the review verdict and the requirement checklist (marked as reported by Claude); mizan shows it when you say yes to "Done. Show me the proof?". /itqan:ship now ends with the proof.

### Changed
- The guard steps aside in sessions that haris guards, since haris covers its rules and more; the workflow, reviews and checklists are unchanged.
- The proof names the CI failure tabib diagnosed on the branch and whether it was reproduced before the fix.
