# Changelog

All notable changes to itqan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

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
