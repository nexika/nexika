# Changelog

All notable changes to tabib are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-06

### Added
- tabib finds out why CI failed, with evidence: it reads the failed GitHub Actions run or GitLab pipeline, pulls out the failing tests and errors (pytest, jest, vitest, go, dotnet, cargo, tsc, ruff, eslint), sorts the failure (code, one Python or OS only, flaky, infrastructure such as a cancelled run or the network, dependencies), compares with the last green run, runs the failing tests again in a throwaway git worktree, and reports the cause with evidence through /tabib:diagnose. It diagnoses only: it never edits code, pushes or re-runs CI; flaky and infrastructure failures come with the re-run command for you to run. English and Arabic.
