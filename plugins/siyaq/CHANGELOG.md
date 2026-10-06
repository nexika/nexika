# Changelog

All notable changes to siyaq are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-06

### Added
- siyaq, project knowledge loaded only when relevant: entries generated from your docs, multilingual matching (Arabic included) with ranking and a token budget, triggers on the files being touched, and stats on what helped and what is missing. (#9)

### Changed
- siyaq loads less as the context fills, by mizan's level: half the budget and one entry fewer at mid, only the strongest match as a summary when full.
