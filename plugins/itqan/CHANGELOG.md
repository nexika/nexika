# Changelog

All notable changes to itqan are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-06

### Added
- itqan, a quality workflow without the friction: plan, failing tests first, implement, verify and a specialist review (/itqan:plan, /itqan:review, /itqan:ship), a guard that only stops risky actions, and checklists loaded only for the stacks a project uses (Python, .NET, Node, Go). (#3)
- itqan learns project rules from your corrections and proposes them for your approval (/itqan:learn), and /itqan:insights shows which skills, agents and rules help. (#4)
- /itqan:proof: itqan runs the project's own tests, lint and build checks itself and saves the proof as JSON with the review verdict and the requirement checklist (marked as reported by Claude); mizan shows it when you say yes to "Done. Show me the proof?". /itqan:ship now ends with the proof.

### Changed
- The guard steps aside in sessions that haris guards, since haris covers its rules and more; the workflow, reviews and checklists are unchanged.
- The proof names the CI failure tabib diagnosed on the branch and whether it was reproduced before the fix.
